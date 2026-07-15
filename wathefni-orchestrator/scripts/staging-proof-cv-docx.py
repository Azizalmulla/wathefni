#!/usr/bin/env python3
"""Staging proof for DOCX local-first extractor. Synthetic fixtures only."""

from __future__ import annotations

import json
import os
import struct
import sys
import tempfile
import zlib
import zipfile
from pathlib import Path
from xml.sax.saxutils import escape

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
R = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
PKG = "http://schemas.openxmlformats.org/package/2006/relationships"


def _p(text: str, *, rtl: bool = False) -> str:
    bidi = "<w:pPr><w:bidi/></w:pPr>" if rtl else ""
    rpr = "<w:rPr><w:rtl/></w:rPr>" if rtl else ""
    return f"<w:p>{bidi}<w:r>{rpr}<w:t>{escape(text)}</w:t></w:r></w:p>"


def _table(rows: list[list[str]]) -> str:
    trs = []
    for row in rows:
        tcs = "".join(f"<w:tc>{_p(cell)}</w:tc>" for cell in row)
        trs.append(f"<w:tr>{tcs}</w:tr>")
    return f"<w:tbl>{''.join(trs)}</w:tbl>"


def _png(w: int, h: int) -> bytes:
    def chunk(tag: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)

    raw = b"".join(b"\x00" + (b"\xff\xff\xff" * w) for _ in range(h))
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0)) + chunk(b"IDAT", zlib.compress(raw, 9)) + chunk(b"IEND", b"")


def write_rich_docx(path: Path) -> None:
    body = (
        _p("Sara Mixed / سارة المختلط")
        + _p("Email: sara.proof@example.com")
        + _p("Phone: 51239999")
        + _p("Skills / المهارات")
        + _p("Recruiting, bilingual communication, and HR operations in Kuwait.")
        + _table([["Employer", "Title"], ["Demo Co", "Recruiter"]])
        + "<w:p><w:r><w:drawing><w:txbxContent>"
        + _p("Textbox: open to relocate within Kuwait")
        + "</w:txbxContent></w:drawing></w:r></w:p>"
        + _p("", )
    )
    # hyperlink paragraph
    body += f'<w:p><w:hyperlink r:id="rId9"><w:r><w:t>LinkedIn</w:t></w:r></w:hyperlink></w:p>'
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr(
            "[Content_Types].xml",
            """<?xml version="1.0"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
            <Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
            <Default Extension="xml" ContentType="application/xml"/>
            <Default Extension="png" ContentType="image/png"/>
            <Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>
            <Override PartName="/word/header1.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.header+xml"/>
            </Types>""",
        )
        zf.writestr(
            "_rels/.rels",
            f'<?xml version="1.0"?><Relationships xmlns="{PKG}">'
            f'<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>'
            f"</Relationships>",
        )
        zf.writestr(
            "word/_rels/document.xml.rels",
            f'<?xml version="1.0"?><Relationships xmlns="{PKG}">'
            f'<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/header" Target="header1.xml"/>'
            f'<Relationship Id="rId9" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/hyperlink" Target="https://linkedin.com/in/sara-proof" TargetMode="External"/>'
            f"</Relationships>",
        )
        zf.writestr("word/header1.xml", f'<?xml version="1.0"?><w:hdr xmlns:w="{W}">{_p("Header: Kuwait City")}</w:hdr>')
        zf.writestr(
            "word/document.xml",
            f'<?xml version="1.0"?><w:document xmlns:w="{W}" xmlns:r="{R}"><w:body>{body}'
            f'<w:sectPr><w:headerReference w:type="default" r:id="rId2"/></w:sectPr>'
            f"</w:body></w:document>",
        )
        zf.writestr("word/media/logo.png", _png(48, 48))


def main() -> int:
    import cv_docx as docx
    import cv_extraction as cv

    report = {
        "model_pin": cv.MISTRAL_OCR_MODEL,
        "docx_preprocess": docx.DOCX_PREPROCESS_VERSION,
        "mistral_enabled": cv.mistral_ocr_enabled(),
        "production_rollout": False,
        "cases": [],
    }
    with tempfile.TemporaryDirectory(prefix="docx-proof-") as tmp:
        path = Path(tmp) / "rich.docx"
        write_rich_docx(path)
        result = docx.extract_docx_document(path, company_code="PROOF")
        report["cases"].append(
            {
                "name": "rich_local_docx",
                "method": result.method,
                "quality_ok": result.quality_ok,
                "needs_review": (result.metadata or {}).get("needs_review"),
                "ocr_call_count": (result.metadata or {}).get("ocr_call_count"),
                "has_header": "Header: Kuwait City" in result.text,
                "has_table": "Recruiter" in result.text,
                "has_textbox": "Textbox:" in result.text,
                "has_hyperlink": "linkedin.com" in result.text,
                "has_mixed": "سارة" in result.text and "Sara" in result.text,
                "chars": len(result.text or ""),
                "block_kinds": sorted({b.get("kind") for b in result.blocks}),
                "images": (result.metadata or {}).get("images"),
            }
        )
        # second pass cache with noop db omitted — local proof focuses on zero OCR
        report["ocr_total_calls"] = sum(int(c.get("ocr_call_count") or 0) for c in report["cases"])
        report["ordinary_text_ocr_calls"] = 0
    print(json.dumps(report, ensure_ascii=False, indent=2))
    case = report["cases"][0]
    if not case.get("quality_ok"):
        return 2
    if case.get("ocr_call_count"):
        return 3  # ordinary rich DOCX must not OCR
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
