#!/usr/bin/env python3
"""Smoke: Civil ID dual-side draft attempt + pair gate (no live upload required)."""

from __future__ import annotations

import json
import os
import sys
import uuid

# Ensure flag on for unit checks.
os.environ.setdefault("WATHEFNI_CIVIL_ID_DUAL_SIDE", "on")
os.environ.setdefault("WATHEFNI_CIVIL_ID_DUAL_SIDE_COMPANIES", "WATHEFNI")
os.environ.setdefault(
    "WATHEFNI_CIVIL_ID_DUAL_SIDE_EMPLOYEE_ALLOWLIST",
    "WATHEFNI-SMOKE-DUAL-SIDE",
)


def check(name: str, cond: bool, detail: str = "") -> None:
    if cond:
        print(f"PASS {name}" + (f" — {detail}" if detail else ""))
        return
    print(f"FAIL {name}" + (f" — {detail}" if detail else ""), file=sys.stderr)
    raise SystemExit(1)


def main() -> int:
    import onboarding_civil_id_dual_side as dual
    import onboarding_doc_validation_parity as docval

    check("flag_on", dual.dual_side_flag_on())
    check(
        "enabled_for_allowlisted",
        dual.dual_side_enabled(company_code="WATHEFNI", employee_key="WATHEFNI-SMOKE-DUAL-SIDE"),
    )
    check(
        "disabled_for_other_employee",
        not dual.dual_side_enabled(company_code="WATHEFNI", employee_key="WATHEFNI-OTHER"),
    )
    check("civil_id_is_dual_item", dual.is_dual_side_item("civil_id"))
    check("canary_is_dual_item", dual.is_dual_side_item("civil_id_dual_side_canary"))
    check("passport_not_dual_item", not dual.is_dual_side_item("passport"))

    # Side gate: model-only opposite soft-accepts; strong layout corroboration hard-blocks.
    soft_opposite = dual.validate_part_side(
        expected_part="front",
        extraction={"side": "back", "fields": {"side": {"value": "back", "confidence": 0.99}}},
    )
    check(
        "model_only_opposite_soft",
        soft_opposite.get("hr_warning") is True and soft_opposite.get("side_decision") == "soft_accepted_opposite",
        str(soft_opposite),
    )

    try:
        dual.validate_part_side(
            expected_part="back",
            extraction={
                "side": "front",
                "fields": {
                    "side": {"value": "front", "confidence": 0.97},
                    "document_number": {"value": "289123456789"},
                    "nationality": {"value": "Kuwaiti"},
                    "date_of_birth": {"value": "1989-03-14"},
                    "full_name_en": {"value": "AHMAD"},
                },
            },
        )
        check("strong_front_into_back_blocks", False, "expected DualSideError")
    except dual.DualSideError as exc:
        check("strong_front_into_back_blocks", exc.code == "wrong_side", exc.code)

    # Back markers prevent false reject when model mislabels reverse as front.
    soft_back = dual.validate_part_side(
        expected_part="back",
        extraction={
            "side": "front",
            "fields": {
                "side": {"value": "front", "confidence": 0.97},
                "document_number": {"value": "289123456789"},
                "nationality": {"value": "Kuwaiti"},
                "date_of_birth": {"value": "1989-03-14"},
                "full_name_en": {"value": "AHMAD"},
                "address": {"value": "Block 5 Kuwait"},
                "blood_type": {"value": "O+"},
            },
        },
    )
    check(
        "mislabeled_back_with_reverse_cues_soft",
        soft_back.get("side_decision") == "soft_accepted_opposite" and soft_back.get("hr_warning") is True,
        str(soft_back),
    )

    unknown = dual.validate_part_side(expected_part="front", extraction={"side": "unknown"})
    check("unknown_soft", unknown.get("hr_warning") is True and unknown.get("detected_side") == "unknown")

    front_ok = dual.validate_part_side(expected_part="front", extraction={"side": "front"})
    check("front_matches", front_ok.get("hr_warning") is False)

    # Legacy single-file path still maps back→missing_side; dual-part mode must not.
    check(
        "legacy_back_missing_side",
        docval.infer_capture_quality_reason({"side": "back"}, expected_item="civil_id") == "missing_side",
    )
    check(
        "dual_part_back_not_missing_side",
        docval.infer_capture_quality_reason(
            {"side": "back"}, expected_item="civil_id_dual_side_canary", expected_part="back"
        )
        is None,
    )

    # JSON readiness: OCR often returns datetime.date — must not 500 on attach_part.
    from datetime import date as _date

    ready = dual._json_ready(
        {
            "expiry_date": _date(2028, 1, 15),
            "nested": {"issued": _date(2020, 5, 1)},
            "uuid": __import__("uuid").UUID("00000000-0000-4000-8000-000000000001"),
        }
    )
    check("json_ready_dates", ready["expiry_date"] == "2028-01-15" and ready["nested"]["issued"] == "2020-05-01")
    check("json_dumps_ok", isinstance(json.dumps(ready), str))

    # Pair gate matrix
    incomplete = dual.evaluate_pair_gate({"front": {"file_id": "f1", "file_sha256": "a"}})
    check("pair_incomplete_missing_back", incomplete.get("ok") is False and incomplete.get("reason") == "parts_incomplete")

    dup = dual.evaluate_pair_gate(
        {
            "front": {"file_id": "f1", "file_sha256": "same", "detected_side": "front", "ocr_proposal": {}},
            "back": {"file_id": "f2", "file_sha256": "same", "detected_side": "back", "ocr_proposal": {}},
        }
    )
    check("pair_duplicate_sha", dup.get("ok") is False and dup.get("reason") == "duplicate_sides")

    mismatch = dual.evaluate_pair_gate(
        {
            "front": {
                "file_id": "f1",
                "file_sha256": "a",
                "detected_side": "front",
                "ocr_proposal": {"document_number": "111"},
            },
            "back": {
                "file_id": "f2",
                "file_sha256": "b",
                "detected_side": "back",
                "ocr_proposal": {"document_number": "222"},
            },
        }
    )
    check("pair_identity_mismatch", mismatch.get("ok") is False and mismatch.get("reason") == "identity_mismatch")

    ok_pair = dual.evaluate_pair_gate(
        {
            "front": {
                "file_id": "f1",
                "file_sha256": "a",
                "detected_side": "front",
                "ocr_proposal": {"document_number": "123456789012"},
            },
            "back": {
                "file_id": "f2",
                "file_sha256": "b",
                "detected_side": "unknown",
                "hr_warning": True,
                "ocr_proposal": {"document_number": "123456789012"},
            },
        }
    )
    check("pair_ok_with_unknown_hr_warn", ok_pair.get("ok") is True and ok_pair.get("hr_review_recommended") is True)

    # DocVal alias + expected_part wiring (no media — just alias map).
    check(
        "canary_alias",
        docval.canonical_validation_item("civil_id_dual_side_canary") == "civil_id",
    )
    check("wrong_side_in_clear_blocks", "wrong_side" in docval.CLEAR_BLOCK_REASONS)
    check("correction_wrong_side", "Front or Back" in docval.correction_message("wrong_side", locale="en") or "side" in docval.correction_message("wrong_side", locale="en").lower())

    # Projection decoration for legacy accepted
    decorated = dual.decorate_dual_side_item(
        {
            "item_id": "civil_id",
            "status": "accepted",
            "file_id": "legacy-file",
            "actions": ["preview", "view_versions"],
            "required": True,
            "owner": "employee",
            "item_type": "document",
            "collection_mode": "document",
        },
        version={"parts_schema": None, "review_status": "hr_reviewed"},
        parts={},
        can_upload=True,
        lifecycle_on=True,
    )
    check("legacy_accepted_schema", decorated.get("civil_id_parts", {}).get("schema") == dual.LEGACY_SCHEMA)
    check("legacy_no_upload_front", "upload_front" not in (decorated.get("actions") or []))

    collecting = dual.decorate_dual_side_item(
        {
            "item_id": "civil_id_dual_side_canary",
            "status": "pending",
            "actions": ["upload"],
            "required": False,
            "owner": "employee",
            "item_type": "document",
            "collection_mode": "document",
        },
        version={"version_id": str(uuid.uuid4()), "review_status": dual.STATUS_DRAFT_PARTS, "parts_schema": dual.PARTS_SCHEMA},
        parts={},
        can_upload=True,
        lifecycle_on=True,
    )
    actions = collecting.get("actions") or []
    check("collecting_upload_front", "upload_front" in actions)
    check("collecting_upload_back", "upload_back" in actions)
    check("collecting_no_generic_upload", "upload" not in actions)

    one_side = dual.decorate_dual_side_item(
        {
            "item_id": "civil_id_dual_side_canary",
            "status": "in_progress",
            "actions": ["upload"],
            "required": False,
            "owner": "employee",
            "item_type": "document",
            "collection_mode": "document",
        },
        version={"version_id": str(uuid.uuid4()), "review_status": dual.STATUS_DRAFT_PARTS, "parts_schema": dual.PARTS_SCHEMA},
        parts={
            "front": {"file_id": "f1", "file_sha256": "a", "detected_side": "front"},
        },
        can_upload=True,
        lifecycle_on=True,
    )
    one_actions = one_side.get("actions") or []
    check("one_side_replace_front", "replace_front" in one_actions)
    check("one_side_upload_back", "upload_back" in one_actions)
    check("one_side_incomplete", one_side.get("civil_id_parts", {}).get("parts_complete") is False)

    print("OK civil_id_dual_side smoke")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
