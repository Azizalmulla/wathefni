#!/usr/bin/env python3
"""Setup Console — Wave 3 Employee Lifecycle company policies.

Owns company-level configuration for employment changes, ESS letters/dependents,
resignation/termination/EOC, notice, offboarding/clearance, settlement/access
gates, exit interview, and rehire eligibility.

Env flags remain fail-closed runtime gates; Setup is the customer-facing policy
owner (not env-only long-term configuration).
"""
from __future__ import annotations

import json
from typing import Any

PHASE = "setup_console_wave3"
CONTRACT_VERSION = "wave3_employee_lifecycle_policies_v1"
WAVE3_MODULE_KEYS = (
    "employment_change",
    "ess_letters_dependents",
    "exit_intent",
    "offboarding",
    "exit_close",
)

DEFAULTS: dict[str, dict[str, Any]] = {
    "employment_change": {
        "enabled": False,
        "require_distinct_approver": True,
        "enabled_types": [
            "promotion",
            "transfer",
            "manager_change",
            "position_change",
            "salary_change",
            "secondment",
            "secondment_return",
        ],
        "optional_payroll_link": False,
    },
    "ess_letters_dependents": {
        "enabled": False,
        "letters_enabled": True,
        "dependents_enabled": True,
        "dependent_review_required": True,
        "salary_cert_without_payroll_ok": True,
    },
    "exit_intent": {
        "enabled": False,
        "resignation_enabled": True,
        "termination_enabled": False,
        "eoc_enabled": True,
        "notice_policy_days": 30,
        "require_distinct_approver": True,
    },
    "offboarding": {
        "enabled": False,
        "template_owned_by_setup": True,
        "clearance_sla_days": 7,
        "waiver_roles": ["hr"],
        "idp_optional": True,
        "settlement_optional": True,
    },
    "exit_close": {
        "enabled": False,
        "require_settlement_ack": False,
        "allow_settlement_waiver": True,
        "require_access_revoke_ack": False,
        "require_last_working_day_reached": True,
        "exit_interview_enabled": False,
        "exit_interview_required": False,
        "rehire_eligibility_default": "eligible",
    },
}

STATUS_LABELS = {
    "employment_change": {"en": "Employment Changes", "ar": "تغييرات التوظيف"},
    "ess_letters_dependents": {"en": "ESS Letters & Dependents", "ar": "خطابات و مرافقون"},
    "exit_intent": {"en": "Resignation / Termination / EOC", "ar": "استقالة / إنهاء / نهاية عقد"},
    "offboarding": {"en": "Offboarding & Clearance", "ar": "إنهاء الخدمة والمخالصة"},
    "exit_close": {"en": "Exit Close & Alumni", "ar": "إغلاق الخروج والخريجون"},
}

# Commercial module_key used for company_modules overlay storage
_COMMERCIAL = {
    "employment_change": "employment_change",
    "ess_letters_dependents": "ess",
    "exit_intent": "exit_intent",
    "offboarding": "offboarding",
    "exit_close": "offboarding",
}


def _company(code: str) -> str:
    return str(code or "").upper()


def status_label(module_key: str, *, lang: str = "en") -> str:
    pack = STATUS_LABELS.get(module_key) or {"en": module_key, "ar": module_key}
    return str(pack.get("ar" if lang.lower().startswith("ar") else "en"))


def honesty_payload() -> dict[str, Any]:
    return {
        "phase": PHASE,
        "contract_version": CONTRACT_VERSION,
        "setup_owns_wave3_policies": True,
        "env_only_ownership": False,
        "assistant_mutations_in_wave3": False,
        "real_termination_dark_by_default": True,
        "settlement_finalized_is_not_paid": True,
        "settlement_is_not_clearance": True,
        "sole_employment_left_authority": "exit_close",
        "commercial_module_offboarding": True,
    }


def _module_row(cur: Any, company: str, module_key: str) -> dict[str, Any]:
    try:
        cur.execute(
            """
            SELECT enabled, settings FROM company_modules
            WHERE company_code=%s AND module_key=%s
            LIMIT 1
            """,
            (company, module_key),
        )
        row = cur.fetchone()
    except Exception:
        return {"enabled": False, "settings": {}}
    if not row:
        return {"enabled": False, "settings": {}}
    d = dict(row) if isinstance(row, dict) else {"enabled": row[0], "settings": row[1]}
    settings = d.get("settings") or {}
    if isinstance(settings, str):
        try:
            settings = json.loads(settings)
        except Exception:
            settings = {}
    if not isinstance(settings, dict):
        settings = {}
    return {"enabled": bool(d.get("enabled")), "settings": settings}


def _save_wave3_overlay(cur: Any, company: str, module_key: str, overlay: dict[str, Any]) -> None:
    commercial = _COMMERCIAL.get(module_key, "offboarding")
    row = _module_row(cur, company, commercial)
    settings = dict(row.get("settings") or {})
    wave3 = dict(settings.get("wave3_setup") or {})
    wave3[module_key] = {**(DEFAULTS.get(module_key) or {}), **(wave3.get(module_key) or {}), **overlay}
    settings["wave3_setup"] = wave3
    cur.execute(
        """
        INSERT INTO company_modules (company_code, module_key, enabled, source, settings, updated_at)
        VALUES (%s,%s,%s,'setup_console_wave3',%s::jsonb, now())
        ON CONFLICT (company_code, module_key) DO UPDATE SET
          settings=EXCLUDED.settings,
          source=EXCLUDED.source,
          updated_at=now()
        """,
        (company, commercial, bool(row.get("enabled")), json.dumps(settings, default=str)),
    )


def _read_overlay(cur: Any, company: str, module_key: str) -> dict[str, Any]:
    commercial = _COMMERCIAL.get(module_key, "offboarding")
    settings = _module_row(cur, company, commercial).get("settings") or {}
    wave3 = settings.get("wave3_setup") if isinstance(settings.get("wave3_setup"), dict) else {}
    overlay = wave3.get(module_key) if isinstance(wave3.get(module_key), dict) else {}
    return {**(DEFAULTS.get(module_key) or {}), **overlay}


def get_wave3_module_policy(cur: Any, company_code: str, module_key: str) -> dict[str, Any]:
    company = _company(company_code)
    key = str(module_key or "").strip()
    if key not in WAVE3_MODULE_KEYS:
        return {"ok": False, "error": "unknown_wave3_module", "allowed": list(WAVE3_MODULE_KEYS)}
    policy = _read_overlay(cur, company, key)
    commercial_key = _COMMERCIAL[key]
    mod = _module_row(cur, company, commercial_key)
    return {
        "ok": True,
        "module_key": key,
        "commercial_module_key": commercial_key,
        "commercial_enabled": bool(mod.get("enabled")),
        "policy": policy,
        "label_en": status_label(key, lang="en"),
        "label_ar": status_label(key, lang="ar"),
        "ownership": {"company_policy": "setup_console", "runtime_gate": "env_allowlist_fail_closed"},
        "phase": PHASE,
        **honesty_payload(),
    }


def get_all_wave3_policies(cur: Any, company_code: str) -> dict[str, Any]:
    company = _company(company_code)
    modules = {key: get_wave3_module_policy(cur, company, key) for key in WAVE3_MODULE_KEYS}
    return {
        "ok": True,
        "company_code": company,
        "modules": modules,
        "phase": PHASE,
        "contract_version": CONTRACT_VERSION,
        **honesty_payload(),
    }


def patch_wave3_module_policy(
    cur: Any,
    *,
    company_code: str,
    module_key: str,
    actor_phone: str,
    reason: str,
    payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if not str(reason or "").strip():
        return {"ok": False, "error": "audit_reason_required"}
    company = _company(company_code)
    key = str(module_key or "").strip()
    if key not in WAVE3_MODULE_KEYS:
        return {"ok": False, "error": "unknown_wave3_module", "allowed": list(WAVE3_MODULE_KEYS)}
    body = dict(payload or {})
    if "required" in body and isinstance(body["required"], dict):
        body = {**body["required"], **{k: v for k, v in body.items() if k != "required"}}
    allowed = set((DEFAULTS.get(key) or {}).keys())
    overlay = {k: body[k] for k in body if k in allowed}
    if not overlay:
        return {"ok": False, "error": "no_allowed_fields", "allowed": sorted(allowed)}
    _save_wave3_overlay(cur, company, key, overlay)
    _ = actor_phone
    return get_wave3_module_policy(cur, company, key)


def modularity_matrix_configs() -> list[dict[str, Any]]:
    """Canonical Wave 3 product modularity matrix."""
    return [
        {"name": "employment_changes_only", "modules": {"employment_change": True}},
        {"name": "ess_letters_dependents_only", "modules": {"ess_letters_dependents": True}},
        {
            "name": "resignation_without_offboarding",
            "modules": {"exit_intent": True},
            "notes": "honest handoff; no empty offboarding shell",
        },
        {
            "name": "offboarding_without_payroll",
            "modules": {"exit_intent": True, "offboarding": True, "exit_close": True},
            "capabilities": {"settlement": False, "idp": False},
        },
        {
            "name": "offboarding_without_idp",
            "modules": {"exit_intent": True, "offboarding": True, "exit_close": True},
            "capabilities": {"settlement": False, "idp": False},
        },
        {
            "name": "offboarding_plus_payroll",
            "modules": {"exit_intent": True, "offboarding": True, "exit_close": True},
            "capabilities": {"settlement": True, "idp": False},
        },
        {
            "name": "offboarding_plus_idp",
            "modules": {"exit_intent": True, "offboarding": True, "exit_close": True},
            "capabilities": {"settlement": False, "idp": True},
        },
        {
            "name": "full_wave3_suite",
            "modules": {
                "employment_change": True,
                "ess_letters_dependents": True,
                "exit_intent": True,
                "offboarding": True,
                "exit_close": True,
            },
            "capabilities": {"settlement": True, "idp": True},
        },
        {"name": "all_disabled", "modules": {}},
    ]
