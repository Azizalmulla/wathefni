"""Canonical Candidates Ranking authority (R0–R3).

Ranks applications for one specific job. Flow:

  tenant + permission
  → exact job/version
  → complete SQL application pool
  → deterministic hard-requirement eligibility
  → advisory soft ranking (optional bounded reorder)
  → evidence + provenance
  → HR decision (read-only; never mutates lifecycle)

Does not own CV extraction, identity merge, interviews product, offers, or reports.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Callable

import candidate_cv_evidence as _cv_evidence
import candidate_cv_facts as _cv_facts

# ---------------------------------------------------------------------------
# Versions / contracts
# ---------------------------------------------------------------------------

SCORING_CONFIG_VERSION = "ranking-soft-v2"
EVIDENCE_POLICY_VERSION = "ranking-evidence-policy-v1"
DENYLIST_VERSION = "ranking-denylist-v1"
NARRATIVE_PROMPT_VERSION = "ranking-terra-brief-v2"
NARRATIVE_MODEL = "gpt-5.6-terra"
_SKILL_STOPWORDS = {
    "with", "and", "the", "for", "years", "year", "experience", "background",
    "role", "job", "work", "working", "skills", "skill", "using", "from",
    "this", "that", "have", "has", "had", "also", "plus", "etc", "ability",
}
RANKING_MODULE = "pre_hiring"
RANKING_READ_PERMISSION = "prehire.read"
RANKING_CRITERIA_PERMISSION = "jobs.edit"
RANKING_CRITERIA_APPROVE_PERMISSION = "jobs.publish"
CANONICAL_EMBEDDING_MODEL = "voyage-4-large"
CANONICAL_RERANK_MODEL = "rerank-2.5"
RANKING_PROJECTION_VERSION = "ranking-embed-projection-v1"
AUTOMATIC_ROLE_PROFILE_VERSION = "ranking-role-profile-v1"

# Conservative defaults used only when an employer-authored job has no explicit
# requirements yet. They provide a useful title-based comparison without
# pretending these are hard requirements.
_ROLE_PROFILE_DEFAULTS: tuple[tuple[tuple[str, ...], tuple[str, ...]], ...] = (
    (
        ("human resources", "hr"),
        (
            "Recruitment and Talent Acquisition",
            "Candidate Screening",
            "Employee Relations",
            "HR Administration",
            "Employee Onboarding",
            "Communication and Interpersonal Skills",
            "Organization and Documentation",
        ),
    ),
    (
        ("accounting excel",),
        (
            "Accounting",
            "Microsoft Excel",
            "Bookkeeping",
            "Financial Reporting",
            "Account Reconciliation",
            "Accounts Payable and Receivable",
            "Spreadsheet Analysis",
            "Attention to Detail",
        ),
    ),
    (
        ("accounting", "accountant"),
        (
            "Accounting",
            "Bookkeeping",
            "Financial Reporting",
            "Account Reconciliation",
            "Accounts Payable and Receivable",
            "Spreadsheets",
            "Attention to Detail",
        ),
    ),
    (
        ("it maintenance", "it support", "help desk"),
        (
            "IT Support",
            "Hardware Troubleshooting",
            "Software Troubleshooting",
            "Network Maintenance",
            "Help Desk",
            "System Maintenance",
            "Technical Documentation",
        ),
    ),
    (
        ("it manager", "information technology manager"),
        (
            "IT Management",
            "Team Leadership",
            "IT Infrastructure",
            "Cybersecurity",
            "Project Management",
            "Vendor Management",
            "Networks and Systems",
        ),
    ),
)

EVIDENCE_SOURCES = ("cv", "screening", "assessment", "semantic", "interview")
EVIDENCE_MODES = ("required", "optional", "unused")
DEFAULT_EVIDENCE_POLICY = {
    "version": EVIDENCE_POLICY_VERSION,
    "sources": {
        "cv": "required",
        "screening": "optional",
        # Assessments are optional product evidence. Ranking stays CV-first unless an
        # approved job policy explicitly selects assessment supplementary use.
        "assessment": "unused",
        "semantic": "optional",
        "interview": "unused",
    },
}

# Required metadata before assessment may change Ranking ordering/score.
ASSESSMENT_SELECTION_REQUIRED_KEYS = (
    "battery_key",
    "assessment_version_id",
    "norm_version",
    "attempt_selection_rule",
    "approved_by_user_id",
    "approved_at",
    "policy_version",
)
# Soft components map to evidence sources for policy gating.
COMPONENT_SOURCE = {
    "skills_alignment": "cv",
    "experience_alignment": "cv",
    "education_cert_alignment": "cv",
    "assessment_evidence": "assessment",
    "semantic_alignment": "semantic",
}

CRITERION_TYPES = (
    "certification",
    "minimum_experience_years",
    "education",
    "language",
    "location",
    "work_arrangement",
    "work_authorization",
    "availability",
    "technical_skill",
)

HARD_RESULTS = ("met", "not_met", "unknown", "not_applicable")
ELIGIBILITY_BUCKETS = (
    "eligible",
    "requirement_not_met",
    "insufficient_information",
    "criteria_not_evaluated",
    "not_applicable",
)

# Soft score components (interview excluded initially per R2 contract).
SOFT_COMPONENT_WEIGHTS = {
    "skills_alignment": 30.0,
    "experience_alignment": 25.0,
    "education_cert_alignment": 15.0,
    "assessment_evidence": 15.0,
    "semantic_alignment": 15.0,
}
SOFT_SCORE_MAX = 100.0

SENSITIVE_DENYLIST_FIELDS = frozenset(
    {
        "civil_id",
        "civilid",
        "national_id",
        "nationality",
        "gender",
        "sex",
        "age",
        "date_of_birth",
        "dob",
        "birth_date",
        "photo",
        "personal_photo",
        "headshot",
        "religion",
        "sect",
        "marital_status",
        "marriage",
        "pregnancy",
        "family_status",
        "disability",
        "health",
        "medical",
        "address",
        "home_address",
        "residence",
        "socioeconomic",
        "salary_expectation_personal",  # keep job-side salary separate
    }
)

SENSITIVE_TEXT_PATTERNS = (
    re.compile(r"\bcivil\s*id\b", re.I),
    re.compile(r"\bnationalit(?:y|ies)\b", re.I),
    re.compile(r"\b(?:gender|male|female|non[\s-]?binary)\b", re.I),
    re.compile(r"\b(?:date of birth|d\.?o\.?b\.?|born on)\b", re.I),
    re.compile(r"\b(?:religion|sect|muslim|christian|hindu)\b", re.I),
    re.compile(r"\b(?:marital status|married|divorced|widow)\b", re.I),
    re.compile(r"\b(?:pregnan|disability|disabled)\b", re.I),
    re.compile(r"\b(?:home address|residential address)\b", re.I),
)

PAGE_DEFAULT = 50
PAGE_MAX = 200


class RankingError(Exception):
    def __init__(self, code: str, message: str = "", *, details: Any = None) -> None:
        super().__init__(message or code)
        self.code = code
        self.details = details


# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS job_ranking_criteria_sets (
  criteria_set_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  company_code text NOT NULL,
  position_code text NOT NULL,
  job_id text,
  version integer NOT NULL DEFAULT 1,
  status text NOT NULL DEFAULT 'draft',
  approved_by_user_id text,
  approved_at timestamptz,
  denylist_version text NOT NULL DEFAULT 'ranking-denylist-v1',
  scoring_config_version text NOT NULL DEFAULT 'ranking-soft-v2',
  evidence_policy jsonb NOT NULL DEFAULT '{}'::jsonb,
  metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (company_code, position_code, version)
);

CREATE TABLE IF NOT EXISTS job_ranking_criteria (
  criterion_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  criteria_set_id uuid NOT NULL REFERENCES job_ranking_criteria_sets(criteria_set_id) ON DELETE CASCADE,
  company_code text NOT NULL,
  position_code text NOT NULL,
  criterion_type text NOT NULL,
  label text NOT NULL,
  classification text NOT NULL DEFAULT 'hard',
  rule_json jsonb NOT NULL DEFAULT '{}'::jsonb,
  weight numeric NOT NULL DEFAULT 0,
  evidence_sources jsonb NOT NULL DEFAULT '[]'::jsonb,
  missing_behavior text NOT NULL DEFAULT 'unknown',
  active boolean NOT NULL DEFAULT true,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS ranking_runs (
  run_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  company_code text NOT NULL,
  position_code text NOT NULL,
  job_id text,
  job_version integer,
  criteria_set_id uuid,
  criteria_version integer,
  actor_user_id text,
  status text NOT NULL DEFAULT 'completed',
  pool_total integer NOT NULL DEFAULT 0,
  eligible_count integer NOT NULL DEFAULT 0,
  not_met_count integer NOT NULL DEFAULT 0,
  unknown_count integer NOT NULL DEFAULT 0,
  scored_count integer NOT NULL DEFAULT 0,
  request_hash text NOT NULL,
  provenance jsonb NOT NULL DEFAULT '{}'::jsonb,
  denylist_version text NOT NULL,
  scoring_config_version text NOT NULL,
  embedding_model text,
  reranker_model text,
  is_current boolean NOT NULL DEFAULT true,
  stale_reason text,
  stale_at timestamptz,
  error text,
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (company_code, position_code, request_hash)
);

CREATE TABLE IF NOT EXISTS ranking_run_items (
  item_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  run_id uuid NOT NULL REFERENCES ranking_runs(run_id) ON DELETE CASCADE,
  company_code text NOT NULL,
  position_code text NOT NULL,
  app_key text NOT NULL,
  person_id uuid,
  membership_id uuid,
  eligibility_bucket text NOT NULL,
  advisory_score numeric,
  component_scores jsonb NOT NULL DEFAULT '{}'::jsonb,
  requirement_results jsonb NOT NULL DEFAULT '[]'::jsonb,
  evidence jsonb NOT NULL DEFAULT '[]'::jsonb,
  missing_data jsonb NOT NULL DEFAULT '[]'::jsonb,
  evidence_coverage numeric,
  confidence text,
  explanation text,
  provenance jsonb NOT NULL DEFAULT '{}'::jsonb,
  pool_ordinal integer,
  soft_rank integer,
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (run_id, app_key)
);

CREATE TABLE IF NOT EXISTS ranking_recalculation_jobs (
  job_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  company_code text NOT NULL,
  position_code text NOT NULL,
  reason text NOT NULL,
  status text NOT NULL DEFAULT 'pending',
  attempts integer NOT NULL DEFAULT 0,
  last_error text,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS ranking_item_narratives (
  narrative_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  item_id uuid NOT NULL REFERENCES ranking_run_items(item_id) ON DELETE CASCADE,
  run_id uuid NOT NULL REFERENCES ranking_runs(run_id) ON DELETE CASCADE,
  company_code text NOT NULL,
  position_code text NOT NULL,
  app_key text NOT NULL,
  narrative_text text,
  model text NOT NULL DEFAULT 'gpt-5.6-terra',
  prompt_version text NOT NULL,
  evidence_hash text NOT NULL,
  locale text NOT NULL DEFAULT 'en',
  status text NOT NULL DEFAULT 'pending',
  error text,
  evidence_envelope jsonb NOT NULL DEFAULT '{}'::jsonb,
  provenance jsonb NOT NULL DEFAULT '{}'::jsonb,
  generated_at timestamptz,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (item_id, prompt_version, evidence_hash, locale)
);

CREATE INDEX IF NOT EXISTS idx_ranking_runs_job_current
  ON ranking_runs(company_code, position_code, is_current, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_ranking_run_items_run
  ON ranking_run_items(run_id, soft_rank NULLS LAST, pool_ordinal);
CREATE INDEX IF NOT EXISTS idx_job_ranking_criteria_sets_job
  ON job_ranking_criteria_sets(company_code, position_code, status, version DESC);
CREATE INDEX IF NOT EXISTS idx_ranking_item_narratives_item
  ON ranking_item_narratives(item_id, status, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_ranking_item_narratives_run
  ON ranking_item_narratives(run_id, app_key);
"""


def ensure_schema(cur: Any) -> None:
    _cv_evidence.ensure_schema(cur)
    cur.execute(SCHEMA_SQL)
    # Additive upgrades for existing deployments.
    cur.execute(
        """
        ALTER TABLE job_ranking_criteria_sets
        ADD COLUMN IF NOT EXISTS evidence_policy jsonb NOT NULL DEFAULT '{}'::jsonb
        """
    )


# ---------------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------------

def _now() -> datetime:
    return datetime.now(timezone.utc)


def json_safe(value: Any) -> Any:
    """Convert DB Decimals and nested payloads into JSON-serializable values."""
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, dict):
        return {str(key): json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_safe(item) for item in value]
    return value


def _json(orch: Any, value: Any) -> Any:
    factory = getattr(orch, "Json", None)
    safe = json_safe(value)
    return factory(safe) if callable(factory) else safe


def _row(value: Any) -> dict[str, Any]:
    if value is None:
        return {}
    if isinstance(value, dict):
        return dict(value)
    try:
        return dict(value)
    except Exception:
        return {}


def stable_hash(payload: Any) -> str:
    blob = json.dumps(json_safe(payload), sort_keys=True, default=str, separators=(",", ":"))
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def normalize_text(value: str | None) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip().lower())


def validate_company(company_code: str | None) -> str:
    code = str(company_code or "").strip().upper()
    if not code:
        raise RankingError("tenant_scope_required", "company_code is required")
    return code


def validate_position(position_code: str | None) -> str:
    code = str(position_code or "").strip().upper()
    if not code:
        raise RankingError("job_required", "position_code is required for ranking")
    return code


_SAFE_ASSESSMENT_TOKEN = re.compile(r"^[A-Za-z0-9_.:-]{1,128}$")


def _sql_assessment_token(value: str, *, field: str) -> str:
    text = str(value or "").strip()
    if not _SAFE_ASSESSMENT_TOKEN.fullmatch(text):
        raise RankingError("invalid_assessment_selection", f"{field}={text}")
    return text


def normalize_evidence_policy(value: Any = None) -> dict[str, Any]:
    """Return a versioned evidence policy with required/optional/unused sources."""
    raw = value if isinstance(value, dict) else {}
    sources_in = raw.get("sources") if isinstance(raw.get("sources"), dict) else {}
    sources: dict[str, str] = {}
    for source in EVIDENCE_SOURCES:
        mode = str(sources_in.get(source) or DEFAULT_EVIDENCE_POLICY["sources"][source]).strip().lower()
        if mode not in EVIDENCE_MODES:
            raise RankingError("invalid_evidence_mode", f"{source}={mode}")
        sources[source] = mode
    # Interview stays unused until a separately approved scoring component exists.
    if sources.get("interview") == "required":
        raise RankingError("interview_scoring_unavailable", "Interview cannot be required until scoring is approved")
    if sources.get("interview") not in {"unused", "optional"}:
        sources["interview"] = "unused"
    out: dict[str, Any] = {
        "version": EVIDENCE_POLICY_VERSION,
        "sources": sources,
    }
    selection = assessment_selection_from_metadata(raw)
    if selection:
        out["assessment_selection"] = selection
    return out


def evidence_policy_from_criteria_set(criteria_set: dict[str, Any] | None) -> dict[str, Any]:
    raw = None
    metadata: dict[str, Any] = {}
    if isinstance(criteria_set, dict):
        raw = criteria_set.get("evidence_policy")
        metadata = criteria_set.get("metadata") if isinstance(criteria_set.get("metadata"), dict) else {}
        if not raw:
            raw = metadata.get("evidence_policy")
            # Legacy single-flag mapping: unapproved assessment contribution → unused.
            if not raw and metadata.get("assessment_contribution_approved") is False:
                legacy = dict(DEFAULT_EVIDENCE_POLICY["sources"])
                legacy["assessment"] = "unused"
                raw = {"version": EVIDENCE_POLICY_VERSION, "sources": legacy}
    policy = normalize_evidence_policy(raw or DEFAULT_EVIDENCE_POLICY)
    # Prefer explicit selection stored on criteria metadata when policy blob omits it.
    if not policy.get("assessment_selection"):
        selection = assessment_selection_from_metadata(metadata)
        if selection:
            policy = {**policy, "assessment_selection": selection}
    return policy


def source_mode(policy: dict[str, Any] | None, source: str) -> str:
    policy = normalize_evidence_policy(policy)
    return str((policy.get("sources") or {}).get(source) or "unused")


def assessment_selection_from_metadata(metadata: dict[str, Any] | None) -> dict[str, Any] | None:
    """Return explicit assessment selection when complete; otherwise None (fail closed)."""
    meta = metadata if isinstance(metadata, dict) else {}
    raw = meta.get("assessment_selection") if isinstance(meta.get("assessment_selection"), dict) else None
    if raw is None and all(meta.get(key) for key in ASSESSMENT_SELECTION_REQUIRED_KEYS):
        raw = meta
    if not isinstance(raw, dict):
        return None
    selection = {
        key: str(raw.get(key) or "").strip()
        for key in ASSESSMENT_SELECTION_REQUIRED_KEYS
    }
    if not all(selection.values()):
        return None
    rule = selection["attempt_selection_rule"]
    if rule not in {"selected_attempt_id", "latest_matching_battery_version"}:
        return None
    if rule == "selected_attempt_id":
        attempt_id = str(raw.get("selected_attempt_id") or "").strip()
        if not attempt_id:
            return None
        selection["selected_attempt_id"] = attempt_id
    return selection


def resolve_assessments_module_enabled(
    orch: Any | None,
    company_code: str,
    explicit: bool | None = None,
) -> bool:
    """Fail closed: assessment Ranking is off unless the module is explicitly on."""
    if explicit is not None:
        return bool(explicit)
    checker = getattr(orch, "company_has_module", None) if orch is not None else None
    if callable(checker):
        try:
            return bool(checker(company_code, "assessments"))
        except Exception:
            return False
    return False


def effective_assessment_mode(
    policy: dict[str, Any] | None,
    *,
    assessments_module_enabled: bool = False,
    criteria_metadata: dict[str, Any] | None = None,
) -> tuple[str, dict[str, Any] | None]:
    """Resolve assessment Ranking mode under module + explicit-selection contract.

    Returns (mode, selection). Mode is unused unless the tenant module is on and an
    approved policy both enables assessment and names the exact selection fields.
    """
    if not assessments_module_enabled:
        return "unused", None
    normalized = normalize_evidence_policy(policy)
    mode = source_mode(normalized, "assessment")
    if mode == "unused":
        return "unused", None
    selection = (
        assessment_selection_from_metadata(normalized)
        or assessment_selection_from_metadata(criteria_metadata)
    )
    if not selection:
        # Fail closed: optional/required without explicit selection must not change Ranking.
        return "unused", None
    return mode, selection


def assessment_attempt_matches_selection(row: dict[str, Any], selection: dict[str, Any]) -> bool:
    """True when the pool row's assessment attempt is the policy-selected evidence."""
    if not selection:
        return False
    rule = selection.get("attempt_selection_rule")
    if rule == "selected_attempt_id":
        return str(row.get("assessment_attempt_id") or "") == selection.get("selected_attempt_id")
    if rule == "latest_matching_battery_version":
        battery = str(row.get("assessment_battery_key") or "").strip()
        version_id = str(row.get("assessment_version_id") or "").strip()
        norm = str(row.get("assessment_norm_version") or "").strip()
        return (
            battery == selection.get("battery_key")
            and version_id == selection.get("assessment_version_id")
            and norm == selection.get("norm_version")
            and str(row.get("assessment_status") or "").lower() == "completed"
            and row.get("assessment_percent") is not None
        )
    return False


def assessment_pool_lateral_sql(selection: dict[str, Any] | None) -> str:
    """SQL lateral for Ranking pool assessment evidence.

    Unused/module-off/incomplete selection: do not join assessment_attempts.
    With an explicit attempt rule: select only the policy-matching attempt.
    """
    if not selection:
        return """
                LEFT JOIN LATERAL (
                  SELECT NULL::text AS assessment_status,
                         NULL::numeric AS assessment_percent,
                         NULL::uuid AS assessment_attempt_id,
                         NULL::text AS assessment_position_code,
                         NULL::text AS assessment_battery_key,
                         NULL::uuid AS assessment_version_id,
                         NULL::text AS assessment_norm_version
                ) latest_assessment ON TRUE
        """
    rule = selection.get("attempt_selection_rule")
    battery = _sql_assessment_token(str(selection.get("battery_key") or ""), field="battery_key")
    version_id = _sql_assessment_token(
        str(selection.get("assessment_version_id") or ""),
        field="assessment_version_id",
    )
    norm = _sql_assessment_token(str(selection.get("norm_version") or ""), field="norm_version")
    if rule == "selected_attempt_id":
        attempt_id = _sql_assessment_token(
            str(selection.get("selected_attempt_id") or ""),
            field="selected_attempt_id",
        )
        return f"""
                LEFT JOIN LATERAL (
                  SELECT aa.status AS assessment_status,
                         s.percent AS assessment_percent,
                         aa.attempt_id AS assessment_attempt_id,
                         aa.position_code AS assessment_position_code,
                         aa.battery_key AS assessment_battery_key,
                         aa.assessment_version_id AS assessment_version_id,
                         s.norm_version AS assessment_norm_version
                  FROM assessment_attempts aa
                  LEFT JOIN assessment_scores s ON s.attempt_id=aa.attempt_id
                  WHERE aa.company_code=a.company_code AND aa.app_key=a.app_key
                    AND aa.attempt_id='{attempt_id}'::uuid
                    AND aa.battery_key='{battery}'
                    AND aa.assessment_version_id::text='{version_id}'
                    AND COALESCE(s.norm_version, '')='{norm}'
                  LIMIT 1
                ) latest_assessment ON TRUE
        """
    # latest_matching_battery_version — never falls back to an unrelated latest attempt.
    return f"""
                LEFT JOIN LATERAL (
                  SELECT aa.status AS assessment_status,
                         s.percent AS assessment_percent,
                         aa.attempt_id AS assessment_attempt_id,
                         aa.position_code AS assessment_position_code,
                         aa.battery_key AS assessment_battery_key,
                         aa.assessment_version_id AS assessment_version_id,
                         s.norm_version AS assessment_norm_version
                  FROM assessment_attempts aa
                  LEFT JOIN assessment_scores s ON s.attempt_id=aa.attempt_id
                  WHERE aa.company_code=a.company_code AND aa.app_key=a.app_key
                    AND aa.battery_key='{battery}'
                    AND aa.assessment_version_id::text='{version_id}'
                    AND aa.status='completed'
                    AND s.percent IS NOT NULL
                    AND COALESCE(s.norm_version, '')='{norm}'
                  ORDER BY aa.completed_at DESC NULLS LAST, aa.updated_at DESC, aa.created_at DESC
                  LIMIT 1
                ) latest_assessment ON TRUE
    """


def application_cv_readiness(row: dict[str, Any]) -> dict[str, Any]:
    return _cv_evidence.readiness_from_row(row)


def application_has_usable_cv(row: dict[str, Any]) -> bool:
    """Required-CV gate: only the current canonical evidence version is usable."""
    return bool(application_cv_readiness(row).get("ready"))


# ---------------------------------------------------------------------------
# R0 sensitive denylist
# ---------------------------------------------------------------------------

def is_denied_field(name: str) -> bool:
    key = normalize_text(name).replace("-", "_").replace(" ", "_")
    if key in SENSITIVE_DENYLIST_FIELDS:
        return True
    return any(token in key for token in SENSITIVE_DENYLIST_FIELDS)


def scrub_sensitive_text(text: str | None) -> str:
    value = str(text or "")
    for pattern in SENSITIVE_TEXT_PATTERNS:
        value = pattern.sub("[redacted]", value)
    return value


def sanitize_ranking_payload(value: Any, *, depth: int = 0) -> Any:
    """Recursively drop denylisted keys and scrub sensitive free text."""
    if depth > 8:
        return None
    if isinstance(value, dict):
        out: dict[str, Any] = {}
        for key, item in value.items():
            if is_denied_field(str(key)):
                continue
            # Names are allowed for display payloads but not for scoring features.
            cleaned = sanitize_ranking_payload(item, depth=depth + 1)
            if cleaned is not None:
                out[str(key)] = cleaned
        return out
    if isinstance(value, list):
        return [sanitize_ranking_payload(item, depth=depth + 1) for item in value][:100]
    if isinstance(value, str):
        return scrub_sensitive_text(value)
    return value


def ranking_feature_text(*, semantic_content: str | None, structured: dict[str, Any] | None) -> str:
    """Build scoring text without names or denylisted fields."""
    safe_structured = sanitize_ranking_payload(structured or {})
    if isinstance(safe_structured, dict):
        for key in ("name", "candidate_name", "full_name", "display_name"):
            safe_structured.pop(key, None)
    parts = [
        scrub_sensitive_text(semantic_content or ""),
        json.dumps(safe_structured, ensure_ascii=False, default=str) if safe_structured else "",
    ]
    return normalize_text(" ".join(parts))


def assert_no_sensitive_leak(payload: Any, *, context: str) -> None:
    serialized = json.dumps(payload, ensure_ascii=False, default=str)
    lowered = serialized.lower()
    for field in ("civil_id", "date_of_birth", "marital_status", "religion", "personal_photo"):
        if f'"{field}"' in lowered or f"'{field}'" in lowered:
            raise RankingError("sensitive_field_leak", f"{context} contains denied field {field}")


# ---------------------------------------------------------------------------
# Job + criteria
# ---------------------------------------------------------------------------

def load_job(orch: Any, *, company_code: str, position_code: str) -> dict[str, Any]:
    company = validate_company(company_code)
    position = validate_position(position_code)
    with orch.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT position_code, title, title_en, title_ar, job_id, version, status,
                       location, work_arrangement, employment_type,
                       requirements_en, requirements_ar, updated_at
                FROM positions
                WHERE company_code=%s AND upper(position_code)=%s
                LIMIT 1
                """,
                (company, position),
            )
            row = cur.fetchone()
    if not row:
        raise RankingError("job_not_found", f"No job {position} for tenant {company}")
    job = _row(row)
    # Compatibility alias used by soft scoring.
    job["requirements"] = job.get("requirements_en") or []
    return job


def automatic_role_profile(job: dict[str, Any]) -> dict[str, Any]:
    """Build a soft, explainable comparison profile from employer job content.

    Explicit requirements win. Title defaults are a fallback and are always
    marked advisory; they never become hard eligibility gates.
    """
    metadata = job.get("metadata") if isinstance(job.get("metadata"), dict) else {}
    requirement_values: list[str] = []
    for source in (
        job.get("requirements_en"),
        job.get("requirements_ar"),
        job.get("requirements"),
        metadata.get("requirements"),
    ):
        values = source if isinstance(source, list) else [source] if source else []
        for value in values:
            text = re.sub(r"\s+", " ", str(value or "")).strip(" \t,;•-")
            if text and text.lower() not in {item.lower() for item in requirement_values}:
                requirement_values.append(text)

    title = re.sub(
        r"[_\-/]+",
        " ",
        str(job.get("title") or job.get("title_en") or job.get("position_code") or ""),
    )
    normalized_title = normalize_text(title)
    source = "job_requirements"
    labels = requirement_values[:16]
    if not labels:
        source = "job_title_profile"
        for aliases, defaults in _ROLE_PROFILE_DEFAULTS:
            if any(normalize_text(alias) == normalized_title or normalize_text(alias) in normalized_title for alias in aliases):
                labels = list(defaults)
                break
    if not labels:
        source = "job_title"
        labels = [title.strip()] if title.strip() else []

    criteria: list[dict[str, Any]] = []
    for label in labels:
        lower = normalize_text(label)
        if re.search(r"\b\d+(?:\.\d+)?\s*\+?\s*(?:years?|yrs?|سنوات|سنة)\b", lower):
            criterion_type = "minimum_experience_years"
        elif any(token in lower for token in ("bachelor", "master", "degree", "diploma", "بكالوريوس", "ماجستير")):
            criterion_type = "education"
        elif any(token in lower for token in ("english", "arabic", "language", "اللغة", "العربية", "الإنجليزية")):
            criterion_type = "language"
        elif any(token in lower for token in ("certificate", "certification", "certified", "شهادة")):
            criterion_type = "certification"
        else:
            criterion_type = "technical_skill"
        criteria.append(
            {
                "criterion_type": criterion_type,
                "label": label,
                "classification": "soft",
                "rule_json": {"value": label},
                "weight": 1.0,
                "evidence_sources": ["application_cv_facts", "cv_extraction"],
                "missing_behavior": "unknown",
                "active": True,
            }
        )
    return {
        "version": AUTOMATIC_ROLE_PROFILE_VERSION,
        "source": source,
        "label": (
            "Published job requirements"
            if source == "job_requirements"
            else "Job title profile"
        ),
        "criteria": criteria,
        "criteria_count": len(criteria),
        "advisory": True,
        "profile_hash": stable_hash({"source": source, "title": normalized_title, "labels": labels}),
    }


def latest_approved_criteria_set(orch: Any, *, company_code: str, position_code: str) -> dict[str, Any] | None:
    company = validate_company(company_code)
    position = validate_position(position_code)
    with orch.db_connect() as conn:
        with conn.cursor() as cur:
            ensure_schema(cur)
            cur.execute(
                """
                SELECT *
                FROM job_ranking_criteria_sets
                WHERE company_code=%s AND upper(position_code)=%s AND status='approved'
                ORDER BY version DESC
                LIMIT 1
                """,
                (company, position),
            )
            row = cur.fetchone()
            if not row:
                return None
            criteria_set = _row(row)
            cur.execute(
                """
                SELECT *
                FROM job_ranking_criteria
                WHERE criteria_set_id=%s AND active=true
                ORDER BY created_at ASC
                """,
                (criteria_set["criteria_set_id"],),
            )
            criteria_set["criteria"] = [_row(r) for r in cur.fetchall()]
            return criteria_set


def approve_criteria_set(
    orch: Any,
    *,
    company_code: str,
    position_code: str,
    criteria: list[dict[str, Any]],
    actor_user_id: str,
    job_id: str | None = None,
    assessment_contribution_approved: bool | None = None,
    evidence_policy: dict[str, Any] | None = None,
    expected_version: int | None = None,
    stale_reason: str = "criteria_version_changed",
) -> dict[str, Any]:
    company = validate_company(company_code)
    position = validate_position(position_code)
    if not actor_user_id:
        raise RankingError("approval_actor_required")
    cleaned: list[dict[str, Any]] = []
    for item in criteria:
        ctype = str(item.get("criterion_type") or "").strip()
        if ctype not in CRITERION_TYPES:
            raise RankingError("unsupported_criterion_type", ctype)
        classification = str(item.get("classification") or "hard").strip().lower()
        if classification not in {"hard", "soft"}:
            raise RankingError("invalid_classification", classification)
        missing_behavior = str(item.get("missing_behavior") or "unknown").strip().lower()
        if missing_behavior not in {"unknown", "not_met"}:
            raise RankingError("invalid_missing_behavior", missing_behavior)
        cleaned.append(
            {
                "criterion_type": ctype,
                "label": str(item.get("label") or ctype),
                "classification": classification,
                "rule_json": sanitize_ranking_payload(item.get("rule_json") or {}),
                "weight": float(item.get("weight") or 0),
                "evidence_sources": list(item.get("evidence_sources") or ["structured_application", "cv_extraction"]),
                "missing_behavior": missing_behavior,
            }
        )
    policy = normalize_evidence_policy(evidence_policy or DEFAULT_EVIDENCE_POLICY)
    # Legacy callers that pass assessment_contribution_approved=False without an
    # explicit evidence_policy keep assessment unused for that criteria version.
    if evidence_policy is None and assessment_contribution_approved is False:
        sources = dict(policy["sources"])
        sources["assessment"] = "unused"
        policy = normalize_evidence_policy({"version": EVIDENCE_POLICY_VERSION, "sources": sources})
    selection_raw = None
    if isinstance(evidence_policy, dict) and isinstance(evidence_policy.get("assessment_selection"), dict):
        selection_raw = evidence_policy.get("assessment_selection")
    assessment_mode_requested = source_mode(policy, "assessment")
    selection = None
    if assessment_mode_requested != "unused":
        proposed_meta = {
            "assessment_selection": {
                **(selection_raw or {}),
                "approved_by_user_id": actor_user_id,
                "approved_at": _now().isoformat(),
                "policy_version": str((selection_raw or {}).get("policy_version") or EVIDENCE_POLICY_VERSION),
            }
        }
        selection = assessment_selection_from_metadata(proposed_meta)
        if not selection:
            # Contained fail-closed: mode without explicit selection cannot change Ranking.
            sources = dict(policy["sources"])
            sources["assessment"] = "unused"
            policy = normalize_evidence_policy({"version": EVIDENCE_POLICY_VERSION, "sources": sources})
        else:
            policy = {**policy, "assessment_selection": selection}
    # Derive legacy flag from effective contribution eligibility.
    if assessment_contribution_approved is None:
        assessment_contribution_approved = selection is not None
    metadata = {
        "assessment_contribution_approved": bool(assessment_contribution_approved and selection),
        "assessment_contribution_approved_by": actor_user_id if selection else None,
        "assessment_contribution_approved_at": _now().isoformat() if selection else None,
        "evidence_policy": policy,
        "evidence_policy_version": EVIDENCE_POLICY_VERSION,
        "assessment_selection": selection,
    }
    with orch.db_connect() as conn:
        with conn.cursor() as cur:
            ensure_schema(cur)
            cur.execute(
                """
                SELECT COALESCE(MAX(version), 0) AS version
                FROM job_ranking_criteria_sets
                WHERE company_code=%s AND upper(position_code)=%s
                """,
                (company, position),
            )
            current_version = int((_row(cur.fetchone()).get("version") or 0))
            if expected_version is not None and int(expected_version) != current_version:
                raise RankingError(
                    "criteria_version_conflict",
                    f"expected={expected_version} current={current_version}",
                )
            next_version = current_version + 1
            criteria_set_id = str(uuid.uuid4())
            cur.execute(
                """
                INSERT INTO job_ranking_criteria_sets(
                  criteria_set_id, company_code, position_code, job_id, version, status,
                  approved_by_user_id, approved_at, denylist_version, scoring_config_version,
                  evidence_policy, metadata
                ) VALUES (%s,%s,%s,%s,%s,'approved',%s,now(),%s,%s,%s,%s)
                """,
                (
                    criteria_set_id,
                    company,
                    position,
                    job_id,
                    next_version,
                    actor_user_id,
                    DENYLIST_VERSION,
                    SCORING_CONFIG_VERSION,
                    _json(orch, policy),
                    _json(orch, metadata),
                ),
            )
            for item in cleaned:
                cur.execute(
                    """
                    INSERT INTO job_ranking_criteria(
                      criteria_set_id, company_code, position_code, criterion_type, label,
                      classification, rule_json, weight, evidence_sources, missing_behavior
                    ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                    """,
                    (
                        criteria_set_id,
                        company,
                        position,
                        item["criterion_type"],
                        item["label"],
                        item["classification"],
                        _json(orch, item["rule_json"]),
                        item["weight"],
                        _json(orch, item["evidence_sources"]),
                        item["missing_behavior"],
                    ),
                )
        conn.commit()
    mark_runs_stale(orch, company_code=company, position_code=position, reason=stale_reason)
    return latest_approved_criteria_set(orch, company_code=company, position_code=position) or {}


def get_job_evidence_policy(orch: Any, *, company_code: str, position_code: str) -> dict[str, Any]:
    """Tenant-scoped evidence policy for HR editor / Ranking blockers."""
    company = validate_company(company_code)
    position = validate_position(position_code)
    criteria_set = latest_approved_criteria_set(orch, company_code=company, position_code=position)
    policy = evidence_policy_from_criteria_set(criteria_set)
    criteria_meta = (criteria_set or {}).get("metadata") if isinstance((criteria_set or {}).get("metadata"), dict) else {}
    module_on = resolve_assessments_module_enabled(orch, company)
    effective_mode, selection = effective_assessment_mode(
        policy,
        assessments_module_enabled=module_on,
        criteria_metadata=criteria_meta,
    )
    return {
        "ok": True,
        "company_code": company,
        "position_code": position,
        "criteria_set_id": (criteria_set or {}).get("criteria_set_id"),
        "criteria_version": (criteria_set or {}).get("version"),
        "scoring_config_version": (criteria_set or {}).get("scoring_config_version") or SCORING_CONFIG_VERSION,
        "evidence_policy": policy,
        "evidence_policy_version": EVIDENCE_POLICY_VERSION,
        "default_policy": DEFAULT_EVIDENCE_POLICY,
        "sources": list(EVIDENCE_SOURCES),
        "modes": list(EVIDENCE_MODES),
        "has_approved_criteria": bool(criteria_set),
        "assessments_module_enabled": module_on,
        "effective_assessment_mode": effective_mode,
        "assessment_selection": selection,
    }


def approve_job_evidence_policy(
    orch: Any,
    *,
    company_code: str,
    position_code: str,
    evidence_policy: dict[str, Any],
    actor_user_id: str,
    expected_version: int | None = None,
    criteria: list[dict[str, Any]] | None = None,
    job_id: str | None = None,
) -> dict[str, Any]:
    """Approve a new criteria-set version that only changes evidence policy (or also criteria)."""
    existing = latest_approved_criteria_set(orch, company_code=company_code, position_code=position_code)
    if criteria is None:
        criteria = list((existing or {}).get("criteria") or [])
    approved = approve_criteria_set(
        orch,
        company_code=company_code,
        position_code=position_code,
        criteria=criteria,
        actor_user_id=actor_user_id,
        job_id=job_id or (existing or {}).get("job_id"),
        evidence_policy=evidence_policy,
        expected_version=expected_version,
        stale_reason="evidence_policy_changed",
    )
    return {
        "ok": True,
        "criteria_set": approved,
        "evidence_policy": evidence_policy_from_criteria_set(approved),
        "stale_reason": "evidence_policy_changed",
    }


def backfill_default_evidence_policy(
    orch: Any,
    *,
    company_code: str | None = None,
    actor_user_id: str = "migration:ranking-evidence-policy-v1",
    dry_run: bool = False,
) -> dict[str, Any]:
    """Additive backfill: stamp default policy onto jobs missing one; mark current runs stale."""
    touched: list[dict[str, Any]] = []
    with orch.db_connect() as conn:
        with conn.cursor() as cur:
            ensure_schema(cur)
            if company_code:
                cur.execute(
                    """
                    SELECT DISTINCT company_code, upper(position_code) AS position_code
                    FROM job_ranking_criteria_sets
                    WHERE status='approved' AND company_code=%s
                    """,
                    (validate_company(company_code),),
                )
            else:
                cur.execute(
                    """
                    SELECT DISTINCT company_code, upper(position_code) AS position_code
                    FROM job_ranking_criteria_sets
                    WHERE status='approved'
                    """
                )
            jobs = [_row(r) for r in cur.fetchall()]
    for job in jobs:
        company = str(job.get("company_code") or "")
        position = str(job.get("position_code") or "")
        current = latest_approved_criteria_set(orch, company_code=company, position_code=position)
        if not current:
            continue
        existing_policy = current.get("evidence_policy")
        if isinstance(existing_policy, dict) and existing_policy.get("version") == EVIDENCE_POLICY_VERSION:
            continue
        meta = current.get("metadata") if isinstance(current.get("metadata"), dict) else {}
        if isinstance(meta.get("evidence_policy"), dict) and meta["evidence_policy"].get("version") == EVIDENCE_POLICY_VERSION:
            continue
        entry = {"company_code": company, "position_code": position, "from_version": current.get("version")}
        if dry_run:
            entry["action"] = "would_approve_default_policy"
            touched.append(entry)
            continue
        approved = approve_criteria_set(
            orch,
            company_code=company,
            position_code=position,
            criteria=list(current.get("criteria") or []),
            actor_user_id=actor_user_id,
            job_id=current.get("job_id"),
            evidence_policy=DEFAULT_EVIDENCE_POLICY,
            expected_version=int(current.get("version") or 0),
            stale_reason="evidence_policy_backfill",
        )
        entry["action"] = "approved_default_policy"
        entry["to_version"] = approved.get("version")
        touched.append(entry)
    return {
        "ok": True,
        "dry_run": dry_run,
        "policy_version": EVIDENCE_POLICY_VERSION,
        "touched_count": len(touched),
        "touched": touched,
    }


# ---------------------------------------------------------------------------
# R0 complete SQL pool
# ---------------------------------------------------------------------------

def _production_predicate(orch: Any) -> str:
    fn = getattr(orch, "production_application_predicate", None)
    if callable(fn):
        return fn("a")
    return "TRUE"


def _reviewable_predicate(orch: Any) -> str:
    fn = getattr(orch, "reviewable_application_predicate", None)
    if callable(fn):
        return fn("a")
    return "TRUE"


def load_job_application_pool(
    orch: Any,
    *,
    company_code: str,
    position_code: str,
    cursor: str | None = None,
    limit: int = PAGE_DEFAULT,
    include_terminal: bool = False,
    visibility_sql: str | None = None,
    visibility_params: list[Any] | None = None,
    assessment_selection: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """ranking.pool.matching — reviewable CV + lifecycle + optional visibility."""
    import ranking_queue_contract as _rqc

    company = validate_company(company_code)
    position = validate_position(position_code)
    page_size = max(1, min(int(limit or PAGE_DEFAULT), PAGE_MAX))
    where = [
        "a.company_code=%s",
        "(upper(a.position_code)=%s OR upper(coalesce(a.position_title,''))=%s)",
        _reviewable_predicate(orch),
    ]
    params: list[Any] = [company, position, position.replace("_", " ")]
    if not include_terminal:
        where.append(_rqc.matching_lifecycle_predicate("a"))
    vis_sql = str(visibility_sql or "").strip()
    if vis_sql:
        where.append(f"({vis_sql})")
        params.extend(list(visibility_params or []))
    if cursor:
        where.append("(a.ingested_at, a.app_key) < (%s::timestamptz, %s)")
        # cursor format: iso|app_key
        try:
            ts, app_key = cursor.split("|", 1)
            params.extend([ts, app_key])
        except ValueError as exc:
            raise RankingError("invalid_cursor", str(exc)) from exc
    where_sql = " AND ".join(where)
    assessment_lateral = assessment_pool_lateral_sql(assessment_selection)
    with orch.db_connect() as conn:
        with conn.cursor() as cur:
            count_where = [
                "a.company_code=%s",
                "(upper(a.position_code)=%s OR upper(coalesce(a.position_title,''))=%s)",
                _reviewable_predicate(orch),
            ]
            count_params: list[Any] = [company, position, position.replace("_", " ")]
            if not include_terminal:
                count_where.append(_rqc.matching_lifecycle_predicate("a"))
            if vis_sql:
                count_where.append(f"({vis_sql})")
                count_params.extend(list(visibility_params or []))
            cur.execute(f"SELECT count(*) AS n FROM applications a WHERE {' AND '.join(count_where)}", count_params)
            total = int(_row(cur.fetchone()).get("n") or 0)
            cur.execute(
                f"""
                SELECT a.app_key, a.company_code, a.phone, a.position_code, a.position_title, a.status,
                       a.cv_received, a.person_id, a.membership_id, a.ingested_at, a.updated_at, a.raw_json,
                       c.name AS candidate_name, c.email AS candidate_email, c.profile AS candidate_profile,
                       c.raw_json AS candidate_raw_json, c.person_id AS candidate_person_id,
                       sd.content AS semantic_content, sd.content_hash AS semantic_content_hash,
                       sd.model AS semantic_model,
                       cve.file_id AS cv_file_id, cve.updated_at AS cv_file_updated_at,
                       cve.evidence_id AS cv_evidence_id,
                       cve.status AS cv_evidence_status,
                       cve.failure_reason AS cv_evidence_failure_reason,
                       cve.file_id AS cv_evidence_file_id,
                       cve.source_content_sha256 AS cv_evidence_source_sha256,
                       cve.extraction_finalization_id AS cv_extraction_finalization_id,
                       cve.extraction_quality_ok AS cv_extraction_quality_ok,
                       cve.extracted_text_hash AS cv_extracted_text_hash,
                       cve.semantic_content_hash AS cv_evidence_semantic_content_hash,
                       cve.embedding_status AS cv_evidence_embedding_status,
                       cve.contract_version AS cv_evidence_contract_version,
                       cvf.facts_id AS cv_facts_id,
                       cvf.status AS cv_facts_status,
                       cvf.contract_version AS cv_facts_contract_version,
                       cvf.extractor_version AS cv_facts_extractor_version,
                       cvf.facts_hash AS cv_facts_hash,
                       cvf.facts AS application_cv_facts,
                       xr.run_id AS cv_extraction_run_id, xr.stage AS cv_extraction_stage,
                       latest_assessment.assessment_status, latest_assessment.assessment_percent,
                       latest_assessment.assessment_attempt_id, latest_assessment.assessment_position_code,
                       latest_assessment.assessment_battery_key, latest_assessment.assessment_version_id,
                       latest_assessment.assessment_norm_version
                FROM applications a
                LEFT JOIN candidates c ON c.phone=a.phone
                LEFT JOIN LATERAL (
                  SELECT content, content_hash, model
                  FROM semantic_documents
                  WHERE company_code=a.company_code
                    AND entity_type='application'
                    AND entity_key=a.app_key
                  ORDER BY
                    CASE WHEN semantic_id=('application:' || a.app_key || ':cv') THEN 0 ELSE 1 END,
                    updated_at DESC NULLS LAST
                  LIMIT 1
                ) sd ON TRUE
                LEFT JOIN LATERAL (
                  SELECT *
                  FROM application_cv_evidence_materializations
                  WHERE company_code=a.company_code
                    AND app_key=a.app_key
                    AND is_current=true
                  ORDER BY updated_at DESC NULLS LAST
                  LIMIT 1
                ) cve ON TRUE
                LEFT JOIN LATERAL (
                  SELECT *
                  FROM application_cv_fact_snapshots
                  WHERE company_code=a.company_code
                    AND app_key=a.app_key
                    AND is_current=true
                    AND (cve.evidence_id IS NULL OR evidence_id=cve.evidence_id)
                  ORDER BY updated_at DESC NULLS LAST
                  LIMIT 1
                ) cvf ON TRUE
                LEFT JOIN LATERAL (
                  SELECT run_id, stage
                  FROM cv_extraction_runs
                  WHERE company_code=a.company_code AND app_key=a.app_key
                  ORDER BY created_at DESC NULLS LAST
                  LIMIT 1
                ) xr ON TRUE
                {assessment_lateral}
                WHERE {where_sql}
                ORDER BY a.ingested_at DESC NULLS LAST, a.app_key DESC
                LIMIT %s
                """,
                [*params, page_size],
            )
            rows = [_row(r) for r in cur.fetchall()]
    next_cursor = None
    if rows:
        last = rows[-1]
        ingested = last.get("ingested_at")
        if ingested is not None:
            next_cursor = f"{ingested.isoformat() if hasattr(ingested, 'isoformat') else ingested}|{last.get('app_key')}"
    return {
        "company_code": company,
        "position_code": position,
        "pool_total": total,
        "page_size": page_size,
        "next_cursor": next_cursor,
        "applications": rows,
        "authority": "ranking.pool.matching",
        "denylist_version": DENYLIST_VERSION,
        "scope": "detail_visibility" if vis_sql else "company",
    }


def load_complete_job_pool(
    orch: Any,
    *,
    company_code: str,
    position_code: str,
    visibility_sql: str | None = None,
    visibility_params: list[Any] | None = None,
    assessment_selection: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Load the full authoritative matching pool (no semantic truncation)."""
    items: list[dict[str, Any]] = []
    cursor = None
    while True:
        page = load_job_application_pool(
            orch,
            company_code=company_code,
            position_code=position_code,
            cursor=cursor,
            limit=PAGE_MAX,
            visibility_sql=visibility_sql,
            visibility_params=visibility_params,
            assessment_selection=assessment_selection,
        )
        batch = page.get("applications") or []
        items.extend(batch)
        cursor = page.get("next_cursor")
        if not cursor or not batch:
            break
        if len(items) >= int(page.get("pool_total") or len(items)):
            break
    return items


# ---------------------------------------------------------------------------
# R1 deterministic eligibility
# ---------------------------------------------------------------------------

def _rule_value(rule: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        if key in rule and rule[key] not in (None, ""):
            return rule[key]
    return None


def _structured_cv_fields(row: dict[str, Any]) -> dict[str, Any]:
    facts = row.get("application_cv_facts") if isinstance(row.get("application_cv_facts"), dict) else None
    facts_state = _cv_facts.readiness_from_row(row)
    if facts and facts_state.get("facts_id"):
        # Application/document facts are the sole authority whenever a current
        # snapshot exists. A review status means uncertainty, never permission
        # to fall back to candidate-global fields.
        return sanitize_ranking_payload(_cv_facts.ranking_fields(facts))
    raw = row.get("raw_json") if isinstance(row.get("raw_json"), dict) else {}
    cv = raw.get("cv") if isinstance(raw.get("cv"), dict) else {}
    extracted = cv.get("extracted") if isinstance(cv.get("extracted"), dict) else {}
    profile = row.get("candidate_profile") if isinstance(row.get("candidate_profile"), dict) else {}
    # Compatibility only while facts are being backfilled. Presentation must
    # treat this as unscoped/unverified and may not make CV-absence claims.
    return sanitize_ranking_payload({
        **profile,
        **extracted,
        **cv,
        "cv_facts_status": str(row.get("cv_facts_status") or "missing"),
        "cv_facts_contract_version": row.get("cv_facts_contract_version"),
        "legacy_candidate_profile_fallback": True,
    })


def _years_from_text(text: str) -> float | None:
    match = re.search(r"(\d+(?:\.\d+)?)\s*\+?\s*(?:years?|yrs?)", text, re.I)
    if not match:
        return None
    try:
        return float(match.group(1))
    except Exception:
        return None


def evaluate_hard_criterion(criterion: dict[str, Any], row: dict[str, Any]) -> dict[str, Any]:
    ctype = str(criterion.get("criterion_type") or "")
    rule = criterion.get("rule_json") if isinstance(criterion.get("rule_json"), dict) else {}
    missing_behavior = str(criterion.get("missing_behavior") or "unknown")
    structured = _structured_cv_fields(row)
    text = ranking_feature_text(semantic_content=row.get("semantic_content"), structured=structured)
    evidence: list[dict[str, Any]] = []
    result = "unknown"
    detail = "insufficient structured evidence"

    if ctype == "minimum_experience_years":
        required = float(_rule_value(rule, "minimum_years", "years") or 0)
        years = structured.get("years_experience") or structured.get("experience_years")
        try:
            years_n = float(years) if years is not None else _years_from_text(text)
        except Exception:
            years_n = _years_from_text(text)
        if years_n is None:
            result = "unknown" if missing_behavior == "unknown" else "not_met"
            detail = "years of experience not verified"
        elif years_n >= required:
            result = "met"
            detail = f"experience_years={years_n} >= {required}"
            evidence.append({"source": "cv_extraction_or_text", "field": "experience_years", "value": years_n})
        else:
            result = "not_met"
            detail = f"experience_years={years_n} < {required}"
            evidence.append({"source": "cv_extraction_or_text", "field": "experience_years", "value": years_n})

    elif ctype in {"certification", "education", "language", "technical_skill", "location", "work_arrangement", "work_authorization", "availability"}:
        needle = normalize_text(str(_rule_value(rule, "value", "required", "skill", "certification", "language", "location") or ""))
        field_map = {
            "certification": ["certifications", "certificates", "license"],
            "education": ["education", "degree", "qualifications"],
            "language": ["languages", "language"],
            "technical_skill": ["skills", "technical_skills"],
            "location": ["location", "city", "country"],
            "work_arrangement": ["work_arrangement", "remote", "onsite"],
            "work_authorization": ["work_authorization", "visa", "permit"],
            "availability": ["availability", "notice_period", "start_date"],
        }
        found = False
        for field in field_map.get(ctype, []):
            value = structured.get(field)
            if value is None:
                continue
            blob = normalize_text(json.dumps(value, ensure_ascii=False) if not isinstance(value, str) else value)
            if needle and needle in blob:
                found = True
                evidence.append({"source": "structured_cv", "field": field, "value": value})
                break
        if not found and needle and needle in text:
            # Text hit alone is weak for hard requirements → unknown, not met.
            result = "unknown"
            detail = "only unstructured text mention; hard fact not verified"
            evidence.append({"source": "unstructured_text", "field": "semantic_content", "value": needle})
        elif found:
            result = "met"
            detail = f"{ctype} matched approved structured evidence"
        else:
            result = "unknown" if missing_behavior == "unknown" else "not_met"
            detail = f"{ctype} evidence missing"

    else:
        result = "not_applicable"
        detail = "unsupported criterion"

    if result not in HARD_RESULTS:
        result = "unknown"
    return {
        "criterion_id": str(criterion.get("criterion_id") or ""),
        "criterion_type": ctype,
        "label": criterion.get("label"),
        "classification": criterion.get("classification"),
        "result": result,
        "detail": detail,
        "evidence": evidence,
    }


def evaluate_application_eligibility(
    criteria: list[dict[str, Any]],
    row: dict[str, Any],
    *,
    evidence_policy: dict[str, Any] | None = None,
) -> dict[str, Any]:
    policy = normalize_evidence_policy(evidence_policy)
    required_missing: list[str] = []
    cv_readiness = application_cv_readiness(row)
    if source_mode(policy, "cv") == "required" and not cv_readiness["ready"]:
        required_missing.extend(["required_cv_unavailable", str(cv_readiness["reason"])])
    if source_mode(policy, "assessment") == "required":
        status = str(row.get("assessment_status") or "").lower()
        percent = row.get("assessment_percent")
        if not (status == "completed" and percent is not None):
            required_missing.append("required_assessment_missing")
    if source_mode(policy, "semantic") == "required" and not row.get("semantic_content") and row.get("semantic_similarity") is None:
        required_missing.append("required_semantic_unavailable")
    if source_mode(policy, "screening") == "required":
        screening = str(row.get("screening_status") or "").lower()
        if screening not in {"complete", "completed"}:
            required_missing.append("required_screening_incomplete")

    hard = [c for c in criteria if str(c.get("classification") or "hard") == "hard" and c.get("active", True)]
    if not hard:
        if required_missing:
            return {
                "eligibility_bucket": "insufficient_information",
                "requirement_results": [],
                "hard_met": 0,
                "hard_not_met": 0,
                "hard_unknown": 0,
                "required_missing": required_missing,
                "requirements_configured": False,
            }
        # Advisory comparison allowed without hard requirements.
        return {
            "eligibility_bucket": "not_applicable",
            "requirement_results": [],
            "hard_met": 0,
            "hard_not_met": 0,
            "hard_unknown": 0,
            "required_missing": [],
            "requirements_configured": False,
        }
    results = [evaluate_hard_criterion(c, row) for c in hard]
    not_met = sum(1 for r in results if r["result"] == "not_met")
    unknown = sum(1 for r in results if r["result"] == "unknown")
    met = sum(1 for r in results if r["result"] == "met")
    if not_met:
        bucket = "requirement_not_met"
    elif unknown or required_missing:
        bucket = "insufficient_information"
    else:
        bucket = "eligible"
    return {
        "eligibility_bucket": bucket,
        "requirement_results": results,
        "hard_met": met,
        "hard_not_met": not_met,
        "hard_unknown": unknown,
        "required_missing": required_missing,
        "requirements_configured": True,
    }


# ---------------------------------------------------------------------------
# R2 advisory soft scoring
# ---------------------------------------------------------------------------

def _keyword_hits(text: str, keywords: list[str]) -> list[str]:
    hits = []
    seen: set[str] = set()
    for keyword in keywords:
        token = normalize_text(keyword)
        if not token or token in _SKILL_STOPWORDS or len(token) < 3:
            continue
        if token in text and token not in seen:
            seen.add(token)
            hits.append(token)
    return hits


def soft_component_scores(
    *,
    row: dict[str, Any],
    job: dict[str, Any],
    soft_criteria: list[dict[str, Any]],
    semantic_similarity: float | None,
    assessment_contribution_approved: bool = False,
    evidence_policy: dict[str, Any] | None = None,
    assessments_module_enabled: bool = True,
    criteria_metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    policy = normalize_evidence_policy(evidence_policy)
    _ = assessment_contribution_approved  # provenance-only; gating uses effective_assessment_mode
    assessment_mode, assessment_selection = effective_assessment_mode(
        policy,
        assessments_module_enabled=assessments_module_enabled,
        criteria_metadata=criteria_metadata,
    )
    structured = _structured_cv_fields(row)
    facts_readiness = _cv_facts.readiness_from_row(row)
    text = ranking_feature_text(semantic_content=row.get("semantic_content"), structured=structured)
    job_text = normalize_text(
        " ".join(
            [
                str(job.get("title") or job.get("title_en") or ""),
                str(job.get("title_ar") or ""),
                json.dumps(job.get("requirements") or {}, ensure_ascii=False),
                json.dumps(job.get("requirements_en") or {}, ensure_ascii=False),
                json.dumps(job.get("requirements_ar") or {}, ensure_ascii=False),
            ]
        )
    )
    soft_keywords: list[str] = []
    for criterion in soft_criteria:
        rule = criterion.get("rule_json") if isinstance(criterion.get("rule_json"), dict) else {}
        value = _rule_value(rule, "value", "skill", "keywords")
        if isinstance(value, list):
            soft_keywords.extend(str(v) for v in value)
        elif value:
            soft_keywords.append(str(value))
    soft_keywords.extend(re.findall(r"[a-z0-9\u0600-\u06FF]{3,}", job_text)[:20])

    skill_hits = _keyword_hits(text, soft_keywords[:30])
    skills_raw = min(SOFT_COMPONENT_WEIGHTS["skills_alignment"], (len(set(skill_hits)) / 8.0) * SOFT_COMPONENT_WEIGHTS["skills_alignment"])
    structured_skills = [
        str(value).strip()
        for value in (structured.get("skills") or [])
        if str(value or "").strip()
    ] if isinstance(structured.get("skills"), list) else []
    structured_employment = [
        value for value in (structured.get("employment") or []) if isinstance(value, dict)
    ] if isinstance(structured.get("employment"), list) else []
    structured_education = [
        str(value).strip()
        for value in (structured.get("education") or [])
        if str(value or "").strip()
    ] if isinstance(structured.get("education"), list) else []

    years = structured.get("experience_years") or structured.get("years_experience") or _years_from_text(text)
    try:
        years_n = float(years) if years is not None else 0.0
    except Exception:
        years_n = 0.0
    if years_n:
        experience_raw = min(
            SOFT_COMPONENT_WEIGHTS["experience_alignment"],
            (years_n / 5.0) * SOFT_COMPONENT_WEIGHTS["experience_alignment"],
        )
    elif structured_employment:
        experience_types = {
            str(item.get("experience_type") or "professional_or_unspecified")
            for item in structured_employment
        }
        role_signal = bool(skill_hits)
        if experience_types == {"academic_or_simulated"}:
            experience_raw = 7.0 if role_signal else 3.0
        else:
            experience_raw = 14.0 if role_signal else 8.0
    else:
        experience_raw = 0.0

    edu_hits = _keyword_hits(text, ["bachelor", "master", "degree", "diploma", "certificate", "certified", "بكالوريوس", "ماجستير", "شهادة"])
    education_raw = min(SOFT_COMPONENT_WEIGHTS["education_cert_alignment"], (len(edu_hits) / 3.0) * SOFT_COMPONENT_WEIGHTS["education_cert_alignment"])

    assessment_raw = 0.0
    assessment_available = False
    required_missing: list[str] = []
    optional_missing: list[str] = []
    unused_omitted: list[str] = []
    status = str(row.get("assessment_status") or "").lower()
    percent = row.get("assessment_percent")
    attempt_position = str(row.get("assessment_position_code") or row.get("position_code") or "").strip().upper()
    job_position = str(job.get("position_code") or "").strip().upper()
    linked_to_job = bool(attempt_position and job_position and attempt_position == job_position)
    assessment_enabled = assessment_mode != "unused" and assessment_selection is not None
    assessment_match = assessment_attempt_matches_selection(row, assessment_selection or {})
    if not assessment_enabled:
        unused_omitted.append("assessment_unused_by_policy")
    elif status == "completed" and percent is not None and linked_to_job and assessment_match:
        try:
            assessment_raw = min(
                SOFT_COMPONENT_WEIGHTS["assessment_evidence"],
                (float(percent) / 100.0) * SOFT_COMPONENT_WEIGHTS["assessment_evidence"],
            )
            assessment_available = True
        except Exception:
            code = "assessment_percent_unusable"
            (required_missing if assessment_mode == "required" else optional_missing).append(code)
    elif not linked_to_job and (status or percent is not None):
        code = "assessment_unrelated_to_job"
        (required_missing if assessment_mode == "required" else optional_missing).append(code)
    elif status == "completed" and percent is not None and linked_to_job and not assessment_match:
        code = "assessment_not_selected_by_policy"
        (required_missing if assessment_mode == "required" else optional_missing).append(code)
    elif status in {"failed", "cancelled", "expired", "in_progress", "pending"}:
        code = f"assessment_{status}"
        (required_missing if assessment_mode == "required" else optional_missing).append(code)
    elif status:
        code = f"assessment_{status}"
        (required_missing if assessment_mode == "required" else optional_missing).append(code)
    else:
        code = "assessment_missing"
        (required_missing if assessment_mode == "required" else optional_missing).append(code)

    semantic_mode = source_mode(policy, "semantic")
    semantic_raw = 0.0
    semantic_available = False
    if semantic_mode == "unused":
        unused_omitted.append("semantic_unused_by_policy")
    elif semantic_similarity is None:
        code = "semantic_similarity_unavailable"
        (required_missing if semantic_mode == "required" else optional_missing).append(code)
    else:
        semantic_raw = max(
            0.0,
            min(
                SOFT_COMPONENT_WEIGHTS["semantic_alignment"],
                float(semantic_similarity) * SOFT_COMPONENT_WEIGHTS["semantic_alignment"],
            ),
        )
        semantic_available = True

    cv_mode = source_mode(policy, "cv")
    cv_readiness = application_cv_readiness(row)
    if cv_mode == "required" and not cv_readiness["ready"]:
        required_missing.extend(["required_cv_unavailable", str(cv_readiness["reason"])])
    elif cv_mode == "optional" and not cv_readiness["ready"]:
        optional_missing.extend(["cv_unavailable", str(cv_readiness["reason"])])
    elif cv_mode == "unused":
        unused_omitted.append("cv_unused_by_policy")

    screening_mode = source_mode(policy, "screening")
    screening = str(row.get("screening_status") or "").lower()
    if screening_mode == "required" and screening not in {"complete", "completed"}:
        required_missing.append("required_screening_incomplete")
    elif screening_mode == "optional" and screening and screening not in {"complete", "completed"}:
        optional_missing.append("screening_incomplete")
    elif screening_mode == "unused":
        unused_omitted.append("screening_unused_by_policy")

    if source_mode(policy, "interview") == "unused":
        unused_omitted.append("interview_unused_by_policy")

    # ranking-soft-v2: include only enabled+available components and normalize.
    raw_components: dict[str, float | None] = {
        "skills_alignment": skills_raw,
        "experience_alignment": experience_raw,
        "education_cert_alignment": education_raw,
        "assessment_evidence": assessment_raw if assessment_available else None,
        "semantic_alignment": semantic_raw if semantic_available else None,
    }
    if cv_mode == "unused" or (cv_mode == "required" and not application_has_usable_cv(row)):
        raw_components["skills_alignment"] = None
        raw_components["experience_alignment"] = None
        raw_components["education_cert_alignment"] = None
    if assessment_mode == "unused":
        raw_components["assessment_evidence"] = None
    if semantic_mode == "unused":
        raw_components["semantic_alignment"] = None

    available_weights = 0.0
    earned = 0.0
    components: dict[str, float] = {}
    for key, value in raw_components.items():
        weight = float(SOFT_COMPONENT_WEIGHTS[key])
        if value is None:
            continue
        available_weights += weight
        earned += float(value)
        components[key] = round(float(value), 2)

    if available_weights > 0:
        advisory_score = round((earned / available_weights) * SOFT_SCORE_MAX, 2)
    else:
        advisory_score = 0.0

    configured_sources = []
    for source in EVIDENCE_SOURCES:
        if source == "assessment":
            if assessment_mode != "unused":
                configured_sources.append(source)
        elif source_mode(policy, source) != "unused":
            configured_sources.append(source)
    present_sources = 0
    if "cv" in configured_sources and (application_has_usable_cv(row) or bool(text.strip())):
        present_sources += 1
    if "screening" in configured_sources and screening in {"complete", "completed"}:
        present_sources += 1
    if "assessment" in configured_sources and assessment_available:
        present_sources += 1
    if "semantic" in configured_sources and semantic_available:
        present_sources += 1
    # interview never contributes yet
    coverage = round(present_sources / max(len(configured_sources), 1), 2) if configured_sources else 0.0
    if required_missing:
        confidence = "low"
    elif coverage >= 0.75:
        confidence = "high"
    elif coverage >= 0.45:
        confidence = "medium"
    else:
        confidence = "low"

    missing = list(dict.fromkeys([*required_missing, *optional_missing]))
    evidence = []
    if facts_readiness.get("ready") and structured_skills:
        evidence.append({
            "source": "application_cv_facts",
            "field": "cv_skills",
            "value": structured_skills[:12],
            "facts_id": facts_readiness.get("facts_id"),
        })
    if facts_readiness.get("ready") and structured_employment:
        evidence.append({
            "source": "application_cv_facts",
            "field": "employment",
            "value": structured_employment[:4],
            "facts_id": facts_readiness.get("facts_id"),
        })
    if facts_readiness.get("ready") and structured_education:
        evidence.append({
            "source": "application_cv_facts",
            "field": "cv_education",
            "value": structured_education[:8],
            "facts_id": facts_readiness.get("facts_id"),
        })
    if skill_hits and "skills_alignment" in components:
        basis = job.get("_ranking_basis") if isinstance(job.get("_ranking_basis"), dict) else {}
        evidence.append({
            "source": (
                "approved_keywords"
                if basis.get("source") == "approved_criteria"
                else "job_profile_keywords"
            ),
            "field": "skills",
            "value": skill_hits[:8],
        })
    if years_n and "experience_alignment" in components:
        evidence.append({"source": "cv_extraction_or_text", "field": "experience_years", "value": years_n})
    if edu_hits and "education_cert_alignment" in components:
        evidence.append({"source": "cv_text", "field": "education_cert", "value": edu_hits[:5]})
    if assessment_available and "assessment_evidence" in components:
        evidence.append(
            {
                "source": "assessment",
                "field": "percent",
                "value": float(percent) if percent is not None else None,
                "employer_approved_for_ranking": True,
                "ranking_mode": "cv_plus_approved_assessment",
                "position_code": attempt_position,
                "attempt_id": row.get("assessment_attempt_id"),
                "battery_key": (assessment_selection or {}).get("battery_key") or row.get("assessment_battery_key"),
                "assessment_version_id": (assessment_selection or {}).get("assessment_version_id")
                or row.get("assessment_version_id"),
                "norm_version": (assessment_selection or {}).get("norm_version")
                or row.get("assessment_norm_version"),
                "attempt_selection_rule": (assessment_selection or {}).get("attempt_selection_rule"),
                "policy_version": (assessment_selection or {}).get("policy_version"),
                "approved_by_user_id": (assessment_selection or {}).get("approved_by_user_id"),
                "approved_at": (assessment_selection or {}).get("approved_at"),
            }
        )
    if semantic_available and "semantic_alignment" in components:
        evidence.append({"source": "semantic_documents", "field": "similarity", "value": round(float(semantic_similarity), 4)})
    component_statuses = {
        "skills_alignment": (
            "not_configured"
            if not soft_keywords
            else ("aligned" if skill_hits else "zero_alignment")
        ),
        "experience_alignment": (
            "aligned"
            if years_n
            else ("present_unquantified" if structured_employment else "not_found")
        ),
        "education_cert_alignment": "aligned" if edu_hits else "not_found",
        "assessment_evidence": (
            "not_configured"
            if assessment_mode == "unused"
            else ("aligned" if assessment_available else "unavailable")
        ),
        "semantic_alignment": (
            "not_configured"
            if semantic_mode == "unused"
            else ("aligned" if semantic_available and semantic_raw > 0 else ("zero_alignment" if semantic_available else "unavailable"))
        ),
    }
    return {
        "advisory_score": advisory_score,
        "component_scores": components,
        "missing_data": missing,
        "required_missing": required_missing,
        "optional_missing": optional_missing,
        "unused_omitted": unused_omitted,
        "component_statuses": component_statuses,
        "cv_facts_readiness": facts_readiness,
        "required_evidence_complete": not bool(required_missing),
        "evidence": evidence,
        "evidence_coverage": coverage,
        "confidence": confidence,
        "available_weight_total": available_weights,
        "scoring_config_version": SCORING_CONFIG_VERSION,
        "evidence_policy_version": EVIDENCE_POLICY_VERSION,
        "assessment_mode": assessment_mode,
        "assessment_selection": assessment_selection,
        "ranking_result_kind": (
            "cv_plus_approved_assessment" if assessment_available else "cv_based"
        ),
    }


def ranking_safe_projection_text(content: str | None) -> str:
    """Scrub denylisted fields/proxies before Ranking embedding projection.

    Does not modify the canonical CV file or CV extraction authority.
    """
    return scrub_sensitive_text(str(content or ""))


def rebuild_ranking_safe_embeddings(
    orch: Any,
    *,
    company_code: str | None = None,
    app_keys: list[str] | None = None,
    force: bool = False,
) -> dict[str, Any]:
    """Rebuild Ranking-safe voyage-4-large projections for semantic_documents.

    Skips documents already on voyage-4-large + projection version unless force=True.
    Never writes CV extraction rows or file_registry content.
    """
    company = validate_company(company_code) if company_code else None
    embed = getattr(orch, "embed_rank_query", None)
    # Prefer document embed path if available.
    upsert = getattr(orch, "upsert_application_semantic_document", None)
    cfg = getattr(orch, "embedding_provider_config", lambda: None)()
    if not isinstance(cfg, dict) or str(cfg.get("model") or "") != CANONICAL_EMBEDDING_MODEL:
        raise RankingError("embedding_model_not_canonical", f"rebuild requires {CANONICAL_EMBEDDING_MODEL}")
    rebuilt = 0
    skipped = 0
    failed = 0
    with orch.db_connect() as conn:
        with conn.cursor() as cur:
            where = ["entity_type='application'"]
            params: list[Any] = []
            if company:
                where.append("company_code=%s")
                params.append(company)
            if app_keys:
                where.append("entity_key = ANY(%s)")
                params.append(app_keys)
            cur.execute(
                f"""
                SELECT semantic_id, entity_key, company_code, content, model, dimensions, metadata, content_hash
                FROM semantic_documents
                WHERE {' AND '.join(where)}
                """,
                params,
            )
            rows = [_row(r) for r in cur.fetchall()]
            for row in rows:
                meta = row.get("metadata") if isinstance(row.get("metadata"), dict) else {}
                already = (
                    str(row.get("model") or "") == CANONICAL_EMBEDDING_MODEL
                    and int(row.get("dimensions") or 0) == 1024
                    and str(meta.get("ranking_projection_version") or "") == RANKING_PROJECTION_VERSION
                    and str(meta.get("denylist_version") or "") == DENYLIST_VERSION
                )
                if already and not force:
                    skipped += 1
                    continue
                safe_text = ranking_safe_projection_text(row.get("content"))
                # Use document embedding helper when present; else query embed as fallback for tests.
                vector = None
                if callable(getattr(orch, "embed_document_for_ranking", None)):
                    vector = orch.embed_document_for_ranking(safe_text)
                elif callable(embed):
                    vector = embed(safe_text)
                if not vector:
                    failed += 1
                    continue
                literal_fn = getattr(orch, "pgvector_literal", None)
                literal = literal_fn(vector) if callable(literal_fn) else "[" + ",".join(str(float(x)) for x in vector) + "]"
                new_meta = {
                    **meta,
                    "ranking_projection_version": RANKING_PROJECTION_VERSION,
                    "denylist_version": DENYLIST_VERSION,
                    "source_content_hash": row.get("content_hash"),
                    "projection_model": CANONICAL_EMBEDDING_MODEL,
                    "projection_dimensions": 1024,
                    "canonical_cv_unmodified": True,
                }
                cur.execute(
                    """
                    UPDATE semantic_documents
                    SET embedding=%s::vector,
                        provider='voyage',
                        model=%s,
                        dimensions=1024,
                        metadata=%s,
                        updated_at=now()
                    WHERE semantic_id=%s
                    """,
                    (literal, CANONICAL_EMBEDDING_MODEL, _json(orch, new_meta), row.get("semantic_id")),
                )
                rebuilt += 1
        conn.commit()
    return {
        "ok": True,
        "rebuilt": rebuilt,
        "skipped": skipped,
        "failed": failed,
        "model": CANONICAL_EMBEDDING_MODEL,
        "dimensions": 1024,
        "projection_version": RANKING_PROJECTION_VERSION,
        "denylist_version": DENYLIST_VERSION,
    }


def maybe_rerank_bounded(items: list[dict[str, Any]], *, query: str) -> tuple[list[dict[str, Any]], str | None]:
    """Optional rerank-2.5. Disabled unless WATHEFNI_RANKING_RERANK is explicitly on.

    Staging/production canonical stack keeps rerank disabled initially.
    Even when enabled, this stub must never omit items or change scores.
    """
    enabled = (os.environ.get("WATHEFNI_RANKING_RERANK") or "").strip().lower() in {"1", "true", "yes", "on"}
    if not enabled or not items:
        return items, None
    # Explicitly zero Voyage rerank API calls until staging A/B approval.
    return items, None


# ---------------------------------------------------------------------------
# Two-layer explanations: backend_explanation + post-commit terra_narrative
# ---------------------------------------------------------------------------

def build_backend_explanation(item: dict[str, Any]) -> str:
    """Deterministic explanation from committed eligibility/components/score/coverage."""
    components = item.get("component_scores") if isinstance(item.get("component_scores"), dict) else {}
    parts = [
        f"Eligibility={item.get('eligibility_bucket')}",
        f"advisory={item.get('advisory_score')}/100",
        f"coverage={item.get('evidence_coverage')}",
    ]
    if components:
        compact = ", ".join(f"{k}={v}" for k, v in sorted(components.items()))
        parts.append(f"components[{compact}]")
    hard = item.get("requirement_results") if isinstance(item.get("requirement_results"), list) else []
    if hard:
        hard_bits = [f"{r.get('criterion_type')}:{r.get('result')}" for r in hard[:8] if isinstance(r, dict)]
        if hard_bits:
            parts.append("hard[" + "; ".join(hard_bits) + "]")
    missing = item.get("missing_data") if isinstance(item.get("missing_data"), list) else []
    if missing:
        parts.append("missing=" + ",".join(str(m) for m in missing[:6]))
    return "; ".join(parts) + "."


def build_bounded_evidence_envelope(
    *,
    item: dict[str, Any],
    run: dict[str, Any],
    job: dict[str, Any] | None = None,
    criteria_set: dict[str, Any] | None = None,
    locale: str = "en",
) -> dict[str, Any]:
    """Backend-built envelope sent to Terra. Sensitive/raw CV content excluded."""
    provenance = item.get("provenance") if isinstance(item.get("provenance"), dict) else {}
    criteria = []
    for criterion in list((criteria_set or {}).get("criteria") or [])[:20]:
        if not isinstance(criterion, dict):
            continue
        criteria.append(
            sanitize_ranking_payload(
                {
                    "criterion_id": criterion.get("criterion_id"),
                    "criterion_type": criterion.get("criterion_type"),
                    "label": criterion.get("label"),
                    "classification": criterion.get("classification"),
                    "rule_json": criterion.get("rule_json"),
                }
            )
        )
    evidence = sanitize_ranking_payload(item.get("evidence") or [])
    requirements = sanitize_ranking_payload(item.get("requirement_results") or [])
    envelope = {
        "contract": "ranking_terra_evidence_envelope_v1",
        "locale": locale,
        "prompt_version": NARRATIVE_PROMPT_VERSION,
        "backend_explanation": item.get("backend_explanation") or item.get("explanation"),
        "committed_result": {
            "item_id": item.get("item_id"),
            "run_id": run.get("run_id"),
            "app_key": item.get("app_key"),
            "soft_rank": item.get("soft_rank"),
            "eligibility_bucket": item.get("eligibility_bucket"),
            "advisory_score": item.get("advisory_score"),
            "component_scores": sanitize_ranking_payload(item.get("component_scores") or {}),
            "evidence_coverage": item.get("evidence_coverage"),
            "confidence": item.get("confidence"),
            "missing_data": sanitize_ranking_payload(item.get("missing_data") or []),
            "requirement_results": requirements,
            "evidence": evidence,
        },
        "job": sanitize_ranking_payload(
            {
                "job_id": (job or {}).get("job_id") or run.get("job_id") or provenance.get("job_id"),
                "position_code": run.get("position_code") or provenance.get("position_code"),
                "title": (job or {}).get("title") or (job or {}).get("title_en") or (job or {}).get("title_ar"),
                "version": (job or {}).get("version") or provenance.get("job_version"),
                "requirements_en": (job or {}).get("requirements_en"),
                "requirements_ar": (job or {}).get("requirements_ar"),
            }
        ),
        "criteria": criteria,
        "cv_refs": {
            "cv_file_id": provenance.get("cv_file_id"),
            "cv_extraction_run_id": provenance.get("cv_extraction_run_id"),
            "semantic_content_hash": provenance.get("semantic_content_hash"),
        },
        "assessment_refs": {
            "assessment_attempt_id": provenance.get("assessment_attempt_id"),
        },
        "provenance": {
            "tenant": provenance.get("tenant") or run.get("company_code"),
            "criteria_set_id": provenance.get("criteria_set_id"),
            "criteria_version": provenance.get("criteria_version"),
            "scoring_config_version": provenance.get("scoring_config_version") or SCORING_CONFIG_VERSION,
            "denylist_version": provenance.get("denylist_version") or DENYLIST_VERSION,
            "embedding_model": provenance.get("embedding_model"),
            "person_id": provenance.get("person_id"),
            "membership_id": provenance.get("membership_id"),
        },
        "rules": [
            "Explain only from this envelope.",
            "Do not calculate or alter scores, weights, or hard-requirement outcomes.",
            "Do not convert unknown into met or not_met.",
            "Do not invent facts absent from the envelope.",
            "Do not use sensitive or protected attributes.",
            "Do not shortlist, reject, schedule, offer, hire, or mutate lifecycle.",
            "Write a detailed candidate-specific narrative in the requested locale.",
        ],
    }
    assert_no_sensitive_leak(envelope, context="terra_evidence_envelope")
    return envelope


def terra_narrative_system_prompt(locale: str) -> str:
    lang = "Arabic" if str(locale or "").lower().startswith("ar") else "English"
    return (
        "You are OctoHR Ranking's post-commit brief layer (gpt-5.6-terra). "
        f"Write a fun, useful {lang} HR ranking brief for one already-committed result. "
        "Use only the provided evidence envelope. Never invent facts. Never change scores or eligibility. "
        "Never recommend automated hiring/lifecycle actions. Keep the verdict under 180 characters. "
        "Return JSON only with keys: narrative, language, verdict, why, gaps, next_step, "
        "interview_questions, matching_on. why/gaps/interview_questions/matching_on must be short string arrays."
    )


def _extract_json_object(payload: Any) -> dict[str, Any]:
    if isinstance(payload, dict):
        if any(key in payload for key in ("narrative", "verdict", "why", "gaps")):
            return payload
        content = payload.get("output_text") or payload.get("content") or payload.get("text")
        if isinstance(content, str) and content.strip():
            try:
                parsed = json.loads(content)
                if isinstance(parsed, dict):
                    return parsed
            except Exception:
                return {}
        return {}
    if isinstance(payload, str):
        raw = payload.strip()
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, dict):
                return parsed
        except Exception:
            return {}
    return {}


def _extract_narrative_text(payload: Any) -> str:
    parsed = _extract_json_object(payload)
    text = parsed.get("narrative") or parsed.get("verdict") or parsed.get("text") or parsed.get("fit_summary")
    if text:
        return str(text).strip()
    if isinstance(payload, dict):
        content = payload.get("output_text") or payload.get("content")
        if isinstance(content, str) and content.strip():
            return content.strip()
    if isinstance(payload, str):
        return payload.strip()
    return ""


def _extract_terra_brief(payload: Any) -> dict[str, Any] | None:
    parsed = _extract_json_object(payload)
    if not parsed:
        return None
    brief = {
        "verdict": str(parsed.get("verdict") or parsed.get("narrative") or "").strip()[:220] or None,
        "why": [str(x).strip() for x in list(parsed.get("why") or []) if str(x).strip()][:4],
        "gaps": [str(x).strip() for x in list(parsed.get("gaps") or []) if str(x).strip()][:4],
        "next_step": str(parsed.get("next_step") or "").strip()[:220] or None,
        "interview_questions": [
            str(x).strip() for x in list(parsed.get("interview_questions") or []) if str(x).strip()
        ][:3],
        "matching_on": [str(x).strip() for x in list(parsed.get("matching_on") or []) if str(x).strip()][:6],
    }
    if not any([brief["verdict"], brief["why"], brief["gaps"], brief["next_step"], brief["interview_questions"]]):
        return None
    return brief


def call_terra_narrative(
    orch: Any,
    *,
    envelope: dict[str, Any],
    locale: str = "en",
) -> dict[str, Any]:
    """Call gpt-5.6-terra for narrative only. Never mutates Ranking scores."""
    injectable = getattr(orch, "ranking_terra_narrative_callable", None)
    if callable(injectable):
        try:
            raw = injectable(envelope=envelope, locale=locale, model=NARRATIVE_MODEL, prompt_version=NARRATIVE_PROMPT_VERSION)
            text = _extract_narrative_text(raw)
            if not text:
                return {"ok": False, "error": "empty_narrative", "model": NARRATIVE_MODEL}
            brief = _extract_terra_brief(raw)
            return {
                "ok": True,
                "narrative_text": text,
                "brief": brief,
                "model": NARRATIVE_MODEL,
                "prompt_version": NARRATIVE_PROMPT_VERSION,
                "raw": raw if isinstance(raw, dict) else {"narrative": text},
            }
        except Exception as exc:
            return {"ok": False, "error": str(exc), "model": NARRATIVE_MODEL}

    provider_fn = getattr(orch, "planner_provider_config", None)
    provider = provider_fn() if callable(provider_fn) else None
    if not isinstance(provider, dict) or not provider.get("api_key"):
        return {"ok": False, "error": "provider_unavailable", "model": NARRATIVE_MODEL}

    model = NARRATIVE_MODEL
    system = terra_narrative_system_prompt(locale)
    user_payload = {
        "task": "Generate a short Ranking HR brief from the committed evidence envelope only.",
        "locale": locale,
        "prompt_version": NARRATIVE_PROMPT_VERSION,
        "envelope": json_safe(envelope),
        "required_output": {
            "narrative": "short HR verdict (<=180 chars)",
            "language": locale,
            "verdict": "one-line fun verdict",
            "why": ["up to 4 short why bullets from evidence"],
            "gaps": ["up to 4 short watch-outs"],
            "next_step": "one concrete next HR action",
            "interview_questions": ["up to 3 short interview questions"],
            "matching_on": ["up to 6 short matching chips"],
        },
    }
    api_kind = str(provider.get("api") or "")
    if api_kind == "openai-responses":
        # gpt-5.6-terra rejects temperature on /v1/responses.
        body = {
            "model": model,
            "input": [
                {"role": "system", "content": system},
                {"role": "user", "content": json.dumps(user_payload, ensure_ascii=False, default=str)},
            ],
        }
    else:
        body = {
            "model": model,
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": json.dumps(user_payload, ensure_ascii=False, default=str)},
            ],
        }
    import urllib.request

    req = urllib.request.Request(
        str(provider["url"]),
        data=json.dumps(body).encode("utf-8"),
        headers={"Authorization": f"Bearer {provider['api_key']}", "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            parsed = json.loads(resp.read().decode("utf-8", errors="replace"))
    except Exception as exc:
        return {"ok": False, "error": f"llm_error:{exc}", "model": model}

    extract_fn = getattr(orch, "extract_model_text", None)
    content = extract_fn(parsed) if callable(extract_fn) else json.dumps(parsed)
    text = _extract_narrative_text(content) or _extract_narrative_text(parsed)
    if not text:
        return {"ok": False, "error": "empty_narrative", "model": model, "raw": parsed}
    brief = _extract_terra_brief(content) or _extract_terra_brief(parsed)
    return {
        "ok": True,
        "narrative_text": text,
        "brief": brief,
        "model": model,
        "prompt_version": NARRATIVE_PROMPT_VERSION,
        "raw": parsed,
    }


def load_item_narrative(
    orch: Any,
    *,
    item_id: str,
    prompt_version: str = NARRATIVE_PROMPT_VERSION,
    evidence_hash: str | None = None,
    locale: str = "en",
) -> dict[str, Any] | None:
    with orch.db_connect() as conn:
        with conn.cursor() as cur:
            ensure_schema(cur)
            if evidence_hash:
                cur.execute(
                    """
                    SELECT * FROM ranking_item_narratives
                    WHERE item_id=%s AND prompt_version=%s AND evidence_hash=%s AND locale=%s
                    ORDER BY created_at DESC LIMIT 1
                    """,
                    (item_id, prompt_version, evidence_hash, locale),
                )
            else:
                cur.execute(
                    """
                    SELECT * FROM ranking_item_narratives
                    WHERE item_id=%s AND prompt_version=%s AND locale=%s AND status='completed'
                    ORDER BY created_at DESC LIMIT 1
                    """,
                    (item_id, prompt_version, locale),
                )
            row = cur.fetchone()
    return _row(row) if row else None


def persist_terra_narrative(
    orch: Any,
    *,
    item: dict[str, Any],
    run: dict[str, Any],
    envelope: dict[str, Any],
    evidence_hash: str,
    locale: str,
    llm_result: dict[str, Any],
) -> dict[str, Any]:
    """Write-once/idempotent narrative for (item_id, prompt_version, evidence_hash, locale)."""
    item_id = str(item.get("item_id") or "")
    if not item_id:
        raise RankingError("ranking_item_id_required")
    existing = load_item_narrative(
        orch,
        item_id=item_id,
        prompt_version=NARRATIVE_PROMPT_VERSION,
        evidence_hash=evidence_hash,
        locale=locale,
    )
    if existing and existing.get("status") == "completed" and existing.get("narrative_text"):
        return {**existing, "idempotent_replay": True}

    narrative_id = str((existing or {}).get("narrative_id") or uuid.uuid4())
    status = "completed" if llm_result.get("ok") and llm_result.get("narrative_text") else "failed"
    narrative_text = llm_result.get("narrative_text") if status == "completed" else None
    error = None if status == "completed" else str(llm_result.get("error") or "narrative_failed")
    brief = llm_result.get("brief") if isinstance(llm_result.get("brief"), dict) else None
    store_envelope = dict(envelope or {})
    if brief:
        store_envelope["brief"] = sanitize_ranking_payload(brief)
    provenance = {
        "model": NARRATIVE_MODEL,
        "prompt_version": NARRATIVE_PROMPT_VERSION,
        "evidence_hash": evidence_hash,
        "locale": locale,
        "run_id": run.get("run_id"),
        "item_id": item_id,
        "app_key": item.get("app_key"),
        "denylist_version": DENYLIST_VERSION,
        "scoring_config_version": SCORING_CONFIG_VERSION,
        "lifecycle_mutations": False,
        "score_mutation": False,
        "eligibility_mutation": False,
        "brief": sanitize_ranking_payload(brief) if brief else None,
    }
    with orch.db_connect() as conn:
        with conn.cursor() as cur:
            ensure_schema(cur)
            cur.execute(
                """
                INSERT INTO ranking_item_narratives(
                  narrative_id, item_id, run_id, company_code, position_code, app_key,
                  narrative_text, model, prompt_version, evidence_hash, locale, status, error,
                  evidence_envelope, provenance, generated_at
                ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s, CASE WHEN %s='completed' THEN now() ELSE NULL END)
                ON CONFLICT (item_id, prompt_version, evidence_hash, locale) DO UPDATE SET
                  narrative_text=COALESCE(ranking_item_narratives.narrative_text, EXCLUDED.narrative_text),
                  status=CASE
                    WHEN ranking_item_narratives.status='completed' THEN ranking_item_narratives.status
                    ELSE EXCLUDED.status
                  END,
                  error=CASE
                    WHEN ranking_item_narratives.status='completed' THEN ranking_item_narratives.error
                    ELSE EXCLUDED.error
                  END,
                  evidence_envelope=EXCLUDED.evidence_envelope,
                  provenance=EXCLUDED.provenance,
                  generated_at=CASE
                    WHEN ranking_item_narratives.status='completed' THEN ranking_item_narratives.generated_at
                    WHEN EXCLUDED.status='completed' THEN now()
                    ELSE ranking_item_narratives.generated_at
                  END,
                  updated_at=now()
                RETURNING *
                """,
                (
                    narrative_id,
                    item_id,
                    run.get("run_id"),
                    run.get("company_code"),
                    run.get("position_code"),
                    item.get("app_key"),
                    narrative_text,
                    NARRATIVE_MODEL,
                    NARRATIVE_PROMPT_VERSION,
                    evidence_hash,
                    locale,
                    status,
                    error,
                    _json(orch, store_envelope),
                    _json(orch, provenance),
                    status,
                ),
            )
            row = _row(cur.fetchone())
        conn.commit()
    if brief and isinstance(row, dict):
        row["brief"] = brief
    return row


def attach_terra_narratives(
    orch: Any,
    *,
    run_result: dict[str, Any],
    job: dict[str, Any] | None = None,
    criteria_set: dict[str, Any] | None = None,
    locale: str = "en",
    generate: bool = True,
) -> dict[str, Any]:
    """Post-commit narrative attachment. Never fails the Ranking run; never alters scores."""
    locale = "ar" if str(locale or "").lower().startswith("ar") else "en"
    items = list(run_result.get("items") or [])
    score_snapshot = [(i.get("item_id"), i.get("advisory_score"), i.get("eligibility_bucket"), json.dumps(i.get("component_scores") or {}, sort_keys=True)) for i in items]
    for item in items:
        item["backend_explanation"] = item.get("backend_explanation") or item.get("explanation") or build_backend_explanation(item)
        item["explanation"] = item["backend_explanation"]
        envelope = build_bounded_evidence_envelope(
            item=item,
            run=run_result,
            job=job,
            criteria_set=criteria_set,
            locale=locale,
        )
        evidence_hash = stable_hash(
            {
                "item_id": item.get("item_id"),
                "run_id": run_result.get("run_id"),
                "advisory_score": item.get("advisory_score"),
                "component_scores": item.get("component_scores"),
                "eligibility_bucket": item.get("eligibility_bucket"),
                "requirement_results": item.get("requirement_results"),
                "evidence": item.get("evidence"),
                "missing_data": item.get("missing_data"),
                "evidence_coverage": item.get("evidence_coverage"),
                "prompt_version": NARRATIVE_PROMPT_VERSION,
            }
        )
        item["evidence_hash"] = evidence_hash
        existing = None
        if item.get("item_id"):
            existing = load_item_narrative(
                orch,
                item_id=str(item["item_id"]),
                prompt_version=NARRATIVE_PROMPT_VERSION,
                evidence_hash=evidence_hash,
                locale=locale,
            )
        if existing and existing.get("status") == "completed" and existing.get("narrative_text"):
            narrative = {**existing, "idempotent_replay": True}
        elif generate:
            llm_result = call_terra_narrative(orch, envelope=envelope, locale=locale)
            try:
                narrative = persist_terra_narrative(
                    orch,
                    item=item,
                    run=run_result,
                    envelope=envelope,
                    evidence_hash=evidence_hash,
                    locale=locale,
                    llm_result=llm_result,
                )
            except Exception as exc:
                narrative = {
                    "status": "failed",
                    "error": str(exc),
                    "model": NARRATIVE_MODEL,
                    "prompt_version": NARRATIVE_PROMPT_VERSION,
                    "evidence_hash": evidence_hash,
                    "locale": locale,
                    "narrative_text": None,
                }
        else:
            narrative = existing or {
                "status": "pending",
                "model": NARRATIVE_MODEL,
                "prompt_version": NARRATIVE_PROMPT_VERSION,
                "evidence_hash": evidence_hash,
                "locale": locale,
                "narrative_text": None,
            }
        item["terra_narrative"] = {
            "narrative_id": narrative.get("narrative_id"),
            "text": narrative.get("narrative_text"),
            "model": narrative.get("model") or NARRATIVE_MODEL,
            "prompt_version": narrative.get("prompt_version") or NARRATIVE_PROMPT_VERSION,
            "evidence_hash": narrative.get("evidence_hash") or evidence_hash,
            "locale": narrative.get("locale") or locale,
            "status": narrative.get("status"),
            "error": narrative.get("error"),
            "generated_at": narrative.get("generated_at"),
            "idempotent_replay": bool(narrative.get("idempotent_replay")),
            "legacy": False,
            "canonical": True,
            "brief": (
                narrative.get("brief")
                if isinstance(narrative.get("brief"), dict)
                else (
                    (narrative.get("evidence_envelope") or {}).get("brief")
                    if isinstance(narrative.get("evidence_envelope"), dict)
                    else (
                        (narrative.get("provenance") or {}).get("brief")
                        if isinstance(narrative.get("provenance"), dict)
                        else None
                    )
                )
            ),
        }
        # Display helper: prefer terra when completed, else backend.
        item["display_explanation"] = item["terra_narrative"]["text"] or item["backend_explanation"]

    # Hard proof: scores/eligibility unchanged by narrative layer.
    after = [(i.get("item_id"), i.get("advisory_score"), i.get("eligibility_bucket"), json.dumps(i.get("component_scores") or {}, sort_keys=True)) for i in items]
    if after != score_snapshot:
        raise RankingError("narrative_mutated_scores", "terra narrative must not alter ranking scores or eligibility")
    run_result["items"] = items
    run_result["narrative_prompt_version"] = NARRATIVE_PROMPT_VERSION
    run_result["narrative_model"] = NARRATIVE_MODEL
    return run_result


def retry_terra_narrative(
    orch: Any,
    *,
    company_code: str,
    position_code: str,
    item_id: str,
    locale: str = "en",
) -> dict[str, Any]:
    """Idempotent narrative retry for one committed ranking item."""
    company = validate_company(company_code)
    position = validate_position(position_code)
    with orch.db_connect() as conn:
        with conn.cursor() as cur:
            ensure_schema(cur)
            cur.execute(
                """
                SELECT i.*, r.run_id, r.company_code, r.position_code, r.job_id, r.job_version,
                       r.criteria_set_id, r.criteria_version, r.provenance AS run_provenance
                FROM ranking_run_items i
                JOIN ranking_runs r ON r.run_id=i.run_id
                WHERE i.item_id=%s AND i.company_code=%s AND upper(i.position_code)=%s
                """,
                (item_id, company, position),
            )
            row = cur.fetchone()
    if not row:
        raise RankingError("ranking_item_not_found")
    item = _row(row)
    item["backend_explanation"] = item.get("explanation") or build_backend_explanation(item)
    item["explanation"] = item["backend_explanation"]
    run = {
        "run_id": item.get("run_id"),
        "company_code": company,
        "position_code": position,
        "job_id": item.get("job_id"),
        "items": [item],
    }
    job = None
    criteria_set = None
    try:
        job = load_job(orch, company_code=company, position_code=position)
    except Exception:
        job = None
    try:
        criteria_set = latest_approved_criteria_set(orch, company_code=company, position_code=position)
    except Exception:
        criteria_set = None
    result = attach_terra_narratives(
        orch,
        run_result=run,
        job=job,
        criteria_set=criteria_set,
        locale=locale,
        generate=True,
    )
    return result["items"][0]


# ---------------------------------------------------------------------------
# R3 staleness
# ---------------------------------------------------------------------------

def mark_runs_stale(orch: Any, *, company_code: str, position_code: str, reason: str) -> int:
    company = validate_company(company_code)
    position = validate_position(position_code)
    with orch.db_connect() as conn:
        with conn.cursor() as cur:
            ensure_schema(cur)
            cur.execute(
                """
                UPDATE ranking_runs
                SET is_current=false, stale_reason=%s, stale_at=now()
                WHERE company_code=%s AND upper(position_code)=%s AND is_current=true
                """,
                (reason, company, position),
            )
            count = cur.rowcount
            cur.execute(
                """
                INSERT INTO ranking_recalculation_jobs(company_code, position_code, reason, status)
                VALUES (%s,%s,%s,'pending')
                """,
                (company, position, reason),
            )
        conn.commit()
    return int(count or 0)


def current_run(orch: Any, *, company_code: str, position_code: str) -> dict[str, Any] | None:
    company = validate_company(company_code)
    position = validate_position(position_code)
    with orch.db_connect() as conn:
        with conn.cursor() as cur:
            ensure_schema(cur)
            cur.execute(
                """
                SELECT * FROM ranking_runs
                WHERE company_code=%s AND upper(position_code)=%s AND is_current=true
                ORDER BY created_at DESC
                LIMIT 1
                """,
                (company, position),
            )
            row = cur.fetchone()
            if not row:
                return None
            run = _row(row)
            cur.execute(
                """
                SELECT * FROM ranking_run_items
                WHERE run_id=%s
                ORDER BY soft_rank NULLS LAST, pool_ordinal ASC, app_key ASC
                """,
                (run["run_id"],),
            )
            run["items"] = [_row(r) for r in cur.fetchall()]
            return run


# ---------------------------------------------------------------------------
# Canonical ranking service
# ---------------------------------------------------------------------------

def _semantic_similarity_for_rows(orch: Any, rows: list[dict[str, Any]], query: str) -> dict[str, float | None]:
    out: dict[str, float | None] = {str(r.get("app_key")): None for r in rows}
    embed = getattr(orch, "embed_rank_query", None)
    literal_fn = getattr(orch, "pgvector_literal", None)
    if not callable(embed) or not callable(literal_fn) or not query.strip():
        return out
    vector = embed(query)
    if not vector:
        return out
    literal = literal_fn(vector)
    app_keys = [str(r.get("app_key")) for r in rows if r.get("app_key")]
    if not app_keys:
        return out
    company = str(rows[0].get("company_code") or "")
    with orch.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT DISTINCT ON (entity_key)
                       entity_key AS app_key,
                       1 - (embedding <=> %s::vector) AS semantic_similarity
                FROM semantic_documents
                WHERE company_code=%s AND entity_type='application'
                  AND entity_key = ANY(%s) AND embedding IS NOT NULL
                ORDER BY entity_key,
                         CASE WHEN semantic_id=('application:' || entity_key || ':cv') THEN 0 ELSE 1 END,
                         updated_at DESC NULLS LAST
                """,
                (literal, company, app_keys),
            )
            for row in cur.fetchall():
                item = _row(row)
                try:
                    out[str(item.get("app_key"))] = float(item.get("semantic_similarity"))
                except Exception:
                    out[str(item.get("app_key"))] = None
    return out


def rank_job_applications(
    orch: Any,
    *,
    company_code: str,
    position_code: str,
    actor_user_id: str | None = None,
    query: str = "",
    force: bool = False,
    visibility_sql: str | None = None,
    visibility_params: list[Any] | None = None,
) -> dict[str, Any]:
    """Single Ranking authority used by dashboard, mobile, and assistant."""
    company = validate_company(company_code)
    position = validate_position(position_code)
    job = load_job(orch, company_code=company, position_code=position)
    criteria_set = latest_approved_criteria_set(orch, company_code=company, position_code=position)
    role_profile = automatic_role_profile(job)
    criteria = list((criteria_set or {}).get("criteria") or role_profile.get("criteria") or [])
    ranking_basis = (
        {
            "version": "ranking-basis-v1",
            "source": "approved_criteria",
            "label": "Employer-approved job criteria",
            "advisory": True,
            "criteria_count": len(criteria),
            "profile_hash": stable_hash(
                {
                    "criteria_set_id": (criteria_set or {}).get("criteria_set_id"),
                    "version": (criteria_set or {}).get("version"),
                }
            ),
        }
        if criteria_set
        else {
            key: role_profile.get(key)
            for key in ("version", "source", "label", "advisory", "criteria_count", "profile_hash")
        }
    )
    job = {**job, "_ranking_basis": ranking_basis}
    effective_criteria_set = criteria_set or {
        "criteria": criteria,
        "metadata": {"ranking_basis": ranking_basis},
        "scoring_config_version": SCORING_CONFIG_VERSION,
    }
    hard_criteria = [c for c in criteria if str(c.get("classification") or "hard") == "hard"]
    soft_criteria = [c for c in criteria if str(c.get("classification") or "") == "soft"]
    evidence_policy = evidence_policy_from_criteria_set(criteria_set)
    criteria_meta = (criteria_set or {}).get("metadata") if isinstance((criteria_set or {}).get("metadata"), dict) else {}
    # Merge top-level evidence_policy assessment_selection if present.
    if isinstance((criteria_set or {}).get("evidence_policy"), dict):
        ep = criteria_set.get("evidence_policy") or {}
        if isinstance(ep.get("assessment_selection"), dict) and "assessment_selection" not in criteria_meta:
            criteria_meta = {**criteria_meta, "assessment_selection": ep.get("assessment_selection")}
    module_check = getattr(orch, "company_has_module", None)
    assessments_module_enabled = True
    if callable(module_check):
        try:
            assessments_module_enabled = bool(module_check(company, "assessments"))
        except Exception:
            assessments_module_enabled = False
    assessment_mode, assessment_selection = effective_assessment_mode(
        evidence_policy,
        assessments_module_enabled=assessments_module_enabled,
        criteria_metadata=criteria_meta,
    )
    assessment_contribution_approved = assessment_mode != "unused" and assessment_selection is not None

    pool_rows = load_complete_job_pool(
        orch,
        company_code=company,
        position_code=position,
        visibility_sql=visibility_sql,
        visibility_params=visibility_params,
        assessment_selection=assessment_selection if assessment_contribution_approved else None,
    )
    ranking_query = query.strip() or str(job.get("title") or job.get("title_en") or position)
    similarities = _semantic_similarity_for_rows(orch, pool_rows, ranking_query)

    embedding_model = None
    embedding_dims = None
    cfg = getattr(orch, "embedding_provider_config", lambda: None)()
    if isinstance(cfg, dict):
        embedding_model = cfg.get("model")
        # Refuse silent voyage-4 fallback for Ranking authority.
        if str(embedding_model or "").strip() and str(embedding_model).strip() != CANONICAL_EMBEDDING_MODEL:
            raise RankingError(
                "embedding_model_not_canonical",
                f"Ranking requires {CANONICAL_EMBEDDING_MODEL}, got {embedding_model}",
            )
        embedding_model = embedding_model or CANONICAL_EMBEDDING_MODEL
    # Detect mixed stored embedding models in the pool.
    stored_models = {str(r.get("semantic_model") or "") for r in pool_rows if r.get("semantic_model")}
    if stored_models and (stored_models - {CANONICAL_EMBEDDING_MODEL, ""}):
        raise RankingError(
            "mixed_embedding_models_in_pool",
            f"Ranking pool contains non-canonical embedding models: {sorted(stored_models)}",
        )

    request_payload = {
        "company_code": company,
        "position_code": position,
        "job_version": job.get("version"),
        "criteria_version": (criteria_set or {}).get("version"),
        "ranking_basis": ranking_basis,
        "pool_app_keys": [r.get("app_key") for r in pool_rows],
        "scoring_config_version": SCORING_CONFIG_VERSION,
        "evidence_policy_version": EVIDENCE_POLICY_VERSION,
        "evidence_policy": evidence_policy,
        "cv_evidence_contract_version": _cv_evidence.CV_EVIDENCE_CONTRACT_VERSION,
        "cv_facts_contract_version": _cv_facts.CV_FACTS_CONTRACT_VERSION,
        "cv_facts_extractor_version": _cv_facts.CV_FACTS_EXTRACTOR_VERSION,
        "pool_cv_evidence_versions": [
            {
                "app_key": row.get("app_key"),
                "evidence_id": row.get("cv_evidence_id"),
                "status": row.get("cv_evidence_status"),
                "embedding_status": row.get("cv_evidence_embedding_status"),
                "facts_id": row.get("cv_facts_id"),
                "facts_status": row.get("cv_facts_status"),
                "facts_hash": row.get("cv_facts_hash"),
            }
            for row in pool_rows
        ],
        "denylist_version": DENYLIST_VERSION,
        "embedding_model": embedding_model or CANONICAL_EMBEDDING_MODEL,
        "embedding_dimensions": 1024,
        "ranking_projection_version": RANKING_PROJECTION_VERSION,
        "reranker_enabled": False,
        "reranker_model": CANONICAL_RERANK_MODEL,
        "query": ranking_query,
        "assessment_contribution_approved": assessment_contribution_approved,
    }
    request_hash = stable_hash(request_payload)

    if not force:
        existing = current_run(orch, company_code=company, position_code=position)
        if existing and existing.get("request_hash") == request_hash and not existing.get("stale_reason"):
            existing["idempotent_replay"] = True
            existing["advisory"] = True
            existing["ai_advisory"] = True
            existing["hr_decision_maker"] = True
            existing["ok"] = True
            existing["company_code"] = company
            existing["position_code"] = position
            existing["job"] = {
                "position_code": position,
                "title": job.get("title") or job.get("title_en") or job.get("title_ar") or position,
                "version": job.get("version"),
            }
            existing["ranking_basis"] = ranking_basis
            for item in existing.get("items") or []:
                item["backend_explanation"] = item.get("explanation") or build_backend_explanation(item)
                item["explanation"] = item["backend_explanation"]
            try:
                attach_terra_narratives(
                    orch,
                    run_result=existing,
                    job=job,
                    criteria_set=effective_criteria_set,
                    locale=str(getattr(orch, "ranking_narrative_locale", None) or "en"),
                    generate=True,
                )
            except Exception:
                # Narrative must never fail an already-committed ranking replay.
                pass
            return existing

    items: list[dict[str, Any]] = []
    for ordinal, row in enumerate(pool_rows):
        eligibility = evaluate_application_eligibility(
            hard_criteria,
            row,
            evidence_policy=evidence_policy,
        )
        if criteria and not hard_criteria:
            eligibility["requirements_configured"] = True
        # Optional Candidate Knowledge live Ranking reader (held/restricted deny).
        ck_reader: dict[str, Any] = {"active": False}
        try:
            from candidate_knowledge_live_registration import apply_ranking_reader_overlay

            ck_reader = apply_ranking_reader_overlay(
                company_code=company,
                application=row,
                eligibility=eligibility,
            )
            if ck_reader.get("active") and not ck_reader.get("eligible", True):
                denial = str(ck_reader.get("denial_reason") or "ck_ranking_denied")
                missing = list(eligibility.get("required_missing") or [])
                missing.append(f"ck_ranking_denied:{denial}")
                eligibility = {
                    **eligibility,
                    "eligibility_bucket": "insufficient_information",
                    "required_missing": missing,
                    "ck_ranking_reader": ck_reader,
                }
        except Exception:
            ck_reader = {"active": False, "error": "overlay_import_or_runtime_failed"}
        soft = soft_component_scores(
            row=row,
            job=job,
            soft_criteria=soft_criteria,
            semantic_similarity=similarities.get(str(row.get("app_key"))),
            assessment_contribution_approved=assessment_contribution_approved,
            evidence_policy=evidence_policy,
            assessments_module_enabled=assessments_module_enabled,
            criteria_metadata=criteria_meta,
        )
        if ck_reader.get("active") and not ck_reader.get("eligible", True):
            soft = {
                **soft,
                "advisory_score": None,
                "required_evidence_complete": False,
                "required_missing": list(soft.get("required_missing") or [])
                + [str(ck_reader.get("denial_reason") or "ck_ranking_denied")],
            }
        provenance = {
            "tenant": company,
            "job_id": job.get("job_id"),
            "job_version": job.get("version"),
            "criteria_set_id": (criteria_set or {}).get("criteria_set_id"),
            "criteria_version": (criteria_set or {}).get("version"),
            "ranking_basis": ranking_basis,
            "app_key": row.get("app_key"),
            "person_id": row.get("person_id") or row.get("candidate_person_id"),
            "membership_id": row.get("membership_id"),
            "cv_file_id": row.get("cv_file_id"),
            "cv_extraction_run_id": row.get("cv_extraction_run_id"),
            "cv_evidence_id": row.get("cv_evidence_id"),
            "cv_evidence_contract_version": row.get("cv_evidence_contract_version"),
            "cv_evidence_readiness": application_cv_readiness(row),
            "cv_facts_id": row.get("cv_facts_id"),
            "cv_facts_contract_version": row.get("cv_facts_contract_version"),
            "cv_facts_extractor_version": row.get("cv_facts_extractor_version"),
            "cv_facts_hash": row.get("cv_facts_hash"),
            "cv_facts_readiness": soft.get("cv_facts_readiness") or _cv_facts.readiness_from_row(row),
            "component_statuses": soft.get("component_statuses") or {},
            "assessment_attempt_id": row.get("assessment_attempt_id") if assessment_contribution_approved else None,
            "assessment_battery_key": row.get("assessment_battery_key") if assessment_contribution_approved else None,
            "assessment_version_id": row.get("assessment_version_id") if assessment_contribution_approved else None,
            "assessment_norm_version": row.get("assessment_norm_version") if assessment_contribution_approved else None,
            "assessment_selection": assessment_selection,
            "assessment_mode": assessment_mode,
            "ranking_result_kind": soft.get("ranking_result_kind") or "cv_based",
            "semantic_content_hash": row.get("semantic_content_hash"),
            "embedding_provider": "voyage",
            "embedding_model": embedding_model or row.get("semantic_model") or CANONICAL_EMBEDDING_MODEL,
            "embedding_dimensions": 1024,
            "ranking_projection_version": RANKING_PROJECTION_VERSION,
            "scoring_config_version": SCORING_CONFIG_VERSION,
            "evidence_policy_version": EVIDENCE_POLICY_VERSION,
            "evidence_policy": evidence_policy,
            "denylist_version": DENYLIST_VERSION,
            "reranker_enabled": False,
            "reranker_model": CANONICAL_RERANK_MODEL,
            "narrative_prompt_version": NARRATIVE_PROMPT_VERSION,
            "narrative_model": NARRATIVE_MODEL,
            "assessment_contribution_approved": assessment_contribution_approved,
            "required_evidence_complete": soft.get("required_evidence_complete"),
            "optional_missing": soft.get("optional_missing") or [],
            "required_missing": soft.get("required_missing") or [],
            "ck_ranking_reader": ck_reader,
        }
        explanation = build_backend_explanation(
            {
                "eligibility_bucket": eligibility["eligibility_bucket"],
                "advisory_score": soft["advisory_score"] if soft.get("required_evidence_complete") else None,
                "evidence_coverage": soft["evidence_coverage"],
                "component_scores": soft["component_scores"],
                "component_statuses": soft.get("component_statuses") or {},
                "requirement_results": eligibility["requirement_results"],
                "missing_data": soft["missing_data"],
                "confidence": soft.get("confidence"),
                "required_evidence_complete": soft.get("required_evidence_complete"),
                "requirements_configured": eligibility.get("requirements_configured"),
            }
        )
        items.append(
            {
                "app_key": row.get("app_key"),
                "person_id": provenance["person_id"],
                "membership_id": provenance["membership_id"],
                "eligibility_bucket": eligibility["eligibility_bucket"],
                "requirement_results": eligibility["requirement_results"],
                "requirements_configured": eligibility.get("requirements_configured"),
                "advisory_score": soft["advisory_score"],
                "component_scores": soft["component_scores"],
                "component_statuses": soft.get("component_statuses") or {},
                "evidence": soft["evidence"],
                "missing_data": soft["missing_data"],
                "required_missing": soft.get("required_missing") or [],
                "optional_missing": soft.get("optional_missing") or [],
                "required_evidence_complete": soft.get("required_evidence_complete"),
                "evidence_coverage": soft["evidence_coverage"],
                "confidence": soft["confidence"],
                "explanation": explanation,
                "backend_explanation": explanation,
                "provenance": provenance,
                "pool_ordinal": ordinal,
                "display": {
                    "name": row.get("candidate_name"),
                    "status": row.get("status"),
                    "position_code": row.get("position_code"),
                    "position_title": row.get("position_title"),
                },
                # lifecycle mutation fields intentionally absent
            }
        )

    # Soft rank only among ranking.pool.rankable; excluded items stay for explanation.
    import ranking_queue_contract as _rqc

    ordered = sorted(
        items,
        key=lambda item: (
            0 if _rqc.is_rankable_item(item) else 1,
            -(float(item.get("advisory_score") or 0) if item.get("advisory_score") is not None else 0),
            int(item.get("pool_ordinal") or 0),
        ),
    )
    ordered, reranker_model = maybe_rerank_bounded(ordered, query=ranking_query)
    # Canonical staging/production pin: reranker disabled; never present stub as active.
    if reranker_model:
        raise RankingError("reranker_must_remain_disabled", "Ranking qualification keeps rerank-2.5 disabled")
    visible_rank = 0
    for item in ordered:
        if not _rqc.is_rankable_item(item):
            item["soft_rank"] = None
            item["leaderboard_eligible"] = False
            continue
        visible_rank += 1
        item["soft_rank"] = visible_rank
        item["leaderboard_eligible"] = True

    assert_no_sensitive_leak(
        [{"component_scores": i["component_scores"], "evidence": i["evidence"], "provenance": i["provenance"]} for i in ordered],
        context="ranking_run_items",
    )

    counters = _rqc.reconcile_pool_counters(ordered)
    eligible_count = counters["eligible_count"]
    not_met_count = counters["not_met_count"]
    unknown_count = counters["unknown_count"]
    not_applicable_count = counters["not_applicable_count"]
    rankable_count = counters["rankable_count"]
    restricted_held_count = counters["restricted_held_count"]

    run_id = str(uuid.uuid4())
    provenance = {
        **request_payload,
        "pool_total": len(ordered),
        "matching_count": counters["matching_count"],
        "rankable_count": rankable_count,
        "eligible_count": eligible_count,
        "not_applicable_count": not_applicable_count,
        "not_met_count": not_met_count,
        "unknown_count": unknown_count,
        "restricted_held_count": restricted_held_count,
        "counters_reconcile": counters["reconciles"],
        "assessment_mode": assessment_mode,
        "assessment_contribution_approved": assessment_contribution_approved,
        "visibility_scoped": bool(str(visibility_sql or "").strip()),
        "reranker_model": CANONICAL_RERANK_MODEL,
        "reranker_enabled": False,
        "reranker_api_calls": 0,
        "interview_scoring": False,
        "lifecycle_mutations": False,
        "legacy_gpt_evaluator_called": False,
        "contract": "ranking_queue_contract_v1",
    }
    previous_current = current_run(orch, company_code=company, position_code=position)
    try:
        with orch.db_connect() as conn:
            with conn.cursor() as cur:
                ensure_schema(cur)
                cur.execute(
                    """
                    INSERT INTO ranking_runs(
                      run_id, company_code, position_code, job_id, job_version, criteria_set_id, criteria_version,
                      actor_user_id, status, pool_total, eligible_count, not_met_count, unknown_count, scored_count,
                      request_hash, provenance, denylist_version, scoring_config_version, embedding_model, reranker_model,
                      is_current
                    ) VALUES (
                      %s,%s,%s,%s,%s,%s,%s,%s,'completed',%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,false
                    )
                    ON CONFLICT (company_code, position_code, request_hash) DO UPDATE
                      SET status='completed',
                          pool_total=EXCLUDED.pool_total, eligible_count=EXCLUDED.eligible_count,
                          not_met_count=EXCLUDED.not_met_count, unknown_count=EXCLUDED.unknown_count,
                          scored_count=EXCLUDED.scored_count, provenance=EXCLUDED.provenance,
                          embedding_model=EXCLUDED.embedding_model, reranker_model=EXCLUDED.reranker_model,
                          actor_user_id=EXCLUDED.actor_user_id, error=NULL
                    RETURNING run_id
                    """,
                    (
                        run_id,
                        company,
                        position,
                        job.get("job_id"),
                        job.get("version"),
                        (criteria_set or {}).get("criteria_set_id"),
                        (criteria_set or {}).get("version"),
                        actor_user_id,
                        len(ordered),
                        eligible_count,
                        not_met_count,
                        unknown_count,
                        len(ordered),
                        request_hash,
                        _json(orch, provenance),
                        DENYLIST_VERSION,
                        SCORING_CONFIG_VERSION,
                        embedding_model,
                        reranker_model,
                    ),
                )
                returned = _row(cur.fetchone())
                run_id = str(returned.get("run_id") or run_id)
                cur.execute("DELETE FROM ranking_run_items WHERE run_id=%s", (run_id,))
                for item in ordered:
                    cur.execute(
                        """
                        INSERT INTO ranking_run_items(
                          run_id, company_code, position_code, app_key, person_id, membership_id,
                          eligibility_bucket, advisory_score, component_scores, requirement_results,
                          evidence, missing_data, evidence_coverage, confidence, explanation,
                          provenance, pool_ordinal, soft_rank
                        ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                        RETURNING item_id
                        """,
                        (
                            run_id,
                            company,
                            position,
                            item["app_key"],
                            item.get("person_id"),
                            item.get("membership_id"),
                            item["eligibility_bucket"],
                            item.get("advisory_score"),
                            _json(orch, item.get("component_scores") or {}),
                            _json(orch, item.get("requirement_results") or []),
                            _json(orch, item.get("evidence") or []),
                            _json(orch, item.get("missing_data") or []),
                            item.get("evidence_coverage"),
                            item.get("confidence"),
                            item.get("backend_explanation") or item.get("explanation"),
                            _json(orch, item.get("provenance") or {}),
                            item.get("pool_ordinal"),
                            item.get("soft_rank"),
                        ),
                    )
                    item_row = _row(cur.fetchone())
                    item["item_id"] = str(item_row.get("item_id") or "")
                    item["run_id"] = run_id
                    item["backend_explanation"] = item.get("backend_explanation") or item.get("explanation")
                # Only after successful item write: flip current pointer.
                cur.execute(
                    """
                    UPDATE ranking_runs
                    SET is_current=false,
                        stale_reason=coalesce(stale_reason, 'superseded_by_new_run'),
                        stale_at=coalesce(stale_at, now())
                    WHERE company_code=%s AND upper(position_code)=%s AND is_current=true AND run_id<>%s
                    """,
                    (company, position, run_id),
                )
                cur.execute(
                    """
                    UPDATE ranking_runs
                    SET is_current=true, stale_reason=NULL, stale_at=NULL, status='completed', error=NULL
                    WHERE run_id=%s
                    """,
                    (run_id,),
                )
            conn.commit()
    except Exception as exc:
        # Failed run must not replace last successful result.
        try:
            with orch.db_connect() as conn:
                with conn.cursor() as cur:
                    ensure_schema(cur)
                    cur.execute(
                        """
                        INSERT INTO ranking_recalculation_jobs(company_code, position_code, reason, status, last_error)
                        VALUES (%s,%s,%s,'failed',%s)
                        """,
                        (company, position, "rank_persist_failed", str(exc)[:500]),
                    )
                conn.commit()
        except Exception:
            pass
        if previous_current and previous_current.get("items") is not None:
            previous_current = dict(previous_current)
            previous_current["ok"] = True
            previous_current["failed_replacement"] = True
            previous_current["error"] = str(exc)
            previous_current["advisory"] = True
            previous_current["ai_advisory"] = True
            previous_current["hr_decision_maker"] = True
            return previous_current
        raise RankingError("ranking_persist_failed", str(exc)) from exc

    result = {
        "ok": True,
        "run_id": run_id,
        "company_code": company,
        "position_code": position,
        "job": {
            "job_id": job.get("job_id"),
            "position_code": position,
            "title": job.get("title") or job.get("title_en") or job.get("title_ar"),
            "version": job.get("version"),
        },
        "criteria_set": {
            "criteria_set_id": (criteria_set or {}).get("criteria_set_id"),
            "version": (criteria_set or {}).get("version"),
            "status": (criteria_set or {}).get("status"),
            "count": len(criteria),
            "evidence_policy": evidence_policy,
        },
        "ranking_basis": ranking_basis,
        "evidence_policy": evidence_policy,
        "evidence_policy_version": EVIDENCE_POLICY_VERSION,
        "scoring_config_version": SCORING_CONFIG_VERSION,
        "pool_total": len(ordered),
        "matching_count": len(ordered),
        "rankable_count": rankable_count,
        "eligible_count": eligible_count,
        "not_applicable_count": not_applicable_count,
        "not_met_count": not_met_count,
        "unknown_count": unknown_count,
        "restricted_held_count": restricted_held_count,
        "scored_count": rankable_count,
        "request_hash": request_hash,
        "provenance": provenance,
        "items": ordered,
        "advisory": True,
        "ai_advisory": True,
        "hr_decision_maker": True,
        "lifecycle_mutations": False,
        "stale": False,
        "idempotent_replay": False,
        "message": "Ranking is advisory. HR remains the decision-maker. Top-N views are not the complete pool.",
    }
    try:
        attach_terra_narratives(
            orch,
            run_result=result,
            job=job,
            criteria_set=effective_criteria_set,
            locale=str(getattr(orch, "ranking_narrative_locale", None) or "en"),
            generate=True,
        )
    except Exception:
        # Committed ranking remains authoritative; backend_explanation is the fallback.
        for item in result["items"]:
            item["backend_explanation"] = item.get("backend_explanation") or item.get("explanation") or build_backend_explanation(item)
            item["terra_narrative"] = {
                "text": None,
                "model": NARRATIVE_MODEL,
                "prompt_version": NARRATIVE_PROMPT_VERSION,
                "status": "failed",
                "error": "narrative_attach_failed",
                "canonical": True,
                "legacy": False,
            }
            item["display_explanation"] = item["backend_explanation"]
    return result


def get_ranking_run(orch: Any, *, company_code: str, position_code: str, run_id: str | None = None, locale: str = "en") -> dict[str, Any]:
    company = validate_company(company_code)
    position = validate_position(position_code)
    with orch.db_connect() as conn:
        with conn.cursor() as cur:
            ensure_schema(cur)
            if run_id:
                cur.execute(
                    "SELECT * FROM ranking_runs WHERE run_id=%s AND company_code=%s AND upper(position_code)=%s",
                    (run_id, company, position),
                )
            else:
                cur.execute(
                    """
                    SELECT * FROM ranking_runs
                    WHERE company_code=%s AND upper(position_code)=%s AND is_current=true
                    ORDER BY created_at DESC LIMIT 1
                    """,
                    (company, position),
                )
            row = cur.fetchone()
            if not row:
                raise RankingError("ranking_run_not_found")
            run = _row(row)
            cur.execute(
                """
                SELECT * FROM ranking_run_items WHERE run_id=%s
                ORDER BY soft_rank NULLS LAST, pool_ordinal ASC
                """,
                (run["run_id"],),
            )
            run["items"] = [_row(r) for r in cur.fetchall()]
    run["ok"] = True
    run["company_code"] = company
    run["position_code"] = position
    run["advisory"] = True
    run["ai_advisory"] = True
    run["hr_decision_maker"] = True
    run["stale"] = bool(run.get("stale_reason")) or not bool(run.get("is_current"))
    for item in run["items"]:
        item["backend_explanation"] = item.get("explanation") or build_backend_explanation(item)
        item["explanation"] = item["backend_explanation"]
        prov = item.get("provenance") if isinstance(item.get("provenance"), dict) else {}
        if item.get("required_evidence_complete") is None and "required_evidence_complete" in prov:
            item["required_evidence_complete"] = prov.get("required_evidence_complete")
        ck = prov.get("ck_ranking_reader") if isinstance(prov.get("ck_ranking_reader"), dict) else None
        if ck and not item.get("ck_ranking_reader"):
            item["ck_ranking_reader"] = ck
    try:
        job = load_job(orch, company_code=company, position_code=position)
    except Exception:
        job = None
    try:
        criteria_set = latest_approved_criteria_set(orch, company_code=company, position_code=position)
    except Exception:
        criteria_set = None
    try:
        attach_terra_narratives(
            orch,
            run_result=run,
            job=job,
            criteria_set=criteria_set,
            locale=locale,
            generate=False,
        )
    except Exception:
        pass
    import ranking_queue_contract as _rqc

    counters = _rqc.reconcile_pool_counters(run.get("items") or [])
    run["matching_count"] = counters["matching_count"]
    run["rankable_count"] = counters["rankable_count"]
    run["eligible_count"] = counters["eligible_count"]
    run["not_applicable_count"] = counters["not_applicable_count"]
    run["not_met_count"] = counters["not_met_count"]
    run["unknown_count"] = counters["unknown_count"]
    run["restricted_held_count"] = counters["restricted_held_count"]
    run["pool_total"] = counters["matching_count"]
    return run


def to_legacy_rank_candidates_shape(result: dict[str, Any], *, top_n: int | None = None) -> dict[str, Any]:
    """Compatibility adapter for existing dashboard/mobile clients."""
    import ranking_queue_contract as _rqc

    items = list(result.get("items") or [])
    job = result.get("job") if isinstance(result.get("job"), dict) else {}
    position_title = job.get("title") or result.get("position_code")
    ranking_basis = result.get("ranking_basis")
    if not isinstance(ranking_basis, dict):
        provenance = result.get("provenance") if isinstance(result.get("provenance"), dict) else {}
        ranking_basis = provenance.get("ranking_basis") if isinstance(provenance.get("ranking_basis"), dict) else {}
    # ranking.run.top_n — only rankable; never fill with unrankable.
    selected = _rqc.top_n_rankable(items, top_n)
    limit = top_n if top_n and top_n > 0 else len(selected)
    candidates = []
    for item in selected:
        display = item.get("display") if isinstance(item.get("display"), dict) else {}
        backend_explanation = item.get("backend_explanation") or item.get("explanation") or build_backend_explanation(item)
        terra = item.get("terra_narrative") if isinstance(item.get("terra_narrative"), dict) else {}
        display_explanation = terra.get("text") or item.get("display_explanation") or backend_explanation
        gpt_source = "ranking_terra_narrative" if terra.get("text") else "ranking_backend_explanation"
        strengths = _legacy_human_strengths(item)
        gaps = _legacy_human_gaps(item)
        advisory = item.get("advisory_score")
        candidates.append(
            {
                "app_key": item.get("app_key"),
                "item_id": item.get("item_id"),
                "name": display.get("name"),
                "phone": None,
                "position_code": display.get("position_code") or result.get("position_code"),
                "position_title": display.get("position_title") or position_title,
                "status": display.get("status"),
                "score": advisory,
                "score_breakdown": item.get("component_scores"),
                "component_scores": item.get("component_scores"),
                "confidence": item.get("confidence"),
                "evidence": _legacy_human_evidence_refs(item),
                "reasons": [backend_explanation] if backend_explanation else [],
                "eligibility_bucket": item.get("eligibility_bucket"),
                "requirement_results": item.get("requirement_results"),
                "missing_data": gaps,
                "required_missing": item.get("required_missing"),
                "required_evidence_complete": item.get("required_evidence_complete"),
                "provenance": item.get("provenance"),
                "soft_rank": item.get("soft_rank"),
                "backend_explanation": backend_explanation,
                "terra_narrative": terra,
                "display_explanation": display_explanation,
                "gpt_evaluation": {
                    "source": gpt_source,
                    "fit_summary": display_explanation if advisory is not None else None,
                    "backend_explanation": backend_explanation,
                    "terra_narrative": terra.get("text"),
                    "terra_status": terra.get("status"),
                    "terra_model": terra.get("model"),
                    "prompt_version": terra.get("prompt_version") or NARRATIVE_PROMPT_VERSION,
                    "evidence_hash": terra.get("evidence_hash") or item.get("evidence_hash"),
                    "legacy": False,
                    "canonical": True,
                    "strengths": strengths,
                    "gaps": gaps,
                    "risks": [],
                    "recommended_next_step": "Review evidence and decide manually; Ranking does not change lifecycle.",
                    "confidence": item.get("confidence"),
                },
                "ai_advisory": True,
            }
        )
    return {
        "ok": True,
        "query": (result.get("provenance") or {}).get("query"),
        "filters": {
            "company_code": result.get("company_code"),
            "position": result.get("position_code"),
            "position_title": position_title,
            "status": None,
        },
        "position_title": position_title,
        "ranking_basis": ranking_basis,
        "run_id": result.get("run_id"),
        "request_hash": result.get("request_hash"),
        "pool_total": result.get("pool_total"),
        "total_matching": result.get("matching_count", result.get("pool_total")),
        "matching_count": result.get("matching_count", result.get("pool_total")),
        "rankable_count": result.get("rankable_count"),
        "total_rankable": result.get("rankable_count"),
        "not_applicable_count": result.get("not_applicable_count"),
        "restricted_held_count": result.get("restricted_held_count"),
        "pool_scanned": result.get("pool_total"),
        "shown_top_n": len(candidates),
        "capped": int(result.get("rankable_count") or 0) > len(candidates),
        "eligible_count": result.get("eligible_count"),
        "not_met_count": result.get("not_met_count"),
        "unknown_count": result.get("unknown_count"),
        "candidates": candidates,
        "items": items,
        "advisory": True,
        "ai_advisory": True,
        "hr_decision_maker": True,
        "stale": result.get("stale"),
        "provenance": result.get("provenance"),
        "narrative_model": result.get("narrative_model") or NARRATIVE_MODEL,
        "narrative_prompt_version": result.get("narrative_prompt_version") or NARRATIVE_PROMPT_VERSION,
        "message": result.get("message"),
        "idempotent_replay": bool(result.get("idempotent_replay")),
        "embedding": {
            "provider": "voyage",
            "model": (result.get("provenance") or {}).get("embedding_model") or CANONICAL_EMBEDDING_MODEL,
            "used": bool((result.get("provenance") or {}).get("embedding_model")),
        },
        "role_profile": {
            "key": "job_criteria",
            "label": ranking_basis.get("label") or "Job profile",
            "criteria": [],
        },
    }


_FIELD_LABELS = {
    "skills": "Skills",
    "employment": "Work experience",
    "education": "Education",
    "cv_education": "Education",
    "cv_skills": "Skills",
    "experience_years": "Years of experience",
    "certifications": "Certifications",
    "languages": "Languages",
    "summary": "Professional summary",
}


def _legacy_human_strengths(item: dict[str, Any]) -> list[str]:
    out: list[str] = []
    for entry in list(item.get("evidence") or [])[:6]:
        if not isinstance(entry, dict):
            continue
        field = str(entry.get("field") or "").strip()
        label = _FIELD_LABELS.get(field, field.replace("_", " ").strip().title() if field else "")
        value = entry.get("value")
        if isinstance(value, list):
            text = ", ".join(str(v).strip() for v in value[:4] if str(v).strip())
        elif isinstance(value, dict):
            text = ""
        else:
            text = str(value or "").strip()
        if label and text and len(text) < 160:
            out.append(f"{label}: {text}")
        elif label:
            out.append(label)
        if len(out) >= 3:
            break
    components = item.get("component_scores") if isinstance(item.get("component_scores"), dict) else {}
    component_labels = {
        "skills_alignment": "Skills match",
        "experience_alignment": "Relevant experience",
        "education_cert_alignment": "Education",
        "assessment_evidence": "Assessment evidence",
        "semantic_alignment": "CV relevance",
    }
    for key, label in component_labels.items():
        if key not in components:
            continue
        try:
            value = float(components.get(key))
        except (TypeError, ValueError):
            continue
        if value > 0 and label not in out:
            out.append(label)
        if len(out) >= 3:
            break
    return out[:3]


def _legacy_human_gaps(item: dict[str, Any]) -> list[str]:
    gaps: list[str] = []
    for code in list(item.get("missing_data") or []) + list(item.get("required_missing") or []):
        text = str(code or "").strip()
        if not text:
            continue
        lowered = text.lower()
        if lowered.startswith("ck_ranking_reader_failed") or "undefinedfunction" in lowered:
            continue
        if lowered.startswith("ck_ranking_denied:"):
            continue
        gaps.append(text.replace("_", " "))
        if len(gaps) >= 3:
            break
    return gaps


def _legacy_human_evidence_refs(item: dict[str, Any]) -> list[str]:
    refs: list[str] = []
    for entry in list(item.get("evidence") or [])[:8]:
        if not isinstance(entry, dict):
            continue
        field = str(entry.get("field") or "").strip()
        label = _FIELD_LABELS.get(field, field.replace("_", " ").strip().title() if field else "")
        if label and label not in refs:
            refs.append(label)
    return refs[:5]



def rank_candidates_compat(orch: Any, action: dict[str, Any], *, company_code: str | None = None) -> dict[str, Any]:
    """Public compatibility entry used by app.rank_candidates / mobile / assistant."""
    company = validate_company(company_code or action.get("company_code"))
    position = str(action.get("position") or "").strip()
    if not position:
        raise RankingError("job_required", "Ranking requires an exact job/position")
    top_n = int(action.get("top_n") or 0) or None
    locale = str(action.get("locale") or getattr(orch, "ranking_narrative_locale", None) or "en")
    setattr(orch, "ranking_narrative_locale", locale)
    result = rank_job_applications(
        orch,
        company_code=company,
        position_code=position,
        actor_user_id=str(action.get("actor_user_id") or "") or None,
        query=str(action.get("query") or action.get("prompt_text") or ""),
        force=bool(action.get("force")),
        visibility_sql=action.get("visibility_sql"),
        visibility_params=list(action.get("visibility_params") or []) or None,
    )
    return to_legacy_rank_candidates_shape(result, top_n=top_n)
