#!/usr/bin/env python3
"""Live-HTTP production qualification matrix — Bank ESS + onboarding completion.

Employee paths run over live HTTP against the running uvicorn using a minted
employee session. HR paths run over live HTTP using a minted dashboard session.
Backend invariants are asserted directly against Postgres.

Synthetic canary employees only (ESS synthetic phone prefix + name prefix).
Never touches a real employee's verified bank data or accepted documents.

Run on the production host:
  WATHEFNI_ENV=production ... python3 ops-smoke-bank-ess-onboarding-qual-matrix.py
"""

from __future__ import annotations

import json
import os
import sys
import time
import traceback
import urllib.error
import urllib.request
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

BASE_URL = os.environ.get("WATHEFNI_QUAL_BASE", "http://127.0.0.1:8010")
REQUEST_TIMEOUT_S = float(os.environ.get("WATHEFNI_QUAL_REQ_TIMEOUT", "60"))
COMPANY = "WATHEFNI"
OTHER_COMPANY = os.environ.get("WATHEFNI_QUAL_OTHER_COMPANY", "")
OUT_DIR = Path(os.environ.get("WATHEFNI_QUAL_OUT", "/tmp/bank-ess-onboarding-qual"))

# Synthetic canary identities (ESS synthetic prefixes → real-bank guard bypassed).
SYNTH_PHONE_PREFIX = "965549"
SYNTH_NAME_PREFIX = "W5C-SYNTH|"
RUN_TAG = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")

LEGACY_SUFFIX = "7004"
CANARY_KEYS = [
    "WATHEFNI-9655497001",
    "WATHEFNI-9655497002",
    "WATHEFNI-9655497003",
    f"WATHEFNI-965549{LEGACY_SUFFIX}",
]

# This runner also makes in-process calls, so it must mirror the flags the
# deployed service already has. It only ever ADDS the synthetic canaries, and it
# refuses to run if the real-bank allowlist is non-empty.
_MIRROR_FLAGS = {
    "WATHEFNI_BANK_ESS_V1": "on",
    "WATHEFNI_BANK_ESS_V1_COMPANIES": COMPANY,
    "WATHEFNI_BANK_ESS_V1_EMPLOYEE_ALLOWLIST": ",".join(CANARY_KEYS),
    "WATHEFNI_ONBOARDING_COMPLETION_CONTRACT": "on",
    "WATHEFNI_ONBOARDING_COMPLETION_CONTRACT_COMPANIES": COMPANY,
    "WATHEFNI_EMPLOYEE_APP": "on",
    "WATHEFNI_EMPLOYEE_ESS_V5": "on",
    "WATHEFNI_EMPLOYEE_ESS_V5_COMPANIES": COMPANY,
    "WATHEFNI_EMPLOYEE_ESS_V5_SYNTHETIC_ONLY": "on",
    "WATHEFNI_EMPLOYEE_ESS_V5_SYNTHETIC_PHONE_PREFIXES": SYNTH_PHONE_PREFIX,
    "WATHEFNI_EMPLOYEE_ESS_V5_SYNTHETIC_NAME_PREFIX": SYNTH_NAME_PREFIX,
    "WATHEFNI_ONBOARDING_LIFECYCLE_V2A": "on",
    "WATHEFNI_ONBOARDING_LIFECYCLE_V2A_COMPANIES": COMPANY,
}
for _k, _v in _MIRROR_FLAGS.items():
    os.environ.setdefault(_k, _v)
for _k in (
    "WATHEFNI_EMPLOYEE_APP_REAL_ALLOWLIST",
    "WATHEFNI_ONBOARDING_LIFECYCLE_V2A_EMPLOYEE_ALLOWLIST",
):
    _existing = [x.strip() for x in (os.environ.get(_k) or "").split(",") if x.strip()]
    os.environ[_k] = ",".join(sorted(set(_existing) | set(CANARY_KEYS)))
if (os.environ.get("WATHEFNI_EMPLOYEE_ESS_V5_BANK_REAL_ALLOWLIST") or "").strip():
    raise SystemExit("refusing to run: real-bank allowlist must be empty for a synthetic matrix")

RESULTS: dict[str, Any] = {
    "run_tag": RUN_TAG,
    "base_url": BASE_URL,
    "bank_ess": [],
    "onboarding_completion": [],
    "created_canaries": [],
    "errors": [],
}


def log(msg: str) -> None:
    print(f"[{datetime.now(timezone.utc).strftime('%H:%M:%S')}] {msg}", flush=True)


def record(section: str, case: str, verdict: str, detail: Any = None) -> None:
    RESULTS[section].append({"case": case, "verdict": verdict, "detail": detail})
    mark = {"proven": "PASS", "partial": "PARTIAL", "failed": "FAIL", "skipped": "SKIP"}.get(
        verdict, verdict.upper()
    )
    log(f"  [{mark}] {case}" + (f" :: {json.dumps(detail, default=str)[:220]}" if detail else ""))


def check(section: str, case: str, ok: bool, detail: Any = None) -> bool:
    record(section, case, "proven" if ok else "failed", detail)
    return ok


# ---------------------------------------------------------------------------
# HTTP
# ---------------------------------------------------------------------------
def http(
    method: str,
    path: str,
    *,
    token: str | None = None,
    dashboard_token: str | None = None,
    body: dict[str, Any] | None = None,
) -> tuple[int, Any]:
    url = f"{BASE_URL}{path}"
    data = json.dumps(body).encode("utf-8") if body is not None else None
    headers = {"Accept": "application/json"}
    if data is not None:
        headers["Content-Type"] = "application/json"
    if token:
        headers["Authorization"] = f"Bearer {token}"
    if dashboard_token:
        headers["X-Dashboard-Token"] = dashboard_token
        headers["Authorization"] = f"Bearer {dashboard_token}"
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT_S) as resp:
            raw = resp.read().decode("utf-8", "replace")
            try:
                return resp.status, json.loads(raw)
            except Exception:
                return resp.status, {"raw": raw[:2000]}
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", "replace")
        try:
            return exc.code, json.loads(raw)
        except Exception:
            return exc.code, {"raw": raw[:2000]}
    except Exception as exc:
        return 0, {"error": type(exc).__name__, "detail": str(exc)[:300]}


def contains_plaintext(blob: Any, secret: str) -> bool:
    """Does a response/log/db payload leak the full account identifier?"""
    if not secret:
        return False
    return secret.upper() in json.dumps(blob, default=str).upper()


# ---------------------------------------------------------------------------
# Canary lifecycle
# ---------------------------------------------------------------------------
def create_canary(app: Any, *, suffix: str, seed_items: bool = True) -> dict[str, Any]:
    phone = f"{SYNTH_PHONE_PREFIX}{suffix}"
    key = f"{COMPANY}-{phone}"
    name = f"{SYNTH_NAME_PREFIX}QUAL-{suffix}"
    with app.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO employees (company_code, employee_key, phone, name,
                                       onboarding_status, employment_status, created_at, updated_at)
                VALUES (%s,%s,%s,%s,'not_started','active',now(),now())
                ON CONFLICT (employee_key) DO UPDATE
                SET name=EXCLUDED.name, phone=EXCLUDED.phone, updated_at=now()
                """,
                (COMPANY, key, phone, name),
            )
        conn.commit()
    RESULTS["created_canaries"].append(key)
    if seed_items:
        seed_canary_items(app, key)
    return {"employee_key": key, "phone": phone, "name": name}


def seed_canary_items(app: Any, key: str, items: list[dict[str, Any]] | None = None) -> None:
    """Disposable checklist rows for completion-state testing."""
    rows = items or [
        {"item_id": "qual_doc_a", "required": True, "owner": "employee", "status": "pending"},
        {"item_id": "qual_doc_b", "required": True, "owner": "employee", "status": "pending"},
        {"item_id": "qual_hr_task", "required": True, "owner": "hr", "status": "pending"},
        {"item_id": "qual_optional", "required": False, "owner": "employee", "status": "pending"},
    ]
    with app.db_connect() as conn:
        with conn.cursor() as cur:
            for row in rows:
                cur.execute(
                    """
                    INSERT INTO onboarding_items (
                      employee_key, item_id, label, status, required, owner,
                      item_type, collection_mode, authority, depends_on,
                      created_at, updated_at
                    ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb,now(),now())
                    ON CONFLICT (employee_key, item_id) DO UPDATE
                    SET status=EXCLUDED.status, required=EXCLUDED.required,
                        owner=EXCLUDED.owner, depends_on=EXCLUDED.depends_on,
                        authority=EXCLUDED.authority, updated_at=now()
                    """,
                    (
                        key,
                        row["item_id"],
                        f"QUAL {row['item_id']}",
                        row["status"],
                        row["required"],
                        row["owner"],
                        row.get("item_type") or "document",
                        row.get("collection_mode") or "document",
                        row.get("authority") or "onboarding",
                        json.dumps(row.get("depends_on") or []),
                    ),
                )
        conn.commit()


def set_item(app: Any, key: str, item_id: str, status: str, **extra) -> None:
    with app.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE onboarding_items
                SET status=%s,
                    required=COALESCE(%s, required),
                    lifecycle_meta=COALESCE(lifecycle_meta,'{}'::jsonb) || %s::jsonb,
                    updated_at=now()
                WHERE employee_key=%s AND item_id=%s
                """,
                (
                    status,
                    extra.get("required"),
                    json.dumps(extra.get("meta") or {}),
                    key,
                    item_id,
                ),
            )
        conn.commit()


def hr_decide(hr_token: str | None, request_id: str, action: str, *,
              comment: str | None = None,
              expected_concurrency_version: int | None = None) -> tuple[int, Any]:
    """HR decision over real HTTP so dashboard_context permissions are exercised."""
    body: dict[str, Any] = {"action": action}
    if comment is not None:
        body["comment"] = comment
    if expected_concurrency_version is not None:
        body["expected_concurrency_version"] = expected_concurrency_version
    return http("POST", f"/dashboard/posthire/employee-ess/requests/{request_id}/decide",
                dashboard_token=hr_token, body=body)


def hr_apply(hr_token: str | None, request_id: str, *,
             idempotency_key: str | None = None) -> tuple[int, Any]:
    return http("POST", f"/dashboard/posthire/employee-ess/requests/{request_id}/apply",
                dashboard_token=hr_token,
                body={"idempotency_key": idempotency_key} if idempotency_key else {})


def err_of(body: Any) -> str:
    if not isinstance(body, dict):
        return ""
    detail = body.get("detail") if isinstance(body.get("detail"), dict) else body
    return str((detail or {}).get("error") or "")


def clear_active_bank_request(token: str) -> dict[str, Any]:
    """Withdraw whatever request is active so the next case starts clean."""
    code, body = http("GET", "/app/bank", token=token)
    sub = ((body or {}).get("submission") or {}) if code == 200 else {}
    rid = sub.get("request_id")
    state = str(body.get("submission_state") or "") if code == 200 else ""
    if not rid or state in {"", "none", "approved", "rejected", "withdrawn"}:
        return {"cleared": False, "state": state}
    wcode, _ = http("POST", f"/app/bank/requests/{rid}/withdraw", token=token)
    return {"cleared": wcode == 200, "state": state, "request_id": rid}


def completion_of(app: Any, key: str) -> dict[str, Any]:
    import onboarding_completion_contract as C

    with app.db_connect() as conn:
        with conn.cursor() as cur:
            snap = C.recompute(cur, employee_key=key, company_code=COMPANY, actor="qual_matrix")
        conn.commit()
    return snap


def cleanup(app: Any, keys: list[str]) -> dict[str, Any]:
    removed: dict[str, int] = {}
    # Blobs first: deleting the DB row would orphan the private evidence file.
    try:
        purge = app.purge_bank_evidence_bytes(company_code=COMPANY, employee_keys=keys)
        removed["evidence_files_unlinked"] = int(purge.get("files_unlinked") or 0) + int(
            purge.get("orphan_files_unlinked") or 0
        )
    except Exception as exc:
        removed["evidence_files_unlinked"] = -1
        RESULTS["errors"].append(f"cleanup evidence blobs: {str(exc)[:160]}")
    tables = [
        ("employee_bank_notifications", "employee_key"),
        ("employee_bank_evidence", "employee_key"),
        ("employee_bank_effective", "employee_key"),
        ("employee_bank_verified", "employee_key"),
        ("employee_ess_bank_profiles", "employee_key"),
        ("employee_ess_request_events", None),
        ("employee_ess_requests", "employee_key"),
        ("employee_onboarding_completion_events", "employee_key"),
        ("employee_onboarding_completion", "employee_key"),
        ("onboarding_items", "employee_key"),
        ("employee_onboarding_assignments", "employee_key"),
        ("employee_sessions", "employee_key"),
        ("employees", "employee_key"),
    ]
    with app.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                DELETE FROM employee_ess_request_events
                WHERE request_id IN (
                  SELECT request_id FROM employee_ess_requests WHERE employee_key = ANY(%s)
                )
                """,
                (keys,),
            )
            removed["employee_ess_request_events"] = cur.rowcount
            for table, col in tables:
                if col is None:
                    continue
                # Savepoint per table: a missing/legacy table must not roll back
                # the deletes that already succeeded.
                cur.execute("SAVEPOINT cleanup_step")
                try:
                    cur.execute(f"DELETE FROM {table} WHERE {col} = ANY(%s)", (keys,))
                    removed[table] = cur.rowcount
                    cur.execute("RELEASE SAVEPOINT cleanup_step")
                except Exception as exc:
                    removed[table] = -1
                    RESULTS["errors"].append(f"cleanup {table}: {str(exc)[:160]}")
                    cur.execute("ROLLBACK TO SAVEPOINT cleanup_step")
        conn.commit()
    return removed


# ---------------------------------------------------------------------------
# Bank ESS matrix
# ---------------------------------------------------------------------------
GOOD_IBAN = "KW81CBKU0000000000001234560101"
GOOD_IBAN_2 = "KW16NBOK0000000000001234560101"
S = "bank_ess"


def run_bank_matrix(app: Any, w5: Any, bank: Any, *, emp: dict, other: dict, token: str,
                    other_token: str, hr_token: str | None, hr_ctx: dict) -> None:
    key = emp["employee_key"]
    other_key = other["employee_key"]

    # --- baseline: no bank yet ---
    code, body = http("GET", "/app/bank", token=token)
    check(S, "employee_view_status_no_bank", code == 200 and body.get("has_verified_bank") is False,
          {"code": code, "state": body.get("submission_state")})
    check(S, "next_step_present_when_empty", bool((body.get("next_step") or {}).get("message")),
          (body.get("next_step") or {}).get("message"))

    # --- draft save ---
    idem_draft = f"qual-draft-{RUN_TAG}-{uuid.uuid4().hex[:8]}"
    code, body = http("POST", "/app/bank/requests", token=token, body={
        "iban": GOOD_IBAN, "bank_name": "NBK", "account_holder": "QUAL CANARY",
        "idempotency_key": idem_draft, "draft": True,
    })
    draft_ok = code == 200 and (body.get("bank") or {}).get("submission_state") == "draft"
    check(S, "draft_save", draft_ok, {"code": code, "state": (body.get("bank") or {}).get("submission_state")})
    draft_id = ((body.get("bank") or {}).get("submission") or {}).get("request_id")

    # --- masked by default in employee response ---
    check(S, "masking_default_employee", not contains_plaintext(body, GOOD_IBAN),
          {"leaked": contains_plaintext(body, GOOD_IBAN)})

    # --- proposal sealed at rest (no plaintext IBAN in DB) ---
    if draft_id:
        with app.db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT proposed_values FROM employee_ess_requests WHERE request_id=%s",
                    (draft_id,),
                )
                row = dict(cur.fetchone() or {})
            conn.commit()
        pv = row.get("proposed_values") or {}
        check(S, "proposal_sealed_at_rest",
              not contains_plaintext(pv, GOOD_IBAN) and bool(pv.get("sealed")),
              {"sealed": bool(pv.get("sealed")), "leaked": contains_plaintext(pv, GOOD_IBAN)})

    # --- retry/idempotency: same idempotency key replays, does not duplicate ---
    code_re, body_re = http("POST", "/app/bank/requests", token=token, body={
        "iban": GOOD_IBAN, "bank_name": "NBK", "account_holder": "QUAL CANARY",
        "idempotency_key": idem_draft, "draft": True,
    })
    check(S, "retry_idempotency_create", code_re == 200 and body_re.get("idempotent") is True,
          {"code": code_re, "idempotent": body_re.get("idempotent")})

    # --- submit draft ---
    if draft_id:
        code, body = http("POST", f"/app/bank/requests/{draft_id}/submit", token=token)
        state = (body.get("bank") or {}).get("submission_state")
        check(S, "submit_draft_for_review", code == 200 and state == "pending_hr",
              {"code": code, "state": state})
        check(S, "change_under_review_flag", bool((body.get("bank") or {}).get("change_under_review")))

    # --- duplicate-submit protection (pending_hr is not replaceable) ---
    code_dup, body_dup = http("POST", "/app/bank/requests", token=token, body={
        "iban": GOOD_IBAN_2, "bank_name": "Gulf Bank",
        "idempotency_key": f"qual-dup-{RUN_TAG}-{uuid.uuid4().hex[:8]}",
    })
    check(S, "duplicate_submit_protection",
          code_dup == 409 and (body_dup.get("detail") or {}).get("error") == "bank_request_already_active",
          {"code": code_dup, "error": (body_dup.get("detail") or {}).get("error")})

    # --- unauthorized employee access: other employee cannot read/act ---
    code_x, body_x = http("GET", "/app/bank", token=other_token)
    other_leak = contains_plaintext(body_x, GOOD_IBAN)
    other_rid = ((body_x.get("submission") or {}) or {}).get("request_id")
    check(S, "unauthorized_employee_isolation",
          code_x in (200, 403) and not other_leak and other_rid is None
          and bool(draft_id) and other_rid != draft_id,
          {"code": code_x, "leaked": other_leak, "other_request_id": other_rid,
           "draft_id_present": bool(draft_id)})
    if draft_id:
        code_w, body_w = http("POST", f"/app/bank/requests/{draft_id}/withdraw", token=other_token)
        check(S, "unauthorized_employee_cannot_withdraw", code_w in (403, 404),
              {"code": code_w, "error": (body_w.get("detail") or {}).get("error")})

    # --- HR review: compare current vs proposed ---
    if hr_token:
        code, body = http("GET", f"/dashboard/posthire/employees/{key}/bank",
                          dashboard_token=hr_token)
        comp = (body or {}).get("comparison") or {}
        check(S, "hr_review_compare_current_vs_proposed",
              code == 200 and comp.get("is_first_submission") is True and bool(comp.get("proposed")),
              {"code": code, "changed_fields": comp.get("changed_fields"),
               "first": comp.get("is_first_submission")})
        check(S, "hr_view_masked_by_default", not contains_plaintext(body, GOOD_IBAN),
              {"leaked": contains_plaintext(body, GOOD_IBAN)})
        check(S, "hr_sees_evidence_list",
              isinstance(((body.get("submission") or {}) or {}).get("evidence"), list))
    else:
        record(S, "hr_review_compare_current_vs_proposed", "skipped", "no dashboard session")

    # --- HR reject requires a reason ---
    if draft_id and hr_token:
        code, body = hr_decide(hr_token, str(draft_id), "reject", comment=None)
        check(S, "hr_reject_requires_reason",
              code == 422 and err_of(body) == "decision_reason_required",
              {"code": code, "error": err_of(body)})

        # --- HR reject with reason ---
        code, body = hr_decide(hr_token, str(draft_id), "reject",
                               comment="QUAL: account holder name does not match your civil ID.")
        if code != 200:
            record(S, "hr_reject_with_reason", "failed", {"code": code, "error": err_of(body)})
        else:
            code, body = http("GET", "/app/bank", token=token)
            sub = body.get("submission") or {}
            check(S, "hr_reject_with_reason",
                  body.get("submission_state") == "rejected" and bool(sub.get("rejection_reason")),
                  {"state": body.get("submission_state"), "reason": sub.get("rejection_reason")})
            check(S, "employee_sees_rejection_next_step",
                  (body.get("next_step") or {}).get("owner") == "employee",
                  body.get("next_step"))
            check(S, "can_resubmit_after_reject", bool(sub.get("can_resubmit")))
    elif draft_id:
        record(S, "hr_reject_with_reason", "skipped", "no dashboard session")

    # --- employee correction + resubmit (new request allowed after reject) ---
    idem_fix = f"qual-fix-{RUN_TAG}-{uuid.uuid4().hex[:8]}"
    code, body = http("POST", "/app/bank/requests", token=token, body={
        "iban": GOOD_IBAN, "bank_name": "NBK", "account_holder": "QUAL CANARY CORRECTED",
        "idempotency_key": idem_fix,
    })
    fixed = (body.get("bank") or {}).get("submission") or {}
    fix_id = fixed.get("request_id")
    check(S, "employee_correction_and_resubmit",
          code == 200 and (body.get("bank") or {}).get("submission_state") == "pending_hr",
          {"code": code, "state": (body.get("bank") or {}).get("submission_state")})

    # --- withdrawal ---
    if fix_id:
        code, body = http("POST", f"/app/bank/requests/{fix_id}/withdraw", token=token)
        check(S, "withdrawal", code == 200
              and (body.get("bank") or {}).get("submission_state") == "withdrawn",
              {"code": code, "state": (body.get("bank") or {}).get("submission_state")})
        with app.db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT status FROM onboarding_items WHERE employee_key=%s AND item_id='bank_details'",
                    (key,),
                )
                bd = dict(cur.fetchone() or {})
            conn.commit()
        if bd:
            check(
                S,
                "withdraw_clears_onboarding_processing",
                str(bd.get("status")) != "processing",
                {"status": bd.get("status")},
            )
        else:
            record(S, "withdraw_clears_onboarding_processing", "skipped", "no bank_details row")

    # --- Kuwait IBAN enforced at submit (cannot survive to HR/Apply) ---
    clear_active_bank_request(token)
    code_bad, body_bad = http("POST", "/app/bank/requests", token=token, body={
        "iban": "KW00INVALID000000000000000000", "bank_name": "NBK",
        "idempotency_key": f"qual-badiban-{RUN_TAG}-{uuid.uuid4().hex[:8]}",
    })
    check(
        S,
        "kw_iban_enforced_at_submit",
        code_bad == 422 and err_of(body_bad) == "bank_account_invalid",
        {"code": code_bad, "error": err_of(body_bad), "detail": body_bad.get("detail")},
    )

    # --- needs_review recovery: employee can replace instead of bank_request_already_active ---
    clear_active_bank_request(token)
    idem_nr = f"qual-needs-review-{RUN_TAG}-{uuid.uuid4().hex[:8]}"
    code, body = http("POST", "/app/bank/requests", token=token, body={
        "iban": GOOD_IBAN, "bank_name": "NBK", "account_holder": "QUAL CANARY",
        "idempotency_key": idem_nr,
    })
    nr_id = ((body.get("bank") or {}).get("submission") or {}).get("request_id")
    if nr_id:
        with app.db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE employee_ess_requests SET state='needs_review', fail_reason='qual_forced' "
                    "WHERE request_id=%s",
                    (nr_id,),
                )
            conn.commit()
        code_nr, body_nr = http("POST", "/app/bank/requests", token=token, body={
            "iban": GOOD_IBAN_2, "bank_name": "Gulf Bank", "account_holder": "QUAL CANARY",
            "idempotency_key": f"qual-needs-review-fix-{RUN_TAG}-{uuid.uuid4().hex[:8]}",
        })
        check(
            S,
            "needs_review_replace_recovery",
            code_nr == 200
            and body_nr.get("replaced") is True
            and (body_nr.get("bank") or {}).get("submission_state") == "pending_hr",
            {
                "code": code_nr,
                "replaced": body_nr.get("replaced"),
                "state": (body_nr.get("bank") or {}).get("submission_state"),
                "error": err_of(body_nr),
            },
        )
        clear_active_bank_request(token)
    else:
        record(S, "needs_review_replace_recovery", "skipped", "could not seed needs_review request")

    # --- fresh request → approve path → payroll effective ---
    # Independent case: don't let an earlier failure's leftover active request
    # turn this into a cascade of 409s.
    clear_active_bank_request(token)
    idem_final = f"qual-final-{RUN_TAG}-{uuid.uuid4().hex[:8]}"
    code, body = http("POST", "/app/bank/requests", token=token, body={
        "iban": GOOD_IBAN, "bank_name": "NBK", "account_holder": "QUAL CANARY",
        "idempotency_key": idem_final,
    })
    final_id = ((body.get("bank") or {}).get("submission") or {}).get("request_id")
    check(S, "first_submission_live", code == 200 and bool(final_id), {"code": code})

    if final_id and hr_token:
        # Concurrent HR review: stale concurrency version must lose.
        with app.db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT concurrency_version FROM employee_ess_requests WHERE request_id=%s",
                            (final_id,))
                ver = int(dict(cur.fetchone() or {}).get("concurrency_version") or 0)
            conn.commit()
        code, body = hr_decide(hr_token, str(final_id), "approve",
                               comment="QUAL hr approve", expected_concurrency_version=ver)
        check(S, "hr_approve_stage_1", code == 200, {"code": code, "error": err_of(body)})
        # P0: HR approval stamps verified; effective must not move yet.
        with app.db_connect() as conn:
            with conn.cursor() as cur:
                bank.ensure_bank_ess_schema(cur)
                cur.execute(
                    """
                    SELECT verified_by_stage, revoked_at IS NULL AS current
                    FROM employee_bank_verified
                    WHERE employee_key=%s AND request_id=%s
                    ORDER BY verified_at DESC LIMIT 1
                    """,
                    (key, final_id),
                )
                vrow = dict(cur.fetchone() or {})
                eff_before_apply = bank.current_effective(cur, company_code=COMPANY, employee_key=key)
            conn.commit()
        code_emp, body_emp = http("GET", "/app/bank", token=token)
        check(
            S,
            "hr_approve_stamps_verified_not_effective",
            code == 200
            and str(vrow.get("verified_by_stage") or "") == "hr"
            and bool(vrow.get("current"))
            and code_emp == 200
            and body_emp.get("submission_state") == "pending_payroll"
            and body_emp.get("has_verified_bank") is True
            and "Apply" not in str((body_emp.get("next_step") or {}).get("message_en") or "")
            and "Apply" not in str((body_emp.get("next_step") or {}).get("message") or ""),
            {
                "verified_by_stage": vrow.get("verified_by_stage"),
                "submission_state": body_emp.get("submission_state"),
                "next_step": body_emp.get("next_step"),
                "effective_fp": (eff_before_apply or {}).get("fingerprint"),
            },
        )
        code_s, body_s = hr_decide(hr_token, str(final_id), "approve",
                                   comment="QUAL stale", expected_concurrency_version=ver)
        check(S, "concurrent_hr_review_guard",
              code_s == 409 and err_of(body_s) == "stale_concurrency_version",
              {"code": code_s, "error": err_of(body_s)})

        # Payroll stage approve then apply.
        applied = None
        with app.db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT state FROM employee_ess_requests WHERE request_id=%s", (final_id,))
                cur_row = dict(cur.fetchone() or {})
            conn.commit()
        if str(cur_row.get("state")) == "pending_payroll":
            code_p, body_p = hr_decide(hr_token, str(final_id), "approve",
                                       comment="QUAL payroll approve")
            if code_p != 200:
                record(S, "payroll_stage_approve", "failed",
                       {"code": code_p, "error": err_of(body_p)})
        code_a, applied = hr_apply(hr_token, str(final_id),
                                   idempotency_key=f"qual-apply-{final_id}")
        applied = applied if isinstance(applied, dict) else {}
        ref = applied.get("authority_ref") if isinstance(applied.get("authority_ref"), dict) else {}
        eff_ref = ref.get("payroll_effective") if isinstance(ref.get("payroll_effective"), dict) else {}
        req_state = str(((applied.get("request") or {}) or {}).get("state") or "")
        check(S, "payroll_effective_transition",
              code_a == 200 and req_state == "applied" and bool(eff_ref.get("effective_from")),
              {"code": code_a, "request_state": req_state,
               "effective_from": eff_ref.get("effective_from"),
               "bank_profile_version": ref.get("bank_profile_version")})

        # Apply is idempotent: same key replays without a second effective row.
        code_r, again = hr_apply(hr_token, str(final_id),
                                 idempotency_key=f"qual-apply-{final_id}")
        with app.db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT count(*) c FROM employee_bank_effective "
                    "WHERE employee_key=%s AND superseded_at IS NULL",
                    (key,),
                )
                eff_rows = int(dict(cur.fetchone() or {}).get("c") or 0)
            conn.commit()
        check(S, "retry_idempotency_apply", code_r == 200 and eff_rows <= 1,
              {"code": code_r, "current_effective_rows": eff_rows})

        # Three-layer authority present and separated.
        with app.db_connect() as conn:
            with conn.cursor() as cur:
                bank.ensure_bank_ess_schema(cur)
                cur.execute("SELECT count(*) c FROM employee_bank_verified WHERE employee_key=%s", (key,))
                n_verified = int(dict(cur.fetchone() or {}).get("c") or 0)
                cur.execute(
                    "SELECT count(*) c FROM employee_bank_effective WHERE employee_key=%s AND superseded_at IS NULL",
                    (key,),
                )
                n_effective = int(dict(cur.fetchone() or {}).get("c") or 0)
                eff = bank.current_effective(cur, company_code=COMPANY, employee_key=key)
            conn.commit()
        check(S, "authority_layers_separated",
              n_verified >= 1 and n_effective == 1,
              {"verified_rows": n_verified, "current_effective_rows": n_effective})
        check(S, "payroll_effective_never_plaintext", not contains_plaintext(eff, GOOD_IBAN),
              {"leaked": contains_plaintext(eff, GOOD_IBAN)})

        # Notification dedup.
        with app.db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT dedup_key, count(*) c FROM employee_bank_notifications WHERE employee_key=%s GROUP BY dedup_key",
                    (key,),
                )
                notif = [dict(r) for r in (cur.fetchall() or [])]
            conn.commit()
        dupes = [n for n in notif if int(n.get("c") or 0) > 1]
        check(S, "notification_deduplication", not dupes, {"groups": len(notif), "dupes": dupes})

        # Audit history: events exist and name the actors.
        with app.db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT e.action, e.from_state, e.to_state, e.actor_user_id, e.actor_employee_key
                    FROM employee_ess_request_events e
                    JOIN employee_ess_requests r ON r.request_id=e.request_id
                    WHERE r.employee_key=%s ORDER BY e.created_at
                    """,
                    (key,),
                )
                events = [dict(r) for r in (cur.fetchall() or [])]
            conn.commit()
        actions = {str(e.get("action")) for e in events}
        check(S, "audit_history",
              len(events) >= 4 and any(a.startswith("decide_") for a in actions),
              {"event_count": len(events), "actions": sorted(actions)[:10]})

        # Onboarding bank item closed by apply.
        with app.db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT status FROM onboarding_items WHERE employee_key=%s AND item_id='bank_details'",
                    (key,),
                )
                bd = dict(cur.fetchone() or {})
            conn.commit()
        if bd:
            check(S, "onboarding_bank_item_synced_on_apply",
                  str(bd.get("status")) == "accepted", {"status": bd.get("status")})
        else:
            record(S, "onboarding_bank_item_synced_on_apply", "skipped", "no bank_details row on canary")

    # --- existing-bank change (second change after a verified value exists) ---
    idem_change = f"qual-change-{RUN_TAG}-{uuid.uuid4().hex[:8]}"
    code, body = http("POST", "/app/bank/requests", token=token, body={
        "iban": GOOD_IBAN_2, "bank_name": "Gulf Bank", "account_holder": "QUAL CANARY",
        "idempotency_key": idem_change,
    })
    bank_view = body.get("bank") or {}
    check(S, "existing_bank_change",
          code == 200 and bool(bank_view.get("has_verified_bank"))
          and bank_view.get("submission_state") == "pending_hr",
          {"code": code, "has_verified": bank_view.get("has_verified_bank"),
           "state": bank_view.get("submission_state")})
    check(S, "verified_separate_from_submitted",
          bool(bank_view.get("verified")) and bool(bank_view.get("submission")),
          {"verified_present": bool(bank_view.get("verified")),
           "submitted_present": bool(bank_view.get("submission"))})
    change_id = ((bank_view.get("submission")) or {}).get("request_id")

    # --- unreviewed input must not become payroll truth ---
    with app.db_connect() as conn:
        with conn.cursor() as cur:
            eff2 = bank.current_effective(cur, company_code=COMPANY, employee_key=key)
        conn.commit()
    still_old = (eff2 or {}).get("fingerprint") == bank.fingerprint(GOOD_IBAN)
    check(S, "unreviewed_input_not_payroll_truth", still_old,
          {"effective_fingerprint_matches_previous": still_old})

    # --- evidence upload + authorized access only ---
    # Capture verified/effective counts before OCR so we can prove OCR never
    # elevates authority layers.
    with app.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT count(*) c FROM employee_bank_verified WHERE employee_key=%s AND revoked_at IS NULL",
                (key,),
            )
            v_before = int(dict(cur.fetchone() or {}).get("c") or 0)
            cur.execute(
                "SELECT count(*) c FROM employee_bank_effective WHERE employee_key=%s",
                (key,),
            )
            e_before = int(dict(cur.fetchone() or {}).get("c") or 0)
        conn.commit()

    ev_body = upload_evidence(token, change_id, return_body=True) or {}
    ev_id = str(ev_body.get("evidence_id") or "") or None
    check(S, "evidence_upload", bool(ev_id), {"evidence_id": ev_id})
    extraction = ev_body.get("extraction") if isinstance(ev_body.get("extraction"), dict) else {}
    check(
        S,
        "p1_evidence_extraction_non_authoritative",
        bool(ev_id)
        and extraction.get("authoritative") is False
        and isinstance(ev_body.get("proposed_fields"), dict)
        and "needs_manual_fallback" in ev_body,
        {
            "status": extraction.get("status"),
            "authoritative": extraction.get("authoritative"),
            "needs_manual_fallback": ev_body.get("needs_manual_fallback"),
            "proposed_keys": sorted((ev_body.get("proposed_fields") or {}).keys()),
        },
    )
    with app.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT count(*) c FROM employee_bank_verified WHERE employee_key=%s AND revoked_at IS NULL",
                (key,),
            )
            v_after = int(dict(cur.fetchone() or {}).get("c") or 0)
            cur.execute(
                "SELECT count(*) c FROM employee_bank_effective WHERE employee_key=%s",
                (key,),
            )
            e_after = int(dict(cur.fetchone() or {}).get("c") or 0)
            if ev_id:
                cur.execute(
                    """
                    SELECT extraction_status, extraction_confidence, extraction_json
                    FROM employee_bank_evidence
                    WHERE evidence_id=%s AND employee_key=%s
                    """,
                    (ev_id, key),
                )
                erow = dict(cur.fetchone() or {})
            else:
                erow = {}
        conn.commit()
    check(
        S,
        "p1_ocr_never_writes_verified_or_effective",
        v_after == v_before and e_after == e_before,
        {"verified_before": v_before, "verified_after": v_after, "effective_before": e_before, "effective_after": e_after},
    )
    check(
        S,
        "p1_evidence_extraction_persisted",
        bool(ev_id) and (erow.get("extraction_status") is not None or erow.get("extraction_json")),
        {
            "extraction_status": erow.get("extraction_status"),
            "has_json": bool(erow.get("extraction_json")),
        },
    )
    if ev_id:
        code_own, _ = http("GET", f"/app/bank/evidence/{ev_id}", token=token)
        check(S, "evidence_access_own", code_own == 200, {"code": code_own})
        code_other, _ = http("GET", f"/app/bank/evidence/{ev_id}", token=other_token)
        check(S, "evidence_access_denied_other_employee", code_other in (403, 404),
              {"code": code_other})
        if hr_token:
            code_hr, _ = http("GET",
                              f"/dashboard/posthire/employees/{key}/bank/evidence/{ev_id}",
                              dashboard_token=hr_token)
            check(S, "evidence_access_hr_authorized", code_hr == 200, {"code": code_hr})
            code_hrb, body_hrb = http(
                "GET",
                f"/dashboard/posthire/employees/{key}/bank",
                dashboard_token=hr_token,
            )
            ev_rows = (((body_hrb.get("submission") or {}) or {}).get("evidence") or [])
            matched = next((r for r in ev_rows if str(r.get("evidence_id")) == str(ev_id)), None)
            check(
                S,
                "p1_hr_sees_extraction_summary",
                code_hrb == 200
                and isinstance(matched, dict)
                and isinstance(matched.get("extraction"), dict)
                and matched["extraction"].get("authoritative") is False,
                {
                    "code": code_hrb,
                    "matched": bool(matched),
                    "status": (matched or {}).get("extraction_status")
                    or ((matched or {}).get("extraction") or {}).get("status"),
                },
            )

    # --- unauthorized HR access (no dashboard credential) ---
    code_nohr, body_nohr = http("GET", f"/dashboard/posthire/employees/{key}/bank")
    check(S, "unauthorized_hr_access_denied", code_nohr in (401, 403),
          {"code": code_nohr, "error": (body_nohr.get("detail") or {}).get("error")})

    # --- cross-tenant isolation ---
    if hr_token:
        code_ct, body_ct = http("GET",
                                f"/dashboard/posthire/employees/{other_key}-NOPE/bank",
                                dashboard_token=hr_token)
        check(S, "cross_tenant_isolation_unknown_key", code_ct == 404,
              {"code": code_ct})
    with app.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT count(*) c FROM employee_bank_effective
                WHERE employee_key=%s AND company_code <> %s
                """,
                (key, COMPANY),
            )
            leak = int(dict(cur.fetchone() or {}).get("c") or 0)
        conn.commit()
    check(S, "cross_tenant_isolation_storage", leak == 0, {"rows_outside_tenant": leak})

    # --- Arabic ---
    code_ar, body_ar = http("GET", "/app/bank?locale=ar", token=token)
    msg_ar = (body_ar.get("next_step") or {}).get("message") or ""
    check(S, "arabic_next_step", code_ar == 200 and bool(msg_ar)
          and any("\u0600" <= ch <= "\u06ff" for ch in msg_ar), {"message": msg_ar[:80]})

    # --- masking + permitted reveal ---
    if hr_token:
        code_m, body_m = http("GET", f"/dashboard/posthire/employees/{key}/bank",
                              dashboard_token=hr_token)
        masking = (body_m or {}).get("masking") or {}
        check(S, "masking_and_permitted_reveal_contract",
              masking.get("masked_by_default") is True
              and masking.get("reveal_is_audited") is True
              and not contains_plaintext(body_m, GOOD_IBAN_2),
              {"masking": masking, "leaked": contains_plaintext(body_m, GOOD_IBAN_2)})

    # --- payroll lock behaviour is defined ---
    with app.db_connect() as conn:
        with conn.cursor() as cur:
            lock = bank.payroll_lock_state(cur, company_code=COMPANY)
        conn.commit()
    check(S, "payroll_lock_state_defined", isinstance(lock, dict) and "locked" in lock, lock)


def upload_evidence(
    token: str,
    request_id: str | None,
    *,
    return_body: bool = False,
    filename: str = "qual-iban-letter.pdf",
    content_type: str = "application/pdf",
    payload: bytes | None = None,
) -> str | dict[str, Any] | None:
    """Multipart upload of synthetic bank evidence (PDF or image)."""
    boundary = "----qualbank" + uuid.uuid4().hex
    pdf = payload or (
        b"%PDF-1.4\n1 0 obj<</Type/Catalog>>endobj\ntrailer<</Root 1 0 R>>\n%%EOF\n"
    )
    parts: list[bytes] = []
    if request_id:
        parts += [
            f"--{boundary}\r\n".encode(),
            b'Content-Disposition: form-data; name="request_id"\r\n\r\n',
            str(request_id).encode() + b"\r\n",
        ]
    parts += [
        f"--{boundary}\r\n".encode(),
        f'Content-Disposition: form-data; name="file"; filename="{filename}"\r\n'.encode(),
        f"Content-Type: {content_type}\r\n\r\n".encode(),
        pdf,
        b"\r\n",
        f"--{boundary}--\r\n".encode(),
    ]
    data = b"".join(parts)
    req = urllib.request.Request(
        f"{BASE_URL}/app/bank/evidence",
        data=data,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": f"multipart/form-data; boundary={boundary}",
            "Accept": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT_S) as resp:
            body = json.loads(resp.read().decode("utf-8", "replace"))
            if return_body:
                return body if isinstance(body, dict) else {"raw": body}
            return str(body.get("evidence_id") or "") or None
    except Exception as exc:
        RESULTS["errors"].append(f"evidence upload: {type(exc).__name__} {str(exc)[:200]}")
        return None


# ---------------------------------------------------------------------------
# Onboarding completion matrix
# ---------------------------------------------------------------------------
O = "onboarding_completion"


def run_onboarding_matrix(app: Any, *, emp: dict, token: str, hr_token: str | None) -> None:
    import onboarding_completion_contract as C

    key = emp["employee_key"]

    # new employee, no progress
    snap = completion_of(app, key)
    check(O, "new_employee_no_progress", snap["state"] == C.STATE_NOT_STARTED, snap["state"])

    # partial progress + waiting on employee
    set_item(app, key, "qual_doc_a", "processing")
    snap = completion_of(app, key)
    check(O, "partial_progress", snap["satisfied_count"] == 0 and snap["open_count"] == 3,
          {"satisfied": snap["satisfied_count"], "open": snap["open_count"]})
    check(O, "waiting_on_employee", snap["state"] == C.STATE_WAITING_ON_EMPLOYEE, snap["state"])

    # waiting on HR: all employee items submitted, HR task waived out
    set_item(app, key, "qual_doc_b", "processing")
    set_item(app, key, "qual_hr_task", "submitted")
    snap = completion_of(app, key)
    check(O, "waiting_on_hr", snap["state"] == C.STATE_WAITING_ON_HR, snap["state"])

    # rejected item flips ownership back to the employee
    set_item(app, key, "qual_doc_a", "replacement_required")
    snap = completion_of(app, key)
    check(O, "rejected_item", snap["state"] == C.STATE_WAITING_ON_EMPLOYEE
          and "qual_doc_a" in snap["waiting_on_employee_items"], snap["state"])

    # corrected item
    set_item(app, key, "qual_doc_a", "accepted")
    snap = completion_of(app, key)
    check(O, "corrected_item", "qual_doc_a" in snap["satisfied_items"], snap["satisfied_items"])

    # waived item
    set_item(app, key, "qual_hr_task", "waived", required=False)
    snap = completion_of(app, key)
    check(O, "waived_item", "qual_hr_task" not in snap["waiting_on_hr_items"],
          {"waiting_hr": snap["waiting_on_hr_items"]})

    # not-applicable item
    set_item(app, key, "qual_doc_b", "pending", meta={"not_applicable": True})
    snap = completion_of(app, key)
    check(O, "not_applicable_item", snap["state"] == C.STATE_COMPLETED, snap["state"])

    # completion
    check(O, "completion", snap["is_complete"] is True, snap["state"])
    with app.db_connect() as conn:
        with conn.cursor() as cur:
            row = C.load_completion_row(cur, company_code=COMPANY, employee_key=key)
        conn.commit()
    check(O, "completion_evidence_recorded",
          bool((row or {}).get("first_completed_at"))
          and len((row or {}).get("completion_evidence") or []) >= 1,
          {"first_completed_at": str((row or {}).get("first_completed_at")),
           "evidence": len((row or {}).get("completion_evidence") or [])})

    # legacy columns mirrored (cross-surface consistency at the DB level)
    with app.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT onboarding_status, documents_pending, documents_complete FROM employees WHERE employee_key=%s",
                (key,),
            )
            legacy = dict(cur.fetchone() or {})
        conn.commit()
    pending_col = legacy.get("documents_pending")
    check(O, "legacy_columns_mirrored",
          str(legacy.get("onboarding_status")) == "completed"
          and pending_col is not None and int(pending_col) == 0,
          legacy)

    # requirement added after completion → reopened
    seed_canary_items(app, key, [
        {"item_id": "qual_new_policy", "required": True, "owner": "employee", "status": "pending"}
    ])
    snap = completion_of(app, key)
    check(O, "requirement_added_after_completion", snap["state"] == C.STATE_REOPENED, snap["state"])
    check(O, "reopened_onboarding", snap["is_complete"] is False, snap["state"])

    # historical evidence survives a requirement change
    with app.db_connect() as conn:
        with conn.cursor() as cur:
            row2 = C.load_completion_row(cur, company_code=COMPANY, employee_key=key)
        conn.commit()
    check(O, "historical_evidence_preserved",
          len((row2 or {}).get("completion_evidence") or []) >= 1
          and bool((row2 or {}).get("first_completed_at")),
          {"evidence": len((row2 or {}).get("completion_evidence") or [])})

    # requirement removed after progress → back to completed
    with app.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM onboarding_items WHERE employee_key=%s AND item_id='qual_new_policy'",
                        (key,))
        conn.commit()
    snap = completion_of(app, key)
    check(O, "requirement_removed_after_progress", snap["state"] == C.STATE_COMPLETED, snap["state"])

    # blocked by dependency
    seed_canary_items(app, key, [
        {"item_id": "qual_dep_parent", "required": True, "owner": "employee", "status": "pending"},
        {"item_id": "qual_dep_child", "required": True, "owner": "employee", "status": "pending",
         "depends_on": ["qual_dep_parent"]},
    ])
    set_item(app, key, "qual_dep_parent", "processing")
    snap = completion_of(app, key)
    check(O, "blocked_dependency_detected", "qual_dep_child" in snap["blocked_items"],
          {"blocked": snap["blocked_items"]})

    # dependency satisfied by `accepted` (the historical bug)
    set_item(app, key, "qual_dep_parent", "accepted")
    snap = completion_of(app, key)
    check(O, "accepted_satisfies_dependency", "qual_dep_child" not in snap["blocked_items"],
          {"blocked": snap["blocked_items"]})

    # employee transfer: requirements change with role/location
    seed_canary_items(app, key, [
        {"item_id": "qual_transfer_req", "required": True, "owner": "hr", "status": "pending"}
    ])
    snap = completion_of(app, key)
    check(O, "employee_transfer_new_requirement",
          snap["state"] in {C.STATE_REOPENED, C.STATE_WAITING_ON_HR, C.STATE_WAITING_ON_EMPLOYEE},
          snap["state"])

    # legacy employee: `received` must not read as verified
    with app.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE onboarding_items SET status='received' WHERE employee_key=%s AND item_id='qual_dep_child'",
                (key,),
            )
        conn.commit()
    snap = completion_of(app, key)
    check(O, "legacy_received_not_verified",
          "qual_dep_child" in snap["waiting_on_hr_items"],
          {"waiting_hr": snap["waiting_on_hr_items"]})

    # Legacy migration: an employee who completed onboarding before the contract
    # existed has no snapshot. The backfill must stamp history so a later
    # requirement change reads as `reopened` rather than a fresh `waiting_on_*`.
    legacy = create_canary(app, suffix=LEGACY_SUFFIX, seed_items=False)
    lkey = legacy["employee_key"]
    seed_canary_items(app, lkey, [
        {"item_id": "qual_legacy_doc", "required": True, "owner": "employee", "status": "accepted"}
    ])
    with app.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE employees SET onboarding_status='completed' WHERE employee_key=%s", (lkey,)
            )
            cur.execute("DELETE FROM employee_onboarding_completion WHERE employee_key=%s", (lkey,))
            cur.execute(
                "DELETE FROM employee_onboarding_completion_events WHERE employee_key=%s", (lkey,)
            )
            pre = C.previously_completed_flag(cur, company_code=COMPANY, employee_key=lkey)
            stamped = C.seed_legacy_completion_history(
                cur, company_code=COMPANY, employee_key=lkey,
                completed_at=datetime(2025, 1, 15, tzinfo=timezone.utc),
                source="legacy_onboarding_status",
            )
            # Second call must be a no-op: the historical stamp is immutable.
            restamped = C.seed_legacy_completion_history(
                cur, company_code=COMPANY, employee_key=lkey,
                completed_at=datetime(2026, 6, 1, tzinfo=timezone.utc),
                source="legacy_onboarding_status",
            )
            row_l = C.load_completion_row(cur, company_code=COMPANY, employee_key=lkey)
        conn.commit()
    check(O, "legacy_backfill_stamps_history",
          pre is False and stamped is True
          and str((row_l or {}).get("first_completed_at") or "").startswith("2025-01-15"),
          {"pre": pre, "stamped": stamped,
           "first_completed_at": str((row_l or {}).get("first_completed_at"))})
    check(O, "legacy_backfill_idempotent",
          restamped is False
          and str((row_l or {}).get("first_completed_at") or "").startswith("2025-01-15"),
          {"restamped": restamped,
           "first_completed_at": str((row_l or {}).get("first_completed_at"))})

    lsnap = completion_of(app, lkey)
    check(O, "legacy_employee_recompute_completed", lsnap["state"] == C.STATE_COMPLETED, lsnap["state"])
    seed_canary_items(app, lkey, [
        {"item_id": "qual_legacy_new_req", "required": True, "owner": "employee", "status": "pending"}
    ])
    lsnap = completion_of(app, lkey)
    check(O, "legacy_employee_reopens_not_restarts",
          lsnap["state"] == C.STATE_REOPENED, lsnap["state"])

    # cross-surface consistency: employee app, HR endpoint and contract agree
    code_app, body_app = http("GET", "/app/onboarding", token=token)
    app_state = ((body_app or {}).get("completion") or {}).get("state") or (
        ((body_app or {}).get("onboarding") or {}).get("completion") or {}
    ).get("state")
    hr_state = None
    if hr_token:
        code_hr, body_hr = http("GET",
                                f"/dashboard/posthire/employees/{key}/onboarding-completion",
                                dashboard_token=hr_token)
        hr_state = (body_hr or {}).get("state")
    hr_web_state = None
    if hr_token:
        code_hw, body_hw = http("GET", f"/dashboard/posthire/onboarding/{key}",
                                dashboard_token=hr_token)
        hr_web_state = ((body_hw or {}).get("completion") or {}).get("state")
    contract_state = completion_of(app, key)["state"]
    surfaces = {
        "employee_app": app_state,
        "hr_completion_endpoint": hr_state,
        "hr_onboarding_web": hr_web_state,
        "contract": contract_state,
    }
    # Every surface must answer, and all answers must be the same. A missing
    # value is a failure: a silent null is how surfaces drift apart.
    check(O, "cross_surface_status_consistency",
          all(bool(v) for v in surfaces.values()) and len(set(surfaces.values())) == 1,
          surfaces)

    # reminders: dedup + covers correction states
    import onboarding_completion_contract as C2

    set_item(app, key, "qual_dep_child", "replacement_required")
    snap = completion_of(app, key)
    r1 = C2.reminder_targets(snap)
    r2 = C2.reminder_targets(completion_of(app, key))
    check(O, "reminder_covers_correction_state",
          r1["party"] == "employee" and "qual_dep_child" in (r1["items"] or []), r1)
    check(O, "reminder_deduplication", r1["dedup_key"] == r2["dedup_key"] and bool(r1["dedup_key"]),
          {"key": r1["dedup_key"]})

    # retry/idempotency: recompute is stable and does not inflate history
    with app.db_connect() as conn:
        with conn.cursor() as cur:
            before = len(C.completion_history(cur, employee_key=key, company_code=COMPANY))
        conn.commit()
    s1 = completion_of(app, key)
    s2 = completion_of(app, key)
    with app.db_connect() as conn:
        with conn.cursor() as cur:
            after = len(C.completion_history(cur, employee_key=key, company_code=COMPANY))
        conn.commit()
    check(O, "retry_idempotency_recompute",
          s1["state"] == s2["state"] and after == before,
          {"state": s1["state"], "history_before": before, "history_after": after})

    # permissions
    code_np, body_np = http("GET", f"/dashboard/posthire/employees/{key}/onboarding-completion")
    check(O, "permissions_unauthenticated_denied", code_np in (401, 403), {"code": code_np})

    # tenant isolation
    if hr_token:
        code_ti, _ = http("GET",
                          "/dashboard/posthire/employees/NOTMYTENANT-999/onboarding-completion",
                          dashboard_token=hr_token)
        check(O, "tenant_isolation", code_ti == 404, {"code": code_ti})

    # arabic
    snap = completion_of(app, key)
    na = C.next_action(snap, locale="ar")
    check(O, "arabic_next_action",
          bool(na["message"]) and any("\u0600" <= ch <= "\u06ff" for ch in na["message"]),
          na["message"][:80])

    # mobile contract shape
    check(O, "mobile_projection_contract",
          code_app == 200 and isinstance(body_app, dict)
          and (body_app.get("lifecycle_version") in {"2a", "legacy"} or "items" in body_app),
          {"code": code_app, "lifecycle_version": body_app.get("lifecycle_version")})


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    import app
    import employee_bank_ess as bank
    import employee_selfservice_wave5 as w5

    log(f"qualification run {RUN_TAG} base={BASE_URL}")

    # Clean slate: a previous aborted run must not seed state into this one.
    pre = cleanup(app, CANARY_KEYS)
    if any(int(v or 0) > 0 for v in pre.values()):
        log(f"pre-run cleanup removed leftovers: "
            f"{ {k: v for k, v in pre.items() if int(v or 0) > 0} }")
    RESULTS["pre_run_cleanup"] = pre

    emp = create_canary(app, suffix="7001")
    # Bank canary carries a real bank_details checklist row so the
    # bank-approval → onboarding-item sync is proven, not skipped.
    seed_canary_items(app, emp["employee_key"], [{
        "item_id": "bank_details", "required": True, "owner": "employee",
        "status": "pending", "authority": "ess",
        "item_type": "bank", "collection_mode": "ess_encrypted",
    }])
    other = create_canary(app, suffix="7002", seed_items=False)
    onb = create_canary(app, suffix="7003")
    log(f"canaries: {emp['employee_key']} {other['employee_key']} {onb['employee_key']}")

    sess = app.create_employee_session(COMPANY, emp["employee_key"], emp["phone"])
    other_sess = app.create_employee_session(COMPANY, other["employee_key"], other["phone"])
    onb_sess = app.create_employee_session(COMPANY, onb["employee_key"], onb["phone"])
    token = str(sess["token"])
    other_token = str(other_sess["token"])
    onb_token = str(onb_sess["token"])

    hr_token = None
    hr_ctx: dict[str, Any] = {}
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
            log(f"minted dashboard session for {hr_user.get('email')} role={hr_user.get('role')}")
        # Built exactly like the HTTP dashboard handlers do, so the permission
        # checks under test are the real ones rather than a hand-made bypass.
        access = app.dashboard_access_payload_for_user(hr_user)
        hr_ctx = {
            "company_code": COMPANY,
            "hr_user": access.get("user"),
            "actor_user_id": str(access["permission_subject_user_id"]),
            "actor_role": access.get("role"),
            "access": access,
            "permissions": access["permissions"],
            "permission_authority": access["permission_authority"],
            "permission_subject_user_id": access["permission_subject_user_id"],
            "permission_subject_company": access["permission_subject_company"],
        }
        resolved = sorted(app.context_permissions(hr_ctx))
        log(f"hr permissions resolved: {len(resolved)} "
            f"ess_hr={'employees.ess.approve.hr' in resolved} "
            f"manage={'employees.manage' in resolved} "
            f"unmask={'employees.ess.unmask' in resolved}")
        RESULTS["hr_permission_probe"] = {
            "count": len(resolved),
            "ess_approve_hr": "employees.ess.approve.hr" in resolved,
            "employees_manage": "employees.manage" in resolved,
            "ess_unmask": "employees.ess.unmask" in resolved,
        }
    except Exception as exc:
        RESULTS["errors"].append(f"dashboard session: {type(exc).__name__} {str(exc)[:200]}")

    try:
        log("=== Bank ESS matrix ===")
        run_bank_matrix(app, w5, bank, emp=emp, other=other, token=token,
                        other_token=other_token, hr_token=hr_token, hr_ctx=hr_ctx)
    except Exception:
        RESULTS["errors"].append("bank matrix: " + traceback.format_exc()[-1500:])
        log("bank matrix crashed; partial results preserved")

    try:
        log("=== Onboarding completion matrix ===")
        run_onboarding_matrix(app, emp=onb, token=onb_token, hr_token=hr_token)
    except Exception:
        RESULTS["errors"].append("onboarding matrix: " + traceback.format_exc()[-1500:])
        log("onboarding matrix crashed; partial results preserved")

    # Static list, not the created ones: a mid-matrix crash must not leave a
    # canary behind just because its dict never made it back here.
    keys = CANARY_KEYS
    RESULTS["cleanup"] = cleanup(app, keys)
    log(f"cleanup: {json.dumps(RESULTS['cleanup'])}")

    for section in ("bank_ess", "onboarding_completion"):
        rows = RESULTS[section]
        RESULTS[f"{section}_summary"] = {
            "total": len(rows),
            "proven": sum(1 for r in rows if r["verdict"] == "proven"),
            "failed": sum(1 for r in rows if r["verdict"] == "failed"),
            "partial": sum(1 for r in rows if r["verdict"] == "partial"),
            "skipped": sum(1 for r in rows if r["verdict"] == "skipped"),
        }

    out = OUT_DIR / f"qual-{RUN_TAG}.json"
    out.write_text(json.dumps(RESULTS, indent=2, default=str))
    log(f"results: {out}")
    for section in ("bank_ess", "onboarding_completion"):
        log(f"{section}: {json.dumps(RESULTS[f'{section}_summary'])}")
    if RESULTS["errors"]:
        log(f"errors: {len(RESULTS['errors'])}")
        for e in RESULTS["errors"]:
            log(f"  ! {e[:400]}")

    failed = sum(RESULTS[f"{s}_summary"]["failed"] for s in ("bank_ess", "onboarding_completion"))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
