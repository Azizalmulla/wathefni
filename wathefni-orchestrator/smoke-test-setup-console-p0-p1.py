#!/usr/bin/env python3
"""Setup Console P0/P1 — URL honesty helpers + catalog effective_state (no DB)."""
from __future__ import annotations

import os
import sys
from pathlib import Path

PASS = 0
FAIL = 0

ROOT = Path(__file__).resolve().parent


def check(label: str, condition: bool, detail: object = None) -> None:
    global PASS, FAIL
    if condition:
        PASS += 1
        print(f"      PASS  {label}")
    else:
        FAIL += 1
        extra = f" :: {detail}" if detail is not None else ""
        print(f"      FAIL  {label}{extra}")


def main() -> int:
    sys.path.insert(0, str(ROOT))
    import setup_console_effective_state as eff

    print("    SETUP CONSOLE P0/P1 — catalog effective state")

    leave = eff.annotate_catalog_module(
        "leave",
        {"key": "leave", "configured": False, "platform_available": True},
        company_code="WATHEFNI",
    )
    leave_state = leave.get("effective_state") or {}
    check("leave is disabled but enableable", leave_state.get("effective_state") == "available_disabled")
    check("leave can_enable", leave.get("can_enable") is True)
    check("leave is not shown enabled", leave.get("usable") is not True)

    os.environ["WATHEFNI_PERFORMANCE_GOALS_C1"] = "on"
    os.environ["WATHEFNI_PERFORMANCE_KILL"] = "off"
    os.environ["WATHEFNI_PERFORMANCE_GOALS_COMPANIES"] = "OCTOHR-STORE-REVIEW"
    blocked = eff.annotate_catalog_module(
        "performance",
        {"key": "performance", "configured": False, "platform_available": True},
        company_code="WATHEFNI",
    )
    blocked_state = blocked.get("effective_state") or {}
    check(
        "WATHEFNI performance is allowlist blocked",
        blocked_state.get("effective_state") == "unavailable_deployment",
        blocked_state,
    )
    check("allowlist reason is public", (blocked_state.get("deployment") or {}).get("reason_code") == "pilot_allowlist")
    check("blocked performance cannot enable", blocked.get("can_enable") is not True)
    check("blocked performance is not usable", blocked.get("usable") is not True)

    stored_blocked = eff.annotate_catalog_module(
        "performance",
        {"key": "performance", "configured": True, "platform_available": True},
        company_code="WATHEFNI",
    )
    stored_state = stored_blocked.get("effective_state") or {}
    check("stored+allowlist is never enabled_usable", stored_state.get("effective_state") != "enabled_usable")
    check("stored+allowlist usable is false", stored_blocked.get("usable") is False)
    check("catalog effective flag follows usable", stored_blocked.get("effective") is False)

    missing_http = eff.annotate_catalog_module(
        "employee_relations",
        {"key": "employee_relations", "configured": False, "platform_available": True},
        company_code="WATHEFNI",
        http_registered=False,
    )
    missing_state = missing_http.get("effective_state") or {}
    check("missing HTTP is not deployed", (missing_state.get("deployment") or {}).get("reason_code") == "not_deployed")
    check("missing HTTP cannot enable", missing_http.get("can_enable") is not True)

    forbidden = eff.annotate_catalog_module(
        "talent",
        {"key": "talent", "configured": False, "platform_available": True},
        company_code="WATHEFNI",
        principal_permitted=False,
        http_registered=True,
    )
    forbidden_state = forbidden.get("effective_state") or {}
    check("missing permission is not_permitted", forbidden_state.get("effective_state") == "not_permitted", forbidden_state)
    check("missing permission cannot enable", forbidden.get("can_enable") is not True)

    dep = eff.resolve_effective_state(
        "comp_planning",
        {"stored_enabled": False, "runtime_gate": {"ok": False, "error": "ja_must_be_enabled"}},
    )
    check("comp planning without JA is dependency_unmet", dep.get("effective_state") == "dependency_unmet")
    check("dependency cannot enable", dep.get("can_enable") is not True)

    employee_app = eff.annotate_catalog_module(
        "employee_app",
        {"key": "employee_app", "configured": False, "platform_available": False},
        company_code="WATHEFNI",
    )
    check("employee app remains selectable before platform on", employee_app.get("can_select") is True)
    check("employee app is not can_enable while platform off", employee_app.get("can_enable") is not True)

    dash = ROOT.parent / "apps" / "wathefni-dashboard"
    setup_app = (dash / "src" / "setup-console" / "SetupConsoleApp.tsx").read_text(encoding="utf-8")
    modules_card = (dash / "src" / "setup-console" / "ModulesAccessCard.tsx").read_text(encoding="utf-8")
    vite = (dash / "vite.config.ts").read_text(encoding="utf-8")
    caddy = (ROOT.parent / "ops" / "caddy" / "api.wathefni.ai.Caddyfile").read_text(encoding="utf-8")
    check("Modules & Access is the default view helper", "viewFromLocation" in setup_app)
    check("company query param is written", "writeSetupConsoleLocation" in setup_app)
    check("search debounce exists", "SEARCH_DEBOUNCE_MS" in setup_app)
    check("admin sign-in is the operator surface", "Admin sign-in" in setup_app)
    check("operator login is email plus password", "loginWithOperatorPassword" in setup_app)
    check("token/phone login copy is gone", "Operator token" not in setup_app and "Authorised operator phone" not in setup_app)
    check("ModulesAccessCard uses effective state banner", "SetupEffectiveStateBanner" in modules_card)
    check("blocked modules cannot look enabled", "would stay unusable" in modules_card)
    check("vite serves canonical /setup-console", "setup-console-canonical-url" in vite)
    check("app host Caddy has /setup-console", "@setup_console path /setup-console" in caddy)
    check("selectCompany no longer forces launch", "workspaceViewRef.current" in setup_app)

    print(f"\n    {PASS} passed, {FAIL} failed")
    if FAIL:
        print("SETUP_CONSOLE_P0_P1_FAIL")
        return 1
    print("SETUP_CONSOLE_P0_P1_PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
