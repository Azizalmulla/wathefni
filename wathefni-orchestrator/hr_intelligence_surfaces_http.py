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


def _enabled_modules(cur: Any, company: str) -> dict[str, bool]:
    cur.execute(
        "SELECT module_key, enabled FROM company_modules WHERE company_code=%s",
        (company,),
    )
    return {str(row["module_key"]): bool(row["enabled"]) for row in (cur.fetchall() or [])}


def _module_on(enabled: dict[str, bool], key: str) -> bool:
    return bool(enabled.get(key))


def sync_source_module_flags(cur: Any, *, company: str, actor: str) -> dict[str, Any]:
    """Keep C3–C5 composition flags aligned with live company_modules.

    Does not change KPI math. Disabled source modules stay unavailable, not zero.
    """
    enabled = _enabled_modules(cur, company)
    changed: list[str] = []
    reason = "sync_composition_from_company_modules"

    def _maybe(slice_name: str, entitled: dict[str, Any], current: dict[str, Any], desired: dict[str, bool], setter: Any) -> None:
        if not entitled.get("ok"):
            return
        settings = entitled.get("settings") or {}
        if any(bool(settings.get(key)) != bool(value) for key, value in desired.items()):
            setter(cur, company_code=company, actor_phone=actor, reason=reason, **desired)
            changed.append(slice_name)

    try:
        import hr_intelligence_recruiting_c3 as c3

        _maybe(
            "c3",
            c3._entitled(cur, company),
            {},
            {
                "recruiting_module_enabled": _module_on(enabled, "pre_hiring"),
                "preboarding_module_enabled": _module_on(enabled, "preboarding"),
                "onboarding_module_enabled": _module_on(enabled, "onboarding"),
                "probation_module_enabled": _module_on(enabled, "probation"),
            },
            c3.set_module_flags,
        )
    except Exception:
        pass
    try:
        import hr_intelligence_time_pay_c4 as c4

        _maybe(
            "c4",
            c4._entitled(cur, company),
            {},
            {
                "attendance_module_enabled": _module_on(enabled, "attendance"),
                "leave_module_enabled": _module_on(enabled, "leave"),
                "shifts_module_enabled": _module_on(enabled, "shifts"),
                "ot_module_enabled": _module_on(enabled, "attendance"),
                "payroll_module_enabled": _module_on(enabled, "payroll"),
            },
            c4.set_module_flags,
        )
    except Exception:
        pass
    try:
        import hr_intelligence_perf_talent_c5 as c5

        perf_on = _module_on(enabled, "performance")
        talent_on = _module_on(enabled, "talent")
        _maybe(
            "c5",
            c5._entitled(cur, company),
            {},
            {
                "goals_module_enabled": perf_on,
                "reviews_module_enabled": perf_on,
                "calibration_module_enabled": perf_on,
                "feedback_module_enabled": perf_on,
                "talent_profile_module_enabled": talent_on,
                "succession_module_enabled": talent_on,
                "hipo_module_enabled": talent_on,
                "nine_box_module_enabled": False,
            },
            c5.set_module_flags,
        )
    except Exception:
        pass
    return {"ok": True, "changed": changed, "enabled_modules": sorted(k for k, v in enabled.items() if v)}


def permission_for_semantic_key(semantic_key: str) -> set[str]:
    key = str(semantic_key or "").strip().lower()
    if key.startswith("talent."):
        return {"talent.read"}
    if key.startswith("payroll."):
        return {"payroll.read"}
    if key.startswith("performance."):
        return {"performance.read"}
    if key.startswith("leave."):
        return {"leave.read"}
    if key.startswith("shifts."):
        return {"shifts.read"}
    if key.startswith(("time.", "overtime.")):
        return {"attendance.read"}
    if key.startswith(("recruiting.", "hire_ready.")):
        return {"analytics.read"}
    return {"analytics.read"}


def actor_may_read_metric(semantic_key: str, permissions: set[str]) -> bool:
    required = permission_for_semantic_key(semantic_key)
    return bool(required & set(permissions or set()))


def _filter_published(items: list[dict[str, Any]] | None, permissions: set[str]) -> list[dict[str, Any]]:
    return [item for item in (items or []) if actor_may_read_metric(str(item.get("semantic_key") or ""), permissions)]


def _filter_overview(result: dict[str, Any], permissions: set[str]) -> dict[str, Any]:
    families = []
    omitted = list(result.get("omitted") or [])
    for family in result.get("families") or []:
        kept = []
        for metric in family.get("metrics") or []:
            key = str(metric.get("semantic_key") or "")
            if actor_may_read_metric(key, permissions):
                kept.append(metric)
            else:
                omitted.append({"semantic_key": key, "status": "blocked", "error": "permission_denied"})
        if kept:
            families.append({**family, "metrics": kept})
    return {**result, "families": families, "omitted": omitted, "omitted_count": len(omitted)}


def _permission_denied(semantic_key: str) -> dict[str, Any]:
    return {
        "ok": False,
        "error": "permission_denied",
        "status": "blocked",
        "semantic_key": semantic_key,
        "message": "Canonical permission required for this intelligence metric.",
    }


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
                try:
                    import hr_intelligence_projection as proj

                    proj.ensure_hr_intelligence_projection_schema(cur)
                except Exception:
                    pass
                sync_source_module_flags(cur, company=company, actor=actor)
                result = callback(cur, company, actor, role, permissions)
            conn.commit()
        if not result.get("ok"):
            _raise_result(result)
        return json_safe(result)

    @app.get(f"{prefix}/bootstrap")
    def intelligence_bootstrap(context: dict[str, Any] = Depends(dashboard_context)):
        def _boot(cur, company, actor, _role, permissions):
            payload = c6.bootstrap_payload(cur, company=company, actor=actor)
            if payload.get("ok"):
                payload["published_kpis"] = _filter_published(payload.get("published_kpis"), permissions)
                payload["composition"] = {
                    "from_company_modules": True,
                    "from_canonical_permissions": True,
                }
            return payload

        return _run(context, _boot)

    @app.post(f"{prefix}/overview")
    def intelligence_overview(
        body: OverviewBody, context: dict[str, Any] = Depends(dashboard_context)
    ):
        def _overview(cur, company, actor, role, permissions):
            payload = c6.compose_overview(
                cur,
                company,
                actor,
                body.time_window,
                _scoped_filters(context, company, role, body.filters),
                body.lang,
                actor_role=role,
            )
            if payload.get("ok"):
                payload = _filter_overview(payload, permissions)
            return payload

        return _run(context, _overview)

    @app.post(f"{prefix}/evaluate")
    def intelligence_evaluate(
        body: QueryBody, context: dict[str, Any] = Depends(dashboard_context)
    ):
        def _evaluate(cur, company, actor, role, permissions):
            if not actor_may_read_metric(body.semantic_key, permissions):
                return _permission_denied(body.semantic_key)
            return c6.evaluate_metric(
                cur,
                company=company,
                actor=actor,
                semantic_key=body.semantic_key,
                time_window=body.time_window,
                filters=_scoped_filters(context, company, role, body.filters),
                actor_role=role,
                lang=body.lang,
                has_permission=True,
            )

        return _run(context, _evaluate)

    @app.get(f"{prefix}/about/{{semantic_key}}")
    def intelligence_about(
        semantic_key: str, context: dict[str, Any] = Depends(dashboard_context)
    ):
        def _about(cur, company, _actor, _role, permissions):
            if not actor_may_read_metric(semantic_key, permissions):
                return _permission_denied(semantic_key)
            return c6.about_metric(cur, semantic_key, company)

        return _run(context, _about)

    @app.post(f"{prefix}/trend")
    def intelligence_trend(
        body: TrendBody, context: dict[str, Any] = Depends(dashboard_context)
    ):
        def _trend(cur, company, actor, role, permissions):
            if not actor_may_read_metric(body.semantic_key, permissions):
                return _permission_denied(body.semantic_key)
            return c6.trend_metric(
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
            )

        return _run(context, _trend)

    @app.post(f"{prefix}/compare")
    def intelligence_compare(
        body: CompareBody, context: dict[str, Any] = Depends(dashboard_context)
    ):
        def _compare(cur, company, actor, role, permissions):
            if not actor_may_read_metric(body.semantic_key, permissions):
                return _permission_denied(body.semantic_key)
            return c6.compare_metric(
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
            )

        return _run(context, _compare)

    @app.post(f"{prefix}/segment")
    def intelligence_segment(
        body: SegmentBody, context: dict[str, Any] = Depends(dashboard_context)
    ):
        def _segment(cur, company, actor, role, permissions):
            if not actor_may_read_metric(body.semantic_key, permissions):
                return _permission_denied(body.semantic_key)
            return c6.segment_metric(
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
            )

        return _run(context, _segment)

    @app.post(f"{prefix}/drill")
    def intelligence_drill(
        body: DrillBody, context: dict[str, Any] = Depends(dashboard_context)
    ):
        def _drill(cur, company, actor, role, permissions):
            if not actor_may_read_metric(body.semantic_key, permissions):
                return _permission_denied(body.semantic_key)
            return c6.drill_population(
                cur,
                company=company,
                actor=actor,
                semantic_key=body.semantic_key,
                time_window=body.time_window,
                filters=_scoped_filters(context, company, role, body.filters),
                actor_role=role,
                has_payroll_permission="payroll.read" in permissions,
                has_talent_permission=bool({"talent.read", "performance.read"} & permissions),
                offset=body.offset,
                limit=body.limit,
                lang=body.lang,
            )

        return _run(context, _drill)

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
        def _save(cur, company, actor, role, _permissions):
            try:
                return c6.create_saved_view(
                    cur,
                    company=company,
                    owner_phone=actor,
                    name_en=body.name_en,
                    name_ar=body.name_ar,
                    mode=body.mode,
                    query_config=body.query_config,
                    layout=body.layout,
                    actor_role=role,
                )
            except Exception as exc:
                if "UniqueViolation" in type(exc).__name__ or "duplicate key" in str(exc).lower():
                    return {
                        "ok": False,
                        "error": "saved_view_name_exists",
                        "message": "A saved view with this name already exists.",
                    }
                raise

        return _run(context, _save)

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
        def _export(cur, company, actor, role, permissions):
            if not actor_may_read_metric(body.semantic_key, permissions):
                return _permission_denied(body.semantic_key)
            return c6.create_export_csv(
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
            )

        return _run(context, _export)

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
        def _assistant(cur, company, actor, _role, permissions):
            if body.semantic_key and not actor_may_read_metric(body.semantic_key, permissions):
                return _permission_denied(body.semantic_key)
            return c6.assistant_query_metric(
                cur, company=company, actor=actor, semantic_key=body.semantic_key
            )

        return _run(context, _assistant)

