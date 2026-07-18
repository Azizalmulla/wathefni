"""Behaviour test for the provider-agnostic outbound candidate email layer.

Verifies (no real network, no real email sent):
  - WATHEFNI_OUTBOUND_EMAIL_PROVIDER resolution + safe fallback to gmail when
    postmark is requested but not configured
  - the Postmark sender shapes success / HTTP error / not-configured correctly
    (urlopen is mocked; nothing leaves the box)
  - dispatch_outbound_email routes to the selected provider
  - the gmail/gog fallback path still builds a `gmail send` command (Calendar/Meet
    is a separate gog surface and is never invoked here)
  - the Postmark delivery/bounce webhook secret verification
  - process_postmark_outbound_status records a company/subject-scoped audit event,
    linked back to the original send via message_id

Run on a host with the orchestrator venv + database:
  /opt/wathefni/orchestrator/.venv/bin/python smoke-test-outbound-email.py
"""

from __future__ import annotations

import io
import os
import urllib.error
import uuid

import app

KEY = f"TESTOUTBOUND-{uuid.uuid4().hex[:10]}"
MSGID = f"pm-{uuid.uuid4().hex[:12]}"
COMPANY = "OUTBOUNDTEST"


def assert_true(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


class _FakeResp:
    def __init__(self, body: bytes):
        self._body = body

    def read(self) -> bytes:
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def _patch_env(**values: str | None):
    """Set env vars (None clears) and return a restore callable."""
    previous = {k: os.environ.get(k) for k in values}

    def restore() -> None:
        for k, old in previous.items():
            if old is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = old

    for k, v in values.items():
        if v is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = v
    return restore


def check_provider_resolution() -> None:
    restore = _patch_env(
        WATHEFNI_OUTBOUND_EMAIL_PROVIDER=None,
        WATHEFNI_POSTMARK_SERVER_TOKEN=None,
        WATHEFNI_OUTBOUND_FROM=None,
    )
    try:
        assert_true(app.outbound_email_provider() == "gmail", "default provider must be gmail")
        os.environ["WATHEFNI_OUTBOUND_EMAIL_PROVIDER"] = "garbage"
        assert_true(app.outbound_email_provider() == "gmail", "unknown provider must fall back to gmail")
        os.environ["WATHEFNI_OUTBOUND_EMAIL_PROVIDER"] = "postmark"
        assert_true(app.outbound_email_provider() == "gmail", "postmark without config must fall back to gmail")
        os.environ["WATHEFNI_POSTMARK_SERVER_TOKEN"] = "test-token"
        os.environ["WATHEFNI_OUTBOUND_FROM"] = "recruitment@wathefni.ai"
        assert_true(app.outbound_postmark_available() is True, "postmark must report available with token + from")
        assert_true(app.outbound_email_provider() == "postmark", "postmark must be selected once configured")
    finally:
        restore()


def check_postmark_sender() -> None:
    restore = _patch_env(
        WATHEFNI_POSTMARK_SERVER_TOKEN="test-token",
        WATHEFNI_OUTBOUND_FROM="recruitment@wathefni.ai",
        WATHEFNI_OUTBOUND_REPLY_TO="",
        WATHEFNI_POSTMARK_MESSAGE_STREAM="outbound",
    )
    real_urlopen = app.urllib.request.urlopen
    try:
        # Success
        app.urllib.request.urlopen = lambda req, timeout=30: _FakeResp(b'{"MessageID":"abc-123","ErrorCode":0,"Message":"OK"}')
        out = app.send_email_via_postmark(to="cand@example.com", subject="Hi", body="Body")
        assert_true(out["ok"] and out["provider"] == "postmark", "successful postmark send must be ok")
        assert_true(out["message_id"] == "abc-123", f"message_id must be parsed, got {out['message_id']}")

        # API-level error (ErrorCode != 0)
        app.urllib.request.urlopen = lambda req, timeout=30: _FakeResp(b'{"ErrorCode":300,"Message":"Invalid email"}')
        out = app.send_email_via_postmark(to="bad", subject="Hi", body="Body")
        assert_true(not out["ok"] and out["error"], "postmark API error must be a failure with a safe message")

        # HTTP error
        def _raise_http(req, timeout=30):
            raise urllib.error.HTTPError(app.OUTBOUND_EMAIL_API, 422, "Unprocessable", {}, io.BytesIO(b'{"Message":"bad"}'))

        app.urllib.request.urlopen = _raise_http
        out = app.send_email_via_postmark(to="x@y.com", subject="Hi", body="Body")
        assert_true(not out["ok"] and out["error"].startswith("postmark_http_422"), f"HTTP error must map to a code, got {out['error']}")
    finally:
        app.urllib.request.urlopen = real_urlopen
        restore()

    # Not configured -> explicit, no network attempted.
    restore2 = _patch_env(WATHEFNI_POSTMARK_SERVER_TOKEN=None)
    try:
        out = app.send_email_via_postmark(to="x@y.com", subject="Hi", body="Body")
        assert_true(out["error"] == "postmark_not_configured", "missing token must short-circuit before any network call")
    finally:
        restore2()


def check_dispatch_routing() -> None:
    restore = _patch_env(
        WATHEFNI_OUTBOUND_EMAIL_PROVIDER="postmark",
        WATHEFNI_POSTMARK_SERVER_TOKEN="test-token",
        WATHEFNI_OUTBOUND_FROM="recruitment@wathefni.ai",
    )
    real_pm = app.send_email_via_postmark
    real_gog = app.send_email_via_gog
    try:
        calls: list[str] = []
        app.send_email_via_postmark = lambda **kw: (calls.append("postmark"), {"ok": True, "provider": "postmark"})[1]
        app.send_email_via_gog = lambda **kw: (calls.append("gmail"), {"ok": True, "provider": "gmail"})[1]
        app.dispatch_outbound_email(to="x@y.com", subject="s", body="b")
        assert_true(calls == ["postmark"], f"postmark provider must route to postmark, got {calls}")

        os.environ["WATHEFNI_OUTBOUND_EMAIL_PROVIDER"] = "gmail"
        calls.clear()
        app.dispatch_outbound_email(to="x@y.com", subject="s", body="b")
        assert_true(calls == ["gmail"], f"gmail provider must route to gog, got {calls}")
    finally:
        app.send_email_via_postmark = real_pm
        app.send_email_via_gog = real_gog
        restore()


def check_gog_fallback_uses_gmail_only() -> None:
    # The fallback path must build a `gmail send` command and never touch calendar.
    real_run_gog = app.run_gog
    real_env = app.openclaw_env
    try:
        captured: dict[str, list[str]] = {}
        app.openclaw_env = lambda: {"GOG_ACCOUNT": "recruitment@wathefni.ai"}
        app.run_gog = lambda args, timeout=60: (captured.__setitem__("args", args), {"ok": True, "json": {"id": "gmail-1"}})[1]
        out = app.send_email_via_gog(to="x@y.com", subject="s", body="b")
        assert_true(out["ok"] and out["provider"] == "gmail", "gog send must succeed + report gmail provider")
        assert_true(out["message_id"] == "gmail-1", "gmail message id must be parsed from gog json")
        assert_true(captured["args"][:2] == ["gmail", "send"], "fallback must use the gmail send subcommand")
        assert_true("calendar" not in captured["args"], "outbound email must never invoke gog calendar")
    finally:
        app.run_gog = real_run_gog
        app.openclaw_env = real_env


def check_webhook_secret() -> None:
    secret = "outbound-secret-xyz"
    assert_true(app._verify_postmark_token(None, secret, secret) is True, "matching ?token must verify")
    import base64

    basic = "Basic " + base64.b64encode(b"postmark:outbound-secret-xyz").decode()
    assert_true(app._verify_postmark_token(basic, None, secret) is True, "matching Basic auth password must verify")
    assert_true(app._verify_postmark_token(None, "wrong", secret) is False, "wrong token must be rejected")
    assert_true(app._verify_postmark_token(None, secret, "") is False, "no configured secret must fail closed")


def check_status_webhook_records_event() -> None:
    # Seed an original 'sent' email event so the status webhook can link back to it.
    app.record_outbound_delivery_event(
        account_id=None,
        target_phone=None,
        target_conversation_id=None,
        status="sent",
        message_text="Interview invite",
        last_error=None,
        payload={"message_id": MSGID, "provider": "postmark", "recipient_email": "cand@example.com"},
        subject_type="candidate",
        subject_key=KEY,
        channel="email",
        message_kind="email",
        company_code=COMPANY,
    )
    out = app.process_postmark_outbound_status({"RecordType": "Delivery", "MessageID": MSGID, "Recipient": "cand@example.com"})
    assert_true(out.get("status") == "delivered", f"Delivery webhook must map to delivered, got {out}")
    out_b = app.process_postmark_outbound_status({"RecordType": "Bounce", "MessageID": MSGID, "Recipient": "cand@example.com", "Description": "hard bounce"})
    assert_true(out_b.get("status") == "bounced", "Bounce webhook must map to bounced")
    out_ignored = app.process_postmark_outbound_status({"RecordType": "Open", "MessageID": MSGID})
    assert_true("ignored" in out_ignored, "non-delivery record types must be ignored")

    with app.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT status, company_code, subject_key FROM outbound_delivery_events "
                "WHERE subject_key=%s AND message_kind='email_status' ORDER BY created_at ASC",
                (KEY,),
            )
            rows = [dict(r) for r in cur.fetchall()]
    statuses = {r["status"] for r in rows}
    assert_true("delivered" in statuses and "bounced" in statuses, f"status events must be recorded, got {statuses}")
    assert_true(all(r["company_code"] == COMPANY for r in rows), "status events must inherit the original send's company scope")


def teardown() -> None:
    with app.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM outbound_delivery_events WHERE subject_key=%s", (KEY,))
        conn.commit()


def main() -> None:
    try:
        check_provider_resolution()
        check_postmark_sender()
        check_dispatch_routing()
        check_gog_fallback_uses_gmail_only()
        check_webhook_secret()
        check_status_webhook_records_event()
    finally:
        teardown()
    print("outbound email smoke tests passed")


if __name__ == "__main__":
    main()
