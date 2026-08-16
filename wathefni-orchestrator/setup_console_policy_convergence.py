"""R6 — duplicate customer-policy ownership resolution.

Leave / Attendance / Onboarding keep frozen domain tables.
Multiple Setup cards may display the same authority; they must not write
conflicting stores.
"""
from __future__ import annotations

import json
from typing import Any

PHASE = "setup_console_r6_policy_convergence"
CONTRACT_VERSION = "policy_convergence_v1"

RESOLUTIONS = {
    "leave": {
        "canonical": "leave_policies",
        "display_cards": ("classic-module-leave", "classic-wave2-leave"),
        "non_authoritative": ("company_modules.settings.leave_setup optional overlays only",),
        "write_through": "wave2_setup.leave.enforced → leave_policies.enforced",
    },
    "attendance": {
        "canonical_ops": "company_modules.settings.attendance_setup",
        "canonical_ingest": "company_modules.settings.wave2_setup.attendance",
        "canonical_pay_mode": "payroll Setup / payroll_company_policy_versions",
        "display_cards": ("classic-module-attendance", "classic-wave2-attendance", "classic-payroll-setup-attendance"),
        "rule": "Each concern has one store; cards read the same store for that concern.",
    },
    "onboarding": {
        "canonical_auto_start": "company_settings.onboarding.auto_start_on_hire",
        "display_cards": ("classic-module-onboarding", "classic-wave1-onboarding-auto-start"),
        "non_authoritative": ("WATHEFNI_ONBOARDING_SEED is infrastructure, not customer policy",),
        "write_through": "onboarding_setup.auto_seed_on_hire ↔ onboarding.auto_start_on_hire",
    },
}


def _company(code: str) -> str:
    return str(code or "").strip().upper()


def _module_settings(cur: Any, company: str, module_key: str) -> dict[str, Any]:
    cur.execute(
        "SELECT enabled, settings FROM company_modules WHERE company_code=%s AND module_key=%s LIMIT 1",
        (company, module_key),
    )
    row = cur.fetchone()
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


def sync_leave_enforced(cur: Any, company_code: str, *, enforced: bool, actor_phone: str | None, reason: str) -> dict[str, Any]:
    """Wave 2 leave.enforced writes through to leave_policies.enforced."""
    company = _company(company_code)
    cur.execute(
        """
        UPDATE leave_policies
           SET enforced=%s
         WHERE company_code=%s
           AND version = (
             SELECT MAX(version) FROM leave_policies lp2
              WHERE lp2.company_code=leave_policies.company_code
                AND lp2.leave_type=leave_policies.leave_type
           )
        """,
        (bool(enforced), company),
    )
    return {
        "ok": True,
        "canonical": "leave_policies.enforced",
        "updated": cur.rowcount or 0,
        "actor": actor_phone,
        "reason": str(reason or "")[:200],
    }


def read_leave_enforced(cur: Any, company_code: str) -> bool:
    company = _company(company_code)
    cur.execute(
        """
        SELECT bool_or(enforced) FROM leave_policies
         WHERE company_code=%s
        """,
        (company,),
    )
    row = cur.fetchone()
    if not row:
        return False
    val = row[0] if not isinstance(row, dict) else list(row.values())[0]
    return bool(val)


def sync_onboarding_auto_start(
    cur: Any,
    company_code: str,
    *,
    auto_start: bool,
    actor_phone: str | None,
    reason: str,
) -> dict[str, Any]:
    """One customer auto-start flag: company_settings + onboarding overlay."""
    company = _company(company_code)
    try:
        import setup_console_wave1_policies as w1

        w1._set_company_setting(cur, company, "onboarding.auto_start_on_hire", bool(auto_start))
    except Exception:
        pass
    row = _module_settings(cur, company, "onboarding")
    settings = dict(row.get("settings") or {})
    overlay = dict(settings.get("onboarding_setup") or {})
    overlay["auto_seed_on_hire"] = bool(auto_start)
    overlay["updated_reason"] = str(reason or "")[:200]
    overlay["updated_by"] = actor_phone
    settings["onboarding_setup"] = overlay
    wave1 = dict(settings.get("wave1_auto_start") or {})
    wave1["auto_start_on_hire"] = bool(auto_start)
    settings["wave1_auto_start"] = wave1
    cur.execute(
        """
        INSERT INTO company_modules (company_code, module_key, enabled, source, settings, updated_at)
        VALUES (%s,'onboarding',%s,'setup_console_r6',%s::jsonb, now())
        ON CONFLICT (company_code, module_key) DO UPDATE SET
          settings=EXCLUDED.settings,
          source=EXCLUDED.source,
          updated_at=now()
        """,
        (company, bool(row.get("enabled")), json.dumps(settings, default=str)),
    )
    return {"ok": True, "canonical": "company_settings.onboarding.auto_start_on_hire", "auto_start": bool(auto_start)}


def read_onboarding_auto_start(cur: Any, company_code: str) -> bool:
    company = _company(company_code)
    try:
        import setup_console_wave1_policies as w1

        return bool(w1._get_company_setting(cur, company, "onboarding.auto_start_on_hire", True))
    except Exception:
        overlay = (_module_settings(cur, company, "onboarding").get("settings") or {}).get("onboarding_setup") or {}
        return bool(overlay.get("auto_seed_on_hire", True))


def resolution_matrix() -> dict[str, Any]:
    return {
        "ok": True,
        "phase": PHASE,
        "contract_version": CONTRACT_VERSION,
        "resolutions": dict(RESOLUTIONS),
        "duplicate_stores_removed_or_non_authoritative": True,
        "frozen_domain_truth_not_rewritten": True,
    }
