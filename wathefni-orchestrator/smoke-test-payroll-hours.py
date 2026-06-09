#!/usr/bin/env python3
"""Smoke tests for payroll-hours routing and deterministic calculations."""

from datetime import date, datetime, time

import app


def assert_true(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def main() -> None:
    action = app.infer_payroll_action("show payroll hours this week")
    assert_true(bool(action), "payroll-hours question must route deterministically")
    assert_true(action["action_type"] == "list_payroll_hours", "payroll question must become list_payroll_hours")

    direct = app.infer_direct_action("How many hours did Fouad work today?")
    assert_true(bool(direct), "worked-hours question must route as a direct action")
    assert_true(direct["action_type"] == "list_payroll_hours", "worked-hours question must become list_payroll_hours")

    original_today = app.kuwait_today
    try:
        app.kuwait_today = lambda: date(2026, 5, 11)
        start, end = app.payroll_period_from_action({"prompt_text": "payroll hours this week"})
        assert_true((start, end) == (date(2026, 5, 11), date(2026, 5, 17)), "this week must use deterministic Kuwait dates")

        start, end = app.payroll_period_from_action({"prompt_text": "payroll hours this month"})
        assert_true((start, end) == (date(2026, 5, 1), date(2026, 5, 31)), "this month must use month bounds")
    finally:
        app.kuwait_today = original_today

    assert_true(app.minutes_between_times(time(9, 0), time(17, 0)) == 480, "scheduled minutes must calculate from shift times")
    assert_true(
        app.minutes_between_datetimes(
            datetime.fromisoformat("2026-05-11T09:00:00+03:00"),
            datetime.fromisoformat("2026-05-11T17:30:00+03:00"),
        )
        == 510,
        "worked minutes must calculate from check-in/out timestamps",
    )

    reply = app.format_payroll_hours_reply(
        {
            "ok": True,
            "start_date": "2026-05-11",
            "end_date": "2026-05-11",
            "summaries": [
                {
                    "employee_name": "Fouad Burhamad",
                    "scheduled_minutes": 480,
                    "worked_minutes": 510,
                    "approved_leave_minutes": 0,
                    "absent_minutes": 0,
                    "late_minutes": 5,
                    "early_leave_minutes": 0,
                    "overtime_minutes": 30,
                    "payroll_status": "Review exceptions",
                }
            ],
            "sheet_sync": {"ok": True},
        }
    )
    assert_true("Fouad Burhamad" in reply, "payroll reply must include employee name")
    assert_true("worked 8.50h" in reply, "payroll reply must include worked hours")
    assert_true("overtime 0.50h" in reply, "payroll reply must include overtime hours")
    assert_true("Payroll Hours sheet updated" in reply, "payroll reply must mention sheet sync when successful")

    review_action = app.infer_direct_action("Prepare timesheets this week")
    assert_true(bool(review_action), "timesheet review request must route")
    assert_true(review_action["action_type"] == "create_timesheet_review", "review request must create draft timesheets")

    unsafe_approval = app.infer_direct_action("approve timesheets")
    assert_true(bool(unsafe_approval), "vague timesheet approval must route to a clarification action")
    assert_true(unsafe_approval["action_type"] == "approve_timesheet", "vague approval must still use the timesheet approval backend")
    assert_true(not unsafe_approval.get("start_date") and not unsafe_approval.get("end_date"), "vague direct approval must not invent a period")
    unsafe_planner_approval = app.normalize_planner_plan(
        "Approve timesheets",
        {
            "tool": "approve_timesheet",
            "args": {"start_date": "2026-05-11", "end_date": "2026-05-17"},
            "confidence": 0.9,
            "reason": "test inferred period",
        },
    )
    assert_true(bool(unsafe_planner_approval), "vague planner approval must route to clarification")
    assert_true(unsafe_planner_approval["action_type"] == "approve_timesheet", "planner approval must preserve action type")
    assert_true(not unsafe_planner_approval.get("start_date") and not unsafe_planner_approval.get("end_date"), "planner-inferred period must be stripped from vague timesheet approval")

    approval = app.infer_direct_action("approve timesheets this week")
    assert_true(bool(approval), "explicit-period timesheet approval must route")
    assert_true(approval["action_type"] == "approve_timesheet", "explicit approval must become approve_timesheet")

    req = app.WhatsAppTurnRequest(
        account_id="default",
        conversation_id="smoke-timesheet",
        sender_phone="96599338566",
        sender_role="hr_admin",
        raw_text="yes",
    )
    pending_action = app.pending_operation_direct_action(
        req,
        {
            "operation_id": "00000000-0000-0000-0000-000000000030",
            "operation_type": "timesheet_review",
            "action_type": "create_timesheet_review",
            "payload": {
                "result": {
                    "start_date": "2026-05-11",
                    "end_date": "2026-05-17",
                    "timesheets": [
                        {
                            "timesheet_id": "00000000-0000-0000-0000-000000000031",
                            "employee_name": "Fouad Burhamad",
                            "employee_phone": "96550000000",
                        }
                    ],
                }
            },
        },
    )
    assert_true(bool(pending_action), "scoped yes must route through pending timesheet operation")
    assert_true(pending_action["action_type"] == "approve_timesheet", "scoped yes must approve the selected timesheet")
    assert_true(pending_action["timesheet_id"].endswith("31"), "pending timesheet approval must preserve timesheet id")

    review_reply = app.format_create_timesheet_review_reply(
        {
            "ok": True,
            "start_date": "2026-05-11",
            "end_date": "2026-05-17",
            "timesheets": [
                {
                    "employee_name": "Fouad Burhamad",
                    "scheduled_minutes": 480,
                    "worked_minutes": 510,
                    "approved_leave_minutes": 0,
                    "absent_minutes": 0,
                    "late_minutes": 5,
                    "early_leave_minutes": 0,
                    "overtime_minutes": 30,
                    "payroll_status": "Review exceptions",
                }
            ],
            "sheet_sync": {"ok": True},
        }
    )
    assert_true("Prepared 1 draft timesheet" in review_reply, "review reply must say draft timesheet was prepared")
    assert_true("Timesheet Approvals sheet updated" in review_reply, "review reply must mention approvals sheet sync")

    policy_action = app.infer_direct_action("Set overtime policy to review only")
    assert_true(bool(policy_action), "payroll policy update must route")
    assert_true(policy_action["action_type"] == "set_payroll_policy", "policy update must become set_payroll_policy")
    updates = app.payroll_policy_updates_from_action({"prompt_text": "Set overtime policy to review only"})
    assert_true(updates.get("overtime_policy") == "review_only", "overtime review-only policy must parse")
    updates = app.payroll_policy_updates_from_action(
        {
            "prompt_text": "Set overtime policy to paid",
            "overtime_policy": "paid",
            "absence_deduction_enabled": False,
            "default_hourly_rate_kwd": 0,
        }
    )
    assert_true(updates == {"overtime_policy": "paid"}, "policy parser must ignore LLM fields not evidenced in raw text")
    updates = app.payroll_policy_updates_from_action({"prompt_text": "Make leave unpaid and enable absence deductions"})
    assert_true(updates.get("leave_policy") == "unpaid", "unpaid leave policy must parse")
    assert_true(updates.get("absence_deduction_enabled") is True, "absence deduction flag must parse")

    # Structured path (dashboard policy editor): explicit fields apply directly,
    # without requiring NLP trigger words in prompt_text.
    structured = app.payroll_policy_updates_from_action(
        {
            "structured_policy": True,
            "employee_pay_type": "hourly",
            "leave_policy": "unpaid",
            "overtime_policy": "capped",
            "overtime_cap_hours": 2,
            "absence_deduction_enabled": False,
            "late_deduction_enabled": True,
            "default_hourly_rate_kwd": 3.5,
            "currency": "kwd",
        }
    )
    assert_true(structured.get("employee_pay_type") == "hourly", "structured pay type must apply without text triggers")
    assert_true(structured.get("leave_policy") == "unpaid", "structured leave policy must apply")
    assert_true(structured.get("overtime_policy") == "capped", "structured overtime policy must apply")
    assert_true(structured.get("overtime_cap_minutes") == 120, "structured overtime cap hours must convert to minutes")
    assert_true(structured.get("absence_deduction_enabled") is False, "structured deduction flag False must apply")
    assert_true(structured.get("late_deduction_enabled") is True, "structured deduction flag True must apply")
    assert_true(structured.get("default_hourly_rate_kwd") == 3.5, "structured hourly rate must apply")
    assert_true(structured.get("currency") == "KWD", "structured currency must normalize to upper-case")
    # The structured editor sends the marker through the dashboard whitelist, so
    # the action's declared optional fields must include structured_policy.
    import action_registry as _ar
    spec = _ar.spec_for("set_payroll_policy")
    assert_true(spec is not None, "set_payroll_policy must be registered")
    assert_true("structured_policy" in spec.optional_fields, "set_payroll_policy must accept structured_policy via dashboard")
    assert_true("employee_pay_type" in spec.optional_fields, "set_payroll_policy must accept structured policy fields via dashboard")

    preview_action = app.infer_direct_action("Preview payroll this week")
    assert_true(bool(preview_action), "payroll preview must route")
    assert_true(preview_action["action_type"] == "preview_payroll", "preview request must become preview_payroll")

    employee_req = app.WhatsAppTurnRequest(
        account_id="default",
        conversation_id="smoke-payroll-employee",
        sender_phone="96550000000",
        sender_role="employee",
        raw_text="How many hours did I work this week?",
    )
    self_payroll = app.infer_payroll_action(employee_req.raw_text, request=employee_req)
    assert_true(bool(self_payroll), "employee payroll hours question must route")
    assert_true(self_payroll["action_type"] == "list_payroll_hours", "employee payroll question must list payroll hours")
    assert_true(app.digits(self_payroll["subject_phone"]) == "96550000000", "employee payroll must bind sender phone")

    self_timesheet = app.infer_timesheet_action("What is my timesheet status this week?", request=employee_req)
    assert_true(bool(self_timesheet), "employee timesheet status question must route")
    assert_true(self_timesheet["action_type"] == "list_timesheets", "employee timesheet status must list timesheets")
    assert_true(app.digits(self_timesheet["subject_phone"]) == "96550000000", "employee timesheet must bind sender phone")
    assert_true(app.is_employee_payroll_command("what is my salary?"), "employee salary question must hit payroll boundary handler")

    original_find_employee_by_phone = app.find_employee_by_phone
    original_company_has_module = app.company_has_module
    original_list_payroll_hours = app.list_payroll_hours
    original_list_shifts = app.list_shifts
    try:
        app.find_employee_by_phone = lambda phone, **_: {"employee_key": "emp-self", "phone": app.digits(phone), "company_code": "WATHEFNI", "name": "Self Employee"}
        app.company_has_module = lambda company_code, module_key: True
        app.list_payroll_hours = lambda action, *, company_code, sync_sheet=True: {
            "ok": True,
            "start_date": "2026-05-11",
            "end_date": "2026-05-17",
            "summaries": [{"worked_minutes": 60, "scheduled_minutes": 120, "payroll_status": "Ready"}],
            "sheet_sync": {"ok": True, "skipped": True, "reason": "employee_self_service_read"},
        }
        app.list_shifts = lambda action, *, company_code: (_ for _ in ()).throw(AssertionError("payroll hours should not route to shift status"))
        routed = app.handle_non_hr_conversational_turn(employee_req)
        assert_true(bool(routed), "employee payroll self-service must produce authoritative response")
        assert_true(routed["handler_key"] == "employee_payroll", "hours wording must route to payroll before shift status")
    finally:
        app.find_employee_by_phone = original_find_employee_by_phone
        app.company_has_module = original_company_has_module
        app.list_payroll_hours = original_list_payroll_hours
        app.list_shifts = original_list_shifts

    policy = app.clean_payroll_policy(
        {
            "employee_pay_type": "hourly",
            "leave_policy": "paid",
            "overtime_policy": "review_only",
            "absence_deduction_enabled": True,
            "late_deduction_enabled": True,
            "default_hourly_rate_kwd": 2.5,
        }
    )
    preview = app.payroll_preview_from_timesheet(
        {
            "timesheet_id": "ts-1",
            "employee_name": "Fouad Burhamad",
            "employee_phone": "96550000000",
            "period_start": "2026-05-11",
            "period_end": "2026-05-17",
            "worked_minutes": 480,
            "approved_leave_minutes": 60,
            "absent_minutes": 120,
            "late_minutes": 15,
            "early_leave_minutes": 0,
            "overtime_minutes": 30,
        },
        policy,
    )
    assert_true(preview["payable_minutes"] == 405, "preview must apply paid leave and enabled deductions")
    assert_true(preview["estimated_amount_kwd"] == 16.875, "hourly preview estimate must use configured rate")
    assert_true("overtime_review" in preview["policy_flags"], "review-only overtime must stay a review flag")

    preview_reply = app.format_preview_payroll_reply(
        {
            "ok": True,
            "start_date": "2026-05-11",
            "end_date": "2026-05-17",
            "preview_rows": [preview],
            "sheet_sync": {"ok": True},
        }
    )
    assert_true("Payroll Preview sheet updated" in preview_reply, "preview reply must mention preview sheet sync")
    assert_true("No payment has been processed" in preview_reply, "preview reply must preserve no-payment boundary")

    employee_hours_reply = app.format_payroll_hours_reply(
        {
            "ok": True,
            "start_date": "2026-05-11",
            "end_date": "2026-05-17",
            "summaries": [preview],
            "sheet_sync": {"ok": True},
        },
        employee_view=True,
    )
    assert_true(employee_hours_reply.startswith("Your payroll hours"), "employee payroll reply must be self-view")
    assert_true("Fouad Burhamad" not in employee_hours_reply, "employee payroll reply must not expose names")
    assert_true("Payroll Hours sheet updated" not in employee_hours_reply, "employee payroll reply must not mention HR dashboard sync")

    employee_timesheet_reply = app.format_list_timesheets_reply(
        {
            "ok": True,
            "start_date": "2026-05-11",
            "end_date": "2026-05-17",
            "timesheets": [
                {
                    "employee_name": "Fouad Burhamad",
                    "status": "approved",
                    "worked_minutes": 480,
                    "scheduled_minutes": 480,
                    "approved_leave_minutes": 0,
                    "absent_minutes": 0,
                    "late_minutes": 0,
                    "early_leave_minutes": 0,
                    "overtime_minutes": 0,
                    "payroll_status": "Ready",
                }
            ],
        },
        employee_view=True,
    )
    assert_true(employee_timesheet_reply.startswith("Your timesheets"), "employee timesheet reply must be self-view")
    assert_true("Fouad Burhamad" not in employee_timesheet_reply, "employee timesheet reply must not expose names")

    export_action = app.infer_direct_action("Export payroll this week")
    assert_true(bool(export_action), "payroll export must route")
    assert_true(export_action["action_type"] == "export_payroll", "export request must become export_payroll")

    vague_export = app.infer_direct_action("Export payroll")
    assert_true(bool(vague_export), "vague payroll export must route to clarification")
    assert_true(vague_export["action_type"] == "export_payroll", "vague export must still use export backend")
    assert_true(not vague_export.get("start_date") and not vague_export.get("end_date"), "vague export must not invent a period")

    unsafe_planner_export = app.normalize_planner_plan(
        "Export payroll",
        {
            "tool": "export_payroll",
            "args": {"start_date": "2026-05-11", "end_date": "2026-05-17"},
            "confidence": 0.9,
            "reason": "test inferred period",
        },
    )
    assert_true(bool(unsafe_planner_export), "vague planner export must route to clarification")
    assert_true(unsafe_planner_export["action_type"] == "export_payroll", "planner export must preserve action type")
    assert_true(not unsafe_planner_export.get("start_date") and not unsafe_planner_export.get("end_date"), "planner-inferred period must be stripped from vague export")

    totals = app.payroll_preview_totals([preview])
    assert_true(totals["row_count"] == 1, "export totals must include row count")
    assert_true(totals["payable_minutes"] == 405, "export totals must preserve payable minutes")
    assert_true(totals["payment_processing"] == "disabled", "export totals must preserve no-payment boundary")

    export_reply = app.format_export_payroll_reply(
        {
            "ok": True,
            "export_id": "00000000-0000-0000-0000-000000000099",
            "start_date": "2026-05-11",
            "end_date": "2026-05-17",
            "row_count": 1,
            "totals": totals,
            "sheet_sync": {"ok": True},
        }
    )
    assert_true("Payroll export locked" in export_reply, "export reply must say the export is locked")
    assert_true("Payroll Export sheet updated" in export_reply, "export reply must mention export sheet sync")
    assert_true("No payment has been processed" in export_reply, "export reply must preserve no-payment boundary")
    assert_true("no bank file was created" in export_reply, "export reply must preserve no-bank-file boundary")

    smoke_req = app.WhatsAppTurnRequest(
        account_id="default",
        conversation_id="smoke-payroll-export-guard",
        sender_phone="96599338566",
        sender_role="hr_admin",
        raw_text="Export payroll",
        metadata={"smoke": True},
    )
    assert_true(app.refresh_hr_conversation_link_from_inbound(smoke_req)["reason"] == "smoke_turn", "smoke HR turns must not overwrite conversation links")

    original_company_branch_rows = app.company_branch_rows
    original_manager_scope_context = app.manager_scope_context
    try:
        app.company_branch_rows = lambda company_code: [
            {
                "company_code": "WATHEFNI",
                "branch_key": "branch_salmiya",
                "branch_name": "Salmiya",
                "aliases": ["salmiya branch"],
            },
            {
                "company_code": "WATHEFNI",
                "branch_key": "branch_avenues",
                "branch_name": "Avenues",
                "aliases": [],
            },
        ]
        branch = app.branch_from_action({"prompt_text": "Who is working in Salmiya today?"}, "WATHEFNI")
        assert_true(bool(branch), "branch-aware routing must identify branch names in natural text")
        assert_true(branch["branch_key"] == "branch_salmiya", "branch-aware routing must return the matching branch key")

        app.manager_scope_context = lambda manager_phone, company_code: {
            "restricted": True,
            "company_code": "WATHEFNI",
            "manager_phone": "96511111111",
            "branch_keys": ["branch_salmiya"],
            "team_keys": [],
        }
        scoped = app.org_scope_for_action(
            {"viewer_phone": "96511111111", "prompt_text": "Who is working in Salmiya today?"},
            "WATHEFNI",
        )
        assert_true(scoped.get("restricted") is True, "manager action must remain scoped")
        assert_true(scoped.get("branch_keys") == ["branch_salmiya"], "manager scope must intersect with requested branch")

        blocked = app.org_scope_for_action(
            {"viewer_phone": "96511111111", "prompt_text": "Who is working in Avenues today?"},
            "WATHEFNI",
        )
        assert_true(blocked.get("blocked") is True, "manager must be blocked from requesting an outside branch")
        assert_true(
            app.format_list_shifts_reply({"ok": False, "error": "employee_outside_manager_scope"}) == "That employee is outside your manager scope.",
            "manager scope errors must not leak outside employee details",
        )

        clause, params = app.employee_scope_sql("s", scoped)
        assert_true("employee_org_assignments" in clause, "scoped SQL must join through employee org assignments")
        assert_true(params[2] == ["branch_salmiya"], "scoped SQL must bind the allowed branch keys")
    finally:
        app.company_branch_rows = original_company_branch_rows
        app.manager_scope_context = original_manager_scope_context

    availability_action = app.infer_direct_action("Fouad is unavailable tomorrow")
    assert_true(bool(availability_action), "availability request must route deterministically")
    assert_true(availability_action["action_type"] == "request_availability", "unavailable wording must create availability request")
    assert_true(availability_action["availability_type"] == "unavailable", "unavailable wording must preserve availability type")

    swap_approval = app.infer_direct_action("Approve Fouad's shift swap tomorrow")
    assert_true(bool(swap_approval), "shift swap approval must route")
    assert_true(swap_approval["action_type"] == "approve_shift_swap", "approve shift swap must be a decision, not a new request")

    swap_list = app.infer_direct_action("Show pending shift swaps")
    assert_true(bool(swap_list), "shift swap list must route")
    assert_true(swap_list["action_type"] == "list_shift_swaps", "pending swap question must list shift swaps")

    employee_availability_req = app.WhatsAppTurnRequest(
        account_id="default",
        conversation_id="smoke-availability-employee",
        sender_phone="96550000000",
        sender_role="employee",
        raw_text="I'm not available tomorrow",
    )
    original_find_employee_by_phone = app.find_employee_by_phone
    original_company_has_module = app.company_has_module
    original_request_availability = app.request_availability
    original_list_shifts = app.list_shifts
    try:
        app.find_employee_by_phone = lambda phone, **_: {"employee_key": "emp-self", "phone": app.digits(phone), "company_code": "WATHEFNI", "name": "Self Employee"}
        app.company_has_module = lambda company_code, module_key: True
        app.request_availability = lambda action, *, company_code, created_by_phone, account_id=None: {
            "ok": True,
            "availability": {
                "availability_id": "av-1",
                "employee_name": "Self Employee",
                "start_date": "2026-05-12",
                "end_date": "2026-05-12",
                "availability_type": "unavailable",
                "status": "requested",
            },
            "employee": {"name": "Self Employee", "phone": "96550000000"},
        }
        app.list_shifts = lambda action, *, company_code: (_ for _ in ()).throw(AssertionError("availability must not fall back to loose shift objection"))
        routed = app.handle_non_hr_conversational_turn(employee_availability_req)
        assert_true(bool(routed), "employee availability self-service must produce authoritative response")
        assert_true(routed["intent"] == "request_availability", "employee availability must bind to structured availability flow")
        assert_true("availability" in routed["reply"].lower(), "employee availability reply must mention availability")
    finally:
        app.find_employee_by_phone = original_find_employee_by_phone
        app.company_has_module = original_company_has_module
        app.request_availability = original_request_availability
        app.list_shifts = original_list_shifts

    analytics_action = app.infer_direct_action("Who is late the most this month?")
    assert_true(bool(analytics_action), "analytics late-most question must route")
    assert_true(analytics_action["action_type"] == "workforce_analytics", "late-most question must use analytics backend")
    assert_true(analytics_action["metric"] == "late", "late-most question must preserve late metric")

    branch_analytics = app.infer_direct_action("Which branch has the most absences?")
    assert_true(bool(branch_analytics), "branch absence analytics must route")
    assert_true(branch_analytics["action_type"] == "workforce_analytics", "branch analytics must use analytics backend")

    review_analytics = app.infer_direct_action("What should I review today?")
    assert_true(bool(review_analytics), "review priority analytics must route")
    assert_true(review_analytics["metric"] == "review", "review priority analytics must preserve review metric")

    planner_analytics = app.normalize_planner_plan(
        "Show overtime risk this week",
        {
            "tool": "workforce_analytics",
            "args": {"metric": "overtime", "start_date": "2026-05-11", "end_date": "2026-05-17"},
            "confidence": 0.9,
            "reason": "test analytics",
        },
    )
    assert_true(bool(planner_analytics), "planner analytics tool call must normalize")
    assert_true(planner_analytics["action_type"] == "workforce_analytics", "planner analytics must preserve action type")

    analytics_reply = app.format_workforce_analytics_reply(
        {
            "ok": True,
            "start_date": "2026-05-01",
            "end_date": "2026-05-31",
            "metric": "late",
            "counts": {
                "scheduled_shifts": 10,
                "absent_records": 1,
                "late_records": 2,
                "pending_leave": 1,
                "pending_availability": 1,
                "pending_swaps": 1,
            },
            "insights": [
                {"metric": "Top lateness", "subject": "Fouad Burhamad", "value": 25, "detail": "2 attendance records."},
                {"metric": "Branch absences", "subject": "Salmiya", "value": 1, "detail": "Absence records by primary branch."},
            ],
            "sheet_sync": {"ok": True},
        }
    )
    assert_true("Workforce analytics" in analytics_reply, "analytics reply must have analytics title")
    assert_true("Fouad Burhamad" in analytics_reply, "analytics reply must include selected insight subject")
    assert_true("Analytics sheet updated" in analytics_reply, "analytics reply must mention sheet sync")
    assert_true(
        app.format_workforce_analytics_reply({"ok": False, "error": "employee_outside_manager_scope"})
        == "That analytics view is outside your manager scope.",
        "analytics scope errors must not leak details",
    )

    print("payroll-hours smoke tests passed")


if __name__ == "__main__":
    main()
