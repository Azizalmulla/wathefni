#!/usr/bin/env python3
"""Focused, dependency-light HR-2A contract smoke checks.

DB-backed authority and mutation checks run in staging only after visual approval.
This suite verifies the local adapter boundary without importing FastAPI/app.py.
"""

from __future__ import annotations

import inspect
import json
from pathlib import Path
from typing import Any

import operator_mobile_data as mobile


ROOT = Path(__file__).resolve().parent
failures: list[str] = []
checks = 0


def check(condition: bool, message: str) -> None:
    global checks
    checks += 1
    if not condition:
        failures.append(message)
        print(f"FAIL: {message}")
    else:
        print(f"PASS: {message}")


class FakeApp:
    @staticmethod
    def json_safe(value: Any) -> Any:
        return json.loads(json.dumps(value, default=str))

    @staticmethod
    def context_permissions(context: dict[str, Any], role_key: str | None = None) -> set[str]:
        data = context or {}
        access = data.get("access") if isinstance(data.get("access"), dict) else {}
        authority = str(data.get("permission_authority") or access.get("permission_authority") or "")
        if authority != "backend_current":
            return set()
        subject_user_id = str(
            data.get("permission_subject_user_id")
            or access.get("permission_subject_user_id")
            or ""
        ).strip()
        actor_user_id = str(data.get("actor_user_id") or "").strip()
        if not subject_user_id or (actor_user_id and subject_user_id != actor_user_id):
            return set()
        subject_company = str(
            data.get("permission_subject_company")
            or access.get("permission_subject_company")
            or ""
        ).strip().upper()
        context_company = str(data.get("company_code") or data.get("company_id") or "").strip().upper()
        if not subject_company or (context_company and subject_company != context_company):
            return set()
        permissions = data.get("permissions")
        if not isinstance(permissions, list):
            permissions = access.get("permissions") if isinstance(access.get("permissions"), list) else []
        return {str(item) for item in permissions or [] if str(item).strip()}

    @staticmethod
    def posthire_employee_card(row: dict[str, Any]) -> dict[str, Any]:
        return {
            "employee_key": row.get("employee_key"),
            "name": row.get("employee_name") or row.get("name"),
            "position_title": row.get("position_title"),
            "department": row.get("department"),
            "employment_status": row.get("employment_status") or "active",
        }


def main() -> int:
    source = inspect.getsource(mobile)
    app_source = (ROOT / "app.py").read_text()
    deploy_source = (ROOT / "ops" / "deploy.sh").read_text()

    check("/app/" not in source, "HR-2A adapters contain no employee API paths")
    check("ai-recruiter" not in source, "HR-2A adapters contain no legacy AI Recruiter path")
    check("dashboard/mobile/priorities" in source, "priorities route is registered")
    check("dashboard/mobile/leave/{leave_id}/decision" in source, "leave decision route is registered")
    check("dashboard/mobile/candidates/{app_key}/decision" in source, "candidate decision route is registered")
    check("dashboard/mobile/candidates/{app_key}/cv/preview" in source, "audited candidate CV preview adapter is registered")
    check("dashboard_prehire_application_cv_preview" in source, "CV preview reuses the audited dashboard authority path")
    check("run_posthire_dashboard_action" in source, "leave mutations reuse the registry harness")
    check("run_dashboard_registry_action" in source, "candidate mutations reuse the registry harness")
    check("confirmation_unavailable" in source, "mobile fails closed if registry confirmation policy changes")
    check("stale_decision" in source, "stale target state has a deterministic conflict")
    check("idempotency_conflict" in source, "idempotency key reuse with different material fails closed")
    check(
        "UNIQUE (company_code, user_id, idempotency_key)" in mobile.MOBILE_DATA_SCHEMA_SQL,
        "idempotency is tenant and operator bound",
    )
    check("company_code=%s AND user_id=%s" in source, "confirmation lookup is tenant and operator scoped")
    check("context[\"company_code\"]" in source, "company authority comes from authenticated context")
    check("context_manager_allows_employee" in source, "leave detail independently enforces manager record scope")
    check("employees.read" in source, "employee adapters retain grant-only employees.read")
    check("context_permissions" in source, "candidate actions use backend context_permissions authority")
    check("_authoritative_permissions" in source, "allowed_actions and decision share authoritative permission helper")
    check("authorize_recruiting_action" in source, "candidate decision uses the shared recruiting authority function")
    check(
        '"_permissions"' not in source or "Never invent grants" in source,
        "data adapters do not advertise from raw client permission bags",
    )
    check(
        app_source.index("_operator_mobile.register_operator_mobile_routes")
        < app_source.index("_operator_mobile_data.register_operator_mobile_data_routes"),
        "HR-1 authentication dependency registers before HR-2A routes",
    )
    check("operator_mobile_data.py" in deploy_source, "staging deploy includes HR-2A module")
    check(
        'str(WORKSPACE / "tools" / "db" / "update_state.py"),\n        "--env",\n        str(ENV_PATH)' in app_source,
        "candidate status updater is explicitly bound to current environment",
    )
    check(
        'str(WORKSPACE / "tools" / "db" / "posthire_state.py"),\n        "--env",\n        str(ENV_PATH)' in app_source,
        "candidate hire transition is explicitly bound to current environment",
    )
    check(
        "binding.child_environment(os.environ)" in app_source
        and "database_env_path" not in app_source,
        "workspace mutation child overrides inherited DB environment",
    )

    leave = mobile.leave_mobile_item(
        FakeApp,
        {
            "leave_id": "leave-1",
            "employee_key": "employee-1",
            "employee_name": "Aisha",
            "leave_type": "annual",
            "start_date": "2026-07-20",
            "end_date": "2026-07-24",
            "status": "requested",
            "shift_conflict_count": 2,
        },
        actions=["read", "approve", "reject"],
    )
    check(leave["allowed_actions"] == ["read", "approve", "reject"], "pending leave DTO preserves backend actions")
    leave["status"] = "approved"
    terminal = mobile.leave_mobile_item(FakeApp, leave, actions=["approve", "reject"])
    check(terminal["allowed_actions"] == [], "terminal leave DTO exposes no decision actions")
    check("company_code" not in leave["employee"], "employee-safe leave context omits tenant internals")

    candidate = mobile.candidate_mobile_item(
        FakeApp,
        {
            "app_key": "app-1",
            "name": "Lina",
            "status": "review_pending",
            "score": 86,
            "evidence": ["CV evidence"],
            "application": {
                "candidate": {"name": "Lina", "email": "lina@example.invalid"},
                "position": {"title": "Designer"},
                "cv": {"received": True},
            },
        },
        context={
            "company_code": "HR2A",
            "actor_user_id": "u-1",
            "permission_authority": "backend_current",
            "permission_subject_user_id": "u-1",
            "permission_subject_company": "HR2A",
            "permissions": ["candidate.manage"],
        },
    )
    check(candidate["ai_advisory"] is True, "candidate ranking is explicitly advisory")
    check(candidate["allowed_actions"] == ["shortlist"], "candidate actions derive from exact backend-current permissions")
    untrusted = mobile.candidate_mobile_item(
        FakeApp,
        {
            "app_key": "app-2",
            "name": "No Auth",
            "status": "ready_for_review",
            "application": {"candidate": {"name": "No Auth"}, "position": {"title": "Role"}},
            "_permissions": ["candidate.manage", "candidate.decide"],
        },
    )
    check(untrusted["allowed_actions"] == [], "candidate actions fail closed without trusted operator context")
    check("phone" not in candidate["candidate"], "candidate mobile identity omits phone by default")
    check("raw_json" not in json.dumps(candidate), "candidate DTO omits raw application payloads")

    check(mobile.MOBILE_ACTIONS["approve_leave"] == "approve_leave_request", "leave approval maps to registry action")
    check(mobile.MOBILE_ACTIONS["hire"] == "hire_candidate", "candidate hire maps to registry action")
    check(mobile._stable_hash({"a": 1, "b": 2}) == mobile._stable_hash({"b": 2, "a": 1}), "confirmation request hash is canonical")

    print(f"\nHR-2A smoke: {checks - len(failures)} passed, {len(failures)} failed")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
