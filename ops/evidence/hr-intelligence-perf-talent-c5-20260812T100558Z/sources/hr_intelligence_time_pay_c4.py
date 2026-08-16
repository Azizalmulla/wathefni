#!/usr/bin/env python3
"""Wave 5 C4 — Time, Leave, Shift, OT, and Payroll Intelligence.

All tables in this module are governed projections, not alternate systems of
record. Formula handlers plug into the C1 Registry evaluator. Payroll money is
accepted only from sealed Wathefni-authoritative periods and no FX conversion
is performed.
"""
from __future__ import annotations

import json
import os
import uuid
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any

import hr_intelligence_registry_c1 as c1

PHASE = "hr_intelligence_time_pay_c4"
CONTRACT_VERSION = "hr_intelligence_time_pay_c4_v1"
PASS_STAMP = "HR_INTELLIGENCE_TIME_PAY_FULL_PASS"
COMMERCIAL_MODULE_KEY = "analytics"
_ON = {"1", "true", "yes", "on"}

ATTENDANCE_RATE_KEY = "time.attendance_rate"
ABSENTEEISM_RATE_KEY = "time.absenteeism.rate"
LATENESS_EMPLOYEES_KEY = "time.lateness.employees"
LATENESS_OCCURRENCES_KEY = "time.lateness.occurrences"
LATENESS_MINUTES_KEY = "time.lateness.minutes"
EARLY_LEAVE_OCCURRENCES_KEY = "time.early_leave.occurrences"
MISSING_PUNCHES_KEY = "time.missing_punches"
LEAVE_UTILIZATION_RATE_KEY = "leave.utilization.rate"
LEAVE_TAKEN_DAYS_KEY = "leave.taken.days"
SHIFTS_SCHEDULED_HOURS_KEY = "shifts.scheduled_hours"
OT_APPROVED_KEY = "overtime.approved"
OT_PAYROLL_EXPORTED_KEY = "overtime.payroll_exported"
OT_PAID_KEY = "overtime.paid"
PAYROLL_WORKFORCE_COST_KEY = "payroll.workforce_cost"
PAYROLL_MOVEMENT_KEY = "payroll.movement"
PAYROLL_COMPONENT_MOVEMENT_KEY = "payroll.component_movement"
SETTLEMENT_FINALIZED_KEY = "payroll.settlement.finalized"
PAYMENT_ACK_KEY = "payroll.payment_file.acknowledged"

FORMULA_KINDS = {
    ATTENDANCE_RATE_KEY: "time_attendance_rate",
    ABSENTEEISM_RATE_KEY: "time_absenteeism_rate",
    LATENESS_EMPLOYEES_KEY: "time_lateness_employees",
    LATENESS_OCCURRENCES_KEY: "time_lateness_occurrences",
    LATENESS_MINUTES_KEY: "time_lateness_minutes",
    EARLY_LEAVE_OCCURRENCES_KEY: "time_early_leave_occurrences",
    MISSING_PUNCHES_KEY: "time_missing_punches",
    LEAVE_UTILIZATION_RATE_KEY: "leave_utilization_rate",
    LEAVE_TAKEN_DAYS_KEY: "leave_taken_days",
    SHIFTS_SCHEDULED_HOURS_KEY: "shifts_scheduled_hours",
    OT_APPROVED_KEY: "ot_approved",
    OT_PAYROLL_EXPORTED_KEY: "ot_payroll_exported",
    OT_PAID_KEY: "ot_paid",
    PAYROLL_WORKFORCE_COST_KEY: "payroll_workforce_cost",
    PAYROLL_MOVEMENT_KEY: "payroll_movement",
    PAYROLL_COMPONENT_MOVEMENT_KEY: "payroll_component_movement",
    SETTLEMENT_FINALIZED_KEY: "settlement_finalized",
    PAYMENT_ACK_KEY: "payment_ack",
}
ALL_SEMANTIC_KEYS = tuple(FORMULA_KINDS)

STATUS_LABELS = {
    "present": {"en": "Present", "ar": "حاضر"},
    "late": {"en": "Late", "ar": "متأخر"},
    "completed": {"en": "Completed", "ar": "مكتمل"},
    "absent": {"en": "Unauthorized absence", "ar": "غياب غير مصرح"},
    "approved_leave": {"en": "Approved leave", "ar": "إجازة معتمدة"},
    "incomplete": {"en": "Incomplete", "ar": "غير مكتمل"},
    "void": {"en": "Void", "ar": "ملغى"},
    "approved": {"en": "Approved", "ar": "معتمد"},
    "rejected": {"en": "Rejected", "ar": "مرفوض"},
    "cancelled": {"en": "Cancelled", "ar": "ملغى"},
    "payroll_exported": {"en": "Exported to payroll", "ar": "مُصدّر إلى الرواتب"},
    "paid": {"en": "Paid", "ar": "مدفوع"},
    "finalized": {"en": "Finalized", "ar": "نهائي"},
    "acknowledged": {"en": "Acknowledged", "ar": "تم الإقرار"},
    "unavailable": {"en": "Unavailable", "ar": "غير متاح"},
    "insufficient_data": {"en": "Insufficient data", "ar": "بيانات غير كافية"},
    "not_applicable": {"en": "Not applicable", "ar": "غير منطبق"},
    "suppressed": {"en": "Suppressed", "ar": "محجوب"},
    "forbidden": {"en": "Forbidden", "ar": "ممنوع"},
}


def _env_on(name: str, default: str = "off") -> bool:
    return (os.environ.get(name) or default).strip().lower() in _ON


def _digits(value: Any) -> str:
    return "".join(ch for ch in str(value or "") if ch.isdigit())


def company_code_norm(company_code: str | None) -> str:
    return str(company_code or "").strip().upper()


def _as_date(value: Any) -> date | None:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value)[:10])


def _number(value: Any) -> float:
    return float(value or 0)


def _parse_window(time_window: dict[str, Any]) -> tuple[date, date]:
    end = _as_date(time_window.get("period_end") or time_window.get("end")) or date.today()
    start = _as_date(time_window.get("period_start") or time_window.get("start")) or (end - timedelta(days=90))
    return start, end


def status_label(status: str | None, *, lang: str = "en") -> str:
    key = str(status or "").strip().lower()
    pack = STATUS_LABELS.get(key) or {"en": key or "unknown", "ar": key or "غير معروف"}
    return str(pack["ar" if lang.lower().startswith("ar") else "en"])


def honesty_payload(*, company_code: str | None = None) -> dict[str, Any]:
    return {
        "phase": PHASE,
        "contract_version": CONTRACT_VERSION,
        "pass_stamp": PASS_STAMP,
        "commercial_module_key": COMMERCIAL_MODULE_KEY,
        "uses_c1_registry_evaluator": True,
        "no_second_analytics_math_engine": True,
        "projections_are_not_alternate_sot": True,
        "raw_punches_are_not_authoritative": True,
        "attendance_requires_expected_work_days": True,
        "approved_leave_is_not_absenteeism": True,
        "approved_ot_is_not_exported_or_paid": True,
        "sealed_payroll_required": True,
        "settlement_finalized_is_not_paid": True,
        "payment_acknowledged_is_not_paid": True,
        "currency": "KWD",
        "fx_conversion": False,
        "assistant_mutations": False,
        "company_code": company_code_norm(company_code) if company_code else None,
    }


def rollback_guidance() -> dict[str, Any]:
    return {
        "phase": PHASE,
        "preserves_history": True,
        "steps": [
            "WATHEFNI_HR_INTELLIGENCE_TIME_PAY_C4=off",
            "Clear WATHEFNI_HR_INTELLIGENCE_TIME_PAY_COMPANIES",
            "WATHEFNI_ANALYTICS_KILL=on (optional)",
            "C1 registry, projections, audit, and evaluation history remain intact",
        ],
    }


def runtime_gate_for_company(company_code: str | None) -> dict[str, Any]:
    company = company_code_norm(company_code)
    if not company:
        return {"ok": False, "enabled": False, "error": "company_required", "phase": PHASE}
    if _env_on("WATHEFNI_ANALYTICS_KILL", "off"):
        return {"ok": False, "enabled": False, "error": "analytics_kill_switch", "gate": "kill", "phase": PHASE}
    gate = c1.runtime_gate_for_company(company)
    if not gate.get("ok"):
        return {**gate, "ok": False, "error": "c1_registry_required", "phase": PHASE}
    if not _env_on("WATHEFNI_HR_INTELLIGENCE_TIME_PAY_C4", "off"):
        return {
            "ok": False, "enabled": False, "error": "hr_intelligence_time_pay_c4_off",
            "gate": "runtime_flag", "phase": PHASE,
        }
    raw = str(os.environ.get("WATHEFNI_HR_INTELLIGENCE_TIME_PAY_COMPANIES") or "").strip()
    allowed = {p.strip().upper() for p in raw.split(",") if p.strip()} if raw else set()
    if not allowed or company not in allowed:
        return {
            "ok": False, "enabled": False,
            "error": "hr_intelligence_time_pay_company_not_allowlisted",
            "gate": "company_allowlist", "phase": PHASE, "company_code": company,
        }
    return {"ok": True, "enabled": True, "company_code": company, "phase": PHASE}


def ensure_hr_intelligence_time_pay_c4_schema(cur: Any, *, force: bool = False) -> None:
    _ = force
    c1.ensure_hr_intelligence_registry_c1_schema(cur)
    statements = [
        """
        CREATE TABLE IF NOT EXISTS hr_intelligence_c4_company_settings (
          company_code text PRIMARY KEY,
          enabled boolean NOT NULL DEFAULT false,
          attendance_module_enabled boolean NOT NULL DEFAULT true,
          leave_module_enabled boolean NOT NULL DEFAULT true,
          shifts_module_enabled boolean NOT NULL DEFAULT true,
          ot_module_enabled boolean NOT NULL DEFAULT true,
          payroll_module_enabled boolean NOT NULL DEFAULT true,
          attendance_rate_expected_work_required boolean NOT NULL DEFAULT true,
          workforce_cost_basis text NOT NULL DEFAULT 'gross',
          included_component_classes jsonb NOT NULL DEFAULT '["earning","allowance","ot"]'::jsonb,
          currency text NOT NULL DEFAULT 'KWD',
          enabled_by_phone text,
          enabled_reason text,
          enabled_at timestamptz,
          disabled_at timestamptz,
          updated_at timestamptz NOT NULL DEFAULT now(),
          CHECK (workforce_cost_basis IN ('gross','net','included_components'))
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS hr_intelligence_attendance_days (
          row_id uuid PRIMARY KEY,
          company_code text NOT NULL,
          employee_key text NOT NULL,
          work_date date NOT NULL,
          status text NOT NULL,
          exception_state text,
          late_minutes numeric NOT NULL DEFAULT 0,
          early_leave_minutes numeric NOT NULL DEFAULT 0,
          expected_work boolean NOT NULL DEFAULT false,
          scheduled boolean NOT NULL DEFAULT false,
          department text,
          manager_employee_key text,
          location text,
          source_authority text NOT NULL,
          correction_applied boolean NOT NULL DEFAULT false,
          raw_punch_only boolean NOT NULL DEFAULT false,
          updated_at timestamptz NOT NULL DEFAULT now(),
          UNIQUE (company_code, employee_key, work_date),
          CHECK (status IN ('present','late','completed','absent','approved_leave','void','incomplete'))
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS hr_intelligence_leave_ledger_facts (
          row_id uuid PRIMARY KEY,
          company_code text NOT NULL,
          entry_id text NOT NULL,
          employee_key text NOT NULL,
          leave_type text NOT NULL,
          entry_kind text NOT NULL,
          days numeric NOT NULL,
          effective_date date NOT NULL,
          request_status text,
          department text,
          confidential boolean NOT NULL DEFAULT false,
          source_authority text NOT NULL DEFAULT 'leave_ledger',
          updated_at timestamptz NOT NULL DEFAULT now(),
          UNIQUE (company_code, entry_id)
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS hr_intelligence_leave_entitlements (
          row_id uuid PRIMARY KEY,
          company_code text NOT NULL,
          employee_key text NOT NULL,
          leave_type text NOT NULL,
          period_year integer NOT NULL,
          entitlement_days numeric NOT NULL,
          updated_at timestamptz NOT NULL DEFAULT now(),
          UNIQUE (company_code, employee_key, leave_type, period_year)
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS hr_intelligence_shift_assignments (
          row_id uuid PRIMARY KEY,
          company_code text NOT NULL,
          assignment_key text NOT NULL,
          employee_key text NOT NULL,
          work_date date NOT NULL,
          scheduled_hours numeric NOT NULL,
          status text NOT NULL,
          department text,
          manager_employee_key text,
          source_authority text NOT NULL DEFAULT 'shift_assignment',
          updated_at timestamptz NOT NULL DEFAULT now(),
          UNIQUE (company_code, assignment_key)
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS hr_intelligence_ot_requests (
          row_id uuid PRIMARY KEY,
          company_code text NOT NULL,
          ot_key text NOT NULL,
          employee_key text NOT NULL,
          status text NOT NULL,
          hours numeric NOT NULL,
          ot_date date NOT NULL,
          paid_in_payroll boolean NOT NULL DEFAULT false,
          department text,
          manager_employee_key text,
          source_authority text NOT NULL DEFAULT 'overtime_request',
          updated_at timestamptz NOT NULL DEFAULT now(),
          UNIQUE (company_code, ot_key),
          CHECK (status IN ('approved','rejected','cancelled','payroll_exported'))
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS hr_intelligence_payroll_periods (
          row_id uuid PRIMARY KEY,
          company_code text NOT NULL,
          period_key text NOT NULL,
          period_start date NOT NULL,
          period_end date NOT NULL,
          authoritative_finalized boolean NOT NULL DEFAULT false,
          money_authority text,
          status text NOT NULL,
          currency text NOT NULL DEFAULT 'KWD',
          totals_gross numeric,
          totals_net numeric,
          sealed_at timestamptz,
          watermark text,
          updated_at timestamptz NOT NULL DEFAULT now(),
          UNIQUE (company_code, period_key)
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS hr_intelligence_payroll_lines (
          row_id uuid PRIMARY KEY,
          company_code text NOT NULL,
          period_key text NOT NULL,
          line_key text NOT NULL,
          employee_key text NOT NULL,
          component_key text NOT NULL,
          component_class text NOT NULL,
          display_label text,
          amount numeric NOT NULL,
          currency text NOT NULL DEFAULT 'KWD',
          department text,
          updated_at timestamptz NOT NULL DEFAULT now(),
          UNIQUE (company_code, period_key, line_key)
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS hr_intelligence_settlements (
          row_id uuid PRIMARY KEY,
          company_code text NOT NULL,
          settlement_key text NOT NULL,
          status text NOT NULL,
          amount numeric NOT NULL,
          currency text NOT NULL DEFAULT 'KWD',
          paid boolean NOT NULL DEFAULT false,
          effective_date date NOT NULL DEFAULT CURRENT_DATE,
          employee_key text,
          updated_at timestamptz NOT NULL DEFAULT now(),
          UNIQUE (company_code, settlement_key),
          CHECK (status IN ('calculated','approved','finalized'))
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS hr_intelligence_payment_files (
          row_id uuid PRIMARY KEY,
          company_code text NOT NULL,
          file_key text NOT NULL,
          status text NOT NULL,
          effective_date date NOT NULL DEFAULT CURRENT_DATE,
          updated_at timestamptz NOT NULL DEFAULT now(),
          UNIQUE (company_code, file_key),
          CHECK (status IN ('generated','acknowledged'))
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS hr_intelligence_c4_audit (
          audit_id bigserial PRIMARY KEY,
          company_code text,
          action text NOT NULL,
          actor_phone text,
          reason text,
          subject_type text,
          subject_id text,
          payload jsonb NOT NULL DEFAULT '{}'::jsonb,
          created_at timestamptz NOT NULL DEFAULT now()
        )
        """,
    ]
    for statement in statements:
        cur.execute(statement)


def _audit(cur: Any, *, company_code: str, action: str, actor_phone: str,
           reason: str | None = None, subject_type: str | None = None,
           subject_id: str | None = None, payload: dict[str, Any] | None = None) -> None:
    cur.execute(
        """
        INSERT INTO hr_intelligence_c4_audit
          (company_code, action, actor_phone, reason, subject_type, subject_id, payload)
        VALUES (%s,%s,%s,%s,%s,%s,%s::jsonb)
        """,
        (
            company_code_norm(company_code), action, _digits(actor_phone),
            str(reason).strip()[:500] if reason else None, subject_type, subject_id,
            json.dumps(payload or {}, default=str),
        ),
    )


def _entitled(cur: Any, company_code: str) -> dict[str, Any]:
    gate = runtime_gate_for_company(company_code)
    if not gate.get("ok"):
        return gate
    company = gate["company_code"]
    ensure_hr_intelligence_time_pay_c4_schema(cur)
    c1_ent = c1._entitled(cur, company)
    if not c1_ent.get("ok"):
        return {"ok": False, "error": "c1_company_intelligence_disabled", "detail": c1_ent}
    cur.execute("SELECT * FROM hr_intelligence_c4_company_settings WHERE company_code=%s", (company,))
    row = cur.fetchone()
    if not row or not bool(dict(row).get("enabled")):
        return {"ok": False, "error": "company_time_pay_intelligence_disabled", "company_code": company}
    return {"ok": True, "company_code": company, "settings": dict(row), "c1_settings": c1_ent["settings"]}


def enable_company_time_pay_intelligence(
    cur: Any, *, company_code: str, actor_phone: str, reason: str,
    attendance_module_enabled: bool = True, leave_module_enabled: bool = True,
    shifts_module_enabled: bool = True, ot_module_enabled: bool = True,
    payroll_module_enabled: bool = True,
    attendance_rate_expected_work_required: bool = True,
    workforce_cost_basis: str = "gross",
    included_component_classes: list[str] | None = None,
    currency: str = "KWD",
) -> dict[str, Any]:
    if not str(reason or "").strip():
        return {"ok": False, "error": "audit_reason_required"}
    gate = runtime_gate_for_company(company_code)
    if not gate.get("ok"):
        return gate
    company = gate["company_code"]
    basis = str(workforce_cost_basis or "gross").lower()
    if basis not in {"gross", "net", "included_components"}:
        return {"ok": False, "error": "invalid_workforce_cost_basis"}
    c1.enable_company_hr_intelligence(
        cur, company_code=company, actor_phone=actor_phone, reason="c4 requires c1"
    )
    ensure_hr_intelligence_time_pay_c4_schema(cur)
    classes = included_component_classes or ["earning", "allowance", "ot"]
    cur.execute(
        """
        INSERT INTO hr_intelligence_c4_company_settings (
          company_code, enabled, attendance_module_enabled, leave_module_enabled,
          shifts_module_enabled, ot_module_enabled, payroll_module_enabled,
          attendance_rate_expected_work_required, workforce_cost_basis,
          included_component_classes, currency, enabled_by_phone, enabled_reason,
          enabled_at, disabled_at, updated_at
        ) VALUES (%s,true,%s,%s,%s,%s,%s,%s,%s,%s::jsonb,%s,%s,%s,now(),NULL,now())
        ON CONFLICT (company_code) DO UPDATE SET
          enabled=true,
          attendance_module_enabled=EXCLUDED.attendance_module_enabled,
          leave_module_enabled=EXCLUDED.leave_module_enabled,
          shifts_module_enabled=EXCLUDED.shifts_module_enabled,
          ot_module_enabled=EXCLUDED.ot_module_enabled,
          payroll_module_enabled=EXCLUDED.payroll_module_enabled,
          attendance_rate_expected_work_required=EXCLUDED.attendance_rate_expected_work_required,
          workforce_cost_basis=EXCLUDED.workforce_cost_basis,
          included_component_classes=EXCLUDED.included_component_classes,
          currency=EXCLUDED.currency,
          enabled_by_phone=EXCLUDED.enabled_by_phone,
          enabled_reason=EXCLUDED.enabled_reason,
          enabled_at=now(), disabled_at=NULL, updated_at=now()
        RETURNING *
        """,
        (
            company, bool(attendance_module_enabled), bool(leave_module_enabled),
            bool(shifts_module_enabled), bool(ot_module_enabled), bool(payroll_module_enabled),
            bool(attendance_rate_expected_work_required), basis, json.dumps(classes),
            str(currency or "KWD").upper(), _digits(actor_phone), str(reason).strip()[:500],
        ),
    )
    settings = dict(cur.fetchone())
    _audit(cur, company_code=company, action="company_enabled", actor_phone=actor_phone,
           reason=reason, subject_type="company", subject_id=company)
    seed_time_pay_definitions(cur, actor_phone=actor_phone)
    _register_handlers()
    return {"ok": True, "settings": settings, **honesty_payload(company_code=company)}


def disable_company_time_pay_intelligence(
    cur: Any, *, company_code: str, actor_phone: str, reason: str
) -> dict[str, Any]:
    if not str(reason or "").strip():
        return {"ok": False, "error": "audit_reason_required"}
    company = company_code_norm(company_code)
    ensure_hr_intelligence_time_pay_c4_schema(cur)
    cur.execute(
        """
        UPDATE hr_intelligence_c4_company_settings
           SET enabled=false, disabled_at=now(), updated_at=now()
         WHERE company_code=%s RETURNING *
        """,
        (company,),
    )
    row = cur.fetchone()
    _audit(cur, company_code=company, action="company_disabled", actor_phone=actor_phone,
           reason=reason, payload={"preserves_history": True})
    return {"ok": True, "settings": dict(row) if row else None, "preserves_history": True}


def set_module_flags(
    cur: Any, *, company_code: str, actor_phone: str, reason: str,
    attendance_module_enabled: bool | None = None,
    leave_module_enabled: bool | None = None,
    shifts_module_enabled: bool | None = None,
    ot_module_enabled: bool | None = None,
    payroll_module_enabled: bool | None = None,
    attendance_rate_expected_work_required: bool | None = None,
) -> dict[str, Any]:
    if not str(reason or "").strip():
        return {"ok": False, "error": "audit_reason_required"}
    ent = _entitled(cur, company_code)
    if not ent.get("ok"):
        return ent
    s, company = ent["settings"], ent["company_code"]
    vals = {
        "attendance_module_enabled": s["attendance_module_enabled"] if attendance_module_enabled is None else bool(attendance_module_enabled),
        "leave_module_enabled": s["leave_module_enabled"] if leave_module_enabled is None else bool(leave_module_enabled),
        "shifts_module_enabled": s["shifts_module_enabled"] if shifts_module_enabled is None else bool(shifts_module_enabled),
        "ot_module_enabled": s["ot_module_enabled"] if ot_module_enabled is None else bool(ot_module_enabled),
        "payroll_module_enabled": s["payroll_module_enabled"] if payroll_module_enabled is None else bool(payroll_module_enabled),
        "attendance_rate_expected_work_required": s["attendance_rate_expected_work_required"] if attendance_rate_expected_work_required is None else bool(attendance_rate_expected_work_required),
    }
    cur.execute(
        """
        UPDATE hr_intelligence_c4_company_settings SET
          attendance_module_enabled=%s, leave_module_enabled=%s,
          shifts_module_enabled=%s, ot_module_enabled=%s,
          payroll_module_enabled=%s, attendance_rate_expected_work_required=%s,
          updated_at=now()
        WHERE company_code=%s RETURNING *
        """,
        (*vals.values(), company),
    )
    row = dict(cur.fetchone())
    _audit(cur, company_code=company, action="module_flags_updated", actor_phone=actor_phone,
           reason=reason, payload=vals)
    return {"ok": True, "settings": row}


# Compatibility aliases matching the concise charter verbs.
enable = enable_company_time_pay_intelligence
disable = disable_company_time_pay_intelligence


def _require_write(cur: Any, company_code: str, reason: str) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    if not str(reason or "").strip():
        return None, {"ok": False, "error": "audit_reason_required"}
    ent = _entitled(cur, company_code)
    if not ent.get("ok"):
        return None, ent
    return ent, None


def upsert_attendance_day(
    cur: Any, *, company_code: str, actor_phone: str, employee_key: str,
    work_date: date | str, status: str, reason: str,
    exception_state: str | None = None, late_minutes: float = 0,
    early_leave_minutes: float = 0, expected_work: bool = False,
    scheduled: bool = False, department: str | None = None,
    manager_employee_key: str | None = None, location: str | None = None,
    source_authority: str = "attendance_projection",
    correction_applied: bool = False, raw_punch_only: bool = False,
) -> dict[str, Any]:
    ent, error = _require_write(cur, company_code, reason)
    if error:
        return error
    company = ent["company_code"]
    st = str(status or "").lower()
    if st not in {"present", "late", "completed", "absent", "approved_leave", "void", "incomplete"}:
        return {"ok": False, "error": "invalid_attendance_status"}
    cur.execute(
        """
        INSERT INTO hr_intelligence_attendance_days (
          row_id, company_code, employee_key, work_date, status, exception_state,
          late_minutes, early_leave_minutes, expected_work, scheduled, department,
          manager_employee_key, location, source_authority, correction_applied, raw_punch_only
        ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
        ON CONFLICT (company_code, employee_key, work_date) DO UPDATE SET
          status=EXCLUDED.status, exception_state=EXCLUDED.exception_state,
          late_minutes=EXCLUDED.late_minutes, early_leave_minutes=EXCLUDED.early_leave_minutes,
          expected_work=EXCLUDED.expected_work, scheduled=EXCLUDED.scheduled,
          department=EXCLUDED.department, manager_employee_key=EXCLUDED.manager_employee_key,
          location=EXCLUDED.location, source_authority=EXCLUDED.source_authority,
          correction_applied=EXCLUDED.correction_applied,
          raw_punch_only=EXCLUDED.raw_punch_only, updated_at=now()
        RETURNING *
        """,
        (
            str(uuid.uuid4()), company, str(employee_key), _as_date(work_date), st,
            exception_state, Decimal(str(late_minutes or 0)), Decimal(str(early_leave_minutes or 0)),
            bool(expected_work), bool(scheduled), department, manager_employee_key,
            location, source_authority, bool(correction_applied), bool(raw_punch_only),
        ),
    )
    row = dict(cur.fetchone())
    _audit(cur, company_code=company, action="attendance_day_upserted", actor_phone=actor_phone,
           reason=reason, subject_type="attendance_day",
           subject_id=f"{employee_key}:{_as_date(work_date)}",
           payload={"raw_punch_only": bool(raw_punch_only), "source_authority": source_authority})
    return {"ok": True, "attendance_day": row}


def apply_attendance_correction(
    cur: Any, *, company_code: str, actor_phone: str, employee_key: str,
    work_date: date | str, status: str, reason: str, **updates: Any,
) -> dict[str, Any]:
    ent, error = _require_write(cur, company_code, reason)
    if error:
        return error
    company = ent["company_code"]
    cur.execute(
        "SELECT * FROM hr_intelligence_attendance_days WHERE company_code=%s AND employee_key=%s AND work_date=%s",
        (company, employee_key, _as_date(work_date)),
    )
    prior = cur.fetchone()
    if not prior:
        return {"ok": False, "error": "attendance_day_not_found"}
    old = dict(prior)
    allowed = {
        "exception_state", "late_minutes", "early_leave_minutes", "expected_work",
        "scheduled", "department", "manager_employee_key", "location", "source_authority",
    }
    values = {k: updates.get(k, old.get(k)) for k in allowed}
    out = upsert_attendance_day(
        cur, company_code=company, actor_phone=actor_phone, employee_key=employee_key,
        work_date=work_date, status=status, reason=reason, correction_applied=True,
        raw_punch_only=False, **values,
    )
    out["domain_audit_rewritten"] = False
    return out


def upsert_leave_ledger_entry(
    cur: Any, *, company_code: str, actor_phone: str, entry_id: str,
    employee_key: str, leave_type: str, entry_kind: str, days: float,
    effective_date: date | str, reason: str, request_status: str | None = None,
    department: str | None = None, confidential: bool = False,
    source_authority: str = "leave_ledger",
) -> dict[str, Any]:
    ent, error = _require_write(cur, company_code, reason)
    if error:
        return error
    company = ent["company_code"]
    cur.execute(
        """
        INSERT INTO hr_intelligence_leave_ledger_facts (
          row_id, company_code, entry_id, employee_key, leave_type, entry_kind,
          days, effective_date, request_status, department, confidential, source_authority
        ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
        ON CONFLICT (company_code, entry_id) DO UPDATE SET
          employee_key=EXCLUDED.employee_key, leave_type=EXCLUDED.leave_type,
          entry_kind=EXCLUDED.entry_kind, days=EXCLUDED.days,
          effective_date=EXCLUDED.effective_date, request_status=EXCLUDED.request_status,
          department=EXCLUDED.department, confidential=EXCLUDED.confidential,
          source_authority=EXCLUDED.source_authority, updated_at=now()
        RETURNING *
        """,
        (
            str(uuid.uuid4()), company, entry_id, employee_key, leave_type,
            str(entry_kind).lower(), Decimal(str(days)), _as_date(effective_date),
            str(request_status).lower() if request_status else None, department,
            bool(confidential), source_authority,
        ),
    )
    row = dict(cur.fetchone())
    _audit(cur, company_code=company, action="leave_ledger_upserted", actor_phone=actor_phone,
           reason=reason, subject_type="leave_entry", subject_id=entry_id)
    return {"ok": True, "leave_entry": row}


def upsert_leave_entitlement(
    cur: Any, *, company_code: str, actor_phone: str, employee_key: str,
    leave_type: str, period_year: int, entitlement_days: float, reason: str,
) -> dict[str, Any]:
    ent, error = _require_write(cur, company_code, reason)
    if error:
        return error
    company = ent["company_code"]
    cur.execute(
        """
        INSERT INTO hr_intelligence_leave_entitlements (
          row_id, company_code, employee_key, leave_type, period_year, entitlement_days
        ) VALUES (%s,%s,%s,%s,%s,%s)
        ON CONFLICT (company_code, employee_key, leave_type, period_year) DO UPDATE SET
          entitlement_days=EXCLUDED.entitlement_days, updated_at=now()
        RETURNING *
        """,
        (str(uuid.uuid4()), company, employee_key, leave_type, int(period_year), Decimal(str(entitlement_days))),
    )
    row = dict(cur.fetchone())
    _audit(cur, company_code=company, action="leave_entitlement_upserted", actor_phone=actor_phone,
           reason=reason, subject_type="leave_entitlement",
           subject_id=f"{employee_key}:{leave_type}:{period_year}")
    return {"ok": True, "leave_entitlement": row}


def upsert_shift_assignment(
    cur: Any, *, company_code: str, actor_phone: str, assignment_key: str,
    employee_key: str, work_date: date | str, scheduled_hours: float,
    status: str, reason: str, department: str | None = None,
    manager_employee_key: str | None = None,
    source_authority: str = "shift_assignment",
) -> dict[str, Any]:
    ent, error = _require_write(cur, company_code, reason)
    if error:
        return error
    company = ent["company_code"]
    cur.execute(
        """
        INSERT INTO hr_intelligence_shift_assignments (
          row_id, company_code, assignment_key, employee_key, work_date,
          scheduled_hours, status, department, manager_employee_key, source_authority
        ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
        ON CONFLICT (company_code, assignment_key) DO UPDATE SET
          employee_key=EXCLUDED.employee_key, work_date=EXCLUDED.work_date,
          scheduled_hours=EXCLUDED.scheduled_hours, status=EXCLUDED.status,
          department=EXCLUDED.department, manager_employee_key=EXCLUDED.manager_employee_key,
          source_authority=EXCLUDED.source_authority, updated_at=now()
        RETURNING *
        """,
        (
            str(uuid.uuid4()), company, assignment_key, employee_key, _as_date(work_date),
            Decimal(str(scheduled_hours)), str(status).lower(), department,
            manager_employee_key, source_authority,
        ),
    )
    row = dict(cur.fetchone())
    _audit(cur, company_code=company, action="shift_assignment_upserted", actor_phone=actor_phone,
           reason=reason, subject_type="shift_assignment", subject_id=assignment_key)
    return {"ok": True, "shift_assignment": row}


def upsert_ot_request(
    cur: Any, *, company_code: str, actor_phone: str, ot_key: str,
    employee_key: str, status: str, hours: float, ot_date: date | str,
    reason: str, paid_in_payroll: bool = False, department: str | None = None,
    manager_employee_key: str | None = None,
    source_authority: str = "overtime_request",
) -> dict[str, Any]:
    ent, error = _require_write(cur, company_code, reason)
    if error:
        return error
    company = ent["company_code"]
    st = str(status).lower()
    if st not in {"approved", "rejected", "cancelled", "payroll_exported"}:
        return {"ok": False, "error": "invalid_ot_status"}
    cur.execute(
        """
        INSERT INTO hr_intelligence_ot_requests (
          row_id, company_code, ot_key, employee_key, status, hours, ot_date,
          paid_in_payroll, department, manager_employee_key, source_authority
        ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
        ON CONFLICT (company_code, ot_key) DO UPDATE SET
          employee_key=EXCLUDED.employee_key, status=EXCLUDED.status,
          hours=EXCLUDED.hours, ot_date=EXCLUDED.ot_date,
          paid_in_payroll=EXCLUDED.paid_in_payroll, department=EXCLUDED.department,
          manager_employee_key=EXCLUDED.manager_employee_key,
          source_authority=EXCLUDED.source_authority, updated_at=now()
        RETURNING *
        """,
        (
            str(uuid.uuid4()), company, ot_key, employee_key, st, Decimal(str(hours)),
            _as_date(ot_date), bool(paid_in_payroll), department,
            manager_employee_key, source_authority,
        ),
    )
    row = dict(cur.fetchone())
    _audit(cur, company_code=company, action="ot_request_upserted", actor_phone=actor_phone,
           reason=reason, subject_type="ot_request", subject_id=ot_key,
           payload={"status": st, "paid_in_payroll_claim": bool(paid_in_payroll)})
    return {"ok": True, "ot_request": row}


def upsert_payroll_period(
    cur: Any, *, company_code: str, actor_phone: str, period_key: str,
    period_start: date | str, period_end: date | str,
    authoritative_finalized: bool, money_authority: str | None, status: str,
    reason: str, currency: str = "KWD", totals_gross: float | None = None,
    totals_net: float | None = None, sealed_at: datetime | None = None,
    watermark: str | None = None,
) -> dict[str, Any]:
    ent, error = _require_write(cur, company_code, reason)
    if error:
        return error
    company = ent["company_code"]
    cur.execute(
        """
        INSERT INTO hr_intelligence_payroll_periods (
          row_id, company_code, period_key, period_start, period_end,
          authoritative_finalized, money_authority, status, currency,
          totals_gross, totals_net, sealed_at, watermark
        ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
        ON CONFLICT (company_code, period_key) DO UPDATE SET
          period_start=EXCLUDED.period_start, period_end=EXCLUDED.period_end,
          authoritative_finalized=EXCLUDED.authoritative_finalized,
          money_authority=EXCLUDED.money_authority, status=EXCLUDED.status,
          currency=EXCLUDED.currency, totals_gross=EXCLUDED.totals_gross,
          totals_net=EXCLUDED.totals_net, sealed_at=EXCLUDED.sealed_at,
          watermark=EXCLUDED.watermark, updated_at=now()
        RETURNING *
        """,
        (
            str(uuid.uuid4()), company, period_key, _as_date(period_start), _as_date(period_end),
            bool(authoritative_finalized), money_authority, str(status).lower(),
            str(currency or "KWD").upper(),
            Decimal(str(totals_gross)) if totals_gross is not None else None,
            Decimal(str(totals_net)) if totals_net is not None else None,
            sealed_at, watermark,
        ),
    )
    row = dict(cur.fetchone())
    _audit(cur, company_code=company, action="payroll_period_upserted", actor_phone=actor_phone,
           reason=reason, subject_type="payroll_period", subject_id=period_key,
           payload={
               "authoritative_finalized": bool(authoritative_finalized),
               "money_authority": money_authority, "currency": row["currency"],
           })
    return {"ok": True, "payroll_period": row}


def upsert_payroll_line(
    cur: Any, *, company_code: str, actor_phone: str, period_key: str,
    line_key: str, employee_key: str, component_key: str,
    component_class: str, amount: float, reason: str, currency: str = "KWD",
    department: str | None = None, display_label: str | None = None,
) -> dict[str, Any]:
    ent, error = _require_write(cur, company_code, reason)
    if error:
        return error
    company = ent["company_code"]
    if not str(component_key or "").strip():
        return {"ok": False, "error": "stable_component_key_required"}
    cur.execute(
        """
        INSERT INTO hr_intelligence_payroll_lines (
          row_id, company_code, period_key, line_key, employee_key,
          component_key, component_class, display_label, amount, currency, department
        ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
        ON CONFLICT (company_code, period_key, line_key) DO UPDATE SET
          employee_key=EXCLUDED.employee_key, component_key=EXCLUDED.component_key,
          component_class=EXCLUDED.component_class, display_label=EXCLUDED.display_label,
          amount=EXCLUDED.amount, currency=EXCLUDED.currency,
          department=EXCLUDED.department, updated_at=now()
        RETURNING *
        """,
        (
            str(uuid.uuid4()), company, period_key, line_key, employee_key,
            str(component_key), str(component_class).lower(), display_label,
            Decimal(str(amount)), str(currency or "KWD").upper(), department,
        ),
    )
    row = dict(cur.fetchone())
    _audit(cur, company_code=company, action="payroll_line_upserted", actor_phone=actor_phone,
           reason=reason, subject_type="payroll_line",
           subject_id=f"{period_key}:{line_key}",
           payload={"component_key": component_key, "display_label_not_identity": True})
    return {"ok": True, "payroll_line": row}


def upsert_settlement(
    cur: Any, *, company_code: str, actor_phone: str, settlement_key: str,
    status: str, amount: float, reason: str, currency: str = "KWD",
    paid: bool = False, effective_date: date | str | None = None,
    employee_key: str | None = None, payment_authority_proven: bool = False,
) -> dict[str, Any]:
    ent, error = _require_write(cur, company_code, reason)
    if error:
        return error
    company = ent["company_code"]
    st = str(status).lower()
    if st not in {"calculated", "approved", "finalized"}:
        return {"ok": False, "error": "invalid_settlement_status"}
    proven_paid = bool(paid) and bool(payment_authority_proven)
    cur.execute(
        """
        INSERT INTO hr_intelligence_settlements (
          row_id, company_code, settlement_key, status, amount, currency,
          paid, effective_date, employee_key
        ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
        ON CONFLICT (company_code, settlement_key) DO UPDATE SET
          status=EXCLUDED.status, amount=EXCLUDED.amount, currency=EXCLUDED.currency,
          paid=EXCLUDED.paid, effective_date=EXCLUDED.effective_date,
          employee_key=EXCLUDED.employee_key, updated_at=now()
        RETURNING *
        """,
        (
            str(uuid.uuid4()), company, settlement_key, st, Decimal(str(amount)),
            str(currency or "KWD").upper(), proven_paid, _as_date(effective_date) or date.today(),
            employee_key,
        ),
    )
    row = dict(cur.fetchone())
    _audit(cur, company_code=company, action="settlement_upserted", actor_phone=actor_phone,
           reason=reason, subject_type="settlement", subject_id=settlement_key,
           payload={
               "status": st, "paid": bool(row["paid"]),
               "payment_authority_proven": bool(payment_authority_proven),
               "finalized_does_not_imply_paid": True,
           })
    return {"ok": True, "settlement": row, "finalized_does_not_imply_paid": True}


def upsert_payment_file(
    cur: Any, *, company_code: str, actor_phone: str, file_key: str,
    status: str, reason: str, effective_date: date | str | None = None,
) -> dict[str, Any]:
    ent, error = _require_write(cur, company_code, reason)
    if error:
        return error
    company = ent["company_code"]
    st = str(status).lower()
    if st not in {"generated", "acknowledged"}:
        return {"ok": False, "error": "invalid_payment_file_status"}
    cur.execute(
        """
        INSERT INTO hr_intelligence_payment_files
          (row_id, company_code, file_key, status, effective_date)
        VALUES (%s,%s,%s,%s,%s)
        ON CONFLICT (company_code, file_key) DO UPDATE SET
          status=EXCLUDED.status, effective_date=EXCLUDED.effective_date, updated_at=now()
        RETURNING *
        """,
        (str(uuid.uuid4()), company, file_key, st, _as_date(effective_date) or date.today()),
    )
    row = dict(cur.fetchone())
    _audit(cur, company_code=company, action="payment_file_upserted", actor_phone=actor_phone,
           reason=reason, subject_type="payment_file", subject_id=file_key,
           payload={"status": st, "acknowledged_does_not_imply_paid": True})
    return {"ok": True, "payment_file": row, "acknowledged_does_not_imply_paid": True}


def _handler_gate(cur: Any, company_code: str) -> dict[str, Any] | None:
    ent = _entitled(cur, company_code)
    if ent.get("ok"):
        return None
    return {
        "status": "unavailable", "value": None, "population_ids": [],
        "explain": {"gate": ent.get("error"), "module_off": True},
    }


def _begin(cur: Any, company: str, module_flag: str, module_name: str) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    gated = _handler_gate(cur, company)
    if gated:
        return None, gated
    cur.execute("SELECT * FROM hr_intelligence_c4_company_settings WHERE company_code=%s", (company,))
    settings = dict(cur.fetchone())
    if not bool(settings.get(module_flag)):
        return settings, {
            "status": "unavailable", "value": None, "population_ids": [],
            "explain": {
                "module_off": True,
                "module": module_name,
                "message_en": f"{module_name} module disabled — unavailable, not zero.",
                "message_ar": f"وحدة {module_name} معطّلة — غير متاح وليس صفراً.",
            },
        }
    return settings, None


def _manager_scope(row: dict[str, Any], filters: dict[str, Any], actor_role: str) -> bool:
    if actor_role != "manager":
        return True
    allowed = set(filters.get("manager_scope_keys") or [])
    if not allowed and filters.get("manager_employee_key"):
        allowed.add(str(filters["manager_employee_key"]))
    return bool(allowed) and str(row.get("manager_employee_key") or "") in allowed


def _rows(cur: Any, table: str, company: str) -> list[dict[str, Any]]:
    allowed = {
        "hr_intelligence_attendance_days", "hr_intelligence_leave_ledger_facts",
        "hr_intelligence_leave_entitlements", "hr_intelligence_shift_assignments",
        "hr_intelligence_ot_requests", "hr_intelligence_payroll_periods",
        "hr_intelligence_payroll_lines", "hr_intelligence_settlements",
        "hr_intelligence_payment_files",
    }
    if table not in allowed:
        raise ValueError("unsupported projection table")
    cur.execute(f"SELECT * FROM {table} WHERE company_code=%s", (company,))
    return [dict(r) for r in (cur.fetchall() or [])]


def _attendance(cur: Any, company: str, filters: dict[str, Any], actor_role: str,
                start: date, end: date) -> list[dict[str, Any]]:
    return [
        r for r in _rows(cur, "hr_intelligence_attendance_days", company)
        if not bool(r.get("raw_punch_only"))
        and start <= _as_date(r.get("work_date")) <= end
        and _manager_scope(r, filters, actor_role)
        and (not filters.get("department") or r.get("department") == filters["department"])
    ]


def _payroll_forbidden(actor_role: str, filters: dict[str, Any]) -> dict[str, Any] | None:
    if actor_role == "manager" and not bool(filters.get("has_payroll_permission")):
        return {
            "status": "forbidden", "value": None, "population_ids": [],
            "explain": {
                "permission": "payroll",
                "message_en": "Payroll permission required.",
                "message_ar": "يلزم تصريح الرواتب.",
            },
        }
    return None


def _sealed_periods(cur: Any, company: str, start: date, end: date) -> list[dict[str, Any]]:
    rows = [
        p for p in _rows(cur, "hr_intelligence_payroll_periods", company)
        if bool(p.get("authoritative_finalized"))
        and str(p.get("money_authority") or "").lower() == "wathefni"
        and _as_date(p.get("period_end")) <= end
        and _as_date(p.get("period_end")) >= start
    ]
    return sorted(rows, key=lambda p: (_as_date(p["period_end"]), str(p["period_key"])))


def _unsealed_payroll(currency: str) -> dict[str, Any]:
    return {
        "status": "unavailable", "value": None, "population_ids": [],
        "explain": {
            "currency": currency, "fx_conversion": False,
            "requires_authoritative_finalized": True,
            "requires_money_authority": "wathefni",
            "message_en": "No sealed Wathefni-authoritative payroll period.",
            "message_ar": "لا توجد فترة رواتب نهائية مختومة ومعتمدة من وظفني.",
        },
    }


def _cost_for_period(settings: dict[str, Any], period: dict[str, Any],
                     lines: list[dict[str, Any]]) -> float:
    basis = str(settings.get("workforce_cost_basis") or "gross")
    if basis == "net":
        return _number(period.get("totals_net"))
    if basis == "included_components":
        classes = settings.get("included_component_classes") or []
        if isinstance(classes, str):
            classes = json.loads(classes)
        return sum(_number(line["amount"]) for line in lines if line.get("component_class") in set(classes))
    return _number(period.get("totals_gross"))


def _handler_dispatch(
    cur: Any, *, company_code: str, settings: dict[str, Any],
    formula_contract: dict[str, Any], publication: dict[str, Any],
    filters: dict[str, Any], time_window: dict[str, Any],
    actor_phone: str, actor_role: str,
) -> dict[str, Any]:
    _ = (settings, publication, actor_phone)
    kind = str(formula_contract.get("kind") or "")
    start, end = _parse_window(time_window)
    attendance_kinds = {
        "time_attendance_rate", "time_absenteeism_rate", "time_lateness_employees",
        "time_lateness_occurrences", "time_lateness_minutes",
        "time_early_leave_occurrences", "time_missing_punches",
    }
    module = (
        ("attendance_module_enabled", "attendance") if kind in attendance_kinds else
        ("leave_module_enabled", "leave") if kind in {"leave_utilization_rate", "leave_taken_days"} else
        ("shifts_module_enabled", "shifts") if kind == "shifts_scheduled_hours" else
        ("ot_module_enabled", "overtime") if kind in {"ot_approved", "ot_payroll_exported", "ot_paid"} else
        ("payroll_module_enabled", "payroll")
    )
    c4s, unavailable = _begin(cur, company_code, *module)
    if unavailable:
        return unavailable
    assert c4s is not None

    if kind in attendance_kinds:
        days = _attendance(cur, company_code, filters, actor_role, start, end)
        expected = [r for r in days if bool(r.get("expected_work"))]
        if kind in {"time_attendance_rate", "time_absenteeism_rate"} and not expected:
            status = "unavailable" if not bool(c4s.get("attendance_rate_expected_work_required")) else "insufficient_data"
            return {
                "status": status, "value": None, "population_ids": [],
                "numerator_value": None, "denominator_value": 0.0,
                "explain": {
                    "expected_work_days_present": False,
                    "headcount_denominator_forbidden": True,
                    "raw_punch_rows_ignored": True,
                    "message_en": "Expected-work days are required; no denominator was invented.",
                    "message_ar": "أيام العمل المتوقعة مطلوبة؛ لم يتم اختراع مقام.",
                },
            }
        if kind == "time_attendance_rate":
            present = [r for r in expected if r.get("status") in {"present", "late", "completed"}]
            return {
                "status": "ok", "value": len(present) / len(expected) * 100.0,
                "unit": "percent", "numerator_value": float(len(present)),
                "denominator_value": float(len(expected)),
                "population_ids": [f"{r['employee_key']}:{r['work_date']}" for r in expected],
                "explain": {"raw_punch_rows_ignored": True, "denominator": "expected_work_days"},
            }
        if kind == "time_absenteeism_rate":
            absent = [r for r in expected if r.get("status") == "absent"]
            return {
                "status": "ok", "value": len(absent) / len(expected) * 100.0,
                "unit": "percent", "numerator_value": float(len(absent)),
                "denominator_value": float(len(expected)),
                "population_ids": [f"{r['employee_key']}:{r['work_date']}" for r in expected],
                "explain": {
                    "numerator_status": "absent", "approved_leave_excluded": True,
                    "numerator_ids": [f"{r['employee_key']}:{r['work_date']}" for r in absent],
                },
            }
        late = [r for r in days if _number(r.get("late_minutes")) > 0 or r.get("status") == "late"]
        if kind == "time_lateness_employees":
            ids = sorted({str(r["employee_key"]) for r in late})
            return {"status": "ok", "value": float(len(ids)), "population_ids": ids,
                    "explain": {"measure": "distinct_employees"}}
        if kind == "time_lateness_occurrences":
            ids = [f"{r['employee_key']}:{r['work_date']}" for r in late]
            return {"status": "ok", "value": float(len(ids)), "population_ids": ids,
                    "explain": {"measure": "occurrences"}}
        if kind == "time_lateness_minutes":
            ids = [f"{r['employee_key']}:{r['work_date']}" for r in late]
            return {"status": "ok", "value": sum(_number(r.get("late_minutes")) for r in late),
                    "unit": "minutes", "population_ids": ids, "explain": {"measure": "minutes"}}
        if kind == "time_early_leave_occurrences":
            early = [r for r in days if _number(r.get("early_leave_minutes")) > 0]
            return {"status": "ok", "value": float(len(early)),
                    "population_ids": [f"{r['employee_key']}:{r['work_date']}" for r in early],
                    "explain": {"positive_early_leave_minutes_required": True}}
        missing = [
            r for r in days if r.get("status") == "incomplete"
            or "missing" in str(r.get("exception_state") or "").lower()
        ]
        return {"status": "ok", "value": float(len(missing)),
                "population_ids": [f"{r['employee_key']}:{r['work_date']}" for r in missing],
                "explain": {"raw_punch_rows_ignored": True}}

    if kind in {"leave_utilization_rate", "leave_taken_days"}:
        entries = [
            r for r in _rows(cur, "hr_intelligence_leave_ledger_facts", company_code)
            if start <= _as_date(r["effective_date"]) <= end
            and str(r.get("request_status") or "").lower() not in {"cancelled", "rejected"}
            and (not filters.get("leave_type") or r.get("leave_type") == filters["leave_type"])
            and (not filters.get("department") or r.get("department") == filters["department"])
        ]
        taken = 0.0
        employees: set[str] = set()
        for row in entries:
            k = str(row.get("entry_kind") or "").lower()
            if k == "consume":
                taken += abs(_number(row["days"]))
                employees.add(str(row["employee_key"]))
            elif k == "reversal":
                taken -= abs(_number(row["days"]))
                employees.add(str(row["employee_key"]))
        taken = max(0.0, taken)
        if kind == "leave_taken_days":
            return {"status": "ok", "value": taken, "unit": "days",
                    "population_ids": sorted(employees),
                    "explain": {"consume_minus_reversals": True, "cancelled_rejected_excluded": True}}
        years = set(range(start.year, end.year + 1))
        entitlements = [
            r for r in _rows(cur, "hr_intelligence_leave_entitlements", company_code)
            if int(r["period_year"]) in years
            and (not filters.get("leave_type") or r.get("leave_type") == filters["leave_type"])
        ]
        denominator = sum(_number(r["entitlement_days"]) for r in entitlements)
        ids = sorted({str(r["employee_key"]) for r in entitlements})
        if denominator == 0:
            return {
                "status": "not_applicable", "value": None,
                "numerator_value": taken, "denominator_value": 0.0,
                "population_ids": ids,
                "explain": {"zero_entitlement": True, "cancelled_rejected_excluded": True},
            }
        return {
            "status": "ok", "value": taken / denominator * 100.0, "unit": "percent",
            "numerator_value": taken, "denominator_value": denominator,
            "population_ids": ids,
            "explain": {"formula": "consume_minus_reversals_over_entitlement", "cancelled_rejected_excluded": True},
        }

    if kind == "shifts_scheduled_hours":
        rows = [
            r for r in _rows(cur, "hr_intelligence_shift_assignments", company_code)
            if start <= _as_date(r["work_date"]) <= end
            and str(r.get("status") or "") not in {"cancelled", "void"}
            and _manager_scope(r, filters, actor_role)
        ]
        return {
            "status": "ok", "value": sum(_number(r["scheduled_hours"]) for r in rows),
            "unit": "hours", "population_ids": [str(r["assignment_key"]) for r in rows],
            "explain": {"module_optional": True},
        }

    if kind in {"ot_approved", "ot_payroll_exported", "ot_paid"}:
        rows = [
            r for r in _rows(cur, "hr_intelligence_ot_requests", company_code)
            if start <= _as_date(r["ot_date"]) <= end and _manager_scope(r, filters, actor_role)
        ]
        if kind == "ot_approved":
            selected = [r for r in rows if r.get("status") == "approved"]
        elif kind == "ot_payroll_exported":
            selected = [r for r in rows if r.get("status") == "payroll_exported"]
        else:
            sealed = _sealed_periods(cur, company_code, start, end)
            sealed_keys = {str(p["period_key"]) for p in sealed}
            paid_employees = {
                str(line["employee_key"])
                for line in _rows(cur, "hr_intelligence_payroll_lines", company_code)
                if str(line["period_key"]) in sealed_keys
                and str(line.get("component_class") or "").lower() == "ot"
            }
            selected = [
                r for r in rows
                if bool(r.get("paid_in_payroll"))
                and str(r["employee_key"]) in paid_employees
            ]
        return {
            "status": "ok", "value": float(len(selected)),
            "population_ids": [str(r["ot_key"]) for r in selected],
            "explain": {
                "state": kind, "approved_not_exported_or_paid": True,
                "paid_requires_sealed_payroll_component_proof": kind == "ot_paid",
            },
        }

    forbidden = _payroll_forbidden(actor_role, filters)
    if forbidden:
        return forbidden
    currency = str(c4s.get("currency") or "KWD").upper()

    if kind in {"payroll_workforce_cost", "payroll_movement", "payroll_component_movement"}:
        periods = _sealed_periods(cur, company_code, start, end)
        if not periods:
            return _unsealed_payroll(currency)
        if kind in {"payroll_movement", "payroll_component_movement"} and len(periods) < 2:
            out = _unsealed_payroll(currency)
            out["status"] = "insufficient_data"
            out["explain"]["requires_two_sealed_periods"] = True
            return out
        lines = _rows(cur, "hr_intelligence_payroll_lines", company_code)
        by_period = {
            p["period_key"]: [line for line in lines if line["period_key"] == p["period_key"]]
            for p in periods
        }
        if kind == "payroll_workforce_cost":
            period = periods[-1]
            period_lines = by_period[period["period_key"]]
            value = _cost_for_period(c4s, period, period_lines)
            return {
                "status": "ok", "value": value, "unit": currency,
                "population_ids": sorted({str(r["employee_key"]) for r in period_lines}),
                "explain": {
                    "currency": currency, "fx_conversion": False, "sealed": True,
                    "money_authority": "wathefni", "period_key": period["period_key"],
                    "workforce_cost_basis": c4s.get("workforce_cost_basis"),
                },
            }
        prior, current = periods[-2], periods[-1]
        prior_lines, current_lines = by_period[prior["period_key"]], by_period[current["period_key"]]
        if kind == "payroll_movement":
            prior_value = _cost_for_period(c4s, prior, prior_lines)
            current_value = _cost_for_period(c4s, current, current_lines)
            ids = sorted({str(r["employee_key"]) for r in prior_lines + current_lines})
            return {
                "status": "ok", "value": current_value - prior_value, "unit": currency,
                "population_ids": ids,
                "explain": {
                    "currency": currency, "fx_conversion": False, "sealed_periods_only": True,
                    "prior_period_key": prior["period_key"], "current_period_key": current["period_key"],
                    "prior_value": prior_value, "current_value": current_value,
                },
            }
        component_filter = filters.get("component_key")
        def component_totals(items: list[dict[str, Any]]) -> dict[str, float]:
            totals: dict[str, float] = {}
            for line in items:
                key = str(line["component_key"])
                if component_filter and key != component_filter:
                    continue
                totals[key] = totals.get(key, 0.0) + _number(line["amount"])
            return totals
        before, after = component_totals(prior_lines), component_totals(current_lines)
        keys = sorted(set(before) | set(after))
        movement = {key: after.get(key, 0.0) - before.get(key, 0.0) for key in keys}
        relevant = [
            line for line in prior_lines + current_lines
            if not component_filter or line["component_key"] == component_filter
        ]
        return {
            "status": "ok", "value": sum(movement.values()), "unit": currency,
            "population_ids": sorted({str(r["employee_key"]) for r in relevant}),
            "explain": {
                "currency": currency, "fx_conversion": False, "sealed_periods_only": True,
                "stable_grouping_identity": "component_key", "display_label_drives_grouping": False,
                "component_movement": movement, "prior_components": before,
                "current_components": after, "component_filter": component_filter,
            },
        }

    if kind == "settlement_finalized":
        rows = [
            r for r in _rows(cur, "hr_intelligence_settlements", company_code)
            if start <= _as_date(r["effective_date"]) <= end and r.get("status") == "finalized"
        ]
        return {
            "status": "ok", "value": float(len(rows)),
            "population_ids": [str(r["settlement_key"]) for r in rows],
            "explain": {
                "currency": currency, "fx_conversion": False,
                "finalized_does_not_mean_paid": True,
                "paid_count": sum(1 for r in rows if bool(r.get("paid"))),
            },
        }

    rows = [
        r for r in _rows(cur, "hr_intelligence_payment_files", company_code)
        if start <= _as_date(r["effective_date"]) <= end and r.get("status") == "acknowledged"
    ]
    return {
        "status": "ok", "value": float(len(rows)),
        "population_ids": [str(r["file_key"]) for r in rows],
        "explain": {
            "currency": currency, "fx_conversion": False,
            "acknowledged_does_not_mean_paid": True,
        },
    }


def _register_handlers() -> None:
    for formula_kind in FORMULA_KINDS.values():
        c1.register_formula_handler(formula_kind, _handler_dispatch)


def seed_time_pay_definitions(cur: Any, *, actor_phone: str) -> dict[str, Any]:
    c1.ensure_hr_intelligence_registry_c1_schema(cur)
    created: list[str] = []

    def ensure(key: str, *, name_en: str, name_ar: str, description_en: str,
               description_ar: str, unit: str, time_semantics: str,
               permission_class: str, numerator: dict[str, Any] | None = None,
               denominator: dict[str, Any] | None = None,
               dimensions: list[str] | None = None) -> None:
        kind = FORMULA_KINDS[key]
        cur.execute(
            """
            SELECT kpi_definition_id, status, formula_contract
              FROM hr_kpi_definitions WHERE semantic_key=%s
             ORDER BY effective_version DESC LIMIT 1
            """,
            (key,),
        )
        existing = cur.fetchone()
        kwargs = {
            "name_en": name_en, "name_ar": name_ar,
            "description_en": description_en, "description_ar": description_ar,
            "business_meaning": description_en,
            "formula_contract": {
                "kind": kind,
                "sensitive_aggregate": permission_class == "payroll_money",
                "currency": "KWD" if key.startswith("payroll.") else None,
                "fx_conversion": False if key.startswith("payroll.") else None,
            },
            "unit": unit, "time_semantics": time_semantics,
            "permission_class": permission_class, "status": "published",
            "numerator": numerator, "denominator": denominator,
            "supported_dimensions": dimensions or ["department"],
            "canonical_source_facts": [key.rsplit(".", 1)[0]],
            "required_domain_authority": ["wathefni_sealed_payroll"] if permission_class == "payroll_money" else [],
            "owner": "wave5_c4", "reason": f"c4 seed {key}",
        }
        if existing:
            ex = dict(existing)
            fc = ex.get("formula_contract")
            if isinstance(fc, str):
                fc = json.loads(fc)
            if not fc or fc.get("kind") != kind:
                out = c1.version_kpi_definition(
                    cur, actor_phone=actor_phone, semantic_key=key,
                    reason=f"c4 activate {key}", updates=kwargs,
                )
                if out.get("ok"):
                    created.append(key)
                    c1.publish_kpi_definition(
                        cur, actor_phone=actor_phone,
                        kpi_definition_id=str(out["definition"]["kpi_definition_id"]),
                        reason="c4 publish refreshed definition",
                    )
            elif ex["status"] != "published":
                c1.publish_kpi_definition(
                    cur, actor_phone=actor_phone,
                    kpi_definition_id=str(ex["kpi_definition_id"]), reason="c4 publish existing",
                )
            return
        out = c1.create_kpi_definition(
            cur, actor_phone=actor_phone, semantic_key=key, **kwargs
        )
        if out.get("ok"):
            created.append(key)
            c1.publish_kpi_definition(
                cur, actor_phone=actor_phone,
                kpi_definition_id=str(out["definition"]["kpi_definition_id"]),
                reason="c4 publish definition",
            )

    definitions = [
        (ATTENDANCE_RATE_KEY, "Attendance rate", "معدل الحضور",
         "Present/late/completed expected-work days divided by expected-work days; no headcount denominator.",
         "أيام الحضور المتوقعة مقسومة على أيام العمل المتوقعة؛ لا يُستخدم عدد الموظفين.", "percent", "rate_over_window", "time_leave"),
        (ABSENTEEISM_RATE_KEY, "Unauthorized absenteeism rate", "معدل الغياب غير المصرح",
         "Unauthorized absent expected-work days only; approved leave is excluded.",
         "أيام الغياب غير المصرح فقط؛ الإجازة المعتمدة مستبعدة.", "percent", "rate_over_window", "time_leave"),
        (LATENESS_EMPLOYEES_KEY, "Employees with lateness", "الموظفون المتأخرون",
         "Distinct employees with lateness in the period.", "عدد الموظفين المميزين الذين تأخروا في الفترة.", "count", "event_count", "time_leave"),
        (LATENESS_OCCURRENCES_KEY, "Lateness occurrences", "حالات التأخر",
         "Attendance-day lateness occurrences.", "حالات التأخر على مستوى يوم الحضور.", "count", "event_count", "time_leave"),
        (LATENESS_MINUTES_KEY, "Lateness minutes", "دقائق التأخر",
         "Sum of authoritative lateness minutes.", "مجموع دقائق التأخر المعتمدة.", "minutes", "period_sum", "time_leave"),
        (EARLY_LEAVE_OCCURRENCES_KEY, "Early-leave occurrences", "حالات المغادرة المبكرة",
         "Attendance days with positive early-leave minutes.", "أيام الحضور ذات دقائق مغادرة مبكرة موجبة.", "count", "event_count", "time_leave"),
        (MISSING_PUNCHES_KEY, "Missing punches", "البصمات المفقودة",
         "Authoritative incomplete or missing-punch attendance days.", "أيام الحضور غير المكتملة أو ذات بصمة مفقودة.", "count", "event_count", "time_leave"),
        (LEAVE_UTILIZATION_RATE_KEY, "Leave utilization rate", "معدل استخدام الإجازة",
         "Consumed less reversals divided by entitlement; rejected/cancelled excluded.",
         "المستهلك ناقص العكس مقسوماً على الاستحقاق؛ المرفوض والملغى مستبعدان.", "percent", "rate_over_window", "time_leave"),
        (LEAVE_TAKEN_DAYS_KEY, "Leave taken days", "أيام الإجازة المأخوذة",
         "Consumed leave less reversals.", "الإجازة المستهلكة ناقص عمليات العكس.", "days", "period_sum", "time_leave"),
        (SHIFTS_SCHEDULED_HOURS_KEY, "Scheduled shift hours", "ساعات المناوبات المجدولة",
         "Scheduled hours from the optional shifts module.", "الساعات المجدولة من وحدة المناوبات الاختيارية.", "hours", "period_sum", "time_leave"),
        (OT_APPROVED_KEY, "Approved overtime", "العمل الإضافي المعتمد",
         "Approved OT requests, distinct from export and payment.", "طلبات العمل الإضافي المعتمدة، منفصلة عن التصدير والدفع.", "count", "event_count", "time_leave"),
        (OT_PAYROLL_EXPORTED_KEY, "Overtime exported to payroll", "العمل الإضافي المصدر للرواتب",
         "OT requests explicitly exported to payroll.", "طلبات العمل الإضافي المصدرة صراحة إلى الرواتب.", "count", "event_count", "time_leave"),
        (OT_PAID_KEY, "Paid overtime", "العمل الإضافي المدفوع",
         "OT with sealed payroll payment-component proof.", "عمل إضافي مع إثبات مكون دفع رواتب مختوم.", "count", "event_count", "time_leave"),
        (PAYROLL_WORKFORCE_COST_KEY, "Payroll workforce cost", "تكلفة القوى العاملة بالرواتب",
         "Configured cost basis from the latest sealed Wathefni payroll period; KWD, no FX.",
         "أساس التكلفة المحدد من أحدث فترة رواتب مختومة من وظفني؛ د.ك بلا صرف.", "KWD", "period_sum", "payroll_money"),
        (PAYROLL_MOVEMENT_KEY, "Payroll movement", "حركة الرواتب",
         "Period-over-period workforce cost movement across two sealed periods.",
         "حركة تكلفة القوى العاملة بين فترتي رواتب مختومتين.", "KWD", "period_sum", "payroll_money"),
        (PAYROLL_COMPONENT_MOVEMENT_KEY, "Payroll component movement", "حركة مكونات الرواتب",
         "Period movement grouped by stable component_key, never display label.",
         "حركة الفترة مجمعة بمفتاح المكون الثابت وليس اسم العرض.", "KWD", "period_sum", "payroll_money"),
        (SETTLEMENT_FINALIZED_KEY, "Finalized settlements", "التسويات النهائية",
         "Count of finalized settlements; finalized does not mean paid.",
         "عدد التسويات النهائية؛ النهائي لا يعني المدفوع.", "count", "event_count", "workforce_general"),
        (PAYMENT_ACK_KEY, "Acknowledged payment files", "ملفات الدفع المُقر بها",
         "Count of acknowledged payment files; acknowledgment does not mean paid.",
         "عدد ملفات الدفع المُقر بها؛ الإقرار لا يعني الدفع.", "count", "event_count", "workforce_general"),
    ]
    for key, en, ar, desc_en, desc_ar, unit, semantics, permission in definitions:
        ensure(
            key, name_en=en, name_ar=ar, description_en=desc_en,
            description_ar=desc_ar, unit=unit, time_semantics=semantics,
            permission_class=permission,
            numerator={"description": desc_en},
            denominator={"description": "governed denominator"} if semantics == "rate_over_window" else None,
            dimensions=["department", "manager", "location", "component_key"],
        )
    _register_handlers()
    return {"ok": True, "created_semantic_keys": created, "semantic_keys": list(ALL_SEMANTIC_KEYS)}


def publish_time_pay_kpis_for_company(
    cur: Any, *, company_code: str, actor_phone: str, reason: str
) -> dict[str, Any]:
    if not str(reason or "").strip():
        return {"ok": False, "error": "audit_reason_required"}
    ent = _entitled(cur, company_code)
    if not ent.get("ok"):
        return ent
    company = ent["company_code"]
    seed_time_pay_definitions(cur, actor_phone=actor_phone)
    published: list[str] = []
    failures: dict[str, Any] = {}
    for key in ALL_SEMANTIC_KEYS:
        result = c1.publish_kpi_for_company(
            cur, company_code=company, actor_phone=actor_phone,
            semantic_key=key, reason=reason,
        )
        if result.get("ok"):
            published.append(key)
        else:
            failures[key] = result.get("error")
    return {
        "ok": len(published) == len(ALL_SEMANTIC_KEYS),
        "published": published, "failures": failures,
        **honesty_payload(company_code=company),
    }


def rebuild_time_pay_facts(
    cur: Any, *, company_code: str, actor_phone: str, reason: str
) -> dict[str, Any]:
    """Idempotently rebuild C1 facts from C4 projections using stable ingest keys."""
    ent, error = _require_write(cur, company_code, reason)
    if error:
        return error
    company = ent["company_code"]
    specs = [
        ("hr_intelligence_attendance_days", "attendance_day", "employee_key", "work_date"),
        ("hr_intelligence_leave_ledger_facts", "leave_ledger", "entry_id", None),
        ("hr_intelligence_leave_entitlements", "leave_entitlement", "employee_key", "leave_type"),
        ("hr_intelligence_shift_assignments", "shift_assignment", "assignment_key", None),
        ("hr_intelligence_ot_requests", "ot_request", "ot_key", None),
        ("hr_intelligence_payroll_periods", "payroll_period", "period_key", None),
        ("hr_intelligence_payroll_lines", "payroll_line", "line_key", "period_key"),
        ("hr_intelligence_settlements", "settlement", "settlement_key", None),
        ("hr_intelligence_payment_files", "payment_file", "file_key", None),
    ]
    counts: dict[str, int] = {}
    idempotent = 0
    for table, fact_type, id_col, second_col in specs:
        rows = _rows(cur, table, company)
        counts[fact_type] = len(rows)
        for row in rows:
            entity_id = str(row[id_col])
            if second_col:
                entity_id = f"{entity_id}:{row[second_col]}"
            measures = {
                key: value for key, value in row.items()
                if key not in {"row_id", "company_code", "updated_at", "department", "location", "manager_employee_key"}
            }
            dimensions = {
                key: row.get(key) for key in ("department", "location", "manager_employee_key", "employee_key")
                if row.get(key) is not None
            }
            out = c1.ingest_fact(
                cur, company_code=company, actor_phone=actor_phone,
                fact_type=fact_type, entity_type=fact_type,
                entity_id=entity_id, source_authority="c4_projection",
                measures=measures, dimensions=dimensions,
                ingest_key=f"c4:{table}:{company}:{entity_id}", reason=reason,
            )
            if out.get("idempotent"):
                idempotent += 1
    _audit(cur, company_code=company, action="facts_rebuilt", actor_phone=actor_phone,
           reason=reason, payload={"counts": counts, "idempotent_updates": idempotent})
    return {"ok": True, "counts": counts, "idempotent_updates": idempotent}


def reconcile_populations(
    cur: Any, *, company_code: str, period_start: date | str,
    period_end: date | str,
) -> dict[str, Any]:
    """Explain why headcount, scheduled, and sealed-payroll populations differ."""
    company = company_code_norm(company_code)
    start, end = _as_date(period_start), _as_date(period_end)
    attendance = {
        str(r["employee_key"]) for r in _rows(cur, "hr_intelligence_attendance_days", company)
        if not r.get("raw_punch_only") and r.get("scheduled")
        and start <= _as_date(r["work_date"]) <= end
    }
    shift = {
        str(r["employee_key"]) for r in _rows(cur, "hr_intelligence_shift_assignments", company)
        if start <= _as_date(r["work_date"]) <= end and r.get("status") not in {"cancelled", "void"}
    }
    payroll_periods = _sealed_periods(cur, company, start, end)
    payroll_keys = {str(p["period_key"]) for p in payroll_periods}
    payroll = {
        str(r["employee_key"]) for r in _rows(cur, "hr_intelligence_payroll_lines", company)
        if str(r["period_key"]) in payroll_keys
    }
    headcount: set[str] = set()
    cur.execute("SELECT to_regclass('hr_intelligence_employment_periods') AS table_name")
    if dict(cur.fetchone()).get("table_name"):
        cur.execute(
            """
            SELECT DISTINCT employee_key FROM hr_intelligence_employment_periods
             WHERE company_code=%s AND superseded_by IS NULL
               AND effective_start <= %s
               AND (effective_end IS NULL OR effective_end >= %s)
            """,
            (company, end, start),
        )
        headcount = {str(dict(r)["employee_key"]) for r in cur.fetchall()}
    scheduled = attendance | shift
    return {
        "ok": True,
        "populations": {
            "headcount": sorted(headcount), "scheduled": sorted(scheduled),
            "payroll": sorted(payroll),
        },
        "counts": {
            "headcount": len(headcount), "scheduled": len(scheduled), "payroll": len(payroll),
        },
        "explain": {
            "headcount_basis": "employment periods active in window when C2 projection exists",
            "scheduled_basis": "authoritative scheduled attendance or shift assignments",
            "payroll_basis": "employees on sealed Wathefni-authoritative payroll lines",
            "differences_expected": [
                "active employees may be unscheduled",
                "scheduled workers may miss the selected finalized payroll",
                "payroll can include settlements or timing adjustments",
            ],
        },
    }


_register_handlers()

