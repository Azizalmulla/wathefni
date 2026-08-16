#!/usr/bin/env python3
"""R5B Performance product surfaces — thin composition over frozen Wave 4 C1–C4.

HTTP and clients are adapters. Progress, rollup, review status, and final rating
come from domain authority. This module never invents Talent/HiPo/9-box state.
"""
from __future__ import annotations

from typing import Any, Iterable, Mapping

import performance_calibration_c4 as c4
import performance_feedback_c3 as c3
import performance_goals_c1 as c1
import performance_reviews_c2 as c2

PHASE = "performance_surfaces_r5b"
CONTRACT_VERSION = "performance_surfaces_v1"
PASS_STAMP = "PRODUCTION_READINESS_R5B_PERFORMANCE_SURFACE_FULL_PASS"
COMMERCIAL_MODULE_KEY = "performance"

TALENT_FORBIDDEN_KEYS = frozenset(
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
        "talent_box",
        "box_placement",
        "master_talent_score",
    }
)

ANON_360_ROLES = frozenset({"peer", "subordinate", "stakeholder"})


def honesty_payload(*, company_code: str | None = None) -> dict[str, Any]:
    return {
        "phase": PHASE,
        "contract_version": CONTRACT_VERSION,
        "pass_stamp": PASS_STAMP,
        "commercial_module_key": COMMERCIAL_MODULE_KEY,
        "canonical_authority": ("goals_c1", "reviews_c2", "feedback_c3", "calibration_c4"),
        "frontend_formulas_forbidden": True,
        "talent_required": False,
        "learning_required": False,
        "high_performer_is_not_hipo": True,
        "ratings_not_collapsed": True,
        "company_code": c1.company_code_norm(company_code) if company_code else None,
    }


def strip_talent(value: Any) -> Any:
    """Remove Talent vocabulary if a caller accidentally attached it."""
    if isinstance(value, Mapping):
        out: dict[str, Any] = {}
        for key, item in value.items():
            if str(key).strip().lower() in TALENT_FORBIDDEN_KEYS:
                continue
            out[str(key)] = strip_talent(item)
        return out
    if isinstance(value, list):
        return [strip_talent(item) for item in value]
    return value


def ensure_all_schemas(cur: Any) -> None:
    c1.ensure_performance_goals_c1_schema(cur)
    c2.ensure_performance_reviews_c2_schema(cur)
    c3.ensure_performance_feedback_c3_schema(cur)
    c4.ensure_performance_calibration_c4_schema(cur)
    try:
        import okr_operating_pt1 as pt1

        pt1.ensure_okr_operating_pt1_schema(cur)
    except Exception:
        pass


def sync_catalog_entitlement(
    cur: Any,
    *,
    company_code: str,
    actor_phone: str,
    enabled: bool,
    reason: str = "sync performance catalog entitlement",
) -> dict[str, Any]:
    """Enable/disable C1–C4 company settings when the catalog SKU changes.

    History rows are never deleted. Disable preserves configuration.
    """
    ensure_all_schemas(cur)
    company = c1.company_code_norm(company_code)
    if enabled:
        goals = c1.enable_company_performance_goals(
            cur, company_code=company, actor_phone=actor_phone, reason=reason
        )
        reviews = c2.enable_company_performance_reviews(
            cur, company_code=company, actor_phone=actor_phone, reason=reason
        )
        feedback = c3.enable_company_performance_feedback(
            cur, company_code=company, actor_phone=actor_phone, reason=reason
        )
        calibration = c4.enable_company_performance_calibration(
            cur, company_code=company, actor_phone=actor_phone, reason=reason
        )
    else:
        goals = c1.disable_company_performance_goals(
            cur, company_code=company, actor_phone=actor_phone, reason=reason
        )
        reviews = c2.disable_company_performance_reviews(
            cur, company_code=company, actor_phone=actor_phone, reason=reason
        )
        feedback = c3.disable_company_performance_feedback(
            cur, company_code=company, actor_phone=actor_phone, reason=reason
        )
        calibration = c4.disable_company_performance_calibration(
            cur, company_code=company, actor_phone=actor_phone, reason=reason
        )
    return strip_talent(
        {
            "ok": True,
            "company_code": company,
            "enabled": bool(enabled),
            "history_preserved": True,
            "goals": goals,
            "reviews": reviews,
            "feedback": feedback,
            "calibration": calibration,
            **honesty_payload(company_code=company),
        }
    )


def _scope_sql(column: str, scope_keys: Iterable[str] | None) -> tuple[str, list[Any]]:
    keys = [str(k) for k in (scope_keys or []) if str(k).strip()]
    if not keys:
        return "", []
    return f" AND {column} = ANY(%s)", [keys]


def _row(value: Any) -> dict[str, Any]:
    return dict(value) if value else {}


def workspace_summary(
    cur: Any,
    *,
    company_code: str,
    actor_role: str,
    manager_scope_keys: list[str] | None = None,
    actor_employee_key: str | None = None,
) -> dict[str, Any]:
    ensure_all_schemas(cur)
    company = c1.company_code_norm(company_code)
    role = str(actor_role or "").strip().lower()
    scope = list(manager_scope_keys or []) if role == "manager" else None
    extra, params = _scope_sql("owner_employee_key", scope)

    cur.execute(
        f"""
        SELECT COUNT(*) AS n FROM perf_objectives
         WHERE company_code=%s AND status IN ('draft','active') {extra}
        """,
        [company, *params],
    )
    objectives_open = int((_row(cur.fetchone()).get("n") or 0))

    extra_c, params_c = _scope_sql("p.employee_key", scope)
    cur.execute(
        f"""
        SELECT COUNT(*) AS n
          FROM perf_review_cycles c
         WHERE c.company_code=%s AND c.status IN ('launched','in_progress','calibration_ready')
        """,
        (company,),
    )
    active_cycles = int((_row(cur.fetchone()).get("n") or 0))

    cur.execute(
        f"""
        SELECT COUNT(*) AS n
          FROM perf_reviews r
          JOIN perf_cycle_participants p
            ON p.cycle_id=r.cycle_id AND p.employee_key=r.subject_employee_key
         WHERE r.company_code=%s AND r.status IN ('not_started','draft')
           AND r.reviewer_role='manager' {extra_c}
        """,
        [company, *params_c],
    )
    manager_pending = int((_row(cur.fetchone()).get("n") or 0))

    cur.execute(
        f"""
        SELECT COUNT(*) AS n
          FROM perf_reviews r
         WHERE r.company_code=%s AND r.status IN ('not_started','draft')
           AND r.reviewer_role='self'
           {"AND r.subject_employee_key=%s" if actor_employee_key else ""}
        """,
        [company] + ([actor_employee_key] if actor_employee_key else []),
    )
    self_pending = int((_row(cur.fetchone()).get("n") or 0))

    extra_d, params_d = _scope_sql("employee_key", scope)
    cur.execute(
        f"""
        SELECT COUNT(*) AS n FROM perf_check_ins
         WHERE company_code=%s AND status IN ('scheduled','open','submitted') {extra_d}
        """,
        [company, *params_d],
    )
    open_check_ins = int((_row(cur.fetchone()).get("n") or 0))

    cur.execute(
        f"""
        SELECT COUNT(*) AS n FROM perf_development_actions a
          JOIN perf_development_plans p ON p.plan_id=a.plan_id
         WHERE a.company_code=%s AND a.status IN ('proposed','accepted','in_progress')
           {("AND p.employee_key = ANY(%s)" if scope else "")}
        """,
        [company] + ([scope] if scope else []),
    )
    open_dev = int((_row(cur.fetchone()).get("n") or 0))

    cur.execute(
        """
        SELECT cycle_id, name_en, name_ar, status, period_start, period_end,
               due_self, due_manager, due_360
          FROM perf_review_cycles
         WHERE company_code=%s AND status IN ('launched','in_progress','calibration_ready')
         ORDER BY launched_at DESC NULLS LAST, created_at DESC
         LIMIT 1
        """,
        (company,),
    )
    active_cycle = _row(cur.fetchone()) or None

    extra_o, params_o = _scope_sql("r.subject_employee_key", scope)
    cur.execute(
        f"""
        SELECT COUNT(*) AS n
          FROM perf_reviews r
          JOIN perf_review_cycles c ON c.cycle_id=r.cycle_id
         WHERE r.company_code=%s AND r.status IN ('not_started','draft')
           AND (
             (r.reviewer_role='self' AND c.due_self IS NOT NULL AND c.due_self < CURRENT_DATE)
             OR (r.reviewer_role='manager' AND c.due_manager IS NOT NULL AND c.due_manager < CURRENT_DATE)
             OR (r.reviewer_role IN ('peer','subordinate','stakeholder')
                 AND c.due_360 IS NOT NULL AND c.due_360 < CURRENT_DATE)
           )
           {extra_o}
        """,
        [company, *params_o],
    )
    overdue_reviews = int((_row(cur.fetchone()).get("n") or 0))

    vis_goals = c1.feature_visibility(cur, company)
    vis_reviews = c2.feature_visibility(cur, company)
    active_okr_cycle = None
    try:
        import okr_operating_pt1 as pt1

        active_okr_cycle = (pt1.current_okr_cycle(cur, company_code=company) or {}).get("cycle")
    except Exception:
        active_okr_cycle = None
    return strip_talent(
        {
            "ok": True,
            "company_code": company,
            "active_cycle": active_cycle,
            "active_okr_cycle": active_okr_cycle,
            "okr_cycle_is_not_review_cycle": True,
            "counts": {
                "objectives_open": objectives_open,
                "active_cycles": active_cycles,
                "manager_reviews_pending": manager_pending,
                "self_reviews_pending": self_pending,
                "open_check_ins": open_check_ins,
                "open_development_actions": open_dev,
                "overdue_reviews": overdue_reviews,
            },
            "upcoming": {
                "due_self": (active_cycle or {}).get("due_self"),
                "due_manager": (active_cycle or {}).get("due_manager"),
                "due_360": (active_cycle or {}).get("due_360"),
            },
            "visibility": {
                "okrs": vis_goals.get("okrs_visible"),
                "reviews": vis_reviews.get("module_enabled"),
                "competencies": bool((c2.get_company_settings(cur, company) or {}).get("competencies_enabled")),
                "review_360": bool((c2.get_company_settings(cur, company) or {}).get("review_360_enabled")),
            },
            "talent_visible": False,
            "learning_required": False,
            **honesty_payload(company_code=company),
        }
    )


def list_objectives(
    cur: Any,
    *,
    company_code: str,
    owner_employee_key: str | None = None,
    manager_scope_keys: list[str] | None = None,
    status: str | None = None,
    limit: int = 100,
    offset: int = 0,
) -> dict[str, Any]:
    ensure_all_schemas(cur)
    company = c1.company_code_norm(company_code)
    where = ["company_code=%s"]
    params: list[Any] = [company]
    if owner_employee_key:
        where.append("owner_employee_key=%s")
        params.append(owner_employee_key)
    elif manager_scope_keys is not None:
        extra, extra_params = _scope_sql("owner_employee_key", manager_scope_keys)
        if extra:
            where.append(extra.replace(" AND ", "", 1))
            params.extend(extra_params)
        else:
            return strip_talent(
                {
                    "ok": True,
                    "objectives": [],
                    "total": 0,
                    **honesty_payload(company_code=company),
                }
            )
    if status:
        where.append("status=%s")
        params.append(str(status).strip().lower())
    cur.execute(
        f"SELECT COUNT(*) AS n FROM perf_objectives WHERE {' AND '.join(where)}",
        params,
    )
    total = int((_row(cur.fetchone()).get("n") or 0))
    cur.execute(
        f"""
        SELECT * FROM perf_objectives
         WHERE {' AND '.join(where)}
         ORDER BY updated_at DESC
         LIMIT %s OFFSET %s
        """,
        [*params, max(1, min(int(limit or 100), 200)), max(0, int(offset or 0))],
    )
    rows = [_row(r) for r in (cur.fetchall() or [])]
    items = []
    for obj in rows:
        rollup = c1.objective_rollup(cur, company_code=company, objective_id=str(obj["objective_id"]))
        items.append({**obj, "rollup": rollup, "entity": "objective", "not_generic_goal": True})
    return strip_talent(
        {
            "ok": True,
            "objectives": items,
            "total": total,
            **honesty_payload(company_code=company),
        }
    )


def get_objective_detail(
    cur: Any,
    *,
    company_code: str,
    objective_id: str,
    manager_scope_keys: list[str] | None = None,
    actor_employee_key: str | None = None,
    actor_role: str = "hr",
) -> dict[str, Any]:
    ensure_all_schemas(cur)
    company = c1.company_code_norm(company_code)
    cur.execute(
        "SELECT * FROM perf_objectives WHERE company_code=%s AND objective_id=%s",
        (company, objective_id),
    )
    obj = cur.fetchone()
    if not obj:
        return {"ok": False, "error": "objective_not_found"}
    obj = _row(obj)
    owner = str(obj.get("owner_employee_key") or "")
    if actor_role == "employee" and actor_employee_key and owner != str(actor_employee_key):
        return {"ok": False, "error": "objective_not_found"}
    if actor_role == "manager" and manager_scope_keys is not None and owner not in {str(k) for k in manager_scope_keys}:
        return {"ok": False, "error": "objective_not_found"}
    cur.execute(
        """
        SELECT kr.*, m.name_en AS measure_name_en, m.name_ar AS measure_name_ar,
               m.unit, m.direction, m.baseline, m.target, m.range_low, m.range_high
          FROM perf_key_results kr
          JOIN perf_measure_definitions m ON m.measure_id=kr.measure_id
         WHERE kr.company_code=%s AND kr.objective_id=%s
         ORDER BY kr.created_at
        """,
        (company, objective_id),
    )
    krs = [_row(r) for r in (cur.fetchall() or [])]
    rollup = c1.objective_rollup(cur, company_code=company, objective_id=str(objective_id))
    versions = c1.list_target_versions(cur, company_code=company, subject_type="objective", subject_id=str(objective_id))
    cur.execute(
        """
        SELECT * FROM perf_alignment_links
         WHERE company_code=%s AND (from_id=%s OR to_id=%s)
        """,
        (company, objective_id, objective_id),
    )
    links = [_row(r) for r in (cur.fetchall() or [])]
    updates: list[dict[str, Any]] = []
    operating_history: dict[str, Any] = {}
    try:
        import okr_operating_pt1 as pt1

        updates = (pt1.list_updates(cur, company_code=company, subject_type="objective", subject_id=str(objective_id)).get("updates") or [])
        operating_history = pt1.objective_operating_history(cur, company_code=company, objective_id=str(objective_id))
    except Exception:
        updates = []
        operating_history = {}
    return strip_talent(
        {
            "ok": True,
            "objective": obj,
            "key_results": krs,
            "rollup": rollup,
            "alignment": links,
            "history": versions,
            "updates": updates,
            "operating_history": operating_history,
            "entity": "objective",
            "not_generic_goal": True,
            "inherits_score": False,
            **honesty_payload(company_code=company),
        }
    )


def list_cycles(
    cur: Any,
    *,
    company_code: str,
    status: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> dict[str, Any]:
    ensure_all_schemas(cur)
    company = c1.company_code_norm(company_code)
    where = ["company_code=%s"]
    params: list[Any] = [company]
    if status:
        where.append("status=%s")
        params.append(str(status).strip().lower())
    cur.execute(f"SELECT COUNT(*) AS n FROM perf_review_cycles WHERE {' AND '.join(where)}", params)
    total = int((_row(cur.fetchone()).get("n") or 0))
    cur.execute(
        f"""
        SELECT cycle_id, name_en, name_ar, status, period_start, period_end,
               due_self, due_manager, due_360, launched_at, closed_at,
               competencies_enabled, review_360_enabled, anonymity_enabled,
               min_respondent_threshold, row_version
          FROM perf_review_cycles
         WHERE {' AND '.join(where)}
         ORDER BY created_at DESC
         LIMIT %s OFFSET %s
        """,
        [*params, max(1, min(int(limit or 50), 200)), max(0, int(offset or 0))],
    )
    cycles = [_row(r) for r in (cur.fetchall() or [])]
    for cycle in cycles:
        cur.execute(
            """
            SELECT reviewer_role, status, COUNT(*) AS n
              FROM perf_reviews
             WHERE company_code=%s AND cycle_id=%s
             GROUP BY reviewer_role, status
            """,
            (company, cycle["cycle_id"]),
        )
        cycle["completion"] = [_row(r) for r in (cur.fetchall() or [])]
    return strip_talent({"ok": True, "cycles": cycles, "total": total, **honesty_payload(company_code=company)})


def get_cycle_detail(
    cur: Any,
    *,
    company_code: str,
    cycle_id: str,
    actor_role: str = "hr",
    include_snapshot: bool = True,
) -> dict[str, Any]:
    ensure_all_schemas(cur)
    company = c1.company_code_norm(company_code)
    cycle = c2.get_cycle(cur, company_code=company, cycle_id=cycle_id)
    if not cycle:
        return {"ok": False, "error": "cycle_not_found"}
    cur.execute(
        "SELECT * FROM perf_cycle_participants WHERE company_code=%s AND cycle_id=%s ORDER BY employee_key",
        (company, cycle_id),
    )
    participants = [_row(r) for r in (cur.fetchall() or [])]
    cur.execute(
        """
        SELECT assignment_id, subject_employee_key, reviewer_role, status, anonymous,
               reviewer_employee_key, reviewer_phone
          FROM perf_cycle_reviewer_assignments
         WHERE company_code=%s AND cycle_id=%s
        """,
        (company, cycle_id),
    )
    assignments = [_row(r) for r in (cur.fetchall() or [])]
    if actor_role == "employee":
        for asn in assignments:
            if asn.get("anonymous") or asn.get("reviewer_role") in ANON_360_ROLES:
                asn["reviewer_employee_key"] = None
                asn["reviewer_phone"] = None
                asn["identities_redacted"] = True
    snapshot = cycle.get("snapshot") if include_snapshot else None
    return strip_talent(
        {
            "ok": True,
            "cycle": {k: v for k, v in cycle.items() if k != "snapshot" or include_snapshot},
            "participants": participants,
            "assignments": assignments,
            "snapshot_frozen": bool(cycle.get("snapshot")),
            "snapshot": snapshot if actor_role in {"hr", "admin", "owner", "cycle_admin"} else None,
            **honesty_payload(company_code=company),
        }
    )


def _redact_review(
    review: dict[str, Any],
    *,
    actor_role: str,
    actor_employee_key: str | None,
    cycle: Mapping[str, Any] | None,
    can_see_sensitive: bool,
) -> dict[str, Any] | None:
    out = dict(review)
    role = str(out.get("reviewer_role") or "")
    subject = str(out.get("subject_employee_key") or "")
    reviewer = str(out.get("reviewer_employee_key") or "")
    status = str(out.get("status") or "")
    if actor_role == "employee":
        if actor_employee_key and subject != str(actor_employee_key) and reviewer != str(actor_employee_key):
            return None
        if role == "manager" and status in {"not_started", "draft"}:
            return None
        if role in ANON_360_ROLES:
            out["reviewer_employee_key"] = None
            out["reviewer_phone"] = None
            out["identities_redacted"] = True
            out.pop("confidential_comment", None)
        if role == "manager" and not can_see_sensitive:
            out.pop("confidential_comment", None)
    elif actor_role == "manager":
        if role in ANON_360_ROLES and (cycle or {}).get("anonymity_enabled"):
            out["reviewer_employee_key"] = None
            out["reviewer_phone"] = None
            out["identities_redacted"] = True
        if not can_see_sensitive:
            out.pop("confidential_comment", None)
    elif not can_see_sensitive:
        out.pop("confidential_comment", None)
    return out


def list_reviews(
    cur: Any,
    *,
    company_code: str,
    cycle_id: str | None = None,
    subject_employee_key: str | None = None,
    reviewer_role: str | None = None,
    actor_role: str = "hr",
    actor_employee_key: str | None = None,
    manager_scope_keys: list[str] | None = None,
    pending_only: bool = False,
    limit: int = 100,
    offset: int = 0,
) -> dict[str, Any]:
    ensure_all_schemas(cur)
    company = c1.company_code_norm(company_code)
    where = ["r.company_code=%s"]
    params: list[Any] = [company]
    if cycle_id:
        where.append("r.cycle_id=%s")
        params.append(cycle_id)
    if subject_employee_key:
        where.append("r.subject_employee_key=%s")
        params.append(subject_employee_key)
    if reviewer_role:
        where.append("r.reviewer_role=%s")
        params.append(str(reviewer_role).strip().lower())
    if pending_only:
        where.append("r.status IN ('not_started','draft')")
    if actor_role == "employee" and actor_employee_key:
        where.append("(r.subject_employee_key=%s OR r.reviewer_employee_key=%s)")
        params.extend([actor_employee_key, actor_employee_key])
    elif actor_role == "manager":
        keys = [str(k) for k in (manager_scope_keys or [])]
        if actor_employee_key:
            keys.append(str(actor_employee_key))
        if not keys:
            return strip_talent({"ok": True, "reviews": [], "total": 0, **honesty_payload(company_code=company)})
        where.append("(r.subject_employee_key = ANY(%s) OR r.reviewer_employee_key = ANY(%s))")
        params.extend([keys, keys])
    cur.execute(
        f"SELECT COUNT(*) AS n FROM perf_reviews r WHERE {' AND '.join(where)}",
        params,
    )
    total = int((_row(cur.fetchone()).get("n") or 0))
    cur.execute(
        f"""
        SELECT r.*, c.name_en AS cycle_name_en, c.name_ar AS cycle_name_ar,
               c.anonymity_enabled, c.status AS cycle_status, c.visibility_rules
          FROM perf_reviews r
          JOIN perf_review_cycles c ON c.cycle_id=r.cycle_id
         WHERE {' AND '.join(where)}
         ORDER BY r.updated_at DESC
         LIMIT %s OFFSET %s
        """,
        [*params, max(1, min(int(limit or 100), 200)), max(0, int(offset or 0))],
    )
    raw = [_row(r) for r in (cur.fetchall() or [])]
    items = []
    for review in raw:
        redacted = _redact_review(
            review,
            actor_role=actor_role,
            actor_employee_key=actor_employee_key,
            cycle=review,
            can_see_sensitive=actor_role in {"hr", "admin", "owner"},
        )
        if redacted:
            items.append(redacted)
    return strip_talent(
        {
            "ok": True,
            "reviews": items,
            "total": total,
            "layers_collapsed": False,
            **honesty_payload(company_code=company),
        }
    )


def get_review_detail(
    cur: Any,
    *,
    company_code: str,
    review_id: str,
    actor_role: str,
    actor_employee_key: str | None = None,
    manager_scope_keys: list[str] | None = None,
    can_see_sensitive: bool = False,
) -> dict[str, Any]:
    ensure_all_schemas(cur)
    company = c1.company_code_norm(company_code)
    cur.execute(
        """
        SELECT r.*, c.anonymity_enabled, c.visibility_rules, c.status AS cycle_status,
               c.min_respondent_threshold, c.review_360_enabled, c.competencies_enabled,
               c.snapshot, a.assignment_id, a.anonymous
          FROM perf_reviews r
          JOIN perf_review_cycles c ON c.cycle_id=r.cycle_id
          LEFT JOIN perf_cycle_reviewer_assignments a ON a.assignment_id=r.assignment_id
         WHERE r.company_code=%s AND r.review_id=%s
        """,
        (company, review_id),
    )
    review = cur.fetchone()
    if not review:
        return {"ok": False, "error": "review_not_found"}
    review = _row(review)
    subject = str(review.get("subject_employee_key") or "")
    reviewer = str(review.get("reviewer_employee_key") or "")
    if actor_role == "employee":
        if actor_employee_key and subject != str(actor_employee_key) and reviewer != str(actor_employee_key):
            return {"ok": False, "error": "review_not_found"}
    if actor_role == "manager" and manager_scope_keys is not None:
        allowed = {str(k) for k in manager_scope_keys}
        if actor_employee_key:
            allowed.add(str(actor_employee_key))
        if subject not in allowed and reviewer not in allowed:
            return {"ok": False, "error": "review_not_found"}
    redacted = _redact_review(
        review,
        actor_role=actor_role,
        actor_employee_key=actor_employee_key,
        cycle=review,
        can_see_sensitive=can_see_sensitive,
    )
    if redacted is None:
        return {"ok": False, "error": "review_not_found"}
    layers = c2.get_layer_ratings(
        cur,
        company_code=company,
        cycle_id=str(review["cycle_id"]),
        subject_employee_key=subject,
    )
    if actor_role == "employee":
        layer_map = dict(layers.get("layers") or {})
        mgr = layer_map.get("manager")
        if mgr and str(mgr.get("status") or "") in {"not_started", "draft"}:
            layer_map["manager"] = None
        extra_360 = []
        for item in layer_map.get("additional_360") or []:
            extra_360.append(
                {
                    "reviewer_role": item.get("reviewer_role"),
                    "status": item.get("status"),
                    "overall_rating_value": None,
                    "identities_redacted": True,
                }
            )
        layer_map["additional_360"] = extra_360
        vis = review.get("visibility_rules") or {}
        if isinstance(vis, str):
            import json

            vis = json.loads(vis)
        if not (vis or {}).get("reveal_final_to_employee"):
            layer_map["final"] = None
        layers = {**layers, "layers": layer_map}
    agg = None
    if review.get("review_360_enabled") and actor_role != "employee":
        agg = c2.get_360_aggregate(
            cur,
            company_code=company,
            cycle_id=str(review["cycle_id"]),
            subject_employee_key=subject,
            actor_role=actor_role,
        )
    return strip_talent(
        {
            "ok": True,
            "review": redacted,
            "layers": layers,
            "aggregate_360": agg,
            "talent_visible": False,
            **honesty_payload(company_code=company),
        }
    )


def list_check_ins(
    cur: Any,
    *,
    company_code: str,
    employee_key: str | None = None,
    manager_scope_keys: list[str] | None = None,
    actor_role: str = "hr",
    limit: int = 100,
    offset: int = 0,
) -> dict[str, Any]:
    ensure_all_schemas(cur)
    company = c1.company_code_norm(company_code)
    where = ["company_code=%s"]
    params: list[Any] = [company]
    if employee_key:
        where.append("employee_key=%s")
        params.append(employee_key)
    elif actor_role == "manager" and manager_scope_keys is not None:
        extra, extra_params = _scope_sql("employee_key", manager_scope_keys)
        if not extra:
            return strip_talent({"ok": True, "check_ins": [], "total": 0, **honesty_payload(company_code=company)})
        where.append(extra.replace(" AND ", "", 1))
        params.extend(extra_params)
    cur.execute(f"SELECT COUNT(*) AS n FROM perf_check_ins WHERE {' AND '.join(where)}", params)
    total = int((_row(cur.fetchone()).get("n") or 0))
    cur.execute(
        f"""
        SELECT check_in_id, kind, status, employee_key, manager_employee_key,
               scheduled_for, next_check_in_date, notes_shared, visibility,
               linked_subject_type, linked_subject_id, completed_at, row_version
          FROM perf_check_ins
         WHERE {' AND '.join(where)}
         ORDER BY updated_at DESC
         LIMIT %s OFFSET %s
        """,
        [*params, max(1, min(int(limit or 100), 200)), max(0, int(offset or 0))],
    )
    rows = [_row(r) for r in (cur.fetchall() or [])]
    if actor_role == "employee":
        for row in rows:
            row.pop("notes_sensitive", None)
    return strip_talent({"ok": True, "check_ins": rows, "total": total, **honesty_payload(company_code=company)})


def list_development(
    cur: Any,
    *,
    company_code: str,
    employee_key: str | None = None,
    manager_scope_keys: list[str] | None = None,
    actor_role: str = "hr",
    limit: int = 100,
    offset: int = 0,
) -> dict[str, Any]:
    ensure_all_schemas(cur)
    company = c1.company_code_norm(company_code)
    where = ["p.company_code=%s"]
    params: list[Any] = [company]
    if employee_key:
        where.append("p.employee_key=%s")
        params.append(employee_key)
    elif actor_role == "manager" and manager_scope_keys is not None:
        extra, extra_params = _scope_sql("p.employee_key", manager_scope_keys)
        if not extra:
            return strip_talent(
                {"ok": True, "plans": [], "actions": [], "total": 0, **honesty_payload(company_code=company)}
            )
        where.append(extra.replace(" AND ", "", 1))
        params.extend(extra_params)
    cur.execute(
        f"""
        SELECT p.*, a.action_id, a.title_en AS action_title_en, a.title_ar AS action_title_ar,
               a.status AS action_status, a.due_date, a.source_type, a.hr_task_id
          FROM perf_development_plans p
          LEFT JOIN perf_development_actions a ON a.plan_id=p.plan_id
         WHERE {' AND '.join(where)}
         ORDER BY p.updated_at DESC
         LIMIT %s OFFSET %s
        """,
        [*params, max(1, min(int(limit or 100), 200)), max(0, int(offset or 0))],
    )
    rows = [_row(r) for r in (cur.fetchall() or [])]
    return strip_talent(
        {
            "ok": True,
            "items": rows,
            "learning_completion_is_not_development_completion": True,
            "learning_required": False,
            **honesty_payload(company_code=company),
        }
    )


def list_calibration_sessions(
    cur: Any,
    *,
    company_code: str,
    actor_phone: str | None = None,
    authorized_only: bool = True,
    limit: int = 50,
) -> dict[str, Any]:
    ensure_all_schemas(cur)
    company = c1.company_code_norm(company_code)
    if authorized_only and actor_phone:
        cur.execute(
            """
            SELECT s.*
              FROM perf_calibration_sessions s
              JOIN perf_calibration_participants p
                ON p.session_id=s.session_id AND p.participant_phone=%s
             WHERE s.company_code=%s
             ORDER BY s.updated_at DESC
             LIMIT %s
            """,
            (c4._digits(actor_phone), company, max(1, min(int(limit or 50), 100))),
        )
    else:
        cur.execute(
            """
            SELECT * FROM perf_calibration_sessions
             WHERE company_code=%s
             ORDER BY updated_at DESC
             LIMIT %s
            """,
            (company, max(1, min(int(limit or 50), 100))),
        )
    sessions = [_row(r) for r in (cur.fetchall() or [])]
    return strip_talent(
        {
            "ok": True,
            "sessions": sessions,
            "pre_calibration_distinct_from_calibrated": True,
            **honesty_payload(company_code=company),
        }
    )


def get_calibration_detail(
    cur: Any,
    *,
    company_code: str,
    session_id: str,
    actor_phone: str,
    can_calibrate: bool,
) -> dict[str, Any]:
    ensure_all_schemas(cur)
    company = c1.company_code_norm(company_code)
    session = c4.get_session(cur, company_code=company, session_id=session_id)
    if not session:
        return {"ok": False, "error": "calibration_session_not_found"}
    cur.execute(
        """
        SELECT 1 FROM perf_calibration_participants
         WHERE company_code=%s AND session_id=%s AND participant_phone=%s
        """,
        (company, session_id, c4._digits(actor_phone)),
    )
    participant = cur.fetchone()
    if not can_calibrate and not participant:
        return {"ok": False, "error": "calibration_forbidden"}
    cur.execute(
        """
        SELECT * FROM perf_calibrated_results
         WHERE company_code=%s AND session_id=%s
         ORDER BY subject_employee_key
        """,
        (company, session_id),
    )
    results = [_row(r) for r in (cur.fetchall() or [])]
    return strip_talent(
        {
            "ok": True,
            "session": session,
            "results": results,
            "pre_calibration_distinct_from_calibrated": True,
            "sealed_immutable": str(session.get("status") or "") in {"locked", "published"},
            **honesty_payload(company_code=company),
        }
    )


def employee_workspace(
    cur: Any,
    *,
    company_code: str,
    employee_key: str,
) -> dict[str, Any]:
    goals = list_objectives(cur, company_code=company_code, owner_employee_key=employee_key)
    reviews = list_reviews(
        cur,
        company_code=company_code,
        actor_role="employee",
        actor_employee_key=employee_key,
    )
    check_ins = list_check_ins(
        cur, company_code=company_code, employee_key=employee_key, actor_role="employee"
    )
    development = list_development(
        cur, company_code=company_code, employee_key=employee_key, actor_role="employee"
    )
    active_okr_cycle = None
    try:
        import okr_operating_pt1 as pt1

        active_okr_cycle = (pt1.current_okr_cycle(cur, company_code=company_code) or {}).get("cycle")
    except Exception:
        active_okr_cycle = None
    return strip_talent(
        {
            "ok": True,
            "employee_key": employee_key,
            "goals": goals.get("objectives") or [],
            "reviews": reviews.get("reviews") or [],
            "check_ins": check_ins.get("check_ins") or [],
            "development": development.get("items") or [],
            "active_okr_cycle": active_okr_cycle,
            "okr_cycle_is_not_review_cycle": True,
            "calibration_hidden": True,
            "talent_visible": False,
            **honesty_payload(company_code=company_code),
        }
    )


def manager_queue(
    cur: Any,
    *,
    company_code: str,
    manager_scope_keys: list[str],
    actor_employee_key: str | None = None,
    limit: int = 50,
) -> dict[str, Any]:
    reviews = list_reviews(
        cur,
        company_code=company_code,
        reviewer_role="manager",
        actor_role="manager",
        actor_employee_key=actor_employee_key,
        manager_scope_keys=manager_scope_keys,
        pending_only=True,
        limit=limit,
    )
    return strip_talent(
        {
            "ok": True,
            "items": reviews.get("reviews") or [],
            "total": reviews.get("total") or 0,
            "company_wide": False,
            "calibration_included": False,
            **honesty_payload(company_code=company_code),
        }
    )


def list_measures(
    cur: Any,
    *,
    company_code: str,
    limit: int = 100,
    offset: int = 0,
) -> dict[str, Any]:
    ensure_all_schemas(cur)
    company = c1.company_code_norm(company_code)
    cur.execute("SELECT COUNT(*) AS n FROM perf_measure_definitions WHERE company_code=%s", (company,))
    total = int((_row(cur.fetchone()).get("n") or 0))
    cur.execute(
        """
        SELECT * FROM perf_measure_definitions
         WHERE company_code=%s
         ORDER BY updated_at DESC
         LIMIT %s OFFSET %s
        """,
        (company, max(1, min(int(limit or 100), 200)), max(0, int(offset or 0))),
    )
    return strip_talent(
        {
            "ok": True,
            "measures": [_row(r) for r in (cur.fetchall() or [])],
            "total": total,
            **honesty_payload(company_code=company),
        }
    )


def list_scales(cur: Any, *, company_code: str) -> dict[str, Any]:
    ensure_all_schemas(cur)
    company = c1.company_code_norm(company_code)
    cur.execute(
        "SELECT * FROM perf_rating_scales WHERE company_code=%s ORDER BY created_at DESC",
        (company,),
    )
    return strip_talent(
        {
            "ok": True,
            "scales": [_row(r) for r in (cur.fetchall() or [])],
            **honesty_payload(company_code=company),
        }
    )


def list_templates(cur: Any, *, company_code: str) -> dict[str, Any]:
    ensure_all_schemas(cur)
    company = c1.company_code_norm(company_code)
    cur.execute(
        "SELECT * FROM perf_review_templates WHERE company_code=%s ORDER BY created_at DESC",
        (company,),
    )
    return strip_talent(
        {
            "ok": True,
            "templates": [_row(r) for r in (cur.fetchall() or [])],
            **honesty_payload(company_code=company),
        }
    )


def list_competencies(cur: Any, *, company_code: str) -> dict[str, Any]:
    """Competencies stay independently configurable. OFF returns an honest empty."""
    ensure_all_schemas(cur)
    company = c1.company_code_norm(company_code)
    settings = c3.get_company_settings(cur, company) or {}
    enabled = bool(settings.get("enabled") and settings.get("competencies_enabled"))
    if not enabled:
        return strip_talent(
            {
                "ok": True,
                "enabled": False,
                "frameworks": [],
                "competencies": [],
                "competencies_optional": True,
                **honesty_payload(company_code=company),
            }
        )
    cur.execute(
        "SELECT * FROM perf_c3_competency_frameworks WHERE company_code=%s ORDER BY created_at",
        (company,),
    )
    frameworks = [_row(r) for r in (cur.fetchall() or [])]
    cur.execute(
        "SELECT * FROM perf_c3_competencies WHERE company_code=%s ORDER BY created_at",
        (company,),
    )
    return strip_talent(
        {
            "ok": True,
            "enabled": True,
            "frameworks": frameworks,
            "competencies": [_row(r) for r in (cur.fetchall() or [])],
            "competencies_optional": True,
            **honesty_payload(company_code=company),
        }
    )


def employee_owns_progress_subject(
    cur: Any,
    *,
    company_code: str,
    employee_key: str,
    subject_type: str,
    subject_id: str,
) -> bool:
    company = c1.company_code_norm(company_code)
    kind = str(subject_type or "").strip().lower()
    sid = str(subject_id or "").strip()
    emp = str(employee_key or "").strip()
    if not sid or not emp:
        return False
    if kind == "objective":
        cur.execute(
            "SELECT owner_employee_key FROM perf_objectives WHERE company_code=%s AND objective_id=%s",
            (company, sid),
        )
        row = cur.fetchone()
        return bool(row) and str((_row(row).get("owner_employee_key") or "")) == emp
    if kind == "key_result":
        cur.execute(
            """
            SELECT o.owner_employee_key
              FROM perf_key_results kr
              JOIN perf_objectives o
                ON o.objective_id=kr.objective_id AND o.company_code=kr.company_code
             WHERE kr.company_code=%s AND kr.key_result_id=%s
            """,
            (company, sid),
        )
        row = cur.fetchone()
        return bool(row) and str((_row(row).get("owner_employee_key") or "")) == emp
    return False
