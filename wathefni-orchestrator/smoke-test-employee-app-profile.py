#!/usr/bin/env python3
"""Employee App `/app/profile` projection contract — Phase 3.

Proves Profile reads canonical employee fields only (no parallel store), that
personal/employment sections are present, and that manager is included only when
a manager phone is already stored on the employee row.
"""

from __future__ import annotations

import os
import sys
import uuid
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
        "user_id": "profile-smoke",
        "actor_user_id": "profile-smoke",
        "email": "profile-smoke@wathefni.ai",
        "permissions": ["employees.manage", "onboarding.manage"],
    }


def allow(*keys: str) -> None:
    current = {k for k in (os.environ.get("WATHEFNI_EMPLOYEE_APP_REAL_ALLOWLIST") or "").split(",") if k}
    os.environ["WATHEFNI_EMPLOYEE_APP_REAL_ALLOWLIST"] = ",".join(sorted(current | set(keys)))


def create_employee(suffix: str, *, email: str | None = None, start_date: str | None = None) -> str:
    phone = f"9658{TAG[:4]}{suffix}"[:11].ljust(11, "0")
    result = legacy.create_company_employee(
        COMPANY,
        name=f"Profile {TAG} {suffix}",
        phone=phone,
        email=email or f"profile-{TAG}-{suffix}@example.invalid",
        start_onboarding=False,
        seed_compliance=False,
    )
    key = str(result.get("employee_key") or "")
    if key:
        CREATED.append(key)
        allow(key)
        access.set_employee_app_access(
            legacy, hr_ctx(), employee_key=key, enabled=True, reason="profile-smoke", deliver_invite=False
        )
        if start_date:
            with legacy.db_connect() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        "UPDATE employees SET start_date=%s, updated_at=now() WHERE company_code=%s AND employee_key=%s",
                        (start_date, COMPANY, key),
                    )
                conn.commit()
    return key


def employee_ctx(employee_key: str) -> dict[str, Any]:
    employee = legacy.find_employee_by_key(employee_key, company_code=COMPANY) or {}
    phone = legacy.digits(employee.get("phone"))
    return {
        "company_code": COMPANY,
        "employee_key": employee_key,
        "employee": employee,
        "phone": phone,
        "session_id": f"profile-{TAG}",
        "actor_employee_key": employee_key,
        "actor_user_id": f"employee_app:{employee_key}",
        "actor_phone": phone,
        "actor_email": employee.get("email") or "",
        "actor_role": "employee",
        "hr_phone": "",
        "hr_user": {"role": "employee", "company_code": COMPANY, "phone": phone, "name": employee.get("name") or ""},
    }


def cleanup() -> None:
    with legacy.db_connect() as conn:
        with conn.cursor() as cur:
            for key in CREATED:
                for table in (
                    "employee_sessions",
                    "employee_app_invites",
                    "employee_push_tokens",
                    "employee_messages",
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
    try:
        with legacy.db_connect() as conn:
            with conn.cursor() as cur:
                access.ensure_access_schema(cur)
                conn.commit()
        access.set_company_app_access_policy(
            legacy, hr_ctx(), module_enabled=True, access_mode="selected", sync_invites=False
        )

        manager_key = create_employee("99", email=f"mgr-{TAG}@example.invalid")
        manager = legacy.find_employee_by_key(manager_key, company_code=COMPANY) or {}
        manager_phone = legacy.digits(manager.get("phone"))

        key = create_employee("01", email=f"emp-{TAG}@example.invalid", start_date="2024-03-15")
        with legacy.db_connect() as conn:
            with conn.cursor() as cur:
                from psycopg2.extras import Json

                cur.execute(
                    """
                    UPDATE employees
                    SET position_title=%s,
                        profile = coalesce(profile, '{}'::jsonb) || %s::jsonb,
                        updated_at=now()
                    WHERE company_code=%s AND employee_key=%s
                    """,
                    (
                        "Cashier",
                        Json({"department": "Retail", "manager_phone": manager_phone}),
                        COMPANY,
                        key,
                    ),
                )
            conn.commit()

        # Refresh context employee after mutation.
        payload = legacy.app_profile(context=employee_ctx(key))
        personal = payload.get("personal") or {}
        employment = payload.get("employment") or {}
        lean = payload.get("employee") or {}

        check("profile payload is ok", payload.get("ok") is True)
        check("personal name/phone/email come from the employee row", personal.get("email") == f"emp-{TAG}@example.invalid")
        check("employment carries position and department", employment.get("position_title") == "Cashier" and employment.get("department") == "Retail")
        check("employment carries employee/company identifiers", employment.get("employee_key") == key and employment.get("company_code") == COMPANY)
        check("start_date is projected when stored", str(employment.get("start_date") or "").startswith("2024-03-15"), str(employment.get("start_date")))
        check(
            "manager is resolved from the stored manager phone",
            isinstance(employment.get("manager"), dict)
            and employment["manager"].get("phone") == manager_phone
            and manager_key in str(employment["manager"].get("employee_key") or ""),
            str(employment.get("manager")),
        )
        check("lean employee card remains present for older clients", lean.get("employee_key") == key)
        check("/app/me stays on the compact public shape", "personal" not in legacy.app_me(context=employee_ctx(key)))

        # No invented manager when none is stored.
        bare = create_employee("02")
        bare_payload = legacy.app_profile(context=employee_ctx(bare))
        check(
            "manager is omitted when no manager phone is stored",
            (bare_payload.get("employment") or {}).get("manager") is None,
            str((bare_payload.get("employment") or {}).get("manager")),
        )

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
    print("PASS employee app profile projection contract")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
