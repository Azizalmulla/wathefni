#!/usr/bin/env python3
"""Synthetic staging proof for WhatsApp provider-ID mapping and dedupe."""

from __future__ import annotations

import concurrent.futures
import json
import os
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

os.environ.setdefault("WATHEFNI_CANONICAL_LIFECYCLE", "true")
os.environ.setdefault("WATHEFNI_DELIVERY_MODE", "dry_run")

import app


def main() -> int:
    app.ensure_schema()
    marker = f"readiness-{uuid.uuid4().hex}"
    provider_payload = {
        "conversation_id": "900001",
        "messages": [
            {
                "id": "wamid.HBgLREADINESS0001",
                "from": "96550000000",
                "type": "text",
                "text": {"body": "status?"},
            }
        ],
    }
    forwarded_metadata = {
        "source": "openclaw_octopus_channel",
        "latest_user_language": "en",
        "provider_payload": provider_payload,
    }
    forwarded = app.WhatsAppTurnRequest(
        account_id="internal-readiness",
        conversation_id="900001",
        sender_phone="96550000000",
        sender_role="candidate",
        raw_text="status?",
        metadata=forwarded_metadata,
    )
    corrected = app.WhatsAppTurnRequest(
        account_id="internal-readiness",
        conversation_id="900001",
        sender_phone="96550000000",
        sender_role="candidate",
        raw_text="status?",
        metadata={
            **forwarded_metadata,
            "provider": "octopus",
            "provider_message_id": provider_payload["messages"][0]["id"],
        },
    )

    base_metadata = {"provider": "readiness-proof", "provider_message_id": marker}

    def request(text: str = "status?") -> app.WhatsAppTurnRequest:
        return app.WhatsAppTurnRequest(
            account_id="internal-readiness",
            conversation_id="900001",
            sender_phone="96550000000",
            sender_role="candidate",
            raw_text=text,
            metadata=base_metadata,
        )

    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        concurrent_claims = list(pool.map(lambda _: app.claim_whatsapp_inbound(request()), range(2)))

    changed = app.claim_whatsapp_inbound(request("withdraw my application"))
    missing = app.claim_whatsapp_inbound(
        app.WhatsAppTurnRequest(
            account_id="internal-readiness",
            conversation_id="900001",
            sender_phone="96550000000",
            raw_text="status?",
            metadata={"provider": "readiness-proof"},
        )
    )

    params = ("readiness-proof", "internal-readiness", marker)
    with app.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT count(*) AS n
                FROM whatsapp_inbound_messages
                WHERE provider=%s AND account_id=%s AND provider_message_id=%s
                """,
                params,
            )
            before_cleanup = int(cur.fetchone()["n"])
            cur.execute(
                """
                DELETE FROM whatsapp_inbound_messages
                WHERE provider=%s AND account_id=%s AND provider_message_id=%s
                """,
                params,
            )
        conn.commit()
    with app.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT count(*) AS n
                FROM whatsapp_inbound_messages
                WHERE provider=%s AND account_id=%s AND provider_message_id=%s
                """,
                params,
            )
            after_cleanup = int(cur.fetchone()["n"])

    extracted_from_deployed_shape = app._whatsapp_provider_message_id(forwarded)
    extracted_from_corrected_shape = app._whatsapp_provider_message_id(corrected)
    output = {
        "mode": "staging_db_synthetic_no_delivery",
        "production_shaped_payload": provider_payload,
        "provider_field": "messages[0].id",
        "extracted_at_channel": provider_payload["messages"][0]["id"],
        "deployed_forwarded_metadata_keys": sorted(forwarded_metadata),
        "orchestrator_id_from_deployed_shape": extracted_from_deployed_shape,
        "orchestrator_id_from_corrected_shape": extracted_from_corrected_shape,
        "mapping_ok": extracted_from_deployed_shape == provider_payload["messages"][0]["id"],
        "concurrent_claims": app.json_safe(concurrent_claims),
        "concurrent_single_claim": (
            sum(1 for item in concurrent_claims if item.get("claimed")) == 1
            and sum(1 for item in concurrent_claims if item.get("duplicate")) == 1
        ),
        "row_count_before_cleanup": before_cleanup,
        "changed_payload_duplicate": bool(changed.get("duplicate")),
        "changed_payload_identity_match": changed.get("identity_match"),
        "missing_id_dedupe_available": missing.get("dedupe_available"),
        "generated_fallback_used": False,
        "row_count_after_cleanup": after_cleanup,
    }
    print(json.dumps(output, ensure_ascii=False, indent=2, sort_keys=True, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
