#!/usr/bin/env python3
"""Wave 2 — legally usable CV PDF corpus acquisition (offline/synthetic-first).

Builds >=500 structurally valid PDFs for pdf-inspector shadow evaluation.
No LinkedIn/Google scraping. No production/staging candidate intake.
Prefers fully synthetic documents with fake identifiers.
"""

from __future__ import annotations

import hashlib
import json
import math
import random
import shutil
import sys
import zlib
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageFont, ImageFilter
from pypdf import PdfReader, PdfWriter
from reportlab.lib.pagesizes import A4, letter
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas

import arabic_reshaper
from bidi.algorithm import get_display

ROOT = Path(__file__).resolve().parents[1]
EVID = Path("/Users/azizalmulla/Desktop/claw/ops/evidence/pdf-inspector-corpus-wave2-20260804")
CORPUS = EVID / "corpus"
MANIFESTS = EVID / "manifests"
ARTIFACTS = EVID / "artifacts"
WAVE0_FIXTURES = Path(
    "/Users/azizalmulla/Desktop/claw/ops/evidence/pdf-inspector-deep-eval-wave0-20260804/fixtures"
)
MOJ_LAW = Path(
    "/Users/azizalmulla/Desktop/claw/ops/evidence/leave-wave2b-policy-closure-20260802T160608Z"
    "/sources/official/moj-law-6-2010-kuwait-labor.pdf"
)

AR_FONT = "/Users/azizalmulla/Library/Fonts/NotoKufiArabic-Regular.ttf"
AR_FONT_BOLD = "/Users/azizalmulla/Library/Fonts/NotoKufiArabic-Bold.ttf"
EN_FONT = "/System/Library/Fonts/Supplemental/Arial Unicode.ttf"
EN_FONT_ALT = "/System/Library/Fonts/Supplemental/Arial Narrow.ttf"
EN_FONT_HEAVY = "/System/Library/Fonts/Supplemental/Arial Black.ttf"
VERA = str(ROOT / ".venv/lib/python3.14/site-packages/reportlab/fonts/Vera.ttf")

for d in (CORPUS, MANIFESTS, ARTIFACTS):
    d.mkdir(parents=True, exist_ok=True)

pdfmetrics.registerFont(TTFont("NotoKufi", AR_FONT))
pdfmetrics.registerFont(TTFont("NotoKufiBold", AR_FONT_BOLD))
pdfmetrics.registerFont(TTFont("ArialUni", EN_FONT))
pdfmetrics.registerFont(TTFont("ArialNarrow", EN_FONT_ALT))
pdfmetrics.registerFont(TTFont("ArialBlack", EN_FONT_HEAVY))
pdfmetrics.registerFont(TTFont("Vera", VERA))


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def ar(text: str) -> str:
    return get_display(arabic_reshaper.reshape(text))


FIRST_EN = [
    "Aisha", "Omar", "Sara", "Nour", "Hassan", "Layla", "Yousef", "Mariam", "Khaled", "Huda",
    "Rania", "Tariq", "Dana", "Faisal", "Noor", "Samir", "Lina", "Bassam", "Reem", "Adel",
]
LAST_EN = [
    "AlSabah", "AlMutairi", "AlQahtani", "AlHarbi", "AlDosari", "AlAjmi", "AlRashid",
    "AlNasser", "AlFaraj", "AlOtaibi", "Synthetic", "Evalcorp", "Benchmark", "Fixture",
]
FIRST_AR = [
    "نورة", "فهد", "مريم", "خالد", "سارة", "يوسف", "ليلى", "حسن", "هدى", "رانيا",
    "طارق", "دانة", "فيصل", "نور", "سمير", "لينا", "بسام", "ريم", "عادل", "عائشة",
]
LAST_AR = [
    "العتيبي", "الشمري", "الصباح", "المطيري", "القحطاني", "الحربي", "الدوسري",
    "العجمي", "الراشد", "الناصر", "الفرج", "الوهيبي",
]
TITLES_EN = [
    "Software Engineer", "Compliance Specialist", "HR Analyst", "Product Manager",
    "Data Scientist", "DevOps Engineer", "Talent Partner", "Finance Analyst",
    "UX Designer", "Security Engineer", "Operations Lead", "QA Engineer",
]
TITLES_AR = [
    "مهندسة برمجيات", "أخصائي امتثال", "محللة موارد بشرية", "مدير منتج",
    "عالم بيانات", "مهندس عمليات", "شريك مواهب", "محلل مالي",
]
SKILLS = [
    "Python", "Postgres", "OCR", "Arabic NLP", "React", "Kubernetes", "SQL",
    "Compliance", "Payroll", "Attendance", "Docker", "TypeScript", "Airflow",
]
COMPANIES = [
    "Synthetic Soft LLC", "Evalcorp Gulf", "Benchmark Labs", "Fixture Systems",
    "Shadow Advisors Co", "Corpus Digital", "Noto Demo Group", "Wathefni Test Co",
]


def persona(rng: random.Random, *, arabic: bool = False) -> dict[str, str]:
    if arabic:
        first = rng.choice(FIRST_AR)
        last = rng.choice(LAST_AR)
        name = f"{first} {last}"
        title = rng.choice(TITLES_AR)
    else:
        first = rng.choice(FIRST_EN)
        last = rng.choice(LAST_EN)
        name = f"{first} {last}"
        title = rng.choice(TITLES_EN)
    slug = f"{first}.{last}".replace(" ", "").lower()
    # Deterministic fake contact — clearly synthetic domains
    email = f"{slug}.{rng.randint(1000,9999)}@synthetic-eval.example"
    phone = f"+9655{rng.randint(1000000, 9999999)}"
    return {
        "name": name,
        "title": title,
        "email": email,
        "phone": phone,
        "company": rng.choice(COMPANIES),
        "skills": ", ".join(rng.sample(SKILLS, k=4)),
    }


def record(
    *,
    doc_id: str,
    path: Path,
    category: str,
    source_id: str,
    notes: str,
    expected_ocr_policy: str,
    contains_real_pii: bool = False,
    pages: int | None = None,
) -> dict[str, Any]:
    page_count = pages
    if page_count is None:
        try:
            page_count = len(PdfReader(str(path)).pages)
        except Exception:
            page_count = 1
    return {
        "doc_id": doc_id,
        "filename": path.name,
        "rel_path": str(path.relative_to(EVID)),
        "sha256": sha256_file(path),
        "bytes": path.stat().st_size,
        "pages": page_count,
        "category": category,
        "source_id": source_id,
        "contains_real_pii": contains_real_pii,
        "synthetic": source_id.startswith("synthetic") or source_id == "wave0_synthetic",
        "expected_ocr_policy": expected_ocr_policy,
        "notes": notes,
        "created_at": utc_now(),
    }


def write_en_digital(path: Path, rng: random.Random, *, multipage: bool = False, font: str = "ArialUni") -> None:
    p = persona(rng)
    c = canvas.Canvas(str(path), pagesize=letter)
    w, h = letter
    c.setFont(font, 16)
    c.drawString(50, h - 60, p["name"])
    c.setFont(font, 11)
    c.drawString(50, h - 80, p["title"])
    c.drawString(50, h - 100, f"Email: {p['email']}")
    c.drawString(50, h - 116, f"Phone: {p['phone']}")
    c.drawString(50, h - 150, "EXPERIENCE")
    y = h - 170
    for i in range(3):
        c.drawString(50, y, f"{2018 + i}-202{i} {p['company']} — {p['title']}")
        y -= 16
        c.drawString(60, y, f"Delivered synthetic project {i+1} with measurable outcomes.")
        y -= 28
    c.drawString(50, y, f"SKILLS: {p['skills']}")
    if multipage:
        c.showPage()
        c.setFont(font, 12)
        c.drawString(50, h - 60, f"{p['name']} — page 2")
        c.drawString(50, h - 90, "EDUCATION")
        c.drawString(50, h - 110, "BSc Computer Science — Synthetic University 2014-2018")
        c.drawString(50, h - 140, "ADDITIONAL")
        for i in range(8):
            c.drawString(50, h - 160 - i * 16, f"Volunteer role {i+1}: corpus evaluation support.")
    c.save()


def write_ar_digital(path: Path, rng: random.Random) -> None:
    p = persona(rng, arabic=True)
    c = canvas.Canvas(str(path), pagesize=A4)
    w, h = A4
    c.setFont("NotoKufiBold", 16)
    c.drawRightString(w - 40, h - 60, ar(p["name"]))
    c.setFont("NotoKufi", 12)
    c.drawRightString(w - 40, h - 85, ar(p["title"]))
    c.setFont("ArialUni", 10)
    c.drawRightString(w - 40, h - 110, f"Email: {p['email']}")
    c.drawRightString(w - 40, h - 126, f"Phone: {p['phone']}")
    c.setFont("NotoKufi", 12)
    c.drawRightString(w - 40, h - 160, ar("الخبرة"))
    y = h - 185
    for i in range(3):
        c.drawRightString(w - 40, y, ar(f"{2019+i}-202{i} {p['company']}"))
        y -= 20
        c.drawRightString(w - 40, y, ar("ساهم في مشاريع تقييم المستندات الرقمية."))
        y -= 28
    c.drawRightString(w - 40, y, ar("المهارات") + f": {p['skills']}")
    c.save()


def write_bilingual(path: Path, rng: random.Random) -> None:
    pe = persona(rng)
    pa = persona(rng, arabic=True)
    c = canvas.Canvas(str(path), pagesize=A4)
    w, h = A4
    c.setFont("ArialUni", 14)
    c.drawString(40, h - 55, pe["name"])
    c.setFont("NotoKufiBold", 14)
    c.drawRightString(w - 40, h - 55, ar(pa["name"]))
    c.setFont("ArialUni", 11)
    c.drawString(40, h - 80, pe["title"])
    c.setFont("NotoKufi", 11)
    c.drawRightString(w - 40, h - 80, ar(pa["title"]))
    c.setFont("ArialUni", 10)
    c.drawString(40, h - 105, f"{pe['email']} | {pe['phone']}")
    c.drawString(40, h - 140, "EXPERIENCE / الخبرة")
    y = h - 165
    for i in range(3):
        c.setFont("ArialUni", 10)
        c.drawString(40, y, f"{2020+i}-202{i+1} {pe['company']}")
        y -= 16
        c.setFont("NotoKufi", 10)
        c.drawRightString(w - 40, y, ar("قيادة مبادرات الموارد البشرية عبر الحدود."))
        y -= 28
    c.setFont("ArialUni", 10)
    c.drawString(40, y, f"SKILLS: {pe['skills']}")
    c.save()


def write_multicolumn(path: Path, rng: random.Random, *, design_heavy: bool = False) -> None:
    p = persona(rng)
    c = canvas.Canvas(str(path), pagesize=letter)
    w, h = letter
    if design_heavy:
        c.setFillColorRGB(0.12, 0.22, 0.35)
        c.rect(0, 0, 180, h, fill=1, stroke=0)
        c.setFillColorRGB(1, 1, 1)
        c.setFont("ArialBlack", 14)
        c.drawString(20, h - 50, p["name"].split()[0])
        c.setFont("ArialNarrow", 10)
        c.drawString(20, h - 70, p["title"])
        c.drawString(20, h - 100, p["email"])
        c.drawString(20, h - 116, p["phone"])
        c.setFont("ArialNarrow", 9)
        for i, skill in enumerate(p["skills"].split(", ")):
            c.drawString(20, h - 160 - i * 14, f"• {skill}")
        c.setFillColorRGB(0.1, 0.1, 0.1)
        c.setFont("ArialUni", 12)
        c.drawString(200, h - 50, "EXPERIENCE")
        y = h - 75
        for i in range(4):
            c.setFont("ArialBlack", 10)
            c.drawString(200, y, f"{p['company']} ({2019+i})")
            y -= 14
            c.setFont("ArialUni", 9)
            c.drawString(200, y, "Owned routing evaluation workflows and OCR cost controls.")
            y -= 28
    else:
        c.setFont("ArialUni", 14)
        c.drawString(40, h - 50, p["name"])
        c.setFont("ArialUni", 10)
        c.drawString(40, h - 70, f"{p['email']} | {p['phone']}")
        c.setFont("ArialUni", 11)
        c.drawString(40, h - 110, "LEFT — Experience")
        c.drawString(320, h - 110, "RIGHT — Education")
        y = h - 135
        for i in range(4):
            c.drawString(40, y, f"{2018+i} {p['company']}")
            c.drawString(320, y, f"Course {i+1} — Synthetic Uni")
            y -= 22
    c.save()


def write_table_heavy(path: Path, rng: random.Random) -> None:
    p = persona(rng)
    c = canvas.Canvas(str(path), pagesize=letter)
    w, h = letter
    c.setFont("ArialUni", 14)
    c.drawString(40, h - 50, p["name"])
    c.setFont("ArialUni", 10)
    c.drawString(40, h - 70, f"{p['email']} | {p['phone']}")
    c.drawString(40, h - 100, "Compensation / Experience Matrix")
    rows = [["Year", "Role", "Company", "Focus"]]
    for i in range(6):
        rows.append([str(2019 + i), p["title"][:18], p["company"][:16], rng.choice(SKILLS)])
    x0, y0 = 40, h - 130
    col_w = [50, 140, 140, 120]
    for r, row in enumerate(rows):
        x = x0
        for ci, cell in enumerate(row):
            c.rect(x, y0 - r * 18 - 14, col_w[ci], 18, stroke=1, fill=0)
            c.setFont("Vera" if r == 0 else "ArialUni", 8 if r else 9)
            c.drawString(x + 3, y0 - r * 18 - 10, str(cell)[:22])
            x += col_w[ci]
    c.save()


def render_scan_image(
    lines: list[str],
    *,
    arabic: bool = False,
    rotate: int = 0,
    low_res: bool = False,
    compress_q: int = 35,
    blur: bool = False,
) -> Path:
    scale = 1 if low_res else 2
    w, h = (612, 792)
    img = Image.new("RGB", (w * scale, h * scale), (245, 245, 240))
    draw = ImageDraw.Draw(img)
    try:
        font = ImageFont.truetype(AR_FONT if arabic else EN_FONT, 22 if low_res else 28)
        title = ImageFont.truetype(AR_FONT_BOLD if arabic else EN_FONT, 30 if low_res else 36)
    except Exception:
        font = ImageFont.load_default()
        title = font
    y = 60 * scale
    for i, line in enumerate(lines):
        text = ar(line) if arabic else line
        f = title if i == 0 else font
        if arabic:
            bbox = draw.textbbox((0, 0), text, font=f)
            tw = bbox[2] - bbox[0]
            draw.text(((w * scale) - 40 * scale - tw, y), text, fill=(15, 15, 15), font=f)
        else:
            draw.text((40 * scale, y), text, fill=(15, 15, 15), font=f)
        y += (36 if i == 0 else 30) * scale
    if blur:
        img = img.filter(ImageFilter.GaussianBlur(radius=1.2))
    if rotate:
        img = img.rotate(rotate, expand=True, fillcolor=(245, 245, 240))
    if low_res:
        img = img.resize((max(200, w // 2), max(260, h // 2)), Image.Resampling.BILINEAR)
        img = img.resize((w, h), Image.Resampling.NEAREST)
    else:
        img = img.resize((w, h), Image.Resampling.LANCZOS)
    out = ARTIFACTS / f"scan-{hashlib.md5(''.join(lines).encode()).hexdigest()[:12]}-q{compress_q}-r{rotate}.jpg"
    img.convert("RGB").save(out, format="JPEG", quality=compress_q, optimize=True)
    return out


def write_image_pdf(path: Path, image_path: Path, *, pagesize=letter) -> None:
    c = canvas.Canvas(str(path), pagesize=pagesize)
    w, h = pagesize
    c.drawImage(str(image_path), 0, 0, width=w, height=h, preserveAspectRatio=True, anchor="c")
    c.save()


def write_scanned(path: Path, rng: random.Random, *, arabic: bool = False, rotate: int = 0, low_res: bool = False, compress_q: int = 28) -> None:
    p = persona(rng, arabic=arabic)
    if arabic:
        lines = [p["name"], p["title"], f"Email: {p['email']}", "خبرة في تحليل المستندات", "مهارات: برمجة وتحليل بيانات"]
    else:
        lines = [p["name"], p["title"], f"Email: {p['email']}", f"Phone: {p['phone']}", f"Skills: {p['skills']}", "Scanned synthetic CV page"]
    img = render_scan_image(lines, arabic=arabic, rotate=rotate, low_res=low_res, compress_q=compress_q, blur=low_res)
    write_image_pdf(path, img)


def write_mixed(path: Path, rng: random.Random) -> None:
    p = persona(rng)
    digital = ARTIFACTS / f"mixed-digital-{path.stem}.pdf"
    write_en_digital(digital, rng)
    scan = ARTIFACTS / f"mixed-scan-{path.stem}.pdf"
    write_scanned(scan, rng, compress_q=30)
    writer = PdfWriter()
    for src in (digital, scan):
        for page in PdfReader(str(src)).pages:
            writer.add_page(page)
    with path.open("wb") as f:
        writer.write(f)


def write_broken_encoding(path: Path, rng: random.Random) -> None:
    """Deliberate mojibake / broken Arabic proxy in an otherwise digital PDF."""
    p = persona(rng)
    c = canvas.Canvas(str(path), pagesize=letter)
    w, h = letter
    c.setFont("ArialUni", 14)
    c.drawString(50, h - 60, f"Broken Encoding CV - {p['name']}")
    c.setFont("ArialUni", 11)
    c.drawString(50, h - 90, f"Email: {p['email']}")
    c.drawString(50, h - 110, f"Phone: {p['phone']}")
    # Classic UTF-8 interpreted as Latin-1 style mojibake proxies
    c.drawString(50, h - 150, "Name mojibake: Ù†ÙˆØ±Ø©")
    c.drawString(50, h - 170, "Garbled Arabic proxy: ÃÑÃÓÇä ãÔÝÑ")
    c.drawString(50, h - 190, "Replacement stress: ���� corrupted glyphs")
    c.drawString(50, h - 220, "EXPERIENCE: encoding stress case for quality gates")
    c.drawString(50, h - 250, f"SKILLS: {p['skills']}")
    c.save()


def write_missing_font_proxy(path: Path, rng: random.Random) -> None:
    """CID/ToUnicode-ish stress: embed text with Symbol/ZapfDingbats + custom stream notes."""
    p = persona(rng)
    c = canvas.Canvas(str(path), pagesize=letter)
    w, h = letter
    c.setFont("ArialUni", 12)
    c.drawString(50, h - 50, f"CID/ToUnicode stress — {p['name']}")
    c.drawString(50, h - 70, f"Email: {p['email']}")
    # Use built-in Symbol to create non-semantic printable glyphs
    c.setFont("Symbol", 14)
    c.drawString(50, h - 120, "abgdezhqiklmnxoprstufcyw")
    c.setFont("ZapfDingbats", 14)
    c.drawString(50, h - 150, "abcdefghijklmnop")
    c.setFont("ArialUni", 10)
    c.drawString(50, h - 190, "Notes: /CID /Identity-H ToUnicode Identity-V proxy markers")
    c.drawString(50, h - 210, f"Company: {p['company']}")
    c.save()


def write_unusual_font_icons(path: Path, rng: random.Random) -> None:
    p = persona(rng)
    c = canvas.Canvas(str(path), pagesize=letter)
    w, h = letter
    c.setFont("ArialBlack", 18)
    c.drawString(50, h - 55, p["name"])
    c.setFont("ArialNarrow", 11)
    c.drawString(50, h - 75, p["title"])
    c.setFont("ZapfDingbats", 12)
    c.drawString(50, h - 100, "★★★★★")
    c.setFont("Vera", 10)
    c.drawString(50, h - 130, f"Email: {p['email']}")
    c.drawString(50, h - 146, f"Phone: {p['phone']}")
    c.setFont("ArialBlack", 11)
    c.drawString(50, h - 180, "SKILLS")
    c.setFont("Vera", 10)
    c.drawString(50, h - 200, p["skills"])
    c.setFont("Symbol", 10)
    c.drawString(50, h - 230, "qwerty")
    c.setFont("ArialUni", 10)
    c.drawString(50, h - 260, f"Experience at {p['company']}")
    c.save()


def build_corpus() -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    # --- Licence-approved external reuse: Wave 0 synthetic fixtures ---
    if WAVE0_FIXTURES.exists():
        for src in sorted(WAVE0_FIXTURES.glob("*.pdf")):
            dest = CORPUS / f"wave0_{src.name}"
            shutil.copy2(src, dest)
            cat = "wave0_reuse"
            expected = "depends"
            name = src.name
            if "scanned" in name or "passport" in name:
                expected = "needs_ocr_all"
                cat = "scanned_image_only_cv" if "scanned" in name else "identity_scanned"
            elif "mixed" in name:
                expected = "needs_ocr_partial"
                cat = "mixed_digital_scanned"
            elif "broken" in name:
                expected = "encoding_stress"
                cat = "broken_encoding"
            elif "ar_digital" in name:
                expected = "digital_accepted_or_poppler_ocr"
                cat = "arabic_digital_cv"
            elif "bilingual" in name:
                expected = "digital_accepted"
                cat = "bilingual_cv"
            elif "multicolumn" in name:
                expected = "digital_accepted"
                cat = "multicolumn_cv"
            elif "tounicode" in name:
                expected = "digital_accepted"
                cat = "cid_tounicode"
            elif name.startswith("cv_"):
                expected = "digital_accepted"
                cat = "english_digital_cv"
            elif "contract" in name or "labor" in name or "law" in name:
                expected = "non_cv_layout"
                cat = "contract_or_legal"
            records.append(
                record(
                    doc_id=f"wave0_{src.stem}",
                    path=dest,
                    category=cat,
                    source_id="wave0_synthetic",
                    notes="Reused Wave 0 synthetic/public fixture",
                    expected_ocr_policy=expected,
                )
            )

    # Public legal PDF (Kuwait MOJ Labor Law) — non-CV edge case, public government text
    if MOJ_LAW.exists():
        dest = CORPUS / "public_moj_kuwait_labor_law_excerpt.pdf"
        # Keep first 3 pages only to reduce size / avoid large redistribution
        reader = PdfReader(str(MOJ_LAW))
        writer = PdfWriter()
        for i, page in enumerate(reader.pages[:3]):
            writer.add_page(page)
        with dest.open("wb") as f:
            writer.write(f)
        records.append(
            record(
                doc_id="public_moj_labor_law_3p",
                path=dest,
                category="contract_or_legal",
                source_id="kuwait_moj_public_law",
                notes="Public Kuwait Labor Law PDF excerpt (3 pages) for non-CV layout",
                expected_ocr_policy="non_cv_layout",
                contains_real_pii=False,
            )
        )

    plans: list[tuple[str, int, str]] = [
        ("english_digital_cv", 120, "digital_accepted"),
        ("english_digital_multipage", 25, "digital_accepted"),
        ("arabic_digital_cv", 80, "digital_accepted_or_poppler_ocr"),
        ("bilingual_cv", 50, "digital_accepted"),
        ("multicolumn_cv", 30, "digital_accepted"),
        ("design_heavy_cv", 25, "digital_accepted"),
        ("table_heavy_cv", 25, "digital_accepted"),
        ("unusual_font_icon_cv", 20, "digital_accepted"),
        ("scanned_image_only_cv", 40, "needs_ocr_all"),
        ("scanned_arabic_cv", 15, "needs_ocr_all"),
        ("mixed_digital_scanned", 30, "needs_ocr_partial"),
        ("rotated_scan_cv", 15, "needs_ocr_all"),
        ("lowres_compressed_scan_cv", 20, "needs_ocr_all"),
        ("broken_encoding", 20, "encoding_stress"),
        ("cid_tounicode_missing_font", 20, "encoding_or_symbol_stress"),
    ]

    for category, count, expected in plans:
        for i in range(count):
            rng = random.Random(hash((category, i, "wave2")) & 0xFFFFFFFF)
            doc_id = f"syn_{category}_{i:03d}"
            path = CORPUS / f"{doc_id}.pdf"
            if category == "english_digital_cv":
                write_en_digital(path, rng, font=rng.choice(["ArialUni", "Vera", "ArialNarrow"]))
            elif category == "english_digital_multipage":
                write_en_digital(path, rng, multipage=True)
            elif category == "arabic_digital_cv":
                write_ar_digital(path, rng)
            elif category == "bilingual_cv":
                write_bilingual(path, rng)
            elif category == "multicolumn_cv":
                write_multicolumn(path, rng, design_heavy=False)
            elif category == "design_heavy_cv":
                write_multicolumn(path, rng, design_heavy=True)
            elif category == "table_heavy_cv":
                write_table_heavy(path, rng)
            elif category == "unusual_font_icon_cv":
                write_unusual_font_icons(path, rng)
            elif category == "scanned_image_only_cv":
                write_scanned(path, rng, compress_q=rng.randint(25, 45))
            elif category == "scanned_arabic_cv":
                write_scanned(path, rng, arabic=True, compress_q=30)
            elif category == "mixed_digital_scanned":
                write_mixed(path, rng)
            elif category == "rotated_scan_cv":
                write_scanned(path, rng, rotate=rng.choice([90, 180, 270]), compress_q=32)
            elif category == "lowres_compressed_scan_cv":
                write_scanned(path, rng, low_res=True, compress_q=rng.randint(12, 22))
            elif category == "broken_encoding":
                write_broken_encoding(path, rng)
            elif category == "cid_tounicode_missing_font":
                write_missing_font_proxy(path, rng)
            else:
                raise RuntimeError(category)
            records.append(
                record(
                    doc_id=doc_id,
                    path=path,
                    category=category,
                    source_id="synthetic_wave2_generated",
                    notes="Fully synthetic CV PDF with fake identifiers (@synthetic-eval.example)",
                    expected_ocr_policy=expected,
                    contains_real_pii=False,
                )
            )

    return records


def licence_ledger() -> list[dict[str, Any]]:
    return [
        {
            "source_id": "synthetic_wave2_generated",
            "dataset_name": "Wathefni Wave 2 Synthetic CV PDF Corpus",
            "source": "Generated offline in-repo via wave2-cv-pdf-corpus-build.py",
            "licence_or_terms": "Internal evaluation artifact; synthetic content owned/generated for Wathefni eval",
            "contains_real_personal_information": False,
            "commercial_or_internal_evaluation_permitted": True,
            "attribution_or_redistribution": "Do not publish as real CVs; fake @synthetic-eval.example contacts",
            "included": True,
            "exclusion_reason": None,
        },
        {
            "source_id": "wave0_synthetic",
            "dataset_name": "pdf-inspector Deep Eval Wave 0 fixtures",
            "source": "ops/evidence/pdf-inspector-deep-eval-wave0-20260804/fixtures",
            "licence_or_terms": "Synthetic fixtures generated for Wave 0; internal eval reuse",
            "contains_real_personal_information": False,
            "commercial_or_internal_evaluation_permitted": True,
            "attribution_or_redistribution": "Internal reuse OK",
            "included": True,
            "exclusion_reason": None,
        },
        {
            "source_id": "kuwait_moj_public_law",
            "dataset_name": "Kuwait Labor Law No. 6 of 2010 (MOJ public PDF excerpt)",
            "source": "Kuwait Ministry of Justice public legal publication (local evidence copy)",
            "licence_or_terms": "Public government legal text; used as non-CV layout edge case only",
            "contains_real_personal_information": False,
            "commercial_or_internal_evaluation_permitted": True,
            "attribution_or_redistribution": "Attribute Kuwait MOJ; redistribute only as public law text",
            "included": True,
            "exclusion_reason": None,
        },
        {
            "source_id": "doclaynet",
            "dataset_name": "DocLayNet",
            "source": "https://github.com/DS4SD/DocLayNet",
            "licence_or_terms": "CDLA-Permissive-1.0 — Use and Publish permitted with agreement notice on redistribution",
            "contains_real_personal_information": "Possible in source business documents; not profiled here",
            "commercial_or_internal_evaluation_permitted": True,
            "attribution_or_redistribution": "Provide CDLA-Permissive-1.0 text/link if publishing data",
            "included": False,
            "exclusion_reason": "Approved licence, but full PDF extra is multi-GB; not ingested this wave. Layout edge cases synthesized instead.",
        },
        {
            "source_id": "publaynet",
            "dataset_name": "PubLayNet",
            "source": "https://github.com/ibm-aur-nlp/publaynet (PMC OA commercial-use subset)",
            "licence_or_terms": "CDLA-Permissive-1.0 / PMC OA commercial-use collection provenance",
            "contains_real_personal_information": False,
            "commercial_or_internal_evaluation_permitted": True,
            "attribution_or_redistribution": "Scientific article pages; provide CDLA notice if redistributing",
            "included": False,
            "exclusion_reason": "Approved for non-CV layout use, but large download deferred; not required to hit 500 with synthetic CV coverage.",
        },
        {
            "source_id": "eramatch_synthetic",
            "dataset_name": "EraMatch CV Parsing Benchmark v3.0",
            "source": "https://www.kaggle.com/datasets/anasahmad25/cv-parsing-eramatch",
            "licence_or_terms": "Stated CC0 / synthetic LLM+template CVs",
            "contains_real_personal_information": False,
            "commercial_or_internal_evaluation_permitted": True,
            "attribution_or_redistribution": "CC0; attribution optional",
            "included": False,
            "exclusion_reason": "Licence appears OK (synthetic+CC0) but Kaggle download not used this wave; equivalent synthetic PDFs generated locally to avoid third-party retention.",
        },
        {
            "source_id": "opensporks_livecareer",
            "dataset_name": "opensporks/resumes (Hugging Face)",
            "source": "https://huggingface.co/datasets/opensporks/resumes",
            "licence_or_terms": "Labeled CC0-1.0, but provenance is scraped LiveCareer resume examples",
            "contains_real_personal_information": True,
            "commercial_or_internal_evaluation_permitted": False,
            "attribution_or_redistribution": "Excluded — scraped personal/example CVs; privacy risk despite CC0 copyright label",
            "included": False,
            "exclusion_reason": "Lawful internal use not established for scraped personal CV examples; user policy forbids identifiable CVs without explicit permitted use.",
        },
        {
            "source_id": "linkedin_google_personal_sites",
            "dataset_name": "LinkedIn / Google / personal website CVs",
            "source": "n/a",
            "licence_or_terms": "Not licensed for scraping",
            "contains_real_personal_information": True,
            "commercial_or_internal_evaluation_permitted": False,
            "attribution_or_redistribution": "Forbidden",
            "included": False,
            "exclusion_reason": "Explicitly out of scope per Wave 2 instructions.",
        },
    ]


def main() -> int:
    records = build_corpus()
    # Validate PDFs open
    valid = []
    invalid = []
    for r in records:
        path = EVID / r["rel_path"]
        try:
            n = len(PdfReader(str(path)).pages)
            assert n >= 1
            r["pages"] = n
            valid.append(r)
        except Exception as exc:
            r["error"] = str(exc)
            invalid.append(r)

    category_counts: dict[str, int] = {}
    for r in valid:
        category_counts[r["category"]] = category_counts.get(r["category"], 0) + 1

    ledger = licence_ledger()
    manifest = {
        "wave": "pdf_inspector_corpus_wave2",
        "created_at": utc_now(),
        "mode": "research_staging_offline",
        "paid_ocr_invoked": False,
        "production_intake": False,
        "target_min_valid_pdfs": 500,
        "valid_pdf_count": len(valid),
        "invalid_pdf_count": len(invalid),
        "category_counts": dict(sorted(category_counts.items())),
        "source_counts": {},
        "documents": valid,
        "invalid": invalid,
    }
    for r in valid:
        sid = r["source_id"]
        manifest["source_counts"][sid] = manifest["source_counts"].get(sid, 0) + 1

    (MANIFESTS / "corpus_manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False))
    (MANIFESTS / "licence_ledger.json").write_text(json.dumps(ledger, indent=2, ensure_ascii=False))
    # CSV-lite for quick scanning
    lines = ["doc_id,category,source_id,pages,sha256,expected_ocr_policy,filename"]
    for r in valid:
        lines.append(
            f"{r['doc_id']},{r['category']},{r['source_id']},{r['pages']},{r['sha256']},{r['expected_ocr_policy']},{r['filename']}"
        )
    (MANIFESTS / "corpus_manifest.csv").write_text("\n".join(lines) + "\n")

    print(json.dumps({
        "valid_pdf_count": len(valid),
        "invalid_pdf_count": len(invalid),
        "category_counts": category_counts,
        "source_counts": manifest["source_counts"],
        "target_met": len(valid) >= 500,
    }, indent=2))
    return 0 if len(valid) >= 500 and not invalid else 1


if __name__ == "__main__":
    raise SystemExit(main())
