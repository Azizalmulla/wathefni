#!/usr/bin/env python3
"""Wave 2 C3 — Shifts MSS production unlock (company-scoped).

Owner-approved under WAVE2_WORKFORCE_TRUTH_CHARTER (2026-08-11).

Gates (fail-closed):
  1) WATHEFNI_SHIFTS_MSS_C3 must be on (global kill; prod stays off)
  2) company must be in WATHEFNI_SHIFTS_MSS_COMPANIES
     (empty allowlist = nobody — never “all companies”)
  3) manager phone must be in WATHEFNI_SHIFTS_MSS_MANAGER_ALLOWLIST
     (separate from frozen empty WATHEFNI_SHIFTS_MANAGER_ALLOWLIST)
  4) manager must have a non-empty real manager_scopes binding

Does NOT redesign shift_assignment / open / swap SMs.
Does NOT populate the global Wave-3 MANAGER_ALLOWLIST.
Does NOT require Attendance. Does not mutate Payroll money.
"""
from __future__ import annotations

import os
from typing import Any

PHASE = "shifts_mss_c3"
CONTRACT_VERSION = "shifts_mss_c3_v1"
_ON = {"1", "true", "yes", "on"}

# Canonical EN/AR status contracts reused by MSS surfaces (prove-only; SM unchanged).
STATUS_LABELS = {
    "scheduled": {"en": "Scheduled", "ar": "مجدول"},
    "cancelled": {"en": "Cancelled", "ar": "ملغى"},
    "requested": {"en": "Requested", "ar": "مطلوب"},
    "approved": {"en": "Approved", "ar": "موافق عليه"},
    "rejected": {"en": "Rejected", "ar": "مرفوض"},
    "open": {"en": "Open", "ar": "مفتوح"},
    "claimed": {"en": "Claimed", "ar": "تم التقديم"},
}


def _env_on(name: str, default: str = "off") -> bool:
    return (os.environ.get(name) or default).strip().lower() in _ON


def _digits(value: Any) -> str:
    return "".join(ch for ch in str(value or "") if ch.isdigit())


def company_code_norm(company_code: str | None) -> str:
    return str(company_code or "").strip().upper()


def shifts_mss_c3_runtime_on() -> bool:
    return _env_on("WATHEFNI_SHIFTS_MSS_C3", "off")


def mss_company_allowlist() -> set[str]:
    """Empty = nobody (fail closed)."""
    raw = str(os.environ.get("WATHEFNI_SHIFTS_MSS_COMPANIES") or "").strip()
    if not raw:
        return set()
    return {p.strip().upper() for p in raw.split(",") if p.strip()}


def mss_manager_allowlist() -> set[str]:
    """Company-entitled MSS manager phones. Empty = no MSS managers.

    Intentionally separate from WATHEFNI_SHIFTS_MANAGER_ALLOWLIST so the Wave 6C
    global boundary (empty manager allowlist) remains intact unless this C3 gate
    is process-scoped for a named company.
    """
    raw = str(os.environ.get("WATHEFNI_SHIFTS_MSS_MANAGER_ALLOWLIST") or "").strip()
    if not raw:
        return set()
    return {_digits(p) for p in raw.split(",") if _digits(p)}


def mss_enabled_for_company(company_code: str | None) -> dict[str, Any]:
    company = company_code_norm(company_code)
    if not company:
        return {"ok": False, "enabled": False, "error": "company_required", "phase": PHASE}
    if not shifts_mss_c3_runtime_on():
        return {
            "ok": False,
            "enabled": False,
            "error": "shifts_mss_c3_off",
            "gate": "runtime_flag",
            "phase": PHASE,
            "read_only": True,
            "message": "Shifts MSS C3 runtime is off (production default).",
        }
    allow = mss_company_allowlist()
    if not allow:
        return {
            "ok": False,
            "enabled": False,
            "error": "shifts_mss_company_not_allowlisted",
            "gate": "company_allowlist",
            "phase": PHASE,
            "read_only": True,
            "message": "MSS company allowlist empty — fail closed (nobody).",
        }
    if company not in allow:
        return {
            "ok": False,
            "enabled": False,
            "error": "shifts_mss_company_not_allowlisted",
            "gate": "company_allowlist",
            "phase": PHASE,
            "company_code": company,
            "read_only": True,
        }
    return {
        "ok": True,
        "enabled": True,
        "company_code": company,
        "phase": PHASE,
        "contract_version": CONTRACT_VERSION,
        "read_only": False,
    }


def actor_is_mss_manager_allowlisted(actor_phone: str | None) -> bool:
    d = _digits(actor_phone)
    return bool(d) and d in mss_manager_allowlist()


def status_label(status: str | None, *, lang: str = "en") -> str:
    key = str(status or "").strip().lower()
    pack = STATUS_LABELS.get(key) or {"en": key or "unknown", "ar": key or "غير معروف"}
    return str(pack.get("ar" if lang.lower().startswith("ar") else "en"))


def honesty_payload(*, company_code: str | None = None) -> dict[str, Any]:
    gate = mss_enabled_for_company(company_code) if company_code else {"ok": False, "enabled": False}
    return {
        "phase": PHASE,
        "contract_version": CONTRACT_VERSION,
        "mss_enabled": bool(gate.get("ok")),
        "payroll_money": False,
        "leave_balances_mutated": False,
        "attendance_authority_mutated": False,
        "attendance_required": False,
        "global_manager_allowlist_untouched": True,
        "self_decision": False,
        "read_only": bool(gate.get("read_only", True)),
    }


def manager_has_real_scope(
    *,
    company_code: str,
    manager_phone: str | None,
    scope_resolver: Any | None = None,
) -> dict[str, Any]:
    """Require non-empty restricted manager scope (branch/team/direct)."""
    company = company_code_norm(company_code)
    phone = _digits(manager_phone)
    if not phone:
        return {"ok": False, "error": "manager_phone_required", "phase": PHASE}
    if scope_resolver is None:
        import app as _app

        scope_resolver = _app.manager_scope_context
    scope = scope_resolver(
        phone,
        company,
        actor_role="manager",
        require_explicit_scope=True,
    )
    if scope.get("configuration_error"):
        return {
            "ok": False,
            "error": "mss_manager_scope_required",
            "configuration_error": scope.get("configuration_error"),
            "phase": PHASE,
            "scope": scope,
        }
    if not scope.get("restricted"):
        return {
            "ok": False,
            "error": "mss_manager_scope_required",
            "message": "MSS managers must have a non-empty restricted scope (not company-wide).",
            "phase": PHASE,
            "scope": scope,
        }
    has_members = bool(
        scope.get("branch_keys") or scope.get("team_keys") or scope.get("direct_employee_keys")
    )
    if not has_members:
        return {
            "ok": False,
            "error": "mss_manager_scope_empty",
            "phase": PHASE,
            "scope": scope,
        }
    return {"ok": True, "scope": scope, "phase": PHASE}


def mss_manager_mutation_gate(
    *,
    actor_phone: str | None,
    company_code: str | None,
    require_scope: bool = True,
    scope_resolver: Any | None = None,
) -> dict[str, Any]:
    """True when actor may perform MSS mutations for the company under C3."""
    gate = mss_enabled_for_company(company_code)
    if not gate.get("ok"):
        return {**gate, "error": gate.get("error") or "shifts_mss_c3_off"}
    if not actor_is_mss_manager_allowlisted(actor_phone):
        return {
            "ok": False,
            "error": "shifts_mss_manager_not_allowlisted",
            "gate": "mss_manager_allowlist",
            "phase": PHASE,
            "company_code": company_code_norm(company_code),
            **honesty_payload(company_code=company_code),
        }
    if require_scope:
        scoped = manager_has_real_scope(
            company_code=company_code_norm(company_code),
            manager_phone=actor_phone,
            scope_resolver=scope_resolver,
        )
        if not scoped.get("ok"):
            return {**scoped, **honesty_payload(company_code=company_code)}
        return {
            "ok": True,
            "company_code": company_code_norm(company_code),
            "phase": PHASE,
            "scope": scoped.get("scope"),
            **honesty_payload(company_code=company_code),
        }
    return {
        "ok": True,
        "company_code": company_code_norm(company_code),
        "phase": PHASE,
        **honesty_payload(company_code=company_code),
    }


def mss_mutation_allowed_via_c3(
    *,
    actor_phone: str | None,
    company_code: str | None,
) -> bool:
    """Lightweight allow check used by Wave 3 real_mutation_denied.

    Scope is enforced at the assignment/swap path via viewer_phone +
    manager_scope_allows_employee. This gate only unlocks the allowlist for
    company-entitled MSS managers when C3 is on.
    """
    gate = mss_enabled_for_company(company_code)
    if not gate.get("ok"):
        return False
    return actor_is_mss_manager_allowlisted(actor_phone)


def employee_view_self_only(
    *,
    viewer_employee_key: str | None,
    row_employee_key: str | None,
) -> bool:
    """Employee surfaces may only see own shift rows."""
    a = str(viewer_employee_key or "").strip()
    b = str(row_employee_key or "").strip()
    return bool(a) and a == b


def rollback_guidance() -> dict[str, Any]:
    return {
        "ok": True,
        "phase": PHASE,
        "steps": [
            "WATHEFNI_SHIFTS_MSS_C3=off",
            "Clear WATHEFNI_SHIFTS_MSS_COMPANIES",
            "Clear WATHEFNI_SHIFTS_MSS_MANAGER_ALLOWLIST",
            "Keep WATHEFNI_SHIFTS_MANAGER_ALLOWLIST empty (Wave 6C boundary)",
        ],
    }
