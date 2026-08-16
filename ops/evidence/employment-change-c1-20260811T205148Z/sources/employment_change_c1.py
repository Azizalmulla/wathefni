#!/usr/bin/env python3
"""Wave 3 C1 — Employment change cases (company-scoped).

Owner-approved under WAVE3_EMPLOYEE_LIFECYCLE_CHARTER (2026-08-11).

SM: draft → pending_approval → approved | rejected | cancelled → applied

Types: promotion | transfer | manager_change | position_change |
       salary_change | secondment | secondment_return

Gates (fail-closed):
  1) WATHEFNI_EMPLOYMENT_CHANGE_C1 must be on
  2) company in WATHEFNI_EMPLOYMENT_CHANGE_COMPANIES (empty = nobody)
  3) company entitlement in employment_change_c1_company_settings
  4) salary→payroll contract link only when link_comp_contracts enabled (OPTIONAL)

Does NOT: invent EOS/notice money; reopen Wave 2; require Offboarding/Payroll;
Assistant mutations. Canonical employment/history only — no duplicate SoT.
"""
from __future__ import annotations

import json
import os
import uuid
from datetime import date, datetime
from typing import Any

PHASE = "employment_change_c1"
CONTRACT_VERSION = "employment_change_c1_v1"
_ON = {"1", "true", "yes", "on"}

CHANGE_TYPES = (
    "promotion",
    "transfer",
    "manager_change",
    "position_change",
    "salary_change",
    "secondment",
    "secondment_return",
)

ST_DRAFT = "draft"
ST_PENDING = "pending_approval"
ST_APPROVED = "approved"
ST_REJECTED = "rejected"
ST_CANCELLED = "cancelled"
ST_APPLIED = "applied"

STATUS_LABELS = {
    "draft": {"en": "Draft", "ar": "مسودة"},
    "pending_approval": {"en": "Pending approval", "ar": "بانتظار الاعتماد"},
    "approved": {"en": "Approved", "ar": "معتمد"},
    "rejected": {"en": "Rejected", "ar": "مرفوض"},
    "cancelled": {"en": "Cancelled", "ar": "ملغى"},
    "applied": {"en": "Applied", "ar": "مُطبَّق"},
    "promotion": {"en": "Promotion", "ar": "ترقية"},
    "transfer": {"en": "Transfer", "ar": "نقل"},
    "manager_change": {"en": "Manager change", "ar": "تغيير المدير"},
    "position_change": {"en": "Position change", "ar": "تغيير المنصب"},
    "salary_change": {"en": "Salary change", "ar": "تغيير الراتب"},
    "secondment": {"en": "Secondment", "ar": "إعارة / تكليف مؤقت"},
    "secondment_return": {"en": "Secondment return", "ar": "عودة من الإعارة"},
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


def employment_change_c1_runtime_on() -> bool:
    return _env_on("WATHEFNI_EMPLOYMENT_CHANGE_C1", "off")


def employment_change_company_allowlist() -> set[str]:
    raw = str(os.environ.get("WATHEFNI_EMPLOYMENT_CHANGE_COMPANIES") or "").strip()
    if not raw:
        return set()
    return {p.strip().upper() for p in raw.split(",") if p.strip()}


def honesty_payload(*, company_code: str | None = None) -> dict[str, Any]:
    return {
        "phase": PHASE,
        "contract_version": CONTRACT_VERSION,
        "assistant_mutations": False,
        "payroll_required": False,
        "offboarding_required": False,
        "invented_legal_formulas": False,
        "duplicate_employment_sot": False,
        "salary_link_is_optional": True,
        "company_code": company_code_norm(company_code) if company_code else None,
    }


def runtime_gate_for_company(company_code: str | None) -> dict[str, Any]:
    company = company_code_norm(company_code)
    if not company:
        return {"ok": False, "enabled": False, "error": "company_required", "phase": PHASE}
    if not employment_change_c1_runtime_on():
        return {
            "ok": False,
            "enabled": False,
            "error": "employment_change_c1_off",
            "gate": "runtime_flag",
            "phase": PHASE,
        }
    allow = employment_change_company_allowlist()
    if not allow:
        return {
            "ok": False,
            "enabled": False,
            "error": "employment_change_company_not_allowlisted",
            "gate": "company_allowlist",
            "phase": PHASE,
            "message": "Employment-change allowlist empty — fail closed (nobody).",
        }
    if company not in allow:
        return {
            "ok": False,
            "enabled": False,
            "error": "employment_change_company_not_allowlisted",
            "gate": "company_allowlist",
            "phase": PHASE,
            "company_code": company,
        }
    return {"ok": True, "enabled": True, "company_code": company, "phase": PHASE}


def ensure_employment_change_c1_schema(cur: Any, *, force: bool = False) -> None:
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS employment_change_c1_company_settings (
          company_code text PRIMARY KEY,
          enabled boolean NOT NULL DEFAULT false,
          link_comp_contracts boolean NOT NULL DEFAULT false,
          require_distinct_approver boolean NOT NULL DEFAULT true,
          enabled_types jsonb NOT NULL DEFAULT '["promotion","transfer","manager_change","position_change","salary_change","secondment","secondment_return"]'::jsonb,
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
        CREATE TABLE IF NOT EXISTS employment_change_cases (
          case_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
          company_code text NOT NULL,
          employee_key text NOT NULL,
          change_type text NOT NULL,
          status text NOT NULL DEFAULT 'draft',
          row_version int NOT NULL DEFAULT 1,
          effective_from date NOT NULL,
          effective_to date,
          payload jsonb NOT NULL DEFAULT '{}'::jsonb,
          before_snapshot jsonb NOT NULL DEFAULT '{}'::jsonb,
          after_snapshot jsonb NOT NULL DEFAULT '{}'::jsonb,
          history_id uuid,
          payroll_contract_id text,
          payroll_link_status text,
          created_by_phone text NOT NULL,
          submitted_by_phone text,
          approved_by_phone text,
          approved_at timestamptz,
          rejected_by_phone text,
          rejected_at timestamptz,
          cancelled_by_phone text,
          cancelled_at timestamptz,
          applied_by_phone text,
          applied_at timestamptz,
          decision_note text,
          created_at timestamptz NOT NULL DEFAULT now(),
          updated_at timestamptz NOT NULL DEFAULT now(),
          metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
          CONSTRAINT employment_change_cases_type_chk
            CHECK (change_type IN (
              'promotion','transfer','manager_change','position_change',
              'salary_change','secondment','secondment_return'
            )),
          CONSTRAINT employment_change_cases_status_chk
            CHECK (status IN (
              'draft','pending_approval','approved','rejected','cancelled','applied'
            ))
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS employment_change_history (
          history_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
          company_code text NOT NULL,
          employee_key text NOT NULL,
          case_id uuid NOT NULL,
          change_type text NOT NULL,
          effective_from date NOT NULL,
          effective_to date,
          before_snapshot jsonb NOT NULL DEFAULT '{}'::jsonb,
          after_snapshot jsonb NOT NULL DEFAULT '{}'::jsonb,
          applied_by_phone text,
          applied_at timestamptz NOT NULL DEFAULT now(),
          reason text,
          metadata jsonb NOT NULL DEFAULT '{}'::jsonb
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS employment_change_c1_audit (
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
        INSERT INTO employment_change_c1_audit (
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
    ensure_employment_change_c1_schema(cur)
    cur.execute(
        "SELECT * FROM employment_change_c1_company_settings WHERE company_code=%s",
        (company_code_norm(company_code),),
    )
    row = cur.fetchone()
    return dict(row) if row else None


def enable_company_employment_change(
    cur: Any,
    *,
    company_code: str,
    actor_phone: str,
    reason: str,
    link_comp_contracts: bool = False,
    require_distinct_approver: bool = True,
    enabled_types: list[str] | None = None,
) -> dict[str, Any]:
    if not str(reason or "").strip():
        return {"ok": False, "error": "audit_reason_required"}
    gate = runtime_gate_for_company(company_code)
    if not gate.get("ok"):
        return gate
    company = company_code_norm(company_code)
    types = list(enabled_types or CHANGE_TYPES)
    for t in types:
        if t not in CHANGE_TYPES:
            return {"ok": False, "error": "invalid_change_type", "type": t, "allowed": list(CHANGE_TYPES)}
    ensure_employment_change_c1_schema(cur)
    cur.execute(
        """
        INSERT INTO employment_change_c1_company_settings (
          company_code, enabled, link_comp_contracts, require_distinct_approver,
          enabled_types, enabled_by_phone, enabled_reason, enabled_at,
          updated_by_phone, updated_at, disabled_at
        ) VALUES (%s,true,%s,%s,%s::jsonb,%s,%s,now(),%s,now(),NULL)
        ON CONFLICT (company_code) DO UPDATE SET
          enabled=true,
          link_comp_contracts=EXCLUDED.link_comp_contracts,
          require_distinct_approver=EXCLUDED.require_distinct_approver,
          enabled_types=EXCLUDED.enabled_types,
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
            bool(link_comp_contracts),
            bool(require_distinct_approver),
            json.dumps(types),
            _digits(actor_phone),
            str(reason).strip()[:500],
            _digits(actor_phone),
        ),
    )
    row = dict(cur.fetchone())
    _audit(
        cur,
        company_code=company,
        action="enable_employment_change",
        actor_phone=actor_phone,
        reason=reason,
        subject_type="company",
        subject_id=company,
        payload={"link_comp_contracts": link_comp_contracts, "enabled_types": types},
    )
    return {"ok": True, "company": row, "phase": PHASE, **honesty_payload(company_code=company)}


def disable_company_employment_change(
    cur: Any,
    *,
    company_code: str,
    actor_phone: str,
    reason: str,
) -> dict[str, Any]:
    if not str(reason or "").strip():
        return {"ok": False, "error": "audit_reason_required"}
    company = company_code_norm(company_code)
    ensure_employment_change_c1_schema(cur)
    cur.execute(
        """
        UPDATE employment_change_c1_company_settings
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
        action="disable_employment_change",
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


def employment_change_enabled_for_company(cur: Any, company_code: str | None) -> dict[str, Any]:
    gate = runtime_gate_for_company(company_code)
    if not gate.get("ok"):
        return gate
    settings = get_company_settings(cur, company_code)
    if not settings or not settings.get("enabled"):
        return {
            "ok": False,
            "enabled": False,
            "error": "employment_change_not_enabled",
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


def get_case(cur: Any, *, company_code: str, case_id: str) -> dict[str, Any] | None:
    ensure_employment_change_c1_schema(cur)
    cur.execute(
        "SELECT * FROM employment_change_cases WHERE company_code=%s AND case_id=%s",
        (company_code_norm(company_code), str(case_id)),
    )
    row = cur.fetchone()
    return dict(row) if row else None


def _employee_snapshot(cur: Any, *, company_code: str, employee_key: str) -> dict[str, Any]:
    company = company_code_norm(company_code)
    cur.execute(
        """
        SELECT employee_key, company_code, name, phone, profile, employment_status
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
        "department": profile.get("department"),
        "position_title": profile.get("position_title") or profile.get("title"),
        "manager_employee_key": profile.get("manager_employee_key") or profile.get("manager"),
        "location": profile.get("location"),
        "grade": profile.get("grade"),
        "secondment": profile.get("secondment"),
        "profile": profile,
    }


def create_change_case(
    cur: Any,
    *,
    company_code: str,
    employee_key: str,
    change_type: str,
    effective_from: date | str,
    actor_phone: str,
    reason: str,
    payload: dict[str, Any] | None = None,
    effective_to: date | str | None = None,
) -> dict[str, Any]:
    if not str(reason or "").strip():
        return {"ok": False, "error": "audit_reason_required"}
    ent = employment_change_enabled_for_company(cur, company_code)
    if not ent.get("ok"):
        return ent
    ctype = str(change_type or "").strip().lower()
    if ctype not in CHANGE_TYPES:
        return {"ok": False, "error": "invalid_change_type", "allowed": list(CHANGE_TYPES)}
    settings = ent.get("settings") or {}
    enabled_types = settings.get("enabled_types") or list(CHANGE_TYPES)
    if isinstance(enabled_types, str):
        enabled_types = json.loads(enabled_types)
    if ctype not in {str(x) for x in enabled_types}:
        return {"ok": False, "error": "change_type_not_enabled_for_company", "change_type": ctype}
    if ctype == "secondment" and not effective_to:
        return {"ok": False, "error": "secondment_requires_effective_to"}
    company = company_code_norm(company_code)
    ensure_employment_change_c1_schema(cur)
    before = _employee_snapshot(cur, company_code=company, employee_key=employee_key)
    if before.get("missing"):
        return {"ok": False, "error": "employee_not_found", "employee_key": employee_key}
    body = dict(payload or {})
    body.setdefault(
        "labels",
        {"en": status_label(ctype, lang="en"), "ar": status_label(ctype, lang="ar")},
    )
    cur.execute(
        """
        INSERT INTO employment_change_cases (
          company_code, employee_key, change_type, status, effective_from, effective_to,
          payload, before_snapshot, created_by_phone, decision_note
        ) VALUES (%s,%s,%s,'draft',%s,%s,%s::jsonb,%s::jsonb,%s,%s)
        RETURNING *
        """,
        (
            company,
            employee_key,
            ctype,
            str(effective_from)[:10],
            str(effective_to)[:10] if effective_to else None,
            json.dumps(body, default=str),
            json.dumps(before, default=str),
            _digits(actor_phone),
            str(reason).strip()[:500],
        ),
    )
    row = dict(cur.fetchone())
    _audit(
        cur,
        company_code=company,
        action="change_case_created",
        actor_phone=actor_phone,
        reason=reason,
        subject_type="employment_change_case",
        subject_id=str(row.get("case_id")),
        payload={"change_type": ctype, "employee_key": employee_key},
    )
    return {"ok": True, "case": row, "phase": PHASE, **honesty_payload(company_code=company)}


def submit_change_case(
    cur: Any,
    *,
    company_code: str,
    case_id: str,
    actor_phone: str,
    reason: str,
    expected_row_version: int | None = None,
) -> dict[str, Any]:
    if not str(reason or "").strip():
        return {"ok": False, "error": "audit_reason_required"}
    ent = employment_change_enabled_for_company(cur, company_code)
    if not ent.get("ok"):
        return ent
    company = company_code_norm(company_code)
    case = get_case(cur, company_code=company, case_id=case_id)
    if not case:
        return {"ok": False, "error": "case_not_found"}
    if expected_row_version is not None and int(case.get("row_version") or 0) != int(expected_row_version):
        return {"ok": False, "error": "stale_change_decision", "actual_row_version": case.get("row_version")}
    if str(case.get("status")) == ST_PENDING:
        return {"ok": True, "idempotent": True, "case": case, "phase": PHASE}
    if str(case.get("status")) != ST_DRAFT:
        return {"ok": False, "error": "case_must_be_draft", "status": case.get("status")}
    cur.execute(
        """
        UPDATE employment_change_cases
           SET status='pending_approval',
               submitted_by_phone=%s,
               decision_note=%s,
               updated_at=now(),
               row_version=row_version+1
         WHERE company_code=%s AND case_id=%s AND status='draft' AND row_version=%s
         RETURNING *
        """,
        (
            _digits(actor_phone),
            str(reason).strip()[:500],
            company,
            str(case_id),
            int(case.get("row_version") or 1),
        ),
    )
    updated = cur.fetchone()
    if not updated:
        return {"ok": False, "error": "stale_change_decision"}
    out = dict(updated)
    _audit(
        cur,
        company_code=company,
        action="change_case_submitted",
        actor_phone=actor_phone,
        reason=reason,
        subject_type="employment_change_case",
        subject_id=str(case_id),
    )
    return {"ok": True, "case": out, "phase": PHASE, **honesty_payload(company_code=company)}


def decide_change_case(
    cur: Any,
    *,
    company_code: str,
    case_id: str,
    decision: str,
    actor_phone: str,
    reason: str,
    expected_row_version: int | None = None,
) -> dict[str, Any]:
    decision_n = str(decision or "").strip().lower()
    if decision_n not in {ST_APPROVED, ST_REJECTED, ST_CANCELLED}:
        return {"ok": False, "error": "invalid_decision", "allowed": [ST_APPROVED, ST_REJECTED, ST_CANCELLED]}
    if not str(reason or "").strip():
        return {"ok": False, "error": "audit_reason_required"}
    ent = employment_change_enabled_for_company(cur, company_code)
    if not ent.get("ok"):
        return ent
    settings = ent.get("settings") or {}
    company = company_code_norm(company_code)
    case = get_case(cur, company_code=company, case_id=case_id)
    if not case:
        return {"ok": False, "error": "case_not_found"}
    if expected_row_version is not None and int(case.get("row_version") or 0) != int(expected_row_version):
        return {"ok": False, "error": "stale_change_decision", "actual_row_version": case.get("row_version")}
    status = str(case.get("status"))
    if status == decision_n:
        return {"ok": True, "idempotent": True, "case": case, "phase": PHASE}
    if decision_n == ST_CANCELLED and status not in {ST_DRAFT, ST_PENDING}:
        return {"ok": False, "error": "invalid_cancel_status", "status": status}
    if decision_n in {ST_APPROVED, ST_REJECTED} and status != ST_PENDING:
        return {"ok": False, "error": "case_must_be_pending_approval", "status": status}
    actor = _digits(actor_phone)
    creator = _digits(case.get("created_by_phone"))
    submitter = _digits(case.get("submitted_by_phone")) or creator
    if decision_n in {ST_APPROVED, ST_REJECTED} and settings.get("require_distinct_approver", True):
        if actor and actor in {creator, submitter}:
            return {"ok": False, "error": "sod_self_approve_forbidden", "phase": PHASE}

    phone_col = {
        ST_APPROVED: "approved_by_phone",
        ST_REJECTED: "rejected_by_phone",
        ST_CANCELLED: "cancelled_by_phone",
    }[decision_n]
    at_col = {
        ST_APPROVED: "approved_at",
        ST_REJECTED: "rejected_at",
        ST_CANCELLED: "cancelled_at",
    }[decision_n]
    cur.execute(
        f"""
        UPDATE employment_change_cases
           SET status=%s,
               {phone_col}=%s,
               {at_col}=now(),
               decision_note=%s,
               updated_at=now(),
               row_version=row_version+1
         WHERE company_code=%s AND case_id=%s AND row_version=%s
         RETURNING *
        """,
        (
            decision_n,
            actor,
            str(reason).strip()[:500],
            company,
            str(case_id),
            int(case.get("row_version") or 1),
        ),
    )
    updated = cur.fetchone()
    if not updated:
        return {"ok": False, "error": "stale_change_decision"}
    out = dict(updated)
    _audit(
        cur,
        company_code=company,
        action=f"change_case_{decision_n}",
        actor_phone=actor_phone,
        reason=reason,
        subject_type="employment_change_case",
        subject_id=str(case_id),
        payload={"before": status, "after": decision_n},
    )
    return {"ok": True, "case": out, "phase": PHASE, **honesty_payload(company_code=company)}


def _build_after_snapshot(before: dict[str, Any], ctype: str, payload: dict[str, Any]) -> dict[str, Any]:
    after = dict(before)
    profile = dict(after.get("profile") or {})
    if ctype in {"transfer", "promotion", "position_change"}:
        if payload.get("department") is not None:
            after["department"] = payload.get("department")
            profile["department"] = payload.get("department")
        if payload.get("position_title") is not None:
            after["position_title"] = payload.get("position_title")
            profile["position_title"] = payload.get("position_title")
        if payload.get("location") is not None:
            after["location"] = payload.get("location")
            profile["location"] = payload.get("location")
        if payload.get("grade") is not None:
            after["grade"] = payload.get("grade")
            profile["grade"] = payload.get("grade")
    if ctype in {"manager_change", "transfer", "promotion"}:
        if payload.get("manager_employee_key") is not None:
            after["manager_employee_key"] = payload.get("manager_employee_key")
            profile["manager_employee_key"] = payload.get("manager_employee_key")
    if ctype == "secondment":
        profile["secondment"] = {
            "active": True,
            "host_department": payload.get("host_department") or payload.get("department"),
            "host_manager": payload.get("manager_employee_key"),
            "position_title": payload.get("position_title"),
        }
        after["secondment"] = profile["secondment"]
        if payload.get("department") is not None:
            after["department"] = payload.get("department")
            profile["department"] = payload.get("department")
    if ctype == "secondment_return":
        profile["secondment"] = {"active": False, "returned": True}
        after["secondment"] = profile["secondment"]
        if payload.get("home_department") is not None:
            after["department"] = payload.get("home_department")
            profile["department"] = payload.get("home_department")
        if payload.get("home_manager_employee_key") is not None:
            after["manager_employee_key"] = payload.get("home_manager_employee_key")
            profile["manager_employee_key"] = payload.get("home_manager_employee_key")
    if ctype == "salary_change":
        after["salary_change_intent"] = {
            "amount": payload.get("amount"),
            "currency": payload.get("currency") or "KWD",
            "component_code": payload.get("component_code") or "BASIC",
            "money_owner": "payroll",
            "calculated_here": False,
        }
    after["profile"] = profile
    return after


def _apply_profile(cur: Any, *, company_code: str, employee_key: str, after: dict[str, Any]) -> None:
    profile = after.get("profile") or {}
    cur.execute(
        """
        UPDATE employees
           SET profile = COALESCE(profile, '{}'::jsonb) || %s::jsonb,
               updated_at=now()
         WHERE company_code=%s AND employee_key=%s
        """,
        (json.dumps(profile, default=str), company_code_norm(company_code), employee_key),
    )


def _optional_payroll_link(
    cur: Any,
    *,
    company_code: str,
    employee_key: str,
    effective_from: Any,
    payload: dict[str, Any],
    actor_phone: str,
    reason: str,
    link_enabled: bool,
) -> dict[str, Any]:
    if not link_enabled:
        return {
            "ok": True,
            "linked": False,
            "payroll_link_status": "not_linked_contract_off",
            "note": "Salary intent recorded; Payroll contract link OPTIONAL and off",
        }
    try:
        import payroll_authority_wave1 as pyw1

        amount = float(payload.get("amount") or 0)
        if amount <= 0:
            return {"ok": False, "error": "salary_amount_required_for_payroll_link"}
        draft = pyw1.create_contract_draft(
            cur,
            company_code=company_code,
            employee_key=employee_key,
            effective_from=str(effective_from)[:10],
            components=[
                {
                    "component_kind": "earning",
                    "code": str(payload.get("component_code") or "BASIC"),
                    "amount": amount,
                    "is_basic": True,
                }
            ],
            actor_phone=actor_phone,
            reason=reason,
        )
        if not draft.get("ok"):
            return {"ok": False, "error": "payroll_contract_draft_failed", "detail": draft}
        cid = str((draft.get("contract") or {}).get("contract_id") or "")
        return {
            "ok": True,
            "linked": True,
            "payroll_link_status": "draft_linked",
            "payroll_contract_id": cid,
            "posts_payment": False,
        }
    except Exception as exc:
        return {"ok": False, "error": "payroll_link_exception", "detail": str(exc)[:200]}


def apply_change_case(
    cur: Any,
    *,
    company_code: str,
    case_id: str,
    actor_phone: str,
    reason: str,
    expected_row_version: int | None = None,
) -> dict[str, Any]:
    """Apply approved case → append-only history + canonical employment mutation."""
    if not str(reason or "").strip():
        return {"ok": False, "error": "audit_reason_required"}
    ent = employment_change_enabled_for_company(cur, company_code)
    if not ent.get("ok"):
        return ent
    settings = ent.get("settings") or {}
    company = company_code_norm(company_code)
    case = get_case(cur, company_code=company, case_id=case_id)
    if not case:
        return {"ok": False, "error": "case_not_found"}
    if expected_row_version is not None and int(case.get("row_version") or 0) != int(expected_row_version):
        return {"ok": False, "error": "stale_change_decision", "actual_row_version": case.get("row_version")}
    if str(case.get("status")) == ST_APPLIED:
        return {"ok": True, "idempotent": True, "case": case, "phase": PHASE, **honesty_payload(company_code=company)}
    if str(case.get("status")) != ST_APPROVED:
        return {"ok": False, "error": "case_must_be_approved", "status": case.get("status")}

    ctype = str(case.get("change_type"))
    payload = case.get("payload") or {}
    if isinstance(payload, str):
        payload = json.loads(payload)
    before = case.get("before_snapshot") or {}
    if isinstance(before, str):
        before = json.loads(before)
    after = _build_after_snapshot(before, ctype, payload)

    payroll_link = {"linked": False, "payroll_link_status": "n/a"}
    if ctype == "salary_change":
        payroll_link = _optional_payroll_link(
            cur,
            company_code=company,
            employee_key=str(case.get("employee_key")),
            effective_from=case.get("effective_from"),
            payload=payload,
            actor_phone=actor_phone,
            reason=reason,
            link_enabled=bool(settings.get("link_comp_contracts")),
        )
        if not payroll_link.get("ok"):
            return {**payroll_link, "phase": PHASE}

    history_id = str(uuid.uuid4())
    cur.execute(
        """
        INSERT INTO employment_change_history (
          history_id, company_code, employee_key, case_id, change_type,
          effective_from, effective_to, before_snapshot, after_snapshot,
          applied_by_phone, reason
        ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s::jsonb,%s::jsonb,%s,%s)
        """,
        (
            history_id,
            company,
            case.get("employee_key"),
            str(case_id),
            ctype,
            str(case.get("effective_from"))[:10],
            str(case.get("effective_to"))[:10] if case.get("effective_to") else None,
            json.dumps(before, default=str),
            json.dumps(after, default=str),
            _digits(actor_phone),
            str(reason).strip()[:500],
        ),
    )
    if ctype != "salary_change":
        _apply_profile(cur, company_code=company, employee_key=str(case.get("employee_key")), after=after)
    elif payroll_link.get("linked"):
        # Still record salary intent on profile metadata without inventing paid state
        intent = {"salary_change_last": after.get("salary_change_intent"), "payroll_contract_id": payroll_link.get("payroll_contract_id")}
        cur.execute(
            """
            UPDATE employees
               SET profile = COALESCE(profile, '{}'::jsonb) || %s::jsonb,
                   updated_at=now()
             WHERE company_code=%s AND employee_key=%s
            """,
            (json.dumps(intent, default=str), company, case.get("employee_key")),
        )

    cur.execute(
        """
        UPDATE employment_change_cases
           SET status='applied',
               after_snapshot=%s::jsonb,
               history_id=%s,
               payroll_contract_id=%s,
               payroll_link_status=%s,
               applied_by_phone=%s,
               applied_at=now(),
               decision_note=%s,
               updated_at=now(),
               row_version=row_version+1
         WHERE company_code=%s AND case_id=%s AND status='approved' AND row_version=%s
         RETURNING *
        """,
        (
            json.dumps(after, default=str),
            history_id,
            payroll_link.get("payroll_contract_id"),
            payroll_link.get("payroll_link_status"),
            _digits(actor_phone),
            str(reason).strip()[:500],
            company,
            str(case_id),
            int(case.get("row_version") or 1),
        ),
    )
    updated = cur.fetchone()
    if not updated:
        return {"ok": False, "error": "stale_change_decision"}
    out = dict(updated)
    _audit(
        cur,
        company_code=company,
        action="change_case_applied",
        actor_phone=actor_phone,
        reason=reason,
        subject_type="employment_change_case",
        subject_id=str(case_id),
        payload={
            "history_id": history_id,
            "change_type": ctype,
            "payroll_link": payroll_link,
            "before": before,
            "after": after,
        },
    )
    return {
        "ok": True,
        "case": out,
        "history_id": history_id,
        "payroll_link": payroll_link,
        "immutable_history": True,
        "phase": PHASE,
        **honesty_payload(company_code=company),
    }


def list_history(cur: Any, *, company_code: str, employee_key: str) -> list[dict[str, Any]]:
    ensure_employment_change_c1_schema(cur)
    cur.execute(
        """
        SELECT * FROM employment_change_history
         WHERE company_code=%s AND employee_key=%s
         ORDER BY applied_at ASC, effective_from ASC
        """,
        (company_code_norm(company_code), employee_key),
    )
    return [dict(r) for r in (cur.fetchall() or [])]


def rollback_guidance() -> dict[str, Any]:
    return {
        "ok": True,
        "phase": PHASE,
        "steps": [
            "WATHEFNI_EMPLOYMENT_CHANGE_C1=off",
            "Clear WATHEFNI_EMPLOYMENT_CHANGE_COMPANIES",
            "disable_company_employment_change(canary)",
            "Applied history rows remain append-only (no silent purge)",
        ],
    }
