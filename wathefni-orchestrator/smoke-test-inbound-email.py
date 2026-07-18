"""Behaviour test for inbound email intake (Postmark) — no network.

Builds Postmark inbound JSON payloads and drives process_postmark_inbound /
the secret verifier directly, proving inbound email feeds the SAME shared import
core and is safe:
  - recipient (envelope) -> company via intake_addresses (company scoping)
  - CV attachments imported into one email_inbound import_batch
  - imported candidates held in Import review / Needs role; excluded from Ranking
  - no candidate messages sent
  - idempotent on provider MessageID (webhook retries import nothing new)
  - unknown recipient -> rejected (no import); spam -> quarantined; no attachments -> note
  - unsupported attachment -> failed item (reported)
  - webhook secret verification (Basic Auth + ?token=) fails closed

Run on a host with the orchestrator venv + database, e.g.:
  /opt/wathefni/staging/orchestrator/.venv/bin/python smoke-test-inbound-email.py
"""

from __future__ import annotations

import base64
import os

os.environ["WATHEFNI_INBOUND_EMAIL"] = "on"
os.environ.setdefault("WATHEFNI_POSTMARK_INBOUND_SECRET", "smoke-secret-token")

import app  # noqa: E402

COMPANY_A = "INBOUNDALPHA"
COMPANY_B = "INBOUNDBRAVO"
MARKER = "temporary_inbound_email_smoke"

_app_keys: list[str] = []
_surrogates: list[str] = []


def assert_true(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def _cv_b64(name: str, email: str) -> str:
    return base64.b64encode(f"{name}\nSenior Welder\nEmail: {email}\n8 years NDT.\n".encode("utf-8")).decode("ascii")


def _payload(message_id: str, recipient: str, sender: str, attachments: list[dict], headers: list[dict] | None = None) -> dict:
    email = app._parse_email_address(sender) or sender
    return {
        "MessageID": message_id,
        "OriginalRecipient": recipient,
        "From": sender,
        "FromFull": {"Email": email, "Name": sender.split("<")[0].strip()},
        "ToFull": [{"Email": recipient, "Name": "", "MailboxHash": ""}],
        "Subject": "My CV",
        "Date": "Mon, 01 Jun 2026 00:00:00 +0000",
        "Attachments": attachments,
        "Headers": headers or [],
    }


def _att(name: str, content_b64: str, ctype: str = "application/pdf") -> dict:
    return {"Name": name, "Content": content_b64, "ContentType": ctype, "ContentLength": len(content_b64)}


def _intake(company: str, local_part: str, domain: str | None = "inbound.wathefni.ai") -> str:
    with app.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO intake_addresses (company_code, local_part, domain) VALUES (%s,%s,%s) RETURNING intake_id::text",
                (company, local_part, domain),
            )
            intake_id = cur.fetchone()["intake_id"]
        conn.commit()
    return intake_id


def _collect(result: dict) -> None:
    for it in result.get("items", []):
        if it.get("app_key"):
            _app_keys.append(it["app_key"])
        if it.get("surrogate_phone"):
            _surrogates.append(it["surrogate_phone"])


def setup() -> None:
    with app.db_connect() as conn:
        with conn.cursor() as cur:
            for company in (COMPANY_A, COMPANY_B):
                cur.execute(
                    "INSERT INTO companies (company_code, name, metadata, raw_json, created_at, updated_at) "
                    "VALUES (%s,%s,%s,%s,now(),now()) ON CONFLICT (company_code) DO NOTHING",
                    (company, f"Inbound {company}", app.Json({"smoke": MARKER}), app.Json({"smoke": MARKER})),
                )
        conn.commit()


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
            cur.execute("DELETE FROM inbound_messages WHERE company_code = ANY(%s) OR company_code IS NULL AND envelope_recipient LIKE %s", ([COMPANY_A, COMPANY_B], "%inbound.wathefni.ai"))
            cur.execute("DELETE FROM intake_addresses WHERE company_code = ANY(%s)", ([COMPANY_A, COMPANY_B],))
            cur.execute("DELETE FROM companies WHERE company_code = ANY(%s)", ([COMPANY_A, COMPANY_B],))
        conn.commit()


def check_secret() -> None:
    secret = app.inbound_postmark_secret()
    basic = "Basic " + base64.b64encode(f"wathefni:{secret}".encode()).decode()
    assert_true(app._verify_postmark_secret(basic, None), "basic auth password must verify")
    assert_true(app._verify_postmark_secret(None, secret), "?token= must verify")
    assert_true(not app._verify_postmark_secret("Basic " + base64.b64encode(b"x:wrong").decode(), None), "wrong secret rejected")
    assert_true(not app._verify_postmark_secret(None, None), "no secret rejected")


def run_checks() -> None:
    check_secret()
    _intake(COMPANY_A, "alpha")
    _intake(COMPANY_B, "bravo")

    ali = _cv_b64("Ali Hassan", "ali@example.com")
    sara = _cv_b64("Sara Noor", "sara@example.com")

    # Run 1: two CVs + one duplicate + one unsupported, to the alpha intake.
    p1 = _payload(
        "pm-1", "alpha@inbound.wathefni.ai", "Ali Hassan <ali@example.com>",
        [_att("Ali_CV.pdf", ali), _att("logo.bin", base64.b64encode(b"not a cv").decode(), "application/octet-stream")],
    )
    r1 = app.process_postmark_inbound(p1)
    _collect(r1)
    assert_true(r1["counts"]["imported"] == 1 and r1["counts"]["failed"] == 1, f"expected 1 imported + 1 unsupported, got {r1['counts']}")
    assert_true(r1["counts"]["needs_role"] == 1, "inbound CV must land in needs_role")
    ali_app = {it["original_filename"]: it for it in r1["items"]}["Ali_CV.pdf"]["app_key"]

    with app.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT status FROM applications WHERE app_key=%s", (ali_app,))
            assert_true(cur.fetchone()["status"] == "needs_role", "held as needs_role")
            cur.execute("SELECT extraction_status FROM candidate_documents WHERE app_key=%s", (ali_app,))
            assert_true(cur.fetchone()["extraction_status"] == "pending_extraction", "CV doc pending for the worker")
            cur.execute("SELECT source, company_code FROM import_batches WHERE batch_id=%s", (r1["batch_id"],))
            brow = cur.fetchone()
            assert_true(brow["source"] == "email_inbound" and brow["company_code"] == COMPANY_A, "batch source/company correct")
            cur.execute("SELECT source_message_id, source_label FROM import_items WHERE app_key=%s", (ali_app,))
            prov = cur.fetchone()
            assert_true(prov["source_message_id"] == "pm-1" and prov["source_label"] == "alpha@inbound.wathefni.ai", "provenance stored")
            cur.execute("SELECT status, batch_id::text AS b FROM inbound_messages WHERE provider_message_id='pm-1'")
            inb = cur.fetchone()
            assert_true(inb["status"] == "processed" and inb["b"] == r1["batch_id"], "inbound ledger processed + linked")

    # No early Ranking; no candidate messaging.
    with app.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"SELECT COUNT(*) AS c FROM applications a WHERE a.company_code=%s AND a.app_key=%s AND {app.reviewable_application_predicate('a')}",
                (COMPANY_A, ali_app),
            )
            assert_true(cur.fetchone()["c"] == 0, "inbound imports excluded from Ranking")
            cur.execute("SELECT COUNT(*) AS c FROM outbound_delivery_events WHERE subject_key=%s", (ali_app,))
            assert_true(cur.fetchone()["c"] == 0, "inbound must never message candidates")

    # Idempotency: same MessageID reprocessed imports nothing new.
    r1b = app.process_postmark_inbound(p1)
    assert_true(r1b.get("duplicate") is True, "duplicate MessageID must be idempotent")

    # Company scoping: bravo intake imports under B only.
    rb = app.process_postmark_inbound(_payload("pm-2", "bravo@inbound.wathefni.ai", "X <x@b.example>", [_att("B_CV.pdf", _cv_b64("B Person", "x@b.example"))]))
    _collect(rb)
    b_app = {it["original_filename"]: it for it in rb["items"]}["B_CV.pdf"]["app_key"]
    with app.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT company_code FROM applications WHERE app_key=%s", (b_app,))
            assert_true(cur.fetchone()["company_code"] == COMPANY_B, "bravo import scoped to B")

    # Unknown recipient -> rejected, no import.
    ru = app.process_postmark_inbound(_payload("pm-3", "nobody@inbound.wathefni.ai", "Y <y@c.example>", [_att("C_CV.pdf", _cv_b64("C", "y@c.example"))]))
    assert_true(ru.get("ignored") == "unknown_recipient", "unknown recipient must be ignored")

    # Spam -> quarantined, no import.
    rs = app.process_postmark_inbound(_payload("pm-4", "alpha@inbound.wathefni.ai", "Spammer <s@x.example>", [_att("CV.pdf", sara)], headers=[{"Name": "X-Spam-Status", "Value": "Yes"}]))
    assert_true(rs.get("quarantined") is True, "spam must be quarantined")

    # No attachments -> note, no batch.
    rn = app.process_postmark_inbound(_payload("pm-5", "alpha@inbound.wathefni.ai", "Z <z@x.example>", []))
    assert_true(rn.get("note") == "no_attachments", "no-attachment mail must be noted, not imported")

    # Recipient resolution via Postmark mailbox hash slug (domain-agnostic intake).
    _intake(COMPANY_A, "hashslug", None)
    with app.db_connect() as conn:
        with conn.cursor() as cur:
            hit = app.resolve_intake_address(cur, "serverhash+hashslug@inbound.postmarkapp.com", "hashslug")
            assert_true(hit and hit["company_code"] == COMPANY_A, "mailbox hash must resolve to the intake company")


def main() -> None:
    setup()
    try:
        run_checks()
    finally:
        teardown()
    print("inbound email smoke tests passed")


if __name__ == "__main__":
    main()
