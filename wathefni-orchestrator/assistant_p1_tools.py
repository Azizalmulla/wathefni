"""P1 Assistant module reads + employment offer governed actions.

Thin wrappers over canonical dashboard/offer services — no parallel workflows.
"""

from __future__ import annotations

from typing import Any


def list_assessment_attempts(
    legacy: Any,
    *,
    company_code: str,
    status: str | None = None,
    position: str | None = None,
    limit: int = 25,
) -> dict[str, Any]:
    company = str(company_code or "").strip().upper()
    payload = legacy.dashboard_assessments_payload(
        company,
        status=status or None,
        position=position or None,
        limit=max(1, min(int(limit or 25), 50)),
        offset=0,
    )
    attempts = payload.get("attempts") if isinstance(payload.get("attempts"), list) else []
    # Privacy: strip heavy report blobs for Assistant context.
    compact = []
    for row in attempts[:50]:
        if not isinstance(row, dict):
            continue
        compact.append(
            {
                "attempt_id": row.get("attempt_id") or row.get("id"),
                "app_key": row.get("app_key"),
                "candidate_name": row.get("candidate_name") or row.get("name"),
                "position_title": row.get("position_title") or row.get("position_code"),
                "status": row.get("status"),
                "score": row.get("score") or row.get("overall_score"),
                "needs_review": row.get("needs_review"),
                "updated_at": row.get("updated_at") or row.get("completed_at"),
            }
        )
    return {
        "ok": True,
        "company_code": company,
        "count": len(compact),
        "attempts": compact,
        "totals": payload.get("status_counts") or payload.get("totals") or {},
    }


def list_live_interviews(
    legacy: Any,
    *,
    company_code: str,
    status: str | None = None,
    limit: int = 25,
) -> dict[str, Any]:
    company = str(company_code or "").strip().upper()
    lim = max(1, min(int(limit or 25), 50))
    rows: list[dict[str, Any]] = []
    with legacy.db_connect() as conn:
        with conn.cursor() as cur:
            clauses = ["company_code=%s", "COALESCE(interview_type, '') <> 'async_video'"]
            params: list[Any] = [company]
            if status:
                clauses.append("status=%s")
                params.append(str(status).strip().lower())
            params.append(lim)
            cur.execute(
                f"""
                SELECT interview_id, app_key, candidate_name, position_title, status,
                       scheduled_start_at, meeting_type, google_meet_link, candidate_notified, updated_at
                FROM candidate_interviews
                WHERE {' AND '.join(clauses)}
                ORDER BY COALESCE(scheduled_start_at, updated_at) DESC NULLS LAST
                LIMIT %s
                """,
                params,
            )
            rows = [dict(r) for r in cur.fetchall()]
    return {"ok": True, "company_code": company, "count": len(rows), "interviews": legacy.json_safe(rows)}


def list_video_interviews(
    legacy: Any,
    *,
    company_code: str,
    status: str | None = None,
    limit: int = 25,
) -> dict[str, Any]:
    company = str(company_code or "").strip().upper()
    lim = max(1, min(int(limit or 25), 50))
    rows: list[dict[str, Any]] = []
    with legacy.db_connect() as conn:
        with conn.cursor() as cur:
            clauses = ["company_code=%s", "interview_type='async_video'"]
            params: list[Any] = [company]
            if status:
                clauses.append("COALESCE(async_status, status)=%s")
                params.append(str(status).strip().lower())
            params.append(lim)
            cur.execute(
                f"""
                SELECT interview_id, app_key, candidate_name, position_title, status, async_status,
                       updated_at, public_link_expires_at
                FROM candidate_interviews
                WHERE {' AND '.join(clauses)}
                ORDER BY updated_at DESC NULLS LAST
                LIMIT %s
                """,
                params,
            )
            rows = [dict(r) for r in cur.fetchall()]
    return {"ok": True, "company_code": company, "count": len(rows), "video_interviews": legacy.json_safe(rows)}


def list_candidate_offers(
    legacy: Any,
    *,
    company_code: str,
    app_key: str,
    permissions: set[str] | list[str] | None = None,
) -> dict[str, Any]:
    import offer_service

    company = str(company_code or "").strip().upper()
    key = str(app_key or "").strip()
    if not key:
        return {"ok": False, "error": "app_key_required", "message": "I need a candidate application key to list offers."}
    offers = offer_service.list_offers_for_application(
        legacy,
        company,
        key,
        permissions=permissions,
        surface="assistant",
    )
    compact = []
    for row in offers:
        if not isinstance(row, dict):
            continue
        compact.append(
            {
                "offer_id": row.get("offer_id"),
                "app_key": row.get("app_key") or key,
                "status": row.get("status"),
                "position_title": row.get("position_title"),
                "current_version": row.get("current_version"),
                "expires_at": row.get("expires_at"),
                "candidate_name": row.get("candidate_name"),
                "can_send": row.get("can_send"),
                "can_approve": row.get("can_approve"),
            }
        )
    return {"ok": True, "company_code": company, "app_key": key, "count": len(compact), "offers": compact}


def approve_employment_offer(
    legacy: Any,
    *,
    company_code: str,
    offer_id: str,
    actor_user_id: str,
    permissions: set[str] | list[str] | None,
) -> dict[str, Any]:
    import offer_service

    result = offer_service.approve_offer(
        legacy=legacy,
        company_code=company_code,
        offer_id=str(offer_id),
        actor_user_id=str(actor_user_id or "assistant"),
        permissions=permissions,
        actor_type="human",
    )
    return {"ok": True, "offer": result}


def send_employment_offer(
    legacy: Any,
    *,
    company_code: str,
    offer_id: str,
    actor_user_id: str,
    permissions: set[str] | list[str] | None,
    channel: str = "whatsapp",
) -> dict[str, Any]:
    import assistant_channel_readiness as acr
    import offer_service

    company = str(company_code or "").strip().upper()
    ch = str(channel or "whatsapp").strip().lower()
    refusal = acr.refuse_unsupported_channel(ch)
    if refusal:
        return refusal
    if ch == "email" and not acr.email_ready(legacy, company):
        return {"ok": False, "error": "email_not_configured", "message": "Outbound email is not configured."}
    if ch == "whatsapp" and not acr.whatsapp_candidate_ready(legacy, company):
        return {"ok": False, "error": "whatsapp_not_configured", "message": "Company WhatsApp is not configured for candidates."}
    result = offer_service.send_offer(
        legacy,
        company_code=company,
        offer_id=str(offer_id),
        actor_user_id=str(actor_user_id or "assistant"),
        permissions=permissions,
        actor_type="human",
        channel=ch if ch in {"whatsapp", "email"} else "whatsapp",
    )
    return {"ok": True, "offer": result, "channel": ch}
