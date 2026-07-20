#!/usr/bin/env python3
"""Staging transactional proof for leave → attendance → payroll invalidation.

Creates a temporary leave + draft timesheet, approves, cancels, then cleans up.
Staging DB only.
"""

from __future__ import annotations

import json
import os
import sys
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

os.environ.setdefault("WATHEFNI_ENV", "staging")
os.environ.setdefault("WATHEFNI_POSTGRES_ENV", "/root/.openclaw/secrets/postgres.staging.env")
os.environ.setdefault("WATHEFNI_WORKSPACE", "/opt/wathefni/staging/workspace")
os.environ.setdefault("WATHEFNI_EXPECTED_DATABASE_HOST", "127.0.0.1")
os.environ.setdefault("WATHEFNI_EXPECTED_DATABASE_PORT", "5432")
os.environ.setdefault("WATHEFNI_EXPECTED_DATABASE_NAME", "wathefni_staging")
os.environ.setdefault("WATHEFNI_DATABASE_ENVIRONMENT_MARKER", "wathefni-staging-hr2-isolation-v1")


def main() -> int:
    import app
    from psycopg2.extras import Json

    app.assert_runtime_environment_binding()
    company = "WATHEFNI"
    token = app.set_active_company_code(company)
    leave_id = None
    employee_key = None
    try:
        with app.db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT employee_key, phone, name
                    FROM employees
                    WHERE company_code=%s
                    ORDER BY updated_at DESC NULLS LAST
                    LIMIT 1
                    """,
                    (company,),
                )
                emp = dict(cur.fetchone())
                employee_key = emp["employee_key"]
                start = date.today() + timedelta(days=45)
                end = start
                cur.execute(
                    """
                    INSERT INTO leave_requests (
                      company_code, employee_key, employee_phone, employee_name,
                      leave_type, start_date, end_date, status, source_text, metadata
                    ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                    RETURNING *
                    """,
                    (
                        company,
                        emp["employee_key"],
                        emp["phone"],
                        emp["name"],
                        "time_off",
                        start,
                        end,
                        "requested",
                        "authority-p0-proof",
                        Json({"proof": True}),
                    ),
                )
                leave = dict(cur.fetchone())
                leave_id = leave["leave_id"]
                period_start = start.replace(day=1)
                period_end = (period_start.replace(day=28) + timedelta(days=4)).replace(day=1) - timedelta(days=1)
                cur.execute(
                    """
                    INSERT INTO payroll_timesheets (
                      company_code, employee_key, employee_phone, employee_name,
                      period_start, period_end, status, scheduled_minutes, worked_minutes,
                      approved_leave_minutes, absent_minutes, late_minutes, early_leave_minutes,
                      overtime_minutes, payroll_status, snapshot, source_counts
                    ) VALUES (%s,%s,%s,%s,%s,%s,'draft',480,480,0,0,0,0,0,'Ready',%s,%s)
                    ON CONFLICT (company_code, employee_key, period_start, period_end) DO UPDATE
                      SET status='draft', payroll_status='Ready', snapshot=%s, updated_at=now()
                    RETURNING *
                    """,
                    (
                        company,
                        emp["employee_key"],
                        emp["phone"],
                        emp["name"],
                        period_start,
                        period_end,
                        Json({"provisional": True}),
                        Json({}),
                        Json({"provisional": True}),
                    ),
                )
                ts = dict(cur.fetchone())
            conn.commit()

        approve = app.approve_leave_request(
            {"leave_id": leave_id, "allow_shift_conflicts": True},
            company_code=company,
            created_by_phone="96500000000",
        )
        cancel = app.cancel_leave_request(
            {"leave_id": leave_id},
            company_code=company,
            created_by_phone="96500000000",
        )
        with app.db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT timesheet_id, status, payroll_status FROM payroll_timesheets WHERE timesheet_id=%s",
                    (ts["timesheet_id"],),
                )
                ts2 = dict(cur.fetchone() or {})
                # Cleanup proof rows
                cur.execute(
                    "DELETE FROM leave_requests WHERE leave_id=%s AND company_code=%s",
                    (leave_id, company),
                )
                cur.execute(
                    """
                    DELETE FROM attendance_records
                    WHERE company_code=%s AND employee_key=%s AND metadata->>'leave_id'=%s
                    """,
                    (company, employee_key, str(leave_id)),
                )
            conn.commit()

        out = {
            "ok": bool(approve.get("ok")) and bool(cancel.get("ok")),
            "approve_ok": bool(approve.get("ok")),
            "approve_payroll_impact": approve.get("payroll_impact"),
            "payroll_invalidated_on_approve": len(approve.get("payroll_invalidated") or []),
            "cancel_ok": bool(cancel.get("ok")),
            "attendance_reversed": len(cancel.get("attendance_reversed") or []),
            "cancel_payroll_impact": cancel.get("payroll_impact"),
            "timesheet_after": ts2,
        }
        print(json.dumps(out, indent=2, default=str))
        return 0 if out["ok"] else 1
    finally:
        app.reset_active_company_code(token)


if __name__ == "__main__":
    raise SystemExit(main())
