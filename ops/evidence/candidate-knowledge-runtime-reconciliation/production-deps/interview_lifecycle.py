"""Pre-Hiring Interviews lifecycle and scheduling authority.

Wathefni owns the interview record. Google Calendar/Meet is optional sync.
Interview status remains orthogonal to application lifecycle. Completion,
no-show, and feedback never hire, reject, rank, or issue offers.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


class InterviewAuthorityError(Exception):
    def __init__(self, error: str, message: str, *, status_code: int = 422, **extra: Any):
        super().__init__(message)
        self.error = error
        self.message = message
        self.status_code = status_code
        self.extra = extra

    def as_detail(self) -> dict[str, Any]:
        detail = {"error": self.error, "message": self.message}
        detail.update(self.extra)
        return detail


INTERVIEW_STATUSES = frozenset({"scheduled", "completed", "no_show", "rescheduled", "cancelled"})
ACTIVE_SCHEDULE_STATUSES = frozenset({"scheduled", "rescheduled"})
FEEDBACK_STATUSES = frozenset({"notes_pending", "feedback_complete"})
MEETING_TYPES = frozenset({"in_person", "phone", "manual_link", "google_meet", "async_video", "none"})
PROVIDER_SYNC_STATES = frozenset(
    {
        "not_configured",
        "pending",
        "synced",
        "update_pending",
        "cancellation_pending",
        "failed",
        "retrying",
    }
)
CHANNEL_SEND_STATES = frozenset(
    {
        "not_requested",
        "pending",
        "send_accepted",
        "delivered",
        "failed",
        "intentionally_skipped",
    }
)
RSVP_STATES = frozenset({"not_requested", "pending", "accepted", "declined", "tentative", "unknown"})
ASSIGNMENT_ROLES = frozenset({"organizer", "interviewer", "panel", "observer"})
FEEDBACK_SUBMISSION_STATES = frozenset({"draft", "submitted", "reopened"})
DEFAULT_DURATION_MINUTES = 30
DEFAULT_VIDEO_RETENTION_DAYS = 90
TRANSCRIPT_PROCESSING_LEASE_SECONDS = 15 * 60


def _text(value: Any) -> str:
    return str(value or "").strip()


def _upper(value: Any) -> str:
    return _text(value).upper()


def _json(value: Any) -> Any:
    try:
        from psycopg2.extras import Json

        return Json(value, dumps=lambda obj: json.dumps(obj, default=str))
    except Exception:
        return json.dumps(value, default=str)


def normalize_interview_status(value: Any, *, default: str | None = None) -> str | None:
    normalized = re.sub(r"[\s-]+", "_", _text(value).lower())
    aliases = {"noshow": "no_show", "canceled": "cancelled", "no_show": "no_show"}
    normalized = aliases.get(normalized, normalized)
    if normalized in INTERVIEW_STATUSES:
        return normalized
    return default


def normalize_feedback_status(value: Any, *, default: str = "notes_pending") -> str:
    normalized = re.sub(r"[\s-]+", "_", _text(value).lower())
    return normalized if normalized in FEEDBACK_STATUSES else default


def normalize_meeting_type(value: Any, *, default: str = "manual_link") -> str:
    normalized = re.sub(r"[\s-]+", "_", _text(value).lower())
    aliases = {
        "physical": "in_person",
        "inperson": "in_person",
        "office": "in_person",
        "call": "phone",
        "telephone": "phone",
        "link": "manual_link",
        "online": "manual_link",
        "zoom": "manual_link",
        "teams": "manual_link",
        "meet": "google_meet",
        "google": "google_meet",
        "async": "async_video",
        "video": "async_video",
    }
    normalized = aliases.get(normalized, normalized)
    return normalized if normalized in MEETING_TYPES else default


def normalize_provider_sync_state(value: Any, *, default: str = "not_configured") -> str:
    normalized = re.sub(r"[\s-]+", "_", _text(value).lower())
    return normalized if normalized in PROVIDER_SYNC_STATES else default


def normalize_channel_send_state(value: Any, *, default: str = "not_requested") -> str:
    normalized = re.sub(r"[\s-]+", "_", _text(value).lower())
    aliases = {
        "sent": "send_accepted",
        "queued": "pending",
        "accepted": "send_accepted",
        "skipped": "intentionally_skipped",
    }
    normalized = aliases.get(normalized, normalized)
    return normalized if normalized in CHANNEL_SEND_STATES else default


def normalize_rsvp_state(value: Any, *, default: str = "not_requested") -> str:
    normalized = re.sub(r"[\s-]+", "_", _text(value).lower())
    aliases = {"yes": "accepted", "no": "declined", "maybe": "tentative"}
    normalized = aliases.get(normalized, normalized)
    return normalized if normalized in RSVP_STATES else default


def company_timezone_name(legacy: Any, company_code: str) -> str:
    company = _upper(company_code)
    try:
        settings = legacy.get_company_settings(company) or {}
        name = _text(settings.get("timezone")) or "Asia/Kuwait"
    except Exception:
        name = "Asia/Kuwait"
    try:
        ZoneInfo(name)
        return name
    except ZoneInfoNotFoundError:
        return "Asia/Kuwait"


def company_tzinfo(legacy: Any, company_code: str):
    return ZoneInfo(company_timezone_name(legacy, company_code))


def parse_aware_datetime(value: Any, *, default_tz: Any) -> datetime | None:
    text = _text(value)
    if not text:
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except Exception:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=default_tz)
    return parsed


def local_date_key(dt: datetime | None, tzinfo: Any) -> str | None:
    if not dt:
        return None
    return dt.astimezone(tzinfo).date().isoformat()


def ranges_overlap(start_a: datetime, end_a: datetime, start_b: datetime, end_b: datetime) -> bool:
    return start_a < end_b and start_b < end_a


def google_calendar_configured(legacy: Any) -> bool:
    try:
        env = legacy.openclaw_env() if hasattr(legacy, "openclaw_env") else {}
        if _text(env.get("GOG_ACCOUNT")):
            return True
    except Exception:
        pass
    flag = _text(os.environ.get("WATHEFNI_GOOGLE_CALENDAR_ENABLED")).lower()
    if flag in {"0", "false", "off", "no"}:
        return False
    if flag in {"1", "true", "on", "yes"}:
        return True
    # Presence of gog auth is probed lazily by callers; default optional.
    return bool(_text(os.environ.get("GOG_ACCOUNT")))


def video_retention_days(legacy: Any | None = None, company_code: str | None = None) -> int:
    raw = os.environ.get("WATHEFNI_VIDEO_INTERVIEW_RETENTION_DAYS")
    if raw is None and legacy and company_code:
        try:
            settings = legacy.get_company_settings(company_code) or {}
            raw = settings.get("video_interview_retention_days")
        except Exception:
            raw = None
    try:
        days = int(raw if raw is not None else DEFAULT_VIDEO_RETENTION_DAYS)
    except Exception:
        days = DEFAULT_VIDEO_RETENTION_DAYS
    return max(1, min(days, 3650))


def ensure_interview_schema(cur: Any) -> None:
    """Idempotent schema for Wathefni-owned interview scheduling and feedback."""
    cur.execute(
        """
        ALTER TABLE IF EXISTS candidate_interviews
          ADD COLUMN IF NOT EXISTS location text,
          ADD COLUMN IF NOT EXISTS duration_minutes integer,
          ADD COLUMN IF NOT EXISTS provider_key text NOT NULL DEFAULT 'none',
          ADD COLUMN IF NOT EXISTS provider_sync_status text NOT NULL DEFAULT 'not_configured',
          ADD COLUMN IF NOT EXISTS provider_sync_error text,
          ADD COLUMN IF NOT EXISTS provider_synced_at timestamptz,
          ADD COLUMN IF NOT EXISTS channel_send_status text NOT NULL DEFAULT 'not_requested',
          ADD COLUMN IF NOT EXISTS rsvp_status text NOT NULL DEFAULT 'not_requested',
          ADD COLUMN IF NOT EXISTS human_feedback_status text NOT NULL DEFAULT 'notes_pending',
          ADD COLUMN IF NOT EXISTS retention_expires_at timestamptz,
          ADD COLUMN IF NOT EXISTS retention_purged_at timestamptz,
          ADD COLUMN IF NOT EXISTS schedule_operation_id uuid
        """
    )
    cur.execute(
        """
        UPDATE candidate_interviews
        SET human_feedback_status = COALESCE(NULLIF(human_feedback_status, ''), feedback_status, 'notes_pending')
        WHERE human_feedback_status IS NULL OR human_feedback_status = ''
        """
    )
    cur.execute(
        """
        UPDATE candidate_interviews
        SET duration_minutes = GREATEST(
              1,
              COALESCE(
                duration_minutes,
                CASE
                  WHEN scheduled_start IS NOT NULL AND scheduled_end IS NOT NULL
                    THEN GREATEST(1, ROUND(EXTRACT(EPOCH FROM (scheduled_end - scheduled_start)) / 60.0)::int)
                  ELSE %s
                END
              )
            )
        WHERE duration_minutes IS NULL OR duration_minutes < 1
        """,
        (DEFAULT_DURATION_MINUTES,),
    )
    cur.execute(
        """
        UPDATE candidate_interviews
        SET provider_key = CASE
              WHEN calendar_event_id IS NOT NULL OR meeting_type = 'google_meet' THEN 'google'
              ELSE COALESCE(NULLIF(provider_key, ''), 'none')
            END,
            provider_sync_status = CASE
              WHEN calendar_event_id IS NOT NULL AND COALESCE(provider_sync_status, 'not_configured') = 'not_configured'
                THEN 'synced'
              ELSE COALESCE(NULLIF(provider_sync_status, ''), 'not_configured')
            END,
            channel_send_status = CASE
              WHEN COALESCE(candidate_notified, false) THEN 'send_accepted'
              WHEN COALESCE(calendar_invite_sent, false) THEN 'send_accepted'
              ELSE COALESCE(NULLIF(channel_send_status, ''), 'not_requested')
            END
        WHERE TRUE
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS interview_schedule_operations (
          operation_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
          company_code text NOT NULL,
          app_key text NOT NULL,
          interview_id uuid,
          action text NOT NULL,
          idempotency_key text NOT NULL,
          requested_start timestamptz,
          requested_end timestamptz,
          timezone text NOT NULL DEFAULT 'Asia/Kuwait',
          meeting_type text NOT NULL DEFAULT 'manual_link',
          location text,
          meet_link text,
          duration_minutes integer NOT NULL DEFAULT 30,
          panel jsonb NOT NULL DEFAULT '[]'::jsonb,
          provider_key text NOT NULL DEFAULT 'none',
          provider_sync_status text NOT NULL DEFAULT 'not_configured',
          provider_event_id text,
          provider_error text,
          lifecycle_status text NOT NULL DEFAULT 'pending',
          request_payload jsonb NOT NULL DEFAULT '{}'::jsonb,
          result_payload jsonb NOT NULL DEFAULT '{}'::jsonb,
          actor_user_id text,
          actor_phone text,
          actor_role text,
          lease_owner text,
          lease_expires_at timestamptz,
          attempt_count integer NOT NULL DEFAULT 0,
          created_at timestamptz NOT NULL DEFAULT now(),
          updated_at timestamptz NOT NULL DEFAULT now(),
          UNIQUE (company_code, idempotency_key)
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS candidate_interview_assignments (
          assignment_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
          interview_id uuid NOT NULL REFERENCES candidate_interviews(interview_id) ON DELETE CASCADE,
          company_code text NOT NULL,
          app_key text NOT NULL,
          assignee_user_id text,
          assignee_email text,
          assignee_name text,
          assignee_phone text,
          panel_role text NOT NULL DEFAULT 'interviewer',
          is_organizer boolean NOT NULL DEFAULT false,
          is_required boolean NOT NULL DEFAULT true,
          rsvp_status text NOT NULL DEFAULT 'pending',
          provider_attendee_status text,
          metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
          created_at timestamptz NOT NULL DEFAULT now(),
          updated_at timestamptz NOT NULL DEFAULT now()
        )
        """
    )
    cur.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS idx_interview_assignments_unique_email
          ON candidate_interview_assignments (interview_id, lower(assignee_email))
          WHERE assignee_email IS NOT NULL AND assignee_email <> ''
        """
    )
    cur.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS idx_interview_assignments_unique_user
          ON candidate_interview_assignments (interview_id, assignee_user_id)
          WHERE assignee_user_id IS NOT NULL AND assignee_user_id <> ''
        """
    )
    cur.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_interview_assignments_company_assignee
          ON candidate_interview_assignments (company_code, assignee_user_id, assignee_email)
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS interview_feedback_definitions (
          definition_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
          company_code text NOT NULL,
          definition_key text NOT NULL,
          name text NOT NULL,
          description text,
          is_active boolean NOT NULL DEFAULT true,
          created_at timestamptz NOT NULL DEFAULT now(),
          updated_at timestamptz NOT NULL DEFAULT now(),
          UNIQUE (company_code, definition_key)
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS interview_feedback_definition_versions (
          version_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
          definition_id uuid NOT NULL REFERENCES interview_feedback_definitions(definition_id) ON DELETE CASCADE,
          company_code text NOT NULL,
          version integer NOT NULL,
          criteria jsonb NOT NULL DEFAULT '[]'::jsonb,
          rating_scale jsonb NOT NULL DEFAULT '{}'::jsonb,
          schema_digest text NOT NULL,
          status text NOT NULL DEFAULT 'published',
          created_by_user_id text,
          created_at timestamptz NOT NULL DEFAULT now(),
          UNIQUE (definition_id, version)
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS interview_feedback_submissions (
          submission_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
          interview_id uuid NOT NULL REFERENCES candidate_interviews(interview_id) ON DELETE CASCADE,
          company_code text NOT NULL,
          app_key text NOT NULL,
          definition_version_id uuid NOT NULL REFERENCES interview_feedback_definition_versions(version_id),
          rater_user_id text,
          rater_email text,
          rater_name text,
          status text NOT NULL DEFAULT 'draft',
          answers jsonb NOT NULL DEFAULT '{}'::jsonb,
          free_text_notes text,
          overall_rating numeric,
          submitted_at timestamptz,
          reopened_at timestamptz,
          reopen_reason text,
          revision integer NOT NULL DEFAULT 1,
          metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
          created_at timestamptz NOT NULL DEFAULT now(),
          updated_at timestamptz NOT NULL DEFAULT now()
        )
        """
    )
    cur.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS idx_interview_feedback_active_rater
          ON interview_feedback_submissions (interview_id, coalesce(rater_user_id, ''), coalesce(lower(rater_email), ''))
          WHERE status IN ('draft', 'submitted', 'reopened')
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS interview_feedback_submission_revisions (
          revision_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
          submission_id uuid NOT NULL REFERENCES interview_feedback_submissions(submission_id) ON DELETE CASCADE,
          company_code text NOT NULL,
          interview_id uuid NOT NULL,
          revision integer NOT NULL,
          status text NOT NULL,
          answers jsonb NOT NULL DEFAULT '{}'::jsonb,
          free_text_notes text,
          overall_rating numeric,
          actor_user_id text,
          actor_role text,
          reason text,
          created_at timestamptz NOT NULL DEFAULT now(),
          UNIQUE (submission_id, revision)
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS interview_video_retention_operations (
          operation_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
          company_code text NOT NULL,
          interview_id uuid NOT NULL,
          response_id uuid,
          file_id uuid,
          local_path text,
          status text NOT NULL DEFAULT 'pending',
          reason text,
          error text,
          actor_user_id text,
          actor_role text,
          purged_at timestamptz,
          created_at timestamptz NOT NULL DEFAULT now(),
          updated_at timestamptz NOT NULL DEFAULT now()
        )
        """
    )
    cur.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_interview_ops_company_app
          ON interview_schedule_operations (company_code, app_key, created_at DESC)
        """
    )
    cur.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS idx_candidate_interviews_one_active_live
          ON candidate_interviews (company_code, app_key)
          WHERE lower(COALESCE(status,'')) IN ('scheduled','rescheduled')
            AND lower(COALESCE(interview_type,'live')) <> 'async_video'
        """
    )
    # Soft constraints via NOT VALID where safe for existing dirty rows.
    for name, ddl in (
        (
            "candidate_interviews_status_chk",
            """
            ALTER TABLE candidate_interviews
              ADD CONSTRAINT candidate_interviews_status_chk
              CHECK (status IN ('scheduled','completed','no_show','rescheduled','cancelled')) NOT VALID
            """,
        ),
        (
            "candidate_interviews_feedback_chk",
            """
            ALTER TABLE candidate_interviews
              ADD CONSTRAINT candidate_interviews_feedback_chk
              CHECK (feedback_status IN ('notes_pending','feedback_complete')) NOT VALID
            """,
        ),
        (
            "candidate_interviews_human_feedback_chk",
            """
            ALTER TABLE candidate_interviews
              ADD CONSTRAINT candidate_interviews_human_feedback_chk
              CHECK (human_feedback_status IN ('notes_pending','feedback_complete')) NOT VALID
            """,
        ),
        (
            "candidate_interviews_time_order_chk",
            """
            ALTER TABLE candidate_interviews
              ADD CONSTRAINT candidate_interviews_time_order_chk
              CHECK (scheduled_start IS NULL OR scheduled_end IS NULL OR scheduled_end > scheduled_start) NOT VALID
            """,
        ),
    ):
        cur.execute(
            """
            SELECT 1 FROM pg_constraint
            WHERE conname=%s AND conrelid='candidate_interviews'::regclass
            """,
            (name,),
        )
        if not cur.fetchone():
            try:
                cur.execute(ddl)
            except Exception:
                pass
    # Seed a default feedback definition for GLOBAL/demo use when missing.
    cur.execute(
        """
        INSERT INTO interview_feedback_definitions (company_code, definition_key, name, description)
        VALUES ('GLOBAL', 'default_v1', 'Standard interview feedback', 'Minimal criteria scorecard for live interviews')
        ON CONFLICT (company_code, definition_key) DO NOTHING
        """
    )
    cur.execute(
        """
        SELECT definition_id FROM interview_feedback_definitions
        WHERE company_code='GLOBAL' AND definition_key='default_v1'
        LIMIT 1
        """
    )
    definition = cur.fetchone() or {}
    definition_id = definition.get("definition_id")
    if definition_id:
        criteria = [
            {"key": "role_fit", "label": "Role fit", "required": True},
            {"key": "communication", "label": "Communication", "required": True},
            {"key": "experience", "label": "Relevant experience", "required": True},
            {"key": "overall", "label": "Overall impression", "required": True},
        ]
        scale = {"min": 1, "max": 5, "labels": {"1": "Poor", "3": "Adequate", "5": "Excellent"}}
        digest = hashlib.sha256(json.dumps({"criteria": criteria, "scale": scale}, sort_keys=True).encode()).hexdigest()
        cur.execute(
            """
            INSERT INTO interview_feedback_definition_versions
              (definition_id, company_code, version, criteria, rating_scale, schema_digest, status)
            VALUES (%s,'GLOBAL',1,%s,%s,%s,'published')
            ON CONFLICT (definition_id, version) DO NOTHING
            """,
            (definition_id, _json(criteria), _json(scale), digest),
        )


def communication_truth(row: dict[str, Any]) -> dict[str, Any]:
    provider_sync = normalize_provider_sync_state(row.get("provider_sync_status"))
    channel = normalize_channel_send_state(row.get("channel_send_status"))
    if channel == "not_requested" and (row.get("candidate_notified") or row.get("calendar_invite_sent")):
        channel = "send_accepted"
    rsvp = normalize_rsvp_state(row.get("rsvp_status"))
    provider_accepted = provider_sync == "synced" or bool(row.get("calendar_event_id"))
    return {
        "provider_accepted": bool(provider_accepted),
        "provider_sync_status": provider_sync,
        "channel_send_status": channel,
        "delivered": channel == "delivered",
        "failed": channel == "failed" or provider_sync == "failed",
        "rsvp_status": rsvp,
        "cancelled": normalize_interview_status(row.get("status")) == "cancelled",
        # Compatibility mirrors — never claim delivery from calendar alone.
        "communication_status": (
            "failed"
            if channel == "failed" or provider_sync == "failed"
            else "sent"
            if channel in {"send_accepted", "delivered"}
            else "intentionally_skipped"
            if normalize_interview_status(row.get("status")) == "cancelled"
            else "pending"
        ),
        "invitation_status": channel,
        "candidate_confirmation": (
            "confirmed"
            if rsvp == "accepted" or row.get("consent_accepted_at")
            else "declined"
            if rsvp == "declined"
            else "tentative"
            if rsvp == "tentative"
            else "not_confirmed"
            if channel in {"send_accepted", "delivered"} or provider_accepted
            else "not_requested"
        ),
    }


def human_feedback_complete(row: dict[str, Any]) -> bool:
    # Prefer explicit human scorecard authority when present.
    if row.get("human_feedback_status") not in (None, ""):
        return normalize_feedback_status(row.get("human_feedback_status")) == "feedback_complete"
    return normalize_feedback_status(row.get("feedback_status")) == "feedback_complete"


def derive_notes_status(row: dict[str, Any]) -> str:
    if human_feedback_complete(row) or _text(row.get("notes")):
        # Free-text notes alone are not scorecard completion.
        if human_feedback_complete(row):
            return "complete"
        return "notes_present"
    return "pending"


def next_human_action(row: dict[str, Any], truth: dict[str, Any] | None = None) -> str:
    truth = truth or communication_truth(row)
    status = normalize_interview_status(row.get("status"), default="scheduled") or "scheduled"
    if truth.get("failed"):
        return "resolve_invitation"
    if status in ACTIVE_SCHEDULE_STATUSES and truth.get("channel_send_status") == "not_requested" and not truth.get("provider_accepted"):
        return "send_invitation"
    if status == "completed" and not human_feedback_complete(row):
        return "record_feedback"
    if status == "completed":
        return "decide_application"
    if status in {"no_show", "cancelled"}:
        return "review_next_step"
    return "conduct_interview"


def default_feedback_version(cur: Any, company_code: str) -> dict[str, Any] | None:
    company = _upper(company_code)
    cur.execute(
        """
        SELECT v.*
        FROM interview_feedback_definition_versions v
        JOIN interview_feedback_definitions d ON d.definition_id=v.definition_id
        WHERE d.company_code IN (%s, 'GLOBAL')
          AND d.is_active IS TRUE
          AND v.status='published'
        ORDER BY CASE WHEN d.company_code=%s THEN 0 ELSE 1 END, v.version DESC
        LIMIT 1
        """,
        (company, company),
    )
    row = cur.fetchone()
    return dict(row) if row else None


def normalize_panel(items: list[Any] | None) -> list[dict[str, Any]]:
    panel: list[dict[str, Any]] = []
    seen: set[str] = set()
    for index, raw in enumerate(items or []):
        data = raw if isinstance(raw, dict) else {"email": raw}
        email = _text(data.get("email") or data.get("assignee_email")).lower()
        user_id = _text(data.get("user_id") or data.get("assignee_user_id") or data.get("actor_user_id"))
        key = email or user_id
        if not key or key in seen:
            continue
        seen.add(key)
        role = _text(data.get("panel_role") or data.get("role") or "interviewer").lower()
        if role not in ASSIGNMENT_ROLES:
            role = "interviewer"
        panel.append(
            {
                "assignee_user_id": user_id or None,
                "assignee_email": email or None,
                "assignee_name": _text(data.get("name") or data.get("assignee_name")) or None,
                "assignee_phone": _text(data.get("phone") or data.get("assignee_phone")) or None,
                "panel_role": role,
                "is_organizer": bool(data.get("is_organizer") or role == "organizer" or index == 0),
                "is_required": bool(data.get("is_required", True)),
            }
        )
    if panel and not any(item.get("is_organizer") for item in panel):
        panel[0]["is_organizer"] = True
        panel[0]["panel_role"] = "organizer"
    return panel


def find_schedule_conflicts(
    cur: Any,
    *,
    company_code: str,
    app_key: str,
    start: datetime,
    end: datetime,
    panel: list[dict[str, Any]] | None = None,
    exclude_interview_id: str | None = None,
) -> list[dict[str, Any]]:
    company = _upper(company_code)
    conflicts: list[dict[str, Any]] = []
    candidate_sql = """
        SELECT interview_id, app_key, scheduled_start, scheduled_end, status, candidate_name
        FROM candidate_interviews
        WHERE company_code=%s
          AND app_key=%s
          AND lower(COALESCE(status,'')) IN ('scheduled','rescheduled')
          AND lower(COALESCE(interview_type,'live')) <> 'async_video'
          AND scheduled_start IS NOT NULL
          AND scheduled_end IS NOT NULL
          AND scheduled_start < %s
          AND scheduled_end > %s
    """
    candidate_params: list[Any] = [company, app_key, end, start]
    if exclude_interview_id:
        candidate_sql += " AND interview_id <> %s"
        candidate_params.append(exclude_interview_id)
    cur.execute(candidate_sql, candidate_params)
    for row in cur.fetchall() or []:
        conflicts.append({"type": "candidate", "interview": dict(row)})

    emails = [str(item["assignee_email"]).lower() for item in (panel or []) if item.get("assignee_email")]
    user_ids = [str(item["assignee_user_id"]) for item in (panel or []) if item.get("assignee_user_id")]
    if emails or user_ids:
        panel_sql = """
            SELECT a.assignment_id, a.interview_id, a.assignee_email, a.assignee_user_id, a.panel_role,
                   i.scheduled_start, i.scheduled_end, i.app_key, i.candidate_name, i.status
            FROM candidate_interview_assignments a
            JOIN candidate_interviews i ON i.interview_id=a.interview_id
            WHERE a.company_code=%s
              AND lower(COALESCE(i.status,'')) IN ('scheduled','rescheduled')
              AND i.scheduled_start IS NOT NULL
              AND i.scheduled_end IS NOT NULL
              AND i.scheduled_start < %s
              AND i.scheduled_end > %s
              AND (
                (cardinality(%s::text[]) > 0 AND lower(COALESCE(a.assignee_email,'')) = ANY(%s))
                OR (cardinality(%s::text[]) > 0 AND COALESCE(a.assignee_user_id,'') = ANY(%s))
              )
        """
        panel_params: list[Any] = [company, end, start, emails, emails, user_ids, user_ids]
        if exclude_interview_id:
            panel_sql += " AND i.interview_id <> %s"
            panel_params.append(exclude_interview_id)
        cur.execute(panel_sql, panel_params)
        for row in cur.fetchall() or []:
            conflicts.append({"type": "panel", "assignment": dict(row)})
    return conflicts


def replace_assignments(cur: Any, interview: dict[str, Any], panel: list[dict[str, Any]]) -> list[dict[str, Any]]:
    interview_id = str(interview.get("interview_id") or "")
    company = _upper(interview.get("company_code"))
    app_key = _text(interview.get("app_key"))
    cur.execute("DELETE FROM candidate_interview_assignments WHERE interview_id=%s", (interview_id,))
    saved: list[dict[str, Any]] = []
    for item in panel:
        cur.execute(
            """
            INSERT INTO candidate_interview_assignments (
              interview_id, company_code, app_key, assignee_user_id, assignee_email, assignee_name,
              assignee_phone, panel_role, is_organizer, is_required, rsvp_status
            )
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'pending')
            RETURNING *
            """,
            (
                interview_id,
                company,
                app_key,
                item.get("assignee_user_id"),
                item.get("assignee_email"),
                item.get("assignee_name"),
                item.get("assignee_phone"),
                item.get("panel_role") or "interviewer",
                bool(item.get("is_organizer")),
                bool(item.get("is_required", True)),
            ),
        )
        saved.append(dict(cur.fetchone() or {}))
    return saved


def list_assignments(cur: Any, interview_id: str) -> list[dict[str, Any]]:
    cur.execute(
        """
        SELECT *
        FROM candidate_interview_assignments
        WHERE interview_id=%s
        ORDER BY is_organizer DESC, created_at ASC
        """,
        (interview_id,),
    )
    return [dict(row) for row in cur.fetchall() or []]


def claim_or_load_operation(
    cur: Any,
    *,
    company_code: str,
    app_key: str,
    action: str,
    idempotency_key: str,
    payload: dict[str, Any],
    actor: dict[str, Any] | None = None,
) -> tuple[dict[str, Any], bool]:
    company = _upper(company_code)
    key = _text(idempotency_key) or f"{action}:{company}:{app_key}:{uuid.uuid4().hex}"
    actor = actor or {}
    cur.execute(
        """
        SELECT * FROM interview_schedule_operations
        WHERE company_code=%s AND idempotency_key=%s
        LIMIT 1
        FOR UPDATE
        """,
        (company, key),
    )
    existing = cur.fetchone()
    if existing:
        return dict(existing), False
    cur.execute(
        """
        INSERT INTO interview_schedule_operations (
          company_code, app_key, action, idempotency_key, requested_start, requested_end, timezone,
          meeting_type, location, meet_link, duration_minutes, panel, provider_key, provider_sync_status,
          lifecycle_status, request_payload, actor_user_id, actor_phone, actor_role, attempt_count
        )
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'pending',%s,%s,%s,%s,1)
        RETURNING *
        """,
        (
            company,
            app_key,
            action,
            key,
            payload.get("scheduled_start"),
            payload.get("scheduled_end"),
            payload.get("timezone") or "Asia/Kuwait",
            payload.get("meeting_type") or "manual_link",
            payload.get("location"),
            payload.get("meet_link"),
            int(payload.get("duration_minutes") or DEFAULT_DURATION_MINUTES),
            _json(payload.get("panel") or []),
            payload.get("provider_key") or "none",
            payload.get("provider_sync_status") or "not_configured",
            _json(payload),
            actor.get("actor_user_id"),
            actor.get("actor_phone"),
            actor.get("actor_role"),
        ),
    )
    return dict(cur.fetchone() or {}), True


def mark_operation(cur: Any, operation_id: str, **fields: Any) -> dict[str, Any]:
    allowed = {
        "interview_id",
        "provider_key",
        "provider_sync_status",
        "provider_event_id",
        "provider_error",
        "lifecycle_status",
        "result_payload",
        "attempt_count",
        "lease_owner",
        "lease_expires_at",
        "meet_link",
        "location",
    }
    sets = ["updated_at=now()"]
    params: list[Any] = []
    for key, value in fields.items():
        if key not in allowed:
            continue
        if key in {"result_payload"} and not hasattr(value, "adapted"):
            value = _json(value)
        sets.append(f"{key}=%s")
        params.append(value)
    params.append(operation_id)
    cur.execute(
        f"UPDATE interview_schedule_operations SET {', '.join(sets)} WHERE operation_id=%s RETURNING *",
        params,
    )
    return dict(cur.fetchone() or {})


def reclaim_stale_transcript_processing(cur: Any, *, older_than_seconds: int = TRANSCRIPT_PROCESSING_LEASE_SECONDS) -> list[str]:
    cur.execute(
        """
        UPDATE candidate_video_interview_responses
        SET transcript_status='pending',
            transcript_error=COALESCE(transcript_error, 'stale_processing_reclaimed'),
            updated_at=now()
        WHERE COALESCE(transcript_status,'pending')='processing'
          AND updated_at < now() - make_interval(secs => %s)
        RETURNING response_id
        """,
        (max(60, int(older_than_seconds)),),
    )
    return [str(row.get("response_id")) for row in cur.fetchall() or []]


def schema_digest(criteria: list[dict[str, Any]], rating_scale: dict[str, Any]) -> str:
    return hashlib.sha256(json.dumps({"criteria": criteria, "scale": rating_scale}, sort_keys=True, default=str).encode()).hexdigest()
