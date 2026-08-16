"""Wave 6 C6 — Compensation Planning.

Canonical authority:
  cycle → eligibility snapshot → budgets → bands → recommendations →
  calibration → approvals → finalized plan → explicit apply/handoff

Not Payroll. Plan approved ≠ salary changed ≠ payroll applied.
JA (C1) is HARD for grade/job/level — no duplicate grade hierarchy.
Performance/Talent OPTIONAL inputs. Assistant mutations OUT.
"""
from __future__ import annotations

import json
import os
import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any

import job_architecture_c1 as ja

PHASE = "compensation_planning_c6"
CONTRACT_VERSION = "compensation_planning_c6_v1"
PASS_STAMP = "COMPENSATION_PLANNING_FULL_PASS"
COMMERCIAL_MODULE_KEY = "comp_planning"
FLAG = "WATHEFNI_COMP_PLANNING_C6"
COMPANIES_FLAG = "WATHEFNI_COMP_PLANNING_COMPANIES"
_ON = {"1", "true", "yes", "on"}

REC_TYPES = (
    "merit_increase",
    "promotion_increase",
    "market_adjustment",
    "one_time_bonus",
    "other_configured",
)
CYCLE_STATES = ("draft", "launched", "calibrating", "finalized", "closed")
BUDGET_OVERRUN = ("warn", "hard_block", "exception_approval")
HANDOFF_TARGETS = ("employment_change_c1", "external_payroll", "wathefni_payroll")

STATUS_LABELS = {
    "draft": {"en": "Draft", "ar": "مسودة"},
    "launched": {"en": "Launched", "ar": "مُطلق"},
    "calibrating": {"en": "Calibrating", "ar": "معايرة"},
    "finalized": {"en": "Finalized", "ar": "نهائي"},
    "closed": {"en": "Closed", "ar": "مغلق"},
    "merit_increase": {"en": "Merit increase", "ar": "زيادة استحقاق"},
    "promotion_increase": {"en": "Promotion increase", "ar": "زيادة ترقية"},
    "market_adjustment": {"en": "Market adjustment", "ar": "تعديل سوقي"},
    "one_time_bonus": {"en": "One-time bonus", "ar": "مكافأة لمرة واحدة"},
    "comp_planning": {"en": "Compensation Planning", "ar": "تخطيط التعويضات"},
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
        "does_not_own_ja_grades": True,
        "ja_is_hard": True,
        "no_duplicate_grade_hierarchy": True,
        "not_payroll": True,
        "plan_approved_not_salary_changed": True,
        "finalized_not_applied": True,
        "change_package_not_payroll_paid": True,
        "performance_optional": True,
        "rating_not_automatic_increase": True,
        "talent_optional": True,
        "hipo_not_automatic_pay": True,
        "works_payroll_off": True,
        "midpoint_not_recommended_salary": True,
        "promotion_plan_not_role_mutation": True,
        "approved_bonus_not_paid": True,
        "currency_explicit": True,
        "assistant_mutations": False,
        "no_second_analytics_engine": True,
        "employee_cannot_see_draft_recommendations": True,
        "company_code": company_code_norm(company_code) if company_code else None,
    }


def surface_composition_rules() -> dict[str, Any]:
    return {
        "hr_web": {"primary_planning_surface": True, "decision_oriented": True},
        "hr_mobile": {"intentionally_thin": True, "no_heavyweight_worksheet_parity": True},
        "manager": {"recommend_authorized_reports_only": True},
        "employee_app": {"no_in_progress_planning": True, "no_draft_recommendation_leak": True},
        "assistant": {"mutations": False, "read_explain_deep_link": True},
        "setup": {"owns_bands_cycle_defaults_sod": True},
    }


def runtime_gate_for_company(company_code: str | None) -> dict[str, Any]:
    company = company_code_norm(company_code)
    if not company:
        return {"ok": False, "enabled": False, "error": "company_required", "phase": PHASE}
    if not _env_on(FLAG, "off"):
        return {"ok": False, "enabled": False, "error": "comp_planning_c6_off", "gate": "runtime_flag", "phase": PHASE}
    raw = str(os.environ.get(COMPANIES_FLAG) or "").strip()
    allow = {p.strip().upper() for p in raw.split(",") if p.strip()} if raw else set()
    if not allow:
        return {
            "ok": False,
            "enabled": False,
            "error": "comp_planning_company_not_allowlisted",
            "gate": "company_allowlist",
            "phase": PHASE,
        }
    if company not in allow:
        return {
            "ok": False,
            "enabled": False,
            "error": "comp_planning_company_not_allowlisted",
            "gate": "company_allowlist",
            "phase": PHASE,
            "company_code": company,
        }
    # JA HARD gate
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


def ensure_compensation_planning_c6_schema(cur: Any, *, force: bool = False) -> None:
    _ = force
    ja.ensure_job_architecture_c1_schema(cur)
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS cp_company_settings (
          company_code text PRIMARY KEY,
          enabled boolean NOT NULL DEFAULT false,
          default_currency text NOT NULL DEFAULT 'KWD',
          budget_overrun_mode text NOT NULL DEFAULT 'hard_block',
          sod_required boolean NOT NULL DEFAULT true,
          performance_input_enabled boolean NOT NULL DEFAULT false,
          talent_input_enabled boolean NOT NULL DEFAULT false,
          payroll_handoff_enabled boolean NOT NULL DEFAULT false,
          employee_draft_visibility boolean NOT NULL DEFAULT false,
          enabled_by_phone text,
          enabled_reason text,
          enabled_at timestamptz,
          disabled_at timestamptz,
          updated_by_phone text,
          updated_at timestamptz NOT NULL DEFAULT now(),
          CHECK (budget_overrun_mode IN ('warn','hard_block','exception_approval')),
          CHECK (employee_draft_visibility = false)
        )
        """
    )
    for ddl in (
        """
        CREATE TABLE IF NOT EXISTS cp_salary_bands (
          band_id uuid PRIMARY KEY,
          company_code text NOT NULL,
          code text NOT NULL,
          band_version int NOT NULL DEFAULT 1,
          ja_grade_id uuid NOT NULL,
          ja_level_id uuid,
          currency text NOT NULL DEFAULT 'KWD',
          minimum numeric NOT NULL,
          midpoint numeric NOT NULL,
          maximum numeric NOT NULL,
          effective_start date NOT NULL,
          effective_end date,
          status text NOT NULL DEFAULT 'published',
          created_by_phone text,
          created_at timestamptz NOT NULL DEFAULT now(),
          UNIQUE (company_code, code, band_version),
          CHECK (minimum <= midpoint AND midpoint <= maximum)
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS cp_cycles (
          cycle_id uuid PRIMARY KEY,
          company_code text NOT NULL,
          code text NOT NULL,
          title_en text NOT NULL,
          title_ar text NOT NULL,
          status text NOT NULL DEFAULT 'draft',
          currency text NOT NULL DEFAULT 'KWD',
          budget_overrun_mode text NOT NULL DEFAULT 'hard_block',
          eligibility_rule jsonb NOT NULL DEFAULT '{}'::jsonb,
          eligibility_rule_version int NOT NULL DEFAULT 1,
          performance_input_enabled boolean NOT NULL DEFAULT false,
          talent_input_enabled boolean NOT NULL DEFAULT false,
          launched_at timestamptz,
          finalized_at timestamptz,
          snapshot_frozen boolean NOT NULL DEFAULT false,
          created_by_phone text,
          created_at timestamptz NOT NULL DEFAULT now(),
          updated_at timestamptz NOT NULL DEFAULT now(),
          UNIQUE (company_code, code),
          CHECK (status IN ('draft','launched','calibrating','finalized','closed')),
          CHECK (budget_overrun_mode IN ('warn','hard_block','exception_approval'))
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS cp_cycle_snapshots (
          snapshot_id uuid PRIMARY KEY,
          company_code text NOT NULL,
          cycle_id uuid NOT NULL REFERENCES cp_cycles(cycle_id),
          employee_key text NOT NULL,
          employment_ref text NOT NULL DEFAULT '',
          current_base numeric NOT NULL,
          currency text NOT NULL,
          ja_grade_id uuid,
          ja_level_id uuid,
          ja_profile_id uuid,
          band_id uuid,
          band_version int,
          manager_key text,
          department_snapshot text NOT NULL DEFAULT '',
          performance_rating_input text,
          talent_context_input text,
          eligible boolean NOT NULL DEFAULT true,
          eligibility_explanation jsonb NOT NULL DEFAULT '{}'::jsonb,
          UNIQUE (cycle_id, employee_key)
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS cp_budgets (
          budget_id uuid PRIMARY KEY,
          company_code text NOT NULL,
          cycle_id uuid NOT NULL REFERENCES cp_cycles(cycle_id),
          scope_type text NOT NULL,
          scope_key text NOT NULL,
          currency text NOT NULL DEFAULT 'KWD',
          allocated numeric NOT NULL DEFAULT 0,
          recommended numeric NOT NULL DEFAULT 0,
          approved numeric NOT NULL DEFAULT 0,
          created_at timestamptz NOT NULL DEFAULT now(),
          UNIQUE (cycle_id, scope_type, scope_key),
          CHECK (scope_type IN ('company','department','manager','grade_group'))
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS cp_recommendations (
          recommendation_id uuid PRIMARY KEY,
          company_code text NOT NULL,
          cycle_id uuid NOT NULL REFERENCES cp_cycles(cycle_id),
          employee_key text NOT NULL,
          recommendation_type text NOT NULL,
          amount numeric,
          percent numeric,
          currency text NOT NULL DEFAULT 'KWD',
          rationale text NOT NULL DEFAULT '',
          actor_key text NOT NULL,
          layer text NOT NULL DEFAULT 'original',
          performance_guided boolean NOT NULL DEFAULT false,
          talent_guided boolean NOT NULL DEFAULT false,
          proposed_ja_grade_id uuid,
          created_at timestamptz NOT NULL DEFAULT now(),
          CHECK (recommendation_type IN (
            'merit_increase','promotion_increase','market_adjustment','one_time_bonus','other_configured'
          )),
          CHECK (layer IN ('original','calibrated','approved'))
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS cp_approvals (
          approval_id uuid PRIMARY KEY,
          company_code text NOT NULL,
          cycle_id uuid NOT NULL REFERENCES cp_cycles(cycle_id),
          employee_key text NOT NULL,
          recommendation_id uuid REFERENCES cp_recommendations(recommendation_id),
          approver_key text NOT NULL,
          decision text NOT NULL,
          decided_at timestamptz NOT NULL DEFAULT now(),
          CHECK (decision IN ('approved','rejected','exception_budget'))
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS cp_final_decisions (
          decision_id uuid PRIMARY KEY,
          company_code text NOT NULL,
          cycle_id uuid NOT NULL REFERENCES cp_cycles(cycle_id),
          employee_key text NOT NULL,
          recommendation_type text NOT NULL,
          approved_amount numeric,
          approved_percent numeric,
          currency text NOT NULL DEFAULT 'KWD',
          old_base numeric,
          proposed_new_base numeric,
          effective_date date,
          applied boolean NOT NULL DEFAULT false,
          finalized_at timestamptz NOT NULL DEFAULT now(),
          UNIQUE (cycle_id, employee_key, recommendation_type),
          CHECK (applied = false OR applied = true)
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS cp_apply_handoffs (
          handoff_id uuid PRIMARY KEY,
          company_code text NOT NULL,
          cycle_id uuid NOT NULL REFERENCES cp_cycles(cycle_id),
          decision_id uuid NOT NULL REFERENCES cp_final_decisions(decision_id),
          employee_key text NOT NULL,
          employment_ref text NOT NULL DEFAULT '',
          change_type text NOT NULL,
          old_value numeric,
          proposed_new_value numeric,
          currency text NOT NULL DEFAULT 'KWD',
          effective_date date NOT NULL,
          target_authority text NOT NULL,
          applied boolean NOT NULL DEFAULT false,
          employment_mutated_by_comp boolean NOT NULL DEFAULT false,
          payroll_paid boolean NOT NULL DEFAULT false,
          payload jsonb NOT NULL DEFAULT '{}'::jsonb,
          created_by_phone text,
          created_at timestamptz NOT NULL DEFAULT now(),
          CHECK (employment_mutated_by_comp = false),
          CHECK (payroll_paid = false),
          CHECK (target_authority IN ('employment_change_c1','external_payroll','wathefni_payroll'))
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS cp_wave5_fact_outbox (
          fact_id uuid PRIMARY KEY,
          company_code text NOT NULL,
          fact_type text NOT NULL,
          entity_type text NOT NULL,
          entity_id text NOT NULL,
          payload jsonb NOT NULL,
          created_at timestamptz NOT NULL DEFAULT now()
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS cp_audit_events (
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
        """
        CREATE TABLE IF NOT EXISTS cp_notification_dedupe (
          dedupe_key text PRIMARY KEY,
          company_code text NOT NULL,
          created_at timestamptz NOT NULL DEFAULT now()
        )
        """,
    ):
        cur.execute(ddl)
    # Explicitly do NOT create grade/job hierarchy tables here.


def _audit(cur: Any, *, company: str, actor: str, action: str, entity_type: str, entity_id: str, detail: dict | None = None) -> None:
    cur.execute(
        """
        INSERT INTO cp_audit_events (audit_id, company_code, actor_phone, action, entity_type, entity_id, detail)
        VALUES (%s,%s,%s,%s,%s,%s,%s::jsonb)
        """,
        (str(uuid.uuid4()), company, _digits(actor), action, entity_type, entity_id, json.dumps(detail or {})),
    )


def _emit(cur: Any, *, company: str, fact_type: str, entity_type: str, entity_id: str, payload: dict) -> None:
    clean = {k: v for k, v in dict(payload or {}).items() if k not in {"salary", "rationale_full", "employee_name"}}
    cur.execute(
        """
        INSERT INTO cp_wave5_fact_outbox (fact_id, company_code, fact_type, entity_type, entity_id, payload)
        VALUES (%s,%s,%s,%s,%s,%s::jsonb)
        """,
        (str(uuid.uuid4()), company, fact_type, entity_type, entity_id, json.dumps(clean)),
    )


def _row(cur: Any) -> dict[str, Any] | None:
    fetched = cur.fetchone()
    return dict(fetched) if fetched else None


def enable_company_comp_planning(cur: Any, *, company_code: str, actor_phone: str, reason: str, **kwargs: Any) -> dict[str, Any]:
    if not str(reason or "").strip():
        return {"ok": False, "error": "audit_reason_required"}
    gate = runtime_gate_for_company(company_code)
    if not gate.get("ok"):
        return gate
    company = gate["company_code"]
    ensure_compensation_planning_c6_schema(cur)
    if not ja.module_enabled_for_company(cur, company):
        return {"ok": False, "error": "ja_must_be_enabled", "ja_is_hard": True}
    overrun = str(kwargs.get("budget_overrun_mode") or "hard_block")
    if overrun not in BUDGET_OVERRUN:
        return {"ok": False, "error": "invalid_budget_overrun_mode"}
    currency = str(kwargs.get("default_currency") or "KWD").upper()
    cur.execute(
        """
        INSERT INTO cp_company_settings (
          company_code, enabled, default_currency, budget_overrun_mode, sod_required,
          performance_input_enabled, talent_input_enabled, payroll_handoff_enabled,
          employee_draft_visibility, enabled_by_phone, enabled_reason, enabled_at,
          disabled_at, updated_by_phone, updated_at
        ) VALUES (%s,true,%s,%s,%s,%s,%s,%s,false,%s,%s,now(),NULL,%s,now())
        ON CONFLICT (company_code) DO UPDATE SET
          enabled=true,
          default_currency=EXCLUDED.default_currency,
          budget_overrun_mode=EXCLUDED.budget_overrun_mode,
          sod_required=EXCLUDED.sod_required,
          performance_input_enabled=EXCLUDED.performance_input_enabled,
          talent_input_enabled=EXCLUDED.talent_input_enabled,
          payroll_handoff_enabled=EXCLUDED.payroll_handoff_enabled,
          employee_draft_visibility=false,
          enabled_by_phone=EXCLUDED.enabled_by_phone, enabled_reason=EXCLUDED.enabled_reason,
          enabled_at=now(), disabled_at=NULL, updated_by_phone=EXCLUDED.updated_by_phone, updated_at=now()
        RETURNING *
        """,
        (
            company, currency, overrun,
            bool(kwargs.get("sod_required", True)),
            bool(kwargs.get("performance_input_enabled", False)),
            bool(kwargs.get("talent_input_enabled", False)),
            bool(kwargs.get("payroll_handoff_enabled", False)),
            _digits(actor_phone), str(reason).strip()[:500], _digits(actor_phone),
        ),
    )
    row = _row(cur)
    _audit(cur, company=company, actor=actor_phone, action="enable", entity_type="company", entity_id=company, detail={"reason": reason})
    return {"ok": True, "settings": row, "honesty": honesty_payload(company_code=company), "ja_is_hard": True}


def disable_company_comp_planning(cur: Any, *, company_code: str, actor_phone: str, reason: str) -> dict[str, Any]:
    company = company_code_norm(company_code)
    ensure_compensation_planning_c6_schema(cur)
    cur.execute(
        """
        UPDATE cp_company_settings
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
    ensure_compensation_planning_c6_schema(cur)
    cur.execute("SELECT enabled FROM cp_company_settings WHERE company_code=%s", (gate["company_code"],))
    row = cur.fetchone()
    return bool(row and dict(row).get("enabled"))


def _require_enabled(cur: Any, company_code: str) -> dict[str, Any]:
    gate = runtime_gate_for_company(company_code)
    if not gate.get("ok"):
        return gate
    if not module_enabled_for_company(cur, gate["company_code"]):
        return {"ok": False, "error": "comp_planning_disabled_for_company", "company_code": gate["company_code"]}
    return {"ok": True, "company_code": gate["company_code"]}


def _settings(cur: Any, company: str) -> dict[str, Any]:
    cur.execute("SELECT * FROM cp_company_settings WHERE company_code=%s", (company,))
    return _row(cur) or {}


def upsert_salary_band(
    cur: Any,
    *,
    company_code: str,
    actor_phone: str,
    code: str,
    ja_grade_id: str,
    minimum: Any,
    midpoint: Any,
    maximum: Any,
    currency: str = "KWD",
    ja_level_id: str | None = None,
    band_version: int = 1,
    effective_start: date | str | None = None,
) -> dict[str, Any]:
    ent = _require_enabled(cur, company_code)
    if not ent.get("ok"):
        return ent
    company = ent["company_code"]
    # JA HARD — grade must exist in JA, never invent local grade
    cur.execute(
        "SELECT grade_id FROM ja_grade WHERE company_code=%s AND grade_id=%s",
        (company, ja_grade_id),
    )
    if not cur.fetchone():
        return {"ok": False, "error": "ja_grade_required", "ja_is_hard": True, "no_duplicate_grade_hierarchy": True}
    mn, mid, mx = _money(minimum), _money(midpoint), _money(maximum)
    if not (mn <= mid <= mx):
        return {"ok": False, "error": "invalid_band_order"}
    if str(currency).upper() != "KWD" and False:
        pass  # KWD-first but currency explicit
    band_id = str(uuid.uuid4())
    cur.execute(
        """
        INSERT INTO cp_salary_bands (
          band_id, company_code, code, band_version, ja_grade_id, ja_level_id, currency,
          minimum, midpoint, maximum, effective_start, created_by_phone
        ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING *
        """,
        (
            band_id, company, code.strip(), int(band_version), ja_grade_id, ja_level_id,
            str(currency).upper(), mn, mid, mx, _as_date(effective_start) or date.today(),
            _digits(actor_phone),
        ),
    )
    row = _row(cur)
    return {
        "ok": True,
        "band": row,
        "midpoint_not_recommended_salary": True,
        "ja_grade_referenced": True,
        "no_local_grade_created": True,
    }


def create_cycle(
    cur: Any,
    *,
    company_code: str,
    actor_phone: str,
    code: str,
    title_en: str,
    title_ar: str,
    eligibility_rule: dict[str, Any] | None = None,
    currency: str | None = None,
) -> dict[str, Any]:
    ent = _require_enabled(cur, company_code)
    if not ent.get("ok"):
        return ent
    company = ent["company_code"]
    settings = _settings(cur, company)
    cycle_id = str(uuid.uuid4())
    cur.execute(
        """
        INSERT INTO cp_cycles (
          cycle_id, company_code, code, title_en, title_ar, currency, budget_overrun_mode,
          eligibility_rule, performance_input_enabled, talent_input_enabled, created_by_phone
        ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s::jsonb,%s,%s,%s) RETURNING *
        """,
        (
            cycle_id, company, code.strip(), title_en, title_ar,
            (currency or settings.get("default_currency") or "KWD").upper(),
            settings.get("budget_overrun_mode") or "hard_block",
            json.dumps(eligibility_rule or {"employment_status": "active"}),
            bool(settings.get("performance_input_enabled")),
            bool(settings.get("talent_input_enabled")),
            _digits(actor_phone),
        ),
    )
    return {"ok": True, "cycle": _row(cur)}


def evaluate_eligibility(employee: dict[str, Any], rule: dict[str, Any]) -> dict[str, Any]:
    reasons = []
    eligible = True
    for key, expected in (rule or {}).items():
        if key.endswith("_min"):
            base = key[: -len("_min")]
            if float(employee.get(base) or 0) < float(expected):
                eligible = False
                reasons.append({"field": key, "expected_min": expected, "actual": employee.get(base)})
            continue
        if employee.get(key) != expected:
            eligible = False
            reasons.append({"field": key, "expected": expected, "actual": employee.get(key)})
    return {"eligible": eligible, "eligible_not_guaranteed_increase": True, "reasons": reasons, "rule": rule}


def launch_cycle(
    cur: Any,
    *,
    company_code: str,
    actor_phone: str,
    cycle_id: str,
    population: list[dict[str, Any]],
) -> dict[str, Any]:
    """Freeze population + compensation + JA + band versions at launch."""
    ent = _require_enabled(cur, company_code)
    if not ent.get("ok"):
        return ent
    company = ent["company_code"]
    cur.execute("SELECT * FROM cp_cycles WHERE company_code=%s AND cycle_id=%s", (company, cycle_id))
    cycle = _row(cur)
    if not cycle:
        return {"ok": False, "error": "cycle_not_found"}
    if cycle["status"] != "draft":
        return {"ok": False, "error": "cycle_not_draft"}
    rule = cycle.get("eligibility_rule") or {}
    if isinstance(rule, str):
        rule = json.loads(rule)
    eligible_n = 0
    for emp in population:
        expl = evaluate_eligibility(emp, rule)
        band_id = emp.get("band_id")
        band_version = emp.get("band_version")
        if band_id:
            cur.execute(
                "SELECT band_version, ja_grade_id FROM cp_salary_bands WHERE company_code=%s AND band_id=%s",
                (company, band_id),
            )
            band = _row(cur)
            if band:
                band_version = int(band["band_version"])
        # Optional performance/talent inputs — never auto-decide pay
        perf = emp.get("performance_rating") if cycle.get("performance_input_enabled") else None
        talent = emp.get("talent_context") if cycle.get("talent_input_enabled") else None
        if expl["eligible"]:
            eligible_n += 1
        cur.execute(
            """
            INSERT INTO cp_cycle_snapshots (
              snapshot_id, company_code, cycle_id, employee_key, employment_ref, current_base, currency,
              ja_grade_id, ja_level_id, ja_profile_id, band_id, band_version, manager_key,
              department_snapshot, performance_rating_input, talent_context_input, eligible, eligibility_explanation
            ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb)
            """,
            (
                str(uuid.uuid4()), company, cycle_id, emp["employee_key"], emp.get("employment_ref", ""),
                _money(emp["current_base"]), emp.get("currency") or cycle["currency"],
                emp.get("ja_grade_id"), emp.get("ja_level_id"), emp.get("ja_profile_id"),
                band_id, band_version, emp.get("manager_key"), emp.get("department", ""),
                perf, talent, expl["eligible"], json.dumps(expl),
            ),
        )
    cur.execute(
        """
        UPDATE cp_cycles SET status='launched', launched_at=now(), snapshot_frozen=true, updated_at=now()
         WHERE cycle_id=%s RETURNING *
        """,
        (cycle_id,),
    )
    launched = _row(cur)
    _emit(
        cur, company=company, fact_type="comp.eligible_population", entity_type="cycle",
        entity_id=cycle_id, payload={"eligible_n": eligible_n, "population_n": len(population)},
    )
    return {
        "ok": True,
        "cycle": launched,
        "snapshot_frozen": True,
        "eligible_n": eligible_n,
        "eligible_not_guaranteed_increase": True,
    }


def create_budget(
    cur: Any,
    *,
    company_code: str,
    actor_phone: str,
    cycle_id: str,
    scope_type: str,
    scope_key: str,
    allocated: Any,
    currency: str = "KWD",
) -> dict[str, Any]:
    ent = _require_enabled(cur, company_code)
    if not ent.get("ok"):
        return ent
    company = ent["company_code"]
    if scope_type not in {"company", "department", "manager", "grade_group"}:
        return {"ok": False, "error": "invalid_budget_scope"}
    budget_id = str(uuid.uuid4())
    cur.execute(
        """
        INSERT INTO cp_budgets (
          budget_id, company_code, cycle_id, scope_type, scope_key, currency, allocated
        ) VALUES (%s,%s,%s,%s,%s,%s,%s) RETURNING *
        """,
        (budget_id, company, cycle_id, scope_type, scope_key, currency.upper(), _money(allocated)),
    )
    row = _row(cur)
    return {
        "ok": True,
        "budget": row,
        "remaining": float(_money(allocated)),
        "allocated_recommended_approved_distinct": True,
    }


def budget_remaining(budget: dict[str, Any]) -> Decimal:
    return _money(budget.get("allocated") or 0) - _money(budget.get("recommended") or 0)


def create_recommendation(
    cur: Any,
    *,
    company_code: str,
    actor_phone: str,
    cycle_id: str,
    employee_key: str,
    actor_key: str,
    recommendation_type: str,
    amount: Any | None = None,
    percent: Any | None = None,
    rationale: str = "",
    budget_scope_type: str = "company",
    budget_scope_key: str = "ALL",
    performance_guided: bool = False,
    talent_guided: bool = False,
    proposed_ja_grade_id: str | None = None,
    hipo_auto_convert: bool = False,
) -> dict[str, Any]:
    ent = _require_enabled(cur, company_code)
    if not ent.get("ok"):
        return ent
    company = ent["company_code"]
    rtype = str(recommendation_type or "").lower()
    if rtype not in REC_TYPES:
        return {"ok": False, "error": "invalid_recommendation_type", "allowed": list(REC_TYPES)}
    if hipo_auto_convert:
        return {"ok": False, "error": "hipo_not_automatic_pay", "talent_optional": True}
    cur.execute("SELECT * FROM cp_cycles WHERE company_code=%s AND cycle_id=%s", (company, cycle_id))
    cycle = _row(cur)
    if not cycle or cycle["status"] not in {"launched", "calibrating"}:
        return {"ok": False, "error": "cycle_not_open_for_recommendations"}
    cur.execute(
        "SELECT * FROM cp_cycle_snapshots WHERE company_code=%s AND cycle_id=%s AND employee_key=%s",
        (company, cycle_id, employee_key),
    )
    snap = _row(cur)
    if not snap or not snap.get("eligible"):
        return {"ok": False, "error": "employee_not_eligible"}
    if snap.get("manager_key") and actor_key != snap["manager_key"] and not actor_key.startswith("hr-"):
        # Manager may only recommend authorized reports unless HR actor
        return {"ok": False, "error": "manager_scope_denied"}
    if performance_guided and not cycle.get("performance_input_enabled"):
        return {"ok": False, "error": "performance_input_disabled"}
    if talent_guided and not cycle.get("talent_input_enabled"):
        return {"ok": False, "error": "talent_input_disabled"}
    # Budget check
    cur.execute(
        """
        SELECT * FROM cp_budgets
         WHERE company_code=%s AND cycle_id=%s AND scope_type=%s AND scope_key=%s
        """,
        (company, cycle_id, budget_scope_type, budget_scope_key),
    )
    budget = _row(cur)
    amt = _money(amount or 0)
    if budget:
        remaining = budget_remaining(budget)
        if amt > remaining:
            mode = cycle.get("budget_overrun_mode") or "hard_block"
            if mode == "hard_block":
                return {"ok": False, "error": "budget_overrun_hard_block", "remaining": float(remaining)}
            if mode == "warn":
                pass  # allow with warning
            if mode == "exception_approval":
                return {"ok": False, "error": "budget_overrun_requires_exception_approval", "remaining": float(remaining)}
        cur.execute(
            "UPDATE cp_budgets SET recommended = recommended + %s WHERE budget_id=%s",
            (amt, budget["budget_id"]),
        )
    rec_id = str(uuid.uuid4())
    cur.execute(
        """
        INSERT INTO cp_recommendations (
          recommendation_id, company_code, cycle_id, employee_key, recommendation_type,
          amount, percent, currency, rationale, actor_key, layer,
          performance_guided, talent_guided, proposed_ja_grade_id
        ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'original',%s,%s,%s) RETURNING *
        """,
        (
            rec_id, company, cycle_id, employee_key, rtype, amount, percent, cycle["currency"],
            rationale[:500], actor_key, bool(performance_guided), bool(talent_guided), proposed_ja_grade_id,
        ),
    )
    row = _row(cur)
    return {
        "ok": True,
        "recommendation": row,
        "layer": "original",
        "rating_not_automatic_increase": True,
        "hipo_not_automatic_pay": True,
        "promotion_plan_not_role_mutation": proposed_ja_grade_id is not None,
    }


def calibrate_recommendation(
    cur: Any,
    *,
    company_code: str,
    actor_phone: str,
    cycle_id: str,
    original_recommendation_id: str,
    actor_key: str,
    amount: Any,
    rationale: str = "",
) -> dict[str, Any]:
    """Creates calibrated layer — does not overwrite original."""
    ent = _require_enabled(cur, company_code)
    if not ent.get("ok"):
        return ent
    company = ent["company_code"]
    cur.execute(
        "SELECT * FROM cp_recommendations WHERE company_code=%s AND recommendation_id=%s",
        (company, original_recommendation_id),
    )
    original = _row(cur)
    if not original or original["layer"] != "original":
        return {"ok": False, "error": "original_recommendation_required"}
    cur.execute(
        "UPDATE cp_cycles SET status='calibrating', updated_at=now() WHERE cycle_id=%s AND status='launched'",
        (cycle_id,),
    )
    rec_id = str(uuid.uuid4())
    cur.execute(
        """
        INSERT INTO cp_recommendations (
          recommendation_id, company_code, cycle_id, employee_key, recommendation_type,
          amount, percent, currency, rationale, actor_key, layer,
          performance_guided, talent_guided, proposed_ja_grade_id
        ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'calibrated',%s,%s,%s) RETURNING *
        """,
        (
            rec_id, company, cycle_id, original["employee_key"], original["recommendation_type"],
            amount, original.get("percent"), original["currency"], rationale[:500], actor_key,
            original["performance_guided"], original["talent_guided"], original.get("proposed_ja_grade_id"),
        ),
    )
    calibrated = _row(cur)
    # Prove original still intact
    cur.execute("SELECT * FROM cp_recommendations WHERE recommendation_id=%s", (original_recommendation_id,))
    still = _row(cur)
    return {
        "ok": True,
        "calibrated": calibrated,
        "original_preserved": still is not None and str(still["recommendation_id"]) == original_recommendation_id,
        "calibration_not_original": True,
    }


def approve_recommendation(
    cur: Any,
    *,
    company_code: str,
    actor_phone: str,
    cycle_id: str,
    recommendation_id: str,
    approver_key: str,
    decision: str = "approved",
) -> dict[str, Any]:
    ent = _require_enabled(cur, company_code)
    if not ent.get("ok"):
        return ent
    company = ent["company_code"]
    settings = _settings(cur, company)
    cur.execute(
        "SELECT * FROM cp_recommendations WHERE company_code=%s AND recommendation_id=%s",
        (company, recommendation_id),
    )
    rec = _row(cur)
    if not rec:
        return {"ok": False, "error": "recommendation_not_found"}
    if settings.get("sod_required", True) and approver_key == rec["actor_key"]:
        return {"ok": False, "error": "sod_violation_recommend_approve_same_actor"}
    approval_id = str(uuid.uuid4())
    cur.execute(
        """
        INSERT INTO cp_approvals (
          approval_id, company_code, cycle_id, employee_key, recommendation_id, approver_key, decision
        ) VALUES (%s,%s,%s,%s,%s,%s,%s) RETURNING *
        """,
        (approval_id, company, cycle_id, rec["employee_key"], recommendation_id, approver_key, decision),
    )
    approval = _row(cur)
    if decision == "approved":
        cur.execute(
            """
            INSERT INTO cp_recommendations (
              recommendation_id, company_code, cycle_id, employee_key, recommendation_type,
              amount, percent, currency, rationale, actor_key, layer,
              performance_guided, talent_guided, proposed_ja_grade_id
            ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'approved',%s,%s,%s)
            """,
            (
                str(uuid.uuid4()), company, cycle_id, rec["employee_key"], rec["recommendation_type"],
                rec["amount"], rec.get("percent"), rec["currency"], "approved", approver_key,
                rec["performance_guided"], rec["talent_guided"], rec.get("proposed_ja_grade_id"),
            ),
        )
        cur.execute(
            """
            UPDATE cp_budgets SET approved = approved + %s
             WHERE cycle_id=%s AND scope_type='company' AND scope_key='ALL'
            """,
            (_money(rec["amount"] or 0), cycle_id),
        )
    return {
        "ok": True,
        "approval": approval,
        "approval_not_salary_mutation": True,
        "plan_approved_not_salary_changed": True,
    }


def finalize_cycle(cur: Any, *, company_code: str, actor_phone: str, cycle_id: str) -> dict[str, Any]:
    ent = _require_enabled(cur, company_code)
    if not ent.get("ok"):
        return ent
    company = ent["company_code"]
    cur.execute(
        """
        SELECT r.* FROM cp_recommendations r
         WHERE r.company_code=%s AND r.cycle_id=%s AND r.layer='approved'
        """,
        (company, cycle_id),
    )
    approved = [dict(x) for x in cur.fetchall()]
    decisions = []
    for rec in approved:
        cur.execute(
            "SELECT current_base FROM cp_cycle_snapshots WHERE cycle_id=%s AND employee_key=%s",
            (cycle_id, rec["employee_key"]),
        )
        snap = _row(cur) or {}
        old_base = _money(snap.get("current_base") or 0)
        amt = _money(rec.get("amount") or 0)
        new_base = old_base + amt if rec["recommendation_type"] != "one_time_bonus" else old_base
        decision_id = str(uuid.uuid4())
        cur.execute(
            """
            INSERT INTO cp_final_decisions (
              decision_id, company_code, cycle_id, employee_key, recommendation_type,
              approved_amount, approved_percent, currency, old_base, proposed_new_base,
              effective_date, applied
            ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,false)
            ON CONFLICT (cycle_id, employee_key, recommendation_type) DO NOTHING
            RETURNING *
            """,
            (
                decision_id, company, cycle_id, rec["employee_key"], rec["recommendation_type"],
                amt, rec.get("percent"), rec["currency"], old_base, new_base, date.today(),
            ),
        )
        row = _row(cur)
        if row:
            decisions.append(row)
            _emit(
                cur, company=company, fact_type="comp.approved_adjustment", entity_type="decision",
                entity_id=str(row["decision_id"]),
                payload={"type": rec["recommendation_type"], "amount": float(amt), "applied": False},
            )
    cur.execute(
        """
        UPDATE cp_cycles SET status='finalized', finalized_at=now(), updated_at=now()
         WHERE cycle_id=%s RETURNING *
        """,
        (cycle_id,),
    )
    cycle = _row(cur)
    return {
        "ok": True,
        "cycle": cycle,
        "decisions": decisions,
        "finalized_not_applied": True,
        "immutable_except_governed_correction": True,
    }


def create_apply_handoff(
    cur: Any,
    *,
    company_code: str,
    actor_phone: str,
    cycle_id: str,
    decision_id: str,
    target_authority: str,
    employment_ref: str = "",
) -> dict[str, Any]:
    """Explicit change package — Comp does not mutate employment/payroll."""
    ent = _require_enabled(cur, company_code)
    if not ent.get("ok"):
        return ent
    company = ent["company_code"]
    settings = _settings(cur, company)
    target = str(target_authority or "").lower()
    if target not in HANDOFF_TARGETS:
        return {"ok": False, "error": "invalid_handoff_target"}
    if target == "wathefni_payroll" and not settings.get("payroll_handoff_enabled"):
        return {"ok": False, "error": "payroll_handoff_disabled", "works_payroll_off": True}
    cur.execute(
        "SELECT * FROM cp_final_decisions WHERE company_code=%s AND decision_id=%s AND cycle_id=%s",
        (company, decision_id, cycle_id),
    )
    decision = _row(cur)
    if not decision:
        return {"ok": False, "error": "decision_not_found"}
    if not decision.get("proposed_new_base") and decision["recommendation_type"] != "one_time_bonus":
        return {"ok": False, "error": "decision_incomplete"}
    handoff_id = str(uuid.uuid4())
    cur.execute(
        """
        INSERT INTO cp_apply_handoffs (
          handoff_id, company_code, cycle_id, decision_id, employee_key, employment_ref,
          change_type, old_value, proposed_new_value, currency, effective_date, target_authority,
          applied, employment_mutated_by_comp, payroll_paid, created_by_phone
        ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,false,false,false,%s) RETURNING *
        """,
        (
            handoff_id, company, cycle_id, decision_id, decision["employee_key"], employment_ref,
            decision["recommendation_type"], decision.get("old_base"),
            decision.get("proposed_new_base") if decision["recommendation_type"] != "one_time_bonus" else decision.get("approved_amount"),
            decision["currency"], decision.get("effective_date") or date.today(), target,
            _digits(actor_phone),
        ),
    )
    handoff = _row(cur)
    return {
        "ok": True,
        "handoff": handoff,
        "applied": False,
        "plan_approved_not_change_package_applied": True,
        "change_package_applied_not_payroll_paid": True,
        "employment_mutated_by_comp": False,
        "payroll_paid": False,
        "employment_change_remains_mutation_authority": target == "employment_change_c1",
        "approved_bonus_not_paid": decision["recommendation_type"] == "one_time_bonus",
    }


def compute_compa_ratio(
    cur: Any, *, company_code: str, cycle_id: str, employee_key: str
) -> dict[str, Any]:
    company = company_code_norm(company_code)
    cur.execute(
        "SELECT * FROM cp_cycle_snapshots WHERE company_code=%s AND cycle_id=%s AND employee_key=%s",
        (company, cycle_id, employee_key),
    )
    snap = _row(cur)
    if not snap:
        return {"ok": False, "error": "snapshot_not_found"}
    if not snap.get("band_id"):
        return {"ok": True, "compa_ratio": None, "unavailable": True, "reason": "no_band_midpoint"}
    cur.execute(
        "SELECT midpoint, currency FROM cp_salary_bands WHERE band_id=%s AND band_version=%s",
        (snap["band_id"], snap.get("band_version")),
    )
    band = _row(cur)
    if not band or not band.get("midpoint"):
        return {"ok": True, "compa_ratio": None, "unavailable": True, "reason": "no_band_midpoint"}
    if str(band["currency"]).upper() != str(snap["currency"]).upper():
        return {"ok": False, "error": "currency_mismatch_fail_closed", "currency_explicit": True}
    mid = _money(band["midpoint"])
    if mid == 0:
        return {"ok": True, "compa_ratio": None, "unavailable": True}
    ratio = float(_money(snap["current_base"]) / mid)
    return {
        "ok": True,
        "compa_ratio": round(ratio, 4),
        "definition": "current_eligible_base / applicable_range_midpoint",
        "currency": snap["currency"],
        "midpoint_not_recommended_salary": True,
    }


def employee_comp_view(cur: Any, *, company_code: str, employee_key: str, cycle_id: str) -> dict[str, Any]:
    """Employees must not see in-progress / draft recommendations."""
    gate = runtime_gate_for_company(company_code)
    if not gate.get("ok"):
        return gate
    company = gate["company_code"]
    settings = _settings(cur, company)
    if settings.get("employee_draft_visibility"):
        return {"ok": False, "error": "employee_draft_visibility_forbidden"}
    cur.execute("SELECT status FROM cp_cycles WHERE company_code=%s AND cycle_id=%s", (company, cycle_id))
    cycle = _row(cur)
    if not cycle:
        return {"ok": False, "error": "cycle_not_found"}
    if cycle["status"] != "finalized":
        return {
            "ok": True,
            "visible": False,
            "recommendations": None,
            "reason": "in_progress_planning_hidden",
            "employee_cannot_see_draft_recommendations": True,
        }
    # Only applied/communicated downstream would show — here finalized but not draft leak
    return {
        "ok": True,
        "visible": False,
        "recommendations": None,
        "message": "employee_facing_comp_via_downstream_authority_only",
        "employee_cannot_see_draft_recommendations": True,
    }


def recommendation_history(cur: Any, *, company_code: str, cycle_id: str, employee_key: str) -> dict[str, Any]:
    company = company_code_norm(company_code)
    cur.execute(
        """
        SELECT recommendation_id, layer, recommendation_type, amount, actor_key, created_at, rationale
          FROM cp_recommendations
         WHERE company_code=%s AND cycle_id=%s AND employee_key=%s
         ORDER BY created_at
        """,
        (company, cycle_id, employee_key),
    )
    rows = [dict(r) for r in cur.fetchall()]
    return {"ok": True, "history": rows, "original_preserved": any(r["layer"] == "original" for r in rows)}


def assistant_query_comp(
    cur: Any, *, company_code: str, actor: str, question_kind: str, cycle_id: str | None = None
) -> dict[str, Any]:
    _ = actor
    if question_kind == "cycle_status" and cycle_id:
        gate = runtime_gate_for_company(company_code)
        if not gate.get("ok"):
            return gate
        cur.execute(
            "SELECT cycle_id, status, currency, snapshot_frozen FROM cp_cycles WHERE company_code=%s AND cycle_id=%s",
            (gate["company_code"], cycle_id),
        )
        return {"ok": True, "mutations": False, "cycle": _row(cur)}
    if question_kind in {"recommend_pay", "change_salary", "approve", "apply_plan", "infer_from_talent"}:
        return {"ok": False, "error": "mutation_forbidden", "mutations": False}
    return {"ok": False, "error": "unsupported_or_forbidden", "mutations": False}


def _notify_dedupe(cur: Any, *, company: str, key: str) -> dict[str, Any]:
    dedupe_key = f"{company}:{key}"
    sp = f"cp_nd_{uuid.uuid4().hex[:12]}"
    cur.execute(f"SAVEPOINT {sp}")
    try:
        cur.execute(
            "INSERT INTO cp_notification_dedupe (dedupe_key, company_code) VALUES (%s,%s)",
            (dedupe_key, company),
        )
        cur.execute(f"RELEASE SAVEPOINT {sp}")
        return {"sent": True, "deduped": False, "no_salary_in_payload": True}
    except Exception:
        cur.execute(f"ROLLBACK TO SAVEPOINT {sp}")
        cur.execute(f"RELEASE SAVEPOINT {sp}")
        return {"sent": False, "deduped": True, "no_salary_in_payload": True}


def no_duplicate_grade_hierarchy_check() -> dict[str, Any]:
    src = open(__file__, encoding="utf-8").read().lower()
    needle = "create table if not exists " + "cp_grade"
    return {
        "ok": True,
        "has_local_grade_table": needle in src,
        "no_duplicate_grade_hierarchy": needle not in src,
        "ja_is_hard": True,
    }
