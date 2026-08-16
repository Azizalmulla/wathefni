#!/usr/bin/env python3
"""Build labeled synthetic Kuwait-style contracts & compliance corpus (Wave 1)."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageFont

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "ops/evidence/kuwait-gcc-contracts-wave1-corpus-20260804"
# Reuse identity corpus images by reference where possible
IDENTITY_CORPUS = ROOT / "ops/evidence/identity-wave1-corpus-20260804"


FIXTURES: list[dict[str, Any]] = [
    {
        "id": "contract_bilingual_digital_01",
        "document_type": "employment_contract",
        "lang": "bilingual",
        "variant": "scan",
        "country_code": "KW",
        "employee_name_ar": "أحمد عبدالله الكندري",
        "employee_name_en": "AHMAD ABDULLAH ALKANDARI",
        "employer_legal_name_en": "WATHEFNI TRADING COMPANY W.L.L.",
        "employer_legal_name_ar": "شركة الوثفني للتجارة ذ.م.م",
        "job_title": "HR Specialist",
        "contract_type": "unlimited",
        "contract_start_date": "2024-01-15",
        "contract_end_date": None,
        "probation_period": "100 days",
        "salary_amount": 850.0,
        "salary_currency": "KWD",
        "allowances": "Transport 50 KWD",
        "work_location": "Kuwait City",
        "working_hours": "8 hours/day",
        "weekly_rest_days": "Friday",
        "annual_leave_entitlement": "30 days",
        "notice_period": "30 days",
        "employee_signature_status": "signed",
        "employer_signature_status": "signed",
        "document_number": "CTR-2024-0011",
    },
    {
        "id": "contract_ar_lowres_unsigned_01",
        "document_type": "employment_contract",
        "lang": "arabic",
        "variant": "low_resolution",
        "country_code": "KW",
        "employee_name_ar": "فاطمة حسين العتيبي",
        "employee_name_en": None,
        "employer_legal_name_en": None,
        "employer_legal_name_ar": "شركة الوثفني",
        "job_title": "محاسب",
        "contract_type": "fixed",
        "contract_start_date": "2023-06-01",
        "contract_end_date": "2025-05-31",
        "probation_period": "90 يوم",
        "salary_amount": 700.0,
        "salary_currency": "KWD",
        "employee_signature_status": "unsigned",
        "employer_signature_status": "signed",
        "document_number": "عقد-7788",
    },
    {
        "id": "contract_en_rotated_conflict_01",
        "document_type": "employment_contract",
        "lang": "english",
        "variant": "rotated",
        "country_code": "KW",
        "employee_name_ar": None,
        "employee_name_en": "SARA NASSER ALMUTAIRI",
        "employer_legal_name_en": "AL MURQAB SERVICES",
        "job_title": "Operations Lead",
        "contract_start_date": "2022-03-01",
        "contract_end_date": "2026-02-28",
        "salary_amount": 1200.0,
        "salary_currency": "KWD",
        "employee_signature_status": "signed",
        "employer_signature_status": "unclear",
        "document_number": "CTR-EN-4421",
        "notes": "near_expiry_relative_to_synthetic_label_only",
    },
    {
        "id": "education_cert_bilingual_01",
        "document_type": "education_cert",
        "lang": "bilingual",
        "variant": "scan",
        "country_code": "KW",
        "employee_or_holder_ar": "يوسف سالم الشمري",
        "employee_or_holder_en": "YOUSEF SALEM ALSHAMMARI",
        "issuing_authority": "Kuwait University",
        "qualification_or_category": "Bachelor of Business",
        "document_number": "EDU-2019-8899",
        "issue_date": "2019-06-20",
        "expiry_date": None,
        "employer_or_sponsor": None,
    },
    {
        "id": "education_cert_en_mobile_01",
        "document_type": "education_cert",
        "lang": "english",
        "variant": "mobile_photo",
        "country_code": "KW",
        "employee_or_holder_en": "LAYLA HASSAN ALQALLAF",
        "issuing_authority": "Attested Ministry of Higher Education",
        "qualification_or_category": "Diploma in Accounting",
        "document_number": "ATT-2021-3311",
        "issue_date": "2021-09-01",
        "expiry_date": None,
    },
    {
        "id": "wrong_category_passport_as_contract_01",
        "document_type": "employment_contract",
        "expected_verify_fail": True,
        "actual_content_type": "passport",
        "lang": "english",
        "variant": "scan",
        "country_code": "KW",
        "reuse_identity_id": "passport_en_01",
        "document_number": "P1234567",
        "employee_name_en": "MOHAMMED RASHID ALHAJRI",
    },
]


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_font(size: int) -> ImageFont.ImageFont:
    for path in (
        "/System/Library/Fonts/Supplemental/Arial Unicode.ttf",
        "/System/Library/Fonts/Supplemental/Arial.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ):
        try:
            return ImageFont.truetype(path, size=size)
        except Exception:
            continue
    return ImageFont.load_default()


def render(label: dict[str, Any]) -> Image.Image:
    w, h = 1100, 780
    img = Image.new("RGB", (w, h), (248, 250, 252))
    draw = ImageDraw.Draw(img)
    draw.rectangle([16, 16, w - 16, h - 16], outline=(20, 50, 90), width=3)
    font_t = load_font(32)
    font = load_font(24)
    y = 36
    title = {
        "employment_contract": "EMPLOYMENT CONTRACT / عقد العمل",
        "education_cert": "EDUCATION CERTIFICATE / شهادة علمية",
    }.get(label["document_type"], label["document_type"].upper())
    draw.text((40, y), title, fill=(10, 30, 70), font=font_t)
    y += 56
    skip = {"id", "lang", "variant", "reuse_identity_id", "expected_verify_fail", "actual_content_type", "notes"}
    for key, value in label.items():
        if key in skip or value is None:
            continue
        draw.text((48, y), f"{key}: {value}", fill=(20, 20, 20), font=font)
        y += 34
        if y > h - 100:
            break
    draw.rectangle([40, h - 80, w - 40, h - 36], fill=(30, 30, 30))
    draw.text((50, h - 70), f"SYNTH/{label['id']}", fill=(230, 230, 230), font=font)
    return img


def apply_variant(img: Image.Image, variant: str) -> Image.Image:
    if variant == "mobile_photo":
        return ImageEnhance.Contrast(img).enhance(1.1).filter(ImageFilter.GaussianBlur(0.5))
    if variant == "low_resolution":
        small = img.resize((img.width // 4, img.height // 4))
        return small.resize(img.size, Image.Resampling.NEAREST)
    if variant == "rotated":
        return img.rotate(10, expand=True, fillcolor=(200, 200, 200))
    return img


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "images").mkdir(parents=True, exist_ok=True)
    rows: list[dict[str, Any]] = []

    # Reference identity fixtures for cross-channel / wrong-category cases
    identity_labels = []
    if (IDENTITY_CORPUS / "labels.jsonl").exists():
        for line in (IDENTITY_CORPUS / "labels.jsonl").read_text(encoding="utf-8").splitlines():
            if line.strip():
                identity_labels.append(json.loads(line))

    for label in FIXTURES:
        if label.get("reuse_identity_id"):
            src = next(r for r in identity_labels if r["id"] == label["reuse_identity_id"])
            # copy bytes into this corpus for self-contained qualify
            src_path = Path(src["absolute_path"])
            dest = OUT / "images" / f"{label['id']}.png"
            dest.write_bytes(src_path.read_bytes())
            path = dest
        else:
            img = apply_variant(render(label), label["variant"])
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

    # Pointers to identity corpus for shared-path identity qualify
    for ident in identity_labels:
        if ident["document_type"] not in {"civil_id", "passport", "residency", "work_permit", "medical"}:
            continue
        # residency in identity corpus
        rows.append(
            {
                "id": f"identity_ref_{ident['id']}",
                "document_type": "residence" if ident["document_type"] == "residency" else ident["document_type"],
                "identity_delegate": True,
                "source_identity_id": ident["id"],
                "absolute_path": ident["absolute_path"],
                "path": ident["path"],
                "content_sha256": ident["content_sha256"],
                "lang": ident.get("lang"),
                "variant": ident.get("variant"),
                "side": ident.get("side"),
                "document_number": ident.get("document_number"),
                "full_name_ar": ident.get("full_name_ar"),
                "full_name_en": ident.get("full_name_en"),
                "expiry_date": ident.get("expiry_date"),
                "issue_date": ident.get("issue_date"),
                "country_code": "KW",
                "synthetic": True,
                "created_at": utc_now(),
            }
        )

    with (OUT / "labels.jsonl").open("w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")

    manifest = {
        "corpus_id": "kuwait-gcc-contracts-wave1-20260804",
        "created_at": utc_now(),
        "count": len(rows),
        "structuring_fixtures": sum(1 for r in rows if not r.get("identity_delegate")),
        "identity_delegate_refs": sum(1 for r in rows if r.get("identity_delegate")),
        "note": "Synthetic anonymized Kuwait-style fixtures; not real customer documents.",
    }
    (OUT / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(manifest, indent=2), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
