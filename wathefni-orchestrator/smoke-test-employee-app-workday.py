#!/usr/bin/env python3
"""Employee App `/app/workday` read-only Schedule projection contract.

Schedule is one surface over two existing authorities — Shifts and Attendance. It must
present what those modules already store and create no authority of its own. This smoke
proves that against real fixtures on the production database (synthetic employees only;
Aziz/Talal are never touched).

Proves:
- entitlement shapes: neither authority is refused, either one alone opens the surface,
  and both together read as one day
- an authority that is off is `disabled` and carries no value (never an empty fact)
- an authority that fails to read is `error`, carries no value, and does not take the
  other authority down with it
- today's record is paired to today's shift only by the canonical `shift_id`
- a record with no matching shift is presented as its own entry, never guessed onto one
- today's record is excluded from the "recent" list so it is not shown twice
- the window summary and the recent list come from the Attendance module's own rows
- cancelled shifts and rows outside the window are not presented
- values are passed through verbatim: no lateness, duration or status is invented
- the surface declares itself read-only: no clocking, no correction, no payroll effect
"""

from __future__ import annotations

import os
import sys
import uuid
from datetime import timedelta
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

import production_data_safety as _r3_data_safety
_r3_data_safety.require_explicit_environment()
os.environ.setdefault("WATHEFNI_EXPECTED_DATABASE_HOST", "127.0.0.1")
os.environ.setdefault("WATHEFNI_EXPECTED_DATABASE_PORT", "5432")
os.environ.setdefault("WATHEFNI_EMPLOYEE_APP", "on")
# A release gate never executes deployment DDL.
os.environ.setdefault("WATHEFNI_SCHEMA_APPLY", "0")

import app as legacy  # noqa: E402
import employee_app_access as access  # noqa: E402
from fastapi import HTTPException  # noqa: E402

COMPANY = "WATHEFNI"
TAG = uuid.uuid4().hex[:8]
FAILS: list[str] = []
CREATED: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    status = "PASS" if ok else "FAIL"
    print(f"{status}  {name}" + (f" — {detail}" if detail else ""))
    if not ok:
        FAILS.append(name)


def hr_ctx() -> dict[str, Any]:
    return {
        "company_code": COMPANY,
        "user_id": "workday-smoke",
        "actor_user_id": "workday-smoke",
        "email": "workday-smoke@wathefni.ai",
        "permissions": ["employees.manage", "onboarding.manage"],
    }


def allow(*keys: str) -> None:
    current = {k for k in (os.environ.get("WATHEFNI_EMPLOYEE_APP_REAL_ALLOWLIST") or "").split(",") if k}
    os.environ["WATHEFNI_EMPLOYEE_APP_REAL_ALLOWLIST"] = ",".join(sorted(current | set(keys)))


def create_employee(suffix: str) -> str:
    phone = f"9657{TAG[:4]}{suffix}"[:11].ljust(11, "0")
    result = legacy.create_company_employee(
        COMPANY,
        name=f"Workday {TAG} {suffix}",
        phone=phone,
        email=f"workday-{TAG}-{suffix}@example.invalid",
        start_onboarding=False,
        seed_compliance=False,
    )
    key = str(result.get("employee_key") or "")
    if key:
        CREATED.append(key)
        allow(key)
        access.set_employee_app_access(
            legacy, hr_ctx(), employee_key=key, enabled=True, reason="workday-smoke", deliver_invite=False
        )
    return key


def employee_ctx(employee_key: str) -> dict[str, Any]:
    """The `/app` context shape without minting a session (no auth path under test)."""
    employee = legacy.find_employee_by_key(employee_key, company_code=COMPANY) or {}
    phone = legacy.digits(employee.get("phone"))
    return {
        "company_code": COMPANY,
        "employee_key": employee_key,
        "employee": employee,
        "phone": phone,
        "session_id": f"workday-{TAG}",
        "actor_employee_key": employee_key,
        "actor_user_id": f"employee_app:{employee_key}",
        "actor_phone": phone,
        "actor_email": employee.get("email") or "",
        "actor_role": "employee",
        "hr_phone": "",
        "hr_user": {"role": "employee", "company_code": COMPANY, "phone": phone, "name": employee.get("name") or ""},
    }


def workday(employee_key: str, *, locale: str = "en") -> dict[str, Any]:
    return legacy.app_workday(locale=locale, context=employee_ctx(employee_key))


def with_modules(modules: set[str], fn: Any) -> Any:
    """Run `fn` with the effective company module set forced, leaving config alone."""
    real = legacy.employee_app_effective_modules

    def fake(_context: dict[str, Any]) -> set[str]:
        return set(modules)

    legacy.employee_app_effective_modules = fake  # type: ignore[assignment]
    try:
        return fn()
    finally:
        legacy.employee_app_effective_modules = real  # type: ignore[assignment]


def seed_shift(
    employee_key: str,
    *,
    on_date: Any,
    start: str,
    end: str,
    status: str = "assigned",
    location: str | None = None,
) -> str:
    with legacy.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO shift_assignments
                    (company_code, employee_key, shift_date, start_time, end_time, status, location)
                VALUES (%s,%s,%s,%s,%s,%s,%s)
                RETURNING shift_id
                """,
                (COMPANY, employee_key, on_date, start, end, status, location),
            )
            shift_id = str(cur.fetchone()["shift_id"])
        conn.commit()
    return shift_id


def seed_attendance(
    employee_key: str,
    *,
    on_date: Any,
    status: str,
    shift_id: str | None = None,
    check_in: str | None = None,
    check_out: str | None = None,
    late_minutes: int = 0,
    early_leave_minutes: int = 0,
    notes: str | None = None,
) -> None:
    with legacy.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO attendance_records
                    (company_code, employee_key, shift_id, attendance_date, status,
                     check_in_at, check_out_at, late_minutes, early_leave_minutes, notes)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                """,
                (
                    COMPANY,
                    employee_key,
                    shift_id,
                    on_date,
                    status,
                    check_in,
                    check_out,
                    late_minutes,
                    early_leave_minutes,
                    notes,
                ),
            )
        conn.commit()


def cleanup() -> None:
    with legacy.db_connect() as conn:
        with conn.cursor() as cur:
            for key in CREATED:
                for table in (
                    "attendance_records",
                    "shift_assignments",
                    "employee_messages",
                    "employee_sessions",
                    "employee_app_invites",
                    "employee_push_tokens",
                ):
                    cur.execute(
                        f"DELETE FROM {table} WHERE company_code=%s AND employee_key=%s",
                        (COMPANY, key),
                    )
                cur.execute(
                    "DELETE FROM employees WHERE company_code=%s AND employee_key=%s",
                    (COMPANY, key),
                )
            conn.commit()


def main() -> int:
    original_policy = access.get_company_app_access_policy(legacy, COMPANY)
    original_allowlist = os.environ.get("WATHEFNI_EMPLOYEE_APP_REAL_ALLOWLIST")
    today = legacy.kuwait_today()
    try:
        with legacy.db_connect() as conn:
            with conn.cursor() as cur:
                access.ensure_access_schema(cur)
                conn.commit()
        access.set_company_app_access_policy(
            legacy, hr_ctx(), module_enabled=True, access_mode="selected", sync_invites=False
        )

        key = create_employee("01")

        # --- 1) Neither authority: the combined surface is refused, not served empty
        try:
            with_modules({"leave"}, lambda: workday(key))
            check("Schedule is refused without either authority", False, "no HTTPException raised")
        except HTTPException as exc:
            detail = exc.detail if isinstance(exc.detail, dict) else {}
            check(
                "Schedule is refused without either authority",
                exc.status_code == 403 and detail.get("error") == "employee_feature_disabled",
                f"{exc.status_code} {detail}",
            )
            check(
                "the refusal names both contributing authorities",
                detail.get("feature") == "shifts+attendance",
                str(detail.get("feature")),
            )

        # --- 2) Shifts alone opens the surface; Attendance stays disabled and empty
        shift_id = seed_shift(key, on_date=today, start="09:00", end="17:00", location=f"Site {TAG}")
        seed_shift(key, on_date=today + timedelta(days=2), start="10:00", end="18:00")
        seed_shift(key, on_date=today + timedelta(days=3), start="10:00", end="18:00", status="cancelled")
        seed_shift(key, on_date=today + timedelta(days=90), start="10:00", end="18:00")

        shifts_only = with_modules({"shifts"}, lambda: workday(key))
        check(
            "shifts alone opens Schedule",
            shifts_only["authority"]["shifts"] == "ready" and shifts_only["authority"]["attendance"] == "disabled",
            str(shifts_only["authority"]),
        )
        check(
            "a disabled attendance authority carries no value",
            shifts_only["recent"] is None
            and shifts_only["window"] is None
            and shifts_only["today"]["recorded_count"] is None,
            str(shifts_only["today"]),
        )
        check(
            "today shows the scheduled shift with no invented record",
            len(shifts_only["today"]["entries"]) == 1
            and shifts_only["today"]["entries"][0]["kind"] == "scheduled"
            and shifts_only["today"]["entries"][0]["recorded"] is None,
            str(shifts_only["today"]["entries"]),
        )
        check(
            "the scheduled entry passes through the module's own values",
            shifts_only["today"]["entries"][0]["scheduled"]["location"] == f"Site {TAG}"
            and str(shifts_only["today"]["entries"][0]["scheduled"]["start_time"]).startswith("09:00"),
            str(shifts_only["today"]["entries"][0]["scheduled"]),
        )
        upcoming_dates = [str(shift["date"]) for shift in shifts_only["upcoming"] or []]
        check(
            "upcoming excludes today and stays inside the window",
            upcoming_dates == [str(today + timedelta(days=2))],
            str(upcoming_dates),
        )
        check(
            "a cancelled shift is never presented",
            all(str(today + timedelta(days=3)) != d for d in upcoming_dates),
            str(upcoming_dates),
        )
        check("Schedule dates the projection in Kuwait time", str(shifts_only["date"]) == str(today))

        # --- 3) Attendance alone opens the surface; Shifts stays disabled and empty
        seed_attendance(
            key,
            on_date=today,
            status="late",
            check_in="2026-01-01T06:12:00+00:00",
            check_out="2026-01-01T14:00:00+00:00",
            late_minutes=12,
            early_leave_minutes=3,
            notes=f"note-{TAG}",
        )
        seed_attendance(key, on_date=today - timedelta(days=2), status="present")
        seed_attendance(key, on_date=today - timedelta(days=4), status="absent")
        seed_attendance(key, on_date=today - timedelta(days=120), status="present")

        attendance_only = with_modules({"attendance"}, lambda: workday(key))
        check(
            "attendance alone opens Schedule",
            attendance_only["authority"]["attendance"] == "ready"
            and attendance_only["authority"]["shifts"] == "disabled",
            str(attendance_only["authority"]),
        )
        check(
            "a disabled shifts authority carries no value",
            attendance_only["upcoming"] is None and attendance_only["today"]["scheduled_count"] is None,
            str(attendance_only["today"]),
        )
        entry = attendance_only["today"]["entries"][0]
        check(
            "today's record is presented without a shift to hang it on",
            len(attendance_only["today"]["entries"]) == 1
            and entry["kind"] == "recorded_only"
            and entry["scheduled"] is None,
            str(attendance_only["today"]["entries"]),
        )
        check(
            "the record's stored lateness and notes are passed through verbatim",
            entry["recorded"]["late_minutes"] == 12
            and entry["recorded"]["early_leave_minutes"] == 3
            and entry["recorded"]["notes"] == f"note-{TAG}"
            and entry["recorded"]["status"] == "late",
            str(entry["recorded"]),
        )
        recent_dates = [str(record["date"]) for record in attendance_only["recent"] or []]
        check(
            "today's record is not repeated in the recent list",
            str(today) not in recent_dates,
            str(recent_dates),
        )
        check(
            "recent is the module's own window, newest first",
            recent_dates == [str(today - timedelta(days=2)), str(today - timedelta(days=4))],
            str(recent_dates),
        )
        check(
            "a row outside the window is not presented",
            str(today - timedelta(days=120)) not in recent_dates,
            str(recent_dates),
        )
        check(
            "the window summary counts the module's rows, including today",
            (attendance_only["window"] or {}).get("summary") == {"present": 1, "late": 1, "absent": 1},
            str(attendance_only["window"]),
        )

        # --- 4) Both authorities: one day, paired by the canonical shift_id
        both = with_modules({"shifts", "attendance"}, lambda: workday(key))
        check(
            "both authorities read as ready",
            both["authority"]["shifts"] == "ready" and both["authority"]["attendance"] == "ready",
            str(both["authority"]),
        )
        check(
            "an unlinked record is its own entry, never guessed onto the shift",
            [e["kind"] for e in both["today"]["entries"]] == ["scheduled", "recorded_only"],
            str([e["kind"] for e in both["today"]["entries"]]),
        )
        check(
            "the unpaired shift still reports no record rather than a wrong one",
            both["today"]["entries"][0]["recorded"] is None,
            str(both["today"]["entries"][0]),
        )

        # Link a second shift and its record: the pair must land in one entry.
        linked_shift = seed_shift(key, on_date=today, start="18:00", end="22:00")
        seed_attendance(
            key,
            on_date=today,
            status="present",
            shift_id=linked_shift,
            check_in="2026-01-01T15:00:00+00:00",
        )
        paired = with_modules({"shifts", "attendance"}, lambda: workday(key))
        linked_entry = next(
            (e for e in paired["today"]["entries"] if (e["scheduled"] or {}).get("shift_id") == linked_shift),
            None,
        )
        check(
            "a record linked to a shift is paired into one entry",
            linked_entry is not None
            and linked_entry["recorded"] is not None
            and linked_entry["recorded"]["shift_id"] == linked_shift,
            str(linked_entry),
        )
        check(
            "pairing consumes the record so it is not shown twice",
            sum(1 for e in paired["today"]["entries"] if (e["recorded"] or {}).get("shift_id") == linked_shift) == 1,
            str(paired["today"]["entries"]),
        )
        check(
            "today's counts come from the modules, not from the entry list",
            paired["today"]["scheduled_count"] == 2 and paired["today"]["recorded_count"] == 2,
            str(paired["today"]),
        )
        check(
            "the still-unpaired shift keeps an explicit missing record",
            any(
                (e["scheduled"] or {}).get("shift_id") == shift_id and e["recorded"] is None
                for e in paired["today"]["entries"]
            ),
            str(paired["today"]["entries"]),
        )

        # --- 5) A failing authority is stated as error and isolated from the other.
        # The forced failure is a real SQL error, so the shared transaction is genuinely
        # aborted: only the per-module savepoint lets the sibling read survive it.
        real_attendance = legacy._employee_attendance_rows

        def exploding_attendance(cur: Any, **_kwargs: Any) -> list[dict[str, Any]]:
            cur.execute("SELECT 1 FROM workday_smoke_missing_table")
            return []

        legacy._employee_attendance_rows = exploding_attendance  # type: ignore[assignment]
        try:
            broken = with_modules({"shifts", "attendance"}, lambda: workday(key))
        finally:
            legacy._employee_attendance_rows = real_attendance  # type: ignore[assignment]
        check(
            "a failed attendance read reports error",
            broken["authority"]["attendance"] == "error",
            str(broken["authority"]),
        )
        check(
            "a failed read carries no value and no fabricated record",
            broken["recent"] is None
            and broken["window"] is None
            and broken["today"]["recorded_count"] is None
            and all(e["recorded"] is None for e in broken["today"]["entries"]),
            str(broken["today"]),
        )
        check(
            "a failed read does not take the other authority down",
            broken["authority"]["shifts"] == "ready" and broken["today"]["scheduled_count"] == 2,
            str(broken["authority"]),
        )

        real_shifts = legacy._employee_shift_rows

        def exploding_shifts(cur: Any, **_kwargs: Any) -> list[dict[str, Any]]:
            cur.execute("SELECT 1 FROM workday_smoke_missing_table")
            return []

        legacy._employee_shift_rows = exploding_shifts  # type: ignore[assignment]
        try:
            broken_shifts = with_modules({"shifts", "attendance"}, lambda: workday(key))
        finally:
            legacy._employee_shift_rows = real_shifts  # type: ignore[assignment]
        check(
            "a failed shifts read reports error and skips the upcoming window",
            broken_shifts["authority"]["shifts"] == "error"
            and broken_shifts["upcoming"] is None
            and broken_shifts["today"]["scheduled_count"] is None,
            str(broken_shifts["authority"]),
        )
        check(
            "a failed shifts read leaves attendance readable",
            broken_shifts["authority"]["attendance"] == "ready" and broken_shifts["recent"] is not None,
            str(broken_shifts["authority"]),
        )
        check(
            "today's records survive a failed schedule read",
            len(broken_shifts["today"]["entries"]) == 2
            and all(e["kind"] == "recorded_only" for e in broken_shifts["today"]["entries"]),
            str(broken_shifts["today"]["entries"]),
        )

        # --- 6) The surface declares itself read-only
        contract = both["read_only"]
        check(
            "Schedule declares no clocking, no correction and no payroll effect",
            contract["employee_clocking"] is False
            and contract["attendance_correction"] is False
            and contract["payroll_effect"] is False,
            str(contract),
        )
        check(
            "Schedule names HR as the authority in both languages",
            bool(contract.get("authority")) and bool(contract.get("authority_ar")),
            str(contract),
        )

        # --- 7) Locale is echoed and constrained
        arabic = with_modules({"shifts"}, lambda: workday(key, locale="ar"))
        check("Schedule echoes the requested locale", arabic["locale"] == "ar")
        weird = with_modules({"shifts"}, lambda: workday(key, locale="fr-CA"))
        check("Schedule falls back to a supported locale", weird["locale"] == "en")

    finally:
        cleanup()
        try:
            access.set_company_app_access_policy(
                legacy,
                hr_ctx(),
                module_enabled=bool(original_policy.get("module_enabled")),
                access_mode=str(original_policy.get("access_mode") or "selected"),
                selected_departments=list(original_policy.get("selected_departments") or []),
                sync_invites=False,
            )
        except Exception:
            pass
        if original_allowlist is None:
            os.environ.pop("WATHEFNI_EMPLOYEE_APP_REAL_ALLOWLIST", None)
        else:
            os.environ["WATHEFNI_EMPLOYEE_APP_REAL_ALLOWLIST"] = original_allowlist

    print("---")
    if FAILS:
        print(f"FAIL count={len(FAILS)}: {', '.join(FAILS)}")
        return 1
    print("PASS employee app workday projection contract")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
