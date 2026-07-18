"""Dashboard + public HTTP routes for employment offers (Offer-1)."""

from __future__ import annotations

from typing import Any

from fastapi import Depends, HTTPException, Query, Request, Response
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field

import offer_lifecycle as offers
import offer_service


class OfferDraftRequest(BaseModel):
    position_code: str | None = None
    position_title: str | None = None
    department: str | None = None
    currency: str = "KWD"
    base_salary: float | None = None
    allowances: list[dict[str, Any]] = Field(default_factory=list)
    proposed_start_date: str | None = None
    probation_days: int | None = None
    expires_at: str | None = None
    wording_en: str | None = None
    wording_ar: str | None = None
    internal_notes: str | None = None
    idempotency_key: str | None = None


class OfferUpdateRequest(BaseModel):
    expected_version: int | None = None
    position_code: str | None = None
    position_title: str | None = None
    department: str | None = None
    currency: str | None = None
    base_salary: float | None = None
    allowances: list[dict[str, Any]] | None = None
    proposed_start_date: str | None = None
    probation_days: int | None = None
    expires_at: str | None = None
    wording_en: str | None = None
    wording_ar: str | None = None
    internal_notes: str | None = None
    refresh_identity_snapshot: bool = False
    uploaded_pdf_b64: str | None = None
    upload_matches_terms_confirmed: bool = False


class OfferReasonRequest(BaseModel):
    reason: str | None = None
    expected_status: str | None = None


class OfferResponseRequest(BaseModel):
    decision: str
    evidence_note: str | None = None
    expected_status: str | None = "sent"


class OfferHireOverrideRequest(BaseModel):
    hire_override: bool = False
    override_reason: str | None = None
    confirm: bool = False


class PublicOfferRespondRequest(BaseModel):
    decision: str


def _handle(exc: Exception) -> None:
    if isinstance(exc, offers.OfferAuthorityError):
        raise HTTPException(status_code=exc.status_code, detail=exc.as_detail()) from exc
    raise exc


def _actor(context: dict[str, Any]) -> str:
    return str(context.get("actor_user_id") or context.get("user_id") or context.get("hr_user") or "")


def _permissions(legacy: Any, context: dict[str, Any]) -> set[str]:
    if hasattr(legacy, "context_permissions"):
        return {str(p) for p in legacy.context_permissions(context)}
    return {str(p) for p in (context.get("permissions") or [])}


def _can_hire(permissions: set[str], application: dict[str, Any]) -> bool:
    if "candidate.decide" not in permissions:
        return False
    stage = str(application.get("status") or "").lower()
    try:
        import recruiting_lifecycle as _rl

        stage = _rl.normalize_stage(stage) or stage
    except Exception:
        pass
    return stage in {"shortlisted", "interview"}


def register_offer_routes(app: Any, legacy: Any) -> None:
    """Attach offer endpoints to the FastAPI app. `legacy` is the app module itself."""

    prehire_dashboard_context = legacy.prehire_dashboard_context

    def _require_offers_module(context: dict[str, Any]) -> None:
        company = context["company_code"]
        if not offers.employment_offers_enabled(legacy, company):
            raise HTTPException(
                status_code=403,
                detail={"error": "module_disabled", "message": "Employment offers module is not enabled."},
            )
        legacy.require_entitlement(context, "employment_offers", "prehire.read")

    @app.get("/dashboard/prehire/applications/{app_key}/offers")
    def dashboard_list_offers(app_key: str, context: dict[str, Any] = Depends(prehire_dashboard_context)):
        _require_offers_module(context)
        company = context["company_code"]
        application = legacy.dashboard_application_or_404(app_key, company)
        perms = _permissions(legacy, context)
        items = offer_service.list_offers_for_application(
            legacy,
            company,
            app_key,
            permissions=perms,
            can_hire=_can_hire(perms, application),
        )
        return {"ok": True, "items": legacy.json_safe(items), "module": "employment_offers"}

    @app.post("/dashboard/prehire/applications/{app_key}/offers")
    def dashboard_create_offer(
        app_key: str,
        body: OfferDraftRequest,
        context: dict[str, Any] = Depends(prehire_dashboard_context),
    ):
        _require_offers_module(context)
        legacy.require_entitlement(context, "employment_offers", "offer.manage")
        try:
            offer = offer_service.create_draft(
                legacy,
                company_code=context["company_code"],
                app_key=app_key,
                actor_user_id=_actor(context),
                permissions=_permissions(legacy, context),
                position_code=body.position_code,
                position_title=body.position_title,
                department=body.department,
                currency=body.currency,
                base_salary=body.base_salary,
                allowances=body.allowances,
                proposed_start_date=body.proposed_start_date,
                probation_days=body.probation_days,
                expires_at=body.expires_at,
                wording_en=body.wording_en,
                wording_ar=body.wording_ar,
                internal_notes=body.internal_notes,
                idempotency_key=body.idempotency_key,
            )
        except Exception as exc:
            _handle(exc)
            raise
        return {"ok": True, "offer": legacy.json_safe(offer)}

    @app.get("/dashboard/prehire/offers/{offer_id}")
    def dashboard_get_offer(offer_id: str, context: dict[str, Any] = Depends(prehire_dashboard_context)):
        _require_offers_module(context)
        company = context["company_code"]
        perms = _permissions(legacy, context)
        try:
            offer_row = offers.get_offer(legacy, company, offer_id)
            if not offer_row:
                raise offers.OfferAuthorityError("offer_not_found", "Offer not found.", status_code=404)
            application = legacy.dashboard_application_or_404(str(offer_row["app_key"]), company)
            offer = offer_service.load_offer_bundle(
                legacy,
                company,
                offer_id,
                permissions=perms,
                can_hire=_can_hire(perms, application),
            )
        except Exception as exc:
            _handle(exc)
            raise
        return {"ok": True, "offer": legacy.json_safe(offer)}

    @app.patch("/dashboard/prehire/offers/{offer_id}")
    def dashboard_update_offer(
        offer_id: str,
        body: OfferUpdateRequest,
        context: dict[str, Any] = Depends(prehire_dashboard_context),
    ):
        _require_offers_module(context)
        legacy.require_entitlement(context, "employment_offers", "offer.manage")
        fields = body.model_dump(exclude_none=True)
        expected_version = fields.pop("expected_version", None)
        uploaded = fields.pop("uploaded_pdf_b64", None)
        upload_confirmed = bool(fields.pop("upload_matches_terms_confirmed", False))
        refresh = bool(fields.pop("refresh_identity_snapshot", False))
        fields["refresh_identity_snapshot"] = refresh
        try:
            offer = offer_service.update_draft(
                legacy,
                company_code=context["company_code"],
                offer_id=offer_id,
                actor_user_id=_actor(context),
                permissions=_permissions(legacy, context),
                expected_version=expected_version,
                fields=fields,
                uploaded_pdf_b64=uploaded,
                upload_matches_terms_confirmed=upload_confirmed,
            )
        except Exception as exc:
            _handle(exc)
            raise
        return {"ok": True, "offer": legacy.json_safe(offer)}

    @app.post("/dashboard/prehire/offers/{offer_id}/submit-approval")
    def dashboard_submit_offer(offer_id: str, context: dict[str, Any] = Depends(prehire_dashboard_context)):
        _require_offers_module(context)
        legacy.require_entitlement(context, "employment_offers", "offer.manage")
        try:
            offer = offer_service.submit_for_approval(
                legacy=legacy,
                company_code=context["company_code"],
                offer_id=offer_id,
                actor_user_id=_actor(context),
                permissions=_permissions(legacy, context),
            )
        except Exception as exc:
            _handle(exc)
            raise
        return {"ok": True, "offer": legacy.json_safe(offer)}

    @app.post("/dashboard/prehire/offers/{offer_id}/approve")
    def dashboard_approve_offer(offer_id: str, context: dict[str, Any] = Depends(prehire_dashboard_context)):
        _require_offers_module(context)
        legacy.require_entitlement(context, "employment_offers", "offer.approve")
        try:
            offer = offer_service.approve_offer(
                legacy=legacy,
                company_code=context["company_code"],
                offer_id=offer_id,
                actor_user_id=_actor(context),
                permissions=_permissions(legacy, context),
            )
        except Exception as exc:
            _handle(exc)
            raise
        return {"ok": True, "offer": legacy.json_safe(offer)}

    @app.post("/dashboard/prehire/offers/{offer_id}/return")
    def dashboard_return_offer(
        offer_id: str,
        body: OfferReasonRequest | None = None,
        context: dict[str, Any] = Depends(prehire_dashboard_context),
    ):
        _require_offers_module(context)
        legacy.require_entitlement(context, "employment_offers", "offer.approve")
        try:
            offer = offer_service.return_to_draft(
                legacy=legacy,
                company_code=context["company_code"],
                offer_id=offer_id,
                actor_user_id=_actor(context),
                permissions=_permissions(legacy, context),
                reason=(body.reason if body else None),
            )
        except Exception as exc:
            _handle(exc)
            raise
        return {"ok": True, "offer": legacy.json_safe(offer)}

    @app.post("/dashboard/prehire/offers/{offer_id}/send")
    def dashboard_send_offer(offer_id: str, context: dict[str, Any] = Depends(prehire_dashboard_context)):
        _require_offers_module(context)
        legacy.require_entitlement(context, "employment_offers", "offer.send")
        try:
            offer = offer_service.send_offer(
                legacy,
                company_code=context["company_code"],
                offer_id=offer_id,
                actor_user_id=_actor(context),
                permissions=_permissions(legacy, context),
            )
        except Exception as exc:
            _handle(exc)
            raise
        # Never expose raw_token on production responses; keep respond_url for HR copy.
        public = {k: v for k, v in offer.items() if k != "raw_token"}
        return {"ok": True, "offer": legacy.json_safe(public)}

    @app.post("/dashboard/prehire/offers/{offer_id}/withdraw")
    def dashboard_withdraw_offer(
        offer_id: str,
        body: OfferReasonRequest,
        context: dict[str, Any] = Depends(prehire_dashboard_context),
    ):
        _require_offers_module(context)
        legacy.require_entitlement(context, "employment_offers", "offer.withdraw")
        try:
            offer = offer_service.withdraw_offer(
                legacy=legacy,
                company_code=context["company_code"],
                offer_id=offer_id,
                actor_user_id=_actor(context),
                permissions=_permissions(legacy, context),
                reason=body.reason,
                expected_status=body.expected_status,
            )
        except Exception as exc:
            _handle(exc)
            raise
        return {"ok": True, "offer": legacy.json_safe(offer)}

    @app.post("/dashboard/prehire/offers/{offer_id}/record-response")
    def dashboard_record_offer_response(
        offer_id: str,
        body: OfferResponseRequest,
        context: dict[str, Any] = Depends(prehire_dashboard_context),
    ):
        _require_offers_module(context)
        legacy.require_entitlement(context, "employment_offers", "offer.record_response")
        try:
            offer = offer_service.record_response(
                legacy,
                company_code=context["company_code"],
                offer_id=offer_id,
                decision=body.decision,
                actor_user_id=_actor(context),
                permissions=_permissions(legacy, context),
                source="manual",
                evidence={"note": body.evidence_note} if body.evidence_note else {},
                expected_status=body.expected_status,
            )
        except Exception as exc:
            _handle(exc)
            raise
        return {"ok": True, "offer": legacy.json_safe(offer)}

    @app.get("/dashboard/prehire/offers/{offer_id}/document")
    def dashboard_offer_document(
        offer_id: str,
        version: int | None = Query(default=None),
        context: dict[str, Any] = Depends(prehire_dashboard_context),
    ):
        _require_offers_module(context)
        try:
            pdf, filename, mime = offer_service.read_offer_pdf(
                legacy, context["company_code"], offer_id, version=version
            )
        except Exception as exc:
            _handle(exc)
            raise
        return Response(
            content=pdf,
            media_type=mime,
            headers={"Content-Disposition": f'inline; filename="{filename}"'},
        )

    @app.get("/offer/{token}", response_class=HTMLResponse)
    def public_offer_page(token: str):
        try:
            preview = offer_service.public_offer_preview(legacy, raw_token=token)
        except offers.OfferAuthorityError as exc:
            return HTMLResponse(
                f"<html><body><h1>Offer unavailable</h1><p>{exc.message}</p></body></html>",
                status_code=exc.status_code,
            )
        title = preview.get("position_title") or "Employment offer"
        can = preview.get("can_respond")
        buttons = ""
        if can:
            buttons = f"""
            <form method="POST" action="/offer/{token}/respond" style="display:inline">
              <input type="hidden" name="decision" value="accepted"/>
              <button type="submit">Accept</button>
            </form>
            <form method="POST" action="/offer/{token}/respond" style="display:inline;margin-left:12px">
              <input type="hidden" name="decision" value="declined"/>
              <button type="submit">Decline</button>
            </form>
            """
        elif preview.get("already_used"):
            buttons = f"<p>Already recorded as <strong>{preview.get('used_decision')}</strong>.</p>"
        return HTMLResponse(
            f"""<!doctype html><html><head><meta charset="utf-8"/><title>{title}</title></head>
            <body style="font-family:system-ui;max-width:640px;margin:40px auto;padding:0 16px">
              <h1>{title}</h1>
              <p>Hello {preview.get('candidate_name_snapshot') or 'candidate'},</p>
              <p>Salary: {preview.get('base_salary') or '—'} {preview.get('currency') or ''}</p>
              <p>Proposed start: {preview.get('proposed_start_date') or '—'}</p>
              <p>Status: {preview.get('status')}</p>
              {buttons}
              <p style="margin-top:24px;font-size:12px;color:#666">Offer version {preview.get('offer_version')}</p>
            </body></html>"""
        )

    @app.get("/offer/{token}/state")
    def public_offer_state(token: str):
        try:
            return offer_service.public_offer_preview(legacy, raw_token=token)
        except Exception as exc:
            _handle(exc)
            raise

    @app.post("/offer/{token}/respond")
    async def public_offer_respond(token: str, request: Request):
        # Support JSON body and form posts from the HTML page.
        decision = None
        try:
            body = await request.json()
            if isinstance(body, dict):
                decision = body.get("decision")
        except Exception:
            form = await request.form()
            decision = form.get("decision")
        try:
            offer = offer_service.respond_via_token(legacy, raw_token=token, decision=str(decision or ""))
        except Exception as exc:
            _handle(exc)
            raise
        # HTML form posts get a simple confirmation page.
        content_type = str(request.headers.get("content-type") or "")
        if "application/json" in content_type:
            return {"ok": True, "offer": legacy.json_safe({k: offer.get(k) for k in ("offer_id", "status", "responded_at", "accepted_version")})}
        return HTMLResponse(
            f"<html><body><h1>Thank you</h1><p>Your response ({offer.get('status')}) was recorded.</p></body></html>"
        )
