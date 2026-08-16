"""Talent Pool Classification authority (advisory, multi-label, evidence-backed).

Independent of Jobs, Ranking, outreach, intake_admit, and recruiting lifecycle.
Uses stored CV text/facts/embeddings only — never triggers OCR.

Feature flags (all default OFF for production posture):
  WATHEFNI_TALENT_POOL_CLASSIFICATION              master
  WATHEFNI_TALENT_POOL_CLASSIFICATION_TENANTS      allowlist (empty => nobody)
  WATHEFNI_TALENT_POOL_CLASSIFICATION_SCHEMA       schema/read support
  WATHEFNI_TALENT_POOL_CLASSIFICATION_MANUAL       local/manual execution
  WATHEFNI_TALENT_POOL_CLASSIFICATION_WORKERS      background workers (must stay OFF)
  WATHEFNI_TALENT_POOL_CLASSIFICATION_UI           filters/chips/profile
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import uuid
from pathlib import Path
from typing import Any

FEATURE_MASTER = "WATHEFNI_TALENT_POOL_CLASSIFICATION"
FEATURE_TENANTS = "WATHEFNI_TALENT_POOL_CLASSIFICATION_TENANTS"
FEATURE_SCHEMA = "WATHEFNI_TALENT_POOL_CLASSIFICATION_SCHEMA"
FEATURE_MANUAL = "WATHEFNI_TALENT_POOL_CLASSIFICATION_MANUAL"
FEATURE_WORKERS = "WATHEFNI_TALENT_POOL_CLASSIFICATION_WORKERS"
FEATURE_UI = "WATHEFNI_TALENT_POOL_CLASSIFICATION_UI"

CLASSIFIER_VERSION = "classifier.deterministic_v1.2"
TAXONOMY_PACK_PATH = Path(__file__).resolve().parent / "talent_pool_taxonomy_v1.json"

BAND_HIGH = "High"
BAND_MEDIUM = "Medium"
BAND_NEEDS_REVIEW = "Needs review"
# Backward-compatible alias for older tests/docs
BAND_LOW = BAND_NEEDS_REVIEW
BANDS = (BAND_HIGH, BAND_MEDIUM, BAND_NEEDS_REVIEW)

STATE_ACTIVE = "active"
STATE_STALE = "stale"
STATE_SUPERSEDED = "superseded_by_run"
STATE_UNCLASSIFIED = "unclassified"
STATE_NEEDS_REVIEW = "needs_review"
STATE_CLASSIFIED = "classified"
STATE_CLASSIFIED_MULTI = "classified_multi"
STATE_CAUTIOUS = "cautious"

OUTCOME_CLEAR = "Clear evidence"
OUTCOME_MULTI = "Multiple relevant areas"
OUTCOME_PARTIAL = "Partial evidence"
OUTCOME_NEEDS_HR = "Needs HR review"
OUTCOME_INSUFFICIENT = "Insufficient evidence to classify"

REVIEW_ACTIONS = ("confirm", "reject", "add", "correct", "supersede")

MATCH_CONFIRMED_CLASSIFICATION = "Matched confirmed classification"
MATCH_AI_SUGGESTED_CLASSIFICATION = "Matched AI-suggested classification"
MATCH_CLASSIFICATION_EVIDENCE = "Matched classification evidence"

JOB_TYPE = "talent_pool_classify_v1"

# Taxonomy-driven filter dimensions (stable node_type keys, not English labels).
DIMENSION_TYPES: dict[str, str] = {
    "career_area": "career_function",
    "likely_role": "likely_role",
    "skill": "skill",
    "industry": "industry",
    "seniority": "seniority",
    "experience_band": "experience_band",
}
FILTERABLE_DIMENSIONS = tuple(DIMENSION_TYPES.keys())
AUTHORITY_FILTERS = (
    "confirmed_or_high_ai",
    "confirmed_only",
    "ai_suggested",
    "either",
)
SAVED_VIEW_CLASSIFICATION_SCHEMA = "classification-filters-v1"
CONFIDENCE_FILTERS = (BAND_HIGH, BAND_MEDIUM, BAND_NEEDS_REVIEW, "Unclassified", STATE_NEEDS_REVIEW)

# Internal score thresholds → UI bands (decimals never shown to HR)
_HIGH_MIN = 0.72
_MEDIUM_MIN = 0.52
_NEEDS_REVIEW_MIN = 0.40
_MIN_TEXT_CHARS = 24
_ROLE_CUE_RE = re.compile(
    r"(engineer|developer|accountant|hr|marketing|sales|manager|analyst|operations|"
    r"software|python|sql|excel|recrui|computer science|graduate|intern|"
    r"مهندس|محاسب|مبيعات|برمج|تقنية|بايثون|platform|sre|تشغيل)",
    re.I,
)
_TECH_ROLE_RE = re.compile(
    r"(software (?:engineer|developer)|backend (?:engineer|developer)|frontend (?:engineer|developer)|"
    r"full[ -]?stack (?:engineer|developer)|data scientist|machine learning engineer|ai engineer|"
    r"security engineer|cybersecurity|help ?desk|desktop support|it support|devops|"
    r"platform engineer|site reliability engineer|\bsre\b|systems administrator|network engineer|"
    r"cloud engineer|technology consultant|it (?:manager|specialist)|programmer|"
    r"مهندس برمجيات|مطور برمجيات|مبرمج|أمن سيبراني|دعم فني|مهندس منصات)",
    re.I,
)
_TECH_EDUCATION_RE = re.compile(
    r"(computer science|software engineering|information technology|computer engineering|"
    r"علوم الحاسوب|هندسة البرمجيات|تقنية المعلومات|هندسة الحاسوب)",
    re.I,
)
_TECH_PROJECT_RE = re.compile(
    r"((?:built|developed|implemented|designed|maintained|deployed|coded|automated|"
    r"بنى|طور|برمج|صمم).{0,80}(?:api|application|software|backend|frontend|database|"
    r"platform|system|code|python|sql|fastapi|django|cloud|automation))",
    re.I,
)
_TECH_SKILL_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("Python", re.compile(r"(?<!\w)python(?:3)?(?!\w)|بايثون", re.I)),
    ("SQL", re.compile(r"(?<!\w)(?:sql|postgres|mysql|t-sql)(?!\w)|قواعد البيانات?", re.I)),
    ("FastAPI", re.compile(r"(?<!\w)fastapi(?!\w)", re.I)),
    ("Django", re.compile(r"(?<!\w)django(?!\w)", re.I)),
    ("Java", re.compile(r"(?<!\w)java(?!script)(?!\w)", re.I)),
    ("JavaScript", re.compile(r"(?<!\w)(?:javascript|typescript|node\.?js)(?!\w)", re.I)),
    ("Frontend", re.compile(r"(?<!\w)(?:react|angular|vue)(?:\.?js)?(?!\w)", re.I)),
    ("Cloud", re.compile(r"(?<!\w)(?:aws|azure|gcp|cloud)(?!\w)", re.I)),
    ("Containers", re.compile(r"(?<!\w)(?:docker|kubernetes)(?!\w)", re.I)),
    ("Systems", re.compile(r"(?<!\w)(?:linux|git|api|apis)(?!\w)", re.I)),
    ("Data/AI", re.compile(r"machine learning|data engineering|cybersecurity|أمن سيبراني", re.I)),
)
_TECH_WORK_CONTEXT_RE = re.compile(
    r"(daily|years? of experience|experience (?:with|using|in)|project|intern|bootcamp|"
    r"built|developed|implemented|maintained|deployed|employment|worked (?:with|on|as)|"
    r"يومي|خبرة|مشروع|تدريب)",
    re.I,
)
_NON_TECH_PRIMARY_RE = re.compile(
    r"(accountant|accounting|finance|treasury|audit|hr generalist|human resources|recruiter|"
    r"employee relations|operations manager|operations coordinator|warehouse|supply chain|"
    r"sales|marketing|office administrator|محاسب|موارد بشرية|توظيف|مبيعات|تسويق|تشغيل)",
    re.I,
)

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS taxonomy_releases (
  taxonomy_version text PRIMARY KEY,
  label_en text NOT NULL,
  label_ar text NOT NULL,
  immutable boolean NOT NULL DEFAULT true,
  pack_json jsonb NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS taxonomy_nodes (
  taxonomy_version text NOT NULL REFERENCES taxonomy_releases(taxonomy_version),
  node_id text NOT NULL,
  node_type text NOT NULL,
  label_en text NOT NULL,
  label_ar text NOT NULL,
  aliases jsonb NOT NULL DEFAULT '[]'::jsonb,
  parent_ids jsonb NOT NULL DEFAULT '[]'::jsonb,
  status text NOT NULL DEFAULT 'active',
  PRIMARY KEY (taxonomy_version, node_id)
);

CREATE TABLE IF NOT EXISTS taxonomy_tenant_nodes (
  company_code text NOT NULL,
  node_id text NOT NULL,
  node_type text NOT NULL,
  label_en text NOT NULL,
  label_ar text NOT NULL,
  aliases jsonb NOT NULL DEFAULT '[]'::jsonb,
  maps_to_canonical_node_id text,
  status text NOT NULL DEFAULT 'active',
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (company_code, node_id)
);

CREATE TABLE IF NOT EXISTS candidate_classification_runs (
  run_id uuid PRIMARY KEY,
  company_code text NOT NULL,
  app_key text NOT NULL,
  document_version_id text,
  extraction_version_id text,
  taxonomy_version text NOT NULL,
  classifier_version text NOT NULL,
  idempotency_key text NOT NULL,
  status text NOT NULL,
  refusal_reason text,
  input_bundle_hash text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (company_code, idempotency_key)
);
CREATE INDEX IF NOT EXISTS idx_class_runs_company_app
  ON candidate_classification_runs(company_code, app_key, created_at DESC);

CREATE TABLE IF NOT EXISTS candidate_classification_suggestions (
  suggestion_id uuid PRIMARY KEY,
  run_id uuid NOT NULL REFERENCES candidate_classification_runs(run_id),
  company_code text NOT NULL,
  app_key text NOT NULL,
  node_id text NOT NULL,
  node_type text NOT NULL,
  confidence_score double precision NOT NULL,
  confidence_band text NOT NULL,
  evidence jsonb NOT NULL DEFAULT '[]'::jsonb,
  state text NOT NULL DEFAULT 'active',
  created_at timestamptz NOT NULL DEFAULT now(),
  CHECK (confidence_band IN ('High','Medium','Needs review')),
  CHECK (jsonb_array_length(evidence) > 0)
);
CREATE INDEX IF NOT EXISTS idx_class_suggestions_company_app
  ON candidate_classification_suggestions(company_code, app_key, state);

CREATE TABLE IF NOT EXISTS candidate_classification_run_invalidations (
  invalidation_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  company_code text NOT NULL,
  run_id uuid NOT NULL,
  reason_code text NOT NULL,
  source_resolution_id uuid,
  source_document_id text,
  invalidated_by text NOT NULL,
  evidence jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (company_code, run_id, reason_code)
);
CREATE INDEX IF NOT EXISTS idx_class_run_invalidations_lookup
  ON candidate_classification_run_invalidations(company_code, run_id, created_at DESC);

CREATE TABLE IF NOT EXISTS candidate_classification_review_events (
  event_id uuid PRIMARY KEY,
  company_code text NOT NULL,
  app_key text NOT NULL,
  action text NOT NULL,
  node_id text NOT NULL,
  previous_node_id text,
  suggestion_id uuid,
  reason text,
  actor_user_id text,
  actor_email text,
  supersedes_event_id uuid,
  created_at timestamptz NOT NULL DEFAULT now(),
  CHECK (action IN ('confirm','reject','add','correct','supersede'))
);
CREATE INDEX IF NOT EXISTS idx_class_review_company_app
  ON candidate_classification_review_events(company_code, app_key, created_at DESC);

CREATE TABLE IF NOT EXISTS talent_pool_classification_jobs (
  job_id uuid PRIMARY KEY,
  company_code text NOT NULL,
  app_key text NOT NULL,
  job_type text NOT NULL DEFAULT 'talent_pool_classify_v1',
  idempotency_key text NOT NULL,
  status text NOT NULL,
  attempt_count integer NOT NULL DEFAULT 0,
  last_error text,
  dead_letter boolean NOT NULL DEFAULT false,
  payload jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (company_code, idempotency_key)
);
CREATE INDEX IF NOT EXISTS idx_tpc_jobs_status
  ON talent_pool_classification_jobs(company_code, status, created_at);
"""


def _truthy(raw: str | None) -> bool:
    return str(raw or "").strip().lower() in {"1", "true", "on", "yes"}


def _env(environ: dict[str, str] | None = None) -> dict[str, str]:
    return environ if environ is not None else os.environ


def feature_master_enabled(environ: dict[str, str] | None = None) -> bool:
    return _truthy(_env(environ).get(FEATURE_MASTER))


def feature_allowed_tenants(environ: dict[str, str] | None = None) -> set[str]:
    raw = str(_env(environ).get(FEATURE_TENANTS) or "").strip()
    if not raw:
        return set()
    return {part.strip().upper() for part in raw.split(",") if part.strip()}


def feature_schema_enabled(environ: dict[str, str] | None = None) -> bool:
    return _truthy(_env(environ).get(FEATURE_SCHEMA))


def feature_manual_enabled(environ: dict[str, str] | None = None) -> bool:
    return _truthy(_env(environ).get(FEATURE_MANUAL))


def feature_workers_enabled(environ: dict[str, str] | None = None) -> bool:
    return _truthy(_env(environ).get(FEATURE_WORKERS))


def feature_ui_enabled(environ: dict[str, str] | None = None) -> bool:
    return _truthy(_env(environ).get(FEATURE_UI))


def feature_enabled_for_company(company_code: str | None, environ: dict[str, str] | None = None) -> bool:
    """Tenant enablement is independent of Unified Candidates flags.

    Empty TENANTS => nobody. Master alone never enables all tenants.
    Schema/manual/UI still require company on allowlist for mutations/reads that
    are tenant-scoped; schema bootstrap may run when SCHEMA=on locally.
    """
    company = str(company_code or "").strip().upper()
    if not company:
        return False
    return company in feature_allowed_tenants(environ)


def feature_status(company_code: str | None = None, environ: dict[str, str] | None = None) -> dict[str, Any]:
    company = str(company_code or "").strip().upper() or None
    enabled = feature_enabled_for_company(company, environ) if company else False
    return {
        "flag": FEATURE_MASTER,
        "master_enabled": feature_master_enabled(environ),
        "allowed_tenants": sorted(feature_allowed_tenants(environ)),
        "company_code": company,
        "enabled_for_company": enabled,
        "schema_enabled": feature_schema_enabled(environ),
        "manual_enabled": feature_manual_enabled(environ),
        "workers_enabled": feature_workers_enabled(environ),
        "ui_enabled": feature_ui_enabled(environ),
        "classifier_version": CLASSIFIER_VERSION,
        "coupled_to_unified_candidates": False,
    }


def assert_workers_disabled_for_local(environ: dict[str, str] | None = None) -> None:
    if feature_workers_enabled(environ):
        raise RuntimeError("background_classification_workers_must_remain_off_in_this_phase")


def score_to_band(score: float) -> str:
    if score >= _HIGH_MIN:
        return BAND_HIGH
    if score >= _MEDIUM_MIN:
        return BAND_MEDIUM
    if score >= 0.40:
        return BAND_NEEDS_REVIEW
    return BAND_NEEDS_REVIEW


def load_taxonomy_pack(path: Path | None = None) -> dict[str, Any]:
    pack_path = path or TAXONOMY_PACK_PATH
    data = json.loads(pack_path.read_text(encoding="utf-8"))
    if not data.get("taxonomy_version") or not isinstance(data.get("nodes"), list):
        raise ValueError("invalid_taxonomy_pack")
    return data


def taxonomy_index(pack: dict[str, Any] | None = None) -> dict[str, dict[str, Any]]:
    pack = pack or load_taxonomy_pack()
    return {str(n["node_id"]): n for n in pack.get("nodes") or [] if n.get("node_id")}


def ensure_classification_schema(cur: Any) -> None:
    cur.execute(SCHEMA_SQL)
    # Additive review metadata for Add/Correct without rewriting immutable runs.
    cur.execute(
        """
        ALTER TABLE candidate_classification_review_events
          ADD COLUMN IF NOT EXISTS node_type text,
          ADD COLUMN IF NOT EXISTS label_en text,
          ADD COLUMN IF NOT EXISTS label_ar text
        """
    )
    # Help list filters resolve current suggestions by app without N+1 scans.
    cur.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_class_suggestions_company_app_node
          ON candidate_classification_suggestions(company_code, app_key, node_id, state)
        """
    )
    cur.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_class_review_company_app_node
          ON candidate_classification_review_events(company_code, app_key, node_id, action, created_at DESC)
        """
    )


def seed_global_taxonomy(cur: Any, pack: dict[str, Any] | None = None) -> str:
    pack = pack or load_taxonomy_pack()
    version = str(pack["taxonomy_version"])
    ensure_classification_schema(cur)
    cur.execute(
        """
        INSERT INTO taxonomy_releases(taxonomy_version, label_en, label_ar, immutable, pack_json)
        VALUES (%s,%s,%s,true,%s::jsonb)
        ON CONFLICT (taxonomy_version) DO NOTHING
        """,
        (version, pack.get("label_en") or version, pack.get("label_ar") or version, json.dumps(pack)),
    )
    for node in pack.get("nodes") or []:
        cur.execute(
            """
            INSERT INTO taxonomy_nodes(
              taxonomy_version, node_id, node_type, label_en, label_ar, aliases, parent_ids, status
            ) VALUES (%s,%s,%s,%s,%s,%s::jsonb,%s::jsonb,'active')
            ON CONFLICT (taxonomy_version, node_id) DO NOTHING
            """,
            (
                version,
                node["node_id"],
                node["node_type"],
                node["label_en"],
                node["label_ar"],
                json.dumps(node.get("aliases") or []),
                json.dumps(node.get("parent_ids") or []),
            ),
        )
    return version


def upsert_tenant_node(
    cur: Any,
    *,
    company_code: str,
    node_id: str,
    node_type: str,
    label_en: str,
    label_ar: str,
    aliases: list[str] | None = None,
    maps_to_canonical_node_id: str | None = None,
) -> dict[str, Any]:
    company = str(company_code or "").strip().upper()
    nid = str(node_id or "").strip()
    if not company or not nid.startswith(f"tenant.{company}."):
        raise ValueError("tenant_node_id_must_be_namespaced")
    ensure_classification_schema(cur)
    cur.execute(
        """
        INSERT INTO taxonomy_tenant_nodes(
          company_code, node_id, node_type, label_en, label_ar, aliases, maps_to_canonical_node_id, updated_at
        ) VALUES (%s,%s,%s,%s,%s,%s::jsonb,%s,now())
        ON CONFLICT (company_code, node_id) DO UPDATE SET
          label_en=EXCLUDED.label_en,
          label_ar=EXCLUDED.label_ar,
          aliases=EXCLUDED.aliases,
          maps_to_canonical_node_id=EXCLUDED.maps_to_canonical_node_id,
          updated_at=now()
        """,
        (
            company,
            nid,
            node_type,
            label_en,
            label_ar,
            json.dumps(aliases or []),
            maps_to_canonical_node_id,
        ),
    )
    return {
        "company_code": company,
        "node_id": nid,
        "node_type": node_type,
        "label_en": label_en,
        "label_ar": label_ar,
        "maps_to_canonical_node_id": maps_to_canonical_node_id,
    }


def build_input_bundle(
    *,
    cv_text: str,
    facts: dict[str, Any] | None,
    hr_confirmed_facts: dict[str, Any] | None,
    document_version_id: str | None,
    extraction_version_id: str | None,
    completeness: list[dict[str, Any]] | None = None,
    embedding_present: bool = False,
) -> dict[str, Any]:
    return {
        "cv_text": str(cv_text or ""),
        "facts": facts if isinstance(facts, dict) else {},
        "hr_confirmed_facts": hr_confirmed_facts if isinstance(hr_confirmed_facts, dict) else {},
        "document_version_id": document_version_id,
        "extraction_version_id": extraction_version_id,
        "completeness": completeness or [],
        "embedding_present": bool(embedding_present),
        "ocr_rerun": False,
    }


def input_bundle_hash(bundle: dict[str, Any]) -> str:
    payload = json.dumps(bundle, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def idempotency_key(
    *,
    company_code: str,
    app_key: str,
    document_version_id: str | None,
    extraction_version_id: str | None,
    taxonomy_version: str,
    classifier_version: str,
    bundle_hash: str,
) -> str:
    raw = "|".join(
        [
            str(company_code or "").upper(),
            str(app_key or ""),
            str(document_version_id or ""),
            str(extraction_version_id or ""),
            str(taxonomy_version or ""),
            str(classifier_version or ""),
            str(bundle_hash or ""),
        ]
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _blob_from_facts(facts: dict[str, Any]) -> str:
    parts: list[str] = []
    for key in ("skills", "languages", "certifications", "summary", "title"):
        val = facts.get(key)
        if isinstance(val, list):
            parts.extend(str(x) for x in val)
        elif val:
            parts.append(str(val))
    for key in ("employment", "education"):
        items = facts.get(key)
        if isinstance(items, list):
            parts.append(json.dumps(items, ensure_ascii=False))
    return " ".join(parts)


def assess_refusal(bundle: dict[str, Any]) -> str | None:
    text = str(bundle.get("cv_text") or "").strip()
    facts = bundle.get("facts") if isinstance(bundle.get("facts"), dict) else {}
    hr = bundle.get("hr_confirmed_facts") if isinstance(bundle.get("hr_confirmed_facts"), dict) else {}
    fact_blob = (_blob_from_facts(facts) + " " + _blob_from_facts(hr)).strip()
    has_role_cue = bool(_ROLE_CUE_RE.search(text)) or bool(_ROLE_CUE_RE.search(fact_blob))
    if len(text) < _MIN_TEXT_CHARS and len(fact_blob) < 20 and not has_role_cue:
        return "insufficient_text_and_facts"
    if len(text) < 120 and not has_role_cue and len(fact_blob) < 40:
        return "identity_only_or_low_information"
    completeness = bundle.get("completeness") if isinstance(bundle.get("completeness"), list) else []
    low_sections = sum(1 for c in completeness if str(c.get("state") or "") in {"not_extracted", "incomplete", "low"})
    if low_sections >= 4 and len(text) < 120 and not has_role_cue:
        return "extraction_completeness_too_low"
    if bundle.get("ocr_rerun"):
        return "ocr_rerun_forbidden"
    return None


def _find_evidence(haystack: str, alias: str) -> dict[str, Any] | None:
    if not alias or not haystack:
        return None
    escaped = re.escape(alias)
    prefix = r"(?<!\w)" if alias[0].isalnum() else ""
    suffix = r"(?!\w)" if alias[-1].isalnum() else ""
    pattern = re.compile(f"{prefix}{escaped}{suffix}", re.IGNORECASE)
    match = pattern.search(haystack)
    if not match:
        return None
    start = max(0, match.start() - 40)
    end = min(len(haystack), match.end() + 40)
    quote = haystack[start:end].strip()
    return {
        "evidence_kind": "cv_text",
        "quote": quote[:240],
        "matched_alias": alias,
        "start": match.start(),
        "end": match.end(),
    }


def _pattern_evidence(
    source: str,
    pattern: re.Pattern[str],
    *,
    evidence_kind: str,
    support_category: str,
    matched_alias: str | None = None,
) -> dict[str, Any] | None:
    match = pattern.search(source)
    if not match:
        return None
    start = max(0, match.start() - 40)
    end = min(len(source), match.end() + 40)
    return {
        "evidence_kind": evidence_kind,
        "quote": source[start:end].strip()[:240],
        "matched_alias": matched_alias or match.group(0),
        "support_category": support_category,
        "start": match.start(),
        "end": match.end(),
    }


def _technology_evidence(
    text: str,
    facts: dict[str, Any],
    hr: dict[str, Any],
) -> tuple[float, list[dict[str, Any]]]:
    """Score broad Technology only from meaningful, attributable support.

    Generic references to software, IT, digital tools, or business systems are
    intentionally insufficient. A role/education/project anchor, or sustained
    technical skills in work context, is required.
    """
    evidence: list[dict[str, Any]] = []
    best_score = 0.0
    text_has_non_tech_primary = bool(_NON_TECH_PRIMARY_RE.search(text))
    sources = (
        ("cv_text", text, 0.0),
        ("extracted_fact", _blob_from_facts(facts), -0.08),
        ("hr_confirmed_fact", _blob_from_facts(hr), 0.08),
    )
    for evidence_kind, source, source_adjustment in sources:
        if not source:
            continue
        source_evidence: list[dict[str, Any]] = []
        role = _pattern_evidence(
            source,
            _TECH_ROLE_RE,
            evidence_kind=evidence_kind,
            support_category="technical_role",
        )
        education = _pattern_evidence(
            source,
            _TECH_EDUCATION_RE,
            evidence_kind=evidence_kind,
            support_category="technical_education",
        )
        project = _pattern_evidence(
            source,
            _TECH_PROJECT_RE,
            evidence_kind=evidence_kind,
            support_category="technical_project_or_employment",
        )
        for item in (role, education, project):
            if item:
                source_evidence.append(item)

        skill_evidence: list[dict[str, Any]] = []
        for label, pattern in _TECH_SKILL_PATTERNS:
            item = _pattern_evidence(
                source,
                pattern,
                evidence_kind=evidence_kind,
                support_category="technical_skill",
                matched_alias=label,
            )
            if item:
                skill_evidence.append(item)

        source_score = 0.0
        if role or education:
            source_score = 0.82 + source_adjustment
        elif project:
            source_score = (
                0.64 if evidence_kind == "cv_text" and text_has_non_tech_primary else 0.78
            ) + source_adjustment
        elif len(skill_evidence) >= 2:
            # A supported secondary Technology area remains useful, but a
            # clearly non-technical primary profile should not be displaced.
            source_score = (0.60 if evidence_kind == "cv_text" and text_has_non_tech_primary else 0.74)
            source_score += source_adjustment
        elif len(skill_evidence) == 1 and _TECH_WORK_CONTEXT_RE.search(source):
            source_score = 0.58 + source_adjustment

        if source_score >= _NEEDS_REVIEW_MIN:
            evidence.extend(source_evidence)
            evidence.extend(skill_evidence[:3])
            best_score = max(best_score, source_score)

    # Corroboration across stored text and structured facts can lift a useful
    # Medium suggestion, but never manufactures evidence.
    kinds = {item["evidence_kind"] for item in evidence}
    if "cv_text" in kinds and kinds.intersection({"extracted_fact", "hr_confirmed_fact"}):
        best_score = min(0.95, best_score + 0.06)

    deduped: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()
    for item in evidence:
        key = (
            str(item.get("evidence_kind") or ""),
            str(item.get("support_category") or ""),
            str(item.get("matched_alias") or "").lower(),
        )
        if key in seen:
            continue
        seen.add(key)
        deduped.append(item)
    return best_score, deduped[:5]


def _find_fact_evidence(facts: dict[str, Any], alias: str, *, confirmed: bool) -> dict[str, Any] | None:
    blob = json.dumps(facts, ensure_ascii=False)
    if alias.lower() not in blob.lower():
        return None
    return {
        "evidence_kind": "hr_confirmed_fact" if confirmed else "extracted_fact",
        "quote": alias,
        "matched_alias": alias,
        "fact_path": "skills" if "skill" in str(facts.keys()) else "profile",
    }


def classify_bundle(
    bundle: dict[str, Any],
    *,
    pack: dict[str, Any] | None = None,
    tenant_nodes: list[dict[str, Any]] | None = None,
    classifier_version: str = CLASSIFIER_VERSION,
) -> dict[str, Any]:
    """Deterministic multi-label classifier. Never calls OCR or external LLMs.

    Graduated outcomes (evidence assessment, never candidate quality):
      Clear evidence / Multiple relevant areas / Partial evidence /
      Needs HR review / Insufficient evidence to classify
    """
    pack = pack or load_taxonomy_pack()
    taxonomy_version = str(pack["taxonomy_version"])
    refusal = assess_refusal(bundle)
    if refusal:
        return {
            "taxonomy_version": taxonomy_version,
            "classifier_version": classifier_version,
            "status": STATE_UNCLASSIFIED,
            "outcome_label": OUTCOME_INSUFFICIENT,
            "refusal_reason": refusal,
            "suggestions": [],
            "ocr_triggered": False,
        }

    text = str(bundle.get("cv_text") or "")
    facts = bundle.get("facts") if isinstance(bundle.get("facts"), dict) else {}
    hr = bundle.get("hr_confirmed_facts") if isinstance(bundle.get("hr_confirmed_facts"), dict) else {}
    nodes = list(pack.get("nodes") or [])
    for tn in tenant_nodes or []:
        nodes.append(tn)

    suggestions: list[dict[str, Any]] = []
    for node in nodes:
        node_id = str(node.get("node_id") or "")
        node_type = str(node.get("node_type") or "")
        if not node_id or not node_type:
            continue
        labels = [str(node.get("label_en") or ""), str(node.get("label_ar") or "")]
        aliases = [str(a) for a in (node.get("aliases") or []) if str(a).strip()]
        candidates = [x for x in [*labels, *aliases] if x.strip()]
        evidence: list[dict[str, Any]] = []
        score = 0.0
        if node_id == "fn.technology":
            score, evidence = _technology_evidence(text, facts, hr)
            if score < _NEEDS_REVIEW_MIN or not evidence:
                continue
            suggestions.append(
                {
                    "node_id": node_id,
                    "node_type": node_type,
                    "label_en": node.get("label_en"),
                    "label_ar": node.get("label_ar"),
                    "confidence_score": round(score, 4),
                    "confidence_band": score_to_band(score),
                    "evidence": evidence,
                    "state": STATE_ACTIVE,
                }
            )
            continue
        for alias in candidates:
            ev = _find_evidence(text, alias)
            if ev:
                evidence.append(ev)
                # Broad function matches from education/projects are still useful
                base = 0.80 if node_type in {"career_function", "likely_role", "skill"} else 0.70
                if node_type == "career_function" and len(alias) >= 8:
                    base = max(base, 0.74)
                score = max(score, base)
                continue
            evf = _find_fact_evidence(hr, alias, confirmed=True)
            if evf:
                evidence.append(evf)
                score = max(score, 0.88)
                continue
            evx = _find_fact_evidence(facts, alias, confirmed=False)
            if evx:
                evidence.append(evx)
                score = max(score, 0.60)
        if not evidence:
            continue
        kinds = {e.get("evidence_kind") for e in evidence}
        if "cv_text" in kinds and ("extracted_fact" in kinds or "hr_confirmed_fact" in kinds):
            score = min(0.95, score + 0.08)
        # Several weaker signals together can reach Medium
        if len(evidence) >= 2 and score < _MEDIUM_MIN:
            score = max(score, _MEDIUM_MIN)
        if score < _NEEDS_REVIEW_MIN:
            continue
        band = score_to_band(score)
        suggestions.append(
            {
                "node_id": node_id,
                "node_type": node_type,
                "label_en": node.get("label_en"),
                "label_ar": node.get("label_ar"),
                "confidence_score": round(score, 4),
                "confidence_band": band,
                "evidence": evidence[:5],
                "state": STATE_ACTIVE,
            }
        )

    if not suggestions:
        return {
            "taxonomy_version": taxonomy_version,
            "classifier_version": classifier_version,
            "status": STATE_UNCLASSIFIED,
            "outcome_label": OUTCOME_INSUFFICIENT,
            "refusal_reason": "no_evidence_backed_labels",
            "suggestions": [],
            "ocr_triggered": False,
        }

    high = [s for s in suggestions if s["confidence_band"] == BAND_HIGH]
    medium = [s for s in suggestions if s["confidence_band"] == BAND_MEDIUM]
    needs = [s for s in suggestions if s["confidence_band"] == BAND_NEEDS_REVIEW]
    high_functions = {s["node_id"] for s in high if s["node_type"] == "career_function"}
    med_functions = {s["node_id"] for s in medium if s["node_type"] == "career_function"}
    function_spread = high_functions | med_functions

    # Conflicting / unclear primary interpretation
    if len(function_spread) >= 3 and len(high) == 0:
        status = STATE_NEEDS_REVIEW
        outcome = OUTCOME_NEEDS_HR
    elif len(high_functions) >= 2 or (len(high) >= 2 and len(function_spread) >= 2):
        status = STATE_CLASSIFIED_MULTI
        outcome = OUTCOME_MULTI
    elif high:
        status = STATE_CLASSIFIED
        outcome = OUTCOME_CLEAR
    elif medium:
        # Medium remains usable (cautious) — do not auto-unclassify
        status = STATE_CAUTIOUS
        outcome = OUTCOME_PARTIAL
    else:
        status = STATE_NEEDS_REVIEW
        outcome = OUTCOME_NEEDS_HR

    return {
        "taxonomy_version": taxonomy_version,
        "classifier_version": classifier_version,
        "status": status,
        "outcome_label": outcome,
        "refusal_reason": None if status != STATE_UNCLASSIFIED else "insufficient_evidence",
        "suggestions": suggestions,
        "ocr_triggered": False,
    }


def compact_row_chip(
    *,
    confirmed: list[dict[str, Any]],
    suggestions: list[dict[str, Any]],
    rejected_node_ids: set[str] | None = None,
) -> str | None:
    """One compact chip only for High + evidence + current + not rejected/conflicting."""
    rejected = rejected_node_ids or set()
    # Prefer HR-confirmed function + role
    conf_fn = next((c for c in confirmed if c.get("node_type") == "career_function"), None)
    conf_role = next((c for c in confirmed if c.get("node_type") == "likely_role"), None)
    if conf_fn and conf_role:
        return f"{conf_fn.get('label_en')} · {conf_role.get('label_en')}"
    if conf_fn:
        return str(conf_fn.get("label_en") or "")
    high = [
        s
        for s in suggestions
        if s.get("confidence_band") == BAND_HIGH
        and s.get("state") == STATE_ACTIVE
        and s.get("node_id") not in rejected
        and (s.get("evidence") or [])
    ]
    fn = next((s for s in high if s.get("node_type") == "career_function"), None)
    role = next((s for s in high if s.get("node_type") == "likely_role"), None)
    if fn and role:
        return f"{fn.get('label_en')} · {role.get('label_en')}"
    if fn:
        return str(fn.get("label_en") or "")
    return None


def effective_classification(
    *,
    suggestions: list[dict[str, Any]],
    review_events: list[dict[str, Any]],
    include_medium_ai: bool = False,
) -> dict[str, Any]:
    """Project HR-confirmed vs AI-suggested layers without mixing authority."""
    rejected: set[str] = set()
    confirmed: dict[str, dict[str, Any]] = {}
    # Process events in time order
    ordered = sorted(review_events, key=lambda e: str(e.get("created_at") or ""))
    for event in ordered:
        action = str(event.get("action") or "").lower()
        node_id = str(event.get("node_id") or "")
        if not node_id:
            continue
        if action == "reject":
            rejected.add(node_id)
            confirmed.pop(node_id, None)
        elif action in {"confirm", "add"}:
            rejected.discard(node_id)
            confirmed[node_id] = {
                "node_id": node_id,
                "node_type": event.get("node_type"),
                "label_en": event.get("label_en"),
                "label_ar": event.get("label_ar"),
                "authority": "hr_confirmed",
                "event_id": event.get("event_id"),
            }
        elif action == "correct":
            prev = str(event.get("previous_node_id") or "")
            if prev:
                confirmed.pop(prev, None)
                rejected.add(prev)
            confirmed[node_id] = {
                "node_id": node_id,
                "node_type": event.get("node_type"),
                "label_en": event.get("label_en"),
                "label_ar": event.get("label_ar"),
                "authority": "hr_confirmed",
                "event_id": event.get("event_id"),
            }
        elif action == "supersede":
            prev = str(event.get("previous_node_id") or event.get("supersedes_event_id") or "")
            if prev in confirmed:
                confirmed.pop(prev, None)

    active_ai: list[dict[str, Any]] = []
    for suggestion in suggestions:
        if suggestion.get("state") not in {STATE_ACTIVE, None}:
            continue
        node_id = str(suggestion.get("node_id") or "")
        if node_id in rejected or node_id in confirmed:
            continue
        band = suggestion.get("confidence_band")
        if band == BAND_HIGH or (band == BAND_MEDIUM and include_medium_ai):
            active_ai.append({**suggestion, "authority": "ai_suggested"})

    return {
        "confirmed": list(confirmed.values()),
        "ai_suggested": active_ai,
        "rejected_node_ids": sorted(rejected),
        "chip": compact_row_chip(
            confirmed=list(confirmed.values()),
            suggestions=suggestions,
            rejected_node_ids=rejected,
        ),
    }


def append_review_event(
    *,
    action: str,
    node_id: str,
    actor_user_id: str | None,
    actor_email: str | None = None,
    suggestion_id: str | None = None,
    previous_node_id: str | None = None,
    reason: str | None = None,
    supersedes_event_id: str | None = None,
    node_type: str | None = None,
    label_en: str | None = None,
    label_ar: str | None = None,
) -> dict[str, Any]:
    action_key = str(action or "").strip().lower()
    if action_key not in REVIEW_ACTIONS:
        raise ValueError("invalid_classification_review_action")
    return {
        "event_id": str(uuid.uuid4()),
        "action": action_key,
        "node_id": node_id,
        "previous_node_id": previous_node_id,
        "suggestion_id": suggestion_id,
        "reason": reason,
        "actor_user_id": actor_user_id,
        "actor_email": actor_email,
        "supersedes_event_id": supersedes_event_id,
        "node_type": node_type,
        "label_en": label_en,
        "label_ar": label_ar,
        "created_at": "now",
    }


def persist_classification_run(
    cur: Any,
    *,
    company_code: str,
    app_key: str,
    bundle: dict[str, Any],
    result: dict[str, Any],
    document_version_id: str | None,
    extraction_version_id: str | None,
) -> dict[str, Any]:
    """Write immutable run + suggestions. Idempotent on cache key."""
    ensure_classification_schema(cur)
    company = str(company_code or "").strip().upper()
    taxonomy_version = str(result.get("taxonomy_version") or "")
    classifier_version = str(result.get("classifier_version") or CLASSIFIER_VERSION)
    bhash = input_bundle_hash(bundle)
    key = idempotency_key(
        company_code=company,
        app_key=app_key,
        document_version_id=document_version_id,
        extraction_version_id=extraction_version_id,
        taxonomy_version=taxonomy_version,
        classifier_version=classifier_version,
        bundle_hash=bhash,
    )
    cur.execute(
        """
        SELECT run_id, status FROM candidate_classification_runs
        WHERE company_code=%s AND idempotency_key=%s
        LIMIT 1
        """,
        (company, key),
    )
    existing = cur.fetchone()
    if existing:
        return {"run_id": str(existing["run_id"]), "status": existing["status"], "idempotent_hit": True, "idempotency_key": key}

    # Stale prior active suggestions for this app
    cur.execute(
        """
        UPDATE candidate_classification_suggestions
        SET state=%s
        WHERE company_code=%s AND app_key=%s AND state=%s
        """,
        (STATE_STALE, company, app_key, STATE_ACTIVE),
    )
    run_id = str(uuid.uuid4())
    status = str(result.get("status") or STATE_UNCLASSIFIED)
    cur.execute(
        """
        INSERT INTO candidate_classification_runs(
          run_id, company_code, app_key, document_version_id, extraction_version_id,
          taxonomy_version, classifier_version, idempotency_key, status, refusal_reason, input_bundle_hash
        ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
        """,
        (
            run_id,
            company,
            app_key,
            document_version_id,
            extraction_version_id,
            taxonomy_version,
            classifier_version,
            key,
            status,
            result.get("refusal_reason"),
            bhash,
        ),
    )
    stored = 0
    for suggestion in result.get("suggestions") or []:
        evidence = suggestion.get("evidence") or []
        if not evidence:
            continue
        if suggestion.get("confidence_band") not in {BAND_HIGH, BAND_MEDIUM, BAND_NEEDS_REVIEW}:
            continue
        cur.execute(
            """
            INSERT INTO candidate_classification_suggestions(
              suggestion_id, run_id, company_code, app_key, node_id, node_type,
              confidence_score, confidence_band, evidence, state
            ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb,%s)
            """,
            (
                str(uuid.uuid4()),
                run_id,
                company,
                app_key,
                suggestion["node_id"],
                suggestion["node_type"],
                float(suggestion["confidence_score"]),
                suggestion["confidence_band"],
                json.dumps(evidence),
                STATE_ACTIVE,
            ),
        )
        stored += 1
    return {
        "run_id": run_id,
        "status": status,
        "idempotent_hit": False,
        "idempotency_key": key,
        "suggestion_count": stored,
        "ocr_triggered": False,
    }


def enqueue_classification_job(
    cur: Any,
    *,
    company_code: str,
    app_key: str,
    idempotency_key_value: str,
    payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Queue row only — does not start production workers."""
    assert_workers_disabled_for_local()
    ensure_classification_schema(cur)
    company = str(company_code or "").strip().upper()
    cur.execute(
        """
        SELECT job_id, status FROM talent_pool_classification_jobs
        WHERE company_code=%s AND idempotency_key=%s
        LIMIT 1
        """,
        (company, idempotency_key_value),
    )
    existing = cur.fetchone()
    if existing:
        return {"job_id": str(existing["job_id"]), "status": existing["status"], "idempotent_hit": True}
    job_id = str(uuid.uuid4())
    cur.execute(
        """
        INSERT INTO talent_pool_classification_jobs(
          job_id, company_code, app_key, job_type, idempotency_key, status, payload
        ) VALUES (%s,%s,%s,%s,%s,'queued',%s::jsonb)
        """,
        (job_id, company, app_key, JOB_TYPE, idempotency_key_value, json.dumps(payload or {})),
    )
    return {"job_id": job_id, "status": "queued", "idempotent_hit": False}


def run_manual_classification(
    *,
    company_code: str,
    app_key: str,
    bundle: dict[str, Any],
    pack: dict[str, Any] | None = None,
    tenant_nodes: list[dict[str, Any]] | None = None,
    environ: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Local/manual execution path. Workers remain OFF."""
    assert_workers_disabled_for_local(environ)
    if not feature_manual_enabled(environ) and not feature_schema_enabled(environ):
        # Allow pure in-memory unit use without flags; callers set flags in qualify.
        pass
    if feature_workers_enabled(environ):
        raise RuntimeError("workers_forbidden")
    result = classify_bundle(bundle, pack=pack, tenant_nodes=tenant_nodes)
    result["company_code"] = str(company_code or "").strip().upper()
    result["app_key"] = app_key
    result["job_type"] = JOB_TYPE
    result["execution_mode"] = "manual"
    result["workers_started"] = False
    return result


def taxonomy_dimensions(
    pack: dict[str, Any] | None = None,
    *,
    tenant_nodes: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Taxonomy-driven filter catalog: dimensions keyed by stable node_type metadata."""
    pack = pack or load_taxonomy_pack()
    index = taxonomy_index(pack)
    by_dimension: dict[str, list[dict[str, Any]]] = {key: [] for key in FILTERABLE_DIMENSIONS}
    for node in pack.get("nodes") or []:
        node_type = str(node.get("node_type") or "")
        for dimension, expected_type in DIMENSION_TYPES.items():
            if node_type != expected_type:
                continue
            by_dimension[dimension].append(
                {
                    "node_id": node.get("node_id"),
                    "node_type": node_type,
                    "dimension": dimension,
                    "label_en": node.get("label_en"),
                    "label_ar": node.get("label_ar"),
                    "parent_ids": list(node.get("parent_ids") or []),
                    "status": "active",
                    "scope": "global",
                    "broad": not bool(node.get("parent_ids")),
                }
            )
    for node in tenant_nodes or []:
        if str(node.get("status") or "active") != "active":
            continue
        node_type = str(node.get("node_type") or "")
        for dimension, expected_type in DIMENSION_TYPES.items():
            if node_type != expected_type:
                continue
            by_dimension[dimension].append(
                {
                    "node_id": node.get("node_id"),
                    "node_type": node_type,
                    "dimension": dimension,
                    "label_en": node.get("label_en"),
                    "label_ar": node.get("label_ar"),
                    "parent_ids": [node.get("maps_to_canonical_node_id")] if node.get("maps_to_canonical_node_id") else [],
                    "status": "active",
                    "scope": "tenant",
                    "broad": False,
                }
            )
    return {
        "taxonomy_version": pack.get("taxonomy_version"),
        "dimensions": [
            {
                "dimension": dimension,
                "node_type": DIMENSION_TYPES[dimension],
                "nodes": by_dimension[dimension],
            }
            for dimension in FILTERABLE_DIMENSIONS
        ],
        "authorities": list(AUTHORITY_FILTERS),
        "confidence_states": [BAND_HIGH, BAND_MEDIUM, BAND_NEEDS_REVIEW, "Unclassified"],
        "node_index": {
            node_id: {
                "node_id": node_id,
                "node_type": node.get("node_type"),
                "label_en": node.get("label_en"),
                "label_ar": node.get("label_ar"),
                "status": "active",
            }
            for node_id, node in index.items()
        },
    }


def parse_classification_filter_query(raw: dict[str, Any] | None) -> dict[str, Any]:
    """Normalize a taxonomy-driven filter payload.

    Contract:
      - dimension_nodes: {dimension: [node_id, ...]}  OR within dimension, AND across
      - node_ids: optional flat list (treated as OR across any dimension)
      - authority: confirmed_only | ai_suggested | confirmed_or_high_ai | either
      - confidence: High | Medium | Needs review | Unclassified | needs_review
      - include_medium_ai: bool
      - current_only: bool (default True for list filters)
    """
    body = raw if isinstance(raw, dict) else {}
    dimension_nodes: dict[str, list[str]] = {}
    for dimension in FILTERABLE_DIMENSIONS:
        values: list[str] = []
        for key in (dimension, f"{dimension}_ids", DIMENSION_TYPES[dimension]):
            raw_value = body.get(key)
            if isinstance(raw_value, str) and raw_value.strip():
                values.extend(part.strip() for part in raw_value.split(",") if part.strip())
            elif isinstance(raw_value, list):
                values.extend(str(part).strip() for part in raw_value if str(part).strip())
        # legacy single-field aliases from earlier UI
        legacy = {
            "career_area": "careerArea",
            "likely_role": "likelyRole",
            "experience_band": "experienceBand",
        }.get(dimension)
        if legacy and body.get(legacy):
            values.append(str(body.get(legacy)).strip())
        if values:
            dimension_nodes[dimension] = list(dict.fromkeys(values))

    nested = body.get("dimension_nodes") if isinstance(body.get("dimension_nodes"), dict) else {}
    for dimension, raw_value in nested.items():
        if dimension not in DIMENSION_TYPES:
            continue
        values = []
        if isinstance(raw_value, str) and raw_value.strip():
            values = [part.strip() for part in raw_value.split(",") if part.strip()]
        elif isinstance(raw_value, list):
            values = [str(part).strip() for part in raw_value if str(part).strip()]
        if values:
            dimension_nodes[dimension] = list(dict.fromkeys([*(dimension_nodes.get(dimension) or []), *values]))

    flat_nodes: list[str] = []
    for key in ("node_ids", "classification_node_ids"):
        raw_value = body.get(key)
        if isinstance(raw_value, str) and raw_value.strip():
            flat_nodes.extend(part.strip() for part in raw_value.split(",") if part.strip())
        elif isinstance(raw_value, list):
            flat_nodes.extend(str(part).strip() for part in raw_value if str(part).strip())

    authority = str(body.get("authority") or body.get("classification_authority") or "confirmed_or_high_ai").strip()
    if authority not in AUTHORITY_FILTERS:
        authority = "confirmed_or_high_ai"
    confidence = str(body.get("confidence") or body.get("classification_confidence") or body.get("state") or "").strip()
    if confidence.lower() in {"needs_review", "needs-review"}:
        confidence = BAND_NEEDS_REVIEW
    if confidence.lower() == "unclassified":
        confidence = "Unclassified"
    include_medium = _truthy(str(body.get("include_medium_ai") if body.get("include_medium_ai") is not None else body.get("includeMediumAi") or ""))
    current_only = body.get("current_only")
    if current_only is None:
        current_only = True
    else:
        current_only = _truthy(str(current_only)) if not isinstance(current_only, bool) else bool(current_only)

    return {
        "schema": SAVED_VIEW_CLASSIFICATION_SCHEMA,
        "dimension_nodes": dimension_nodes,
        "node_ids": list(dict.fromkeys(flat_nodes)),
        "authority": authority,
        "confidence": confidence or None,
        "include_medium_ai": include_medium,
        "current_only": current_only,
        "active": bool(dimension_nodes or flat_nodes or confidence or authority != "confirmed_or_high_ai" or include_medium),
    }


def normalize_saved_view_classification(filters: dict[str, Any] | None) -> dict[str, Any]:
    """Versioned saved-view classification payload with deprecated-node disclosure hooks."""
    body = filters if isinstance(filters, dict) else {}
    nested = body.get("classification") if isinstance(body.get("classification"), dict) else body
    parsed = parse_classification_filter_query(nested)
    pack = load_taxonomy_pack()
    index = taxonomy_index(pack)
    known = set(index)
    selected = []
    deprecated: list[dict[str, Any]] = []
    for dimension, node_ids in parsed["dimension_nodes"].items():
        for node_id in node_ids:
            selected.append({"dimension": dimension, "node_id": node_id})
            if node_id not in known and not str(node_id).startswith("tenant."):
                deprecated.append(
                    {
                        "node_id": node_id,
                        "dimension": dimension,
                        "status": "missing_or_deprecated",
                        "message": "This taxonomy node is no longer in the active pack and will not silently map to another node.",
                    }
                )
    for node_id in parsed["node_ids"]:
        if node_id not in known and not str(node_id).startswith("tenant."):
            deprecated.append(
                {
                    "node_id": node_id,
                    "dimension": None,
                    "status": "missing_or_deprecated",
                    "message": "This taxonomy node is no longer in the active pack and will not silently map to another node.",
                }
            )
    return {
        **parsed,
        "selected": selected,
        "deprecated_nodes": deprecated,
    }


def _authority_pool(effective: dict[str, Any], authority: str, *, include_medium_ai: bool) -> list[dict[str, Any]]:
    confirmed = list(effective.get("confirmed") or [])
    ai = list(effective.get("ai_suggested") or [])
    if not include_medium_ai:
        ai = [item for item in ai if item.get("confidence_band") == BAND_HIGH]
    if authority == "confirmed_only":
        return confirmed
    if authority == "ai_suggested":
        return ai
    if authority == "confirmed_or_high_ai":
        return confirmed + [item for item in ai if item.get("confidence_band") == BAND_HIGH]
    return confirmed + ai


def filter_matches_classification(
    *,
    effective: dict[str, Any],
    career_area: str | None = None,
    likely_role: str | None = None,
    skill: str | None = None,
    industry: str | None = None,
    seniority: str | None = None,
    experience_band: str | None = None,
    confidence: str | None = None,
    authority: str = "confirmed_or_high_ai",
    dimension_nodes: dict[str, list[str]] | None = None,
    node_ids: list[str] | None = None,
    include_medium_ai: bool = False,
    run_status: str | None = None,
) -> bool:
    """Generic taxonomy filter.

    - Multiple nodes within one dimension: OR
    - Separate dimension groups: AND
    - Flat node_ids: OR across any matched evidence
    - Authority/state filters apply to the matched classification evidence pool
    """
    parsed_nodes = dict(dimension_nodes or {})
    legacy = {
        "career_area": career_area,
        "likely_role": likely_role,
        "skill": skill,
        "industry": industry,
        "seniority": seniority,
        "experience_band": experience_band,
    }
    for dimension, value in legacy.items():
        if value:
            parsed_nodes.setdefault(dimension, [])
            if str(value) not in parsed_nodes[dimension]:
                parsed_nodes[dimension].append(str(value))

    pool = _authority_pool(effective, authority, include_medium_ai=include_medium_ai)
    flat = [str(node_id) for node_id in (node_ids or []) if str(node_id).strip()]

    if confidence:
        conf = str(confidence)
        if conf.lower() == "unclassified" or conf == "Unclassified":
            if pool or (run_status and run_status not in {STATE_UNCLASSIFIED, None, ""}):
                # Unclassified means no current effective labels.
                if pool:
                    return False
            else:
                return not pool and not any(parsed_nodes.values()) and not flat
        if conf in {BAND_NEEDS_REVIEW, STATE_NEEDS_REVIEW}:
            if run_status == STATE_NEEDS_REVIEW:
                pass
            else:
                ok_band = any(str(item.get("confidence_band")) == BAND_NEEDS_REVIEW for item in pool)
                if not ok_band:
                    return False
        elif conf in {BAND_HIGH, BAND_MEDIUM}:
            ok_band = any(str(item.get("confidence_band")) == conf for item in pool)
            if conf == BAND_HIGH and effective.get("confirmed"):
                ok_band = True
            if not ok_band:
                return False

    def _pool_has_any(node_type: str | None, wanted: list[str]) -> bool:
        wanted_set = set(wanted)
        return any(
            str(item.get("node_id")) in wanted_set
            and (not node_type or item.get("node_type") == node_type)
            for item in pool
        )

    for dimension, wanted in parsed_nodes.items():
        if not wanted:
            continue
        node_type = DIMENSION_TYPES.get(dimension)
        if not _pool_has_any(node_type, wanted):
            return False

    if flat and not _pool_has_any(None, flat):
        return False

    # If only authority default with no other constraints, match everything.
    return True


def classification_filter_sql(
    *,
    company_code: str,
    filters: dict[str, Any],
    applications_alias: str = "a",
) -> tuple[str, list[Any]]:
    """Server-correct EXISTS filter over classification sidecars.

    Uses taxonomy node IDs and review-event authority, not display labels.
    Avoids N+1 by remaining a single composable SQL predicate.
    """
    company = str(company_code or "").strip().upper()
    parsed = parse_classification_filter_query(filters)
    if not parsed.get("active") and parsed.get("authority") == "confirmed_or_high_ai" and not parsed.get("confidence"):
        # Still active when confidence/authority explicitly requested via parse.active
        if not parsed.get("dimension_nodes") and not parsed.get("node_ids") and not parsed.get("confidence"):
            return "TRUE", []

    params: list[Any] = []
    clauses: list[str] = []

    # Unclassified: no current effective suggestion and no confirmed review labels.
    if str(parsed.get("confidence") or "") == "Unclassified":
        sql = f"""
        NOT EXISTS (
          SELECT 1
          FROM candidate_classification_suggestions s
          WHERE s.company_code=%s
            AND s.app_key={applications_alias}.app_key
            AND s.state='active'
            AND NOT EXISTS (
              SELECT 1 FROM candidate_classification_run_invalidations i
              WHERE i.company_code=s.company_code AND i.run_id=s.run_id
            )
        )
        AND NOT EXISTS (
          SELECT 1
          FROM candidate_classification_review_events e
          WHERE e.company_code=%s
            AND e.app_key={applications_alias}.app_key
            AND e.action IN ('confirm','add','correct')
            AND NOT EXISTS (
              SELECT 1 FROM candidate_classification_review_events later
              WHERE later.company_code=e.company_code
                AND later.app_key=e.app_key
                AND later.created_at > e.created_at
                AND (
                  (later.action='reject' AND later.node_id=e.node_id)
                  OR (later.action='correct' AND later.previous_node_id=e.node_id)
                )
            )
        )
        """
        return sql, [company, company]

    suggestion_band_sql = ""
    if parsed.get("confidence") in {BAND_HIGH, BAND_MEDIUM, BAND_NEEDS_REVIEW}:
        suggestion_band_sql = " AND s.confidence_band=%s"
    authority = parsed.get("authority") or "confirmed_or_high_ai"

    def _node_group_sql(node_ids: list[str], node_type: str | None) -> tuple[str, list[Any]]:
        if not node_ids:
            return "TRUE", []
        type_sql = " AND s.node_type=%s" if node_type else ""
        type_params: list[Any] = [node_type] if node_type else []
        confirmed_sql = f"""
        EXISTS (
          SELECT 1 FROM candidate_classification_review_events e
          WHERE e.company_code=%s
            AND e.app_key={applications_alias}.app_key
            AND e.node_id = ANY(%s)
            AND e.action IN ('confirm','add','correct')
            AND NOT EXISTS (
              SELECT 1 FROM candidate_classification_review_events later
              WHERE later.company_code=e.company_code
                AND later.app_key=e.app_key
                AND later.created_at > e.created_at
                AND (
                  (later.action='reject' AND later.node_id=e.node_id)
                  OR (later.action='correct' AND later.previous_node_id=e.node_id)
                )
            )
        )
        """
        ai_band = ""
        ai_params: list[Any] = []
        if authority == "confirmed_or_high_ai" and not parsed.get("include_medium_ai"):
            ai_band = " AND s.confidence_band=%s"
            ai_params.append(BAND_HIGH)
        elif parsed.get("confidence") in {BAND_HIGH, BAND_MEDIUM, BAND_NEEDS_REVIEW}:
            ai_band = suggestion_band_sql
            ai_params.append(parsed["confidence"])
        ai_sql = f"""
        EXISTS (
          SELECT 1 FROM candidate_classification_suggestions s
          WHERE s.company_code=%s
            AND s.app_key={applications_alias}.app_key
            AND s.state='active'
            AND s.node_id = ANY(%s)
            {type_sql}
            {ai_band}
            AND NOT EXISTS (
              SELECT 1 FROM candidate_classification_run_invalidations i
              WHERE i.company_code=s.company_code AND i.run_id=s.run_id
            )
            AND NOT EXISTS (
              SELECT 1 FROM candidate_classification_review_events e
              WHERE e.company_code=s.company_code
                AND e.app_key=s.app_key
                AND e.node_id=s.node_id
                AND e.action='reject'
            )
        )
        """
        if authority == "confirmed_only":
            return confirmed_sql, [company, node_ids]
        if authority == "ai_suggested":
            return ai_sql, [company, node_ids, *type_params, *ai_params]
        # confirmed or suggested
        return f"(({confirmed_sql}) OR ({ai_sql}))", [company, node_ids, company, node_ids, *type_params, *ai_params]

    for dimension, node_ids in (parsed.get("dimension_nodes") or {}).items():
        group_sql, group_params = _node_group_sql(node_ids, DIMENSION_TYPES.get(dimension))
        clauses.append(f"({group_sql})")
        params.extend(group_params)
    if parsed.get("node_ids"):
        group_sql, group_params = _node_group_sql(list(parsed["node_ids"]), None)
        clauses.append(f"({group_sql})")
        params.extend(group_params)

    if not clauses and parsed.get("confidence") in {BAND_HIGH, BAND_MEDIUM, BAND_NEEDS_REVIEW, STATE_NEEDS_REVIEW}:
        conf = BAND_NEEDS_REVIEW if parsed["confidence"] == STATE_NEEDS_REVIEW else parsed["confidence"]
        if authority == "confirmed_only" and conf == BAND_HIGH:
            clauses.append(
                f"""EXISTS (
                  SELECT 1 FROM candidate_classification_review_events e
                  WHERE e.company_code=%s AND e.app_key={applications_alias}.app_key
                    AND e.action IN ('confirm','add','correct')
                )"""
            )
            params.append(company)
        else:
            clauses.append(
                f"""EXISTS (
                  SELECT 1 FROM candidate_classification_suggestions s
                  WHERE s.company_code=%s AND s.app_key={applications_alias}.app_key
                    AND s.state='active' AND s.confidence_band=%s
                    AND NOT EXISTS (
                      SELECT 1 FROM candidate_classification_run_invalidations i
                      WHERE i.company_code=s.company_code AND i.run_id=s.run_id
                    )
                )"""
            )
            params.extend([company, conf])
            if conf == BAND_NEEDS_REVIEW:
                clauses[-1] = (
                    f"""(
                      EXISTS (
                        SELECT 1 FROM candidate_classification_runs r
                        WHERE r.company_code=%s AND r.app_key={applications_alias}.app_key
                          AND r.status=%s
                          AND NOT EXISTS (
                            SELECT 1 FROM candidate_classification_run_invalidations i
                            WHERE i.company_code=r.company_code AND i.run_id=r.run_id
                          )
                      )
                      OR {clauses[-1]}
                    )"""
                )
                params = [company, STATE_NEEDS_REVIEW, *params]

    if not clauses:
        return "TRUE", []
    return " AND ".join(clauses), params


def bulk_load_classification_rows(
    cur: Any,
    *,
    company_code: str,
    app_keys: list[str],
) -> dict[str, dict[str, Any]]:
    """Load current suggestions + review events for a page of apps (no N+1)."""
    company = str(company_code or "").strip().upper()
    keys = [str(key) for key in app_keys if str(key).strip()]
    if not keys:
        return {}
    ensure_classification_schema(cur)
    cur.execute(
        """
        SELECT DISTINCT ON (r.app_key)
          r.run_id, r.app_key, r.status, r.refusal_reason, r.taxonomy_version,
          r.classifier_version, r.document_version_id, r.extraction_version_id,
          r.created_at
        FROM candidate_classification_runs r
        WHERE r.company_code=%s AND r.app_key = ANY(%s)
          AND NOT EXISTS (
            SELECT 1 FROM candidate_classification_run_invalidations i
            WHERE i.company_code=r.company_code AND i.run_id=r.run_id
          )
        ORDER BY r.app_key, r.created_at DESC
        """,
        (company, keys),
    )
    runs = {str(row["app_key"]): dict(row) for row in cur.fetchall()}
    cur.execute(
        """
        SELECT i.*, r.app_key
        FROM candidate_classification_run_invalidations i
        JOIN candidate_classification_runs r
          ON r.company_code=i.company_code AND r.run_id=i.run_id
        WHERE i.company_code=%s AND r.app_key = ANY(%s)
        ORDER BY i.created_at DESC
        """,
        (company, keys),
    )
    invalidations_by_run: dict[str, list[dict[str, Any]]] = {}
    invalidations_by_app: dict[str, list[dict[str, Any]]] = {
        key: [] for key in keys
    }
    for row in cur.fetchall():
        item = dict(row)
        invalidations_by_run.setdefault(
            str(item.get("run_id") or ""), []
        ).append(item)
        invalidations_by_app.setdefault(
            str(item.get("app_key") or ""), []
        ).append(item)
    cur.execute(
        """
        SELECT *
        FROM candidate_classification_suggestions
        WHERE company_code=%s AND app_key = ANY(%s)
        ORDER BY created_at DESC
        """,
        (company, keys),
    )
    suggestions_by_app: dict[str, list[dict[str, Any]]] = {key: [] for key in keys}
    for row in cur.fetchall():
        item = dict(row)
        invalidations = invalidations_by_run.get(str(item.get("run_id") or ""), [])
        if invalidations:
            item["invalidated"] = True
            item["invalidations"] = invalidations
        suggestions_by_app.setdefault(str(item.get("app_key")), []).append(item)
    cur.execute(
        """
        SELECT *
        FROM candidate_classification_review_events
        WHERE company_code=%s AND app_key = ANY(%s)
        ORDER BY created_at ASC
        """,
        (company, keys),
    )
    reviews_by_app: dict[str, list[dict[str, Any]]] = {key: [] for key in keys}
    for row in cur.fetchall():
        item = dict(row)
        reviews_by_app.setdefault(str(item.get("app_key")), []).append(item)

    pack = load_taxonomy_pack()
    index = taxonomy_index(pack)
    out: dict[str, dict[str, Any]] = {}
    for app_key in keys:
        suggestions = []
        for suggestion in suggestions_by_app.get(app_key) or []:
            node = index.get(str(suggestion.get("node_id") or ""), {})
            suggestions.append(
                {
                    **suggestion,
                    "label_en": suggestion.get("label_en") or node.get("label_en"),
                    "label_ar": suggestion.get("label_ar") or node.get("label_ar"),
                    "node_type": suggestion.get("node_type") or node.get("node_type"),
                }
            )
        # Prefer current/active suggestions tied to latest run when present.
        latest = runs.get(app_key)
        if latest:
            current = [
                item
                for item in suggestions
                if str(item.get("run_id")) == str(latest.get("run_id"))
                and not item.get("invalidated")
            ]
            if current:
                suggestions_for_effective = current
            else:
                suggestions_for_effective = [
                    item
                    for item in suggestions
                    if item.get("state") == STATE_ACTIVE
                    and not item.get("invalidated")
                ]
        else:
            suggestions_for_effective = [
                item
                for item in suggestions
                if item.get("state") == STATE_ACTIVE
                and not item.get("invalidated")
            ]
        reviews = reviews_by_app.get(app_key) or []
        # Enrich review events with taxonomy labels when missing from older rows.
        enriched_reviews = []
        for event in reviews:
            node = index.get(str(event.get("node_id") or ""), {})
            enriched_reviews.append(
                {
                    **event,
                    "node_type": event.get("node_type") or node.get("node_type"),
                    "label_en": event.get("label_en") or node.get("label_en"),
                    "label_ar": event.get("label_ar") or node.get("label_ar"),
                }
            )
        effective = effective_classification(
            suggestions=suggestions_for_effective,
            review_events=enriched_reviews,
            include_medium_ai=True,
        )
        out[app_key] = {
            "run": latest,
            "suggestions": suggestions_for_effective,
            "all_suggestions": suggestions,
            "review_events": enriched_reviews,
            "invalidations": invalidations_by_app.get(app_key) or [],
            "effective": effective,
            "projection": row_classification_projection(effective=effective, run=latest),
        }
    return out


def row_classification_projection(
    *,
    effective: dict[str, Any],
    run: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Compact Candidates-table projection from sidecars only."""
    confirmed = list(effective.get("confirmed") or [])
    ai = list(effective.get("ai_suggested") or [])
    node_ids = sorted(
        {
            str(item.get("node_id"))
            for item in [*confirmed, *ai]
            if item.get("node_id")
        }
    )
    status = str((run or {}).get("status") or (STATE_UNCLASSIFIED if not node_ids else STATE_CLASSIFIED))
    return {
        "classification_chip": effective.get("chip"),
        "classification_chip_confirmed": bool(confirmed) and bool(effective.get("chip")),
        "classification_state": status,
        "classification_authority_summary": {
            "confirmed_count": len(confirmed),
            "ai_suggested_count": len(ai),
            "rejected_count": len(effective.get("rejected_node_ids") or []),
        },
        "classification_node_ids": node_ids,
    }


def search_match_reasons_for_classification(
    *,
    query: str,
    effective: dict[str, Any],
    suggestions: list[dict[str, Any]] | None = None,
) -> list[str]:
    q = str(query or "").strip().lower()
    if not q:
        return []
    reasons: list[str] = []
    for item in effective.get("confirmed") or []:
        blob = json.dumps(item, ensure_ascii=False).lower()
        if q in blob:
            reasons.append(MATCH_CONFIRMED_CLASSIFICATION)
            break
    for item in effective.get("ai_suggested") or []:
        blob = json.dumps(item, ensure_ascii=False).lower()
        if q in blob:
            reasons.append(MATCH_AI_SUGGESTED_CLASSIFICATION)
            break
    for suggestion in suggestions or []:
        for evidence in suggestion.get("evidence") or []:
            if q in json.dumps(evidence, ensure_ascii=False).lower():
                reasons.append(MATCH_CLASSIFICATION_EVIDENCE)
                break
        if MATCH_CLASSIFICATION_EVIDENCE in reasons:
            break
    return list(dict.fromkeys(reasons))


def profile_classification_section(
    *,
    run: dict[str, Any] | None,
    suggestions: list[dict[str, Any]],
    review_events: list[dict[str, Any]],
    pack: dict[str, Any] | None = None,
    runs: list[dict[str, Any]] | None = None,
    runs_total: int | None = None,
    runs_offset: int = 0,
    runs_limit: int = 20,
    invalidations: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    pack = pack or load_taxonomy_pack()
    index = taxonomy_index(pack)
    all_invalidations = list(invalidations or [])
    invalidations_by_run: dict[str, list[dict[str, Any]]] = {}
    for item in all_invalidations:
        invalidations_by_run.setdefault(
            str(item.get("run_id") or ""), []
        ).append(item)
    for item in runs or []:
        embedded = item.get("invalidations")
        if isinstance(embedded, list):
            invalidations_by_run.setdefault(
                str(item.get("run_id") or ""), []
            ).extend(
                dict(value) for value in embedded if isinstance(value, dict)
            )
    enriched = []
    for suggestion in suggestions:
        if (
            suggestion.get("invalidated")
            or str(suggestion.get("run_id") or "") in invalidations_by_run
        ):
            continue
        node = index.get(str(suggestion.get("node_id") or ""), {})
        enriched.append(
            {
                **suggestion,
                "label_en": suggestion.get("label_en") or node.get("label_en"),
                "label_ar": suggestion.get("label_ar") or node.get("label_ar"),
                "node_type": suggestion.get("node_type") or node.get("node_type"),
            }
        )
    enriched_reviews = []
    for event in review_events:
        node = index.get(str(event.get("node_id") or ""), {})
        enriched_reviews.append(
            {
                **event,
                "node_type": event.get("node_type") or node.get("node_type"),
                "label_en": event.get("label_en") or node.get("label_en"),
                "label_ar": event.get("label_ar") or node.get("label_ar"),
            }
        )
    effective = effective_classification(suggestions=enriched, review_events=enriched_reviews, include_medium_ai=True)
    current_run = run
    if current_run and str(current_run.get("run_id") or "") in invalidations_by_run:
        current_run = None
    if not current_run:
        current_run = next(
            (
                item
                for item in (runs or [])
                if str(item.get("run_id") or "") not in invalidations_by_run
            ),
            None,
        )
    status = (current_run or {}).get("status") or (STATE_UNCLASSIFIED if not enriched else "classified")
    run_rows = []
    for item in runs or ([current_run] if current_run else []):
        if not item:
            continue
        run_invalidations = invalidations_by_run.get(
            str(item.get("run_id") or ""), []
        )
        is_invalidated = bool(run_invalidations)
        is_current = (
            not is_invalidated
            and bool(current_run)
            and str(item.get("run_id")) == str(current_run.get("run_id"))
        )
        run_rows.append(
            {
                **item,
                "currency": (
                    "invalidated"
                    if is_invalidated
                    else ("current" if is_current else "stale")
                ),
                "invalidated": is_invalidated,
                "invalidations": run_invalidations,
                "document_version_id": item.get("document_version_id"),
                "extraction_version_id": item.get("extraction_version_id"),
                "taxonomy_version": item.get("taxonomy_version"),
                "classifier_version": item.get("classifier_version"),
            }
        )
    return {
        "status": status,
        "refusal_reason": (current_run or {}).get("refusal_reason"),
        "taxonomy_version": (current_run or {}).get("taxonomy_version") or pack.get("taxonomy_version"),
        "classifier_version": (current_run or {}).get("classifier_version") or CLASSIFIER_VERSION,
        "current_run": (
            next((item for item in run_rows if item["currency"] == "current"), None)
        ),
        "currency": "current" if current_run else "unclassified",
        "confirmed": effective["confirmed"],
        "ai_suggested": effective["ai_suggested"],
        "rejected_node_ids": effective["rejected_node_ids"],
        "history": enriched_reviews,
        "invalidations": all_invalidations,
        "runs": run_rows,
        "runs_total": int(runs_total if runs_total is not None else len(run_rows)),
        "runs_offset": int(runs_offset),
        "runs_limit": int(runs_limit),
        "chip": effective["chip"],
        "actions": ["confirm", "reject", "add", "correct"],
        "hiring_score": None,
        "role_profile_score": None,
        "job_assignment": None,
    }
