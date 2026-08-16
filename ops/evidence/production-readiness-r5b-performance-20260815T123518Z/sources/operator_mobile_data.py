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
    status = str(row.get("status") or "")
    # Advertise resolve only on open tasks when the feature grants it.
    allowed = [
        action
        for action in actions
        if action != "resolve" or status == "open"
    ]
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
        "status": status or None,
        "priority": row.get("priority"),
        "created_at": _iso(row.get("created_at")),
        "updated_at": _iso(row.get("updated_at")),
        "allowed_actions": allowed,
        "destination": f"/tasks/{task_id}",
    }


def _load_hr_task(app_mod: Any, context: dict[str, Any], task_id: str) -> dict[str, Any]:
    """Load one task under the same tenant + manager scope as the open queue."""
    company = context["company_code"]
    scope = context.get("scope") if isinstance(context.get("scope"), dict) else None
    row = app_mod._outbound_delivery.get_hr_task(
        company_code=company,
        task_id=task_id,
        scope=scope,
    )
    if not row:
        raise app_mod.HTTPException(
            status_code=404,
            detail={"error": "task_not_found", "message": "This task was not found."},
        )
    employee_key = str(row.get("employee_key") or "").strip()
    if employee_key:
        employee = app_mod.find_employee_by_key(employee_key, company_code=company)
        if not employee or not app_mod.context_manager_allows_employee(
            context, employee, company_code=company
        ):
            raise app_mod.HTTPException(
                status_code=404,
                detail={"error": "task_not_found", "message": "This task was not found."},
            )
    elif scope and scope.get("restricted"):
        # Company-wide tasks stay HR-only (matches list_hr_tasks NULL-key rule).
        raise app_mod.HTTPException(
            status_code=404,
            detail={"error": "task_not_found", "message": "This task was not found."},
        )
    return row


def mobile_hr_tasks(
    app_mod: Any,
    context: dict[str, Any],
    *,
    status: str = "open",
    offset: int = 0,
    limit: int = 30,
) -> dict[str, Any]:
    """Open follow-up queue by default — history stays web-first."""
    feature = _require_mobile_feature_action(app_mod, context, "hr", "hr_tasks", "read")
    bucket = str(status or "").strip().lower() or "open"
    result = app_mod.dashboard_hr_tasks(
        status=bucket,
        limit=max(1, min(int(limit or 30), 100)),
        offset=max(0, int(offset or 0)),
        context=context,
    )
    items = [
        hr_task_mobile_item(row, actions=_actions(feature))
        for row in result.get("tasks") or []
    ]
    if bucket == "open":
        items = [row for row in items if str(row.get("status") or "") == "open"]
    resolved_offset = int(result.get("offset") or 0)
    resolved_limit = int(result.get("limit") or limit)
    total = int(result.get("total") or 0)
    return {
        "ok": True,
        "items": items,
        "open_count": int(result.get("open_count") or 0),
        "total": total,
        "offset": resolved_offset,
        "limit": resolved_limit,
        "has_more": (resolved_offset + resolved_limit) < total,
        "status": bucket,
    }


def mobile_hr_task_detail(
    app_mod: Any,
    context: dict[str, Any],
    task_id: str,
) -> dict[str, Any]:
    feature = _require_mobile_feature_action(app_mod, context, "hr", "hr_tasks", "read")
    row = _load_hr_task(app_mod, context, task_id)
    return {
        "ok": True,
        "task": hr_task_mobile_item(row, actions=_actions(feature)),
    }


def mobile_hr_task_resolve(
    app_mod: Any,
    context: dict[str, Any],
    task_id: str,
    *,
    status: str = "done",
    expected_status: str = "open",
) -> dict[str, Any]:
    """Mark done via canonical resolve_hr_task + web handoff side effects.

    Enforces manage capability and the same manager scope as the read path.
    Mobile v1 accepts ``done`` only (dismiss stays web-first).
    """
    _require_mobile_feature_action(app_mod, context, "hr", "hr_tasks", "resolve")
    # Same manage gate as dashboard_hr_task_resolve.
    company = app_mod._hr_tasks_context(context, manage=True)
    normalized = str(status or "done").strip().lower()
    if normalized != "done":
        raise app_mod.HTTPException(
            status_code=400,
            detail={
                "error": "unsupported_task_status",
                "message": "Mobile can only mark tasks done.",
            },
        )
    row = _load_hr_task(app_mod, context, task_id)
    current_status = str(row.get("status") or "")
    if current_status != "open" or str(expected_status or "") != current_status:
        raise app_mod.HTTPException(
            status_code=409,
            detail={
                "error": "stale_decision",
                "message": "This task changed since you reviewed it.",
                "current_status": current_status,
            },
        )
    result = app_mod._outbound_delivery.resolve_hr_task(
        company_code=company,
        task_id=task_id,
        status="done",
        resolver_phone=context.get("hr_phone"),
        expected_status=current_status,
    )
    if result.get("error") == "stale_decision":
        # Lost the race between the read above and the write.
        raise app_mod.HTTPException(
            status_code=409,
            detail={
                "error": "stale_decision",
                "message": "This task changed since you reviewed it.",
                "current_status": result.get("current_status"),
            },
        )
    if not result.get("ok"):
        raise app_mod.HTTPException(
            status_code=404,
            detail={"error": result.get("error") or "task_not_found", "message": "This task was not found."},
        )
    task = result.get("task") if isinstance(result.get("task"), dict) else {}
    if not task.get("task_type"):
        task["task_type"] = row.get("task_type")
    if task.get("metadata") is None and row.get("metadata") is not None:
        task["metadata"] = row.get("metadata")
    if str(task.get("task_type") or "") == "candidate_handoff":
        import recruiting_lifecycle as _rl

        result["handoff_resume"] = _rl.resume_candidate_handoff(
            app_mod,
            company_code=company,
            task=task,
            resumed_by=context.get("hr_phone") or context.get("actor_user_id"),
        )
    app_mod.record_admin_audit(
        context,
        "hr_task_resolved",
        summary="Marked HR task done.",
        target_type="hr_task",
        target=task_id,
        details={"status": "done", "source": task.get("source"), "via": "operator_mobile"},
    )
    return app_mod.json_safe(
        {
            "ok": True,
            "status": "done",
            "result": result,
            "task": hr_task_mobile_item(
                {**row, **task, "status": "done", "employee_name": row.get("employee_name")},
                actions=[],
            ),
        }
    )


def onboarding_mobile_item(
    app_mod: Any,
    row: dict[str, Any],
    *,
    actions: list[str],
    hr_actionable_count: int = 0,
) -> dict[str, Any]:
    employee_key = str(row.get("employee_key") or "")
    status = str(row.get("onboarding_status") or row.get("status") or "")
    return {
        "employee_key": employee_key,
        "employee": _employee_identity(app_mod, row),
        "status": status,
        "pending_count": int(row.get("pending_count") or 0),
        "received_count": int(row.get("received_count") or 0),
        "hr_actionable_count": int(hr_actionable_count or 0),
        "updated_at": _iso(row.get("updated_at")),
        "allowed_actions": list(actions),
        "destination": f"/onboarding/{employee_key}",
    }


def _is_bank_ess_item(item: dict[str, Any]) -> bool:
    item_id = str(item.get("item_id") or "").lower()
    mode = str(item.get("collection_mode") or "").lower()
    authority = str(item.get("authority") or "").lower()
    return (
        item_id == "bank_details"
        or mode == "ess_encrypted"
        or authority == "ess"
    )


def onboarding_checklist_mobile_item(
    app_mod: Any,
    item: dict[str, Any],
    *,
    file_id: str | None,
    feature_actions: list[str],
    can_mutate: bool,
    lifecycle_on: bool,
) -> dict[str, Any]:
    """Map a projection row to mobile — reuse lifecycle group + HR actions."""
    import onboarding_lifecycle_wave2a as _lc

    item_id = str(item.get("item_id") or "")
    status = str(item.get("status") or "")
    group = str(item.get("group") or _lc.group_key_for_item(item) or "")
    hr_actions = list(
        item.get("actions")
        or _lc.actions_for_hr_item(
            item,
            can_mutate=can_mutate,
            can_upload=False,
            lifecycle_on=lifecycle_on,
        )
    )
    is_bank = _is_bank_ess_item(item)
    mobile_actions: list[str] = []
    # Preview whenever a file exists (also when bank has attachments).
    if file_id or "preview" in hr_actions:
        mobile_actions.append("preview")
    if group == "being_reviewed":
        if is_bank:
            # Bank ESS / web handoff only — never accept/waive bank on mobile.
            mobile_actions.append("review_bank")
        elif can_mutate and "review" in feature_actions:
            if "mark_complete" in hr_actions:
                mobile_actions.append("accept")
            if "waive" in hr_actions:
                mobile_actions.append("waive")
    return {
        "item_id": item_id,
        "label": item.get("label") or app_mod.item_display_label(item),
        "item_type": item.get("item_type"),
        "document_type": item.get("document_type"),
        "required": bool(item.get("required")),
        "status": status,
        "group": group,
        "is_bank_ess": is_bank,
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
        "allowed_actions": mobile_actions,
    }


def _map_onboarding_projection_items(
    app_mod: Any,
    result: dict[str, Any],
    *,
    feature_actions: list[str],
    can_mutate: bool,
    lifecycle_on: bool,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    index = result.get("document_index") if isinstance(result.get("document_index"), dict) else {}

    def _map_bucket(rows: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        for item in rows or []:
            file_id = index.get(str(item.get("item_id") or "")) or index.get(
                str(item.get("document_type") or "")
            )
            if not file_id and item.get("file_id"):
                file_id = item.get("file_id")
            out.append(
                onboarding_checklist_mobile_item(
                    app_mod,
                    item,
                    file_id=str(file_id) if file_id else None,
                    feature_actions=feature_actions,
                    can_mutate=can_mutate,
                    lifecycle_on=lifecycle_on,
                )
            )
        return out

    hr_actionable = _map_bucket(result.get("being_reviewed"))
    waiting = _map_bucket(result.get("your_actions"))
    return hr_actionable, waiting


def mobile_onboarding_list(
    app_mod: Any,
    context: dict[str, Any],
    *,
    offset: int = 0,
    limit: int = 30,
    search: str = "",
) -> dict[str, Any]:
    """HR-actionable queue only — employees with being_reviewed items."""
    feature = _require_mobile_feature_action(app_mod, context, "hr", "onboarding_review", "read")
    feature_actions = _actions(feature)
    company = str(context.get("company_code") or "")
    can_mutate = bool(
        "review" in feature_actions
        and callable(getattr(app_mod, "onboarding_hr_mutate_enabled_for_company", None))
        and app_mod.onboarding_hr_mutate_enabled_for_company(company)
    )
    page_limit = max(1, min(int(limit or 30), 100))
    page_offset = max(0, int(offset or 0))
    # Canonical SQL page of employees with ≥1 HR-review checklist item — never
    # scan a truncated in_progress window and miss actionable rows past ~90.
    page = app_mod.list_onboarding_hr_actionable_page(
        company,
        viewer_phone=context.get("hr_phone"),
        dashboard_user_id=context.get("actor_user_id"),
        actor_role=context.get("actor_role"),
        search=str(search or ""),
        limit=page_limit,
        offset=page_offset,
    )
    items: list[dict[str, Any]] = []
    for row in page.get("rows") or []:
        employee_key = str(row.get("employee_key") or "")
        if not employee_key:
            continue
        emp_actions = ["read"]
        if can_mutate:
            emp_actions.append("review")
        items.append(
            onboarding_mobile_item(
                app_mod,
                row,
                actions=emp_actions,
                hr_actionable_count=int(row.get("hr_actionable_count") or 0),
            )
        )
    return {
        "ok": True,
        "items": items,
        "completed_count": 0,
        "total": int(page.get("total_count") or len(items)),
        "total_count": int(page.get("total_count") or len(items)),
        "limit": page_limit,
        "offset": page_offset,
        "has_more": bool(page.get("has_more")),
        "hr_mutate_enabled": can_mutate,
    }


def mobile_onboarding_detail(
    app_mod: Any,
    context: dict[str, Any],
    employee_key: str,
) -> dict[str, Any]:
    feature = _require_mobile_feature_action(app_mod, context, "hr", "onboarding_review", "read")
    feature_actions = _actions(feature)
    result = app_mod.dashboard_posthire_onboarding_detail(employee_key, context=context)
    employee = app_mod.find_employee_by_key(employee_key, company_code=context["company_code"])
    company = str(context.get("company_code") or "")
    can_mutate = bool(
        "review" in feature_actions
        and callable(getattr(app_mod, "onboarding_hr_mutate_enabled_for_company", None))
        and app_mod.onboarding_hr_mutate_enabled_for_company(company)
    )
    lifecycle_on = True
    try:
        import onboarding_lifecycle_wave2a as _lc

        lifecycle_on = bool(
            _lc.lifecycle_enabled(company_code=company, employee_key=str(employee_key))
        )
    except Exception:
        lifecycle_on = True
    hr_items, waiting_items = _map_onboarding_projection_items(
        app_mod,
        result,
        feature_actions=feature_actions,
        can_mutate=can_mutate,
        lifecycle_on=lifecycle_on,
    )
    emp_actions = ["read"]
    if can_mutate and hr_items:
        emp_actions.append("review")
    return {
        "ok": True,
        "onboarding": {
            "employee_key": str(employee_key),
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
            "hr_actionable_count": len(hr_items),
            "hr_actionable_items": hr_items,
            "waiting_on_employee_items": waiting_items,
            # Back-compat: items = HR-actionable only (never all open work).
            "items": hr_items,
            "hr_mutate_enabled": can_mutate,
            "allowed_actions": emp_actions,
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
    """Document Reviews queue — default needs_review only on compliance path."""
    feature = _require_mobile_feature_action(app_mod, context, "hr", "document_review", "read")
    permissions = {str(value) for value in context.get("permissions") or []}
    company = context["company_code"]
    # Mobile default = action queue (needs_review). Explicit status still supported.
    bucket = str(status or "").strip().lower() or "needs_review"
    if app_mod.company_has_module(company, "compliance") and "compliance.read" in permissions:
        compliance_actions = ["read"]
        if "review" in _actions(feature) and "compliance.manage" in permissions:
            compliance_actions.append("review")
        result = _mobile_compliance_payload(
            app_mod,
            context,
            search=search,
            status=bucket,
            offset=offset,
            limit=limit,
        )
        items = [
            compliance_mobile_item(app_mod, row, actions=compliance_actions)
            for row in result.get("documents") or []
        ]
        # Belt-and-suspenders: never surface non-needs_review when defaulting the queue.
        if bucket == "needs_review":
            items = [row for row in items if str(row.get("status") or "") == "needs_review"]
        return {
            "ok": True,
            "items": items,
            "summary": app_mod.json_safe(result.get("summary") or {}),
            "total": int(result.get("filtered_total") or len(items)),
            "offset": int(result.get("offset") or 0),
            "limit": int(result.get("limit") or limit),
            "has_more": bool(result.get("has_more")),
            "status": bucket,
            "source": "compliance",
        }

    # Onboarding-only tenants: preview/context rows only — never compliance decide.
    # Do not fan onboarding into Documents when compliance module is enabled (above).
    onboarding = mobile_onboarding_list(
        app_mod,
        context,
        offset=offset,
        limit=limit,
        search=search,
    )
    items: list[dict[str, Any]] = []
    for card in onboarding["items"]:
        employee_key = str(
            card.get("employee_key")
            or (card.get("employee") or {}).get("employee_key")
            or ""
        )
        detail = mobile_onboarding_detail(app_mod, context, employee_key)
        for item in (detail.get("onboarding") or {}).get("hr_actionable_items") or []:
            if item.get("document_type") or item.get("item_type") == "document":
                items.append(
                    {
                        "document_id": f"{employee_key}:{item.get('item_id')}",
                        "source": "onboarding",
                        "employee": card.get("employee"),
                        "name": item.get("label") or item.get("item_id"),
                        "label": item.get("label"),
                        "document_type": item.get("document_type") or item.get("item_id"),
                        "status": item.get("status") or "needs_review",
                        "has_file": bool(item.get("has_file") or item.get("preview_path")),
                        "preview_path": item.get("preview_path"),
                        "download_path": item.get("download_path"),
                        "destination": f"/onboarding/{employee_key}",
                        "allowed_actions": [
                            a for a in (item.get("allowed_actions") or []) if a == "preview"
                        ],
                    }
                )
    return {
        "ok": True,
        "items": items,
        "summary": {"needs_attention": len(items)},
        "total": len(items),
        "offset": onboarding["offset"],
        "limit": onboarding["limit"],
        "has_more": onboarding["has_more"],
        "status": "needs_review",
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
            # Exceptional People-row chip authority (not daily attendance).
            "onboarding_status": card.get("onboarding_status"),
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
    channel = (
        str(row.get("channel_used") or "").strip()
        or str(row.get("flow_label") or "").strip()
        or str(row.get("flow") or "").strip()
        or None
    )
    return {
        "alert_id": message_id,
        "employee": {
            "employee_key": employee_key or None,
            "name": row.get("employee_name") or None,
        },
        "title": row.get("flow_label") or row.get("flow") or "Delivery alert",
        "summary": row.get("reason"),
        "status": row.get("status"),
        "kind": row.get("kind"),
        "channel": channel,
        "flow": row.get("flow"),
        "flow_label": row.get("flow_label"),
        "occurred_at": _iso(row.get("last_attempt_at")),
        "suggested_action": row.get("suggested_action"),
        "attempts": int(row.get("attempts") or 0),
        "has_task": bool(row.get("has_task")),
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
    """Read-only outbound monitor — excludes rows already linked to an HR task."""
    _require_mobile_feature_action(app_mod, context, "hr", "delivery_alerts", "read")
    result = app_mod.dashboard_outbound_needs_follow_up(
        limit=max(1, min(int(limit or 30), 100)),
        offset=max(0, int(offset or 0)),
        exclude_linked_tasks=True,
        context=context,
    )
    messages = [
        row for row in (result.get("messages") or []) if not row.get("has_task")
    ]
    return {
        "ok": True,
        "items": [delivery_alert_mobile_item(row) for row in messages],
        "total": int(result.get("total") or 0),
        "limit": int(result.get("limit") or limit),
        "offset": int(result.get("offset") or offset),
        "has_more": int(result.get("offset") or offset)
        + len(messages)
        < int(result.get("total") or 0),
        "exclude_linked_tasks": True,
    }


def attendance_mobile_item(
    app_mod: Any,
    row: dict[str, Any],
    *,
    actions: list[str],
) -> dict[str, Any]:
    attendance_id = str(row.get("attendance_id") or "")
    status = str(row.get("status") or "")
    kind = app_mod.attendance_exception_kind(row)
    is_exception = bool(kind) or app_mod.attendance_row_is_exception(row)
    # Resolve is only offered on genuine exceptions. Under authority this maps to
    # request_correction (often pending_review) — never claim the day is fixed.
    reviewable = is_exception and status not in {"approved_leave", "void"}
    can_resolve = "resolve" in actions and reviewable
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
        "exception_kind": kind,
        "is_exception": is_exception,
        "late_minutes": int(row.get("late_minutes") or 0),
        "early_leave_minutes": int(row.get("early_leave_minutes") or 0),
        "notes": row.get("notes"),
        "updated_at": _iso(row.get("updated_at")),
        # Honest governance: mobile resolve prepares correct_attendance_record,
        # which requests a correction when authority is enabled.
        "action_mode": "request_correction" if can_resolve else "read",
        "allowed_actions": ["resolve"] if can_resolve else [],
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
    status_norm = str(status or result.get("status_filter") or "").strip().lower()
    mapped = [
        attendance_mobile_item(app_mod, row, actions=_actions(feature))
        for row in result.get("attendance") or []
    ]
    # Never surface normal present/completed days as exceptions on mobile.
    if status_norm == "exceptions":
        mapped = [item for item in mapped if item.get("is_exception")]
    return {
        "ok": True,
        "items": mapped,
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
    """L0 assignment slice for mobile — read-only companion to web Schedule."""
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
        # Prefer governed assignment_type; fall back to legacy role label.
        "role": row.get("assignment_type") or row.get("role"),
        "location": row.get("location") or row.get("site_name") or row.get("branch_name"),
        "status": row.get("status") or row.get("ui_state") or "scheduled",
        "updated_at": _iso(row.get("updated_at")),
        "allowed_actions": ["read"],
        # Mobile has no shift-detail workflow yet — destination stays list-level.
        "destination": "/shifts",
    }


def _attach_swap_shifts(
    app_mod: Any,
    context: dict[str, Any],
    row: dict[str, Any],
    *,
    actions: list[str],
) -> dict[str, Any]:
    """Enrich a swap with both L0 sides (scoped by company)."""
    item = shift_swap_mobile_item(app_mod, row, actions=actions)
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
    company = str(context.get("company_code") or "").upper()
    if requester_shift and str(requester_shift.get("company_code") or "").upper() != company:
        requester_shift = None
    if target_shift and str(target_shift.get("company_code") or "").upper() != company:
        target_shift = None
    item["requester_shift"] = (
        shift_mobile_item(app_mod, requester_shift) if requester_shift else None
    )
    item["target_shift"] = shift_mobile_item(app_mod, target_shift) if target_shift else None
    return item



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
    offset: int = 0,
    limit: int = 100,
) -> dict[str, Any]:
    feature = _require_mobile_feature_action(
        app_mod, context, "hr", "shift_swap_decisions", "read"
    )
    app_mod.require_entitlement(context, "shifts", "shifts.manage")
    page_size = max(1, min(int(limit or 100), 200))
    start = max(0, int(offset or 0))
    # The swap reader has no offset and applies viewer scoping row by row, so we
    # pull the window plus one extra row to answer "is there more?" honestly
    # rather than letting the page silently look complete.
    result = app_mod.list_shift_swaps(
        {
            "company_code": context["company_code"],
            "status": status,
            "viewer_phone": context.get("hr_phone"),
            "viewer_user_id": context.get("actor_user_id"),
            "actor_role": context.get("actor_role"),
            "limit": min(start + page_size + 1, 500),
        },
        company_code=context["company_code"],
    )
    visible = []
    for row in result.get("swaps") or []:
        try:
            scoped, _, _ = _load_shift_swap(app_mod, context, str(row.get("swap_id") or ""))
        except app_mod.HTTPException:
            continue
        visible.append(scoped)
    window = visible[start : start + page_size]
    items = [
        _attach_swap_shifts(app_mod, context, scoped, actions=_actions(feature))
        for scoped in window
    ]
    return {
        "ok": True,
        "items": items,
        "total": len(visible),
        "offset": start,
        "limit": page_size,
        "has_more": len(visible) > start + page_size,
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
    return {
        "ok": True,
        "swap": _attach_swap_shifts(app_mod, context, row, actions=_actions(feature)),
    }


def _mobile_interview_allowed_actions(
    status_actions: list[str],
    note_actions: list[str],
) -> list[str]:
    """Only advertise interview actions mobile can execute.

    Cancel / reschedule / schedule remain web-only (capabilities mark them
    feature_disabled). Notes write is the sole mutation path on mobile.
    """
    try:
        import recruiting_lifecycle as _rl

        executable = _rl.MOBILE_EXECUTABLE_INTERVIEW_ACTIONS
    except Exception:
        executable = frozenset({"write", "write_notes", "read"})
    return sorted(
        {
            action
            for action in [*status_actions, *note_actions]
            if str(action) in executable
        }
    )


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
        "application_stage": row.get("application_stage"),
        "application_stage_label": row.get("application_stage_label"),
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
        "communication_status": row.get("communication_status"),
        "invitation_status": row.get("invitation_status"),
        "candidate_confirmation": row.get("candidate_confirmation"),
        "notes_status": row.get("notes_status"),
        "next_human_action": row.get("next_human_action"),
        "notes_available": bool(str(row.get("notes") or "").strip()),
        "updated_at": _iso(row.get("updated_at")),
        "notes_version": row.get("notes_version"),
        "allowed_actions": _mobile_interview_allowed_actions(status_actions, note_actions),
        "destination": f"/interviews/{interview_id}",
    }
    if detail:
        payload["notes"] = row.get("notes")
        payload["ai_summary"] = app_mod.json_safe(row.get("ai_summary") or {})
        payload["ai_advisory"] = True
        # Prefer locked-row concurrency fields when summary omitted them.
        if payload.get("notes_version") is None and row.get("notes_version") is not None:
            payload["notes_version"] = row.get("notes_version")
        if not payload.get("updated_at"):
            payload["updated_at"] = _iso(row.get("updated_at"))
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
    raw_row = _load_interview(app_mod, context, interview_id)
    application = app_mod.find_application_by_key(
        str(raw_row.get("app_key") or ""),
        company_code=context["company_code"],
    )
    row = app_mod.candidate_interview_summary(
        {
            **raw_row,
            "application_status": (application or {}).get("status"),
        }
    )
    # Concurrency tokens live on the interview row; keep them on the mobile DTO.
    if isinstance(row, dict):
        row = {
            **row,
            "notes_version": raw_row.get("notes_version", row.get("notes_version")),
            "updated_at": raw_row.get("updated_at") or row.get("updated_at"),
        }
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
    feature = _require_mobile_feature_action(app_mod, context, "hr", "leave_approvals", "read")
    app_mod.require_entitlement(context, "leave", "leave.read")
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
    feature = _require_mobile_feature_action(app_mod, context, "hr", "leave_approvals", "read")
    app_mod.require_entitlement(context, "leave", "leave.read")
    leave, employee = _load_leave(app_mod, context, leave_id)
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


def _authoritative_permissions(app_mod: Any, context: dict[str, Any]) -> set[str]:
    """Permissions from the same backend_current authority used by execution."""
    if hasattr(app_mod, "context_permissions"):
        return {str(item) for item in app_mod.context_permissions(context) if str(item).strip()}
    # Fail closed when authority helpers are unavailable.
    return set()


def _candidate_allowed_actions(app_mod: Any, context: dict[str, Any], status: str) -> list[str]:
    permissions = _authoritative_permissions(app_mod, context)
    try:
        import recruiting_lifecycle as _rl

        stage = _rl.normalize_stage(status) or str(status or "").strip().lower()
        return _rl.mobile_candidate_allowed_actions(stage, permissions)
    except Exception:
        if status in {"hired", "rejected", "withdrawn"}:
            return []
        actions: list[str] = []
        if "candidate.manage" in permissions and status != "shortlisted":
            actions.append("shortlist")
        if "candidate.decide" in permissions:
            # Hire is not valid from ready_for_review under the canonical matrix;
            # only advertise reject from early stages when lifecycle import fails.
            actions.append("reject")
            if status in {"shortlisted", "interview", "scheduled"}:
                actions.append("hire")
        return actions


def candidate_mobile_item(
    app_mod: Any,
    item: dict[str, Any],
    *,
    context: dict[str, Any] | None = None,
) -> dict[str, Any]:
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
    try:
        import recruiting_lifecycle as _rl

        canonical_stage = _rl.normalize_stage(status) or status
        status_label = _rl.stage_label(status)
    except Exception:
        canonical_stage = status
        status_label = status.replace("_", " ")
    # Prefer the trusted operator context. Never invent grants from role names or
    # a raw `_permissions` bag without backend_current authority markers.
    auth_context = context if isinstance(context, dict) else {
        "permissions": [],
        "permission_authority": "",
        "actor_user_id": "",
        "company_code": "",
    }
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
        "canonical_stage": canonical_stage,
        "status_label": status_label,
        "intake_source": application.get("intake_source"),
        "communication_status": (
            application.get("communication", {}).get("status")
            if isinstance(application.get("communication"), dict)
            else None
        ),
        "next_human_action": (
            application.get("waiting_for_hr", [None])[0]
            if isinstance(application.get("waiting_for_hr"), list)
            and application.get("waiting_for_hr")
            else None
        ),
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
        "allowed_actions": _candidate_allowed_actions(app_mod, auth_context, status),
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
    _require_mobile_feature_action(app_mod, context, "recruiting", "candidate_rankings", "read")
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
    # Ranking is job-scoped. Do not invent a company-wide parallel list, and do not
    # claim an empty success when the ranking authority rejected the request.
    if result.get("ok") is False:
        error = str(result.get("error") or "ranking_unavailable")
        return {
            "ok": True,
            "items": [],
            "total": 0,
            "filters": app_mod.json_safe(
                result.get("filters")
                or {"query": query, "position": position, "status": status}
            ),
            "ai_advisory": True,
            "ranking_unavailable": True,
            "ranking_error": error,
            "requires_position": error == "job_required" and not str(position or "").strip(),
            "message": result.get("message") or str(result.get("error") or "Ranking unavailable"),
        }
    items = []
    for candidate in result.get("candidates") or []:
        items.append(candidate_mobile_item(app_mod, candidate, context=context))
    return {
        "ok": True,
        "items": items,
        "total": int(result.get("total_matching") or 0),
        "filters": app_mod.json_safe(result.get("filters") or {}),
        "ai_advisory": True,
        "ranking_unavailable": False,
        "ranking_error": None,
        "requires_position": False,
        "message": None,
    }


def mobile_candidate_detail(app_mod: Any, context: dict[str, Any], app_key: str) -> dict[str, Any]:
    import recruiting_lifecycle as _rl

    _require_mobile_feature_action(app_mod, context, "recruiting", "candidate_summary", "read")
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
    if isinstance(summary, dict):
        summary = {
            **summary,
            "status": status,
            "canonical_stage": _rl.normalize_stage(status) or status,
            "status_label": _rl.stage_label(status),
        }
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
    communication_status = [
        {
            "status": _rl.normalize_communication_status(
                row.get("status") or app_mod.dashboard_delivery_status(row)
            ),
            "raw_status": row.get("status"),
            "display_status": app_mod.dashboard_delivery_status(row),
            "message_kind": row.get("message_kind"),
            "sent_at": _iso(row.get("sent_at")),
            "failed_at": _iso(row.get("failed_at")),
            "updated_at": _iso(row.get("updated_at")),
        }
        for row in communications
    ]
    if not communication_status:
        communication_status = [
            {
                "status": "intentionally_skipped",
                "raw_status": None,
                "display_status": "intentionally_skipped",
                "message_kind": None,
                "sent_at": None,
                "failed_at": None,
                "updated_at": None,
            }
        ]
    latest_communication = communication_status[0]
    stage_changed_without_contact = (
        (_rl.normalize_stage(status) or status) in {"shortlisted", "interview", "hired", "rejected"}
        and latest_communication["status"] != "sent"
    )
    if isinstance(summary, dict):
        waiting_for_hr = list(summary.get("waiting_for_hr") or [])
        if stage_changed_without_contact and "inform_candidate" not in waiting_for_hr:
            waiting_for_hr.append("inform_candidate")
        summary = {
            **summary,
            "communication": {
                **(summary.get("communication") if isinstance(summary.get("communication"), dict) else {}),
                **latest_communication,
                "stage_changed_without_contact": stage_changed_without_contact,
            },
            "waiting_for_hr": waiting_for_hr,
        }
    allowed_actions = _candidate_allowed_actions(app_mod, context, status)
    permissions = _authoritative_permissions(app_mod, context)
    if cv and "prehire.read" in permissions:
        allowed_actions.extend(["preview_cv", "download_cv"])
    offer_payload = None
    try:
        import offer_lifecycle as _offers
        import offer_service as _offer_service

        if _offers.employment_offers_enabled(app_mod, context["company_code"]):
            offer_items = _offer_service.list_offers_for_application(
                app_mod,
                context["company_code"],
                app_key,
                permissions=permissions,
                surface="mobile",
                can_hire="hire" in allowed_actions,
            )
            current = next((item for item in offer_items if item.get("status") in _offers.OFFER_OPEN | {"accepted"}), None)
            if current is None and offer_items:
                current = offer_items[0]
            offer_payload = {
                "current": app_mod.json_safe(current) if current else None,
                "items": app_mod.json_safe(offer_items),
                "allowed_actions": list((current or {}).get("allowed_actions") or []),
            }
    except Exception:
        offer_payload = None
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
            "communication_status": communication_status,
            "offer": offer_payload,
            "allowed_actions": list(dict.fromkeys(allowed_actions)),
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
    for item in app_mod.employee_onboarding_items(
        employee_key, company_code=context["company_code"]
    ):
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

    if (hr_features.get("performance_reviews") or {}).get("enabled"):
        try:
            import performance_surfaces as _ps

            company = str(context.get("company_code") or "").strip().upper()
            role = str(context.get("actor_role") or "hr").strip().lower()
            keys = None
            if role == "manager" and callable(getattr(app_mod, "context_manager_employee_keys", None)):
                keys = sorted(str(k) for k in (app_mod.context_manager_employee_keys(context, company) or set()))
            with app_mod.db_connect() as conn:
                with conn.cursor() as cur:
                    queue = _ps.manager_queue(
                        cur,
                        company_code=company,
                        manager_scope_keys=keys or [],
                        limit=max_items,
                    )
                conn.commit()
            sections.append(
                {
                    "type": "performance_reviews",
                    "title": "Performance reviews",
                    "total": int(queue.get("total") or 0),
                    "items": [
                        {
                            "type": "performance_review",
                            "target_id": item.get("review_id"),
                            "summary": item.get("cycle_name_en") or "Performance review",
                            "status": item.get("status"),
                            "timestamp": item.get("updated_at"),
                            "permitted_actions": ["read", "submit"] if item.get("status") in {"not_started", "draft"} else ["read"],
                            "destination": f"/performance/{item.get('review_id')}",
                        }
                        for item in (queue.get("items") or [])
                    ],
                }
            )
        except Exception:
            pass
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
        onboarding = mobile_onboarding_list(app_mod, context, offset=0, limit=max_items, search="")
        sections.append(
            {
                "type": "onboarding_reviews",
                "title": "Onboarding reviews",
                "total": int(onboarding.get("total_count") or onboarding.get("total") or 0),
                "items": [
                    {
                        "type": "onboarding_review",
                        "target_id": item.get("employee_key")
                        or (item.get("employee") or {}).get("employee_key"),
                        "summary": (item.get("employee") or {}).get("name") or "Onboarding review",
                        "status": "needs_hr_action",
                        "timestamp": item.get("updated_at"),
                        "due_context": {
                            "hr_actionable_count": item.get("hr_actionable_count"),
                        },
                        "permitted_actions": item.get("allowed_actions") or [],
                        "destination": item.get("destination")
                        or f"/onboarding/{item.get('employee_key')}",
                        "urgency": "high" if int(item.get("hr_actionable_count") or 0) > 1 else None,
                    }
                    for item in onboarding.get("items") or []
                ],
            }
        )

    # Preboarding Needs Attention / Joining Soon (module-composable; fail closed).
    if (hr_features.get("preboarding_review") or {}).get("enabled"):
        try:
            import preboarding as _pb
            import preboarding_surfaces as _pbs

            company = str(context.get("company_code") or "").strip().upper()
            role = str(context.get("actor_role") or "hr").strip().lower()
            with app_mod.db_connect() as conn:
                with conn.cursor() as cur:
                    _pb.ensure_preboarding_schema(cur)
                    gate = _pb.preboarding_enabled_for_company(cur, company)
                    if gate.get("ok"):
                        queue = _pbs.queue_payload(
                            cur,
                            company_code=company,
                            manager_scope_only=role == "manager",
                            actor_user_id=context.get("actor_user_id"),
                            limit=max_items,
                            offset=0,
                            hub_lookup=lambda key, co: app_mod.find_employee_by_key(key, company_code=co),
                        )
                        attention = [
                            a
                            for a in (queue.get("assignments") or [])
                            if a.get("status") == "blocked"
                            or int((a.get("items_summary") or {}).get("overdue") or 0) > 0
                        ]
                        joining = sorted(
                            [
                                a
                                for a in (queue.get("assignments") or [])
                                if a.get("status") not in {"converted", "cancelled"}
                            ],
                            key=lambda a: str(a.get("joining_date") or "9999"),
                        )[:max_items]
                        if attention:
                            sections.append(
                                {
                                    "type": "preboarding_attention",
                                    "title": "Preboarding needs attention",
                                    "total": len(attention),
                                    "items": [
                                        {
                                            "type": "preboarding_attention",
                                            "target_id": a.get("assignment_id"),
                                            "summary": a.get("employee_name")
                                            or a.get("employee_key")
                                            or "Future joiner",
                                            "status": a.get("status"),
                                            "timestamp": a.get("updated_at"),
                                            "due_context": {
                                                "joining_date": a.get("joining_date"),
                                                "overdue": (a.get("items_summary") or {}).get("overdue"),
                                            },
                                            "permitted_actions": ["review", "waive"],
                                            "destination": f"/hr/preboarding/{a.get('assignment_id')}",
                                            "urgency": "high" if a.get("status") == "blocked" else "medium",
                                        }
                                        for a in attention[:max_items]
                                    ],
                                }
                            )
                        if joining:
                            sections.append(
                                {
                                    "type": "preboarding_joining_soon",
                                    "title": "Joining soon",
                                    "total": len(joining),
                                    "items": [
                                        {
                                            "type": "preboarding_joining_soon",
                                            "target_id": a.get("assignment_id"),
                                            "summary": a.get("employee_name")
                                            or a.get("employee_key")
                                            or "Future joiner",
                                            "status": a.get("status"),
                                            "timestamp": a.get("joining_date"),
                                            "due_context": {"joining_date": a.get("joining_date")},
                                            "permitted_actions": ["open"],
                                            "destination": f"/hr/preboarding/{a.get('assignment_id')}",
                                        }
                                        for a in joining
                                    ],
                                }
                            )
                conn.commit()
        except Exception:
            pass

    # Probation Needs Attention / Reviews Due (module-composable; fail closed).
    if (hr_features.get("probation_review") or {}).get("enabled"):
        try:
            import probation as _pr
            import probation_surfaces as _prs

            company = str(context.get("company_code") or "").strip().upper()
            role = str(context.get("actor_role") or "hr").strip().lower()
            with app_mod.db_connect() as conn:
                with conn.cursor() as cur:
                    _pr.ensure_probation_schema(cur)
                    gate = _pr.probation_enabled_for_company(cur, company)
                    if gate.get("ok"):
                        queue = _prs.queue_payload(
                            cur,
                            company_code=company,
                            status="attention",
                            manager_scope_only=role == "manager",
                            actor_user_id=context.get("actor_user_id"),
                            limit=max_items,
                            offset=0,
                            hub_lookup=lambda key, co: app_mod.find_employee_by_key(key, company_code=co),
                        )
                        attention = [
                            c
                            for c in (queue.get("cases") or [])
                            if c.get("needs_attention") or c.get("decision_required")
                        ]
                        if attention:
                            sections.append(
                                {
                                    "type": "probation_attention",
                                    "title": "Probation needs attention",
                                    "total": len(attention),
                                    "items": [
                                        {
                                            "type": "probation_attention",
                                            "target_id": c.get("case_id"),
                                            "summary": c.get("employee_name")
                                            or c.get("employee_key")
                                            or "Probationer",
                                            "status": c.get("status"),
                                            "timestamp": c.get("probation_end"),
                                            "due_context": {
                                                "probation_end": c.get("probation_end"),
                                                "decision_required": c.get("decision_required"),
                                                "overdue": (c.get("milestones_summary") or {}).get("overdue"),
                                            },
                                            "permitted_actions": ["review", "recommend", "decide"],
                                            "destination": f"/hr/probation/{c.get('case_id')}",
                                            "urgency": "high" if c.get("decision_required") else "medium",
                                        }
                                        for c in attention[:max_items]
                                    ],
                                }
                            )
                conn.commit()
        except Exception:
            pass

    # Requisitions Needs Attention (module-composable; fail closed; recruiting).
    if (recruiting_features.get("requisitions_review") or {}).get("enabled"):
        try:
            import requisitions as _rq
            import requisitions_surfaces as _rqs

            company = str(context.get("company_code") or "").strip().upper()
            role = str(context.get("actor_role") or "hr").strip().lower()
            perms = set(context.get("permissions") or [])
            with app_mod.db_connect() as conn:
                with conn.cursor() as cur:
                    _rq.ensure_requisitions_schema(cur)
                    gate = _rq.requisitions_enabled_for_company(cur, company)
                    if gate.get("ok"):
                        queue = _rqs.queue_payload(
                            cur,
                            company_code=company,
                            status="attention",
                            manager_scope_only=role == "manager" and "requisitions.approve" not in perms,
                            actor_user_id=context.get("actor_user_id"),
                            limit=max_items,
                            offset=0,
                        )
                        attention = [
                            r
                            for r in (queue.get("requisitions") or [])
                            if r.get("needs_attention") or r.get("decision_required")
                        ]
                        if attention:
                            sections.append(
                                {
                                    "type": "requisitions_attention",
                                    "title": "Requisitions need approval",
                                    "total": len(attention),
                                    "items": [
                                        {
                                            "type": "requisitions_attention",
                                            "target_id": r.get("requisition_id"),
                                            "summary": r.get("title_en") or r.get("title_ar") or "Requisition",
                                            "status": r.get("status"),
                                            "timestamp": r.get("updated_at") or r.get("target_hire_date"),
                                            "due_context": {
                                                "headcount": r.get("headcount"),
                                                "decision_required": r.get("decision_required"),
                                            },
                                            "permitted_actions": ["approve", "reject", "open"],
                                            "destination": f"/hr/requisitions/{r.get('requisition_id')}",
                                            "urgency": "high" if r.get("decision_required") else "medium",
                                        }
                                        for r in attention[:max_items]
                                    ],
                                }
                            )
                conn.commit()
        except Exception:
            pass

    if (hr_features.get("document_review") or {}).get("enabled"):
        docs = mobile_document_reviews(
            app_mod, context, search="", status="needs_review", offset=0, limit=max_items
        )
        sections.append(
            {
                "type": "document_reviews",
                "title": "Document reviews",
                "total": int(docs.get("total") or 0),
                "items": [
                    {
                        "type": "document_review",
                        "target_id": item.get("document_id"),
                        "summary": (
                            f"{(item.get('employee') or {}).get('name') or 'Employee'} · "
                            f"{item.get('label') or item.get('name') or item.get('document_type') or 'Document'}"
                        ),
                        "status": item.get("status") or "needs_review",
                        "timestamp": item.get("last_checked_at") or item.get("updated_at"),
                        "due_context": {
                            "expiry_date": item.get("expiry_date"),
                            "days_until_expiry": item.get("days_until_expiry"),
                        },
                        "permitted_actions": item.get("allowed_actions") or [],
                        "destination": item.get("destination")
                        or (
                            f"/onboarding/{(item.get('employee') or {}).get('employee_key')}"
                            if item.get("source") == "onboarding"
                            else f"/documents/{(item.get('employee') or {}).get('employee_key')}/{item.get('document_type')}"
                        ),
                        "urgency": "high"
                        if item.get("days_until_expiry") is not None
                        and int(item.get("days_until_expiry") or 0) <= 7
                        else None,
                    }
                    for item in docs.get("items") or []
                ],
            }
        )

    if (hr_features.get("attendance_exceptions") or {}).get("enabled"):
        attendance = app_mod.dashboard_posthire_attendance(
            start_date=None,
            end_date=None,
            status="exceptions",
            offset=0,
            limit=max_items,
            context=context,
        )
        att_actions = _actions(hr_features.get("attendance_exceptions"))
        att_items = []
        for raw in attendance.get("attendance") or []:
            item = attendance_mobile_item(app_mod, raw, actions=att_actions)
            if not item.get("is_exception"):
                continue
            emp = item.get("employee") or {}
            kind = item.get("exception_kind") or "needs_review"
            att_items.append(
                {
                    "type": "attendance_exception",
                    "target_id": item.get("attendance_id") or emp.get("employee_key"),
                    "summary": emp.get("name") or "Attendance exception",
                    "status": kind,
                    "timestamp": item.get("updated_at") or item.get("attendance_date"),
                    "due_context": {"date": item.get("attendance_date")},
                    "permitted_actions": att_actions,
                    "destination": item.get("destination") or "/attendance",
                    "severity": "high" if kind == "absence" else None,
                }
            )
        sections.append(
            {
                "type": "attendance_exceptions",
                "title": "Attendance exceptions",
                "total": int(attendance.get("total_count") or attendance.get("count") or len(att_items)),
                "items": att_items,
            }
        )

    if (hr_features.get("shift_swap_decisions") or {}).get("enabled"):
        swaps = mobile_shift_swaps(app_mod, context, status="requested", limit=max_items)
        swap_items = []
        for item in swaps.get("items") or []:
            requester = item.get("requester") or {}
            target = item.get("target") or {}
            req_name = requester.get("name") or "Requester"
            tgt_name = target.get("name") if target else None
            summary = f"{req_name} → {tgt_name}" if tgt_name else f"{req_name} · shift swap"
            swap_items.append(
                {
                    "type": "shift_swap",
                    "target_id": item.get("swap_id"),
                    "summary": summary,
                    "status": item.get("status") or "requested",
                    "timestamp": item.get("requested_at") or item.get("updated_at"),
                    "due_context": {"date": item.get("shift_date")},
                    "permitted_actions": item.get("allowed_actions") or [],
                    "destination": item.get("destination") or f"/shift-swaps/{item.get('swap_id')}",
                    "urgency": None,
                }
            )
        sections.append(
            {
                "type": "shift_swap_decisions",
                "title": "Shift swaps",
                "total": int(swaps.get("total") or len(swap_items)),
                "items": swap_items,
            }
        )

    if (hr_features.get("hr_tasks") or {}).get("enabled"):
        tasks = mobile_hr_tasks(
            app_mod, context, status="open", offset=0, limit=max_items
        )
        sections.append(
            {
                "type": "hr_tasks",
                "title": "HR tasks",
                "total": int(tasks.get("total") or 0),
                "items": [
                    {
                        "type": str(item.get("task_type") or item.get("source") or "hr_task"),
                        "target_id": str(item.get("task_id") or ""),
                        "summary": (
                            f"{(item.get('employee') or {}).get('name')} · {item.get('title') or 'HR task'}"
                            if (item.get("employee") or {}).get("name")
                            else (item.get("title") or "HR task")
                        ),
                        "status": item.get("status") or "open",
                        "timestamp": item.get("created_at") or item.get("updated_at"),
                        "due_context": {
                            "priority": item.get("priority"),
                            "task_type": item.get("task_type"),
                        },
                        "permitted_actions": item.get("allowed_actions") or [],
                        "destination": item.get("destination")
                        or f"/tasks/{item.get('task_id')}",
                        "urgency": "high"
                        if str(item.get("priority") or "").lower() == "high"
                        else None,
                    }
                    for item in tasks.get("items") or []
                ],
            }
        )

    # delivery_alerts intentionally omitted from mobile priorities — Home/Inbox
    # never render them; the More monitor is the sole surface (has_task-deduped).

    # Shared pre-hire priorities contract (same action_counts / next_action
    # authority as desktop Overview and Admin Assistant tools). Emit whenever
    # the tenant has pre_hiring + prehire.read — do not hide behind ranking
    # action enablement.
    company_code = str(context.get("company_code") or "")
    access = context.get("access") if isinstance(context.get("access"), dict) else {}
    permissions = set(context.get("permissions") or access.get("permissions") or [])
    has_prehire = False
    try:
        has_prehire = bool(app_mod.company_has_module(company_code, "pre_hiring")) and (
            not permissions or "prehire.read" in permissions or "candidate.manage" in permissions
        )
    except Exception:
        has_prehire = False
    if has_prehire:
        try:
            overview = app_mod._prehire_overview.build_overview_authority(
                company=company_code,
                db_connect=app_mod.db_connect,
                get_company_settings=app_mod.get_company_settings,
                assessments_enabled=bool(app_mod.company_has_module(company_code, "assessments")),
                interviews_enabled=True,
            )
            counts = overview.get("action_counts") or {}
            next_action = overview.get("next_action") or {}
            role = overview.get("role_priority")
            prehire_items: list[dict[str, Any]] = []
            if int(counts.get("follow_up_needed") or 0):
                prehire_items.append(
                    {
                        "type": "prehire_follow_up",
                        "target_id": "follow_up_needed",
                        "summary": f"{counts['follow_up_needed']} candidates need follow-up",
                        "status": "follow_up_needed",
                        "timestamp": overview.get("as_of"),
                        "due_context": {"total": counts["follow_up_needed"]},
                        "permitted_actions": [],
                        "destination": "/jobs",
                        "severity": "high",
                        "authority_source": "prehire_overview.follow_up_needed",
                    }
                )
            if int(counts.get("ready_for_review") or 0):
                prehire_items.append(
                    {
                        "type": "prehire_ready_for_review",
                        "target_id": "ready_for_review",
                        "summary": f"{counts['ready_for_review']} candidates ready for review",
                        "status": "ready_for_review",
                        "timestamp": overview.get("as_of"),
                        "due_context": {"total": counts["ready_for_review"]},
                        "permitted_actions": [],
                        "destination": "/jobs",
                        "severity": "high" if str(next_action.get("action")) == "ready_for_review" else None,
                        "authority_source": "prehire_overview.ready_for_review",
                    }
                )
            if int(counts.get("assessment_pending") or 0) and app_mod.company_has_module(company_code, "assessments"):
                prehire_items.append(
                    {
                        "type": "prehire_assessment_pending",
                        "target_id": "assessment_pending",
                        "summary": f"{counts['assessment_pending']} candidates awaiting assessment",
                        "status": "assessment_pending",
                        "timestamp": overview.get("as_of"),
                        "due_context": {"total": counts["assessment_pending"]},
                        "permitted_actions": [],
                        "destination": "/jobs",
                        "severity": None,
                        "authority_source": "prehire_overview.assessment_pending",
                    }
                )
            if role:
                position_code = str(role.get("position_code") or "").strip()
                prehire_items.append(
                    {
                        "type": "prehire_role_priority",
                        "target_id": position_code or role.get("position_code"),
                        "summary": f"{role.get('position_title')}: {role.get('reason')}",
                        "status": "role_priority",
                        "timestamp": overview.get("as_of"),
                        "due_context": {
                            "priority": role.get("priority"),
                            "position_code": position_code or None,
                            "position_title": role.get("position_title"),
                        },
                        "permitted_actions": [],
                        "destination": (
                            f"/candidates?position={position_code}" if position_code else "/jobs"
                        ),
                        "urgency": None,
                        "authority_source": "prehire_overview.role_priority",
                    }
                )
            sections.append(
                {
                    "type": "prehire_priorities",
                    "title": "Hiring priorities",
                    "total": sum(int(counts.get(k) or 0) for k in ("follow_up_needed", "ready_for_review", "assessment_pending")),
                    "items": prehire_items[:max_items],
                    "action_counts": counts,
                    "next_action": next_action,
                    "authority_source": "prehire_overview",
                }
            )
        except Exception:
            pass

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

    class OfferActionRequest(BaseModel):
        action: str
        reason: str | None = None
        evidence_note: str | None = None
        confirm: bool = False

    class OnboardingReviewRequest(BaseModel):
        item_id: str
        outcome: str = "accepted"
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
        expected_updated_at: str | None = None
        expected_version: int | None = None

    # ``from __future__ import annotations`` makes FastAPI resolve these names
    # through module globals rather than this registration function's locals.
    globals()["LeaveDecisionRequest"] = LeaveDecisionRequest
    globals()["CandidateActionRequest"] = CandidateActionRequest
    globals()["OfferActionRequest"] = OfferActionRequest
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
        action = str(request.action or "").strip().lower()
        if action not in {"approve", "reject"}:
            raise app_mod.HTTPException(
                status_code=400,
                detail={"error": "unsupported_leave_action", "message": "That leave decision is not supported."},
            )
        _require_mobile_feature_action(app_mod, context, "hr", "leave_approvals", action)
        app_mod.require_entitlement(context, "leave", "leave.decide")
        leave, employee = _load_leave(app_mod, context, leave_id)
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

    @app_mod.app.get("/dashboard/mobile/positions")
    def mobile_prehire_positions(
        q: str = Query(default=""),
        status: str = Query(default="open"),
        limit: int = Query(default=50, ge=1, le=100),
        offset: int = Query(default=0, ge=0),
        context: dict[str, Any] = Depends(dependency),
    ):
        """Same Pre-Hiring positions payload as the web Jobs page / Assistant list tool."""
        app_mod.require_entitlement(context, "pre_hiring", "prehire.read")
        company = str(context.get("company_code") or "").strip().upper()
        status_filter = str(status or "open").strip().lower() or "open"
        positions, total_count = app_mod._dashboard_prehire_positions_query(
            company,
            limit=limit,
            offset=offset,
            search=q or None,
            status=None if status_filter in {"", "all"} else status_filter,
        )
        return {
            "company_code": company,
            "positions": positions,
            "total_count": total_count,
            "limit": limit,
            "offset": offset,
            "has_more": (offset + len(positions)) < total_count,
            "status_filter": status_filter,
            "summary": app_mod.dashboard_prehire_positions_summary(company),
        }

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
        _require_mobile_feature_action(app_mod, context, "recruiting", "candidate_cv", "view")
        app_mod.require_entitlement(context, "pre_hiring", "prehire.read")
        return app_mod.dashboard_prehire_application_cv(app_key, context=context)

    @app_mod.app.get("/dashboard/mobile/candidates/{app_key}/cv/preview")
    def mobile_candidate_cv_preview(
        app_key: str,
        context: dict[str, Any] = Depends(dependency),
    ):
        _require_mobile_feature_action(app_mod, context, "recruiting", "candidate_cv", "preview")
        app_mod.require_entitlement(context, "pre_hiring", "prehire.read")
        return app_mod.dashboard_prehire_application_cv_preview(app_key, context=context)

    @app_mod.app.post("/dashboard/mobile/candidates/{app_key}/decision")
    def mobile_candidate_decision(
        app_key: str,
        request: CandidateActionRequest,
        context: dict[str, Any] = Depends(dependency),
    ):
        import recruiting_lifecycle as _rl

        action = str(request.action or "").strip().lower()
        if action not in _rl.MOBILE_EXECUTABLE_CANDIDATE_ACTIONS:
            raise app_mod.HTTPException(
                status_code=400,
                detail={"error": "unsupported_candidate_action", "message": "That candidate action is not supported."},
            )
        feature_for_action = {
            "shortlist": ("candidate_shortlist", "shortlist"),
            "reject": ("candidate_reject", "reject"),
            "hire": ("candidate_hire", "hire"),
        }.get(action)
        if feature_for_action:
            _require_mobile_feature_action(
                app_mod, context, "recruiting", feature_for_action[0], feature_for_action[1]
            )
        app_mod.require_entitlement(context, "pre_hiring", "prehire.read")
        application = app_mod.dashboard_application_or_404(app_key, context["company_code"])
        status = str(application.get("status") or "")
        stage = _rl.normalize_stage(status) or status
        if request.confirm:
            # Confirm path owns stale_decision vs already-processed replay.
            # Do not short-circuit on terminal status here — that would collapse
            # mid-flight stale confirms into already_decided.
            return confirm_mobile_action(
                app_mod,
                context,
                confirmation_id=str(request.confirmation_id or ""),
                confirmation_hash=str(request.confirmation_hash or ""),
                expected_target_type="application",
                expected_target_id=app_key,
                expected_action_types={MOBILE_ACTIONS[action]},
            )
        # Terminal state is distinct from permission denial (prepare path only).
        if stage in _rl.TERMINAL_STAGES or status in {"hired", "rejected"}:
            raise app_mod.HTTPException(
                status_code=409,
                detail={"error": "already_decided", "message": "This candidate already has a final decision."},
            )
        permissions = _authoritative_permissions(app_mod, context)
        required = _rl.permission_for_recruiting_action(action)
        # Same matrix + permission authority used by allowed_actions advertisement.
        if not _rl.authorize_recruiting_action(action, stage, permissions):
            if required and required not in permissions:
                raise app_mod.HTTPException(
                    status_code=403,
                    detail={
                        "error": "permission_denied",
                        "message": "You do not have permission to do this action.",
                        "required_permission": required,
                    },
                )
            raise app_mod.HTTPException(
                status_code=403,
                detail={
                    "error": "action_forbidden",
                    "message": "That action is not available in the current candidate stage.",
                    "current_stage": stage,
                },
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

    @app_mod.app.post("/dashboard/mobile/offers/{offer_id}/action")
    def mobile_offer_action(
        offer_id: str,
        request: OfferActionRequest,
        context: dict[str, Any] = Depends(dependency),
    ):
        """Mobile V1 offer mutations: approve/return, record response, withdraw."""
        import offer_lifecycle as _offers
        import offer_service as _offer_service

        app_mod.require_entitlement(context, "employment_offers", "prehire.read")
        if not _offers.employment_offers_enabled(app_mod, context["company_code"]):
            raise app_mod.HTTPException(
                status_code=403,
                detail={"error": "module_disabled", "message": "Employment offers module is not enabled."},
            )
        action = str(request.action or "").strip().lower()
        mobile_actions = {"approve", "return_draft", "record_accept", "record_decline", "withdraw"}
        if action not in mobile_actions:
            raise app_mod.HTTPException(
                status_code=400,
                detail={
                    "error": "unsupported_offer_action",
                    "message": "Mobile V1 supports approve, return, record response, and withdraw only.",
                },
            )
        if not request.confirm:
            raise app_mod.HTTPException(
                status_code=422,
                detail={"error": "confirmation_required", "message": "Confirm this offer action explicitly."},
            )
        permissions = _authoritative_permissions(app_mod, context)
        actor_user_id = str(context.get("actor_user_id") or "")
        company = context["company_code"]
        try:
            if action == "approve":
                offer = _offer_service.approve_offer(
                    legacy=app_mod,
                    company_code=company,
                    offer_id=offer_id,
                    actor_user_id=actor_user_id,
                    permissions=permissions,
                )
            elif action == "return_draft":
                offer = _offer_service.return_to_draft(
                    legacy=app_mod,
                    company_code=company,
                    offer_id=offer_id,
                    actor_user_id=actor_user_id,
                    permissions=permissions,
                    reason=request.reason,
                )
            elif action == "withdraw":
                offer = _offer_service.withdraw_offer(
                    legacy=app_mod,
                    company_code=company,
                    offer_id=offer_id,
                    actor_user_id=actor_user_id,
                    permissions=permissions,
                    reason=request.reason,
                )
            elif action == "record_accept":
                offer = _offer_service.record_response(
                    app_mod,
                    company_code=company,
                    offer_id=offer_id,
                    decision="accepted",
                    actor_user_id=actor_user_id,
                    permissions=permissions,
                    evidence={"note": request.evidence_note} if request.evidence_note else {},
                )
            else:
                offer = _offer_service.record_response(
                    app_mod,
                    company_code=company,
                    offer_id=offer_id,
                    decision="declined",
                    actor_user_id=actor_user_id,
                    permissions=permissions,
                    evidence={"note": request.evidence_note} if request.evidence_note else {},
                )
        except _offers.OfferAuthorityError as exc:
            raise app_mod.HTTPException(status_code=exc.status_code, detail=exc.as_detail()) from exc
        return {"ok": True, "offer": app_mod.json_safe(offer)}

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

    @app_mod.app.get("/dashboard/mobile/tasks/{task_id}")
    def mobile_task_detail(
        task_id: str,
        context: dict[str, Any] = Depends(dependency),
    ):
        return mobile_hr_task_detail(app_mod, context, task_id)

    class HrTaskMobileResolveRequest(BaseModel):
        status: str = "done"
        expected_status: str = "open"

    globals()["HrTaskMobileResolveRequest"] = HrTaskMobileResolveRequest

    @app_mod.app.post("/dashboard/mobile/tasks/{task_id}/resolve")
    def mobile_task_resolve(
        task_id: str,
        request: HrTaskMobileResolveRequest,
        context: dict[str, Any] = Depends(dependency),
    ):
        return mobile_hr_task_resolve(
            app_mod,
            context,
            task_id,
            status=request.status,
            expected_status=request.expected_status,
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
        # Canonical: accepted | waived. Legacy "received" remaps to accepted in mark_onboarding_item.
        if outcome not in {"accepted", "waived", "received"}:
            raise app_mod.HTTPException(
                status_code=400,
                detail={
                    "error": "unsupported_onboarding_outcome",
                    "message": "That onboarding review outcome is not supported.",
                },
            )
        if outcome == "received":
            outcome = "accepted"
        # Company mutate allowlist — never prepare Review if confirm would be blocked.
        company = str(context.get("company_code") or "")
        if not (
            callable(getattr(app_mod, "onboarding_hr_mutate_enabled_for_company", None))
            and app_mod.onboarding_hr_mutate_enabled_for_company(company)
        ):
            raise app_mod.HTTPException(
                status_code=403,
                detail={
                    "error": "onboarding_mutate_disabled",
                    "message": "Onboarding review mutations are not enabled for this company.",
                },
            )
        target_id = f"{employee_key}:{str(request.item_id or '').strip()}"
        item, employee = _load_onboarding_item(app_mod, context, target_id)
        if _is_bank_ess_item(item):
            raise app_mod.HTTPException(
                status_code=400,
                detail={
                    "error": "bank_via_ess_required",
                    "message": "Bank items must be reviewed in the web/ESS bank workflow.",
                },
            )
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
        verb = "Accept" if outcome == "accepted" else "Waive"
        return prepare_mobile_confirmation(
            app_mod,
            context,
            idempotency_key=request.idempotency_key,
            action_type=MOBILE_ACTIONS["review_onboarding"],
            target_type="onboarding_item",
            target_id=target_id,
            expected_status=str(item.get("status") or ""),
            safe_summary=f"{employee_name} · {item_label}",
            consequence=f"{verb} {item_label} for {employee_name}'s onboarding checklist.",
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
        normalized = str(status or "").strip().lower() or "needs_review"
        if normalized not in {
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
            consequence=f"Request a correction for {employee_name}'s attendance to {status}. Review may be required before the day is updated.",
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
        offset: int = Query(default=0, ge=0),
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
            app_mod, context, status=normalized, offset=offset, limit=limit
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
                expected_updated_at=str(request.expected_updated_at or "") or None,
                expected_version=request.expected_version,
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
