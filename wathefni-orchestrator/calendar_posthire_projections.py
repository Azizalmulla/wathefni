"""Calendar Wave 2 — real post-hire read-only projections.

Calendar is a unified time view only. Owning modules keep mutation authority.
Each source is independently feature-flagged and company-allowlisted.

Event ids use prefix ``calproj-`` (never written to calendar_events).
"""

from __future__ import annotations

import os
from datetime import date, datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo

TZ = ZoneInfo("Asia/Kuwait")
PROJ_ID_PREFIX = "calproj-"

# Per-source flags (preview-style: off unless explicitly on + company allowlisted).
SOURCE_FLAGS: dict[str, dict[str, str]] = {
    "employee_start": {
        "flag": "WATHEFNI_CALENDAR_PROJECTION_EMPLOYEE_START",
        "companies": "WATHEFNI_CALENDAR_PROJECTION_EMPLOYEE_START_COMPANIES",
        "permission": "employees.read",
    },
    "onboarding_deadline": {
        "flag": "WATHEFNI_CALENDAR_PROJECTION_ONBOARDING",
        "companies": "WATHEFNI_CALENDAR_PROJECTION_ONBOARDING_COMPANIES",
        "permission": "onboarding.read",
    },
    "approved_leave": {
        "flag": "WATHEFNI_CALENDAR_PROJECTION_LEAVE",
        "companies": "WATHEFNI_CALENDAR_PROJECTION_LEAVE_COMPANIES",
        "permission": "leave.read",
    },
    "compliance_expiry": {
        "flag": "WATHEFNI_CALENDAR_PROJECTION_COMPLIANCE",
        "companies": "WATHEFNI_CALENDAR_PROJECTION_COMPLIANCE_COMPANIES",
        "permission": "compliance.read",
    },
    "company_events": {
        "flag": "WATHEFNI_CALENDAR_PROJECTION_COMPANY_EVENTS",
        "companies": "WATHEFNI_CALENDAR_PROJECTION_COMPANY_EVENTS_COMPANIES",
        "permission": "calendar.read",
    },
}

SOURCE_ORDER = (
    "employee_start",
    "onboarding_deadline",
    "approved_leave",
    "compliance_expiry",
    "company_events",
)

ONBOARDING_ASSIGNMENT_EXCLUDE = frozenset({"completed", "cancelled", "abandoned"})
ONBOARDING_ITEM_EXCLUDE = frozenset({
    "received",
    "complete",
    "completed",
    "verified",
    "waived",
    "cancelled_onboarding",
    "abandoned_employment_ended",
    "retired_legacy",
})
LEAVE_STATUS_USE = frozenset({"approved"})
EMPLOYMENT_STATUS_EXCLUDE = frozenset({"left"})
PERSON_STATUS_EXCLUDE = frozenset({"merged", "archived"})
HOLIDAY_REVIEW_EXCLUDE = frozenset({"draft", "pending_review", "rejected", "superseded"})


def _env_on(name: str) -> bool:
    return str(os.environ.get(name) or "").strip().lower() in {"1", "on", "true", "yes", "enabled"}


def source_enabled_for_company(source: str, company_code: str | None) -> bool:
    meta = SOURCE_FLAGS.get(source)
    if not meta:
        return False
    if not _env_on(meta["flag"]):
        return False
    company = str(company_code or "").strip().upper()
    if not company:
        return False
    raw = str(os.environ.get(meta["companies"]) or "WATHEFNI").strip()
    allowed = {part.strip().upper() for part in raw.split(",") if part.strip()}
    return company in allowed


def actor_has_permission(permissions: list[str] | None, permission: str) -> bool:
    perms = {str(p).strip() for p in (permissions or []) if str(p).strip()}
    return permission in perms or "* " in perms or "*" in perms


def is_projection_event_id(event_id: str | None) -> bool:
    return str(event_id or "").startswith(PROJ_ID_PREFIX)


def _parse_bound(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=TZ)
    text = str(value).strip()
    if not text:
        return None
    try:
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        dt = datetime.fromisoformat(text)
        return dt if dt.tzinfo else dt.replace(tzinfo=TZ)
    except Exception:
        return None


def _as_date(value: Any) -> date | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.astimezone(TZ).date()
    if isinstance(value, date):
        return value
    text = str(value).strip()[:10]
    try:
        return date.fromisoformat(text)
    except Exception:
        return None


def _all_day_bounds(day: date, days: int = 1) -> tuple[str, str]:
    start = datetime.combine(day, time(0, 0), tzinfo=TZ)
    end = datetime.combine(day + timedelta(days=max(1, days) - 1), time(23, 59), tzinfo=TZ)
    return start.isoformat(), end.isoformat()


def _timed_bounds(day: date, start_t: Any, end_t: Any) -> tuple[str, str] | None:
    def _parse_time(v: Any) -> time | None:
        if v is None:
            return None
        if isinstance(v, time):
            return v
        text = str(v).strip()
        if not text:
            return None
        try:
            parts = text.split(":")
            return time(int(parts[0]), int(parts[1]) if len(parts) > 1 else 0)
        except Exception:
            return None

    st = _parse_time(start_t)
    et = _parse_time(end_t)
    if not st or not et:
        return None
    start = datetime.combine(day, st, tzinfo=TZ)
    end = datetime.combine(day, et, tzinfo=TZ)
    if end <= start:
        end = start + timedelta(hours=1)
    return start.isoformat(), end.isoformat()


def _projection_event(
    *,
    suffix: str,
    company_code: str,
    title: str,
    title_ar: str,
    event_type: str,
    start_at: str,
    end_at: str,
    preview_category: str,
    module_owner: str,
    authority: str,
    source_workflow: str,
    source_record_id: str,
    deep_link: dict[str, str],
    all_day: bool = False,
    busy: bool = False,
    extra_meta: dict[str, Any] | None = None,
) -> dict[str, Any]:
    meta = {
        "preview_category": preview_category,
        "module_owner": module_owner,
        "source_workflow": source_workflow,
        "source_record_id": source_record_id,
        "projection": True,
        "read_only": True,
        "deep_link": deep_link,
    }
    if extra_meta:
        meta.update(extra_meta)
    return {
        "event_id": f"{PROJ_ID_PREFIX}{suffix}",
        "company_code": company_code,
        "event_type": event_type,
        "title": title,
        "title_ar": title_ar,
        "status": "confirmed",
        "start_at": start_at,
        "end_at": end_at,
        "timezone": "Asia/Kuwait",
        "all_day": all_day,
        "visibility": "company" if authority == "company_events" else "team",
        "detail_level": "full",
        "busy": busy,
        "version": 1,
        "interview_managed": False,
        "projection_managed": True,
        "authority": authority,
        "preview_only": False,
        "attendees": [],
        "guests": [],
        "links": [
            {
                "link_id": f"proj-{suffix}",
                "source_workflow": source_workflow,
                "source_record_id": source_record_id,
                "link_status": "active",
            }
        ],
        "metadata": meta,
        **(
            {"employee_key": deep_link.get("employee")}
            if deep_link.get("employee")
            else {}
        ),
        **(
            {"leave_id": deep_link.get("leave")}
            if deep_link.get("leave")
            else {}
        ),
    }


def _range_dates(start: Any, end: Any) -> tuple[date, date] | None:
    start_dt = _parse_bound(start)
    end_dt = _parse_bound(end)
    if not start_dt or not end_dt:
        return None
    return start_dt.astimezone(TZ).date(), end_dt.astimezone(TZ).date()


def _overlaps_window(ev_start: date, ev_end: date, win_start: date, win_end: date) -> bool:
    # end bound is exclusive in calendar range queries
    return ev_start < win_end and ev_end >= win_start


def load_employee_starts(
    app_mod: Any,
    *,
    company_code: str,
    start: Any,
    end: Any,
) -> list[dict[str, Any]]:
    bounds = _range_dates(start, end)
    if not bounds:
        return []
    win_start, win_end = bounds
    company = company_code.upper()
    out: list[dict[str, Any]] = []
    with app_mod.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT employee_key, name, start_date, coalesce(employment_status, 'active') AS employment_status
                FROM employees
                WHERE company_code=%s
                  AND start_date IS NOT NULL
                  AND start_date >= %s
                  AND start_date < %s
                  AND lower(coalesce(employment_status, 'active')) <> 'left'
                ORDER BY start_date, name
                LIMIT 500
                """,
                (company, win_start, win_end),
            )
            for row in cur.fetchall():
                d = dict(row)
                day = _as_date(d.get("start_date"))
                if not day:
                    continue
                key = str(d.get("employee_key") or "").strip()
                name = str(d.get("name") or key or "Employee").strip()
                start_at, end_at = _all_day_bounds(day)
                out.append(
                    _projection_event(
                        suffix=f"employee-start-{key}",
                        company_code=company,
                        title=f"Employee start · {name}",
                        title_ar=f"بدء موظف · {name}",
                        event_type="other",
                        start_at=start_at,
                        end_at=end_at,
                        preview_category="employee_start",
                        module_owner="employees360",
                        authority="employees",
                        source_workflow="employee_start",
                        source_record_id=key,
                        deep_link={"page": "employees", "employee": key},
                        all_day=True,
                        extra_meta={"employee_name": name},
                    )
                )
    return out


def load_onboarding_deadlines(
    app_mod: Any,
    *,
    company_code: str,
    start: Any,
    end: Any,
) -> list[dict[str, Any]]:
    bounds = _range_dates(start, end)
    if not bounds:
        return []
    win_start, win_end = bounds
    company = company_code.upper()
    out: list[dict[str, Any]] = []
    with app_mod.db_connect() as conn:
        with conn.cursor() as cur:
            import onboarding_completion_contract as _completion

            cur.execute(
                f"""
                SELECT oi.item_id, oi.employee_key, oi.due_date, oi.status, oi.label, oi.document_type,
                       e.name AS employee_name, a.status AS assignment_status
                FROM onboarding_items oi
                JOIN employees e ON e.employee_key = oi.employee_key AND e.company_code = %s
                LEFT JOIN employee_onboarding_assignments a
                  ON a.employee_key = oi.employee_key AND a.company_code = e.company_code
                WHERE oi.due_date IS NOT NULL
                  AND oi.due_date >= %s
                  AND oi.due_date < %s
                  AND lower(coalesce(e.employment_status, 'active')) <> 'left'
                  AND lower(coalesce(a.status, 'in_progress')) NOT IN ('completed', 'cancelled', 'abandoned')
                  AND {_completion.sql_open_predicate('oi.status')}
                ORDER BY oi.due_date, e.name
                LIMIT 800
                """,
                (company, win_start, win_end),
            )
            for row in cur.fetchall():
                d = dict(row)
                day = _as_date(d.get("due_date"))
                if not day:
                    continue
                key = str(d.get("employee_key") or "").strip()
                item_id = str(d.get("item_id") or "").strip()
                name = str(d.get("employee_name") or key).strip()
                label = str(d.get("label") or d.get("document_type") or "Onboarding").strip()
                start_at, end_at = _all_day_bounds(day)
                out.append(
                    _projection_event(
                        suffix=f"onboarding-{key}-{item_id}",
                        company_code=company,
                        title=f"Onboarding · {label} · {name}",
                        title_ar=f"إنهاء التعيين · {label} · {name}",
                        event_type="deadline",
                        start_at=start_at,
                        end_at=end_at,
                        preview_category="onboarding_deadline",
                        module_owner="onboarding",
                        authority="onboarding",
                        source_workflow="onboarding_item",
                        source_record_id=f"{key}:{item_id}",
                        deep_link={"page": "onboarding", "employee": key, "item": item_id},
                        all_day=True,
                        extra_meta={"employee_name": name, "item_label": label},
                    )
                )
    return out


def load_approved_leave(
    app_mod: Any,
    *,
    company_code: str,
    start: Any,
    end: Any,
) -> list[dict[str, Any]]:
    bounds = _range_dates(start, end)
    if not bounds:
        return []
    win_start, win_end = bounds
    company = company_code.upper()
    out: list[dict[str, Any]] = []
    with app_mod.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT lr.leave_id, lr.employee_key, lr.start_date, lr.end_date, lr.status,
                       lr.leave_type, lr.duration_unit, lr.start_time, lr.end_time, e.name AS employee_name
                FROM leave_requests lr
                JOIN employees e ON e.employee_key = lr.employee_key AND e.company_code = lr.company_code
                WHERE lr.company_code=%s
                  AND lr.status = 'approved'
                  AND lr.start_date IS NOT NULL
                  AND lr.end_date IS NOT NULL
                  AND lr.start_date < %s
                  AND lr.end_date >= %s
                  AND lower(coalesce(e.employment_status, 'active')) <> 'left'
                ORDER BY lr.start_date, e.name
                LIMIT 500
                """,
                (company, win_end, win_start),
            )
            for row in cur.fetchall():
                d = dict(row)
                start_d = _as_date(d.get("start_date"))
                end_d = _as_date(d.get("end_date"))
                if not start_d or not end_d:
                    continue
                if not _overlaps_window(start_d, end_d, win_start, win_end):
                    continue
                key = str(d.get("employee_key") or "").strip()
                leave_id = str(d.get("leave_id") or "").strip()
                name = str(d.get("employee_name") or key).strip()
                leave_type = str(d.get("leave_type") or "leave").replace("_", " ").strip()
                duration = str(d.get("duration_unit") or "full_day").lower()
                all_day = duration in {"", "full_day", "day", "days"}
                if all_day:
                    span = max(1, (end_d - start_d).days + 1)
                    start_at, end_at = _all_day_bounds(start_d, span)
                else:
                    timed = _timed_bounds(start_d, d.get("start_time"), d.get("end_time"))
                    if timed:
                        start_at, end_at = timed
                        all_day = False
                    else:
                        start_at, end_at = _all_day_bounds(start_d, max(1, (end_d - start_d).days + 1))
                        all_day = True
                out.append(
                    _projection_event(
                        suffix=f"leave-{leave_id}",
                        company_code=company,
                        title=f"Approved leave · {name}",
                        title_ar=f"إجازة معتمدة · {name}",
                        event_type="out_of_office",
                        start_at=start_at,
                        end_at=end_at,
                        preview_category="approved_leave",
                        module_owner="leave",
                        authority="leave",
                        source_workflow="leave",
                        source_record_id=leave_id,
                        deep_link={"page": "leave", "leave": leave_id, "employee": key},
                        all_day=all_day,
                        busy=True,
                        extra_meta={"employee_name": name, "leave_type": leave_type},
                    )
                )
    return out


def load_compliance_expiries(
    app_mod: Any,
    *,
    company_code: str,
    start: Any,
    end: Any,
) -> list[dict[str, Any]]:
    bounds = _range_dates(start, end)
    if not bounds:
        return []
    win_start, win_end = bounds
    company = company_code.upper()
    out: list[dict[str, Any]] = []
    classify = getattr(app_mod, "classify_compliance_row", None)
    with app_mod.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT cd.employee_key, cd.document_type, cd.expiry_date, cd.status, cd.renewal_status,
                       cd.warning_days, e.name AS employee_name
                FROM compliance_documents cd
                JOIN employees e ON e.employee_key = cd.employee_key AND e.company_code = cd.company_code
                WHERE cd.company_code=%s
                  AND cd.expiry_date IS NOT NULL
                  AND cd.expiry_date >= %s
                  AND cd.expiry_date < %s
                  AND lower(coalesce(cd.status, '')) NOT IN ('missing', 'archived', 'superseded', 'rejected')
                  AND lower(coalesce(cd.renewal_status, '')) NOT IN ('superseded', 'rejected', 'archived')
                  AND lower(coalesce(e.employment_status, 'active')) <> 'left'
                ORDER BY cd.expiry_date, e.name
                LIMIT 800
                """,
                (company, win_start, win_end),
            )
            for row in cur.fetchall():
                d = dict(row)
                # Confirmed/usable docs only — pending OCR review stays out.
                renewal = str(d.get("renewal_status") or "").strip().lower()
                status = str(d.get("status") or "").strip().lower()
                if renewal in {"pending_hr_review", "pending"} and status not in {"valid", "received", "expiring_soon", "expired"}:
                    continue
                if callable(classify):
                    try:
                        classified = classify(d) or {}
                        bucket = str(classified.get("status") or "").lower()
                        if bucket not in {"expired", "expiring_soon", "valid"}:
                            # Still project dated expiries inside the window for planning
                            if bucket in {"missing", "needs_review"} and not d.get("expiry_date"):
                                continue
                    except Exception:
                        pass
                day = _as_date(d.get("expiry_date"))
                if not day:
                    continue
                key = str(d.get("employee_key") or "").strip()
                doc_type = str(d.get("document_type") or "document").strip()
                name = str(d.get("employee_name") or key).strip()
                pretty = doc_type.replace("_", " ")
                start_at, end_at = _all_day_bounds(day)
                out.append(
                    _projection_event(
                        suffix=f"compliance-{key}-{doc_type}",
                        company_code=company,
                        title=f"Compliance · {pretty} · {name}",
                        title_ar=f"امتثال · {pretty} · {name}",
                        event_type="deadline",
                        start_at=start_at,
                        end_at=end_at,
                        preview_category="compliance_expiry",
                        module_owner="compliance",
                        authority="compliance",
                        source_workflow="compliance_document",
                        source_record_id=f"{key}:{doc_type}",
                        deep_link={"page": "compliance", "employee": key, "document_type": doc_type},
                        all_day=True,
                        extra_meta={"employee_name": name, "document_type": doc_type},
                    )
                )
    return out


def load_company_events(
    app_mod: Any,
    *,
    company_code: str,
    start: Any,
    end: Any,
) -> list[dict[str, Any]]:
    """Company events = approved/seeded public holidays (no training LMS yet)."""
    bounds = _range_dates(start, end)
    if not bounds:
        return []
    win_start, win_end = bounds
    company = company_code.upper()
    out: list[dict[str, Any]] = []
    with app_mod.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT holiday_id, holiday_date, name, coalesce(review_status, 'seeded_fixed') AS review_status
                FROM public_holidays
                WHERE company_code=%s
                  AND holiday_date >= %s
                  AND holiday_date < %s
                  AND lower(coalesce(review_status, 'seeded_fixed')) NOT IN
                      ('draft', 'pending_review', 'rejected', 'superseded')
                ORDER BY holiday_date
                LIMIT 200
                """,
                (company, win_start, win_end),
            )
            for row in cur.fetchall():
                d = dict(row)
                day = _as_date(d.get("holiday_date"))
                if not day:
                    continue
                holiday_id = str(d.get("holiday_id") or f"{day.isoformat()}").strip()
                name = str(d.get("name") or "Company holiday").strip()
                start_at, end_at = _all_day_bounds(day)
                out.append(
                    _projection_event(
                        suffix=f"company-holiday-{holiday_id}",
                        company_code=company,
                        title=f"Company · {name}",
                        title_ar=f"الشركة · {name}",
                        event_type="meeting",
                        start_at=start_at,
                        end_at=end_at,
                        preview_category="training_company",
                        module_owner="leave",
                        authority="company_events",
                        source_workflow="public_holiday",
                        source_record_id=holiday_id,
                        deep_link={"page": "leave"},
                        all_day=True,
                        extra_meta={"holiday_name": name},
                    )
                )
    return out


LOADERS = {
    "employee_start": load_employee_starts,
    "onboarding_deadline": load_onboarding_deadlines,
    "approved_leave": load_approved_leave,
    "compliance_expiry": load_compliance_expiries,
    "company_events": load_company_events,
}


def collect_projection_events(
    app_mod: Any,
    *,
    company_code: str,
    permissions: list[str] | None,
    start: Any,
    end: Any,
    event_types: list[str] | None = None,
    statuses: list[str] | None = None,
    sources: tuple[str, ...] | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Return (events, meta) for enabled sources the actor may read."""
    company = str(company_code or "").strip().upper()
    wanted = sources or SOURCE_ORDER
    enabled: list[str] = []
    events: list[dict[str, Any]] = []
    for source in wanted:
        meta = SOURCE_FLAGS[source]
        if not source_enabled_for_company(source, company):
            continue
        if not actor_has_permission(permissions, meta["permission"]):
            continue
        enabled.append(source)
        loader = LOADERS[source]
        events.extend(loader(app_mod, company_code=company, start=start, end=end))

    if statuses:
        allow = {str(s).lower() for s in statuses}
        events = [e for e in events if str(e.get("status") or "").lower() in allow]
    if event_types:
        allow_t = {str(t).lower() for t in event_types}
        events = [e for e in events if str(e.get("event_type") or "").lower() in allow_t]

    # Stable order by start then title
    events.sort(key=lambda e: (str(e.get("start_at") or ""), str(e.get("title") or "")))
    return events, {"enabled_sources": enabled, "injected": len(events)}


def get_projection_event(
    app_mod: Any,
    *,
    company_code: str,
    permissions: list[str] | None,
    event_id: str,
) -> dict[str, Any] | None:
    if not is_projection_event_id(event_id):
        return None
    # Wide window around "now" — detail lookup for open drawer.
    now = datetime.now(TZ)
    start = (now - timedelta(days=400)).isoformat()
    end = (now + timedelta(days=400)).isoformat()
    events, _ = collect_projection_events(
        app_mod,
        company_code=company_code,
        permissions=permissions,
        start=start,
        end=end,
    )
    for event in events:
        if str(event.get("event_id")) == str(event_id):
            return event
    return None


def merge_into_list_result(
    app_mod: Any,
    result: dict[str, Any],
    *,
    company_code: str,
    permissions: list[str] | None,
    start: Any,
    end: Any,
    event_types: list[str] | None = None,
    statuses: list[str] | None = None,
) -> dict[str, Any]:
    projected, meta = collect_projection_events(
        app_mod,
        company_code=company_code,
        permissions=permissions,
        start=start,
        end=end,
        event_types=event_types,
        statuses=statuses,
    )
    if not meta.get("enabled_sources") and not projected:
        return result
    existing = list(result.get("events") or [])
    seen = {str(e.get("event_id")) for e in existing}
    # Also de-dupe leave windows that already have a manual OOO linked somehow by source id in links
    for e in existing:
        for link in e.get("links") or []:
            sw = str(link.get("source_workflow") or "")
            sid = str(link.get("source_record_id") or "")
            if sw and sid:
                seen.add(f"link:{sw}:{sid}")
    merged_proj = []
    for ev in projected:
        eid = str(ev.get("event_id"))
        if eid in seen:
            continue
        link = (ev.get("links") or [{}])[0]
        link_key = f"link:{link.get('source_workflow')}:{link.get('source_record_id')}"
        if link_key in seen:
            continue
        merged_proj.append(ev)
        seen.add(eid)
        seen.add(link_key)
    out = dict(result)
    out["events"] = existing + merged_proj
    out["count"] = len(out["events"])
    out["posthire_projections"] = {
        "enabled": True,
        "injected": len(merged_proj),
        "sources": meta.get("enabled_sources") or [],
    }
    return out


def merge_into_overview(
    app_mod: Any,
    result: dict[str, Any],
    *,
    company_code: str,
    permissions: list[str] | None,
) -> dict[str, Any]:
    now = datetime.now(TZ)
    month_start = datetime(now.year, now.month, 1, tzinfo=TZ)
    if now.month == 12:
        month_end = datetime(now.year + 1, 1, 1, tzinfo=TZ)
    else:
        month_end = datetime(now.year, now.month + 1, 1, tzinfo=TZ)
    projected, meta = collect_projection_events(
        app_mod,
        company_code=company_code,
        permissions=permissions,
        start=month_start.isoformat(),
        end=month_end.isoformat(),
        statuses=["confirmed"],
    )
    if not meta.get("enabled_sources") and not projected:
        return result
    busy = set(result.get("month", {}).get("busy_days") or [])
    for ev in projected:
        day = str(ev.get("start_at") or "")[:10]
        if day:
            busy.add(day)
    upcoming = list(result.get("upcoming") or [])
    seen = {str(e.get("event_id")) for e in upcoming}
    for ev in projected:
        if ev["event_id"] in seen:
            continue
        es = _parse_bound(ev.get("start_at"))
        if not es or es < now - timedelta(hours=1):
            continue
        upcoming.append(ev)
        if len(upcoming) >= 8:
            break
    out = dict(result)
    month = dict(out.get("month") or {})
    month["busy_days"] = sorted(busy)
    out["month"] = month
    out["upcoming"] = upcoming[:8]
    out["upcoming_count"] = len(out["upcoming"])
    out["posthire_projections"] = {
        "enabled": True,
        "injected": len(projected),
        "sources": meta.get("enabled_sources") or [],
    }
    return out
