"""Smoke test: Leave standalone readiness — file on behalf + cancel + history.

Standalone-readiness for the Leave module beyond employee-request approval:
HR must be able to file leave for an employee, cancel approved/upcoming leave,
and review history — company-scoped and gated on leave permissions.

This pins the NEW dashboard surface for the batch:
  - history endpoint: view=history returns decided/past leave over a wide window,
    honours the status filter, sorts most-recent first, and is gated on leave.read
    (a role without it is denied).
  - file on behalf: request_leave through the dashboard action path creates a
    'requested' row (no auto-approve, no notification) and records an audit.
  - cancel: cancel_leave_request through the dashboard path is preflight-then-
    confirm, then sets status='cancelled' and records an audit.

External side-effects (employee notification, Google Sheet sync) are stubbed.
All writes use a synthetic employee + leave rows removed in a finally block, so
this is safe to re-run against staging.

Run against a DB (staging): python3 smoke-test-leave-standalone.py
"""

from __future__ import annotations

import sys
import uuid
from datetime import timedelta
from pathlib import Path

PASS = 0
FAIL = 0


def check(label: str, condition: bool) -> None:
    global PASS, FAIL
    if condition:
        PASS += 1
        print(f"      PASS  {label}")
    else:
        FAIL += 1
        print(f"      FAIL  {label}")


def main() -> int:
    print("    leave standalone — file on behalf + cancel + history, RBAC + scope + audit")
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    try:
        import app
    except ModuleNotFoundError as exc:
        if exc.name == "psycopg2":
            print("SKIP: psycopg2 not available locally; full run happens on staging.")
            return 0
        raise

    today = app.kuwait_today()

    # --- locate a company with the leave module enabled ------------------
    candidates: list[str] = []
    with app.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT DISTINCT company_code FROM employees WHERE company_code <> '' LIMIT 30")
            candidates = [str(dict(r)["company_code"]).upper() for r in cur.fetchall()]
    if "WATHEFNI" not in candidates:
        candidates.append("WATHEFNI")
    company = next((c for c in candidates if app.company_has_module(c, "leave")), None)
    if not company:
        print("    (no company has the leave module enabled — skipping)")
        print(f"\n    {PASS} passed, {FAIL} failed")
        return 1 if FAIL else 0
    print(f"    using company {company}")

    def ctx(perms: list[str], role: str = "owner"):
        return {
            "company_code": company,
            "permissions": perms,
            "access": {"role": role, "permissions": perms},
            "actor_user_id": "smoke-leave",
            "actor_role": role,
            "actor_email": "smoke@wathefni.ai",
            "hr_phone": "99900000088",
            "hr_user": {"role": role, "status": "active", "company_code": company},
        }

    owner = ctx(["leave.read", "leave.request", "leave.decide"])

    # Neutralize external side-effects so file/cancel never reach WhatsApp/Sheets.
    app.notify_employee_leave_decision = lambda *a, **k: {"ok": True, "stub": True}
    app.sync_leave_sheet_rows = lambda *a, **k: {"ok": True, "stub": True}
    audits: list[dict] = []
    real_record = app.dashboard_record_action_result
    app.dashboard_record_action_result = lambda action_type, status, payload, reply: audits.append({"action_type": action_type, "status": status})

    emp_phone = "96599000077"
    emp_name = "Leave Smoke Person"
    emp_key = f"{company}-{app.canonical_employee_phone(emp_phone)}"

    def cleanup():
        with app.db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM leave_events WHERE leave_id IN (SELECT leave_id FROM leave_requests WHERE employee_key=%s)", (emp_key,))
                cur.execute("DELETE FROM leave_ledger WHERE employee_key=%s", (emp_key,))
                cur.execute("DELETE FROM leave_requests WHERE employee_key=%s", (emp_key,))
                cur.execute("DELETE FROM employees WHERE employee_key=%s", (emp_key,))
            conn.commit()

    def seed_leave(start, end, status, leave_type="annual"):
        with app.db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO leave_requests
                      (company_code, employee_key, employee_phone, employee_name,
                       start_date, end_date, leave_type, status, reason, metadata)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,'smoke',%s)
                    """,
                    (company, emp_key, app.digits(emp_phone), emp_name, start, end, leave_type, status, app.Json({})),
                )
            conn.commit()

    cleanup()
    try:
        # --- history endpoint: window + status filter + sort -------------
        seed_leave(today - timedelta(days=20), today - timedelta(days=18), "approved")
        seed_leave(today - timedelta(days=15), today - timedelta(days=14), "cancelled")
        seed_leave(today - timedelta(days=10), today - timedelta(days=9), "rejected")

        hist = app.dashboard_posthire_leave(view="history", status=None, context=owner)
        mine = [r for r in (hist.get("history") or []) if str(r.get("employee_key")) == emp_key]
        check("history view returns the decided rows", len(mine) == 3)
        statuses = {str(r.get("status")) for r in mine}
        check("history includes approved/cancelled/rejected", {"approved", "cancelled", "rejected"} <= statuses)
        starts = [str(r.get("start_date")) for r in mine]
        check("history sorts most-recent first", starts == sorted(starts, reverse=True))

        only_approved = app.dashboard_posthire_leave(view="history", status="approved", context=owner)
        mine_appr = [r for r in (only_approved.get("history") or []) if str(r.get("employee_key")) == emp_key]
        check("history status filter returns only approved", len(mine_appr) == 1 and str(mine_appr[0].get("status")) == "approved")

        active = app.dashboard_posthire_leave(view="active", status=None, context=owner)
        check("active view still returns pending/upcoming shape", active.get("view") == "active" and "pending" in active and "upcoming" in active)

        # RBAC: history requires leave.read
        try:
            app.dashboard_posthire_leave(view="history", status=None, context=ctx([], role="recruiter"))
            check("role without leave.read is denied (history)", False)
        except app.HTTPException as exc:
            check("role without leave.read is denied (history)", exc.status_code in (401, 403))

        # --- file on behalf via the dashboard action path ----------------
        seeded = app.create_company_employee(company, name=emp_name, phone=emp_phone, position_title="Tester")
        check("temp employee created/exists", seeded.get("status") in {"created", "exists"})

        audits.clear()
        fstart = (today + timedelta(days=12)).isoformat()
        fend = (today + timedelta(days=13)).isoformat()
        filed = app.run_posthire_dashboard_action(owner, "request_leave", {
            "employee_name": emp_name, "employee_phone": emp_phone,
            "leave_type": "annual", "start_date": fstart, "end_date": fend, "reason": "smoke filing",
        })
        check("file leave via dashboard returns ok", bool(filed.get("ok")))
        check("file leave recorded an audit", any(a["action_type"] == "request_leave" for a in audits))

        with app.db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT leave_id, status FROM leave_requests WHERE employee_key=%s AND start_date=%s", (emp_key, fstart))
                filed_row = cur.fetchone()
        filed_row = dict(filed_row) if filed_row else {}
        check("filed leave is in 'requested' status (no auto-approve)", str(filed_row.get("status")) == "requested")
        leave_id = str(filed_row.get("leave_id")) if filed_row.get("leave_id") else ""

        # RBAC: filing requires leave.request (the dashboard harness raises 403).
        try:
            app.run_posthire_dashboard_action(ctx(["leave.read"], role="viewer"), "request_leave", {
                "employee_name": emp_name, "employee_phone": emp_phone, "leave_type": "annual",
                "start_date": (today + timedelta(days=20)).isoformat(), "end_date": (today + timedelta(days=21)).isoformat(),
            })
            check("viewer (leave.read only) cannot file leave", False)
        except app.HTTPException as exc:
            check("viewer (leave.read only) cannot file leave", exc.status_code in (401, 403))

        # --- cancel via the dashboard action path (preflight-then-confirm)
        audits.clear()
        first = app.run_posthire_dashboard_action(owner, "cancel_leave_request", {"leave_id": leave_id, "employee_name": emp_name})
        check("cancel preflights with a confirmation step", str(first.get("status")) == "needs_confirmation" and bool(first.get("confirmation")))
        conf = first.get("confirmation") or {}
        second = app.run_posthire_dashboard_action(owner, conf.get("action_type") or "cancel_leave_request", conf.get("args") or {})
        check("cancel completes after confirmation", bool(second.get("ok")))
        check("cancel recorded an audit", any(a["action_type"] == "cancel_leave_request" for a in audits))

        with app.db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT status FROM leave_requests WHERE leave_id=%s", (leave_id,))
                row = cur.fetchone()
        check("filed leave is now cancelled", row is not None and str(dict(row).get("status")) == "cancelled")
    finally:
        app.dashboard_record_action_result = real_record
        cleanup()

    print(f"\n    {PASS} passed, {FAIL} failed")
    if FAIL:
        print("    LEAVE STANDALONE: FAILURES")
        return 1
    print("    LEAVE STANDALONE: ALL CHECKS PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
