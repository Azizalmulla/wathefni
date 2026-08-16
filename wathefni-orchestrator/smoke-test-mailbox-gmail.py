"""Step 3 behaviour test for the Gmail adapter (no real Google/Gmail calls).

Wathefni owns ALL import logic; `gog` is only a stateless transport. This test
mocks the `gog` subprocess and the OAuth token mint so it never touches the
network, then proves:
  - GmailProvider parses search -> get -> attachment into the neutral message shape
  - live legacy mailbox sync fails closed before candidate/import mutation
  - the access token travels ONLY via $GOG_ACCESS_TOKEN env, never argv/results
  - OAuth state signing round-trips and rejects tampered/expired state
  - label listing parses and failures fail closed to needs_reconnect

Run on a host with the orchestrator venv + database, e.g.:
  /opt/wathefni/staging/orchestrator/.venv/bin/python smoke-test-mailbox-gmail.py
"""

from __future__ import annotations

import json
import os
import types
from pathlib import Path

os.environ["WATHEFNI_MAILBOX_SYNC"] = "on"
os.environ.setdefault("WATHEFNI_MAILBOX_SECRET_KEY", "")

import app  # noqa: E402

# Ensure a real encryption key exists for credential storage.
if not app.mailbox_encryption_available():
    os.environ["WATHEFNI_MAILBOX_SECRET_KEY"] = app.generate_mailbox_secret_key()

COMPANY = "MGMAILALPHA"
MARKER = "temporary_gmail_adapter_smoke"
ACCESS_TOKEN = "test-access-token-SECRET"

_app_keys: list[str] = []
_surrogates: list[str] = []
_gog_calls: list[dict] = []

_ALI = b"Ali Hassan\nSenior Welder\nEmail: ali@example.com\nExperience: 8 years.\n"
_SARA = b"Sara Noor\nQA Engineer\nEmail: sara@example.com\nExperience: 5 years.\n"


def assert_true(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def _gmail_message_resource(message_id: str, sender: str, subject: str, cv_filename: str) -> dict:
    return {
        "id": message_id,
        "internalDate": "1748736000000",  # ms epoch
        "payload": {
            "headers": [
                {"name": "From", "value": sender},
                {"name": "Subject", "value": subject},
                {"name": "Date", "value": "Mon, 01 Jun 2026 00:00:00 +0000"},
            ],
            "parts": [
                {"mimeType": "text/plain", "filename": "", "body": {"size": 10}},
                {"mimeType": "application/pdf", "filename": cv_filename, "body": {"attachmentId": f"att-{message_id}"}},
                {"mimeType": "application/octet-stream", "filename": "logo.bin", "body": {"attachmentId": f"junk-{message_id}"}},
            ],
        },
    }


_ATTACHMENT_BYTES = {"att-m1": _ALI, "att-m2": _SARA}


def _fake_gog(cmd, **kwargs):
    """Stand-in for `gog`. Records the call (incl. token location) and returns
    canned JSON for each read-only subcommand."""
    env = kwargs.get("env") or {}
    _gog_calls.append({"cmd": list(cmd), "env_token": env.get("GOG_ACCESS_TOKEN")})
    proc = types.SimpleNamespace(returncode=0, stdout="", stderr="")
    sub = cmd[2] if len(cmd) > 2 else ""
    if sub == "search":
        proc.stdout = json.dumps({"messages": [{"id": "m1"}, {"id": "m2"}]})
    elif sub == "get":
        mid = cmd[3]
        sender = "Ali Hassan <ali@example.com>" if mid == "m1" else "Sara Noor <sara@example.com>"
        fname = "Ali_CV.pdf" if mid == "m1" else "Sara_CV.pdf"
        proc.stdout = json.dumps(_gmail_message_resource(mid, sender, "My CV", fname))
    elif sub == "attachment":
        att_id = cmd[4]
        out = cmd[cmd.index("--out") + 1]
        Path(out).write_bytes(_ATTACHMENT_BYTES.get(att_id, b"x"))
        proc.stdout = "{}"
    elif sub == "labels":
        proc.stdout = json.dumps({"labels": [
            {"id": "Label_1", "name": "Recruitment/CVs", "type": "user"},
            {"id": "INBOX", "name": "INBOX", "type": "system"},
            {"id": "SENT", "name": "SENT", "type": "system"},
        ]})
    return proc


def setup() -> None:
    with app.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO companies (company_code, name, metadata, raw_json, created_at, updated_at) "
                "VALUES (%s,%s,%s,%s,now(),now()) ON CONFLICT (company_code) DO NOTHING",
                (COMPANY, "Gmail Adapter Smoke", app.Json({"smoke": MARKER}), app.Json({"smoke": MARKER})),
            )
        conn.commit()


def _connect_live_gmail(email: str = "careers@mgmailalpha.example") -> str:
    row = app.create_mailbox_connection(company_code=COMPANY, provider="gmail", email_address=email, label_filter="Recruitment/CVs")
    mailbox_id = row["mailbox_id"]
    app.set_mailbox_credential(company_code=COMPANY, mailbox_id=mailbox_id, secret_value="fake-refresh-token", secret_type="oauth_refresh_token")
    with app.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute("UPDATE mailbox_connections SET sync_enabled=true, status='connected', sync_mode='live' WHERE mailbox_id=%s", (mailbox_id,))
        conn.commit()
    return mailbox_id


def _collect(result: dict) -> None:
    for it in result.get("items", []):
        if it.get("app_key"):
            _app_keys.append(it["app_key"])
        if it.get("surrogate_phone"):
            _surrogates.append(it["surrogate_phone"])


def teardown() -> None:
    with app.db_connect() as conn:
        with conn.cursor() as cur:
            if _app_keys:
                cur.execute("DELETE FROM candidate_documents WHERE app_key = ANY(%s)", (_app_keys,))
                cur.execute("DELETE FROM file_registry WHERE subject_key = ANY(%s)", (_app_keys,))
                cur.execute("DELETE FROM applications WHERE app_key = ANY(%s)", (_app_keys,))
            if _surrogates:
                cur.execute("DELETE FROM candidates WHERE phone = ANY(%s)", (_surrogates,))
            cur.execute("DELETE FROM import_batches WHERE company_code=%s", (COMPANY,))
            cur.execute("DELETE FROM mailbox_connections WHERE company_code=%s", (COMPANY,))
            cur.execute("DELETE FROM companies WHERE company_code=%s", (COMPANY,))
        conn.commit()


def check_oauth_state() -> None:
    payload = {"company_code": COMPANY, "mailbox_id": "abc", "nonce": "n", "exp": int(app.time_module.time()) + 600}
    state = app.sign_mailbox_oauth_state(payload)
    decoded = app.verify_mailbox_oauth_state(state)
    assert_true(decoded and decoded["mailbox_id"] == "abc", "state must round-trip")
    assert_true(app.verify_mailbox_oauth_state(state + "x") is None, "tampered state must be rejected")
    expired = app.sign_mailbox_oauth_state({**payload, "exp": int(app.time_module.time()) - 5})
    assert_true(app.verify_mailbox_oauth_state(expired) is None, "expired state must be rejected")


def check_token_mint(real_mint) -> None:
    # Exercise the REAL mint with the Google token endpoint mocked (no network).
    app.mint_google_access_token = real_mint
    os.environ["WATHEFNI_GMAIL_CLIENT_ID"] = "test-client-id"
    os.environ["WATHEFNI_GMAIL_CLIENT_SECRET"] = "test-client-secret"
    saved = app._google_token_request
    try:
        app._google_token_request = lambda form: {"access_token": "minted-xyz"}
        assert_true(app.mint_google_access_token("rt") == "minted-xyz", "mint must return the access token")
        app._google_token_request = lambda form: {}
        raised = False
        try:
            app.mint_google_access_token("rt")
        except RuntimeError:
            raised = True
        assert_true(raised, "missing access_token must raise")
    finally:
        app._google_token_request = saved
        os.environ.pop("WATHEFNI_GMAIL_CLIENT_ID", None)
        os.environ.pop("WATHEFNI_GMAIL_CLIENT_SECRET", None)


def run_checks() -> None:
    check_oauth_state()

    real_run = app.subprocess.run
    real_mint = app.mint_google_access_token
    real_token_request = app._google_token_request
    app.subprocess.run = _fake_gog
    app.mint_google_access_token = lambda refresh_token: ACCESS_TOKEN
    try:
        mailbox = _connect_live_gmail()
        connection = app.get_mailbox_connection(COMPANY, mailbox)
        provider = app.build_mailbox_provider(connection)
        messages, next_cursor = provider.fetch_new_messages(
            connection=connection,
            cursor={},
        )
        assert_true(len(messages) == 2, "Gmail transport must parse two messages")
        assert_true(
            [a["filename"] for m in messages for a in m["attachments"]]
            == ["Ali_CV.pdf", "Sara_CV.pdf"],
            "Gmail transport must include only CV attachments",
        )
        assert_true(
            next_cursor["after_epoch"] == 1748736000,
            "Gmail transport must return the provider cursor",
        )

        # Live legacy sync cannot attach those files until migrated to durable intake.
        r1 = app.run_mailbox_sync(COMPANY, mailbox, "manual")
        assert_true(
            not r1["ok"]
            and r1["error"] == "durable_scan_and_identity_authority_required",
            "live Gmail sync must fail closed at the authority boundary",
        )
        with app.db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT count(*) AS c FROM import_batches WHERE mailbox_id=%s",
                    (mailbox,),
                )
                assert_true(cur.fetchone()["c"] == 0, "blocked Gmail sync creates no import batch")
                cur.execute(
                    "SELECT count(*) AS c FROM applications WHERE company_code=%s",
                    (COMPANY,),
                )
                assert_true(cur.fetchone()["c"] == 0, "blocked Gmail sync creates no candidate application")
                cur.execute(
                    "SELECT cursor FROM mailbox_connections WHERE mailbox_id=%s",
                    (mailbox,),
                )
                assert_true(cur.fetchone()["cursor"] == {}, "blocked Gmail sync does not advance cursor")

        # Token hygiene: token only ever travels via env, never argv.
        assert_true(_gog_calls, "gog must have been invoked")
        for call in _gog_calls:
            assert_true(call["env_token"] == ACCESS_TOKEN, "token must be passed via $GOG_ACCESS_TOKEN")
            assert_true(ACCESS_TOKEN not in " ".join(call["cmd"]), "token must never appear in argv")
            assert_true("--enable-commands" in call["cmd"], "CLI must be restricted to gmail commands")
        # Token must not leak into the public connection serializer.
        public = app.mailbox_connection_ui(app.get_mailbox_connection(COMPANY, mailbox))
        assert_true(ACCESS_TOKEN not in json.dumps(public) and "cursor" not in public and "fake-refresh-token" not in json.dumps(public), "no secrets in public serializer")

        # Labels: parsed for the picker; failures fail closed.
        labels = app.gmail_list_labels_safe(COMPANY, mailbox)
        assert_true(labels["ok"] and "Recruitment/CVs" in labels["labels"], "label list must parse")

        # Provider/auth failure in label access remains calm and secret-free.
        app.mint_google_access_token = lambda refresh_token: (_ for _ in ()).throw(RuntimeError("google_token_failed:401"))
        lab_fail = app.gmail_list_labels_safe(COMPANY, mailbox)
        assert_true(not lab_fail["ok"] and lab_fail["error"] == "mailbox_needs_reconnect", "label failure fails closed")

        check_token_mint(real_mint)
    finally:
        app.subprocess.run = real_run
        app.mint_google_access_token = real_mint
        app._google_token_request = real_token_request


def main() -> None:
    setup()
    try:
        run_checks()
    finally:
        teardown()
    print("gmail adapter smoke tests passed")


if __name__ == "__main__":
    main()
