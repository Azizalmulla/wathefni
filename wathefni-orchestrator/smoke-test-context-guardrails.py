#!/usr/bin/env python3
"""Smoke tests for HR operational context guardrails."""

from pathlib import Path
import tempfile

import app


def assert_true(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def copy_request(request, **updates):
    if hasattr(request, "model_copy"):
        return request.model_copy(update=updates)
    return request.copy(update=updates)


def main() -> None:
    app.call_operational_wording_llm = lambda *, user_text, facts, turn_id=None, timeout=8: facts.get("backend_reply")
    repo_root = Path(__file__).resolve().parents[1]
    channel_path = repo_root / "plugins" / "octopus-channel" / "octopus-channel.ts"
    if channel_path.exists():
        channel_source = channel_path.read_text(encoding="utf-8")
        assert_true("HR_ORCHESTRATOR_SAFE_FALLBACK_REPLY" in channel_source, "Octopus HR gate must define a local safe fallback")
        assert_true("hr orchestrator fail-closed" in channel_source, "Octopus HR gate must log fail-closed behavior")
        assert_true("senderRole === \"hr_admin\"" in channel_source and "return;" in channel_source, "HR admin orchestrator failures must not fall through to OpenClaw dispatch")
    original_workspace = app.WORKSPACE
    try:
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            (workspace / "IDENTITY.md").write_text("# Identity\nWathefni assistant identity.\n", encoding="utf-8")
            (workspace / "SOUL.md").write_text("# Soul\nWarm, grounded, Kuwaiti HR tone.\n", encoding="utf-8")
            (workspace / "SKILL.md").write_text("# Skills\nUse backend tools only when grounded.\n", encoding="utf-8")
            (workspace / "TOOLS.md").write_text("# Tools\nActionResult truth wins.\n", encoding="utf-8")
            app.WORKSPACE = workspace
            prompt_status = app.openclaw_prompt_debug_status()
            assert_true(prompt_status["loaded_identity"] is True, "OpenClaw identity doc must load from runtime workspace")
            assert_true(prompt_status["loaded_soul"] is True, "OpenClaw soul doc must load from runtime workspace")
            assert_true(prompt_status["loaded_skills"] is True, "OpenClaw skill doc must load from runtime workspace")
            assert_true(prompt_status["loaded_tools"] is True, "OpenClaw tools doc must load from runtime workspace")
            assert_true(prompt_status["source_paths"]["skills"].endswith("SKILL.md"), "skills loader must support singular SKILL.md")
            assert_true(bool(prompt_status["prompt_version_hash"]), "OpenClaw prompt context must expose a version hash")
            assert_true(prompt_status["injection"]["tool_agent"] is True, "tool-agent prompt must receive OpenClaw docs")
            assert_true(prompt_status["injection"]["planner"] is True, "planner prompt must receive OpenClaw docs")
            assert_true(prompt_status["injection"]["style_layer"] is True, "style layer prompt must receive OpenClaw docs")
            augmented = app.openclaw_augmented_system_prompt(app.PLANNER_BASE_SYSTEM, prompt_name="planner")
            assert_true("OPENCLAW_RUNTIME_CONTEXT:planner" in augmented, "planner system prompt must include OpenClaw context marker")
    finally:
        app.WORKSPACE = original_workspace

    pronoun_text = "online meeting tomorrow 3pm and send him the google meets link"
    hallucinated_plan = {
        "tool": "send_custom_employee_message",
        "args": {
            "subject_name": "mohammad alqattan",
            "message_text": "Your online meeting is tomorrow at 3:00 PM. Google Meet link: [please insert link]",
        },
        "confidence": 0.9,
        "reason": "test hallucinated subject",
    }
    normalized = app.normalize_planner_plan(pronoun_text, hallucinated_plan)
    assert_true(normalized is None, "pronoun-only planner send must not accept a hallucinated subject")

    original_context = app.recent_candidate_email_context
    try:
        app.recent_candidate_email_context = lambda minutes=45, **kwargs: None
        direct = app.infer_direct_action(pronoun_text)
        assert_true(direct is None, "pronoun-only send without stored context must not become a direct action")

        selected_app = {
            "app_key": "96599338566-WATHEFNI-FULLSTACK_DEVELOPER",
            "phone": "96599338566",
            "candidate_name": "Aziz Almulla",
            "candidate_email": "azizalmulla16@gmail.com",
            "position_title": "Full Stack Developer",
            "position_code": "FULLSTACK_DEVELOPER",
            "status": "screening_complete",
        }
        app.recent_candidate_email_context = lambda minutes=45, **kwargs: {
            "selected_application": selected_app,
            "matches": [selected_app],
        }
        continuation = app.infer_candidate_email_continuation_action(pronoun_text)
        assert_true(bool(continuation), "stored candidate context must produce a continuation action")
        assert_true(continuation["action_type"] == "schedule_candidate_meeting", "meeting follow-up must route to calendar invite")
        assert_true(continuation["app_key"] == selected_app["app_key"], "continuation must preserve selected application")

        req = app.WhatsAppTurnRequest(
            account_id="default",
            conversation_id="smoke-context-guardrail",
            sender_phone="96599338566",
            sender_role="hr_admin",
            raw_text=pronoun_text,
        )
        operation_action = app.pending_operation_direct_action(
            req,
            {
                "operation_id": "00000000-0000-0000-0000-000000000001",
                "operation_type": "candidate_email_selected",
                "payload": {"selected_application": selected_app},
            },
        )
        assert_true(bool(operation_action), "pending operation context must route vague candidate follow-up")
        assert_true(operation_action["app_key"] == selected_app["app_key"], "pending operation must preserve candidate app key")
    finally:
        app.recent_candidate_email_context = original_context

    shift_req = app.WhatsAppTurnRequest(
        account_id="default",
        conversation_id="smoke-shift-context",
        sender_phone="96599338566",
        sender_role="hr_admin",
        raw_text="yes cancel and schedule this 8am to 3pm",
    )
    shift_action = app.pending_operation_direct_action(
        shift_req,
        {
            "operation_id": "00000000-0000-0000-0000-000000000002",
            "operation_type": "shift_conflict",
            "payload": {
                "source_text": "Schedule Mohammad tomorrow 8am to 3pm",
                "result": {
                    "employee": {"name": "Mohammad Alqattan", "phone": "96550000000", "employee_key": "emp-mohammad"},
                    "conflicts": [{"shift_id": "shift-1", "shift_date": "2026-05-11"}],
                    "requested_dates": ["2026-05-11"],
                },
            },
        },
    )
    assert_true(bool(shift_action), "pending shift conflict must create a replacement action")
    assert_true(shift_action["action_type"] == "replace_conflicting_shift_assignment", "shift conflict must route to atomic replacement")
    assert_true(shift_action["conflict_shift_ids"] == ["shift-1"], "replacement must preserve conflicting shift id")

    assert_true(app.resolve_employee_for_direct_action({}) is None, "empty employee action must not fall back to latest employee")
    assert_true(app.has_unsafe_outbound_placeholder("Google Meet link: [please insert link]"), "placeholder links must be blocked")
    assert_true(app.is_verification_followup_question("r u sure"), "r u sure must route as verification follow-up")
    req_a = app.WhatsAppTurnRequest(
        account_id="default",
        conversation_id="conv-1",
        sender_phone="+965 9933 8566",
        sender_role="hr_admin",
        raw_text="r u sure",
    )
    req_b = app.WhatsAppTurnRequest(
        account_id="default",
        conversation_id="conv-2",
        sender_phone="+965 9933 8566",
        sender_role="hr_admin",
        raw_text="r u sure",
    )
    assert_true(app.scoped_graph_thread_id(req_a) != app.scoped_graph_thread_id(req_b), "legacy thread id helper must be scoped by conversation")
    assert_true(app.scoped_graph_thread_id(req_a).endswith(":96599338566"), "legacy thread id helper must include normalized admin phone")
    assert_true(app.required_module_for_action("send_email") is None, "email must be a shared communication channel, not pre-hiring gated")
    assert_true(app.operational_module_for_action("send_email") == "COMMUNICATIONS", "email actions must be labeled as shared communications")
    assert_true(app.tool_enabled_for_company("send_email", "COMPANY_WITHOUT_PREHIRING"), "shared email must not require pre_hiring module")

    focus_app = {
        "app_key": "96551234567-WATHEFNI-HR_OFFICER",
        "phone": "96551234567",
        "candidate_name": "Fouad Burhamad",
        "candidate_email": "fouad@example.com",
        "position_title": "HR Officer",
        "position_code": "HR_OFFICER",
        "company_code": "WATHEFNI",
    }
    candidate_context = app.set_operational_focus({"focus": app.default_focus_context()}, app.candidate_focus_from_app(focus_app, source_action="send_assessment"))
    email_followup = app.direct_action_from_operational_context("email him", candidate_context)
    assert_true(bool(email_followup), "candidate pronoun follow-up must create a direct action from graph focus")
    assert_true(email_followup["action_type"] == "send_email", "email pronoun must route to candidate email")
    assert_true(email_followup["app_key"] == focus_app["app_key"], "email pronoun must bind to focused candidate app key")
    email_correction = app.direct_action_from_operational_context("I said email", candidate_context)
    assert_true(email_correction["action_type"] == "send_email", "email correction must route to candidate email")
    assert_true(email_correction["app_key"] == focus_app["app_key"], "email correction must bind focused candidate without asking clarification")
    first_email = app.infer_direct_action("Hala pls send foad an email for the assessment test")
    assert_true(first_email["action_type"] == "send_email", "explicit email-for-assessment request must not become assessment WhatsApp send")
    assert_true(app.infer_action_type_from_text("email him for the assessment test") == "send_email", "email keyword must outrank assessment keyword")
    email_content = app.compose_email_content(focus_app, {"prompt_text": "send Fouad an email for an assessment test reminder"})
    assert_true(email_content["subject"] == "Application Assessment Reminder", "assessment reminder email must use assessment reminder subject")
    assert_true("application assessment" in email_content["body"].lower(), "assessment reminder email body must mention the application assessment")
    retry_action = app.infer_direct_action("try again now")
    assert_true(retry_action["action_type"] == "retry_last_failed_action", "retry wording must route to structured generic retry first")
    scratch = app.turn_scratch_with_action_resolution(
        app.turn_scratch_for_request(req_a, "turn-1"),
        action=email_followup,
        intent="execute_direct_action",
    )
    assert_true(scratch["reply_text"] is None, "new turn scratch must not inherit stale reply text")
    assert_true(scratch["resolved_entities"]["candidate"]["app_key"] == focus_app["app_key"], "shared resolver must write candidate to resolved_entities")

    assessment_followup = app.bind_focus_to_action({"action_type": "send_assessment", "prompt_text": "send it to him"}, candidate_context, "send it to him")
    assert_true(assessment_followup["app_key"] == focus_app["app_key"], "assessment follow-up must bind focused candidate")
    expired_context = {
        "focus": {
            **app.default_focus_context(),
            "current_candidate": {
                **candidate_context["focus"]["current_candidate"],
                "expires_at": "2000-01-01T00:00:00+00:00",
            },
        }
    }
    assert_true(app.direct_action_from_operational_context("email him", expired_context) is None, "expired candidate focus must not be reused")

    talal_app = {
        "app_key": "96570000000-WATHEFNI-SOCIAL_MEDIA_MANAGER",
        "phone": "96570000000",
        "candidate_name": "Talal Fadhli",
        "candidate_email": "talal@example.com",
        "position_title": "Social Media Manager",
        "position_code": "SOCIAL_MEDIA_MANAGER",
        "status": "screening",
        "company_code": "WATHEFNI",
    }
    aziz_app = {
        "app_key": "96598900677-WATHEFNI-HR",
        "phone": "96598900677",
        "candidate_name": "Aziz Almulla",
        "candidate_email": "aziz@example.com",
        "position_title": "HR",
        "position_code": "HR",
        "status": "shortlisted",
        "company_code": "WATHEFNI",
    }
    original_resolve_candidate_reference = app.resolve_candidate_reference_from_text
    original_find_pending_focus = app.find_pending_action
    original_find_operation_focus = app.find_pending_operation
    original_candidate_cv_eval = app.candidate_cv_evaluation
    original_capability_planner = app.call_capability_planner
    original_latest_repairable_context = app.latest_repairable_context
    original_find_application_by_key_focus = app.find_application_by_key
    try:
        app.find_pending_action = lambda request: None
        app.find_pending_operation = lambda request: None
        def fake_capability_planner(**kwargs):
            normalized_text = app.normalize_text(kwargs.get("text"))
            if normalized_text == "compare him to azizalmulla and foad":
                return {
                    "capability": "compare_evaluate",
                    "entity_type": "candidate",
                    "operation": "compare",
                    "targets": [
                        {"ref": "him", "resolution_hint": "current_candidate", "type": "pronoun"},
                        {"ref": "azizalmulla", "type": "candidate_name"},
                        {"ref": "foad", "type": "candidate_name"},
                    ],
                    "confidence": 0.96,
                    "reason": "test structured compare targets",
                }
            if normalized_text == "pls can u compare foad aziz and talal":
                return {
                    "capability": "compare_evaluate",
                    "entity_type": "candidate",
                    "operation": "compare",
                    "targets": [
                        {"ref": "foad aziz", "type": "candidate_name"},
                        {"ref": "talal", "type": "candidate_name"},
                    ],
                    "confidence": 0.96,
                    "reason": "test merged compare target repair",
                }
            return None

        def fake_resolve_candidate_reference(text, company_code="WATHEFNI"):
            normalized = app.normalize_text(text)
            if normalized in {"talal", "6lal", "what about talal"}:
                return {"status": "resolved", "application": talal_app, "matches": [talal_app]}
            if normalized in {"azizalmulla", "aziz almulla"}:
                return {"status": "resolved", "application": aziz_app, "matches": [aziz_app]}
            if normalized in {"foad", "fouad"}:
                return {"status": "resolved", "application": focus_app, "matches": [focus_app]}
            if normalized == "aziz":
                return {"status": "ambiguous", "matches": [aziz_app, focus_app]}
            if "aziz" in normalized:
                return {"status": "ambiguous", "matches": [talal_app, focus_app]}
            return {"status": "none", "matches": []}

        app.call_capability_planner = fake_capability_planner
        app.find_application_by_key = lambda app_key: {**talal_app, "status": "hired"} if app_key == talal_app["app_key"] else original_find_application_by_key_focus(app_key)
        app.resolve_candidate_reference_from_text = fake_resolve_candidate_reference
        app.candidate_cv_evaluation = lambda action, company_code="WATHEFNI": {
            "ok": True,
            "query": action.get("query") or action.get("prompt_text"),
            "selected_application": app.candidate_lookup_match_payload(talal_app),
            "candidates": [{
                "app_key": talal_app["app_key"],
                "name": "Talal Fadhli",
                "job": "Social Media Manager",
                "stage": "screening",
                "cv_status": "received",
                "assessment_status": "missing",
                "assessment_score": "missing",
                "stored_data_score": "missing",
                "confidence": "single_candidate",
                "stored_evidence": ["CV is received"],
                "gaps": ["Assessment result is missing"],
            }],
            "recommended_next_action": "Review Talal Fadhli from the stored candidate record before making a decision.",
        }
        focus_req = app.WhatsAppTurnRequest(account_id="default", conversation_id="candidate-focus-smoke", sender_phone="96599338566", sender_role="hr_admin", raw_text="talal")
        classified_focus = app.classify({
            "request": focus_req,
            "turn_id": "00000000-0000-0000-0000-000000000101",
            "persistent_context": {"focus": app.default_focus_context()},
            "turn_scratch": app.turn_scratch_for_request(focus_req, "00000000-0000-0000-0000-000000000101"),
            "direct_action": None,
            "planner_plan": None,
            "audit": {},
        })
        assert_true(classified_focus["intent"] == "answer_candidate_focus", "candidate name alone must route to candidate focus")
        focused_context = app.set_operational_focus(classified_focus["persistent_context"], classified_focus["candidate_focus"]["focus"])
        current_candidate = focused_context["focus"]["current_candidate"]
        assert_true(current_candidate["app_key"] == talal_app["app_key"], "candidate focus turn must store current_candidate")
        eval_req = copy_request(focus_req, raw_text="is he good")
        classified_eval = app.classify({
            "request": eval_req,
            "turn_id": "turn-candidate-eval",
            "persistent_context": focused_context,
            "turn_scratch": app.turn_scratch_for_request(eval_req, "turn-candidate-eval"),
            "direct_action": None,
            "planner_plan": None,
            "audit": {},
        })
        assert_true(classified_eval["intent"] == "execute_direct_action", "candidate evaluation follow-up must execute grounded candidate evaluation")
        assert_true(classified_eval["direct_action"]["action_type"] == "candidate_cv_evaluation", "is he good must route to candidate CV evaluation")
        assert_true(classified_eval["direct_action"]["app_key"] == talal_app["app_key"], "candidate evaluation must bind current candidate")
        shortlist_req = copy_request(focus_req, raw_text="shortlist him now")
        classified_shortlist = app.classify({
            "request": shortlist_req,
            "turn_id": "turn-candidate-shortlist",
            "persistent_context": focused_context,
            "turn_scratch": app.turn_scratch_for_request(shortlist_req, "turn-candidate-shortlist"),
            "direct_action": None,
            "planner_plan": None,
            "audit": {},
        })
        assert_true(classified_shortlist["intent"] == "execute_direct_action", "shortlist pronoun must execute candidate mutation with focus")
        assert_true(classified_shortlist["direct_action"]["action_type"] == "shortlist_candidate", "shortlist him must route to shortlist_candidate")
        assert_true(classified_shortlist["direct_action"]["app_key"] == talal_app["app_key"], "shortlist him must bind current candidate")
        assert_true(classified_shortlist["direct_action"].get("capability") == "change_stage", "shortlist him should compile through change_stage capability")
        notes_req = copy_request(focus_req, raw_text="Can u add notes about him… write interesting person")
        classified_notes = app.classify({
            "request": notes_req,
            "turn_id": "turn-candidate-notes",
            "persistent_context": focused_context,
            "turn_scratch": app.turn_scratch_for_request(notes_req, "turn-candidate-notes"),
            "direct_action": None,
            "planner_plan": None,
            "audit": {},
        })
        assert_true(classified_notes["intent"] == "answer_capability_decision", "candidate notes request must route to capability decision")
        assert_true(classified_notes["capability_decision"]["proposal"]["capability"] == "update_record", "notes request must be interpreted as update_record")
        assert_true(classified_notes["capability_decision"]["validation"]["reason"] == "candidate_notes_not_whatsapp_editable_yet", "notes must be blocked as unsupported from WhatsApp")
        blocked_notes_context = {
            "source": "memory_snapshot",
            "kind": "capability_decision",
            "payload": classified_notes["capability_decision"],
        }
        app.latest_repairable_context = lambda request: blocked_notes_context
        sheets_req = copy_request(focus_req, raw_text="its in google sheets")
        classified_sheets = app.classify({
            "request": sheets_req,
            "turn_id": "turn-post-action-sheets",
            "persistent_context": focused_context,
            "turn_scratch": app.turn_scratch_for_request(sheets_req, "turn-post-action-sheets"),
            "direct_action": None,
            "planner_plan": None,
            "audit": {},
        })
        assert_true(classified_sheets["intent"] == "answer_post_action_repair", "Sheets objection must stay in post-action repair")
        assert_true("Postgres" in classified_sheets["post_action_repair"]["reply"], "Sheets objection must explain Postgres truth")
        assert_true("dashboard" in classified_sheets["post_action_repair"]["reply"].lower(), "Sheets objection must point to the dashboard as the visible record")
        hired_context = app.set_operational_focus({"focus": app.default_focus_context()}, app.candidate_focus_from_app({**talal_app, "status": "hired"}, source_action="hire_candidate"))
        hired_req = copy_request(focus_req, raw_text="huh do u not have context? we hired him already and sent him an email")
        classified_hired_objection = app.classify({
            "request": hired_req,
            "turn_id": "turn-post-action-hired",
            "persistent_context": hired_context,
            "turn_scratch": app.turn_scratch_for_request(hired_req, "turn-post-action-hired"),
            "direct_action": None,
            "planner_plan": None,
            "audit": {},
        })
        assert_true(classified_hired_objection["intent"] == "answer_post_action_repair", "past-tense hired objection must not rerun hire")
        assert_true(classified_hired_objection.get("direct_action") is None, "hired objection must clear direct hire action")
        assert_true("currently hired" in classified_hired_objection["post_action_repair"]["reply"], "hired objection must check stored status")
        why_req = copy_request(focus_req, raw_text="then why did you say this")
        classified_why_this = app.classify({
            "request": why_req,
            "turn_id": "turn-post-action-why-this",
            "persistent_context": focused_context,
            "turn_scratch": app.turn_scratch_for_request(why_req, "turn-post-action-why-this"),
            "direct_action": None,
            "planner_plan": None,
            "audit": {},
        })
        assert_true(classified_why_this["intent"] == "answer_post_action_repair", "why-this objection must stay authoritative")
        assert_true("previous turn was validated" in classified_why_this["post_action_repair"]["reply"], "why-this must explain previous route/result")
        email_req = copy_request(focus_req, raw_text="Email him for onboarding / compliance")
        classified_email = app.classify({
            "request": email_req,
            "turn_id": "turn-candidate-capability-email",
            "persistent_context": focused_context,
            "turn_scratch": app.turn_scratch_for_request(email_req, "turn-candidate-capability-email"),
            "direct_action": None,
            "planner_plan": None,
            "audit": {},
        })
        assert_true(classified_email["intent"] == "execute_direct_action", "candidate email capability must compile to direct execution")
        assert_true(classified_email["direct_action"]["action_type"] == "send_email", "send_message/email capability must compile to send_email")
        assert_true(classified_email["direct_action"]["purpose"] == "onboarding_compliance", "email capability must preserve onboarding/compliance purpose")
        compare_req = copy_request(focus_req, raw_text="compare him to azizalmulla and foad")
        classified_compare_targets = app.classify({
            "request": compare_req,
            "turn_id": "turn-candidate-capability-compare",
            "persistent_context": focused_context,
            "turn_scratch": app.turn_scratch_for_request(compare_req, "turn-candidate-capability-compare"),
            "direct_action": None,
            "planner_plan": None,
            "audit": {},
        })
        assert_true(classified_compare_targets["intent"] == "execute_direct_action", "structured compare capability must execute direct action")
        assert_true(classified_compare_targets["direct_action"]["action_type"] == "compare_candidates", "compare capability must compile to compare_candidates")
        compare_ids = set(classified_compare_targets["direct_action"]["candidate_ids"])
        assert_true(talal_app["app_key"] in compare_ids, "compare targets must include current candidate")
        assert_true(aziz_app["app_key"] in compare_ids, "compare targets must include explicit Aziz alias")
        assert_true(focus_app["app_key"] in compare_ids, "compare targets must include Foad/Fouad alias")
        merged_compare_req = copy_request(focus_req, raw_text="pls can u compare foad aziz and talal")
        classified_merged_compare = app.classify({
            "request": merged_compare_req,
            "turn_id": "turn-candidate-merged-compare",
            "persistent_context": focused_context,
            "turn_scratch": app.turn_scratch_for_request(merged_compare_req, "turn-candidate-merged-compare"),
            "direct_action": None,
            "planner_plan": None,
            "audit": {},
        })
        assert_true(classified_merged_compare["intent"] == "answer_capability_decision", "multi-name compare must not route to single candidate focus")
        assert_true(classified_merged_compare.get("candidate_focus") is None, "capability compare clarification must suppress legacy candidate focus")
        assert_true(classified_merged_compare["capability_decision"]["validation"]["reason"] == "ambiguous_compare_target", "ambiguous compare target must ask clarification")
        pending_compare_clarification = app.pending_clarification_from_capability_decision(classified_merged_compare["capability_decision"], merged_compare_req)
        assert_true(pending_compare_clarification and pending_compare_clarification["kind"] == "resolve_ambiguous_compare_target", "ambiguous compare must create pending clarification state")
        pending_compare_context = app.set_pending_clarification(focused_context, pending_compare_clarification)
        compare_hr_req = copy_request(focus_req, raw_text="hr")
        classified_compare_hr = app.classify({
            "request": compare_hr_req,
            "turn_id": "turn-candidate-merged-compare-hr",
            "persistent_context": pending_compare_context,
            "turn_scratch": app.turn_scratch_for_request(compare_hr_req, "turn-candidate-merged-compare-hr"),
            "direct_action": None,
            "planner_plan": None,
            "audit": {},
        })
        assert_true(classified_compare_hr["intent"] == "execute_direct_action", "clarification response must resume original compare action")
        assert_true(classified_compare_hr["direct_action"]["action_type"] == "compare_candidates", "HR clarification must compile compare_candidates")
        compare_hr_ids = set(classified_compare_hr["direct_action"]["candidate_ids"])
        assert_true(aziz_app["app_key"] in compare_hr_ids, "HR clarification must select Aziz HR")
        assert_true(focus_app["app_key"] in compare_hr_ids, "resumed compare must keep Foad target")
        assert_true(talal_app["app_key"] in compare_hr_ids, "resumed compare must keep Talal target")
        assert_true(classified_compare_hr["pending_clarification"] is None, "resolved clarification must be cleared")
        fallback_rank_req = copy_request(focus_req, raw_text="who is the most accomplished based on CVs")
        classified_fallback_rank = app.classify({
            "request": fallback_rank_req,
            "turn_id": "turn-capability-fallback-rank",
            "persistent_context": focused_context,
            "turn_scratch": app.turn_scratch_for_request(fallback_rank_req, "turn-capability-fallback-rank"),
            "direct_action": None,
            "planner_plan": None,
            "audit": {},
        })
        assert_true(classified_fallback_rank["intent"] == "execute_direct_action", "legacy direct action must remain fallback when capability has no proposal")
        assert_true(classified_fallback_rank["direct_action"]["action_type"] == "candidate_cv_evaluation", "candidate CV evaluation must still route via fallback")
        invalid_capability = app.validate_capability_proposal(
            email_req,
            focused_context,
            {"capability": "send_message", "entity_type": "candidate", "target_ref": "current_candidate", "channel": "fax", "confidence": 0.9},
        )
        assert_true(invalid_capability["status"] == "unsupported", "invalid capability channel must be rejected by backend validation")
        no_focus_req = copy_request(focus_req, raw_text="shortlist him")
        classified_no_focus = app.classify({
            "request": no_focus_req,
            "turn_id": "turn-candidate-no-focus",
            "persistent_context": {"focus": app.default_focus_context()},
            "turn_scratch": app.turn_scratch_for_request(no_focus_req, "turn-candidate-no-focus"),
            "direct_action": None,
            "planner_plan": None,
            "audit": {},
        })
        assert_true(classified_no_focus["intent"] == "answer_capability_decision", "shortlist pronoun without focus must ask through capability validation")
        assert_true("which candidate" in classified_no_focus["capability_decision"]["reply"].lower(), "missing candidate target must ask which candidate")
        ambiguous_req = copy_request(focus_req, raw_text="aziz")
        classified_ambiguous = app.classify({
            "request": ambiguous_req,
            "turn_id": "turn-candidate-ambiguous",
            "persistent_context": {"focus": app.default_focus_context()},
            "turn_scratch": app.turn_scratch_for_request(ambiguous_req, "turn-candidate-ambiguous"),
            "direct_action": None,
            "planner_plan": None,
            "audit": {},
        })
        assert_true(classified_ambiguous["intent"] == "answer_candidate_focus", "ambiguous candidate name must stay authoritative")
        assert_true(classified_ambiguous["candidate_focus"]["status"] == "ambiguous", "ambiguous candidate name must ask clarification")
    finally:
        app.resolve_candidate_reference_from_text = original_resolve_candidate_reference
        app.find_pending_action = original_find_pending_focus
        app.find_pending_operation = original_find_operation_focus
        app.candidate_cv_evaluation = original_candidate_cv_eval
        app.call_capability_planner = original_capability_planner
        app.latest_repairable_context = original_latest_repairable_context
        app.find_application_by_key = original_find_application_by_key_focus

    employee_context = app.set_operational_focus({"focus": app.default_focus_context()}, app.employee_focus_from_employee({
        "employee_key": "emp-fouad",
        "phone": "96551234567",
        "name": "Fouad Burhamad",
        "company_code": "WATHEFNI",
    }, source_action="start_onboarding"))
    employee_message = app.bind_focus_to_action({"action_type": "send_custom_employee_message", "message_text": "Please send your civil ID"}, employee_context, "message him")
    assert_true(employee_message["subject_key"] == "emp-fouad", "employee pronoun must bind focused employee")

    original_resolve_application = app.resolve_application_for_action
    try:
        app.resolve_application_for_action = lambda action, allow_latest=False: focus_app if action.get("app_key") == focus_app["app_key"] else None
        updated_context = app.operational_context_from_action_result(
            {"focus": app.default_focus_context()},
            action_type="send_assessment",
            status="failed",
            action={"action_type": "send_assessment", "app_key": focus_app["app_key"], "turn_id": "failed-assessment-turn"},
            result_payload={"error": "conversation_closed"},
        )
        assert_true(updated_context["focus"]["current_candidate"]["app_key"] == focus_app["app_key"], "failed candidate action must still persist candidate focus")
        assert_true(updated_context["last_failed_action"]["action_type"] == "send_assessment", "failed action must persist as operational context")
        assert_true(updated_context["last_failed_action"]["channel"] == "whatsapp", "assessment send failure must store WhatsApp channel")
        assert_true(updated_context["last_failed_action"]["source_turn_id"] == "failed-assessment-turn", "failed action must store source turn id")
    finally:
        app.resolve_application_for_action = original_resolve_application

    original_run_gog = app.run_gog
    try:
        app.run_gog = lambda args, timeout=60: {"ok": True, "json": {"id": "gmail-message-1"}, "stderr": "", "stdout": ""}
        sent_email = app.send_email(focus_app, {"prompt_text": "send Fouad an email for an assessment test reminder"})
        assert_true(sent_email["ok"] is True, "stubbed Gmail send must succeed")
        assert_true(sent_email["subject"] == "Application Assessment Reminder", "send_email must store exact assessment reminder subject")
        assert_true("application assessment" in sent_email["body"].lower(), "send_email must store exact assessment reminder body")
        assert_true(sent_email["recipient_email"] == focus_app["candidate_email"], "send_email must store recipient email")
        assert_true(sent_email["gmail_message_id"] == "gmail-message-1", "send_email must store Gmail message id when returned")
        onboarding_email = app.send_email(focus_app, {"prompt_text": "email him for onboarding / compliance", "purpose": "onboarding_compliance"})
        assert_true(onboarding_email["subject"] == "Onboarding and Compliance Requirements", "onboarding/compliance email must use purpose-specific subject")
        assert_true("onboarding and compliance requirements" in onboarding_email["body"].lower(), "onboarding/compliance email body must match purpose")
        sent_payload = app.normalized_result_payload(
            action_type="send_email",
            status="completed",
            action={"action_type": "send_email", "app_key": focus_app["app_key"], "subject_name": "Fouad Burhamad"},
            result_payload=sent_email,
            template_reply="Done — I’ve sent the email to Fouad Burhamad.",
        )
        history_reply = app.format_action_history_followup_reply({
            "question": "u emailed him and said what",
            "latest_successful_action": {
                "action_type": "send_email",
                "status": "completed",
                "result": sent_payload,
                "final_reply": "Done — I’ve sent the email to Fouad Burhamad.",
                "normalized_action_result": sent_payload["normalized_action_result"],
            },
        })
        assert_true("Subject: Application Assessment Reminder" in history_reply, "sent-message follow-up must show exact stored subject")
        assert_true("application assessment" in history_reply.lower(), "sent-message follow-up must show exact stored body")
        assert_true("failed" not in history_reply.lower(), "sent-message follow-up must not invent a failure")
        assert_true("Fouad" in history_reply, "sent-message follow-up must use the stored successful action target")
        direct_what_reply = app.format_action_history_followup_reply({
            "question": "What did u send",
            "latest_successful_action": {
                "action_type": "send_email",
                "status": "completed",
                "result": sent_payload,
                "final_reply": "Done — I’ve sent the email to Fouad Burhamad.",
                "normalized_action_result": sent_payload["normalized_action_result"],
            },
        })
        assert_true("Subject: Application Assessment Reminder" in direct_what_reply, "what did u send must show exact stored subject/body")
        success_correction = app.enforce_operational_reply_invariants("I did not send it.", sent_payload)
        assert_true(success_correction.startswith("Actually, the email was sent successfully"), "success ActionResult must block false failure claims with human wording")
    finally:
        app.run_gog = original_run_gog

    original_send_email = app.send_email
    original_retry_legacy = app.retry_last_employee_message
    try:
        calls = {"email": 0, "legacy": 0}
        app.resolve_application_for_action = lambda action, allow_latest=False: focus_app if action.get("app_key") == focus_app["app_key"] else None
        app.send_email = lambda resolved_app, action: calls.__setitem__("email", calls["email"] + 1) or {"ok": False, "error": "gmail_auth_required", "candidate": app.candidate_contact(resolved_app)}
        app.retry_last_employee_message = lambda account_id: calls.__setitem__("legacy", calls["legacy"] + 1) or {"ok": False, "error": "legacy_called"}
        failed_email_context = app.operational_context_from_action_result(
            {"focus": app.default_focus_context()},
            action_type="send_email",
            status="failed",
            action={"action_type": "send_email", "app_key": focus_app["app_key"], "subject_name": "Fouad Burhamad", "turn_id": "failed-email-turn"},
            result_payload={"error": "gmail_auth_required"},
        )
        gmail_config_payload = app.normalized_result_payload(
            action_type="send_email",
            status="failed",
            action={"action_type": "send_email", "app_key": focus_app["app_key"], "subject_name": "Fouad Burhamad"},
            result_payload={
                "ok": False,
                "gmail": {
                    "ok": False,
                    "stderr": "gmail options: service account token source: service account path: resolve user config dir: neither $XDG_CONFIG_HOME nor $HOME are defined\n",
                    "returncode": 1,
                },
                "candidate": app.candidate_contact(focus_app),
            },
            template_reply="I could not send the email to Fouad Burhamad.",
        )
        normalized = gmail_config_payload["normalized_action_result"]
        assert_true(normalized["error_code"] == "gmail_config_home_missing", "normalized email result must expose Gmail config error code")
        assert_true(normalized["channel"] == "email", "normalized email result must expose channel")
        assert_true(normalized["target_name"] == "Fouad Burhamad", "normalized email result must expose target name")
        assert_true("server environment" in normalized["safe_user_message"], "normalized email result must have a safe explainable user message")
        why_reply = app.action_failure_explanation_from_normalized(normalized)
        assert_true("gmail sender" in why_reply.lower(), "why reply must explain Gmail backend cause")
        assert_true("could not send the email" not in why_reply.lower(), "why reply must not just repeat the final failure reply")
        retry_req = app.WhatsAppTurnRequest(
            account_id="default",
            conversation_id="conv-retry-email",
            sender_phone="+965 9933 8566",
            sender_role="hr_admin",
            raw_text="try again now",
        )
        status, retry_reply, retry_payload = app.retry_action_from_failed_context({
            "request": retry_req,
            "turn_id": "retry-email-turn",
            "persistent_context": failed_email_context,
            "turn_scratch": app.turn_scratch_for_request(retry_req, "retry-email-turn"),
        })
        assert_true(status == "failed", "failed email retry should preserve failed status from Gmail")
        assert_true(calls["email"] == 1, "generic retry must retry send_email")
        assert_true(calls["legacy"] == 0, "generic retry must not call legacy WhatsApp retry when failed email exists")
        assert_true(retry_payload["retried_action_type"] == "send_email", "retry payload must identify retried email action")
        assert_true("email" in retry_reply.lower(), "retry reply must describe email retry")
    finally:
        app.resolve_application_for_action = original_resolve_application
        app.send_email = original_send_email
        app.retry_last_employee_message = original_retry_legacy

    ambiguous_retry_context = {
        "focus": app.default_focus_context(),
        "last_failed_action": {
            "action_type": "send_email",
            "target_type": "candidate",
            "target_id": "app-1",
            "target_name": "Aziz",
            "failed_at": app.operational_context_timestamp(),
            "expires_at": app.operational_context_timestamp(60),
            "payload": {"action": {"action_type": "send_email", "app_key": "app-1"}},
        },
        "failed_action_history": [
            {
                "action_type": "send_email",
                "target_type": "candidate",
                "target_id": "app-1",
                "target_name": "Aziz",
                "failed_at": app.operational_context_timestamp(),
                "expires_at": app.operational_context_timestamp(60),
                "payload": {"action": {"action_type": "send_email", "app_key": "app-1"}},
            },
            {
                "action_type": "send_assessment",
                "target_type": "candidate",
                "target_id": "app-2",
                "target_name": "Fouad",
                "failed_at": app.operational_context_timestamp(),
                "expires_at": app.operational_context_timestamp(60),
                "payload": {"action": {"action_type": "send_assessment", "app_key": "app-2"}},
            },
        ],
    }
    status, retry_reply, retry_payload = app.retry_action_from_failed_context({
        "request": retry_req,
        "turn_id": "retry-ambiguous-turn",
        "persistent_context": ambiguous_retry_context,
        "turn_scratch": app.turn_scratch_for_request(retry_req, "retry-ambiguous-turn"),
    })
    assert_true(status == "needs_clarification", "multiple recent failed actions must ask clarification")
    assert_true(retry_payload["reason"] == "multiple_recent_failed_actions", "ambiguous retry must not pick a stale action")
    ambiguous_pending_context = app.operational_context_from_action_result(
        ambiguous_retry_context,
        action_type="retry_last_failed_action",
        status="needs_clarification",
        action={"action_type": "retry_last_failed_action", "prompt_text": "try again pls", "turn_id": "ambiguous-retry-turn"},
        result_payload=retry_payload,
    )
    assert_true(ambiguous_pending_context["last_failed_action"]["action_type"] == "send_email", "ambiguous retry prompt must not replace the original failed action with retry wrapper")
    assert_true(len(ambiguous_pending_context["pending_action"]["payload"]["failed_actions"]) == 2, "ambiguous retry options must be stored for clarification")
    dirty_retry_context = app.persistent_context_pruned({
        "focus": app.default_focus_context(),
        "last_failed_action": {
            "action_type": "retry_last_failed_action",
            "target_type": None,
            "target_id": None,
            "error_code": "failed",
            "failed_at": app.operational_context_timestamp(),
            "expires_at": app.operational_context_timestamp(60),
        },
        "failed_action_history": [
            {
                "action_type": "retry_last_failed_action",
                "target_type": None,
                "target_id": None,
                "error_code": "failed",
                "failed_at": app.operational_context_timestamp(),
                "expires_at": app.operational_context_timestamp(60),
            },
            {
                "action_type": "send_email",
                "target_type": "candidate",
                "target_id": "app-hr",
                "target_name": "Aziz Almulla",
                "failed_at": app.operational_context_timestamp(),
                "expires_at": app.operational_context_timestamp(60),
                "payload": {"action": {"action_type": "send_email", "app_key": "app-hr"}},
            },
        ],
    })
    assert_true(dirty_retry_context["last_failed_action"]["action_type"] == "send_email", "stale retry wrapper checkpoints must unwrap to the business failed action")
    hr_retry_context = {
        "focus": app.default_focus_context(),
        "pending_action": {
            "action_type": "retry_last_failed_action",
            "payload": {
                "failed_actions": [
                    {
                        "action_type": "send_email",
                        "target_type": "candidate",
                        "target_id": "app-hr",
                        "target_name": "Aziz Almulla",
                        "failed_at": app.operational_context_timestamp(),
                        "expires_at": app.operational_context_timestamp(60),
                        "payload": {
                            "action": {"action_type": "send_email", "app_key": "app-hr"},
                            "result": {"payload": {"candidate": {"name": "Aziz Almulla", "position_title": "HR"}}},
                        },
                    },
                ]
            },
            "expires_at": app.operational_context_timestamp(60),
        },
    }
    clarified_retry = app.retry_clarification_action("the one with the hr cv", hr_retry_context)
    assert_true(clarified_retry["action_type"] == "retry_last_failed_action", "retry clarification must route back to generic retry")
    assert_true(clarified_retry["selected_failed_action"]["target_id"] == "app-hr", "retry clarification must select the HR CV option")

    list_context = {
        "focus": app.default_focus_context(),
        "last_result_set": {
            "type": "leave_requests",
            "items": [
                {"leave_id": "leave-1", "employee_name": "Aziz"},
                {"leave_id": "leave-2", "employee_name": "Fouad"},
            ],
            "source_action": "list_leave_requests",
            "updated_at": app.operational_context_timestamp(),
            "expires_at": app.operational_context_timestamp(30),
        },
    }
    ordinal_action = app.direct_action_from_operational_context("approve the second one", list_context)
    assert_true(ordinal_action["action_type"] == "approve_leave_request", "ordinal leave follow-up must route to leave approval")
    assert_true(ordinal_action["leave_id"] == "leave-2", "second one must bind to second leave request")

    candidate_list_context = {
        "focus": app.default_focus_context(),
        "last_result_set": {
            "type": "candidates",
            "items": [
                {
                    "app_key": "app-aziz",
                    "candidate_name": "Aziz Almulla",
                    "position_title": "HR Officer",
                    "status": "screening_complete",
                    "score": 82,
                    "notes": "Completed screening",
                },
                {
                    "app_key": "app-fouad",
                    "candidate_name": "Fouad Burhamad",
                    "position_title": "HR Officer",
                    "status": "review_pending",
                },
            ],
            "source_action": "list_candidates",
            "updated_at": app.operational_context_timestamp(),
            "expires_at": app.operational_context_timestamp(30),
        },
    }
    compare_action = app.direct_action_from_operational_context("compare first two", candidate_list_context)
    assert_true(compare_action["action_type"] == "compare_candidates", "compare first two must route to grounded candidate comparison")
    assert_true(compare_action["candidate_ids"] == ["app-aziz", "app-fouad"], "compare first two must bind both candidate ids")
    original_find_application = app.find_application_by_key
    try:
        app.find_application_by_key = lambda app_key: {
            "app-aziz": {
                "app_key": "app-aziz",
                "company_code": "WATHEFNI",
                "phone": "96511111111",
                "candidate_name": "Aziz Almulla",
                "candidate_email": "aziz@example.com",
                "position_title": "HR Officer",
                "position_code": "HR_OFFICER",
                "status": "screening_complete",
                "cv_received": True,
                "updated_at": "2026-05-12T10:00:00+00:00",
                "raw_json": {"assessment": {"status": "completed", "score": 76}, "notes": "Completed screening"},
            },
            "app-fouad": {
                "app_key": "app-fouad",
                "company_code": "WATHEFNI",
                "phone": "96522222222",
                "candidate_name": "Fouad Burhamad",
                "candidate_email": "fouad@example.com",
                "position_title": "HR Officer",
                "position_code": "HR_OFFICER",
                "status": "review_pending",
                "cv_received": False,
                "updated_at": "2026-05-12T09:00:00+00:00",
                "raw_json": {},
            },
        }.get(app_key)
        comparison = app.compare_candidates(compare_action, company_code="WATHEFNI")
        assert_true(comparison["ok"] is True, "compare_candidates must complete with two stored candidates")
        reply = app.format_compare_candidates_reply(comparison)
        assert_true("Grounded candidate comparison" in reply, "compare reply must be grounded comparison output")
        assert_true("missing" in reply.lower(), "compare reply must explicitly show missing data")
        assert_true("invent" not in reply.lower(), "compare reply must not invent qualifications")
    finally:
        app.find_application_by_key = original_find_application

    assert_true(app.ROUTING_PRIORITY_CONTRACT[0] == "pending_confirmation_or_clarification", "routing contract must be explicit and priority ordered")
    assert_true(app.is_candidate_cv_evaluation_question("who is the most accomplished"), "implicit accomplishment question must be candidate/CV evaluation")
    assert_true(not app.is_workforce_analytics_question("who is the most accomplished"), "broad who+most must not be stolen by workforce analytics")
    assert_true(app.infer_direct_action("who is the most accomplished")["action_type"] == "candidate_cv_evaluation", "most accomplished must route to candidate_cv_evaluation")
    assert_true(app.infer_direct_action("in general based on CVs")["action_type"] == "candidate_cv_evaluation", "based on CVs correction must route to candidate_cv_evaluation")
    assert_true(app.infer_direct_action("who is late the most this month")["action_type"] == "workforce_analytics", "workforce signal must still route to workforce analytics")
    assert_true(app.is_pure_greeting("hi"), "hi must be recognized as a fresh greeting")
    assert_true(app.is_pure_greeting("hala walla"), "Kuwaiti greeting must be recognized as a fresh greeting")
    assert_true(app.is_fresh_conversational_opener("i have a question"), "question opener must be recognized as fresh small talk")
    assert_true(app.greeting_reply_for_text("yo") == "", "orchestrator must not own hardcoded conversational replies")
    assert_true(app.is_sent_message_history_question("did u send it?"), "short send verification must route to action history, not new send action")

    original_find_pending = app.find_pending_action
    original_find_operation = app.find_pending_operation
    original_pending_operation_action = app.pending_operation_direct_action
    original_verification = app.verification_followup_context
    original_operational = app.recent_operational_followup_context
    original_action_history = app.action_history_followup_context
    original_position_filter = app.infer_position_filter_from_text
    original_refinement_planner = app.call_analytical_refinement_planner
    original_capability_planner_refinement = app.call_capability_planner
    try:
        app.find_pending_action = lambda request: None
        app.find_pending_operation = lambda request: None
        app.pending_operation_direct_action = lambda request, operation: None
        app.verification_followup_context = lambda request: None
        app.recent_operational_followup_context = lambda text: None
        app.action_history_followup_context = lambda request, context: None
        def fake_position_filter(text):
            normalized = app.normalize_text(text)
            if "social media" in normalized:
                return "SOCIAL_MEDIA_MANAGER"
            if "accounting" in normalized:
                return "ACCOUNTING"
            if "hr" in normalized:
                return "HR"
            return original_position_filter(text)

        def fake_refinement_planner(*, text, latest_action, company_code, timeout=8):
            normalized = app.normalize_text(text)
            previous = latest_action.get("action_type")
            if normalized == "for hr pls":
                return {"intent": "analytical_refinement", "previous_action": previous, "filters": {"job_role": "HR"}, "confidence": 0.91}
            if normalized == "what about social media":
                return {"intent": "analytical_refinement", "previous_action": previous, "filters": {"job_role": "Social Media"}, "confidence": 0.9}
            if normalized == "only shortlisted":
                return {"intent": "analytical_refinement", "previous_action": previous, "filters": {"status": "shortlisted"}, "confidence": 0.9}
            if normalized == "top 3":
                return {"intent": "analytical_refinement", "previous_action": previous, "filters": {"count": 3}, "confidence": 0.9}
            if normalized == "same for accounting":
                return {"intent": "analytical_refinement", "previous_action": previous, "filters": {"job_role": "Accounting"}, "confidence": 0.9}
            if normalized == "this month":
                return {"intent": "analytical_refinement", "previous_action": previous, "filters": {"time_period": "this_month"}, "confidence": 0.9}
            if normalized == "same one":
                return {"intent": "clarification_needed", "previous_action": previous, "question": "Which filter should I apply?", "confidence": 0.82}
            if normalized == "for astronauts":
                return {"intent": "analytical_refinement", "previous_action": previous, "filters": {"job_role": "Astronauts"}, "confidence": 0.91}
            return None

        def fake_capability_refinement_planner(**kwargs):
            normalized = app.normalize_text(kwargs.get("text"))
            if normalized == "for hr pls":
                return {"capability": "filter_refine", "entity_type": "candidate", "filters": {"job_role": "HR"}, "confidence": 0.91}
            if normalized == "what about social media":
                return {"capability": "filter_refine", "entity_type": "candidate", "filters": {"job_role": "Social Media"}, "confidence": 0.93}
            if normalized == "only shortlisted":
                return {"capability": "filter_refine", "entity_type": "candidate", "filters": {"stage": "shortlisted"}, "confidence": 0.92}
            if normalized == "top 3":
                return {"capability": "filter_refine", "entity_type": "candidate", "filters": {"count": 3}, "confidence": 0.9}
            if normalized == "same for accounting":
                return {"capability": "filter_refine", "entity_type": "candidate", "filters": {"job_role": "Accounting"}, "confidence": 0.9}
            if normalized == "this month":
                return {"capability": "filter_refine", "entity_type": "analytics", "filters": {"time_period": "this_month"}, "confidence": 0.9}
            if normalized == "same one":
                return {"capability": "filter_refine", "entity_type": "candidate", "filters": {}, "confidence": 0.82}
            if normalized == "for astronauts":
                return {"capability": "filter_refine", "entity_type": "candidate", "filters": {"job_role": "Astronauts"}, "confidence": 0.91}
            if normalized == "shlonk":
                return {"capability": "small_talk", "confidence": 0.93, "reason": "Kuwaiti casual check-in"}
            return None

        app.infer_position_filter_from_text = fake_position_filter
        app.call_analytical_refinement_planner = fake_refinement_planner
        app.call_capability_planner = fake_capability_refinement_planner
        greeting_req = app.WhatsAppTurnRequest(
            account_id="default",
            conversation_id="conv-fresh-greeting",
            sender_phone="+965 9933 8566",
            sender_role="hr_admin",
            raw_text="hi",
        )
        classified_greeting = app.classify({
            "request": greeting_req,
            "turn_id": "turn-fresh-greeting",
            "persistent_context": {
                "focus": app.default_focus_context(),
                "last_result_set": {
                    "type": "candidates",
                    "items": [{"app_key": "stale-app", "candidate_name": "Fouad Burhamad"}],
                    "updated_at": app.operational_context_timestamp(),
                    "expires_at": app.operational_context_timestamp(60),
                },
                "last_failed_action": {
                    "action_type": "send_email",
                    "target_name": "Fouad Burhamad",
                    "error_code": "gmail_auth_required",
                    "failed_at": app.operational_context_timestamp(),
                    "expires_at": app.operational_context_timestamp(60),
                },
                "offered_followup": {
                    "action_type": "check_assessment_config",
                    "created_at": app.operational_context_timestamp(),
                    "expires_at": app.operational_context_timestamp(60),
                },
            },
            "turn_scratch": app.turn_scratch_for_request(greeting_req, "turn-fresh-greeting"),
            "direct_action": {"action_type": "candidate_cv_evaluation", "prompt_text": "stale planner action"},
            "planner_plan": {"action_type": "check_assessment_config", "prompt_text": "stale planner action"},
            "audit": {},
        })
        assert_true(classified_greeting["intent"] == "answer_greeting", "pure greeting must route to fresh greeting")
        assert_true(classified_greeting.get("direct_action") is None, "pure greeting must ignore stale direct/planner actions")
        assert_true(classified_greeting["audit"]["pure_greeting"] is True, "pure greeting must be recorded in routing audit")
        shlonk_req = copy_request(greeting_req, raw_text="shlonk")
        classified_shlonk = app.classify({
            "request": shlonk_req,
            "turn_id": "turn-gpt-small-talk",
            "persistent_context": {"focus": app.default_focus_context()},
            "turn_scratch": app.turn_scratch_for_request(shlonk_req, "turn-gpt-small-talk"),
            "direct_action": None,
            "planner_plan": None,
            "audit": {},
        })
        assert_true(classified_shlonk["intent"] == "answer_greeting", "GPT-classified small talk must route to greeting")
        assert_true(classified_shlonk["capability_decision"]["status"] == "small_talk", "small talk must be validated by backend capability decision")
        assert_true(classified_shlonk["candidate_focus"] is None, "small talk must not use candidate focus or stale context")
        stale_outer_context = {
            "focus": app.default_focus_context(),
            "last_successful_action": {
                "action_type": "candidate_cv_evaluation",
                "target_name": "Talal Fadhli",
                "payload": {"reply": "old Talal / Google Sheets / Gmail context"},
                "completed_at": app.operational_context_timestamp(),
                "expires_at": app.operational_context_timestamp(60),
            },
            "last_failed_action": {
                "action_type": "send_email",
                "target_name": "Talal Fadhli",
                "error_code": "gmail_auth_required",
                "failed_at": app.operational_context_timestamp(),
                "expires_at": app.operational_context_timestamp(60),
            },
        }
        unsure_req = copy_request(greeting_req, raw_text="hmm idk")
        classified_unsure = app.classify({
            "request": unsure_req,
            "turn_id": "turn-neutral-help-fallback",
            "persistent_context": stale_outer_context,
            "turn_scratch": app.turn_scratch_for_request(unsure_req, "turn-neutral-help-fallback"),
            "direct_action": None,
            "planner_plan": None,
            "audit": {},
        })
        neutral_fallback = app.fallback(classified_unsure)
        assert_true(neutral_fallback["authoritative"] is True, "generic HR fallback must stay authoritative inside orchestrator")
        assert_true(neutral_fallback["intent"] == "answer_neutral_help_fallback", "generic HR fallback must use neutral help intent")
        assert_true(neutral_fallback["final_reply_source"] == "backend_neutral_help_fallback", "generic HR fallback must not use OpenClaw runtime fallback")
        assert_true("No worries" in neutral_fallback["reply_text"], "casual uncertainty must get neutral help")
        stale_words = ["talal", "sheet", "google", "gmail"]
        assert_true(not any(word in neutral_fallback["reply_text"].lower() for word in stale_words), "neutral fallback must not mention stale operational context")
        opener_req = app.WhatsAppTurnRequest(
            account_id="default",
            conversation_id="conv-question-opener",
            sender_phone="+965 9933 8566",
            sender_role="hr_admin",
            raw_text="i have a question",
        )
        classified_opener = app.classify({
            "request": opener_req,
            "turn_id": "turn-question-opener",
            "persistent_context": {
                "focus": app.default_focus_context(),
                "last_failed_action": {
                    "action_type": "send_email",
                    "target_name": "Fouad Burhamad",
                    "error_code": "gmail_auth_required",
                    "failed_at": app.operational_context_timestamp(),
                    "expires_at": app.operational_context_timestamp(60),
                },
            },
            "turn_scratch": app.turn_scratch_for_request(opener_req, "turn-question-opener"),
            "direct_action": {"action_type": "candidate_cv_evaluation", "prompt_text": "stale planner action"},
            "planner_plan": {"action_type": "check_assessment_config", "prompt_text": "stale planner action"},
            "audit": {},
        })
        assert_true(classified_opener["intent"] == "answer_greeting", "question opener must not continue stale operational context")
        cv_req = app.WhatsAppTurnRequest(
            account_id="default",
            conversation_id="conv-routing-cv",
            sender_phone="+965 9933 8566",
            sender_role="hr_admin",
            raw_text="in general based on CVs",
        )
        classified_cv = app.classify({
            "request": cv_req,
            "turn_id": "turn-routing-cv",
            "persistent_context": {
                "focus": app.default_focus_context(),
                "last_successful_action": {
                    "action_type": "workforce_analytics",
                    "completed_at": app.operational_context_timestamp(),
                    "expires_at": app.operational_context_timestamp(60),
                },
                "last_failed_action": {
                    "action_type": "send_email",
                    "target_name": "Fouad Burhamad",
                    "error_code": "gmail_auth_required",
                    "failed_at": app.operational_context_timestamp(),
                    "expires_at": app.operational_context_timestamp(60),
                },
            },
            "turn_scratch": app.turn_scratch_for_request(cv_req, "turn-routing-cv"),
            "direct_action": None,
            "planner_plan": {"action_type": "workforce_analytics", "prompt_text": "in general based on CVs"},
            "audit": {},
        })
        assert_true(classified_cv["intent"] == "execute_direct_action", "CV correction must execute a grounded route")
        assert_true(classified_cv["direct_action"]["action_type"] == "candidate_cv_evaluation", "CV correction must not reuse analytics or stale email context")
        refinement_req = app.WhatsAppTurnRequest(
            account_id="default",
            conversation_id="conv-analytical-refinement",
            sender_phone="+965 9933 8566",
            sender_role="hr_admin",
            raw_text="for hr pls",
        )
        refinement_context = {
            "focus": app.default_focus_context(),
            "last_successful_action": {
                "action_type": "candidate_cv_evaluation",
                "payload": {
                    "action": {
                        "action_type": "candidate_cv_evaluation",
                        "subject_type": "candidate",
                        "prompt_text": "out of everyone we have who is the most accomplished",
                        "query": "out of everyone we have who is the most accomplished",
                        "top_n": 5,
                    },
                    "result": {"ok": True, "candidates": [{"name": "Aziz Almulla"}]},
                },
                "completed_at": app.operational_context_timestamp(),
                "expires_at": app.operational_context_timestamp(60),
            },
        }
        classified_refinement = app.classify({
            "request": refinement_req,
            "turn_id": "turn-analytical-refinement",
            "persistent_context": refinement_context,
            "turn_scratch": app.turn_scratch_for_request(refinement_req, "turn-analytical-refinement"),
            "direct_action": None,
            "planner_plan": None,
            "audit": {},
        })
        assert_true(classified_refinement["intent"] == "execute_direct_action", "short analytical refinement must compile through capability framework")
        assert_true(classified_refinement["direct_action"]["action_type"] == "candidate_cv_evaluation", "analytical refinement must rerun prior CV evaluation action")
        assert_true(classified_refinement["direct_action"]["position"] == "HR", "analytical refinement must apply role/job filter")
        assert_true(classified_refinement["direct_action"]["resolved_from_analytical_refinement"] is True, "analytical refinement must be tagged")
        assert_true(classified_refinement["direct_action"]["capability"] == "filter_refine", "analytical refinement must be capability validated")
        for raw_text, expected_key, expected_value in [
            ("what about social media", "position", "SOCIAL_MEDIA_MANAGER"),
            ("only shortlisted", "status", "shortlisted"),
            ("top 3", "top_n", 3),
            ("same for accounting", "position", "ACCOUNTING"),
        ]:
            req = copy_request(refinement_req, raw_text=raw_text)
            classified_more = app.classify({
                "request": req,
                "turn_id": f"turn-analytical-refinement-{expected_key}",
                "persistent_context": refinement_context,
                "turn_scratch": app.turn_scratch_for_request(req, f"turn-analytical-refinement-{expected_key}"),
                "direct_action": None,
                "planner_plan": None,
                "audit": {},
            })
            assert_true(classified_more["intent"] == "execute_direct_action", f"{raw_text} must compile to grounded action through capability")
            assert_true(classified_more["direct_action"][expected_key] == expected_value, f"{raw_text} must apply {expected_key} filter")
            assert_true(classified_more["direct_action"]["analytical_refinement"]["source"] == "capability_planner", f"{raw_text} must use structured capability proposal")
        workforce_refinement_context = {
            "focus": app.default_focus_context(),
            "last_successful_action": {
                "action_type": "workforce_analytics",
                "payload": {
                    "action": {"action_type": "workforce_analytics", "subject_type": "analytics", "prompt_text": "who is late the most", "query": "who is late the most"},
                    "result": {"ok": True, "summary": {}},
                },
                "completed_at": app.operational_context_timestamp(),
                "expires_at": app.operational_context_timestamp(60),
            },
        }
        month_req = copy_request(refinement_req, raw_text="this month")
        classified_month = app.classify({
            "request": month_req,
            "turn_id": "turn-analytical-refinement-month",
            "persistent_context": workforce_refinement_context,
            "turn_scratch": app.turn_scratch_for_request(month_req, "turn-analytical-refinement-month"),
            "direct_action": None,
            "planner_plan": None,
            "audit": {},
        })
        assert_true(classified_month["intent"] == "execute_direct_action", "this month must refine workforce analytics through capability")
        assert_true(classified_month["direct_action"]["action_type"] == "workforce_analytics", "workforce refinement must rerun workforce analytics")
        assert_true(classified_month["direct_action"].get("start_date") and classified_month["direct_action"].get("end_date"), "time refinement must apply a date range")
        ambiguous_req = copy_request(refinement_req, raw_text="same one")
        classified_ambiguous = app.classify({
            "request": ambiguous_req,
            "turn_id": "turn-analytical-refinement-ambiguous",
            "persistent_context": refinement_context,
            "turn_scratch": app.turn_scratch_for_request(ambiguous_req, "turn-analytical-refinement-ambiguous"),
            "direct_action": None,
            "planner_plan": None,
            "audit": {},
        })
        assert_true(classified_ambiguous["intent"] == "answer_capability_decision", "ambiguous refinement must stay in capability validation")
        assert_true(classified_ambiguous.get("direct_action") is None, "ambiguous refinement must not execute")
        assert_true(classified_ambiguous["capability_decision"]["status"] == "needs_clarification", "ambiguous refinement must ask clarification")
        invalid_req = copy_request(refinement_req, raw_text="for astronauts")
        classified_invalid = app.classify({
            "request": invalid_req,
            "turn_id": "turn-analytical-refinement-invalid",
            "persistent_context": refinement_context,
            "turn_scratch": app.turn_scratch_for_request(invalid_req, "turn-analytical-refinement-invalid"),
            "direct_action": None,
            "planner_plan": None,
            "audit": {},
        })
        assert_true(classified_invalid["intent"] == "answer_capability_decision", "invalid refinement must stay in capability validation")
        assert_true(classified_invalid.get("direct_action") is None, "invalid refinement must not execute")
        assert_true("not valid" in classified_invalid["capability_decision"]["reply"].lower(), "invalid refinement must return a safe validation response")
        compare_req = app.WhatsAppTurnRequest(
            account_id="default",
            conversation_id="conv-compare-candidates",
            sender_phone="+965 9933 8566",
            sender_role="hr_admin",
            raw_text="compare first two",
        )
        classified_compare = app.classify({
            "request": compare_req,
            "turn_id": "turn-compare-candidates",
            "persistent_context": candidate_list_context,
            "turn_scratch": app.turn_scratch_for_request(compare_req, "turn-compare-candidates"),
            "direct_action": None,
            "planner_plan": None,
            "audit": {},
        })
        assert_true(classified_compare["intent"] == "execute_direct_action", "compare first two must not fall through to fallback")
        assert_true(classified_compare["direct_action"]["action_type"] == "compare_candidates", "compare first two must call compare_candidates")
        check_req = app.WhatsAppTurnRequest(
            account_id="default",
            conversation_id="conv-offered-followup",
            sender_phone="+965 9933 8566",
            sender_role="hr_admin",
            raw_text="Pls check",
        )
        classified = app.classify({
            "request": check_req,
            "turn_id": "turn-offered-followup",
            "persistent_context": offered_context,
            "turn_scratch": app.turn_scratch_for_request(check_req, "turn-offered-followup"),
            "direct_action": {"action_type": "retry_last_employee_message", "subject_type": "employee", "prompt_text": "Pls check"},
            "planner_plan": {"action_type": "retry_last_employee_message", "subject_type": "employee", "prompt_text": "Pls check"},
            "audit": {},
        })
        assert_true(classified["intent"] == "execute_direct_action", "offered follow-up acceptance must execute the offered action")
        assert_true(classified["direct_action"]["action_type"] == "check_assessment_config", "offered follow-up must outrank stale planner retry")
        why_req = app.WhatsAppTurnRequest(
            account_id="default",
            conversation_id="conv-why-followup",
            sender_phone="+965 9933 8566",
            sender_role="hr_admin",
            raw_text="why",
        )
        why_context = app.operational_context_from_action_result(
            {"focus": app.default_focus_context()},
            action_type="send_email",
            status="failed",
            action={"action_type": "send_email", "app_key": focus_app["app_key"], "subject_name": "Fouad Burhamad", "turn_id": "failed-email-turn"},
            result_payload=gmail_config_payload,
        )
        classified_why = app.classify({
            "request": why_req,
            "turn_id": "turn-why-followup",
            "persistent_context": why_context,
            "turn_scratch": app.turn_scratch_for_request(why_req, "turn-why-followup"),
            "direct_action": None,
            "planner_plan": None,
            "audit": {},
        })
        assert_true(classified_why["intent"] == "answer_action_failure", "bare why must route to latest failed action from persistent context")
        history_req = app.WhatsAppTurnRequest(
            account_id="default",
            conversation_id="conv-history-followup",
            sender_phone="+965 9933 8566",
            sender_role="hr_admin",
            raw_text="u emailed him and said what",
        )
        app.action_history_followup_context = lambda request, context: {"question": request.raw_text, "latest_successful_action": {"action_type": "send_email", "status": "completed", "result": sent_payload, "normalized_action_result": sent_payload["normalized_action_result"]}}
        classified_history = app.classify({
            "request": history_req,
            "turn_id": "turn-history-followup",
            "persistent_context": candidate_context,
            "turn_scratch": app.turn_scratch_for_request(history_req, "turn-history-followup"),
            "direct_action": None,
            "planner_plan": None,
            "audit": {},
        })
        assert_true(classified_history["intent"] == "answer_action_history_followup", "sent-message follow-up must route to action history, not fallback")
        did_send_req = app.WhatsAppTurnRequest(
            account_id="default",
            conversation_id="conv-did-send-followup",
            sender_phone="+965 9933 8566",
            sender_role="hr_admin",
            raw_text="did u email him?",
        )
        classified_did_send = app.classify({
            "request": did_send_req,
            "turn_id": "turn-did-send-followup",
            "persistent_context": candidate_context,
            "turn_scratch": app.turn_scratch_for_request(did_send_req, "turn-did-send-followup"),
            "direct_action": {"action_type": "send_email", "app_key": focus_app["app_key"], "prompt_text": "did u email him?"},
            "planner_plan": None,
            "audit": {},
        })
        assert_true(classified_did_send["intent"] == "answer_action_history_followup", "did-send questions must beat direct send_email routing")
        blocked = app.fallback({
            "request": history_req,
            "turn_id": "turn-history-followup",
            "turn_scratch": app.turn_scratch_for_request(history_req, "turn-history-followup"),
        })
        assert_true(blocked["final_reply_source"] == "blocked_operational_fallback", "operational fallback must be blocked from making claims")
        cv_blocked = app.fallback({
            "request": cv_req,
            "turn_id": "turn-routing-cv",
            "turn_scratch": app.turn_scratch_for_request(cv_req, "turn-routing-cv"),
            "persistent_context": {"last_failed_action": {"target_name": "Fouad Burhamad", "error_code": "gmail_auth_required"}},
        })
        assert_true(cv_blocked["final_reply_source"] == "blocked_domain_fallback", "domain fallback must be blocked for CV questions")
        assert_true("Fouad" not in cv_blocked["reply_text"] and "Gmail" not in cv_blocked["reply_text"], "blocked domain fallback must not leak stale Gmail/Fouad context")
    finally:
        app.find_pending_action = original_find_pending
        app.find_pending_operation = original_find_operation
        app.pending_operation_direct_action = original_pending_operation_action
        app.verification_followup_context = original_verification
        app.recent_operational_followup_context = original_operational
        app.action_history_followup_context = original_action_history
        app.infer_position_filter_from_text = original_position_filter
        app.call_analytical_refinement_planner = original_refinement_planner
        app.call_capability_planner = original_capability_planner_refinement

    verify_reply = app.format_verification_followup_reply({
        "latest_action_result": {
            "action_type": "mark_attendance_absent",
            "status": "failed",
            "final_reply": "I found approved leave for Fouad Burhamad on Monday, 11 May 2026, so I will not mark them absent.",
            "result": {
                "error": "approved_leave_exists",
                "attendance_date": "2026-05-11",
                "employee": {"name": "Fouad Burhamad"},
                "leave": {"start_date": "2026-05-11", "employee_name": "Fouad Burhamad"},
            },
        }
    })
    assert_true("approved leave" in verify_reply.lower(), "verification reply must use backend attendance/leave truth")
    assert_true("full stack" not in verify_reply.lower(), "verification reply must not leak stale candidate context")

    cv_eval_reply = (
        "Candidate/CV evaluation (stored data only):\n"
        "1. Aziz Almulla - Full Stack Developer | CV: received | stored-data score: 55.4\n"
        "I did not infer qualifications or accomplishments that are not present in stored records."
    )
    cv_eval_payload = app.normalized_result_payload(
        action_type="candidate_cv_evaluation",
        status="completed",
        action={"action_type": "candidate_cv_evaluation"},
        result_payload={"ok": True, "candidates": [{"name": "Aziz Almulla"}]},
        template_reply=cv_eval_reply,
    )
    assert_true(app.enforce_operational_reply_invariants(cv_eval_reply, cv_eval_payload) == cv_eval_reply, "read-only CV evaluation must preserve did-not-infer wording")
    rendered_cv_reply, rendered_cv_meta = app.render_grounded_reply(
        action_type="candidate_cv_evaluation",
        status="completed",
        result_payload=cv_eval_payload,
        template_reply=cv_eval_reply,
        user_text="who is the most accomplished",
    )
    assert_true("Candidate/CV evaluation" in rendered_cv_reply, "read-only renderer should keep grounded CV content available to wording layer")
    assert_true("I did not infer qualifications" in rendered_cv_reply, "styled CV reply must preserve grounded caution language")
    assert_true(rendered_cv_meta["mode"] == "operational_wording", "read-only renderer should use grounded operational wording")
    compare_reply = "No grounded recommendation is available because stored ranking scores are missing."
    compare_payload = app.normalized_result_payload(
        action_type="compare_candidates",
        status="completed",
        action={"action_type": "compare_candidates"},
        result_payload={"ok": True, "candidates": [{"name": "Aziz"}, {"name": "Fouad"}]},
        template_reply=compare_reply,
    )
    assert_true(app.enforce_operational_reply_invariants(compare_reply, compare_payload) == compare_reply, "read-only comparison must preserve missing-ranking caveat")
    rendered_compare_reply, rendered_compare_meta = app.render_grounded_reply(
        action_type="compare_candidates",
        status="completed",
        result_payload=compare_payload,
        template_reply=compare_reply,
        user_text="compare first two",
    )
    assert_true(rendered_compare_reply == compare_reply, "read-only renderer must preserve missing-ranking caveat when wording layer keeps template")
    assert_true(rendered_compare_meta["mode"] == "operational_wording", "read-only comparison should use grounded operational wording path")
    sent_ok_payload = app.normalized_result_payload(
        action_type="send_email",
        status="completed",
        action={"action_type": "send_email", "subject_name": "Aziz Almulla"},
        result_payload={"ok": True, "candidate": {"name": "Aziz Almulla"}},
        template_reply="Email sent to Aziz Almulla.",
    )
    blocked_success_email = app.enforce_operational_reply_invariants("I didn't send the email.", sent_ok_payload)
    assert_true(blocked_success_email.startswith("Actually, the email was sent successfully"), "successful email must block false not-sent claim with human wording")
    sent_fail_payload = app.normalized_result_payload(
        action_type="send_email",
        status="failed",
        action={"action_type": "send_email", "subject_name": "Aziz Almulla"},
        result_payload={"ok": False, "error": "gmail_auth_required", "safe_user_message": "The Gmail sender needs re-authentication."},
        template_reply="I could not send the email to Aziz Almulla.",
    )
    blocked_failed_email = app.enforce_operational_reply_invariants("Done, I sent it.", sent_fail_payload)
    assert_true("Done, I sent it" not in blocked_failed_email and "did not send" in blocked_failed_email, "failed email must block false sent claim")
    assert_true("don’t want to guess" in app.safe_fallback_reply("operational"), "operational fallback should be human but safe")
    assert_true("Wathefni" in app.safe_fallback_reply("domain"), "domain fallback should point back to stored records")

    facts = app.operational_fact_bundle(
        "mark_attendance_absent",
        "failed",
        {
            "error": "approved_leave_exists",
            "employee": {"name": "Fouad Burhamad", "email": "fb-urhama@gmail.com", "start_date": "2026-05-07"},
            "leave": {"start_date": "2026-05-11", "employee_name": "Fouad Burhamad"},
            "metadata": {"old_candidate_email": "azizalmulla16@gmail.com", "old_date": "2026-05-07"},
        },
        "I found approved leave for Fouad Burhamad on Monday, 11 May 2026, so I will not mark them absent.",
    )
    assert_true("2026-05-07" not in facts["dates"], "verifier facts must ignore unrelated nested metadata dates")
    assert_true(not facts["emails"], "non-candidate operational facts must not allow unrelated emails")
    ok, reason = app.verify_operational_wording(
        "Yes, I checked. Fouad Burhamad has approved leave on Monday, 11 May 2026, so I won't mark him absent.",
        facts,
    )
    assert_true(ok, f"grounded wording verifier should accept natural safe wording: {reason}")
    ok, reason = app.verify_operational_wording(
        "Yes, the Full Stack candidate with that email is Aziz Almulla at azizalmulla16@gmail.com.",
        facts,
    )
    assert_true(not ok and reason in {"missing_name:Fouad Burhamad", "missing_date:2026-05-11", "missing_approved_leave", "missing_absent_action", "unexpected_email", "stale_candidate_context"}, "verifier must reject stale candidate/email wording")

    original_wording = app.call_operational_wording_llm
    try:
        app.call_operational_wording_llm = lambda **kwargs: "Yes, I checked. Fouad Burhamad has approved leave on Monday, 11 May 2026, so I won't mark him absent."
        composed, metadata = app.compose_operational_reply(
            action_type="mark_attendance_absent",
            status="failed",
            result_payload={
                "error": "approved_leave_exists",
                "employee": {"name": "Fouad Burhamad"},
                "leave": {"start_date": "2026-05-11", "employee_name": "Fouad Burhamad"},
            },
            template_reply="I found approved leave for Fouad Burhamad on Monday, 11 May 2026, so I will not mark them absent.",
            user_text="r u sure",
        )
        assert_true(metadata.get("used") is True and "I checked" in composed, "verified LLM wording should replace template")
        app.call_operational_wording_llm = lambda **kwargs: "Yes, the Full Stack candidate is Aziz Almulla at azizalmulla16@gmail.com."
        composed, metadata = app.compose_operational_reply(
            action_type="mark_attendance_absent",
            status="failed",
            result_payload={
                "error": "approved_leave_exists",
                "employee": {"name": "Fouad Burhamad"},
                "leave": {"start_date": "2026-05-11", "employee_name": "Fouad Burhamad"},
            },
            template_reply="I found approved leave for Fouad Burhamad on Monday, 11 May 2026, so I will not mark them absent.",
            user_text="r u sure",
        )
        assert_true(metadata.get("used") is False and "approved leave" in composed.lower(), "failed wording verification must fall back to safe template")
    finally:
        app.call_operational_wording_llm = original_wording

    print("context guardrail smoke tests passed")


if __name__ == "__main__":
    main()
