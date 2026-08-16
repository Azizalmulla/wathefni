"""Wathefni Calendar C4 — RSVP, guest tokens, reschedule requests, personal notify hooks.

Calendar truth stays first-party. Delivery failures never silently remove events.
"""

from __future__ import annotations

import hashlib
import hmac
import os
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any, Iterable, Mapping, Sequence
from uuid import uuid4

import calendar_schema
import calendar_store as store

RSVP_STATES = frozenset({"needs_action", "accepted", "declined", "tentative", "removed"})
GUEST_ACTIONS = frozenset({"accept", "decline", "tentative", "request_reschedule"})
TOKEN_TTL_HOURS = int(os.environ.get("CALENDAR_GUEST_TOKEN_TTL_HOURS", "168") or 168)
MAJOR_TIME_CHANGE_SECONDS = int(os.environ.get("CALENDAR_MAJOR_TIME_CHANGE_SECONDS", "900") or 900)
RECONFIRM_ON_MAJOR_TIME_CHANGE = True  # locked C4 policy


class CalendarParticipationError(Exception):
    def __init__(self, code: str, message: str, *, http_status: int = 422, details: Mapping[str, Any] | None = None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.http_status = http_status
        self.details = dict(details or {})

    def envelope(self) -> dict[str, Any]:
        out = {"ok": False, "error": self.code, "message": self.message}
        out.update(self.details)
        return out


def _text(value: Any) -> str:
    return str(value or "").strip()


def _json(legacy: Any, value: Any) -> Any:
    if hasattr(legacy, "Json"):
        return legacy.Json(value if value is not None else {})
    return value if value is not None else {}


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(value: Any) -> str | None:
    return store._iso(value)


def hash_token(raw: str) -> str:
    return hashlib.sha256(_text(raw).encode("utf-8")).hexdigest()


def mint_raw_token() -> str:
    return secrets.token_urlsafe(32)


def ensure_schema(legacy: Any) -> None:
    with legacy.db_connect() as conn:
        with conn.cursor() as cur:
            calendar_schema.ensure_calendar_schema(cur)
        conn.commit()


def _audit(cur: Any, legacy: Any, **kwargs: Any) -> None:
    store._audit(cur, legacy, **kwargs)


# ---------------------------------------------------------------------------
# Personal / operational notifications — via canonical communication authority
# ---------------------------------------------------------------------------


def notify_personal(
    legacy: Any,
    *,
    company_code: str,
    user_ids: Sequence[str],
    message: str,
    source: str,
    kind: str,
    subject_type: str = "calendar_event",
    subject_key: str | None = None,
    purpose: str | None = None,
    recipient_type: str = "hr",
) -> dict[str, Any]:
    """Emit Calendar operational intents through wathefni_communication (not providers)."""
    import wathefni_communication as comm

    ids = [_text(u) for u in user_ids if _text(u)]
    if not ids:
        return {"ok": True, "skipped": True, "audience": "personal", "source": source, "target_count": 0}
    mapped = {
        "rsvp_received": "calendar_rsvp_received",
        "reschedule_requested": "calendar_reschedule_requested",
        "attendee_invited": "calendar_invitation",
        "reminder_due": "calendar_reminder",
    }.get(_text(kind), purpose or "calendar_rsvp_received")
    results: list[dict[str, Any]] = []
    for uid in ids:
        rtype = recipient_type
        if rtype not in {"hr", "employee"}:
            rtype = "hr"
        results.append(
            comm.deliver_intent(
                legacy,
                {
                    "company_code": _text(company_code).upper(),
                    "purpose": mapped,
                    "recipient_type": rtype,
                    "lifecycle": "hr_ops" if rtype == "hr" else "post_hire",
                    "recipient": {"user_id": uid},
                    "event_id": subject_key,
                    "subject_type": subject_type,
                    "subject_key": subject_key,
                    "payload": {"message": message, "source": source, "kind": kind},
                    "idempotency_key": f"notify:{source}:{kind}:{subject_key}:{uid}",
                },
            )
        )
    return {
        "ok": any(r.get("ok") for r in results),
        "audience": "personal",
        "source": source,
        "kind": kind,
        "target_count": len(results),
        "results": results,
    }


# ---------------------------------------------------------------------------
# Internal RSVP
# ---------------------------------------------------------------------------


def set_attendee_rsvp(
    legacy: Any,
    *,
    company_code: str,
    event_id: str,
    actor_user_id: str,
    target_user_id: str | None = None,
    rsvp_status: str,
    expected_rsvp_version: Any = None,
    permissions: Iterable[Any] | None = None,
) -> dict[str, Any]:
    """Attendee (or authorized organizer) updates RSVP with OCC on rsvp_version."""
    company = _text(company_code).upper()
    actor = _text(actor_user_id)
    target = _text(target_user_id) or actor
    status = _text(rsvp_status).lower()
    if status not in RSVP_STATES or status == "removed":
        raise CalendarParticipationError("invalid_rsvp", "RSVP must be accepted, declined, tentative, or needs_action.")
    if not company or not actor or not event_id:
        raise CalendarParticipationError("event_not_found", "Event not found.", http_status=404)

    with legacy.db_connect() as conn:
        with conn.cursor() as cur:
            calendar_schema.ensure_calendar_schema(cur)
            bundle = store.load_event_bundle(cur, company, event_id)
            if not bundle:
                raise CalendarParticipationError("event_not_found", "Event not found.", http_status=404)
            event = bundle["row"]
            if _text(event.get("status")).lower() == "cancelled":
                raise CalendarParticipationError("event_cancelled", "Cannot RSVP to a cancelled event.", http_status=409)

            cur.execute(
                """
                SELECT * FROM calendar_attendees
                WHERE company_code=%s AND event_id=%s AND user_id=%s
                FOR UPDATE
                """,
                (company, event_id, target),
            )
            row = cur.fetchone()
            if not row:
                raise CalendarParticipationError("attendee_not_found", "Attendee not found on this event.", http_status=404)
            attendee = dict(row)
            if _text(attendee.get("rsvp_status")).lower() == "removed":
                raise CalendarParticipationError("attendee_removed", "Removed attendees cannot RSVP.", http_status=409)

            perms = {_text(p) for p in (permissions or [])}
            is_self = actor == target
            is_organizer = actor in {
                _text(event.get("organizer_user_id")),
                _text(event.get("owner_user_id")),
            } or bool(attendee.get("is_organizer")) and actor == target
            # Organizer may set another attendee's RSVP only with calendar.manage
            if not is_self:
                if "calendar.manage" not in perms or actor not in {
                    _text(event.get("organizer_user_id")),
                    _text(event.get("owner_user_id")),
                }:
                    raise CalendarParticipationError(
                        "permission_denied",
                        "Only the attendee (or event organizer with manage) may change this RSVP.",
                        http_status=403,
                    )

            current_version = int(attendee.get("rsvp_version") or 1)
            if expected_rsvp_version is not None:
                try:
                    expected = int(expected_rsvp_version)
                except (TypeError, ValueError):
                    expected = -1
                if expected != current_version:
                    raise CalendarParticipationError(
                        "stale_rsvp_version",
                        "RSVP was updated elsewhere. Refresh and retry.",
                        http_status=409,
                        details={"current_version": current_version, "expected_version": expected},
                    )

            before = {"rsvp_status": attendee.get("rsvp_status"), "rsvp_version": current_version}
            cur.execute(
                """
                UPDATE calendar_attendees
                SET rsvp_status=%s,
                    response_at=now(),
                    rsvp_version=%s,
                    updated_at=now()
                WHERE company_code=%s AND event_id=%s AND user_id=%s AND rsvp_version=%s
                RETURNING *
                """,
                (status, current_version + 1, company, event_id, target, current_version),
            )
            updated = cur.fetchone()
            if not updated:
                raise CalendarParticipationError("stale_rsvp_version", "RSVP conflict.", http_status=409)

            _audit(
                cur,
                legacy,
                company_code=company,
                event_id=event_id,
                actor_user_id=actor,
                action="attendee_rsvp",
                before=before,
                after={"user_id": target, "rsvp_status": status, "rsvp_version": current_version + 1},
            )
            bundle = store.load_event_bundle(cur, company, event_id)
        conn.commit()

    # Personal notify organizer (not self-RSVP as organizer-only noise suppression for own action)
    organizer = _text(event.get("organizer_user_id"))
    if organizer and organizer != actor:
        notify_personal(
            legacy,
            company_code=company,
            user_ids=[organizer],
            message=f"Calendar RSVP: {_text(target)[:8]}… → {status} for “{_text(event.get('title')) or 'event'}”.",
            source="calendar_rsvp",
            kind="rsvp_received",
            subject_key=event_id,
        )
    assert bundle is not None
    return {"ok": True, "event": bundle["payload"], "attendee": store.serialize_attendee(dict(updated))}


# ---------------------------------------------------------------------------
# Guest tokens + public RSVP
# ---------------------------------------------------------------------------


def issue_guest_token(
    cur: Any,
    *,
    company_code: str,
    event_id: str,
    guest_id: str,
    ttl_hours: int = TOKEN_TTL_HOURS,
    revoke_existing: bool = True,
) -> dict[str, Any]:
    company = _text(company_code).upper()
    if revoke_existing:
        cur.execute(
            """
            UPDATE calendar_guest_tokens
            SET revoked_at=now()
            WHERE company_code=%s AND guest_id=%s AND revoked_at IS NULL
            """,
            (company, guest_id),
        )
    raw = mint_raw_token()
    token_id = str(uuid4())
    expires = _now() + timedelta(hours=max(1, int(ttl_hours)))
    cur.execute(
        """
        INSERT INTO calendar_guest_tokens
          (token_id, company_code, event_id, guest_id, token_hash, purpose, expires_at)
        VALUES (%s,%s,%s,%s,%s,'rsvp',%s)
        """,
        (token_id, company, event_id, guest_id, hash_token(raw), expires),
    )
    return {"token_id": token_id, "token": raw, "expires_at": expires.isoformat()}


def resolve_guest_token(cur: Any, raw_token: str) -> dict[str, Any]:
    th = hash_token(raw_token)
    if not th:
        raise CalendarParticipationError("invalid_token", "Invalid or expired link.", http_status=404)
    cur.execute(
        """
        SELECT t.*, g.email, g.phone, g.display_name, g.guest_kind, g.person_key, g.app_key,
               g.rsvp_status AS guest_rsvp, g.rsvp_version AS guest_rsvp_version,
               e.title, e.title_ar, e.start_at, e.end_at, e.timezone, e.location, e.meeting_url,
               e.status AS event_status, e.company_code AS event_company
        FROM calendar_guest_tokens t
        JOIN calendar_guests g ON g.guest_id=t.guest_id AND g.company_code=t.company_code
        JOIN calendar_events e ON e.event_id=t.event_id AND e.company_code=t.company_code
        WHERE t.token_hash=%s
        LIMIT 1
        """,
        (th,),
    )
    row = cur.fetchone()
    if not row:
        raise CalendarParticipationError("invalid_token", "Invalid or expired link.", http_status=404)
    data = dict(row)
    if data.get("revoked_at"):
        raise CalendarParticipationError("token_revoked", "This invitation link was revoked.", http_status=410)
    expires = data.get("expires_at")
    if expires and expires.tzinfo is None:
        expires = expires.replace(tzinfo=timezone.utc)
    if expires and expires < _now():
        raise CalendarParticipationError("token_expired", "This invitation link has expired.", http_status=410)
    if _text(data.get("event_status")).lower() == "cancelled":
        data["event_cancelled"] = True
    return data


def public_guest_payload(row: Mapping[str, Any]) -> dict[str, Any]:
    """Privacy-safe guest page payload — no internal IDs beyond opaque token scope."""
    return {
        "ok": True,
        "event": {
            "title": row.get("title"),
            "title_ar": row.get("title_ar"),
            "start_at": _iso(row.get("start_at")),
            "end_at": _iso(row.get("end_at")),
            "timezone": _text(row.get("timezone")) or "Asia/Kuwait",
            "location": row.get("location"),
            "meeting_url": row.get("meeting_url"),
            "status": _text(row.get("event_status")),
            "cancelled": bool(row.get("event_cancelled")),
        },
        "guest": {
            "display_name": row.get("display_name"),
            "rsvp_status": _text(row.get("guest_rsvp")) or "needs_action",
            "rsvp_version": int(row.get("guest_rsvp_version") or 1),
        },
        "actions": sorted(GUEST_ACTIONS),
        "expires_at": _iso(row.get("expires_at")),
    }


def apply_guest_action(
    legacy: Any,
    *,
    raw_token: str,
    action: str,
    note: str | None = None,
    preferred_times: list[Any] | None = None,
    expected_rsvp_version: Any = None,
    client_ip: str | None = None,
) -> dict[str, Any]:
    act = _text(action).lower()
    if act not in GUEST_ACTIONS:
        raise CalendarParticipationError("invalid_action", "Unsupported guest action.")

    with legacy.db_connect() as conn:
        with conn.cursor() as cur:
            calendar_schema.ensure_calendar_schema(cur)
            row = resolve_guest_token(cur, raw_token)
            company = _text(row.get("company_code")).upper()
            event_id = str(row.get("event_id"))
            guest_id = str(row.get("guest_id"))

            if row.get("event_cancelled") and act != "decline":
                raise CalendarParticipationError("event_cancelled", "This event was cancelled.", http_status=409)

            # Rate-limit soft: reject rapid identical action spam via used_at window for non-reschedule
            if act != "request_reschedule":
                status_map = {"accept": "accepted", "decline": "declined", "tentative": "tentative"}
                new_status = status_map[act]
                current_version = int(row.get("guest_rsvp_version") or 1)
                if expected_rsvp_version is not None:
                    try:
                        expected = int(expected_rsvp_version)
                    except (TypeError, ValueError) as exc:
                        raise CalendarParticipationError(
                            "stale_rsvp_version", "Invalid RSVP version.", http_status=409
                        ) from exc
                    if expected != current_version:
                        raise CalendarParticipationError(
                            "stale_rsvp_version",
                            "RSVP was updated elsewhere.",
                            http_status=409,
                            details={"current_version": current_version},
                        )

                # Replay-safe: identical status+version → success without bump
                if _text(row.get("guest_rsvp")).lower() == new_status:
                    return {
                        "ok": True,
                        "idempotent": True,
                        "rsvp_status": new_status,
                        "event": public_guest_payload(row)["event"],
                    }

                cur.execute(
                    """
                    UPDATE calendar_guests
                    SET rsvp_status=%s, rsvp_version=%s, updated_at=now()
                    WHERE company_code=%s AND guest_id=%s AND rsvp_version=%s
                    RETURNING *
                    """,
                    (new_status, current_version + 1, company, guest_id, current_version),
                )
                updated = cur.fetchone()
                if not updated:
                    raise CalendarParticipationError("stale_rsvp_version", "RSVP conflict.", http_status=409)
                cur.execute(
                    """
                    UPDATE calendar_guest_tokens
                    SET used_at=COALESCE(used_at, now()), last_action=%s
                    WHERE token_id=%s
                    """,
                    (act, str(row.get("token_id"))),
                )
                _audit(
                    cur,
                    legacy,
                    company_code=company,
                    event_id=event_id,
                    actor_user_id=None,
                    action="guest_rsvp",
                    before={"rsvp_status": row.get("guest_rsvp")},
                    after={"guest_id": guest_id, "rsvp_status": new_status, "action": act, "client_ip": client_ip},
                )
                # Notify organizer
                cur.execute(
                    "SELECT organizer_user_id, owner_user_id, title FROM calendar_events WHERE company_code=%s AND event_id=%s",
                    (company, event_id),
                )
                ev = dict(cur.fetchone() or {})
            else:
                # Reschedule request — never changes event time
                if row.get("event_cancelled"):
                    raise CalendarParticipationError("event_cancelled", "This event was cancelled.", http_status=409)
                preferred = preferred_times if isinstance(preferred_times, list) else []
                interview_id = None
                cur.execute(
                    """
                    SELECT source_record_id FROM calendar_event_links
                    WHERE company_code=%s AND event_id=%s AND link_status='active'
                      AND lower(source_workflow)='interview'
                    LIMIT 1
                    """,
                    (company, event_id),
                )
                link = cur.fetchone()
                if link:
                    interview_id = _text(link.get("source_record_id")) or None
                cur.execute(
                    """
                    SELECT * FROM calendar_reschedule_requests
                    WHERE company_code=%s AND event_id=%s AND guest_id=%s AND status='pending'
                    LIMIT 1
                    """,
                    (company, event_id, guest_id),
                )
                existing = cur.fetchone()
                if existing:
                    conn.commit()
                    return {
                        "ok": True,
                        "idempotent": True,
                        "request": serialize_reschedule_request(dict(existing)),
                        "message": "A pending reschedule request already exists.",
                    }
                cur.execute(
                    """
                    INSERT INTO calendar_reschedule_requests
                      (request_id, company_code, event_id, guest_id, interview_id, status,
                       preferred_times, note)
                    VALUES (%s,%s,%s,%s,%s,'pending',%s,%s)
                    RETURNING *
                    """,
                    (
                        str(uuid4()),
                        company,
                        event_id,
                        guest_id,
                        interview_id,
                        _json(legacy, preferred),
                        _text(note) or None,
                    ),
                )
                req = dict(cur.fetchone())
                cur.execute(
                    """
                    UPDATE calendar_guest_tokens
                    SET used_at=COALESCE(used_at, now()), last_action=%s
                    WHERE token_id=%s
                    """,
                    (act, str(row.get("token_id"))),
                )
                _audit(
                    cur,
                    legacy,
                    company_code=company,
                    event_id=event_id,
                    actor_user_id=None,
                    action="guest_reschedule_request",
                    before={},
                    after={"request_id": req["request_id"], "interview_id": interview_id, "client_ip": client_ip},
                )
                cur.execute(
                    "SELECT organizer_user_id, owner_user_id, title FROM calendar_events WHERE company_code=%s AND event_id=%s",
                    (company, event_id),
                )
                ev = dict(cur.fetchone() or {})
                conn.commit()
                targets = [_text(ev.get("organizer_user_id")), _text(ev.get("owner_user_id"))]
                notify_personal(
                    legacy,
                    company_code=company,
                    user_ids=[t for t in targets if t],
                    message=f"Reschedule requested for “{_text(ev.get('title')) or 'event'}”. Confirm via Interviews if linked.",
                    source="calendar_rsvp",
                    kind="reschedule_requested",
                    subject_key=event_id,
                )
                return {
                    "ok": True,
                    "request": serialize_reschedule_request(req),
                    "message": "Reschedule request recorded. The organizer must confirm any time change.",
                    "interview_linked": bool(interview_id),
                }

            conn.commit()

    targets = [_text(ev.get("organizer_user_id")), _text(ev.get("owner_user_id"))]
    notify_personal(
        legacy,
        company_code=company,
        user_ids=[t for t in targets if t],
        message=f"Guest RSVP ({act}) for “{_text(ev.get('title')) or 'event'}”.",
        source="calendar_rsvp",
        kind="rsvp_received",
        subject_key=event_id,
    )
    return {"ok": True, "rsvp_status": new_status, "action": act}


def serialize_reschedule_request(row: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "request_id": str(row.get("request_id")),
        "event_id": str(row.get("event_id")),
        "guest_id": str(row.get("guest_id")) if row.get("guest_id") else None,
        "interview_id": _text(row.get("interview_id")) or None,
        "status": _text(row.get("status")) or "pending",
        "preferred_times": row.get("preferred_times") if isinstance(row.get("preferred_times"), list) else [],
        "note": row.get("note"),
        "created_at": _iso(row.get("created_at")),
        "resolved_at": _iso(row.get("resolved_at")),
    }


def list_reschedule_requests(
    legacy: Any,
    *,
    company_code: str,
    event_id: str | None = None,
    status: str = "pending",
) -> list[dict[str, Any]]:
    company = _text(company_code).upper()
    with legacy.db_connect() as conn:
        with conn.cursor() as cur:
            calendar_schema.ensure_calendar_schema(cur)
            sql = """
                SELECT * FROM calendar_reschedule_requests
                WHERE company_code=%s
            """
            params: list[Any] = [company]
            if event_id:
                sql += " AND event_id=%s"
                params.append(event_id)
            if status:
                sql += " AND status=%s"
                params.append(_text(status).lower())
            sql += " ORDER BY created_at DESC LIMIT 100"
            cur.execute(sql, params)
            return [serialize_reschedule_request(dict(r)) for r in cur.fetchall() or []]


def resolve_reschedule_request(
    legacy: Any,
    *,
    company_code: str,
    request_id: str,
    actor_user_id: str,
    decision: str,
    resolution_note: str | None = None,
) -> dict[str, Any]:
    """Organizer accepts/declines request record — does NOT change event time."""
    company = _text(company_code).upper()
    dec = _text(decision).lower()
    if dec not in {"accepted", "declined", "cancelled"}:
        raise CalendarParticipationError("invalid_decision", "decision must be accepted, declined, or cancelled.")
    with legacy.db_connect() as conn:
        with conn.cursor() as cur:
            calendar_schema.ensure_calendar_schema(cur)
            cur.execute(
                """
                SELECT * FROM calendar_reschedule_requests
                WHERE company_code=%s AND request_id=%s FOR UPDATE
                """,
                (company, request_id),
            )
            row = cur.fetchone()
            if not row:
                raise CalendarParticipationError("request_not_found", "Request not found.", http_status=404)
            req = dict(row)
            if _text(req.get("status")) != "pending":
                return {"ok": True, "idempotent": True, "request": serialize_reschedule_request(req)}
            cur.execute(
                """
                UPDATE calendar_reschedule_requests
                SET status=%s, resolved_at=now(), resolved_by_user_id=%s,
                    resolution_note=%s, updated_at=now()
                WHERE company_code=%s AND request_id=%s
                RETURNING *
                """,
                (dec, _text(actor_user_id), _text(resolution_note) or None, company, request_id),
            )
            updated = dict(cur.fetchone())
            _audit(
                cur,
                legacy,
                company_code=company,
                event_id=str(req.get("event_id")),
                actor_user_id=actor_user_id,
                action="reschedule_request_resolved",
                before={"status": "pending"},
                after={"status": dec, "request_id": request_id},
            )
        conn.commit()
    return {
        "ok": True,
        "request": serialize_reschedule_request(updated),
        "safe_next_action": "use_interview_reschedule" if updated.get("interview_id") and dec == "accepted" else "none",
        "message": (
            "Request accepted. For interview-linked events, confirm the new time via Interview reschedule."
            if dec == "accepted" and updated.get("interview_id")
            else "Request updated. Event time was not changed by this action."
        ),
    }


# ---------------------------------------------------------------------------
# Delivery outbox
# ---------------------------------------------------------------------------


def _intent_payload(
    *,
    purpose: str,
    recipient_type: str,
    lifecycle: str | None,
    recipient: Mapping[str, Any],
    payload: Mapping[str, Any],
    preferred_channel_hint: str | None = None,
    urgency: str = "normal",
    locale: str = "en",
) -> dict[str, Any]:
    import wathefni_communication as comm

    return {
        **dict(payload),
        "communication_purpose": comm.normalize_purpose(purpose),
        "recipient_type": recipient_type,
        "lifecycle": lifecycle,
        "recipient": dict(recipient),
        "preferred_channel_hint": preferred_channel_hint,
        "urgency": urgency,
        "locale": locale,
    }


def enqueue_delivery(
    cur: Any,
    legacy: Any,
    *,
    company_code: str,
    event_id: str,
    channel: str,
    purpose: str,
    idempotency_key: str,
    payload: Mapping[str, Any],
    guest_id: str | None = None,
    reminder_id: str | None = None,
    recipient_type: str | None = None,
    lifecycle: str | None = None,
    preferred_channel_hint: str | None = None,
) -> dict[str, Any]:
    """Enqueue a Calendar-domain communication intent.

    ``channel`` is stored as ``routed`` (handoff). Provider selection happens only
    in ``wathefni_communication`` when the worker processes the row.
    """
    company = _text(company_code).upper()
    key = _text(idempotency_key)
    # Infer recipient classification from payload when callers omit it.
    rtype = _text(recipient_type)
    if not rtype:
        if guest_id or payload.get("guest_id") or payload.get("email") or payload.get("phone"):
            rtype = "candidate" if payload.get("app_key") or payload.get("person_key") or _text(payload.get("guest_kind")) == "candidate" else "external_guest"
        elif payload.get("user_id"):
            rtype = "employee"
        else:
            rtype = "unknown"
    recipient = {
        "user_id": payload.get("user_id"),
        "guest_id": guest_id or payload.get("guest_id"),
        "email": payload.get("email"),
        "phone": payload.get("phone"),
        "display_name": payload.get("display_name"),
        "guest_kind": payload.get("guest_kind"),
        "app_key": payload.get("app_key"),
        "person_key": payload.get("person_key"),
        "preferred_channel": preferred_channel_hint or payload.get("channel"),
    }
    hint = preferred_channel_hint or _text(payload.get("channel") or channel)
    if hint in {"in_app", "routed", ""}:
        hint = None
    intent = _intent_payload(
        purpose=purpose,
        recipient_type=rtype,
        lifecycle=lifecycle,
        recipient=recipient,
        payload=payload,
        preferred_channel_hint=hint,
    )
    cur.execute(
        """
        INSERT INTO calendar_delivery_outbox
          (delivery_id, company_code, event_id, guest_id, reminder_id, channel, purpose,
           idempotency_key, payload, status, next_attempt_at)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,'queued',now())
        ON CONFLICT (company_code, idempotency_key) DO NOTHING
        RETURNING *
        """,
        (
            str(uuid4()),
            company,
            event_id,
            guest_id,
            reminder_id,
            "routed",
            _text(purpose),
            key,
            _json(legacy, intent),
        ),
    )
    row = cur.fetchone()
    if row:
        return {"ok": True, "enqueued": True, "delivery": dict(row)}
    cur.execute(
        "SELECT * FROM calendar_delivery_outbox WHERE company_code=%s AND idempotency_key=%s",
        (company, key),
    )
    existing = cur.fetchone()
    return {"ok": True, "enqueued": False, "idempotent": True, "delivery": dict(existing or {})}


def queue_guest_invite(
    legacy: Any,
    *,
    company_code: str,
    event_id: str,
    guest_id: str,
    channel: str | None = None,
    actor_user_id: str | None = None,
) -> dict[str, Any]:
    company = _text(company_code).upper()
    with legacy.db_connect() as conn:
        with conn.cursor() as cur:
            calendar_schema.ensure_calendar_schema(cur)
            cur.execute(
                "SELECT * FROM calendar_guests WHERE company_code=%s AND guest_id=%s AND event_id=%s",
                (company, guest_id, event_id),
            )
            guest = cur.fetchone()
            if not guest:
                raise CalendarParticipationError("guest_not_found", "Guest not found.", http_status=404)
            guest = dict(guest)
            # Hint only — canonical router applies company pre-hire / external-guest policy.
            hint = _text(channel) or _text(guest.get("invite_channel")) or None
            if hint in {"none", "routed", "in_app"}:
                hint = None
            if hint and hint not in {"email", "whatsapp"}:
                hint = None
            token = issue_guest_token(cur, company_code=company, event_id=event_id, guest_id=guest_id)
            invite_path = f"/calendar/guest/{token['token']}"
            guest_kind = _text(guest.get("guest_kind")) or "external"
            recipient_type = "candidate" if guest_kind == "candidate" or guest.get("app_key") or guest.get("person_key") else "external_guest"
            payload = {
                "guest_id": guest_id,
                "invite_path": invite_path,
                "token_expires_at": token["expires_at"],
                "email": guest.get("email"),
                "phone": guest.get("phone"),
                "display_name": guest.get("display_name"),
                "person_key": guest.get("person_key"),
                "app_key": guest.get("app_key"),
                "guest_kind": guest_kind,
            }
            key = f"guest_invite:{event_id}:{guest_id}:{hint or 'policy'}:{token['token_id']}"
            result = enqueue_delivery(
                cur,
                legacy,
                company_code=company,
                event_id=event_id,
                guest_id=guest_id,
                channel="routed",
                purpose="guest_invite",
                idempotency_key=key,
                payload=payload,
                recipient_type=recipient_type,
                preferred_channel_hint=hint,
            )
            cur.execute(
                """
                UPDATE calendar_guests
                SET invite_channel=%s, invite_status='queued', last_invited_at=now(), updated_at=now()
                WHERE company_code=%s AND guest_id=%s
                """,
                (hint or _text(guest.get("invite_channel")) or "none", company, guest_id),
            )
            _audit(
                cur,
                legacy,
                company_code=company,
                event_id=event_id,
                actor_user_id=actor_user_id,
                action="guest_invite_queued",
                before={},
                after={
                    "guest_id": guest_id,
                    "channel_hint": hint,
                    "delivery_id": str((result.get("delivery") or {}).get("delivery_id") or ""),
                    "routed": True,
                },
            )
        conn.commit()
    return {"ok": True, "invite_path": invite_path, **result}


def process_delivery_item(legacy: Any, cur: Any, item: Mapping[str, Any]) -> dict[str, Any]:
    """Handoff one Calendar intent to the canonical communication authority.

    Never selects provider credentials or company channel accounts here.
    """
    import wathefni_communication as comm

    delivery_id = str(item.get("delivery_id"))
    company = _text(item.get("company_code")).upper()
    purpose = _text(item.get("purpose"))
    payload = item.get("payload") if isinstance(item.get("payload"), dict) else {}
    event_id = str(item.get("event_id"))

    cur.execute(
        "SELECT title, status, start_at, timezone, location FROM calendar_events WHERE company_code=%s AND event_id=%s",
        (company, event_id),
    )
    event = dict(cur.fetchone() or {})
    if _text(event.get("status")).lower() == "cancelled" and purpose in {
        "guest_invite",
        "attendee_invite",
        "guest_reminder",
        "attendee_reminder",
    }:
        cur.execute(
            """
            UPDATE calendar_delivery_outbox
            SET status='cancelled', updated_at=now(), last_error='event_cancelled'
            WHERE delivery_id=%s
            """,
            (delivery_id,),
        )
        return {"ok": True, "cancelled": True}

    public_base = _text(os.environ.get("WATHEFNI_PUBLIC_BASE_URL") or os.environ.get("WATHEFNI_DASHBOARD_PUBLIC_ORIGIN") or "")
    invite_path = _text(payload.get("invite_path"))
    link = f"{public_base.rstrip('/')}{invite_path}" if public_base and invite_path else invite_path
    title = _text(event.get("title")) or "Wathefni event"
    recipient = payload.get("recipient") if isinstance(payload.get("recipient"), dict) else {
        "user_id": payload.get("user_id"),
        "guest_id": item.get("guest_id") or payload.get("guest_id"),
        "email": payload.get("email"),
        "phone": payload.get("phone"),
        "display_name": payload.get("display_name"),
        "guest_kind": payload.get("guest_kind"),
        "app_key": payload.get("app_key"),
        "person_key": payload.get("person_key"),
    }
    msg = _text(payload.get("message"))
    if not msg:
        if purpose in {"guest_cancel", "attendee_cancel"}:
            msg = f"Cancelled: “{title}”."
        elif purpose in {"guest_update", "attendee_update"}:
            msg = f"Updated: “{title}”."
        elif "reminder" in purpose:
            msg = f"Reminder: “{title}” starts soon ({_iso(event.get('start_at'))})."
        else:
            msg = f"You are invited: {title}."
            if link:
                msg = f"{msg} Respond: {link}"

    intent = {
        "company_code": company,
        "purpose": payload.get("communication_purpose") or purpose,
        "recipient_type": payload.get("recipient_type"),
        "lifecycle": payload.get("lifecycle"),
        "recipient": recipient,
        "event_id": event_id,
        "subject_type": "calendar_event",
        "subject_key": event_id,
        "preferred_channel_hint": payload.get("preferred_channel_hint"),
        "idempotency_key": _text(item.get("idempotency_key")),
        "payload": {
            **payload,
            "title": title,
            "message": msg,
            "link": link,
            "invite_path": invite_path,
        },
    }

    try:
        result = comm.deliver_intent(legacy, intent)
    except Exception as exc:
        result = {"ok": False, "error": str(exc)[:300], "attempts": []}

    ok = bool(result.get("ok"))
    provider_ref = _text(result.get("provider_ref")) or None
    error = None if ok else _text(result.get("error")) or "delivery_failed"
    channel_used = _text(result.get("channel_used")) or "routed"

    if ok:
        cur.execute(
            """
            UPDATE calendar_delivery_outbox
            SET status='delivered', delivered_at=now(), provider_ref=%s,
                lease_owner=NULL, lease_expires_at=NULL, updated_at=now(), last_error=NULL
            WHERE delivery_id=%s
            """,
            (provider_ref or f"{channel_used}:{delivery_id}", delivery_id),
        )
        if item.get("guest_id") and purpose == "guest_invite":
            cur.execute(
                """
                UPDATE calendar_guests
                SET invite_status='delivered', last_delivery_error=NULL, updated_at=now()
                WHERE company_code=%s AND guest_id=%s
                """,
                (company, str(item.get("guest_id"))),
            )
        _audit(
            cur,
            legacy,
            company_code=company,
            event_id=event_id,
            actor_user_id=None,
            action="delivery_delivered",
            before={},
            after={
                "delivery_id": delivery_id,
                "channel_used": channel_used,
                "purpose": purpose,
                "provider_ref": provider_ref,
                "lifecycle": result.get("lifecycle"),
                "fallback_used": result.get("fallback_used"),
            },
        )
        return {"ok": True, "delivered": True, "provider_ref": provider_ref, "channel_used": channel_used, "result": result}

    attempts = int(item.get("attempt_count") or 0) + 1
    dead = attempts >= 8 or error in {"purpose_not_allowed", "consent_required"}
    retryable = bool(result.get("retryable")) or error in {"quiet_hours", "no_qualified_channel", "all_channels_failed"}
    if error == "no_qualified_channel":
        # Policy misconfiguration: retry briefly then dead — do not spam forever.
        dead = attempts >= 3
    delay = min(7200, 30 * (2 ** min(attempts, 6)))
    cur.execute(
        """
        UPDATE calendar_delivery_outbox
        SET status=%s, attempt_count=%s, last_error=%s,
            next_attempt_at=now() + make_interval(secs => %s),
            lease_owner=NULL, lease_expires_at=NULL, updated_at=now()
        WHERE delivery_id=%s
        """,
        ("dead" if dead else "queued", attempts, error, 0 if dead else delay, delivery_id),
    )
    if item.get("guest_id") and purpose == "guest_invite":
        cur.execute(
            """
            UPDATE calendar_guests
            SET invite_status=%s, last_delivery_error=%s, updated_at=now()
            WHERE company_code=%s AND guest_id=%s
            """,
            ("dead" if dead else "failed", error, company, str(item.get("guest_id"))),
        )
    _audit(
        cur,
        legacy,
        company_code=company,
        event_id=event_id,
        actor_user_id=None,
        action="delivery_failed",
        before={},
        after={
            "delivery_id": delivery_id,
            "error": error,
            "attempt_count": attempts,
            "status": "dead" if dead else "queued",
            "retryable": retryable,
            "attempts": result.get("attempts"),
        },
    )
    return {"ok": False, "error": error, "dead": dead, "result": result}


def claim_next_delivery(cur: Any, *, worker_id: str, lease_seconds: int = 120) -> dict[str, Any] | None:
    cur.execute(
        """
        UPDATE calendar_delivery_outbox
        SET status='queued', lease_owner=NULL, lease_expires_at=NULL, updated_at=now()
        WHERE status='processing' AND lease_expires_at IS NOT NULL AND lease_expires_at < now()
        """
    )
    cur.execute(
        """
        WITH next AS (
          SELECT delivery_id FROM calendar_delivery_outbox
          WHERE status='queued' AND next_attempt_at <= now()
          ORDER BY next_attempt_at ASC
          FOR UPDATE SKIP LOCKED
          LIMIT 1
        )
        UPDATE calendar_delivery_outbox d
        SET status='processing',
            lease_owner=%s,
            lease_expires_at=now() + make_interval(secs => %s),
            updated_at=now()
        FROM next
        WHERE d.delivery_id=next.delivery_id
        RETURNING d.*
        """,
        (worker_id, lease_seconds),
    )
    row = cur.fetchone()
    return dict(row) if row else None


def run_delivery_once(legacy: Any, *, limit: int = 50) -> dict[str, Any]:
    worker_id = f"cal-delivery:{os.getpid()}"
    processed = 0
    results: list[dict[str, Any]] = []
    with legacy.db_connect() as conn:
        with conn.cursor() as cur:
            calendar_schema.ensure_calendar_schema(cur)
            for _ in range(max(1, limit)):
                item = claim_next_delivery(cur, worker_id=worker_id)
                if not item:
                    break
                results.append(process_delivery_item(legacy, cur, item))
                processed += 1
                conn.commit()
    return {"ok": True, "processed": processed, "results": results}


# ---------------------------------------------------------------------------
# Reminders
# ---------------------------------------------------------------------------


def schedule_event_reminders(
    cur: Any,
    legacy: Any,
    *,
    company_code: str,
    event_id: str,
    offsets_minutes: Sequence[int] | None = None,
    channels: Sequence[str] | None = None,
) -> int:
    """Create pending reminders for attendees+guests. Does not create calendar blocks."""
    company = _text(company_code).upper()
    cur.execute(
        "SELECT start_at, status, timezone FROM calendar_events WHERE company_code=%s AND event_id=%s",
        (company, event_id),
    )
    event = cur.fetchone()
    if not event:
        return 0
    event = dict(event)
    if _text(event.get("status")).lower() in {"cancelled", "completed"}:
        return 0
    start = event.get("start_at")
    if not start:
        return 0
    if start.tzinfo is None:
        start = start.replace(tzinfo=timezone.utc)
    offsets = list(offsets_minutes) if offsets_minutes is not None else [60, 15]
    chans = list(channels) if channels else ["in_app"]
    attendees = store.fetch_attendees(cur, company, event_id)
    guests = store.fetch_guests(cur, company, event_id)
    created = 0
    for offset in offsets:
        fire_at = start - timedelta(minutes=int(offset))
        if fire_at < _now() - timedelta(minutes=1):
            continue
        for att in attendees:
            if _text(att.get("rsvp_status")).lower() == "removed":
                continue
            uid = _text(att.get("user_id"))
            for ch in chans:
                key = f"reminder:{event_id}:user:{uid}:{offset}:{ch}"
                cur.execute(
                    """
                    INSERT INTO calendar_reminders
                      (reminder_id, event_id, company_code, user_id, kind, offset_minutes, channel,
                       fire_at, status, idempotency_key, next_attempt_at)
                    VALUES (%s,%s,%s,%s,'event',%s,%s,%s,'pending',%s,%s)
                    ON CONFLICT DO NOTHING
                    """,
                    (str(uuid4()), event_id, company, uid, int(offset), ch, fire_at, key, fire_at),
                )
                if cur.rowcount:
                    created += 1
        for guest in guests:
            if _text(guest.get("rsvp_status")).lower() == "removed":
                continue
            gid = str(guest.get("guest_id"))
            ch = _text(guest.get("invite_channel")) if _text(guest.get("invite_channel")) in {"email", "whatsapp"} else "email"
            key = f"reminder:{event_id}:guest:{gid}:{offset}:{ch}"
            cur.execute(
                """
                INSERT INTO calendar_reminders
                  (reminder_id, event_id, company_code, guest_id, kind, offset_minutes, channel,
                   fire_at, status, idempotency_key, next_attempt_at)
                VALUES (%s,%s,%s,%s,'event',%s,%s,%s,'pending',%s,%s)
                ON CONFLICT DO NOTHING
                """,
                (str(uuid4()), event_id, company, gid, int(offset), ch, fire_at, key, fire_at),
            )
            if cur.rowcount:
                created += 1
    return created


def cancel_future_reminders(cur: Any, *, company_code: str, event_id: str, reason: str = "event_changed") -> int:
    cur.execute(
        """
        UPDATE calendar_reminders
        SET status='cancelled', last_error=%s, updated_at=now(),
            lease_owner=NULL, lease_expires_at=NULL
        WHERE company_code=%s AND event_id=%s
          AND status IN ('pending','failed')
          AND (sent_at IS NULL)
        RETURNING reminder_id
        """,
        (reason, _text(company_code).upper(), event_id),
    )
    return len(cur.fetchall() or [])


def recalculate_reminders(cur: Any, legacy: Any, *, company_code: str, event_id: str) -> dict[str, Any]:
    cancelled = cancel_future_reminders(cur, company_code=company_code, event_id=event_id, reason="recalculated")
    created = schedule_event_reminders(cur, legacy, company_code=company_code, event_id=event_id)
    return {"cancelled": cancelled, "created": created}


def claim_next_reminder(cur: Any, *, worker_id: str, lease_seconds: int = 120) -> dict[str, Any] | None:
    cur.execute(
        """
        UPDATE calendar_reminders
        SET status='pending', lease_owner=NULL, lease_expires_at=NULL
        WHERE status='processing' AND lease_expires_at IS NOT NULL AND lease_expires_at < now()
        """
    )
    cur.execute(
        """
        WITH next AS (
          SELECT reminder_id FROM calendar_reminders
          WHERE status IN ('pending','failed')
            AND fire_at IS NOT NULL AND fire_at <= now()
            AND (next_attempt_at IS NULL OR next_attempt_at <= now())
          ORDER BY fire_at ASC
          FOR UPDATE SKIP LOCKED
          LIMIT 1
        )
        UPDATE calendar_reminders r
        SET status='processing',
            lease_owner=%s,
            lease_expires_at=now() + make_interval(secs => %s),
            updated_at=now()
        FROM next
        WHERE r.reminder_id=next.reminder_id
        RETURNING r.*
        """,
        (worker_id, lease_seconds),
    )
    row = cur.fetchone()
    return dict(row) if row else None


def process_reminder(legacy: Any, cur: Any, item: Mapping[str, Any]) -> dict[str, Any]:
    company = _text(item.get("company_code")).upper()
    event_id = str(item.get("event_id"))
    reminder_id = str(item.get("reminder_id"))
    cur.execute(
        "SELECT title, status, start_at, timezone FROM calendar_events WHERE company_code=%s AND event_id=%s",
        (company, event_id),
    )
    event = dict(cur.fetchone() or {})
    if _text(event.get("status")).lower() == "cancelled":
        cur.execute(
            "UPDATE calendar_reminders SET status='cancelled', last_error='event_cancelled', updated_at=now() WHERE reminder_id=%s",
            (reminder_id,),
        )
        return {"ok": True, "cancelled": True}

    channel = _text(item.get("channel")) or "in_app"
    title = _text(event.get("title")) or "event"
    msg = f"Reminder: “{title}” starts soon ({_iso(event.get('start_at'))})."

    if item.get("user_id"):
        # Idempotent delivery row — canonical router decides channels (no direct notify).
        key = _text(item.get("idempotency_key")) or f"reminder_send:{reminder_id}"
        enqueue_delivery(
            cur,
            legacy,
            company_code=company,
            event_id=event_id,
            reminder_id=reminder_id,
            channel="routed",
            purpose="attendee_reminder",
            idempotency_key=key,
            payload={"user_id": _text(item.get("user_id")), "message": msg},
            recipient_type="employee",
            lifecycle="post_hire",
        )
    elif item.get("guest_id"):
        key = _text(item.get("idempotency_key")) or f"reminder_send:{reminder_id}"
        cur.execute(
            "SELECT email, phone, invite_channel, guest_kind, app_key, person_key FROM calendar_guests WHERE company_code=%s AND guest_id=%s",
            (company, str(item.get("guest_id"))),
        )
        guest = dict(cur.fetchone() or {})
        hint = _text(guest.get("invite_channel")) if _text(guest.get("invite_channel")) in {"email", "whatsapp"} else None
        gkind = _text(guest.get("guest_kind")) or "external"
        rtype = "candidate" if gkind == "candidate" or guest.get("app_key") or guest.get("person_key") else "external_guest"
        enqueue_delivery(
            cur,
            legacy,
            company_code=company,
            event_id=event_id,
            guest_id=str(item.get("guest_id")),
            reminder_id=reminder_id,
            channel="routed",
            purpose="guest_reminder",
            idempotency_key=key,
            payload={
                "email": guest.get("email"),
                "phone": guest.get("phone"),
                "message": msg,
                "guest_kind": gkind,
                "app_key": guest.get("app_key"),
                "person_key": guest.get("person_key"),
            },
            recipient_type=rtype,
            preferred_channel_hint=hint,
        )

    cur.execute(
        """
        UPDATE calendar_reminders
        SET status='sent', sent_at=now(), lease_owner=NULL, lease_expires_at=NULL,
            updated_at=now(), last_error=NULL
        WHERE reminder_id=%s
        """,
        (reminder_id,),
    )
    return {"ok": True, "sent": True, "reminder_id": reminder_id}


def run_reminders_once(legacy: Any, *, limit: int = 50) -> dict[str, Any]:
    worker_id = f"cal-reminder:{os.getpid()}"
    processed = 0
    results: list[dict[str, Any]] = []
    with legacy.db_connect() as conn:
        with conn.cursor() as cur:
            calendar_schema.ensure_calendar_schema(cur)
            for _ in range(max(1, limit)):
                item = claim_next_reminder(cur, worker_id=worker_id)
                if not item:
                    break
                try:
                    results.append(process_reminder(legacy, cur, item))
                except Exception as exc:
                    cur.execute(
                        """
                        UPDATE calendar_reminders
                        SET status='failed', attempt_count=attempt_count+1,
                            last_error=%s, next_attempt_at=now() + interval '5 minutes',
                            lease_owner=NULL, lease_expires_at=NULL, updated_at=now()
                        WHERE reminder_id=%s
                        """,
                        (str(exc)[:300], str(item.get("reminder_id"))),
                    )
                    results.append({"ok": False, "error": str(exc)[:200]})
                processed += 1
                conn.commit()
    # Also flush delivery queue
    delivery = run_delivery_once(legacy, limit=limit)
    return {"ok": True, "reminders_processed": processed, "results": results, "delivery": delivery}


# ---------------------------------------------------------------------------
# Event change / cancel side-effects
# ---------------------------------------------------------------------------


def on_event_mutated(
    cur: Any,
    legacy: Any,
    *,
    company_code: str,
    event_id: str,
    actor_user_id: str | None,
    before: Mapping[str, Any],
    after: Mapping[str, Any],
    cancelled: bool = False,
) -> dict[str, Any]:
    """Notify attendees/guests and recalculate reminders. Never deletes the event."""
    company = _text(company_code).upper()
    attendees = store.fetch_attendees(cur, company, event_id)
    guests = store.fetch_guests(cur, company, event_id)
    title = _text(after.get("title") or before.get("title")) or "event"

    if cancelled:
        cancel_future_reminders(cur, company_code=company, event_id=event_id, reason="event_cancelled")
        # Cancel pending deliveries that aren't already delivered
        cur.execute(
            """
            UPDATE calendar_delivery_outbox
            SET status='cancelled', updated_at=now(), last_error='event_cancelled'
            WHERE company_code=%s AND event_id=%s
              AND status IN ('queued','failed','not_queued','processing')
            """,
            (company, event_id),
        )
        # Revoke guest tokens
        cur.execute(
            """
            UPDATE calendar_guest_tokens
            SET revoked_at=now()
            WHERE company_code=%s AND event_id=%s AND revoked_at IS NULL
            """,
            (company, event_id),
        )
        user_ids = [_text(a.get("user_id")) for a in attendees if _text(a.get("rsvp_status")) != "removed"]
        # Queue cancel notices idempotently — router decides channels.
        for uid in user_ids:
            enqueue_delivery(
                cur,
                legacy,
                company_code=company,
                event_id=event_id,
                channel="routed",
                purpose="attendee_cancel",
                idempotency_key=f"cancel:{event_id}:user:{uid}:{after.get('version')}",
                payload={"user_id": uid, "message": f"Cancelled: “{title}”."},
                recipient_type="employee",
                lifecycle="post_hire",
            )
        for g in guests:
            gid = str(g.get("guest_id"))
            hint = _text(g.get("invite_channel")) if _text(g.get("invite_channel")) in {"email", "whatsapp"} else None
            gkind = _text(g.get("guest_kind")) or "external"
            rtype = "candidate" if gkind == "candidate" or g.get("app_key") or g.get("person_key") else "external_guest"
            enqueue_delivery(
                cur,
                legacy,
                company_code=company,
                event_id=event_id,
                guest_id=gid,
                channel="routed",
                purpose="guest_cancel",
                idempotency_key=f"cancel:{event_id}:guest:{gid}:{after.get('version')}",
                payload={
                    "email": g.get("email"),
                    "phone": g.get("phone"),
                    "message": f"Cancelled: “{title}”.",
                    "guest_kind": gkind,
                    "app_key": g.get("app_key"),
                    "person_key": g.get("person_key"),
                },
                recipient_type=rtype,
                preferred_channel_hint=hint,
            )
        return {"ok": True, "cancelled_notices": True}

    # Time/location/link change
    before_start = before.get("start_at")
    after_start = after.get("start_at")
    major = False
    try:
        if before_start and after_start:
            b = before_start if getattr(before_start, "tzinfo", None) else None
            # compare iso strings via store parse
            bs = store._parse_dt(store._iso(before_start), field="start_at") if before_start else None
            as_ = store._parse_dt(store._iso(after_start), field="start_at") if after_start else None
            if bs and as_ and abs((as_ - bs).total_seconds()) >= MAJOR_TIME_CHANGE_SECONDS:
                major = True
    except Exception:
        major = False

    if major and RECONFIRM_ON_MAJOR_TIME_CHANGE:
        cur.execute(
            """
            UPDATE calendar_attendees
            SET rsvp_status='needs_action', response_at=NULL, rsvp_version=rsvp_version+1, updated_at=now()
            WHERE company_code=%s AND event_id=%s
              AND rsvp_status IN ('accepted','tentative')
              AND COALESCE(is_organizer,false)=false
            """,
            (company, event_id),
        )
        cur.execute(
            """
            UPDATE calendar_guests
            SET rsvp_status='needs_action', rsvp_version=rsvp_version+1, updated_at=now()
            WHERE company_code=%s AND event_id=%s
              AND rsvp_status IN ('accepted','tentative')
            """,
            (company, event_id),
        )
        # Re-issue tokens (revoke old)
        for g in guests:
            issue_guest_token(cur, company_code=company, event_id=event_id, guest_id=str(g.get("guest_id")))

    rem = recalculate_reminders(cur, legacy, company_code=company, event_id=event_id)
    user_ids = [_text(a.get("user_id")) for a in attendees if _text(a.get("rsvp_status")) != "removed"]
    for uid in user_ids:
        if uid == _text(actor_user_id):
            continue
        enqueue_delivery(
            cur,
            legacy,
            company_code=company,
            event_id=event_id,
            channel="routed",
            purpose="attendee_update",
            idempotency_key=f"update:{event_id}:user:{uid}:{after.get('version')}",
            payload={"user_id": uid, "message": f"Updated: “{title}”."},
            recipient_type="employee",
            lifecycle="post_hire",
        )
    return {"ok": True, "major_time_change": major, "reminders": rem}
