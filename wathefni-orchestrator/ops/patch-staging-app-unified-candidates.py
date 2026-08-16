#!/usr/bin/env python3
"""Surgically patch staging app.py with Unified Candidates hooks only.

Preserves C0–C3 ownership/collaboration, durable email ingress, ranking, offers.
Does not replace the whole local dirty app.py.
"""

from __future__ import annotations

import sys
from pathlib import Path

BASE = Path(sys.argv[1] if len(sys.argv) > 1 else "/tmp/unified-staging/app.py.staging")
OUT = Path(sys.argv[2] if len(sys.argv) > 2 else "/tmp/unified-staging/app.py.patched")


def must_replace(hay: str, old: str, new: str, label: str) -> str:
    if old not in hay:
        raise SystemExit(f"missing anchor for {label}")
    count = hay.count(old)
    if count != 1:
        raise SystemExit(f"anchor for {label} matched {count} times (want 1)")
    return hay.replace(old, new, 1)


src = BASE.read_text(encoding="utf-8")
if "UNIFIED_CANDIDATES_STAGING_PATCH" in src:
    raise SystemExit("already patched")

# 1) Schema ensure (additive; safe with flag OFF)
src = must_replace(
    src,
    """            _durable_email_ingress.ensure_schema(cur)
            import recruiting_lifecycle as _rl
""",
    """            _durable_email_ingress.ensure_schema(cur)
            import unified_candidates as _unified_candidates  # UNIFIED_CANDIDATES_STAGING_PATCH

            _unified_candidates.ensure_unified_candidates_schema(cur)
            import recruiting_lifecycle as _rl
""",
    "schema_hook",
)

# 2) Defer route mount to just BEFORE the SPA catch-all (helpers must exist by then)
src = must_replace(
    src,
    """import offer_routes as _offer_routes

_offer_routes.register_offer_routes(app, sys.modules[__name__])
""",
    """import offer_routes as _offer_routes

_offer_routes.register_offer_routes(app, sys.modules[__name__])
# UNIFIED_CANDIDATES_STAGING_PATCH: routes mounted before SPA catch-all
""",
    "mount_routes_placeholder",
)

# 2b) Mount immediately before dashboard SPA catch-all so API paths win.
src = must_replace(
    src,
    '''@app.get("/dashboard/{asset_path:path}")
def dashboard_spa_or_asset(asset_path: str):
''',
    '''# UNIFIED_CANDIDATES_STAGING_PATCH: late route mount after helpers exist, before SPA catch-all
import unified_candidates_routes as _unified_candidates_routes

_unified_candidates_routes.mount_unified_candidate_routes_late(sys.modules[__name__])


@app.get("/dashboard/{asset_path:path}")
def dashboard_spa_or_asset(asset_path: str):
''',
    "mount_before_spa",
)

# Remove any prior end-of-file mount if re-patching a previously appended file
END_MARK = """
# UNIFIED_CANDIDATES_STAGING_PATCH: late route mount after helpers exist
import unified_candidates_routes as _unified_candidates_routes

_unified_candidates_routes.mount_unified_candidate_routes_late(sys.modules[__name__])
"""
if src.count(END_MARK.strip()) > 1:
    # keep first (before SPA), drop trailing duplicate
    first = src.find(END_MARK.strip())
    second = src.find(END_MARK.strip(), first + 10)
    if second > 0:
        src = src[:second] + src[second:].replace(END_MARK.strip(), "", 1)


# 3) Held action denial (always fail-closed, independent of UX flag)
src = must_replace(
    src,
    """    allowed_actions: list[str] = []
    if permissions is not None:
        perms = {str(value) for value in permissions}
        allowed_actions = _rl.allowed_actions_for_stage(canonical_stage, perms)
        if cv_received and "prehire.read" in perms:
            allowed_actions.extend(["preview_cv", "download_cv"])
        if "candidate.manage" in perms:
            allowed_actions.extend(["notify", "generate_evaluation"])
        if include_assessment and cv_received and "assessment.manage" in perms:
            allowed_actions.append("send_assessment")
        if cv_received and "interview.manage" in perms:
            allowed_actions.append("send_video_interview")
        allowed_actions = list(dict.fromkeys(allowed_actions))

    stage_changed_at = lifecycle_event.get("created_at")
    sent_at = communication.get("sent_at")
    stage_changed_without_contact = (
        canonical_stage in {"shortlisted", "interview", "hired", "rejected"}
""",
    """    held_status = str(raw_status or "").strip().lower() in HELD_IMPORT_STATUSES
    allowed_actions: list[str] = []
    if permissions is not None:
        perms = {str(value) for value in permissions}
        if held_status:
            # UNIFIED_CANDIDATES_STAGING_PATCH: held rows never advertise lifecycle/outreach/ranking.
            import unified_candidates as _unified_candidates

            allowed_actions = _unified_candidates.held_allowed_actions(perms, cv_received=cv_received)
            waiting_for_hr = ["review_held_intake"]
            automatic_activity = [item for item in automatic_activity if item in {"cv_received", "cv_processed"}]
            communication_status = "intentionally_skipped"
        else:
            allowed_actions = _rl.allowed_actions_for_stage(canonical_stage, perms)
            if cv_received and "prehire.read" in perms:
                allowed_actions.extend(["preview_cv", "download_cv"])
            if "candidate.manage" in perms:
                allowed_actions.extend(["notify", "generate_evaluation"])
            if include_assessment and cv_received and "assessment.manage" in perms:
                allowed_actions.append("send_assessment")
            if cv_received and "interview.manage" in perms:
                allowed_actions.append("send_video_interview")
            allowed_actions = list(dict.fromkeys(allowed_actions))

    stage_changed_at = lifecycle_event.get("created_at")
    sent_at = communication.get("sent_at")
    stage_changed_without_contact = (
        (not held_status)
        and canonical_stage in {"shortlisted", "interview", "hired", "rejected"}
""",
    "held_actions",
)

# 4) Extend prehire_applications_query signature + unified view branch
src = must_replace(
    src,
    """def prehire_applications_query(
    *,
    company_code: str,
    status: str | None,
    position: str | None,
    search: str | None,
    limit: int,
    offset: int,
    cv_status: str | None = None,
    assessment_status: str | None = None,
    interview_status: str | None = None,
    follow_up: str | None = None,
    review_status: str | None = None,
    activity_from: str | None = None,
    activity_to: str | None = None,
    sort: str | None = None,
    include_assessment: bool = True,
    permissions: set[str] | list[str] | None = None,
    owner_scope: str | None = None,
    owner_user_id: str | None = None,
    actor_user_id: str | None = None,
    tag_id: str | None = None,
    cursor: str | None = None,
) -> dict[str, Any]:
    cv_filter = str(cv_status or "").strip().lower()
    base_predicate = production_application_predicate("a") if cv_filter in {"all", "incomplete", "missing", "no_cv"} else reviewable_application_predicate("a")
    where = ["a.company_code=%s", base_predicate]
    params: list[Any] = [company_code]
""",
    """def prehire_applications_query(
    *,
    company_code: str,
    status: str | None,
    position: str | None,
    search: str | None,
    limit: int,
    offset: int,
    cv_status: str | None = None,
    assessment_status: str | None = None,
    interview_status: str | None = None,
    follow_up: str | None = None,
    review_status: str | None = None,
    activity_from: str | None = None,
    activity_to: str | None = None,
    sort: str | None = None,
    include_assessment: bool = True,
    permissions: set[str] | list[str] | None = None,
    owner_scope: str | None = None,
    owner_user_id: str | None = None,
    actor_user_id: str | None = None,
    tag_id: str | None = None,
    cursor: str | None = None,
    view: str | None = None,
    source_channel: str | None = None,
    recruiter_owner: str | None = None,
    cv_processing_state: str | None = None,
    received_from: str | None = None,
    received_to: str | None = None,
    has_grounded_email: str | None = None,
    has_grounded_phone: str | None = None,
    fact_completeness: str | None = None,
    department_intake_tag: str | None = None,
    include_match_reasons: bool = False,
) -> dict[str, Any]:
    import unified_candidates as _uc  # UNIFIED_CANDIDATES_STAGING_PATCH

    cv_filter = str(cv_status or "").strip().lower()
    view_key = str(view or "").strip().lower()
    unified_on = _uc.feature_enabled_for_company(company_code)
    use_unified = unified_on and (
        bool(view_key)
        or any(
            [
                source_channel,
                recruiter_owner,
                cv_processing_state,
                received_from,
                received_to,
                has_grounded_email,
                has_grounded_phone,
                fact_completeness,
                department_intake_tag,
            ]
        )
    )
    if use_unified:
        view_key = view_key or _uc.VIEW_ALL
        view_sql, view_params = _uc.view_predicate_sql(view_key, "a", "gov")
        where = ["a.company_code=%s", view_sql]
        params: list[Any] = [company_code, *view_params]
    else:
        base_predicate = production_application_predicate("a") if cv_filter in {"all", "incomplete", "missing", "no_cv"} else reviewable_application_predicate("a")
        where = ["a.company_code=%s", base_predicate]
        params = [company_code]
        view_key = ""
""",
    "query_signature",
)

# 4b) Unified search clause (flag-on only)
src = must_replace(
    src,
    """    if search:
        where.append(
            "(a.app_key ILIKE %s OR a.phone ILIKE %s OR c.name ILIKE %s OR c.email ILIKE %s "
            "OR a.position_code ILIKE %s OR a.position_title ILIKE %s)"
        )
        like = f"%{search}%"
        params.extend([like, like, like, like, like, like])
""",
    """    if search:
        if use_unified:
            where.append(
                "("
                "a.app_key ILIKE %s OR c.name ILIKE %s OR c.email ILIKE %s "
                "OR a.position_code ILIKE %s OR a.position_title ILIKE %s "
                "OR (a.phone NOT ILIKE 'imp-%%' AND a.phone ILIKE %s) "
                "OR COALESCE(a.raw_json->>'candidate_email', a.raw_json->>'email', '') ILIKE %s "
                "OR COALESCE(a.raw_json->>'candidate_phone', '') ILIKE %s "
                "OR COALESCE(sd.content, '') ILIKE %s "
                "OR COALESCE(c.profile::text, '') ILIKE %s"
                ")"
            )
            like = f"%{search}%"
            params.extend([like, like, like, like, like, like, like, like, like, like])
        else:
            where.append(
                "(a.app_key ILIKE %s OR a.phone ILIKE %s OR c.name ILIKE %s OR c.email ILIKE %s "
                "OR a.position_code ILIKE %s OR a.position_title ILIKE %s)"
            )
            like = f"%{search}%"
            params.extend([like, like, like, like, like, like])
""",
    "search_clause",
)

# 5) Extra filters after activity_to block (before sort_key)
src = must_replace(
    src,
    """    if activity_to:
        where.append("COALESCE(a.updated_at, a.ingested_at) < (%s::date + interval '1 day')")
        params.append(activity_to)
    sort_key = str(sort or "newest").strip().lower()
""",
    """    if activity_to:
        where.append("COALESCE(a.updated_at, a.ingested_at) < (%s::date + interval '1 day')")
        params.append(activity_to)
    if received_from:
        where.append("a.ingested_at >= %s::date")
        params.append(received_from)
    if received_to:
        where.append("a.ingested_at < (%s::date + interval '1 day')")
        params.append(received_to)
    if source_channel:
        where.append(
            "LOWER(COALESCE(a.raw_json->'intake'->>'source', a.raw_json->'import'->>'source', a.raw_json->>'intake_source', a.data_source, '')) ILIKE %s"
        )
        params.append(f"%{source_channel.strip().lower()}%")
    if recruiter_owner:
        if str(recruiter_owner).strip().lower() in {"unassigned", "none", "-"}:
            where.append("COALESCE(gov.recruiter_owner_user_id, a.owner_user_id::text, '') = ''")
        else:
            where.append("COALESCE(gov.recruiter_owner_user_id, a.owner_user_id::text, '') = %s")
            params.append(str(recruiter_owner).strip())
    if cv_processing_state:
        bucket = str(cv_processing_state).strip().lower()
        if bucket == "ready":
            where.append(
                "(COALESCE(a.raw_json->'cv'->'processing'->>'profile_parsed','') IN ('true','1') "
                "OR jsonb_typeof(c.profile) = 'object')"
            )
        elif bucket == "partial":
            where.append(
                "(COALESCE(a.raw_json->'cv'->'processing'->>'status','') ILIKE ANY(ARRAY['partial','incomplete','processing']) "
                "OR COALESCE(a.raw_json->'cv'->'processing'->>'text_extracted','') IN ('true','1'))"
            )
        elif bucket == "failed":
            where.append("COALESCE(a.raw_json->'cv'->'processing'->>'status','') ILIKE ANY(ARRAY['failed','error','dead_letter'])")
    if has_grounded_email and str(has_grounded_email).strip().lower() in {"1", "true", "yes"}:
        where.append("COALESCE(c.email, a.raw_json->>'candidate_email', a.raw_json->>'email', '') <> ''")
    if has_grounded_phone and str(has_grounded_phone).strip().lower() in {"1", "true", "yes"}:
        where.append(
            "("
            "(a.phone IS NOT NULL AND a.phone NOT ILIKE 'imp-%%') "
            "OR COALESCE(a.raw_json->>'candidate_phone','') <> ''"
            ")"
        )
    if department_intake_tag:
        where.append("COALESCE(gov.department_intake_tag, '') ILIKE %s")
        params.append(f"%{department_intake_tag.strip()}%")
    sort_key = str(sort or "newest").strip().lower()
""",
    "extra_filters",
)

# 6) Add governance + semantic joins
src = must_replace(
    src,
    '''    joins_sql = """
                LEFT JOIN candidates c ON c.phone=a.phone
                LEFT JOIN dashboard_users owner_user
                  ON owner_user.company_code=a.company_code
                 AND owner_user.user_id=a.owner_user_id
                LEFT JOIN LATERAL (
''',
    '''    joins_sql = """
                LEFT JOIN candidates c ON c.phone=a.phone
                LEFT JOIN dashboard_users owner_user
                  ON owner_user.company_code=a.company_code
                 AND owner_user.user_id=a.owner_user_id
                LEFT JOIN candidate_record_governance gov
                  ON gov.company_code=a.company_code AND gov.app_key=a.app_key
                LEFT JOIN semantic_documents sd
                  ON sd.entity_type='application' AND sd.entity_key=a.app_key
                LEFT JOIN LATERAL (
''',
    "joins",
)

# 7) Enrich application summaries when unified
src = must_replace(
    src,
    """        "applications": [
            prehire_application_summary(
                row,
                include_assessment=include_assessment,
                permissions=permissions,
            )
            for row in rows
        ],
    }
""",
    """        "view": view_key or None,
        "unified_candidates": use_unified,
        "applications": _unified_applications_payload(
            rows,
            include_assessment=include_assessment,
            permissions=permissions,
            use_unified=use_unified,
            include_match_reasons=include_match_reasons,
            search=search,
            _uc=_uc,
            prehire_application_summary=prehire_application_summary,
        ),
    }
""",
    "enrich_summaries",
)

# Helper inserted once near prehire_applications_query
if "def _unified_applications_payload(" not in src:
    src = must_replace(
        src,
        "def prehire_applications_query(",
        '''def _unified_applications_payload(
    rows,
    *,
    include_assessment,
    permissions,
    use_unified,
    include_match_reasons,
    search,
    _uc,
    prehire_application_summary,
):
    out = []
    for row in rows:
        summary = prehire_application_summary(
            row,
            include_assessment=include_assessment,
            permissions=permissions,
        )
        if use_unified:
            gov = row.get("governance_json") if isinstance(row.get("governance_json"), dict) else None
            summary = _uc.enrich_application_summary(summary, row, gov=gov, permissions=permissions)
            if include_match_reasons and search:
                snapshot = _uc.extract_facts_snapshot(row)
                effective = _uc.effective_facts_from_events(snapshot, [])
                summary["match_reasons"] = _uc.search_match_reasons(
                    query=search,
                    row=row,
                    effective_facts=effective,
                    semantic_similarity=None,
                )
                summary["record_state_label"] = _uc.record_state_label(
                    summary.get("record_state") or _uc.RECORD_ACTIVE
                )
        out.append(summary)
    return out


def prehire_applications_query(
''',
        "helper_payload",
    )


# Select governance fields when unified — add to SELECT list
src = must_replace(
    src,
    """                SELECT a.*, c.name AS candidate_name, c.email AS candidate_email,
                       c.profile AS candidate_profile, c.raw_json AS candidate_raw_json,
                       latest_assessment.assessment_json,
                       latest_interview.interview_json,
                       latest_eval.rank_evaluation_json,
                       latest_delivery.communication_json,
                       latest_review_task.review_task_json,
                       latest_lifecycle_event.lifecycle_event_json,
                       owner_user.name AS owner_name,
                       owner_user.email AS owner_email,
                       owner_user.role AS owner_role,
                       owner_user.status AS owner_status,
                       COALESCE(c2_tasks.open_task_count,0) AS open_task_count,
                       COALESCE(c2_tasks.overdue_task_count,0) AS overdue_task_count,
                       c2_tags.tags_json
""",
    """                SELECT a.*, c.name AS candidate_name, c.email AS candidate_email,
                       c.profile AS candidate_profile, c.raw_json AS candidate_raw_json,
                       latest_assessment.assessment_json,
                       latest_interview.interview_json,
                       latest_eval.rank_evaluation_json,
                       latest_delivery.communication_json,
                       latest_review_task.review_task_json,
                       latest_lifecycle_event.lifecycle_event_json,
                       owner_user.name AS owner_name,
                       owner_user.email AS owner_email,
                       owner_user.role AS owner_role,
                       owner_user.status AS owner_status,
                       COALESCE(c2_tasks.open_task_count,0) AS open_task_count,
                       COALESCE(c2_tasks.overdue_task_count,0) AS overdue_task_count,
                       c2_tags.tags_json,
                       to_jsonb(gov.*) AS governance_json,
                       sd.content AS semantic_content
""",
    "select_gov",
)

# 8) Dashboard list endpoint accepts view params
src = must_replace(
    src,
    """@app.get("/dashboard/prehire/applications")
def dashboard_prehire_applications(
    status: str | None = None,
    position: str | None = None,
    q: str | None = None,
    cv_status: str | None = None,
    assessment_status: str | None = None,
    interview_status: str | None = None,
    follow_up: str | None = None,
    review_status: str | None = None,
    activity_from: str | None = None,
    activity_to: str | None = None,
    sort: str | None = None,
    owner_scope: str | None = None,
    owner_user_id: str | None = None,
    tag_id: str | None = None,
    cursor: str | None = None,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    context: dict[str, Any] = Depends(prehire_dashboard_context),
):
    require_entitlement(context, "pre_hiring", "candidates.read")
    company = context["company_code"]
    return {
        "company_code": company,
        **prehire_applications_query(
            company_code=company,
            status=(status or "").strip() or None,
            position=(position or "").strip() or None,
            search=(q or "").strip() or None,
            limit=bounded_limit(limit),
            offset=max(0, int(offset)),
            cv_status=(cv_status or "").strip() or None,
            assessment_status=(assessment_status or "").strip() or None,
            interview_status=(interview_status or "").strip() or None,
            follow_up=(follow_up or "").strip() or None,
            review_status=(review_status or "").strip() or None,
            activity_from=(activity_from or "").strip() or None,
            activity_to=(activity_to or "").strip() or None,
            sort=(sort or "").strip() or None,
            owner_scope=(owner_scope or "").strip() or "all",
            owner_user_id=(owner_user_id or "").strip() or None,
            actor_user_id=str(context.get("actor_user_id") or "") or None,
            tag_id=(tag_id or "").strip() or None,
            cursor=(cursor or "").strip() or None,
            include_assessment=company_has_module(company, "assessments"),
            permissions=context.get("permissions") or [],
        ),
    }
""",
    """@app.get("/dashboard/prehire/applications")
def dashboard_prehire_applications(
    status: str | None = None,
    position: str | None = None,
    q: str | None = None,
    cv_status: str | None = None,
    assessment_status: str | None = None,
    interview_status: str | None = None,
    follow_up: str | None = None,
    review_status: str | None = None,
    activity_from: str | None = None,
    activity_to: str | None = None,
    sort: str | None = None,
    owner_scope: str | None = None,
    owner_user_id: str | None = None,
    tag_id: str | None = None,
    cursor: str | None = None,
    view: str | None = None,
    source_channel: str | None = None,
    recruiter_owner: str | None = None,
    cv_processing_state: str | None = None,
    received_from: str | None = None,
    received_to: str | None = None,
    has_grounded_email: str | None = None,
    has_grounded_phone: str | None = None,
    fact_completeness: str | None = None,
    department_intake_tag: str | None = None,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    context: dict[str, Any] = Depends(prehire_dashboard_context),
):
    require_entitlement(context, "pre_hiring", "candidates.read")
    company = context["company_code"]
    search = (q or "").strip() or None
    return {
        "company_code": company,
        **prehire_applications_query(
            company_code=company,
            status=(status or "").strip() or None,
            position=(position or "").strip() or None,
            search=search,
            limit=bounded_limit(limit),
            offset=max(0, int(offset)),
            cv_status=(cv_status or "").strip() or None,
            assessment_status=(assessment_status or "").strip() or None,
            interview_status=(interview_status or "").strip() or None,
            follow_up=(follow_up or "").strip() or None,
            review_status=(review_status or "").strip() or None,
            activity_from=(activity_from or "").strip() or None,
            activity_to=(activity_to or "").strip() or None,
            sort=(sort or "").strip() or None,
            owner_scope=(owner_scope or "").strip() or "all",
            owner_user_id=(owner_user_id or "").strip() or None,
            actor_user_id=str(context.get("actor_user_id") or "") or None,
            tag_id=(tag_id or "").strip() or None,
            cursor=(cursor or "").strip() or None,
            include_assessment=company_has_module(company, "assessments"),
            permissions=context.get("permissions") or [],
            view=(view or "").strip() or None,
            source_channel=(source_channel or "").strip() or None,
            recruiter_owner=(recruiter_owner or "").strip() or None,
            cv_processing_state=(cv_processing_state or "").strip() or None,
            received_from=(received_from or "").strip() or None,
            received_to=(received_to or "").strip() or None,
            has_grounded_email=(has_grounded_email or "").strip() or None,
            has_grounded_phone=(has_grounded_phone or "").strip() or None,
            fact_completeness=(fact_completeness or "").strip() or None,
            department_intake_tag=(department_intake_tag or "").strip() or None,
            include_match_reasons=bool(search),
        ),
    }
""",
    "list_endpoint",
)

# 9) Block ranking evaluation for held rows (always)
src = must_replace(
    src,
    """@app.post("/dashboard/prehire/applications/{app_key}/evaluation")
def dashboard_prehire_application_evaluation(
    app_key: str,
    force: bool = False,
    context: dict[str, Any] = Depends(prehire_dashboard_context),
):
    require_entitlement(context, "pre_hiring", "candidate.manage")
    company = context["company_code"]
    application = dashboard_application_or_404(app_key, company)
    candidate = generate_application_profile_evaluation(app_key, company, force=force)
""",
    """@app.post("/dashboard/prehire/applications/{app_key}/evaluation")
def dashboard_prehire_application_evaluation(
    app_key: str,
    force: bool = False,
    context: dict[str, Any] = Depends(prehire_dashboard_context),
):
    require_entitlement(context, "pre_hiring", "candidate.manage")
    company = context["company_code"]
    application = dashboard_application_or_404(app_key, company)
    if str(application.get("status") or "") in HELD_IMPORT_STATUSES:
        raise HTTPException(
            status_code=409,
            detail={
                "error": "held_record_evaluation_forbidden",
                "message": "Talent Pool held records cannot be ranked or evaluated until linked to a Job.",
            },
        )
    candidate = generate_application_profile_evaluation(app_key, company, force=force)
""",
    "eval_gate",
)

# 10) Block notify/assessment for held rows (HTTP fail-closed; UI already hides)
src = must_replace(
    src,
    """@app.post("/dashboard/prehire/applications/{app_key}/notify")
def dashboard_prehire_notify(
    app_key: str,
    request: DashboardCandidateMessage | None = None,
    context: dict[str, Any] = Depends(prehire_dashboard_context),
):
    require_entitlement(context, "pre_hiring", "candidate.manage")
    company = context["company_code"]
    application = dashboard_application_or_404(app_key, company)
""",
    """@app.post("/dashboard/prehire/applications/{app_key}/notify")
def dashboard_prehire_notify(
    app_key: str,
    request: DashboardCandidateMessage | None = None,
    context: dict[str, Any] = Depends(prehire_dashboard_context),
):
    require_entitlement(context, "pre_hiring", "candidate.manage")
    company = context["company_code"]
    application = dashboard_application_or_404(app_key, company)
    if str(application.get("status") or "") in HELD_IMPORT_STATUSES:
        raise HTTPException(
            status_code=409,
            detail={
                "error": "held_record_outreach_forbidden",
                "message": "Talent Pool held records cannot receive outreach until linked to a Job.",
            },
        )
""",
    "notify_gate",
)

src = must_replace(
    src,
    """@app.post("/dashboard/prehire/applications/{app_key}/assessment")
def dashboard_prehire_assessment(
    app_key: str,
    request: DashboardCandidateMessage | None = None,
    context: dict[str, Any] = Depends(assessments_dashboard_context),
):
    require_entitlement(context, "assessments", "assessment.manage")
    company = context["company_code"]
    application = dashboard_application_or_404(app_key, company)
""",
    """@app.post("/dashboard/prehire/applications/{app_key}/assessment")
def dashboard_prehire_assessment(
    app_key: str,
    request: DashboardCandidateMessage | None = None,
    context: dict[str, Any] = Depends(assessments_dashboard_context),
):
    require_entitlement(context, "assessments", "assessment.manage")
    company = context["company_code"]
    application = dashboard_application_or_404(app_key, company)
    if str(application.get("status") or "") in HELD_IMPORT_STATUSES:
        raise HTTPException(
            status_code=409,
            detail={
                "error": "held_record_assessment_forbidden",
                "message": "Talent Pool held records cannot receive assessments until linked to a Job.",
            },
        )
""",
    "assessment_gate",
)

OUT.write_text(src, encoding="utf-8")
print(f"wrote {OUT} ({OUT.stat().st_size} bytes)")
