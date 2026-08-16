#!/usr/bin/env python3
"""Smoke: Onboarding Document Validation Parity (soft/hard) — no live Mistral required."""

from __future__ import annotations

import os
import sys
from datetime import date, timedelta

import onboarding_doc_validation_parity as v


def check(name: str, cond: bool, detail: object = None) -> None:
    if cond:
        print(f"PASS {name}")
        return
    print(f"FAIL {name}: {detail}")
    raise SystemExit(1)


def _emp(**kwargs):
    base = {
        "employee_key": "WATHEFNI-96599338566",
        "company_code": "WATHEFNI",
        "name": "Aziz Almulla",
    }
    base.update(kwargs)
    return base


def test_flags_and_allowlist() -> None:
    os.environ.pop(v.FLAG_SOFT, None)
    os.environ.pop(v.FLAG_HARD, None)
    os.environ.pop(v.FLAG_COMPANIES, None)
    os.environ.pop(v.FLAG_ALLOWLIST, None)
    check("off by default", not v.validation_enabled(company_code="WATHEFNI", employee_key="WATHEFNI-96599338566"))
    os.environ[v.FLAG_SOFT] = "on"
    os.environ[v.FLAG_COMPANIES] = "WATHEFNI"
    os.environ[v.FLAG_ALLOWLIST] = "WATHEFNI-96599338566,WATHEFNI-96550252254"
    check("aziz allowlisted", v.validation_enabled(company_code="WATHEFNI", employee_key="WATHEFNI-96599338566"))
    check("talal allowlisted", v.validation_enabled(company_code="WATHEFNI", employee_key="WATHEFNI-96550252254"))
    check("other employee denied", not v.validation_enabled(company_code="WATHEFNI", employee_key="WATHEFNI-OTHER"))
    check("other company denied", not v.validation_enabled(company_code="ACME", employee_key="WATHEFNI-96599338566"))


def test_civil_id_clear_mismatch_blocks() -> None:
    os.environ[v.FLAG_SOFT] = "on"
    os.environ[v.FLAG_HARD] = "off"
    os.environ[v.FLAG_COMPANIES] = "WATHEFNI"
    os.environ[v.FLAG_ALLOWLIST] = "WATHEFNI-96599338566"

    def verify(*_a, **_k):
        return {
            "detected_item": "passport",
            "matches_expected_item": False,
            "confidence": 0.91,
            "extraction_status": "extracted",
            "gpt_used": False,
        }

    result = v.evaluate_employee_upload(
        employee=_emp(),
        item_id="civil_id",
        media={"path": "/tmp/x.jpg", "type": "image/jpeg"},
        filename="x.jpg",
        size_bytes=50_000,
        extension=".jpg",
        verify_fn=verify,
        identity_fn=lambda **_k: (True, None, {"extraction_status": "extracted", "confidence": 0.9, "full_name": "Aziz Almulla", "gpt_used": False}),
    )
    check("civil_id wrong type blocks", v.should_block(result), result)
    check("reason wrong_media_item", result.get("reason") == "wrong_media_item", result.get("reason"))
    check("has en correction", "doesn't look like" in (result.get("message_en") or "") or "doesn’t look like" in (result.get("message_en") or ""), result.get("message_en"))
    check("gpt_used false", result.get("gpt_used") is False)


def test_civil_id_identity_mismatch_blocks() -> None:
    def verify(*_a, **_k):
        return {
            "detected_item": "civil_id",
            "matches_expected_item": True,
            "confidence": 0.88,
            "extraction_status": "extracted",
        }

    def identity(**_k):
        return (
            False,
            "identity_mismatch",
            {
                "extraction_status": "extracted",
                "confidence": 0.88,
                "full_name": "Someone Else",
                "identity_check": {"status": "mismatch", "match": False},
                "gpt_used": False,
            },
        )

    result = v.evaluate_employee_upload(
        employee=_emp(),
        item_id="civil_id",
        media={"path": "/tmp/x.jpg", "type": "image/jpeg"},
        filename="id.jpg",
        size_bytes=40_000,
        extension=".jpg",
        verify_fn=verify,
        identity_fn=identity,
    )
    check("identity mismatch blocks soft", v.should_block(result), result)
    check("reason identity_mismatch", result.get("reason") == "identity_mismatch")


def test_uncertain_goes_to_hr_not_block() -> None:
    def verify(*_a, **_k):
        return {
            "detected_item": "employment_contract",
            "matches_expected_item": True,
            "confidence": 0.4,
            "extraction_status": "needs_review",
        }

    result = v.evaluate_employee_upload(
        employee=_emp(),
        item_id="employment_contract",
        media={"path": "/tmp/c.pdf", "type": "application/pdf"},
        filename="c.pdf",
        size_bytes=20_000,
        extension=".pdf",
        verify_fn=verify,
        identity_fn=lambda **_k: (True, None, {"extraction_status": "needs_review", "confidence": 0.4, "gpt_used": False}),
    )
    check("soft uncertain not blocked", not v.should_block(result), result)
    check("decision allow_uncertain", result.get("decision") == "allow_uncertain", result.get("decision"))
    check("hr review recommended", result.get("hr_review_recommended") is True)


def test_hard_blocks_uncertain() -> None:
    os.environ[v.FLAG_HARD] = "on"

    def verify(*_a, **_k):
        return {
            "detected_item": "education_cert",
            "matches_expected_item": True,
            "confidence": 0.3,
            "extraction_status": "needs_review",
        }

    result = v.evaluate_employee_upload(
        employee=_emp(),
        item_id="education_cert",
        media={"path": "/tmp/e.pdf", "type": "application/pdf"},
        filename="e.pdf",
        size_bytes=20_000,
        extension=".pdf",
        verify_fn=verify,
        identity_fn=lambda **_k: (False, "needs_review", {"extraction_status": "needs_review", "confidence": 0.3}),
    )
    check("hard blocks needs_review", v.should_block(result), result)
    os.environ[v.FLAG_HARD] = "off"


def test_personal_photo_rejects_id() -> None:
    def classify(*_a, **_k):
        return {"detected_item": "civil_id", "confidence": 0.93, "matches_expected_item": False}

    result = v.evaluate_employee_upload(
        employee=_emp(),
        item_id="personal_photo",
        media={"path": "/tmp/p.jpg", "type": "image/jpeg"},
        filename="p.jpg",
        size_bytes=30_000,
        extension=".jpg",
        classify_fn=classify,
    )
    check("photo that is ID blocks", v.should_block(result), result)
    check("looks_like_id_not_photo", result.get("reason") == "looks_like_id_not_photo")


def test_personal_photo_accepts_image() -> None:
    def classify(*_a, **_k):
        return {"detected_item": "personal_photo", "confidence": 0.8, "matches_expected_item": True}

    result = v.evaluate_employee_upload(
        employee=_emp(),
        item_id="personal_photo",
        media={"path": "/tmp/p.jpg", "type": "image/jpeg"},
        filename="p.jpg",
        size_bytes=30_000,
        extension=".jpg",
        classify_fn=classify,
    )
    check("personal photo allows", result.get("decision") == "allow", result)


def test_passport_expired_blocks() -> None:
    def verify(*_a, **_k):
        return {
            "detected_item": "passport",
            "matches_expected_item": True,
            "confidence": 0.9,
            "extraction_status": "extracted",
        }

    expired = (date.today() - timedelta(days=30)).isoformat()

    def identity(**_k):
        return (
            True,
            None,
            {
                "extraction_status": "extracted",
                "confidence": 0.9,
                "full_name": "Aziz Almulla",
                "document_number": "A123",
                "expiry_date": expired,
                "identity_check": {"match": True, "status": "matched"},
                "gpt_used": False,
            },
        )

    result = v.evaluate_employee_upload(
        employee=_emp(),
        item_id="passport",
        media={"path": "/tmp/pp.jpg", "type": "image/jpeg"},
        filename="pp.jpg",
        size_bytes=40_000,
        extension=".jpg",
        verify_fn=verify,
        identity_fn=identity,
    )
    check("expired passport blocks", v.should_block(result), result)
    check("expired reason", result.get("reason") == "expired_document")


def test_file_too_small_blocks() -> None:
    result = v.evaluate_employee_upload(
        employee=_emp(),
        item_id="civil_id",
        media={"path": "/tmp/tiny.jpg", "type": "image/jpeg"},
        filename="tiny.jpg",
        size_bytes=100,
        extension=".jpg",
        verify_fn=lambda *_a, **_k: None,
    )
    check("tiny file blocks", v.should_block(result), result)
    check("file_too_small", result.get("reason") == "file_too_small")


def test_route_no_gpt() -> None:
    route = v.resolve_reading_route(item_id="employment_contract", extension=".pdf")
    check("route gpt false", route.get("gpt_auto_ocr_fallback") is False, route)
    route2 = v.resolve_reading_route(item_id="education_cert", extension=".docx")
    check("docx anydoc flag", route2.get("anydoc_applicable") is True, route2)


def test_http_detail_shape() -> None:
    detail = v.http_error_detail(
        {"reason": "wrong_media_item", "gate": "soft", "message": "x", "verification": {"detected_item": "passport", "confidence": 0.9}},
        locale="en",
    )
    check("error code prefix", str(detail.get("error") or "").startswith("document_validation_"))
    check("validation gpt false", (detail.get("validation") or {}).get("gpt_used") is False)


def _civil_id_eval(verify_payload: dict, *, identity_ok: bool = True):
    os.environ[v.FLAG_SOFT] = "on"
    os.environ[v.FLAG_HARD] = "off"
    os.environ[v.FLAG_COMPANIES] = "WATHEFNI"
    os.environ[v.FLAG_ALLOWLIST] = "WATHEFNI-96599338566"

    def verify(*_a, **_k):
        return dict(verify_payload)

    def identity(**_k):
        if not identity_ok:
            return False, "identity_unverified", {"extraction_status": "needs_review", "confidence": 0.4, "gpt_used": False}
        return (
            True,
            None,
            {
                "extraction_status": "extracted",
                "confidence": float(verify_payload.get("confidence") or 0.9),
                "full_name": "Aziz Almulla",
                "document_number": "289010100123",
                "expiry_date": (date.today() + timedelta(days=400)).isoformat(),
                "identity_check": {"match": True, "status": "matched"},
                "gpt_used": False,
            },
        )

    return v.evaluate_employee_upload(
        employee=_emp(),
        item_id="civil_id",
        media={"path": "/tmp/fixture.jpg", "type": "image/jpeg"},
        filename="fixture.jpg",
        size_bytes=48_000,
        extension=".jpg",
        verify_fn=verify,
        identity_fn=identity,
    )


def test_fixture_matrix_non_documents_block() -> None:
    """Obvious non-document uploads must block (no allow_uncertain / store path)."""
    fixtures = [
        (
            "selfie",
            {
                "detected_item": "personal_photo",
                "matches_expected_item": False,
                "confidence": 0.92,
                "extraction_status": "extracted",
            },
            "looks_like_photo_not_document",
        ),
        (
            "person_holding_product",
            {
                "detected_item": "unknown",
                "matches_expected_item": False,
                "confidence": 0.0,
                "extraction_status": "needs_review",
                "extraction_error": "shared_extract_unavailable",
            },
            "not_a_document",
        ),
        (
            "food_product_photo",
            {
                "detected_item": "unknown",
                "matches_expected_item": False,
                "confidence": 0.05,
                "extraction_status": "needs_review",
                "extraction_error": "unusable_image",
            },
            "not_a_document",
        ),
        (
            "game_screenshot",
            {
                "detected_item": "game_screenshot",
                "matches_expected_item": False,
                "confidence": 0.88,
                "extraction_status": "extracted",
            },
            "not_a_document",
        ),
    ]
    for name, payload, reason in fixtures:
        result = _civil_id_eval(payload)
        check(f"fixture {name} blocks", v.should_block(result), result)
        check(f"fixture {name} reason", result.get("reason") == reason, result.get("reason"))
        check(f"fixture {name} not uncertain", result.get("decision") != "allow_uncertain", result.get("decision"))


def test_fixture_blurry_and_partial_soft_submit() -> None:
    """Credible but poor-readability Civil ID evidence → soft uncertain (HR), not hard block."""
    blurry = _civil_id_eval(
        {
            "detected_item": "civil_id",
            "matches_expected_item": False,
            "confidence": 0.38,
            "extraction_status": "needs_review",
            "full_name": None,
            "document_number": None,
        }
    )
    check("blurry civil_id soft not blocked", not v.should_block(blurry), blurry)
    check("blurry civil_id allow_uncertain", blurry.get("decision") == "allow_uncertain", blurry.get("decision"))
    check("blurry civil_id needs_review", blurry.get("reason") == "needs_review", blurry.get("reason"))

    partial = _civil_id_eval(
        {
            "detected_item": "civil_id",
            "matches_expected_item": False,
            "confidence": 0.42,
            "extraction_status": "needs_review",
            "document_number": "289",
            "full_name": "Az",
        }
    )
    check("partial civil_id soft not blocked", not v.should_block(partial), partial)
    check("partial civil_id allow_uncertain", partial.get("decision") == "allow_uncertain", partial.get("decision"))


def test_fixture_clear_civil_id_passes() -> None:
    clear = _civil_id_eval(
        {
            "detected_item": "civil_id",
            "matches_expected_item": True,
            "confidence": 0.91,
            "extraction_status": "extracted",
            "document_number": "289010100123",
            "full_name": "Aziz Almulla",
        }
    )
    check("clear civil_id allow", clear.get("decision") == "allow", clear)
    check("clear civil_id not blocked", not v.should_block(clear), clear)


def test_oreo_style_unknown_zero_conf_blocks() -> None:
    """Regression: Oreo lifestyle false-accept (unknown/0/needs_review) must block."""
    result = _civil_id_eval(
        {
            "detected_item": "unknown",
            "matches_expected_item": False,
            "confidence": 0.0,
            "extraction_status": "needs_review",
            "extraction_error": "shared_extract_unavailable",
            "gpt_used": False,
        }
    )
    check("oreo-style blocks", v.should_block(result), result)
    check("oreo-style not_a_document", result.get("reason") == "not_a_document", result.get("reason"))
    check("oreo-style not uncertain", result.get("decision") != "allow_uncertain", result.get("decision"))


def test_validator_unavailable_blocks_without_store() -> None:
    result = v.evaluate_employee_upload(
        employee=_emp(),
        item_id="civil_id",
        media={"path": "/tmp/x.jpg", "type": "image/jpeg"},
        filename="x.jpg",
        size_bytes=40_000,
        extension=".jpg",
        verify_fn=lambda *_a, **_k: None,
        identity_fn=lambda **_k: (True, None, {"gpt_used": False}),
    )
    check("validator unavailable blocks", v.should_block(result), result)
    check("validator_unavailable reason", result.get("reason") == "validator_unavailable", result.get("reason"))


def main() -> None:
    test_flags_and_allowlist()
    test_civil_id_clear_mismatch_blocks()
    test_civil_id_identity_mismatch_blocks()
    test_uncertain_goes_to_hr_not_block()
    test_hard_blocks_uncertain()
    test_personal_photo_rejects_id()
    test_personal_photo_accepts_image()
    test_passport_expired_blocks()
    test_file_too_small_blocks()
    test_route_no_gpt()
    test_http_detail_shape()
    test_fixture_matrix_non_documents_block()
    test_fixture_blurry_and_partial_soft_submit()
    test_fixture_clear_civil_id_passes()
    test_oreo_style_unknown_zero_conf_blocks()
    test_validator_unavailable_blocks_without_store()
    # Keep Wave 2A smoke still green when imported after flag reset
    os.environ[v.FLAG_SOFT] = "on"
    print("OK onboarding doc validation parity local smoke")


if __name__ == "__main__":
    main()
