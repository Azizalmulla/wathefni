#!/usr/bin/env python3
"""Thin attendance-authority hooks for surgical production wiring (Wave 1C).

Keeps real employees on the legacy path when SYNTHETIC_ONLY=on.
Does not enable import/QR/GPS/kiosk/clocking UI.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any

import attendance_authority_wave1 as core

try:
    import attendance_authority_postgres as pg
except Exception:  # pragma: no cover
    pg = None  # type: ignore


def allowed_for(company: str, employee: dict[str, Any] | None) -> bool:
    return core.attendance_authority_allowed_for(company, employee)


def ensure_schema(cur: Any) -> None:
    core.ensure_attendance_authority_schema(cur)
    if pg is not None:
        pg.ensure_attendance_authority_postgres_schema(cur)


def _source_event_id(action: dict[str, Any] | None, *, prefix: str, employee_key: str, attendance_date: date) -> str:
    action = action or {}
    explicit = action.get("source_event_id") or action.get("idempotency_key") or action.get("event_id")
    if explicit:
        return str(explicit)
    digest = str(action.get("prompt_text") or action.get("query") or action.get("time") or "")
    return f"{prefix}:{employee_key}:{attendance_date.isoformat()}:{digest}"


def mirror_compat(
    upsert_attendance_record,
    cur: Any,
    *,
    company: str,
    employee: dict[str, Any],
    shift: dict[str, Any] | None,
    attendance_date: date,
    compat: dict[str, Any],
    created_by_phone: str | None,
    action: dict[str, Any] | None,
    Json: Any,
    json_safe: Any,
) -> dict[str, Any]:
    meta = compat.get("metadata") if isinstance(compat.get("metadata"), dict) else {}
    check_in = compat.get("check_in_at")
    check_out = compat.get("check_out_at")
    if check_in and not isinstance(check_in, datetime):
        check_in = datetime.fromisoformat(str(check_in).replace("Z", "+00:00"))
    if check_out and not isinstance(check_out, datetime):
        check_out = datetime.fromisoformat(str(check_out).replace("Z", "+00:00"))
    return upsert_attendance_record(
        cur,
        company=company,
        employee=employee,
        shift=shift,
        attendance_date=attendance_date,
        status=str(compat.get("status") or "pending"),
        check_in_at=check_in,
        check_out_at=check_out,
        notes=compat.get("notes"),
        source_text=str((action or {}).get("prompt_text") or (action or {}).get("query") or ""),
        created_by_phone=created_by_phone,
        action={
            **(action or {}),
            "authority_mirror": True,
            "projection_version": meta.get("projection_version"),
            "exception_state": meta.get("exception_state"),
            "authority": core.AUTHORITY_VERSION,
        },
    )


def try_check_in(
    *,
    app: Any,
    company: str,
    employee: dict[str, Any],
    shift: dict[str, Any],
    attendance_date: date,
    check_in_at: datetime,
    action: dict[str, Any],
    created_by_phone: str | None,
) -> dict[str, Any] | None:
    if not allowed_for(company, employee):
        return None
    svc = core.get_authority_service(company)
    authority = svc.ingest_punch(
        company_code=company,
        employee=employee,
        punched_at=check_in_at,
        direction="in",
        source=str(action.get("attendance_source") or "whatsapp"),
        source_event_id=_source_event_id(action, prefix="check_in", employee_key=str(employee.get("employee_key")), attendance_date=attendance_date),
        shift=shift,
        work_date=attendance_date,
        created_by_phone=created_by_phone,
        metadata={"action_type": "check_in_employee", "wave": "1c"},
    )
    if not authority.get("ok"):
        return {**authority, "employee": app.json_safe(employee), "action": action}
    with app.db_connect() as conn:
        with conn.cursor() as cur:
            attendance = mirror_compat(
                app.upsert_attendance_record,
                cur,
                company=company,
                employee=employee,
                shift=shift,
                attendance_date=attendance_date,
                compat=authority.get("compat") or {},
                created_by_phone=created_by_phone,
                action=action,
                Json=app.Json,
                json_safe=app.json_safe,
            )
            event_type = "checked_in_late" if int(attendance.get("late_minutes") or 0) > 0 else "checked_in"
            app.record_attendance_event(
                cur,
                attendance=attendance,
                company_code=company,
                event_type=event_type,
                payload={"action": action, "attendance": attendance, "shift": shift, "authority": authority},
                created_by_phone=created_by_phone,
            )
        conn.commit()
    return {
        "ok": True,
        "employee": app.json_safe(employee),
        "shift": app.json_safe(shift),
        "attendance": app.json_safe(attendance),
        "authority": app.json_safe(authority),
    }


def try_check_out(
    *,
    app: Any,
    company: str,
    employee: dict[str, Any],
    shift: dict[str, Any] | None,
    attendance_date: date,
    check_out_at: datetime,
    action: dict[str, Any],
    created_by_phone: str | None,
) -> dict[str, Any] | None:
    if not allowed_for(company, employee):
        return None
    work_date = attendance_date
    use_shift = shift
    if not use_shift:
        with app.db_connect() as conn:
            with conn.cursor() as cur:
                prev = attendance_date - timedelta(days=1)
                use_shift = app.active_shift_for_attendance(
                    cur,
                    company_code=company,
                    employee_key=str(employee.get("employee_key")),
                    attendance_date=prev,
                    shift_id=action.get("shift_id"),
                )
                if use_shift:
                    work_date = prev
    svc = core.get_authority_service(company)
    authority = svc.ingest_punch(
        company_code=company,
        employee=employee,
        punched_at=check_out_at,
        direction="out",
        source=str(action.get("attendance_source") or "whatsapp"),
        source_event_id=_source_event_id(action, prefix="check_out", employee_key=str(employee.get("employee_key")), attendance_date=work_date),
        shift=use_shift,
        work_date=work_date,
        created_by_phone=created_by_phone,
        metadata={"action_type": "check_out_employee", "wave": "1c"},
    )
    if not authority.get("ok"):
        return {**authority, "employee": app.json_safe(employee), "action": action}
    with app.db_connect() as conn:
        with conn.cursor() as cur:
            attendance = mirror_compat(
                app.upsert_attendance_record,
                cur,
                company=company,
                employee=employee,
                shift=use_shift,
                attendance_date=work_date,
                compat=authority.get("compat") or {},
                created_by_phone=created_by_phone,
                action=action,
                Json=app.Json,
                json_safe=app.json_safe,
            )
            app.record_attendance_event(
                cur,
                attendance=attendance,
                company_code=company,
                event_type="checked_out",
                payload={"action": action, "attendance": attendance, "shift": use_shift, "authority": authority},
                created_by_phone=created_by_phone,
            )
        conn.commit()
    return {
        "ok": True,
        "employee": app.json_safe(employee),
        "shift": app.json_safe(use_shift),
        "attendance": app.json_safe(attendance),
        "authority": app.json_safe(authority),
    }


def assert_cleanup_guc_not_in_app_paths(app_src: str) -> bool:
    """Production app request paths must never enable the cleanup GUC."""
    return "wathefni.allow_authority_cleanup" not in app_src
