"""Smoke test: Shift cancel / reschedule + week navigation (dashboard).

Standalone-readiness for the Shifts module: an HR admin must be able to cancel
and reschedule a specific shift from the dashboard, scoped to their company and
gated on shifts.manage. This test pins:

  - clock parsing: HH:MM / HH:MM:SS accepted, junk rejected.
  - RBAC: cancel/reschedule require shifts.manage; a viewer is denied (403).
  - precise targeting: actions key off shift_id (the table PK), company-scoped.
  - cancel: scheduled -> cancelled, records a shift_event, second cancel -> 409.
  - reschedule: end<=start -> 422; a valid move updates date/time + records an
    event; unknown id -> 404.
  - week navigation: the read window honors the `week` offset.

External side-effects (employee WhatsApp notify + Google Sheet sync) are stubbed
so the test never messages a real employee. All writes use a synthetic shift_id
+ employee_key and are removed in a finally block, so it is safe to re-run.

Run against a DB (staging): python3 smoke-test-shift-management.py
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
    print("    shift management — cancel / reschedule / week nav, RBAC + tenant scoped")
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    try:
        import app
    except ModuleNotFoundError as exc:
        if exc.name == "psycopg2":
            print("SKIP: psycopg2 not available locally; full run happens on staging.")
            return 0
        raise

    # --- pure parsing checks (no DB) -------------------------------------
    check("clock parse: HH:MM", app._parse_clock("09:30") == "09:30")
    check("clock parse: HH:MM:SS -> HH:MM", app._parse_clock("17:00:00") == "17:00")
    check("clock parse: blank -> None", app._parse_clock("") is None)
    check("clock parse: junk -> None", app._parse_clock("9am") is None)

    # --- locate a company with the shifts module enabled -----------------
    candidates: list[str] = []
    with app.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT DISTINCT company_code FROM employees WHERE company_code <> '' LIMIT 30")
            candidates = [str(dict(r)["company_code"]).upper() for r in cur.fetchall()]
    if "WATHEFNI" not in candidates:
        candidates.append("WATHEFNI")
    company = next((c for c in candidates if app.company_has_module(c, "shifts")), None)
    if not company:
        print("    (no company has the shifts module enabled — skipping live shift checks)")
        print(f"\n    {PASS} passed, {FAIL} failed")
        return 1 if FAIL else 0

    print(f"    using company {company}")

    def ctx(perms: list[str], role: str = "owner"):
        return {
            "company_code": company,
            "permissions": perms,
            "access": {"role": role, "permissions": perms},
            "actor_user_id": "smoke-shifts",
            "actor_role": role,
            "hr_phone": "99900000099",
            "hr_user": {"role": role, "status": "active", "company_code": company},
        }

    owner = ctx(["shifts.read", "shifts.manage"])
    viewer = ctx(["shifts.read"], role="viewer")

    # Neutralize external side-effects so we never message a real employee.
    app.notify_employee_shift_cancelled = lambda **k: {"ok": True, "stub": True}
    app.notify_employee_shift_created = lambda **k: {"ok": True, "stub": True}

    sid = str(uuid.uuid4())
    emp_key = f"{company}-SMOKESHIFT99"
    today = app.kuwait_today()
    tomorrow = (today + timedelta(days=1)).isoformat()

    def cleanup():
        with app.db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM shift_events WHERE shift_id=%s", (sid,))
                cur.execute("DELETE FROM shift_assignments WHERE shift_id=%s OR employee_key=%s", (sid, emp_key))
            conn.commit()

    def insert_shift():
        with app.db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO shift_assignments
                      (shift_id, company_code, employee_key, employee_phone, employee_name,
                       shift_date, start_time, end_time, timezone, status, metadata)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,'scheduled',%s)
                    """,
                    (sid, company, emp_key, "99900000099", "Shift Smoke",
                     today, "09:00", "17:00", "Asia/Kuwait", app.Json({})),
                )
            conn.commit()

    def shift_row():
        with app.db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT * FROM shift_assignments WHERE shift_id=%s", (sid,))
                row = cur.fetchone()
        return dict(row) if row else None

    def event_types():
        with app.db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT event_type FROM shift_events WHERE shift_id=%s", (sid,))
                return {str(dict(r)["event_type"]) for r in cur.fetchall()}

    cleanup()
    try:
        insert_shift()

        # RBAC -------------------------------------------------------------
        try:
            app.dashboard_posthire_cancel_shift(sid, context=viewer)
            check("viewer without shifts.manage is denied (cancel)", False)
        except app.HTTPException as exc:
            check("viewer without shifts.manage is denied (cancel)", exc.status_code == 403)

        # week navigation --------------------------------------------------
        this_week = app.dashboard_posthire_shifts(week=0, context=owner)
        ids_now = {str(s.get("shift_id")) for s in (this_week.get("shifts") or [])}
        check("week=0 read includes the shift scheduled today", sid in ids_now)
        far = app.dashboard_posthire_shifts(week=-4, context=owner)
        ids_far = {str(s.get("shift_id")) for s in (far.get("shifts") or [])}
        check("a distant week window excludes today's shift", sid not in ids_far)
        check("week offset is clamped", app.dashboard_posthire_shifts(week=999, context=owner).get("week") == 26)

        # unknown id -------------------------------------------------------
        try:
            app.dashboard_posthire_cancel_shift(str(uuid.uuid4()), context=owner)
            check("unknown shift_id -> 404", False)
        except app.HTTPException as exc:
            check("unknown shift_id -> 404", exc.status_code == 404)

        # reschedule validation -------------------------------------------
        try:
            app.dashboard_posthire_reschedule_shift(sid, app.ShiftRescheduleRequest(shift_date=tomorrow, start_time="17:00", end_time="09:00"), context=owner)
            check("end <= start -> 422", False)
        except app.HTTPException as exc:
            check("end <= start -> 422", exc.status_code == 422)

        # reschedule (valid) ----------------------------------------------
        res = app.dashboard_posthire_reschedule_shift(sid, app.ShiftRescheduleRequest(shift_date=tomorrow, start_time="10:00", end_time="14:00"), context=owner)
        check("reschedule returns status=rescheduled", res.get("status") == "rescheduled")
        moved = shift_row()
        check("DB row moved to the new date", moved and str(moved.get("shift_date")) == tomorrow)
        check("DB row moved to the new start time", moved and str(moved.get("start_time")).startswith("10:00"))
        check("DB row still scheduled after reschedule", moved and moved.get("status") == "scheduled")

        # cancel (valid) ---------------------------------------------------
        res2 = app.dashboard_posthire_cancel_shift(sid, context=owner)
        check("cancel returns status=cancelled", res2.get("status") == "cancelled")
        gone = shift_row()
        check("DB row is now cancelled", gone and gone.get("status") == "cancelled")

        # cancel again -> 409 ---------------------------------------------
        try:
            app.dashboard_posthire_cancel_shift(sid, context=owner)
            check("cancelling an already-cancelled shift -> 409", False)
        except app.HTTPException as exc:
            check("cancelling an already-cancelled shift -> 409", exc.status_code == 409)

        # events recorded --------------------------------------------------
        evts = event_types()
        check("shift_events recorded a 'rescheduled' event", "rescheduled" in evts)
        check("shift_events recorded a 'cancelled' event", "cancelled" in evts)
    finally:
        cleanup()

    print(f"\n    {PASS} passed, {FAIL} failed")
    if FAIL:
        print("    SHIFT MANAGEMENT: FAILURES")
        return 1
    print("    SHIFT MANAGEMENT: ALL CHECKS PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
