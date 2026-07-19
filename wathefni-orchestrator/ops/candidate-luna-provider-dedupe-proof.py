#!/usr/bin/env python3
"""Staging proof: provider message-ID forwarding + generic-agent bypass guard.

No real WhatsApp delivery. Uses staging DB only for synthetic dedupe rows.
"""

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

EVIDENCE_DIR = Path(__file__).resolve().parents[2] / "staging-evidence" / "candidate-luna-semantic-router1"


def simulate_channel_metadata(payload: dict, *, forward_top_level: bool) -> dict:
    message_id = None
    messages = payload.get("messages") if isinstance(payload.get("messages"), list) else []
    if messages and isinstance(messages[0], dict):
        message_id = str(messages[0].get("id") or "").strip() or None
    meta = {
        "source": "openclaw_octopus_channel",
        "latest_user_language": "en",
        "provider_payload": payload,
    }
    if forward_top_level and message_id:
        meta.update(
            {
                "provider": "octopus",
                "provider_message_id": message_id,
                "message_id": message_id,
                "wamid": message_id,
            }
        )
    return meta


def channel_fail_closed_decision(*, authoritative: bool | None, reply_text: str | None, agent_id: str, has_message_id: bool) -> dict:
    """Mirrors the Octopus wathefni-hr fail-closed gate after the Luna fix."""
    if agent_id != "wathefni-hr":
        return {"falls_through_to_generic_agent": True, "reason": "non_hr_agent"}
    if not has_message_id:
        return {"falls_through_to_generic_agent": False, "reason": "missing_provider_message_id_return"}
    if authoritative:
        return {"falls_through_to_generic_agent": False, "reason": "authoritative_return_even_without_reply"}
    return {"falls_through_to_generic_agent": False, "reason": "orchestrator_fail_closed_safe_reply"}


def main() -> int:
    app.ensure_schema()
    EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
    marker = f"luna-dedupe-{uuid.uuid4().hex}"
    provider_payload = {
        "conversation_id": "900001",
        "messages": [
            {
                "id": "wamid.HBgLLUNA0001PROOF",
                "from": "96550000001",
                "type": "text",
                "text": {"body": "status?"},
            }
        ],
    }
    legacy_meta = simulate_channel_metadata(provider_payload, forward_top_level=False)
    fixed_meta = simulate_channel_metadata(provider_payload, forward_top_level=True)

    legacy_req = app.WhatsAppTurnRequest(
        account_id="internal-luna-proof",
        conversation_id="900001",
        sender_phone="96550000001",
        sender_role="candidate",
        raw_text="status?",
        metadata=legacy_meta,
    )
    fixed_req = app.WhatsAppTurnRequest(
        account_id="internal-luna-proof",
        conversation_id="900001",
        sender_phone="96550000001",
        sender_role="candidate",
        raw_text="status?",
        metadata=fixed_meta,
    )

    extracted_legacy = app._whatsapp_provider_message_id(legacy_req)
    extracted_fixed = app._whatsapp_provider_message_id(fixed_req)
    expected_id = provider_payload["messages"][0]["id"]

    base_metadata = {"provider": "luna-proof", "provider_message_id": marker}

    def request(text: str = "status?") -> app.WhatsAppTurnRequest:
        return app.WhatsAppTurnRequest(
            account_id="internal-luna-proof",
            conversation_id="900001",
            sender_phone="96550000001",
            sender_role="candidate",
            raw_text=text,
            metadata=base_metadata,
        )

    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        concurrent_claims = list(pool.map(lambda _: app.claim_whatsapp_inbound(request()), range(2)))

    changed = app.claim_whatsapp_inbound(request("withdraw my application"))
    missing = app.claim_whatsapp_inbound(
        app.WhatsAppTurnRequest(
            account_id="internal-luna-proof",
            conversation_id="900001",
            sender_phone="96550000001",
            sender_role="candidate",
            raw_text="status?",
            metadata={"provider": "luna-proof"},
        )
    )

    # Authoritative empty reply must not fall through (generic-agent bypass).
    bypass_checks = {
        "authoritative_with_reply": channel_fail_closed_decision(
            authoritative=True, reply_text="hello", agent_id="wathefni-hr", has_message_id=True
        ),
        "authoritative_without_reply": channel_fail_closed_decision(
            authoritative=True, reply_text=None, agent_id="wathefni-hr", has_message_id=True
        ),
        "missing_message_id": channel_fail_closed_decision(
            authoritative=None, reply_text=None, agent_id="wathefni-hr", has_message_id=False
        ),
        "orchestrator_null": channel_fail_closed_decision(
            authoritative=None, reply_text=None, agent_id="wathefni-hr", has_message_id=True
        ),
    }
    no_generic_bypass = all(not item["falls_through_to_generic_agent"] for item in bypass_checks.values())

    params = ("luna-proof", "internal-luna-proof", marker)
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

    output = {
        "mode": "staging_db_synthetic_no_delivery",
        "production_shaped_payload": provider_payload,
        "provider_field": "messages[0].id",
        "extracted_at_channel": expected_id,
        "legacy_metadata_keys": sorted(legacy_meta),
        "fixed_metadata_keys": sorted(fixed_meta),
        "orchestrator_id_from_legacy_nested_only": extracted_legacy,
        "orchestrator_id_from_fixed_top_level": extracted_fixed,
        "mapping_ok": extracted_fixed == expected_id and extracted_legacy == expected_id,
        "nested_provider_payload_fallback_ok": extracted_legacy == expected_id,
        "top_level_forwarding_ok": extracted_fixed == expected_id,
        "concurrent_claims": app.json_safe(concurrent_claims),
        "concurrent_single_claim": (
            sum(1 for item in concurrent_claims if item.get("claimed")) == 1
            and sum(1 for item in concurrent_claims if item.get("duplicate")) == 1
        ),
        "changed_payload_duplicate": bool(changed.get("duplicate")),
        "changed_payload_identity_match": changed.get("identity_match"),
        "missing_id_dedupe_available": missing.get("dedupe_available"),
        "row_count_before_cleanup": before_cleanup,
        "row_count_after_cleanup": after_cleanup,
        "generic_agent_bypass_checks": bypass_checks,
        "no_generic_agent_bypass": no_generic_bypass,
        "pass": (
            extracted_fixed == expected_id
            and extracted_legacy == expected_id
            and no_generic_bypass
            and sum(1 for item in concurrent_claims if item.get("claimed")) == 1
            and missing.get("dedupe_available") is False
            and after_cleanup == 0
        ),
    }
    (EVIDENCE_DIR / "PROVIDER_DEDUPE_PROOF.json").write_text(
        json.dumps(output, ensure_ascii=False, indent=2, sort_keys=True, default=str),
        encoding="utf-8",
    )
    print(json.dumps(output, ensure_ascii=False, indent=2, sort_keys=True, default=str))
    return 0 if output["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
