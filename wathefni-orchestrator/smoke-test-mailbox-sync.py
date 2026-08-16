"""Step 2 behaviour test for run_mailbox_sync (no real Google/Gmail calls).

Uses an in-memory provider to prove the legacy mailbox path fails closed before
fetching or mutating candidates. Dry-run inspection remains read-only, and the
master flag still disables mailbox checks.

Run on a host with the orchestrator venv + database, e.g.:
  /opt/wathefni/staging/orchestrator/.venv/bin/python smoke-test-mailbox-sync.py
"""

from __future__ import annotations

import os

import app

os.environ["WATHEFNI_MAILBOX_SYNC"] = "on"
os.environ.setdefault("WATHEFNI_MAILBOX_SECRET_KEY", app.generate_mailbox_secret_key())

COMPANY_A = "MSYNCALPHA"
COMPANY_B = "MSYNCBRAVO"
MARKER = "temporary_mailbox_sync_smoke"

_app_keys: list[str] = []
_surrogates: list[str] = []


def assert_true(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def _cv_bytes(name: str, email: str) -> bytes:
    return (f"{name}\nSenior Welder\nEmail: {email}\nExperience: 8 years, NDT certified.\n").encode("utf-8")


class FakeMailboxProvider:
    """Minimal fixture: returns messages whose index is beyond the stored cursor."""

    def __init__(self, messages: list[dict], *, ignore_cursor: bool = False) -> None:
        self._messages = messages
        self._ignore_cursor = ignore_cursor

    def fetch_new_messages(self, *, connection, cursor):
        start = 0 if self._ignore_cursor else int((cursor or {}).get("idx", 0))
        new = self._messages[start:]
        return new, {"idx": len(self._messages)}


def _msg(message_id: str, sender: str, subject: str, attachments: list[dict]) -> dict:
    return {"message_id": message_id, "sender": sender, "subject": subject, "label": "Recruitment/CVs", "received_at": "2026-06-01T00:00:00Z", "attachments": attachments}


def setup() -> None:
    with app.db_connect() as conn:
        with conn.cursor() as cur:
            for company in (COMPANY_A, COMPANY_B):
                cur.execute(
                    "INSERT INTO companies (company_code, name, metadata, raw_json, created_at, updated_at) "
                    "VALUES (%s,%s,%s,%s,now(),now()) ON CONFLICT (company_code) DO NOTHING",
                    (company, f"Mailbox Sync {company}", app.Json({"smoke": MARKER}), app.Json({"smoke": MARKER})),
                )
        conn.commit()


def _connect_mailbox(company: str, *, live: bool, email: str | None = None) -> str:
    conn_row = app.create_mailbox_connection(company_code=company, provider="gmail", email_address=email or f"careers@{company.lower()}.example", label_filter="Recruitment/CVs")
    mailbox_id = conn_row["mailbox_id"]
    with app.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE mailbox_connections SET sync_enabled=true, status='connected', sync_mode=%s WHERE mailbox_id=%s",
                ("live" if live else "dry_run", mailbox_id),
            )
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
            cur.execute("DELETE FROM import_batches WHERE company_code = ANY(%s)", ([COMPANY_A, COMPANY_B],))
            cur.execute("DELETE FROM mailbox_connections WHERE company_code = ANY(%s)", ([COMPANY_A, COMPANY_B],))
            cur.execute("DELETE FROM companies WHERE company_code = ANY(%s)", ([COMPANY_A, COMPANY_B],))
        conn.commit()


def run_checks() -> None:
    ali = _cv_bytes("Ali Hassan", "ali@example.com")
    mailbox_a = _connect_mailbox(COMPANY_A, live=True)
    messages = [
        _msg("m1", "Ali Hassan <ali@example.com>", "My CV", [{"filename": "Ali_CV.txt", "data": ali, "mime_type": "text/plain"}]),
    ]
    provider = FakeMailboxProvider(messages)

    # Live legacy sync must stop before provider fetch or any import mutation.
    r1 = app.run_mailbox_sync(COMPANY_A, mailbox_a, "manual", provider=provider)
    assert_true(
        not r1["ok"]
        and r1["error"] == "durable_scan_and_identity_authority_required",
        "live legacy mailbox sync must fail closed",
    )
    with app.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT count(*) AS c FROM import_batches WHERE mailbox_id=%s",
                (mailbox_a,),
            )
            assert_true(cur.fetchone()["c"] == 0, "blocked sync creates no import batch")
            cur.execute(
                "SELECT cursor FROM mailbox_connections WHERE mailbox_id=%s",
                (mailbox_a,),
            )
            assert_true(cur.fetchone()["cursor"] == {}, "blocked sync does not advance cursor")
            cur.execute(
                "SELECT count(*) AS c FROM applications WHERE company_code=%s",
                (COMPANY_A,),
            )
            assert_true(cur.fetchone()["c"] == 0, "blocked sync creates no application")

    # Tenant scoping remains enforced before the authority response.
    assert_true(app.get_mailbox_connection(COMPANY_B, mailbox_a) is None, "company B must not fetch company A's mailbox")

    # Dry-run mode writes nothing and does not advance the cursor.
    mailbox_dry = _connect_mailbox(COMPANY_A, live=False, email="dryrun@msyncalpha.example")
    rd = app.run_mailbox_sync(COMPANY_A, mailbox_dry, "manual", provider=FakeMailboxProvider([messages[0]]))
    assert_true(rd["ok"] and rd.get("dry_run") and rd["would_import"] == 1, "dry run must report would_import without writing")
    with app.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) AS c FROM import_batches WHERE mailbox_id=%s", (mailbox_dry,))
            assert_true(cur.fetchone()["c"] == 0, "dry run must create no import batch")
            cur.execute("SELECT cursor FROM mailbox_connections WHERE mailbox_id=%s", (mailbox_dry,))
            assert_true(cur.fetchone()["cursor"] == {}, "dry run must not advance the cursor")

    # Master flag OFF disables sync entirely.
    saved = os.environ.pop("WATHEFNI_MAILBOX_SYNC", None)
    try:
        off = app.run_mailbox_sync(COMPANY_A, mailbox_a, "manual", provider=provider)
        assert_true(off.get("skipped") == "mailbox_sync_disabled", "sync must be disabled when the master flag is off")
    finally:
        if saved is not None:
            os.environ["WATHEFNI_MAILBOX_SYNC"] = saved


def main() -> None:
    setup()
    try:
        run_checks()
    finally:
        teardown()
    print("mailbox sync smoke tests passed")


if __name__ == "__main__":
    main()
