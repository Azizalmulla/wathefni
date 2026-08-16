#!/usr/bin/env python3
"""Bank ESS P1 — document-first Kuwait bank certificate (OCR) qualification.

Authority preserved:
  employee submit = proposed
  HR approve = verified
  Apply = payroll-effective
  OCR never writes verified or effective

Runs unit checks locally, then live HTTP against the running orchestrator when
WATHEFNI_QUAL_BASE is reachable (production canary host).

Synthetic canaries only. Does not rewrite real-bank allowlists.
"""

from __future__ import annotations

import io
import json
import os
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

OUT_DIR = Path(os.environ.get("WATHEFNI_QUAL_OUT", "/tmp/bank-ess-p1"))
BASE_URL = os.environ.get("WATHEFNI_QUAL_BASE", "http://127.0.0.1:8010")
COMPANY = "WATHEFNI"
RUN_TAG = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
GOOD_IBAN = "KW81CBKU0000000000001234560101"
GOOD_IBAN_2 = "KW16NBOK0000000000001234560101"

RESULTS: dict[str, Any] = {"run_tag": RUN_TAG, "unit": [], "live": [], "errors": []}


def log(msg: str) -> None:
    print(f"[{datetime.now(timezone.utc).strftime('%H:%M:%S')}] {msg}", flush=True)


def record(section: str, case: str, ok: bool, detail: Any = None) -> None:
    RESULTS[section].append({"case": case, "verdict": "proven" if ok else "failed", "detail": detail})
    log(f"  [{'PASS' if ok else 'FAIL'}] {case}" + (f" :: {json.dumps(detail, default=str)[:240]}" if detail else ""))


def check(section: str, case: str, ok: bool, detail: Any = None) -> bool:
    record(section, case, ok, detail)
    return ok


def run_unit() -> None:
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import employee_bank_ess as bank
    from kuwait_gcc_document_intelligence.schemas import (
        STRUCTURING_TYPES,
        bank_certificate_json_schema,
        normalize_document_type,
    )

    check("unit", "contract_version_p1", bank.CONTRACT_VERSION == "bank_ess_v1_p1_document_first", bank.CONTRACT_VERSION)
    check("unit", "bank_certificate_in_structuring", "bank_certificate" in STRUCTURING_TYPES)
    check("unit", "iban_letter_alias", normalize_document_type("iban_letter") == "bank_certificate")
    schema = bank_certificate_json_schema()
    required = set(schema.get("required") or [])
    check(
        "unit",
        "extraction_schema_has_kw_fields",
        {"bank_name", "account_holder", "iban", "account_number"} <= set((schema.get("properties") or {}).keys())
        and {"bank_name", "account_holder", "iban", "account_number", "overall_confidence", "document_type"} <= required,
        sorted((schema.get("properties") or {}).keys()),
    )

    good = bank.sanitize_bank_extraction(
        {
            "extraction_status": "extracted",
            "confidence": 0.92,
            "fields": {
                "bank_name": {"value": "National Bank of Kuwait", "confidence": 0.9},
                "account_holder": {"value": "Aziz Al Mulla", "confidence": 0.88},
                "iban": {"value": "KW81 CBKU 0000 0000 0000 1234 5601 01", "confidence": 0.95},
                "account_number": {"value": "1234560101", "confidence": 0.8},
            },
            "warnings": [],
        }
    )
    check(
        "unit",
        "sanitize_good_certificate",
        good["authoritative"] is False
        and good["proposed"].get("iban") == GOOD_IBAN
        and good["needs_manual_fallback"] is False
        and good["status"] == "extracted",
        {"proposed": good["proposed"], "status": good["status"]},
    )

    partial = bank.sanitize_bank_extraction(
        {
            "extraction_status": "partial",
            "confidence": 0.4,
            "fields": {"iban": {"value": GOOD_IBAN, "confidence": 0.4}},
            "warnings": ["low_confidence_iban"],
        }
    )
    check(
        "unit",
        "sanitize_uncertain_partial",
        partial["uncertain"] is True and partial["authoritative"] is False and bool(partial["proposed"].get("iban")),
        partial,
    )

    failed = bank.sanitize_bank_extraction(
        {"extraction_status": "failed", "confidence": 0.0, "fields": {}, "warnings": ["unreadable"]}
    )
    check(
        "unit",
        "sanitize_failed_manual_fallback",
        failed["needs_manual_fallback"] is True and failed["authoritative"] is False and failed["proposed"] == {},
        failed,
    )

    check("unit", "bank_ocr_default_on", bank.bank_ocr_enabled(company_code=COMPANY) is True)


def _tiny_png() -> bytes:
    # 1x1 PNG
    return (
        b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x02\x00\x00\x00\x90wS\xde"
        b"\x00\x00\x00\x0cIDATx\x9cc\xf8\x0f\x00\x00\x01\x01\x00\x05\x18\xd8N\x00\x00\x00\x00IEND\xaeB`\x82"
    )


def _textish_pdf() -> bytes:
    # Minimal PDF with visible text stream for OCR attempts.
    content = (
        b"BT /F1 12 Tf 50 700 Td (National Bank of Kuwait IBAN Letter) Tj ET "
        b"BT /F1 12 Tf 50 680 Td (Account Holder QUAL CANARY) Tj ET "
        b"BT /F1 12 Tf 50 660 Td (IBAN KW81CBKU0000000000001234560101) Tj ET "
        b"BT /F1 12 Tf 50 640 Td (Account Number 1234560101) Tj ET"
    )
    objects = []
    objects.append(b"1 0 obj<< /Type /Catalog /Pages 2 0 R >>endobj\n")
    objects.append(b"2 0 obj<< /Type /Pages /Kids [3 0 R] /Count 1 >>endobj\n")
    objects.append(
        b"3 0 obj<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
        b"/Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>endobj\n"
    )
    stream = b"<< /Length %d >>stream\n" % len(content) + content + b"\nendstream\nendobj\n"
    objects.append(b"4 0 obj" + stream)
    objects.append(b"5 0 obj<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>endobj\n")
    out = io.BytesIO()
    out.write(b"%PDF-1.4\n")
    offsets = [0]
    for obj in objects:
        offsets.append(out.tell())
        out.write(obj)
    xref = out.tell()
    out.write(f"xref\n0 {len(offsets)}\n".encode())
    out.write(b"0000000000 65535 f \n")
    for off in offsets[1:]:
        out.write(f"{off:010d} 00000 n \n".encode())
    out.write(f"trailer<< /Size {len(offsets)} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode())
    return out.getvalue()


def run_live_embedded() -> None:
    """Live path: load sibling qual matrix helpers by path."""
    import importlib.util

    matrix_path = Path(__file__).resolve().parent / "ops-smoke-bank-ess-onboarding-qual-matrix.py"
    spec = importlib.util.spec_from_file_location("bank_qual_matrix", matrix_path)
    if not spec or not spec.loader:
        RESULTS["errors"].append("cannot load qual matrix module")
        check("live", "live_runner_boot", False, "missing matrix module")
        return
    # Avoid the matrix's real-allowlist refusal by clearing before exec.
    os.environ["WATHEFNI_EMPLOYEE_ESS_V5_BANK_REAL_ALLOWLIST"] = ""
    matrix = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(matrix)

    import app
    import employee_bank_ess as bank

    # Use the same allowlisted synthetic keys as the main qual matrix
    # (WATHEFNI_BANK_ESS_V1_EMPLOYEE_ALLOWLIST includes 7001/7002).
    keys = ["WATHEFNI-9655497001", "WATHEFNI-9655497002"]
    matrix.cleanup(app, keys)
    emp = matrix.create_canary(app, suffix="7001")
    other = matrix.create_canary(app, suffix="7002", seed_items=False)
    RESULTS["created_canaries"] = keys
    matrix.seed_canary_items(
        app,
        emp["employee_key"],
        [
            {
                "item_id": "bank_details",
                "required": True,
                "owner": "employee",
                "status": "pending",
                "authority": "ess",
                "item_type": "bank",
                "collection_mode": "ess_encrypted",
            }
        ],
    )
    sess = app.create_employee_session(COMPANY, emp["employee_key"], emp["phone"])
    other_sess = app.create_employee_session(COMPANY, other["employee_key"], other["phone"])
    token = str(sess["token"])
    other_token = str(other_sess["token"])

    hr_token = None
    try:
        with app.db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT * FROM dashboard_users
                    WHERE company_code=%s AND lower(coalesce(role,'')) IN ('owner','admin','hr_admin','hr')
                    ORDER BY created_at LIMIT 1
                    """,
                    (COMPANY,),
                )
                hr_user = dict(cur.fetchone() or {})
            conn.commit()
        if hr_user:
            tok, _ = app.create_dashboard_session(hr_user)
            hr_token = str(tok)
    except Exception as exc:
        RESULTS["errors"].append(f"dashboard session: {exc}")

    key = emp["employee_key"]
    with app.db_connect() as conn:
        with conn.cursor() as cur:
            bank.ensure_bank_ess_schema(cur)
            cur.execute(
                "SELECT count(*) c FROM employee_bank_verified WHERE employee_key=%s AND revoked_at IS NULL",
                (key,),
            )
            v0 = int(dict(cur.fetchone() or {}).get("c") or 0)
            cur.execute("SELECT count(*) c FROM employee_bank_effective WHERE employee_key=%s", (key,))
            e0 = int(dict(cur.fetchone() or {}).get("c") or 0)
        conn.commit()

    pdf_body = (
        matrix.upload_evidence(
            token,
            None,
            return_body=True,
            filename="kw-iban-letter.pdf",
            content_type="application/pdf",
            payload=_textish_pdf(),
        )
        or {}
    )
    pdf_id = str(pdf_body.get("evidence_id") or "")
    pdf_ex = pdf_body.get("extraction") if isinstance(pdf_body.get("extraction"), dict) else {}
    check(
        "live",
        "pdf_upload_extraction_shape",
        bool(pdf_id)
        and pdf_ex.get("authoritative") is False
        and isinstance(pdf_body.get("proposed_fields"), dict)
        and "needs_manual_fallback" in pdf_body,
        {
            "evidence_id": pdf_id,
            "status": pdf_ex.get("status"),
            "fallback": pdf_body.get("needs_manual_fallback"),
            "proposed": pdf_body.get("proposed_fields"),
        },
    )

    img_body = (
        matrix.upload_evidence(
            token,
            None,
            return_body=True,
            filename="kw-iban-letter.png",
            content_type="image/png",
            payload=_tiny_png(),
        )
        or {}
    )
    img_id = str(img_body.get("evidence_id") or "")
    img_ex = img_body.get("extraction") if isinstance(img_body.get("extraction"), dict) else {}
    check(
        "live",
        "image_upload_manual_fallback_ok",
        bool(img_id)
        and img_ex.get("authoritative") is False
        and (img_body.get("needs_manual_fallback") is True or bool(img_body.get("proposed_fields"))),
        {
            "evidence_id": img_id,
            "status": img_ex.get("status"),
            "fallback": img_body.get("needs_manual_fallback"),
        },
    )

    with app.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT count(*) c FROM employee_bank_verified WHERE employee_key=%s AND revoked_at IS NULL",
                (key,),
            )
            v1 = int(dict(cur.fetchone() or {}).get("c") or 0)
            cur.execute("SELECT count(*) c FROM employee_bank_effective WHERE employee_key=%s", (key,))
            e1 = int(dict(cur.fetchone() or {}).get("c") or 0)
        conn.commit()
    check(
        "live",
        "ocr_upload_leaves_verified_effective_untouched",
        v1 == v0 and e1 == e0,
        {"v0": v0, "v1": v1, "e0": e0, "e1": e1},
    )

    proposed = dict(pdf_body.get("proposed_fields") or {})
    proposed["iban"] = GOOD_IBAN
    proposed["bank_name"] = proposed.get("bank_name") or "NBK"
    proposed["account_holder"] = proposed.get("account_holder") or "QUAL CANARY P1"
    evidence_ids = [x for x in [pdf_id, img_id] if x]
    code, body = matrix.http(
        "POST",
        "/app/bank/requests",
        token=token,
        body={
            **{k: v for k, v in proposed.items() if v},
            "idempotency_key": f"p1-doc-{RUN_TAG}-{uuid.uuid4().hex[:8]}",
            "evidence_ids": evidence_ids,
        },
    )
    bank_view = body.get("bank") or {}
    rid = ((bank_view.get("submission") or {}) or {}).get("request_id")
    check(
        "live",
        "document_first_submit_proposed",
        code == 200 and bank_view.get("submission_state") == "pending_hr" and bool(rid),
        {"code": code, "state": bank_view.get("submission_state"), "request_id": rid},
    )

    if rid and evidence_ids:
        with app.db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT count(*) c FROM employee_bank_evidence
                    WHERE request_id=%s AND employee_key=%s AND deleted_at IS NULL
                      AND evidence_id::text = ANY(%s)
                    """,
                    (rid, key, evidence_ids),
                )
                linked = int(dict(cur.fetchone() or {}).get("c") or 0)
            conn.commit()
        check(
            "live",
            "evidence_linked_to_request",
            linked == len(evidence_ids),
            {"linked": linked, "expected": len(evidence_ids)},
        )

    matrix.clear_active_bank_request(token)
    code_bad, body_bad = matrix.http(
        "POST",
        "/app/bank/requests",
        token=token,
        body={
            "iban": "KW00INVALID000000000000000000",
            "bank_name": "NBK",
            "idempotency_key": f"p1-badiban-{RUN_TAG}-{uuid.uuid4().hex[:8]}",
            "evidence_ids": [pdf_id] if pdf_id else None,
        },
    )
    check(
        "live",
        "invalid_kw_iban_rejected",
        code_bad == 422 and matrix.err_of(body_bad) == "bank_account_invalid",
        {"code": code_bad, "error": matrix.err_of(body_bad)},
    )

    matrix.clear_active_bank_request(token)
    replace_body = (
        matrix.upload_evidence(
            token,
            None,
            return_body=True,
            filename="kw-iban-letter-replace.pdf",
            content_type="application/pdf",
            payload=_textish_pdf(),
        )
        or {}
    )
    replace_id = str(replace_body.get("evidence_id") or "")
    code2, body2 = matrix.http(
        "POST",
        "/app/bank/requests",
        token=token,
        body={
            "iban": GOOD_IBAN_2,
            "bank_name": "Gulf Bank",
            "account_holder": "QUAL CANARY P1 REPLACE",
            "idempotency_key": f"p1-replace-{RUN_TAG}-{uuid.uuid4().hex[:8]}",
            "evidence_ids": [replace_id] if replace_id else None,
        },
    )
    rid2 = (((body2.get("bank") or {}).get("submission") or {}) or {}).get("request_id")
    check(
        "live",
        "replacement_resubmit_with_new_evidence",
        code2 == 200 and bool(rid2) and bool(replace_id),
        {"code": code2, "request_id": rid2, "evidence_id": replace_id},
    )

    if rid2 and hr_token:
        with app.db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT concurrency_version FROM employee_ess_requests WHERE request_id=%s",
                    (rid2,),
                )
                ver = int(dict(cur.fetchone() or {}).get("concurrency_version") or 0)
                eff_before = bank.current_effective(cur, company_code=COMPANY, employee_key=key)
            conn.commit()
        code_a, _ = matrix.hr_decide(
            hr_token,
            str(rid2),
            "approve",
            comment="P1 qual HR approve",
            expected_concurrency_version=ver,
        )
        check("live", "hr_verify_approve", code_a == 200, {"code": code_a})
        with app.db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT verified_by_stage FROM employee_bank_verified
                    WHERE employee_key=%s AND request_id=%s AND revoked_at IS NULL
                    ORDER BY verified_at DESC LIMIT 1
                    """,
                    (key, rid2),
                )
                vrow = dict(cur.fetchone() or {})
                eff_mid = bank.current_effective(cur, company_code=COMPANY, employee_key=key)
            conn.commit()
        check(
            "live",
            "hr_approve_stamps_verified_not_effective",
            str(vrow.get("verified_by_stage")) == "hr"
            and (eff_mid or {}).get("fingerprint") == (eff_before or {}).get("fingerprint"),
            {
                "verified_by_stage": vrow.get("verified_by_stage"),
                "eff_changed": (eff_mid or {}).get("fingerprint")
                != (eff_before or {}).get("fingerprint"),
            },
        )

        # Dual-control: payroll approve then apply.
        with app.db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT concurrency_version, state FROM employee_ess_requests WHERE request_id=%s",
                    (rid2,),
                )
                row2 = dict(cur.fetchone() or {})
            conn.commit()
        if str(row2.get("state")) == "pending_payroll":
            matrix.hr_decide(
                hr_token,
                str(rid2),
                "approve",
                comment="P1 qual payroll approve",
                expected_concurrency_version=int(row2.get("concurrency_version") or 0),
            )
        code_app, body_app = matrix.hr_apply(
            hr_token, str(rid2), idempotency_key=f"p1-apply-{rid2}"
        )
        with app.db_connect() as conn:
            with conn.cursor() as cur:
                eff_after = bank.current_effective(cur, company_code=COMPANY, employee_key=key)
            conn.commit()
        check(
            "live",
            "payroll_apply_writes_effective",
            code_app == 200
            and bool(eff_after)
            and (eff_after or {}).get("fingerprint") == bank.fingerprint(GOOD_IBAN_2),
            {
                "apply_code": code_app,
                "eff_fp": (eff_after or {}).get("fingerprint"),
                "expected_fp": bank.fingerprint(GOOD_IBAN_2),
                "error": matrix.err_of(body_app),
            },
        )
    elif rid2:
        check("live", "hr_verify_approve", False, "no hr token")

    code_en, _ = matrix.http("GET", "/app/bank?locale=en", token=token)
    code_ar, body_ar = matrix.http("GET", "/app/bank?locale=ar", token=token)
    msg_ar = ((body_ar.get("next_step") or {}).get("message") or "")
    check(
        "live",
        "en_ar_bank_status",
        code_en == 200
        and code_ar == 200
        and bool(msg_ar)
        and any("\u0600" <= ch <= "\u06ff" for ch in msg_ar),
        {"en": code_en, "ar": code_ar, "ar_msg": msg_ar[:80]},
    )

    if pdf_id:
        code_x, _ = matrix.http("GET", f"/app/bank/evidence/{pdf_id}", token=other_token)
        check("live", "evidence_isolated", code_x in (403, 404), {"code": code_x})

    try:
        matrix.cleanup(app, keys)
    except Exception as exc:
        RESULTS["errors"].append(f"cleanup: {exc}")


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    log("Bank ESS P1 document-first qualification")
    run_unit()
    live = (os.environ.get("WATHEFNI_P1_LIVE") or "on").strip().lower() not in {"0", "off", "false", "no"}
    if live:
        try:
            run_live_embedded()
        except SystemExit as exc:
            RESULTS["errors"].append(f"live SystemExit: {exc}")
            check("live", "live_runner_boot", False, str(exc))
        except Exception as exc:
            RESULTS["errors"].append(f"live: {type(exc).__name__}: {exc}")
            check("live", "live_runner_boot", False, f"{type(exc).__name__}: {exc}")
    else:
        log("live skipped (WATHEFNI_P1_LIVE=off)")

    unit_fail = sum(1 for r in RESULTS["unit"] if r["verdict"] != "proven")
    live_fail = sum(1 for r in RESULTS["live"] if r["verdict"] != "proven")
    unit_pass = sum(1 for r in RESULTS["unit"] if r["verdict"] == "proven")
    live_pass = sum(1 for r in RESULTS["live"] if r["verdict"] == "proven")
    RESULTS["summary"] = {
        "unit": f"{unit_pass}/{unit_pass + unit_fail}",
        "live": f"{live_pass}/{live_pass + live_fail}",
        "errors": RESULTS["errors"],
    }
    out = OUT_DIR / f"p1-{RUN_TAG}.json"
    out.write_text(json.dumps(RESULTS, indent=2, default=str))
    log(f"summary {RESULTS['summary']} → {out}")
    return 0 if unit_fail == 0 and live_fail == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
