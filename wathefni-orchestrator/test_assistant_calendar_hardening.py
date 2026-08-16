"""Tests for schedule→interview_service migration, Microsoft helpers, cancel reconciliation."""

from __future__ import annotations

import inspect
from types import SimpleNamespace


def test_schedule_executor_uses_interview_service():
    import action_registry as registry

    src = inspect.getsource(registry._schedule_interview_executor)
    assert "interview_service" in src
    assert "run_gog" not in src
    assert "create_candidate_interview_from_schedule" not in src
    assert "legacy direct gog" in src  # documents migration away from gog


def test_microsoft_meeting_type_normalized():
    import interview_lifecycle as life

    assert life.normalize_meeting_type("teams") == "microsoft_teams"
    assert life.normalize_meeting_type("microsoft_teams") == "microsoft_teams"
    assert "microsoft_teams" in life.MEETING_TYPES


def test_resolve_meeting_fields_microsoft():
    import interview_service as svc

    fields = svc.resolve_meeting_fields(meeting_type="microsoft_teams", microsoft_connected=True)
    assert fields["meeting_type"] == "microsoft_teams"
    assert fields["provider_key"] == "microsoft"
    fields2 = svc.resolve_meeting_fields(meeting_type="microsoft_teams", microsoft_connected=False, meet_link="https://x")
    assert fields2["meeting_type"] == "manual_link"


def test_sync_provider_routes_microsoft():
    import interview_service as svc

    src = inspect.getsource(svc.sync_provider_for_interview)
    assert "_sync_microsoft_for_interview" in src
    assert "interview_microsoft_calendar" in inspect.getsource(svc._sync_microsoft_for_interview)


def test_cancel_reconciliation_prefers_completed_tool_result():
    import tool_call_orchestrator as orch

    src = inspect.getsource(orch._handle_toolcall_whatsapp_turn_impl)
    assert "Stopped further steps. The last action already completed successfully." in src
    assert 'last_status = "cancelled"' in src  # only when no successful tool


def test_microsoft_calendar_helpers_shape():
    import interview_microsoft_calendar as mcal

    assert callable(mcal.create_teams_event)
    assert callable(mcal.update_teams_event)
    assert callable(mcal.cancel_teams_event)
    assert callable(mcal.mint_graph_token)


if __name__ == "__main__":
    test_schedule_executor_uses_interview_service()
    test_microsoft_meeting_type_normalized()
    test_resolve_meeting_fields_microsoft()
    test_sync_provider_routes_microsoft()
    test_cancel_reconciliation_prefers_completed_tool_result()
    test_microsoft_calendar_helpers_shape()
    print("assistant-calendar-hardening unit PASS")
