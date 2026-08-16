"""Employment offer service — draft/version/approve/send/respond/hire-gate.

All mutations require human actor_type. AI mutation is rejected.
Candidate phone/name are display snapshots only.
Delivery status is keyed by offer_id + version.
"""

from __future__ import annotations

import base64
import hashlib
import os
import urllib.parse
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
import uuid

import candidate_messages
import offer_lifecycle as offers


def _legacy():
    import app as legacy

    return legacy


def _company(company_code: str) -> str:
    return str(company_code or "").strip().upper()


def _perms(permissions: set[str] | list[str] | None) -> set[str]:
    return {str(p) for p in (permissions or []) if str(p).strip()}


def _http_error(exc: offers.OfferAuthorityError):
    from fastapi import HTTPException

    raise HTTPException(status_code=exc.status_code, detail=exc.as_detail()) from exc


def ensure_schema(legacy: Any | None = None) -> None:
    legacy = legacy or _legacy()
    with legacy.db_connect() as conn:
        with conn.cursor() as cur:
            offers.ensure_offer_schema(cur)
        conn.commit()


def _application_row(legacy: Any, company: str, app_key: str) -> dict[str, Any]:
    return legacy.dashboard_application_or_404(app_key, company)


def _snapshot_identity(application: dict[str, Any]) -> tuple[str | None, str | None]:
    """Historical display snapshots — never identity authority."""
    name = str(application.get("candidate_name") or "").strip() or None
    phone_raw = application.get("phone") or application.get("candidate_phone")
    phone = None
    try:
        digits_fn = getattr(_legacy(), "digits", None)
        if callable(digits_fn):
            phone = str(digits_fn(phone_raw) or "").strip() or None
        else:
            phone = str(phone_raw or "").strip() or None
    except Exception:
        phone = str(phone_raw or "").strip() or None
    return name, phone


def _latest_delivery(legacy: Any, offer_id: str, version: int | None = None) -> dict[str, Any] | None:
    with legacy.db_connect() as conn:
        with conn.cursor() as cur:
            if version is not None:
                cur.execute(
                    """
                    SELECT * FROM employment_offer_deliveries
                    WHERE offer_id=%s AND offer_version=%s
                    ORDER BY created_at DESC LIMIT 1
                    """,
                    (offer_id, int(version)),
                )
            else:
                cur.execute(
                    """
                    SELECT * FROM employment_offer_deliveries
                    WHERE offer_id=%s
                    ORDER BY created_at DESC LIMIT 1
                    """,
                    (offer_id,),
                )
            row = cur.fetchone()
    return dict(row) if row else None


def load_offer_bundle(
    legacy: Any,
    company: str,
    offer_id: str,
    *,
    permissions: set[str] | list[str] | None = None,
    surface: str = "web",
    can_hire: bool = False,
    locale: str = "en",
) -> dict[str, Any]:
    offer = offers.get_offer(legacy, company, offer_id)
    if not offer:
        from fastapi import HTTPException

        raise HTTPException(status_code=404, detail={"error": "offer_not_found", "message": "Offer not found."})
    version = int(offer.get("current_version") or 1)
    version_row = offers.get_offer_version(legacy, offer_id, version)
    delivery = _latest_delivery(legacy, offer_id, version)
    return offers.offer_public_dto(
        offer,
        version_row,
        delivery=delivery,
        permissions=permissions,
        surface=surface,
        can_hire=can_hire,
        locale=locale,
    )


def list_offers_for_application(
    legacy: Any,
    company: str,
    app_key: str,
    *,
    permissions: set[str] | list[str] | None = None,
    surface: str = "web",
    can_hire: bool = False,
) -> list[dict[str, Any]]:
    with legacy.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT * FROM employment_offers
                WHERE company_code=%s AND app_key=%s
                ORDER BY created_at DESC
                """,
                (_company(company), str(app_key)),
            )
            rows = [dict(r) for r in cur.fetchall()]
    out = []
    for offer in rows:
        version = int(offer.get("current_version") or 1)
        version_row = offers.get_offer_version(legacy, str(offer["offer_id"]), version)
        delivery = _latest_delivery(legacy, str(offer["offer_id"]), version)
        out.append(
            offers.offer_public_dto(
                offer,
                version_row,
                delivery=delivery,
                permissions=permissions,
                surface=surface,
                can_hire=can_hire,
            )
        )
    return out


def create_draft(
    legacy: Any,
    *,
    company_code: str,
    app_key: str,
    actor_user_id: str,
    permissions: set[str] | list[str] | None,
    actor_type: str = "human",
    position_code: str | None = None,
    position_title: str | None = None,
    department: str | None = None,
    currency: str = "KWD",
    base_salary: Any = None,
    allowances: list[dict[str, Any]] | None = None,
    proposed_start_date: Any = None,
    probation_days: int | None = None,
    expires_at: Any = None,
    wording_en: str | None = None,
    wording_ar: str | None = None,
    internal_notes: str | None = None,
    idempotency_key: str | None = None,
) -> dict[str, Any]:
    offers.require_human_actor(actor_type)
    if not offers.authorize_offer_action("create", None, permissions):
        raise offers.OfferAuthorityError("permission_denied", "Missing offer.manage permission.", status_code=403)
    company = _company(company_code)
    if not offers.employment_offers_enabled(legacy, company):
        raise offers.OfferAuthorityError(
            "module_disabled",
            "Employment offers module is not enabled for this company.",
            status_code=403,
        )
    application = _application_row(legacy, company, app_key)
    stage = str(application.get("status") or "").strip().lower()
    try:
        import recruiting_lifecycle as _rl

        stage = _rl.normalize_stage(stage) or stage
    except Exception:
        pass
    if stage not in offers.APPLICATION_STAGES_ELIGIBLE_FOR_OFFER:
        raise offers.OfferAuthorityError(
            "stage_not_eligible",
            "Offers can only be drafted for shortlisted or interview-stage candidates.",
            status_code=409,
            extra={"stage": stage},
        )
    if idempotency_key:
        with legacy.db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT offer_id FROM employment_offers
                    WHERE company_code=%s AND idempotency_key=%s LIMIT 1
                    """,
                    (company, idempotency_key),
                )
                existing = cur.fetchone()
        if existing:
            return load_offer_bundle(legacy, company, str(existing["offer_id"]), permissions=permissions)

    open_offer = offers.find_open_offer(legacy, company, app_key)
    if open_offer:
        raise offers.OfferAuthorityError(
            "open_offer_exists",
            "An open offer already exists for this candidate. Withdraw or complete it first.",
            status_code=409,
            extra={"offer_id": str(open_offer.get("offer_id"))},
        )

    name_snap, phone_snap = _snapshot_identity(application)
    pos = application.get("position") if isinstance(application.get("position"), dict) else {}
    position_code = position_code or application.get("position_code") or pos.get("code")
    position_title = position_title or application.get("position_title") or pos.get("title")
    terms = offers.build_terms_payload(
        position_code=position_code,
        position_title=position_title,
        department=department,
        currency=currency or "KWD",
        base_salary=base_salary,
        allowances=allowances,
        proposed_start_date=proposed_start_date,
        probation_days=probation_days,
        expires_at=expires_at,
        wording_en=wording_en,
        wording_ar=wording_ar,
        candidate_name_snapshot=name_snap,
    )
    pdf = offers.generate_offer_pdf_bytes(terms, locale="en")
    sha = hashlib.sha256(pdf).hexdigest()
    offer_id = None
    with legacy.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO employment_offers (
                  company_code, app_key, status, current_version,
                  position_code, position_title, department, currency, base_salary,
                  allowances_json, proposed_start_date, probation_days, expires_at,
                  internal_notes, candidate_name_snapshot, candidate_phone_snapshot,
                  created_by_user_id, idempotency_key
                ) VALUES (
                  %s,%s,'draft',1,
                  %s,%s,%s,%s,%s,
                  %s::jsonb,%s,%s,%s,
                  %s,%s,%s,
                  %s,%s
                )
                RETURNING *
                """,
                (
                    company,
                    app_key,
                    position_code,
                    position_title,
                    department,
                    currency or "KWD",
                    base_salary,
                    offers._json_dump(allowances or []),
                    proposed_start_date,
                    probation_days,
                    expires_at,
                    internal_notes,
                    name_snap,
                    phone_snap,
                    actor_user_id,
                    idempotency_key,
                ),
            )
            offer = dict(cur.fetchone())
            offer_id = str(offer["offer_id"])
            storage_uri = _persist_pdf(legacy, company, offer_id, 1, pdf)
            cur.execute(
                """
                INSERT INTO employment_offer_versions (
                  offer_id, version, terms_json, wording_en, wording_ar,
                  document_sha256, document_storage_uri, document_filename, mime_type,
                  document_source, upload_matches_terms_confirmed, created_by_user_id, created_reason
                ) VALUES (
                  %s,1,%s::jsonb,%s,%s,
                  %s,%s,%s,'application/pdf',
                  'generated', false, %s, 'create_draft'
                )
                """,
                (
                    offer_id,
                    offers._json_dump(terms),
                    wording_en or "",
                    wording_ar or "",
                    sha,
                    storage_uri,
                    f"offer-{offer_id[:8]}-v1.pdf",
                    actor_user_id,
                ),
            )
            offers.record_offer_event(
                cur,
                offer_id=offer_id,
                company_code=company,
                event_type="created",
                actor_type=actor_type,
                actor_user_id=actor_user_id,
                from_status=None,
                to_status="draft",
                version=1,
                payload={"terms_fingerprint": offers.terms_fingerprint(terms)},
            )
        conn.commit()
    return load_offer_bundle(legacy, company, offer_id, permissions=permissions)


def update_draft(
    legacy: Any,
    *,
    company_code: str,
    offer_id: str,
    actor_user_id: str,
    permissions: set[str] | list[str] | None,
    actor_type: str = "human",
    expected_version: int | None = None,
    expected_status: str | None = "draft",
    fields: dict[str, Any] | None = None,
    uploaded_pdf_b64: str | None = None,
    upload_matches_terms_confirmed: bool = False,
) -> dict[str, Any]:
    offers.require_human_actor(actor_type)
    company = _company(company_code)
    offer = offers.get_offer(legacy, company, offer_id)
    if not offer:
        raise offers.OfferAuthorityError("offer_not_found", "Offer not found.", status_code=404)
    offers.assert_not_stale(current=offer.get("status"), expected=expected_status or "draft")
    if not offers.authorize_offer_action("edit", offer.get("status"), permissions):
        raise offers.OfferAuthorityError("permission_denied", "Cannot edit this offer.", status_code=403)
    current_version = int(offer.get("current_version") or 1)
    if expected_version is not None and current_version != int(expected_version):
        offers.assert_not_stale(current=str(current_version), expected=str(expected_version), field="version")

    fields = fields or {}
    name_snap = fields.get("candidate_name_snapshot", offer.get("candidate_name_snapshot"))
    # Phone/name snapshots may be refreshed from application for display only.
    if fields.get("refresh_identity_snapshot"):
        application = _application_row(legacy, company, str(offer["app_key"]))
        name_snap, phone_snap = _snapshot_identity(application)
    else:
        phone_snap = offer.get("candidate_phone_snapshot")

    position_code = fields.get("position_code", offer.get("position_code"))
    position_title = fields.get("position_title", offer.get("position_title"))
    department = fields.get("department", offer.get("department"))
    currency = fields.get("currency", offer.get("currency") or "KWD")
    base_salary = fields.get("base_salary", offer.get("base_salary"))
    allowances = fields.get("allowances", offer.get("allowances_json") if isinstance(offer.get("allowances_json"), list) else [])
    proposed_start_date = fields.get("proposed_start_date", offer.get("proposed_start_date"))
    probation_days = fields.get("probation_days", offer.get("probation_days"))
    expires_at = fields.get("expires_at", offer.get("expires_at"))
    wording_en = fields.get("wording_en")
    wording_ar = fields.get("wording_ar")
    if wording_en is None or wording_ar is None:
        prior = offers.get_offer_version(legacy, offer_id, current_version) or {}
        if wording_en is None:
            wording_en = prior.get("wording_en")
        if wording_ar is None:
            wording_ar = prior.get("wording_ar")
    internal_notes = fields.get("internal_notes", offer.get("internal_notes"))

    terms = offers.build_terms_payload(
        position_code=position_code,
        position_title=position_title,
        department=department,
        currency=currency,
        base_salary=base_salary,
        allowances=allowances,
        proposed_start_date=proposed_start_date,
        probation_days=probation_days,
        expires_at=expires_at,
        wording_en=wording_en,
        wording_ar=wording_ar,
        candidate_name_snapshot=name_snap,
    )

    document_source = "generated"
    upload_confirmed = False
    if uploaded_pdf_b64:
        if not upload_matches_terms_confirmed:
            raise offers.OfferAuthorityError(
                "upload_match_confirmation_required",
                "Confirm that the uploaded document matches the recorded offer terms.",
                status_code=422,
            )
        try:
            pdf = base64.b64decode(uploaded_pdf_b64)
        except Exception as exc:
            raise offers.OfferAuthorityError("invalid_upload", "Uploaded PDF could not be decoded.", status_code=422) from exc
        if not pdf.startswith(b"%PDF"):
            raise offers.OfferAuthorityError("invalid_upload", "Uploaded file must be a PDF.", status_code=422)
        document_source = "uploaded"
        upload_confirmed = True
    else:
        pdf = offers.generate_offer_pdf_bytes(terms, locale="en")

    sha = hashlib.sha256(pdf).hexdigest()
    new_version = current_version + 1
    storage_uri = _persist_pdf(legacy, company, offer_id, new_version, pdf)

    with legacy.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE employment_offers SET
                  position_code=%s, position_title=%s, department=%s, currency=%s,
                  base_salary=%s, allowances_json=%s::jsonb, proposed_start_date=%s,
                  probation_days=%s, expires_at=%s, internal_notes=%s,
                  candidate_name_snapshot=%s, candidate_phone_snapshot=%s,
                  current_version=%s, updated_at=now()
                WHERE company_code=%s AND offer_id=%s AND status='draft' AND current_version=%s
                RETURNING *
                """,
                (
                    position_code,
                    position_title,
                    department,
                    currency,
                    base_salary,
                    offers._json_dump(allowances or []),
                    proposed_start_date,
                    probation_days,
                    expires_at,
                    internal_notes,
                    name_snap,
                    phone_snap,
                    new_version,
                    company,
                    offer_id,
                    current_version,
                ),
            )
            updated = cur.fetchone()
            if not updated:
                raise offers.OfferAuthorityError("stale_offer", "Offer changed during edit.", status_code=409)
            cur.execute(
                """
                INSERT INTO employment_offer_versions (
                  offer_id, version, terms_json, wording_en, wording_ar,
                  document_sha256, document_storage_uri, document_filename, mime_type,
                  document_source, upload_matches_terms_confirmed, created_by_user_id, created_reason
                ) VALUES (
                  %s,%s,%s::jsonb,%s,%s,
                  %s,%s,%s,'application/pdf',
                  %s,%s,%s,'draft_edit'
                )
                """,
                (
                    offer_id,
                    new_version,
                    offers._json_dump(terms),
                    wording_en or "",
                    wording_ar or "",
                    sha,
                    storage_uri,
                    f"offer-{offer_id[:8]}-v{new_version}.pdf",
                    document_source,
                    upload_confirmed,
                    actor_user_id,
                ),
            )
            offers.record_offer_event(
                cur,
                offer_id=offer_id,
                company_code=company,
                event_type="versioned",
                actor_type=actor_type,
                actor_user_id=actor_user_id,
                from_status="draft",
                to_status="draft",
                version=new_version,
                payload={
                    "document_source": document_source,
                    "document_sha256": sha,
                    "upload_matches_terms_confirmed": upload_confirmed,
                },
            )
        conn.commit()
    return load_offer_bundle(legacy, company, offer_id, permissions=permissions)


def _transition(
    legacy: Any,
    *,
    company_code: str,
    offer_id: str,
    action: str,
    to_status: str,
    actor_user_id: str,
    permissions: set[str] | list[str] | None,
    actor_type: str = "human",
    expected_status: str | None = None,
    reason: str | None = None,
    extra_event: str | None = None,
    extra_payload: dict[str, Any] | None = None,
    self_approval_check: bool = False,
) -> dict[str, Any]:
    offers.require_human_actor(actor_type)
    company = _company(company_code)
    offer = offers.get_offer(legacy, company, offer_id)
    if not offer:
        raise offers.OfferAuthorityError("offer_not_found", "Offer not found.", status_code=404)
    if expected_status:
        offers.assert_not_stale(current=offer.get("status"), expected=expected_status)
    if not offers.authorize_offer_action(action, offer.get("status"), permissions, to_status=to_status):
        raise offers.OfferAuthorityError(
            "permission_denied",
            f"Not allowed to {action} this offer.",
            status_code=403,
            extra={"required_permission": offers.permission_for_offer_action(action)},
        )
    offers.assert_transition(offer.get("status"), to_status)

    if self_approval_check and action == "approve":
        created_by = str(offer.get("created_by_user_id") or "")
        if created_by and created_by == str(actor_user_id) and not offers.offer_allow_self_approval(legacy, company):
            raise offers.OfferAuthorityError(
                "self_approval_forbidden",
                "Separation of duties: the offer creator cannot approve it. Enable company self-approval policy for small-company exceptions.",
                status_code=403,
            )

    from_status = str(offer.get("status"))
    version = int(offer.get("current_version") or 1)
    sets = ["status=%s", "updated_at=now()"]
    params: list[Any] = [to_status]
    if to_status == "approved":
        sets.extend(["approved_at=now()", "approved_by_user_id=%s"])
        params.append(actor_user_id)
    if to_status == "withdrawn":
        sets.extend(["withdrawn_at=now()", "withdraw_reason=%s"])
        params.append(reason)
    params.extend([company, offer_id, from_status])
    with legacy.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                UPDATE employment_offers
                SET {', '.join(sets)}
                WHERE company_code=%s AND offer_id=%s AND status=%s
                RETURNING *
                """,
                tuple(params),
            )
            updated = cur.fetchone()
            if not updated:
                raise offers.OfferAuthorityError("stale_offer", "Offer changed during transition.", status_code=409)
            payload = {"reason": reason} if reason else {}
            if extra_payload:
                payload.update(extra_payload)
            if self_approval_check and action == "approve" and str(offer.get("created_by_user_id") or "") == str(actor_user_id):
                payload["self_approval"] = True
                payload["policy_allow_self_approval"] = True
            offers.record_offer_event(
                cur,
                offer_id=offer_id,
                company_code=company,
                event_type=extra_event or action,
                actor_type=actor_type,
                actor_user_id=actor_user_id,
                from_status=from_status,
                to_status=to_status,
                version=version,
                payload=payload,
            )
            if to_status == "withdrawn":
                cur.execute(
                    """
                    UPDATE employment_offer_tokens
                    SET revoked_at=now()
                    WHERE offer_id=%s AND used_at IS NULL AND revoked_at IS NULL
                    """,
                    (offer_id,),
                )
        conn.commit()
    return load_offer_bundle(legacy, company, offer_id, permissions=permissions)


def submit_for_approval(**kwargs: Any) -> dict[str, Any]:
    return _transition(to_status="pending_approval", action="submit_approval", expected_status="draft", **kwargs)


def approve_offer(**kwargs: Any) -> dict[str, Any]:
    return _transition(
        to_status="approved",
        action="approve",
        expected_status="pending_approval",
        self_approval_check=True,
        **kwargs,
    )


def return_to_draft(**kwargs: Any) -> dict[str, Any]:
    return _transition(to_status="draft", action="return_draft", expected_status="pending_approval", **kwargs)


def withdraw_offer(*, reason: str | None = None, **kwargs: Any) -> dict[str, Any]:
    text = str(reason or "").strip()
    if len(text) < 3:
        raise offers.OfferAuthorityError("withdraw_reason_required", "A withdraw reason is required.", status_code=422)
    return _transition(to_status="withdrawn", action="withdraw", reason=text, **kwargs)


def send_offer(
    legacy: Any,
    *,
    company_code: str,
    offer_id: str,
    actor_user_id: str,
    permissions: set[str] | list[str] | None,
    actor_type: str = "human",
    expected_status: str | None = "approved",
    channel: str = "whatsapp",
    recipient_override: str | None = None,
) -> dict[str, Any]:
    offers.require_human_actor(actor_type)
    company = _company(company_code)
    offer = offers.get_offer(legacy, company, offer_id)
    if not offer:
        raise offers.OfferAuthorityError("offer_not_found", "Offer not found.", status_code=404)
    offers.assert_not_stale(current=offer.get("status"), expected=expected_status or "approved")
    if not offers.authorize_offer_action("send", offer.get("status"), permissions, to_status="sent"):
        raise offers.OfferAuthorityError("permission_denied", "Missing offer.send permission.", status_code=403)
    offers.assert_transition(offer.get("status"), "sent")

    version = int(offer.get("current_version") or 1)
    version_row = offers.get_offer_version(legacy, offer_id, version)
    if not version_row or not version_row.get("document_sha256"):
        raise offers.OfferAuthorityError("document_required", "Offer document is missing for this version.", status_code=422)

    # Sent versions are immutable — no further edits after send.
    expires_at = offer.get("expires_at")
    if not expires_at:
        expires_at = datetime.now(timezone.utc) + timedelta(days=14)

    application = legacy.find_application_by_key(str(offer.get("app_key") or ""), company_code=company) if hasattr(legacy, "find_application_by_key") else None
    if hasattr(legacy, "assert_application_communication_allowed"):
        try:
            legacy.assert_application_communication_allowed(
                application,
                kind="offer",
                expected_company_code=company,
            )
        except Exception as exc:
            code = getattr(exc, "code", None) or "held_record_communication_forbidden"
            message = getattr(exc, "message", None) or str(exc) or "Offer cannot be sent for this application."
            status_code = int(getattr(exc, "status_code", 409) or 409)
            raise offers.OfferAuthorityError(code, message, status_code=status_code) from exc
    elif application is None:
        raise offers.OfferAuthorityError(
            "candidate_communication_requires_live_application",
            "A live Job application is required before sending an offer.",
            status_code=409,
        )

    raw_token, token_hash = offers.mint_offer_token()
    respond_url = _offer_respond_url(legacy, raw_token)

    recipient = recipient_override or offer.get("candidate_phone_snapshot")
    delivery_status = "pending"
    delivery_result = None
    outbound_event_id = None
    try:
        app_raw = application.get("raw_json") if isinstance(application, dict) and isinstance(application.get("raw_json"), dict) else {}
        locale = candidate_messages.normalize_locale(app_raw.get("candidate_locale") or app_raw.get("locale") or "en")
        candidate_template = candidate_messages.render(
            "offer_invitation",
            locale,
            role=offer.get("position_title") or (application or {}).get("position_title") or "the role",
            link=respond_url,
        )
        message = candidate_template["text"]
        if hasattr(legacy, "send_company_whatsapp_message"):
            send_result = legacy.send_company_whatsapp_message(
                company,
                recipient,
                message,
                account_id="default",
                subject_key=str(offer.get("app_key")),
                message_kind="employment_offer",
                metadata={
                    "offer_id": offer_id,
                    "offer_version": version,
                    "document_sha256": version_row.get("document_sha256"),
                    "candidate_template": candidate_template,
                },
            )
            if isinstance(send_result, dict) and send_result.get("ok"):
                delivery_status = "intentionally_skipped" if send_result.get("dry_run") else "sent"
                outbound_event_id = str(send_result.get("event_id") or send_result.get("outbound_event_id") or "") or None
            else:
                delivery_status = "failed"
                delivery_result = str((send_result or {}).get("error") or "send_failed")
        else:
            # Staging-safe: mark intentionally_skipped when no transport, but still flip offer to sent
            # with a working token URL (HR can share manually / record response).
            delivery_status = "intentionally_skipped"
            delivery_result = "no_transport_or_recipient"
    except offers.OfferAuthorityError:
        raise
    except Exception as exc:
        delivery_status = "failed"
        delivery_result = str(exc)
    if delivery_status == "failed":
        raise offers.OfferAuthorityError(
            "offer_delivery_failed",
            f"Offer delivery failed: {delivery_result or 'send_failed'}",
            status_code=502,
        )

    with legacy.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE employment_offers
                SET status='sent', sent_at=now(), sent_by_user_id=%s,
                    expires_at=COALESCE(expires_at, %s), updated_at=now()
                WHERE company_code=%s AND offer_id=%s AND status='approved'
                RETURNING *
                """,
                (actor_user_id, expires_at, company, offer_id),
            )
            updated = cur.fetchone()
            if not updated:
                raise offers.OfferAuthorityError("stale_offer", "Offer changed during send.", status_code=409)
            cur.execute(
                """
                INSERT INTO employment_offer_tokens
                  (offer_id, company_code, token_hash, purpose, offer_version, expires_at)
                VALUES (%s,%s,%s,'respond',%s,%s)
                """,
                (offer_id, company, token_hash, version, expires_at),
            )
            cur.execute(
                """
                INSERT INTO employment_offer_deliveries (
                  offer_id, company_code, offer_version, recipient, channel,
                  document_sha256, document_version, status, delivery_result,
                  expires_at, outbound_event_id, sent_at, failed_at, metadata
                ) VALUES (
                  %s,%s,%s,%s,%s,
                  %s,%s,%s,%s,
                  %s,%s,
                  CASE WHEN %s='sent' THEN now() ELSE NULL END,
                  CASE WHEN %s='failed' THEN now() ELSE NULL END,
                  %s::jsonb
                )
                """,
                (
                    offer_id,
                    company,
                    version,
                    recipient,
                    channel,
                    version_row.get("document_sha256"),
                    version,
                    delivery_status,
                    delivery_result,
                    expires_at,
                    outbound_event_id,
                    delivery_status,
                    delivery_status,
                    offers._json_dump(
                        {
                            "respond_url": respond_url,
                            "token_purpose": "respond",
                            "offer_id": offer_id,
                            "offer_version": version,
                            "candidate_template": candidate_template,
                        }
                    ),
                ),
            )
            offers.record_offer_event(
                cur,
                offer_id=offer_id,
                company_code=company,
                event_type="sent",
                actor_type=actor_type,
                actor_user_id=actor_user_id,
                from_status="approved",
                to_status="sent",
                version=version,
                payload={
                    "delivery_status": delivery_status,
                    "document_sha256": version_row.get("document_sha256"),
                    "offer_version": version,
                    "candidate_template": candidate_template,
                },
            )
        conn.commit()
    bundle = load_offer_bundle(legacy, company, offer_id, permissions=permissions)
    bundle["respond_url"] = respond_url
    bundle["raw_token"] = raw_token  # staging/debug only; strip in production responses if needed
    return bundle


def record_response(
    legacy: Any,
    *,
    company_code: str,
    offer_id: str,
    decision: str,
    actor_user_id: str | None,
    permissions: set[str] | list[str] | None,
    actor_type: str = "human",
    source: str = "manual",
    evidence: dict[str, Any] | None = None,
    expected_status: str | None = "sent",
) -> dict[str, Any]:
    offers.require_human_actor(actor_type)
    decision_key = str(decision or "").strip().lower()
    if decision_key not in {"accepted", "declined"}:
        raise offers.OfferAuthorityError("invalid_decision", "Decision must be accepted or declined.", status_code=422)
    company = _company(company_code)
    offer = offers.get_offer(legacy, company, offer_id)
    if not offer:
        raise offers.OfferAuthorityError("offer_not_found", "Offer not found.", status_code=404)
    offers.assert_not_stale(current=offer.get("status"), expected=expected_status or "sent")
    if source != "token" and not offers.authorize_offer_action("record_response", offer.get("status"), permissions):
        raise offers.OfferAuthorityError("permission_denied", "Missing offer.record_response permission.", status_code=403)
    offers.assert_transition(offer.get("status"), decision_key)
    version = int(offer.get("current_version") or 1)
    with legacy.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE employment_offers
                SET status=%s, responded_at=now(), response_source=%s,
                    response_evidence_json=%s::jsonb,
                    accepted_version=CASE WHEN %s='accepted' THEN current_version ELSE accepted_version END,
                    updated_at=now()
                WHERE company_code=%s AND offer_id=%s AND status='sent'
                RETURNING *
                """,
                (
                    decision_key,
                    source,
                    offers._json_dump(evidence or {}),
                    decision_key,
                    company,
                    offer_id,
                ),
            )
            updated = cur.fetchone()
            if not updated:
                raise offers.OfferAuthorityError("stale_offer", "Offer changed during response.", status_code=409)
            cur.execute(
                """
                UPDATE employment_offer_tokens
                SET revoked_at=COALESCE(revoked_at, now())
                WHERE offer_id=%s AND used_at IS NULL AND revoked_at IS NULL
                """,
                (offer_id,),
            )
            offers.record_offer_event(
                cur,
                offer_id=offer_id,
                company_code=company,
                event_type=decision_key,
                actor_type=actor_type,
                actor_user_id=actor_user_id,
                from_status="sent",
                to_status=decision_key,
                version=version,
                payload={"source": source, "evidence": evidence or {}},
            )
            if decision_key == "accepted":
                try:
                    import hire_ready_bridge as _hrb

                    _hrb.on_offer_accepted(
                        cur,
                        company_code=company,
                        offer=dict(updated),
                        actor_user_id=actor_user_id,
                    )
                except Exception:
                    pass
        conn.commit()
    return load_offer_bundle(legacy, company, offer_id, permissions=permissions)


def respond_via_token(legacy: Any, *, raw_token: str, decision: str) -> dict[str, Any]:
    decision_key = str(decision or "").strip().lower()
    if decision_key not in {"accepted", "declined"}:
        raise offers.OfferAuthorityError("invalid_decision", "Decision must be accepted or declined.", status_code=422)
    token_hash = offers.hash_offer_token(raw_token)
    with legacy.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT * FROM employment_offer_tokens
                WHERE token_hash=%s
                LIMIT 1
                FOR UPDATE
                """,
                (token_hash,),
            )
            token = cur.fetchone()
            if not token:
                raise offers.OfferAuthorityError("invalid_token", "Offer link is invalid.", status_code=404)
            token = dict(token)
            if token.get("revoked_at"):
                raise offers.OfferAuthorityError("token_revoked", "This offer link was revoked.", status_code=410)
            if token.get("used_at"):
                raise offers.OfferAuthorityError(
                    "token_used",
                    "This offer was already responded to.",
                    status_code=409,
                    extra={"decision": token.get("used_decision")},
                )
            expires_at = token.get("expires_at")
            if expires_at and expires_at < datetime.now(timezone.utc):
                raise offers.OfferAuthorityError("token_expired", "This offer link has expired.", status_code=410)
            offer_id = str(token["offer_id"])
            company = str(token["company_code"])
            cur.execute(
                "SELECT * FROM employment_offers WHERE offer_id=%s AND company_code=%s FOR UPDATE",
                (offer_id, company),
            )
            offer = cur.fetchone()
            if not offer:
                raise offers.OfferAuthorityError("offer_not_found", "Offer not found.", status_code=404)
            offer = dict(offer)
            if offer.get("status") != "sent":
                raise offers.OfferAuthorityError(
                    "offer_not_open",
                    "This offer is no longer awaiting a response.",
                    status_code=409,
                    extra={"status": offer.get("status")},
                )
            if int(offer.get("current_version") or 0) != int(token.get("offer_version") or 0):
                raise offers.OfferAuthorityError(
                    "version_mismatch",
                    "This link is for an older offer version.",
                    status_code=409,
                )
            cur.execute(
                """
                UPDATE employment_offers
                SET status=%s, responded_at=now(), response_source='token',
                    accepted_version=CASE WHEN %s='accepted' THEN current_version ELSE accepted_version END,
                    response_evidence_json=%s::jsonb, updated_at=now()
                WHERE offer_id=%s
                """,
                (decision_key, decision_key, offers._json_dump({"via": "public_token"}), offer_id),
            )
            cur.execute(
                """
                UPDATE employment_offer_tokens
                SET used_at=now(), used_decision=%s
                WHERE token_id=%s
                """,
                (decision_key, token["token_id"]),
            )
            offers.record_offer_event(
                cur,
                offer_id=offer_id,
                company_code=company,
                event_type=decision_key,
                actor_type="candidate",
                from_status="sent",
                to_status=decision_key,
                version=int(token.get("offer_version") or 0),
                payload={"source": "token"},
            )
            if decision_key == "accepted":
                try:
                    import hire_ready_bridge as _hrb

                    cur.execute(
                        "SELECT * FROM employment_offers WHERE offer_id=%s AND company_code=%s",
                        (offer_id, company),
                    )
                    accepted_offer = cur.fetchone()
                    _hrb.on_offer_accepted(
                        cur,
                        company_code=company,
                        offer=dict(accepted_offer or offer),
                        actor_user_id=None,
                    )
                except Exception:
                    pass
        conn.commit()
    return load_offer_bundle(legacy, company, offer_id, permissions=None, surface="web")


def public_offer_preview(legacy: Any, *, raw_token: str) -> dict[str, Any]:
    token_hash = offers.hash_offer_token(raw_token)
    with legacy.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM employment_offer_tokens WHERE token_hash=%s LIMIT 1", (token_hash,))
            token = cur.fetchone()
    if not token:
        raise offers.OfferAuthorityError("invalid_token", "Offer link is invalid.", status_code=404)
    token = dict(token)
    if token.get("revoked_at"):
        raise offers.OfferAuthorityError("token_revoked", "This offer link was revoked.", status_code=410)
    expires_at = token.get("expires_at")
    if expires_at and expires_at < datetime.now(timezone.utc):
        raise offers.OfferAuthorityError("token_expired", "This offer link has expired.", status_code=410)
    offer = offers.get_offer(legacy, str(token["company_code"]), str(token["offer_id"]))
    if not offer:
        raise offers.OfferAuthorityError("offer_not_found", "Offer not found.", status_code=404)
    version_row = offers.get_offer_version(legacy, str(token["offer_id"]), int(token["offer_version"]))
    return {
        "ok": True,
        "offer_id": str(offer["offer_id"]),
        "status": offer.get("status"),
        "position_title": offer.get("position_title"),
        "company_code": offer.get("company_code"),
        "candidate_name_snapshot": offer.get("candidate_name_snapshot"),
        "base_salary": str(offer.get("base_salary")) if offer.get("base_salary") is not None else None,
        "currency": offer.get("currency"),
        "proposed_start_date": offer.get("proposed_start_date"),
        "expires_at": offer.get("expires_at"),
        "offer_version": token.get("offer_version"),
        "already_used": bool(token.get("used_at")),
        "used_decision": token.get("used_decision"),
        "document_sha256": (version_row or {}).get("document_sha256"),
        "can_respond": offer.get("status") == "sent" and not token.get("used_at") and not token.get("revoked_at"),
    }


def read_offer_pdf(legacy: Any, company: str, offer_id: str, version: int | None = None) -> tuple[bytes, str, str]:
    offer = offers.get_offer(legacy, company, offer_id)
    if not offer:
        raise offers.OfferAuthorityError("offer_not_found", "Offer not found.", status_code=404)
    ver = int(version or offer.get("current_version") or 1)
    version_row = offers.get_offer_version(legacy, offer_id, ver)
    if not version_row:
        raise offers.OfferAuthorityError("version_not_found", "Offer version not found.", status_code=404)
    uri = str(version_row.get("document_storage_uri") or "")
    path = Path(uri)
    if not path.is_file():
        # regenerate from terms if generated
        terms = version_row.get("terms_json") if isinstance(version_row.get("terms_json"), dict) else {}
        pdf = offers.generate_offer_pdf_bytes(terms, locale="en")
        return pdf, str(version_row.get("document_filename") or f"offer-v{ver}.pdf"), "application/pdf"
    return path.read_bytes(), str(version_row.get("document_filename") or path.name), str(version_row.get("mime_type") or "application/pdf")


def _persist_pdf(legacy: Any, company: str, offer_id: str, version: int, pdf: bytes) -> str:
    root = Path(legacy.company_root(company)) / "offers" / offer_id
    root.mkdir(parents=True, exist_ok=True)
    path = root / f"v{version}.pdf"
    path.write_bytes(pdf)
    return str(path)


def _offer_respond_url(legacy: Any, raw_token: str) -> str:
    base = (
        os.environ.get("WATHEFNI_OFFER_PUBLIC_BASE_URL")
        or os.environ.get("WATHEFNI_PUBLIC_BASE_URL")
        or os.environ.get("WATHEFNI_ASSESSMENT_PUBLIC_BASE_URL")
        or "https://app.wathefni.com"
    ).rstrip("/")
    return f"{base}/offer/{urllib.parse.quote(raw_token)}"


def enforce_hire_gate(
    legacy: Any,
    *,
    company_code: str,
    app_key: str,
    permissions: set[str] | list[str] | None,
    hire_override: bool = False,
    override_reason: str | None = None,
    actor_user_id: str | None = None,
    actor_subject: str | None = None,
    actor_type: str = "human",
    confirmation_token: str | None = None,
    confirmed: bool = False,
    expected_from_stage: str | None = None,
    idempotency_key: str | None = None,
) -> dict[str, Any]:
    """Enforce accepted-offer hire gate; durable override audit is mandatory.

    Normal accepted-offer path is unchanged. Override never completes without a
    persisted audit row. AI/Assistant cannot use override.
    """
    company = _company(company_code)
    key = str(app_key or "").strip()

    if not offers.employment_offers_enabled(legacy, company):
        return {"ok": True, "required": False, "offer_id": None, "override": False}

    application = offers.load_application_for_hire_gate(
        legacy, company_code=company, app_key=key
    )
    from_stage = offers.assert_hire_stage(
        application, expected_from_stage=expected_from_stage
    )

    confirm_ref = str(confirmation_token or "").strip()
    # Explicit confirmation is required for override; token alone is not enough.
    gate = offers.hire_gate_allows(
        legacy,
        company_code=company,
        app_key=key,
        permissions=permissions,
        hire_override=hire_override,
        override_reason=override_reason,
        confirmed=bool(confirmed),
        actor_type=actor_type,
    )
    if not gate.get("override"):
        return {**gate, "from_stage": from_stage, "to_stage": "hired"}

    offers.require_human_hire_override_actor(actor_type)
    subject = offers.normalize_actor_subject(
        actor_subject=actor_subject, actor_user_id=actor_user_id
    )
    if not confirmed:
        raise offers.OfferAuthorityError(
            "override_confirm_required",
            "Confirm hire override explicitly.",
            status_code=422,
        )
    if not confirm_ref:
        confirm_ref = f"hire-override:{company}:{key}:{uuid.uuid4()}"

    reason = str(gate.get("reason") or override_reason or "").strip()
    idem = str(idempotency_key or "").strip() or f"hire-override:{company}:{key}:{confirm_ref}"
    user_id_for_row = str(actor_user_id or "").strip() or None
    if user_id_for_row is None and offers.is_uuid_text(subject):
        user_id_for_row = subject

    audit = _persist_hire_override_audit(
        legacy,
        company_code=company,
        app_key=key,
        actor_type="human",
        actor_subject=subject,
        actor_user_id=user_id_for_row,
        reason=reason,
        from_stage=from_stage,
        to_stage="hired",
        confirmation_ref=confirm_ref,
        no_accepted_offer=True,
        idempotency_key=idem,
        metadata={
            "permission": "offer.hire_override",
            "module": "employment_offers",
        },
    )
    return {
        **gate,
        "from_stage": from_stage,
        "to_stage": "hired",
        "audit_id": str(audit.get("audit_id")),
        "actor_subject": subject,
        "confirmation_ref": confirm_ref,
        "idempotent_replay": bool(audit.get("idempotent_replay")),
    }


def _persist_hire_override_audit(
    legacy: Any,
    *,
    company_code: str,
    app_key: str,
    actor_type: str,
    actor_subject: str,
    actor_user_id: str | None,
    reason: str,
    from_stage: str | None,
    to_stage: str,
    confirmation_ref: str,
    no_accepted_offer: bool,
    idempotency_key: str,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Insert durable override audit. Fail closed on any persistence error."""
    company = _company(company_code)
    payload = offers._json_dump(metadata or {})
    try:
        with legacy.db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT *
                    FROM employment_offer_hire_override_audits
                    WHERE company_code=%s
                      AND (
                        (idempotency_key IS NOT NULL AND idempotency_key=%s)
                        OR (app_key=%s AND confirmation_ref=%s)
                      )
                    ORDER BY created_at ASC
                    LIMIT 1
                    """,
                    (company, idempotency_key, app_key, confirmation_ref),
                )
                existing = cur.fetchone()
                if existing:
                    row = dict(existing)
                    row["idempotent_replay"] = True
                    _mirror_override_offer_event(
                        cur,
                        legacy=legacy,
                        company_code=company,
                        app_key=app_key,
                        actor_type=actor_type,
                        actor_user_id=actor_user_id,
                        confirmation_token=confirmation_ref,
                        reason=reason,
                    )
                    conn.commit()
                    return row

                cur.execute(
                    """
                    INSERT INTO employment_offer_hire_override_audits (
                      company_code, app_key, actor_type, actor_subject, actor_user_id,
                      reason, from_stage, to_stage, confirmation_ref, no_accepted_offer,
                      idempotency_key, metadata
                    ) VALUES (
                      %s,%s,%s,%s,%s,
                      %s,%s,%s,%s,%s,
                      %s,%s::jsonb
                    )
                    RETURNING *
                    """,
                    (
                        company,
                        app_key,
                        actor_type,
                        actor_subject,
                        actor_user_id,
                        reason,
                        from_stage,
                        to_stage,
                        confirmation_ref,
                        bool(no_accepted_offer),
                        idempotency_key,
                        payload,
                    ),
                )
                inserted = cur.fetchone()
                if not inserted:
                    raise offers.OfferAuthorityError(
                        "override_audit_failed",
                        "Hire override audit could not be persisted.",
                        status_code=500,
                    )
                _mirror_override_offer_event(
                    cur,
                    legacy=legacy,
                    company_code=company,
                    app_key=app_key,
                    actor_type=actor_type,
                    actor_user_id=actor_user_id,
                    confirmation_token=confirmation_ref,
                    reason=reason,
                )
            conn.commit()
    except offers.OfferAuthorityError:
        raise
    except Exception as exc:
        raise offers.OfferAuthorityError(
            "override_audit_failed",
            "Hire override audit could not be persisted.",
            status_code=500,
            extra={"cause": type(exc).__name__},
        ) from exc

    row = dict(inserted)
    row["idempotent_replay"] = False
    return row


def _mirror_override_offer_event(
    cur: Any,
    *,
    legacy: Any,
    company_code: str,
    app_key: str,
    actor_type: str,
    actor_user_id: str | None,
    confirmation_token: str | None,
    reason: str,
) -> None:
    """Best-effort mirror onto offer events when an offer row exists (non-fatal)."""
    try:
        open_or_any = offers.find_open_offer(legacy, company_code, app_key) or offers.find_accepted_offer(
            legacy, company_code, app_key
        )
        if not open_or_any:
            return
        offers.record_offer_event(
            cur,
            offer_id=str(open_or_any["offer_id"]),
            company_code=company_code,
            event_type="hire_override",
            actor_type=actor_type,
            actor_user_id=actor_user_id,
            from_status=str(open_or_any.get("status")),
            to_status=str(open_or_any.get("status")),
            version=int(open_or_any.get("current_version") or 1),
            confirmation_token=confirmation_token,
            payload={"reason": reason, "app_key": app_key, "source": "hire_override_audit"},
        )
    except Exception:
        return
