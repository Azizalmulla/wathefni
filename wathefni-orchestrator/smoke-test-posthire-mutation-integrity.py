#!/usr/bin/env python3
"""Post-hire mutation integrity — assistant kill must not block dashboard actions.

Proves:
  * WATHEFNI_ASSISTANT_MUTATIONS=0 still denies assistant/WhatsApp-channel mutations
  * web_dashboard channel (native Onboarding / Leave / Attendance / Shifts buttons)
    is NOT denied by the assistant mutation kill
  * compliance reminder/mark tools are not kill-classified (documented)
  * harness maps mutations_disabled to dashboard-safe copy when present

Does not mutate production data. Stubs legacy DB + executors.
"""

from __future__ import annotations

import os
import sys
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace
from typing import Any


ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

os.environ["WATHEFNI_PLATFORM_ASSISTANT_WAVE1"] = "1"
os.environ["WATHEFNI_ASSISTANT_MUTATIONS"] = "0"
os.environ["WATHEFNI_ASSISTANT_KILL"] = "0"


def assert_true(cond: bool, msg: str) -> None:
    if not cond:
        raise AssertionError(msg)


class _FakeConn:
    def commit(self) -> None:
        return None

    def cursor(self):
        return self

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def execute(self, *args, **kwargs):
        return None


@contextmanager
def _fake_db_connect():
    yield _FakeConn()


def main() -> int:
    import platform_assistant_spine_wave1 as spine
    import tool_call_orchestrator as tco
    import action_registry as registry

    assert_true(spine.assistant_mutations_allowed() is False, "mutations must be off for this smoke")
    assert_true(spine.platform_assistant_wave1_enabled() is True, "wave1 on")

    mut_tools = [
        "cancel_onboarding",
        "reschedule_onboarding",
        "onboarding_mark_item",
        "approve_leave_request",
        "reject_leave_request",
        "correct_attendance_record",
        "approve_shift_swap",
        "reject_shift_swap",
    ]
    non_mut = [
        "send_onboarding_reminder",
        "compliance_send_reminder",
        "compliance_mark_reviewed",
    ]

    for name in mut_tools:
        spec = registry.spec_for(name)
        assert_true(spec is not None, f"missing registry spec {name}")
        assert_true(spine.tool_is_mutation(spec) is True, f"{name} must be mutation")

    for name in non_mut:
        spec = registry.spec_for(name)
        if spec is None:
            continue
        assert_true(spine.tool_is_mutation(spec) is False, f"{name} should not be kill-classified")

    scope = {
        "company_id": "WATHEFNI",
        "admin_user_id": "test-user",
        "permissions": {
            "onboarding.manage",
            "leave.decide",
            "attendance.manage",
            "shifts.manage",
            "compliance.manage",
            "employees.manage",
        },
    }

    real_legacy = tco._legacy
    real_tool_allowed = tco._tool_allowed
    real_spec_for = registry.spec_for

    class _FakeLegacy:
        def db_connect(self):
            return _fake_db_connect()

        def json_safe(self, value):
            return value

    def fake_allowed(tool_name: str, _scope: dict):
        return True, None

    class _FakeSpec:
        def __init__(self, name: str, base: Any):
            self._base = base
            self.name = name
            self.sensitive = getattr(base, "sensitive", False)
            self.requires_confirmation = False  # skip confirm branch
            self.preflight = None
            self.module = getattr(base, "module", "onboarding")
            self.entity_type = getattr(base, "entity_type", None)
            self.executor = staticmethod(
                lambda *_a, **_k: {"ok": True, "safe_user_message": "stub-ok"}
            )

        def __getattr__(self, item: str):
            return getattr(self._base, item)

    def fake_spec(name: str):
        base = real_spec_for(name)
        if base is None:
            return None
        return _FakeSpec(name, base)

    tco._legacy = lambda: _FakeLegacy()  # type: ignore[assignment]
    tco._tool_allowed = fake_allowed  # type: ignore[assignment]
    registry.spec_for = fake_spec  # type: ignore[assignment]
    tco._registry = registry

    try:
        dash_req = SimpleNamespace(
            raw_text="[dashboard] cancel_onboarding",
            metadata={"channel": "web_dashboard", "dashboard": True, "company_code": "WATHEFNI"},
        )
        asst_req = SimpleNamespace(
            raw_text="please cancel onboarding",
            metadata={"channel": "whatsapp", "dashboard": False, "company_code": "WATHEFNI"},
        )

        denied = tco._execute_tool("cancel_onboarding", {"employee_key": "E1"}, asst_req, {}, {}, scope)
        assert_true(denied.get("status") == "mutations_disabled", f"assistant kill missing: {denied}")
        assert_true("assistant session" in str(denied.get("message") or "").lower(), denied.get("message"))

        for tool in mut_tools:
            out = tco._execute_tool(tool, {"employee_key": "E1"}, dash_req, {}, {}, scope)
            assert_true(
                out.get("status") != "mutations_disabled",
                f"dashboard leaked kill for {tool}: {out}",
            )
            msg = str(out.get("message") or "") + str((out.get("result") or {}))
            assert_true("assistant session" not in msg.lower(), f"dashboard got assistant copy for {tool}: {out}")

        dash_meta_only = SimpleNamespace(
            raw_text="[dashboard] x",
            metadata={"dashboard": True, "company_code": "WATHEFNI"},
        )
        out = tco._execute_tool("approve_leave_request", {"request_id": "L1"}, dash_meta_only, {}, {}, scope)
        assert_true(out.get("status") != "mutations_disabled", out)

        avail = real_spec_for("approve_availability_request")
        print(
            "availability_approve_registered",
            bool(avail),
            "# gap documented if False — unknown_action on UI",
        )

        # Harness mapping — only when app imports (prod/staging venv).
        try:
            import app
        except ModuleNotFoundError as exc:
            print(f"harness_mapping SKIPPED ({exc.name} missing locally)")
        else:
            captured: list[tuple] = []

            def fake_audit(action_type, status, payload, reply):
                captured.append((action_type, status, reply))
                return {"result_id": "x"}

            orig_exec = tco._execute_tool
            orig_audit = app.dashboard_record_action_result

            def deny_exec(tool_name, args, request, state, graph_state, scope_arg):
                return spine.mutation_kill_denial(tool_name=tool_name, locale="en")

            tco._execute_tool = deny_exec  # type: ignore[assignment]
            app.dashboard_record_action_result = fake_audit  # type: ignore[assignment]
            try:
                ctx = {
                    "company_code": "WATHEFNI",
                    "hr_phone": "96599338566",
                    "actor_user_id": "u1",
                    "actor_email": "a@b.c",
                    "actor_role": "owner",
                    "hr_user": {"user_id": "u1"},
                    "access": {"permissions": list(scope["permissions"])},
                    "permissions": list(scope["permissions"]),
                }
                pack = app.run_dashboard_registry_action(
                    ctx,
                    "cancel_onboarding",
                    {"employee_key": "E1"},
                    allowed_modules={
                        "onboarding",
                        "leave",
                        "attendance",
                        "shifts",
                        "compliance",
                        "employees",
                        "payroll",
                    },
                    conversation_id="dash:test",
                    scope={
                        "company_id": "WATHEFNI",
                        "admin_user_id": "u1",
                        "permissions": scope["permissions"],
                    },
                    audit_target_type="employee",
                )
                assert_true(pack.get("ok") is False, pack)
                assert_true(pack.get("status") == "mutations_disabled", pack)
                assert_true("assistant session" not in str(pack.get("message") or "").lower(), pack.get("message"))
                assert_true("safety switch" in str(pack.get("message") or "").lower(), pack.get("message"))
                print("harness_mapping OK")
            finally:
                tco._execute_tool = orig_exec  # type: ignore[assignment]
                app.dashboard_record_action_result = orig_audit  # type: ignore[assignment]

        print("posthire-mutation-integrity smoke passed")
        print("add_employee_path=dedicated_REST (bypasses assistant kill by design)")
        return 0
    finally:
        tco._legacy = real_legacy  # type: ignore[assignment]
        tco._tool_allowed = real_tool_allowed  # type: ignore[assignment]
        registry.spec_for = real_spec_for  # type: ignore[assignment]
        tco._registry = registry


if __name__ == "__main__":
    raise SystemExit(main())
