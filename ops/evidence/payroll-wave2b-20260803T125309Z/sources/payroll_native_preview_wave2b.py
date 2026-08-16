"""Payroll Native Preview Wave 2B — deterministic Kuwait private-sector preview.

Builds non-authoritative preview amounts for monthly salaried employees:
  - effective-dated base + fixed monthly components
  - join/exit calendar-day proration
  - approved unpaid-leave deductions (classification days only)
  - fixed one-time earnings/deductions
  - versioned policy + input + calculation fingerprints
  - employee/period totals, breakdown, audit trail

Counsel-gated (review_only / unsupported — fail closed if requested):
  PIFSS, overtime premiums, sick-leave pay fractions, EOS,
  public-holiday/rest-day pay.

Does NOT: enable payment_processing, bank/WPS, remittance, journals,
payslips-as-money, AI calculations, or alter frozen Wave 1/2A flows.
"""
from __future__ import annotations

import hashlib
import json
import os
import uuid
from datetime import date, datetime, timedelta, timezone
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path
from typing import Any

import payroll_authority_wave1 as pyw1

PAYROLL_WAVE2B_VERSION = "1.0.0"
PREVIEW_POLICY_VERSION = "payroll_preview_policy@1.0.0"
PREVIEW_RESULT_SCHEMA = "payroll_preview_result@1.0.0"

_ON = {"1", "true", "yes", "on"}

DEFAULT_SYNTHETIC_KEY_MARKERS = ("PYW2B", "PYW2B-SYNTH|", "PYW1", "PYW1-SYNTH|")
DEFAULT_SYNTHETIC_PHONE_PREFIXES = ("965539", "965541")

UNSUPPORTED_RULES = (
    "pifss",
    "overtime_premiums",
    "sick_leave_pay_fractions",
    "eos",
    "public_holiday_rest_day_pay",
)

CURRENCY = "KWD"
DECIMAL_PLACES = 3
QUANT = Decimal("0.001")

SCHEMA_PATH = Path(__file__).resolve().parent / "ops" / "sql" / "payroll_native_preview_wave2b_v1.sql"
SCHEMA_SQL = SCHEMA_PATH.read_text(encoding="utf-8") if SCHEMA_PATH.exists() else ""

_SCHEMA_READY = False


def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.environ.get(name)
    if raw is None or str(raw).strip() == "":
        return default
    return str(raw).strip().lower() in _ON


def digits_phone(value: Any) -> str:
    return "".join(ch for ch in str(value or "") if ch.isdigit())


def payroll_wave2b_enabled() -> bool:
    return _env_bool("WATHEFNI_PAYROLL_WAVE2B", default=False)


def payroll_wave2b_enabled_for_company(company_code: str | None) -> bool:
    if not payroll_wave2b_enabled():
        return False
    raw = str(os.environ.get("WATHEFNI_PAYROLL_WAVE2B_COMPANIES") or "WATHEFNI").strip()
    allowed = {p.strip().upper() for p in raw.split(",") if p.strip()}
    return (company_code or "").upper() in allowed


def payroll_wave2b_synthetic_only() -> bool:
    raw = os.environ.get("WATHEFNI_PAYROLL_WAVE2B_SYNTHETIC_ONLY")
    env = (os.environ.get("WATHEFNI_ENV") or "").strip().lower()
    if env == "production" and (raw is None or str(raw).strip() == ""):
        return True
    if raw is None or str(raw).strip() == "":
        return False
    return str(raw).strip().lower() in _ON


def synthetic_key_markers() -> tuple[str, ...]:
    raw = str(os.environ.get("WATHEFNI_PAYROLL_WAVE2B_SYNTHETIC_KEY_MARKERS") or "").strip()
    if not raw:
        return DEFAULT_SYNTHETIC_KEY_MARKERS
    return tuple(p.strip() for p in raw.split(",") if p.strip()) or DEFAULT_SYNTHETIC_KEY_MARKERS


def synthetic_phone_prefixes() -> tuple[str, ...]:
    raw = str(os.environ.get("WATHEFNI_PAYROLL_WAVE2B_SYNTHETIC_PHONE_PREFIXES") or "").strip()
    if not raw:
        return DEFAULT_SYNTHETIC_PHONE_PREFIXES
    return tuple(p.strip() for p in raw.split(",") if p.strip()) or DEFAULT_SYNTHETIC_PHONE_PREFIXES


def is_wave2b_synthetic_employee(*, employee_key: str | None = None, phone: str | None = None) -> bool:
    key = str(employee_key or "")
    for marker in synthetic_key_markers():
        if marker and marker in key:
            return True
    phone_d = digits_phone(phone)
    for prefix in synthetic_phone_prefixes():
        if prefix and phone_d.startswith(prefix):
            return True
    return False


def honesty_payload() -> dict[str, Any]:
    return {
        "payroll_wave2b_version": PAYROLL_WAVE2B_VERSION,
        "preview_policy_version": PREVIEW_POLICY_VERSION,
        "preview_result_schema": PREVIEW_RESULT_SCHEMA,
        "payment_processing": "disabled",
        "authoritative": False,
        "preview_only": True,
        "money_authority": "preview_non_authoritative",
        "wathefni_money_authority": False,
        "posts_payment": False,
        "bank_files": False,
        "wps": False,
        "pifss": False,
        "eos": False,
        "journals": False,
        "payslips": False,
        "native_gross_to_net_full": False,
        "ai_calculations": False,
        "external_flows_unchanged": True,
        "wave1_contracts_unchanged": True,
        "unsupported_rules": list(UNSUPPORTED_RULES),
        "synthetic_only": payroll_wave2b_synthetic_only(),
    }


def freeze_invariants() -> dict[str, Any]:
    return {
        "payment_processing_hard_disabled": True,
        "preview_non_authoritative": True,
        "no_bank_files": True,
        "no_pifss_calc": True,
        "no_eos_calc": True,
        "no_ai": True,
        "wave1_ddl_untouched": True,
        "wave2a_ddl_untouched": True,
        "deterministic_only": True,
    }


def ensure_payroll_wave2b_schema(cur: Any, *, force: bool = False) -> None:
    global _SCHEMA_READY
    if _SCHEMA_READY and not force:
        return
    if not SCHEMA_SQL.strip():
        _SCHEMA_READY = True
        return
    lock_id = 770_900_003
    cur.execute("SELECT pg_advisory_lock(%s)", (lock_id,))
    try:
        cur.execute("SET LOCAL lock_timeout = '15s'")
        pyw1.ensure_payroll_wave1_schema(cur)
        cur.execute(SCHEMA_SQL)
        _SCHEMA_READY = True
    finally:
        cur.execute("SELECT pg_advisory_unlock(%s)", (lock_id,))


def _row(cur: Any) -> dict[str, Any] | None:
    row = cur.fetchone()
    if row is None:
        return None
    if isinstance(row, dict):
        return dict(row)
    cols = [d[0] for d in cur.description]
    return dict(zip(cols, row))


def _rows(cur: Any) -> list[dict[str, Any]]:
    fetched = cur.fetchall() or []
    if not fetched:
        return []
    if isinstance(fetched[0], dict):
        return [dict(r) for r in fetched]
    cols = [d[0] for d in cur.description]
    return [dict(zip(cols, r)) for r in fetched]


def _json_safe(value: Any) -> Any:
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, uuid.UUID):
        return str(value)
    if isinstance(value, dict):
        return {str(k): _json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(v) for v in value]
    return value


def money(value: Any) -> Decimal:
    d = Decimal(str(value or 0))
    return d.quantize(QUANT, rounding=ROUND_HALF_UP)


def fingerprint_payload(payload: dict[str, Any]) -> str:
    canonical = json.dumps(_json_safe(payload), sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def require_audit_reason(reason: Any) -> dict[str, Any] | None:
    text = str(reason or "").strip()
    if len(text) < 3:
        return {"ok": False, "error": "audit_reason_required"}
    return None


def default_policy() -> dict[str, Any]:
    return {
        "policy_version": PREVIEW_POLICY_VERSION,
        "currency": CURRENCY,
        "decimal_places": DECIMAL_PLACES,
        "rounding_mode": "ROUND_HALF_UP",
        "proration_basis": "calendar_days",
        "pay_type_supported": "monthly_salaried",
        "unsupported_rules": list(UNSUPPORTED_RULES),
        "unpaid_leave_base": "basic_plus_fixed_monthly_allowances",
    }


def policy_fingerprint(policy: dict[str, Any] | None = None) -> str:
    return fingerprint_payload(policy or default_policy())


def parse_date(value: Any) -> date | None:
    if value is None or value == "":
        return None
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    return date.fromisoformat(str(value)[:10])


def daterange(start: date, end: date) -> list[date]:
    if end < start:
        return []
    out: list[date] = []
    cur = start
    while cur <= end:
        out.append(cur)
        cur += timedelta(days=1)
    return out


def _event(
    cur: Any,
    *,
    company_code: str,
    event_type: str,
    preview_run_id: str | None = None,
    payload: dict[str, Any] | None = None,
    actor_phone: str | None = None,
) -> None:
    cur.execute(
        """
        INSERT INTO payroll_preview_events (company_code, preview_run_id, event_type, payload, created_by_phone)
        VALUES (%s,%s,%s,%s::jsonb,%s)
        """,
        (
            (company_code or "").upper(),
            preview_run_id,
            event_type,
            json.dumps(_json_safe(payload or {})),
            digits_phone(actor_phone),
        ),
    )


def ensure_default_policy(cur: Any, *, company_code: str, actor_phone: str | None = None) -> dict[str, Any]:
    ensure_payroll_wave2b_schema(cur)
    company = (company_code or "").upper()
    policy = default_policy()
    cur.execute(
        """
        INSERT INTO payroll_preview_policies (
          company_code, policy_version, currency, decimal_places, rounding_mode,
          proration_basis, pay_type_supported, unsupported_rules, payload, created_by_phone
        ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s::jsonb,%s::jsonb,%s)
        ON CONFLICT (company_code, policy_version) DO UPDATE SET payload=EXCLUDED.payload
        RETURNING *
        """,
        (
            company,
            PREVIEW_POLICY_VERSION,
            CURRENCY,
            DECIMAL_PLACES,
            "ROUND_HALF_UP",
            "calendar_days",
            "monthly_salaried",
            json.dumps(list(UNSUPPORTED_RULES)),
            json.dumps(_json_safe(policy)),
            digits_phone(actor_phone),
        ),
    )
    return _json_safe(_row(cur) or policy)


def create_preview_adjustment(
    cur: Any,
    *,
    company_code: str,
    period_start: date | str,
    period_end: date | str,
    employee_key: str,
    component_kind: str,
    code: str,
    amount: Any,
    actor_phone: str | None = None,
    reason: str | None = None,
    period_id: str | None = None,
    label_en: str | None = None,
) -> dict[str, Any]:
    denied = require_audit_reason(reason)
    if denied:
        return denied
    if payroll_wave2b_synthetic_only() and not is_wave2b_synthetic_employee(employee_key=employee_key):
        return {"ok": False, "error": "payroll_wave2b_synthetic_only", "employee_key": employee_key}
    kind = str(component_kind or "").lower()
    if kind not in ("earning", "deduction"):
        return {"ok": False, "error": "invalid_adjustment_kind"}
    ensure_payroll_wave2b_schema(cur)
    company = (company_code or "").upper()
    p_start = parse_date(period_start)
    p_end = parse_date(period_end)
    if not p_start or not p_end or p_end < p_start:
        return {"ok": False, "error": "invalid_period"}
    cur.execute(
        """
        INSERT INTO payroll_preview_adjustments (
          company_code, period_id, period_start, period_end, employee_key,
          component_kind, code, label_en, amount, currency, status, decision_note, created_by_phone
        ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'active',%s,%s)
        RETURNING *
        """,
        (
            company,
            period_id,
            p_start,
            p_end,
            employee_key,
            kind,
            str(code or "ADJ").upper(),
            label_en,
            money(amount),
            CURRENCY,
            str(reason).strip(),
            digits_phone(actor_phone),
        ),
    )
    row = _row(cur) or {}
    return {"ok": True, "adjustment": _json_safe(row), **honesty_payload()}


def list_preview_adjustments(
    cur: Any,
    *,
    company_code: str,
    period_start: date | str,
    period_end: date | str,
) -> list[dict[str, Any]]:
    ensure_payroll_wave2b_schema(cur)
    cur.execute(
        """
        SELECT * FROM payroll_preview_adjustments
        WHERE company_code=%s AND period_start=%s::date AND period_end=%s::date AND status='active'
        ORDER BY employee_key, code
        """,
        ((company_code or "").upper(), str(period_start)[:10], str(period_end)[:10]),
    )
    return _json_safe(_rows(cur))


def _contract_covers_day(contract: dict[str, Any], day: date) -> bool:
    ef = parse_date(contract.get("effective_from"))
    et = parse_date(contract.get("effective_to"))
    if not ef or day < ef:
        return False
    if et and day > et:
        return False
    return str(contract.get("status")) == "approved"


def _monthly_components(contract: dict[str, Any]) -> list[dict[str, Any]]:
    out = []
    for c in contract.get("components") or []:
        unit = str(c.get("amount_unit") or "monthly").lower()
        kind = str(c.get("component_kind") or "").lower()
        if unit != "monthly":
            continue
        if kind not in ("earning", "allowance", "deduction"):
            continue
        out.append(c)
    return out


def _one_time_from_contracts(contracts: list[dict[str, Any]], active_start: date, active_end: date) -> list[dict[str, Any]]:
    """One-time contract components apply if contract overlaps active employment window."""
    lines = []
    for contract in contracts:
        ef = parse_date(contract.get("effective_from"))
        et = parse_date(contract.get("effective_to")) or date(9999, 12, 31)
        if not ef or et < active_start or ef > active_end:
            continue
        for c in contract.get("components") or []:
            if str(c.get("amount_unit") or "").lower() != "one_time":
                continue
            kind = str(c.get("component_kind") or "").lower()
            if kind not in ("earning", "allowance", "deduction"):
                continue
            lines.append({**c, "contract_id": contract.get("contract_id")})
    return lines


def calculate_employee_preview(
    *,
    period_start: date,
    period_end: date,
    employee: dict[str, Any],
    contracts: list[dict[str, Any]],
    unpaid_leaves: list[dict[str, Any]] | None = None,
    adjustments: list[dict[str, Any]] | None = None,
    requested_unsupported: list[str] | None = None,
) -> dict[str, Any]:
    """Pure deterministic preview for one monthly-salaried employee. No I/O."""
    emp_key = str(employee.get("employee_key") or "")
    blockers: list[dict[str, str]] = []
    unsupported_hits = [r for r in (requested_unsupported or []) if r in UNSUPPORTED_RULES]
    if unsupported_hits:
        return {
            "ok": False,
            "status": "blocked",
            "employee_key": emp_key,
            "blockers": [
                {
                    "code": "unsupported_rule_requested",
                    "message": f"Counsel-gated rule not supported in Wave 2B preview: {', '.join(unsupported_hits)}",
                    "rules": unsupported_hits,
                    "posture": "review_only",
                }
            ],
            "lines": [
                {
                    "line_kind": "unsupported",
                    "code": r,
                    "amount": 0,
                    "label_en": f"Unsupported / review_only: {r}",
                    "calc_notes": {"posture": "review_only"},
                }
                for r in unsupported_hits
            ],
            **honesty_payload(),
        }

    period_days = (period_end - period_start).days + 1
    if period_days <= 0:
        return {"ok": False, "error": "invalid_period", "employee_key": emp_key}

    emp_start = parse_date(employee.get("employment_start")) or period_start
    emp_end = parse_date(employee.get("employment_end")) or period_end
    active_start = max(period_start, emp_start)
    active_end = min(period_end, emp_end)
    if active_end < active_start:
        blockers.append({"code": "employee_outside_period", "message": "Employee has no active days in this period."})
        return {
            "ok": False,
            "status": "blocked",
            "employee_key": emp_key,
            "blockers": blockers,
            "lines": [],
            "active_days": 0,
            "period_days": period_days,
            **honesty_payload(),
        }

    active_days_list = daterange(active_start, active_end)
    active_days = len(active_days_list)
    emp_contracts = [c for c in contracts if str(c.get("employee_key") or "") == emp_key and str(c.get("status")) == "approved"]

    # Day-level fail-closed contract resolution
    day_contract: dict[date, dict[str, Any]] = {}
    for day in active_days_list:
        covering = [c for c in emp_contracts if _contract_covers_day(c, day)]
        if not covering:
            blockers.append(
                {
                    "code": "missing_approved_contract",
                    "message": f"No approved compensation contract covers {day.isoformat()}.",
                }
            )
            break
        if len(covering) > 1:
            blockers.append(
                {
                    "code": "overlapping_approved_contracts",
                    "message": f"Multiple approved contracts cover {day.isoformat()}.",
                }
            )
            break
        day_contract[day] = covering[0]

    if blockers:
        return {
            "ok": False,
            "status": "blocked",
            "employee_key": emp_key,
            "blockers": blockers,
            "lines": [{"line_kind": "blocker", "code": b["code"], "amount": 0, "label_en": b["message"]} for b in blockers],
            "active_days": active_days,
            "period_days": period_days,
            **honesty_payload(),
        }

    # Aggregate monthly components by (kind, code) weighted by days under each contract segment
    monthly_accum: dict[tuple[str, str], dict[str, Any]] = {}
    for day, contract in day_contract.items():
        for comp in _monthly_components(contract):
            kind = str(comp.get("component_kind") or "").lower()
            code = str(comp.get("code") or "COMP").upper()
            key = (kind, code)
            bucket = monthly_accum.setdefault(
                key,
                {
                    "component_kind": kind,
                    "code": code,
                    "label_en": comp.get("label_en") or code,
                    "is_basic": bool(comp.get("is_basic")),
                    "monthly_amount": money(comp.get("amount")),
                    "days": 0,
                },
            )
            # If same code appears with different monthly amounts across days, fail closed
            if money(comp.get("amount")) != bucket["monthly_amount"]:
                return {
                    "ok": False,
                    "status": "blocked",
                    "employee_key": emp_key,
                    "blockers": [
                        {
                            "code": "conflicting_component_amounts",
                            "message": f"Component {code} has conflicting monthly amounts within the period.",
                        }
                    ],
                    "lines": [],
                    **honesty_payload(),
                }
            bucket["days"] += 1

    lines: list[dict[str, Any]] = []
    earnings = Decimal("0")
    deductions = Decimal("0")
    basic_plus_allowances_monthly = Decimal("0")

    for (kind, code), bucket in sorted(monthly_accum.items(), key=lambda x: (0 if x[0][0] == "earning" else 1, x[0][1])):
        prorated = money(bucket["monthly_amount"] * Decimal(bucket["days"]) / Decimal(period_days))
        notes = {
            "monthly_amount": float(bucket["monthly_amount"]),
            "days": bucket["days"],
            "period_days": period_days,
            "proration_basis": "calendar_days",
        }
        if kind in ("earning", "allowance"):
            earnings += prorated
            basic_plus_allowances_monthly += bucket["monthly_amount"]
            lines.append(
                {
                    "line_kind": kind,
                    "code": code,
                    "label_en": bucket["label_en"],
                    "amount": float(prorated),
                    "calc_notes": notes,
                }
            )
        elif kind == "deduction":
            deductions += prorated
            lines.append(
                {
                    "line_kind": "deduction",
                    "code": code,
                    "label_en": bucket["label_en"],
                    "amount": float(prorated),
                    "calc_notes": notes,
                }
            )

    # Unpaid leave deductions from classification chargeable_days
    unpaid_days = Decimal("0")
    for leave in unpaid_leaves or []:
        if str(leave.get("employee_key") or "") != emp_key:
            continue
        # Reject money fields if present
        for banned in ("salary_deduction", "pay_fraction", "amount", "deduction_kd", "monetary_fields"):
            if leave.get(banned) not in (None, {}, [], ""):
                return {
                    "ok": False,
                    "status": "blocked",
                    "employee_key": emp_key,
                    "blockers": [{"code": "leave_money_fields_forbidden", "message": "Leave handoff must be classification-only."}],
                    "lines": [],
                    **honesty_payload(),
                }
        classification = str(leave.get("classification") or leave.get("leave_type") or "").lower()
        if classification not in ("unpaid", "unpaid_leave"):
            continue
        days = Decimal(str(leave.get("chargeable_days") or 0))
        if days < 0:
            return {
                "ok": False,
                "status": "blocked",
                "employee_key": emp_key,
                "blockers": [{"code": "invalid_unpaid_days", "message": "Unpaid chargeable_days cannot be negative."}],
                "lines": [],
                **honesty_payload(),
            }
        unpaid_days += days

    if unpaid_days > Decimal(active_days):
        return {
            "ok": False,
            "status": "blocked",
            "employee_key": emp_key,
            "blockers": [
                {
                    "code": "unpaid_days_exceed_active",
                    "message": "Unpaid leave days exceed active employment days in period.",
                }
            ],
            "lines": [],
            **honesty_payload(),
        }

    if unpaid_days > 0:
        if basic_plus_allowances_monthly <= 0:
            return {
                "ok": False,
                "status": "blocked",
                "employee_key": emp_key,
                "blockers": [
                    {
                        "code": "missing_basic_for_unpaid",
                        "message": "Cannot deduct unpaid leave without basic/fixed monthly earnings base.",
                    }
                ],
                "lines": [],
                **honesty_payload(),
            }
        unpaid_deduction = money(basic_plus_allowances_monthly * unpaid_days / Decimal(period_days))
        deductions += unpaid_deduction
        lines.append(
            {
                "line_kind": "unpaid_leave_deduction",
                "code": "UNPAID_LEAVE",
                "label_en": "Unpaid leave deduction",
                "amount": float(unpaid_deduction),
                "calc_notes": {
                    "unpaid_days": float(unpaid_days),
                    "period_days": period_days,
                    "monthly_base": float(basic_plus_allowances_monthly),
                    "base": "basic_plus_fixed_monthly_allowances",
                },
            }
        )

    # One-time from contracts + period adjustments
    for comp in _one_time_from_contracts(emp_contracts, active_start, active_end):
        kind = str(comp.get("component_kind") or "").lower()
        amt = money(comp.get("amount"))
        code = str(comp.get("code") or "ONE_TIME").upper()
        if kind in ("earning", "allowance"):
            earnings += amt
            lines.append(
                {
                    "line_kind": "one_time_earning",
                    "code": code,
                    "label_en": comp.get("label_en") or code,
                    "amount": float(amt),
                    "calc_notes": {"source": "contract_one_time"},
                }
            )
        elif kind == "deduction":
            deductions += amt
            lines.append(
                {
                    "line_kind": "one_time_deduction",
                    "code": code,
                    "label_en": comp.get("label_en") or code,
                    "amount": float(amt),
                    "calc_notes": {"source": "contract_one_time"},
                }
            )

    for adj in adjustments or []:
        if str(adj.get("employee_key") or "") != emp_key:
            continue
        kind = str(adj.get("component_kind") or "").lower()
        amt = money(adj.get("amount"))
        code = str(adj.get("code") or "ADJ").upper()
        if kind == "earning":
            earnings += amt
            lines.append(
                {
                    "line_kind": "one_time_earning",
                    "code": code,
                    "label_en": adj.get("label_en") or code,
                    "amount": float(amt),
                    "calc_notes": {"source": "period_adjustment"},
                }
            )
        elif kind == "deduction":
            deductions += amt
            lines.append(
                {
                    "line_kind": "one_time_deduction",
                    "code": code,
                    "label_en": adj.get("label_en") or code,
                    "amount": float(amt),
                    "calc_notes": {"source": "period_adjustment"},
                }
            )
        else:
            return {
                "ok": False,
                "status": "blocked",
                "employee_key": emp_key,
                "blockers": [{"code": "invalid_adjustment_kind", "message": f"Invalid adjustment kind: {kind}"}],
                "lines": [],
                **honesty_payload(),
            }

    net = money(earnings - deductions)
    return {
        "ok": True,
        "status": "ok",
        "employee_key": emp_key,
        "active_days": active_days,
        "period_days": period_days,
        "unpaid_days": float(unpaid_days),
        "employment_start": emp_start.isoformat(),
        "employment_end": emp_end.isoformat(),
        "totals_earnings": float(money(earnings)),
        "totals_deductions": float(money(deductions)),
        "totals_net_preview": float(net),
        "currency": CURRENCY,
        "lines": lines,
        "blockers": [],
        "authoritative": False,
        **honesty_payload(),
    }


def _normalize_inputs(
    *,
    period_start: date,
    period_end: date,
    employees: list[dict[str, Any]],
    contracts: list[dict[str, Any]],
    unpaid_leaves: list[dict[str, Any]],
    adjustments: list[dict[str, Any]],
    requested_unsupported: list[str] | None,
) -> dict[str, Any]:
    return {
        "period_start": period_start.isoformat(),
        "period_end": period_end.isoformat(),
        "employees": sorted(
            [
                {
                    "employee_key": str(e.get("employee_key") or ""),
                    "employment_start": str(e.get("employment_start") or "")[:10] or None,
                    "employment_end": str(e.get("employment_end") or "")[:10] or None,
                }
                for e in employees
            ],
            key=lambda x: x["employee_key"],
        ),
        "contracts": sorted(
            [
                {
                    "contract_id": str(c.get("contract_id") or ""),
                    "employee_key": str(c.get("employee_key") or ""),
                    "status": str(c.get("status") or ""),
                    "effective_from": str(c.get("effective_from") or "")[:10],
                    "effective_to": str(c.get("effective_to") or "")[:10] or None,
                    "components": sorted(
                        [
                            {
                                "component_kind": str(x.get("component_kind") or ""),
                                "code": str(x.get("code") or ""),
                                "amount": float(money(x.get("amount"))),
                                "amount_unit": str(x.get("amount_unit") or "monthly"),
                                "is_basic": bool(x.get("is_basic")),
                            }
                            for x in (c.get("components") or [])
                        ],
                        key=lambda x: (x["component_kind"], x["code"]),
                    ),
                }
                for c in contracts
            ],
            key=lambda x: (x["employee_key"], x["effective_from"], x["contract_id"]),
        ),
        "unpaid_leaves": sorted(
            [
                {
                    "employee_key": str(u.get("employee_key") or ""),
                    "leave_id": str(u.get("leave_id") or ""),
                    "classification": str(u.get("classification") or u.get("leave_type") or "unpaid"),
                    "chargeable_days": float(u.get("chargeable_days") or 0),
                    "start_date": str(u.get("start_date") or "")[:10] or None,
                    "end_date": str(u.get("end_date") or "")[:10] or None,
                }
                for u in unpaid_leaves
            ],
            key=lambda x: (x["employee_key"], x["leave_id"]),
        ),
        "adjustments": sorted(
            [
                {
                    "employee_key": str(a.get("employee_key") or ""),
                    "component_kind": str(a.get("component_kind") or ""),
                    "code": str(a.get("code") or ""),
                    "amount": float(money(a.get("amount"))),
                }
                for a in adjustments
            ],
            key=lambda x: (x["employee_key"], x["code"]),
        ),
        "requested_unsupported": sorted(requested_unsupported or []),
    }


def calculate_native_preview(
    cur: Any,
    *,
    company_code: str,
    period_start: date | str,
    period_end: date | str,
    employees: list[dict[str, Any]],
    contracts: list[dict[str, Any]],
    unpaid_leaves: list[dict[str, Any]] | None = None,
    adjustments: list[dict[str, Any]] | None = None,
    requested_unsupported: list[str] | None = None,
    actor_phone: str | None = None,
    reason: str | None = None,
    period_id: str | None = None,
) -> dict[str, Any]:
    denied = require_audit_reason(reason)
    if denied:
        return denied
    ensure_payroll_wave2b_schema(cur)
    company = (company_code or "").upper()

    settings = pyw1.ensure_company_settings(cur, company_code=company)
    mode = str(settings.get("payroll_mode") or "")
    if mode not in ("native", "parallel_shadow"):
        return {
            "ok": False,
            "error": "mode_not_native_preview",
            "message": "Native preview requires payroll_mode native or parallel_shadow.",
            "payroll_mode": mode,
            **honesty_payload(),
        }
    if str(settings.get("payment_processing") or "") != "disabled":
        return {"ok": False, "error": "payment_processing_enabled", **honesty_payload()}

    p_start = parse_date(period_start)
    p_end = parse_date(period_end)
    if not p_start or not p_end or p_end < p_start:
        return {"ok": False, "error": "invalid_period"}

    if payroll_wave2b_synthetic_only():
        for emp in employees:
            key = str(emp.get("employee_key") or "")
            if not is_wave2b_synthetic_employee(employee_key=key, phone=emp.get("phone")):
                return {"ok": False, "error": "payroll_wave2b_synthetic_only", "employee_key": key}

    unpaid = list(unpaid_leaves or [])
    adjs = list(adjustments or [])
    # Merge DB adjustments for period if caller did not pass any
    if not adjs:
        adjs = list_preview_adjustments(cur, company_code=company, period_start=p_start, period_end=p_end)

    ensure_default_policy(cur, company_code=company, actor_phone=actor_phone)
    policy = default_policy()
    pol_fp = policy_fingerprint(policy)
    normalized = _normalize_inputs(
        period_start=p_start,
        period_end=p_end,
        employees=employees,
        contracts=contracts,
        unpaid_leaves=unpaid,
        adjustments=adjs,
        requested_unsupported=requested_unsupported,
    )
    in_fp = fingerprint_payload(normalized)

    # Idempotent replay
    cur.execute(
        """
        SELECT * FROM payroll_preview_runs
        WHERE company_code=%s AND input_fingerprint=%s AND policy_fingerprint=%s
          AND status='calculated'
        ORDER BY created_at DESC LIMIT 1
        """,
        (company, in_fp, pol_fp),
    )
    prior = _row(cur)
    if prior:
        return {
            "ok": True,
            "idempotent": True,
            "preview_run": _json_safe(prior),
            "input_fingerprint": in_fp,
            "policy_fingerprint": pol_fp,
            **honesty_payload(),
        }

    # Supersede prior calculated runs for same period with different fingerprint
    cur.execute(
        """
        UPDATE payroll_preview_runs
        SET status='superseded', updated_at=now(), row_version=row_version+1
        WHERE company_code=%s AND period_start=%s AND period_end=%s AND status='calculated'
          AND input_fingerprint <> %s
        RETURNING preview_run_id::text
        """,
        (company, p_start, p_end, in_fp),
    )
    superseded = [dict(r)["preview_run_id"] for r in cur.fetchall()]

    employee_results: list[dict[str, Any]] = []
    all_ok = True
    tot_earn = Decimal("0")
    tot_ded = Decimal("0")
    for emp in employees:
        result = calculate_employee_preview(
            period_start=p_start,
            period_end=p_end,
            employee=emp,
            contracts=contracts,
            unpaid_leaves=unpaid,
            adjustments=adjs,
            requested_unsupported=requested_unsupported,
        )
        employee_results.append(result)
        if not result.get("ok"):
            all_ok = False
        else:
            tot_earn += money(result.get("totals_earnings"))
            tot_ded += money(result.get("totals_deductions"))

    calc_fp = fingerprint_payload({"employees": employee_results, "policy": policy})
    status = "calculated" if all_ok else "failed"
    tot_net = money(tot_earn - tot_ded)

    cur.execute(
        """
        INSERT INTO payroll_preview_runs (
          company_code, period_id, period_start, period_end, policy_version, status,
          input_fingerprint, policy_fingerprint, calculation_fingerprint,
          money_authority, payment_processing, authoritative, posts_payment,
          employee_count, totals_earnings, totals_deductions, totals_net_preview, currency,
          inputs, result_summary, decision_note, created_by_phone
        ) VALUES (
          %s,%s,%s,%s,%s,%s,
          %s,%s,%s,
          'preview_non_authoritative','disabled',false,false,
          %s,%s,%s,%s,%s,
          %s::jsonb,%s::jsonb,%s,%s
        )
        RETURNING *
        """,
        (
            company,
            period_id,
            p_start,
            p_end,
            PREVIEW_POLICY_VERSION,
            status,
            in_fp,
            pol_fp,
            calc_fp,
            len(employees),
            money(tot_earn),
            money(tot_ded),
            tot_net,
            CURRENCY,
            json.dumps(_json_safe(normalized)),
            json.dumps(_json_safe({"employee_results": employee_results, "superseded_run_ids": superseded})),
            str(reason).strip(),
            digits_phone(actor_phone),
        ),
    )
    run = _row(cur) or {}
    run_id = str(run.get("preview_run_id"))

    for er in employee_results:
        cur.execute(
            """
            INSERT INTO payroll_preview_employee_results (
              preview_run_id, company_code, employee_key, status, active_days, period_days,
              unpaid_days, totals_earnings, totals_deductions, totals_net_preview, currency,
              employment_start, employment_end, breakdown, blockers
            ) VALUES (
              %s,%s,%s,%s,%s,%s,
              %s,%s,%s,%s,%s,
              %s,%s,%s::jsonb,%s::jsonb
            )
            RETURNING *
            """,
            (
                run_id,
                company,
                er.get("employee_key"),
                er.get("status") or ("ok" if er.get("ok") else "blocked"),
                int(er.get("active_days") or 0),
                int(er.get("period_days") or 0),
                money(er.get("unpaid_days") or 0),
                money(er.get("totals_earnings") or 0),
                money(er.get("totals_deductions") or 0),
                money(er.get("totals_net_preview") or 0),
                CURRENCY,
                parse_date(er.get("employment_start")),
                parse_date(er.get("employment_end")),
                json.dumps(_json_safe({"lines": er.get("lines") or []})),
                json.dumps(_json_safe(er.get("blockers") or [])),
            ),
        )
        emp_row = _row(cur) or {}
        eid = str(emp_row.get("employee_result_id"))
        for i, line in enumerate(er.get("lines") or []):
            cur.execute(
                """
                INSERT INTO payroll_preview_lines (
                  preview_run_id, employee_result_id, company_code, employee_key,
                  line_kind, code, label_en, amount, currency, calc_notes, sort_order
                ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb,%s)
                """,
                (
                    run_id,
                    eid,
                    company,
                    er.get("employee_key"),
                    line.get("line_kind") or "earning",
                    line.get("code") or "LINE",
                    line.get("label_en"),
                    money(line.get("amount") or 0),
                    CURRENCY,
                    json.dumps(_json_safe(line.get("calc_notes") or {})),
                    i,
                ),
            )

    _event(
        cur,
        company_code=company,
        event_type="preview_calculated" if all_ok else "preview_failed",
        preview_run_id=run_id,
        payload={
            "input_fingerprint": in_fp,
            "calculation_fingerprint": calc_fp,
            "employee_count": len(employees),
            "superseded_run_ids": superseded,
            "authoritative": False,
        },
        actor_phone=actor_phone,
    )

    return {
        "ok": all_ok,
        "idempotent": False,
        "preview_run": _json_safe(run),
        "employee_results": _json_safe(employee_results),
        "input_fingerprint": in_fp,
        "policy_fingerprint": pol_fp,
        "calculation_fingerprint": calc_fp,
        "superseded_run_ids": superseded,
        "totals": {
            "earnings": float(money(tot_earn)),
            "deductions": float(money(tot_ded)),
            "net_preview": float(tot_net),
            "currency": CURRENCY,
        },
        "authoritative": False,
        **honesty_payload(),
    }


def get_preview_run(cur: Any, *, company_code: str, preview_run_id: str) -> dict[str, Any] | None:
    ensure_payroll_wave2b_schema(cur)
    cur.execute(
        "SELECT * FROM payroll_preview_runs WHERE company_code=%s AND preview_run_id=%s",
        ((company_code or "").upper(), preview_run_id),
    )
    return _json_safe(_row(cur) or {}) or None


def list_preview_runs(cur: Any, *, company_code: str, limit: int = 50) -> list[dict[str, Any]]:
    ensure_payroll_wave2b_schema(cur)
    cur.execute(
        """
        SELECT preview_run_id::text, period_start, period_end, status, policy_version,
               input_fingerprint, calculation_fingerprint, employee_count,
               totals_earnings, totals_deductions, totals_net_preview, currency,
               authoritative, payment_processing, created_at
        FROM payroll_preview_runs
        WHERE company_code=%s
        ORDER BY created_at DESC
        LIMIT %s
        """,
        ((company_code or "").upper(), max(1, min(int(limit or 50), 200))),
    )
    return _json_safe(_rows(cur))


def list_preview_employee_results(cur: Any, *, company_code: str, preview_run_id: str) -> list[dict[str, Any]]:
    ensure_payroll_wave2b_schema(cur)
    cur.execute(
        """
        SELECT * FROM payroll_preview_employee_results
        WHERE company_code=%s AND preview_run_id=%s
        ORDER BY employee_key
        """,
        ((company_code or "").upper(), preview_run_id),
    )
    return _json_safe(_rows(cur))


def list_preview_lines(cur: Any, *, company_code: str, preview_run_id: str) -> list[dict[str, Any]]:
    ensure_payroll_wave2b_schema(cur)
    cur.execute(
        """
        SELECT * FROM payroll_preview_lines
        WHERE company_code=%s AND preview_run_id=%s
        ORDER BY employee_key, sort_order
        """,
        ((company_code or "").upper(), preview_run_id),
    )
    return _json_safe(_rows(cur))


def list_preview_events(cur: Any, *, company_code: str, preview_run_id: str | None = None, limit: int = 100) -> list[dict[str, Any]]:
    ensure_payroll_wave2b_schema(cur)
    cur.execute(
        """
        SELECT event_id::text, preview_run_id::text, event_type, payload, created_by_phone, created_at
        FROM payroll_preview_events
        WHERE company_code=%s AND (%s::uuid IS NULL OR preview_run_id=%s::uuid)
        ORDER BY created_at DESC
        LIMIT %s
        """,
        (
            (company_code or "").upper(),
            preview_run_id,
            preview_run_id,
            max(1, min(int(limit or 100), 500)),
        ),
    )
    return _json_safe(_rows(cur))


def rollback_preview_run(
    cur: Any,
    *,
    company_code: str,
    preview_run_id: str,
    actor_phone: str | None = None,
    reason: str | None = None,
) -> dict[str, Any]:
    denied = require_audit_reason(reason)
    if denied:
        return denied
    ensure_payroll_wave2b_schema(cur)
    company = (company_code or "").upper()
    cur.execute(
        """
        UPDATE payroll_preview_runs
        SET status='rolled_back', updated_at=now(), row_version=row_version+1,
            decision_note=COALESCE(decision_note,'') || ' | rollback:' || %s
        WHERE company_code=%s AND preview_run_id=%s AND status IN ('calculated','failed')
        RETURNING *
        """,
        (str(reason).strip(), company, preview_run_id),
    )
    updated = _row(cur)
    if not updated:
        return {"ok": False, "error": "preview_run_not_found_or_bad_status"}
    _event(
        cur,
        company_code=company,
        event_type="preview_rolled_back",
        preview_run_id=preview_run_id,
        payload={"reason": reason},
        actor_phone=actor_phone,
    )
    return {"ok": True, "preview_run": _json_safe(updated), **honesty_payload()}
