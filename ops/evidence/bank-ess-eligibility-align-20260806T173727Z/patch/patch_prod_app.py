#!/usr/bin/env python3
"""Surgical production app.py patch — Bank ESS eligibility alignment."""

from __future__ import annotations

from pathlib import Path

APP = Path("/opt/wathefni/orchestrator/app.py")
text = APP.read_text(encoding="utf-8")
orig = text

old_ver = '_EMPLOYEE_APP_FEATURE_CONTRACT_VERSION = "phase9a1"'
new_ver = '_EMPLOYEE_APP_FEATURE_CONTRACT_VERSION = "phase9a1_bank_ess"'
if old_ver in text:
    text = text.replace(old_ver, new_ver, 1)
elif new_ver not in text:
    raise SystemExit("feature contract version marker missing")

if '"bank": {' not in text.split("_EMPLOYEE_APP_FEATURE_DEFINITIONS", 1)[1][:2500]:
    needle = '''    "leave": {
        "dependency_mode": "all",
        "module_keys": ("leave",),
        "actions": ("view", "request", "cancel"),
    },
    # Reserved canonical keys. They are returned disabled until employee-safe
'''
    bank_def = '''    "leave": {
        "dependency_mode": "all",
        "module_keys": ("leave",),
        "actions": ("view", "request", "cancel"),
    },
    # Bank ESS is employee-keyed; eligibility applied in apply_bank_ess_feature_contract.
    "bank": {
        "dependency_mode": "bank_ess",
        "module_keys": (),
        "actions": ("view", "submit", "withdraw", "upload_evidence"),
        "implemented": True,
    },
    # Reserved canonical keys. They are returned disabled until employee-safe
'''
    if needle not in text:
        raise SystemExit("leave feature definition needle missing")
    text = text.replace(needle, bank_def, 1)

old_loop = '''    for key, definition in _EMPLOYEE_APP_FEATURE_DEFINITIONS.items():
        dependency_mode = str(definition.get("dependency_mode") or "all")
        module_keys = tuple(str(item) for item in definition.get("module_keys") or ())
        if dependency_mode == "core":
            entitled = True
        elif dependency_mode == "any":
            entitled = any(item in modules for item in module_keys)
        else:
            entitled = all(item in modules for item in module_keys)
        implemented = bool(definition.get("implemented", True))
        enabled = entitled and implemented
        reason = None
        if not entitled:
            reason = "module_disabled"
        elif not implemented:
            reason = "feature_not_available"
        actions = list(definition.get("actions") or ()) if enabled else []
        if key == "settings" and enabled and push_available:
            actions.append("manage_push")
'''

new_loop = '''    for key, definition in _EMPLOYEE_APP_FEATURE_DEFINITIONS.items():
        dependency_mode = str(definition.get("dependency_mode") or "all")
        module_keys = tuple(str(item) for item in definition.get("module_keys") or ())
        if dependency_mode == "bank_ess":
            entitled = False
            implemented = bool(definition.get("implemented", True))
            enabled = False
            reason = "bank_ess_pending_eligibility"
            actions = []
        elif dependency_mode == "core":
            entitled = True
            implemented = bool(definition.get("implemented", True))
            enabled = entitled and implemented
            reason = None if enabled else ("feature_not_available" if not implemented else "module_disabled")
            actions = list(definition.get("actions") or ()) if enabled else []
        elif dependency_mode == "any":
            entitled = any(item in modules for item in module_keys)
            implemented = bool(definition.get("implemented", True))
            enabled = entitled and implemented
            reason = None
            if not entitled:
                reason = "module_disabled"
            elif not implemented:
                reason = "feature_not_available"
            actions = list(definition.get("actions") or ()) if enabled else []
        else:
            entitled = all(item in modules for item in module_keys)
            implemented = bool(definition.get("implemented", True))
            enabled = entitled and implemented
            reason = None
            if not entitled:
                reason = "module_disabled"
            elif not implemented:
                reason = "feature_not_available"
            actions = list(definition.get("actions") or ()) if enabled else []
        if key == "settings" and enabled and push_available and "manage_push" not in actions:
            actions.append("manage_push")
'''

if "bank_ess_pending_eligibility" not in text:
    if old_loop not in text:
        raise SystemExit("feature loop needle missing")
    text = text.replace(old_loop, new_loop, 1)

helper = '''

def apply_bank_ess_feature_contract(
    contract: dict[str, Any],
    *,
    company_code: str,
    employee_key: str,
) -> dict[str, Any]:
    """Stamp the canonical Bank ESS eligibility onto the feature contract."""
    import employee_bank_ess as _bank
    import employee_selfservice_wave5 as _w5

    eligibility = _bank.bank_ess_eligibility(
        company_code,
        employee_key,
        ess_v5_enabled=_w5.ess_v5_enabled(company_code),
    )
    definition = _EMPLOYEE_APP_FEATURE_DEFINITIONS.get("bank") or {}
    eligible = bool(eligibility.get("eligible"))
    reason = None if eligible else str(eligibility.get("reason") or "bank_ess_disabled")
    actions = list(definition.get("actions") or ()) if eligible else []
    features = dict(contract.get("features") or {})
    features["bank"] = {
        "enabled": eligible,
        "reason": reason,
        "dependency_mode": "bank_ess",
        "module_keys": [],
        "actions": actions,
        "eligibility": {
            "eligible": eligible,
            "reason": reason,
            "contract_version": eligibility.get("contract_version"),
        },
    }
    out = dict(contract)
    out["features"] = features
    out["enabled_features"] = [key for key, value in features.items() if value.get("enabled")]
    out["bank_ess"] = features["bank"]["eligibility"]
    return out


def employee_app_feature_contract_for_context(context: dict[str, Any]) -> dict[str, Any]:
    contract = build_employee_app_feature_contract(
        employee_app_effective_modules(context),
        push_available=push_notifications_enabled(),
    )
    return apply_bank_ess_feature_contract(
        contract,
        company_code=str(context.get("company_code") or ""),
        employee_key=str(context.get("employee_key") or ""),
    )

'''

if "def apply_bank_ess_feature_contract(" not in text:
    idx = text.find("def build_employee_app_feature_contract(")
    if idx < 0:
        raise SystemExit("build_employee_app_feature_contract missing")
    anchor = text.find('\n    return {\n        "version": _EMPLOYEE_APP_FEATURE_CONTRACT_VERSION,', idx)
    if anchor < 0:
        raise SystemExit("build contract return missing")
    end = text.find("\n\ndef ", anchor)
    if end < 0:
        raise SystemExit("cannot find end of build contract")
    text = text[:end] + helper + text[end:]

old_cap = '''def employee_app_capability_payload(context: dict[str, Any]) -> dict[str, Any]:
    company = str(context.get("company_code") or "").strip().upper()
    employee_modules = employee_app_effective_modules(context)
    contract = build_employee_app_feature_contract(
        employee_modules,
        push_available=push_notifications_enabled(),
    )
'''
new_cap = '''def employee_app_capability_payload(context: dict[str, Any]) -> dict[str, Any]:
    company = str(context.get("company_code") or "").strip().upper()
    employee_modules = employee_app_effective_modules(context)
    contract = employee_app_feature_contract_for_context(context)
'''
if "contract = employee_app_feature_contract_for_context(context)" not in text.split("def employee_app_capability_payload")[1][:500]:
    if old_cap not in text:
        raise SystemExit("capability payload needle missing")
    text = text.replace(old_cap, new_cap, 1)

old_req = '''def require_employee_app_feature(
    context: dict[str, Any],
    feature_key: str,
    *,
    action: str | None = None,
) -> dict[str, Any]:
    key = str(feature_key or "").strip()
    contract = build_employee_app_feature_contract(
        employee_app_effective_modules(context),
        push_available=push_notifications_enabled(),
    )
'''
new_req = '''def require_employee_app_feature(
    context: dict[str, Any],
    feature_key: str,
    *,
    action: str | None = None,
) -> dict[str, Any]:
    key = str(feature_key or "").strip()
    contract = employee_app_feature_contract_for_context(context)
'''
if old_req in text:
    text = text.replace(old_req, new_req, 1)

old_proj = '''    items = list(summary.get("items") or [])
    projection = _lc.build_employee_projection(
        items,
        company_code=company,
        employee_key=key,
        file_index=index,
        versions_by_type=versions_by_type,
        can_upload=can_upload,
        lifecycle_on=lifecycle_on,
        previously_completed=previously_completed,
    )
'''
new_proj = '''    items = list(summary.get("items") or [])
    bank_ess = (employee_app_feature_contract_for_context(context).get("bank_ess") or {})
    bank_ess_eligible = bool(bank_ess.get("eligible"))
    projection = _lc.build_employee_projection(
        items,
        company_code=company,
        employee_key=key,
        file_index=index,
        versions_by_type=versions_by_type,
        can_upload=can_upload,
        lifecycle_on=lifecycle_on,
        previously_completed=previously_completed,
        bank_ess_eligible=bank_ess_eligible,
    )
'''
if "bank_ess_eligible=bank_ess_eligible" not in text:
    if old_proj not in text:
        raise SystemExit("onboarding projection needle missing")
    text = text.replace(old_proj, new_proj, 1)

# Insert bank_ess ONLY into app_onboarding return (not app_profile).
onb_start = text.find("def app_onboarding(")
onb_end = text.find('@app.get("/app/onboarding/items', onb_start) if onb_start >= 0 else -1
if onb_start < 0 or onb_end < 0:
    raise SystemExit("app_onboarding bounds missing")
onb_chunk = text[onb_start:onb_end]
onb_needle = (
    '        "bank_collection": summary.get("bank_collection"),\n'
    '        "can_upload": can_upload,\n'
)
onb_insert = (
    '        "bank_collection": summary.get("bank_collection"),\n'
    '        "bank_ess": bank_ess,\n'
    '        "can_upload": can_upload,\n'
)
if '"bank_ess": bank_ess,' not in onb_chunk:
    if onb_needle not in onb_chunk:
        raise SystemExit("onboarding bank_collection/can_upload needle missing")
    text = text[:onb_start] + onb_chunk.replace(onb_needle, onb_insert, 1) + text[onb_end:]

old_ctx = '''def _bank_ess_context(context: dict[str, Any]) -> tuple[str, str, dict[str, Any]]:
    company = context["company_code"]
    key = context["employee_key"]
    import employee_bank_ess as _bank
    import employee_selfservice_wave5 as _w5

    if not _bank.bank_ess_enabled(company):
        raise HTTPException(
            status_code=403,
            detail={
                "error": "bank_ess_disabled",
                "message": "Bank self-service is not available for your company yet.",
            },
        )
    allow = _bank.bank_ess_employee_allowlist()
    if allow and str(key) not in allow:
        raise HTTPException(
            status_code=403,
            detail={
                "error": "bank_ess_not_allowlisted",
                "message": "Bank self-service is not enabled for your account yet.",
            },
        )
    if not _w5.ess_v5_enabled(company):
        raise HTTPException(status_code=403, detail={"error": "ess_v5_disabled"})
    # ESS context is pinned to this one employee: no cross-employee reach.
'''

new_ctx = '''def _bank_ess_context(context: dict[str, Any]) -> tuple[str, str, dict[str, Any]]:
    company = context["company_code"]
    key = context["employee_key"]
    import employee_bank_ess as _bank
    import employee_selfservice_wave5 as _w5

    eligibility = _bank.bank_ess_eligibility(
        company,
        key,
        ess_v5_enabled=_w5.ess_v5_enabled(company),
    )
    if not eligibility.get("eligible"):
        reason = str(eligibility.get("reason") or "bank_ess_disabled")
        message = {
            "bank_ess_disabled": "Bank self-service is not available for your company yet.",
            "bank_ess_not_allowlisted": "Bank self-service is not enabled for your account yet.",
            "ess_v5_disabled": "Employee self-service is not available for your company yet.",
        }.get(reason, "Bank self-service is not available yet.")
        raise HTTPException(
            status_code=403,
            detail={"error": reason, "message": message},
        )
    # ESS context is pinned to this one employee: no cross-employee reach.
'''

# Marker must be unique to _bank_ess_context (apply_bank_ess_feature_contract also calls eligibility).
if "eligibility = _bank.bank_ess_eligibility(\n        company,\n        key," not in text:
    if old_ctx not in text:
        raise SystemExit("_bank_ess_context needle missing")
    text = text.replace(old_ctx, new_ctx, 1)

if text == orig:
    raise SystemExit("no changes applied")

backup = Path("/opt/wathefni/orchestrator/app.py.bak-bank-elig")
backup.write_text(orig, encoding="utf-8")
APP.write_text(text, encoding="utf-8")
print("patched", APP)
print("backup", backup)
