#!/usr/bin/env python3
"""Smoke tests for attendance guardrails and deterministic routing."""

from datetime import date, datetime, time

import app


def assert_true(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def main() -> None:
    hr_req = app.WhatsAppTurnRequest(
        account_id="default",
        conversation_id="smoke-attendance",
        sender_phone="96599338566",
        sender_role="hr_admin",
        raw_text="yes do it",
    )
    employee = {
        "employee_key": "emp-fouad",
        "name": "Fouad Burhamad",
        "phone": "96550000000",
        "company_code": "WATHEFNI",
    }
    pending_action = app.pending_operation_direct_action(
        hr_req,
        {
            "operation_id": "00000000-0000-0000-0000-000000000010",
            "operation_type": "attendance_missing_shift",
            "action_type": "mark_attendance_absent",
            "payload": {
                "action": {
                    "action_type": "mark_attendance_absent",
                    "subject_name": "Fouad Burhamad",
                    "date": "2026-05-11",
                },
                "result": {"employee": employee, "attendance_date": "2026-05-11"},
            },
        },
    )
    assert_true(bool(pending_action), "approval must resolve through pending attendance operation")
    assert_true(pending_action["action_type"] == "mark_attendance_absent", "pending operation must preserve attendance action")
    assert_true(bool(pending_action.get("allow_without_shift")), "missing-shift approval must set allow_without_shift")
    assert_true(pending_action["subject_name"] == "Fouad Burhamad", "pending operation must preserve employee")

    no_context = app.infer_attendance_action("mark him absent today")
    assert_true(no_context is None, "pronoun-only attendance mutation must not become a direct action")

    listed = app.infer_attendance_action("who is late today?")
    assert_true(bool(listed), "attendance question must route deterministically")
    assert_true(listed["action_type"] == "list_attendance", "late question must become list_attendance")

    self_req = app.WhatsAppTurnRequest(
        account_id="default",
        conversation_id="smoke-attendance-employee",
        sender_phone="96550000000",
        sender_role="employee",
        raw_text="I'm here",
    )
    check_in = app.infer_attendance_action("I'm here", request=self_req)
    assert_true(bool(check_in), "employee check-in phrase must route")
    assert_true(check_in["action_type"] == "check_in_employee", "employee phrase must become check_in_employee")
    assert_true(app.digits(check_in["subject_phone"]) == "96550000000", "employee self check-in must bind sender phone")

    shift = {"shift_date": date(2026, 5, 11), "start_time": time(9, 0)}
    late_at = datetime(2026, 5, 11, 9, 14, tzinfo=app.KUWAIT_TZ)
    assert_true(app.attendance_minutes_late(late_at, shift) == 14, "late minutes must be deterministic")

    print("attendance guardrail smoke tests passed")


if __name__ == "__main__":
    main()
