"""Calm error contract — calendar module (interaction assurance P2 wave)."""

from __future__ import annotations

from calendar_store import CalendarError


def test_event_not_found_has_calm_message_distinct_from_code():
    err = CalendarError("event_not_found", http_status=404)
    envelope = err.envelope()
    assert envelope["error"] == "event_not_found"
    assert envelope["message"]
    assert envelope["message"] != envelope["error"]
    assert " " in envelope["message"]


def test_explicit_message_preserved():
    err = CalendarError("permission_denied", message="Not allowed to edit this event.", http_status=403)
    assert err.envelope()["message"] == "Not allowed to edit this event."
