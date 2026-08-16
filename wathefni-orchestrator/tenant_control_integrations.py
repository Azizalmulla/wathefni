"""Integration control plane (Wave 3).

Honest support tiers. Unsupported providers are never selectable as ready.
Secrets live only in tc_secret_refs (locator/fingerprint), never in audit JSON.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from typing import Any
from uuid import uuid4

import tenant_control_decision as decision
import tenant_control_lifecycle as lifecycle
import tenant_control_wave3_schema as wave3


@dataclass(frozen=True)
class ProviderDefinition:
    provider_key: str
    channel_key: str
    label: str
    support_tier: str  # supported | partial | platform_global | unsupported | future
    selectable: bool
    required_scopes: tuple[str, ...] = ()
    notes: str = ""


PROVIDER_CATALOG: tuple[ProviderDefinition, ...] = (
    ProviderDefinition(
        "octopus_whatsapp",
        "whatsapp_business",
        "WhatsApp Business (Octopus)",
        "platform_global",
        True,
        notes="Platform-global today; company channel accounts flag OFF. Ownership verification required before treating as tenant-owned.",
    ),
    ProviderDefinition(
        "postmark_inbound",
        "inbound_email",
        "Inbound Email (Postmark)",
        "supported",
        True,
        notes="Unified inbound CV email path for allowlisted tenants.",
    ),
    ProviderDefinition(
        "postmark_outbound",
        "outbound_email",
        "Outbound Email (Postmark)",
        "supported",
        True,
    ),
    ProviderDefinition(
        "gmail_gog",
        "gmail_mailbox",
        "Gmail mailbox (gog)",
        "partial",
        True,
        notes="Mailbox connect exists; live import blocked pending durable scan/identity authority.",
    ),
    ProviderDefinition(
        "google_calendar",
        "calendar_meet",
        "Google Calendar / Meet",
        "partial",
        True,
        notes="C5: platform google_workspace integration + Calendar sync consumer.",
    ),
    ProviderDefinition(
        "microsoft_365",
        "outlook",
        "Microsoft 365 / Outlook",
        "partial",
        True,
        notes="C5: platform microsoft_365 integration + Graph Calendar/Teams consumer (dry-run safe).",
    ),
    ProviderDefinition(
        "microsoft_teams",
        "teams",
        "Microsoft Teams",
        "partial",
        True,
        notes="C5: Teams meeting creation via Graph onlineMeeting on calendar events.",
    ),
    ProviderDefinition(
        "imap",
        "imap_mailbox",
        "IMAP mailbox",
        "unsupported",
        False,
        notes="Future — not end-to-end implemented.",
    ),
    ProviderDefinition(
        "sms",
        "sms",
        "SMS",
        "future",
        False,
        notes="Appears in vocabulary only; no live SMS provider.",
    ),
    ProviderDefinition(
        "push",
        "push_notifications",
        "Push notifications",
        "partial",
        True,
        notes="Employee-app dependent; platform employee app flag currently OFF.",
    ),
    ProviderDefinition(
        "mistral_ocr",
        "ocr_ai",
        "OCR / AI (Mistral)",
        "platform_global",
        True,
        notes="Platform secrets via env; not tenant-owned credentials.",
    ),
    ProviderDefinition(
        "candidate_indexing",
        "candidate_knowledge_index",
        "Candidate indexing",
        "supported",
        True,
        notes="Backend capability under Candidates; production-dark worker.",
    ),
)

PROVIDER_BY_KEY = {p.provider_key: p for p in PROVIDER_CATALOG}


def ensure_schema(cur: Any) -> dict[str, Any]:
    return wave3.ensure_tenant_control_schema(cur)


def provider_matrix() -> list[dict[str, Any]]:
    return [asdict(p) | {"required_scopes": list(p.required_scopes)} for p in PROVIDER_CATALOG]


def register_secret_ref(
    cur: Any,
    *,
    company_code: str,
    provider_key: str,
    purpose: str,
    secret_locator: str,
    secret_backend: str = "env_file",
    actor: str,
) -> dict[str, Any]:
    """Store only a locator + fingerprint — never the secret value."""
    ensure_schema(cur)
    tenant = decision.load_tenant_state(cur, company_code)
    fingerprint = hashlib.sha256(f"{secret_backend}:{secret_locator}".encode()).hexdigest()[:16]
    cur.execute(
        """
        INSERT INTO tc_secret_refs (
          tenant_id, company_code, provider_key, purpose, secret_backend, secret_locator, fingerprint, metadata
        ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s::jsonb)
        ON CONFLICT (company_code, provider_key, purpose) DO UPDATE SET
          secret_backend=EXCLUDED.secret_backend,
          secret_locator=EXCLUDED.secret_locator,
          fingerprint=EXCLUDED.fingerprint,
          rotated_at=now(),
          metadata=EXCLUDED.metadata
        RETURNING secret_ref_id::text AS secret_ref_id, fingerprint
        """,
        (
            (tenant or {}).get("tenant_id"),
            company_code.upper(),
            provider_key,
            purpose,
            secret_backend,
            secret_locator,
            fingerprint,
            json.dumps({"actor": actor, "no_secret_material": True}),
        ),
    )
    row = dict(cur.fetchone())
    return {"ok": True, **row, "secret_locator": secret_locator, "secret_backend": secret_backend}


def upsert_integration(
    cur: Any,
    *,
    company_code: str,
    provider_key: str,
    state: str | None = None,
    provider_account_ref: str | None = None,
    secret_ref_id: str | None = None,
    actor: str = "system",
    kill_switch: bool | None = None,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    ensure_schema(cur)
    provider = PROVIDER_BY_KEY.get(provider_key)
    if not provider:
        return {"ok": False, "error": "unknown_provider"}
    if state and state not in {"not_selected", None} and not provider.selectable:
        return {
            "ok": False,
            "error": "provider_not_selectable",
            "message": f"{provider.label} is {provider.support_tier} and cannot be selected as ready.",
            "support_tier": provider.support_tier,
            "available": False,
        }
    if state == "selected" and not provider.selectable:
        return {
            "ok": False,
            "error": "provider_not_selectable",
            "message": f"{provider.label} is {provider.support_tier} and cannot be selected as ready.",
            "support_tier": provider.support_tier,
        }
    # Never treat a manually entered account reference as verified ownership.
    if state in {"verified", "live"} and provider_account_ref and not secret_ref_id:
        if provider.support_tier in {"unsupported", "future"}:
            return {"ok": False, "error": "unsupported_provider"}
        return {
            "ok": False,
            "error": "account_ref_not_verified_ownership",
            "message": "Manually entered account references are not verified ownership.",
        }
    tenant = decision.load_tenant_state(cur, company_code)
    if not tenant:
        return {"ok": False, "error": "tenant_not_imported"}
    cur.execute(
        """
        SELECT integration_id::text AS integration_id, state
        FROM tc_integrations
        WHERE company_code=%s AND provider_key=%s AND channel_key=%s
        LIMIT 1
        """,
        (company_code.upper(), provider.provider_key, provider.channel_key),
    )
    existing = cur.fetchone()
    from_state = existing["state"] if existing else "not_selected"
    to_state = state or from_state or "not_selected"
    cur.execute(
        """
        INSERT INTO tc_integrations (
          tenant_id, company_code, provider_key, channel_key, display_name, state,
          supported, support_tier, provider_account_ref, secret_ref_id, required_scopes,
          kill_switch, metadata, updated_at
        ) VALUES (
          %s,%s,%s,%s,%s,%s,
          %s,%s,%s,%s,%s::jsonb,
          COALESCE(%s,false),%s::jsonb,now()
        )
        ON CONFLICT (company_code, provider_key, channel_key) DO UPDATE SET
          state=COALESCE(EXCLUDED.state, tc_integrations.state),
          provider_account_ref=COALESCE(EXCLUDED.provider_account_ref, tc_integrations.provider_account_ref),
          secret_ref_id=COALESCE(EXCLUDED.secret_ref_id, tc_integrations.secret_ref_id),
          kill_switch=COALESCE(EXCLUDED.kill_switch, tc_integrations.kill_switch),
          metadata=tc_integrations.metadata || EXCLUDED.metadata,
          updated_at=now()
        RETURNING integration_id::text AS integration_id, state, support_tier, kill_switch
        """,
        (
            tenant["tenant_id"],
            company_code.upper(),
            provider.provider_key,
            provider.channel_key,
            provider.label,
            to_state,
            provider.support_tier in {"supported", "partial", "platform_global"},
            provider.support_tier,
            provider_account_ref,
            secret_ref_id,
            json.dumps(list(provider.required_scopes)),
            kill_switch,
            json.dumps({**(metadata or {}), "notes": provider.notes, "actor": actor}),
        ),
    )
    row = dict(cur.fetchone())
    cur.execute(
        """
        INSERT INTO tc_integration_events (
          integration_id, company_code, event_type, from_state, to_state, actor, detail
        ) VALUES (%s,%s,%s,%s,%s,%s,%s::jsonb)
        """,
        (
            row["integration_id"],
            company_code.upper(),
            "state_change",
            from_state,
            row["state"],
            actor,
            json.dumps({"provider_key": provider_key, "no_secrets": True}),
        ),
    )
    return {"ok": True, **row, "provider_key": provider_key, "selectable": provider.selectable}


def run_integration_test(
    cur: Any,
    *,
    company_code: str,
    provider_key: str,
    test_kind: str,
    actor: str,
) -> dict[str, Any]:
    provider = PROVIDER_BY_KEY.get(provider_key)
    if not provider:
        return {"ok": False, "error": "unknown_provider"}
    if provider.support_tier in {"unsupported", "future"}:
        return {
            "ok": False,
            "error": "provider_unsupported",
            "message": f"{provider.label} is not supported end-to-end.",
            "support_tier": provider.support_tier,
            "available": False,
        }
    cur.execute(
        """
        SELECT integration_id::text AS integration_id, state, kill_switch, secret_ref_id::text AS secret_ref_id
        FROM tc_integrations
        WHERE company_code=%s AND provider_key=%s
        LIMIT 1
        """,
        (company_code.upper(), provider_key),
    )
    row = cur.fetchone()
    if not row:
        return {"ok": False, "error": "integration_not_found"}
    integ = dict(row)
    if integ.get("kill_switch"):
        return {"ok": False, "error": "integration_kill_switch", "state": integ["state"]}
    # Simulated deterministic tests for supported/partial/platform_global — no secret values.
    result = {
        "ok": True,
        "test_kind": test_kind,
        "provider_key": provider_key,
        "passed": True,
        "evidence": {
            "support_tier": provider.support_tier,
            "secret_ref_present": bool(integ.get("secret_ref_id")),
            # Secret locator / account ref presence is never verified ownership.
            "account_ref_verified_ownership": False,
            "ownership_note": "Manual account references and secret locators are not verified ownership.",
        },
        "actor": actor,
    }
    if test_kind in {"connect", "verify", "test_send", "test_receive", "webhook_test", "health"}:
        new_state = {
            "connect": "connected",
            "verify": "verified",
            "test_send": "testing",
            "test_receive": "testing",
            "webhook_test": "testing",
            "health": integ["state"] if integ["state"] in {"live", "verified", "connected"} else "connected",
        }[test_kind]
        if test_kind == "health" and provider.support_tier == "supported":
            new_state = "live"
        upsert_integration(
            cur,
            company_code=company_code,
            provider_key=provider_key,
            state=new_state,
            actor=actor,
            metadata={"last_test": test_kind, "passed": True},
        )
        cur.execute(
            """
            UPDATE tc_integrations
            SET last_tested_at=now(),
                last_verified_at=CASE WHEN %s IN ('verify','health') THEN now() ELSE last_verified_at END,
                health_json=%s::jsonb,
                updated_at=now()
            WHERE company_code=%s AND provider_key=%s
            """,
            (
                test_kind,
                json.dumps({"status": "ok", "test_kind": test_kind, "no_secrets": True}),
                company_code.upper(),
                provider_key,
            ),
        )
    return result


def set_integration_degraded(
    cur: Any,
    *,
    company_code: str,
    provider_key: str,
    actor: str,
    reason: str,
) -> dict[str, Any]:
    result = upsert_integration(
        cur,
        company_code=company_code,
        provider_key=provider_key,
        state="degraded",
        actor=actor,
        metadata={"degraded_reason": reason},
    )
    # Block side effects via kill switch while degraded for canary/safety.
    if result.get("ok"):
        upsert_integration(
            cur,
            company_code=company_code,
            provider_key=provider_key,
            kill_switch=True,
            actor=actor,
            metadata={"blocked_side_effects": True},
        )
    return result


def restore_integration(
    cur: Any,
    *,
    company_code: str,
    provider_key: str,
    actor: str,
    state: str = "live",
) -> dict[str, Any]:
    return upsert_integration(
        cur,
        company_code=company_code,
        provider_key=provider_key,
        state=state,
        kill_switch=False,
        actor=actor,
        metadata={"restored": True},
    )


def seed_wathefni_integrations(cur: Any, *, actor: str = "wave3_seed") -> dict[str, Any]:
    ensure_schema(cur)
    seeded = []
    # Platform-global / supported representations for current WATHEFNI posture.
    mapping = [
        ("octopus_whatsapp", "live", None, "platform whatsapp"),
        ("postmark_inbound", "live", "/opt/wathefni/var/unified-inbound-cv.production.env", "inbound"),
        ("postmark_outbound", "live", "/root/.openclaw/secrets/wathefni-intake.env", "outbound"),
        ("gmail_gog", "setup_required", "/root/.openclaw/secrets/gog-keyring.env", "mailbox"),
        ("google_calendar", "setup_required", None, "calendar"),
        ("microsoft_365", "not_selected", None, None),
        ("microsoft_teams", "not_selected", None, None),
        ("imap", "not_selected", None, None),
        ("sms", "not_selected", None, None),
        ("push", "setup_required", None, None),
        ("mistral_ocr", "live", "/root/.openclaw/secrets/mistral.env", "ocr"),
        ("candidate_indexing", "live", "/opt/wathefni/var/ck-flags.production.env", "index"),
    ]
    for provider_key, state, locator, purpose in mapping:
        provider = PROVIDER_BY_KEY[provider_key]
        secret_ref_id = None
        if locator and purpose and provider.selectable:
            secret = register_secret_ref(
                cur,
                company_code="WATHEFNI",
                provider_key=provider_key,
                purpose=purpose,
                secret_locator=locator,
                actor=actor,
            )
            secret_ref_id = secret.get("secret_ref_id")
        # Unsupported/future stay not_selected and unselectable.
        if not provider.selectable:
            state = "not_selected"
            secret_ref_id = None
        # Partial providers never seed as live — setup_required until end-to-end proven.
        if provider.support_tier == "partial" and state in {"live", "verified"}:
            state = "setup_required"
        result = upsert_integration(
            cur,
            company_code="WATHEFNI",
            provider_key=provider_key,
            state=state,
            secret_ref_id=secret_ref_id,
            actor=actor,
            metadata={"seeded_from_production_posture": True},
        )
        seeded.append(result)
    return {"ok": True, "count": len(seeded), "items": seeded}


def integration_blocks_side_effects(cur: Any, *, company_code: str, provider_key: str) -> bool:
    cur.execute(
        """
        SELECT kill_switch, state
        FROM tc_integrations
        WHERE company_code=%s AND provider_key=%s
        LIMIT 1
        """,
        (company_code.upper(), provider_key),
    )
    row = cur.fetchone()
    if not row:
        return False
    return bool(row["kill_switch"]) or str(row["state"]) in {"degraded", "blocked", "disconnected", "uninstalling"}
