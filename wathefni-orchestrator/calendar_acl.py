"""Wathefni Calendar ACL — detail levels full | limited | busy_only | hidden.

Depends only on OrgScopeAdapter + event bindings. Never queries manager_scopes.
"""

from __future__ import annotations

from typing import Any, Iterable, Mapping, Sequence

from calendar_org_scope import OrgScopeAdapter

DETAIL_FULL = "full"
DETAIL_LIMITED = "limited"
DETAIL_BUSY_ONLY = "busy_only"
DETAIL_HIDDEN = "hidden"

HIRING_SOURCE_WORKFLOWS = frozenset(
    {
        "interview",
        "assessment_deadline",
        "offer_deadline",
        "candidate_followup",
    }
)

COMPANY_OVERSIGHT_ROLES = frozenset({"owner", "hr_admin", "hr_manager"})
TEAM_BUSY_ROLES = frozenset({"interviewer", "viewer"})
TEAM_LIMITED_ROLES = frozenset({"recruiter", "hiring_manager", "manager"})


def _text(value: Any) -> str:
    return str(value or "").strip()


def actor_permissions(permissions: Iterable[Any] | None) -> set[str]:
    return {str(p).strip() for p in (permissions or []) if str(p).strip()}


def is_candidate_linked(event: Mapping[str, Any], links: Sequence[Mapping[str, Any]] | None = None) -> bool:
    sensitivity = _text(event.get("sensitivity")).lower()
    if sensitivity == "candidate_confidential":
        return True
    meta = event.get("metadata") if isinstance(event.get("metadata"), dict) else {}
    if meta.get("candidate_linked") is True:
        return True
    for link in links or []:
        if _text(link.get("link_status")).lower() not in {"", "active"}:
            continue
        if _text(link.get("source_workflow")).lower() in HIRING_SOURCE_WORKFLOWS:
            return True
    return False


def actor_is_principal(
    event: Mapping[str, Any],
    *,
    actor_user_id: str,
    attendee_user_ids: Iterable[str] | None = None,
) -> bool:
    actor = _text(actor_user_id)
    if not actor:
        return False
    if actor in {
        _text(event.get("owner_user_id")),
        _text(event.get("organizer_user_id")),
        _text(event.get("creator_user_id")) if _text(event.get("visibility")).lower() == "private" else "",
    }:
        return True
    attendees = {_text(uid) for uid in (attendee_user_ids or []) if _text(uid)}
    return actor in attendees


def event_scope_ids(bindings: Sequence[Mapping[str, Any]] | None) -> list[str]:
    return [_text(b.get("org_scope_id")) for b in (bindings or []) if _text(b.get("org_scope_id"))]


def evaluate_detail_level(
    *,
    event: Mapping[str, Any],
    actor_user_id: str,
    actor_role: str,
    permissions: Iterable[Any] | None,
    attendee_user_ids: Iterable[str] | None,
    org_bindings: Sequence[Mapping[str, Any]] | None,
    links: Sequence[Mapping[str, Any]] | None,
    adapter: OrgScopeAdapter,
    company_code: str,
    oversight_busy: bool = True,
) -> str:
    """Return ACL detail level for one event for one actor."""
    perms = actor_permissions(permissions)
    if "calendar.read" not in perms and "calendar.manage" not in perms and "calendar.company" not in perms:
        return DETAIL_HIDDEN

    if actor_is_principal(event, actor_user_id=actor_user_id, attendee_user_ids=attendee_user_ids):
        return DETAIL_FULL

    visibility = _text(event.get("visibility")).lower() or "attendees_only"
    role = _text(actor_role).lower()
    has_company = "calendar.company" in perms
    candidate = is_candidate_linked(event, links)
    scopes = event_scope_ids(org_bindings)
    in_scope = adapter.actor_in_any(company_code, actor_user_id, scopes) if scopes else False

    if visibility == "private":
        return DETAIL_HIDDEN

    if visibility == "attendees_only":
        if has_company and oversight_busy:
            return DETAIL_BUSY_ONLY
        return DETAIL_HIDDEN

    if visibility == "company":
        if has_company:
            return DETAIL_BUSY_ONLY if candidate else DETAIL_LIMITED
        return DETAIL_HIDDEN

    # team
    if visibility == "team":
        if not scopes:
            if "calendar.manage" in perms:
                return DETAIL_BUSY_ONLY if candidate else DETAIL_LIMITED
            return DETAIL_HIDDEN
        if not in_scope:
            if has_company and oversight_busy:
                return DETAIL_BUSY_ONLY
            return DETAIL_HIDDEN
        if candidate:
            if has_company or role in TEAM_LIMITED_ROLES or role in COMPANY_OVERSIGHT_ROLES:
                return DETAIL_BUSY_ONLY
            return DETAIL_HIDDEN
        if has_company or role in COMPANY_OVERSIGHT_ROLES or role in TEAM_LIMITED_ROLES:
            return DETAIL_LIMITED
        if role in TEAM_BUSY_ROLES:
            return DETAIL_BUSY_ONLY
        return DETAIL_HIDDEN

    return DETAIL_HIDDEN


def serialize_for_detail_level(event_payload: Mapping[str, Any], detail_level: str) -> dict[str, Any] | None:
    """Project an event payload to the locked detail level. hidden → None."""
    level = _text(detail_level).lower()
    if level == DETAIL_HIDDEN:
        return None
    base = dict(event_payload)
    base["detail_level"] = level
    if level == DETAIL_FULL:
        return base
    if level == DETAIL_LIMITED:
        limited = {
            "event_id": base.get("event_id"),
            "company_code": base.get("company_code"),
            "event_type": base.get("event_type"),
            "title": base.get("title"),
            "title_ar": base.get("title_ar"),
            "status": base.get("status"),
            "start_at": base.get("start_at"),
            "end_at": base.get("end_at"),
            "timezone": base.get("timezone"),
            "all_day": base.get("all_day"),
            "location": base.get("location"),
            "visibility": base.get("visibility"),
            "busy": True,
            "version": base.get("version"),
            "detail_level": DETAIL_LIMITED,
        }
        return limited
    # busy_only — no titles, attendees, guests, source, or candidate identity
    return {
        "event_id": base.get("event_id"),
        "company_code": base.get("company_code"),
        "start_at": base.get("start_at"),
        "end_at": base.get("end_at"),
        "timezone": base.get("timezone"),
        "all_day": base.get("all_day"),
        "busy": True,
        "title": "Busy",
        "title_ar": "مشغول",
        "status": base.get("status"),
        "version": base.get("version"),
        "detail_level": DETAIL_BUSY_ONLY,
    }
