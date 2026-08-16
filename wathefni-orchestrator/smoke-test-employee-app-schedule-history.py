#!/usr/bin/env python3
"""Employee App `/app/schedule/history` attendance history pagination contract.

Proves keyset paging beyond the `/app/workday` ~30-day window without inventing
shift facts. Synthetic employees only; Aziz/Talal untouched.
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
        "user_id": "sched-hist-smoke",
        "actor_user_id": "sched-hist-smoke",
        "email": "sched-hist-smoke@wathefni.ai",
        "permissions": ["employees.manage", "onboarding.manage"],
    }


def allow(*keys: str) -> None:
    current = {k for k in (os.environ.get("WATHEFNI_EMPLOYEE_APP_REAL_ALLOWLIST") or "").split(",") if k}
    os.environ["WATHEFNI_EMPLOYEE_APP_REAL_ALLOWLIST"] = ",".join(sorted(current | set(keys)))


def create_employee(suffix: str) -> str:
    phone = f"9657{TAG[:4]}{suffix}"[:11].ljust(11, "0")
    result = legacy.create_company_employee(
        COMPANY,
        name=f"SchedHist {TAG} {suffix}",
        phone=phone,
        email=f"sched-hist-{TAG}-{suffix}@example.invalid",
        start_onboarding=False,
        seed_compliance=False,
    )
    key = str(result.get("employee_key") or "")
    if key:
        CREATED.append(key)
        allow(key)
        access.set_employee_app_access(
            legacy, hr_ctx(), employee_key=key, enabled=True, reason="sched-hist-smoke", deliver_invite=False
        )
    return key


def employee_ctx(employee_key: str) -> dict[str, Any]:
    employee = legacy.find_employee_by_key(employee_key, company_code=COMPANY) or {}
    phone = legacy.digits(employee.get("phone"))
    return {
        "company_code": COMPANY,
        "employee_key": employee_key,
        "employee": employee,
        "phone": phone,
        "session_id": f"sched-hist-{TAG}",
        "actor_employee_key": employee_key,
        "actor_user_id": f"employee_app:{employee_key}",
        "actor_phone": phone,
        "actor_email": employee.get("email") or "",
        "actor_role": "employee",
        "hr_phone": "",
        "hr_user": {
            "role": "employee",
            "company_code": COMPANY,
            "phone": phone,
            "name": employee.get("name") or "",
        },
    }


def with_modules(modules: set[str], fn: Any) -> Any:
    real = legacy.employee_app_effective_modules

    def fake(_context: dict[str, Any]) -> set[str]:
        return set(modules)

    legacy.employee_app_effective_modules = fake  # type: ignore[assignment]
    try:
        return fn()
    finally:
        legacy.employee_app_effective_modules = real  # type: ignore[assignment]


def seed_shift(employee_key: str, *, on_date: Any, start: str = "09:00", end: str = "17:00") -> str:
    with legacy.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO shift_assignments
                    (company_code, employee_key, shift_date, start_time, end_time, status, location)
                VALUES (%s,%s,%s,%s,%s,'assigned',%s)
                RETURNING shift_id
                """,
                (COMPANY, employee_key, on_date, start, end, f"Site {TAG}"),
            )
            sid = str(cur.fetchone()["shift_id"])
        conn.commit()
    return sid


def seed_attendance(
    employee_key: str,
    *,
    on_date: Any,
    status: str = "present",
    shift_id: str | None = None,
) -> None:
    with legacy.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO attendance_records
                    (company_code, employee_key, shift_id, attendance_date, status)
                VALUES (%s,%s,%s,%s,%s)
                """,
                (COMPANY, employee_key, shift_id, on_date, status),
            )
        conn.commit()


def cleanup() -> None:
    with legacy.db_connect() as conn:
        with conn.cursor() as cur:
            for key in CREATED:
                for table in ("attendance_records", "shift_assignments", "employee_sessions", "employee_app_invites"):
                    cur.execute(
                        f"DELETE FROM {table} WHERE company_code=%s AND employee_key=%s",
                        (COMPANY, key),
                    )
                cur.execute(
                    "DELETE FROM employees WHERE company_code=%s AND employee_key=%s",
                    (COMPANY, key),
                )
            conn.commit()


def history(employee_key: str, **kwargs: Any) -> dict[str, Any]:
    # Explicit Query-param defaults so direct (non-ASGI) calls do not leave FastAPI Query() objects.
    params: dict[str, Any] = {
        "locale": "en",
        "limit": 30,
        "cursor": None,
        "date_from": None,
        "date_to": None,
    }
    params.update(kwargs)
    return with_modules(
        {"attendance", "shifts"},
        lambda: legacy.app_schedule_history(context=employee_ctx(employee_key), **params),
    )


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

        # Cursor unit
        token = legacy.encode_schedule_history_cursor(
            {"attendance_date": "2024-01-15", "attendance_id": "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"}
        )
        decoded = legacy.decode_schedule_history_cursor(token)
        check(
            "cursor round-trips",
            decoded == {"d": "2024-01-15", "id": "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"},
        )
        try:
            legacy.decode_schedule_history_cursor("!!!")
            check("malformed cursor raises", False)
        except ValueError:
            check("malformed cursor raises", True)

        key_a = create_employee("01")
        key_b = create_employee("02")

        # Seed: mix of recent + older-than-30d, one with real shift, one without
        old = today - timedelta(days=120)
        mid = today - timedelta(days=45)
        recent = today - timedelta(days=3)
        sid = seed_shift(key_a, on_date=old)
        seed_attendance(key_a, on_date=old, status="present", shift_id=sid)
        seed_attendance(key_a, on_date=mid, status="late")
        seed_attendance(key_a, on_date=recent, status="absent")
        seed_attendance(key_a, on_date=today - timedelta(days=10), status="present")
        seed_attendance(key_a, on_date=today - timedelta(days=11), status="present")
        # Peer employee row must not leak
        seed_attendance(key_b, on_date=old, status="present")

        # Empty employee
        key_empty = create_employee("03")
        empty = history(key_empty, limit=10)
        check("empty history", empty.get("records") == [] and empty.get("has_more") is False)

        # Pages of 2 across 5 rows
        p1 = history(key_a, limit=2)
        check("page1 has_more", p1.get("has_more") is True)
        check("page1 size", len(p1.get("records") or []) == 2)
        check("page1 newest-first", (p1["records"][0]["recorded"]["date"] >= p1["records"][1]["recorded"]["date"]))
        ids1 = [r["recorded"]["attendance_id"] for r in p1["records"]]

        p2 = history(key_a, limit=2, cursor=p1.get("next_cursor"))
        ids2 = [r["recorded"]["attendance_id"] for r in p2["records"]]
        check("pages do not overlap", set(ids1).isdisjoint(ids2), str(set(ids1) & set(ids2)))
        check("page2 has_more", p2.get("has_more") is True)

        p3 = history(key_a, limit=2, cursor=p2.get("next_cursor"))
        ids3 = [r["recorded"]["attendance_id"] for r in p3["records"]]
        check("final page drains", p3.get("has_more") is False and len(ids3) == 1)
        all_ids = ids1 + ids2 + ids3
        check("no duplicates across cursors", len(all_ids) == len(set(all_ids)) == 5)
        check("all five reachable", len(set(all_ids)) == 5)

        # Old row beyond 30d is present and may carry scheduled when shift_id resolves
        deep = history(key_a, limit=50, date_from=(today - timedelta(days=200)).isoformat(), date_to=old.isoformat())
        deep_dates = [r["recorded"]["date"] for r in (deep.get("records") or [])]
        check("older-than-30d reachable", str(old) in {str(d) for d in deep_dates}, str(deep_dates))
        paired = next((r for r in deep["records"] if str(r["recorded"]["date"]) == str(old)), None)
        check(
            "canonical shift attached when shift_id exists",
            paired is not None and paired.get("scheduled") is not None and paired["scheduled"]["shift_id"] == sid,
        )
        unpaired = next((r for r in (p1.get("records") or []) if not r["recorded"].get("shift_id")), None)
        # Find a record without shift in full list
        full = history(key_a, limit=50)
        no_shift = next((r for r in full["records"] if not r["recorded"].get("shift_id")), None)
        check(
            "no fabricated scheduled without shift_id",
            no_shift is not None and no_shift.get("scheduled") is None,
        )

        # Isolation
        peer = history(key_b, limit=20)
        peer_ids = {r["recorded"]["attendance_id"] for r in (peer.get("records") or [])}
        check("employee isolation", set(all_ids).isdisjoint(peer_ids))

        with legacy.db_connect() as conn:
            with conn.cursor() as cur:
                foreign = legacy._employee_attendance_history_page(
                    cur,
                    company_code="OTHERCO",
                    employee_key=key_a,
                    limit=20,
                )
        check(
            "tenant isolation (wrong company empty)",
            foreign.get("records") == [] and foreign.get("has_more") is False,
        )

        # Ordering: newest date first across full page
        ordered_dates = [str(r["recorded"]["date"]) for r in full["records"]]
        check("newest→oldest ordering", ordered_dates == sorted(ordered_dates, reverse=True), str(ordered_dates))

        # Invalid cursor / range
        try:
            history(key_a, cursor="not-a-cursor")
            check("invalid cursor → 400", False)
        except HTTPException as exc:
            err = (exc.detail or {}).get("error") if isinstance(exc.detail, dict) else None
            check("invalid cursor → 400", exc.status_code == 400 and err == "invalid_cursor")

        try:
            history(key_a, date_from=(today + timedelta(days=1)).isoformat(), date_to=today.isoformat())
            # date_from > date_to after cap? today+1 capped... date_from tomorrow > date_to today
            check("invalid range → 400", False)
        except HTTPException as exc:
            err = (exc.detail or {}).get("error") if isinstance(exc.detail, dict) else None
            check("invalid range → 400", exc.status_code == 400 and err == "invalid_range", str(exc.detail))

        try:
            history(key_a, date_from="not-a-date")
            check("invalid date_from → 400", False)
        except HTTPException as exc:
            err = (exc.detail or {}).get("error") if isinstance(exc.detail, dict) else None
            check("invalid date_from → 400", exc.status_code == 400 and err == "invalid_date_from")

        # Attendance entitlement required
        try:
            with_modules(
                {"shifts"},
                lambda: legacy.app_schedule_history(
                    locale="en",
                    limit=10,
                    cursor=None,
                    date_from=None,
                    date_to=None,
                    context=employee_ctx(key_a),
                ),
            )
            check("shifts-only refused", False)
        except HTTPException as exc:
            check("shifts-only refused", exc.status_code in (403, 404), str(exc.status_code))

        # /app/workday still 30-day window (regression sample)
        wd = with_modules({"attendance", "shifts"}, lambda: legacy.app_workday(context=employee_ctx(key_a)))
        check("workday window still 30", (wd.get("window") or {}).get("days") == 30)
        recent_dates = {str(r.get("date")) for r in (wd.get("recent") or [])}
        check(
            "workday recent excludes ancient row",
            str(old) not in recent_dates,
            str(recent_dates),
        )

    finally:
        cleanup()
        try:
            access.set_company_app_access_policy(
                legacy,
                hr_ctx(),
                module_enabled=bool((original_policy or {}).get("module_enabled", True)),
                access_mode=str((original_policy or {}).get("access_mode") or "open"),
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
        print(f"FAIL employee schedule history contract ({len(FAILS)}) — {', '.join(FAILS)}")
        return 1
    print("PASS employee schedule history contract")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
