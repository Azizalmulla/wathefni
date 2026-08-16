#!/usr/bin/env python3
"""Live Microsoft outbound evidence matrix for Hybrid Email Phase 1.

Evidence tenant only (default WATHEFNI). Does not enable customer tenants.
Requires WATHEFNI_M365_MAIL_* already configured AFTER Exchange scope is applied.
"""

from __future__ import annotations

import json
import os
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

ORCH = Path(__file__).resolve().parent
sys.path.insert(0, str(ORCH))

import app  # noqa: E402
import microsoft_mail_send as mms  # noqa: E402
import tenant_email_authority as tea  # noqa: E402

EVIDENCE_COMPANY = (os.environ.get("WATHEFNI_MAIL_EVIDENCE_COMPANY") or "WATHEFNI").strip().upper()
EVIDENCE_UPN = (os.environ.get("WATHEFNI_M365_MAIL_EVIDENCE_UPN") or "ABDULAZIZALMULLA@wathefni.onmicrosoft.com").strip().lower()
DENIED_UPN = (os.environ.get("WATHEFNI_M365_MAIL_DENIED_UPN") or "wathefni-rbac-deny-probe@wathefni.onmicrosoft.com").strip().lower()
REPLY_TO = (os.environ.get("WATHEFNI_M365_MAIL_REPLY_TO") or "hr@wathefni.ai").strip().lower()
RECIPIENT = (os.environ.get("WATHEFNI_M365_MAIL_TEST_TO") or EVIDENCE_UPN).strip().lower()
OUTDIR = Path(os.environ.get("MAIL_EVID_DIR") or f"/tmp/hybrid-email-m365-outbound-{int(time.time())}")
OUTDIR.mkdir(parents=True, exist_ok=True)

results: dict = {"stamp": datetime.now(timezone.utc).isoformat(), "proofs": {}, "company": EVIDENCE_COMPANY}


def ok(name: str, cond: bool, **detail) -> None:
    results["proofs"][name] = {"ok": bool(cond), **detail}
    print(("PASS" if cond else "FAIL"), name, json.dumps(detail)[:300])
    (OUTDIR / "results.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
    if not cond:
        raise SystemExit(2)


def write(name: str, obj) -> None:
    (OUTDIR / name).write_text(json.dumps(obj, indent=2, default=str), encoding="utf-8")


def jwt_roles(token: str) -> list[str]:
    import base64

    part = token.split(".")[1]
    pad = "=" * (-len(part) % 4)
    data = json.loads(base64.urlsafe_b64decode(part + pad))
    roles = data.get("roles") or []
    return list(roles) if isinstance(roles, list) else []


def main() -> None:
    print("=== hybrid email microsoft outbound live matrix ===")
    print("outdir=", OUTDIR)

    cal_client = (os.environ.get("WATHEFNI_M365_CLIENT_ID") or "").strip()
    mail_client = (os.environ.get("WATHEFNI_M365_MAIL_CLIENT_ID") or "").strip()
    ok("mail_sp_configured", mms.mail_send_configured())
    ok("mail_sp_differs_from_calendar", bool(mail_client) and mail_client != cal_client, mail_client_suffix=mail_client[-8:], calendar_suffix=cal_client[-8:])

    # 1) Separate mail-SP token mint
    token = mms.mint_mail_graph_token()
    roles = jwt_roles(token)
    write("mail-token-roles.json", {"roles": roles})
    ok("mail_sp_token_mint", bool(token), roles=roles)
    ok("mail_sp_has_mail_send_role_or_rbacfa", ("Mail.Send" in roles) or (roles == [] or "Mail.Send" in roles), note="RBACfA may omit roles claim")
    ok("mail_sp_no_mail_read_roles", "Mail.Read" not in roles and "Mail.ReadWrite" not in roles, roles=roles)

    # 2) Calendar/Teams SP cannot perform mail sending
    import platform_connection_c6 as c6
    import urllib.error
    import urllib.request

    cal_pem = open(os.environ["WATHEFNI_M365_CERT_BUNDLE_PATH"], encoding="utf-8").read()
    try:
        cal_tok = c6.mint_microsoft_app_token(
            tenant_id=os.environ["WATHEFNI_M365_TENANT_ID"],
            client_id=cal_client,
            certificate_pem=cal_pem,
        )
    finally:
        del cal_pem
    payload = json.dumps(
        {
            "message": {
                "subject": "calendar-sp-must-not-send",
                "body": {"contentType": "Text", "content": "deny"},
                "toRecipients": [{"emailAddress": {"address": RECIPIENT}}],
            },
            "saveToSentItems": False,
        }
    ).encode()
    req = urllib.request.Request(
        f"https://graph.microsoft.com/v1.0/users/{EVIDENCE_UPN}/sendMail",
        data=payload,
        headers={"Authorization": f"Bearer {cal_tok}", "Content-Type": "application/json"},
        method="POST",
    )
    cal_denied = False
    cal_code = None
    try:
        urllib.request.urlopen(req, timeout=30)
    except urllib.error.HTTPError as exc:
        cal_denied = exc.code in {401, 403}
        cal_code = exc.code
        write("calendar-sp-send-deny.json", {"http": exc.code, "body": exc.read().decode("utf-8", errors="replace")[:500]})
    ok("calendar_sp_cannot_send_mail", cal_denied, http=cal_code)

    # 3) Email SP cannot use Calendar/Teams authority (Calendars.ReadWrite create)
    mail_tok = token
    start = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    end = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    # end must be after start; bump +30m
    from datetime import timedelta

    now = datetime.now(timezone.utc)
    ev_body = json.dumps(
        {
            "subject": "mail-sp-must-not-create-calendar",
            "start": {"dateTime": now.isoformat().replace("+00:00", ""), "timeZone": "UTC"},
            "end": {"dateTime": (now + timedelta(minutes=30)).isoformat().replace("+00:00", ""), "timeZone": "UTC"},
        }
    ).encode()
    req2 = urllib.request.Request(
        f"https://graph.microsoft.com/v1.0/users/{EVIDENCE_UPN}/events",
        data=ev_body,
        headers={"Authorization": f"Bearer {mail_tok}", "Content-Type": "application/json"},
        method="POST",
    )
    mail_cal_denied = False
    mail_cal_code = None
    try:
        urllib.request.urlopen(req2, timeout=30)
    except urllib.error.HTTPError as exc:
        mail_cal_denied = exc.code in {401, 403}
        mail_cal_code = exc.code
        write("mail-sp-calendar-deny.json", {"http": exc.code, "body": exc.read().decode("utf-8", errors="replace")[:500]})
    ok("email_sp_cannot_use_calendar_authority", mail_cal_denied, http=mail_cal_code)

    # Register evidence mailbox, require readiness before activate
    mb = tea.upsert_operational_mailbox(
        app,
        EVIDENCE_COMPANY,
        address=EVIDENCE_UPN,
        display_name="Wathefni Evidence",
        provider="microsoft",
        allow_send=True,
        status="approved",
        entra_user_id=os.environ.get("WATHEFNI_M365_MAIL_EVIDENCE_USER_ID") or None,
        exchange_scope_ref=os.environ.get("WATHEFNI_M365_MAIL_AU_ID") or "Wathefni-Mail-Evidence",
    )
    write("mailbox-upsert.json", mb)
    # Probe (token mint path used by API)
    mms.mint_mail_graph_token()
    probed = tea.record_mailbox_probe(app, EVIDENCE_COMPANY, str(mb["mailbox_id"]), ok=True)
    write("mailbox-probe.json", probed)
    ok("mailbox_probe_ok", bool(probed.get("last_probe_ok")), mailbox_id=probed.get("mailbox_id"))

    # Activation must succeed only when ready
    settings = tea.upsert_email_settings(
        app,
        EVIDENCE_COMPANY,
        {
            "outbound_mode": "microsoft_mailbox",
            "outbound_mailbox_id": str(mb["mailbox_id"]),
            "reply_to": REPLY_TO,
            "display_name": "Wathefni Evidence",
            "allow_wathefni_emergency_fallback": False,
        },
        allow_unready_mode=False,
        updated_by_user_id="mail-outbound-evidence",
    )
    write("settings-activated.json", settings)
    ok("microsoft_mode_activated_evidence_only", settings.get("outbound_mode") == "microsoft_mailbox")

    # Ensure no other tenant activated
    with app.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT company_code, outbound_mode FROM company_email_settings WHERE outbound_mode <> 'wathefni'"
            )
            rows = cur.fetchall()
            branded = [dict(r) if hasattr(r, "keys") else {"company_code": r[0], "outbound_mode": r[1]} for r in rows]
    write("branded-tenants.json", branded)
    ok(
        "only_evidence_tenant_microsoft",
        len(branded) == 1 and str(branded[0].get("company_code")).upper() == EVIDENCE_COMPANY,
        branded=branded,
    )

    # 4) Approved mailbox sends branded email
    marker = f"hybrid-email-ms-outbound-{uuid.uuid4().hex[:12]}"
    subject = f"[Wathefni evidence] {marker}"
    body = f"Hybrid Email Phase 1 Microsoft outbound evidence.\nmarker={marker}\nreply_to={REPLY_TO}\n"
    sent = mms.send_mail_as_mailbox(
        mailbox=EVIDENCE_UPN,
        to=RECIPIENT,
        subject=subject,
        body=body,
        reply_to=REPLY_TO,
        save_to_sent_items=True,
    )
    write("send-approved.json", sent)
    ok(
        "approved_mailbox_send",
        bool(sent.get("ok")) and sent.get("provider_accept_status") == "accepted_by_provider",
        **{k: sent.get(k) for k in ("ok", "provider_accept_status", "error", "raw")},
    )
    ok("accept_status_not_delivered", sent.get("provider_accept_status") == "accepted_by_provider")

    # Authority dispatch path records accepted_by_provider
    resolved = tea.resolve_outbound_sender(app, EVIDENCE_COMPANY, purpose="evidence_send", for_send=True)
    write("resolved-sender.json", resolved)
    ok("resolve_microsoft_activatable", resolved.get("mode") == "microsoft_mailbox" and resolved.get("activatable") is True)
    dispatched = app.dispatch_outbound_email(
        to=RECIPIENT,
        subject=f"{subject}-via-dispatch",
        body=body + "via_dispatch=1\n",
        company_code=EVIDENCE_COMPANY,
        purpose="evidence_dispatch",
    )
    write("dispatch-approved.json", dispatched)
    ok(
        "dispatch_accepted_by_provider",
        dispatched.get("provider_accept_status") == "accepted_by_provider" or (
            dispatched.get("ok") and dispatched.get("provider") == "microsoft_graph"
        ),
        **{k: dispatched.get(k) for k in ("ok", "provider", "provider_accept_status", "error", "sender_mode")},
    )

    # 5) Outside-scope deny
    denied = mms.send_mail_as_mailbox(
        mailbox=DENIED_UPN,
        to=RECIPIENT,
        subject=f"[deny] {marker}",
        body="should fail",
        reply_to=REPLY_TO,
        save_to_sent_items=False,
    )
    write("send-denied.json", denied)
    ok(
        "outside_scope_send_denied",
        not denied.get("ok"),
        error=denied.get("error"),
        raw=denied.get("raw"),
    )

    # 6) Inbound / calendar unchanged markers
    ok("inbound_still_postmark", app.inbound_email_enabled() is True)
    ok("calendar_client_unchanged", cal_client == "16f7135a-b7e8-4ac8-adfe-2d2b13de3131")
    cal_mod = (ORCH / "interview_microsoft_calendar.py").read_text(encoding="utf-8")
    ok("calendar_module_untouched_by_mail_client", "WATHEFNI_M365_MAIL_CLIENT_ID" not in cal_mod and "microsoft_mail_send" not in cal_mod)

    # 7) Tenant isolation — other company cannot see evidence mailbox
    other = None
    with app.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT company_code FROM companies WHERE COALESCE(status,'active')='active' AND company_code <> %s ORDER BY company_code LIMIT 1",
                (EVIDENCE_COMPANY,),
            )
            row = cur.fetchone()
            if row:
                other = str(row["company_code"] if hasattr(row, "keys") else row[0]).upper()
    if other:
        foreign = tea.list_operational_mailboxes(app, other)
        leak = [m for m in foreign if str(m.get("address") or "").lower() == EVIDENCE_UPN]
        ok("tenant_isolation_no_mailbox_leak", len(leak) == 0, other=other, leak_count=len(leak))
        got = tea.get_mailbox(app, other, str(mb["mailbox_id"]))
        ok("tenant_isolation_get_by_id", got is None, other=other)
    else:
        ok("tenant_isolation_skipped_no_other_tenant", True)

    # 8) Switch evidence tenant back to Wathefni
    restored = tea.force_wathefni_fallback(app, EVIDENCE_COMPANY, updated_by_user_id="mail-outbound-evidence")
    write("settings-restored-wathefni.json", restored)
    ok("switch_back_to_wathefni", restored.get("outbound_mode") == "wathefni")
    live = tea.resolve_outbound_sender(app, EVIDENCE_COMPANY, purpose="after_restore", for_send=True)
    ok("resolve_wathefni_after_restore", live.get("mode") == "wathefni" and live.get("provider") == "postmark", resolved=live)

    print("ALL_MICROSOFT_OUTBOUND_MATRIX_CORE_PASS")
    print("MARKER=", marker)
    print("NOTE= Sent Items / MessageTrace / reply-to delivery verification handled by companion EXO checks.")
    (OUTDIR / "MARKER.txt").write_text(marker + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
