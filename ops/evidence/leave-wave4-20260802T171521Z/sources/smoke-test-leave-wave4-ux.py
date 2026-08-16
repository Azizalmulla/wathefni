#!/usr/bin/env python3
"""Leave Wave 4 — UX/controlled readiness smoke (local/staging)."""
from __future__ import annotations

import os
import sys
import uuid
from datetime import date, timedelta
from pathlib import Path

PASS = FAIL = 0
SUFFIX = uuid.uuid4().hex[:8]
PHONE_DIGITS = ("".join(ch for ch in SUFFIX if ch.isdigit()) + "000000")[:6]


def check(label: str, cond: bool, detail=None) -> None:
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"      PASS  {label}")
    else:
        FAIL += 1
        print(f"      FAIL  {label} :: {detail}")


def main() -> int:
    print("    leave wave4 — controlled readiness + enrich + dual-control + allowlist")
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import leave_wave4_controlled as w4
    import leave_workflow_wave3 as w3
    import leave_authority_wave1 as w1

    check("wave4 version", w4.LEAVE_WAVE4_VERSION == "4.0.0")
    check("kill switch off by default path", w4.leave_wave4_enabled() or os.environ.get("WATHEFNI_ENV") == "production")
    os.environ["WATHEFNI_LEAVE_WAVE4"] = "on"
    os.environ["WATHEFNI_LEAVE_WAVE4_KILL"] = ""
    os.environ["WATHEFNI_LEAVE_REAL_DECISION_GATE"] = "on"
    os.environ["WATHEFNI_LEAVE_REAL_DECISION_ALLOWLIST"] = "96599338566,96588009911"
    check("wave4 enabled", w4.leave_wave4_enabled())
    check("gate on", w4.leave_real_decision_gate_enabled())
    check("allowlist has HR", "96599338566" in w4.real_decision_allowlist())
    check(
        "non-allowlisted denied for real",
        w4.real_decision_denied(leave={"leave_id": "x"}, actor_phone="96511111111", is_synthetic_subject=False) is not None,
    )
    check(
        "synthetic bypasses real gate",
        w4.real_decision_denied(leave={"leave_id": "x"}, actor_phone="96511111111", is_synthetic_subject=True) is None,
    )
    check(
        "allowlisted real ok",
        w4.real_decision_denied(leave={"leave_id": "x"}, actor_phone="96599338566", is_synthetic_subject=False) is None,
    )
    enriched = w4.enrich_leave_row_for_ui(
        {
            "leave_id": "1",
            "leave_type": "unpaid",
            "duration_unit": "half_day",
            "half_portion": "am",
            "status": "requested",
            "start_date": (date.today() + timedelta(days=10)).isoformat(),
            "end_date": (date.today() + timedelta(days=10)).isoformat(),
            "chargeable_days": 0.5,
        }
    )
    check("enrich unpaid flag", enriched.get("is_unpaid") is True)
    check("enrich partial flag", enriched.get("is_partial_day") is True)
    check("enrich next_action decide", enriched.get("next_action") == "decide")
    check("enrich balance non-binding", enriched.get("balances_enforced") is False)
    check("self approval still banned", "self_approval_forbidden" in w1.self_decision_denied(
        leave={"employee_phone": "965527100001"}, actor_phone="965527100001", action="approve"
    ).get("error", ""))

    try:
        import app
    except ModuleNotFoundError as exc:
        if exc.name == "psycopg2":
            print(f"\n    {PASS} passed, {FAIL} failed (unit-only)")
            return 1 if FAIL else 0
        raise

    os.environ["WATHEFNI_LEAVE_BALANCES"] = "on"
    os.environ.setdefault("WATHEFNI_LEAVE_POLICY_WAVE2", "on")
    os.environ["WATHEFNI_LEAVE_WORKFLOW_WAVE3"] = "on"
    app.notify_employee_leave_decision = lambda *a, **k: {"ok": True, "stub": True}

    company = "WATHEFNI"
    if not app.company_has_module(company, "leave"):
        print("skip: leave module off")
        print(f"\n    {PASS} passed, {FAIL} failed")
        return 1 if FAIL else 0

    phone = f"965527{PHONE_DIGITS}"
    hr = "96599338566"
    hr2 = "96588009911"
    name = f"LVW4-SYNTH| Emp {SUFFIX}"
    emp_key = None

    def cleanup():
        nonlocal emp_key
        if not emp_key:
            return
        with app.db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT leave_id FROM leave_requests WHERE employee_key=%s", (emp_key,))
                ids = [str(dict(r)["leave_id"]) for r in cur.fetchall()]
                if ids:
                    cur.execute("DELETE FROM leave_dual_control_actions WHERE leave_id = ANY(%s::uuid[])", (ids,))
                    cur.execute("DELETE FROM leave_attachment_audit WHERE leave_id = ANY(%s::uuid[])", (ids,))
                    cur.execute("DELETE FROM leave_request_attachments WHERE leave_id = ANY(%s::uuid[])", (ids,))
                    cur.execute("DELETE FROM leave_payroll_handoff_events WHERE leave_id = ANY(%s::uuid[])", (ids,))
                    cur.execute("DELETE FROM leave_events WHERE leave_id = ANY(%s::uuid[])", (ids,))
                    cur.execute("DELETE FROM leave_ledger WHERE leave_id = ANY(%s::uuid[]) OR employee_key=%s", (ids, emp_key))
                    cur.execute("DELETE FROM leave_requests WHERE leave_id = ANY(%s::uuid[])", (ids,))
                cur.execute("DELETE FROM leave_balances WHERE employee_key=%s", (emp_key,))
                cur.execute("DELETE FROM shift_assignments WHERE employee_key=%s", (emp_key,))
                cur.execute("DELETE FROM employees WHERE employee_key=%s", (emp_key,))
            conn.commit()

    cleanup()
    try:
        with app.db_connect() as conn:
            with conn.cursor() as cur:
                w1.ensure_leave_authority_wave1_schema(cur)
                w3.ensure_leave_workflow_wave3_schema(cur)
                w4.ensure_leave_wave4_schema(cur)
            conn.commit()
        app.create_company_employee(company, name=name, phone=phone, position_title="W4")
        emp = app.find_employee_by_phone(phone, company_code=company) or {}
        emp_key = str(emp.get("employee_key") or "")
        check("synth employee", bool(emp_key))

        today = app.kuwait_today()
        day = today + timedelta(days=21)
        while day.weekday() != 0:
            day += timedelta(days=1)
        with app.db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO shift_assignments
                      (company_code, employee_key, employee_phone, employee_name, shift_date, start_time, end_time, status)
                    VALUES (%s,%s,%s,%s,%s,'09:00','17:00','scheduled')
                    """,
                    (company, emp_key, phone, name, day),
                )
            conn.commit()

        # Real-gate: non-allowlisted HR cannot approve synthetic? Synthetic bypasses.
        req = app.request_leave(
            {
                "employee_phone": phone,
                "leave_type": "annual",
                "start_date": day.isoformat(),
                "end_date": day.isoformat(),
                "duration_unit": "half_day",
                "half_portion": "am",
            },
            company_code=company,
            created_by_phone=phone,
        )
        check("half-day request", bool(req.get("ok")), req)
        lid = (req.get("leave") or {}).get("leave_id")

        # Self-approval denial
        self_a = app.approve_leave_request({"leave_id": lid}, company_code=company, created_by_phone=phone)
        check("self-approval denied", self_a.get("error") == "self_approval_forbidden", self_a)

        # Allowlisted approve ok (synthetic subject)
        appr = app.approve_leave_request(
            {"leave_id": lid, "allow_shift_conflicts": True},
            company_code=company,
            created_by_phone=hr,
        )
        check("allowlisted approve synth", bool(appr.get("ok")), appr)

        # Dual-control on a synthetic stale pending
        past = today - timedelta(days=10)
        with app.db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO leave_requests (
                      company_code, employee_key, employee_phone, employee_name,
                      start_date, end_date, leave_type, status, duration_unit, chargeable_days, row_version
                    ) VALUES (%s,%s,%s,%s,%s,%s,'annual','requested','full_day',1,1)
                    RETURNING *
                    """,
                    (company, emp_key, phone, name, past, past),
                )
                stale = dict(cur.fetchone())
            conn.commit()
        init = app.initiate_leave_stale_dual_control(
            {"leave_id": stale["leave_id"], "action_kind": "expire_stale"},
            company_code=company,
            created_by_phone=hr,
        )
        check("dual initiate", bool(init.get("ok")), init)
        same = app.confirm_leave_stale_dual_control(
            {"leave_id": stale["leave_id"]},
            company_code=company,
            created_by_phone=hr,
        )
        check("dual same actor denied", same.get("error") == "dual_control_same_actor", same)
        conf = app.confirm_leave_stale_dual_control(
            {"leave_id": stale["leave_id"]},
            company_code=company,
            created_by_phone=hr2,
        )
        check("dual confirm expire", bool(conf.get("ok")) and (conf.get("leave") or {}).get("status") == "expired_stale", conf)

        # Holiday status payload
        with app.db_connect() as conn:
            with conn.cursor() as cur:
                hol = w4.holiday_year_status_payload(cur, year=today.year)
        check("holiday status present", "status" in hol, hol)
        check("holiday fail-closed flag when not approved", hol.get("fail_closed_if_enforced") is True or hol.get("status") == "approved", hol)

        # Policy eligibility snapshot for four real keys (read-only; may be absent on staging)
        real_keys = [
            "WATHEFNI-96550252254",
            "WATHEFNI-96566363363",
            "WATHEFNI-96597727743",
            "WATHEFNI-96599411617",
        ]
        with app.db_connect() as conn:
            with conn.cursor() as cur:
                snap = w4.policy_eligibility_snapshot(cur, company_code=company, employee_keys=real_keys)
        check("eligibility snapshot len 4", len(snap) == 4, snap)
        check("honesty enforced false", all(s.get("enforced") is False for s in snap if s.get("ok")), snap)

    finally:
        cleanup()

    print(f"\n    {PASS} passed, {FAIL} failed")
    return 1 if FAIL else 0


if __name__ == "__main__":
    raise SystemExit(main())
