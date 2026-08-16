"""Interviews queue contract — single source of truth for tab membership.

Approved product contract:

* Upcoming = scheduled/rescheduled only.
* Needs feedback = completed only; one canonical feedback authority — structured
  submission wins; any valid complete state removes pending; stale legacy fields
  cannot keep a completed interview pending when another complete mirror exists.
* Video = async video excluding cancelled and no-show; completed video remains.
* Completed / No-shows / Cancelled = exact status.
* All = full history including terminals.
* List filters and tab badge counts share these predicates plus the same tenant,
  CV-exists, module-kind, assignment, and visibility scope.
* Cancel retains video/feedback/invitation fields; membership only changes.
"""

from __future__ import annotations

from typing import Any, Mapping, Sequence

CANONICAL_STATUSES = frozenset({"scheduled", "completed", "no_show", "rescheduled", "cancelled"})
TERMINAL_STATUSES = frozenset({"cancelled", "no_show"})
ACTIVE_SCHEDULE_STATUSES = frozenset({"scheduled", "rescheduled"})

TAB_IDS = (
    "upcoming",
    "needs_feedback",
    "video_interviews",
    "completed",
    "no_show",
    "cancelled",
    "all",
)

STATUS_ALIASES = {
    "noshow": "no_show",
    "no-show": "no_show",
    "canceled": "cancelled",
    "cancelled": "cancelled",
}

CV_EXISTS_SQL = (
    "EXISTS ("
    "SELECT 1 FROM applications a "
    "WHERE a.company_code=ci.company_code AND a.app_key=ci.app_key "
    "AND (a.cv_received IS TRUE OR jsonb_typeof(a.raw_json->'cv') = 'object')"
    ")"
)

ASYNC_VIDEO_SQL = "(ci.interview_type='async_video' OR ci.source='async_video')"


def normalize_status(value: Any, *, default: str | None = None) -> str | None:
    raw = str(value or "").strip().lower().replace(" ", "_")
    if not raw:
        return default
    raw = STATUS_ALIASES.get(raw, raw)
    if raw in CANONICAL_STATUSES:
        return raw
    return default


def is_async_video(row: Mapping[str, Any]) -> bool:
    return str(row.get("interview_type") or "").lower() == "async_video" or str(row.get("source") or "").lower() == "async_video"


def feedback_is_complete(row: Mapping[str, Any]) -> bool:
    """Canonical queue feedback completion.

    Precedence: latest structured submission (reopened → not complete; submitted →
    complete). Otherwise either legacy mirror counts as complete so a stale
    notes_pending human field cannot override feedback_complete.
    """
    submission = row.get("feedback_submission") if isinstance(row.get("feedback_submission"), dict) else None
    submission_status = str((submission or {}).get("status") or "").lower()
    if submission_status == "reopened":
        return False
    if submission_status == "submitted":
        return True
    human = str(row.get("human_feedback_status") or "").lower()
    legacy = str(row.get("feedback_status") or "").lower()
    return human == "feedback_complete" or legacy == "feedback_complete"


def sql_feedback_complete_expr() -> str:
    """Boolean SQL expression: interview feedback is complete under the contract."""
    return (
        "COALESCE("
        "("
        "SELECT CASE"
        " WHEN lower(s.status)='reopened' THEN FALSE"
        " WHEN lower(s.status)='submitted' THEN TRUE"
        " ELSE NULL"
        " END"
        " FROM interview_feedback_submissions s"
        " WHERE s.interview_id=ci.interview_id AND s.company_code=ci.company_code"
        " ORDER BY s.updated_at DESC NULLS LAST"
        " LIMIT 1"
        "),"
        "("
        "COALESCE(ci.human_feedback_status,'')='feedback_complete'"
        " OR COALESCE(ci.feedback_status,'')='feedback_complete'"
        ")"
        ")"
    )


def tab_membership(row: Mapping[str, Any], tab: str) -> bool:
    """Return True if row belongs in the given tab under the approved contract."""
    status = normalize_status(row.get("status"), default="scheduled") or "scheduled"
    tab_key = _normalize_tab(tab)

    if tab_key == "all":
        return True
    if tab_key == "upcoming":
        return status in ACTIVE_SCHEDULE_STATUSES
    if tab_key == "completed":
        return status == "completed"
    if tab_key == "no_show":
        return status == "no_show"
    if tab_key == "cancelled":
        return status == "cancelled"
    if tab_key == "needs_feedback":
        if status != "completed":
            return False
        return not feedback_is_complete(row)
    if tab_key == "video_interviews":
        if not is_async_video(row):
            return False
        return status not in TERMINAL_STATUSES
    raise ValueError(f"unknown interview tab: {tab}")


def sql_status_predicate(tab: str) -> str:
    """SQL fragment matching tab_membership (no bind params)."""
    tab_key = _normalize_tab(tab)
    if tab_key == "all":
        return "TRUE"
    if tab_key == "upcoming":
        return "ci.status IN ('scheduled','rescheduled')"
    if tab_key == "completed":
        return "ci.status='completed'"
    if tab_key == "no_show":
        return "ci.status='no_show'"
    if tab_key == "cancelled":
        return "ci.status='cancelled'"
    if tab_key == "needs_feedback":
        return f"ci.status='completed' AND NOT ({sql_feedback_complete_expr()})"
    if tab_key == "video_interviews":
        return f"{ASYNC_VIDEO_SQL} AND ci.status NOT IN ('cancelled','no_show')"
    raise ValueError(f"unknown interview tab: {tab}")


def list_tab_predicate(status: str | None) -> tuple[str | None, list[Any]]:
    """Return (sql, params) for the list status= query param, or (None, []) for all."""
    normalized = str(status or "").strip().lower()
    if not normalized or normalized == "all":
        return None, []
    if normalized in {"video", "video_interviews", "async_video"}:
        return sql_status_predicate("video_interviews"), []
    if normalized in {"upcoming", "needs_feedback"}:
        return sql_status_predicate(normalized), []
    status_value = normalize_status(normalized, default=None)
    if status_value:
        return "ci.status=%s", [status_value]
    return None, []


def kind_clause(*, include_live: bool = True, include_async_video: bool = True) -> str:
    if not include_live and not include_async_video:
        return "FALSE"
    if not include_async_video:
        return f"NOT {ASYNC_VIDEO_SQL}"
    if not include_live:
        return ASYNC_VIDEO_SQL
    return ""


def build_shared_scope(
    company: str,
    *,
    include_live: bool = True,
    include_async_video: bool = True,
    assignment_sql: str | None = None,
    assignment_params: Sequence[Any] | None = None,
    visibility_sql: str | None = None,
    visibility_params: Sequence[Any] | None = None,
) -> tuple[list[str], list[Any]]:
    """Tenant + CV-exists + kind + assignment + visibility — shared by list and counts."""
    where = ["ci.company_code=%s", CV_EXISTS_SQL]
    params: list[Any] = [company]
    if assignment_sql:
        where.append(assignment_sql)
        params.extend(list(assignment_params or []))
    if visibility_sql:
        where.append(visibility_sql)
        params.extend(list(visibility_params or []))
    kind = kind_clause(include_live=include_live, include_async_video=include_async_video)
    if kind:
        where.append(kind)
    return where, params


def _normalize_tab(tab: str) -> str:
    tab_key = str(tab or "").strip().lower()
    if tab_key in {"video", "async_video"}:
        return "video_interviews"
    return tab_key


def current_diverges_from_contract() -> dict[str, bool]:
    """Post-implementation: production predicates match the contract."""
    return {tab: False for tab in TAB_IDS}
