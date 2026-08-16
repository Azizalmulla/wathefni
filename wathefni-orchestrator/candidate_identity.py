"""Candidates C3 identity, privacy, and human-controlled merge authority.

This module is intentionally additive and lifecycle-independent.  It never
changes application status/current_step and never performs automatic merges.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import re
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping

IDENTITY_READ = "candidates.identity.read"
IDENTITY_MANAGE = "candidates.identity.manage"
DUPLICATES_REVIEW = "candidates.duplicates.review"
MERGE_EXECUTE = "candidates.merge.execute"
MERGE_REVERSE = "candidates.merge.reverse"
PRIVACY_READ = "candidates.privacy.read"
PRIVACY_MANAGE = "candidates.privacy.manage"
PRIVACY_HOLD = "candidates.privacy.hold"
PRIVACY_EXPORT = "candidates.privacy.export"
CIVIL_ID_READ = "candidates.civil_id.read"
CIVIL_ID_WRITE = "candidates.civil_id.write"
CANDIDATE_IDENTITY_PERMISSIONS = frozenset({IDENTITY_READ, IDENTITY_MANAGE, DUPLICATES_REVIEW, MERGE_EXECUTE, MERGE_REVERSE, PRIVACY_READ, PRIVACY_MANAGE, PRIVACY_HOLD, PRIVACY_EXPORT, CIVIL_ID_READ, CIVIL_ID_WRITE})
RETENTION_DEFAULTS = {"active": (None, "review"), "rejected": (730, "review"), "withdrawn": (730, "review"), "unfinished": (365, "review"), "inactive": (365, "review"), "talent_pool": (None, "review"), "hired": (None, "review")}

# Document-channel boundary (recruiting vs post-hire onboarding).
# Candidates C3 never owns post-hire collection workflows.
RECRUITING_DOCUMENT_KINDS = frozenset({"cv", "replacement_cv", "portfolio", "application_certificate"})
ONBOARDING_DOCUMENT_KINDS = frozenset({
    "civil_id", "passport", "residency", "work_permit", "bank_details",
    "emergency_contact", "signed_employee_form", "onboarding_certificate", "compliance_document",
})
CIVIL_ID_ALLOWED_PURPOSES = frozenset({
    "onboarding_identity",
    "privacy_architecture_reference",
    "human_reviewed_match_evidence",
})
CIVIL_ID_FORBIDDEN_PURPOSES = frozenset({
    "application_required",
    "recruiting_apply",
    "candidate_whatsapp_apply",
    "ranking",
    "auto_merge",
})
DOCUMENT_CHANNEL_RECRUITING = "recruiting"
DOCUMENT_CHANNEL_ONBOARDING = "onboarding"
DOCUMENT_CHANNEL_EMPLOYEE = "employee"

# Canonical merge inventory. Only the first four tables carry mutable identity
# ownership. Application-owned descendants deliberately keep their app/file
# keys, so notes, tasks, tags, interviews, assessments, offers, hire operations,
# communications, semantic documents, and CV extraction history never move.
MERGE_REASSIGNED_ENTITY_SPECS: dict[str, dict[str, str | None]] = {
    "applications": {
        "primary_key": "app_key",
        "tenant_column": "company_code",
        "person_column": "person_id",
        "membership_column": "membership_id",
    },
    "file_registry": {
        "primary_key": "file_id",
        "tenant_column": "company_code",
        "person_column": "person_id",
        "membership_column": "membership_id",
    },
    "candidates": {
        "primary_key": "phone",
        "tenant_column": "active_company_code",
        "person_column": "person_id",
        "membership_column": None,
    },
    "person_contact_points": {
        "primary_key": "contact_id",
        "tenant_column": "company_code",
        "person_column": "person_id",
        "membership_column": None,
    },
    "ranking_run_items": {
        "primary_key": "item_id",
        "tenant_column": "company_code",
        "person_column": "person_id",
        "membership_column": "membership_id",
    },
}
MERGE_DIRECT_IDENTITY_TABLES = frozenset({
    "persons",
    "person_company_memberships",
    *MERGE_REASSIGNED_ENTITY_SPECS,
    "person_consent_records",
    "retention_operations",
    "legal_holds",
    "privacy_requests",
    "document_privacy_jobs",
})
MERGE_APPLICATION_OWNED_ENTITIES = frozenset({
    "application_lifecycle_events",
    "application_ownership_events",
    "application_notes",
    "application_note_events",
    "application_recruiter_tasks",
    "application_recruiter_task_events",
    "application_tags",
    "application_tag_events",
    "candidate_tag_dictionary",
    "candidate_action_confirmations",
    "candidate_bulk_operations",
    "candidate_bulk_operation_items",
    "batch_actions",
    "batch_action_items",
    "conversation_application_bindings",
    "candidate_interviews",
    "candidate_interview_events",
    "candidate_video_interview_questions",
    "candidate_video_interview_responses",
    "assessment_attempts",
    "assessment_events",
    "assessment_tokens",
    "assessment_invitations",
    "assessment_responses",
    "assessment_scores",
    "assessment_reports",
    "employment_offers",
    "employment_offer_versions",
    "employment_offer_events",
    "employment_offer_tokens",
    "employment_offer_deliveries",
    "employment_offer_hire_override_audits",
    "hire_operations",
    "outbound_delivery_events",
    "whatsapp_inbound_messages",
    "semantic_documents",
    "cv_extraction_runs",
    "cv_extraction_cache",
    "cv_extraction_leases",
    "candidate_rank_evaluations",
    "ranking_runs",
    "ranking_run_items",
    "ranking_item_narratives",
    "ranking_recalculation_jobs",
    "job_ranking_criteria_sets",
    "job_ranking_criteria",
})
MERGE_BLOCKING_DEPENDENCIES: dict[str, tuple[str, ...]] = {
    "legal_holds": ("active",),
    "privacy_requests": ("submitted", "verified", "approved", "processing", "blocked_hold"),
    "retention_operations": ("pending_review", "approved", "blocked_hold"),
    "document_privacy_jobs": ("queued", "processing", "retryable"),
}

class IdentityError(Exception):
    def __init__(self, code: str, *, message: str | None = None, details: Mapping[str, Any] | None = None):
        super().__init__(message or code)
        self.code, self.message, self.details = code, message or code, dict(details or {})

    def envelope(self) -> dict[str, Any]:
        return {"ok": False, "error": self.code, "message": self.message, **({"details": self.details} if self.details else {})}


def _row(value: Any) -> dict[str, Any]:
    if value is None:
        return {}
    if isinstance(value, Mapping):
        return dict(value)
    return dict(value)


def validate_company_code(company_code: str) -> str:
    value = str(company_code or "").strip().upper()
    if not value or any(ord(c) < 32 for c in value):
        raise IdentityError("tenant_scope_required")
    return value


def require_permission(permissions: Iterable[str] | None, required: str) -> None:
    if required not in set(permissions or ()):
        raise IdentityError("permission_denied", details={"required": required})


def normalize_phone(value: str) -> str:
    digits = re.sub(r"\D", "", str(value or ""))
    if len(digits) < 7 or len(digits) > 15:
        raise IdentityError("phone_invalid")
    return "+" + digits


def normalize_email(value: str) -> str:
    email = str(value or "").strip().casefold()
    if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email):
        raise IdentityError("email_invalid")
    return email


def stable_payload_hash(payload: Any) -> str:
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode()).hexdigest()


def _json(legacy: Any, value: Any) -> Any:
    return legacy.Json(value) if hasattr(legacy, "Json") else json.dumps(value, default=str)


def ensure_schema(cur: Any) -> None:
    """Install only additive C3 objects; existing lifecycle values are untouched."""
    cur.execute("""
    CREATE TABLE IF NOT EXISTS persons (person_id uuid PRIMARY KEY DEFAULT gen_random_uuid(), display_name text, display_name_ar text, preferred_locale text, status text NOT NULL DEFAULT 'active' CHECK(status IN ('active','merged','anonymized','deleted')), merged_into_person_id uuid, created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now(), metadata jsonb NOT NULL DEFAULT '{}'::jsonb);
    CREATE TABLE IF NOT EXISTS person_company_memberships (membership_id uuid PRIMARY KEY DEFAULT gen_random_uuid(), person_id uuid NOT NULL REFERENCES persons(person_id), company_code text NOT NULL, status text NOT NULL DEFAULT 'active' CHECK(status IN ('active','inactive','anonymized')), source text, first_seen_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now(), UNIQUE(person_id, company_code));
    CREATE TABLE IF NOT EXISTS person_contact_points (contact_id uuid PRIMARY KEY DEFAULT gen_random_uuid(), person_id uuid NOT NULL REFERENCES persons(person_id), company_code text, contact_type text NOT NULL CHECK(contact_type IN ('phone','email','whatsapp','civil_id')), raw_value text, normalized_value text, verified boolean NOT NULL DEFAULT false, is_preferred boolean NOT NULL DEFAULT false, purpose text, encrypted_value text, created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now());
    CREATE UNIQUE INDEX IF NOT EXISTS person_contact_phone_email_company_uq ON person_contact_points(company_code, contact_type, normalized_value) WHERE contact_type IN ('phone','email') AND normalized_value IS NOT NULL;
    ALTER TABLE IF EXISTS applications ADD COLUMN IF NOT EXISTS person_id uuid, ADD COLUMN IF NOT EXISTS membership_id uuid;
    DO $c3$
    BEGIN
      IF to_regclass('public.applications') IS NOT NULL AND NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname='applications_person_c3_fk') THEN
        ALTER TABLE applications ADD CONSTRAINT applications_person_c3_fk FOREIGN KEY(person_id) REFERENCES persons(person_id) ON DELETE RESTRICT NOT VALID;
      END IF;
      IF to_regclass('public.applications') IS NOT NULL AND NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname='applications_membership_c3_fk') THEN
        ALTER TABLE applications ADD CONSTRAINT applications_membership_c3_fk FOREIGN KEY(membership_id) REFERENCES person_company_memberships(membership_id) ON DELETE RESTRICT NOT VALID;
      END IF;
    END $c3$;
    ALTER TABLE IF EXISTS candidates ADD COLUMN IF NOT EXISTS person_id uuid;
    ALTER TABLE IF EXISTS file_registry ADD COLUMN IF NOT EXISTS person_id uuid, ADD COLUMN IF NOT EXISTS membership_id uuid;
    CREATE TABLE IF NOT EXISTS person_duplicate_suggestions (suggestion_id uuid PRIMARY KEY DEFAULT gen_random_uuid(), company_code text NOT NULL, left_person_id uuid NOT NULL, right_person_id uuid NOT NULL, score numeric NOT NULL, evidence jsonb NOT NULL DEFAULT '{}'::jsonb, status text NOT NULL DEFAULT 'open' CHECK(status IN ('open','accepted','dismissed','expired','merged')), created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now());
    CREATE TABLE IF NOT EXISTS person_merge_operations (operation_id uuid PRIMARY KEY DEFAULT gen_random_uuid(), company_code text NOT NULL, canonical_person_id uuid NOT NULL, absorbed_person_id uuid NOT NULL, actor_user_id uuid NOT NULL, confirmation_id uuid, request_hash text NOT NULL, preview_payload jsonb NOT NULL DEFAULT '{}'::jsonb, snapshot jsonb NOT NULL DEFAULT '{}'::jsonb, status text NOT NULL CONSTRAINT person_merge_operations_status_check CHECK(status IN ('previewed','processing','completed','reversed','failed')), result jsonb NOT NULL DEFAULT '{}'::jsonb, failure_reason text, reversal_result jsonb NOT NULL DEFAULT '{}'::jsonb, reversal_failure jsonb NOT NULL DEFAULT '{}'::jsonb, reverse_confirmation_id uuid, created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now(), executed_at timestamptz, reversed_at timestamptz, reverse_of_operation_id uuid);
    ALTER TABLE person_merge_operations ADD COLUMN IF NOT EXISTS result jsonb NOT NULL DEFAULT '{}'::jsonb;
    ALTER TABLE person_merge_operations ADD COLUMN IF NOT EXISTS failure_reason text;
    ALTER TABLE person_merge_operations ADD COLUMN IF NOT EXISTS reversal_result jsonb NOT NULL DEFAULT '{}'::jsonb;
    ALTER TABLE person_merge_operations ADD COLUMN IF NOT EXISTS reversal_failure jsonb NOT NULL DEFAULT '{}'::jsonb;
    ALTER TABLE person_merge_operations ADD COLUMN IF NOT EXISTS reverse_confirmation_id uuid;
    ALTER TABLE person_merge_operations ADD COLUMN IF NOT EXISTS updated_at timestamptz NOT NULL DEFAULT now();
    DO $c3$
    BEGIN
      IF EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conrelid='person_merge_operations'::regclass
          AND conname='person_merge_operations_status_check'
          AND pg_get_constraintdef(oid) NOT LIKE '%processing%'
      ) THEN
        ALTER TABLE person_merge_operations DROP CONSTRAINT person_merge_operations_status_check;
        ALTER TABLE person_merge_operations ADD CONSTRAINT person_merge_operations_status_check
          CHECK(status IN ('previewed','processing','completed','reversed','failed'));
      END IF;
    END $c3$;
    CREATE UNIQUE INDEX IF NOT EXISTS person_merge_operations_request_uq ON person_merge_operations(company_code, request_hash);
    CREATE TABLE IF NOT EXISTS person_merge_operation_items (
      item_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
      operation_id uuid NOT NULL REFERENCES person_merge_operations(operation_id),
      company_code text NOT NULL,
      phase text NOT NULL DEFAULT 'merge' CHECK(phase IN ('merge','reversal')),
      source_item_id uuid,
      entity_type text NOT NULL,
      entity_id text NOT NULL,
      pre_person_id uuid,
      pre_membership_id uuid,
      post_person_id uuid,
      post_membership_id uuid,
      from_person_id uuid,
      to_person_id uuid,
      pre_fingerprint text NOT NULL,
      post_fingerprint text NOT NULL,
      action_taken text NOT NULL,
      result_status text NOT NULL,
      metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
      created_at timestamptz NOT NULL DEFAULT now()
    );
    ALTER TABLE person_merge_operation_items ADD COLUMN IF NOT EXISTS company_code text;
    ALTER TABLE person_merge_operation_items ADD COLUMN IF NOT EXISTS phase text NOT NULL DEFAULT 'merge';
    ALTER TABLE person_merge_operation_items ADD COLUMN IF NOT EXISTS source_item_id uuid;
    ALTER TABLE person_merge_operation_items ADD COLUMN IF NOT EXISTS pre_person_id uuid;
    ALTER TABLE person_merge_operation_items ADD COLUMN IF NOT EXISTS pre_membership_id uuid;
    ALTER TABLE person_merge_operation_items ADD COLUMN IF NOT EXISTS post_person_id uuid;
    ALTER TABLE person_merge_operation_items ADD COLUMN IF NOT EXISTS post_membership_id uuid;
    ALTER TABLE person_merge_operation_items ADD COLUMN IF NOT EXISTS from_person_id uuid;
    ALTER TABLE person_merge_operation_items ADD COLUMN IF NOT EXISTS to_person_id uuid;
    ALTER TABLE person_merge_operation_items ADD COLUMN IF NOT EXISTS pre_fingerprint text;
    ALTER TABLE person_merge_operation_items ADD COLUMN IF NOT EXISTS post_fingerprint text;
    ALTER TABLE person_merge_operation_items ADD COLUMN IF NOT EXISTS action_taken text;
    ALTER TABLE person_merge_operation_items ADD COLUMN IF NOT EXISTS metadata jsonb NOT NULL DEFAULT '{}'::jsonb;
    ALTER TABLE person_merge_operation_items ADD COLUMN IF NOT EXISTS created_at timestamptz NOT NULL DEFAULT now();
    UPDATE person_merge_operation_items i SET
      company_code=o.company_code,
      pre_person_id=COALESCE(i.pre_person_id, i.from_person_id),
      post_person_id=COALESCE(i.post_person_id, i.to_person_id),
      pre_fingerprint=COALESCE(i.pre_fingerprint, md5(i.entity_type || ':' || i.entity_id || ':legacy-pre')),
      post_fingerprint=COALESCE(i.post_fingerprint, md5(i.entity_type || ':' || i.entity_id || ':legacy-post')),
      action_taken=COALESCE(i.action_taken, 'legacy')
    FROM person_merge_operations o
    WHERE i.operation_id=o.operation_id
      AND (i.company_code IS NULL OR i.pre_fingerprint IS NULL OR i.post_fingerprint IS NULL OR i.action_taken IS NULL);
    ALTER TABLE person_merge_operation_items ALTER COLUMN company_code SET NOT NULL;
    ALTER TABLE person_merge_operation_items ALTER COLUMN pre_fingerprint SET NOT NULL;
    ALTER TABLE person_merge_operation_items ALTER COLUMN post_fingerprint SET NOT NULL;
    ALTER TABLE person_merge_operation_items ALTER COLUMN action_taken SET NOT NULL;
    CREATE UNIQUE INDEX IF NOT EXISTS person_merge_operation_items_entity_uq
      ON person_merge_operation_items(operation_id,phase,entity_type,entity_id);
    CREATE OR REPLACE FUNCTION prevent_person_merge_item_mutation() RETURNS trigger AS $$
    BEGIN
      IF COALESCE(current_setting('wathefni.c3_ledger_maintenance', true), '') <> 'on' THEN
        RAISE EXCEPTION 'person_merge_operation_items_immutable' USING ERRCODE='P0001';
      END IF;
      RETURN OLD;
    END;
    $$ LANGUAGE plpgsql;
    DROP TRIGGER IF EXISTS person_merge_operation_items_immutable_guard ON person_merge_operation_items;
    CREATE TRIGGER person_merge_operation_items_immutable_guard
      BEFORE UPDATE OR DELETE ON person_merge_operation_items
      FOR EACH ROW EXECUTE FUNCTION prevent_person_merge_item_mutation();
    CREATE TABLE IF NOT EXISTS candidate_c3_confirmations (confirmation_id uuid PRIMARY KEY DEFAULT gen_random_uuid(), company_code text NOT NULL, actor_user_id uuid NOT NULL, action text NOT NULL, payload_hash text NOT NULL, token_hash text NOT NULL, payload jsonb NOT NULL, status text NOT NULL DEFAULT 'pending', expires_at timestamptz NOT NULL, consumed_at timestamptz, CHECK(status IN ('pending','consumed','expired','cancelled')));
    CREATE TABLE IF NOT EXISTS person_consent_records (consent_id uuid PRIMARY KEY DEFAULT gen_random_uuid(), company_code text NOT NULL, person_id uuid NOT NULL, purpose text NOT NULL, policy_version text, locale text, acquisition_surface text, status text NOT NULL CHECK(status IN ('granted','withdrawn')), granted_at timestamptz NOT NULL DEFAULT now(), withdrawn_at timestamptz, evidence_ref text, metadata jsonb NOT NULL DEFAULT '{}'::jsonb);
    CREATE TABLE IF NOT EXISTS tenant_retention_policies (policy_id uuid PRIMARY KEY DEFAULT gen_random_uuid(), company_code text NOT NULL, entity_class text NOT NULL, retain_days integer, action text NOT NULL CHECK(action IN ('review','anonymize','delete')), metadata jsonb NOT NULL DEFAULT '{}'::jsonb, UNIQUE(company_code, entity_class));
    CREATE TABLE IF NOT EXISTS retention_operations (operation_id uuid PRIMARY KEY DEFAULT gen_random_uuid(), company_code text NOT NULL, person_id uuid, entity_class text NOT NULL, entity_ref text, due_at timestamptz, status text NOT NULL CHECK(status IN ('pending_review','approved','rejected','completed','blocked_hold')), actor_user_id uuid, result jsonb NOT NULL DEFAULT '{}'::jsonb);
    CREATE TABLE IF NOT EXISTS legal_holds (hold_id uuid PRIMARY KEY DEFAULT gen_random_uuid(), company_code text NOT NULL, person_id uuid NOT NULL, scope text NOT NULL, reason text NOT NULL, case_reference text, status text NOT NULL DEFAULT 'active' CHECK(status IN ('active','released')), placed_by_user_id uuid NOT NULL, placed_at timestamptz NOT NULL DEFAULT now(), released_by_user_id uuid, released_at timestamptz, confirmation_id uuid);
    CREATE TABLE IF NOT EXISTS privacy_requests (request_id uuid PRIMARY KEY DEFAULT gen_random_uuid(), company_code text NOT NULL, person_id uuid NOT NULL, request_type text NOT NULL CHECK(request_type IN ('export','delete','anonymize')), status text NOT NULL CHECK(status IN ('submitted','verified','approved','processing','completed','failed','rejected','blocked_hold')), verification_state text, actor_user_id uuid, result jsonb NOT NULL DEFAULT '{}'::jsonb, created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now());
    CREATE TABLE IF NOT EXISTS privacy_request_events (event_id uuid PRIMARY KEY DEFAULT gen_random_uuid(), request_id uuid NOT NULL REFERENCES privacy_requests(request_id), company_code text NOT NULL, event_type text NOT NULL, actor_user_id uuid, payload jsonb NOT NULL DEFAULT '{}'::jsonb, created_at timestamptz NOT NULL DEFAULT now());
    CREATE TABLE IF NOT EXISTS document_privacy_jobs (job_id uuid PRIMARY KEY DEFAULT gen_random_uuid(), company_code text NOT NULL, file_id text NOT NULL, person_id uuid, action text NOT NULL CHECK(action IN ('delete','anonymize','reassociate')), document_channel text NOT NULL DEFAULT 'recruiting' CHECK(document_channel IN ('recruiting','onboarding','employee')), status text NOT NULL DEFAULT 'queued' CHECK(status IN ('queued','processing','retryable','completed','failed')), storage_result jsonb NOT NULL DEFAULT '{}'::jsonb, attempts integer NOT NULL DEFAULT 0, last_error text, created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now());
    ALTER TABLE IF EXISTS document_privacy_jobs ADD COLUMN IF NOT EXISTS document_channel text;
    """)


def assert_no_cv_processing_authority() -> None:
    """Hard contract: C3 must not own CV extraction/OCR/ranking pipelines."""
    forbidden = (
        "def ensure_cv_extraction_schema",
        "def extract_cv",
        "mistral-ocr",
        "CREATE TABLE IF NOT EXISTS cv_extraction",
        "def rank_candidates",
    )
    # References to canonical application/file-owned CV tables are allowed for
    # inventory and invariant proof; defining a parser/cache/lease/ranker is not.
    body = Path(__file__).read_text(encoding="utf-8").split("def assert_no_cv_processing_authority", 1)[0]
    for token in forbidden:
        if token in body:
            raise IdentityError("cv_authority_boundary_violated", details={"token": token})


def classify_document_channel(document_kind: str | None, *, lifecycle_stage: str | None = None) -> str:
    kind = str(document_kind or "").strip().lower()
    stage = str(lifecycle_stage or "").strip().lower()
    if kind in ONBOARDING_DOCUMENT_KINDS or stage in {"hired", "onboarding", "employee"}:
        return DOCUMENT_CHANNEL_ONBOARDING if stage != "employee" else DOCUMENT_CHANNEL_EMPLOYEE
    if kind in RECRUITING_DOCUMENT_KINDS or not kind:
        return DOCUMENT_CHANNEL_RECRUITING
    # Unknown kinds default to recruiting association for privacy jobs only; workflow ownership stays with source module.
    return DOCUMENT_CHANNEL_RECRUITING


def validate_civil_id_purpose(purpose: str | None) -> str:
    value = str(purpose or "onboarding_identity").strip().lower() or "onboarding_identity"
    if value in CIVIL_ID_FORBIDDEN_PURPOSES:
        raise IdentityError("civil_id_purpose_forbidden_in_recruiting", details={"purpose": value})
    if value not in CIVIL_ID_ALLOWED_PURPOSES:
        raise IdentityError("civil_id_purpose_invalid", details={"purpose": value})
    return value


def ensure_default_retention_policies(cur: Any, company_code: str) -> None:
    company_code = validate_company_code(company_code)
    for entity_class, (days, action) in RETENTION_DEFAULTS.items():
        cur.execute("INSERT INTO tenant_retention_policies(company_code,entity_class,retain_days,action) VALUES (%s,%s,%s,%s) ON CONFLICT(company_code,entity_class) DO NOTHING", (company_code, entity_class, days, action))


def assert_tenant_membership_scoped_read(cur: Any, company_code: str, person_id: str) -> dict[str, Any]:
    company_code = validate_company_code(company_code)
    cur.execute("SELECT p.*, m.membership_id, m.status AS membership_status FROM persons p JOIN person_company_memberships m ON m.person_id=p.person_id WHERE m.company_code=%s AND p.person_id=%s AND m.status='active'", (company_code, person_id))
    row = _row(cur.fetchone())
    if not row:
        raise IdentityError("person_not_found_or_cross_tenant")
    return row


def get_person_tenant_view(legacy: Any, company_code: str, person_id: str, permissions: Iterable[str]) -> dict[str, Any]:
    require_permission(permissions, IDENTITY_READ)
    with legacy.db_connect() as conn:
        with conn.cursor() as cur:
            person = assert_tenant_membership_scoped_read(cur, company_code, person_id)
            contacts = list_membership_contacts(cur, company_code, person_id, permissions)
    return {"person": person, "contacts": contacts}


def list_membership_contacts(cur: Any, company_code: str, person_id: str, permissions: Iterable[str]) -> list[dict[str, Any]]:
    assert_tenant_membership_scoped_read(cur, company_code, person_id)
    cur.execute("SELECT contact_id, person_id, company_code, contact_type, normalized_value, verified, is_preferred, purpose, created_at, updated_at, encrypted_value FROM person_contact_points WHERE person_id=%s AND (company_code=%s OR company_code IS NULL) ORDER BY created_at", (person_id, validate_company_code(company_code)))
    result = []
    for contact in cur.fetchall():
        value = _row(contact)
        if value.get("contact_type") == "civil_id":
            value.pop("encrypted_value", None)
            value["normalized_value"] = decrypt_civil_id(_row(contact).get("encrypted_value")) if CIVIL_ID_READ in set(permissions or ()) else None
        result.append(value)
    return result


def _civil_key() -> bytes:
    key = os.getenv("WATHEFNI_CIVIL_ID_KEY")
    if not key:
        raise IdentityError("civil_id_key_missing")
    return key.encode()


def encrypt_civil_id(value: str) -> str:
    key = _civil_key()
    try:
        from cryptography.fernet import Fernet
        return "fernet:" + Fernet(key).encrypt(value.encode()).decode()
    except ImportError:
        nonce = secrets.token_bytes(16)
        stream = hmac.new(key, nonce, hashlib.sha256).digest()
        ciphertext = bytes(b ^ stream[i % len(stream)] for i, b in enumerate(value.encode()))
        return "hmac:" + base64.urlsafe_b64encode(nonce + ciphertext).decode()


def decrypt_civil_id(blob: str | None) -> str | None:
    if not blob:
        return None
    key = _civil_key()
    if blob.startswith("fernet:"):
        from cryptography.fernet import Fernet
        return Fernet(key).decrypt(blob[7:].encode()).decode()
    if blob.startswith("hmac:"):
        data = base64.urlsafe_b64decode(blob[5:].encode()); nonce, ciphertext = data[:16], data[16:]
        stream = hmac.new(key, nonce, hashlib.sha256).digest()
        return bytes(b ^ stream[i % len(stream)] for i, b in enumerate(ciphertext)).decode()
    raise IdentityError("civil_id_ciphertext_invalid")


def add_contact_point(cur: Any, *, company_code: str, person_id: str, contact_type: str, value: str, permissions: Iterable[str], verified: bool = False, is_preferred: bool = False, purpose: str | None = None) -> dict[str, Any]:
    company_code = validate_company_code(company_code); assert_tenant_membership_scoped_read(cur, company_code, person_id)
    if contact_type not in {"phone", "email", "whatsapp", "civil_id"}: raise IdentityError("contact_type_invalid")
    encrypted = None
    if contact_type == "civil_id":
        # Civil ID is never part of the normal recruiting apply channel.
        purpose = validate_civil_id_purpose(purpose)
        require_permission(permissions, CIVIL_ID_WRITE)
        encrypted = encrypt_civil_id(str(value))
        normalized = None
        raw = None
    else:
        normalized = normalize_phone(value) if contact_type in {"phone", "whatsapp"} else normalize_email(value); raw = value
    cur.execute("INSERT INTO person_contact_points(person_id,company_code,contact_type,raw_value,normalized_value,verified,is_preferred,purpose,encrypted_value) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING contact_id, person_id, company_code, contact_type, normalized_value, verified, is_preferred, purpose", (person_id, company_code, contact_type, raw, normalized, verified, is_preferred, purpose, encrypted))
    return _row(cur.fetchone())


def build_match_evidence(left: Mapping[str, Any], right: Mapping[str, Any], *, permissions: Iterable[str] = ()) -> dict[str, Any]:
    lp, rp = set(left.get("phones", ())), set(right.get("phones", ()))
    le, re_ = set(left.get("emails", ())), set(right.get("emails", ()))
    evidence = {"shared_phones": sorted(lp & rp), "shared_emails": sorted(le & re_), "civil_id_match_evidence": False, "advisory_only": True}
    if CIVIL_ID_READ in set(permissions) and left.get("civil_id") and right.get("civil_id"):
        evidence["civil_id_match_evidence"] = hmac.compare_digest(str(left["civil_id"]), str(right["civil_id"]))
    return evidence


def create_duplicate_suggestion(cur: Any, *, company_code: str, left_person_id: str, right_person_id: str, score: float, evidence: Mapping[str, Any], permissions: Iterable[str]) -> dict[str, Any]:
    require_permission(permissions, DUPLICATES_REVIEW)
    if left_person_id == right_person_id: raise IdentityError("duplicate_same_person")
    assert_tenant_membership_scoped_read(cur, company_code, left_person_id); assert_tenant_membership_scoped_read(cur, company_code, right_person_id)
    cur.execute("INSERT INTO person_duplicate_suggestions(company_code,left_person_id,right_person_id,score,evidence) VALUES (%s,%s,%s,%s,%s) RETURNING *", (validate_company_code(company_code), left_person_id, right_person_id, score, json.dumps(dict(evidence))))
    return _row(cur.fetchone())


def list_duplicate_suggestions(cur: Any, *, company_code: str, permissions: Iterable[str]) -> list[dict[str, Any]]:
    require_permission(permissions, DUPLICATES_REVIEW)
    cur.execute("SELECT * FROM person_duplicate_suggestions WHERE company_code=%s AND status='open' ORDER BY score DESC, created_at", (validate_company_code(company_code),))
    rows = [_row(r) for r in cur.fetchall()]
    return [sanitize_match_evidence_for_viewer(row, permissions) for row in rows]


def sanitize_match_evidence_for_viewer(row: Mapping[str, Any], permissions: Iterable[str]) -> dict[str, Any]:
    """Hide Civil ID match evidence from viewers without civil_id.read."""
    out = dict(row)
    evidence = out.get("evidence")
    if isinstance(evidence, str):
        try:
            evidence = json.loads(evidence)
        except Exception:
            evidence = {}
    if not isinstance(evidence, Mapping):
        evidence = {}
    evidence = dict(evidence)
    if CIVIL_ID_READ not in set(permissions or ()):
        evidence.pop("civil_id_match_evidence", None)
        evidence["civil_id_match_evidence_redacted"] = True
    out["evidence"] = evidence
    return out


def assert_hire_handoff_preserves_document_boundary() -> dict[str, Any]:
    """Contract: hiring links person→employee without moving/exposing recruiting docs.

    Onboarding remains the authority for post-hire document requests and completion.
    """
    return {
        "links_person_to_employee": True,
        "auto_moves_recruiting_documents": False,
        "exposes_recruiting_docs_to_employee_channel": False,
        "onboarding_owns_post_hire_collection": True,
        "candidate_whatsapp_sensitive_upload_default": False,
    }


def dismiss_duplicate_suggestion(cur: Any, *, company_code: str, suggestion_id: str, permissions: Iterable[str]) -> None:
    require_permission(permissions, DUPLICATES_REVIEW); cur.execute("UPDATE person_duplicate_suggestions SET status='dismissed',updated_at=now() WHERE company_code=%s AND suggestion_id=%s AND status='open'", (validate_company_code(company_code), suggestion_id))


def mint_c3_confirmation(cur: Any, *, company_code: str, actor_user_id: str, action: str, payload: Mapping[str, Any], ttl_seconds: int = 600) -> dict[str, Any]:
    token = secrets.token_urlsafe(32); payload_hash = stable_payload_hash(payload)
    cur.execute("INSERT INTO candidate_c3_confirmations(company_code,actor_user_id,action,payload_hash,token_hash,payload,expires_at) VALUES (%s,%s,%s,%s,%s,%s,now()+(%s * interval '1 second')) RETURNING confirmation_id,expires_at", (validate_company_code(company_code), actor_user_id, action, payload_hash, hashlib.sha256(token.encode()).hexdigest(), json.dumps(dict(payload)), ttl_seconds))
    result = _row(cur.fetchone()); result["token"] = token; result["payload_hash"] = payload_hash; return result


def consume_c3_confirmation(cur: Any, *, company_code: str, actor_user_id: str, action: str, payload: Mapping[str, Any], token: str) -> str:
    cur.execute("UPDATE candidate_c3_confirmations SET status='consumed',consumed_at=now() WHERE company_code=%s AND actor_user_id=%s AND action=%s AND payload_hash=%s AND token_hash=%s AND status='pending' AND expires_at>now() RETURNING confirmation_id", (validate_company_code(company_code), actor_user_id, action, stable_payload_hash(payload), hashlib.sha256(token.encode()).hexdigest()))
    row = _row(cur.fetchone())
    if not row: raise IdentityError("confirmation_invalid_or_expired")
    return str(row["confirmation_id"])


def preview_merge(cur: Any, *, company_code: str, canonical_person_id: str, absorbed_person_id: str, actor_user_id: str, permissions: Iterable[str]) -> dict[str, Any]:
    require_permission(permissions, MERGE_EXECUTE)
    canonical = assert_tenant_membership_scoped_read(cur, company_code, canonical_person_id); absorbed = assert_tenant_membership_scoped_read(cur, company_code, absorbed_person_id)
    if canonical_person_id == absorbed_person_id: raise IdentityError("merge_same_person")
    payload = {"company_code": validate_company_code(company_code), "canonical_person_id": canonical_person_id, "absorbed_person_id": absorbed_person_id, "versions": {canonical_person_id: str(canonical.get("updated_at")), absorbed_person_id: str(absorbed.get("updated_at"))}, "memberships": sorted([str(canonical.get("membership_id")), str(absorbed.get("membership_id"))])}
    payload["request_hash"] = stable_payload_hash(payload); return payload


def _json_object(value: Any) -> dict[str, Any]:
    if isinstance(value, Mapping):
        return dict(value)
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
            return dict(parsed) if isinstance(parsed, Mapping) else {}
        except (TypeError, ValueError):
            return {}
    return {}


def _same_id(left: Any, right: Any) -> bool:
    return (str(left) if left is not None else None) == (str(right) if right is not None else None)


def _safe_identifier(value: str) -> str:
    if not re.fullmatch(r"[a-z_][a-z0-9_]*", value):
        raise IdentityError("merge_inventory_identifier_invalid", details={"identifier": value})
    return value


def _validate_merge_request(preview: Mapping[str, Any]) -> tuple[str, str]:
    supplied = str(preview.get("request_hash") or "")
    payload = {key: value for key, value in dict(preview).items() if key != "request_hash"}
    expected = stable_payload_hash(payload)
    if not supplied or not hmac.compare_digest(supplied, expected):
        raise IdentityError("merge_request_hash_invalid", details={"expected_request_hash": expected})
    return validate_company_code(str(preview.get("company_code") or "")), supplied


def _fetch_merge_operation(cur: Any, company_code: str, request_hash: str, *, lock: bool = False) -> dict[str, Any]:
    cur.execute(
        "SELECT * FROM person_merge_operations WHERE company_code=%s AND request_hash=%s" + (" FOR UPDATE" if lock else ""),
        (company_code, request_hash),
    )
    return _row(cur.fetchone())


def _operation_response(operation: Mapping[str, Any], *, idempotent: bool) -> dict[str, Any]:
    result = _json_object(operation.get("result"))
    return {"operation": dict(operation), "result": result, "idempotent": idempotent}


def _lock_merge_identities(
    cur: Any,
    *,
    company_code: str,
    canonical_person_id: str,
    absorbed_person_id: str,
) -> dict[str, dict[str, Any]]:
    if canonical_person_id == absorbed_person_id:
        raise IdentityError("merge_same_person")
    cur.execute(
        """
        SELECT p.*, m.membership_id, m.status AS membership_status,
               m.updated_at AS membership_updated_at,
               md5(to_jsonb(p)::text) AS person_fingerprint,
               md5(to_jsonb(m)::text) AS membership_fingerprint
        FROM persons p
        JOIN person_company_memberships m ON m.person_id=p.person_id
        WHERE m.company_code=%s AND p.person_id=ANY(%s::uuid[])
        ORDER BY p.person_id
        FOR UPDATE OF p,m
        """,
        (company_code, [canonical_person_id, absorbed_person_id]),
    )
    rows = {_row(row).get("person_id"): _row(row) for row in (cur.fetchall() or [])}
    normalized = {str(key): value for key, value in rows.items() if key is not None}
    if set(normalized) != {canonical_person_id, absorbed_person_id}:
        raise IdentityError("person_not_found_or_cross_tenant")
    for person_id, row in normalized.items():
        if row.get("status") != "active" or row.get("membership_status") != "active":
            raise IdentityError("merge_identity_not_active", details={"person_id": person_id})
    return normalized


def _locked_preview(
    company_code: str,
    canonical_person_id: str,
    absorbed_person_id: str,
    identities: Mapping[str, Mapping[str, Any]],
) -> dict[str, Any]:
    payload = {
        "company_code": company_code,
        "canonical_person_id": canonical_person_id,
        "absorbed_person_id": absorbed_person_id,
        "versions": {
            canonical_person_id: str(identities[canonical_person_id].get("updated_at")),
            absorbed_person_id: str(identities[absorbed_person_id].get("updated_at")),
        },
        "memberships": sorted([
            str(identities[canonical_person_id].get("membership_id")),
            str(identities[absorbed_person_id].get("membership_id")),
        ]),
    }
    payload["request_hash"] = stable_payload_hash(payload)
    return payload


def _collect_merge_blockers(
    cur: Any,
    *,
    company_code: str,
    canonical_person_id: str,
    absorbed_person_id: str,
    canonical_membership_id: str,
    absorbed_membership_id: str,
) -> list[dict[str, Any]]:
    blockers: list[dict[str, Any]] = []
    cur.execute(
        """
        SELECT membership_id,person_id,company_code,status
        FROM person_company_memberships
        WHERE person_id=ANY(%s::uuid[]) AND company_code<>%s AND status='active'
        ORDER BY company_code,membership_id
        """,
        ([canonical_person_id, absorbed_person_id], company_code),
    )
    for row in cur.fetchall() or []:
        blockers.append({"entity_type": "person_company_memberships", "entity_id": str(_row(row).get("membership_id")), "reason": "active_cross_tenant_membership"})

    for table, spec in MERGE_REASSIGNED_ENTITY_SPECS.items():
        table = _safe_identifier(table)
        tenant = _safe_identifier(str(spec["tenant_column"]))
        person = _safe_identifier(str(spec["person_column"]))
        membership = spec.get("membership_column")
        condition = f"{person}=%s"
        params: list[Any] = [company_code, absorbed_person_id]
        if membership:
            membership = _safe_identifier(str(membership))
            condition += f" OR {membership}=%s"
            params.append(absorbed_membership_id)
        cur.execute(
            f"SELECT count(*) AS n FROM {table} WHERE {tenant}<>%s AND ({condition})",
            tuple(params),
        )
        count = int(_row(cur.fetchone()).get("n") or 0)
        if count:
            blockers.append({"entity_type": table, "entity_id": "*", "reason": "cross_tenant_identity_reference", "count": count})

    cur.execute(
        "SELECT contact_id FROM person_contact_points WHERE person_id=%s AND company_code IS NULL FOR UPDATE",
        (absorbed_person_id,),
    )
    for row in cur.fetchall() or []:
        blockers.append({"entity_type": "person_contact_points", "entity_id": str(_row(row).get("contact_id")), "reason": "global_contact_requires_separate_authority"})

    for table, statuses in MERGE_BLOCKING_DEPENDENCIES.items():
        table = _safe_identifier(table)
        cur.execute(
            f"SELECT * FROM {table} WHERE company_code=%s AND person_id=ANY(%s::uuid[]) AND status=ANY(%s) FOR UPDATE",
            (company_code, [canonical_person_id, absorbed_person_id], list(statuses)),
        )
        for row in cur.fetchall() or []:
            value = _row(row)
            entity_id = next((value.get(key) for key in ("hold_id", "request_id", "operation_id", "job_id") if value.get(key)), "*")
            blockers.append({"entity_type": table, "entity_id": str(entity_id), "reason": "active_privacy_or_legal_dependency", "status": value.get("status")})

    cur.execute(
        """
        SELECT table_name,array_agg(column_name ORDER BY column_name) AS columns
        FROM information_schema.columns
        WHERE table_schema='public' AND column_name IN ('person_id','membership_id')
        GROUP BY table_name
        ORDER BY table_name
        """
    )
    for row in cur.fetchall() or []:
        value = _row(row)
        table = str(value.get("table_name") or "")
        if table in MERGE_DIRECT_IDENTITY_TABLES:
            continue
        columns = {str(column) for column in (value.get("columns") or [])}
        conditions: list[str] = []
        params = []
        if "person_id" in columns:
            conditions.append("person_id=%s")
            params.append(absorbed_person_id)
        if "membership_id" in columns:
            conditions.append("membership_id=%s")
            params.append(absorbed_membership_id)
        if conditions:
            table = _safe_identifier(table)
            cur.execute(f"SELECT count(*) AS n FROM {table} WHERE {' OR '.join(conditions)}", tuple(params))
            count = int(_row(cur.fetchone()).get("n") or 0)
            if count:
                blockers.append({"entity_type": table, "entity_id": "*", "reason": "unclassified_identity_reference", "count": count})
    return blockers


def _insert_merge_item(
    cur: Any,
    *,
    operation_id: str,
    company_code: str,
    phase: str,
    entity_type: str,
    entity_id: str,
    pre_person_id: Any,
    pre_membership_id: Any,
    post_person_id: Any,
    post_membership_id: Any,
    pre_fingerprint: str,
    post_fingerprint: str,
    action_taken: str,
    metadata: Mapping[str, Any] | None = None,
    source_item_id: str | None = None,
) -> dict[str, Any]:
    cur.execute(
        """
        INSERT INTO person_merge_operation_items(
          operation_id,company_code,phase,source_item_id,entity_type,entity_id,
          pre_person_id,pre_membership_id,post_person_id,post_membership_id,
          from_person_id,to_person_id,pre_fingerprint,post_fingerprint,
          action_taken,result_status,metadata
        ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'applied',%s)
        RETURNING *
        """,
        (
            operation_id,
            company_code,
            phase,
            source_item_id,
            entity_type,
            entity_id,
            pre_person_id,
            pre_membership_id,
            post_person_id,
            post_membership_id,
            pre_person_id,
            post_person_id,
            pre_fingerprint,
            post_fingerprint,
            action_taken,
            json.dumps(dict(metadata or {}), default=str),
        ),
    )
    return _row(cur.fetchone())


def _lock_reassigned_rows(
    cur: Any,
    *,
    table: str,
    spec: Mapping[str, str | None],
    company_code: str,
    absorbed_person_id: str,
    absorbed_membership_id: str,
) -> list[dict[str, Any]]:
    table = _safe_identifier(table)
    primary_key = _safe_identifier(str(spec["primary_key"]))
    tenant = _safe_identifier(str(spec["tenant_column"]))
    person = _safe_identifier(str(spec["person_column"]))
    membership = spec.get("membership_column")
    condition = f"{person}=%s"
    params: list[Any] = [company_code, absorbed_person_id]
    if membership:
        membership = _safe_identifier(str(membership))
        condition += f" OR {membership}=%s"
        params.append(absorbed_membership_id)
    cur.execute(
        f"""
        SELECT t.*, {primary_key}::text AS entity_id,
               md5(to_jsonb(t)::text) AS fingerprint
        FROM {table} t
        WHERE {tenant}=%s AND ({condition})
        ORDER BY {primary_key}::text
        FOR UPDATE
        """,
        tuple(params),
    )
    return [_row(row) for row in (cur.fetchall() or [])]


def _reassign_row(
    cur: Any,
    *,
    operation_id: str,
    company_code: str,
    table: str,
    spec: Mapping[str, str | None],
    row: Mapping[str, Any],
    canonical_person_id: str,
    canonical_membership_id: str,
) -> None:
    table = _safe_identifier(table)
    primary_key = _safe_identifier(str(spec["primary_key"]))
    tenant = _safe_identifier(str(spec["tenant_column"]))
    person = _safe_identifier(str(spec["person_column"]))
    membership = spec.get("membership_column")
    assignments = [f"{person}=%s"]
    params: list[Any] = [canonical_person_id]
    if membership:
        membership = _safe_identifier(str(membership))
        assignments.append(f"{membership}=%s")
        params.append(canonical_membership_id)
    params.extend([str(row["entity_id"]), company_code])
    cur.execute(
        f"""
        WITH changed AS (
          UPDATE {table}
          SET {','.join(assignments)}
          WHERE {primary_key}::text=%s AND {tenant}=%s
          RETURNING *
        )
        SELECT changed.*, md5(to_jsonb(changed)::text) AS fingerprint FROM changed
        """,
        tuple(params),
    )
    after = _row(cur.fetchone())
    if not after:
        raise IdentityError("merge_entity_update_missing", details={"entity_type": table, "entity_id": row["entity_id"]})
    _insert_merge_item(
        cur,
        operation_id=operation_id,
        company_code=company_code,
        phase="merge",
        entity_type=table,
        entity_id=str(row["entity_id"]),
        pre_person_id=row.get(person),
        pre_membership_id=row.get(membership) if membership else None,
        post_person_id=after.get(person),
        post_membership_id=after.get(membership) if membership else None,
        pre_fingerprint=str(row.get("fingerprint") or ""),
        post_fingerprint=str(after.get("fingerprint") or ""),
        action_taken="reassigned",
        metadata={"primary_key": primary_key, "tenant_column": tenant},
    )


def _current_item_state(cur: Any, item: Mapping[str, Any], *, lock: bool = False) -> dict[str, Any]:
    entity_type = str(item.get("entity_type") or "")
    entity_id = str(item.get("entity_id") or "")
    company_code = str(item.get("company_code") or "")
    suffix = " FOR UPDATE" if lock else ""
    if entity_type in MERGE_REASSIGNED_ENTITY_SPECS:
        spec = MERGE_REASSIGNED_ENTITY_SPECS[entity_type]
        primary_key = _safe_identifier(str(spec["primary_key"]))
        tenant = _safe_identifier(str(spec["tenant_column"]))
        person = _safe_identifier(str(spec["person_column"]))
        membership = spec.get("membership_column")
        columns = f"{person} AS person_id"
        if membership:
            columns += f",{_safe_identifier(str(membership))} AS membership_id"
        else:
            columns += ",NULL::uuid AS membership_id"
        cur.execute(
            f"SELECT {columns},md5(to_jsonb(t)::text) AS fingerprint FROM {entity_type} t WHERE {primary_key}::text=%s AND {tenant}=%s{suffix}",
            (entity_id, company_code),
        )
    elif entity_type == "persons":
        cur.execute(f"SELECT person_id,NULL::uuid AS membership_id,md5(to_jsonb(t)::text) AS fingerprint FROM persons t WHERE person_id=%s{suffix}", (entity_id,))
    elif entity_type == "person_company_memberships":
        cur.execute(f"SELECT person_id,membership_id,md5(to_jsonb(t)::text) AS fingerprint FROM person_company_memberships t WHERE membership_id=%s AND company_code=%s{suffix}", (entity_id, company_code))
    elif entity_type == "person_duplicate_suggestions":
        cur.execute(f"SELECT NULL::uuid AS person_id,NULL::uuid AS membership_id,md5(to_jsonb(t)::text) AS fingerprint FROM person_duplicate_suggestions t WHERE suggestion_id=%s AND company_code=%s{suffix}", (entity_id, company_code))
    else:
        raise IdentityError("merge_item_entity_unclassified", details={"entity_type": entity_type, "entity_id": entity_id})
    return _row(cur.fetchone())


def _verify_operation_items(cur: Any, *, operation_id: str, phase: str, lock: bool = False) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    cur.execute(
        "SELECT * FROM person_merge_operation_items WHERE operation_id=%s AND phase=%s AND result_status='applied' ORDER BY created_at,item_id",
        (operation_id, phase),
    )
    items = [_row(row) for row in (cur.fetchall() or [])]
    blockers: list[dict[str, Any]] = []
    for item in items:
        current = _current_item_state(cur, item, lock=lock)
        if not current:
            blockers.append({"entity_type": item.get("entity_type"), "entity_id": item.get("entity_id"), "reason": "entity_missing"})
            continue
        if not _same_id(current.get("person_id"), item.get("post_person_id")):
            blockers.append({"entity_type": item.get("entity_type"), "entity_id": item.get("entity_id"), "reason": "post_person_mapping_changed"})
        if not _same_id(current.get("membership_id"), item.get("post_membership_id")):
            blockers.append({"entity_type": item.get("entity_type"), "entity_id": item.get("entity_id"), "reason": "post_membership_mapping_changed"})
        if str(current.get("fingerprint") or "") != str(item.get("post_fingerprint") or ""):
            blockers.append({"entity_type": item.get("entity_type"), "entity_id": item.get("entity_id"), "reason": "post_merge_fingerprint_changed"})
    return items, blockers


def _verify_merge_invariants(
    cur: Any,
    *,
    operation_id: str,
    company_code: str,
    absorbed_person_id: str,
    absorbed_membership_id: str,
) -> dict[str, Any]:
    items, blockers = _verify_operation_items(cur, operation_id=operation_id, phase="merge")
    for table, spec in MERGE_REASSIGNED_ENTITY_SPECS.items():
        table = _safe_identifier(table)
        tenant = _safe_identifier(str(spec["tenant_column"]))
        person = _safe_identifier(str(spec["person_column"]))
        membership = spec.get("membership_column")
        condition = f"{person}=%s"
        params: list[Any] = [company_code, absorbed_person_id]
        if membership:
            condition += f" OR {_safe_identifier(str(membership))}=%s"
            params.append(absorbed_membership_id)
        cur.execute(f"SELECT count(*) AS n FROM {table} WHERE {tenant}=%s AND ({condition})", tuple(params))
        remaining = int(_row(cur.fetchone()).get("n") or 0)
        if remaining:
            blockers.append({"entity_type": table, "entity_id": "*", "reason": "absorbed_identity_reference_remains", "count": remaining})
    cur.execute(
        """
        SELECT i.entity_id
        FROM person_merge_operation_items i
        JOIN file_registry f ON f.file_id::text=i.entity_id AND f.company_code=i.company_code
        WHERE i.operation_id=%s AND i.phase='merge' AND i.entity_type='file_registry'
          AND f.subject_type='application'
          AND NOT EXISTS (
            SELECT 1 FROM applications a
            WHERE a.company_code=f.company_code AND a.app_key=f.subject_key
          )
        """,
        (operation_id,),
    )
    for row in cur.fetchall() or []:
        blockers.append({"entity_type": "file_registry", "entity_id": str(_row(row).get("entity_id")), "reason": "application_document_relationship_missing"})
    if blockers:
        raise IdentityError("merge_post_invariant_failed", details={"blocking_entities": blockers})
    return {"operation_items": len(items), "blocking_entities": []}


def _record_failed_merge(cur: Any, operation_id: str, exc: Exception) -> dict[str, Any]:
    code = exc.code if isinstance(exc, IdentityError) else "merge_transaction_failed"
    details = exc.details if isinstance(exc, IdentityError) else {"exception": type(exc).__name__, "message": str(exc)}
    failure = {"error": code, "details": details, "retry_policy": "failed_terminal_new_preview_required"}
    cur.execute(
        "UPDATE person_merge_operations SET status='failed',failure_reason=%s,result=%s,updated_at=now() WHERE operation_id=%s RETURNING *",
        (code, json.dumps(failure, default=str), operation_id),
    )
    return {"operation": _row(cur.fetchone()), **failure, "idempotent": False}


def execute_merge(cur: Any, *, preview: Mapping[str, Any], actor_user_id: str, actor_type: str, permissions: Iterable[str], confirmation_token: str | None) -> dict[str, Any]:
    if actor_type == "assistant":
        raise IdentityError("assistant_merge_execute_denied")
    require_permission(permissions, MERGE_EXECUTE)
    company, request_hash = _validate_merge_request(preview)

    # Serialize this tenant/request pair before looking up durable state. Exact
    # completed replay is resolved before confirmation validation/consumption.
    cur.execute("SELECT pg_advisory_xact_lock(hashtextextended(%s,0))", (f"c3-merge:{company}:{request_hash}",))
    existing = _fetch_merge_operation(cur, company, request_hash, lock=True)
    if existing:
        status = str(existing.get("status") or "")
        if status == "completed":
            return _operation_response(existing, idempotent=True)
        if status in {"processing", "previewed"}:
            return {**_operation_response(existing, idempotent=True), "in_progress": True}
        if status == "failed":
            failure = _json_object(existing.get("result"))
            return {"operation": existing, **failure, "idempotent": True}
        if status == "reversed":
            return {"operation": existing, "error": "merge_operation_already_reversed", "idempotent": True}

    if not confirmation_token:
        raise IdentityError("confirmation_required")
    confirmation_id = consume_c3_confirmation(
        cur,
        company_code=company,
        actor_user_id=actor_user_id,
        action="merge",
        payload=preview,
        token=confirmation_token,
    )
    canonical_person_id = str(preview.get("canonical_person_id") or "")
    absorbed_person_id = str(preview.get("absorbed_person_id") or "")
    identities = _lock_merge_identities(
        cur,
        company_code=company,
        canonical_person_id=canonical_person_id,
        absorbed_person_id=absorbed_person_id,
    )
    current = _locked_preview(company, canonical_person_id, absorbed_person_id, identities)
    if current["request_hash"] != request_hash:
        raise IdentityError("stale_merge_preview")
    canonical_membership_id = str(identities[canonical_person_id]["membership_id"])
    absorbed_membership_id = str(identities[absorbed_person_id]["membership_id"])
    snapshot = {
        "canonical": canonical_person_id,
        "absorbed": absorbed_person_id,
        "canonical_membership_id": canonical_membership_id,
        "absorbed_membership_id": absorbed_membership_id,
        "preview": dict(preview),
    }
    cur.execute(
        """
        INSERT INTO person_merge_operations(
          company_code,canonical_person_id,absorbed_person_id,actor_user_id,
          confirmation_id,request_hash,preview_payload,snapshot,status,updated_at
        ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,'processing',now())
        RETURNING *
        """,
        (company, canonical_person_id, absorbed_person_id, actor_user_id, confirmation_id, request_hash, json.dumps(dict(preview), default=str), json.dumps(snapshot, default=str)),
    )
    operation = _row(cur.fetchone())
    operation_id = str(operation["operation_id"])
    cur.execute("SAVEPOINT candidates_c3_merge_apply")
    try:
        blockers = _collect_merge_blockers(
            cur,
            company_code=company,
            canonical_person_id=canonical_person_id,
            absorbed_person_id=absorbed_person_id,
            canonical_membership_id=canonical_membership_id,
            absorbed_membership_id=absorbed_membership_id,
        )
        if blockers:
            raise IdentityError("merge_blocked", details={"blocking_entities": blockers})

        locked_rows: dict[str, list[dict[str, Any]]] = {}
        for table, spec in MERGE_REASSIGNED_ENTITY_SPECS.items():
            locked_rows[table] = _lock_reassigned_rows(
                cur,
                table=table,
                spec=spec,
                company_code=company,
                absorbed_person_id=absorbed_person_id,
                absorbed_membership_id=absorbed_membership_id,
            )
        for table, rows in locked_rows.items():
            for row in rows:
                _reassign_row(
                    cur,
                    operation_id=operation_id,
                    company_code=company,
                    table=table,
                    spec=MERGE_REASSIGNED_ENTITY_SPECS[table],
                    row=row,
                    canonical_person_id=canonical_person_id,
                    canonical_membership_id=canonical_membership_id,
                )

        absorbed_membership = identities[absorbed_person_id]
        cur.execute(
            """
            WITH changed AS (
              UPDATE person_company_memberships
              SET status='inactive',updated_at=now()
              WHERE membership_id=%s AND company_code=%s AND person_id=%s
              RETURNING *
            )
            SELECT changed.*,md5(to_jsonb(changed)::text) AS fingerprint FROM changed
            """,
            (absorbed_membership_id, company, absorbed_person_id),
        )
        membership_after = _row(cur.fetchone())
        if not membership_after:
            raise IdentityError("merge_membership_update_missing")
        _insert_merge_item(
            cur,
            operation_id=operation_id,
            company_code=company,
            phase="merge",
            entity_type="person_company_memberships",
            entity_id=absorbed_membership_id,
            pre_person_id=absorbed_person_id,
            pre_membership_id=absorbed_membership_id,
            post_person_id=absorbed_person_id,
            post_membership_id=absorbed_membership_id,
            pre_fingerprint=str(absorbed_membership.get("membership_fingerprint") or ""),
            post_fingerprint=str(membership_after.get("fingerprint") or ""),
            action_taken="deactivated",
            metadata={"pre_status": absorbed_membership.get("membership_status"), "post_status": "inactive"},
        )

        absorbed_person = identities[absorbed_person_id]
        cur.execute(
            """
            WITH changed AS (
              UPDATE persons
              SET status='merged',merged_into_person_id=%s,updated_at=now()
              WHERE person_id=%s AND status='active'
              RETURNING *
            )
            SELECT changed.*,md5(to_jsonb(changed)::text) AS fingerprint FROM changed
            """,
            (canonical_person_id, absorbed_person_id),
        )
        person_after = _row(cur.fetchone())
        if not person_after:
            raise IdentityError("merge_person_update_missing")
        _insert_merge_item(
            cur,
            operation_id=operation_id,
            company_code=company,
            phase="merge",
            entity_type="persons",
            entity_id=absorbed_person_id,
            pre_person_id=absorbed_person_id,
            pre_membership_id=None,
            post_person_id=absorbed_person_id,
            post_membership_id=None,
            pre_fingerprint=str(absorbed_person.get("person_fingerprint") or ""),
            post_fingerprint=str(person_after.get("fingerprint") or ""),
            action_taken="marked_merged",
            metadata={
                "pre_status": absorbed_person.get("status"),
                "pre_merged_into_person_id": absorbed_person.get("merged_into_person_id"),
                "post_status": "merged",
                "post_merged_into_person_id": canonical_person_id,
            },
        )

        cur.execute(
            """
            SELECT *,md5(to_jsonb(s)::text) AS fingerprint
            FROM person_duplicate_suggestions s
            WHERE company_code=%s
              AND ((left_person_id=%s AND right_person_id=%s) OR (left_person_id=%s AND right_person_id=%s))
              AND status IN ('open','accepted')
            ORDER BY suggestion_id
            FOR UPDATE
            """,
            (company, canonical_person_id, absorbed_person_id, absorbed_person_id, canonical_person_id),
        )
        suggestions = [_row(row) for row in (cur.fetchall() or [])]
        for suggestion in suggestions:
            cur.execute(
                """
                WITH changed AS (
                  UPDATE person_duplicate_suggestions SET status='merged',updated_at=now()
                  WHERE suggestion_id=%s AND company_code=%s RETURNING *
                )
                SELECT changed.*,md5(to_jsonb(changed)::text) AS fingerprint FROM changed
                """,
                (suggestion["suggestion_id"], company),
            )
            suggestion_after = _row(cur.fetchone())
            _insert_merge_item(
                cur,
                operation_id=operation_id,
                company_code=company,
                phase="merge",
                entity_type="person_duplicate_suggestions",
                entity_id=str(suggestion["suggestion_id"]),
                pre_person_id=None,
                pre_membership_id=None,
                post_person_id=None,
                post_membership_id=None,
                pre_fingerprint=str(suggestion.get("fingerprint") or ""),
                post_fingerprint=str(suggestion_after.get("fingerprint") or ""),
                action_taken="marked_merged",
                metadata={"pre_status": suggestion.get("status"), "post_status": "merged"},
            )

        invariant = _verify_merge_invariants(
            cur,
            operation_id=operation_id,
            company_code=company,
            absorbed_person_id=absorbed_person_id,
            absorbed_membership_id=absorbed_membership_id,
        )
        assert_no_cv_processing_authority()
        result_payload = {
            "operation_id": operation_id,
            "status": "completed",
            "canonical_person_id": canonical_person_id,
            "absorbed_person_id": absorbed_person_id,
            **invariant,
        }
        cur.execute(
            "UPDATE person_merge_operations SET status='completed',result=%s,executed_at=now(),updated_at=now() WHERE operation_id=%s RETURNING *",
            (json.dumps(result_payload, default=str), operation_id),
        )
        completed = _row(cur.fetchone())
        cur.execute("RELEASE SAVEPOINT candidates_c3_merge_apply")
        return {"operation": completed, "result": result_payload, "idempotent": False}
    except Exception as exc:
        cur.execute("ROLLBACK TO SAVEPOINT candidates_c3_merge_apply")
        cur.execute("RELEASE SAVEPOINT candidates_c3_merge_apply")
        return _record_failed_merge(cur, operation_id, exc)


def _restore_merge_item(
    cur: Any,
    *,
    operation_id: str,
    item: Mapping[str, Any],
) -> None:
    company_code = str(item["company_code"])
    entity_type = str(item["entity_type"])
    entity_id = str(item["entity_id"])
    metadata = _json_object(item.get("metadata"))
    current = _current_item_state(cur, item, lock=True)
    if str(current.get("fingerprint") or "") != str(item.get("post_fingerprint") or ""):
        raise IdentityError("reverse_unsafe", details={"blocking_entities": [{"entity_type": entity_type, "entity_id": entity_id, "reason": "post_merge_fingerprint_changed"}]})
    if entity_type in MERGE_REASSIGNED_ENTITY_SPECS:
        spec = MERGE_REASSIGNED_ENTITY_SPECS[entity_type]
        primary_key = _safe_identifier(str(spec["primary_key"]))
        tenant = _safe_identifier(str(spec["tenant_column"]))
        person = _safe_identifier(str(spec["person_column"]))
        membership = spec.get("membership_column")
        assignments = [f"{person}=%s"]
        params: list[Any] = [item.get("pre_person_id")]
        if membership:
            membership = _safe_identifier(str(membership))
            assignments.append(f"{membership}=%s")
            params.append(item.get("pre_membership_id"))
        params.extend([entity_id, company_code])
        cur.execute(
            f"""
            WITH changed AS (
              UPDATE {entity_type} SET {','.join(assignments)}
              WHERE {primary_key}::text=%s AND {tenant}=%s RETURNING *
            )
            SELECT changed.*,md5(to_jsonb(changed)::text) AS fingerprint FROM changed
            """,
            tuple(params),
        )
    elif entity_type == "person_company_memberships":
        cur.execute(
            """
            WITH changed AS (
              UPDATE person_company_memberships SET status=%s,updated_at=now()
              WHERE membership_id=%s AND company_code=%s RETURNING *
            )
            SELECT changed.*,md5(to_jsonb(changed)::text) AS fingerprint FROM changed
            """,
            (metadata.get("pre_status"), entity_id, company_code),
        )
    elif entity_type == "persons":
        cur.execute(
            """
            WITH changed AS (
              UPDATE persons SET status=%s,merged_into_person_id=%s,updated_at=now()
              WHERE person_id=%s RETURNING *
            )
            SELECT changed.*,md5(to_jsonb(changed)::text) AS fingerprint FROM changed
            """,
            (metadata.get("pre_status"), metadata.get("pre_merged_into_person_id"), entity_id),
        )
    elif entity_type == "person_duplicate_suggestions":
        cur.execute(
            """
            WITH changed AS (
              UPDATE person_duplicate_suggestions SET status=%s,updated_at=now()
              WHERE suggestion_id=%s AND company_code=%s RETURNING *
            )
            SELECT changed.*,md5(to_jsonb(changed)::text) AS fingerprint FROM changed
            """,
            (metadata.get("pre_status"), entity_id, company_code),
        )
    else:
        raise IdentityError("merge_item_entity_unclassified", details={"entity_type": entity_type, "entity_id": entity_id})
    after = _row(cur.fetchone())
    if not after:
        raise IdentityError("reverse_entity_update_missing", details={"entity_type": entity_type, "entity_id": entity_id})
    spec = MERGE_REASSIGNED_ENTITY_SPECS.get(entity_type)
    person_column = str(spec["person_column"]) if spec else "person_id"
    membership_column = str(spec["membership_column"]) if spec and spec.get("membership_column") else "membership_id"
    _insert_merge_item(
        cur,
        operation_id=operation_id,
        company_code=company_code,
        phase="reversal",
        source_item_id=str(item["item_id"]),
        entity_type=entity_type,
        entity_id=entity_id,
        pre_person_id=item.get("post_person_id"),
        pre_membership_id=item.get("post_membership_id"),
        post_person_id=after.get(person_column) if entity_type not in {"person_duplicate_suggestions"} else None,
        post_membership_id=after.get(membership_column) if entity_type not in {"persons", "person_duplicate_suggestions"} else None,
        pre_fingerprint=str(item.get("post_fingerprint") or ""),
        post_fingerprint=str(after.get("fingerprint") or ""),
        action_taken="restored",
        metadata={"source_action": item.get("action_taken")},
    )


def _reversal_dependency_blockers(cur: Any, operation: Mapping[str, Any], merge_items: Iterable[Mapping[str, Any]]) -> list[dict[str, Any]]:
    company_code = str(operation["company_code"])
    canonical_person_id = str(operation["canonical_person_id"])
    executed_at = operation.get("executed_at")
    blockers: list[dict[str, Any]] = []
    item_keys = {(str(item.get("entity_type")), str(item.get("entity_id"))) for item in merge_items}
    if executed_at:
        cur.execute(
            "SELECT app_key FROM applications WHERE company_code=%s AND person_id=%s AND updated_at>%s FOR UPDATE",
            (company_code, canonical_person_id, executed_at),
        )
        for row in cur.fetchall() or []:
            entity_id = str(_row(row).get("app_key"))
            if ("applications", entity_id) not in item_keys:
                blockers.append({"entity_type": "applications", "entity_id": entity_id, "reason": "post_merge_dependency_created_or_modified"})
        cur.execute(
            "SELECT file_id FROM file_registry WHERE company_code=%s AND person_id=%s AND created_at>%s FOR UPDATE",
            (company_code, canonical_person_id, executed_at),
        )
        for row in cur.fetchall() or []:
            entity_id = str(_row(row).get("file_id"))
            if ("file_registry", entity_id) not in item_keys:
                blockers.append({"entity_type": "file_registry", "entity_id": entity_id, "reason": "post_merge_dependency_created"})
    return blockers


def _verify_reversal_invariants(cur: Any, *, operation_id: str, operation: Mapping[str, Any]) -> dict[str, Any]:
    reversal_items, blockers = _verify_operation_items(cur, operation_id=operation_id, phase="reversal")
    cur.execute("SELECT count(*) AS n FROM persons WHERE person_id=ANY(%s::uuid[])", ([operation["canonical_person_id"], operation["absorbed_person_id"]],))
    if int(_row(cur.fetchone()).get("n") or 0) != 2:
        blockers.append({"entity_type": "persons", "entity_id": "*", "reason": "person_row_count_changed"})
    snapshot = _json_object(operation.get("snapshot"))
    membership_ids = [snapshot.get("canonical_membership_id"), snapshot.get("absorbed_membership_id")]
    cur.execute("SELECT count(*) AS n FROM person_company_memberships WHERE membership_id=ANY(%s::uuid[])", (membership_ids,))
    if int(_row(cur.fetchone()).get("n") or 0) != 2:
        blockers.append({"entity_type": "person_company_memberships", "entity_id": "*", "reason": "membership_row_count_changed"})
    if blockers:
        raise IdentityError("reverse_post_invariant_failed", details={"blocking_entities": blockers})
    assert_no_cv_processing_authority()
    return {"reversal_items": len(reversal_items), "blocking_entities": []}


def reverse_merge(cur: Any, *, company_code: str, operation_id: str, actor_user_id: str, permissions: Iterable[str], confirmation_token: str | None) -> dict[str, Any]:
    require_permission(permissions, MERGE_REVERSE)
    company = validate_company_code(company_code)
    cur.execute(
        "SELECT * FROM person_merge_operations WHERE company_code=%s AND operation_id=%s FOR UPDATE",
        (company, operation_id),
    )
    operation = _row(cur.fetchone())
    if not operation:
        raise IdentityError("reverse_unsafe", details={"reason": "merge_operation_not_found"})
    if operation.get("status") == "reversed":
        committed = _json_object(operation.get("reversal_result"))
        return {**committed, "idempotent": True}
    if operation.get("status") != "completed":
        raise IdentityError("reverse_unsafe", details={"reason": "merge_operation_not_completed", "status": operation.get("status")})
    if not confirmation_token:
        raise IdentityError("confirmation_required")

    payload = {"operation_id": operation_id, "request_hash": operation.get("request_hash")}
    cur.execute("SAVEPOINT candidates_c3_merge_reverse")
    try:
        confirmation_id = consume_c3_confirmation(
            cur,
            company_code=company,
            actor_user_id=actor_user_id,
            action="reverse_merge",
            payload=payload,
            token=confirmation_token,
        )
        merge_items, blockers = _verify_operation_items(cur, operation_id=operation_id, phase="merge", lock=True)
        blockers.extend(_reversal_dependency_blockers(cur, operation, merge_items))
        cur.execute(
            "SELECT hold_id FROM legal_holds WHERE company_code=%s AND person_id=ANY(%s::uuid[]) AND status='active' FOR UPDATE",
            (company, [operation["canonical_person_id"], operation["absorbed_person_id"]]),
        )
        for row in cur.fetchall() or []:
            blockers.append({"entity_type": "legal_holds", "entity_id": str(_row(row).get("hold_id")), "reason": "active_legal_hold"})
        if blockers:
            raise IdentityError("reverse_unsafe", details={"blocking_entities": blockers})

        # Identity roots are restored first; application/document/contact rows
        # then return to the exact mappings captured by the immutable ledger.
        order = {"persons": 0, "person_company_memberships": 1, "person_contact_points": 2, "candidates": 3, "applications": 4, "file_registry": 5, "person_duplicate_suggestions": 6}
        for item in sorted(merge_items, key=lambda value: (order.get(str(value.get("entity_type")), 99), str(value.get("entity_id")))):
            _restore_merge_item(cur, operation_id=operation_id, item=item)
        invariant = _verify_reversal_invariants(cur, operation_id=operation_id, operation=operation)
        result = {"operation_id": operation_id, "status": "reversed", **invariant}
        cur.execute(
            """
            UPDATE person_merge_operations
            SET status='reversed',reverse_confirmation_id=%s,reversal_result=%s,
                reversal_failure='{}'::jsonb,reversed_at=now(),updated_at=now()
            WHERE operation_id=%s
            """,
            (confirmation_id, json.dumps(result, default=str), operation_id),
        )
        cur.execute("RELEASE SAVEPOINT candidates_c3_merge_reverse")
        return {**result, "idempotent": False}
    except Exception as exc:
        cur.execute("ROLLBACK TO SAVEPOINT candidates_c3_merge_reverse")
        cur.execute("RELEASE SAVEPOINT candidates_c3_merge_reverse")
        if isinstance(exc, IdentityError) and exc.code == "confirmation_invalid_or_expired":
            raise
        code = exc.code if isinstance(exc, IdentityError) else "reverse_transaction_failed"
        details = exc.details if isinstance(exc, IdentityError) else {"exception": type(exc).__name__, "message": str(exc)}
        failure = {"error": code, "details": details}
        cur.execute(
            "UPDATE person_merge_operations SET reversal_failure=%s,updated_at=now() WHERE operation_id=%s",
            (json.dumps(failure, default=str), operation_id),
        )
        return {"operation_id": operation_id, **failure, "idempotent": False}


def record_consent(cur: Any, *, company_code: str, person_id: str, purpose: str, policy_version: str | None = None, locale: str | None = None, acquisition_surface: str | None = None, evidence_ref: str | None = None, metadata: Mapping[str, Any] | None = None) -> dict[str, Any]:
    assert_tenant_membership_scoped_read(cur, company_code, person_id); cur.execute("INSERT INTO person_consent_records(company_code,person_id,purpose,policy_version,locale,acquisition_surface,status,evidence_ref,metadata) VALUES (%s,%s,%s,%s,%s,%s,'granted',%s,%s) RETURNING *", (validate_company_code(company_code), person_id, purpose, policy_version, locale, acquisition_surface, evidence_ref, json.dumps(dict(metadata or {})))); return _row(cur.fetchone())


def withdraw_consent(cur: Any, *, company_code: str, consent_id: str) -> None:
    cur.execute("UPDATE person_consent_records SET status='withdrawn',withdrawn_at=now() WHERE company_code=%s AND consent_id=%s AND status='granted'", (validate_company_code(company_code), consent_id))


def upsert_retention_policy(cur: Any, *, company_code: str, entity_class: str, retain_days: int | None, action: str, metadata: Mapping[str, Any] | None = None) -> None:
    if action not in {"review", "anonymize", "delete"} or retain_days is not None and retain_days < 0: raise IdentityError("retention_policy_invalid")
    cur.execute("INSERT INTO tenant_retention_policies(company_code,entity_class,retain_days,action,metadata) VALUES (%s,%s,%s,%s,%s) ON CONFLICT(company_code,entity_class) DO UPDATE SET retain_days=excluded.retain_days,action=excluded.action,metadata=excluded.metadata", (validate_company_code(company_code), entity_class, retain_days, action, json.dumps(dict(metadata or {}))))


def calculate_retention_due(application_row: Mapping[str, Any], policies: Mapping[str, Any], consents: Iterable[Mapping[str, Any]], tz: Any = timezone.utc) -> dict[str, Any]:
    state = str(application_row.get("status") or application_row.get("entity_class") or "unfinished").lower()
    entity_class = "hired" if state == "hired" else ("talent_pool" if application_row.get("talent_pool") else state if state in RETENTION_DEFAULTS else "unfinished")
    policy = policies.get(entity_class) or RETENTION_DEFAULTS[entity_class]
    days, action = (policy.get("retain_days"), policy.get("action")) if isinstance(policy, Mapping) else policy
    if entity_class == "talent_pool" and any(c.get("status") == "granted" for c in consents): return {"entity_class": entity_class, "due_at": None, "action": "review", "reason": "consent_active"}
    base = application_row.get("updated_at") or application_row.get("created_at") or datetime.now(timezone.utc)
    if isinstance(base, str): base = datetime.fromisoformat(base.replace("Z", "+00:00"))
    return {"entity_class": entity_class, "due_at": None if days is None else base.astimezone(tz) + timedelta(days=int(days)), "action": action}


def _hold_authorized(permissions: Iterable[str], role: str | None, allow_owner_emergency: bool) -> None:
    if PRIVACY_HOLD not in set(permissions or ()) and not (allow_owner_emergency and role == "owner"): raise IdentityError("permission_denied")


def place_legal_hold(cur: Any, *, company_code: str, person_id: str, scope: str, reason: str, actor_user_id: str, permissions: Iterable[str], role: str | None = None, allow_owner_emergency: bool = True, case_reference: str | None = None, confirmation_id: str | None = None) -> dict[str, Any]:
    _hold_authorized(permissions, role, allow_owner_emergency); assert_tenant_membership_scoped_read(cur, company_code, person_id)
    cur.execute("INSERT INTO legal_holds(company_code,person_id,scope,reason,case_reference,placed_by_user_id,confirmation_id) VALUES (%s,%s,%s,%s,%s,%s,%s) RETURNING *", (validate_company_code(company_code), person_id, scope, reason, case_reference, actor_user_id, confirmation_id)); return _row(cur.fetchone())


def release_legal_hold(cur: Any, *, company_code: str, hold_id: str, actor_user_id: str, permissions: Iterable[str], role: str | None = None, allow_owner_emergency: bool = True) -> None:
    _hold_authorized(permissions, role, allow_owner_emergency); cur.execute("UPDATE legal_holds SET status='released',released_at=now(),released_by_user_id=%s WHERE company_code=%s AND hold_id=%s AND status='active'", (actor_user_id, validate_company_code(company_code), hold_id))


def create_privacy_request(cur: Any, *, company_code: str, person_id: str, request_type: str, actor_user_id: str, permissions: Iterable[str]) -> dict[str, Any]:
    require_permission(permissions, PRIVACY_MANAGE); assert_tenant_membership_scoped_read(cur, company_code, person_id)
    if request_type not in {"export", "delete", "anonymize"}: raise IdentityError("privacy_request_invalid")
    cur.execute("SELECT 1 FROM legal_holds WHERE company_code=%s AND person_id=%s AND status='active'", (validate_company_code(company_code), person_id))
    status = "blocked_hold" if request_type in {"delete", "anonymize"} and cur.fetchone() else "submitted"
    cur.execute("INSERT INTO privacy_requests(company_code,person_id,request_type,status,actor_user_id) VALUES (%s,%s,%s,%s,%s) RETURNING *", (validate_company_code(company_code), person_id, request_type, status, actor_user_id)); return _row(cur.fetchone())


def advance_privacy_request(cur: Any, *, company_code: str, request_id: str, status: str, actor_user_id: str, permissions: Iterable[str]) -> dict[str, Any]:
    require_permission(permissions, PRIVACY_MANAGE)
    cur.execute("SELECT * FROM privacy_requests WHERE company_code=%s AND request_id=%s FOR UPDATE", (validate_company_code(company_code), request_id)); request = _row(cur.fetchone())
    if not request: raise IdentityError("privacy_request_not_found")
    if request["request_type"] in {"delete", "anonymize"}:
        cur.execute("SELECT 1 FROM legal_holds WHERE company_code=%s AND person_id=%s AND status='active'", (validate_company_code(company_code), request["person_id"]))
        if cur.fetchone(): status = "blocked_hold"
    cur.execute("UPDATE privacy_requests SET status=%s,updated_at=now() WHERE request_id=%s RETURNING *", (status, request_id)); result = _row(cur.fetchone())
    cur.execute("INSERT INTO privacy_request_events(request_id,company_code,event_type,actor_user_id,payload) VALUES (%s,%s,%s,%s,%s)", (request_id, validate_company_code(company_code), status, actor_user_id, "{}")); return result


def export_person_package(cur: Any, *, company_code: str, person_id: str, permissions: Iterable[str]) -> dict[str, Any]:
    try:
        import tenant_control_queue_gate as _tc_qg

        queued_epoch = _tc_qg.persist_work_epoch(
            cur,
            company_code=str(company_code or "").upper(),
            work_kind="privacy_export",
            work_ref=str(person_id),
            module_key="pre_hiring",
        )
        allowed, decision = _tc_qg.gate_or_skip(
            cur,
            company_code=str(company_code or "").upper(),
            module_key="pre_hiring",
            work_kind="privacy_export",
            work_ref=str(person_id),
            queued_epoch=queued_epoch,
            surface="workers",
        )
        if not allowed:
            raise IdentityError(
                "tenant_control_held",
                details={"reason": decision.reason_code, "correlation_id": decision.audit_correlation_id},
            )
    except IdentityError:
        raise
    except Exception:
        pass
    require_permission(permissions, PRIVACY_EXPORT); person = assert_tenant_membership_scoped_read(cur, company_code, person_id)
    contacts = list_membership_contacts(cur, company_code, person_id, permissions)
    cur.execute("SELECT purpose,status,granted_at,withdrawn_at,evidence_ref FROM person_consent_records WHERE company_code=%s AND person_id=%s", (validate_company_code(company_code), person_id))
    return {"person": person, "contacts": contacts, "consents": [_row(r) for r in cur.fetchall()]}


def enqueue_document_privacy_job(
    cur: Any,
    *,
    company_code: str,
    file_id: str,
    person_id: str,
    action: str,
    document_kind: str | None = None,
    document_channel: str | None = None,
    lifecycle_stage: str | None = None,
) -> dict[str, Any]:
    """Enqueue privacy work for a file without claiming document-collection ownership.

    Recruiting CVs stay on the canonical CV pipeline. Onboarding/employee channels may be
    reconciled later; Candidates never becomes the post-hire collection workflow owner.
    """
    channel = document_channel or classify_document_channel(document_kind, lifecycle_stage=lifecycle_stage)
    if channel not in {DOCUMENT_CHANNEL_RECRUITING, DOCUMENT_CHANNEL_ONBOARDING, DOCUMENT_CHANNEL_EMPLOYEE}:
        raise IdentityError("document_channel_invalid", details={"document_channel": channel})
    cur.execute(
        "INSERT INTO document_privacy_jobs(company_code,file_id,person_id,action,document_channel) VALUES (%s,%s,%s,%s,%s) RETURNING *",
        (validate_company_code(company_code), file_id, person_id, action, channel),
    )
    row = _row(cur.fetchone())
    try:
        import tenant_control_queue_gate as _tc_qg

        _tc_qg.persist_work_epoch(
            cur,
            company_code=str(company_code or "").upper(),
            work_kind="document_privacy_job",
            work_ref=str(row.get("job_id") or file_id),
            module_key="pre_hiring",
        )
    except Exception:
        pass
    return row


def reconcile_document_privacy_job(cur: Any, *, job_id: str, object_store_action: Callable[[Mapping[str, Any]], Any]) -> dict[str, Any]:
    cur.execute("SELECT * FROM document_privacy_jobs WHERE job_id=%s FOR UPDATE", (job_id,)); job = _row(cur.fetchone())
    if not job: raise IdentityError("document_job_not_found")
    try: result = object_store_action(job)
    except Exception as exc:
        cur.execute("UPDATE document_privacy_jobs SET status='retryable',attempts=attempts+1,last_error=%s,updated_at=now() WHERE job_id=%s", (str(exc)[:500], job_id)); return {"job_id": job_id, "status": "retryable"}
    cur.execute("UPDATE document_privacy_jobs SET status='completed',attempts=attempts+1,storage_result=%s,updated_at=now() WHERE job_id=%s", (json.dumps(result or {}), job_id)); return {"job_id": job_id, "status": "completed"}


def detect_orphan_files(cur: Any, company_code: str) -> list[dict[str, Any]]:
    cur.execute("SELECT f.* FROM file_registry f LEFT JOIN person_company_memberships m ON m.membership_id=f.membership_id AND m.company_code=%s WHERE f.company_code=%s AND f.person_id IS NOT NULL AND m.membership_id IS NULL", (validate_company_code(company_code), validate_company_code(company_code))); return [_row(r) for r in cur.fetchall()]


def collision_report(legacy: Any) -> dict[str, Any]:
    """Read-only pre-migration collision inventory. Never merges."""
    with legacy.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT phone AS raw, active_company_code AS company_code, count(*) AS count
                FROM candidates
                WHERE phone IS NOT NULL AND btrim(phone) <> ''
                GROUP BY phone, active_company_code
                HAVING count(*) > 1
                """
            )
            dup_phones = [_row(r) for r in cur.fetchall()]
            cur.execute(
                """
                SELECT lower(btrim(email)) AS raw, active_company_code AS company_code, count(*) AS count
                FROM candidates
                WHERE email IS NOT NULL AND btrim(email) <> ''
                GROUP BY lower(btrim(email)), active_company_code
                HAVING count(*) > 1
                """
            )
            dup_emails = [_row(r) for r in cur.fetchall()]
            cur.execute(
                """
                SELECT phone AS raw, count(DISTINCT active_company_code) AS companies
                FROM candidates
                WHERE phone IS NOT NULL AND btrim(phone) <> ''
                GROUP BY phone
                HAVING count(DISTINCT active_company_code) > 1
                """
            )
            cross_phone = [_row(r) for r in cur.fetchall()]
            cur.execute(
                """
                SELECT lower(btrim(email)) AS raw, count(DISTINCT active_company_code) AS companies
                FROM candidates
                WHERE email IS NOT NULL AND btrim(email) <> ''
                GROUP BY lower(btrim(email))
                HAVING count(DISTINCT active_company_code) > 1
                """
            )
            cross_email = [_row(r) for r in cur.fetchall()]
            cur.execute("SELECT phone, email, active_company_code FROM candidates")
            malformed: list[dict[str, Any]] = []
            for row in cur.fetchall():
                item = _row(row)
                phone_ok = email_ok = True
                try:
                    if item.get("phone"):
                        normalize_phone(str(item.get("phone")))
                    else:
                        phone_ok = False
                except IdentityError:
                    phone_ok = False
                try:
                    if item.get("email"):
                        normalize_email(str(item.get("email")))
                except IdentityError:
                    email_ok = False
                if not phone_ok or (item.get("email") and not email_ok):
                    malformed.append({"phone": item.get("phone"), "email": item.get("email"), "company_code": item.get("active_company_code")})
            cur.execute(
                """
                SELECT c.phone, c.active_company_code AS company_code, count(a.app_key) AS app_count
                FROM candidates c
                LEFT JOIN applications a
                  ON a.phone=c.phone AND a.company_code=c.active_company_code
                GROUP BY c.phone, c.active_company_code
                HAVING count(a.app_key) > 1
                """
            )
            ambiguous = [_row(r) for r in cur.fetchall()]
    return {
        "read_only": True,
        "auto_merged": 0,
        "counts": {
            "duplicate_phones": len(dup_phones),
            "duplicate_emails": len(dup_emails),
            "malformed": len(malformed),
            "cross_company_shared": len(cross_phone) + len(cross_email),
            "ambiguous_app_links": len(ambiguous),
        },
        "samples": {
            "duplicate_phones": dup_phones[:20],
            "duplicate_emails": dup_emails[:20],
            "malformed": malformed[:20],
            "cross_company_shared_phones": cross_phone[:20],
            "cross_company_shared_emails": cross_email[:20],
            "ambiguous_app_links": ambiguous[:20],
        },
    }


def migrate_candidates_additive(legacy: Any, *, company_code: str | None = None, dry_run: bool = False) -> dict[str, Any]:
    """Create one person+membership per candidate row. Never auto-merge duplicates."""
    scope = validate_company_code(company_code) if company_code else None
    report: dict[str, Any] = {"created": 0, "linked": 0, "skipped": [], "ambiguous": [], "auto_merged": 0, "dry_run": dry_run}
    with legacy.db_connect() as conn:
        with conn.cursor() as cur:
            ensure_schema(cur)
            if scope:
                cur.execute("SELECT * FROM candidates WHERE active_company_code=%s", (scope,))
            else:
                cur.execute("SELECT * FROM candidates")
            for candidate in cur.fetchall():
                row = _row(candidate)
                tenant_raw = row.get("active_company_code") or scope
                if not tenant_raw:
                    report["skipped"].append({"phone": row.get("phone"), "reason": "missing_tenant"})
                    continue
                tenant = validate_company_code(str(tenant_raw))
                if row.get("person_id"):
                    report["skipped"].append({"phone": row.get("phone"), "reason": "already_migrated"})
                    continue
                try:
                    phone = normalize_phone(str(row.get("phone") or ""))
                except IdentityError:
                    report["skipped"].append({"phone": row.get("phone"), "reason": "phone_invalid"})
                    continue
                if dry_run:
                    report["created"] += 1
                    continue
                person_id = str(uuid.uuid4())
                membership_id = str(uuid.uuid4())
                cur.execute("INSERT INTO persons(person_id,display_name,preferred_locale) VALUES (%s,%s,%s)", (person_id, row.get("name"), "ar"))
                cur.execute(
                    "INSERT INTO person_company_memberships(membership_id,person_id,company_code,source) VALUES (%s,%s,%s,'candidate_migration')",
                    (membership_id, person_id, tenant),
                )
                cur.execute(
                    """
                    INSERT INTO person_contact_points(person_id,company_code,contact_type,raw_value,normalized_value,is_preferred)
                    VALUES (%s,%s,'phone',%s,%s,true)
                    ON CONFLICT DO NOTHING
                    """,
                    (person_id, tenant, row.get("phone"), phone),
                )
                if row.get("email"):
                    try:
                        email = normalize_email(str(row.get("email")))
                        cur.execute(
                            """
                            INSERT INTO person_contact_points(person_id,company_code,contact_type,raw_value,normalized_value)
                            VALUES (%s,%s,'email',%s,%s)
                            ON CONFLICT DO NOTHING
                            """,
                            (person_id, tenant, row.get("email"), email),
                        )
                    except IdentityError:
                        report["skipped"].append({"phone": row.get("phone"), "reason": "email_invalid"})
                cur.execute("UPDATE candidates SET person_id=%s WHERE phone=%s", (person_id, row.get("phone")))
                ensure_default_retention_policies(cur, tenant)
                report["created"] += 1
                cur.execute("SELECT app_key FROM applications WHERE company_code=%s AND phone=%s", (tenant, row.get("phone")))
                apps = [_row(a) for a in cur.fetchall()]
                if len(apps) == 1:
                    cur.execute(
                        "UPDATE applications SET person_id=%s, membership_id=%s WHERE company_code=%s AND app_key=%s",
                        (person_id, membership_id, tenant, apps[0].get("app_key")),
                    )
                    report["linked"] += 1
                elif len(apps) > 1:
                    report["ambiguous"].append({"phone": row.get("phone"), "company_code": tenant, "app_count": len(apps), "reason": "ambiguous_app_links"})
            if not dry_run:
                conn.commit()
    return report


def strip_identity_fields_from_candidate_payload(payload: Any) -> Any:
    # Strip identity + sensitive onboarding fields from candidate WhatsApp / public recruiting payloads.
    blocked = {
        "person_id",
        "membership_id",
        "person_merge_operations",
        "merge_operations",
        "duplicate_suggestions",
        "privacy_requests",
        "legal_holds",
        "consent_records",
        "civil_id",
        "encrypted_value",
        "bank_details",
        "iban",
        "passport",
        "residency",
        "work_permit",
        "emergency_contact",
    }
    if isinstance(payload, list): return [strip_identity_fields_from_candidate_payload(v) for v in payload]
    if isinstance(payload, Mapping): return {k: strip_identity_fields_from_candidate_payload(v) for k, v in payload.items() if k not in blocked and not k.startswith("identity_")}
    return payload


def assert_recruiting_channel_excludes_sensitive_onboarding(request_text: str | None) -> None:
    """Fail closed if candidate recruiting copy asks for post-hire document kinds."""
    text = str(request_text or "").strip().lower()
    if not text:
        return
    forbidden_patterns = (
        r"\bcivil\s*id\b",
        r"\bnational\s*id\b",
        r"\bpassport\b",
        r"\biban\b",
        r"\bbank\s*(details|account|iban)\b",
        r"\bresidency\b",
        r"\bwork[\s-]*permit\b",
        r"\bemergency\s*contact\b",
    )
    for pattern in forbidden_patterns:
        if re.search(pattern, text):
            raise IdentityError("recruiting_channel_sensitive_document_request", details={"pattern": pattern})


__all__ = [name for name in globals() if name.isupper() or name in {"IdentityError", "ensure_schema", "ensure_default_retention_policies", "normalize_phone", "normalize_email", "collision_report", "migrate_candidates_additive", "get_person_tenant_view", "list_membership_contacts", "add_contact_point", "create_duplicate_suggestion", "list_duplicate_suggestions", "dismiss_duplicate_suggestion", "build_match_evidence", "preview_merge", "execute_merge", "reverse_merge", "mint_c3_confirmation", "consume_c3_confirmation", "record_consent", "withdraw_consent", "upsert_retention_policy", "calculate_retention_due", "place_legal_hold", "release_legal_hold", "create_privacy_request", "advance_privacy_request", "export_person_package", "enqueue_document_privacy_job", "reconcile_document_privacy_job", "detect_orphan_files", "strip_identity_fields_from_candidate_payload", "assert_tenant_membership_scoped_read", "assert_no_cv_processing_authority", "assert_recruiting_channel_excludes_sensitive_onboarding", "assert_hire_handoff_preserves_document_boundary", "classify_document_channel", "validate_civil_id_purpose", "sanitize_match_evidence_for_viewer", "encrypt_civil_id", "decrypt_civil_id", "stable_payload_hash", "require_permission", "validate_company_code"}]
