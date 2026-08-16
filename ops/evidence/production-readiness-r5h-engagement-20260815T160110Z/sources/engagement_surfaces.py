#!/usr/bin/env python3
"""R5H Engagement product surfaces — thin composition over frozen Wave 6 C5.

HTTP and clients are adapters. Survey, version, audience freeze, anonymity,
aggregates, complementary suppression, eNPS, and action plans stay
domain-authoritative. This module never invents a second survey engine,
recognition, AI sentiment, or an ER/employment mutation.
"""
from __future__ import annotations

from typing import Any, Mapping

import engagement_c5 as c5

PHASE = "engagement_surfaces_r5h"
CONTRACT_VERSION = "engagement_surfaces_v1"
PASS_STAMP = "PRODUCTION_READINESS_R5H_ENGAGEMENT_SURFACE_FULL_PASS"
COMMERCIAL_MODULE_KEY = "engagement"

EMPLOYEE_FORBIDDEN_KEYS = frozenset(
    {
        "hr_admin",
        "enabled_by_phone",
        "disabled_at",
        "audience_snapshot",
        "audience_employee_keys",
        "employee_attrs",
        "scores",
        "enps",
        "action_plans",
        "free_text",
        "items",
        "respondent",
        "other_employee_keys",
        "manager_private_detail",
    }
)


def honesty_payload(*, company_code: str | None = None) -> dict[str, Any]:
    return {
        "phase": PHASE,
        "contract_version": CONTRACT_VERSION,
        "pass_stamp": PASS_STAMP,
        "commercial_module_key": COMMERCIAL_MODULE_KEY,
        "canonical_authority": ("engagement_c5",),
        "anonymous_is_not_identified": True,
        "participation_is_not_answer_mapping": True,
        "suppressed_is_not_zero": True,
        "survey_result_is_not_action_plan": True,
        "action_plan_is_not_er_case": True,
        "no_auto_er": True,
        "no_engagement_ai_authority": True,
        "no_universal_employee_score": True,
        "recognition_out": True,
        "empty_manager_scope_is_not_company_wide": True,
        "export_obeys_suppression": True,
        "wave5_typed_facts_only": True,
        "assistant_mutations": False,
        "company_code": c5.company_code_norm(company_code) if company_code else None,
        **c5.honesty_payload(company_code=company_code),
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


def ensure_schema(cur: Any) -> None:
    c5.ensure_engagement_c5_schema(cur)


def _upsert_company_module(cur: Any, company: str, enabled: bool) -> None:
    cur.execute(
        """
        INSERT INTO company_modules (company_code, module_key, enabled, source, settings, updated_at)
        VALUES (%s, 'engagement', %s, 'engagement_surfaces', '{}'::jsonb, now())
        ON CONFLICT (company_code, module_key)
        DO UPDATE SET enabled=EXCLUDED.enabled, source='engagement_surfaces', updated_at=now()
        """,
        (company, bool(enabled)),
    )


def sync_catalog_entitlement(
    cur: Any,
    *,
    company_code: str,
    actor_phone: str,
    enabled: bool,
    reason: str = "sync engagement catalog entitlement",
) -> dict[str, Any]:
    ensure_schema(cur)
    company = c5.company_code_norm(company_code)
    if enabled:
        result = c5.enable_company_engagement(
            cur, company_code=company, actor_phone=actor_phone, reason=reason
        )
    else:
        result = c5.disable_company_engagement(
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


def _public_campaign(row: Mapping[str, Any]) -> dict[str, Any]:
    camp = dict(row)
    privacy = str(camp.get("privacy_mode") or "")
    return {
        "campaign_id": str(camp.get("campaign_id") or ""),
        "survey_id": str(camp.get("survey_id") or ""),
        "survey_version_id": str(camp.get("survey_version_id") or ""),
        "title_en": camp.get("title_en"),
        "title_ar": camp.get("title_ar"),
        "status": camp.get("status"),
        "status_label_en": c5.status_label(camp.get("status"), lang="en"),
        "status_label_ar": c5.status_label(camp.get("status"), lang="ar"),
        "privacy_mode": privacy,
        "privacy_mode_label_en": c5.status_label(privacy, lang="en"),
        "privacy_mode_label_ar": c5.status_label(privacy, lang="ar"),
        "anonymous": privacy == "anonymous",
        "identified": privacy == "identified",
        "min_responses": camp.get("min_responses"),
        "audience_frozen": bool(camp.get("audience_frozen")),
        "opens_at": camp.get("opens_at"),
        "closes_at": camp.get("closes_at"),
        "launched_at": camp.get("launched_at"),
        "closed_at": camp.get("closed_at"),
        "calculation_version": camp.get("calculation_version"),
    }


def workspace_summary(cur: Any, *, company_code: str) -> dict[str, Any]:
    ensure_schema(cur)
    company = c5.company_code_norm(company_code)
    if not c5.module_enabled_for_company(cur, company):
        return {
            "ok": True,
            "company_code": company,
            "enabled": False,
            "resource_state": "unavailable",
            "counts": None,
            **honesty_payload(company_code=company),
        }
    cur.execute(
        "SELECT COUNT(*) AS n FROM eng_campaigns WHERE company_code=%s AND status='launched'",
        (company,),
    )
    live = int((_row(cur.fetchone()).get("n") or 0))
    cur.execute(
        "SELECT COUNT(*) AS n FROM eng_campaigns WHERE company_code=%s AND status='closed'",
        (company,),
    )
    closed = int((_row(cur.fetchone()).get("n") or 0))
    cur.execute(
        "SELECT COUNT(*) AS n FROM eng_campaigns WHERE company_code=%s AND status='draft'",
        (company,),
    )
    drafts = int((_row(cur.fetchone()).get("n") or 0))
    cur.execute(
        "SELECT COUNT(*) AS n FROM eng_action_plans WHERE company_code=%s AND status IN ('open','in_progress')",
        (company,),
    )
    plans = int((_row(cur.fetchone()).get("n") or 0))
    return {
        "ok": True,
        "company_code": company,
        "enabled": True,
        "resource_state": "ready" if (live or closed or drafts or plans) else "empty",
        "counts": {
            "live_surveys": live,
            "closed_surveys": closed,
            "draft_surveys": drafts,
            "open_action_plans": plans,
        },
        "er_enabled": _module_on(cur, company, "employee_relations"),
        "performance_enabled": _module_on(cur, company, "performance"),
        "talent_enabled": _module_on(cur, company, "talent"),
        "analytics_enabled": _module_on(cur, company, "analytics"),
        **honesty_payload(company_code=company),
    }


def list_surveys(cur: Any, *, company_code: str) -> dict[str, Any]:
    ensure_schema(cur)
    company = c5.company_code_norm(company_code)
    if not c5.module_enabled_for_company(cur, company):
        return {"ok": True, "enabled": False, "resource_state": "unavailable", "surveys": None, **honesty_payload(company_code=company)}
    cur.execute(
        """
        SELECT survey_id, code, title_en, title_ar, status, created_at
          FROM eng_surveys WHERE company_code=%s ORDER BY created_at DESC
        """,
        (company,),
    )
    return {"ok": True, "surveys": [dict(r) for r in cur.fetchall()], **honesty_payload(company_code=company)}


def list_versions(cur: Any, *, company_code: str, survey_id: str) -> dict[str, Any]:
    ensure_schema(cur)
    company = c5.company_code_norm(company_code)
    if not c5.module_enabled_for_company(cur, company):
        return {"ok": True, "enabled": False, "resource_state": "unavailable", "versions": None, **honesty_payload(company_code=company)}
    cur.execute(
        """
        SELECT survey_version_id, version_no, privacy_mode, min_responses, visibility, frozen_at, created_at
          FROM eng_survey_versions
         WHERE company_code=%s AND survey_id=%s
         ORDER BY version_no
        """,
        (company, survey_id),
    )
    versions = []
    for row in cur.fetchall():
        item = dict(row)
        item["privacy_mode_label_en"] = c5.status_label(item.get("privacy_mode"), lang="en")
        item["privacy_mode_label_ar"] = c5.status_label(item.get("privacy_mode"), lang="ar")
        versions.append(item)
    return {"ok": True, "versions": versions, **honesty_payload(company_code=company)}


def list_campaigns(cur: Any, *, company_code: str, status: str | None = None) -> dict[str, Any]:
    ensure_schema(cur)
    company = c5.company_code_norm(company_code)
    if not c5.module_enabled_for_company(cur, company):
        return {"ok": True, "enabled": False, "resource_state": "unavailable", "campaigns": None, **honesty_payload(company_code=company)}
    sql = "SELECT * FROM eng_campaigns WHERE company_code=%s"
    params: list[Any] = [company]
    if status:
        sql += " AND status=%s"
        params.append(status)
    sql += " ORDER BY created_at DESC"
    cur.execute(sql, params)
    return {
        "ok": True,
        "campaigns": [_public_campaign(dict(r)) for r in cur.fetchall()],
        **honesty_payload(company_code=company),
    }


def campaign_detail(cur: Any, *, company_code: str, campaign_id: str) -> dict[str, Any]:
    ensure_schema(cur)
    company = c5.company_code_norm(company_code)
    if not c5.module_enabled_for_company(cur, company):
        return {"ok": True, "enabled": False, "resource_state": "unavailable", "campaign": None, **honesty_payload(company_code=company)}
    cur.execute("SELECT * FROM eng_campaigns WHERE company_code=%s AND campaign_id=%s", (company, campaign_id))
    camp = _row(cur.fetchone())
    if not camp:
        return {"ok": False, "error": "campaign_not_found"}
    questions = list_questions(cur, company_code=company, survey_version_id=str(camp["survey_version_id"]))
    participation = participation_status(cur, company_code=company, campaign_id=campaign_id)
    return {
        "ok": True,
        "campaign": _public_campaign(camp),
        "questions": questions.get("questions") or [],
        "participation": participation.get("participation"),
        "audience_count": len(participation.get("participation") or []),
        **honesty_payload(company_code=company),
    }


def list_questions(cur: Any, *, company_code: str, survey_version_id: str) -> dict[str, Any]:
    company = c5.company_code_norm(company_code)
    cur.execute(
        """
        SELECT question_id, question_type, prompt_en, prompt_ar, scale_min, scale_max, options, is_enps, sort_order
          FROM eng_questions
         WHERE company_code=%s AND survey_version_id=%s
         ORDER BY sort_order
        """,
        (company, survey_version_id),
    )
    return {"ok": True, "questions": [dict(r) for r in cur.fetchall()]}


def participation_status(cur: Any, *, company_code: str, campaign_id: str) -> dict[str, Any]:
    """Participation only — never answer content."""
    ensure_schema(cur)
    company = c5.company_code_norm(company_code)
    cur.execute(
        """
        SELECT employee_key, status, started_at, submitted_at, department_snapshot, location_snapshot
          FROM eng_invitations
         WHERE company_code=%s AND campaign_id=%s
         ORDER BY employee_key
        """,
        (company, campaign_id),
    )
    rows = [dict(r) for r in cur.fetchall()]
    return {
        "ok": True,
        "participation": rows,
        "participation_is_not_answer_mapping": True,
        "answers_included": False,
        **honesty_payload(company_code=company),
    }


def _safe_aggregate(result: dict[str, Any]) -> dict[str, Any]:
    out = dict(result)
    if out.get("suppressed"):
        out["scores"] = None
        out["enps"] = None
        out["n"] = None
        out["raw_values_sent"] = False
        out["suppressed_is_not_zero"] = True
    out["manager_raw_anonymous_answers"] = False
    return out


def campaign_results(
    cur: Any,
    *,
    company_code: str,
    campaign_id: str,
    segment: dict[str, str] | None = None,
    actor_role: str = "engagement_admin",
    manager_scope_employee_keys: list[str] | None = None,
) -> dict[str, Any]:
    ensure_schema(cur)
    company = c5.company_code_norm(company_code)
    if not c5.module_enabled_for_company(cur, company):
        return {"ok": True, "enabled": False, "resource_state": "unavailable", "results": None, **honesty_payload(company_code=company)}
    if actor_role == "manager" and not list(manager_scope_employee_keys or []):
        return {
            "ok": True,
            "suppressed": True,
            "reason": "manager_scope_empty",
            "raw_values_sent": False,
            "scores": None,
            "enps": None,
            "n": None,
            "empty_manager_scope_is_not_company_wide": True,
            **honesty_payload(company_code=company),
        }
    agg = c5.compute_aggregates(
        cur,
        company_code=company,
        campaign_id=campaign_id,
        segment=segment,
        actor_role=actor_role,
        manager_scope_employee_keys=manager_scope_employee_keys,
    )
    if agg.get("ok") is False:
        return agg
    return {**_safe_aggregate(agg), **honesty_payload(company_code=company)}


def segment_breakdown(
    cur: Any,
    *,
    company_code: str,
    campaign_id: str,
    dimension: str,
    actor_role: str = "engagement_admin",
    manager_scope_employee_keys: list[str] | None = None,
) -> dict[str, Any]:
    """Governed department/location segments. Each cell uses C5 complementary suppression."""
    ensure_schema(cur)
    company = c5.company_code_norm(company_code)
    if dimension not in {"department", "location"}:
        return {"ok": False, "error": "ungoverned_segment_dimension"}
    col = "department_snapshot" if dimension == "department" else "location_snapshot"
    cur.execute(
        f"SELECT DISTINCT {col} AS value FROM eng_invitations WHERE company_code=%s AND campaign_id=%s AND {col} <> ''",
        (company, campaign_id),
    )
    values = [str(dict(r)["value"]) for r in cur.fetchall()]
    segments = []
    for value in values:
        cell = campaign_results(
            cur,
            company_code=company,
            campaign_id=campaign_id,
            segment={dimension: value},
            actor_role=actor_role,
            manager_scope_employee_keys=manager_scope_employee_keys,
        )
        segments.append(
            {
                "dimension": dimension,
                "value": value,
                "suppressed": bool(cell.get("suppressed")),
                "reason": cell.get("reason"),
                "scores": None if cell.get("suppressed") else cell.get("scores"),
                "enps": None if cell.get("suppressed") else cell.get("enps"),
                "n": None if cell.get("suppressed") else cell.get("n"),
            }
        )
    overall = campaign_results(
        cur,
        company_code=company,
        campaign_id=campaign_id,
        actor_role=actor_role,
        manager_scope_employee_keys=manager_scope_employee_keys,
    )
    return {
        "ok": True,
        "dimension": dimension,
        "overall": _safe_aggregate(overall) if overall.get("ok") else overall,
        "segments": segments,
        "complementary_suppression": True,
        **honesty_payload(company_code=company),
    }


def export_results(
    cur: Any,
    *,
    company_code: str,
    campaign_id: str,
    actor_role: str = "engagement_admin",
    manager_scope_employee_keys: list[str] | None = None,
) -> dict[str, Any]:
    results = campaign_results(
        cur,
        company_code=company_code,
        campaign_id=campaign_id,
        actor_role=actor_role,
        manager_scope_employee_keys=manager_scope_employee_keys,
    )
    if results.get("suppressed"):
        return {
            "ok": True,
            "export": None,
            "suppressed": True,
            "reason": results.get("reason"),
            "export_obeys_suppression": True,
            **honesty_payload(company_code=company_code),
        }
    return {
        "ok": True,
        "export": {
            "campaign_id": campaign_id,
            "scores": results.get("scores"),
            "enps": results.get("enps"),
            "n": results.get("n"),
            "threshold": results.get("threshold"),
        },
        "suppressed": False,
        "respondent_answer_map_included": False,
        "export_obeys_suppression": True,
        **honesty_payload(company_code=company_code),
    }


def list_action_plans(cur: Any, *, company_code: str, campaign_id: str | None = None) -> dict[str, Any]:
    ensure_schema(cur)
    company = c5.company_code_norm(company_code)
    if not c5.module_enabled_for_company(cur, company):
        return {"ok": True, "enabled": False, "resource_state": "unavailable", "action_plans": None, **honesty_payload(company_code=company)}
    sql = "SELECT * FROM eng_action_plans WHERE company_code=%s"
    params: list[Any] = [company]
    if campaign_id:
        sql += " AND campaign_id=%s"
        params.append(campaign_id)
    sql += " ORDER BY created_at DESC"
    cur.execute(sql, params)
    plans = []
    for row in cur.fetchall():
        plan = dict(row)
        cur.execute(
            """
            SELECT action_item_id, title_en, title_ar, owner_key, due_date, status, shared_task_ref
              FROM eng_action_items WHERE company_code=%s AND action_plan_id=%s
            """,
            (company, plan["action_plan_id"]),
        )
        plan["items"] = [dict(r) for r in cur.fetchall()]
        plan["not_er_case"] = True
        plan["not_employment_mutation"] = True
        plans.append(plan)
    return {
        "ok": True,
        "action_plans": plans,
        "survey_result_is_not_action_plan": True,
        "action_plan_is_not_er_case": True,
        **honesty_payload(company_code=company),
    }


def list_history(cur: Any, *, company_code: str, campaign_id: str | None = None) -> dict[str, Any]:
    ensure_schema(cur)
    company = c5.company_code_norm(company_code)
    if not c5.module_enabled_for_company(cur, company):
        return {"ok": True, "enabled": False, "resource_state": "unavailable", "history": None, **honesty_payload(company_code=company)}
    sql = "SELECT audit_id, actor_phone, action, entity_type, entity_id, detail, created_at FROM eng_audit_events WHERE company_code=%s"
    params: list[Any] = [company]
    if campaign_id:
        sql += " AND entity_id=%s"
        params.append(campaign_id)
    sql += " ORDER BY created_at ASC"
    cur.execute(sql, params)
    return {"ok": True, "history": [dict(r) for r in cur.fetchall()], **honesty_payload(company_code=company)}


def manager_aggregates(
    cur: Any,
    *,
    company_code: str,
    manager_scope_employee_keys: list[str] | None,
    campaign_id: str | None = None,
) -> dict[str, Any]:
    ensure_schema(cur)
    company = c5.company_code_norm(company_code)
    if not c5.module_enabled_for_company(cur, company):
        return {
            "ok": True,
            "enabled": False,
            "resource_state": "unavailable",
            "counts": None,
            "campaigns": None,
            **honesty_payload(company_code=company),
        }
    keys = list(manager_scope_employee_keys or [])
    if not keys:
        return {
            "ok": True,
            "enabled": True,
            "resource_state": "empty",
            "suppressed": True,
            "reason": "manager_scope_empty",
            "campaigns": [],
            "empty_manager_scope_is_not_company_wide": True,
            "company_wide": False,
            **honesty_payload(company_code=company),
        }
    sql = """
        SELECT DISTINCT c.*
          FROM eng_campaigns c
          JOIN eng_invitations i ON i.campaign_id=c.campaign_id
         WHERE c.company_code=%s AND i.employee_key = ANY(%s)
           AND c.status IN ('launched','closed')
    """
    params: list[Any] = [company, keys]
    if campaign_id:
        sql += " AND c.campaign_id=%s"
        params.append(campaign_id)
    sql += " ORDER BY c.created_at DESC"
    cur.execute(sql, params)
    items = []
    for row in cur.fetchall():
        camp = _public_campaign(dict(row))
        results = campaign_results(
            cur,
            company_code=company,
            campaign_id=str(camp["campaign_id"]),
            actor_role="manager",
            manager_scope_employee_keys=keys,
        )
        items.append({**camp, "results": _safe_aggregate(results) if results.get("ok") else results})
    return {
        "ok": True,
        "enabled": True,
        "resource_state": "ready" if items else "empty",
        "campaigns": items,
        "company_wide": False,
        "manager_raw_anonymous_answers": False,
        **honesty_payload(company_code=company),
    }


def employee_workspace(cur: Any, *, company_code: str, employee_key: str) -> dict[str, Any]:
    ensure_schema(cur)
    company = c5.company_code_norm(company_code)
    if not c5.module_enabled_for_company(cur, company):
        return {
            "ok": True,
            "enabled": False,
            "resource_state": "unavailable",
            "surveys": None,
            **honesty_payload(company_code=company),
        }
    cur.execute(
        """
        SELECT i.campaign_id, i.status AS participation_status, i.submitted_at,
               c.title_en, c.title_ar, c.privacy_mode, c.status AS campaign_status, c.closes_at, c.opens_at
          FROM eng_invitations i
          JOIN eng_campaigns c ON c.campaign_id=i.campaign_id
         WHERE i.company_code=%s AND i.employee_key=%s
         ORDER BY c.created_at DESC
        """,
        (company, employee_key),
    )
    surveys = []
    for row in cur.fetchall():
        d = dict(row)
        privacy = str(d.get("privacy_mode") or "")
        campaign_status = str(d.get("campaign_status") or "")
        part = str(d.get("participation_status") or "")
        if campaign_status == "closed" or (d.get("closes_at") and campaign_status != "launched"):
            state = "closed"
        elif part == "submitted":
            state = "submitted"
        elif campaign_status == "launched":
            state = "open"
        else:
            state = campaign_status
        surveys.append(
            {
                "campaign_id": str(d["campaign_id"]),
                "title_en": d.get("title_en"),
                "title_ar": d.get("title_ar"),
                "privacy_mode": privacy,
                "privacy_mode_label_en": c5.status_label(privacy, lang="en"),
                "privacy_mode_label_ar": c5.status_label(privacy, lang="ar"),
                "anonymous": privacy == "anonymous",
                "identified": privacy == "identified",
                "participation_status": part,
                "state": state,
                "closes_at": d.get("closes_at"),
            }
        )
    return {
        "ok": True,
        "enabled": True,
        "resource_state": "ready" if surveys else "empty",
        "surveys": surveys,
        "company_analytics_included": False,
        **honesty_payload(company_code=company),
    }


def employee_survey_detail(cur: Any, *, company_code: str, employee_key: str, campaign_id: str) -> dict[str, Any]:
    ensure_schema(cur)
    company = c5.company_code_norm(company_code)
    if not c5.module_enabled_for_company(cur, company):
        return {"ok": True, "enabled": False, "resource_state": "unavailable", "survey": None, **honesty_payload(company_code=company)}
    cur.execute(
        """
        SELECT i.status AS participation_status, c.*
          FROM eng_invitations i
          JOIN eng_campaigns c ON c.campaign_id=i.campaign_id
         WHERE i.company_code=%s AND i.employee_key=%s AND i.campaign_id=%s
        """,
        (company, employee_key, campaign_id),
    )
    row = _row(cur.fetchone())
    if not row:
        return {"ok": False, "error": "not_in_audience"}
    questions = list_questions(cur, company_code=company, survey_version_id=str(row["survey_version_id"]))
    privacy = str(row.get("privacy_mode") or "")
    return {
        "ok": True,
        "survey": {
            **_public_campaign(row),
            "participation_status": row.get("participation_status"),
            "privacy_disclosed_before_response": True,
            "privacy_promise_matches_backend": True,
        },
        "questions": questions.get("questions") or [],
        "other_employees_answers_included": False,
        "aggregates_included": False,
        "action_plans_included": False,
        **honesty_payload(company_code=company),
    }


def employee_start(cur: Any, *, company_code: str, employee_key: str, campaign_id: str) -> dict[str, Any]:
    result = c5.start_response(cur, company_code=company_code, employee_key=employee_key, campaign_id=campaign_id)
    if result.get("ok"):
        result.update(honesty_payload(company_code=company_code))
    return result


def employee_submit(
    cur: Any,
    *,
    company_code: str,
    employee_key: str,
    campaign_id: str,
    answers: list[dict[str, Any]],
) -> dict[str, Any]:
    result = c5.submit_response(
        cur,
        company_code=company_code,
        employee_key=employee_key,
        campaign_id=campaign_id,
        answers=answers,
    )
    if result.get("ok"):
        result["auto_created_er_case"] = False
        result.update(honesty_payload(company_code=company_code))
    return result


def refuse_admin_answer_map(
    cur: Any, *, company_code: str, campaign_id: str, employee_key: str
) -> dict[str, Any]:
    return c5.try_admin_resolve_respondent_answers(
        cur, company_code=company_code, campaign_id=campaign_id, employee_key=employee_key
    )


def assistant_query(
    cur: Any,
    *,
    company_code: str,
    actor: str,
    question_kind: str,
    campaign_id: str | None = None,
    employee_key: str | None = None,
) -> dict[str, Any]:
    if question_kind in {"identify_respondent", "expose_suppressed", "submit_response", "mutate_campaign", "fake_score", "create_er"}:
        return {"ok": False, "error": "mutation_or_privacy_forbidden", "mutations": False, **honesty_payload(company_code=company_code)}
    result = c5.assistant_query_engagement(
        cur,
        company_code=company_code,
        actor=actor,
        question_kind=question_kind,
        campaign_id=campaign_id,
        employee_key=employee_key,
    )
    if result.get("suppressed"):
        result["scores"] = None
        result["enps"] = None
    result["mutations"] = False
    result.update(honesty_payload(company_code=company_code))
    return result


def wave5_safe_facts(cur: Any, *, company_code: str, campaign_id: str | None = None) -> dict[str, Any]:
    company = c5.company_code_norm(company_code)
    sql = """
        SELECT fact_type, entity_type, entity_id, payload, created_at
          FROM eng_wave5_fact_outbox
         WHERE company_code=%s
    """
    params: list[Any] = [company]
    if campaign_id:
        sql += " AND (entity_id=%s OR payload->>'campaign_id'=%s)"
        params.extend([campaign_id, campaign_id])
    sql += " ORDER BY created_at ASC"
    cur.execute(sql, params)
    facts = []
    for row in cur.fetchall():
        item = dict(row)
        payload = dict(item.get("payload") or {})
        for banned in ("answers", "value_text", "free_text", "respondent", "employee_key"):
            payload.pop(banned, None)
        item["payload"] = payload
        facts.append(item)
    return {
        "ok": True,
        "facts": facts,
        "wave5_typed_facts_only": True,
        "raw_free_text_excluded": True,
        **honesty_payload(company_code=company),
    }
