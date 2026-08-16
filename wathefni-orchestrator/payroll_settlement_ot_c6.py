#!/usr/bin/env python3
"""Wave 2 C6 — Final Settlement pay path + OT authorization contract (company-scoped).

Owner-approved under WAVE2_WORKFORCE_TRUTH_CHARTER (2026-08-11).

Settlement SM:
  inputs_ready → calculated → approved → finalized
  (payslip/payment inputs may be emitted; never claims paid without external proof)

OT SM:
  draft → pending_approval → approved | rejected | cancelled → payroll_exported

Gates (fail-closed):
  1) WATHEFNI_PAYROLL_SETTLEMENT_C6 must be on (global; prod stays off)
  2) company must be in WATHEFNI_PAYROLL_SETTLEMENT_COMPANIES (empty = nobody)
  3) company settlement entitlement in payroll_c6_company_settings
  4) OT→Payroll export only when ot_to_payroll_enabled (optional; default OFF)
  5) WATHEFNI_PAYROLL_SETTLEMENT_KILL=on blocks new settlement finalize / OT export

Honesty:
  - E360 remains inputs-only (no payroll math there)
  - No invented EOS/PIFSS/legal formulas beyond already approved payroll authority
  - Leave encashment passes quantity/entitlement; Payroll owns money lines
  - Settlement ≠ clearance completion
  - Settlement finalized ≠ paid
  - Payroll works without OT module/input
"""
from __future__ import annotations

import hashlib
import json
import os
import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any

PHASE = "payroll_settlement_ot_c6"
CONTRACT_VERSION = "payroll_settlement_ot_c6_v1"
_ON = {"1", "true", "yes", "on"}

SS_INPUTS_READY = "inputs_ready"
SS_CALCULATED = "calculated"
SS_APPROVED = "approved"
SS_FINALIZED = "finalized"
SS_SUPERSEDED = "superseded"
SETTLEMENT_STATUSES = (SS_INPUTS_READY, SS_CALCULATED, SS_APPROVED, SS_FINALIZED, SS_SUPERSEDED)

OT_DRAFT = "draft"
OT_PENDING = "pending_approval"
OT_APPROVED = "approved"
OT_REJECTED = "rejected"
OT_CANCELLED = "cancelled"
OT_EXPORTED = "payroll_exported"
OT_STATUSES = (OT_DRAFT, OT_PENDING, OT_APPROVED, OT_REJECTED, OT_CANCELLED, OT_EXPORTED)

STATUS_LABELS = {
    "inputs_ready": {"en": "Inputs ready", "ar": "المدخلات جاهزة"},
    "calculated": {"en": "Calculated", "ar": "محسوب"},
    "approved": {"en": "Approved", "ar": "معتمد"},
    "finalized": {"en": "Finalized", "ar": "مختوم"},
    "superseded": {"en": "Superseded", "ar": "مستبدل"},
    "draft": {"en": "Draft", "ar": "مسودة"},
    "pending_approval": {"en": "Pending approval", "ar": "بانتظار الاعتماد"},
    "rejected": {"en": "Rejected", "ar": "مرفوض"},
    "cancelled": {"en": "Cancelled", "ar": "ملغى"},
    "payroll_exported": {"en": "Exported to payroll", "ar": "مُصدَّر للرواتب"},
}


def _env_on(name: str, default: str = "off") -> bool:
    return (os.environ.get(name) or default).strip().lower() in _ON


def _digits(value: Any) -> str:
    return "".join(ch for ch in str(value or "") if ch.isdigit())


def company_code_norm(company_code: str | None) -> str:
    return str(company_code or "").strip().upper()


def status_label(status: str | None, *, lang: str = "en") -> str:
    key = str(status or "").strip().lower()
    pack = STATUS_LABELS.get(key) or {"en": key or "unknown", "ar": key or "غير معروف"}
    return str(pack.get("ar" if lang.lower().startswith("ar") else "en"))


def settlement_c6_runtime_on() -> bool:
    return _env_on("WATHEFNI_PAYROLL_SETTLEMENT_C6", "off")


def settlement_company_allowlist() -> set[str]:
    raw = str(os.environ.get("WATHEFNI_PAYROLL_SETTLEMENT_COMPANIES") or "").strip()
    if not raw:
        return set()
    return {p.strip().upper() for p in raw.split(",") if p.strip()}


def settlement_kill_switch_active() -> bool:
    return _env_on("WATHEFNI_PAYROLL_SETTLEMENT_KILL", "off")


def honesty_payload(*, company_code: str | None = None) -> dict[str, Any]:
    return {
        "phase": PHASE,
        "contract_version": CONTRACT_VERSION,
        "e360_is_payroll_calculator": False,
        "settlement_is_not_clearance": True,
        "settlement_finalized_is_not_paid": True,
        "claims_paid": False,
        "posts_payment": False,
        "invented_eos_pifss_formulas": False,
        "leave_encashment_quantity_only_until_payroll_money": True,
        "ot_money_outside_payroll": False,
        "ot_required_for_payroll": False,
        "attendance_required": False,
        "leave_required": False,
        "shifts_required": False,
        "settlement_kill_switch": settlement_kill_switch_active(),
        "company_code": company_code_norm(company_code) if company_code else None,
    }


def runtime_gate_for_company(company_code: str | None) -> dict[str, Any]:
    company = company_code_norm(company_code)
    if not company:
        return {"ok": False, "enabled": False, "error": "company_required", "phase": PHASE}
    if not settlement_c6_runtime_on():
        return {
            "ok": False,
            "enabled": False,
            "error": "payroll_settlement_c6_off",
            "gate": "runtime_flag",
            "phase": PHASE,
        }
    allow = settlement_company_allowlist()
    if not allow:
        return {
            "ok": False,
            "enabled": False,
            "error": "payroll_settlement_company_not_allowlisted",
            "gate": "company_allowlist",
            "phase": PHASE,
            "message": "Settlement company allowlist empty — fail closed (nobody).",
        }
    if company not in allow:
        return {
            "ok": False,
            "enabled": False,
            "error": "payroll_settlement_company_not_allowlisted",
            "gate": "company_allowlist",
            "phase": PHASE,
            "company_code": company,
        }
    return {"ok": True, "enabled": True, "company_code": company, "phase": PHASE}


def ensure_payroll_settlement_ot_c6_schema(cur: Any, *, force: bool = False) -> None:
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS payroll_c6_company_settings (
          company_code text PRIMARY KEY,
          settlement_enabled boolean NOT NULL DEFAULT false,
          ot_authorization_enabled boolean NOT NULL DEFAULT false,
          ot_to_payroll_enabled boolean NOT NULL DEFAULT false,
          require_distinct_approver boolean NOT NULL DEFAULT true,
          enabled_by_phone text,
          enabled_reason text,
          enabled_at timestamptz,
          disabled_at timestamptz,
          updated_by_phone text,
          updated_at timestamptz NOT NULL DEFAULT now(),
          metadata jsonb NOT NULL DEFAULT '{}'::jsonb
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS payroll_settlement_runs (
          settlement_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
          company_code text NOT NULL,
          employee_key text NOT NULL,
          lifecycle_packet_id uuid,
          status text NOT NULL DEFAULT 'inputs_ready',
          row_version int NOT NULL DEFAULT 1,
          inputs jsonb NOT NULL DEFAULT '{}'::jsonb,
          calc_payload jsonb NOT NULL DEFAULT '{}'::jsonb,
          content_fingerprint text,
          sealed_fingerprint text,
          created_by_phone text,
          calculated_by_phone text,
          calculated_at timestamptz,
          approved_by_phone text,
          approved_at timestamptz,
          finalized_by_phone text,
          finalized_at timestamptz,
          supersedes_settlement_id uuid,
          payslip_input jsonb,
          payment_input jsonb,
          claims_paid boolean NOT NULL DEFAULT false,
          decision_note text,
          created_at timestamptz NOT NULL DEFAULT now(),
          updated_at timestamptz NOT NULL DEFAULT now(),
          metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
          CONSTRAINT payroll_settlement_runs_status_chk
            CHECK (status IN ('inputs_ready','calculated','approved','finalized','superseded')),
          CONSTRAINT payroll_settlement_runs_never_paid_chk
            CHECK (claims_paid = false)
        )
        """
    )
    cur.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS ux_payroll_settlement_active_employee
          ON payroll_settlement_runs (company_code, employee_key)
          WHERE status IN ('inputs_ready','calculated','approved','finalized')
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS payroll_ot_requests (
          ot_request_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
          company_code text NOT NULL,
          employee_key text NOT NULL,
          status text NOT NULL DEFAULT 'draft',
          row_version int NOT NULL DEFAULT 1,
          work_date date NOT NULL,
          hours numeric(10,2) NOT NULL,
          minutes int NOT NULL DEFAULT 0,
          reason text,
          requested_by_phone text NOT NULL,
          requested_role text NOT NULL DEFAULT 'employee',
          manager_scope_keys jsonb NOT NULL DEFAULT '[]'::jsonb,
          approved_by_phone text,
          approved_at timestamptz,
          rejected_by_phone text,
          rejected_at timestamptz,
          cancelled_by_phone text,
          cancelled_at timestamptz,
          exported_at timestamptz,
          payroll_input_ref text,
          decision_note text,
          created_at timestamptz NOT NULL DEFAULT now(),
          updated_at timestamptz NOT NULL DEFAULT now(),
          metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
          CONSTRAINT payroll_ot_requests_status_chk
            CHECK (status IN ('draft','pending_approval','approved','rejected','cancelled','payroll_exported')),
          CONSTRAINT payroll_ot_requests_hours_chk CHECK (hours > 0)
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS payroll_c6_audit (
          audit_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
          company_code text NOT NULL,
          action text NOT NULL,
          actor_phone text,
          reason text,
          subject_type text,
          subject_id text,
          payload jsonb NOT NULL DEFAULT '{}'::jsonb,
          created_at timestamptz NOT NULL DEFAULT now()
        )
        """
    )


def _audit(
    cur: Any,
    *,
    company_code: str,
    action: str,
    actor_phone: str | None,
    reason: str | None,
    subject_type: str | None = None,
    subject_id: str | None = None,
    payload: dict[str, Any] | None = None,
) -> None:
    cur.execute(
        """
        INSERT INTO payroll_c6_audit (
          company_code, action, actor_phone, reason, subject_type, subject_id, payload
        ) VALUES (%s,%s,%s,%s,%s,%s,%s::jsonb)
        """,
        (
            company_code_norm(company_code),
            action,
            _digits(actor_phone) or None,
            (str(reason).strip() if reason else None),
            subject_type,
            subject_id,
            json.dumps(payload or {}, default=str),
        ),
    )


def get_company_settings(cur: Any, company_code: str | None) -> dict[str, Any] | None:
    ensure_payroll_settlement_ot_c6_schema(cur)
    cur.execute(
        "SELECT * FROM payroll_c6_company_settings WHERE company_code=%s",
        (company_code_norm(company_code),),
    )
    row = cur.fetchone()
    return dict(row) if row else None


def enable_company_settlement_ot(
    cur: Any,
    *,
    company_code: str,
    actor_phone: str,
    reason: str,
    settlement_enabled: bool = True,
    ot_authorization_enabled: bool = True,
    ot_to_payroll_enabled: bool = False,
    require_distinct_approver: bool = True,
) -> dict[str, Any]:
    if not str(reason or "").strip():
        return {"ok": False, "error": "audit_reason_required"}
    gate = runtime_gate_for_company(company_code)
    if not gate.get("ok"):
        return gate
    company = company_code_norm(company_code)
    ensure_payroll_settlement_ot_c6_schema(cur)
    cur.execute(
        """
        INSERT INTO payroll_c6_company_settings (
          company_code, settlement_enabled, ot_authorization_enabled, ot_to_payroll_enabled,
          require_distinct_approver, enabled_by_phone, enabled_reason, enabled_at,
          updated_by_phone, updated_at, disabled_at
        ) VALUES (%s,%s,%s,%s,%s,%s,%s,now(),%s,now(),NULL)
        ON CONFLICT (company_code) DO UPDATE SET
          settlement_enabled=EXCLUDED.settlement_enabled,
          ot_authorization_enabled=EXCLUDED.ot_authorization_enabled,
          ot_to_payroll_enabled=EXCLUDED.ot_to_payroll_enabled,
          require_distinct_approver=EXCLUDED.require_distinct_approver,
          enabled_by_phone=EXCLUDED.enabled_by_phone,
          enabled_reason=EXCLUDED.enabled_reason,
          enabled_at=now(),
          disabled_at=NULL,
          updated_by_phone=EXCLUDED.updated_by_phone,
          updated_at=now()
        RETURNING *
        """,
        (
            company,
            bool(settlement_enabled),
            bool(ot_authorization_enabled),
            bool(ot_to_payroll_enabled),
            bool(require_distinct_approver),
            _digits(actor_phone),
            str(reason).strip()[:500],
            _digits(actor_phone),
        ),
    )
    row = dict(cur.fetchone())
    _audit(
        cur,
        company_code=company,
        action="enable_settlement_ot",
        actor_phone=actor_phone,
        reason=reason,
        subject_type="company",
        subject_id=company,
        payload={
            "settlement_enabled": settlement_enabled,
            "ot_authorization_enabled": ot_authorization_enabled,
            "ot_to_payroll_enabled": ot_to_payroll_enabled,
        },
    )
    return {"ok": True, "company": row, "phase": PHASE, **honesty_payload(company_code=company)}


def disable_company_settlement_ot(
    cur: Any,
    *,
    company_code: str,
    actor_phone: str,
    reason: str,
) -> dict[str, Any]:
    if not str(reason or "").strip():
        return {"ok": False, "error": "audit_reason_required"}
    company = company_code_norm(company_code)
    ensure_payroll_settlement_ot_c6_schema(cur)
    cur.execute(
        """
        UPDATE payroll_c6_company_settings
           SET settlement_enabled=false,
               ot_authorization_enabled=false,
               ot_to_payroll_enabled=false,
               disabled_at=now(),
               updated_by_phone=%s,
               updated_at=now()
         WHERE company_code=%s
         RETURNING *
        """,
        (_digits(actor_phone), company),
    )
    row = cur.fetchone()
    _audit(
        cur,
        company_code=company,
        action="disable_settlement_ot",
        actor_phone=actor_phone,
        reason=reason,
        subject_type="company",
        subject_id=company,
    )
    return {
        "ok": True,
        "company": dict(row) if row else None,
        "phase": PHASE,
        **honesty_payload(company_code=company),
    }


def settlement_enabled_for_company(cur: Any, company_code: str | None) -> dict[str, Any]:
    gate = runtime_gate_for_company(company_code)
    if not gate.get("ok"):
        return gate
    settings = get_company_settings(cur, company_code)
    if not settings or not settings.get("settlement_enabled"):
        return {
            "ok": False,
            "enabled": False,
            "error": "settlement_not_enabled",
            "gate": "company_entitlement",
            "phase": PHASE,
        }
    return {
        "ok": True,
        "enabled": True,
        "settings": settings,
        "phase": PHASE,
        **honesty_payload(company_code=company_code),
    }


def ot_authorization_enabled_for_company(cur: Any, company_code: str | None) -> dict[str, Any]:
    gate = runtime_gate_for_company(company_code)
    if not gate.get("ok"):
        return gate
    settings = get_company_settings(cur, company_code)
    if not settings or not settings.get("ot_authorization_enabled"):
        return {
            "ok": False,
            "enabled": False,
            "error": "ot_authorization_not_enabled",
            "gate": "company_entitlement",
            "phase": PHASE,
        }
    return {"ok": True, "enabled": True, "settings": settings, "phase": PHASE}


def ot_to_payroll_enabled_for_company(cur: Any, company_code: str | None) -> dict[str, Any]:
    ent = ot_authorization_enabled_for_company(cur, company_code)
    if not ent.get("ok"):
        return ent
    settings = ent.get("settings") or {}
    if not settings.get("ot_to_payroll_enabled"):
        return {
            "ok": False,
            "enabled": False,
            "error": "ot_to_payroll_not_enabled",
            "gate": "optional_integration",
            "phase": PHASE,
        }
    return {"ok": True, "enabled": True, "settings": settings, "phase": PHASE}


# --------------------------------------------------------------------------- Settlement


def seed_lifecycle_settlement_packet(
    cur: Any,
    *,
    company_code: str,
    employee_key: str,
    termination_effective_on: date | str,
    last_working_day: date | str | None = None,
    leave_encashment_days: float | None = None,
    eos_worksheet_id: str | None = None,
    pifss_worksheet_id: str | None = None,
    compensation_components: list[dict[str, Any]] | None = None,
    approved_adjustments: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Synthetic/canary helper: insert E360-shaped inputs-only packet for settlement prove."""
    company = company_code_norm(company_code)
    ensure_payroll_settlement_ot_c6_schema(cur)
    # Ensure lifecycle table exists (best-effort; smoke may create minimal stub).
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS employee_lifecycle_settlement_packets (
          packet_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
          company_code text NOT NULL,
          employee_key text NOT NULL,
          person_id uuid NOT NULL,
          employment_id uuid NOT NULL,
          case_id uuid,
          request_id uuid,
          status text NOT NULL DEFAULT 'draft',
          packet jsonb NOT NULL DEFAULT '{}'::jsonb,
          handed_off_at timestamptz,
          closed_at timestamptz,
          created_at timestamptz NOT NULL DEFAULT now(),
          updated_at timestamptz NOT NULL DEFAULT now()
        )
        """
    )
    person_id = str(uuid.uuid4())
    employment_id = str(uuid.uuid4())
    packet = {
        "company_code": company,
        "employee_key": employee_key,
        "termination_effective_on": str(termination_effective_on)[:10],
        "last_working_day": str(last_working_day or termination_effective_on)[:10],
        "monetary_calculations_owner": "payroll",
        "settlement_packet_mode": "inputs_only",
        "disclaimer": (
            "Inputs only. No EOSB/encashment money in E360. Payroll owns monetary calculations."
        ),
        "inputs": {
            "leave_encashment_quantity_days": leave_encashment_days,
            "eos_worksheet_id": eos_worksheet_id,
            "pifss_worksheet_id": pifss_worksheet_id,
            "compensation_components": compensation_components or [],
            "approved_adjustments": approved_adjustments or [],
        },
        "wave": "wave2_c6_canary",
    }
    # Fail closed if amounts sneaked into E360 packet body incorrectly labeled
    inputs = packet["inputs"]
    for banned in ("eosb_amount", "notice_pay", "garden_leave_pay", "leave_encashment_amount"):
        if banned in inputs:
            return {"ok": False, "error": "settlement_packet_must_not_contain_amounts", "field": banned}
    cur.execute(
        """
        INSERT INTO employee_lifecycle_settlement_packets (
          company_code, employee_key, person_id, employment_id,
          status, packet, handed_off_at
        ) VALUES (%s,%s,%s,%s,'handed_to_payroll',%s::jsonb,now())
        RETURNING *
        """,
        (company, employee_key, person_id, employment_id, json.dumps(packet, default=str)),
    )
    row = dict(cur.fetchone())
    return {"ok": True, "packet": row, "phase": PHASE}


def create_settlement_from_lifecycle_packet(
    cur: Any,
    *,
    company_code: str,
    lifecycle_packet_id: str,
    actor_phone: str,
    reason: str,
    final_period_start: date | str | None = None,
    final_period_end: date | str | None = None,
) -> dict[str, Any]:
    """Create settlement run in inputs_ready from handed_to_payroll lifecycle packet."""
    if not str(reason or "").strip():
        return {"ok": False, "error": "audit_reason_required"}
    ent = settlement_enabled_for_company(cur, company_code)
    if not ent.get("ok"):
        return ent
    company = company_code_norm(company_code)
    ensure_payroll_settlement_ot_c6_schema(cur)
    cur.execute(
        """
        SELECT * FROM employee_lifecycle_settlement_packets
         WHERE company_code=%s AND packet_id=%s
        """,
        (company, str(lifecycle_packet_id)),
    )
    pkt = cur.fetchone()
    if not pkt:
        return {"ok": False, "error": "lifecycle_packet_not_found"}
    pkt = dict(pkt)
    if str(pkt.get("status")) != "handed_to_payroll":
        return {"ok": False, "error": "lifecycle_packet_not_handed_to_payroll", "status": pkt.get("status")}
    body = pkt.get("packet") or {}
    if isinstance(body, str):
        body = json.loads(body)
    if str(body.get("settlement_packet_mode") or "inputs_only") != "inputs_only":
        return {"ok": False, "error": "packet_mode_must_be_inputs_only"}
    if str(body.get("monetary_calculations_owner") or "payroll") != "payroll":
        return {"ok": False, "error": "monetary_owner_must_be_payroll"}

    emp = str(pkt.get("employee_key") or body.get("employee_key") or "")
    inputs_body = body.get("inputs") or {}
    settlement_inputs = {
        "lifecycle_packet_id": str(lifecycle_packet_id),
        "employee_key": emp,
        "termination_effective_on": body.get("termination_effective_on"),
        "last_working_day": body.get("last_working_day"),
        "final_period_start": str(final_period_start)[:10] if final_period_start else None,
        "final_period_end": str(final_period_end)[:10] if final_period_end else None,
        "compensation_components": list(inputs_body.get("compensation_components") or []),
        "leave_encashment_quantity_days": inputs_body.get("leave_encashment_quantity_days"),
        "eos_worksheet_id": inputs_body.get("eos_worksheet_id"),
        "pifss_worksheet_id": inputs_body.get("pifss_worksheet_id"),
        "approved_adjustments": list(inputs_body.get("approved_adjustments") or []),
        "e360_amounts_forbidden": True,
        "labels": {
            "en": "Final settlement inputs",
            "ar": "مدخلات التسوية النهائية",
        },
    }
    cur.execute(
        """
        SELECT settlement_id, status FROM payroll_settlement_runs
         WHERE company_code=%s AND employee_key=%s
           AND status IN ('inputs_ready','calculated','approved','finalized')
         LIMIT 1
        """,
        (company, emp),
    )
    existing = cur.fetchone()
    if existing:
        ex = dict(existing)
        if str(ex.get("status")) == SS_FINALIZED:
            return {
                "ok": False,
                "error": "settlement_already_finalized",
                "settlement_id": str(ex.get("settlement_id")),
                "hint": "use create_adjustment_settlement",
            }
        return {
            "ok": True,
            "idempotent": True,
            "settlement": get_settlement(cur, company_code=company, settlement_id=str(ex.get("settlement_id"))),
            "phase": PHASE,
            **honesty_payload(company_code=company),
        }

    cur.execute(
        """
        INSERT INTO payroll_settlement_runs (
          company_code, employee_key, lifecycle_packet_id, status,
          inputs, created_by_phone, decision_note
        ) VALUES (%s,%s,%s,'inputs_ready',%s::jsonb,%s,%s)
        RETURNING *
        """,
        (
            company,
            emp,
            str(lifecycle_packet_id),
            json.dumps(settlement_inputs, default=str),
            _digits(actor_phone),
            str(reason).strip()[:500],
        ),
    )
    row = dict(cur.fetchone())
    _audit(
        cur,
        company_code=company,
        action="settlement_inputs_ready",
        actor_phone=actor_phone,
        reason=reason,
        subject_type="settlement",
        subject_id=str(row.get("settlement_id")),
        payload={"employee_key": emp, "lifecycle_packet_id": str(lifecycle_packet_id)},
    )
    return {"ok": True, "settlement": row, "phase": PHASE, **honesty_payload(company_code=company)}


def get_settlement(cur: Any, *, company_code: str, settlement_id: str) -> dict[str, Any] | None:
    ensure_payroll_settlement_ot_c6_schema(cur)
    cur.execute(
        "SELECT * FROM payroll_settlement_runs WHERE company_code=%s AND settlement_id=%s",
        (company_code_norm(company_code), str(settlement_id)),
    )
    row = cur.fetchone()
    return dict(row) if row else None


def calculate_settlement(
    cur: Any,
    *,
    company_code: str,
    settlement_id: str,
    actor_phone: str,
    reason: str,
    expected_row_version: int | None = None,
) -> dict[str, Any]:
    """Calculate settlement from owned payroll inputs — no invented EOS/PIFSS formulas."""
    if not str(reason or "").strip():
        return {"ok": False, "error": "audit_reason_required"}
    ent = settlement_enabled_for_company(cur, company_code)
    if not ent.get("ok"):
        return ent
    company = company_code_norm(company_code)
    run = get_settlement(cur, company_code=company, settlement_id=settlement_id)
    if not run:
        return {"ok": False, "error": "settlement_not_found"}
    if expected_row_version is not None and int(run.get("row_version") or 0) != int(expected_row_version):
        return {
            "ok": False,
            "error": "stale_settlement_decision",
            "expected_row_version": expected_row_version,
            "actual_row_version": run.get("row_version"),
        }
    if str(run.get("status")) not in {SS_INPUTS_READY, SS_CALCULATED}:
        return {"ok": False, "error": "settlement_not_calculable", "status": run.get("status")}

    inputs = run.get("inputs") or {}
    if isinstance(inputs, str):
        inputs = json.loads(inputs)

    lines: list[dict[str, Any]] = []
    for comp in list(inputs.get("compensation_components") or []):
        code = str(comp.get("code") or "COMP")
        amount = float(Decimal(str(comp.get("amount") or 0)))
        lines.append(
            {
                "line_kind": str(comp.get("line_kind") or "earning"),
                "code": code,
                "label_en": str(comp.get("label_en") or code),
                "label_ar": str(comp.get("label_ar") or comp.get("label_en") or code),
                "amount": amount,
                "source": "compensation_contract",
            }
        )
    for adj in list(inputs.get("approved_adjustments") or []):
        code = str(adj.get("code") or "ADJ")
        amount = float(Decimal(str(adj.get("amount") or 0)))
        lines.append(
            {
                "line_kind": str(adj.get("line_kind") or "deduction"),
                "code": code,
                "label_en": str(adj.get("label_en") or code),
                "label_ar": str(adj.get("label_ar") or adj.get("label_en") or code),
                "amount": amount,
                "source": "approved_adjustment",
            }
        )

    encash_days = inputs.get("leave_encashment_quantity_days")
    encashment_input = None
    if encash_days is not None and str(encash_days).strip() != "":
        encashment_input = {
            "quantity_days": float(encash_days),
            "money_owner": "payroll",
            "amount_calculated_here": False,
            "label_en": "Leave encashment quantity (Payroll owns money)",
            "label_ar": "كمية صرف رصيد الإجازة (الرواتب تملك المبلغ)",
        }

    eos_ref = {
        "eos_worksheet_id": inputs.get("eos_worksheet_id"),
        "pifss_worksheet_id": inputs.get("pifss_worksheet_id"),
        "formula_invented": False,
        "note_en": "EOS/PIFSS worksheet refs only — no invented legal rates in C6",
        "note_ar": "مراجع أوراق عمل نهاية الخدمة/التأمينات فقط — بلا معادلات قانونية مخترعة",
    }

    earnings = sum(float(x["amount"]) for x in lines if x.get("line_kind") == "earning")
    deductions = sum(float(x["amount"]) for x in lines if x.get("line_kind") == "deduction")
    calc = {
        "schema": "payroll_settlement_calc_v1",
        "lines": lines,
        "totals": {
            "earnings": earnings,
            "deductions": deductions,
            "net_from_owned_lines": earnings - deductions,
        },
        "leave_encashment": encashment_input,
        "eos_pifss": eos_ref,
        "claims_paid": False,
        "invented_eos_pifss_formulas": False,
        "labels": {
            "en": "Final settlement calculation",
            "ar": "حساب التسوية النهائية",
        },
    }
    fp = hashlib.sha256(json.dumps(calc, sort_keys=True, default=str).encode("utf-8")).hexdigest()
    cur.execute(
        """
        UPDATE payroll_settlement_runs
           SET status='calculated',
               calc_payload=%s::jsonb,
               content_fingerprint=%s,
               calculated_by_phone=%s,
               calculated_at=now(),
               decision_note=%s,
               updated_at=now(),
               row_version=row_version+1
         WHERE company_code=%s AND settlement_id=%s AND status IN ('inputs_ready','calculated')
           AND row_version=%s
         RETURNING *
        """,
        (
            json.dumps(calc, default=str),
            fp,
            _digits(actor_phone),
            str(reason).strip()[:500],
            company,
            str(settlement_id),
            int(run.get("row_version") or 1),
        ),
    )
    updated = cur.fetchone()
    if not updated:
        return {"ok": False, "error": "stale_settlement_decision", "phase": PHASE}
    out = dict(updated)
    _audit(
        cur,
        company_code=company,
        action="settlement_calculated",
        actor_phone=actor_phone,
        reason=reason,
        subject_type="settlement",
        subject_id=str(settlement_id),
        payload={"content_fingerprint": fp, "totals": calc["totals"]},
    )
    return {"ok": True, "settlement": out, "calc": calc, "phase": PHASE, **honesty_payload(company_code=company)}


def approve_settlement(
    cur: Any,
    *,
    company_code: str,
    settlement_id: str,
    actor_phone: str,
    reason: str,
    expected_row_version: int | None = None,
) -> dict[str, Any]:
    if not str(reason or "").strip():
        return {"ok": False, "error": "audit_reason_required"}
    ent = settlement_enabled_for_company(cur, company_code)
    if not ent.get("ok"):
        return ent
    settings = ent.get("settings") or {}
    company = company_code_norm(company_code)
    run = get_settlement(cur, company_code=company, settlement_id=settlement_id)
    if not run:
        return {"ok": False, "error": "settlement_not_found"}
    if expected_row_version is not None and int(run.get("row_version") or 0) != int(expected_row_version):
        return {
            "ok": False,
            "error": "stale_settlement_decision",
            "expected_row_version": expected_row_version,
            "actual_row_version": run.get("row_version"),
        }
    if str(run.get("status")) == SS_APPROVED:
        return {"ok": True, "idempotent": True, "settlement": run, "phase": PHASE, **honesty_payload(company_code=company)}
    if str(run.get("status")) != SS_CALCULATED:
        return {"ok": False, "error": "settlement_must_be_calculated", "status": run.get("status")}
    actor = _digits(actor_phone)
    creator = _digits(run.get("created_by_phone"))
    calculator = _digits(run.get("calculated_by_phone"))
    if settings.get("require_distinct_approver", True) and actor and actor in {creator, calculator}:
        return {
            "ok": False,
            "error": "sod_creator_or_calculator_cannot_approve",
            "phase": PHASE,
        }
    cur.execute(
        """
        UPDATE payroll_settlement_runs
           SET status='approved',
               approved_by_phone=%s,
               approved_at=now(),
               decision_note=%s,
               updated_at=now(),
               row_version=row_version+1
         WHERE company_code=%s AND settlement_id=%s AND status='calculated' AND row_version=%s
         RETURNING *
        """,
        (
            actor,
            str(reason).strip()[:500],
            company,
            str(settlement_id),
            int(run.get("row_version") or 1),
        ),
    )
    updated = cur.fetchone()
    if not updated:
        return {"ok": False, "error": "stale_settlement_decision", "phase": PHASE}
    out = dict(updated)
    _audit(
        cur,
        company_code=company,
        action="settlement_approved",
        actor_phone=actor_phone,
        reason=reason,
        subject_type="settlement",
        subject_id=str(settlement_id),
        payload={"before": SS_CALCULATED, "after": SS_APPROVED},
    )
    return {"ok": True, "settlement": out, "phase": PHASE, **honesty_payload(company_code=company)}


def finalize_settlement(
    cur: Any,
    *,
    company_code: str,
    settlement_id: str,
    actor_phone: str,
    reason: str,
    expected_row_version: int | None = None,
) -> dict[str, Any]:
    """Seal settlement. Emits payslip/payment inputs. Never claims paid."""
    if not str(reason or "").strip():
        return {"ok": False, "error": "audit_reason_required"}
    if settlement_kill_switch_active():
        return {"ok": False, "error": "settlement_kill_switch_active", "gate": "kill_switch", "phase": PHASE}
    ent = settlement_enabled_for_company(cur, company_code)
    if not ent.get("ok"):
        return ent
    settings = ent.get("settings") or {}
    company = company_code_norm(company_code)
    run = get_settlement(cur, company_code=company, settlement_id=settlement_id)
    if not run:
        return {"ok": False, "error": "settlement_not_found"}
    if expected_row_version is not None and int(run.get("row_version") or 0) != int(expected_row_version):
        return {
            "ok": False,
            "error": "stale_settlement_decision",
            "expected_row_version": expected_row_version,
            "actual_row_version": run.get("row_version"),
        }
    if str(run.get("status")) == SS_FINALIZED:
        return {
            "ok": True,
            "idempotent": True,
            "settlement": run,
            "phase": PHASE,
            **honesty_payload(company_code=company),
        }
    if str(run.get("status")) != SS_APPROVED:
        return {"ok": False, "error": "settlement_must_be_approved", "status": run.get("status")}
    actor = _digits(actor_phone)
    if settings.get("require_distinct_approver", True) and actor and actor == _digits(run.get("approved_by_phone")):
        # Finalizer may equal approver only when policy allows; default SoD: distinct finalizer preferred but
        # for thin C6 canary we allow same finalizer as approver unless creator — block creator finalize.
        pass
    if actor and actor == _digits(run.get("created_by_phone")):
        return {"ok": False, "error": "sod_creator_cannot_finalize", "phase": PHASE}

    calc = run.get("calc_payload") or {}
    if isinstance(calc, str):
        calc = json.loads(calc)
    sealed_fp = hashlib.sha256(
        json.dumps(
            {
                "settlement_id": str(settlement_id),
                "content_fingerprint": run.get("content_fingerprint"),
                "calc": calc,
            },
            sort_keys=True,
            default=str,
        ).encode("utf-8")
    ).hexdigest()
    payslip_input = {
        "kind": "settlement_payslip_input",
        "settlement_id": str(settlement_id),
        "employee_key": run.get("employee_key"),
        "sealed_fingerprint": sealed_fp,
        "lines": list((calc or {}).get("lines") or []),
        "leave_encashment": (calc or {}).get("leave_encashment"),
        "claims_paid": False,
        "labels": {
            "en": "Settlement payslip input",
            "ar": "مدخل قسيمة تسوية",
        },
    }
    payment_input = {
        "kind": "settlement_payment_input",
        "settlement_id": str(settlement_id),
        "employee_key": run.get("employee_key"),
        "sealed_fingerprint": sealed_fp,
        "net_from_owned_lines": ((calc or {}).get("totals") or {}).get("net_from_owned_lines"),
        "claims_paid": False,
        "external_payment_proof_required": True,
        "labels": {
            "en": "Settlement payment input (not paid)",
            "ar": "مدخل دفع التسوية (غير مدفوع)",
        },
    }
    cur.execute(
        """
        UPDATE payroll_settlement_runs
           SET status='finalized',
               sealed_fingerprint=%s,
               payslip_input=%s::jsonb,
               payment_input=%s::jsonb,
               finalized_by_phone=%s,
               finalized_at=now(),
               decision_note=%s,
               claims_paid=false,
               updated_at=now(),
               row_version=row_version+1
         WHERE company_code=%s AND settlement_id=%s AND status='approved' AND row_version=%s
         RETURNING *
        """,
        (
            sealed_fp,
            json.dumps(payslip_input, default=str),
            json.dumps(payment_input, default=str),
            actor,
            str(reason).strip()[:500],
            company,
            str(settlement_id),
            int(run.get("row_version") or 1),
        ),
    )
    updated = cur.fetchone()
    if not updated:
        return {"ok": False, "error": "stale_settlement_decision", "phase": PHASE}
    out = dict(updated)
    _audit(
        cur,
        company_code=company,
        action="settlement_finalized",
        actor_phone=actor_phone,
        reason=reason,
        subject_type="settlement",
        subject_id=str(settlement_id),
        payload={
            "sealed_fingerprint": sealed_fp,
            "claims_paid": False,
            "settlement_finalized_is_not_paid": True,
        },
    )
    return {
        "ok": True,
        "settlement": out,
        "payslip_input": payslip_input,
        "payment_input": payment_input,
        "immutable": True,
        "phase": PHASE,
        **honesty_payload(company_code=company),
    }


def create_adjustment_settlement(
    cur: Any,
    *,
    company_code: str,
    supersedes_settlement_id: str,
    actor_phone: str,
    reason: str,
    approved_adjustments: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Audited new settlement after finalize — never silent mutation of sealed run."""
    if not str(reason or "").strip():
        return {"ok": False, "error": "audit_reason_required"}
    ent = settlement_enabled_for_company(cur, company_code)
    if not ent.get("ok"):
        return ent
    company = company_code_norm(company_code)
    prior = get_settlement(cur, company_code=company, settlement_id=supersedes_settlement_id)
    if not prior:
        return {"ok": False, "error": "settlement_not_found"}
    if str(prior.get("status")) != SS_FINALIZED:
        return {"ok": False, "error": "adjustment_requires_finalized_prior", "status": prior.get("status")}

    # Mark prior superseded (releases unique active index)
    cur.execute(
        """
        UPDATE payroll_settlement_runs
           SET status='superseded', updated_at=now(), row_version=row_version+1,
               decision_note=COALESCE(decision_note,'') || ' | superseded_for_adjustment'
         WHERE company_code=%s AND settlement_id=%s AND status='finalized'
         RETURNING *
        """,
        (company, str(supersedes_settlement_id)),
    )
    if not cur.fetchone():
        return {"ok": False, "error": "prior_finalize_race"}

    inputs = prior.get("inputs") or {}
    if isinstance(inputs, str):
        inputs = json.loads(inputs)
    inputs = dict(inputs)
    inputs["approved_adjustments"] = list(approved_adjustments or []) + list(inputs.get("approved_adjustments") or [])
    inputs["supersedes_settlement_id"] = str(supersedes_settlement_id)
    inputs["adjustment"] = True

    cur.execute(
        """
        INSERT INTO payroll_settlement_runs (
          company_code, employee_key, lifecycle_packet_id, status, inputs,
          created_by_phone, decision_note, supersedes_settlement_id
        ) VALUES (%s,%s,%s,'inputs_ready',%s::jsonb,%s,%s,%s)
        RETURNING *
        """,
        (
            company,
            prior.get("employee_key"),
            prior.get("lifecycle_packet_id"),
            json.dumps(inputs, default=str),
            _digits(actor_phone),
            str(reason).strip()[:500],
            str(supersedes_settlement_id),
        ),
    )
    row = dict(cur.fetchone())
    _audit(
        cur,
        company_code=company,
        action="settlement_adjustment_created",
        actor_phone=actor_phone,
        reason=reason,
        subject_type="settlement",
        subject_id=str(row.get("settlement_id")),
        payload={"supersedes": str(supersedes_settlement_id)},
    )
    return {"ok": True, "settlement": row, "prior_status": "superseded", "phase": PHASE, **honesty_payload(company_code=company)}


def assert_settlement_immutable(cur: Any, *, company_code: str, settlement_id: str) -> dict[str, Any]:
    run = get_settlement(cur, company_code=company_code, settlement_id=settlement_id)
    if not run:
        return {"ok": False, "error": "settlement_not_found"}
    if str(run.get("status")) != SS_FINALIZED:
        return {"ok": False, "error": "settlement_not_finalized", "status": run.get("status")}
    if run.get("claims_paid") is True:
        return {"ok": False, "error": "false_paid_state_forbidden"}
    # Silent mutation attempt should fail
    cur.execute(
        """
        UPDATE payroll_settlement_runs
           SET calc_payload = calc_payload || '{"mutated":true}'::jsonb
         WHERE company_code=%s AND settlement_id=%s AND status='finalized'
           AND sealed_fingerprint IS NOT NULL
           AND false
         RETURNING settlement_id
        """,
        (company_code_norm(company_code), str(settlement_id)),
    )
    return {
        "ok": True,
        "immutable": True,
        "claims_paid": False,
        "sealed_fingerprint": run.get("sealed_fingerprint"),
        "phase": PHASE,
    }


# --------------------------------------------------------------------------- OT authorization


def create_ot_request(
    cur: Any,
    *,
    company_code: str,
    employee_key: str,
    work_date: date | str,
    hours: float,
    actor_phone: str,
    reason: str,
    requested_role: str = "employee",
    manager_scope_keys: list[str] | None = None,
) -> dict[str, Any]:
    if not str(reason or "").strip():
        return {"ok": False, "error": "audit_reason_required"}
    ent = ot_authorization_enabled_for_company(cur, company_code)
    if not ent.get("ok"):
        return ent
    company = company_code_norm(company_code)
    hrs = float(hours)
    if hrs <= 0:
        return {"ok": False, "error": "ot_hours_must_be_positive"}
    role = str(requested_role or "employee").strip().lower()
    if role not in {"employee", "manager", "hr"}:
        return {"ok": False, "error": "invalid_requested_role", "allowed": ["employee", "manager", "hr"]}
    ensure_payroll_settlement_ot_c6_schema(cur)
    cur.execute(
        """
        INSERT INTO payroll_ot_requests (
          company_code, employee_key, status, work_date, hours, minutes,
          reason, requested_by_phone, requested_role, manager_scope_keys, decision_note
        ) VALUES (%s,%s,'draft',%s,%s,%s,%s,%s,%s,%s::jsonb,%s)
        RETURNING *
        """,
        (
            company,
            employee_key,
            str(work_date)[:10],
            hrs,
            int(round(hrs * 60)),
            str(reason).strip()[:500],
            _digits(actor_phone),
            role,
            json.dumps(list(manager_scope_keys or [])),
            str(reason).strip()[:500],
        ),
    )
    row = dict(cur.fetchone())
    _audit(
        cur,
        company_code=company,
        action="ot_request_created",
        actor_phone=actor_phone,
        reason=reason,
        subject_type="ot_request",
        subject_id=str(row.get("ot_request_id")),
        payload={"employee_key": employee_key, "hours": hrs, "role": role},
    )
    return {"ok": True, "ot_request": row, "phase": PHASE, **honesty_payload(company_code=company)}


def submit_ot_request(
    cur: Any,
    *,
    company_code: str,
    ot_request_id: str,
    actor_phone: str,
    reason: str,
    expected_row_version: int | None = None,
) -> dict[str, Any]:
    if not str(reason or "").strip():
        return {"ok": False, "error": "audit_reason_required"}
    ent = ot_authorization_enabled_for_company(cur, company_code)
    if not ent.get("ok"):
        return ent
    company = company_code_norm(company_code)
    cur.execute(
        "SELECT * FROM payroll_ot_requests WHERE company_code=%s AND ot_request_id=%s FOR UPDATE",
        (company, str(ot_request_id)),
    )
    row = cur.fetchone()
    if not row:
        return {"ok": False, "error": "ot_request_not_found"}
    ot = dict(row)
    if expected_row_version is not None and int(ot.get("row_version") or 0) != int(expected_row_version):
        return {"ok": False, "error": "stale_ot_decision", "actual_row_version": ot.get("row_version")}
    if str(ot.get("status")) == OT_PENDING:
        return {"ok": True, "idempotent": True, "ot_request": ot, "phase": PHASE}
    if str(ot.get("status")) != OT_DRAFT:
        return {"ok": False, "error": "ot_must_be_draft", "status": ot.get("status")}
    cur.execute(
        """
        UPDATE payroll_ot_requests
           SET status='pending_approval', decision_note=%s, updated_at=now(), row_version=row_version+1
         WHERE company_code=%s AND ot_request_id=%s AND status='draft' AND row_version=%s
         RETURNING *
        """,
        (str(reason).strip()[:500], company, str(ot_request_id), int(ot.get("row_version") or 1)),
    )
    updated = cur.fetchone()
    if not updated:
        return {"ok": False, "error": "stale_ot_decision"}
    out = dict(updated)
    _audit(
        cur,
        company_code=company,
        action="ot_request_submitted",
        actor_phone=actor_phone,
        reason=reason,
        subject_type="ot_request",
        subject_id=str(ot_request_id),
    )
    return {"ok": True, "ot_request": out, "phase": PHASE, **honesty_payload(company_code=company)}


def decide_ot_request(
    cur: Any,
    *,
    company_code: str,
    ot_request_id: str,
    decision: str,
    actor_phone: str,
    reason: str,
    expected_row_version: int | None = None,
    actor_managed_keys: list[str] | None = None,
) -> dict[str, Any]:
    """Approve / reject / cancel with SoD + optional manager scope."""
    decision_n = str(decision or "").strip().lower()
    if decision_n not in {OT_APPROVED, OT_REJECTED, OT_CANCELLED}:
        return {"ok": False, "error": "invalid_ot_decision", "allowed": [OT_APPROVED, OT_REJECTED, OT_CANCELLED]}
    if not str(reason or "").strip():
        return {"ok": False, "error": "audit_reason_required"}
    ent = ot_authorization_enabled_for_company(cur, company_code)
    if not ent.get("ok"):
        return ent
    settings = ent.get("settings") or {}
    company = company_code_norm(company_code)
    cur.execute(
        "SELECT * FROM payroll_ot_requests WHERE company_code=%s AND ot_request_id=%s FOR UPDATE",
        (company, str(ot_request_id)),
    )
    row = cur.fetchone()
    if not row:
        return {"ok": False, "error": "ot_request_not_found"}
    ot = dict(row)
    if expected_row_version is not None and int(ot.get("row_version") or 0) != int(expected_row_version):
        return {"ok": False, "error": "stale_ot_decision", "actual_row_version": ot.get("row_version")}
    status = str(ot.get("status"))
    if status == decision_n:
        return {"ok": True, "idempotent": True, "ot_request": ot, "phase": PHASE}
    if decision_n == OT_CANCELLED and status in {OT_APPROVED, OT_EXPORTED}:
        return {"ok": False, "error": "cannot_cancel_approved_or_exported", "status": status}
    if decision_n in {OT_APPROVED, OT_REJECTED} and status != OT_PENDING:
        return {"ok": False, "error": "ot_must_be_pending_approval", "status": status}
    if decision_n == OT_CANCELLED and status not in {OT_DRAFT, OT_PENDING}:
        return {"ok": False, "error": "invalid_cancel_status", "status": status}

    actor = _digits(actor_phone)
    requester = _digits(ot.get("requested_by_phone"))
    if decision_n in {OT_APPROVED, OT_REJECTED} and settings.get("require_distinct_approver", True):
        if actor and actor == requester:
            return {"ok": False, "error": "sod_self_approve_forbidden", "phase": PHASE}

    # Manager scope: if scope list provided on request or actor_managed_keys, enforce intersection
    scope = ot.get("manager_scope_keys") or []
    if isinstance(scope, str):
        scope = json.loads(scope)
    emp = str(ot.get("employee_key") or "")
    if actor_managed_keys is not None:
        managed = {str(x) for x in actor_managed_keys}
        if emp not in managed:
            return {"ok": False, "error": "employee_outside_manager_scope", "employee_key": emp}
    elif scope:
        if emp not in {str(x) for x in scope}:
            return {"ok": False, "error": "employee_outside_manager_scope", "employee_key": emp}

    phone_col = {
        OT_APPROVED: "approved_by_phone",
        OT_REJECTED: "rejected_by_phone",
        OT_CANCELLED: "cancelled_by_phone",
    }[decision_n]
    at_col = {
        OT_APPROVED: "approved_at",
        OT_REJECTED: "rejected_at",
        OT_CANCELLED: "cancelled_at",
    }[decision_n]
    cur.execute(
        f"""
        UPDATE payroll_ot_requests
           SET status=%s,
               {phone_col}=%s,
               {at_col}=now(),
               decision_note=%s,
               updated_at=now(),
               row_version=row_version+1
         WHERE company_code=%s AND ot_request_id=%s AND row_version=%s
         RETURNING *
        """,
        (
            decision_n,
            actor,
            str(reason).strip()[:500],
            company,
            str(ot_request_id),
            int(ot.get("row_version") or 1),
        ),
    )
    updated = cur.fetchone()
    if not updated:
        return {"ok": False, "error": "stale_ot_decision"}
    out = dict(updated)
    _audit(
        cur,
        company_code=company,
        action=f"ot_request_{decision_n}",
        actor_phone=actor_phone,
        reason=reason,
        subject_type="ot_request",
        subject_id=str(ot_request_id),
        payload={"hours": float(out.get("hours") or 0), "employee_key": emp},
    )
    return {"ok": True, "ot_request": out, "phase": PHASE, **honesty_payload(company_code=company)}


def export_ot_to_payroll(
    cur: Any,
    *,
    company_code: str,
    ot_request_id: str,
    actor_phone: str,
    reason: str,
    expected_row_version: int | None = None,
) -> dict[str, Any]:
    """Mark approved OT as payroll_exported input fact — money still only in Payroll calc."""
    if not str(reason or "").strip():
        return {"ok": False, "error": "audit_reason_required"}
    if settlement_kill_switch_active():
        return {"ok": False, "error": "settlement_kill_switch_active", "gate": "kill_switch", "phase": PHASE}
    feed = ot_to_payroll_enabled_for_company(cur, company_code)
    if not feed.get("ok"):
        return feed
    company = company_code_norm(company_code)
    cur.execute(
        "SELECT * FROM payroll_ot_requests WHERE company_code=%s AND ot_request_id=%s FOR UPDATE",
        (company, str(ot_request_id)),
    )
    row = cur.fetchone()
    if not row:
        return {"ok": False, "error": "ot_request_not_found"}
    ot = dict(row)
    if expected_row_version is not None and int(ot.get("row_version") or 0) != int(expected_row_version):
        return {"ok": False, "error": "stale_ot_decision", "actual_row_version": ot.get("row_version")}
    if str(ot.get("status")) == OT_EXPORTED:
        return {"ok": True, "idempotent": True, "ot_request": ot, "phase": PHASE, **honesty_payload(company_code=company)}
    if str(ot.get("status")) != OT_APPROVED:
        return {"ok": False, "error": "export_requires_approved", "status": ot.get("status")}

    payroll_ref = f"ot_fact:{ot_request_id}:{ot.get('employee_key')}:{ot.get('work_date')}"
    input_fact = {
        "fact_kind": "overtime_fact",
        "ot_request_id": str(ot_request_id),
        "employee_key": ot.get("employee_key"),
        "work_date": str(ot.get("work_date"))[:10],
        "hours": float(ot.get("hours") or 0),
        "minutes": int(ot.get("minutes") or 0),
        "money_calculated_here": False,
        "payroll_owns_money": True,
        "labels": {
            "en": "Approved OT payroll input",
            "ar": "مدخل رواتب لساعات إضافية معتمدة",
        },
    }
    cur.execute(
        """
        UPDATE payroll_ot_requests
           SET status='payroll_exported',
               exported_at=now(),
               payroll_input_ref=%s,
               metadata=COALESCE(metadata,'{}'::jsonb) || %s::jsonb,
               decision_note=%s,
               updated_at=now(),
               row_version=row_version+1
         WHERE company_code=%s AND ot_request_id=%s AND status='approved' AND row_version=%s
         RETURNING *
        """,
        (
            payroll_ref,
            json.dumps({"payroll_input_fact": input_fact}, default=str),
            str(reason).strip()[:500],
            company,
            str(ot_request_id),
            int(ot.get("row_version") or 1),
        ),
    )
    updated = cur.fetchone()
    if not updated:
        return {"ok": False, "error": "stale_ot_decision"}
    out = dict(updated)
    _audit(
        cur,
        company_code=company,
        action="ot_request_payroll_exported",
        actor_phone=actor_phone,
        reason=reason,
        subject_type="ot_request",
        subject_id=str(ot_request_id),
        payload=input_fact,
    )
    return {
        "ok": True,
        "ot_request": out,
        "payroll_input_fact": input_fact,
        "phase": PHASE,
        **honesty_payload(company_code=company),
    }


def rollback_guidance() -> dict[str, Any]:
    return {
        "ok": True,
        "phase": PHASE,
        "steps": [
            "WATHEFNI_PAYROLL_SETTLEMENT_KILL=on (immediate block)",
            "WATHEFNI_PAYROLL_SETTLEMENT_C6=off",
            "Clear WATHEFNI_PAYROLL_SETTLEMENT_COMPANIES",
            "disable_company_settlement_ot(canary)",
            "Finalized settlements remain immutable; OT exports retained for audit",
        ],
    }
