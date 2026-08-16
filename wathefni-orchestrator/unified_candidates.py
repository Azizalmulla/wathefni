"""Unified Candidates + Talent Pool read authority (Option B, Phase 1).

Held intake (`needs_role` / `import_review`) and live Job applications share one
Candidates read surface. Lifecycle, Ranking, Interviews, Offers, and Reports
predicates remain frozen — this module only adds governed read models,
append-only fact review, privacy hooks, saved views, and Intake Operations.

Rules:
- Never overwrite `application-cv-facts-v1` extraction snapshots.
- Never advertise lifecycle / outreach / ranking actions for held rows.
- Never expose synthetic `imp-…` compatibility keys as HR contacts.
- Missing facts are Not extracted / Unknown, never negative facts.
- No Link to Job / intake_admit / outreach in this phase.
- Classification is a separate optional authority (`talent_pool_classification`);
  not coupled to this feature flag.
"""

from __future__ import annotations

import json
import os
import re
import uuid
from typing import Any, Callable

FEATURE_FLAG = "WATHEFNI_UNIFIED_CANDIDATES_TALENT_POOL"
FEATURE_TENANTS_FLAG = "WATHEFNI_UNIFIED_CANDIDATES_TENANTS"

HELD_ACTIVE_STATUSES = ("needs_role", "import_review")
HELD_ARCHIVED_STATUS = "import_archived"
HELD_ALL_STATUSES = (*HELD_ACTIVE_STATUSES, HELD_ARCHIVED_STATUS)

VIEW_ALL = "all"
VIEW_ACTIVE = "active"
VIEW_TALENT_POOL = "talent_pool"
VIEW_HIRED = "hired"
VIEW_ARCHIVED = "archived"
VIEW_RESTRICTED = "restricted"
SAVED_VIEWS = (VIEW_ALL, VIEW_ACTIVE, VIEW_TALENT_POOL, VIEW_HIRED, VIEW_ARCHIVED, VIEW_RESTRICTED)

RECORD_TALENT_POOL = "talent_pool"
RECORD_ACTIVE = "active_application"
RECORD_HIRED = "hired"
RECORD_ARCHIVED = "archived"
RECORD_RESTRICTED = "restricted"

MATCH_METADATA = "Matched metadata"
MATCH_CV_TEXT = "Matched CV text"
MATCH_EXTRACTED = "Matched extracted fact"
MATCH_CONFIRMED = "Matched confirmed fact"
MATCH_EDUCATION = "Matched education"
MATCH_SEMANTIC = "Semantic similarity"
# Classification match reasons are owned by talent_pool_classification; re-exported
# for Unified Candidates search disclosure when classification UI is enabled.
MATCH_CONFIRMED_CLASSIFICATION = "Matched confirmed classification"
MATCH_AI_SUGGESTED_CLASSIFICATION = "Matched AI-suggested classification"
MATCH_CLASSIFICATION_EVIDENCE = "Matched classification evidence"

FACT_EVENT_ACTIONS = ("confirm", "correct", "reject", "add", "supersede")

SURROGATE_PHONE_RE = re.compile(r"^imp-", re.IGNORECASE)

PRIVACY_NOT_CONFIGURED = "Privacy and retention policy not configured"


def _truthy(raw: str | None) -> bool:
    return str(raw or "").strip().lower() in {"1", "true", "on", "yes"}


def feature_master_enabled(environ: dict[str, str] | None = None) -> bool:
    """Global master switch. Default OFF."""
    env = environ if environ is not None else os.environ
    return _truthy(env.get(FEATURE_FLAG))


def feature_allowed_tenants(environ: dict[str, str] | None = None) -> set[str]:
    """Comma-separated tenant allowlist. Empty allowlist => nobody (never global)."""
    env = environ if environ is not None else os.environ
    raw = str(env.get(FEATURE_TENANTS_FLAG) or "").strip()
    if not raw:
        return set()
    return {part.strip().upper() for part in raw.split(",") if part.strip()}


def feature_enabled_for_company(company_code: str | None, environ: dict[str, str] | None = None) -> bool:
    """Tenant-scoped enablement only.

    - Empty TENANTS => disabled for everyone (global enablement is impossible).
    - Non-empty TENANTS => only listed companies, even when master is OFF
      (production canary override with global flag remaining OFF).
    - Master alone never enables all tenants.
    """
    company = str(company_code or "").strip().upper()
    if not company:
        return False
    return company in feature_allowed_tenants(environ)


def feature_status(company_code: str | None = None, environ: dict[str, str] | None = None) -> dict[str, Any]:
    tenants = sorted(feature_allowed_tenants(environ))
    master = feature_master_enabled(environ)
    company = str(company_code or "").strip().upper() or None
    enabled = feature_enabled_for_company(company, environ) if company else False
    return {
        "flag": FEATURE_FLAG,
        "master_enabled": master,
        "allowed_tenants": tenants,
        "company_code": company,
        "enabled_for_company": enabled,
        "activation_mode": (
            "tenant_canary_override"
            if enabled and not master
            else ("tenant_allowlist" if enabled and master else "off")
        ),
    }


SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS candidate_record_governance (
  company_code text NOT NULL,
  app_key text NOT NULL,
  recruiter_owner_user_id text,
  department_intake_tag text,
  tenant_controller_code text,
  processing_basis_code text,
  privacy_notice_id text,
  privacy_notice_version text,
  retention_policy_id text,
  retention_policy_version text,
  retention_deadline_at timestamptz,
  archive_state text,
  restriction_state text,
  legal_hold_state text,
  deletion_request_state text,
  audit_tombstone_ref text,
  tags jsonb NOT NULL DEFAULT '[]'::jsonb,
  metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (company_code, app_key)
);
CREATE INDEX IF NOT EXISTS idx_candidate_governance_company_owner
  ON candidate_record_governance(company_code, recruiter_owner_user_id);
CREATE INDEX IF NOT EXISTS idx_candidate_governance_company_archive
  ON candidate_record_governance(company_code, archive_state);
CREATE INDEX IF NOT EXISTS idx_candidate_governance_company_restriction
  ON candidate_record_governance(company_code, restriction_state);

CREATE TABLE IF NOT EXISTS candidate_fact_review_events (
  event_id uuid PRIMARY KEY,
  company_code text NOT NULL,
  app_key text NOT NULL,
  document_version_id text,
  extraction_version_id text,
  fact_path text NOT NULL,
  action text NOT NULL,
  previous_value jsonb,
  new_value jsonb,
  evidence_refs jsonb NOT NULL DEFAULT '[]'::jsonb,
  note text,
  actor_user_id text,
  actor_email text,
  supersedes_event_id uuid,
  created_at timestamptz NOT NULL DEFAULT now(),
  CHECK (action IN ('confirm','correct','reject','add','supersede'))
);
CREATE INDEX IF NOT EXISTS idx_fact_review_company_app
  ON candidate_fact_review_events(company_code, app_key, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_fact_review_fact_path
  ON candidate_fact_review_events(company_code, app_key, fact_path, created_at DESC);

CREATE TABLE IF NOT EXISTS candidate_saved_views (
  view_id uuid PRIMARY KEY,
  company_code text NOT NULL,
  actor_user_id text NOT NULL,
  name text NOT NULL,
  filters jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (company_code, actor_user_id, name)
);
CREATE INDEX IF NOT EXISTS idx_candidate_saved_views_actor
  ON candidate_saved_views(company_code, actor_user_id, updated_at DESC);
"""


def ensure_unified_candidates_schema(cur: Any) -> None:
    cur.execute(SCHEMA_SQL)


def is_surrogate_phone(value: Any) -> bool:
    return bool(SURROGATE_PHONE_RE.match(str(value or "").strip()))


def is_held_status(status: Any) -> bool:
    return str(status or "").strip().lower() in HELD_ALL_STATUSES


def is_active_held_status(status: Any) -> bool:
    return str(status or "").strip().lower() in HELD_ACTIVE_STATUSES


def grounded_contact_email(row: dict[str, Any]) -> str | None:
    raw = row.get("raw_json") if isinstance(row.get("raw_json"), dict) else {}
    profile = row.get("candidate_profile") if isinstance(row.get("candidate_profile"), dict) else {}
    contacts = profile.get("contacts") if isinstance(profile.get("contacts"), dict) else {}
    email = (
        contacts.get("email")
        or profile.get("email")
        or row.get("candidate_email")
        or raw.get("candidate_email")
        or raw.get("email")
    )
    email = str(email or "").strip() or None
    return email


def grounded_contact_phone(row: dict[str, Any]) -> str | None:
    """Return CV-grounded phone only. Never return surrogate imp- keys."""
    phone = str(row.get("phone") or "").strip()
    if is_surrogate_phone(phone):
        raw = row.get("raw_json") if isinstance(row.get("raw_json"), dict) else {}
        profile = row.get("candidate_profile") if isinstance(row.get("candidate_profile"), dict) else {}
        contacts = profile.get("contacts") if isinstance(profile.get("contacts"), dict) else {}
        candidate_phone = (
            contacts.get("phone")
            or profile.get("phone")
            or raw.get("candidate_phone")
            or raw.get("phone")
        )
        candidate_phone = str(candidate_phone or "").strip() or None
        if candidate_phone and not is_surrogate_phone(candidate_phone):
            return candidate_phone
        return None
    return phone or None


def display_phone_for_hr(row: dict[str, Any]) -> str | None:
    return grounded_contact_phone(row)


def governance_is_restricted(gov: dict[str, Any] | None) -> bool:
    if not isinstance(gov, dict):
        return False
    state = str(gov.get("restriction_state") or "").strip().lower()
    deletion = str(gov.get("deletion_request_state") or "").strip().lower()
    return state in {"restricted", "active", "true", "1"} or deletion in {
        "requested",
        "in_progress",
        "pending",
        "completed",
    }


def governance_is_archived(gov: dict[str, Any] | None, status: Any) -> bool:
    if str(status or "").strip().lower() == HELD_ARCHIVED_STATUS:
        return True
    if not isinstance(gov, dict):
        return False
    return str(gov.get("archive_state") or "").strip().lower() in {"archived", "active", "true", "1"}


def record_state_for(row: dict[str, Any], gov: dict[str, Any] | None = None) -> str:
    status = str(row.get("status") or "").strip().lower()
    if governance_is_restricted(gov):
        return RECORD_RESTRICTED
    if governance_is_archived(gov, status):
        return RECORD_ARCHIVED
    if status in HELD_ACTIVE_STATUSES:
        return RECORD_TALENT_POOL
    if status == "hired":
        return RECORD_HIRED
    return RECORD_ACTIVE


def record_state_label(state: str) -> str:
    return {
        RECORD_TALENT_POOL: "Talent Pool",
        RECORD_ACTIVE: "Active application",
        RECORD_HIRED: "Hired",
        RECORD_ARCHIVED: "Archived",
        RECORD_RESTRICTED: "Restricted",
    }.get(state, state)


def cv_processing_display(row: dict[str, Any]) -> dict[str, Any]:
    raw = row.get("raw_json") if isinstance(row.get("raw_json"), dict) else {}
    cv = raw.get("cv") if isinstance(raw.get("cv"), dict) else {}
    processing = cv.get("processing") if isinstance(cv.get("processing"), dict) else {}
    status = str(
        processing.get("status")
        or cv.get("processing_status")
        or ("received" if row.get("cv_received") or cv else "not_received")
    ).strip().lower()
    text_ok = bool(processing.get("text_extracted") or processing.get("normalized_text"))
    profile_ok = bool(processing.get("profile_parsed") or row.get("candidate_profile"))
    failed = status in {"failed", "error", "dead_letter"}
    if failed:
        label = "Failed"
        bucket = "failed"
    elif profile_ok and text_ok:
        label = "Ready"
        bucket = "ready"
    elif text_ok or status in {"partial", "incomplete", "processing"}:
        label = "Partial"
        bucket = "partial"
    elif row.get("cv_received") or cv:
        label = "Received"
        bucket = "received"
    else:
        label = "Not received"
        bucket = "not_received"
    return {"status": status or bucket, "label": label, "bucket": bucket, "received": bool(row.get("cv_received") or cv)}


def completeness_summary(profile: dict[str, Any] | None) -> list[dict[str, str]]:
    """Section-aware completeness. Missing ≠ candidate lacks the fact."""
    profile = profile if isinstance(profile, dict) else {}
    contacts = profile.get("contacts") if isinstance(profile.get("contacts"), dict) else {}
    skills = profile.get("skills") if isinstance(profile.get("skills"), list) else []
    languages = profile.get("languages") if isinstance(profile.get("languages"), list) else []
    education = profile.get("education") if isinstance(profile.get("education"), list) else []
    employment = (
        profile.get("employment")
        or profile.get("experience")
        or profile.get("work_history")
        or []
    )
    if not isinstance(employment, list):
        employment = []
    certifications = profile.get("certifications") if isinstance(profile.get("certifications"), list) else []

    def section(name: str, present: bool, partial: bool = False) -> dict[str, str]:
        if present and not partial:
            return {"section": name, "state": "grounded", "label": f"{name} grounded"}
        if present and partial:
            return {"section": name, "state": "partial", "label": f"{name} partially extracted"}
        if name.lower() in {"skills", "languages", "certifications"}:
            return {"section": name, "state": "not_extracted", "label": f"{name} not extracted"}
        return {"section": name, "state": "incomplete", "label": f"{name} incomplete"}

    contact_present = bool(contacts.get("email") or contacts.get("phone") or profile.get("email") or profile.get("phone"))
    return [
        section("Contacts", contact_present),
        section("Employment", bool(employment), partial=len(employment) == 1),
        section("Skills", bool(skills), partial=0 < len(skills) < 3),
        section("Languages", bool(languages)),
        section("Education", bool(education), partial=len(education) > 4),
        section("Certifications", bool(certifications)),
    ]


def held_allowed_actions(permissions: set[str] | list[str] | None, *, cv_received: bool) -> list[str]:
    """Held rows may only preview/download CV under prehire.read. No lifecycle/outreach."""
    perms = {str(p) for p in (permissions or [])}
    actions: list[str] = []
    if cv_received and "prehire.read" in perms:
        actions.extend(["preview_cv", "download_cv"])
    return list(dict.fromkeys(actions))


def view_predicate_sql(view: str, alias: str = "a", gov_alias: str = "gov") -> tuple[str, list[Any]]:
    """Return SQL fragment + params for a saved view. Does not mutate live predicates elsewhere."""
    view_key = str(view or VIEW_ALL).strip().lower() or VIEW_ALL
    restricted = (
        f"(COALESCE({gov_alias}.restriction_state,'') ILIKE ANY(ARRAY['restricted','active','true','1']) "
        f"OR COALESCE({gov_alias}.deletion_request_state,'') ILIKE ANY(ARRAY['requested','in_progress','pending','completed']))"
    )
    archived = (
        f"(LOWER(COALESCE({alias}.status,'')) = '{HELD_ARCHIVED_STATUS}' "
        f"OR COALESCE({gov_alias}.archive_state,'') ILIKE ANY(ARRAY['archived','active','true','1']))"
    )
    held_active = f"LOWER(COALESCE({alias}.status,'')) IN ('needs_role','import_review')"
    hired = f"LOWER(COALESCE({alias}.status,'')) = 'hired'"
    live = (
        f"COALESCE({alias}.data_source, {alias}.raw_json->>'data_source', 'production') = 'production' "
        f"AND COALESCE({alias}.status, '') NOT IN ('needs_role','import_review','import_archived') "
        f"AND COALESCE({alias}.phone, '') NOT LIKE '9655555%%' "
        f"AND COALESCE({alias}.app_key, '') NOT ILIKE '%%TEST%%' "
        f"AND COALESCE({alias}.raw_json->>'candidate_name', {alias}.raw_json->>'name', '') NOT ILIKE 'test %%'"
    )

    if view_key == VIEW_TALENT_POOL:
        return f"({held_active}) AND NOT ({restricted}) AND NOT ({archived})", []
    if view_key == VIEW_ACTIVE:
        return (
            f"({live}) AND NOT ({hired}) AND NOT ({restricted}) AND NOT ({archived}) "
            f"AND LOWER(COALESCE({alias}.status,'')) NOT IN ('rejected','withdrawn')",
            [],
        )
    if view_key == VIEW_HIRED:
        return f"({hired}) AND NOT ({restricted})", []
    if view_key == VIEW_ARCHIVED:
        return f"({archived}) AND NOT ({restricted})", []
    if view_key == VIEW_RESTRICTED:
        return f"({restricted})", []
    # all: held active + live (incl hired) + exclude archived/restricted by default
    return (
        f"((({held_active}) OR ({live})) AND NOT ({restricted}) AND NOT ({archived}))",
        [],
    )


def extract_facts_snapshot(row: dict[str, Any]) -> dict[str, Any]:
    """Prefer application-cv-facts-v1 when present; else project from candidate profile."""
    raw = row.get("raw_json") if isinstance(row.get("raw_json"), dict) else {}
    cv = raw.get("cv") if isinstance(raw.get("cv"), dict) else {}
    processing = cv.get("processing") if isinstance(cv.get("processing"), dict) else {}
    for key in ("facts", "cv_facts", "application_cv_facts"):
        value = processing.get(key) or raw.get(key) or cv.get(key)
        if isinstance(value, dict) and value:
            schema = str(value.get("schema") or value.get("schema_version") or "")
            if "application-cv-facts" in schema or value.get("facts") or value.get("sections"):
                return {
                    "schema": schema or "application-cv-facts-v1",
                    "immutable": True,
                    "snapshot": value,
                    "source": "extraction_snapshot",
                }
    profile = row.get("candidate_profile") if isinstance(row.get("candidate_profile"), dict) else {}
    doc_meta = row.get("document_metadata") if isinstance(row.get("document_metadata"), dict) else {}
    if not profile and isinstance(doc_meta.get("profile"), dict):
        profile = doc_meta["profile"]
    return {
        "schema": "application-cv-facts-v1",
        "immutable": True,
        "snapshot": {
            "schema": "application-cv-facts-v1",
            "projected_from": "candidate_profile",
            "name": profile.get("name") or row.get("candidate_name"),
            "contacts": (profile.get("contacts") if isinstance(profile.get("contacts"), dict) else {})
            or {
                "email": grounded_contact_email(row),
                "phone": grounded_contact_phone(row),
            },
            "skills": profile.get("skills") or [],
            "languages": profile.get("languages") or [],
            "education": profile.get("education") or [],
            "employment": profile.get("employment") or profile.get("experience") or [],
            "certifications": profile.get("certifications") or [],
            "summary": profile.get("summary") or profile.get("profile_summary"),
            "location": profile.get("location"),
        },
        "source": "profile_projection",
    }


def effective_facts_from_events(
    snapshot: dict[str, Any],
    events: list[dict[str, Any]],
) -> dict[str, Any]:
    """Apply append-only review events. HR-confirmed takes display precedence."""
    base = snapshot.get("snapshot") if isinstance(snapshot.get("snapshot"), dict) else {}
    effective = json.loads(json.dumps(base)) if base else {}
    by_path: dict[str, dict[str, Any]] = {}
    for event in sorted(events, key=lambda e: str(e.get("created_at") or "")):
        path = str(event.get("fact_path") or "").strip()
        if not path:
            continue
        action = str(event.get("action") or "").strip().lower()
        if action == "reject":
            by_path[path] = {**event, "display_state": "rejected"}
            _set_path(effective, path, None)
        elif action in {"confirm", "correct", "add", "supersede"}:
            by_path[path] = {**event, "display_state": "hr_confirmed"}
            _set_path(effective, path, event.get("new_value"))
    return {
        "schema": snapshot.get("schema") or "application-cv-facts-v1",
        "extraction_snapshot": snapshot,
        "effective": effective,
        "reviews_by_path": by_path,
        "missing_policy": "Not extracted or Unknown — never a negative fact",
    }


def _set_path(target: dict[str, Any], path: str, value: Any) -> None:
    parts = [p for p in str(path).split(".") if p]
    if not parts:
        return
    cur: Any = target
    for part in parts[:-1]:
        if not isinstance(cur, dict):
            return
        nxt = cur.get(part)
        if not isinstance(nxt, dict):
            nxt = {}
            cur[part] = nxt
        cur = nxt
    if isinstance(cur, dict):
        cur[parts[-1]] = value


def fact_display_value(path: str, effective: dict[str, Any], snapshot: dict[str, Any]) -> dict[str, Any]:
    snap = snapshot.get("snapshot") if isinstance(snapshot.get("snapshot"), dict) else snapshot
    extracted = _get_path(snap if isinstance(snap, dict) else {}, path)
    current = _get_path(effective if isinstance(effective, dict) else {}, path)
    if current is not None and current != "":
        return {"path": path, "value": current, "state": "present", "label": None}
    if extracted is not None and extracted != "":
        return {"path": path, "value": extracted, "state": "extracted", "label": None}
    return {"path": path, "value": None, "state": "not_extracted", "label": "Not extracted"}


def _get_path(target: dict[str, Any], path: str) -> Any:
    cur: Any = target
    for part in [p for p in str(path).split(".") if p]:
        if not isinstance(cur, dict):
            return None
        cur = cur.get(part)
    return cur


def privacy_projection(gov: dict[str, Any] | None) -> dict[str, Any]:
    gov = gov if isinstance(gov, dict) else {}
    configured = bool(
        gov.get("privacy_notice_id")
        or gov.get("retention_policy_id")
        or gov.get("processing_basis_code")
        or gov.get("tenant_controller_code")
    )
    return {
        "configured": configured,
        "message": None if configured else PRIVACY_NOT_CONFIGURED,
        "tenant_controller_code": gov.get("tenant_controller_code"),
        "processing_basis_code": gov.get("processing_basis_code"),
        "privacy_notice_id": gov.get("privacy_notice_id"),
        "privacy_notice_version": gov.get("privacy_notice_version"),
        "retention_policy_id": gov.get("retention_policy_id"),
        "retention_policy_version": gov.get("retention_policy_version"),
        "retention_deadline_at": gov.get("retention_deadline_at"),
        "archive_state": gov.get("archive_state"),
        "restriction_state": gov.get("restriction_state"),
        "legal_hold_state": gov.get("legal_hold_state"),
        "deletion_request_state": gov.get("deletion_request_state"),
        "audit_tombstone_ref": gov.get("audit_tombstone_ref"),
    }


def enrich_application_summary(
    payload: dict[str, Any],
    row: dict[str, Any],
    *,
    gov: dict[str, Any] | None = None,
    permissions: set[str] | list[str] | None = None,
) -> dict[str, Any]:
    """Additive projection fields for unified Candidates rows."""
    status = str(row.get("status") or payload.get("status") or "")
    state = record_state_for(row, gov)
    held = is_active_held_status(status) or state == RECORD_TALENT_POOL
    processing = cv_processing_display(row)
    profile = None
    if isinstance(payload.get("candidate"), dict):
        profile = payload["candidate"].get("profile")
    if not isinstance(profile, dict):
        profile = row.get("candidate_profile") if isinstance(row.get("candidate_profile"), dict) else {}

    email = grounded_contact_email(row)
    phone = display_phone_for_hr(row)
    recruiter = None
    if isinstance(gov, dict) and gov.get("recruiter_owner_user_id"):
        recruiter = {
            "user_id": gov.get("recruiter_owner_user_id"),
            "label": gov.get("recruiter_owner_label") or gov.get("recruiter_owner_user_id"),
        }
    elif row.get("recruiter_user_id"):
        recruiter = {
            "user_id": row.get("recruiter_user_id"),
            "label": row.get("recruiter_label") or row.get("recruiter_user_id"),
        }

    payload = dict(payload)
    payload["record_state"] = state
    payload["record_state_label"] = record_state_label(state)
    payload["is_held"] = held or state in {RECORD_TALENT_POOL, RECORD_ARCHIVED}
    payload["job_display"] = "Not linked" if held or state == RECORD_TALENT_POOL else (
        (payload.get("position") or {}).get("title")
        or (payload.get("position") or {}).get("code")
        or "—"
    )
    payload["status_display"] = "Talent Pool" if state == RECORD_TALENT_POOL else (
        payload.get("status_label") or status
    )
    payload["recruiter_owner"] = recruiter or {"user_id": None, "label": "Unassigned"}
    payload["cv_processing"] = {
        **(payload.get("cv_processing") if isinstance(payload.get("cv_processing"), dict) else {}),
        **processing,
    }
    payload["assessment_display"] = "—" if held or state == RECORD_TALENT_POOL else None
    payload["communication_display"] = "No outreach" if held or state == RECORD_TALENT_POOL else None
    payload["grounded_contacts"] = {"email": email, "phone": phone}
    payload["completeness"] = completeness_summary(profile if isinstance(profile, dict) else {})
    payload["privacy"] = privacy_projection(gov)
    payload["department_intake_tag"] = (gov or {}).get("department_intake_tag") if isinstance(gov, dict) else None
    payload["link_to_job"] = {
        "available": False,
        "enabled": False,
        "label": "Link to Job",
        "reason": "Reserved for a future confirmed intake_admit action. Not implemented in this phase.",
    }

    # Hide surrogate phone from ordinary HR payloads.
    if is_surrogate_phone(payload.get("phone")):
        payload["phone"] = phone or ""
        payload["identity"] = {
            "compatibility_key_hidden": True,
            "note": "Compatibility identity is not shown as a confirmed person contact.",
        }

    if isinstance(payload.get("candidate"), dict):
        candidate = dict(payload["candidate"])
        if email:
            candidate["email"] = email
        payload["candidate"] = candidate

    if held or state in {RECORD_TALENT_POOL, RECORD_ARCHIVED, RECORD_RESTRICTED}:
        cv_received = bool((payload.get("cv") or {}).get("received"))
        payload["allowed_actions"] = held_allowed_actions(permissions, cv_received=cv_received)
        payload["waiting_for_hr"] = ["review_held_intake"] if state == RECORD_TALENT_POOL else []
        payload["communication"] = {
            **(payload.get("communication") if isinstance(payload.get("communication"), dict) else {}),
            "status": "intentionally_skipped",
            "message_kind": "no_outreach",
            "stage_changed_without_contact": False,
        }

    return payload


def search_match_reasons(
    *,
    query: str,
    row: dict[str, Any],
    effective_facts: dict[str, Any] | None = None,
    semantic_similarity: float | None = None,
    classification_effective: dict[str, Any] | None = None,
    classification_suggestions: list[dict[str, Any]] | None = None,
) -> list[str]:
    q = str(query or "").strip().lower()
    if not q:
        return []
    reasons: list[str] = []
    name = str(row.get("candidate_name") or "").lower()
    email = str(grounded_contact_email(row) or "").lower()
    phone = str(grounded_contact_phone(row) or "").lower()
    app_key = str(row.get("app_key") or "").lower()
    if q in name or q in email or q in phone or q in app_key:
        reasons.append(MATCH_METADATA)

    content = str(row.get("semantic_content") or "").lower()
    if q and q in content:
        reasons.append(MATCH_CV_TEXT)

    profile = row.get("candidate_profile") if isinstance(row.get("candidate_profile"), dict) else {}
    education = profile.get("education") if isinstance(profile.get("education"), list) else []
    if any(q in json.dumps(item, ensure_ascii=False).lower() for item in education):
        reasons.append(MATCH_EDUCATION)

    extracted_blob = json.dumps(profile, ensure_ascii=False).lower()
    if q in extracted_blob and MATCH_EDUCATION not in reasons:
        reasons.append(MATCH_EXTRACTED)
    elif q in extracted_blob and MATCH_EXTRACTED not in reasons:
        # education already matched; still note extracted fact if skills/etc match separately
        skills = profile.get("skills") if isinstance(profile.get("skills"), list) else []
        employment = profile.get("employment") if isinstance(profile.get("employment"), list) else []
        if any(q in json.dumps(item, ensure_ascii=False).lower() for item in [*skills, *employment]):
            reasons.append(MATCH_EXTRACTED)

    if isinstance(effective_facts, dict):
        reviews = effective_facts.get("reviews_by_path") if isinstance(effective_facts.get("reviews_by_path"), dict) else {}
        confirmed_blob = json.dumps(
            {
                path: event.get("new_value")
                for path, event in reviews.items()
                if str(event.get("display_state") or "") == "hr_confirmed"
            },
            ensure_ascii=False,
        ).lower()
        if q in confirmed_blob:
            reasons.append(MATCH_CONFIRMED)

    if semantic_similarity is not None and float(semantic_similarity) >= 0.55:
        reasons.append(MATCH_SEMANTIC)

    # Classification reasons stay separate from fact/metadata authority (no silent blend).
    if isinstance(classification_effective, dict):
        try:
            import talent_pool_classification as tpc

            reasons.extend(
                tpc.search_match_reasons_for_classification(
                    query=query,
                    effective=classification_effective,
                    suggestions=classification_suggestions,
                )
            )
        except Exception:
            pass

    # Preserve order, unique
    return list(dict.fromkeys(reasons))


def append_fact_review_event(
    cur: Any,
    *,
    company_code: str,
    app_key: str,
    fact_path: str,
    action: str,
    actor_user_id: str | None,
    actor_email: str | None = None,
    new_value: Any = None,
    previous_value: Any = None,
    evidence_refs: list[Any] | None = None,
    note: str | None = None,
    document_version_id: str | None = None,
    extraction_version_id: str | None = None,
    supersedes_event_id: str | None = None,
) -> dict[str, Any]:
    action_key = str(action or "").strip().lower()
    if action_key not in FACT_EVENT_ACTIONS:
        raise ValueError("invalid_fact_review_action")
    path = str(fact_path or "").strip()
    if not path:
        raise ValueError("fact_path_required")

    if action_key == "supersede":
        if not supersedes_event_id:
            raise ValueError("supersedes_event_id_required")
        cur.execute(
            """
            SELECT event_id, company_code, app_key, fact_path
            FROM candidate_fact_review_events
            WHERE event_id=%s AND company_code=%s AND app_key=%s
            LIMIT 1
            """,
            (supersedes_event_id, company_code, app_key),
        )
        prior = cur.fetchone()
        if not prior:
            raise ValueError("superseded_event_not_found")
        if str(prior.get("fact_path") or "") != path:
            raise ValueError("supersede_fact_path_mismatch")

    event_id = str(uuid.uuid4())
    cur.execute(
        """
        INSERT INTO candidate_fact_review_events (
          event_id, company_code, app_key, document_version_id, extraction_version_id,
          fact_path, action, previous_value, new_value, evidence_refs, note,
          actor_user_id, actor_email, supersedes_event_id
        ) VALUES (
          %s,%s,%s,%s,%s,%s,%s,%s::jsonb,%s::jsonb,%s::jsonb,%s,%s,%s,%s
        )
        RETURNING *
        """,
        (
            event_id,
            company_code,
            app_key,
            document_version_id,
            extraction_version_id,
            path,
            action_key,
            json.dumps(previous_value) if previous_value is not None else None,
            json.dumps(new_value) if new_value is not None else None,
            json.dumps(evidence_refs or []),
            note,
            actor_user_id,
            actor_email,
            supersedes_event_id,
        ),
    )
    row = dict(cur.fetchone() or {})
    row["event_id"] = str(row.get("event_id") or event_id)
    return row


def list_fact_review_events(cur: Any, *, company_code: str, app_key: str) -> list[dict[str, Any]]:
    cur.execute(
        """
        SELECT *
        FROM candidate_fact_review_events
        WHERE company_code=%s AND app_key=%s
        ORDER BY created_at ASC
        """,
        (company_code, app_key),
    )
    return [dict(r) for r in cur.fetchall()]


def upsert_saved_view(
    cur: Any,
    *,
    company_code: str,
    actor_user_id: str,
    name: str,
    filters: dict[str, Any],
    view_id: str | None = None,
) -> dict[str, Any]:
    name_clean = str(name or "").strip()
    if not name_clean:
        raise ValueError("saved_view_name_required")
    actor = str(actor_user_id or "").strip()
    if not actor:
        raise ValueError("actor_required")
    vid = str(view_id or uuid.uuid4())
    payload = dict(filters or {})
    try:
        import talent_pool_classification as _tpc

        if isinstance(payload.get("classification"), dict) or any(
            key in payload
            for key in (
                "career_area",
                "likely_role",
                "skill",
                "industry",
                "seniority",
                "experience_band",
                "classification_authority",
                "classification_confidence",
                "include_medium_ai",
                "includeMediumAi",
            )
        ):
            payload["classification"] = _tpc.normalize_saved_view_classification(payload)
            # Preserve versioned nested payload; leave unknown legacy keys intact.
            payload["classification_schema"] = _tpc.SAVED_VIEW_CLASSIFICATION_SCHEMA
    except Exception:
        # Old saved views / classification unavailable must still persist.
        pass
    cur.execute(
        """
        INSERT INTO candidate_saved_views (view_id, company_code, actor_user_id, name, filters)
        VALUES (%s,%s,%s,%s,%s::jsonb)
        ON CONFLICT (company_code, actor_user_id, name) DO UPDATE
          SET filters=EXCLUDED.filters, updated_at=now()
        RETURNING *
        """,
        (vid, company_code, actor, name_clean, json.dumps(payload)),
    )
    row = dict(cur.fetchone() or {})
    row["view_id"] = str(row.get("view_id") or vid)
    return row

def list_saved_views(cur: Any, *, company_code: str, actor_user_id: str) -> list[dict[str, Any]]:
    cur.execute(
        """
        SELECT *
        FROM candidate_saved_views
        WHERE company_code=%s AND actor_user_id=%s
        ORDER BY updated_at DESC
        """,
        (company_code, actor_user_id),
    )
    rows = []
    for row in cur.fetchall():
        item = dict(row)
        item["view_id"] = str(item.get("view_id"))
        rows.append(item)
    return rows


def delete_saved_view(cur: Any, *, company_code: str, actor_user_id: str, view_id: str) -> bool:
    cur.execute(
        """
        DELETE FROM candidate_saved_views
        WHERE company_code=%s AND actor_user_id=%s AND view_id=%s
        """,
        (company_code, actor_user_id, view_id),
    )
    return cur.rowcount > 0


def load_governance(cur: Any, *, company_code: str, app_key: str) -> dict[str, Any] | None:
    cur.execute(
        """
        SELECT *
        FROM candidate_record_governance
        WHERE company_code=%s AND app_key=%s
        LIMIT 1
        """,
        (company_code, app_key),
    )
    row = cur.fetchone()
    return dict(row) if row else None


def upsert_governance(
    cur: Any,
    *,
    company_code: str,
    app_key: str,
    patch: dict[str, Any],
) -> dict[str, Any]:
    allowed = {
        "recruiter_owner_user_id",
        "department_intake_tag",
        "tenant_controller_code",
        "processing_basis_code",
        "privacy_notice_id",
        "privacy_notice_version",
        "retention_policy_id",
        "retention_policy_version",
        "retention_deadline_at",
        "archive_state",
        "restriction_state",
        "legal_hold_state",
        "deletion_request_state",
        "audit_tombstone_ref",
        "tags",
        "metadata",
    }
    clean = {k: patch[k] for k in allowed if k in patch}
    cur.execute(
        """
        INSERT INTO candidate_record_governance (company_code, app_key)
        VALUES (%s,%s)
        ON CONFLICT (company_code, app_key) DO NOTHING
        """,
        (company_code, app_key),
    )
    if clean:
        sets = []
        params: list[Any] = []
        for key, value in clean.items():
            if key in {"tags", "metadata"}:
                sets.append(f"{key}=%s::jsonb")
                params.append(json.dumps(value if value is not None else ({} if key == "metadata" else [])))
            else:
                sets.append(f"{key}=%s")
                params.append(value)
        sets.append("updated_at=now()")
        params.extend([company_code, app_key])
        cur.execute(
            f"""
            UPDATE candidate_record_governance
            SET {', '.join(sets)}
            WHERE company_code=%s AND app_key=%s
            RETURNING *
            """,
            params,
        )
        return dict(cur.fetchone() or {})
    return load_governance(cur, company_code=company_code, app_key=app_key) or {}


# Internal/system processing states — never HR attention.
_HR_INTERNAL_PROC_STATUSES = frozenset(
    {
        "pending",
        "queued",
        "pending_async_processing",
        "processing",
        "extracting",
        "retrying",
        "running",
        "waiting_quota",
        "waiting_budget",
        "claimed",
    }
)
# Successful / idle held candidates (no job linked is valid Talent Pool).
_HR_READY_PROC_STATUSES = frozenset(
    {
        "ready",
        "complete",
        "completed",
        "done",
        "processed",
        "ok",
        "success",
        "",
    }
)


def intake_operations_summary(cur: Any, *, company_code: str) -> dict[str, Any]:
    """Read-only intake ops buckets + HR-actionable attention counts.

    Platform support may inspect queued/processing buckets. Normal HR attention
    excludes all healthy internal queue states and ready general candidates.
    """
    buckets = {
        "queued": 0,
        "processing": 0,
        "incomplete_extraction": 0,
        "failed_dead_letter": 0,
        "unsupported": 0,
        "password_protected": 0,
        "quarantined_malware": 0,
        "ready_held": 0,
    }
    # Prefer durable ingress tables when present; fall back to held application processing flags.
    try:
        cur.execute(
            """
            SELECT status, COUNT(*) AS count
            FROM intake_processing_jobs
            WHERE company_code=%s
            GROUP BY status
            """,
            (company_code,),
        )
        for row in cur.fetchall():
            status = str(row.get("status") or "").lower()
            count = int(row.get("count") or 0)
            if status in {"pending", "queued", "retrying", "waiting_quota", "waiting_budget"}:
                buckets["queued"] += count
            elif status in {"running", "processing", "claimed"}:
                buckets["processing"] += count
            elif status in {"failed", "dead_letter"}:
                buckets["failed_dead_letter"] += count
    except Exception:
        pass

    try:
        cur.execute(
            """
            SELECT
              COALESCE(raw_json->'cv'->'processing'->>'status','') AS proc_status,
              COALESCE(raw_json->'cv'->'processing'->>'scan_result','') AS scan_result,
              COUNT(*) AS count
            FROM applications
            WHERE company_code=%s AND status IN ('needs_role','import_review')
            GROUP BY 1, 2
            """,
            (company_code,),
        )
        for row in cur.fetchall():
            proc = str(row.get("proc_status") or "").lower()
            scan = str(row.get("scan_result") or "").lower()
            count = int(row.get("count") or 0)
            if "malware" in scan or "quarantine" in scan or proc in {"quarantined", "malware"}:
                buckets["quarantined_malware"] += count
            elif proc in {"unsupported", "unreadable", "invalid_corrupt", "mime_mismatch"}:
                buckets["unsupported"] += count
            elif "password" in proc:
                buckets["password_protected"] += count
            elif proc in {"failed", "error", "dead_letter"}:
                buckets["failed_dead_letter"] += count
            elif proc in {"partial", "incomplete"}:
                buckets["incomplete_extraction"] += count
            elif proc in _HR_READY_PROC_STATUSES:
                buckets["ready_held"] += count
            elif proc in {"processing", "extracting", "running", "claimed"}:
                buckets["processing"] += count
            elif proc in _HR_INTERNAL_PROC_STATUSES:
                buckets["queued"] += count
            else:
                # Unknown processing labels are incomplete until classified.
                buckets["incomplete_extraction"] += count
    except Exception:
        pass

    # HR attention: actionable human work only. Never queued/processing/ready_held.
    attention = (
        buckets["incomplete_extraction"]
        + buckets["failed_dead_letter"]
        + buckets["unsupported"]
        + buckets["password_protected"]
        + buckets["quarantined_malware"]
    )
    return {
        "company_code": company_code,
        "buckets": buckets,
        "attention_count": attention,
        "banner": f"{attention} CVs need HR action" if attention else None,
        "malware_release_forbidden": True,
        "note": "General HR cannot release or download quarantined/malware files. Queue and processing states are platform-support only.",
        "hr_attention_excludes": sorted(_HR_INTERNAL_PROC_STATUSES | {"ready_held", "queued", "processing"}),
    }


def sender_provenance(row: dict[str, Any]) -> dict[str, Any] | None:
    raw = row.get("raw_json") if isinstance(row.get("raw_json"), dict) else {}
    intake = raw.get("intake") if isinstance(raw.get("intake"), dict) else {}
    inbound = raw.get("inbound") if isinstance(raw.get("inbound"), dict) else {}
    import_meta = raw.get("import") if isinstance(raw.get("import"), dict) else {}
    sender = (
        intake.get("sender_email")
        or inbound.get("from")
        or inbound.get("sender")
        or import_meta.get("sender_email")
        or raw.get("sender_email")
    )
    if not sender:
        return None
    return {
        "sender_email": sender,
        "role": "provenance_only",
        "note": "Sender address is provenance, not the candidate identity key.",
    }


def held_reason(row: dict[str, Any]) -> str:
    status = str(row.get("status") or "").strip().lower()
    if status == "needs_role":
        return "This CV arrived without a confirmed Job link and is held in Talent Pool until HR links it."
    if status == "import_review":
        return "This imported CV needs human role confirmation before entering the live recruiting pipeline."
    if status == HELD_ARCHIVED_STATUS:
        return "This held intake record is archived."
    return "This record is not an active Job application."


JsonSafe = Callable[[Any], Any]
