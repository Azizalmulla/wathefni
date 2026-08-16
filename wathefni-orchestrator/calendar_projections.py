"""Wathefni Calendar projections — My / Team / Company + Overview ≤5.

Uses OrgScopeAdapter only — never imports or queries manager scope tables directly.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Iterable, Mapping, Sequence

import calendar_acl as acl
from calendar_org_scope import OrgScopeAdapter, get_org_scope_adapter
import calendar_store as store

OVERVIEW_MAX_ITEMS = 5
MAX_RANGE_DAYS = 92  # align with calendar_store.list_events_in_range


def _text(value: Any) -> str:
    return str(value or "").strip()


def _attendee_ids(attendees: Sequence[Mapping[str, Any]]) -> list[str]:
    return [_text(a.get("user_id")) for a in attendees if _text(a.get("user_id"))]


def _parse_bound(value: Any, *, field: str) -> datetime:
    return store._parse_dt(value, field=field)


def assert_bounded_range(start: Any, end: Any) -> tuple[datetime, datetime]:
    start_dt = _parse_bound(start, field="start")
    end_dt = _parse_bound(end, field="end")
    if end_dt < start_dt:
        raise store.CalendarError("invalid_time_range", message="end must be >= start")
    if (end_dt - start_dt) > timedelta(days=MAX_RANGE_DAYS):
        raise store.CalendarError(
            "range_too_large",
            message=f"Date range must be ≤ {MAX_RANGE_DAYS} days.",
            http_status=422,
        )
    return start_dt, end_dt


def include_in_my_calendar(
    *,
    event: Mapping[str, Any],
    actor_user_id: str,
    attendee_user_ids: Iterable[str],
) -> bool:
    actor = _text(actor_user_id)
    if not actor:
        return False
    if actor in {_text(event.get("owner_user_id")), _text(event.get("organizer_user_id"))}:
        return True
    if actor in {_text(uid) for uid in attendee_user_ids}:
        return True
    if actor == _text(event.get("creator_user_id")) and _text(event.get("visibility")).lower() == "private":
        return True
    if _text(event.get("event_type")).lower() == "personal_block" and actor == _text(event.get("owner_user_id")):
        return True
    return False


def include_in_team_calendar(
    *,
    event: Mapping[str, Any],
    actor_user_id: str,
    attendee_user_ids: Iterable[str],
    org_bindings: Sequence[Mapping[str, Any]],
    actor_scope_ids: set[str],
    permissions: Iterable[Any],
    detail_level: str,
) -> bool:
    """C0 §2.3 Team inclusion."""
    if detail_level == acl.DETAIL_HIDDEN:
        return False
    if include_in_my_calendar(event=event, actor_user_id=actor_user_id, attendee_user_ids=attendee_user_ids):
        return True  # T1
    visibility = _text(event.get("visibility")).lower()
    event_scopes = {_text(b.get("org_scope_id")) for b in org_bindings if _text(b.get("org_scope_id"))}
    if visibility in {"team", "company"} and event_scopes and (event_scopes & actor_scope_ids):
        return True  # T2
    perms = acl.actor_permissions(permissions)
    if visibility == "team" and not event_scopes and "calendar.manage" in perms:
        return True  # T3 rare
    return False


def include_in_company_calendar(
    *,
    event: Mapping[str, Any],
    permissions: Iterable[Any],
    detail_level: str,
) -> bool:
    perms = acl.actor_permissions(permissions)
    if "calendar.company" not in perms:
        return False
    if detail_level == acl.DETAIL_HIDDEN:
        return False
    visibility = _text(event.get("visibility")).lower()
    if visibility == "private":
        return False
    return True


def team_scope_meta(
    legacy: Any,
    *,
    company_code: str,
    actor_user_id: str,
    permissions: Iterable[Any],
    adapter: OrgScopeAdapter | None = None,
) -> dict[str, Any]:
    adapter = adapter or get_org_scope_adapter(legacy)
    memberships = adapter.list_memberships(company_code, actor_user_id)
    perms = acl.actor_permissions(permissions)
    has_company = "calendar.company" in perms
    scopes = [
        {
            "org_scope_id": m.org_scope_id,
            "org_scope_kind": m.org_scope_kind,
            "label": m.label,
        }
        for m in memberships
    ]
    show_team = bool(scopes)  # hiring-team switch only when actor has org scope memberships
    return {
        "show_team_switch": show_team,
        "has_team_scope": bool(scopes),
        "has_company_oversight": has_company,
        "no_team_guidance": (not scopes) and has_company,
        "scopes": scopes,
        "primary_org_scope_id": scopes[0]["org_scope_id"] if scopes else None,
    }


def _filter_event(
    *,
    scope_key: str,
    event: Mapping[str, Any],
    actor_user_id: str,
    attendee_ids: list[str],
    org_scopes: Sequence[Mapping[str, Any]],
    permissions: Iterable[Any],
    detail: str,
    actor_scope_ids: set[str],
    event_types: set[str] | None,
    statuses: set[str] | None,
    mine_only: bool,
) -> bool:
    if event_types and _text(event.get("event_type")).lower() not in event_types:
        return False
    if statuses and _text(event.get("status")).lower() not in statuses:
        return False
    if mine_only and not include_in_my_calendar(
        event=event, actor_user_id=actor_user_id, attendee_user_ids=attendee_ids
    ):
        return False

    if scope_key == "mine":
        return include_in_my_calendar(event=event, actor_user_id=actor_user_id, attendee_user_ids=attendee_ids)
    if scope_key == "team":
        return include_in_team_calendar(
            event=event,
            actor_user_id=actor_user_id,
            attendee_user_ids=attendee_ids,
            org_bindings=org_scopes,
            actor_scope_ids=actor_scope_ids,
            permissions=permissions,
            detail_level=detail,
        )
    # company
    if include_in_company_calendar(event=event, permissions=permissions, detail_level=detail):
        return True
    return include_in_my_calendar(event=event, actor_user_id=actor_user_id, attendee_user_ids=attendee_ids)


def project_events(
    legacy: Any,
    *,
    company_code: str,
    actor_user_id: str,
    actor_role: str,
    permissions: Iterable[Any],
    scope: str,
    start: Any,
    end: Any,
    adapter: OrgScopeAdapter | None = None,
    oversight_busy: bool = True,
    org_scope_id: str | None = None,
    event_types: Sequence[str] | None = None,
    statuses: Sequence[str] | None = None,
    mine_only: bool = False,
    limit: int | None = None,
) -> dict[str, Any]:
    scope_key = _text(scope).lower() or "mine"
    if scope_key not in {"mine", "team", "company"}:
        raise store.CalendarError("invalid_scope", message="scope must be mine, team, or company")
    if scope_key == "company" and "calendar.company" not in acl.actor_permissions(permissions):
        raise store.CalendarError("permission_denied", message="Missing calendar.company", http_status=403)

    start_dt, end_dt = assert_bounded_range(start, end)
    adapter = adapter or get_org_scope_adapter(legacy)
    memberships = adapter.list_memberships(company_code, actor_user_id)
    actor_scope_ids = {m.org_scope_id for m in memberships}
    selected_scope = _text(org_scope_id)
    if selected_scope:
        if selected_scope not in actor_scope_ids and "calendar.company" not in acl.actor_permissions(permissions):
            raise store.CalendarError("permission_denied", message="Not a member of this org scope", http_status=403)
        actor_scope_ids = {selected_scope} if scope_key == "team" else actor_scope_ids

    if scope_key == "team" and not actor_scope_ids and "calendar.company" not in acl.actor_permissions(permissions):
        raise store.CalendarError(
            "no_team_scope",
            message="No team scope available for this actor.",
            http_status=403,
        )

    type_set = {_text(t).lower() for t in (event_types or []) if _text(t)} or None
    status_set = {_text(s).lower() for s in (statuses or []) if _text(s)} or None

    bundles = store.list_events_in_range(legacy, company_code=company_code, start_at=start_dt, end_at=end_dt)
    projected: list[dict[str, Any]] = []

    for bundle in bundles:
        event = bundle["row"]
        attendees = bundle["attendees"]
        links = bundle["links"]
        org_scopes = bundle["org_scopes"]
        attendee_ids = _attendee_ids(attendees)
        detail = acl.evaluate_detail_level(
            event=event,
            actor_user_id=actor_user_id,
            actor_role=actor_role,
            permissions=permissions,
            attendee_user_ids=attendee_ids,
            org_bindings=org_scopes,
            links=links,
            adapter=adapter,
            company_code=company_code,
            oversight_busy=oversight_busy,
        )
        if detail == acl.DETAIL_HIDDEN:
            continue
        if not _filter_event(
            scope_key=scope_key,
            event=event,
            actor_user_id=actor_user_id,
            attendee_ids=attendee_ids,
            org_scopes=org_scopes,
            permissions=permissions,
            detail=detail,
            actor_scope_ids=actor_scope_ids,
            event_types=type_set,
            statuses=status_set,
            mine_only=mine_only,
        ):
            continue
        serialized = acl.serialize_for_detail_level(bundle["payload"], detail)
        if serialized is not None:
            projected.append(serialized)
            if limit is not None and len(projected) >= int(limit):
                break

    team_meta = team_scope_meta(
        legacy,
        company_code=company_code,
        actor_user_id=actor_user_id,
        permissions=permissions,
        adapter=adapter,
    )
    return {
        "scope": scope_key,
        "org_scope_id": selected_scope or None,
        "start": store._iso(start_dt),
        "end": store._iso(end_dt),
        "events": projected,
        "count": len(projected),
        "team": team_meta,
    }


def project_overview(
    legacy: Any,
    *,
    company_code: str,
    actor_user_id: str,
    actor_role: str,
    permissions: Iterable[Any],
    scope: str = "mine",
    now: datetime | None = None,
    adapter: OrgScopeAdapter | None = None,
) -> dict[str, Any]:
    """Constant-size Overview panel: mini month markers + ≤5 upcoming."""
    scope_key = _text(scope).lower() or "mine"
    if scope_key not in {"mine", "company"}:
        scope_key = "mine"
    if scope_key == "company" and "calendar.company" not in acl.actor_permissions(permissions):
        scope_key = "mine"

    now_dt = now or datetime.now(timezone.utc)
    # Mini month: current calendar month window in UTC bounds (± a few days handled client-side)
    month_start = datetime(now_dt.year, now_dt.month, 1, tzinfo=timezone.utc)
    if now_dt.month == 12:
        month_end = datetime(now_dt.year + 1, 1, 1, tzinfo=timezone.utc)
    else:
        month_end = datetime(now_dt.year, now_dt.month + 1, 1, tzinfo=timezone.utc)

    upcoming_end = now_dt + timedelta(days=21)
    result = project_events(
        legacy,
        company_code=company_code,
        actor_user_id=actor_user_id,
        actor_role=actor_role,
        permissions=permissions,
        scope=scope_key,
        start=now_dt - timedelta(hours=1),
        end=upcoming_end,
        adapter=adapter,
        statuses=["tentative", "confirmed"],
        limit=OVERVIEW_MAX_ITEMS,
    )
    # Month dots (busy days) — bounded month query, titles not needed
    month = project_events(
        legacy,
        company_code=company_code,
        actor_user_id=actor_user_id,
        actor_role=actor_role,
        permissions=permissions,
        scope=scope_key,
        start=month_start,
        end=month_end,
        adapter=adapter,
        statuses=["tentative", "confirmed"],
    )
    busy_days: set[str] = set()
    for ev in month.get("events") or []:
        start = ev.get("start_at")
        if start:
            busy_days.add(str(start)[:10])

    upcoming = (result.get("events") or [])[:OVERVIEW_MAX_ITEMS]
    today_iso = now_dt.date().isoformat()
    today_items = [e for e in upcoming if str(e.get("start_at") or "")[:10] == today_iso]

    return {
        "scope": scope_key,
        "today": today_iso,
        "month": {
            "year": now_dt.year,
            "month": now_dt.month,
            "busy_days": sorted(busy_days),
        },
        "today_count": len(today_items),
        "upcoming": upcoming,
        "upcoming_count": len(upcoming),
        "max_items": OVERVIEW_MAX_ITEMS,
        "can_add_event": "calendar.manage" in acl.actor_permissions(permissions),
    }


def project_event_detail(
    legacy: Any,
    *,
    company_code: str,
    event_id: str,
    actor_user_id: str,
    actor_role: str,
    permissions: Iterable[Any],
    adapter: OrgScopeAdapter | None = None,
    oversight_busy: bool = True,
) -> dict[str, Any]:
    adapter = adapter or get_org_scope_adapter(legacy)
    bundle = store.get_event(legacy, company_code=company_code, event_id=event_id)
    if not bundle:
        raise store.CalendarError("event_not_found", http_status=404)
    event = bundle["row"]
    if _text(event.get("company_code")).upper() != _text(company_code).upper():
        raise store.CalendarError("event_not_found", http_status=404)

    attendee_ids = _attendee_ids(bundle["attendees"])
    detail = acl.evaluate_detail_level(
        event=event,
        actor_user_id=actor_user_id,
        actor_role=actor_role,
        permissions=permissions,
        attendee_user_ids=attendee_ids,
        org_bindings=bundle["org_scopes"],
        links=bundle["links"],
        adapter=adapter,
        company_code=company_code,
        oversight_busy=oversight_busy,
    )
    if detail == acl.DETAIL_HIDDEN:
        raise store.CalendarError("event_not_found", http_status=404)
    serialized = acl.serialize_for_detail_level(bundle["payload"], detail)
    if serialized is None:
        raise store.CalendarError("event_not_found", http_status=404)

    interview_link = store.active_interview_link(bundle["links"])
    if interview_link and detail == acl.DETAIL_FULL:
        serialized["interview_managed"] = True
        serialized["interview_id"] = interview_link.get("source_record_id")
        serialized["authority"] = "interview"
    return serialized
