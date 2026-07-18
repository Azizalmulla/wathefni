#!/usr/bin/env python3
"""Smoke tests for leave/time-off guardrails and deterministic routing."""

from datetime import date

import app


def assert_true(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def main() -> None:
    hr_req = app.WhatsAppTurnRequest(
        account_id="default",
        conversation_id="smoke-leave",
        sender_phone="96599338566",
        sender_role="hr_admin",
        raw_text="yes approve it",
    )
    leave = {
        "leave_id": "00000000-0000-0000-0000-000000000020",
        "employee_key": "emp-fouad",
        "employee_name": "Fouad Burhamad",
        "employee_phone": "96550000000",
        "start_date": "2026-05-11",
        "end_date": "2026-05-11",
        "status": "requested",
    }
    pending_action = app.pending_operation_direct_action(
        hr_req,
        {
            "operation_id": "00000000-0000-0000-0000-000000000021",
            "operation_type": "leave_shift_conflict",
            "action_type": "approve_leave_request",
            "payload": {
                "action": {"action_type": "approve_leave_request", "leave_id": leave["leave_id"]},
                "result": {"leave": leave, "shift_conflicts": [{"shift_id": "shift-1"}]},
            },
        },
    )
    assert_true(bool(pending_action), "approval must resolve through pending leave operation")
    assert_true(pending_action["action_type"] == "approve_leave_request", "pending operation must approve leave")
    assert_true(bool(pending_action.get("allow_shift_conflicts")), "shift-conflict approval must set allow_shift_conflicts")
    assert_true(pending_action["leave_id"] == leave["leave_id"], "pending operation must preserve leave id")

    no_context = app.infer_leave_action("approve it")
    assert_true(no_context is None, "vague leave approval without pending state must not become a direct action")

    listed = app.infer_leave_action("who is off tomorrow?")
    assert_true(bool(listed), "leave question must route deterministically")
    assert_true(listed["action_type"] == "list_leave_requests", "off question must become list_leave_requests")

    self_req = app.WhatsAppTurnRequest(
        account_id="default",
        conversation_id="smoke-leave-employee",
        sender_phone="96550000000",
        sender_role="employee",
        raw_text="I need sick leave tomorrow",
    )
    self_leave = app.infer_leave_action("I need sick leave tomorrow", request=self_req)
    assert_true(bool(self_leave), "employee leave phrase must route")
    assert_true(self_leave["action_type"] == "request_leave", "employee phrase must become request_leave")
    assert_true(app.digits(self_leave["subject_phone"]) == "96550000000", "employee self leave must bind sender phone")
    assert_true(self_leave["leave_type"] == "sick", "sick leave must be typed deterministically")

    original_today = app.kuwait_today
    try:
        app.kuwait_today = lambda: date(2026, 5, 11)
        relative_window = app.shift_query_window({
            "prompt_text": "Who is off tomorrow?",
            "date": "2026-05-11",
        })
        assert_true(relative_window == (date(2026, 5, 12), date(2026, 5, 12)), "relative date words must override LLM-provided stale dates")
    finally:
        app.kuwait_today = original_today

    print("leave guardrail smoke tests passed")


if __name__ == "__main__":
    main()
