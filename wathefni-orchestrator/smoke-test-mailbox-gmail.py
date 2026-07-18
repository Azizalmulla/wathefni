"""Step 3 behaviour test for the Gmail adapter (no real Google/Gmail calls).

Wathefni owns ALL import logic; `gog` is only a stateless transport. This test
mocks the `gog` subprocess and the OAuth token mint so it never touches the
network, then proves:
  - GmailProvider parses search -> get -> attachment into the neutral message shape
  - run_mailbox_sync(GmailProvider) feeds the SAME shared import core
  - emailed CVs are held in Needs role and excluded from Ranking
  - cursor advances; re-running dedupes by checksum (no double import)
  - a provider/auth failure maps to a calm "needs reconnecting" (no raw error)
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

        # Run 1: GmailProvider resolved by build_mailbox_provider; imports 2 CVs.
        r1 = app.run_mailbox_sync(COMPANY, mailbox, "manual")
        _collect(r1)
        assert_true(r1["ok"] and not r1.get("dry_run"), "live gmail sync should run")
        assert_true(r1["counts"]["imported"] == 2, f"expected 2 imported, got {r1['counts']}")
        assert_true(r1["counts"]["needs_role"] == 2, "emailed CVs must land in needs_role")
        # The junk .bin attachment is filtered before download (not even fetched).
        assert_true(all("junk-" not in c["cmd"][4] for c in _gog_calls if c["cmd"][2] == "attachment"), "non-CV attachments must not be downloaded")

        by_file = {it["original_filename"]: it for it in r1["items"]}
        ali_app = by_file["Ali_CV.pdf"]["app_key"]
        sara_app = by_file["Sara_CV.pdf"]["app_key"]

        with app.db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT status FROM applications WHERE app_key=%s", (ali_app,))
                assert_true(cur.fetchone()["status"] == "needs_role", "emailed candidate held as needs_role")
                cur.execute("SELECT extraction_status FROM candidate_documents WHERE app_key=%s", (ali_app,))
                assert_true(cur.fetchone()["extraction_status"] == "pending_extraction", "CV doc pending for the worker")
                cur.execute("SELECT source FROM import_batches WHERE batch_id=%s", (r1["batch_id"],))
                assert_true(cur.fetchone()["source"] == "email", "batch source must be email")
                cur.execute("SELECT source_message_id, source_sender, source_label FROM import_items WHERE app_key=%s", (ali_app,))
                prov = cur.fetchone()
                assert_true(prov["source_message_id"] == "m1" and "ali@example.com" in (prov["source_sender"] or ""), "email provenance stored")
                assert_true(prov["source_label"] == "Recruitment/CVs", "label provenance stored")
                cur.execute("SELECT cursor->>'after_epoch' AS a, status FROM mailbox_connections WHERE mailbox_id=%s", (mailbox,))
                crow = cur.fetchone()
                assert_true(int(crow["a"]) == 1748736000 and crow["status"] == "connected", "cursor advances to internalDate seconds")

        # No early Ranking, no candidate messaging.
        with app.db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    f"SELECT COUNT(*) AS c FROM applications a WHERE a.company_code=%s AND a.app_key=ANY(%s) AND {app.reviewable_application_predicate('a')}",
                    (COMPANY, [ali_app, sara_app]),
                )
                assert_true(cur.fetchone()["c"] == 0, "emailed imports excluded from Ranking")
                cur.execute("SELECT COUNT(*) AS c FROM outbound_delivery_events WHERE subject_key = ANY(%s)", ([ali_app, sara_app],))
                assert_true(cur.fetchone()["c"] == 0, "sync must never message candidates")

        # Token hygiene: token only ever travels via env, never argv.
        assert_true(_gog_calls, "gog must have been invoked")
        for call in _gog_calls:
            assert_true(call["env_token"] == ACCESS_TOKEN, "token must be passed via $GOG_ACCESS_TOKEN")
            assert_true(ACCESS_TOKEN not in " ".join(call["cmd"]), "token must never appear in argv")
            assert_true("--enable-commands" in call["cmd"], "CLI must be restricted to gmail commands")
        # Token must not leak into the public connection serializer.
        public = app.mailbox_connection_ui(app.get_mailbox_connection(COMPANY, mailbox))
        assert_true(ACCESS_TOKEN not in json.dumps(public) and "cursor" not in public and "fake-refresh-token" not in json.dumps(public), "no secrets in public serializer")

        # Run 2: search returns the same ids, get returns same content -> checksum dedupe.
        r2 = app.run_mailbox_sync(COMPANY, mailbox, "manual")
        _collect(r2)
        assert_true(r2["counts"]["imported"] == 0 and r2["counts"]["duplicate"] == 2, f"re-sync must dedupe, got {r2['counts']}")

        # Labels: parsed for the picker; failures fail closed.
        labels = app.gmail_list_labels_safe(COMPANY, mailbox)
        assert_true(labels["ok"] and "Recruitment/CVs" in labels["labels"], "label list must parse")

        # Provider/auth failure -> calm needs_reconnect, generic error (no raw leak).
        app.mint_google_access_token = lambda refresh_token: (_ for _ in ()).throw(RuntimeError("google_token_failed:401"))
        fail = app.run_mailbox_sync(COMPANY, mailbox, "manual")
        assert_true(fail.get("error") == "mailbox_fetch_failed" and "401" not in json.dumps(fail), "auth failure maps to generic mailbox_fetch_failed")
        with app.db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT status FROM mailbox_connections WHERE mailbox_id=%s", (mailbox,))
                assert_true(cur.fetchone()["status"] == "needs_reconnect", "auth failure -> needs_reconnect")
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
