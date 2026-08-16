#!/usr/bin/env python3
"""Audit latest civil_id_canary_test upload rejection (read-only)."""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import app
import onboarding_doc_validation_parity as v

EMP = "WATHEFNI-96599338566"
ITEM = "civil_id_canary_test"


def main() -> None:
    out: dict = {
        "audited_at": datetime.now(timezone.utc).isoformat(),
        "employee_key": EMP,
        "item_id": ITEM,
    }
    with app.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT result_id, created_at, status, result, actor_user_id, actor_phone
                FROM action_results
                WHERE action_type='employee_document_upload_rejected'
                  AND result->>'employee_key'=%s
                  AND result->>'item_id'=%s
                ORDER BY created_at DESC
                LIMIT 10
                """,
                (EMP, ITEM),
            )
            rejections = [dict(r) for r in (cur.fetchall() or [])]
            out["rejections"] = rejections
            latest = rejections[0] if rejections else None
            out["latest_rejection"] = latest

            cur.execute(
                "SELECT employee_key, name, phone, company_code, profile FROM employees WHERE employee_key=%s",
                (EMP,),
            )
            out["employee"] = dict(cur.fetchone() or {})

            cur.execute(
                """
                SELECT status, value, content_sha256, mime_type, local_path,
                       row_version, lifecycle_meta, updated_at
                FROM onboarding_items
                WHERE employee_key=%s AND item_id=%s
                """,
                (EMP, ITEM),
            )
            out["canary_item"] = dict(cur.fetchone() or {})

            # No version is created on block; confirm absence around rejection time
            if latest:
                ts = latest["created_at"]
                cur.execute(
                    """
                    SELECT version_id, file_id, file_sha256, filename, mime_type,
                           review_status, created_at, rejection_reason, ocr_proposal
                    FROM governed_document_versions
                    WHERE employee_key=%s AND document_type=%s
                      AND created_at BETWEEN %s::timestamptz - interval '2 minutes'
                                        AND %s::timestamptz + interval '2 minutes'
                    ORDER BY created_at DESC
                    """,
                    (EMP, ITEM, ts, ts),
                )
                out["versions_near_rejection"] = [dict(r) for r in (cur.fetchall() or [])]

    # Name-match matrix for interpretation
    emp_name = str((out.get("employee") or {}).get("name") or "")
    probes = ["Aziz Almulla", "Aziz Mobile QA", "Mohammad Qattan", "Curriculum Vitae", emp_name]
    out["name_match_probes"] = [
        {"extracted": p, "result": app.document_name_match(emp_name, p)} for p in probes
    ]

    # Rule-order documentation from live module
    out["rule_ordering"] = [
        "1. quality: file_too_small / wrong_format / media unreadable_reason",
        "2. personal_photo lane (N/A for civil_id)",
        "3. verify(media) via Mistral identity verify",
        "4. if verify None → validator_unavailable block",
        "5. instruction_screenshot → block",
        "6. personal_photo/selfie/lifestyle on identity item → looks_like_photo_not_document",
        "7. is_obvious_non_document → not_a_document (etc)",
        "8. detected!=expected AND conf>=0.65 AND not matches → wrong_media_item",
        "9. infer_capture_quality_reason → too_blurry/crop/glare/missing_side block",
        "10. low_readability (not matches OR conf<0.65 OR needs_review+low conf) → retake block if credible else non-doc",
        "11. ONLY if matches AND conf>=0.65: identity() / validate_onboarding_document_identity",
        "12. missing_side / expiry / required_fields",
        "13. identity_reason==identity_mismatch → BLOCK identity_mismatch  << selected",
        "14. else identity_unverified → soft uncertain / hard block",
        "15. else allow",
    ]
    out["why_wrong_media_item_did_not_fire"] = (
        "wrong_media_item only runs when detected_item differs from expected AND "
        "confidence>=0.65 AND matches_expected_item is False. "
        "identity_mismatch is only reachable after low_readability is False, which requires "
        "matches_expected_item True AND confidence>=VERIFY_CONFIDENCE_FLOOR (0.65). "
        "Therefore verify must have treated the upload as a matching Civil ID before identity ran."
    )
    out["verdict_categories"] = {
        "misclassified_as_identity_document": (
            "Required precondition for identity_mismatch under current soft gate: "
            "verify.matches_expected_item=True with confidence>=0.65 for expected civil_id."
        ),
        "identity_before_document_type": False,
        "identity_before_document_type_detail": (
            "Document-type verification (verify/matches/wrong_media_item/non-doc/capture) "
            "runs first; identity name-match runs only after a high-confidence expected match."
        ),
        "wrong_employee_message_fallback": False,
        "message_source": (
            "CORRECTION_COPY['identity_mismatch'] selected because "
            "validate_onboarding_document_identity returned reason identity_mismatch "
            "when document_name_match(...).status == 'mismatch'."
        ),
    }
    out["employee_name_used_for_comparison"] = emp_name
    out["receipt"] = {
        "result_id": (latest or {}).get("result_id") if latest else None,
        "event_id": ((latest or {}).get("result") or {}).get("event_id") if latest else None,
        "rejection_code": ((latest or {}).get("result") or {}).get("rejection_code") if latest else None,
        "created_at": str((latest or {}).get("created_at")) if latest else None,
        "declared_mime": ((latest or {}).get("result") or {}).get("declared_mime") if latest else None,
        "extension": ((latest or {}).get("result") or {}).get("extension") if latest else None,
        "attempted_byte_size": ((latest or {}).get("result") or {}).get("attempted_byte_size") if latest else None,
        "version_id": None,
        "version_note": "Blocked before store — no governed/ESS version_id was created for this attempt.",
    }
    out["flags"] = {
        "soft": __import__("os").environ.get("WATHEFNI_ONBOARDING_DOC_VALIDATION_SOFT"),
        "hard": __import__("os").environ.get("WATHEFNI_ONBOARDING_DOC_VALIDATION_HARD"),
        "allowlist": __import__("os").environ.get("WATHEFNI_ONBOARDING_DOC_VALIDATION_EMPLOYEE_ALLOWLIST"),
    }
    print(json.dumps(out, default=str, indent=2))


if __name__ == "__main__":
    main()
