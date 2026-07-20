#!/usr/bin/env python3
"""Pre-Hiring Assistant channel parity smokes.

Proves WhatsApp HR toolcall scope hydrates backend_current authority like
dashboard chat, list_job_openings routes correctly, and entitlements no longer
false-deny owners who already hold prehire.read.
"""

from __future__ import annotations

import importlib
import sys
import types
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def assert_true(cond: bool, message: str) -> None:
    if not cond:
        raise AssertionError(message)


class FakeRequest:
    def __init__(self, **kwargs):
        self.account_id = kwargs.get("account_id", "default")
        self.conversation_id = kwargs.get("conversation_id", "conv-1")
        self.sender_phone = kwargs.get("sender_phone", "96599338566")
        self.sender_role = kwargs.get("sender_role", "hr_admin")
        self.raw_text = kwargs.get("raw_text", "")
        self.metadata = kwargs.get("metadata") or {}


def main() -> None:
    import action_registry
    import tool_call_orchestrator as tco

    # --- Forced routing ---
    tools = [{"function": {"name": "list_job_openings"}}, {"function": {"name": "create_job_opening"}}, {"function": {"name": "rank_candidates"}}]
    list_req = FakeRequest(raw_text="Hello what job openings do we have open")
    assert_true(
        tco._forced_tool_for_turn(list_req, tools) == "list_job_openings",
        "open-jobs phrasing must force list_job_openings",
    )
    assert_true(
        tco._looks_like_list_job_openings_request("show open positions"),
        "show open positions is a list request",
    )
    assert_true(
        not tco._looks_like_list_job_openings_request("create a new marketing job"),
        "create phrasing must not force list",
    )
    create_req = FakeRequest(raw_text="create a new marketing job with salary 800")
    assert_true(
        tco._forced_tool_for_turn(create_req, tools) == "create_job_opening",
        "create phrasing must still force create_job_opening",
    )
    assert_true(
        tco._forced_tool_for_turn(FakeRequest(raw_text="open a new sales role"), tools) == "create_job_opening",
        "open a new role must force create, not list",
    )

    # --- Registry presence ---
    spec = action_registry.spec_for("list_job_openings")
    assert_true(spec is not None and spec.module == "pre_hiring", "list_job_openings registered under pre_hiring")
    assert_true(tco.TOOL_PERMISSION_MAP.get("list_job_openings") == "prehire.read", "list_job_openings requires prehire.read")
    assert_true("list_job_openings" in tco.TOOLCALL_SYSTEM, "system prompt must mention list_job_openings")

    # --- Scope authority parity ---
    owner_perms = [
        "prehire.read",
        "candidate.manage",
        "settings.manage",
        "assessment.manage",
    ]
    linked = {
        "company_code": "WATHEFNI",
        "actor_user_id": "88b17ca9-aff4-4721-a553-c1b5514ef95f",
        "actor_email": "azizalmulla16@gmail.com",
        "actor_phone": "96599338566",
        "actor_role": "owner",
        "permissions": owner_perms,
        "permission_authority": "backend_current",
        "permission_subject_user_id": "88b17ca9-aff4-4721-a553-c1b5514ef95f",
        "permission_subject_company": "WATHEFNI",
        "status": "active",
    }

    class FakeLegacy:
        @staticmethod
        def digits(value):
            return "".join(ch for ch in str(value or "") if ch.isdigit())

        @staticmethod
        def request_company_code(request):
            return "WATHEFNI"

        @staticmethod
        def whatsapp_actor_context_for_phone(phone, company_code=None):
            if FakeLegacy.digits(phone) == "96599338566":
                return dict(linked)
            return None

        @staticmethod
        def require_entitlement(context, module_key, permission=None):
            # Delegate to real app.require_entitlement if available after patching.
            import app as app_mod

            return app_mod.require_entitlement(context, module_key, permission)

    real_legacy = tco._legacy
    tco._legacy = lambda: FakeLegacy  # type: ignore[assignment]
    try:
        wa_scope = tco._base_memory_scope(FakeRequest(sender_phone="96599338566"))
        assert_true(wa_scope.get("permission_authority") == "backend_current", "WhatsApp linked owner must get backend_current")
        assert_true(wa_scope.get("permission_subject_user_id") == linked["actor_user_id"], "subject user id must match actor")
        assert_true(wa_scope.get("permission_subject_company") == "WATHEFNI", "subject company must match")
        assert_true(isinstance(wa_scope.get("hr_user"), dict) and wa_scope["hr_user"].get("user_id") == linked["actor_user_id"], "hr_user must be hydrated")
        assert_true("prehire.read" in (wa_scope.get("permissions") or []), "permissions must include prehire.read")
        assert_true((wa_scope.get("access") or {}).get("permission_authority") == "backend_current", "nested access must carry authority")

        unlinked_scope = tco._base_memory_scope(FakeRequest(sender_phone="96500000000"))
        assert_true(not unlinked_scope.get("permission_authority"), "unlinked WhatsApp must not invent backend_current")

        # Soft allow + hard entitlement should both pass for owner
        allowed, required = tco._tool_allowed("list_job_openings", wa_scope)
        assert_true(allowed and required == "prehire.read", "owner soft-allow list_job_openings")
        allowed_rank, required_rank = tco._tool_allowed("rank_candidates", wa_scope)
        assert_true(allowed_rank and required_rank == "prehire.read", "owner soft-allow rank_candidates")

        # Entitlement context must preserve markers for require_entitlement
        ent = tco._entitlement_context(wa_scope)
        assert_true(ent.get("permission_authority") == "backend_current", "entitlement context authority")
        assert_true(ent.get("permission_subject_user_id") == linked["actor_user_id"], "entitlement subject")

        # Dashboard-shaped metadata path also preserves authority without phone actor
        dash_req = FakeRequest(
            sender_phone="96599338566",
            metadata={
                "channel": "web_dashboard",
                "dashboard": True,
                "company_code": "WATHEFNI",
                "admin_user": {
                    "user_id": linked["actor_user_id"],
                    "role": "owner",
                    "email": linked["actor_email"],
                    "phone": "96599338566",
                    "status": "active",
                    "permissions": owner_perms,
                    "company_code": "WATHEFNI",
                },
                "access": {
                    "role": "owner",
                    "permissions": owner_perms,
                    "permission_authority": "backend_current",
                    "permission_subject_user_id": linked["actor_user_id"],
                    "permission_subject_company": "WATHEFNI",
                },
                "permissions": owner_perms,
            },
        )
        dash_scope = tco._base_memory_scope(dash_req)
        assert_true(dash_scope.get("permission_authority") == "backend_current", "dashboard metadata scope must stay backend_current")
        assert_true(isinstance(dash_scope.get("hr_user"), dict), "dashboard admin_user becomes hr_user")
    finally:
        tco._legacy = real_legacy  # type: ignore[assignment]

    # --- list_job_openings executor uses positions authority query ---
    class PositionsLegacy:
        @staticmethod
        def json_safe(value):
            return value

        @staticmethod
        def digits(value):
            return "".join(ch for ch in str(value or "") if ch.isdigit())

        @staticmethod
        def now_iso():
            return "2026-07-20T00:00:00Z"

        @staticmethod
        def request_company_code(request):
            return "WATHEFNI"

        @staticmethod
        def _dashboard_prehire_positions_query(company, *, limit=200, offset=0, search=None, status=None):
            assert company == "WATHEFNI"
            assert status == "open"
            assert search is None
            rows = [
                {
                    "position_code": "FULLSTACK",
                    "position_title": "Full Stack Developer",
                    "apply_code": "APPLY-WATHEFNI-FULLSTACK",
                    "active_count": 2,
                    "application_count": 5,
                    "status": "open",
                }
            ]
            return rows, len(rows)

        @staticmethod
        def dashboard_prehire_positions_summary(company):
            return {"open_positions": 1, "total_positions": 1}

        @staticmethod
        def format_list_job_openings_reply(result):
            positions = result.get("positions") or []
            if not positions:
                return "No open job openings right now."
            item = positions[0]
            return f"Open roles (1):\n- {item['position_title']} — `{item['apply_code']}`"

    ctx = action_registry.ExecutionContext(
        request=FakeRequest(raw_text="what jobs are open"),
        action={"status": "open"},
        state={},
        graph_state={},
        intent={},
        legacy=PositionsLegacy(),
    )
    listed = action_registry._list_job_openings_executor(ctx)
    assert_true(listed.get("status") == "completed", "list_job_openings completes")
    assert_true(listed.get("total_matching") == 1, "list_job_openings returns payload rows")
    assert_true(listed.get("authority") == "positions", "list_job_openings uses positions authority")
    assert_true("Full Stack Developer" in str(listed.get("message") or ""), "list reply includes title")

    empty_ctx = action_registry.ExecutionContext(
        request=FakeRequest(),
        action={"status": "open"},
        state={},
        graph_state={},
        intent={},
        legacy=type(
            "EmptyLegacy",
            (),
            {
                "json_safe": staticmethod(lambda v: v),
                "digits": staticmethod(lambda v: "".join(ch for ch in str(v or "") if ch.isdigit())),
                "now_iso": staticmethod(lambda: "2026-07-20T00:00:00Z"),
                "request_company_code": staticmethod(lambda request: "WATHEFNI"),
                "_dashboard_prehire_positions_query": staticmethod(lambda *a, **k: ([], 0)),
                "dashboard_prehire_positions_summary": staticmethod(lambda *a, **k: {"open_positions": 0, "total_positions": 0}),
                "format_list_job_openings_reply": staticmethod(
                    lambda result: "No open job openings right now."
                    if not (result.get("positions") or [])
                    else "ok"
                ),
            },
        )(),
    )
    empty = action_registry._list_job_openings_executor(empty_ctx)
    assert_true("No open job openings" in str(empty.get("message") or ""), "empty open list copy")

    # --- Source contracts ---
    toolcall_source = Path(tco.__file__).read_text(encoding="utf-8")
    assert_true("LIST_JOB_OPENINGS_RE" in toolcall_source, "list openings regex present")
    assert_true("permission_authority" in toolcall_source and "backend_current" in toolcall_source, "scope hydration mentions backend_current")
    app_source = Path(ROOT / "app.py").read_text(encoding="utf-8")
    assert_true("def format_list_job_openings_reply" in app_source, "shared reply formatter exists on app")
    assert_true("status: str | None = None" in app_source or "status: str | None = None," in app_source or "status: str | None = None," in app_source.replace("\n", " "), "positions query accepts status filter")
    assert_true("effective_status" in app_source or "p.status" in app_source, "positions query filters via position status")
    mobile_source = Path(ROOT / "operator_mobile_data.py").read_text(encoding="utf-8")
    assert_true("/dashboard/mobile/positions" in mobile_source, "mobile positions route registered")
    registry_source = Path(ROOT / "action_registry.py").read_text(encoding="utf-8")
    assert_true("_dashboard_prehire_positions_query" in registry_source, "list tool uses positions authority query")
    assert_true("search_job_openings" in registry_source, "search_job_openings registered")

    print("smoke-test-prehire-assistant-parity: ALL CHECKS PASSED")


if __name__ == "__main__":
    main()
