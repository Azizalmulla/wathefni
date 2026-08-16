#!/usr/bin/env python3
"""R5E Learning product surfaces — thin composition over frozen Wave 6 C2.

HTTP and clients are adapters. Catalog, assignment, enrollment, attendance,
completion, and certification stay domain-authoritative. This module never
invents a second Learning model, never silently closes Wave 4 C3 development,
and never auto-verifies competency or Talent judgments.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Iterable, Mapping
import json

import learning_development_c2 as c2

PHASE = "learning_surfaces_r5e"
CONTRACT_VERSION = "learning_surfaces_v1"
PASS_STAMP = "PRODUCTION_READINESS_R5E_LEARNING_SURFACE_FULL_PASS"
COMMERCIAL_MODULE_KEY = "learning"

EMPLOYEE_FORBIDDEN_KEYS = frozenset(
    {
        "hr_admin",
        "population_rule",
        "enabled_by_phone",
        "disabled_at",
        "catalog_authoring",
        "mandatory_policies_admin",
        "other_employee_keys",
    }
)


def honesty_payload(*, company_code: str | None = None) -> dict[str, Any]:
    return {
        "phase": PHASE,
        "contract_version": CONTRACT_VERSION,
        "pass_stamp": PASS_STAMP,
        "commercial_module_key": COMMERCIAL_MODULE_KEY,
        "canonical_authority": ("learning_development_c2",),
        "assignment_is_not_enrollment": True,
        "enrollment_is_not_completion": True,
        "attendance_is_not_completion": True,
        "completion_is_not_certification": True,
        "course_completion_is_not_competency_verification": True,
        "overdue_is_not_automatic_failure": True,
        "request_is_not_approval": True,
        "approval_is_not_enrollment": True,
        "performance_optional": True,
        "talent_optional": True,
        "job_architecture_optional": True,
        "no_duplicate_skills_authority": True,
        "no_learning_talent_score": True,
        "no_auto_hipo": True,
        "c3_development_remains_canonical": True,
        "learning_completion_does_not_silently_close_development": True,
        "external_lms_not_required": True,
        "company_code": c2.company_code_norm(company_code) if company_code else None,
        **c2.honesty_payload(company_code=company_code),
    }


def strip_employee_admin(value: Any) -> Any:
    if isinstance(value, Mapping):
        out: dict[str, Any] = {}
        for key, item in value.items():
            if str(key).strip().lower() in EMPLOYEE_FORBIDDEN_KEYS:
                continue
            out[str(key)] = strip_employee_admin(item)
        return out
    if isinstance(value, list):
        return [strip_employee_admin(item) for item in value]
    return value


def ensure_schema(cur: Any) -> None:
    c2.ensure_learning_development_c2_schema(cur)


def _upsert_company_module(cur: Any, company: str, enabled: bool) -> None:
    cur.execute(
        """
        INSERT INTO company_modules (company_code, module_key, enabled, source, settings, updated_at)
        VALUES (%s, 'learning', %s, 'learning_surfaces', '{}'::jsonb, now())
        ON CONFLICT (company_code, module_key)
        DO UPDATE SET enabled=EXCLUDED.enabled, source='learning_surfaces', updated_at=now()
        """,
        (company, bool(enabled)),
    )


def sync_catalog_entitlement(
    cur: Any,
    *,
    company_code: str,
    actor_phone: str,
    enabled: bool,
    reason: str = "sync learning catalog entitlement",
) -> dict[str, Any]:
    ensure_schema(cur)
    company = c2.company_code_norm(company_code)
    if enabled:
        result = c2.enable_company_learning(
            cur, company_code=company, actor_phone=actor_phone, reason=reason
        )
    else:
        result = c2.disable_company_learning(
            cur, company_code=company, actor_phone=actor_phone, reason=reason
        )
    if result.get("ok"):
        _upsert_company_module(cur, company, bool(enabled))
    return {
        "ok": bool(result.get("ok")),
        "company_code": company,
        "enabled": bool(enabled),
        "history_preserved": True,
        "result": result,
        **honesty_payload(company_code=company),
    }


def _row(value: Any) -> dict[str, Any]:
    return dict(value) if value else {}


def _scope_sql(column: str, scope_keys: Iterable[str] | None) -> tuple[str, list[Any]]:
    keys = [str(k) for k in (scope_keys or []) if str(k).strip()]
    if not keys:
        return "", []
    return f" AND {column} = ANY(%s)", [keys]


def _module_on(cur: Any, company: str, key: str) -> bool:
    cur.execute(
        """
        SELECT 1 FROM company_modules
         WHERE company_code=%s AND module_key=%s AND enabled IS TRUE
         LIMIT 1
        """,
        (company, key),
    )
    return bool(cur.fetchone())


def _as_meta(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return dict(value)
    if isinstance(value, str) and value.strip():
        try:
            parsed = json.loads(value)
            return dict(parsed) if isinstance(parsed, dict) else {}
        except Exception:
            return {}
    return {}


def decorate_assignment(assignment: dict[str, Any], *, today=None) -> dict[str, Any]:
    row = dict(assignment)
    derived = c2.assignment_derived_state(row, today=today)
    meta = _as_meta(row.get("metadata"))
    enrolled = bool(row.get("offering_id")) or str(row.get("source") or "") == "employee_requested"
    attended = bool(meta.get("attended"))
    completed = str(row.get("status") or "") == "completed"
    row["derived"] = derived
    row["enrolled"] = enrolled
    row["attended"] = attended
    row["completed"] = completed
    row["assignment_is_not_enrollment"] = not enrolled or True
    row["enrollment_is_not_completion"] = enrolled and not completed
    row["attendance_is_not_completion"] = attended and not completed
    row["failed"] = False
    return row


def decorate_certification(cert: dict[str, Any], *, warning_days: int = 30, today=None) -> dict[str, Any]:
    row = dict(cert)
    row["derived"] = c2.certification_derived_status(row, today=today, warning_days=warning_days)
    row["course_completion_is_not_certification"] = True
    return row


def workspace_summary(
    cur: Any,
    *,
    company_code: str,
    actor_role: str,
    manager_scope_keys: list[str] | None = None,
) -> dict[str, Any]:
    ensure_schema(cur)
    company = c2.company_code_norm(company_code)
    if not c2.module_enabled_for_company(cur, company):
        return {
            "ok": True,
            "company_code": company,
            "enabled": False,
            "resource_state": "unavailable",
            "counts": None,
            "company_wide": False,
            **honesty_payload(company_code=company),
        }

    role = str(actor_role or "").strip().lower()
    scope = list(manager_scope_keys or []) if role == "manager" else None
    extra, params = _scope_sql("employee_key", scope)
    if role == "manager" and not extra:
        return {
            "ok": True,
            "company_code": company,
            "enabled": True,
            "resource_state": "empty",
            "counts": {
                "active_assignments": 0,
                "overdue_mandatory": 0,
                "upcoming_sessions": 0,
                "expiring_certificates": 0,
                "pending_requests": 0,
            },
            "company_wide": False,
            "scope_empty": True,
            **honesty_payload(company_code=company),
        }

    cur.execute(
        f"""
        SELECT COUNT(*) AS n FROM ld_assignments
         WHERE company_code=%s AND status IN ('assigned','in_progress') {extra}
        """,
        [company, *params],
    )
    active = int((_row(cur.fetchone()).get("n") or 0))

    cur.execute(
        f"""
        SELECT COUNT(*) AS n FROM ld_assignments
         WHERE company_code=%s AND required IS TRUE
           AND status IN ('assigned','in_progress')
           AND due_date IS NOT NULL AND due_date < CURRENT_DATE {extra}
        """,
        [company, *params],
    )
    overdue = int((_row(cur.fetchone()).get("n") or 0))

    cur.execute(
        """
        SELECT COUNT(*) AS n FROM ld_offerings
         WHERE company_code=%s AND status='scheduled'
           AND (starts_at IS NULL OR starts_at >= now())
        """,
        (company,),
    )
    upcoming = int((_row(cur.fetchone()).get("n") or 0))

    settings = c2._settings(cur, company)
    warning = int(settings.get("expiry_warning_days") or 30)
    extra_c, params_c = _scope_sql("employee_key", scope)
    cur.execute(
        f"""
        SELECT COUNT(*) AS n FROM ld_certifications
         WHERE company_code=%s AND status='valid'
           AND expires_on IS NOT NULL
           AND expires_on <= CURRENT_DATE + (%s * INTERVAL '1 day')
           AND expires_on >= CURRENT_DATE {extra_c}
        """,
        [company, warning, *params_c],
    )
    expiring = int((_row(cur.fetchone()).get("n") or 0))

    extra_r, params_r = _scope_sql("employee_key", scope)
    cur.execute(
        f"""
        SELECT COUNT(*) AS n FROM ld_learning_requests
         WHERE company_code=%s AND status='requested' {extra_r}
        """,
        [company, *params_r],
    )
    pending = int((_row(cur.fetchone()).get("n") or 0))

    return {
        "ok": True,
        "company_code": company,
        "enabled": True,
        "resource_state": "ready",
        "counts": {
            "active_assignments": active,
            "overdue_mandatory": overdue,
            "upcoming_sessions": upcoming,
            "expiring_certificates": expiring,
            "pending_requests": pending,
        },
        "company_wide": role != "manager",
        "performance_on": _module_on(cur, company, "performance"),
        "talent_on": _module_on(cur, company, "talent"),
        "job_architecture_on": _module_on(cur, company, "job_architecture"),
        **honesty_payload(company_code=company),
    }


def list_catalog(
    cur: Any,
    *,
    company_code: str,
    published_only: bool = False,
    programs_only: bool = False,
    limit: int = 200,
    offset: int = 0,
) -> dict[str, Any]:
    ensure_schema(cur)
    company = c2.company_code_norm(company_code)
    where = ["company_code=%s"]
    params: list[Any] = [company]
    if published_only:
        where.append("status='published'")
    if programs_only:
        where.append("item_type='program'")
    cur.execute(f"SELECT COUNT(*) AS n FROM ld_learning_items WHERE {' AND '.join(where)}", params)
    total = int((_row(cur.fetchone()).get("n") or 0))
    cur.execute(
        f"""
        SELECT * FROM ld_learning_items
         WHERE {' AND '.join(where)}
         ORDER BY updated_at DESC
         LIMIT %s OFFSET %s
        """,
        [*params, max(1, min(int(limit or 200), 400)), max(0, int(offset or 0))],
    )
    items = [_row(r) for r in (cur.fetchall() or [])]
    return {
        "ok": True,
        "items": items,
        "total": total,
        "resource_state": "empty" if total == 0 else "ready",
        **honesty_payload(company_code=company),
    }


def list_program_children(cur: Any, *, company_code: str, program_item_id: str) -> dict[str, Any]:
    ensure_schema(cur)
    company = c2.company_code_norm(company_code)
    cur.execute(
        """
        SELECT p.*, i.code, i.title_en, i.title_ar, i.item_type, i.status
          FROM ld_program_items p
          JOIN ld_learning_items i ON i.item_id=p.child_item_id
         WHERE p.company_code=%s AND p.program_item_id_parent=%s
         ORDER BY p.sequence_no NULLS LAST, i.code
        """,
        (company, program_item_id),
    )
    return {
        "ok": True,
        "children": [_row(r) for r in (cur.fetchall() or [])],
        **honesty_payload(company_code=company),
    }


def list_assignments(
    cur: Any,
    *,
    company_code: str,
    actor_role: str = "hr",
    manager_scope_keys: list[str] | None = None,
    employee_key: str | None = None,
    limit: int = 200,
) -> dict[str, Any]:
    ensure_schema(cur)
    company = c2.company_code_norm(company_code)
    where = ["a.company_code=%s"]
    params: list[Any] = [company]
    if actor_role == "manager":
        extra, extra_params = _scope_sql("a.employee_key", manager_scope_keys)
        if not extra:
            return {
                "ok": True,
                "assignments": [],
                "total": 0,
                "resource_state": "empty",
                "scope_empty": True,
                **honesty_payload(company_code=company),
            }
        where.append(extra.replace(" AND ", "", 1))
        params.extend(extra_params)
    if employee_key:
        where.append("a.employee_key=%s")
        params.append(employee_key)
    cur.execute(f"SELECT COUNT(*) AS n FROM ld_assignments a WHERE {' AND '.join(where)}", params)
    total = int((_row(cur.fetchone()).get("n") or 0))
    cur.execute(
        f"""
        SELECT a.*, i.code AS item_code, i.title_en, i.title_ar, i.item_type, i.delivery_mode
          FROM ld_assignments a
          JOIN ld_learning_items i ON i.item_id=a.item_id
         WHERE {' AND '.join(where)}
         ORDER BY a.assigned_at DESC, a.updated_at DESC
         LIMIT %s
        """,
        [*params, max(1, min(int(limit or 200), 400))],
    )
    rows = [decorate_assignment(_row(r)) for r in (cur.fetchall() or [])]
    return {
        "ok": True,
        "assignments": rows,
        "total": total,
        "resource_state": "empty" if total == 0 else "ready",
        **honesty_payload(company_code=company),
    }


def list_requests(
    cur: Any,
    *,
    company_code: str,
    actor_role: str = "hr",
    manager_scope_keys: list[str] | None = None,
    employee_key: str | None = None,
    limit: int = 200,
) -> dict[str, Any]:
    ensure_schema(cur)
    company = c2.company_code_norm(company_code)
    where = ["r.company_code=%s"]
    params: list[Any] = [company]
    if actor_role == "manager":
        extra, extra_params = _scope_sql("r.employee_key", manager_scope_keys)
        if not extra:
            return {"ok": True, "requests": [], "total": 0, "resource_state": "empty", "scope_empty": True, **honesty_payload(company_code=company)}
        where.append(extra.replace(" AND ", "", 1))
        params.extend(extra_params)
    if employee_key:
        where.append("r.employee_key=%s")
        params.append(employee_key)
    cur.execute(f"SELECT COUNT(*) AS n FROM ld_learning_requests r WHERE {' AND '.join(where)}", params)
    total = int((_row(cur.fetchone()).get("n") or 0))
    cur.execute(
        f"""
        SELECT r.*, i.code AS item_code, i.title_en, i.title_ar
          FROM ld_learning_requests r
          JOIN ld_learning_items i ON i.item_id=r.item_id
         WHERE {' AND '.join(where)}
         ORDER BY r.requested_at DESC
         LIMIT %s
        """,
        [*params, max(1, min(int(limit or 200), 400))],
    )
    return {
        "ok": True,
        "requests": [_row(r) for r in (cur.fetchall() or [])],
        "total": total,
        "resource_state": "empty" if total == 0 else "ready",
        "request_is_not_approval": True,
        "approval_is_not_enrollment": True,
        **honesty_payload(company_code=company),
    }


def list_sessions(
    cur: Any,
    *,
    company_code: str,
    offering_id: str | None = None,
    limit: int = 200,
) -> dict[str, Any]:
    ensure_schema(cur)
    company = c2.company_code_norm(company_code)
    where = ["o.company_code=%s"]
    params: list[Any] = [company]
    if offering_id:
        where.append("o.offering_id=%s")
        params.append(offering_id)
    cur.execute(
        f"""
        SELECT o.*, i.code AS item_code, i.title_en, i.title_ar,
               (SELECT COUNT(*) FROM ld_assignments a
                 WHERE a.offering_id=o.offering_id AND a.status <> 'cancelled') AS enrolled_count
          FROM ld_offerings o
          JOIN ld_learning_items i ON i.item_id=o.item_id
         WHERE {' AND '.join(where)}
         ORDER BY o.starts_at NULLS LAST, o.created_at DESC
         LIMIT %s
        """,
        [*params, max(1, min(int(limit or 200), 400))],
    )
    sessions = []
    for raw in cur.fetchall() or []:
        row = _row(raw)
        capacity = row.get("capacity")
        enrolled = int(row.get("enrolled_count") or 0)
        row["capacity_remaining"] = None if capacity is None else max(0, int(capacity) - enrolled)
        row["enrolled_is_not_attended"] = True
        sessions.append(row)
    return {
        "ok": True,
        "sessions": sessions,
        "total": len(sessions),
        "resource_state": "empty" if not sessions else "ready",
        **honesty_payload(company_code=company),
    }


def session_detail(
    cur: Any,
    *,
    company_code: str,
    offering_id: str,
    employee_key: str | None = None,
) -> dict[str, Any]:
    listed = list_sessions(cur, company_code=company_code, offering_id=offering_id, limit=1)
    sessions = listed.get("sessions") or []
    if not sessions:
        return {"ok": False, "error": "session_not_found"}
    session = sessions[0]
    company = c2.company_code_norm(company_code)
    where = ["company_code=%s", "offering_id=%s"]
    params: list[Any] = [company, offering_id]
    if employee_key:
        where.append("employee_key=%s")
        params.append(employee_key)
    cur.execute(
        f"SELECT * FROM ld_assignments WHERE {' AND '.join(where)} ORDER BY assigned_at DESC",
        params,
    )
    participants = [decorate_assignment(_row(r)) for r in (cur.fetchall() or [])]
    return {
        "ok": True,
        "session": session,
        "participants": participants,
        "enrolled_is_not_attended": True,
        "attended_is_not_completed": True,
        **honesty_payload(company_code=company),
    }


def list_completions(
    cur: Any,
    *,
    company_code: str,
    actor_role: str = "hr",
    manager_scope_keys: list[str] | None = None,
    employee_key: str | None = None,
    limit: int = 200,
) -> dict[str, Any]:
    ensure_schema(cur)
    company = c2.company_code_norm(company_code)
    where = ["c.company_code=%s"]
    params: list[Any] = [company]
    if actor_role == "manager":
        extra, extra_params = _scope_sql("c.employee_key", manager_scope_keys)
        if not extra:
            return {"ok": True, "completions": [], "total": 0, "resource_state": "empty", **honesty_payload(company_code=company)}
        where.append(extra.replace(" AND ", "", 1))
        params.extend(extra_params)
    if employee_key:
        where.append("c.employee_key=%s")
        params.append(employee_key)
    cur.execute(
        f"""
        SELECT c.*, i.title_en, i.title_ar
          FROM ld_completions c
          JOIN ld_learning_items i ON i.item_id=c.item_id
         WHERE {' AND '.join(where)}
         ORDER BY c.completed_at DESC
         LIMIT %s
        """,
        [*params, max(1, min(int(limit or 200), 400))],
    )
    rows = [_row(r) for r in (cur.fetchall() or [])]
    for row in rows:
        row["skill_auto_verified"] = False
        row["competency_auto_verified"] = False
        row["completion_is_not_certification"] = True
    return {
        "ok": True,
        "completions": rows,
        "total": len(rows),
        "resource_state": "empty" if not rows else "ready",
        **honesty_payload(company_code=company),
    }


def list_certificates(
    cur: Any,
    *,
    company_code: str,
    actor_role: str = "hr",
    manager_scope_keys: list[str] | None = None,
    employee_key: str | None = None,
    limit: int = 200,
) -> dict[str, Any]:
    ensure_schema(cur)
    company = c2.company_code_norm(company_code)
    settings = c2._settings(cur, company)
    warning = int(settings.get("expiry_warning_days") or 30)
    where = ["company_code=%s"]
    params: list[Any] = [company]
    if actor_role == "manager":
        extra, extra_params = _scope_sql("employee_key", manager_scope_keys)
        if not extra:
            return {"ok": True, "certificates": [], "total": 0, "resource_state": "empty", **honesty_payload(company_code=company)}
        where.append(extra.replace(" AND ", "", 1))
        params.extend(extra_params)
    if employee_key:
        where.append("employee_key=%s")
        params.append(employee_key)
    cur.execute(
        f"""
        SELECT * FROM ld_certifications
         WHERE {' AND '.join(where)}
         ORDER BY issued_on DESC
         LIMIT %s
        """,
        [*params, max(1, min(int(limit or 200), 400))],
    )
    rows = [decorate_certification(_row(r), warning_days=warning) for r in (cur.fetchall() or [])]
    return {
        "ok": True,
        "certificates": rows,
        "total": len(rows),
        "resource_state": "empty" if not rows else "ready",
        "expiry_does_not_erase_history": True,
        **honesty_payload(company_code=company),
    }


def list_mandatory(
    cur: Any,
    *,
    company_code: str,
    limit: int = 100,
) -> dict[str, Any]:
    ensure_schema(cur)
    company = c2.company_code_norm(company_code)
    cur.execute(
        """
        SELECT p.*, i.code AS item_code, i.title_en AS item_title_en
          FROM ld_mandatory_policies p
          JOIN ld_learning_items i ON i.item_id=p.item_id
         WHERE p.company_code=%s
         ORDER BY p.created_at DESC
         LIMIT %s
        """,
        (company, max(1, min(int(limit or 100), 200))),
    )
    return {
        "ok": True,
        "policies": [_row(r) for r in (cur.fetchall() or [])],
        "generation_is_idempotent": True,
        **honesty_payload(company_code=company),
    }


def list_development_links(
    cur: Any,
    *,
    company_code: str,
    employee_key: str | None = None,
    limit: int = 100,
) -> dict[str, Any]:
    ensure_schema(cur)
    company = c2.company_code_norm(company_code)
    where = ["company_code=%s"]
    params: list[Any] = [company]
    if employee_key:
        where.append(
            """
            (assignment_id IN (SELECT assignment_id FROM ld_assignments WHERE company_code=%s AND employee_key=%s)
             OR completion_id IN (SELECT completion_id FROM ld_completions WHERE company_code=%s AND employee_key=%s))
            """
        )
        params.extend([company, employee_key, company, employee_key])
    cur.execute(
        f"""
        SELECT * FROM ld_development_fulfillment_links
         WHERE {' AND '.join(where)}
         ORDER BY created_at DESC
         LIMIT %s
        """,
        [*params, max(1, min(int(limit or 100), 200))],
    )
    rows = [_row(r) for r in (cur.fetchall() or [])]
    for row in rows:
        row["silently_closed_c3"] = False
        row["c3_remains_sole_development_authority"] = True
    return {
        "ok": True,
        "links": rows,
        "learning_completion_does_not_silently_close_development": True,
        **honesty_payload(company_code=company),
    }


def list_history(
    cur: Any,
    *,
    company_code: str,
    actor_role: str = "hr",
    manager_scope_keys: list[str] | None = None,
    employee_key: str | None = None,
    limit: int = 200,
) -> dict[str, Any]:
    ensure_schema(cur)
    company = c2.company_code_norm(company_code)
    where = ["company_code=%s"]
    params: list[Any] = [company]
    if employee_key:
        where.append("(detail->>'employee_key'=%s OR entity_id=%s)")
        params.extend([employee_key, employee_key])
    cur.execute(
        f"""
        SELECT * FROM ld_audit_events
         WHERE {' AND '.join(where)}
         ORDER BY created_at DESC
         LIMIT %s
        """,
        [*params, max(1, min(int(limit or 200), 400))],
    )
    events = [_row(r) for r in (cur.fetchall() or [])]
    completions = list_completions(
        cur,
        company_code=company,
        actor_role=actor_role,
        manager_scope_keys=manager_scope_keys,
        employee_key=employee_key,
        limit=limit,
    )
    certs = list_certificates(
        cur,
        company_code=company,
        actor_role=actor_role,
        manager_scope_keys=manager_scope_keys,
        employee_key=employee_key,
        limit=limit,
    )
    versions: list[dict[str, Any]] = []
    cur.execute(
        """
        SELECT * FROM ld_item_versions
         WHERE company_code=%s
         ORDER BY created_at DESC
         LIMIT %s
        """,
        (company, max(1, min(int(limit or 200), 200))),
    )
    versions = [_row(r) for r in (cur.fetchall() or [])]
    return {
        "ok": True,
        "events": events,
        "completions": completions.get("completions") or [],
        "certificates": certs.get("certificates") or [],
        "item_versions": versions,
        "later_policy_does_not_rewrite_history": True,
        **honesty_payload(company_code=company),
    }


def enroll_in_session(
    cur: Any,
    *,
    company_code: str,
    actor_phone: str,
    offering_id: str,
    employee_key: str,
    source: str = "hr_assigned",
    reason: str = "enroll in session",
) -> dict[str, Any]:
    ensure_schema(cur)
    company = c2.company_code_norm(company_code)
    cur.execute(
        "SELECT * FROM ld_offerings WHERE company_code=%s AND offering_id=%s",
        (company, offering_id),
    )
    offering = _row(cur.fetchone())
    if not offering:
        return {"ok": False, "error": "session_not_found"}
    cur.execute(
        """
        SELECT * FROM ld_assignments
         WHERE company_code=%s AND employee_key=%s AND offering_id=%s
           AND status NOT IN ('cancelled')
         LIMIT 1
        """,
        (company, employee_key, offering_id),
    )
    existing = _row(cur.fetchone())
    if existing:
        return {
            "ok": True,
            "assignment": decorate_assignment(existing),
            "already_enrolled": True,
            "created": False,
            "enrollment_is_not_completion": True,
            **honesty_payload(company_code=company),
        }
    capacity = offering.get("capacity")
    if capacity is not None:
        cur.execute(
            """
            SELECT COUNT(*) AS n FROM ld_assignments
             WHERE company_code=%s AND offering_id=%s AND status <> 'cancelled'
            """,
            (company, offering_id),
        )
        enrolled = int((_row(cur.fetchone()).get("n") or 0))
        if enrolled >= int(capacity):
            return {"ok": False, "error": "session_capacity_exceeded", "capacity": int(capacity)}
    assigned = c2.create_assignment(
        cur,
        company_code=company,
        actor_phone=actor_phone,
        employee_key=employee_key,
        item_id=str(offering["item_id"]),
        source=source,
        offering_id=offering_id,
        reason=reason,
        required=True,
    )
    if not assigned.get("ok"):
        return assigned
    return {
        **assigned,
        "assignment": decorate_assignment(assigned.get("assignment") or {}),
        "enrollment_is_not_completion": True,
        "attendance_is_not_completion": True,
        **honesty_payload(company_code=company),
    }


def record_session_attendance(
    cur: Any,
    *,
    company_code: str,
    actor_phone: str,
    offering_id: str,
    assignment_id: str,
    evidence_ref: str = "",
    evidence_payload: dict | None = None,
) -> dict[str, Any]:
    """Attendance metadata only — never fabricates completion."""
    ensure_schema(cur)
    company = c2.company_code_norm(company_code)
    ent = c2._require_enabled(cur, company)
    if not ent.get("ok"):
        return ent
    cur.execute(
        "SELECT * FROM ld_assignments WHERE company_code=%s AND assignment_id=%s",
        (company, assignment_id),
    )
    asn = _row(cur.fetchone())
    if not asn or str(asn.get("offering_id") or "") != str(offering_id):
        return {"ok": False, "error": "assignment_not_found"}
    meta = _as_meta(asn.get("metadata"))
    meta.update(
        {
            "attended": True,
            "attendance_recorded_at": datetime.now(timezone.utc).isoformat(),
            "attendance_evidence_ref": str(evidence_ref or ""),
            "attendance_evidence_payload": evidence_payload or {},
            "attendance_actor_phone": c2._digits(actor_phone),
            "attendance_is_not_completion": True,
        }
    )
    cur.execute(
        """
        UPDATE ld_assignments
           SET metadata=%s::jsonb, updated_at=now()
         WHERE assignment_id=%s
         RETURNING *
        """,
        (json.dumps(meta), assignment_id),
    )
    row = decorate_assignment(_row(cur.fetchone()))
    return {
        "ok": True,
        "assignment": row,
        "attended": True,
        "completed": False,
        "attendance_is_not_completion": True,
        **honesty_payload(company_code=company),
    }


def decide_request(
    cur: Any,
    *,
    company_code: str,
    actor_phone: str,
    request_id: str,
    approve: bool,
    reason: str = "",
) -> dict[str, Any]:
    if not approve and not str(reason or "").strip():
        return {"ok": False, "error": "rejection_reason_required"}
    result = c2.decide_learning_request(
        cur,
        company_code=company_code,
        actor_phone=actor_phone,
        request_id=request_id,
        approve=approve,
        reason=reason,
    )
    if result.get("ok"):
        result.update(honesty_payload(company_code=company_code))
        result["request_is_not_approval"] = True
        result["approval_is_not_enrollment"] = True
        result["enrollment_is_not_completion"] = True
    return result


def record_completion_guarded(
    cur: Any,
    *,
    company_code: str,
    actor_phone: str,
    assignment_id: str,
    evidence_source: str,
    evidence_ref: str = "",
    evidence_payload: dict | None = None,
    provider_id: str | None = None,
    actor_role: str = "hr",
) -> dict[str, Any]:
    ensure_schema(cur)
    company = c2.company_code_norm(company_code)
    cur.execute(
        "SELECT * FROM ld_assignments WHERE company_code=%s AND assignment_id=%s",
        (company, assignment_id),
    )
    asn = _row(cur.fetchone())
    if not asn:
        return {"ok": False, "error": "assignment_not_found"}
    if str(actor_role or "").strip().lower() == "employee":
        settings = c2._settings(cur, company)
        item_reqs = {}
        cur.execute(
            "SELECT completion_requirements FROM ld_learning_items WHERE company_code=%s AND item_id=%s",
            (company, asn.get("item_id")),
        )
        item = _row(cur.fetchone())
        item_reqs = _as_meta(item.get("completion_requirements"))
        allow = bool(
            (_as_meta(settings.get("metadata")).get("employee_self_attestation_allowed"))
            or item_reqs.get("employee_self_attestation_allowed")
        )
        mandatory = bool(asn.get("required")) or str(asn.get("source") or "") == "mandatory_policy"
        if mandatory and not allow:
            return {
                "ok": False,
                "error": "employee_self_completion_forbidden",
                "mandatory": True,
                "self_attestation_allowed": False,
            }
    result = c2.record_completion(
        cur,
        company_code=company,
        actor_phone=actor_phone,
        assignment_id=assignment_id,
        evidence_source=evidence_source,
        evidence_ref=evidence_ref,
        evidence_payload=evidence_payload,
        provider_id=provider_id,
    )
    if result.get("ok"):
        result.update(honesty_payload(company_code=company))
        result["skill_auto_verified"] = False
        result["competency_auto_verified"] = False
        result["completion_is_not_certification"] = True
    return result


def optional_context(
    cur: Any,
    *,
    company_code: str,
    employee_key: str | None = None,
) -> dict[str, Any]:
    """Read-only enrichment. Never writes Talent / Performance / JA."""
    company = c2.company_code_norm(company_code)
    talent_on = _module_on(cur, company, "talent")
    perf_on = _module_on(cur, company, "performance")
    ja_on = _module_on(cur, company, "job_architecture")
    talent_context: dict[str, Any] = {"available": talent_on, "auto_hipo": False, "learning_talent_score": None}
    if talent_on and employee_key:
        try:
            cur.execute(
                """
                SELECT skill_code, name_en, name_ar, state, proficiency_level
                  FROM talent_skills
                 WHERE company_code=%s AND employee_key=%s AND status='active'
                 ORDER BY skill_code
                 LIMIT 50
                """,
                (company, employee_key),
            )
            talent_context["skill_gaps"] = [_row(r) for r in (cur.fetchall() or [])]
        except Exception:
            talent_context["skill_gaps"] = []
    return {
        "ok": True,
        "talent": talent_context,
        "performance": {"available": perf_on, "does_not_close_development": True},
        "job_architecture": {"available": ja_on, "no_learning_grade_hierarchy": True},
        "no_auto_hipo": True,
        "no_learning_talent_score": True,
        **honesty_payload(company_code=company),
    }


def employee_workspace(
    cur: Any,
    *,
    company_code: str,
    employee_key: str,
) -> dict[str, Any]:
    ensure_schema(cur)
    view = c2.employee_learning_view(cur, company_code=company_code, employee_key=employee_key)
    if not view.get("ok"):
        if view.get("error") == "learning_disabled_for_company":
            return {
                "ok": True,
                "resource_state": "unavailable",
                "enabled": False,
                "assignments": None,
                "certifications": None,
                "requests": None,
                "hr_admin_exposed": False,
                **honesty_payload(company_code=company_code),
            }
        return view
    company = c2.company_code_norm(company_code)
    assignments = [decorate_assignment(a) for a in (view.get("assignments") or [])]
    certs = [decorate_certification(c) for c in (view.get("certifications") or [])]
    catalog = list_catalog(cur, company_code=company, published_only=True, limit=100)
    requests = list_requests(cur, company_code=company, employee_key=employee_key, limit=50)
    completions = list_completions(cur, company_code=company, employee_key=employee_key, limit=50)
    upcoming = [
        a
        for a in assignments
        if a.get("offering_id") and str(a.get("status") or "") in {"assigned", "in_progress"}
    ]
    required = [a for a in assignments if a.get("required") and str(a.get("status") or "") in {"assigned", "in_progress"}]
    completed = [a for a in assignments if a.get("completed")]
    return strip_employee_admin(
        {
            "ok": True,
            "enabled": True,
            "resource_state": "ready",
            "employee_key": employee_key,
            "assignments": assignments,
            "required": required,
            "upcoming": upcoming,
            "completed": completed,
            "certifications": certs,
            "requests": requests.get("requests") or [],
            "catalog": catalog.get("items") or [],
            "completions": completions.get("completions") or [],
            "hr_admin_exposed": False,
            "context": optional_context(cur, company_code=company, employee_key=employee_key),
            **honesty_payload(company_code=company),
        }
    )


def manager_team_status(
    cur: Any,
    *,
    company_code: str,
    manager_scope_keys: list[str] | None,
) -> dict[str, Any]:
    ensure_schema(cur)
    keys = [str(k) for k in (manager_scope_keys or []) if str(k).strip()]
    view = c2.manager_learning_view(
        cur, company_code=company_code, manager_scope_employee_keys=keys
    )
    if not view.get("ok"):
        return view
    assignments = [decorate_assignment(a) for a in (view.get("assignments") or [])]
    return {
        "ok": True,
        "assignments": assignments,
        "scope_empty": bool(view.get("scope_empty")),
        "uses_canonical_manager_scope": True,
        "company_wide": False,
        **honesty_payload(company_code=company_code),
    }
