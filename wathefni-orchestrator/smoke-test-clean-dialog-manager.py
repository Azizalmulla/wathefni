#!/usr/bin/env python3
"""Smoke tests for the clean Wathefni dialog-manager contract."""

from pathlib import Path
import tempfile

import app


def assert_true(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def main() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    channel_path = repo_root / "plugins" / "octopus-channel" / "octopus-channel.ts"
    if not channel_path.exists():
        channel_path = Path("/root/.openclaw/extensions/octopus-channel.ts")
    webhook_path = repo_root / "ai-recruiter" / "app" / "routers" / "webhook.py"
    channel_source = channel_path.read_text(encoding="utf-8")
    webhook_source = webhook_path.read_text(encoding="utf-8") if webhook_path.exists() else "wathefni_hr_orchestrator_url"

    assert_true("orchestratorOwnsHrDialog" in channel_source, "Wathefni HR channel must name the orchestrator ownership gate")
    assert_true("!orchestratorOwnsHrDialog" in channel_source, "Local Octopus pending state must be gated away from Wathefni HR")
    if webhook_path.exists():
        assert_true("handle_hr_query" not in webhook_source, "Meta HR webhook must not call the legacy HR engine")
        assert_true("wathefni_hr_orchestrator_url" in webhook_source, "Meta HR webhook must forward to the orchestrator")

    assert_true(app.LEGACY_REGEX_INFERENCE_ENABLED is False, "Legacy regex inference should be opt-in")
    assert_true(app.action_requires_confirmation("hire_candidate"), "Hiring must require confirmation")
    assert_true(app.action_requires_confirmation("reject_candidate"), "Rejection must require confirmation")
    assert_true(app.action_requires_confirmation("export_payroll"), "Payroll export must require confirmation")
    assert_true(not app.action_requires_confirmation("list_payroll_hours"), "Read-only payroll checks should not require confirmation")

    pending = {
        "kind": "resolve_ambiguous_compare_target",
        "attempt_count": 1,
        "original_proposal": {"capability": "compare_evaluate"},
        "options": [{"candidate_name": "Ahmed", "app_key": "a1"}],
    }
    request = app.WhatsAppTurnRequest(sender_phone="+96590000000", sender_role="hr_admin", raw_text="not that")
    decision = app.resolve_pending_compare_clarification(request, {}, pending)
    assert_true((decision.get("validation") or {}).get("reason") == "clarification_attempts_exceeded", "Clarification must stop after two failed attempts")
    assert_true("show or rank candidates" in decision.get("reply", ""), "Clarification limit should offer a short capability menu")

    original_workspace = app.WORKSPACE
    try:
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            (workspace / "IDENTITY.md").write_text("# Identity\nWathefni identity.\n", encoding="utf-8")
            (workspace / "SOUL.md").write_text("# Soul\nWarm tone.\n", encoding="utf-8")
            (workspace / "SKILL.md").write_text("# Skills\nBackend truth and ActionResult only.\n", encoding="utf-8")
            (workspace / "TOOLS.md").write_text(
                "# Tools\nPayroll truth uses ActionResult.\n\n\n\n\n\n\n\n\n\n\n\nSECRET_FULL_DOC_MARKER should not be injected.\n",
                encoding="utf-8",
            )
            app.WORKSPACE = workspace
            augmented = app.openclaw_augmented_system_prompt(app.PLANNER_BASE_SYSTEM, prompt_name="planner")
            assert_true("OPENCLAW_RUNTIME_CONTEXT:planner" in augmented, "Planner prompt must still receive runtime context")
            assert_true("SECRET_FULL_DOC_MARKER" not in augmented, "Prompt context should be selective, not full-file injection")
    finally:
        app.WORKSPACE = original_workspace

    original_resolver = app.resolve_candidate_reference_from_text
    original_focus = app.candidate_focus_from_app
    try:
        fake_app = {"app_key": "app-1", "candidate_name": "Foad Aziz", "phone": "96590000000"}
        app.resolve_candidate_reference_from_text = lambda text, company_code=None: {"status": "resolved", "application": fake_app}
        app.candidate_focus_from_app = lambda found, source_action, confidence="resolved": {
            "entity_type": "candidate",
            "key": found["app_key"],
            "display_name": found["candidate_name"],
            "expires_at": app.operational_context_timestamp(30),
        }
        vague = app.WhatsAppTurnRequest(sender_phone="+96590000000", sender_role="hr_admin", raw_text="Foad Aziz can start Sunday")
        explicit = app.WhatsAppTurnRequest(sender_phone="+96590000000", sender_role="hr_admin", raw_text="tell me about Foad Aziz")
        assert_true(app.candidate_focus_context(vague, {}) is None, "Candidate focus must not steal unrelated named intents")
        assert_true(app.candidate_focus_context(explicit, {}) is not None, "Explicit candidate detail requests should still set focus")
    finally:
        app.resolve_candidate_reference_from_text = original_resolver
        app.candidate_focus_from_app = original_focus

    assert_true(app.detect_user_language("shlon payroll today?") == "ar", "Arabizi should route to Arabic replies")
    assert_true("recent_assistant_replies" in Path(app.__file__).read_text(encoding="utf-8"), "Renderer must receive recent replies for variation")


if __name__ == "__main__":
    main()
