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
    "http_not_registered",
    "not_deployed",
}

# Domain runtime_gate_for_company loaders for catalog SKUs. Analytics stays
# Wave 1 — do not bind it to Intelligence C1, which would lie about a live surface.
_CATALOG_RUNTIME_GATES = {
    "performance": "performance_goals_c1",
    "talent": "talent_profile_c5",
    "learning": "learning_development_c2",
    "benefits": "benefits_administration_c3",
    "employee_relations": "employee_relations_c4",
    "engagement": "engagement_c5",
    "comp_planning": "compensation_planning_c6",
    "workforce_planning": "workforce_planning_c7",
}

MODULE_READ_PERMISSIONS = {
    "performance": "performance.read",
    "talent": "talent.read",
    "learning": "learning.read",
    "benefits": "benefits.read",
    "employee_relations": "er.read",
    "engagement": "engagement.read",
    "comp_planning": "comp_planning.read",
    "workforce_planning": "workforce_planning.read",
    "analytics": "analytics.read",
    "job_architecture": "job_architecture.read",
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
    gate_kind = str(gate.get("gate") or "").strip().lower()
    if err in _DEPENDENCY_ERRORS or "ja_" in err:
        return {
            "deployment_available": True,
            "reason_code": "dependency_unmet",
            "message_en": "Job Architecture must be enabled first.",
            "message_ar": "يجب تفعيل هيكل الوظائف أولاً.",
        }
    if (
        gate_kind == "not_deployed"
        or err in {"http_not_registered", "not_deployed"}
    ):
        return {
            "deployment_available": False,
            "reason_code": "not_deployed",
            "message_en": "Not deployed in this environment.",
            "message_ar": "غير منشور في هذه البيئة.",
        }
    if (
        gate_kind == "company_allowlist"
        or err == "company_allowlist"
        or "not_allowlisted" in err
        or "allowlist" in err
    ):
        return {
            "deployment_available": False,
            "reason_code": "pilot_allowlist",
            "message_en": "Blocked by a deployment allowlist or pilot gate.",
            "message_ar": "محظور بقائمة سماح أو بوابة تجريبية.",
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

    blockers: list[dict[str, str]] = []
    if principal_permitted is False:
        blockers.append(
            {
                "code": "not_permitted",
                "message_en": "No company administrator has permission to use this module.",
                "message_ar": "لا يملك أي مسؤول في الشركة صلاحية استخدام هذه الوحدة.",
            }
        )
    if not released:
        blockers.append(
            {
                "code": "not_released",
                "message_en": "Not released for customer enablement.",
                "message_ar": "غير مُصدَر لتفعيل العملاء.",
            }
        )
    reason_code = str(public.get("reason_code") or "")
    if not deployment_ok and reason_code == "pilot_allowlist":
        blockers.append(
            {
                "code": "pilot_allowlist",
                "message_en": str(public.get("message_en") or "Blocked by a deployment allowlist or pilot gate."),
                "message_ar": str(public.get("message_ar") or ""),
            }
        )
    elif not deployment_ok and reason_code == "not_deployed":
        blockers.append(
            {
                "code": "not_deployed",
                "message_en": str(public.get("message_en") or "Not deployed in this environment."),
                "message_ar": str(public.get("message_ar") or ""),
            }
        )
    elif not deployment_ok:
        blockers.append(
            {
                "code": "unavailable_deployment",
                "message_en": str(public.get("message_en") or "Unavailable in this deployment."),
                "message_ar": str(public.get("message_ar") or ""),
            }
        )
    if dep_unmet:
        blockers.append(
            {
                "code": "dependency_unmet",
                "message_en": str(public.get("message_en") or "Job Architecture must be enabled first."),
                "message_ar": str(public.get("message_ar") or ""),
            }
        )

    cap = _capability_key(key)
    payload = {
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
        "blockers": blockers,
        "never_enabled_when_unusable": True,
        "readiness": ready.readiness_payload(cap) if cap else None,
        "required_permission": MODULE_READ_PERMISSIONS.get(normalize_module_key(key) or key),
    }
    payload["can_enable"] = can_become_usable(payload)
    return payload


def annotate_with_effective_state(
    module_key: str,
    payload: Mapping[str, Any] | None,
    *,
    principal_permitted: bool | None = None,
    company_entitled: bool | None = None,
) -> dict[str, Any]:
    out = dict(payload or {})
    state = resolve_effective_state(
        module_key,
        out,
        principal_permitted=principal_permitted,
        company_entitled=company_entitled,
    )
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
        "setup_console_modules_access": True,
    }


def can_become_usable(state: Mapping[str, Any] | None) -> bool:
    """True only when turning the catalog entitlement on would yield enabled_usable."""
    body = dict(state or {})
    key = str(body.get("effective_state") or "")
    if key == "enabled_usable":
        return True
    if key not in {"available_disabled", "not_entitled"}:
        return False
    if body.get("principal_permitted") is False:
        return False
    return bool(body.get("product_released")) and bool(body.get("deployment_available")) and bool(body.get("dependency_ok"))


def catalog_runtime_gate_for_company(
    module_key: str,
    company_code: str | None,
    *,
    platform_available: bool = True,
    http_registered: bool | None = None,
) -> dict[str, Any]:
    """Build a runtime_gate for a catalog SKU without exposing env names."""
    key = normalize_module_key(module_key) or str(module_key or "").strip().lower()
    if http_registered is False:
        return {"ok": False, "error": "http_not_registered", "gate": "not_deployed"}
    if platform_available is False:
        return {"ok": False, "error": "kill_switch", "gate": "runtime_flag"}
    loader = _CATALOG_RUNTIME_GATES.get(key)
    if loader:
        try:
            mod = __import__(loader, fromlist=["runtime_gate_for_company"])
            gate = mod.runtime_gate_for_company(company_code)
            if isinstance(gate, dict):
                return gate
        except Exception:
            return {"ok": False, "error": "http_not_registered", "gate": "not_deployed"}
    return {"ok": True, "enabled": True}


def annotate_catalog_module(
    module_key: str,
    item: Mapping[str, Any] | None,
    *,
    company_code: str | None = None,
    principal_permitted: bool | None = None,
    http_registered: bool | None = None,
) -> dict[str, Any]:
    """Attach canonical effective_state to a Setup catalog row."""
    body = dict(item or {})
    key = normalize_module_key(module_key or body.get("key")) or str(module_key or "").strip().lower()
    stored = bool(body.get("configured") or body.get("stored_enabled") or body.get("enabled"))
    platform_available = True if "platform_available" not in body else bool(body.get("platform_available"))
    gate = catalog_runtime_gate_for_company(
        key,
        company_code,
        platform_available=platform_available,
        http_registered=http_registered,
    )
    annotated = annotate_with_effective_state(
        key,
        {
            **body,
            "stored_enabled": stored,
            "enabled": stored,
            "runtime_gate": gate,
        },
        principal_permitted=principal_permitted,
        company_entitled=stored,
    )
    state = dict(annotated.get("effective_state") or {})
    customer_facing = str(annotated.get("customer_facing_state") or "")
    annotated["effective"] = bool(state.get("usable"))
    annotated["configured"] = stored
    annotated["can_enable"] = bool(state.get("can_enable"))
    annotated["can_select"] = bool(state.get("can_enable")) or (key == "employee_app")
    if customer_facing == "enabled" and not state.get("usable"):
        annotated["customer_facing_state"] = "unavailable"
    return annotated


def annotate_setup_catalog(
    company_code: str | None,
    items: list[Mapping[str, Any]] | None,
    *,
    principal_permitted_by_key: Mapping[str, bool | None] | None = None,
    http_registered_by_key: Mapping[str, bool | None] | None = None,
) -> list[dict[str, Any]]:
    permitted = dict(principal_permitted_by_key or {})
    registered = dict(http_registered_by_key or {})
    out: list[dict[str, Any]] = []
    for item in items or []:
        key = str((item or {}).get("key") or "").strip().lower()
        out.append(
            annotate_catalog_module(
                key,
                item,
                company_code=company_code,
                principal_permitted=permitted.get(key),
                http_registered=registered.get(key),
            )
        )
    return out
