#!/usr/bin/env python3
"""R5F Benefits product surfaces — thin composition over frozen Wave 6 C3.

HTTP and clients are adapters. Plan, eligibility, enrollment, waiver, coverage,
contributions, and provider refs stay domain-authoritative. This module never
invents a second Benefits model, claims engine, Kuwait statutory formula, or
payroll deduction.
"""
from __future__ import annotations

from datetime import date
from typing import Any, Mapping

import benefits_administration_c3 as c3

PHASE = "benefits_surfaces_r5f"
CONTRACT_VERSION = "benefits_surfaces_v1"
PASS_STAMP = "PRODUCTION_READINESS_R5F_BENEFITS_SURFACE_FULL_PASS"
COMMERCIAL_MODULE_KEY = "benefits"

EMPLOYEE_FORBIDDEN_KEYS = frozenset(
    {
        "hr_admin",
        "enabled_by_phone",
        "disabled_at",
        "plan_authoring",
        "eligibility_admin",
        "other_employee_keys",
        "manager_private_detail",
    }
)

SENSITIVE_KEYS = frozenset(
    {
        "member_id",
        "policy_group_number",
        "policy_group_ref",
        "amount",
        "percent",
        "employee_amount",
        "employer_amount",
        "component_mapping",
    }
)


def honesty_payload(*, company_code: str | None = None) -> dict[str, Any]:
    return {
        "phase": PHASE,
        "contract_version": CONTRACT_VERSION,
        "pass_stamp": PASS_STAMP,
        "commercial_module_key": COMMERCIAL_MODULE_KEY,
        "canonical_authority": ("benefits_administration_c3",),
        "eligible_is_not_enrolled": True,
        "election_is_not_coverage": True,
        "waiver_is_not_ineligibility": True,
        "dependent_exists_is_not_covered": True,
        "coverage_is_not_provider_confirmed": True,
        "contribution_is_not_deduction": True,
        "handoff_is_not_payroll_execution": True,
        "payroll_optional": True,
        "claims_out": True,
        "no_invented_kuwait_formulas": True,
        "no_manager_private_default": True,
        "no_duplicate_dependent_authority": True,
        "company_code": c3.company_code_norm(company_code) if company_code else None,
        **c3.honesty_payload(company_code=company_code),
    }


def strip_employee_admin(value: Any) -> Any:
    if isinstance(value, Mapping):
        out: dict[str, Any] = {}
        for key, item in value.items():
            if str(key).strip().lower() in EMPLOYEE_FORBIDDEN_KEYS:
                continue
            out[str(key)] = strip_employee_admin(item)
        return out
    if isinstance(value, list):
        return [strip_employee_admin(item) for item in value]
    return value


def strip_sensitive(value: Any) -> Any:
    if isinstance(value, Mapping):
        out: dict[str, Any] = {}
        for key, item in value.items():
            if str(key).strip().lower() in SENSITIVE_KEYS:
                continue
            out[str(key)] = strip_sensitive(item)
        return out
    if isinstance(value, list):
        return [strip_sensitive(item) for item in value]
    return value


def ensure_schema(cur: Any) -> None:
    c3.ensure_benefits_administration_c3_schema(cur)


def _upsert_company_module(cur: Any, company: str, enabled: bool) -> None:
    cur.execute(
        """
        INSERT INTO company_modules (company_code, module_key, enabled, source, settings, updated_at)
        VALUES (%s, 'benefits', %s, 'benefits_surfaces', '{}'::jsonb, now())
        ON CONFLICT (company_code, module_key)
        DO UPDATE SET enabled=EXCLUDED.enabled, source='benefits_surfaces', updated_at=now()
        """,
        (company, bool(enabled)),
    )


def sync_catalog_entitlement(
    cur: Any,
    *,
    company_code: str,
    actor_phone: str,
    enabled: bool,
    reason: str = "sync benefits catalog entitlement",
    payroll_handoff_enabled: bool | None = None,
) -> dict[str, Any]:
    ensure_schema(cur)
    company = c3.company_code_norm(company_code)
    kwargs: dict[str, Any] = {}
    if payroll_handoff_enabled is not None:
        kwargs["payroll_handoff_enabled"] = payroll_handoff_enabled
    if enabled:
        result = c3.enable_company_benefits(
            cur, company_code=company, actor_phone=actor_phone, reason=reason, **kwargs
        )
    else:
        result = c3.disable_company_benefits(
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


def _row(value: Any) -> dict[str, Any]:
    return dict(value) if value else {}


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


def decorate_enrollment(enrollment: dict[str, Any]) -> dict[str, Any]:
    row = dict(enrollment)
    status = str(row.get("status") or "")
    row["eligible"] = status not in {"declined", "cancelled"}
    row["elected"] = status in {"elected", "pending_evidence", "pending_approval", "confirmed", "coverage_active"}
    row["waived"] = status == "waived"
    row["coverage_active"] = status == "coverage_active"
    row["provider_confirmed"] = bool(row.get("provider_confirmed"))
    row["election_is_not_coverage"] = status != "coverage_active"
    row["eligible_is_not_enrolled"] = status in {"eligible", "enrollment_open"}
    row["waiver_is_not_ineligibility"] = True
    return row


def decorate_coverage(coverage: dict[str, Any]) -> dict[str, Any]:
    row = dict(coverage)
    row["provider_confirmed"] = bool(row.get("provider_confirmed"))
    row["internal_recorded"] = str(row.get("provenance") or "") == "internal_recorded"
    row["coverage_is_not_provider_confirmed"] = not bool(row.get("provider_confirmed"))
    row["election_is_not_coverage"] = False
    return row


def decorate_contribution(contrib: dict[str, Any]) -> dict[str, Any]:
    row = dict(contrib)
    row["contribution_is_not_deduction"] = True
    row["paid_amount"] = None
    row["estimated_or_configured"] = True
    return row


def workspace_summary(cur: Any, *, company_code: str) -> dict[str, Any]:
    ensure_schema(cur)
    company = c3.company_code_norm(company_code)
    if not c3.module_enabled_for_company(cur, company):
        return {
            "ok": True,
            "company_code": company,
            "enabled": False,
            "resource_state": "unavailable",
            "counts": None,
            **honesty_payload(company_code=company),
        }
    cur.execute("SELECT COUNT(*) AS n FROM bn_plans WHERE company_code=%s AND status='published'", (company,))
    active_plans = int((_row(cur.fetchone()).get("n") or 0))
    cur.execute(
        """
        SELECT COUNT(*) AS n FROM bn_enrollments
         WHERE company_code=%s AND status IN ('enrollment_open','pending_evidence','pending_approval')
        """,
        (company,),
    )
    needing_action = int((_row(cur.fetchone()).get("n") or 0))
    cur.execute(
        """
        SELECT COUNT(*) AS n FROM bn_enrollment_windows
         WHERE company_code=%s AND status='open' AND ends_on >= CURRENT_DATE
        """,
        (company,),
    )
    open_windows = int((_row(cur.fetchone()).get("n") or 0))
    cur.execute(
        """
        SELECT COUNT(*) AS n FROM bn_coverage_periods
         WHERE company_code=%s AND status='active' AND start_date > CURRENT_DATE
        """,
        (company,),
    )
    upcoming = int((_row(cur.fetchone()).get("n") or 0))
    cur.execute(
        """
        SELECT COUNT(*) AS n FROM bn_coverage_periods
         WHERE company_code=%s AND status='active' AND provider_confirmed IS FALSE
        """,
        (company,),
    )
    exceptions = int((_row(cur.fetchone()).get("n") or 0))
    return {
        "ok": True,
        "company_code": company,
        "enabled": True,
        "resource_state": "ready",
        "counts": {
            "active_plans": active_plans,
            "employees_requiring_action": needing_action,
            "open_windows": open_windows,
            "upcoming_effective_changes": upcoming,
            "coverage_provider_exceptions": exceptions,
        },
        "payroll_on": _module_on(cur, company, "payroll"),
        "learning_on": _module_on(cur, company, "learning"),
        "talent_on": _module_on(cur, company, "talent"),
        "job_architecture_on": _module_on(cur, company, "job_architecture"),
        **honesty_payload(company_code=company),
    }


def list_plans(cur: Any, *, company_code: str, published_only: bool = False, limit: int = 200) -> dict[str, Any]:
    ensure_schema(cur)
    company = c3.company_code_norm(company_code)
    where = ["company_code=%s"]
    params: list[Any] = [company]
    if published_only:
        where.append("status='published'")
    cur.execute(f"SELECT COUNT(*) AS n FROM bn_plans WHERE {' AND '.join(where)}", params)
    total = int((_row(cur.fetchone()).get("n") or 0))
    cur.execute(
        f"""
        SELECT * FROM bn_plans
         WHERE {' AND '.join(where)}
         ORDER BY updated_at DESC
         LIMIT %s
        """,
        [*params, max(1, min(int(limit or 200), 400))],
    )
    items = [_row(r) for r in (cur.fetchall() or [])]
    return {
        "ok": True,
        "plans": items,
        "total": total,
        "resource_state": "empty" if total == 0 else "ready",
        **honesty_payload(company_code=company),
    }


def list_plan_versions(cur: Any, *, company_code: str, plan_id: str, limit: int = 100) -> dict[str, Any]:
    ensure_schema(cur)
    company = c3.company_code_norm(company_code)
    cur.execute(
        """
        SELECT * FROM bn_plan_versions
         WHERE company_code=%s AND plan_id=%s
         ORDER BY effective_version DESC
         LIMIT %s
        """,
        (company, plan_id, max(1, min(int(limit or 100), 200))),
    )
    rows = [_row(r) for r in (cur.fetchall() or [])]
    return {
        "ok": True,
        "versions": rows,
        "total": len(rows),
        "later_version_does_not_rewrite_history": True,
        **honesty_payload(company_code=company),
    }


def list_eligibility(
    cur: Any, *, company_code: str, employee_key: str | None = None, plan_id: str | None = None, limit: int = 200
) -> dict[str, Any]:
    ensure_schema(cur)
    company = c3.company_code_norm(company_code)
    where = ["e.company_code=%s"]
    params: list[Any] = [company]
    if employee_key:
        where.append("e.employee_key=%s")
        params.append(employee_key)
    if plan_id:
        where.append("e.plan_id=%s")
        params.append(plan_id)
    cur.execute(
        f"""
        SELECT e.*, p.code AS plan_code, p.title_en, p.title_ar
          FROM bn_eligibility_evaluations e
          JOIN bn_plans p ON p.plan_id=e.plan_id
         WHERE {' AND '.join(where)}
         ORDER BY e.created_at DESC
         LIMIT %s
        """,
        [*params, max(1, min(int(limit or 200), 400))],
    )
    rows = [_row(r) for r in (cur.fetchall() or [])]
    for row in rows:
        row["eligible_is_not_enrolled"] = True
        row["enrolled"] = False
    return {
        "ok": True,
        "evaluations": rows,
        "total": len(rows),
        "resource_state": "empty" if not rows else "ready",
        **honesty_payload(company_code=company),
    }


def list_enrollments(
    cur: Any, *, company_code: str, employee_key: str | None = None, limit: int = 200
) -> dict[str, Any]:
    ensure_schema(cur)
    company = c3.company_code_norm(company_code)
    where = ["n.company_code=%s"]
    params: list[Any] = [company]
    if employee_key:
        where.append("n.employee_key=%s")
        params.append(employee_key)
    cur.execute(
        f"""
        SELECT n.*, p.code AS plan_code, p.title_en, p.title_ar
          FROM bn_enrollments n
          JOIN bn_plans p ON p.plan_id=n.plan_id
         WHERE {' AND '.join(where)}
         ORDER BY n.updated_at DESC
         LIMIT %s
        """,
        [*params, max(1, min(int(limit or 200), 400))],
    )
    rows = [decorate_enrollment(_row(r)) for r in (cur.fetchall() or [])]
    return {
        "ok": True,
        "enrollments": rows,
        "total": len(rows),
        "resource_state": "empty" if not rows else "ready",
        **honesty_payload(company_code=company),
    }


def list_waivers(cur: Any, *, company_code: str, employee_key: str | None = None, limit: int = 200) -> dict[str, Any]:
    listed = list_enrollments(cur, company_code=company_code, employee_key=employee_key, limit=limit)
    waivers = [row for row in (listed.get("enrollments") or []) if row.get("waived")]
    return {
        "ok": True,
        "waivers": waivers,
        "total": len(waivers),
        "waiver_is_not_ineligibility": True,
        "resource_state": "empty" if not waivers else "ready",
        **honesty_payload(company_code=company_code),
    }


def list_coverage(
    cur: Any, *, company_code: str, employee_key: str | None = None, limit: int = 200
) -> dict[str, Any]:
    ensure_schema(cur)
    company = c3.company_code_norm(company_code)
    where = ["c.company_code=%s"]
    params: list[Any] = [company]
    if employee_key:
        where.append("c.employee_key=%s")
        params.append(employee_key)
    cur.execute(
        f"""
        SELECT c.*, p.code AS plan_code, p.title_en, p.title_ar
          FROM bn_coverage_periods c
          JOIN bn_plans p ON p.plan_id=c.plan_id
         WHERE {' AND '.join(where)}
         ORDER BY c.start_date DESC
         LIMIT %s
        """,
        [*params, max(1, min(int(limit or 200), 400))],
    )
    rows = [decorate_coverage(_row(r)) for r in (cur.fetchall() or [])]
    return {
        "ok": True,
        "coverage": rows,
        "total": len(rows),
        "resource_state": "empty" if not rows else "ready",
        **honesty_payload(company_code=company),
    }


def list_contributions(
    cur: Any, *, company_code: str, employee_key: str | None = None, limit: int = 200
) -> dict[str, Any]:
    ensure_schema(cur)
    company = c3.company_code_norm(company_code)
    where = ["c.company_code=%s"]
    params: list[Any] = [company]
    if employee_key:
        where.append(
            """
            (c.enrollment_id IN (SELECT enrollment_id FROM bn_enrollments WHERE company_code=%s AND employee_key=%s)
             OR c.coverage_id IN (SELECT coverage_id FROM bn_coverage_periods WHERE company_code=%s AND employee_key=%s))
            """
        )
        params.extend([company, employee_key, company, employee_key])
    cur.execute(
        f"""
        SELECT c.* FROM bn_contributions c
         WHERE {' AND '.join(where)}
         ORDER BY c.effective_start DESC
         LIMIT %s
        """,
        [*params, max(1, min(int(limit or 200), 400))],
    )
    rows = [decorate_contribution(_row(r)) for r in (cur.fetchall() or [])]
    return {
        "ok": True,
        "contributions": rows,
        "total": len(rows),
        "contribution_is_not_deduction": True,
        "resource_state": "empty" if not rows else "ready",
        **honesty_payload(company_code=company),
    }


def list_handoffs(
    cur: Any, *, company_code: str, employee_key: str | None = None, limit: int = 200
) -> dict[str, Any]:
    ensure_schema(cur)
    company = c3.company_code_norm(company_code)
    where = ["company_code=%s"]
    params: list[Any] = [company]
    if employee_key:
        where.append("employee_key=%s")
        params.append(employee_key)
    cur.execute(
        f"""
        SELECT * FROM bn_payroll_handoffs
         WHERE {' AND '.join(where)}
         ORDER BY created_at DESC
         LIMIT %s
        """,
        [*params, max(1, min(int(limit or 200), 400))],
    )
    rows = [_row(r) for r in (cur.fetchall() or [])]
    for row in rows:
        row["applied_to_payroll"] = False
        row["handoff_is_not_payroll_execution"] = True
        row["finalized_payroll_not_rewritten"] = True
    return {
        "ok": True,
        "handoffs": rows,
        "total": len(rows),
        **honesty_payload(company_code=company),
    }


def list_member_refs(
    cur: Any, *, company_code: str, employee_key: str | None = None, limit: int = 200
) -> dict[str, Any]:
    ensure_schema(cur)
    company = c3.company_code_norm(company_code)
    where = ["company_code=%s"]
    params: list[Any] = [company]
    if employee_key:
        where.append("employee_key=%s")
        params.append(employee_key)
    cur.execute(
        f"""
        SELECT * FROM bn_provider_member_refs
         WHERE {' AND '.join(where)}
         ORDER BY created_at DESC
         LIMIT %s
        """,
        [*params, max(1, min(int(limit or 200), 400))],
    )
    rows = [_row(r) for r in (cur.fetchall() or [])]
    for row in rows:
        row["not_proof_of_insurer_active_unless_provider_confirmed"] = not bool(row.get("provider_status_confirmed"))
    return {
        "ok": True,
        "member_refs": rows,
        "total": len(rows),
        **honesty_payload(company_code=company),
    }


def list_dependents_for_coverage(
    cur: Any, *, company_code: str, employee_key: str, limit: int = 100
) -> dict[str, Any]:
    """Canonical Wave 3 dependents plus coverage-link state. No second profile."""
    ensure_schema(cur)
    company = c3.company_code_norm(company_code)
    dependents: list[dict[str, Any]] = []
    cur.execute("SELECT to_regclass('employee_dependents') AS t")
    if _row(cur.fetchone()).get("t"):
        cur.execute(
            """
            SELECT dependent_id, employee_key, relationship, name_en, name_ar, status
              FROM employee_dependents
             WHERE company_code=%s AND employee_key=%s
             ORDER BY name_en NULLS LAST
             LIMIT %s
            """,
            (company, employee_key, max(1, min(int(limit or 100), 200))),
        )
        dependents = [_row(r) for r in (cur.fetchall() or [])]
    cur.execute(
        """
        SELECT l.*, c.employee_key, c.status AS coverage_status
          FROM bn_dependent_coverage_links l
          JOIN bn_coverage_periods c ON c.coverage_id=l.coverage_id
         WHERE l.company_code=%s AND c.employee_key=%s
        """,
        (company, employee_key),
    )
    links = [_row(r) for r in (cur.fetchall() or [])]
    covered_ids = {str(item.get("dependent_id")) for item in links}
    for dep in dependents:
        dep["exists"] = True
        dep["covered"] = str(dep.get("dependent_id")) in covered_ids
        dep["dependent_exists_is_not_covered"] = not dep["covered"]
    return {
        "ok": True,
        "dependents": dependents,
        "coverage_links": links,
        "does_not_create_dependent_master": True,
        **honesty_payload(company_code=company),
    }


def list_history(
    cur: Any, *, company_code: str, employee_key: str | None = None, limit: int = 200
) -> dict[str, Any]:
    ensure_schema(cur)
    company = c3.company_code_norm(company_code)
    where = ["company_code=%s"]
    params: list[Any] = [company]
    if employee_key:
        where.append("(detail->>'employee_key'=%s OR entity_id=%s)")
        params.extend([employee_key, employee_key])
    cur.execute(
        f"""
        SELECT * FROM bn_audit_events
         WHERE {' AND '.join(where)}
         ORDER BY created_at DESC
         LIMIT %s
        """,
        [*params, max(1, min(int(limit or 200), 400))],
    )
    events = [_row(r) for r in (cur.fetchall() or [])]
    enrollments = list_enrollments(cur, company_code=company, employee_key=employee_key, limit=limit)
    coverage = list_coverage(cur, company_code=company, employee_key=employee_key, limit=limit)
    versions: list[dict[str, Any]] = []
    cur.execute(
        """
        SELECT * FROM bn_plan_versions
         WHERE company_code=%s
         ORDER BY created_at DESC
         LIMIT %s
        """,
        (company, max(1, min(int(limit or 200), 200))),
    )
    versions = [_row(r) for r in (cur.fetchall() or [])]
    return {
        "ok": True,
        "events": events,
        "enrollments": enrollments.get("enrollments") or [],
        "coverage": coverage.get("coverage") or [],
        "plan_versions": versions,
        "later_policy_does_not_rewrite_history": True,
        **honesty_payload(company_code=company),
    }


def _employment_attributes(cur: Any, *, company: str, employee_key: str) -> dict[str, Any]:
    """Server employment truth for eligibility. Client attributes never override this."""
    attrs: dict[str, Any] = {}
    try:
        cur.execute("SELECT to_regclass('employees') AS t")
        if not _row(cur.fetchone()).get("t"):
            return attrs
        cur.execute(
            """
            SELECT * FROM employees
             WHERE company_code=%s AND employee_key=%s
             LIMIT 1
            """,
            (company, employee_key),
        )
        row = _row(cur.fetchone())
        if not row:
            return attrs
        for key in ("employment_status", "employment_type", "location", "grade"):
            if row.get(key) not in (None, ""):
                attrs[key] = row[key]
        if not attrs.get("employment_status") and row.get("status"):
            attrs["employment_status"] = row["status"]
    except Exception:
        return attrs
    return attrs


def latest_rule_for_plan(cur: Any, *, company: str, plan_id: str) -> dict[str, Any]:
    cur.execute(
        """
        SELECT * FROM bn_eligibility_rules
         WHERE company_code=%s AND plan_id=%s AND status='active'
         ORDER BY rule_version DESC, created_at DESC
         LIMIT 1
        """,
        (company, plan_id),
    )
    return _row(cur.fetchone())


def employee_elect_or_waive(
    cur: Any,
    *,
    company_code: str,
    actor_phone: str,
    employee_key: str,
    plan_id: str,
    waive: bool,
    tier: str | None = None,
    reason: str = "",
    evaluation_id: str | None = None,
    window_id: str | None = None,
    attributes: dict[str, Any] | None = None,
    enrollment_id: str | None = None,
) -> dict[str, Any]:
    """Employee/HR election adapter. Never confirms coverage."""
    if enrollment_id:
        return c3.elect_or_waive(
            cur,
            company_code=company_code,
            actor_phone=actor_phone,
            enrollment_id=enrollment_id,
            waive=waive,
            tier=tier,
            reason=reason,
        )
    company = c3.company_code_norm(company_code)
    eval_id = evaluation_id
    if not eval_id:
        rule = latest_rule_for_plan(cur, company=company, plan_id=plan_id)
        if not rule:
            return {"ok": False, "error": "eligibility_rule_not_found"}
        merged = dict(attributes or {})
        merged.update(_employment_attributes(cur, company=company, employee_key=employee_key))
        evaluated = c3.evaluate_eligibility(
            cur,
            company_code=company,
            employee_key=employee_key,
            plan_id=plan_id,
            rule_id=str(rule["rule_id"]),
            attributes=merged,
        )
        if not evaluated.get("ok"):
            return evaluated
        if not evaluated.get("eligible"):
            return {**evaluated, "ok": False, "error": "not_eligible", "eligible_is_not_enrolled": True}
        eval_id = str((evaluated.get("evaluation") or {}).get("evaluation_id") or "")
    started = c3.start_enrollment(
        cur,
        company_code=company,
        actor_phone=actor_phone,
        employee_key=employee_key,
        plan_id=plan_id,
        evaluation_id=eval_id,
        window_id=window_id,
        source="employee_self",
    )
    if not started.get("ok"):
        return started
    return c3.elect_or_waive(
        cur,
        company_code=company,
        actor_phone=actor_phone,
        enrollment_id=str((started.get("enrollment") or {}).get("enrollment_id") or ""),
        waive=waive,
        tier=tier,
        reason=reason,
    )


def prepare_enrollment(
    cur: Any,
    *,
    company_code: str,
    actor_phone: str,
    employee_key: str,
    plan_id: str,
    attributes: dict[str, Any] | None = None,
    window_id: str | None = None,
) -> dict[str, Any]:
    """HR evaluate + start. Eligibility alone never creates coverage."""
    company = c3.company_code_norm(company_code)
    rule = latest_rule_for_plan(cur, company=company, plan_id=plan_id)
    if not rule:
        return {"ok": False, "error": "eligibility_rule_not_found"}
    merged = dict(attributes or {})
    merged.update(_employment_attributes(cur, company=company, employee_key=employee_key))
    evaluated = c3.evaluate_eligibility(
        cur,
        company_code=company,
        employee_key=employee_key,
        plan_id=plan_id,
        rule_id=str(rule["rule_id"]),
        attributes=merged,
    )
    if not evaluated.get("ok"):
        return evaluated
    if not evaluated.get("eligible"):
        return {
            **evaluated,
            "started": False,
            "coverage_created": False,
            "eligible_is_not_enrolled": True,
        }
    started = c3.start_enrollment(
        cur,
        company_code=company,
        actor_phone=actor_phone,
        employee_key=employee_key,
        plan_id=plan_id,
        evaluation_id=str((evaluated.get("evaluation") or {}).get("evaluation_id") or ""),
        window_id=window_id,
        source="hr_admin",
    )
    return {
        **started,
        "evaluation": evaluated.get("evaluation"),
        "eligible": True,
        "enrolled": False,
        "coverage_created": False,
        "eligible_is_not_enrolled": True,
        "election_is_not_coverage": True,
    }


def employee_plan_detail(
    cur: Any, *, company_code: str, employee_key: str, plan_id: str
) -> dict[str, Any]:
    ensure_schema(cur)
    company = c3.company_code_norm(company_code)
    if not c3.module_enabled_for_company(cur, company):
        return {
            "ok": True,
            "resource_state": "unavailable",
            "enabled": False,
            "plan": None,
            **honesty_payload(company_code=company),
        }
    plans = list_plans(cur, company_code=company, published_only=True, limit=200)
    plan = next((row for row in (plans.get("plans") or []) if str(row.get("plan_id")) == str(plan_id)), None)
    if not plan:
        return {"ok": False, "error": "plan_not_found"}
    enrollments = [
        row
        for row in (list_enrollments(cur, company_code=company, employee_key=employee_key).get("enrollments") or [])
        if str(row.get("plan_id")) == str(plan_id)
    ]
    coverage = [
        row
        for row in (list_coverage(cur, company_code=company, employee_key=employee_key).get("coverage") or [])
        if str(row.get("plan_id")) == str(plan_id)
    ]
    contribs = list_contributions(cur, company_code=company, employee_key=employee_key, limit=50)
    members = list_member_refs(cur, company_code=company, employee_key=employee_key, limit=50)
    eligibility = list_eligibility(cur, company_code=company, employee_key=employee_key, plan_id=plan_id, limit=20)
    deps = list_dependents_for_coverage(cur, company_code=company, employee_key=employee_key)
    evals = eligibility.get("evaluations") or []
    latest_eval = evals[0] if evals else None
    return strip_employee_admin(
        {
            "ok": True,
            "enabled": True,
            "resource_state": "ready",
            "employee_key": employee_key,
            "plan": plan,
            "enrollments": enrollments,
            "coverage": coverage,
            "contributions": contribs.get("contributions") or [],
            "member_refs": members.get("member_refs") or [],
            "eligibility": evals,
            "latest_eligible": None if latest_eval is None else bool(latest_eval.get("eligible")),
            "dependents": deps.get("dependents") or [],
            "hr_admin_exposed": False,
            **honesty_payload(company_code=company),
        }
    )


def employee_workspace(cur: Any, *, company_code: str, employee_key: str) -> dict[str, Any]:
    ensure_schema(cur)
    view = c3.employee_benefits_view(cur, company_code=company_code, employee_key=employee_key)
    if not view.get("ok"):
        err = view.get("error")
        if err in {"benefits_disabled_for_company", "employee_self_service_disabled"}:
            return {
                "ok": True,
                "resource_state": "unavailable",
                "enabled": False,
                "plans": None,
                "enrollments": None,
                "coverage": None,
                "waivers": None,
                "hr_admin_exposed": False,
                **honesty_payload(company_code=company_code),
            }
        return view
    company = c3.company_code_norm(company_code)
    plans = list_plans(cur, company_code=company, published_only=True, limit=100)
    enrollments = [decorate_enrollment(row) for row in (view.get("enrollments") or [])]
    coverage = [decorate_coverage(row) for row in (view.get("coverage") or [])]
    contribs = list_contributions(cur, company_code=company, employee_key=employee_key, limit=50)
    members = list_member_refs(cur, company_code=company, employee_key=employee_key, limit=50)
    deps = list_dependents_for_coverage(cur, company_code=company, employee_key=employee_key)
    eligible_evals = list_eligibility(cur, company_code=company, employee_key=employee_key, limit=50)
    return strip_employee_admin(
        {
            "ok": True,
            "enabled": True,
            "resource_state": "ready",
            "employee_key": employee_key,
            "plans": plans.get("plans") or [],
            "enrollments": enrollments,
            "coverage": coverage,
            "waivers": [row for row in enrollments if row.get("waived")],
            "contributions": contribs.get("contributions") or [],
            "member_refs": members.get("member_refs") or [],
            "dependents": deps.get("dependents") or [],
            "eligibility": eligible_evals.get("evaluations") or [],
            "hr_admin_exposed": False,
            **honesty_payload(company_code=company),
        }
    )
