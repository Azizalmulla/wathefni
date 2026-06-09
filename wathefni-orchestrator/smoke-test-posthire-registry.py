"""Smoke test for the broad post-hire migration onto the registry / tool-call
architecture (attendance, shifts, onboarding, payroll, analytics).

Proves the post-hire modules run at the same architecture level as Pre-Hiring
and Leave:
  - every post-hire action is registered in action_registry with the right module
  - the sensitive subset requires confirmation + has a preflight + is marked sensitive
  - reads/routine writes do NOT require confirmation
  - TOOL_PERMISSION_MAP wires each tool to its permission; export_payroll has its
    own payroll.export permission
  - all post-hire modules are gated tool-call modules
  - tools are only visible to companies that enabled the module AND users who hold
    the matching permission (no cross-module leakage)
  - a viewer sees only read tools and is denied manage/export actions
  - a sensitive action (export_payroll) triggers the pending_actions confirmation
    flow with a stable action_hash
  - a module-disabled company sees zero tools for that module and cannot execute them
  - a read path (workforce_analytics) executes end-to-end through the result contract
  - pre-hiring and leave tools are unaffected

The legacy execute_direct_action / infer_* / pending_operations paths are
intentionally untouched; this test only exercises the new registry surface.
"""

from __future__ import annotations

import sys
from pathlib import Path


# name -> (module, permission, kind in {"read","write","sensitive"})
POSTHIRE_ACTIONS = {
    # Attendance
    "list_attendance": ("attendance", "attendance.read", "read"),
    "check_in_employee": ("attendance", "attendance.manage", "write"),
    "check_out_employee": ("attendance", "attendance.manage", "write"),
    "mark_attendance_absent": ("attendance", "attendance.manage", "sensitive"),
    "correct_attendance_record": ("attendance", "attendance.manage", "sensitive"),
    # Shifts
    "list_shifts": ("shifts", "shifts.read", "read"),
    "list_availability": ("shifts", "shifts.read", "read"),
    "list_shift_swaps": ("shifts", "shifts.read", "read"),
    "create_shift_assignment": ("shifts", "shifts.manage", "write"),
    "cancel_shift_assignment": ("shifts", "shifts.manage", "sensitive"),
    "replace_conflicting_shift_assignment": ("shifts", "shifts.manage", "sensitive"),
    "request_availability": ("shifts", "shifts.manage", "write"),
    "request_shift_swap": ("shifts", "shifts.manage", "write"),
    "approve_shift_swap": ("shifts", "shifts.manage", "sensitive"),
    "reject_shift_swap": ("shifts", "shifts.manage", "sensitive"),
    # Onboarding
    "send_onboarding_reminder": ("onboarding", "onboarding.manage", "write"),
    "start_onboarding": ("onboarding", "onboarding.manage", "sensitive"),
    "onboarding_mark_item": ("onboarding", "onboarding.manage", "sensitive"),
    # Payroll
    "list_payroll_hours": ("payroll", "payroll.read", "read"),
    "list_timesheets": ("payroll", "payroll.read", "read"),
    "show_payroll_policy": ("payroll", "payroll.read", "read"),
    "preview_payroll": ("payroll", "payroll.read", "read"),
    "list_payroll_exports": ("payroll", "payroll.read", "read"),
    "create_timesheet_review": ("payroll", "payroll.manage", "write"),
    "approve_timesheet": ("payroll", "payroll.manage", "sensitive"),
    "reject_timesheet": ("payroll", "payroll.manage", "sensitive"),
    "set_payroll_policy": ("payroll", "payroll.manage", "sensitive"),
    "export_payroll": ("payroll", "payroll.export", "sensitive"),
    # Analytics
    "workforce_analytics": ("analytics", "analytics.read", "read"),
}

POSTHIRE_MODULES = {"attendance", "shifts", "onboarding", "payroll", "analytics"}
ALL_POSTHIRE_TOOLS = set(POSTHIRE_ACTIONS)
SENSITIVE_TOOLS = {n for n, (_, _, k) in POSTHIRE_ACTIONS.items() if k == "sensitive"}
READ_TOOLS = {n for n, (_, _, k) in POSTHIRE_ACTIONS.items() if k == "read"}

FULL_PERMS = [
    "prehire.read", "candidate.manage",
    "attendance.read", "attendance.manage",
    "shifts.read", "shifts.manage",
    "onboarding.manage",
    "payroll.read", "payroll.manage", "payroll.export",
    "analytics.read",
    "leave.read", "leave.request", "leave.decide",
]
VIEWER_PERMS = [
    "prehire.read", "attendance.read", "shifts.read", "payroll.read", "analytics.read", "leave.read",
]


class FakeHTTPException(Exception):
    def __init__(self, detail):
        self.detail = detail


class FakeLegacy:
    ENABLED_MODULES = {
        "pre_hiring", "assessments", "video_interviews", "leave",
        "attendance", "shifts", "onboarding", "payroll", "analytics",
    }

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

    # --- one read executor exercised end-to-end --------------------------
    @classmethod
    def workforce_analytics(cls, action, *, company_code, sync_sheet=True):
        return {"ok": True, "metric": action.get("metric") or "headcount", "value": 42, "company_code": company_code}

    @staticmethod
    def format_workforce_analytics_reply(result):
        if not result.get("ok"):
            return "I could not pull that analytic."
        return f"{result.get('metric')}: {result.get('value')}."

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
        self.raw_text = "export payroll for last month"
        self.account_id = "WATHEFNI"
        self.conversation_id = "posthire-smoke"
        self.sender_phone = "+96597485758"
        self.metadata = {}


def assert_true(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def _scope(*, permissions, role="hr_manager", company="WATHEFNI"):
    return {
        "company_id": company,
        "account_id": company,
        "admin_user_id": "96597485758",
        "conversation_id": "posthire-smoke",
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

    # 1) Registry validates as a whole.
    assert_true(action_registry.validate_registry(strict=False) == [], "registry must validate cleanly with post-hire actions")

    # 2) Every post-hire action registered with the right module + executor, and
    #    the right confirmation / preflight / sensitivity profile.
    for name, (module, _perm, kind) in POSTHIRE_ACTIONS.items():
        spec = action_registry.spec_for(name)
        assert_true(spec is not None, f"{name} must be registered in action_registry")
        assert_true(spec.module == module, f"{name} must be gated by the {module} module (got {spec.module})")
        assert_true(spec.executor is not None, f"{name} must have an executor")
        if kind == "sensitive":
            assert_true(bool(spec.requires_confirmation), f"{name} must require confirmation")
            assert_true(spec.preflight is not None, f"{name} must have a confirm preflight")
            assert_true(spec.sensitive, f"{name} must be marked sensitive")
        else:
            assert_true(not spec.requires_confirmation, f"{name} ({kind}) must not require confirmation")

    # 3) Permission map + gated modules wired for every post-hire tool.
    for name, (_module, perm, _kind) in POSTHIRE_ACTIONS.items():
        assert_true(tco.TOOL_PERMISSION_MAP.get(name) == perm, f"{name} must map to {perm}")
    assert_true(tco.TOOL_PERMISSION_MAP.get("export_payroll") == "payroll.export", "export_payroll must use its own payroll.export permission")
    for module in POSTHIRE_MODULES:
        assert_true(module in tco.TOOLCALL_GATED_MODULES, f"{module} must be a gated tool-call module")

    all_tools = action_registry.build_tool_schemas(FakeLegacy(), FakeRequest())
    assert_true(ALL_POSTHIRE_TOOLS.issubset(_tool_names(all_tools)), "build_tool_schemas must include all post-hire tools")

    # 4) Full permissions + all modules enabled -> all post-hire tools visible.
    visible_full = _tool_names(tco._visible_tools(all_tools, _scope(permissions=FULL_PERMS)))
    missing = ALL_POSTHIRE_TOOLS - visible_full
    assert_true(not missing, f"entitled HR manager should see all post-hire tools, missing: {sorted(missing)}")

    # 5) Viewer sees only read tools, never manage/sensitive.
    viewer_visible = _tool_names(tco._visible_tools(all_tools, _scope(permissions=VIEWER_PERMS, role="viewer")))
    assert_true(READ_TOOLS.issubset(viewer_visible), "viewer must see post-hire read tools")
    writeish = ALL_POSTHIRE_TOOLS - READ_TOOLS
    assert_true(not (writeish & viewer_visible), f"viewer must not see manage/sensitive tools: {sorted(writeish & viewer_visible)}")

    # 6) Pre-hiring + leave tools are unaffected by the gating.
    assert_true("rank_candidates" in visible_full, "pre-hiring tools must remain visible")
    assert_true("list_leave_requests" in visible_full, "leave tools must remain visible with full perms")

    # 7) No cross-module leakage: enabling ONLY payroll shows payroll tools but not
    #    attendance/shifts/onboarding/analytics tools.
    original_modules = set(FakeLegacy.ENABLED_MODULES)
    try:
        FakeLegacy.ENABLED_MODULES = {"pre_hiring", "payroll"}
        payroll_only = _tool_names(tco._visible_tools(all_tools, _scope(permissions=FULL_PERMS)))
        payroll_tools = {n for n, (m, _, _) in POSTHIRE_ACTIONS.items() if m == "payroll"}
        other_posthire = ALL_POSTHIRE_TOOLS - payroll_tools
        assert_true(payroll_tools.issubset(payroll_only), "payroll tools visible when payroll enabled")
        assert_true(not (other_posthire & payroll_only), f"non-payroll post-hire tools must be hidden: {sorted(other_posthire & payroll_only)}")

        # ... and execution of a disabled-module tool is blocked even if leaked.
        blocked = tco._execute_tool(
            "create_shift_assignment", {"employee_name": "Sara Ahmad"},
            FakeRequest(), {}, {}, _scope(permissions=FULL_PERMS),
        )
        assert_true(blocked.get("status") == "module_disabled", "shift action must be blocked when shifts module disabled")
    finally:
        FakeLegacy.ENABLED_MODULES = original_modules

    # 8) Permission gate: viewer cannot export payroll (most sensitive money action).
    denied = tco._execute_tool(
        "export_payroll", {"start_date": "2026-05-01", "end_date": "2026-05-31"},
        FakeRequest(), {}, {}, _scope(permissions=VIEWER_PERMS, role="viewer"),
    )
    assert_true(denied.get("status") == "permission_denied", "viewer must be denied export_payroll")

    # 9) Sensitive money action triggers the pending_actions confirmation flow.
    FakeLegacy._PENDING_STORE.clear()
    confirm = tco._execute_tool(
        "export_payroll", {"start_date": "2026-05-01", "end_date": "2026-05-31"},
        FakeRequest(), {}, {}, _scope(permissions=FULL_PERMS),
    )
    assert_true(confirm.get("status") == "needs_confirmation", "export_payroll must ask for confirmation, not execute immediately")
    assert_true(confirm.get("action_hash"), "confirmation must bind a stable action_hash")
    assert_true(len(FakeLegacy._PENDING_STORE) == 1, "export_payroll must persist exactly one pending_actions row")

    # 10) Read path executes end-to-end through the registry result contract.
    listed = tco._execute_tool(
        "workforce_analytics", {"metric": "headcount"},
        FakeRequest(), {}, {}, _scope(permissions=FULL_PERMS),
    )
    assert_true(listed.get("status") == "completed", "workforce_analytics must complete for an entitled user")
    result = listed.get("result") if isinstance(listed.get("result"), dict) else {}
    assert_true(result.get("action_type") == "workforce_analytics", "result must carry the normalized action_type")
    assert_true(bool(result.get("safe_user_message")), "post-hire result must expose a safe_user_message")

    print(f"smoke-test-posthire-registry: OK ({len(POSTHIRE_ACTIONS)} actions across {len(POSTHIRE_MODULES)} modules)")


if __name__ == "__main__":
    main()
