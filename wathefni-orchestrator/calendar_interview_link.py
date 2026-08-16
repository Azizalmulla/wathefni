"""Wathefni Calendar C2 — Interview → Calendar ensure / cancel / complete / panel sync.

Interview lifecycle remains business authority. This module projects live interviews
into the first-party calendar_events spine. Async video interviews never create
timed events here.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Mapping, Sequence
from uuid import uuid4

SOURCE_WORKFLOW = "interview"
EVENT_TYPE = "interview"
DEFAULT_VISIBILITY = "attendees_only"
DEFAULT_SENSITIVITY = "candidate_confidential"


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


def _json(legacy: Any, value: Any) -> Any:
    if hasattr(legacy, "Json"):
        return legacy.Json(value if value is not None else {})
    return value if value is not None else {}


def is_live_timed_interview(interview: Mapping[str, Any] | None) -> bool:
    if not interview:
        return False
    itype = _text(interview.get("interview_type")).lower() or "live"
    if itype == "async_video":
        return False
    meeting = _text(interview.get("meeting_type")).lower()
    if meeting == "async_video":
        return False
    return bool(interview.get("scheduled_start") and interview.get("scheduled_end"))


def resolve_person_key(cur: Any, *, company_code: str, app_key: str) -> str | None:
    """Best-effort person_key from applications authority — never invent one."""
    company = _text(company_code).upper()
    key = _text(app_key)
    if not company or not key:
        return None
    queries = (
        "SELECT person_key FROM applications WHERE company_code=%s AND app_key=%s AND person_key IS NOT NULL LIMIT 1",
        "SELECT candidate_person_key AS person_key FROM applications WHERE company_code=%s AND app_key=%s AND candidate_person_key IS NOT NULL LIMIT 1",
    )
    for sql in queries:
        try:
            cur.execute("SAVEPOINT calendar_person_key")
            cur.execute(sql, (company, key))
            row = cur.fetchone()
            cur.execute("RELEASE SAVEPOINT calendar_person_key")
            if row:
                pk = _text(row.get("person_key") if isinstance(row, dict) else row[0])
                if pk:
                    return pk
        except Exception:
            try:
                cur.execute("ROLLBACK TO SAVEPOINT calendar_person_key")
            except Exception:
                pass
    return None


def build_interview_projection_payload(
    interview: Mapping[str, Any],
    *,
    assignments: Sequence[Mapping[str, Any]] | None = None,
    person_key: str | None = None,
    operation: str = "ensure",
) -> dict[str, Any]:
    organizer = None
    attendees: list[dict[str, Any]] = []
    for item in assignments or []:
        uid = _text(item.get("assignee_user_id") or item.get("user_id"))
        if not uid:
            continue
        is_org = bool(item.get("is_organizer")) or _text(item.get("panel_role")).lower() == "organizer"
        if is_org and not organizer:
            organizer = uid
        attendees.append(
            {
                "user_id": uid,
                "role": "organizer" if is_org else "required",
                "is_organizer": is_org,
                "rsvp_status": _text(item.get("rsvp_status")) or "needs_action",
                "email": item.get("assignee_email"),
                "name": item.get("assignee_name"),
            }
        )
    if not organizer and attendees:
        organizer = attendees[0]["user_id"]
        attendees[0]["is_organizer"] = True
        attendees[0]["role"] = "organizer"
    creator = organizer or _text(interview.get("created_by_user_id")) or "system"

    guest = None
    if _text(interview.get("candidate_email")) or _text(interview.get("candidate_name")) or person_key or _text(interview.get("app_key")):
        guest = {
            "guest_kind": "candidate",
            "email": _text(interview.get("candidate_email")) or None,
            "phone": _text(interview.get("phone")) or None,
            "display_name": _text(interview.get("candidate_name")) or None,
            "person_key": person_key,
            "app_key": _text(interview.get("app_key")) or None,
            "invite_channel": "email" if _text(interview.get("candidate_email")) else "none",
        }

    status = _text(interview.get("status")).lower() or "scheduled"
    cal_status = {
        "scheduled": "confirmed",
        "rescheduled": "confirmed",
        "completed": "completed",
        "cancelled": "cancelled",
        "no_show": "cancelled",
    }.get(status, "confirmed")

    title = _text(interview.get("position_title")) or _text(interview.get("candidate_name")) or "Interview"
    if _text(interview.get("candidate_name")) and _text(interview.get("position_title")):
        title = f"Interview · {interview.get('candidate_name')} · {interview.get('position_title')}"
    elif _text(interview.get("candidate_name")):
        title = f"Interview · {interview.get('candidate_name')}"

    meta: dict[str, Any] = {
        "candidate_linked": True,
        "source_workflow": SOURCE_WORKFLOW,
        "interview_id": _text(interview.get("interview_id")),
        "app_key": _text(interview.get("app_key")),
        "interview_status": status,
        "meeting_type": _text(interview.get("meeting_type")) or None,
    }
    google_id = _text(interview.get("calendar_event_id"))
    if google_id:
        meta["legacy_operator_calendar"] = {
            "provider": "google",
            "provider_event_id": google_id,
            "mode": "legacy_operator",
        }

    return {
        "operation": operation,
        "interview_id": _text(interview.get("interview_id")),
        "company_code": _text(interview.get("company_code")).upper(),
        "app_key": _text(interview.get("app_key")),
        "event_type": EVENT_TYPE,
        "title": title,
        "description": None,
        "visibility": DEFAULT_VISIBILITY,
        "sensitivity": DEFAULT_SENSITIVITY,
        "status": cal_status,
        "start_at": _iso(interview.get("scheduled_start")),
        "end_at": _iso(interview.get("scheduled_end")),
        "timezone": _text(interview.get("timezone")) or "Asia/Kuwait",
        "all_day": False,
        "location": _text(interview.get("location")) or None,
        "meeting_url": _text(interview.get("meet_link")) or None,
        "organizer_user_id": organizer or creator,
        "owner_user_id": organizer or creator,
        "creator_user_id": creator,
        "attendees": attendees,
        "guest": guest,
        "metadata": meta,
        "schedule_operation_id": _text(interview.get("schedule_operation_id")) or None,
        "legacy_google_event_id": google_id or None,
    }


def _find_active_link(cur: Any, company: str, interview_id: str) -> dict[str, Any] | None:
    cur.execute(
        """
        SELECT * FROM calendar_event_links
        WHERE company_code=%s AND source_workflow=%s AND source_record_id=%s AND link_status='active'
        LIMIT 1
        """,
        (company, SOURCE_WORKFLOW, interview_id),
    )
    row = cur.fetchone()
    return dict(row) if row else None


def _sync_attendees_preserving_rsvp(
    cur: Any,
    *,
    company: str,
    event_id: str,
    organizer_user_id: str,
    attendees: Sequence[Mapping[str, Any]],
) -> None:
    cur.execute(
        """
        SELECT user_id, rsvp_status, response_at
        FROM calendar_attendees
        WHERE company_code=%s AND event_id=%s AND rsvp_status <> 'removed'
        """,
        (company, event_id),
    )
    prior: dict[str, dict[str, Any]] = {}
    for r in cur.fetchall() or []:
        row = dict(r) if not isinstance(r, dict) else r
        uid = _text(row.get("user_id"))
        if uid:
            prior[uid] = row

    desired: dict[str, Mapping[str, Any]] = {}
    for item in attendees:
        uid = _text(item.get("user_id"))
        if uid:
            desired[uid] = item
    org = _text(organizer_user_id)
    if org and org not in desired:
        desired[org] = {"user_id": org, "role": "organizer", "is_organizer": True}

    cur.execute(
        "DELETE FROM calendar_attendees WHERE company_code=%s AND event_id=%s",
        (company, event_id),
    )
    for uid, item in desired.items():
        role = _text(item.get("role")) or ("organizer" if uid == org else "required")
        if role not in {"organizer", "required", "optional", "resource_owner"}:
            role = "required"
        is_org = bool(item.get("is_organizer")) or uid == org or role == "organizer"
        prev = prior.get(uid) or {}
        mapped = _text(prev.get("rsvp_status")).lower()
        if mapped in {"needs_action", "accepted", "declined", "tentative"}:
            rsvp = mapped
            response_at = prev.get("response_at")
        else:
            rsvp = "needs_action"
            response_at = None
        cur.execute(
            """
            INSERT INTO calendar_attendees
              (attendee_id, event_id, company_code, user_id, role, rsvp_status, response_at, is_organizer)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
            """,
            (str(uuid4()), event_id, company, uid, role, rsvp, response_at, is_org),
        )


def _sync_candidate_guest(
    cur: Any,
    *,
    company: str,
    event_id: str,
    guest: Mapping[str, Any] | None,
) -> None:
    cur.execute(
        """
        UPDATE calendar_guests
        SET rsvp_status='removed', updated_at=now()
        WHERE company_code=%s AND event_id=%s AND guest_kind='candidate' AND rsvp_status <> 'removed'
        """,
        (company, event_id),
    )
    if not guest:
        return
    cur.execute(
        """
        INSERT INTO calendar_guests
          (guest_id, event_id, company_code, email, phone, display_name, guest_kind,
           person_key, app_key, rsvp_status, invite_channel)
        VALUES (%s,%s,%s,%s,%s,%s,'candidate',%s,%s,'needs_action',%s)
        """,
        (
            str(uuid4()),
            event_id,
            company,
            _text(guest.get("email")) or None,
            _text(guest.get("phone")) or None,
            _text(guest.get("display_name")) or None,
            _text(guest.get("person_key")) or None,
            _text(guest.get("app_key")) or None,
            _text(guest.get("invite_channel")) or "none",
        ),
    )


def _audit(cur: Any, legacy: Any, *, company: str, event_id: str, action: str, after: dict[str, Any], actor: str | None = None) -> None:
    cur.execute(
        """
        INSERT INTO calendar_event_audit
          (audit_id, event_id, company_code, actor_user_id, action, before, after, request_id)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
        """,
        (str(uuid4()), event_id, company, actor, action, _json(legacy, {}), _json(legacy, after), None),
    )


def ensure_calendar_event(
    legacy: Any,
    cur: Any,
    *,
    company_code: str,
    interview_id: str,
    payload: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Idempotent create/update of the single active interview-linked calendar event."""
    company = _text(company_code).upper()
    iid = _text(interview_id)
    if not company or not iid:
        return {"ok": False, "error": "interview_required"}

    data = dict(payload or {})
    if not data.get("start_at") or not data.get("end_at"):
        return {"ok": False, "error": "missing_schedule", "skipped": True}

    link = _find_active_link(cur, company, iid)
    event_id = str(link["event_id"]) if link else str(uuid4())
    organizer = _text(data.get("organizer_user_id")) or "system"
    owner = _text(data.get("owner_user_id")) or organizer
    creator = _text(data.get("creator_user_id")) or organizer
    meta = data.get("metadata") if isinstance(data.get("metadata"), dict) else {}

    if link:
        cur.execute(
            """
            UPDATE calendar_events
            SET event_type=%s,
                title=%s,
                visibility=%s,
                sensitivity=%s,
                status=%s,
                start_at=%s::timestamptz,
                end_at=%s::timestamptz,
                timezone=%s,
                all_day=false,
                location=%s,
                meeting_url=%s,
                organizer_user_id=%s,
                owner_user_id=%s,
                version=version+1,
                updated_at=now(),
                updated_by_user_id=%s,
                cancelled_at=CASE WHEN %s='cancelled' THEN COALESCE(cancelled_at, now()) ELSE NULL END,
                completed_at=CASE WHEN %s='completed' THEN COALESCE(completed_at, now()) ELSE NULL END,
                metadata=%s
            WHERE company_code=%s AND event_id=%s
            RETURNING *
            """,
            (
                EVENT_TYPE,
                _text(data.get("title")) or "Interview",
                DEFAULT_VISIBILITY,
                DEFAULT_SENSITIVITY,
                _text(data.get("status")) or "confirmed",
                data.get("start_at"),
                data.get("end_at"),
                _text(data.get("timezone")) or "Asia/Kuwait",
                _text(data.get("location")) or None,
                _text(data.get("meeting_url")) or None,
                organizer,
                owner,
                creator,
                _text(data.get("status")) or "confirmed",
                _text(data.get("status")) or "confirmed",
                _json(legacy, meta),
                company,
                event_id,
            ),
        )
        row = dict(cur.fetchone() or {})
        action = "interview_ensure_updated"
    else:
        cur.execute(
            """
            INSERT INTO calendar_events (
              event_id, company_code, event_type, title, visibility, sensitivity, status,
              start_at, end_at, timezone, all_day, location, meeting_url,
              creator_user_id, organizer_user_id, owner_user_id, version, updated_by_user_id, metadata
            ) VALUES (
              %s,%s,%s,%s,%s,%s,%s,%s::timestamptz,%s::timestamptz,%s,false,%s,%s,%s,%s,%s,1,%s,%s
            )
            RETURNING *
            """,
            (
                event_id,
                company,
                EVENT_TYPE,
                _text(data.get("title")) or "Interview",
                DEFAULT_VISIBILITY,
                DEFAULT_SENSITIVITY,
                _text(data.get("status")) or "confirmed",
                data.get("start_at"),
                data.get("end_at"),
                _text(data.get("timezone")) or "Asia/Kuwait",
                _text(data.get("location")) or None,
                _text(data.get("meeting_url")) or None,
                creator,
                organizer,
                owner,
                creator,
                _json(legacy, meta),
            ),
        )
        row = dict(cur.fetchone() or {})
        try:
            cur.execute(
                """
                INSERT INTO calendar_event_links
                  (link_id, company_code, event_id, source_workflow, source_record_id, link_status)
                VALUES (%s,%s,%s,%s,%s,'active')
                """,
                (str(uuid4()), company, event_id, SOURCE_WORKFLOW, iid),
            )
        except Exception:
            # Race: another worker created the active link — reuse it
            race = _find_active_link(cur, company, iid)
            if not race:
                raise
            event_id = str(race["event_id"])
            # Delete orphan row we just inserted if different
            if str(row.get("event_id")) != event_id:
                cur.execute("DELETE FROM calendar_events WHERE event_id=%s AND company_code=%s", (row.get("event_id"), company))
            return ensure_calendar_event(legacy, cur, company_code=company, interview_id=iid, payload=data)
        action = "interview_ensure_created"

    _sync_attendees_preserving_rsvp(
        cur,
        company=company,
        event_id=event_id,
        organizer_user_id=organizer,
        attendees=data.get("attendees") if isinstance(data.get("attendees"), list) else [],
    )
    _sync_candidate_guest(cur, company=company, event_id=event_id, guest=data.get("guest") if isinstance(data.get("guest"), dict) else None)
    _audit(cur, legacy, company=company, event_id=event_id, action=action, after={"interview_id": iid, "status": data.get("status")}, actor=creator)
    return {"ok": True, "event_id": event_id, "action": action, "version": int(row.get("version") or 1)}


def sync_interview_attendees(
    legacy: Any,
    cur: Any,
    *,
    company_code: str,
    interview_id: str,
    payload: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    company = _text(company_code).upper()
    iid = _text(interview_id)
    link = _find_active_link(cur, company, iid)
    if not link:
        # No event yet — full ensure
        return ensure_calendar_event(legacy, cur, company_code=company, interview_id=iid, payload=payload)
    data = dict(payload or {})
    event_id = str(link["event_id"])
    organizer = _text(data.get("organizer_user_id")) or "system"
    _sync_attendees_preserving_rsvp(
        cur,
        company=company,
        event_id=event_id,
        organizer_user_id=organizer,
        attendees=data.get("attendees") if isinstance(data.get("attendees"), list) else [],
    )
    if isinstance(data.get("guest"), dict):
        _sync_candidate_guest(cur, company=company, event_id=event_id, guest=data.get("guest"))
    _audit(cur, legacy, company=company, event_id=event_id, action="interview_sync_attendees", after={"interview_id": iid}, actor=organizer)
    return {"ok": True, "event_id": event_id, "action": "interview_sync_attendees"}


def cancel_interview_calendar_event(
    legacy: Any,
    cur: Any,
    *,
    company_code: str,
    interview_id: str,
    payload: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    company = _text(company_code).upper()
    iid = _text(interview_id)
    link = _find_active_link(cur, company, iid)
    if not link:
        return {"ok": True, "skipped": True, "reason": "no_active_link"}
    event_id = str(link["event_id"])
    cur.execute(
        """
        UPDATE calendar_events
        SET status='cancelled', cancelled_at=COALESCE(cancelled_at, now()),
            version=version+1, updated_at=now()
        WHERE company_code=%s AND event_id=%s
        RETURNING event_id, version
        """,
        (company, event_id),
    )
    row = cur.fetchone()
    _audit(cur, legacy, company=company, event_id=event_id, action="interview_cancel", after={"interview_id": iid})
    return {"ok": True, "event_id": event_id, "version": int((row or {}).get("version") or 0), "action": "interview_cancel"}


def complete_interview_calendar_event(
    legacy: Any,
    cur: Any,
    *,
    company_code: str,
    interview_id: str,
    payload: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    company = _text(company_code).upper()
    iid = _text(interview_id)
    link = _find_active_link(cur, company, iid)
    if not link:
        return {"ok": True, "skipped": True, "reason": "no_active_link"}
    event_id = str(link["event_id"])
    cur.execute(
        """
        UPDATE calendar_events
        SET status='completed', completed_at=COALESCE(completed_at, now()),
            version=version+1, updated_at=now()
        WHERE company_code=%s AND event_id=%s
        RETURNING event_id, version
        """,
        (company, event_id),
    )
    row = cur.fetchone()
    _audit(cur, legacy, company=company, event_id=event_id, action="interview_complete", after={"interview_id": iid})
    return {"ok": True, "event_id": event_id, "version": int((row or {}).get("version") or 0), "action": "interview_complete"}
