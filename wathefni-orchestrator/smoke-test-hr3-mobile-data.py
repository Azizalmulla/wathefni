#!/usr/bin/env python3
"""Dependency-light HR-3 mobile data contract checks.

This suite is source/DTO-only. It never imports app.py, opens a database, or
contacts staging/production.
"""

from __future__ import annotations

import inspect
import json
from pathlib import Path
from typing import Any

import operator_mobile as capabilities
import operator_mobile_data as mobile


ROOT = Path(__file__).resolve().parent
failures: list[str] = []
checks = 0


def check(condition: bool, message: str) -> None:
    global checks
    checks += 1
    if condition:
        print(f"PASS: {message}")
    else:
        failures.append(message)
        print(f"FAIL: {message}")


class ContractHTTPException(Exception):
    def __init__(self, *, status_code: int, detail: dict[str, Any]):
        super().__init__(str(detail))
        self.status_code = status_code
        self.detail = detail


class FakeApp:
    HTTPException = ContractHTTPException

    @staticmethod
    def json_safe(value: Any) -> Any:
        return json.loads(json.dumps(value, default=str))

    @staticmethod
    def posthire_employee_card(row: dict[str, Any]) -> dict[str, Any]:
        return {
            "employee_key": row.get("employee_key"),
            "name": row.get("employee_name") or row.get("name"),
            "position_title": row.get("position_title"),
            "department": row.get("department"),
            "employment_status": row.get("employment_status") or "active",
            "phone": row.get("phone"),
            "raw_json": row.get("raw_json"),
        }

    @staticmethod
    def item_display_label(item: dict[str, Any]) -> str:
        return str(item.get("label") or item.get("document_type") or item.get("item_id") or "Item")

    @staticmethod
    def attendance_exception_kind(row: dict[str, Any] | None) -> str | None:
        status = str((row or {}).get("status") or "").lower()
        if status == "late":
            return "lateness"
        if status in {"absent", "absence"}:
            return "absence"
        return status or None

    @staticmethod
    def attendance_row_is_exception(row: dict[str, Any] | None) -> bool:
        return FakeApp.attendance_exception_kind(row) is not None


class CapabilityApp:
    HTTPException = ContractHTTPException
    _operator_mobile = capabilities

    @staticmethod
    def company_has_module(_company: str, module: str) -> bool:
        return module in {"onboarding", "compliance", "attendance", "shifts", "pre_hiring", "interviews"}

    @staticmethod
    def onboarding_hr_mutate_enabled() -> bool:
        return True

    @staticmethod
    def onboarding_hr_mutate_enabled_for_company(_company: str) -> bool:
        return True


class CapabilityAppOnboardingReadOnly(CapabilityApp):
    @staticmethod
    def onboarding_hr_mutate_enabled() -> bool:
        return False

    @staticmethod
    def onboarding_hr_mutate_enabled_for_company(_company: str) -> bool:
        return False


def context(*permissions: str, blocked: bool = False) -> dict[str, Any]:
    return {
        "company_code": "HR3TEST",
        "permissions": list(permissions),
        "actor_role": "manager",
        "scope": (
            {
                "restricted": True,
                "blocked": True,
                "configuration_error": "manager_scope_binding_conflict",
            }
            if blocked
            else {
                "restricted": True,
                "blocked": False,
                "configuration_error": None,
                "scope_authority": "dashboard_user_id",
            }
        ),
    }


def assert_denied(fn: Any, code: str, message: str) -> None:
    try:
        fn()
    except ContractHTTPException as exc:
        check(exc.status_code == 403 and exc.detail.get("error") == code, message)
    else:
        check(False, message)


def main() -> int:
    source = inspect.getsource(mobile)
    auth_source = inspect.getsource(capabilities)
    app_source = (ROOT / "app.py").read_text()

    routes = {
        "tasks": "/dashboard/mobile/tasks",
        "onboarding list": "/dashboard/mobile/onboarding",
        "onboarding review": "/dashboard/mobile/onboarding/{employee_key}/review",
        "documents list": "/dashboard/mobile/documents",
        "document detail": "/dashboard/mobile/documents/{employee_key}/{document_type}",
        "document review": "/dashboard/mobile/documents/{employee_key}/{document_type}/review",
        "document file": "/dashboard/mobile/documents/files/{file_id}",
        "attendance list": "/dashboard/mobile/attendance",
        "attendance detail": "/dashboard/mobile/attendance/{attendance_id}",
        "attendance resolve": "/dashboard/mobile/attendance/{attendance_id}/resolve",
        "day shifts": "/dashboard/mobile/shifts",
        "swap list": "/dashboard/mobile/shift-swaps",
        "swap detail": "/dashboard/mobile/shift-swaps/{swap_id}",
        "swap decision": "/dashboard/mobile/shift-swaps/{swap_id}/decision",
        "interview list": "/dashboard/mobile/interviews",
        "interview detail": "/dashboard/mobile/interviews/{interview_id}",
        "interview notes": "/dashboard/mobile/interviews/{interview_id}/notes",
        "employee list": "/dashboard/mobile/employees",
        "employee detail": "/dashboard/mobile/employees/{employee_key}",
        "delivery alerts": "/dashboard/mobile/delivery-alerts",
    }
    for label, route in routes.items():
        check(route in source, f"{label} route is registered")
    check("/dashboard/mobile/tasks/{task_id}/resolve" in source, "HR-task resolve is exposed for Mark done")
    check("/dashboard/mobile/tasks/{task_id}" in source, "HR-task detail route is registered")
    check("mobile_hr_task_resolve" in source, "scoped mobile resolve helper exists")
    check("_load_hr_task" in source, "mobile task load enforces manager scope")

    check("/app/" not in source, "HR-3 adapters expose no Employee App route")
    check("ai-recruiter" not in source, "HR-3 adapters expose no legacy recruiter route")
    check("/dashboard/setup" not in source, "HR-3 adapters expose no Setup Console route")
    check("/dashboard/owner" not in source, "HR-3 adapters expose no owner-admin route")
    check("employee_token_rejected" in auth_source, "employee token boundary remains explicit")
    check("browser_session_rejected" in auth_source, "browser token boundary remains explicit")
    check("legacy_authority_rejected" in auth_source, "legacy shared-token boundary remains explicit")
    check('SESSION_CHANNEL = "operator_mobile"' in auth_source, "operator-mobile channel remains distinct")

    action_routes = {
        "onboarding review": ("review_onboarding", "onboarding_mark_item"),
        "attendance resolve": ("resolve_attendance", "correct_attendance_record"),
        "swap approve": ("approve_shift_swap", "approve_shift_swap"),
        "swap reject": ("reject_shift_swap", "reject_shift_swap"),
        "compliance review": ("review_compliance", "compliance_mark_reviewed"),
    }
    for label, (key, action_name) in action_routes.items():
        check(mobile.MOBILE_ACTIONS.get(key) == action_name, f"{label} uses the existing registry action")

    check("run_posthire_dashboard_action" in source, "post-hire mutations reuse the registry harness")
    check(
        '"compliance.manage" in permissions' in source,
        "compliance items expose review only with compliance.manage",
    )
    check("dashboard_prehire_interview_notes" in source, "interview notes reuse the audited browser business function")
    check("DashboardInterviewNotesRequest" in source, "interview notes use the authoritative request schema")
    check("expected_target_type" in source and "expected_action_types" in source, "confirmation is route/target/action bound")
    check("idempotency_conflict" in source, "idempotency conflicts remain deterministic")
    check("stale_decision" in source, "stale decisions remain deterministic")
    check("confirmation_unavailable" in source, "registry confirmation policy changes fail closed")
    check("company_code=%s AND user_id=%s" in source, "confirmations remain tenant/operator scoped")
    for target_type in ("onboarding_item", "attendance_record", "shift_swap"):
        check(f'target_type == "{target_type}"' in source, f"{target_type} has authoritative stale-state lookup")

    read_context = context(
        "onboarding.read",
        "compliance.read",
        "attendance.read",
        "shifts.read",
        "prehire.read",
    )
    review_context = context(
        "onboarding.read",
        "onboarding.manage",
        "compliance.read",
        "compliance.manage",
        "attendance.read",
        "attendance.manage",
        "shifts.read",
        "shifts.manage",
        "prehire.read",
        "interview.manage",
    )
    mobile._require_mobile_feature_action(
        CapabilityApp, review_context, "hr", "onboarding_review", "review"
    )
    check(True, "advertised onboarding review capability has an adapter")
    assert_denied(
        lambda: mobile._require_mobile_feature_action(
            CapabilityAppOnboardingReadOnly,
            review_context,
            "hr",
            "onboarding_review",
            "review",
        ),
        "action_forbidden",
        "disabled onboarding mutation is not advertised",
    )
    mobile._require_mobile_feature_action(
        CapabilityApp, review_context, "hr", "attendance_exceptions", "resolve"
    )
    check(True, "advertised attendance resolve capability has an adapter")
    mobile._require_mobile_feature_action(
        CapabilityApp, review_context, "hr", "shift_swap_decisions", "approve"
    )
    check(True, "advertised shift-swap approve capability has an adapter")
    mobile._require_mobile_feature_action(
        CapabilityApp, review_context, "recruiting", "interview_notes", "write"
    )
    check(True, "advertised interview-notes write capability has an adapter")

    assert_denied(
        lambda: mobile._require_mobile_feature_action(
            CapabilityApp, read_context, "hr", "attendance_exceptions", "resolve"
        ),
        "action_forbidden",
        "read-only attendance grant cannot resolve",
    )
    assert_denied(
        lambda: mobile._require_mobile_feature_action(
            CapabilityApp,
            context("attendance.read", blocked=True),
            "hr",
            "attendance_exceptions",
            "read",
        ),
        "action_forbidden",
        "blocked manager scope fails closed",
    )
    assert_denied(
        lambda: mobile._require_mobile_feature_action(
            CapabilityApp, context(), "hr", "document_review", "read"
        ),
        "action_forbidden",
        "missing grants fail closed",
    )

    task = mobile.hr_task_mobile_item(
        {
            "task_id": "task-1",
            "company_code": "SECRET",
            "task_type": "delivery",
            "source": "outbound",
            "title": "Follow up",
            "detail": "Employee needs help",
            "employee_key": "emp-1",
            "employee_name": "Aisha",
            "status": "open",
            "priority": "high",
            "metadata": {"secret": True},
        },
        actions=["read"],
    )
    check(
        set(task)
        == {
            "task_id",
            "task_type",
            "source",
            "title",
            "detail",
            "employee",
            "status",
            "priority",
            "created_at",
            "updated_at",
            "allowed_actions",
            "destination",
        },
        "HR-task DTO matches its allowlist",
    )

    attendance = mobile.attendance_mobile_item(
        FakeApp,
        {
            "attendance_id": "attendance-1",
            "company_code": "SECRET",
            "employee_key": "emp-1",
            "employee_name": "Aisha",
            "attendance_date": "2026-07-15",
            "status": "late",
            "late_minutes": 12,
            "source_text": "raw browser content",
            "metadata": {"secret": True},
        },
        actions=["read", "resolve"],
    )
    check(attendance["allowed_actions"] == ["resolve"], "attendance exception exposes only resolve")
    check("company_code" not in attendance and "metadata" not in attendance, "attendance DTO omits tenant/raw internals")

    shift = mobile.shift_mobile_item(
        FakeApp,
        {
            "shift_id": "shift-1",
            "company_code": "SECRET",
            "employee_key": "emp-1",
            "employee_name": "Aisha",
            "shift_date": "2026-07-15",
            "start_time": "09:00",
            "end_time": "17:00",
            "source_text": "raw",
            "metadata": {"secret": True},
        },
    )
    check("source_text" not in shift and "metadata" not in shift, "shift DTO omits browser-heavy fields")

    swap = mobile.shift_swap_mobile_item(
        FakeApp,
        {
            "swap_id": "swap-1",
            "requester_employee_key": "emp-1",
            "requester_employee_name": "Aisha",
            "requester_employee_phone": "96550000000",
            "status": "requested",
            "reason": "Family",
            "source_text": "raw",
            "metadata": {"secret": True},
        },
        actions=["read", "approve", "reject"],
    )
    check(swap["allowed_actions"] == ["approve", "reject"], "pending swap exposes advertised decisions")
    check("phone" not in json.dumps(swap), "swap DTO omits employee phones")

    compliance = mobile.compliance_mobile_item(
        FakeApp,
        {
            "employee_key": "emp-1",
            "employee_name": "Aisha",
            "document_type": "civil_id",
            "document_label": "Civil ID",
            "status": "needs_review",
            "file_id": "file-1",
            "storage_url": "https://secret.invalid",
            "local_path": "/secret",
            "raw_json": {"secret": True},
        },
        actions=["read", "review"],
    )
    check(compliance["allowed_actions"] == ["review"], "needs-review document exposes review")
    serialized = json.dumps(compliance)
    check("storage_url" not in serialized and "local_path" not in serialized and "raw_json" not in serialized, "document DTO omits storage/raw payloads")

    interview = mobile.interview_mobile_item(
        FakeApp,
        {
            "interview_id": "interview-1",
            "candidate_name": "Lina",
            "candidate_email": "lina@example.invalid",
            "status": "completed",
            "notes": "Human notes",
            "transcript": "raw transcript",
            "sent_body": "browser-heavy invite",
            "calendar_event_id": "private-event",
            "ai_summary": {"summary": "Advisory"},
            "async_video_config": {"secret": True},
        },
        status_actions=["read"],
        note_actions=["read", "write"],
        detail=True,
    )
    interview_json = json.dumps(interview)
    check(interview["ai_advisory"] is True, "interview AI summary is explicitly advisory")
    check("transcript" not in interview_json and "sent_body" not in interview_json, "interview DTO omits transcript/invite body")
    check("calendar_event_id" not in interview_json and "async_video_config" not in interview_json, "interview DTO omits browser-heavy internals")

    employee = mobile.employee_directory_mobile_item(
        FakeApp,
        {
            "employee_key": "emp-1",
            "name": "Aisha",
            "phone": "96550000000",
            "email": "aisha@example.invalid",
            "position_title": "Coordinator",
            "department": "People",
            "employment_status": "active",
            "raw_json": {"secret": True},
        },
    )
    employee_json = json.dumps(employee)
    check("phone" not in employee_json and "email" not in employee_json, "employee search DTO omits contact data")
    check("raw_json" not in employee_json, "employee search DTO omits raw employee payloads")

    alert = mobile.delivery_alert_mobile_item(
        {
            "message_id": "msg-1",
            "employee_key": "emp-1",
            "flow_label": "Onboarding reminder",
            "reason": "Delivery failed.",
            "status": "failed",
            "target_email": "private@example.invalid",
            "last_error": "provider internals",
            "payload": {"secret": True},
        }
    )
    alert_json = json.dumps(alert)
    check("target_email" not in alert_json and "last_error" not in alert_json, "delivery alert DTO omits contact/provider internals")
    check("payload" not in alert_json, "delivery alert DTO omits raw message payloads")

    check(
        "binding.child_environment(os.environ)" in app_source
        and "database_env_path" not in app_source,
        "runtime mutation environment isolation remains intact",
    )

    print(f"\nHR-3 mobile data smoke: {checks - len(failures)} passed, {len(failures)} failed")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
