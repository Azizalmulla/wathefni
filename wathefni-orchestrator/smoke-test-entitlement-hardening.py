from __future__ import annotations

from pathlib import Path


def assert_true(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def main() -> None:
    root = Path(__file__).resolve().parent
    app_source = (root / "app.py").read_text(encoding="utf-8")
    registry_source = (root / "action_registry.py").read_text(encoding="utf-8")
    toolcall_source = (root / "tool_call_orchestrator.py").read_text(encoding="utf-8")
    frontend_source = (root.parent / "apps" / "wathefni-dashboard" / "src" / "App.tsx").read_text(encoding="utf-8")
    frontend_test_source = (root.parent / "apps" / "wathefni-dashboard" / "src" / "App.test.tsx").read_text(encoding="utf-8")

    assert_true("def require_entitlement(" in app_source, "central require_entitlement helper must exist")
    assert_true('return require_entitlement(context, "pre_hiring", "prehire.read")' in app_source, "pre-hiring dashboard routes must fail closed through entitlement")
    assert_true('return require_entitlement(context, "assessments", "prehire.read")' in app_source, "assessment dashboard routes must check module entitlement")
    assert_true('require_entitlement(context, "assessments", "assessment.manage")' in app_source, "assessment mutations must require module + permission")
    assert_true('require_entitlement(context, "video_interviews", "interview.manage")' in app_source, "video interview mutations must require module + permission")
    assert_true('"send_assessment": "assessments"' in app_source, "legacy action module map must gate send_assessment by assessments")
    assert_true('"send_video_interview": "video_interviews"' in app_source, "legacy action module map must gate send_video_interview by video_interviews")
    assert_true("company_has_module(interview.get(\"company_code\"), \"video_interviews\")" in app_source, "public video links must check video_interviews module")
    assert_true("This link is no longer available. Please contact the hiring team if you need a new link." in app_source, "public disabled-module links must return candidate-safe copy")

    assert_true('module="assessments"' in registry_source, "ActionSpec.module must gate send_assessment by assessments")
    assert_true('module="video_interviews"' in registry_source, "ActionSpec.module must gate send_video_interview by video_interviews")
    assert_true("_require_tool_entitlements" in toolcall_source, "AI tool execution must have an entitlement gate")
    assert_true("entitlement_denied = _require_tool_entitlements" in toolcall_source, "AI tool execution must call entitlement before preflight/executor")
    assert_true("_mixed_item_action_names" in toolcall_source and "_workflow_step_names" in toolcall_source, "batch/workflow item modules must be inspected")

    assert_true("dashboardModuleEnabled" in frontend_source, "dashboard nav must derive from enabled_modules")
    assert_true("availableNavItems" in frontend_source, "disabled modules must not render as usable nav items")
    assert_true("This feature is not enabled for this company." in frontend_source, "module disabled errors must use HR-safe copy")
    assert_true("hides assessment navigation when the module is disabled" in frontend_test_source, "frontend must test disabled assessment nav")

    print("entitlement hardening smoke tests passed")


if __name__ == "__main__":
    main()
