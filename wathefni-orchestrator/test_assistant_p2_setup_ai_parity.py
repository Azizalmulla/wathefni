"""P2 Setup→AI parity: calendar tools, employee_app/push awareness, wave company lists."""

from __future__ import annotations

import action_registry as registry
import assistant_capability_catalog as caps
import platform_assistant_spine_wave1 as spine
import tool_call_orchestrator as orch


def test_calendar_tool_registered():
    spec = registry.spec_for("list_calendar_events")
    assert spec is not None
    assert spec.module == "calendar"
    assert orch.TOOL_PERMISSION_MAP["list_calendar_events"] == "calendar.read"


def test_calendar_hidden_without_module(monkeypatch):
    class Legacy:
        def company_has_module(self, company, module):
            return module == "pre_hiring"

        def setup_console_channel_policy(self, company):
            return {"pre_hiring": {"company_whatsapp": {"configured": False}}}

        def outbound_postmark_available(self):
            return False

    monkeypatch.setattr(orch, "_legacy", lambda: Legacy())
    tools = [{"type": "function", "function": {"name": "list_calendar_events"}}]
    visible = orch._visible_tools(tools, {"company_id": "NOCAL", "permissions": ["calendar.read"]})
    assert visible == []


def test_calendar_shown_with_module(monkeypatch):
    class Legacy:
        def company_has_module(self, company, module):
            return module == "calendar"

        def setup_console_channel_policy(self, company):
            return {}

        def outbound_postmark_available(self):
            return False

    monkeypatch.setattr(orch, "_legacy", lambda: Legacy())
    tools = [{"type": "function", "function": {"name": "list_calendar_events"}}]
    visible = {
        t["function"]["name"]
        for t in orch._visible_tools(tools, {"company_id": "CALCO", "permissions": ["calendar.read"]})
    }
    assert "list_calendar_events" in visible


def test_catalog_has_calendar_and_employee_app_caps():
    assert "calendar_module" in caps.CAPABILITY_IDS
    assert "employee_app" in caps.CAPABILITY_IDS
    assert "push_notifications" in caps.CAPABILITY_IDS


def test_wave1_company_list_not_hardcoded_single_tenant(monkeypatch):
    monkeypatch.setenv("WATHEFNI_PLATFORM_ASSISTANT_WAVE1", "on")
    monkeypatch.setenv("WATHEFNI_PLATFORM_ASSISTANT_WAVE1_COMPANIES", "ACME,BETA")
    assert spine.wave1_enabled_for_company("ACME") is True
    assert spine.wave1_enabled_for_company("BETA") is True
    assert spine.wave1_enabled_for_company("OTHER") is False
