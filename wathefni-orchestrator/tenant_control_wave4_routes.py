"""Wave 4 Super Admin wizard, control page, cutover, and lifecycle APIs."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

import tenant_control_lifecycle as tc_lifecycle
import tenant_control_runtime as tc_runtime
import tenant_control_wizard as tc_wizard


router = APIRouter(prefix="/dashboard/superadmin/setup", tags=["tenant-control-wave4"])


class WizardCreateRequest(BaseModel):
    company_code: str | None = None
    synthetic: bool = False
    locale: str = "en"
    idempotency_key: str | None = None


class WizardSaveRequest(BaseModel):
    patch: dict[str, Any] = Field(default_factory=dict)
    current_step: int | None = None


class ImpactPreviewRequest(BaseModel):
    action: str
    module_key: str | None = None


class CutoverRequest(BaseModel):
    boundary_key: str
    canary_token: str


class ImportBatchRequest(BaseModel):
    import_kind: str
    mapping: dict[str, Any] = Field(default_factory=dict)
    rows: list[dict[str, Any]] = Field(default_factory=list)
    dry_run: bool = True


class ModuleLifecycleRequest(BaseModel):
    action: str  # pause|resume|activate
    reason: str = ""
    canary_token: str | None = None


def register_wave4_routes(app: Any, *, superadmin_dependency: Any, db_connect: Any) -> None:
    def _actor(superadmin: dict[str, Any]) -> str:
        return str((superadmin or {}).get("email") or (superadmin or {}).get("actor_phone") or "superadmin")

    @router.get("/wizard/steps")
    def wizard_steps(locale: str = "en", superadmin: dict[str, Any] = Depends(superadmin_dependency)):
        _ = superadmin
        return {"ok": True, "steps": tc_wizard.wizard_steps(locale=locale), "purchasable_modules": tc_wizard.purchasable_modules()}

    @router.post("/wizard/drafts")
    def create_wizard_draft(request: WizardCreateRequest, superadmin: dict[str, Any] = Depends(superadmin_dependency)):
        with db_connect() as conn:
            with conn.cursor() as cur:
                result = tc_wizard.create_or_resume_draft(
                    cur,
                    actor=_actor(superadmin),
                    company_code=request.company_code,
                    synthetic=request.synthetic,
                    locale=request.locale,
                    idempotency_key=request.idempotency_key,
                )
            conn.commit()
        if not result.get("ok"):
            raise HTTPException(status_code=422, detail=result)
        return result

    @router.get("/wizard/drafts/{draft_id}")
    def get_wizard_draft(draft_id: str, superadmin: dict[str, Any] = Depends(superadmin_dependency)):
        _ = superadmin
        with db_connect() as conn:
            with conn.cursor() as cur:
                tc_wizard.ensure_schema(cur)
                draft = tc_wizard.get_draft(cur, draft_id=draft_id)
            conn.commit()
        if not draft:
            raise HTTPException(status_code=404, detail={"error": "draft_not_found"})
        return {"ok": True, "draft": draft, "steps": tc_wizard.wizard_steps(locale=draft.get("locale") or "en")}

    @router.patch("/wizard/drafts/{draft_id}")
    def save_wizard_draft(
        draft_id: str,
        request: WizardSaveRequest,
        superadmin: dict[str, Any] = Depends(superadmin_dependency),
    ):
        with db_connect() as conn:
            with conn.cursor() as cur:
                result = tc_wizard.autosave_draft(
                    cur,
                    draft_id=draft_id,
                    patch=request.patch,
                    current_step=request.current_step,
                    actor=_actor(superadmin),
                )
            conn.commit()
        if not result.get("ok"):
            raise HTTPException(status_code=422, detail=result)
        return result

    @router.post("/wizard/drafts/{draft_id}/validate/{step}")
    def validate_wizard_step(
        draft_id: str,
        step: int,
        superadmin: dict[str, Any] = Depends(superadmin_dependency),
    ):
        _ = superadmin
        with db_connect() as conn:
            with conn.cursor() as cur:
                result = tc_wizard.validate_step(cur, draft_id=draft_id, step=step)
            conn.commit()
        return result

    @router.get("/companies/{company_code}/control")
    def company_control(company_code: str, superadmin: dict[str, Any] = Depends(superadmin_dependency)):
        _ = superadmin
        with db_connect() as conn:
            with conn.cursor() as cur:
                result = tc_wizard.control_page_snapshot(cur, company_code=company_code.upper())
            conn.commit()
        if not result.get("ok"):
            raise HTTPException(status_code=404, detail=result)
        return result

    @router.post("/companies/{company_code}/impact-preview")
    def impact_preview(
        company_code: str,
        request: ImpactPreviewRequest,
        superadmin: dict[str, Any] = Depends(superadmin_dependency),
    ):
        with db_connect() as conn:
            with conn.cursor() as cur:
                result = tc_wizard.impact_preview(
                    cur,
                    company_code=company_code.upper(),
                    action=request.action,
                    module_key=request.module_key,
                    actor=_actor(superadmin),
                )
            conn.commit()
        return result

    @router.post("/companies/{company_code}/modules/{module_key}/lifecycle")
    def module_lifecycle(
        company_code: str,
        module_key: str,
        request: ModuleLifecycleRequest,
        superadmin: dict[str, Any] = Depends(superadmin_dependency),
    ):
        company = company_code.upper()
        with db_connect() as conn:
            with conn.cursor() as cur:
                preview = tc_wizard.impact_preview(
                    cur,
                    company_code=company,
                    action=request.action,
                    module_key=module_key,
                    actor=_actor(superadmin),
                )
                if request.action == "pause":
                    result = tc_lifecycle.pause_module(
                        cur,
                        company_code=company,
                        module_key=module_key,
                        actor=_actor(superadmin),
                        reason=request.reason or "operator_pause",
                    )
                elif request.action == "resume":
                    result = tc_lifecycle.resume_module(
                        cur,
                        company_code=company,
                        module_key=module_key,
                        actor=_actor(superadmin),
                        reason=request.reason or "operator_resume",
                    )
                elif request.action == "activate":
                    # Activation requires readiness; selecting alone never activates.
                    import tenant_control_readiness as tc_ready

                    ready = tc_ready.evaluate_readiness(cur, company_code=company, module_key=module_key)
                    if not ready.get("ready"):
                        result = {"ok": False, "error": "readiness_incomplete", "readiness": ready}
                    else:
                        result = tc_lifecycle.resume_module(
                            cur,
                            company_code=company,
                            module_key=module_key,
                            actor=_actor(superadmin),
                            reason="operator_activate",
                        )
                        result["activated"] = True
                else:
                    result = {"ok": False, "error": "unknown_action"}
            conn.commit()
        if not result.get("ok"):
            raise HTTPException(status_code=422, detail={**result, "impact_preview": preview})
        return {**result, "impact_preview": preview}

    @router.get("/companies/{company_code}/cutover")
    def list_cutover(company_code: str, superadmin: dict[str, Any] = Depends(superadmin_dependency)):
        _ = superadmin
        with db_connect() as conn:
            with conn.cursor() as cur:
                tc_runtime.ensure_schema(cur)
                rows = tc_runtime.list_cutovers(cur, company_code=company_code.upper())
                boundaries = list(tc_runtime.CUTOVER_BOUNDARIES)
            conn.commit()
        return {"ok": True, "boundaries": boundaries, "cutovers": rows, "global_canonical": False}

    @router.post("/companies/{company_code}/cutover/parity/{boundary_key}")
    def cutover_parity(
        company_code: str,
        boundary_key: str,
        superadmin: dict[str, Any] = Depends(superadmin_dependency),
    ):
        _ = superadmin
        with db_connect() as conn:
            with conn.cursor() as cur:
                result = tc_runtime.parity_for_boundary(
                    cur, company_code=company_code.upper(), boundary_key=boundary_key
                )
            conn.commit()
        return result

    @router.post("/companies/{company_code}/cutover/activate")
    def cutover_activate(
        company_code: str,
        request: CutoverRequest,
        superadmin: dict[str, Any] = Depends(superadmin_dependency),
    ):
        with db_connect() as conn:
            with conn.cursor() as cur:
                result = tc_runtime.activate_canary_cutover(
                    cur,
                    company_code=company_code.upper(),
                    boundary_key=request.boundary_key,
                    actor=_actor(superadmin),
                    canary_token=request.canary_token,
                )
            conn.commit()
        if not result.get("ok"):
            raise HTTPException(status_code=422, detail=result)
        return result

    @router.post("/companies/{company_code}/cutover/rollback/{boundary_key}")
    def cutover_rollback(
        company_code: str,
        boundary_key: str,
        superadmin: dict[str, Any] = Depends(superadmin_dependency),
    ):
        with db_connect() as conn:
            with conn.cursor() as cur:
                result = tc_runtime.rollback_cutover(
                    cur,
                    company_code=company_code.upper(),
                    boundary_key=boundary_key,
                    actor=_actor(superadmin),
                )
            conn.commit()
        if not result.get("ok"):
            raise HTTPException(status_code=422, detail=result)
        return result

    @router.post("/companies/{company_code}/imports")
    def create_import(
        company_code: str,
        request: ImportBatchRequest,
        superadmin: dict[str, Any] = Depends(superadmin_dependency),
    ):
        with db_connect() as conn:
            with conn.cursor() as cur:
                result = tc_wizard.create_import_batch(
                    cur,
                    company_code=company_code.upper(),
                    import_kind=request.import_kind,
                    mapping=request.mapping,
                    rows=request.rows,
                    actor=_actor(superadmin),
                    dry_run=request.dry_run,
                )
            conn.commit()
        return result

    @router.post("/companies/{company_code}/offboarding/preview")
    def offboarding_preview(company_code: str, superadmin: dict[str, Any] = Depends(superadmin_dependency)):
        with db_connect() as conn:
            with conn.cursor() as cur:
                result = tc_wizard.offboarding_preview(
                    cur, company_code=company_code.upper(), actor=_actor(superadmin)
                )
            conn.commit()
        return result

    app.include_router(router)
