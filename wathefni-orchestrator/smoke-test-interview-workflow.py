from __future__ import annotations

import sys
import types

if "psycopg2" not in sys.modules:
    psycopg2 = types.ModuleType("psycopg2")
    psycopg2.connect = lambda *args, **kwargs: None  # type: ignore[attr-defined]
    extras = types.ModuleType("psycopg2.extras")
    extras.RealDictCursor = object
    extras.Json = lambda value: value
    sys.modules["psycopg2"] = psycopg2
    sys.modules["psycopg2.extras"] = extras

import app


def assert_true(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def main() -> None:
    assert_true(app.normalize_interview_status("no-show") == "no_show", "no-show should normalize")
    assert_true(app.normalize_interview_status("cancelled") == "cancelled", "cancelled should be allowed")
    assert_true(app.normalize_interview_feedback_status("feedback complete") == "feedback_complete", "feedback status should normalize")

    start = app.parse_datetime_or_none("2026-05-18T21:00:00+03:00")
    assert_true(start is not None and start.isoformat().startswith("2026-05-18T21:00:00"), "ISO interview time should parse")

    calendar_payload = {
        "event": {
            "id": "event-123",
            "conferenceData": {
                "entryPoints": [
                    {"entryPointType": "video", "uri": "https://meet.google.com/abc-defg-hij"},
                ],
            },
        },
    }
    assert_true(app.interview_calendar_event_id(calendar_payload) == "event-123", "calendar event id should be extracted")
    assert_true(
        app.interview_meet_link_from_calendar(calendar_payload) == "https://meet.google.com/abc-defg-hij",
        "Google Meet link should be extracted",
    )
    invite_message = app.compose_interview_invite_message(
        {"candidate_name": "Hamad Almulla", "position_title": "Accounting Excel"},
        {
            "candidate_name": "Hamad Almulla",
            "position_title": "Accounting Excel",
            "scheduled_start": "2026-05-18T21:00:00+03:00",
            "meet_link": "https://meet.google.com/abc-defg-hij",
        },
    )
    assert_true("Google Meet: https://meet.google.com/abc-defg-hij" in invite_message, "candidate invite must include actual Meet link")
    calendar_only_message = app.compose_interview_invite_message(
        {"candidate_name": "Hamad Almulla", "position_title": "Accounting Excel"},
        {
            "candidate_name": "Hamad Almulla",
            "position_title": "Accounting Excel",
            "scheduled_start": "2026-05-18T21:00:00+03:00",
            "calendar_event_id": "event-123",
            "calendar_invite_sent": True,
        },
    )
    assert_true("calendar invite contains the joining" in calendar_only_message.lower(), "candidate invite without Meet link must point to Calendar invite details")

    summary = app.deterministic_interview_summary("Strong communication. Needs Excel follow-up.")
    assert_true(summary["decision_policy"].lower().find("hr remains") >= 0, "summary must keep HR as decision-maker")
    print("interview workflow smoke passed")


if __name__ == "__main__":
    main()
