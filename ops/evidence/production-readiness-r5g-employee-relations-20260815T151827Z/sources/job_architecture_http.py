#!/usr/bin/env python3
"""HTTP adapters for Job Architecture (R5D) — thin wrappers over frozen C1.

Namespace: /dashboard/job-architecture/...

Company and actor identity come from authenticated dashboard context only.
JA Job Profile ≠ Recruiting Job ≠ Requisition.
"""
from __future__ import annotations

from typing import Any

from fastapi import Depends, HTTPException
from pydantic import BaseModel

import job_architecture_c1 as c1
import job_architecture_surfaces as surfaces

PREFIX = "/dashboard/job-architecture"


class ReasonBody(BaseModel):
    reason: str = "job architecture action"


class FamilyBody(BaseModel):
    code: str
    name_en: str
    name_ar: str
    status: str = "draft"
    description_en: str = ""
    description_ar: str = ""
    reason: str = "upsert family"


class FunctionBody(BaseModel):
    family_id: str
    code: str
    name_en: str
    name_ar: str
    status: str = "draft"
    reason: str = "upsert function"


class GradeBody(BaseModel):
    code: str
    name_en: str
    name_ar: str
    rank_order: int = 0
    status: str = "draft"
    reason: str = "upsert grade"


class LevelBody(BaseModel):
    code: str
    name_en: str
    name_ar: str
    grade_id: str | None = None
    rank_order: int = 0
    status: str = "draft"
    reason: str = "upsert level"


class ProfileBody(BaseModel):
    function_id: str
    code: str
    name_en: str
    name_ar: str
    status: str = "draft"
    default_grade_id: str | None = None
    default_level_id: str | None = None
    description_en: str = ""
    description_ar: str = ""
    reason: str = "upsert profile"


class EdgeBody(BaseModel):
    edge_type: str
    from_profile_id: str | None = None
    to_profile_id: str | None = None
    from_grade_id: str | None = None
    to_grade_id: str | None = None
    optional_requirements: dict[str, Any] | None = None
    status: str = "published"
    notes_en: str = ""
    notes_ar: str = ""
    reason: str = "create career edge"


class AssignBody(BaseModel):
    employee_key: str
    effective_start: str
    profile_id: str | None = None
    grade_id: str | None = None
    level_id: str | None = None
    employment_period_key: str | None = None
    reason: str = "assign architecture"


class PositionLinkBody(BaseModel):
    org_position_ref: str
    profile_id: str
    effective_start: str
    reason: str = "link org position"


class MigrateBody(BaseModel):
    raw_field: str
    candidates: list[dict[str, Any]]
    reason: str = "migrate legacy values"


class ResolveMappingBody(BaseModel):
    mapped_entity_type: str
    mapped_entity_id: str
    reason: str = "human resolve mapping"


class ExternalRefBody(BaseModel):
    domain: str
    external_key: str
    profile_id: str | None = None
    grade_id: str | None = None
    note: str = ""


_GATE_ERRORS = {
    "job_architecture_c1_off",
    "job_architecture_company_not_allowlisted",
    "job_architecture_disabled_for_company",
    "company_required",
}
_NOT_FOUND = {"mapping_not_found", "profile_not_found"}
_FORBIDDEN = {
    "permission_denied",
    "eligibility_scoring_forbidden",
    "destructive_delete_forbidden",
}


def _raise_gate(result: dict[str, Any]) -> None:
    err = str(result.get("error") or "job_architecture_denied")
    if err in _GATE_ERRORS or err.endswith("_not_allowlisted") or err.endswith("_disabled_for_company"):
        raise HTTPException(
            status_code=403,
            detail={"error": err, "message": "Job Architecture is not available for this company.", "gate": result.get("gate")},
        )
    if err in _NOT_FOUND or err.endswith("_not_found"):
        raise HTTPException(status_code=404, detail={"error": err, "message": "Not found."})
    if err in _FORBIDDEN:
        raise HTTPException(status_code=403, detail={"error": err, "message": "Not permitted."})
    raise HTTPException(status_code=422, detail={"error": err, "message": result.get("message") or err})


def register_job_architecture_http(app_mod: Any) -> None:
    app = app_mod.app
    dashboard_context = app_mod.dashboard_context
    db_connect = app_mod.db_connect
    json_safe = app_mod.json_safe
    context_permissions = app_mod.context_permissions
    dashboard_context_role_key = app_mod.dashboard_context_role_key

    def _perms(context: dict[str, Any]) -> set[str]:
        return set(context_permissions(context, dashboard_context_role_key(context)) or [])

    def _role(context: dict[str, Any]) -> str:
        return str(context.get("actor_role") or dashboard_context_role_key(context) or "").strip().lower()

    def _company(context: dict[str, Any], *, write: bool = False, mapping: bool = False, publish: bool = False) -> str:
        company = str(context.get("company_code") or "").strip().upper()
        if not company:
            raise HTTPException(status_code=401, detail={"error": "dashboard_company_required"})
        if not context.get("actor_user_id"):
            raise HTTPException(status_code=401, detail={"error": "dashboard_user_identity_required"})
        perms = _perms(context)
        if "job_architecture.read" not in perms:
            raise HTTPException(status_code=403, detail={"error": "permission_denied", "message": "Not permitted."})
        if write and "job_architecture.manage" not in perms:
            raise HTTPException(status_code=403, detail={"error": "permission_denied", "message": "Authoring is not permitted."})
        if mapping and "job_architecture.mapping" not in perms:
            raise HTTPException(status_code=403, detail={"error": "permission_denied", "message": "Mapping is not permitted."})
        if publish and "job_architecture.publish" not in perms and "job_architecture.manage" not in perms:
            raise HTTPException(status_code=403, detail={"error": "permission_denied", "message": "Publish is not permitted."})
        gate = c1.runtime_gate_for_company(company)
        if not gate.get("ok"):
            _raise_gate(gate)
        return company

    def _run(callback: Any) -> Any:
        with db_connect() as conn:
            with conn.cursor() as cur:
                surfaces.ensure_schema(cur)
                result = callback(cur)
            conn.commit()
        if isinstance(result, dict) and result.get("ok") is False:
            _raise_gate(result)
        return json_safe(result)

    def dashboard_workspace(context: dict[str, Any] = Depends(dashboard_context)):
        company = _company(context)
        return _run(lambda cur: surfaces.workspace_summary(cur, company_code=company))

    def dashboard_catalog(context: dict[str, Any] = Depends(dashboard_context)):
        company = _company(context)
        return _run(lambda cur: surfaces.list_catalog(cur, company_code=company))

    def _catalog_slice(company: str, key: str) -> Any:
        def _inner(cur: Any) -> dict[str, Any]:
            catalog = surfaces.list_catalog(cur, company_code=company)
            if catalog.get("ok") is False:
                return catalog
            return {
                **catalog,
                key: catalog.get(key) or [],
                "slice": key,
            }

        return _inner

    def dashboard_families_get(context: dict[str, Any] = Depends(dashboard_context)):
        company = _company(context)
        return _run(_catalog_slice(company, "families"))

    def dashboard_functions_get(context: dict[str, Any] = Depends(dashboard_context)):
        company = _company(context)
        return _run(_catalog_slice(company, "functions"))

    def dashboard_grades_get(context: dict[str, Any] = Depends(dashboard_context)):
        company = _company(context)
        return _run(_catalog_slice(company, "grades"))

    def dashboard_levels_get(context: dict[str, Any] = Depends(dashboard_context)):
        company = _company(context)
        return _run(_catalog_slice(company, "levels"))

    def dashboard_profiles_get(context: dict[str, Any] = Depends(dashboard_context)):
        company = _company(context)
        return _run(_catalog_slice(company, "profiles"))

    def dashboard_edges_get(context: dict[str, Any] = Depends(dashboard_context)):
        company = _company(context)
        return _run(_catalog_slice(company, "career_edges"))

    def dashboard_families(body: FamilyBody, context: dict[str, Any] = Depends(dashboard_context)):
        company = _company(context, write=True, publish=body.status == "published")
        return _run(
            lambda cur: c1.upsert_job_family(
                cur,
                company_code=company,
                actor_phone=str(context.get("actor_phone") or ""),
                code=body.code,
                name_en=body.name_en,
                name_ar=body.name_ar,
                status=body.status,
                description_en=body.description_en,
                description_ar=body.description_ar,
                reason=body.reason,
            )
        )

    def dashboard_functions(body: FunctionBody, context: dict[str, Any] = Depends(dashboard_context)):
        company = _company(context, write=True, publish=body.status == "published")
        return _run(
            lambda cur: c1.upsert_job_function(
                cur,
                company_code=company,
                actor_phone=str(context.get("actor_phone") or ""),
                family_id=body.family_id,
                code=body.code,
                name_en=body.name_en,
                name_ar=body.name_ar,
                status=body.status,
                reason=body.reason,
            )
        )

    def dashboard_grades(body: GradeBody, context: dict[str, Any] = Depends(dashboard_context)):
        company = _company(context, write=True, publish=body.status == "published")
        return _run(
            lambda cur: c1.upsert_grade(
                cur,
                company_code=company,
                actor_phone=str(context.get("actor_phone") or ""),
                code=body.code,
                name_en=body.name_en,
                name_ar=body.name_ar,
                rank_order=body.rank_order,
                status=body.status,
                reason=body.reason,
            )
        )

    def dashboard_levels(body: LevelBody, context: dict[str, Any] = Depends(dashboard_context)):
        company = _company(context, write=True, publish=body.status == "published")
        return _run(
            lambda cur: c1.upsert_level(
                cur,
                company_code=company,
                actor_phone=str(context.get("actor_phone") or ""),
                code=body.code,
                name_en=body.name_en,
                name_ar=body.name_ar,
                grade_id=body.grade_id,
                rank_order=body.rank_order,
                status=body.status,
                reason=body.reason,
            )
        )

    def dashboard_profiles(body: ProfileBody, context: dict[str, Any] = Depends(dashboard_context)):
        company = _company(context, write=True, publish=body.status == "published")
        return _run(
            lambda cur: c1.upsert_job_profile(
                cur,
                company_code=company,
                actor_phone=str(context.get("actor_phone") or ""),
                function_id=body.function_id,
                code=body.code,
                name_en=body.name_en,
                name_ar=body.name_ar,
                status=body.status,
                default_grade_id=body.default_grade_id,
                default_level_id=body.default_level_id,
                description_en=body.description_en,
                description_ar=body.description_ar,
                reason=body.reason,
            )
        )

    def dashboard_edges(body: EdgeBody, context: dict[str, Any] = Depends(dashboard_context)):
        company = _company(context, write=True)
        return _run(
            lambda cur: c1.create_career_edge(
                cur,
                company_code=company,
                actor_phone=str(context.get("actor_phone") or ""),
                edge_type=body.edge_type,
                from_profile_id=body.from_profile_id,
                to_profile_id=body.to_profile_id,
                from_grade_id=body.from_grade_id,
                to_grade_id=body.to_grade_id,
                optional_requirements=body.optional_requirements,
                status=body.status,
                notes_en=body.notes_en,
                notes_ar=body.notes_ar,
                reason=body.reason,
            )
        )

    def dashboard_assign(body: AssignBody, context: dict[str, Any] = Depends(dashboard_context)):
        company = _company(context, mapping=True)
        return _run(
            lambda cur: c1.assign_employment_architecture(
                cur,
                company_code=company,
                actor_phone=str(context.get("actor_phone") or ""),
                employee_key=body.employee_key,
                effective_start=body.effective_start,
                profile_id=body.profile_id,
                grade_id=body.grade_id,
                level_id=body.level_id,
                employment_period_key=body.employment_period_key,
                reason=body.reason,
            )
        )

    def dashboard_assignments(employee_key: str | None = None, context: dict[str, Any] = Depends(dashboard_context)):
        company = _company(context)
        return _run(lambda cur: surfaces.list_assignments(cur, company_code=company, employee_key=employee_key))

    def dashboard_position_link(body: PositionLinkBody, context: dict[str, Any] = Depends(dashboard_context)):
        company = _company(context, mapping=True)
        return _run(
            lambda cur: c1.link_org_position(
                cur,
                company_code=company,
                actor_phone=str(context.get("actor_phone") or ""),
                org_position_ref=body.org_position_ref,
                profile_id=body.profile_id,
                effective_start=body.effective_start,
                reason=body.reason,
            )
        )

    def dashboard_migrate(body: MigrateBody, context: dict[str, Any] = Depends(dashboard_context)):
        company = _company(context, mapping=True)
        return _run(
            lambda cur: c1.migrate_legacy_values(
                cur,
                company_code=company,
                actor_phone=str(context.get("actor_phone") or ""),
                raw_field=body.raw_field,
                candidates=body.candidates,
            )
        )

    def dashboard_mappings(match_kind: str | None = None, context: dict[str, Any] = Depends(dashboard_context)):
        company = _company(context)
        return _run(lambda cur: surfaces.list_mappings(cur, company_code=company, match_kind=match_kind))

    def dashboard_resolve(mapping_id: str, body: ResolveMappingBody, context: dict[str, Any] = Depends(dashboard_context)):
        company = _company(context, mapping=True)
        return _run(
            lambda cur: surfaces.resolve_legacy_mapping(
                cur,
                company_code=company,
                actor_phone=str(context.get("actor_phone") or ""),
                mapping_id=mapping_id,
                mapped_entity_type=body.mapped_entity_type,
                mapped_entity_id=body.mapped_entity_id,
                reason=body.reason,
            )
        )

    def dashboard_history(entity_type: str | None = None, context: dict[str, Any] = Depends(dashboard_context)):
        company = _company(context)
        return _run(lambda cur: surfaces.list_history(cur, company_code=company, entity_type=entity_type))

    def dashboard_refs(context: dict[str, Any] = Depends(dashboard_context)):
        company = _company(context)
        return _run(lambda cur: surfaces.list_downstream_refs(cur, company_code=company))

    def dashboard_external_ref(body: ExternalRefBody, context: dict[str, Any] = Depends(dashboard_context)):
        company = _company(context, mapping=True)
        return _run(
            lambda cur: c1.optional_external_ref(
                cur,
                company_code=company,
                actor_phone=str(context.get("actor_phone") or ""),
                domain=body.domain,
                external_key=body.external_key,
                profile_id=body.profile_id,
                grade_id=body.grade_id,
                note=body.note,
            )
        )

    def dashboard_refuse_delete(entity_type: str, context: dict[str, Any] = Depends(dashboard_context)):
        _company(context, write=True)
        refused = surfaces.refuse_hard_delete(entity_type=entity_type)
        raise HTTPException(status_code=403, detail=refused)

    app.add_api_route(PREFIX + "/workspace", dashboard_workspace, methods=["GET"])
    app.add_api_route(PREFIX + "/catalog", dashboard_catalog, methods=["GET"])
    app.add_api_route(PREFIX + "/families", dashboard_families_get, methods=["GET"])
    app.add_api_route(PREFIX + "/families", dashboard_families, methods=["POST"])
    app.add_api_route(PREFIX + "/functions", dashboard_functions_get, methods=["GET"])
    app.add_api_route(PREFIX + "/functions", dashboard_functions, methods=["POST"])
    app.add_api_route(PREFIX + "/grades", dashboard_grades_get, methods=["GET"])
    app.add_api_route(PREFIX + "/grades", dashboard_grades, methods=["POST"])
    app.add_api_route(PREFIX + "/levels", dashboard_levels_get, methods=["GET"])
    app.add_api_route(PREFIX + "/levels", dashboard_levels, methods=["POST"])
    app.add_api_route(PREFIX + "/profiles", dashboard_profiles_get, methods=["GET"])
    app.add_api_route(PREFIX + "/profiles", dashboard_profiles, methods=["POST"])
    app.add_api_route(PREFIX + "/career-edges", dashboard_edges_get, methods=["GET"])
    app.add_api_route(PREFIX + "/career-edges", dashboard_edges, methods=["POST"])
    app.add_api_route(PREFIX + "/assignments", dashboard_assign, methods=["POST"])
    app.add_api_route(PREFIX + "/assignments", dashboard_assignments, methods=["GET"])
    app.add_api_route(PREFIX + "/positions", dashboard_position_link, methods=["POST"])
    app.add_api_route(PREFIX + "/mappings/migrate", dashboard_migrate, methods=["POST"])
    app.add_api_route(PREFIX + "/mappings", dashboard_mappings, methods=["GET"])
    app.add_api_route(PREFIX + "/mappings/{mapping_id}/resolve", dashboard_resolve, methods=["POST"])
    app.add_api_route(PREFIX + "/history", dashboard_history, methods=["GET"])
    app.add_api_route(PREFIX + "/refs", dashboard_refs, methods=["GET"])
    app.add_api_route(PREFIX + "/refs", dashboard_external_ref, methods=["POST"])
    app.add_api_route(PREFIX + "/{entity_type}", dashboard_refuse_delete, methods=["DELETE"])
