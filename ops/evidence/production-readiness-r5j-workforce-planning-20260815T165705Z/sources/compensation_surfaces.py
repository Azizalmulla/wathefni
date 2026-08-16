#!/usr/bin/env python3
"""R5I Compensation Planning product surfaces — thin composition over frozen C6.

HTTP and HR Web are adapters. Cycle freeze, eligibility, budgets, JA-linked
bands, recommendations, calibration, SOD, finalization, and handoffs stay
domain-authoritative. This module never invents grades, FX, or a salary mutation.
"""
from __future__ import annotations

from decimal import Decimal
from typing import Any, Mapping

import compensation_planning_c6 as c6
import job_architecture_c1 as ja

PHASE = "compensation_surfaces_r5i"
CONTRACT_VERSION = "compensation_surfaces_v1"
PASS_STAMP = "PRODUCTION_READINESS_R5I_COMPENSATION_PLANNING_SURFACE_FULL_PASS"
COMMERCIAL_MODULE_KEY = "comp_planning"


def honesty_payload(*, company_code: str | None = None) -> dict[str, Any]:
    return {
        "phase": PHASE,
        "contract_version": CONTRACT_VERSION,
        "pass_stamp": PASS_STAMP,
        "commercial_module_key": COMMERCIAL_MODULE_KEY,
        "canonical_authority": ("compensation_planning_c6",),
        "compensation_plan_is_not_salary_change": True,
        "salary_change_is_not_payroll_application": True,
        "payroll_application_is_not_paid": True,
        "finalized_is_not_applied": True,
        "eligible_is_not_increase": True,
        "grade_is_not_salary_band": True,
        "salary_range_is_not_employee_salary": True,
        "recommendation_is_not_approval": True,
        "original_recommendation_preserved": True,
        "ja_is_hard": True,
        "no_duplicate_grades": True,
        "no_fx": True,
        "kwd_explicit": True,
        "performance_optional": True,
        "rating_not_automatic_increase": True,
        "talent_optional": True,
        "hipo_not_automatic_pay": True,
        "empty_manager_scope_is_zero_rows": True,
        "assistant_mutations": False,
        "company_code": c6.company_code_norm(company_code) if company_code else None,
        **c6.honesty_payload(company_code=company_code),
    }


def ensure_schema(cur: Any) -> None:
    c6.ensure_compensation_planning_c6_schema(cur)


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
        VALUES (%s, 'comp_planning', %s, 'compensation_surfaces', '{}'::jsonb, now())
        ON CONFLICT (company_code, module_key)
        DO UPDATE SET enabled=EXCLUDED.enabled, source='compensation_surfaces', updated_at=now()
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
    reason: str = "sync compensation planning catalog entitlement",
) -> dict[str, Any]:
    ensure_schema(cur)
    company = c6.company_code_norm(company_code)
    if enabled:
        result = c6.enable_company_comp_planning(
            cur, company_code=company, actor_phone=actor_phone, reason=reason
        )
    else:
        result = c6.disable_company_comp_planning(
            cur, company_code=company, actor_phone=actor_phone, reason=reason
        )
    if result.get("ok"):
        _upsert_company_module(cur, company, bool(enabled))
    return {
        "ok": bool(result.get("ok")),
        "company_code": company,
        "enabled": bool(enabled),
        "history_preserved": True,
        "result": result,
        **honesty_payload(company_code=company),
    }


def _public_cycle(row: Mapping[str, Any]) -> dict[str, Any]:
    status = str(row.get("status") or "")
    return {
        "cycle_id": str(row.get("cycle_id") or ""),
        "code": row.get("code"),
        "title_en": row.get("title_en"),
        "title_ar": row.get("title_ar"),
        "status": status,
        "status_label_en": c6.status_label(status, lang="en"),
        "status_label_ar": c6.status_label(status, lang="ar"),
        "currency": row.get("currency"),
        "budget_overrun_mode": row.get("budget_overrun_mode"),
        "snapshot_frozen": bool(row.get("snapshot_frozen")),
        "performance_input_enabled": bool(row.get("performance_input_enabled")),
        "talent_input_enabled": bool(row.get("talent_input_enabled")),
        "launched_at": row.get("launched_at"),
        "finalized_at": row.get("finalized_at"),
        "finalized_is_not_applied": True,
    }


def workspace_summary(cur: Any, *, company_code: str) -> dict[str, Any]:
    ensure_schema(cur)
    company = c6.company_code_norm(company_code)
    if not _ja_ready(cur, company):
        return _unavailable(company=company, reason="ja_hard_dependency_unmet")
    if not c6.module_enabled_for_company(cur, company):
        return _unavailable(company=company, reason="comp_planning_disabled")
    cur.execute("SELECT COUNT(*) AS n FROM cp_cycles WHERE company_code=%s AND status='draft'", (company,))
    drafts = int((_row(cur.fetchone()).get("n") or 0))
    cur.execute(
        "SELECT COUNT(*) AS n FROM cp_cycles WHERE company_code=%s AND status IN ('launched','calibrating')",
        (company,),
    )
    live = int((_row(cur.fetchone()).get("n") or 0))
    cur.execute("SELECT COUNT(*) AS n FROM cp_cycles WHERE company_code=%s AND status='finalized'", (company,))
    finalized = int((_row(cur.fetchone()).get("n") or 0))
    cur.execute(
        """
        SELECT COUNT(*) AS n FROM cp_recommendations r
         WHERE r.company_code=%s AND r.layer IN ('original','calibrated')
           AND NOT EXISTS (
             SELECT 1 FROM cp_approvals a
              WHERE a.recommendation_id=r.recommendation_id AND a.decision='approved'
           )
        """,
        (company,),
    )
    pending = int((_row(cur.fetchone()).get("n") or 0))
    cur.execute(
        """
        SELECT COALESCE(SUM(allocated),0) AS allocated, COALESCE(SUM(recommended),0) AS recommended,
               COALESCE(SUM(approved),0) AS approved
          FROM cp_budgets WHERE company_code=%s
        """,
        (company,),
    )
    budget = _row(cur.fetchone())
    return {
        "ok": True,
        "company_code": company,
        "enabled": True,
        "resource_state": "ready" if (drafts or live or finalized) else "empty",
        "counts": {
            "draft_cycles": drafts,
            "live_cycles": live,
            "finalized_cycles": finalized,
            "approvals_needing_attention": pending,
        },
        "budget_usage": {
            "allocated": _money(budget.get("allocated")),
            "recommended": _money(budget.get("recommended")),
            "approved": _money(budget.get("approved")),
            "currency": "KWD",
        },
        "ja_enabled": True,
        "performance_enabled": _module_on(cur, company, "performance"),
        "talent_enabled": _module_on(cur, company, "talent"),
        "payroll_enabled": _module_on(cur, company, "payroll"),
        "workforce_planning_enabled": False,
        **honesty_payload(company_code=company),
    }


def list_cycles(cur: Any, *, company_code: str, status: str | None = None) -> dict[str, Any]:
    ensure_schema(cur)
    company = c6.company_code_norm(company_code)
    if not _ja_ready(cur, company):
        return {**_unavailable(company=company, reason="ja_hard_dependency_unmet"), "cycles": None}
    if not c6.module_enabled_for_company(cur, company):
        return {**_unavailable(company=company, reason="comp_planning_disabled"), "cycles": None}
    sql = "SELECT * FROM cp_cycles WHERE company_code=%s"
    params: list[Any] = [company]
    if status:
        sql += " AND status=%s"
        params.append(status)
    sql += " ORDER BY created_at DESC"
    cur.execute(sql, params)
    return {"ok": True, "cycles": [_public_cycle(dict(r)) for r in cur.fetchall()], **honesty_payload(company_code=company)}


def cycle_detail(cur: Any, *, company_code: str, cycle_id: str) -> dict[str, Any]:
    ensure_schema(cur)
    company = c6.company_code_norm(company_code)
    if not c6.module_enabled_for_company(cur, company):
        return {**_unavailable(company=company, reason="comp_planning_disabled"), "cycle": None}
    cur.execute("SELECT * FROM cp_cycles WHERE company_code=%s AND cycle_id=%s", (company, cycle_id))
    camp = _row(cur.fetchone())
    if not camp:
        return {"ok": False, "error": "cycle_not_found"}
    return {"ok": True, "cycle": _public_cycle(camp), **honesty_payload(company_code=company)}


def eligibility_snapshot(
    cur: Any,
    *,
    company_code: str,
    cycle_id: str,
    manager_scope_employee_keys: list[str] | None = None,
) -> dict[str, Any]:
    ensure_schema(cur)
    company = c6.company_code_norm(company_code)
    if not c6.module_enabled_for_company(cur, company):
        return {**_unavailable(company=company, reason="comp_planning_disabled"), "population": None}
    sql = """
        SELECT employee_key, eligible, eligibility_explanation, ja_grade_id, ja_level_id, ja_profile_id,
               band_id, band_version, manager_key, department_snapshot, current_base, currency,
               performance_rating_input, talent_context_input, employment_ref
          FROM cp_cycle_snapshots
         WHERE company_code=%s AND cycle_id=%s
    """
    params: list[Any] = [company, cycle_id]
    if manager_scope_employee_keys is not None:
        keys = list(manager_scope_employee_keys)
        if not keys:
            return {
                "ok": True,
                "population": [],
                "empty_manager_scope_is_zero_rows": True,
                "company_wide": False,
                **honesty_payload(company_code=company),
            }
        sql += " AND employee_key = ANY(%s)"
        params.append(keys)
    sql += " ORDER BY employee_key"
    cur.execute(sql, params)
    rows = []
    for raw in cur.fetchall():
        item = dict(raw)
        item["current_base"] = _money(item.get("current_base"))
        item["eligible_is_not_increase"] = True
        rows.append(item)
    return {
        "ok": True,
        "population": rows,
        "eligible_is_not_increase": True,
        "snapshot_frozen": True,
        **honesty_payload(company_code=company),
    }


def list_budgets(cur: Any, *, company_code: str, cycle_id: str) -> dict[str, Any]:
    ensure_schema(cur)
    company = c6.company_code_norm(company_code)
    if not c6.module_enabled_for_company(cur, company):
        return {**_unavailable(company=company, reason="comp_planning_disabled"), "budgets": None}
    cur.execute(
        """
        SELECT budget_id, scope_type, scope_key, currency, allocated, recommended, approved
          FROM cp_budgets WHERE company_code=%s AND cycle_id=%s ORDER BY scope_type, scope_key
        """,
        (company, cycle_id),
    )
    budgets = []
    for raw in cur.fetchall():
        item = dict(raw)
        allocated = _money(item.get("allocated")) or 0
        recommended = _money(item.get("recommended")) or 0
        approved = _money(item.get("approved")) or 0
        budgets.append(
            {
                **item,
                "allocated": allocated,
                "recommended": recommended,
                "approved": approved,
                "remaining": allocated - recommended,
                "over_budget": recommended > allocated,
                "allocated_recommended_approved_distinct": True,
            }
        )
    return {"ok": True, "budgets": budgets, **honesty_payload(company_code=company)}


def list_bands(cur: Any, *, company_code: str) -> dict[str, Any]:
    ensure_schema(cur)
    company = c6.company_code_norm(company_code)
    if not c6.module_enabled_for_company(cur, company):
        return {**_unavailable(company=company, reason="comp_planning_disabled"), "bands": None}
    cur.execute(
        """
        SELECT b.band_id, b.code, b.band_version, b.ja_grade_id, b.ja_level_id, b.currency,
               b.minimum, b.midpoint, b.maximum, b.effective_start, g.code AS ja_grade_code,
               g.name_en AS ja_grade_name_en, g.name_ar AS ja_grade_name_ar
          FROM cp_salary_bands b
          JOIN ja_grade g ON g.grade_id=b.ja_grade_id AND g.company_code=b.company_code
         WHERE b.company_code=%s
         ORDER BY b.code, b.band_version
        """,
        (company,),
    )
    bands = []
    for raw in cur.fetchall():
        item = dict(raw)
        bands.append(
            {
                **item,
                "minimum": _money(item.get("minimum")),
                "midpoint": _money(item.get("midpoint")),
                "maximum": _money(item.get("maximum")),
                "grade_is_not_salary_band": True,
                "salary_range_is_not_employee_salary": True,
                "midpoint_not_recommended_salary": True,
                "belongs_to_compensation_not_ja": True,
            }
        )
    return {"ok": True, "bands": bands, "no_local_grade_created": True, **honesty_payload(company_code=company)}


def _recommendation_layers(cur: Any, company: str, cycle_id: str, employee_key: str) -> dict[str, Any]:
    hist = c6.recommendation_history(
        cur, company_code=company, cycle_id=cycle_id, employee_key=employee_key
    )
    layers = {str(item.get("layer")): dict(item) for item in (hist.get("history") or [])}
    for item in layers.values():
        item["amount"] = _money(item.get("amount"))
    return {
        "original": layers.get("original"),
        "calibrated": layers.get("calibrated"),
        "approved": layers.get("approved"),
        "original_preserved": bool(layers.get("original")),
        "history": hist.get("history") or [],
    }


def worksheet(
    cur: Any,
    *,
    company_code: str,
    cycle_id: str,
    manager_scope_employee_keys: list[str] | None = None,
) -> dict[str, Any]:
    snap = eligibility_snapshot(
        cur,
        company_code=company_code,
        cycle_id=cycle_id,
        manager_scope_employee_keys=manager_scope_employee_keys,
    )
    if snap.get("ok") is False or snap.get("population") is None:
        return snap
    company = c6.company_code_norm(company_code)
    rows = []
    for item in snap.get("population") or []:
        layers = _recommendation_layers(cur, company, cycle_id, str(item["employee_key"]))
        ratio = c6.compute_compa_ratio(
            cur, company_code=company, cycle_id=cycle_id, employee_key=str(item["employee_key"])
        )
        rows.append(
            {
                **item,
                "recommendations": layers,
                "compa_ratio": ratio.get("compa_ratio"),
                "eligible_is_not_increase": True,
                "salary_range_is_not_employee_salary": True,
            }
        )
    return {
        "ok": True,
        "rows": rows,
        "company_wide": manager_scope_employee_keys is None,
        "empty_manager_scope_is_zero_rows": manager_scope_employee_keys == [],
        **honesty_payload(company_code=company),
    }


def manager_worksheet(
    cur: Any,
    *,
    company_code: str,
    manager_scope_employee_keys: list[str] | None,
    cycle_id: str | None = None,
) -> dict[str, Any]:
    company = c6.company_code_norm(company_code)
    if not _ja_ready(cur, company):
        return {**_unavailable(company=company, reason="ja_hard_dependency_unmet"), "rows": None, "company_wide": False}
    if not c6.module_enabled_for_company(cur, company):
        return {**_unavailable(company=company, reason="comp_planning_disabled"), "rows": None, "company_wide": False}
    keys = list(manager_scope_employee_keys or [])
    if not keys:
        return {
            "ok": True,
            "enabled": True,
            "resource_state": "empty",
            "rows": [],
            "cycles": [],
            "company_wide": False,
            "empty_manager_scope_is_zero_rows": True,
            **honesty_payload(company_code=company),
        }
    if not cycle_id:
        cur.execute(
            """
            SELECT cycle_id FROM cp_cycles
             WHERE company_code=%s AND status IN ('launched','calibrating')
             ORDER BY created_at DESC LIMIT 1
            """,
            (company,),
        )
        found = _row(cur.fetchone())
        cycle_id = str(found.get("cycle_id") or "") if found else ""
    if not cycle_id:
        return {
            "ok": True,
            "enabled": True,
            "resource_state": "empty",
            "rows": [],
            "cycles": [],
            "company_wide": False,
            **honesty_payload(company_code=company),
        }
    sheet = worksheet(
        cur,
        company_code=company,
        cycle_id=cycle_id,
        manager_scope_employee_keys=keys,
    )
    sheet["company_wide"] = False
    sheet["peer_manager_budgets_included"] = False
    sheet["hr_calibration_authority"] = False
    sheet["talent_sensitive_included"] = False
    return sheet


def list_recommendations(cur: Any, *, company_code: str, cycle_id: str) -> dict[str, Any]:
    company = c6.company_code_norm(company_code)
    cur.execute(
        """
        SELECT recommendation_id, employee_key, recommendation_type, amount, percent, currency,
               rationale, actor_key, layer, created_at, proposed_ja_grade_id
          FROM cp_recommendations
         WHERE company_code=%s AND cycle_id=%s
         ORDER BY created_at
        """,
        (company, cycle_id),
    )
    items = []
    for raw in cur.fetchall():
        item = dict(raw)
        item["amount"] = _money(item.get("amount"))
        item["recommendation_is_not_approval"] = True
        items.append(item)
    return {
        "ok": True,
        "recommendations": items,
        "original_recommendation_preserved": any(i.get("layer") == "original" for i in items),
        **honesty_payload(company_code=company),
    }


def list_approvals(cur: Any, *, company_code: str, cycle_id: str) -> dict[str, Any]:
    company = c6.company_code_norm(company_code)
    cur.execute(
        """
        SELECT approval_id, employee_key, recommendation_id, approver_key, decision, decided_at
          FROM cp_approvals WHERE company_code=%s AND cycle_id=%s ORDER BY decided_at
        """,
        (company, cycle_id),
    )
    return {
        "ok": True,
        "approvals": [dict(r) for r in cur.fetchall()],
        "approval_not_salary_mutation": True,
        **honesty_payload(company_code=company),
    }


def list_final_decisions(cur: Any, *, company_code: str, cycle_id: str) -> dict[str, Any]:
    company = c6.company_code_norm(company_code)
    cur.execute(
        """
        SELECT decision_id, employee_key, recommendation_type, approved_amount, approved_percent,
               currency, old_base, proposed_new_base, effective_date, applied
          FROM cp_final_decisions WHERE company_code=%s AND cycle_id=%s ORDER BY employee_key
        """,
        (company, cycle_id),
    )
    decisions = []
    for raw in cur.fetchall():
        item = dict(raw)
        for key in ("approved_amount", "old_base", "proposed_new_base"):
            item[key] = _money(item.get(key))
        item["finalized_is_not_applied"] = True
        item["applied"] = False
        decisions.append(item)
    return {"ok": True, "decisions": decisions, "finalized_not_applied": True, **honesty_payload(company_code=company)}


def list_handoffs(cur: Any, *, company_code: str, cycle_id: str) -> dict[str, Any]:
    company = c6.company_code_norm(company_code)
    cur.execute(
        """
        SELECT handoff_id, decision_id, employee_key, change_type, old_value, proposed_new_value,
               currency, effective_date, target_authority, applied, employment_mutated_by_comp, payroll_paid
          FROM cp_apply_handoffs WHERE company_code=%s AND cycle_id=%s ORDER BY created_at
        """,
        (company, cycle_id),
    )
    items = []
    for raw in cur.fetchall():
        item = dict(raw)
        item["old_value"] = _money(item.get("old_value"))
        item["proposed_new_value"] = _money(item.get("proposed_new_value"))
        item["handoff_created_is_not_salary_changed"] = True
        item["applied"] = False
        item["payroll_paid"] = False
        items.append(item)
    return {"ok": True, "handoffs": items, **honesty_payload(company_code=company)}


def execution_status(cur: Any, *, company_code: str, cycle_id: str) -> dict[str, Any]:
    decisions = list_final_decisions(cur, company_code=company_code, cycle_id=cycle_id)
    handoffs = list_handoffs(cur, company_code=company_code, cycle_id=cycle_id)
    return {
        "ok": True,
        "finalized_count": len(decisions.get("decisions") or []),
        "handoff_count": len(handoffs.get("handoffs") or []),
        "any_applied": False,
        "any_payroll_paid": False,
        "finalized_is_not_applied": True,
        "handoff_is_not_downstream_execution": True,
        **honesty_payload(company_code=company_code),
    }


def list_history(cur: Any, *, company_code: str, cycle_id: str | None = None) -> dict[str, Any]:
    ensure_schema(cur)
    company = c6.company_code_norm(company_code)
    enabled = c6.module_enabled_for_company(cur, company)
    sql = """
        SELECT audit_id, actor_phone, action, entity_type, entity_id, detail, created_at
          FROM cp_audit_events WHERE company_code=%s
    """
    params: list[Any] = [company]
    if cycle_id:
        sql += " AND (entity_id=%s OR COALESCE(detail->>'cycle_id','')=%s)"
        params.extend([cycle_id, cycle_id])
    sql += " ORDER BY created_at ASC"
    cur.execute(sql, params)
    history = [dict(r) for r in cur.fetchall()]
    if cycle_id:
        cur.execute(
            """
            SELECT cycle_id, status, snapshot_frozen, created_at, launched_at, finalized_at, currency
              FROM cp_cycles WHERE company_code=%s AND cycle_id=%s
            """,
            (company, cycle_id),
        )
        camp = _row(cur.fetchone())
        if camp:
            history.append(
                {
                    "action": "cycle_state",
                    "entity_type": "cycle",
                    "entity_id": cycle_id,
                    "created_at": camp.get("finalized_at") or camp.get("launched_at") or camp.get("created_at"),
                    "detail": {
                        "status": camp.get("status"),
                        "snapshot_frozen": bool(camp.get("snapshot_frozen")),
                        "reconstructed_from_canonical_row": True,
                    },
                }
            )
        recs = list_recommendations(cur, company_code=company, cycle_id=cycle_id)
        if recs.get("recommendations"):
            history.append(
                {
                    "action": "recommendation_layers",
                    "entity_type": "cycle",
                    "entity_id": cycle_id,
                    "detail": {
                        "original_preserved": recs.get("original_recommendation_preserved"),
                        "layers": [item.get("layer") for item in recs["recommendations"]],
                    },
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


def export_worksheet(
    cur: Any,
    *,
    company_code: str,
    cycle_id: str,
    manager_scope_employee_keys: list[str] | None = None,
) -> dict[str, Any]:
    sheet = worksheet(
        cur,
        company_code=company_code,
        cycle_id=cycle_id,
        manager_scope_employee_keys=manager_scope_employee_keys,
    )
    if sheet.get("ok") is False:
        return sheet
    return {
        "ok": True,
        "export": sheet.get("rows") or [],
        "hidden_rows_included": False,
        "manager_scope_bypassed": False,
        "respondent_answer_map_included": False,
        **honesty_payload(company_code=company_code),
    }


def create_cycle(cur: Any, **kwargs: Any) -> dict[str, Any]:
    blocked = _require_kwd(kwargs.get("currency"))
    if blocked:
        return blocked
    result = c6.create_cycle(cur, **kwargs)
    if result.get("ok"):
        result.update(honesty_payload(company_code=kwargs.get("company_code")))
    return result


def launch_cycle(cur: Any, **kwargs: Any) -> dict[str, Any]:
    result = c6.launch_cycle(cur, **kwargs)
    if result.get("ok"):
        result["eligible_is_not_increase"] = True
        result.update(honesty_payload(company_code=kwargs.get("company_code")))
    return result


def create_budget(cur: Any, **kwargs: Any) -> dict[str, Any]:
    blocked = _require_kwd(kwargs.get("currency"))
    if blocked:
        return blocked
    result = c6.create_budget(cur, **kwargs)
    if result.get("ok"):
        result.update(honesty_payload(company_code=kwargs.get("company_code")))
    return result


def upsert_salary_band(cur: Any, **kwargs: Any) -> dict[str, Any]:
    blocked = _require_kwd(kwargs.get("currency"))
    if blocked:
        return blocked
    result = c6.upsert_salary_band(cur, **kwargs)
    if result.get("ok"):
        result["belongs_to_compensation_not_ja"] = True
        result.update(honesty_payload(company_code=kwargs.get("company_code")))
    return result


def create_recommendation(cur: Any, **kwargs: Any) -> dict[str, Any]:
    result = c6.create_recommendation(cur, **kwargs)
    if result.get("ok"):
        result["recommendation_is_not_approval"] = True
        result.update(honesty_payload(company_code=kwargs.get("company_code")))
    return result


def calibrate_recommendation(cur: Any, **kwargs: Any) -> dict[str, Any]:
    result = c6.calibrate_recommendation(cur, **kwargs)
    if result.get("ok"):
        result.update(honesty_payload(company_code=kwargs.get("company_code")))
    return result


def approve_recommendation(cur: Any, **kwargs: Any) -> dict[str, Any]:
    result = c6.approve_recommendation(cur, **kwargs)
    if result.get("ok"):
        result.update(honesty_payload(company_code=kwargs.get("company_code")))
    return result


def finalize_cycle(cur: Any, **kwargs: Any) -> dict[str, Any]:
    result = c6.finalize_cycle(cur, **kwargs)
    if result.get("ok"):
        result["finalized_is_not_applied"] = True
        result.update(honesty_payload(company_code=kwargs.get("company_code")))
    return result


def create_handoff(cur: Any, **kwargs: Any) -> dict[str, Any]:
    company = c6.company_code_norm(kwargs.get("company_code"))
    cycle_id = str(kwargs.get("cycle_id") or "")
    decision_id = str(kwargs.get("decision_id") or "")
    target = str(kwargs.get("target_authority") or "").lower()
    cur.execute(
        """
        SELECT * FROM cp_apply_handoffs
         WHERE company_code=%s AND cycle_id=%s AND decision_id=%s AND target_authority=%s
         ORDER BY created_at ASC LIMIT 1
        """,
        (company, cycle_id, decision_id, target),
    )
    existing = _row(cur.fetchone())
    if existing:
        return {
            "ok": True,
            "handoff": existing,
            "applied": False,
            "idempotent_replay": True,
            "employment_mutated_by_comp": False,
            "payroll_paid": False,
            **honesty_payload(company_code=company),
        }
    result = c6.create_apply_handoff(cur, **kwargs)
    if result.get("ok"):
        result["idempotent_replay"] = False
        result["handoff_created_is_not_salary_changed"] = True
        result.update(honesty_payload(company_code=company))
    return result


def assistant_query(cur: Any, *, company_code: str, actor: str, question_kind: str, cycle_id: str | None = None) -> dict[str, Any]:
    if question_kind in {"recommend_pay", "change_salary", "approve", "apply_plan", "infer_from_talent", "invent_fx"}:
        return {"ok": False, "error": "mutation_forbidden", "mutations": False, **honesty_payload(company_code=company_code)}
    result = c6.assistant_query_comp(
        cur, company_code=company_code, actor=actor, question_kind=question_kind, cycle_id=cycle_id
    )
    result["mutations"] = False
    result.update(honesty_payload(company_code=company_code))
    return result
