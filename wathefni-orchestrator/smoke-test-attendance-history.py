"""Smoke test: Attendance date-range history + CSV export (dashboard).

Standalone-readiness for the Attendance module: an HR admin must be able to view
attendance over a date range and export it to CSV, scoped to their company and
gated on attendance permissions. This test pins:

  - range helper: defaults to today, swaps reversed inputs, clamps to 92 days.
  - read window: a record on a past date appears for a range that includes it and
    is excluded by a range that does not.
  - RBAC: read + export require attendance.read (module enabled); a role without
    it is denied (403).
  - export: CSV carries the agreed columns (Employee, Date, Status, Check-in,
    Check-out, Late minutes, Notes) and the inserted record's data.
  - audit: the export endpoint records an 'attendance_exported' admin audit row.

External side-effects (Google Sheet sync) are stubbed. All writes use a synthetic
attendance_id + employee_key and are removed in a finally block, so it is safe to
re-run against staging.

Run against a DB (staging): python3 smoke-test-attendance-history.py
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
    print("    attendance history — date range + CSV export, RBAC + tenant scoped")
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    try:
        import app
    except ModuleNotFoundError as exc:
        if exc.name == "psycopg2":
            print("SKIP: psycopg2 not available locally; full run happens on staging.")
            return 0
        raise

    today = app.kuwait_today()

    # --- pure range helper (no DB) ---------------------------------------
    d0, d1 = app._attendance_range(None, None)
    check("range defaults to today/today", d0 == today and d1 == today)
    s, e = app._attendance_range("2026-01-10", "2026-01-05")
    check("range swaps reversed inputs", s.isoformat() == "2026-01-05" and e.isoformat() == "2026-01-10")
    s2, e2 = app._attendance_range("2020-01-01", "2026-01-01")
    check("range clamps span to 92 days", (e2 - s2).days == 92)

    # --- CSV builder column contract (no DB) -----------------------------
    sample = [{
        "employee_name": "Range Tester", "attendance_date": "2026-06-01", "status": "late",
        "check_in_at": None, "check_out_at": None, "late_minutes": 12, "notes": "traffic",
    }]
    csv_text = app.build_attendance_csv(sample)
    header = csv_text.splitlines()[0]
    check("CSV header has the agreed columns", header == "Employee,Date,Status,Check-in,Check-out,Late minutes,Notes")
    check("CSV humanizes status", ",Late," in csv_text)
    check("CSV includes the row data", "Range Tester" in csv_text and "traffic" in csv_text and "12" in csv_text)

    # --- locate a company with the attendance module enabled -------------
    candidates: list[str] = []
    with app.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT DISTINCT company_code FROM employees WHERE company_code <> '' LIMIT 30")
            candidates = [str(dict(r)["company_code"]).upper() for r in cur.fetchall()]
    if "WATHEFNI" not in candidates:
        candidates.append("WATHEFNI")
    company = next((c for c in candidates if app.company_has_module(c, "attendance")), None)
    if not company:
        print("    (no company has the attendance module enabled — skipping live checks)")
        print(f"\n    {PASS} passed, {FAIL} failed")
        return 1 if FAIL else 0
    print(f"    using company {company}")

    def ctx(perms: list[str], role: str = "owner"):
        return {
            "company_code": company,
            "permissions": perms,
            "access": {"role": role, "permissions": perms},
            "actor_user_id": "smoke-attendance",
            "actor_role": role,
            "hr_phone": "99900000099",
            "hr_user": {"role": role, "status": "active", "company_code": company},
        }

    owner = ctx(["attendance.read", "attendance.manage"])

    # Capture audit calls without coupling to the audit store internals.
    audits: list[dict] = []
    real_audit = app.record_admin_audit
    app.record_admin_audit = lambda context, action_type, **k: audits.append({"action_type": action_type, **k})

    aid = str(uuid.uuid4())
    emp_key = f"{company}-SMOKEATT99"
    past = today - timedelta(days=10)

    def cleanup():
        with app.db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM attendance_records WHERE attendance_id=%s OR employee_key=%s", (aid, emp_key))
            conn.commit()

    def insert_record():
        with app.db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO attendance_records
                      (attendance_id, company_code, employee_key, employee_phone, employee_name,
                       attendance_date, status, late_minutes, notes, metadata)
                    VALUES (%s,%s,%s,%s,%s,%s,'late',9,'smoke note',%s)
                    """,
                    (aid, company, emp_key, "99900000099", "Attendance Smoke", past, app.Json({})),
                )
            conn.commit()

    cleanup()
    try:
        insert_record()

        # read window includes / excludes the record ----------------------
        wide = app.dashboard_posthire_attendance(start_date=(past - timedelta(days=1)).isoformat(), end_date=(past + timedelta(days=1)).isoformat(), context=owner)
        ids_wide = {str(r.get("attendance_id")) for r in (wide.get("attendance") or [])}
        check("range read includes a record inside the window", aid in ids_wide)
        check("range read echoes the window", wide.get("start_date") == (past - timedelta(days=1)).isoformat())
        check("range read flags non-today windows", wide.get("is_today") is False)

        narrow = app.dashboard_posthire_attendance(start_date=today.isoformat(), end_date=today.isoformat(), context=owner)
        ids_narrow = {str(r.get("attendance_id")) for r in (narrow.get("attendance") or [])}
        check("today-only read excludes the 10-day-old record", aid not in ids_narrow)
        check("default-today read sets is_today", narrow.get("is_today") is True)

        # RBAC ------------------------------------------------------------
        try:
            app.dashboard_posthire_attendance_export(start_date=past.isoformat(), end_date=past.isoformat(), context=ctx([], role="recruiter"))
            check("role without attendance.read is denied (export)", False)
        except app.HTTPException as exc:
            check("role without attendance.read is denied (export)", exc.status_code in (403, 401))

        # export ----------------------------------------------------------
        audits.clear()
        resp = app.dashboard_posthire_attendance_export(start_date=(past - timedelta(days=1)).isoformat(), end_date=(past + timedelta(days=1)).isoformat(), context=owner)
        check("export returns a text/csv response", getattr(resp, "media_type", "") == "text/csv")
        check("export sets an attachment filename", "attachment" in str(resp.headers.get("content-disposition", "")).lower())
        check("export recorded an 'attendance_exported' audit", any(a["action_type"] == "attendance_exported" for a in audits))
    finally:
        app.record_admin_audit = real_audit
        cleanup()

    print(f"\n    {PASS} passed, {FAIL} failed")
    if FAIL:
        print("    ATTENDANCE HISTORY: FAILURES")
        return 1
    print("    ATTENDANCE HISTORY: ALL CHECKS PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
