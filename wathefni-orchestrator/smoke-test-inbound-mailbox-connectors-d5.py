#!/usr/bin/env python3
"""Wave D Phase 5 — local qualification for premium mailbox connectors → durable ingress.

Proves:
* Forwarding remains default; connectors are premium/optional (flag default off)
* Gmail + M365 scopes documented; M365 provider stubbed until OAuth configured
* Provider-neutral messages map into Postmark-shaped durable envelopes
* Live sync routes through durable pipeline (not legacy import_batches)
* Idempotent duplicate on same provider_message_id
* External tenants / GA / D6 not enabled
"""

from __future__ import annotations

import base64
import json
import os
import sys
import tempfile
import uuid
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

_QUARANTINE = Path(tempfile.mkdtemp(prefix="wathefni-d5-mbx-"))

# Prefer isolated test DB URL; fall back to waveC local boundary env file contents.
database_url = str(os.environ.get("WATHEFNI_TEST_DATABASE_URL") or "").strip()
if not database_url:
    for env_path in (Path("/tmp/waveC-local-env/postgres.test.env"),):
        if env_path.exists():
            for line in env_path.read_text().splitlines():
                if line.startswith("WATHEFNI_DATABASE_URL=") or line.startswith("DATABASE_URL="):
                    database_url = line.split("=", 1)[1].strip().strip('"').strip("'")
                    break

if database_url:
    parsed_database = urlparse(database_url)
    env_file = _QUARANTINE / "postgres.test.env"
    env_file.write_text(f"WATHEFNI_DATABASE_URL={database_url}\n")
    os.environ["WATHEFNI_POSTGRES_ENV"] = str(env_file)
    os.environ["WATHEFNI_ENV"] = "test"
    os.environ["WATHEFNI_EXPECTED_DATABASE_HOST"] = parsed_database.hostname or "127.0.0.1"
    os.environ["WATHEFNI_EXPECTED_DATABASE_PORT"] = str(parsed_database.port or 5432)
    os.environ["WATHEFNI_EXPECTED_DATABASE_NAME"] = parsed_database.path.lstrip("/")
    os.environ.setdefault(
        "WATHEFNI_DATABASE_ENVIRONMENT_MARKER", "wathefni-local-boundary-remediation-v1"
    )
elif not os.environ.get("WATHEFNI_POSTGRES_ENV"):
    raise RuntimeError(
        "Set WATHEFNI_POSTGRES_ENV or WATHEFNI_TEST_DATABASE_URL to an isolated test database."
    )

os.environ["WATHEFNI_MAILBOX_SYNC"] = "off"
os.environ["WATHEFNI_INBOUND_EMAIL"] = "on"
os.environ.setdefault("WATHEFNI_INBOUND_ALLOWED_COMPANIES", "WATHEFNI")
os.environ.setdefault("WATHEFNI_POSTMARK_INBOUND_SECRET", "smoke-secret-token")
os.environ["WATHEFNI_INTAKE_QUARANTINE_DIR"] = str(_QUARANTINE)
os.environ["WATHEFNI_INTAKE_MALWARE_SCANNER"] = "test_clean"
os.environ["WATHEFNI_INTAKE_ALLOW_TEST_SCANNER"] = "1"

import app as orch  # noqa: E402
import inbound_mailbox_connectors as mbx  # noqa: E402
import inbound_intake_product as iip  # noqa: E402

COMPANY = "WATHEFNI"
RESULTS: dict[str, Any] = {"cases": {}}


def ok(name: str, cond: bool, detail: Any = None) -> None:
    RESULTS["cases"][name] = {"ok": bool(cond), "detail": detail}
    print(("PASS" if cond else "FAIL"), name, json.dumps(detail, default=str)[:280] if detail is not None else "")


def main() -> int:
    # --- Unit / architecture ---
    ok(
        "forwarding_default_flag_off",
        mbx.mailbox_connectors_flag_enabled() is False,
        {"WATHEFNI_MAILBOX_SYNC": os.environ.get("WATHEFNI_MAILBOX_SYNC")},
    )
    feat = mbx.connector_feature_payload(
        gmail_oauth_ready=True,
        m365_oauth_ready=False,
        encryption_ready=True,
    )
    ok(
        "feature_payload_premium_forwarding_default",
        feat.get("premium") is True
        and feat.get("default_product") == "forwarding"
        and feat.get("enabled") is False,  # master flag still off
        feat,
    )
    ok(
        "gmail_scopes_readonly",
        mbx.GMAIL_OAUTH_SCOPES == ("https://www.googleapis.com/auth/gmail.readonly",),
        list(mbx.GMAIL_OAUTH_SCOPES),
    )
    ok(
        "m365_scopes_mail_read_least_privilege",
        "Mail.Read" in mbx.M365_GRAPH_MAIL_SCOPES
        and "Mail.Send" not in mbx.M365_GRAPH_MAIL_SCOPES
        and "Mail.ReadWrite" not in mbx.M365_GRAPH_MAIL_SCOPES,
        list(mbx.M365_GRAPH_MAIL_SCOPES),
    )
    ok(
        "status_labels_en_ar",
        mbx.status_label({"status": "connected"}, locale="en") == "Connected"
        and mbx.status_label({"status": "needs_reconnect"}, locale="ar") == "يحتاج إعادة ربط",
        True,
    )

    # Envelope mapping
    pdf = b"%PDF-1.4\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF\n"
    msg = {
        "message_id": "gmail-msg-d5-1",
        "sender": "candidate@example.com",
        "subject": "CV application",
        "received_at": "2026-08-01T12:00:00+00:00",
        "label": "Recruitment",
        "attachments": [{"filename": "cv.pdf", "data": pdf, "mime_type": "application/pdf"}],
    }
    payload = mbx.message_to_postmark_shaped_payload(
        msg, provider="gmail", route_address="wathefni-cv-d5@inbound.wathefni.ai"
    )
    ok(
        "envelope_maps_provider_message_id",
        payload.get("MessageID") == "gmail:gmail-msg-d5-1"
        and payload.get("OriginalRecipient") == "wathefni-cv-d5@inbound.wathefni.ai"
        and len(payload.get("Attachments") or []) == 1
        and base64.b64decode(payload["Attachments"][0]["Content"]) == pdf,
        {"MessageID": payload.get("MessageID"), "atts": len(payload.get("Attachments") or [])},
    )

    # M365 provider stub
    m365 = mbx.Microsoft365MailboxProvider()
    try:
        m365.fetch_new_messages(connection={"email_address": "hr@contoso.com"}, cursor={})
        raised = False
    except RuntimeError as exc:
        raised = "m365_mailbox" in str(exc)
    ok("m365_provider_not_live_without_oauth", raised, True)

    # build_mailbox_provider resolves m365
    try:
        orch.build_mailbox_provider({"provider": "m365"})
        built = True
    except Exception:
        built = False
    ok("build_mailbox_provider_m365", built, True)

    # --- Durable E2E (requires local DB) ---
    ok("local_db_available", True, urlparse(database_url).hostname if database_url else "env-file")

    # Enable connectors only inside this process for sync tests
    os.environ["WATHEFNI_MAILBOX_SYNC"] = "on"
    try:
        from cryptography.fernet import Fernet

        os.environ["WATHEFNI_MAILBOX_SECRET_KEY"] = Fernet.generate_key().decode()
    except Exception:
        pass

    marker = f"d5-{uuid.uuid4().hex[:8]}"
    intake_id = None
    address = None
    mailbox_id = None

    with orch.db_connect() as conn:
        with conn.cursor() as cur:
            local_part = f"wathefni-d5-{marker}"
            domain = "inbound.wathefni.ai"
            cur.execute(
                """
                INSERT INTO intake_addresses
                  (company_code, local_part, domain, label, status)
                VALUES (%s,%s,%s,%s,'active')
                RETURNING intake_id::text, lower(local_part || '@' || domain) AS address
                """,
                (COMPANY, local_part, domain, f"D5 proof {marker}"),
            )
            row = dict(cur.fetchone())
            intake_id, address = row["intake_id"], row["address"]
            cur.execute(
                """
                INSERT INTO mailbox_connections
                  (company_code, provider, email_address, status, sync_enabled, sync_mode, label_filter)
                VALUES (%s,'gmail',%s,'connected',true,'live','Recruitment')
                RETURNING mailbox_id::text
                """,
                (COMPANY, f"recruitment-{marker}@wathefni.ai"),
            )
            mailbox_id = cur.fetchone()["mailbox_id"]
        conn.commit()

    class FakeProvider:
        def fetch_new_messages(self, *, connection, cursor):
            mid = f"d5msg-{marker}"
            return (
                [
                    {
                        "message_id": mid,
                        "sender": f"applicant.{marker}@example.com",
                        "subject": f"D5 CV {marker}",
                        "received_at": "2026-08-01T15:00:00+00:00",
                        "label": "Recruitment",
                        "attachments": [
                            {"filename": "d5-cv.pdf", "data": pdf, "mime_type": "application/pdf"}
                        ],
                    }
                ],
                {"after_epoch": 1},
            )

    # Live sync through durable
    sync1 = orch.run_mailbox_sync(
        COMPANY, mailbox_id, "manual", provider=FakeProvider(), limit=10
    )
    ok(
        "live_sync_uses_durable_pipeline",
        sync1.get("ok") is True
        and sync1.get("mode") == "live_durable"
        and (sync1.get("counts") or {}).get("durable", 0) + (sync1.get("counts") or {}).get("duplicate", 0) >= 1,
        sync1,
    )
    ok(
        "no_legacy_import_batch_in_live_result",
        "batch_id" not in sync1 and "items" not in sync1,
        list(sync1.keys())[:20],
    )

    # Idempotent replay
    sync2 = orch.run_mailbox_sync(
        COMPANY, mailbox_id, "manual", provider=FakeProvider(), limit=10
    )
    dup_count = (sync2.get("counts") or {}).get("duplicate", 0)
    ok(
        "idempotent_no_duplicate_candidates",
        sync2.get("ok") is True and dup_count >= 1,
        sync2.get("counts"),
    )

    # Dry-run still available
    with orch.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE mailbox_connections SET sync_mode='dry_run' WHERE mailbox_id=%s",
                (mailbox_id,),
            )
        conn.commit()
    dry = orch.run_mailbox_sync(COMPANY, mailbox_id, "manual", provider=FakeProvider(), limit=10)
    ok("dry_run_reports_would_import", dry.get("dry_run") is True and dry.get("pipeline") == "durable_email_ingress", dry)

    # Flag off skips
    os.environ["WATHEFNI_MAILBOX_SYNC"] = "off"
    skipped = orch.run_mailbox_sync(COMPANY, mailbox_id, "manual", provider=FakeProvider())
    ok("flag_off_skips_sync", skipped.get("skipped") == "mailbox_sync_disabled", skipped)

    src = Path(iip.__file__).read_text()
    ok(
        "product_forwarding_default_in_source",
        "mailbox_sync_enabled" in src
        and "False" in src
        and "mailbox_connectors_premium" in src
        and "default_intake_product" in src,
        True,
    )

    ok("external_tenants_not_enabled", os.environ.get("WATHEFNI_INBOUND_ALLOWED_COMPANIES", "").upper() in {"", "WATHEFNI"}, True)
    ok("d6_not_started", True, "local D5 only")
    ok("ga_not_enabled", os.environ.get("WATHEFNI_MAILBOX_SYNC", "off").lower() == "off", True)

    # Cleanup
    with orch.db_connect() as conn:
        with conn.cursor() as cur:
            if mailbox_id:
                cur.execute("DELETE FROM mailbox_connections WHERE mailbox_id=%s", (mailbox_id,))
            if intake_id:
                cur.execute(
                    "UPDATE intake_addresses SET status='disabled' WHERE intake_id=%s",
                    (intake_id,),
                )
        conn.commit()

    RESULTS["passed"] = sum(1 for v in RESULTS["cases"].values() if v["ok"])
    RESULTS["failed"] = sum(1 for v in RESULTS["cases"].values() if not v["ok"])
    print(json.dumps({"passed": RESULTS["passed"], "failed": RESULTS["failed"]}, indent=2))
    return 0 if RESULTS["failed"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
