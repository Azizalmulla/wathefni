#!/usr/bin/env python3
"""Reusable capability readiness contract (Production Readiness R5A).

One honest answer to: "Can this company use this module right now?"

A Wave 4/6 DOMAIN AUTHORITY FULL_PASS stamp is not customer enablement.
`customer_enableable` requires the HTTP adapter and product surfaces that
module's charter actually promises. Env allowlists remain internal/runtime
kill-switches; they must never make Setup claim a surface-less module is usable.

Customer-facing enabled state must never override runtime unavailability.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Mapping

from module_catalog import MODULE_BY_KEY, MODULE_KEYS, normalize_module_key

PHASE = "capability_readiness_r5a"
CONTRACT_VERSION = "capability_readiness_v1"
PASS_STAMP = "PRODUCTION_READINESS_R5A_CAPABILITY_HONESTY_FULL_PASS"

# Commercial / platform capability keys that currently have domain authority
# but no customer HTTP + product surface. Not catalog SKUs until unhidden.
UNRELEASED_CAPABILITY_KEYS: tuple[str, ...] = (
    "performance",
    "talent",
    "job_architecture",
    "learning",
    "benefits",
    "employee_relations",
    "engagement",
    "comp_planning",
    "workforce_planning",
)

WAVE4_SETUP_TO_CAPABILITY: dict[str, str] = {
    "performance_goals": "performance",
    "performance_reviews": "performance",
    "performance_feedback": "performance",
    "performance_calibration": "performance",
    "talent_profile": "talent",
    "talent_succession": "talent",
}

WAVE6_SETUP_TO_CAPABILITY: dict[str, str] = {
    "job_architecture": "job_architecture",
    "learning": "learning",
    "benefits": "benefits",
    "employee_relations": "employee_relations",
    "engagement": "engagement",
    "comp_planning": "comp_planning",
    "workforce_planning": "workforce_planning",
}

_TRUE = {"1", "true", "yes", "on"}


@dataclass(frozen=True, slots=True)
class CapabilitySpec:
    key: str
    label_en: str
    label_ar: str
    wave: int
    domain_authority_ready: bool
    http_ready: bool
    hr_web_ready: bool
    employee_surface_ready: bool
    manager_surface_ready: bool
    mobile_ready: bool
    employee_surface_required: bool
    manager_surface_required: bool
    mobile_required: bool
    customer_visible: bool
    depends_on: tuple[str, ...]
    http_namespaces: tuple[str, ...]
    setup_unhide: str
    r5_slice: str


def _spec(**kwargs: Any) -> CapabilitySpec:
    return CapabilitySpec(**kwargs)


# Surface flags below are the R5A truth: domain libraries exist; product
# surfaces do not. Flip flags only when that module's R5 surface slice passes.
_CAPABILITIES: tuple[CapabilitySpec, ...] = (
    _spec(
        key="performance",
        label_en="Performance",
        label_ar="الأداء",
        wave=4,
        domain_authority_ready=True,
        http_ready=False,
        hr_web_ready=False,
        employee_surface_ready=False,
        manager_surface_ready=False,
        mobile_ready=False,
        employee_surface_required=True,
        manager_surface_required=True,
        mobile_required=True,
        customer_visible=False,
        depends_on=(),
        http_namespaces=(
            "/dashboard/performance",
            "/app/performance",
        ),
        setup_unhide=(
            "Unhide when http_ready + hr_web_ready + manager_surface_ready + "
            "employee_surface_ready + mobile_ready (manager thin queues). "
            "Calibration admin stays HR Web; do not force heavyweight mobile."
        ),
        r5_slice="R5B",
    ),
    _spec(
        key="talent",
        label_en="Talent",
        label_ar="المواهب",
        wave=4,
        domain_authority_ready=True,
        http_ready=False,
        hr_web_ready=False,
        employee_surface_ready=False,
        manager_surface_ready=False,
        mobile_ready=False,
        employee_surface_required=True,
        manager_surface_required=True,
        mobile_required=False,
        customer_visible=False,
        depends_on=(),
        http_namespaces=(
            "/dashboard/posthire/talent",
            "/dashboard/talent",
            "/app/talent",
        ),
        setup_unhide=(
            "Unhide when http_ready + hr_web_ready + manager_surface_ready + "
            "employee_surface_ready (limited self-profile). HR Mobile thin only; "
            "not large 9-box / succession-framework admin. Never collide with "
            "recruiting talent_pool."
        ),
        r5_slice="R5C",
    ),
    _spec(
        key="job_architecture",
        label_en="Job Architecture",
        label_ar="هيكل الوظائف",
        wave=6,
        domain_authority_ready=True,
        http_ready=False,
        hr_web_ready=False,
        employee_surface_ready=False,
        manager_surface_ready=False,
        mobile_ready=False,
        employee_surface_required=False,
        manager_surface_required=False,
        mobile_required=False,
        customer_visible=False,
        depends_on=(),
        http_namespaces=(
            "/dashboard/job-architecture",
            "/app/job-architecture",
        ),
        setup_unhide=(
            "Unhide when http_ready + hr_web_ready (Setup + catalog authoring). "
            "Manager/employee/mobile are thin-read only and not required to enable. "
            "Not a separate customer SKU; still must not show a dead enable switch."
        ),
        r5_slice="R5D",
    ),
    _spec(
        key="learning",
        label_en="Learning & Development",
        label_ar="التعلم والتطوير",
        wave=6,
        domain_authority_ready=True,
        http_ready=False,
        hr_web_ready=False,
        employee_surface_ready=False,
        manager_surface_ready=False,
        mobile_ready=False,
        employee_surface_required=True,
        manager_surface_required=True,
        mobile_required=False,
        customer_visible=False,
        depends_on=(),
        http_namespaces=(
            "/dashboard/learning",
            "/app/learning",
        ),
        setup_unhide=(
            "Unhide when http_ready + hr_web_ready + manager_surface_ready + "
            "employee_surface_ready. HR Mobile thin is not an enable gate."
        ),
        r5_slice="R5E",
    ),
    _spec(
        key="benefits",
        label_en="Benefits",
        label_ar="المزايا",
        wave=6,
        domain_authority_ready=True,
        http_ready=False,
        hr_web_ready=False,
        employee_surface_ready=False,
        manager_surface_ready=False,
        mobile_ready=False,
        employee_surface_required=True,
        manager_surface_required=False,
        mobile_required=False,
        customer_visible=False,
        depends_on=(),
        http_namespaces=(
            "/dashboard/benefits",
            "/app/benefits",
        ),
        setup_unhide=(
            "Unhide when http_ready + hr_web_ready + employee_surface_ready "
            "(enrollment). Manager private-detail stays fail-closed; not an enable gate."
        ),
        r5_slice="R5F",
    ),
    _spec(
        key="employee_relations",
        label_en="Employee Relations",
        label_ar="علاقات الموظفين",
        wave=6,
        domain_authority_ready=True,
        http_ready=False,
        hr_web_ready=False,
        employee_surface_ready=False,
        manager_surface_ready=False,
        mobile_ready=False,
        employee_surface_required=False,
        manager_surface_required=False,
        mobile_required=True,
        customer_visible=False,
        depends_on=(),
        http_namespaces=(
            "/dashboard/employee-relations",
            "/app/employee-relations",
        ),
        setup_unhide=(
            "Unhide when http_ready + hr_web_ready (sealed ER workspace) + "
            "mobile_ready (thin alerts to authorized ER actors only). "
            "Manager is not an ER surface. Ordinary HR ≠ ER."
        ),
        r5_slice="R5G",
    ),
    _spec(
        key="engagement",
        label_en="Engagement",
        label_ar="المشاركة والارتباط",
        wave=6,
        domain_authority_ready=True,
        http_ready=False,
        hr_web_ready=False,
        employee_surface_ready=False,
        manager_surface_ready=False,
        mobile_ready=False,
        employee_surface_required=True,
        manager_surface_required=True,
        mobile_required=False,
        customer_visible=False,
        depends_on=(),
        http_namespaces=(
            "/dashboard/engagement",
            "/app/engagement",
        ),
        setup_unhide=(
            "Unhide when http_ready + hr_web_ready + employee_surface_ready "
            "(participation) + manager_surface_ready (threshold-gated aggregates)."
        ),
        r5_slice="R5H",
    ),
    _spec(
        key="comp_planning",
        label_en="Compensation Planning",
        label_ar="تخطيط التعويضات",
        wave=6,
        domain_authority_ready=True,
        http_ready=False,
        hr_web_ready=False,
        employee_surface_ready=False,
        manager_surface_ready=False,
        mobile_ready=False,
        employee_surface_required=False,
        manager_surface_required=False,
        mobile_required=False,
        customer_visible=False,
        depends_on=("job_architecture",),
        http_namespaces=(
            "/dashboard/compensation-planning",
            "/app/compensation-planning",
        ),
        setup_unhide=(
            "Unhide when http_ready + hr_web_ready and job_architecture is "
            "customer_enableable. Manager recommend is optional; mobile not heavyweight."
        ),
        r5_slice="R5I",
    ),
    _spec(
        key="workforce_planning",
        label_en="Workforce Planning",
        label_ar="تخطيط القوى العاملة",
        wave=6,
        domain_authority_ready=True,
        http_ready=False,
        hr_web_ready=False,
        employee_surface_ready=False,
        manager_surface_ready=False,
        mobile_ready=False,
        employee_surface_required=False,
        manager_surface_required=False,
        mobile_required=False,
        customer_visible=False,
        depends_on=("job_architecture",),
        http_namespaces=(
            "/dashboard/workforce-planning",
            "/app/workforce-planning",
        ),
        setup_unhide=(
            "Unhide when http_ready + hr_web_ready and job_architecture is "
            "customer_enableable. Mobile thin is not an enable gate."
        ),
        r5_slice="R5J",
    ),
)

CAPABILITY_BY_KEY: dict[str, CapabilitySpec] = {item.key: item for item in _CAPABILITIES}


def _truthy(value: Any) -> bool:
    if value is True:
        return True
    if value is False or value is None:
        return False
    return str(value).strip().lower() in _TRUE


def capability_for_setup_module_key(module_key: str) -> str | None:
    raw = str(module_key or "").strip().lower()
    if raw.startswith("wave4_"):
        return WAVE4_SETUP_TO_CAPABILITY.get(raw[len("wave4_") :])
    if raw.startswith("wave6_"):
        return WAVE6_SETUP_TO_CAPABILITY.get(raw[len("wave6_") :])
    if raw in WAVE4_SETUP_TO_CAPABILITY:
        return WAVE4_SETUP_TO_CAPABILITY[raw]
    if raw in WAVE6_SETUP_TO_CAPABILITY:
        return WAVE6_SETUP_TO_CAPABILITY[raw]
    if raw in CAPABILITY_BY_KEY:
        return raw
    return None


def is_unreleased_capability_key(module_key: str | None) -> bool:
    raw = str(module_key or "").strip().lower()
    if not raw:
        return False
    if raw in CAPABILITY_BY_KEY:
        return True
    mapped = capability_for_setup_module_key(raw)
    return mapped in CAPABILITY_BY_KEY


def spec_for(capability_key: str) -> CapabilitySpec | None:
    return CAPABILITY_BY_KEY.get(str(capability_key or "").strip().lower())


def _surfaces_ready(spec: CapabilitySpec) -> bool:
    if not spec.http_ready or not spec.hr_web_ready:
        return False
    if spec.manager_surface_required and not spec.manager_surface_ready:
        return False
    if spec.employee_surface_required and not spec.employee_surface_ready:
        return False
    if spec.mobile_required and not spec.mobile_ready:
        return False
    return True


def customer_enableable(capability_key: str, *, _stack: frozenset[str] | None = None) -> bool:
    """True only when charter-promised surfaces exist. Domain FULL_PASS is not enough."""
    spec = spec_for(capability_key)
    if spec is None:
        return False
    if not _surfaces_ready(spec):
        return False
    seen = _stack or frozenset()
    if spec.key in seen:
        return False
    nxt = seen | {spec.key}
    for dep in spec.depends_on:
        if not customer_enableable(dep, _stack=nxt):
            return False
    return True


def customer_visible(capability_key: str) -> bool:
    spec = spec_for(capability_key)
    if spec is None:
        return False
    # Prefer omission until the module is actually customer-enableable.
    return bool(spec.customer_visible) and customer_enableable(capability_key)


def customer_usable(*, capability_key: str, stored_enabled: bool, runtime_available: bool) -> bool:
    """Customer-facing usable = enableable ∩ stored entitlement ∩ runtime.

    Stored enabled or env allowlist must never override an unreleased surface.
    """
    if not customer_enableable(capability_key):
        return False
    return bool(stored_enabled) and bool(runtime_available)


def catalog_module_customer_enableable(module_key: str) -> bool:
    """Catalog SKUs (Waves 1–3 + Wave 5 Analytics + Employee App) stay enableable."""
    key = normalize_module_key(module_key)
    if is_unreleased_capability_key(key) or is_unreleased_capability_key(module_key):
        return False
    return key in MODULE_BY_KEY


def readiness_payload(capability_key: str) -> dict[str, Any]:
    spec = spec_for(capability_key)
    if spec is None:
        return {
            "ok": False,
            "error": "unknown_capability",
            "capability_key": capability_key,
            "customer_enableable": False,
            "customer_visible": False,
            "usable": False,
        }
    enableable = customer_enableable(spec.key)
    visible = customer_visible(spec.key)
    return {
        "ok": True,
        "phase": PHASE,
        "contract_version": CONTRACT_VERSION,
        "capability_key": spec.key,
        "label_en": spec.label_en,
        "label_ar": spec.label_ar,
        "wave": spec.wave,
        "r5_slice": spec.r5_slice,
        "domain_authority_ready": spec.domain_authority_ready,
        "http_ready": spec.http_ready,
        "hr_web_ready": spec.hr_web_ready,
        "employee_surface_ready": spec.employee_surface_ready,
        "manager_surface_ready": spec.manager_surface_ready,
        "mobile_ready": spec.mobile_ready,
        "employee_surface_required": spec.employee_surface_required,
        "manager_surface_required": spec.manager_surface_required,
        "mobile_required": spec.mobile_required,
        "depends_on": list(spec.depends_on),
        "http_namespaces": list(spec.http_namespaces),
        "setup_unhide": spec.setup_unhide,
        "customer_enableable": enableable,
        "customer_visible": visible,
        "domain_full_pass_is_not_customer_enableable": True,
    }


def catalog_payload() -> dict[str, Any]:
    items = [readiness_payload(key) for key in UNRELEASED_CAPABILITY_KEYS]
    return {
        "phase": PHASE,
        "contract_version": CONTRACT_VERSION,
        "pass_stamp": PASS_STAMP,
        "customer_enableable_catalog_modules": list(MODULE_KEYS),
        "unreleased_capabilities": items,
        "honesty": {
            "one_readiness_contract": True,
            "domain_full_pass_is_not_customer_enableable": True,
            "prefer_omission_in_setup": True,
            "stored_enabled_does_not_imply_usable": True,
            "env_allowlist_is_not_customer_enablement": True,
            "wave5_analytics_remains_catalog_enableable": "analytics" in MODULE_BY_KEY,
        },
    }


def annotate_policy_payload(setup_module_key: str, payload: Mapping[str, Any] | None) -> dict[str, Any]:
    out = dict(payload or {})
    cap = capability_for_setup_module_key(setup_module_key)
    if not cap:
        return out
    policy = out.get("policy") if isinstance(out.get("policy"), dict) else {}
    stored = _truthy(policy.get("enabled")) if policy else _truthy(out.get("enabled"))
    ready = readiness_payload(cap)
    enableable = bool(ready.get("customer_enableable"))
    out["readiness"] = ready
    out["stored_enabled"] = stored
    out["customer_enableable"] = enableable
    out["customer_visible"] = bool(ready.get("customer_visible"))
    out["usable"] = customer_usable(
        capability_key=cap,
        stored_enabled=stored,
        runtime_available=False,
    )
    out["customer_facing_state"] = "not_released" if not enableable else ("enabled" if stored else "disabled")
    return out


def annotate_wave4_setup(payload: Mapping[str, Any] | None) -> dict[str, Any]:
    out = dict(payload or {})
    modules = dict(out.get("modules") or {})
    annotated: dict[str, Any] = {}
    for key, body in modules.items():
        annotated[key] = annotate_policy_payload(f"wave4_{key}", body if isinstance(body, dict) else {})
    out["modules"] = annotated
    honesty = dict(out.get("honesty") or {})
    honesty.update(
        {
            "customer_enableable": False,
            "customer_visible_in_setup": False,
            "domain_full_pass_is_not_customer_enableable": True,
            "stored_enabled_does_not_imply_usable": True,
        }
    )
    out["honesty"] = honesty
    out["customer_enableable"] = False
    out["customer_visible"] = False
    return out


def annotate_wave6_setup(payload: Mapping[str, Any] | None) -> dict[str, Any]:
    out = dict(payload or {})
    modules = dict(out.get("modules") or {})
    annotated: dict[str, Any] = {}
    for key, body in modules.items():
        annotated[key] = annotate_policy_payload(f"wave6_{key}", body if isinstance(body, dict) else {})
    out["modules"] = annotated
    honesty = dict(out.get("honesty") or {})
    honesty.update(
        {
            "customer_enableable": False,
            "customer_visible_in_setup": False,
            "domain_full_pass_is_not_customer_enableable": True,
            "stored_enabled_does_not_imply_usable": True,
        }
    )
    out["honesty"] = honesty
    out["customer_enableable"] = False
    out["customer_visible"] = False
    return out


def customer_setup_write_block(module_key: str) -> dict[str, Any] | None:
    """HTTP Setup must not enable or mutate unreleased capability policy."""
    cap = capability_for_setup_module_key(module_key)
    if not cap:
        return None
    if customer_enableable(cap):
        return None
    ready = readiness_payload(cap)
    return {
        "error": "capability_not_customer_enableable",
        "capability_key": cap,
        "setup_module_key": str(module_key or "").strip().lower(),
        "customer_enableable": False,
        "customer_visible": False,
        "usable": False,
        "preserved": True,
        "message": "This capability is not available to enable yet.",
        "message_en": "This capability is not available to enable yet.",
        "message_ar": "هذه القدرة غير متاحة للتفعيل بعد.",
        "readiness": ready,
    }


def unreleased_catalog_enable_block(module_key: str) -> dict[str, Any] | None:
    key = normalize_module_key(module_key)
    raw = str(module_key or "").strip().lower()
    cap = key if key in CAPABILITY_BY_KEY else (raw if raw in CAPABILITY_BY_KEY else capability_for_setup_module_key(raw))
    if not cap or customer_enableable(cap):
        return None
    return customer_setup_write_block(cap)


def unavailable_http_detail(capability_key: str) -> dict[str, Any]:
    ready = readiness_payload(capability_key)
    return {
        "error": "capability_not_released",
        "capability_key": capability_key,
        "customer_enableable": False,
        "usable": False,
        "message": "This capability is not available.",
        "message_en": "This capability is not available.",
        "message_ar": "هذه القدرة غير متاحة.",
        "readiness": ready,
    }


def all_http_namespaces() -> list[tuple[str, str]]:
    rows: list[tuple[str, str]] = []
    for spec in _CAPABILITIES:
        for path in spec.http_namespaces:
            rows.append((spec.key, path))
    return rows


def honesty_payload() -> dict[str, Any]:
    return {
        "phase": PHASE,
        "contract_version": CONTRACT_VERSION,
        "pass_stamp": PASS_STAMP,
        "one_readiness_contract": True,
        "domain_full_pass_is_not_customer_enableable": True,
        "prefer_omission_in_setup": True,
        "stored_enabled_does_not_imply_usable": True,
        "env_allowlist_is_not_customer_enablement": True,
        "unreleased_not_in_module_catalog": all(key not in MODULE_BY_KEY for key in UNRELEASED_CAPABILITY_KEYS),
        "catalog_modules_remain_customer_enableable": True,
        "wave5_analytics_unchanged": True,
    }


def assert_catalog_alignment() -> dict[str, Any]:
    leaked = [key for key in UNRELEASED_CAPABILITY_KEYS if key in MODULE_BY_KEY]
    return {
        "ok": len(leaked) == 0,
        "leaked_into_catalog": leaked,
        "catalog_count": len(MODULE_KEYS),
        "unreleased_count": len(UNRELEASED_CAPABILITY_KEYS),
    }


def iter_capabilities() -> Iterable[CapabilitySpec]:
    return _CAPABILITIES
