#!/usr/bin/env python3
"""Wave 5 C1 — KPI Registry + HR Intelligence fact/query spine (company-scoped).

Owner-approved under WAVE5_HR_INTELLIGENCE_CHARTER (2026-08-12) §0.7–§0.8.

Commercial module key: `analytics` (no duplicate).
Internal namespace: `hr_intelligence_*` tables/APIs.

C1 authority:
  - Versioned KPI Registry (draft → published → retired | blocked)
  - Typed fact spine (ingest, correction/supersession)
  - Shared evaluator (definition@version → facts → status/value + drill IDs)
  - Company settings: min_cohort_n (≥5, upward only), demographic defaults off
  - Binding headcount/FTE policy constants for later C2 (FTE blocked)

Does NOT (C1):
  - Publish workforce headcount/FTE production cards (C2)
  - Domain KPI implementations beyond spine prove metrics
  - Intelligence UI surfaces (C6)
  - Invent metrics / universal employee scores
  - Mutate Waves 1–4 domain SoT

Gates (fail-closed):
  1) WATHEFNI_HR_INTELLIGENCE_REGISTRY_C1 must be on
  2) company in WATHEFNI_HR_INTELLIGENCE_REGISTRY_COMPANIES (empty = nobody)
  3) company entitlement in hr_intelligence_c1_company_settings
  4) optional WATHEFNI_ANALYTICS_KILL
"""
from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timezone
from typing import Any

PHASE = "hr_intelligence_registry_c1"
CONTRACT_VERSION = "hr_intelligence_registry_c1_v1"
PASS_STAMP = "HR_INTELLIGENCE_REGISTRY_FULL_PASS"
COMMERCIAL_MODULE_KEY = "analytics"
INTERNAL_NAMESPACE = "hr_intelligence"
_ON = {"1", "true", "yes", "on"}

# Extensible formula kinds (C2+ register handlers; C1 remains Registry/evaluator SoT)
_FORMULA_HANDLERS: dict[str, Any] = {}

DEFAULT_MIN_COHORT_N = 5
DEFINITION_STATUSES = ("draft", "published", "retired", "blocked")
TIME_SEMANTICS = (
    "point_in_time",
    "event_count",
    "period_sum",
    "period_average",
    "rate_over_window",
    "cohort",
    "rolling_window",
)
PERMISSION_CLASSES = (
    "workforce_general",
    "workforce_sensitive_demo",
    "time_leave",
    "payroll_money",
    "performance_aggregate",
    "performance_raw",
    "talent_sensitive",
    "lifecycle_confidential",
    "platform_ops",
    "intelligence_spine",
)

HEADCOUNT_POLICY = {
    "measure": "heads",
    "pending_start_in_headcount": False,
    "pending_start_separate_future_starters_metric": True,
    "notice_period_in_headcount_until_effective_lwd_or_end": True,
    "active_on_leave_or_suspension_in_headcount": True,
    "contingent_mixed_into_employee_headcount": False,
    "fte_publishable": False,
    "fte_never_assume_one_head_equals_one_fte": True,
    "fte_requires_authoritative_standard_hours_inputs": True,
}

SPINE_FACT_COUNT_KEY = "intelligence.spine.fact_count"
SPINE_RATE_KEY = "intelligence.spine.demo_rate"
HEADCOUNT_KEY = "workforce.headcount.active_heads"
FUTURE_STARTERS_KEY = "workforce.future_starters.count"
FTE_KEY = "workforce.fte.active"

STATUS_LABELS = {
    "draft": {"en": "Draft", "ar": "مسودة"},
    "published": {"en": "Published", "ar": "منشور"},
    "retired": {"en": "Retired", "ar": "متقاعد"},
    "blocked": {"en": "Blocked", "ar": "محظور"},
    "ok": {"en": "OK", "ar": "سليم"},
    "not_applicable": {"en": "Not applicable", "ar": "غير منطبق"},
    "insufficient_data": {"en": "Insufficient data", "ar": "بيانات غير كافية"},
    "unavailable": {"en": "Unavailable", "ar": "غير متاح"},
    "suppressed": {"en": "Suppressed", "ar": "محجوب"},
    "forbidden": {"en": "Forbidden", "ar": "ممنوع"},
}



def register_formula_handler(kind: str, handler: Any) -> None:
    """Allow later slices to plug formula kinds into the shared evaluator without parallel math engines."""
    key = str(kind or "").strip().lower()
    if not key or not callable(handler):
        raise ValueError("formula handler required")
    _FORMULA_HANDLERS[key] = handler


def _env_on(name: str, default: str = "off") -> bool:
    return (os.environ.get(name) or default).strip().lower() in _ON


def _digits(value: Any) -> str:
    return "".join(ch for ch in str(value or "") if ch.isdigit())


def company_code_norm(company_code: str | None) -> str:
    return str(company_code or "").strip().upper()


def status_label(status: str | None, *, lang: str = "en") -> str:
    key = str(status or "").strip().lower()
    pack = STATUS_LABELS.get(key) or {"en": key or "unknown", "ar": key or "غير معروف"}
    return str(pack.get("ar" if lang.lower().startswith("ar") else "en"))


def honesty_payload(*, company_code: str | None = None) -> dict[str, Any]:
    return {
        "phase": PHASE,
        "contract_version": CONTRACT_VERSION,
        "pass_stamp": PASS_STAMP,
        "commercial_module_key": COMMERCIAL_MODULE_KEY,
        "internal_namespace": INTERNAL_NAMESPACE,
        "no_duplicate_commercial_module": True,
        "assistant_mutations": False,
        "registry_is_authority": True,
        "formula_handlers_extensible": True,
        "no_card_without_published_definition": True,
        "domain_modules_remain_sot": True,
        "no_universal_employee_score": True,
        "no_talent_score": True,
        "no_workforce_score": True,
        "min_cohort_n_default": DEFAULT_MIN_COHORT_N,
        "min_cohort_n_upward_only": True,
        "complementary_suppression_required": True,
        "demographics_off_by_default": True,
        "nationality_explicit_kw_compliance_only": True,
        "demographics_never_talent_performance_scoring_inputs": True,
        "fte_blocked_until_authoritative_inputs": True,
        "fte_never_assume_one_head_equals_one_fte": True,
        "pending_start_excluded_from_headcount": True,
        "ops_attention_not_intelligence": True,
        "headcount_policy": dict(HEADCOUNT_POLICY),
        "company_code": company_code_norm(company_code) if company_code else None,
    }


def rollback_guidance() -> dict[str, Any]:
    return {
        "phase": PHASE,
        "preserves_history": True,
        "does_not_mutate_domain_sot": True,
        "steps": [
            "WATHEFNI_HR_INTELLIGENCE_REGISTRY_C1=off",
            "Clear WATHEFNI_HR_INTELLIGENCE_REGISTRY_COMPANIES",
            "WATHEFNI_ANALYTICS_KILL=on (optional immediate block)",
            "Disable company Setup entitlement (preserves registry/evaluation history)",
        ],
    }


def slice_allowlist_admits(company: str, env_name: str) -> bool:
    """Empty slice allowlist admits after R6 when analytics is catalog-enableable."""
    raw = str(os.environ.get(env_name) or "").strip()
    allow = {p.strip().upper() for p in raw.split(",") if p.strip()} if raw else set()
    try:
        import capability_readiness as _ready

        return _ready.hr_intelligence_runtime_allowlist_admits(company, allow)
    except Exception:
        return bool(allow) and company in allow


def runtime_gate_for_company(company_code: str | None) -> dict[str, Any]:
    company = company_code_norm(company_code)
    if not company:
        return {"ok": False, "enabled": False, "error": "company_required", "phase": PHASE}
    if _env_on("WATHEFNI_ANALYTICS_KILL", "off"):
        return {"ok": False, "enabled": False, "error": "analytics_kill_switch", "gate": "kill", "phase": PHASE}
    if not _env_on("WATHEFNI_HR_INTELLIGENCE_REGISTRY_C1", "off"):
        return {
            "ok": False,
            "enabled": False,
            "error": "hr_intelligence_registry_c1_off",
            "gate": "runtime_flag",
            "phase": PHASE,
        }
    raw = str(os.environ.get("WATHEFNI_HR_INTELLIGENCE_REGISTRY_COMPANIES") or "").strip()
    allow = {p.strip().upper() for p in raw.split(",") if p.strip()} if raw else set()
    try:
        import capability_readiness as _ready

        admitted = _ready.hr_intelligence_runtime_allowlist_admits(company, allow)
    except Exception:
        admitted = bool(allow) and company in allow
    if not admitted:
        return {
            "ok": False,
            "enabled": False,
            "error": "hr_intelligence_company_not_allowlisted",
            "gate": "company_allowlist",
            "phase": PHASE,
            "company_code": company,
        }
    return {"ok": True, "enabled": True, "company_code": company, "phase": PHASE}


def ensure_hr_intelligence_registry_c1_schema(cur: Any, *, force: bool = False) -> None:
    _ = force
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS hr_intelligence_c1_company_settings (
          company_code text PRIMARY KEY,
          enabled boolean NOT NULL DEFAULT false,
          min_cohort_n integer NOT NULL DEFAULT 5,
          nationality_dimension_enabled boolean NOT NULL DEFAULT false,
          other_sensitive_demographics_enabled boolean NOT NULL DEFAULT false,
          fiscal_year_start_month integer NOT NULL DEFAULT 1,
          headcount_policy jsonb NOT NULL DEFAULT '{}'::jsonb,
          enabled_by_phone text,
          enabled_reason text,
          enabled_at timestamptz,
          disabled_at timestamptz,
          updated_at timestamptz NOT NULL DEFAULT now(),
          CHECK (min_cohort_n >= 5)
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS hr_kpi_definitions (
          kpi_definition_id uuid PRIMARY KEY,
          semantic_key text NOT NULL,
          effective_version integer NOT NULL,
          status text NOT NULL,
          name_en text NOT NULL,
          name_ar text NOT NULL,
          description_en text NOT NULL,
          description_ar text NOT NULL,
          business_meaning text NOT NULL,
          numerator jsonb NOT NULL DEFAULT '{}'::jsonb,
          denominator jsonb,
          formula_contract jsonb NOT NULL,
          unit text NOT NULL,
          inclusion_rules jsonb NOT NULL DEFAULT '{}'::jsonb,
          exclusion_rules jsonb NOT NULL DEFAULT '{}'::jsonb,
          time_semantics text NOT NULL,
          as_of_vs_period text NOT NULL DEFAULT 'as_of_or_period',
          supported_dimensions jsonb NOT NULL DEFAULT '[]'::jsonb,
          canonical_source_facts jsonb NOT NULL DEFAULT '[]'::jsonb,
          required_domain_authority jsonb NOT NULL DEFAULT '[]'::jsonb,
          permission_class text NOT NULL,
          owner text,
          approving_authority text,
          prior_kpi_definition_id uuid,
          created_by_phone text,
          created_reason text,
          created_at timestamptz NOT NULL DEFAULT now(),
          UNIQUE (semantic_key, effective_version),
          CHECK (status IN ('draft','published','retired','blocked')),
          CHECK (effective_version >= 1)
        )
        """
    )
    cur.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_hr_kpi_definitions_semantic
          ON hr_kpi_definitions (semantic_key, effective_version DESC)
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS hr_kpi_company_publications (
          publication_id uuid PRIMARY KEY,
          company_code text NOT NULL,
          semantic_key text NOT NULL,
          kpi_definition_id uuid NOT NULL REFERENCES hr_kpi_definitions(kpi_definition_id),
          effective_version integer NOT NULL,
          published boolean NOT NULL DEFAULT true,
          published_by_phone text,
          published_reason text,
          published_at timestamptz NOT NULL DEFAULT now(),
          unpublished_at timestamptz,
          UNIQUE (company_code, semantic_key)
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS hr_intelligence_facts (
          fact_id uuid PRIMARY KEY,
          company_code text NOT NULL,
          fact_type text NOT NULL,
          entity_type text NOT NULL,
          entity_id text NOT NULL,
          event_time timestamptz,
          effective_from timestamptz,
          effective_to timestamptz,
          recorded_at timestamptz NOT NULL DEFAULT now(),
          dimensions jsonb NOT NULL DEFAULT '{}'::jsonb,
          measures jsonb NOT NULL DEFAULT '{}'::jsonb,
          source_authority text NOT NULL,
          source_version text,
          correction_of uuid,
          supersedes uuid,
          superseded_by uuid,
          is_synthetic boolean NOT NULL DEFAULT false,
          ingest_key text,
          UNIQUE (company_code, ingest_key)
        )
        """
    )
    cur.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_hr_intelligence_facts_type
          ON hr_intelligence_facts (company_code, fact_type)
          WHERE superseded_by IS NULL
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS hr_kpi_evaluations (
          evaluation_id uuid PRIMARY KEY,
          company_code text NOT NULL,
          kpi_definition_id uuid NOT NULL,
          semantic_key text NOT NULL,
          effective_version integer NOT NULL,
          formula_snapshot jsonb NOT NULL,
          status text NOT NULL,
          value numeric,
          unit text,
          numerator_value numeric,
          denominator_value numeric,
          population_ids jsonb NOT NULL DEFAULT '[]'::jsonb,
          filters jsonb NOT NULL DEFAULT '{}'::jsonb,
          time_window jsonb NOT NULL DEFAULT '{}'::jsonb,
          permission_class text NOT NULL,
          freshness jsonb NOT NULL DEFAULT '{}'::jsonb,
          actor_phone text,
          actor_role text,
          evaluated_at timestamptz NOT NULL DEFAULT now(),
          CHECK (status IN ('ok','not_applicable','insufficient_data','unavailable','suppressed','forbidden','blocked'))
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS hr_intelligence_c1_audit (
          audit_id bigserial PRIMARY KEY,
          company_code text,
          action text NOT NULL,
          actor_phone text,
          reason text,
          subject_type text,
          subject_id text,
          payload jsonb NOT NULL DEFAULT '{}'::jsonb,
          created_at timestamptz NOT NULL DEFAULT now()
        )
        """
    )


def _audit(
    cur: Any,
    *,
    company_code: str | None,
    action: str,
    actor_phone: str | None,
    reason: str | None = None,
    subject_type: str | None = None,
    subject_id: str | None = None,
    payload: dict[str, Any] | None = None,
) -> None:
    cur.execute(
        """
        INSERT INTO hr_intelligence_c1_audit (
          company_code, action, actor_phone, reason, subject_type, subject_id, payload
        ) VALUES (%s,%s,%s,%s,%s,%s,%s::jsonb)
        """,
        (
            company_code_norm(company_code) if company_code else None,
            action,
            _digits(actor_phone) if actor_phone else None,
            (str(reason).strip()[:500] if reason else None),
            subject_type,
            subject_id,
            json.dumps(payload or {}, default=str),
        ),
    )


def _entitled(cur: Any, company_code: str) -> dict[str, Any]:
    gate = runtime_gate_for_company(company_code)
    if not gate.get("ok"):
        return gate
    company = gate["company_code"]
    ensure_hr_intelligence_registry_c1_schema(cur)
    cur.execute(
        "SELECT * FROM hr_intelligence_c1_company_settings WHERE company_code=%s",
        (company,),
    )
    row = cur.fetchone()
    if not row or not bool(dict(row).get("enabled")):
        return {"ok": False, "error": "company_intelligence_disabled", "company_code": company}
    return {"ok": True, "company_code": company, "settings": dict(row)}


def enable_company_hr_intelligence(
    cur: Any,
    *,
    company_code: str,
    actor_phone: str,
    reason: str,
    min_cohort_n: int = DEFAULT_MIN_COHORT_N,
) -> dict[str, Any]:
    if not str(reason or "").strip():
        return {"ok": False, "error": "audit_reason_required"}
    gate = runtime_gate_for_company(company_code)
    if not gate.get("ok"):
        return gate
    company = gate["company_code"]
    n = int(min_cohort_n)
    if n < DEFAULT_MIN_COHORT_N:
        return {"ok": False, "error": "min_cohort_n_below_floor", "floor": DEFAULT_MIN_COHORT_N, "requested": n}
    ensure_hr_intelligence_registry_c1_schema(cur)
    cur.execute(
        "SELECT min_cohort_n FROM hr_intelligence_c1_company_settings WHERE company_code=%s",
        (company,),
    )
    existing = cur.fetchone()
    if existing:
        n = max(n, int(dict(existing)["min_cohort_n"]))
    cur.execute(
        """
        INSERT INTO hr_intelligence_c1_company_settings (
          company_code, enabled, min_cohort_n, headcount_policy,
          enabled_by_phone, enabled_reason, enabled_at, disabled_at, updated_at
        ) VALUES (%s,true,%s,%s::jsonb,%s,%s,now(),NULL,now())
        ON CONFLICT (company_code) DO UPDATE SET
          enabled=true,
          min_cohort_n=GREATEST(hr_intelligence_c1_company_settings.min_cohort_n, EXCLUDED.min_cohort_n),
          headcount_policy=EXCLUDED.headcount_policy,
          enabled_by_phone=EXCLUDED.enabled_by_phone,
          enabled_reason=EXCLUDED.enabled_reason,
          enabled_at=now(),
          disabled_at=NULL,
          updated_at=now()
        RETURNING *
        """,
        (company, n, json.dumps(HEADCOUNT_POLICY, default=str), _digits(actor_phone), str(reason).strip()[:500]),
    )
    row = dict(cur.fetchone())
    _audit(cur, company_code=company, action="company_enabled", actor_phone=actor_phone, reason=reason, subject_type="company", subject_id=company, payload={"min_cohort_n": n})
    return {"ok": True, "settings": row, **honesty_payload(company_code=company)}


def disable_company_hr_intelligence(
    cur: Any, *, company_code: str, actor_phone: str, reason: str
) -> dict[str, Any]:
    if not str(reason or "").strip():
        return {"ok": False, "error": "audit_reason_required"}
    company = company_code_norm(company_code)
    ensure_hr_intelligence_registry_c1_schema(cur)
    cur.execute(
        """
        UPDATE hr_intelligence_c1_company_settings
           SET enabled=false, disabled_at=now(), updated_at=now()
         WHERE company_code=%s
        RETURNING *
        """,
        (company,),
    )
    row = cur.fetchone()
    _audit(cur, company_code=company, action="company_disabled", actor_phone=actor_phone, reason=reason, subject_type="company", subject_id=company, payload={"preserves_history": True})
    return {"ok": True, "settings": dict(row) if row else None, "preserves_history": True}


def set_min_cohort_n(
    cur: Any, *, company_code: str, actor_phone: str, min_cohort_n: int, reason: str
) -> dict[str, Any]:
    if not str(reason or "").strip():
        return {"ok": False, "error": "audit_reason_required"}
    ent = _entitled(cur, company_code)
    if not ent.get("ok"):
        return ent
    n = int(min_cohort_n)
    if n < DEFAULT_MIN_COHORT_N:
        return {"ok": False, "error": "min_cohort_n_below_floor", "floor": DEFAULT_MIN_COHORT_N}
    current = int(ent["settings"]["min_cohort_n"])
    if n < current:
        return {"ok": False, "error": "min_cohort_n_downward_forbidden", "current": current, "requested": n}
    cur.execute(
        """
        UPDATE hr_intelligence_c1_company_settings
           SET min_cohort_n=%s, updated_at=now()
         WHERE company_code=%s
        RETURNING *
        """,
        (n, ent["company_code"]),
    )
    row = dict(cur.fetchone())
    _audit(cur, company_code=ent["company_code"], action="min_cohort_n_raised", actor_phone=actor_phone, reason=reason, payload={"from": current, "to": n})
    return {"ok": True, "settings": row}


def create_kpi_definition(
    cur: Any,
    *,
    actor_phone: str,
    semantic_key: str,
    name_en: str,
    name_ar: str,
    description_en: str,
    description_ar: str,
    business_meaning: str,
    formula_contract: dict[str, Any],
    unit: str,
    time_semantics: str,
    permission_class: str,
    status: str = "draft",
    numerator: dict[str, Any] | None = None,
    denominator: dict[str, Any] | None = None,
    inclusion_rules: dict[str, Any] | None = None,
    exclusion_rules: dict[str, Any] | None = None,
    supported_dimensions: list[Any] | None = None,
    canonical_source_facts: list[Any] | None = None,
    required_domain_authority: list[Any] | None = None,
    owner: str | None = None,
    approving_authority: str | None = None,
    reason: str = "create kpi definition",
    company_code: str | None = None,
) -> dict[str, Any]:
    if not str(reason or "").strip():
        return {"ok": False, "error": "audit_reason_required"}
    if company_code:
        gate = runtime_gate_for_company(company_code)
        if not gate.get("ok"):
            return gate
    st = str(status or "draft").strip().lower()
    if st not in DEFINITION_STATUSES:
        return {"ok": False, "error": "invalid_status", "allowed": list(DEFINITION_STATUSES)}
    ts = str(time_semantics or "").strip().lower()
    if ts not in TIME_SEMANTICS:
        return {"ok": False, "error": "invalid_time_semantics", "allowed": list(TIME_SEMANTICS)}
    pc = str(permission_class or "").strip().lower()
    if pc not in PERMISSION_CLASSES:
        return {"ok": False, "error": "invalid_permission_class", "allowed": list(PERMISSION_CLASSES)}
    key = str(semantic_key or "").strip()
    if not key or not str(name_en or "").strip() or not str(name_ar or "").strip():
        return {"ok": False, "error": "semantic_key_and_bilingual_names_required"}
    if not isinstance(formula_contract, dict) or not formula_contract.get("kind"):
        return {"ok": False, "error": "formula_contract_kind_required"}
    if key in {"employee_score", "workforce_score", "talent_score", "universal_talent_score"} or any(
        k in key for k in ("employee_score", "talent_score", "workforce_score")
    ):
        return {"ok": False, "error": "universal_score_forbidden"}
    ensure_hr_intelligence_registry_c1_schema(cur)
    cur.execute(
        "SELECT COALESCE(MAX(effective_version), 0) AS v FROM hr_kpi_definitions WHERE semantic_key=%s",
        (key,),
    )
    ver = int(dict(cur.fetchone())["v"]) + 1
    kid = str(uuid.uuid4())
    cur.execute(
        """
        INSERT INTO hr_kpi_definitions (
          kpi_definition_id, semantic_key, effective_version, status,
          name_en, name_ar, description_en, description_ar, business_meaning,
          numerator, denominator, formula_contract, unit,
          inclusion_rules, exclusion_rules, time_semantics, supported_dimensions,
          canonical_source_facts, required_domain_authority, permission_class,
          owner, approving_authority, created_by_phone, created_reason
        ) VALUES (
          %s,%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb,%s::jsonb,%s::jsonb,%s,
          %s::jsonb,%s::jsonb,%s,%s::jsonb,%s::jsonb,%s::jsonb,%s,%s,%s,%s,%s
        ) RETURNING *
        """,
        (
            kid, key, ver, st,
            str(name_en).strip()[:300], str(name_ar).strip()[:300],
            str(description_en).strip()[:2000], str(description_ar).strip()[:2000],
            str(business_meaning).strip()[:2000],
            json.dumps(numerator or {}, default=str),
            json.dumps(denominator, default=str) if denominator is not None else None,
            json.dumps(formula_contract, default=str), str(unit).strip()[:64],
            json.dumps(inclusion_rules or {}, default=str),
            json.dumps(exclusion_rules or {}, default=str), ts,
            json.dumps(supported_dimensions or [], default=str),
            json.dumps(canonical_source_facts or [], default=str),
            json.dumps(required_domain_authority or [], default=str),
            pc, owner, approving_authority, _digits(actor_phone), str(reason).strip()[:500],
        ),
    )
    row = dict(cur.fetchone())
    _audit(cur, company_code=company_code, action="kpi_definition_created", actor_phone=actor_phone, reason=reason, subject_type="kpi_definition", subject_id=kid, payload={"semantic_key": key, "effective_version": ver, "status": st})
    return {"ok": True, "definition": row}


def version_kpi_definition(
    cur: Any,
    *,
    actor_phone: str,
    semantic_key: str,
    reason: str,
    updates: dict[str, Any],
    company_code: str | None = None,
) -> dict[str, Any]:
    if not str(reason or "").strip():
        return {"ok": False, "error": "audit_reason_required"}
    ensure_hr_intelligence_registry_c1_schema(cur)
    key = str(semantic_key).strip()
    cur.execute(
        """
        SELECT * FROM hr_kpi_definitions
         WHERE semantic_key=%s
         ORDER BY effective_version DESC
         LIMIT 1
        """,
        (key,),
    )
    prev = cur.fetchone()
    if not prev:
        return {"ok": False, "error": "definition_not_found"}
    prev = dict(prev)
    body = {
        "name_en": updates.get("name_en", prev["name_en"]),
        "name_ar": updates.get("name_ar", prev["name_ar"]),
        "description_en": updates.get("description_en", prev["description_en"]),
        "description_ar": updates.get("description_ar", prev["description_ar"]),
        "business_meaning": updates.get("business_meaning", prev["business_meaning"]),
        "formula_contract": updates.get("formula_contract", prev["formula_contract"]),
        "unit": updates.get("unit", prev["unit"]),
        "time_semantics": updates.get("time_semantics", prev["time_semantics"]),
        "permission_class": updates.get("permission_class", prev["permission_class"]),
        "status": updates.get("status", prev["status"]),
        "numerator": updates.get("numerator", prev["numerator"]),
        "denominator": updates.get("denominator", prev["denominator"]),
        "inclusion_rules": updates.get("inclusion_rules", prev["inclusion_rules"]),
        "exclusion_rules": updates.get("exclusion_rules", prev["exclusion_rules"]),
        "supported_dimensions": updates.get("supported_dimensions", prev["supported_dimensions"]),
        "canonical_source_facts": updates.get("canonical_source_facts", prev["canonical_source_facts"]),
        "required_domain_authority": updates.get("required_domain_authority", prev["required_domain_authority"]),
        "owner": updates.get("owner", prev.get("owner")),
        "approving_authority": updates.get("approving_authority", prev.get("approving_authority")),
    }
    if isinstance(body["formula_contract"], str):
        body["formula_contract"] = json.loads(body["formula_contract"])
    for jk in ("numerator", "denominator", "inclusion_rules", "exclusion_rules", "supported_dimensions", "canonical_source_facts", "required_domain_authority"):
        if isinstance(body.get(jk), str):
            body[jk] = json.loads(body[jk]) if body[jk] is not None else None
    created = create_kpi_definition(cur, actor_phone=actor_phone, semantic_key=key, reason=reason, company_code=company_code, **body)
    if not created.get("ok"):
        return created
    cur.execute(
        "UPDATE hr_kpi_definitions SET prior_kpi_definition_id=%s WHERE kpi_definition_id=%s",
        (prev["kpi_definition_id"], created["definition"]["kpi_definition_id"]),
    )
    cur.execute(
        "SELECT formula_contract, effective_version FROM hr_kpi_definitions WHERE kpi_definition_id=%s",
        (prev["kpi_definition_id"],),
    )
    frozen = dict(cur.fetchone())
    return {
        "ok": True,
        "definition": created["definition"],
        "prior_preserved": True,
        "prior_version": int(frozen["effective_version"]),
        "prior_formula_contract": frozen["formula_contract"],
    }


def publish_kpi_definition(
    cur: Any, *, actor_phone: str, kpi_definition_id: str, reason: str
) -> dict[str, Any]:
    if not str(reason or "").strip():
        return {"ok": False, "error": "audit_reason_required"}
    ensure_hr_intelligence_registry_c1_schema(cur)
    cur.execute("SELECT * FROM hr_kpi_definitions WHERE kpi_definition_id=%s", (kpi_definition_id,))
    row = cur.fetchone()
    if not row:
        return {"ok": False, "error": "definition_not_found"}
    row = dict(row)
    if row["status"] == "blocked":
        return {"ok": False, "error": "blocked_definition_cannot_publish"}
    cur.execute(
        "UPDATE hr_kpi_definitions SET status='published' WHERE kpi_definition_id=%s RETURNING *",
        (kpi_definition_id,),
    )
    out = dict(cur.fetchone())
    _audit(cur, company_code=None, action="kpi_definition_published", actor_phone=actor_phone, reason=reason, subject_type="kpi_definition", subject_id=str(kpi_definition_id))
    return {"ok": True, "definition": out}


def publish_kpi_for_company(
    cur: Any,
    *,
    company_code: str,
    actor_phone: str,
    semantic_key: str,
    reason: str,
    kpi_definition_id: str | None = None,
) -> dict[str, Any]:
    if not str(reason or "").strip():
        return {"ok": False, "error": "audit_reason_required"}
    ent = _entitled(cur, company_code)
    if not ent.get("ok"):
        return ent
    company = ent["company_code"]
    key = str(semantic_key).strip()
    if kpi_definition_id:
        cur.execute("SELECT * FROM hr_kpi_definitions WHERE kpi_definition_id=%s", (kpi_definition_id,))
    else:
        cur.execute(
            """
            SELECT * FROM hr_kpi_definitions
             WHERE semantic_key=%s AND status='published'
             ORDER BY effective_version DESC LIMIT 1
            """,
            (key,),
        )
    defn = cur.fetchone()
    if not defn:
        return {"ok": False, "error": "published_definition_required"}
    defn = dict(defn)
    if defn["status"] != "published":
        return {"ok": False, "error": "definition_not_published"}
    fc = defn["formula_contract"]
    if isinstance(fc, str):
        fc = json.loads(fc)
    if fc.get("kind") == "blocked" or defn["semantic_key"] == FTE_KEY:
        return {"ok": False, "error": "fte_or_blocked_kpi_not_publishable"}
    pid = str(uuid.uuid4())
    cur.execute(
        """
        INSERT INTO hr_kpi_company_publications (
          publication_id, company_code, semantic_key, kpi_definition_id,
          effective_version, published, published_by_phone, published_reason
        ) VALUES (%s,%s,%s,%s,%s,true,%s,%s)
        ON CONFLICT (company_code, semantic_key) DO UPDATE SET
          kpi_definition_id=EXCLUDED.kpi_definition_id,
          effective_version=EXCLUDED.effective_version,
          published=true,
          published_by_phone=EXCLUDED.published_by_phone,
          published_reason=EXCLUDED.published_reason,
          published_at=now(),
          unpublished_at=NULL
        RETURNING *
        """,
        (pid, company, key, defn["kpi_definition_id"], int(defn["effective_version"]), _digits(actor_phone), str(reason).strip()[:500]),
    )
    pub = dict(cur.fetchone())
    _audit(cur, company_code=company, action="kpi_published_for_company", actor_phone=actor_phone, reason=reason, subject_type="kpi_publication", subject_id=str(pub["publication_id"]), payload={"semantic_key": key, "effective_version": int(defn["effective_version"])})
    return {"ok": True, "publication": pub, "definition": defn}


def ingest_fact(
    cur: Any,
    *,
    company_code: str,
    actor_phone: str,
    fact_type: str,
    entity_type: str,
    entity_id: str,
    source_authority: str,
    measures: dict[str, Any] | None = None,
    dimensions: dict[str, Any] | None = None,
    event_time: datetime | None = None,
    effective_from: datetime | None = None,
    effective_to: datetime | None = None,
    source_version: str | None = None,
    ingest_key: str | None = None,
    is_synthetic: bool = False,
    reason: str = "ingest fact",
) -> dict[str, Any]:
    ent = _entitled(cur, company_code)
    if not ent.get("ok"):
        return ent
    company = ent["company_code"]
    fid = str(uuid.uuid4())
    key = ingest_key or f"{fact_type}:{entity_type}:{entity_id}:{source_version or 'v1'}"
    cur.execute(
        """
        INSERT INTO hr_intelligence_facts (
          fact_id, company_code, fact_type, entity_type, entity_id,
          event_time, effective_from, effective_to, dimensions, measures,
          source_authority, source_version, is_synthetic, ingest_key
        ) VALUES (
          %s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb,%s::jsonb,%s,%s,%s,%s
        )
        ON CONFLICT (company_code, ingest_key) DO UPDATE SET
          measures=EXCLUDED.measures,
          dimensions=EXCLUDED.dimensions,
          recorded_at=now()
        RETURNING *
        """,
        (
            fid, company, str(fact_type), str(entity_type), str(entity_id),
            event_time, effective_from, effective_to,
            json.dumps(dimensions or {}, default=str),
            json.dumps(measures or {}, default=str),
            str(source_authority), source_version, bool(is_synthetic), key,
        ),
    )
    row = dict(cur.fetchone())
    _audit(cur, company_code=company, action="fact_ingested", actor_phone=actor_phone, reason=reason, subject_type="fact", subject_id=str(row["fact_id"]), payload={"fact_type": fact_type, "idempotent_key": key})
    return {"ok": True, "fact": row, "idempotent": str(row["fact_id"]) != fid}


def correct_fact(
    cur: Any,
    *,
    company_code: str,
    actor_phone: str,
    prior_fact_id: str,
    measures: dict[str, Any],
    reason: str,
    source_version: str | None = None,
) -> dict[str, Any]:
    if not str(reason or "").strip():
        return {"ok": False, "error": "audit_reason_required"}
    ent = _entitled(cur, company_code)
    if not ent.get("ok"):
        return ent
    company = ent["company_code"]
    cur.execute(
        "SELECT * FROM hr_intelligence_facts WHERE company_code=%s AND fact_id=%s",
        (company, prior_fact_id),
    )
    prior = cur.fetchone()
    if not prior:
        return {"ok": False, "error": "fact_not_found"}
    prior = dict(prior)
    dims = prior.get("dimensions")
    if isinstance(dims, str):
        dims = json.loads(dims)
    new = ingest_fact(
        cur,
        company_code=company,
        actor_phone=actor_phone,
        fact_type=prior["fact_type"],
        entity_type=prior["entity_type"],
        entity_id=prior["entity_id"],
        source_authority=prior["source_authority"],
        measures=measures,
        dimensions=dims if isinstance(dims, dict) else {},
        event_time=prior.get("event_time"),
        effective_from=prior.get("effective_from"),
        effective_to=prior.get("effective_to"),
        source_version=source_version or f"correction_of_{prior_fact_id}",
        ingest_key=f"correction:{prior_fact_id}:{uuid.uuid4().hex[:8]}",
        is_synthetic=bool(prior.get("is_synthetic")),
        reason=reason,
    )
    if not new.get("ok"):
        return new
    new_id = str(new["fact"]["fact_id"])
    cur.execute("UPDATE hr_intelligence_facts SET superseded_by=%s WHERE fact_id=%s", (new_id, prior_fact_id))
    cur.execute(
        "UPDATE hr_intelligence_facts SET correction_of=%s, supersedes=%s WHERE fact_id=%s",
        (prior_fact_id, prior_fact_id, new_id),
    )
    return {"ok": True, "fact": new["fact"], "prior_fact_id": prior_fact_id, "domain_audit_rewritten": False}


def _active_facts(cur: Any, *, company: str, fact_type: str) -> list[dict[str, Any]]:
    cur.execute(
        """
        SELECT * FROM hr_intelligence_facts
         WHERE company_code=%s AND fact_type=%s AND superseded_by IS NULL
         ORDER BY recorded_at
        """,
        (company, fact_type),
    )
    return [dict(r) for r in (cur.fetchall() or [])]


def evaluate_kpi(
    cur: Any,
    *,
    company_code: str,
    actor_phone: str,
    semantic_key: str,
    actor_role: str = "hr",
    filters: dict[str, Any] | None = None,
    time_window: dict[str, Any] | None = None,
    has_permission: bool = True,
    persist: bool = True,
) -> dict[str, Any]:
    ent = _entitled(cur, company_code)
    if not ent.get("ok"):
        return {**ent, "status": "unavailable"}
    company = ent["company_code"]
    settings = ent["settings"]
    key = str(semantic_key).strip()
    cur.execute(
        """
        SELECT p.*, d.status AS def_status, d.formula_contract, d.unit, d.permission_class,
               d.name_en, d.name_ar, d.numerator, d.denominator, d.time_semantics
          FROM hr_kpi_company_publications p
          JOIN hr_kpi_definitions d ON d.kpi_definition_id=p.kpi_definition_id
         WHERE p.company_code=%s AND p.semantic_key=%s AND p.published=true
        """,
        (company, key),
    )
    pub = cur.fetchone()
    if not pub:
        return {
            "ok": False,
            "status": "unavailable",
            "error": "kpi_not_published_for_company",
            "semantic_key": key,
            "message": "No production card without company-published Registry definition.",
        }
    pub = dict(pub)
    if pub["def_status"] == "blocked":
        return {"ok": False, "status": "blocked", "error": "kpi_blocked", "semantic_key": key}
    if not has_permission:
        return {"ok": False, "status": "forbidden", "error": "permission_denied", "semantic_key": key}

    fc = pub["formula_contract"]
    if isinstance(fc, str):
        fc = json.loads(fc)
    kind = str(fc.get("kind") or "").strip().lower()
    unit = pub["unit"]
    population: list[str] = []
    value = None
    num_v = None
    den_v = None
    status = "ok"

    if kind == "blocked":
        status = "blocked"
    elif kind == "count_facts":
        ftype = str(fc.get("fact_type") or "")
        facts = _active_facts(cur, company=company, fact_type=ftype)
        if fc.get("require_facts") and not facts:
            status = "insufficient_data"
        else:
            population = [str(f["entity_id"]) for f in facts]
            value = float(len(facts))
            num_v = value
    elif kind == "rate_from_counts":
        nums = _active_facts(cur, company=company, fact_type=str(fc.get("numerator_fact_type") or ""))
        dens = _active_facts(cur, company=company, fact_type=str(fc.get("denominator_fact_type") or ""))
        num_v = float(len(nums))
        den_v = float(len(dens))
        population = [str(f["entity_id"]) for f in dens]
        if den_v == 0:
            status = "not_applicable"
            value = None
        else:
            value = (num_v / den_v) * float(fc.get("scale", 100.0))
            unit = unit or "percent"
    elif kind == "unavailable":
        status = "unavailable"
    elif kind in _FORMULA_HANDLERS:
        handled = _FORMULA_HANDLERS[kind](
            cur,
            company_code=company,
            settings=settings,
            formula_contract=fc,
            publication=pub,
            filters=filters or {},
            time_window=time_window or {},
            actor_phone=actor_phone,
            actor_role=actor_role,
        )
        if not isinstance(handled, dict):
            return {"ok": False, "error": "invalid_formula_handler_result", "kind": kind}
        if handled.get("error") and handled.get("status") is None:
            return handled
        status = str(handled.get("status") or "ok")
        value = handled.get("value")
        num_v = handled.get("numerator_value", num_v)
        den_v = handled.get("denominator_value", den_v)
        population = list(handled.get("population_ids") or [])
        if handled.get("unit"):
            unit = handled["unit"]
        # allow handlers to attach explain metadata via result merge later
        handler_meta = handled.get("explain") or {}
    else:
        return {"ok": False, "error": "unsupported_formula_kind", "kind": kind}

    handler_meta = locals().get("handler_meta") or {}

    sensitive = pub["permission_class"] in {
        "workforce_sensitive_demo", "payroll_money", "performance_raw", "talent_sensitive", "lifecycle_confidential",
    } or bool(fc.get("sensitive_aggregate"))
    min_n = int(settings["min_cohort_n"])
    if status == "ok" and sensitive and len(population) < min_n:
        status = "suppressed"
        value = None

    freshness = {
        "mode": "near_real_time_spine",
        "evaluated_at": datetime.now(timezone.utc).isoformat(),
        "guaranteed_current": False,
    }
    result = {
        "ok": status in ("ok", "not_applicable", "insufficient_data", "suppressed", "blocked", "unavailable"),
        "status": status,
        "value": value,
        "unit": unit,
        "numerator_value": num_v,
        "denominator_value": den_v,
        "population_ids": population,
        "population_count": len(population),
        "kpi_definition_id": str(pub["kpi_definition_id"]),
        "semantic_key": key,
        "effective_version": int(pub["effective_version"]),
        "formula_snapshot": fc,
        "permission_class": pub["permission_class"],
        "filters": filters or {},
        "time_window": time_window or {},
        "freshness": freshness,
        "name_en": pub["name_en"],
        "name_ar": pub["name_ar"],
        "min_cohort_n": min_n,
        "same_authority_as_export": True,
        "explain": handler_meta,
    }
    if persist:
        eid = str(uuid.uuid4())
        cur.execute(
            """
            INSERT INTO hr_kpi_evaluations (
              evaluation_id, company_code, kpi_definition_id, semantic_key, effective_version,
              formula_snapshot, status, value, unit, numerator_value, denominator_value,
              population_ids, filters, time_window, permission_class, freshness,
              actor_phone, actor_role
            ) VALUES (
              %s,%s,%s,%s,%s,%s::jsonb,%s,%s,%s,%s,%s,%s::jsonb,%s::jsonb,%s::jsonb,%s,%s::jsonb,%s,%s
            ) RETURNING evaluation_id, evaluated_at
            """,
            (
                eid, company, pub["kpi_definition_id"], key, int(pub["effective_version"]),
                json.dumps(fc, default=str), status, value, unit, num_v, den_v,
                json.dumps(population, default=str), json.dumps(filters or {}, default=str),
                json.dumps(time_window or {}, default=str), pub["permission_class"],
                json.dumps(freshness, default=str), _digits(actor_phone), actor_role,
            ),
        )
        stored = dict(cur.fetchone())
        result["evaluation_id"] = str(stored["evaluation_id"])
        result["evaluated_at"] = stored["evaluated_at"]
    return result


def assistant_resolve_metric(
    cur: Any,
    *,
    company_code: str,
    semantic_key: str,
    actor_phone: str = "assistant",
) -> dict[str, Any]:
    key = str(semantic_key or "").strip()
    if not key:
        return {"ok": False, "error": "metric_undefined", "invented": False, "message_en": "No metric key provided.", "message_ar": "لم يتم توفير مفتاح مؤشر."}
    if any(x in key for x in ("employee_score", "talent_score", "workforce_score")):
        return {
            "ok": False,
            "error": "universal_score_forbidden",
            "invented": False,
            "message_en": "OctoHR does not provide a universal employee/talent score.",
            "message_ar": "لا يوفّر OctoHR درجة موظف/مواهب عامة.",
        }
    ensure_hr_intelligence_registry_c1_schema(cur)
    cur.execute("SELECT 1 FROM hr_kpi_definitions WHERE semantic_key=%s LIMIT 1", (key,))
    if not cur.fetchone():
        return {
            "ok": False,
            "error": "metric_not_in_registry",
            "invented": False,
            "semantic_key": key,
            "message_en": "That metric has no governed KPI Registry definition. I will not invent one.",
            "message_ar": "لا يوجد تعريف محكوم لهذا المؤشر في السجل. لن أخترع مؤشراً.",
        }
    evaluated = evaluate_kpi(cur, company_code=company_code, actor_phone=actor_phone, semantic_key=key, actor_role="assistant", persist=False)
    if evaluated.get("error") == "kpi_not_published_for_company":
        return {
            "ok": False,
            "error": "metric_not_published",
            "invented": False,
            "semantic_key": key,
            "message_en": "This metric exists in the Registry but is not published for your company.",
            "message_ar": "هذا المؤشر موجود في السجل لكنه غير منشور لشركتك.",
        }
    return {"ok": True, "invented": False, "evaluation": evaluated, "assistant_mutations": False}


def seed_platform_spine_definitions(cur: Any, *, actor_phone: str) -> dict[str, Any]:
    ensure_hr_intelligence_registry_c1_schema(cur)
    created: list[str] = []

    def _ensure(key: str, **kwargs: Any) -> None:
        cur.execute("SELECT kpi_definition_id, status FROM hr_kpi_definitions WHERE semantic_key=%s ORDER BY effective_version DESC LIMIT 1", (key,))
        existing = cur.fetchone()
        if existing:
            existing = dict(existing)
            if kwargs.get("status") == "published" and existing["status"] != "published":
                publish_kpi_definition(cur, actor_phone=actor_phone, kpi_definition_id=str(existing["kpi_definition_id"]), reason="seed publish existing")
            return
        out = create_kpi_definition(cur, actor_phone=actor_phone, semantic_key=key, **kwargs)
        if out.get("ok"):
            created.append(key)
            if kwargs.get("status") == "published":
                publish_kpi_definition(cur, actor_phone=actor_phone, kpi_definition_id=str(out["definition"]["kpi_definition_id"]), reason="seed publish")

    _ensure(
        SPINE_FACT_COUNT_KEY,
        name_en="Intelligence spine fact count", name_ar="عدد حقائق عمود الذكاء",
        description_en="C1 prove metric: count of active ingested facts of a type.",
        description_ar="مؤشر إثبات C1: عدد الحقائق النشطة لنوع معيّن.",
        business_meaning="Proves Registry + fact spine + shared evaluator without domain KPI cards.",
        formula_contract={"kind": "count_facts", "fact_type": "spine_demo_entity", "require_facts": False},
        unit="count", time_semantics="event_count", permission_class="intelligence_spine", status="published",
        numerator={"description": "active facts"}, canonical_source_facts=["spine_demo_entity"], owner="wave5_c1", reason="seed spine",
    )
    _ensure(
        SPINE_RATE_KEY,
        name_en="Intelligence spine demo rate", name_ar="معدل إثبات عمود الذكاء",
        description_en="C1 prove rate with honest zero-denominator semantics.",
        description_ar="معدل إثبات C1 مع دلالات مقام صفري صريحة.",
        business_meaning="Proves not_applicable when denominator is empty.",
        formula_contract={"kind": "rate_from_counts", "numerator_fact_type": "spine_demo_num", "denominator_fact_type": "spine_demo_den", "scale": 100.0, "sensitive_aggregate": True},
        unit="percent", time_semantics="rate_over_window", permission_class="intelligence_spine", status="published",
        numerator={"description": "num facts"}, denominator={"description": "den facts"}, owner="wave5_c1", reason="seed spine rate",
    )
    _ensure(
        HEADCOUNT_KEY,
        name_en="Active headcount (heads)", name_ar="عدد الرؤوس النشط",
        description_en="Point-in-time employee heads per binding inclusion policy.",
        description_ar="عدد الموظفين النشطين حسب سياسة الإدراج الملزمة.",
        business_meaning="Workforce size as-of date; pending_start excluded.",
        formula_contract={"kind": "unavailable", "implemented_in": "c2"},
        unit="heads", time_semantics="point_in_time", permission_class="workforce_general", status="draft",
        inclusion_rules=dict(HEADCOUNT_POLICY), owner="wave5_c2", reason="seed headcount draft for C2",
    )
    _ensure(
        FUTURE_STARTERS_KEY,
        name_en="Future starters", name_ar="الملتحقون المستقبليون",
        description_en="pending_start / future starters — separate from headcount.",
        description_ar="قيد الالتحاق / الملتحقون المستقبليون — منفصل عن عدد الرؤوس.",
        business_meaning="Represents pending_start population excluded from headcount.",
        formula_contract={"kind": "unavailable", "implemented_in": "c2"},
        unit="count", time_semantics="point_in_time", permission_class="workforce_general", status="draft",
        owner="wave5_c2", reason="seed future starters",
    )
    _ensure(
        FTE_KEY,
        name_en="Active FTE", name_ar="المكافئ بدوام كامل النشط",
        description_en="Blocked until authoritative FTE/standard-hours inputs exist.",
        description_ar="محظور حتى تتوفر مدخلات FTE/ساعات معيارية موثوقة.",
        business_meaning="Must not assume 1 head = 1 FTE.",
        formula_contract={"kind": "blocked", "reason": "authoritative_fte_inputs_required", "never_assume_one_head_equals_one_fte": True},
        unit="fte", time_semantics="point_in_time", permission_class="workforce_general", status="blocked",
        owner="wave5_c2", reason="seed FTE blocked",
    )
    return {"ok": True, "created_semantic_keys": created, "headcount_policy": HEADCOUNT_POLICY}
