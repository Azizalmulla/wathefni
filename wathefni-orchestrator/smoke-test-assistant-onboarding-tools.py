#!/usr/bin/env python3
"""Deterministic contracts for the two onboarding Assistant tools.

No model or database is contacted. The proof exercises tool registration,
tenant/module routing, canonical status payload use, persistence intent, and
strict classifier acceptance rules.
"""
from __future__ import annotations

from unittest.mock import patch

import app

PASS = 0
FAIL = 0


def check(label: str, condition: bool, detail: object = None) -> None:
    global PASS, FAIL
    if condition:
        PASS += 1
        print(f"      PASS  {label}")
    else:
        FAIL += 1
        suffix = f" :: {detail}" if detail is not None else ""
        print(f"      FAIL  {label}{suffix}")


class _Cursor:
    def __init__(self) -> None:
        self.calls: list[tuple[str, tuple[object, ...]]] = []

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def execute(self, sql: str, params: tuple[object, ...]) -> None:
        self.calls.append((" ".join(sql.split()), params))


class _Connection:
    def __init__(self, cursor: _Cursor) -> None:
        self._cursor = cursor
        self.committed = False

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def cursor(self) -> _Cursor:
        return self._cursor

    def commit(self) -> None:
        self.committed = True


def _state(text: str = "Who is still onboarding?") -> app.GraphState:
    return {
        "request": app.WhatsAppTurnRequest(
            sender_phone="96550000000",
            sender_role="hr_admin",
            raw_text=text,
        ),
        "turn_id": "assistant-onboarding-proof",
    }


def main() -> int:
    print("    assistant onboarding tools — deterministic contracts")

    planner_names = {row.get("name") for row in app.PLANNER_TOOL_DEFINITIONS}
    reply_names = {
        row.get("function", {}).get("name")
        for row in app.EMPLOYEE_REPLY_TOOL_DEFINITIONS
        if isinstance(row, dict)
    }
    check("answer_onboarding_status registered", "answer_onboarding_status" in planner_names)
    check("classifier registered", "classify_employee_onboarding_reply" in reply_names)
    check("status tool executable", "answer_onboarding_status" in app.PLANNER_EXECUTABLE_TOOLS)

    with (
        patch.object(app, "request_company_code", return_value="TENANT_A"),
        patch.object(app, "company_has_module", return_value=False),
        patch.object(app, "module_disabled_reply", return_value="Onboarding is unavailable."),
    ):
        disabled = app.answer_onboarding_status(_state())
    check("module disabled fails closed", disabled.get("turn_focus") == "module_disabled", disabled)
    check("module denial remains authoritative", disabled.get("authoritative") is True, disabled)

    cursor = _Cursor()
    connection = _Connection(cursor)
    with (
        patch.object(app, "request_company_code", return_value="TENANT_A"),
        patch.object(app, "company_has_module", return_value=True),
        patch.object(
            app,
            "onboarding_queue_reply",
            return_value=("Two employees need onboarding help.", {"company_code": "TENANT_A", "count": 2}),
        ) as queue,
        patch.object(app, "compose_operational_reply", side_effect=lambda **kw: (kw["template_reply"], {"used": False})),
        patch.object(app, "db_connect", return_value=connection),
    ):
        result = app.answer_onboarding_status(_state())
    queue.assert_called_once_with(company_code="TENANT_A")
    check("status read uses authoritative tenant", result.get("turn_focus") == "onboarding_status", result)
    check("status reply uses canonical result", result.get("reply_text") == "Two employees need onboarding help.", result)
    check("status read is authoritative", result.get("final_reply_source") == "focused_backend_status", result)
    check("status snapshot persists", any("INSERT INTO memory_snapshots" in sql for sql, _ in cursor.calls), cursor.calls)
    check("status snapshot commits", connection.committed)

    employee = {"employee_key": "TENANT_A-E1", "name": "Employee", "phone": "96551111111", "onboarding_status": "pending"}
    pending = {"item_id": "civil_id"}
    with patch.object(
        app,
        "call_single_tool_agent",
        return_value={
            "tool": "classify_employee_onboarding_reply",
            "args": {"reply_type": "name", "item_id": "unknown", "value": "Sara Ali", "confidence": 0.91},
        },
    ):
        classified_name = app.plan_employee_onboarding_reply(employee=employee, text="Sara Ali", media=None, next_item=pending)
    check("classifier accepts grounded high-confidence name", classified_name == {"reply_type": "name", "value": "Sara Ali", "reason": None, "confidence": 0.91}, classified_name)

    with patch.object(
        app,
        "call_single_tool_agent",
        return_value={
            "tool": "classify_employee_onboarding_reply",
            "args": {"reply_type": "onboarding_item", "item_id": "civil_id", "value": "uploaded image", "confidence": 0.94},
        },
    ):
        classified_item = app.plan_employee_onboarding_reply(
            employee=employee,
            text="Attached",
            media={"path": "/tmp/current.jpg", "mime_type": "image/jpeg"},
            next_item=pending,
        )
    check("classifier accepts allowlisted onboarding item", classified_item and classified_item.get("item_id") == "civil_id", classified_item)

    with patch.object(
        app,
        "call_single_tool_agent",
        return_value={
            "tool": "classify_employee_onboarding_reply",
            "args": {"reply_type": "onboarding_item", "item_id": "civil_id", "value": "guess", "confidence": 0.2},
        },
    ):
        low_confidence = app.plan_employee_onboarding_reply(employee=employee, text="maybe", media=None, next_item=pending)
    check("classifier rejects low confidence", low_confidence is None, low_confidence)

    with patch.object(app, "call_single_tool_agent", return_value={"tool": "wrong_tool", "args": {}}):
        wrong_tool = app.plan_employee_onboarding_reply(employee=employee, text="hello", media=None, next_item=pending)
    check("classifier rejects wrong tool", wrong_tool is None, wrong_tool)

    print(f"\n    {PASS} passed, {FAIL} failed")
    if FAIL == 0:
        print("ASSISTANT_ONBOARDING_TOOLS_FULL_PASS")
    return 1 if FAIL else 0


if __name__ == "__main__":
    raise SystemExit(main())
