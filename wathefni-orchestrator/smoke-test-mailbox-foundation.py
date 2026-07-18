"""Step 1 behaviour test for the provider-agnostic mailbox ingestion foundation.

Validates the dark-shipped foundation WITHOUT any real Google/Gmail calls, polling,
or sync. It checks:
  - credential encryption round-trips and never stores/echoes plaintext
  - mailbox_connections / mailbox_credentials are company_code scoped
  - the public serializer never leaks ciphertext, cursor, or secrets
  - the 'email' import source is supported
  - schema tables/columns exist (connections, credentials, item provenance fields)
  - ingestion is OFF by default (master flag) and encryption fails closed without a key

Run on a host with the orchestrator venv + database, e.g.:
  /opt/wathefni/staging/orchestrator/.venv/bin/python smoke-test-mailbox-foundation.py
"""

from __future__ import annotations

import os

# Provide an encryption key for the test BEFORE exercising encrypt/decrypt. The
# helpers read the env at call time, so this is sufficient and isolated.
import app

os.environ["WATHEFNI_MAILBOX_SECRET_KEY"] = app.generate_mailbox_secret_key()

COMPANY_A = "MBOXALPHA"
COMPANY_B = "MBOXBRAVO"
MARKER = "temporary_mailbox_foundation_smoke"

_mailbox_ids: list[str] = []


def assert_true(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def setup() -> None:
    with app.db_connect() as conn:
        with conn.cursor() as cur:
            for company in (COMPANY_A, COMPANY_B):
                cur.execute(
                    "INSERT INTO companies (company_code, name, metadata, raw_json, created_at, updated_at) "
                    "VALUES (%s,%s,%s,%s,now(),now()) ON CONFLICT (company_code) DO NOTHING",
                    (company, f"Mailbox Smoke {company}", app.Json({"smoke": MARKER}), app.Json({"smoke": MARKER})),
                )
        conn.commit()


def teardown() -> None:
    with app.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM mailbox_connections WHERE company_code = ANY(%s)", ([COMPANY_A, COMPANY_B],))
            cur.execute("DELETE FROM companies WHERE company_code = ANY(%s)", ([COMPANY_A, COMPANY_B],))
        conn.commit()


def run_checks() -> None:
    # 1) Encryption round-trip; ciphertext must not reveal the plaintext.
    secret = "1//refresh-token-VERY-SECRET-value-abc123"
    enc = app.encrypt_mailbox_secret(secret)
    assert_true(enc["alg"] == "fernet" and enc["ciphertext"], "encrypt must return a fernet token")
    assert_true(secret not in enc["ciphertext"], "ciphertext must not contain the plaintext")
    assert_true(app.decrypt_mailbox_secret(enc["ciphertext"]) == secret, "decrypt must recover the plaintext")
    assert_true(enc["key_version"].startswith("fp_"), "key_version must be a key fingerprint, not the key itself")

    # 2) Create a company-scoped connection (no real provider calls).
    conn_a = app.create_mailbox_connection(
        company_code=COMPANY_A,
        provider="gmail",
        email_address="careers@alpha.example",
        label_filter="Recruitment/CVs",
        scopes=["https://www.googleapis.com/auth/gmail.readonly"],
        created_by_email="owner@alpha.example",
    )
    mailbox_id = conn_a["mailbox_id"]
    _mailbox_ids.append(mailbox_id)
    assert_true(conn_a["status"] == "disconnected", "new connection must start disconnected")
    assert_true(conn_a["sync_enabled"] is False, "sync must be disabled by default")
    assert_true(conn_a["sync_mode"] == "dry_run", "sync mode must default to dry_run")

    # 3) Store + retrieve an encrypted credential (decrypt only for in-process use).
    app.set_mailbox_credential(
        company_code=COMPANY_A, mailbox_id=mailbox_id, secret_value=secret,
        secret_type="oauth_refresh_token", token_meta={"token_type": "Bearer", "scope": "gmail.readonly", "refresh_token": "SHOULD_BE_DROPPED"},
    )
    assert_true(app.get_mailbox_credential(COMPANY_A, mailbox_id) == secret, "stored credential must decrypt back to the original")

    # token_meta must never persist secret-bearing keys.
    with app.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT ciphertext, token_meta FROM mailbox_credentials WHERE mailbox_id=%s", (mailbox_id,))
            row = cur.fetchone()
            assert_true(secret not in row["ciphertext"], "DB ciphertext must not contain plaintext")
            assert_true("refresh_token" not in (row["token_meta"] or {}), "token_meta must drop secret-bearing keys")

    # 4) Company scoping: company B cannot see or read company A's mailbox/credential.
    assert_true(app.list_mailbox_connections(COMPANY_B) == [], "company B must see no connections")
    assert_true(app.get_mailbox_connection(COMPANY_B, mailbox_id) is None, "company B must not fetch company A's mailbox")
    assert_true(app.get_mailbox_credential(COMPANY_B, mailbox_id) is None, "company B must not read company A's credential")
    try:
        app.set_mailbox_credential(company_code=COMPANY_B, mailbox_id=mailbox_id, secret_value="x")
        raise AssertionError("company B must not be able to write a credential to company A's mailbox")
    except ValueError as exc:
        assert_true("mailbox_not_found_for_company" in str(exc), "cross-company credential write must be refused")

    # 5) Public serializer must not leak ciphertext, cursor, or any secret.
    full = app.get_mailbox_connection(COMPANY_A, mailbox_id)
    public = app.mailbox_connection_public(full)
    blob = str(public).lower()
    assert_true("ciphertext" not in public and "cursor" not in public, "public view must omit cursor + ciphertext fields")
    assert_true(secret.lower() not in blob and "refresh" not in blob, "public view must not contain any secret material")
    assert_true(public["has_credentials"] is True and public["provider_label"] == "Gmail / Google Workspace", "public view exposes safe status only")

    # 6) 'email' is a first-class import source for the shared core.
    assert_true("email" in app.IMPORT_SOURCES, "email must be a supported import source")

    # 7) Schema presence: tables + provenance columns on import_items.
    with app.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT to_regclass('public.mailbox_connections') AS t1, to_regclass('public.mailbox_credentials') AS t2")
            reg = cur.fetchone()
            assert_true(reg["t1"] is not None and reg["t2"] is not None, "mailbox tables must exist")
            cur.execute(
                "SELECT column_name FROM information_schema.columns WHERE table_name='import_items' "
                "AND column_name = ANY(%s)",
                (["source_message_id", "source_sender", "source_received_at", "source_subject", "source_label"],),
            )
            cols = {r["column_name"] for r in cur.fetchall()}
            assert_true(cols == {"source_message_id", "source_sender", "source_received_at", "source_subject", "source_label"}, f"import_items must carry email provenance columns, got {cols}")

    # 8) Disconnect cascades the credential away.
    assert_true(app.delete_mailbox_connection(COMPANY_A, mailbox_id) is True, "disconnect must delete the connection")
    with app.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) AS c FROM mailbox_credentials WHERE mailbox_id=%s", (mailbox_id,))
            assert_true(cur.fetchone()["c"] == 0, "credentials must cascade-delete with the connection")
    _mailbox_ids.clear()

    # 9) Fail-closed: master flag OFF by default; encryption errors without a key.
    saved = os.environ.pop("WATHEFNI_MAILBOX_SYNC", None)
    try:
        assert_true(app.mailbox_ingestion_enabled() is False, "ingestion must be OFF by default")
    finally:
        if saved is not None:
            os.environ["WATHEFNI_MAILBOX_SYNC"] = saved
    saved_key = os.environ.pop("WATHEFNI_MAILBOX_SECRET_KEY", None)
    saved_fallback = os.environ.pop("WATHEFNI_SECRET_KEY", None)
    try:
        assert_true(app.mailbox_encryption_available() is False, "encryption must report unavailable without a key")
        try:
            app.encrypt_mailbox_secret("x")
            raise AssertionError("encrypt must fail closed without a key")
        except RuntimeError as exc:
            assert_true("mailbox_encryption_unavailable" in str(exc), "missing key must raise a clear error")
    finally:
        if saved_key is not None:
            os.environ["WATHEFNI_MAILBOX_SECRET_KEY"] = saved_key
        if saved_fallback is not None:
            os.environ["WATHEFNI_SECRET_KEY"] = saved_fallback


def main() -> None:
    setup()
    try:
        run_checks()
    finally:
        teardown()
    print("mailbox foundation smoke tests passed")


if __name__ == "__main__":
    main()
