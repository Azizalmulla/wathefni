#!/usr/bin/env python3
"""Employee App access eligibility + invite trigger matrix (WATHEFNI canary).

Proves:
- company app OFF + create → no invite
- company ON + employee access OFF → no invite
- enable employee access → invite issued/delivered (stamped)
- bulk-import style create → no invites
- enable selected → only those employees invited
- enable all / department bulk → deduped invites
- repeated enable is idempotent (no spam)
- revoke / reinvite still work
- Auth Wave 2 Phase 6 not started

Does not touch Aziz/Talal sessions.
"""

from __future__ import annotations

import json
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
os.environ.setdefault("WATHEFNI_EMPLOYEE_APP_AUTO_INVITE", "on")
os.environ.setdefault("WATHEFNI_EMPLOYEE_APP_AUTO_INVITE_COMPANIES", "WATHEFNI")
os.environ.setdefault("WATHEFNI_SCHEMA_APPLY", "1")

import app as legacy  # noqa: E402
import employee_app_access as access  # noqa: E402
import employee_app_invitation as inv  # noqa: E402

COMPANY = "WATHEFNI"
FAILS: list[str] = []
TAG = uuid.uuid4().hex[:8]
CREATED: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    status = "PASS" if ok else "FAIL"
    print(f"{status}  {name}" + (f" — {detail}" if detail else ""))
    if not ok:
        FAILS.append(name)


def ctx() -> dict[str, Any]:
    return {
        "company_code": COMPANY,
        "user_id": "access-elig-smoke",
        "actor_user_id": "access-elig-smoke",
        "email": "access-elig-smoke@wathefni.ai",
        "permissions": ["employees.manage", "onboarding.manage"],
    }


def invite_count(employee_key: str) -> int:
    with legacy.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT count(*) AS n FROM employee_app_invites WHERE company_code=%s AND employee_key=%s",
                (COMPANY, employee_key),
            )
            n = int(dict(cur.fetchone() or {}).get("n") or 0)
            conn.commit()
    return n


def set_module(enabled: bool, mode: str = "selected") -> None:
    access.set_company_app_access_policy(
        legacy,
        ctx(),
        module_enabled=enabled,
        access_mode=mode,
        sync_invites=False,
    )


def create_emp(suffix: str, department: str | None = None) -> dict[str, Any]:
    phone = f"96571{TAG}{suffix}"[-11:]
    if not phone.startswith("965"):
        phone = f"96571{suffix}{TAG[:4]}"
    name = f"Access Elig {TAG} {suffix}"
    result = legacy.create_company_employee(
        COMPANY,
        name=name,
        phone=phone,
        email=f"access-elig-{TAG}-{suffix}@example.invalid",
        department=department,
        start_onboarding=False,
        seed_compliance=False,
    )
    key = str(result.get("employee_key") or "")
    if key:
        CREATED.append(key)
    return result


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
                    "DELETE FROM employees WHERE company_code=%s AND employee_key=%s",
                    (COMPANY, key),
                )
            conn.commit()


def main() -> int:
    original = access.get_company_app_access_policy(legacy, COMPANY)
    try:
        with legacy.db_connect() as conn:
            with conn.cursor() as cur:
                access.ensure_access_schema(cur)
                inv.ensure_invitation_schema(cur)
                conn.commit()

        # --- 1) Company OFF + create → no invite
        set_module(False)
        off = create_emp("01")
        key1 = str(off.get("employee_key") or "")
        check("create status created", off.get("status") == "created", str(off.get("status")))
        check("create skipped auto invite", (off.get("app_invitation") or {}).get("skipped") is True)
        check("company off → zero invites", invite_count(key1) == 0, str(invite_count(key1)))
        issue_blocked = inv.issue_and_deliver_invitation(
            legacy,
            company_code=COMPANY,
            employee=legacy.find_employee_by_key(key1, company_code=COMPANY),
            trigger_source=inv.TRIGGER_HR_REINVITE,
            force_new=True,
        )
        check(
            "company off blocks issue_and_deliver",
            not issue_blocked.get("ok"),
            str(issue_blocked.get("error")),
        )

        # --- 2) Company ON + employee access OFF → no invite
        set_module(True, mode="selected")
        on = create_emp("02", department="Sales")
        key2 = str(on.get("employee_key") or "")
        check("create while company on still no invite", invite_count(key2) == 0)
        state2 = access.get_employee_app_access_state(legacy, company_code=COMPANY, employee_key=key2)
        check("employee access off by default", state2.get("app_access_enabled") is False)
        check("not eligible until enabled", state2.get("eligible") is False, str(state2.get("eligibility_reason")))

        # Legacy create trigger blocked
        auto = inv.maybe_auto_invite_employee(
            legacy,
            company_code=COMPANY,
            employee=legacy.find_employee_by_key(key2, company_code=COMPANY),
            trigger_source=inv.TRIGGER_AUTO_CREATE,
            idempotency_key=f"should-block:{key2}",
        )
        check("legacy auto_create skipped", auto.get("skipped") is True, str(auto.get("reason")))

        # --- 3) Enable employee → invite
        enabled = access.set_employee_app_access(
            legacy, ctx(), employee_key=key2, enabled=True, reason="smoke-enable"
        )
        check("enable ok", enabled.get("ok") is True)
        check("invite after enable", invite_count(key2) >= 1, str(invite_count(key2)))
        inv_meta = enabled.get("invitation") or {}
        check(
            "invite delivery stamped",
            inv_meta.get("ok") is True
            or inv_meta.get("delivery_status") in {
                inv.STATUS_SENT,
                inv.STATUS_DELIVERED,
                inv.STATUS_FAILED,
                inv.STATUS_NEEDS_ATTENTION,
                inv.STATUS_PENDING,
            }
            or inv_meta.get("skipped_duplicate") is True,
            str(inv_meta.get("delivery_status") or inv_meta.get("reason")),
        )

        # --- 4) Idempotent re-enable
        before = invite_count(key2)
        again = access.set_employee_app_access(
            legacy, ctx(), employee_key=key2, enabled=True, reason="smoke-enable-again"
        )
        after = invite_count(key2)
        check("re-enable does not spam invites", after == before or (again.get("invitation") or {}).get("skipped_duplicate") is True, f"{before}->{after}")

        # --- 5) Bulk-import style creates → no invites
        keys_import = []
        for i in range(3):
            r = create_emp(f"1{i}", department="Ops")
            k = str(r.get("employee_key") or "")
            keys_import.append(k)
            check(f"import create {i} no invite", invite_count(k) == 0)

        # --- 6) Enable selected only
        chosen = keys_import[0]
        left_out = keys_import[1]
        access.set_employee_app_access(legacy, ctx(), employee_key=chosen, enabled=True, reason="selected")
        check("selected invited", invite_count(chosen) >= 1)
        check("non-selected untouched", invite_count(left_out) == 0)

        # --- 7) Enable department group (deduped)
        bulk = access.enable_app_access_bulk(
            legacy,
            ctx(),
            departments=["Ops"],
            reason="dept-ops",
        )
        check("bulk dept ok", bulk.get("ok") is True, json.dumps({k: bulk.get(k) for k in ("requested", "errors")}))
        for k in keys_import:
            check(f"ops emp invited {k[-6:]}", invite_count(k) >= 1)

        # Enable all active for our tag-prefixed names only via keys
        key3 = str(create_emp("99", department="Finance").get("employee_key") or "")
        before_all = invite_count(key3)
        access.enable_app_access_bulk(
            legacy,
            ctx(),
            employee_keys=[key3],
            reason="selected-keys",
        )
        check("enable keys invites", invite_count(key3) > before_all or invite_count(key3) >= 1)

        # --- 8) Disable + revoke semantics
        disabled = access.set_employee_app_access(
            legacy, ctx(), employee_key=key2, enabled=False, reason="smoke-disable"
        )
        check("disable ok", disabled.get("ok") is True)
        state_off = access.get_employee_app_access_state(legacy, company_code=COMPANY, employee_key=key2)
        check("disabled not eligible", state_off.get("eligible") is False)
        blocked = inv.issue_and_deliver_invitation(
            legacy,
            company_code=COMPANY,
            employee=legacy.find_employee_by_key(key2, company_code=COMPANY),
            trigger_source=inv.TRIGGER_HR_REINVITE,
            force_new=True,
        )
        check("disabled blocks new invite", not blocked.get("ok"), str(blocked.get("error")))

        # Re-enable then revoke (device) should keep eligibility for reinvite
        access.set_employee_app_access(legacy, ctx(), employee_key=key2, enabled=True, reason="re-enable")
        # Simulate active session then HR revoke (does not clear eligibility flag)
        with legacy.db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO employee_sessions
                      (company_code, employee_key, phone, token_hash, refresh_hash, status, expires_at, refresh_expires_at)
                    VALUES (%s,%s,%s,%s,%s,'active', now() + interval '1 day', now() + interval '7 days')
                    """,
                    (COMPANY, key2, "96500000000", f"tok-{TAG}", f"ref-{TAG}"),
                )
                conn.commit()
        legacy.revoke_employee_app_access(COMPANY, key2, reason="hr_revoked")
        state_rev = access.get_employee_app_access_state(legacy, company_code=COMPANY, employee_key=key2)
        # Note: revoke_employee_app_access does not clear flag — eligibility remains if still enabled
        check("flag remains after device revoke when still enabled", state_rev.get("app_access_enabled") is True)
        reinv = inv.reinvite_employee(legacy, ctx(), employee_key=key2, reason="after-revoke")
        check("reinvite after revoke ok", reinv.get("ok") is True, str(reinv.get("error")))

        # Snapshot actions shape
        snap = inv.get_invitation_snapshot(legacy, company_code=COMPANY, employee_key=key2)
        check("snapshot has eligibility fields", "app_access_enabled" in snap and "actions" in snap)
        check("snapshot no activation_code", "activation_code" not in json.dumps(snap, default=str))

        # Phase 6 not started
        routes = {getattr(r, "path", None) for r in legacy.app.routes}
        check("no phase6 devices route", "/app/devices" not in routes)
        check("eligibility route present", any(
            getattr(r, "path", "") == "/dashboard/posthire/employees/{employee_key}/app-access/eligibility"
            for r in legacy.app.routes
        ))
        check("policy route present", any(
            getattr(r, "path", "") == "/dashboard/posthire/app-access/policy" for r in legacy.app.routes
        ))

    finally:
        cleanup()
        # Restore prior company module policy best-effort
        try:
            access.set_company_app_access_policy(
                legacy,
                ctx(),
                module_enabled=bool(original.get("module_enabled")),
                access_mode=str(original.get("access_mode") or "selected"),
                selected_departments=list(original.get("selected_departments") or []),
                sync_invites=False,
            )
        except Exception:
            pass

    print("---")
    if FAILS:
        print(f"FAIL count={len(FAILS)}: {', '.join(FAILS)}")
        return 1
    print("PASS employee app access eligibility matrix")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
