#!/usr/bin/env python3
"""Wave 2 C3 — Shifts MSS production unlock prove.

Company-scoped manager MSS. Process-scoped flags only. Global MANAGER_ALLOWLIST stays empty.
"""
from __future__ import annotations

import os
import sys
import uuid
from datetime import date, timedelta
from pathlib import Path

PASS = 0
FAIL = 0
SUFFIX = uuid.uuid4().hex[:8]
# Digits-only phone tails — manager_scope_context lookups use digits().
_N = int(SUFFIX, 16) % 100000
COMPANY = f"MSS{_N:05d}"[:12].upper()
OTHER = f"MSX{_N:05d}"[:12].upper()
MGR = f"9655401{_N:05d}"
MGR_OOS = f"9655402{_N:05d}"
EMP_A = f"9655403{_N:05d}"
EMP_B = f"9655404{_N:05d}"
EMP_OUT = f"9655405{_N:05d}"
KEY_A = f"{COMPANY}-A-{SUFFIX}"
KEY_B = f"{COMPANY}-B-{SUFFIX}"
KEY_OUT = f"{COMPANY}-OUT-{SUFFIX}"
BRANCH = f"br-{_N:05d}"


def check(label: str, condition: bool, detail: object = None) -> None:
    global PASS, FAIL
    if condition:
        PASS += 1
        print(f"      PASS  {label}")
    else:
        FAIL += 1
        extra = f" :: {detail}" if detail is not None else ""
        print(f"      FAIL  {label}{extra}")


def _flags(*, mss: str, companies: str, managers: str) -> None:
    os.environ["WATHEFNI_SHIFTS_MSS_C3"] = mss
    os.environ["WATHEFNI_SHIFTS_MSS_COMPANIES"] = companies
    os.environ["WATHEFNI_SHIFTS_MSS_MANAGER_ALLOWLIST"] = managers
    os.environ["WATHEFNI_SHIFTS_MANAGER_ALLOWLIST"] = ""
    os.environ["WATHEFNI_SHIFTS_HR_ALLOWLIST"] = ""
    os.environ["WATHEFNI_SHIFTS_REAL_MUTATION_GATE"] = "1"
    os.environ["WATHEFNI_SHIFTS_WAVE3"] = "1"
    os.environ["WATHEFNI_SHIFTS_WAVE3_COMPANIES"] = f"{COMPANY},{OTHER}"
    os.environ["WATHEFNI_SHIFTS_WAVE5"] = "1"
    os.environ["WATHEFNI_SHIFTS_WAVE5_COMPANIES"] = COMPANY
    os.environ["WATHEFNI_SHIFTS_WAVE5_SYNTHETIC_ONLY"] = "0"
    os.environ["WATHEFNI_SHIFTS_AUTHORITY_WAVE1"] = "1"
    os.environ["WATHEFNI_SHIFTS_AUTHORITY_COMPANIES"] = f"{COMPANY},{OTHER}"
    os.environ["WATHEFNI_SHIFTS_AUTHORITY_SYNTHETIC_ONLY"] = "0"
    os.environ["WATHEFNI_SHIFTS_ALLOW_OVERNIGHT"] = "1"
    os.environ["WATHEFNI_ORG_HIERARCHY"] = "0"


def main() -> int:
    print("    shifts mss c3 — prove")
    sys.path.insert(0, str(Path(__file__).resolve().parent))

    import shifts_mss_c3 as c3
    import shifts_wave3_controlled as w3
    import shifts_controlled_wave6c as w6c
    import shifts_authority_wave1 as w1
    import shifts_publish_wave5 as w5

    check("mss module", c3.PHASE == "shifts_mss_c3")
    check("rollback guidance", "WATHEFNI_SHIFTS_MSS_C3=off" in str(c3.rollback_guidance()))
    check("EN status scheduled", c3.status_label("scheduled", lang="en") == "Scheduled")
    check("AR status scheduled", c3.status_label("scheduled", lang="ar") == "مجدول")
    check("EN status open", c3.status_label("open", lang="en") == "Open")
    check("AR status open", c3.status_label("open", lang="ar") == "مفتوح")
    check("self_decision false in honesty", c3.honesty_payload().get("self_decision") is False)
    check("attendance not required", c3.honesty_payload().get("attendance_required") is False)

    _flags(mss="off", companies="", managers="")
    g0 = c3.mss_enabled_for_company(COMPANY)
    check("global mss off", g0.get("ok") is not True and g0.get("read_only") is True, g0)

    _flags(mss="on", companies="", managers=MGR)
    g1 = c3.mss_enabled_for_company(COMPANY)
    check("empty company allowlist denies", g1.get("ok") is not True and "allowlist" in str(g1.get("gate")), g1)

    _flags(mss="on", companies=COMPANY, managers="")
    g2 = c3.mss_manager_mutation_gate(actor_phone=MGR, company_code=COMPANY, require_scope=False)
    check("empty manager allowlist denies", g2.get("error") == "shifts_mss_manager_not_allowlisted", g2)

    _flags(mss="on", companies=COMPANY, managers=MGR)
    g3 = c3.mss_enabled_for_company(COMPANY)
    check("canary company entitled", g3.get("ok") is True, g3)
    g4 = c3.mss_enabled_for_company(OTHER)
    check("other company denied", g4.get("ok") is not True, g4)
    check("global MANAGER_ALLOWLIST still empty", w3.manager_mutation_allowlist() == set())
    check("wave6c boundary still holds", w6c.allowlists_within_approved_boundary() is True)
    check("legacy manager_real_rollout remains False", w6c.manager_real_rollout_enabled() is False)
    check("C3 manager unlock recognized", w3.actor_is_mss_c3_manager(MGR, COMPANY) is True)
    check(
        "non-allowlisted denied by real_mutation",
        w3.real_mutation_denied(actor_phone="96554099999", is_synthetic_subject=False, company_code=COMPANY) is not None,
    )
    check(
        "C3 manager allowed by real_mutation",
        w3.real_mutation_denied(actor_phone=MGR, is_synthetic_subject=False, company_code=COMPANY) is None,
    )

    try:
        import app
    except ModuleNotFoundError as exc:
        if exc.name == "psycopg2":
            print("SKIP DB: psycopg2 not available locally")
            print(f"\n    {PASS} passed, {FAIL} failed (unit-only)")
            return 1 if FAIL else 0
        raise

    app.notify_employee_shift_cancelled = lambda **k: {"ok": True, "stub": True}
    app.notify_employee_shift_created = lambda **k: {"ok": True, "stub": True}
    app.notify_hr_admins = lambda **k: {"ok": True, "stub": True}
    app.send_custom_employee_message = lambda *a, **k: {"ok": True, "stub": True}

    day = date.today() + timedelta(days=21)
    while day.weekday() >= 4:
        day += timedelta(days=1)
    day2 = day + timedelta(days=1)
    while day2.weekday() >= 4:
        day2 += timedelta(days=1)

    with app.db_connect() as conn:
        with conn.cursor() as cur:
            w1.ensure_shifts_authority_wave1_schema(cur)
            w1.seed_shift_authority_settings(cur, COMPANY)
            w5.ensure_shifts_publish_wave5_schema(cur)
            cur.execute(
                """
                INSERT INTO company_branches (branch_key, company_code, branch_name, is_active, created_at, updated_at)
                VALUES (%s,%s,%s,true,now(),now())
                ON CONFLICT DO NOTHING
                """,
                (BRANCH, COMPANY, f"C3 Branch {SUFFIX}"),
            )
            for key, phone, name in (
                (KEY_A, EMP_A, f"Report A {SUFFIX}"),
                (KEY_B, EMP_B, f"Report B {SUFFIX}"),
                (KEY_OUT, EMP_OUT, f"Out of scope {SUFFIX}"),
            ):
                cur.execute(
                    """
                    INSERT INTO employees (company_code, employee_key, name, phone, raw_json, created_at, updated_at)
                    VALUES (%s,%s,%s,%s,'{}'::jsonb, now(), now())
                    ON CONFLICT DO NOTHING
                    """,
                    (COMPANY, key, name, phone),
                )
                cur.execute(
                    "UPDATE employees SET employment_status='active' WHERE company_code=%s AND employee_key=%s",
                    (COMPANY, key),
                )
            # A and B in branch; OUT not assigned
            for key in (KEY_A, KEY_B):
                cur.execute(
                    """
                    INSERT INTO employee_org_assignments (company_code, employee_key, branch_key, created_at, updated_at)
                    VALUES (%s,%s,%s,now(),now())
                    ON CONFLICT DO NOTHING
                    """,
                    (COMPANY, key, BRANCH),
                )
            cur.execute(
                """
                INSERT INTO manager_scopes (
                  company_code, manager_phone, scope_type, branch_key, role, is_active, updated_at
                ) VALUES (%s,%s,'branch',%s,'manager',true,now())
                RETURNING scope_id
                """,
                (COMPANY, MGR, BRANCH),
            )
            conn.commit()

    scoped = c3.manager_has_real_scope(company_code=COMPANY, manager_phone=MGR)
    check("manager has real scope", scoped.get("ok") is True, scoped)
    ready = c3.mss_manager_mutation_gate(actor_phone=MGR, company_code=COMPANY, require_scope=True)
    check("mss manager ready", ready.get("ok") is True, ready)
    no_scope = c3.mss_manager_mutation_gate(actor_phone=MGR_OOS, company_code=COMPANY, require_scope=True)
    check(
        "allowlisted without scope fails when required",
        no_scope.get("ok") is not True,
        no_scope,
    )

    # Temporarily add OOS manager to allowlist for scope-required prove, then restore
    os.environ["WATHEFNI_SHIFTS_MSS_MANAGER_ALLOWLIST"] = f"{MGR},{MGR_OOS}"
    no_scope2 = c3.mss_manager_mutation_gate(actor_phone=MGR_OOS, company_code=COMPANY, require_scope=True)
    check("mss manager without scope denied", no_scope2.get("error") in {
        "mss_manager_scope_required",
        "mss_manager_scope_empty",
    }, no_scope2)
    os.environ["WATHEFNI_SHIFTS_MSS_MANAGER_ALLOWLIST"] = MGR

    # Roster in-scope
    roster_ok = app.create_shift_assignment(
        {
            "employee_key": KEY_A,
            "date": day.isoformat(),
            "start_time": "09:00",
            "end_time": "17:00",
            "reason": "c3 mss roster in scope",
            "idempotency_key": f"mss-c3-roster-a-{SUFFIX}",
            "company_code": COMPANY,
            "viewer_phone": MGR,
        },
        company_code=COMPANY,
        created_by_phone=MGR,
    )
    check("manager rosters scoped report", roster_ok.get("ok") is True, roster_ok)
    sid_a = str(((roster_ok.get("created") or [{}])[0]).get("shift_id") or "")

    # Hit the scope gate directly (list resolve may hide out-of-scope as not_found).
    emp_out = {
        "employee_key": KEY_OUT,
        "company_code": COMPANY,
        "phone": EMP_OUT,
        "name": f"Out of scope {SUFFIX}",
    }
    roster_out = app.create_shift_assignment_for_employee(
        {
            "employee_key": KEY_OUT,
            "date": day.isoformat(),
            "start_time": "09:00",
            "end_time": "17:00",
            "reason": "c3 mss out of scope attempt",
            "idempotency_key": f"mss-c3-roster-out-{SUFFIX}",
            "company_code": COMPANY,
            "viewer_phone": MGR,
        },
        employee=emp_out,
        company_code=COMPANY,
        created_by_phone=MGR,
    )
    check(
        "manager cannot mutate out-of-scope",
        roster_out.get("ok") is False and roster_out.get("error") == "employee_outside_manager_scope",
        roster_out,
    )

    # Second report shift for swap
    roster_b = app.create_shift_assignment(
        {
            "employee_key": KEY_B,
            "date": day.isoformat(),
            "start_time": "13:00",
            "end_time": "21:00",
            "reason": "c3 mss roster b",
            "idempotency_key": f"mss-c3-roster-b-{SUFFIX}",
            "company_code": COMPANY,
            "viewer_phone": MGR,
        },
        company_code=COMPANY,
        created_by_phone=MGR,
    )
    check("manager rosters second report", roster_b.get("ok") is True, roster_b)
    sid_b = str(((roster_b.get("created") or [{}])[0]).get("shift_id") or "")

    # Employee self-only view contract
    check("employee sees only own key", c3.employee_view_self_only(viewer_employee_key=KEY_A, row_employee_key=KEY_A))
    check(
        "employee cannot see other key",
        c3.employee_view_self_only(viewer_employee_key=KEY_A, row_employee_key=KEY_B) is False,
    )
    with app.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT employee_key FROM shift_assignments
                WHERE company_code=%s AND shift_id=%s
                """,
                (COMPANY, sid_a),
            )
            row = dict(cur.fetchone() or {})
    check(
        "employee own shift data scoped",
        c3.employee_view_self_only(viewer_employee_key=KEY_A, row_employee_key=row.get("employee_key")),
        row,
    )

    # Open shift publish/claim
    with app.db_connect() as conn:
        with conn.cursor() as cur:
            open_pub = w5.create_open_shift(
                cur,
                company_code=COMPANY,
                payload={
                    "shift_date": day2.isoformat(),
                    "start_time": "10:00",
                    "end_time": "14:00",
                    "notes": f"c3 open {SUFFIX}",
                    "role": "ops",
                    "branch_key": BRANCH,
                },
                actor_phone=MGR,
            )
            check("open shift publish", open_pub.get("ok") is True, open_pub)
            open_id = str((open_pub.get("open_shift") or {}).get("open_shift_id") or "")
            claim = w5.claim_open_shift(
                cur,
                company_code=COMPANY,
                open_shift_id=open_id,
                employee={"employee_key": KEY_A, "phone": EMP_A, "name": f"Report A {SUFFIX}"},
                actor_phone=EMP_A,
            )
            check("open shift claim", claim.get("ok") is True, claim)
            claim_id = str((claim.get("claim") or {}).get("claim_id") or "")
            self_os = w5.decide_open_shift_claim(
                cur,
                company_code=COMPANY,
                claim_id=claim_id,
                decision="approved",
                actor_phone=EMP_A,
                actor_employee_key=KEY_A,
                create_fn=app.create_shift_assignment,
            )
            check("open-shift self-approval denied", self_os.get("error") == "self_approval_denied", self_os)
            os_row = w5.get_open_shift(cur, company_code=COMPANY, open_shift_id=open_id) or {}
            approve_os = w5.decide_open_shift_claim(
                cur,
                company_code=COMPANY,
                claim_id=claim_id,
                decision="approved",
                actor_phone=MGR,
                actor_employee_key=None,
                expected_row_version=int(os_row.get("row_version") or 0),
                create_fn=app.create_shift_assignment,
            )
            check("open-shift claim approved by manager", approve_os.get("ok") is True, approve_os)
            stale_os = w5.decide_open_shift_claim(
                cur,
                company_code=COMPANY,
                claim_id=claim_id,
                decision="approved",
                actor_phone=MGR,
                expected_row_version=0,
                create_fn=app.create_shift_assignment,
            )
            check(
                "stale/duplicate open-shift decision fails safely",
                stale_os.get("ok") is False
                and stale_os.get("error")
                in {"claim_not_pending", "stale_open_shift", "open_shift_already_resolved"},
                stale_os,
            )
        conn.commit()

    # Swap request + self-decision ban + approve/reject + stale
    swap_req = app.request_shift_swap(
        {
            "employee_key": KEY_A,
            "target_employee_key": KEY_B,
            "target_phone": EMP_B,
            "shift_id": sid_a,
            "target_shift_id": sid_b,
            "date": day.isoformat(),
            "reason": f"c3 swap {SUFFIX}",
            "company_code": COMPANY,
        },
        company_code=COMPANY,
        created_by_phone=EMP_A,
    )
    check("swap requested", swap_req.get("ok") is True, swap_req)
    swap_id = str((swap_req.get("swap") or {}).get("swap_id") or "")

    self_swap = app.approve_shift_swap(
        {"swap_id": swap_id, "company_code": COMPANY, "viewer_phone": EMP_A},
        company_code=COMPANY,
        created_by_phone=EMP_A,
    )
    check(
        "manager/employee cannot approve own swap",
        self_swap.get("ok") is False
        and self_swap.get("error")
        in {"self_swap_decision_forbidden", "shifts_real_mutation_not_allowlisted"},
        self_swap,
    )

    # Reject path (decision works)
    reject = app.reject_shift_swap(
        {"swap_id": swap_id, "company_code": COMPANY, "viewer_phone": MGR},
        company_code=COMPANY,
        created_by_phone=MGR,
    )
    check("requested swap reject works", reject.get("ok") is True, reject)

    # Fresh swap for approve + stale
    swap2 = app.request_shift_swap(
        {
            "employee_key": KEY_B,
            "target_employee_key": KEY_A,
            "target_phone": EMP_A,
            "shift_id": sid_b,
            "target_shift_id": sid_a,
            "date": day.isoformat(),
            "reason": f"c3 swap2 {SUFFIX}",
            "company_code": COMPANY,
        },
        company_code=COMPANY,
        created_by_phone=EMP_B,
    )
    swap2_id = str((swap2.get("swap") or {}).get("swap_id") or "")
    approve = app.approve_shift_swap(
        {"swap_id": swap2_id, "company_code": COMPANY, "viewer_phone": MGR},
        company_code=COMPANY,
        created_by_phone=MGR,
    )
    check("requested swap approve works", approve.get("ok") is True, approve)
    stale_swap = app.reject_shift_swap(
        {"swap_id": swap2_id, "company_code": COMPANY, "viewer_phone": MGR},
        company_code=COMPANY,
        created_by_phone=MGR,
    )
    check(
        "stale concurrent swap decision fails safely",
        stale_swap.get("ok") is False
        or stale_swap.get("idempotent") is True
        or stale_swap.get("error") in {"stale_swap_decision", "shift_swap_not_found"},
        stale_swap,
    )

    # Module-off / empty-allowlist honest read-only
    _flags(mss="off", companies=COMPANY, managers=MGR)
    off = c3.mss_enabled_for_company(COMPANY)
    check("module-off is read-only", off.get("ok") is not True and off.get("read_only") is True, off)
    denied_off = w3.real_mutation_denied(actor_phone=MGR, is_synthetic_subject=False, company_code=COMPANY)
    check("module-off manager mutation denied", denied_off is not None, denied_off)

    _flags(mss="on", companies="", managers=MGR)
    empty = c3.mss_enabled_for_company(COMPANY)
    check("empty-allowlist read-only", empty.get("read_only") is True, empty)

    # Restore entitled flags for final honesty / independence
    _flags(mss="on", companies=COMPANY, managers=MGR)
    check("tenant isolation other company", c3.mss_enabled_for_company(OTHER).get("ok") is not True)
    h = c3.honesty_payload(company_code=COMPANY)
    check("leave not mutated", h.get("leave_balances_mutated") is False)
    check("payroll money false", h.get("payroll_money") is False)
    check("attendance authority not mutated", h.get("attendance_authority_mutated") is False)
    check(
        "shifts independent of attendance module",
        "attendance_truth_c1" not in Path(__file__).with_name("shifts_mss_c3.py").read_text(),
    )
    check(
        "global manager allowlist still empty after prove",
        w3.manager_mutation_allowlist() == set(),
    )

    print(f"\n    {PASS} passed, {FAIL} failed")
    if FAIL:
        return 1
    print("SHIFTS_MSS_UNIT_PASS")
    print("SHIFTS_MSS_FULL_PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
