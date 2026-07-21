"""Local-first DOCX CV extraction with selective embedded-image OCR.

Ordinary recoverable DOCX text never goes to Mistral. Only embedded images
classified as likely text regions (not logos/photos/icons) may call
mistral-ocr-4-0 when local XML text cannot recover that content.
"""

from __future__ import annotations

import hashlib
import logging
import re
import zipfile
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any
from xml.etree import ElementTree as ET

import cv_extraction as cv

logger = logging.getLogger("wathefni.cv_docx")

DOCX_PREPROCESS_VERSION = "cv_docx_preprocess_v2"
DOCX_EXTRACT_OPTIONS_VERSION = "cv_docx_opts_v2"
W_NS = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
R_NS = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"
V_NS = "{urn:schemas-microsoft-com:vml}"

_IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".tif", ".tiff", ".webp"}
_SKIP_NAME_RE = re.compile(
    r"(logo|icon|avatar|photo|portrait|headshot|selfie|profile.?pic|signature|stamp|badge)",
    re.I,
)
_EMAIL_HINT = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,24}")
_PHONE_HINT = re.compile(r"(?:\+?965)?\s*[569]\d{7}|\b0?[569]\d{7}\b")


@dataclass
class DocxBlock:
    block_id: str
    kind: str  # paragraph|table_cell|header|footer|textbox|hyperlink|image_ocr
    text: str
    order: int
    rtl: bool = False
    bilingual: bool = False
    href: str | None = None
    table_row: int | None = None
    table_col: int | None = None
    section: str = "body"  # header|body|footer
    source_part: str = "word/document.xml"
    image_part: str | None = None
    engine: str = "docx-local"
    model: str | None = None
    confidence: float | None = 1.0

    def to_dict(self) -> dict[str, Any]:
        return {k: v for k, v in asdict(self).items() if v is not None}


@dataclass
class DocxImage:
    part_name: str
    content_type: str
    data: bytes
    width: int | None = None
    height: int | None = None
    classification: str = "unknown"
    reason: str = ""
    sha256: str = ""

    def __post_init__(self) -> None:
        if not self.sha256 and self.data:
            self.sha256 = hashlib.sha256(self.data).hexdigest()


@dataclass
class DocxQuality:
    ok: bool
    needs_review: bool
    reasons: list[str] = field(default_factory=list)
    missing_contact: bool = False
    image_heavy: bool = False
    corrupted: bool = False
    broken_order: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _local(tag: str) -> str:
    if "}" in tag:
        return tag.rsplit("}", 1)[-1]
    return tag


def _text_of_node(node: ET.Element) -> str:
    parts: list[str] = []
    for t in node.iter(f"{W_NS}t"):
        if t.text:
            parts.append(t.text)
        if t.tail:
            parts.append(t.tail)
    return "".join(parts)


def _paragraph_rtl(paragraph: ET.Element) -> bool:
    ppr = paragraph.find(f"{W_NS}pPr")
    if ppr is not None and ppr.find(f"{W_NS}bidi") is not None:
        return True
    for rpr in paragraph.iter(f"{W_NS}rPr"):
        if rpr.find(f"{W_NS}rtl") is not None or rpr.find(f"{W_NS}cs") is not None:
            return True
    return False


def _is_bilingual(text: str) -> bool:
    has_ar = bool(re.search(r"[\u0600-\u06FF]", text or ""))
    has_lat = bool(re.search(r"[A-Za-z]", text or ""))
    return has_ar and has_lat


def _read_rels(archive: zipfile.ZipFile, rels_path: str) -> dict[str, dict[str, str]]:
    out: dict[str, dict[str, str]] = {}
    try:
        root = ET.fromstring(archive.read(rels_path))
    except Exception:
        return out
    for rel in root:
        if _local(rel.tag) != "Relationship":
            continue
        rid = rel.attrib.get("Id") or ""
        target = rel.attrib.get("Target") or ""
        rel_type = rel.attrib.get("Type") or ""
        if rid:
            out[rid] = {"target": target, "type": rel_type}
    return out


def _resolve_part(base_dir: str, target: str) -> str:
    if target.startswith("/"):
        return target.lstrip("/")
    base = base_dir.strip("/")
    parts = (base.split("/") if base else []) + target.split("/")
    stack: list[str] = []
    for part in parts:
        if part in ("", "."):
            continue
        if part == "..":
            if stack:
                stack.pop()
            continue
        stack.append(part)
    return "/".join(stack)


def _png_size(data: bytes) -> tuple[int | None, int | None]:
    if len(data) >= 24 and data[:8] == b"\x89PNG\r\n\x1a\n":
        w = int.from_bytes(data[16:20], "big")
        h = int.from_bytes(data[20:24], "big")
        return w, h
    return None, None


def _jpeg_size(data: bytes) -> tuple[int | None, int | None]:
    if len(data) < 4 or data[:2] != b"\xff\xd8":
        return None, None
    i = 2
    while i + 9 < len(data):
        if data[i] != 0xFF:
            i += 1
            continue
        marker = data[i + 1]
        if marker in (0xC0, 0xC1, 0xC2):
            h = int.from_bytes(data[i + 5 : i + 7], "big")
            w = int.from_bytes(data[i + 7 : i + 9], "big")
            return w, h
        length = int.from_bytes(data[i + 2 : i + 4], "big")
        i += 2 + length
    return None, None


def _image_dimensions(data: bytes, content_type: str, part_name: str) -> tuple[int | None, int | None]:
    lower = part_name.lower()
    if "png" in content_type or lower.endswith(".png"):
        return _png_size(data)
    if "jpeg" in content_type or "jpg" in content_type or lower.endswith((".jpg", ".jpeg")):
        return _jpeg_size(data)
    w, h = _png_size(data)
    if w:
        return w, h
    return _jpeg_size(data)


def mimetypes_guess(suffix: str) -> str:
    return {
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".gif": "image/gif",
        ".bmp": "image/bmp",
        ".tif": "image/tiff",
        ".tiff": "image/tiff",
        ".webp": "image/webp",
    }.get(suffix, "application/octet-stream")


def classify_embedded_image(img: DocxImage) -> DocxImage:
    name = img.part_name.split("/")[-1]
    size = len(img.data or b"")
    w, h = img.width, img.height
    if w is None or h is None:
        w, h = _image_dimensions(img.data, img.content_type, img.part_name)
        img.width, img.height = w, h

    if _SKIP_NAME_RE.search(name):
        if re.search(r"(photo|portrait|headshot|selfie|avatar|profile)", name, re.I):
            img.classification = "skip_photo"
            img.reason = "filename_photo"
            return img
        img.classification = "skip_logo"
        img.reason = "filename_logo_or_icon"
        return img

    if size < 8_000:
        img.classification = "skip_icon"
        img.reason = "tiny_file"
        return img

    if w and h:
        mx, mn = max(w, h), min(w, h)
        if mx < 120 or mn < 80:
            img.classification = "skip_icon"
            img.reason = "tiny_dimensions"
            return img
        ratio = mx / max(mn, 1)
        if 0.85 <= ratio <= 1.25 and 120 <= mx <= 900 and "jpeg" in (img.content_type or "").lower():
            img.classification = "skip_photo"
            img.reason = "square_jpeg_portrait_heuristic"
            return img
        if mx >= 220 or size >= 25_000:
            img.classification = "text_candidate"
            img.reason = "large_enough_for_text"
            return img

    if size >= 40_000:
        img.classification = "text_candidate"
        img.reason = "large_payload"
        return img

    img.classification = "unknown"
    img.reason = "ambiguous_skip_default"
    return img


def _hyperlink_map(archive: zipfile.ZipFile, part_name: str) -> dict[str, str]:
    rels_path = str(Path(part_name).parent / "_rels" / f"{Path(part_name).name}.rels").replace("\\", "/")
    rels = _read_rels(archive, rels_path)
    return {
        rid: meta["target"]
        for rid, meta in rels.items()
        if "hyperlink" in (meta.get("type") or "").lower()
    }


def _collect_textbox_paragraphs(node: ET.Element) -> list[ET.Element]:
    found: list[ET.Element] = []
    for txbx in node.iter(f"{W_NS}txbxContent"):
        for child in list(txbx):
            if child.tag == f"{W_NS}p":
                found.append(child)
            elif child.tag == f"{W_NS}tbl":
                for p in child.iter(f"{W_NS}p"):
                    found.append(p)
    for vtextbox in node.iter(f"{V_NS}textbox"):
        for p in vtextbox.iter(f"{W_NS}p"):
            found.append(p)
    return found


def _emit_paragraph_blocks(
    paragraph: ET.Element,
    *,
    order_start: int,
    section: str,
    source_part: str,
    kind: str,
    hyperlinks: dict[str, str],
    table_row: int | None = None,
    table_col: int | None = None,
) -> tuple[list[DocxBlock], int]:
    blocks: list[DocxBlock] = []
    order = order_start
    rtl = _paragraph_rtl(paragraph)

    for hyper in paragraph.findall(f"{W_NS}hyperlink"):
        rid = hyper.attrib.get(f"{R_NS}id") or hyper.attrib.get("id")
        href = hyperlinks.get(rid or "", None)
        htext = _text_of_node(hyper).strip()
        if htext or href:
            order += 1
            blocks.append(
                DocxBlock(
                    block_id=f"{section}-hlink-{order}",
                    kind="hyperlink",
                    text=htext or (href or ""),
                    order=order,
                    rtl=rtl,
                    bilingual=_is_bilingual(htext),
                    href=href,
                    table_row=table_row,
                    table_col=table_col,
                    section=section,
                    source_part=source_part,
                )
            )

    text = _text_of_node(paragraph).strip()
    if text:
        order += 1
        blocks.append(
            DocxBlock(
                block_id=f"{section}-{kind}-{order}",
                kind=kind,
                text=text,
                order=order,
                rtl=rtl,
                bilingual=_is_bilingual(text),
                table_row=table_row,
                table_col=table_col,
                section=section,
                source_part=source_part,
            )
        )

    for tb_p in _collect_textbox_paragraphs(paragraph):
        tb_text = _text_of_node(tb_p).strip()
        if not tb_text:
            continue
        order += 1
        blocks.append(
            DocxBlock(
                block_id=f"{section}-textbox-{order}",
                kind="textbox",
                text=tb_text,
                order=order,
                rtl=_paragraph_rtl(tb_p),
                bilingual=_is_bilingual(tb_text),
                section=section,
                source_part=source_part,
            )
        )
    return blocks, order


def _walk_block_container(
    container: ET.Element,
    *,
    order: int,
    section: str,
    source_part: str,
    hyperlinks: dict[str, str],
    default_kind: str = "paragraph",
) -> tuple[list[DocxBlock], int]:
    blocks: list[DocxBlock] = []
    for child in list(container):
        tag = child.tag
        if tag == f"{W_NS}p":
            more, order = _emit_paragraph_blocks(
                child,
                order_start=order,
                section=section,
                source_part=source_part,
                kind=default_kind,
                hyperlinks=hyperlinks,
            )
            blocks.extend(more)
        elif tag == f"{W_NS}tbl":
            for r_idx, row in enumerate(child.findall(f"{W_NS}tr")):
                for c_idx, cell in enumerate(row.findall(f"{W_NS}tc")):
                    for p in cell.findall(f"{W_NS}p"):
                        more, order = _emit_paragraph_blocks(
                            p,
                            order_start=order,
                            section=section,
                            source_part=source_part,
                            kind="table_cell",
                            hyperlinks=hyperlinks,
                            table_row=r_idx,
                            table_col=c_idx,
                        )
                        blocks.extend(more)
        else:
            for p in child.findall(f".//{W_NS}p"):
                more, order = _emit_paragraph_blocks(
                    p,
                    order_start=order,
                    section=section,
                    source_part=source_part,
                    kind="textbox" if _collect_textbox_paragraphs(child) else default_kind,
                    hyperlinks=hyperlinks,
                )
                blocks.extend(more)
    return blocks, order


def _body_element(document_root: ET.Element) -> ET.Element | None:
    return document_root.find(f"{W_NS}body")


def _header_footer_parts(archive: zipfile.ZipFile) -> tuple[list[str], list[str]]:
    rels = _read_rels(archive, "word/_rels/document.xml.rels")
    headers: list[str] = []
    footers: list[str] = []
    for meta in rels.values():
        target = meta.get("target") or ""
        rel_type = (meta.get("type") or "").lower()
        part = _resolve_part("word", target)
        if "header" in rel_type or re.search(r"header\d*\.xml$", part):
            headers.append(part)
        elif "footer" in rel_type or re.search(r"footer\d*\.xml$", part):
            footers.append(part)
    return sorted(set(headers)), sorted(set(footers))


def _content_types(archive: zipfile.ZipFile) -> dict[str, str]:
    mapping: dict[str, str] = {}
    try:
        root = ET.fromstring(archive.read("[Content_Types].xml"))
    except Exception:
        return mapping
    for node in root:
        local = _local(node.tag)
        if local == "Override":
            part = (node.attrib.get("PartName") or "").lstrip("/")
            ctype = node.attrib.get("ContentType") or ""
            if part:
                mapping[part] = ctype
        elif local == "Default":
            ext = (node.attrib.get("Extension") or "").lower()
            ctype = node.attrib.get("ContentType") or ""
            if ext:
                mapping[f"*.{ext}"] = ctype
    return mapping


def extract_docx_images(archive: zipfile.ZipFile) -> list[DocxImage]:
    types = _content_types(archive)
    images: list[DocxImage] = []
    for name in archive.namelist():
        if not name.startswith("word/media/"):
            continue
        suffix = Path(name).suffix.lower()
        if suffix not in _IMAGE_EXTS:
            continue
        try:
            data = archive.read(name)
        except Exception:
            continue
        ctype = types.get(name) or types.get(f"*{suffix}") or mimetypes_guess(suffix)
        img = DocxImage(part_name=name, content_type=ctype, data=data)
        images.append(classify_embedded_image(img))
    return images


def parse_docx_local(path: Path) -> tuple[list[DocxBlock], list[DocxImage], dict[str, Any]]:
    meta: dict[str, Any] = {"corrupted": False, "error": None}
    try:
        archive = zipfile.ZipFile(path)
    except Exception as exc:
        meta["corrupted"] = True
        meta["error"] = f"zip_open:{type(exc).__name__}"
        return [], [], meta

    with archive:
        try:
            document_xml = archive.read("word/document.xml")
            document_root = ET.fromstring(document_xml)
        except Exception as exc:
            meta["corrupted"] = True
            meta["error"] = f"document_xml:{type(exc).__name__}"
            return [], [], meta

        blocks: list[DocxBlock] = []
        order = 0
        headers, footers = _header_footer_parts(archive)

        for part in headers:
            try:
                root = ET.fromstring(archive.read(part))
            except Exception:
                continue
            hyperlinks = _hyperlink_map(archive, part)
            container = root
            more, order = _walk_block_container(
                container,
                order=order,
                section="header",
                source_part=part,
                hyperlinks=hyperlinks,
                default_kind="header",
            )
            blocks.extend(more)

        body = _body_element(document_root)
        if body is not None:
            hyperlinks = _hyperlink_map(archive, "word/document.xml")
            more, order = _walk_block_container(
                body,
                order=order,
                section="body",
                source_part="word/document.xml",
                hyperlinks=hyperlinks,
                default_kind="paragraph",
            )
            blocks.extend(more)

        for part in footers:
            try:
                root = ET.fromstring(archive.read(part))
            except Exception:
                continue
            hyperlinks = _hyperlink_map(archive, part)
            more, order = _walk_block_container(
                root,
                order=order,
                section="footer",
                source_part=part,
                hyperlinks=hyperlinks,
                default_kind="footer",
            )
            blocks.extend(more)

        deduped: list[DocxBlock] = []
        seen: set[tuple[str, str, str]] = set()
        for block in blocks:
            key = (block.section, block.kind, block.text)
            if key in seen and block.kind != "table_cell":
                continue
            seen.add(key)
            deduped.append(block)
        for idx, block in enumerate(deduped, start=1):
            block.order = idx

        images = extract_docx_images(archive)
        meta.update(
            {
                "header_parts": headers,
                "footer_parts": footers,
                "block_count": len(deduped),
                "image_count": len(images),
                "text_candidate_images": sum(1 for i in images if i.classification == "text_candidate"),
            }
        )
        return deduped, images, meta


def blocks_to_text(blocks: list[DocxBlock]) -> str:
    parts: list[str] = []
    for block in sorted(blocks, key=lambda b: b.order):
        text = (block.text or "").strip()
        if not text:
            continue
        if block.kind == "hyperlink" and block.href and block.href not in text:
            parts.append(f"{text} ({block.href})")
        else:
            parts.append(text)
    return "\n".join(parts).strip()


def docx_quality_check(
    text: str,
    blocks: list[DocxBlock],
    images: list[DocxImage],
    *,
    corrupted: bool = False,
) -> DocxQuality:
    reasons: list[str] = []
    if corrupted:
        return DocxQuality(ok=False, needs_review=True, reasons=["corrupted_docx"], corrupted=True)

    words = cv.word_count(text)
    has_email = bool(_EMAIL_HINT.search(text or ""))
    has_phone = bool(_PHONE_HINT.search(cv.normalize_digits(text or "")))
    missing_contact = not has_email or not has_phone
    image_count = len(images)
    text_candidate = sum(1 for i in images if i.classification == "text_candidate")
    image_heavy = image_count >= 3 and words < 40

    multi = sum(1 for b in blocks if len((b.text or "").split()) >= 3)
    tiny = sum(1 for b in blocks if 0 < len((b.text or "").split()) <= 1)
    broken_order = bool(blocks) and tiny >= 12 and multi <= 2 and words < 80

    if not text.strip():
        reasons.append("no_text_extracted")
    elif not cv.cv_text_quality_ok(text):
        reasons.append("quality_gate_failed")
    if missing_contact and words >= 20:
        reasons.append("missing_contact_details")
    if image_heavy:
        reasons.append("image_heavy_sparse_text")
    if broken_order:
        reasons.append("suspicious_reading_order")
    if text_candidate and words < 30:
        reasons.append("unrecovered_embedded_image_text_likely")

    needs_review = bool(reasons) and (
        "no_text_extracted" in reasons
        or "image_heavy_sparse_text" in reasons
        or "suspicious_reading_order" in reasons
        or ("missing_contact_details" in reasons and "quality_gate_failed" in reasons)
        or ("unrecovered_embedded_image_text_likely" in reasons and not cv.mistral_ocr_enabled())
    )
    ok = cv.cv_text_quality_ok(text) and "no_text_extracted" not in reasons
    if missing_contact and ok and "missing_contact_details" in reasons:
        needs_review = True
    return DocxQuality(
        ok=ok,
        needs_review=needs_review or (not ok),
        reasons=reasons,
        missing_contact=missing_contact,
        image_heavy=image_heavy,
        corrupted=corrupted,
        broken_order=broken_order,
    )


def _image_already_covered_by_text(local_text: str, ocr_text: str) -> bool:
    local_norm = re.sub(r"\s+", " ", (local_text or "").lower())
    ocr_norm = re.sub(r"\s+", " ", (ocr_text or "").lower())
    if not ocr_norm:
        return True
    ocr_words = [w for w in re.findall(r"[a-z0-9\u0600-\u06ff]{3,}", ocr_norm)]
    if not ocr_words:
        return True
    hit = sum(1 for w in ocr_words if w in local_norm)
    return (hit / max(len(ocr_words), 1)) >= 0.8


def maybe_ocr_docx_images(
    images: list[DocxImage],
    local_text: str,
) -> tuple[list[DocxBlock], list[cv.EngineCallMeta], int]:
    blocks: list[DocxBlock] = []
    calls: list[cv.EngineCallMeta] = []
    ocr_calls = 0
    if not cv.mistral_ocr_enabled():
        return blocks, calls, ocr_calls

    order_base = 10_000
    for img in images:
        if img.classification != "text_candidate":
            continue
        if (
            cv.cv_text_quality_ok(local_text)
            and _EMAIL_HINT.search(local_text)
            and _PHONE_HINT.search(cv.normalize_digits(local_text))
            and len(img.data) < 80_000
        ):
            continue

        import tempfile

        suffix = Path(img.part_name).suffix.lower() or ".png"
        with tempfile.NamedTemporaryFile(prefix="docx-img-", suffix=suffix) as tmp:
            tmp.write(img.data)
            tmp.flush()
            text, ocr_blocks, meta = cv.extract_image_with_mistral(Path(tmp.name), img.content_type or "image/png")
            ocr_calls += 1
            meta.stage = "docx_embedded_image_ocr"
            meta.tier = "mistral_ocr"
            calls.append(meta)
            if not text or _image_already_covered_by_text(local_text, text):
                continue
            order_base += 1
            blocks.append(
                DocxBlock(
                    block_id=f"image-ocr-{order_base}",
                    kind="image_ocr",
                    text=text.strip(),
                    order=order_base,
                    bilingual=_is_bilingual(text),
                    section="body",
                    source_part=img.part_name,
                    image_part=img.part_name,
                    engine="mistral",
                    model=cv.MISTRAL_OCR_MODEL,
                    confidence=0.8 if meta.quality_ok else 0.4,
                )
            )
            for ob in ocr_blocks:
                ob["docx_image_part"] = img.part_name
    return blocks, calls, ocr_calls


def extract_docx_document(
    path: Path,
    *,
    company_code: str | None = None,
    document_id: str | None = None,
    app_key: str | None = None,
    db_execute: cv.DbExecute | None = None,
) -> cv.ExtractionResult:
    company = str(company_code or "").strip().upper()
    if not company:
        return cv.ExtractionResult(text="", method="scope-check", error="tenant_scope_required")
    if not path.exists() or not path.is_file():
        return cv.ExtractionResult(text="", method="missing-file", error="file_not_found")

    content = path.read_bytes()
    content_sha = cv.sha256_bytes(content)
    options = {
        "version": DOCX_EXTRACT_OPTIONS_VERSION,
        "include_headers_footers": True,
        "include_tables": True,
        "include_textboxes": True,
        "include_hyperlinks": True,
        "embedded_image_ocr": True,
        "ocr_model": cv.MISTRAL_OCR_MODEL,
    }

    blocks, images, parse_meta = parse_docx_local(path)
    local_text = blocks_to_text(blocks)
    image_hashes = [i.sha256 for i in images]
    cache_key = cv.build_cache_key(
        content_sha256=content_sha,
        page_hashes=image_hashes or [cv.sha256_text("docx-no-images")],
        preprocessing_version=DOCX_PREPROCESS_VERSION,
        provider="docx-local+mistral" if cv.mistral_ocr_enabled() else "docx-local",
        ocr_model=cv.MISTRAL_OCR_MODEL,
        api_version=cv.MISTRAL_OCR_API_VERSION,
        extraction_options=options,
    )

    if db_execute is not None:
        cached = cv.lookup_extraction_cache(db_execute, company_code=company, cache_key=cache_key)
        if cached and isinstance(cached.get("result"), dict):
            payload = cached["result"]
            text = str(payload.get("text") or "")
            quality_raw = payload.get("quality") if isinstance(payload.get("quality"), dict) else {}
            quality = DocxQuality(
                ok=bool(quality_raw.get("ok", cv.cv_text_quality_ok(text))),
                needs_review=bool(quality_raw.get("needs_review", False)),
                reasons=list(quality_raw.get("reasons") or []),
                missing_contact=bool(quality_raw.get("missing_contact", False)),
                image_heavy=bool(quality_raw.get("image_heavy", False)),
                corrupted=bool(quality_raw.get("corrupted", False)),
                broken_order=bool(quality_raw.get("broken_order", False)),
            )
            meta = cv.EngineCallMeta(
                stage="docx_extract",
                tier="docx_cache",
                provider="cache",
                actual_request_model="docx-local-v2",
                provider_response_model=str(cached.get("ocr_model") or "docx-local-v2"),
                provider_request_id=cached.get("provider_request_id"),
                latency_ms=int(cached.get("latency_ms") or 0),
                billable_pages=0,
                estimated_cost_usd=0.0,
                cache_hit=True,
                quality_ok=quality.ok,
                retention="cache_hit_no_provider_call",
            )
            cv.record_extraction_run(
                db_execute,
                company_code=company,
                document_id=document_id,
                app_key=app_key,
                content_sha256=content_sha,
                stage=meta.stage,
                tier=meta.tier,
                provider=meta.provider,
                actual_request_model=meta.actual_request_model,
                provider_response_model=meta.provider_response_model,
                pages_requested=None,
                pages_processed=0,
                billable_pages=0,
                estimated_cost_usd=0.0,
                latency_ms=meta.latency_ms,
                provider_request_id=meta.provider_request_id,
                quality_ok=quality.ok,
                cache_hit=True,
                error=None,
                metadata={"cache_key": cache_key, "docx": True, "ocr_call_count": 0},
            )
            return cv.ExtractionResult(
                text=text,
                method="docx-local-v2+cache",
                quality_ok=quality.ok,
                engine_calls=[meta],
                blocks=list(payload.get("blocks") or []),
                provenance=list(payload.get("provenance") or []),
                content_sha256=content_sha,
                cache_key=cache_key,
                cache_hit=True,
                metadata={
                    "stage": "docx_extract",
                    "tier": "docx_cache",
                    "provider": "cache",
                    "actual_request_model": "docx-local-v2",
                    "provider_response_model": meta.provider_response_model,
                    "needs_review": quality.needs_review,
                    "quality": quality.to_dict(),
                    "ocr_call_count": 0,
                    "cache_hit": True,
                },
            )

    engine_calls: list[cv.EngineCallMeta] = [
        cv.EngineCallMeta(
            stage="docx_extract",
            tier="docx_local",
            provider="local",
            actual_request_model="docx-local-v2",
            provider_response_model="docx-local-v2",
            billable_pages=0,
            estimated_cost_usd=0.0,
            quality_ok=bool(local_text),
            retention="local_only",
        )
    ]

    ocr_blocks, ocr_calls_meta, ocr_call_count = maybe_ocr_docx_images(images, local_text)
    engine_calls.extend(ocr_calls_meta)
    all_blocks = list(blocks) + list(ocr_blocks)
    for idx, block in enumerate(sorted(all_blocks, key=lambda b: b.order), start=1):
        block.order = idx
    text = blocks_to_text(all_blocks)
    quality = docx_quality_check(
        text,
        all_blocks,
        images,
        corrupted=bool(parse_meta.get("corrupted")),
    )
    engine_calls[0].quality_ok = quality.ok

    billable = sum(int(c.billable_pages or 0) for c in ocr_calls_meta)
    cost = sum(float(c.estimated_cost_usd or 0) for c in ocr_calls_meta)
    latency = sum(int(c.latency_ms or 0) for c in ocr_calls_meta)

    if db_execute is not None:
        cv.record_extraction_run(
            db_execute,
            company_code=company,
            document_id=document_id,
            app_key=app_key,
            content_sha256=content_sha,
            stage="docx_extract",
            tier="docx_local+ocr" if ocr_call_count else "docx_local",
            provider="local" if not ocr_call_count else "local+mistral",
            actual_request_model=cv.MISTRAL_OCR_MODEL if ocr_call_count else "docx-local-v2",
            provider_response_model=cv.MISTRAL_OCR_MODEL if ocr_call_count else "docx-local-v2",
            pages_requested=None,
            pages_processed=billable,
            billable_pages=billable,
            estimated_cost_usd=cost,
            latency_ms=latency,
            provider_request_id=next((c.provider_request_id for c in ocr_calls_meta if c.provider_request_id), None),
            quality_ok=quality.ok,
            cache_hit=False,
            error=None if quality.ok else ",".join(quality.reasons) or "docx_quality",
            metadata={
                "needs_review": quality.needs_review,
                "ocr_call_count": ocr_call_count,
                "image_classifications": [i.classification for i in images],
            },
        )
        if quality.ok or text:
            cv.store_extraction_cache(
                db_execute,
                company_code=company,
                cache_key=cache_key,
                content_sha256=content_sha,
                page_hashes=image_hashes or [cv.sha256_text("docx-no-images")],
                provider="docx-local+mistral" if ocr_call_count else "docx-local",
                ocr_model=cv.MISTRAL_OCR_MODEL if ocr_call_count else "docx-local-v2",
                api_version=cv.MISTRAL_OCR_API_VERSION,
                extraction_options=options,
                result={
                    "text": text,
                    "blocks": [b.to_dict() for b in all_blocks],
                    "provenance": [b.to_dict() for b in all_blocks],
                    "quality": quality.to_dict(),
                    "ocr_call_count": ocr_call_count,
                },
                billable_pages=billable,
                estimated_cost_usd=cost,
                latency_ms=latency,
                provider_request_id=next((c.provider_request_id for c in ocr_calls_meta if c.provider_request_id), None),
            )

    method = "docx-local-v2"
    if ocr_call_count:
        method = "docx-local-v2+mistral-ocr-4-0"
    error = None
    if parse_meta.get("corrupted"):
        error = str(parse_meta.get("error") or "corrupted_docx")
    elif not text:
        error = "no_text_extracted"
    elif not quality.ok:
        error = ",".join(quality.reasons) or "docx_quality"

    return cv.ExtractionResult(
        text=text,
        method=method,
        error=error,
        quality_ok=quality.ok,
        engine_calls=engine_calls,
        blocks=[b.to_dict() for b in all_blocks],
        provenance=[b.to_dict() for b in all_blocks],
        content_sha256=content_sha,
        cache_key=cache_key,
        metadata={
            "stage": "docx_extract",
            "tier": "docx_local+ocr" if ocr_call_count else "docx_local",
            "provider": "local+mistral" if ocr_call_count else "local",
            "actual_request_model": cv.MISTRAL_OCR_MODEL if ocr_call_count else "docx-local-v2",
            "provider_response_model": cv.MISTRAL_OCR_MODEL if ocr_call_count else "docx-local-v2",
            "needs_review": quality.needs_review,
            "quality": quality.to_dict(),
            "ocr_call_count": ocr_call_count,
            "images": [
                {
                    "part": i.part_name,
                    "classification": i.classification,
                    "reason": i.reason,
                    "width": i.width,
                    "height": i.height,
                    "bytes": len(i.data),
                }
                for i in images
            ],
            "billable_pages": billable,
            "estimated_cost_usd": cost,
            "preprocess_version": DOCX_PREPROCESS_VERSION,
        },
    )
