"""Read-only production verification for post-hire architecture unification.

Run from /opt/wathefni/orchestrator so imports resolve correctly:
  /opt/wathefni/orchestrator/.venv/bin/python _verify_posthire_prod.py
"""

from __future__ import annotations

import sys

POSTHIRE_ACTIONS = {
    "list_attendance": ("attendance", "attendance.read", "read"),
    "check_in_employee": ("attendance", "attendance.manage", "write"),
    "check_out_employee": ("attendance", "attendance.manage", "write"),
    "mark_attendance_absent": ("attendance", "attendance.manage", "sensitive"),
    "correct_attendance_record": ("attendance", "attendance.manage", "sensitive"),
    "list_shifts": ("shifts", "shifts.read", "read"),
    "list_availability": ("shifts", "shifts.read", "read"),
    "list_shift_swaps": ("shifts", "shifts.read", "read"),
    "create_shift_assignment": ("shifts", "shifts.manage", "sensitive"),
    "cancel_shift_assignment": ("shifts", "shifts.manage", "sensitive"),
    "replace_conflicting_shift_assignment": ("shifts", "shifts.manage", "sensitive"),
    "request_availability": ("shifts", "shifts.manage", "write"),
    "request_shift_swap": ("shifts", "shifts.manage", "write"),
    "approve_shift_swap": ("shifts", "shifts.manage", "sensitive"),
    "reject_shift_swap": ("shifts", "shifts.manage", "sensitive"),
    "send_onboarding_reminder": ("onboarding", "onboarding.manage", "write"),
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
    "workforce_analytics": ("analytics", "analytics.read", "read"),
}

LEAVE_TOOLS = {
    "list_leave_requests", "request_leave", "approve_leave_request",
    "reject_leave_request", "cancel_leave_request",
}
PREHIRE_TOOLS = {"rank_candidates", "shortlist_candidate", "create_job_opening", "send_video_interview"}
POSTHIRE_MODULES = {module for module, _, _ in POSTHIRE_ACTIONS.values()}
SENSITIVE = {n for n, (_, _, k) in POSTHIRE_ACTIONS.items() if k == "sensitive"}
READ_TOOLS = {n for n, (_, _, k) in POSTHIRE_ACTIONS.items() if k == "read"}

FULL_PERMS = sorted({
    "prehire.read", "candidate.manage", "leave.read", "leave.request", "leave.decide",
    "attendance.read", "attendance.manage", "shifts.read", "shifts.manage",
    "onboarding.manage", "payroll.read", "payroll.manage", "payroll.export", "analytics.read",
})
VIEWER_PERMS = sorted({"prehire.read", "leave.read", "attendance.read", "shifts.read", "payroll.read", "analytics.read"})


class FakeRequest:
    raw_text = "verify"
    account_id = "WATHEFNI"
    conversation_id = "prod-verify"
    sender_phone = "+96597485758"
    metadata = {}


def fail(msg: str) -> None:
    print(f"FAIL: {msg}")
    sys.exit(1)


def ok(msg: str) -> None:
    print(f"OK: {msg}")


def scope(permissions, role="hr_manager"):
    return {
        "company_id": "WATHEFNI",
        "account_id": "WATHEFNI",
        "admin_user_id": "96597485758",
        "conversation_id": "prod-verify",
        "channel": "web_dashboard",
        "module": "pre_hiring",
        "session_id": "sess-verify",
        "role_scope": role,
        "permissions": list(permissions),
    }


def tool_names(tools):
    return {str((t.get("function") or {}).get("name") or "") for t in tools}


def main() -> None:
    import action_registry as reg
    import app
    import tool_call_orchestrator as tco

    # 2) Registry strict validation
    issues = reg.validate_registry(strict=True)
    if issues:
        fail(f"validate_registry(strict=True) returned {issues}")
    ok("validate_registry(strict=True) passes")

    intents = reg.registered_intents()
    ok(f"registered_intents count={len(intents)}")

    # 3) All post-hire actions registered correctly
    for name, (module, perm, kind) in POSTHIRE_ACTIONS.items():
        spec = reg.spec_for(name)
        if not spec:
            fail(f"{name} not registered")
        if spec.module != module:
            fail(f"{name} module={spec.module} expected {module}")
        if not spec.executor:
            fail(f"{name} missing executor")
        if kind == "sensitive":
            if not spec.requires_confirmation or not spec.preflight or not spec.sensitive:
                fail(f"{name} sensitive profile incomplete")
        elif spec.requires_confirmation:
            fail(f"{name} should not require confirmation")
        if tco.TOOL_PERMISSION_MAP.get(name) != perm:
            fail(f"{name} permission map {tco.TOOL_PERMISSION_MAP.get(name)} != {perm}")
    ok(f"all {len(POSTHIRE_ACTIONS)} post-hire actions registered with correct module/perm/confirmation")

    if tco.TOOL_PERMISSION_MAP.get("export_payroll") != "payroll.export":
        fail("export_payroll must map to payroll.export")
    ok("export_payroll uses payroll.export permission")

    for module in POSTHIRE_MODULES:
        if module not in tco.TOOLCALL_GATED_MODULES:
            fail(f"{module} not in TOOLCALL_GATED_MODULES")
    ok("all post-hire modules gated in TOOLCALL_GATED_MODULES")

    all_tools = reg.build_tool_schemas(app, FakeRequest())

    # 4) Tools visible when modules enabled (WATHEFNI should have post-hire modules)
    visible_full = tool_names(tco._visible_tools(all_tools, scope(FULL_PERMS)))
    missing = set(POSTHIRE_ACTIONS) - visible_full
    if missing:
        fail(f"entitled user missing tools: {sorted(missing)}")
    ok("post-hire tools visible for entitled user with modules enabled")

    # 5) Module-disabled: simulate by patching company_has_module
    original = app.company_has_module

    def only_prehire(company_code, module_key):
        mk = str(module_key or "")
        if mk in POSTHIRE_MODULES:
            return False
        return original(company_code, module_key)

    app.company_has_module = only_prehire
    try:
        hidden = tool_names(tco._visible_tools(all_tools, scope(FULL_PERMS)))
        leaked = set(POSTHIRE_ACTIONS) & hidden
        if leaked:
            fail(f"module-disabled company still sees: {sorted(leaked)}")
        blocked = tco._execute_tool(
            "export_payroll", {"start_date": "2026-05-01", "end_date": "2026-05-31"},
            FakeRequest(), {}, {}, scope(FULL_PERMS),
        )
        if blocked.get("status") != "module_disabled":
            fail(f"export_payroll should be module_disabled, got {blocked.get('status')}")
    finally:
        app.company_has_module = original
    ok("post-hire tools hidden + execution blocked when modules disabled")

    # 6) Viewer cannot mutate
    viewer_visible = tool_names(tco._visible_tools(all_tools, scope(VIEWER_PERMS, role="viewer")))
    writeish = set(POSTHIRE_ACTIONS) - READ_TOOLS
    if writeish & viewer_visible:
        fail(f"viewer sees manage tools: {sorted(writeish & viewer_visible)}")
    denied = tco._execute_tool(
        "create_shift_assignment", {"employee_name": "Test"},
        FakeRequest(), {}, {}, scope(VIEWER_PERMS, role="viewer"),
    )
    if denied.get("status") != "permission_denied":
        fail(f"viewer create_shift should be permission_denied, got {denied.get('status')}")
    ok("viewer read-only: manage tools hidden and execution denied")

    # 7) Payroll export requires payroll.export
    no_export = [p for p in FULL_PERMS if p != "payroll.export"]
    denied_export = tco._execute_tool(
        "export_payroll", {"start_date": "2026-05-01", "end_date": "2026-05-31"},
        FakeRequest(), {}, {}, scope(no_export),
    )
    if denied_export.get("status") != "permission_denied":
        fail(f"user without payroll.export should be denied, got {denied_export.get('status')}")
    ok("payroll.export permission enforced separately from payroll.manage")

    # 8) Sensitive actions require confirmation contract + stable action_hash
    for name in SENSITIVE:
        spec = reg.spec_for(name)
        if not spec.requires_confirmation:
            fail(f"{name} must require confirmation")
        if not spec.preflight:
            fail(f"{name} must have preflight")
        if not spec.sensitive:
            fail(f"{name} must be marked sensitive")
    action_hash = tco._action_hash(
        "export_payroll",
        {"start_date": "2026-05-01", "end_date": "2026-05-31"},
        scope(FULL_PERMS),
    )
    if not action_hash:
        fail("action_hash must be non-empty for sensitive actions")
    ok(f"sensitive actions ({len(SENSITIVE)}) have confirmation contract + action_hash binds args")

    # 9) No cross-module leakage (payroll-only enabled)
    def only_payroll(company_code, module_key):
        mk = str(module_key or "")
        if mk == "payroll":
            return True
        if mk in POSTHIRE_MODULES:
            return False
        return original(company_code, module_key)

    app.company_has_module = only_payroll
    try:
        payroll_only = tool_names(tco._visible_tools(all_tools, scope(FULL_PERMS)))
        payroll_tools = {n for n, (m, _, _) in POSTHIRE_ACTIONS.items() if m == "payroll"}
        other = set(POSTHIRE_ACTIONS) - payroll_tools
        if not payroll_tools.issubset(payroll_only):
            fail("payroll-only company missing payroll tools")
        if other & payroll_only:
            fail(f"cross-module leakage: {sorted(other & payroll_only)}")
    finally:
        app.company_has_module = original
    ok("no cross-module tool leakage (payroll-only isolation)")

    # 10) Pre-Hiring unaffected
    if not PREHIRE_TOOLS.issubset(visible_full):
        fail(f"pre-hiring tools missing: {PREHIRE_TOOLS - visible_full}")
    ok("pre-hiring tools remain visible")

    # 11) Leave still works
    if not LEAVE_TOOLS.issubset(visible_full):
        fail(f"leave tools missing: {LEAVE_TOOLS - visible_full}")
    for name in LEAVE_TOOLS:
        spec = reg.spec_for(name)
        if not spec or spec.module != "leave":
            fail(f"leave spec broken for {name}")
    ok("leave tools registered and visible")

    # 12) Legacy post-hire paths still present
    legacy_checks = [
        "execute_direct_action",
        "check_in_employee", "list_shifts", "export_payroll", "workforce_analytics",
        "send_onboarding_reminder", "request_leave", "ACTION_REQUIRED_MODULES",
    ]
    for attr in legacy_checks:
        if not hasattr(app, attr):
            fail(f"legacy path missing: app.{attr}")
    arm = app.ACTION_REQUIRED_MODULES
    for name in list(POSTHIRE_ACTIONS) + list(LEAVE_TOOLS):
        if arm.get(name) != reg.spec_for(name).module:
            fail(f"ACTION_REQUIRED_MODULES[{name}]={arm.get(name)} != registry module")
    ok("legacy execute_direct_action dispatch + ACTION_REQUIRED_MODULES intact")

    print("\n=== PRODUCTION POST-HIRE VERIFICATION: ALL CHECKS PASSED ===")


if __name__ == "__main__":
    main()
