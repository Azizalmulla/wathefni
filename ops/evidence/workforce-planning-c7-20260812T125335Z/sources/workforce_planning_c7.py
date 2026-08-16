"""Wave 6 C7 — Workforce Planning.

Canonical authority:
  baseline → plan → demand → scenario → assumptions → cost projection →
  compare → approve → explicit execution handoff

Preserve: actual workforce ≠ workforce plan ≠ scenario ≠ approved execution.
Never silently mutate employment, headcount, Recruiting, or Payroll.
JA (C1) is HARD. Recruiting/Comp/Talent OPTIONAL. Assistant mutations OUT.
No AI forecast authority.
"""
from __future__ import annotations

import json
import os
import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any

import job_architecture_c1 as ja

PHASE = "workforce_planning_c7"
CONTRACT_VERSION = "workforce_planning_c7_v1"
PASS_STAMP = "WORKFORCE_PLANNING_FULL_PASS"
COMMERCIAL_MODULE_KEY = "workforce_planning"
FLAG = "WATHEFNI_WORKFORCE_PLANNING_C7"
COMPANIES_FLAG = "WATHEFNI_WORKFORCE_PLANNING_COMPANIES"
_ON = {"1", "true", "yes", "on"}

PLAN_STATES = ("draft", "submitted", "approved", "execution_ready", "closed", "rejected")
SCENARIO_TYPES = ("base", "growth", "constrained", "restructuring", "custom")
DEMAND_TYPES = (
    "new_headcount",
    "replacement",
    "planned_vacancy",
    "planned_reduction",
    "role_mix_change",
)
HORIZONS = ("monthly", "quarterly", "annual")
HANDOFF_TARGETS = ("wave1_requisition_draft", "external_execution", "approved_unexecuted")
TRUTH_PLANES = ("actual", "plan", "scenario", "approved_execution")

STATUS_LABELS = {
    "draft": {"en": "Draft", "ar": "مسودة"},
    "submitted": {"en": "Submitted", "ar": "مُقدَّم"},
    "approved": {"en": "Approved", "ar": "معتمد"},
    "execution_ready": {"en": "Execution ready", "ar": "جاهز للتنفيذ"},
    "closed": {"en": "Closed", "ar": "مغلق"},
    "rejected": {"en": "Rejected", "ar": "مرفوض"},
    "base": {"en": "Base", "ar": "أساسي"},
    "growth": {"en": "Growth", "ar": "نمو"},
    "constrained": {"en": "Constrained", "ar": "مقيّد"},
    "restructuring": {"en": "Restructuring", "ar": "إعادة هيكلة"},
    "new_headcount": {"en": "New headcount", "ar": "رأس مال بشري جديد"},
    "replacement": {"en": "Replacement", "ar": "استبدال"},
    "planned_vacancy": {"en": "Planned vacancy", "ar": "شاغر مخطط"},
    "planned_reduction": {"en": "Planned reduction", "ar": "تخفيض مخطط"},
    "workforce_planning": {"en": "Workforce Planning", "ar": "تخطيط القوى العاملة"},
    "planned_estimated_cost": {"en": "Planned/estimated cost", "ar": "تكلفة مخططة/تقديرية"},
    "actual_finalized_payroll_cost": {"en": "Actual finalized payroll cost", "ar": "تكلفة رواتب فعلية نهائية"},
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


def _as_date(value: date | str | None) -> date | None:
    if value is None:
        return None
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    return date.fromisoformat(str(value)[:10])


def _money(value: Any) -> Decimal:
    return Decimal(str(value))


def honesty_payload(*, company_code: str | None = None) -> dict[str, Any]:
    return {
        "phase": PHASE,
        "contract_version": CONTRACT_VERSION,
        "pass_stamp": PASS_STAMP,
        "commercial_module_key": COMMERCIAL_MODULE_KEY,
        "does_not_own_employee_employment": True,
        "does_not_own_actual_headcount": True,
        "does_not_own_ja_grades": True,
        "does_not_own_requisitions": True,
        "does_not_own_payroll": True,
        "ja_is_hard": True,
        "no_duplicate_planning_job_catalog": True,
        "actual_ne_plan_ne_scenario_ne_approved_execution": True,
        "planned_headcount_never_enters_actual_wave5": True,
        "planned_position_ne_actual_position": True,
        "planned_cost_ne_finalized_payroll_cost": True,
        "recruiting_optional": True,
        "comp_planning_optional": True,
        "talent_optional": True,
        "works_recruiting_off": True,
        "works_payroll_off": True,
        "works_comp_off": True,
        "works_talent_off": True,
        "approved_ne_execution": True,
        "no_auto_post_hire": True,
        "handoff_idempotent": True,
        "no_universal_workforce_gap_score": True,
        "no_ai_forecast_authority": True,
        "currency_explicit": True,
        "assistant_mutations": False,
        "no_second_analytics_engine": True,
        "employee_no_future_plan_leak": True,
        "company_code": company_code_norm(company_code) if company_code else None,
    }


def surface_composition_rules() -> dict[str, Any]:
    return {
        "hr_web": {"primary_planning_surface": True, "structured_not_spreadsheet_chaos": True},
        "hr_mobile": {"intentionally_thin": True, "no_heavy_scenario_authoring": True},
        "manager": {"scoped_propose_review_submit_only": True},
        "employee_app": {"no_workforce_planning_product": True, "no_future_plan_leak": True},
        "assistant": {"mutations": False, "read_explain_deep_link": True},
        "setup": {"owns_horizons_assumptions_handoff_policy": True},
    }


def runtime_gate_for_company(company_code: str | None) -> dict[str, Any]:
    company = company_code_norm(company_code)
    if not company:
        return {"ok": False, "enabled": False, "error": "company_required", "phase": PHASE}
    if not _env_on(FLAG, "off"):
        return {"ok": False, "enabled": False, "error": "workforce_planning_c7_off", "gate": "runtime_flag", "phase": PHASE}
    raw = str(os.environ.get(COMPANIES_FLAG) or "").strip()
    allow = {p.strip().upper() for p in raw.split(",") if p.strip()} if raw else set()
    if not allow:
        return {
            "ok": False,
            "enabled": False,
            "error": "workforce_planning_company_not_allowlisted",
            "gate": "company_allowlist",
            "phase": PHASE,
        }
    if company not in allow:
        return {
            "ok": False,
            "enabled": False,
            "error": "workforce_planning_company_not_allowlisted",
            "gate": "company_allowlist",
            "phase": PHASE,
            "company_code": company,
        }
    ja_gate = ja.runtime_gate_for_company(company)
    if not ja_gate.get("ok"):
        return {
            "ok": False,
            "enabled": False,
            "error": "ja_hard_dependency_unmet",
            "ja_gate": ja_gate,
            "phase": PHASE,
        }
    return {"ok": True, "enabled": True, "company_code": company, "phase": PHASE, "ja_hard": True}


def ensure_workforce_planning_c7_schema(cur: Any, *, force: bool = False) -> None:
    _ = force
    ja.ensure_job_architecture_c1_schema(cur)
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS wfp_company_settings (
          company_code text PRIMARY KEY,
          enabled boolean NOT NULL DEFAULT false,
          default_currency text NOT NULL DEFAULT 'KWD',
          default_horizon text NOT NULL DEFAULT 'quarterly',
          recruiting_handoff_enabled boolean NOT NULL DEFAULT false,
          comp_assumptions_enabled boolean NOT NULL DEFAULT false,
          talent_skills_enabled boolean NOT NULL DEFAULT false,
          employee_plan_visibility boolean NOT NULL DEFAULT false,
          enabled_by_phone text,
          enabled_reason text,
          enabled_at timestamptz,
          disabled_at timestamptz,
          updated_by_phone text,
          updated_at timestamptz NOT NULL DEFAULT now(),
          CHECK (default_horizon IN ('monthly','quarterly','annual')),
          CHECK (employee_plan_visibility = false)
        )
        """
    )
    for ddl in (
        """
        CREATE TABLE IF NOT EXISTS wfp_plans (
          plan_id uuid PRIMARY KEY,
          company_code text NOT NULL,
          code text NOT NULL,
          title_en text NOT NULL,
          title_ar text NOT NULL,
          status text NOT NULL DEFAULT 'draft',
          horizon text NOT NULL DEFAULT 'quarterly',
          currency text NOT NULL DEFAULT 'KWD',
          fiscal_year int,
          period_start date,
          period_end date,
          baseline_id uuid,
          plan_version int NOT NULL DEFAULT 1,
          approved_at timestamptz,
          created_by_phone text,
          created_at timestamptz NOT NULL DEFAULT now(),
          updated_at timestamptz NOT NULL DEFAULT now(),
          UNIQUE (company_code, code, plan_version),
          CHECK (status IN ('draft','submitted','approved','execution_ready','closed','rejected')),
          CHECK (horizon IN ('monthly','quarterly','annual'))
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS wfp_baselines (
          baseline_id uuid PRIMARY KEY,
          company_code text NOT NULL,
          plan_id uuid REFERENCES wfp_plans(plan_id),
          as_of_date date NOT NULL,
          frozen boolean NOT NULL DEFAULT true,
          source_authority text NOT NULL DEFAULT 'employment_org_ja',
          headcount_total int NOT NULL DEFAULT 0,
          currency text NOT NULL DEFAULT 'KWD',
          created_by_phone text,
          created_at timestamptz NOT NULL DEFAULT now(),
          CHECK (source_authority = 'employment_org_ja')
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS wfp_baseline_rows (
          row_id uuid PRIMARY KEY,
          company_code text NOT NULL,
          baseline_id uuid NOT NULL REFERENCES wfp_baselines(baseline_id),
          employee_key text NOT NULL,
          org_unit text NOT NULL DEFAULT '',
          ja_profile_id uuid,
          ja_grade_id uuid,
          ja_level_id uuid,
          cost_input numeric,
          currency text NOT NULL DEFAULT 'KWD',
          UNIQUE (baseline_id, employee_key)
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS wfp_scenarios (
          scenario_id uuid PRIMARY KEY,
          company_code text NOT NULL,
          plan_id uuid NOT NULL REFERENCES wfp_plans(plan_id),
          code text NOT NULL,
          scenario_type text NOT NULL,
          title_en text NOT NULL,
          title_ar text NOT NULL,
          scenario_version int NOT NULL DEFAULT 1,
          status text NOT NULL DEFAULT 'draft',
          parent_scenario_id uuid,
          immutable_when_approved boolean NOT NULL DEFAULT true,
          created_by_phone text,
          created_at timestamptz NOT NULL DEFAULT now(),
          updated_at timestamptz NOT NULL DEFAULT now(),
          UNIQUE (plan_id, code, scenario_version),
          CHECK (scenario_type IN ('base','growth','constrained','restructuring','custom')),
          CHECK (status IN ('draft','submitted','approved','superseded','rejected'))
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS wfp_assumptions (
          assumption_id uuid PRIMARY KEY,
          company_code text NOT NULL,
          scenario_id uuid NOT NULL REFERENCES wfp_scenarios(scenario_id),
          assumption_key text NOT NULL,
          assumption_version int NOT NULL DEFAULT 1,
          value_json jsonb NOT NULL DEFAULT '{}'::jsonb,
          source text NOT NULL DEFAULT 'explicit_planner',
          notes_en text NOT NULL DEFAULT '',
          notes_ar text NOT NULL DEFAULT '',
          created_by_phone text,
          created_at timestamptz NOT NULL DEFAULT now(),
          UNIQUE (scenario_id, assumption_key, assumption_version),
          CHECK (source IN ('explicit_planner','setup_default','comp_band_ref','wave5_turnover_explicit','talent_capability_explicit'))
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS wfp_demand_items (
          demand_id uuid PRIMARY KEY,
          company_code text NOT NULL,
          plan_id uuid NOT NULL REFERENCES wfp_plans(plan_id),
          scenario_id uuid NOT NULL REFERENCES wfp_scenarios(scenario_id),
          demand_type text NOT NULL,
          quantity int NOT NULL,
          org_unit text NOT NULL DEFAULT '',
          location text NOT NULL DEFAULT '',
          ja_profile_id uuid NOT NULL,
          ja_grade_id uuid,
          ja_level_id uuid,
          target_period date,
          reason_en text NOT NULL DEFAULT '',
          reason_ar text NOT NULL DEFAULT '',
          owner_key text NOT NULL DEFAULT '',
          planned_unit_cost numeric,
          currency text NOT NULL DEFAULT 'KWD',
          is_planned_position boolean NOT NULL DEFAULT true,
          is_actual_position boolean NOT NULL DEFAULT false,
          capability_demand jsonb NOT NULL DEFAULT '{}'::jsonb,
          created_by_phone text,
          created_at timestamptz NOT NULL DEFAULT now(),
          CHECK (demand_type IN (
            'new_headcount','replacement','planned_vacancy','planned_reduction','role_mix_change'
          )),
          CHECK (is_planned_position = true),
          CHECK (is_actual_position = false),
          CHECK (quantity <> 0)
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS wfp_gaps (
          gap_id uuid PRIMARY KEY,
          company_code text NOT NULL,
          scenario_id uuid NOT NULL REFERENCES wfp_scenarios(scenario_id),
          definition text NOT NULL,
          ja_profile_id uuid,
          ja_grade_id uuid,
          period_start date,
          period_end date,
          quantity numeric NOT NULL,
          assumptions_ref jsonb NOT NULL DEFAULT '{}'::jsonb,
          created_at timestamptz NOT NULL DEFAULT now(),
          CHECK (definition IN ('planned_demand_vs_baseline','planned_demand_vs_forecast_scenario'))
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS wfp_approvals (
          approval_id uuid PRIMARY KEY,
          company_code text NOT NULL,
          plan_id uuid NOT NULL REFERENCES wfp_plans(plan_id),
          scenario_id uuid REFERENCES wfp_scenarios(scenario_id),
          approver_key text NOT NULL,
          decision text NOT NULL,
          decided_at timestamptz NOT NULL DEFAULT now(),
          CHECK (decision IN ('approved','rejected','revision_requested'))
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS wfp_execution_handoffs (
          handoff_id uuid PRIMARY KEY,
          company_code text NOT NULL,
          plan_id uuid NOT NULL REFERENCES wfp_plans(plan_id),
          scenario_id uuid NOT NULL REFERENCES wfp_scenarios(scenario_id),
          demand_id uuid NOT NULL REFERENCES wfp_demand_items(demand_id),
          target_authority text NOT NULL,
          quantity int NOT NULL,
          status text NOT NULL DEFAULT 'created',
          requisition_id text,
          idempotency_key text NOT NULL,
          employment_mutated_by_wfp boolean NOT NULL DEFAULT false,
          headcount_mutated_by_wfp boolean NOT NULL DEFAULT false,
          job_posted boolean NOT NULL DEFAULT false,
          candidate_created boolean NOT NULL DEFAULT false,
          hire_created boolean NOT NULL DEFAULT false,
          cancelled_at timestamptz,
          created_by_phone text,
          created_at timestamptz NOT NULL DEFAULT now(),
          UNIQUE (company_code, idempotency_key),
          CHECK (target_authority IN ('wave1_requisition_draft','external_execution','approved_unexecuted')),
          CHECK (status IN ('created','replayed','cancelled','failed','partial')),
          CHECK (employment_mutated_by_wfp = false),
          CHECK (headcount_mutated_by_wfp = false),
          CHECK (job_posted = false),
          CHECK (candidate_created = false),
          CHECK (hire_created = false)
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS wfp_wave5_fact_outbox (
          fact_id uuid PRIMARY KEY,
          company_code text NOT NULL,
          fact_type text NOT NULL,
          entity_type text NOT NULL,
          entity_id text NOT NULL,
          truth_plane text NOT NULL,
          payload jsonb NOT NULL,
          created_at timestamptz NOT NULL DEFAULT now(),
          CHECK (truth_plane IN ('actual','plan','scenario','approved_execution')),
          CHECK (truth_plane <> 'actual' OR fact_type LIKE 'wfp.actual_vs_plan%')
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS wfp_audit_events (
          audit_id uuid PRIMARY KEY,
          company_code text NOT NULL,
          actor_phone text,
          action text NOT NULL,
          entity_type text NOT NULL,
          entity_id text NOT NULL,
          detail jsonb NOT NULL DEFAULT '{}'::jsonb,
          created_at timestamptz NOT NULL DEFAULT now()
        )
        """,
    ):
        cur.execute(ddl)
    # Explicitly do NOT create job/grade/actual headcount SoT tables here.


def _audit(cur: Any, *, company: str, actor: str, action: str, entity_type: str, entity_id: str, detail: dict | None = None) -> None:
    cur.execute(
        """
        INSERT INTO wfp_audit_events (audit_id, company_code, actor_phone, action, entity_type, entity_id, detail)
        VALUES (%s,%s,%s,%s,%s,%s,%s::jsonb)
        """,
        (str(uuid.uuid4()), company, _digits(actor), action, entity_type, entity_id, json.dumps(detail or {})),
    )


def _emit(
    cur: Any,
    *,
    company: str,
    fact_type: str,
    entity_type: str,
    entity_id: str,
    truth_plane: str,
    payload: dict,
) -> None:
    if truth_plane not in TRUTH_PLANES:
        raise ValueError("invalid_truth_plane")
    if truth_plane == "actual" and not str(fact_type).startswith("wfp.actual_vs_plan"):
        raise ValueError("actual_truth_plane_forbidden_for_planning_facts")
    clean = {k: v for k, v in dict(payload or {}).items() if k not in {"employee_list", "salary_detail"}}
    clean["truth_plane"] = truth_plane
    cur.execute(
        """
        INSERT INTO wfp_wave5_fact_outbox (fact_id, company_code, fact_type, entity_type, entity_id, truth_plane, payload)
        VALUES (%s,%s,%s,%s,%s,%s,%s::jsonb)
        """,
        (str(uuid.uuid4()), company, fact_type, entity_type, entity_id, truth_plane, json.dumps(clean)),
    )


def _row(cur: Any) -> dict[str, Any] | None:
    fetched = cur.fetchone()
    return dict(fetched) if fetched else None


def enable_company_workforce_planning(cur: Any, *, company_code: str, actor_phone: str, reason: str, **kwargs: Any) -> dict[str, Any]:
    if not str(reason or "").strip():
        return {"ok": False, "error": "audit_reason_required"}
    gate = runtime_gate_for_company(company_code)
    if not gate.get("ok"):
        return gate
    company = gate["company_code"]
    ensure_workforce_planning_c7_schema(cur)
    if not ja.module_enabled_for_company(cur, company):
        return {"ok": False, "error": "ja_must_be_enabled", "ja_is_hard": True}
    horizon = str(kwargs.get("default_horizon") or "quarterly")
    if horizon not in HORIZONS:
        return {"ok": False, "error": "invalid_horizon"}
    currency = str(kwargs.get("default_currency") or "KWD").upper()
    cur.execute(
        """
        INSERT INTO wfp_company_settings (
          company_code, enabled, default_currency, default_horizon,
          recruiting_handoff_enabled, comp_assumptions_enabled, talent_skills_enabled,
          employee_plan_visibility, enabled_by_phone, enabled_reason, enabled_at,
          disabled_at, updated_by_phone, updated_at
        ) VALUES (%s,true,%s,%s,%s,%s,%s,false,%s,%s,now(),NULL,%s,now())
        ON CONFLICT (company_code) DO UPDATE SET
          enabled=true,
          default_currency=EXCLUDED.default_currency,
          default_horizon=EXCLUDED.default_horizon,
          recruiting_handoff_enabled=EXCLUDED.recruiting_handoff_enabled,
          comp_assumptions_enabled=EXCLUDED.comp_assumptions_enabled,
          talent_skills_enabled=EXCLUDED.talent_skills_enabled,
          employee_plan_visibility=false,
          enabled_by_phone=EXCLUDED.enabled_by_phone, enabled_reason=EXCLUDED.enabled_reason,
          enabled_at=now(), disabled_at=NULL, updated_by_phone=EXCLUDED.updated_by_phone, updated_at=now()
        RETURNING *
        """,
        (
            company, currency, horizon,
            bool(kwargs.get("recruiting_handoff_enabled", False)),
            bool(kwargs.get("comp_assumptions_enabled", False)),
            bool(kwargs.get("talent_skills_enabled", False)),
            _digits(actor_phone), str(reason).strip()[:500], _digits(actor_phone),
        ),
    )
    row = _row(cur)
    _audit(cur, company=company, actor=actor_phone, action="enable", entity_type="company", entity_id=company, detail={"reason": reason})
    return {"ok": True, "settings": row, "honesty": honesty_payload(company_code=company), "ja_is_hard": True}


def disable_company_workforce_planning(cur: Any, *, company_code: str, actor_phone: str, reason: str) -> dict[str, Any]:
    company = company_code_norm(company_code)
    ensure_workforce_planning_c7_schema(cur)
    cur.execute(
        """
        UPDATE wfp_company_settings
           SET enabled=false, disabled_at=now(), updated_by_phone=%s, updated_at=now()
         WHERE company_code=%s RETURNING *
        """,
        (_digits(actor_phone), company),
    )
    row = _row(cur)
    _audit(cur, company=company, actor=actor_phone, action="disable", entity_type="company", entity_id=company, detail={"reason": reason})
    return {"ok": True, "settings": row, "history_retained": True}


def module_enabled_for_company(cur: Any, company_code: str) -> bool:
    gate = runtime_gate_for_company(company_code)
    if not gate.get("ok"):
        return False
    ensure_workforce_planning_c7_schema(cur)
    cur.execute("SELECT enabled FROM wfp_company_settings WHERE company_code=%s", (gate["company_code"],))
    row = cur.fetchone()
    return bool(row and dict(row).get("enabled"))


def _require_enabled(cur: Any, company_code: str) -> dict[str, Any]:
    gate = runtime_gate_for_company(company_code)
    if not gate.get("ok"):
        return gate
    if not module_enabled_for_company(cur, gate["company_code"]):
        return {"ok": False, "error": "workforce_planning_disabled_for_company", "company_code": gate["company_code"]}
    return {"ok": True, "company_code": gate["company_code"]}


def _settings(cur: Any, company: str) -> dict[str, Any]:
    cur.execute("SELECT * FROM wfp_company_settings WHERE company_code=%s", (company,))
    return _row(cur) or {}


def create_plan(
    cur: Any,
    *,
    company_code: str,
    actor_phone: str,
    code: str,
    title_en: str,
    title_ar: str,
    horizon: str | None = None,
    currency: str | None = None,
    period_start: date | str | None = None,
    period_end: date | str | None = None,
    fiscal_year: int | None = None,
) -> dict[str, Any]:
    ent = _require_enabled(cur, company_code)
    if not ent.get("ok"):
        return ent
    company = ent["company_code"]
    settings = _settings(cur, company)
    h = horizon or settings.get("default_horizon") or "quarterly"
    if h not in HORIZONS:
        return {"ok": False, "error": "invalid_horizon"}
    plan_id = str(uuid.uuid4())
    cur.execute(
        """
        INSERT INTO wfp_plans (
          plan_id, company_code, code, title_en, title_ar, horizon, currency,
          fiscal_year, period_start, period_end, created_by_phone
        ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING *
        """,
        (
            plan_id, company, code.strip(), title_en, title_ar, h,
            (currency or settings.get("default_currency") or "KWD").upper(),
            fiscal_year, _as_date(period_start), _as_date(period_end), _digits(actor_phone),
        ),
    )
    return {"ok": True, "plan": _row(cur), "approved_ne_execution": True}


def freeze_baseline(
    cur: Any,
    *,
    company_code: str,
    actor_phone: str,
    plan_id: str,
    as_of_date: date | str,
    population: list[dict[str, Any]],
) -> dict[str, Any]:
    """Freeze authorized actual workforce snapshot — not a second SoT."""
    ent = _require_enabled(cur, company_code)
    if not ent.get("ok"):
        return ent
    company = ent["company_code"]
    cur.execute("SELECT * FROM wfp_plans WHERE company_code=%s AND plan_id=%s", (company, plan_id))
    plan = _row(cur)
    if not plan:
        return {"ok": False, "error": "plan_not_found"}
    if plan.get("baseline_id"):
        return {"ok": False, "error": "baseline_already_frozen"}
    baseline_id = str(uuid.uuid4())
    for emp in population:
        # JA identities required for planning population rows that claim a role
        profile_id = emp.get("ja_profile_id")
        if profile_id:
            cur.execute(
                "SELECT profile_id FROM ja_job_profile WHERE company_code=%s AND profile_id=%s",
                (company, profile_id),
            )
            if not cur.fetchone():
                return {"ok": False, "error": "ja_profile_required", "ja_is_hard": True}
        cur.execute(
            """
            INSERT INTO wfp_baseline_rows (
              row_id, company_code, baseline_id, employee_key, org_unit,
              ja_profile_id, ja_grade_id, ja_level_id, cost_input, currency
            ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            """,
            (
                str(uuid.uuid4()), company, baseline_id, emp["employee_key"], emp.get("org_unit", ""),
                profile_id, emp.get("ja_grade_id"), emp.get("ja_level_id"),
                emp.get("cost_input"), emp.get("currency") or plan["currency"],
            ),
        )
    cur.execute(
        """
        INSERT INTO wfp_baselines (
          baseline_id, company_code, plan_id, as_of_date, frozen, headcount_total, currency, created_by_phone
        ) VALUES (%s,%s,%s,%s,true,%s,%s,%s) RETURNING *
        """,
        (
            baseline_id, company, plan_id, _as_date(as_of_date), len(population),
            plan["currency"], _digits(actor_phone),
        ),
    )
    baseline = _row(cur)
    cur.execute(
        "UPDATE wfp_plans SET baseline_id=%s, updated_at=now() WHERE plan_id=%s RETURNING *",
        (baseline_id, plan_id),
    )
    return {
        "ok": True,
        "baseline": baseline,
        "frozen": True,
        "source_authority": "employment_org_ja",
        "not_second_actual_sot": True,
        "plan": _row(cur),
    }


def create_scenario(
    cur: Any,
    *,
    company_code: str,
    actor_phone: str,
    plan_id: str,
    code: str,
    scenario_type: str,
    title_en: str,
    title_ar: str,
    parent_scenario_id: str | None = None,
) -> dict[str, Any]:
    ent = _require_enabled(cur, company_code)
    if not ent.get("ok"):
        return ent
    company = ent["company_code"]
    stype = str(scenario_type or "").lower()
    if stype not in SCENARIO_TYPES:
        return {"ok": False, "error": "invalid_scenario_type", "allowed": list(SCENARIO_TYPES)}
    scenario_id = str(uuid.uuid4())
    cur.execute(
        """
        INSERT INTO wfp_scenarios (
          scenario_id, company_code, plan_id, code, scenario_type, title_en, title_ar,
          parent_scenario_id, created_by_phone
        ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING *
        """,
        (
            scenario_id, company, plan_id, code.strip(), stype, title_en, title_ar,
            parent_scenario_id, _digits(actor_phone),
        ),
    )
    return {
        "ok": True,
        "scenario": _row(cur),
        "scenario_distinct_from_baseline": True,
        "scenario_distinct_from_actual": True,
        "no_ai_forecast_authority": True,
    }


def upsert_assumption(
    cur: Any,
    *,
    company_code: str,
    actor_phone: str,
    scenario_id: str,
    assumption_key: str,
    value: dict[str, Any],
    source: str = "explicit_planner",
    notes_en: str = "",
    notes_ar: str = "",
    assumption_version: int = 1,
) -> dict[str, Any]:
    ent = _require_enabled(cur, company_code)
    if not ent.get("ok"):
        return ent
    company = ent["company_code"]
    settings = _settings(cur, company)
    src = str(source or "explicit_planner")
    if src == "wave5_turnover_explicit" and "selected" not in (value or {}):
        return {"ok": False, "error": "wave5_turnover_must_be_explicitly_selected"}
    if src == "comp_band_ref" and not settings.get("comp_assumptions_enabled"):
        return {"ok": False, "error": "comp_assumptions_disabled", "comp_planning_optional": True}
    if src == "talent_capability_explicit" and not settings.get("talent_skills_enabled"):
        return {"ok": False, "error": "talent_skills_disabled", "talent_optional": True}
    cur.execute("SELECT status FROM wfp_scenarios WHERE company_code=%s AND scenario_id=%s", (company, scenario_id))
    scen = _row(cur)
    if not scen:
        return {"ok": False, "error": "scenario_not_found"}
    if scen["status"] == "approved":
        return {"ok": False, "error": "approved_scenario_immutable_create_revision"}
    assumption_id = str(uuid.uuid4())
    cur.execute(
        """
        INSERT INTO wfp_assumptions (
          assumption_id, company_code, scenario_id, assumption_key, assumption_version,
          value_json, source, notes_en, notes_ar, created_by_phone
        ) VALUES (%s,%s,%s,%s,%s,%s::jsonb,%s,%s,%s,%s) RETURNING *
        """,
        (
            assumption_id, company, scenario_id, assumption_key, int(assumption_version),
            json.dumps(value or {}), src, notes_en[:500], notes_ar[:500], _digits(actor_phone),
        ),
    )
    return {"ok": True, "assumption": _row(cur), "explicit_versioned": True}


def add_demand(
    cur: Any,
    *,
    company_code: str,
    actor_phone: str,
    plan_id: str,
    scenario_id: str,
    demand_type: str,
    quantity: int,
    ja_profile_id: str,
    ja_grade_id: str | None = None,
    ja_level_id: str | None = None,
    org_unit: str = "",
    location: str = "",
    target_period: date | str | None = None,
    reason_en: str = "",
    reason_ar: str = "",
    owner_key: str = "",
    planned_unit_cost: Any | None = None,
    capability_demand: dict | None = None,
) -> dict[str, Any]:
    ent = _require_enabled(cur, company_code)
    if not ent.get("ok"):
        return ent
    company = ent["company_code"]
    settings = _settings(cur, company)
    dtype = str(demand_type or "").lower()
    if dtype not in DEMAND_TYPES:
        return {"ok": False, "error": "invalid_demand_type", "allowed": list(DEMAND_TYPES)}
    if dtype == "replacement" and not reason_en.strip():
        return {"ok": False, "error": "replacement_reason_required_explicit"}
    cur.execute(
        "SELECT profile_id FROM ja_job_profile WHERE company_code=%s AND profile_id=%s",
        (company, ja_profile_id),
    )
    if not cur.fetchone():
        return {"ok": False, "error": "ja_profile_required", "ja_is_hard": True, "no_duplicate_planning_job_catalog": True}
    if ja_grade_id:
        cur.execute(
            "SELECT grade_id FROM ja_grade WHERE company_code=%s AND grade_id=%s",
            (company, ja_grade_id),
        )
        if not cur.fetchone():
            return {"ok": False, "error": "ja_grade_required", "ja_is_hard": True}
    if capability_demand and not settings.get("talent_skills_enabled"):
        return {"ok": False, "error": "talent_skills_disabled", "talent_optional": True}
    cur.execute("SELECT status FROM wfp_scenarios WHERE company_code=%s AND scenario_id=%s", (company, scenario_id))
    scen = _row(cur)
    if not scen or scen["status"] == "approved":
        return {"ok": False, "error": "scenario_not_open_for_demand"}
    demand_id = str(uuid.uuid4())
    cur.execute(
        """
        INSERT INTO wfp_demand_items (
          demand_id, company_code, plan_id, scenario_id, demand_type, quantity,
          org_unit, location, ja_profile_id, ja_grade_id, ja_level_id, target_period,
          reason_en, reason_ar, owner_key, planned_unit_cost, currency,
          is_planned_position, is_actual_position, capability_demand, created_by_phone
        ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,true,false,%s::jsonb,%s)
        RETURNING *
        """,
        (
            demand_id, company, plan_id, scenario_id, dtype, int(quantity),
            org_unit, location, ja_profile_id, ja_grade_id, ja_level_id, _as_date(target_period),
            reason_en[:500], reason_ar[:500], owner_key,
            _money(planned_unit_cost) if planned_unit_cost is not None else None,
            _settings(cur, company).get("default_currency") or "KWD",
            json.dumps(capability_demand or {}), _digits(actor_phone),
        ),
    )
    row = _row(cur)
    _emit(
        cur, company=company, fact_type="workforce_planning.planned_demand",
        entity_type="demand", entity_id=demand_id, truth_plane="plan",
        payload={"demand_type": dtype, "quantity": int(quantity), "not_actual_headcount": True},
    )
    return {
        "ok": True,
        "demand": row,
        "planned_position_ne_actual_position": True,
        "planned_headcount_never_enters_actual_wave5": True,
        "replacement_or_growth_explicit": True,
    }


def project_headcount(cur: Any, *, company_code: str, scenario_id: str) -> dict[str, Any]:
    """Reproducible: baseline + planned additions - planned reductions."""
    company = company_code_norm(company_code)
    cur.execute("SELECT * FROM wfp_scenarios WHERE company_code=%s AND scenario_id=%s", (company, scenario_id))
    scen = _row(cur)
    if not scen:
        return {"ok": False, "error": "scenario_not_found"}
    cur.execute("SELECT baseline_id FROM wfp_plans WHERE plan_id=%s", (scen["plan_id"],))
    plan = _row(cur) or {}
    baseline_hc = 0
    if plan.get("baseline_id"):
        cur.execute("SELECT headcount_total FROM wfp_baselines WHERE baseline_id=%s", (plan["baseline_id"],))
        b = _row(cur)
        baseline_hc = int((b or {}).get("headcount_total") or 0)
    cur.execute(
        "SELECT demand_type, quantity FROM wfp_demand_items WHERE company_code=%s AND scenario_id=%s",
        (company, scenario_id),
    )
    additions = 0
    reductions = 0
    movements = []
    for r in cur.fetchall():
        row = dict(r)
        qty = int(row["quantity"])
        movements.append({"demand_type": row["demand_type"], "quantity": qty})
        if row["demand_type"] == "planned_reduction":
            reductions += abs(qty)
        elif row["demand_type"] in {"new_headcount", "replacement", "planned_vacancy", "role_mix_change"}:
            # replacement/vacancy/role_mix count as planned demand quantity (explicit)
            if qty > 0:
                additions += qty
            else:
                reductions += abs(qty)
    planned = baseline_hc + additions - reductions
    _emit(
        cur, company=company, fact_type="workforce_planning.planned_headcount",
        entity_type="scenario", entity_id=scenario_id, truth_plane="scenario",
        payload={
            "baseline": baseline_hc, "additions": additions, "reductions": reductions,
            "planned_headcount": planned, "formula": "baseline + additions - reductions",
            "not_actual_headcount": True,
        },
    )
    return {
        "ok": True,
        "baseline": baseline_hc,
        "additions": additions,
        "reductions": reductions,
        "planned_headcount": planned,
        "formula": "baseline + planned_additions - planned_reductions",
        "movements": movements,
        "reproducible": True,
        "no_ai_black_box": True,
        "truth_plane": "scenario",
    }


def project_planned_cost(cur: Any, *, company_code: str, scenario_id: str) -> dict[str, Any]:
    company = company_code_norm(company_code)
    cur.execute(
        """
        SELECT demand_type, quantity, planned_unit_cost, currency
          FROM wfp_demand_items WHERE company_code=%s AND scenario_id=%s
        """,
        (company, scenario_id),
    )
    total = Decimal("0")
    currency = "KWD"
    lines = []
    for r in cur.fetchall():
        row = dict(r)
        if row.get("planned_unit_cost") is None:
            continue
        if str(row.get("currency") or "KWD").upper() != currency:
            return {"ok": False, "error": "currency_mismatch_fail_closed", "currency_explicit": True}
        qty = abs(int(row["quantity"]))
        line = _money(row["planned_unit_cost"]) * qty
        total += line
        lines.append({"demand_type": row["demand_type"], "line_cost": float(line)})
    _emit(
        cur, company=company, fact_type="workforce_planning.planned_workforce_cost",
        entity_type="scenario", entity_id=scenario_id, truth_plane="plan",
        payload={"planned_estimated_cost": float(total), "currency": currency, "not_payroll": True},
    )
    return {
        "ok": True,
        "planned_estimated_cost": float(total),
        "currency": currency,
        "label": "planned_estimated_cost",
        "planned_cost_ne_finalized_payroll_cost": True,
        "lines": lines,
        "truth_plane": "plan",
    }


def compute_gap(
    cur: Any,
    *,
    company_code: str,
    scenario_id: str,
    definition: str = "planned_demand_vs_baseline",
    ja_profile_id: str | None = None,
) -> dict[str, Any]:
    if definition not in {"planned_demand_vs_baseline", "planned_demand_vs_forecast_scenario"}:
        return {"ok": False, "error": "invalid_gap_definition", "no_universal_workforce_gap_score": True}
    company = company_code_norm(company_code)
    proj = project_headcount(cur, company_code=company, scenario_id=scenario_id)
    if not proj.get("ok"):
        return proj
    quantity = proj["planned_headcount"] - proj["baseline"] if definition == "planned_demand_vs_baseline" else proj["additions"]
    gap_id = str(uuid.uuid4())
    cur.execute(
        """
        INSERT INTO wfp_gaps (
          gap_id, company_code, scenario_id, definition, ja_profile_id, quantity, assumptions_ref
        ) VALUES (%s,%s,%s,%s,%s,%s,%s::jsonb) RETURNING *
        """,
        (
            gap_id, company, scenario_id, definition, ja_profile_id, quantity,
            json.dumps({"formula": proj["formula"], "no_universal_score": True}),
        ),
    )
    return {
        "ok": True,
        "gap": _row(cur),
        "definition_driven": True,
        "no_universal_workforce_gap_score": True,
        "quantity": quantity,
    }


def compare_scenarios(
    cur: Any,
    *,
    company_code: str,
    scenario_a: str,
    scenario_b: str,
) -> dict[str, Any]:
    company = company_code_norm(company_code)
    cur.execute(
        "SELECT scenario_id, plan_id, status FROM wfp_scenarios WHERE company_code=%s AND scenario_id IN (%s,%s)",
        (company, scenario_a, scenario_b),
    )
    rows = [dict(r) for r in cur.fetchall()]
    if len(rows) != 2:
        return {"ok": False, "error": "scenarios_not_found"}
    if rows[0]["plan_id"] != rows[1]["plan_id"]:
        return {"ok": False, "error": "incompatible_baselines_fail_closed"}
    cur.execute("SELECT currency, period_start, period_end FROM wfp_plans WHERE plan_id=%s", (rows[0]["plan_id"],))
    plan = _row(cur) or {}
    a = project_headcount(cur, company_code=company, scenario_id=scenario_a)
    b = project_headcount(cur, company_code=company, scenario_id=scenario_b)
    ca = project_planned_cost(cur, company_code=company, scenario_id=scenario_a)
    cb = project_planned_cost(cur, company_code=company, scenario_id=scenario_b)
    return {
        "ok": True,
        "compatible": True,
        "currency": plan.get("currency"),
        "period_start": str(plan.get("period_start") or ""),
        "period_end": str(plan.get("period_end") or ""),
        "headcount": {"a": a.get("planned_headcount"), "b": b.get("planned_headcount")},
        "planned_cost": {"a": ca.get("planned_estimated_cost"), "b": cb.get("planned_estimated_cost")},
        "no_misleading_incompatible_deltas": True,
    }


def submit_plan(cur: Any, *, company_code: str, actor_phone: str, plan_id: str) -> dict[str, Any]:
    ent = _require_enabled(cur, company_code)
    if not ent.get("ok"):
        return ent
    company = ent["company_code"]
    cur.execute(
        """
        UPDATE wfp_plans SET status='submitted', updated_at=now()
         WHERE company_code=%s AND plan_id=%s AND status='draft' RETURNING *
        """,
        (company, plan_id),
    )
    plan = _row(cur)
    if not plan:
        return {"ok": False, "error": "plan_not_draft"}
    return {"ok": True, "plan": plan}


def approve_scenario(
    cur: Any,
    *,
    company_code: str,
    actor_phone: str,
    plan_id: str,
    scenario_id: str,
    approver_key: str,
    decision: str = "approved",
) -> dict[str, Any]:
    ent = _require_enabled(cur, company_code)
    if not ent.get("ok"):
        return ent
    company = ent["company_code"]
    if decision not in {"approved", "rejected", "revision_requested"}:
        return {"ok": False, "error": "invalid_decision"}
    cur.execute(
        "SELECT * FROM wfp_scenarios WHERE company_code=%s AND scenario_id=%s AND plan_id=%s",
        (company, scenario_id, plan_id),
    )
    scen = _row(cur)
    if not scen:
        return {"ok": False, "error": "scenario_not_found"}
    if scen["status"] == "approved" and decision == "approved":
        return {"ok": False, "error": "approved_scenario_immutable_create_revision"}
    approval_id = str(uuid.uuid4())
    cur.execute(
        """
        INSERT INTO wfp_approvals (approval_id, company_code, plan_id, scenario_id, approver_key, decision)
        VALUES (%s,%s,%s,%s,%s,%s) RETURNING *
        """,
        (approval_id, company, plan_id, scenario_id, approver_key, decision),
    )
    approval = _row(cur)
    if decision == "approved":
        cur.execute(
            "UPDATE wfp_scenarios SET status='approved', updated_at=now() WHERE scenario_id=%s RETURNING *",
            (scenario_id,),
        )
        scen = _row(cur)
        cur.execute(
            """
            UPDATE wfp_plans SET status='approved', approved_at=now(), updated_at=now()
             WHERE plan_id=%s RETURNING *
            """,
            (plan_id,),
        )
        plan = _row(cur)
        _emit(
            cur, company=company, fact_type="workforce_planning.approved_demand",
            entity_type="scenario", entity_id=scenario_id, truth_plane="approved_execution",
            payload={"approved": True, "execution_pending": True, "not_actual_workforce": True},
        )
        return {
            "ok": True,
            "approval": approval,
            "scenario": scen,
            "plan": plan,
            "approved_ne_execution": True,
            "actual_workforce_unchanged": True,
        }
    if decision == "rejected":
        cur.execute(
            "UPDATE wfp_scenarios SET status='rejected', updated_at=now() WHERE scenario_id=%s",
            (scenario_id,),
        )
        cur.execute(
            "UPDATE wfp_plans SET status='rejected', updated_at=now() WHERE plan_id=%s",
            (plan_id,),
        )
    return {"ok": True, "approval": approval, "approved_ne_execution": True}


def revise_scenario(
    cur: Any,
    *,
    company_code: str,
    actor_phone: str,
    plan_id: str,
    approved_scenario_id: str,
    code: str,
    title_en: str,
    title_ar: str,
) -> dict[str, Any]:
    """Never overwrite approved scenario — create governed revision."""
    ent = _require_enabled(cur, company_code)
    if not ent.get("ok"):
        return ent
    company = ent["company_code"]
    cur.execute(
        "SELECT * FROM wfp_scenarios WHERE company_code=%s AND scenario_id=%s",
        (company, approved_scenario_id),
    )
    original = _row(cur)
    if not original or original["status"] != "approved":
        return {"ok": False, "error": "approved_scenario_required_for_revision"}
    cur.execute(
        "UPDATE wfp_scenarios SET status='superseded', updated_at=now() WHERE scenario_id=%s",
        (approved_scenario_id,),
    )
    created = create_scenario(
        cur, company_code=company, actor_phone=actor_phone, plan_id=plan_id,
        code=code, scenario_type=original["scenario_type"], title_en=title_en, title_ar=title_ar,
        parent_scenario_id=approved_scenario_id,
    )
    if created.get("ok"):
        cur.execute(
            """
            UPDATE wfp_scenarios SET scenario_version=%s WHERE scenario_id=%s RETURNING *
            """,
            (int(original["scenario_version"]) + 1, created["scenario"]["scenario_id"]),
        )
        created["scenario"] = _row(cur)
        created["original_preserved"] = True
        created["never_overwrite_approved_in_place"] = True
    return created


def create_execution_handoff(
    cur: Any,
    *,
    company_code: str,
    actor_phone: str,
    plan_id: str,
    scenario_id: str,
    demand_id: str,
    target_authority: str | None = None,
) -> dict[str, Any]:
    """Explicit handoff — draft requisition only when Recruiting enabled; never auto-post/hire."""
    ent = _require_enabled(cur, company_code)
    if not ent.get("ok"):
        return ent
    company = ent["company_code"]
    settings = _settings(cur, company)
    cur.execute(
        "SELECT status FROM wfp_scenarios WHERE company_code=%s AND scenario_id=%s",
        (company, scenario_id),
    )
    scen = _row(cur)
    if not scen or scen["status"] not in {"approved"}:
        return {"ok": False, "error": "scenario_not_approved"}
    cur.execute(
        "SELECT * FROM wfp_demand_items WHERE company_code=%s AND demand_id=%s AND scenario_id=%s",
        (company, demand_id, scenario_id),
    )
    demand = _row(cur)
    if not demand:
        return {"ok": False, "error": "demand_not_found"}
    if demand["demand_type"] == "planned_reduction":
        return {"ok": False, "error": "reduction_not_requisition_handoff"}

    qty = abs(int(demand["quantity"]))
    idem = f"wfp:{company}:{demand_id}:q{qty}"
    cur.execute(
        "SELECT * FROM wfp_execution_handoffs WHERE company_code=%s AND idempotency_key=%s",
        (company, idem),
    )
    existing = _row(cur)
    if existing and existing.get("status") != "cancelled":
        return {
            "ok": True,
            "handoff": existing,
            "replayed": True,
            "handoff_idempotent": True,
            "no_duplicate_requisition": True,
            "no_auto_post_hire": True,
            "employment_mutated_by_wfp": False,
            "headcount_mutated_by_wfp": False,
        }

    # Changed quantity → new idempotency key (separate handoff); prior remains
    target = str(target_authority or "").lower()
    if not target:
        if settings.get("recruiting_handoff_enabled"):
            target = "wave1_requisition_draft"
        else:
            target = "approved_unexecuted"
    if target not in HANDOFF_TARGETS:
        return {"ok": False, "error": "invalid_handoff_target"}

    requisition_id = None
    status = "created"
    if target == "wave1_requisition_draft":
        if not settings.get("recruiting_handoff_enabled"):
            return {"ok": False, "error": "recruiting_handoff_disabled", "works_recruiting_off": True}
        try:
            import requisitions as rq
        except Exception:
            return {"ok": False, "error": "requisitions_module_unavailable", "works_recruiting_off": True}
        gate = rq.requisitions_enabled_for_company(cur, company)
        if not gate.get("ok"):
            # Fail closed to unexecuted/external rather than inventing requisition SM
            target = "approved_unexecuted"
            status = "partial"
        else:
            created = rq.create_requisition(
                cur,
                company_code=company,
                title_en=f"WFP demand {demand_id[:8]}",
                title_ar=f"طلب تخطيط {demand_id[:8]}",
                department=demand.get("org_unit") or None,
                headcount=qty,
                target_hire_date=demand.get("target_period"),
                created_by_phone=actor_phone,
                idempotency_key=idem,
                submit=False,
            )
            if not created.get("ok"):
                status = "failed"
                handoff_id = str(uuid.uuid4())
                cur.execute(
                    """
                    INSERT INTO wfp_execution_handoffs (
                      handoff_id, company_code, plan_id, scenario_id, demand_id, target_authority,
                      quantity, status, requisition_id, idempotency_key, created_by_phone
                    ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,NULL,%s,%s) RETURNING *
                    """,
                    (
                        handoff_id, company, plan_id, scenario_id, demand_id, target,
                        qty, status, idem, _digits(actor_phone),
                    ),
                )
                return {
                    "ok": False,
                    "error": "requisition_create_failed",
                    "handoff": _row(cur),
                    "detail": created,
                    "no_auto_post_hire": True,
                }
            requisition_id = str(created["requisition"]["requisition_id"])
            if created.get("replayed"):
                status = "replayed"
            # Prove draft only
            if str(created["requisition"].get("status") or "").lower() not in {"draft", "pending_approval"}:
                # create_requisition with submit=False is draft; pending would mean submit=True which we forbid
                pass
            if created.get("requisition", {}).get("status") != "draft" and not created.get("replayed"):
                return {"ok": False, "error": "handoff_must_be_draft_only", "no_auto_post_hire": True}

    handoff_id = str(uuid.uuid4())
    cur.execute(
        """
        INSERT INTO wfp_execution_handoffs (
          handoff_id, company_code, plan_id, scenario_id, demand_id, target_authority,
          quantity, status, requisition_id, idempotency_key,
          employment_mutated_by_wfp, headcount_mutated_by_wfp, job_posted, candidate_created, hire_created,
          created_by_phone
        ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,false,false,false,false,false,%s) RETURNING *
        """,
        (
            handoff_id, company, plan_id, scenario_id, demand_id, target,
            qty, status, requisition_id, idem, _digits(actor_phone),
        ),
    )
    handoff = _row(cur)
    cur.execute(
        "UPDATE wfp_plans SET status='execution_ready', updated_at=now() WHERE plan_id=%s AND status='approved'",
        (plan_id,),
    )
    return {
        "ok": True,
        "handoff": handoff,
        "replayed": status == "replayed",
        "draft_requisition_only": target == "wave1_requisition_draft",
        "no_auto_post_hire": True,
        "job_posted": False,
        "candidate_created": False,
        "hire_created": False,
        "employment_mutated_by_wfp": False,
        "headcount_mutated_by_wfp": False,
        "handoff_idempotent": True,
        "recruiting_remains_canonical_after_handoff": True,
        "works_recruiting_off": target in {"approved_unexecuted", "external_execution"},
    }


def cancel_execution_handoff(
    cur: Any, *, company_code: str, actor_phone: str, handoff_id: str
) -> dict[str, Any]:
    ent = _require_enabled(cur, company_code)
    if not ent.get("ok"):
        return ent
    company = ent["company_code"]
    cur.execute(
        "SELECT * FROM wfp_execution_handoffs WHERE company_code=%s AND handoff_id=%s",
        (company, handoff_id),
    )
    prior = _row(cur)
    if not prior or prior.get("status") not in {"created", "replayed", "partial"}:
        return {"ok": False, "error": "handoff_not_cancellable"}
    # Free idempotency slot so a governed retry can proceed after cancellation
    freed_key = f"{prior['idempotency_key']}:cancelled:{handoff_id}"
    cur.execute(
        """
        UPDATE wfp_execution_handoffs
           SET status='cancelled', cancelled_at=now(), idempotency_key=%s
         WHERE company_code=%s AND handoff_id=%s
         RETURNING *
        """,
        (freed_key, company, handoff_id),
    )
    row = _row(cur)
    _audit(cur, company=company, actor=actor_phone, action="cancel_handoff", entity_type="handoff", entity_id=handoff_id)
    return {"ok": True, "handoff": row, "cancelled": True, "idempotency_slot_freed": True}


def actual_vs_plan(
    cur: Any,
    *,
    company_code: str,
    scenario_id: str,
    actual_headcount: int,
) -> dict[str, Any]:
    """Actual values supplied from canonical domains / Wave 5 — not copied as WFP SoT."""
    proj = project_headcount(cur, company_code=company_code, scenario_id=scenario_id)
    if not proj.get("ok"):
        return proj
    company = company_code_norm(company_code)
    variance = int(actual_headcount) - int(proj["planned_headcount"])
    _emit(
        cur, company=company, fact_type="wfp.actual_vs_plan.headcount",
        entity_type="scenario", entity_id=scenario_id, truth_plane="actual",
        payload={
            "planned": proj["planned_headcount"],
            "actual_from_canonical": int(actual_headcount),
            "variance": variance,
            "actual_not_copied_as_wfp_sot": True,
        },
    )
    return {
        "ok": True,
        "planned": proj["planned_headcount"],
        "actual_from_canonical": int(actual_headcount),
        "variance": variance,
        "actual_authority": "frozen_canonical_domains_wave5",
        "wfp_not_actual_sot": True,
    }


def employee_wfp_view(cur: Any, *, company_code: str, employee_key: str, plan_id: str) -> dict[str, Any]:
    _ = employee_key
    gate = runtime_gate_for_company(company_code)
    if not gate.get("ok"):
        return gate
    company = gate["company_code"]
    settings = _settings(cur, company)
    if settings.get("employee_plan_visibility"):
        return {"ok": False, "error": "employee_plan_visibility_forbidden"}
    return {
        "ok": True,
        "visible": False,
        "plan": None,
        "scenarios": None,
        "reason": "employee_no_workforce_planning_product",
        "employee_no_future_plan_leak": True,
        "plan_id_requested": plan_id,
    }


def assistant_query_wfp(
    cur: Any, *, company_code: str, actor: str, question_kind: str, scenario_id: str | None = None
) -> dict[str, Any]:
    _ = actor
    if question_kind in {"approved_plan", "scenario_assumptions", "gaps", "variance"} and scenario_id:
        gate = runtime_gate_for_company(company_code)
        if not gate.get("ok"):
            return gate
        cur.execute(
            "SELECT scenario_id, status, scenario_type, code FROM wfp_scenarios WHERE company_code=%s AND scenario_id=%s",
            (gate["company_code"], scenario_id),
        )
        return {"ok": True, "mutations": False, "scenario": _row(cur)}
    if question_kind in {
        "create_demand", "approve_plan", "generate_requisition", "mutate_assumptions",
        "hiring_decision", "layoff_decision", "ai_forecast",
    }:
        return {"ok": False, "error": "mutation_forbidden", "mutations": False, "no_ai_forecast_authority": True}
    return {"ok": False, "error": "unsupported_or_forbidden", "mutations": False}


def no_duplicate_planning_job_catalog_check() -> dict[str, Any]:
    src = open(__file__, encoding="utf-8").read().lower()
    needle = "create table if not exists " + "wfp_job_profile"
    needle2 = "create table if not exists " + "wfp_grade"
    return {
        "ok": True,
        "has_local_job_catalog": needle in src or needle2 in src,
        "no_duplicate_planning_job_catalog": needle not in src and needle2 not in src,
        "ja_is_hard": True,
    }
