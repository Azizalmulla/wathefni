#!/usr/bin/env python3
"""Pure Phase 9A1 capability-contract checks. No app import and no database."""

from __future__ import annotations

import ast
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent
APP_PATH = ROOT / "app.py"


def load_contract_builder():
    tree = ast.parse(APP_PATH.read_text(encoding="utf-8"), filename=str(APP_PATH))
    selected: list[ast.stmt] = []
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(
            isinstance(target, ast.Name) and target.id == "_EMPLOYEE_APP_FEATURE_CONTRACT_VERSION"
            for target in node.targets
        ):
            selected.append(node)
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name) and node.target.id == "_EMPLOYEE_APP_FEATURE_DEFINITIONS":
            selected.append(node)
        elif isinstance(node, ast.FunctionDef) and node.name == "build_employee_app_feature_contract":
            selected.append(node)
    if len(selected) != 3:
        raise AssertionError("canonical capability contract definitions were not found")
    namespace: dict[str, Any] = {
        "Any": Any,
        "normalize_module_key": lambda value: str(value).strip().lower(),
    }
    exec(compile(ast.Module(body=selected, type_ignores=[]), str(APP_PATH), "exec"), namespace)
    return namespace["build_employee_app_feature_contract"]


def check(label: str, condition: bool) -> None:
    if not condition:
        raise AssertionError(label)
    print(f"PASS {label}")


def denied_before_data_access(function_name: str, feature_key: str) -> bool:
    tree = ast.parse(APP_PATH.read_text(encoding="utf-8"), filename=str(APP_PATH))
    fn = next(node for node in tree.body if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == function_name)
    calls = [
        node
        for node in ast.walk(fn)
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "require_employee_app_feature"
    ]
    return any(
        len(call.args) >= 2
        and isinstance(call.args[1], ast.Constant)
        and call.args[1].value == feature_key
        for call in calls
    )


def main() -> None:
    build = load_contract_builder()
    core = {"home", "profile", "inbox", "settings"}

    leave_only = build({"employee_app", "leave"}, push_available=False)
    check("leave-only tenant gets core plus leave", set(leave_only["enabled_features"]) == core | {"leave"})
    check("leave-only tenant does not get documents", not leave_only["features"]["documents"]["enabled"])

    workforce = build({"employee_app", "shifts", "attendance"}, push_available=False)
    check("shifts/attendance tenant gets both projections", {"shifts", "attendance"} <= set(workforce["enabled_features"]))
    check("shifts/attendance tenant does not get leave", not workforce["features"]["leave"]["enabled"])

    onboarding = build({"employee_app", "onboarding"}, push_available=False)
    check("onboarding enables checklist and documents", {"onboarding", "documents"} <= set(onboarding["enabled_features"]))

    compliance = build({"employee_app", "compliance"}, push_available=False)
    check("compliance enables documents", compliance["features"]["documents"]["enabled"])
    check("unfinished compliance actions stay disabled", compliance["features"]["compliance_actions"]["reason"] == "feature_not_available")

    payroll = build({"employee_app", "payroll"}, push_available=False)
    check("future payslips stay disabled", payroll["features"]["payslips"]["reason"] == "feature_not_available")

    push = build({"employee_app"}, push_available=True)
    check("push action follows backend channel availability", "manage_push" in push["features"]["settings"]["actions"])

    no_modules = build({"employee_app"}, push_available=False)
    check("module removal deterministically removes optional features", set(no_modules["enabled_features"]) == core)

    route_gates = {
        "app_onboarding": "onboarding",
        "app_leave": "leave",
        "app_leave_request": "leave",
        "app_leave_cancel": "leave",
        "app_shifts_today": "shifts",
        "app_shifts_upcoming": "shifts",
        "app_attendance": "attendance",
        "app_documents": "documents",
        "app_document_file": "documents",
        "app_onboarding_document_upload": "onboarding",
        "app_push_register": "settings",
    }
    for function_name, feature_key in route_gates.items():
        check(
            f"{function_name} enforces {feature_key}",
            denied_before_data_access(function_name, feature_key),
        )

    print("employee app capability contract: GREEN")


if __name__ == "__main__":
    main()
