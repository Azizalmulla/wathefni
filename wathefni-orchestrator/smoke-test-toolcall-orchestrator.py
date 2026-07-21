from __future__ import annotations

import sys
from pathlib import Path


class FakeLegacy:
    APP = {
        "app_key": "96597485758-WATHEFNI-HR",
        "company_code": "WATHEFNI",
        "candidate_name": "Hamad Almulla",
        "candidate_email": "h.almulla@almulla-media.com",
        "phone": "96597485758",
        "position_code": "HR",
        "position_title": "HR",
        "status": "review_pending",
    }
    APP_FAISAL = {
        "app_key": "96599652277-WATHEFNI-SOCIAL_MEDIA_MANAGER",
        "company_code": "WATHEFNI",
        "candidate_name": "Faisal Almulla",
        "candidate_email": None,
        "phone": "96599652277",
        "position_code": "SOCIAL_MEDIA_MANAGER",
        "position_title": "Social Media Manager",
        "status": "review_pending",
    }
    ENABLED_MODULES = {"pre_hiring", "assessments", "video_interviews"}

    @staticmethod
    def json_safe(value):
        return value

    @staticmethod
    def digits(value):
        return "".join(ch for ch in str(value or "") if ch.isdigit())

    @classmethod
    def company_has_module(cls, company_code, module_key):
        return str(module_key or "") in cls.ENABLED_MODULES

    @classmethod
    def require_entitlement(cls, context, module_key, permission=None):
        company = str((context or {}).get("company_code") or "").strip()
        actor = str((context or {}).get("actor_user_id") or "").strip()
        permissions = {str(item) for item in (context or {}).get("permissions") or []}
        role = str((context or {}).get("actor_role") or "")
        if not company or not actor or role == "invalid":
            raise FakeHTTPException({"error": "permission_denied", "message": "You do not have permission to do this action.", "required_permission": permission})
        if module_key not in cls.ENABLED_MODULES:
            raise FakeHTTPException({"error": "module_disabled", "message": "This module is not enabled for this company.", "required_module": module_key})
        if permission and permission not in permissions:
            raise FakeHTTPException({"error": "permission_denied", "message": "You do not have permission to do this action.", "required_permission": permission})
        return context

    @staticmethod
    def resolve_application_for_action(action, allow_latest=False):
        if (
            action.get("subject_name") == "Hamad Almulla"
            or action.get("app_key") == FakeLegacy.APP["app_key"]
            or action.get("subject_key") == FakeLegacy.APP["app_key"]
            or str(action.get("subject_name") or "").lower().startswith("hamad")
        ):
            return dict(FakeLegacy.APP)
        return None

    @staticmethod
    def resolve_candidate(*, app_key=None, phone=None, email=None, name=None, company_code=None, similarity_threshold=0.35, max_matches=5):
        searched = {k: v for k, v in {"app_key": app_key, "name": name, "email": email, "phone": phone}.items() if v}
        if not searched:
            return {"status": "no_input", "matches": [], "searched": {}}
        if app_key == FakeLegacy.APP["app_key"]:
            return {"status": "resolved", "matches": [dict(FakeLegacy.APP)], "searched": searched}
        if app_key == FakeLegacy.APP_FAISAL["app_key"]:
            return {"status": "resolved", "matches": [dict(FakeLegacy.APP_FAISAL)], "searched": searched}
        if email == FakeLegacy.APP["candidate_email"]:
            return {"status": "resolved", "matches": [dict(FakeLegacy.APP)], "searched": searched}
        if name and "hamad" in name.lower() and "faisal" not in name.lower():
            return {"status": "resolved", "matches": [dict(FakeLegacy.APP)], "searched": searched}
        if name and "faisal" in name.lower():
            return {"status": "resolved", "matches": [dict(FakeLegacy.APP_FAISAL)], "searched": searched}
        if name and "almulla" in name.lower():
            return {"status": "ambiguous", "matches": [dict(FakeLegacy.APP), dict(FakeLegacy.APP_FAISAL)], "searched": searched}
        return {"status": "not_found", "matches": [], "searched": searched}

    @staticmethod
    def find_application_by_key(app_key):
        return dict(FakeLegacy.APP) if app_key == FakeLegacy.APP["app_key"] else None

    @staticmethod
    def candidate_applications_by_email(email):
        return [dict(FakeLegacy.APP)] if email == FakeLegacy.APP["candidate_email"] else []

    @staticmethod
    def candidate_lookup_match_payload(app):
        return {
            "app_key": app.get("app_key"),
            "candidate_name": app.get("candidate_name"),
            "candidate_email": app.get("candidate_email"),
            "phone": app.get("phone"),
            "position_code": app.get("position_code"),
            "position_title": app.get("position_title"),
            "status": app.get("status"),
        }

    @staticmethod
    def latest_candidate_interview_for_app(app_key, company_code):
        return None

    @staticmethod
    def request_company_code(request):
        return "WATHEFNI"

    @staticmethod
    def compare_candidate_item(source, company_code=None):
        return {
            "app_key": source.get("app_key"),
            "name": FakeLegacy.APP["candidate_name"],
            "job": "HR",
            "stage": FakeLegacy.APP["status"],
            "ranking_score": 0.82,
        }

    @staticmethod
    def candidate_strengths_and_gaps(item):
        return (["CV received"], ["Assessment missing"])

    class _FakeCursor:
        def __init__(self, rows):
            self._rows = rows

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def execute(self, sql, params=None):
            self.last = (sql, params)

        def fetchone(self):
            return self._rows[0] if self._rows else None

        def fetchall(self):
            return list(self._rows or [])

    class _FakeConn:
        def __init__(self, rows):
            self._rows = rows

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def cursor(self):
            return FakeLegacy._FakeCursor(self._rows)

        def commit(self):
            pass

    @classmethod
    def db_connect(cls):
        return cls._FakeConn([
            {"position_code": "HR", "position_title": "HR"},
            {"position_code": "SOCIAL_MEDIA_MANAGER", "position_title": "Social Media Manager"},
        ])

    @staticmethod
    def production_application_predicate(alias="a"):
        return "TRUE"


class FakeRequest:
    raw_text = "is hamad good?"
    account_id = None
    conversation_id = None
    sender_phone = "+96597485758"
    metadata = {}


class FakeHTTPException(Exception):
    def __init__(self, detail):
        self.detail = detail


def assert_true(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def main() -> None:
    script_dir = Path(__file__).resolve().parent
    orchestrator_dir = script_dir
    if not (orchestrator_dir / "app.py").exists():
        orchestrator_dir = script_dir.parents[0] / "wathefni-orchestrator"
    sys.path.insert(0, str(orchestrator_dir))
    sys.modules["app"] = FakeLegacy()

    import action_registry
    import tool_call_orchestrator

    app_source = (orchestrator_dir / "app.py").read_text(encoding="utf-8")
    toolcall_source = (orchestrator_dir / "tool_call_orchestrator.py").read_text(encoding="utf-8")

    assert_true("handle_toolcall_whatsapp_turn" in app_source, "whatsapp_turn must call the toolcall orchestrator directly")
    assert_true("WATHEFNI_SIMPLE_ORCHESTRATOR_ENABLED" not in app_source, "old intent-renderer env fallback must be removed from live route")
    assert_true("GRAPH.invoke" not in app_source, "old graph fallback must be removed from live route")
    assert_true("toolcall_orchestrator_primary" in app_source, "toolcall route must identify as primary in audit")
    assert_true("WATHEFNI_TOOLCALL_LEGACY_FALLBACK" not in app_source, "toolcall errors must not fall through to legacy")
    assert_true("final_reply_source=\"toolcall_orchestrator_error\"" in app_source, "toolcall errors must fail closed instead of silently invoking old orchestrators")
    assert_true("latest_candidate_interview_for_app(app_key, company)" in app_source, "scheduled interview invites must look up only the exact current app_key")
    assert_true("latest_candidate_interview_for_candidate(application, company)" not in app_source[app_source.index("def send_interview_invite"):app_source.index("def interview_invite_status")], "send_interview_invite must not fall back to old interviews by phone/email")
    assert_true("communication_delivery_failure_message" in app_source and "invalid_grant" in app_source and "no_usable_conversation_id" in app_source, "delivery failures must map Gmail/WhatsApp technical errors to HR-safe messages")
    assert_true("def require_entitlement(" in app_source, "backend must expose one central entitlement helper")
    assert_true("_require_tool_entitlements" in toolcall_source and "legacy.require_entitlement" in toolcall_source, "tool execution must call central entitlement before execution")

    tools = action_registry.build_tool_schemas(FakeLegacy(), FakeRequest())
    tool_index = {t["function"]["name"]: t for t in tools}
    assert_true(action_registry.spec_for("send_assessment").module == "assessments", "send_assessment must be gated by the assessments module")
    assert_true(action_registry.spec_for("send_video_interview").module == "video_interviews", "send_video_interview must be gated by the video_interviews module")

    entitlement_scope = {
        "company_id": "WATHEFNI",
        "account_id": "WATHEFNI",
        "admin_user_id": "96597485758",
        "conversation_id": "entitlement-smoke",
        "channel": "web_dashboard",
        "module": "pre_hiring",
        "role_scope": "hr_manager",
        "permissions": ["prehire.read", "candidate.manage", "assessment.manage", "interview.manage"],
    }
    original_modules = set(FakeLegacy.ENABLED_MODULES)
    try:
        FakeLegacy.ENABLED_MODULES = {"pre_hiring", "video_interviews"}
        blocked_assessment = tool_call_orchestrator._execute_tool(
            "send_assessment",
            {"candidate_app_key": FakeLegacy.APP["app_key"]},
            FakeRequest(),
            {},
            {},
            entitlement_scope,
        )
        assert_true(blocked_assessment["status"] == "module_disabled", "assessments disabled must block send_assessment before preflight/executor")
        blocked_batch = tool_call_orchestrator._execute_tool(
            "execute_candidate_batch",
            {"batch_action_type": "send_assessment", "candidate_app_keys": [FakeLegacy.APP["app_key"]]},
            FakeRequest(),
            {},
            {},
            entitlement_scope,
        )
        assert_true(blocked_batch["status"] == "module_disabled", "disabled assessment module must block assessment batch items")
        FakeLegacy.ENABLED_MODULES = {"pre_hiring", "assessments"}
        blocked_video = tool_call_orchestrator._execute_tool(
            "send_video_interview",
            {"candidate_app_key": FakeLegacy.APP["app_key"]},
            FakeRequest(),
            {},
            {},
            entitlement_scope,
        )
        assert_true(blocked_video["status"] == "module_disabled", "video_interviews disabled must block send_video_interview")
        viewer_denied = tool_call_orchestrator._execute_tool(
            "send_assessment",
            {"candidate_app_key": FakeLegacy.APP["app_key"]},
            FakeRequest(),
            {},
            {},
            {**entitlement_scope, "role_scope": "viewer", "permissions": ["prehire.read"]},
        )
        assert_true(viewer_denied["status"] == "permission_denied", "Viewer must not mutate even when modules are enabled")
        FakeLegacy.ENABLED_MODULES = {"pre_hiring", "assessments", "video_interviews"}
        allowed_entitlement = tool_call_orchestrator._require_tool_entitlements(
            "send_assessment",
            {"candidate_app_key": FakeLegacy.APP["app_key"]},
            action_registry.spec_for("send_assessment"),
            "assessment.manage",
            entitlement_scope,
        )
        assert_true(allowed_entitlement is None, "enabled module plus correct permission must pass entitlement gate")
    finally:
        FakeLegacy.ENABLED_MODULES = original_modules

    for name in (
        "rank_candidates",
        "candidate_cv_evaluation",
        "get_candidate_status",
        "shortlist_candidate",
        "hire_candidate",
        "reject_candidate",
        "send_email",
        "schedule_interview",
        "execute_candidate_workflow",
        "create_job_opening",
    ):
        assert_true(name in tool_index, f"tool schema must include {name}")
        spec = action_registry.spec_for(name)
        function_def = tool_index[name]["function"]
        assert_true(function_def["description"], f"{name} must have a description for GPT")
        properties = function_def["parameters"]["properties"]
        if spec.entity_type == "candidate":
            assert_true(
                "candidate_name" in properties and "candidate_app_key" in properties,
                f"{name} must accept candidate_name / candidate_app_key references",
            )
            assert_true(
                "app_key" not in function_def["parameters"]["required"],
                f"{name} must not require raw app_key in its tool schema; orchestrator resolves it",
            )
        if (isinstance(spec.requires_confirmation, bool) and spec.requires_confirmation) or callable(spec.requires_confirmation):
            if spec.preflight is not None:
                assert_true("PREFLIGHT-THEN-CONFIRM" in function_def["description"], f"{name} must surface PREFLIGHT-THEN-CONFIRM in its description for tool-use GPT")
            else:
                assert_true("SENSITIVE" in function_def["description"], f"{name} must surface SENSITIVE in its description for tool-use GPT")

    rank_tool = tool_index["rank_candidates"]["function"]
    rank_properties = rank_tool["parameters"]["properties"]
    assert_true("position" in rank_properties and isinstance(rank_properties["position"].get("enum"), list), "rank_candidates position must expose an enum from the live parameters_catalog")
    assert_true("SOCIAL_MEDIA_MANAGER" in rank_properties["position"]["enum"], "rank_candidates position enum must include real DB positions")
    assert_true("status" in rank_properties and "review_pending" in rank_properties["status"]["enum"], "rank_candidates status enum must include canonical statuses")
    assert_true("query" in rank_properties, "rank_candidates must offer a free-text query field for unmatched wording")

    resolved = action_registry.resolve_candidate_reference(FakeLegacy(), {"candidate_name": "Hamad Almulla"})
    assert_true(resolved is not None and resolved.get("app_key") == FakeLegacy.APP["app_key"], "candidate reference must resolve from name to app_key")

    resolved_email = action_registry.resolve_candidate_reference(FakeLegacy(), {"candidate_email": FakeLegacy.APP["candidate_email"]})
    assert_true(resolved_email is not None and resolved_email.get("app_key") == FakeLegacy.APP["app_key"], "candidate reference must resolve from email to app_key")

    resolved_key = action_registry.resolve_candidate_reference(FakeLegacy(), {"candidate_app_key": FakeLegacy.APP["app_key"]})
    assert_true(resolved_key is not None and resolved_key.get("app_key") == FakeLegacy.APP["app_key"], "candidate reference must resolve directly from app_key when provided")

    no_resolve = action_registry.resolve_candidate_reference(FakeLegacy(), {"candidate_name": "Nobody Ever"})
    assert_true(no_resolve is None, "candidate reference resolver must return None when nothing matches")

    typed_resolved = action_registry.resolve_candidate_typed(FakeLegacy(), {"candidate_name": "Hamad Almulla"})
    assert_true(typed_resolved["status"] == "resolved" and typed_resolved["matches"], "typed resolver returns 'resolved' for a single match")

    typed_faisal = action_registry.resolve_candidate_typed(FakeLegacy(), {"candidate_name": "Faisal Almulla"})
    assert_true(typed_faisal["status"] == "resolved" and typed_faisal["matches"][0]["app_key"] == FakeLegacy.APP_FAISAL["app_key"], "typed resolver resolves Faisal Almulla via the new fuzzy resolver")

    typed_ambiguous = action_registry.resolve_candidate_typed(FakeLegacy(), {"candidate_name": "Almulla"})
    assert_true(typed_ambiguous["status"] == "ambiguous" and len(typed_ambiguous["matches"]) >= 2, "typed resolver flags surname-only queries with multiple matches as ambiguous, not auto-pick")

    typed_not_found = action_registry.resolve_candidate_typed(FakeLegacy(), {"candidate_name": "Mohammed AlNobody"})
    assert_true(typed_not_found["status"] == "not_found", "typed resolver returns 'not_found' when nothing matches a provided name")

    typed_no_input = action_registry.resolve_candidate_typed(FakeLegacy(), {})
    assert_true(typed_no_input["status"] == "no_input", "typed resolver returns 'no_input' when caller gave no identifying info")

    for phrase in ("candidate_not_found", "candidate_ambiguous", "needs_candidate_reference", "Do NOT keep asking"):
        assert_true(phrase in toolcall_source, f"tool-call orchestrator must surface {phrase!r} to GPT")
    for prompt_phrase in ("candidate_not_found", "candidate_ambiguous", "needs_candidate_reference"):
        assert_true(prompt_phrase in toolcall_source, f"toolcall system prompt must teach GPT how to handle the {prompt_phrase} tool state")

    workflow_tool = tool_index["execute_candidate_workflow"]["function"]
    workflow_props = workflow_tool["parameters"]["properties"]
    assert_true("steps" in workflow_props and workflow_props["steps"]["type"] == "array", "workflow tool must expose ordered registry steps as an array")
    assert_true("send_interview_invite" in workflow_props["steps"]["items"]["enum"], "workflow tool must expose canonical interview invite step")
    assert_true("datetime_text" in workflow_props and "allow_fallback" in workflow_props, "workflow tool must expose missing-time and fallback controls")
    assert_true("PREFLIGHT-THEN-CONFIRM" in workflow_tool["description"], "workflow tool schema must allow preflight before confirmation")
    assert_true("execute_candidate_workflow once" in toolcall_source, "tool-call prompt must tell GPT to use one workflow tool for multi-step candidate operations")
    assert_true("spec.preflight" in toolcall_source, "tool-call executor must run preflight before asking for sensitive workflow confirmation")
    assert_true("_handle_pending_confirmation_if_any" in toolcall_source and "pending_confirmation_resumed_by_backend" in toolcall_source, "backend must resume approved pending workflows without asking GPT to re-plan")
    assert_true("_forced_tool_for_turn" in toolcall_source and "execute_candidate_workflow" in toolcall_source, "candidate mutation/workflow turns must force workflow preflight instead of direct replies")
    screening_request = FakeRequest()
    screening_request.raw_text = "Show candidates who are screening complete"
    assert_true(
        tool_call_orchestrator._forced_tool_for_turn(screening_request, tools) == "rank_candidates",
        "exact screening-complete list request must force rank_candidates, not execute_candidate_workflow",
    )
    assert_true(
        tool_call_orchestrator._looks_like_candidate_list_request("Show candidates who are screening complete"),
        "exact screening-complete phrase must be recognized as a read/list request",
    )
    invite_status_request = FakeRequest()
    invite_status_request.raw_text = "did u notify him or"
    assert_true(
        tool_call_orchestrator._forced_tool_for_turn(invite_status_request, tools) == "get_interview_invite_status",
        "interview notification status questions must check interview/outbound truth instead of starting notification workflow",
    )
    invite_reply = tool_call_orchestrator._reply_for_tool_result(
        "execute_candidate_workflow",
        {
            "status": "completed",
            "result": {
                "status": "completed",
                "candidate": {"candidate_name": "Hamad Almulla"},
                "completed_steps": ["send_interview_invite"],
                "step_results": [
                    {
                        "step": "send_interview_invite",
                        "result": {
                            "status": "completed",
                            "message": "Interview invite sent to Hamad Almulla by email.",
                            "notification_channel": "email",
                        },
                    }
                ],
            },
        },
    )
    assert_true("send interview invite" not in invite_reply.lower(), "workflow reply must not leak raw send_interview_invite action name")
    assert_true("interview invite sent" in invite_reply.lower() and "email" in invite_reply.lower(), "workflow reply must use human-facing interview invite wording")
    failed_invite_reply = tool_call_orchestrator._reply_for_tool_result(
        "execute_candidate_workflow",
        {
            "status": "partial",
            "result": {
                "status": "partial",
                "candidate": {"candidate_name": "Hamad Almulla"},
                "completed_steps": [],
                "failed_steps": [
                    {
                        "step": "send_interview_invite",
                        "result": {
                            "status": "failed",
                            "safe_user_message": "I couldn't send Hamad's interview invite. Email needs reconnecting. WhatsApp conversation is not active.",
                        },
                    }
                ],
            },
        },
    )
    assert_true("0 step" not in failed_invite_reply.lower(), "workflow failure reply must not say completed 0 steps")
    assert_true("email needs reconnecting" in failed_invite_reply.lower(), "workflow failure reply must surface Gmail auth failure")
    assert_true("whatsapp conversation is not active" in failed_invite_reply.lower(), "workflow failure reply must surface WhatsApp conversation failure")
    invite_tool = tool_index["send_interview_invite"]["function"]
    assert_true("candidate_interviews" in invite_tool["description"], "interview invite tool must use candidate_interviews as source of truth")
    video_steps = action_registry._workflow_steps_from_action({"workflow_goal": "send Hamad an AI video interview"})
    assert_true(video_steps == ["send_video_interview"], "AI video interview wording must route to send_video_interview")
    video_link_steps = action_registry._workflow_steps_from_action({"workflow_goal": "send Hamad a video interview link"})
    assert_true(video_link_steps == ["send_video_interview"], "video interview link wording must route to send_video_interview")
    no_schedule_ctx = action_registry.ExecutionContext(
        request=FakeRequest(),
        action={"action_type": "execute_candidate_workflow", "app_key": FakeLegacy.APP["app_key"], "subject_name": "Hamad Almulla", "workflow_goal": "send Hamad an interview link", "prompt_text": "send Hamad an interview link"},
        state={},
        graph_state={},
        intent={},
        legacy=FakeLegacy(),
    )
    no_schedule_plan = action_registry._candidate_workflow_plan(no_schedule_ctx)
    assert_true(no_schedule_plan["status"] == "needs_clarification", "interview link with no exact app scheduled interview must ask/offer AI video instead")
    assert_true("AI video interview link" in no_schedule_plan["message"], "no scheduled interview message must offer AI video interview link")
    original_latest = FakeLegacy.latest_candidate_interview_for_app
    FakeLegacy.latest_candidate_interview_for_app = staticmethod(lambda app_key, company_code: {"interview_id": "int-1", "app_key": app_key, "company_code": company_code, "candidate_name": "Hamad Almulla", "status": "scheduled"} if app_key == FakeLegacy.APP["app_key"] else None)
    scheduled_plan = action_registry._candidate_workflow_plan(no_schedule_ctx)
    FakeLegacy.latest_candidate_interview_for_app = original_latest
    assert_true(scheduled_plan["status"] == "ready" and scheduled_plan["steps"] == ["send_interview_invite"], "scheduled interview invite should be ready only when exact app_key has an interview")
    status_tool = tool_index["get_interview_invite_status"]["function"]
    assert_true("outbound_delivery_events" in status_tool["description"], "invite status tool must read outbound delivery events")
    job_tool = tool_index["create_job_opening"]["function"]
    job_props = job_tool["parameters"]["properties"]
    assert_true("title" in job_props and "salary" in job_props, "create_job_opening must expose title and salary fields")
    assert_true("PREFLIGHT-THEN-CONFIRM" in job_tool["description"], "create_job_opening must be preflighted before confirmation")
    assert_true("JOB_OPENING_TRIGGER_RE" in toolcall_source and "create_job_opening" in toolcall_source, "job opening requests must force create_job_opening preflight")
    assert_true("LIST_JOB_OPENINGS_RE" in toolcall_source and "list_job_openings" in toolcall_source, "list job openings must be forced for inventory asks")
    assert_true("list_job_openings" in tool_index, "list_job_openings must be in the tool catalog")
    assert_true(tool_call_orchestrator.TOOL_PERMISSION_MAP.get("list_job_openings") == "jobs.read", "list_job_openings is a jobs.read tool")

    for scoped_phrase in (
        "memory_scope",
        "company_id",
        "admin_user_id",
        "conversation_id",
        "module",
        "session_id",
        "workflow_id",
        "same_company_admin_conversation_channel_module_session_only",
        "TERMINAL_FAILURE_STATUSES",
        "action_hash",
        "current_focus_by_module",
    ):
        assert_true(scoped_phrase in toolcall_source, f"tool-call orchestrator must include enterprise-scoped memory field {scoped_phrase!r}")

    request_a = FakeRequest()
    request_a.account_id = "company-a"
    request_a.conversation_id = "conversation-1"
    request_a.sender_phone = "+96511111111"
    scope_a = tool_call_orchestrator._base_memory_scope(request_a)
    request_b = FakeRequest()
    request_b.account_id = "company-a"
    request_b.conversation_id = "conversation-1"
    request_b.sender_phone = "+96522222222"
    scope_b = tool_call_orchestrator._base_memory_scope(request_b)
    assert_true(scope_a["admin_user_id"] != scope_b["admin_user_id"], "two admins in the same company/conversation must get separate memory scopes")
    assert_true(scope_a["module"] == "pre_hiring", "tool-call orchestrator is currently scoped to the pre_hiring module")
    assert_true(not tool_call_orchestrator._scope_matches({**scope_a, "session_id": "a"}, {**scope_b, "session_id": "a"}), "cross-admin memory scopes must not match")
    assert_true(not tool_call_orchestrator._scope_matches({**scope_a, "module": "payroll", "session_id": "a"}, {**scope_a, "session_id": "a"}), "cross-module memory scopes must not match")
    assert_true(tool_call_orchestrator._is_fresh_session_opener("good wbu"), "casual check-ins should start a fresh scoped session")
    assert_true(not tool_call_orchestrator._is_fresh_session_opener("is Faisal good for Instagram marketing?"), "operational candidate turns must not reset the active session")

    for language_phrase in (
        "Language policy is based on the user's CURRENT message only",
        "reply only in Latin characters",
        "Do NOT switch into Arabic script",
        "Do not infer reply language from WhatsApp profile name",
    ):
        assert_true(language_phrase in toolcall_source, f"tool-call prompt must enforce strict current-message language policy: {language_phrase!r}")

    for required_phrase in (
        "Wathefni HR",
        "answer directly with no tool call",
        "state_summary",
        "SENSITIVE",
        "Never invent",
        "WhatsApp-short",
    ):
        assert_true(required_phrase in toolcall_source, f"toolcall system prompt must include the rule: {required_phrase!r}")

    assert_true("MAX_TOOL_LOOPS" in toolcall_source and "tool_choice" in toolcall_source, "tool-use loop must bound iterations and request tool_choice")
    assert_true("openai-responses" in toolcall_source or "/responses" in toolcall_source, "tool-use orchestrator must use the OpenAI Responses API")
    assert_true("reasoning" in toolcall_source and "function_call_output" in toolcall_source, "Responses tool loop must pass reasoning effort and function_call_output")
    assert_true("strict" in toolcall_source and "_convert_tools_for_responses" in toolcall_source, "Responses tools must use strict schemas")
    assert_true("reasoning_content_logged" in toolcall_source, "telemetry must explicitly avoid logging hidden reasoning content")
    assert_true("needs_confirmation" in toolcall_source, "tool-use orchestrator must implement a confirmation gate")
    assert_true("handle_toolcall_whatsapp_turn" in toolcall_source, "tool-use orchestrator must expose handle_toolcall_whatsapp_turn entry point")
    assert_true("_save_pending" in toolcall_source and "_resolve_pending_match" in toolcall_source, "tool-use orchestrator must persist pending confirmations across turns")

    # Responses payload shaping unit checks (no network).
    body = tool_call_orchestrator._provider_responses_body(
        instructions="sys",
        input_items=[{"role": "user", "content": "hi"}],
        tools=[{"type": "function", "name": "list_job_openings", "description": "x", "parameters": {"type": "object", "properties": {}}, "strict": True}],
        provider={"model": "gpt-5.6-terra"},
        reasoning_effort="low",
        forced_tool_name="list_job_openings",
    )
    assert_true(body.get("model") == "gpt-5.6-terra", "Responses body must pin gpt-5.6-terra when provider says so")
    assert_true(body.get("reasoning") == {"effort": "low"}, "Responses body must set reasoning.effort")
    assert_true("temperature" not in body, "Responses body must not set custom temperature")
    assert_true(body.get("tool_choice") == {"type": "function", "name": "list_job_openings"}, "forced tool_choice must use Responses shape")
    assert_true(body.get("parallel_tool_calls") is False, "parallel tool calls must stay disabled")
    strict_tools = tool_call_orchestrator._convert_tools_for_responses(
        [{"type": "function", "function": {"name": "list_job_openings", "description": "List jobs", "parameters": {"type": "object", "properties": {"status": {"type": "string"}}, "required": [], "additionalProperties": True}}}]
    )
    assert_true(strict_tools and strict_tools[0].get("strict") is True, "converted tools must be strict")
    assert_true(strict_tools[0]["parameters"].get("additionalProperties") is False, "strict tools must forbid additionalProperties")
    assert_true("status" in (strict_tools[0]["parameters"].get("required") or []), "strict tools must require all properties")

    print("toolcall orchestrator smoke tests passed")


if __name__ == "__main__":
    main()
