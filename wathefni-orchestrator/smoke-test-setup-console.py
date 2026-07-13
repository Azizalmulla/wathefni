"""Smoke test: Setup Console operator gate and V2 provisioning control center.

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

import json
import os
import sys
import tempfile
from pathlib import Path

PASS = 0
FAIL = 0
TEST_CO = "SETUPCONSOLETEST"
TEST_CO2 = "SETUPCONSOLETEST2"
OPERATOR_TOKEN = "smoke-setup-operator-token"
ADMIN_PHONE = "96599338566"
OTHER_PHONE = "96500000000"
OTHER_OPERATOR_TOKEN = "smoke-second-operator-token"
SHARED_DASHBOARD_TOKEN = "smoke-shared-dashboard-token"


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
                    cur.execute("DELETE FROM company_channel_accounts WHERE company_code=%s", (company,))
                    cur.execute("DELETE FROM dashboard_whatsapp_identities WHERE company_code=%s", (company,))
                    cur.execute("DELETE FROM dashboard_user_sessions WHERE company_code=%s", (company,))
                    cur.execute("DELETE FROM dashboard_user_invites WHERE company_code=%s", (company,))
                    cur.execute("DELETE FROM dashboard_users WHERE company_code=%s", (company,))
                    cur.execute("DELETE FROM company_modules WHERE company_code=%s", (company,))
                    cur.execute("DELETE FROM company_settings WHERE company_code=%s", (company,))
                    cur.execute("DELETE FROM payroll_policies WHERE company_code=%s", (company,))
                    cur.execute("DELETE FROM action_results WHERE company_code=%s", (company,))
                    cur.execute("DELETE FROM companies WHERE company_code=%s", (company,))
            conn.commit()

    saved_env = {k: os.environ.get(k) for k in (
        "WATHEFNI_SETUP_CONSOLE_ENABLED",
        "WATHEFNI_SETUP_CONSOLE_V2",
        "WATHEFNI_COMPANY_CHANNEL_ACCOUNTS",
        "WATHEFNI_EMPLOYEE_APP",
        "WATHEFNI_PLATFORM_ADMINS",
        "WATHEFNI_DASHBOARD_TOKEN",
        "WATHEFNI_SETUP_OPERATOR_CREDENTIALS",
    )}

    def set_env(enabled: str | None, admins: str | None, token: str | None) -> None:
        credentials = json.dumps({
            ADMIN_PHONE: token,
            OTHER_PHONE: OTHER_OPERATOR_TOKEN,
        }) if token else None
        for key, value in (
            ("WATHEFNI_SETUP_CONSOLE_ENABLED", enabled),
            ("WATHEFNI_PLATFORM_ADMINS", admins),
            ("WATHEFNI_DASHBOARD_TOKEN", SHARED_DASHBOARD_TOKEN),
            ("WATHEFNI_SETUP_OPERATOR_CREDENTIALS", credentials),
        ):
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
            gate(SHARED_DASHBOARD_TOKEN, ADMIN_PHONE); raise AssertionError("shared dashboard token should 401")
        except app.HTTPException as e:
            check("ordinary dashboard token cannot access Setup Console", e.status_code == 401)

        try:
            gate(OPERATOR_TOKEN, OTHER_PHONE); raise AssertionError("operator token is bound to its phone")
        except app.HTTPException as e:
            check("operator token cannot spoof another allowlisted identity", e.status_code == 401)

        try:
            gate(OTHER_OPERATOR_TOKEN, OTHER_PHONE); raise AssertionError("non-allowlisted phone should 403")
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
        from fastapi.testclient import TestClient
        client = TestClient(app.app)
        check("Setup Console API rejects public requests", client.get("/dashboard/superadmin/setup/companies").status_code == 401)
        check(
            "operator token without allowlisted identity is rejected",
            client.get(
                "/dashboard/superadmin/setup/companies",
                headers={"Authorization": f"Bearer {OPERATOR_TOKEN}"},
            ).status_code == 401,
        )

        original_dist = app.DASHBOARD_DIST_PATH
        os.environ["WATHEFNI_SETUP_CONSOLE_V2"] = "off"
        legacy_page = app.setup_console_page()
        check("V2 OFF serves the legacy rollback page", b"Setup Console" in legacy_page.body)
        with tempfile.TemporaryDirectory() as temp_dir:
            dist = Path(temp_dir)
            (dist / "setup-console.html").write_text("<div id=\"setup-console-root\">V2</div>")
            app.DASHBOARD_DIST_PATH = dist
            os.environ["WATHEFNI_SETUP_CONSOLE_V2"] = "on"
            v2_page = app.setup_console_page()
            check("V2 ON serves the dedicated React entry", Path(str(v2_page.path)).name == "setup-console.html")
        app.DASHBOARD_DIST_PATH = original_dist

        # --- 2) V2 provisioning (staging DB) -------------------------------
        os.environ["WATHEFNI_SETUP_CONSOLE_V2"] = "on"
        os.environ["WATHEFNI_COMPANY_CHANNEL_ACCOUNTS"] = "off"
        os.environ["WATHEFNI_EMPLOYEE_APP"] = "off"
        cleanup()

        # invalid company code
        try:
            app.setup_console_create_company(app.SetupCompanyCreateRequest(company_code="bad code!"), ctx); raise AssertionError("invalid code should 422")
        except app.HTTPException as e:
            check("invalid company code -> 422", e.status_code == 422)

        created = app.setup_console_create_company(
            app.SetupCompanyCreateRequest(company_code=TEST_CO, name="Setup Console Test", country="KW"),
            ctx,
        )
        check("create company returns created=True", created.get("created") is True)
        check("new company exists but is not ready yet", created["readiness"]["exists"] is True and created["readiness"]["ready"] is False)
        check("GCC profile defaults are durable", (
            created["readiness"].get("country") == "KW"
            and created["readiness"].get("timezone") == "Asia/Kuwait"
            and created["readiness"].get("currency") == "KWD"
        ))

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
        employee_app = next(item for item in detail["available_modules"] if item["key"] == "employee_app")
        check("employee_app is configured/effective through separate gates", (
            employee_app["configured"] is False
            and employee_app["platform_available"] is False
            and employee_app["effective"] is False
        ))
        check("module bundles are exposed to Setup Console", len(detail.get("module_bundles") or []) >= 6)
        check("module guidance includes app surface helpers", "app_surfaces" in (detail.get("module_guidance") or {}))
        assessments_item = next(item for item in detail["available_modules"] if item["key"] == "assessments")
        check("assessments advertises hard dependency on pre_hiring", assessments_item.get("depends_on") == ["pre_hiring"])
        payroll_item = next(item for item in detail["available_modules"] if item["key"] == "payroll")
        check("payroll soft-recommends attendance and leave", set(payroll_item.get("recommended_with") or []) == {"attendance", "leave"})
        check("channel sections separate candidates, employees, and HR", set(detail["channel_policy"]) >= {
            "pre_hiring", "post_hiring", "hr_admin",
        })

        try:
            app.setup_console_set_modules(TEST_CO, app.SetupModulesRequest(modules=["assessments"]), ctx)
            raise AssertionError("assessments without pre_hiring should 422")
        except app.HTTPException as e:
            check("hard dependency missing -> 422", e.status_code == 422 and e.detail.get("error") == "missing_module_dependency")
            check("hard dependency response suggests expanded modules", e.detail.get("suggested_modules") == ["assessments", "pre_hiring"])

        mod = app.setup_console_set_modules(TEST_CO, app.SetupModulesRequest(modules=["pre_hiring", "Payroll", "employee_app"]), ctx)
        check("soft recommendations never block save", mod.get("modules") == ["employee_app", "payroll", "pre_hiring"])
        check("modules normalised + enabled", mod.get("modules") == ["employee_app", "payroll", "pre_hiring"])
        guidance = app.setup_console_module_guidance(TEST_CO, ["employee_app", "payroll", "attendance"])
        check(
            "app surface preview excludes payroll and requires employee_app",
            {item["surface_key"] for item in guidance["app_surfaces"]} == {"inbox", "attendance"},
        )
        check(
            "company_has_module reflects the enable",
            app.company_has_module(TEST_CO, "payroll")
            and app.company_has_module(TEST_CO, "pre_hiring")
            and app.company_has_module(TEST_CO, "employee_app"),
        )
        check("readiness modules step done", any(s["key"] == "modules" and s["done"] for s in mod["readiness"]["steps"]))
        with app.db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT settings FROM payroll_policies WHERE company_code=%s", (TEST_CO,))
                payroll_row = cur.fetchone()
        check("new payroll policy uses the company currency", (payroll_row or {}).get("settings", {}).get("currency") == "KWD")

        mod2 = app.setup_console_set_modules(TEST_CO, app.SetupModulesRequest(modules=["pre_hiring"]), ctx)
        check(
            "disabling drops omitted modules (payroll + employee_app off)",
            "payroll" not in app.configured_company_modules(TEST_CO)
            and "employee_app" not in app.configured_company_modules(TEST_CO)
            and "pre_hiring" in app.configured_company_modules(TEST_CO),
        )
        app.sync_company_module_registry()
        check(
            "restart-style legacy sync preserves explicit module disables",
            "payroll" not in app.configured_company_modules(TEST_CO)
            and "employee_app" not in app.configured_company_modules(TEST_CO),
        )

        profile = app.setup_console_set_profile(
            TEST_CO,
            app.SetupCompanyProfileRequest(name="Setup Console Test", country="SA", timezone="Asia/Riyadh", currency="SAR"),
            ctx,
        )
        check("company profile updates validated fields", profile["profile"]["country"] == "SA" and profile["profile"]["currency"] == "SAR")
        original_audit_writer = app.write_admin_audit
        try:
            app.write_admin_audit = lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("audit-smoke-failure"))
            try:
                app.setup_console_set_profile(
                    TEST_CO,
                    app.SetupCompanyProfileRequest(name="Must Roll Back", country="KW", timezone="Asia/Kuwait", currency="KWD"),
                    ctx,
                )
                raise AssertionError("profile update should fail when its audit row fails")
            except RuntimeError:
                pass
        finally:
            app.write_admin_audit = original_audit_writer
        rolled_back_profile = app.company_profile_payload(TEST_CO)
        check("profile and audit write are atomic", rolled_back_profile["name"] == "Setup Console Test" and rolled_back_profile["country"] == "SA")
        try:
            app.setup_console_set_profile(TEST_CO, app.SetupCompanyProfileRequest(timezone="Kuwait"), ctx)
            raise AssertionError("invalid timezone should 422")
        except app.HTTPException as e:
            check("non-IANA timezone rejected", e.status_code == 422)

        st = app.setup_console_set_settings(
            TEST_CO,
            app.SetupSettingsRequest(notification_preset="office", channel_policy_reviewed=True),
            ctx,
        )
        check("channel policy review saved", any(s["key"] == "channel_policy" and s["done"] for s in st["readiness"]["steps"]))

        # owner
        owner = app.setup_console_seed_owner(TEST_CO, app.SetupOwnerRequest(email="owner@setupconsoletest.com", name="Test Owner", phone="96599000111"), ctx)
        check("owner seeded with role=owner", (owner.get("user") or {}).get("role") == "owner")
        check("owner invite token issued", bool(owner.get("invite_token")))
        check("readiness owner step done", any(s["key"] == "owner" and s["done"] for s in owner["readiness"]["steps"]))
        owner_again = app.setup_console_seed_owner(TEST_CO, app.SetupOwnerRequest(email="owner@setupconsoletest.com"), ctx)
        check("re-seeding the same owner is safe", (owner_again.get("user") or {}).get("role") == "owner")
        with app.db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT metadata FROM dashboard_user_invites WHERE company_code=%s ORDER BY created_at DESC LIMIT 1", (TEST_CO,))
                invite_metadata = (cur.fetchone() or {}).get("metadata") or {}
        check("invite token is returned once but never persisted in metadata", "invite_token_preview" not in invite_metadata and owner_again["invite_token"] not in str(invite_metadata))

        # whatsapp link requires an owner -> on a fresh company it should 422
        app.setup_console_create_company(app.SetupCompanyCreateRequest(company_code=TEST_CO2, name="No Owner Co"), ctx)
        try:
            app.setup_console_link_whatsapp(TEST_CO2, app.SetupWhatsAppLinkRequest(phone="96599000222"), ctx); raise AssertionError("link without owner should 422")
        except app.HTTPException as e:
            check("WhatsApp link without an Owner -> 422", e.status_code == 422)

        wa = app.setup_console_link_whatsapp(TEST_CO, app.SetupWhatsAppLinkRequest(phone="96599000111"), ctx)
        check("WhatsApp link attaches to the Owner", bool(wa.get("user_id")))
        check("HR-user WhatsApp identity stays optional", wa["readiness"]["ready"] is True)

        try:
            app.setup_console_upsert_channel_account(
                TEST_CO,
                app.SetupCompanyChannelAccountRequest(provider_account_id="wa-smoke-account"),
                ctx,
            )
            raise AssertionError("channel account flag off should 404")
        except app.HTTPException as e:
            check("channel account mutations hidden while flag OFF", e.status_code == 404)

        os.environ["WATHEFNI_COMPANY_CHANNEL_ACCOUNTS"] = "on"
        pending = app.setup_console_upsert_channel_account(
            TEST_CO,
            app.SetupCompanyChannelAccountRequest(
                provider_account_id="wa-smoke-account",
                sender_phone="96599000111",
                audiences=["candidate", "employee"],
                status="active",
            ),
            ctx,
        )
        check("unverified active request reports pending honestly", pending["channel_account"]["status"] == "pending_verification" and pending["readiness"]["ready"] is False)
        os.environ["WATHEFNI_COMPANY_CHANNEL_ACCOUNTS"] = "off"
        check("pending account does not block readiness while channel feature is OFF", app.setup_console_company_readiness(TEST_CO)["ready"] is True)
        os.environ["WATHEFNI_COMPANY_CHANNEL_ACCOUNTS"] = "on"
        verified = app.setup_console_upsert_channel_account(
            TEST_CO,
            app.SetupCompanyChannelAccountRequest(
                provider_account_id="wa-smoke-account",
                sender_phone="96599000111",
                audiences=["candidate", "employee"],
                status="active",
                verification_reference="provider-check-smoke",
            ),
            ctx,
        )
        check("verified company channel can become active", verified["channel_account"]["verified"] is True and verified["readiness"]["ready"] is True)
        isolated_detail = app.setup_console_company_detail(TEST_CO2, ctx)
        check("company channel account is tenant-isolated", isolated_detail.get("channel_account") is None)
        check("company WhatsApp account is separate from HR identity", (
            verified["channel_account"]["provider_account_id"] == "wa-smoke-account"
            and app.setup_console_company_readiness(TEST_CO)["whatsapp_links"] == 1
        ))
        disabled = app.setup_console_disable_channel_account(TEST_CO, ctx)
        check("channel account disable is soft and audited", disabled["channel_account"]["status"] == "disabled")

        listing = app.setup_console_list_companies(q="SETUPCONSOLE", limit=1, offset=0, superadmin=ctx)
        check("company list supports search and pagination", listing["total_count"] == 2 and len(listing["companies"]) == 1 and listing["has_more"] is True)

        with app.db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT to_regclass('public.company_channel_accounts') AS table_name")
                schema_row = cur.fetchone()
        check("schema creates channel account table without manual SQL", bool((schema_row or {}).get("table_name")))

        # --- 3) company lifecycle (disable / reactivate / archive) ----------
        fresh_owner = app.setup_console_seed_owner(
            TEST_CO,
            app.SetupOwnerRequest(email="owner@setupconsoletest.com", name="Lifecycle Owner", phone="96599000111"),
            ctx,
        )
        invite_token = fresh_owner.get("invite_token")
        check("fresh owner invite available for lifecycle proof", bool(invite_token))
        accepted = app.dashboard_team_accept_invite(
            app.DashboardAcceptInviteRequest(
                invite_token=invite_token,
                name="Lifecycle Owner",
                password="LifecyclePass1",
            )
        )
        session_token = accepted.get("access_token") or accepted.get("token")
        check("owner accept creates a session for lifecycle proof", bool(session_token))
        modules_before = sorted(app.configured_company_modules(TEST_CO))

        try:
            app.setup_console_set_company_lifecycle(
                "WATHEFNI",
                app.SetupCompanyLifecycleRequest(status="disabled", reason="must never happen"),
                ctx,
            )
            raise AssertionError("WATHEFNI disable should be blocked")
        except app.HTTPException as e:
            check("WATHEFNI cannot be disabled via lifecycle control", e.status_code == 409 and e.detail.get("error") == "protected_company")

        try:
            app.setup_console_set_company_lifecycle(
                TEST_CO,
                app.SetupCompanyLifecycleRequest(status="disabled", reason=""),
                ctx,
            )
            raise AssertionError("empty reason should 422")
        except app.HTTPException as e:
            check("lifecycle reason required", e.status_code == 422 and e.detail.get("error") == "lifecycle_reason_required")

        disabled = app.setup_console_set_company_lifecycle(
            TEST_CO,
            app.SetupCompanyLifecycleRequest(status="disabled", reason="Phase 7A smoke disable"),
            ctx,
        )
        check("disable returns disabled status", disabled.get("status") == "disabled")
        check("disable revokes active sessions", int(disabled.get("revoked_sessions") or 0) >= 1)
        check("disable keeps readiness status disabled", disabled["readiness"].get("status") == "disabled")
        check("disable preserves modules", sorted(app.configured_company_modules(TEST_CO)) == modules_before)

        with app.db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT count(*) AS n FROM dashboard_user_sessions WHERE company_code=%s AND status='active'",
                    (TEST_CO,),
                )
                active_sessions = int((cur.fetchone() or {}).get("n") or 0)
                cur.execute(
                    "SELECT count(*) AS n FROM dashboard_user_invites WHERE company_code=%s AND status='pending'",
                    (TEST_CO,),
                )
                pending_invites = int((cur.fetchone() or {}).get("n") or 0)
        check("no active sessions remain after disable", active_sessions == 0)
        check("pending invites superseded after disable", pending_invites == 0)

        try:
            app.dashboard_auth_login(app.DashboardLoginRequest(company_code=TEST_CO, email="owner@setupconsoletest.com", password="LifecyclePass1"))
            raise AssertionError("login should fail while disabled")
        except app.HTTPException as e:
            check("login blocked while company disabled", e.status_code == 403 and e.detail.get("error") == "company_disabled")

        try:
            app.dashboard_context(authorization=f"Bearer {session_token}", x_company_code=TEST_CO)
            raise AssertionError("old session should be rejected")
        except app.HTTPException as e:
            check("old session rejected after disable", e.status_code in (401, 403))

        try:
            app.setup_console_seed_owner(TEST_CO, app.SetupOwnerRequest(email="another@setupconsoletest.com", name="Blocked"), ctx)
            raise AssertionError("owner seed should fail while disabled")
        except app.HTTPException as e:
            check("owner seed blocked while company disabled", e.status_code == 403)

        active_listing = app.setup_console_list_companies(q=TEST_CO, limit=20, offset=0, superadmin=ctx)
        check(
            "disabled company hidden from default active list",
            TEST_CO not in [c.get("company_code") for c in active_listing.get("companies") or []],
        )
        inactive_listing = app.setup_console_list_companies(
            q=TEST_CO, limit=20, offset=0, include_inactive=True, superadmin=ctx
        )
        check(
            "disabled company visible when include_inactive=true",
            TEST_CO in [c.get("company_code") for c in inactive_listing.get("companies") or []],
        )

        reactivated = app.setup_console_set_company_lifecycle(
            TEST_CO,
            app.SetupCompanyLifecycleRequest(status="active", reason="Phase 7A smoke reactivate"),
            ctx,
        )
        check("reactivate restores active status", reactivated.get("status") == "active")
        check("reactivate preserves modules", sorted(app.configured_company_modules(TEST_CO)) == modules_before)
        fresh_login = app.dashboard_auth_login(
            app.DashboardLoginRequest(company_code=TEST_CO, email="owner@setupconsoletest.com", password="LifecyclePass1")
        )
        fresh_token = fresh_login.get("access_token") or fresh_login.get("token")
        check("fresh login works after reactivate", bool(fresh_token))
        try:
            app.dashboard_context(authorization=f"Bearer {session_token}", x_company_code=TEST_CO)
            raise AssertionError("old revoked session must stay dead after reactivate")
        except app.HTTPException as e:
            check("old session remains revoked after reactivate", e.status_code in (401, 403))

        archived = app.setup_console_set_company_lifecycle(
            TEST_CO,
            app.SetupCompanyLifecycleRequest(status="archived", reason="Phase 7A smoke archive"),
            ctx,
        )
        check("archive returns archived status", archived.get("status") == "archived")
        try:
            app.dashboard_auth_login(app.DashboardLoginRequest(company_code=TEST_CO, email="owner@setupconsoletest.com", password="LifecyclePass1"))
            raise AssertionError("login should fail while archived")
        except app.HTTPException as e:
            check("login blocked while company archived", e.status_code == 403 and e.detail.get("error") == "company_archived")
        archived_listing = app.setup_console_list_companies(q=TEST_CO, limit=20, offset=0, superadmin=ctx)
        check(
            "archived company hidden from default active list",
            TEST_CO not in [c.get("company_code") for c in archived_listing.get("companies") or []],
        )

        with app.db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT count(*) AS n FROM action_results WHERE company_code=%s "
                    "AND action_type IN ('setup_company_disabled','setup_company_reactivated','setup_company_archived')",
                    (TEST_CO,),
                )
                lifecycle_audits = int((cur.fetchone() or {}).get("n") or 0)
        check("lifecycle transitions are audited", lifecycle_audits >= 3)

        # --- 4) boundaries: mutating a non-existent company -> 404 ---------
        for label, fn in (
            ("modules", lambda: app.setup_console_set_modules("NOSUCHCOMPANYXYZ", app.SetupModulesRequest(modules=["pre_hiring"]), ctx)),
            ("settings", lambda: app.setup_console_set_settings("NOSUCHCOMPANYXYZ", app.SetupSettingsRequest(timezone="Asia/Kuwait"), ctx)),
            ("profile", lambda: app.setup_console_set_profile("NOSUCHCOMPANYXYZ", app.SetupCompanyProfileRequest(name="Missing"), ctx)),
            ("owner", lambda: app.setup_console_seed_owner("NOSUCHCOMPANYXYZ", app.SetupOwnerRequest(email="x@y.com"), ctx)),
            ("lifecycle", lambda: app.setup_console_set_company_lifecycle("NOSUCHCOMPANYXYZ", app.SetupCompanyLifecycleRequest(status="disabled", reason="missing"), ctx)),
        ):
            try:
                fn(); raise AssertionError(f"{label} on missing company should 404")
            except app.HTTPException as e:
                check(f"{label} on a non-existent company -> 404", e.status_code == 404)

        # --- 5) audit: setup_* rows recorded for the company ---------------
        with app.db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT count(*) AS n FROM action_results WHERE company_code=%s AND action_type LIKE 'setup_%%'", (TEST_CO,))
                audit_rows = int((cur.fetchone() or {}).get("n") or 0)
        check("setup actions are audited (>=8 rows)", audit_rows >= 8)
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
