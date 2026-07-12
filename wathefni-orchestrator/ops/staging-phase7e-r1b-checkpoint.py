#!/usr/bin/env python3
"""Focused Phase 7E-R1B content-type consistency checkpoint."""

from __future__ import annotations

import base64
import importlib.util
import json
import os
from pathlib import Path
from typing import Any


HERE = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location(
    "phase7e_verifier",
    HERE / "staging-phase7e-employee-app-verify.py",
)
if SPEC is None or SPEC.loader is None:
    raise SystemExit("unable to load Phase 7E verifier helpers")
v = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(v)
app = v.app

REPORT_PATH = Path(
    os.environ.get(
        "WATHEFNI_PHASE7E_R1B_REPORT",
        str(HERE / "reports" / "phase7e-r1b-checkpoint-report.json"),
    )
)

PDF_BYTES = b"%PDF-1.4\n1 0 obj\n<< /Type /Catalog >>\nendobj\ntrailer\n<< /Root 1 0 R >>\n%%EOF\n"
PNG_BYTES = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+A8AAQUBAScY42YAAAAASUVORK5CYII="
)

checks: list[dict[str, Any]] = []


def record(case_id: str, title: str, passed: bool, observed: Any) -> None:
    checks.append(
        {
            "case_id": case_id,
            "title": title,
            "passed": bool(passed),
            "observed": v.json_safe(observed),
        }
    )
    print(f"{'PASS' if passed else 'FAIL'} {case_id} {title}")


def item_state(item_id: str) -> dict[str, Any]:
    return {
        "status": v.scalar(
            "SELECT status FROM onboarding_items WHERE employee_key=%s AND item_id=%s",
            (v.EMP_A, item_id),
        ),
        "files": int(
            v.scalar(
                "SELECT count(*) FROM file_registry WHERE company_code=%s AND subject_key=%s AND document_type=%s",
                (v.COMPANY, v.EMP_A, item_id),
            )
            or 0
        ),
        "documents": int(
            v.scalar(
                "SELECT count(*) FROM employee_documents WHERE company_code=%s AND employee_key=%s AND item_id=%s",
                (v.COMPANY, v.EMP_A, item_id),
            )
            or 0
        ),
        "completion_audits": int(
            v.scalar(
                """
                SELECT count(*) FROM action_results
                WHERE company_code=%s AND action_type='employee_document_uploaded'
                  AND result->'action'->>'target'=%s
                  AND result->'details'->>'item_id'=%s
                """,
                (v.COMPANY, v.EMP_A, item_id),
            )
            or 0
        ),
    }


def rejected_control(
    case_id: str,
    title: str,
    *,
    item_id: str,
    filename: str,
    declared_mime: str,
    data: bytes,
    context: dict[str, Any],
) -> None:
    before = item_state(item_id)
    response = v.invoke(
        lambda: v.synthetic_upload(filename, declared_mime, data, item_id, context)
    )
    after = item_state(item_id)
    record(
        case_id,
        title,
        v.denied(response, {400, 415})
        and (response.get("body") or {}).get("error") == "mime_mismatch_or_invalid_content"
        and before == after
        and after["status"] == "pending",
        {"response": response, "before": before, "after": after},
    )


def main() -> int:
    production_before = v.production_snapshot()
    protected_before = v.staging_protected_snapshot()
    try:
        v.setup()
        v.set_flag("WATHEFNI_EMPLOYEE_APP", True)
        v.set_flag("WATHEFNI_COMPANY_CHANNEL_ACCOUNTS", False)
        v.set_flag("WATHEFNI_ONBOARDING_SEED", False)
        v.set_flag("WATHEFNI_PUSH_NOTIFICATIONS", False)
        v.set_module(v.COMPANY, "employee_app", True)
        for item_id in (
            "r1b_valid_pdf",
            "r1b_valid_png",
            "r1b_ext_mismatch",
            "r1b_declared_mismatch",
            "r1b_signature_mismatch",
            "r1b_unknown",
            "r1b_detector_error",
        ):
            v.insert_item(v.COMPANY, v.EMP_A, item_id)
        session = app.create_employee_session(v.COMPANY, v.EMP_A, v.PHONE_A)
        context = v.app_context(session["token"])

        pdf_response = v.invoke(
            lambda: v.synthetic_upload(
                "valid.pdf",
                "application/pdf",
                PDF_BYTES,
                "r1b_valid_pdf",
                context,
            )
        )
        pdf_state = item_state("r1b_valid_pdf")
        pdf_mime = v.scalar(
            """
            SELECT mime_type FROM file_registry
            WHERE company_code=%s AND subject_key=%s AND document_type='r1b_valid_pdf'
            ORDER BY created_at DESC LIMIT 1
            """,
            (v.COMPANY, v.EMP_A),
        )
        record(
            "R1B-V1",
            "valid PDF extension, MIME, and signature is accepted",
            pdf_response.get("returned") is True
            and pdf_state["status"] == "received"
            and pdf_state["files"] == 1
            and pdf_state["documents"] == 1
            and pdf_mime == "application/pdf",
            {"response": pdf_response, "state": pdf_state, "stored_mime": pdf_mime},
        )

        png_response = v.invoke(
            lambda: v.synthetic_upload(
                "valid.png",
                "image/png",
                PNG_BYTES,
                "r1b_valid_png",
                context,
            )
        )
        png_state = item_state("r1b_valid_png")
        png_mime = v.scalar(
            """
            SELECT mime_type FROM file_registry
            WHERE company_code=%s AND subject_key=%s AND document_type='r1b_valid_png'
            ORDER BY created_at DESC LIMIT 1
            """,
            (v.COMPANY, v.EMP_A),
        )
        record(
            "R1B-V2",
            "valid PNG extension, MIME, and signature is accepted",
            png_response.get("returned") is True
            and png_state["status"] == "received"
            and png_state["files"] == 1
            and png_state["documents"] == 1
            and png_mime == "image/png",
            {"response": png_response, "state": png_state, "stored_mime": png_mime},
        )

        rejected_control(
            "R1B-N1",
            "filename extension mismatch fails closed before canonical writes",
            item_id="r1b_ext_mismatch",
            filename="spoof.pdf",
            declared_mime="application/pdf",
            data=PNG_BYTES,
            context=context,
        )
        rejected_control(
            "R1B-N2",
            "declared MIME mismatch fails closed before canonical writes",
            item_id="r1b_declared_mismatch",
            filename="spoof.png",
            declared_mime="application/pdf",
            data=PNG_BYTES,
            context=context,
        )
        rejected_control(
            "R1B-N3",
            "signature mismatch fails closed before canonical writes",
            item_id="r1b_signature_mismatch",
            filename="spoof.png",
            declared_mime="image/png",
            data=PDF_BYTES,
            context=context,
        )
        rejected_control(
            "R1B-N4",
            "unknown signature fails closed before canonical writes",
            item_id="r1b_unknown",
            filename="unknown.pdf",
            declared_mime="application/pdf",
            data=b"not a PDF or an allowed image",
            context=context,
        )

        original_detector = app._detect_employee_app_upload_matches

        def detector_error(_data: bytes) -> list[Any]:
            raise RuntimeError("synthetic_detector_error")

        app._detect_employee_app_upload_matches = detector_error
        try:
            rejected_control(
                "R1B-N5",
                "detector error fails closed before canonical writes",
                item_id="r1b_detector_error",
                filename="detector-error.pdf",
                declared_mime="application/pdf",
                data=PDF_BYTES,
                context=context,
            )
        finally:
            app._detect_employee_app_upload_matches = original_detector
    finally:
        v.set_flag("WATHEFNI_EMPLOYEE_APP", False)
        v.set_flag("WATHEFNI_COMPANY_CHANNEL_ACCOUNTS", False)
        v.set_flag("WATHEFNI_ONBOARDING_SEED", False)
        v.set_flag("WATHEFNI_PUSH_NOTIFICATIONS", False)
        v.cleanup()

    production_after = v.production_snapshot()
    protected_after = v.staging_protected_snapshot()
    flags = v.systemd_flags("wathefni-orchestrator-staging.service")
    record(
        "R1B-S1",
        "production and protected staging snapshots remain unchanged",
        production_before.get("sha256") == production_after.get("sha256")
        and protected_before.get("sha256") == protected_after.get("sha256"),
        {
            "production_unchanged": production_before.get("sha256") == production_after.get("sha256"),
            "staging_protected_unchanged": protected_before.get("sha256") == protected_after.get("sha256"),
        },
    )
    record(
        "R1B-S2",
        "protected staging service flags remain off",
        all(v.flag_is_off(flags.get(flag, "unset")) for flag in v.PROTECTED_FLAGS),
        flags,
    )
    passed = sum(1 for check in checks if check["passed"])
    report = {
        "phase": "7E-R1B",
        "detector": {"library": "puremagic", "version": "2.2.0", "purpose": "content-type consistency, not antivirus"},
        "passed": passed,
        "failed": len(checks) - passed,
        "checks": checks,
        "recommendation": "r1b-green" if passed == len(checks) else "r1b-blocked",
    }
    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(json.dumps(report, indent=2, sort_keys=True, default=str) + "\n")
    print(f"PHASE 7E-R1B: {passed}/{len(checks)} passed")
    print(f"report={REPORT_PATH}")
    return 0 if passed == len(checks) else 1


if __name__ == "__main__":
    raise SystemExit(main())
