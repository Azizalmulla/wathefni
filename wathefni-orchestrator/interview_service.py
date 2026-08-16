"""Wathefni-owned interview scheduling, optional calendar sync, feedback, retention.

Commit authority lives in Wathefni. Google Calendar/Meet is optional after-commit sync.
Interview mutations never hire, reject, rank, or issue offers.
"""

from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import interview_lifecycle as life


def _legacy():
    import app as legacy

    return legacy


def _company(value: Any) -> str:
    return str(value or "").strip().upper()


def _text(value: Any) -> str:
    return str(value or "").strip()


def _json(value: Any) -> Any:
    legacy = _legacy()
    return legacy.Json(legacy.json_safe(value))


def _actor(actor: dict[str, Any] | None) -> dict[str, Any]:
    actor = actor or {}
    return {
        "actor_user_id": _text(actor.get("actor_user_id")) or None,
        "actor_phone": _text(actor.get("actor_phone")) or None,
        "actor_role": _text(actor.get("actor_role")) or None,
        "actor_type": _text(actor.get("actor_type") or "human") or "human",
    }


def _require_live_interviews(legacy: Any, company: str) -> None:
    """Defence in depth for the live-interview module.

    Routes and registry specs are already entitled; this keeps the module owning
    its own writes so a new caller cannot schedule against a disabled tenant.
    """
    checker = getattr(legacy, "company_has_module", None)
    if callable(checker) and not checker(company, "interviews"):
        raise life.InterviewAuthorityError(
            "module_disabled",
            "This module is not enabled for this company.",
            status_code=403,
            required_module="interviews",
        )


def _require_calendar_outbox_intent(
    cur: Any,
    legacy: Any,
    *,
    interview: dict[str, Any],
    assignments: list[Any] | None,
    operation: str,
    operation_token: str,
) -> dict[str, Any]:
    """Insert required Calendar outbox intent in the current Interview TX.

    Raises InterviewAuthorityError (503/retryable) on genuine enqueue failure so
    the caller rolls back Interview truth. Duplicate idempotency keys succeed.
    """
    import calendar_outbox as _cal_outbox

    try:
        return _cal_outbox.require_enqueue_from_interview(
            cur,
            legacy,
            interview=interview,
            assignments=assignments,
            operation=operation,
            operation_token=operation_token,
        )
    except _cal_outbox.CalendarOutboxError as exc:
        raise life.InterviewAuthorityError(
            exc.code,
            exc.message,
            status_code=503 if exc.retryable else 422,
            retryable=exc.retryable,
            **{k: v for k, v in exc.details.items() if k not in {"error", "message"}},
        ) from exc


def ensure_schema(legacy: Any | None = None) -> None:
    legacy = legacy or _legacy()
    with legacy.db_connect() as conn:
        with conn.cursor() as cur:
            life.ensure_interview_schema(cur)
        conn.commit()


def _http_error(exc: life.InterviewAuthorityError):
    from fastapi import HTTPException

    raise HTTPException(status_code=exc.status_code, detail=exc.as_detail()) from exc


def enrich_interview_row(row: dict[str, Any] | None, *, assignments: list[dict[str, Any]] | None = None) -> dict[str, Any] | None:
    if not row:
        return None
    legacy = _legacy()
    data = dict(row)
    truth = life.communication_truth(data)
    summary = legacy.candidate_interview_summary(data)
    summary.update(
        {
            "location": data.get("location"),
            "duration_minutes": data.get("duration_minutes"),
            "provider_key": data.get("provider_key") or "none",
            "provider_sync_status": truth["provider_sync_status"],
            "provider_sync_error": data.get("provider_sync_error"),
            "provider_synced_at": legacy.json_safe(data.get("provider_synced_at")),
            "channel_send_status": truth["channel_send_status"],
            "rsvp_status": truth["rsvp_status"],
            "human_feedback_status": life.normalize_feedback_status(
                data.get("human_feedback_status") or data.get("feedback_status")
            ),
            "communication_status": truth["communication_status"],
            "invitation_status": truth["invitation_status"],
            "candidate_confirmation": truth["candidate_confirmation"],
            "provider_accepted": truth["provider_accepted"],
            "delivered": truth["delivered"],
            "failed": truth["failed"],
            "notes_status": life.derive_notes_status(data),
            "next_human_action": life.next_human_action(data, truth),
            "assignments": assignments if assignments is not None else [],
            "retention_expires_at": legacy.json_safe(data.get("retention_expires_at")),
            "retention_purged_at": legacy.json_safe(data.get("retention_purged_at")),
            "schedule_operation_id": str(data.get("schedule_operation_id") or "") or None,
        }
    )
    # Free-text notes are not scorecards; keep legacy feedback_status for notes queue
    # but surface human_feedback_status for scorecard authority.
    return summary


def load_interview(cur: Any, interview_id: str, company_code: str | None = None) -> dict[str, Any] | None:
    company = _company(company_code)
    if company:
        cur.execute(
            "SELECT * FROM candidate_interviews WHERE interview_id=%s AND company_code=%s LIMIT 1",
            (interview_id, company),
        )
    else:
        cur.execute("SELECT * FROM candidate_interviews WHERE interview_id=%s LIMIT 1", (interview_id,))
    row = cur.fetchone()
    return dict(row) if row else None


def record_event(
    legacy: Any,
    interview: dict[str, Any],
    event_type: str,
    payload: dict[str, Any] | None = None,
    *,
    actor: dict[str, Any] | None = None,
    action: str | None = None,
) -> None:
    actor = _actor(actor)
    legacy.record_interview_event(
        str(interview.get("interview_id") or ""),
        _company(interview.get("company_code")),
        _text(interview.get("app_key")),
        event_type,
        payload or {},
        actor.get("actor_phone"),
        actor_context={
            "company_code": _company(interview.get("company_code")),
            "actor_user_id": actor.get("actor_user_id"),
            "actor_phone": actor.get("actor_phone"),
            "actor_role": actor.get("actor_role"),
        },
        action=action or event_type,
        target_type="interview",
        target=str(interview.get("interview_id") or ""),
    )


def resolve_schedule_window(
    legacy: Any,
    company_code: str,
    *,
    start: Any,
    end: Any = None,
    duration_minutes: int | None = None,
    timezone_name: str | None = None,
) -> tuple[datetime, datetime, str, int]:
    tz_name = _text(timezone_name) or life.company_timezone_name(legacy, company_code)
    try:
        from zoneinfo import ZoneInfo

        tzinfo = ZoneInfo(tz_name)
    except Exception:
        tz_name = "Asia/Kuwait"
        from zoneinfo import ZoneInfo

        tzinfo = ZoneInfo(tz_name)
    start_dt = life.parse_aware_datetime(start, default_tz=tzinfo)
    if not start_dt:
        raise life.InterviewAuthorityError("invalid_start", "Interview start time is required and must be a valid datetime.")
    minutes = int(duration_minutes or life.DEFAULT_DURATION_MINUTES)
    minutes = max(5, min(minutes, 8 * 60))
    end_dt = life.parse_aware_datetime(end, default_tz=tzinfo) if end else None
    if not end_dt:
        end_dt = start_dt + timedelta(minutes=minutes)
    if end_dt <= start_dt:
        raise life.InterviewAuthorityError("invalid_time_range", "Interview end must be after start.")
    minutes = max(1, int(round((end_dt - start_dt).total_seconds() / 60.0)))
    return start_dt, end_dt, tz_name, minutes


def resolve_meeting_fields(
    *,
    meeting_type: Any,
    location: Any = None,
    meet_link: Any = None,
    google_connected: bool = False,
    microsoft_connected: bool = False,
) -> dict[str, Any]:
    mtype = life.normalize_meeting_type(meeting_type, default="manual_link")
    loc = _text(location) or None
    link = _text(meet_link) or None
    if mtype == "google_meet" and not google_connected:
        # Prefer an explicit manual link; otherwise keep a valid Wathefni phone interview.
        mtype = "manual_link" if link else "phone"
    if mtype == "microsoft_teams" and not microsoft_connected:
        mtype = "manual_link" if link else "phone"
    if mtype == "in_person" and not loc:
        raise life.InterviewAuthorityError("location_required", "Physical interviews require a location.")
    if mtype == "manual_link" and not link:
        raise life.InterviewAuthorityError("meet_link_required", "Online interviews require a meeting link when Meet/Teams is not used.")
    if mtype == "phone":
        link = None
    if mtype == "google_meet" and google_connected:
        provider_key = "google"
    elif mtype == "microsoft_teams" and microsoft_connected:
        provider_key = "microsoft"
    else:
        provider_key = "none"
    provider_sync = "pending" if provider_key in {"google", "microsoft"} else "not_configured"
    return {
        "meeting_type": mtype,
        "location": loc,
        "meet_link": link,
        "provider_key": provider_key,
        "provider_sync_status": provider_sync,
    }


def _google_create(legacy: Any, *, summary: str, start: datetime, end: datetime, attendees: list[str], with_meet: bool) -> dict[str, Any]:
    account = ""
    try:
        account = _text((legacy.openclaw_env() or {}).get("GOG_ACCOUNT"))
    except Exception:
        account = _text(os.environ.get("GOG_ACCOUNT"))
    args = [
        "calendar",
        "create",
        "primary",
        "--summary",
        summary,
        "--from",
        start.isoformat(),
        "--to",
        end.isoformat(),
        "--send-updates",
        "all",
        "--no-input",
    ]
    if attendees:
        args.extend(["--attendees", ",".join(attendees)])
    if with_meet:
        args.append("--with-meet")
    if account:
        args.extend(["--account", account])
    return legacy.run_gog(args, timeout=60) if hasattr(legacy, "run_gog") else {"ok": False, "error": "gog_unavailable"}


def _google_update(legacy: Any, event_id: str, *, summary: str, start: datetime, end: datetime, attendees: list[str], with_meet: bool) -> dict[str, Any]:
    """Update an existing Google Calendar event in place.

    `with_meet` is accepted for call-site compatibility but intentionally unused:
    gog v0.12.0 `calendar update` rejects `--with-meet`. Meet/conference data on
    the existing event must be preserved by updating the same event_id.
    """
    _ = with_meet  # create-only flag; never pass on update
    account = ""
    try:
        account = _text((legacy.openclaw_env() or {}).get("GOG_ACCOUNT"))
    except Exception:
        account = _text(os.environ.get("GOG_ACCOUNT"))
    # Prefer update/patch; fall back to delete+create only when update command unsupported.
    args = [
        "calendar",
        "update",
        "primary",
        event_id,
        "--summary",
        summary,
        "--from",
        start.isoformat(),
        "--to",
        end.isoformat(),
        "--send-updates",
        "all",
        "--no-input",
    ]
    if attendees:
        args.extend(["--attendees", ",".join(attendees)])
    if account:
        args.extend(["--account", account])
    result = legacy.run_gog(args, timeout=60) if hasattr(legacy, "run_gog") else {"ok": False, "error": "gog_unavailable"}
    if isinstance(result, dict) and result.get("ok"):
        return result
    # Some gog builds use `events update`.
    args2 = [
        "calendar",
        "events",
        "update",
        "primary",
        event_id,
        "--summary",
        summary,
        "--from",
        start.isoformat(),
        "--to",
        end.isoformat(),
        "--send-updates",
        "all",
        "--no-input",
    ]
    if attendees:
        args2.extend(["--attendees", ",".join(attendees)])
    if account:
        args2.extend(["--account", account])
    return legacy.run_gog(args2, timeout=60) if hasattr(legacy, "run_gog") else result


def _google_delete(legacy: Any, event_id: str) -> dict[str, Any]:
    account = ""
    try:
        account = _text((legacy.openclaw_env() or {}).get("GOG_ACCOUNT"))
    except Exception:
        account = _text(os.environ.get("GOG_ACCOUNT"))
    # gog v0.12.0 refuses non-interactive delete without --force/-y.
    for args in (
        ["calendar", "delete", "primary", event_id, "--send-updates", "all", "--no-input", "--force"],
        ["calendar", "events", "delete", "primary", event_id, "--send-updates", "all", "--no-input", "--force"],
    ):
        cmd = list(args)
        if account:
            cmd.extend(["--account", account])
        result = legacy.run_gog(cmd, timeout=60) if hasattr(legacy, "run_gog") else {"ok": False, "error": "gog_unavailable"}
        if isinstance(result, dict) and result.get("ok"):
            return result
    return result if isinstance(result, dict) else {"ok": False, "error": "gog_delete_failed"}


def sync_provider_for_interview(
    legacy: Any,
    cur: Any,
    interview: dict[str, Any],
    *,
    mode: str,
    attendees: list[str] | None = None,
) -> dict[str, Any]:
    """Optional external sync. Never invalidates the Wathefni interview on failure."""
    provider_key = _text(interview.get("provider_key") or "none") or "none"
    meeting_type = life.normalize_meeting_type(interview.get("meeting_type"))
    if provider_key == "none" or meeting_type in {"in_person", "phone", "async_video", "none"}:
        if meeting_type == "google_meet" and provider_key == "google":
            pass
        elif meeting_type == "microsoft_teams" and provider_key == "microsoft":
            pass
        else:
            cur.execute(
                """
                UPDATE candidate_interviews
                SET provider_sync_status='not_configured', provider_sync_error=NULL, updated_at=now()
                WHERE interview_id=%s
                RETURNING *
                """,
                (str(interview["interview_id"]),),
            )
            return {"ok": True, "skipped": True, "interview": dict(cur.fetchone() or interview)}

    if provider_key == "microsoft":
        return _sync_microsoft_for_interview(legacy, cur, interview, mode=mode, attendees=attendees)

    if provider_key != "google":
        cur.execute(
            """
            UPDATE candidate_interviews
            SET provider_sync_status='not_configured',
                provider_sync_error=%s,
                updated_at=now()
            WHERE interview_id=%s
            RETURNING *
            """,
            (f"provider_{provider_key}_not_implemented", str(interview["interview_id"])),
        )
        return {"ok": False, "error": "provider_not_implemented", "interview": dict(cur.fetchone() or interview)}

    if not life.google_calendar_configured(legacy) and mode != "cancel":
        # Still attempt if GOG is available via run_gog; otherwise mark not_configured.
        pass

    with_meet = meeting_type == "google_meet"
    start = interview.get("scheduled_start")
    end = interview.get("scheduled_end")
    if isinstance(start, str):
        start = life.parse_aware_datetime(start, default_tz=timezone.utc)
    if isinstance(end, str):
        end = life.parse_aware_datetime(end, default_tz=timezone.utc)
    summary = f"OctoHR interview with {interview.get('candidate_name') or 'candidate'}"
    attendee_list = [a for a in (attendees or []) if a]
    if interview.get("candidate_email") and interview["candidate_email"] not in attendee_list:
        attendee_list.insert(0, str(interview["candidate_email"]))

    cur.execute(
        """
        UPDATE candidate_interviews
        SET provider_sync_status=CASE
              WHEN %s='cancel' THEN 'cancellation_pending'
              WHEN %s='update' THEN 'update_pending'
              ELSE 'pending'
            END,
            updated_at=now()
        WHERE interview_id=%s
        """,
        (mode, mode, str(interview["interview_id"])),
    )

    event_id = _text(interview.get("calendar_event_id")) or None
    try:
        if mode == "cancel":
            if not event_id:
                result = {"ok": True, "skipped": True}
            else:
                result = _google_delete(legacy, event_id)
            if result.get("ok"):
                cur.execute(
                    """
                    UPDATE candidate_interviews
                    SET provider_sync_status='synced',
                        provider_sync_error=NULL,
                        provider_synced_at=now(),
                        calendar_invite_sent=false,
                        updated_at=now()
                    WHERE interview_id=%s
                    RETURNING *
                    """,
                    (str(interview["interview_id"]),),
                )
                return {"ok": True, "result": result, "interview": dict(cur.fetchone() or interview)}
            cur.execute(
                """
                UPDATE candidate_interviews
                SET provider_sync_status='failed',
                    provider_sync_error=%s,
                    updated_at=now()
                WHERE interview_id=%s
                RETURNING *
                """,
                (_text(result.get("error") or result.get("stderr") or "calendar_cancel_failed")[:1000], str(interview["interview_id"])),
            )
            return {"ok": False, "error": "calendar_cancel_failed", "result": result, "interview": dict(cur.fetchone() or interview)}

        if mode == "update" and event_id:
            result = _google_update(legacy, event_id, summary=summary, start=start, end=end, attendees=attendee_list, with_meet=with_meet)
            if not result.get("ok"):
                # Do not create a second active event when update fails.
                cur.execute(
                    """
                    UPDATE candidate_interviews
                    SET provider_sync_status='failed',
                        provider_sync_error=%s,
                        updated_at=now()
                    WHERE interview_id=%s
                    RETURNING *
                    """,
                    (_text(result.get("error") or "calendar_update_failed")[:1000], str(interview["interview_id"])),
                )
                return {"ok": False, "error": "calendar_update_failed", "result": result, "interview": dict(cur.fetchone() or interview)}
        else:
            result = _google_create(legacy, summary=summary, start=start, end=end, attendees=attendee_list, with_meet=with_meet)
            if not result.get("ok"):
                cur.execute(
                    """
                    UPDATE candidate_interviews
                    SET provider_sync_status='failed',
                        provider_sync_error=%s,
                        updated_at=now()
                    WHERE interview_id=%s
                    RETURNING *
                    """,
                    (_text(result.get("error") or "calendar_create_failed")[:1000], str(interview["interview_id"])),
                )
                return {"ok": False, "error": "calendar_create_failed", "result": result, "interview": dict(cur.fetchone() or interview), "interview_valid": True}

        new_event_id = legacy.interview_calendar_event_id(legacy.json_safe(result)) or event_id
        meet_link = legacy.interview_meet_link_from_calendar(legacy.json_safe(result)) or interview.get("meet_link")
        channel = "send_accepted" if attendee_list else interview.get("channel_send_status") or "not_requested"
        cur.execute(
            """
            UPDATE candidate_interviews
            SET calendar_event_id=COALESCE(%s, calendar_event_id),
                calendar_payload=%s,
                meet_link=COALESCE(%s, meet_link),
                provider_sync_status='synced',
                provider_sync_error=NULL,
                provider_synced_at=now(),
                calendar_invite_sent=%s,
                candidate_invited=%s,
                channel_send_status=%s,
                notification_channel=CASE WHEN %s THEN 'calendar_email' ELSE notification_channel END,
                invite_sent_at=CASE WHEN %s THEN COALESCE(invite_sent_at, now()) ELSE invite_sent_at END,
                updated_at=now()
            WHERE interview_id=%s
            RETURNING *
            """,
            (
                new_event_id,
                _json(result),
                meet_link,
                bool(new_event_id and attendee_list),
                bool(new_event_id and attendee_list),
                channel,
                bool(new_event_id and attendee_list),
                bool(new_event_id and attendee_list),
                str(interview["interview_id"]),
            ),
        )
        return {"ok": True, "result": result, "interview": dict(cur.fetchone() or interview)}
    except Exception as exc:
        cur.execute(
            """
            UPDATE candidate_interviews
            SET provider_sync_status='failed',
                provider_sync_error=%s,
                updated_at=now()
            WHERE interview_id=%s
            RETURNING *
            """,
            (str(exc)[:1000], str(interview["interview_id"])),
        )
        return {"ok": False, "error": "calendar_sync_exception", "interview": dict(cur.fetchone() or interview), "interview_valid": True}


def _sync_microsoft_for_interview(
    legacy: Any,
    cur: Any,
    interview: dict[str, Any],
    *,
    mode: str,
    attendees: list[str] | None = None,
) -> dict[str, Any]:
    import interview_microsoft_calendar as mcal

    if not mcal.microsoft_env_configured():
        cur.execute(
            """
            UPDATE candidate_interviews
            SET provider_sync_status='not_configured',
                provider_sync_error=%s,
                updated_at=now()
            WHERE interview_id=%s
            RETURNING *
            """,
            ("microsoft_certificate_not_configured", str(interview["interview_id"])),
        )
        return {"ok": False, "error": "microsoft_not_configured", "interview": dict(cur.fetchone() or interview)}

    mailbox = mcal.microsoft_mailbox_upn(company_code=str(interview.get("company_code") or ""), legacy=legacy)
    start = interview.get("scheduled_start")
    end = interview.get("scheduled_end")
    if isinstance(start, str):
        start = life.parse_aware_datetime(start, default_tz=timezone.utc)
    if isinstance(end, str):
        end = life.parse_aware_datetime(end, default_tz=timezone.utc)
    summary = f"OctoHR interview with {interview.get('candidate_name') or 'candidate'}"
    attendee_list = [a for a in (attendees or []) if a]
    if interview.get("candidate_email") and interview["candidate_email"] not in attendee_list:
        attendee_list.insert(0, str(interview["candidate_email"]))
    tz_name = _text(interview.get("timezone")) or "UTC"
    event_id = _text(interview.get("calendar_event_id")) or None
    payload_obj = interview.get("calendar_payload")
    if isinstance(payload_obj, str):
        try:
            payload_obj = json.loads(payload_obj)
        except Exception:
            payload_obj = {}
    if not isinstance(payload_obj, dict):
        payload_obj = {}
    online_meeting_id = _text(payload_obj.get("online_meeting_id") or interview.get("online_meeting_id")) or None
    existing_meet_link = _text(interview.get("meet_link") or payload_obj.get("meet_link")) or None

    cur.execute(
        """
        UPDATE candidate_interviews
        SET provider_sync_status=CASE
              WHEN %s='cancel' THEN 'cancellation_pending'
              WHEN %s='update' THEN 'update_pending'
              ELSE 'pending'
            END,
            updated_at=now()
        WHERE interview_id=%s
        """,
        (mode, mode, str(interview["interview_id"])),
    )
    try:
        token = mcal.mint_graph_token()
        if mode == "cancel":
            result = (
                {"ok": True, "skipped": True}
                if not event_id
                else mcal.cancel_teams_event(
                    token=token,
                    mailbox_upn=mailbox,
                    event_id=event_id,
                    online_meeting_id=online_meeting_id,
                )
            )
        elif mode == "update" and event_id:
            result = mcal.update_teams_event(
                token=token,
                mailbox_upn=mailbox,
                event_id=event_id,
                summary=summary,
                start=start,
                end=end,
                timezone_name=tz_name,
                attendees=attendee_list,
                meet_link=existing_meet_link,
                online_meeting_id=online_meeting_id,
            )
        else:
            result = mcal.create_teams_event(
                token=token,
                mailbox_upn=mailbox,
                summary=summary,
                start=start,
                end=end,
                timezone_name=tz_name,
                attendees=attendee_list,
            )
        if not result.get("ok"):
            cur.execute(
                """
                UPDATE candidate_interviews
                SET provider_sync_status='failed',
                    provider_sync_error=%s,
                    updated_at=now()
                WHERE interview_id=%s
                RETURNING *
                """,
                (_text(result.get("error") or result.get("detail") or "microsoft_sync_failed")[:1000], str(interview["interview_id"])),
            )
            return {
                "ok": False,
                "error": result.get("error") or "microsoft_sync_failed",
                "result": result,
                "interview": dict(cur.fetchone() or interview),
                "interview_valid": True,
            }
        new_event_id = _text(result.get("event_id")) or event_id
        meet_link = _text(result.get("meet_link")) or interview.get("meet_link")
        channel = "send_accepted" if attendee_list and mode != "cancel" else interview.get("channel_send_status") or "not_requested"
        cur.execute(
            """
            UPDATE candidate_interviews
            SET calendar_event_id=COALESCE(%s, calendar_event_id),
                calendar_payload=%s,
                meet_link=COALESCE(%s, meet_link),
                provider_key='microsoft',
                provider_sync_status='synced',
                provider_sync_error=NULL,
                provider_synced_at=now(),
                calendar_invite_sent=%s,
                candidate_invited=%s,
                channel_send_status=%s,
                notification_channel=CASE WHEN %s THEN 'calendar_email' ELSE notification_channel END,
                invite_sent_at=CASE WHEN %s THEN COALESCE(invite_sent_at, now()) ELSE invite_sent_at END,
                updated_at=now()
            WHERE interview_id=%s
            RETURNING *
            """,
            (
                new_event_id if mode != "cancel" else event_id,
                _json(result),
                meet_link,
                bool(mode != "cancel" and new_event_id and attendee_list),
                bool(mode != "cancel" and new_event_id and attendee_list),
                "intentionally_skipped" if mode == "cancel" else channel,
                bool(mode != "cancel" and new_event_id and attendee_list),
                bool(mode != "cancel" and new_event_id and attendee_list),
                str(interview["interview_id"]),
            ),
        )
        return {"ok": True, "result": result, "interview": dict(cur.fetchone() or interview)}
    except Exception as exc:
        cur.execute(
            """
            UPDATE candidate_interviews
            SET provider_sync_status='failed',
                provider_sync_error=%s,
                updated_at=now()
            WHERE interview_id=%s
            RETURNING *
            """,
            (str(exc)[:1000], str(interview["interview_id"])),
        )
        return {"ok": False, "error": "microsoft_sync_exception", "interview": dict(cur.fetchone() or interview), "interview_valid": True}


def schedule_interview(
    *,
    company_code: str,
    app_key: str,
    start: Any,
    end: Any = None,
    duration_minutes: int | None = None,
    timezone_name: str | None = None,
    meeting_type: Any = "manual_link",
    location: Any = None,
    meet_link: Any = None,
    panel: list[Any] | None = None,
    idempotency_key: str | None = None,
    actor: dict[str, Any] | None = None,
    source: str = "dashboard_schedule",
    sync_external: bool = True,
    move_application_stage: bool = True,
    confirmation: dict[str, Any] | None = None,
    permissions: set[str] | list[str] | None = None,
    override_conflicts: bool = False,
    override_reason: str | None = None,
) -> dict[str, Any]:
    legacy = _legacy()
    company = _company(company_code)
    app_key = _text(app_key)
    actor = _actor(actor)
    if not company or not app_key:
        raise life.InterviewAuthorityError("tenant_scope_required", "company_code and app_key are required.", status_code=422)
    _require_live_interviews(legacy, company)

    application = legacy.dashboard_application_or_404(app_key, company)
    start_dt, end_dt, tz_name, minutes = resolve_schedule_window(
        legacy, company, start=start, end=end, duration_minutes=duration_minutes, timezone_name=timezone_name
    )
    google_connected = life.google_calendar_configured(legacy)
    try:
        import interview_microsoft_calendar as mcal

        microsoft_connected = mcal.microsoft_env_configured()
    except Exception:
        microsoft_connected = False
    meeting = resolve_meeting_fields(
        meeting_type=meeting_type,
        location=location,
        meet_link=meet_link,
        google_connected=google_connected and life.normalize_meeting_type(meeting_type) == "google_meet",
        microsoft_connected=microsoft_connected and life.normalize_meeting_type(meeting_type) == "microsoft_teams",
    )
    # Explicit google_meet request when connected.
    if life.normalize_meeting_type(meeting_type) == "google_meet" and google_connected:
        meeting = resolve_meeting_fields(
            meeting_type="google_meet",
            location=location,
            meet_link=meet_link,
            google_connected=True,
            microsoft_connected=False,
        )
        meeting["meeting_type"] = "google_meet"
        meeting["provider_key"] = "google"
        meeting["provider_sync_status"] = "pending"
        if not meeting.get("meet_link"):
            meeting["meet_link"] = None
    if life.normalize_meeting_type(meeting_type) == "microsoft_teams" and microsoft_connected:
        meeting = resolve_meeting_fields(
            meeting_type="microsoft_teams",
            location=location,
            meet_link=meet_link,
            google_connected=False,
            microsoft_connected=True,
        )
        meeting["meeting_type"] = "microsoft_teams"
        meeting["provider_key"] = "microsoft"
        meeting["provider_sync_status"] = "pending"
        if not meeting.get("meet_link"):
            meeting["meet_link"] = None
    panel_norm = life.normalize_panel(panel)
    if not panel_norm and actor.get("actor_user_id"):
        panel_norm = life.normalize_panel(
            [
                {
                    "user_id": actor.get("actor_user_id"),
                    "phone": actor.get("actor_phone"),
                    "panel_role": "organizer",
                    "is_organizer": True,
                }
            ]
        )

    payload = {
        "scheduled_start": start_dt,
        "scheduled_end": end_dt,
        "timezone": tz_name,
        "duration_minutes": minutes,
        "meeting_type": meeting["meeting_type"],
        "location": meeting.get("location"),
        "meet_link": meeting.get("meet_link"),
        "panel": panel_norm,
        "provider_key": meeting["provider_key"],
        "provider_sync_status": meeting["provider_sync_status"],
        "source": source,
    }
    key = _text(idempotency_key) or f"schedule:{company}:{app_key}:{start_dt.isoformat()}:{end_dt.isoformat()}:{meeting['meeting_type']}"

    with legacy.db_connect() as conn:
        with conn.cursor() as cur:
            life.ensure_interview_schema(cur)
            op, created = life.claim_or_load_operation(
                cur,
                company_code=company,
                app_key=app_key,
                action="schedule",
                idempotency_key=key,
                payload=payload,
                actor=actor,
            )
            if not created and op.get("lifecycle_status") == "completed" and op.get("interview_id"):
                interview = load_interview(cur, str(op["interview_id"]), company)
                assignments = life.list_assignments(cur, str(op["interview_id"]))
                conn.commit()
                return {
                    "ok": True,
                    "idempotent_replay": True,
                    "operation_id": str(op["operation_id"]),
                    "interview": enrich_interview_row(interview, assignments=assignments),
                    "provider_sync": {"ok": life.normalize_provider_sync_state(interview.get("provider_sync_status") if interview else None) == "synced"},
                }

            import calendar_conflicts as cal_conflicts

            panel_attendees = [
                {
                    "user_id": _text(p.get("assignee_user_id")),
                    "email": _text(p.get("assignee_email")),
                    "role": "optional" if p.get("is_required") is False else "required",
                }
                for p in (panel_norm or [])
                if _text(p.get("assignee_user_id")) or _text(p.get("assignee_email"))
            ]
            try:
                conflict_result = cal_conflicts.require_no_blocking_conflicts(
                    cur,
                    legacy,
                    company_code=company,
                    start=start_dt,
                    end=end_dt,
                    timezone_name=tz_name,
                    organizer_user_id=next(
                        (_text(p.get("assignee_user_id")) for p in (panel_norm or []) if p.get("is_organizer")),
                        None,
                    ),
                    attendees=panel_attendees,
                    app_key=app_key,
                    panel=panel_norm,
                    override_conflicts=bool(override_conflicts),
                    override_reason=_text(override_reason) or None,
                    actor_permissions=permissions or [],
                    include_interview_legacy=True,
                    include_calendar_events=True,
                )
            except cal_conflicts.SchedulingConflictError as exc:
                life.mark_operation(
                    cur,
                    str(op["operation_id"]),
                    lifecycle_status="failed",
                    result_payload={"error": "scheduling_conflict", "conflicts": exc.conflicts},
                )
                conn.commit()
                raise life.InterviewAuthorityError(
                    "scheduling_conflict",
                    exc.message,
                    status_code=409,
                    conflicts=legacy.json_safe(exc.conflicts),
                    draft_preserved=True,
                ) from exc
            if conflict_result.get("overridden"):
                cal_conflicts.record_conflict_override_audit(
                    cur,
                    legacy,
                    company_code=company,
                    event_id=None,
                    actor_user_id=_text(actor.get("actor_user_id")),
                    conflicts=conflict_result.get("conflicts") or [],
                    override_reason=_text(override_reason),
                    source="interview_schedule",
                )

            retention_days = life.video_retention_days(legacy, company)
            try:
                cur.execute(
                    """
                    UPDATE candidate_interviews
                    SET status='rescheduled',
                        updated_by_phone=%s,
                        updated_at=now()
                    WHERE company_code=%s
                      AND app_key=%s
                      AND lower(COALESCE(status,'')) IN ('scheduled','rescheduled')
                      AND lower(COALESCE(interview_type,'live')) <> 'async_video'
                    """,
                    (actor.get("actor_phone"), company, app_key),
                )
                cur.execute(
                    """
                    INSERT INTO candidate_interviews (
                      company_code, app_key, phone, candidate_name, candidate_email, position_code, position_title,
                      interview_type, status, feedback_status, human_feedback_status, scheduled_start, scheduled_end,
                      timezone, duration_minutes, meeting_type, location, meet_link, provider_key, provider_sync_status,
                      channel_send_status, rsvp_status, schedule_operation_id, retention_expires_at, source,
                      created_by_phone, updated_by_phone
                    )
                    VALUES (
                      %s,%s,%s,%s,%s,%s,%s,'live','scheduled','notes_pending','notes_pending',%s,%s,%s,%s,%s,%s,%s,%s,%s,
                      'not_requested','not_requested',%s, now() + make_interval(days => %s), %s, %s, %s
                    )
                    RETURNING *
                    """,
                    (
                        company,
                        app_key,
                        application.get("phone"),
                        application.get("candidate_name"),
                        application.get("candidate_email"),
                        application.get("position_code"),
                        application.get("position_title"),
                        start_dt,
                        end_dt,
                        tz_name,
                        minutes,
                        meeting["meeting_type"],
                        meeting.get("location"),
                        meeting.get("meet_link"),
                        meeting["provider_key"],
                        meeting["provider_sync_status"],
                        str(op["operation_id"]),
                        retention_days,
                        source,
                        actor.get("actor_phone"),
                        actor.get("actor_phone"),
                    ),
                )
            except Exception as exc:
                # Unique active live interview race — one winner.
                conn.rollback()
                with legacy.db_connect() as conn2:
                    with conn2.cursor() as cur2:
                        life.ensure_interview_schema(cur2)
                        cur2.execute(
                            """
                            SELECT * FROM candidate_interviews
                            WHERE company_code=%s AND app_key=%s
                              AND lower(COALESCE(status,'')) IN ('scheduled','rescheduled')
                              AND lower(COALESCE(interview_type,'live')) <> 'async_video'
                            ORDER BY updated_at DESC LIMIT 1
                            """,
                            (company, app_key),
                        )
                        winner = cur2.fetchone()
                        if winner and str(op.get("idempotency_key") or "") == key:
                            # Another concurrent writer won; treat as conflict unless same op completed.
                            life.mark_operation(
                                cur2,
                                str(op["operation_id"]),
                                lifecycle_status="failed",
                                result_payload={"error": "concurrent_schedule_conflict", "detail": str(exc)},
                            )
                            conn2.commit()
                        raise life.InterviewAuthorityError(
                            "concurrent_schedule_conflict",
                            "Another interview schedule won the concurrent write for this application.",
                            status_code=409,
                            existing_interview_id=str((winner or {}).get("interview_id") or ""),
                        ) from exc

            interview = dict(cur.fetchone() or {})
            assignments = life.replace_assignments(cur, interview, panel_norm)
            life.mark_operation(
                cur,
                str(op["operation_id"]),
                interview_id=str(interview["interview_id"]),
                lifecycle_status="committed",
                provider_key=meeting["provider_key"],
                provider_sync_status=meeting["provider_sync_status"],
            )

            sync_result = {"ok": True, "skipped": True}
            if sync_external and meeting["provider_key"] == "google":
                sync_result = sync_provider_for_interview(legacy, cur, interview, mode="create", attendees=[a.get("assignee_email") for a in panel_norm if a.get("assignee_email")])
                interview = sync_result.get("interview") or interview

            life.mark_operation(
                cur,
                str(op["operation_id"]),
                lifecycle_status="completed",
                provider_sync_status=interview.get("provider_sync_status"),
                provider_event_id=interview.get("calendar_event_id"),
                provider_error=interview.get("provider_sync_error"),
                meet_link=interview.get("meet_link"),
                result_payload={"interview_id": str(interview.get("interview_id")), "sync": sync_result.get("ok"), "sync_error": sync_result.get("error")},
            )
            # C2 durability: required Calendar intent in the same TX (worker is async).
            _require_calendar_outbox_intent(
                cur,
                legacy,
                interview=interview,
                assignments=assignments,
                operation="ensure",
                operation_token=str(op["operation_id"]),
            )
            conn.commit()

    record_event(legacy, interview, "scheduled", {"source": source, "meeting_type": meeting["meeting_type"], "sync": sync_result}, actor=actor, action="schedule_interview")
    legacy.update_application_interview_snapshot(app_key, interview)

    stage_update = None
    if move_application_stage and hasattr(legacy, "canonical_lifecycle_enabled") and legacy.canonical_lifecycle_enabled():
        confirmation = confirmation or {}
        stage_update = legacy.update_application_status(
            application,
            "interview",
            trigger="schedule_interview",
            human_confirmed=bool(confirmation.get("human_confirmed", True)),
            actor_type=actor.get("actor_type") or "human",
            actor_user_id=actor.get("actor_user_id"),
            actor_phone=actor.get("actor_phone"),
            channel=str(confirmation.get("channel") or "web"),
            permissions=set(permissions or confirmation.get("permissions") or []),
            expected_from_stage=confirmation.get("expected_from_stage"),
            expected_version=confirmation.get("expected_version"),
            confirmation_id=confirmation.get("confirmation_id"),
            confirmation_token=confirmation.get("confirmation_token"),
            confirmation_action="schedule_interview",
            confirmation_payload=confirmation.get("confirmation_payload") if isinstance(confirmation.get("confirmation_payload"), dict) else {},
            idempotency_key=confirmation.get("idempotency_key") or f"lifecycle-schedule:{company}:{app_key}:{key}",
            metadata={"interview_id": str(interview.get("interview_id")), "source": source},
        )

    with legacy.db_connect() as conn:
        with conn.cursor() as cur:
            interview = load_interview(cur, str(interview["interview_id"]), company) or interview
            assignments = life.list_assignments(cur, str(interview["interview_id"]))

    return {
        "ok": True,
        "idempotent_replay": False,
        "operation_id": str(op["operation_id"]),
        "interview": enrich_interview_row(interview, assignments=assignments),
        "provider_sync": {
            "ok": bool(sync_result.get("ok")),
            "error": sync_result.get("error"),
            "status": interview.get("provider_sync_status"),
            "interview_valid": True,
        },
        "application_stage_update": legacy.json_safe(stage_update) if stage_update else None,
    }


def reschedule_interview(
    *,
    company_code: str,
    interview_id: str,
    start: Any,
    end: Any = None,
    duration_minutes: int | None = None,
    timezone_name: str | None = None,
    meeting_type: Any = None,
    location: Any = None,
    meet_link: Any = None,
    panel: list[Any] | None = None,
    idempotency_key: str | None = None,
    actor: dict[str, Any] | None = None,
    sync_external: bool = True,
    permissions: set[str] | list[str] | None = None,
    override_conflicts: bool = False,
    override_reason: str | None = None,
) -> dict[str, Any]:
    legacy = _legacy()
    company = _company(company_code)
    actor = _actor(actor)
    interview_id = _text(interview_id)
    key = _text(idempotency_key) or f"reschedule:{company}:{interview_id}:{_text(start)}:{_text(end)}"

    with legacy.db_connect() as conn:
        with conn.cursor() as cur:
            life.ensure_interview_schema(cur)
            current = load_interview(cur, interview_id, company)
            if not current:
                raise life.InterviewAuthorityError("interview_not_found", "Interview not found.", status_code=404)
            if life.normalize_interview_status(current.get("status")) == "cancelled":
                raise life.InterviewAuthorityError("interview_cancelled", "Cancelled interviews cannot be rescheduled.", status_code=409)

            op, created = life.claim_or_load_operation(
                cur,
                company_code=company,
                app_key=_text(current.get("app_key")),
                action="reschedule",
                idempotency_key=key,
                payload={"interview_id": interview_id, "start": start, "end": end},
                actor=actor,
            )
            if not created and op.get("lifecycle_status") == "completed" and op.get("interview_id"):
                interview = load_interview(cur, str(op["interview_id"]), company)
                assignments = life.list_assignments(cur, str(op["interview_id"]))
                conn.commit()
                return {"ok": True, "idempotent_replay": True, "interview": enrich_interview_row(interview, assignments=assignments)}

            start_dt, end_dt, tz_name, minutes = resolve_schedule_window(
                legacy,
                company,
                start=start,
                end=end,
                duration_minutes=duration_minutes or current.get("duration_minutes"),
                timezone_name=timezone_name or current.get("timezone"),
            )
            google_connected = life.google_calendar_configured(legacy)
            try:
                import interview_microsoft_calendar as mcal

                microsoft_connected = mcal.microsoft_env_configured()
            except Exception:
                microsoft_connected = False
            mtype = meeting_type if meeting_type is not None else current.get("meeting_type")
            meeting = resolve_meeting_fields(
                meeting_type=mtype,
                location=location if location is not None else current.get("location"),
                meet_link=meet_link if meet_link is not None else current.get("meet_link"),
                google_connected=google_connected and life.normalize_meeting_type(mtype) == "google_meet",
                microsoft_connected=microsoft_connected and life.normalize_meeting_type(mtype) == "microsoft_teams",
            )
            if life.normalize_meeting_type(mtype) == "google_meet" and google_connected:
                meeting["meeting_type"] = "google_meet"
                meeting["provider_key"] = "google"
                meeting["provider_sync_status"] = "update_pending" if current.get("calendar_event_id") else "pending"
            if life.normalize_meeting_type(mtype) == "microsoft_teams" and microsoft_connected:
                meeting["meeting_type"] = "microsoft_teams"
                meeting["provider_key"] = "microsoft"
                meeting["provider_sync_status"] = "update_pending" if current.get("calendar_event_id") else "pending"
            panel_norm = life.normalize_panel(panel) if panel is not None else life.list_assignments(cur, interview_id)
            if panel is not None:
                panel_norm = life.normalize_panel(panel)
            else:
                panel_norm = [
                    {
                        "assignee_user_id": a.get("assignee_user_id"),
                        "assignee_email": a.get("assignee_email"),
                        "assignee_name": a.get("assignee_name"),
                        "assignee_phone": a.get("assignee_phone"),
                        "panel_role": a.get("panel_role"),
                        "is_organizer": a.get("is_organizer"),
                        "is_required": a.get("is_required"),
                    }
                    for a in life.list_assignments(cur, interview_id)
                ]

            import calendar_conflicts as cal_conflicts

            panel_attendees = [
                {
                    "user_id": _text(p.get("assignee_user_id")),
                    "email": _text(p.get("assignee_email")),
                    "role": "optional" if p.get("is_required") is False else "required",
                }
                for p in (panel_norm or [])
                if _text(p.get("assignee_user_id")) or _text(p.get("assignee_email"))
            ]
            try:
                conflict_result = cal_conflicts.require_no_blocking_conflicts(
                    cur,
                    legacy,
                    company_code=company,
                    start=start_dt,
                    end=end_dt,
                    timezone_name=tz_name,
                    organizer_user_id=next(
                        (_text(p.get("assignee_user_id")) for p in (panel_norm or []) if p.get("is_organizer")),
                        None,
                    ),
                    attendees=panel_attendees,
                    exclude_event_id=None,
                    app_key=_text(current.get("app_key")),
                    panel=panel_norm,
                    exclude_interview_id=interview_id,
                    override_conflicts=bool(override_conflicts),
                    override_reason=_text(override_reason) or None,
                    actor_permissions=permissions or [],
                    include_interview_legacy=True,
                    include_calendar_events=True,
                )
            except cal_conflicts.SchedulingConflictError as exc:
                raise life.InterviewAuthorityError(
                    "scheduling_conflict",
                    exc.message,
                    status_code=409,
                    conflicts=legacy.json_safe(exc.conflicts),
                    draft_preserved=True,
                ) from exc
            if conflict_result.get("overridden"):
                cal_conflicts.record_conflict_override_audit(
                    cur,
                    legacy,
                    company_code=company,
                    event_id=None,
                    actor_user_id=_text(actor.get("actor_user_id")),
                    conflicts=conflict_result.get("conflicts") or [],
                    override_reason=_text(override_reason),
                    source="interview_reschedule",
                )

            # Keep one active Wathefni interview row — update in place; mark prior slot as superseded via event.
            cur.execute(
                """
                UPDATE candidate_interviews
                SET scheduled_start=%s,
                    scheduled_end=%s,
                    timezone=%s,
                    duration_minutes=%s,
                    meeting_type=%s,
                    location=%s,
                    meet_link=%s,
                    provider_key=%s,
                    provider_sync_status=%s,
                    status='scheduled',
                    updated_by_phone=%s,
                    schedule_operation_id=%s,
                    updated_at=now()
                WHERE interview_id=%s AND company_code=%s
                RETURNING *
                """,
                (
                    start_dt,
                    end_dt,
                    tz_name,
                    minutes,
                    meeting["meeting_type"],
                    meeting.get("location"),
                    meeting.get("meet_link"),
                    meeting["provider_key"],
                    meeting["provider_sync_status"],
                    actor.get("actor_phone"),
                    str(op["operation_id"]),
                    interview_id,
                    company,
                ),
            )
            interview = dict(cur.fetchone() or {})
            assignments = life.replace_assignments(cur, interview, panel_norm)

            sync_result = {"ok": True, "skipped": True}
            if sync_external and meeting["provider_key"] == "google":
                mode = "update" if interview.get("calendar_event_id") else "create"
                sync_result = sync_provider_for_interview(
                    legacy,
                    cur,
                    interview,
                    mode=mode,
                    attendees=[a.get("assignee_email") for a in panel_norm if a.get("assignee_email")],
                )
                interview = sync_result.get("interview") or interview

            life.mark_operation(
                cur,
                str(op["operation_id"]),
                interview_id=interview_id,
                lifecycle_status="completed",
                provider_event_id=interview.get("calendar_event_id"),
                provider_sync_status=interview.get("provider_sync_status"),
                provider_error=interview.get("provider_sync_error"),
                result_payload={"sync": sync_result.get("ok"), "sync_error": sync_result.get("error")},
            )
            # C2 durability: ensure when schedule/meeting fields change; sync_attendees for panel-only.
            def _as_dt(value: Any):
                if isinstance(value, datetime):
                    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
                return life.parse_aware_datetime(value, default_tz=timezone.utc)

            times_changed = (
                _as_dt(current.get("scheduled_start")) != start_dt
                or _as_dt(current.get("scheduled_end")) != end_dt
                or _text(current.get("timezone")) != tz_name
                or _text(current.get("meeting_type")) != _text(meeting.get("meeting_type"))
                or _text(current.get("location")) != _text(meeting.get("location"))
                or _text(current.get("meet_link")) != _text(meeting.get("meet_link"))
            )
            cal_op = "sync_attendees" if (panel is not None and not times_changed) else "ensure"
            _require_calendar_outbox_intent(
                cur,
                legacy,
                interview=interview,
                assignments=assignments,
                operation=cal_op,
                operation_token=str(op["operation_id"]),
            )
            conn.commit()

    record_event(legacy, interview, "rescheduled", {"sync": sync_result}, actor=actor, action="reschedule_interview")
    legacy.update_application_interview_snapshot(_text(interview.get("app_key")), interview)
    return {
        "ok": True,
        "idempotent_replay": False,
        "interview": enrich_interview_row(interview, assignments=assignments),
        "provider_sync": {"ok": bool(sync_result.get("ok")), "error": sync_result.get("error"), "status": interview.get("provider_sync_status"), "interview_valid": True},
    }


def cancel_interview(
    *,
    company_code: str,
    interview_id: str,
    idempotency_key: str | None = None,
    actor: dict[str, Any] | None = None,
    sync_external: bool = True,
    revert_application_stage: bool = True,
    permissions: set[str] | list[str] | None = None,
) -> dict[str, Any]:
    legacy = _legacy()
    company = _company(company_code)
    actor = _actor(actor)
    interview_id = _text(interview_id)
    key = _text(idempotency_key) or f"cancel:{company}:{interview_id}"

    with legacy.db_connect() as conn:
        with conn.cursor() as cur:
            life.ensure_interview_schema(cur)
            current = load_interview(cur, interview_id, company)
            if not current:
                raise life.InterviewAuthorityError("interview_not_found", "Interview not found.", status_code=404)

            op, created = life.claim_or_load_operation(
                cur,
                company_code=company,
                app_key=_text(current.get("app_key")),
                action="cancel",
                idempotency_key=key,
                payload={"interview_id": interview_id},
                actor=actor,
            )
            if life.normalize_interview_status(current.get("status")) == "cancelled":
                life.mark_operation(cur, str(op["operation_id"]), interview_id=interview_id, lifecycle_status="completed", result_payload={"idempotent": True})
                assignments = life.list_assignments(cur, interview_id)
                conn.commit()
                return {"ok": True, "idempotent_replay": True, "interview": enrich_interview_row(current, assignments=assignments)}

            cur.execute(
                """
                UPDATE candidate_interviews
                SET status='cancelled',
                    channel_send_status=CASE
                      WHEN channel_send_status IN ('send_accepted','delivered','pending') THEN channel_send_status
                      ELSE channel_send_status
                    END,
                    updated_by_phone=%s,
                    schedule_operation_id=%s,
                    updated_at=now()
                WHERE interview_id=%s AND company_code=%s
                RETURNING *
                """,
                (actor.get("actor_phone"), str(op["operation_id"]), interview_id, company),
            )
            interview = dict(cur.fetchone() or {})

            sync_result = {"ok": True, "skipped": True}
            if sync_external and (_text(interview.get("provider_key")) == "google" or interview.get("calendar_event_id")):
                interview["provider_key"] = interview.get("provider_key") or "google"
                sync_result = sync_provider_for_interview(legacy, cur, interview, mode="cancel")
                interview = sync_result.get("interview") or interview

            life.mark_operation(
                cur,
                str(op["operation_id"]),
                interview_id=interview_id,
                lifecycle_status="completed",
                provider_sync_status=interview.get("provider_sync_status"),
                provider_error=interview.get("provider_sync_error"),
                result_payload={"sync": sync_result.get("ok")},
            )
            _require_calendar_outbox_intent(
                cur,
                legacy,
                interview=interview,
                assignments=life.list_assignments(cur, interview_id),
                operation="cancel",
                operation_token=str(op["operation_id"]),
            )
            conn.commit()

    record_event(legacy, interview, "status_cancelled", {"sync": sync_result}, actor=actor, action="cancel_interview")
    legacy.update_application_interview_snapshot(_text(interview.get("app_key")), interview)

    stage_update = None
    if revert_application_stage:
        try:
            import recruiting_lifecycle as _rl

            application = legacy.find_application_by_key(_text(interview.get("app_key")), company_code=company) or {}
            app_status = _text(application.get("status")).lower()
            if app_status in {"interview", "interviewing"}:
                stage_update = _rl.transition_application(
                    legacy,
                    app_key=_text(interview.get("app_key")),
                    company_code=company,
                    to_stage="shortlisted",
                    trigger="interview_cancelled",
                    expected_from_stage="interview",
                    actor_type=actor.get("actor_type") or "human",
                    actor_user_id=actor.get("actor_user_id"),
                    actor_phone=actor.get("actor_phone"),
                    channel="web",
                    idempotency_key=f"interview-cancel-stage:{company}:{interview_id}:{key}",
                    metadata={"interview_id": interview_id, "interview_status": "cancelled"},
                    run_hire_side_effects=False,
                    permissions=set(permissions or []),
                )
        except Exception as exc:
            stage_update = {"ok": False, "error": str(exc)}

    with legacy.db_connect() as conn:
        with conn.cursor() as cur:
            interview = load_interview(cur, interview_id, company) or interview
            assignments = life.list_assignments(cur, interview_id)

    return {
        "ok": True,
        "idempotent_replay": not created,
        "interview": enrich_interview_row(interview, assignments=assignments),
        "provider_sync": {"ok": bool(sync_result.get("ok")), "error": sync_result.get("error"), "status": interview.get("provider_sync_status")},
        "application_stage_update": legacy.json_safe(stage_update) if stage_update else None,
    }


def submit_feedback(
    *,
    company_code: str,
    interview_id: str,
    answers: dict[str, Any],
    free_text_notes: str | None = None,
    overall_rating: float | None = None,
    definition_version_id: str | None = None,
    actor: dict[str, Any] | None = None,
    rater: dict[str, Any] | None = None,
) -> dict[str, Any]:
    legacy = _legacy()
    company = _company(company_code)
    actor = _actor(actor)
    rater = rater or {}
    rater_user_id = _text(rater.get("user_id") or actor.get("actor_user_id")) or None
    rater_email = _text(rater.get("email")).lower() or None
    rater_name = _text(rater.get("name")) or None
    if not rater_user_id and not rater_email:
        raise life.InterviewAuthorityError("rater_required", "Feedback requires an assigned rater user or email.")

    with legacy.db_connect() as conn:
        with conn.cursor() as cur:
            life.ensure_interview_schema(cur)
            interview = load_interview(cur, interview_id, company)
            if not interview:
                raise life.InterviewAuthorityError("interview_not_found", "Interview not found.", status_code=404)
            version = None
            if definition_version_id:
                cur.execute(
                    "SELECT * FROM interview_feedback_definition_versions WHERE version_id=%s LIMIT 1",
                    (definition_version_id,),
                )
                version = cur.fetchone()
            if not version:
                version = life.default_feedback_version(cur, company)
            if not version:
                raise life.InterviewAuthorityError("feedback_definition_missing", "No published feedback definition is available.")
            version = dict(version)

            cur.execute(
                """
                SELECT * FROM interview_feedback_submissions
                WHERE interview_id=%s
                  AND coalesce(rater_user_id,'') = coalesce(%s,'')
                  AND coalesce(lower(rater_email),'') = coalesce(%s,'')
                  AND status IN ('draft','submitted','reopened')
                ORDER BY updated_at DESC
                LIMIT 1
                FOR UPDATE
                """,
                (interview_id, rater_user_id or "", rater_email or ""),
            )
            existing = cur.fetchone()
            if existing and str(existing.get("status")) == "submitted":
                raise life.InterviewAuthorityError(
                    "feedback_immutable",
                    "Finalized feedback is immutable unless reopened.",
                    status_code=409,
                    submission_id=str(existing.get("submission_id")),
                )

            answers = answers if isinstance(answers, dict) else {}
            if existing:
                revision = int(existing.get("revision") or 1)
                if str(existing.get("status")) == "reopened":
                    revision += 1
                cur.execute(
                    """
                    UPDATE interview_feedback_submissions
                    SET status='submitted',
                        answers=%s,
                        free_text_notes=%s,
                        overall_rating=%s,
                        definition_version_id=%s,
                        submitted_at=now(),
                        revision=%s,
                        updated_at=now()
                    WHERE submission_id=%s
                    RETURNING *
                    """,
                    (
                        _json(answers),
                        free_text_notes,
                        overall_rating,
                        str(version["version_id"]),
                        revision,
                        str(existing["submission_id"]),
                    ),
                )
                submission = dict(cur.fetchone() or {})
            else:
                cur.execute(
                    """
                    INSERT INTO interview_feedback_submissions (
                      interview_id, company_code, app_key, definition_version_id,
                      rater_user_id, rater_email, rater_name, status, answers, free_text_notes,
                      overall_rating, submitted_at, revision
                    )
                    VALUES (%s,%s,%s,%s,%s,%s,%s,'submitted',%s,%s,%s,now(),1)
                    RETURNING *
                    """,
                    (
                        interview_id,
                        company,
                        interview.get("app_key"),
                        str(version["version_id"]),
                        rater_user_id,
                        rater_email,
                        rater_name,
                        _json(answers),
                        free_text_notes,
                        overall_rating,
                    ),
                )
                submission = dict(cur.fetchone() or {})

            cur.execute(
                """
                INSERT INTO interview_feedback_submission_revisions (
                  submission_id, company_code, interview_id, revision, status, answers,
                  free_text_notes, overall_rating, actor_user_id, actor_role, reason
                )
                VALUES (%s,%s,%s,%s,'submitted',%s,%s,%s,%s,%s,%s)
                """,
                (
                    str(submission["submission_id"]),
                    company,
                    interview_id,
                    int(submission.get("revision") or 1),
                    _json(answers),
                    free_text_notes,
                    overall_rating,
                    actor.get("actor_user_id"),
                    actor.get("actor_role"),
                    "submit",
                ),
            )
            # Human scorecard completion is independent of free-text notes / AI summary.
            cur.execute(
                """
                UPDATE candidate_interviews
                SET human_feedback_status='feedback_complete',
                    updated_by_phone=%s,
                    updated_at=now()
                WHERE interview_id=%s
                RETURNING *
                """,
                (actor.get("actor_phone"), interview_id),
            )
            interview = dict(cur.fetchone() or interview)
            conn.commit()

    record_event(
        legacy,
        interview,
        "feedback_submitted",
        {"submission_id": str(submission["submission_id"]), "definition_version_id": str(version["version_id"])},
        actor=actor,
        action="submit_interview_feedback",
    )
    # Explicitly do not push scores into Ranking.
    return {
        "ok": True,
        "submission": legacy.json_safe(submission),
        "interview": enrich_interview_row(interview),
        "ranking_updated": False,
    }


def reopen_feedback(
    *,
    company_code: str,
    submission_id: str,
    reason: str,
    actor: dict[str, Any] | None = None,
) -> dict[str, Any]:
    legacy = _legacy()
    company = _company(company_code)
    actor = _actor(actor)
    reason = _text(reason)
    if not reason:
        raise life.InterviewAuthorityError("reopen_reason_required", "A reopen reason is required.")
    with legacy.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT * FROM interview_feedback_submissions
                WHERE submission_id=%s AND company_code=%s
                LIMIT 1 FOR UPDATE
                """,
                (submission_id, company),
            )
            submission = cur.fetchone()
            if not submission:
                raise life.InterviewAuthorityError("feedback_not_found", "Feedback submission not found.", status_code=404)
            submission = dict(submission)
            if str(submission.get("status")) != "submitted":
                raise life.InterviewAuthorityError("feedback_not_finalized", "Only submitted feedback can be reopened.", status_code=409)
            next_revision = int(submission.get("revision") or 1) + 1
            cur.execute(
                """
                UPDATE interview_feedback_submissions
                SET status='reopened', reopened_at=now(), reopen_reason=%s, revision=%s, updated_at=now()
                WHERE submission_id=%s
                RETURNING *
                """,
                (reason, next_revision, submission_id),
            )
            submission = dict(cur.fetchone() or {})
            cur.execute(
                """
                INSERT INTO interview_feedback_submission_revisions (
                  submission_id, company_code, interview_id, revision, status, answers,
                  free_text_notes, overall_rating, actor_user_id, actor_role, reason
                )
                VALUES (%s,%s,%s,%s,'reopened',%s,%s,%s,%s,%s,%s)
                """,
                (
                    submission_id,
                    company,
                    str(submission.get("interview_id")),
                    next_revision,
                    _json(submission.get("answers") or {}),
                    submission.get("free_text_notes"),
                    submission.get("overall_rating"),
                    actor.get("actor_user_id"),
                    actor.get("actor_role"),
                    reason,
                ),
            )
            cur.execute(
                """
                UPDATE candidate_interviews
                SET human_feedback_status='notes_pending', updated_at=now()
                WHERE interview_id=%s
                """,
                (str(submission.get("interview_id")),),
            )
            interview = load_interview(cur, str(submission.get("interview_id")), company)
            conn.commit()
    record_event(legacy, interview or {}, "feedback_reopened", {"submission_id": submission_id, "reason": reason}, actor=actor, action="reopen_interview_feedback")
    return {"ok": True, "submission": legacy.json_safe(submission), "interview": enrich_interview_row(interview)}


def save_notes_only(
    *,
    company_code: str,
    interview_id: str,
    notes: str,
    transcript: str | None = None,
    status: str | None = None,
    generate_summary: bool = False,
    actor: dict[str, Any] | None = None,
    expected_updated_at: str | None = None,
    expected_version: int | None = None,
) -> dict[str, Any]:
    """Free-text notes + optional AI summary. Does not complete human scorecard feedback."""
    import concurrency_safety as _cs

    legacy = _legacy()
    company = _company(company_code)
    actor = _actor(actor)
    notes = _text(notes)
    transcript = _text(transcript)
    if not notes and not transcript:
        raise life.InterviewAuthorityError("interview_notes_required", "Notes or transcript text is required.")
    interview = legacy.fetch_candidate_interview(interview_id, company)
    if not interview:
        raise life.InterviewAuthorityError("interview_not_found", "Interview not found.", status_code=404)
    application = legacy.dashboard_application_or_404(_text(interview.get("app_key")), company)
    next_status = life.normalize_interview_status(status, default=str(interview.get("status") or "completed")) or "completed"
    if next_status == "scheduled":
        next_status = "completed"
    summary = (
        legacy.generate_interview_ai_summary(notes, transcript, application, interview)
        if generate_summary
        else legacy.deterministic_interview_summary(notes, transcript)
    )
    with legacy.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT *
                FROM candidate_interviews
                WHERE interview_id=%s AND company_code=%s
                FOR UPDATE
                """,
                (interview_id, company),
            )
            locked = cur.fetchone()
            if not locked:
                raise life.InterviewAuthorityError("interview_not_found", "Interview not found.", status_code=404)
            locked_row = dict(locked)
            try:
                _cs.assert_fresh(
                    current_version=locked_row.get("notes_version"),
                    expected_version=expected_version,
                    current_updated_at=locked_row.get("updated_at"),
                    expected_updated_at=expected_updated_at,
                    last_changed_by={
                        "user_id": locked_row.get("updated_by_user_id"),
                        "phone": locked_row.get("updated_by_phone"),
                        "name": locked_row.get("updated_by_name"),
                    },
                    entity_type="interview_notes",
                    entity_id=str(interview_id),
                    code_version="stale_interview_notes",
                    code_updated_at="stale_interview_notes",
                    require_token=True,
                )
            except _cs.ConcurrencyError as exc:
                detail = exc.as_detail()
                raise life.InterviewAuthorityError(
                    exc.code,
                    exc.message,
                    status_code=exc.http_status,
                    **{k: v for k, v in detail.items() if k not in {"error", "message"}},
                ) from exc
            life.ensure_interview_notes_concurrency_schema(cur)
            cur.execute(
                """
                UPDATE candidate_interviews
                SET status=%s,
                    notes=%s,
                    transcript=NULLIF(%s, ''),
                    ai_summary=%s,
                    updated_by_phone=%s,
                    updated_by_user_id=COALESCE(%s, updated_by_user_id),
                    notes_version = COALESCE(notes_version, 0) + 1,
                    updated_at=now()
                WHERE interview_id=%s AND company_code=%s
                RETURNING *
                """,
                (
                    next_status,
                    notes or transcript,
                    transcript,
                    _json(summary),
                    actor.get("actor_phone"),
                    actor.get("actor_user_id"),
                    interview_id,
                    company,
                ),
            )
            row = dict(cur.fetchone() or {})
            assignments = life.list_assignments(cur, interview_id)
            prev_status = life.normalize_interview_status(locked_row.get("status"))
            if next_status == "completed" and prev_status != "completed":
                import calendar_interview_link as _cil

                if _cil.is_live_timed_interview(row):
                    _require_calendar_outbox_intent(
                        cur,
                        legacy,
                        interview=row,
                        assignments=assignments,
                        operation="complete",
                        operation_token=f"notes-complete:{interview_id}:{int(row.get('notes_version') or 0)}",
                    )
        conn.commit()
    record_event(legacy, row, "notes_saved", {"status": next_status, "summary_advisory": True}, actor=actor, action="save_interview_notes")
    legacy.update_application_interview_snapshot(_text(row.get("app_key")), row)
    return {"ok": True, "interview": enrich_interview_row(row, assignments=assignments), "ranking_updated": False, "human_feedback_complete": False}


def agenda_payload(
    company_code: str,
    *,
    week_start: str | None = None,
    limit: int = 200,
) -> dict[str, Any]:
    legacy = _legacy()
    company = _company(company_code)
    tz_name = life.company_timezone_name(legacy, company)
    from zoneinfo import ZoneInfo

    tzinfo = ZoneInfo(tz_name)
    if week_start:
        start_local = datetime.fromisoformat(week_start).date()
    else:
        today = datetime.now(tzinfo).date()
        start_local = today - timedelta(days=today.weekday())
    end_local = start_local + timedelta(days=7)
    start_utc = datetime.combine(start_local, datetime.min.time(), tzinfo=tzinfo).astimezone(timezone.utc)
    end_utc = datetime.combine(end_local, datetime.min.time(), tzinfo=tzinfo).astimezone(timezone.utc)
    with legacy.db_connect() as conn:
        with conn.cursor() as cur:
            life.ensure_interview_schema(cur)
            cur.execute(
                """
                SELECT ci.*
                FROM candidate_interviews ci
                WHERE ci.company_code=%s
                  AND ci.scheduled_start >= %s
                  AND ci.scheduled_start < %s
                  AND lower(COALESCE(ci.interview_type,'live')) <> 'async_video'
                ORDER BY ci.scheduled_start ASC
                LIMIT %s
                """,
                (company, start_utc, end_utc, max(1, min(int(limit), 500))),
            )
            rows = [dict(r) for r in cur.fetchall() or []]
            items = []
            calendar_enabled = False
            checker = getattr(legacy, "company_has_module", None)
            if callable(checker):
                try:
                    calendar_enabled = bool(checker(company, "calendar"))
                except Exception:
                    calendar_enabled = False
            native_by_interview: dict[str, dict[str, Any]] = {}
            if calendar_enabled and rows:
                ids = [str(r["interview_id"]) for r in rows]
                cur.execute(
                    """
                    SELECT l.source_record_id AS interview_id, e.event_id, e.start_at, e.end_at,
                           e.timezone, e.status, e.meeting_url, e.location, e.version,
                           e.metadata
                    FROM calendar_event_links l
                    JOIN calendar_events e ON e.event_id = l.event_id AND e.company_code = l.company_code
                    WHERE l.company_code=%s
                      AND l.source_workflow='interview'
                      AND l.link_status='active'
                      AND l.source_record_id = ANY(%s)
                    """,
                    (company, ids),
                )
                for link_row in cur.fetchall() or []:
                    lr = dict(link_row)
                    native_by_interview[str(lr.get("interview_id"))] = lr
            for row in rows:
                assignments = life.list_assignments(cur, str(row["interview_id"]))
                item = enrich_interview_row(row, assignments=assignments) or {}
                native = native_by_interview.get(str(row["interview_id"]))
                if calendar_enabled and native:
                    # Prefer native Wathefni Calendar times; keep legacy Google id as secondary.
                    item["calendar_native"] = {
                        "event_id": str(native.get("event_id")),
                        "start_at": native.get("start_at"),
                        "end_at": native.get("end_at"),
                        "timezone": native.get("timezone"),
                        "status": native.get("status"),
                        "meeting_url": native.get("meeting_url"),
                        "location": native.get("location"),
                        "version": native.get("version"),
                        "authority": "wathefni_calendar",
                    }
                    # Avoid duplicate display: expose a single schedule authority when native exists.
                    item["schedule_authority"] = "wathefni_calendar"
                    if native.get("start_at"):
                        item["scheduled_start"] = native.get("start_at")
                    if native.get("end_at"):
                        item["scheduled_end"] = native.get("end_at")
                    if native.get("meeting_url") and not item.get("meet_link"):
                        item["meet_link"] = native.get("meeting_url")
                    # Keep calendar_event_id as legacy Google binding only (do not overwrite with native uuid).
                    item["legacy_google_calendar_event_id"] = item.get("calendar_event_id")
                else:
                    item["schedule_authority"] = "interview_record"
                items.append(item)
    by_day: dict[str, list[dict[str, Any]]] = {}
    for item in items:
        start = life.parse_aware_datetime(item.get("scheduled_start"), default_tz=tzinfo)
        day = life.local_date_key(start, tzinfo) or "unknown"
        by_day.setdefault(day, []).append(item)
    return {
        "company_code": company,
        "timezone": tz_name,
        "week_start": start_local.isoformat(),
        "week_end": (end_local - timedelta(days=1)).isoformat(),
        "calendar_module_enabled": bool(
            getattr(legacy, "company_has_module", lambda *_: False)(company, "calendar")
            if callable(getattr(legacy, "company_has_module", None))
            else False
        ),
        "days": [{"date": day, "interviews": by_day.get(day, [])} for day in [(start_local + timedelta(days=i)).isoformat() for i in range(7)]],
        "interviews": items,
    }


def reclaim_stale_transcriptions(*, older_than_seconds: int | None = None) -> dict[str, Any]:
    legacy = _legacy()
    with legacy.db_connect() as conn:
        with conn.cursor() as cur:
            ids = life.reclaim_stale_transcript_processing(
                cur, older_than_seconds=older_than_seconds or life.TRANSCRIPT_PROCESSING_LEASE_SECONDS
            )
        conn.commit()
    return {"ok": True, "reclaimed_response_ids": ids, "count": len(ids)}


def purge_expired_video_files(
    *,
    company_code: str | None = None,
    actor: dict[str, Any] | None = None,
    limit: int = 50,
) -> dict[str, Any]:
    legacy = _legacy()
    actor = _actor(actor)
    company = _company(company_code) if company_code else None
    purged: list[dict[str, Any]] = []
    with legacy.db_connect() as conn:
        with conn.cursor() as cur:
            life.ensure_interview_schema(cur)
            params: list[Any] = []
            company_sql = ""
            if company:
                company_sql = "AND ci.company_code=%s"
                params.append(company)
            cur.execute(
                f"""
                SELECT r.*, ci.retention_expires_at, ci.retention_purged_at
                FROM candidate_video_interview_responses r
                JOIN candidate_interviews ci ON ci.interview_id=r.interview_id
                WHERE ci.interview_type='async_video'
                  AND ci.retention_expires_at IS NOT NULL
                  AND ci.retention_expires_at < now()
                  AND ci.retention_purged_at IS NULL
                  AND (r.local_path IS NOT NULL OR r.video_file_id IS NOT NULL)
                  {company_sql}
                ORDER BY ci.retention_expires_at ASC
                LIMIT %s
                """,
                params + [max(1, min(int(limit), 200))],
            )
            rows = [dict(r) for r in cur.fetchall() or []]
            for row in rows:
                local_path = _text(row.get("local_path"))
                error = None
                status = "purged"
                if local_path:
                    try:
                        path = Path(local_path)
                        if path.exists() and path.is_file():
                            path.unlink()
                    except Exception as exc:
                        error = str(exc)[:500]
                        status = "failed"
                cur.execute(
                    """
                    INSERT INTO interview_video_retention_operations (
                      company_code, interview_id, response_id, file_id, local_path, status, reason, error,
                      actor_user_id, actor_role, purged_at
                    )
                    VALUES (%s,%s,%s,%s,%s,%s,'retention_policy',%s,%s,%s,CASE WHEN %s='purged' THEN now() ELSE NULL END)
                    RETURNING *
                    """,
                    (
                        row.get("company_code"),
                        row.get("interview_id"),
                        row.get("response_id"),
                        row.get("video_file_id"),
                        local_path or None,
                        status,
                        error,
                        actor.get("actor_user_id"),
                        actor.get("actor_role"),
                        status,
                    ),
                )
                op = dict(cur.fetchone() or {})
                if status == "purged":
                    cur.execute(
                        """
                        UPDATE candidate_video_interview_responses
                        SET local_path=NULL,
                            storage_url=NULL,
                            storage_object_key=NULL,
                            video_file_id=NULL,
                            updated_at=now()
                        WHERE response_id=%s
                        """,
                        (str(row["response_id"]),),
                    )
                    if row.get("video_file_id"):
                        try:
                            cur.execute("DELETE FROM file_registry WHERE file_id=%s", (str(row["video_file_id"]),))
                        except Exception:
                            cur.execute(
                                """
                                UPDATE file_registry
                                SET deleted_at=now(), metadata=COALESCE(metadata,'{}'::jsonb) || '{"purged":true}'::jsonb
                                WHERE file_id=%s
                                """,
                                (str(row["video_file_id"]),),
                            )
                    cur.execute(
                        """
                        UPDATE candidate_interviews
                        SET retention_purged_at=now(), updated_at=now()
                        WHERE interview_id=%s
                          AND NOT EXISTS (
                            SELECT 1 FROM candidate_video_interview_responses r2
                            WHERE r2.interview_id=candidate_interviews.interview_id
                              AND (r2.local_path IS NOT NULL OR r2.video_file_id IS NOT NULL)
                          )
                        """,
                        (str(row["interview_id"]),),
                    )
                purged.append(legacy.json_safe(op))
        conn.commit()
    return {"ok": True, "operations": purged, "count": len(purged)}


def cleanup_retake_files(interview_id: str, *, keep_response_id: str | None = None, actor: dict[str, Any] | None = None) -> dict[str, Any]:
    legacy = _legacy()
    actor = _actor(actor)
    removed = []
    with legacy.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT * FROM candidate_video_interview_responses
                WHERE interview_id=%s
                ORDER BY submitted_at DESC NULLS LAST, updated_at DESC
                """,
                (interview_id,),
            )
            rows = [dict(r) for r in cur.fetchall() or []]
            keep = _text(keep_response_id)
            by_question: dict[str, list[dict[str, Any]]] = {}
            for row in rows:
                by_question.setdefault(str(row.get("question_id") or row.get("question_order") or ""), []).append(row)
            for _qid, items in by_question.items():
                for index, row in enumerate(items):
                    if keep and str(row.get("response_id")) == keep:
                        continue
                    if index == 0 and not keep:
                        continue
                    local_path = _text(row.get("local_path"))
                    if local_path:
                        try:
                            path = Path(local_path)
                            if path.exists():
                                path.unlink()
                        except Exception:
                            pass
                    cur.execute(
                        """
                        UPDATE candidate_video_interview_responses
                        SET local_path=NULL, video_file_id=NULL, storage_url=NULL, updated_at=now()
                        WHERE response_id=%s
                        """,
                        (str(row["response_id"]),),
                    )
                    removed.append(str(row["response_id"]))
                    cur.execute(
                        """
                        INSERT INTO interview_video_retention_operations (
                          company_code, interview_id, response_id, local_path, status, reason,
                          actor_user_id, actor_role, purged_at
                        ) VALUES (%s,%s,%s,%s,'purged','retake_cleanup',%s,%s,now())
                        """,
                        (row.get("company_code"), interview_id, row.get("response_id"), local_path or None, actor.get("actor_user_id"), actor.get("actor_role")),
                    )
        conn.commit()
    return {"ok": True, "removed_response_ids": removed, "count": len(removed)}
