"""Keep prior unit file green after fail-closed fallback correction."""

from __future__ import annotations

import microsoft_mail_send as mms
import tenant_email_authority as tea


def test_resolve_defaults_to_wathefni():
    resolved = tea.resolve_outbound_sender_pure(settings=None, global_from="hr@wathefni.ai")
    assert resolved["mode"] == "wathefni"
    assert resolved["from_address"] == "hr@wathefni.ai"
    assert resolved["activatable"] is True


def test_refuse_unverified_company_from():
    resolved = tea.resolve_outbound_sender_pure(
        settings={"outbound_mode": "postmark_company_domain", "from_address": "hr@acme.com"},
        global_from="hr@wathefni.ai",
        verified_domain_names=[],
    )
    assert resolved["activatable"] is False
    assert resolved["block_reason"] == "company_domain_not_verified"
    assert resolved.get("emergency_fallback_used") is False


def test_microsoft_mode_requires_approved_probed_mailbox():
    blocked = tea.resolve_outbound_sender_pure(
        settings={"outbound_mode": "microsoft_mailbox"},
        global_from="hr@wathefni.ai",
        approved_mailboxes=[],
        microsoft_configured=True,
    )
    assert blocked["activatable"] is False

    ready = tea.resolve_outbound_sender_pure(
        settings={"outbound_mode": "microsoft_mailbox"},
        global_from="hr@wathefni.ai",
        approved_mailboxes=[{"address": "hr@acme.com", "status": "approved", "allow_send": True, "last_probe_ok": True}],
        microsoft_configured=True,
    )
    assert ready["activatable"] is True


def test_no_silent_fallback():
    resolved = tea.resolve_outbound_sender_pure(
        settings={"outbound_mode": "microsoft_mailbox", "allow_wathefni_emergency_fallback": False},
        global_from="hr@wathefni.ai",
        approved_mailboxes=[],
        microsoft_configured=True,
    )
    assert resolved["mode"] == "microsoft_mailbox"
    assert resolved["activatable"] is False


def test_dual_send_skip_matrix():
    assert tea.should_skip_interview_email_pure(
        calendar_invite_sent=True, candidate_email="a@b.com", interview_email_when_calendar_sent=False
    )
    assert not tea.should_skip_interview_email_pure(
        calendar_invite_sent=True, candidate_email="a@b.com", interview_email_when_calendar_sent=False, explicit=True
    )
    assert not tea.should_skip_interview_email_pure(
        calendar_invite_sent=True, candidate_email="a@b.com", interview_email_when_calendar_sent=False, provider_sync_ok=False
    )


def test_postmark_domain_status_mapping():
    assert tea.map_postmark_domain_status({"DKIMVerified": True, "ReturnPathDomainVerified": True}) == "verified"


def test_format_from_header():
    assert tea.format_from_header("Acme HR", "hr@acme.com") == '"Acme HR" <hr@acme.com>'


def test_mail_send_sp_separation_env():
    assert isinstance(mms.mail_send_configured(), bool)


def test_inbound_resolve_intake_untouched_import():
    from pathlib import Path

    path = Path(__file__).with_name("durable_email_ingress.py")
    assert path.exists()
    auth = Path(__file__).with_name("tenant_email_authority.py").read_text(encoding="utf-8")
    assert "durable_email_ingress" not in auth


if __name__ == "__main__":
    test_resolve_defaults_to_wathefni()
    test_refuse_unverified_company_from()
    test_microsoft_mode_requires_approved_probed_mailbox()
    test_no_silent_fallback()
    test_dual_send_skip_matrix()
    test_postmark_domain_status_mapping()
    test_format_from_header()
    test_mail_send_sp_separation_env()
    test_inbound_resolve_intake_untouched_import()
    print("tenant_email_authority Phase 1 PASS")
