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
    """Semantic field uncertainty on a clear matching document → HR, not retake block."""
    def verify(*_a, **_k):
        return {
            "detected_item": "civil_id",
            "matches_expected_item": True,
            "confidence": 0.88,
            "extraction_status": "extracted",
            "document_number": "289010100123",
            "full_name": "Aziz Almulla",
        }

    def identity(**_k):
        return (
            False,
            "identity_unverified",
            {
                "extraction_status": "extracted",
                "confidence": 0.88,
                "full_name": "Aziz Almulla",
                "document_number": "289010100123",
                "identity_check": {"status": "uncertain", "match": None},
                "gpt_used": False,
            },
        )

    result = v.evaluate_employee_upload(
        employee=_emp(),
        item_id="civil_id",
        media={"path": "/tmp/id.jpg", "type": "image/jpeg"},
        filename="id.jpg",
        size_bytes=40_000,
        extension=".jpg",
        verify_fn=verify,
        identity_fn=identity,
    )
    check("semantic uncertain not blocked", not v.should_block(result), result)
    check("decision allow_uncertain", result.get("decision") == "allow_uncertain", result.get("decision"))
    check("hr review recommended", result.get("hr_review_recommended") is True)
    check("reason identity_unverified", result.get("reason") == "identity_unverified", result.get("reason"))


def test_hard_blocks_uncertain() -> None:
    os.environ[v.FLAG_HARD] = "on"

    def verify(*_a, **_k):
        return {
            "detected_item": "civil_id",
            "matches_expected_item": True,
            "confidence": 0.88,
            "extraction_status": "extracted",
        }

    result = v.evaluate_employee_upload(
        employee=_emp(),
        item_id="civil_id",
        media={"path": "/tmp/id.jpg", "type": "image/jpeg"},
        filename="id.jpg",
        size_bytes=40_000,
        extension=".jpg",
        verify_fn=verify,
        identity_fn=lambda **_k: (
            False,
            "identity_unverified",
            {
                "extraction_status": "extracted",
                "confidence": 0.88,
                "full_name": "Aziz Almulla",
                "identity_check": {"status": "uncertain"},
                "gpt_used": False,
            },
        ),
    )
    check("hard blocks identity_unverified", v.should_block(result), result)
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


def test_fixture_blurry_and_partial_block_retake() -> None:
    """Fixable capture quality must block with retake guidance — not HR review."""
    blurry = _civil_id_eval(
        {
            "detected_item": "civil_id",
            "matches_expected_item": False,
            "confidence": 0.38,
            "extraction_status": "needs_review",
            "unreadable_reason": "too blurry to read text",
        }
    )
    check("blurry civil_id blocks", v.should_block(blurry), blurry)
    check("blurry reason too_blurry", blurry.get("reason") == "too_blurry", blurry.get("reason"))
    check("blurry has EN retake", "blurry" in (blurry.get("message_en") or "").lower(), blurry.get("message_en"))
    check("blurry has AR copy", bool(blurry.get("message_ar")), blurry.get("message_ar"))

    partial = _civil_id_eval(
        {
            "detected_item": "civil_id",
            "matches_expected_item": False,
            "confidence": 0.42,
            "extraction_status": "needs_review",
            "unreadable_reason": "cropped / not fully visible",
            "document_number": "289",
            "full_name": "Az",
        }
    )
    check("partial civil_id blocks", v.should_block(partial), partial)
    check(
        "partial reason document_not_fully_visible",
        partial.get("reason") == "document_not_fully_visible",
        partial.get("reason"),
    )

    glare = _civil_id_eval(
        {
            "detected_item": "civil_id",
            "matches_expected_item": True,
            "confidence": 0.7,
            "extraction_status": "needs_review",
            "unreadable_reason": "glare and heavy shadow on name",
        }
    )
    check("glare blocks", v.should_block(glare), glare)
    check("glare reason", glare.get("reason") == "glare_or_shadow", glare.get("reason"))

    def verify_back(*_a, **_k):
        return {
            "detected_item": "civil_id",
            "matches_expected_item": True,
            "confidence": 0.9,
            "extraction_status": "extracted",
            "side": "back",
        }

    def identity_back(**_k):
        return (
            True,
            None,
            {
                "extraction_status": "extracted",
                "confidence": 0.9,
                "full_name": "Aziz Almulla",
                "document_number": "289010100123",
                "side": "back",
                "expiry_date": (date.today() + timedelta(days=400)).isoformat(),
                "identity_check": {"match": True, "status": "matched"},
                "gpt_used": False,
            },
        )

    missing_back = v.evaluate_employee_upload(
        employee=_emp(),
        item_id="civil_id",
        media={"path": "/tmp/back.jpg", "type": "image/jpeg"},
        filename="back.jpg",
        size_bytes=48_000,
        extension=".jpg",
        verify_fn=verify_back,
        identity_fn=identity_back,
    )
    check("missing back blocks", v.should_block(missing_back), missing_back)
    check("missing_side reason", missing_back.get("reason") == "missing_side", missing_back.get("reason"))
    check("missing_side EN", "front and back" in (missing_back.get("message_en") or "").lower(), missing_back.get("message_en"))


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


def test_low_conf_credible_doc_blocks_retake_not_hr() -> None:
    """Default low-readability on a credible doc must not fall through to HR."""
    result = _civil_id_eval(
        {
            "detected_item": "civil_id",
            "matches_expected_item": False,
            "confidence": 0.4,
            "extraction_status": "needs_review",
        }
    )
    check("low-conf credible blocks", v.should_block(result), result)
    check("low-conf not uncertain", result.get("decision") != "allow_uncertain", result.get("decision"))
    check("low-conf retake reason", result.get("reason") in v.CAPTURE_QUALITY_BLOCK_REASONS, result.get("reason"))


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


def test_decision_order_nondoc_beats_capture_copy() -> None:
    """Live defect: random non-doc blocked with glare/blur copy — wrong-doc message must win."""
    import tempfile
    from pathlib import Path

    import numpy as np
    from PIL import Image

    with tempfile.TemporaryDirectory(prefix="docval-nondoc-") as td:
        path = Path(td) / "random_glare.jpg"
        arr = np.full((800, 1200, 3), 255, dtype=np.uint8)
        Image.fromarray(arr).save(path, format="JPEG", quality=90)

        def verify(*_a, **_k):
            return {
                "detected_item": "lifestyle",
                "matches_expected_item": False,
                "confidence": 0.88,
                "extraction_status": "extracted",
            }

        result = v.evaluate_employee_upload(
            employee=_emp(),
            item_id="civil_id_canary_test",
            media={"path": str(path), "type": "image/jpeg"},
            filename="random.jpg",
            size_bytes=path.stat().st_size,
            extension=".jpg",
            verify_fn=verify,
            identity_fn=lambda **_k: (True, None, {"gpt_used": False}),
        )
    check("nondoc blocks", v.should_block(result), result)
    check(
        "nondoc reason photo/wrong-doc",
        result.get("reason") in {"looks_like_photo_not_document", "not_a_document"},
        result.get("reason"),
    )
    check(
        "nondoc not glare/blur message",
        result.get("reason") not in {"glare_or_shadow", "too_blurry", "document_not_fully_visible"},
        result.get("reason"),
    )


def test_high_ocr_cannot_allow_reject_capture() -> None:
    """Live defect: blurry Civil ID with high Mistral conf must still retake-block."""
    import tempfile
    from pathlib import Path

    from PIL import Image, ImageDraw, ImageFilter

    with tempfile.TemporaryDirectory(prefix="docval-blur-") as td:
        path = Path(td) / "blurry_civil_id.jpg"
        img = Image.new("RGB", (1000, 640), (168, 172, 178))
        d = ImageDraw.Draw(img)
        d.rounded_rectangle((80, 60, 920, 580), radius=18, fill=(214, 216, 220), outline=(40, 40, 50), width=3)
        d.text((200, 200), "CIVIL ID ABDULAZIZ 302082900873", fill=(20, 20, 20))
        img.filter(ImageFilter.GaussianBlur(radius=10)).save(path, format="JPEG", quality=80)

        def verify(*_a, **_k):
            return {
                "detected_item": "civil_id",
                "matches_expected_item": True,
                "confidence": 0.97,
                "extraction_status": "extracted",
            }

        def identity(**_k):
            return (
                True,
                None,
                {
                    "extraction_status": "extracted",
                    "confidence": 0.97,
                    "full_name": "ABDULAZIZ H R ALMULLA",
                    "document_number": "302082900873",
                    "expiry_date": "2027-01-01",
                    "identity_check": {"match": True, "status": "matched"},
                    "gpt_used": False,
                },
            )

        result = v.evaluate_employee_upload(
            employee=_emp(),
            item_id="civil_id_canary_test",
            media={"path": str(path), "type": "image/jpeg"},
            filename="E4D2A514-7F85-4C9E-BBC5-C3100C9E8D9A.jpg",
            size_bytes=path.stat().st_size,
            extension=".jpg",
            verify_fn=verify,
            identity_fn=identity,
        )
    check("blurry+highOCR blocks", v.should_block(result), result)
    check("blurry+highOCR reason too_blurry", result.get("reason") == "too_blurry", result.get("reason"))
    check("blurry+highOCR not allow", result.get("decision") != "allow", result.get("decision"))
    check("blurry+highOCR not HR", result.get("decision") != "allow_uncertain", result.get("decision"))
    check(
        "blurry capture reject status",
        (result.get("capture_quality") or {}).get("status") == "reject",
        result.get("capture_quality"),
    )


def test_aziz_canary_identity_alias_allows() -> None:
    """Aziz canary only: ABDULAZIZ alias passes soft identity without changing employees.name."""
    os.environ[v.FLAG_SOFT] = "on"
    os.environ[v.FLAG_HARD] = "off"
    os.environ[v.FLAG_COMPANIES] = "WATHEFNI"
    os.environ[v.FLAG_ALLOWLIST] = "WATHEFNI-96599338566"

    def verify(*_a, **_k):
        return {
            "detected_item": "civil_id",
            "matches_expected_item": True,
            "confidence": 0.97,
            "extraction_status": "extracted",
        }

    def identity(**_k):
        return (
            False,
            "identity_mismatch",
            {
                "extraction_status": "extracted",
                "confidence": 0.97,
                "full_name": "ABDULAZIZ H R ALMULLA",
                "full_name_en": "ABDULAZIZ H R ALMULLA",
                "full_name_ar": "عبد العزيز حمد راشد الملا",
                "document_number": "302082900873",
                "identity_check": {"status": "mismatch", "match": False},
                "gpt_used": False,
            },
        )

    # Prefer real document_name_match when available; else strict equality stub.
    try:
        import app as _app  # type: ignore

        match_fn = _app.document_name_match
    except Exception:
        def match_fn(expected, document):  # type: ignore
            ok = str(expected or "").strip().casefold() == str(document or "").strip().casefold()
            return {"match": ok, "status": "matched" if ok else "mismatch"}

    # Monkeypatch helper path used inside evaluate by ensuring alias uses match_fn via app import;
    # evaluate calls canary_identity_alias_match which imports app — if unavailable, inject via direct check.
    alias = v.canary_identity_alias_match(
        employee_key="WATHEFNI-96599338566",
        extraction={
            "full_name": "ABDULAZIZ H R ALMULLA",
            "full_name_ar": "عبد العزيز حمد راشد الملا",
        },
        name_match_fn=match_fn,
    )
    check("alias helper matches EN", bool(alias and alias.get("match")), alias)

    other = v.canary_identity_alias_match(
        employee_key="WATHEFNI-OTHER",
        extraction={"full_name": "ABDULAZIZ H R ALMULLA"},
        name_match_fn=match_fn,
    )
    check("alias not applied to other employees", other is None, other)

    result = v.evaluate_employee_upload(
        employee=_emp(name="W5C-SYNTH|Aziz Mobile QA"),
        item_id="civil_id",
        media={"path": "/tmp/id.jpg", "type": "image/jpeg"},
        filename="id.jpg",
        size_bytes=48_000,
        extension=".jpg",
        verify_fn=verify,
        identity_fn=identity,
    )
    # Without app.document_name_match available locally, evaluate may still block; prove via helper above.
    # When app is importable (prod), expect allow.
    try:
        import app as _app  # noqa: F401

        check("canary alias allows clear ID", result.get("decision") == "allow", result)
        check("canary alias not blocked", not v.should_block(result), result)
    except Exception:
        check("canary alias helper ready without app", alias.get("canary_alias") == "ABDULAZIZ H R ALMULLA", alias)


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
    test_fixture_blurry_and_partial_block_retake()
    test_fixture_clear_civil_id_passes()
    test_low_conf_credible_doc_blocks_retake_not_hr()
    test_oreo_style_unknown_zero_conf_blocks()
    test_decision_order_nondoc_beats_capture_copy()
    test_high_ocr_cannot_allow_reject_capture()
    test_aziz_canary_identity_alias_allows()
    test_validator_unavailable_blocks_without_store()
    # Keep Wave 2A smoke still green when imported after flag reset
    os.environ[v.FLAG_SOFT] = "on"
    print("OK onboarding doc validation parity local smoke")


if __name__ == "__main__":
    main()
