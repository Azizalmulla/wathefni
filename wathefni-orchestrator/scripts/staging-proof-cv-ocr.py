#!/usr/bin/env python3
"""Staging proof for CV OCR upgrade — synthetic fixtures only.

Never reads production candidate CVs. Requires staging env + optional Mistral key.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def _make_text_pdf(path: Path, text: str) -> None:
    """Create a real text PDF via reportlab (required for Poppler digital path proof)."""
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas

    c = canvas.Canvas(str(path), pagesize=A4)
    # Helvetica cannot render Arabic glyphs; for Arabic fixtures also emit a
    # Latin transliteration line so pdftotext still recovers usable digital text,
    # while deterministic Arabic contact tests cover Arabic parsing separately.
    y = 800
    for line in text.splitlines():
        try:
            c.drawString(40, y, line[:110])
        except Exception:
            c.drawString(40, y, line.encode("ascii", "ignore").decode()[:110])
        y -= 16
        if y < 40:
            c.showPage()
            y = 800
    c.save()


def _make_image_cv(path: Path, text: str) -> None:
    from PIL import Image, ImageDraw

    img = Image.new("RGB", (1240, 1754), "white")
    draw = ImageDraw.Draw(img)
    y = 40
    for line in text.splitlines():
        draw.text((40, y), line, fill="black")
        y += 28
    img.save(path)


def _images_to_pdf(pngs: list[Path], dest: Path) -> bool:
    try:
        import img2pdf

        dest.write_bytes(img2pdf.convert(*[str(p) for p in pngs]))
        return dest.exists()
    except Exception:
        return False


def main() -> int:
    import cv_extraction as cv

    report: dict = {
        "model_pin": cv.MISTRAL_OCR_MODEL,
        "sdk_pin": cv.MISTRAL_SDK_PIN,
        "api_version": cv.MISTRAL_OCR_API_VERSION,
        "flag_mistral": cv.mistral_ocr_enabled(),
        "flag_rescue": cv.gpt_vision_rescue_enabled(),
        "mistral_key_present": bool(cv.mistral_api_key()),
        "poppler": {
            "pdftotext": bool(shutil.which("pdftotext")),
            "pdfinfo": bool(shutil.which("pdfinfo")),
            "pdftoppm": bool(shutil.which("pdftoppm")),
        },
        "cases": [],
        "privacy": {
            "prefer_base64_direct": True,
            "files_api_retention_note": "Mistral may retain uploaded files up to ~30 days unless deleted; we prefer base64 direct and delete uploads if used.",
            "production_cvs_sent": False,
        },
    }

    digital_text = (
        "Fatima Al-Sabah\n"
        "Email: fatima.proof@example.com\n"
        "Phone: +965 5123 4567\n"
        "Skills\n"
        "Recruiting, HRIS, interviewing, Arabic and English communication.\n"
        "Experience\n"
        "HR Coordinator at Example Co from January 2019 to Present.\n"
        "Education\n"
        "BA Business Administration, Kuwait University.\n"
    )
    arabic_text = (
        "Noura Khaled Al-Ajmi / نورة خالد العجمي\n"
        "Email: noura.proof@example.com\n"
        "Phone: 51234568\n"
        "Skills / المهارات\n"
        "Recruiting, talent management, bilingual communication.\n"
        "Experience / الخبرة\n"
        "HR Specialist since 15 March 2021 / أخصائية موارد بشرية منذ ١٥ مارس ٢٠٢١.\n"
        "Education / التعليم\n"
        "BA Business Administration.\n"
    )

    with tempfile.TemporaryDirectory(prefix="cv-ocr-proof-") as tmp:
        tmp_path = Path(tmp)
        digital_pdf = tmp_path / "digital.pdf"
        arabic_pdf = tmp_path / "arabic-digital.pdf"
        image_cv = tmp_path / "image-cv.png"
        _make_text_pdf(digital_pdf, digital_text)
        _make_text_pdf(arabic_pdf, arabic_text)
        _make_image_cv(image_cv, digital_text)

        # Case 1: clean digital PDF stays local
        t0 = time.perf_counter()
        digital = cv.extract_cv_document(digital_pdf, mime_type="application/pdf", company_code="PROOF")
        digital_ms = int((time.perf_counter() - t0) * 1000)
        report["cases"].append(
            {
                "name": "digital_pdf_local",
                "method": digital.method,
                "quality_ok": digital.quality_ok,
                "error": digital.error,
                "latency_ms": digital_ms,
                "stage": (digital.metadata or {}).get("stage"),
                "tier": (digital.metadata or {}).get("tier"),
                "provider": (digital.metadata or {}).get("provider"),
                "actual_request_model": (digital.metadata or {}).get("actual_request_model"),
                "billable_pages": (digital.metadata or {}).get("billable_pages"),
                "chars": len(digital.text or ""),
                "ocr_called": any(c.tier == "mistral_ocr" for c in digital.engine_calls),
            }
        )

        # Case 2: Arabic digital must not force OCR
        arabic = cv.extract_cv_document(arabic_pdf, mime_type="application/pdf", company_code="PROOF")
        report["cases"].append(
            {
                "name": "arabic_digital_no_ocr_trigger",
                "method": arabic.method,
                "quality_ok": arabic.quality_ok,
                "error": arabic.error,
                "ocr_called": any(c.tier == "mistral_ocr" for c in arabic.engine_calls),
                "arabic_ratio": max((p.arabic_ratio for p in arabic.page_assessments), default=None),
                "chars": len(arabic.text or ""),
            }
        )

        # Case 3: image CV — only if flag + key
        if cv.mistral_ocr_enabled() and cv.mistral_api_key():
            t0 = time.perf_counter()
            image = cv.extract_cv_document(image_cv, mime_type="image/png", company_code="PROOF")
            image_ms = int((time.perf_counter() - t0) * 1000)
            rescue = any(c.tier == "gpt_vision_rescue" for c in image.engine_calls)
            report["cases"].append(
                {
                    "name": "image_cv_mistral",
                    "method": image.method,
                    "quality_ok": image.quality_ok,
                    "error": image.error,
                    "latency_ms": image_ms,
                    "stage": (image.metadata or {}).get("stage"),
                    "tier": (image.metadata or {}).get("tier"),
                    "provider": (image.metadata or {}).get("provider"),
                    "actual_request_model": (image.metadata or {}).get("actual_request_model"),
                    "provider_response_model": (image.metadata or {}).get("provider_response_model"),
                    "provider_request_id": (image.metadata or {}).get("provider_request_id"),
                    "billable_pages": (image.metadata or {}).get("billable_pages"),
                    "estimated_cost_usd": (image.metadata or {}).get("estimated_cost_usd"),
                    "retention": (image.metadata or {}).get("retention"),
                    "rescue_used": rescue,
                    "chars": len(image.text or ""),
                }
            )
        else:
            report["cases"].append(
                {
                    "name": "image_cv_mistral",
                    "skipped": True,
                    "reason": "flag_or_key_missing",
                    "flag_mistral": cv.mistral_ocr_enabled(),
                    "mistral_key_present": bool(cv.mistral_api_key()),
                }
            )

        # Case 4: scanned-like PDF via pdftoppm image re-wrap
        if shutil.which("pdftoppm"):
            scan_dir = tmp_path / "scan"
            scan_dir.mkdir()
            subprocess.run(
                ["pdftoppm", "-png", "-r", "150", str(digital_pdf), str(scan_dir / "p")],
                check=False,
                capture_output=True,
            )
            pngs = sorted(scan_dir.glob("p*.png"))
            scanned_pdf = tmp_path / "scanned.pdf"
            built = bool(pngs) and _images_to_pdf(pngs, scanned_pdf)
            if built and cv.mistral_ocr_enabled() and cv.mistral_api_key():
                t0 = time.perf_counter()
                scanned = cv.extract_cv_document(scanned_pdf, mime_type="application/pdf", company_code="PROOF")
                report["cases"].append(
                    {
                        "name": "scanned_pdf_mistral",
                        "method": scanned.method,
                        "quality_ok": scanned.quality_ok,
                        "error": scanned.error,
                        "latency_ms": int((time.perf_counter() - t0) * 1000),
                        "stage": (scanned.metadata or {}).get("stage"),
                        "tier": (scanned.metadata or {}).get("tier"),
                        "actual_request_model": (scanned.metadata or {}).get("actual_request_model"),
                        "provider_response_model": (scanned.metadata or {}).get("provider_response_model"),
                        "billable_pages": (scanned.metadata or {}).get("billable_pages"),
                        "estimated_cost_usd": (scanned.metadata or {}).get("estimated_cost_usd"),
                        "pages_ocr": (scanned.metadata or {}).get("pages_ocr"),
                        "rescue_pages": (scanned.metadata or {}).get("pages_rescue"),
                        "retention": (scanned.metadata or {}).get("retention"),
                        "chars": len(scanned.text or ""),
                    }
                )
            elif built:
                # Even without Mistral, prove page detection classifies image-only pages.
                assessments = cv.assess_pdf_pages(scanned_pdf)
                report["cases"].append(
                    {
                        "name": "scanned_pdf_detection",
                        "pages": [asdict_page(p) for p in assessments],
                        "needs_ocr_pages": [p.page_number for p in assessments if p.disposition == "needs_ocr"],
                        "mistral_live": False,
                        "reason": "flag_or_key_missing",
                    }
                )
            else:
                report["cases"].append(
                    {
                        "name": "scanned_pdf_mistral",
                        "skipped": True,
                        "reason": "img2pdf_failed",
                    }
                )
        else:
            report["cases"].append(
                {
                    "name": "scanned_pdf_mistral",
                    "skipped": True,
                    "reason": "missing_pdftoppm",
                }
            )

        # Deterministic contacts proof
        contacts = cv.deterministic_contact_profile(arabic_text + "\n" + digital_text)
        report["deterministic_contacts"] = {
            "email": contacts.get("email"),
            "phone": contacts.get("phone"),
            "has_arabic_heading": any(h.get("lang") == "ar" for h in (contacts.get("headings") or [])),
            "dates": contacts.get("dates"),
        }

    print(json.dumps(report, ensure_ascii=False, indent=2, default=str))
    # Exit non-zero only on hard local failures (digital path broken).
    digital_case = next((c for c in report["cases"] if c.get("name") == "digital_pdf_local"), {})
    if digital_case.get("ocr_called"):
        return 2
    if digital_case.get("quality_ok") is not True and not digital_case.get("skipped"):
        # Digital local path should succeed when Poppler + reportlab fixtures are available.
        if report.get("poppler", {}).get("pdftotext"):
            return 3
    return 0


def asdict_page(p) -> dict:
    return {
        "page_number": p.page_number,
        "disposition": p.disposition,
        "reason": p.reason,
        "chars": p.char_count,
        "words": p.word_count,
    }


if __name__ == "__main__":
    raise SystemExit(main())
