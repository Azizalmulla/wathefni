"""Wathefni Calendar event store — CRUD, OCC, attendees, guests, links, audit.

C1: manual timed events + personal_block. Interview authority mutations rejected.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Iterable, Mapping, Sequence
from uuid import uuid4

import concurrency_safety as _cs
from calendar_org_scope import get_org_scope_adapter

EVENT_TYPES = frozenset(
    {"meeting", "interview", "personal_block", "deadline", "hold", "out_of_office", "other"}
)
VISIBILITIES = frozenset({"private", "attendees_only", "team", "company"})
SENSITIVITIES = frozenset({"normal", "candidate_confidential", "sensitive"})
STATUSES = frozenset({"tentative", "confirmed", "cancelled", "completed"})
MANUAL_CREATE_TYPES = frozenset({"meeting", "personal_block", "deadline", "hold", "out_of_office", "other"})

# Fields that remain Interview-owned when an active interview link exists.
INTERVIEW_AUTHORITY_FIELDS = frozenset(
    {
        "start_at",
        "end_at",
        "timezone",
        "all_day",
        "status",
        "organizer_user_id",
        "title",
        "title_ar",
        "location",
        "meeting_url",
        "attendees",
        "guests",
    }
)


_CALENDAR_DEFAULT_MESSAGES: dict[str, str] = {
    "event_not_found": "This calendar event was not found. Refresh and try again.",
    "permission_denied": "You do not have permission to change this calendar event.",
}


class CalendarError(Exception):
    def __init__(
        self,
        code: str,
        *,
        message: str | None = None,
        http_status: int = 422,
        details: Mapping[str, Any] | None = None,
    ):
        resolved = message or _CALENDAR_DEFAULT_MESSAGES.get(code) or code
        super().__init__(resolved)
        self.code = code
        self.message = resolved
        self.http_status = http_status
        self.details = dict(details or {})

    def envelope(self) -> dict[str, Any]:
        out: dict[str, Any] = {"ok": False, "error": self.code, "message": self.message}
        if self.details:
            # Prefer nested conflict envelope fields at top level for clients.
            for key, value in self.details.items():
                if key not in out:
                    out[key] = value
            if "details" not in out:
                out["details"] = dict(self.details)
        return out


def _text(value: Any) -> str:
    return str(value or "").strip()


def _iso(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.isoformat()
    return str(value)


def _parse_dt(value: Any, *, field: str) -> datetime:
    raw = _text(value)
    if not raw:
        raise CalendarError("invalid_datetime", message=f"{field} is required")
    try:
        if raw.endswith("Z"):
            raw = raw[:-1] + "+00:00"
        dt = datetime.fromisoformat(raw)
    except ValueError as exc:
        raise CalendarError("invalid_datetime", message=f"Invalid {field}") from exc
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def _json(legacy: Any, value: Any) -> Any:
    if hasattr(legacy, "Json"):
        return legacy.Json(value if value is not None else {})
    return value if value is not None else {}


def _audit(cur: Any, legacy: Any, **kwargs: Any) -> None:
    before = kwargs.pop("before", None)
    after = kwargs.pop("after", None)
    cur.execute(
        """
        INSERT INTO calendar_event_audit
          (audit_id, event_id, company_code, actor_user_id, action, before, after, request_id)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
        """,
        (
            str(uuid4()),
            kwargs["event_id"],
            kwargs["company_code"],
            kwargs.get("actor_user_id"),
            kwargs["action"],
            _json(legacy, before),
            _json(legacy, after),
            kwargs.get("request_id"),
        ),
    )


def fetch_attendees(cur: Any, company_code: str, event_id: str) -> list[dict[str, Any]]:
    cur.execute(
        """
        SELECT * FROM calendar_attendees
        WHERE company_code=%s AND event_id=%s AND rsvp_status <> 'removed'
        ORDER BY is_organizer DESC, created_at ASC
        """,
        (company_code, event_id),
    )
    return [dict(r) for r in cur.fetchall()]


def fetch_guests(cur: Any, company_code: str, event_id: str) -> list[dict[str, Any]]:
    cur.execute(
        """
        SELECT * FROM calendar_guests
        WHERE company_code=%s AND event_id=%s AND rsvp_status <> 'removed'
        ORDER BY created_at ASC
        """,
        (company_code, event_id),
    )
    return [dict(r) for r in cur.fetchall()]


def fetch_links(cur: Any, company_code: str, event_id: str) -> list[dict[str, Any]]:
    cur.execute(
        """
        SELECT * FROM calendar_event_links
        WHERE company_code=%s AND event_id=%s
        ORDER BY created_at ASC
        """,
        (company_code, event_id),
    )
    return [dict(r) for r in cur.fetchall()]


def fetch_org_scopes(cur: Any, company_code: str, event_id: str) -> list[dict[str, Any]]:
    cur.execute(
        """
        SELECT * FROM calendar_event_org_scopes
        WHERE company_code=%s AND event_id=%s
        ORDER BY org_scope_id
        """,
        (company_code, event_id),
    )
    return [dict(r) for r in cur.fetchall()]


def serialize_attendee(row: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "attendee_id": str(row.get("attendee_id")),
        "user_id": _text(row.get("user_id")),
        "role": _text(row.get("role")) or "required",
        "rsvp_status": _text(row.get("rsvp_status")) or "needs_action",
        "rsvp_version": int(row.get("rsvp_version") or 1),
        "is_organizer": bool(row.get("is_organizer")),
        "response_at": _iso(row.get("response_at")),
    }


def serialize_guest(row: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "guest_id": str(row.get("guest_id")),
        "email": row.get("email"),
        "phone": row.get("phone"),
        "display_name": row.get("display_name"),
        "guest_kind": _text(row.get("guest_kind")) or "external",
        "person_key": row.get("person_key"),
        "app_key": row.get("app_key"),
        "rsvp_status": _text(row.get("rsvp_status")) or "needs_action",
        "rsvp_version": int(row.get("rsvp_version") or 1),
        "invite_channel": _text(row.get("invite_channel")) or "none",
        "invite_status": _text(row.get("invite_status")) or "not_queued",
        "last_invited_at": _iso(row.get("last_invited_at")),
        "last_delivery_error": row.get("last_delivery_error"),
    }


def serialize_link(row: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "link_id": str(row.get("link_id")),
        "source_workflow": _text(row.get("source_workflow")),
        "source_record_id": _text(row.get("source_record_id")),
        "link_status": _text(row.get("link_status")) or "active",
    }


def serialize_event(
    row: Mapping[str, Any],
    *,
    attendees: Sequence[Mapping[str, Any]] | None = None,
    guests: Sequence[Mapping[str, Any]] | None = None,
    links: Sequence[Mapping[str, Any]] | None = None,
    org_scopes: Sequence[Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    return {
        "event_id": str(row.get("event_id")),
        "company_code": _text(row.get("company_code")),
        "event_type": _text(row.get("event_type")),
        "title": row.get("title"),
        "title_ar": row.get("title_ar"),
        "description": row.get("description"),
        "description_ar": row.get("description_ar"),
        "visibility": _text(row.get("visibility")) or "attendees_only",
        "sensitivity": _text(row.get("sensitivity")) or "normal",
        "status": _text(row.get("status")) or "confirmed",
        "start_at": _iso(row.get("start_at")),
        "end_at": _iso(row.get("end_at")),
        "timezone": _text(row.get("timezone")) or "Asia/Kuwait",
        "all_day": bool(row.get("all_day")),
        "location": row.get("location"),
        "meeting_url": row.get("meeting_url"),
        "creator_user_id": _text(row.get("creator_user_id")),
        "organizer_user_id": _text(row.get("organizer_user_id")),
        "owner_user_id": _text(row.get("owner_user_id")) or None,
        "version": int(row.get("version") or 1),
        "created_at": _iso(row.get("created_at")),
        "updated_at": _iso(row.get("updated_at")),
        "updated_by_user_id": _text(row.get("updated_by_user_id")) or None,
        "cancelled_at": _iso(row.get("cancelled_at")),
        "completed_at": _iso(row.get("completed_at")),
        "metadata": dict(row.get("metadata") or {}) if isinstance(row.get("metadata"), dict) else {},
        "attendees": [serialize_attendee(a) for a in (attendees or [])],
        "guests": [serialize_guest(g) for g in (guests or [])],
        "links": [serialize_link(lnk) for lnk in (links or [])],
        "org_scope_ids": [_text(s.get("org_scope_id")) for s in (org_scopes or []) if _text(s.get("org_scope_id"))],
        "org_scopes": [
            {
                "org_scope_id": _text(s.get("org_scope_id")),
                "org_scope_kind": _text(s.get("org_scope_kind")) or None,
            }
            for s in (org_scopes or [])
        ],
    }


def load_event_bundle(cur: Any, company_code: str, event_id: str) -> dict[str, Any] | None:
    cur.execute(
        "SELECT * FROM calendar_events WHERE company_code=%s AND event_id=%s",
        (company_code, event_id),
    )
    row = cur.fetchone()
    if not row:
        return None
    event = dict(row)
    attendees = fetch_attendees(cur, company_code, event_id)
    guests = fetch_guests(cur, company_code, event_id)
    links = fetch_links(cur, company_code, event_id)
    scopes = fetch_org_scopes(cur, company_code, event_id)
    return {
        "row": event,
        "attendees": attendees,
        "guests": guests,
        "links": links,
        "org_scopes": scopes,
        "payload": serialize_event(event, attendees=attendees, guests=guests, links=links, org_scopes=scopes),
    }


def active_interview_link(links: Sequence[Mapping[str, Any]] | None) -> Mapping[str, Any] | None:
    for link in links or []:
        if _text(link.get("link_status")).lower() == "active" and _text(link.get("source_workflow")).lower() == "interview":
            return link
    return None


def _replace_attendees(
    cur: Any,
    *,
    company_code: str,
    event_id: str,
    organizer_user_id: str,
    attendees: Sequence[Mapping[str, Any]] | None,
) -> None:
    cur.execute(
        "DELETE FROM calendar_attendees WHERE company_code=%s AND event_id=%s",
        (company_code, event_id),
    )
    seen: set[str] = set()
    rows = list(attendees or [])
    # Ensure organizer is present.
    org = _text(organizer_user_id)
    if org and not any(_text(a.get("user_id")) == org for a in rows):
        rows.insert(0, {"user_id": org, "role": "organizer", "is_organizer": True})
    for item in rows:
        uid = _text(item.get("user_id"))
        if not uid or uid in seen:
            continue
        seen.add(uid)
        role = _text(item.get("role")) or ("organizer" if uid == org else "required")
        if role not in {"organizer", "required", "optional", "resource_owner"}:
            role = "required"
        is_org = bool(item.get("is_organizer")) or uid == org or role == "organizer"
        cur.execute(
            """
            INSERT INTO calendar_attendees
              (attendee_id, event_id, company_code, user_id, role, rsvp_status, is_organizer)
            VALUES (%s,%s,%s,%s,%s,'needs_action',%s)
            """,
            (str(uuid4()), event_id, company_code, uid, role, is_org),
        )


def _replace_guests(
    cur: Any,
    *,
    company_code: str,
    event_id: str,
    guests: Sequence[Mapping[str, Any]] | None,
) -> None:
    cur.execute(
        "DELETE FROM calendar_guests WHERE company_code=%s AND event_id=%s",
        (company_code, event_id),
    )
    for item in guests or []:
        email = _text(item.get("email")) or None
        phone = _text(item.get("phone")) or None
        display = _text(item.get("display_name")) or None
        if not email and not phone and not display and not _text(item.get("person_key")) and not _text(item.get("app_key")):
            continue
        kind = _text(item.get("guest_kind")) or "external"
        if kind not in {"candidate", "external", "other"}:
            kind = "external"
        channel = _text(item.get("invite_channel")) or "none"
        if channel not in {"email", "whatsapp", "none"}:
            channel = "none"
        cur.execute(
            """
            INSERT INTO calendar_guests
              (guest_id, event_id, company_code, email, phone, display_name, guest_kind,
               person_key, app_key, rsvp_status, invite_channel)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,'needs_action',%s)
            """,
            (
                str(uuid4()),
                event_id,
                company_code,
                email,
                phone,
                display,
                kind,
                _text(item.get("person_key")) or None,
                _text(item.get("app_key")) or None,
                channel,
            ),
        )


def _replace_org_scopes(
    cur: Any,
    *,
    company_code: str,
    event_id: str,
    org_scope_ids: Sequence[str] | None,
    adapter: Any,
) -> None:
    cur.execute(
        "DELETE FROM calendar_event_org_scopes WHERE company_code=%s AND event_id=%s",
        (company_code, event_id),
    )
    ids = [_text(x) for x in (org_scope_ids or []) if _text(x)]
    if not ids:
        return
    refs = {r.org_scope_id: r for r in adapter.resolve_scopes(company_code, ids)}
    for sid in ids:
        ref = refs.get(sid)
        cur.execute(
            """
            INSERT INTO calendar_event_org_scopes (event_id, company_code, org_scope_id, org_scope_kind)
            VALUES (%s,%s,%s,%s)
            ON CONFLICT DO NOTHING
            """,
            (event_id, company_code, sid, (ref.org_scope_kind if ref else None)),
        )


def create_manual_event(
    legacy: Any,
    *,
    company_code: str,
    actor_user_id: str,
    payload: Mapping[str, Any],
    request_id: str | None = None,
    actor_permissions: Iterable[Any] | None = None,
) -> dict[str, Any]:
    import calendar_conflicts as conflicts

    company = _text(company_code).upper()
    actor = _text(actor_user_id)
    if not company or not actor:
        raise CalendarError("company_required", http_status=401)

    event_type = _text(payload.get("event_type")) or "meeting"
    if event_type not in MANUAL_CREATE_TYPES:
        raise CalendarError("invalid_event_type", message="Reminders are not timed events; use meeting or personal_block.")
    if event_type == "reminder":
        raise CalendarError("reminder_not_timed_event", message="A reminder is not a timed event and must not create a busy block.")

    title = _text(payload.get("title"))
    if not title:
        raise CalendarError("title_required", message="Title is required.")
    start_at = _parse_dt(payload.get("start_at"), field="start_at")
    end_at = _parse_dt(payload.get("end_at"), field="end_at")
    if end_at < start_at:
        raise CalendarError("invalid_time_range", message="end_at must be >= start_at")

    visibility = _text(payload.get("visibility")) or "attendees_only"
    if visibility not in VISIBILITIES:
        raise CalendarError("invalid_visibility")
    sensitivity = _text(payload.get("sensitivity")) or "normal"
    if sensitivity not in SENSITIVITIES:
        raise CalendarError("invalid_sensitivity")
    status = _text(payload.get("status")) or "confirmed"
    if status not in STATUSES or status == "cancelled":
        status = "confirmed"
    timezone_name = _text(payload.get("timezone")) or "Asia/Kuwait"
    organizer = _text(payload.get("organizer_user_id")) or actor
    owner = _text(payload.get("owner_user_id")) or (actor if event_type == "personal_block" else organizer)
    attendees_payload = payload.get("attendees") if isinstance(payload.get("attendees"), list) else []
    all_day = bool(payload.get("all_day"))

    adapter = get_org_scope_adapter(legacy)
    org_scope_ids = payload.get("org_scope_ids")
    if not isinstance(org_scope_ids, list):
        org_scope_ids = []
    org_scope_ids = [_text(x) for x in org_scope_ids if _text(x)]
    if not org_scope_ids and visibility in {"team"}:
        primary = adapter.primary_scope_for_user(company, organizer)
        if primary:
            org_scope_ids = [primary]

    event_id = str(uuid4())
    with legacy.db_connect() as conn:
        with conn.cursor() as cur:
            try:
                conflict_result = conflicts.require_no_blocking_conflicts(
                    cur,
                    legacy,
                    company_code=company,
                    start=start_at,
                    end=end_at,
                    timezone_name=timezone_name,
                    all_day=all_day,
                    organizer_user_id=organizer,
                    attendees=attendees_payload,
                    override_conflicts=bool(payload.get("override_conflicts")),
                    override_reason=_text(payload.get("override_reason")) or None,
                    actor_permissions=actor_permissions,
                    include_interview_legacy=True,
                    include_calendar_events=True,
                )
            except conflicts.SchedulingConflictError as exc:
                raise CalendarError(
                    exc.code,
                    message=exc.message,
                    http_status=exc.http_status,
                    details=exc.envelope(),
                ) from exc

            cur.execute(
                """
                INSERT INTO calendar_events (
                  event_id, company_code, event_type, title, title_ar, description, description_ar,
                  visibility, sensitivity, status, start_at, end_at, timezone, all_day,
                  location, meeting_url, creator_user_id, organizer_user_id, owner_user_id,
                  version, updated_by_user_id, metadata
                ) VALUES (
                  %s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,1,%s,%s
                )
                RETURNING *
                """,
                (
                    event_id,
                    company,
                    event_type,
                    title,
                    _text(payload.get("title_ar")) or None,
                    payload.get("description"),
                    payload.get("description_ar"),
                    visibility,
                    sensitivity,
                    status,
                    start_at,
                    end_at,
                    timezone_name,
                    all_day,
                    _text(payload.get("location")) or None,
                    _text(payload.get("meeting_url")) or None,
                    actor,
                    organizer,
                    owner or None,
                    actor,
                    _json(legacy, payload.get("metadata") if isinstance(payload.get("metadata"), dict) else {}),
                ),
            )
            row = dict(cur.fetchone())
            _replace_attendees(
                cur,
                company_code=company,
                event_id=event_id,
                organizer_user_id=organizer,
                attendees=attendees_payload,
            )
            _replace_guests(
                cur,
                company_code=company,
                event_id=event_id,
                guests=payload.get("guests") if isinstance(payload.get("guests"), list) else [],
            )
            _replace_org_scopes(
                cur,
                company_code=company,
                event_id=event_id,
                org_scope_ids=org_scope_ids,
                adapter=adapter,
            )
            # Optional non-interview workflow link (manual uniqueness proof / personal).
            link = payload.get("link") if isinstance(payload.get("link"), dict) else None
            if link:
                sw = _text(link.get("source_workflow"))
                sr = _text(link.get("source_record_id"))
                if sw and sr:
                    if sw.lower() == "interview":
                        raise CalendarError(
                            "interview_authority_required",
                            message="Interview-linked events must be created via Interview services.",
                            http_status=422,
                        )
                    try:
                        cur.execute(
                            """
                            INSERT INTO calendar_event_links
                              (link_id, company_code, event_id, source_workflow, source_record_id, link_status)
                            VALUES (%s,%s,%s,%s,%s,'active')
                            """,
                            (str(uuid4()), company, event_id, sw, sr),
                        )
                    except Exception as exc:
                        raise CalendarError(
                            "workflow_link_conflict",
                            message="An active calendar link already exists for this workflow record.",
                            http_status=409,
                            details={"source_workflow": sw, "source_record_id": sr},
                        ) from exc
            _audit(
                cur,
                legacy,
                company_code=company,
                event_id=event_id,
                actor_user_id=actor,
                action="created",
                before={},
                after={"event_id": event_id, "title": title, "event_type": event_type},
                request_id=request_id,
            )
            if conflict_result.get("overridden"):
                conflicts.record_conflict_override_audit(
                    cur,
                    legacy,
                    company_code=company,
                    event_id=event_id,
                    actor_user_id=actor,
                    conflicts=conflict_result.get("conflicts") or [],
                    override_reason=_text(payload.get("override_reason")),
                    version=1,
                    request_id=request_id,
                    source="calendar_create",
                )
            # C4: default reminders (notify-only) + invite notices for attendees.
            try:
                import calendar_participation as cpart

                cpart.schedule_event_reminders(cur, legacy, company_code=company, event_id=event_id)
                for att in (attendees_payload or []):
                    uid = _text(att.get("user_id"))
                    if uid and uid != actor:
                        cpart.enqueue_delivery(
                            cur,
                            legacy,
                            company_code=company,
                            event_id=event_id,
                            channel="routed",
                            purpose="attendee_invite",
                            idempotency_key=f"invite:{event_id}:user:{uid}:v1",
                            payload={"user_id": uid, "message": f"Invited to “{title}”."},
                            recipient_type="employee",
                            lifecycle="post_hire",
                        )
            except Exception:
                pass
            # C5: provider-neutral sync outbox (failures never roll back event truth).
            try:
                import calendar_sync as csync

                csync.enqueue_sync_for_event(cur, legacy, company_code=company, event_id=event_id, operation="upsert")
            except Exception:
                pass
            bundle = load_event_bundle(cur, company, event_id)
        conn.commit()
    assert bundle is not None
    # Attendee invites are durable via calendar_delivery_outbox → canonical router.
    # Do not dual-send immediately (idempotency / no duplicate spam).
    return bundle["payload"]

def update_event(
    legacy: Any,
    *,
    company_code: str,
    event_id: str,
    actor_user_id: str,
    payload: Mapping[str, Any],
    expected_version: Any,
    request_id: str | None = None,
    actor_permissions: Iterable[Any] | None = None,
) -> dict[str, Any]:
    import calendar_conflicts as conflicts

    company = _text(company_code).upper()
    actor = _text(actor_user_id)
    eid = _text(event_id)
    if not company or not actor or not eid:
        raise CalendarError("event_not_found", http_status=404)

    try:
        version = int(expected_version)
    except (TypeError, ValueError):
        raise CalendarError(
            "missing_expected_version",
            message=_cs.CONFLICT_MESSAGE_EN,
            http_status=422,
            details=_cs.conflict_envelope(code="missing_expected_version", entity_type="calendar_event", entity_id=eid),
        ) from None

    adapter = get_org_scope_adapter(legacy)
    with legacy.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT * FROM calendar_events WHERE company_code=%s AND event_id=%s FOR UPDATE",
                (company, eid),
            )
            row = cur.fetchone()
            if not row:
                raise CalendarError("event_not_found", http_status=404)
            event = dict(row)
            links = fetch_links(cur, company, eid)
            interview_link = active_interview_link(links)

            touched_authority = [k for k in INTERVIEW_AUTHORITY_FIELDS if k in payload]
            if interview_link and touched_authority:
                raise CalendarError(
                    "interview_authority_required",
                    message="Schedule, panel, status, and cancel for interview-linked events must use Interview APIs.",
                    http_status=422,
                    details={"fields": touched_authority, "source_record_id": interview_link.get("source_record_id")},
                )

            current_version = int(event.get("version") or 0)
            try:
                _cs.assert_fresh(
                    current_version=current_version,
                    expected_version=version,
                    current_updated_at=event.get("updated_at"),
                    expected_updated_at=payload.get("expected_updated_at"),
                    require_token=True,
                    code_version="stale_version",
                    entity_type="calendar_event",
                    entity_id=eid,
                    last_changed_by={"user_id": event.get("updated_by_user_id") or event.get("organizer_user_id")},
                )
            except _cs.ConcurrencyError as exc:
                raise CalendarError(exc.code, message=exc.message, http_status=exc.http_status, details=exc.as_detail()) from exc

            fields: list[str] = []
            values: list[Any] = []

            def set_field(column: str, value: Any) -> None:
                fields.append(f"{column}=%s")
                values.append(value)

            if "title" in payload:
                title = _text(payload.get("title"))
                if not title:
                    raise CalendarError("title_required")
                set_field("title", title)
            for col in ("title_ar", "description", "description_ar", "location", "meeting_url"):
                if col in payload:
                    set_field(col, payload.get(col))
            if "visibility" in payload:
                vis = _text(payload.get("visibility"))
                if vis not in VISIBILITIES:
                    raise CalendarError("invalid_visibility")
                set_field("visibility", vis)
            if "sensitivity" in payload:
                sens = _text(payload.get("sensitivity"))
                if sens not in SENSITIVITIES:
                    raise CalendarError("invalid_sensitivity")
                set_field("sensitivity", sens)
            if "status" in payload:
                st = _text(payload.get("status"))
                if st not in STATUSES:
                    raise CalendarError("invalid_status")
                set_field("status", st)
                if st == "cancelled":
                    set_field("cancelled_at", datetime.now(timezone.utc))
                if st == "completed":
                    set_field("completed_at", datetime.now(timezone.utc))
            if "start_at" in payload:
                set_field("start_at", _parse_dt(payload.get("start_at"), field="start_at"))
            if "end_at" in payload:
                set_field("end_at", _parse_dt(payload.get("end_at"), field="end_at"))
            if "timezone" in payload:
                set_field("timezone", _text(payload.get("timezone")) or "Asia/Kuwait")
            if "all_day" in payload:
                set_field("all_day", bool(payload.get("all_day")))
            if "owner_user_id" in payload:
                set_field("owner_user_id", _text(payload.get("owner_user_id")) or None)
            if "organizer_user_id" in payload:
                set_field("organizer_user_id", _text(payload.get("organizer_user_id")) or actor)
            if "metadata" in payload and isinstance(payload.get("metadata"), dict):
                set_field("metadata", _json(legacy, payload.get("metadata")))

            # Proposed times / attendees for conflict check (before write).
            next_start = _parse_dt(payload["start_at"], field="start_at") if "start_at" in payload else event.get("start_at")
            next_end = _parse_dt(payload["end_at"], field="end_at") if "end_at" in payload else event.get("end_at")
            next_tz = _text(payload.get("timezone")) if "timezone" in payload else _text(event.get("timezone"))
            next_all_day = bool(payload.get("all_day")) if "all_day" in payload else bool(event.get("all_day"))
            next_org = (
                _text(payload.get("organizer_user_id")) or actor
                if "organizer_user_id" in payload
                else _text(event.get("organizer_user_id"))
            )
            if "attendees" in payload and isinstance(payload.get("attendees"), list):
                next_attendees = payload.get("attendees")
            else:
                next_attendees = fetch_attendees(cur, company, eid)

            schedule_touched = any(k in payload for k in ("start_at", "end_at", "timezone", "all_day", "attendees", "organizer_user_id"))
            conflict_result: dict[str, Any] = {"overridden": False, "conflicts": []}
            if schedule_touched and _text(payload.get("status")).lower() != "cancelled":
                try:
                    conflict_result = conflicts.require_no_blocking_conflicts(
                        cur,
                        legacy,
                        company_code=company,
                        start=next_start,
                        end=next_end,
                        timezone_name=next_tz,
                        all_day=next_all_day,
                        organizer_user_id=next_org,
                        attendees=next_attendees,
                        exclude_event_id=eid,
                        override_conflicts=bool(payload.get("override_conflicts")),
                        override_reason=_text(payload.get("override_reason")) or None,
                        actor_permissions=actor_permissions,
                    )
                except conflicts.SchedulingConflictError as exc:
                    raise CalendarError(
                        exc.code,
                        message=exc.message,
                        http_status=exc.http_status,
                        details=exc.envelope(),
                    ) from exc

            set_field("version", current_version + 1)
            set_field("updated_at", datetime.now(timezone.utc))
            set_field("updated_by_user_id", actor)

            values.extend([company, eid, version])
            cur.execute(
                f"""
                UPDATE calendar_events
                SET {', '.join(fields)}
                WHERE company_code=%s AND event_id=%s AND version=%s
                RETURNING *
                """,
                tuple(values),
            )
            updated = cur.fetchone()
            if not updated:
                raise CalendarError(
                    "stale_version",
                    message=_cs.CONFLICT_MESSAGE_EN,
                    http_status=409,
                    details=_cs.conflict_envelope(
                        code="stale_version",
                        current_version=current_version,
                        expected_version=version,
                        entity_type="calendar_event",
                        entity_id=eid,
                    ),
                )

            if "attendees" in payload and isinstance(payload.get("attendees"), list):
                org = _text(updated.get("organizer_user_id")) or actor
                _replace_attendees(
                    cur,
                    company_code=company,
                    event_id=eid,
                    organizer_user_id=org,
                    attendees=payload.get("attendees"),
                )
            if "guests" in payload and isinstance(payload.get("guests"), list):
                _replace_guests(cur, company_code=company, event_id=eid, guests=payload.get("guests"))
            if "org_scope_ids" in payload and isinstance(payload.get("org_scope_ids"), list):
                _replace_org_scopes(
                    cur,
                    company_code=company,
                    event_id=eid,
                    org_scope_ids=payload.get("org_scope_ids"),
                    adapter=adapter,
                )

            _audit(
                cur,
                legacy,
                company_code=company,
                event_id=eid,
                actor_user_id=actor,
                action="updated",
                before={"version": current_version},
                after={"version": current_version + 1, "keys": sorted(k for k in payload.keys() if k != "expected_version")},
                request_id=request_id,
            )
            if conflict_result.get("overridden"):
                conflicts.record_conflict_override_audit(
                    cur,
                    legacy,
                    company_code=company,
                    event_id=eid,
                    actor_user_id=actor,
                    conflicts=conflict_result.get("conflicts") or [],
                    override_reason=_text(payload.get("override_reason")),
                    version=current_version + 1,
                    request_id=request_id,
                    source="calendar_update",
                )
            bundle = load_event_bundle(cur, company, eid)
            try:
                import calendar_participation as cpart

                cancelled_now = _text((bundle or {}).get("row", {}).get("status")).lower() == "cancelled"
                cpart.on_event_mutated(
                    cur,
                    legacy,
                    company_code=company,
                    event_id=eid,
                    actor_user_id=actor,
                    before=event,
                    after=dict((bundle or {}).get("row") or {}),
                    cancelled=cancelled_now and _text(event.get("status")).lower() != "cancelled",
                )
            except Exception:
                pass
            # C5 sync handoff (after participation); provider failure must not affect event.
            try:
                import calendar_sync as csync

                op = "cancel" if cancelled_now else "upsert"
                csync.enqueue_sync_for_event(cur, legacy, company_code=company, event_id=eid, operation=op)
            except Exception:
                pass
        conn.commit()
    assert bundle is not None
    return bundle["payload"]

def cancel_event(
    legacy: Any,
    *,
    company_code: str,
    event_id: str,
    actor_user_id: str,
    expected_version: Any,
    request_id: str | None = None,
) -> dict[str, Any]:
    return update_event(
        legacy,
        company_code=company_code,
        event_id=event_id,
        actor_user_id=actor_user_id,
        payload={"status": "cancelled"},
        expected_version=expected_version,
        request_id=request_id,
    )


def list_events_in_range(
    legacy: Any,
    *,
    company_code: str,
    start_at: Any,
    end_at: Any,
) -> list[dict[str, Any]]:
    company = _text(company_code).upper()
    start = _parse_dt(start_at, field="start")
    end = _parse_dt(end_at, field="end")
    if end < start:
        raise CalendarError("invalid_date_window", message="end must be >= start")
    # Cap window at 92 days to protect projections.
    if (end - start).days > 92:
        raise CalendarError("date_window_too_large", message="Date window must be 92 days or less.")

    with legacy.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT * FROM calendar_events
                WHERE company_code=%s
                  AND start_at < %s
                  AND end_at > %s
                  AND status <> 'cancelled'
                ORDER BY start_at ASC
                """,
                (company, end, start),
            )
            rows = [dict(r) for r in cur.fetchall()]
            if not rows:
                return []
            event_ids = [str(r["event_id"]) for r in rows]
            cur.execute(
                """
                SELECT * FROM calendar_attendees
                WHERE company_code=%s AND event_id = ANY(%s::uuid[]) AND rsvp_status <> 'removed'
                """,
                (company, event_ids),
            )
            attendees_by: dict[str, list[dict[str, Any]]] = {}
            for r in cur.fetchall():
                attendees_by.setdefault(str(r["event_id"]), []).append(dict(r))
            cur.execute(
                """
                SELECT * FROM calendar_guests
                WHERE company_code=%s AND event_id = ANY(%s::uuid[]) AND rsvp_status <> 'removed'
                """,
                (company, event_ids),
            )
            guests_by: dict[str, list[dict[str, Any]]] = {}
            for r in cur.fetchall():
                guests_by.setdefault(str(r["event_id"]), []).append(dict(r))
            cur.execute(
                """
                SELECT * FROM calendar_event_links
                WHERE company_code=%s AND event_id = ANY(%s::uuid[])
                """,
                (company, event_ids),
            )
            links_by: dict[str, list[dict[str, Any]]] = {}
            for r in cur.fetchall():
                links_by.setdefault(str(r["event_id"]), []).append(dict(r))
            cur.execute(
                """
                SELECT * FROM calendar_event_org_scopes
                WHERE company_code=%s AND event_id = ANY(%s::uuid[])
                """,
                (company, event_ids),
            )
            scopes_by: dict[str, list[dict[str, Any]]] = {}
            for r in cur.fetchall():
                scopes_by.setdefault(str(r["event_id"]), []).append(dict(r))

    out: list[dict[str, Any]] = []
    for row in rows:
        eid = str(row["event_id"])
        out.append(
            {
                "row": row,
                "attendees": attendees_by.get(eid, []),
                "guests": guests_by.get(eid, []),
                "links": links_by.get(eid, []),
                "org_scopes": scopes_by.get(eid, []),
                "payload": serialize_event(
                    row,
                    attendees=attendees_by.get(eid, []),
                    guests=guests_by.get(eid, []),
                    links=links_by.get(eid, []),
                    org_scopes=scopes_by.get(eid, []),
                ),
            }
        )
    return out


def get_event(
    legacy: Any,
    *,
    company_code: str,
    event_id: str,
) -> dict[str, Any] | None:
    company = _text(company_code).upper()
    with legacy.db_connect() as conn:
        with conn.cursor() as cur:
            return load_event_bundle(cur, company, _text(event_id))
