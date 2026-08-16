#!/usr/bin/env python3
"""R5C Talent product surfaces — thin composition over frozen Wave 4 C5–C6.

HTTP and clients are adapters. Potential, HiPo, readiness, and 9-box stay
domain-authoritative. This module never invents a master talent_score,
never writes recruiting talent_pool, and never treats Performance as Talent.
"""
from __future__ import annotations

from typing import Any, Iterable, Mapping

import talent_profile_c5 as c5
import talent_succession_c6 as c6

PHASE = "talent_surfaces_r5c"
CONTRACT_VERSION = "talent_surfaces_v1"
PASS_STAMP = "PRODUCTION_READINESS_R5C_TALENT_SURFACE_FULL_PASS"
COMMERCIAL_MODULE_KEY = "talent"
RECRUITING_POOL_KEY = "talent_pool"

EMPLOYEE_FORBIDDEN_KEYS = frozenset(
    {
        "hipo",
        "hi_po",
        "hi-po",
        "potential",
        "succession",
        "readiness",
        "nine_box",
        "9-box",
        "ninebox",
        "talent_score",
        "master_talent_score",
        "box_placement",
        "designations",
        "assessments",
        "nominations",
        "critical_roles",
        "succession_plans",
        "nine_box_projection",
        "confidential_notes",
    }
)


def honesty_payload(*, company_code: str | None = None) -> dict[str, Any]:
    return {
        "phase": PHASE,
        "contract_version": CONTRACT_VERSION,
        "pass_stamp": PASS_STAMP,
        "commercial_module_key": COMMERCIAL_MODULE_KEY,
        "canonical_authority": ("talent_profile_c5", "talent_succession_c6"),
        "recruiting_talent_pool_isolated": True,
        "recruiting_storage_key": RECRUITING_POOL_KEY,
        "no_master_talent_score": True,
        "performance_optional": True,
        "high_performer_is_not_hipo": True,
        "performance_is_not_potential": True,
        "potential_is_not_hipo": True,
        "nine_box_is_projection_not_sot": True,
        "readiness_is_target_specific": True,
        "learning_required": False,
        "job_architecture_required": False,
        "c3_development_remains_canonical": True,
        "mobility_interest_is_not_application": True,
        "silent_candidate_creation": False,
        "company_code": c5.company_code_norm(company_code) if company_code else None,
    }


def strip_employee_judgments(value: Any) -> Any:
    """Remove internal HR judgments from employee-facing payloads."""
    if isinstance(value, Mapping):
        out: dict[str, Any] = {}
        for key, item in value.items():
            if str(key).strip().lower() in EMPLOYEE_FORBIDDEN_KEYS:
                continue
            out[str(key)] = strip_employee_judgments(item)
        return out
    if isinstance(value, list):
        return [strip_employee_judgments(item) for item in value]
    return value


def ensure_all_schemas(cur: Any) -> None:
    c5.ensure_talent_profile_c5_schema(cur)
    c6.ensure_talent_succession_c6_schema(cur)
    try:
        import talent_evidence_index_pt1 as idx

        idx.ensure_talent_evidence_index_pt1_schema(cur)
    except Exception:
        pass
    try:
        import talent_models_pt2 as pt2

        pt2.ensure_talent_models_pt2_schema(cur)
    except Exception:
        pass


def sync_catalog_entitlement(
    cur: Any,
    *,
    company_code: str,
    actor_phone: str,
    enabled: bool,
    reason: str = "sync talent catalog entitlement",
) -> dict[str, Any]:
    ensure_all_schemas(cur)
    company = c5.company_code_norm(company_code)
    if enabled:
        profile = c5.enable_company_talent_profile(
            cur, company_code=company, actor_phone=actor_phone, reason=reason
        )
        succession = c6.enable_company_talent_succession(
            cur, company_code=company, actor_phone=actor_phone, reason=reason
        )
    else:
        profile = c5.disable_company_talent_profile(
            cur, company_code=company, actor_phone=actor_phone, reason=reason
        )
        succession = c6.disable_company_talent_succession(
            cur, company_code=company, actor_phone=actor_phone, reason=reason
        )
    return {
        "ok": True,
        "company_code": company,
        "enabled": bool(enabled),
        "history_preserved": True,
        "profile": profile,
        "succession": succession,
        **honesty_payload(company_code=company),
    }


def _row(value: Any) -> dict[str, Any]:
    return dict(value) if value else {}


def _scope_sql(column: str, scope_keys: Iterable[str] | None) -> tuple[str, list[Any]]:
    keys = [str(k) for k in (scope_keys or []) if str(k).strip()]
    if not keys:
        return "", []
    return f" AND {column} = ANY(%s)", [keys]


def _recruiting_enabled(cur: Any, company: str) -> bool:
    cur.execute(
        """
        SELECT 1 FROM company_modules
         WHERE company_code=%s AND enabled IS TRUE
           AND module_key IN ('pre_hiring', 'recruiting')
         LIMIT 1
        """,
        (company,),
    )
    return bool(cur.fetchone())


def workspace_summary(
    cur: Any,
    *,
    company_code: str,
    actor_role: str,
    manager_scope_keys: list[str] | None = None,
    can_see_sensitive: bool = False,
    can_see_succession: bool = False,
) -> dict[str, Any]:
    ensure_all_schemas(cur)
    company = c5.company_code_norm(company_code)
    role = str(actor_role or "").strip().lower()
    scope = list(manager_scope_keys or []) if role == "manager" else None
    extra, params = _scope_sql("employee_key", scope)
    if role == "manager" and not extra:
        return {
            "ok": True,
            "company_code": company,
            "counts": {
                "profiles": 0,
                "open_reviews": 0,
                "uncovered_roles": 0,
                "hipo_designated": None,
            },
            "readiness_distribution": [],
            "company_wide": False,
            "master_talent_score": None,
            **honesty_payload(company_code=company),
        }

    cur.execute(
        f"SELECT COUNT(*) AS n FROM talent_profiles WHERE company_code=%s {extra}",
        [company, *params],
    )
    profiles = int((_row(cur.fetchone()).get("n") or 0))

    cur.execute(
        """
        SELECT COUNT(*) AS n FROM talent_reviews
         WHERE company_code=%s AND status IN ('draft','prepared','in_review')
        """,
        (company,),
    )
    open_reviews = int((_row(cur.fetchone()).get("n") or 0))

    uncovered = 0
    readiness: list[dict[str, Any]] = []
    if can_see_succession:
        gaps = c6.list_uncovered_critical_roles(cur, company_code=company)
        uncovered = len(gaps.get("uncovered") or [])
        cur.execute(
            """
            SELECT readiness, COUNT(*) AS n
              FROM talent_successor_nominations
             WHERE company_code=%s AND status='active'
             GROUP BY readiness
            """,
            (company,),
        )
        readiness = [_row(r) for r in (cur.fetchall() or [])]

    hipo_n = None
    if can_see_sensitive:
        extra_h, params_h = _scope_sql("employee_key", scope)
        cur.execute(
            f"""
            SELECT COUNT(*) AS n FROM talent_hipo_designations
             WHERE company_code=%s AND status='designated'
               AND superseded_by_designation_id IS NULL {extra_h}
            """,
            [company, *params_h],
        )
        hipo_n = int((_row(cur.fetchone()).get("n") or 0))

    return {
        "ok": True,
        "company_code": company,
        "counts": {
            "profiles": profiles,
            "open_reviews": open_reviews,
            "uncovered_roles": uncovered if can_see_succession else None,
            "hipo_designated": hipo_n,
        },
        "readiness_distribution": readiness,
        "company_wide": role != "manager",
        "master_talent_score": None,
        "performance_visible_as_evidence_only": True,
        **honesty_payload(company_code=company),
    }


def list_profiles(
    cur: Any,
    *,
    company_code: str,
    manager_scope_keys: list[str] | None = None,
    actor_role: str = "hr",
    limit: int = 100,
    offset: int = 0,
) -> dict[str, Any]:
    ensure_all_schemas(cur)
    company = c5.company_code_norm(company_code)
    where = ["company_code=%s"]
    params: list[Any] = [company]
    if actor_role == "manager":
        extra, extra_params = _scope_sql("employee_key", manager_scope_keys)
        if not extra:
            return {"ok": True, "profiles": [], "total": 0, **honesty_payload(company_code=company)}
        where.append(extra.replace(" AND ", "", 1))
        params.extend(extra_params)
    cur.execute(f"SELECT COUNT(*) AS n FROM talent_profiles WHERE {' AND '.join(where)}", params)
    total = int((_row(cur.fetchone()).get("n") or 0))
    cur.execute(
        f"""
        SELECT * FROM talent_profiles
         WHERE {' AND '.join(where)}
         ORDER BY updated_at DESC
         LIMIT %s OFFSET %s
        """,
        [*params, max(1, min(int(limit or 100), 200)), max(0, int(offset or 0))],
    )
    return {
        "ok": True,
        "profiles": [_row(r) for r in (cur.fetchall() or [])],
        "total": total,
        "master_talent_score": None,
        **honesty_payload(company_code=company),
    }


def get_profile_detail(
    cur: Any,
    *,
    company_code: str,
    employee_key: str,
    actor_role: str,
    actor_employee_key: str | None = None,
    manager_scope_keys: list[str] | None = None,
    can_see_sensitive: bool = False,
    can_see_succession: bool = False,
    include_history: bool = False,
) -> dict[str, Any]:
    ensure_all_schemas(cur)
    company = c5.company_code_norm(company_code)
    key = str(employee_key or "").strip()
    if actor_role == "employee" and actor_employee_key and key != str(actor_employee_key):
        return {"ok": False, "error": "profile_not_found"}
    if actor_role == "manager" and manager_scope_keys is not None and key not in {str(k) for k in manager_scope_keys}:
        return {"ok": False, "error": "profile_not_found"}
    profile = c5.get_talent_profile(cur, company_code=company, employee_key=key)
    if not profile:
        return {"ok": False, "error": "profile_not_found"}
    facts = c5.list_dimension_facts(
        cur,
        company_code=company,
        employee_key=key,
        include_history=include_history,
        viewer_role=actor_role,
        has_sensitive_permission=can_see_sensitive,
    )
    cur.execute(
        """
        SELECT skill_id, skill_code, name_en, name_ar, state, proficiency_level, version, status
          FROM talent_skills
         WHERE company_code=%s AND employee_key=%s AND status='active'
         ORDER BY skill_code
        """,
        (company, key),
    )
    skills = [_row(r) for r in (cur.fetchall() or [])]
    payload: dict[str, Any] = {
        "ok": True,
        "profile": profile,
        "facts": facts.get("facts") or [],
        "skills": skills,
        "master_talent_score": None,
        "dimensions_collapsed": False,
        **honesty_payload(company_code=company),
    }
    if actor_role == "employee":
        return strip_employee_judgments(payload)
    if can_see_sensitive:
        pot = c5.get_potential_for_viewer(
            cur,
            company_code=company,
            employee_key=key,
            viewer_role=actor_role,
            has_sensitive_permission=True,
        )
        hipo = c6.get_hipo_for_viewer(
            cur,
            company_code=company,
            employee_key=key,
            viewer_role=actor_role,
            has_sensitive_permission=True,
        )
        payload["potential"] = pot
        payload["hipo"] = hipo
        cur.execute(
            """
            SELECT * FROM talent_performance_evidence_links
             WHERE company_code=%s AND employee_key=%s
             ORDER BY created_at DESC
            """,
            (company, key),
        )
        payload["performance_evidence"] = [_row(r) for r in (cur.fetchall() or [])]
        payload["performance_is_not_potential"] = True
        payload["high_performer_is_not_hipo"] = True
        try:
            import talent_evidence_index_pt1 as idx

            indexed = idx.list_evidence(
                cur,
                company_code=company,
                employee_key=key,
                actor_role=actor_role,
                has_talent_read=True,
                can_see_sensitive=can_see_sensitive,
                can_see_performance=True,
            )
            payload["evidence_index"] = indexed.get("evidence") or []
            payload["okr_is_not_potential"] = True
            payload["okr_is_not_hipo"] = True
        except Exception:
            payload["evidence_index"] = []
        try:
            import talent_models_pt2 as pt2

            listed = pt2.list_classifications(cur, company_code=company)
            mine = [c for c in (listed.get("classifications") or []) if str(c.get("employee_key")) == key]
            payload["derived_classifications"] = mine
            payload["derived_signal_is_not_designated_hipo"] = True
            if mine:
                why = pt2.get_why(cur, company_code=company, why_id=str(mine[0].get("why_id") or ""))
                payload["why"] = why.get("why") if why.get("ok") else None
        except Exception:
            payload["derived_classifications"] = []
    if can_see_succession:
        payload["target_roles"] = c6.talent_map_queries(
            cur, company_code=company, employee_key=key
        ).get("employee_to_target_roles") or []
    return payload


def list_reviews(
    cur: Any,
    *,
    company_code: str,
    limit: int = 50,
) -> dict[str, Any]:
    ensure_all_schemas(cur)
    company = c5.company_code_norm(company_code)
    cur.execute(
        """
        SELECT review_id, name_en, name_ar, status, facilitator_phone, population_frozen_at,
               nine_box_enabled_snapshot, row_version, created_at, updated_at
          FROM talent_reviews
         WHERE company_code=%s
         ORDER BY updated_at DESC
         LIMIT %s
        """,
        (company, max(1, min(int(limit or 50), 100))),
    )
    return {
        "ok": True,
        "reviews": [_row(r) for r in (cur.fetchall() or [])],
        **honesty_payload(company_code=company),
    }


def get_review_detail(
    cur: Any,
    *,
    company_code: str,
    review_id: str,
) -> dict[str, Any]:
    ensure_all_schemas(cur)
    company = c5.company_code_norm(company_code)
    cur.execute(
        "SELECT * FROM talent_reviews WHERE company_code=%s AND review_id=%s",
        (company, review_id),
    )
    review = cur.fetchone()
    if not review:
        return {"ok": False, "error": "talent_review_not_found"}
    review = _row(review)
    cur.execute(
        """
        SELECT * FROM talent_review_population
         WHERE company_code=%s AND review_id=%s
         ORDER BY employee_key
        """,
        (company, review_id),
    )
    population = [_row(r) for r in (cur.fetchall() or [])]
    return {
        "ok": True,
        "review": review,
        "population": population,
        "snapshot_frozen": bool(review.get("snapshot")),
        **honesty_payload(company_code=company),
    }


def list_succession(
    cur: Any,
    *,
    company_code: str,
) -> dict[str, Any]:
    ensure_all_schemas(cur)
    company = c5.company_code_norm(company_code)
    cur.execute(
        """
        SELECT * FROM talent_critical_roles
         WHERE company_code=%s AND status='active'
         ORDER BY title_en
        """,
        (company,),
    )
    roles = [_row(r) for r in (cur.fetchall() or [])]
    cur.execute(
        """
        SELECT p.*, cr.canonical_role_key, cr.title_en, cr.title_ar
          FROM talent_succession_plans p
          JOIN talent_critical_roles cr ON cr.critical_role_id=p.critical_role_id
         WHERE p.company_code=%s
         ORDER BY p.updated_at DESC
        """,
        (company,),
    )
    plans = [_row(r) for r in (cur.fetchall() or [])]
    gaps = c6.list_uncovered_critical_roles(cur, company_code=company)
    return {
        "ok": True,
        "critical_roles": roles,
        "plans": plans,
        "uncovered": gaps.get("uncovered") or [],
        "global_readiness_score": None,
        **honesty_payload(company_code=company),
    }


def get_slate(
    cur: Any,
    *,
    company_code: str,
    plan_id: str,
) -> dict[str, Any]:
    ensure_all_schemas(cur)
    company = c5.company_code_norm(company_code)
    cur.execute(
        "SELECT * FROM talent_succession_plans WHERE company_code=%s AND plan_id=%s",
        (company, plan_id),
    )
    plan = cur.fetchone()
    if not plan:
        return {"ok": False, "error": "succession_plan_not_found"}
    plan = _row(plan)
    cur.execute(
        """
        SELECT * FROM talent_successor_nominations
         WHERE company_code=%s AND plan_id=%s
         ORDER BY created_at
        """,
        (company, plan_id),
    )
    nominations = [_row(r) for r in (cur.fetchall() or [])]
    return {
        "ok": True,
        "plan": plan,
        "nominations": nominations,
        "multi_successor": True,
        "global_readiness_score": None,
        **honesty_payload(company_code=company),
    }


def list_nine_box_configs(cur: Any, *, company_code: str) -> dict[str, Any]:
    ensure_all_schemas(cur)
    company = c5.company_code_norm(company_code)
    settings = c6.get_company_settings(cur, company) or {}
    if not settings.get("nine_box_enabled"):
        return {
            "ok": True,
            "enabled": False,
            "configs": [],
            "is_canonical_employee_state": False,
            **honesty_payload(company_code=company),
        }
    cur.execute(
        "SELECT * FROM talent_nine_box_configs WHERE company_code=%s ORDER BY created_at DESC",
        (company,),
    )
    return {
        "ok": True,
        "enabled": True,
        "configs": [_row(r) for r in (cur.fetchall() or [])],
        "is_canonical_employee_state": False,
        **honesty_payload(company_code=company),
    }


def derive_nine_box(
    cur: Any,
    *,
    company_code: str,
    config_id: str,
    performance_value: Any,
    potential_level: str | None,
) -> dict[str, Any]:
    ensure_all_schemas(cur)
    company = c5.company_code_norm(company_code)
    settings = c6.get_company_settings(cur, company) or {}
    if not settings.get("nine_box_enabled"):
        return {
            "ok": True,
            "available": False,
            "cell": None,
            "reason": "nine_box_disabled",
            "is_canonical_employee_state": False,
            "does_not_imply_hipo": True,
            **honesty_payload(company_code=company),
        }
    cur.execute(
        "SELECT * FROM talent_nine_box_configs WHERE company_code=%s AND config_id=%s",
        (company, config_id),
    )
    cfg = cur.fetchone()
    if not cfg:
        return {"ok": False, "error": "nine_box_config_not_found"}
    proj = c6.project_nine_box(
        config=_row(cfg),
        performance_value=performance_value,
        potential_level=potential_level,
    )
    return {**proj, **honesty_payload(company_code=company)}


def mobility_surface(
    cur: Any,
    *,
    company_code: str,
    employee_key: str,
    actor_role: str,
    can_see_sensitive: bool = False,
) -> dict[str, Any]:
    ensure_all_schemas(cur)
    company = c5.company_code_norm(company_code)
    facts = c5.list_dimension_facts(
        cur,
        company_code=company,
        employee_key=employee_key,
        dimension_kind="mobility_preference",
        viewer_role=actor_role,
        has_sensitive_permission=can_see_sensitive,
    )
    recruiting_on = _recruiting_enabled(cur, company)
    payload = {
        "ok": True,
        "preferences": facts.get("facts") or [],
        "interest_is_not_application": True,
        "application_is_not_selection": True,
        "selection_is_not_employment_change": True,
        "silent_candidate_creation": False,
        "writes_talent_pool": False,
        "recruiting_enabled": recruiting_on,
        "handoff_available": recruiting_on,
        "handoff": (
            {
                "kind": "explicit_internal_opportunity",
                "module": "pre_hiring",
                "writes_talent_pool": False,
            }
            if recruiting_on
            else None
        ),
        **honesty_payload(company_code=company),
    }
    if actor_role == "employee":
        return strip_employee_judgments(payload)
    return payload


def development_context(
    cur: Any,
    *,
    company_code: str,
    employee_key: str,
) -> dict[str, Any]:
    """Reuse C3 development truth. Do not create a second plan authority."""
    company = c5.company_code_norm(company_code)
    items: list[dict[str, Any]] = []
    try:
        import performance_feedback_c3 as c3

        c3.ensure_performance_feedback_c3_schema(cur)
        cur.execute(
            """
            SELECT p.plan_id, p.employee_key, p.title_en, a.action_id,
                   a.title_en AS action_title_en, a.status AS action_status
              FROM perf_development_plans p
              LEFT JOIN perf_development_actions a ON a.plan_id=p.plan_id
             WHERE p.company_code=%s AND p.employee_key=%s
             ORDER BY p.updated_at DESC
             LIMIT 50
            """,
            (company, employee_key),
        )
        items = [_row(r) for r in (cur.fetchall() or [])]
    except Exception:
        items = []
    return {
        "ok": True,
        "items": items,
        "reused_c3_authority": True,
        "learning_required": False,
        "learning_completion_is_not_development_completion": True,
        **honesty_payload(company_code=company),
    }


def employee_workspace(
    cur: Any,
    *,
    company_code: str,
    employee_key: str,
) -> dict[str, Any]:
    ensure_all_schemas(cur)
    company = c5.company_code_norm(company_code)
    ensure = c5.ensure_talent_profile(
        cur, company_code=company, employee_key=employee_key
    )
    if not ensure.get("ok"):
        return ensure
    facts = c5.list_dimension_facts(
        cur,
        company_code=company,
        employee_key=employee_key,
        viewer_role="employee",
        has_sensitive_permission=False,
    )
    cur.execute(
        """
        SELECT skill_id, skill_code, name_en, name_ar, state, proficiency_level
          FROM talent_skills
         WHERE company_code=%s AND employee_key=%s AND status='active'
         ORDER BY skill_code
        """,
        (company, employee_key),
    )
    skills = [_row(r) for r in (cur.fetchall() or [])]
    mobility = mobility_surface(
        cur,
        company_code=company,
        employee_key=employee_key,
        actor_role="employee",
    )
    development = development_context(cur, company_code=company, employee_key=employee_key)
    return strip_employee_judgments(
        {
            "ok": True,
            "employee_key": employee_key,
            "profile": ensure.get("profile"),
            "facts": facts.get("facts") or [],
            "skills": skills,
            "mobility": mobility,
            "development": development.get("items") or [],
            "potential_hidden": True,
            "hipo_hidden": True,
            "succession_hidden": True,
            "nine_box_hidden": True,
            "master_talent_score": None,
            **honesty_payload(company_code=company),
        }
    )


def list_potential_frameworks(cur: Any, *, company_code: str) -> dict[str, Any]:
    ensure_all_schemas(cur)
    company = c5.company_code_norm(company_code)
    cur.execute(
        "SELECT * FROM talent_potential_frameworks WHERE company_code=%s ORDER BY created_at DESC",
        (company,),
    )
    return {
        "ok": True,
        "frameworks": [_row(r) for r in (cur.fetchall() or [])],
        **honesty_payload(company_code=company),
    }
