"""Shifts Wave 3 — controlled scheduling UX and real-operation readiness.

- Named WATHEFNI HR allowlist for real assignment mutations
- Named scoped-manager allowlist (phone digits)
- Broad employee app remains disabled here
- Talal remains read-only unless separately qualified
- Real mutations require audit reason + concurrency token (enforced at dashboard routes)
- Operator timers / real reminder sending remain disabled unless explicitly approved

Does NOT: templates, recurring, rotations, publish, open shifts, PAM, Payroll money.
Does NOT enable production real mutations by default (gate fail-closed when allowlist empty
or REAL_MUTATION_GATE unset/off in production until authorized).
"""
from __future__ import annotations

import os
from typing import Any

SHIFTS_WAVE3_VERSION = "3.1.0"
_ON = {"1", "true", "yes", "on"}

# Placeholder named allowlists — populate via env for controlled readiness.
# Empty + gate on ⇒ no real mutations (fail closed). Synthetic subjects still allowed
# under Wave 1/2/3B SYNTHETIC_ONLY markers.
DEFAULT_HR_ALLOWLIST: tuple[str, ...] = ()
DEFAULT_MANAGER_ALLOWLIST: tuple[str, ...] = ()

# Wave 3B production synthetic UX canary markers (never real employees).
DEFAULT_W3_SYNTHETIC_KEY_MARKERS = ("SHW3B", "SHW3B-SYNTH|")
DEFAULT_W3_SYNTHETIC_PHONE_PREFIXES = ("965531",)


def _digits(value: Any) -> str:
    return "".join(ch for ch in str(value or "") if ch.isdigit())


def shifts_wave3_enabled() -> bool:
    """UX enrich + controlled readiness helpers. Default on outside production."""
    if str(os.environ.get("WATHEFNI_SHIFTS_WAVE3_KILL") or "").strip().lower() in _ON:
        return False
    raw = os.environ.get("WATHEFNI_SHIFTS_WAVE3")
    if raw is None or str(raw).strip() == "":
        return (os.environ.get("WATHEFNI_ENV") or "").strip().lower() != "production"
    return str(raw).strip().lower() in _ON


def shifts_wave3_companies() -> set[str]:
    raw = str(os.environ.get("WATHEFNI_SHIFTS_WAVE3_COMPANIES") or "WATHEFNI").strip()
    return {p.strip().upper() for p in raw.split(",") if p.strip()}


def shifts_wave3_enabled_for_company(company_code: str | None) -> bool:
    if not shifts_wave3_enabled():
        return False
    companies = shifts_wave3_companies()
    if not companies:
        return False
    return (company_code or "").upper() in companies


def real_mutation_gate_enabled() -> bool:
    """When on, non-synthetic shift mutations require allowlisted actor phone."""
    if not shifts_wave3_enabled():
        return False
    raw = os.environ.get("WATHEFNI_SHIFTS_REAL_MUTATION_GATE")
    if raw is None or str(raw).strip() == "":
        # Fail-closed default in production readiness posture.
        return (os.environ.get("WATHEFNI_ENV") or "").strip().lower() == "production"
    return str(raw).strip().lower() in _ON


def hr_mutation_allowlist() -> set[str]:
    raw = str(os.environ.get("WATHEFNI_SHIFTS_HR_ALLOWLIST") or "").strip()
    if not raw:
        return {_digits(p) for p in DEFAULT_HR_ALLOWLIST if _digits(p)}
    return {_digits(p) for p in raw.split(",") if _digits(p)}


def manager_mutation_allowlist() -> set[str]:
    raw = str(os.environ.get("WATHEFNI_SHIFTS_MANAGER_ALLOWLIST") or "").strip()
    if not raw:
        return {_digits(p) for p in DEFAULT_MANAGER_ALLOWLIST if _digits(p)}
    return {_digits(p) for p in raw.split(",") if _digits(p)}


def actor_allowlisted_for_real_mutation(actor_phone: str | None) -> bool:
    d = _digits(actor_phone)
    if not d:
        return False
    return d in hr_mutation_allowlist() or d in manager_mutation_allowlist()


def actor_is_hr_allowlisted(actor_phone: str | None) -> bool:
    d = _digits(actor_phone)
    return bool(d) and d in hr_mutation_allowlist()


def actor_is_manager_allowlisted(actor_phone: str | None) -> bool:
    d = _digits(actor_phone)
    return bool(d) and d in manager_mutation_allowlist()


def real_reminders_enabled() -> bool:
    """Real-employee reminder sending — off unless explicitly approved."""
    return str(os.environ.get("WATHEFNI_SHIFTS_REAL_REMINDERS") or "").strip().lower() in _ON


def employee_app_shifts_write_enabled() -> bool:
    """Broad employee-app shift mutations — always off in Wave 3."""
    return False


def talal_shifts_read_only() -> bool:
    """Talal employee-app scheduling remains read-only unless separately qualified."""
    return True


def wave3_synthetic_key_markers() -> tuple[str, ...]:
    raw = str(os.environ.get("WATHEFNI_SHIFTS_WAVE3_SYNTHETIC_KEY_MARKERS") or "").strip()
    if raw:
        return tuple(p.strip() for p in raw.split(",") if p.strip())
    return DEFAULT_W3_SYNTHETIC_KEY_MARKERS


def wave3_synthetic_phone_prefixes() -> tuple[str, ...]:
    raw = str(os.environ.get("WATHEFNI_SHIFTS_WAVE3_SYNTHETIC_PHONE_PREFIXES") or "").strip()
    if raw:
        return tuple(p.strip() for p in raw.split(",") if p.strip())
    return DEFAULT_W3_SYNTHETIC_PHONE_PREFIXES


def is_wave3_synthetic_employee(
    *,
    employee_key: Any = None,
    phone: Any = None,
    employee: dict[str, Any] | None = None,
) -> bool:
    """Wave 3B synthetic UX canary subjects (SHW3B / 965531*)."""
    key = str(employee_key or (employee or {}).get("employee_key") or "")
    phone_digits = _digits(phone or (employee or {}).get("phone") or (employee or {}).get("employee_phone"))
    for marker in wave3_synthetic_key_markers():
        if marker and marker in key:
            return True
    for prefix in wave3_synthetic_phone_prefixes():
        if prefix and phone_digits.startswith(prefix):
            return True
    raw = (employee or {}).get("raw_json") if isinstance(employee, dict) else None
    if isinstance(raw, dict) and (raw.get("shw3b") is True or str(raw.get("shw3b") or "").lower() in _ON):
        return True
    return False


def honesty_payload() -> dict[str, Any]:
    return {
        "shifts_wave3_version": SHIFTS_WAVE3_VERSION,
        "payroll_money": False,
        "leave_balances_mutated": False,
        "attendance_authority_mutated": False,
        "templates": False,
        "recurring_schedules": False,
        "rotations": False,
        "publishing": False,
        "open_shifts": False,
        "pam_export": False,
        "broad_employee_app": False,
        "talal_read_only": talal_shifts_read_only(),
        "real_reminders": real_reminders_enabled(),
        "operator_timers_default": "disabled",
        "real_mutation_gate": real_mutation_gate_enabled(),
        "wave3b_synthetic_markers": {
            "key_markers": list(wave3_synthetic_key_markers()),
            "phone_prefixes": list(wave3_synthetic_phone_prefixes()),
        },
    }


def real_mutation_denied(
    *,
    actor_phone: str | None,
    is_synthetic_subject: bool,
    company_code: str | None = None,
) -> dict[str, Any] | None:
    """Deny real (non-synthetic) schedule mutations when gate on and actor not allowlisted."""
    if company_code and not shifts_wave3_enabled_for_company(company_code):
        # Wave 3 gate only applies when Wave 3 is enabled for the company.
        return None
    if not real_mutation_gate_enabled():
        return None
    if is_synthetic_subject:
        return None
    if actor_allowlisted_for_real_mutation(actor_phone):
        return None
    return {
        "ok": False,
        "error": "shifts_real_mutation_not_allowlisted",
        "message": (
            "Real shift mutations are limited to the named WATHEFNI HR/manager allowlist "
            "while Shifts Wave 3 is in controlled readiness."
        ),
        **honesty_payload(),
    }


def require_audit_reason(reason: str | None) -> dict[str, Any] | None:
    text = str(reason or "").strip()
    if len(text) < 3:
        return {
            "ok": False,
            "error": "audit_reason_required",
            "message": "Enter an audit reason (at least 3 characters) before changing a real schedule.",
        }
    return None


def enrich_shift_row_for_ui(row: dict[str, Any], *, open_flags: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    """Presentation helpers — does not mutate authority."""
    out = dict(row)
    status = str(out.get("status") or "scheduled").lower()
    ends_next = bool(out.get("ends_next_day"))
    flags = [f for f in (open_flags or []) if str(f.get("shift_id")) == str(out.get("shift_id"))]
    ui_state = status
    if status == "cancelled":
        ui_state = "cancelled"
    elif flags:
        ui_state = "reconciliation_required"
    elif out.get("conflict_hint") or out.get("warnings"):
        ui_state = "conflicted"
    out["ui_state"] = ui_state
    out["is_overnight"] = ends_next
    out["is_split_hint"] = False  # board groups same-day windows separately
    out["open_reconciliation_count"] = len(flags)
    out["display_window"] = {
        "shift_date": str(out.get("shift_date") or ""),
        "start_time": str(out.get("start_time") or "")[:5],
        "end_time": str(out.get("end_time") or "")[:5],
        "ends_next_day": ends_next,
        "spans_next_date": ends_next,
    }
    return out


def permission_matrix() -> dict[str, Any]:
    return {
        "hr_allowlisted": {
            "create": True,
            "reschedule": True,
            "soft_cancel": True,
            "swap_decide": True,
            "availability_decide": True,
            "reconciliation_resolve": True,
            "view_history": True,
            "view_terminal_reminders": True,
        },
        "manager_allowlisted_scoped": {
            "create": "in_scope_only",
            "reschedule": "in_scope_only",
            "soft_cancel": "in_scope_only",
            "swap_decide": "in_scope_only",
            "availability_decide": "in_scope_only",
            "reconciliation_resolve": "in_scope_only",
            "view_history": "in_scope_only",
            "self_decision": False,
        },
        "talal_employee_app": {
            "read_own": "read_only_unless_separately_qualified",
            "mutate": False,
        },
        "broad_employee_app": {
            "read": False,
            "mutate": False,
        },
        "operator_timers": "disabled_by_default",
        "real_reminders": "disabled_unless_WATHEFNI_SHIFTS_REAL_REMINDERS=on",
    }
