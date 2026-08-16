#!/usr/bin/env python3
"""Employee App `/app/leave/history` leave-request pagination contract.

Proves keyset paging beyond the `/app/leave` ~50-row window without inventing
balance/policy facts. Synthetic employees only; Aziz/Talal untouched.
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
        "user_id": "leave-hist-smoke",
        "actor_user_id": "leave-hist-smoke",
        "email": "leave-hist-smoke@wathefni.ai",
        "permissions": ["employees.manage", "onboarding.manage"],
    }


def allow(*keys: str) -> None:
    current = {k for k in (os.environ.get("WATHEFNI_EMPLOYEE_APP_REAL_ALLOWLIST") or "").split(",") if k}
    os.environ["WATHEFNI_EMPLOYEE_APP_REAL_ALLOWLIST"] = ",".join(sorted(current | set(keys)))


def create_employee(suffix: str) -> str:
    phone = f"9658{TAG[:4]}{suffix}"[:11].ljust(11, "0")
    result = legacy.create_company_employee(
        COMPANY,
        name=f"LeaveHist {TAG} {suffix}",
        phone=phone,
        email=f"leave-hist-{TAG}-{suffix}@example.invalid",
        start_onboarding=False,
        seed_compliance=False,
    )
    key = str(result.get("employee_key") or "")
    if key:
        CREATED.append(key)
        allow(key)
        access.set_employee_app_access(
            legacy, hr_ctx(), employee_key=key, enabled=True, reason="leave-hist-smoke", deliver_invite=False
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
        "session_id": f"leave-hist-{TAG}",
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


def seed_leave(
    employee_key: str,
    *,
    start: Any,
    end: Any | None = None,
    status: str = "cancelled",
    leave_type: str = "annual",
    reason: str = "leave-hist-smoke",
) -> str:
    end_date = end if end is not None else start
    with legacy.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO leave_requests
                    (company_code, employee_key, start_date, end_date, leave_type, status, reason)
                VALUES (%s,%s,%s,%s,%s,%s,%s)
                RETURNING leave_id
                """,
                (COMPANY, employee_key, start, end_date, leave_type, status, reason),
            )
            leave_id = str(cur.fetchone()["leave_id"])
        conn.commit()
    return leave_id


def cleanup() -> None:
    with legacy.db_connect() as conn:
        with conn.cursor() as cur:
            for key in CREATED:
                for table in ("leave_requests", "employee_sessions", "employee_app_invites"):
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
    params: dict[str, Any] = {
        "locale": "en",
        "limit": 30,
        "cursor": None,
        "date_from": None,
        "date_to": None,
        "year": None,
        "status": None,
    }
    params.update(kwargs)
    return with_modules(
        {"leave"},
        lambda: legacy.app_leave_history(context=employee_ctx(employee_key), **params),
    )


def root_leave(employee_key: str) -> dict[str, Any]:
    return with_modules({"leave"}, lambda: legacy.app_leave(context=employee_ctx(employee_key)))


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

        token = legacy.encode_leave_history_cursor(
            {"start_date": "2024-01-15", "leave_id": "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"}
        )
        decoded = legacy.decode_leave_history_cursor(token)
        check(
            "cursor round-trips",
            decoded == {"d": "2024-01-15", "id": "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"},
        )
        try:
            legacy.decode_leave_history_cursor("!!!")
            check("malformed cursor raises", False)
        except ValueError:
            check("malformed cursor raises", True)

        key_a = create_employee("01")
        key_b = create_employee("02")
        key_empty = create_employee("03")

        empty = history(key_empty, limit=10)
        check("empty history", empty.get("requests") == [] and empty.get("has_more") is False)

        # Mix of statuses + enough rows to exceed `/app/leave` hard cap of 50
        statuses_cycle = ["cancelled", "rejected", "approved", "requested", "completed"]
        seeded_ids: list[str] = []
        seeded_by_status: dict[str, list[str]] = {}
        for i in range(55):
            st = statuses_cycle[i % len(statuses_cycle)]
            start = today - timedelta(days=400 - i)  # spread into older history
            lid = seed_leave(key_a, start=start, status=st, reason=f"{TAG}-{i}")
            seeded_ids.append(lid)
            seeded_by_status.setdefault(st, []).append(lid)

        # Peer isolation seed
        peer_id = seed_leave(key_b, start=today - timedelta(days=10), status="cancelled")

        # Pages of 2
        p1 = history(key_a, limit=2)
        check("page1 has_more", p1.get("has_more") is True)
        check("page1 size", len(p1.get("requests") or []) == 2)
        check(
            "page1 newest-first",
            str(p1["requests"][0]["start_date"]) >= str(p1["requests"][1]["start_date"]),
        )
        ids1 = [r["leave_id"] for r in p1["requests"]]

        p2 = history(key_a, limit=2, cursor=p1.get("next_cursor"))
        ids2 = [r["leave_id"] for r in p2["requests"]]
        check("pages do not overlap", set(ids1).isdisjoint(ids2), str(set(ids1) & set(ids2)))
        check("page2 has_more", p2.get("has_more") is True)

        # Drain all via small pages
        seen: list[str] = []
        cursor = None
        pages = 0
        while True:
            page = history(key_a, limit=10, cursor=cursor)
            pages += 1
            batch = [r["leave_id"] for r in (page.get("requests") or [])]
            seen.extend(batch)
            if not page.get("has_more"):
                break
            cursor = page.get("next_cursor")
            if pages > 20:
                break
        check("no duplicates across cursors", len(seen) == len(set(seen)))
        check("all seeded reachable", set(seen) == set(seeded_ids), f"got={len(seen)} want={len(seeded_ids)}")
        check("older-than-50-cap reachable", len(seen) > 50)

        # Status preservation + filter
        cancelled = history(key_a, limit=50, status="cancelled")
        cancelled_ids = {r["leave_id"] for r in (cancelled.get("requests") or [])}
        check(
            "status filter cancelled only",
            cancelled_ids == set(seeded_by_status["cancelled"]) and cancelled_ids,
            f"got={len(cancelled_ids)}",
        )
        check(
            "status values preserved",
            all(r.get("status") == "cancelled" for r in cancelled["requests"]),
        )

        # Year / range
        old_year = (today - timedelta(days=400)).year
        by_year = history(key_a, limit=50, year=old_year)
        check(
            "year filter returns only that year",
            all(str(r["start_date"]).startswith(str(old_year)) for r in (by_year.get("requests") or [])),
            str([r["start_date"] for r in (by_year.get("requests") or [])][:5]),
        )

        # Isolation
        peer = history(key_b, limit=20)
        peer_ids = {r["leave_id"] for r in (peer.get("requests") or [])}
        check("employee isolation", set(seen).isdisjoint(peer_ids) and peer_id in peer_ids)

        with legacy.db_connect() as conn:
            with conn.cursor() as cur:
                foreign = legacy._employee_leave_history_page(
                    cur, company_code="OTHERCO", employee_key=key_a, limit=20
                )
        check(
            "tenant isolation (wrong company empty)",
            foreign.get("requests") == [] and foreign.get("has_more") is False,
        )

        # Invalid inputs
        try:
            history(key_a, cursor="not-a-cursor")
            check("invalid cursor → 400", False)
        except HTTPException as exc:
            err = (exc.detail or {}).get("error") if isinstance(exc.detail, dict) else None
            check("invalid cursor → 400", exc.status_code == 400 and err == "invalid_cursor")

        try:
            history(key_a, date_from=(today + timedelta(days=5)).isoformat(), date_to=today.isoformat())
            check("invalid range → 400", False)
        except HTTPException as exc:
            err = (exc.detail or {}).get("error") if isinstance(exc.detail, dict) else None
            check("invalid range → 400", exc.status_code == 400 and err == "invalid_range", str(exc.detail))

        try:
            history(key_a, status="not-a-real-status")
            check("invalid status → 400", False)
        except HTTPException as exc:
            err = (exc.detail or {}).get("error") if isinstance(exc.detail, dict) else None
            check("invalid status → 400", exc.status_code == 400 and err == "invalid_status")

        try:
            history(key_a, date_from="not-a-date")
            check("invalid date_from → 400", False)
        except HTTPException as exc:
            err = (exc.detail or {}).get("error") if isinstance(exc.detail, dict) else None
            check("invalid date_from → 400", exc.status_code == 400 and err == "invalid_date_from")

        # `/app/leave` root still capped + shape intact
        root = root_leave(key_a)
        check("root leave still capped ≤50", len(root.get("requests") or []) <= 50)
        check("root leave has requests field", isinstance(root.get("requests"), list))
        check(
            "root leave honesty flags intact",
            root.get("balances_enforced") is False and root.get("observe_only") is True,
        )
        # Cap means history has more than root when >50 seeded
        check(
            "history exceeds root window",
            len(seen) > len(root.get("requests") or []),
            f"hist={len(seen)} root={len(root.get('requests') or [])}",
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
        print(f"FAIL employee leave history contract ({len(FAILS)}) — {', '.join(FAILS)}")
        return 1
    print("PASS employee leave history contract")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
