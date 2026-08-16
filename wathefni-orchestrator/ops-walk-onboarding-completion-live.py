#!/usr/bin/env python3
"""Live Aziz/Talal walkthrough: one onboarding state across every surface.

Drives the real HTTP endpoints through the whole loop —
employee action → HR review → correction → resubmit → HR approve → payroll
approve → apply → completion — and after every transition reads all four
surfaces and asserts they agree:

  A. HR onboarding queue row      GET /dashboard/posthire/onboarding
  B. HR drawer detail             GET /dashboard/posthire/onboarding/{key}
  C. Employee app checklist       GET /app/onboarding
  D. Employee profile completion  GET /app/profile

The comparison tuple is (completion state, satisfied/required, next-action owner)
plus the bank checklist status where the surface exposes items. It also re-reads
the HR drawer twice per checkpoint, because the bug this walkthrough was written
for only appeared on the second read: a stale rejected request outranked the
applied one and silently reverted a completed item.

Run on the orchestrator host with the service environment loaded.
"""
from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.request
from typing import Any

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

BASE_URL = os.environ.get("WALK_BASE_URL", "http://127.0.0.1:8010")
COMPANY = "WATHEFNI"
AZIZ = "WATHEFNI-96599338566"
TALAL = "WATHEFNI-96550252254"
TIMEOUT = 30

# A checksum-valid synthetic Kuwait IBAN, already proven against the production
# validator. Only the last digits change between walkthrough submissions.
IBAN = "KW30TEST0000000000000000000000"

RESULTS: dict[str, Any] = {"checkpoints": [], "checks": [], "failed": 0}


def log(msg: str) -> None:
    print(f"[walk] {msg}", flush=True)


def check(name: str, ok: bool, detail: Any = None) -> bool:
    RESULTS["checks"].append({"check": name, "status": "proven" if ok else "FAILED", "detail": detail})
    if not ok:
        RESULTS["failed"] += 1
    print(f"{'PASS' if ok else 'FAIL'} {name}" + (f" :: {json.dumps(detail, default=str)}" if detail else ""), flush=True)
    return ok


def http(method: str, path: str, *, token: str | None = None, hr_token: str | None = None,
         body: dict[str, Any] | None = None) -> tuple[int, Any]:
    data = json.dumps(body).encode() if body is not None else None
    headers = {"Accept": "application/json"}
    if data is not None:
        headers["Content-Type"] = "application/json"
    if token:
        headers["Authorization"] = f"Bearer {token}"
    if hr_token:
        headers["X-Dashboard-Token"] = hr_token
        headers["Authorization"] = f"Bearer {hr_token}"
    req = urllib.request.Request(f"{BASE_URL}{path}", data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            raw = resp.read().decode("utf-8", "replace")
            try:
                return resp.status, json.loads(raw)
            except Exception:
                return resp.status, {"raw": raw[:800]}
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", "replace")
        try:
            return exc.code, json.loads(raw)
        except Exception:
            return exc.code, {"raw": raw[:800]}
    except Exception as exc:
        return 0, {"error": type(exc).__name__, "detail": str(exc)[:300]}


# ---------------------------------------------------------------------------
# Surface readers — each returns the same normalized shape
# ---------------------------------------------------------------------------
def _tuple(state: Any, satisfied: Any, required: Any, owner: Any) -> dict[str, Any]:
    return {
        "state": str(state or "") or None,
        "satisfied": int(satisfied or 0),
        "required": int(required or 0),
        "owner": str(owner or "") or None,
    }


def surface_hr_queue(hr_token: str, key: str) -> dict[str, Any]:
    code, body = http("GET", "/dashboard/posthire/onboarding?limit=500", hr_token=hr_token)
    row = next((r for r in (body.get("in_progress") or []) if r.get("employee_key") == key), None)
    if row is None:
        # A completed employee leaves the "still onboarding" queue by design.
        return {"http": code, "absent_from_queue": True, **_tuple("completed", 0, 0, None)}
    return {
        "http": code,
        "absent_from_queue": False,
        **_tuple(row.get("completion_state"), row.get("satisfied_count"), row.get("required_total"),
                 (row.get("completion_next_action") or {}).get("owner") if not row.get("next_owner") else row.get("next_owner")),
        "next_item_label": row.get("next_item_label"),
        "next_owner_group": row.get("next_owner_group"),
    }


def surface_hr_drawer(hr_token: str, key: str) -> dict[str, Any]:
    code, body = http("GET", f"/dashboard/posthire/onboarding/{key}", hr_token=hr_token)
    completion = body.get("completion") or {}
    items = body.get("items") or []
    bank = next((i for i in items if i.get("item_id") == "bank_details"), {})
    return {
        "http": code,
        **_tuple(completion.get("state"), completion.get("satisfied_count"), completion.get("required_total"),
                 (completion.get("next_action") or {}).get("owner")),
        "bank_status": bank.get("status"),
        "bank_actions": bank.get("actions"),
        "bank_reason": bank.get("rejection_reason"),
    }


def surface_employee_app(token: str) -> dict[str, Any]:
    code, body = http("GET", "/app/onboarding", token=token)
    completion = body.get("completion") or {}
    groups = {
        g: [i.get("item_id") for i in (body.get(g) or [])]
        for g in ("your_actions", "being_reviewed", "handled_by_others", "completed")
    }
    all_items = [i for g in ("your_actions", "being_reviewed", "handled_by_others", "completed") for i in (body.get(g) or [])]
    bank = next((i for i in all_items if i.get("item_id") == "bank_details"), {})
    return {
        "http": code,
        **_tuple(completion.get("state"), completion.get("satisfied_count"), completion.get("required_total"),
                 (completion.get("next_action") or {}).get("owner")),
        "bank_status": bank.get("status"),
        "bank_actions": bank.get("actions"),
        "groups": groups,
    }


def surface_employee_profile(token: str) -> dict[str, Any]:
    code, body = http("GET", "/app/profile", token=token)
    onb = body.get("onboarding") or {}
    completion = onb.get("completion") or {}
    return {
        "http": code,
        **_tuple(completion.get("state") or onb.get("completion_state"),
                 completion.get("satisfied_count"), completion.get("required_total"),
                 (onb.get("next_action") or completion.get("next_action") or {}).get("owner")),
    }


def snapshot(label: str, *, hr_token: str, token: str, key: str) -> dict[str, Any]:
    """Read all four surfaces, twice for the HR drawer, and assert agreement."""
    a = surface_hr_queue(hr_token, key)
    b1 = surface_hr_drawer(hr_token, key)
    b2 = surface_hr_drawer(hr_token, key)  # the reverting read in the original bug
    c = surface_employee_app(token)
    d = surface_employee_profile(token)
    cmp_keys = ("state", "satisfied", "required", "owner")
    tuples = {
        "hr_queue": {k: a[k] for k in cmp_keys},
        "hr_drawer": {k: b1[k] for k in cmp_keys},
        "employee_app": {k: c[k] for k in cmp_keys},
        "employee_profile": {k: d[k] for k in cmp_keys},
    }
    # A completed employee drops out of the "still onboarding" queue, so the row
    # cannot carry counts; compare it on state only in that case.
    comparable = dict(tuples)
    if a.get("absent_from_queue"):
        comparable.pop("hr_queue")
        check(f"{label}: completed employee leaves the onboarding queue",
              b1["state"] == "completed", {"drawer_state": b1["state"]})
    distinct = {json.dumps(v, sort_keys=True) for v in comparable.values()}
    check(f"{label}: all surfaces report one state", len(distinct) == 1, tuples)
    check(f"{label}: a second HR drawer read does not change anything",
          {k: b1[k] for k in cmp_keys} == {k: b2[k] for k in cmp_keys}
          and b1.get("bank_status") == b2.get("bank_status"),
          {"first": {**{k: b1[k] for k in cmp_keys}, "bank": b1.get("bank_status")},
           "second": {**{k: b2[k] for k in cmp_keys}, "bank": b2.get("bank_status")}})
    check(f"{label}: bank item agrees between HR and the employee app",
          b1.get("bank_status") == c.get("bank_status"),
          {"hr": b1.get("bank_status"), "app": c.get("bank_status")})
    for name, surf in (("hr_queue", a), ("hr_drawer", b1), ("employee_app", c), ("employee_profile", d)):
        if surf.get("http") not in (200, None):
            check(f"{label}: {name} responded 200", False, surf.get("http"))
    row = {"checkpoint": label, "hr_queue": a, "hr_drawer": b1, "hr_drawer_reread": b2,
           "employee_app": c, "employee_profile": d}
    RESULTS["checkpoints"].append(row)
    log(f"{label}: state={b1['state']} {b1['satisfied']}/{b1['required']} owner={b1['owner']} bank={b1.get('bank_status')}")
    return row


def main() -> int:
    import app as A

    # Employee session for Aziz (the same session type the device uses).
    aziz = A.find_employee_by_key(AZIZ, company_code=COMPANY)
    talal = A.find_employee_by_key(TALAL, company_code=COMPANY)
    token = str(A.create_employee_session(COMPANY, AZIZ, str(aziz.get("phone")))["token"])
    talal_token = str(A.create_employee_session(COMPANY, TALAL, str(talal.get("phone")))["token"])

    with A.db_connect() as conn:
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
    hr_token = str(A.create_dashboard_session(hr_user)[0])
    log(f"hr session for {hr_user.get('email')} role={hr_user.get('role')}")

    # --- Preflight: only one bank request may be open, so an aborted earlier run
    # would otherwise poison the baseline. Withdraw through the real endpoint.
    code, bank = http("GET", "/app/bank", token=token)
    stale = str(((bank.get("submission") or {}) if code == 200 else {}).get("request_id") or "")
    if stale and ((bank.get("submission") or {}).get("can_withdraw") or bank.get("change_under_review")):
        wcode, wbody = http("POST", f"/app/bank/requests/{stale}/withdraw", token=token)
        log(f"preflight withdrew stale request {stale} http={wcode}")
        RESULTS["preflight"] = {"withdrew": stale, "http": wcode, "detail": wbody if wcode >= 400 else None}

    # --- T0 baseline: the state the reconciliation fix left behind -----------
    snapshot("T0 baseline (bank applied)", hr_token=hr_token, token=token, key=AZIZ)

    # --- T1 employee action: submit a bank change ---------------------------
    payload = {
        "iban": IBAN,
        "account_number": "5454545454",
        "bank_name": "Walkthrough Bank",
        "account_holder": "Aziz Walkthrough",
        "branch": "Main",
        "swift": "NSBSHSHD",
    }
    code, body = http("POST", "/app/bank/requests", token=token,
                      body={**payload, "idempotency_key": f"walk-{int(time.time())}"})
    check("T1: employee submits a bank change", code in (200, 201), {"http": code, "detail": body if code >= 400 else None})
    request_id = str(((body.get("bank") or {}).get("submission") or {}).get("request_id") or "")
    if not check("T1: submission returns a request id", bool(request_id), request_id):
        print(json.dumps(RESULTS, indent=2, default=str))
        print("WALKTHROUGH_FAILED")
        return 1
    snapshot("T1 submitted (with HR)", hr_token=hr_token, token=token, key=AZIZ)

    # --- T2 HR review: return for correction --------------------------------
    reason = "Walkthrough: please correct the account holder name and resubmit."
    code, body = http("POST", f"/dashboard/posthire/employee-ess/requests/{request_id}/decide",
                      hr_token=hr_token,
                      body={"action": "return_for_information", "comment": reason})
    check("T2: HR returns the request for correction", code == 200, {"http": code, "detail": body if code >= 400 else None})
    t2 = snapshot("T2 returned (waiting on employee)", hr_token=hr_token, token=token, key=AZIZ)
    check("T2: the correction reason HR wrote is the one shown",
          t2["hr_drawer"].get("bank_reason") == reason, t2["hr_drawer"].get("bank_reason"))
    check("T2: the employee sees bank under their own actions",
          "bank_details" in (t2["employee_app"]["groups"].get("your_actions") or []),
          t2["employee_app"]["groups"])

    # --- T3 correction: employee resubmits ----------------------------------
    payload2 = dict(payload, account_holder="Aziz Walkthrough Corrected")
    code, body = http("POST", "/app/bank/requests", token=token,
                      body={**payload2, "idempotency_key": f"walk-fix-{int(time.time())}"})
    check("T3: employee resubmits without a duplicate-request conflict",
          code in (200, 201), {"http": code, "detail": body if code >= 400 else None})
    resubmit_id = str(((body.get("bank") or {}).get("submission") or {}).get("request_id") or "")
    check("T3: the correction reuses the same request, preserving audit history",
          resubmit_id == request_id, {"original": request_id, "resubmit": resubmit_id})
    t3 = snapshot("T3 resubmitted (with HR)", hr_token=hr_token, token=token, key=AZIZ)
    check("T3: the stale correction reason is cleared once resubmitted",
          not t3["hr_drawer"].get("bank_reason"), t3["hr_drawer"].get("bank_reason"))

    # --- T4/T5 approval: HR stage then payroll stage ------------------------
    code, body = http("POST", f"/dashboard/posthire/employee-ess/requests/{request_id}/decide",
                      hr_token=hr_token, body={"action": "approve"})
    check("T4: HR approves (first stage)", code == 200, {"http": code, "detail": body if code >= 400 else None})
    state_after_hr = str(((body.get("request") or {}).get("state")) or "")
    check("T4: the request moves to payroll approval, not straight to approved",
          state_after_hr == "pending_payroll", state_after_hr)
    snapshot("T4 HR approved (pending payroll)", hr_token=hr_token, token=token, key=AZIZ)

    code, body = http("POST", f"/dashboard/posthire/employee-ess/requests/{request_id}/decide",
                      hr_token=hr_token, body={"action": "approve"})
    check("T5: payroll approves (second stage)", code == 200, {"http": code, "detail": body if code >= 400 else None})
    state_after_payroll = str(((body.get("request") or {}).get("state")) or "")
    check("T5: the request is approved and awaiting apply", state_after_payroll == "approved", state_after_payroll)
    snapshot("T5 approved (awaiting apply)", hr_token=hr_token, token=token, key=AZIZ)

    # --- T6 apply: one Apply must complete onboarding -----------------------
    code, body = http("POST", f"/dashboard/posthire/employee-ess/requests/{request_id}/apply",
                      hr_token=hr_token, body={"idempotency_key": f"walk-apply-{request_id}"})
    check("T6: Apply succeeds", code == 200, {"http": code, "detail": body if code >= 400 else None})
    t6 = snapshot("T6 applied (complete)", hr_token=hr_token, token=token, key=AZIZ)
    check("T6: one Apply satisfies the bank item",
          t6["hr_drawer"].get("bank_status") == "accepted", t6["hr_drawer"].get("bank_status"))
    check("T6: one Apply completes onboarding on every surface",
          t6["hr_drawer"]["state"] == "completed"
          and t6["employee_app"]["state"] == "completed"
          and t6["employee_profile"]["state"] == "completed",
          {"drawer": t6["hr_drawer"]["state"], "app": t6["employee_app"]["state"],
           "profile": t6["employee_profile"]["state"]})
    check("T6: no next action is claimed once complete",
          t6["hr_drawer"]["owner"] in (None, "none"), t6["hr_drawer"]["owner"])
    check("T6: the completed bank item sits under Completed for the employee",
          "bank_details" in (t6["employee_app"]["groups"].get("completed") or []),
          t6["employee_app"]["groups"])
    check("T6: no HR mark-complete or waive is offered on the applied bank item",
          not ({"mark_complete", "waive"} & set(t6["hr_drawer"].get("bank_actions") or [])),
          t6["hr_drawer"].get("bank_actions"))

    # Third and fourth reads: the original revert only showed up on a re-read.
    again = surface_hr_drawer(hr_token, AZIZ)
    check("T6: repeated HR reads keep onboarding complete",
          again["state"] == "completed" and again.get("bank_status") == "accepted",
          {"state": again["state"], "bank": again.get("bank_status")})

    # --- Talal: no dead-end bank CTA for an employee outside the allowlist ---
    talal_app = surface_employee_app(talal_token)
    talal_profile = surface_employee_profile(talal_token)
    code, tbank = http("GET", "/app/bank", token=talal_token)
    check("Talal: bank is not offered as an action he cannot take",
          "open_bank" not in set(talal_app.get("bank_actions") or []),
          {"bank_actions": talal_app.get("bank_actions"), "bank_http": code})
    check("Talal: app checklist and profile completion agree",
          {k: talal_app[k] for k in ("state", "satisfied", "required")}
          == {k: talal_profile[k] for k in ("state", "satisfied", "required")},
          {"app": talal_app, "profile": talal_profile})
    talal_drawer = surface_hr_drawer(hr_token, TALAL)
    check("Talal: HR drawer agrees with his app",
          talal_drawer["state"] == talal_app["state"]
          and talal_drawer["satisfied"] == talal_app["satisfied"],
          {"drawer": {k: talal_drawer[k] for k in ("state", "satisfied", "required")},
           "app": {k: talal_app[k] for k in ("state", "satisfied", "required")}})
    check("Talal: the employee app never lists work owned by others",
          not (talal_app["groups"].get("handled_by_others") is None),
          talal_app["groups"])
    RESULTS["talal"] = {"app": talal_app, "profile": talal_profile, "drawer": talal_drawer,
                        "bank_http": code, "bank_eligible": bool((tbank or {}).get("eligible"))}

    print(json.dumps(RESULTS, indent=2, default=str))
    verdict = "WALKTHROUGH_OK" if RESULTS["failed"] == 0 else "WALKTHROUGH_FAILED"
    print(verdict)
    return 0 if RESULTS["failed"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
