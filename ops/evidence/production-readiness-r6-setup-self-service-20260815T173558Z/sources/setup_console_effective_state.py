"""R6 — one canonical effective capability state for Setup.

product released × deployment available × company entitled/configured × principal permitted

Setup must never show Enabled while runtime cannot use the capability.
Does not invent a second readiness system: consumes capability_readiness +
domain runtime_gate + company_modules / domain settings.
"""
from __future__ import annotations

from typing import Any, Mapping

import capability_readiness as ready
from module_catalog import MODULE_BY_KEY, normalize_module_key

PHASE = "setup_console_r6_effective_state"
CONTRACT_VERSION = "setup_effective_state_v1"

STATES = (
    "not_released",
    "unavailable_deployment",
    "dependency_unmet",
    "available_disabled",
    "not_entitled",
    "not_permitted",
    "enabled_usable",
)

STATE_LABELS = {
    "not_released": {"en": "Not released", "ar": "غير مُصدَر"},
    "unavailable_deployment": {"en": "Unavailable in this deployment", "ar": "غير متاح في هذا النشر"},
    "dependency_unmet": {"en": "Requires a dependency", "ar": "يتطلب اعتماداً"},
    "available_disabled": {"en": "Available but disabled", "ar": "متاح لكنه متوقف"},
    "not_entitled": {"en": "Not entitled", "ar": "غير مُخوَّل"},
    "not_permitted": {"en": "Not permitted", "ar": "غير مسموح"},
    "enabled_usable": {"en": "Enabled", "ar": "مفعّل"},
}

# R5A frozen customer_facing_state vocabulary. Richer R6 state lives in effective_state.
CUSTOMER_FACING_STATE = {
    "enabled_usable": "enabled",
    "available_disabled": "disabled",
    "not_released": "not_released",
    "unavailable_deployment": "unavailable",
    "dependency_unmet": "dependency_unmet",
    "not_entitled": "disabled",
    "not_permitted": "not_permitted",
}

# Errors that are deployment/kill-switch, never customer policy.
_DEPLOYMENT_ERRORS = {
    "analytics_kill_switch",
    "hr_intelligence_registry_c1_off",
    "hr_intelligence_company_not_allowlisted",
    "hr_intelligence_workforce_c2_off",
    "hr_intelligence_workforce_company_not_allowlisted",
    "hr_intelligence_recruiting_c3_off",
    "hr_intelligence_recruiting_company_not_allowlisted",
    "hr_intelligence_time_pay_c4_off",
    "hr_intelligence_surfaces_c6_off",
    "hr_intelligence_surfaces_company_not_allowlisted",
    "c1_registry_required",
    "kill_switch",
    "runtime_flag",
    "company_allowlist",
}

_DEPENDENCY_ERRORS = {
    "ja_must_be_enabled",
    "ja_hard_dependency_unmet",
    "ja_hard_unmet",
    "dependency_unmet",
}

_HARD_DEPS = {
    "comp_planning": ("job_architecture",),
    "workforce_planning": ("job_architecture",),
    "wave6_comp_planning": ("job_architecture",),
    "wave6_workforce_planning": ("job_architecture",),
}


def _truthy(value: Any) -> bool:
    if value is True:
        return True
    if value is False or value is None:
        return False
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def state_label(state: str, *, lang: str = "en") -> str:
    pack = STATE_LABELS.get(str(state or "").strip().lower()) or {
        "en": str(state or "unknown"),
        "ar": str(state or "غير معروف"),
    }
    return str(pack.get("ar" if str(lang).lower().startswith("ar") else "en"))


def public_deployment_reason(runtime_gate: Mapping[str, Any] | None) -> dict[str, Any]:
    """Non-sensitive reason. Never expose env names or secrets."""
    gate = dict(runtime_gate or {})
    if gate.get("ok"):
        return {
            "deployment_available": True,
            "reason_code": "available",
            "message_en": "Available in this deployment.",
            "message_ar": "متاح في هذا النشر.",
        }
    err = str(gate.get("error") or gate.get("gate") or "unavailable").strip().lower()
    if err in _DEPENDENCY_ERRORS or "ja_" in err:
        return {
            "deployment_available": True,
            "reason_code": "dependency_unmet",
            "message_en": "Job Architecture must be enabled first.",
            "message_ar": "يجب تفعيل هيكل الوظائف أولاً.",
        }
    return {
        "deployment_available": False,
        "reason_code": "unavailable_deployment",
        "message_en": "Unavailable in this deployment.",
        "message_ar": "غير متاح في هذا النشر.",
    }


def _capability_key(module_key: str) -> str | None:
    return ready.capability_for_setup_module_key(module_key)


def _product_released(module_key: str) -> bool:
    cap = _capability_key(module_key)
    if cap:
        return bool(ready.customer_enableable(cap))
    key = normalize_module_key(module_key) or str(module_key or "").strip().lower()
    if key.startswith("wave5_") or key in {"analytics", "intelligence", "hr_intelligence"}:
        return ready.catalog_module_customer_enableable("analytics")
    if key in {"notifications", "delivery", "channels"}:
        return True
    if key in MODULE_BY_KEY:
        return ready.catalog_module_customer_enableable(key)
    # Platform foundations (Job Architecture) are capability-keyed.
    return False


def _stored_enabled(payload: Mapping[str, Any] | None) -> bool:
    body = dict(payload or {})
    policy = body.get("policy") if isinstance(body.get("policy"), dict) else {}
    if "enabled" in policy:
        return _truthy(policy.get("enabled"))
    if "module_enabled" in body:
        return _truthy(body.get("module_enabled"))
    if "commercial_enabled" in body:
        return _truthy(body.get("commercial_enabled"))
    return _truthy(body.get("enabled") or body.get("stored_enabled"))


def _runtime_gate(payload: Mapping[str, Any] | None) -> dict[str, Any]:
    body = dict(payload or {})
    gate = body.get("runtime_gate")
    return dict(gate) if isinstance(gate, dict) else {}


def resolve_effective_state(
    module_key: str,
    payload: Mapping[str, Any] | None = None,
    *,
    principal_permitted: bool | None = None,
    company_entitled: bool | None = None,
) -> dict[str, Any]:
    key = str(module_key or "").strip().lower()
    body = dict(payload or {})
    released = _product_released(key)
    stored = _stored_enabled(body) if company_entitled is None else bool(company_entitled)
    gate = _runtime_gate(body)
    public = public_deployment_reason(gate) if gate else {
        "deployment_available": True,
        "reason_code": "available",
        "message_en": "Available in this deployment.",
        "message_ar": "متاح في هذا النشر.",
    }
    deployment_ok = bool(public.get("deployment_available"))
    dep_unmet = False
    if gate:
        err = str(gate.get("error") or gate.get("gate") or "").strip().lower()
        dep_unmet = err in _DEPENDENCY_ERRORS or "ja_" in err
    if not dep_unmet:
        for dep in _HARD_DEPS.get(key, ()):
            if not ready.customer_enableable(dep):
                dep_unmet = True
                public = {
                    "deployment_available": True,
                    "reason_code": "dependency_unmet",
                    "message_en": "Job Architecture must be enabled first.",
                    "message_ar": "يجب تفعيل هيكل الوظائف أولاً.",
                }

    if principal_permitted is False:
        state = "not_permitted"
    elif not released:
        state = "not_released"
    elif not deployment_ok:
        state = "unavailable_deployment"
    elif dep_unmet:
        state = "dependency_unmet"
    elif not stored:
        # Released + deployable, company has not turned it on.
        state = "available_disabled"
    else:
        state = "enabled_usable"

    usable = state == "enabled_usable"
    # Honesty: stored ON + blocked runtime is never "Enabled".
    if stored and state in {"unavailable_deployment", "dependency_unmet", "not_released", "not_permitted"}:
        usable = False

    cap = _capability_key(key)
    return {
        "ok": True,
        "phase": PHASE,
        "contract_version": CONTRACT_VERSION,
        "module_key": key,
        "capability_key": cap,
        "product_released": released,
        "deployment_available": deployment_ok,
        "company_entitled": stored,
        "principal_permitted": principal_permitted,
        "dependency_ok": not dep_unmet,
        "stored_enabled": stored,
        "usable": usable,
        "effective_state": state,
        "label_en": state_label(state, lang="en"),
        "label_ar": state_label(state, lang="ar"),
        "deployment": public,
        "never_enabled_when_unusable": True,
        "readiness": ready.readiness_payload(cap) if cap else None,
    }


def annotate_with_effective_state(
    module_key: str,
    payload: Mapping[str, Any] | None,
    *,
    principal_permitted: bool | None = None,
) -> dict[str, Any]:
    out = dict(payload or {})
    state = resolve_effective_state(module_key, out, principal_permitted=principal_permitted)
    out["effective_state"] = state
    out["stored_enabled"] = state["stored_enabled"]
    out["usable"] = state["usable"]
    out["customer_facing_state"] = CUSTOMER_FACING_STATE.get(
        str(state["effective_state"]), str(state["effective_state"])
    )
    out["customer_enableable"] = state["product_released"]
    if state.get("readiness"):
        out["readiness"] = state["readiness"]
    return out


def honesty_payload() -> dict[str, Any]:
    return {
        "phase": PHASE,
        "contract_version": CONTRACT_VERSION,
        "one_effective_state": True,
        "consumes_capability_readiness": True,
        "no_second_availability_system": True,
        "stored_enabled_does_not_imply_usable": True,
        "enabled_never_shown_when_runtime_unavailable": True,
        "env_names_never_exposed": True,
    }
