from __future__ import annotations

import app


def assert_true(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def main() -> None:
    # Canonical live Job application shape — authority gate must allow policy/router behavior.
    candidate = {
        "app_key": "96500000000-WATHEFNI-ACCOUNTING",
        "company_code": "WATHEFNI",
        "phone": "96500000000",
        "candidate_name": "Accounting Candidate",
        "candidate_email": "candidate@example.com",
        "position_title": "Accounting",
        "status": "screening",
        "data_source": "production",
    }
    original_email = app.send_email
    original_notify = app.notify_candidate
    calls: list[str] = []

    def fake_email(candidate_app, action):
        calls.append("email")
        return {"ok": True, "channel": "email", "candidate": app.candidate_contact(candidate_app), "action": action}

    def fake_notify(candidate_app, account_id, message=None):
        calls.append("whatsapp")
        return {"ok": False, "send": {"ok": False, "error": "conversation_closed"}, "message": message}

    try:
        app.send_email = fake_email
        app.notify_candidate = fake_notify
        result = app.candidate_communication_router(
            candidate,
            account_id="default",
            kind="notification",
            message="Hello",
            action={"preferred_channel": "whatsapp"},
        )
        assert_true(result["ok"] is True, "router must succeed when email fallback succeeds")
        assert_true(result["successful_channels"] == ["email"], "email must be recorded as fallback success")
        assert_true(result["fallback_used"] is True, "fallback_used must be true when WhatsApp fails and email succeeds")
        assert_true(calls == ["whatsapp", "email"], "router must try WhatsApp first, then email fallback")

        calls.clear()
        result = app.candidate_communication_router(candidate, account_id="default", kind="assessment", message="Assessment ready", action={})
        assert_true(calls == ["email", "whatsapp"], "assessment policy must attempt email and WhatsApp")
        assert_true(result["successful_channels"] == ["email"], "assessment email success must be preserved even if WhatsApp fails")

        held = {**candidate, "status": "needs_role"}
        denied = app.candidate_communication_router(
            held,
            account_id="default",
            kind="notification",
            message="Hello",
            action={"preferred_channel": "whatsapp"},
        )
        assert_true(denied.get("ok") is False, "held Talent Pool row must fail closed")
        assert_true(
            denied.get("error") == "held_record_communication_forbidden",
            "held denial must use held_record_communication_forbidden",
        )
        assert_true(calls == ["email", "whatsapp"], "held denial must not invoke providers")
    finally:
        app.send_email = original_email
        app.notify_candidate = original_notify

    print("communication router smoke tests passed")


if __name__ == "__main__":
    main()
