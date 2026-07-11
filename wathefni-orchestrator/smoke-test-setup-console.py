"""Smoke test: Setup Console V1 (A) — super-admin provisioning console.

The Setup Console lets a Wathefni platform operator onboard a new client company
without hand-editing DB rows or workspace config. It is a thin, fully audited
orchestration over existing tables. This test pins its safety + behaviour:

  - GATE (fail-closed): WATHEFNI_SETUP_CONSOLE_ENABLED off -> 404; wrong/blank
    token -> 401; right operator token but a non-allowlisted phone (or empty
    allowlist) -> 403; right token + allowlisted phone -> platform-admin context
  - PROVISIONING (staging DB), idempotent + audited:
      * create/select company (invalid code rejected; second create is a select)
      * enable modules (unknown rejected; disabling drops a module; reflected by
        company_has_module / configured_company_modules)
      * set timezone
      * seed first Owner (role=owner, invite token issued, idempotent)
      * link Owner WhatsApp (requires an existing Owner -> 422 otherwise)
      * readiness flips to ready only once company+modules+owner+timezone are set
  - BOUNDARIES: mutating a non-existent company -> 404
  - AUDIT: every mutation writes a setup_* action_results row scoped to the company

Run (staging has psycopg2): WATHEFNI_DELIVERY_MODE=dry_run python3 smoke-test-setup-console.py

NEVER point this at production: it creates and deletes throwaway companies.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

PASS = 0
FAIL = 0
TEST_CO = "SETUPCONSOLETEST"
TEST_CO2 = "SETUPCONSOLETEST2"
OPERATOR_TOKEN = "smoke-setup-operator-token"
ADMIN_PHONE = "96599338566"
OTHER_PHONE = "96500000000"


def check(label: str, condition: bool) -> None:
    global PASS, FAIL
    if condition:
        PASS += 1
        print(f"      PASS  {label}")
    else:
        FAIL += 1
        print(f"      FAIL  {label}")


def main() -> int:
    print("    setup console V1 — gate + provisioning + readiness + audit")
    orchestrator_dir = Path(__file__).resolve().parent
    sys.path.insert(0, str(orchestrator_dir))
    try:
        import app
    except ModuleNotFoundError as exc:
        if exc.name == "psycopg2":
            print("SKIP: psycopg2 not available locally; full run happens on staging.")
            return 0
        raise

    def cleanup() -> None:
        with app.db_connect() as conn:
            with conn.cursor() as cur:
                for company in (TEST_CO, TEST_CO2):
                    cur.execute("DELETE FROM dashboard_whatsapp_identities WHERE company_code=%s", (company,))
                    cur.execute("DELETE FROM dashboard_user_invites WHERE company_code=%s", (company,))
                    cur.execute("DELETE FROM dashboard_users WHERE company_code=%s", (company,))
                    cur.execute("DELETE FROM company_modules WHERE company_code=%s", (company,))
                    cur.execute("DELETE FROM company_settings WHERE company_code=%s", (company,))
                    cur.execute("DELETE FROM action_results WHERE company_code=%s", (company,))
                    cur.execute("DELETE FROM companies WHERE company_code=%s", (company,))
            conn.commit()

    saved_env = {k: os.environ.get(k) for k in ("WATHEFNI_SETUP_CONSOLE_ENABLED", "WATHEFNI_PLATFORM_ADMINS", "WATHEFNI_DASHBOARD_TOKEN")}

    def set_env(enabled: str | None, admins: str | None, token: str | None) -> None:
        for key, value in (("WATHEFNI_SETUP_CONSOLE_ENABLED", enabled), ("WATHEFNI_PLATFORM_ADMINS", admins), ("WATHEFNI_DASHBOARD_TOKEN", token)):
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value

    def gate(token: str | None, phone: str | None):
        return app.superadmin_context(authorization=f"Bearer {token}" if token else None, x_hr_phone=phone)

    try:
        # --- 1) gate: fail-closed ------------------------------------------
        set_env("off", ADMIN_PHONE, OPERATOR_TOKEN)
        try:
            gate(OPERATOR_TOKEN, ADMIN_PHONE); raise AssertionError("flag-off should 404")
        except app.HTTPException as e:
            check("flag off -> 404 (feature hidden)", e.status_code == 404)

        set_env("true", ADMIN_PHONE, OPERATOR_TOKEN)
        try:
            gate("wrong-token", ADMIN_PHONE); raise AssertionError("wrong token should 401")
        except app.HTTPException as e:
            check("wrong operator token -> 401", e.status_code == 401)

        try:
            gate(OPERATOR_TOKEN, OTHER_PHONE); raise AssertionError("non-allowlisted phone should 403")
        except app.HTTPException as e:
            check("non-allowlisted phone -> 403", e.status_code == 403)

        set_env("true", "", OPERATOR_TOKEN)
        try:
            gate(OPERATOR_TOKEN, ADMIN_PHONE); raise AssertionError("empty allowlist should 403")
        except app.HTTPException as e:
            check("empty platform-admin allowlist -> 403 (fail closed)", e.status_code == 403)

        set_env("true", ADMIN_PHONE, OPERATOR_TOKEN)
        ctx = gate(OPERATOR_TOKEN, ADMIN_PHONE)
        check("allowlisted operator -> platform-admin context", ctx.get("is_platform_admin") is True and ctx.get("actor_role") == "platform_admin")

        # --- 2) provisioning (staging DB) ----------------------------------
        cleanup()

        # invalid company code
        try:
            app.setup_console_create_company(app.SetupCompanyCreateRequest(company_code="bad code!"), ctx); raise AssertionError("invalid code should 422")
        except app.HTTPException as e:
            check("invalid company code -> 422", e.status_code == 422)

        created = app.setup_console_create_company(app.SetupCompanyCreateRequest(company_code=TEST_CO, name="Setup Console Test"), ctx)
        check("create company returns created=True", created.get("created") is True)
        check("new company exists but is not ready yet", created["readiness"]["exists"] is True and created["readiness"]["ready"] is False)

        again = app.setup_console_create_company(app.SetupCompanyCreateRequest(company_code=TEST_CO), ctx)
        check("second create is idempotent (created=False)", again.get("created") is False)

        # modules: unknown rejected
        try:
            app.setup_console_set_modules(TEST_CO, app.SetupModulesRequest(modules=["pre_hiring", "totally_made_up"]), ctx); raise AssertionError("unknown module should 422")
        except app.HTTPException as e:
            check("unknown module -> 422", e.status_code == 422)

        detail = app.setup_console_company_detail(TEST_CO, ctx)
        available_keys = {item["key"] for item in detail.get("available_modules", [])}
        check("employee_app is a first-class Setup Console module", "employee_app" in available_keys)

        mod = app.setup_console_set_modules(TEST_CO, app.SetupModulesRequest(modules=["pre_hiring", "Payroll", "employee_app"]), ctx)
        check("modules normalised + enabled", mod.get("modules") == ["employee_app", "payroll", "pre_hiring"])
        check(
            "company_has_module reflects the enable",
            app.company_has_module(TEST_CO, "payroll")
            and app.company_has_module(TEST_CO, "pre_hiring")
            and app.company_has_module(TEST_CO, "employee_app"),
        )
        check("readiness modules step done", any(s["key"] == "modules" and s["done"] for s in mod["readiness"]["steps"]))

        mod2 = app.setup_console_set_modules(TEST_CO, app.SetupModulesRequest(modules=["pre_hiring"]), ctx)
        check(
            "disabling drops omitted modules (payroll + employee_app off)",
            "payroll" not in app.configured_company_modules(TEST_CO)
            and "employee_app" not in app.configured_company_modules(TEST_CO)
            and "pre_hiring" in app.configured_company_modules(TEST_CO),
        )

        # timezone
        st = app.setup_console_set_settings(TEST_CO, app.SetupSettingsRequest(timezone="Asia/Kuwait"), ctx)
        check("timezone saved", st["readiness"]["timezone"] == "Asia/Kuwait")

        # owner
        owner = app.setup_console_seed_owner(TEST_CO, app.SetupOwnerRequest(email="owner@setupconsoletest.com", name="Test Owner", phone="96599000111"), ctx)
        check("owner seeded with role=owner", (owner.get("user") or {}).get("role") == "owner")
        check("owner invite token issued", bool(owner.get("invite_token")))
        check("readiness owner step done", any(s["key"] == "owner" and s["done"] for s in owner["readiness"]["steps"]))
        owner_again = app.setup_console_seed_owner(TEST_CO, app.SetupOwnerRequest(email="owner@setupconsoletest.com"), ctx)
        check("re-seeding the same owner is safe", (owner_again.get("user") or {}).get("role") == "owner")

        # whatsapp link requires an owner -> on a fresh company it should 422
        app.setup_console_create_company(app.SetupCompanyCreateRequest(company_code=TEST_CO2, name="No Owner Co"), ctx)
        try:
            app.setup_console_link_whatsapp(TEST_CO2, app.SetupWhatsAppLinkRequest(phone="96599000222"), ctx); raise AssertionError("link without owner should 422")
        except app.HTTPException as e:
            check("WhatsApp link without an Owner -> 422", e.status_code == 422)

        wa = app.setup_console_link_whatsapp(TEST_CO, app.SetupWhatsAppLinkRequest(phone="96599000111"), ctx)
        check("WhatsApp link attaches to the Owner", bool(wa.get("user_id")))
        check("readiness now fully ready", wa["readiness"]["ready"] is True)

        # --- 3) boundaries: mutating a non-existent company -> 404 ---------
        for label, fn in (
            ("modules", lambda: app.setup_console_set_modules("NOSUCHCOMPANYXYZ", app.SetupModulesRequest(modules=["pre_hiring"]), ctx)),
            ("settings", lambda: app.setup_console_set_settings("NOSUCHCOMPANYXYZ", app.SetupSettingsRequest(timezone="Asia/Kuwait"), ctx)),
            ("owner", lambda: app.setup_console_seed_owner("NOSUCHCOMPANYXYZ", app.SetupOwnerRequest(email="x@y.com"), ctx)),
        ):
            try:
                fn(); raise AssertionError(f"{label} on missing company should 404")
            except app.HTTPException as e:
                check(f"{label} on a non-existent company -> 404", e.status_code == 404)

        # --- 4) audit: setup_* rows recorded for the company ---------------
        with app.db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT count(*) AS n FROM action_results WHERE company_code=%s AND action_type LIKE 'setup_%%'", (TEST_CO,))
                audit_rows = int((cur.fetchone() or {}).get("n") or 0)
        check("setup actions are audited (>=5 rows)", audit_rows >= 5)
    finally:
        try:
            cleanup()
        except Exception:
            print("    (warning: cleanup failed)")
        for key, value in saved_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value

    print(f"\n    {PASS} passed, {FAIL} failed")
    if FAIL:
        print("    SETUP CONSOLE: FAILURES")
        return 1
    print("    SETUP CONSOLE: ALL CHECKS PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
