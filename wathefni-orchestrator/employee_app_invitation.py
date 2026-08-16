"""Employee App invitation + delivery authority (separate from Auth Wave 2).

Auth remains responsible for activate / refresh / logout / sessions / PIN /
Face ID / revoke / session_epoch. This module owns:

- when an eligible employee should receive app access
- invitation issuance (one active pending invite)
- delivery via email / WhatsApp (SMS intentionally excluded)
- resend / re-invite / expiry / delivery status for HR

Plaintext activation codes are delivered to the employee through the outbound
ladder and are NOT returned to HR on the normal path.
"""

from __future__ import annotations

import json
import logging
import os
import uuid
from datetime import timedelta
from typing import Any

logger = logging.getLogger("wathefni.employee_app_invitation")

# --- Public HR lifecycle statuses (product vocabulary) ---------------------
STATUS_PENDING = "pending"
STATUS_SENT = "sent"
STATUS_DELIVERED = "delivered"
STATUS_ACTIVATED = "activated"
STATUS_EXPIRED = "expired"
STATUS_FAILED = "failed"
STATUS_NEEDS_ATTENTION = "needs_attention"
STATUS_NONE = "none"

HR_STATUSES = {
    STATUS_PENDING,
    STATUS_SENT,
    STATUS_DELIVERED,
    STATUS_ACTIVATED,
    STATUS_EXPIRED,
    STATUS_FAILED,
    STATUS_NEEDS_ATTENTION,
    STATUS_NONE,
}

# Channels we may use. SMS is intentionally excluded forever for this flow.
CHANNEL_EMAIL = "email"
CHANNEL_WHATSAPP = "whatsapp"
CHANNEL_WHATSAPP_TEMPLATE = "whatsapp_template"
CHANNEL_PUSH = "push"  # reserved for later; not used for first activation
ALLOWED_CHANNELS = {CHANNEL_EMAIL, CHANNEL_WHATSAPP, CHANNEL_WHATSAPP_TEMPLATE, CHANNEL_PUSH}

TRIGGER_AUTO_CREATE = "auto_create"  # legacy; create path no longer auto-invites
TRIGGER_AUTO_ONBOARDING = "auto_onboarding"  # legacy; onboarding start no longer auto-invites
TRIGGER_HR_RESEND = "hr_resend"
TRIGGER_HR_REINVITE = "hr_reinvite"
TRIGGER_REQUEST_CODE = "request_code"
# Canonical auto triggers (employee_app_access eligibility).
TRIGGER_ACCESS_ENABLED = "app_access_enabled"
TRIGGER_ACCESS_BULK = "app_access_bulk"
TRIGGER_ACCESS_POLICY = "app_access_policy"

DELIVERY_MODE_AUTO = "auto_delivery"
DELIVERY_MODE_HR_TASK = "hr_task_only"
DELIVERY_MODE_EXTERNAL = "external_ladder"


def auto_invite_enabled(*, company_code: str | None = None) -> bool:
    """Master + optional company allowlist for automatic invitation/delivery."""
    raw = (os.environ.get("WATHEFNI_EMPLOYEE_APP_AUTO_INVITE") or "off").strip().lower()
    if raw not in {"1", "true", "yes", "on"}:
        return False
    allow = (os.environ.get("WATHEFNI_EMPLOYEE_APP_AUTO_INVITE_COMPANIES") or "").strip().upper()
    if not allow:
        return True
    company = str(company_code or "").strip().upper()
    return company in {c.strip() for c in allow.split(",") if c.strip()}


def ensure_invitation_schema(cur: Any) -> None:
    """Additive columns for invitation delivery status (idempotent)."""
    try:
        import employee_app_access as _access

        _access.ensure_access_schema(cur)
    except Exception:
        pass
    cur.execute(
        """
        ALTER TABLE employee_app_invites
          ADD COLUMN IF NOT EXISTS delivery_status text,
          ADD COLUMN IF NOT EXISTS delivery_channel text,
          ADD COLUMN IF NOT EXISTS last_delivery_at timestamptz,
          ADD COLUMN IF NOT EXISTS last_delivery_error text,
          ADD COLUMN IF NOT EXISTS trigger_source text,
          ADD COLUMN IF NOT EXISTS delivery_attempts int NOT NULL DEFAULT 0
        """
    )
    cur.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_employee_app_invites_delivery
          ON employee_app_invites(company_code, employee_key, status, delivery_status)
        """
    )


def _now(legacy: Any):
    return legacy.now_utc()


def _map_outbound_to_invite_delivery(outbound: dict[str, Any] | None) -> tuple[str, str | None, str | None]:
    """Map outbound_delivery result → (delivery_status, channel, error)."""
    outbound = outbound or {}
    status = str(outbound.get("delivery_status") or outbound.get("status") or "").strip().lower()
    channel_raw = str(outbound.get("channel") or outbound.get("channel_used") or "").strip().lower() or None
    channel = None
    if channel_raw:
        if "email" in channel_raw:
            channel = CHANNEL_EMAIL
        elif "template" in channel_raw:
            channel = CHANNEL_WHATSAPP_TEMPLATE
        elif "whatsapp" in channel_raw:
            channel = CHANNEL_WHATSAPP
        elif "push" in channel_raw:
            channel = CHANNEL_PUSH
        else:
            channel = channel_raw if channel_raw in ALLOWED_CHANNELS else None
    error = str(outbound.get("error") or outbound.get("last_error") or outbound.get("message") or "").strip() or None
    if outbound.get("ok") and status in {
        "delivered_push",
        "delivered_whatsapp",
        "delivered_template",
        "sent_email_fallback",
    }:
        return STATUS_DELIVERED, channel, None
    if outbound.get("ok") and channel:
        return STATUS_SENT, channel, None
    if status in {"needs_hr_action", "needs_hr"}:
        return STATUS_NEEDS_ATTENTION, channel, error or "needs_hr_action"
    if status in {"failed", "suppressed", "throttled", "dashboard_only"} or not outbound.get("ok"):
        return STATUS_FAILED if status != "needs_hr_action" else STATUS_NEEDS_ATTENTION, channel, error or status or "delivery_failed"
    return STATUS_SENT if channel else STATUS_PENDING, channel, error


def invitation_public_status(invite: dict[str, Any] | None, *, now: Any) -> str:
    """HR-facing status for one invite row (or none)."""
    if not invite:
        return STATUS_NONE
    status = str(invite.get("status") or "").strip().lower()
    if status == "redeemed":
        return STATUS_ACTIVATED
    if status in {"superseded", "locked"}:
        # Prefer a newer pending/redeemed row; caller should pass latest relevant.
        return STATUS_EXPIRED if status == "locked" else STATUS_NONE
    if status != "pending":
        return STATUS_NONE
    expires = invite.get("expires_at")
    if expires is not None and expires <= now:
        return STATUS_EXPIRED
    delivery = str(invite.get("delivery_status") or "").strip().lower()
    if delivery in HR_STATUSES and delivery not in {STATUS_NONE, STATUS_ACTIVATED, STATUS_EXPIRED}:
        return delivery
    if invite.get("last_sent_at") or invite.get("last_delivery_at"):
        return STATUS_SENT
    return STATUS_PENDING


def get_invitation_snapshot(legacy: Any, *, company_code: str, employee_key: str) -> dict[str, Any]:
    """Compact invitation + delivery snapshot for HR (never includes the code)."""
    company = str(company_code or "").upper()
    key = str(employee_key or "").strip()
    now = _now(legacy)
    with legacy.db_connect() as conn:
        with conn.cursor() as cur:
            ensure_invitation_schema(cur)
            cur.execute(
                """
                SELECT *
                FROM employee_app_invites
                WHERE company_code=%s AND employee_key=%s
                ORDER BY created_at DESC
                LIMIT 8
                """,
                (company, key),
            )
            rows = [dict(r) for r in cur.fetchall()]
            conn.commit()

    active = next((r for r in rows if str(r.get("status") or "") == "pending"), None)
    latest = rows[0] if rows else None
    focus = active or latest
    public = invitation_public_status(focus, now=now) if focus else STATUS_NONE
    # If newest is redeemed, prefer activated even if an older pending existed (shouldn't).
    redeemed = next((r for r in rows if str(r.get("status") or "") == "redeemed"), None)
    if redeemed and (not active):
        focus = redeemed
        public = STATUS_ACTIVATED

    channel = None
    sent_at = None
    error = None
    invite_id = None
    expires_at = None
    delivery_mode = None
    if focus:
        invite_id = str(focus.get("invite_id") or "")
        expires_at = focus.get("expires_at")
        delivery_mode = focus.get("delivery_mode")
        channel = focus.get("delivery_channel")
        sent_at = focus.get("last_delivery_at") or focus.get("last_sent_at")
        error = focus.get("last_delivery_error")
        if public == STATUS_EXPIRED and str(focus.get("status") or "") == "pending":
            # Soft-expire for display; activate path already rejects expired.
            pass

    has_active_session = False
    with legacy.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT 1 FROM employee_sessions
                WHERE company_code=%s AND employee_key=%s AND status='active' AND expires_at > now()
                LIMIT 1
                """,
                (company, key),
            )
            has_active_session = bool(cur.fetchone())
            conn.commit()

    access_state: dict[str, Any] = {}
    try:
        import employee_app_access as _access

        access_state = _access.get_employee_app_access_state(
            legacy, company_code=company, employee_key=key
        )
    except Exception:
        access_state = {}

    eligible = bool(access_state.get("eligible"))
    access_enabled = bool(access_state.get("app_access_enabled"))
    company_on = bool((access_state.get("policy") or {}).get("module_enabled"))

    # Resend: live invite still in flight (pending/sent/delivered/failed/needs_attention)
    can_resend = eligible and public in {
        STATUS_PENDING,
        STATUS_SENT,
        STATUS_DELIVERED,
        STATUS_FAILED,
        STATUS_NEEDS_ATTENTION,
    }
    # Re-invite: no valid live invite (none/expired/activated) or after revoke
    can_reinvite = eligible and public in {STATUS_NONE, STATUS_EXPIRED, STATUS_ACTIVATED} and not has_active_session
    # If activated with active session, reinvite is wrong — revoke first.
    if eligible and public == STATUS_ACTIVATED and has_active_session:
        can_reinvite = False

    return {
        "ok": True,
        "employee_key": key,
        "invitation_status": public,
        "invite_id": invite_id,
        "channel": channel,
        "sent_at": sent_at,
        "expires_at": expires_at,
        "delivery_mode": delivery_mode,
        "last_error": error if public in {STATUS_FAILED, STATUS_NEEDS_ATTENTION} else None,
        "app_access_active": has_active_session,
        "app_access_enabled": access_enabled,
        "app_access_eligible": eligible,
        "company_app_on": company_on,
        "actions": {
            "resend": can_resend,
            "reinvite": can_reinvite,
            "revoke_access": has_active_session,
            "enable_access": company_on and not access_enabled and employment_ok_for_enable(legacy, company, key),
            "disable_access": access_enabled,
            # Manual code handoff is exception-only when delivery needs attention.
            "show_code_exception": public == STATUS_NEEDS_ATTENTION,
        },
    }


def employment_ok_for_enable(legacy: Any, company: str, employee_key: str) -> bool:
    try:
        emp = legacy.find_employee_by_key(employee_key, company_code=company)
        import employee_app_access as _access

        return _access.employment_eligible(emp)
    except Exception:
        return False


def _stamp_delivery(
    legacy: Any,
    *,
    invite_id: str,
    delivery_status: str,
    channel: str | None,
    error: str | None,
    trigger_source: str | None = None,
) -> None:
    with legacy.db_connect() as conn:
        with conn.cursor() as cur:
            ensure_invitation_schema(cur)
            cur.execute(
                """
                UPDATE employee_app_invites
                SET delivery_status=%s,
                    delivery_channel=COALESCE(%s, delivery_channel),
                    last_delivery_at=now(),
                    last_delivery_error=%s,
                    last_sent_at=now(),
                    delivery_attempts=COALESCE(delivery_attempts, 0) + 1,
                    trigger_source=COALESCE(%s, trigger_source),
                    updated_at=now()
                WHERE invite_id=%s
                """,
                (delivery_status, channel, (error or "")[:500] or None, trigger_source, invite_id),
            )
            conn.commit()


def _deliver_code(legacy: Any, *, company: str, employee: dict[str, Any], code: str, invite_id: str, trigger_source: str) -> dict[str, Any]:
    outbound = legacy.deliver_app_activation_code(company, employee, code, invite_id=invite_id)
    delivery_status, channel, error = _map_outbound_to_invite_delivery(outbound)
    _stamp_delivery(
        legacy,
        invite_id=invite_id,
        delivery_status=delivery_status,
        channel=channel,
        error=error,
        trigger_source=trigger_source,
    )
    return {
        "ok": delivery_status in {STATUS_SENT, STATUS_DELIVERED},
        "delivery_status": delivery_status,
        "channel": channel,
        "error": error,
        "outbound": outbound,
    }


def issue_and_deliver_invitation(
    legacy: Any,
    *,
    company_code: str,
    employee: dict[str, Any],
    trigger_source: str,
    idempotency_key: str | None = None,
    force_new: bool = False,
    created_by_user_id: str | None = None,
) -> dict[str, Any]:
    """Create (or reuse) one pending invite and deliver the code to the employee.

    Never returns the plaintext code to callers. Idempotent when ``idempotency_key``
    is provided and ``force_new`` is false: an existing pending non-expired invite
    is re-delivered instead of minting duplicates.
    """
    company = str(company_code or "").upper()
    employee_key = str(employee.get("employee_key") or "").strip()
    if not employee_key:
        return {"ok": False, "error": "employee_identity_invalid"}
    if not legacy.company_has_module(company, "employee_app"):
        return {"ok": False, "error": "employee_app_not_enabled_for_company"}
    if not legacy._employee_app_employee_eligible(employee):
        return {"ok": False, "error": "employee_not_eligible"}
    # Company + employee app-access eligibility gate (never invite on mere create).
    try:
        import employee_app_access as _access

        eligible, reason = _access.is_employee_app_access_eligible(
            legacy, company_code=company, employee=employee
        )
        if not eligible:
            return {"ok": False, "error": reason or "employee_app_access_not_enabled"}
    except Exception:
        logger.exception("access eligibility check failed")
        return {"ok": False, "error": "employee_app_access_not_enabled"}

    now = _now(legacy)
    reused = False
    invite: dict[str, Any] | None = None
    code: str | None = None

    with legacy.db_connect() as conn:
        with conn.cursor() as cur:
            ensure_invitation_schema(cur)
            if idempotency_key and not force_new:
                key = idempotency_key.strip()
                # Only pending + unexpired invites are reusable. Terminal/expired rows
                # must release the key so a later legitimate enable can mint + deliver.
                cur.execute(
                    """
                    UPDATE employee_app_invites
                    SET idempotency_key=NULL, updated_at=now()
                    WHERE company_code=%s AND idempotency_key=%s
                      AND (status IS DISTINCT FROM 'pending' OR expires_at <= now())
                    """,
                    (company, key),
                )
                cur.execute(
                    """
                    SELECT * FROM employee_app_invites
                    WHERE company_code=%s AND idempotency_key=%s
                      AND status='pending' AND expires_at > now()
                    LIMIT 1
                    FOR UPDATE
                    """,
                    (company, key),
                )
                existing_idem = cur.fetchone()
                if existing_idem:
                    invite = dict(existing_idem)
                    reused = True
            if not invite and not force_new:
                cur.execute(
                    """
                    SELECT * FROM employee_app_invites
                    WHERE company_code=%s AND employee_key=%s AND status='pending'
                      AND expires_at > now()
                    ORDER BY created_at DESC
                    LIMIT 1
                    FOR UPDATE
                    """,
                    (company, employee_key),
                )
                pending = cur.fetchone()
                if pending:
                    invite = dict(pending)
                    reused = True
            conn.commit()

    if invite and reused and not force_new:
        # Cannot re-deliver without the plaintext code. Mint a fresh invite instead
        # when resending, or leave as-is for pure idempotent "already issued".
        if trigger_source in {TRIGGER_HR_RESEND, TRIGGER_REQUEST_CODE}:
            force_new = True
            reused = False
            invite = None
        else:
            # Auto triggers: do not spam — return current snapshot.
            return {
                "ok": True,
                "reused": True,
                "invite_id": str(invite.get("invite_id")),
                "delivered": False,
                "skipped_duplicate": True,
                "snapshot": get_invitation_snapshot(legacy, company_code=company, employee_key=employee_key),
            }

    if force_new or not invite:
        try:
            invite, code = legacy.create_employee_app_invite(
                company,
                employee,
                created_by_user_id=created_by_user_id,
            )
        except legacy.EmployeeAppInviteDenied as exc:
            return {"ok": False, "error": getattr(exc, "reason", None) or "invite_denied"}
        with legacy.db_connect() as conn:
            with conn.cursor() as cur:
                ensure_invitation_schema(cur)
                meta = invite.get("metadata") if isinstance(invite.get("metadata"), dict) else {}
                meta = dict(meta or {})
                meta.update({"trigger_source": trigger_source, "auto_delivery": True})
                cur.execute(
                    """
                    UPDATE employee_app_invites
                    SET delivery_mode=%s,
                        trigger_source=%s,
                        idempotency_key=COALESCE(%s, idempotency_key),
                        metadata=%s::jsonb,
                        updated_at=now()
                    WHERE invite_id=%s
                    RETURNING *
                    """,
                    (
                        DELIVERY_MODE_AUTO,
                        trigger_source,
                        (idempotency_key or "").strip() or None,
                        json.dumps(meta),
                        invite["invite_id"],
                    ),
                )
                invite = dict(cur.fetchone())
                conn.commit()

    if not code:
        # Should only happen on reuse path that forced new above.
        try:
            invite, code = legacy.create_employee_app_invite(
                company,
                employee,
                created_by_user_id=created_by_user_id,
            )
        except legacy.EmployeeAppInviteDenied as exc:
            return {"ok": False, "error": getattr(exc, "reason", None) or "invite_denied"}

    delivery = _deliver_code(
        legacy,
        company=company,
        employee=employee,
        code=code,
        invite_id=str(invite["invite_id"]),
        trigger_source=trigger_source,
    )
    return {
        "ok": True,
        "reused": False,
        "invite_id": str(invite["invite_id"]),
        "delivered": bool(delivery.get("ok")),
        "delivery_status": delivery.get("delivery_status"),
        "channel": delivery.get("channel"),
        "error": delivery.get("error"),
        "snapshot": get_invitation_snapshot(legacy, company_code=company, employee_key=employee_key),
    }


def maybe_auto_invite_employee(
    legacy: Any,
    *,
    company_code: str,
    employee: dict[str, Any],
    trigger_source: str,
    idempotency_key: str | None = None,
) -> dict[str, Any]:
    """Best-effort auto invite. Never raises into roster/onboarding callers.

    Only runs when company Employee App is ON and the employee is access-eligible.
    Create / onboarding callers must NOT use this without an explicit enable path.
    """
    company = str(company_code or "").upper()
    if not auto_invite_enabled(company_code=company):
        return {"ok": False, "skipped": True, "reason": "auto_invite_disabled"}
    if not legacy.employee_app_enabled():
        return {"ok": False, "skipped": True, "reason": "employee_app_disabled"}
    # Hard-block legacy create/onboarding triggers — eligibility enable is the only auto path.
    if trigger_source in {TRIGGER_AUTO_CREATE, TRIGGER_AUTO_ONBOARDING}:
        return {"ok": False, "skipped": True, "reason": "legacy_create_onboarding_invite_disabled"}
    try:
        import employee_app_access as _access

        eligible, reason = _access.is_employee_app_access_eligible(
            legacy, company_code=company, employee=employee
        )
        if not eligible:
            return {"ok": False, "skipped": True, "reason": reason or "employee_app_access_not_enabled"}
    except Exception:
        logger.exception("auto invite eligibility failed employee=%s", employee.get("employee_key"))
        return {"ok": False, "skipped": True, "reason": "eligibility_check_failed"}
    try:
        key = f"{idempotency_key or trigger_source}:{company}:{employee.get('employee_key')}"
        return issue_and_deliver_invitation(
            legacy,
            company_code=company,
            employee=employee,
            trigger_source=trigger_source,
            idempotency_key=key[:120],
            force_new=False,
        )
    except Exception:
        logger.exception("auto invite failed employee=%s", employee.get("employee_key"))
        return {"ok": False, "error": "auto_invite_failed"}


def resend_invitation(
    legacy: Any,
    context: dict[str, Any],
    *,
    employee_key: str,
    reason: str,
) -> dict[str, Any]:
    """HR resend: mint fresh code (invalidates prior pending) and deliver. No code in response."""
    company = str(context.get("company_code") or "").upper()
    employee = legacy.find_employee_by_key(employee_key, company_code=company)
    if not employee:
        raise legacy.HTTPException(status_code=404, detail={"error": "employee_not_found"})
    if not legacy.context_manager_allows_employee(context, employee, company_code=company):
        raise legacy.HTTPException(status_code=404, detail={"error": "employee_not_found"})
    result = issue_and_deliver_invitation(
        legacy,
        company_code=company,
        employee=employee,
        trigger_source=TRIGGER_HR_RESEND,
        idempotency_key=None,
        force_new=True,
        created_by_user_id=str(context.get("actor_user_id") or "") or None,
    )
    try:
        legacy.record_admin_audit(
            context,
            "employee_app_invitation_resent",
            summary="Resent employee app activation invitation.",
            target_type="employee",
            target=str(employee_key),
            details={"reason": reason, "invite_id": result.get("invite_id"), "delivery_status": result.get("delivery_status"), "channel": result.get("channel")},
        )
    except Exception:
        logger.warning("invitation resend audit failed", exc_info=True)
    return {"ok": bool(result.get("ok")), **{k: v for k, v in result.items() if k != "outbound"}, "code_disclosed": False}


def reinvite_employee(
    legacy: Any,
    context: dict[str, Any],
    *,
    employee_key: str,
    reason: str,
) -> dict[str, Any]:
    """HR re-invite after revoke/expiry/failure — force-new deliver, no code disclosure."""
    company = str(context.get("company_code") or "").upper()
    employee = legacy.find_employee_by_key(employee_key, company_code=company)
    if not employee:
        raise legacy.HTTPException(status_code=404, detail={"error": "employee_not_found"})
    if not legacy.context_manager_allows_employee(context, employee, company_code=company):
        raise legacy.HTTPException(status_code=404, detail={"error": "employee_not_found"})
    result = issue_and_deliver_invitation(
        legacy,
        company_code=company,
        employee=employee,
        trigger_source=TRIGGER_HR_REINVITE,
        idempotency_key=None,
        force_new=True,
        created_by_user_id=str(context.get("actor_user_id") or "") or None,
    )
    try:
        legacy.record_admin_audit(
            context,
            "employee_app_invitation_reinvited",
            summary="Re-issued employee app activation invitation.",
            target_type="employee",
            target=str(employee_key),
            details={
                "reason": reason,
                "invite_id": result.get("invite_id"),
                "delivery_status": result.get("delivery_status"),
                "channel": result.get("channel"),
            },
        )
    except Exception:
        logger.warning("invitation reinvite audit failed", exc_info=True)
    return {"ok": bool(result.get("ok")), **{k: v for k, v in result.items() if k != "outbound"}, "code_disclosed": False}
