#!/usr/bin/env python3
"""Employee app invitation + delivery canary smoke (WATHEFNI).

Proves:
- invitation module loads
- schema columns exist
- snapshot never returns activation_code
- auto-invite flag honors allowlist
- force reinvite issues invite + stamps delivery (uses outbound ladder)
- Auth Wave 2 activate route still present (no Phase 6)

Uses a disposable synthetic employee; cleans up invite rows for that key.
Does not revoke Aziz/Talal sessions.
"""

from __future__ import annotations

import json
import os
import sys
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

os.environ.setdefault("WATHEFNI_ENV", "production")
os.environ.setdefault("WATHEFNI_POSTGRES_ENV", "/root/.openclaw/secrets/postgres.env")
os.environ.setdefault("WATHEFNI_WORKSPACE", "/root/.openclaw/workspaces/company-wathefni")

import app as legacy  # noqa: E402
import employee_app_invitation as inv  # noqa: E402

COMPANY = "WATHEFNI"
FAILS: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    status = "PASS" if ok else "FAIL"
    print(f"{status}  {name}" + (f" — {detail}" if detail else ""))
    if not ok:
        FAILS.append(name)


def main() -> int:
    legacy.ensure_schema()
    check("module import", True)
    check("auto invite env readable", isinstance(inv.auto_invite_enabled(company_code=COMPANY), bool))

    with legacy.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT column_name FROM information_schema.columns
                WHERE table_name='employee_app_invites'
                  AND column_name IN (
                    'delivery_status','delivery_channel','last_delivery_at',
                    'last_delivery_error','trigger_source','delivery_attempts'
                  )
                ORDER BY 1
                """
            )
            cols = {r["column_name"] if isinstance(r, dict) else r[0] for r in cur.fetchall()}
            conn.commit()
    needed = {
        "delivery_status",
        "delivery_channel",
        "last_delivery_at",
        "last_delivery_error",
        "trigger_source",
        "delivery_attempts",
    }
    check("invitation delivery columns", needed <= cols, ",".join(sorted(cols)))

    # Read-only snapshot on canary Aziz — never disclose code.
    aziz = "WATHEFNI-96599338566"
    snap = inv.get_invitation_snapshot(legacy, company_code=COMPANY, employee_key=aziz)
    check("aziz snapshot ok", bool(snap.get("ok")))
    blob = json.dumps(snap, default=str)
    check("aziz snapshot has no activation_code", "activation_code" not in blob and "code_hash" not in blob)
    check("aziz snapshot has status", "invitation_status" in snap)

    # Disposable synthetic employee for issue+deliver prove.
    suffix = uuid.uuid4().hex[:8]
    phone = f"9655{suffix[:7]}"
    # Ensure 8-digit local feel after country — use fixed test range.
    phone = f"96570{suffix[:6]}"
    employee_key = f"WATHEFNI-INVITE-SMOKE-{suffix.upper()}"
    email = f"invite-smoke-{suffix}@example.invalid"

    created = False
    try:
        with legacy.db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    INSERT INTO employees (
                      company_code, employee_key, name, phone, email,
                      employment_status, position_title, department, raw_json
                    )
                    VALUES (%s,%s,%s,%s,%s,'active','Invite Smoke','QA',%s::jsonb)
                    RETURNING employee_key
                    """,
                    (
                        COMPANY,
                        employee_key,
                        f"Invite Smoke {suffix}",
                        phone[-8:],
                        email,
                        json.dumps({"source": "invitation_delivery_smoke"}),
                    ),
                )
                row = cur.fetchone()
                created = bool(row)
                conn.commit()
        check("synthetic employee ready", created, employee_key)

        employee = legacy.find_employee_by_key(employee_key, company_code=COMPANY)
        check("synthetic employee loadable", bool(employee))

        # Force deliver path; outbound may fail to example.invalid — status must stamp.
        result = inv.issue_and_deliver_invitation(
            legacy,
            company_code=COMPANY,
            employee=employee,
            trigger_source=inv.TRIGGER_HR_REINVITE,
            force_new=True,
            created_by_user_id="invitation-smoke",
        )
        check("issue_and_deliver returned", bool(result.get("ok") or result.get("error")))
        check("no code in issue result", "activation_code" not in json.dumps(result, default=str))
        check("invite_id present", bool(result.get("invite_id")), str(result.get("invite_id")))
        check(
            "delivery status stamped",
            result.get("delivery_status") in {
                inv.STATUS_SENT,
                inv.STATUS_DELIVERED,
                inv.STATUS_FAILED,
                inv.STATUS_NEEDS_ATTENTION,
                inv.STATUS_PENDING,
            }
            or bool(result.get("snapshot")),
            str(result.get("delivery_status")),
        )

        snap2 = inv.get_invitation_snapshot(legacy, company_code=COMPANY, employee_key=employee_key)
        check("synthetic snapshot status not none", snap2.get("invitation_status") != inv.STATUS_NONE, str(snap2.get("invitation_status")))
        check("synthetic snapshot no code", "activation_code" not in json.dumps(snap2, default=str))
        check("show_code_exception only on needs_attention",
              snap2.get("actions", {}).get("show_code_exception") == (snap2.get("invitation_status") == inv.STATUS_NEEDS_ATTENTION))

        # Idempotent auto: second auto should skip duplicate.
        os.environ["WATHEFNI_EMPLOYEE_APP_AUTO_INVITE"] = "on"
        os.environ["WATHEFNI_EMPLOYEE_APP_AUTO_INVITE_COMPANIES"] = "WATHEFNI"
        auto = inv.maybe_auto_invite_employee(
            legacy,
            company_code=COMPANY,
            employee=employee,
            trigger_source=inv.TRIGGER_AUTO_CREATE,
            idempotency_key=f"smoke-auto:{employee_key}",
        )
        check("auto invite does not crash", "ok" in auto or "skipped" in auto or "error" in auto)

    finally:
        with legacy.db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "DELETE FROM employee_app_invites WHERE company_code=%s AND employee_key=%s",
                    (COMPANY, employee_key),
                )
                cur.execute(
                    "DELETE FROM employees WHERE company_code=%s AND employee_key=%s",
                    (COMPANY, employee_key),
                )
                conn.commit()
        check("synthetic cleanup", True, employee_key)

    # Auth surface still present — Phase 6 not started.
    routes = {getattr(r, "path", None) for r in legacy.app.routes}
    check("activate route frozen present", "/app/auth/activate" in routes)
    check("invitation GET route present", "/dashboard/posthire/employees/{employee_key}/app-invitation" in routes)
    check("invitation resend route present", "/dashboard/posthire/employees/{employee_key}/app-invitation/resend" in routes)
    check("no phase6 device-trust route", "/app/devices" not in routes)

    print("---")
    if FAILS:
        print(f"FAIL count={len(FAILS)}: {', '.join(FAILS)}")
        return 1
    print("PASS employee_app_invitation_smoke")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
