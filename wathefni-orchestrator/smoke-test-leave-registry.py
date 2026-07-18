"""Smoke test for the Leave post-hire pilot on the registry / tool-call architecture.

Proves leave runs at the same architecture level as pre-hiring:
  - the 5 leave actions are registered in action_registry with module="leave"
  - sensitive leave decisions require confirmation and have a preflight
  - leave tools are only visible to companies that have the leave module AND
    users who hold the matching permission
  - a viewer (leave.read only) cannot approve leave
  - approving leave triggers the pending_actions confirmation flow
  - a company without the leave module sees no leave tools and cannot execute them
  - read/list leave executes end-to-end through the registry result contract

The legacy execute_direct_action / infer_leave_action / pending_operations paths
are intentionally untouched; this test only exercises the new registry surface.
"""

from __future__ import annotations

import sys
from pathlib import Path


LEAVE_TOOLS = {
    "list_leave_requests",
    "request_leave",
    "approve_leave_request",
    "reject_leave_request",
    "cancel_leave_request",
}


class FakeLegacy:
    ENABLED_MODULES = {"pre_hiring", "assessments", "video_interviews", "leave"}

    LEAVE = {
        "leave_id": "leave-123",
        "company_code": "WATHEFNI",
        "employee_key": "emp-1",
        "employee_phone": "96590000001",
        "employee_name": "Sara Ahmad",
        "start_date": "2026-06-08",
        "end_date": "2026-06-10",
        "leave_type": "vacation",
        "status": "requested",
    }

    # --- generic helpers -------------------------------------------------
    @staticmethod
    def json_safe(value):
        return value

    @staticmethod
    def digits(value):
        return "".join(ch for ch in str(value or "") if ch.isdigit())

    @staticmethod
    def Json(value):
        return value

    @classmethod
    def company_has_module(cls, company_code, module_key):
        return str(module_key or "") in cls.ENABLED_MODULES

    @staticmethod
    def request_company_code(request):
        return "WATHEFNI"

    @classmethod
    def require_entitlement(cls, context, module_key, permission=None):
        company = str((context or {}).get("company_code") or "").strip()
        actor = str((context or {}).get("actor_user_id") or "").strip()
        role = str((context or {}).get("actor_role") or "")
        permissions = {str(item) for item in (context or {}).get("permissions") or []}
        if not company or not actor or not role:
            raise FakeHTTPException({"error": "permission_denied", "message": "Access needs to be verified.", "required_permission": permission})
        if module_key and module_key not in cls.ENABLED_MODULES:
            raise FakeHTTPException({"error": "module_disabled", "message": "This module is not enabled for this company.", "required_module": module_key})
        if permission and permission not in permissions:
            raise FakeHTTPException({"error": "permission_denied", "message": "You do not have permission to do this action.", "required_permission": permission})
        return context

    # --- leave domain ----------------------------------------------------
    @staticmethod
    def format_shift_date_range(start, end):
        if start and end and start != end:
            return f"{start} to {end}"
        return str(start or end or "")

    @classmethod
    def resolve_leave_request(cls, action, *, company_code, statuses=("requested",)):
        if cls.LEAVE.get("status") in statuses or not statuses:
            return dict(cls.LEAVE)
        return dict(cls.LEAVE)

    @staticmethod
    def find_employee_by_phone(phone, *, company_code=None):
        return {"employee_key": "emp-1", "phone": phone, "company_code": company_code or "WATHEFNI", "name": "Sara Ahmad"}

    @staticmethod
    def manager_scope_allows_employee(employee, *, company_code, viewer_phone):
        return True

    @staticmethod
    def leave_shift_conflicts(cur, *, company, employee_key, start_date, end_date):
        return []

    @classmethod
    def list_leave_requests(cls, action, *, company_code):
        return {
            "ok": True,
            "leave_requests": [dict(cls.LEAVE)],
            "count": 1,
            "start_date": cls.LEAVE["start_date"],
            "end_date": cls.LEAVE["end_date"],
            "status_filter": "requested",
        }

    @classmethod
    def request_leave(cls, action, *, company_code, created_by_phone):
        return {"ok": True, "leave": dict(cls.LEAVE), "shift_conflicts": []}

    @classmethod
    def approve_leave_request(cls, action, *, company_code, created_by_phone, account_id=None):
        assert action.get("allow_shift_conflicts") is True, "executor must cover conflicts post-confirmation"
        leave = {**cls.LEAVE, "status": "approved"}
        return {"ok": True, "leave": leave, "shift_conflicts": []}

    @classmethod
    def reject_leave_request(cls, action, *, company_code, created_by_phone, account_id=None):
        leave = {**cls.LEAVE, "status": "rejected"}
        return {"ok": True, "leave": leave}

    @classmethod
    def cancel_leave_request(cls, action, *, company_code, created_by_phone, account_id=None):
        leave = {**cls.LEAVE, "status": "cancelled"}
        return {"ok": True, "leave": leave}

    @staticmethod
    def format_leave_mutation_reply(result, action_type, employee_view=False):
        if not result.get("ok"):
            return "I could not update leave safely."
        return f"{action_type} done."

    @staticmethod
    def format_list_leave_requests_reply(result, employee_view=False):
        if not result.get("ok"):
            return "I could not list leave."
        return f"Leave ({len(result.get('leave_requests') or [])} request(s))."

    @staticmethod
    def normalize_posthire_result(result, *, action_type, reply=None):
        data = dict(result) if isinstance(result, dict) else {}
        ok = bool(data.get("ok"))
        if ok:
            status = "completed"
        elif data.get("needs_confirmation"):
            status = "needs_confirmation"
        else:
            status = "failed"
        safe = str(reply or data.get("safe_user_message") or data.get("message") or "").strip()
        if not safe:
            safe = "Done." if ok else "I could not complete that action."
        data["action_type"] = action_type
        data["success"] = ok
        data["status"] = status
        data["message"] = safe
        data["safe_user_message"] = safe
        return data

    # --- pending_actions DB shim ----------------------------------------
    class _FakeCursor:
        def __init__(self, store):
            self._store = store
            self._last_sql = ""

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def execute(self, sql, params=None):
            self._last_sql = sql

        def fetchone(self):
            sql = self._last_sql
            if "INSERT INTO pending_actions" in sql:
                row = {"action_id": "pending-1", "status": "pending"}
                self._store.append(row)
                return row
            if "FROM pending_actions" in sql:
                return None
            return None

        def fetchall(self):
            return []

    class _FakeConn:
        def __init__(self, store):
            self._store = store

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def cursor(self):
            return FakeLegacy._FakeCursor(self._store)

        def commit(self):
            pass

    _PENDING_STORE: list = []

    @classmethod
    def db_connect(cls):
        return cls._FakeConn(cls._PENDING_STORE)


class FakeRequest:
    def __init__(self):
        self.raw_text = "approve Sara's leave"
        self.account_id = "WATHEFNI"
        self.conversation_id = "leave-smoke"
        self.sender_phone = "+96597485758"
        self.metadata = {}


class FakeHTTPException(Exception):
    def __init__(self, detail):
        self.detail = detail


def assert_true(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def _scope(*, permissions, role="hr_manager", company="WATHEFNI"):
    return {
        "company_id": company,
        "account_id": company,
        "admin_user_id": "96597485758",
        "conversation_id": "leave-smoke",
        "channel": "web_dashboard",
        "module": "pre_hiring",
        "session_id": "sess-1",
        "role_scope": role,
        "permissions": list(permissions),
    }


def _tool_names(tools):
    return {str((t.get("function") or {}).get("name") or "") for t in tools}


def main() -> None:
    script_dir = Path(__file__).resolve().parent
    orchestrator_dir = script_dir
    if not (orchestrator_dir / "app.py").exists():
        orchestrator_dir = script_dir.parents[0] / "wathefni-orchestrator"
    sys.path.insert(0, str(orchestrator_dir))
    sys.modules["app"] = FakeLegacy()

    import action_registry
    import tool_call_orchestrator as tco

    # 1) Registry validation: the 5 leave actions exist and are well-formed.
    for name in LEAVE_TOOLS:
        spec = action_registry.spec_for(name)
        assert_true(spec is not None, f"{name} must be registered in action_registry")
        assert_true(spec.module == "leave", f"{name} must be gated by the leave module")
        assert_true(spec.executor is not None, f"{name} must have an executor")
    # Registry must still validate as a whole (no malformed leave specs).
    assert_true(action_registry.validate_registry(strict=False) == [], "registry must validate cleanly with leave actions")

    decisions = {"approve_leave_request", "reject_leave_request", "cancel_leave_request"}
    for name in decisions:
        spec = action_registry.spec_for(name)
        assert_true(bool(spec.requires_confirmation), f"{name} must require confirmation")
        assert_true(spec.preflight is not None, f"{name} must have a preflight to resolve the request before confirming")
        assert_true(spec.sensitive, f"{name} must be marked sensitive")
    for name in {"list_leave_requests", "request_leave"}:
        spec = action_registry.spec_for(name)
        assert_true(not spec.requires_confirmation, f"{name} must not require confirmation")
    assert_true(action_registry.spec_for("approve_leave_request").preflight is not None, "approve preflight reuses conflict logic")

    # 2) Permission map wired for all leave tools.
    assert_true(tco.TOOL_PERMISSION_MAP.get("list_leave_requests") == "leave.read", "list maps to leave.read")
    assert_true(tco.TOOL_PERMISSION_MAP.get("request_leave") == "leave.request", "request maps to leave.request")
    for name in decisions:
        assert_true(tco.TOOL_PERMISSION_MAP.get(name) == "leave.decide", f"{name} maps to leave.decide")
    assert_true("leave" in tco.TOOLCALL_GATED_MODULES, "leave must be a gated tool-call module")

    all_tools = action_registry.build_tool_schemas(FakeLegacy(), FakeRequest())
    assert_true(LEAVE_TOOLS.issubset(_tool_names(all_tools)), "build_tool_schemas must include leave tools")

    # 3) Visibility: full leave permissions + module enabled -> all leave tools.
    full_perms = ["prehire.read", "candidate.manage", "leave.read", "leave.request", "leave.decide"]
    visible_full = tco._visible_tools(all_tools, _scope(permissions=full_perms))
    assert_true(LEAVE_TOOLS.issubset(_tool_names(visible_full)), "entitled HR manager sees all leave tools")

    # 4) Viewer (leave.read only) sees only the read tool.
    viewer_tools = tco._visible_tools(all_tools, _scope(permissions=["prehire.read", "leave.read"], role="viewer"))
    names = _tool_names(viewer_tools)
    assert_true("list_leave_requests" in names, "viewer sees list_leave_requests")
    assert_true(not (decisions | {"request_leave"}) & names, "viewer must not see leave decision/request tools")

    # 5) Module-disabled company sees zero leave tools.
    original_modules = set(FakeLegacy.ENABLED_MODULES)
    try:
        FakeLegacy.ENABLED_MODULES = {"pre_hiring"}
        no_leave_tools = tco._visible_tools(all_tools, _scope(permissions=full_perms))
        assert_true(not LEAVE_TOOLS & _tool_names(no_leave_tools), "company without leave module sees no leave tools")
        # ... and execution is blocked even if a tool name leaks through.
        blocked = tco._execute_tool(
            "approve_leave_request",
            {"employee_name": "Sara Ahmad"},
            FakeRequest(),
            {},
            {},
            _scope(permissions=full_perms),
        )
        assert_true(blocked.get("status") == "module_disabled", "leave actions must be blocked when module disabled")
    finally:
        FakeLegacy.ENABLED_MODULES = original_modules

    # 6) Viewer cannot approve leave (permission gate before any execution).
    denied = tco._execute_tool(
        "approve_leave_request",
        {"employee_name": "Sara Ahmad"},
        FakeRequest(),
        {},
        {},
        _scope(permissions=["prehire.read", "leave.read"], role="viewer"),
    )
    assert_true(denied.get("status") == "permission_denied", "viewer must be denied approve_leave_request")

    # 7) Approving leave triggers the pending_actions confirmation flow.
    FakeLegacy._PENDING_STORE.clear()
    confirm = tco._execute_tool(
        "approve_leave_request",
        {"employee_name": "Sara Ahmad"},
        FakeRequest(),
        {},
        {},
        _scope(permissions=full_perms),
    )
    assert_true(confirm.get("status") == "needs_confirmation", "approve must ask for confirmation, not execute immediately")
    assert_true(confirm.get("action_hash"), "confirmation must bind a stable action_hash")
    assert_true(len(FakeLegacy._PENDING_STORE) == 1, "approve must persist exactly one pending_actions row")

    # 8) Read path executes end-to-end through the registry result contract.
    listed = tco._execute_tool(
        "list_leave_requests",
        {},
        FakeRequest(),
        {},
        {},
        _scope(permissions=full_perms),
    )
    assert_true(listed.get("status") == "completed", "list_leave_requests must complete for an entitled user")
    result = listed.get("result") if isinstance(listed.get("result"), dict) else {}
    assert_true(result.get("action_type") == "list_leave_requests", "result must carry the normalized action_type")
    assert_true(bool(result.get("safe_user_message")), "post-hire result must expose a safe_user_message")

    print("smoke-test-leave-registry: OK")


if __name__ == "__main__":
    main()
