#!/usr/bin/env python3
"""Seed a disposable Schedule visual-QA fixture on a synthetic employee only.

Target: WATHEFNI-96550010001 (Noura Almutairi) — already on the employee-app
allowlist, previously empty shifts/attendance. Aziz/Talal are never touched.

Seeds realistic /app/workday shape for physical Schedule redesign judgment:
  - today: scheduled shift + recorded Present check-in
  - 3 upcoming shifts (distinct times/locations)
  - recent Present / Late (12 min) / Absent mix

Usage (production host):
  WATHEFNI_ENV=production ... .venv/bin/python ops-seed-schedule-visual-fixture.py
  WATHEFNI_ENV=production ... .venv/bin/python ops-seed-schedule-visual-fixture.py --cleanup
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

import production_data_safety as _pds  # noqa: E402

_pds.activate_fixture_tooling_from_argv()
os.environ.setdefault("WATHEFNI_EMPLOYEE_APP", "on")
os.environ.setdefault("WATHEFNI_SCHEMA_APPLY", "0")

import app as legacy  # noqa: E402
from psycopg2.extras import Json  # noqa: E402

COMPANY = os.environ["WATHEFNI_COMPANY_CODE"]
# Existing synthetic bank/ESS fixture — never Aziz/Talal.
KEY = f"{COMPANY}-96550010001"
PROTECTED = {"WATHEFNI-96599338566", "WATHEFNI-96550252254"}
TAG = "schedule-visual-fixture"
STAMP = os.environ.get("SCHEDULE_VISUAL_STAMP") or datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
NOTE = f"{TAG}:{STAMP}"


def _guard() -> None:
    if KEY in PROTECTED:
        raise SystemExit(f"refusing protected canary key {KEY}")


def _kuwait_check(day: Any, hour: int, minute: int = 0) -> datetime:
    """Naive wall time in Asia/Kuwait → timestamptz (Kuwait = UTC+3)."""
    return datetime(day.year, day.month, day.day, hour, minute, tzinfo=timezone(timedelta(hours=3)))


def cleanup() -> dict[str, Any]:
    _guard()
    with legacy.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                DELETE FROM attendance_records
                WHERE company_code=%s AND employee_key=%s
                  AND (notes = %s OR COALESCE(metadata->>'fixture', '') = %s)
                """,
                (COMPANY, KEY, NOTE, TAG),
            )
            att = cur.rowcount
            cur.execute(
                """
                DELETE FROM shift_assignments
                WHERE company_code=%s AND employee_key=%s
                  AND (notes = %s OR COALESCE(metadata->>'fixture', '') = %s)
                """,
                (COMPANY, KEY, NOTE, TAG),
            )
            shifts = cur.rowcount
        conn.commit()
    return {"employee_key": KEY, "deleted_attendance": att, "deleted_shifts": shifts, "stamp": STAMP}


def seed() -> dict[str, Any]:
    _guard()
    today = legacy.kuwait_today()
    emp = legacy.find_employee_by_key(KEY, company_code=COMPANY) or {}
    if not emp:
        raise SystemExit(f"missing synthetic employee {KEY}")
    phone = legacy.digits(emp.get("phone"))
    name = str(emp.get("name") or "")

    meta = Json({"fixture": TAG, "stamp": STAMP, "purpose": "schedule_visual_qa"})

    # Wipe prior fixture rows for this stamp family (same fixture key), keep other data.
    with legacy.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                DELETE FROM attendance_records
                WHERE company_code=%s AND employee_key=%s
                  AND COALESCE(metadata->>'fixture', '') = %s
                """,
                (COMPANY, KEY, TAG),
            )
            cur.execute(
                """
                DELETE FROM shift_assignments
                WHERE company_code=%s AND employee_key=%s
                  AND COALESCE(metadata->>'fixture', '') = %s
                """,
                (COMPANY, KEY, TAG),
            )
        conn.commit()

    def insert_shift(
        on_date: Any,
        start: str,
        end: str,
        *,
        location: str,
        role: str = "Operations",
    ) -> str:
        with legacy.db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO shift_assignments
                        (company_code, employee_key, employee_phone, employee_name,
                         shift_date, start_time, end_time, status, location, role,
                         notes, metadata, assignment_type, source_kind)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,'scheduled',%s,%s,%s,%s,'operations','manual')
                    RETURNING shift_id
                    """,
                    (COMPANY, KEY, phone, name, on_date, start, end, location, role, None, meta),
                )
                sid = str(cur.fetchone()["shift_id"])
            conn.commit()
        return sid

    def insert_attendance(
        on_date: Any,
        *,
        status: str,
        shift_id: str | None = None,
        check_in: datetime | None = None,
        check_out: datetime | None = None,
        late_minutes: int = 0,
        early_leave_minutes: int = 0,
        scheduled_start: str | None = None,
        scheduled_end: str | None = None,
    ) -> None:
        with legacy.db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO attendance_records
                        (company_code, employee_key, employee_phone, employee_name,
                         shift_id, attendance_date, scheduled_start, scheduled_end,
                         check_in_at, check_out_at, status, late_minutes, early_leave_minutes,
                         notes, metadata)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                    """,
                    (
                        COMPANY,
                        KEY,
                        phone,
                        name,
                        shift_id,
                        on_date,
                        scheduled_start,
                        scheduled_end,
                        check_in,
                        check_out,
                        status,
                        late_minutes,
                        early_leave_minutes,
                        None,
                        meta,
                    ),
                )
            conn.commit()

    # --- Today: planned shift + Present with check-in ---
    today_shift = insert_shift(today, "09:00", "17:00", location="Salmiya Branch")
    insert_attendance(
        today,
        status="present",
        shift_id=today_shift,
        check_in=_kuwait_check(today, 9, 2),
        check_out=None,
        scheduled_start="09:00",
        scheduled_end="17:00",
    )

    # --- Upcoming (distinct so the list is useful, not repetitive) ---
    insert_shift(today + timedelta(days=1), "10:00", "18:00", location="Headquarters — Floor 3")
    insert_shift(today + timedelta(days=3), "14:00", "22:00", location="Airport Road Site", role="Night")
    insert_shift(today + timedelta(days=5), "08:30", "12:30", location="Salmiya Branch")

    # --- Recent mix (excluded from today in /app/workday) ---
    d_present = today - timedelta(days=2)
    present_shift = insert_shift(d_present, "09:00", "17:00", location="Salmiya Branch")
    insert_attendance(
        d_present,
        status="present",
        shift_id=present_shift,
        check_in=_kuwait_check(d_present, 8, 58),
        check_out=_kuwait_check(d_present, 17, 1),
        scheduled_start="09:00",
        scheduled_end="17:00",
    )

    d_late = today - timedelta(days=4)
    late_shift = insert_shift(d_late, "09:00", "17:00", location="Headquarters — Floor 3")
    insert_attendance(
        d_late,
        status="late",
        shift_id=late_shift,
        check_in=_kuwait_check(d_late, 9, 12),
        check_out=_kuwait_check(d_late, 17, 0),
        late_minutes=12,
        scheduled_start="09:00",
        scheduled_end="17:00",
    )

    d_absent = today - timedelta(days=6)
    insert_shift(d_absent, "09:00", "17:00", location="Salmiya Branch")
    insert_attendance(
        d_absent,
        status="absent",
        shift_id=None,
        scheduled_start="09:00",
        scheduled_end="17:00",
    )

    # Extra Present so the 30d summary isn't a 1/1/1 strip only.
    d_present2 = today - timedelta(days=8)
    insert_attendance(
        d_present2,
        status="present",
        check_in=_kuwait_check(d_present2, 9, 0),
        check_out=_kuwait_check(d_present2, 17, 0),
        scheduled_start="09:00",
        scheduled_end="17:00",
    )

    # Ensure app access + mint activation code for physical login (code printed once).
    if not emp.get("app_access_enabled"):
        import employee_app_access as access

        access.set_employee_app_access(
            legacy,
            {
                "company_code": COMPANY,
                "user_id": "schedule-visual-fixture",
                "actor_user_id": "schedule-visual-fixture",
                "email": "schedule-visual-fixture@wathefni.ai",
                "permissions": ["employees.manage", "onboarding.manage"],
            },
            employee_key=KEY,
            enabled=True,
            reason="schedule-visual-fixture",
            deliver_invite=False,
        )
        emp = legacy.find_employee_by_key(KEY, company_code=COMPANY) or emp

    invite, code = legacy.create_employee_app_invite(
        COMPANY,
        emp,
        created_by_user_id="schedule-visual-fixture",
    )

    # Verify projection shape without HTTP (no session required).
    ctx = {
        "company_code": COMPANY,
        "employee_key": KEY,
        "employee": emp,
        "phone": phone,
        "session_id": f"schedule-visual-{STAMP}",
        "actor_employee_key": KEY,
        "actor_user_id": f"employee_app:{KEY}",
        "actor_phone": phone,
        "actor_email": emp.get("email") or "",
        "actor_role": "employee",
        "hr_phone": "",
        "hr_user": {"role": "employee", "company_code": COMPANY, "phone": phone, "name": name},
    }
    workday = legacy.app_workday(locale="en", context=ctx)

    summary = (workday.get("window") or {}).get("summary") or {}
    shape = {
        "date": str(workday.get("date")),
        "authority": workday.get("authority"),
        "today_entries": len((workday.get("today") or {}).get("entries") or []),
        "today_kinds": [e.get("kind") for e in ((workday.get("today") or {}).get("entries") or [])],
        "today_location": (
            (((workday.get("today") or {}).get("entries") or [{}])[0].get("scheduled") or {}).get("location")
        ),
        "today_recorded_status": (
            (((workday.get("today") or {}).get("entries") or [{}])[0].get("recorded") or {}).get("status")
        ),
        "upcoming_count": len(workday.get("upcoming") or []),
        "upcoming_dates": [str(s.get("date")) for s in (workday.get("upcoming") or [])],
        "recent_count": len(workday.get("recent") or []),
        "recent_statuses": [r.get("status") for r in (workday.get("recent") or [])],
        "recent_late_minutes": [r.get("late_minutes") for r in (workday.get("recent") or [])],
        "summary": summary,
    }

    ok = (
        shape["today_entries"] == 1
        and shape["today_recorded_status"] == "present"
        and shape["today_location"] == "Salmiya Branch"
        and shape["upcoming_count"] >= 3
        and "late" in shape["recent_statuses"]
        and "absent" in shape["recent_statuses"]
        and "present" in shape["recent_statuses"]
        and 12 in shape["recent_late_minutes"]
    )

    return {
        "ok": ok,
        "stamp": STAMP,
        "employee_key": KEY,
        "name": name,
        "phone": phone,
        "activation_code": code,
        "invite_id": str(invite.get("invite_id") or invite.get("id") or ""),
        "invite_expires_at": str(invite.get("expires_at") or ""),
        "fixture_note": NOTE,
        "shape": shape,
        "protected_untouched": sorted(PROTECTED),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--company", default=os.environ.get("WATHEFNI_COMPANY_CODE"))
    parser.add_argument("--ack-non-production", default=os.environ.get("WATHEFNI_DATA_SAFETY_ACK"))
    parser.add_argument("--cleanup", action="store_true")
    args = parser.parse_args()
    if args.cleanup:
        # Prefer env stamp; if absent, delete all rows tagged with this fixture family.
        global NOTE  # noqa: PLW0603
        if not os.environ.get("SCHEDULE_VISUAL_STAMP"):
            with legacy.db_connect() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        DELETE FROM attendance_records
                        WHERE company_code=%s AND employee_key=%s
                          AND COALESCE(metadata->>'fixture', '') = %s
                        """,
                        (COMPANY, KEY, TAG),
                    )
                    att = cur.rowcount
                    cur.execute(
                        """
                        DELETE FROM shift_assignments
                        WHERE company_code=%s AND employee_key=%s
                          AND COALESCE(metadata->>'fixture', '') = %s
                        """,
                        (COMPANY, KEY, TAG),
                    )
                    shifts = cur.rowcount
                conn.commit()
            print(json.dumps({"employee_key": KEY, "deleted_attendance": att, "deleted_shifts": shifts, "mode": "family"}, indent=2))
            return 0
        print(json.dumps(cleanup(), indent=2))
        return 0

    result = seed()
    print(json.dumps(result, indent=2, default=str))
    return 0 if result.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
