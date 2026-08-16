"""Wathefni Calendar C3 — shared conflict authority.

Used by Calendar create/update and Interview schedule/reschedule.
Calendar *processing* stays async; conflict checks run inside the mutation TX.

Privacy: conflict messages never include candidate PII for unauthorized audiences.
Leave/shift overlaps are warnings unless company policy hardens them.
"""

from __future__ import annotations

from datetime import datetime, time, timedelta, timezone
from typing import Any, Iterable, Mapping, Sequence
from uuid import uuid4
from zoneinfo import ZoneInfo

import interview_lifecycle as life

# Conflict types (canonical)
TYPE_ATTENDEE = "attendee_double_book"
TYPE_ORGANIZER = "organizer_double_book"
TYPE_LEAVE = "leave_overlap"
TYPE_SHIFT = "shift_overlap"
TYPE_WORKING_HOURS = "working_hours"
TYPE_INTERVIEW_CANDIDATE = "interview_candidate"
TYPE_INTERVIEW_PANEL = "interview_panel"

DEFAULT_WORK_WEEKDAYS = {0, 1, 2, 3, 4}  # Mon–Fri fallback; Kuwait Sun–Thu preferred via policy
DEFAULT_WORK_START = time(8, 0)
DEFAULT_WORK_END = time(17, 0)
DEFAULT_TZ = "Asia/Kuwait"


class SchedulingConflictError(Exception):
    """Blocking scheduling conflicts — caller must not commit without override."""

    def __init__(
        self,
        conflicts: list[dict[str, Any]],
        *,
        message: str = "Scheduling conflict detected.",
        message_ar: str = "تم اكتشاف تعارض في الجدولة.",
    ):
        super().__init__(message)
        self.code = "scheduling_conflict"
        self.message = message
        self.message_ar = message_ar
        self.conflicts = list(conflicts or [])
        self.http_status = 409

    def envelope(self) -> dict[str, Any]:
        return {
            "ok": False,
            "error": self.code,
            "message": self.message,
            "message_ar": self.message_ar,
            "conflicts": self.conflicts,
            "blocking_count": sum(1 for c in self.conflicts if c.get("blocking")),
            "warning_count": sum(1 for c in self.conflicts if not c.get("blocking")),
            "draft_preserved": True,
            "safe_next_action": "resolve_or_override",
        }


def _text(value: Any) -> str:
    return str(value or "").strip()


def _parse_dt(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    raw = _text(value)
    if not raw:
        return None
    try:
        if raw.endswith("Z"):
            raw = raw[:-1] + "+00:00"
        dt = datetime.fromisoformat(raw)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def _iso(value: Any) -> str | None:
    dt = _parse_dt(value)
    return dt.isoformat() if dt else None


def _conflict(
    *,
    ctype: str,
    affected_ref: Mapping[str, Any],
    start: Any,
    end: Any,
    severity: str,
    blocking: bool,
    message: str,
    message_ar: str,
    attendee_role: str | None = None,
    extra: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    out: dict[str, Any] = {
        "type": ctype,
        "affected_ref": dict(affected_ref),
        "start_at": _iso(start),
        "end_at": _iso(end),
        "severity": severity,
        "blocking": bool(blocking),
        "message": message,
        "message_ar": message_ar,
    }
    if attendee_role:
        out["attendee_role"] = attendee_role
    if extra:
        out.update(dict(extra))
    return out


def company_work_policy(legacy: Any, company_code: str) -> dict[str, Any]:
    """Company working-hours policy with safe defaults (Kuwait-oriented)."""
    tz_name = DEFAULT_TZ
    leave_blocking = False
    shift_blocking = False
    workdays = {6, 0, 1, 2, 3}  # Sun–Thu
    try:
        settings = {}
        if hasattr(legacy, "get_company_settings"):
            settings = legacy.get_company_settings(_text(company_code).upper()) or {}
        tz_name = _text(settings.get("timezone")) or tz_name
        cal = settings.get("calendar") if isinstance(settings.get("calendar"), dict) else {}
        if isinstance(cal.get("work_weekdays"), list) and cal.get("work_weekdays"):
            workdays = {int(x) for x in cal["work_weekdays"]}
        if cal.get("leave_overlap_blocking") is True:
            leave_blocking = True
        if cal.get("shift_overlap_blocking") is True:
            shift_blocking = True
        start_s = _text(cal.get("work_start")) or "08:00"
        end_s = _text(cal.get("work_end")) or "17:00"
        wh_start = time.fromisoformat(start_s)
        wh_end = time.fromisoformat(end_s)
    except Exception:
        wh_start, wh_end = DEFAULT_WORK_START, DEFAULT_WORK_END
    return {
        "timezone": tz_name,
        "work_weekdays": workdays,
        "work_start": wh_start,
        "work_end": wh_end,
        "leave_overlap_blocking": leave_blocking,
        "shift_overlap_blocking": shift_blocking,
    }


def _user_employee_keys(cur: Any, company: str, user_ids: Sequence[str]) -> dict[str, list[str]]:
    """Map dashboard user_id → employee_key candidates (phone / employee_key columns)."""
    ids = [_text(u) for u in user_ids if _text(u)]
    if not ids:
        return {}
    out: dict[str, list[str]] = {uid: [] for uid in ids}
    try:
        cur.execute(
            """
            SELECT user_id::text AS user_id, phone, email
            FROM dashboard_users
            WHERE company_code=%s AND user_id::text = ANY(%s)
            """,
            (company, ids),
        )
        for row in cur.fetchall() or []:
            uid = _text(row.get("user_id"))
            keys: list[str] = []
            phone = _text(row.get("phone"))
            email = _text(row.get("email")).lower()
            if phone:
                keys.append(phone)
            if email:
                keys.append(email)
            out[uid] = keys
    except Exception:
        pass
    return out


def _attendee_role_map(attendees: Sequence[Mapping[str, Any]] | None) -> dict[str, str]:
    roles: dict[str, str] = {}
    for item in attendees or []:
        uid = _text(item.get("user_id"))
        if not uid:
            continue
        role = _text(item.get("role")).lower() or "required"
        if role == "organizer":
            role = "required"
        if role not in {"required", "optional", "resource_owner"}:
            role = "required"
        roles[uid] = role
    return roles


def check_calendar_attendee_overlaps(
    cur: Any,
    *,
    company_code: str,
    start: datetime,
    end: datetime,
    user_ids: Sequence[str],
    role_by_user: Mapping[str, str] | None = None,
    exclude_event_id: str | None = None,
    organizer_user_id: str | None = None,
) -> list[dict[str, Any]]:
    company = _text(company_code).upper()
    ids = sorted({_text(u) for u in user_ids if _text(u)})
    if not company or not ids or not start or not end:
        return []
    roles = dict(role_by_user or {})
    sql = """
        SELECT e.event_id, e.title, e.start_at, e.end_at, e.status, e.event_type,
               a.user_id, a.role, a.is_organizer
        FROM calendar_events e
        JOIN calendar_attendees a ON a.event_id = e.event_id AND a.company_code = e.company_code
        WHERE e.company_code = %s
          AND lower(COALESCE(e.status,'')) NOT IN ('cancelled', 'completed')
          AND a.rsvp_status <> 'removed'
          AND a.user_id = ANY(%s)
          AND e.start_at < %s
          AND e.end_at > %s
    """
    params: list[Any] = [company, ids, end, start]
    if exclude_event_id:
        sql += " AND e.event_id <> %s"
        params.append(_text(exclude_event_id))
    cur.execute(sql, params)
    conflicts: list[dict[str, Any]] = []
    for row in cur.fetchall() or []:
        uid = _text(row.get("user_id"))
        att_role = roles.get(uid) or _text(row.get("role")) or "required"
        is_optional = att_role == "optional"
        is_org = uid == _text(organizer_user_id) or bool(row.get("is_organizer"))
        ctype = TYPE_ORGANIZER if is_org else TYPE_ATTENDEE
        conflicts.append(
            _conflict(
                ctype=ctype,
                affected_ref={"kind": "user", "id": uid, "label": "Attendee"},
                start=row.get("start_at"),
                end=row.get("end_at"),
                severity="warning" if is_optional else "error",
                blocking=not is_optional,
                message=(
                    "Optional attendee has another event in this window."
                    if is_optional
                    else "Attendee is already booked in this window."
                ),
                message_ar=(
                    "لدى المدعو الاختياري حدث آخر في هذه الفترة."
                    if is_optional
                    else "المدعو محجوز بالفعل في هذه الفترة."
                ),
                attendee_role=att_role,
                extra={"conflicting_event_id": str(row.get("event_id")), "privacy_safe": True},
            )
        )
    return conflicts


def check_leave_overlaps(
    cur: Any,
    *,
    company_code: str,
    start: datetime,
    end: datetime,
    user_ids: Sequence[str],
    role_by_user: Mapping[str, str] | None = None,
    blocking: bool = False,
) -> list[dict[str, Any]]:
    company = _text(company_code).upper()
    key_map = _user_employee_keys(cur, company, user_ids)
    flat_keys = sorted({k for keys in key_map.values() for k in keys if k})
    if not flat_keys:
        return []
    start_d = start.date()
    end_d = end.date()
    try:
        cur.execute(
            """
            SELECT leave_id, employee_key, employee_name, start_date, end_date, status
            FROM leave_requests
            WHERE company_code=%s
              AND lower(COALESCE(status,'')) IN ('approved', 'active')
              AND start_date <= %s
              AND end_date >= %s
              AND employee_key = ANY(%s)
            """,
            (company, end_d, start_d, flat_keys),
        )
    except Exception:
        return []
    roles = dict(role_by_user or {})
    uid_by_key: dict[str, str] = {}
    for uid, keys in key_map.items():
        for k in keys:
            uid_by_key[k] = uid
    out: list[dict[str, Any]] = []
    for row in cur.fetchall() or []:
        ek = _text(row.get("employee_key"))
        uid = uid_by_key.get(ek, "")
        att_role = roles.get(uid) or "required"
        leave_block = blocking and att_role != "optional"
        out.append(
            _conflict(
                ctype=TYPE_LEAVE,
                affected_ref={"kind": "user", "id": uid or ek, "label": "Team member"},
                start=datetime.combine(row["start_date"], time.min, tzinfo=timezone.utc),
                end=datetime.combine(row["end_date"], time.max, tzinfo=timezone.utc),
                severity="error" if leave_block else "warning",
                blocking=leave_block,
                message="Attendee has approved leave overlapping this window.",
                message_ar="لدى المدعو إجازة معتمدة تتداخل مع هذه الفترة.",
                attendee_role=att_role,
                extra={"leave_id": str(row.get("leave_id")), "privacy_safe": True},
            )
        )
    return out


def check_shift_overlaps(
    cur: Any,
    *,
    company_code: str,
    start: datetime,
    end: datetime,
    user_ids: Sequence[str],
    role_by_user: Mapping[str, str] | None = None,
    timezone_name: str = DEFAULT_TZ,
    blocking: bool = False,
) -> list[dict[str, Any]]:
    company = _text(company_code).upper()
    key_map = _user_employee_keys(cur, company, user_ids)
    flat_keys = sorted({k for keys in key_map.values() for k in keys if k})
    if not flat_keys:
        return []
    try:
        tz = ZoneInfo(timezone_name)
    except Exception:
        tz = ZoneInfo(DEFAULT_TZ)
    local_start = start.astimezone(tz)
    local_end = end.astimezone(tz)
    try:
        cur.execute(
            """
            SELECT shift_id, employee_key, shift_date, start_time, end_time, timezone, status
            FROM shift_assignments
            WHERE company_code=%s
              AND lower(COALESCE(status,'')) IN ('scheduled', 'confirmed', 'assigned')
              AND shift_date >= %s
              AND shift_date <= %s
              AND employee_key = ANY(%s)
            """,
            (company, local_start.date(), local_end.date(), flat_keys),
        )
    except Exception:
        return []
    roles = dict(role_by_user or {})
    uid_by_key: dict[str, str] = {}
    for uid, keys in key_map.items():
        for k in keys:
            uid_by_key[k] = uid
    out: list[dict[str, Any]] = []
    for row in cur.fetchall() or []:
        try:
            row_tz = ZoneInfo(_text(row.get("timezone")) or timezone_name)
        except Exception:
            row_tz = tz
        sdt = datetime.combine(row["shift_date"], row["start_time"], tzinfo=row_tz)
        edt = datetime.combine(row["shift_date"], row["end_time"], tzinfo=row_tz)
        if edt <= sdt:
            edt = sdt + timedelta(hours=8)
        if not (sdt < end and edt > start):
            continue
        ek = _text(row.get("employee_key"))
        uid = uid_by_key.get(ek, "")
        att_role = roles.get(uid) or "required"
        shift_block = blocking and att_role != "optional"
        out.append(
            _conflict(
                ctype=TYPE_SHIFT,
                affected_ref={"kind": "user", "id": uid or ek, "label": "Team member"},
                start=sdt,
                end=edt,
                severity="error" if shift_block else "warning",
                blocking=shift_block,
                message="Attendee has an assigned shift overlapping this window.",
                message_ar="لدى المدعو وردية مسندة تتداخل مع هذه الفترة.",
                attendee_role=att_role,
                extra={"shift_id": str(row.get("shift_id")), "privacy_safe": True},
            )
        )
    return out


def check_working_hours(
    *,
    start: datetime,
    end: datetime,
    timezone_name: str,
    policy: Mapping[str, Any],
    all_day: bool = False,
    user_ids: Sequence[str] | None = None,
) -> list[dict[str, Any]]:
    if all_day:
        return []
    try:
        tz = ZoneInfo(timezone_name or policy.get("timezone") or DEFAULT_TZ)
    except Exception:
        tz = ZoneInfo(DEFAULT_TZ)
    local_start = start.astimezone(tz)
    local_end = end.astimezone(tz)
    workdays = set(policy.get("work_weekdays") or DEFAULT_WORK_WEEKDAYS)
    wh_start = policy.get("work_start") or DEFAULT_WORK_START
    wh_end = policy.get("work_end") or DEFAULT_WORK_END
    outside = False
    if local_start.weekday() not in workdays or local_end.weekday() not in workdays:
        outside = True
    if local_start.timetz().replace(tzinfo=None) < wh_start or local_end.timetz().replace(tzinfo=None) > wh_end:
        outside = True
    if not outside:
        return []
    ref_id = _text((user_ids or [None])[0]) if user_ids else "organizer"
    return [
        _conflict(
            ctype=TYPE_WORKING_HOURS,
            affected_ref={"kind": "policy", "id": "working_hours", "label": "Working hours"},
            start=start,
            end=end,
            severity="warning",
            blocking=False,
            message="Event falls outside company working hours.",
            message_ar="الحدث خارج ساعات العمل الرسمية للشركة.",
            extra={"timezone": str(tz), "privacy_safe": True, "affected_user_hint": ref_id},
        )
    ]


def check_interview_legacy_conflicts(
    cur: Any,
    *,
    company_code: str,
    app_key: str | None,
    start: datetime,
    end: datetime,
    panel: list[dict[str, Any]] | None = None,
    exclude_interview_id: str | None = None,
) -> list[dict[str, Any]]:
    """Fold legacy interview candidate/panel checks into shared conflict shape."""
    if not app_key:
        # Still check panel overlaps without candidate when scheduling calendar-only.
        panel = panel or []
        if not panel:
            return []
        # Use empty app_key path — find_schedule_conflicts requires app_key for candidate;
        # call panel-only via temporary synthetic key that won't match.
        raw = life.find_schedule_conflicts(
            cur,
            company_code=company_code,
            app_key="__calendar_no_candidate__",
            start=start,
            end=end,
            panel=panel,
            exclude_interview_id=exclude_interview_id,
        )
    else:
        raw = life.find_schedule_conflicts(
            cur,
            company_code=company_code,
            app_key=app_key,
            start=start,
            end=end,
            panel=panel,
            exclude_interview_id=exclude_interview_id,
        )
    out: list[dict[str, Any]] = []
    for item in raw:
        if item.get("type") == "candidate":
            interview = item.get("interview") or {}
            out.append(
                _conflict(
                    ctype=TYPE_INTERVIEW_CANDIDATE,
                    affected_ref={"kind": "candidate", "id": "candidate", "label": "Candidate"},
                    start=interview.get("scheduled_start"),
                    end=interview.get("scheduled_end"),
                    severity="error",
                    blocking=True,
                    message="Candidate already has a live interview in this window.",
                    message_ar="لدى المرشح مقابلة مباشرة في هذه الفترة.",
                    extra={
                        "interview_id": str(interview.get("interview_id") or ""),
                        "privacy_safe": True,
                    },
                )
            )
        elif item.get("type") == "panel":
            assignment = item.get("assignment") or {}
            out.append(
                _conflict(
                    ctype=TYPE_INTERVIEW_PANEL,
                    affected_ref={
                        "kind": "user",
                        "id": _text(assignment.get("assignee_user_id"))
                        or _text(assignment.get("assignee_email"))
                        or "panel",
                        "label": "Panel member",
                    },
                    start=assignment.get("scheduled_start"),
                    end=assignment.get("scheduled_end"),
                    severity="error",
                    blocking=True,
                    message="Panel member already has an interview in this window.",
                    message_ar="عضو اللجنة لديه مقابلة في هذه الفترة.",
                    attendee_role="required",
                    extra={
                        "interview_id": str(assignment.get("interview_id") or ""),
                        "privacy_safe": True,
                    },
                )
            )
    return out


def evaluate_conflicts(
    cur: Any,
    legacy: Any,
    *,
    company_code: str,
    start: datetime | str,
    end: datetime | str,
    timezone_name: str | None = None,
    all_day: bool = False,
    organizer_user_id: str | None = None,
    attendees: Sequence[Mapping[str, Any]] | None = None,
    exclude_event_id: str | None = None,
    # Interview fold-in
    app_key: str | None = None,
    panel: list[dict[str, Any]] | None = None,
    exclude_interview_id: str | None = None,
    include_interview_legacy: bool = True,
    include_calendar_events: bool = True,
) -> dict[str, Any]:
    start_dt = _parse_dt(start)
    end_dt = _parse_dt(end)
    if not start_dt or not end_dt or end_dt < start_dt:
        return {"ok": True, "conflicts": [], "blocking": [], "warnings": []}

    company = _text(company_code).upper()
    policy = company_work_policy(legacy, company)
    tz_name = _text(timezone_name) or policy["timezone"]
    roles = _attendee_role_map(attendees)
    user_ids = sorted(set(roles.keys()) | ({_text(organizer_user_id)} if _text(organizer_user_id) else set()))
    if _text(organizer_user_id) and _text(organizer_user_id) not in roles:
        roles[_text(organizer_user_id)] = "required"

    conflicts: list[dict[str, Any]] = []

    if include_calendar_events and user_ids:
        conflicts.extend(
            check_calendar_attendee_overlaps(
                cur,
                company_code=company,
                start=start_dt,
                end=end_dt,
                user_ids=user_ids,
                role_by_user=roles,
                exclude_event_id=exclude_event_id,
                organizer_user_id=organizer_user_id,
            )
        )

    if include_interview_legacy:
        # Build panel from attendees when not provided.
        panel_rows = panel
        if panel_rows is None and attendees:
            panel_rows = []
            for a in attendees:
                uid = _text(a.get("user_id"))
                if not uid:
                    continue
                panel_rows.append(
                    {
                        "assignee_user_id": uid,
                        "assignee_email": _text(a.get("email")),
                        "panel_role": _text(a.get("role")) or "required",
                        "is_required": _text(a.get("role")).lower() != "optional",
                    }
                )
        conflicts.extend(
            check_interview_legacy_conflicts(
                cur,
                company_code=company,
                app_key=app_key,
                start=start_dt,
                end=end_dt,
                panel=panel_rows,
                exclude_interview_id=exclude_interview_id,
            )
        )

    conflicts.extend(
        check_leave_overlaps(
            cur,
            company_code=company,
            start=start_dt,
            end=end_dt,
            user_ids=user_ids,
            role_by_user=roles,
            blocking=bool(policy.get("leave_overlap_blocking")),
        )
    )
    conflicts.extend(
        check_shift_overlaps(
            cur,
            company_code=company,
            start=start_dt,
            end=end_dt,
            user_ids=user_ids,
            role_by_user=roles,
            timezone_name=tz_name,
            blocking=bool(policy.get("shift_overlap_blocking")),
        )
    )
    conflicts.extend(
        check_working_hours(
            start=start_dt,
            end=end_dt,
            timezone_name=tz_name,
            policy=policy,
            all_day=all_day,
            user_ids=user_ids,
        )
    )

    # De-dupe by (type, affected id, conflicting id / start)
    seen: set[str] = set()
    unique: list[dict[str, Any]] = []
    for c in conflicts:
        key = f"{c.get('type')}:{c.get('affected_ref', {}).get('id')}:{c.get('conflicting_event_id') or c.get('interview_id') or c.get('start_at')}"
        if key in seen:
            continue
        seen.add(key)
        unique.append(c)

    blocking = [c for c in unique if c.get("blocking")]
    warnings = [c for c in unique if not c.get("blocking")]
    return {
        "ok": not blocking,
        "conflicts": unique,
        "blocking": blocking,
        "warnings": warnings,
        "blocking_count": len(blocking),
        "warning_count": len(warnings),
    }


def require_no_blocking_conflicts(
    cur: Any,
    legacy: Any,
    *,
    company_code: str,
    start: Any,
    end: Any,
    timezone_name: str | None = None,
    all_day: bool = False,
    organizer_user_id: str | None = None,
    attendees: Sequence[Mapping[str, Any]] | None = None,
    exclude_event_id: str | None = None,
    app_key: str | None = None,
    panel: list[dict[str, Any]] | None = None,
    exclude_interview_id: str | None = None,
    override_conflicts: bool = False,
    override_reason: str | None = None,
    actor_permissions: Iterable[Any] | None = None,
    include_interview_legacy: bool = True,
    include_calendar_events: bool = True,
) -> dict[str, Any]:
    """Evaluate conflicts; raise SchedulingConflictError unless override is authorized."""
    result = evaluate_conflicts(
        cur,
        legacy,
        company_code=company_code,
        start=start,
        end=end,
        timezone_name=timezone_name,
        all_day=all_day,
        organizer_user_id=organizer_user_id,
        attendees=attendees,
        exclude_event_id=exclude_event_id,
        app_key=app_key,
        panel=panel,
        exclude_interview_id=exclude_interview_id,
        include_interview_legacy=include_interview_legacy,
        include_calendar_events=include_calendar_events,
    )
    blocking = result.get("blocking") or []
    if not blocking:
        return {**result, "overridden": False}

    perms = {_text(p) for p in (actor_permissions or []) if _text(p)}
    reason = _text(override_reason)
    if override_conflicts:
        if "calendar.conflict_override" not in perms:
            raise SchedulingConflictError(
                result["conflicts"],
                message="Conflict override requires calendar.conflict_override permission.",
                message_ar="تجاوز التعارض يتطلب صلاحية تجاوز تعارض التقويم.",
            )
        if not reason:
            raise SchedulingConflictError(
                result["conflicts"],
                message="override_reason is required when override_conflicts=true.",
                message_ar="سبب التجاوز مطلوب عند تفعيل تجاوز التعارضات.",
            )
        return {**result, "overridden": True, "override_reason": reason}

    raise SchedulingConflictError(result["conflicts"])


def record_conflict_override_audit(
    cur: Any,
    legacy: Any,
    *,
    company_code: str,
    event_id: str | None,
    actor_user_id: str,
    conflicts: Sequence[Mapping[str, Any]],
    override_reason: str,
    version: int | None = None,
    request_id: str | None = None,
    source: str = "calendar",
) -> None:
    """Append-only audit of conflict override (calendar_event_audit when event_id known)."""
    snapshot = {
        "override_reason": _text(override_reason),
        "conflicts": list(conflicts),
        "version": version,
        "source": source,
        "recorded_at": datetime.now(timezone.utc).isoformat(),
    }
    if event_id:
        cur.execute(
            """
            INSERT INTO calendar_event_audit
              (audit_id, event_id, company_code, actor_user_id, action, before, after, request_id)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
            """,
            (
                str(uuid4()),
                event_id,
                _text(company_code).upper(),
                _text(actor_user_id) or None,
                "conflict_override",
                legacy.Json({}) if hasattr(legacy, "Json") else {},
                legacy.Json(snapshot) if hasattr(legacy, "Json") else snapshot,
                request_id,
            ),
        )
    # Best-effort secondary admin audit — never abort the Interview/Calendar TX.
    try:
        cur.execute("SAVEPOINT calendar_conflict_override_admin_audit")
        cur.execute(
            """
            INSERT INTO admin_audit_log (company_code, actor_user_id, action, summary, target_type, target, details)
            VALUES (%s,%s,%s,%s,%s,%s,%s)
            """,
            (
                _text(company_code).upper(),
                _text(actor_user_id) or None,
                "calendar_conflict_override",
                f"Overrode {len(conflicts)} scheduling conflict(s).",
                "calendar_event" if event_id else "scheduling",
                event_id,
                legacy.Json(snapshot) if hasattr(legacy, "Json") else snapshot,
            ),
        )
        cur.execute("RELEASE SAVEPOINT calendar_conflict_override_admin_audit")
    except Exception:
        try:
            cur.execute("ROLLBACK TO SAVEPOINT calendar_conflict_override_admin_audit")
        except Exception:
            pass
