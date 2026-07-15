"""HR-2A/HR-3 mobile-safe operator data adapters.

Thin DTO and confirmation adapters over the existing dashboard business logic.
No authority, tenant, scope, or mutation policy is implemented client-side.
"""

from __future__ import annotations

import hashlib
import hmac
import json
from datetime import timedelta
from typing import Any


MOBILE_CONFIRMATION_TTL = timedelta(minutes=10)
MOBILE_ACTIONS = {
    "approve_leave": "approve_leave_request",
    "reject_leave": "reject_leave_request",
    "shortlist": "shortlist_candidate",
    "reject": "reject_candidate",
    "hire": "hire_candidate",
    "review_onboarding": "onboarding_mark_item",
    "resolve_attendance": "correct_attendance_record",
    "approve_shift_swap": "approve_shift_swap",
    "reject_shift_swap": "reject_shift_swap",
    "review_compliance": "compliance_mark_reviewed",
}

MOBILE_DATA_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS dashboard_operator_mobile_confirmations (
  confirmation_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id uuid NOT NULL REFERENCES dashboard_users(user_id) ON DELETE CASCADE,
  session_id uuid REFERENCES dashboard_operator_mobile_sessions(session_id) ON DELETE SET NULL,
  company_code text NOT NULL,
  idempotency_key text NOT NULL,
  request_hash text NOT NULL,
  action_type text NOT NULL,
  target_type text NOT NULL,
  target_id text NOT NULL,
  expected_status text,
  safe_summary text NOT NULL,
  consequence text NOT NULL,
  args jsonb NOT NULL DEFAULT '{}'::jsonb,
  registry_action_hash text,
  registry_confirmation jsonb,
  status text NOT NULL DEFAULT 'preparing',
  result jsonb,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  expires_at timestamptz NOT NULL,
  completed_at timestamptz,
  UNIQUE (company_code, user_id, idempotency_key)
);
CREATE INDEX IF NOT EXISTS idx_mobile_confirmations_lookup
  ON dashboard_operator_mobile_confirmations(company_code, user_id, confirmation_id);
"""


def ensure_operator_mobile_data_schema(app_mod: Any) -> None:
    with app_mod.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(MOBILE_DATA_SCHEMA_SQL)
        conn.commit()


def _stable_hash(value: dict[str, Any]) -> str:
    encoded = json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def _actions(feature: dict[str, Any] | None) -> list[str]:
    return [str(item) for item in ((feature or {}).get("actions") or [])]


def _workspace_features(app_mod: Any, context: dict[str, Any], workspace: str) -> dict[str, Any]:
    if workspace == "hr":
        return app_mod._operator_mobile.build_hr_workspace_capabilities(app_mod, context)
    if workspace == "recruiting":
        return app_mod._operator_mobile.build_recruiting_workspace_capabilities(app_mod, context)
    return {}


def _require_mobile_feature_action(
    app_mod: Any,
    context: dict[str, Any],
    workspace: str,
    feature_name: str,
    action: str,
) -> dict[str, Any]:
    feature = _workspace_features(app_mod, context, workspace).get(feature_name) or {}
    if not feature.get("enabled") or action not in _actions(feature):
        reason = str(feature.get("reason") or "action_forbidden")
        code = reason if reason in {"module_disabled", "feature_disabled"} else "action_forbidden"
        raise app_mod.HTTPException(
            status_code=403,
            detail={"error": code, "message": "You do not have access to do that."},
        )
    return feature


def _iso(value: Any) -> Any:
    return value.isoformat() if hasattr(value, "isoformat") else value


def _employee_context(app_mod: Any, employee: dict[str, Any] | None) -> dict[str, Any]:
    row = employee if isinstance(employee, dict) else {}
    card = app_mod.posthire_employee_card(row) if row else {}
    return {
        "employee_key": card.get("employee_key"),
        "name": card.get("name") or "Employee",
        "position_title": card.get("position_title") or None,
        "department": card.get("department") or None,
        "employment_status": card.get("employment_status") or None,
    }


def _employee_identity(
    app_mod: Any,
    employee: dict[str, Any] | None,
    *,
    key: str | None = None,
    name: str | None = None,
    department: str | None = None,
) -> dict[str, Any]:
    if employee:
        card = _employee_context(app_mod, employee)
        return {
            "employee_key": card.get("employee_key"),
            "name": card.get("name"),
            "department": card.get("department"),
        }
    return {
        "employee_key": key,
        "name": name or "Employee",
        "department": department,
    }


def hr_task_mobile_item(row: dict[str, Any], *, actions: list[str]) -> dict[str, Any]:
    task_id = str(row.get("task_id") or "")
    return {
        "task_id": task_id,
        "task_type": row.get("task_type"),
        "source": row.get("source"),
        "title": row.get("title") or "HR task",
        "detail": row.get("detail"),
        "employee": {
            "employee_key": row.get("employee_key"),
            "name": row.get("employee_name") or None,
        },
        "status": row.get("status"),
        "priority": row.get("priority"),
        "created_at": _iso(row.get("created_at")),
        "updated_at": _iso(row.get("updated_at")),
        "allowed_actions": list(actions),
        "destination": f"/tasks/{task_id}",
    }


def mobile_hr_tasks(
    app_mod: Any,
    context: dict[str, Any],
    *,
    status: str = "open",
    offset: int = 0,
    limit: int = 30,
) -> dict[str, Any]:
    feature = _require_mobile_feature_action(app_mod, context, "hr", "hr_tasks", "read")
    result = app_mod.dashboard_hr_tasks(
        status=status,
        limit=max(1, min(int(limit or 30), 100)),
        offset=max(0, int(offset or 0)),
        context=context,
    )
    return {
        "ok": True,
        "items": [
            hr_task_mobile_item(row, actions=_actions(feature))
            for row in result.get("tasks") or []
        ],
        "open_count": int(result.get("open_count") or 0),
        "total": int(result.get("total") or 0),
        "offset": int(result.get("offset") or 0),
        "limit": int(result.get("limit") or limit),
        "status": status,
    }


def onboarding_mobile_item(
    app_mod: Any,
    row: dict[str, Any],
    *,
    actions: list[str],
) -> dict[str, Any]:
    employee_key = str(row.get("employee_key") or "")
    status = str(row.get("onboarding_status") or row.get("status") or "")
    return {
        "employee": _employee_identity(app_mod, row),
        "status": status,
        "pending_count": int(row.get("pending_count") or 0),
        "received_count": int(row.get("received_count") or 0),
        "updated_at": _iso(row.get("updated_at")),
        "allowed_actions": list(actions),
        "destination": f"/onboarding/{employee_key}",
    }


def onboarding_checklist_mobile_item(
    app_mod: Any,
    item: dict[str, Any],
    *,
    file_id: str | None,
    actions: list[str],
) -> dict[str, Any]:
    item_id = str(item.get("item_id") or "")
    status = str(item.get("status") or "")
    reviewable = status not in {"received", "complete", "completed", "verified", "waived"}
    return {
        "item_id": item_id,
        "label": item.get("label") or app_mod.item_display_label(item),
        "item_type": item.get("item_type"),
        "document_type": item.get("document_type"),
        "required": bool(item.get("required")),
        "status": status,
        "storage_status": item.get("storage_status"),
        "reminder_count": int(item.get("reminder_count") or 0),
        "last_reminded_at": _iso(item.get("last_reminded_at")),
        "updated_at": _iso(item.get("updated_at")),
        "has_file": bool(file_id),
        "preview_path": f"/dashboard/mobile/documents/files/{file_id}" if file_id else None,
        "download_path": (
            f"/dashboard/mobile/documents/files/{file_id}?disposition=attachment"
            if file_id
            else None
        ),
        "allowed_actions": [a for a in actions if a == "review"] if reviewable else [],
    }


def mobile_onboarding_list(
    app_mod: Any,
    context: dict[str, Any],
    *,
    offset: int = 0,
    limit: int = 30,
    search: str = "",
) -> dict[str, Any]:
    feature = _require_mobile_feature_action(app_mod, context, "hr", "onboarding_review", "read")
    result = app_mod.dashboard_posthire_onboarding(
        offset=max(0, int(offset or 0)),
        limit=max(1, min(int(limit or 30), 100)),
        search=str(search or ""),
        context=context,
    )
    return {
        "ok": True,
        "items": [
            onboarding_mobile_item(app_mod, row, actions=_actions(feature))
            for row in result.get("in_progress") or []
        ],
        "completed_count": int(result.get("completed_count") or 0),
        "total": int(result.get("total") or 0),
        "total_count": int(result.get("total_count") or 0),
        "limit": int(result.get("limit") or limit),
        "offset": int(result.get("offset") or 0),
        "has_more": bool(result.get("has_more")),
    }


def mobile_onboarding_detail(
    app_mod: Any,
    context: dict[str, Any],
    employee_key: str,
) -> dict[str, Any]:
    feature = _require_mobile_feature_action(app_mod, context, "hr", "onboarding_review", "read")
    result = app_mod.dashboard_posthire_onboarding_detail(employee_key, context=context)
    employee = app_mod.find_employee_by_key(employee_key, company_code=context["company_code"])
    index = result.get("document_index") if isinstance(result.get("document_index"), dict) else {}
    items = []
    for item in [*(result.get("pending") or []), *(result.get("received") or [])]:
        file_id = index.get(str(item.get("item_id") or "")) or index.get(
            str(item.get("document_type") or "")
        )
        items.append(
            onboarding_checklist_mobile_item(
                app_mod,
                item,
                file_id=str(file_id) if file_id else None,
                actions=_actions(feature),
            )
        )
    return {
        "ok": True,
        "onboarding": {
            "employee": _employee_identity(
                app_mod,
                employee,
                key=str(result.get("employee_key") or employee_key),
                name=result.get("name"),
            ),
            "status": result.get("status"),
            "required_total": int(result.get("required_total") or 0),
            "received_count": int(result.get("received_count") or 0),
            "pending_count": int(result.get("pending_count") or 0),
            "items": items,
            "allowed_actions": _actions(feature),
        },
    }


def compliance_mobile_item(
    app_mod: Any,
    row: dict[str, Any],
    *,
    actions: list[str],
) -> dict[str, Any]:
    employee_key = str(row.get("employee_key") or "")
    document_type = str(row.get("document_type") or "")
    file_id = str(row.get("file_id") or "")
    reviewable = str(row.get("status") or "") == "needs_review"
    return {
        "document_id": f"{employee_key}:{document_type}",
        "source": "compliance",
        "employee": _employee_identity(
            app_mod,
            None,
            key=employee_key,
            name=row.get("employee_name"),
            department=row.get("department"),
        ),
        "document_type": document_type,
        "label": row.get("document_label"),
        "status": row.get("status"),
        "status_label": row.get("status_label"),
        "tone": row.get("tone"),
        "expiry_date": _iso(row.get("expiry_date")),
        "days_until_expiry": row.get("days_until_expiry"),
        "last_checked_at": _iso(row.get("last_checked_at")),
        "last_reminded_at": _iso(row.get("last_reminded_at")),
        "reminder_count": int(row.get("reminder_count") or 0),
        "extraction_confidence": row.get("confidence"),
        "next_action": row.get("next_action"),
        "has_file": bool(file_id),
        "preview_path": f"/dashboard/mobile/documents/files/{file_id}" if file_id else None,
        "download_path": (
            f"/dashboard/mobile/documents/files/{file_id}?disposition=attachment"
            if file_id
            else None
        ),
        "allowed_actions": [a for a in actions if a == "review"] if reviewable else [],
        "destination": f"/documents/{employee_key}/{document_type}",
    }


def _mobile_compliance_payload(
    app_mod: Any,
    context: dict[str, Any],
    *,
    search: str = "",
    status: str = "",
    offset: int = 0,
    limit: int = 30,
) -> dict[str, Any]:
    return app_mod.dashboard_compliance_payload(
        context["company_code"],
        viewer_phone=context.get("hr_phone"),
        dashboard_user_id=context.get("actor_user_id"),
        actor_role=context.get("actor_role"),
        search=search,
        bucket_filter=status,
        offset=max(0, int(offset or 0)),
        limit=max(1, min(int(limit or 30), 100)),
    )


def mobile_document_reviews(
    app_mod: Any,
    context: dict[str, Any],
    *,
    search: str = "",
    status: str = "",
    offset: int = 0,
    limit: int = 30,
) -> dict[str, Any]:
    feature = _require_mobile_feature_action(app_mod, context, "hr", "document_review", "read")
    permissions = {str(value) for value in context.get("permissions") or []}
    company = context["company_code"]
    if app_mod.company_has_module(company, "compliance") and "compliance.read" in permissions:
        compliance_actions = ["read"]
        if "review" in _actions(feature) and "compliance.manage" in permissions:
            compliance_actions.append("review")
        result = _mobile_compliance_payload(
            app_mod,
            context,
            search=search,
            status=status,
            offset=offset,
            limit=limit,
        )
        return {
            "ok": True,
            "items": [
                compliance_mobile_item(app_mod, row, actions=compliance_actions)
                for row in result.get("documents") or []
            ],
            "summary": app_mod.json_safe(result.get("summary") or {}),
            "total": int(result.get("filtered_total") or 0),
            "offset": int(result.get("offset") or 0),
            "limit": int(result.get("limit") or limit),
            "has_more": bool(result.get("has_more")),
            "source": "compliance",
        }

    # Onboarding-only companies still receive a safe document-review queue via
    # the authoritative onboarding adapter. No compliance module is implied.
    onboarding = mobile_onboarding_list(
        app_mod,
        context,
        offset=offset,
        limit=limit,
        search=search,
    )
    items: list[dict[str, Any]] = []
    for card in onboarding["items"]:
        employee_key = str((card.get("employee") or {}).get("employee_key") or "")
        detail = mobile_onboarding_detail(app_mod, context, employee_key)
        for item in (detail.get("onboarding") or {}).get("items") or []:
            if item.get("document_type") or item.get("item_type") == "document":
                items.append(
                    {
                        **item,
                        "document_id": f"{employee_key}:{item.get('item_id')}",
                        "source": "onboarding",
                        "employee": card.get("employee"),
                        "destination": f"/onboarding/{employee_key}",
                    }
                )
    return {
        "ok": True,
        "items": items,
        "summary": {"needs_attention": sum(1 for item in items if item.get("allowed_actions"))},
        "total": len(items),
        "offset": onboarding["offset"],
        "limit": onboarding["limit"],
        "has_more": onboarding["has_more"],
        "source": "onboarding",
    }


def _find_compliance_document(
    app_mod: Any,
    context: dict[str, Any],
    employee_key: str,
    document_type: str,
) -> dict[str, Any]:
    result = app_mod.dashboard_compliance_payload(
        context["company_code"],
        viewer_phone=context.get("hr_phone"),
        dashboard_user_id=context.get("actor_user_id"),
        actor_role=context.get("actor_role"),
    )
    for row in result.get("documents") or []:
        if (
            str(row.get("employee_key") or "") == str(employee_key)
            and str(row.get("document_type") or "") == str(document_type)
        ):
            return row
    raise app_mod.HTTPException(
        status_code=404,
        detail={"error": "document_not_found", "message": "This document was not found."},
    )


def mobile_document_detail(
    app_mod: Any,
    context: dict[str, Any],
    employee_key: str,
    document_type: str,
) -> dict[str, Any]:
    feature = _require_mobile_feature_action(app_mod, context, "hr", "document_review", "read")
    app_mod.require_entitlement(context, "compliance", "compliance.read")
    row = _find_compliance_document(app_mod, context, employee_key, document_type)
    actions = ["read"]
    if (
        "review" in _actions(feature)
        and app_mod.dashboard_context_has_permission(context, "compliance.manage")
    ):
        actions.append("review")
    return {
        "ok": True,
        "document": compliance_mobile_item(app_mod, row, actions=actions),
    }


def employee_directory_mobile_item(app_mod: Any, row: dict[str, Any]) -> dict[str, Any]:
    card = row if isinstance(row, dict) else {}
    employee_key = str(card.get("employee_key") or "")
    return {
        "employee_key": employee_key,
        "employee": {
            "employee_key": employee_key,
            "name": card.get("name") or "Employee",
            "position_title": card.get("position_title"),
            "department": card.get("department"),
            "employment_status": card.get("employment_status"),
        },
        "started_on": _iso(card.get("start_date")),
        "allowed_actions": ["read"],
        "destination": f"/employees/{employee_key}",
    }


def mobile_employee_directory(
    app_mod: Any,
    context: dict[str, Any],
    *,
    search: str = "",
    offset: int = 0,
    limit: int = 30,
) -> dict[str, Any]:
    _require_mobile_feature_action(app_mod, context, "hr", "employee_search", "read")
    result = app_mod.dashboard_posthire_employees(
        offset=max(0, int(offset or 0)),
        limit=max(1, min(int(limit or 30), 100)),
        search=str(search or ""),
        context=context,
    )
    return {
        "ok": True,
        "items": [
            employee_directory_mobile_item(app_mod, row)
            for row in result.get("employees") or []
        ],
        "total": int(result.get("total_count") or 0),
        "limit": int(result.get("limit") or limit),
        "offset": int(result.get("offset") or offset),
        "has_more": bool(result.get("has_more")),
    }


def mobile_employee_quick_profile(
    app_mod: Any,
    context: dict[str, Any],
    employee_key: str,
) -> dict[str, Any]:
    _require_mobile_feature_action(
        app_mod, context, "hr", "employee_quick_profile", "read"
    )
    app_mod.require_workspace_permission(context, "employees.read")
    profile = app_mod.dashboard_employee_profile(context, employee_key)
    card = profile.get("employee") if isinstance(profile.get("employee"), dict) else {}
    key = str(card.get("employee_key") or employee_key)
    return {
        "ok": True,
        "employee": {
            "employee_key": key,
            "employee": {
                "employee_key": key,
                "name": card.get("name") or "Employee",
                "position_title": card.get("position_title"),
                "department": card.get("department"),
                "employment_status": card.get("employment_status"),
            },
            "email": card.get("email"),
            "phone": card.get("phone"),
            "started_on": _iso(card.get("start_date")),
            "allowed_actions": ["read"],
        },
    }


def delivery_alert_mobile_item(row: dict[str, Any]) -> dict[str, Any]:
    message_id = str(row.get("message_id") or "")
    employee_key = str(row.get("employee_key") or "")
    return {
        "alert_id": message_id,
        "title": row.get("flow_label") or "Delivery alert",
        "summary": row.get("reason"),
        "status": row.get("status"),
        "channel": row.get("flow"),
        "occurred_at": _iso(row.get("last_attempt_at")),
        "suggested_action": row.get("suggested_action"),
        "attempts": int(row.get("attempts") or 0),
        "destination": f"/employees/{employee_key}" if employee_key else None,
        "allowed_actions": ["read"],
    }


def mobile_delivery_alert_queue(
    app_mod: Any,
    context: dict[str, Any],
    *,
    offset: int = 0,
    limit: int = 30,
) -> dict[str, Any]:
    _require_mobile_feature_action(app_mod, context, "hr", "delivery_alerts", "read")
    result = app_mod.dashboard_outbound_needs_follow_up(
        limit=max(1, min(int(limit or 30), 100)),
        offset=max(0, int(offset or 0)),
        context=context,
    )
    return {
        "ok": True,
        "items": [
            delivery_alert_mobile_item(row)
            for row in result.get("messages") or []
        ],
        "total": int(result.get("total") or 0),
        "limit": int(result.get("limit") or limit),
        "offset": int(result.get("offset") or offset),
        "has_more": int(result.get("offset") or offset)
        + len(result.get("messages") or [])
        < int(result.get("total") or 0),
    }


def attendance_mobile_item(
    app_mod: Any,
    row: dict[str, Any],
    *,
    actions: list[str],
) -> dict[str, Any]:
    attendance_id = str(row.get("attendance_id") or "")
    status = str(row.get("status") or "")
    reviewable = status in {"late", "absent", "pending"}
    return {
        "attendance_id": attendance_id,
        "employee": _employee_identity(
            app_mod,
            None,
            key=str(row.get("employee_key") or ""),
            name=row.get("employee_name"),
        ),
        "attendance_date": _iso(row.get("attendance_date")),
        "scheduled_start": _iso(row.get("scheduled_start")),
        "scheduled_end": _iso(row.get("scheduled_end")),
        "check_in_at": _iso(row.get("check_in_at")),
        "check_out_at": _iso(row.get("check_out_at")),
        "status": status,
        "late_minutes": int(row.get("late_minutes") or 0),
        "early_leave_minutes": int(row.get("early_leave_minutes") or 0),
        "notes": row.get("notes"),
        "updated_at": _iso(row.get("updated_at")),
        "allowed_actions": [a for a in actions if a == "resolve"] if reviewable else [],
        "destination": f"/attendance/{attendance_id}",
    }


def mobile_attendance_list(
    app_mod: Any,
    context: dict[str, Any],
    *,
    start_date: str | None = None,
    end_date: str | None = None,
    status: str | None = None,
    offset: int = 0,
    limit: int = 100,
) -> dict[str, Any]:
    feature = _require_mobile_feature_action(app_mod, context, "hr", "attendance_exceptions", "read")
    result = app_mod.dashboard_posthire_attendance(
        start_date=start_date,
        end_date=end_date,
        status=status,
        offset=max(0, int(offset or 0)),
        limit=max(1, min(int(limit or 100), 200)),
        context=context,
    )
    return {
        "ok": True,
        "items": [
            attendance_mobile_item(app_mod, row, actions=_actions(feature))
            for row in result.get("attendance") or []
        ],
        "start_date": result.get("start_date"),
        "end_date": result.get("end_date"),
        "is_today": bool(result.get("is_today")),
        "status": result.get("status_filter"),
        "total": int(result.get("total_count") or 0),
        "limit": int(result.get("limit") or limit),
        "offset": int(result.get("offset") or 0),
        "has_more": bool(result.get("has_more")),
    }


def _load_attendance(
    app_mod: Any,
    context: dict[str, Any],
    attendance_id: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    with app_mod.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT *
                FROM attendance_records
                WHERE company_code=%s AND attendance_id=%s
                LIMIT 1
                """,
                (context["company_code"], str(attendance_id)),
            )
            row = cur.fetchone()
    if not row:
        raise app_mod.HTTPException(
            status_code=404,
            detail={"error": "attendance_not_found", "message": "This attendance record was not found."},
        )
    attendance = dict(row)
    employee = app_mod.find_employee_by_key(
        attendance.get("employee_key"), company_code=context["company_code"]
    )
    if not employee or not app_mod.context_manager_allows_employee(
        context, employee, company_code=context["company_code"]
    ):
        raise app_mod.HTTPException(
            status_code=404,
            detail={"error": "attendance_not_found", "message": "This attendance record was not found."},
        )
    return attendance, employee


def mobile_attendance_detail(
    app_mod: Any,
    context: dict[str, Any],
    attendance_id: str,
) -> dict[str, Any]:
    feature = _require_mobile_feature_action(app_mod, context, "hr", "attendance_exceptions", "read")
    app_mod.require_entitlement(context, "attendance", "attendance.read")
    row, _ = _load_attendance(app_mod, context, attendance_id)
    return {
        "ok": True,
        "attendance": attendance_mobile_item(app_mod, row, actions=_actions(feature)),
    }


def shift_mobile_item(app_mod: Any, row: dict[str, Any]) -> dict[str, Any]:
    return {
        "shift_id": str(row.get("shift_id") or ""),
        "employee": _employee_identity(
            app_mod,
            None,
            key=str(row.get("employee_key") or ""),
            name=row.get("employee_name"),
        ),
        "shift_date": _iso(row.get("shift_date")),
        "start_time": _iso(row.get("start_time")),
        "end_time": _iso(row.get("end_time")),
        "timezone": row.get("timezone"),
        "role": row.get("role"),
        "location": row.get("location"),
        "status": row.get("status"),
        "updated_at": _iso(row.get("updated_at")),
        "allowed_actions": ["read"],
        "destination": f"/shifts/{row.get('shift_id')}",
    }


def mobile_day_shifts(
    app_mod: Any,
    context: dict[str, Any],
    *,
    shift_date: str | None = None,
    offset: int = 0,
    limit: int = 100,
) -> dict[str, Any]:
    _require_mobile_feature_action(app_mod, context, "hr", "today_shifts", "read")
    app_mod.require_entitlement(context, "shifts", "shifts.read")
    day = app_mod.parse_shift_date_value(shift_date) if shift_date else app_mod.kuwait_today()
    if not day:
        raise app_mod.HTTPException(
            status_code=400,
            detail={"error": "invalid_shift_date", "message": "That shift date is not valid."},
        )
    result = app_mod.list_shifts(
        {
            "company_code": context["company_code"],
            "start_date": day.isoformat(),
            "end_date": day.isoformat(),
            "viewer_phone": context.get("hr_phone"),
            "viewer_user_id": context.get("actor_user_id"),
            "actor_role": context.get("actor_role"),
            "limit": max(1, min(int(limit or 100), 200)),
            "offset": max(0, int(offset or 0)),
        },
        company_code=context["company_code"],
    )
    return {
        "ok": True,
        "date": day.isoformat(),
        "items": [shift_mobile_item(app_mod, row) for row in result.get("shifts") or []],
        "total": int(result.get("total_count") or 0),
        "limit": int(result.get("limit") or limit),
        "offset": int(result.get("offset") or 0),
        "has_more": bool(result.get("has_more")),
    }


def shift_swap_mobile_item(
    app_mod: Any,
    row: dict[str, Any],
    *,
    actions: list[str],
) -> dict[str, Any]:
    swap_id = str(row.get("swap_id") or "")
    status = str(row.get("status") or "")
    return {
        "swap_id": swap_id,
        "requester": _employee_identity(
            app_mod,
            None,
            key=str(row.get("requester_employee_key") or ""),
            name=row.get("requester_employee_name"),
        ),
        "target": (
            _employee_identity(
                app_mod,
                None,
                key=str(row.get("target_employee_key") or ""),
                name=row.get("target_employee_name"),
            )
            if row.get("target_employee_key")
            else None
        ),
        "requester_shift_id": (
            str(row.get("requester_shift_id")) if row.get("requester_shift_id") else None
        ),
        "target_shift_id": str(row.get("target_shift_id")) if row.get("target_shift_id") else None,
        "shift_date": _iso(row.get("shift_date")),
        "status": status,
        "reason": row.get("reason"),
        "decision_note": row.get("decision_note"),
        "requested_at": _iso(row.get("requested_at") or row.get("created_at")),
        "decided_at": _iso(row.get("decided_at")),
        "updated_at": _iso(row.get("updated_at")),
        "allowed_actions": (
            [a for a in actions if a in {"approve", "reject"}]
            if status == "requested"
            else []
        ),
        "destination": f"/shift-swaps/{swap_id}",
    }


def _load_shift_swap(
    app_mod: Any,
    context: dict[str, Any],
    swap_id: str,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any] | None]:
    with app_mod.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT *
                FROM shift_swap_requests
                WHERE company_code=%s AND swap_id=%s
                LIMIT 1
                """,
                (context["company_code"], str(swap_id)),
            )
            row = cur.fetchone()
    if not row:
        raise app_mod.HTTPException(
            status_code=404,
            detail={"error": "shift_swap_not_found", "message": "This shift swap was not found."},
        )
    swap = dict(row)
    requester = app_mod.find_employee_by_key(
        swap.get("requester_employee_key"), company_code=context["company_code"]
    )
    target = (
        app_mod.find_employee_by_key(
            swap.get("target_employee_key"), company_code=context["company_code"]
        )
        if swap.get("target_employee_key")
        else None
    )
    if (
        not requester
        or (swap.get("target_employee_key") and not target)
        or not app_mod.context_manager_allows_employee(
            context, requester, company_code=context["company_code"]
        )
        or (
            target
            and not app_mod.context_manager_allows_employee(
                context, target, company_code=context["company_code"]
            )
        )
    ):
        raise app_mod.HTTPException(
            status_code=404,
            detail={"error": "shift_swap_not_found", "message": "This shift swap was not found."},
        )
    return swap, requester, target


def mobile_shift_swaps(
    app_mod: Any,
    context: dict[str, Any],
    *,
    status: str = "requested",
    limit: int = 100,
) -> dict[str, Any]:
    feature = _require_mobile_feature_action(
        app_mod, context, "hr", "shift_swap_decisions", "read"
    )
    app_mod.require_entitlement(context, "shifts", "shifts.manage")
    result = app_mod.list_shift_swaps(
        {
            "company_code": context["company_code"],
            "status": status,
            "viewer_phone": context.get("hr_phone"),
            "viewer_user_id": context.get("actor_user_id"),
            "actor_role": context.get("actor_role"),
            "limit": max(1, min(int(limit or 100), 200)),
        },
        company_code=context["company_code"],
    )
    items = []
    for row in result.get("swaps") or []:
        try:
            scoped, _, _ = _load_shift_swap(app_mod, context, str(row.get("swap_id") or ""))
        except app_mod.HTTPException:
            continue
        items.append(shift_swap_mobile_item(app_mod, scoped, actions=_actions(feature)))
    return {
        "ok": True,
        "items": items,
        "total": len(items),
        "status": status,
    }


def mobile_shift_swap_detail(
    app_mod: Any,
    context: dict[str, Any],
    swap_id: str,
) -> dict[str, Any]:
    feature = _require_mobile_feature_action(
        app_mod, context, "hr", "shift_swap_decisions", "read"
    )
    app_mod.require_entitlement(context, "shifts", "shifts.manage")
    row, _, _ = _load_shift_swap(app_mod, context, swap_id)
    requester_shift = (
        app_mod.shift_by_id(str(row.get("requester_shift_id")))
        if row.get("requester_shift_id")
        else None
    )
    target_shift = (
        app_mod.shift_by_id(str(row.get("target_shift_id")))
        if row.get("target_shift_id")
        else None
    )
    if requester_shift and str(requester_shift.get("company_code") or "").upper() != context["company_code"]:
        requester_shift = None
    if target_shift and str(target_shift.get("company_code") or "").upper() != context["company_code"]:
        target_shift = None
    return {
        "ok": True,
        "swap": {
            **shift_swap_mobile_item(app_mod, row, actions=_actions(feature)),
            "requester_shift": (
                shift_mobile_item(app_mod, requester_shift) if requester_shift else None
            ),
            "target_shift": shift_mobile_item(app_mod, target_shift) if target_shift else None,
        },
    }


def interview_mobile_item(
    app_mod: Any,
    row: dict[str, Any],
    *,
    status_actions: list[str],
    note_actions: list[str],
    detail: bool = False,
) -> dict[str, Any]:
    interview_id = str(row.get("interview_id") or "")
    payload = {
        "interview_id": interview_id,
        "app_key": row.get("app_key"),
        "candidate": {
            "name": row.get("candidate_name") or "Candidate",
            "email": row.get("candidate_email"),
        },
        "position": {
            "code": row.get("position_code"),
            "title": row.get("position_title"),
        },
        "interview_type": row.get("interview_type"),
        "status": row.get("status"),
        "feedback_status": row.get("feedback_status"),
        "scheduled_start": _iso(row.get("scheduled_start")),
        "scheduled_end": _iso(row.get("scheduled_end")),
        "timezone": row.get("timezone"),
        "meeting": {
            "type": row.get("meeting_type"),
            "join_url": row.get("meet_link"),
        },
        "communication": {
            "calendar_invite_sent": bool(row.get("calendar_invite_sent")),
            "candidate_invited": bool(row.get("candidate_invited")),
            "candidate_notified": bool(row.get("candidate_notified")),
            "channel": row.get("notification_channel"),
            "invite_sent_at": _iso(row.get("invite_sent_at")),
        },
        "notes_available": bool(str(row.get("notes") or "").strip()),
        "updated_at": _iso(row.get("updated_at")),
        "allowed_actions": sorted(set([*status_actions, *note_actions])),
        "destination": f"/interviews/{interview_id}",
    }
    if detail:
        payload["notes"] = row.get("notes")
        payload["ai_summary"] = app_mod.json_safe(row.get("ai_summary") or {})
        payload["ai_advisory"] = True
    return payload


def mobile_interviews(
    app_mod: Any,
    context: dict[str, Any],
    *,
    status: str | None = None,
    query: str | None = None,
    role: str | None = None,
    date_filter: str | None = None,
    interviewer: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> dict[str, Any]:
    status_feature = _require_mobile_feature_action(
        app_mod, context, "recruiting", "interview_status", "read"
    )
    notes_feature = _workspace_features(app_mod, context, "recruiting").get("interview_notes") or {}
    result = app_mod.dashboard_interviews_payload(
        context["company_code"],
        status=status,
        q=query,
        role=role,
        date_filter=date_filter,
        interviewer=interviewer,
        limit=max(1, min(int(limit or 50), 100)),
        offset=max(0, int(offset or 0)),
    )
    items = [
        interview_mobile_item(
            app_mod,
            row,
            status_actions=_actions(status_feature),
            note_actions=_actions(notes_feature),
        )
        for row in result.get("interviews") or []
    ]
    total = int(result.get("total") or 0)
    result_offset = int(result.get("offset") or offset)
    return {
        "ok": True,
        "items": items,
        "total": total,
        "limit": int(result.get("limit") or limit),
        "offset": result_offset,
        "has_more": result_offset + len(items) < total,
        "status_counts": app_mod.json_safe(result.get("status_counts") or []),
        "feedback_counts": app_mod.json_safe(result.get("feedback_counts") or []),
    }


def _load_interview(app_mod: Any, context: dict[str, Any], interview_id: str) -> dict[str, Any]:
    row = app_mod.fetch_candidate_interview(interview_id, context["company_code"])
    if not row:
        raise app_mod.HTTPException(
            status_code=404,
            detail={"error": "interview_not_found", "message": "This interview was not found."},
        )
    return row


def mobile_interview_detail(
    app_mod: Any,
    context: dict[str, Any],
    interview_id: str,
) -> dict[str, Any]:
    status_feature = _require_mobile_feature_action(
        app_mod, context, "recruiting", "interview_status", "read"
    )
    notes_feature = _workspace_features(app_mod, context, "recruiting").get("interview_notes") or {}
    row = app_mod.candidate_interview_summary(_load_interview(app_mod, context, interview_id))
    return {
        "ok": True,
        "interview": interview_mobile_item(
            app_mod,
            row,
            status_actions=_actions(status_feature),
            note_actions=_actions(notes_feature),
            detail=True,
        ),
    }


def _leave_duration(row: dict[str, Any]) -> float | None:
    explicit = row.get("duration_days") or row.get("days")
    if explicit is not None:
        try:
            return float(explicit)
        except (TypeError, ValueError):
            pass
    start = row.get("start_date")
    end = row.get("end_date")
    if start and end:
        try:
            return float((end - start).days + 1)
        except Exception:
            return None
    return None


def leave_mobile_item(
    app_mod: Any,
    row: dict[str, Any],
    *,
    employee: dict[str, Any] | None = None,
    actions: list[str] | None = None,
    balance: Any = None,
) -> dict[str, Any]:
    status = str(row.get("status") or "")
    allowed = list(actions or []) if status == "requested" else []
    return {
        "leave_id": str(row.get("leave_id") or ""),
        "employee": _employee_context(app_mod, employee or row),
        "leave_type": row.get("leave_type") or row.get("type"),
        "start_date": _iso(row.get("start_date")),
        "end_date": _iso(row.get("end_date")),
        "duration_days": _leave_duration(row),
        "reason": row.get("reason") or row.get("request_reason"),
        "status": status,
        "decision_note": row.get("decision_note"),
        "requested_at": _iso(row.get("requested_at") or row.get("created_at")),
        "updated_at": _iso(row.get("updated_at")),
        "shift_conflict_count": int(row.get("shift_conflict_count") or 0),
        "balance": app_mod.json_safe(balance) if balance is not None else None,
        "allowed_actions": allowed,
        "destination": f"/leave/{row.get('leave_id')}",
    }


def _load_leave(app_mod: Any, context: dict[str, Any], leave_id: str) -> tuple[dict[str, Any], dict[str, Any]]:
    company = context["company_code"]
    with app_mod.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT lr.*,
                  (
                    SELECT COUNT(*)
                    FROM shift_assignments s
                    WHERE s.company_code=lr.company_code
                      AND s.employee_key=lr.employee_key
                      AND s.shift_date BETWEEN lr.start_date AND lr.end_date
                      AND s.status='scheduled'
                  ) AS shift_conflict_count
                FROM leave_requests lr
                WHERE lr.company_code=%s AND lr.leave_id=%s
                LIMIT 1
                """,
                (company, str(leave_id)),
            )
            row = cur.fetchone()
    if not row:
        raise app_mod.HTTPException(
            status_code=404,
            detail={"error": "leave_request_not_found", "message": "This leave request was not found."},
        )
    leave = dict(row)
    employee = app_mod.find_employee_by_key(leave.get("employee_key"), company_code=company)
    if not employee or not app_mod.context_manager_allows_employee(context, employee, company_code=company):
        # Cross-tenant and out-of-scope records are intentionally indistinguishable.
        raise app_mod.HTTPException(
            status_code=404,
            detail={"error": "leave_request_not_found", "message": "This leave request was not found."},
        )
    return leave, employee


def mobile_leave_list(
    app_mod: Any,
    context: dict[str, Any],
    *,
    status: str = "requested",
    offset: int = 0,
    limit: int = 30,
) -> dict[str, Any]:
    app_mod.require_entitlement(context, "leave", "leave.read")
    feature = app_mod._operator_mobile.build_hr_workspace_capabilities(app_mod, context).get("leave_approvals")
    result = app_mod.list_leave_requests(
        {
            "company_code": context["company_code"],
            "status": status,
            "viewer_phone": context.get("hr_phone"),
            "viewer_user_id": context.get("actor_user_id"),
            "actor_role": context.get("actor_role"),
            "limit": max(1, min(int(limit or 30), 100)),
            "offset": max(0, int(offset or 0)),
        },
        company_code=context["company_code"],
    )
    rows = result.get("leave_requests") or []
    employees = {
        str(row.get("employee_key")): app_mod.find_employee_by_key(
            row.get("employee_key"), company_code=context["company_code"]
        )
        for row in rows
        if row.get("employee_key")
    }
    actions = _actions(feature)
    return {
        "ok": True,
        "items": [
            leave_mobile_item(
                app_mod,
                row,
                employee=employees.get(str(row.get("employee_key"))),
                actions=actions,
            )
            for row in rows
        ],
        "total": int(result.get("total_count") or 0),
        "offset": int(result.get("offset") or 0),
        "limit": int(result.get("limit") or limit),
        "has_more": bool(result.get("has_more")),
        "status": status,
    }


def mobile_leave_detail(app_mod: Any, context: dict[str, Any], leave_id: str) -> dict[str, Any]:
    app_mod.require_entitlement(context, "leave", "leave.read")
    leave, employee = _load_leave(app_mod, context, leave_id)
    feature = app_mod._operator_mobile.build_hr_workspace_capabilities(app_mod, context).get("leave_approvals")
    balance = None
    if app_mod.leave_balances_enabled():
        balance = app_mod.leave_balances_for_employee(context["company_code"], str(leave.get("employee_key")))
    return {
        "ok": True,
        "request": leave_mobile_item(
            app_mod,
            leave,
            employee=employee,
            actions=_actions(feature),
            balance=balance,
        ),
    }


def _candidate_allowed_actions(context: dict[str, Any], status: str) -> list[str]:
    permissions = {str(value) for value in context.get("permissions") or []}
    if status in {"hired", "rejected"}:
        return []
    actions: list[str] = []
    if "candidate.manage" in permissions and status != "shortlisted":
        actions.append("shortlist")
    if "candidate.decide" in permissions:
        actions.extend(["reject", "hire"])
    return actions


def candidate_mobile_item(app_mod: Any, item: dict[str, Any]) -> dict[str, Any]:
    application = item.get("application") if isinstance(item.get("application"), dict) else {}
    candidate = application.get("candidate") if isinstance(application.get("candidate"), dict) else {}
    position = application.get("position") if isinstance(application.get("position"), dict) else {}
    evidence = item.get("evidence") if isinstance(item.get("evidence"), list) else []
    evaluation = item.get("gpt_evaluation") if isinstance(item.get("gpt_evaluation"), dict) else {}
    concerns = (
        evaluation.get("concerns")
        or evaluation.get("gaps")
        or evaluation.get("missing_evidence")
        or []
    )
    status = str(item.get("status") or application.get("status") or "")
    return {
        "app_key": str(item.get("app_key") or application.get("app_key") or ""),
        "candidate": {
            "name": item.get("name") or candidate.get("name") or "Candidate",
            "email": candidate.get("email"),
        },
        "position": {
            "code": item.get("position_code") or position.get("code"),
            "title": item.get("position_title") or position.get("title"),
        },
        "status": status,
        "score": item.get("score"),
        "confidence": item.get("confidence"),
        "evidence": app_mod.json_safe(evidence),
        "reasons": app_mod.json_safe(item.get("reasons") or evidence[:4]),
        "concerns": app_mod.json_safe(concerns),
        "missing_evidence": app_mod.json_safe(evaluation.get("missing_evidence") or []),
        "assessment": app_mod.json_safe(item.get("assessment_signal") or application.get("assessment")),
        "interview": app_mod.json_safe(item.get("interview_signal") or application.get("interview")),
        "cv": app_mod.json_safe(application.get("cv") or {}),
        "ai_advisory": True,
        "allowed_actions": _candidate_allowed_actions(
            {"permissions": item.get("_permissions") or []},
            status,
        ),
        "destination": f"/candidates/{item.get('app_key') or application.get('app_key')}",
    }


def mobile_candidate_rankings(
    app_mod: Any,
    context: dict[str, Any],
    *,
    query: str = "",
    position: str = "",
    status: str = "",
    limit: int = 20,
) -> dict[str, Any]:
    app_mod.require_entitlement(context, "pre_hiring", "prehire.read")
    result = app_mod.rank_candidates(
        {
            "query": query,
            "position": position,
            "status": status,
            "top_n": max(1, min(int(limit or 20), 50)),
        },
        company_code=context["company_code"],
    )
    items = []
    for candidate in result.get("candidates") or []:
        items.append(candidate_mobile_item(app_mod, {**candidate, "_permissions": context.get("permissions") or []}))
    return {
        "ok": True,
        "items": items,
        "total": int(result.get("total_matching") or 0),
        "filters": app_mod.json_safe(result.get("filters") or {}),
        "ai_advisory": True,
    }


def mobile_candidate_detail(app_mod: Any, context: dict[str, Any], app_key: str) -> dict[str, Any]:
    app_mod.require_entitlement(context, "pre_hiring", "prehire.read")
    application = app_mod.dashboard_application_or_404(app_key, context["company_code"])
    summary = app_mod.prehire_application_summary(
        application,
        include_raw=False,
        include_assessment=app_mod.company_has_module(context["company_code"], "assessments"),
    )
    evaluation = app_mod.latest_application_rank_evaluation(context["company_code"], app_key) or {}
    evidence = evaluation.get("evidence") or evaluation.get("reasons") or []
    concerns = evaluation.get("concerns") or evaluation.get("gaps") or evaluation.get("gaps_or_risks") or []
    cv = app_mod.dashboard_candidate_cv_metadata(application)
    status = str(summary.get("status") or application.get("status") or "")
    with app_mod.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT status, feedback_status, notes, ai_summary, scheduled_start, updated_at
                FROM candidate_interviews
                WHERE company_code=%s AND app_key=%s
                ORDER BY scheduled_start DESC NULLS LAST, updated_at DESC
                LIMIT 1
                """,
                (context["company_code"], app_key),
            )
            interview = dict(cur.fetchone() or {})
            cur.execute(
                """
                SELECT status, last_error, message_kind, sent_at, failed_at, updated_at
                FROM outbound_delivery_events
                WHERE account_id=%s AND subject_key=%s
                ORDER BY created_at DESC
                LIMIT 10
                """,
                (context["company_code"], app_key),
            )
            communications = [dict(row) for row in cur.fetchall()]
    return {
        "ok": True,
        "candidate": {
            "app_key": app_key,
            "overview": app_mod.json_safe(summary),
            "ranking": {
                "score": evaluation.get("score"),
                "confidence": evaluation.get("confidence"),
                "reasons": app_mod.json_safe(evaluation.get("reasons") or evidence[:4]),
                "evidence": app_mod.json_safe(evidence),
                "concerns": app_mod.json_safe(concerns),
                "missing_evidence": app_mod.json_safe(evaluation.get("missing_evidence") or []),
                "ai_advisory": True,
            },
            "cv": {
                "available": bool(cv),
                "filename": (cv or {}).get("original_filename"),
                "mime_type": (cv or {}).get("mime_type"),
                "size_bytes": (cv or {}).get("size_bytes"),
                "preview_path": f"/dashboard/mobile/candidates/{app_key}/cv/preview" if cv else None,
                "download_path": f"/dashboard/mobile/candidates/{app_key}/cv" if cv else None,
            },
            "interview": app_mod.json_safe(interview) if interview else None,
            "communication_status": [
                {
                    "status": row.get("status"),
                    "display_status": app_mod.dashboard_delivery_status(row),
                    "message_kind": row.get("message_kind"),
                    "sent_at": _iso(row.get("sent_at")),
                    "failed_at": _iso(row.get("failed_at")),
                    "updated_at": _iso(row.get("updated_at")),
                }
                for row in communications
            ],
            "allowed_actions": _candidate_allowed_actions(context, status),
        },
    }


def _confirmation_public(row: dict[str, Any], *, replay: bool = False) -> dict[str, Any]:
    registry = row.get("registry_confirmation") if isinstance(row.get("registry_confirmation"), dict) else {}
    return {
        "confirmation_id": str(row.get("confirmation_id") or ""),
        "confirmation_hash": row.get("request_hash"),
        "action": row.get("action_type"),
        "target": {"type": row.get("target_type"), "id": row.get("target_id")},
        "summary": row.get("safe_summary"),
        "consequence": row.get("consequence"),
        "current_state": row.get("expected_status"),
        "expires_at": _iso(row.get("expires_at")),
        "status": row.get("status"),
        "backend_confirmation": registry,
        "idempotent_replay": replay,
    }


def _confirmation_lookup(
    app_mod: Any,
    context: dict[str, Any],
    *,
    idempotency_key: str | None = None,
    confirmation_id: str | None = None,
    for_update: bool = False,
) -> dict[str, Any] | None:
    where = "confirmation_id=%s" if confirmation_id else "idempotency_key=%s"
    value = confirmation_id or idempotency_key
    lock = " FOR UPDATE" if for_update else ""
    with app_mod.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                SELECT *
                FROM dashboard_operator_mobile_confirmations
                WHERE company_code=%s AND user_id=%s AND {where}
                LIMIT 1{lock}
                """,
                (context["company_code"], context["actor_user_id"], value),
            )
            row = cur.fetchone()
    return dict(row) if row else None


def _execute_registry_action(
    app_mod: Any,
    context: dict[str, Any],
    action_type: str,
    args: dict[str, Any],
    target_type: str,
) -> dict[str, Any]:
    if target_type in {
        "leave_request",
        "onboarding_item",
        "attendance_record",
        "shift_swap",
        "compliance_document",
    }:
        result = app_mod.run_posthire_dashboard_action(context, action_type, args)
    else:
        conversation_id = app_mod.posthire_dashboard_conversation_id(context)
        scope = app_mod.posthire_dashboard_scope(context, conversation_id)
        result = app_mod.run_dashboard_registry_action(
            context,
            action_type,
            args,
            allowed_modules=app_mod.PREHIRE_DASHBOARD_REGISTRY_MODULES,
            conversation_id=conversation_id,
            scope=scope,
            audit_target_type="application",
        )
    return result


def prepare_mobile_confirmation(
    app_mod: Any,
    context: dict[str, Any],
    *,
    idempotency_key: str,
    action_type: str,
    target_type: str,
    target_id: str,
    expected_status: str,
    safe_summary: str,
    consequence: str,
    args: dict[str, Any],
) -> dict[str, Any]:
    key = str(idempotency_key or "").strip()
    if len(key) < 12 or len(key) > 160:
        raise app_mod.HTTPException(
            status_code=422,
            detail={"error": "invalid_idempotency_key", "message": "A valid idempotency key is required."},
        )
    request_hash = _stable_hash(
        {
            "action_type": action_type,
            "target_type": target_type,
            "target_id": target_id,
            "expected_status": expected_status,
            "args": args,
        }
    )
    existing = _confirmation_lookup(app_mod, context, idempotency_key=key)
    if existing:
        if existing.get("request_hash") != request_hash:
            raise app_mod.HTTPException(
                status_code=409,
                detail={"error": "idempotency_conflict", "message": "That action key was already used for another decision."},
            )
        return {
            "ok": str(existing.get("status")) == "completed",
            "status": existing.get("status"),
            "confirmation": _confirmation_public(existing, replay=True),
            "result": app_mod.json_safe(existing.get("result")),
        }

    expires_at = app_mod.now_utc() + MOBILE_CONFIRMATION_TTL
    with app_mod.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO dashboard_operator_mobile_confirmations
                  (user_id, session_id, company_code, idempotency_key, request_hash,
                   action_type, target_type, target_id, expected_status,
                   safe_summary, consequence, args, expires_at)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                RETURNING *
                """,
                (
                    context["actor_user_id"],
                    context.get("mobile_session_id") or None,
                    context["company_code"],
                    key,
                    request_hash,
                    action_type,
                    target_type,
                    target_id,
                    expected_status,
                    safe_summary,
                    consequence,
                    app_mod.Json(app_mod.json_safe(args)),
                    expires_at,
                ),
            )
            row = dict(cur.fetchone())
        conn.commit()

    # Preflight through the authoritative registry. The mutation cannot execute
    # here because every exposed mobile action is registry-confirmed.
    preflight = _execute_registry_action(app_mod, context, action_type, args, target_type)
    if preflight.get("status") != "needs_confirmation":
        # Fail closed if registry policy unexpectedly stops requiring confirmation.
        with app_mod.db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE dashboard_operator_mobile_confirmations
                    SET status='failed', result=%s, updated_at=now()
                    WHERE confirmation_id=%s
                    """,
                    (app_mod.Json(app_mod.json_safe(preflight)), row["confirmation_id"]),
                )
            conn.commit()
        raise app_mod.HTTPException(
            status_code=409,
            detail={"error": "confirmation_unavailable", "message": "This decision could not be prepared safely."},
        )

    registry_confirmation = preflight.get("confirmation") or {}
    with app_mod.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE dashboard_operator_mobile_confirmations
                SET status='pending', registry_action_hash=%s,
                    registry_confirmation=%s, updated_at=now()
                WHERE confirmation_id=%s
                RETURNING *
                """,
                (
                    registry_confirmation.get("action_hash"),
                    app_mod.Json(app_mod.json_safe(registry_confirmation)),
                    row["confirmation_id"],
                ),
            )
            prepared = dict(cur.fetchone())
        conn.commit()
    return {
        "ok": False,
        "status": "needs_confirmation",
        "confirmation": _confirmation_public(prepared),
        "result": None,
    }


def _load_onboarding_item(
    app_mod: Any,
    context: dict[str, Any],
    target_id: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    employee_key, separator, item_id = str(target_id or "").partition(":")
    if not separator or not employee_key or not item_id:
        raise app_mod.HTTPException(
            status_code=404,
            detail={"error": "onboarding_item_not_found", "message": "This checklist item was not found."},
        )
    employee = app_mod.find_employee_by_key(
        employee_key, company_code=context["company_code"]
    )
    if not employee or not app_mod.context_manager_allows_employee(
        context, employee, company_code=context["company_code"]
    ):
        raise app_mod.HTTPException(
            status_code=404,
            detail={"error": "onboarding_item_not_found", "message": "This checklist item was not found."},
        )
    for item in app_mod.employee_onboarding_items(employee_key):
        if str(item.get("item_id") or "") == item_id:
            return item, employee
    raise app_mod.HTTPException(
        status_code=404,
        detail={"error": "onboarding_item_not_found", "message": "This checklist item was not found."},
    )


def _current_target_status(app_mod: Any, context: dict[str, Any], row: dict[str, Any]) -> str | None:
    target_type = str(row.get("target_type") or "")
    target_id = str(row.get("target_id") or "")
    if target_type == "leave_request":
        leave, _ = _load_leave(app_mod, context, str(row.get("target_id") or ""))
        return str(leave.get("status") or "")
    if target_type == "onboarding_item":
        item, _ = _load_onboarding_item(app_mod, context, target_id)
        return str(item.get("status") or "")
    if target_type == "attendance_record":
        attendance, _ = _load_attendance(app_mod, context, target_id)
        return str(attendance.get("status") or "")
    if target_type == "shift_swap":
        swap, _, _ = _load_shift_swap(app_mod, context, target_id)
        return str(swap.get("status") or "")
    application = app_mod.dashboard_application_or_404(target_id, context["company_code"])
    return str(application.get("status") or "")


def confirm_mobile_action(
    app_mod: Any,
    context: dict[str, Any],
    *,
    confirmation_id: str,
    confirmation_hash: str,
    expected_target_type: str | None = None,
    expected_target_id: str | None = None,
    expected_action_types: set[str] | None = None,
) -> dict[str, Any]:
    row = _confirmation_lookup(app_mod, context, confirmation_id=confirmation_id)
    if not row:
        raise app_mod.HTTPException(
            status_code=404,
            detail={"error": "confirmation_not_found", "message": "This confirmation is no longer available."},
        )
    if not hmac.compare_digest(str(row.get("request_hash") or ""), str(confirmation_hash or "")):
        raise app_mod.HTTPException(
            status_code=403,
            detail={"error": "confirmation_mismatch", "message": "This confirmation does not match the decision."},
        )
    if (
        (expected_target_type and str(row.get("target_type") or "") != expected_target_type)
        or (expected_target_id and str(row.get("target_id") or "") != expected_target_id)
        or (
            expected_action_types is not None
            and str(row.get("action_type") or "") not in expected_action_types
        )
    ):
        raise app_mod.HTTPException(
            status_code=403,
            detail={
                "error": "confirmation_mismatch",
                "message": "This confirmation does not match the decision.",
            },
        )
    status = str(row.get("status") or "")
    if status in {"completed", "failed"}:
        return {
            "ok": status == "completed",
            "status": status,
            "confirmation": _confirmation_public(row, replay=True),
            "result": app_mod.json_safe(row.get("result")),
        }
    if status == "processing":
        raise app_mod.HTTPException(
            status_code=409,
            detail={"error": "action_in_progress", "message": "This decision is already being processed."},
        )
    if row.get("expires_at") and row["expires_at"] <= app_mod.now_utc():
        raise app_mod.HTTPException(
            status_code=409,
            detail={"error": "confirmation_expired", "message": "Review the current state and confirm again."},
        )
    current_status = _current_target_status(app_mod, context, row)
    if current_status != str(row.get("expected_status") or ""):
        with app_mod.db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE dashboard_operator_mobile_confirmations
                    SET status='failed', result=%s, updated_at=now()
                    WHERE confirmation_id=%s
                    """,
                    (
                        app_mod.Json(
                            {
                                "error": "stale_decision",
                                "expected_status": row.get("expected_status"),
                                "current_status": current_status,
                            }
                        ),
                        row["confirmation_id"],
                    ),
                )
            conn.commit()
        raise app_mod.HTTPException(
            status_code=409,
            detail={
                "error": "stale_decision",
                "message": "This item changed since you reviewed it.",
                "current_status": current_status,
            },
        )

    with app_mod.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE dashboard_operator_mobile_confirmations
                SET status='processing', updated_at=now()
                WHERE confirmation_id=%s AND status='pending'
                RETURNING confirmation_id
                """,
                (row["confirmation_id"],),
            )
            claimed = cur.fetchone()
        conn.commit()
    if not claimed:
        raise app_mod.HTTPException(
            status_code=409,
            detail={"error": "action_in_progress", "message": "This decision is already being processed."},
        )

    try:
        result = _execute_registry_action(
            app_mod,
            context,
            str(row.get("action_type") or ""),
            dict(row.get("args") or {}),
            str(row.get("target_type") or ""),
        )
        # The prepare call created the registry pending action, so this should be
        # terminal. One extra invoke is allowed only after explicit mobile confirm
        # to tolerate a restarted pending-action store.
        if result.get("status") == "needs_confirmation":
            result = _execute_registry_action(
                app_mod,
                context,
                str(row.get("action_type") or ""),
                dict(row.get("args") or {}),
                str(row.get("target_type") or ""),
            )
        terminal = "completed" if result.get("ok") or result.get("status") == "completed" else "failed"
    except Exception:
        with app_mod.db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    UPDATE dashboard_operator_mobile_confirmations
                    SET status='pending', updated_at=now()
                    WHERE confirmation_id=%s AND status='processing'
                    """,
                    (row["confirmation_id"],),
                )
            conn.commit()
        raise

    with app_mod.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE dashboard_operator_mobile_confirmations
                SET status=%s, result=%s, completed_at=now(), updated_at=now()
                WHERE confirmation_id=%s
                RETURNING *
                """,
                (terminal, app_mod.Json(app_mod.json_safe(result)), row["confirmation_id"]),
            )
            completed = dict(cur.fetchone())
        conn.commit()
    return {
        "ok": terminal == "completed",
        "status": terminal,
        "confirmation": _confirmation_public(completed),
        "result": app_mod.json_safe(result),
    }


def build_mobile_priorities(app_mod: Any, context: dict[str, Any], *, limit: int = 12) -> dict[str, Any]:
    hr_features = app_mod._operator_mobile.build_hr_workspace_capabilities(app_mod, context)
    recruiting_features = app_mod._operator_mobile.build_recruiting_workspace_capabilities(app_mod, context)
    sections: list[dict[str, Any]] = []
    max_items = max(1, min(int(limit or 12), 30))

    if (hr_features.get("leave_approvals") or {}).get("enabled"):
        leave = mobile_leave_list(app_mod, context, status="requested", limit=max_items)
        sections.append(
            {
                "type": "leave_approvals",
                "title": "Leave approvals",
                "total": leave["total"],
                "items": [
                    {
                        "type": "leave_approval",
                        "target_id": item["leave_id"],
                        "summary": f"{item['employee']['name']} · {item.get('leave_type') or 'Leave request'}",
                        "status": item["status"],
                        "timestamp": item.get("requested_at") or item.get("updated_at"),
                        "due_context": {
                            "start_date": item.get("start_date"),
                            "end_date": item.get("end_date"),
                        },
                        "permitted_actions": item["allowed_actions"],
                        "destination": item["destination"],
                        "severity": "high" if item.get("shift_conflict_count") else None,
                    }
                    for item in leave["items"]
                ],
            }
        )

    if (hr_features.get("onboarding_review") or {}).get("enabled"):
        onboarding = app_mod.dashboard_posthire_onboarding(
            offset=0, limit=max_items, search="", context=context
        )
        sections.append(
            {
                "type": "onboarding_reviews",
                "title": "Onboarding reviews",
                "total": int(onboarding.get("total_count") or 0),
                "items": [
                    {
                        "type": "onboarding_review",
                        "target_id": item.get("employee_key"),
                        "summary": item.get("name") or "Employee onboarding",
                        "status": item.get("onboarding_status"),
                        "timestamp": _iso(item.get("updated_at")),
                        "due_context": None,
                        "permitted_actions": _actions(hr_features.get("onboarding_review")),
                        "destination": f"/onboarding/{item.get('employee_key')}",
                        "severity": None,
                    }
                    for item in onboarding.get("in_progress") or []
                ],
            }
        )

    if (hr_features.get("attendance_exceptions") or {}).get("enabled"):
        attendance = app_mod.dashboard_posthire_attendance(
            start_date=None,
            end_date=None,
            status="late",
            offset=0,
            limit=max_items,
            context=context,
        )
        sections.append(
            {
                "type": "attendance_exceptions",
                "title": "Attendance exceptions",
                "total": int(attendance.get("total_count") or attendance.get("count") or 0),
                "items": [
                    {
                        "type": "attendance_exception",
                        "target_id": item.get("attendance_id") or item.get("employee_key"),
                        "summary": item.get("employee_name") or "Attendance exception",
                        "status": item.get("status"),
                        "timestamp": _iso(item.get("updated_at") or item.get("attendance_date")),
                        "due_context": {"date": _iso(item.get("attendance_date"))},
                        "permitted_actions": _actions(hr_features.get("attendance_exceptions")),
                        "destination": "/attendance",
                        "severity": None,
                    }
                    for item in attendance.get("attendance") or []
                ],
            }
        )

    if (hr_features.get("hr_tasks") or {}).get("enabled"):
        tasks = app_mod.dashboard_hr_tasks(status="open", limit=max_items, offset=0, context=context)
        sections.append(
            {
                "type": "hr_tasks",
                "title": "HR tasks",
                "total": int(tasks.get("total") or 0),
                "items": [
                    {
                        "type": str(item.get("task_type") or item.get("source") or "hr_task"),
                        "target_id": str(item.get("task_id") or ""),
                        "summary": item.get("summary") or item.get("title") or "HR task",
                        "status": item.get("status"),
                        "timestamp": _iso(item.get("created_at") or item.get("updated_at")),
                        "due_context": app_mod.json_safe(item.get("due_context")),
                        "permitted_actions": _actions(hr_features.get("hr_tasks")),
                        "destination": f"/tasks/{item.get('task_id')}",
                        "severity": item.get("severity") or item.get("priority"),
                    }
                    for item in tasks.get("tasks") or []
                ],
            }
        )

    if (hr_features.get("delivery_alerts") or {}).get("enabled"):
        delivery = app_mod.dashboard_outbound_needs_follow_up(
            limit=max_items, offset=0, context=context
        )
        sections.append(
            {
                "type": "delivery_alerts",
                "title": "Delivery alerts",
                "total": int(delivery.get("total") or 0),
                "items": [
                    {
                        "type": "delivery_alert",
                        "target_id": item.get("message_id"),
                        "summary": item.get("reason"),
                        "status": item.get("status"),
                        "timestamp": _iso(item.get("last_attempt_at")),
                        "due_context": {"suggested_action": item.get("suggested_action")},
                        "permitted_actions": _actions(hr_features.get("delivery_alerts")),
                        "destination": "/delivery-alerts",
                        "severity": item.get("criticality"),
                    }
                    for item in delivery.get("messages") or []
                    if item.get("kind") == "issue"
                ],
            }
        )

    if (recruiting_features.get("candidate_rankings") or {}).get("enabled"):
        candidates = mobile_candidate_rankings(app_mod, context, limit=max_items)
        decision_items = [
            item for item in candidates["items"] if item.get("allowed_actions")
        ]
        sections.append(
            {
                "type": "candidate_decisions",
                "title": "Candidate decisions",
                "total": len(decision_items),
                "items": [
                    {
                        "type": "candidate_decision",
                        "target_id": item["app_key"],
                        "summary": f"{item['candidate']['name']} · {item['position'].get('title') or 'Candidate'}",
                        "status": item.get("status"),
                        "timestamp": None,
                        "due_context": None,
                        "permitted_actions": item.get("allowed_actions") or [],
                        "destination": item["destination"],
                        "severity": None,
                    }
                    for item in decision_items
                ],
            }
        )

    return {
        "ok": True,
        "generated_at": app_mod.now_utc().isoformat(),
        "ranking_policy": "separated_authoritative_sections_no_invented_urgency",
        "sections": sections,
    }


def register_operator_mobile_data_routes(app_mod: Any) -> None:
    """Register HR-2A/HR-3 routes after HR-1 mobile auth routes."""
    from fastapi import Depends, Query
    from pydantic import BaseModel

    dependency = getattr(
        app_mod._operator_mobile.register_operator_mobile_routes,
        "operator_mobile_context",
        None,
    )
    if dependency is None:
        raise RuntimeError("operator mobile auth routes must register before HR-2A data routes")

    class LeaveDecisionRequest(BaseModel):
        action: str
        reason: str | None = None
        idempotency_key: str
        confirmation_id: str | None = None
        confirmation_hash: str | None = None
        confirm: bool = False

    class CandidateActionRequest(BaseModel):
        action: str
        reason: str | None = None
        idempotency_key: str
        confirmation_id: str | None = None
        confirmation_hash: str | None = None
        confirm: bool = False

    class OnboardingReviewRequest(BaseModel):
        item_id: str
        outcome: str = "received"
        note: str | None = None
        idempotency_key: str
        confirmation_id: str | None = None
        confirmation_hash: str | None = None
        confirm: bool = False

    class AttendanceResolveRequest(BaseModel):
        status: str
        time: str | None = None
        notes: str | None = None
        idempotency_key: str
        confirmation_id: str | None = None
        confirmation_hash: str | None = None
        confirm: bool = False

    class ShiftSwapDecisionRequest(BaseModel):
        action: str
        idempotency_key: str
        confirmation_id: str | None = None
        confirmation_hash: str | None = None
        confirm: bool = False

    class ComplianceReviewRequest(BaseModel):
        note: str | None = None
        expected_status: str = "needs_review"

    class InterviewNotesRequest(BaseModel):
        notes: str
        status: str | None = None
        generate_summary: bool = True

    # ``from __future__ import annotations`` makes FastAPI resolve these names
    # through module globals rather than this registration function's locals.
    globals()["LeaveDecisionRequest"] = LeaveDecisionRequest
    globals()["CandidateActionRequest"] = CandidateActionRequest
    globals()["OnboardingReviewRequest"] = OnboardingReviewRequest
    globals()["AttendanceResolveRequest"] = AttendanceResolveRequest
    globals()["ShiftSwapDecisionRequest"] = ShiftSwapDecisionRequest
    globals()["ComplianceReviewRequest"] = ComplianceReviewRequest
    globals()["InterviewNotesRequest"] = InterviewNotesRequest

    @app_mod.app.get("/dashboard/mobile/priorities")
    def mobile_priorities(
        limit: int = Query(default=12, ge=1, le=30),
        context: dict[str, Any] = Depends(dependency),
    ):
        return build_mobile_priorities(app_mod, context, limit=limit)

    @app_mod.app.get("/dashboard/mobile/leave")
    def mobile_leave(
        status: str = Query(default="requested"),
        offset: int = Query(default=0, ge=0),
        limit: int = Query(default=30, ge=1, le=100),
        context: dict[str, Any] = Depends(dependency),
    ):
        normalized = str(status or "").strip().lower()
        if normalized not in {"requested", "approved", "rejected", "cancelled"}:
            raise app_mod.HTTPException(
                status_code=400,
                detail={"error": "invalid_leave_status", "message": "That leave status is not valid."},
            )
        return mobile_leave_list(
            app_mod, context, status=normalized, offset=offset, limit=limit
        )

    @app_mod.app.get("/dashboard/mobile/leave/{leave_id}")
    def mobile_leave_request(
        leave_id: str,
        context: dict[str, Any] = Depends(dependency),
    ):
        return mobile_leave_detail(app_mod, context, leave_id)

    @app_mod.app.post("/dashboard/mobile/leave/{leave_id}/decision")
    def mobile_leave_decision(
        leave_id: str,
        request: LeaveDecisionRequest,
        context: dict[str, Any] = Depends(dependency),
    ):
        app_mod.require_entitlement(context, "leave", "leave.decide")
        leave, employee = _load_leave(app_mod, context, leave_id)
        action = str(request.action or "").strip().lower()
        if action not in {"approve", "reject"}:
            raise app_mod.HTTPException(
                status_code=400,
                detail={"error": "unsupported_leave_action", "message": "That leave decision is not supported."},
            )
        if action == "reject" and not str(request.reason or "").strip():
            raise app_mod.HTTPException(
                status_code=422,
                detail={"error": "rejection_reason_required", "message": "Add a reason before rejecting this request."},
            )
        if request.confirm:
            return confirm_mobile_action(
                app_mod,
                context,
                confirmation_id=str(request.confirmation_id or ""),
                confirmation_hash=str(request.confirmation_hash or ""),
                expected_target_type="leave_request",
                expected_target_id=str(leave_id),
                expected_action_types={MOBILE_ACTIONS[f"{action}_leave"]},
            )
        employee_name = _employee_context(app_mod, employee)["name"]
        consequence = (
            f"Approve {employee_name}'s leave and notify the employee."
            if action == "approve"
            else f"Reject {employee_name}'s leave and notify the employee."
        )
        return prepare_mobile_confirmation(
            app_mod,
            context,
            idempotency_key=request.idempotency_key,
            action_type=MOBILE_ACTIONS[f"{action}_leave"],
            target_type="leave_request",
            target_id=str(leave_id),
            expected_status=str(leave.get("status") or ""),
            safe_summary=f"{employee_name} · {leave.get('leave_type') or 'Leave request'}",
            consequence=consequence,
            args={
                "leave_id": str(leave_id),
                "decision_note": str(request.reason or "").strip() or None,
            },
        )

    @app_mod.app.get("/dashboard/mobile/candidates")
    def mobile_candidates(
        q: str = Query(default=""),
        position: str = Query(default=""),
        status: str = Query(default=""),
        limit: int = Query(default=20, ge=1, le=50),
        context: dict[str, Any] = Depends(dependency),
    ):
        return mobile_candidate_rankings(
            app_mod,
            context,
            query=q,
            position=position,
            status=status,
            limit=limit,
        )

    @app_mod.app.get("/dashboard/mobile/candidates/{app_key}")
    def mobile_candidate(
        app_key: str,
        context: dict[str, Any] = Depends(dependency),
    ):
        return mobile_candidate_detail(app_mod, context, app_key)

    @app_mod.app.get("/dashboard/mobile/candidates/{app_key}/cv")
    def mobile_candidate_cv(
        app_key: str,
        context: dict[str, Any] = Depends(dependency),
    ):
        app_mod.require_entitlement(context, "pre_hiring", "prehire.read")
        return app_mod.dashboard_prehire_application_cv(app_key, context=context)

    @app_mod.app.get("/dashboard/mobile/candidates/{app_key}/cv/preview")
    def mobile_candidate_cv_preview(
        app_key: str,
        context: dict[str, Any] = Depends(dependency),
    ):
        app_mod.require_entitlement(context, "pre_hiring", "prehire.read")
        return app_mod.dashboard_prehire_application_cv_preview(app_key, context=context)

    @app_mod.app.post("/dashboard/mobile/candidates/{app_key}/decision")
    def mobile_candidate_decision(
        app_key: str,
        request: CandidateActionRequest,
        context: dict[str, Any] = Depends(dependency),
    ):
        app_mod.require_entitlement(context, "pre_hiring", "prehire.read")
        action = str(request.action or "").strip().lower()
        if action not in {"shortlist", "reject", "hire"}:
            raise app_mod.HTTPException(
                status_code=400,
                detail={"error": "unsupported_candidate_action", "message": "That candidate action is not supported."},
            )
        permission = "candidate.manage" if action == "shortlist" else "candidate.decide"
        if not app_mod.dashboard_context_has_permission(context, permission):
            raise app_mod.HTTPException(
                status_code=403,
                detail={"error": "action_forbidden", "message": "You do not have access to do that."},
            )
        application = app_mod.dashboard_application_or_404(app_key, context["company_code"])
        if request.confirm:
            return confirm_mobile_action(
                app_mod,
                context,
                confirmation_id=str(request.confirmation_id or ""),
                confirmation_hash=str(request.confirmation_hash or ""),
                expected_target_type="application",
                expected_target_id=app_key,
                expected_action_types={MOBILE_ACTIONS[action]},
            )
        status = str(application.get("status") or "")
        if status in {"hired", "rejected"}:
            raise app_mod.HTTPException(
                status_code=409,
                detail={"error": "already_decided", "message": "This candidate already has a final decision."},
            )
        summary = app_mod.prehire_application_summary(application, include_raw=False)
        candidate = summary.get("candidate") if isinstance(summary.get("candidate"), dict) else {}
        position_data = summary.get("position") if isinstance(summary.get("position"), dict) else {}
        name = candidate.get("name") or "Candidate"
        position_title = position_data.get("title") or "this role"
        consequences = {
            "shortlist": f"Move {name} to the shortlist for {position_title}.",
            "reject": f"Reject {name} for {position_title}. This removes them from the active pipeline.",
            "hire": f"Hire {name} for {position_title}. This creates the employee and starts post-hire setup.",
        }
        return prepare_mobile_confirmation(
            app_mod,
            context,
            idempotency_key=request.idempotency_key,
            action_type=MOBILE_ACTIONS[action],
            target_type="application",
            target_id=app_key,
            expected_status=status,
            safe_summary=f"{name} · {position_title}",
            consequence=consequences[action],
            args={"app_key": app_key, "reason": str(request.reason or "").strip() or None},
        )

    @app_mod.app.get("/dashboard/mobile/tasks")
    def mobile_tasks(
        status: str = Query(default="open"),
        offset: int = Query(default=0, ge=0),
        limit: int = Query(default=30, ge=1, le=100),
        context: dict[str, Any] = Depends(dependency),
    ):
        normalized = ",".join(
            value
            for value in [part.strip().lower() for part in str(status or "").split(",")]
            if value in {"open", "done", "dismissed"}
        )
        if not normalized:
            raise app_mod.HTTPException(
                status_code=400,
                detail={"error": "invalid_task_status", "message": "That task status is not valid."},
            )
        return mobile_hr_tasks(
            app_mod,
            context,
            status=normalized,
            offset=offset,
            limit=limit,
        )

    @app_mod.app.get("/dashboard/mobile/onboarding")
    def mobile_onboarding(
        offset: int = Query(default=0, ge=0),
        limit: int = Query(default=30, ge=1, le=100),
        search: str = Query(default=""),
        context: dict[str, Any] = Depends(dependency),
    ):
        return mobile_onboarding_list(
            app_mod,
            context,
            offset=offset,
            limit=limit,
            search=search,
        )

    @app_mod.app.get("/dashboard/mobile/onboarding/{employee_key}")
    def mobile_onboarding_employee(
        employee_key: str,
        context: dict[str, Any] = Depends(dependency),
    ):
        return mobile_onboarding_detail(app_mod, context, employee_key)

    @app_mod.app.post("/dashboard/mobile/onboarding/{employee_key}/review")
    def mobile_onboarding_review(
        employee_key: str,
        request: OnboardingReviewRequest,
        context: dict[str, Any] = Depends(dependency),
    ):
        _require_mobile_feature_action(
            app_mod, context, "hr", "onboarding_review", "review"
        )
        app_mod.require_entitlement(context, "onboarding", "onboarding.manage")
        outcome = str(request.outcome or "").strip().lower()
        if outcome not in {"received", "waived"}:
            raise app_mod.HTTPException(
                status_code=400,
                detail={
                    "error": "unsupported_onboarding_outcome",
                    "message": "That onboarding review outcome is not supported.",
                },
            )
        target_id = f"{employee_key}:{str(request.item_id or '').strip()}"
        item, employee = _load_onboarding_item(app_mod, context, target_id)
        if request.confirm:
            return confirm_mobile_action(
                app_mod,
                context,
                confirmation_id=str(request.confirmation_id or ""),
                confirmation_hash=str(request.confirmation_hash or ""),
                expected_target_type="onboarding_item",
                expected_target_id=target_id,
                expected_action_types={MOBILE_ACTIONS["review_onboarding"]},
            )
        employee_name = _employee_context(app_mod, employee)["name"]
        item_label = item.get("label") or app_mod.item_display_label(item)
        verb = "Mark received" if outcome == "received" else "Waive"
        return prepare_mobile_confirmation(
            app_mod,
            context,
            idempotency_key=request.idempotency_key,
            action_type=MOBILE_ACTIONS["review_onboarding"],
            target_type="onboarding_item",
            target_id=target_id,
            expected_status=str(item.get("status") or ""),
            safe_summary=f"{employee_name} · {item_label}",
            consequence=f"{verb} for {employee_name}'s onboarding checklist.",
            args={
                "employee_key": employee_key,
                "item_id": str(request.item_id or "").strip(),
                "item_status": outcome,
                "notes": str(request.note or "").strip() or None,
            },
        )

    @app_mod.app.get("/dashboard/mobile/documents")
    def mobile_documents(
        q: str = Query(default=""),
        status: str = Query(default=""),
        offset: int = Query(default=0, ge=0),
        limit: int = Query(default=30, ge=1, le=100),
        context: dict[str, Any] = Depends(dependency),
    ):
        normalized = str(status or "").strip().lower()
        if normalized and normalized not in {
            "expired",
            "expiring_soon",
            "missing",
            "needs_review",
            "valid",
        }:
            raise app_mod.HTTPException(
                status_code=400,
                detail={
                    "error": "invalid_document_status",
                    "message": "That document status is not valid.",
                },
            )
        return mobile_document_reviews(
            app_mod,
            context,
            search=q,
            status=normalized,
            offset=offset,
            limit=limit,
        )

    # Register the fixed files segment before the two-parameter detail route.
    @app_mod.app.get("/dashboard/mobile/documents/files/{file_id}")
    def mobile_document_file(
        file_id: str,
        disposition: str = Query(default="inline"),
        context: dict[str, Any] = Depends(dependency),
    ):
        _require_mobile_feature_action(app_mod, context, "hr", "document_review", "read")
        mode = "attachment" if str(disposition).lower() == "attachment" else "inline"
        return app_mod.dashboard_posthire_document_file(
            file_id,
            disposition=mode,
            context=context,
        )

    @app_mod.app.get("/dashboard/mobile/documents/{employee_key}/{document_type}")
    def mobile_document(
        employee_key: str,
        document_type: str,
        context: dict[str, Any] = Depends(dependency),
    ):
        return mobile_document_detail(
            app_mod, context, employee_key, document_type
        )

    @app_mod.app.post("/dashboard/mobile/documents/{employee_key}/{document_type}/review")
    def mobile_compliance_review(
        employee_key: str,
        document_type: str,
        request: ComplianceReviewRequest,
        context: dict[str, Any] = Depends(dependency),
    ):
        _require_mobile_feature_action(
            app_mod, context, "hr", "document_review", "review"
        )
        app_mod.require_entitlement(context, "compliance", "compliance.manage")
        row = _find_compliance_document(
            app_mod, context, employee_key, document_type
        )
        current_status = str(row.get("status") or "")
        if (
            current_status != "needs_review"
            or str(request.expected_status or "") != current_status
        ):
            raise app_mod.HTTPException(
                status_code=409,
                detail={
                    "error": "stale_decision",
                    "message": "This document changed since you reviewed it.",
                    "current_status": current_status,
                },
            )
        employee = app_mod.find_employee_by_key(
            employee_key, company_code=context["company_code"]
        )
        if not employee or not app_mod.context_manager_allows_employee(
            context, employee, company_code=context["company_code"]
        ):
            raise app_mod.HTTPException(
                status_code=404,
                detail={"error": "document_not_found", "message": "This document was not found."},
            )
        result = _execute_registry_action(
            app_mod,
            context,
            MOBILE_ACTIONS["review_compliance"],
            {
                "employee_phone": employee.get("phone"),
                "document_type": document_type,
                "notes": str(request.note or "").strip() or None,
            },
            "compliance_document",
        )
        if result.get("status") == "needs_confirmation":
            raise app_mod.HTTPException(
                status_code=409,
                detail={
                    "error": "confirmation_policy_changed",
                    "message": "This review could not be completed safely.",
                },
            )
        return {
            "ok": bool(result.get("ok")),
            "status": result.get("status"),
            "result": app_mod.json_safe(result.get("result")),
        }

    @app_mod.app.get("/dashboard/mobile/attendance")
    def mobile_attendance(
        start_date: str | None = Query(default=None),
        end_date: str | None = Query(default=None),
        status: str | None = Query(default=None),
        offset: int = Query(default=0, ge=0),
        limit: int = Query(default=100, ge=1, le=200),
        context: dict[str, Any] = Depends(dependency),
    ):
        return mobile_attendance_list(
            app_mod,
            context,
            start_date=start_date,
            end_date=end_date,
            status=status,
            offset=offset,
            limit=limit,
        )

    @app_mod.app.get("/dashboard/mobile/attendance/{attendance_id}")
    def mobile_attendance_record(
        attendance_id: str,
        context: dict[str, Any] = Depends(dependency),
    ):
        return mobile_attendance_detail(app_mod, context, attendance_id)

    @app_mod.app.post("/dashboard/mobile/attendance/{attendance_id}/resolve")
    def mobile_attendance_resolve(
        attendance_id: str,
        request: AttendanceResolveRequest,
        context: dict[str, Any] = Depends(dependency),
    ):
        _require_mobile_feature_action(
            app_mod, context, "hr", "attendance_exceptions", "resolve"
        )
        app_mod.require_entitlement(context, "attendance", "attendance.manage")
        status = str(request.status or "").strip().lower()
        if status not in {"present", "late", "absent", "completed"}:
            raise app_mod.HTTPException(
                status_code=400,
                detail={
                    "error": "invalid_attendance_resolution",
                    "message": "That attendance status is not valid.",
                },
            )
        attendance, employee = _load_attendance(app_mod, context, attendance_id)
        if request.confirm:
            return confirm_mobile_action(
                app_mod,
                context,
                confirmation_id=str(request.confirmation_id or ""),
                confirmation_hash=str(request.confirmation_hash or ""),
                expected_target_type="attendance_record",
                expected_target_id=attendance_id,
                expected_action_types={MOBILE_ACTIONS["resolve_attendance"]},
            )
        employee_name = _employee_context(app_mod, employee)["name"]
        return prepare_mobile_confirmation(
            app_mod,
            context,
            idempotency_key=request.idempotency_key,
            action_type=MOBILE_ACTIONS["resolve_attendance"],
            target_type="attendance_record",
            target_id=attendance_id,
            expected_status=str(attendance.get("status") or ""),
            safe_summary=f"{employee_name} · {_iso(attendance.get('attendance_date'))}",
            consequence=f"Correct {employee_name}'s attendance status to {status}.",
            args={
                "employee_phone": employee.get("phone"),
                "date": _iso(attendance.get("attendance_date")),
                "status": status,
                "time": str(request.time or "").strip() or None,
                "notes": str(request.notes or "").strip() or None,
            },
        )

    @app_mod.app.get("/dashboard/mobile/shifts")
    def mobile_shifts(
        date: str | None = Query(default=None),
        week: int | None = Query(default=None, ge=-26, le=26),
        offset: int = Query(default=0, ge=0),
        limit: int = Query(default=100, ge=1, le=200),
        context: dict[str, Any] = Depends(dependency),
    ):
        if date is not None or week is None:
            day = mobile_day_shifts(
                app_mod,
                context,
                shift_date=date,
                offset=offset,
                limit=limit,
            )
            return {
                **day,
                "shifts": day["items"],
                "start_date": day["date"],
                "end_date": day["date"],
                "week": None,
            }
        _require_mobile_feature_action(app_mod, context, "hr", "today_shifts", "read")
        result = app_mod.dashboard_posthire_shifts(
            week=week, offset=offset, limit=limit, context=context
        )
        items = [shift_mobile_item(app_mod, row) for row in result.get("shifts") or []]
        return {
            "ok": True,
            "items": items,
            "shifts": items,
            "start_date": result.get("start_date"),
            "end_date": result.get("end_date"),
            "week": result.get("week"),
            "total": int(result.get("total_count") or 0),
            "total_count": int(result.get("total_count") or 0),
            "limit": int(result.get("limit") or limit),
            "offset": int(result.get("offset") or offset),
            "has_more": bool(result.get("has_more")),
        }

    @app_mod.app.get("/dashboard/mobile/shift-swaps")
    def mobile_shift_swap_list(
        status: str = Query(default="requested"),
        limit: int = Query(default=100, ge=1, le=200),
        context: dict[str, Any] = Depends(dependency),
    ):
        normalized = str(status or "").strip().lower()
        if normalized not in {"requested", "approved", "rejected", "cancelled"}:
            raise app_mod.HTTPException(
                status_code=400,
                detail={
                    "error": "invalid_shift_swap_status",
                    "message": "That shift-swap status is not valid.",
                },
            )
        return mobile_shift_swaps(
            app_mod, context, status=normalized, limit=limit
        )

    @app_mod.app.get("/dashboard/mobile/shift-swaps/{swap_id}")
    def mobile_shift_swap(
        swap_id: str,
        context: dict[str, Any] = Depends(dependency),
    ):
        return mobile_shift_swap_detail(app_mod, context, swap_id)

    @app_mod.app.post("/dashboard/mobile/shift-swaps/{swap_id}/decision")
    def mobile_shift_swap_decision(
        swap_id: str,
        request: ShiftSwapDecisionRequest,
        context: dict[str, Any] = Depends(dependency),
    ):
        action = str(request.action or "").strip().lower()
        if action not in {"approve", "reject"}:
            raise app_mod.HTTPException(
                status_code=400,
                detail={
                    "error": "unsupported_shift_swap_action",
                    "message": "That shift-swap decision is not supported.",
                },
            )
        _require_mobile_feature_action(
            app_mod, context, "hr", "shift_swap_decisions", action
        )
        app_mod.require_entitlement(context, "shifts", "shifts.manage")
        swap, _, _ = _load_shift_swap(app_mod, context, swap_id)
        if str(swap.get("status") or "") != "requested":
            raise app_mod.HTTPException(
                status_code=409,
                detail={
                    "error": "already_decided",
                    "message": "This shift swap already has a decision.",
                },
            )
        if request.confirm:
            return confirm_mobile_action(
                app_mod,
                context,
                confirmation_id=str(request.confirmation_id or ""),
                confirmation_hash=str(request.confirmation_hash or ""),
                expected_target_type="shift_swap",
                expected_target_id=swap_id,
                expected_action_types={MOBILE_ACTIONS[f"{action}_shift_swap"]},
            )
        requester_name = str(swap.get("requester_employee_name") or "Employee")
        consequence = (
            f"Approve {requester_name}'s shift swap and update the affected shifts."
            if action == "approve"
            else f"Reject {requester_name}'s shift swap."
        )
        return prepare_mobile_confirmation(
            app_mod,
            context,
            idempotency_key=request.idempotency_key,
            action_type=MOBILE_ACTIONS[f"{action}_shift_swap"],
            target_type="shift_swap",
            target_id=swap_id,
            expected_status="requested",
            safe_summary=f"{requester_name} · {_iso(swap.get('shift_date'))}",
            consequence=consequence,
            args={"swap_id": swap_id},
        )

    @app_mod.app.get("/dashboard/mobile/interviews")
    def mobile_interview_list(
        status: str | None = Query(default=None),
        q: str | None = Query(default=None),
        role: str | None = Query(default=None),
        date: str | None = Query(default=None),
        interviewer: str | None = Query(default=None),
        limit: int = Query(default=50, ge=1, le=100),
        offset: int = Query(default=0, ge=0),
        context: dict[str, Any] = Depends(dependency),
    ):
        return mobile_interviews(
            app_mod,
            context,
            status=status,
            query=q,
            role=role,
            date_filter=date,
            interviewer=interviewer,
            limit=limit,
            offset=offset,
        )

    @app_mod.app.get("/dashboard/mobile/interviews/{interview_id}")
    def mobile_interview(
        interview_id: str,
        context: dict[str, Any] = Depends(dependency),
    ):
        return mobile_interview_detail(app_mod, context, interview_id)

    @app_mod.app.post("/dashboard/mobile/interviews/{interview_id}/notes")
    def mobile_interview_notes(
        interview_id: str,
        request: InterviewNotesRequest,
        context: dict[str, Any] = Depends(dependency),
    ):
        _require_mobile_feature_action(
            app_mod, context, "recruiting", "interview_notes", "write"
        )
        app_mod.require_entitlement(context, "pre_hiring", "interview.manage")
        _load_interview(app_mod, context, interview_id)
        notes = str(request.notes or "").strip()
        if not notes:
            raise app_mod.HTTPException(
                status_code=422,
                detail={
                    "error": "interview_notes_required",
                    "message": "Add notes before saving.",
                },
            )
        app_mod.dashboard_prehire_interview_notes(
            interview_id,
            app_mod.DashboardInterviewNotesRequest(
                notes=notes,
                transcript=None,
                status=request.status,
                generate_summary=bool(request.generate_summary),
            ),
            context=context,
        )
        return mobile_interview_detail(app_mod, context, interview_id)

    @app_mod.app.get("/dashboard/mobile/employees")
    def mobile_employees(
        search: str = Query(default=""),
        offset: int = Query(default=0, ge=0),
        limit: int = Query(default=30, ge=1, le=100),
        context: dict[str, Any] = Depends(dependency),
    ):
        return mobile_employee_directory(
            app_mod,
            context,
            offset=offset,
            limit=limit,
            search=search,
        )

    @app_mod.app.get("/dashboard/mobile/employees/{employee_key}")
    def mobile_employee(
        employee_key: str,
        context: dict[str, Any] = Depends(dependency),
    ):
        return mobile_employee_quick_profile(app_mod, context, employee_key)

    @app_mod.app.get("/dashboard/mobile/delivery-alerts")
    def mobile_delivery_alerts(
        offset: int = Query(default=0, ge=0),
        limit: int = Query(default=30, ge=1, le=100),
        context: dict[str, Any] = Depends(dependency),
    ):
        return mobile_delivery_alert_queue(
            app_mod,
            context,
            limit=limit,
            offset=offset,
        )
