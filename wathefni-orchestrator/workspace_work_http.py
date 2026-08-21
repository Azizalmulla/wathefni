"""HTTP for workspace Work aggregation (My Work / Company Attention)."""
from __future__ import annotations

from typing import Any

from fastapi import Depends, HTTPException, Query

import workspace_work as work


def register_workspace_work_http(app_mod: Any) -> None:
    app = app_mod.app
    dashboard_context = app_mod.dashboard_context
    db_connect = app_mod.db_connect
    json_safe = getattr(app_mod, "json_safe", lambda value: value)
    dashboard_context_role_key = app_mod.dashboard_context_role_key
    context_permissions = app_mod.context_permissions
    configured_company_modules = app_mod.configured_company_modules
    get_company_settings = app_mod.get_company_settings

    def _load_inbox(context: dict[str, Any]) -> dict[str, Any] | None:
        try:
            return app_mod.dashboard_action_inbox_payload(context)
        except HTTPException as exc:
            if exc.status_code in {401, 403, 404}:
                return None
            raise

    @app.get("/dashboard/work")
    def dashboard_workspace_work(
        scope: str = Query(default="mine"),
        limit: int = Query(default=10, ge=1, le=50),
        context: dict[str, Any] = Depends(dashboard_context),
    ):
        company = context["company_code"]
        role = dashboard_context_role_key(context)
        perms = context_permissions(context, role)
        actor_user_id = str(context.get("actor_user_id") or "")
        actor_phone = str(context.get("actor_phone") or context.get("hr_phone") or "")
        actor_employee_key = str(context.get("actor_employee_key") or context.get("employee_key") or "")
        payload = work.compose_workspace_work(
            company=company,
            db_connect=db_connect,
            actor_user_id=actor_user_id,
            actor_role=role,
            actor_email=str(context.get("actor_email") or ""),
            actor_phone=actor_phone,
            actor_employee_key=actor_employee_key,
            actor_key=actor_user_id or actor_phone,
            enabled_modules=configured_company_modules(company),
            permissions=perms,
            settings=get_company_settings(company),
            scope=scope,
            limit=limit,
            load_inbox=lambda: _load_inbox(context),
            load_leave=lambda: app_mod.list_leave_requests(
                {
                    "status": "requested",
                    "viewer_phone": actor_phone,
                    "dashboard_user_id": actor_user_id,
                    "actor_role": role,
                    "limit": 50,
                },
                company_code=company,
            ),
            load_onboarding=lambda: app_mod.list_onboarding_hr_actionable_page(
                company,
                viewer_phone=actor_phone or None,
                dashboard_user_id=actor_user_id or None,
                actor_role=role,
                limit=50,
                offset=0,
            ),
            load_swaps=lambda: app_mod.resolve_shift_swaps(
                {"limit": 50},
                company_code=company,
                statuses=("requested",),
            ),
        )
        if not payload.get("ok"):
            raise HTTPException(
                status_code=400,
                detail={"error": payload.get("error"), "message": payload.get("message")},
            )
        return json_safe(payload)
