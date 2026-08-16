"""Workflow preview / partial-failure contract tests for Assistant."""

from __future__ import annotations

from types import SimpleNamespace

import action_registry as registry


class _Legacy:
    def json_safe(self, value):
        return value

    def candidate_contact(self, app):
        return {"name": app.get("name") or "Sara", "email": app.get("email"), "phone": "965000"}

    def candidate_lookup_match_payload(self, app):
        return {"candidate_name": app.get("name") or "Sara", "app_key": app.get("app_key")}


def _ctx(action, app=None):
    app = app or {"app_key": "APP1", "company_code": "WATHEFNI", "name": "Sara", "email": "sara@example.com"}

    class Ctx:
        request = SimpleNamespace(sender_phone="965111", metadata={"dashboard": True, "permissions": ["candidate.manage"]})
        state = {}
        graph_state = {}
        intent = {}
        legacy = _Legacy()

    ctx = Ctx()
    ctx.action = {**action, "app_key": app["app_key"]}
    # Patch resolve
    original = registry._resolve_app
    registry._resolve_app = lambda _ctx: app
    ctx._restore = lambda: setattr(registry, "_resolve_app", original)
    return ctx


def test_workflow_preflight_includes_workflow_card():
    ctx = _ctx(
        {
            "action_type": "execute_candidate_workflow",
            "workflow_goal": "schedule and notify",
            "steps": ["schedule_interview", "notify_candidate"],
            "datetime_text": "tomorrow at 4pm",
            "invite_channel": "whatsapp",
        }
    )
    try:
        plan = registry._candidate_workflow_plan(ctx)
        assert plan.get("status") == "ready"
        card = plan.get("workflow_card") or {}
        assert card.get("kind") == "workflow_preview"
        assert [s["step"] for s in card.get("steps") or []] == ["schedule_interview", "notify_candidate"]
        assert card.get("people")
    finally:
        ctx._restore()


def test_workflow_partial_does_not_claim_full_success(monkeypatch):
    ctx = _ctx(
        {
            "action_type": "execute_candidate_workflow",
            "steps": ["shortlist_candidate", "send_email"],
            "idempotency_key": "wf-test-1",
        }
    )

    calls = []

    def fake_execute(step, atomic_ctx):
        calls.append(step)
        if step == "shortlist_candidate":
            return {"action_type": step, "success": True, "status": "completed", "message": "shortlisted"}
        return {"action_type": step, "success": False, "status": "failed", "error": "email_failed", "message": "email failed"}

    monkeypatch.setattr(registry, "execute", fake_execute)
    monkeypatch.setattr(registry, "_candidate_workflow_plan", lambda _ctx: {
        "status": "ready",
        "steps": ["shortlist_candidate", "send_email"],
        "candidate": {"candidate_name": "Sara"},
        "invite_channel": "email",
        "datetime_text": None,
        "meeting_type": None,
    })
    monkeypatch.setattr(registry, "_workflow_order_steps", lambda steps: list(steps))
    monkeypatch.setattr(registry, "_prior_workflow_artifacts", lambda *_a, **_k: {})
    monkeypatch.setattr(registry, "_workflow_interview_fields", lambda *_a, **_k: {})
    monkeypatch.setattr(registry, "_workflow_communication_message", lambda *_a, **_k: "hi")
    monkeypatch.setattr(registry, "_candidate_name", lambda *_a, **_k: "Sara")

    try:
        result = registry._execute_candidate_workflow_executor(ctx)
        assert result["success"] is False
        assert result["status"] == "partial"
        assert "not claiming the whole workflow succeeded" in result["message"].lower() or "needs attention" in result["message"].lower()
        assert result["completed_steps"] == ["shortlist_candidate"]
        assert result["compensation_state"]["retry_step"] == "send_email"
        assert result["workflow_card"]["status"] == "partial"
        assert result["idempotency_key"]
        assert calls == ["shortlist_candidate", "send_email"]
    finally:
        ctx._restore()
