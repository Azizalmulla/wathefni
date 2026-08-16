#!/usr/bin/env python3
"""pdf-inspector Deep Evaluation Wave 0 — staging/local shadow-only.

Real structurally valid PDF fixtures only (no .txt CVs, no trivial placeholders).
Poppler remains authoritative. pdf-inspector is shadow signal only.
No production routing changes. No paid OCR / Mistral calls.
"""

from __future__ import annotations

import hashlib
import json
import re
import shutil
import sys
import time
import zlib
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from importlib.metadata import metadata, version
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageFont
from pypdf import PdfReader, PdfWriter
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
    Frame,
    PageTemplate,
    BaseDocTemplate,
    FrameBreak,
    NextPageTemplate,
)
from reportlab.platypus.doctemplate import PageTemplate as RLPageTemplate
from reportlab.pdfgen import canvas

import arabic_reshaper
from bidi.algorithm import get_display

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

EVID = Path("/Users/azizalmulla/Desktop/claw/ops/evidence/pdf-inspector-deep-eval-wave0-20260804")
FIXTURES = EVID / "fixtures"
EXPECTED = EVID / "expected"
RESULTS = EVID / "results"
ARTIFACTS = EVID / "artifacts"
for d in (FIXTURES, EXPECTED, RESULTS, ARTIFACTS):
    d.mkdir(parents=True, exist_ok=True)

AR_FONT = "/Users/azizalmulla/Library/Fonts/NotoKufiArabic-Regular.ttf"
AR_FONT_BOLD = "/Users/azizalmulla/Library/Fonts/NotoKufiArabic-Bold.ttf"
EN_FONT = "/System/Library/Fonts/Supplemental/Arial Unicode.ttf"
LAW_PDF = Path(
    "/Users/azizalmulla/Desktop/claw/ops/evidence/leave-wave2b-policy-closure-20260802T160608Z"
    "/sources/official/moj-law-6-2010-kuwait-labor.pdf"
)

COST_USD_PER_PAGE = 0.004

pdfmetrics.registerFont(TTFont("NotoKufi", AR_FONT))
pdfmetrics.registerFont(TTFont("NotoKufiBold", AR_FONT_BOLD))
pdfmetrics.registerFont(TTFont("ArialUni", EN_FONT))


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def ar(text: str) -> str:
    """Shape Arabic for ReportLab LTR canvas drawing."""
    return get_display(arabic_reshaper.reshape(text))


def write_expected(fixture_id: str, payload: dict[str, Any]) -> None:
    (EXPECTED / f"{fixture_id}.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def draw_en_lines(c: canvas.Canvas, lines: list[str], *, x: float = 50, y: float = 760, size: int = 11) -> None:
    c.setFont("ArialUni", size)
    yy = y
    for line in lines:
        c.drawString(x, yy, line)
        yy -= size + 5


def draw_ar_lines(c: canvas.Canvas, lines: list[str], *, x_right: float = 560, y: float = 760, size: int = 12) -> None:
    c.setFont("NotoKufi", size)
    yy = y
    for line in lines:
        c.drawRightString(x_right, yy, ar(line))
        yy -= size + 8


def pdf_page_image_text(
    path: Path,
    lines: list[str],
    *,
    arabic: bool = False,
    pagesize=letter,
) -> None:
    """Render visible text to PNG, then embed as an image-only PDF page (no text operators)."""
    w, h = (int(pagesize[0]), int(pagesize[1]))
    scale = 2
    img = Image.new("RGB", (w * scale, h * scale), (248, 248, 245))
    draw = ImageDraw.Draw(img)
    font_path = AR_FONT if arabic else EN_FONT
    try:
        font = ImageFont.truetype(font_path, 28 if arabic else 26)
        font_title = ImageFont.truetype(AR_FONT_BOLD if arabic else font_path, 36 if arabic else 32)
    except Exception:
        font = ImageFont.load_default()
        font_title = font
    y = 80
    for i, line in enumerate(lines):
        text = ar(line) if arabic else line
        f = font_title if i == 0 else font
        if arabic:
            bbox = draw.textbbox((0, 0), text, font=f)
            tw = bbox[2] - bbox[0]
            draw.text(((w * scale) - 80 - tw, y), text, fill=(20, 20, 20), font=f)
        else:
            draw.text((80, y), text, fill=(20, 20, 20), font=f)
        y += 48 if i == 0 else 40
    png_path = ARTIFACTS / f"{path.stem}-render.png"
    img.save(png_path)
    # Embed raw RGB via ReportLab image, then strip text by rewriting as image XObject-only via canvas image.
    # Using canvas.drawImage still creates no extractable text for the words themselves if we only draw the bitmap.
    c = canvas.Canvas(str(path), pagesize=pagesize)
    c.drawImage(str(png_path), 0, 0, width=w, height=h)
    c.showPage()
    c.save()


def build_fixture_manifest() -> list[dict[str, Any]]:
    """Create 24 structurally valid PDFs and expected truth files."""
    fixtures: list[dict[str, Any]] = []

    def add(
        fid: str,
        category: str,
        path: Path,
        *,
        language: str,
        layout: str,
        pdf_nature: str,
        pages: int,
        expected_ocr_pages_1idx: list[int],
        expected_text_needles: list[str],
        expected_fields: dict[str, Any],
        notes: str,
    ) -> None:
        assert path.exists() and path.suffix.lower() == ".pdf", path
        assert path.stat().st_size > 500, f"trivial/empty pdf rejected: {path}"
        write_expected(
            fid,
            {
                "fixture_id": fid,
                "category": category,
                "language": language,
                "layout": layout,
                "pdf_nature": pdf_nature,
                "pages": pages,
                "expected_ocr_pages_1idx": expected_ocr_pages_1idx,
                "expected_text_needles": expected_text_needles,
                "expected_fields": expected_fields,
                "notes": notes,
                "sha256": sha256_file(path),
                "bytes": path.stat().st_size,
            },
        )
        fixtures.append(
            {
                "fixture_id": fid,
                "category": category,
                "path": str(path.relative_to(EVID)),
                "language": language,
                "layout": layout,
                "pdf_nature": pdf_nature,
                "pages": pages,
            }
        )

    # --- 1. English digital CVs (3) ---
    en_cvs = [
        (
            "cv_en_digital_01",
            "Sara Al-Mutairi",
            "sara.almutairi@example.com",
            "+96550110011",
            "Senior Backend Engineer",
            [
                "EXPERIENCE",
                "2021-2026 Wathefni — Platform queues, OCR routing, Postgres.",
                "EDUCATION",
                "BSc Computer Science — Kuwait University",
                "SKILLS",
                "Python, PostgreSQL, Redis, Arabic/English document pipelines",
            ],
        ),
        (
            "cv_en_digital_02",
            "James Carter",
            "james.carter@example.com",
            "+96555223344",
            "HR Operations Analyst",
            [
                "EXPERIENCE",
                "2019-2026 Gulf Staffing — compliance renewals and onboarding.",
                "EDUCATION",
                "BA Business Administration — AUK",
                "SKILLS",
                "Excel, policy drafting, Civil ID tracking",
            ],
        ),
        (
            "cv_en_digital_03",
            "Layla Hassan",
            "layla.hassan@example.com",
            "+96560011223",
            "Data Engineer",
            [
                "EXPERIENCE",
                "2020-2026 Analytics Hub — warehouse pipelines and reporting.",
                "EDUCATION",
                "MSc Data Science — University of Manchester",
                "SKILLS",
                "SQL, dbt, Python, Airflow",
            ],
        ),
    ]
    for fid, name, email, phone, title, body in en_cvs:
        path = FIXTURES / f"{fid}.pdf"
        c = canvas.Canvas(str(path), pagesize=letter)
        draw_en_lines(
            c,
            [name, title, f"Email: {email}", f"Phone: {phone}", ""] + body,
            size=12,
        )
        c.showPage()
        c.save()
        add(
            fid,
            "english_digital_cv",
            path,
            language="en",
            layout="single_column",
            pdf_nature="digital_text",
            pages=1,
            expected_ocr_pages_1idx=[],
            expected_text_needles=[name, email, phone, "EXPERIENCE", "SKILLS"],
            expected_fields={"full_name": name, "email": email, "phone": phone, "title": title},
            notes="Structurally valid digital English CV with embedded TrueType text.",
        )

    # --- 2. Arabic digital CVs (3) ---
    ar_cvs = [
        (
            "cv_ar_digital_01",
            "نورة العتيبي",
            "noura.otaibi@example.com",
            "+96551112233",
            "مهندسة برمجيات",
            [
                "الخبرة العملية",
                "٢٠٢٠-٢٠٢٦ شركة وطني — تطوير أنظمة الموارد البشرية",
                "التعليم",
                "بكالوريوس علوم حاسوب — جامعة الكويت",
                "المهارات",
                "بايثون، قواعد البيانات، معالجة الوثائق",
            ],
        ),
        (
            "cv_ar_digital_02",
            "فهد الشمري",
            "fahad.shamri@example.com",
            "+96557778899",
            "أخصائي امتثال",
            [
                "الخبرة العملية",
                "٢٠١٨-٢٠٢٦ إدارة الالتزام — متابعة الإقامات وتصاريح العمل",
                "التعليم",
                "ليسانس قانون — جامعة الكويت",
                "المهارات",
                "الامتثال، التدقيق، إدارة الوثائق",
            ],
        ),
        (
            "cv_ar_digital_03",
            "مريم الصباح",
            "mariam.sabah@example.com",
            "+96553334455",
            "محللة موارد بشرية",
            [
                "الخبرة العملية",
                "٢٠٢١-٢٠٢٦ التوظيف والتأهيل — مقابلات وتقييم المرشحين",
                "التعليم",
                "ماجستير إدارة أعمال — الجامعة الأمريكية",
                "المهارات",
                "التوظيف، المقابلات، أنظمة التتبع",
            ],
        ),
    ]
    for fid, name, email, phone, title, body in ar_cvs:
        path = FIXTURES / f"{fid}.pdf"
        c = canvas.Canvas(str(path), pagesize=A4)
        draw_ar_lines(c, [name, title], y=800, size=16)
        c.setFont("ArialUni", 11)
        c.drawRightString(560, 760, f"Email: {email}")
        c.drawRightString(560, 742, f"Phone: {phone}")
        draw_ar_lines(c, body, y=700, size=12)
        c.showPage()
        c.save()
        add(
            fid,
            "arabic_digital_cv",
            path,
            language="ar",
            layout="single_column_rtl",
            pdf_nature="digital_text",
            pages=1,
            expected_ocr_pages_1idx=[],
            expected_text_needles=[name, email, phone, "الخبرة العملية", "المهارات"],
            expected_fields={"full_name": name, "email": email, "phone": phone, "title": title},
            notes="Structurally valid Arabic CV with embedded Noto Kufi TrueType (shaped+bidi).",
        )

    # --- 3. Bilingual CVs (2) ---
    bilingual = [
        (
            "cv_bilingual_01",
            "Abdullah Al-Rashid",
            "عبدالله الراشد",
            "abdullah.rashid@example.com",
            "+96551234567",
            "Product Manager / مدير منتج",
        ),
        (
            "cv_bilingual_02",
            "Hessa Al-Ali",
            "حصة العلي",
            "hessa.ali@example.com",
            "+96559876543",
            "Finance Controller / مراقبة مالية",
        ),
    ]
    for fid, en_name, ar_name, email, phone, title in bilingual:
        path = FIXTURES / f"{fid}.pdf"
        c = canvas.Canvas(str(path), pagesize=A4)
        draw_en_lines(
            c,
            [
                en_name,
                title,
                f"Email: {email}",
                f"Phone: {phone}",
                "EXPERIENCE",
                "2022-2026 Cross-border HR SaaS — roadmap and delivery.",
                "SKILLS",
                "Roadmapping, stakeholder management, bilingual documentation",
            ],
            y=800,
        )
        draw_ar_lines(
            c,
            [
                ar_name,
                "الخبرة العملية",
                "٢٠٢٢-٢٠٢٦ أنظمة الموارد البشرية — إدارة المنتجات",
                "المهارات",
                "التخطيط، التواصل، الوثائق ثنائية اللغة",
            ],
            y=520,
        )
        c.showPage()
        c.save()
        add(
            fid,
            "bilingual_cv",
            path,
            language="ar_en",
            layout="stacked_bilingual",
            pdf_nature="digital_text",
            pages=1,
            expected_ocr_pages_1idx=[],
            expected_text_needles=[en_name, ar_name, email, phone, "EXPERIENCE", "الخبرة العملية"],
            expected_fields={"full_name": en_name, "full_name_ar": ar_name, "email": email, "phone": phone, "title": title},
            notes="English block then Arabic block; both embedded as real text.",
        )

    # --- 4. Multi-column CVs (2) ---
    for i, (fid, name, email, phone) in enumerate(
        [
            ("cv_multicolumn_01", "Omar Nasser", "omar.nasser@example.com", "+96550001122"),
            ("cv_multicolumn_02", "Rita Gomez", "rita.gomez@example.com", "+96550003344"),
        ],
        start=1,
    ):
        path = FIXTURES / f"{fid}.pdf"
        c = canvas.Canvas(str(path), pagesize=letter)
        c.setFont("ArialUni", 14)
        c.drawString(50, 760, name)
        c.setFont("ArialUni", 10)
        c.drawString(50, 742, f"{email} | {phone}")
        c.setStrokeColor(colors.grey)
        c.line(300, 120, 300, 720)
        c.setFont("ArialUni", 11)
        left = [
            "LEFT COLUMN — Experience",
            "Senior Engineer 2020-2026",
            "Built intake queues and OCR gates.",
            "Owned PostgreSQL schemas.",
            "Mentored 4 engineers.",
        ]
        right = [
            "RIGHT COLUMN — Education",
            "BSc Computer Engineering",
            "Kuwait University 2019",
            "Certifications",
            "AWS SAA, PMP",
        ]
        y = 700
        for line in left:
            c.drawString(50, y, line)
            y -= 18
        y = 700
        for line in right:
            c.drawString(320, y, line)
            y -= 18
        c.showPage()
        c.save()
        add(
            fid,
            "multicolumn_cv",
            path,
            language="en",
            layout="two_column",
            pdf_nature="digital_text",
            pages=1,
            expected_ocr_pages_1idx=[],
            expected_text_needles=[name, email, "LEFT COLUMN", "RIGHT COLUMN", "Experience", "Education"],
            expected_fields={"full_name": name, "email": email, "phone": phone},
            notes="Two-column layout with a vertical divider; reading-order stress.",
        )

    # --- 5. Scanned / image-only CVs (3) ---
    scanned = [
        (
            "cv_scanned_en_01",
            False,
            [
                "Scanned CV — Dana Wilkes",
                "Email: dana.wilkes@example.com",
                "Phone: +96551110000",
                "Role: QA Lead",
                "Experience: automation frameworks 2018-2026",
            ],
            {"full_name": "Dana Wilkes", "email": "dana.wilkes@example.com", "phone": "+96551110000"},
        ),
        (
            "cv_scanned_ar_01",
            True,
            [
                "سيرة ذاتية ممسوحة — خالد المنصور",
                "البريد: khaled.mansour@example.com",
                "الهاتف: +96552220000",
                "المسمى: مهندس شبكات",
                "الخبرة: البنية التحتية ٢٠١٧-٢٠٢٦",
            ],
            {"full_name": "خالد المنصور", "email": "khaled.mansour@example.com", "phone": "+96552220000"},
        ),
        (
            "cv_scanned_en_02",
            False,
            [
                "Scanned CV — Priya Shah",
                "Email: priya.shah@example.com",
                "Phone: +96553330000",
                "Role: Recruiter",
                "Experience: high-volume hiring 2019-2026",
            ],
            {"full_name": "Priya Shah", "email": "priya.shah@example.com", "phone": "+96553330000"},
        ),
    ]
    for fid, is_ar, lines, fields in scanned:
        path = FIXTURES / f"{fid}.pdf"
        pdf_page_image_text(path, lines, arabic=is_ar, pagesize=A4 if is_ar else letter)
        # Image-only pages: native text extractors should not recover the needles;
        # expected OCR = page 1. Needles remain as OCR target truth, not native truth.
        add(
            fid,
            "scanned_image_only_cv",
            path,
            language="ar" if is_ar else "en",
            layout="single_column",
            pdf_nature="scanned_image_only",
            pages=1,
            expected_ocr_pages_1idx=[1],
            expected_text_needles=lines[:3],
            expected_fields=fields,
            notes="Rendered text embedded as image-only page; native extractors should miss needles.",
        )

    # --- 6. Mixed digital + scanned (2) ---
    for fid, name, email in [
        ("cv_mixed_01", "Mixed Digital Scan", "mixed01@example.com"),
        ("cv_mixed_02", "Hybrid Resume Case", "mixed02@example.com"),
    ]:
        path = FIXTURES / f"{fid}.pdf"
        # page 1 digital
        tmp1 = ARTIFACTS / f"{fid}-p1.pdf"
        c = canvas.Canvas(str(tmp1), pagesize=letter)
        draw_en_lines(
            c,
            [
                name,
                f"Email: {email}",
                "DIGITAL PAGE — readable native text",
                "Skills: Python, Postgres, OCR routing",
            ],
        )
        c.showPage()
        c.save()
        # page 2 scanned
        tmp2 = ARTIFACTS / f"{fid}-p2.pdf"
        pdf_page_image_text(
            tmp2,
            [
                "SCANNED PAGE — certificate image",
                "Issuer: Kuwait Professional Board",
                "Credential: Cloud Architect",
            ],
        )
        writer = PdfWriter()
        writer.append(str(tmp1))
        writer.append(str(tmp2))
        with path.open("wb") as f:
            writer.write(f)
        add(
            fid,
            "mixed_digital_scanned",
            path,
            language="en",
            layout="mixed_pages",
            pdf_nature="mixed",
            pages=2,
            expected_ocr_pages_1idx=[2],
            expected_text_needles=[name, email, "DIGITAL PAGE"],
            expected_fields={"full_name": name, "email": email},
            notes="Page 1 digital text; page 2 image-only. OCR expected only on page 2.",
        )

    # --- 7. CID/ToUnicode + broken encoding (2) ---
    # Proper Unicode TrueType (ToUnicode via ReportLab)
    fid = "cv_tounicode_proper_01"
    path = FIXTURES / f"{fid}.pdf"
    c = canvas.Canvas(str(path), pagesize=letter)
    draw_en_lines(
        c,
        [
            "ToUnicode Proper CV — Nadia Faris",
            "Email: nadia.faris@example.com",
            "Phone: +96554445566",
            "Unicode markers: café naïve résumé — حساب تجريبي",
            "EXPERIENCE",
            "Document encoding specialist 2023-2026",
        ],
    )
    draw_ar_lines(c, ["نادية فارس", "اختبار ترميز يونيكود السليم"], y=560)
    c.showPage()
    c.save()
    add(
        fid,
        "cid_tounicode",
        path,
        language="ar_en",
        layout="single_column",
        pdf_nature="digital_text_tounicode",
        pages=1,
        expected_ocr_pages_1idx=[],
        expected_text_needles=["Nadia Faris", "nadia.faris@example.com", "نادية فارس", "café"],
        expected_fields={"full_name": "Nadia Faris", "email": "nadia.faris@example.com", "phone": "+96554445566"},
        notes="Proper embedded TrueType with Unicode text; should NOT need OCR.",
    )

    # Deliberately broken encoding: WinAnsi bytes that look like mojibake for Arabic intent
    fid = "cv_broken_encoding_01"
    path = FIXTURES / f"{fid}.pdf"
    # Build a minimal PDF with a custom font lacking useful ToUnicode and weird glyph bytes.
    # Use Helvetica with high-bit latin stand-ins that page_text_usable should flag.
    broken_lines = [
        "Broken Encoding CV - Proxy",
        "Email: broken.encoding@example.com",
        "Phone: +96556667788",
        "Name mojibake: \xd9\x86\xd9\x88\xd8\xb1\xd8\xa9",  # will be written as latin-1 escapes poorly
        "Garbled Arabic proxy: ÃÑÃÓÇä ãÔÝÑ",
        "EXPERIENCE: encoding stress case",
    ]
    c = canvas.Canvas(str(path), pagesize=letter)
    c.setFont("Helvetica", 12)
    y = 760
    for line in broken_lines:
        safe = line.encode("latin-1", errors="replace").decode("latin-1")
        c.drawString(50, y, safe)
        y -= 18
    c.showPage()
    c.save()
    add(
        fid,
        "broken_encoding",
        path,
        language="en_broken",
        layout="single_column",
        pdf_nature="digital_broken_encoding",
        pages=1,
        expected_ocr_pages_1idx=[1],  # should prefer OCR / flag encoding issues
        expected_text_needles=["broken.encoding@example.com", "+96556667788", "EXPERIENCE"],
        expected_fields={"email": "broken.encoding@example.com", "phone": "+96556667788"},
        notes="Deliberate mojibake/garbled text; encoding-issue / OCR-fallback stress case.",
    )

    # --- 8. Contracts (2) ---
    fid = "contract_employment_en_01"
    path = FIXTURES / f"{fid}.pdf"
    doc = SimpleDocTemplate(str(path), pagesize=A4, title="Employment Contract")
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(name="BodyUni", fontName="ArialUni", fontSize=10, leading=14))
    styles.add(ParagraphStyle(name="TitleUni", fontName="ArialUni", fontSize=14, leading=18, spaceAfter=12))
    story = [
        Paragraph("EMPLOYMENT CONTRACT", styles["TitleUni"]),
        Paragraph("Employer: Wathefni Technologies W.L.L.", styles["BodyUni"]),
        Paragraph("Employee: Samir Haddad", styles["BodyUni"]),
        Paragraph("Civil ID: 289010101234", styles["BodyUni"]),
        Paragraph("Role: Staff Software Engineer", styles["BodyUni"]),
        Paragraph("Start Date: 2026-09-01", styles["BodyUni"]),
        Paragraph("Basic Salary: KWD 1,250", styles["BodyUni"]),
        Spacer(1, 12),
        Paragraph(
            "Clause 1. The Employee shall perform duties assigned by the Employer in accordance "
            "with Kuwait Labor Law No. 6 of 2010 and company policy.",
            styles["BodyUni"],
        ),
        Paragraph(
            "Clause 2. Working hours are 8 hours per day, Sunday to Thursday, excluding official holidays.",
            styles["BodyUni"],
        ),
        Paragraph(
            "Clause 3. Either party may terminate this contract according to statutory notice requirements.",
            styles["BodyUni"],
        ),
    ]
    doc.build(story)
    add(
        fid,
        "contract",
        path,
        language="en",
        layout="legal_prose",
        pdf_nature="digital_text",
        pages=1,
        expected_ocr_pages_1idx=[],
        expected_text_needles=["EMPLOYMENT CONTRACT", "Samir Haddad", "Civil ID", "Kuwait Labor Law"],
        expected_fields={"employee_name": "Samir Haddad", "civil_id": "289010101234", "salary_kwd": "1250"},
        notes="Generated employment contract with structured clauses.",
    )

    # Real public Kuwait Labor Law PDF — subset first 3 pages for manageable fixture.
    fid = "contract_kuwait_labor_law_real_01"
    path = FIXTURES / f"{fid}.pdf"
    assert LAW_PDF.exists(), LAW_PDF
    reader = PdfReader(str(LAW_PDF))
    writer = PdfWriter()
    for i in range(min(3, len(reader.pages))):
        writer.add_page(reader.pages[i])
    with path.open("wb") as f:
        writer.write(f)
    add(
        fid,
        "contract",
        path,
        language="ar",
        layout="official_legal",
        pdf_nature="digital_text_real_world",
        pages=min(3, len(reader.pages)),
        expected_ocr_pages_1idx=[],
        expected_text_needles=["قانون", "العمل"],
        expected_fields={"document_type": "kuwait_labor_law", "source": "moj_law_6_2010"},
        notes="Real-world MOJ Kuwait Labor Law PDF, first 3 pages only.",
    )

    # --- 9. Identity-document style (2) ---
    fid = "identity_civil_id_digital_01"
    path = FIXTURES / f"{fid}.pdf"
    c = canvas.Canvas(str(path), pagesize=(85.6 * mm, 53.98 * mm))
    c.setFont("ArialUni", 8)
    c.drawString(8 * mm, 45 * mm, "CIVIL ID CARD — SYNTHETIC")
    c.setFont("NotoKufi", 9)
    c.drawRightString(78 * mm, 38 * mm, ar("بطاقة المدنية"))
    c.setFont("ArialUni", 7)
    c.drawString(8 * mm, 30 * mm, "Name: Yousef Al-Ahmad")
    c.drawString(8 * mm, 24 * mm, "Civil ID: 290123456789")
    c.drawString(8 * mm, 18 * mm, "Nationality: Kuwaiti")
    c.drawString(8 * mm, 12 * mm, "Expiry: 2030-01-15")
    c.showPage()
    c.save()
    add(
        fid,
        "identity_document",
        path,
        language="ar_en",
        layout="id_card",
        pdf_nature="digital_text",
        pages=1,
        expected_ocr_pages_1idx=[],
        expected_text_needles=["CIVIL ID", "Yousef Al-Ahmad", "290123456789"],
        expected_fields={"full_name": "Yousef Al-Ahmad", "civil_id": "290123456789", "doc_type": "civil_id"},
        notes="Synthetic Civil ID card-sized digital PDF (not a real person ID).",
    )

    fid = "identity_passport_scanned_01"
    path = FIXTURES / f"{fid}.pdf"
    pdf_page_image_text(
        path,
        [
            "PASSPORT BIODATA — SYNTHETIC SCAN",
            "Surname: ALMUTAIRI",
            "Given Names: HAYA",
            "Passport No: P1234567",
            "Nationality: KWT",
            "Date of Birth: 12 JAN 1994",
        ],
        pagesize=letter,
    )
    add(
        fid,
        "identity_document",
        path,
        language="en",
        layout="passport_biodata",
        pdf_nature="scanned_image_only",
        pages=1,
        expected_ocr_pages_1idx=[1],
        expected_text_needles=["PASSPORT", "ALMUTAIRI", "P1234567"],
        expected_fields={"surname": "ALMUTAIRI", "given_names": "HAYA", "passport_no": "P1234567", "doc_type": "passport"},
        notes="Synthetic passport biodata rendered as scanned image-only page.",
    )

    # --- 10. Table-heavy (2) ---
    fid = "table_compensation_01"
    path = FIXTURES / f"{fid}.pdf"
    doc = SimpleDocTemplate(str(path), pagesize=A4)
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(name="TTitle", fontName="ArialUni", fontSize=13, spaceAfter=10))
    data = [
        ["Component", "Amount (KWD)", "Frequency"],
        ["Basic Salary", "900", "Monthly"],
        ["Housing", "200", "Monthly"],
        ["Transport", "50", "Monthly"],
        ["Mobile", "25", "Monthly"],
        ["Total Cash", "1175", "Monthly"],
    ]
    table = Table(data, colWidths=[180, 120, 120])
    table.setStyle(
        TableStyle(
            [
                ("FONTNAME", (0, 0), (-1, -1), "ArialUni"),
                ("BACKGROUND", (0, 0), (-1, 0), colors.lightgrey),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.black),
                ("ALIGN", (1, 0), (-1, -1), "RIGHT"),
            ]
        )
    )
    doc.build([Paragraph("Compensation Breakdown — Employee Table", styles["TTitle"]), table])
    add(
        fid,
        "table_heavy",
        path,
        language="en",
        layout="table",
        pdf_nature="digital_text",
        pages=1,
        expected_ocr_pages_1idx=[],
        expected_text_needles=["Compensation Breakdown", "Basic Salary", "Total Cash", "1175"],
        expected_fields={"basic_salary": "900", "total_cash": "1175"},
        notes="Compensation table for section/table preservation scoring.",
    )

    fid = "table_experience_matrix_01"
    path = FIXTURES / f"{fid}.pdf"
    doc = SimpleDocTemplate(str(path), pagesize=letter)
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(name="TTitle2", fontName="ArialUni", fontSize=13, spaceAfter=10))
    data = [
        ["Year", "Employer", "Role", "Domain"],
        ["2024", "Wathefni", "Staff Engineer", "HR Tech"],
        ["2022", "Gulf Soft", "Senior Engineer", "Queues"],
        ["2020", "ByteCo", "Engineer", "ETL"],
        ["2018", "Startly", "Junior Engineer", "Web"],
    ]
    table = Table(data, colWidths=[60, 120, 140, 100])
    table.setStyle(
        TableStyle(
            [
                ("FONTNAME", (0, 0), (-1, -1), "ArialUni"),
                ("BACKGROUND", (0, 0), (-1, 0), colors.Color(0.9, 0.9, 0.95)),
                ("GRID", (0, 0), (-1, -1), 0.4, colors.black),
            ]
        )
    )
    doc.build(
        [
            Paragraph("Experience Matrix — Table Heavy CV Annex", styles["TTitle2"]),
            Paragraph("Candidate: Table Annex Demo | email: table.annex@example.com", styles["Normal"]),
            Spacer(1, 8),
            table,
        ]
    )
    add(
        fid,
        "table_heavy",
        path,
        language="en",
        layout="table",
        pdf_nature="digital_text",
        pages=1,
        expected_ocr_pages_1idx=[],
        expected_text_needles=["Experience Matrix", "Wathefni", "Staff Engineer", "table.annex@example.com"],
        expected_fields={"email": "table.annex@example.com", "latest_employer": "Wathefni"},
        notes="Multi-row experience matrix table.",
    )

    # --- 11. Multi-page digital CV (fills locked total of 24) ---
    fid = "cv_en_digital_multipage_01"
    path = FIXTURES / f"{fid}.pdf"
    c = canvas.Canvas(str(path), pagesize=letter)
    draw_en_lines(
        c,
        [
            "Multi-page CV — Nora Blake",
            "Email: nora.blake@example.com",
            "Phone: +96557770011",
            "Title: Staff Platform Engineer",
            "EXPERIENCE — Page 1",
            "2023-2026 Wathefni — durable intake queues and extraction safety.",
            "2020-2023 Cloudlane — event-driven payroll integrations.",
        ],
    )
    c.showPage()
    draw_en_lines(
        c,
        [
            "EDUCATION — Page 2",
            "MSc Software Systems — Imperial College London",
            "SKILLS",
            "Python, Rust bindings evaluation, PostgreSQL, OCR routing policy",
            "LANGUAGES",
            "English, Arabic (working)",
        ],
    )
    c.showPage()
    c.save()
    add(
        fid,
        "english_digital_cv",
        path,
        language="en",
        layout="single_column_multipage",
        pdf_nature="digital_text",
        pages=2,
        expected_ocr_pages_1idx=[],
        expected_text_needles=["Nora Blake", "nora.blake@example.com", "EXPERIENCE", "EDUCATION", "SKILLS"],
        expected_fields={
            "full_name": "Nora Blake",
            "email": "nora.blake@example.com",
            "phone": "+96557770011",
            "title": "Staff Platform Engineer",
        },
        notes="Two-page digital English CV for multi-page routing/extraction stress.",
    )

    assert len(fixtures) == 24, len(fixtures)
    (FIXTURES / "MANIFEST.json").write_text(
        json.dumps(
            {
                "created_at": utc_now(),
                "count": len(fixtures),
                "fixtures": fixtures,
                "policy": {
                    "no_txt_cvs": True,
                    "no_trivial_placeholders": True,
                    "structurally_valid_pdfs_only": True,
                    "paid_ocr": False,
                },
            },
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    return fixtures


def package_identity() -> dict[str, Any]:
    import pdf_inspector as pi

    so = Path(pi.__file__).with_name("pdf_inspector.abi3.so")
    md = metadata("pdf-inspector")
    return {
        "package": "pdf-inspector",
        "pypi_version": version("pdf-inspector"),
        "binding": "Python via PyO3 (Rust abi3 extension)",
        "module_file": str(pi.__file__),
        "extension_so": str(so),
        "extension_so_sha256": sha256_file(so) if so.exists() else None,
        "license": md.get("License"),
        "project_urls": dict(md).get("Project-URL"),
        "github_tag_note": (
            "PyPI publishes 0.2.6; GitHub tags observed around evaluation time include "
            "v0.2.0–v0.2.3 then v0.3.x…v0.7.0. No matching GitHub tag named v0.2.6 was found; "
            "report package version + wheel digest instead of inventing a commit."
        ),
        "wheel_arm64_sha256_from_pypi": "d2b2aaa95b242da38630bbd0644ffe9a929466f9c4e6406d6f1957b59b413d08",
        "apis_invoked": [
            "process_pdf",
            "detect_pdf",
            "classify_pdf",
            "extract_pages_markdown",
            "extract_text",
        ],
        "scan_strategy": {
            "python_exposed": False,
            "rust_strategies_documented": ["EarlyExit", "Full", "Sample(n)", "Pages(vec)"],
            "python_process_pdf_signature": "process_pdf(path, pages=None)",
            "wave0_strategy": (
                "Python binding does not expose ScanStrategy. Wave 0 uses process_pdf() "
                "default detection path for full detect+extract+markdown, plus "
                "extract_pages_markdown() for per-page Markdown/OCR flags. Full strategy "
                "is documented for Rust process_pdf_with_options only."
            ),
        },
    }


_EMAIL_RE = re.compile(r"[A-Z0-9._%+\-]+@[A-Z0-9.\-]+\.[A-Z]{2,}", re.I)
_PHONE_RE = re.compile(r"\+965\d{8}")


def extract_fields(text: str) -> dict[str, Any]:
    emails = _EMAIL_RE.findall(text or "")
    phones = _PHONE_RE.findall(text or "")
    return {
        "emails": emails[:3],
        "phones": phones[:3],
        "has_experience_section": bool(re.search(r"EXPERIENCE|الخبرة", text or "", re.I)),
        "has_skills_section": bool(re.search(r"SKILLS|المهارات", text or "", re.I)),
    }


def arabic_integrity(text: str, needles: list[str]) -> dict[str, Any]:
    ar_needles = [n for n in needles if re.search(r"[\u0600-\u06FF]", n)]
    if not ar_needles:
        return {"applicable": False, "hit": 0, "total": 0, "ratio": None, "missing": []}
    missing = [n for n in ar_needles if n not in (text or "")]
    hit = len(ar_needles) - len(missing)
    return {
        "applicable": True,
        "hit": hit,
        "total": len(ar_needles),
        "ratio": round(hit / len(ar_needles), 3),
        "missing": missing,
    }


def poppler_shadow(path: Path) -> dict[str, Any]:
    import subprocess

    import cv_extraction as cvx

    t0 = time.perf_counter()
    assessments = cvx.assess_pdf_pages(path)
    elapsed_ms = int((time.perf_counter() - t0) * 1000)
    pages_needing = []
    page_details = []
    for a in assessments:
        page_number = int(getattr(a, "page_number"))
        disposition = str(getattr(a, "disposition") or "")
        reason = getattr(a, "reason", None)
        text = getattr(a, "local_text", "") or ""
        needs = disposition == "needs_ocr"
        if needs:
            pages_needing.append(page_number)
        page_details.append(
            {
                "page": page_number,
                "disposition": disposition,
                "needs_ocr": needs,
                "reason": reason,
                "text_preview": text[:240],
                "text_len": len(text),
            }
        )
    proc = subprocess.run(
        ["pdftotext", "-layout", str(path), "-"],
        capture_output=True,
        text=True,
    )
    full_text = proc.stdout or ""
    err = None if proc.returncode == 0 else f"pdftotext_rc_{proc.returncode}"
    return {
        "engine": "poppler_pdftotext_assess_pdf_pages",
        "elapsed_ms": elapsed_ms,
        "pages_needing_ocr_1idx": pages_needing,
        "page_details": page_details,
        "text": full_text,
        "text_error": err,
        "fields": extract_fields(full_text),
    }


def inspector_shadow(path: Path) -> dict[str, Any]:
    import pdf_inspector as pi

    t0 = time.perf_counter()
    processed = pi.process_pdf(str(path))
    process_ms = int((time.perf_counter() - t0) * 1000)

    t1 = time.perf_counter()
    detected = pi.detect_pdf(str(path))
    detect_ms = int((time.perf_counter() - t1) * 1000)

    t2 = time.perf_counter()
    classified = pi.classify_pdf(str(path))
    classify_ms = int((time.perf_counter() - t2) * 1000)

    t3 = time.perf_counter()
    pages_md = pi.extract_pages_markdown(str(path))
    pages_ms = int((time.perf_counter() - t3) * 1000)

    plain = pi.extract_text(str(path))

    def dump_result(obj: Any) -> dict[str, Any]:
        return {
            "pdf_type": getattr(obj, "pdf_type", None),
            "page_count": getattr(obj, "page_count", None),
            "processing_time_ms": getattr(obj, "processing_time_ms", None),
            "pages_needing_ocr": list(getattr(obj, "pages_needing_ocr", []) or []),
            "confidence": getattr(obj, "confidence", None),
            "is_complex_layout": getattr(obj, "is_complex_layout", None),
            "pages_with_tables": list(getattr(obj, "pages_with_tables", []) or []),
            "pages_with_columns": list(getattr(obj, "pages_with_columns", []) or []),
            "has_encoding_issues": getattr(obj, "has_encoding_issues", None),
            "title": getattr(obj, "title", None),
            "markdown_len": len(getattr(obj, "markdown", None) or ""),
        }

    per_page = []
    for p in getattr(pages_md, "pages", []) or []:
        per_page.append(
            {
                "page_0idx": p.page,
                "needs_ocr": p.needs_ocr,
                "markdown": p.markdown,
                "markdown_len": len(p.markdown or ""),
            }
        )

    # Normalize pages_needing_ocr to 1-indexed for comparison with Poppler/expected.
    # classify_pdf docs say 0-indexed; process_pdf / extract_pages_markdown docs say 1-indexed for some fields.
    process_pages = list(getattr(processed, "pages_needing_ocr", []) or [])
    classify_pages_0 = list(getattr(classified, "pages_needing_ocr", []) or [])
    pages_md_pages = list(getattr(pages_md, "pages_needing_ocr", []) or [])

    markdown = getattr(processed, "markdown", None) or ""
    return {
        "engine": "pdf_inspector_process_pdf",
        "process_wall_ms": process_ms,
        "detect_wall_ms": detect_ms,
        "classify_wall_ms": classify_ms,
        "pages_markdown_wall_ms": pages_ms,
        "process_pdf": dump_result(processed),
        "detect_pdf": dump_result(detected),
        "classify_pdf": {
            "pdf_type": classified.pdf_type,
            "page_count": classified.page_count,
            "pages_needing_ocr_0idx": classify_pages_0,
            "confidence": classified.confidence,
        },
        "extract_pages_markdown": {
            "pages_with_tables_1idx": list(getattr(pages_md, "pages_with_tables", []) or []),
            "pages_with_columns_1idx": list(getattr(pages_md, "pages_with_columns", []) or []),
            "pages_needing_ocr_1idx": pages_md_pages,
            "is_complex": getattr(pages_md, "is_complex", None),
            "pages": per_page,
        },
        "markdown": markdown,
        "plain_text": plain,
        "pages_needing_ocr_process": process_pages,
        "fields_from_markdown": extract_fields(markdown),
        "fields_from_plain": extract_fields(plain or ""),
    }


def normalize_ocr_pages(pages: list[int], *, page_count: int, assume: str) -> list[int]:
    """Return sorted unique 1-indexed page numbers."""
    if not pages:
        return []
    pages = sorted({int(p) for p in pages})
    if assume == "auto":
        # If any value is 0, treat as 0-indexed.
        if any(p == 0 for p in pages):
            return [p + 1 for p in pages]
        # If max equals page_count and min>=1, already 1-indexed.
        return pages
    if assume == "0idx":
        return [p + 1 for p in pages]
    return pages


def score_fixture(fid: str, path: Path) -> dict[str, Any]:
    expected = json.loads((EXPECTED / f"{fid}.json").read_text(encoding="utf-8"))
    pop = poppler_shadow(path)
    insp = inspector_shadow(path)

    # Persist artifacts
    art_dir = ARTIFACTS / fid
    art_dir.mkdir(parents=True, exist_ok=True)
    (art_dir / "poppler.txt").write_text(pop.get("text") or "", encoding="utf-8")
    (art_dir / "inspector.md").write_text(insp.get("markdown") or "", encoding="utf-8")
    (art_dir / "inspector_plain.txt").write_text(insp.get("plain_text") or "", encoding="utf-8")
    (art_dir / "inspector_pages.json").write_text(
        json.dumps(insp.get("extract_pages_markdown"), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    exp_ocr = set(expected["expected_ocr_pages_1idx"])
    pop_ocr = set(pop["pages_needing_ocr_1idx"])
    insp_ocr_raw = insp["pages_needing_ocr_process"]
    insp_ocr = set(
        normalize_ocr_pages(
            insp_ocr_raw,
            page_count=int(insp["process_pdf"].get("page_count") or expected["pages"]),
            assume="auto",
        )
    )
    # Prefer extract_pages_markdown 1-idx when process list empty but pages say needs_ocr
    if not insp_ocr:
        md_pages = insp["extract_pages_markdown"].get("pages_needing_ocr_1idx") or []
        insp_ocr = set(normalize_ocr_pages(md_pages, page_count=expected["pages"], assume="auto"))
    # Also include per-page needs_ocr flags
    for p in insp["extract_pages_markdown"].get("pages") or []:
        if p.get("needs_ocr"):
            insp_ocr.add(int(p["page_0idx"]) + 1)

    false_skips = sorted(exp_ocr - insp_ocr)  # expected OCR but inspector skipped
    unnecessary = sorted(insp_ocr - exp_ocr)  # inspector OCR but not expected
    pop_false_skips = sorted(exp_ocr - pop_ocr)
    pop_unnecessary = sorted(pop_ocr - exp_ocr)

    needles = expected["expected_text_needles"]
    nature = expected["pdf_nature"]

    def needle_score(text: str) -> dict[str, Any]:
        missing = [n for n in needles if n not in (text or "")]
        # For scanned image-only, native extractors are expected to miss OCR-target needles.
        if nature in {"scanned_image_only"}:
            # Success means NOT finding image-rendered needles in native text (or finding none).
            return {
                "mode": "native_should_miss_ocr_targets",
                "found": [n for n in needles if n in (text or "")],
                "missing": missing,
                "native_leak_ratio": round((len(needles) - len(missing)) / max(1, len(needles)), 3),
            }
        hit = len(needles) - len(missing)
        return {
            "mode": "native_should_hit",
            "hit": hit,
            "total": len(needles),
            "ratio": round(hit / max(1, len(needles)), 3),
            "missing": missing,
        }

    pop_needles = needle_score(pop.get("text") or "")
    insp_needles = needle_score(insp.get("markdown") or "")
    insp_plain_needles = needle_score(insp.get("plain_text") or "")

    # Field accuracy vs expected_fields for digital docs using inspector markdown / poppler text
    exp_fields = expected.get("expected_fields") or {}
    field_scores = {}
    for label, text, extracted in [
        ("poppler", pop.get("text") or "", pop.get("fields") or {}),
        ("inspector_markdown", insp.get("markdown") or "", insp.get("fields_from_markdown") or {}),
    ]:
        checks = {}
        for key, val in exp_fields.items():
            if key in {"email"}:
                checks[key] = val in (extracted.get("emails") or []) or val in text
            elif key in {"phone"}:
                checks[key] = val in (extracted.get("phones") or []) or val in text
            else:
                checks[key] = str(val) in text
        field_scores[label] = {
            "checks": checks,
            "hit": sum(1 for v in checks.values() if v),
            "total": len(checks),
            "ratio": round(sum(1 for v in checks.values() if v) / max(1, len(checks)), 3),
        }

    # Projected Mistral pages: if using inspector OCR advice vs Poppler vs naive all-pages
    page_count = expected["pages"]
    proj = {
        "pages_total": page_count,
        "ocr_pages_expected": sorted(exp_ocr),
        "ocr_pages_poppler": sorted(pop_ocr),
        "ocr_pages_inspector": sorted(insp_ocr),
        "cost_if_all_pages_usd": round(page_count * COST_USD_PER_PAGE, 6),
        "cost_if_poppler_ocr_usd": round(len(pop_ocr) * COST_USD_PER_PAGE, 6),
        "cost_if_inspector_ocr_usd": round(len(insp_ocr) * COST_USD_PER_PAGE, 6),
        "cost_if_expected_ocr_usd": round(len(exp_ocr) * COST_USD_PER_PAGE, 6),
        "inspector_vs_all_pages_savings_usd": round((page_count - len(insp_ocr)) * COST_USD_PER_PAGE, 6),
        "inspector_vs_poppler_delta_pages": len(insp_ocr) - len(pop_ocr),
    }

    row = {
        "fixture_id": fid,
        "category": expected["category"],
        "language": expected["language"],
        "pdf_nature": nature,
        "path": str(path),
        "page_count": page_count,
        "poppler": {
            "elapsed_ms": pop["elapsed_ms"],
            "pages_needing_ocr_1idx": sorted(pop_ocr),
            "false_skips_vs_expected": pop_false_skips,
            "unnecessary_vs_expected": pop_unnecessary,
            "needle_score": pop_needles,
            "arabic_integrity": arabic_integrity(pop.get("text") or "", needles),
            "field_score": field_scores["poppler"],
            "encoding_signal": any("encod" in str(p.get("reason") or "").lower() for p in pop.get("page_details") or []),
        },
        "pdf_inspector": {
            "process_wall_ms": insp["process_wall_ms"],
            "library_processing_time_ms": insp["process_pdf"].get("processing_time_ms"),
            "pdf_type": insp["process_pdf"].get("pdf_type"),
            "confidence": insp["process_pdf"].get("confidence"),
            "has_encoding_issues": insp["process_pdf"].get("has_encoding_issues"),
            "is_complex_layout": insp["process_pdf"].get("is_complex_layout"),
            "pages_with_tables": insp["process_pdf"].get("pages_with_tables"),
            "pages_with_columns": insp["process_pdf"].get("pages_with_columns"),
            "pages_needing_ocr_1idx": sorted(insp_ocr),
            "false_skips_vs_expected": false_skips,
            "unnecessary_vs_expected": unnecessary,
            "needle_score_markdown": insp_needles,
            "needle_score_plain": insp_plain_needles,
            "arabic_integrity_markdown": arabic_integrity(insp.get("markdown") or "", needles),
            "arabic_integrity_plain": arabic_integrity(insp.get("plain_text") or "", needles),
            "field_score": field_scores["inspector_markdown"],
            "detect_pdf_type": insp["detect_pdf"].get("pdf_type"),
            "classify_confidence": insp["classify_pdf"].get("confidence"),
        },
        "routing_agreement_with_expected": {
            "poppler_exact": pop_ocr == exp_ocr,
            "inspector_exact": insp_ocr == exp_ocr,
            "poppler_vs_inspector": pop_ocr == insp_ocr,
        },
        "projected_cost": proj,
        "mistral_reference": {
            "called": False,
            "reason": "Wave 0 default: no paid OCR; capped sample requires separate owner approval",
        },
    }
    return row


def summarize(rows: list[dict[str, Any]]) -> dict[str, Any]:
    n = len(rows)
    insp_false_skips = sum(1 for r in rows if r["pdf_inspector"]["false_skips_vs_expected"])
    insp_unnec = sum(1 for r in rows if r["pdf_inspector"]["unnecessary_vs_expected"])
    pop_false_skips = sum(1 for r in rows if r["poppler"]["false_skips_vs_expected"])
    digital = [r for r in rows if "scanned" not in r["pdf_nature"] and r["pdf_nature"] != "mixed"]
    scanned = [r for r in rows if "scanned" in r["pdf_nature"]]
    mixed = [r for r in rows if r["pdf_nature"] == "mixed"]

    def avg_field(rows_: list[dict[str, Any]], path: tuple[str, ...]) -> float | None:
        vals = []
        for r in rows_:
            cur: Any = r
            for p in path:
                cur = cur.get(p) if isinstance(cur, dict) else None
            if isinstance(cur, (int, float)):
                vals.append(float(cur))
        return round(sum(vals) / len(vals), 3) if vals else None

    total_pages = sum(r["page_count"] for r in rows)
    insp_ocr_pages = sum(len(r["pdf_inspector"]["pages_needing_ocr_1idx"]) for r in rows)
    pop_ocr_pages = sum(len(r["poppler"]["pages_needing_ocr_1idx"]) for r in rows)
    exp_ocr_pages = sum(len(r["projected_cost"]["ocr_pages_expected"]) for r in rows)

    arabic_rows = [r for r in rows if r["language"] in {"ar", "ar_en"}]
    ar_insp = []
    for r in arabic_rows:
        ai = r["pdf_inspector"]["arabic_integrity_markdown"]
        if ai.get("applicable"):
            ar_insp.append(ai["ratio"])

    return {
        "fixtures": n,
        "total_pages": total_pages,
        "routing": {
            "inspector_exact_match_rate": round(
                sum(1 for r in rows if r["routing_agreement_with_expected"]["inspector_exact"]) / n, 3
            ),
            "poppler_exact_match_rate": round(
                sum(1 for r in rows if r["routing_agreement_with_expected"]["poppler_exact"]) / n, 3
            ),
            "inspector_poppler_agreement_rate": round(
                sum(1 for r in rows if r["routing_agreement_with_expected"]["poppler_vs_inspector"]) / n, 3
            ),
            "fixtures_with_inspector_false_skips": insp_false_skips,
            "fixtures_with_inspector_unnecessary_ocr": insp_unnec,
            "fixtures_with_poppler_false_skips": pop_false_skips,
        },
        "speed_ms": {
            "inspector_process_avg": avg_field(rows, ("pdf_inspector", "process_wall_ms")),
            "inspector_library_avg": avg_field(rows, ("pdf_inspector", "library_processing_time_ms")),
            "poppler_assess_avg": avg_field(rows, ("poppler", "elapsed_ms")),
        },
        "digital_native_needle_hit_avg": avg_field(
            [r for r in digital if r["pdf_inspector"]["needle_score_markdown"].get("mode") == "native_should_hit"],
            ("pdf_inspector", "needle_score_markdown", "ratio"),
        ),
        "poppler_digital_needle_hit_avg": avg_field(
            [r for r in digital if r["poppler"]["needle_score"].get("mode") == "native_should_hit"],
            ("poppler", "needle_score", "ratio"),
        ),
        "arabic_integrity_markdown_avg": round(sum(ar_insp) / len(ar_insp), 3) if ar_insp else None,
        "field_accuracy_avg": {
            "inspector_markdown": avg_field(rows, ("pdf_inspector", "field_score", "ratio")),
            "poppler": avg_field(rows, ("poppler", "field_score", "ratio")),
        },
        "projected_mistral": {
            "usd_per_page_assumption": COST_USD_PER_PAGE,
            "pages_total": total_pages,
            "ocr_pages_expected": exp_ocr_pages,
            "ocr_pages_poppler": pop_ocr_pages,
            "ocr_pages_inspector": insp_ocr_pages,
            "cost_all_pages_usd": round(total_pages * COST_USD_PER_PAGE, 6),
            "cost_poppler_usd": round(pop_ocr_pages * COST_USD_PER_PAGE, 6),
            "cost_inspector_usd": round(insp_ocr_pages * COST_USD_PER_PAGE, 6),
            "savings_vs_all_pages_usd": round((total_pages - insp_ocr_pages) * COST_USD_PER_PAGE, 6),
            "savings_vs_poppler_usd": round((pop_ocr_pages - insp_ocr_pages) * COST_USD_PER_PAGE, 6),
            "note": "Projection only; Wave 0 did not call Mistral.",
        },
        "subset_counts": {"digital_like": len(digital), "scanned": len(scanned), "mixed": len(mixed)},
    }


def verdicts(summary: dict[str, Any], rows: list[dict[str, Any]]) -> dict[str, Any]:
    insp_false = summary["routing"]["fixtures_with_inspector_false_skips"]
    ar_avg = summary.get("arabic_integrity_markdown_avg")
    digital_hit = summary.get("digital_native_needle_hit_avg") or 0
    field_insp = (summary.get("field_accuracy_avg") or {}).get("inspector_markdown") or 0
    broken = [r for r in rows if r["fixture_id"] == "cv_broken_encoding_01"]
    broken_false_skip = bool(broken and broken[0]["pdf_inspector"]["false_skips_vs_expected"] == [])
    # false_skips empty means it did NOT skip when OCR expected — good.
    # If expected OCR=[1] and inspector false_skips empty and 1 in pages_needing -> good advisor.
    broken_ok = False
    if broken:
        b = broken[0]
        broken_ok = (
            1 in b["pdf_inspector"]["pages_needing_ocr_1idx"]
            or b["pdf_inspector"].get("has_encoding_issues") is True
        )

    # 1) native text extractor
    native = "NO-GO"
    native_reason = []
    if digital_hit >= 0.85 and (ar_avg is None or ar_avg >= 0.8):
        native = "CONDITIONAL-GO"
        native_reason.append("Strong digital needle recovery including Arabic on curated set.")
    else:
        native_reason.append(
            f"Digital needle hit={digital_hit}, arabic_integrity={ar_avg}; below safe replace threshold."
        )
    if field_insp < 0.75:
        native = "NO-GO"
        native_reason.append(f"Downstream field accuracy {field_insp} < 0.75.")

    # 2) OCR-page advisor
    advisor = "NO-GO"
    advisor_reason = []
    exact = summary["routing"]["inspector_exact_match_rate"]
    if exact >= 0.85 and insp_false == 0 and broken_ok:
        advisor = "GO"
        advisor_reason.append("High exact routing match, zero false OCR skips, broken-encoding flagged.")
    elif exact >= 0.7 and insp_false <= 1:
        advisor = "CONDITIONAL-GO"
        advisor_reason.append(
            f"Exact match {exact}; false-skip fixtures={insp_false}; usable only behind Poppler veto."
        )
    else:
        advisor_reason.append(
            f"Exact match {exact}; false-skip fixtures={insp_false}; broken_encoding_ok={broken_ok}."
        )

    # 3) primary router with Poppler veto
    primary = "NO-GO"
    primary_reason = [
        "Primary routing requires durable false-skip=0 on broken encoding + Arabic/real-scan soak, "
        "Python Full scan strategy exposure, and production shadow metrics. Not met for Wave 0."
    ]
    if advisor in {"GO", "CONDITIONAL-GO"} and insp_false == 0 and broken_ok:
        primary = "CONDITIONAL-GO"
        primary_reason = [
            "May shadow-advise OCR pages with Poppler authoritative veto only; not allowed to skip OCR alone."
        ]

    smallest_wave = {
        "name": "pdf_inspector_shadow_advisor_wave1",
        "scope": (
            "CV PDF intake only: record pdf-inspector process_pdf signals beside Poppler assess_pdf_pages; "
            "never change paid OCR routing; emit disagreement metrics."
        ),
        "feature_flag": "WATHEFNI_PDF_INSPECTOR_SHADOW=1",
        "authoritative_router": "Poppler assess_pdf_pages / page_text_usable",
        "shadow_signals": [
            "pdf_type",
            "confidence",
            "pages_needing_ocr",
            "has_encoding_issues",
            "pages_with_tables",
            "pages_with_columns",
            "markdown_len",
            "processing_time_ms",
        ],
        "observability": [
            "cv_extraction_runs.raw_json.pdf_inspector_shadow",
            "metric: pdf_inspector_poppler_ocr_page_disagreement",
            "metric: pdf_inspector_false_skip_candidate",
            "metric: pdf_inspector_encoding_issue_rate",
        ],
        "rollback": "Unset WATHEFNI_PDF_INSPECTOR_SHADOW; no routing code path depends on it.",
        "acceptance_thresholds_before_advisor_canary": {
            "false_ocr_skips_on_known_need_ocr_set": 0,
            "broken_encoding_flag_or_ocr_rate": "100%",
            "arabic_needle_integrity_avg": ">=0.90",
            "digital_needle_hit_avg": ">=0.90",
            "shadow_overhead_p95_ms": "<=150 on <=10 page CVs",
        },
        "explicitly_out_of_scope": [
            "Replace Poppler",
            "Call/skip Mistral based on inspector alone",
            "Identity/contract/payroll routing changes",
            "Migration Wave 1-B resume",
        ],
    }

    return {
        "native_pdf_text_extraction": {"verdict": native, "reasons": native_reason},
        "ocr_page_advising": {"verdict": advisor, "reasons": advisor_reason},
        "primary_routing_with_poppler_veto": {"verdict": primary, "reasons": primary_reason},
        "smallest_safe_implementation_wave": smallest_wave,
    }


def main() -> None:
    print("PDF_INSPECTOR_DEEP_EVAL_WAVE0_START")
    print(json.dumps({"evid": str(EVID), "fixture_target": 24}, indent=2))
    fixtures = build_fixture_manifest()
    print(f"FIXTURES_BUILT count={len(fixtures)}")

    identity = package_identity()
    (RESULTS / "package_identity.json").write_text(json.dumps(identity, indent=2), encoding="utf-8")

    rows = []
    for fx in fixtures:
        fid = fx["fixture_id"]
        path = EVID / fx["path"]
        print(f"BENCH {fid}")
        row = score_fixture(fid, path)
        rows.append(row)
        (RESULTS / f"{fid}.json").write_text(json.dumps(row, ensure_ascii=False, indent=2), encoding="utf-8")

    summary = summarize(rows)
    decisions = verdicts(summary, rows)
    matrix = {
        "created_at": utc_now(),
        "package": identity,
        "summary": summary,
        "decisions": decisions,
        "rows": rows,
        "constraints_honored": {
            "production_routing_unchanged": True,
            "poppler_authoritative": True,
            "pdf_inspector_shadow_only": True,
            "migration_wave1b_not_resumed": True,
            "paid_ocr_called": False,
            "real_pdf_fixtures_only": True,
        },
    }
    (RESULTS / "matrix.json").write_text(json.dumps(matrix, ensure_ascii=False, indent=2), encoding="utf-8")

    # Compact CSV-like markdown table
    lines = [
        "| fixture | category | nature | poppler_ocr | inspector_ocr | insp_false_skip | insp_unnec | insp_ms | field_insp | ar_integrity |",
        "|---|---|---|---|---|---|---|---:|---:|---:|",
    ]
    for r in rows:
        ai = r["pdf_inspector"]["arabic_integrity_markdown"]
        ar_s = ai.get("ratio") if ai.get("applicable") else "-"
        lines.append(
            "| {fid} | {cat} | {nat} | {po} | {io} | {fs} | {un} | {ms} | {fi} | {ar} |".format(
                fid=r["fixture_id"],
                cat=r["category"],
                nat=r["pdf_nature"],
                po=",".join(map(str, r["poppler"]["pages_needing_ocr_1idx"])) or "-",
                io=",".join(map(str, r["pdf_inspector"]["pages_needing_ocr_1idx"])) or "-",
                fs=",".join(map(str, r["pdf_inspector"]["false_skips_vs_expected"])) or "-",
                un=",".join(map(str, r["pdf_inspector"]["unnecessary_vs_expected"])) or "-",
                ms=r["pdf_inspector"]["process_wall_ms"],
                fi=r["pdf_inspector"]["field_score"]["ratio"],
                ar=ar_s,
            )
        )
    (RESULTS / "matrix.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

    print(json.dumps({"summary": summary, "decisions": decisions}, indent=2, ensure_ascii=False))
    print("PDF_INSPECTOR_DEEP_EVAL_WAVE0_DONE")


if __name__ == "__main__":
    main()
