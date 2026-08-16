"""Wave C entitlement blockers — interviews module + mobile assessments omit."""

from __future__ import annotations

import action_registry as registry
import operator_mobile as mobile
import tool_call_orchestrator as tco
from module_catalog import TOOLCALL_GATED_MODULES


LIVE_INTERVIEW_TOOLS = (
    "schedule_interview",
    "reschedule_interview",
    "cancel_interview",
    "send_interview_invite",
    "get_interview_invite_status",
)


class _App:
    def __init__(self, modules: set[str]):
        self._modules = set(modules)

    def company_has_module(self, company, module):
        return module in self._modules

    def configured_company_modules(self, company_code):
        return set(self._modules)


FULL_PERMS = [
    "prehire.read",
    "candidate.manage",
    "candidate.decide",
    "interview.manage",
    "assessment.manage",
]


def test_live_interview_actionspecs_require_interviews_module():
    assert "interviews" in TOOLCALL_GATED_MODULES
    for name in LIVE_INTERVIEW_TOOLS:
        spec = registry.spec_for(name)
        assert spec is not None, name
        assert spec.module == "interviews", name
        mapped = [m for m, _p in tco._required_entitlements(name, {}, spec, "interview.manage")]
        assert "interviews" in mapped, (name, mapped)


def test_visible_tools_hide_live_interviews_when_module_off(monkeypatch=None):
    app = _App({"pre_hiring", "video_interviews", "assessments"})
    monkeypatch_legacy = getattr(tco, "_legacy", None)

    def _legacy():
        return app

    tco._legacy = _legacy  # type: ignore[attr-defined]
    try:
        schemas = registry.build_tool_schemas(app, None)
        visible = tco._visible_tools(
            schemas,
            {"company_id": "WCTEST", "permissions": FULL_PERMS},
        )
        names = {str(((t.get("function") or {}).get("name") or "")) for t in visible if isinstance(t, dict)}
        assert not (set(LIVE_INTERVIEW_TOOLS) & names)
        assert "send_video_interview" in names
        assert "send_assessment" in names
    finally:
        if monkeypatch_legacy is not None:
            tco._legacy = monkeypatch_legacy  # type: ignore[attr-defined]


def test_visible_tools_show_live_interviews_when_module_on():
    app = _App({"pre_hiring", "interviews", "assessments"})
    previous = tco._legacy

    def _legacy():
        return app

    tco._legacy = _legacy  # type: ignore[attr-defined]
    try:
        schemas = registry.build_tool_schemas(app, None)
        visible = tco._visible_tools(
            schemas,
            {"company_id": "WCTEST", "permissions": FULL_PERMS},
        )
        names = {str(((t.get("function") or {}).get("name") or "")) for t in visible if isinstance(t, dict)}
        assert set(LIVE_INTERVIEW_TOOLS).issubset(names)
    finally:
        tco._legacy = previous  # type: ignore[attr-defined]


def test_execution_blocks_schedule_interview_when_interviews_off():
    app = _App({"pre_hiring"})
    previous = tco._legacy

    def _legacy():
        return app

    tco._legacy = _legacy  # type: ignore[attr-defined]
    try:
        blocked = tco._require_tool_entitlements(
            "schedule_interview",
            {},
            registry.spec_for("schedule_interview"),
            "interview.manage",
            {"company_id": "WCTEST", "permissions": FULL_PERMS, "actor_user_id": "actor-a"},
        )
        assert blocked is not None
        assert blocked.get("status") == "module_disabled" or "module" in str(blocked).lower()
    finally:
        tco._legacy = previous  # type: ignore[attr-defined]


def test_mobile_omits_assessments_when_off():
    off = mobile.build_recruiting_workspace_capabilities(
        _App({"pre_hiring", "interviews"}),
        {"company_code": "WCTEST", "permissions": FULL_PERMS},
    )
    assert "assessments" not in off
    assert "interview_status" in off
    assert "interview_notes" in off

    on = mobile.build_recruiting_workspace_capabilities(
        _App({"pre_hiring", "assessments"}),
        {"company_code": "WCTEST", "permissions": FULL_PERMS},
    )
    assert "assessments" in on
    assert on["assessments"]["enabled"] is True
    assert "interview_status" not in on
    assert "interview_notes" not in on


def test_mobile_omits_live_interview_features_when_interviews_off():
    caps = mobile.build_recruiting_workspace_capabilities(
        _App({"pre_hiring", "assessments", "video_interviews"}),
        {"company_code": "WCTEST", "permissions": FULL_PERMS},
    )
    assert "interview_status" not in caps
    assert "interview_notes" not in caps
    assert "assessments" in caps


if __name__ == "__main__":
    test_live_interview_actionspecs_require_interviews_module()
    test_visible_tools_hide_live_interviews_when_module_off()
    test_visible_tools_show_live_interviews_when_module_on()
    test_execution_blocks_schedule_interview_when_interviews_off()
    test_mobile_omits_assessments_when_off()
    test_mobile_omits_live_interview_features_when_interviews_off()
    print("wave C entitlement blockers PASS")
