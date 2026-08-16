#!/usr/bin/env python3
"""Wave 3 C3 — Exit intent: resignation / termination / EOC (synthetic).

Owner-approved under WAVE3_EMPLOYEE_LIFECYCLE_CHARTER.
C2 ESS_LETTERS_DEPENDENTS_FULL_PASS ACCEPTED/frozen before this slice.

Canonical exit-intent SM:
  draft → submitted → pending_approval → approved → notice_period → ready_for_offboarding
  (+ rejected | withdrawn | cancelled)

Types: resignation | termination | end_of_contract

C3 ends at ready_for_offboarding / approved exit intent.
Does NOT: clearance, access revoke, settlement finalize, employment=left/terminated,
invent statutory notice/EOS, Assistant mutations, real non-synthetic termination.

Gates (fail-closed):
  1) WATHEFNI_RESIGNATION_ESS_C3 must be on
  2) company in WATHEFNI_RESIGNATION_ESS_COMPANIES (empty = nobody)
  3) company entitlement in exit_intent_c3_company_settings
  4) WATHEFNI_REAL_TERMINATION_CANARY must remain off (dark)
  5) synthetic markers required for mutation subjects
"""
from __future__ import annotations

import json
import os
import uuid
from datetime import date, datetime, timedelta
from typing import Any

PHASE = "exit_intent_c3"
CONTRACT_VERSION = "exit_intent_c3_v1"
PASS_STAMP = "RESIGNATION_TERMINATION_FULL_PASS"
_ON = {"1", "true", "yes", "on"}

EXIT_TYPES = ("resignation", "termination", "end_of_contract")

ST_DRAFT = "draft"
ST_SUBMITTED = "submitted"
ST_PENDING = "pending_approval"
ST_APPROVED = "approved"
ST_NOTICE = "notice_period"
ST_READY = "ready_for_offboarding"
ST_REJECTED = "rejected"
ST_WITHDRAWN = "withdrawn"
ST_CANCELLED = "cancelled"

STATUSES = (
    ST_DRAFT,
    ST_SUBMITTED,
    ST_PENDING,
    ST_APPROVED,
    ST_NOTICE,
    ST_READY,
    ST_REJECTED,
    ST_WITHDRAWN,
    ST_CANCELLED,
)

TERMINAL = {ST_REJECTED, ST_WITHDRAWN, ST_CANCELLED, ST_READY}
WITHDRAWABLE = {ST_DRAFT, ST_SUBMITTED, ST_PENDING, ST_APPROVED}
# Irreversible boundary for employee withdraw = entering notice_period

TERMINATION_CATEGORIES = (
    "performance",
    "misconduct",
    "redundancy",
    "probation_fail",
    "other",
)

STATUS_LABELS = {
    "draft": {"en": "Draft", "ar": "مسودة"},
    "submitted": {"en": "Submitted", "ar": "مُقدَّم"},
    "pending_approval": {"en": "Pending approval", "ar": "بانتظار الاعتماد"},
    "approved": {"en": "Approved", "ar": "معتمد"},
    "notice_period": {"en": "Notice period", "ar": "فترة الإشعار"},
    "ready_for_offboarding": {"en": "Ready for offboarding", "ar": "جاهز لإنهاء الخدمة"},
    "rejected": {"en": "Rejected", "ar": "مرفوض"},
    "withdrawn": {"en": "Withdrawn", "ar": "منسحب"},
    "cancelled": {"en": "Cancelled", "ar": "ملغى"},
    "resignation": {"en": "Resignation", "ar": "استقالة"},
    "termination": {"en": "Termination", "ar": "إنهاء خدمة"},
    "end_of_contract": {"en": "End of contract", "ar": "انتهاء العقد"},
    "renewed": {"en": "Renewed", "ar": "مُجدَّد"},
    "non_renewed": {"en": "Non-renewed", "ar": "غير مُجدَّد"},
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


def resignation_ess_c3_runtime_on() -> bool:
    return _env_on("WATHEFNI_RESIGNATION_ESS_C3", "off")


def real_termination_canary_on() -> bool:
    """Must remain OFF through C3. Dark until C6+ synthetic journey green."""
    return _env_on("WATHEFNI_REAL_TERMINATION_CANARY", "off")


def resignation_ess_company_allowlist() -> set[str]:
    raw = str(os.environ.get("WATHEFNI_RESIGNATION_ESS_COMPANIES") or "").strip()
    if not raw:
        return set()
    return {p.strip().upper() for p in raw.split(",") if p.strip()}


def synthetic_markers() -> tuple[str, ...]:
    raw = str(os.environ.get("WATHEFNI_EXIT_INTENT_SYNTHETIC_MARKERS") or "W3C3,EX3,EI3").strip()
    return tuple(p.strip() for p in raw.split(",") if p.strip())


def honesty_payload(*, company_code: str | None = None) -> dict[str, Any]:
    return {
        "phase": PHASE,
        "contract_version": CONTRACT_VERSION,
        "pass_stamp": PASS_STAMP,
        "assistant_mutations": False,
        "payroll_required": False,
        "offboarding_required": False,
        "clearance_in_c3": False,
        "access_revoke_in_c3": False,
        "settlement_finalize_in_c3": False,
        "employment_closed_on_approve": False,
        "invented_statutory_notice": False,
        "invented_eos_formulas": False,
        "real_termination_canary": real_termination_canary_on(),
        "real_termination_dark": not real_termination_canary_on(),
        "offboarding_handoff_optional": True,
        "company_code": company_code_norm(company_code) if company_code else None,
    }


def rollback_guidance() -> dict[str, Any]:
    return {
        "phase": PHASE,
        "steps": [
            "WATHEFNI_RESIGNATION_ESS_C3=off",
            "Clear WATHEFNI_RESIGNATION_ESS_COMPANIES",
            "WATHEFNI_REAL_TERMINATION_CANARY remains off",
            "disable_company_exit_intent(canary)",
            "Exit-intent case/notice history retained — employment truth not purged",
        ],
        "history_intact": True,
    }


def runtime_gate_for_company(company_code: str | None) -> dict[str, Any]:
    company = company_code_norm(company_code)
    if not company:
        return {"ok": False, "enabled": False, "error": "company_required", "phase": PHASE}
    if not resignation_ess_c3_runtime_on():
        return {
            "ok": False,
            "enabled": False,
            "error": "resignation_ess_c3_off",
            "gate": "runtime_flag",
            "phase": PHASE,
        }
    allow = resignation_ess_company_allowlist()
    if not allow:
        return {
            "ok": False,
            "enabled": False,
            "error": "resignation_ess_company_not_allowlisted",
            "gate": "company_allowlist",
            "phase": PHASE,
            "message": "Resignation/exit-intent allowlist empty — fail closed (nobody).",
        }
    if company not in allow:
        return {
            "ok": False,
            "enabled": False,
            "error": "resignation_ess_company_not_allowlisted",
            "gate": "company_allowlist",
            "phase": PHASE,
            "company_code": company,
        }
    return {"ok": True, "enabled": True, "company_code": company, "phase": PHASE}


def assert_real_termination_dark() -> dict[str, Any]:
    if real_termination_canary_on():
        return {
            "ok": False,
            "error": "real_termination_canary_must_remain_off_in_c3",
            "gate": "real_termination_canary",
            "phase": PHASE,
        }
    return {"ok": True, "real_termination_dark": True, "phase": PHASE}


def assert_synthetic_employee_key(employee_key: str) -> dict[str, Any]:
    key = str(employee_key or "")
    markers = synthetic_markers()
    if any(m and m in key for m in markers):
        return {"ok": True, "synthetic": True, "markers": list(markers)}
    return {
        "ok": False,
        "error": "non_synthetic_employee_blocked",
        "gate": "synthetic_only",
        "message": "C3 qualification mutates synthetic subjects only. Real termination remains dark.",
        "markers": list(markers),
        "phase": PHASE,
    }


def ensure_exit_intent_c3_schema(cur: Any, *, force: bool = False) -> None:
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS exit_intent_c3_company_settings (
          company_code text PRIMARY KEY,
          enabled boolean NOT NULL DEFAULT false,
          resignation_enabled boolean NOT NULL DEFAULT false,
          termination_enabled boolean NOT NULL DEFAULT false,
          eoc_enabled boolean NOT NULL DEFAULT false,
          require_distinct_approver boolean NOT NULL DEFAULT true,
          allow_employee_withdraw_before_notice boolean NOT NULL DEFAULT true,
          notice_policy_days int NOT NULL DEFAULT 30,
          notice_policy_source text NOT NULL DEFAULT 'company_setup',
          legal_pack_ref text,
          eoc_task_days_before int NOT NULL DEFAULT 30,
          offboarding_handoff_enabled boolean NOT NULL DEFAULT false,
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
        CREATE TABLE IF NOT EXISTS exit_intent_cases (
          case_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
          company_code text NOT NULL,
          employee_key text NOT NULL,
          exit_type text NOT NULL,
          status text NOT NULL DEFAULT 'draft',
          row_version int NOT NULL DEFAULT 1,
          reason text,
          reason_category text,
          requested_last_working_day date,
          effective_last_working_day date,
          notice_starts_on date,
          notice_ends_on date,
          employment_snapshot jsonb NOT NULL DEFAULT '{}'::jsonb,
          payload jsonb NOT NULL DEFAULT '{}'::jsonb,
          eoc_decision text,
          renewed_contract_end date,
          created_by_phone text NOT NULL,
          submitted_by_phone text,
          submitted_at timestamptz,
          pending_approver_role text,
          approved_by_phone text,
          approved_at timestamptz,
          rejected_by_phone text,
          rejected_at timestamptz,
          withdrawn_by_phone text,
          withdrawn_at timestamptz,
          cancelled_by_phone text,
          cancelled_at timestamptz,
          notice_entered_at timestamptz,
          ready_at timestamptz,
          decision_note text,
          handoff_id uuid,
          created_at timestamptz NOT NULL DEFAULT now(),
          updated_at timestamptz NOT NULL DEFAULT now(),
          metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
          CONSTRAINT exit_intent_cases_type_chk
            CHECK (exit_type IN ('resignation','termination','end_of_contract')),
          CONSTRAINT exit_intent_cases_status_chk
            CHECK (status IN (
              'draft','submitted','pending_approval','approved','notice_period',
              'ready_for_offboarding','rejected','withdrawn','cancelled'
            )),
          CONSTRAINT exit_intent_cases_eoc_decision_chk
            CHECK (eoc_decision IS NULL OR eoc_decision IN ('renewed','non_renewed'))
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS exit_intent_notice_versions (
          notice_version_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
          company_code text NOT NULL,
          case_id uuid NOT NULL,
          version_number int NOT NULL,
          notice_starts_on date NOT NULL,
          notice_ends_on date NOT NULL,
          last_working_day date NOT NULL,
          policy_days int,
          policy_source text NOT NULL DEFAULT 'company_setup',
          legal_pack_ref text,
          change_reason text NOT NULL,
          changed_by_phone text NOT NULL,
          created_at timestamptz NOT NULL DEFAULT now(),
          UNIQUE (case_id, version_number)
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS exit_intent_handoffs (
          handoff_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
          company_code text NOT NULL,
          case_id uuid NOT NULL,
          employee_key text NOT NULL,
          contract_name text NOT NULL DEFAULT 'exit_intent.offboarding_handoff',
          status text NOT NULL DEFAULT 'emitted',
          offboarding_required boolean NOT NULL DEFAULT false,
          offboarding_module_present boolean NOT NULL DEFAULT false,
          payload jsonb NOT NULL DEFAULT '{}'::jsonb,
          emitted_by_phone text,
          emitted_at timestamptz NOT NULL DEFAULT now(),
          CONSTRAINT exit_intent_handoffs_status_chk
            CHECK (status IN ('emitted','accepted','deferred','cancelled'))
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS exit_intent_tasks (
          task_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
          company_code text NOT NULL,
          employee_key text NOT NULL,
          case_id uuid,
          task_type text NOT NULL,
          due_on date,
          status text NOT NULL DEFAULT 'open',
          title_en text NOT NULL,
          title_ar text NOT NULL,
          payload jsonb NOT NULL DEFAULT '{}'::jsonb,
          created_at timestamptz NOT NULL DEFAULT now(),
          updated_at timestamptz NOT NULL DEFAULT now(),
          CONSTRAINT exit_intent_tasks_status_chk
            CHECK (status IN ('open','done','cancelled'))
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS exit_intent_c3_audit (
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
        INSERT INTO exit_intent_c3_audit (
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
    ensure_exit_intent_c3_schema(cur)
    cur.execute(
        "SELECT * FROM exit_intent_c3_company_settings WHERE company_code=%s",
        (company_code_norm(company_code),),
    )
    row = cur.fetchone()
    return dict(row) if row else None


def enable_company_exit_intent(
    cur: Any,
    *,
    company_code: str,
    actor_phone: str,
    reason: str,
    resignation_enabled: bool = True,
    termination_enabled: bool = True,
    eoc_enabled: bool = True,
    require_distinct_approver: bool = True,
    notice_policy_days: int = 30,
    notice_policy_source: str = "company_setup",
    legal_pack_ref: str | None = None,
    eoc_task_days_before: int = 30,
    offboarding_handoff_enabled: bool = False,
) -> dict[str, Any]:
    if not str(reason or "").strip():
        return {"ok": False, "error": "audit_reason_required"}
    dark = assert_real_termination_dark()
    if not dark.get("ok"):
        return dark
    gate = runtime_gate_for_company(company_code)
    if not gate.get("ok"):
        return gate
    company = company_code_norm(company_code)
    ensure_exit_intent_c3_schema(cur)
    source = str(notice_policy_source or "company_setup").strip()
    if source == "legal_pack" and not str(legal_pack_ref or "").strip():
        return {
            "ok": False,
            "error": "legal_pack_ref_required",
            "message": "Kuwait/statutory notice values require an approved legal pack ref — not invented defaults.",
        }
    cur.execute(
        """
        INSERT INTO exit_intent_c3_company_settings (
          company_code, enabled, resignation_enabled, termination_enabled, eoc_enabled,
          require_distinct_approver, notice_policy_days, notice_policy_source, legal_pack_ref,
          eoc_task_days_before, offboarding_handoff_enabled,
          enabled_by_phone, enabled_reason, enabled_at, updated_by_phone, updated_at, disabled_at
        ) VALUES (%s,true,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,now(),%s,now(),NULL)
        ON CONFLICT (company_code) DO UPDATE SET
          enabled=true,
          resignation_enabled=EXCLUDED.resignation_enabled,
          termination_enabled=EXCLUDED.termination_enabled,
          eoc_enabled=EXCLUDED.eoc_enabled,
          require_distinct_approver=EXCLUDED.require_distinct_approver,
          notice_policy_days=EXCLUDED.notice_policy_days,
          notice_policy_source=EXCLUDED.notice_policy_source,
          legal_pack_ref=EXCLUDED.legal_pack_ref,
          eoc_task_days_before=EXCLUDED.eoc_task_days_before,
          offboarding_handoff_enabled=EXCLUDED.offboarding_handoff_enabled,
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
            bool(resignation_enabled),
            bool(termination_enabled),
            bool(eoc_enabled),
            bool(require_distinct_approver),
            int(notice_policy_days),
            source,
            (str(legal_pack_ref).strip() if legal_pack_ref else None),
            int(eoc_task_days_before),
            bool(offboarding_handoff_enabled),
            _digits(actor_phone),
            str(reason).strip()[:500],
            _digits(actor_phone),
        ),
    )
    row = dict(cur.fetchone())
    _audit(
        cur,
        company_code=company,
        action="enable_exit_intent",
        actor_phone=actor_phone,
        reason=reason,
        subject_type="company",
        subject_id=company,
        payload={"resignation_enabled": resignation_enabled, "termination_enabled": termination_enabled},
    )
    return {"ok": True, "company": row, "phase": PHASE, **honesty_payload(company_code=company)}


def disable_company_exit_intent(
    cur: Any,
    *,
    company_code: str,
    actor_phone: str,
    reason: str,
) -> dict[str, Any]:
    if not str(reason or "").strip():
        return {"ok": False, "error": "audit_reason_required"}
    company = company_code_norm(company_code)
    ensure_exit_intent_c3_schema(cur)
    cur.execute(
        """
        UPDATE exit_intent_c3_company_settings
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
        action="disable_exit_intent",
        actor_phone=actor_phone,
        reason=reason,
        subject_type="company",
        subject_id=company,
    )
    return {
        "ok": True,
        "company": dict(row) if row else None,
        "history_preserved": True,
        "phase": PHASE,
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
            "error": "exit_intent_not_enabled",
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
        "resignation_visible": bool(enabled and settings and settings.get("resignation_enabled")),
        "termination_visible": bool(enabled and settings and settings.get("termination_enabled")),
        "eoc_visible": bool(enabled and settings and settings.get("eoc_enabled")),
        "assistant_mutations": False,
        "real_termination_dark": True,
        **honesty_payload(company_code=company_code),
    }


def _employee_snapshot(cur: Any, *, company_code: str, employee_key: str) -> dict[str, Any]:
    company = company_code_norm(company_code)
    cur.execute(
        """
        SELECT employee_key, company_code, name, phone, profile, employment_status,
               hire_date, start_date
          FROM employees
         WHERE company_code=%s AND employee_key=%s
         LIMIT 1
        """,
        (company, employee_key),
    )
    row = cur.fetchone()
    if not row:
        return {"employee_key": employee_key, "missing": True}
    d = dict(row)
    profile = d.get("profile") or {}
    if isinstance(profile, str):
        try:
            profile = json.loads(profile)
        except Exception:
            profile = {}
    return {
        "employee_key": d.get("employee_key"),
        "name": d.get("name"),
        "phone": d.get("phone"),
        "employment_status": d.get("employment_status"),
        "hire_date": str(d.get("hire_date") or d.get("start_date") or ""),
        "contract_end_date": profile.get("contract_end_date") or profile.get("contract_end"),
        "department": profile.get("department"),
        "position_title": profile.get("position_title") or profile.get("title"),
        "manager_employee_key": profile.get("manager_employee_key") or profile.get("manager"),
        "profile": profile,
    }


def _employment_still_active(cur: Any, *, company_code: str, employee_key: str) -> bool:
    snap = _employee_snapshot(cur, company_code=company_code, employee_key=employee_key)
    status = str(snap.get("employment_status") or "").strip().lower()
    return status not in ("left", "terminated", "inactive", "ended")


def _decorate_case(row: dict[str, Any]) -> dict[str, Any]:
    out = dict(row)
    out["status_label_en"] = status_label(out.get("status"), lang="en")
    out["status_label_ar"] = status_label(out.get("status"), lang="ar")
    out["exit_type_label_en"] = status_label(out.get("exit_type"), lang="en")
    out["exit_type_label_ar"] = status_label(out.get("exit_type"), lang="ar")
    out["labels"] = {
        "status_en": out["status_label_en"],
        "status_ar": out["status_label_ar"],
        "exit_type_en": out["exit_type_label_en"],
        "exit_type_ar": out["exit_type_label_ar"],
    }
    return out


def get_case(cur: Any, *, company_code: str, case_id: str) -> dict[str, Any] | None:
    ensure_exit_intent_c3_schema(cur)
    cur.execute(
        "SELECT * FROM exit_intent_cases WHERE company_code=%s AND case_id=%s",
        (company_code_norm(company_code), str(case_id)),
    )
    row = cur.fetchone()
    return _decorate_case(dict(row)) if row else None


def _create_case(
    cur: Any,
    *,
    company_code: str,
    employee_key: str,
    exit_type: str,
    actor_phone: str,
    reason: str | None,
    reason_category: str | None,
    requested_last_working_day: date | str | None,
    payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    enabled = module_enabled_for_company(cur, company_code)
    if not enabled.get("ok"):
        return enabled
    synth = assert_synthetic_employee_key(employee_key)
    if not synth.get("ok"):
        return synth
    settings = enabled["settings"]
    if exit_type == "resignation" and not settings.get("resignation_enabled"):
        return {"ok": False, "error": "resignation_disabled"}
    if exit_type == "termination" and not settings.get("termination_enabled"):
        return {"ok": False, "error": "termination_disabled"}
    if exit_type == "end_of_contract" and not settings.get("eoc_enabled"):
        return {"ok": False, "error": "eoc_disabled"}
    snap = _employee_snapshot(cur, company_code=company_code, employee_key=employee_key)
    if snap.get("missing"):
        return {"ok": False, "error": "employee_not_found"}
    if not _employment_still_active(cur, company_code=company_code, employee_key=employee_key):
        return {"ok": False, "error": "employee_already_left"}
    company = company_code_norm(company_code)
    cur.execute(
        """
        INSERT INTO exit_intent_cases (
          company_code, employee_key, exit_type, status, reason, reason_category,
          requested_last_working_day, employment_snapshot, payload, created_by_phone
        ) VALUES (%s,%s,%s,'draft',%s,%s,%s,%s::jsonb,%s::jsonb,%s)
        RETURNING *
        """,
        (
            company,
            employee_key,
            exit_type,
            (str(reason).strip()[:1000] if reason else None),
            reason_category,
            requested_last_working_day,
            json.dumps(snap, default=str),
            json.dumps(payload or {}, default=str),
            _digits(actor_phone),
        ),
    )
    row = dict(cur.fetchone())
    _audit(
        cur,
        company_code=company,
        action=f"{exit_type}_draft_created",
        actor_phone=actor_phone,
        reason=reason,
        subject_type="exit_intent_case",
        subject_id=str(row["case_id"]),
        payload={"exit_type": exit_type},
    )
    return {"ok": True, "case": _decorate_case(row), **honesty_payload(company_code=company)}


def create_resignation(
    cur: Any,
    *,
    company_code: str,
    employee_key: str,
    actor_phone: str,
    requested_last_working_day: date | str,
    reason: str,
) -> dict[str, Any]:
    if not str(reason or "").strip():
        return {"ok": False, "error": "reason_required"}
    if not requested_last_working_day:
        return {"ok": False, "error": "requested_last_working_day_required"}
    return _create_case(
        cur,
        company_code=company_code,
        employee_key=employee_key,
        exit_type="resignation",
        actor_phone=actor_phone,
        reason=reason,
        reason_category="resignation",
        requested_last_working_day=requested_last_working_day,
        payload={"channel": "employee_app"},
    )


def create_termination(
    cur: Any,
    *,
    company_code: str,
    employee_key: str,
    actor_phone: str,
    reason: str,
    reason_category: str,
    effective_last_working_day: date | str,
    hr_authorized: bool = True,
) -> dict[str, Any]:
    if not hr_authorized:
        return {"ok": False, "error": "hr_authorization_required"}
    if not str(reason or "").strip():
        return {"ok": False, "error": "reason_required"}
    cat = str(reason_category or "").strip().lower()
    if cat not in TERMINATION_CATEGORIES:
        return {"ok": False, "error": "invalid_reason_category", "allowed": list(TERMINATION_CATEGORIES)}
    if not effective_last_working_day:
        return {"ok": False, "error": "effective_last_working_day_required"}
    return _create_case(
        cur,
        company_code=company_code,
        employee_key=employee_key,
        exit_type="termination",
        actor_phone=actor_phone,
        reason=reason,
        reason_category=cat,
        requested_last_working_day=effective_last_working_day,
        payload={"channel": "hr", "hr_authorized": True},
    )


def create_eoc_case(
    cur: Any,
    *,
    company_code: str,
    employee_key: str,
    actor_phone: str,
    contract_end_date: date | str,
    reason: str = "contract approaching expiry",
) -> dict[str, Any]:
    """EOC intent from canonical contract end — does not silently terminate."""
    if not contract_end_date:
        return {"ok": False, "error": "contract_end_date_required"}
    created = _create_case(
        cur,
        company_code=company_code,
        employee_key=employee_key,
        exit_type="end_of_contract",
        actor_phone=actor_phone,
        reason=reason,
        reason_category="end_of_contract",
        requested_last_working_day=contract_end_date,
        payload={"channel": "hr", "contract_end_date": str(contract_end_date), "silent_expiry_is_not_termination": True},
    )
    if not created.get("ok"):
        return created
    settings = module_enabled_for_company(cur, company_code)["settings"]
    days_before = int(settings.get("eoc_task_days_before") or 30)
    try:
        end = contract_end_date if isinstance(contract_end_date, date) else date.fromisoformat(str(contract_end_date)[:10])
    except Exception:
        end = date.today()
    due = end - timedelta(days=days_before)
    cur.execute(
        """
        INSERT INTO exit_intent_tasks (
          company_code, employee_key, case_id, task_type, due_on, status, title_en, title_ar, payload
        ) VALUES (%s,%s,%s,'eoc_decision_due',%s,'open',%s,%s,%s::jsonb)
        RETURNING *
        """,
        (
            company_code_norm(company_code),
            employee_key,
            created["case"]["case_id"],
            due,
            "Decide renewal / non-renewal before contract end",
            "قرار تجديد / عدم تجديد قبل انتهاء العقد",
            json.dumps({"contract_end_date": str(contract_end_date)}, default=str),
        ),
    )
    task = dict(cur.fetchone())
    _audit(
        cur,
        company_code=company_code,
        action="eoc_task_created",
        actor_phone=actor_phone,
        subject_type="exit_intent_task",
        subject_id=str(task["task_id"]),
        payload={"case_id": str(created["case"]["case_id"])},
    )
    return {**created, "task": task}


def _bump(
    cur: Any,
    *,
    company_code: str,
    case_id: str,
    expected_version: int | None,
    from_statuses: tuple[str, ...],
    to_status: str,
    actor_phone: str,
    action: str,
    reason: str | None = None,
    extra_sets: str = "",
    extra_params: tuple[Any, ...] = (),
) -> dict[str, Any]:
    company = company_code_norm(company_code)
    params: list[Any] = [to_status, *extra_params, company, str(case_id), list(from_statuses)]
    version_clause = ""
    if expected_version is not None:
        version_clause = " AND row_version=%s"
        params.append(int(expected_version))
    cur.execute(
        f"""
        UPDATE exit_intent_cases
           SET status=%s,
               row_version = row_version + 1,
               updated_at = now()
               {extra_sets}
         WHERE company_code=%s AND case_id=%s
           AND status = ANY(%s)
           {version_clause}
        RETURNING *
        """,
        tuple(params),
    )
    row = cur.fetchone()
    if not row:
        cur.execute(
            "SELECT status, row_version, employee_key FROM exit_intent_cases WHERE company_code=%s AND case_id=%s",
            (company, str(case_id)),
        )
        existing = cur.fetchone()
        if not existing:
            return {"ok": False, "error": "case_not_found"}
        ed = dict(existing)
        if expected_version is not None and int(ed.get("row_version") or 0) != int(expected_version):
            return {"ok": False, "error": "stale_row_version", "row_version": ed.get("row_version")}
        return {
            "ok": False,
            "error": "invalid_status_transition",
            "status": ed.get("status"),
            "from_statuses": list(from_statuses),
            "to_status": to_status,
        }
    d = dict(row)
    _audit(
        cur,
        company_code=company,
        action=action,
        actor_phone=actor_phone,
        reason=reason,
        subject_type="exit_intent_case",
        subject_id=str(d["case_id"]),
        payload={"status": to_status},
    )
    return {"ok": True, "case": _decorate_case(d)}


def submit_case(
    cur: Any,
    *,
    company_code: str,
    case_id: str,
    actor_phone: str,
    reason: str = "submit",
    expected_version: int | None = None,
) -> dict[str, Any]:
    enabled = module_enabled_for_company(cur, company_code)
    if not enabled.get("ok"):
        return enabled
    case = get_case(cur, company_code=company_code, case_id=case_id)
    if not case:
        return {"ok": False, "error": "case_not_found"}
    # submit does not mark employment left
    if not _employment_still_active(cur, company_code=company_code, employee_key=str(case["employee_key"])):
        return {"ok": False, "error": "employee_already_left"}
    out = _bump(
        cur,
        company_code=company_code,
        case_id=case_id,
        expected_version=expected_version,
        from_statuses=(ST_DRAFT,),
        to_status=ST_SUBMITTED,
        actor_phone=actor_phone,
        action="exit_intent_submitted",
        reason=reason,
        extra_sets=", submitted_by_phone=%s, submitted_at=now()",
        extra_params=(_digits(actor_phone),),
    )
    if not out.get("ok"):
        return out
    # Auto-advance to pending_approval (keeps initiation vs approval distinct in history via audit)
    return _bump(
        cur,
        company_code=company_code,
        case_id=case_id,
        expected_version=int(out["case"]["row_version"]),
        from_statuses=(ST_SUBMITTED,),
        to_status=ST_PENDING,
        actor_phone=actor_phone,
        action="exit_intent_pending_approval",
        reason=reason,
        extra_sets=", pending_approver_role=%s",
        extra_params=("hr",),
    )


def approve_case(
    cur: Any,
    *,
    company_code: str,
    case_id: str,
    actor_phone: str,
    reason: str,
    expected_version: int | None = None,
) -> dict[str, Any]:
    if not str(reason or "").strip():
        return {"ok": False, "error": "audit_reason_required"}
    enabled = module_enabled_for_company(cur, company_code)
    if not enabled.get("ok"):
        return enabled
    settings = enabled["settings"]
    case = get_case(cur, company_code=company_code, case_id=case_id)
    if not case:
        return {"ok": False, "error": "case_not_found"}
    if settings.get("require_distinct_approver"):
        creators = {_digits(case.get("created_by_phone")), _digits(case.get("submitted_by_phone"))}
        if _digits(actor_phone) in creators:
            return {"ok": False, "error": "sod_self_approve_forbidden"}
    return _bump(
        cur,
        company_code=company_code,
        case_id=case_id,
        expected_version=expected_version,
        from_statuses=(ST_PENDING, ST_SUBMITTED),
        to_status=ST_APPROVED,
        actor_phone=actor_phone,
        action="exit_intent_approved",
        reason=reason,
        extra_sets=", approved_by_phone=%s, approved_at=now(), decision_note=%s",
        extra_params=(_digits(actor_phone), str(reason).strip()[:500]),
    )


def reject_case(
    cur: Any,
    *,
    company_code: str,
    case_id: str,
    actor_phone: str,
    reason: str,
    expected_version: int | None = None,
) -> dict[str, Any]:
    if not str(reason or "").strip():
        return {"ok": False, "error": "audit_reason_required"}
    enabled = module_enabled_for_company(cur, company_code)
    if not enabled.get("ok"):
        return enabled
    return _bump(
        cur,
        company_code=company_code,
        case_id=case_id,
        expected_version=expected_version,
        from_statuses=(ST_PENDING, ST_SUBMITTED),
        to_status=ST_REJECTED,
        actor_phone=actor_phone,
        action="exit_intent_rejected",
        reason=reason,
        extra_sets=", rejected_by_phone=%s, rejected_at=now(), decision_note=%s",
        extra_params=(_digits(actor_phone), str(reason).strip()[:500]),
    )


def withdraw_case(
    cur: Any,
    *,
    company_code: str,
    case_id: str,
    actor_phone: str,
    reason: str,
    expected_version: int | None = None,
) -> dict[str, Any]:
    if not str(reason or "").strip():
        return {"ok": False, "error": "audit_reason_required"}
    enabled = module_enabled_for_company(cur, company_code)
    if not enabled.get("ok"):
        return enabled
    settings = enabled["settings"]
    case = get_case(cur, company_code=company_code, case_id=case_id)
    if not case:
        return {"ok": False, "error": "case_not_found"}
    if case.get("status") not in WITHDRAWABLE:
        return {
            "ok": False,
            "error": "withdraw_past_irreversible_boundary",
            "status": case.get("status"),
            "message": "Withdrawal only before notice_period / ready_for_offboarding.",
        }
    if not settings.get("allow_employee_withdraw_before_notice") and case.get("exit_type") == "resignation":
        return {"ok": False, "error": "withdraw_disabled_by_policy"}
    return _bump(
        cur,
        company_code=company_code,
        case_id=case_id,
        expected_version=expected_version,
        from_statuses=tuple(WITHDRAWABLE),
        to_status=ST_WITHDRAWN,
        actor_phone=actor_phone,
        action="exit_intent_withdrawn",
        reason=reason,
        extra_sets=", withdrawn_by_phone=%s, withdrawn_at=now(), decision_note=%s",
        extra_params=(_digits(actor_phone), str(reason).strip()[:500]),
    )


def cancel_case(
    cur: Any,
    *,
    company_code: str,
    case_id: str,
    actor_phone: str,
    reason: str,
    expected_version: int | None = None,
) -> dict[str, Any]:
    if not str(reason or "").strip():
        return {"ok": False, "error": "audit_reason_required"}
    enabled = module_enabled_for_company(cur, company_code)
    if not enabled.get("ok"):
        return enabled
    return _bump(
        cur,
        company_code=company_code,
        case_id=case_id,
        expected_version=expected_version,
        from_statuses=(ST_DRAFT, ST_SUBMITTED, ST_PENDING, ST_APPROVED, ST_NOTICE),
        to_status=ST_CANCELLED,
        actor_phone=actor_phone,
        action="exit_intent_cancelled",
        reason=reason,
        extra_sets=", cancelled_by_phone=%s, cancelled_at=now(), decision_note=%s",
        extra_params=(_digits(actor_phone), str(reason).strip()[:500]),
    )


def _compute_notice_dates(
    *,
    settings: dict[str, Any],
    last_working_day: date,
    notice_starts_on: date | None = None,
) -> dict[str, Any]:
    days = int(settings.get("notice_policy_days") or 30)
    source = str(settings.get("notice_policy_source") or "company_setup")
    if source == "legal_pack" and not settings.get("legal_pack_ref"):
        return {"ok": False, "error": "legal_pack_ref_required"}
    start = notice_starts_on or date.today()
    # Policy days are company Setup configuration — not invented statutory law
    end = start + timedelta(days=max(days, 0))
    lwd = last_working_day
    if lwd < start:
        return {"ok": False, "error": "last_working_day_before_notice_start"}
    return {
        "ok": True,
        "notice_starts_on": start,
        "notice_ends_on": end,
        "last_working_day": lwd,
        "policy_days": days,
        "policy_source": source,
        "legal_pack_ref": settings.get("legal_pack_ref"),
    }


def enter_notice_period(
    cur: Any,
    *,
    company_code: str,
    case_id: str,
    actor_phone: str,
    reason: str,
    last_working_day: date | str | None = None,
    notice_starts_on: date | str | None = None,
    expected_version: int | None = None,
) -> dict[str, Any]:
    if not str(reason or "").strip():
        return {"ok": False, "error": "audit_reason_required"}
    enabled = module_enabled_for_company(cur, company_code)
    if not enabled.get("ok"):
        return enabled
    settings = enabled["settings"]
    case = get_case(cur, company_code=company_code, case_id=case_id)
    if not case:
        return {"ok": False, "error": "case_not_found"}
    if case.get("status") != ST_APPROVED:
        return {"ok": False, "error": "case_not_approved", "status": case.get("status")}
    raw_lwd = last_working_day or case.get("requested_last_working_day") or case.get("effective_last_working_day")
    if not raw_lwd:
        return {"ok": False, "error": "last_working_day_required"}
    lwd = raw_lwd if isinstance(raw_lwd, date) else date.fromisoformat(str(raw_lwd)[:10])
    start = None
    if notice_starts_on:
        start = notice_starts_on if isinstance(notice_starts_on, date) else date.fromisoformat(str(notice_starts_on)[:10])
    computed = _compute_notice_dates(settings=settings, last_working_day=lwd, notice_starts_on=start)
    if not computed.get("ok"):
        return computed

    # Record notice version 1
    cur.execute(
        """
        INSERT INTO exit_intent_notice_versions (
          company_code, case_id, version_number, notice_starts_on, notice_ends_on,
          last_working_day, policy_days, policy_source, legal_pack_ref, change_reason, changed_by_phone
        ) VALUES (%s,%s,1,%s,%s,%s,%s,%s,%s,%s,%s)
        RETURNING *
        """,
        (
            company_code_norm(company_code),
            case_id,
            computed["notice_starts_on"],
            computed["notice_ends_on"],
            computed["last_working_day"],
            computed["policy_days"],
            computed["policy_source"],
            computed.get("legal_pack_ref"),
            str(reason).strip()[:500],
            _digits(actor_phone),
        ),
    )
    notice_ver = dict(cur.fetchone())

    bumped = _bump(
        cur,
        company_code=company_code,
        case_id=case_id,
        expected_version=expected_version if expected_version is not None else int(case["row_version"]),
        from_statuses=(ST_APPROVED,),
        to_status=ST_NOTICE,
        actor_phone=actor_phone,
        action="exit_intent_notice_period",
        reason=reason,
        extra_sets=(
            ", notice_starts_on=%s, notice_ends_on=%s, effective_last_working_day=%s, notice_entered_at=now()"
        ),
        extra_params=(
            computed["notice_starts_on"],
            computed["notice_ends_on"],
            computed["last_working_day"],
        ),
    )
    if not bumped.get("ok"):
        return bumped

    # Honesty: do NOT set employment left/terminated
    still_active = _employment_still_active(
        cur, company_code=company_code, employee_key=str(case["employee_key"])
    )
    return {
        **bumped,
        "notice_version": notice_ver,
        "employment_still_active": still_active,
        "employment_closed": False,
        **honesty_payload(company_code=company_code),
    }


def amend_notice(
    cur: Any,
    *,
    company_code: str,
    case_id: str,
    actor_phone: str,
    reason: str,
    notice_starts_on: date | str,
    notice_ends_on: date | str,
    last_working_day: date | str,
) -> dict[str, Any]:
    if not str(reason or "").strip():
        return {"ok": False, "error": "audit_reason_required"}
    enabled = module_enabled_for_company(cur, company_code)
    if not enabled.get("ok"):
        return enabled
    case = get_case(cur, company_code=company_code, case_id=case_id)
    if not case:
        return {"ok": False, "error": "case_not_found"}
    if case.get("status") not in (ST_NOTICE, ST_APPROVED):
        return {"ok": False, "error": "notice_not_amendable", "status": case.get("status")}
    settings = enabled["settings"]
    start = notice_starts_on if isinstance(notice_starts_on, date) else date.fromisoformat(str(notice_starts_on)[:10])
    end = notice_ends_on if isinstance(notice_ends_on, date) else date.fromisoformat(str(notice_ends_on)[:10])
    lwd = last_working_day if isinstance(last_working_day, date) else date.fromisoformat(str(last_working_day)[:10])
    if end < start:
        return {"ok": False, "error": "notice_end_before_start"}
    cur.execute(
        "SELECT COALESCE(MAX(version_number),0)+1 AS v FROM exit_intent_notice_versions WHERE case_id=%s",
        (case_id,),
    )
    version_number = int(dict(cur.fetchone())["v"])
    cur.execute(
        """
        INSERT INTO exit_intent_notice_versions (
          company_code, case_id, version_number, notice_starts_on, notice_ends_on,
          last_working_day, policy_days, policy_source, legal_pack_ref, change_reason, changed_by_phone
        ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
        RETURNING *
        """,
        (
            company_code_norm(company_code),
            case_id,
            version_number,
            start,
            end,
            lwd,
            int(settings.get("notice_policy_days") or 30),
            str(settings.get("notice_policy_source") or "company_setup"),
            settings.get("legal_pack_ref"),
            str(reason).strip()[:500],
            _digits(actor_phone),
        ),
    )
    ver = dict(cur.fetchone())
    cur.execute(
        """
        UPDATE exit_intent_cases
           SET notice_starts_on=%s,
               notice_ends_on=%s,
               effective_last_working_day=%s,
               row_version = row_version + 1,
               updated_at=now()
         WHERE company_code=%s AND case_id=%s
        RETURNING *
        """,
        (start, end, lwd, company_code_norm(company_code), case_id),
    )
    case_row = dict(cur.fetchone())
    _audit(
        cur,
        company_code=company_code,
        action="exit_intent_notice_amended",
        actor_phone=actor_phone,
        reason=reason,
        subject_type="exit_intent_notice_version",
        subject_id=str(ver["notice_version_id"]),
        payload={"version_number": version_number},
    )
    return {"ok": True, "case": _decorate_case(case_row), "notice_version": ver}


def mark_ready_for_offboarding(
    cur: Any,
    *,
    company_code: str,
    case_id: str,
    actor_phone: str,
    reason: str,
    expected_version: int | None = None,
) -> dict[str, Any]:
    """C3 terminal success boundary — not employment closed / clearance / paid."""
    if not str(reason or "").strip():
        return {"ok": False, "error": "audit_reason_required"}
    enabled = module_enabled_for_company(cur, company_code)
    if not enabled.get("ok"):
        return enabled
    settings = enabled["settings"]
    case = get_case(cur, company_code=company_code, case_id=case_id)
    if not case:
        return {"ok": False, "error": "case_not_found"}
    bumped = _bump(
        cur,
        company_code=company_code,
        case_id=case_id,
        expected_version=expected_version if expected_version is not None else int(case["row_version"]),
        from_statuses=(ST_NOTICE,),
        to_status=ST_READY,
        actor_phone=actor_phone,
        action="exit_intent_ready_for_offboarding",
        reason=reason,
        extra_sets=", ready_at=now(), decision_note=%s",
        extra_params=(str(reason).strip()[:500],),
    )
    if not bumped.get("ok"):
        return bumped

    handoff = emit_offboarding_handoff(
        cur,
        company_code=company_code,
        case_id=case_id,
        actor_phone=actor_phone,
        offboarding_module_present=False,
        offboarding_required=bool(settings.get("offboarding_handoff_enabled")),
    )
    still_active = _employment_still_active(
        cur, company_code=company_code, employee_key=str(case["employee_key"])
    )
    return {
        **bumped,
        "handoff": handoff,
        "employment_still_active": still_active,
        "employment_closed": False,
        "clearance_complete": False,
        "access_revoked": False,
        "settlement_finalized": False,
        "employee_paid": False,
        **honesty_payload(company_code=company_code),
    }


def emit_offboarding_handoff(
    cur: Any,
    *,
    company_code: str,
    case_id: str,
    actor_phone: str,
    offboarding_module_present: bool = False,
    offboarding_required: bool = False,
) -> dict[str, Any]:
    """OPTIONAL Offboarding contract — works when Offboarding absent."""
    case = get_case(cur, company_code=company_code, case_id=case_id)
    if not case:
        return {"ok": False, "error": "case_not_found"}
    payload = {
        "contract": "exit_intent.offboarding_handoff",
        "contract_version": CONTRACT_VERSION,
        "case_id": str(case_id),
        "employee_key": case.get("employee_key"),
        "exit_type": case.get("exit_type"),
        "notice_starts_on": str(case.get("notice_starts_on") or ""),
        "notice_ends_on": str(case.get("notice_ends_on") or ""),
        "last_working_day": str(case.get("effective_last_working_day") or ""),
        "offboarding_module_present": bool(offboarding_module_present),
        "offboarding_required": bool(offboarding_required),
        "status_when_offboarding_absent": "deferred_awaiting_offboarding_module",
        "does_not_mean": [
            "employment_closed",
            "clearance_complete",
            "access_revoked",
            "settlement_finalized",
            "employee_paid",
        ],
    }
    status = "accepted" if offboarding_module_present and offboarding_required else "deferred"
    cur.execute(
        """
        INSERT INTO exit_intent_handoffs (
          company_code, case_id, employee_key, contract_name, status,
          offboarding_required, offboarding_module_present, payload, emitted_by_phone
        ) VALUES (%s,%s,%s,'exit_intent.offboarding_handoff',%s,%s,%s,%s::jsonb,%s)
        RETURNING *
        """,
        (
            company_code_norm(company_code),
            case_id,
            case.get("employee_key"),
            status,
            bool(offboarding_required),
            bool(offboarding_module_present),
            json.dumps(payload, default=str),
            _digits(actor_phone),
        ),
    )
    handoff = dict(cur.fetchone())
    cur.execute(
        """
        UPDATE exit_intent_cases
           SET handoff_id=%s, updated_at=now()
         WHERE company_code=%s AND case_id=%s
        """,
        (handoff["handoff_id"], company_code_norm(company_code), case_id),
    )
    _audit(
        cur,
        company_code=company_code,
        action="offboarding_handoff_emitted",
        actor_phone=actor_phone,
        subject_type="exit_intent_handoff",
        subject_id=str(handoff["handoff_id"]),
        payload={"status": status, "offboarding_module_present": offboarding_module_present},
    )
    return {"ok": True, "handoff": handoff, "payload": payload}


def decide_eoc_renewal(
    cur: Any,
    *,
    company_code: str,
    case_id: str,
    actor_phone: str,
    reason: str,
    renewed_contract_end: date | str,
    expected_version: int | None = None,
) -> dict[str, Any]:
    """Renewal — not termination. Closes EOC intent as cancelled with eoc_decision=renewed."""
    if not str(reason or "").strip():
        return {"ok": False, "error": "audit_reason_required"}
    if not renewed_contract_end:
        return {"ok": False, "error": "renewed_contract_end_required"}
    enabled = module_enabled_for_company(cur, company_code)
    if not enabled.get("ok"):
        return enabled
    case = get_case(cur, company_code=company_code, case_id=case_id)
    if not case:
        return {"ok": False, "error": "case_not_found"}
    if case.get("exit_type") != "end_of_contract":
        return {"ok": False, "error": "not_eoc_case"}
    end = (
        renewed_contract_end
        if isinstance(renewed_contract_end, date)
        else date.fromisoformat(str(renewed_contract_end)[:10])
    )
    # Update profile contract end (employment remains active — not left)
    snap = _employee_snapshot(cur, company_code=company_code, employee_key=str(case["employee_key"]))
    profile = dict(snap.get("profile") or {})
    profile["contract_end_date"] = end.isoformat()
    profile["contract_renewal_at"] = datetime.utcnow().isoformat() + "Z"
    cur.execute(
        """
        UPDATE employees
           SET profile = COALESCE(profile,'{}'::jsonb) || %s::jsonb,
               updated_at=now()
         WHERE company_code=%s AND employee_key=%s
        """,
        (json.dumps({"contract_end_date": end.isoformat(), "contract_renewal_at": profile["contract_renewal_at"]}), company_code_norm(company_code), case["employee_key"]),
    )
    cur.execute(
        """
        UPDATE exit_intent_cases
           SET eoc_decision='renewed',
               renewed_contract_end=%s,
               status='cancelled',
               cancelled_by_phone=%s,
               cancelled_at=now(),
               decision_note=%s,
               row_version = row_version + 1,
               updated_at=now()
         WHERE company_code=%s AND case_id=%s
           AND status = ANY(%s)
           AND (%s::int IS NULL OR row_version=%s)
        RETURNING *
        """,
        (
            end,
            _digits(actor_phone),
            str(reason).strip()[:500],
            company_code_norm(company_code),
            case_id,
            list(WITHDRAWABLE | {ST_DRAFT}),
            expected_version,
            expected_version,
        ),
    )
    row = cur.fetchone()
    if not row:
        return {"ok": False, "error": "stale_row_version_or_invalid_status"}
    # Close open EOC tasks
    cur.execute(
        """
        UPDATE exit_intent_tasks
           SET status='done', updated_at=now()
         WHERE case_id=%s AND task_type='eoc_decision_due' AND status='open'
        """,
        (case_id,),
    )
    d = dict(row)
    _audit(
        cur,
        company_code=company_code,
        action="eoc_renewed",
        actor_phone=actor_phone,
        reason=reason,
        subject_type="exit_intent_case",
        subject_id=str(case_id),
        payload={"renewed_contract_end": end.isoformat()},
    )
    return {
        "ok": True,
        "case": _decorate_case(d),
        "eoc_decision": "renewed",
        "employment_still_active": _employment_still_active(
            cur, company_code=company_code, employee_key=str(case["employee_key"])
        ),
        "silent_expiry_treated_as_termination": False,
    }


def decide_eoc_non_renewal(
    cur: Any,
    *,
    company_code: str,
    case_id: str,
    actor_phone: str,
    reason: str,
    expected_version: int | None = None,
) -> dict[str, Any]:
    """Non-renewal — explicit decision, then normal approve→notice→ready path."""
    if not str(reason or "").strip():
        return {"ok": False, "error": "audit_reason_required"}
    enabled = module_enabled_for_company(cur, company_code)
    if not enabled.get("ok"):
        return enabled
    settings = enabled["settings"]
    case = get_case(cur, company_code=company_code, case_id=case_id)
    if not case:
        return {"ok": False, "error": "case_not_found"}
    if case.get("exit_type") != "end_of_contract":
        return {"ok": False, "error": "not_eoc_case"}
    if settings.get("require_distinct_approver") and _digits(actor_phone) == _digits(case.get("created_by_phone")):
        # Decision itself can be by creator; approval later enforces SoD
        pass
    cur.execute(
        """
        UPDATE exit_intent_cases
           SET eoc_decision='non_renewed',
               row_version = row_version + 1,
               updated_at=now(),
               decision_note=%s,
               payload = COALESCE(payload,'{}'::jsonb) || %s::jsonb
         WHERE company_code=%s AND case_id=%s
           AND (%s::int IS NULL OR row_version=%s)
        RETURNING *
        """,
        (
            str(reason).strip()[:500],
            json.dumps({"eoc_decision": "non_renewed", "silent_expiry_is_not_termination": True}),
            company_code_norm(company_code),
            case_id,
            expected_version,
            expected_version,
        ),
    )
    row = cur.fetchone()
    if not row:
        return {"ok": False, "error": "stale_row_version_or_missing"}
    cur.execute(
        """
        UPDATE exit_intent_tasks
           SET status='done', updated_at=now()
         WHERE case_id=%s AND task_type='eoc_decision_due' AND status='open'
        """,
        (case_id,),
    )
    d = dict(row)
    _audit(
        cur,
        company_code=company_code,
        action="eoc_non_renewed",
        actor_phone=actor_phone,
        reason=reason,
        subject_type="exit_intent_case",
        subject_id=str(case_id),
    )
    return {
        "ok": True,
        "case": _decorate_case(d),
        "eoc_decision": "non_renewed",
        "silent_expiry_treated_as_termination": False,
        "next": "submit → pending_approval → approved → notice_period → ready_for_offboarding",
    }


def list_cases_for_employee(
    cur: Any,
    *,
    company_code: str,
    employee_key: str,
) -> dict[str, Any]:
    enabled = module_enabled_for_company(cur, company_code)
    if not enabled.get("ok"):
        return enabled
    cur.execute(
        """
        SELECT * FROM exit_intent_cases
         WHERE company_code=%s AND employee_key=%s
         ORDER BY created_at DESC
        """,
        (company_code_norm(company_code), employee_key),
    )
    return {"ok": True, "cases": [_decorate_case(dict(r)) for r in (cur.fetchall() or [])]}


def list_notice_versions(cur: Any, *, case_id: str) -> list[dict[str, Any]]:
    ensure_exit_intent_c3_schema(cur)
    cur.execute(
        """
        SELECT * FROM exit_intent_notice_versions
         WHERE case_id=%s
         ORDER BY version_number
        """,
        (str(case_id),),
    )
    return [dict(r) for r in (cur.fetchall() or [])]
