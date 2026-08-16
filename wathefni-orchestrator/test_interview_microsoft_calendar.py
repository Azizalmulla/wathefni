"""Unit tests for Teams Online Meetings + calendar link helper (no live Graph)."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest import mock

import interview_microsoft_calendar as mcal


def test_create_teams_event_uses_online_meetings_then_calendar():
    token = "t"
    calls = []

    def fake_graph(method, path, token, body=None):
        calls.append((method, path, body))
        if method == "POST" and "/onlineMeetings" in path:
            assert "dcb6b7dd-8509-4a20-8069-ec0de9445dd7" in path
            return {
                "ok": True,
                "status": 201,
                "json": {
                    "id": "om-1",
                    "joinWebUrl": "https://teams.microsoft.com/l/meetup-join/abc",
                },
            }
        if method == "POST" and path.endswith("/events"):
            assert "isOnlineMeeting" not in (body or {})
            assert "teams.microsoft.com" in ((body or {}).get("body") or {}).get("content", "")
            assert body.get("attendees")
            return {
                "ok": True,
                "status": 201,
                "json": {"id": "ev-1", "webLink": "https://outlook.office365.com/x", "attendees": body.get("attendees")},
            }
        return {"ok": False, "status": 500, "error": "unexpected"}

    with mock.patch.object(mcal, "_graph", side_effect=fake_graph):
        result = mcal.create_teams_event(
            token=token,
            mailbox_upn="ABDULAZIZALMULLA@wathefni.onmicrosoft.com",
            summary="Interview",
            start=datetime(2026, 8, 1, 10, 0, tzinfo=timezone.utc),
            end=datetime(2026, 8, 1, 10, 30, tzinfo=timezone.utc),
            timezone_name="Asia/Kuwait",
            attendees=["candidate@example.com"],
        )
    assert result["ok"] is True
    assert result["meet_link"].startswith("https://teams.microsoft.com/")
    assert result["event_id"] == "ev-1"
    assert result["online_meeting_id"] == "om-1"
    assert result["linked"] is True
    assert calls[0][0] == "POST" and calls[0][1].endswith("/onlineMeetings")
    assert calls[1][0] == "POST" and calls[1][1].endswith("/events")


def test_update_keeps_same_event_id_and_does_not_recreate_meeting_first():
    calls = []

    def fake_graph(method, path, token, body=None):
        calls.append((method, path, body))
        if method == "PATCH" and "/events/" in path:
            return {"ok": True, "status": 200, "json": {"id": "ev-1"}}
        if method == "PATCH" and "/onlineMeetings/" in path:
            assert "dcb6b7dd-8509-4a20-8069-ec0de9445dd7" in path
            return {"ok": True, "status": 200, "json": {"id": "om-1"}}
        return {"ok": False, "status": 500}

    with mock.patch.object(mcal, "_graph", side_effect=fake_graph):
        result = mcal.update_teams_event(
            token="t",
            mailbox_upn="a@wathefni.onmicrosoft.com",
            event_id="ev-1",
            summary="Rescheduled",
            start=datetime(2026, 8, 1, 11, 0, tzinfo=timezone.utc),
            end=datetime(2026, 8, 1, 11, 30, tzinfo=timezone.utc),
            meet_link="https://teams.microsoft.com/l/meetup-join/abc",
            online_meeting_id="om-1",
        )
    assert result["ok"] and result["same_event_id"] and result["event_id"] == "ev-1"
    assert not any(c[0] == "POST" for c in calls)


def test_create_fails_closed_when_online_meetings_forbidden():
    def fake_graph(method, path, token, body=None):
        if "/onlineMeetings" in path:
            return {"ok": False, "status": 403, "error": "graph_http_403", "detail": "Missing required permissions"}
        raise AssertionError("calendar must not be called when OM fails")

    with mock.patch.object(mcal, "_graph", side_effect=fake_graph):
        result = mcal.create_teams_event(
            token="t",
            mailbox_upn="ABDULAZIZALMULLA@wathefni.onmicrosoft.com",
            summary="x",
            start=datetime(2026, 8, 1, 10, 0, tzinfo=timezone.utc),
            end=datetime(2026, 8, 1, 10, 30, tzinfo=timezone.utc),
        )
    assert result["ok"] is False
    assert int(result.get("status") or 0) == 403


if __name__ == "__main__":
    test_create_teams_event_uses_online_meetings_then_calendar()
    test_update_keeps_same_event_id_and_does_not_recreate_meeting_first()
    test_create_fails_closed_when_online_meetings_forbidden()
    print("test_interview_microsoft_calendar PASS")
