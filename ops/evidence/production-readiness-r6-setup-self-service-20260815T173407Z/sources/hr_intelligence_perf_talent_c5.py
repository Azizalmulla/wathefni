#!/usr/bin/env python3
"""Wave 5 C5 — governed Performance and Talent Intelligence.

The tables in this module are company-scoped projections over domain systems of
record. They do not create a recruiting talent pool, infer HiPo designations, or
produce universal employee/talent scores. All formulas run through the C1
Registry evaluator.
"""
from __future__ import annotations

import json
import os
import uuid
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Any

import hr_intelligence_registry_c1 as c1

PHASE = "hr_intelligence_perf_talent_c5"
CONTRACT_VERSION = "hr_intelligence_perf_talent_c5_v1"
PASS_STAMP = "HR_INTELLIGENCE_PERFORMANCE_TALENT_FULL_PASS"
COMMERCIAL_MODULE_KEY = "analytics"
RECRUITING_POOL_QUERIED = False
NINE_BOX_IS_CANONICAL = False
_ON = {"1", "true", "yes", "on"}

GOAL_ATTAINMENT_KEY = "performance.goal_attainment"
KR_ATTAINMENT_KEY = "performance.kr_attainment"
REVIEW_SELF_COMPLETION_KEY = "performance.review_completion.self"
REVIEW_MANAGER_COMPLETION_KEY = "performance.review_completion.manager"
REVIEW_FULL_COMPLETION_KEY = "performance.review_completion.full"
OUTCOME_DISTRIBUTION_KEY = "performance.outcome_distribution"
HIGH_PERFORMER_COUNT_KEY = "performance.high_performer_count"
COMPETENCY_ASSESSED_KEY = "performance.competency_assessed_count"
DEV_ACTIONS_ACTIVE_KEY = "performance.development_actions_active"
DEV_ACTIONS_COMPLETED_KEY = "performance.development_actions_completed"
TALENT_POPULATION_KEY = "talent.population"
POTENTIAL_ASSESSED_KEY = "talent.potential_assessed_count"
HIPO_COUNT_KEY = "talent.hipo_count"
SUCCESSION_COVERAGE_KEY = "talent.succession_coverage"
READY_NOW_COVERAGE_KEY = "talent.ready_now_coverage"
SUCCESSORS_PER_ROLE_KEY = "talent.successors_per_critical_role"
READINESS_DISTRIBUTION_KEY = "talent.readiness_distribution"
UNCOVERED_ROLES_KEY = "talent.uncovered_critical_roles"
BENCH_STRENGTH_KEY = "talent.bench_strength"

FORMULA_KINDS = {
    GOAL_ATTAINMENT_KEY: "perf_goal_attainment",
    KR_ATTAINMENT_KEY: "perf_kr_attainment",
    REVIEW_SELF_COMPLETION_KEY: "perf_review_self_completion",
    REVIEW_MANAGER_COMPLETION_KEY: "perf_review_manager_completion",
    REVIEW_FULL_COMPLETION_KEY: "perf_review_full_completion",
    OUTCOME_DISTRIBUTION_KEY: "perf_outcome_distribution",
    HIGH_PERFORMER_COUNT_KEY: "perf_high_performer_count",
    COMPETENCY_ASSESSED_KEY: "perf_competency_assessed",
    DEV_ACTIONS_ACTIVE_KEY: "perf_dev_actions_active",
    DEV_ACTIONS_COMPLETED_KEY: "perf_dev_actions_completed",
    TALENT_POPULATION_KEY: "talent_population",
    POTENTIAL_ASSESSED_KEY: "talent_potential_count",
    HIPO_COUNT_KEY: "talent_hipo_count",
    SUCCESSION_COVERAGE_KEY: "talent_succession_coverage",
    READY_NOW_COVERAGE_KEY: "talent_ready_now_coverage",
    SUCCESSORS_PER_ROLE_KEY: "talent_successors_per_role",
    READINESS_DISTRIBUTION_KEY: "talent_readiness_distribution",
    UNCOVERED_ROLES_KEY: "talent_uncovered_critical_roles",
    BENCH_STRENGTH_KEY: "talent_bench_strength",
}
ALL_SEMANTIC_KEYS = tuple(FORMULA_KINDS)

PERFORMANCE_KINDS = {kind for key, kind in FORMULA_KINDS.items() if key.startswith("performance.")}
TALENT_KINDS = {kind for key, kind in FORMULA_KINDS.items() if key.startswith("talent.")}

STATUS_LABELS = {
    "draft": {"en": "Draft", "ar": "مسودة"},
    "in_progress": {"en": "In progress", "ar": "قيد التنفيذ"},
    "calibration_ready": {"en": "Calibration ready", "ar": "جاهز للمعايرة"},
    "closed": {"en": "Closed", "ar": "مغلق"},
    "submitted": {"en": "Submitted", "ar": "مقدّم"},
    "accepted": {"en": "Accepted", "ar": "مقبول"},
    "designated": {"en": "Designated", "ar": "مصنّف"},
    "nominated": {"en": "Nominated", "ar": "مرشّح"},
    "withdrawn": {"en": "Withdrawn", "ar": "مسحوب"},
    "active": {"en": "Active", "ar": "نشط"},
    "completed": {"en": "Completed", "ar": "مكتمل"},
    "done": {"en": "Done", "ar": "منجز"},
    "unavailable": {"en": "Unavailable", "ar": "غير متاح"},
    "insufficient_data": {"en": "Insufficient data", "ar": "بيانات غير كافية"},
    "suppressed": {"en": "Suppressed", "ar": "محجوب"},
    "forbidden": {"en": "Forbidden", "ar": "ممنوع"},
    "blocked": {"en": "Blocked", "ar": "محظور"},
}


def _env_on(name: str, default: str = "off") -> bool:
    return (os.environ.get(name) or default).strip().lower() in _ON


def _digits(value: Any) -> str:
    return "".join(ch for ch in str(value or "") if ch.isdigit())


def company_code_norm(company_code: str | None) -> str:
    return str(company_code or "").strip().upper()


def _as_date(value: Any) -> date | None:
    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value)[:10])


def _number(value: Any) -> float:
    return float(value or 0)


def _parse_window(time_window: dict[str, Any]) -> tuple[date | None, date | None]:
    return (
        _as_date(time_window.get("period_start") or time_window.get("start")),
        _as_date(time_window.get("period_end") or time_window.get("end")),
    )


def status_label(status: str | None, *, lang: str = "en") -> str:
    key = str(status or "").strip().lower()
    pack = STATUS_LABELS.get(key) or {"en": key or "unknown", "ar": key or "غير معروف"}
    return str(pack["ar" if lang.lower().startswith("ar") else "en"])


def honesty_payload(*, company_code: str | None = None) -> dict[str, Any]:
    return {
        "phase": PHASE,
        "contract_version": CONTRACT_VERSION,
        "pass_stamp": PASS_STAMP,
        "commercial_module_key": COMMERCIAL_MODULE_KEY,
        "uses_c1_registry_evaluator": True,
        "no_second_analytics_math_engine": True,
        "projections_are_not_alternate_sot": True,
        "post_hire_talent_only": True,
        "recruiting_pool_queried": RECRUITING_POOL_QUERIED,
        "performance_outcome_is_not_hipo": True,
        "potential_is_explicit_only": True,
        "hipo_is_explicit_designation_only": True,
        "nine_box_is_canonical": NINE_BOX_IS_CANONICAL,
        "no_employee_score": True,
        "no_talent_score": True,
        "no_universal_score": True,
        "no_global_readiness_score": True,
        "assistant_mutations": False,
        "company_code": company_code_norm(company_code) if company_code else None,
    }


def rollback_guidance() -> dict[str, Any]:
    return {
        "phase": PHASE,
        "preserves_history": True,
        "steps": [
            "WATHEFNI_HR_INTELLIGENCE_PERF_TALENT_C5=off",
            "Clear WATHEFNI_HR_INTELLIGENCE_PERF_TALENT_COMPANIES",
            "WATHEFNI_ANALYTICS_KILL=on (optional)",
            "C1 Registry, projections, target versions, audit, and evaluations remain intact",
        ],
    }


def runtime_gate_for_company(company_code: str | None) -> dict[str, Any]:
    company = company_code_norm(company_code)
    if not company:
        return {"ok": False, "enabled": False, "error": "company_required", "phase": PHASE}
    if _env_on("WATHEFNI_ANALYTICS_KILL", "off"):
        return {"ok": False, "enabled": False, "error": "analytics_kill_switch", "gate": "kill", "phase": PHASE}
    gate = c1.runtime_gate_for_company(company)
    if not gate.get("ok"):
        return {**gate, "ok": False, "error": "c1_registry_required", "phase": PHASE}
    if not _env_on("WATHEFNI_HR_INTELLIGENCE_PERF_TALENT_C5", "off"):
        return {
            "ok": False, "enabled": False, "error": "hr_intelligence_perf_talent_c5_off",
            "gate": "runtime_flag", "phase": PHASE,
        }
    if not c1.slice_allowlist_admits(company, "WATHEFNI_HR_INTELLIGENCE_PERF_TALENT_COMPANIES"):
        return {
            "ok": False, "enabled": False,
            "error": "hr_intelligence_perf_talent_company_not_allowlisted",
            "gate": "company_allowlist", "phase": PHASE, "company_code": company,
        }
    return {"ok": True, "enabled": True, "company_code": company, "phase": PHASE}


def ensure_hr_intelligence_perf_talent_c5_schema(cur: Any, *, force: bool = False) -> None:
    _ = force
    c1.ensure_hr_intelligence_registry_c1_schema(cur)
    statements = [
        """
        CREATE TABLE IF NOT EXISTS hr_intelligence_c5_company_settings (
          company_code text PRIMARY KEY,
          enabled boolean NOT NULL DEFAULT false,
          goals_module_enabled boolean NOT NULL DEFAULT true,
          reviews_module_enabled boolean NOT NULL DEFAULT true,
          calibration_module_enabled boolean NOT NULL DEFAULT true,
          feedback_module_enabled boolean NOT NULL DEFAULT true,
          talent_profile_module_enabled boolean NOT NULL DEFAULT true,
          succession_module_enabled boolean NOT NULL DEFAULT true,
          nine_box_module_enabled boolean NOT NULL DEFAULT false,
          hipo_module_enabled boolean NOT NULL DEFAULT true,
          min_respondent_threshold integer NOT NULL DEFAULT 3,
          enabled_by_phone text,
          enabled_reason text,
          enabled_at timestamptz,
          disabled_at timestamptz,
          updated_at timestamptz NOT NULL DEFAULT now(),
          CHECK (min_respondent_threshold >= 2)
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS hr_intelligence_perf_objectives (
          row_id uuid PRIMARY KEY, company_code text NOT NULL, objective_key text NOT NULL,
          employee_key text NOT NULL, status text NOT NULL, progress_pct numeric,
          direction text NOT NULL DEFAULT 'increase', baseline numeric, target numeric,
          current numeric, weight numeric NOT NULL DEFAULT 1, target_version integer NOT NULL DEFAULT 1,
          period_start date, period_end date, department text, manager_employee_key text,
          updated_at timestamptz NOT NULL DEFAULT now(),
          UNIQUE (company_code, objective_key)
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS hr_intelligence_perf_krs (
          row_id uuid PRIMARY KEY, company_code text NOT NULL, kr_key text NOT NULL,
          objective_key text NOT NULL, employee_key text NOT NULL, status text NOT NULL,
          progress_pct numeric, direction text NOT NULL DEFAULT 'increase', baseline numeric,
          target numeric, current numeric, weight numeric NOT NULL DEFAULT 1,
          target_version integer NOT NULL DEFAULT 1, updated_at timestamptz NOT NULL DEFAULT now(),
          UNIQUE (company_code, kr_key)
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS hr_intelligence_perf_target_versions (
          row_id uuid PRIMARY KEY, company_code text NOT NULL, entity_type text NOT NULL,
          entity_key text NOT NULL, version integer NOT NULL, target numeric NOT NULL,
          effective_from timestamptz NOT NULL, superseded_at timestamptz,
          created_at timestamptz NOT NULL DEFAULT now(),
          UNIQUE (company_code, entity_type, entity_key, version),
          CHECK (entity_type IN ('objective','kr'))
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS hr_intelligence_perf_review_cycles (
          row_id uuid PRIMARY KEY, company_code text NOT NULL, cycle_key text NOT NULL,
          status text NOT NULL, scale_key text NOT NULL, scale_version text NOT NULL,
          scale_type text NOT NULL, updated_at timestamptz NOT NULL DEFAULT now(),
          UNIQUE (company_code, cycle_key),
          CHECK (status IN ('draft','in_progress','calibration_ready','closed')),
          CHECK (scale_type IN ('numeric','labeled','mixed'))
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS hr_intelligence_perf_review_population (
          row_id uuid PRIMARY KEY, company_code text NOT NULL, cycle_key text NOT NULL,
          employee_key text NOT NULL, self_status text, manager_status text, three60_status text,
          fully_completed boolean NOT NULL DEFAULT false, layer_submitted_rating text,
          layer_pre_calibration_rating text, layer_final_rating text,
          final_locked boolean NOT NULL DEFAULT false, department text,
          manager_employee_key text, updated_at timestamptz NOT NULL DEFAULT now(),
          UNIQUE (company_code, cycle_key, employee_key)
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS hr_intelligence_perf_360_aggregates (
          row_id uuid PRIMARY KEY, company_code text NOT NULL, cycle_key text NOT NULL,
          employee_key text NOT NULL, respondent_count integer NOT NULL,
          aggregate_value numeric, anonymity_ok boolean NOT NULL DEFAULT false,
          updated_at timestamptz NOT NULL DEFAULT now(),
          UNIQUE (company_code, cycle_key, employee_key)
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS hr_intelligence_perf_competencies (
          row_id uuid PRIMARY KEY, company_code text NOT NULL, assessment_key text NOT NULL,
          employee_key text NOT NULL, framework_version text NOT NULL, competency_key text NOT NULL,
          source_role text NOT NULL, score numeric, status text NOT NULL,
          updated_at timestamptz NOT NULL DEFAULT now(),
          UNIQUE (company_code, assessment_key, competency_key, source_role),
          CHECK (source_role IN ('self','manager','other'))
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS hr_intelligence_perf_dev_actions (
          row_id uuid PRIMARY KEY, company_code text NOT NULL, action_key text NOT NULL,
          employee_key text NOT NULL, status text NOT NULL, source text NOT NULL, category text,
          updated_at timestamptz NOT NULL DEFAULT now(),
          UNIQUE (company_code, action_key),
          CHECK (status IN ('proposed','in_progress','done','cancelled','overdue')),
          CHECK (source IN ('review','check_in','competency_gap','manual'))
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS hr_intelligence_talent_profiles (
          row_id uuid PRIMARY KEY, company_code text NOT NULL, employee_key text NOT NULL,
          active boolean NOT NULL DEFAULT true, updated_at timestamptz NOT NULL DEFAULT now(),
          UNIQUE (company_code, employee_key)
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS hr_intelligence_talent_potential (
          row_id uuid PRIMARY KEY, company_code text NOT NULL, assessment_key text NOT NULL,
          employee_key text NOT NULL, framework_version text NOT NULL, status text NOT NULL,
          level text NOT NULL, updated_at timestamptz NOT NULL DEFAULT now(),
          UNIQUE (company_code, assessment_key),
          CHECK (status IN ('submitted','accepted'))
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS hr_intelligence_talent_hipo (
          row_id uuid PRIMARY KEY, company_code text NOT NULL, designation_key text NOT NULL,
          employee_key text NOT NULL, status text NOT NULL,
          inferred_from_nine_box boolean NOT NULL DEFAULT false,
          updated_at timestamptz NOT NULL DEFAULT now(),
          UNIQUE (company_code, designation_key),
          CHECK (inferred_from_nine_box = false)
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS hr_intelligence_talent_critical_roles (
          row_id uuid PRIMARY KEY, company_code text NOT NULL, role_key text NOT NULL,
          title text NOT NULL, active boolean NOT NULL DEFAULT true,
          updated_at timestamptz NOT NULL DEFAULT now(),
          UNIQUE (company_code, role_key)
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS hr_intelligence_talent_nominations (
          row_id uuid PRIMARY KEY, company_code text NOT NULL, nomination_key text NOT NULL,
          role_key text NOT NULL, employee_key text NOT NULL, readiness text NOT NULL,
          status text NOT NULL, updated_at timestamptz NOT NULL DEFAULT now(),
          UNIQUE (company_code, nomination_key),
          CHECK (readiness IN ('ready_now','ready_lt_1y','ready_1_2y','longer_term','not_ready','unassessed'))
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS hr_intelligence_talent_nine_box_snapshots (
          row_id uuid PRIMARY KEY, company_code text NOT NULL, review_key text NOT NULL,
          employee_key text NOT NULL, box_label text NOT NULL, config_version text NOT NULL,
          is_canonical boolean NOT NULL DEFAULT false, updated_at timestamptz NOT NULL DEFAULT now(),
          UNIQUE (company_code, review_key, employee_key),
          CHECK (is_canonical = false)
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS hr_intelligence_c5_audit (
          audit_id bigserial PRIMARY KEY, company_code text, action text NOT NULL,
          actor_phone text, reason text, subject_type text, subject_id text,
          payload jsonb NOT NULL DEFAULT '{}'::jsonb,
          created_at timestamptz NOT NULL DEFAULT now()
        )
        """,
    ]
    for statement in statements:
        cur.execute(statement)


def _audit(
    cur: Any, *, company_code: str, action: str, actor_phone: str,
    reason: str | None = None, subject_type: str | None = None,
    subject_id: str | None = None, payload: dict[str, Any] | None = None,
) -> None:
    cur.execute(
        """
        INSERT INTO hr_intelligence_c5_audit
          (company_code, action, actor_phone, reason, subject_type, subject_id, payload)
        VALUES (%s,%s,%s,%s,%s,%s,%s::jsonb)
        """,
        (
            company_code_norm(company_code), action, _digits(actor_phone),
            str(reason).strip()[:500] if reason else None, subject_type, subject_id,
            json.dumps(payload or {}, default=str),
        ),
    )


def _entitled(cur: Any, company_code: str) -> dict[str, Any]:
    gate = runtime_gate_for_company(company_code)
    if not gate.get("ok"):
        return gate
    company = gate["company_code"]
    ensure_hr_intelligence_perf_talent_c5_schema(cur)
    c1_ent = c1._entitled(cur, company)
    if not c1_ent.get("ok"):
        return {"ok": False, "error": "c1_company_intelligence_disabled", "detail": c1_ent}
    cur.execute("SELECT * FROM hr_intelligence_c5_company_settings WHERE company_code=%s", (company,))
    row = cur.fetchone()
    if not row or not bool(dict(row).get("enabled")):
        return {"ok": False, "error": "company_perf_talent_intelligence_disabled", "company_code": company}
    return {"ok": True, "company_code": company, "settings": dict(row), "c1_settings": c1_ent["settings"]}


def enable_company_perf_talent_intelligence(
    cur: Any, *, company_code: str, actor_phone: str, reason: str,
    goals_module_enabled: bool = True, reviews_module_enabled: bool = True,
    calibration_module_enabled: bool = True, feedback_module_enabled: bool = True,
    talent_profile_module_enabled: bool = True, succession_module_enabled: bool = True,
    nine_box_module_enabled: bool = False, hipo_module_enabled: bool = True,
    min_respondent_threshold: int = 3,
) -> dict[str, Any]:
    if not str(reason or "").strip():
        return {"ok": False, "error": "audit_reason_required"}
    gate = runtime_gate_for_company(company_code)
    if not gate.get("ok"):
        return gate
    if int(min_respondent_threshold) < 2:
        return {"ok": False, "error": "invalid_min_respondent_threshold"}
    company = gate["company_code"]
    c1.enable_company_hr_intelligence(
        cur, company_code=company, actor_phone=actor_phone, reason="c5 requires c1"
    )
    ensure_hr_intelligence_perf_talent_c5_schema(cur)
    values = (
        company, bool(goals_module_enabled), bool(reviews_module_enabled),
        bool(calibration_module_enabled), bool(feedback_module_enabled),
        bool(talent_profile_module_enabled), bool(succession_module_enabled),
        bool(nine_box_module_enabled), bool(hipo_module_enabled),
        int(min_respondent_threshold), _digits(actor_phone), str(reason).strip()[:500],
    )
    cur.execute(
        """
        INSERT INTO hr_intelligence_c5_company_settings (
          company_code, enabled, goals_module_enabled, reviews_module_enabled,
          calibration_module_enabled, feedback_module_enabled, talent_profile_module_enabled,
          succession_module_enabled, nine_box_module_enabled, hipo_module_enabled,
          min_respondent_threshold, enabled_by_phone, enabled_reason,
          enabled_at, disabled_at, updated_at
        ) VALUES (%s,true,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,now(),NULL,now())
        ON CONFLICT (company_code) DO UPDATE SET
          enabled=true, goals_module_enabled=EXCLUDED.goals_module_enabled,
          reviews_module_enabled=EXCLUDED.reviews_module_enabled,
          calibration_module_enabled=EXCLUDED.calibration_module_enabled,
          feedback_module_enabled=EXCLUDED.feedback_module_enabled,
          talent_profile_module_enabled=EXCLUDED.talent_profile_module_enabled,
          succession_module_enabled=EXCLUDED.succession_module_enabled,
          nine_box_module_enabled=EXCLUDED.nine_box_module_enabled,
          hipo_module_enabled=EXCLUDED.hipo_module_enabled,
          min_respondent_threshold=EXCLUDED.min_respondent_threshold,
          enabled_by_phone=EXCLUDED.enabled_by_phone, enabled_reason=EXCLUDED.enabled_reason,
          enabled_at=now(), disabled_at=NULL, updated_at=now()
        RETURNING *
        """,
        values,
    )
    settings = dict(cur.fetchone())
    _audit(cur, company_code=company, action="company_enabled", actor_phone=actor_phone,
           reason=reason, subject_type="company", subject_id=company)
    seed_perf_talent_definitions(cur, actor_phone=actor_phone)
    _register_handlers()
    return {"ok": True, "settings": settings, **honesty_payload(company_code=company)}


def disable_company_perf_talent_intelligence(
    cur: Any, *, company_code: str, actor_phone: str, reason: str
) -> dict[str, Any]:
    if not str(reason or "").strip():
        return {"ok": False, "error": "audit_reason_required"}
    company = company_code_norm(company_code)
    ensure_hr_intelligence_perf_talent_c5_schema(cur)
    cur.execute(
        """
        UPDATE hr_intelligence_c5_company_settings
           SET enabled=false, disabled_at=now(), updated_at=now()
         WHERE company_code=%s RETURNING *
        """,
        (company,),
    )
    row = cur.fetchone()
    _audit(cur, company_code=company, action="company_disabled", actor_phone=actor_phone,
           reason=reason, payload={"preserves_history": True})
    return {"ok": True, "settings": dict(row) if row else None, "preserves_history": True}


def set_module_flags(
    cur: Any, *, company_code: str, actor_phone: str, reason: str,
    goals_module_enabled: bool | None = None,
    reviews_module_enabled: bool | None = None,
    calibration_module_enabled: bool | None = None,
    feedback_module_enabled: bool | None = None,
    talent_profile_module_enabled: bool | None = None,
    succession_module_enabled: bool | None = None,
    nine_box_module_enabled: bool | None = None,
    hipo_module_enabled: bool | None = None,
) -> dict[str, Any]:
    if not str(reason or "").strip():
        return {"ok": False, "error": "audit_reason_required"}
    ent = _entitled(cur, company_code)
    if not ent.get("ok"):
        return ent
    settings, company = ent["settings"], ent["company_code"]
    supplied = {
        "goals_module_enabled": goals_module_enabled,
        "reviews_module_enabled": reviews_module_enabled,
        "calibration_module_enabled": calibration_module_enabled,
        "feedback_module_enabled": feedback_module_enabled,
        "talent_profile_module_enabled": talent_profile_module_enabled,
        "succession_module_enabled": succession_module_enabled,
        "nine_box_module_enabled": nine_box_module_enabled,
        "hipo_module_enabled": hipo_module_enabled,
    }
    values = {key: bool(value) if value is not None else bool(settings[key]) for key, value in supplied.items()}
    cur.execute(
        """
        UPDATE hr_intelligence_c5_company_settings SET
          goals_module_enabled=%s, reviews_module_enabled=%s,
          calibration_module_enabled=%s, feedback_module_enabled=%s,
          talent_profile_module_enabled=%s, succession_module_enabled=%s,
          nine_box_module_enabled=%s, hipo_module_enabled=%s, updated_at=now()
        WHERE company_code=%s RETURNING *
        """,
        (*values.values(), company),
    )
    row = dict(cur.fetchone())
    _audit(cur, company_code=company, action="module_flags_updated", actor_phone=actor_phone,
           reason=reason, payload=values)
    return {"ok": True, "settings": row}


enable = enable_company_perf_talent_intelligence
disable = disable_company_perf_talent_intelligence


def _require_write(cur: Any, company_code: str, reason: str) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    if not str(reason or "").strip():
        return None, {"ok": False, "error": "audit_reason_required"}
    ent = _entitled(cur, company_code)
    if not ent.get("ok"):
        return None, ent
    return ent, None


def record_target_version(
    cur: Any, *, company_code: str, actor_phone: str, entity_type: str,
    entity_key: str, version: int, target: float,
    effective_from: datetime | None = None, reason: str,
) -> dict[str, Any]:
    ent, error = _require_write(cur, company_code, reason)
    if error:
        return error
    company = ent["company_code"]
    entity_type = str(entity_type).lower()
    if entity_type not in {"objective", "kr"}:
        return {"ok": False, "error": "invalid_target_entity_type"}
    effective = effective_from or datetime.now(timezone.utc)
    cur.execute(
        """
        UPDATE hr_intelligence_perf_target_versions
           SET superseded_at=%s
         WHERE company_code=%s AND entity_type=%s AND entity_key=%s
           AND superseded_at IS NULL AND version < %s
        """,
        (effective, company, entity_type, entity_key, int(version)),
    )
    cur.execute(
        """
        INSERT INTO hr_intelligence_perf_target_versions
          (row_id, company_code, entity_type, entity_key, version, target, effective_from)
        VALUES (%s,%s,%s,%s,%s,%s,%s)
        ON CONFLICT (company_code, entity_type, entity_key, version) DO NOTHING
        RETURNING *
        """,
        (str(uuid.uuid4()), company, entity_type, entity_key, int(version), Decimal(str(target)), effective),
    )
    row = cur.fetchone()
    if not row:
        cur.execute(
            """
            SELECT * FROM hr_intelligence_perf_target_versions
             WHERE company_code=%s AND entity_type=%s AND entity_key=%s AND version=%s
            """,
            (company, entity_type, entity_key, int(version)),
        )
        row = cur.fetchone()
    result = dict(row)
    if _number(result["target"]) != float(target):
        return {"ok": False, "error": "target_version_immutable", "target_version": result}
    _audit(cur, company_code=company, action="target_version_recorded", actor_phone=actor_phone,
           reason=reason, subject_type=entity_type, subject_id=entity_key,
           payload={"version": int(version), "target": float(target)})
    return {"ok": True, "target_version": result}


def upsert_objective(
    cur: Any, *, company_code: str, actor_phone: str, objective_key: str,
    employee_key: str, status: str, reason: str, progress_pct: float | None = None,
    direction: str = "increase", baseline: float | None = None, target: float | None = None,
    current: float | None = None, weight: float = 1, target_version: int = 1,
    period_start: date | str | None = None, period_end: date | str | None = None,
    department: str | None = None, manager_employee_key: str | None = None,
) -> dict[str, Any]:
    ent, error = _require_write(cur, company_code, reason)
    if error:
        return error
    company = ent["company_code"]
    cur.execute(
        """
        SELECT target_version FROM hr_intelligence_perf_objectives
         WHERE company_code=%s AND objective_key=%s
        """,
        (company, objective_key),
    )
    existing = cur.fetchone()
    if existing and int(target_version) < int(dict(existing)["target_version"]):
        return {"ok": False, "error": "stale_target_version"}
    if target is not None:
        recorded = record_target_version(
            cur, company_code=company, actor_phone=actor_phone, entity_type="objective",
            entity_key=objective_key, version=target_version, target=target, reason=reason,
        )
        if not recorded.get("ok"):
            return recorded
    cur.execute(
        """
        INSERT INTO hr_intelligence_perf_objectives (
          row_id, company_code, objective_key, employee_key, status, progress_pct,
          direction, baseline, target, current, weight, target_version, period_start,
          period_end, department, manager_employee_key
        ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
        ON CONFLICT (company_code, objective_key) DO UPDATE SET
          employee_key=EXCLUDED.employee_key, status=EXCLUDED.status,
          progress_pct=EXCLUDED.progress_pct, direction=EXCLUDED.direction,
          baseline=EXCLUDED.baseline, target=EXCLUDED.target, current=EXCLUDED.current,
          weight=EXCLUDED.weight, target_version=EXCLUDED.target_version,
          period_start=EXCLUDED.period_start, period_end=EXCLUDED.period_end,
          department=EXCLUDED.department, manager_employee_key=EXCLUDED.manager_employee_key,
          updated_at=now()
        RETURNING *
        """,
        (
            str(uuid.uuid4()), company, objective_key, employee_key, str(status).lower(),
            Decimal(str(progress_pct)) if progress_pct is not None else None, str(direction).lower(),
            Decimal(str(baseline)) if baseline is not None else None,
            Decimal(str(target)) if target is not None else None,
            Decimal(str(current)) if current is not None else None, Decimal(str(weight)),
            int(target_version), _as_date(period_start), _as_date(period_end), department,
            manager_employee_key,
        ),
    )
    row = dict(cur.fetchone())
    _audit(cur, company_code=company, action="objective_upserted", actor_phone=actor_phone,
           reason=reason, subject_type="objective", subject_id=objective_key,
           payload={"target_version": int(target_version), "current_present": current is not None})
    return {"ok": True, "objective": row}


def upsert_kr(
    cur: Any, *, company_code: str, actor_phone: str, kr_key: str,
    objective_key: str, employee_key: str, status: str, reason: str,
    progress_pct: float | None = None, direction: str = "increase",
    baseline: float | None = None, target: float | None = None,
    current: float | None = None, weight: float = 1, target_version: int = 1,
) -> dict[str, Any]:
    ent, error = _require_write(cur, company_code, reason)
    if error:
        return error
    company = ent["company_code"]
    cur.execute(
        """
        SELECT target_version FROM hr_intelligence_perf_krs
         WHERE company_code=%s AND kr_key=%s
        """,
        (company, kr_key),
    )
    existing = cur.fetchone()
    if existing and int(target_version) < int(dict(existing)["target_version"]):
        return {"ok": False, "error": "stale_target_version"}
    if target is not None:
        recorded = record_target_version(
            cur, company_code=company, actor_phone=actor_phone, entity_type="kr",
            entity_key=kr_key, version=target_version, target=target, reason=reason,
        )
        if not recorded.get("ok"):
            return recorded
    cur.execute(
        """
        INSERT INTO hr_intelligence_perf_krs (
          row_id, company_code, kr_key, objective_key, employee_key, status,
          progress_pct, direction, baseline, target, current, weight, target_version
        ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
        ON CONFLICT (company_code, kr_key) DO UPDATE SET
          objective_key=EXCLUDED.objective_key, employee_key=EXCLUDED.employee_key,
          status=EXCLUDED.status, progress_pct=EXCLUDED.progress_pct,
          direction=EXCLUDED.direction, baseline=EXCLUDED.baseline,
          target=EXCLUDED.target, current=EXCLUDED.current, weight=EXCLUDED.weight,
          target_version=EXCLUDED.target_version, updated_at=now()
        RETURNING *
        """,
        (
            str(uuid.uuid4()), company, kr_key, objective_key, employee_key,
            str(status).lower(), Decimal(str(progress_pct)) if progress_pct is not None else None,
            str(direction).lower(), Decimal(str(baseline)) if baseline is not None else None,
            Decimal(str(target)) if target is not None else None,
            Decimal(str(current)) if current is not None else None,
            Decimal(str(weight)), int(target_version),
        ),
    )
    row = dict(cur.fetchone())
    _audit(cur, company_code=company, action="kr_upserted", actor_phone=actor_phone,
           reason=reason, subject_type="kr", subject_id=kr_key)
    return {"ok": True, "kr": row}


def apply_objective_target_correction(
    cur: Any, *, company_code: str, actor_phone: str, objective_key: str,
    target: float, reason: str, effective_from: datetime | None = None,
) -> dict[str, Any]:
    ent, error = _require_write(cur, company_code, reason)
    if error:
        return error
    company = ent["company_code"]
    cur.execute(
        "SELECT * FROM hr_intelligence_perf_objectives WHERE company_code=%s AND objective_key=%s",
        (company, objective_key),
    )
    prior = cur.fetchone()
    if not prior:
        return {"ok": False, "error": "objective_not_found"}
    old = dict(prior)
    new_version = int(old["target_version"]) + 1
    recorded = record_target_version(
        cur, company_code=company, actor_phone=actor_phone, entity_type="objective",
        entity_key=objective_key, version=new_version, target=target,
        effective_from=effective_from, reason=reason,
    )
    if not recorded.get("ok"):
        return recorded
    cur.execute(
        """
        UPDATE hr_intelligence_perf_objectives
           SET target=%s, target_version=%s, updated_at=now()
         WHERE company_code=%s AND objective_key=%s RETURNING *
        """,
        (Decimal(str(target)), new_version, company, objective_key),
    )
    row = dict(cur.fetchone())
    _audit(cur, company_code=company, action="objective_target_corrected", actor_phone=actor_phone,
           reason=reason, subject_type="objective", subject_id=objective_key,
           payload={"old_version": old["target_version"], "new_version": new_version})
    return {
        "ok": True, "objective": row, "new_target_version": recorded["target_version"],
        "historical_versions_preserved": True,
    }


def upsert_review_cycle(
    cur: Any, *, company_code: str, actor_phone: str, cycle_key: str,
    status: str, scale_key: str, scale_version: str, scale_type: str, reason: str,
) -> dict[str, Any]:
    ent, error = _require_write(cur, company_code, reason)
    if error:
        return error
    company = ent["company_code"]
    st, scale = str(status).lower(), str(scale_type).lower()
    if st not in {"draft", "in_progress", "calibration_ready", "closed"}:
        return {"ok": False, "error": "invalid_review_cycle_status"}
    if scale not in {"numeric", "labeled", "mixed"}:
        return {"ok": False, "error": "invalid_scale_type"}
    cur.execute(
        """
        INSERT INTO hr_intelligence_perf_review_cycles
          (row_id, company_code, cycle_key, status, scale_key, scale_version, scale_type)
        VALUES (%s,%s,%s,%s,%s,%s,%s)
        ON CONFLICT (company_code, cycle_key) DO UPDATE SET
          status=EXCLUDED.status, scale_key=EXCLUDED.scale_key,
          scale_version=EXCLUDED.scale_version, scale_type=EXCLUDED.scale_type,
          updated_at=now()
        RETURNING *
        """,
        (str(uuid.uuid4()), company, cycle_key, st, scale_key, str(scale_version), scale),
    )
    row = dict(cur.fetchone())
    _audit(cur, company_code=company, action="review_cycle_upserted", actor_phone=actor_phone,
           reason=reason, subject_type="review_cycle", subject_id=cycle_key)
    return {"ok": True, "review_cycle": row}


def upsert_review_population(
    cur: Any, *, company_code: str, actor_phone: str, cycle_key: str,
    employee_key: str, reason: str, self_status: str | None = None,
    manager_status: str | None = None, three60_status: str | None = None,
    fully_completed: bool = False, layer_submitted_rating: str | None = None,
    layer_pre_calibration_rating: str | None = None,
    layer_final_rating: str | None = None, final_locked: bool = False,
    department: str | None = None, manager_employee_key: str | None = None,
) -> dict[str, Any]:
    ent, error = _require_write(cur, company_code, reason)
    if error:
        return error
    company = ent["company_code"]
    if final_locked and layer_final_rating is None:
        return {"ok": False, "error": "locked_final_rating_required"}
    cur.execute(
        """
        INSERT INTO hr_intelligence_perf_review_population (
          row_id, company_code, cycle_key, employee_key, self_status, manager_status,
          three60_status, fully_completed, layer_submitted_rating,
          layer_pre_calibration_rating, layer_final_rating, final_locked,
          department, manager_employee_key
        ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
        ON CONFLICT (company_code, cycle_key, employee_key) DO UPDATE SET
          self_status=EXCLUDED.self_status, manager_status=EXCLUDED.manager_status,
          three60_status=EXCLUDED.three60_status, fully_completed=EXCLUDED.fully_completed,
          layer_submitted_rating=EXCLUDED.layer_submitted_rating,
          layer_pre_calibration_rating=EXCLUDED.layer_pre_calibration_rating,
          layer_final_rating=EXCLUDED.layer_final_rating, final_locked=EXCLUDED.final_locked,
          department=EXCLUDED.department, manager_employee_key=EXCLUDED.manager_employee_key,
          updated_at=now()
        RETURNING *
        """,
        (
            str(uuid.uuid4()), company, cycle_key, employee_key,
            str(self_status).lower() if self_status else None,
            str(manager_status).lower() if manager_status else None,
            str(three60_status).lower() if three60_status else None, bool(fully_completed),
            layer_submitted_rating, layer_pre_calibration_rating, layer_final_rating,
            bool(final_locked), department, manager_employee_key,
        ),
    )
    row = dict(cur.fetchone())
    _audit(cur, company_code=company, action="review_population_upserted", actor_phone=actor_phone,
           reason=reason, subject_type="review_population",
           subject_id=f"{cycle_key}:{employee_key}", payload={"final_locked": bool(final_locked)})
    return {"ok": True, "review_population": row}


def upsert_360_aggregate(
    cur: Any, *, company_code: str, actor_phone: str, cycle_key: str,
    employee_key: str, respondent_count: int, aggregate_value: float | None,
    reason: str,
) -> dict[str, Any]:
    ent, error = _require_write(cur, company_code, reason)
    if error:
        return error
    company, settings = ent["company_code"], ent["settings"]
    anonymity_ok = int(respondent_count) >= int(settings["min_respondent_threshold"])
    stored_value = Decimal(str(aggregate_value)) if anonymity_ok and aggregate_value is not None else None
    cur.execute(
        """
        INSERT INTO hr_intelligence_perf_360_aggregates
          (row_id, company_code, cycle_key, employee_key, respondent_count, aggregate_value, anonymity_ok)
        VALUES (%s,%s,%s,%s,%s,%s,%s)
        ON CONFLICT (company_code, cycle_key, employee_key) DO UPDATE SET
          respondent_count=EXCLUDED.respondent_count, aggregate_value=EXCLUDED.aggregate_value,
          anonymity_ok=EXCLUDED.anonymity_ok, updated_at=now()
        RETURNING *
        """,
        (str(uuid.uuid4()), company, cycle_key, employee_key, int(respondent_count), stored_value, anonymity_ok),
    )
    row = dict(cur.fetchone())
    _audit(cur, company_code=company, action="360_aggregate_upserted", actor_phone=actor_phone,
           reason=reason, subject_type="360_aggregate", subject_id=f"{cycle_key}:{employee_key}",
           payload={"respondent_count": int(respondent_count), "anonymity_ok": anonymity_ok,
                    "respondent_identities_stored": False})
    return {"ok": True, "aggregate": row, "respondent_identities_returned": False}


def get_360_aggregate(
    cur: Any, *, company_code: str, cycle_key: str, employee_key: str
) -> dict[str, Any]:
    ent = _entitled(cur, company_code)
    if not ent.get("ok"):
        return {**ent, "status": "unavailable", "value": None}
    cur.execute(
        """
        SELECT respondent_count, aggregate_value, anonymity_ok
          FROM hr_intelligence_perf_360_aggregates
         WHERE company_code=%s AND cycle_key=%s AND employee_key=%s
        """,
        (ent["company_code"], cycle_key, employee_key),
    )
    row = cur.fetchone()
    if not row:
        return {"ok": True, "status": "unavailable", "value": None, "respondent_identities": []}
    item = dict(row)
    if not bool(item["anonymity_ok"]):
        return {
            "ok": True, "status": "suppressed", "value": None, "respondent_identities": [],
            "explain": {"anonymity_fail_closed": True, "respondent_count": item["respondent_count"]},
        }
    return {
        "ok": True, "status": "ok", "value": _number(item["aggregate_value"]),
        "respondent_identities": [], "explain": {"aggregate_only": True},
    }


def _simple_upsert(
    cur: Any, *, company_code: str, actor_phone: str, reason: str,
    table: str, conflict: str, columns: list[str], values: list[Any],
    subject_type: str, subject_id: str,
) -> dict[str, Any]:
    ent, error = _require_write(cur, company_code, reason)
    if error:
        return error
    company = ent["company_code"]
    allowed = {
        "hr_intelligence_perf_competencies", "hr_intelligence_perf_dev_actions",
        "hr_intelligence_talent_profiles", "hr_intelligence_talent_potential",
        "hr_intelligence_talent_hipo", "hr_intelligence_talent_critical_roles",
        "hr_intelligence_talent_nominations", "hr_intelligence_talent_nine_box_snapshots",
    }
    if table not in allowed:
        raise ValueError("unsupported projection table")
    all_columns = ["row_id", "company_code", *columns]
    placeholders = ",".join(["%s"] * len(all_columns))
    updates = ", ".join(f"{column}=EXCLUDED.{column}" for column in columns) + ", updated_at=now()"
    cur.execute(
        f"""
        INSERT INTO {table} ({",".join(all_columns)}) VALUES ({placeholders})
        ON CONFLICT ({conflict}) DO UPDATE SET {updates}
        RETURNING *
        """,
        [str(uuid.uuid4()), company, *values],
    )
    row = dict(cur.fetchone())
    _audit(cur, company_code=company, action=f"{subject_type}_upserted", actor_phone=actor_phone,
           reason=reason, subject_type=subject_type, subject_id=subject_id)
    return {"ok": True, subject_type: row}


def upsert_competency(
    cur: Any, *, company_code: str, actor_phone: str, assessment_key: str,
    employee_key: str, framework_version: str, competency_key: str,
    source_role: str, score: float | None, status: str, reason: str,
) -> dict[str, Any]:
    role = str(source_role).lower()
    if role not in {"self", "manager", "other"}:
        return {"ok": False, "error": "invalid_competency_source_role"}
    return _simple_upsert(
        cur, company_code=company_code, actor_phone=actor_phone, reason=reason,
        table="hr_intelligence_perf_competencies",
        conflict="company_code, assessment_key, competency_key, source_role",
        columns=["assessment_key", "employee_key", "framework_version", "competency_key", "source_role", "score", "status"],
        values=[assessment_key, employee_key, str(framework_version), competency_key, role,
                Decimal(str(score)) if score is not None else None, str(status).lower()],
        subject_type="competency", subject_id=f"{assessment_key}:{competency_key}:{role}",
    )


def upsert_dev_action(
    cur: Any, *, company_code: str, actor_phone: str, action_key: str,
    employee_key: str, status: str, source: str, category: str | None, reason: str,
) -> dict[str, Any]:
    st, src = str(status).lower(), str(source).lower()
    if st not in {"proposed", "in_progress", "done", "cancelled", "overdue"}:
        return {"ok": False, "error": "invalid_dev_action_status"}
    if src not in {"review", "check_in", "competency_gap", "manual"}:
        return {"ok": False, "error": "invalid_dev_action_source"}
    return _simple_upsert(
        cur, company_code=company_code, actor_phone=actor_phone, reason=reason,
        table="hr_intelligence_perf_dev_actions", conflict="company_code, action_key",
        columns=["action_key", "employee_key", "status", "source", "category"],
        values=[action_key, employee_key, st, src, category],
        subject_type="dev_action", subject_id=action_key,
    )


def upsert_talent_profile(
    cur: Any, *, company_code: str, actor_phone: str, employee_key: str,
    active: bool, reason: str,
) -> dict[str, Any]:
    return _simple_upsert(
        cur, company_code=company_code, actor_phone=actor_phone, reason=reason,
        table="hr_intelligence_talent_profiles", conflict="company_code, employee_key",
        columns=["employee_key", "active"], values=[employee_key, bool(active)],
        subject_type="talent_profile", subject_id=employee_key,
    )


def upsert_potential(
    cur: Any, *, company_code: str, actor_phone: str, assessment_key: str,
    employee_key: str, framework_version: str, status: str, level: str, reason: str,
) -> dict[str, Any]:
    st = str(status).lower()
    if st not in {"submitted", "accepted"}:
        return {"ok": False, "error": "invalid_potential_status"}
    return _simple_upsert(
        cur, company_code=company_code, actor_phone=actor_phone, reason=reason,
        table="hr_intelligence_talent_potential", conflict="company_code, assessment_key",
        columns=["assessment_key", "employee_key", "framework_version", "status", "level"],
        values=[assessment_key, employee_key, str(framework_version), st, level],
        subject_type="potential", subject_id=assessment_key,
    )


def upsert_hipo(
    cur: Any, *, company_code: str, actor_phone: str, designation_key: str,
    employee_key: str, status: str, reason: str, inferred_from_nine_box: bool = False,
) -> dict[str, Any]:
    if inferred_from_nine_box:
        return {
            "ok": False, "error": "hipo_inference_forbidden", "inferred_from_nine_box": False,
            "message_en": "HiPo must be an explicit designation; nine-box inference is forbidden.",
            "message_ar": "يجب أن يكون تصنيف الإمكانات العالية صريحاً؛ الاستنتاج من شبكة التسعة محظور.",
        }
    return _simple_upsert(
        cur, company_code=company_code, actor_phone=actor_phone, reason=reason,
        table="hr_intelligence_talent_hipo", conflict="company_code, designation_key",
        columns=["designation_key", "employee_key", "status", "inferred_from_nine_box"],
        values=[designation_key, employee_key, str(status).lower(), False],
        subject_type="hipo", subject_id=designation_key,
    )


def upsert_critical_role(
    cur: Any, *, company_code: str, actor_phone: str, role_key: str,
    title: str, active: bool, reason: str,
) -> dict[str, Any]:
    return _simple_upsert(
        cur, company_code=company_code, actor_phone=actor_phone, reason=reason,
        table="hr_intelligence_talent_critical_roles", conflict="company_code, role_key",
        columns=["role_key", "title", "active"], values=[role_key, title, bool(active)],
        subject_type="critical_role", subject_id=role_key,
    )


def upsert_nomination(
    cur: Any, *, company_code: str, actor_phone: str, nomination_key: str,
    role_key: str, employee_key: str, readiness: str, status: str, reason: str,
) -> dict[str, Any]:
    ready = str(readiness).lower()
    if ready not in {"ready_now", "ready_lt_1y", "ready_1_2y", "longer_term", "not_ready", "unassessed"}:
        return {"ok": False, "error": "invalid_readiness"}
    return _simple_upsert(
        cur, company_code=company_code, actor_phone=actor_phone, reason=reason,
        table="hr_intelligence_talent_nominations", conflict="company_code, nomination_key",
        columns=["nomination_key", "role_key", "employee_key", "readiness", "status"],
        values=[nomination_key, role_key, employee_key, ready, str(status).lower()],
        subject_type="nomination", subject_id=nomination_key,
    )


def upsert_nine_box_snapshot(
    cur: Any, *, company_code: str, actor_phone: str, review_key: str,
    employee_key: str, box_label: str, config_version: str, reason: str,
    is_canonical: bool = False,
) -> dict[str, Any]:
    _ = is_canonical
    result = _simple_upsert(
        cur, company_code=company_code, actor_phone=actor_phone, reason=reason,
        table="hr_intelligence_talent_nine_box_snapshots",
        conflict="company_code, review_key, employee_key",
        columns=["review_key", "employee_key", "box_label", "config_version", "is_canonical"],
        values=[review_key, employee_key, box_label, str(config_version), False],
        subject_type="nine_box_snapshot", subject_id=f"{review_key}:{employee_key}",
    )
    result["is_canonical"] = False
    return result


def _handler_gate(cur: Any, company_code: str) -> dict[str, Any] | None:
    ent = _entitled(cur, company_code)
    if ent.get("ok"):
        return None
    return {
        "status": "unavailable", "value": None, "population_ids": [],
        "explain": {"gate": ent.get("error"), "module_off": True},
    }


def _begin(
    cur: Any, company: str, module_flag: str, module_name: str
) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    gated = _handler_gate(cur, company)
    if gated:
        return None, gated
    cur.execute("SELECT * FROM hr_intelligence_c5_company_settings WHERE company_code=%s", (company,))
    settings = dict(cur.fetchone())
    if not bool(settings.get(module_flag)):
        return settings, {
            "status": "unavailable", "value": None, "population_ids": [],
            "explain": {
                "module_off": True, "module": module_name,
                "message_en": f"{module_name} module disabled — unavailable, not zero.",
                "message_ar": f"وحدة {module_name} معطّلة — غير متاح وليس صفراً.",
            },
        }
    return settings, None


def _rows(cur: Any, table: str, company: str) -> list[dict[str, Any]]:
    allowed = {
        "hr_intelligence_perf_objectives", "hr_intelligence_perf_krs",
        "hr_intelligence_perf_target_versions", "hr_intelligence_perf_review_cycles",
        "hr_intelligence_perf_review_population", "hr_intelligence_perf_360_aggregates",
        "hr_intelligence_perf_competencies", "hr_intelligence_perf_dev_actions",
        "hr_intelligence_talent_profiles", "hr_intelligence_talent_potential",
        "hr_intelligence_talent_hipo", "hr_intelligence_talent_critical_roles",
        "hr_intelligence_talent_nominations", "hr_intelligence_talent_nine_box_snapshots",
    }
    if table not in allowed:
        raise ValueError("unsupported projection table")
    cur.execute(f"SELECT * FROM {table} WHERE company_code=%s", (company,))
    return [dict(row) for row in (cur.fetchall() or [])]


def _manager_scope(row: dict[str, Any], filters: dict[str, Any], actor_role: str) -> bool:
    if actor_role != "manager":
        return True
    allowed = {str(value) for value in (filters.get("manager_scope_keys") or [])}
    if not allowed and filters.get("manager_employee_key"):
        allowed.add(str(filters["manager_employee_key"]))
    return bool(allowed) and str(row.get("manager_employee_key") or "") in allowed


def _manager_employee_keys(
    cur: Any, company: str, filters: dict[str, Any], actor_role: str
) -> set[str] | None:
    if actor_role != "manager":
        return None
    return {
        str(row["employee_key"])
        for row in _rows(cur, "hr_intelligence_perf_review_population", company)
        if _manager_scope(row, filters, actor_role)
    }


def _overlaps_window(row: dict[str, Any], start: date | None, end: date | None) -> bool:
    row_start, row_end = _as_date(row.get("period_start")), _as_date(row.get("period_end"))
    if start is not None and row_end is not None and row_end < start:
        return False
    if end is not None and row_start is not None and row_start > end:
        return False
    return True


def _module_for_kind(kind: str) -> tuple[str, str]:
    if kind in {"perf_goal_attainment", "perf_kr_attainment"}:
        return "goals_module_enabled", "goals"
    if kind in {
        "perf_review_self_completion", "perf_review_manager_completion",
        "perf_review_full_completion", "perf_competency_assessed",
    }:
        return "reviews_module_enabled", "reviews"
    if kind in {"perf_outcome_distribution", "perf_high_performer_count"}:
        return "calibration_module_enabled", "calibration"
    if kind in {"perf_dev_actions_active", "perf_dev_actions_completed"}:
        return "feedback_module_enabled", "feedback/development"
    if kind == "talent_hipo_count":
        return "hipo_module_enabled", "HiPo"
    if kind in {
        "talent_succession_coverage", "talent_ready_now_coverage",
        "talent_successors_per_role", "talent_readiness_distribution",
        "talent_uncovered_critical_roles", "talent_bench_strength",
    }:
        return "succession_module_enabled", "succession"
    return "talent_profile_module_enabled", "talent profile"


def _selected_review_rows(
    cur: Any, company: str, filters: dict[str, Any], actor_role: str
) -> list[dict[str, Any]]:
    return [
        row for row in _rows(cur, "hr_intelligence_perf_review_population", company)
        if (not filters.get("cycle_key") or row["cycle_key"] == filters["cycle_key"])
        and (not filters.get("department") or row.get("department") == filters["department"])
        and _manager_scope(row, filters, actor_role)
    ]


def _talent_forbidden(actor_role: str, filters: dict[str, Any]) -> dict[str, Any] | None:
    if actor_role == "manager" and not bool(filters.get("has_talent_permission")):
        return {
            "status": "forbidden", "value": None, "population_ids": [],
            "explain": {
                "permission": "talent_sensitive",
                "message_en": "Talent permission is required for potential, HiPo, and succession intelligence.",
                "message_ar": "يلزم تصريح المواهب لذكاء الإمكانات العالية والخلافة.",
            },
        }
    return None


def _scale_compatible(
    cur: Any, company: str, rows: list[dict[str, Any]], filters: dict[str, Any]
) -> dict[str, Any] | None:
    if not filters.get("require_compatible_scale"):
        return None
    cycle_keys = {str(row["cycle_key"]) for row in rows}
    versions = {
        str(cycle["scale_version"])
        for cycle in _rows(cur, "hr_intelligence_perf_review_cycles", company)
        if str(cycle["cycle_key"]) in cycle_keys
    }
    if len(versions) > 1:
        return {
            "status": "insufficient_data", "value": None,
            "population_ids": [str(row["employee_key"]) for row in rows],
            "explain": {
                "incompatible_scale_versions": sorted(versions),
                "message_en": "Selected review populations use incompatible scale versions.",
                "message_ar": "تستخدم مجموعات المراجعة المحددة إصدارات مقاييس غير متوافقة.",
            },
        }
    return None


def _handler_dispatch(
    cur: Any, *, company_code: str, settings: dict[str, Any],
    formula_contract: dict[str, Any], publication: dict[str, Any],
    filters: dict[str, Any], time_window: dict[str, Any],
    actor_phone: str, actor_role: str,
) -> dict[str, Any]:
    _ = (settings, publication, actor_phone)
    kind = str(formula_contract.get("kind") or "")
    start, end = _parse_window(time_window)
    c5_settings, unavailable = _begin(cur, company_code, *_module_for_kind(kind))
    if unavailable:
        return unavailable
    assert c5_settings is not None
    if filters.get("nine_box_related") and not bool(c5_settings["nine_box_module_enabled"]):
        return {
            "status": "unavailable", "value": None, "population_ids": [],
            "explain": {"nine_box_module_off": True, "nine_box_is_canonical": False},
        }

    if kind in TALENT_KINDS:
        forbidden = _talent_forbidden(actor_role, filters)
        if forbidden:
            return forbidden

    if kind in {"perf_goal_attainment", "perf_kr_attainment"}:
        table = "hr_intelligence_perf_objectives" if kind == "perf_goal_attainment" else "hr_intelligence_perf_krs"
        id_key = "objective_key" if kind == "perf_goal_attainment" else "kr_key"
        objectives = {
            str(row["objective_key"]): row
            for row in _rows(cur, "hr_intelligence_perf_objectives", company_code)
            if _overlaps_window(row, start, end)
        }
        candidates = _rows(cur, table, company_code)
        if kind == "perf_kr_attainment":
            candidates = [
                {**row, **{
                    "department": objectives[str(row["objective_key"])].get("department"),
                    "manager_employee_key": objectives[str(row["objective_key"])].get("manager_employee_key"),
                }}
                for row in candidates
                if str(row["objective_key"]) in objectives
            ]
        rows = [
            row for row in candidates
            if row.get("status") in {"active", "completed"}
            and row.get("current") is not None
            and row.get("progress_pct") is not None
            and (kind != "perf_goal_attainment" or _overlaps_window(row, start, end))
            and (not filters.get("department") or row.get("department") == filters["department"])
            and _manager_scope(row, filters, actor_role)
        ]
        if not rows:
            return {
                "status": "insufficient_data", "value": None, "population_ids": [],
                "explain": {
                    "current_required": True, "progress_invented": False,
                    "message_en": "No objective/KR has both canonical current and progress values.",
                    "message_ar": "لا يوجد هدف أو نتيجة رئيسية بقيمتي التقدم والحالي المعتمدتين.",
                },
            }
        value = sum(_number(row["progress_pct"]) for row in rows) / len(rows)
        return {
            "status": "ok", "value": value, "unit": "percent",
            "population_ids": [str(row[id_key]) for row in rows],
            "explain": {
                "measure": "average_progress_pct", "canonical_current_required": True,
                "missing_current_excluded": True, "progress_invented": False,
            },
        }

    if kind in {
        "perf_review_self_completion", "perf_review_manager_completion",
        "perf_review_full_completion",
    }:
        rows = _selected_review_rows(cur, company_code, filters, actor_role)
        compatible = _scale_compatible(cur, company_code, rows, filters)
        if compatible:
            return compatible
        if not rows:
            return {
                "status": "not_applicable", "value": None, "numerator_value": 0.0,
                "denominator_value": 0.0, "population_ids": [],
                "explain": {"no_review_population": True},
            }
        if kind == "perf_review_self_completion":
            completed = [row for row in rows if row.get("self_status") in {"submitted", "completed"}]
            layer = "self_status"
        elif kind == "perf_review_manager_completion":
            completed = [row for row in rows if row.get("manager_status") in {"submitted", "completed"}]
            layer = "manager_status"
        else:
            completed = [row for row in rows if bool(row.get("fully_completed"))]
            layer = "fully_completed"
        return {
            "status": "ok", "value": len(completed) / len(rows) * 100.0, "unit": "percent",
            "numerator_value": float(len(completed)), "denominator_value": float(len(rows)),
            "population_ids": [str(row["employee_key"]) for row in rows],
            "explain": {"completion_layer": layer, "distinct_completion_states": True},
        }

    if kind in {"perf_outcome_distribution", "perf_high_performer_count"}:
        rows = _selected_review_rows(cur, company_code, filters, actor_role)
        compatible = _scale_compatible(cur, company_code, rows, filters)
        if compatible:
            return compatible
        locked = [row for row in rows if bool(row.get("final_locked")) and row.get("layer_final_rating") is not None]
        if not locked:
            cycle_statuses = {
                str(cycle["status"])
                for cycle in _rows(cur, "hr_intelligence_perf_review_cycles", company_code)
                if not filters.get("cycle_key") or cycle["cycle_key"] == filters["cycle_key"]
            }
            return {
                "status": "insufficient_data", "value": None,
                "population_ids": [str(row["employee_key"]) for row in rows],
                "explain": {
                    "locked_finals_required": True, "fake_finals": False,
                    "cycle_statuses": sorted(cycle_statuses),
                    "performance_outcome_is_not_hipo": True,
                },
            }
        if kind == "perf_high_performer_count":
            qualifying = filters.get("qualifying_final_ratings")
            if not isinstance(qualifying, list) or not qualifying:
                return {
                    "status": "unavailable", "value": None,
                    "population_ids": [str(row["employee_key"]) for row in locked],
                    "explain": {
                        "registry_policy_required": "filters.qualifying_final_ratings",
                        "performance_outcome_is_not_hipo": True,
                        "message_en": "Registry policy must provide qualifying final ratings.",
                        "message_ar": "يجب أن تحدد سياسة السجل التقييمات النهائية المؤهلة.",
                    },
                }
            selected = [row for row in locked if str(row["layer_final_rating"]) in {str(v) for v in qualifying}]
            return {
                "status": "ok", "value": float(len(selected)),
                "population_ids": [str(row["employee_key"]) for row in locked],
                "explain": {
                    "qualifying_final_ratings": qualifying,
                    "matched_employee_ids": [str(row["employee_key"]) for row in selected],
                    "hipo_not_used": True, "performance_outcome_is_not_hipo": True,
                },
            }
        distribution: dict[str, int] = {}
        for row in locked:
            rating = str(row["layer_final_rating"])
            distribution[rating] = distribution.get(rating, 0) + 1
        return {
            "status": "ok", "value": float(len(locked)),
            "population_ids": [str(row["employee_key"]) for row in locked],
            "explain": {
                "distribution": distribution, "final_locked_only": True,
                "performance_outcome_is_not_hipo": True,
            },
        }

    if kind == "perf_competency_assessed":
        manager_employees = _manager_employee_keys(cur, company_code, filters, actor_role)
        rows = [
            row for row in _rows(cur, "hr_intelligence_perf_competencies", company_code)
            if row.get("status") in {"submitted", "accepted", "completed"}
            and (not filters.get("framework_version") or str(row["framework_version"]) == str(filters["framework_version"]))
            and (manager_employees is None or str(row["employee_key"]) in manager_employees)
        ]
        assessment_ids = sorted({str(row["assessment_key"]) for row in rows})
        return {
            "status": "ok", "value": float(len(assessment_ids)), "population_ids": assessment_ids,
            "explain": {
                "framework_versions": sorted({str(row["framework_version"]) for row in rows}),
                "framework_version_preserved": True,
            },
        }

    if kind in {"perf_dev_actions_active", "perf_dev_actions_completed"}:
        rows = _rows(cur, "hr_intelligence_perf_dev_actions", company_code)
        manager_employees = _manager_employee_keys(cur, company_code, filters, actor_role)
        if manager_employees is not None:
            rows = [row for row in rows if str(row["employee_key"]) in manager_employees]
        if kind == "perf_dev_actions_active":
            selected = [row for row in rows if row["status"] in {"proposed", "in_progress", "overdue"}]
        else:
            selected = [row for row in rows if row["status"] == "done"]
        return {
            "status": "ok", "value": float(len(selected)),
            "population_ids": [str(row["action_key"]) for row in selected],
            "explain": {"projection_source": "development_actions", "c3_like_projection": True},
        }

    if kind == "talent_population":
        rows = [row for row in _rows(cur, "hr_intelligence_talent_profiles", company_code) if bool(row["active"])]
        return {
            "status": "ok", "value": float(len(rows)),
            "population_ids": [str(row["employee_key"]) for row in rows],
            "explain": {"post_hire_only": True, "recruiting_pool_queried": False},
        }

    if kind == "talent_potential_count":
        rows = [
            row for row in _rows(cur, "hr_intelligence_talent_potential", company_code)
            if row["status"] == "accepted"
        ]
        if not rows:
            return {
                "status": "unavailable", "value": None, "population_ids": [],
                "explain": {"accepted_assessment_required": True, "performance_not_potential": True},
            }
        return {
            "status": "ok", "value": float(len(rows)),
            "population_ids": [str(row["employee_key"]) for row in rows],
            "explain": {
                "accepted_only": True, "explicit_assessments_only": True,
                "performance_not_potential": True,
                "framework_versions": sorted({str(row["framework_version"]) for row in rows}),
            },
        }

    if kind == "talent_hipo_count":
        all_rows = _rows(cur, "hr_intelligence_talent_hipo", company_code)
        if any(bool(row.get("inferred_from_nine_box")) for row in all_rows):
            return {
                "status": "unavailable", "value": None, "population_ids": [],
                "explain": {"hipo_inference_detected": True, "hipo_inference_forbidden": True},
            }
        rows = [row for row in all_rows if row["status"] == "designated"]
        return {
            "status": "ok", "value": float(len(rows)),
            "population_ids": [str(row["employee_key"]) for row in rows],
            "explain": {
                "designated_only": True, "inferred_from_nine_box": False,
                "performance_outcome_is_not_hipo": True,
            },
        }

    roles = [row for row in _rows(cur, "hr_intelligence_talent_critical_roles", company_code) if bool(row["active"])]
    nominations = [
        row for row in _rows(cur, "hr_intelligence_talent_nominations", company_code)
        if row["status"] == "active"
        and (not filters.get("role_key") or row["role_key"] == filters["role_key"])
    ]
    if filters.get("role_key"):
        roles = [role for role in roles if role["role_key"] == filters["role_key"]]

    if kind == "talent_bench_strength":
        return {
            "status": "unavailable", "value": None,
            "population_ids": [str(row["role_key"]) for row in roles],
            "explain": {
                "black_box_score": False, "global_readiness_score": False,
                "message_en": "Bench strength has no approved transparent Registry formula.",
                "message_ar": "لا توجد صيغة سجل شفافة ومعتمدة لقوة الاحتياط.",
            },
        }

    covered = {str(row["role_key"]) for row in nominations}
    ready_now = {str(row["role_key"]) for row in nominations if row["readiness"] == "ready_now"}
    role_ids = [str(role["role_key"]) for role in roles]

    if kind in {"talent_succession_coverage", "talent_ready_now_coverage"}:
        if not roles:
            return {
                "status": "not_applicable", "value": None, "numerator_value": 0.0,
                "denominator_value": 0.0, "population_ids": [],
                "explain": {"active_critical_roles_required": True},
            }
        selected = covered if kind == "talent_succession_coverage" else ready_now
        return {
            "status": "ok", "value": len(selected) / len(roles) * 100.0, "unit": "percent",
            "numerator_value": float(len(selected)), "denominator_value": float(len(roles)),
            "population_ids": role_ids,
            "explain": {
                "distinct_measure": "any_active_successor" if kind == "talent_succession_coverage" else "ready_now_active_successor",
                "target_specific_readiness": True,
            },
        }

    if kind == "talent_successors_per_role":
        if filters.get("role_key"):
            return {
                "status": "ok", "value": float(len(nominations)),
                "population_ids": [str(row["employee_key"]) for row in nominations],
                "explain": {"role_key": filters["role_key"], "measure": "successor_count"},
            }
        if not roles:
            return {
                "status": "not_applicable", "value": None, "population_ids": [],
                "numerator_value": 0.0, "denominator_value": 0.0,
                "explain": {"active_critical_roles_required": True},
            }
        return {
            "status": "ok", "value": len(nominations) / len(roles),
            "numerator_value": float(len(nominations)), "denominator_value": float(len(roles)),
            "population_ids": role_ids,
            "explain": {"measure": "average_active_successors_per_critical_role"},
        }

    if kind == "talent_readiness_distribution":
        distribution: dict[str, int] = {}
        for row in nominations:
            band = str(row["readiness"])
            distribution[band] = distribution.get(band, 0) + 1
        return {
            "status": "ok", "value": float(len(nominations)),
            "population_ids": [str(row["nomination_key"]) for row in nominations],
            "explain": {
                "distribution": distribution, "target_specific_readiness": True,
                "same_employee_multiple_roles_allowed": True,
            },
        }

    uncovered = [role for role in roles if str(role["role_key"]) not in covered]
    return {
        "status": "ok", "value": float(len(uncovered)),
        "population_ids": role_ids,
        "explain": {
            "uncovered_role_keys": [str(role["role_key"]) for role in uncovered],
            "active_critical_roles_only": True,
        },
    }


def _register_handlers() -> None:
    for formula_kind in FORMULA_KINDS.values():
        c1.register_formula_handler(formula_kind, _handler_dispatch)


def seed_perf_talent_definitions(cur: Any, *, actor_phone: str) -> dict[str, Any]:
    c1.ensure_hr_intelligence_registry_c1_schema(cur)
    created: list[str] = []

    definitions = [
        (GOAL_ATTAINMENT_KEY, "Goal attainment", "تحقق الأهداف", "Average canonical progress for active/completed objectives with current values.", "متوسط التقدم المعتمد للأهداف النشطة أو المكتملة ذات القيمة الحالية.", "percent", "period_average", "performance_aggregate"),
        (KR_ATTAINMENT_KEY, "KR attainment", "تحقق النتائج الرئيسية", "Average canonical progress for active/completed key results with current values.", "متوسط التقدم المعتمد للنتائج الرئيسية النشطة أو المكتملة ذات القيمة الحالية.", "percent", "period_average", "performance_aggregate"),
        (REVIEW_SELF_COMPLETION_KEY, "Self-review completion", "اكتمال التقييم الذاتي", "Self-review submitted/completed population rate.", "نسبة تقديم أو اكتمال التقييم الذاتي.", "percent", "rate_over_window", "performance_aggregate"),
        (REVIEW_MANAGER_COMPLETION_KEY, "Manager-review completion", "اكتمال تقييم المدير", "Manager-review submitted/completed population rate.", "نسبة تقديم أو اكتمال تقييم المدير.", "percent", "rate_over_window", "performance_aggregate"),
        (REVIEW_FULL_COMPLETION_KEY, "Fully completed reviews", "المراجعات المكتملة بالكامل", "Fully completed review population rate.", "نسبة المراجعات المكتملة بالكامل.", "percent", "rate_over_window", "performance_aggregate"),
        (OUTCOME_DISTRIBUTION_KEY, "Final outcome distribution", "توزيع النتائج النهائية", "Distribution of locked final ratings only.", "توزيع التقييمات النهائية المقفلة فقط.", "count", "cohort", "performance_aggregate"),
        (HIGH_PERFORMER_COUNT_KEY, "High performer count", "عدد ذوي الأداء العالي", "Locked finals matching an explicit Registry qualifying-rating policy; never HiPo.", "النتائج النهائية المقفلة المطابقة لسياسة السجل؛ ليست إمكانات عالية.", "count", "cohort", "performance_aggregate"),
        (COMPETENCY_ASSESSED_KEY, "Competency assessments", "تقييمات الكفاءات", "Count of completed/submitted competency assessments by framework version.", "عدد تقييمات الكفاءات المكتملة أو المقدمة حسب إصدار الإطار.", "count", "event_count", "performance_aggregate"),
        (DEV_ACTIONS_ACTIVE_KEY, "Active development actions", "إجراءات التطوير النشطة", "Proposed, in-progress, or overdue development actions.", "إجراءات التطوير المقترحة أو الجارية أو المتأخرة.", "count", "event_count", "performance_aggregate"),
        (DEV_ACTIONS_COMPLETED_KEY, "Completed development actions", "إجراءات التطوير المكتملة", "Development actions explicitly marked done.", "إجراءات التطوير المعلّمة صراحة كمنجزة.", "count", "event_count", "performance_aggregate"),
        (TALENT_POPULATION_KEY, "Post-hire talent population", "مجموعة المواهب بعد التوظيف", "Active post-hire talent profiles; never recruiting candidates.", "ملفات المواهب النشطة بعد التوظيف؛ لا تشمل المرشحين.", "count", "point_in_time", "talent_sensitive"),
        (POTENTIAL_ASSESSED_KEY, "Potential assessed", "تم تقييم الإمكانات", "Accepted explicit potential assessments only.", "تقييمات الإمكانات الصريحة المقبولة فقط.", "count", "point_in_time", "talent_sensitive"),
        (HIPO_COUNT_KEY, "Designated HiPo count", "عدد المصنفين إمكانات عالية", "Explicit designated HiPo records only; never inferred.", "سجلات الإمكانات العالية المصنفة صراحة فقط؛ بلا استنتاج.", "count", "point_in_time", "talent_sensitive"),
        (SUCCESSION_COVERAGE_KEY, "Succession coverage", "تغطية الخلافة", "Active critical roles with at least one active successor.", "الأدوار الحرجة النشطة التي لها خلف نشط واحد على الأقل.", "percent", "rate_over_window", "talent_sensitive"),
        (READY_NOW_COVERAGE_KEY, "Ready-now coverage", "تغطية الجاهزين الآن", "Active critical roles with at least one ready-now successor.", "الأدوار الحرجة النشطة التي لها خلف جاهز الآن.", "percent", "rate_over_window", "talent_sensitive"),
        (SUCCESSORS_PER_ROLE_KEY, "Successors per critical role", "الخلفاء لكل دور حرج", "Average active successors per active critical role, or target-role count.", "متوسط الخلفاء النشطين لكل دور حرج أو عدد دور محدد.", "count", "point_in_time", "talent_sensitive"),
        (READINESS_DISTRIBUTION_KEY, "Readiness distribution", "توزيع الجاهزية", "Active target-specific nominations by readiness band.", "الترشيحات النشطة الخاصة بالهدف حسب فئة الجاهزية.", "count", "cohort", "talent_sensitive"),
        (UNCOVERED_ROLES_KEY, "Uncovered critical roles", "الأدوار الحرجة غير المغطاة", "Active critical roles without an active successor.", "الأدوار الحرجة النشطة بلا خلف نشط.", "count", "point_in_time", "talent_sensitive"),
        (BENCH_STRENGTH_KEY, "Bench strength", "قوة الاحتياط", "Unavailable until a transparent governed formula is approved; no black-box score.", "غير متاح حتى اعتماد صيغة شفافة محكومة؛ لا درجة غامضة.", "unavailable", "point_in_time", "talent_sensitive"),
    ]

    for key, name_en, name_ar, desc_en, desc_ar, unit, semantics, permission in definitions:
        if semantics not in c1.TIME_SEMANTICS:
            raise ValueError(f"invalid C1 time semantics: {semantics}")
        if permission not in c1.PERMISSION_CLASSES:
            raise ValueError(f"invalid C1 permission class: {permission}")
        kind = FORMULA_KINDS[key]
        cur.execute(
            """
            SELECT kpi_definition_id, status, formula_contract
              FROM hr_kpi_definitions WHERE semantic_key=%s
             ORDER BY effective_version DESC LIMIT 1
            """,
            (key,),
        )
        existing = cur.fetchone()
        kwargs = {
            "name_en": name_en, "name_ar": name_ar,
            "description_en": desc_en, "description_ar": desc_ar,
            "business_meaning": desc_en,
            "formula_contract": {
                "kind": kind,
                "sensitive_aggregate": permission == "talent_sensitive",
                "performance_outcome_is_not_hipo": key in {OUTCOME_DISTRIBUTION_KEY, HIGH_PERFORMER_COUNT_KEY},
            },
            "unit": unit, "time_semantics": semantics, "permission_class": permission,
            "status": "published", "numerator": {"description": desc_en},
            "denominator": {"description": "governed denominator"} if semantics == "rate_over_window" else None,
            "supported_dimensions": ["department", "manager", "cycle_key", "role_key", "framework_version"],
            "canonical_source_facts": ["c5_governed_projection"],
            "required_domain_authority": [], "owner": "wave5_c5", "reason": f"c5 seed {key}",
        }
        if existing:
            item = dict(existing)
            contract = item.get("formula_contract")
            if isinstance(contract, str):
                contract = json.loads(contract)
            if not contract or contract.get("kind") != kind:
                out = c1.version_kpi_definition(
                    cur, actor_phone=actor_phone, semantic_key=key,
                    reason=f"c5 activate {key}", updates=kwargs,
                )
                if out.get("ok"):
                    created.append(key)
                    c1.publish_kpi_definition(
                        cur, actor_phone=actor_phone,
                        kpi_definition_id=str(out["definition"]["kpi_definition_id"]),
                        reason="c5 publish refreshed definition",
                    )
            elif item["status"] != "published":
                c1.publish_kpi_definition(
                    cur, actor_phone=actor_phone,
                    kpi_definition_id=str(item["kpi_definition_id"]), reason="c5 publish existing",
                )
            continue
        out = c1.create_kpi_definition(cur, actor_phone=actor_phone, semantic_key=key, **kwargs)
        if out.get("ok"):
            created.append(key)
            c1.publish_kpi_definition(
                cur, actor_phone=actor_phone,
                kpi_definition_id=str(out["definition"]["kpi_definition_id"]),
                reason="c5 publish definition",
            )
    _register_handlers()
    return {"ok": True, "created_semantic_keys": created, "semantic_keys": list(ALL_SEMANTIC_KEYS)}


def publish_perf_talent_kpis_for_company(
    cur: Any, *, company_code: str, actor_phone: str, reason: str
) -> dict[str, Any]:
    if not str(reason or "").strip():
        return {"ok": False, "error": "audit_reason_required"}
    ent = _entitled(cur, company_code)
    if not ent.get("ok"):
        return ent
    company = ent["company_code"]
    seed_perf_talent_definitions(cur, actor_phone=actor_phone)
    published: list[str] = []
    failures: dict[str, Any] = {}
    for key in ALL_SEMANTIC_KEYS:
        result = c1.publish_kpi_for_company(
            cur, company_code=company, actor_phone=actor_phone, semantic_key=key, reason=reason
        )
        if result.get("ok"):
            published.append(key)
        else:
            failures[key] = result.get("error")
    return {
        "ok": len(published) == len(ALL_SEMANTIC_KEYS),
        "published": published, "failures": failures,
        **honesty_payload(company_code=company),
    }


def rebuild_perf_talent_facts(
    cur: Any, *, company_code: str, actor_phone: str, reason: str
) -> dict[str, Any]:
    """Idempotently rebuild C1 facts from stable C5 projection identities."""
    ent, error = _require_write(cur, company_code, reason)
    if error:
        return error
    company = ent["company_code"]
    specs = [
        ("hr_intelligence_perf_objectives", "perf_objective", "objective_key", None),
        ("hr_intelligence_perf_krs", "perf_kr", "kr_key", None),
        ("hr_intelligence_perf_target_versions", "perf_target_version", "entity_key", "version"),
        ("hr_intelligence_perf_review_cycles", "perf_review_cycle", "cycle_key", None),
        ("hr_intelligence_perf_review_population", "perf_review_population", "employee_key", "cycle_key"),
        ("hr_intelligence_perf_360_aggregates", "perf_360_aggregate", "employee_key", "cycle_key"),
        ("hr_intelligence_perf_competencies", "perf_competency", "assessment_key", "competency_key"),
        ("hr_intelligence_perf_dev_actions", "perf_dev_action", "action_key", None),
        ("hr_intelligence_talent_profiles", "talent_profile", "employee_key", None),
        ("hr_intelligence_talent_potential", "talent_potential", "assessment_key", None),
        ("hr_intelligence_talent_hipo", "talent_hipo", "designation_key", None),
        ("hr_intelligence_talent_critical_roles", "talent_critical_role", "role_key", None),
        ("hr_intelligence_talent_nominations", "talent_nomination", "nomination_key", None),
        ("hr_intelligence_talent_nine_box_snapshots", "talent_nine_box_snapshot", "employee_key", "review_key"),
    ]
    counts: dict[str, int] = {}
    idempotent = 0
    for table, fact_type, id_column, second_column in specs:
        rows = _rows(cur, table, company)
        counts[fact_type] = len(rows)
        for row in rows:
            entity_id = str(row[id_column])
            if second_column:
                entity_id = f"{entity_id}:{row[second_column]}"
            measures = {
                key: value for key, value in row.items()
                if key not in {"row_id", "company_code", "updated_at", "department", "manager_employee_key"}
            }
            dimensions = {
                key: row.get(key)
                for key in ("employee_key", "department", "manager_employee_key", "cycle_key", "role_key")
                if row.get(key) is not None
            }
            out = c1.ingest_fact(
                cur, company_code=company, actor_phone=actor_phone,
                fact_type=fact_type, entity_type=fact_type, entity_id=entity_id,
                source_authority="c5_projection", measures=measures, dimensions=dimensions,
                ingest_key=f"c5:{table}:{company}:{entity_id}", reason=reason,
            )
            if out.get("idempotent"):
                idempotent += 1
    _audit(cur, company_code=company, action="facts_rebuilt", actor_phone=actor_phone,
           reason=reason, payload={"counts": counts, "idempotent_updates": idempotent})
    return {"ok": True, "counts": counts, "idempotent_updates": idempotent}


def reconcile_perf_talent_populations(cur: Any, *, company_code: str) -> dict[str, Any]:
    company = company_code_norm(company_code)
    review = {
        str(row["employee_key"])
        for row in _rows(cur, "hr_intelligence_perf_review_population", company)
    }
    potential = {
        str(row["employee_key"])
        for row in _rows(cur, "hr_intelligence_talent_potential", company)
        if row["status"] == "accepted"
    }
    hipo = {
        str(row["employee_key"])
        for row in _rows(cur, "hr_intelligence_talent_hipo", company)
        if row["status"] == "designated" and not bool(row["inferred_from_nine_box"])
    }
    return {
        "ok": True,
        "populations": {
            "performance_outcomes": sorted(review),
            "accepted_potential": sorted(potential),
            "designated_hipo": sorted(hipo),
        },
        "explain": {
            "performance_outcome_is_not_hipo": True,
            "performance_never_becomes_potential": True,
            "hipo_requires_explicit_designation": True,
            "recruiting_pool_queried": False,
        },
    }


def refuse_invented_metric(semantic_key: str) -> dict[str, Any]:
    key = str(semantic_key or "").strip()
    return {
        "ok": False, "error": "metric_not_governed_or_forbidden", "semantic_key": key,
        "invented": False,
        "message_en": "This performance/talent metric is not governed and will not be invented.",
        "message_ar": "مؤشر الأداء/المواهب هذا غير محكوم ولن يتم اختراعه.",
    }


def assistant_explain_metric(
    cur: Any, *, company_code: str, semantic_key: str, actor_phone: str = "assistant"
) -> dict[str, Any]:
    key = str(semantic_key or "").strip()
    if key not in ALL_SEMANTIC_KEYS:
        return refuse_invented_metric(key)
    return c1.assistant_resolve_metric(
        cur, company_code=company_code, semantic_key=key, actor_phone=actor_phone
    )


_register_handlers()
