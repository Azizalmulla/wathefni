"""Calendar Wave 1 — populated preview injector (WATHEFNI canary only).

Observation/review surface only:
- Does NOT write calendar_events or any specialist module rows
- Does NOT enable production emitters
- Gated by WATHEFNI_CALENDAR_POPULATED_PREVIEW + company allowlist
"""

from __future__ import annotations

import os
from datetime import date, datetime, time, timedelta, timezone
from typing import Any
from zoneinfo import ZoneInfo

FLAG = "WATHEFNI_CALENDAR_POPULATED_PREVIEW"
COMPANIES_FLAG = "WATHEFNI_CALENDAR_POPULATED_PREVIEW_COMPANIES"
PREVIEW_ID_PREFIX = "calprev-"
TZ = ZoneInfo("Asia/Kuwait")


def _env_on(name: str) -> bool:
    return str(os.environ.get(name) or "").strip().lower() in {"1", "on", "true", "yes", "enabled"}


def preview_enabled_for_company(company_code: str | None) -> bool:
    if not _env_on(FLAG):
        return False
    company = str(company_code or "").strip().upper()
    if not company:
        return False
    raw = str(os.environ.get(COMPANIES_FLAG) or "WATHEFNI").strip()
    allowed = {part.strip().upper() for part in raw.split(",") if part.strip()}
    return company in allowed


def is_preview_event_id(event_id: str | None) -> bool:
    return str(event_id or "").startswith(PREVIEW_ID_PREFIX)


def _week_sunday(d: date) -> date:
    return d - timedelta(days=(d.weekday() + 1) % 7)


def _at(day: date, hour: int, minute: int = 0, *, end_hour: int | None = None, end_minute: int = 0) -> tuple[str, str]:
    start = datetime.combine(day, time(hour, minute), tzinfo=TZ)
    if end_hour is None:
        end = start + timedelta(hours=1)
    else:
        end = datetime.combine(day, time(end_hour, end_minute), tzinfo=TZ)
    return start.isoformat(), end.isoformat()


def _all_day(day: date, days: int = 1) -> tuple[str, str]:
    start = datetime.combine(day, time(0, 0), tzinfo=TZ)
    end = datetime.combine(day + timedelta(days=days - 1), time(23, 59), tzinfo=TZ)
    return start.isoformat(), end.isoformat()


def _event(
    *,
    suffix: str,
    title: str,
    title_ar: str,
    event_type: str,
    status: str,
    start_at: str,
    end_at: str,
    preview_category: str,
    module_owner: str,
    all_day: bool = False,
    note: str | None = None,
) -> dict[str, Any]:
    return {
        "event_id": f"{PREVIEW_ID_PREFIX}{suffix}",
        "company_code": "WATHEFNI",
        "event_type": event_type,
        "title": title,
        "title_ar": title_ar,
        "status": status,
        "start_at": start_at,
        "end_at": end_at,
        "timezone": "Asia/Kuwait",
        "all_day": all_day,
        "visibility": "company",
        "detail_level": "full",
        "busy": event_type in {"out_of_office", "personal_block"},
        "version": 1,
        "interview_managed": False,
        "authority": "calendar_preview",
        "preview_only": True,
        "attendees": [],
        "guests": [],
        "links": [],
        "metadata": {
            "preview_only": True,
            "preview_category": preview_category,
            "module_owner": module_owner,
            "note": note,
            "synthetic": True,
            "not_a_real_record": True,
        },
    }


def build_preview_events(*, now: datetime | None = None) -> list[dict[str, Any]]:
    """Deterministic synthetic week relative to Kuwait 'today' (Sun–Sat)."""
    now_local = (now or datetime.now(TZ)).astimezone(TZ)
    sunday = _week_sunday(now_local.date())
    d = {i: sunday + timedelta(days=i) for i in range(7)}  # 0=Sun … 6=Sat

    events: list[dict[str, Any]] = []

    # Connected-style (still synthetic, labeled Preview for honesty — no DB rows)
    s, e = _at(d[1], 10, 0, end_hour=11, end_minute=0)  # Mon
    events.append(
        _event(
            suffix="interview-sara",
            title="Preview · Interview · Sara · Product Designer",
            title_ar="معاينة · مقابلة · سارة · مصممة منتجات",
            event_type="interview",
            status="confirmed",
            start_at=s,
            end_at=e,
            preview_category="interview",
            module_owner="interviews",
            note="Synthetic preview only — not a live interview row.",
        )
    )
    s, e = _at(d[1], 10, 30, end_hour=11, end_minute=30)  # overlap Mon
    events.append(
        _event(
            suffix="meeting-hiring-sync",
            title="Preview · Hiring sync",
            title_ar="معاينة · مزامنة التوظيف",
            event_type="meeting",
            status="confirmed",
            start_at=s,
            end_at=e,
            preview_category="meeting",
            module_owner="calendar",
        )
    )
    s, e = _all_day(d[1])
    events.append(
        _event(
            suffix="employee-start-khaled",
            title="Preview · Employee start · Khaled",
            title_ar="معاينة · بدء موظف · خالد",
            event_type="other",
            status="confirmed",
            start_at=s,
            end_at=e,
            preview_category="employee_start",
            module_owner="employees360",
            all_day=True,
        )
    )

    s, e = _at(d[2], 14, 0, end_hour=15, end_minute=0)  # Tue
    events.append(
        _event(
            suffix="interview-omar",
            title="Preview · Interview · Omar · Ops Lead",
            title_ar="معاينة · مقابلة · عمر · قائد العمليات",
            event_type="interview",
            status="tentative",
            start_at=s,
            end_at=e,
            preview_category="interview",
            module_owner="interviews",
        )
    )
    s, e = _at(d[2], 16, 0, end_hour=16, end_minute=30)
    events.append(
        _event(
            suffix="payroll-cutoff",
            title="Preview · Payroll cutoff",
            title_ar="معاينة · قطع الرواتب",
            event_type="deadline",
            status="confirmed",
            start_at=s,
            end_at=e,
            preview_category="payroll_cutoff",
            module_owner="payroll",
        )
    )

    s, e = _at(d[3], 9, 0, end_hour=9, end_minute=45)  # Wed
    events.append(
        _event(
            suffix="video-lina",
            title="Preview · Video interview (async) · Lina",
            title_ar="معاينة · مقابلة مرئية · لينا",
            event_type="other",
            status="confirmed",
            start_at=s,
            end_at=e,
            preview_category="video_interview",
            module_owner="interviews",
            note="Async video is not a timed calendar source in production.",
        )
    )
    s, e = _all_day(d[3], days=2)  # Wed–Thu leave
    events.append(
        _event(
            suffix="leave-nour",
            title="Preview · Approved leave · Nour",
            title_ar="معاينة · إجازة معتمدة · نور",
            event_type="out_of_office",
            status="confirmed",
            start_at=s,
            end_at=e,
            preview_category="approved_leave",
            module_owner="leave",
            all_day=True,
        )
    )

    s, e = _at(d[4], 11, 30, end_hour=12, end_minute=0)  # Thu
    events.append(
        _event(
            suffix="followup-sara",
            title="Preview · Candidate follow-up · Sara",
            title_ar="معاينة · متابعة مرشح · سارة",
            event_type="deadline",
            status="confirmed",
            start_at=s,
            end_at=e,
            preview_category="candidate_followup",
            module_owner="candidates",
        )
    )
    s, e = _at(d[4], 13, 0, end_hour=15, end_minute=0)
    events.append(
        _event(
            suffix="training-safety",
            title="Preview · Company training · Safety",
            title_ar="معاينة · تدريب الشركة · السلامة",
            event_type="meeting",
            status="confirmed",
            start_at=s,
            end_at=e,
            preview_category="training_company",
            module_owner="calendar_manual",
        )
    )

    s, e = _at(d[5], 17, 0, end_hour=17, end_minute=30)  # Fri
    events.append(
        _event(
            suffix="onboard-docs",
            title="Preview · Onboarding deadline · docs due",
            title_ar="معاينة · موعد إنهاء التعيين · المستندات",
            event_type="deadline",
            status="confirmed",
            start_at=s,
            end_at=e,
            preview_category="onboarding_deadline",
            module_owner="onboarding",
        )
    )
    s, e = _at(d[5], 11, 0, end_hour=12, end_minute=0)
    events.append(
        _event(
            suffix="interview-cancelled",
            title="Preview · Interview · cancelled slot",
            title_ar="معاينة · مقابلة · ملغاة",
            event_type="interview",
            status="cancelled",
            start_at=s,
            end_at=e,
            preview_category="interview",
            module_owner="interviews",
        )
    )

    s, e = _at(d[6], 9, 0, end_hour=9, end_minute=30)  # Sat
    events.append(
        _event(
            suffix="compliance-civil-id",
            title="Preview · Compliance expiry · Civil ID",
            title_ar="معاينة · انتهاء امتثال · البطاقة المدنية",
            event_type="deadline",
            status="confirmed",
            start_at=s,
            end_at=e,
            preview_category="compliance_expiry",
            module_owner="compliance",
        )
    )

    # Sunday intentionally empty for sparse-day review
    return events


def _parse_bound(value: Any) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        dt = datetime.fromisoformat(text)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except ValueError:
        return None


def events_overlapping_range(
    *,
    start: Any,
    end: Any,
    event_types: list[str] | None = None,
    statuses: list[str] | None = None,
) -> list[dict[str, Any]]:
    start_dt = _parse_bound(start)
    end_dt = _parse_bound(end)
    if not start_dt or not end_dt:
        return []
    type_set = {t.lower() for t in (event_types or []) if t} or None
    status_set = {s.lower() for s in (statuses or []) if s} or None
    out: list[dict[str, Any]] = []
    for ev in build_preview_events():
        es = _parse_bound(ev.get("start_at"))
        ee = _parse_bound(ev.get("end_at"))
        if not es or not ee:
            continue
        if ee < start_dt or es > end_dt:
            continue
        if type_set and str(ev.get("event_type") or "").lower() not in type_set:
            # Also allow filter by preview_category via metadata when event_type is other
            cat = str((ev.get("metadata") or {}).get("preview_category") or "").lower()
            if cat not in type_set:
                continue
        if status_set and str(ev.get("status") or "").lower() not in status_set:
            continue
        out.append(ev)
    return out


def get_preview_event(event_id: str) -> dict[str, Any] | None:
    if not is_preview_event_id(event_id):
        return None
    for ev in build_preview_events():
        if ev["event_id"] == event_id:
            return ev
    return None


def merge_into_list_result(result: dict[str, Any], *, company_code: str, start: Any, end: Any,
                           event_types: list[str] | None = None, statuses: list[str] | None = None) -> dict[str, Any]:
    if not preview_enabled_for_company(company_code):
        return result
    preview = events_overlapping_range(start=start, end=end, event_types=event_types, statuses=statuses)
    if not preview:
        out = dict(result)
        out["populated_preview"] = {"enabled": True, "injected": 0, "company_code": "WATHEFNI"}
        return out
    existing = list(result.get("events") or [])
    # Preview after real events; de-dupe by id
    seen = {str(e.get("event_id")) for e in existing}
    merged = existing + [e for e in preview if e["event_id"] not in seen]
    out = dict(result)
    out["events"] = merged
    out["count"] = len(merged)
    out["populated_preview"] = {
        "enabled": True,
        "injected": len(preview),
        "company_code": "WATHEFNI",
        "label": "Preview",
        "label_ar": "معاينة",
        "honesty": "Synthetic review events only — not stored module records.",
    }
    return out


def merge_into_overview(result: dict[str, Any], *, company_code: str) -> dict[str, Any]:
    if not preview_enabled_for_company(company_code):
        return result
    now = datetime.now(TZ)
    month_start = datetime(now.year, now.month, 1, tzinfo=TZ)
    if now.month == 12:
        month_end = datetime(now.year + 1, 1, 1, tzinfo=TZ)
    else:
        month_end = datetime(now.year, now.month + 1, 1, tzinfo=TZ)
    preview = events_overlapping_range(start=month_start.isoformat(), end=month_end.isoformat(),
                                       statuses=["tentative", "confirmed"])
    busy = set(result.get("month", {}).get("busy_days") or [])
    for ev in preview:
        day = str(ev.get("start_at") or "")[:10]
        if day:
            busy.add(day)
    upcoming = list(result.get("upcoming") or [])
    seen = {str(e.get("event_id")) for e in upcoming}
    for ev in preview:
        if ev["event_id"] in seen:
            continue
        es = _parse_bound(ev.get("start_at"))
        if not es or es < now - timedelta(hours=1):
            continue
        if str(ev.get("status") or "").lower() == "cancelled":
            continue
        upcoming.append(ev)
        if len(upcoming) >= 5:
            break
    out = dict(result)
    month = dict(out.get("month") or {})
    month["busy_days"] = sorted(busy)
    out["month"] = month
    out["upcoming"] = upcoming[:5]
    out["upcoming_count"] = len(out["upcoming"])
    out["populated_preview"] = {
        "enabled": True,
        "injected": len(preview),
        "company_code": "WATHEFNI",
        "label": "Preview",
    }
    return out
