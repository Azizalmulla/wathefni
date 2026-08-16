#!/usr/bin/env python3
"""Employee App runtime access enforcement (fail-closed on app_access_enabled).

Eligibility architecture, storage, modes and invite semantics are frozen. This
smoke proves only the runtime repair: an authenticated session must stop working
the moment `employees.app_access_enabled` is false, on every path that can serve
or renew access.

Proves:
- active token + flag true  → /app context resolves
- active token + flag false → 401 app_access_revoked and the session is revoked
- the follow-up request keeps the same definitive reason (no ambiguous 401)
- refresh with a live refresh token + flag false → no rotation, session revoked
- activation redemption with a valid pending invite + flag false → generic 401
- HR disable whose session revoke raises still blocks access and reports it
- employment-inactive keeps its existing 403 account_inactive behaviour
- the deploy reconcile only enables employees holding a live session, and is idempotent

Does not touch Aziz/Talal sessions. The reconcile check runs the real deploy function,
which is company-wide by design: it can only grant access to an employee who already
holds a live session, and the second pass asserts the fleet-wide invariant is clean.
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
# A release gate must never execute deployment DDL: the schema apply path takes broad
# locks and deadlocked against the live service. Migrations belong to deploy.
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


def ctx() -> dict[str, Any]:
    return {
        "company_code": COMPANY,
        "user_id": "runtime-access-smoke",
        "actor_user_id": "runtime-access-smoke",
        "email": "runtime-access-smoke@wathefni.ai",
        "permissions": ["employees.manage", "onboarding.manage"],
    }


def allow(*keys: str) -> None:
    """Controlled rollout allowlist is read per call, so scope it to our fixtures."""
    current = {k for k in (os.environ.get("WATHEFNI_EMPLOYEE_APP_REAL_ALLOWLIST") or "").split(",") if k}
    os.environ["WATHEFNI_EMPLOYEE_APP_REAL_ALLOWLIST"] = ",".join(sorted(current | set(keys)))


def create_employee(suffix: str) -> str:
    phone = f"9657{TAG[:4]}{suffix}"[:11].ljust(11, "0")
    result = legacy.create_company_employee(
        COMPANY,
        name=f"Runtime Access {TAG} {suffix}",
        phone=phone,
        email=f"runtime-access-{TAG}-{suffix}@example.invalid",
        start_onboarding=False,
        seed_compliance=False,
    )
    key = str(result.get("employee_key") or "")
    if key:
        CREATED.append(key)
        allow(key)
    return key


def mint_session(employee_key: str) -> dict[str, Any]:
    with legacy.db_connect() as conn:
        with conn.cursor() as cur:
            session = legacy._create_employee_session_with_cursor(
                cur, COMPANY, employee_key, "96500000000", platform="ios"
            )
        conn.commit()
    return session


def set_flag(employee_key: str, enabled: bool) -> None:
    """Write the raw flag without the HR disable path (simulates a failed revoke)."""
    with legacy.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE employees SET app_access_enabled=%s, updated_at=now() WHERE company_code=%s AND employee_key=%s",
                (bool(enabled), COMPANY, employee_key),
            )
            conn.commit()


def session_row(employee_key: str) -> dict[str, Any]:
    with legacy.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT status, revoked_reason FROM employee_sessions
                WHERE company_code=%s AND employee_key=%s
                ORDER BY created_at DESC LIMIT 1
                """,
                (COMPANY, employee_key),
            )
            row = cur.fetchone()
            conn.commit()
    return dict(row or {})


def call_context(token: str) -> tuple[int | None, str]:
    """Return (status_code, error_code) for an /app request with this token."""
    try:
        legacy.employee_app_context(authorization=f"Bearer {token}")
    except legacy.HTTPException as exc:
        detail = exc.detail if isinstance(exc.detail, dict) else {}
        return exc.status_code, str(detail.get("error") or "")
    return None, "ok"


def cleanup() -> None:
    with legacy.db_connect() as conn:
        with conn.cursor() as cur:
            for key in CREATED:
                cur.execute(
                    "DELETE FROM employee_app_invites WHERE company_code=%s AND employee_key=%s",
                    (COMPANY, key),
                )
                cur.execute(
                    "DELETE FROM employee_sessions WHERE company_code=%s AND employee_key=%s",
                    (COMPANY, key),
                )
                cur.execute(
                    "DELETE FROM employee_push_tokens WHERE company_code=%s AND employee_key=%s",
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
            legacy, ctx(), module_enabled=True, access_mode="selected", sync_invites=False
        )

        # --- 1) Enabled employee with an active session is served
        key = create_employee("01")
        access.set_employee_app_access(
            legacy, ctx(), employee_key=key, enabled=True, reason="runtime-smoke", deliver_invite=False
        )
        session = mint_session(key)
        status, code = call_context(session["token"])
        check("enabled employee resolves /app context", status is None, f"{status}:{code}")

        # --- 2) Flag cleared behind an active session must fail closed
        set_flag(key, False)
        status, code = call_context(session["token"])
        check(
            "disabled flag blocks the live access token",
            status == 401 and code == "app_access_revoked",
            f"{status}:{code}",
        )
        row = session_row(key)
        check(
            "blocked request revokes the session",
            row.get("status") == "revoked" and row.get("revoked_reason") == "app_access_disabled",
            f"{row.get('status')}:{row.get('revoked_reason')}",
        )

        # --- 3) Follow-up request keeps the definitive reason, never an ambiguous 401
        status, code = call_context(session["token"])
        check(
            "revoked-for-access session keeps app_access_revoked",
            status == 401 and code == "app_access_revoked",
            f"{status}:{code}",
        )

        # --- 4) Refresh must not renew access after the flag is cleared
        key2 = create_employee("02")
        access.set_employee_app_access(
            legacy, ctx(), employee_key=key2, enabled=True, reason="runtime-smoke", deliver_invite=False
        )
        session2 = mint_session(key2)
        rotated_ok = legacy.rotate_employee_session(session2["refresh_token"])
        check("refresh works while enabled", bool(rotated_ok and rotated_ok.get("token")))
        set_flag(key2, False)
        rotated_blocked = legacy.rotate_employee_session((rotated_ok or {}).get("refresh_token"))
        check("refresh refuses to rotate after disable", rotated_blocked is None)
        row2 = session_row(key2)
        check(
            "blocked refresh revokes the session",
            row2.get("status") == "revoked" and row2.get("revoked_reason") == "app_access_disabled",
            f"{row2.get('status')}:{row2.get('revoked_reason')}",
        )

        # --- 5) Activation redemption re-checks eligibility
        key3 = create_employee("03")
        access.set_employee_app_access(
            legacy, ctx(), employee_key=key3, enabled=True, reason="runtime-smoke", deliver_invite=False
        )
        emp3 = legacy.find_employee_by_key(key3, company_code=COMPANY) or {}
        phone3 = legacy.digits(emp3.get("phone"))
        _invite3, invite_code = legacy.create_employee_app_invite(COMPANY, emp3)
        set_flag(key3, False)
        activate_status: int | None = None
        activate_code = ""
        try:
            legacy.app_auth_activate(
                legacy.EmployeeAppActivateRequest(phone=phone3, code=invite_code, platform="ios")
            )
        except legacy.HTTPException as exc:
            detail = exc.detail if isinstance(exc.detail, dict) else {}
            activate_status = exc.status_code
            activate_code = str(detail.get("error") or "")
        check(
            "activation with a valid code is refused after disable",
            activate_status == 401 and activate_code == "app_activation_failed",
            f"{activate_status}:{activate_code}",
        )
        check("refused activation leaves the invite unredeemed", not session_row(key3))

        # --- 6) HR disable keeps access blocked even when session revoke fails
        key4 = create_employee("04")
        access.set_employee_app_access(
            legacy, ctx(), employee_key=key4, enabled=True, reason="runtime-smoke", deliver_invite=False
        )
        session4 = mint_session(key4)
        real_revoke = legacy.revoke_employee_app_access

        def exploding_revoke(*_args: Any, **_kwargs: Any) -> int:
            raise RuntimeError("forced revoke failure")

        legacy.revoke_employee_app_access = exploding_revoke  # type: ignore[assignment]
        try:
            disabled = access.set_employee_app_access(
                legacy, ctx(), employee_key=key4, enabled=False, reason="forced-revoke-failure"
            )
        finally:
            legacy.revoke_employee_app_access = real_revoke  # type: ignore[assignment]
        revoke_meta = disabled.get("revoke") or {}
        check("forced revoke failure is reported, not swallowed", revoke_meta.get("revoke_clean") is False, str(revoke_meta))
        check("forced revoke failure records the error", bool(revoke_meta.get("revoke_error")), str(revoke_meta.get("revoke_error")))
        check("disable still clears eligibility", (disabled.get("state") or {}).get("eligible") is False)
        status, code = call_context(session4["token"])
        check(
            "access blocked despite the failed revoke",
            status == 401 and code == "app_access_revoked",
            f"{status}:{code}",
        )

        # --- 7) Employment-inactive behaviour is unchanged
        key5 = create_employee("05")
        access.set_employee_app_access(
            legacy, ctx(), employee_key=key5, enabled=True, reason="runtime-smoke", deliver_invite=False
        )
        session5 = mint_session(key5)
        with legacy.db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE employees SET employment_status='left', updated_at=now() WHERE company_code=%s AND employee_key=%s",
                    (COMPANY, key5),
                )
                conn.commit()
        status, code = call_context(session5["token"])
        check(
            "employment-inactive still returns account_inactive",
            status == 403 and code == "account_inactive",
            f"{status}:{code}",
        )

        # --- 8) Deploy reconcile only rescues employees holding a live session
        key6 = create_employee("06")  # pre-flag employee holding a live session
        key7 = create_employee("07")  # never granted, no session
        mint_session(key6)
        set_flag(key6, False)
        set_flag(key7, False)
        with legacy.db_connect() as conn:
            with conn.cursor() as cur:
                reconciled = {
                    str(row.get("employee_key") or "")
                    for row in access.reconcile_access_flag_for_live_sessions(cur)
                }
                conn.commit()
        check("reconcile enables the live pre-flag session", key6 in reconciled, str(sorted(reconciled)))
        check("reconcile leaves never-granted employees off", key7 not in reconciled, str(sorted(reconciled)))
        with legacy.db_connect() as conn:
            with conn.cursor() as cur:
                second_pass = access.reconcile_access_flag_for_live_sessions(cur)
                conn.commit()
        check("reconcile is idempotent", second_pass == [], str(second_pass))

        # --- 9) Canonical helper shape
        ok_true, reason_true = legacy._employee_app_runtime_access(
            {"employment_status": "active", "app_access_enabled": True}
        )
        ok_flag, reason_flag = legacy._employee_app_runtime_access(
            {"employment_status": "active", "app_access_enabled": False}
        )
        ok_missing, _ = legacy._employee_app_runtime_access({"employment_status": "active"})
        ok_left, reason_left = legacy._employee_app_runtime_access(
            {"employment_status": "left", "app_access_enabled": True}
        )
        check("helper allows enabled active employee", ok_true is True and reason_true == "employee_enabled")
        check("helper denies cleared flag", ok_flag is False and reason_flag == "employee_access_disabled")
        check("helper fails closed on a missing flag", ok_missing is False)
        check(
            "helper reports employment before access",
            ok_left is False and reason_left == "employee_not_employment_eligible",
        )

    finally:
        cleanup()
        try:
            access.set_company_app_access_policy(
                legacy,
                ctx(),
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
    print("PASS employee app runtime access enforcement")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
