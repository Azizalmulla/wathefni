"""P1 Setup→AI parity proofs: offers, assessment/interview/video reads, HR reads default-on."""

from __future__ import annotations

import os

import action_registry as registry
import assistant_capability_catalog as caps
import tool_call_orchestrator as orch


def test_p1_tools_registered():
    for name in (
        "list_assessment_attempts",
        "list_live_interviews",
        "list_video_interviews",
        "list_candidate_offers",
        "approve_employment_offer",
        "send_employment_offer",
    ):
        spec = registry.spec_for(name)
        assert spec is not None, name
        assert spec.executor is not None, name
    assert registry.spec_for("approve_employment_offer").requires_confirmation is True
    assert registry.spec_for("send_employment_offer").requires_confirmation is True
    assert registry.spec_for("list_candidate_offers").module == "employment_offers"


def test_p1_permission_map():
    assert orch.TOOL_PERMISSION_MAP["list_assessment_attempts"] == "assessment.manage"
    assert orch.TOOL_PERMISSION_MAP["list_live_interviews"] == "interview.manage"
    assert orch.TOOL_PERMISSION_MAP["list_video_interviews"] == "interview.manage"
    assert orch.TOOL_PERMISSION_MAP["list_candidate_offers"] == "offer.manage"
    assert orch.TOOL_PERMISSION_MAP["send_employment_offer"] == "offer.send"
    assert orch.TOOL_PERMISSION_MAP["approve_employment_offer"] == "offer.approve"


def test_employment_offers_hidden_when_module_off(monkeypatch):
    class Legacy:
        def company_has_module(self, company, module):
            return module in {"pre_hiring"}

        def setup_console_channel_policy(self, company):
            return {"pre_hiring": {"company_whatsapp": {"configured": True}}}

        def outbound_postmark_available(self):
            return True

    monkeypatch.setattr(orch, "_legacy", lambda: Legacy())
    tools = [
        {"type": "function", "function": {"name": n}}
        for n in ("list_candidate_offers", "send_employment_offer", "list_job_openings")
    ]
    visible = {
        t["function"]["name"]
        for t in orch._visible_tools(
            tools,
            {"company_id": "NOOFFER", "permissions": ["offer.manage", "offer.send", "prehire.read", "jobs.read"]},
        )
    }
    assert "list_job_openings" in visible
    assert "list_candidate_offers" not in visible
    assert "send_employment_offer" not in visible


def test_employment_offers_appear_when_module_on(monkeypatch):
    class Legacy:
        def company_has_module(self, company, module):
            return module in {"pre_hiring", "employment_offers"}

        def setup_console_channel_policy(self, company):
            return {"pre_hiring": {"company_whatsapp": {"configured": True}}}

        def outbound_postmark_available(self):
            return True

    monkeypatch.setattr(orch, "_legacy", lambda: Legacy())
    tools = [
        {"type": "function", "function": {"name": n}}
        for n in ("list_candidate_offers", "send_employment_offer", "approve_employment_offer")
    ]
    visible = {
        t["function"]["name"]
        for t in orch._visible_tools(
            tools,
            {
                "company_id": "OFFERCO",
                "permissions": ["offer.manage", "offer.send", "offer.approve"],
            },
        )
    }
    assert visible == {"list_candidate_offers", "send_employment_offer", "approve_employment_offer"}


def test_assessment_read_requires_module(monkeypatch):
    class Legacy:
        def company_has_module(self, company, module):
            return module == "pre_hiring"

        def setup_console_channel_policy(self, company):
            return {"pre_hiring": {"company_whatsapp": {"configured": False}}}

        def outbound_postmark_available(self):
            return False

    monkeypatch.setattr(orch, "_legacy", lambda: Legacy())
    tools = [{"type": "function", "function": {"name": "list_assessment_attempts"}}]
    visible = orch._visible_tools(
        tools,
        {"company_id": "X", "permissions": ["assessment.manage"]},
    )
    assert visible == []


def test_hr_reads_default_on(monkeypatch):
    import app as app_mod

    monkeypatch.delenv("WATHEFNI_ASSISTANT_HR_READS", raising=False)
    assert app_mod.assistant_hr_reads_enabled() is True
    monkeypatch.setenv("WATHEFNI_ASSISTANT_HR_READS", "off")
    assert app_mod.assistant_hr_reads_enabled() is False
    monkeypatch.setenv("WATHEFNI_ASSISTANT_HR_READS", "on")
    assert app_mod.assistant_hr_reads_enabled() is True


def test_catalog_includes_offers_and_interview_reads():
    assert "employment_offers" in caps.CAPABILITY_IDS
    assert "interviews_read" in caps.CAPABILITY_IDS
