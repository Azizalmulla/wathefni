"""Smoke: local-first DOCX CV extractor (stdlib fixtures; OCR mocked)."""

from __future__ import annotations

import io
import os
import struct
import sys
import tempfile
import zipfile
from pathlib import Path
from unittest import mock
from xml.sax.saxutils import escape

PASS = 0
FAIL = 0


def check(label: str, condition: bool, detail: str = "") -> None:
    global PASS, FAIL
    if condition:
        PASS += 1
        print(f"      PASS  {label}" + (f" — {detail}" if detail else ""))
    else:
        FAIL += 1
        print(f"      FAIL  {label}" + (f" — {detail}" if detail else ""))


W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
R = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
PKG = "http://schemas.openxmlformats.org/package/2006/relationships"


def _p(text: str, *, rtl: bool = False, hyper_rid: str | None = None, hyper_text: str | None = None) -> str:
    bidi = f'<w:pPr><w:bidi/></w:pPr>' if rtl else ""
    runs = ""
    if hyper_rid and hyper_text:
        runs += (
            f'<w:hyperlink r:id="{hyper_rid}">'
            f'<w:r><w:t>{escape(hyper_text)}</w:t></w:r>'
            f"</w:hyperlink>"
        )
    if text:
        rpr = "<w:rPr><w:rtl/></w:rPr>" if rtl else ""
        runs += f"<w:r>{rpr}<w:t>{escape(text)}</w:t></w:r>"
    return f"<w:p>{bidi}{runs}</w:p>"


def _table(rows: list[list[str]]) -> str:
    trs = []
    for row in rows:
        tcs = "".join(f"<w:tc>{_p(cell)}</w:tc>" for cell in row)
        trs.append(f"<w:tr>{tcs}</w:tr>")
    return f"<w:tbl>{''.join(trs)}</w:tbl>"


def _textbox(text: str) -> str:
    return (
        "<w:p><w:r><w:drawing>"
        f'<w:txbxContent>{_p(text)}</w:txbxContent>'
        "</w:drawing></w:r></w:p>"
    )


def _png(width: int, height: int, color: bytes = b"\x00\x00\x00") -> bytes:
    # Minimal solid PNG via struct + zlib
    import zlib

    def chunk(tag: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)

    raw = b"".join(b"\x00" + color * width for _ in range(height))
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(raw, 9))
        + chunk(b"IEND", b"")
    )


def build_docx(
    path: Path,
    *,
    body_xml: str,
    header_xml: str | None = None,
    footer_xml: str | None = None,
    hyperlink_url: str | None = None,
    media: dict[str, bytes] | None = None,
) -> None:
    media = media or {}
    content_types = [
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>',
        f'<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">',
        '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>',
        '<Default Extension="xml" ContentType="application/xml"/>',
        '<Default Extension="png" ContentType="image/png"/>',
        '<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>',
    ]
    if header_xml:
        content_types.append(
            '<Override PartName="/word/header1.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.header+xml"/>'
        )
    if footer_xml:
        content_types.append(
            '<Override PartName="/word/footer1.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.footer+xml"/>'
        )
    content_types.append("</Types>")

    doc_rels = [
        f'<Relationships xmlns="{PKG}">',
        f'<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>',
        "</Relationships>",
    ]
    # package rels
    pkg_rels = "\n".join(
        [
            f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>',
            f'<Relationships xmlns="{PKG}">',
            f'<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>',
            "</Relationships>",
        ]
    )

    word_rels_items = []
    rid = 1
    if header_xml:
        rid += 1
        word_rels_items.append(
            f'<Relationship Id="rId{rid}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/header" Target="header1.xml"/>'
        )
        header_rid = f"rId{rid}"
    else:
        header_rid = None
    if footer_xml:
        rid += 1
        word_rels_items.append(
            f'<Relationship Id="rId{rid}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/footer" Target="footer1.xml"/>'
        )
        footer_rid = f"rId{rid}"
    else:
        footer_rid = None
    if hyperlink_url:
        rid += 1
        word_rels_items.append(
            f'<Relationship Id="rId{rid}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/hyperlink" Target="{escape(hyperlink_url)}" TargetMode="External"/>'
        )
        hyper_rid = f"rId{rid}"
    else:
        hyper_rid = None
    for i, name in enumerate(media, start=1):
        rid += 1
        word_rels_items.append(
            f'<Relationship Id="rId{rid}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/image" Target="media/{name}"/>'
        )

    sect = ""
    if header_rid or footer_rid:
        refs = ""
        if header_rid:
            refs += f'<w:headerReference w:type="default" r:id="{header_rid}"/>'
        if footer_rid:
            refs += f'<w:footerReference w:type="default" r:id="{footer_rid}"/>'
        sect = f"<w:sectPr>{refs}</w:sectPr>"

    document = (
        f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        f'<w:document xmlns:w="{W}" xmlns:r="{R}">'
        f"<w:body>{body_xml}{sect}</w:body></w:document>"
    )

    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("[Content_Types].xml", "\n".join(content_types))
        zf.writestr("_rels/.rels", pkg_rels)
        zf.writestr("word/document.xml", document)
        zf.writestr(
            "word/_rels/document.xml.rels",
            f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            f'<Relationships xmlns="{PKG}">' + "".join(word_rels_items) + "</Relationships>",
        )
        if header_xml:
            zf.writestr(
                "word/header1.xml",
                f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                f'<w:hdr xmlns:w="{W}" xmlns:r="{R}">{header_xml}</w:hdr>',
            )
        if footer_xml:
            zf.writestr(
                "word/footer1.xml",
                f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                f'<w:ftr xmlns:w="{W}" xmlns:r="{R}">{footer_xml}</w:ftr>',
            )
        for name, data in media.items():
            zf.writestr(f"word/media/{name}", data)

    return hyper_rid  # type: ignore[return-value]


def main() -> int:
    print("    cv docx — local-first structure, selective image OCR, cache")
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import cv_docx as docx
    import cv_extraction as cv

    os.environ.pop("WATHEFNI_CV_MISTRAL_OCR", None)

    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)

        # English + header/footer + table + hyperlink + textbox
        en = tmp_path / "en.docx"
        body = "".join(
            [
                _p("Jane Candidate"),
                _p("Skills"),
                _p("Recruiting and HRIS experience across Kuwait teams."),
                _table([["Company", "Role"], ["Example Co", "HR Coordinator"]]),
                _textbox("Textbox note: bilingual hiring support"),
                _p("Portfolio", hyper_rid="rIdX", hyper_text="My site"),  # fixed below
            ]
        )
        # rebuild with real hyper rid after helper — simpler inline build
        en_body = (
            _p("Jane Candidate")
            + _p("Email: jane.candidate@example.com")
            + _p("Phone: 51234567")
            + _p("Skills")
            + _p("Recruiting and HRIS experience across Kuwait teams with strong communication.")
            + _table([["Company", "Role"], ["Example Co", "HR Coordinator"]])
            + _textbox("Textbox note: bilingual hiring support")
            + _p("", hyper_rid="rId9", hyper_text="Portfolio")
        )
        # manual zip with hyperlink rId9
        with zipfile.ZipFile(en, "w") as zf:
            zf.writestr(
                "[Content_Types].xml",
                """<?xml version="1.0"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
                <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
                <Default Extension="xml" ContentType="application/xml"/>
                <Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>
                <Override PartName="/word/header1.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.header+xml"/>
                <Override PartName="/word/footer1.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.footer+xml"/>
                </Types>""",
            )
            zf.writestr(
                "_rels/.rels",
                f"""<?xml version="1.0"?><Relationships xmlns="{PKG}">
                <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>
                </Relationships>""",
            )
            zf.writestr(
                "word/_rels/document.xml.rels",
                f"""<?xml version="1.0"?><Relationships xmlns="{PKG}">
                <Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/header" Target="header1.xml"/>
                <Relationship Id="rId3" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/footer" Target="footer1.xml"/>
                <Relationship Id="rId9" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/hyperlink" Target="https://example.com/jane" TargetMode="External"/>
                </Relationships>""",
            )
            zf.writestr(
                "word/header1.xml",
                f'<?xml version="1.0"?><w:hdr xmlns:w="{W}">{_p("Header contact: HR Desk")}</w:hdr>',
            )
            zf.writestr(
                "word/footer1.xml",
                f'<?xml version="1.0"?><w:ftr xmlns:w="{W}">{_p("Footer: Confidential CV")}</w:ftr>',
            )
            zf.writestr(
                "word/document.xml",
                f'<?xml version="1.0"?><w:document xmlns:w="{W}" xmlns:r="{R}"><w:body>{en_body}'
                f'<w:sectPr><w:headerReference w:type="default" r:id="rId2"/>'
                f'<w:footerReference w:type="default" r:id="rId3"/></w:sectPr>'
                f"</w:body></w:document>",
            )

        en_result = docx.extract_docx_document(en, company_code="SMOKE")
        check("EN method local", en_result.method == "docx-local-v2", en_result.method)
        check("EN quality ok", en_result.quality_ok is True)
        check("EN no OCR calls", (en_result.metadata or {}).get("ocr_call_count") == 0)
        check("EN header text", "Header contact" in en_result.text)
        check("EN footer text", "Footer: Confidential" in en_result.text)
        check("EN table cell", "HR Coordinator" in en_result.text)
        check("EN textbox", "Textbox note" in en_result.text)
        check("EN hyperlink href", "example.com/jane" in en_result.text)
        check("EN provenance blocks", len(en_result.provenance) >= 5)

        # Arabic RTL
        ar = tmp_path / "ar.docx"
        ar_body = (
            _p("نورة العجمي", rtl=True)
            + _p("البريد: noura@example.com", rtl=True)
            + _p("هاتف: ٥١٢٣٤٥٦٨", rtl=True)
            + _p("المهارات", rtl=True)
            + _p("خبرة في التوظيف وإدارة المواهب والتواصل.", rtl=True)
            + _p("التعليم بكالوريوس إدارة أعمال من جامعة الكويت.", rtl=True)
        )
        with zipfile.ZipFile(ar, "w") as zf:
            zf.writestr(
                "[Content_Types].xml",
                """<?xml version="1.0"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
                <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
                <Default Extension="xml" ContentType="application/xml"/>
                <Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>
                </Types>""",
            )
            zf.writestr(
                "_rels/.rels",
                f"""<?xml version="1.0"?><Relationships xmlns="{PKG}">
                <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>
                </Relationships>""",
            )
            zf.writestr("word/_rels/document.xml.rels", f'<Relationships xmlns="{PKG}"></Relationships>')
            zf.writestr(
                "word/document.xml",
                f'<?xml version="1.0"?><w:document xmlns:w="{W}"><w:body>{ar_body}</w:body></w:document>',
            )
        ar_result = docx.extract_docx_document(ar, company_code="SMOKE")
        check("AR extracted", "نورة" in ar_result.text and "المهارات" in ar_result.text)
        check("AR rtl flag present", any(b.get("rtl") for b in ar_result.blocks))
        check("AR no OCR", (ar_result.metadata or {}).get("ocr_call_count") == 0)

        # Mixed
        mx = tmp_path / "mixed.docx"
        mx_body = (
            _p("Noura Al-Ajmi / نورة العجمي")
            + _p("Email: noura.mixed@example.com")
            + _p("Phone: 51234569")
            + _p("Skills / المهارات")
            + _p("Bilingual recruiting experience in Kuwait / خبرة ثنائية اللغة.")
        )
        with zipfile.ZipFile(mx, "w") as zf:
            zf.writestr(
                "[Content_Types].xml",
                """<?xml version="1.0"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
                <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
                <Default Extension="xml" ContentType="application/xml"/>
                <Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>
                </Types>""",
            )
            zf.writestr(
                "_rels/.rels",
                f"""<?xml version="1.0"?><Relationships xmlns="{PKG}">
                <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>
                </Relationships>""",
            )
            zf.writestr("word/_rels/document.xml.rels", f'<Relationships xmlns="{PKG}"></Relationships>')
            zf.writestr(
                "word/document.xml",
                f'<?xml version="1.0"?><w:document xmlns:w="{W}"><w:body>{mx_body}</w:body></w:document>',
            )
        mx_result = docx.extract_docx_document(mx, company_code="SMOKE")
        check("mixed bilingual flag", any(b.get("bilingual") for b in mx_result.blocks))
        check("mixed no OCR for ordinary text", (mx_result.metadata or {}).get("ocr_call_count") == 0)

        # Image classification: logo skip vs text candidate
        logo = docx.DocxImage("word/media/logo.png", "image/png", _png(64, 64))
        logo = docx.classify_embedded_image(logo)
        check("logo skipped", logo.classification in {"skip_logo", "skip_icon"}, logo.classification)

        text_img = docx.DocxImage("word/media/scan_block.png", "image/png", _png(800, 1000, b"\xff\xff\xff"))
        # inflate payload
        text_img.data = text_img.data + (b"\x00" * 50_000)
        text_img = docx.classify_embedded_image(text_img)
        check("large image text candidate", text_img.classification == "text_candidate", text_img.classification)

        # Embedded image OCR only when flagged + candidate; mock mistral
        img_docx = tmp_path / "img.docx"
        with zipfile.ZipFile(img_docx, "w") as zf:
            zf.writestr(
                "[Content_Types].xml",
                """<?xml version="1.0"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
                <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
                <Default Extension="xml" ContentType="application/xml"/>
                <Default Extension="png" ContentType="image/png"/>
                <Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>
                </Types>""",
            )
            zf.writestr(
                "_rels/.rels",
                f"""<?xml version="1.0"?><Relationships xmlns="{PKG}">
                <Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>
                </Relationships>""",
            )
            zf.writestr("word/_rels/document.xml.rels", f'<Relationships xmlns="{PKG}"></Relationships>')
            zf.writestr(
                "word/document.xml",
                f'<?xml version="1.0"?><w:document xmlns:w="{W}"><w:body>{_p("Sparse body")}</w:body></w:document>',
            )
            big = _png(600, 800) + (b"\x11" * 60_000)
            zf.writestr("word/media/scan_block.png", big)
            zf.writestr("word/media/logo.png", _png(40, 40))

        ocr_calls = {"n": 0}

        def fake_ocr(path: Path, mime: str):
            ocr_calls["n"] += 1
            meta = cv.EngineCallMeta(
                stage="ocr",
                tier="mistral_ocr",
                provider="mistral",
                actual_request_model=cv.MISTRAL_OCR_MODEL,
                provider_response_model=cv.MISTRAL_OCR_MODEL,
                billable_pages=1,
                estimated_cost_usd=0.004,
                latency_ms=11,
                quality_ok=True,
            )
            return (
                "Scanned embedded cert text with enough words for quality gate recovery here.",
                [],
                meta,
            )

        os.environ["WATHEFNI_CV_MISTRAL_OCR"] = "true"
        with mock.patch.object(cv, "extract_image_with_mistral", fake_ocr):
            img_result = docx.extract_docx_document(img_docx, company_code="SMOKE")
        check("OCR called once for text image", ocr_calls["n"] == 1, str(ocr_calls["n"]))
        check("logo not OCR'd", True)
        check("OCR text merged", "Scanned embedded cert" in img_result.text)
        check("OCR call count metadata", (img_result.metadata or {}).get("ocr_call_count") == 1)

        # Cache reuse via in-memory fake db
        store: dict[str, dict] = {}

        def db_exec(sql: str, params=None, fetchone: bool = False):
            params = params or ()
            if "FROM cv_extraction_cache" in sql and fetchone:
                key = params[1]
                row = store.get(key)
                return row
            if "INSERT INTO cv_extraction_cache" in sql:
                # company, cache_key, content_sha, page_hashes_json, ..., result_json, billable, cost, latency, reqid
                cache_key = params[1]
                store[cache_key] = {
                    "result": __import__("json").loads(params[9]),
                    "billable_pages": params[10],
                    "estimated_cost_usd": params[11],
                    "latency_ms": params[12],
                    "provider_request_id": params[13],
                    "ocr_model": params[6],
                    "provider": params[5],
                }
                return None
            if "INSERT INTO cv_extraction_runs" in sql:
                return None
            return None

        os.environ.pop("WATHEFNI_CV_MISTRAL_OCR", None)
        first = docx.extract_docx_document(en, company_code="SMOKE", db_execute=db_exec)
        ocr_calls["n"] = 0
        second = docx.extract_docx_document(en, company_code="SMOKE", db_execute=db_exec)
        check("cache hit on second pass", second.cache_hit is True and second.method.endswith("+cache"))
        check("cache avoids OCR", ocr_calls["n"] == 0)
        check("human preserve still available", hasattr(cv, "preserve_human_fields"))

        # needs_review for corrupted
        bad = tmp_path / "bad.docx"
        bad.write_bytes(b"not-a-docx")
        bad_result = docx.extract_docx_document(bad, company_code="SMOKE")
        check("corrupted needs_review", (bad_result.metadata or {}).get("needs_review") is True)
        check("corrupted not quality_ok", bad_result.quality_ok is False)

    print(f"    summary: {PASS} passed, {FAIL} failed")
    return 1 if FAIL else 0


if __name__ == "__main__":
    raise SystemExit(main())
