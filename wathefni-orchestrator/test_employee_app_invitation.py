"""Unit tests for employee_app_invitation status + outbound mapping."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import employee_app_invitation as inv


def test_map_outbound_delivered_email():
    status, channel, error = inv._map_outbound_to_invite_delivery(
        {"ok": True, "delivery_status": "sent_email_fallback", "channel": "email"}
    )
    assert status == inv.STATUS_DELIVERED
    assert channel == inv.CHANNEL_EMAIL
    assert error is None


def test_map_outbound_needs_hr():
    status, channel, error = inv._map_outbound_to_invite_delivery(
        {"ok": False, "delivery_status": "needs_hr_action", "error": "no_channel"}
    )
    assert status == inv.STATUS_NEEDS_ATTENTION
    assert error == "no_channel"


def test_map_outbound_failed():
    status, channel, error = inv._map_outbound_to_invite_delivery(
        {"ok": False, "delivery_status": "failed", "error": "provider_down"}
    )
    assert status == inv.STATUS_FAILED
    assert error == "provider_down"


def test_invitation_public_status_expired():
    now = datetime.now(timezone.utc)
    invite = {
        "status": "pending",
        "expires_at": now - timedelta(minutes=1),
        "delivery_status": "sent",
    }
    assert inv.invitation_public_status(invite, now=now) == inv.STATUS_EXPIRED


def test_invitation_public_status_activated():
    now = datetime.now(timezone.utc)
    invite = {"status": "redeemed", "expires_at": now + timedelta(hours=1)}
    assert inv.invitation_public_status(invite, now=now) == inv.STATUS_ACTIVATED


def test_invitation_public_status_delivery():
    now = datetime.now(timezone.utc)
    invite = {
        "status": "pending",
        "expires_at": now + timedelta(hours=1),
        "delivery_status": "delivered",
    }
    assert inv.invitation_public_status(invite, now=now) == inv.STATUS_DELIVERED


def test_auto_invite_flag_off(monkeypatch):
    monkeypatch.setenv("WATHEFNI_EMPLOYEE_APP_AUTO_INVITE", "off")
    assert inv.auto_invite_enabled(company_code="WATHEFNI") is False


def test_auto_invite_company_allowlist(monkeypatch):
    monkeypatch.setenv("WATHEFNI_EMPLOYEE_APP_AUTO_INVITE", "on")
    monkeypatch.setenv("WATHEFNI_EMPLOYEE_APP_AUTO_INVITE_COMPANIES", "WATHEFNI,ACME")
    assert inv.auto_invite_enabled(company_code="WATHEFNI") is True
    assert inv.auto_invite_enabled(company_code="OTHER") is False


def test_snapshot_actions_never_require_code_disclosure_fields():
    # Contract: public status helpers must not invent a code field.
    assert "activation_code" not in inv.HR_STATUSES
