"""HTTP registration for Wave 5 C6 HR Intelligence surfaces."""
from __future__ import annotations

from typing import Any

from fastapi import Depends, HTTPException, Response
from pydantic import BaseModel, Field


class QueryBody(BaseModel):
    semantic_key: str = ""
    time_window: dict[str, Any] = Field(default_factory=dict)
    filters: dict[str, Any] = Field(default_factory=dict)
    lang: str = "en"
    actor_role: str | None = None


class OverviewBody(BaseModel):
    time_window: dict[str, Any] = Field(default_factory=dict)
    filters: dict[str, Any] = Field(default_factory=dict)
    lang: str = "en"


class TrendBody(QueryBody):
    bucket: str = "monthly"
    time_buckets: list[dict[str, Any]] | None = None


class CompareBody(BaseModel):
    semantic_key: str
    current_time_window: dict[str, Any] = Field(default_factory=dict)
    prior_time_window: dict[str, Any] | None = None
    current_filters: dict[str, Any] = Field(default_factory=dict)
    comparison_filters: dict[str, Any] | None = None
    mode: str = "prior"
    lang: str = "en"


class SegmentBody(QueryBody):
    dimension: str
    dimension_value: Any


class DrillBody(QueryBody):
    offset: int = 0
    limit: int = 50


class SavedViewBody(BaseModel):
    name_en: str
    name_ar: str | None = None
    mode: str = "live"
    query_config: dict[str, Any] = Field(default_factory=dict)
    layout: dict[str, Any] = Field(default_factory=dict)


class ExportBody(QueryBody):
    person_level: bool = False


class AssistantBody(BaseModel):
    semantic_key: str


def _raise_result(result: dict[str, Any]) -> None:
    error = str(result.get("error") or "hr_intelligence_request_failed")
    if error in {
        "saved_view_not_found",
        "export_not_found",
        "kpi_not_published_for_company",
    }:
        status = 404
    elif error in {
        "hr_intelligence_surfaces_c6_off",
        "hr_intelligence_surfaces_company_not_allowlisted",
        "company_intelligence_surfaces_disabled",
        "c1_registry_required",
        "c1_company_entitlement_required",
        "manager_analytics_disabled",
        "permission_denied",
        "person_level_export_permission_required",
        "payroll_drill_permission_required",
        "talent_drill_permission_required",
    }:
        status = 403
    else:
        status = 422
    raise HTTPException(
        status_code=status,
        detail={
            "error": error,
            "message": result.get("message") or error.replace("_", " ").capitalize(),
            **{
                key: result.get(key)
                for key in ("status", "allowed", "supported_dimensions", "comparable")
                if key in result
            },
        },
    )


def register_hr_intelligence_surfaces_http(app_mod: Any) -> None:
    app = app_mod.app
    dashboard_context = app_mod.dashboard_context
    db_connect = app_mod.db_connect
    json_safe = getattr(app_mod, "json_safe", lambda value: value)
    posthire_context = app_mod._posthire_read_context
    role_key = app_mod.dashboard_context_role_key
    context_permissions = app_mod.context_permissions
    manager_keys = getattr(app_mod, "context_manager_employee_keys", None)

    import hr_intelligence_surfaces_c6 as c6

    prefix = "/dashboard/posthire/intelligence"

    def _identity(context: dict[str, Any]) -> tuple[str, str, str, set[str]]:
        company = posthire_context(context, c6.COMMERCIAL_MODULE_KEY)
        actor = str(context.get("actor_phone") or context.get("hr_phone") or "")
        role = str(role_key(context) or "hr")
        permissions = context_permissions(context, role)
        return company, actor, role, permissions

    def _scoped_filters(
        context: dict[str, Any], company: str, role: str, filters: dict[str, Any] | None
    ) -> dict[str, Any]:
        out = dict(filters or {})
        # Client-provided manager scope is never authoritative.
        out.pop("manager_scope_employee_keys", None)
        if role == "manager":
            keys = manager_keys(context, company) if manager_keys else set()
            out["manager_scope_employee_keys"] = sorted(str(item) for item in (keys or set()))
        return out

    def _run(context: dict[str, Any], callback: Any) -> Any:
        company, actor, role, permissions = _identity(context)
        with db_connect() as conn:
            with conn.cursor() as cur:
                c6.ensure_schema(cur)
                result = callback(cur, company, actor, role, permissions)
            conn.commit()
        if not result.get("ok"):
            _raise_result(result)
        return json_safe(result)

    @app.get(f"{prefix}/bootstrap")
    def intelligence_bootstrap(context: dict[str, Any] = Depends(dashboard_context)):
        return _run(
            context,
            lambda cur, company, actor, _role, _permissions: c6.bootstrap_payload(
                cur, company=company, actor=actor
            ),
        )

    @app.post(f"{prefix}/overview")
    def intelligence_overview(
        body: OverviewBody, context: dict[str, Any] = Depends(dashboard_context)
    ):
        return _run(
            context,
            lambda cur, company, actor, role, _permissions: c6.compose_overview(
                cur,
                company,
                actor,
                body.time_window,
                _scoped_filters(context, company, role, body.filters),
                body.lang,
                actor_role=role,
            ),
        )

    @app.post(f"{prefix}/evaluate")
    def intelligence_evaluate(
        body: QueryBody, context: dict[str, Any] = Depends(dashboard_context)
    ):
        return _run(
            context,
            lambda cur, company, actor, role, _permissions: c6.evaluate_metric(
                cur,
                company=company,
                actor=actor,
                semantic_key=body.semantic_key,
                time_window=body.time_window,
                filters=_scoped_filters(context, company, role, body.filters),
                actor_role=role,
                lang=body.lang,
            ),
        )

    @app.get(f"{prefix}/about/{{semantic_key}}")
    def intelligence_about(
        semantic_key: str, context: dict[str, Any] = Depends(dashboard_context)
    ):
        return _run(
            context,
            lambda cur, company, _actor, _role, _permissions: c6.about_metric(
                cur, semantic_key, company
            ),
        )

    @app.post(f"{prefix}/trend")
    def intelligence_trend(
        body: TrendBody, context: dict[str, Any] = Depends(dashboard_context)
    ):
        return _run(
            context,
            lambda cur, company, actor, role, _permissions: c6.trend_metric(
                cur,
                company=company,
                actor=actor,
                semantic_key=body.semantic_key,
                time_window=body.time_window,
                filters=_scoped_filters(context, company, role, body.filters),
                bucket=body.bucket,
                time_buckets=body.time_buckets,
                actor_role=role,
                lang=body.lang,
            ),
        )

    @app.post(f"{prefix}/compare")
    def intelligence_compare(
        body: CompareBody, context: dict[str, Any] = Depends(dashboard_context)
    ):
        return _run(
            context,
            lambda cur, company, actor, role, _permissions: c6.compare_metric(
                cur,
                company=company,
                actor=actor,
                semantic_key=body.semantic_key,
                current_time_window=body.current_time_window,
                prior_time_window=body.prior_time_window,
                current_filters=_scoped_filters(context, company, role, body.current_filters),
                comparison_filters=(
                    _scoped_filters(context, company, role, body.comparison_filters)
                    if body.comparison_filters is not None
                    else None
                ),
                mode=body.mode,
                actor_role=role,
                lang=body.lang,
            ),
        )

    @app.post(f"{prefix}/segment")
    def intelligence_segment(
        body: SegmentBody, context: dict[str, Any] = Depends(dashboard_context)
    ):
        return _run(
            context,
            lambda cur, company, actor, role, _permissions: c6.segment_metric(
                cur,
                company=company,
                actor=actor,
                semantic_key=body.semantic_key,
                dimension=body.dimension,
                dimension_value=body.dimension_value,
                time_window=body.time_window,
                filters=_scoped_filters(context, company, role, body.filters),
                actor_role=role,
                lang=body.lang,
            ),
        )

    @app.post(f"{prefix}/drill")
    def intelligence_drill(
        body: DrillBody, context: dict[str, Any] = Depends(dashboard_context)
    ):
        return _run(
            context,
            lambda cur, company, actor, role, permissions: c6.drill_population(
                cur,
                company=company,
                actor=actor,
                semantic_key=body.semantic_key,
                time_window=body.time_window,
                filters=_scoped_filters(context, company, role, body.filters),
                actor_role=role,
                has_payroll_permission="payroll.read" in permissions,
                has_talent_permission=bool(
                    {"talent.read", "performance.read"} & permissions
                ),
                offset=body.offset,
                limit=body.limit,
                lang=body.lang,
            ),
        )

    @app.get(f"{prefix}/saved-views")
    def intelligence_saved_views(context: dict[str, Any] = Depends(dashboard_context)):
        return _run(
            context,
            lambda cur, company, actor, _role, _permissions: c6.list_saved_views(
                cur, company=company, owner_phone=actor
            ),
        )

    @app.post(f"{prefix}/saved-views")
    def intelligence_save_view(
        body: SavedViewBody, context: dict[str, Any] = Depends(dashboard_context)
    ):
        return _run(
            context,
            lambda cur, company, actor, role, _permissions: c6.create_saved_view(
                cur,
                company=company,
                owner_phone=actor,
                name_en=body.name_en,
                name_ar=body.name_ar,
                mode=body.mode,
                query_config=body.query_config,
                layout=body.layout,
                actor_role=role,
            ),
        )

    @app.get(f"{prefix}/saved-views/{{view_id}}")
    def intelligence_saved_view(
        view_id: str, context: dict[str, Any] = Depends(dashboard_context)
    ):
        return _run(
            context,
            lambda cur, company, actor, role, _permissions: c6.get_saved_view(
                cur,
                company=company,
                owner_phone=actor,
                view_id=view_id,
                actor_role=role,
            ),
        )

    @app.delete(f"{prefix}/saved-views/{{view_id}}")
    def intelligence_delete_view(
        view_id: str, context: dict[str, Any] = Depends(dashboard_context)
    ):
        return _run(
            context,
            lambda cur, company, actor, _role, _permissions: c6.delete_saved_view(
                cur, company=company, owner_phone=actor, view_id=view_id
            ),
        )

    @app.post(f"{prefix}/exports")
    def intelligence_export(
        body: ExportBody, context: dict[str, Any] = Depends(dashboard_context)
    ):
        return _run(
            context,
            lambda cur, company, actor, role, permissions: c6.create_export_csv(
                cur,
                company=company,
                actor=actor,
                semantic_key=body.semantic_key,
                time_window=body.time_window,
                filters=_scoped_filters(context, company, role, body.filters),
                person_level=body.person_level,
                actor_role=role,
                has_export_person_permission=bool(
                    {"report.export", "analytics.export"} & permissions
                ),
                has_payroll_permission="payroll.read" in permissions,
                has_talent_permission=bool(
                    {"talent.read", "performance.read"} & permissions
                ),
                lang=body.lang,
            ),
        )

    @app.get(f"{prefix}/exports/{{export_id}}")
    def intelligence_export_job(
        export_id: str, context: dict[str, Any] = Depends(dashboard_context)
    ):
        return _run(
            context,
            lambda cur, company, actor, _role, _permissions: c6.get_export(
                cur, company=company, actor=actor, export_id=export_id
            ),
        )

    @app.get(f"{prefix}/exports/{{export_id}}/download")
    def intelligence_export_download(
        export_id: str, context: dict[str, Any] = Depends(dashboard_context)
    ):
        company, actor, _role, _permissions = _identity(context)
        with db_connect() as conn:
            with conn.cursor() as cur:
                c6.ensure_schema(cur)
                result = c6.get_export(
                    cur,
                    company=company,
                    actor=actor,
                    export_id=export_id,
                    include_csv=True,
                )
            conn.commit()
        if not result.get("ok"):
            _raise_result(result)
        text = str((result.get("export") or {}).get("csv_text") or "")
        return Response(
            content=text,
            media_type="text/csv; charset=utf-8",
            headers={
                "Content-Disposition": f'attachment; filename="hr-intelligence-{export_id}.csv"',
                "X-Content-Type-Options": "nosniff",
            },
        )

    @app.post(f"{prefix}/assistant/query")
    def intelligence_assistant(
        body: AssistantBody, context: dict[str, Any] = Depends(dashboard_context)
    ):
        return _run(
            context,
            lambda cur, company, actor, _role, _permissions: c6.assistant_query_metric(
                cur, company=company, actor=actor, semantic_key=body.semantic_key
            ),
        )

