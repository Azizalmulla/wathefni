#!/usr/bin/env python3
"""Wave 3 C5 — Exit Close + Settlement Ack/Waiver + Exit Interview + Rehire/Alumni.

Owner-approved under WAVE3_EMPLOYEE_LIFECYCLE_CHARTER.
C4 OFFBOARDING_FULL_PASS ACCEPTED/frozen before this slice.

Exit-close SM:
  pending_close → ready_to_close → closed
  (+ blocked | cancelled)

closed = sole authority that sets canonical employment left/inactive.
Does NOT: invent fake settlement rows; equate finalized/ack with paid;
require IdP/Payroll/Exit Interview universally; unlock real termination;
Assistant mutations; silently reopen closed employment.

Gates (fail-closed):
  1) WATHEFNI_EXIT_CLOSE_C5 must be on
  2) company in WATHEFNI_EXIT_CLOSE_COMPANIES (empty = nobody)
  3) company entitlement in exit_close_c5_company_settings
  4) WATHEFNI_REAL_TERMINATION_CANARY remains off
  5) synthetic markers required for subjects
"""
from __future__ import annotations

import json
import os
import uuid
from datetime import date, datetime, timedelta
from typing import Any

PHASE = "exit_close_c5"
CONTRACT_VERSION = "exit_close_c5_v1"
PASS_STAMP = "EXIT_CLOSE_HANDOFF_FULL_PASS"
_ON = {"1", "true", "yes", "on"}

ST_PENDING = "pending_close"
ST_READY = "ready_to_close"
ST_CLOSED = "closed"
ST_BLOCKED = "blocked"
ST_CANCELLED = "cancelled"

SETT_NOT_REQUIRED = "not_required"
SETT_AWAITING_FINALIZED = "awaiting_finalized"
SETT_FINALIZED_AWAITING_ACK = "finalized_awaiting_ack"
SETT_ACKNOWLEDGED = "acknowledged"
SETT_WAIVED = "waived"

PAY_UNKNOWN = "unknown"
PAY_NOT_CONFIRMED = "not_confirmed"
PAY_CONFIRMED = "confirmed"  # never set by C5 from finalize/ack alone

REHIRE_ELIGIBLE = "eligible"
REHIRE_NOT = "not_eligible"
REHIRE_REVIEW = "review_required"

INTERVIEW_INVITED = "invited"
INTERVIEW_COMPLETED = "completed"
INTERVIEW_DECLINED = "declined"
INTERVIEW_SKIPPED = "skipped"

STATUS_LABELS = {
    "pending_close": {"en": "Pending close", "ar": "بانتظار الإغلاق"},
    "ready_to_close": {"en": "Ready to close", "ar": "جاهز للإغلاق"},
    "closed": {"en": "Closed", "ar": "مغلق"},
    "blocked": {"en": "Blocked", "ar": "موقوف"},
    "cancelled": {"en": "Cancelled", "ar": "ملغى"},
    "not_required": {"en": "Not required", "ar": "غير مطلوب"},
    "awaiting_finalized": {"en": "Awaiting settlement finalize", "ar": "بانتظار ختم التسوية"},
    "finalized_awaiting_ack": {"en": "Finalized — awaiting ack", "ar": "مختوم — بانتظار الإقرار"},
    "acknowledged": {"en": "Acknowledged", "ar": "مُقَر"},
    "waived": {"en": "Waived", "ar": "مُعفى"},
    "eligible": {"en": "Rehire eligible", "ar": "مؤهل لإعادة التعيين"},
    "not_eligible": {"en": "Not rehire eligible", "ar": "غير مؤهل لإعادة التعيين"},
    "review_required": {"en": "Rehire review required", "ar": "مراجعة إعادة التعيين مطلوبة"},
    "invited": {"en": "Interview invited", "ar": "دعوة مقابلة الخروج"},
    "completed": {"en": "Completed", "ar": "مكتمل"},
    "declined": {"en": "Declined", "ar": "مرفوض"},
    "skipped": {"en": "Skipped", "ar": "تم التخطي"},
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


def exit_close_c5_runtime_on() -> bool:
    return _env_on("WATHEFNI_EXIT_CLOSE_C5", "off")


def real_termination_canary_on() -> bool:
    return _env_on("WATHEFNI_REAL_TERMINATION_CANARY", "off")


def exit_close_company_allowlist() -> set[str]:
    raw = str(os.environ.get("WATHEFNI_EXIT_CLOSE_COMPANIES") or "").strip()
    if not raw:
        return set()
    return {p.strip().upper() for p in raw.split(",") if p.strip()}


def synthetic_markers() -> tuple[str, ...]:
    raw = str(
        os.environ.get("WATHEFNI_EXIT_CLOSE_SYNTHETIC_MARKERS") or "W3C5,XC5,W3C4,OB4,W3C3,EX3"
    ).strip()
    return tuple(p.strip() for p in raw.split(",") if p.strip())


def honesty_payload(*, company_code: str | None = None) -> dict[str, Any]:
    return {
        "phase": PHASE,
        "contract_version": CONTRACT_VERSION,
        "pass_stamp": PASS_STAMP,
        "assistant_mutations": False,
        "sole_employment_left_authority": True,
        "payroll_required": False,
        "idp_required": False,
        "exit_interview_required_by_default": False,
        "settlement_finalized_is_not_paid": True,
        "settlement_ack_is_not_paid": True,
        "fake_settlement_rows_forbidden": True,
        "real_termination_canary": real_termination_canary_on(),
        "real_termination_dark": not real_termination_canary_on(),
        "synthetic_session_revoke_only": True,
        "company_code": company_code_norm(company_code) if company_code else None,
    }


def rollback_guidance() -> dict[str, Any]:
    return {
        "phase": PHASE,
        "steps": [
            "WATHEFNI_EXIT_CLOSE_C5=off",
            "Clear WATHEFNI_EXIT_CLOSE_COMPANIES",
            "WATHEFNI_REAL_TERMINATION_CANARY remains off",
            "disable_company_exit_close(canary)",
            "Closed employment + alumni/interview history retained",
        ],
        "history_intact": True,
    }


def assert_real_termination_dark() -> dict[str, Any]:
    if real_termination_canary_on():
        return {
            "ok": False,
            "error": "real_termination_canary_must_remain_off_in_c5",
            "gate": "real_termination_canary",
            "phase": PHASE,
        }
    return {"ok": True, "real_termination_dark": True}


def assert_synthetic_employee_key(employee_key: str) -> dict[str, Any]:
    key = str(employee_key or "")
    markers = synthetic_markers()
    if any(m and m in key for m in markers):
        return {"ok": True, "synthetic": True, "markers": list(markers)}
    return {
        "ok": False,
        "error": "non_synthetic_employee_blocked",
        "gate": "synthetic_only",
        "markers": list(markers),
        "phase": PHASE,
    }


def runtime_gate_for_company(company_code: str | None) -> dict[str, Any]:
    company = company_code_norm(company_code)
    if not company:
        return {"ok": False, "enabled": False, "error": "company_required", "phase": PHASE}
    if not exit_close_c5_runtime_on():
        return {
            "ok": False,
            "enabled": False,
            "error": "exit_close_c5_off",
            "gate": "runtime_flag",
            "phase": PHASE,
        }
    allow = exit_close_company_allowlist()
    if not allow:
        return {
            "ok": False,
            "enabled": False,
            "error": "exit_close_company_not_allowlisted",
            "gate": "company_allowlist",
            "phase": PHASE,
        }
    if company not in allow:
        return {
            "ok": False,
            "enabled": False,
            "error": "exit_close_company_not_allowlisted",
            "gate": "company_allowlist",
            "phase": PHASE,
            "company_code": company,
        }
    return {"ok": True, "enabled": True, "company_code": company, "phase": PHASE}


def ensure_exit_close_c5_schema(cur: Any, *, force: bool = False) -> None:
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS exit_close_c5_company_settings (
          company_code text PRIMARY KEY,
          enabled boolean NOT NULL DEFAULT false,
          require_offboarding_complete boolean NOT NULL DEFAULT true,
          require_last_working_day_reached boolean NOT NULL DEFAULT true,
          allow_lwd_override boolean NOT NULL DEFAULT true,
          require_settlement_ack boolean NOT NULL DEFAULT false,
          allow_settlement_waiver boolean NOT NULL DEFAULT true,
          settlement_waiver_roles jsonb NOT NULL DEFAULT '["hr"]'::jsonb,
          require_access_revoke_ack boolean NOT NULL DEFAULT false,
          access_waiver_roles jsonb NOT NULL DEFAULT '["hr"]'::jsonb,
          exit_interview_enabled boolean NOT NULL DEFAULT false,
          exit_interview_required boolean NOT NULL DEFAULT false,
          require_distinct_closer boolean NOT NULL DEFAULT true,
          default_rehire_eligibility text NOT NULL DEFAULT 'eligible',
          enabled_by_phone text,
          enabled_reason text,
          enabled_at timestamptz,
          disabled_at timestamptz,
          updated_by_phone text,
          updated_at timestamptz NOT NULL DEFAULT now(),
          metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
          CONSTRAINT exit_close_c5_rehire_default_chk
            CHECK (default_rehire_eligibility IN ('eligible','not_eligible','review_required'))
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS exit_close_cases (
          close_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
          company_code text NOT NULL,
          employee_key text NOT NULL,
          offboarding_case_id uuid NOT NULL,
          exit_intent_case_id uuid,
          status text NOT NULL DEFAULT 'pending_close',
          row_version int NOT NULL DEFAULT 1,
          blocked_reasons jsonb NOT NULL DEFAULT '[]'::jsonb,
          last_working_day date,
          lwd_override boolean NOT NULL DEFAULT false,
          lwd_override_reason text,
          lwd_override_by_phone text,
          settlement_gate text NOT NULL DEFAULT 'not_required',
          settlement_run_id uuid,
          settlement_finalized boolean NOT NULL DEFAULT false,
          settlement_acknowledged boolean NOT NULL DEFAULT false,
          settlement_waived boolean NOT NULL DEFAULT false,
          payment_status text NOT NULL DEFAULT 'not_confirmed',
          access_gate text NOT NULL DEFAULT 'not_required',
          access_revoked_acked boolean NOT NULL DEFAULT false,
          access_waived boolean NOT NULL DEFAULT false,
          interview_gate text NOT NULL DEFAULT 'not_required',
          security_boundary jsonb NOT NULL DEFAULT '{}'::jsonb,
          created_by_phone text NOT NULL,
          closed_by_phone text,
          closed_at timestamptz,
          cancelled_by_phone text,
          cancelled_at timestamptz,
          decision_note text,
          created_at timestamptz NOT NULL DEFAULT now(),
          updated_at timestamptz NOT NULL DEFAULT now(),
          metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
          CONSTRAINT exit_close_cases_status_chk
            CHECK (status IN (
              'pending_close','ready_to_close','closed','blocked','cancelled'
            )),
          CONSTRAINT exit_close_cases_sett_chk
            CHECK (settlement_gate IN (
              'not_required','awaiting_finalized','finalized_awaiting_ack',
              'acknowledged','waived'
            )),
          CONSTRAINT exit_close_cases_pay_chk
            CHECK (payment_status IN ('unknown','not_confirmed','confirmed')),
          CONSTRAINT exit_close_cases_ob_uq UNIQUE (company_code, offboarding_case_id)
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS exit_interviews (
          interview_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
          company_code text NOT NULL,
          employee_key text NOT NULL,
          close_id uuid,
          status text NOT NULL DEFAULT 'invited',
          structured_reasons jsonb NOT NULL DEFAULT '[]'::jsonb,
          notes text,
          response_lang text NOT NULL DEFAULT 'en',
          confidential boolean NOT NULL DEFAULT true,
          invited_by_phone text,
          responded_by_phone text,
          responded_at timestamptz,
          created_at timestamptz NOT NULL DEFAULT now(),
          updated_at timestamptz NOT NULL DEFAULT now(),
          CONSTRAINT exit_interviews_status_chk
            CHECK (status IN ('invited','completed','declined','skipped'))
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS employment_alumni_episodes (
          episode_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
          company_code text NOT NULL,
          employee_key text NOT NULL,
          person_key text NOT NULL,
          close_id uuid NOT NULL,
          exit_type text,
          exit_reason text,
          hire_date date,
          last_working_day date,
          rehire_eligibility text NOT NULL DEFAULT 'eligible',
          rehire_reason text,
          rehire_set_by_phone text,
          rehire_set_at timestamptz,
          employment_snapshot jsonb NOT NULL DEFAULT '{}'::jsonb,
          created_at timestamptz NOT NULL DEFAULT now(),
          CONSTRAINT employment_alumni_rehire_chk
            CHECK (rehire_eligibility IN ('eligible','not_eligible','review_required')),
          CONSTRAINT employment_alumni_close_uq UNIQUE (close_id)
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS exit_close_c5_audit (
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
    reason: str | None = None,
    subject_type: str | None = None,
    subject_id: str | None = None,
    payload: dict[str, Any] | None = None,
) -> None:
    cur.execute(
        """
        INSERT INTO exit_close_c5_audit (
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
    ensure_exit_close_c5_schema(cur)
    cur.execute(
        "SELECT * FROM exit_close_c5_company_settings WHERE company_code=%s",
        (company_code_norm(company_code),),
    )
    row = cur.fetchone()
    return dict(row) if row else None


def enable_company_exit_close(
    cur: Any,
    *,
    company_code: str,
    actor_phone: str,
    reason: str,
    require_offboarding_complete: bool = True,
    require_last_working_day_reached: bool = True,
    allow_lwd_override: bool = True,
    require_settlement_ack: bool = False,
    allow_settlement_waiver: bool = True,
    require_access_revoke_ack: bool = False,
    exit_interview_enabled: bool = False,
    exit_interview_required: bool = False,
    require_distinct_closer: bool = True,
    default_rehire_eligibility: str = "eligible",
) -> dict[str, Any]:
    if not str(reason or "").strip():
        return {"ok": False, "error": "audit_reason_required"}
    dark = assert_real_termination_dark()
    if not dark.get("ok"):
        return dark
    gate = runtime_gate_for_company(company_code)
    if not gate.get("ok"):
        return gate
    if default_rehire_eligibility not in (REHIRE_ELIGIBLE, REHIRE_NOT, REHIRE_REVIEW):
        return {"ok": False, "error": "invalid_rehire_eligibility"}
    if exit_interview_required and not exit_interview_enabled:
        return {"ok": False, "error": "exit_interview_required_needs_enabled"}
    company = company_code_norm(company_code)
    ensure_exit_close_c5_schema(cur)
    cur.execute(
        """
        INSERT INTO exit_close_c5_company_settings (
          company_code, enabled, require_offboarding_complete, require_last_working_day_reached,
          allow_lwd_override, require_settlement_ack, allow_settlement_waiver,
          require_access_revoke_ack, exit_interview_enabled, exit_interview_required,
          require_distinct_closer, default_rehire_eligibility,
          enabled_by_phone, enabled_reason, enabled_at, updated_by_phone, updated_at, disabled_at
        ) VALUES (%s,true,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,now(),%s,now(),NULL)
        ON CONFLICT (company_code) DO UPDATE SET
          enabled=true,
          require_offboarding_complete=EXCLUDED.require_offboarding_complete,
          require_last_working_day_reached=EXCLUDED.require_last_working_day_reached,
          allow_lwd_override=EXCLUDED.allow_lwd_override,
          require_settlement_ack=EXCLUDED.require_settlement_ack,
          allow_settlement_waiver=EXCLUDED.allow_settlement_waiver,
          require_access_revoke_ack=EXCLUDED.require_access_revoke_ack,
          exit_interview_enabled=EXCLUDED.exit_interview_enabled,
          exit_interview_required=EXCLUDED.exit_interview_required,
          require_distinct_closer=EXCLUDED.require_distinct_closer,
          default_rehire_eligibility=EXCLUDED.default_rehire_eligibility,
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
            bool(require_offboarding_complete),
            bool(require_last_working_day_reached),
            bool(allow_lwd_override),
            bool(require_settlement_ack),
            bool(allow_settlement_waiver),
            bool(require_access_revoke_ack),
            bool(exit_interview_enabled),
            bool(exit_interview_required),
            bool(require_distinct_closer),
            default_rehire_eligibility,
            _digits(actor_phone),
            str(reason).strip()[:500],
            _digits(actor_phone),
        ),
    )
    row = dict(cur.fetchone())
    _audit(
        cur,
        company_code=company,
        action="enable_exit_close",
        actor_phone=actor_phone,
        reason=reason,
        subject_type="company",
        subject_id=company,
        payload={
            "require_settlement_ack": require_settlement_ack,
            "exit_interview_enabled": exit_interview_enabled,
        },
    )
    return {"ok": True, "company": row, **honesty_payload(company_code=company)}


def disable_company_exit_close(
    cur: Any,
    *,
    company_code: str,
    actor_phone: str,
    reason: str,
) -> dict[str, Any]:
    if not str(reason or "").strip():
        return {"ok": False, "error": "audit_reason_required"}
    company = company_code_norm(company_code)
    ensure_exit_close_c5_schema(cur)
    cur.execute(
        """
        UPDATE exit_close_c5_company_settings
           SET enabled=false, disabled_at=now(), updated_by_phone=%s, updated_at=now()
         WHERE company_code=%s
         RETURNING *
        """,
        (_digits(actor_phone), company),
    )
    row = cur.fetchone()
    _audit(
        cur,
        company_code=company,
        action="disable_exit_close",
        actor_phone=actor_phone,
        reason=reason,
        subject_type="company",
        subject_id=company,
    )
    return {
        "ok": True,
        "company": dict(row) if row else None,
        "history_preserved": True,
        **honesty_payload(company_code=company),
    }


def module_enabled_for_company(cur: Any, company_code: str | None) -> dict[str, Any]:
    dark = assert_real_termination_dark()
    if not dark.get("ok"):
        return dark
    gate = runtime_gate_for_company(company_code)
    if not gate.get("ok"):
        return gate
    settings = get_company_settings(cur, company_code)
    if not settings or not settings.get("enabled"):
        return {
            "ok": False,
            "enabled": False,
            "error": "exit_close_not_enabled",
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


def feature_visibility(cur: Any, company_code: str | None) -> dict[str, Any]:
    gate = runtime_gate_for_company(company_code)
    settings = get_company_settings(cur, company_code) if gate.get("ok") else None
    enabled = bool(gate.get("ok") and settings and settings.get("enabled"))
    return {
        "ok": True,
        "module_enabled": enabled,
        "exit_interview_visible": bool(enabled and settings and settings.get("exit_interview_enabled")),
        "settlement_ack_visible": bool(enabled and settings and settings.get("require_settlement_ack")),
        "assistant_mutations": False,
        **honesty_payload(company_code=company_code),
    }


def _decorate_close(row: dict[str, Any]) -> dict[str, Any]:
    out = dict(row)
    out["status_label_en"] = status_label(out.get("status"), lang="en")
    out["status_label_ar"] = status_label(out.get("status"), lang="ar")
    out["settlement_gate_label_en"] = status_label(out.get("settlement_gate"), lang="en")
    out["settlement_gate_label_ar"] = status_label(out.get("settlement_gate"), lang="ar")
    out["distinctions"] = {
        "settlement_finalized": bool(out.get("settlement_finalized")),
        "settlement_acknowledged": bool(out.get("settlement_acknowledged")),
        "settlement_waived": bool(out.get("settlement_waived")),
        "payment_status": out.get("payment_status"),
        "payment_confirmed": out.get("payment_status") == PAY_CONFIRMED,
        "finalized_equals_paid": False,
        "ack_equals_paid": False,
    }
    return out


def get_close_case(cur: Any, *, company_code: str, close_id: str) -> dict[str, Any] | None:
    ensure_exit_close_c5_schema(cur)
    cur.execute(
        "SELECT * FROM exit_close_cases WHERE company_code=%s AND close_id=%s",
        (company_code_norm(company_code), str(close_id)),
    )
    row = cur.fetchone()
    return _decorate_close(dict(row)) if row else None


def get_close_by_offboarding(
    cur: Any, *, company_code: str, offboarding_case_id: str
) -> dict[str, Any] | None:
    ensure_exit_close_c5_schema(cur)
    if not offboarding_case_id or str(offboarding_case_id) in ("None", "null"):
        return None
    cur.execute(
        """
        SELECT * FROM exit_close_cases
         WHERE company_code=%s AND offboarding_case_id=%s
        """,
        (company_code_norm(company_code), str(offboarding_case_id)),
    )
    row = cur.fetchone()
    return _decorate_close(dict(row)) if row else None


def _load_offboarding(cur: Any, *, company_code: str, offboarding_case_id: str) -> dict[str, Any] | None:
    cur.execute("SELECT to_regclass('public.offboarding_cases') AS t")
    if not dict(cur.fetchone()).get("t"):
        return None
    cur.execute(
        "SELECT * FROM offboarding_cases WHERE company_code=%s AND case_id=%s",
        (company_code_norm(company_code), str(offboarding_case_id)),
    )
    row = cur.fetchone()
    return dict(row) if row else None


def _employee_row(cur: Any, *, company_code: str, employee_key: str) -> dict[str, Any] | None:
    cur.execute(
        """
        SELECT employee_key, company_code, name, phone, profile, employment_status,
               hire_date, start_date
          FROM employees
         WHERE company_code=%s AND employee_key=%s
         LIMIT 1
        """,
        (company_code_norm(company_code), employee_key),
    )
    row = cur.fetchone()
    return dict(row) if row else None


def open_exit_close_from_offboarding(
    cur: Any,
    *,
    company_code: str,
    offboarding_case_id: str,
    actor_phone: str,
    reason: str = "open exit close",
) -> dict[str, Any]:
    if not str(reason or "").strip():
        return {"ok": False, "error": "audit_reason_required"}
    enabled = module_enabled_for_company(cur, company_code)
    if not enabled.get("ok"):
        return enabled
    settings = enabled["settings"]
    company = company_code_norm(company_code)

    existing = get_close_by_offboarding(
        cur, company_code=company, offboarding_case_id=offboarding_case_id
    )
    if existing:
        return {
            "ok": True,
            "case": existing,
            "duplicate_open": True,
            "created": False,
            "message": "Duplicate open is idempotent — one close authority per offboarding case.",
        }

    ob = _load_offboarding(cur, company_code=company, offboarding_case_id=offboarding_case_id)
    if not ob:
        return {"ok": False, "error": "offboarding_case_not_found"}
    if settings.get("require_offboarding_complete") and str(ob.get("status")) != "completed":
        return {
            "ok": False,
            "error": "offboarding_not_completed",
            "status": ob.get("status"),
            "message": "Incomplete required clearance/offboarding blocks close intake.",
        }
    employee_key = str(ob.get("employee_key"))
    synth = assert_synthetic_employee_key(employee_key)
    if not synth.get("ok"):
        return synth

    # Derive LWD from exit snapshot
    snap = ob.get("exit_snapshot") or {}
    if isinstance(snap, str):
        snap = json.loads(snap)
    lwd_raw = snap.get("last_working_day") or None
    lwd = None
    if lwd_raw:
        try:
            lwd = date.fromisoformat(str(lwd_raw)[:10])
        except Exception:
            lwd = None

    sett_gate = SETT_AWAITING_FINALIZED if settings.get("require_settlement_ack") else SETT_NOT_REQUIRED
    access_gate = "awaiting_ack" if settings.get("require_access_revoke_ack") else "not_required"
    interview_gate = (
        "required"
        if settings.get("exit_interview_enabled") and settings.get("exit_interview_required")
        else ("optional" if settings.get("exit_interview_enabled") else "not_required")
    )

    # If access already acked on offboarding case
    access_acked = bool(ob.get("access_revoked"))
    if access_gate == "awaiting_ack" and access_acked:
        access_gate = "acked"

    cur.execute(
        """
        INSERT INTO exit_close_cases (
          company_code, employee_key, offboarding_case_id, exit_intent_case_id, status,
          last_working_day, settlement_gate, access_gate, access_revoked_acked,
          interview_gate, payment_status, created_by_phone
        ) VALUES (%s,%s,%s,%s,'pending_close',%s,%s,%s,%s,%s,'not_confirmed',%s)
        RETURNING *
        """,
        (
            company,
            employee_key,
            offboarding_case_id,
            ob.get("exit_intent_case_id"),
            lwd,
            sett_gate,
            access_gate,
            access_acked,
            interview_gate,
            _digits(actor_phone),
        ),
    )
    case = dict(cur.fetchone())
    close_id = str(case["close_id"])

    if settings.get("exit_interview_enabled"):
        invite_exit_interview(
            cur,
            company_code=company,
            close_id=close_id,
            actor_phone=actor_phone,
            reason="auto-invite on close open",
        )

    evaluated = evaluate_close_readiness(cur, company_code=company, close_id=close_id)
    _audit(
        cur,
        company_code=company,
        action="exit_close_opened",
        actor_phone=actor_phone,
        reason=reason,
        subject_type="exit_close_case",
        subject_id=close_id,
        payload={"offboarding_case_id": str(offboarding_case_id)},
    )
    return {
        "ok": True,
        "case": evaluated.get("case") or _decorate_close(case),
        "created": True,
        "duplicate_open": False,
        "readiness": evaluated.get("readiness"),
        **honesty_payload(company_code=company),
    }


def evaluate_close_readiness(cur: Any, *, company_code: str, close_id: str) -> dict[str, Any]:
    enabled = module_enabled_for_company(cur, company_code)
    if not enabled.get("ok"):
        return enabled
    settings = enabled["settings"]
    case = get_close_case(cur, company_code=company_code, close_id=close_id)
    if not case:
        return {"ok": False, "error": "close_case_not_found"}
    if case.get("status") in (ST_CLOSED, ST_CANCELLED):
        return {"ok": True, "case": case, "readiness": {"ready": case.get("status") == ST_CLOSED, "terminal": True}}

    blockers: list[str] = []

    # Offboarding complete gate
    if settings.get("require_offboarding_complete"):
        ob = _load_offboarding(
            cur, company_code=company_code, offboarding_case_id=str(case["offboarding_case_id"])
        )
        if not ob or str(ob.get("status")) != "completed":
            blockers.append("offboarding_incomplete")

    # LWD gate
    if settings.get("require_last_working_day_reached"):
        lwd = case.get("last_working_day")
        if isinstance(lwd, datetime):
            lwd = lwd.date()
        if lwd and not case.get("lwd_override") and date.today() < lwd:
            blockers.append("last_working_day_not_reached")

    # Settlement gate
    sg = str(case.get("settlement_gate") or SETT_NOT_REQUIRED)
    if sg in (SETT_AWAITING_FINALIZED, SETT_FINALIZED_AWAITING_ACK):
        blockers.append(f"settlement_{sg}")
    # acknowledged/waived/not_required OK

    # Access gate
    ag = str(case.get("access_gate") or "not_required")
    if ag == "awaiting_ack" and not case.get("access_revoked_acked") and not case.get("access_waived"):
        blockers.append("access_revoke_ack_missing")

    # Interview gate (only if required)
    if str(case.get("interview_gate")) == "required":
        cur.execute(
            """
            SELECT status FROM exit_interviews
             WHERE company_code=%s AND close_id=%s
             ORDER BY created_at DESC LIMIT 1
            """,
            (company_code_norm(company_code), close_id),
        )
        iv = cur.fetchone()
        if not iv or str(dict(iv).get("status")) not in (
            INTERVIEW_COMPLETED,
            INTERVIEW_DECLINED,
            INTERVIEW_SKIPPED,
        ):
            blockers.append("exit_interview_required_unsatisfied")

    new_status = ST_READY if not blockers else ST_BLOCKED
    # pending_close stays until first eval moves to ready/blocked
    if case.get("status") == ST_PENDING and not blockers:
        new_status = ST_READY
    elif case.get("status") == ST_PENDING and blockers:
        new_status = ST_BLOCKED

    cur.execute(
        """
        UPDATE exit_close_cases
           SET status=%s,
               blocked_reasons=%s::jsonb,
               row_version = row_version + 1,
               updated_at=now()
         WHERE company_code=%s AND close_id=%s
           AND status NOT IN ('closed','cancelled')
        RETURNING *
        """,
        (
            new_status,
            json.dumps(blockers),
            company_code_norm(company_code),
            close_id,
        ),
    )
    row = cur.fetchone()
    return {
        "ok": True,
        "case": _decorate_close(dict(row)) if row else case,
        "readiness": {"ready": len(blockers) == 0, "blockers": blockers},
    }


def override_last_working_day_gate(
    cur: Any,
    *,
    company_code: str,
    close_id: str,
    actor_phone: str,
    reason: str,
    actor_role: str = "hr",
) -> dict[str, Any]:
    if not str(reason or "").strip():
        return {"ok": False, "error": "audit_reason_required"}
    enabled = module_enabled_for_company(cur, company_code)
    if not enabled.get("ok"):
        return enabled
    if not enabled["settings"].get("allow_lwd_override"):
        return {"ok": False, "error": "lwd_override_disabled"}
    if str(actor_role).lower() != "hr":
        return {"ok": False, "error": "lwd_override_hr_only"}
    cur.execute(
        """
        UPDATE exit_close_cases
           SET lwd_override=true,
               lwd_override_reason=%s,
               lwd_override_by_phone=%s,
               row_version=row_version+1,
               updated_at=now()
         WHERE company_code=%s AND close_id=%s AND status NOT IN ('closed','cancelled')
        RETURNING *
        """,
        (str(reason).strip()[:500], _digits(actor_phone), company_code_norm(company_code), close_id),
    )
    row = cur.fetchone()
    if not row:
        return {"ok": False, "error": "close_case_not_found_or_terminal"}
    _audit(
        cur,
        company_code=company_code,
        action="lwd_gate_overridden",
        actor_phone=actor_phone,
        reason=reason,
        subject_type="exit_close_case",
        subject_id=str(close_id),
    )
    return evaluate_close_readiness(cur, company_code=company_code, close_id=close_id)


def bind_wave2_settlement_finalized(
    cur: Any,
    *,
    company_code: str,
    close_id: str,
    settlement_run_id: str,
    actor_phone: str,
    reason: str,
) -> dict[str, Any]:
    """Consume frozen Wave 2 settlement authority — do not invent rows."""
    if not str(reason or "").strip():
        return {"ok": False, "error": "audit_reason_required"}
    enabled = module_enabled_for_company(cur, company_code)
    if not enabled.get("ok"):
        return enabled
    case = get_close_case(cur, company_code=company_code, close_id=close_id)
    if not case:
        return {"ok": False, "error": "close_case_not_found"}
    if case.get("settlement_gate") == SETT_NOT_REQUIRED:
        return {"ok": False, "error": "settlement_not_required_for_company"}

    try:
        import payroll_settlement_ot_c6 as sett
    except Exception:
        return {"ok": False, "error": "payroll_settlement_module_unavailable"}

    run = sett.get_settlement(
        cur, company_code=company_code, settlement_id=str(settlement_run_id)
    )
    if not run:
        return {
            "ok": False,
            "error": "settlement_run_not_found",
            "message": "Never manufacture a fake settlement row to unblock closure.",
        }
    if str(run.get("status")) != "finalized":
        return {
            "ok": False,
            "error": "settlement_not_finalized",
            "status": run.get("status"),
        }
    if bool(run.get("claims_paid")):
        # Wave 2 honesty: claims_paid must stay false; refuse if violated
        return {"ok": False, "error": "settlement_claims_paid_forbidden"}
    if str(run.get("employee_key")) != str(case.get("employee_key")):
        return {"ok": False, "error": "settlement_employee_mismatch"}

    cur.execute(
        """
        UPDATE exit_close_cases
           SET settlement_run_id=%s,
               settlement_finalized=true,
               settlement_gate='finalized_awaiting_ack',
               settlement_acknowledged=false,
               payment_status='not_confirmed',
               row_version=row_version+1,
               updated_at=now()
         WHERE company_code=%s AND close_id=%s
        RETURNING *
        """,
        (settlement_run_id, company_code_norm(company_code), close_id),
    )
    row = dict(cur.fetchone())
    _audit(
        cur,
        company_code=company_code,
        action="settlement_finalized_bound",
        actor_phone=actor_phone,
        reason=reason,
        subject_type="exit_close_case",
        subject_id=str(close_id),
        payload={
            "settlement_run_id": str(settlement_run_id),
            "settlement_finalized_is_not_paid": True,
            "payment_status": "not_confirmed",
        },
    )
    evaluated = evaluate_close_readiness(cur, company_code=company_code, close_id=close_id)
    return {
        "ok": True,
        "case": evaluated.get("case") or _decorate_close(row),
        "settlement_finalized": True,
        "settlement_acknowledged": False,
        "payment_status": PAY_NOT_CONFIRMED,
        "finalized_equals_paid": False,
    }


def acknowledge_settlement(
    cur: Any,
    *,
    company_code: str,
    close_id: str,
    actor_phone: str,
    reason: str,
    actor_role: str = "hr",
) -> dict[str, Any]:
    if not str(reason or "").strip():
        return {"ok": False, "error": "audit_reason_required"}
    enabled = module_enabled_for_company(cur, company_code)
    if not enabled.get("ok"):
        return enabled
    case = get_close_case(cur, company_code=company_code, close_id=close_id)
    if not case:
        return {"ok": False, "error": "close_case_not_found"}
    if not case.get("settlement_finalized"):
        return {
            "ok": False,
            "error": "settlement_finalized_required_before_ack",
            "settlement_gate": case.get("settlement_gate"),
        }
    cur.execute(
        """
        UPDATE exit_close_cases
           SET settlement_acknowledged=true,
               settlement_gate='acknowledged',
               payment_status='not_confirmed',
               row_version=row_version+1,
               updated_at=now()
         WHERE company_code=%s AND close_id=%s
        RETURNING *
        """,
        (company_code_norm(company_code), close_id),
    )
    row = dict(cur.fetchone())
    _audit(
        cur,
        company_code=company_code,
        action="settlement_acknowledged",
        actor_phone=actor_phone,
        reason=reason,
        subject_type="exit_close_case",
        subject_id=str(close_id),
        payload={"ack_equals_paid": False, "actor_role": actor_role},
    )
    return evaluate_close_readiness(cur, company_code=company_code, close_id=close_id)


def waive_settlement(
    cur: Any,
    *,
    company_code: str,
    close_id: str,
    actor_phone: str,
    actor_role: str,
    reason: str,
) -> dict[str, Any]:
    if not str(reason or "").strip():
        return {"ok": False, "error": "audit_reason_required"}
    enabled = module_enabled_for_company(cur, company_code)
    if not enabled.get("ok"):
        return enabled
    settings = enabled["settings"]
    if not settings.get("allow_settlement_waiver"):
        return {"ok": False, "error": "settlement_waiver_disabled"}
    roles = settings.get("settlement_waiver_roles") or ["hr"]
    if isinstance(roles, str):
        roles = json.loads(roles)
    if str(actor_role).lower() not in {str(r).lower() for r in roles}:
        return {
            "ok": False,
            "error": "unauthorized_settlement_waiver",
            "allowed_roles": list(roles),
        }
    cur.execute(
        """
        UPDATE exit_close_cases
           SET settlement_waived=true,
               settlement_gate='waived',
               payment_status='not_confirmed',
               row_version=row_version+1,
               updated_at=now(),
               decision_note=%s
         WHERE company_code=%s AND close_id=%s AND status NOT IN ('closed','cancelled')
        RETURNING *
        """,
        (str(reason).strip()[:500], company_code_norm(company_code), close_id),
    )
    row = cur.fetchone()
    if not row:
        return {"ok": False, "error": "close_case_not_found_or_terminal"}
    _audit(
        cur,
        company_code=company_code,
        action="settlement_waived",
        actor_phone=actor_phone,
        reason=reason,
        subject_type="exit_close_case",
        subject_id=str(close_id),
        payload={"actor_role": actor_role, "no_fake_settlement_row": True},
    )
    return evaluate_close_readiness(cur, company_code=company_code, close_id=close_id)


def acknowledge_access_revoke(
    cur: Any,
    *,
    company_code: str,
    close_id: str,
    actor_phone: str,
    reason: str,
) -> dict[str, Any]:
    if not str(reason or "").strip():
        return {"ok": False, "error": "audit_reason_required"}
    enabled = module_enabled_for_company(cur, company_code)
    if not enabled.get("ok"):
        return enabled
    cur.execute(
        """
        UPDATE exit_close_cases
           SET access_revoked_acked=true,
               access_gate='acked',
               row_version=row_version+1,
               updated_at=now()
         WHERE company_code=%s AND close_id=%s
        RETURNING *
        """,
        (company_code_norm(company_code), close_id),
    )
    row = cur.fetchone()
    if not row:
        return {"ok": False, "error": "close_case_not_found"}
    _audit(
        cur,
        company_code=company_code,
        action="access_revoke_acked",
        actor_phone=actor_phone,
        reason=reason,
        subject_type="exit_close_case",
        subject_id=str(close_id),
        payload={"requested_is_not_revoked_without_ack": True},
    )
    return evaluate_close_readiness(cur, company_code=company_code, close_id=close_id)


def waive_access_revoke(
    cur: Any,
    *,
    company_code: str,
    close_id: str,
    actor_phone: str,
    actor_role: str,
    reason: str,
) -> dict[str, Any]:
    if not str(reason or "").strip():
        return {"ok": False, "error": "audit_reason_required"}
    enabled = module_enabled_for_company(cur, company_code)
    if not enabled.get("ok"):
        return enabled
    roles = enabled["settings"].get("access_waiver_roles") or ["hr"]
    if isinstance(roles, str):
        roles = json.loads(roles)
    if str(actor_role).lower() not in {str(r).lower() for r in roles}:
        return {"ok": False, "error": "unauthorized_access_waiver", "allowed_roles": list(roles)}
    cur.execute(
        """
        UPDATE exit_close_cases
           SET access_waived=true,
               access_gate='waived',
               row_version=row_version+1,
               updated_at=now()
         WHERE company_code=%s AND close_id=%s
        RETURNING *
        """,
        (company_code_norm(company_code), close_id),
    )
    if not cur.fetchone():
        return {"ok": False, "error": "close_case_not_found"}
    _audit(
        cur,
        company_code=company_code,
        action="access_revoke_waived",
        actor_phone=actor_phone,
        reason=reason,
        subject_type="exit_close_case",
        subject_id=str(close_id),
    )
    return evaluate_close_readiness(cur, company_code=company_code, close_id=close_id)


def invite_exit_interview(
    cur: Any,
    *,
    company_code: str,
    close_id: str,
    actor_phone: str,
    reason: str = "invite",
) -> dict[str, Any]:
    enabled = module_enabled_for_company(cur, company_code)
    if not enabled.get("ok"):
        return enabled
    if not enabled["settings"].get("exit_interview_enabled"):
        return {"ok": False, "error": "exit_interview_disabled"}
    case = get_close_case(cur, company_code=company_code, close_id=close_id)
    if not case:
        return {"ok": False, "error": "close_case_not_found"}
    cur.execute(
        """
        INSERT INTO exit_interviews (
          company_code, employee_key, close_id, status, invited_by_phone, confidential
        ) VALUES (%s,%s,%s,'invited',%s,true)
        RETURNING *
        """,
        (
            company_code_norm(company_code),
            case["employee_key"],
            close_id,
            _digits(actor_phone),
        ),
    )
    row = dict(cur.fetchone())
    _audit(
        cur,
        company_code=company_code,
        action="exit_interview_invited",
        actor_phone=actor_phone,
        reason=reason,
        subject_type="exit_interview",
        subject_id=str(row["interview_id"]),
    )
    return {"ok": True, "interview": row}


def respond_exit_interview(
    cur: Any,
    *,
    company_code: str,
    interview_id: str,
    actor_phone: str,
    decision: str,
    structured_reasons: list[str] | None = None,
    notes: str | None = None,
    lang: str = "en",
) -> dict[str, Any]:
    enabled = module_enabled_for_company(cur, company_code)
    if not enabled.get("ok"):
        return enabled
    if not enabled["settings"].get("exit_interview_enabled"):
        return {"ok": False, "error": "exit_interview_disabled"}
    dec = str(decision or "").strip().lower()
    if dec not in (INTERVIEW_COMPLETED, INTERVIEW_DECLINED, INTERVIEW_SKIPPED):
        return {"ok": False, "error": "invalid_interview_decision"}
    lang_n = "ar" if str(lang).lower().startswith("ar") else "en"
    cur.execute(
        """
        UPDATE exit_interviews
           SET status=%s,
               structured_reasons=%s::jsonb,
               notes=%s,
               response_lang=%s,
               responded_by_phone=%s,
               responded_at=now(),
               updated_at=now()
         WHERE company_code=%s AND interview_id=%s AND status='invited'
        RETURNING *
        """,
        (
            dec,
            json.dumps(structured_reasons or [], default=str),
            notes,
            lang_n,
            _digits(actor_phone),
            company_code_norm(company_code),
            interview_id,
        ),
    )
    row = cur.fetchone()
    if not row:
        return {"ok": False, "error": "interview_not_found_or_not_invited"}
    d = dict(row)
    _audit(
        cur,
        company_code=company_code,
        action="exit_interview_responded",
        actor_phone=actor_phone,
        subject_type="exit_interview",
        subject_id=str(interview_id),
        payload={"status": dec, "confidential": True},
    )
    if d.get("close_id"):
        evaluate_close_readiness(
            cur, company_code=company_code, close_id=str(d["close_id"])
        )
    return {"ok": True, "interview": d, "wave5_fact": {"event": "exit_interview_submitted", "status": dec}}


def get_exit_interview(
    cur: Any,
    *,
    company_code: str,
    interview_id: str,
    actor_role: str = "hr",
) -> dict[str, Any]:
    ensure_exit_close_c5_schema(cur)
    cur.execute(
        "SELECT * FROM exit_interviews WHERE company_code=%s AND interview_id=%s",
        (company_code_norm(company_code), str(interview_id)),
    )
    row = cur.fetchone()
    if not row:
        return {"ok": False, "error": "interview_not_found"}
    d = dict(row)
    # Confidentiality: non-HR sees redacted notes
    if str(actor_role).lower() not in ("hr", "admin") and d.get("confidential"):
        d = {**d, "notes": "[redacted]", "structured_reasons": ["[redacted]"]}
    return {"ok": True, "interview": d}


def execute_exit_close(
    cur: Any,
    *,
    company_code: str,
    close_id: str,
    actor_phone: str,
    reason: str,
    expected_version: int | None = None,
    rehire_eligibility: str | None = None,
    rehire_reason: str | None = None,
) -> dict[str, Any]:
    """Irreversible boundary: set employment left/inactive. Sole authority."""
    if not str(reason or "").strip():
        return {"ok": False, "error": "audit_reason_required"}
    enabled = module_enabled_for_company(cur, company_code)
    if not enabled.get("ok"):
        return enabled
    settings = enabled["settings"]
    company = company_code_norm(company_code)

    existing = get_close_case(cur, company_code=company, close_id=close_id)
    if not existing:
        return {"ok": False, "error": "close_case_not_found"}
    if existing.get("status") == ST_CLOSED:
        return {
            "ok": True,
            "case": existing,
            "idempotent_duplicate_close": True,
            "employment_left": True,
            "message": "Duplicate close is idempotent.",
        }
    if expected_version is not None and int(existing.get("row_version") or 0) != int(expected_version):
        return {"ok": False, "error": "stale_row_version", "row_version": existing.get("row_version")}

    if settings.get("require_distinct_closer") and _digits(actor_phone) == _digits(
        existing.get("created_by_phone")
    ):
        return {"ok": False, "error": "sod_self_close_forbidden"}

    readiness = evaluate_close_readiness(cur, company_code=company, close_id=close_id)
    case = readiness.get("case") or existing
    if case.get("status") != ST_READY:
        return {
            "ok": False,
            "error": "not_ready_to_close",
            "status": case.get("status"),
            "blockers": (readiness.get("readiness") or {}).get("blockers"),
        }

    emp = _employee_row(cur, company_code=company, employee_key=str(case["employee_key"]))
    if not emp:
        return {"ok": False, "error": "employee_not_found"}
    status_now = str(emp.get("employment_status") or "").lower()
    if status_now in ("left", "terminated", "inactive"):
        # Already left somehow — refuse silent reopen path; allow idempotent align
        return {"ok": False, "error": "employment_already_inactive", "status": status_now}

    profile = emp.get("profile") or {}
    if isinstance(profile, str):
        try:
            profile = json.loads(profile)
        except Exception:
            profile = {}
    lwd = case.get("last_working_day") or date.today()
    if isinstance(lwd, datetime):
        lwd = lwd.date()

    # Security boundary contract (synthetic — no real session revoke in C5 qualify)
    security = {
        "contract": "exit_close.security_boundary",
        "effective_at": datetime.utcnow().isoformat() + "Z",
        "synthetic_only": True,
        "real_user_revoke": False,
        "app_sessions_invalid_after_boundary": True,
        "idp_optional": True,
        "requested_is_not_revoked_without_ack": True,
        "actor_phone": _digits(actor_phone),
    }

    # Canonical employment → left (sole writer)
    cur.execute(
        """
        UPDATE employees
           SET employment_status='left',
               profile = COALESCE(profile,'{}'::jsonb) || %s::jsonb,
               updated_at=now()
         WHERE company_code=%s AND employee_key=%s AND employment_status NOT IN ('left','terminated','inactive')
        RETURNING employee_key, employment_status, profile
        """,
        (
            json.dumps(
                {
                    "exit_closed_at": datetime.utcnow().isoformat() + "Z",
                    "exit_close_id": str(close_id),
                    "last_working_day": str(lwd),
                    "exit_reason": reason,
                    "active_headcount": False,
                    "workforce_domains": {
                        "attendance_active": False,
                        "leave_active": False,
                        "shifts_active": False,
                        "new_payroll_period_active": False,
                    },
                },
                default=str,
            ),
            company,
            case["employee_key"],
        ),
    )
    emp_updated = cur.fetchone()
    if not emp_updated:
        return {"ok": False, "error": "employment_transition_failed"}

    cur.execute(
        """
        UPDATE exit_close_cases
           SET status='closed',
               closed_by_phone=%s,
               closed_at=now(),
               decision_note=%s,
               security_boundary=%s::jsonb,
               row_version=row_version+1,
               updated_at=now()
         WHERE company_code=%s AND close_id=%s AND status='ready_to_close'
           AND (%s::int IS NULL OR row_version=%s)
        RETURNING *
        """,
        (
            _digits(actor_phone),
            str(reason).strip()[:500],
            json.dumps(security, default=str),
            company,
            close_id,
            expected_version,
            expected_version,
        ),
    )
    closed_row = cur.fetchone()
    if not closed_row:
        return {"ok": False, "error": "stale_close_rejected"}

    # Alumni episode
    rehire = rehire_eligibility or settings.get("default_rehire_eligibility") or REHIRE_ELIGIBLE
    if rehire not in (REHIRE_ELIGIBLE, REHIRE_NOT, REHIRE_REVIEW):
        rehire = REHIRE_ELIGIBLE
    person_key = str(profile.get("person_id") or profile.get("person_key") or case["employee_key"])
    snap = {
        "name": emp.get("name"),
        "phone": emp.get("phone"),
        "hire_date": str(emp.get("hire_date") or emp.get("start_date") or ""),
        "last_working_day": str(lwd),
        "profile": profile,
        "close_id": str(close_id),
    }
    # exit type from offboarding snapshot
    ob = _load_offboarding(
        cur, company_code=company, offboarding_case_id=str(case["offboarding_case_id"])
    )
    exit_snap = (ob or {}).get("exit_snapshot") or {}
    if isinstance(exit_snap, str):
        exit_snap = json.loads(exit_snap)
    cur.execute(
        """
        INSERT INTO employment_alumni_episodes (
          company_code, employee_key, person_key, close_id, exit_type, exit_reason,
          hire_date, last_working_day, rehire_eligibility, rehire_reason,
          rehire_set_by_phone, rehire_set_at, employment_snapshot
        ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,now(),%s::jsonb)
        ON CONFLICT (close_id) DO NOTHING
        RETURNING *
        """,
        (
            company,
            case["employee_key"],
            person_key,
            close_id,
            exit_snap.get("exit_type"),
            reason,
            emp.get("hire_date") or emp.get("start_date"),
            lwd,
            rehire,
            rehire_reason,
            _digits(actor_phone),
            json.dumps(snap, default=str),
        ),
    )
    alumni = cur.fetchone()
    if not alumni:
        cur.execute(
            "SELECT * FROM employment_alumni_episodes WHERE close_id=%s",
            (close_id,),
        )
        alumni = cur.fetchone()

    _audit(
        cur,
        company_code=company,
        action="exit_closed",
        actor_phone=actor_phone,
        reason=reason,
        subject_type="exit_close_case",
        subject_id=str(close_id),
        payload={
            "employment_status": "left",
            "security_boundary": security,
            "rehire_eligibility": rehire,
            "payment_status": case.get("payment_status"),
        },
    )
    return {
        "ok": True,
        "case": _decorate_close(dict(closed_row)),
        "employment_status": "left",
        "alumni": dict(alumni) if alumni else None,
        "security_boundary": security,
        "active_workforce": {
            "attendance_active": False,
            "leave_active": False,
            "shifts_active": False,
            "new_payroll_period_active": False,
        },
        "idempotent_duplicate_close": False,
        **honesty_payload(company_code=company),
    }


def set_rehire_eligibility(
    cur: Any,
    *,
    company_code: str,
    close_id: str,
    actor_phone: str,
    eligibility: str,
    reason: str,
) -> dict[str, Any]:
    if not str(reason or "").strip():
        return {"ok": False, "error": "audit_reason_required"}
    enabled = module_enabled_for_company(cur, company_code)
    if not enabled.get("ok"):
        return enabled
    if eligibility not in (REHIRE_ELIGIBLE, REHIRE_NOT, REHIRE_REVIEW):
        return {"ok": False, "error": "invalid_rehire_eligibility"}
    cur.execute(
        """
        UPDATE employment_alumni_episodes
           SET rehire_eligibility=%s,
               rehire_reason=%s,
               rehire_set_by_phone=%s,
               rehire_set_at=now()
         WHERE company_code=%s AND close_id=%s
        RETURNING *
        """,
        (
            eligibility,
            str(reason).strip()[:500],
            _digits(actor_phone),
            company_code_norm(company_code),
            close_id,
        ),
    )
    row = cur.fetchone()
    if not row:
        return {"ok": False, "error": "alumni_episode_not_found"}
    _audit(
        cur,
        company_code=company_code,
        action="rehire_eligibility_set",
        actor_phone=actor_phone,
        reason=reason,
        subject_type="alumni_episode",
        subject_id=str(dict(row)["episode_id"]),
        payload={"eligibility": eligibility},
    )
    return {"ok": True, "alumni": dict(row)}


def attempt_reopen_closed_employment(
    cur: Any,
    *,
    company_code: str,
    employee_key: str,
) -> dict[str, Any]:
    """Honesty prove — no silent reopen; use explicit rehire/amendment later."""
    emp = _employee_row(cur, company_code=company_code, employee_key=employee_key)
    if not emp:
        return {"ok": False, "error": "employee_not_found"}
    if str(emp.get("employment_status") or "").lower() in ("left", "terminated", "inactive"):
        return {
            "ok": False,
            "error": "silent_reopen_forbidden",
            "message": "Closed employment cannot be silently reopened. Use audited rehire / lifecycle amendment.",
            "status": emp.get("employment_status"),
        }
    return {"ok": False, "error": "employment_not_closed"}


def cancel_exit_close(
    cur: Any,
    *,
    company_code: str,
    close_id: str,
    actor_phone: str,
    reason: str,
    expected_version: int | None = None,
) -> dict[str, Any]:
    if not str(reason or "").strip():
        return {"ok": False, "error": "audit_reason_required"}
    enabled = module_enabled_for_company(cur, company_code)
    if not enabled.get("ok"):
        return enabled
    cur.execute(
        """
        UPDATE exit_close_cases
           SET status='cancelled',
               cancelled_by_phone=%s,
               cancelled_at=now(),
               decision_note=%s,
               row_version=row_version+1,
               updated_at=now()
         WHERE company_code=%s AND close_id=%s
           AND status NOT IN ('closed','cancelled')
           AND (%s::int IS NULL OR row_version=%s)
        RETURNING *
        """,
        (
            _digits(actor_phone),
            str(reason).strip()[:500],
            company_code_norm(company_code),
            close_id,
            expected_version,
            expected_version,
        ),
    )
    row = cur.fetchone()
    if not row:
        return {"ok": False, "error": "stale_or_terminal"}
    _audit(
        cur,
        company_code=company_code,
        action="exit_close_cancelled",
        actor_phone=actor_phone,
        reason=reason,
        subject_type="exit_close_case",
        subject_id=str(close_id),
    )
    return {"ok": True, "case": _decorate_close(dict(row))}


def is_active_for_workforce(cur: Any, *, company_code: str, employee_key: str) -> dict[str, Any]:
    """Active-headcount semantics for Attendance/Leave/Shifts/Payroll period participation."""
    emp = _employee_row(cur, company_code=company_code, employee_key=employee_key)
    if not emp:
        return {"ok": False, "active": False, "error": "employee_not_found"}
    status = str(emp.get("employment_status") or "").lower()
    active = status in ("active", "notice_period", "pending_start")
    profile = emp.get("profile") or {}
    if isinstance(profile, str):
        try:
            profile = json.loads(profile)
        except Exception:
            profile = {}
    domains = profile.get("workforce_domains") or {}
    if status in ("left", "terminated", "inactive"):
        active = False
        domains = {
            "attendance_active": False,
            "leave_active": False,
            "shifts_active": False,
            "new_payroll_period_active": False,
        }
    return {
        "ok": True,
        "active": active,
        "employment_status": status,
        "workforce_domains": domains,
    }
