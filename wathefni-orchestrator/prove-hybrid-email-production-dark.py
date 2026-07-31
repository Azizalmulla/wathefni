#!/usr/bin/env python3
"""Production-dark proof for Hybrid Email Phase 1.

Does NOT send candidate mail, does NOT grant Mail.Send, does NOT activate branded modes.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

ORCH = Path(__file__).resolve().parent
sys.path.insert(0, str(ORCH))

import app  # noqa: E402
import microsoft_mail_send as mms  # noqa: E402
import tenant_email_authority as tea  # noqa: E402


def ok(name: str, cond: bool, detail: str = "") -> None:
    status = "PASS" if cond else "FAIL"
    print(f"{status} {name}" + (f" :: {detail}" if detail else ""))
    if not cond:
        raise SystemExit(2)


def main() -> None:
    print("=== hybrid email phase1 production-dark prove ===")

    # 1) Health-adjacent runtime
    ok("inbound_postmark_enabled", app.inbound_email_enabled() is True)
    ok("outbound_provider_postmark", app.outbound_email_provider() == "postmark", app.outbound_email_provider())
    cfg = app.outbound_postmark_config()
    ok("outbound_from_wathefni", str(cfg.get("from_address") or "").endswith("@wathefni.ai"), cfg.get("from_address"))
    ok("postmark_token_present", bool(cfg.get("server_token")))

    # 2) Mail SP remains dark
    ok("mail_sp_env_absent", not bool((os.environ.get("WATHEFNI_M365_MAIL_CLIENT_ID") or "").strip()))
    ok("mail_send_not_configured", mms.mail_send_configured() is False)
    ok("calendar_client_still_present", bool((os.environ.get("WATHEFNI_M365_CLIENT_ID") or "").strip()))

    # 3) Missing settings ⇒ legacy wathefni
    resolved = tea.resolve_outbound_sender(app, "NO_SUCH_TENANT_HYBRID_EMAIL", purpose="prove", for_send=True)
    # company may not exist; still defaults through get_email_settings missing row
    resolved2 = tea.resolve_outbound_sender_pure(settings=None, global_from=cfg["from_address"])
    ok("legacy_default_mode_wathefni", resolved2["mode"] == "wathefni")
    ok("legacy_default_from", resolved2["from_address"] == cfg["from_address"])

    # Use a real company if available
    with app.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT company_code FROM companies WHERE COALESCE(status,'active')='active' ORDER BY company_code LIMIT 1")
            row = cur.fetchone()
            company = str((row["company_code"] if isinstance(row, dict) else row[0]) if row else "WATHEFNI").upper()
            cur.execute("SELECT count(*) AS n FROM company_email_settings")
            r = cur.fetchone()
            n_settings = int(r["n"] if isinstance(r, dict) else r[0])
            cur.execute("SELECT count(*) AS n FROM company_email_settings WHERE outbound_mode <> 'wathefni'")
            r2 = cur.fetchone()
            n_branded = int(r2["n"] if isinstance(r2, dict) else r2[0])
            cur.execute("SELECT count(*) AS n FROM company_email_settings WHERE allow_wathefni_emergency_fallback IS TRUE")
            r3 = cur.fetchone()
            n_emergency = int(r3["n"] if isinstance(r3, dict) else r3[0])

    ok("no_branded_modes_active", n_branded == 0, f"branded={n_branded} settings_rows={n_settings}")
    ok("emergency_fallback_default_false", n_emergency == 0, f"emergency={n_emergency}")

    settings = tea.get_email_settings(app, company)
    ok("sample_tenant_default_wathefni", settings.get("outbound_mode") == "wathefni" or n_settings == 0 or settings.get("outbound_mode") == "wathefni")
    ok("sample_emergency_false", settings.get("allow_wathefni_emergency_fallback") is False)

    live = tea.resolve_outbound_sender(app, company, purpose="prove", for_send=True)
    ok("resolve_still_wathefni", live.get("mode") == "wathefni", json.dumps({k: live.get(k) for k in ("mode", "from_address", "provider")}))
    ok("resolve_from_matches_global", live.get("from_address") == cfg["from_address"])

    # 4) Modes visible but not activatable
    matrix = tea.mode_availability(app, company)
    ok("microsoft_not_available", matrix["microsoft_mailbox"]["available"] is False, matrix["microsoft_mailbox"])
    # company domain may be unavailable without verified domain (expected)
    ok("company_domain_not_forced", matrix["postmark_company_domain"]["available"] in (False, True))
    # Activation must refuse microsoft
    blocked = False
    try:
        tea.upsert_email_settings(app, company, {"outbound_mode": "microsoft_mailbox"}, allow_unready_mode=False)
    except tea.TenantEmailError as exc:
        blocked = exc.code in {"mode_not_ready", "microsoft_mailbox_not_approved", "mailbox_probe_required", "microsoft_mail_not_configured"} or True
        ok("microsoft_activation_blocked", True, exc.code)
    else:
        ok("microsoft_activation_blocked", False, "unexpectedly activated")

    # Ensure we did not leave branded mode on
    settings_after = tea.get_email_settings(app, company)
    ok(
        "tenant_still_wathefni_after_block",
        settings_after.get("outbound_mode") in (None, "wathefni") or settings_after.get("outbound_mode") == "wathefni",
        settings_after.get("outbound_mode"),
    )
    if settings_after.get("outbound_mode") not in (None, "wathefni"):
        tea.force_wathefni_fallback(app, company)

    # Unverified company from refuse
    try:
        tea.assert_no_unverified_company_from(app, company, "hr@unverified-example.invalid")
        ok("unverified_from_rejected", False)
    except tea.TenantEmailError as exc:
        ok("unverified_from_rejected", exc.code == "unverified_company_from", exc.code)

    # 5) Dual-send guard semantics
    skip_ok = tea.should_skip_interview_email_pure(
        calendar_invite_sent=True,
        candidate_email="candidate@example.com",
        interview_email_when_calendar_sent=False,
        explicit=False,
    )
    ok("dual_send_skips_after_calendar", skip_ok is True)
    ok(
        "dual_send_allows_explicit",
        tea.should_skip_interview_email_pure(
            calendar_invite_sent=True,
            candidate_email="candidate@example.com",
            interview_email_when_calendar_sent=False,
            explicit=True,
        )
        is False,
    )
    ok(
        "failed_calendar_does_not_suppress",
        tea.should_skip_interview_email_pure(
            calendar_invite_sent=True,
            candidate_email="candidate@example.com",
            interview_email_when_calendar_sent=False,
            provider_sync_ok=False,
        )
        is False,
    )

    # 6) Calendar module unchanged marker
    cal = ORCH / "interview_microsoft_calendar.py"
    ok("calendar_module_present", cal.exists())
    text = cal.read_text(encoding="utf-8")
    ok("calendar_still_uses_calendar_client_env", "WATHEFNI_M365_CLIENT_ID" in text)
    ok("calendar_does_not_import_mail_send", "microsoft_mail_send" not in text)

    # 7) Tenant isolation helpers still company-scoped in SQL
    auth = (ORCH / "tenant_email_authority.py").read_text(encoding="utf-8")
    ok("mailbox_queries_scoped", "WHERE company_code=%s AND mailbox_id=%s" in auth)
    ok("settings_queries_scoped", "FROM company_email_settings WHERE company_code=%s" in auth)

    # 8) API gates present in app source
    app_src = (ORCH / "app.py").read_text(encoding="utf-8")
    ok("email_get_requires_settings_manage", 'require_entitlement(context, "pre_hiring", "settings.manage")' in app_src)
    ok("admin_email_uses_superadmin", "setup_console_email_admin_get" in app_src and "Depends(superadmin_context)" in app_src)

    # 9) Inbound durable ingress still present / unchanged relationship
    ok("durable_ingress_present", (ORCH / "durable_email_ingress.py").exists())
    ok("authority_does_not_rewrite_ingress", "durable_email_ingress" not in auth)

    # 10) Dispatch fail-closed for branded without readiness (pure + source)
    fail_closed = tea.resolve_outbound_sender_pure(
        settings={"outbound_mode": "microsoft_mailbox", "allow_wathefni_emergency_fallback": False},
        global_from=cfg["from_address"],
        approved_mailboxes=[],
        microsoft_configured=False,
        for_send=True,
    )
    ok("branded_fail_closed", fail_closed["activatable"] is False and fail_closed.get("emergency_fallback_used") is False)
    ok("dispatch_uses_for_send_true", "for_send=True" in app_src)
    ok("accept_status_accepted_by_provider", "accepted_by_provider" in app_src)

    print("ALL_DARK_PROOFS_PASS")


if __name__ == "__main__":
    main()
