"""Durable malware-scan and candidate-identity authority for inbound CV email.

The sender address is stored as provenance only.  Candidate binding is decided
from tenant-scoped identity evidence extracted from a durably clean attachment.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from difflib import SequenceMatcher
from typing import Any, Literal

from psycopg2.extras import Json


UTC = timezone.utc
SCAN_POLICY_VERSION = "inbound-cv-scan-v1"
IDENTITY_POLICY_VERSION = "inbound-cv-identity-v1"
SCAN_STATES = frozenset(
    {"pending_scan", "clean", "infected", "scan_failed", "quarantined"}
)
IDENTITY_OUTCOMES = frozenset(
    {"safe_exact_reuse", "new_candidate", "possible_match", "conflict"}
)
ACCEPTED_IDENTITY_OUTCOMES = frozenset({"safe_exact_reuse", "new_candidate"})
HELD_APPLICATION_STATUSES = frozenset(
    {"needs_role", "import_review", "import_archived", "review_pending"}
)


SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS inbound_attachment_scan_decisions (
  decision_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  company_code text NOT NULL,
  inbound_id uuid NOT NULL REFERENCES inbound_messages(inbound_id) ON DELETE CASCADE,
  intake_document_id uuid NOT NULL REFERENCES intake_documents(document_id) ON DELETE CASCADE,
  attachment_ordinal integer NOT NULL,
  content_sha256 text NOT NULL,
  scanner_policy_version text NOT NULL,
  attempt_no integer NOT NULL,
  state text NOT NULL CHECK (
    state IN ('pending_scan','clean','infected','scan_failed','quarantined')
  ),
  scanner_engine text,
  scanner_version text,
  signature_database_version text,
  scan_started_at timestamptz NOT NULL,
  scan_completed_at timestamptz,
  result text,
  failure_reason text,
  quarantine_object_ref text,
  actor_service_identity text NOT NULL,
  reused_from_decision_id uuid REFERENCES inbound_attachment_scan_decisions(decision_id),
  evidence jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (company_code, intake_document_id, attempt_no)
);
CREATE INDEX IF NOT EXISTS idx_inbound_scan_authority_lookup
  ON inbound_attachment_scan_decisions
    (company_code, intake_document_id, scan_completed_at DESC, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_inbound_scan_authority_reuse
  ON inbound_attachment_scan_decisions
    (company_code, content_sha256, scanner_policy_version, scan_completed_at DESC)
  WHERE state='clean';

CREATE TABLE IF NOT EXISTS inbound_cv_identity_extractions (
  extraction_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  company_code text NOT NULL,
  inbound_id uuid NOT NULL REFERENCES inbound_messages(inbound_id) ON DELETE CASCADE,
  intake_document_id uuid NOT NULL REFERENCES intake_documents(document_id) ON DELETE CASCADE,
  content_sha256 text NOT NULL,
  extraction_status text NOT NULL,
  extraction_method text,
  extracted_text_sha256 text,
  extracted_identity jsonb NOT NULL DEFAULT '{}'::jsonb,
  document_identity_evidence jsonb NOT NULL DEFAULT '{}'::jsonb,
  error_code text,
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (company_code, intake_document_id)
);

CREATE TABLE IF NOT EXISTS inbound_cv_identity_resolutions (
  resolution_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  company_code text NOT NULL,
  inbound_id uuid NOT NULL REFERENCES inbound_messages(inbound_id) ON DELETE CASCADE,
  intake_document_id uuid NOT NULL REFERENCES intake_documents(document_id) ON DELETE CASCADE,
  content_sha256 text NOT NULL,
  identity_policy_version text NOT NULL,
  sender_email_provenance text,
  extracted_email text,
  extracted_phone text,
  normalized_full_name text,
  outcome text NOT NULL CHECK (
    outcome IN ('safe_exact_reuse','new_candidate','possible_match','conflict')
  ),
  confidence numeric(6,5) NOT NULL,
  selected_candidate_phone text,
  selected_app_key text,
  candidate_matches jsonb NOT NULL DEFAULT '[]'::jsonb,
  strong_keys jsonb NOT NULL DEFAULT '[]'::jsonb,
  weak_keys jsonb NOT NULL DEFAULT '[]'::jsonb,
  reason_codes jsonb NOT NULL DEFAULT '[]'::jsonb,
  ownership_confirmed boolean NOT NULL DEFAULT false,
  actor_service_identity text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (company_code, intake_document_id, identity_policy_version)
);
CREATE INDEX IF NOT EXISTS idx_inbound_identity_resolution_lookup
  ON inbound_cv_identity_resolutions
    (company_code, intake_document_id, created_at DESC);

CREATE TABLE IF NOT EXISTS inbound_cv_identity_reviews (
  review_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  company_code text NOT NULL,
  resolution_id uuid NOT NULL UNIQUE
    REFERENCES inbound_cv_identity_resolutions(resolution_id) ON DELETE CASCADE,
  intake_document_id uuid NOT NULL REFERENCES intake_documents(document_id) ON DELETE CASCADE,
  status text NOT NULL DEFAULT 'open',
  review_type text NOT NULL,
  possible_candidate_phones jsonb NOT NULL DEFAULT '[]'::jsonb,
  possible_app_keys jsonb NOT NULL DEFAULT '[]'::jsonb,
  reason_codes jsonb NOT NULL DEFAULT '[]'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now(),
  resolved_at timestamptz,
  resolved_by text,
  resolution_note text
);

CREATE TABLE IF NOT EXISTS inbound_cv_identity_events (
  event_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  company_code text NOT NULL,
  resolution_id uuid REFERENCES inbound_cv_identity_resolutions(resolution_id),
  intake_document_id uuid NOT NULL REFERENCES intake_documents(document_id) ON DELETE CASCADE,
  event_type text NOT NULL,
  actor_service_identity text NOT NULL,
  payload jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS candidate_identity_keys (
  identity_key_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  company_code text NOT NULL,
  candidate_phone text NOT NULL,
  key_type text NOT NULL,
  normalized_value text NOT NULL,
  authority text NOT NULL,
  source_ref text,
  active boolean NOT NULL DEFAULT true,
  confirmed_at timestamptz,
  confirmed_by text,
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (company_code, candidate_phone, key_type, normalized_value, authority)
);
CREATE INDEX IF NOT EXISTS idx_candidate_identity_key_lookup
  ON candidate_identity_keys (company_code, key_type, normalized_value)
  WHERE active;

CREATE TABLE IF NOT EXISTS candidate_classification_run_invalidations (
  invalidation_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  company_code text NOT NULL,
  run_id uuid NOT NULL,
  reason_code text NOT NULL,
  source_resolution_id uuid REFERENCES inbound_cv_identity_resolutions(resolution_id),
  source_document_id text,
  invalidated_by text NOT NULL,
  evidence jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (company_code, run_id, reason_code)
);

CREATE OR REPLACE FUNCTION prevent_inbound_authority_rewrite()
RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF current_setting('wathefni.authority_cleanup', true) = 'synthetic' THEN
    RETURN OLD;
  END IF;
  RAISE EXCEPTION 'inbound authority records are append-only';
END;
$$;
DROP TRIGGER IF EXISTS trg_scan_authority_append_only
  ON inbound_attachment_scan_decisions;
CREATE TRIGGER trg_scan_authority_append_only
BEFORE UPDATE OR DELETE ON inbound_attachment_scan_decisions
FOR EACH ROW EXECUTE FUNCTION prevent_inbound_authority_rewrite();
DROP TRIGGER IF EXISTS trg_identity_resolution_append_only
  ON inbound_cv_identity_resolutions;
CREATE TRIGGER trg_identity_resolution_append_only
BEFORE UPDATE OR DELETE ON inbound_cv_identity_resolutions
FOR EACH ROW EXECUTE FUNCTION prevent_inbound_authority_rewrite();
DROP TRIGGER IF EXISTS trg_identity_event_append_only
  ON inbound_cv_identity_events;
CREATE TRIGGER trg_identity_event_append_only
BEFORE UPDATE OR DELETE ON inbound_cv_identity_events
FOR EACH ROW EXECUTE FUNCTION prevent_inbound_authority_rewrite();
DROP TRIGGER IF EXISTS trg_classification_invalidation_append_only
  ON candidate_classification_run_invalidations;
CREATE TRIGGER trg_classification_invalidation_append_only
BEFORE UPDATE OR DELETE ON candidate_classification_run_invalidations
FOR EACH ROW EXECUTE FUNCTION prevent_inbound_authority_rewrite();
"""


def ensure_schema(cur: Any) -> None:
    cur.execute(SCHEMA_SQL)


def _actor() -> str:
    return (
        str(os.environ.get("WATHEFNI_INTAKE_SERVICE_IDENTITY") or "").strip()
        or "wathefni-durable-email-ingress"
    )


def _row(value: Any) -> dict[str, Any]:
    return dict(value or {})


def normalize_email(value: Any) -> str | None:
    text = str(value or "").strip().lower()
    if not text or "@" not in text:
        return None
    return text


def normalize_phone(value: Any) -> str | None:
    raw = str(value or "").strip()
    if not raw:
        return None
    plus = raw.startswith("+")
    digits = re.sub(r"\D", "", raw)
    if len(digits) < 7:
        return None
    return f"+{digits}" if plus else digits


def normalize_name(value: Any) -> str | None:
    text = re.sub(r"[^\w\u0600-\u06ff]+", " ", str(value or "").casefold())
    text = " ".join(text.split())
    return text or None


def _signature_versions(signature: str | None) -> tuple[str | None, str | None]:
    text = str(signature or "").strip()
    if not text:
        return None, None
    parts = text.split("/", 1)
    return parts[0].strip() or None, text


def latest_scan_decision(
    cur: Any, *, company_code: str, intake_document_id: str
) -> dict[str, Any] | None:
    cur.execute(
        """
        SELECT *, decision_id::text AS decision_id,
               intake_document_id::text AS intake_document_id,
               inbound_id::text AS inbound_id,
               reused_from_decision_id::text AS reused_from_decision_id
        FROM inbound_attachment_scan_decisions
        WHERE company_code=%s AND intake_document_id=%s
        ORDER BY attempt_no DESC LIMIT 1
        """,
        (company_code, intake_document_id),
    )
    row = cur.fetchone()
    return _row(row) if row else None


def begin_scan(
    cur: Any,
    *,
    company_code: str,
    inbound_id: str,
    intake_document_id: str,
    attachment_ordinal: int,
    content_sha256: str,
    quarantine_object_ref: str | None,
    policy_version: str = SCAN_POLICY_VERSION,
) -> dict[str, Any]:
    cur.execute(
        """
        SELECT COALESCE(max(attempt_no),0)+1 AS attempt_no
        FROM inbound_attachment_scan_decisions
        WHERE company_code=%s AND intake_document_id=%s
        """,
        (company_code, intake_document_id),
    )
    attempt = int(_row(cur.fetchone()).get("attempt_no") or 1)
    cur.execute(
        """
        INSERT INTO inbound_attachment_scan_decisions
          (company_code, inbound_id, intake_document_id, attachment_ordinal,
           content_sha256, scanner_policy_version, attempt_no, state,
           scan_started_at, quarantine_object_ref, actor_service_identity)
        VALUES (%s,%s,%s,%s,%s,%s,%s,'pending_scan',now(),%s,%s)
        RETURNING *, decision_id::text AS decision_id
        """,
        (
            company_code,
            inbound_id,
            intake_document_id,
            attachment_ordinal,
            content_sha256,
            policy_version,
            attempt,
            quarantine_object_ref,
            _actor(),
        ),
    )
    return _row(cur.fetchone())


def reusable_clean_scan(
    cur: Any,
    *,
    company_code: str,
    content_sha256: str,
    policy_version: str = SCAN_POLICY_VERSION,
    retention_hours: int | None = None,
) -> dict[str, Any] | None:
    hours = retention_hours
    if hours is None:
        try:
            hours = max(
                0,
                int(os.environ.get("WATHEFNI_INTAKE_SCAN_REUSE_HOURS") or "168"),
            )
        except ValueError:
            hours = 168
    cutoff = datetime.now(UTC) - timedelta(hours=hours)
    cur.execute(
        """
        SELECT *, decision_id::text AS decision_id
        FROM inbound_attachment_scan_decisions
        WHERE company_code=%s AND content_sha256=%s
          AND scanner_policy_version=%s
          AND state='clean' AND scan_completed_at >= %s
        ORDER BY scan_completed_at DESC LIMIT 1
        """,
        (company_code, content_sha256, policy_version, cutoff),
    )
    row = cur.fetchone()
    return _row(row) if row else None


def complete_scan(
    cur: Any,
    *,
    pending_decision: dict[str, Any],
    state: str,
    scanner_engine: str | None,
    signature_version: str | None,
    failure_reason: str | None,
    evidence: dict[str, Any] | None = None,
    reused_from_decision_id: str | None = None,
) -> dict[str, Any]:
    if state not in SCAN_STATES or state == "pending_scan":
        raise ValueError("invalid_terminal_scan_state")
    scanner_version, database_version = _signature_versions(signature_version)
    # Append the terminal decision; the pending row itself remains immutable.
    attempt = int(pending_decision["attempt_no"])
    terminal_attempt = attempt + 1
    cur.execute(
        """
        INSERT INTO inbound_attachment_scan_decisions
          (company_code, inbound_id, intake_document_id, attachment_ordinal,
           content_sha256, scanner_policy_version, attempt_no, state,
           scanner_engine, scanner_version, signature_database_version,
           scan_started_at, scan_completed_at, result, failure_reason,
           quarantine_object_ref, actor_service_identity,
           reused_from_decision_id, evidence)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,now(),%s,%s,%s,%s,%s,%s)
        RETURNING *, decision_id::text AS decision_id
        """,
        (
            pending_decision["company_code"],
            pending_decision["inbound_id"],
            pending_decision["intake_document_id"],
            pending_decision["attachment_ordinal"],
            pending_decision["content_sha256"],
            pending_decision["scanner_policy_version"],
            terminal_attempt,
            state,
            scanner_engine,
            scanner_version,
            database_version,
            pending_decision["scan_started_at"],
            state,
            failure_reason,
            pending_decision.get("quarantine_object_ref"),
            _actor(),
            reused_from_decision_id,
            Json(evidence or {}),
        ),
    )
    return _row(cur.fetchone())


def scan_is_authoritatively_clean(
    cur: Any, *, company_code: str, intake_document_id: str, content_sha256: str
) -> bool:
    latest = latest_scan_decision(
        cur, company_code=company_code, intake_document_id=intake_document_id
    )
    return bool(
        latest
        and latest.get("state") == "clean"
        and latest.get("scan_completed_at")
        and latest.get("content_sha256") == content_sha256
        and latest.get("scanner_policy_version") == SCAN_POLICY_VERSION
    )


def record_identity_extraction(
    cur: Any,
    *,
    company_code: str,
    inbound_id: str,
    intake_document_id: str,
    content_sha256: str,
    extraction_status: str,
    extraction_method: str | None,
    extracted_text: str | None,
    extracted_identity: dict[str, Any],
    document_identity_evidence: dict[str, Any],
    error_code: str | None = None,
) -> dict[str, Any]:
    text_hash = (
        hashlib.sha256(str(extracted_text).encode("utf-8")).hexdigest()
        if extracted_text
        else None
    )
    cur.execute(
        """
        INSERT INTO inbound_cv_identity_extractions
          (company_code, inbound_id, intake_document_id, content_sha256,
           extraction_status, extraction_method, extracted_text_sha256,
           extracted_identity, document_identity_evidence, error_code)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
        ON CONFLICT (company_code, intake_document_id) DO NOTHING
        RETURNING *, extraction_id::text AS extraction_id
        """,
        (
            company_code,
            inbound_id,
            intake_document_id,
            content_sha256,
            extraction_status,
            extraction_method,
            text_hash,
            Json(extracted_identity),
            Json(document_identity_evidence),
            error_code,
        ),
    )
    row = cur.fetchone()
    if row:
        return _row(row)
    cur.execute(
        """
        SELECT *, extraction_id::text AS extraction_id
        FROM inbound_cv_identity_extractions
        WHERE company_code=%s AND intake_document_id=%s
        """,
        (company_code, intake_document_id),
    )
    return _row(cur.fetchone())


def _nested(mapping: dict[str, Any], *paths: tuple[str, ...]) -> list[Any]:
    values: list[Any] = []
    for path in paths:
        value: Any = mapping
        for key in path:
            if not isinstance(value, dict):
                value = None
                break
            value = value.get(key)
        if value not in (None, ""):
            values.append(value)
    return values


def _candidate_rows(cur: Any, company_code: str) -> list[dict[str, Any]]:
    cur.execute(
        """
        SELECT c.phone, c.name, c.email, c.profile, c.raw_json,
               a.app_key, a.status, a.position_code, a.updated_at,
               k.key_type AS identity_key_type,
               k.normalized_value AS identity_key_value,
               k.authority AS identity_key_authority
        FROM candidates c
        JOIN applications a ON a.phone=c.phone
        LEFT JOIN candidate_identity_keys k
          ON k.company_code=a.company_code AND k.candidate_phone=c.phone
         AND k.active
        WHERE a.company_code=%s
        ORDER BY a.updated_at DESC NULLS LAST, a.created_at DESC NULLS LAST
        """,
        (company_code,),
    )
    return [_row(value) for value in cur.fetchall()]


def _candidate_evidence(row: dict[str, Any]) -> dict[str, Any]:
    profile = row.get("profile") if isinstance(row.get("profile"), dict) else {}
    raw = row.get("raw_json") if isinstance(row.get("raw_json"), dict) else {}
    emails = {
        value
        for value in (
            normalize_email(item)
            for item in [
                row.get("email"),
                *_nested(
                    profile,
                    ("email",),
                    ("contact", "email"),
                    ("contact_details", "email"),
                ),
                *_nested(raw, ("contact", "email"), ("candidate_email",)),
            ]
        )
        if value
    }
    phones = {
        value
        for value in (
            normalize_phone(item)
            for item in [
                None if str(row.get("phone") or "").startswith("imp-") else row.get("phone"),
                *_nested(
                    profile,
                    ("phone",),
                    ("contact", "phone"),
                    ("contact_details", "phone"),
                ),
                *_nested(raw, ("contact", "phone"), ("candidate_phone",)),
            ]
        )
        if value
    }
    if row.get("identity_key_type") == "email":
        key_email = normalize_email(row.get("identity_key_value"))
        if key_email:
            emails.add(key_email)
    if row.get("identity_key_type") == "phone":
        key_phone = normalize_phone(row.get("identity_key_value"))
        if key_phone:
            phones.add(key_phone)
    return {
        "candidate_phone": row.get("phone"),
        "app_key": row.get("app_key"),
        "status": row.get("status"),
        "name": normalize_name(row.get("name")),
        "emails": sorted(emails),
        "phones": sorted(phones),
    }


def _provisional_phone(
    company_code: str,
    *,
    email: str | None,
    phone: str | None,
    content_sha256: str,
) -> str:
    seed = email or phone or content_sha256
    token = hashlib.sha1(
        f"{company_code}:{seed}".encode("utf-8")
    ).hexdigest()[:16]
    return f"imp-{company_code.lower()}-{token}"


def _app_key(candidate_phone: str, company_code: str) -> str:
    return f"{candidate_phone}-{company_code}-IMPORT"


def _name_similarity(left: str | None, right: str | None) -> float:
    if not left or not right:
        return 0.0
    ignored = {
        "cv",
        "resume",
        "curriculum",
        "vitae",
        "updated",
        "update",
        "new",
        "v2",
        "السيرة",
        "الذاتية",
    }
    left_tokens = [token for token in left.split() if token not in ignored]
    right_tokens = [token for token in right.split() if token not in ignored]
    normalized_left = " ".join(left_tokens) or left
    normalized_right = " ".join(right_tokens) or right
    return SequenceMatcher(None, normalized_left, normalized_right).ratio()


def _names_conflict(left: str | None, right: str | None) -> bool:
    if not left or not right:
        return False
    ignored = {
        "cv",
        "resume",
        "curriculum",
        "vitae",
        "updated",
        "update",
        "new",
        "v2",
        "السيرة",
        "الذاتية",
    }
    left_tokens = {token for token in left.split() if token not in ignored}
    right_tokens = {token for token in right.split() if token not in ignored}
    if left_tokens and right_tokens and left_tokens.isdisjoint(right_tokens):
        return True
    return _name_similarity(left, right) < 0.58


@dataclass(frozen=True)
class IdentityDecision:
    outcome: Literal[
        "safe_exact_reuse", "new_candidate", "possible_match", "conflict"
    ]
    confidence: float
    candidate_phone: str | None
    app_key: str | None
    candidate_matches: list[dict[str, Any]]
    strong_keys: list[str]
    weak_keys: list[str]
    reason_codes: list[str]
    ownership_confirmed: bool


def _decide_identity(
    *,
    company_code: str,
    content_sha256: str,
    extracted_email: str | None,
    extracted_phone: str | None,
    normalized_full_name: str | None,
    rows: list[dict[str, Any]],
) -> IdentityDecision:
    candidates: dict[str, dict[str, Any]] = {}
    for row in rows:
        evidence = _candidate_evidence(row)
        phone = str(evidence["candidate_phone"])
        item = candidates.setdefault(
            phone,
            {
                "candidate_phone": phone,
                "name": evidence["name"],
                "emails": set(),
                "phones": set(),
                "applications": [],
            },
        )
        item["emails"].update(evidence["emails"])
        item["phones"].update(evidence["phones"])
        item["applications"].append(
            {
                "app_key": evidence["app_key"],
                "status": evidence["status"],
                "position_code": row.get("position_code"),
            }
        )

    matches: list[dict[str, Any]] = []
    strong_candidates: set[str] = set()
    weak_candidates: set[str] = set()
    strong_keys: list[str] = []
    weak_keys: list[str] = []
    for phone, candidate in candidates.items():
        email_match = bool(extracted_email and extracted_email in candidate["emails"])
        phone_match = bool(extracted_phone and extracted_phone in candidate["phones"])
        similarity = _name_similarity(normalized_full_name, candidate["name"])
        if email_match or phone_match or similarity >= 0.72:
            matches.append(
                {
                    "candidate_phone": phone,
                    "email_exact": email_match,
                    "phone_exact": phone_match,
                    "name_similarity": round(similarity, 5),
                    "applications": candidate["applications"],
                }
            )
        if email_match:
            strong_candidates.add(phone)
            strong_keys.append(f"email:{extracted_email}")
        if phone_match:
            strong_candidates.add(phone)
            strong_keys.append(f"phone:{extracted_phone}")
        if similarity >= 0.72:
            weak_candidates.add(phone)
            weak_keys.append(f"name:{normalized_full_name}")

    if len(strong_candidates) > 1:
        return IdentityDecision(
            "conflict",
            0.0,
            None,
            None,
            matches,
            sorted(set(strong_keys)),
            sorted(set(weak_keys)),
            ["strong_keys_resolve_to_different_candidates"],
            False,
        )
    if len(strong_candidates) == 1:
        candidate_phone = next(iter(strong_candidates))
        candidate = candidates[candidate_phone]
        similarity = _name_similarity(normalized_full_name, candidate["name"])
        conflicting_email = bool(
            extracted_email
            and candidate["emails"]
            and extracted_email not in candidate["emails"]
        )
        conflicting_phone = bool(
            extracted_phone
            and candidate["phones"]
            and extracted_phone not in candidate["phones"]
        )
        conflicting_name = _names_conflict(
            normalized_full_name, candidate["name"]
        )
        if conflicting_email or conflicting_phone or conflicting_name:
            reasons = []
            if conflicting_email:
                reasons.append("conflicting_cv_email")
            if conflicting_phone:
                reasons.append("conflicting_cv_phone")
            if conflicting_name:
                reasons.append("conflicting_cv_name")
            return IdentityDecision(
                "conflict",
                0.0,
                None,
                None,
                matches,
                sorted(set(strong_keys)),
                sorted(set(weak_keys)),
                reasons,
                False,
            )
        held = next(
            (
                app
                for app in candidate["applications"]
                if str(app.get("status") or "").lower() in HELD_APPLICATION_STATUSES
                and not str(app.get("position_code") or "").strip()
            ),
            None,
        )
        selected_app = (
            str(held["app_key"])
            if held
            else _app_key(candidate_phone, company_code)
        )
        return IdentityDecision(
            "safe_exact_reuse",
            1.0 if extracted_email and extracted_phone else 0.98,
            candidate_phone,
            selected_app,
            matches,
            sorted(set(strong_keys)),
            sorted(set(weak_keys)),
            ["tenant_scoped_exact_identity_key"],
            True,
        )
    if weak_candidates:
        return IdentityDecision(
            "possible_match",
            max(
                (
                    float(match["name_similarity"])
                    for match in matches
                    if match["candidate_phone"] in weak_candidates
                ),
                default=0.0,
            ),
            None,
            None,
            matches,
            [],
            sorted(set(weak_keys)),
            ["weak_name_match_requires_hr_review"],
            False,
        )
    provisional = _provisional_phone(
        company_code,
        email=extracted_email,
        phone=extracted_phone,
        content_sha256=content_sha256,
    )
    return IdentityDecision(
        "new_candidate",
        0.95 if extracted_email or extracted_phone else 0.75,
        provisional,
        _app_key(provisional, company_code),
        matches,
        [
            key
            for key in (
                f"email:{extracted_email}" if extracted_email else None,
                f"phone:{extracted_phone}" if extracted_phone else None,
            )
            if key
        ],
        [f"name:{normalized_full_name}"] if normalized_full_name else [],
        ["no_tenant_scoped_identity_match"],
        True,
    )


def resolve_identity(
    cur: Any,
    *,
    company_code: str,
    inbound_id: str,
    intake_document_id: str,
    content_sha256: str,
    sender_email: str | None,
    extracted_identity: dict[str, Any],
) -> dict[str, Any]:
    existing = latest_identity_resolution(
        cur, company_code=company_code, intake_document_id=intake_document_id
    )
    if existing:
        return existing
    email = normalize_email(extracted_identity.get("email"))
    phone = normalize_phone(extracted_identity.get("phone"))
    name = normalize_name(
        extracted_identity.get("full_name") or extracted_identity.get("name")
    )
    decision = _decide_identity(
        company_code=company_code,
        content_sha256=content_sha256,
        extracted_email=email,
        extracted_phone=phone,
        normalized_full_name=name,
        rows=_candidate_rows(cur, company_code),
    )
    cur.execute(
        """
        INSERT INTO inbound_cv_identity_resolutions
          (company_code, inbound_id, intake_document_id, content_sha256,
           identity_policy_version, sender_email_provenance, extracted_email,
           extracted_phone, normalized_full_name, outcome, confidence,
           selected_candidate_phone, selected_app_key, candidate_matches,
           strong_keys, weak_keys, reason_codes, ownership_confirmed,
           actor_service_identity)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
        RETURNING *, resolution_id::text AS resolution_id,
                  intake_document_id::text AS intake_document_id,
                  inbound_id::text AS inbound_id
        """,
        (
            company_code,
            inbound_id,
            intake_document_id,
            content_sha256,
            IDENTITY_POLICY_VERSION,
            normalize_email(sender_email),
            email,
            phone,
            name,
            decision.outcome,
            decision.confidence,
            decision.candidate_phone,
            decision.app_key,
            Json(decision.candidate_matches),
            Json(decision.strong_keys),
            Json(decision.weak_keys),
            Json(decision.reason_codes),
            decision.ownership_confirmed,
            _actor(),
        ),
    )
    resolution = _row(cur.fetchone())
    cur.execute(
        """
        INSERT INTO inbound_cv_identity_events
          (company_code, resolution_id, intake_document_id, event_type,
           actor_service_identity, payload)
        VALUES (%s,%s,%s,%s,%s,%s)
        """,
        (
            company_code,
            resolution["resolution_id"],
            intake_document_id,
            (
                "identity_conflict_detected"
                if decision.outcome == "conflict"
                else "identity_resolution_completed"
            ),
            _actor(),
            Json(
                {
                    "outcome": decision.outcome,
                    "reason_codes": decision.reason_codes,
                    "sender_is_provenance_only": True,
                }
            ),
        ),
    )
    if decision.outcome in {"possible_match", "conflict"}:
        cur.execute(
            """
            INSERT INTO inbound_cv_identity_reviews
              (company_code, resolution_id, intake_document_id, review_type,
               possible_candidate_phones, possible_app_keys, reason_codes)
            VALUES (%s,%s,%s,%s,%s,%s,%s)
            ON CONFLICT (resolution_id) DO NOTHING
            """,
            (
                company_code,
                resolution["resolution_id"],
                intake_document_id,
                decision.outcome,
                Json(
                    sorted(
                        {
                            str(match["candidate_phone"])
                            for match in decision.candidate_matches
                        }
                    )
                ),
                Json(
                    sorted(
                        {
                            str(app["app_key"])
                            for match in decision.candidate_matches
                            for app in match.get("applications") or []
                        }
                    )
                ),
                Json(decision.reason_codes),
            ),
        )
    return resolution


def record_identity_failure(
    cur: Any,
    *,
    company_code: str,
    inbound_id: str,
    intake_document_id: str,
    content_sha256: str,
    sender_email: str | None,
    reason_code: str,
) -> dict[str, Any]:
    existing = latest_identity_resolution(
        cur, company_code=company_code, intake_document_id=intake_document_id
    )
    if existing:
        return existing
    cur.execute(
        """
        INSERT INTO inbound_cv_identity_resolutions
          (company_code, inbound_id, intake_document_id, content_sha256,
           identity_policy_version, sender_email_provenance, outcome, confidence,
           candidate_matches, strong_keys, weak_keys, reason_codes,
           ownership_confirmed, actor_service_identity)
        VALUES (%s,%s,%s,%s,%s,%s,'possible_match',0,'[]','[]','[]',%s,false,%s)
        RETURNING *, resolution_id::text AS resolution_id,
                  intake_document_id::text AS intake_document_id,
                  inbound_id::text AS inbound_id
        """,
        (
            company_code,
            inbound_id,
            intake_document_id,
            content_sha256,
            IDENTITY_POLICY_VERSION,
            normalize_email(sender_email),
            Json([reason_code]),
            _actor(),
        ),
    )
    resolution = _row(cur.fetchone())
    cur.execute(
        """
        INSERT INTO inbound_cv_identity_reviews
          (company_code, resolution_id, intake_document_id, review_type,
           reason_codes)
        VALUES (%s,%s,%s,'identity_extraction_failed',%s)
        ON CONFLICT (resolution_id) DO NOTHING
        """,
        (
            company_code,
            resolution["resolution_id"],
            intake_document_id,
            Json([reason_code]),
        ),
    )
    cur.execute(
        """
        INSERT INTO inbound_cv_identity_events
          (company_code, resolution_id, intake_document_id, event_type,
           actor_service_identity, payload)
        VALUES (%s,%s,%s,'identity_extraction_failed',%s,%s)
        """,
        (
            company_code,
            resolution["resolution_id"],
            intake_document_id,
            _actor(),
            Json({"reason_code": reason_code, "sender_is_provenance_only": True}),
        ),
    )
    return resolution


def latest_identity_resolution(
    cur: Any, *, company_code: str, intake_document_id: str
) -> dict[str, Any] | None:
    cur.execute(
        """
        SELECT *, resolution_id::text AS resolution_id,
               intake_document_id::text AS intake_document_id,
               inbound_id::text AS inbound_id
        FROM inbound_cv_identity_resolutions
        WHERE company_code=%s AND intake_document_id=%s
          AND identity_policy_version=%s
        ORDER BY created_at DESC LIMIT 1
        """,
        (company_code, intake_document_id, IDENTITY_POLICY_VERSION),
    )
    row = cur.fetchone()
    return _row(row) if row else None


def binding_is_authorized(
    cur: Any,
    *,
    company_code: str,
    intake_document_id: str,
    content_sha256: str,
    candidate_phone: str | None = None,
    app_key: str | None = None,
) -> bool:
    if not scan_is_authoritatively_clean(
        cur,
        company_code=company_code,
        intake_document_id=intake_document_id,
        content_sha256=content_sha256,
    ):
        return False
    resolution = latest_identity_resolution(
        cur, company_code=company_code, intake_document_id=intake_document_id
    )
    if not resolution:
        return False
    if resolution.get("outcome") not in ACCEPTED_IDENTITY_OUTCOMES:
        return False
    if not resolution.get("ownership_confirmed"):
        return False
    if candidate_phone and resolution.get("selected_candidate_phone") != candidate_phone:
        return False
    if app_key and resolution.get("selected_app_key") != app_key:
        return False
    return True


def held_review_extraction_authorized(
    cur: Any,
    *,
    company_code: str,
    intake_document_id: str,
    content_sha256: str,
    intake_metadata: dict[str, Any] | None = None,
    held_application: bool = False,
) -> bool:
    """Allow CV extraction for scan-clean Held identity-review documents.

    Wave D6B: conflict / possible_match / weak-CV Held apps are intentionally not
    ownership-bound. Extraction may still run against the Held surrogate so fields
    promote into the review record. This must never be labeled as
    ``intake_document_not_clean`` when ``safety_state=clean``.
    """
    if not scan_is_authoritatively_clean(
        cur,
        company_code=company_code,
        intake_document_id=intake_document_id,
        content_sha256=content_sha256,
    ):
        return False
    meta = intake_metadata if isinstance(intake_metadata, dict) else {}
    held_review_doc = bool(
        held_application
        or meta.get("held_materialization_status")
        or meta.get("held_terminal_reason")
        or meta.get("identity_review_warning")
    )
    resolution = latest_identity_resolution(
        cur, company_code=company_code, intake_document_id=intake_document_id
    )
    outcome = str((resolution or {}).get("outcome") or "")
    non_accepted_identity = bool(
        resolution and outcome and outcome not in ACCEPTED_IDENTITY_OUTCOMES
    )
    return held_review_doc or non_accepted_identity


def record_candidate_identity_keys(
    cur: Any,
    *,
    company_code: str,
    candidate_phone: str,
    resolution: dict[str, Any],
) -> None:
    for key_type, value in (
        ("email", normalize_email(resolution.get("extracted_email"))),
        ("phone", normalize_phone(resolution.get("extracted_phone"))),
    ):
        if not value:
            continue
        cur.execute(
            """
            INSERT INTO candidate_identity_keys
              (company_code, candidate_phone, key_type, normalized_value,
               authority, source_ref)
            VALUES (%s,%s,%s,%s,'cv_extracted',%s)
            ON CONFLICT DO NOTHING
            """,
            (
                company_code,
                candidate_phone,
                key_type,
                value,
                f"inbound-resolution:{resolution.get('resolution_id')}",
            ),
        )


def decision_json(decision: dict[str, Any]) -> str:
    return json.dumps(decision, default=str, sort_keys=True)
