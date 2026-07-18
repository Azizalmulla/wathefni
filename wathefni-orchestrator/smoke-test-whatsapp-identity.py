"""Item 4 — WhatsApp HR identity / permission hardening smoke tests.

Verifies the WATHEFNI_STRICT_WHATSAPP_PERMS flag and its fail-closed behaviour
without touching the database (app is stubbed via sys.modules, mirroring
smoke-test-toolcall-orchestrator.py).

Guarantees checked:
  - Flag defaults OFF and parses common truthy values.
  - Flag OFF  → legacy behaviour preserved (empty perms stay admin-capable).
  - Flag ON   → empty/unlinked identity can READ but cannot MUTATE (fail closed).
  - Flag ON   → linked owner (real permission set) is unaffected.
  - Denials use a clear, HR-facing access message (no raw codes/tool names).
  - Employee self-service routes through the non-HR turn handler, never the
    orchestrator permission gate (so it cannot be affected by this flag).
"""

from __future__ import annotations

import os
import sys
from pathlib import Path


class FakeLegacy:
    ENABLED_MODULES = {
        "pre_hiring", "assessments", "video_interviews",
        "leave", "attendance", "shifts", "onboarding", "payroll", "analytics",
    }

    @staticmethod
    def json_safe(value):
        return value

    @staticmethod
    def digits(value):
        return "".join(ch for ch in str(value or "") if ch.isdigit())

    @classmethod
    def company_has_module(cls, company_code, module_key):
        return str(module_key or "") in cls.ENABLED_MODULES

    @classmethod
    def require_entitlement(cls, context, module_key, permission=None):
        return context

    @staticmethod
    def request_company_code(request):
        return "WATHEFNI"


class FakeRequest:
    raw_text = "approve fatima's leave"
    account_id = None
    conversation_id = None
    sender_phone = "+96599999999"
    sender_role = "hr_admin"
    metadata = {}


def assert_true(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


# Representative real permission set for a linked owner.
OWNER_PERMS = [
    "prehire.read", "candidate.manage", "candidate.decide", "candidate.import",
    "interview.manage", "assessment.manage", "report.export", "settings.manage", "users.manage",
    "leave.read", "leave.request", "leave.decide",
    "attendance.read", "attendance.manage",
    "shifts.read", "shifts.manage",
    "onboarding.read", "onboarding.manage",
    "payroll.read", "payroll.manage", "payroll.export",
    "analytics.read",
]


def _scope(permissions):
    return {
        "company_id": "WATHEFNI",
        "account_id": "WATHEFNI",
        "admin_user_id": "96599999999",
        "conversation_id": "wa-identity-smoke",
        "channel": "whatsapp",
        "module": "pre_hiring",
        "role_scope": "hr_admin",
        "permissions": list(permissions),
    }


def _set_flag(value: str | None) -> None:
    if value is None:
        os.environ.pop("WATHEFNI_STRICT_WHATSAPP_PERMS", None)
    else:
        os.environ["WATHEFNI_STRICT_WHATSAPP_PERMS"] = value


def main() -> None:
    script_dir = Path(__file__).resolve().parent
    orchestrator_dir = script_dir
    if not (orchestrator_dir / "app.py").exists():
        orchestrator_dir = script_dir.parents[0] / "wathefni-orchestrator"
    sys.path.insert(0, str(orchestrator_dir))
    sys.modules["app"] = FakeLegacy()

    import action_registry  # noqa: F401
    import tool_call_orchestrator as tc

    app_source = (orchestrator_dir / "app.py").read_text(encoding="utf-8")

    passed: list[str] = []

    def ok(label: str) -> None:
        passed.append(label)
        print(f"      PASS  {label}")

    # Always restore the environment to a known-off state at the end.
    original_flag = os.environ.get("WATHEFNI_STRICT_WHATSAPP_PERMS")
    try:
        # --- flag parsing ---------------------------------------------------
        _set_flag(None)
        assert_true(tc._strict_whatsapp_perms() is False, "flag must default OFF when unset")
        ok("flag defaults OFF when unset")
        for truthy in ("1", "true", "TRUE", "yes", "on"):
            _set_flag(truthy)
            assert_true(tc._strict_whatsapp_perms() is True, f"flag must be ON for {truthy!r}")
        for falsy in ("0", "false", "no", "off", ""):
            _set_flag(falsy)
            assert_true(tc._strict_whatsapp_perms() is False, f"flag must be OFF for {falsy!r}")
        ok("flag parses truthy/falsy values correctly")

        # --- read-only classification --------------------------------------
        assert_true(tc._is_read_only_permission("attendance.read") is True, "*.read is read-only")
        assert_true(tc._is_read_only_permission("attendance.manage") is False, "*.manage is mutating")
        assert_true(tc._is_read_only_permission("payroll.export") is False, "*.export is mutating")
        assert_true(tc._is_read_only_permission(None) is False, "None is not read-only")
        ok("read-only permission classification correct")

        empty = _scope([])
        owner = _scope(OWNER_PERMS)
        viewer = _scope(["prehire.read", "leave.read", "attendance.read", "payroll.read", "analytics.read"])

        # --- flag OFF: legacy behaviour preserved --------------------------
        _set_flag("0")
        allow_read, _ = tc._tool_allowed("list_attendance", empty)
        allow_mut, _ = tc._tool_allowed("approve_leave_request", empty)
        assert_true(allow_read is True, "flag off: empty perms can read")
        assert_true(allow_mut is True, "flag off: empty perms keep legacy admin-capable mutate")
        ok("flag OFF preserves legacy empty-perms behaviour (no regression on deploy)")

        # --- flag ON: empty/unlinked identity fails closed for mutation ----
        _set_flag("1")
        allow_read, _ = tc._tool_allowed("list_attendance", empty)
        allow_mut, req = tc._tool_allowed("approve_leave_request", empty)
        assert_true(allow_read is True, "flag on: empty perms can still READ")
        assert_true(allow_mut is False, "flag on: empty perms cannot MUTATE")
        assert_true(req == "leave.decide", "denied mutate reports the required permission")
        ok("flag ON: unlinked/empty identity reads but cannot mutate")

        for tool in ("export_payroll", "approve_timesheet", "mark_attendance_absent", "create_shift_assignment", "send_onboarding_reminder", "hire_candidate", "request_leave"):
            allowed, _ = tc._tool_allowed(tool, empty)
            assert_true(allowed is False, f"flag on: empty perms must not authorize {tool}")
        for tool in ("list_attendance", "list_timesheets", "workforce_analytics", "list_shifts", "list_leave_requests"):
            allowed, _ = tc._tool_allowed(tool, empty)
            assert_true(allowed is True, f"flag on: empty perms must still allow read tool {tool}")
        ok("flag ON: every mutating tool fails closed for empty perms; reads still allowed")

        # --- flag ON: linked owner unaffected ------------------------------
        for tool in ("approve_leave_request", "export_payroll", "approve_timesheet", "create_shift_assignment", "hire_candidate"):
            allowed, _ = tc._tool_allowed(tool, owner)
            assert_true(allowed is True, f"flag on: linked owner must still run {tool}")
        ok("flag ON: linked owner (real permission set) is unaffected")

        # --- flag ON: partial role still gated by its real permissions -----
        allowed_view_mut, _ = tc._tool_allowed("approve_leave_request", viewer)
        allowed_view_read, _ = tc._tool_allowed("list_leave_requests", viewer)
        assert_true(allowed_view_mut is False, "flag on: viewer cannot approve leave")
        assert_true(allowed_view_read is True, "flag on: viewer can read leave")
        ok("flag ON: partial-permission role enforced by its own permission set")

        # --- _visible_tools filtering --------------------------------------
        tools = action_registry.build_tool_schemas(FakeLegacy(), FakeRequest())

        def names(scope):
            return {str((t.get("function") or {}).get("name") or "") for t in tc._visible_tools(tools, scope)}

        _set_flag("0")
        off_names = names(empty)
        assert_true("approve_leave_request" in off_names, "flag off: gated mutate tool visible to empty perms")

        _set_flag("1")
        on_empty = names(empty)
        assert_true("approve_leave_request" not in on_empty, "flag on: gated mutate tool hidden from empty perms")
        assert_true("export_payroll" not in on_empty, "flag on: payroll export hidden from empty perms")
        assert_true("list_attendance" in on_empty, "flag on: gated read tool still visible to empty perms")
        on_owner = names(owner)
        assert_true("approve_leave_request" in on_owner, "flag on: owner still sees gated mutate tools")
        ok("_visible_tools hides mutating gated tools from unlinked identity (owner unaffected)")

        # --- execution-time denial message is HR-facing --------------------
        _set_flag("1")
        denied = tc._execute_tool("approve_leave_request", {}, FakeRequest(), {}, {}, empty)
        assert_true(denied.get("status") == "permission_denied", "strict empty-perms mutate must be denied at execution")
        assert_true(denied.get("reason") == "identity_not_linked", "denial must carry identity_not_linked reason")
        message = str(denied.get("message") or "")
        assert_true("link" in message.lower(), "denial message must guide the user to link their number")
        for leak in ("permission_denied", "identity_not_linked", "approve_leave_request", "leave.decide", "_", "traceback"):
            assert_true(leak not in message, f"denial message must not leak technical token {leak!r}")
        ok("execution-time denial uses a clear, HR-facing access message (no raw tokens)")

        # --- employee self-service is on a different code path -------------
        assert_true("handle_non_hr_conversational_turn" in app_source, "non-HR self-service handler must exist")
        guard_idx = app_source.find('request.sender_role != "hr_admin" and not is_hr_phone')
        toolcall_idx = app_source.find("handle_toolcall_whatsapp_turn(request)")
        assert_true(guard_idx != -1, "non-HR branch guard must exist before the orchestrator call")
        assert_true(toolcall_idx != -1 and guard_idx < toolcall_idx, "non-HR self-service must be routed before the HR orchestrator path")
        ok("employee self-service routes through the non-HR handler, not the hardened orchestrator gate")

    finally:
        _set_flag(original_flag)

    print(f"\n    {len(passed)} passed, 0 failed")
    print("\n    WHATSAPP IDENTITY HARDENING: ALL CHECKS PASSED")


if __name__ == "__main__":
    main()
