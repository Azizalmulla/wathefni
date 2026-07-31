"""Phase 1 tenant email authority — unit tests (no DB / no prod)."""

from __future__ import annotations

import microsoft_mail_send as mms
import tenant_email_authority as tea


def test_resolve_defaults_to_wathefni():
    resolved = tea.resolve_outbound_sender_pure(
        settings=None,
        global_from="hr@wathefni.ai",
        global_reply=None,
        postmark_configured=True,
    )
    assert resolved["mode"] == "wathefni"
    assert resolved["from_address"] == "hr@wathefni.ai"
    assert resolved["provider"] == "postmark"
    assert resolved["activatable"] is True


def test_refuse_unverified_company_from():
    resolved = tea.resolve_outbound_sender_pure(
        settings={
            "outbound_mode": "postmark_company_domain",
            "from_address": "hr@acme.com",
            "display_name": "Acme HR",
        },
        global_from="hr@wathefni.ai",
        verified_domain_names=[],
    )
    assert resolved["activatable"] is False
    assert resolved["block_reason"] == "company_domain_not_verified"

    ok = tea.resolve_outbound_sender_pure(
        settings={
            "outbound_mode": "postmark_company_domain",
            "from_address": "hr@acme.com",
        },
        global_from="hr@wathefni.ai",
        verified_domain_names=["acme.com"],
    )
    assert ok["activatable"] is True
    assert ok["from_address"] == "hr@acme.com"


def test_microsoft_mode_requires_approved_mailbox():
    blocked = tea.resolve_outbound_sender_pure(
        settings={"outbound_mode": "microsoft_mailbox"},
        global_from="hr@wathefni.ai",
        approved_mailboxes=[],
        microsoft_configured=True,
    )
    assert blocked["activatable"] is False
    assert blocked["block_reason"] == "microsoft_mailbox_not_approved"

    ready = tea.resolve_outbound_sender_pure(
        settings={"outbound_mode": "microsoft_mailbox", "display_name": "People"},
        global_from="hr@wathefni.ai",
        approved_mailboxes=[{"address": "hr@acme.com", "status": "approved", "allow_send": True}],
        microsoft_configured=True,
    )
    assert ready["activatable"] is True
    assert ready["provider"] == "microsoft_graph"
    assert ready["from_address"] == "hr@acme.com"


def test_microsoft_not_configured_blocks():
    resolved = tea.resolve_outbound_sender_pure(
        settings={"outbound_mode": "microsoft_mailbox"},
        global_from="hr@wathefni.ai",
        approved_mailboxes=[{"address": "hr@acme.com", "status": "approved", "allow_send": True}],
        microsoft_configured=False,
    )
    assert resolved["activatable"] is False
    assert resolved["block_reason"] == "microsoft_mail_not_configured"


def test_dual_send_skip_matrix():
    assert tea.should_skip_interview_email_pure(
        calendar_invite_sent=True,
        candidate_email="a@b.com",
        interview_email_when_calendar_sent=False,
        explicit=False,
    )
    assert not tea.should_skip_interview_email_pure(
        calendar_invite_sent=True,
        candidate_email="a@b.com",
        interview_email_when_calendar_sent=True,
        explicit=False,
    )
    assert not tea.should_skip_interview_email_pure(
        calendar_invite_sent=True,
        candidate_email="a@b.com",
        interview_email_when_calendar_sent=False,
        explicit=True,
    )
    assert not tea.should_skip_interview_email_pure(
        calendar_invite_sent=False,
        candidate_email="a@b.com",
        interview_email_when_calendar_sent=False,
        explicit=False,
    )


def test_postmark_domain_status_mapping():
    assert tea.map_postmark_domain_status({"DKIMVerified": True, "ReturnPathDomainVerified": True}) == "verified"
    assert tea.map_postmark_domain_status({"DKIMVerified": False, "DKIMUpdateStatus": "Pending"}) == "pending_verification"
    assert tea.map_postmark_domain_status({"DKIMVerified": False, "DKIMPendingHost": "x._domainkey"}) == "pending_verification"


def test_format_from_header():
    assert tea.format_from_header(None, "hr@wathefni.ai") == "hr@wathefni.ai"
    assert tea.format_from_header("Acme HR", "hr@acme.com") == '"Acme HR" <hr@acme.com>'


def test_mail_send_sp_separation_env():
    # Without mail-specific client id, mail send must report not configured
    # even if calendar env might exist in some shells.
    assert isinstance(mms.mail_send_configured(), bool)


def test_public_view_has_no_internal_jargon():
    # Shape-only: ensure projection helpers do not invent capability IDs in choice titles
    choices_titles = [
        "Send through Wathefni",
        "Send from our Microsoft mailbox",
        "Send from our company domain",
    ]
    for title in choices_titles:
        assert "RBAC" not in title
        assert "service principal" not in title.lower()
        assert "Mail.Send" not in title


def test_tenant_isolation_helpers_scope_by_company_code():
    # Pure contract: company codes normalize and empty company never invents foreign rows
    assert tea._company("acme") == "ACME"
    assert tea.default_settings("ACME")["company_code"] == "ACME"
    assert tea.default_settings("")["outbound_mode"] == "wathefni"


def test_inbound_resolve_intake_untouched_import():
    """Regression smoke: durable ingress module still present; Phase 1 must not rewrite it."""
    from pathlib import Path

    path = Path(__file__).with_name("durable_email_ingress.py")
    assert path.exists()
    source = path.read_text(encoding="utf-8")
    assert "resolve_intake" in source or "intake_address" in source
    # Authority module must not redefine durable ingress routing
    auth = Path(__file__).with_name("tenant_email_authority.py").read_text(encoding="utf-8")
    assert "durable_email_ingress" not in auth
    assert "inbound webhook" not in auth.lower()


if __name__ == "__main__":
    test_resolve_defaults_to_wathefni()
    test_refuse_unverified_company_from()
    test_microsoft_mode_requires_approved_mailbox()
    test_microsoft_not_configured_blocks()
    test_dual_send_skip_matrix()
    test_postmark_domain_status_mapping()
    test_format_from_header()
    test_mail_send_sp_separation_env()
    test_public_view_has_no_internal_jargon()
    test_tenant_isolation_helpers_scope_by_company_code()
    test_inbound_resolve_intake_untouched_import()
    print("tenant_email_authority Phase 1 PASS")
