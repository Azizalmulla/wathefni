"""Payroll Authority P3 — Components + company policy + Mode A preview calc.

Consumes locked P2 input snapshots + Wave 1 compensation + versioned company policy
to produce deterministic preview_non_authoritative component lines.

Does NOT: unlock Mode A seal, native official PDF, PIFSS/EOS rates, payments.
OT/rest-day/PH/sick money requires counsel-approved rate tables or fail closed.
"""
from __future__ import annotations

import hashlib
import json
import os
import uuid
from datetime import date, datetime
from decimal import Decimal, ROUND_CEILING, ROUND_FLOOR, ROUND_HALF_UP
from pathlib import Path
from typing import Any

import payroll_authority_snapshot_p1 as p1
import payroll_authority_wave1 as pyw1
import payroll_input_snapshot_p2 as p2

PAYROLL_AUTHORITY_P3_VERSION = "1.0.0"
CALC_SCHEMA = "wathefni.payroll_calc_preview.v1"
MONEY_PREVIEW = "preview_non_authoritative"
COUNSEL_FAMILIES = ("ot_ordinary", "rest_day_work", "public_holiday_work", "sick_leave_fractions")

SCHEMA_SQL_PATH = Path(__file__).resolve().parent / "ops" / "sql" / "payroll_components_policy_p3_v1.sql"
SCHEMA_SQL = SCHEMA_SQL_PATH.read_text(encoding="utf-8") if SCHEMA_SQL_PATH.exists() else ""
_SCHEMA_READY = False
_ON = ("1", "true", "yes", "on")
DEFAULT_SYNTHETIC_KEY_MARKERS = (
    "PYW1", "PYW2A", "PYW2B", "PYW3", "PYAUTH", "PYP1", "PYP2", "PYP3", "PYINPUT", "PYCALC",
)


def digits_phone(value: Any) -> str:
    return "".join(ch for ch in str(value or "") if ch.isdigit())


def _env_bool(name: str, *, default: bool = False) -> bool:
    raw = os.environ.get(name)
    if raw is None or str(raw).strip() == "":
        return default
    return str(raw).strip().lower() in _ON


def payroll_authority_p3_enabled() -> bool:
    return _env_bool("WATHEFNI_PAYROLL_AUTHORITY_P3", default=True)


def payroll_authority_p3_enabled_for_company(company_code: str | None) -> bool:
    if not payroll_authority_p3_enabled():
        return False
    raw = str(os.environ.get("WATHEFNI_PAYROLL_AUTHORITY_P3_COMPANIES") or "WATHEFNI").strip()
    return (company_code or "").upper() in {p.strip().upper() for p in raw.split(",") if p.strip()}


def payroll_authority_p3_synthetic_only() -> bool:
    raw = os.environ.get("WATHEFNI_PAYROLL_AUTHORITY_P3_SYNTHETIC_ONLY")
    env = (os.environ.get("WATHEFNI_ENV") or "").strip().lower()
    if env == "production" and (raw is None or str(raw).strip() == ""):
        return True
    if raw is None or str(raw).strip() == "":
        return False
    return str(raw).strip().lower() in _ON


def synthetic_key_markers() -> tuple[str, ...]:
    raw = str(os.environ.get("WATHEFNI_PAYROLL_AUTHORITY_P3_SYNTHETIC_KEY_MARKERS") or "").strip()
    if not raw:
        return DEFAULT_SYNTHETIC_KEY_MARKERS
    return tuple(p.strip() for p in raw.split(",") if p.strip()) or DEFAULT_SYNTHETIC_KEY_MARKERS


def is_p3_synthetic_employee(*, employee_key: str | None = None) -> bool:
    key = str(employee_key or "")
    return any(m and m in key for m in synthetic_key_markers())


def honesty_payload() -> dict[str, Any]:
    return {
        "payroll_authority_p3_version": PAYROLL_AUTHORITY_P3_VERSION,
        "calc_schema": CALC_SCHEMA,
        "money_authority": MONEY_PREVIEW,
        "mode_a_wathefni_seal_unlocked": False,
        "native_official_pdf_unlocked": False,
        "pifss_eos_rates_implemented": False,
        "ot_sick_ph_rates_counsel_gated": True,
        "payment_processing": "disabled",
        "posts_payment": False,
        "payment_date_invented": False,
        "synthetic_only": payroll_authority_p3_synthetic_only(),
        "kuwait_first": True,
        "arbitrary_formula_scripts": False,
        "p1_p2_preserved": True,
    }


def freeze_invariants() -> dict[str, Any]:
    return {
        "preview_non_authoritative": True,
        "requires_locked_input_snapshot": True,
        "deterministic_idempotent": True,
        "policy_versioned": True,
        "counsel_rates_fail_closed_when_required": True,
        "no_double_deduct_unpaid_leave_absence": True,
        "informational_attendance_no_money": True,
        "stale_inputs_do_not_mutate_existing_calc": True,
    }


def ensure_payroll_components_policy_schema(cur: Any, *, force: bool = False) -> None:
    global _SCHEMA_READY
    if _SCHEMA_READY and not force:
        return
    if not SCHEMA_SQL.strip():
        _SCHEMA_READY = True
        return
    lock_id = 770_900_013
    cur.execute("SELECT pg_advisory_lock(%s)", (lock_id,))
    try:
        cur.execute("SET LOCAL lock_timeout = '15s'")
        pyw1.ensure_payroll_wave1_schema(cur)
        p1.ensure_payroll_authority_snapshot_schema(cur)
        p2.ensure_payroll_input_snapshot_schema(cur)
        cur.execute(SCHEMA_SQL)
        _SCHEMA_READY = True
    finally:
        try:
            cur.execute("SELECT pg_advisory_unlock(%s)", (lock_id,))
        except Exception:
            pass


def _row(cur: Any) -> dict[str, Any] | None:
    row = cur.fetchone()
    if row is None:
        return None
    if isinstance(row, dict):
        return dict(row)
    return dict(zip([d[0] for d in cur.description], row))


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


def fingerprint_payload(payload: Any) -> str:
    raw = json.dumps(_json_safe(payload), sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def require_audit_reason(reason: str | None) -> dict[str, Any] | None:
    if not str(reason or "").strip():
        return {"ok": False, "error": "audit_reason_required"}
    return None


def money(value: Any, *, rounding: str = "half_up_3") -> Decimal:
    q = Decimal("0.001")
    d = Decimal(str(value or 0))
    mode = ROUND_HALF_UP
    if rounding == "floor_3":
        mode = ROUND_FLOOR
    elif rounding == "ceil_3":
        mode = ROUND_CEILING
    return d.quantize(q, rounding=mode)


def _parse_date(value: Any) -> date | None:
    if value is None:
        return None
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    try:
        return date.fromisoformat(str(value)[:10])
    except Exception:
        return None


def _record_event(
    cur: Any,
    *,
    company_code: str,
    calc_run_id: str | None,
    event_type: str,
    payload: dict[str, Any],
    actor_phone: str | None,
) -> None:
    cur.execute(
        """
        INSERT INTO payroll_calc_preview_events
          (calc_run_id, company_code, event_type, payload, created_by_phone)
        VALUES (%s,%s,%s,%s::jsonb,%s)
        """,
        (
            calc_run_id,
            (company_code or "").upper(),
            event_type,
            json.dumps(_json_safe(payload)),
            digits_phone(actor_phone),
        ),
    )


def list_component_catalog(cur: Any) -> list[dict[str, Any]]:
    ensure_payroll_components_policy_schema(cur)
    cur.execute("SELECT * FROM payroll_component_catalog ORDER BY component_code")
    return _rows(cur)


def catalog_fingerprint(cur: Any) -> str:
    rows = list_component_catalog(cur)
    return fingerprint_payload(
        [{"code": r.get("component_code"), "category": r.get("category"), "counsel": r.get("counsel_gated")} for r in rows]
    )


def create_policy_version(
    cur: Any,
    *,
    company_code: str,
    effective_from: str | date,
    actor_phone: str | None,
    reason: str | None,
    attendance_payroll_mode: str = "required",
    lateness_money_enabled: bool = False,
    lateness_grace_minutes: int = 0,
    absence_money_enabled: bool = True,
    unpaid_leave_money_enabled: bool = True,
    ot_money_enabled: bool = False,
    rest_day_money_enabled: bool = False,
    public_holiday_money_enabled: bool = False,
    sick_leave_money_enabled: bool = False,
    approve: bool = True,
) -> dict[str, Any]:
    denied = require_audit_reason(reason)
    if denied:
        return denied
    ensure_payroll_components_policy_schema(cur)
    company = (company_code or "").upper()
    mode = str(attendance_payroll_mode or "required").lower()
    if mode not in ("required", "informational", "ignored"):
        return {"ok": False, "error": "invalid_attendance_payroll_mode"}
    ef = _parse_date(effective_from)
    if not ef:
        return {"ok": False, "error": "invalid_effective_from"}
    cur.execute(
        "SELECT COALESCE(MAX(version_number),0)+1 AS n FROM payroll_company_policy_versions WHERE company_code=%s",
        (company,),
    )
    ver = int(dict(cur.fetchone())["n"])
    payload = {
        "attendance_payroll_mode": mode,
        "lateness_money_enabled": bool(lateness_money_enabled),
        "lateness_grace_minutes": int(lateness_grace_minutes or 0),
        "absence_money_enabled": bool(absence_money_enabled),
        "unpaid_leave_money_enabled": bool(unpaid_leave_money_enabled),
        "ot_money_enabled": bool(ot_money_enabled),
        "rest_day_money_enabled": bool(rest_day_money_enabled),
        "public_holiday_money_enabled": bool(public_holiday_money_enabled),
        "sick_leave_money_enabled": bool(sick_leave_money_enabled),
        "rounding_mode": "half_up_3",
    }
    fp = fingerprint_payload(payload)
    status = "approved" if approve else "draft"
    # supersede prior approved overlapping
    if approve:
        cur.execute(
            """
            UPDATE payroll_company_policy_versions
            SET status='superseded', updated_at=now(), row_version=row_version+1
            WHERE company_code=%s AND status='approved'
            """,
            (company,),
        )
    cur.execute(
        """
        INSERT INTO payroll_company_policy_versions (
          company_code, version_number, status, effective_from,
          attendance_payroll_mode, lateness_money_enabled, lateness_grace_minutes,
          absence_money_enabled, unpaid_leave_money_enabled,
          ot_money_enabled, rest_day_money_enabled, public_holiday_money_enabled,
          sick_leave_money_enabled, policy_payload, content_fingerprint,
          decision_note, created_by_phone, approved_by_phone, approved_at
        ) VALUES (
          %s,%s,%s,%s,
          %s,%s,%s,
          %s,%s,
          %s,%s,%s,
          %s,%s::jsonb,%s,
          %s,%s,%s, CASE WHEN %s THEN now() ELSE NULL END
        )
        RETURNING *
        """,
        (
            company,
            ver,
            status,
            ef,
            mode,
            bool(lateness_money_enabled),
            int(lateness_grace_minutes or 0),
            bool(absence_money_enabled),
            bool(unpaid_leave_money_enabled),
            bool(ot_money_enabled),
            bool(rest_day_money_enabled),
            bool(public_holiday_money_enabled),
            bool(sick_leave_money_enabled),
            json.dumps(payload),
            fp,
            str(reason).strip(),
            digits_phone(actor_phone),
            digits_phone(actor_phone) if approve else None,
            approve,
        ),
    )
    row = _row(cur)
    return {"ok": True, "policy": _json_safe(row), **honesty_payload()}


def get_policy_for_period(
    cur: Any, *, company_code: str, period_start: str | date
) -> dict[str, Any] | None:
    ensure_payroll_components_policy_schema(cur)
    cur.execute(
        """
        SELECT * FROM payroll_company_policy_versions
        WHERE company_code=%s AND status='approved' AND effective_from <= %s
          AND (effective_to IS NULL OR effective_to >= %s)
        ORDER BY effective_from DESC, version_number DESC
        LIMIT 1
        """,
        ((company_code or "").upper(), str(period_start)[:10], str(period_start)[:10]),
    )
    return _row(cur)


def get_policy_by_id(cur: Any, *, company_code: str, policy_version_id: str) -> dict[str, Any] | None:
    ensure_payroll_components_policy_schema(cur)
    cur.execute(
        """
        SELECT * FROM payroll_company_policy_versions
        WHERE company_code=%s AND policy_version_id=%s
        """,
        ((company_code or "").upper(), policy_version_id),
    )
    return _row(cur)


def ensure_counsel_required_rate_placeholders(
    cur: Any, *, company_code: str, actor_phone: str | None = None
) -> list[dict[str, Any]]:
    """Seed counsel_required placeholders — no multipliers."""
    ensure_payroll_components_policy_schema(cur)
    company = (company_code or "").upper()
    out = []
    for family in COUNSEL_FAMILIES:
        cur.execute(
            """
            SELECT * FROM payroll_rate_tables
            WHERE company_code=%s AND rule_family=%s AND status='counsel_required'
            ORDER BY created_at DESC LIMIT 1
            """,
            (company, family),
        )
        existing = _row(cur)
        if existing:
            out.append(existing)
            continue
        payload = {"rule_family": family, "status": "counsel_required", "multiplier": None}
        fp = fingerprint_payload(payload)
        cur.execute(
            """
            INSERT INTO payroll_rate_tables (
              company_code, rule_family, status, version_label, effective_from,
              multiplier, counsel_signed, counsel_note, content_fingerprint, created_by_phone
            ) VALUES (%s,%s,'counsel_required','counsel_pending',CURRENT_DATE,NULL,false,
                      'Kuwait statutory rates require counsel-signed table before money calc',%s,%s)
            RETURNING *
            """,
            (company, family, fp, digits_phone(actor_phone)),
        )
        out.append(_row(cur) or {})
    return out


def get_approved_rate(
    cur: Any, *, company_code: str, rule_family: str, as_of: date
) -> dict[str, Any] | None:
    """Return counsel-signed legal rate only. Architecture fixtures never qualify here."""
    # P4A legal bridge (legal_claim=true only). Architecture fixtures are excluded.
    try:
        import payroll_statutory_architecture_p4a as p4a

        bridged = p4a.get_approved_rate_for_p3(
            cur,
            company_code=company_code,
            rule_family=rule_family,
            as_of=as_of,
            allow_architecture_fixture=False,
        )
        if bridged and bridged.get("legal_claim") and (
            bridged.get("multiplier") is not None
            or (isinstance(bridged.get("fraction_payload"), dict) and bridged.get("fraction_payload"))
        ):
            return bridged
    except Exception:
        pass
    cur.execute(
        """
        SELECT * FROM payroll_rate_tables
        WHERE company_code=%s AND rule_family=%s AND status='approved'
          AND counsel_signed=true AND effective_from <= %s
          AND (effective_to IS NULL OR effective_to >= %s)
          AND multiplier IS NOT NULL
        ORDER BY effective_from DESC LIMIT 1
        """,
        ((company_code or "").upper(), rule_family, as_of, as_of),
    )
    return _row(cur)


def upsert_company_component(
    cur: Any,
    *,
    company_code: str,
    catalog_code: str,
    component_code: str,
    label_en: str,
    label_ar: str | None,
    line_kind: str,
    amount_unit: str = "monthly",
    default_amount: Any = None,
    is_custom: bool = False,
    actor_phone: str | None = None,
    reason: str | None = None,
) -> dict[str, Any]:
    denied = require_audit_reason(reason)
    if denied:
        return denied
    ensure_payroll_components_policy_schema(cur)
    # Reserved statutory codes cannot be re-homed as custom
    reserved = {"PIFSS_EE", "PIFSS_ER", "EOS_INDEMNITY", "OT_ORDINARY", "OT_REST_DAY_PH", "SICK_LEAVE"}
    code = str(component_code or "").upper()
    if is_custom and code in reserved:
        return {"ok": False, "error": "reserved_component_cannot_be_custom", "component_code": code}
    cur.execute(
        """
        INSERT INTO payroll_company_components (
          company_code, catalog_code, component_code, label_en, label_ar,
          line_kind, amount_unit, default_amount, is_custom, created_by_phone
        ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
        ON CONFLICT (company_code, component_code) DO UPDATE
          SET label_en=EXCLUDED.label_en, label_ar=EXCLUDED.label_ar,
              default_amount=EXCLUDED.default_amount, active=true, updated_at=now()
        RETURNING *
        """,
        (
            (company_code or "").upper(),
            catalog_code,
            code,
            label_en,
            label_ar,
            line_kind,
            amount_unit,
            float(default_amount) if default_amount is not None else None,
            is_custom,
            digits_phone(actor_phone),
        ),
    )
    return {"ok": True, "component": _json_safe(_row(cur)), **honesty_payload()}


def assign_component(
    cur: Any,
    *,
    company_code: str,
    company_component_id: str,
    amount: Any,
    effective_from: str | date,
    employee_key: str | None = None,
    employee_group: str | None = None,
    actor_phone: str | None = None,
    reason: str | None = None,
) -> dict[str, Any]:
    denied = require_audit_reason(reason)
    if denied:
        return denied
    ensure_payroll_components_policy_schema(cur)
    if not employee_key and not employee_group:
        return {"ok": False, "error": "assignment_target_required"}
    if payroll_authority_p3_synthetic_only() and employee_key and not is_p3_synthetic_employee(employee_key=employee_key):
        return {"ok": False, "error": "payroll_authority_p3_synthetic_only", "employee_key": employee_key}
    cur.execute(
        """
        INSERT INTO payroll_component_assignments (
          company_code, employee_key, employee_group, company_component_id,
          amount, effective_from, decision_note, created_by_phone
        ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
        RETURNING *
        """,
        (
            (company_code or "").upper(),
            employee_key,
            employee_group,
            company_component_id,
            float(amount),
            str(effective_from)[:10],
            str(reason).strip(),
            digits_phone(actor_phone),
        ),
    )
    return {"ok": True, "assignment": _json_safe(_row(cur)), **honesty_payload()}


def create_one_off_adjustment(
    cur: Any,
    *,
    company_code: str,
    employee_key: str,
    period_start: str | date,
    period_end: str | date,
    component_code: str,
    line_kind: str,
    amount: Any,
    reason: str | None,
    actor_phone: str | None = None,
    label_en: str | None = None,
) -> dict[str, Any]:
    denied = require_audit_reason(reason)
    if denied:
        return denied
    ensure_payroll_components_policy_schema(cur)
    if payroll_authority_p3_synthetic_only() and not is_p3_synthetic_employee(employee_key=employee_key):
        return {"ok": False, "error": "payroll_authority_p3_synthetic_only"}
    cur.execute(
        """
        INSERT INTO payroll_one_off_adjustments (
          company_code, employee_key, period_start, period_end,
          component_code, line_kind, amount, label_en, status,
          decision_note, created_by_phone, approved_by_phone
        ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,'approved',%s,%s,%s)
        RETURNING *
        """,
        (
            (company_code or "").upper(),
            employee_key,
            str(period_start)[:10],
            str(period_end)[:10],
            str(component_code).upper(),
            line_kind,
            float(amount),
            label_en or str(component_code),
            str(reason).strip(),
            digits_phone(actor_phone),
            digits_phone(actor_phone),
        ),
    )
    return {"ok": True, "adjustment": _json_safe(_row(cur)), **honesty_payload()}


def _load_contracts(cur: Any, *, company_code: str, employee_key: str, period_start: date, period_end: date) -> list[dict[str, Any]]:
    cur.execute(
        """
        SELECT * FROM payroll_compensation_contracts
        WHERE company_code=%s AND employee_key=%s AND status='approved'
          AND effective_from <= %s AND (effective_to IS NULL OR effective_to >= %s)
        ORDER BY effective_from
        """,
        ((company_code or "").upper(), employee_key, period_end, period_start),
    )
    contracts = _rows(cur)
    for c in contracts:
        comps = pyw1._components_for_contract(cur, str(c.get("contract_id")))
        c["components"] = comps
    return contracts


def _contract_covers_day(contract: dict[str, Any], day: date) -> bool:
    start = _parse_date(contract.get("effective_from"))
    end = _parse_date(contract.get("effective_to"))
    if not start or day < start:
        return False
    if end and day > end:
        return False
    return True


def _daily_rate_from_basic(basic_monthly: Decimal, period_days: int, rounding: str) -> Decimal:
    if period_days <= 0:
        return money(0, rounding=rounding)
    return money(basic_monthly / Decimal(period_days), rounding=rounding)


def _calc_employee(
    *,
    employee_key: str,
    period_start: date,
    period_end: date,
    emp_row: dict[str, Any],
    input_lines: list[dict[str, Any]],
    contracts: list[dict[str, Any]],
    policy: dict[str, Any],
    assignments: list[dict[str, Any]],
    adjustments: list[dict[str, Any]],
    company_components: dict[str, dict[str, Any]],
    approved_rates: dict[str, dict[str, Any] | None],
) -> dict[str, Any]:
    rounding = str(policy.get("rounding_mode") or "half_up_3")
    att_mode = str(policy.get("attendance_payroll_mode") or "required")
    period_days = (period_end - period_start).days + 1
    blockers: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    lines: list[dict[str, Any]] = []
    sort_i = 0

    active_start = _parse_date(emp_row.get("active_start")) or period_start
    active_end = _parse_date(emp_row.get("active_end")) or period_end
    if active_end < active_start:
        return {
            "ok": False,
            "status": "blocked",
            "employee_key": employee_key,
            "blockers": [{"code": "employee_outside_period", "message": "No active days in period"}],
            "warnings": [],
            "lines": [],
            "totals": {"earnings": 0, "deductions": 0, "gross": 0, "net": 0},
        }

    # Day → contract (fail closed on overlap/missing)
    from datetime import timedelta

    day = active_start
    day_contract: dict[date, dict[str, Any]] = {}
    while day <= active_end:
        covering = [c for c in contracts if _contract_covers_day(c, day)]
        if not covering:
            blockers.append({"code": "missing_approved_contract", "message": f"No contract on {day.isoformat()}", "fact_date": str(day)})
            break
        if len(covering) > 1:
            blockers.append({"code": "overlapping_approved_contracts", "message": f"Overlap on {day.isoformat()}", "fact_date": str(day)})
            break
        day_contract[day] = covering[0]
        day += timedelta(days=1)

    if blockers:
        return {
            "ok": False,
            "status": "blocked",
            "employee_key": employee_key,
            "blockers": blockers,
            "warnings": warnings,
            "lines": [],
            "totals": {"earnings": 0, "deductions": 0, "gross": 0, "net": 0},
        }

    # Prorate monthly contract components
    monthly_accum: dict[tuple[str, str], dict[str, Any]] = {}
    basic_by_day: dict[date, Decimal] = {}
    for d, contract in day_contract.items():
        for comp in contract.get("components") or []:
            unit = str(comp.get("amount_unit") or "monthly").lower()
            kind = str(comp.get("component_kind") or "").lower()
            code = str(comp.get("code") or "COMP").upper()
            amt = money(comp.get("amount"), rounding=rounding)
            if unit == "one_time":
                continue
            if unit != "monthly":
                warnings.append({"code": "unsupported_amount_unit", "message": f"{code} unit={unit} skipped"})
                continue
            key = (kind, code)
            bucket = monthly_accum.setdefault(
                key,
                {
                    "code": code,
                    "kind": kind,
                    "label_en": comp.get("label_en") or code,
                    "is_basic": bool(comp.get("is_basic")) or code == "BASIC",
                    "monthly_amount": amt,
                    "days": 0,
                    "contract_ids": set(),
                },
            )
            if amt != bucket["monthly_amount"]:
                # same code different amount across days — still OK if mid-period change via different contracts;
                # track separately by monthly amount key
                key = (kind, code, str(amt))
                bucket = monthly_accum.setdefault(
                    key,
                    {
                        "code": code,
                        "kind": kind,
                        "label_en": comp.get("label_en") or code,
                        "is_basic": bool(comp.get("is_basic")) or code == "BASIC",
                        "monthly_amount": amt,
                        "days": 0,
                        "contract_ids": set(),
                    },
                )
            bucket["days"] += 1
            bucket["contract_ids"].add(str(contract.get("contract_id")))
            if bucket["is_basic"] or code == "BASIC":
                basic_by_day[d] = amt

    for key, bucket in monthly_accum.items():
        prorated = money(bucket["monthly_amount"] * Decimal(bucket["days"]) / Decimal(period_days), rounding=rounding)
        line_kind = "earning" if bucket["kind"] in ("earning", "allowance") else "deduction"
        if bucket["kind"] == "deduction":
            line_kind = "deduction"
        elif bucket["kind"] in ("earning", "allowance"):
            line_kind = "earning"
        else:
            line_kind = "earning" if bucket["kind"] != "deduction" else "deduction"
        lines.append(
            {
                "component_code": bucket["code"],
                "catalog_code": "BASIC" if bucket["is_basic"] else bucket["code"],
                "line_kind": line_kind,
                "category": "earning_basic" if bucket["is_basic"] else (
                    "earning_allowance_recurring" if line_kind == "earning" else "deduction_recurring"
                ),
                "label_en": bucket["label_en"],
                "label_ar": bucket["label_en"],
                "amount": float(prorated),
                "sort_order": sort_i,
                "calc_notes": {
                    "monthly_amount": float(bucket["monthly_amount"]),
                    "days": bucket["days"],
                    "period_days": period_days,
                    "proration": "calendar_days",
                },
                "provenance": {
                    "contract_ids": sorted(bucket["contract_ids"]),
                    "source": "payroll_compensation_contracts",
                },
                "contract_id": next(iter(bucket["contract_ids"]), None),
            }
        )
        sort_i += 1

    # One-time contract components (full amount if any active day covered by that contract)
    seen_one_time: set[str] = set()
    for contract in contracts:
        cid = str(contract.get("contract_id"))
        for comp in contract.get("components") or []:
            if str(comp.get("amount_unit") or "").lower() != "one_time":
                continue
            code = str(comp.get("code") or "ONE_OFF").upper()
            tok = f"{cid}:{code}"
            if tok in seen_one_time:
                continue
            # include if contract covers any active day
            if not any(_contract_covers_day(contract, d) for d in day_contract):
                continue
            seen_one_time.add(tok)
            kind = str(comp.get("component_kind") or "earning").lower()
            line_kind = "deduction" if kind == "deduction" else "earning"
            lines.append(
                {
                    "component_code": code,
                    "catalog_code": "ALLOWANCE.ONE_OFF" if line_kind == "earning" else "DEDUCTION.ONE_OFF",
                    "line_kind": line_kind,
                    "category": "earning_allowance_one_off" if line_kind == "earning" else "deduction_one_off",
                    "label_en": comp.get("label_en") or code,
                    "amount": float(money(comp.get("amount"), rounding=rounding)),
                    "sort_order": sort_i,
                    "calc_notes": {"amount_unit": "one_time"},
                    "provenance": {"contract_id": cid, "source": "payroll_compensation_contracts"},
                    "contract_id": cid,
                }
            )
            sort_i += 1

    # Company component assignments (employee-specific)
    for asg in assignments:
        if str(asg.get("employee_key") or "") != employee_key:
            continue
        cc = company_components.get(str(asg.get("company_component_id")))
        if not cc:
            continue
        amt = money(asg.get("amount"), rounding=rounding)
        # simple full-period if assignment covers period start
        ef = _parse_date(asg.get("effective_from"))
        et = _parse_date(asg.get("effective_to"))
        if ef and ef > period_end:
            continue
        if et and et < period_start:
            continue
        # prorate by overlap days with active span
        overlap_start = max(active_start, ef or active_start, period_start)
        overlap_end = min(active_end, et or active_end, period_end)
        if overlap_end < overlap_start:
            continue
        days = (overlap_end - overlap_start).days + 1
        unit = str(cc.get("amount_unit") or "monthly")
        if unit == "monthly":
            amt = money(amt * Decimal(days) / Decimal(period_days), rounding=rounding)
        lines.append(
            {
                "component_code": str(cc.get("component_code")),
                "catalog_code": str(cc.get("catalog_code")),
                "line_kind": str(cc.get("line_kind")),
                "category": "other" if cc.get("is_custom") else None,
                "label_en": cc.get("label_en"),
                "label_ar": cc.get("label_ar"),
                "amount": float(amt),
                "sort_order": sort_i,
                "calc_notes": {"assignment_id": str(asg.get("assignment_id")), "days": days},
                "provenance": {"assignment_id": str(asg.get("assignment_id")), "source": "payroll_component_assignments"},
            }
        )
        sort_i += 1

    # One-off adjustments
    for adj in adjustments:
        if str(adj.get("employee_key") or "") != employee_key:
            continue
        if str(adj.get("status") or "") != "approved":
            continue
        lines.append(
            {
                "component_code": str(adj.get("component_code")),
                "catalog_code": str(adj.get("component_code")),
                "line_kind": str(adj.get("line_kind")),
                "label_en": adj.get("label_en") or adj.get("component_code"),
                "amount": float(money(adj.get("amount"), rounding=rounding)),
                "sort_order": sort_i,
                "calc_notes": {"adjustment_id": str(adj.get("adjustment_id"))},
                "provenance": {"adjustment_id": str(adj.get("adjustment_id")), "source": "payroll_one_off_adjustments"},
            }
        )
        sort_i += 1

    # Average basic for daily rate
    if basic_by_day:
        avg_basic = money(sum(basic_by_day.values()) / Decimal(len(basic_by_day)), rounding=rounding)
    else:
        # fallback from lines
        basic_lines = [ln for ln in lines if ln.get("component_code") == "BASIC" or ln.get("catalog_code") == "BASIC"]
        avg_basic = money(0)
        if basic_lines:
            # reverse-engineer approximate monthly from prorated — use first contract monthly if available
            for c in contracts:
                for comp in c.get("components") or []:
                    if comp.get("is_basic") or str(comp.get("code")).upper() == "BASIC":
                        avg_basic = money(comp.get("amount"), rounding=rounding)
                        break
    daily = _daily_rate_from_basic(avg_basic, period_days, rounding)

    # Attendance / leave money from P2 facts
    attendance_money = att_mode not in ("informational", "ignored")
    unpaid_leave_dates: set[date] = set()
    paid_leave_dates: set[date] = set()
    for ln in input_lines:
        if ln.get("line_kind") != "leave_interval":
            continue
        cls = str(ln.get("classification") or "")
        fs = _parse_date(ln.get("fact_date"))
        fe = _parse_date(ln.get("fact_end_date")) or fs
        if not fs or not fe:
            continue
        d = fs
        while d <= fe:
            if cls == "unpaid_leave":
                unpaid_leave_dates.add(d)
            elif cls == "paid_leave":
                paid_leave_dates.add(d)
            d += timedelta(days=1)

    if attendance_money and policy.get("unpaid_leave_money_enabled"):
        for ln in input_lines:
            if ln.get("line_kind") != "leave_interval":
                continue
            if str(ln.get("classification")) != "unpaid_leave":
                continue
            days = float(ln.get("chargeable_days") or 0)
            if days <= 0:
                fs = _parse_date(ln.get("fact_date"))
                fe = _parse_date(ln.get("fact_end_date")) or fs
                days = float((fe - fs).days + 1) if fs and fe else 0
            amt = money(daily * Decimal(str(days)), rounding=rounding)
            lines.append(
                {
                    "component_code": "UNPAID_LEAVE",
                    "catalog_code": "UNPAID_LEAVE",
                    "line_kind": "deduction",
                    "category": "deduction_unpaid_leave",
                    "label_en": "Unpaid leave deduction",
                    "label_ar": "استقطاع إجازة بدون راتب",
                    "amount": float(amt),
                    "sort_order": sort_i,
                    "input_line_id": str(ln.get("line_id") or "") or None,
                    "calc_notes": {"chargeable_days": days, "daily_rate": float(daily)},
                    "provenance": {
                        "leave_id": ln.get("leave_id"),
                        "input_line_kind": "leave_interval",
                        "source": "payroll_input_snapshot_lines",
                    },
                }
            )
            sort_i += 1

    if attendance_money and policy.get("absence_money_enabled"):
        for ln in input_lines:
            if ln.get("line_kind") != "attendance_day":
                continue
            if str(ln.get("classification") or "").lower() != "absent":
                continue
            if ln.get("suppressed"):
                continue
            d = _parse_date(ln.get("fact_date"))
            if d and d in unpaid_leave_dates:
                # safety: should already be suppressed in P2
                warnings.append({"code": "absence_skipped_unpaid_leave_overlap", "fact_date": str(d)})
                continue
            if d and d in paid_leave_dates:
                warnings.append({"code": "absence_skipped_paid_leave", "fact_date": str(d)})
                continue
            lines.append(
                {
                    "component_code": "DEDUCTION.ABSENCE",
                    "catalog_code": "DEDUCTION.ABSENCE",
                    "line_kind": "deduction",
                    "category": "deduction_unpaid_leave",
                    "label_en": "Unpaid absence deduction",
                    "amount": float(daily),
                    "sort_order": sort_i,
                    "input_line_id": str(ln.get("line_id") or "") or None,
                    "calc_notes": {"daily_rate": float(daily)},
                    "provenance": {
                        "attendance_snapshot_id": ln.get("attendance_snapshot_id"),
                        "source": "payroll_input_snapshot_lines",
                    },
                }
            )
            sort_i += 1

    # Never money-deduct suppressed absences
    for ln in input_lines:
        if ln.get("line_kind") == "suppressed_absence":
            warnings.append(
                {
                    "code": "suppressed_absence_no_money",
                    "message": "Absence suppressed by unpaid leave — no deduction",
                    "fact_date": str(ln.get("fact_date") or ""),
                }
            )

    if attendance_money and policy.get("lateness_money_enabled"):
        grace = int(policy.get("lateness_grace_minutes") or 0)
        for ln in input_lines:
            if ln.get("line_kind") != "attendance_day":
                continue
            late = float(ln.get("late_minutes") or 0)
            if late <= grace:
                continue
            scheduled = float(ln.get("expected_minutes") or 480) or 480
            frac = Decimal(str(max(0.0, late - grace))) / Decimal(str(scheduled))
            amt = money(daily * frac, rounding=rounding)
            if amt <= 0:
                continue
            lines.append(
                {
                    "component_code": "DEDUCTION.LATENESS",
                    "catalog_code": "DEDUCTION.LATENESS",
                    "line_kind": "deduction",
                    "label_en": "Lateness deduction",
                    "amount": float(amt),
                    "sort_order": sort_i,
                    "input_line_id": str(ln.get("line_id") or "") or None,
                    "calc_notes": {"late_minutes": late, "grace": grace, "daily_rate": float(daily)},
                    "provenance": {"attendance_snapshot_id": ln.get("attendance_snapshot_id")},
                }
            )
            sort_i += 1

    # Counsel-gated rule families
    def _require_rate(enabled: bool, family: str, fact_lines: list[dict[str, Any]], code: str) -> None:
        nonlocal sort_i
        if not enabled:
            for fl in fact_lines:
                warnings.append({"code": f"{family}_fact_no_money", "message": "Fact present; money disabled by policy"})
            return
        rate = approved_rates.get(family)
        if not rate:
            blockers.append(
                {
                    "code": "counsel_rate_required",
                    "rule_family": family,
                    "message": (
                        f"Policy enables {family} money but no approved Wathefni public baseline "
                        f"or counsel-attested rate table exists"
                    ),
                }
            )
            return
        if family == "sick_leave_fractions":
            frac = rate.get("fraction_payload") or {}
            for fl in fact_lines:
                lines.append(
                    {
                        "component_code": code,
                        "catalog_code": code,
                        "line_kind": "earning",
                        "label_en": "Sick leave (statutory bands)",
                        "amount": 0.0,
                        "sort_order": sort_i,
                        "calc_notes": {
                            "fraction_payload": frac,
                            "note": "Band table applied from public baseline; pay-base/year-basis may still need classification",
                            "rule_version_id": str(rate.get("rule_version_id") or rate.get("rate_table_id")),
                            "policy_version": rate.get("policy_version"),
                            "official_source_ref": rate.get("official_source_ref"),
                        },
                        "provenance": {
                            "input_line_id": str(fl.get("line_id") or ""),
                            "rule_family": family,
                            "authority_kind": rate.get("authority_kind"),
                            "source": rate.get("source"),
                        },
                    }
                )
                sort_i += 1
            return
        # If rates exist, apply multiplier
        mult = money(rate.get("multiplier") or 0, rounding=rounding)
        hourly = money(avg_basic / Decimal("30") / Decimal("8"), rounding=rounding)
        for fl in fact_lines:
            minutes = float(fl.get("overtime_minutes_fact") or fl.get("worked_minutes") or 0)
            hours = Decimal(str(minutes)) / Decimal("60")
            amt = money(hourly * hours * mult, rounding=rounding)
            lines.append(
                {
                    "component_code": code,
                    "catalog_code": code,
                    "line_kind": "earning",
                    "label_en": f"{family} (statutory baseline)",
                    "amount": float(amt),
                    "sort_order": sort_i,
                    "calc_notes": {
                        "multiplier": float(mult),
                        "hours": float(hours),
                        "rate_table_id": str(rate.get("rate_table_id")),
                        "rule_version_id": str(rate.get("rule_version_id") or ""),
                        "policy_version": rate.get("policy_version"),
                        "official_source_ref": rate.get("official_source_ref"),
                    },
                    "provenance": {
                        "input_line_id": str(fl.get("line_id") or ""),
                        "rule_family": family,
                        "authority_kind": rate.get("authority_kind"),
                        "source": rate.get("source"),
                    },
                }
            )
            sort_i += 1

    ot_facts = [ln for ln in input_lines if ln.get("line_kind") == "overtime_fact"]
    rest_facts = [ln for ln in input_lines if ln.get("line_kind") == "rest_day_work_fact"]
    ph_facts = [ln for ln in input_lines if ln.get("line_kind") == "public_holiday_work_fact"]
    sick_facts = [ln for ln in input_lines if ln.get("line_kind") == "leave_interval" and ln.get("classification") == "sick_leave"]

    _require_rate(bool(policy.get("ot_money_enabled")), "ot_ordinary", ot_facts, "OT_ORDINARY")
    _require_rate(bool(policy.get("rest_day_money_enabled")), "rest_day_work", rest_facts, "OT_REST_DAY_PH")
    _require_rate(bool(policy.get("public_holiday_money_enabled")), "public_holiday_work", ph_facts, "OT_REST_DAY_PH")
    if policy.get("sick_leave_money_enabled"):
        if not approved_rates.get("sick_leave_fractions"):
            blockers.append(
                {
                    "code": "counsel_rate_required",
                    "rule_family": "sick_leave_fractions",
                    "message": "Sick leave money enabled but approved public baseline / counsel fraction table missing",
                }
            )
        else:
            _require_rate(True, "sick_leave_fractions", sick_facts, "SICK_LEAVE")
    else:
        for fl in sick_facts:
            warnings.append({"code": "sick_leave_fact_no_money", "message": "Sick leave fact; money disabled"})

    if blockers:
        return {
            "ok": False,
            "status": "blocked",
            "employee_key": employee_key,
            "blockers": blockers,
            "warnings": warnings,
            "lines": lines,
            "totals": {"earnings": 0, "deductions": 0, "gross": 0, "net": 0},
        }

    earn = money(0)
    ded = money(0)
    for ln in lines:
        amt = money(ln.get("amount"), rounding=rounding)
        if ln.get("line_kind") == "deduction":
            ded += amt
        else:
            earn += amt
    gross = earn
    net = money(earn - ded, rounding=rounding)
    return {
        "ok": True,
        "status": "ok",
        "employee_key": employee_key,
        "blockers": blockers,
        "warnings": warnings,
        "lines": lines,
        "totals": {
            "earnings": float(earn),
            "deductions": float(ded),
            "gross": float(gross),
            "net": float(net),
        },
        "provenance": {
            "active_start": str(active_start),
            "active_end": str(active_end),
            "policy_version_id": str(policy.get("policy_version_id")),
            "avg_basic": float(avg_basic),
            "daily_rate": float(daily),
            "attendance_money": attendance_money,
        },
    }


def calculate_mode_a_preview(
    cur: Any,
    *,
    company_code: str,
    input_snapshot_id: str,
    actor_phone: str | None = None,
    reason: str | None = None,
    policy_version_id: str | None = None,
    employee_keys: list[str] | None = None,
) -> dict[str, Any]:
    denied = require_audit_reason(reason)
    if denied:
        return denied
    if not payroll_authority_p3_enabled_for_company(company_code):
        return {"ok": False, "error": "payroll_authority_p3_disabled_for_company"}
    ensure_payroll_components_policy_schema(cur)
    company = (company_code or "").upper()

    snap = p2.get_input_snapshot_by_id(cur, company_code=company, input_snapshot_id=input_snapshot_id)
    if not snap:
        return {"ok": False, "error": "input_snapshot_not_found"}
    if str(snap.get("status")) != "locked":
        return {
            "ok": False,
            "error": "input_snapshot_not_locked",
            "status": snap.get("status"),
            "message": "P3 calc requires a locked P2 input snapshot",
        }

    p_start = _parse_date(snap.get("period_start"))
    p_end = _parse_date(snap.get("period_end"))
    if not p_start or not p_end:
        return {"ok": False, "error": "invalid_input_period"}

    if policy_version_id:
        policy = get_policy_by_id(cur, company_code=company, policy_version_id=policy_version_id)
    else:
        policy = get_policy_for_period(cur, company_code=company, period_start=p_start)
    if not policy or str(policy.get("status")) != "approved":
        return {"ok": False, "error": "approved_policy_required"}

    ensure_counsel_required_rate_placeholders(cur, company_code=company, actor_phone=actor_phone)
    approved_rates = {
        fam: get_approved_rate(cur, company_code=company, rule_family=fam, as_of=p_start) for fam in COUNSEL_FAMILIES
    }
    statutory_provenance = {
        fam: {
            "rule_version_id": (approved_rates[fam] or {}).get("rule_version_id"),
            "policy_version": (approved_rates[fam] or {}).get("policy_version"),
            "authority_kind": (approved_rates[fam] or {}).get("authority_kind"),
            "official_source_ref": (approved_rates[fam] or {}).get("official_source_ref"),
            "source": (approved_rates[fam] or {}).get("source"),
            "legal_claim": (approved_rates[fam] or {}).get("legal_claim"),
        }
        for fam in COUNSEL_FAMILIES
        if approved_rates.get(fam)
    }

    employees = p2.list_input_snapshot_employees(cur, company_code=company, input_snapshot_id=input_snapshot_id)
    all_lines = p2.list_input_snapshot_lines(cur, company_code=company, input_snapshot_id=input_snapshot_id)
    if employee_keys:
        keys = set(employee_keys)
        employees = [e for e in employees if str(e.get("employee_key")) in keys]
    if payroll_authority_p3_synthetic_only():
        kept = []
        for e in employees:
            key = str(e.get("employee_key") or "")
            allowed = is_p3_synthetic_employee(employee_key=key)
            if not allowed:
                try:
                    import payroll_authority_production_p6 as p6

                    allowed = p6.employee_production_mutations_allowed(
                        cur, company_code=company, employee_key=key
                    )
                except Exception:
                    allowed = False
            if allowed:
                kept.append(e)
        employees = kept
    if not employees:
        return {"ok": False, "error": "no_employees_to_calculate"}

    # Load company components + assignments + adjustments once
    cur.execute(
        "SELECT * FROM payroll_company_components WHERE company_code=%s AND active=true",
        (company,),
    )
    co_comps = {str(r.get("company_component_id")): r for r in _rows(cur)}
    cur.execute(
        """
        SELECT * FROM payroll_component_assignments
        WHERE company_code=%s AND status='active'
          AND effective_from <= %s AND (effective_to IS NULL OR effective_to >= %s)
        """,
        (company, p_end, p_start),
    )
    assignments = _rows(cur)
    cur.execute(
        """
        SELECT * FROM payroll_one_off_adjustments
        WHERE company_code=%s AND status='approved'
          AND period_start=%s AND period_end=%s
        """,
        (company, p_start, p_end),
    )
    adjustments = _rows(cur)

    cat_fp = catalog_fingerprint(cur)
    policy_fp = str(policy.get("content_fingerprint") or "")
    input_fp = str(snap.get("content_fingerprint") or "")

    results = []
    comp_parts = []
    for emp in employees:
        key = str(emp.get("employee_key"))
        contracts = _load_contracts(cur, company_code=company, employee_key=key, period_start=p_start, period_end=p_end)
        comp_parts.append(
            {
                "employee_key": key,
                "contracts": [
                    {
                        "contract_id": str(c.get("contract_id")),
                        "effective_from": str(c.get("effective_from"))[:10],
                        "effective_to": str(c.get("effective_to") or "")[:10],
                        "row_version": c.get("row_version"),
                        "components": [
                            {"code": x.get("code"), "amount": float(x.get("amount") or 0), "unit": x.get("amount_unit")}
                            for x in (c.get("components") or [])
                        ],
                    }
                    for c in contracts
                ],
            }
        )
        emp_lines = [ln for ln in all_lines if str(ln.get("employee_key")) == key]
        results.append(
            _calc_employee(
                employee_key=key,
                period_start=p_start,
                period_end=p_end,
                emp_row=emp,
                input_lines=emp_lines,
                contracts=contracts,
                policy=policy,
                assignments=assignments,
                adjustments=adjustments,
                company_components=co_comps,
                approved_rates=approved_rates,
            )
        )

    comp_fp = fingerprint_payload(comp_parts)
    content = {
        "schema": CALC_SCHEMA,
        "company_code": company,
        "period_start": str(p_start),
        "period_end": str(p_end),
        "input_snapshot_id": input_snapshot_id,
        "policy_version_id": str(policy.get("policy_version_id")),
        "catalog_fingerprint": cat_fp,
        "compensation_fingerprint": comp_fp,
        "policy_fingerprint": policy_fp,
        "input_fingerprint": input_fp,
        "statutory_policy_provenance": statutory_provenance,
        "money_authority": MONEY_PREVIEW,
        "employees": _json_safe(results),
    }
    content_fp = fingerprint_payload(content)

    # Idempotent
    cur.execute(
        """
        SELECT * FROM payroll_calc_preview_runs
        WHERE company_code=%s AND content_fingerprint=%s AND status='calculated'
        ORDER BY created_at DESC LIMIT 1
        """,
        (company, content_fp),
    )
    existing = _row(cur)
    if existing:
        return {
            "ok": True,
            "idempotent": True,
            "calc_run": _json_safe(existing),
            **honesty_payload(),
        }

    blocked = any(not r.get("ok") for r in results)
    tot_earn = money(sum(Decimal(str((r.get("totals") or {}).get("earnings") or 0)) for r in results if r.get("ok")))
    tot_ded = money(sum(Decimal(str((r.get("totals") or {}).get("deductions") or 0)) for r in results if r.get("ok")))
    tot_net = money(tot_earn - tot_ded)
    blocker_count = sum(len(r.get("blockers") or []) for r in results)
    warning_count = sum(len(r.get("warnings") or []) for r in results)
    run_id = str(uuid.uuid4())
    status = "blocked" if blocked and all(not r.get("ok") for r in results) else ("calculated" if not blocked else "blocked")
    # Allow partial: if any ok, status calculated with blockers noted; if all blocked → blocked
    if any(r.get("ok") for r in results) and blocked:
        status = "calculated"

    cur.execute(
        """
        INSERT INTO payroll_calc_preview_runs (
          calc_run_id, company_code, period_start, period_end, input_snapshot_id, policy_version_id,
          catalog_fingerprint, compensation_fingerprint, policy_fingerprint, input_fingerprint,
          content_fingerprint, status, money_authority, employee_count,
          totals_earnings, totals_deductions, totals_gross, totals_net,
          blocker_count, warning_count, result_payload, provenance, decision_note, created_by_phone
        ) VALUES (
          %s,%s,%s,%s,%s,%s,
          %s,%s,%s,%s,
          %s,%s,'preview_non_authoritative',%s,
          %s,%s,%s,%s,
          %s,%s,%s::jsonb,%s::jsonb,%s,%s
        )
        RETURNING *
        """,
        (
            run_id,
            company,
            p_start,
            p_end,
            input_snapshot_id,
            policy.get("policy_version_id"),
            cat_fp,
            comp_fp,
            policy_fp,
            input_fp,
            content_fp,
            status,
            len(results),
            float(tot_earn),
            float(tot_ded),
            float(tot_earn),
            float(tot_net),
            blocker_count,
            warning_count,
            json.dumps(_json_safe(content)),
            json.dumps(
                _json_safe(
                    {
                        "input_snapshot_id": input_snapshot_id,
                        "policy_version_id": str(policy.get("policy_version_id")),
                        "policy_version_number": policy.get("version_number"),
                    }
                )
            ),
            str(reason).strip(),
            digits_phone(actor_phone),
        ),
    )
    header = _row(cur)

    for r in results:
        cur.execute(
            """
            INSERT INTO payroll_calc_preview_employee_results (
              calc_run_id, company_code, employee_key, status,
              totals_earnings, totals_deductions, totals_gross, totals_net,
              blockers, warnings, provenance
            ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb,%s::jsonb,%s::jsonb)
            """,
            (
                run_id,
                company,
                r["employee_key"],
                r.get("status") or ("ok" if r.get("ok") else "blocked"),
                float((r.get("totals") or {}).get("earnings") or 0),
                float((r.get("totals") or {}).get("deductions") or 0),
                float((r.get("totals") or {}).get("gross") or 0),
                float((r.get("totals") or {}).get("net") or 0),
                json.dumps(_json_safe(r.get("blockers") or [])),
                json.dumps(_json_safe(r.get("warnings") or [])),
                json.dumps(_json_safe(r.get("provenance") or {})),
            ),
        )
        for ln in r.get("lines") or []:
            cur.execute(
                """
                INSERT INTO payroll_calc_preview_lines (
                  calc_run_id, company_code, employee_key, component_code, catalog_code,
                  line_kind, category, label_en, label_ar, amount, policy_version_id,
                  input_line_id, contract_id, sort_order, calc_notes, provenance
                ) VALUES (
                  %s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb,%s::jsonb
                )
                """,
                (
                    run_id,
                    company,
                    r["employee_key"],
                    ln.get("component_code"),
                    ln.get("catalog_code"),
                    ln.get("line_kind"),
                    ln.get("category"),
                    ln.get("label_en"),
                    ln.get("label_ar"),
                    float(ln.get("amount") or 0),
                    policy.get("policy_version_id"),
                    ln.get("input_line_id"),
                    ln.get("contract_id"),
                    int(ln.get("sort_order") or 0),
                    json.dumps(_json_safe(ln.get("calc_notes") or {})),
                    json.dumps(_json_safe(ln.get("provenance") or {})),
                ),
            )

    _record_event(
        cur,
        company_code=company,
        calc_run_id=run_id,
        event_type="calc_preview_calculated",
        payload={"content_fingerprint": content_fp, "status": status, "blocker_count": blocker_count},
        actor_phone=actor_phone,
    )
    return {
        "ok": True,
        "idempotent": False,
        "calc_run": _json_safe(header or {}),
        "employees": _json_safe(results),
        **honesty_payload(),
    }


def get_calc_run(cur: Any, *, company_code: str, calc_run_id: str) -> dict[str, Any] | None:
    ensure_payroll_components_policy_schema(cur)
    cur.execute(
        "SELECT * FROM payroll_calc_preview_runs WHERE company_code=%s AND calc_run_id=%s",
        ((company_code or "").upper(), calc_run_id),
    )
    return _row(cur)


def list_calc_lines(cur: Any, *, company_code: str, calc_run_id: str, employee_key: str | None = None) -> list[dict[str, Any]]:
    ensure_payroll_components_policy_schema(cur)
    if employee_key:
        cur.execute(
            """
            SELECT * FROM payroll_calc_preview_lines
            WHERE company_code=%s AND calc_run_id=%s AND employee_key=%s
            ORDER BY sort_order
            """,
            ((company_code or "").upper(), calc_run_id, employee_key),
        )
    else:
        cur.execute(
            """
            SELECT * FROM payroll_calc_preview_lines
            WHERE company_code=%s AND calc_run_id=%s
            ORDER BY employee_key, sort_order
            """,
            ((company_code or "").upper(), calc_run_id),
        )
    return _rows(cur)


def list_calc_employee_results(cur: Any, *, company_code: str, calc_run_id: str) -> list[dict[str, Any]]:
    ensure_payroll_components_policy_schema(cur)
    cur.execute(
        """
        SELECT * FROM payroll_calc_preview_employee_results
        WHERE company_code=%s AND calc_run_id=%s ORDER BY employee_key
        """,
        ((company_code or "").upper(), calc_run_id),
    )
    return _rows(cur)


def workspace_bootstrap(cur: Any, *, company_code: str) -> dict[str, Any]:
    ensure_payroll_components_policy_schema(cur)
    company = (company_code or "").upper()
    catalog = list_component_catalog(cur)
    cur.execute(
        """
        SELECT * FROM payroll_company_policy_versions
        WHERE company_code=%s ORDER BY version_number DESC LIMIT 10
        """,
        (company,),
    )
    policies = _rows(cur)
    cur.execute(
        "SELECT * FROM payroll_company_components WHERE company_code=%s AND active=true ORDER BY component_code",
        (company,),
    )
    components = _rows(cur)
    cur.execute(
        """
        SELECT calc_run_id::text, period_start, period_end, status, money_authority,
               content_fingerprint, created_at, totals_net, blocker_count
        FROM payroll_calc_preview_runs
        WHERE company_code=%s
        ORDER BY created_at DESC LIMIT 20
        """,
        (company,),
    )
    runs = _rows(cur)
    return {
        "ok": True,
        "catalog": _json_safe(catalog),
        "policies": _json_safe(policies),
        "company_components": _json_safe(components),
        "recent_calc_runs": _json_safe(runs),
        **honesty_payload(),
    }
