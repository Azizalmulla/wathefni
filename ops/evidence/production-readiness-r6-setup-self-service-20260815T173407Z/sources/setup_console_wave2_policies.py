#!/usr/bin/env python3
"""Setup Console — Wave 2 Workforce Truth company policies.

Owns company-level configuration surfaces for Attendance / Leave / Shifts /
Payroll feeds / Payment processing / Settlement / OT→Payroll.

Reuses company_modules.settings.wave2_setup overlays + C4/C5/C6 entitlement
tables where present. Env flags remain fail-closed runtime gates; Setup is
the customer-facing policy owner (not env-only).
"""
from __future__ import annotations

import json
from typing import Any

PHASE = "setup_console_wave2"
CONTRACT_VERSION = "wave2_workforce_truth_policies_v1"
WAVE2_MODULE_KEYS = (
    "attendance",
    "leave",
    "shifts",
    "payroll",
    "payment_processing",
    "settlement",
    "ot_to_payroll",
)

DEFAULTS: dict[str, dict[str, Any]] = {
    "attendance": {
        "ingest_enabled": False,
        "correction_enabled": True,
        "use_shift_schedule": False,
    },
    "leave": {
        "enforced": False,
        "legal_pack_attested": False,
        "n_step_enabled": False,
    },
    "shifts": {
        "mss_enabled": False,
        "manager_allowlist_required": True,
    },
    "payroll": {
        "authoritative_finalize": False,
        "feed_attendance": False,
        "feed_leave": False,
        "feed_ot": False,
        "feed_imported": True,
        "manual_inputs_ok": True,
    },
    "payment_processing": {
        "enabled": False,
        "kill_switch_respected": True,
        "acknowledged_is_not_paid": True,
    },
    "settlement": {
        "enabled": False,
        "finalized_is_not_paid": True,
        "not_clearance": True,
    },
    "ot_to_payroll": {
        "enabled": False,
        "ot_money_outside_payroll": False,
    },
}

STATUS_LABELS = {
    "attendance": {"en": "Attendance Truth", "ar": "حقيقة الحضور"},
    "leave": {"en": "Leave Enforcement", "ar": "إنفاذ الإجازات"},
    "shifts": {"en": "Shifts / MSS", "ar": "المناوبات / المديرين"},
    "payroll": {"en": "Payroll Authority", "ar": "سلطة الرواتب"},
    "payment_processing": {"en": "Payment Files", "ar": "ملفات الدفع"},
    "settlement": {"en": "Final Settlement", "ar": "التسوية النهائية"},
    "ot_to_payroll": {"en": "OT → Payroll", "ar": "إضافي → رواتب"},
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
        "setup_owns_wave2_policies": True,
        "env_only_ownership": False,
        "assistant_mutations_in_wave2": False,
        "payment_acknowledged_is_not_paid": True,
        "settlement_finalized_is_not_paid": True,
        "settlement_is_not_clearance": True,
        "payroll_independent_of_attendance_leave_shifts": True,
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


def _save_wave2_overlay(cur: Any, company: str, module_key: str, overlay: dict[str, Any]) -> None:
    """Persist wave2_setup under the commercial module row (attendance/leave/shifts/payroll)."""
    commercial = {
        "attendance": "attendance",
        "leave": "leave",
        "shifts": "shifts",
        "payroll": "payroll",
        "payment_processing": "payroll",
        "settlement": "payroll",
        "ot_to_payroll": "attendance",
    }.get(module_key, "payroll")
    row = _module_row(cur, company, commercial)
    settings = dict(row.get("settings") or {})
    wave2 = dict(settings.get("wave2_setup") or {})
    wave2[module_key] = {**(DEFAULTS.get(module_key) or {}), **(wave2.get(module_key) or {}), **overlay}
    settings["wave2_setup"] = wave2
    cur.execute(
        """
        INSERT INTO company_modules (company_code, module_key, enabled, source, settings, updated_at)
        VALUES (%s,%s,%s,'setup_console_wave2',%s::jsonb, now())
        ON CONFLICT (company_code, module_key) DO UPDATE SET
          settings=EXCLUDED.settings,
          source=EXCLUDED.source,
          updated_at=now()
        """,
        (company, commercial, bool(row.get("enabled")), json.dumps(settings, default=str)),
    )


def _read_overlay(cur: Any, company: str, module_key: str) -> dict[str, Any]:
    commercial = {
        "attendance": "attendance",
        "leave": "leave",
        "shifts": "shifts",
        "payroll": "payroll",
        "payment_processing": "payroll",
        "settlement": "payroll",
        "ot_to_payroll": "attendance",
    }.get(module_key, "payroll")
    settings = _module_row(cur, company, commercial).get("settings") or {}
    wave2 = settings.get("wave2_setup") if isinstance(settings.get("wave2_setup"), dict) else {}
    overlay = wave2.get(module_key) if isinstance(wave2.get(module_key), dict) else {}
    return {**(DEFAULTS.get(module_key) or {}), **overlay}


def get_wave2_module_policy(cur: Any, company_code: str, module_key: str) -> dict[str, Any]:
    company = _company(company_code)
    key = str(module_key or "").strip()
    if key not in WAVE2_MODULE_KEYS:
        return {"ok": False, "error": "unknown_wave2_module", "allowed": list(WAVE2_MODULE_KEYS)}
    policy = _read_overlay(cur, company, key)
    if key == "leave":
        try:
            import setup_console_policy_convergence as _conv

            policy["enforced"] = _conv.read_leave_enforced(cur, company)
        except Exception:
            pass
    commercial_key = {
        "attendance": "attendance",
        "leave": "leave",
        "shifts": "shifts",
        "payroll": "payroll",
        "payment_processing": "payroll",
        "settlement": "payroll",
        "ot_to_payroll": "attendance",
    }[key]
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


def get_all_wave2_policies(cur: Any, company_code: str) -> dict[str, Any]:
    company = _company(company_code)
    modules = {}
    for key in WAVE2_MODULE_KEYS:
        modules[key] = get_wave2_module_policy(cur, company, key)
    return {
        "ok": True,
        "company_code": company,
        "modules": modules,
        "phase": PHASE,
        "contract_version": CONTRACT_VERSION,
        **honesty_payload(),
    }


def patch_wave2_module_policy(
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
    if key not in WAVE2_MODULE_KEYS:
        return {"ok": False, "error": "unknown_wave2_module", "allowed": list(WAVE2_MODULE_KEYS)}
    body = dict(payload or {})
    # Normalize common nesting
    if "required" in body and isinstance(body["required"], dict):
        body = {**body["required"], **{k: v for k, v in body.items() if k != "required"}}
    allowed = set((DEFAULTS.get(key) or {}).keys())
    overlay = {k: body[k] for k in body if k in allowed}
    if not overlay:
        return {"ok": False, "error": "no_allowed_fields", "allowed": sorted(allowed)}
    _save_wave2_overlay(cur, company, key, overlay)
    if key == "leave" and "enforced" in overlay:
        try:
            import setup_console_policy_convergence as _conv

            _conv.sync_leave_enforced(
                cur,
                company,
                enforced=bool(overlay.get("enforced")),
                actor_phone=actor_phone,
                reason=reason,
            )
        except Exception:
            pass

    # Best-effort sync into C4/C5/C6 entitlement tables when those modules are importable.
    try:
        if key == "payroll" and "authoritative_finalize" in overlay:
            import payroll_authoritative_c4 as c4

            if overlay["authoritative_finalize"]:
                c4.enable_company_authoritative_finalize(
                    cur, company_code=company, actor_phone=actor_phone, reason=reason
                )
            else:
                c4.disable_company_authoritative_finalize(
                    cur, company_code=company, actor_phone=actor_phone, reason=reason
                )
        if key == "payment_processing" and "enabled" in overlay:
            import payroll_payslip_payment_c5 as c5

            if overlay["enabled"]:
                c5.enable_company_payment_processing(
                    cur, company_code=company, actor_phone=actor_phone, reason=reason
                )
            else:
                c5.disable_company_payment_processing(
                    cur, company_code=company, actor_phone=actor_phone, reason=reason
                )
        if key in {"settlement", "ot_to_payroll"}:
            import payroll_settlement_ot_c6 as c6

            current = get_wave2_module_policy(cur, company, "settlement").get("policy") or {}
            ot = get_wave2_module_policy(cur, company, "ot_to_payroll").get("policy") or {}
            if key == "settlement":
                current = {**current, **overlay}
            if key == "ot_to_payroll":
                ot = {**ot, **overlay}
            if current.get("enabled") or ot.get("enabled"):
                c6.enable_company_settlement_ot(
                    cur,
                    company_code=company,
                    actor_phone=actor_phone,
                    reason=reason,
                    settlement_enabled=bool(current.get("enabled")),
                    ot_authorization_enabled=True,
                    ot_to_payroll_enabled=bool(ot.get("enabled")),
                )
            else:
                c6.disable_company_settlement_ot(
                    cur, company_code=company, actor_phone=actor_phone, reason=reason
                )
    except Exception as exc:
        # Overlay persisted; entitlement sync is best-effort (runtime may be off).
        return {
            **get_wave2_module_policy(cur, company, key),
            "sync_warning": str(exc)[:200],
        }

    return get_wave2_module_policy(cur, company, key)


def modularity_matrix_configs() -> list[dict[str, Any]]:
    """Canonical W2-M01 matrix: alone + meaningful combinations."""
    return [
        {"name": "attendance_alone", "modules": {"attendance": True}},
        {"name": "leave_alone", "modules": {"leave": True}},
        {"name": "shifts_alone", "modules": {"shifts": True}},
        {"name": "payroll_alone_manual", "modules": {"payroll": True}, "feeds": {"manual": True}},
        {"name": "attendance_payroll", "modules": {"attendance": True, "payroll": True}, "feeds": {"attendance": True}},
        {"name": "leave_payroll", "modules": {"leave": True, "payroll": True}, "feeds": {"leave": True}},
        {"name": "ot_payroll_optional", "modules": {"attendance": True, "payroll": True}, "feeds": {"ot": True}},
        {"name": "shifts_attendance", "modules": {"shifts": True, "attendance": True}},
        {
            "name": "full_workforce_truth",
            "modules": {
                "attendance": True,
                "leave": True,
                "shifts": True,
                "payroll": True,
                "payment_processing": True,
                "settlement": True,
            },
            "feeds": {"attendance": True, "leave": True, "ot": True},
        },
        {"name": "all_disabled", "modules": {}},
    ]
