"""Formal Employment Offer Lifecycle — Offer-1 authority.

An employment offer is a separate entity from application stage.
Application stays shortlisted/interview until an accepted offer unlocks
human-confirmed hire (when the employment_offers module is enabled).

AI may draft wording only. AI must never approve, send, withdraw, accept,
decline, override-hire, or hire.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import secrets
import uuid
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Any


OFFER_STATUSES = (
    "draft",
    "pending_approval",
    "approved",
    "sent",
    "accepted",
    "declined",
    "expired",
    "withdrawn",
)

OFFER_TERMINAL = frozenset({"accepted", "declined", "expired", "withdrawn"})
OFFER_OPEN = frozenset({"draft", "pending_approval", "approved", "sent"})

OFFER_ALLOWED_TRANSITIONS: dict[str, frozenset[str]] = {
    "draft": frozenset({"pending_approval", "withdrawn"}),
    "pending_approval": frozenset({"approved", "draft", "withdrawn"}),
    "approved": frozenset({"sent", "draft", "withdrawn"}),
    "sent": frozenset({"accepted", "declined", "expired", "withdrawn"}),
    "accepted": frozenset(),
    "declined": frozenset(),
    "expired": frozenset(),
    "withdrawn": frozenset(),
}

# Human offer actions → required permission.
OFFER_ACTION_PERMISSIONS: dict[str, str] = {
    "create": "offer.manage",
    "edit": "offer.manage",
    "submit_approval": "offer.manage",
    "approve": "offer.approve",
    "return_draft": "offer.approve",
    "send": "offer.send",
    "withdraw": "offer.withdraw",
    "record_response": "offer.record_response",
    "hire_override": "offer.hire_override",
}

# Grant-only: never inferred from role defaults.
OFFER_GRANT_ONLY_PERMISSIONS = frozenset({"offer.hire_override"})

OFFER_ROLE_PERMISSIONS: dict[str, frozenset[str]] = {
    "owner": frozenset({"offer.manage", "offer.approve", "offer.send", "offer.withdraw", "offer.record_response"}),
    "hr_manager": frozenset({"offer.manage", "offer.approve", "offer.send", "offer.withdraw", "offer.record_response"}),
    "recruiter": frozenset({"offer.manage", "offer.send", "offer.withdraw"}),
    "hiring_manager": frozenset({"offer.approve"}),
}

APPLICATION_STAGES_ELIGIBLE_FOR_OFFER = frozenset({"shortlisted", "interview"})
APPLICATION_STAGES_ELIGIBLE_FOR_HIRE = frozenset({"shortlisted", "interview"})

OFFER_DELIVERY_STATES = ("pending", "sent", "failed", "intentionally_skipped")

OFFER_STATUS_LABELS_EN = {
    "draft": "Draft",
    "pending_approval": "Pending approval",
    "approved": "Approved",
    "sent": "Sent",
    "accepted": "Accepted",
    "declined": "Declined",
    "expired": "Expired",
    "withdrawn": "Withdrawn",
}

OFFER_STATUS_LABELS_AR = {
    "draft": "مسودة",
    "pending_approval": "بانتظار الموافقة",
    "approved": "معتمد",
    "sent": "مُرسل",
    "accepted": "مقبول",
    "declined": "مرفوض",
    "expired": "منتهي",
    "withdrawn": "مسحوب",
}


def employment_offers_enabled(legacy: Any, company_code: str | None) -> bool:
    """Module gate — hire requires accepted offer only when this is on."""
    company = str(company_code or "").strip().upper()
    if not company:
        return False
    try:
        return bool(legacy.company_has_module(company, "employment_offers"))
    except Exception:
        return False


def offer_allow_self_approval(legacy: Any, company_code: str | None) -> bool:
    """Separation of duties by default; company setting may allow self-approval."""
    try:
        settings = legacy.get_company_settings(company_code) or {}
    except Exception:
        settings = {}
    return bool(settings.get("offer_allow_self_approval") is True)


def normalize_offer_status(raw: Any) -> str | None:
    key = str(raw or "").strip().lower()
    return key if key in OFFER_STATUSES else None


def offer_status_label(status: str | None, locale: str = "en") -> str:
    key = normalize_offer_status(status) or ""
    labels = OFFER_STATUS_LABELS_AR if str(locale).lower().startswith("ar") else OFFER_STATUS_LABELS_EN
    return labels.get(key, key.replace("_", " ").title() or "Unknown")


def allowed_offer_targets(from_status: str | None) -> frozenset[str]:
    status = normalize_offer_status(from_status)
    if not status:
        return frozenset()
    return OFFER_ALLOWED_TRANSITIONS.get(status, frozenset())


def permission_for_offer_action(action: str) -> str | None:
    return OFFER_ACTION_PERMISSIONS.get(str(action or "").strip().lower())


def authorize_offer_action(
    action: str,
    status: str | None,
    permissions: set[str] | list[str] | None,
    *,
    to_status: str | None = None,
) -> bool:
    """Single authority check — permissions + transition matrix. Never role names."""
    requested = str(action or "").strip().lower()
    required = permission_for_offer_action(requested)
    if not required:
        return False
    perms = {str(p) for p in (permissions or [])}
    if required not in perms:
        return False
    if requested == "create":
        return True
    if requested == "edit":
        return normalize_offer_status(status) == "draft"
    if requested == "hire_override":
        return True  # gate is separate (accepted-offer bypass); still grant-only
    target = to_status
    if target is None:
        target = {
            "submit_approval": "pending_approval",
            "approve": "approved",
            "return_draft": "draft",
            "send": "sent",
            "withdraw": "withdrawn",
            "record_response": None,  # accepted|declined checked by caller
        }.get(requested)
    if requested == "record_response":
        return normalize_offer_status(status) == "sent"
    if not target:
        return False
    return target in allowed_offer_targets(status)


def mobile_offer_allowed_actions(
    status: str | None,
    permissions: set[str] | list[str] | None,
    *,
    can_hire: bool = False,
) -> list[str]:
    """Mobile V1 executable subset: approve/return, record response, withdraw, hire."""
    actions: list[str] = []
    if authorize_offer_action("approve", status, permissions, to_status="approved"):
        actions.append("approve")
    if authorize_offer_action("return_draft", status, permissions, to_status="draft"):
        actions.append("return_draft")
    if authorize_offer_action("record_response", status, permissions):
        actions.extend(["record_accept", "record_decline"])
    if authorize_offer_action("withdraw", status, permissions, to_status="withdrawn"):
        actions.append("withdraw")
    if can_hire:
        actions.append("hire")
    return list(dict.fromkeys(actions))


def web_offer_allowed_actions(
    status: str | None,
    permissions: set[str] | list[str] | None,
    *,
    can_hire: bool = False,
    can_override: bool = False,
) -> list[str]:
    actions: list[str] = []
    if authorize_offer_action("edit", status, permissions):
        actions.append("edit")
    if authorize_offer_action("submit_approval", status, permissions, to_status="pending_approval"):
        actions.append("submit_approval")
    if authorize_offer_action("approve", status, permissions, to_status="approved"):
        actions.append("approve")
    if authorize_offer_action("return_draft", status, permissions, to_status="draft"):
        actions.append("return_draft")
    if authorize_offer_action("send", status, permissions, to_status="sent"):
        actions.append("send")
    if authorize_offer_action("withdraw", status, permissions, to_status="withdrawn"):
        actions.append("withdraw")
    if authorize_offer_action("record_response", status, permissions):
        actions.extend(["record_accept", "record_decline"])
    if can_hire:
        actions.append("hire")
    if can_override and "offer.hire_override" in {str(p) for p in (permissions or [])}:
        actions.append("hire_override")
    return list(dict.fromkeys(actions))


def ensure_offer_schema(cur: Any) -> None:
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS employment_offers (
          offer_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
          company_code text NOT NULL,
          app_key text NOT NULL,
          status text NOT NULL DEFAULT 'draft',
          current_version integer NOT NULL DEFAULT 1,
          accepted_version integer,
          position_code text,
          position_title text,
          department text,
          currency text NOT NULL DEFAULT 'KWD',
          base_salary numeric(14,3),
          allowances_json jsonb NOT NULL DEFAULT '[]'::jsonb,
          proposed_start_date date,
          probation_days integer,
          expires_at timestamptz,
          internal_notes text,
          requires_approval boolean NOT NULL DEFAULT true,
          candidate_name_snapshot text,
          candidate_phone_snapshot text,
          approved_at timestamptz,
          approved_by_user_id text,
          sent_at timestamptz,
          sent_by_user_id text,
          responded_at timestamptz,
          response_source text,
          response_evidence_json jsonb NOT NULL DEFAULT '{}'::jsonb,
          withdrawn_at timestamptz,
          withdraw_reason text,
          created_by_user_id text,
          idempotency_key text,
          metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
          created_at timestamptz NOT NULL DEFAULT now(),
          updated_at timestamptz NOT NULL DEFAULT now()
        )
        """
    )
    cur.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS employment_offers_open_app_uq
          ON employment_offers (company_code, app_key)
          WHERE status IN ('draft', 'pending_approval', 'approved', 'sent')
        """
    )
    cur.execute(
        """
        CREATE INDEX IF NOT EXISTS employment_offers_company_status_idx
          ON employment_offers (company_code, status, updated_at DESC)
        """
    )
    cur.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS employment_offers_idempotency_uq
          ON employment_offers (company_code, idempotency_key)
          WHERE idempotency_key IS NOT NULL AND idempotency_key <> ''
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS employment_offer_versions (
          offer_id uuid NOT NULL REFERENCES employment_offers(offer_id) ON DELETE CASCADE,
          version integer NOT NULL,
          terms_json jsonb NOT NULL DEFAULT '{}'::jsonb,
          wording_en text,
          wording_ar text,
          document_sha256 text,
          document_storage_uri text,
          document_filename text,
          mime_type text,
          document_source text NOT NULL DEFAULT 'generated',
          upload_matches_terms_confirmed boolean NOT NULL DEFAULT false,
          created_by_user_id text,
          created_reason text NOT NULL DEFAULT 'draft_edit',
          created_at timestamptz NOT NULL DEFAULT now(),
          PRIMARY KEY (offer_id, version)
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS employment_offer_events (
          event_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
          offer_id uuid NOT NULL REFERENCES employment_offers(offer_id) ON DELETE CASCADE,
          company_code text NOT NULL,
          event_type text NOT NULL,
          actor_type text NOT NULL DEFAULT 'human',
          actor_user_id text,
          actor_phone text,
          from_status text,
          to_status text,
          version integer,
          confirmation_token text,
          payload_json jsonb NOT NULL DEFAULT '{}'::jsonb,
          created_at timestamptz NOT NULL DEFAULT now()
        )
        """
    )
    cur.execute(
        """
        CREATE INDEX IF NOT EXISTS employment_offer_events_offer_idx
          ON employment_offer_events (company_code, offer_id, created_at DESC)
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS employment_offer_tokens (
          token_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
          offer_id uuid NOT NULL REFERENCES employment_offers(offer_id) ON DELETE CASCADE,
          company_code text NOT NULL,
          token_hash text NOT NULL UNIQUE,
          purpose text NOT NULL DEFAULT 'respond',
          offer_version integer NOT NULL,
          expires_at timestamptz NOT NULL,
          used_at timestamptz,
          used_decision text,
          revoked_at timestamptz,
          created_at timestamptz NOT NULL DEFAULT now()
        )
        """
    )
    cur.execute(
        """
        CREATE INDEX IF NOT EXISTS employment_offer_tokens_offer_idx
          ON employment_offer_tokens (company_code, offer_id, created_at DESC)
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS employment_offer_deliveries (
          delivery_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
          offer_id uuid NOT NULL REFERENCES employment_offers(offer_id) ON DELETE CASCADE,
          company_code text NOT NULL,
          offer_version integer NOT NULL,
          recipient text,
          channel text,
          document_sha256 text,
          document_version integer,
          status text NOT NULL DEFAULT 'pending',
          delivery_result text,
          expires_at timestamptz,
          outbound_event_id text,
          sent_at timestamptz,
          failed_at timestamptz,
          metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
          created_at timestamptz NOT NULL DEFAULT now(),
          updated_at timestamptz NOT NULL DEFAULT now()
        )
        """
    )
    cur.execute(
        """
        CREATE INDEX IF NOT EXISTS employment_offer_deliveries_offer_ver_idx
          ON employment_offer_deliveries (company_code, offer_id, offer_version, created_at DESC)
        """
    )
    # Durable hire-override audits — actor subject is text (UUID or non-UUID auth ids).
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS employment_offer_hire_override_audits (
          audit_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
          company_code text NOT NULL,
          app_key text NOT NULL,
          actor_type text NOT NULL,
          actor_subject text NOT NULL,
          actor_user_id text,
          reason text NOT NULL,
          from_stage text,
          to_stage text NOT NULL DEFAULT 'hired',
          confirmation_ref text NOT NULL,
          no_accepted_offer boolean NOT NULL DEFAULT true,
          idempotency_key text,
          metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
          created_at timestamptz NOT NULL DEFAULT now()
        )
        """
    )
    cur.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS employment_offer_hire_override_audits_idem_uq
          ON employment_offer_hire_override_audits (company_code, idempotency_key)
          WHERE idempotency_key IS NOT NULL AND idempotency_key <> ''
        """
    )
    cur.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS employment_offer_hire_override_audits_confirm_uq
          ON employment_offer_hire_override_audits (company_code, app_key, confirmation_ref)
          WHERE confirmation_ref IS NOT NULL AND confirmation_ref <> ''
        """
    )
    cur.execute(
        """
        CREATE INDEX IF NOT EXISTS employment_offer_hire_override_audits_app_idx
          ON employment_offer_hire_override_audits (company_code, app_key, created_at DESC)
        """
    )


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _json_dump(value: Any) -> str:
    return json.dumps(value, default=str, ensure_ascii=False, sort_keys=True)


def terms_fingerprint(terms: dict[str, Any]) -> str:
    return hashlib.sha256(_json_dump(terms).encode("utf-8")).hexdigest()


def build_terms_payload(
    *,
    position_code: str | None,
    position_title: str | None,
    department: str | None,
    currency: str,
    base_salary: Any,
    allowances: list[dict[str, Any]] | None,
    proposed_start_date: Any,
    probation_days: int | None,
    expires_at: Any,
    wording_en: str | None,
    wording_ar: str | None,
    candidate_name_snapshot: str | None,
) -> dict[str, Any]:
    return {
        "position_code": position_code,
        "position_title": position_title,
        "department": department,
        "currency": currency,
        "base_salary": str(base_salary) if base_salary is not None else None,
        "allowances": allowances or [],
        "proposed_start_date": str(proposed_start_date) if proposed_start_date else None,
        "probation_days": probation_days,
        "expires_at": str(expires_at) if expires_at else None,
        "wording_en": wording_en or "",
        "wording_ar": wording_ar or "",
        "candidate_name_snapshot": candidate_name_snapshot or "",
    }


def generate_offer_pdf_bytes(terms: dict[str, Any], *, locale: str = "en") -> bytes:
    """Minimal versioned PDF from canonical terms (no external PDF dependency)."""
    is_ar = str(locale).lower().startswith("ar")
    title = "عرض عمل" if is_ar else "Employment Offer"
    lines = [
        title,
        "",
        f"Candidate: {terms.get('candidate_name_snapshot') or '—'}",
        f"Position: {terms.get('position_title') or terms.get('position_code') or '—'}",
        f"Department: {terms.get('department') or '—'}",
        f"Salary: {terms.get('base_salary') or '—'} {terms.get('currency') or ''}",
        f"Start date: {terms.get('proposed_start_date') or '—'}",
        f"Probation (days): {terms.get('probation_days') if terms.get('probation_days') is not None else '—'}",
        f"Expires: {terms.get('expires_at') or '—'}",
        "",
        "Allowances / benefits:",
    ]
    for item in terms.get("allowances") or []:
        if isinstance(item, dict):
            lines.append(f"- {item.get('label') or item.get('name') or 'item'}: {item.get('amount') or ''} {item.get('currency') or terms.get('currency') or ''}")
        else:
            lines.append(f"- {item}")
    wording = terms.get("wording_ar") if is_ar else terms.get("wording_en")
    if wording:
        lines.extend(["", str(wording)])
    fingerprint = terms_fingerprint(terms)
    lines.extend(["", f"Terms fingerprint: {fingerprint[:16]}…", f"Generated at: {_now().isoformat()}"])
    return _simple_pdf("\n".join(lines))


def _simple_pdf(text: str) -> bytes:
    """Write a single-page PDF with Helvetica text (ASCII-safe escaped)."""
    # Escape PDF string specials; non-latin becomes '?' for the minimal generator.
    safe = "".join(ch if 32 <= ord(ch) < 127 else ("\\n" if ch == "\n" else "?") for ch in text)
    safe = safe.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
    content_lines = []
    y = 800
    for line in safe.split("\\n"):
        content_lines.append(f"BT /F1 11 Tf 50 {y} Td ({line[:110]}) Tj ET")
        y -= 14
        if y < 50:
            break
    stream = "\n".join(content_lines).encode("latin-1", errors="replace")
    objects: list[bytes] = []
    objects.append(b"1 0 obj<< /Type /Catalog /Pages 2 0 R >>endobj\n")
    objects.append(b"2 0 obj<< /Type /Pages /Kids [3 0 R] /Count 1 >>endobj\n")
    objects.append(
        b"3 0 obj<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
        b"/Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>endobj\n"
    )
    objects.append(b"4 0 obj<< /Length " + str(len(stream)).encode() + b" >>stream\n" + stream + b"\nendstream\nendobj\n")
    objects.append(b"5 0 obj<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>endobj\n")
    out = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for obj in objects:
        offsets.append(len(out))
        out.extend(obj)
    xref_pos = len(out)
    out.extend(f"xref\n0 {len(offsets)}\n".encode())
    out.extend(b"0000000000 65535 f \n")
    for off in offsets[1:]:
        out.extend(f"{off:010d} 00000 n \n".encode())
    out.extend(
        f"trailer<< /Size {len(offsets)} /Root 1 0 R >>\nstartxref\n{xref_pos}\n%%EOF\n".encode()
    )
    return bytes(out)


def hash_offer_token(raw_token: str) -> str:
    return hashlib.sha256(str(raw_token).encode("utf-8")).hexdigest()


def mint_offer_token() -> tuple[str, str]:
    raw = secrets.token_urlsafe(32)
    return raw, hash_offer_token(raw)


def require_human_actor(actor_type: str | None) -> None:
    """Reject AI. Allow human, candidate (token response), and system (expiry jobs)."""
    key = str(actor_type or "human").strip().lower()
    if key == "ai":
        raise OfferAuthorityError(
            "ai_forbidden",
            "AI cannot mutate the employment offer lifecycle.",
            status_code=403,
        )
    if key not in {"human", "candidate", "system"}:
        raise OfferAuthorityError(
            "actor_forbidden",
            f"Actor type '{key}' cannot mutate employment offers.",
            status_code=403,
        )


def require_human_hire_override_actor(actor_type: str | None) -> None:
    """Hire override is human-only — never AI, Assistant, candidate, or system."""
    key = str(actor_type or "").strip().lower()
    if key != "human":
        raise OfferAuthorityError(
            "ai_forbidden" if key == "ai" else "actor_forbidden",
            "Only a human operator can use offer hire override.",
            status_code=403,
            extra={"actor_type": key or None},
        )


def normalize_actor_subject(
    *,
    actor_subject: str | None = None,
    actor_user_id: str | None = None,
) -> str:
    """Canonical actor subject for audit — supports UUID and non-UUID auth ids."""
    subject = str(actor_subject or "").strip() or str(actor_user_id or "").strip()
    if not subject:
        raise OfferAuthorityError(
            "actor_required",
            "Authenticated actor subject is required for hire override.",
            status_code=401,
        )
    return subject


def is_uuid_text(value: str | None) -> bool:
    text = str(value or "").strip()
    if not text:
        return False
    try:
        uuid.UUID(text)
        return True
    except (ValueError, TypeError, AttributeError):
        return False


class OfferAuthorityError(Exception):
    def __init__(self, code: str, message: str, *, status_code: int = 400, extra: dict[str, Any] | None = None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code
        self.extra = extra or {}

    def as_detail(self) -> dict[str, Any]:
        detail = {"error": self.code, "message": self.message}
        detail.update(self.extra)
        return detail


def assert_transition(from_status: str | None, to_status: str) -> None:
    if to_status not in allowed_offer_targets(from_status):
        raise OfferAuthorityError(
            "transition_not_allowed",
            f"Cannot move offer from {from_status} to {to_status}.",
            status_code=409,
            extra={"from_status": from_status, "to_status": to_status},
        )


def assert_not_stale(*, current: str | None, expected: str | None, field: str = "status") -> None:
    if expected is not None and str(current or "") != str(expected):
        raise OfferAuthorityError(
            "stale_offer",
            "This offer changed. Refresh and try again.",
            status_code=409,
            extra={"expected": expected, "current": current, "field": field},
        )


def hire_gate_allows(
    legacy: Any,
    *,
    company_code: str,
    app_key: str,
    permissions: set[str] | list[str] | None,
    hire_override: bool = False,
    override_reason: str | None = None,
    confirmed: bool = False,
    actor_type: str = "human",
) -> dict[str, Any]:
    """When employment_offers module is on, hire requires accepted offer (or override).

    Override checks permission/reason/confirm/actor here; durable audit is enforced
    separately and must succeed before hire proceeds.
    """
    if not employment_offers_enabled(legacy, company_code):
        return {"ok": True, "required": False, "offer_id": None, "override": False}
    perms = {str(p) for p in (permissions or [])}
    accepted = find_accepted_offer(legacy, company_code, app_key)
    if accepted:
        return {
            "ok": True,
            "required": True,
            "override": False,
            "offer_id": str(accepted.get("offer_id")),
            "accepted_version": accepted.get("accepted_version") or accepted.get("current_version"),
            "no_accepted_offer": False,
        }
    if hire_override:
        require_human_hire_override_actor(actor_type)
        if "offer.hire_override" not in perms:
            raise OfferAuthorityError(
                "permission_denied",
                "You do not have offer hire override permission.",
                status_code=403,
                extra={"required_permission": "offer.hire_override"},
            )
        if not confirmed:
            raise OfferAuthorityError(
                "override_confirm_required",
                "Confirm hire override explicitly.",
                status_code=422,
            )
        reason = str(override_reason or "").strip()
        if not reason:
            raise OfferAuthorityError(
                "override_reason_required",
                "A clear reason is required to hire without an accepted offer.",
                status_code=422,
            )
        return {
            "ok": True,
            "required": True,
            "override": True,
            "reason": reason,
            "offer_id": None,
            "no_accepted_offer": True,
        }
    raise OfferAuthorityError(
        "accepted_offer_required",
        "An accepted employment offer is required before hire.",
        status_code=409,
    )


def load_application_for_hire_gate(
    legacy: Any,
    *,
    company_code: str,
    app_key: str,
) -> dict[str, Any]:
    """Load application scoped to tenant. Fail closed on mismatch/missing."""
    company = str(company_code or "").strip().upper()
    key = str(app_key or "").strip()
    if not company or not key:
        raise OfferAuthorityError(
            "tenant_mismatch",
            "Company and application are required for hire.",
            status_code=400,
        )
    with legacy.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT app_key, company_code, status
                FROM applications
                WHERE company_code=%s AND app_key=%s
                LIMIT 1
                """,
                (company, key),
            )
            row = cur.fetchone()
    if not row:
        # Distinguish missing vs wrong-tenant probe: look up app_key alone.
        with legacy.db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT company_code FROM applications WHERE app_key=%s LIMIT 1",
                    (key,),
                )
                other = cur.fetchone()
        if other and str(other.get("company_code") or "").upper() != company:
            raise OfferAuthorityError(
                "tenant_mismatch",
                "Application does not belong to this company.",
                status_code=404,
                extra={"company_code": company, "app_key": key},
            )
        raise OfferAuthorityError(
            "application_not_found",
            "Application not found.",
            status_code=404,
            extra={"company_code": company, "app_key": key},
        )
    return dict(row)


def assert_hire_stage(application: dict[str, Any], *, expected_from_stage: str | None = None) -> str:
    raw = str(application.get("status") or "")
    stage = raw.strip().lower()
    try:
        import recruiting_lifecycle as _rl

        stage = _rl.normalize_stage(raw) or stage
    except Exception:
        pass
    if expected_from_stage is not None:
        expected = str(expected_from_stage).strip().lower()
        try:
            import recruiting_lifecycle as _rl

            expected = _rl.normalize_stage(expected_from_stage) or expected
        except Exception:
            pass
        if stage != expected:
            raise OfferAuthorityError(
                "stale_application",
                "This candidate’s status changed. Refresh and try again.",
                status_code=409,
                extra={"expected": expected, "current": stage},
            )
    if stage not in APPLICATION_STAGES_ELIGIBLE_FOR_HIRE:
        raise OfferAuthorityError(
            "invalid_hire_stage",
            "Hire override is only allowed from shortlisted or interview.",
            status_code=409,
            extra={"current_stage": stage},
        )
    return stage


def find_accepted_offer(legacy: Any, company_code: str, app_key: str) -> dict[str, Any] | None:
    with legacy.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT *
                FROM employment_offers
                WHERE company_code=%s AND app_key=%s AND status='accepted'
                ORDER BY responded_at DESC NULLS LAST, updated_at DESC
                LIMIT 1
                """,
                (str(company_code).upper(), str(app_key)),
            )
            row = cur.fetchone()
    return dict(row) if row else None


def find_open_offer(legacy: Any, company_code: str, app_key: str) -> dict[str, Any] | None:
    with legacy.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT *
                FROM employment_offers
                WHERE company_code=%s AND app_key=%s
                  AND status = ANY(%s)
                ORDER BY updated_at DESC
                LIMIT 1
                """,
                (str(company_code).upper(), str(app_key), list(OFFER_OPEN)),
            )
            row = cur.fetchone()
    return dict(row) if row else None


def get_offer(legacy: Any, company_code: str, offer_id: str) -> dict[str, Any] | None:
    with legacy.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT *
                FROM employment_offers
                WHERE company_code=%s AND offer_id=%s
                LIMIT 1
                """,
                (str(company_code).upper(), str(offer_id)),
            )
            row = cur.fetchone()
    return dict(row) if row else None


def get_offer_version(legacy: Any, offer_id: str, version: int) -> dict[str, Any] | None:
    with legacy.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT *
                FROM employment_offer_versions
                WHERE offer_id=%s AND version=%s
                LIMIT 1
                """,
                (str(offer_id), int(version)),
            )
            row = cur.fetchone()
    return dict(row) if row else None


def record_offer_event(
    cur: Any,
    *,
    offer_id: str,
    company_code: str,
    event_type: str,
    actor_type: str = "human",
    actor_user_id: str | None = None,
    from_status: str | None = None,
    to_status: str | None = None,
    version: int | None = None,
    confirmation_token: str | None = None,
    payload: dict[str, Any] | None = None,
) -> None:
    require_human_actor(actor_type)
    cur.execute(
        """
        INSERT INTO employment_offer_events
          (offer_id, company_code, event_type, actor_type, actor_user_id,
           from_status, to_status, version, confirmation_token, payload_json)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb)
        """,
        (
            offer_id,
            str(company_code).upper(),
            event_type,
            actor_type,
            actor_user_id,
            from_status,
            to_status,
            version,
            confirmation_token,
            _json_dump(payload or {}),
        ),
    )


def offer_public_dto(
    offer: dict[str, Any],
    version_row: dict[str, Any] | None,
    *,
    delivery: dict[str, Any] | None = None,
    permissions: set[str] | list[str] | None = None,
    surface: str = "web",
    can_hire: bool = False,
    locale: str = "en",
) -> dict[str, Any]:
    status = str(offer.get("status") or "")
    perms = permissions
    if surface == "mobile":
        allowed = mobile_offer_allowed_actions(status, perms, can_hire=can_hire)
    else:
        allowed = web_offer_allowed_actions(
            status,
            perms,
            can_hire=can_hire,
            can_override="offer.hire_override" in {str(p) for p in (perms or [])},
        )
    terms = (version_row or {}).get("terms_json") if isinstance((version_row or {}).get("terms_json"), dict) else {}
    delivery_status = None
    if isinstance(delivery, dict):
        delivery_status = {
            "status": delivery.get("status"),
            "channel": delivery.get("channel"),
            "recipient": delivery.get("recipient"),
            "offer_version": delivery.get("offer_version"),
            "document_sha256": delivery.get("document_sha256"),
            "sent_at": delivery.get("sent_at"),
            "failed_at": delivery.get("failed_at"),
            "delivery_result": delivery.get("delivery_result"),
            "expires_at": delivery.get("expires_at"),
        }
    return {
        "offer_id": str(offer.get("offer_id")),
        "app_key": offer.get("app_key"),
        "company_code": offer.get("company_code"),
        "status": status,
        "status_label": offer_status_label(status, locale),
        "current_version": offer.get("current_version"),
        "accepted_version": offer.get("accepted_version"),
        "position_code": offer.get("position_code"),
        "position_title": offer.get("position_title"),
        "department": offer.get("department"),
        "currency": offer.get("currency"),
        "base_salary": str(offer.get("base_salary")) if offer.get("base_salary") is not None else None,
        "allowances": offer.get("allowances_json") if isinstance(offer.get("allowances_json"), list) else [],
        "proposed_start_date": offer.get("proposed_start_date"),
        "probation_days": offer.get("probation_days"),
        "expires_at": offer.get("expires_at"),
        "internal_notes": offer.get("internal_notes") if surface == "web" else None,
        "candidate_name_snapshot": offer.get("candidate_name_snapshot"),
        "candidate_phone_snapshot": offer.get("candidate_phone_snapshot"),
        "document": {
            "version": (version_row or {}).get("version") or offer.get("current_version"),
            "sha256": (version_row or {}).get("document_sha256"),
            "filename": (version_row or {}).get("document_filename"),
            "mime_type": (version_row or {}).get("mime_type"),
            "source": (version_row or {}).get("document_source"),
            "upload_matches_terms_confirmed": (version_row or {}).get("upload_matches_terms_confirmed"),
        },
        "terms": terms,
        "wording_en": (version_row or {}).get("wording_en"),
        "wording_ar": (version_row or {}).get("wording_ar"),
        "delivery": delivery_status,
        "allowed_actions": allowed,
        "approved_at": offer.get("approved_at"),
        "sent_at": offer.get("sent_at"),
        "responded_at": offer.get("responded_at"),
        "response_source": offer.get("response_source"),
        "updated_at": offer.get("updated_at"),
        "created_at": offer.get("created_at"),
    }
