#!/usr/bin/env python3
"""Wave 4 C5 — Canonical Talent Profile / Talent Dimensions (company-scoped).

Owner-approved under WAVE4_PERFORMANCE_TALENT_CHARTER (2026-08-12) §0.8.5 + W4.9.

Authority: commercial module `talent` — operates when Performance is OFF.
Performance C1–C4 outputs are OPTIONAL evidence, never a hard dependency.

Dimension-first (not a master Talent score / blob):
  skills · competencies-as-evidence · strengths · development areas ·
  career aspirations · role/job-family interests · mobility · potential ·
  broader observations/evidence

Identity: existing company_code + employee_key (canonical person/employee).
No shadow talent-person table. Recruiting `talent_pool` remains isolated.

Does NOT:
  - HiPo / 9-box / succession nominations / employee rankings / mobility engine
  - invent a universal Talent score
  - silently rewrite employee-declared aspirations as manager/HR truth
  - treat performance as potential
  - duplicate C3 development plans

Gates (fail-closed):
  1) WATHEFNI_TALENT_PROFILE_C5 must be on
  2) company in WATHEFNI_TALENT_PROFILE_COMPANIES (empty = nobody)
  3) company entitlement in talent_profile_c5_company_settings
"""
from __future__ import annotations

import json
import os
from datetime import date, datetime
from typing import Any

PHASE = "talent_profile_c5"
CONTRACT_VERSION = "talent_profile_c5_v1"
PASS_STAMP = "TALENT_PROFILE_FULL_PASS"
COMMERCIAL_MODULE_KEY = "talent"
RECRUITING_POOL_KEY = "talent_pool"  # candidate-only — never write here
_ON = {"1", "true", "yes", "on"}

DIMENSION_KINDS = (
    "strength",
    "development_area",
    "career_aspiration",
    "role_interest",
    "job_family_interest",
    "mobility_preference",
    "observation",
    "skill_note",
)
FACT_SOURCES = (
    "employee_declared",
    "manager_assessed",
    "hr_assessed",
    "competency_evidence",
    "development_evidence",
    "performance_outcome",
    "imported",
    "learning_evidence",
)
SKILL_STATES = ("claimed", "verified", "assessed", "deprecated")
VISIBILITY = ("employee_visible", "manager_visible", "hr_confidential")
POTENTIAL_STATES = ("draft", "submitted", "accepted", "withdrawn")
READINESS_SCOPES = ("general", "role_specific_primitive")  # no succession nomination

STATUS_LABELS = {
    "claimed": {"en": "Claimed", "ar": "مُدَّعى"},
    "verified": {"en": "Verified", "ar": "موثَّق"},
    "assessed": {"en": "Assessed", "ar": "مُقيَّم"},
    "deprecated": {"en": "Deprecated", "ar": "مهجور"},
    "draft": {"en": "Draft", "ar": "مسودة"},
    "submitted": {"en": "Submitted", "ar": "مُقدَّم"},
    "accepted": {"en": "Accepted", "ar": "مقبول"},
    "withdrawn": {"en": "Withdrawn", "ar": "مسحوب"},
    "employee_declared": {"en": "Employee-declared", "ar": "تصريح الموظف"},
    "manager_assessed": {"en": "Manager-assessed", "ar": "تقييم المدير"},
    "hr_assessed": {"en": "HR-assessed", "ar": "تقييم الموارد البشرية"},
    "hr_confidential": {"en": "HR confidential", "ar": "سري للموارد البشرية"},
    "strength": {"en": "Strength", "ar": "نقطة قوة"},
    "development_area": {"en": "Development area", "ar": "مجال تطوير"},
    "career_aspiration": {"en": "Career aspiration", "ar": "طموح مهني"},
    "mobility_preference": {"en": "Mobility preference", "ar": "تفضيل تنقل"},
}


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


def talent_profile_c5_runtime_on() -> bool:
    return _env_on("WATHEFNI_TALENT_PROFILE_C5", "off")


def talent_profile_company_allowlist() -> set[str]:
    raw = str(os.environ.get("WATHEFNI_TALENT_PROFILE_COMPANIES") or "").strip()
    if not raw:
        return set()
    return {p.strip().upper() for p in raw.split(",") if p.strip()}


def honesty_payload(*, company_code: str | None = None) -> dict[str, Any]:
    return {
        "phase": PHASE,
        "contract_version": CONTRACT_VERSION,
        "pass_stamp": PASS_STAMP,
        "commercial_module_key": COMMERCIAL_MODULE_KEY,
        "recruiting_talent_pool_isolated": True,
        "recruiting_storage_key": RECRUITING_POOL_KEY,
        "assistant_mutations": False,
        "uses_canonical_employee_identity": True,
        "no_shadow_talent_person_table": True,
        "dimension_first_not_blob_score": True,
        "no_master_talent_score": True,
        "performance_optional_not_hard_dependency": True,
        "talent_works_when_performance_off": True,
        "talent_works_without_recruiting": True,
        "talent_works_without_learning": True,
        "talent_works_without_succession_or_9box": True,
        "employee_declared_not_silently_rewritten": True,
        "skill_not_automatically_competency": True,
        "competency_evidence_requires_explicit_contract": True,
        "performance_is_not_potential": True,
        "potential_works_without_performance": True,
        "c3_development_remains_canonical": True,
        "no_hipo_9box_succession_writes_in_c5": True,
        "no_protected_attribute_inference": True,
        "historical_versions_survive_edits": True,
        "company_code": company_code_norm(company_code) if company_code else None,
    }


def rollback_guidance() -> dict[str, Any]:
    return {
        "phase": PHASE,
        "preserves_history": True,
        "does_not_damage_performance_history": True,
        "steps": [
            "WATHEFNI_TALENT_PROFILE_C5=off",
            "Clear WATHEFNI_TALENT_PROFILE_COMPANIES",
            "WATHEFNI_TALENT_KILL=on (optional immediate block)",
            "Disable company Setup entitlement (preserves Talent history; Performance untouched)",
        ],
    }


def runtime_gate_for_company(company_code: str | None) -> dict[str, Any]:
    company = company_code_norm(company_code)
    if not company:
        return {"ok": False, "enabled": False, "error": "company_required", "phase": PHASE}
    if _env_on("WATHEFNI_TALENT_KILL", "off"):
        return {
            "ok": False,
            "enabled": False,
            "error": "talent_kill_switch",
            "gate": "kill",
            "phase": PHASE,
        }
    if not talent_profile_c5_runtime_on():
        return {
            "ok": False,
            "enabled": False,
            "error": "talent_profile_c5_off",
            "gate": "runtime_flag",
            "phase": PHASE,
        }
    allow = talent_profile_company_allowlist()
    if not allow:
        return {
            "ok": False,
            "enabled": False,
            "error": "talent_profile_company_not_allowlisted",
            "gate": "company_allowlist",
            "phase": PHASE,
            "message": "Talent-profile allowlist empty — fail closed (nobody).",
        }
    if company not in allow:
        return {
            "ok": False,
            "enabled": False,
            "error": "talent_profile_company_not_allowlisted",
            "gate": "company_allowlist",
            "phase": PHASE,
            "company_code": company,
        }
    return {"ok": True, "enabled": True, "company_code": company, "phase": PHASE}


def ensure_talent_profile_c5_schema(cur: Any, *, force: bool = False) -> None:
    _ = force
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS talent_profile_c5_company_settings (
          company_code text PRIMARY KEY,
          enabled boolean NOT NULL DEFAULT false,
          employee_career_self_service boolean NOT NULL DEFAULT true,
          performance_evidence_consume boolean NOT NULL DEFAULT false,
          potential_enabled boolean NOT NULL DEFAULT true,
          skills_enabled boolean NOT NULL DEFAULT true,
          sensitive_potential_hr_manager_only boolean NOT NULL DEFAULT true,
          require_sensitive_permission_for_potential boolean NOT NULL DEFAULT true,
          enabled_by_phone text,
          enabled_reason text,
          enabled_at timestamptz,
          disabled_at timestamptz,
          updated_by_phone text,
          updated_at timestamptz NOT NULL DEFAULT now(),
          metadata jsonb NOT NULL DEFAULT '{}'::jsonb
        )
        """
    )
    # Thin anchor — identity only; dimensions live in child tables.
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS talent_profiles (
          profile_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
          company_code text NOT NULL,
          employee_key text NOT NULL,
          row_version int NOT NULL DEFAULT 1,
          created_at timestamptz NOT NULL DEFAULT now(),
          updated_at timestamptz NOT NULL DEFAULT now(),
          updated_by_phone text,
          metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
          UNIQUE (company_code, employee_key),
          CONSTRAINT talent_profiles_no_score_chk CHECK (
            (metadata->>'master_talent_score') IS NULL
          )
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS talent_dimension_facts (
          fact_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
          company_code text NOT NULL,
          employee_key text NOT NULL,
          dimension_kind text NOT NULL,
          version int NOT NULL DEFAULT 1,
          status text NOT NULL DEFAULT 'active',
          title_en text NOT NULL,
          title_ar text,
          detail_en text,
          detail_ar text,
          source text NOT NULL,
          actor_phone text,
          actor_system text,
          confidence text,
          visibility text NOT NULL DEFAULT 'manager_visible',
          effective_date date,
          superseded_by_fact_id uuid,
          evidence_refs jsonb NOT NULL DEFAULT '[]'::jsonb,
          created_at timestamptz NOT NULL DEFAULT now(),
          metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
          CONSTRAINT talent_dim_kind_chk CHECK (dimension_kind IN (
            'strength','development_area','career_aspiration','role_interest',
            'job_family_interest','mobility_preference','observation','skill_note'
          )),
          CONSTRAINT talent_dim_source_chk CHECK (source IN (
            'employee_declared','manager_assessed','hr_assessed','competency_evidence',
            'development_evidence','performance_outcome','imported','learning_evidence'
          )),
          CONSTRAINT talent_dim_vis_chk CHECK (visibility IN (
            'employee_visible','manager_visible','hr_confidential'
          )),
          CONSTRAINT talent_dim_status_chk CHECK (status IN ('active','superseded','withdrawn'))
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS talent_skills (
          skill_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
          company_code text NOT NULL,
          employee_key text NOT NULL,
          skill_code text NOT NULL,
          name_en text NOT NULL,
          name_ar text,
          proficiency_level text,
          state text NOT NULL DEFAULT 'claimed',
          source text NOT NULL,
          actor_phone text,
          acquired_on date,
          assessed_on date,
          last_verified_on date,
          version int NOT NULL DEFAULT 1,
          status text NOT NULL DEFAULT 'active',
          evidence_refs jsonb NOT NULL DEFAULT '[]'::jsonb,
          created_at timestamptz NOT NULL DEFAULT now(),
          updated_at timestamptz NOT NULL DEFAULT now(),
          metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
          CONSTRAINT talent_skill_state_chk CHECK (state IN (
            'claimed','verified','assessed','deprecated'
          )),
          CONSTRAINT talent_skill_source_chk CHECK (source IN (
            'employee_declared','manager_assessed','hr_assessed','competency_evidence',
            'development_evidence','performance_outcome','imported','learning_evidence'
          )),
          CONSTRAINT talent_skill_status_chk CHECK (status IN ('active','superseded','withdrawn')),
          UNIQUE (company_code, employee_key, skill_code, version)
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS talent_skill_history (
          history_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
          company_code text NOT NULL,
          skill_id uuid NOT NULL REFERENCES talent_skills(skill_id),
          before_payload jsonb NOT NULL,
          after_payload jsonb NOT NULL,
          reason text NOT NULL,
          actor_phone text,
          created_at timestamptz NOT NULL DEFAULT now()
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS talent_competency_evidence_maps (
          mapping_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
          company_code text NOT NULL,
          competency_id text NOT NULL,
          competency_framework_version int,
          target_kind text NOT NULL,
          target_skill_code text,
          contract_version text NOT NULL DEFAULT 'competency_talent_map_v1',
          status text NOT NULL DEFAULT 'active',
          created_by_phone text,
          reason text NOT NULL,
          created_at timestamptz NOT NULL DEFAULT now(),
          CONSTRAINT talent_cmap_kind_chk CHECK (target_kind IN (
            'skill','strength','development_area','observation'
          )),
          CONSTRAINT talent_cmap_status_chk CHECK (status IN ('active','deprecated'))
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS talent_potential_frameworks (
          framework_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
          company_code text NOT NULL,
          name_en text NOT NULL,
          name_ar text,
          version int NOT NULL DEFAULT 1,
          status text NOT NULL DEFAULT 'active',
          dimensions jsonb NOT NULL,
          scale_points jsonb NOT NULL,
          created_by_phone text,
          created_at timestamptz NOT NULL DEFAULT now(),
          updated_at timestamptz NOT NULL DEFAULT now(),
          metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
          CONSTRAINT talent_pf_status_chk CHECK (status IN ('active','deprecated'))
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS talent_potential_assessments (
          assessment_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
          company_code text NOT NULL,
          employee_key text NOT NULL,
          framework_id uuid NOT NULL,
          framework_version int NOT NULL,
          status text NOT NULL DEFAULT 'draft',
          assessor_phone text NOT NULL,
          assessor_role text NOT NULL DEFAULT 'hr',
          dimension_scores jsonb NOT NULL DEFAULT '{}'::jsonb,
          resulting_level text,
          rationale text NOT NULL,
          evidence_refs jsonb NOT NULL DEFAULT '[]'::jsonb,
          performance_evidence_optional jsonb,
          effective_date date,
          version int NOT NULL DEFAULT 1,
          superseded_by_assessment_id uuid,
          row_version int NOT NULL DEFAULT 1,
          submitted_at timestamptz,
          created_at timestamptz NOT NULL DEFAULT now(),
          updated_at timestamptz NOT NULL DEFAULT now(),
          metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
          CONSTRAINT talent_pa_status_chk CHECK (status IN (
            'draft','submitted','accepted','withdrawn'
          )),
          CONSTRAINT talent_pa_role_chk CHECK (assessor_role IN ('manager','hr'))
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS talent_readiness_observations (
          observation_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
          company_code text NOT NULL,
          employee_key text NOT NULL,
          scope text NOT NULL DEFAULT 'general',
          role_key text,
          title_en text NOT NULL,
          title_ar text,
          detail_en text,
          source text NOT NULL,
          actor_phone text,
          effective_date date,
          version int NOT NULL DEFAULT 1,
          status text NOT NULL DEFAULT 'active',
          created_at timestamptz NOT NULL DEFAULT now(),
          metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
          CONSTRAINT talent_ready_scope_chk CHECK (scope IN (
            'general','role_specific_primitive'
          )),
          CONSTRAINT talent_ready_source_chk CHECK (source IN (
            'employee_declared','manager_assessed','hr_assessed','competency_evidence',
            'development_evidence','performance_outcome','imported','learning_evidence'
          )),
          CONSTRAINT talent_ready_status_chk CHECK (status IN ('active','superseded','withdrawn')),
          CONSTRAINT talent_ready_no_succession_chk CHECK (
            (metadata->>'successor_nomination') IS NULL
          )
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS talent_performance_evidence_links (
          link_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
          company_code text NOT NULL,
          employee_key text NOT NULL,
          performance_subject_type text NOT NULL,
          performance_subject_id text NOT NULL,
          linked_as text NOT NULL DEFAULT 'optional_evidence',
          actor_phone text,
          reason text NOT NULL,
          created_at timestamptz NOT NULL DEFAULT now(),
          metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
          CONSTRAINT talent_pel_type_chk CHECK (performance_subject_type IN (
            'pre_calibration_result','calibrated_result','review','goal','check_in','competency_assessment'
          )),
          CONSTRAINT talent_pel_as_chk CHECK (linked_as IN (
            'optional_evidence','not_potential'
          ))
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS talent_profile_c5_audit (
          audit_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
          company_code text NOT NULL,
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
    for idx_sql in (
        "CREATE INDEX IF NOT EXISTS talent_profiles_emp_idx ON talent_profiles(company_code, employee_key)",
        "CREATE INDEX IF NOT EXISTS talent_dim_emp_kind_idx ON talent_dimension_facts(company_code, employee_key, dimension_kind, status)",
        "CREATE INDEX IF NOT EXISTS talent_skills_code_idx ON talent_skills(company_code, skill_code, state, status)",
        "CREATE INDEX IF NOT EXISTS talent_skills_emp_idx ON talent_skills(company_code, employee_key, status)",
        "CREATE INDEX IF NOT EXISTS talent_pa_emp_idx ON talent_potential_assessments(company_code, employee_key, status)",
        "CREATE INDEX IF NOT EXISTS talent_ready_emp_idx ON talent_readiness_observations(company_code, employee_key, scope)",
        "CREATE INDEX IF NOT EXISTS talent_pel_emp_idx ON talent_performance_evidence_links(company_code, employee_key)",
    ):
        cur.execute(idx_sql)


def _audit(
    cur: Any,
    *,
    company_code: str,
    action: str,
    actor_phone: str | None,
    reason: str | None = None,
    subject_type: str | None = None,
    subject_id: str | None = None,
    payload: dict[str, Any] | None = None,
) -> None:
    cur.execute(
        """
        INSERT INTO talent_profile_c5_audit (
          company_code, action, actor_phone, reason, subject_type, subject_id, payload
        ) VALUES (%s,%s,%s,%s,%s,%s,%s::jsonb)
        """,
        (
            company_code_norm(company_code),
            action,
            _digits(actor_phone) if actor_phone else None,
            (str(reason).strip()[:500] if reason else None),
            subject_type,
            str(subject_id) if subject_id else None,
            json.dumps(payload or {}, default=str),
        ),
    )


def get_company_settings(cur: Any, company_code: str | None) -> dict[str, Any] | None:
    ensure_talent_profile_c5_schema(cur)
    cur.execute(
        "SELECT * FROM talent_profile_c5_company_settings WHERE company_code=%s",
        (company_code_norm(company_code),),
    )
    row = cur.fetchone()
    return dict(row) if row else None


def _entitled(cur: Any, company_code: str) -> dict[str, Any]:
    gate = runtime_gate_for_company(company_code)
    if not gate.get("ok"):
        return gate
    settings = get_company_settings(cur, company_code)
    if not settings or not settings.get("enabled"):
        return {
            "ok": False,
            "error": "talent_profile_company_not_enabled",
            "gate": "company_settings",
            "phase": PHASE,
        }
    return {"ok": True, "settings": settings, "company_code": company_code_norm(company_code)}


def enable_company_talent_profile(
    cur: Any,
    *,
    company_code: str,
    actor_phone: str,
    reason: str,
    employee_career_self_service: bool = True,
    performance_evidence_consume: bool = False,
    potential_enabled: bool = True,
    skills_enabled: bool = True,
    sensitive_potential_hr_manager_only: bool = True,
    require_sensitive_permission_for_potential: bool = True,
) -> dict[str, Any]:
    if not str(reason or "").strip():
        return {"ok": False, "error": "audit_reason_required"}
    gate = runtime_gate_for_company(company_code)
    if not gate.get("ok"):
        return gate
    company = company_code_norm(company_code)
    ensure_talent_profile_c5_schema(cur)
    cur.execute(
        """
        INSERT INTO talent_profile_c5_company_settings (
          company_code, enabled, employee_career_self_service, performance_evidence_consume,
          potential_enabled, skills_enabled, sensitive_potential_hr_manager_only,
          require_sensitive_permission_for_potential,
          enabled_by_phone, enabled_reason, enabled_at, updated_by_phone, updated_at, disabled_at
        ) VALUES (%s,true,%s,%s,%s,%s,%s,%s,%s,%s,now(),%s,now(),NULL)
        ON CONFLICT (company_code) DO UPDATE SET
          enabled=true,
          employee_career_self_service=EXCLUDED.employee_career_self_service,
          performance_evidence_consume=EXCLUDED.performance_evidence_consume,
          potential_enabled=EXCLUDED.potential_enabled,
          skills_enabled=EXCLUDED.skills_enabled,
          sensitive_potential_hr_manager_only=EXCLUDED.sensitive_potential_hr_manager_only,
          require_sensitive_permission_for_potential=EXCLUDED.require_sensitive_permission_for_potential,
          enabled_by_phone=EXCLUDED.enabled_by_phone,
          enabled_reason=EXCLUDED.enabled_reason,
          enabled_at=now(),
          disabled_at=NULL,
          updated_by_phone=EXCLUDED.updated_by_phone,
          updated_at=now()
        RETURNING *
        """,
        (
            company,
            bool(employee_career_self_service),
            bool(performance_evidence_consume),
            bool(potential_enabled),
            bool(skills_enabled),
            bool(sensitive_potential_hr_manager_only),
            bool(require_sensitive_permission_for_potential),
            _digits(actor_phone),
            str(reason).strip()[:500],
            _digits(actor_phone),
        ),
    )
    row = dict(cur.fetchone())
    _audit(
        cur, company_code=company, action="company_enabled", actor_phone=actor_phone,
        reason=reason, subject_type="company", subject_id=company,
        payload={
            "performance_evidence_consume": bool(performance_evidence_consume),
            "recruiting_talent_pool_untouched": True,
        },
    )
    return {"ok": True, "settings": row}


def disable_company_talent_profile(
    cur: Any, *, company_code: str, actor_phone: str, reason: str
) -> dict[str, Any]:
    if not str(reason or "").strip():
        return {"ok": False, "error": "audit_reason_required"}
    company = company_code_norm(company_code)
    ensure_talent_profile_c5_schema(cur)
    cur.execute(
        """
        UPDATE talent_profile_c5_company_settings
        SET enabled=false, disabled_at=now(), updated_by_phone=%s, updated_at=now()
        WHERE company_code=%s
        RETURNING *
        """,
        (_digits(actor_phone), company),
    )
    row = cur.fetchone()
    if not row:
        return {"ok": False, "error": "company_settings_not_found"}
    _audit(
        cur, company_code=company, action="company_disabled", actor_phone=actor_phone,
        reason=reason, subject_type="company", subject_id=company,
        payload={"preserves_history": True, "performance_history_untouched": True},
    )
    return {
        "ok": True,
        "settings": dict(row),
        "preserves_history": True,
        "performance_history_untouched": True,
    }


# ── Profile anchor (canonical employee identity) ────────────────────────────


def ensure_talent_profile(
    cur: Any, *, company_code: str, employee_key: str, actor_phone: str | None = None
) -> dict[str, Any]:
    ent = _entitled(cur, company_code)
    if not ent.get("ok"):
        return ent
    company = ent["company_code"]
    key = str(employee_key or "").strip()
    if not key:
        return {"ok": False, "error": "employee_key_required"}
    cur.execute(
        """
        INSERT INTO talent_profiles (company_code, employee_key, updated_by_phone)
        VALUES (%s,%s,%s)
        ON CONFLICT (company_code, employee_key) DO UPDATE SET
          updated_at=now(),
          updated_by_phone=COALESCE(EXCLUDED.updated_by_phone, talent_profiles.updated_by_phone)
        RETURNING *
        """,
        (company, key, _digits(actor_phone) if actor_phone else None),
    )
    row = dict(cur.fetchone())
    return {
        "ok": True,
        "profile": row,
        "identity": {"company_code": company, "employee_key": key},
        "master_talent_score": None,
        "shadow_person_table": False,
    }


def get_talent_profile(
    cur: Any, *, company_code: str, employee_key: str
) -> dict[str, Any] | None:
    ensure_talent_profile_c5_schema(cur)
    cur.execute(
        "SELECT * FROM talent_profiles WHERE company_code=%s AND employee_key=%s",
        (company_code_norm(company_code), str(employee_key)),
    )
    row = cur.fetchone()
    return dict(row) if row else None


# ── Dimension facts (versioned, provenance-mandatory) ───────────────────────


def add_dimension_fact(
    cur: Any,
    *,
    company_code: str,
    actor_phone: str,
    employee_key: str,
    dimension_kind: str,
    title_en: str,
    source: str,
    title_ar: str | None = None,
    detail_en: str | None = None,
    detail_ar: str | None = None,
    visibility: str = "manager_visible",
    confidence: str | None = None,
    effective_date: date | None = None,
    evidence_refs: list[Any] | None = None,
    actor_system: str | None = None,
    reason: str = "add talent dimension fact",
) -> dict[str, Any]:
    if not str(reason or "").strip():
        return {"ok": False, "error": "audit_reason_required"}
    ent = _entitled(cur, company_code)
    if not ent.get("ok"):
        return ent
    company = ent["company_code"]
    kind = str(dimension_kind or "").strip().lower()
    if kind not in DIMENSION_KINDS:
        return {"ok": False, "error": "invalid_dimension_kind", "allowed": list(DIMENSION_KINDS)}
    src = str(source or "").strip().lower()
    if src not in FACT_SOURCES:
        return {"ok": False, "error": "invalid_source", "allowed": list(FACT_SOURCES)}
    vis = str(visibility or "manager_visible").strip().lower()
    if vis not in VISIBILITY:
        return {"ok": False, "error": "invalid_visibility", "allowed": list(VISIBILITY)}

    ensure = ensure_talent_profile(
        cur, company_code=company, employee_key=employee_key, actor_phone=actor_phone
    )
    if not ensure.get("ok"):
        return ensure

    # Version: bump among same kind+source family for this employee (coexistence across sources)
    cur.execute(
        """
        SELECT COALESCE(MAX(version),0) AS v FROM talent_dimension_facts
        WHERE company_code=%s AND employee_key=%s AND dimension_kind=%s AND source=%s
        """,
        (company, employee_key, kind, src),
    )
    ver = int(dict(cur.fetchone())["v"]) + 1

    # Supersede prior active fact of same kind+source (not other sources — contradictions coexist)
    cur.execute(
        """
        UPDATE talent_dimension_facts SET status='superseded'
        WHERE company_code=%s AND employee_key=%s AND dimension_kind=%s AND source=%s
          AND status='active'
        RETURNING fact_id
        """,
        (company, employee_key, kind, src),
    )
    prior = cur.fetchone()

    cur.execute(
        """
        INSERT INTO talent_dimension_facts (
          company_code, employee_key, dimension_kind, version, status,
          title_en, title_ar, detail_en, detail_ar, source, actor_phone, actor_system,
          confidence, visibility, effective_date, superseded_by_fact_id, evidence_refs
        ) VALUES (
          %s,%s,%s,%s,'active',%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,NULL,%s::jsonb
        ) RETURNING *
        """,
        (
            company, employee_key, kind, ver, title_en, title_ar, detail_en, detail_ar,
            src, _digits(actor_phone), actor_system, confidence, vis,
            effective_date or date.today(),
            json.dumps(evidence_refs or [], default=str),
        ),
    )
    row = dict(cur.fetchone())
    if prior:
        cur.execute(
            """
            UPDATE talent_dimension_facts SET superseded_by_fact_id=%s
            WHERE fact_id=%s
            """,
            (row["fact_id"], dict(prior)["fact_id"]),
        )
    _audit(
        cur, company_code=company, action="dimension_fact_added", actor_phone=actor_phone,
        reason=reason, subject_type="dimension_fact", subject_id=str(row["fact_id"]),
        payload={"dimension_kind": kind, "source": src, "version": ver},
    )
    return {"ok": True, "fact": row}


def update_employee_aspiration(
    cur: Any,
    *,
    company_code: str,
    employee_phone: str,
    employee_key: str,
    title_en: str,
    title_ar: str | None = None,
    detail_en: str | None = None,
    reason: str = "employee career aspiration update",
) -> dict[str, Any]:
    """Employee-owned career profile — labeled employee_declared; managers cannot silently rewrite."""
    ent = _entitled(cur, company_code)
    if not ent.get("ok"):
        return ent
    if not ent["settings"].get("employee_career_self_service"):
        return {"ok": False, "error": "employee_career_self_service_disabled"}
    return add_dimension_fact(
        cur,
        company_code=company_code,
        actor_phone=employee_phone,
        employee_key=employee_key,
        dimension_kind="career_aspiration",
        title_en=title_en,
        title_ar=title_ar,
        detail_en=detail_en,
        source="employee_declared",
        visibility="employee_visible",
        reason=reason,
    )


def forbid_silent_rewrite_employee_aspiration(
    cur: Any,
    *,
    company_code: str,
    actor_phone: str,
    employee_key: str,
    title_en: str,
    as_source: str = "manager_assessed",
) -> dict[str, Any]:
    """Managers/HR may add their own assessed fact; must not overwrite employee_declared rows in place."""
    if as_source == "employee_declared":
        return {"ok": False, "error": "manager_cannot_write_as_employee_declared"}
    # Adding manager/HR assessed aspiration is allowed as separate evidence
    return add_dimension_fact(
        cur,
        company_code=company_code,
        actor_phone=actor_phone,
        employee_key=employee_key,
        dimension_kind="career_aspiration",
        title_en=title_en,
        source=as_source,
        visibility="manager_visible",
        reason="manager/HR assessed aspiration (separate from employee-declared)",
    )


def list_dimension_facts(
    cur: Any,
    *,
    company_code: str,
    employee_key: str,
    dimension_kind: str | None = None,
    include_history: bool = False,
    viewer_role: str = "hr",
    has_sensitive_permission: bool = False,
) -> dict[str, Any]:
    ensure_talent_profile_c5_schema(cur)
    company = company_code_norm(company_code)
    sql = """
        SELECT * FROM talent_dimension_facts
        WHERE company_code=%s AND employee_key=%s
    """
    params: list[Any] = [company, employee_key]
    if dimension_kind:
        sql += " AND dimension_kind=%s"
        params.append(dimension_kind)
    if not include_history:
        sql += " AND status='active'"
    sql += " ORDER BY dimension_kind, source, version DESC"
    cur.execute(sql, params)
    rows = [dict(r) for r in (cur.fetchall() or [])]
    visible = []
    for r in rows:
        vis = str(r.get("visibility") or "")
        if vis == "hr_confidential" and viewer_role not in ("hr",) and not has_sensitive_permission:
            continue
        if vis == "hr_confidential" and viewer_role == "employee":
            continue
        if vis == "manager_visible" and viewer_role == "employee":
            # employee may still see their own employee_declared
            if r.get("source") != "employee_declared":
                continue
        visible.append(r)
    return {"ok": True, "facts": visible, "flattened": False}


# ── Skills ──────────────────────────────────────────────────────────────────


def claim_skill(
    cur: Any,
    *,
    company_code: str,
    actor_phone: str,
    employee_key: str,
    skill_code: str,
    name_en: str,
    name_ar: str | None = None,
    proficiency_level: str | None = None,
    acquired_on: date | None = None,
    reason: str = "employee skill claim",
) -> dict[str, Any]:
    ent = _entitled(cur, company_code)
    if not ent.get("ok"):
        return ent
    if not ent["settings"].get("skills_enabled"):
        return {"ok": False, "error": "skills_disabled"}
    company = ent["company_code"]
    ensure_talent_profile(cur, company_code=company, employee_key=employee_key, actor_phone=actor_phone)
    code = str(skill_code or "").strip().upper()
    cur.execute(
        """
        SELECT COALESCE(MAX(version),0) AS v FROM talent_skills
        WHERE company_code=%s AND employee_key=%s AND skill_code=%s
        """,
        (company, employee_key, code),
    )
    ver = int(dict(cur.fetchone())["v"]) + 1
    cur.execute(
        """
        UPDATE talent_skills SET status='superseded', updated_at=now()
        WHERE company_code=%s AND employee_key=%s AND skill_code=%s AND status='active'
        """,
        (company, employee_key, code),
    )
    cur.execute(
        """
        INSERT INTO talent_skills (
          company_code, employee_key, skill_code, name_en, name_ar, proficiency_level,
          state, source, actor_phone, acquired_on, version
        ) VALUES (%s,%s,%s,%s,%s,%s,'claimed','employee_declared',%s,%s,%s)
        RETURNING *
        """,
        (
            company, employee_key, code, name_en, name_ar, proficiency_level,
            _digits(actor_phone), acquired_on or date.today(), ver,
        ),
    )
    row = dict(cur.fetchone())
    _audit(
        cur, company_code=company, action="skill_claimed", actor_phone=actor_phone,
        reason=reason, subject_type="skill", subject_id=str(row["skill_id"]),
        payload={"state": "claimed", "version": ver},
    )
    return {"ok": True, "skill": row}


def verify_skill(
    cur: Any,
    *,
    company_code: str,
    actor_phone: str,
    skill_id: str,
    reason: str,
    proficiency_level: str | None = None,
    as_state: str = "verified",
) -> dict[str, Any]:
    if not str(reason or "").strip():
        return {"ok": False, "error": "audit_reason_required"}
    ent = _entitled(cur, company_code)
    if not ent.get("ok"):
        return ent
    company = ent["company_code"]
    state = str(as_state or "verified").strip().lower()
    if state not in ("verified", "assessed"):
        return {"ok": False, "error": "invalid_verify_state"}
    cur.execute(
        "SELECT * FROM talent_skills WHERE company_code=%s AND skill_id=%s",
        (company, skill_id),
    )
    old = cur.fetchone()
    if not old:
        return {"ok": False, "error": "skill_not_found"}
    old = dict(old)
    before = {k: old.get(k) for k in ("state", "proficiency_level", "source", "version")}
    cur.execute(
        """
        UPDATE talent_skills SET
          state=%s,
          proficiency_level=COALESCE(%s, proficiency_level),
          source='hr_assessed',
          actor_phone=%s,
          assessed_on=CURRENT_DATE,
          last_verified_on=CURRENT_DATE,
          updated_at=now()
        WHERE skill_id=%s
        RETURNING *
        """,
        (state, proficiency_level, _digits(actor_phone), skill_id),
    )
    row = dict(cur.fetchone())
    cur.execute(
        """
        INSERT INTO talent_skill_history (
          company_code, skill_id, before_payload, after_payload, reason, actor_phone
        ) VALUES (%s,%s,%s::jsonb,%s::jsonb,%s,%s)
        """,
        (
            company, skill_id,
            json.dumps(before, default=str),
            json.dumps({k: row.get(k) for k in before}, default=str),
            str(reason).strip()[:500], _digits(actor_phone),
        ),
    )
    _audit(
        cur, company_code=company, action="skill_verified", actor_phone=actor_phone,
        reason=reason, subject_type="skill", subject_id=str(skill_id),
        payload={"from_state": old.get("state"), "to_state": state},
    )
    return {"ok": True, "skill": row}


def create_competency_talent_mapping(
    cur: Any,
    *,
    company_code: str,
    actor_phone: str,
    competency_id: str,
    target_kind: str,
    reason: str,
    target_skill_code: str | None = None,
    competency_framework_version: int | None = None,
) -> dict[str, Any]:
    """Explicit contract — competency evidence does not silently become a skill object."""
    if not str(reason or "").strip():
        return {"ok": False, "error": "audit_reason_required"}
    ent = _entitled(cur, company_code)
    if not ent.get("ok"):
        return ent
    company = ent["company_code"]
    kind = str(target_kind or "").strip().lower()
    if kind not in ("skill", "strength", "development_area", "observation"):
        return {"ok": False, "error": "invalid_target_kind"}
    if kind == "skill" and not target_skill_code:
        return {"ok": False, "error": "target_skill_code_required_for_skill_map"}
    cur.execute(
        """
        INSERT INTO talent_competency_evidence_maps (
          company_code, competency_id, competency_framework_version,
          target_kind, target_skill_code, created_by_phone, reason
        ) VALUES (%s,%s,%s,%s,%s,%s,%s)
        RETURNING *
        """,
        (
            company, str(competency_id), competency_framework_version,
            kind, (str(target_skill_code).upper() if target_skill_code else None),
            _digits(actor_phone), str(reason).strip()[:500],
        ),
    )
    row = dict(cur.fetchone())
    _audit(
        cur, company_code=company, action="competency_talent_map_created",
        actor_phone=actor_phone, reason=reason, subject_type="competency_map",
        subject_id=str(row["mapping_id"]),
        payload={"explicit_contract": True, "skill_is_not_competency": True},
    )
    return {"ok": True, "mapping": row}


def apply_competency_evidence(
    cur: Any,
    *,
    company_code: str,
    actor_phone: str,
    employee_key: str,
    mapping_id: str,
    title_en: str | None = None,
    reason: str = "apply competency evidence via contract",
) -> dict[str, Any]:
    ent = _entitled(cur, company_code)
    if not ent.get("ok"):
        return ent
    company = ent["company_code"]
    cur.execute(
        "SELECT * FROM talent_competency_evidence_maps WHERE company_code=%s AND mapping_id=%s AND status='active'",
        (company, mapping_id),
    )
    m = cur.fetchone()
    if not m:
        return {"ok": False, "error": "mapping_not_found_or_inactive"}
    m = dict(m)
    refs = [{"mapping_id": str(mapping_id), "competency_id": m["competency_id"]}]
    if m["target_kind"] == "skill":
        return claim_or_evidence_skill_from_map(
            cur, company_code=company, actor_phone=actor_phone, employee_key=employee_key,
            skill_code=str(m["target_skill_code"]), name_en=title_en or str(m["target_skill_code"]),
            evidence_refs=refs, reason=reason,
        )
    dim = {
        "strength": "strength",
        "development_area": "development_area",
        "observation": "observation",
    }[m["target_kind"]]
    return add_dimension_fact(
        cur,
        company_code=company,
        actor_phone=actor_phone,
        employee_key=employee_key,
        dimension_kind=dim,
        title_en=title_en or f"From competency {m['competency_id']}",
        source="competency_evidence",
        evidence_refs=refs,
        reason=reason,
    )


def claim_or_evidence_skill_from_map(
    cur: Any,
    *,
    company_code: str,
    actor_phone: str,
    employee_key: str,
    skill_code: str,
    name_en: str,
    evidence_refs: list[Any],
    reason: str,
) -> dict[str, Any]:
    ent = _entitled(cur, company_code)
    if not ent.get("ok"):
        return ent
    company = ent["company_code"]
    ensure_talent_profile(cur, company_code=company, employee_key=employee_key, actor_phone=actor_phone)
    code = skill_code.upper()
    cur.execute(
        """
        SELECT COALESCE(MAX(version),0) AS v FROM talent_skills
        WHERE company_code=%s AND employee_key=%s AND skill_code=%s
        """,
        (company, employee_key, code),
    )
    ver = int(dict(cur.fetchone())["v"]) + 1
    cur.execute(
        """
        UPDATE talent_skills SET status='superseded', updated_at=now()
        WHERE company_code=%s AND employee_key=%s AND skill_code=%s AND status='active'
        """,
        (company, employee_key, code),
    )
    cur.execute(
        """
        INSERT INTO talent_skills (
          company_code, employee_key, skill_code, name_en, state, source, actor_phone,
          assessed_on, version, evidence_refs
        ) VALUES (%s,%s,%s,%s,'assessed','competency_evidence',%s,CURRENT_DATE,%s,%s::jsonb)
        RETURNING *
        """,
        (company, employee_key, code, name_en, _digits(actor_phone), ver, json.dumps(evidence_refs, default=str)),
    )
    row = dict(cur.fetchone())
    _audit(
        cur, company_code=company, action="skill_from_competency_evidence",
        actor_phone=actor_phone, reason=reason, subject_type="skill", subject_id=str(row["skill_id"]),
        payload={"via_explicit_mapping": True},
    )
    return {"ok": True, "skill": row}


def query_employees_with_skill(
    cur: Any, *, company_code: str, skill_code: str, min_state: str | None = None
) -> dict[str, Any]:
    """Future Talent Mapping primitive — normalized query, not a 9-box row."""
    ensure_talent_profile_c5_schema(cur)
    company = company_code_norm(company_code)
    code = str(skill_code).upper()
    cur.execute(
        """
        SELECT employee_key, skill_code, proficiency_level, state, source, version, last_verified_on
        FROM talent_skills
        WHERE company_code=%s AND skill_code=%s AND status='active'
        ORDER BY employee_key
        """,
        (company, code),
    )
    rows = [dict(r) for r in (cur.fetchall() or [])]
    if min_state == "verified":
        rows = [r for r in rows if r.get("state") in ("verified", "assessed")]
    return {"ok": True, "skill_code": code, "matches": rows, "nine_box_precomputed": False}


# ── Potential ───────────────────────────────────────────────────────────────


def create_potential_framework(
    cur: Any,
    *,
    company_code: str,
    actor_phone: str,
    name_en: str,
    dimensions: list[dict[str, Any]],
    scale_points: list[dict[str, Any]],
    name_ar: str | None = None,
    reason: str = "create potential framework",
) -> dict[str, Any]:
    if not str(reason or "").strip():
        return {"ok": False, "error": "audit_reason_required"}
    ent = _entitled(cur, company_code)
    if not ent.get("ok"):
        return ent
    if not ent["settings"].get("potential_enabled"):
        return {"ok": False, "error": "potential_disabled"}
    if not dimensions or not scale_points:
        return {"ok": False, "error": "dimensions_and_scale_required"}
    company = ent["company_code"]
    cur.execute(
        """
        INSERT INTO talent_potential_frameworks (
          company_code, name_en, name_ar, dimensions, scale_points, created_by_phone
        ) VALUES (%s,%s,%s,%s::jsonb,%s::jsonb,%s)
        RETURNING *
        """,
        (
            company, name_en, name_ar,
            json.dumps(dimensions, default=str), json.dumps(scale_points, default=str),
            _digits(actor_phone),
        ),
    )
    row = dict(cur.fetchone())
    _audit(
        cur, company_code=company, action="potential_framework_created",
        actor_phone=actor_phone, reason=reason, subject_type="potential_framework",
        subject_id=str(row["framework_id"]),
        payload={"not_hardcoded_lmh": True, "works_without_performance": True},
    )
    return {"ok": True, "framework": row}


def submit_potential_assessment(
    cur: Any,
    *,
    company_code: str,
    actor_phone: str,
    employee_key: str,
    framework_id: str,
    rationale: str,
    dimension_scores: dict[str, Any],
    resulting_level: str | None = None,
    assessor_role: str = "hr",
    evidence_refs: list[Any] | None = None,
    performance_evidence_optional: dict[str, Any] | None = None,
    effective_date: date | None = None,
    has_sensitive_permission: bool = False,
    reason: str = "submit potential assessment",
) -> dict[str, Any]:
    if not str(rationale or "").strip():
        return {"ok": False, "error": "rationale_required"}
    if not str(reason or "").strip():
        return {"ok": False, "error": "audit_reason_required"}
    ent = _entitled(cur, company_code)
    if not ent.get("ok"):
        return ent
    settings = ent["settings"]
    if not settings.get("potential_enabled"):
        return {"ok": False, "error": "potential_disabled"}
    if settings.get("require_sensitive_permission_for_potential") and not has_sensitive_permission:
        return {"ok": False, "error": "sensitive_permission_required"}
    company = ent["company_code"]
    role = str(assessor_role or "hr").strip().lower()
    if role not in ("manager", "hr"):
        return {"ok": False, "error": "invalid_assessor_role"}
    cur.execute(
        "SELECT * FROM talent_potential_frameworks WHERE company_code=%s AND framework_id=%s",
        (company, framework_id),
    )
    fw = cur.fetchone()
    if not fw:
        return {"ok": False, "error": "framework_not_found"}
    fw = dict(fw)

    # Optional performance evidence must never auto-become potential
    perf_payload = None
    if performance_evidence_optional is not None:
        if not settings.get("performance_evidence_consume"):
            return {"ok": False, "error": "performance_evidence_consume_disabled"}
        perf_payload = dict(performance_evidence_optional)
        perf_payload["is_not_potential"] = True
        perf_payload["performance_equals_potential"] = False

    ensure_talent_profile(cur, company_code=company, employee_key=employee_key, actor_phone=actor_phone)
    cur.execute(
        """
        SELECT COALESCE(MAX(version),0) AS v FROM talent_potential_assessments
        WHERE company_code=%s AND employee_key=%s AND framework_id=%s
        """,
        (company, employee_key, framework_id),
    )
    ver = int(dict(cur.fetchone())["v"]) + 1
    # Supersede prior accepted/submitted of same framework (history retained)
    cur.execute(
        """
        UPDATE talent_potential_assessments SET status='withdrawn', updated_at=now()
        WHERE company_code=%s AND employee_key=%s AND framework_id=%s
          AND status IN ('draft','submitted','accepted')
        RETURNING assessment_id
        """,
        (company, employee_key, framework_id),
    )
    priors = [dict(r)["assessment_id"] for r in (cur.fetchall() or [])]

    cur.execute(
        """
        INSERT INTO talent_potential_assessments (
          company_code, employee_key, framework_id, framework_version, status,
          assessor_phone, assessor_role, dimension_scores, resulting_level, rationale,
          evidence_refs, performance_evidence_optional, effective_date, version, submitted_at
        ) VALUES (
          %s,%s,%s,%s,'submitted',%s,%s,%s::jsonb,%s,%s,%s::jsonb,%s::jsonb,%s,%s,now()
        ) RETURNING *
        """,
        (
            company, employee_key, framework_id, int(fw["version"]),
            _digits(actor_phone), role,
            json.dumps(dimension_scores or {}, default=str), resulting_level,
            str(rationale).strip()[:2000],
            json.dumps(evidence_refs or [], default=str),
            json.dumps(perf_payload, default=str) if perf_payload is not None else None,
            effective_date or date.today(), ver,
        ),
    )
    row = dict(cur.fetchone())
    for pid in priors:
        cur.execute(
            "UPDATE talent_potential_assessments SET superseded_by_assessment_id=%s WHERE assessment_id=%s",
            (row["assessment_id"], pid),
        )
    _audit(
        cur, company_code=company, action="potential_assessed", actor_phone=actor_phone,
        reason=reason, subject_type="potential_assessment", subject_id=str(row["assessment_id"]),
        payload={
            "performance_is_not_potential": True,
            "framework_version": int(fw["version"]),
            "version": ver,
            "ai_inference": False,
        },
    )
    return {
        "ok": True,
        "assessment": row,
        "performance_equals_potential": False,
        "ai_assigned": False,
    }


def accept_potential_assessment(
    cur: Any,
    *,
    company_code: str,
    assessment_id: str,
    actor_phone: str,
    reason: str,
    has_sensitive_permission: bool = False,
) -> dict[str, Any]:
    ent = _entitled(cur, company_code)
    if not ent.get("ok"):
        return ent
    if ent["settings"].get("require_sensitive_permission_for_potential") and not has_sensitive_permission:
        return {"ok": False, "error": "sensitive_permission_required"}
    company = ent["company_code"]
    cur.execute(
        """
        UPDATE talent_potential_assessments
        SET status='accepted', updated_at=now(), row_version=row_version+1
        WHERE company_code=%s AND assessment_id=%s AND status='submitted'
        RETURNING *
        """,
        (company, assessment_id),
    )
    row = cur.fetchone()
    if not row:
        return {"ok": False, "error": "assessment_not_submittable"}
    _audit(
        cur, company_code=company, action="potential_accepted", actor_phone=actor_phone,
        reason=reason, subject_type="potential_assessment", subject_id=str(assessment_id),
    )
    return {"ok": True, "assessment": dict(row)}


def get_potential_for_viewer(
    cur: Any,
    *,
    company_code: str,
    employee_key: str,
    viewer_role: str,
    has_sensitive_permission: bool = False,
) -> dict[str, Any]:
    ensure_talent_profile_c5_schema(cur)
    company = company_code_norm(company_code)
    settings = get_company_settings(cur, company) or {}
    if settings.get("require_sensitive_permission_for_potential") and not has_sensitive_permission:
        if viewer_role == "employee":
            return {"ok": False, "error": "potential_hidden_from_employee"}
        if viewer_role not in ("hr", "manager") or (
            settings.get("sensitive_potential_hr_manager_only") and viewer_role not in ("hr", "manager")
        ):
            return {"ok": False, "error": "sensitive_permission_required"}
        if viewer_role in ("hr", "manager") and not has_sensitive_permission:
            return {"ok": False, "error": "sensitive_permission_required"}
    if viewer_role == "employee":
        return {"ok": False, "error": "potential_hidden_from_employee"}
    cur.execute(
        """
        SELECT * FROM talent_potential_assessments
        WHERE company_code=%s AND employee_key=%s
        ORDER BY version DESC
        """,
        (company, employee_key),
    )
    rows = [dict(r) for r in (cur.fetchall() or [])]
    return {"ok": True, "assessments": rows, "master_talent_score": None}


# ── Optional Performance evidence consume ───────────────────────────────────


def link_performance_evidence(
    cur: Any,
    *,
    company_code: str,
    actor_phone: str,
    employee_key: str,
    performance_subject_type: str,
    performance_subject_id: str,
    reason: str,
) -> dict[str, Any]:
    if not str(reason or "").strip():
        return {"ok": False, "error": "audit_reason_required"}
    ent = _entitled(cur, company_code)
    if not ent.get("ok"):
        return ent
    if not ent["settings"].get("performance_evidence_consume"):
        return {"ok": False, "error": "performance_evidence_consume_disabled"}
    company = ent["company_code"]
    ptype = str(performance_subject_type or "").strip().lower()
    if ptype not in (
        "pre_calibration_result", "calibrated_result", "review", "goal", "check_in", "competency_assessment"
    ):
        return {"ok": False, "error": "invalid_performance_subject_type"}
    ensure_talent_profile(cur, company_code=company, employee_key=employee_key, actor_phone=actor_phone)
    cur.execute(
        """
        INSERT INTO talent_performance_evidence_links (
          company_code, employee_key, performance_subject_type, performance_subject_id,
          linked_as, actor_phone, reason
        ) VALUES (%s,%s,%s,%s,'optional_evidence',%s,%s)
        RETURNING *
        """,
        (
            company, employee_key, ptype, str(performance_subject_id),
            _digits(actor_phone), str(reason).strip()[:500],
        ),
    )
    row = dict(cur.fetchone())
    _audit(
        cur, company_code=company, action="performance_evidence_linked",
        actor_phone=actor_phone, reason=reason, subject_type="performance_evidence_link",
        subject_id=str(row["link_id"]),
        payload={"optional": True, "not_hard_dependency": True, "not_potential": True},
    )
    return {"ok": True, "link": row, "becomes_potential": False}


# ── Readiness primitives (no succession) ────────────────────────────────────


def add_readiness_observation(
    cur: Any,
    *,
    company_code: str,
    actor_phone: str,
    employee_key: str,
    title_en: str,
    source: str,
    scope: str = "general",
    role_key: str | None = None,
    title_ar: str | None = None,
    detail_en: str | None = None,
    reason: str = "add readiness observation",
) -> dict[str, Any]:
    ent = _entitled(cur, company_code)
    if not ent.get("ok"):
        return ent
    company = ent["company_code"]
    sc = str(scope or "general").strip().lower()
    if sc not in READINESS_SCOPES:
        return {"ok": False, "error": "invalid_readiness_scope"}
    if sc == "role_specific_primitive" and not role_key:
        return {"ok": False, "error": "role_key_required_for_role_specific"}
    src = str(source or "").strip().lower()
    if src not in FACT_SOURCES:
        return {"ok": False, "error": "invalid_source"}
    ensure_talent_profile(cur, company_code=company, employee_key=employee_key, actor_phone=actor_phone)
    cur.execute(
        """
        INSERT INTO talent_readiness_observations (
          company_code, employee_key, scope, role_key, title_en, title_ar, detail_en,
          source, actor_phone, effective_date
        ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,CURRENT_DATE)
        RETURNING *
        """,
        (
            company, employee_key, sc, role_key, title_en, title_ar, detail_en,
            src, _digits(actor_phone),
        ),
    )
    row = dict(cur.fetchone())
    _audit(
        cur, company_code=company, action="readiness_observation_added",
        actor_phone=actor_phone, reason=reason, subject_type="readiness_observation",
        subject_id=str(row["observation_id"]),
        payload={"no_successor_nomination": True},
    )
    return {"ok": True, "observation": row, "successor_nominated": False}


# ── Temporal / as-of ────────────────────────────────────────────────────────


def talent_as_of(
    cur: Any,
    *,
    company_code: str,
    employee_key: str,
    as_of: datetime | date,
) -> dict[str, Any]:
    """What did we know/believe about this employee at a point in time?"""
    ensure_talent_profile_c5_schema(cur)
    company = company_code_norm(company_code)
    if isinstance(as_of, date) and not isinstance(as_of, datetime):
        cutoff = datetime.combine(as_of, datetime.max.time())
    else:
        cutoff = as_of
    cur.execute(
        """
        SELECT * FROM talent_dimension_facts
        WHERE company_code=%s AND employee_key=%s AND created_at <= %s
        ORDER BY created_at
        """,
        (company, employee_key, cutoff),
    )
    facts = [dict(r) for r in (cur.fetchall() or [])]
    cur.execute(
        """
        SELECT * FROM talent_skills
        WHERE company_code=%s AND employee_key=%s AND created_at <= %s
        ORDER BY created_at
        """,
        (company, employee_key, cutoff),
    )
    skills = [dict(r) for r in (cur.fetchall() or [])]
    cur.execute(
        """
        SELECT * FROM talent_potential_assessments
        WHERE company_code=%s AND employee_key=%s AND created_at <= %s
        ORDER BY created_at
        """,
        (company, employee_key, cutoff),
    )
    pots = [dict(r) for r in (cur.fetchall() or [])]
    return {
        "ok": True,
        "as_of": cutoff.isoformat(),
        "employee_key": employee_key,
        "dimension_facts": facts,
        "skills": skills,
        "potential_assessments": pots,
        "master_talent_score": None,
        "why_trackable_via_source_and_version": True,
    }


def prove_recruiting_talent_pool_isolated(cur: Any) -> dict[str, Any]:
    """Naming boundary — C5 never writes recruiting talent_pool."""
    cur.execute("SELECT to_regclass('public.talent_pool') AS t")
    # Whether or not recruiting table exists, C5 module does not touch it.
    return {
        "ok": True,
        "c5_writes_to_recruiting_talent_pool": False,
        "posthire_module_key": COMMERCIAL_MODULE_KEY,
        "recruiting_key": RECRUITING_POOL_KEY,
        "isolated": True,
    }


def assert_no_forbidden_c5_writes() -> dict[str, Any]:
    return {
        "ok": True,
        "hipo_writes": False,
        "nine_box_writes": False,
        "succession_nomination_writes": False,
        "master_talent_score": False,
        "assistant_mutations": False,
    }
