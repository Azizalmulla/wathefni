"""Setup Console Phase 1 — module disable semantics (canonical contract).

Disabling a company module must:
  - stop new future activity
  - hide navigation / employee surfaces
  - fail-close module APIs
  - preserve historical records + audit
  - never delete data
  - never silently cancel or mutate existing records unless an explicit lifecycle rule exists

Employee App is the known special case: disable revokes sessions and supersedes invites
(explicit lifecycle rule), without deleting historical invite/audit rows.
"""
from __future__ import annotations

from typing import Any

PHASE = "setup_console_phase1"
CONTRACT_VERSION = "module_disable_semantics_v1"

STANDARD = {
    "stop_new_activity": True,
    "hide_navigation_and_surfaces": True,
    "block_module_apis": True,
    "preserve_historical_records": True,
    "preserve_audit_history": True,
    "delete_data": False,
    "silent_cancel_or_mutate_existing": False,
}


def module_disable_semantics() -> dict[str, Any]:
    """Per-module notes where behaviour differs from the standard contract."""
    return {
        "ok": True,
        "phase": PHASE,
        "contract_version": CONTRACT_VERSION,
        "standard": STANDARD,
        "modules": {
            "employee_app": {
                **STANDARD,
                "explicit_lifecycle_rule": True,
                "on_disable": [
                    "revoke_active_employee_app_sessions",
                    "supersede_open_invites",
                ],
                "deletes_history": False,
                "note": "Sessions/invites closed so the app cannot be used; history retained.",
            },
            "payroll": {
                **STANDARD,
                "explicit_lifecycle_rule": False,
                "note": "Sealed authority snapshots and payslips are retained; no new Mode A activity without entitlement.",
            },
            "leave": {**STANDARD, "explicit_lifecycle_rule": False},
            "attendance": {**STANDARD, "explicit_lifecycle_rule": False},
            "shifts": {**STANDARD, "explicit_lifecycle_rule": False},
            "onboarding": {**STANDARD, "explicit_lifecycle_rule": False},
            "compliance": {**STANDARD, "explicit_lifecycle_rule": False},
            "pre_hiring": {**STANDARD, "explicit_lifecycle_rule": False},
        },
        "exceptions_from_standard": ["employee_app"],
    }
