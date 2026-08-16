"""P0 Setup→AI parity proofs: workspace auth, channel readiness, module/channel gating."""

from __future__ import annotations

import inspect

import assistant_capability_catalog as caps
import assistant_channel_readiness as acr
import tool_call_orchestrator as orch


class _Legacy:
    def __init__(self, modules=None, wa_candidate=True, wa_employee=False, email_ready=True):
        self._modules = set(modules or {"pre_hiring", "leave"})
        self._wa_candidate = wa_candidate
        self._wa_employee = wa_employee
        self._email_ready = email_ready

    def configured_company_modules(self, company_code):
        return set(self._modules)

    def company_has_module(self, company_code, module_key):
        return module_key in self._modules

    def setup_console_channel_policy(self, company_code):
        return {
            "pre_hiring": {"company_whatsapp": {"configured": self._wa_candidate}},
            "post_hiring": {
                "company_whatsapp": {"configured": self._wa_employee},
                "push": {"effective": False},
                "in_app_inbox": {"effective": False},
            },
        }

    def outbound_postmark_available(self):
        return bool(self._email_ready)

    def db_connect(self):
        raise RuntimeError("no db")

    def openclaw_env(self):
        return {}


def _tools(*names):
    return [{"type": "function", "function": {"name": name}} for name in names]


def test_channel_readiness_snapshot_and_unsupported_refuse():
    legacy = _Legacy(wa_candidate=True, email_ready=True)
    snap = acr.channel_readiness_snapshot(legacy, "ACME")
    assert snap["email"]["configured"] is True
    assert snap["whatsapp_candidate"]["configured"] is True
    assert "sms" in snap["unsupported_messaging"]
    assert "telegram" in snap["unsupported_messaging"]
    assert acr.refuse_unsupported_channel("sms")["error"] == "unsupported_channel"
    assert acr.refuse_unsupported_channel("telegram")["error"] == "unsupported_channel"
    assert acr.refuse_unsupported_channel("teams_chat")["error"] == "unsupported_channel"
    assert acr.refuse_unsupported_channel("email") is None
    assert acr.refuse_unsupported_channel("whatsapp") is None


def test_email_whatsapp_tools_hidden_when_unconfigured(monkeypatch):
    legacy = _Legacy(wa_candidate=False, email_ready=False)
    monkeypatch.setattr(orch, "_legacy", lambda: legacy)
    monkeypatch.setattr(orch, "TOOLCALL_GATED_MODULES", frozenset({"leave", "attendance"}))
    tools = _tools(
        "list_job_openings",
        "send_email",
        "notify_candidate",
        "send_screening_questions",
        "list_leave_requests",
    )
    scope = {"company_id": "ACME", "permissions": ["prehire.read", "candidate.manage", "leave.read"]}
    visible = {t["function"]["name"] for t in orch._visible_tools(tools, scope)}
    assert "list_job_openings" in visible
    assert "send_email" not in visible
    assert "notify_candidate" not in visible
    assert "send_screening_questions" not in visible


def test_email_whatsapp_tools_appear_when_configured(monkeypatch):
    legacy = _Legacy(wa_candidate=True, email_ready=True)
    monkeypatch.setattr(orch, "_legacy", lambda: legacy)
    tools = _tools("send_email", "notify_candidate", "list_job_openings")
    scope = {"company_id": "ACME", "permissions": ["candidate.manage", "prehire.read"]}
    visible = {t["function"]["name"] for t in orch._visible_tools(tools, scope)}
    assert "send_email" in visible
    assert "notify_candidate" in visible


def test_module_off_hides_leave_tools(monkeypatch):
    legacy = _Legacy(modules={"pre_hiring"}, wa_candidate=True, email_ready=True)
    monkeypatch.setattr(orch, "_legacy", lambda: legacy)
    tools = _tools("list_leave_requests", "approve_leave_request", "list_job_openings")
    scope = {"company_id": "LEAVELESS", "permissions": ["leave.read", "leave.decide", "prehire.read"]}
    visible = {t["function"]["name"] for t in orch._visible_tools(tools, scope)}
    assert "list_job_openings" in visible
    assert "list_leave_requests" not in visible
    assert "approve_leave_request" not in visible


def test_module_on_shows_leave_tools(monkeypatch):
    legacy = _Legacy(modules={"leave", "pre_hiring"}, wa_candidate=True, email_ready=True)
    monkeypatch.setattr(orch, "_legacy", lambda: legacy)
    tools = _tools("list_leave_requests", "approve_leave_request")
    scope = {"company_id": "LEAVECO", "permissions": ["leave.read", "leave.decide"]}
    visible = {t["function"]["name"] for t in orch._visible_tools(tools, scope)}
    assert "list_leave_requests" in visible
    assert "approve_leave_request" in visible


def test_permission_hides_leave_mutate(monkeypatch):
    legacy = _Legacy(modules={"leave"}, wa_candidate=False, email_ready=False)
    monkeypatch.setattr(orch, "_legacy", lambda: legacy)
    tools = _tools("list_leave_requests", "approve_leave_request")
    scope = {"company_id": "MGR", "permissions": ["leave.read"]}  # no leave.decide
    visible = {t["function"]["name"] for t in orch._visible_tools(tools, scope)}
    assert "list_leave_requests" in visible
    assert "approve_leave_request" not in visible


def test_catalog_marks_unconfigured_and_prompt_refuses_sms():
    legacy = _Legacy(wa_candidate=False, email_ready=False)
    # Force probes off even if env has Postmark on developer machine
    original_email = caps._email_configured
    original_wa = caps._whatsapp_configured
    caps._email_configured = lambda legacy, company=None: False
    caps._whatsapp_configured = lambda legacy, company=None: False
    try:
        catalog = caps.build_assistant_capability_catalog(
            legacy=legacy,
            company_code="ACME",
            permissions=["candidate.manage", "prehire.read"],
            visible_tools=_tools("send_email", "notify_candidate", "list_job_openings"),
        )
        # Tools may be absent from visible list in real path; when present, status not configured
        assert catalog["providers"]["whatsapp"] is False
        block = caps.capability_prompt_block(catalog)
        assert "SMS" in block or "sms" in block.lower()
        assert "Telegram" in block or "telegram" in block.lower()
        assert "Teams chat" in block or "teams chat" in block.lower()
    finally:
        caps._email_configured = original_email
        caps._whatsapp_configured = original_wa


def test_assistant_dashboard_context_exists_and_chat_routes_use_it():
    import app as app_mod

    assert hasattr(app_mod, "assistant_dashboard_context")
    src = inspect.getsource(app_mod)
    assert "def assistant_dashboard_context" in src
    # Chat/capabilities must not use prehire-only Depends
    for marker in (
        'assistant/capabilities"',
        "/dashboard/prehire/chat/sessions\"",
        "def dashboard_prehire_chat(",
        "def dashboard_prehire_chat_stream(",
        "def dashboard_prehire_chat_new_session(",
    ):
        idx = src.find(marker)
        assert idx > 0, marker
        window = src[idx : idx + 500]
        assert "Depends(assistant_dashboard_context)" in window, marker
        assert "Depends(prehire_dashboard_context)" not in window, marker


def test_assistant_access_constants_cover_posthire():
    import app as app_mod

    assert "leave" in app_mod.ASSISTANT_OFFERABLE_MODULES
    assert "pre_hiring" in app_mod.ASSISTANT_OFFERABLE_MODULES
    assert "leave.read" in app_mod.ASSISTANT_OFFERABLE_PERMISSIONS


def test_notify_candidate_passes_company_routing():
    import app as app_mod

    src = inspect.getsource(app_mod.notify_candidate)
    assert "company_code=company" in src or "company_code=company or None" in src
    assert 'audience="candidate"' in src
    assert "whatsapp_candidate_ready" in src or "whatsapp_not_configured" in src


def test_multi_tenant_matrix(monkeypatch):
    """Synthetic companies: enable/disable modules + channels → tool visibility."""

    cases = [
        {
            "company": "PREONLY",
            "modules": {"pre_hiring"},
            "wa": True,
            "email": True,
            "perms": ["prehire.read", "candidate.manage"],
            "expect": {"list_job_openings", "send_email", "notify_candidate"},
            "forbid": {"list_leave_requests", "list_attendance"},
        },
        {
            "company": "LEAVEONLY",
            "modules": {"leave"},
            "wa": False,
            "email": False,
            "perms": ["leave.read", "leave.decide"],
            "expect": {"list_leave_requests", "approve_leave_request"},
            "forbid": {"send_email", "notify_candidate", "list_job_openings"},
        },
        {
            "company": "ATTEND",
            "modules": {"attendance", "leave"},
            "wa": False,
            "email": True,
            "perms": ["attendance.read", "leave.read"],
            "expect": {"list_attendance", "list_leave_requests"},
            "forbid": {"approve_leave_request", "notify_candidate"},
        },
        {
            "company": "NOWA",
            "modules": {"pre_hiring"},
            "wa": False,
            "email": True,
            "perms": ["candidate.manage", "prehire.read"],
            "expect": {"send_email", "list_job_openings"},
            "forbid": {"notify_candidate"},
        },
    ]
    all_tools = _tools(
        "list_job_openings",
        "send_email",
        "notify_candidate",
        "list_leave_requests",
        "approve_leave_request",
        "list_attendance",
    )
    for case in cases:
        legacy = _Legacy(
            modules=case["modules"],
            wa_candidate=case["wa"],
            email_ready=case["email"],
        )
        monkeypatch.setattr(orch, "_legacy", lambda legacy=legacy: legacy)
        visible = {
            t["function"]["name"]
            for t in orch._visible_tools(
                all_tools,
                {"company_id": case["company"], "permissions": case["perms"]},
            )
        }
        for name in case["expect"]:
            assert name in visible, f"{case['company']} missing {name}: {visible}"
        for name in case["forbid"]:
            assert name not in visible, f"{case['company']} should hide {name}: {visible}"
