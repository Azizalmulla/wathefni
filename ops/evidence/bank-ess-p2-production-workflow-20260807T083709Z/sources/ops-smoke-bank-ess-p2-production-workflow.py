#!/usr/bin/env python3
"""Bank ESS P2 — production workflow qualification (WATHEFNI canary).

P1 OCR path is frozen. This proves the employee production loop:
  upload → extract → confirm/correct → proposed → HR → payroll → Apply

Uses the real Gulf Bank certificate when present at
  /tmp/kw-bank-cert-realdoc.pdf
or WATHEFNI_P2_FIXTURE_PDF.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

OUT_DIR = Path(os.environ.get("WATHEFNI_QUAL_OUT", "/tmp/bank-ess-p2"))
BASE_URL = os.environ.get("WATHEFNI_QUAL_BASE", "http://127.0.0.1:8010")
COMPANY = "WATHEFNI"
RUN_TAG = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
FIXTURE = Path(os.environ.get("WATHEFNI_P2_FIXTURE_PDF", "/tmp/kw-bank-cert-realdoc.pdf"))

RESULTS: dict[str, Any] = {"run_tag": RUN_TAG, "unit": [], "live": [], "errors": []}


def log(msg: str) -> None:
    print(f"[{datetime.now(timezone.utc).strftime('%H:%M:%S')}] {msg}", flush=True)


def check(section: str, case: str, ok: bool, detail: Any = None) -> bool:
    RESULTS[section].append({"case": case, "verdict": "PASS" if ok else "FAIL", "detail": detail})
    log(f"  [{'PASS' if ok else 'FAIL'}] {case}" + (f" :: {json.dumps(detail, default=str)[:280]}" if detail is not None else ""))
    return ok


def mask_iban(v: str | None) -> str | None:
    s = re.sub(r"[^A-Za-z0-9]", "", str(v or "").upper())
    return (s[:4] + "…" + s[-4:]) if len(s) >= 8 else (s or None)


def run_unit() -> None:
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import employee_bank_ess as bank
    from kuwait_gcc_document_intelligence.extraction import _sniff_mime

    check("unit", "contract_version_p2", bank.CONTRACT_VERSION == "bank_ess_v1_p2_production_workflow", bank.CONTRACT_VERSION)
    check("unit", "p1_mime_sniff_frozen", _sniff_mime(b"%PDF-1.7\n", path=None) == "application/pdf")
    wrong = bank.sanitize_bank_extraction(
        {
            "extraction_status": "extracted",
            "confidence": 0.7,
            "fields": {"document_type": {"value": "passport"}, "bank_name": {"value": "X"}},
        }
    )
    check("unit", "wrong_document_type_flag", wrong.get("wrong_document_type") is True and wrong.get("missing_iban") is True, wrong)
    masked = bank.sanitize_bank_extraction(
        {
            "extraction_status": "extracted",
            "confidence": 0.98,
            "fields": {
                "iban": {"value": "KW35GULB0000000000000096259548", "confidence": 1},
                "bank_name": {"value": "Gulf Bank", "confidence": 1},
            },
        },
        mask_sensitive=True,
    )
    check(
        "unit",
        "p1_hr_masking_frozen",
        "*" in str(masked["proposed"].get("iban")) and masked["proposed"].get("bank_name") == "Gulf Bank",
        masked["proposed"],
    )


def run_live() -> None:
    import importlib.util

    matrix_path = Path(__file__).resolve().parent / "ops-smoke-bank-ess-onboarding-qual-matrix.py"
    spec = importlib.util.spec_from_file_location("bank_qual_matrix", matrix_path)
    os.environ["WATHEFNI_EMPLOYEE_ESS_V5_BANK_REAL_ALLOWLIST"] = ""
    matrix = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
    assert spec and spec.loader
    spec.loader.exec_module(matrix)

    import app
    import employee_bank_ess as bank
    import identity_document_extraction as ide

    ide.reset_circuit_for_tests()
    if not FIXTURE.is_file() or FIXTURE.stat().st_size < 10000:
        check("live", "real_fixture_present", False, {"path": str(FIXTURE)})
        return
    pdf_bytes = FIXTURE.read_bytes()
    RESULTS["fixture"] = {"path": str(FIXTURE), "sha256": hashlib.sha256(pdf_bytes).hexdigest(), "bytes": len(pdf_bytes)}

    keys = ["WATHEFNI-9655497001", "WATHEFNI-9655497002"]
    matrix.cleanup(app, keys)
    emp = matrix.create_canary(app, suffix="7001")
    other = matrix.create_canary(app, suffix="7002", seed_items=False)
    key = emp["employee_key"]
    token = str(app.create_employee_session(COMPANY, key, emp["phone"])["token"])
    other_token = str(app.create_employee_session(COMPANY, other["employee_key"], other["phone"])["token"])

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
    hr_token = str(app.create_dashboard_session(hr_user)[0]) if hr_user else None

    with app.db_connect() as conn:
        with conn.cursor() as cur:
            aziz_fp0 = (
                bank.current_effective(cur, company_code=COMPANY, employee_key="WATHEFNI-96599338566") or {}
            ).get("fingerprint")
        conn.commit()

    # Seed effective bank
    code, body = matrix.http(
        "POST",
        "/app/bank/requests",
        token=token,
        body={
            "iban": matrix.GOOD_IBAN,
            "bank_name": "NBK",
            "account_holder": "QUAL SEED",
            "idempotency_key": f"p2-seed-{uuid.uuid4().hex[:8]}",
        },
    )
    rid0 = (((body.get("bank") or {}).get("submission") or {}) or {}).get("request_id")
    check("live", "seed_request", code == 200 and bool(rid0), {"code": code})
    if rid0 and hr_token:
        with app.db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT concurrency_version FROM employee_ess_requests WHERE request_id=%s", (rid0,))
                ver = int(dict(cur.fetchone() or {}).get("concurrency_version") or 0)
            conn.commit()
        matrix.hr_decide(hr_token, str(rid0), "approve", comment="p2 seed hr", expected_concurrency_version=ver)
        with app.db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT concurrency_version, state FROM employee_ess_requests WHERE request_id=%s", (rid0,))
                row = dict(cur.fetchone() or {})
            conn.commit()
        if str(row.get("state")) == "pending_payroll":
            matrix.hr_decide(
                hr_token,
                str(rid0),
                "approve",
                comment="p2 seed payroll",
                expected_concurrency_version=int(row.get("concurrency_version") or 0),
            )
        matrix.hr_apply(hr_token, str(rid0), idempotency_key=f"p2-seed-apply-{rid0}")

    with app.db_connect() as conn:
        with conn.cursor() as cur:
            seed_fp = (bank.current_effective(cur, company_code=COMPANY, employee_key=key) or {}).get("fingerprint")
        conn.commit()
    check("live", "seed_effective", bool(seed_fp), {"fp": seed_fp})

    # Upload real certificate
    up = (
        matrix.upload_evidence(
            token,
            None,
            return_body=True,
            filename="1786090542147.pdf",
            content_type="application/pdf",
            payload=pdf_bytes,
        )
        or {}
    )
    ev_id = str(up.get("evidence_id") or "")
    ex = up.get("extraction") if isinstance(up.get("extraction"), dict) else {}
    proposed = dict(up.get("proposed_fields") or ex.get("proposed") or {})
    iban = re.sub(r"[^A-Za-z0-9]", "", str(proposed.get("iban") or "").upper())
    check("live", "upload_extract_rich", bool(ev_id) and bool(proposed.get("bank_name")) and len(iban) == 30, {
        "bank": proposed.get("bank_name"),
        "iban": mask_iban(iban),
        "status": ex.get("status"),
        "confidence": ex.get("confidence"),
        "authoritative": ex.get("authoritative"),
    })
    check("live", "extract_non_authoritative", ex.get("authoritative") is False)
    check("live", "kw_iban_valid", bool(bank.validate_account({"iban": iban}, scheme="kw_iban").get("ok")), {"iban": mask_iban(iban)})

    # Employee confirm/correct (light correction on holder whitespace)
    corrected = {
        "iban": iban,
        "bank_name": proposed.get("bank_name") or "Gulf Bank",
        "account_holder": " ".join(str(proposed.get("account_holder") or "QUAL").split()),
    }
    if proposed.get("account_number"):
        corrected["account_number"] = proposed["account_number"]
    for opt in ("branch", "swift"):
        if proposed.get(opt):
            corrected[opt] = proposed[opt]

    # Duplicate idempotency
    idem = f"p2-submit-{uuid.uuid4().hex[:8]}"
    code1, body1 = matrix.http(
        "POST",
        "/app/bank/requests",
        token=token,
        body={**corrected, "idempotency_key": idem, "evidence_ids": [ev_id]},
    )
    rid = (((body1.get("bank") or {}).get("submission") or {}) or {}).get("request_id")
    check("live", "confirm_correct_submit", code1 == 200 and (body1.get("bank") or {}).get("submission_state") == "pending_hr", {
        "code": code1,
        "state": (body1.get("bank") or {}).get("submission_state"),
        "request_id": rid,
    })
    code_dup, body_dup = matrix.http(
        "POST",
        "/app/bank/requests",
        token=token,
        body={**corrected, "iban": matrix.GOOD_IBAN_2, "idempotency_key": f"p2-dup-{uuid.uuid4().hex[:8]}"},
    )
    check(
        "live",
        "duplicate_submit_blocked",
        code_dup == 409 and matrix.err_of(body_dup) == "bank_request_already_active",
        {"code": code_dup, "error": matrix.err_of(body_dup)},
    )
    code_idem, body_idem = matrix.http(
        "POST",
        "/app/bank/requests",
        token=token,
        body={**corrected, "idempotency_key": idem, "evidence_ids": [ev_id]},
    )
    check("live", "idempotent_resubmit", code_idem == 200 and body_idem.get("idempotent") is True, {
        "code": code_idem,
        "idempotent": body_idem.get("idempotent"),
    })

    # Invalid KW IBAN (withdraw first)
    matrix.clear_active_bank_request(token)
    code_bad, body_bad = matrix.http(
        "POST",
        "/app/bank/requests",
        token=token,
        body={
            "iban": "KW00INVALID000000000000000000",
            "bank_name": "Gulf Bank",
            "idempotency_key": f"p2-badiban-{uuid.uuid4().hex[:8]}",
            "evidence_ids": [ev_id],
        },
    )
    check("live", "invalid_kw_iban_rejected", code_bad == 422 and matrix.err_of(body_bad) == "bank_account_invalid", {
        "code": code_bad,
        "error": matrix.err_of(body_bad),
    })

    # Resubmit good change with evidence
    code2, body2 = matrix.http(
        "POST",
        "/app/bank/requests",
        token=token,
        body={**corrected, "idempotency_key": f"p2-final-{uuid.uuid4().hex[:8]}", "evidence_ids": [ev_id]},
    )
    rid2 = (((body2.get("bank") or {}).get("submission") or {}) or {}).get("request_id")
    check("live", "resubmit_with_evidence", code2 == 200 and bool(rid2), {"code": code2, "request_id": rid2})

    with app.db_connect() as conn:
        with conn.cursor() as cur:
            mid_fp = (bank.current_effective(cur, company_code=COMPANY, employee_key=key) or {}).get("fingerprint")
            cur.execute(
                "SELECT count(*) c FROM employee_bank_verified WHERE employee_key=%s AND request_id=%s AND revoked_at IS NULL",
                (key, rid2),
            )
            v_req = int(dict(cur.fetchone() or {}).get("c") or 0)
        conn.commit()
    check("live", "effective_unchanged_until_apply", mid_fp == seed_fp, {"seed": seed_fp, "mid": mid_fp})
    check("live", "submit_did_not_write_verified", v_req == 0, {"count": v_req})

    check("live", "evidence_private", matrix.http("GET", f"/app/bank/evidence/{ev_id}", token=other_token)[0] in (403, 404))

    if hr_token and rid2:
        code_hr, body_hr = matrix.http(
            "GET",
            f"/dashboard/posthire/employees/{key}/bank",
            dashboard_token=hr_token,
        )
        comp = (body_hr or {}).get("comparison") or {}
        matched = next(
            (r for r in (((body_hr.get("submission") or {}).get("evidence")) or []) if str(r.get("evidence_id")) == ev_id),
            None,
        )
        extr = (matched or {}).get("extraction") or {}
        prop_iban = (extr.get("proposed") or {}).get("iban")
        check(
            "live",
            "hr_current_vs_proposed_vs_extracted",
            code_hr == 200
            and bool(comp.get("proposed"))
            and isinstance(matched, dict)
            and bool((extr.get("proposed") or {}).get("bank_name")),
            {
                "changed": comp.get("changed_fields"),
                "extract_status": extr.get("status"),
                "extract_iban": prop_iban,
            },
        )
        check(
            "live",
            "hr_extraction_masked",
            not matrix.contains_plaintext(body_hr, iban) and bool(prop_iban) and "*" in str(prop_iban),
            {"leaked": matrix.contains_plaintext(body_hr, iban), "extract_iban": prop_iban},
        )

        with app.db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT concurrency_version FROM employee_ess_requests WHERE request_id=%s", (rid2,))
                ver = int(dict(cur.fetchone() or {}).get("concurrency_version") or 0)
            conn.commit()
        matrix.hr_decide(hr_token, str(rid2), "approve", comment="p2 hr", expected_concurrency_version=ver)
        with app.db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT concurrency_version, state FROM employee_ess_requests WHERE request_id=%s", (rid2,))
                row = dict(cur.fetchone() or {})
                mid2 = (bank.current_effective(cur, company_code=COMPANY, employee_key=key) or {}).get("fingerprint")
            conn.commit()
        check("live", "hr_verify_not_effective", mid2 == seed_fp and str(row.get("state")) in {"pending_payroll", "approved"}, {
            "state": row.get("state"),
            "fp": mid2,
        })
        if str(row.get("state")) == "pending_payroll":
            matrix.hr_decide(
                hr_token,
                str(rid2),
                "approve",
                comment="p2 payroll",
                expected_concurrency_version=int(row.get("concurrency_version") or 0),
            )
        code_app, _ = matrix.hr_apply(hr_token, str(rid2), idempotency_key=f"p2-apply-{rid2}")
        with app.db_connect() as conn:
            with conn.cursor() as cur:
                after = bank.current_effective(cur, company_code=COMPANY, employee_key=key) or {}
            conn.commit()
        check(
            "live",
            "apply_writes_effective",
            code_app == 200 and after.get("fingerprint") == bank.fingerprint(iban),
            {"code": code_app, "fp": after.get("fingerprint"), "expected": bank.fingerprint(iban)},
        )

    with app.db_connect() as conn:
        with conn.cursor() as cur:
            aziz = (
                bank.current_effective(cur, company_code=COMPANY, employee_key="WATHEFNI-96599338566") or {}
            ).get("fingerprint")
        conn.commit()
    check("live", "aziz_effective_unchanged", aziz == aziz_fp0 == "0f349ce848ab5e4b", {"before": aziz_fp0, "after": aziz})

    # Failure-state projection (unit-like via sanitize already covered; live EN/AR)
    code_ar, body_ar = matrix.http("GET", "/app/bank?locale=ar", token=token)
    msg = ((body_ar.get("next_step") or {}).get("message") or "")
    check("live", "ar_next_step", code_ar == 200 and any("\u0600" <= ch <= "\u06ff" for ch in msg), {"msg": msg[:80]})

    try:
        matrix.cleanup(app, keys)
    except Exception as exc:
        RESULTS["errors"].append(str(exc))


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    log("Bank ESS P2 production workflow qualification")
    run_unit()
    if (os.environ.get("WATHEFNI_P2_LIVE") or "on").strip().lower() not in {"0", "off", "false", "no"}:
        try:
            run_live()
        except SystemExit as exc:
            RESULTS["errors"].append(f"SystemExit: {exc}")
            check("live", "live_boot", False, str(exc))
        except Exception as exc:
            RESULTS["errors"].append(f"{type(exc).__name__}: {exc}")
            check("live", "live_boot", False, f"{type(exc).__name__}: {exc}")
    fails = [r for sec in ("unit", "live") for r in RESULTS[sec] if r["verdict"] != "PASS"]
    RESULTS["summary"] = {
        "unit": f"{sum(1 for r in RESULTS['unit'] if r['verdict']=='PASS')}/{len(RESULTS['unit'])}",
        "live": f"{sum(1 for r in RESULTS['live'] if r['verdict']=='PASS')}/{len(RESULTS['live'])}",
        "verdict": "PASS" if not fails else "FAIL",
        "errors": RESULTS["errors"],
    }
    out = OUT_DIR / f"p2-{RUN_TAG}.json"
    out.write_text(json.dumps(RESULTS, indent=2, default=str))
    log(f"summary {RESULTS['summary']} → {out}")
    return 0 if not fails else 1


if __name__ == "__main__":
    raise SystemExit(main())
