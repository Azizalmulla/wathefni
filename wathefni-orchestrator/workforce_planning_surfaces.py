#!/usr/bin/env python3
"""R5J Workforce Planning product surfaces — thin composition over frozen C7.

HTTP and HR Web are adapters. Baseline freeze, demand, scenarios, assumptions,
projection, planned cost, gaps, comparison, approvals, and handoffs stay
domain-authoritative. This module never invents roles, FX, or actual headcount.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any, Mapping

import job_architecture_c1 as ja
import workforce_planning_c7 as c7

PHASE = "workforce_planning_surfaces_r5j"
CONTRACT_VERSION = "workforce_planning_surfaces_v1"
PASS_STAMP = "PRODUCTION_READINESS_R5J_WORKFORCE_PLANNING_SURFACE_FULL_PASS"
COMMERCIAL_MODULE_KEY = "workforce_planning"


def honesty_payload(*, company_code: str | None = None) -> dict[str, Any]:
    return {
        "phase": PHASE,
        "contract_version": CONTRACT_VERSION,
        "pass_stamp": PASS_STAMP,
        "commercial_module_key": COMMERCIAL_MODULE_KEY,
        "canonical_authority": ("workforce_planning_c7",),
        "actual_ne_baseline": True,
        "actual_ne_plan": True,
        "baseline_ne_scenario": True,
        "scenario_ne_approved_execution": True,
        "planned_headcount_never_enters_actual_wave5": True,
        "planned_position_ne_actual_position": True,
        "planned_cost_ne_finalized_payroll_cost": True,
        "approval_ne_actual_workforce_change": True,
        "ja_is_hard": True,
        "no_duplicate_planning_job_catalog": True,
        "no_ai_forecast_authority": True,
        "no_frontend_forecast_authority": True,
        "no_universal_workforce_gap_score": True,
        "no_fx": True,
        "kwd_explicit": True,
        "recruiting_optional": True,
        "comp_planning_optional": True,
        "talent_optional": True,
        "empty_manager_scope_is_zero_rows": True,
        "assistant_mutations": False,
        "company_code": c7.company_code_norm(company_code) if company_code else None,
        **c7.honesty_payload(company_code=company_code),
    }


def ensure_schema(cur: Any) -> None:
    c7.ensure_workforce_planning_c7_schema(cur)


def _money(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, Decimal):
        return float(value)
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _row(value: Any) -> dict[str, Any]:
    return dict(value) if value else {}


def _require_kwd(currency: str | None) -> dict[str, Any] | None:
    code = str(currency or "KWD").strip().upper() or "KWD"
    if code != "KWD":
        return {
            "ok": False,
            "error": "currency_unsupported_no_fx",
            "currency_explicit": True,
            "no_fx": True,
            "message": "Only KWD is supported. Exchange rates are not invented.",
        }
    return None


def _upsert_company_module(cur: Any, company: str, enabled: bool) -> None:
    cur.execute(
        """
        INSERT INTO company_modules (company_code, module_key, enabled, source, settings, updated_at)
        VALUES (%s, 'workforce_planning', %s, 'workforce_planning_surfaces', '{}'::jsonb, now())
        ON CONFLICT (company_code, module_key)
        DO UPDATE SET enabled=EXCLUDED.enabled, source='workforce_planning_surfaces', updated_at=now()
        """,
        (company, bool(enabled)),
    )


def _module_on(cur: Any, company: str, key: str) -> bool:
    cur.execute(
        """
        SELECT 1 FROM company_modules
         WHERE company_code=%s AND module_key=%s AND enabled IS TRUE
         LIMIT 1
        """,
        (company, key),
    )
    return bool(cur.fetchone())


def _ja_ready(cur: Any, company: str) -> bool:
    return bool(ja.runtime_gate_for_company(company).get("ok")) and ja.module_enabled_for_company(cur, company)


def _unavailable(*, company: str, reason: str) -> dict[str, Any]:
    return {
        "ok": True,
        "enabled": False,
        "resource_state": "unavailable",
        "counts": None,
        "reason": reason,
        "ja_hard_unmet": reason == "ja_hard_dependency_unmet",
        **honesty_payload(company_code=company),
    }


def sync_catalog_entitlement(
    cur: Any,
    *,
    company_code: str,
    actor_phone: str,
    enabled: bool,
    reason: str = "sync workforce planning catalog entitlement",
) -> dict[str, Any]:
    ensure_schema(cur)
    company = c7.company_code_norm(company_code)
    if enabled:
        result = c7.enable_company_workforce_planning(
            cur, company_code=company, actor_phone=actor_phone, reason=reason
        )
    else:
        result = c7.disable_company_workforce_planning(
            cur, company_code=company, actor_phone=actor_phone, reason=reason
        )
    if result.get("ok"):
        _upsert_company_module(cur, company, bool(enabled))
    return {
        "ok": bool(result.get("ok")),
        "company_code": company,
        "enabled": bool(enabled),
        "history_preserved": True,
        "linked_requisitions_not_deleted": True,
        "downstream_execution_not_reversed": True,
        "result": result,
        **honesty_payload(company_code=company),
    }


def _public_plan(row: Mapping[str, Any]) -> dict[str, Any]:
    status = str(row.get("status") or "")
    return {
        "plan_id": str(row.get("plan_id") or ""),
        "code": row.get("code"),
        "title_en": row.get("title_en"),
        "title_ar": row.get("title_ar"),
        "status": status,
        "status_label_en": c7.status_label(status, lang="en"),
        "status_label_ar": c7.status_label(status, lang="ar"),
        "horizon": row.get("horizon"),
        "currency": row.get("currency"),
        "fiscal_year": row.get("fiscal_year"),
        "period_start": row.get("period_start"),
        "period_end": row.get("period_end"),
        "baseline_id": str(row.get("baseline_id") or "") or None,
        "plan_version": row.get("plan_version"),
        "approved_at": row.get("approved_at"),
        "approval_ne_actual_workforce_change": True,
    }


def _public_scenario(row: Mapping[str, Any]) -> dict[str, Any]:
    status = str(row.get("status") or "")
    stype = str(row.get("scenario_type") or "")
    return {
        "scenario_id": str(row.get("scenario_id") or ""),
        "plan_id": str(row.get("plan_id") or ""),
        "code": row.get("code"),
        "scenario_type": stype,
        "type_label_en": c7.status_label(stype, lang="en"),
        "type_label_ar": c7.status_label(stype, lang="ar"),
        "title_en": row.get("title_en"),
        "title_ar": row.get("title_ar"),
        "status": status,
        "status_label_en": c7.status_label(status, lang="en"),
        "status_label_ar": c7.status_label(status, lang="ar"),
        "scenario_version": row.get("scenario_version"),
        "parent_scenario_id": str(row.get("parent_scenario_id") or "") or None,
        "scenario_distinct_from_baseline": True,
        "scenario_distinct_from_actual": True,
    }


def _public_demand(row: Mapping[str, Any], *, include_cost: bool) -> dict[str, Any]:
    dtype = str(row.get("demand_type") or "")
    out = {
        "demand_id": str(row.get("demand_id") or ""),
        "plan_id": str(row.get("plan_id") or ""),
        "scenario_id": str(row.get("scenario_id") or ""),
        "demand_type": dtype,
        "type_label_en": c7.status_label(dtype, lang="en"),
        "type_label_ar": c7.status_label(dtype, lang="ar"),
        "quantity": row.get("quantity"),
        "org_unit": row.get("org_unit"),
        "location": row.get("location"),
        "ja_profile_id": str(row.get("ja_profile_id") or "") or None,
        "ja_grade_id": str(row.get("ja_grade_id") or "") or None,
        "ja_level_id": str(row.get("ja_level_id") or "") or None,
        "target_period": row.get("target_period"),
        "reason_en": row.get("reason_en"),
        "reason_ar": row.get("reason_ar"),
        "owner_key": row.get("owner_key"),
        "currency": row.get("currency"),
        "is_planned_position": True,
        "is_actual_position": False,
        "planned_position_ne_actual_position": True,
        "replacement_or_growth_explicit": True,
    }
    if include_cost:
        out["planned_unit_cost"] = _money(row.get("planned_unit_cost"))
        out["planned_estimated_cost_label"] = "planned_estimated_cost"
    return out


def _table_exists(cur: Any, name: str) -> bool:
    cur.execute("SELECT to_regclass(%s) AS rel", (name,))
    return bool((_row(cur.fetchone()).get("rel")))


def canonical_actual_population(cur: Any, *, company_code: str, as_of_date: date | str) -> list[dict[str, Any]]:
    """Authorized actual snapshot from canonical employment + JA mapping. Not a WFP SoT."""
    company = c7.company_code_norm(company_code)
    as_of = c7._as_date(as_of_date) or date.today()
    ja.ensure_job_architecture_c1_schema(cur)
    cur.execute(
        """
        SELECT DISTINCT ON (employee_key)
               employee_key, profile_id AS ja_profile_id, grade_id AS ja_grade_id,
               level_id AS ja_level_id, employment_period_key
          FROM ja_employment_assignment
         WHERE company_code=%s
           AND effective_start <= %s
           AND (effective_end IS NULL OR effective_end >= %s)
           AND superseded_by IS NULL
         ORDER BY employee_key, effective_start DESC
        """,
        (company, as_of, as_of),
    )
    rows = [dict(r) for r in cur.fetchall()]
    if rows:
        return [
            {
                "employee_key": item["employee_key"],
                "org_unit": "",
                "ja_profile_id": item.get("ja_profile_id"),
                "ja_grade_id": item.get("ja_grade_id"),
                "ja_level_id": item.get("ja_level_id"),
                "source_authority": "employment_org_ja",
            }
            for item in rows
        ]
    if _table_exists(cur, "employee_employments"):
        cur.execute(
            """
            SELECT COALESCE(legacy_employee_key, employment_id::text) AS employee_key
              FROM employee_employments
             WHERE company_code=%s AND employment_status='active'
            """,
            (company,),
        )
        return [
            {
                "employee_key": dict(item)["employee_key"],
                "org_unit": "",
                "source_authority": "employment_org_ja",
            }
            for item in cur.fetchall()
        ]
    return []


def canonical_actual_headcount(cur: Any, *, company_code: str) -> int:
    company = c7.company_code_norm(company_code)
    if _table_exists(cur, "employee_employments"):
        cur.execute(
            """
            SELECT COUNT(*) AS n FROM employee_employments
             WHERE company_code=%s AND employment_status='active'
            """,
            (company,),
        )
        n = int((_row(cur.fetchone()).get("n") or 0))
        if n:
            return n
    ja.ensure_job_architecture_c1_schema(cur)
    cur.execute(
        """
        SELECT COUNT(DISTINCT employee_key) AS n
          FROM ja_employment_assignment
         WHERE company_code=%s AND superseded_by IS NULL AND effective_end IS NULL
        """,
        (company,),
    )
    return int((_row(cur.fetchone()).get("n") or 0))


def workspace_summary(cur: Any, *, company_code: str) -> dict[str, Any]:
    ensure_schema(cur)
    company = c7.company_code_norm(company_code)
    if not _ja_ready(cur, company):
        return _unavailable(company=company, reason="ja_hard_dependency_unmet")
    if not c7.module_enabled_for_company(cur, company):
        return _unavailable(company=company, reason="workforce_planning_disabled")
    cur.execute("SELECT COUNT(*) AS n FROM wfp_plans WHERE company_code=%s AND status='draft'", (company,))
    drafts = int((_row(cur.fetchone()).get("n") or 0))
    cur.execute(
        "SELECT COUNT(*) AS n FROM wfp_plans WHERE company_code=%s AND status IN ('submitted','approved','execution_ready')",
        (company,),
    )
    live = int((_row(cur.fetchone()).get("n") or 0))
    cur.execute("SELECT COUNT(*) AS n FROM wfp_scenarios WHERE company_code=%s AND status='approved'", (company,))
    approved = int((_row(cur.fetchone()).get("n") or 0))
    cur.execute("SELECT COUNT(*) AS n FROM wfp_demand_items WHERE company_code=%s", (company,))
    demand_n = int((_row(cur.fetchone()).get("n") or 0))
    cur.execute(
        "SELECT COUNT(*) AS n FROM wfp_execution_handoffs WHERE company_code=%s AND status IN ('created','replayed','partial')",
        (company,),
    )
    handoffs = int((_row(cur.fetchone()).get("n") or 0))
    cur.execute(
        """
        SELECT plan_id, code, title_en, title_ar, status, horizon, currency
          FROM wfp_plans WHERE company_code=%s
         ORDER BY created_at DESC LIMIT 1
        """,
        (company,),
    )
    current = _row(cur.fetchone())
    settings = c7._settings(cur, company)
    return {
        "ok": True,
        "company_code": company,
        "enabled": True,
        "resource_state": "ready" if (drafts or live or approved or demand_n) else "empty",
        "counts": {
            "draft_plans": drafts,
            "live_plans": live,
            "approved_scenarios": approved,
            "demand_items": demand_n,
            "open_handoffs": handoffs,
        },
        "current_plan": _public_plan(current) if current else None,
        "horizon": settings.get("default_horizon") or "quarterly",
        "currency": "KWD",
        "ja_enabled": True,
        "recruiting_enabled": _module_on(cur, company, "requisitions"),
        "comp_planning_enabled": _module_on(cur, company, "comp_planning"),
        "talent_enabled": _module_on(cur, company, "talent"),
        "payroll_enabled": _module_on(cur, company, "payroll"),
        "performance_enabled": _module_on(cur, company, "performance"),
        "recruiting_handoff_enabled": bool(settings.get("recruiting_handoff_enabled")),
        **honesty_payload(company_code=company),
    }


def list_plans(cur: Any, *, company_code: str, status: str | None = None) -> dict[str, Any]:
    ensure_schema(cur)
    company = c7.company_code_norm(company_code)
    if not _ja_ready(cur, company):
        return {**_unavailable(company=company, reason="ja_hard_dependency_unmet"), "plans": None}
    if not c7.module_enabled_for_company(cur, company):
        return {**_unavailable(company=company, reason="workforce_planning_disabled"), "plans": None}
    sql = "SELECT * FROM wfp_plans WHERE company_code=%s"
    params: list[Any] = [company]
    if status:
        sql += " AND status=%s"
        params.append(status)
    sql += " ORDER BY created_at DESC"
    cur.execute(sql, params)
    plans = [_public_plan(dict(r)) for r in cur.fetchall()]
    return {
        "ok": True,
        "plans": plans,
        "resource_state": "ready" if plans else "empty",
        **honesty_payload(company_code=company),
    }


def plan_detail(cur: Any, *, company_code: str, plan_id: str) -> dict[str, Any]:
    ensure_schema(cur)
    company = c7.company_code_norm(company_code)
    if not c7.module_enabled_for_company(cur, company):
        return {**_unavailable(company=company, reason="workforce_planning_disabled"), "plan": None}
    cur.execute("SELECT * FROM wfp_plans WHERE company_code=%s AND plan_id=%s", (company, plan_id))
    plan = _row(cur.fetchone())
    if not plan:
        return {"ok": False, "error": "plan_not_found"}
    return {"ok": True, "plan": _public_plan(plan), **honesty_payload(company_code=company)}


def create_plan(cur: Any, **kwargs: Any) -> dict[str, Any]:
    blocked = _require_kwd(kwargs.get("currency"))
    if blocked:
        return blocked
    result = c7.create_plan(cur, **kwargs)
    if result.get("ok"):
        result["plan"] = _public_plan(result.get("plan") or {})
        result.update(honesty_payload(company_code=kwargs.get("company_code")))
    return result


def freeze_baseline(
    cur: Any,
    *,
    company_code: str,
    actor_phone: str,
    plan_id: str,
    as_of_date: date | str,
    population: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    company = c7.company_code_norm(company_code)
    snap = list(population or canonical_actual_population(cur, company_code=company, as_of_date=as_of_date))
    result = c7.freeze_baseline(
        cur,
        company_code=company,
        actor_phone=actor_phone,
        plan_id=plan_id,
        as_of_date=as_of_date,
        population=snap,
    )
    if result.get("ok"):
        result["actual_ne_baseline"] = True
        result["not_second_actual_sot"] = True
        result["source_authority"] = "employment_org_ja"
        result.update(honesty_payload(company_code=company))
    return result


def get_baseline(cur: Any, *, company_code: str, plan_id: str) -> dict[str, Any]:
    ensure_schema(cur)
    company = c7.company_code_norm(company_code)
    if not c7.module_enabled_for_company(cur, company):
        return {**_unavailable(company=company, reason="workforce_planning_disabled"), "baseline": None, "rows": None}
    cur.execute("SELECT * FROM wfp_plans WHERE company_code=%s AND plan_id=%s", (company, plan_id))
    plan = _row(cur.fetchone())
    if not plan:
        return {"ok": False, "error": "plan_not_found"}
    if not plan.get("baseline_id"):
        return {
            "ok": True,
            "baseline": None,
            "rows": [],
            "resource_state": "empty",
            "actual_ne_baseline": True,
            **honesty_payload(company_code=company),
        }
    cur.execute(
        "SELECT * FROM wfp_baselines WHERE company_code=%s AND baseline_id=%s",
        (company, plan["baseline_id"]),
    )
    baseline = _row(cur.fetchone())
    cur.execute(
        """
        SELECT employee_key, org_unit, ja_profile_id, ja_grade_id, ja_level_id, currency
          FROM wfp_baseline_rows WHERE company_code=%s AND baseline_id=%s
         ORDER BY employee_key
        """,
        (company, plan["baseline_id"]),
    )
    rows = [dict(r) for r in cur.fetchall()]
    return {
        "ok": True,
        "baseline": baseline,
        "rows": rows,
        "frozen": True,
        "actual_ne_baseline": True,
        "not_second_actual_sot": True,
        **honesty_payload(company_code=company),
    }


def list_scenarios(cur: Any, *, company_code: str, plan_id: str) -> dict[str, Any]:
    ensure_schema(cur)
    company = c7.company_code_norm(company_code)
    if not c7.module_enabled_for_company(cur, company):
        return {**_unavailable(company=company, reason="workforce_planning_disabled"), "scenarios": None}
    cur.execute(
        "SELECT * FROM wfp_scenarios WHERE company_code=%s AND plan_id=%s ORDER BY created_at",
        (company, plan_id),
    )
    scenarios = [_public_scenario(dict(r)) for r in cur.fetchall()]
    return {
        "ok": True,
        "scenarios": scenarios,
        "resource_state": "ready" if scenarios else "empty",
        **honesty_payload(company_code=company),
    }


def create_scenario(cur: Any, **kwargs: Any) -> dict[str, Any]:
    result = c7.create_scenario(cur, **kwargs)
    if result.get("ok"):
        result["scenario"] = _public_scenario(result.get("scenario") or {})
        result.update(honesty_payload(company_code=kwargs.get("company_code")))
    return result


def revise_scenario(cur: Any, **kwargs: Any) -> dict[str, Any]:
    result = c7.revise_scenario(cur, **kwargs)
    if result.get("ok"):
        result["scenario"] = _public_scenario(result.get("scenario") or {})
        result.update(honesty_payload(company_code=kwargs.get("company_code")))
    return result


def list_assumptions(cur: Any, *, company_code: str, scenario_id: str) -> dict[str, Any]:
    company = c7.company_code_norm(company_code)
    if not c7.module_enabled_for_company(cur, company):
        return {**_unavailable(company=company, reason="workforce_planning_disabled"), "assumptions": None}
    cur.execute(
        """
        SELECT assumption_id, assumption_key, assumption_version, value_json, source, notes_en, notes_ar, created_at
          FROM wfp_assumptions WHERE company_code=%s AND scenario_id=%s
         ORDER BY assumption_key, assumption_version
        """,
        (company, scenario_id),
    )
    items = [dict(r) for r in cur.fetchall()]
    return {
        "ok": True,
        "assumptions": items,
        "explicit_versioned": True,
        "no_silent_wave5_turnover_forecast": True,
        **honesty_payload(company_code=company),
    }


def upsert_assumption(cur: Any, **kwargs: Any) -> dict[str, Any]:
    result = c7.upsert_assumption(cur, **kwargs)
    if result.get("ok"):
        result.update(honesty_payload(company_code=kwargs.get("company_code")))
    return result


def list_demand(
    cur: Any,
    *,
    company_code: str,
    plan_id: str | None = None,
    scenario_id: str | None = None,
    include_cost: bool = False,
    owner_keys: list[str] | None = None,
) -> dict[str, Any]:
    company = c7.company_code_norm(company_code)
    if not _ja_ready(cur, company):
        return {**_unavailable(company=company, reason="ja_hard_dependency_unmet"), "demand": None}
    if not c7.module_enabled_for_company(cur, company):
        return {**_unavailable(company=company, reason="workforce_planning_disabled"), "demand": None}
    if owner_keys is not None and not owner_keys:
        return {
            "ok": True,
            "demand": [],
            "company_wide": False,
            "empty_manager_scope_is_zero_rows": True,
            "resource_state": "empty",
            **honesty_payload(company_code=company),
        }
    sql = "SELECT * FROM wfp_demand_items WHERE company_code=%s"
    params: list[Any] = [company]
    if plan_id:
        sql += " AND plan_id=%s"
        params.append(plan_id)
    if scenario_id:
        sql += " AND scenario_id=%s"
        params.append(scenario_id)
    if owner_keys is not None:
        sql += " AND owner_key = ANY(%s)"
        params.append(list(owner_keys))
    sql += " ORDER BY created_at"
    cur.execute(sql, params)
    items = [_public_demand(dict(r), include_cost=include_cost) for r in cur.fetchall()]
    return {
        "ok": True,
        "demand": items,
        "resource_state": "ready" if items else "empty",
        "company_wide": owner_keys is None,
        **honesty_payload(company_code=company),
    }


def add_demand(cur: Any, **kwargs: Any) -> dict[str, Any]:
    blocked = _require_kwd(kwargs.get("currency") or "KWD")
    if blocked:
        return blocked
    result = c7.add_demand(cur, **kwargs)
    if result.get("ok"):
        result["demand"] = _public_demand(result.get("demand") or {}, include_cost=True)
        result.update(honesty_payload(company_code=kwargs.get("company_code")))
    return result


def list_planned_positions(cur: Any, *, company_code: str, scenario_id: str, include_cost: bool = False) -> dict[str, Any]:
    demand = list_demand(cur, company_code=company_code, scenario_id=scenario_id, include_cost=include_cost)
    if demand.get("demand") is None:
        return demand
    return {
        "ok": True,
        "planned_positions": demand.get("demand") or [],
        "planned_position_ne_actual_position": True,
        "not_actual_vacancy": True,
        **honesty_payload(company_code=company_code),
    }


def project_headcount(cur: Any, *, company_code: str, scenario_id: str) -> dict[str, Any]:
    result = c7.project_headcount(cur, company_code=company_code, scenario_id=scenario_id)
    if result.get("ok"):
        result["explainable"] = True
        result["no_frontend_forecast_authority"] = True
        result.update(honesty_payload(company_code=company_code))
    return result


def project_planned_cost(cur: Any, *, company_code: str, scenario_id: str) -> dict[str, Any]:
    result = c7.project_planned_cost(cur, company_code=company_code, scenario_id=scenario_id)
    if result.get("ok"):
        result["label"] = "planned_estimated_cost"
        result["not_finalized_payroll_cost"] = True
        result.update(honesty_payload(company_code=company_code))
    return result


def compute_gap(cur: Any, **kwargs: Any) -> dict[str, Any]:
    result = c7.compute_gap(cur, **kwargs)
    if result.get("ok"):
        result.update(honesty_payload(company_code=kwargs.get("company_code")))
    return result


def list_gaps(cur: Any, *, company_code: str, scenario_id: str) -> dict[str, Any]:
    company = c7.company_code_norm(company_code)
    if not c7.module_enabled_for_company(cur, company):
        return {**_unavailable(company=company, reason="workforce_planning_disabled"), "gaps": None}
    cur.execute(
        """
        SELECT gap_id, definition, ja_profile_id, quantity, assumptions_ref, created_at
          FROM wfp_gaps WHERE company_code=%s AND scenario_id=%s
         ORDER BY created_at
        """,
        (company, scenario_id),
    )
    gaps = [dict(r) for r in cur.fetchall()]
    return {
        "ok": True,
        "gaps": gaps,
        "resource_state": "ready" if gaps else "empty",
        "definition_driven": True,
        "no_universal_workforce_gap_score": True,
        **honesty_payload(company_code=company),
    }


def compare_scenarios(cur: Any, **kwargs: Any) -> dict[str, Any]:
    result = c7.compare_scenarios(cur, **kwargs)
    if result.get("ok"):
        result.update(honesty_payload(company_code=kwargs.get("company_code")))
    return result


def submit_plan(cur: Any, **kwargs: Any) -> dict[str, Any]:
    result = c7.submit_plan(cur, **kwargs)
    if result.get("ok"):
        result["plan"] = _public_plan(result.get("plan") or {})
        result.update(honesty_payload(company_code=kwargs.get("company_code")))
    return result


def approve_scenario(cur: Any, **kwargs: Any) -> dict[str, Any]:
    result = c7.approve_scenario(cur, **kwargs)
    if result.get("ok"):
        if result.get("plan"):
            result["plan"] = _public_plan(result["plan"])
        if result.get("scenario"):
            result["scenario"] = _public_scenario(result["scenario"])
        result["approval_ne_actual_workforce_change"] = True
        result.update(honesty_payload(company_code=kwargs.get("company_code")))
    return result


def list_approvals(cur: Any, *, company_code: str, plan_id: str) -> dict[str, Any]:
    company = c7.company_code_norm(company_code)
    cur.execute(
        """
        SELECT approval_id, scenario_id, approver_key, decision, decided_at
          FROM wfp_approvals WHERE company_code=%s AND plan_id=%s
         ORDER BY decided_at
        """,
        (company, plan_id),
    )
    return {
        "ok": True,
        "approvals": [dict(r) for r in cur.fetchall()],
        "approval_ne_actual_workforce_change": True,
        **honesty_payload(company_code=company),
    }


def create_execution_handoff(cur: Any, **kwargs: Any) -> dict[str, Any]:
    company = c7.company_code_norm(kwargs.get("company_code"))
    demand_id = str(kwargs.get("demand_id") or "")
    cur.execute(
        "SELECT quantity FROM wfp_demand_items WHERE company_code=%s AND demand_id=%s",
        (company, demand_id),
    )
    demand = _row(cur.fetchone())
    qty = abs(int((demand or {}).get("quantity") or 0))
    idem = f"wfp:{company}:{demand_id}:q{qty}"
    cur.execute(
        "SELECT * FROM wfp_execution_handoffs WHERE company_code=%s AND idempotency_key=%s",
        (company, idem),
    )
    existing = _row(cur.fetchone())
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
            **honesty_payload(company_code=company),
        }
    result = c7.create_execution_handoff(cur, **kwargs)
    if result.get("ok"):
        result.update(honesty_payload(company_code=company))
    return result


def cancel_execution_handoff(cur: Any, **kwargs: Any) -> dict[str, Any]:
    result = c7.cancel_execution_handoff(cur, **kwargs)
    if result.get("ok"):
        result.update(honesty_payload(company_code=kwargs.get("company_code")))
    return result


def list_handoffs(cur: Any, *, company_code: str, plan_id: str) -> dict[str, Any]:
    company = c7.company_code_norm(company_code)
    cur.execute(
        """
        SELECT handoff_id, scenario_id, demand_id, target_authority, quantity, status,
               requisition_id, idempotency_key, employment_mutated_by_wfp, headcount_mutated_by_wfp,
               job_posted, candidate_created, hire_created, created_at
          FROM wfp_execution_handoffs WHERE company_code=%s AND plan_id=%s
         ORDER BY created_at
        """,
        (company, plan_id),
    )
    items = []
    for raw in cur.fetchall():
        item = dict(raw)
        item["employment_mutated_by_wfp"] = False
        item["headcount_mutated_by_wfp"] = False
        item["job_posted"] = False
        item["candidate_created"] = False
        item["hire_created"] = False
        item["approved_workforce_demand_ne_approved_requisition"] = True
        items.append(item)
    return {"ok": True, "handoffs": items, "no_auto_post_hire": True, **honesty_payload(company_code=company)}


def execution_status(cur: Any, *, company_code: str, plan_id: str) -> dict[str, Any]:
    handoffs = list_handoffs(cur, company_code=company_code, plan_id=plan_id)
    return {
        "ok": True,
        "handoff_count": len(handoffs.get("handoffs") or []),
        "any_employment_mutated": False,
        "any_job_posted": False,
        "any_hire_created": False,
        "approval_ne_execution": True,
        **honesty_payload(company_code=company_code),
    }


def actual_vs_plan(cur: Any, *, company_code: str, scenario_id: str) -> dict[str, Any]:
    company = c7.company_code_norm(company_code)
    actual = canonical_actual_headcount(cur, company_code=company)
    result = c7.actual_vs_plan(cur, company_code=company, scenario_id=scenario_id, actual_headcount=actual)
    if result.get("ok"):
        result["actual_authority"] = "frozen_canonical_domains_wave5"
        result["wfp_not_actual_sot"] = True
        result.update(honesty_payload(company_code=company))
    return result


def list_history(cur: Any, *, company_code: str, plan_id: str | None = None) -> dict[str, Any]:
    ensure_schema(cur)
    company = c7.company_code_norm(company_code)
    enabled = c7.module_enabled_for_company(cur, company)
    sql = """
        SELECT audit_id, actor_phone, action, entity_type, entity_id, detail, created_at
          FROM wfp_audit_events WHERE company_code=%s
    """
    params: list[Any] = [company]
    if plan_id:
        sql += " AND (entity_id=%s OR COALESCE(detail->>'plan_id','')=%s)"
        params.extend([plan_id, plan_id])
    sql += " ORDER BY created_at ASC"
    cur.execute(sql, params)
    history = [dict(r) for r in cur.fetchall()]
    if plan_id:
        cur.execute(
            """
            SELECT plan_id, status, baseline_id, plan_version, created_at, approved_at, currency, horizon
              FROM wfp_plans WHERE company_code=%s AND plan_id=%s
            """,
            (company, plan_id),
        )
        plan = _row(cur.fetchone())
        if plan:
            history.append(
                {
                    "action": "plan_state",
                    "entity_type": "plan",
                    "entity_id": plan_id,
                    "created_at": plan.get("approved_at") or plan.get("created_at"),
                    "detail": {
                        "status": plan.get("status"),
                        "baseline_id": str(plan.get("baseline_id") or "") or None,
                        "plan_version": plan.get("plan_version"),
                        "reconstructed_from_canonical_row": True,
                    },
                }
            )
        cur.execute(
            """
            SELECT scenario_id, code, scenario_type, status, scenario_version
              FROM wfp_scenarios WHERE company_code=%s AND plan_id=%s
             ORDER BY created_at
            """,
            (company, plan_id),
        )
        scenarios = [dict(r) for r in cur.fetchall()]
        if scenarios:
            history.append(
                {
                    "action": "scenario_versions",
                    "entity_type": "plan",
                    "entity_id": plan_id,
                    "detail": {"scenarios": scenarios, "reconstructed_from_canonical_row": True},
                }
            )
        cur.execute(
            """
            SELECT demand_id, demand_type, quantity, ja_profile_id
              FROM wfp_demand_items WHERE company_code=%s AND plan_id=%s
            """,
            (company, plan_id),
        )
        demand = [dict(r) for r in cur.fetchall()]
        if demand:
            history.append(
                {
                    "action": "demand_items",
                    "entity_type": "plan",
                    "entity_id": plan_id,
                    "detail": {"demand": demand, "reconstructed_from_canonical_row": True},
                }
            )
        approvals = list_approvals(cur, company_code=company, plan_id=plan_id)
        if approvals.get("approvals"):
            history.append(
                {
                    "action": "approvals",
                    "entity_type": "plan",
                    "entity_id": plan_id,
                    "detail": {"approvals": approvals["approvals"]},
                }
            )
        handoffs = list_handoffs(cur, company_code=company, plan_id=plan_id)
        if handoffs.get("handoffs"):
            history.append(
                {
                    "action": "handoffs",
                    "entity_type": "plan",
                    "entity_id": plan_id,
                    "detail": {"handoffs": handoffs["handoffs"]},
                }
            )
    return {
        "ok": True,
        "enabled": enabled,
        "resource_state": "ready" if history else ("unavailable" if not enabled else "empty"),
        "history": history,
        "historically_reconstructable": bool(history),
        "history_preserved_when_disabled": True,
        **honesty_payload(company_code=company),
    }


def export_plan(cur: Any, *, company_code: str, plan_id: str, include_cost: bool = False) -> dict[str, Any]:
    plan = plan_detail(cur, company_code=company_code, plan_id=plan_id)
    if plan.get("ok") is False:
        return plan
    demand = list_demand(cur, company_code=company_code, plan_id=plan_id, include_cost=include_cost)
    scenarios = list_scenarios(cur, company_code=company_code, plan_id=plan_id)
    return {
        "ok": True,
        "export": {
            "plan": plan.get("plan"),
            "scenarios": scenarios.get("scenarios") or [],
            "demand": demand.get("demand") or [],
        },
        "hidden_rows_included": False,
        "manager_scope_bypassed": False,
        **honesty_payload(company_code=company_code),
    }


def manager_workspace(
    cur: Any,
    *,
    company_code: str,
    manager_scope_employee_keys: list[str] | None,
    plan_id: str | None = None,
) -> dict[str, Any]:
    company = c7.company_code_norm(company_code)
    if not _ja_ready(cur, company):
        return {**_unavailable(company=company, reason="ja_hard_dependency_unmet"), "demand": None, "company_wide": False}
    if not c7.module_enabled_for_company(cur, company):
        return {**_unavailable(company=company, reason="workforce_planning_disabled"), "demand": None, "company_wide": False}
    keys = list(manager_scope_employee_keys or [])
    if not keys:
        return {
            "ok": True,
            "enabled": True,
            "resource_state": "empty",
            "demand": [],
            "plans": [],
            "company_wide": False,
            "empty_manager_scope_is_zero_rows": True,
            "cost_sensitive_included": False,
            "restructuring_included": False,
            **honesty_payload(company_code=company),
        }
    demand = list_demand(
        cur,
        company_code=company,
        plan_id=plan_id,
        include_cost=False,
        owner_keys=keys,
    )
    demand["company_wide"] = False
    demand["cost_sensitive_included"] = False
    demand["restructuring_included"] = False
    demand["final_execution_authority"] = False
    return demand


def assistant_query(
    cur: Any,
    *,
    company_code: str,
    actor: str,
    question_kind: str,
    scenario_id: str | None = None,
) -> dict[str, Any]:
    if question_kind in {
        "create_demand",
        "approve_plan",
        "generate_requisition",
        "mutate_assumptions",
        "hiring_decision",
        "layoff_decision",
        "ai_forecast",
        "create_scenario",
        "execute_handoff",
    }:
        return {
            "ok": False,
            "error": "mutation_forbidden",
            "mutations": False,
            "no_ai_forecast_authority": True,
            **honesty_payload(company_code=company_code),
        }
    result = c7.assistant_query_wfp(
        cur, company_code=company_code, actor=actor, question_kind=question_kind, scenario_id=scenario_id
    )
    result["mutations"] = False
    result.update(honesty_payload(company_code=company_code))
    return result
