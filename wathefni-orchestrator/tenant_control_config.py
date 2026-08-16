"""Versioned tenant configuration framework (Wave 3).

Draft → validate → review → publish → effective date → rollback.
Secrets never belong in config_json.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

import tenant_control_decision as decision
import tenant_control_lifecycle as lifecycle
import tenant_control_wave3_schema as wave3


CONFIG_SCHEMA_VERSION = "tenant-config-schemas-v1"

# Lightweight JSON-schema-like contracts (required keys + types). Full JSON Schema
# engines are intentionally avoided to keep the control plane dependency-free.
DOMAIN_SCHEMAS: dict[str, dict[str, Any]] = {
    "company_profile": {
        "required": ["display_name", "country", "timezone", "currency", "languages"],
        "properties": {
            "display_name": "string",
            "country": "string",
            "timezone": "string",
            "currency": "string",
            "languages": "array",
            "branding": "object",
            "sector": "string",
        },
    },
    "org_structure": {
        "required": ["legal_entities", "branches", "departments", "teams", "cost_centers"],
        "properties": {
            "legal_entities": "array",
            "branches": "array",
            "departments": "array",
            "teams": "array",
            "cost_centers": "array",
        },
    },
    "module_policies": {
        "required": ["modules"],
        "properties": {"modules": "object"},
    },
    "notification_policies": {
        "required": ["preset"],
        "properties": {
            "preset": "string",
            "channels": "object",
            "quiet_hours": "object",
        },
    },
    "retention_policies": {
        "required": ["cv_retention_days", "legal_hold"],
        "properties": {
            "cv_retention_days": "number",
            "deletion_policy": "string",
            "export_policy": "string",
            "legal_hold": "boolean",
        },
    },
    "quotas": {
        "required": ["limits"],
        "properties": {"limits": "object"},
    },
    "custom_fields": {
        "required": ["candidate_fields", "employee_fields"],
        "properties": {
            "candidate_fields": "array",
            "employee_fields": "array",
            "required_fields": "array",
        },
    },
    "document_requirements": {
        "required": ["items"],
        "properties": {"items": "array"},
    },
    "workflows": {
        "required": ["approvals"],
        "properties": {
            "approvals": "object",
            "chains": "array",
        },
    },
    "prehire": {
        "required": [
            "candidates_area",
            "jobs",
            "lifecycle",
            "notes",
            "duplicate_policy",
            "general_cv_intake",
            "held_vs_admitted",
            "cv_retention",
            "ranking",
            "screening",
            "assessments",
            "interviews",
            "video_interviews",
            "communication",
            "approvals",
            "candidate_custom_fields",
        ],
        "properties": {
            "candidates_area": "object",
            "jobs": "object",
            "lifecycle": "object",
            "notes": "object",
            "duplicate_policy": "object",
            "general_cv_intake": "object",
            "held_vs_admitted": "object",
            "cv_retention": "object",
            "ranking": "object",
            "screening": "object",
            "assessments": "object",
            "interviews": "object",
            "video_interviews": "object",
            "communication": "object",
            "approvals": "object",
            "candidate_custom_fields": "array",
            "backend_capabilities": "object",
        },
        "notes": "Candidate Knowledge and Talent Pool remain backend-only under candidates_area.",
    },
    "posthire": {
        "required": [
            "onboarding",
            "compliance",
            "attendance",
            "shifts",
            "leave",
            "payroll",
            "analytics",
            "employee_app",
        ],
        "properties": {
            "onboarding": "object",
            "compliance": "object",
            "attendance": "object",
            "shifts": "object",
            "leave": "object",
            "payroll": "object",
            "analytics": "object",
            "employee_app": "object",
        },
    },
}


FORBIDDEN_SECRET_KEYS = {
    "password", "secret", "token", "api_key", "apikey", "private_key",
    "client_secret", "access_token", "refresh_token", "webhook_secret",
}


def ensure_schema(cur: Any) -> dict[str, Any]:
    result = wave3.ensure_tenant_control_schema(cur)
    for key, spec in DOMAIN_SCHEMAS.items():
        cur.execute(
            """
            INSERT INTO tc_config_schemas (schema_key, schema_version, domain, json_schema, description)
            VALUES (%s,%s,%s,%s::jsonb,%s)
            ON CONFLICT (schema_key, schema_version) DO UPDATE SET
              json_schema = EXCLUDED.json_schema,
              description = EXCLUDED.description
            """,
            (
                key,
                CONFIG_SCHEMA_VERSION,
                key,
                json.dumps(spec),
                spec.get("notes") or f"Wave 3 schema for {key}",
            ),
        )
    return result


def _type_name(value: Any) -> str:
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return "number"
    if isinstance(value, str):
        return "string"
    if isinstance(value, list):
        return "array"
    if isinstance(value, dict):
        return "object"
    if value is None:
        return "null"
    return type(value).__name__


def _scan_secrets(payload: Any, path: str = "") -> list[str]:
    hits: list[str] = []
    if isinstance(payload, dict):
        for key, value in payload.items():
            key_l = str(key).lower()
            next_path = f"{path}.{key}" if path else str(key)
            if any(part in key_l for part in FORBIDDEN_SECRET_KEYS):
                hits.append(next_path)
            hits.extend(_scan_secrets(value, next_path))
    elif isinstance(payload, list):
        for idx, item in enumerate(payload):
            hits.extend(_scan_secrets(item, f"{path}[{idx}]"))
    return hits


def validate_config(domain: str, config_json: dict[str, Any]) -> dict[str, Any]:
    schema = DOMAIN_SCHEMAS.get(domain)
    if not schema:
        return {"ok": False, "errors": [{"code": "unknown_domain", "message": f"Unknown domain {domain}"}]}
    errors: list[dict[str, str]] = []
    warnings: list[dict[str, str]] = []
    for key in schema.get("required") or []:
        if key not in config_json:
            errors.append({"code": "missing_required", "message": f"Missing required key: {key}"})
    props = schema.get("properties") or {}
    for key, expected in props.items():
        if key not in config_json:
            continue
        actual = _type_name(config_json[key])
        if actual != expected and not (expected == "number" and actual == "number"):
            errors.append({
                "code": "type_mismatch",
                "message": f"{key} expected {expected}, got {actual}",
            })
    secret_hits = _scan_secrets(config_json)
    if secret_hits:
        errors.append({
            "code": "secrets_in_config",
            "message": "Secrets must use tc_secret_refs, not config JSON: " + ", ".join(secret_hits[:20]),
        })
    if domain == "prehire":
        backend = config_json.get("backend_capabilities") or {}
        if backend.get("candidate_knowledge_hr_visible") or backend.get("talent_pool_hr_product"):
            errors.append({
                "code": "backend_capability_exposed",
                "message": "Candidate Knowledge and Talent Pool must remain backend-only under Candidates.",
            })
        area = config_json.get("candidates_area") or {}
        if area.get("split_products"):
            errors.append({
                "code": "candidates_must_be_single_area",
                "message": "HR-facing product must remain one Candidates area.",
            })
    return {
        "ok": not errors,
        "errors": errors,
        "warnings": warnings,
        "schema_key": domain,
        "schema_version": CONFIG_SCHEMA_VERSION,
    }


def create_draft(
    cur: Any,
    *,
    company_code: str,
    domain: str,
    config_json: dict[str, Any],
    actor: str,
    idempotency_key: str | None = None,
) -> dict[str, Any]:
    ensure_schema(cur)
    tenant = decision.load_tenant_state(cur, company_code)
    if not tenant:
        raise RuntimeError("tenant_not_imported")
    if domain not in DOMAIN_SCHEMAS:
        raise ValueError(f"unknown_domain:{domain}")
    validation = validate_config(domain, config_json)
    idem = idempotency_key or f"draft-{domain}-{uuid4().hex}"
    correlation = uuid4().hex
    cur.execute(
        """
        INSERT INTO tc_config_documents (
          tenant_id, domain, schema_key, schema_version, status, owned_by,
          config_json, validation_json, idempotency_key, correlation_id
        ) VALUES (%s,%s,%s,%s,'draft',%s,%s::jsonb,%s::jsonb,%s,%s)
        ON CONFLICT (tenant_id, domain, idempotency_key) DO UPDATE SET
          config_json = EXCLUDED.config_json,
          validation_json = EXCLUDED.validation_json,
          updated_at = now()
        RETURNING document_id::text AS document_id, status
        """,
        (
            tenant["tenant_id"],
            domain,
            domain,
            CONFIG_SCHEMA_VERSION,
            actor,
            json.dumps(config_json),
            json.dumps(validation),
            idem,
            correlation,
        ),
    )
    row = dict(cur.fetchone())
    return {
        "ok": True,
        "document_id": row["document_id"],
        "status": row["status"],
        "validation": validation,
        "correlation_id": correlation,
    }


def mark_validated(cur: Any, *, document_id: str, actor: str) -> dict[str, Any]:
    cur.execute(
        "SELECT document_id::text AS document_id, domain, config_json, status FROM tc_config_documents WHERE document_id=%s",
        (document_id,),
    )
    row = cur.fetchone()
    if not row:
        return {"ok": False, "error": "document_not_found"}
    doc = dict(row)
    config = doc["config_json"]
    if isinstance(config, str):
        config = json.loads(config)
    validation = validate_config(doc["domain"], config)
    if not validation["ok"]:
        cur.execute(
            "UPDATE tc_config_documents SET validation_json=%s::jsonb, updated_at=now() WHERE document_id=%s",
            (json.dumps(validation), document_id),
        )
        return {"ok": False, "error": "validation_failed", "validation": validation}
    cur.execute(
        """
        UPDATE tc_config_documents
        SET status='validated', validation_json=%s::jsonb, updated_at=now()
        WHERE document_id=%s
        RETURNING document_id::text AS document_id, status
        """,
        (json.dumps(validation), document_id),
    )
    out = dict(cur.fetchone())
    return {"ok": True, **out, "validation": validation, "actor": actor}


def publish_document(
    cur: Any,
    *,
    document_id: str,
    actor: str,
    effective_from: datetime | None = None,
) -> dict[str, Any]:
    cur.execute(
        """
        SELECT d.*, t.company_code, t.tenant_id::text AS tenant_id
        FROM tc_config_documents d
        JOIN tc_tenants t ON t.tenant_id = d.tenant_id
        WHERE d.document_id=%s
        """,
        (document_id,),
    )
    row = cur.fetchone()
    if not row:
        return {"ok": False, "error": "document_not_found"}
    doc = dict(row)
    if doc["status"] not in {"validated", "approved", "in_review"}:
        # allow validated-or-better; auto-validate if still draft and valid
        config = doc["config_json"]
        if isinstance(config, str):
            config = json.loads(config)
        validation = validate_config(doc["domain"], config)
        if not validation["ok"]:
            return {"ok": False, "error": "validation_failed", "validation": validation}
    else:
        config = doc["config_json"]
        if isinstance(config, str):
            config = json.loads(config)
        validation = validate_config(doc["domain"], config)
        if not validation["ok"]:
            return {"ok": False, "error": "validation_failed", "validation": validation}

    company = doc["company_code"]
    domain = doc["domain"]
    cur.execute(
        """
        SELECT config_json, version_number
        FROM tc_config_documents
        WHERE tenant_id=%s AND domain=%s AND status='published'
        ORDER BY version_number DESC NULLS LAST
        LIMIT 1
        """,
        (doc["tenant_id"], domain),
    )
    prev = cur.fetchone()
    before = {}
    prev_version = None
    if prev:
        before = prev["config_json"] if isinstance(prev, dict) else prev[0]
        if isinstance(before, str):
            before = json.loads(before)
        prev_version = prev["version_number"] if isinstance(prev, dict) else prev[1]

    after = config
    import tenant_control_service as wave1

    diff = wave1._json_diff(before if isinstance(before, dict) else {}, after)
    cur.execute(
        """
        SELECT COALESCE(max(version_number), 0) + 1 AS next_version
        FROM tc_config_documents
        WHERE tenant_id=%s AND domain=%s AND version_number IS NOT NULL
        """,
        (doc["tenant_id"], domain),
    )
    next_version = int((cur.fetchone() or {}).get("next_version") or 1)
    correlation = uuid4().hex
    # supersede previous published
    cur.execute(
        """
        UPDATE tc_config_documents
        SET status='superseded', updated_at=now()
        WHERE tenant_id=%s AND domain=%s AND status='published'
        """,
        (doc["tenant_id"], domain),
    )
    cur.execute(
        """
        UPDATE tc_config_documents
        SET status='published',
            version_number=%s,
            effective_from=COALESCE(%s, now()),
            approved_by=%s,
            before_json=%s::jsonb,
            after_json=%s::jsonb,
            diff_json=%s::jsonb,
            validation_json=%s::jsonb,
            migration_impact=%s::jsonb,
            rollback_of_version=NULL,
            published_at=now(),
            updated_at=now(),
            correlation_id=%s
        WHERE document_id=%s
        RETURNING document_id::text AS document_id, version_number, status
        """,
        (
            next_version,
            effective_from,
            actor,
            json.dumps(before if isinstance(before, dict) else {}),
            json.dumps(after),
            json.dumps(diff),
            json.dumps(validation),
            json.dumps({"previous_version": prev_version, "domain": domain}),
            correlation,
            document_id,
        ),
    )
    published = dict(cur.fetchone())
    lifecycle._audit_fail_closed(
        cur,
        tenant_id=doc["tenant_id"],
        company_code=company,
        event_type="config_published",
        actor=actor,
        before=before if isinstance(before, dict) else {},
        after=after,
        detail={
            "domain": domain,
            "version_number": next_version,
            "document_id": document_id,
            "correlation_id": correlation,
            "diff": diff,
        },
        idempotency_key=f"config-publish-{company}-{domain}-{next_version}-{correlation}",
    )
    return {
        "ok": True,
        **published,
        "domain": domain,
        "company_code": company,
        "diff": diff,
        "rollback_target": prev_version,
        "correlation_id": correlation,
    }


def rollback_domain(
    cur: Any,
    *,
    company_code: str,
    domain: str,
    target_version: int,
    actor: str,
) -> dict[str, Any]:
    tenant = decision.load_tenant_state(cur, company_code)
    if not tenant:
        return {"ok": False, "error": "tenant_not_imported"}
    cur.execute(
        """
        SELECT document_id::text AS document_id, after_json, config_json, version_number
        FROM tc_config_documents
        WHERE tenant_id=%s AND domain=%s AND version_number=%s
        LIMIT 1
        """,
        (tenant["tenant_id"], domain, target_version),
    )
    row = cur.fetchone()
    if not row:
        return {"ok": False, "error": "version_not_found"}
    doc = dict(row)
    snapshot = doc.get("after_json") or doc.get("config_json") or {}
    if isinstance(snapshot, str):
        snapshot = json.loads(snapshot)
    draft = create_draft(
        cur,
        company_code=company_code,
        domain=domain,
        config_json=snapshot,
        actor=actor,
        idempotency_key=f"rollback-{domain}-{target_version}-{uuid4().hex}",
    )
    validated = mark_validated(cur, document_id=draft["document_id"], actor=actor)
    if not validated.get("ok"):
        return validated
    published = publish_document(cur, document_id=draft["document_id"], actor=actor)
    if published.get("ok"):
        cur.execute(
            """
            UPDATE tc_config_documents
            SET rollback_of_version=%s
            WHERE document_id=%s
            """,
            (target_version, draft["document_id"]),
        )
    return published


def get_published(cur: Any, *, company_code: str, domain: str) -> dict[str, Any] | None:
    tenant = decision.load_tenant_state(cur, company_code)
    if not tenant:
        return None
    cur.execute(
        """
        SELECT document_id::text AS document_id, domain, status, version_number,
               config_json, effective_from, published_at, diff_json
        FROM tc_config_documents
        WHERE tenant_id=%s AND domain=%s AND status='published'
        ORDER BY version_number DESC
        LIMIT 1
        """,
        (tenant["tenant_id"], domain),
    )
    row = cur.fetchone()
    return dict(row) if row else None


def list_drafts(cur: Any, *, company_code: str, domain: str | None = None) -> list[dict[str, Any]]:
    tenant = decision.load_tenant_state(cur, company_code)
    if not tenant:
        return []
    if domain:
        cur.execute(
            """
            SELECT document_id::text AS document_id, domain, status, version_number, updated_at
            FROM tc_config_documents
            WHERE tenant_id=%s AND domain=%s AND status IN ('draft','validated','in_review','approved')
            ORDER BY updated_at DESC
            """,
            (tenant["tenant_id"], domain),
        )
    else:
        cur.execute(
            """
            SELECT document_id::text AS document_id, domain, status, version_number, updated_at
            FROM tc_config_documents
            WHERE tenant_id=%s AND status IN ('draft','validated','in_review','approved')
            ORDER BY updated_at DESC
            """,
            (tenant["tenant_id"],),
        )
    return [dict(r) for r in cur.fetchall()]


def wathefni_default_configs() -> dict[str, dict[str, Any]]:
    """Represent current WATHEFNI live posture as control-plane config documents."""
    return {
        "company_profile": {
            "display_name": "Wathefni",
            "country": "KW",
            "timezone": "Asia/Kuwait",
            "currency": "KWD",
            "languages": ["en", "ar"],
            "branding": {"product_name": "Wathefni"},
            "sector": "Recruitment",
        },
        "org_structure": {
            "legal_entities": [{"code": "WATHEFNI", "country": "KW"}],
            "branches": [],
            "departments": [],
            "teams": [],
            "cost_centers": [],
        },
        "module_policies": {
            "modules": {
                "pre_hiring": {"live": True},
                "assessments": {"live": True},
                "interviews": {"live": True, "compatibility_protected": True},
                "video_interviews": {"live": True},
                "employment_offers": {"live": True},
                "onboarding": {"live": True},
                "compliance": {"live": True},
                "attendance": {"live": True},
                "shifts": {"live": True},
                "leave": {"live": True},
                "payroll": {"live": True},
                "analytics": {"live": True},
                "employee_app": {"live": False, "platform_flag": "off"},
            }
        },
        "notification_policies": {
            "preset": "frontline",
            "channels": {"whatsapp": "platform_global", "email": "postmark"},
            "quiet_hours": {},
        },
        "retention_policies": {
            "cv_retention_days": 730,
            "deletion_policy": "review",
            "export_policy": "owner_approved",
            "legal_hold": False,
        },
        "quotas": {
            "limits": {
                "intake_daily_message_quota": 0,
                "intake_tenant_concurrency": 1,
            }
        },
        "custom_fields": {
            "candidate_fields": [],
            "employee_fields": [],
            "required_fields": [],
        },
        "document_requirements": {"items": []},
        "workflows": {
            "approvals": {
                "shortlist": "hr",
                "reject": "hr",
                "offer": "owner_or_hr",
                "hire": "owner_or_hr",
            },
            "chains": [],
        },
        "prehire": {
            "candidates_area": {
                "single_hr_product": True,
                "split_products": False,
                "label": "Candidates",
            },
            "jobs": {"application_forms": "canonical", "apply_whatsapp": True},
            "lifecycle": {"canonical": True, "allowed_transitions": "canonical_lifecycle"},
            "notes": {
                "categories": True,
                "mentions": True,
                "attachments": True,
                "visibility": "role_scoped",
            },
            "duplicate_policy": {
                "person": "identity_authority",
                "application": "job_binding_aware",
            },
            "general_cv_intake": {
                "unified_inbound_cv": True,
                "tenants": ["WATHEFNI"],
                "channels": ["email", "whatsapp_unsolicited", "manual"],
            },
            "held_vs_admitted": {
                "authority": "inbound_cv_authority",
                "held_communication": True,
            },
            "cv_retention": {"versioning": True, "dual_write": True},
            "ranking": {"mode": "replay_only", "evidence_policy": "verified_binding"},
            "screening": {"templates": "tenant_default"},
            "assessments": {"enabled": True},
            "interviews": {"enabled": True, "compatibility_shield": True},
            "video_interviews": {"enabled": True, "async_only": True},
            "communication": {"held_authority": True, "whatsapp_platform_global": True},
            "approvals": {
                "shortlist": "hr",
                "reject": "hr",
                "offer": "owner_or_hr",
                "hire": "owner_or_hr",
            },
            "candidate_custom_fields": [],
            "backend_capabilities": {
                "candidate_knowledge": True,
                "talent_pool": True,
                "candidate_knowledge_hr_visible": False,
                "talent_pool_hr_product": False,
            },
        },
        "posthire": {
            "onboarding": {"enabled": True},
            "compliance": {"enabled": True},
            "attendance": {"enabled": True},
            "shifts": {"enabled": True, "timezone": "Asia/Kuwait"},
            "leave": {"enabled": True},
            "payroll": {"enabled": True, "employee_app_surface": False},
            "analytics": {"enabled": True},
            "employee_app": {"enabled": False, "platform_flag": "off"},
        },
    }
