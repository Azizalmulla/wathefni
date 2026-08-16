"""HR Mobile Assistant — multi-tenant / module / RBAC / channel contracts."""

from __future__ import annotations

import inspect

import operator_mobile as om
import operator_mobile_assistant as oma


class _App:
    ASSISTANT_OFFERABLE_MODULES = frozenset(
        {
            "pre_hiring",
            "leave",
            "attendance",
            "onboarding",
            "shifts",
            "payroll",
            "compliance",
            "calendar",
            "employment_offers",
            "assessments",
            "interviews",
            "video_interviews",
            "analytics",
        }
    )
    ASSISTANT_OFFERABLE_PERMISSIONS = frozenset(
        {"prehire.read", "leave.read", "attendance.read", "employees.read", "*:*"}
    )

    def __init__(self, modules=None):
        self._modules = set(modules or set())

    def configured_company_modules(self, company_code):
        return set(self._modules)

    def company_has_module(self, company_code, module_key):
        return module_key in self._modules

    def context_permissions(self, context):
        return set(context.get("permissions") or [])

    def digits(self, value):
        return "".join(ch for ch in str(value or "") if ch.isdigit())


def test_offerable_requires_module_and_permission():
    app = _App(modules={"pre_hiring"})
    ctx_ok = {"company_code": "ACME", "permissions": ["prehire.read"]}
    assert oma.assistant_mobile_offerable(app, ctx_ok) is True

    ctx_no_perm = {"company_code": "ACME", "permissions": ["users.read"]}
    assert oma.assistant_mobile_offerable(app, ctx_no_perm) is False

    app_empty = _App(modules=set())
    assert oma.assistant_mobile_offerable(app_empty, ctx_ok) is False


def test_tenant_isolation_company_required():
    app = _App(modules={"leave"})
    assert oma.assistant_mobile_offerable(app, {"company_code": "", "permissions": ["leave.read"]}) is False
    assert oma.assistant_mobile_offerable(app, {"permissions": ["leave.read"]}) is False


def test_leave_only_tenant_offerable_with_leave_read():
    app = _App(modules={"leave"})
    assert oma.assistant_mobile_offerable(app, {"company_code": "LEAVECO", "permissions": ["leave.read"]}) is True
    # Module on + non-offerable permission → denied
    assert oma.assistant_mobile_offerable(app, {"company_code": "LEAVECO", "permissions": ["users.read"]}) is False
    # Permission alone without module → denied
    app_none = _App(modules=set())
    assert oma.assistant_mobile_offerable(app_none, {"company_code": "LEAVECO", "permissions": ["leave.read"]}) is False


def test_hr_capability_includes_assistant_and_manager_scope_blocks():
    src = inspect.getsource(om.build_hr_workspace_capabilities)
    assert '"assistant"' in src
    assert "assistant_mobile_offerable" in src
    # Manager fail-closed list includes assistant
    assert "assistant" in src


def test_routes_registered_under_mobile_prefix():
    src = inspect.getsource(oma.register_mobile_assistant_routes)
    assert "/dashboard/mobile/assistant/capabilities" in src
    assert "/dashboard/mobile/assistant/chat" in src
    assert "/dashboard/mobile/assistant/chat/stream" in src
    turn = inspect.getsource(oma._run_mobile_assistant_turn)
    assert "hr_mobile" in turn
    assert "web_dashboard" not in turn
    assert "ai-recruiter" not in src.lower()
    assert "ai_recruiter" not in src.lower()


def test_confirm_maps_to_affirmative_token():
    src = inspect.getsource(oma._run_mobile_assistant_turn)
    assert "__confirm__" in src
    assert "نعم" in src
    assert "yes" in src


def test_capabilities_mark_unsupported_messaging():
    src = inspect.getsource(oma.register_mobile_assistant_routes)
    assert "sms" in src and "telegram" in src and "teams_chat" in src and "push_send" in src
    assert 'payload["surface"] = "hr_mobile"' in src


def test_reply_stream_chunks_preserves_text():
    chunks = oma._reply_stream_chunks("one two three four five six seven eight", words_per_chunk=3)
    assert "".join(chunks) == "one two three four five six seven eight"
    assert len(chunks) >= 2


def test_operator_mobile_wires_register():
    src = inspect.getsource(om.register_operator_mobile_routes)
    assert "register_mobile_assistant_routes" in src
    assert "operator_mobile_assistant" in src
