"""Smoke test: Phase 1 security lockdown.

Pins two guarantees added in the security-lockdown pass:

  1. require_internal_access() — the fail-closed gate now protecting the
     /orchestrator/audit/*, /orchestrator/debug/*, and worker-trigger routes.
     It must deny when the secret is unset, deny on mismatch, and accept the
     configured secret via either Authorization: Bearer or X-Internal-Token.

  2. POST /dashboard/team/whatsapp-link anti-hijack guard — a WhatsApp identity
     that is actively linked to one account may not be reassigned to a different
     account in the same company (409); the owning account may still re-link it,
     and a fresh number links normally.

Run (staging has psycopg2): WATHEFNI_DELIVERY_MODE=dry_run python3 smoke-test-internal-auth.py
"""

from __future__ import annotations

import os
import sys
import uuid
from pathlib import Path

PASS = 0
FAIL = 0
TEST_CO = "INTERNALAUTHTEST"
INTERNAL_TOKEN = "smoke-internal-token"
PHONE = "96599112233"
FRESH_PHONE = "96599445566"
# dashboard_users.user_id is a UUID column — use real UUIDs, not labels.
USER_A = str(uuid.uuid4())
USER_B = str(uuid.uuid4())


def check(label: str, condition: bool) -> None:
    global PASS, FAIL
    if condition:
        PASS += 1
        print(f"      PASS  {label}")
    else:
        FAIL += 1
        print(f"      FAIL  {label}")


def main() -> int:
    print("    internal-auth lockdown — require_internal_access + whatsapp-link anti-hijack")
    orchestrator_dir = Path(__file__).resolve().parent
    sys.path.insert(0, str(orchestrator_dir))
    try:
        import app
    except ModuleNotFoundError as exc:
        if exc.name == "psycopg2":
            # The require_internal_access checks below need no DB; but app import
            # itself pulls psycopg2. Full run happens on staging.
            print("SKIP: psycopg2 not available locally; full run happens on staging.")
            return 0
        raise

    saved_token = os.environ.get("WATHEFNI_INTERNAL_TOKEN")

    # --- 1) require_internal_access: fail-closed ---------------------------
    os.environ.pop("WATHEFNI_INTERNAL_TOKEN", None)
    try:
        app.require_internal_access(authorization="Bearer anything", x_internal_token=None)
        raise AssertionError("unset secret must deny")
    except app.HTTPException as e:
        check("secret unset -> 401 (fail-closed, never open)", e.status_code == 401)

    os.environ["WATHEFNI_INTERNAL_TOKEN"] = INTERNAL_TOKEN
    try:
        app.require_internal_access(authorization=None, x_internal_token=None)
        raise AssertionError("missing token must deny")
    except app.HTTPException as e:
        check("no token provided -> 401", e.status_code == 401)

    try:
        app.require_internal_access(authorization="Bearer wrong-token", x_internal_token=None)
        raise AssertionError("wrong token must deny")
    except app.HTTPException as e:
        check("wrong token -> 401", e.status_code == 401)

    ok_bearer = app.require_internal_access(authorization=f"Bearer {INTERNAL_TOKEN}", x_internal_token=None)
    check("correct token via Authorization Bearer -> allowed", ok_bearer.get("is_internal") is True)

    ok_header = app.require_internal_access(authorization=None, x_internal_token=INTERNAL_TOKEN)
    check("correct token via X-Internal-Token -> allowed", ok_header.get("is_internal") is True)

    # --- 2) whatsapp-link anti-hijack (staging DB) -------------------------
    real_audit = app.record_admin_audit
    app.record_admin_audit = lambda *a, **k: None  # avoid coupling to audit internals

    def cleanup() -> None:
        with app.db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute("DELETE FROM dashboard_whatsapp_identities WHERE company_code=%s", (TEST_CO,))
                cur.execute("DELETE FROM dashboard_users WHERE company_code=%s", (TEST_CO,))
                cur.execute("DELETE FROM companies WHERE company_code=%s", (TEST_CO,))
            conn.commit()

    def ctx(user_id: str) -> dict:
        return {
            "company_code": TEST_CO,
            "actor_user_id": user_id,
            "permission_authority": "backend_current",
            "permission_subject_user_id": user_id,
            "permission_subject_company": TEST_CO,
            "hr_phone": PHONE,
            "actor_role": "owner",
            "permissions": sorted(app.hr_role_permissions("owner")),
        }

    def link(user_id: str, phone: str):
        return app.dashboard_team_link_whatsapp(app.DashboardWhatsAppLinkRequest(phone=phone), context=ctx(user_id))

    cleanup()
    try:
        with app.db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "INSERT INTO companies (company_code, name, metadata, raw_json, created_at, updated_at) "
                    "VALUES (%s,%s,%s,%s,now(),now()) ON CONFLICT (company_code) DO NOTHING",
                    (TEST_CO, "Internal Auth Test", app.Json({}), app.Json({})),
                )
                for uid, email in ((USER_A, "a@internalauth.test"), (USER_B, "b@internalauth.test")):
                    cur.execute(
                        "INSERT INTO dashboard_users (user_id, company_code, email, role, status, created_at, updated_at) "
                        "VALUES (%s,%s,%s,'owner','active',now(),now()) ON CONFLICT (user_id) DO NOTHING",
                        (uid, TEST_CO, email),
                    )
            conn.commit()

        res_a = link(USER_A, PHONE)
        check("owner A links a fresh number -> ok", res_a.get("ok") is True)

        res_a_again = link(USER_A, PHONE)
        check("owner A re-links their own number -> ok (idempotent)", res_a_again.get("ok") is True)

        try:
            link(USER_B, PHONE)
            raise AssertionError("hijack must be blocked")
        except app.HTTPException as e:
            check("user B cannot steal A's active linked number -> 409", e.status_code == 409)

        res_b_fresh = link(USER_B, FRESH_PHONE)
        check("user B links a different fresh number -> ok", res_b_fresh.get("ok") is True)

        with app.db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT user_id FROM dashboard_whatsapp_identities WHERE company_code=%s AND phone=%s",
                    (TEST_CO, app.digits(PHONE)),
                )
                row = cur.fetchone()
        check("A's number is still owned by A after the blocked hijack", bool(row) and row.get("user_id") == USER_A)
    finally:
        cleanup()
        app.record_admin_audit = real_audit
        if saved_token is None:
            os.environ.pop("WATHEFNI_INTERNAL_TOKEN", None)
        else:
            os.environ["WATHEFNI_INTERNAL_TOKEN"] = saved_token

    print(f"\n    {PASS} passed, {FAIL} failed\n")
    if FAIL:
        print("    INTERNAL-AUTH LOCKDOWN: FAILURES")
        return 1
    print("    INTERNAL-AUTH LOCKDOWN: ALL CHECKS PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
