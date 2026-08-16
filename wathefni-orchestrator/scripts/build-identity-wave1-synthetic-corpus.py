#!/usr/bin/env python3
"""Build labeled synthetic/anonymized identity documents for Wave 1 qualification.

Covers Arabic, English, bilingual; scans/mobile/rotated/low-res; Civil ID front/back;
passport; residency; work permit; medical certificate. No real PII.
"""

from __future__ import annotations

import hashlib
import json
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageEnhance, ImageFont, ImageFilter

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "ops/evidence/identity-wave1-corpus-20260804"
LABELS = OUT / "labels.jsonl"


FIXTURES: list[dict[str, Any]] = [
    {
        "id": "civil_id_front_bilingual_01",
        "document_type": "civil_id",
        "side": "front",
        "lang": "bilingual",
        "variant": "scan",
        "full_name_ar": "أحمد عبدالله محمد الكندري",
        "full_name_en": "AHMAD ABDULLAH MOHAMMAD ALKANDARI",
        "document_number": "289123456789",
        "nationality": "Kuwaiti",
        "date_of_birth": "1989-03-14",
        "issue_date": "2022-01-10",
        "expiry_date": "2032-01-09",
        "employer_or_sponsor": None,
        "document_relationship": "civil_id_front",
    },
    {
        "id": "civil_id_back_bilingual_01",
        "document_type": "civil_id",
        "side": "back",
        "lang": "bilingual",
        "variant": "scan",
        "full_name_ar": "أحمد عبدالله محمد الكندري",
        "full_name_en": "AHMAD ABDULLAH MOHAMMAD ALKANDARI",
        "document_number": "289123456789",
        "nationality": "Kuwaiti",
        "date_of_birth": "1989-03-14",
        "issue_date": "2022-01-10",
        "expiry_date": "2032-01-09",
        "employer_or_sponsor": None,
        "document_relationship": "civil_id_back_of:civil_id_front_bilingual_01",
    },
    {
        "id": "civil_id_front_ar_mobile_01",
        "document_type": "civil_id",
        "side": "front",
        "lang": "arabic",
        "variant": "mobile_photo",
        "full_name_ar": "فاطمة حسين علي العتيبي",
        "full_name_en": None,
        "document_number": "291045678901",
        "nationality": "كويتي",
        "date_of_birth": "1991-07-22",
        "issue_date": "2021-05-01",
        "expiry_date": "2031-04-30",
        "employer_or_sponsor": None,
        "document_relationship": "civil_id_front",
    },
    {
        "id": "civil_id_front_en_lowres_01",
        "document_type": "civil_id",
        "side": "front",
        "lang": "english",
        "variant": "low_resolution",
        "full_name_ar": None,
        "full_name_en": "SARA NASSER ALMUTAIRI",
        "document_number": "294112233445",
        "nationality": "Kuwaiti",
        "date_of_birth": "1994-11-02",
        "issue_date": "2020-09-15",
        "expiry_date": "2030-09-14",
        "employer_or_sponsor": None,
        "document_relationship": "civil_id_front",
    },
    {
        "id": "civil_id_front_rotated_01",
        "document_type": "civil_id",
        "side": "front",
        "lang": "bilingual",
        "variant": "rotated",
        "full_name_ar": "يوسف سالم فهد الشمري",
        "full_name_en": "YOUSEF SALEM FAHAD ALSHAMMARI",
        "document_number": "287556677889",
        "nationality": "Kuwaiti",
        "date_of_birth": "1987-12-01",
        "issue_date": "2019-03-20",
        "expiry_date": "2029-03-19",
        "employer_or_sponsor": None,
        "document_relationship": "civil_id_front",
    },
    {
        "id": "passport_en_01",
        "document_type": "passport",
        "side": "single",
        "lang": "english",
        "variant": "scan",
        "full_name_ar": None,
        "full_name_en": "MOHAMMED RASHID ALHAJRI",
        "document_number": "P1234567",
        "nationality": "KUWAITI",
        "date_of_birth": "1985-06-18",
        "issue_date": "2018-08-01",
        "expiry_date": "2028-07-31",
        "employer_or_sponsor": None,
        "document_relationship": "standalone",
    },
    {
        "id": "passport_bilingual_mobile_01",
        "document_type": "passport",
        "side": "single",
        "lang": "bilingual",
        "variant": "mobile_photo",
        "full_name_ar": "نورة خالد إبراهيم الصباح",
        "full_name_en": "NOURA KHALED IBRAHIM ALSABAH",
        "document_number": "N9988776",
        "nationality": "KUWAITI / كويتي",
        "date_of_birth": "1992-04-09",
        "issue_date": "2023-01-12",
        "expiry_date": "2033-01-11",
        "employer_or_sponsor": None,
        "document_relationship": "standalone",
    },
    {
        "id": "residency_bilingual_01",
        "document_type": "residency",
        "side": "single",
        "lang": "bilingual",
        "variant": "scan",
        "full_name_ar": "راجيش كومار شارما",
        "full_name_en": "RAJESH KUMAR SHARMA",
        "document_number": "RES-778899",
        "nationality": "Indian",
        "date_of_birth": "1988-02-25",
        "issue_date": "2024-01-01",
        "expiry_date": "2026-12-31",
        "employer_or_sponsor": "WATHEFNI TRADING CO",
        "document_relationship": "standalone",
    },
    {
        "id": "work_permit_en_01",
        "document_type": "work_permit",
        "side": "single",
        "lang": "english",
        "variant": "scan",
        "full_name_ar": None,
        "full_name_en": "JUAN CARLOS MENDOZA",
        "document_number": "WP-445566",
        "nationality": "Filipino",
        "date_of_birth": "1990-09-30",
        "issue_date": "2024-06-01",
        "expiry_date": "2025-05-31",
        "employer_or_sponsor": "AL MURQAB SERVICES",
        "document_relationship": "standalone",
    },
    {
        "id": "work_permit_ar_lowres_01",
        "document_type": "work_permit",
        "side": "single",
        "lang": "arabic",
        "variant": "low_resolution",
        "full_name_ar": "محمد أنور حسين",
        "full_name_en": None,
        "document_number": "تصريح-112233",
        "nationality": "مصري",
        "date_of_birth": "1986-01-15",
        "issue_date": "2023-11-01",
        "expiry_date": "2024-10-31",
        "employer_or_sponsor": "شركة الوثفني",
        "document_relationship": "standalone",
    },
    {
        "id": "medical_en_01",
        "document_type": "medical",
        "side": "single",
        "lang": "english",
        "variant": "scan",
        "full_name_ar": None,
        "full_name_en": "LAYLA HASSAN ALQALLAF",
        "document_number": "MED-2024-8899",
        "nationality": "Kuwaiti",
        "date_of_birth": "1995-08-08",
        "issue_date": "2024-03-01",
        "expiry_date": "2025-02-28",
        "employer_or_sponsor": None,
        "document_relationship": "standalone",
    },
    {
        "id": "medical_bilingual_rotated_01",
        "document_type": "medical",
        "side": "single",
        "lang": "bilingual",
        "variant": "rotated",
        "full_name_ar": "خالد فهد العازمي",
        "full_name_en": "KHALED FAHAD ALAZEMI",
        "document_number": "MED-2023-4411",
        "nationality": "Kuwaiti",
        "date_of_birth": "1983-05-19",
        "issue_date": "2023-10-10",
        "expiry_date": "2024-10-09",
        "employer_or_sponsor": None,
        "document_relationship": "standalone",
    },
]


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_font(size: int, arabic: bool = False) -> ImageFont.ImageFont:
    candidates = []
    if arabic:
        candidates.extend(
            [
                "/System/Library/Fonts/Supplemental/Arial Unicode.ttf",
                "/System/Library/Fonts/GeezaPro.ttc",
                "/Library/Fonts/Arial Unicode.ttf",
                "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
                "/usr/share/fonts/truetype/noto/NotoSansArabic-Regular.ttf",
                "/usr/share/fonts/opentype/noto/NotoSansArabic-Regular.ttf",
            ]
        )
    candidates.extend(
        [
            "/System/Library/Fonts/Supplemental/Arial.ttf",
            "/System/Library/Fonts/Helvetica.ttc",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
            "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
        ]
    )
    for path in candidates:
        try:
            return ImageFont.truetype(path, size=size)
        except Exception:
            continue
    return ImageFont.load_default()


def title_for(doc_type: str, side: str, lang: str) -> str:
    titles = {
        "civil_id": {
            "arabic": "البطاقة المدنية",
            "english": "CIVIL ID CARD",
            "bilingual": "CIVIL ID / البطاقة المدنية",
        },
        "passport": {
            "arabic": "جواز السفر",
            "english": "PASSPORT",
            "bilingual": "PASSPORT / جواز السفر",
        },
        "residency": {
            "arabic": "إقامة",
            "english": "RESIDENCY PERMIT",
            "bilingual": "RESIDENCY / إقامة",
        },
        "work_permit": {
            "arabic": "تصريح عمل",
            "english": "WORK PERMIT",
            "bilingual": "WORK PERMIT / تصريح عمل",
        },
        "medical": {
            "arabic": "شهادة طبية",
            "english": "MEDICAL CERTIFICATE",
            "bilingual": "MEDICAL / شهادة طبية",
        },
    }
    base = titles.get(doc_type, {}).get(lang) or doc_type.upper()
    if side in {"front", "back"}:
        return f"{base} ({side.upper()})"
    return base


def render_card(label: dict[str, Any]) -> Image.Image:
    w, h = 1000, 640
    bg = (245, 248, 252) if label["document_type"] != "passport" else (250, 245, 235)
    img = Image.new("RGB", (w, h), bg)
    draw = ImageDraw.Draw(img)
    draw.rectangle([20, 20, w - 20, h - 20], outline=(30, 60, 110), width=3)
    font_title = load_font(34, arabic=True)
    font = load_font(26, arabic=True)
    font_sm = load_font(22, arabic=True)

    y = 40
    draw.text((40, y), title_for(label["document_type"], label["side"], label["lang"]), fill=(20, 40, 80), font=font_title)
    y += 60
    rows = [
        ("Document Type", label["document_type"]),
        ("Side", label["side"]),
        ("Name (AR)", label.get("full_name_ar")),
        ("Name (EN)", label.get("full_name_en")),
        ("Document No", label.get("document_number")),
        ("Nationality", label.get("nationality")),
        ("Date of Birth", label.get("date_of_birth")),
        ("Issue Date", label.get("issue_date")),
        ("Expiry Date", label.get("expiry_date")),
        ("Employer/Sponsor", label.get("employer_or_sponsor")),
    ]
    for key, value in rows:
        if value is None:
            continue
        draw.text((50, y), f"{key}: {value}", fill=(15, 15, 15), font=font if "AR" in key else font_sm)
        y += 42

    # Fake MRZ / barcode band for OCR texture
    draw.rectangle([40, h - 90, w - 40, h - 40], fill=(30, 30, 30))
    draw.text(
        (50, h - 78),
        f"SYNTH/{label['id']}/{label['document_number']}",
        fill=(230, 230, 230),
        font=font_sm,
    )
    return img


def apply_variant(img: Image.Image, variant: str) -> Image.Image:
    if variant == "mobile_photo":
        img = ImageEnhance.Brightness(img).enhance(0.92)
        img = ImageEnhance.Contrast(img).enhance(1.15)
        img = img.filter(ImageFilter.GaussianBlur(radius=0.6))
        # slight perspective-ish crop
        return img.crop((12, 18, img.width - 8, img.height - 10)).resize(img.size)
    if variant == "low_resolution":
        small = img.resize((img.width // 4, img.height // 4), Image.Resampling.BILINEAR)
        return small.resize(img.size, Image.Resampling.NEAREST)
    if variant == "rotated":
        return img.rotate(12, expand=True, fillcolor=(200, 200, 200))
    # scan
    return ImageEnhance.Sharpness(img).enhance(1.2)


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "images").mkdir(parents=True, exist_ok=True)
    rows: list[dict[str, Any]] = []
    for label in FIXTURES:
        img = apply_variant(render_card(label), label["variant"])
        path = OUT / "images" / f"{label['id']}.png"
        img.save(path, format="PNG")
        sha = hashlib.sha256(path.read_bytes()).hexdigest()
        row = {
            **label,
            "path": str(path.relative_to(ROOT)),
            "absolute_path": str(path),
            "content_sha256": sha,
            "synthetic": True,
            "anonymized": True,
            "created_at": utc_now(),
        }
        rows.append(row)
        print(f"wrote {path.name}", flush=True)

    with LABELS.open("w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")

    manifest = {
        "corpus_id": "identity-wave1-synthetic-20260804",
        "created_at": utc_now(),
        "count": len(rows),
        "document_types": sorted({r["document_type"] for r in rows}),
        "variants": sorted({r["variant"] for r in rows}),
        "langs": sorted({r["lang"] for r in rows}),
        "labels_path": str(LABELS.relative_to(ROOT)),
        "note": "Synthetic anonymized fixtures only; not real customer documents.",
    }
    (OUT / "manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps(manifest, indent=2), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
