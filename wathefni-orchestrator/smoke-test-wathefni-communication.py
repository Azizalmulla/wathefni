#!/usr/bin/env python3
"""Wathefni canonical communication router smoke — policy, readiness, Calendar handoff."""

from __future__ import annotations

import os
import sys
import traceback
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

PASS = 0
FAIL = 0


def check(name: str, cond: bool, detail: str = "") -> None:
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"PASS: {name}")
    else:
        FAIL += 1
        print(f"FAIL: {name} {detail}")


class FakeLegacy:
    """Minimal legacy surface for router unit proofs (no live provider calls)."""

    def __init__(self, policy: dict | None = None):
        self._policy = policy or {}
        self.whatsapp_calls: list[dict] = []
        self.email_calls: list[dict] = []

    def get_company_settings(self, company_code: str | None) -> dict:
        return {"communication_policy": self._policy}

    def delivery_is_dry_run(self) -> bool:
        return True

    def send_octopus_whatsapp(self, **kwargs):
        self.whatsapp_calls.append(kwargs)
        assert "account_id" in kwargs and kwargs["account_id"]
        assert kwargs.get("company_code"), "company_code required for tenant isolation"
        return {"ok": True, "dry_run": True, "account_id": kwargs["account_id"], "message_id": "wa-1"}

    def send_outbound_email(self, **kwargs):
        self.email_calls.append(kwargs)
        assert kwargs.get("company_code"), "company_code required for tenant isolation"
        return {"ok": True, "dry_run": True, "provider": "postmark", "message_id": "em-1"}


def main() -> int:
    print("=== Wathefni communication router smoke ===")
    try:
        import wathefni_communication as comm
        import calendar_participation as part
    except Exception:
        traceback.print_exc()
        check("imports", False)
        return 1

    check("imports", True)

    matrix = {row["channel"]: row for row in comm.channel_readiness_matrix()}
    check("whatsapp production_ready", matrix["whatsapp"]["readiness"] == "production_ready")
    check("email production_ready", matrix["email"]["readiness"] == "production_ready")
    check("wathefni_in_app not selectable", matrix["wathefni_in_app"]["selectable"] is False)
    check("microsoft_teams not selectable", matrix["microsoft_teams"]["selectable"] is False)
    check("telegram not selectable", matrix["telegram"]["selectable"] is False)
    check("sms not selectable", matrix["sms"]["selectable"] is False)

    # No global WhatsApp-first: default pre_hire prefers email.
    default_pre = comm.build_channel_ladder(
        policy_slice=comm.DEFAULT_COMMUNICATION_POLICY["pre_hire"],
    )
    check("default pre_hire email-first among live", default_pre[:1] == ["email"], str(default_pre))

    # Company can choose WhatsApp-first without global hardcode.
    wa_first_policy = {
        "pre_hire": {
            "preferred_channels": ["whatsapp"],
            "fallback_channels": ["email"],
            "enabled_channels": ["whatsapp", "email"],
        }
    }
    legacy = FakeLegacy(wa_first_policy)
    route = comm.resolve_route(
        legacy,
        company_code="DEMOCO",
        purpose="calendar_invitation",
        recipient_type="candidate",
    )
    check("candidate uses pre_hire lifecycle", route.get("lifecycle") == "pre_hire")
    check("company whatsapp-first honored", (route.get("channels") or [])[:1] == ["whatsapp"], str(route.get("channels")))

    email_first = {
        "pre_hire": {
            "preferred_channels": ["email"],
            "fallback_channels": ["whatsapp"],
            "enabled_channels": ["email", "whatsapp"],
        }
    }
    legacy2 = FakeLegacy(email_first)
    route2 = comm.resolve_route(
        legacy2,
        company_code="DEMOCO",
        purpose="calendar_invitation",
        recipient_type="candidate",
    )
    check("company email-first honored", (route2.get("channels") or [])[:1] == ["email"])

    # External guest lifecycle
    route_g = comm.resolve_route(
        legacy2,
        company_code="DEMOCO",
        purpose="calendar_invitation",
        recipient_type="external_guest",
        guest_kind="external",
    )
    check("external guest lifecycle", route_g.get("lifecycle") == "external_guest")

    # Post-hire: foundation channels not selectable → no_qualified until company enables live extras.
    post_default = comm.resolve_route(
        FakeLegacy({}),
        company_code="DEMOCO",
        purpose="calendar_invitation",
        recipient_type="employee",
    )
    check("employee uses post_hire", post_default.get("lifecycle") == "post_hire")
    check(
        "default post_hire has no qualified live channel",
        post_default.get("channels") == [],
        str(post_default.get("channels")),
    )

    post_enabled = {
        "post_hire": {
            "preferred_channels": ["wathefni_in_app", "email"],
            "fallback_channels": ["whatsapp"],
            "enabled_channels": ["wathefni_in_app", "email", "whatsapp"],
        }
    }
    route_e = comm.resolve_route(
        FakeLegacy(post_enabled),
        company_code="DEMOCO",
        purpose="calendar_invitation",
        recipient_type="employee",
    )
    check(
        "post_hire skips unqualified in_app then email",
        (route_e.get("channels") or [])[:1] == ["email"],
        str(route_e.get("channels")),
    )

    hr_policy = {
        "hr_ops": {
            "preferred_channels": ["wathefni_in_app", "whatsapp"],
            "fallback_channels": [],
            "enabled_channels": ["wathefni_in_app", "whatsapp"],
        }
    }
    route_hr = comm.resolve_route(
        FakeLegacy(hr_policy),
        company_code="DEMOCO",
        purpose="calendar_rsvp_received",
        recipient_type="hr",
    )
    check("hr uses hr_ops", route_hr.get("lifecycle") == "hr_ops")
    check("hr skips in_app then whatsapp", (route_hr.get("channels") or [])[:1] == ["whatsapp"])

    # Unqualified never selected even if preferred.
    bad = {
        "pre_hire": {
            "preferred_channels": ["microsoft_teams", "sms", "telegram"],
            "fallback_channels": [],
            "enabled_channels": ["microsoft_teams", "sms", "telegram", "email"],
        }
    }
    route_bad = comm.resolve_route(
        FakeLegacy(bad),
        company_code="DEMOCO",
        purpose="calendar_invitation",
        recipient_type="candidate",
    )
    check("unqualified channels excluded", route_bad.get("channels") == [], str(route_bad.get("channels")))

    # Deliver: stop after success (no multi-send).
    os.environ["CALENDAR_DELIVERY_DRY_RUN"] = "true"
    deliver_legacy = FakeLegacy(
        {
            "external_guest": {
                "preferred_channels": ["email"],
                "fallback_channels": ["whatsapp"],
                "enabled_channels": ["email", "whatsapp"],
            }
        }
    )
    delivered = comm.deliver_intent(
        deliver_legacy,
        {
            "company_code": "DEMOCO",
            "purpose": "calendar_invitation",
            "recipient_type": "external_guest",
            "recipient": {"email": "guest@example.com", "phone": "96550000000"},
            "event_id": str(uuid4()),
            "payload": {"title": "Demo", "message": "Hello"},
            "idempotency_key": f"t-{uuid4()}",
        },
    )
    check("live email handoff ok", delivered.get("ok") is True and delivered.get("channel_used") == "email")
    check("fallback stops after success", delivered.get("fallback_used") is False)
    check("email adapter called once", len(deliver_legacy.email_calls) == 1)
    check("whatsapp not called after email success", len(deliver_legacy.whatsapp_calls) == 0)

    # WhatsApp path includes account_id + company_code
    wa_legacy = FakeLegacy(
        {
            "pre_hire": {
                "preferred_channels": ["whatsapp"],
                "fallback_channels": [],
                "enabled_channels": ["whatsapp"],
            }
        }
    )
    wa = comm.deliver_intent(
        wa_legacy,
        {
            "company_code": "TENANTA",
            "purpose": "calendar_invitation",
            "recipient_type": "candidate",
            "recipient": {"phone": "96551111111", "app_key": "app1"},
            "event_id": str(uuid4()),
            "payload": {"title": "Interview"},
            "idempotency_key": f"wa-{uuid4()}",
        },
    )
    check("whatsapp handoff ok", wa.get("ok") is True and wa.get("channel_used") == "whatsapp")
    check("whatsapp company_code threaded", wa_legacy.whatsapp_calls and wa_legacy.whatsapp_calls[0].get("company_code") == "TENANTA")
    check("whatsapp account_id present", bool(wa_legacy.whatsapp_calls[0].get("account_id")))

    # Calendar must not call providers directly.
    src = Path(part.__file__).read_text()
    check("calendar has no direct send_octopus_whatsapp", "send_octopus_whatsapp(" not in src)
    check("calendar uses wathefni_communication", "wathefni_communication" in src)
    check("calendar outbox uses routed handoff", 'channel="routed"' in src or "\"routed\"" in src)

    # No office/frontline hardcode in router.
    router_src = Path(comm.__file__).read_text()
    check("no frontline assumption in router", "frontline" not in router_src.lower())
    check("no office/frontline channel preset in router", "NOTIFICATION_PRESET" not in router_src)

    print(f"=== communication smoke done PASS={PASS} FAIL={FAIL} ===")
    return 0 if FAIL == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
