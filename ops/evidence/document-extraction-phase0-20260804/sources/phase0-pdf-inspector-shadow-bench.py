#!/usr/bin/env python3
"""Document Extraction Phase 0 — generate synthetic PDF matrix + shadow-benchmark
pdf-inspector vs Poppler assess_pdf_pages.

NO Mistral / paid OCR calls. Poppler remains authoritative; pdf-inspector is shadow only.
"""

from __future__ import annotations

import json
import re
import struct
import subprocess
import sys
import time
import zlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

MATRIX = Path("/tmp/pdf-inspector-phase0/matrix")
RESULTS = Path("/tmp/pdf-inspector-phase0/results")
MATRIX.mkdir(parents=True, exist_ok=True)
RESULTS.mkdir(parents=True, exist_ok=True)


def _pdf_escape(s: str) -> str:
    return s.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def write_simple_text_pdf(path: Path, lines: list[str], *, font: str = "Helvetica", size: int = 11) -> None:
    """Minimal single-page text PDF (Latin Helvetica)."""
    y = 750
    content_parts = ["BT", f"/{font} {size} Tf", "50 750 Td"]
    first = True
    for line in lines:
        safe = _pdf_escape(line[:110])
        if first:
            content_parts.append(f"({safe}) Tj")
            first = False
        else:
            content_parts.append(f"0 -16 Td ({safe}) Tj")
        y -= 16
    content_parts.append("ET")
    stream = "\n".join(content_parts).encode("latin-1", errors="replace")
    objects: list[bytes] = []
    objects.append(b"1 0 obj<< /Type /Catalog /Pages 2 0 R >>endobj\n")
    objects.append(b"2 0 obj<< /Type /Pages /Kids [3 0 R] /Count 1 >>endobj\n")
    objects.append(
        b"3 0 obj<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
        b"/Contents 4 0 R /Resources << /Font << /Helvetica 5 0 R /Helvetica-Bold 6 0 R >> >> >>endobj\n"
    )
    objects.append(f"4 0 obj<< /Length {len(stream)} >>stream\n".encode() + stream + b"\nendstream\nendobj\n")
    objects.append(b"5 0 obj<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>endobj\n")
    objects.append(b"6 0 obj<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold >>endobj\n")
    out = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for obj in objects:
        offsets.append(len(out))
        out.extend(obj)
    xref = len(out)
    out.extend(f"xref\n0 {len(objects)+1}\n".encode())
    out.extend(b"0000000000 65535 f \n")
    for off in offsets[1:]:
        out.extend(f"{off:010d} 00000 n \n".encode())
    out.extend(
        f"trailer<< /Size {len(objects)+1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode()
    )
    path.write_bytes(bytes(out))


def write_multicolumn_pdf(path: Path) -> None:
    stream = b"""BT
/Helvetica 12 Tf
50 740 Td (COLUMN LEFT - Senior Engineer CV) Tj
0 -16 Td (Experience: Platform systems, queues, OCR routing.) Tj
0 -16 Td (Skills: Python, Postgres, Arabic/English docs.) Tj
ET
BT
/Helvetica 12 Tf
320 740 Td (COLUMN RIGHT - Education) Tj
0 -16 Td (BSc Computer Science - Kuwait University) Tj
0 -16 Td (Certifications: PMP, AWS) Tj
ET
"""
    objects: list[bytes] = []
    objects.append(b"1 0 obj<< /Type /Catalog /Pages 2 0 R >>endobj\n")
    objects.append(b"2 0 obj<< /Type /Pages /Kids [3 0 R] /Count 1 >>endobj\n")
    objects.append(
        b"3 0 obj<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
        b"/Contents 4 0 R /Resources << /Font << /Helvetica 5 0 R >> >> >>endobj\n"
    )
    objects.append(f"4 0 obj<< /Length {len(stream)} >>stream\n".encode() + stream + b"\nendstream\nendobj\n")
    objects.append(b"5 0 obj<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>endobj\n")
    out = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for obj in objects:
        offsets.append(len(out))
        out.extend(obj)
    xref = len(out)
    out.extend(f"xref\n0 {len(objects)+1}\n".encode())
    out.extend(b"0000000000 65535 f \n")
    for off in offsets[1:]:
        out.extend(f"{off:010d} 00000 n \n".encode())
    out.extend(f"trailer<< /Size {len(objects)+1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode())
    path.write_bytes(bytes(out))


def _png_rgb(width: int, height: int, rgb: tuple[int, int, int] = (245, 245, 245)) -> bytes:
    """Untouched solid PNG (no text) — used as scanned/image-only page stand-in."""
    r, g, b = rgb
    raw = b"".join(b"\x00" + bytes([r, g, b]) * width for _ in range(height))
    compressed = zlib.compress(raw, 9)

    def chunk(tag: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)

    ihdr = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr) + chunk(b"IDAT", compressed) + chunk(b"IEND", b"")


def write_image_only_pdf(path: Path, *, pages: int = 1) -> None:
    """Image-only PDF pages (no text operators) — synthetic scanned stand-in."""
    png = _png_rgb(200, 280)
    # Build one image XObject shared; N pages referencing it without text.
    objs: list[bytes] = []
    # We'll assemble carefully with correct object numbers.
    # 1 catalog, 2 pages, 3..2+N pages, then content streams, then image, then length handled inline
    page_objs = []
    content_objs = []
    img_obj_num = 3 + pages * 2
    for i in range(pages):
        page_num = 3 + i
        content_num = 3 + pages + i
        page_objs.append(
            f"{page_num} 0 obj<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
            f"/Contents {content_num} 0 R /Resources << /XObject << /Im0 {img_obj_num} 0 R >> >> >>endobj\n".encode()
        )
        cstream = b"q 500 0 0 700 50 50 cm /Im0 Do Q"
        content_objs.append(
            f"{content_num} 0 obj<< /Length {len(cstream)} >>stream\n".encode() + cstream + b"\nendstream\nendobj\n"
        )
    kids = " ".join(f"{3+i} 0 R" for i in range(pages))
    objects = [
        b"1 0 obj<< /Type /Catalog /Pages 2 0 R >>endobj\n",
        f"2 0 obj<< /Type /Pages /Kids [{kids}] /Count {pages} >>endobj\n".encode(),
        *page_objs,
        *content_objs,
        (
            f"{img_obj_num} 0 obj<< /Type /XObject /Subtype /Image /Width 200 /Height 280 "
            f"/ColorSpace /DeviceRGB /BitsPerComponent 8 /Filter /FlateDecode /Length {len(png)} >>stream\n".encode()
            # NOTE: embedding raw PNG bytes as FlateDecode image data is not valid JPEG/raw RGB;
            # Poppler may fail to render but still treat as image-bearing page without text — good enough for routing shadow.
            + png
            + b"\nendstream\nendobj\n"
        ),
    ]
    # Better: use uncompressed raw RGB image so pdfinfo/pdfimages see an image
    raw_rgb = bytes([240, 240, 240]) * (120 * 160)
    compressed = zlib.compress(raw_rgb, 9)
    objects[-1] = (
        f"{img_obj_num} 0 obj<< /Type /XObject /Subtype /Image /Width 120 /Height 160 "
        f"/ColorSpace /DeviceRGB /BitsPerComponent 8 /Filter /FlateDecode /Length {len(compressed)} >>stream\n".encode()
        + compressed
        + b"\nendstream\nendobj\n"
    )
    out = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for obj in objects:
        offsets.append(len(out))
        out.extend(obj)
    xref = len(out)
    out.extend(f"xref\n0 {len(objects)+1}\n".encode())
    out.extend(b"0000000000 65535 f \n")
    for off in offsets[1:]:
        out.extend(f"{off:010d} 00000 n \n".encode())
    out.extend(f"trailer<< /Size {len(objects)+1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode())
    path.write_bytes(bytes(out))


def write_mixed_pdf(path: Path) -> None:
    """Page1 digital text + page2 image-only."""
    # Two-page: reuse text page content + image page via concatenating approach — write manually.
    png_raw = zlib.compress(bytes([200, 200, 200]) * (100 * 100), 9)
    content1 = b"BT /Helvetica 12 Tf 50 720 Td (DIGITAL PAGE - readable CV text for hybrid test.) Tj 0 -16 Td (Skills: Python Postgres OCR routing.) Tj ET"
    content2 = b"q 400 0 0 400 100 200 cm /Im0 Do Q"
    parts = []
    parts.append(b"1 0 obj<< /Type /Catalog /Pages 2 0 R >>endobj\n")
    parts.append(b"2 0 obj<< /Type /Pages /Kids [3 0 R 4 0 R] /Count 2 >>endobj\n")
    parts.append(
        b"3 0 obj<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 5 0 R "
        b"/Resources << /Font << /Helvetica 7 0 R >> >> >>endobj\n"
    )
    parts.append(
        b"4 0 obj<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 6 0 R "
        b"/Resources << /XObject << /Im0 8 0 R >> >> >>endobj\n"
    )
    parts.append(f"5 0 obj<< /Length {len(content1)} >>stream\n".encode() + content1 + b"\nendstream\nendobj\n")
    parts.append(f"6 0 obj<< /Length {len(content2)} >>stream\n".encode() + content2 + b"\nendstream\nendobj\n")
    parts.append(b"7 0 obj<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>endobj\n")
    parts.append(
        f"8 0 obj<< /Type /XObject /Subtype /Image /Width 100 /Height 100 /ColorSpace /DeviceRGB "
        f"/BitsPerComponent 8 /Filter /FlateDecode /Length {len(png_raw)} >>stream\n".encode()
        + png_raw
        + b"\nendstream\nendobj\n"
    )
    out = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for obj in parts:
        offsets.append(len(out))
        out.extend(obj)
    xref = len(out)
    out.extend(f"xref\n0 {len(parts)+1}\n".encode())
    out.extend(b"0000000000 65535 f \n")
    for off in offsets[1:]:
        out.extend(f"{off:010d} 00000 n \n".encode())
    out.extend(f"trailer<< /Size {len(parts)+1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode())
    path.write_bytes(bytes(out))


def write_broken_encoding_pdf(path: Path) -> None:
    """Text operators with high-bit / mojibake-like content to stress encoding gates."""
    # Intentionally weird string bytes inside Tj
    weird = bytes([0xC0 + (i % 32) for i in range(80)])
    # Keep as octal-ish PDF string using escaped bytes via literal latin-1 replacement in content
    safe = "".join(f"\\{b:03o}" for b in weird)
    stream = f"BT /Helvetica 12 Tf 50 720 Td ({safe}) Tj ET".encode("latin-1")
    objects = [
        b"1 0 obj<< /Type /Catalog /Pages 2 0 R >>endobj\n",
        b"2 0 obj<< /Type /Pages /Kids [3 0 R] /Count 1 >>endobj\n",
        b"3 0 obj<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R "
        b"/Resources << /Font << /Helvetica 5 0 R >> >> >>endobj\n",
        f"4 0 obj<< /Length {len(stream)} >>stream\n".encode() + stream + b"\nendstream\nendobj\n",
        b"5 0 obj<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>endobj\n",
    ]
    out = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for obj in objects:
        offsets.append(len(out))
        out.extend(obj)
    xref = len(out)
    out.extend(f"xref\n0 {len(objects)+1}\n".encode())
    out.extend(b"0000000000 65535 f \n")
    for off in offsets[1:]:
        out.extend(f"{off:010d} 00000 n \n".encode())
    out.extend(f"trailer<< /Size {len(objects)+1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode())
    path.write_bytes(bytes(out))


def build_matrix() -> list[dict]:
    fixtures = []

    p = MATRIX / "cv_en_digital.pdf"
    write_simple_text_pdf(
        p,
        [
            "ENGLISH CV - Jane Doe",
            "Email: jane.doe@example.com  Phone: +96550000001",
            "Experience: 8 years platform engineering, durable queues, OCR pipelines.",
            "Skills: Python, PostgreSQL, FastAPI, Arabic/English documentation.",
            "Education: BSc Computer Science",
        ],
    )
    fixtures.append({"id": "cv_en_digital", "category": "english_cv_digital", "path": p, "expect_ocr_pages": 0})

    p = MATRIX / "cv_ar_digital_translit.pdf"
    # Helvetica cannot embed Arabic glyphs; use transliteration + Arabic Unicode in comments path separately.
    # True Arabic glyph PDFs need embedded fonts; we also add a UTF-8 sidecar expectation note.
    write_simple_text_pdf(
        p,
        [
            "CV ARABIC (transliteration stand-in) - Ahmad Al-Sabah",
            "Email: ahmad@example.com  Phone: +96550000002",
            "Khebra: 6 sanawat fi majal al-nizam wa al-wathaeq.",
            "Maharat: Python, Postgres, Wathefni HR OS.",
            "NOTE: true Arabic glyph PDF requires embedded font; see cv_ar_real if available.",
        ],
    )
    fixtures.append({"id": "cv_ar_digital_translit", "category": "arabic_cv_proxy", "path": p, "expect_ocr_pages": 0})

    p = MATRIX / "cv_bilingual_digital.pdf"
    write_simple_text_pdf(
        p,
        [
            "BILINGUAL CV / سيرة ذاتية (latin+note)",
            "Name: Sara Al-Mutawa / سارة المطوع",
            "Email: sara@example.com",
            "Experience EN: Recruitment operations Kuwait/GCC.",
            "Experience AR note: khibrat fi al-tawzeef wa al-imithal.",
            "Languages: Arabic (native), English (fluent)",
        ],
    )
    fixtures.append({"id": "cv_bilingual_digital", "category": "bilingual_cv", "path": p, "expect_ocr_pages": 0})

    p = MATRIX / "cv_multicolumn_digital.pdf"
    write_multicolumn_pdf(p)
    fixtures.append({"id": "cv_multicolumn_digital", "category": "multicolumn_cv", "path": p, "expect_ocr_pages": 0})

    p = MATRIX / "cv_scanned_image_only.pdf"
    write_image_only_pdf(p, pages=1)
    fixtures.append({"id": "cv_scanned_image_only", "category": "scanned_pdf", "path": p, "expect_ocr_pages": 1})

    p = MATRIX / "cv_mixed_digital_plus_scan.pdf"
    write_mixed_pdf(p)
    fixtures.append({"id": "cv_mixed_digital_plus_scan", "category": "mixed_pdf", "path": p, "expect_ocr_pages": 1})

    p = MATRIX / "cv_broken_encoding.pdf"
    write_broken_encoding_pdf(p)
    fixtures.append({"id": "cv_broken_encoding", "category": "cid_broken_encoding", "path": p, "expect_ocr_pages": "maybe"})

    p = MATRIX / "contract_table_heavy.pdf"
    write_simple_text_pdf(
        p,
        [
            "EMPLOYMENT CONTRACT - TABLE HEAVY",
            "Clause | EN | AR",
            "1 Salary | KWD 800 | ratib",
            "2 Leave | 30 days | ijaza",
            "3 Probation | 100 days | tajriba",
            "4 Notice | 30 days | ishaar",
            "Signatures: Employer ________________  Employee ________________",
        ],
        font="Helvetica",
    )
    fixtures.append({"id": "contract_table_heavy", "category": "contracts_tables", "path": p, "expect_ocr_pages": 0})

    p = MATRIX / "identity_civil_id_proxy.pdf"
    write_simple_text_pdf(
        p,
        [
            "CIVIL ID / IDENTITY DOCUMENT PROXY (synthetic)",
            "Civil ID No: 289123456789",
            "Name: PROXY PERSON",
            "Nationality: KWT",
            "Expiry: 2028-12-31",
            "This is a synthetic digital identity stand-in for routing tests only.",
        ],
    )
    fixtures.append({"id": "identity_civil_id_proxy", "category": "identity_document", "path": p, "expect_ocr_pages": 0})

    # Real offer PDFs from repo if present (contracts)
    offer_en = ROOT / "staging-evidence/offer-1/owner-review/offer-en.pdf"
    offer_ar = ROOT / "staging-evidence/offer-1/owner-review/offer-ar.pdf"
    if offer_en.exists():
        dest = MATRIX / "contract_offer_en_real.pdf"
        dest.write_bytes(offer_en.read_bytes())
        fixtures.append({"id": "contract_offer_en_real", "category": "contracts_real", "path": dest, "expect_ocr_pages": "unknown"})
    if offer_ar.exists():
        dest = MATRIX / "contract_offer_ar_real.pdf"
        dest.write_bytes(offer_ar.read_bytes())
        fixtures.append({"id": "contract_offer_ar_real", "category": "contracts_real_arabic", "path": dest, "expect_ocr_pages": "unknown"})

    return fixtures


def poppler_shadow(path: Path) -> dict:
    import cv_extraction as cv

    t0 = time.perf_counter()
    assessments = cv.assess_pdf_pages(path)
    ms = (time.perf_counter() - t0) * 1000
    needs = [a.page_number for a in assessments if a.disposition == "needs_ocr"]
    local_pages = [a.page_number for a in assessments if a.disposition == "accepted_local"]
    texts = [a.local_text for a in assessments if a.local_text]
    merged = "\n".join(texts)
    return {
        "engine": "poppler_assess_pdf_pages",
        "ms": round(ms, 2),
        "page_count": len(assessments),
        "pages_needing_ocr": needs,
        "pages_local": local_pages,
        "dispositions": [{"page": a.page_number, "disposition": a.disposition, "reason": a.reason} for a in assessments],
        "text_chars": len(merged),
        "text_words": len(re.findall(r"\S+", merged)),
        "arabic_ratio": round(cv.arabic_ratio(merged), 4) if merged else 0.0,
        "quality_ok": cv.cv_text_quality_ok(merged) if merged else False,
        "text_preview": merged[:240],
    }


def inspector_shadow(path: Path) -> dict:
    import pdf_inspector

    t0 = time.perf_counter()
    # detect first (routing signal)
    det = pdf_inspector.detect_pdf(str(path))
    detect_ms = (time.perf_counter() - t0) * 1000
    t1 = time.perf_counter()
    full = pdf_inspector.process_pdf(str(path))
    process_ms = (time.perf_counter() - t1) * 1000
    md = getattr(full, "markdown", None) or ""
    pages_ocr = list(getattr(det, "pages_needing_ocr", None) or getattr(full, "pages_needing_ocr", None) or [])
    return {
        "engine": "pdf_inspector",
        "detect_ms": round(detect_ms, 2),
        "process_ms": round(process_ms, 2),
        "pdf_type": getattr(det, "pdf_type", None) or getattr(full, "pdf_type", None),
        "confidence": getattr(det, "confidence", None) or getattr(full, "confidence", None),
        "page_count": getattr(det, "page_count", None) or getattr(full, "page_count", None),
        "pages_needing_ocr": pages_ocr,
        "is_complex_layout": getattr(full, "is_complex_layout", None),
        "pages_with_tables": list(getattr(full, "pages_with_tables", None) or []),
        "pages_with_columns": list(getattr(full, "pages_with_columns", None) or []),
        "has_encoding_issues": getattr(full, "has_encoding_issues", None),
        "markdown_chars": len(md),
        "markdown_words": len(re.findall(r"\S+", md)),
        "markdown_preview": md[:240],
    }


def compare_row(fx: dict, pop: dict, insp: dict) -> dict:
    pop_ocr = set(pop.get("pages_needing_ocr") or [])
    insp_ocr = set(insp.get("pages_needing_ocr") or [])
    # Normalize inspector pages to ints
    insp_ocr = {int(x) for x in insp_ocr}
    agree = pop_ocr == insp_ocr
    false_skip = bool(pop_ocr - insp_ocr)  # poppler says OCR needed, inspector doesn't
    extra_ocr = bool(insp_ocr - pop_ocr)  # inspector would OCR more
    # Projected cost if we trusted each router ($0.004/page)
    cost_pop = round(len(pop_ocr) * 0.004, 6)
    cost_insp = round(len(insp_ocr) * 0.004, 6)
    return {
        "id": fx["id"],
        "category": fx["category"],
        "path": str(fx["path"]),
        "expect_ocr_pages": fx.get("expect_ocr_pages"),
        "agreement_on_ocr_pages": agree,
        "false_ocr_skip_vs_poppler": false_skip,
        "extra_ocr_vs_poppler": extra_ocr,
        "poppler_ocr_pages": sorted(pop_ocr),
        "inspector_ocr_pages": sorted(insp_ocr),
        "projected_cost_if_poppler_usd": cost_pop,
        "projected_cost_if_inspector_usd": cost_insp,
        "projected_savings_vs_poppler_usd": round(cost_pop - cost_insp, 6),
        "poppler": pop,
        "inspector": insp,
        "shadow_only": True,
        "authoritative_router": "poppler",
        "paid_ocr_called": False,
    }


def main() -> None:
    print("PHASE0_SHADOW_BENCH_START")
    fixtures = build_matrix()
    rows = []
    for fx in fixtures:
        path = Path(fx["path"])
        assert path.exists(), path
        pop = poppler_shadow(path)
        try:
            insp = inspector_shadow(path)
        except Exception as exc:
            insp = {"engine": "pdf_inspector", "error": str(exc)[:300]}
        row = compare_row(fx, pop, insp if "error" not in insp else {**insp, "pages_needing_ocr": []})
        if "error" in insp:
            row["inspector_error"] = insp["error"]
        rows.append(row)
        print(json.dumps({"id": row["id"], "agree": row["agreement_on_ocr_pages"], "pop": row["poppler_ocr_pages"], "insp": row["inspector_ocr_pages"], "type": insp.get("pdf_type")}, ensure_ascii=False))

    agreements = sum(1 for r in rows if r["agreement_on_ocr_pages"])
    false_skips = sum(1 for r in rows if r["false_ocr_skip_vs_poppler"])
    extra = sum(1 for r in rows if r["extra_ocr_vs_poppler"])
    summary = {
        "matrix_size": len(rows),
        "agreement_count": agreements,
        "agreement_rate": round(agreements / max(1, len(rows)), 3),
        "false_ocr_skips_vs_poppler": false_skips,
        "extra_ocr_vs_poppler": extra,
        "total_projected_poppler_ocr_pages": sum(len(r["poppler_ocr_pages"]) for r in rows),
        "total_projected_inspector_ocr_pages": sum(len(r["inspector_ocr_pages"]) for r in rows),
        "projected_cost_poppler_usd": round(sum(r["projected_cost_if_poppler_usd"] for r in rows), 6),
        "projected_cost_inspector_usd": round(sum(r["projected_cost_if_inspector_usd"] for r in rows), 6),
        "paid_ocr_called": False,
        "authoritative_router": "poppler",
        "limitations": [
            "Synthetic matrix; Helvetica cannot embed true Arabic glyphs — arabic_cv uses transliteration proxy",
            "Image-only pages are synthetic RGB XObjects, not camera scans",
            "No Mistral calls; cost figures are projected from page counts only",
            "Downstream field-extraction accuracy not measured (would require OCR/LLM)",
        ],
    }
    out = {"summary": summary, "rows": rows}
    (RESULTS / "shadow_benchmark.json").write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(summary, indent=2))
    print("PHASE0_SHADOW_BENCH_PASS")
    print(f"RESULTS={RESULTS / 'shadow_benchmark.json'}")


if __name__ == "__main__":
    main()
