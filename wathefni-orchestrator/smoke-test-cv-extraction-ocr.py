"""Smoke: CV extraction OCR upgrade (pure + mocked; no production CVs, no network OCR)."""

from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path
from unittest import mock

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


def main() -> int:
    print("    cv extraction — mistral-ocr-4-0 routing, arabic, cache, provenance")
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import cv_extraction as cv

    check("model pin is mistral-ocr-4-0", cv.MISTRAL_OCR_MODEL == "mistral-ocr-4-0")
    check("sdk pin is mistralai==2.6.0", cv.MISTRAL_SDK_PIN == "mistralai==2.6.0")
    check("never uses mistral-ocr-latest constant", "mistral-ocr-latest" not in cv.MISTRAL_OCR_MODEL)

    # Arabic / bilingual deterministic extraction
    sample = (
        "أحمد علي الكندري\n"
        "البريد: candidate\u200f@example.com\n"
        "هاتف: ٠٩٦٥٥١٢٣٤٥٦٧\n"
        "www.example.com/cv\n"
        "المهارات\n"
        "Python, SQL\n"
        "الخبرة\n"
        "عمل من ١٥ يناير ٢٠٢٠ إلى الآن\n"
    )
    check("arabic-indic digits normalize", cv.normalize_digits("٠١٢٣٤٥٦٧٨٩") == "0123456789")
    check("persian digits normalize", cv.normalize_digits("۰۱۲۳۴۵۶۷۸۹") == "0123456789")
    emails = cv.extract_emails(sample)
    check("email inside RTL marks", bool(emails) and emails[0]["value"] == "candidate@example.com")
    phones = cv.extract_kuwait_phones(sample)
    check("kuwait phone from arabic digits", bool(phones) and phones[0]["value"] == "96551234567")
    urls = cv.extract_urls(sample)
    check("url extracted", bool(urls) and "example.com" in urls[0]["value"])
    headings = cv.detect_headings(sample)
    check("arabic headings detected", any(h.get("lang") == "ar" for h in headings))
    dates = cv.parse_bilingual_dates(sample)
    check("arabic month date parsed", any(d.get("iso") == "2020-01-15" for d in dates))

    # Arabic alone must NOT be treated as OCR trigger
    arabic_cv = (
        "سارة محمد العتيبي\n"
        "ملخص مهني عن خبرة في الموارد البشرية والتوظيف في الكويت.\n"
        "المهارات تشمل التواصل وإدارة المقابلات وتقييم المرشحين.\n"
        "التعليم بكالوريوس إدارة أعمال من جامعة الكويت.\n"
        "اللغات العربية والإنجليزية.\n"
        "خبرة عملية لأكثر من خمس سنوات في بيئة عمل ثنائية اللغة.\n"
    )
    usable, reason = cv.page_text_usable(arabic_cv)
    check("arabic-only digital text accepted locally", usable is True and reason == "accepted_local", reason)

    # Quality gates
    check("empty fails quality", cv.cv_text_quality_ok("") is False)
    check("short fails quality", cv.cv_text_quality_ok("hello world") is False)
    check("good bilingual passes quality", cv.cv_text_quality_ok(arabic_cv + "\n" + sample) is True)

    # Human authority never overwritten
    existing = {
        "email": "human@verified.com",
        "field_provenance": {
            "email": {"authority_status": "human_verified", "value": "human@verified.com"},
        },
    }
    incoming = {"email": "ocr@machine.com", "name": "New Name", "field_provenance": {}}
    preserved = cv.preserve_human_fields(existing, incoming)
    check("human_verified email preserved", preserved.get("email") == "human@verified.com")
    check("non-protected field can update", preserved.get("name") == "New Name")

    # Cache key stability
    key1 = cv.build_cache_key(
        content_sha256="abc",
        page_hashes=["p1", "p2"],
        provider="mistral",
        ocr_model=cv.MISTRAL_OCR_MODEL,
        api_version=cv.MISTRAL_OCR_API_VERSION,
        extraction_options=cv.default_extraction_options(),
    )
    key2 = cv.build_cache_key(
        content_sha256="abc",
        page_hashes=["p1", "p2"],
        provider="mistral",
        ocr_model=cv.MISTRAL_OCR_MODEL,
        api_version=cv.MISTRAL_OCR_API_VERSION,
        extraction_options=cv.default_extraction_options(),
    )
    key3 = cv.build_cache_key(
        content_sha256="abc",
        page_hashes=["p1", "p2"],
        provider="mistral",
        ocr_model="mistral-ocr-latest",
        api_version=cv.MISTRAL_OCR_API_VERSION,
        extraction_options=cv.default_extraction_options(),
    )
    check("cache key stable", key1 == key2)
    check("cache key changes with model", key1 != key3)

    # Flag defaults OFF
    os.environ.pop("WATHEFNI_CV_MISTRAL_OCR", None)
    check("mistral OCR default off", cv.mistral_ocr_enabled() is False)

    # Page assessment routing with mocked poppler helpers
    with tempfile.TemporaryDirectory() as tmp:
        pdf_path = Path(tmp) / "mixed.pdf"
        pdf_path.write_bytes(b"%PDF-1.4 fake")

        pages = [
            cv.PageAssessment(1, 0, arabic_cv, cv.sha256_text(arabic_cv), "accepted_local", "accepted_local", len(arabic_cv), 40, 0.9),
            cv.PageAssessment(2, 1, "", cv.sha256_text("empty:2"), "needs_ocr", "image_only_page", 0, 0, 0.0),
        ]

        def fake_assess(_path: Path):
            return pages

        ocr_calls: list[list[int]] = []

        def fake_ocr(path: Path, page_indexes: list[int]):
            ocr_calls.append(list(page_indexes))
            meta = cv.EngineCallMeta(
                stage="ocr",
                tier="mistral_ocr",
                provider="mistral",
                actual_request_model=cv.MISTRAL_OCR_MODEL,
                provider_response_model=cv.MISTRAL_OCR_MODEL,
                latency_ms=12,
                billable_pages=1,
                estimated_cost_usd=0.004,
                pages=page_indexes,
                quality_ok=True,
                retention="base64_direct_no_files_api",
            )
            return {2: "Scanned page text with enough words for quality gate checks here and more."}, [], meta

        os.environ["WATHEFNI_CV_MISTRAL_OCR"] = "true"
        with mock.patch.object(cv, "assess_pdf_pages", fake_assess), mock.patch.object(
            cv, "extract_pdf_pages_with_mistral", fake_ocr
        ):
            result = cv.extract_cv_document(pdf_path, mime_type="application/pdf", company_code="SMOKE")
        check("OCR only failed page indexes", ocr_calls == [[1]], str(ocr_calls))
        check("mixed PDF keeps local page text", "سارة" in result.text and "Scanned page" in result.text)
        check("metadata has real stage/tier/provider/models", result.metadata.get("actual_request_model") == cv.MISTRAL_OCR_MODEL)
        check("billable pages recorded", result.metadata.get("billable_pages") == 1)

        # Flag off → scanned pages do not call OCR
        os.environ["WATHEFNI_CV_MISTRAL_OCR"] = "false"
        ocr_calls.clear()
        with mock.patch.object(cv, "assess_pdf_pages", fake_assess), mock.patch.object(
            cv, "extract_pdf_pages_with_mistral", fake_ocr
        ):
            blocked = cv.extract_cv_document(
                pdf_path, mime_type="application/pdf", company_code="SMOKE"
            )
        check("OCR skipped when flag off", ocr_calls == [] and blocked.error == "ocr_required_mistral_disabled")
        missing_tenant = cv.extract_cv_document(pdf_path, mime_type="application/pdf")
        check(
            "missing tenant fails closed",
            missing_tenant.error == "tenant_scope_required" and missing_tenant.text == "",
        )

    # Cost estimate
    check("cost estimate $4/1000 pages", cv.estimate_mistral_cost(1) == 0.004)

    # Engine call meta shape (replaces gpt-5.4-vision label)
    meta = cv.EngineCallMeta(
        stage="vision_rescue",
        tier="gpt_vision_rescue",
        provider="openai-sse",
        actual_request_model="gpt-5.4",
        provider_response_model="gpt-5.4",
    ).to_dict()
    check("meta has stage", "stage" in meta)
    check("meta has tier", "tier" in meta)
    check("meta has provider", "provider" in meta)
    check("meta has actual_request_model", meta["actual_request_model"] == "gpt-5.4")
    check("meta has provider_response_model", meta["provider_response_model"] == "gpt-5.4")
    check("no gpt-5.4-vision label", "gpt-5.4-vision" not in json.dumps(meta))

    print(f"    summary: {PASS} passed, {FAIL} failed")
    return 1 if FAIL else 0


if __name__ == "__main__":
    raise SystemExit(main())
