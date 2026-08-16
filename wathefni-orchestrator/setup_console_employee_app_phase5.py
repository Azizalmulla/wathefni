"""Setup Console Phase 5 — Employee App composition contract (server twin + docs).

Client SoT: apps/wathefni-employee-mobile/src/composition/employeeAppComposition.ts
Composition derives from /app/me features (Setup Console entitlements), not a
parallel frontend registry.
"""
from __future__ import annotations

from typing import Any

PHASE = "setup_console_phase5"
CONTRACT_VERSION = "employee_app_composition_v1"

CORE_SURFACES = ("home", "inbox", "profile", "settings")
MODULE_SURFACES = ("onboarding", "documents", "attendance", "shifts", "leave", "payslips", "bank", "performance", "talent")
HOME_TILES = ("shifts", "attendance", "leave", "documents", "payslips", "performance", "talent")


def composition_from_features(
    features: dict[str, bool],
    *,
    onboarding_required_pending: int = 0,
    onboarding_pending_count: int = 0,
    onboarding_required_total: int = 0,
) -> dict[str, Any]:
    modules = {key: bool(features.get(key)) for key in MODULE_SURFACES}
    home_tiles = [key for key in HOME_TILES if modules.get(key)]
    feature_on = bool(modules.get("onboarding"))
    incomplete = feature_on and (onboarding_required_pending > 0 or onboarding_pending_count > 0)
    completed = (
        feature_on
        and not incomplete
        and onboarding_required_total > 0
        and onboarding_required_pending == 0
        and onboarding_pending_count == 0
    )
    return {
        "ok": True,
        "phase": PHASE,
        "contract_version": CONTRACT_VERSION,
        "core": {k: True for k in CORE_SURFACES},
        "modules": modules,
        "home_tiles": home_tiles,
        "wide_home_tiles": len(home_tiles) <= 1,
        "show_onboarding_journey": incomplete,
        "onboarding_demoted": completed or not feature_on,
        "tabs": {
            "home": True,
            "inbox": True,
            "shifts": bool(modules.get("shifts")),
            "leave": bool(modules.get("leave")),
            "profile": True,
        },
        "separate_compliance_tab": False,
        "inbox_is_purchased_module": False,
        "honesty": {
            "derives_from_app_me_features": True,
            "no_parallel_frontend_registry": True,
            "notifications_not_purchased_module": True,
            "documents_owns_employee_compliance": True,
        },
    }


# Representative qualification configurations (feature maps).
CONFIGS: dict[str, dict[str, Any]] = {
    "A_documents_only": {
        "features": {"documents": True},
        "expect_home_tiles": ["documents"],
        "expect_wide": True,
        "expect_tabs_shifts": False,
        "expect_tabs_leave": False,
    },
    "B_leave_documents": {
        "features": {"leave": True, "documents": True},
        "expect_home_tiles": ["leave", "documents"],
        "expect_wide": False,
        "expect_tabs_leave": True,
    },
    "C_leave_documents_attendance_payslips": {
        "features": {"leave": True, "documents": True, "attendance": True, "payslips": True},
        "expect_home_tiles": ["attendance", "leave", "documents", "payslips"],
        "expect_wide": False,
    },
    "D_full_suite": {
        "features": {
            "onboarding": True,
            "documents": True,
            "attendance": True,
            "shifts": True,
            "leave": True,
            "payslips": True,
            "bank": True,
        },
        "expect_home_tiles": ["shifts", "attendance", "leave", "documents", "payslips"],
        "expect_tabs_shifts": True,
        "expect_tabs_leave": True,
    },
    "E_onboarding_employee": {
        "features": {"onboarding": True, "documents": True, "leave": True},
        "onboarding_required_pending": 2,
        "onboarding_pending_count": 2,
        "onboarding_required_total": 5,
        "expect_show_onboarding": True,
        "expect_demoted": False,
    },
    "F_onboarding_complete": {
        "features": {"onboarding": True, "documents": True, "leave": True},
        "onboarding_required_pending": 0,
        "onboarding_pending_count": 0,
        "onboarding_required_total": 5,
        "expect_show_onboarding": False,
        "expect_demoted": True,
    },
}


def qualify_config(name: str) -> dict[str, Any]:
    spec = CONFIGS[name]
    features = dict(spec["features"])
    composed = composition_from_features(
        features,
        onboarding_required_pending=int(spec.get("onboarding_required_pending") or 0),
        onboarding_pending_count=int(spec.get("onboarding_pending_count") or 0),
        onboarding_required_total=int(spec.get("onboarding_required_total") or 0),
    )
    failures: list[str] = []
    if "expect_home_tiles" in spec and composed["home_tiles"] != list(spec["expect_home_tiles"]):
        failures.append(f"home_tiles={composed['home_tiles']}")
    if "expect_wide" in spec and composed["wide_home_tiles"] != bool(spec["expect_wide"]):
        failures.append(f"wide={composed['wide_home_tiles']}")
    if "expect_tabs_shifts" in spec and composed["tabs"]["shifts"] != bool(spec["expect_tabs_shifts"]):
        failures.append("tabs.shifts")
    if "expect_tabs_leave" in spec and composed["tabs"]["leave"] != bool(spec["expect_tabs_leave"]):
        failures.append("tabs.leave")
    if "expect_show_onboarding" in spec and composed["show_onboarding_journey"] != bool(spec["expect_show_onboarding"]):
        failures.append("show_onboarding_journey")
    if "expect_demoted" in spec and composed["onboarding_demoted"] != bool(spec["expect_demoted"]):
        failures.append("onboarding_demoted")
    if composed["inbox_is_purchased_module"]:
        failures.append("inbox_counted_as_module")
    if composed["separate_compliance_tab"]:
        failures.append("compliance_tab")
    # Inbox never in home_tiles
    if "inbox" in composed["home_tiles"] or "notifications" in composed["home_tiles"]:
        failures.append("inbox_in_home_tiles")
    return {"ok": not failures, "name": name, "composition": composed, "failures": failures}


def qualify_all() -> dict[str, Any]:
    results = [qualify_config(name) for name in CONFIGS]
    return {
        "ok": all(r["ok"] for r in results),
        "phase": PHASE,
        "contract_version": CONTRACT_VERSION,
        "results": results,
    }
