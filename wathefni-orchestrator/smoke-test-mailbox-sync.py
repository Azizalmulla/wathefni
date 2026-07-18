"""Step 2 behaviour test for run_mailbox_sync (no real Google/Gmail calls).

Uses a tiny in-memory fake provider (a test fixture, NOT a fake Gmail) to prove the
sync core feeds the SAME shared import core as bulk upload and is safe:
  - run_mailbox_sync imports CV attachments into a single email import_batch
  - cursor advances; re-running imports nothing new (cursor + checksum dedupe)
  - company_code scoping (one company's sync never touches another's)
  - imported candidates are held in Import review / Needs role
  - held imports never enter Ranking
  - sync never sends a candidate message
  - dry_run mode writes nothing; master flag OFF disables sync

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
    sara = _cv_bytes("Sara Noor", "sara@example.com")

    mailbox_a = _connect_mailbox(COMPANY_A, live=True)
    messages = [
        _msg("m1", "Ali Hassan <ali@example.com>", "My CV", [{"filename": "Ali_CV.txt", "data": ali, "mime_type": "text/plain"}]),
        _msg("m2", "Sara Noor <sara@example.com>", "Application", [
            {"filename": "Sara_CV.txt", "data": sara, "mime_type": "text/plain"},
            {"filename": "Sara_CV_again.txt", "data": sara, "mime_type": "text/plain"},  # identical -> in-batch duplicate
            {"filename": "signature.bin", "data": b"not a cv", "mime_type": "application/octet-stream"},  # unsupported
        ]),
    ]
    provider = FakeMailboxProvider(messages)

    # Run 1: imports Ali + Sara, flags the duplicate and the unsupported file.
    r1 = app.run_mailbox_sync(COMPANY_A, mailbox_a, "manual", provider=provider)
    _collect(r1)
    assert_true(r1["ok"] and not r1.get("dry_run"), "live sync should run")
    assert_true(r1["counts"]["imported"] == 2, f"expected 2 imported, got {r1['counts']['imported']}")
    assert_true(r1["counts"]["duplicate"] == 1, f"expected 1 in-batch duplicate, got {r1['counts']['duplicate']}")
    assert_true(r1["counts"]["failed"] == 1, f"expected 1 unsupported, got {r1['counts']['failed']}")
    assert_true(r1["counts"]["needs_role"] == 2, "emailed CVs must land in needs_role")

    by_file = {it["original_filename"]: it for it in r1["items"]}
    ali_app = by_file["Ali_CV.txt"]["app_key"]
    sara_app = by_file["Sara_CV.txt"]["app_key"]

    with app.db_connect() as conn:
        with conn.cursor() as cur:
            # Holdout + email provenance + batch source.
            cur.execute("SELECT status FROM applications WHERE app_key=%s", (ali_app,))
            assert_true(cur.fetchone()["status"] == "needs_role", "emailed candidate must be held as needs_role")
            cur.execute("SELECT extraction_status FROM candidate_documents WHERE app_key=%s", (ali_app,))
            assert_true(cur.fetchone()["extraction_status"] == "pending_extraction", "emailed CV doc must be pending for the worker")
            cur.execute("SELECT source FROM import_batches WHERE batch_id=%s", (r1["batch_id"],))
            assert_true(cur.fetchone()["source"] == "email", "batch source must be email")
            cur.execute("SELECT source_message_id, source_sender FROM import_items WHERE app_key=%s", (ali_app,))
            prov = cur.fetchone()
            assert_true(prov["source_message_id"] == "m1" and "ali@example.com" in (prov["source_sender"] or ""), "email provenance must be stored on the item")
            # Cursor advanced.
            cur.execute("SELECT cursor->>'idx' AS idx, status FROM mailbox_connections WHERE mailbox_id=%s", (mailbox_a,))
            cur_row = cur.fetchone()
            assert_true(cur_row["idx"] == "2" and cur_row["status"] == "connected", "cursor must advance and status stay connected")

    # No early Ranking: held imports are excluded by the ranking predicate.
    with app.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"SELECT COUNT(*) AS c FROM applications a WHERE a.company_code=%s AND a.app_key=ANY(%s) AND {app.reviewable_application_predicate('a')}",
                (COMPANY_A, [ali_app, sara_app]),
            )
            assert_true(cur.fetchone()["c"] == 0, "emailed imports must be excluded from Ranking")
            # No candidate messaging during sync.
            cur.execute("SELECT COUNT(*) AS c FROM outbound_delivery_events WHERE subject_key = ANY(%s)", ([ali_app, sara_app],))
            assert_true(cur.fetchone()["c"] == 0, "sync must never message candidates")

    # Not in the live pipeline list.
    listing = app.prehire_applications_query(company_code=COMPANY_A, status=None, position=None, search=None, limit=200, offset=0)
    listed = {a.get("app_key") for a in listing.get("applications", [])}
    assert_true(ali_app not in listed and sara_app not in listed, "held emailed imports must not show in the pipeline list")

    # Run 2: cursor has advanced -> provider returns nothing -> nothing imported.
    r2 = app.run_mailbox_sync(COMPANY_A, mailbox_a, "scheduled", provider=provider)
    _collect(r2)
    assert_true(r2["ok"] and r2["messages"] == 0 and r2["counts"]["imported"] == 0, "second run must import nothing new (cursor)")

    # Run 3: replay the SAME message ignoring the cursor -> checksum dedupe blocks reimport.
    replay = FakeMailboxProvider([messages[0]], ignore_cursor=True)
    r3 = app.run_mailbox_sync(COMPANY_A, mailbox_a, "manual", provider=replay)
    _collect(r3)
    assert_true(r3["counts"]["imported"] == 0 and r3["counts"]["duplicate"] == 1, "replayed message must be deduped, not reimported")

    # Company scoping: B never sees A's mailbox or A's held imports.
    assert_true(app.get_mailbox_connection(COMPANY_B, mailbox_a) is None, "company B must not fetch company A's mailbox")
    mailbox_b = _connect_mailbox(COMPANY_B, live=True)
    rb = app.run_mailbox_sync(COMPANY_B, mailbox_b, "manual", provider=FakeMailboxProvider([_msg("b1", "X <x@b.example>", "CV", [{"filename": "B_CV.txt", "data": _cv_bytes("B Person", "x@b.example"), "mime_type": "text/plain"}])]))
    _collect(rb)
    b_app = {it["original_filename"]: it for it in rb["items"]}["B_CV.txt"]["app_key"]
    with app.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT company_code FROM applications WHERE app_key=%s", (b_app,))
            assert_true(cur.fetchone()["company_code"] == COMPANY_B, "company B's import must be scoped to B")
            cur.execute("SELECT COUNT(*) AS c FROM applications WHERE company_code=%s AND app_key=ANY(%s)", (COMPANY_B, [ali_app, sara_app]))
            assert_true(cur.fetchone()["c"] == 0, "company A's imports must never appear under company B")

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
