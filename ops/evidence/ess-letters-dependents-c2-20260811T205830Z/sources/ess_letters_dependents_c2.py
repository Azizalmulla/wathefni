#!/usr/bin/env python3
"""Wave 3 C2 — ESS Letters + Dependents (company-scoped).

Owner-approved under WAVE3_EMPLOYEE_LIFECYCLE_CHARTER (2026-08-11).
C1 EMPLOYMENT_CHANGE_FULL_PASS ACCEPTED/frozen before this slice.

Letter SM:
  requested → under_review → approved → processing → issued
  (+ rejected | cancelled)

Letter types:
  salary_certificate | employment_certificate | experience_letter

Dependents: canonical CRUD + archive; optional employee-request + HR review.
Benefits / insurance dependents = OUT (Wave 6).

Gates (fail-closed):
  1) WATHEFNI_ESS_LETTERS_DEPENDENTS_C2 must be on
  2) company in WATHEFNI_ESS_LETTERS_DEPENDENTS_COMPANIES (empty = nobody)
  3) company entitlement in ess_letters_dependents_c2_company_settings
  4) letters_fulfill must be on to issue (no silent invent when off)
  5) salary_cert_use_payroll OPTIONAL for salary figures

Does NOT: invent company legal wording; require Payroll/Benefits/Offboarding;
Assistant mutations; reopen C1.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import uuid
from datetime import date, datetime
from typing import Any

PHASE = "ess_letters_dependents_c2"
CONTRACT_VERSION = "ess_letters_dependents_c2_v1"
_ON = {"1", "true", "yes", "on"}

LETTER_TYPES = (
    "salary_certificate",
    "employment_certificate",
    "experience_letter",
)

# Map experience_letter ↔ legacy ESS service_certificate naming
LETTER_TYPE_ALIASES = {
    "service_certificate": "experience_letter",
    "employment_letter": "employment_certificate",
}

ST_REQUESTED = "requested"
ST_UNDER_REVIEW = "under_review"
ST_APPROVED = "approved"
ST_PROCESSING = "processing"
ST_ISSUED = "issued"
ST_REJECTED = "rejected"
ST_CANCELLED = "cancelled"

LETTER_STATUSES = (
    ST_REQUESTED,
    ST_UNDER_REVIEW,
    ST_APPROVED,
    ST_PROCESSING,
    ST_ISSUED,
    ST_REJECTED,
    ST_CANCELLED,
)

DEP_RELATIONS = (
    "spouse",
    "child",
    "parent",
    "sibling",
    "other",
)

DEP_REQ_STATUSES = (
    "requested",
    "under_review",
    "approved",
    "applied",
    "rejected",
    "cancelled",
)

# Placeholders only — Setup owns real company wording. No invented legal claims.
DEFAULT_TEMPLATE_BODIES = {
    "employment_certificate": {
        "en": (
            "EMPLOYMENT CERTIFICATE\n"
            "Company: {{company_name}}\n"
            "Employee: {{employee_name}}\n"
            "Employee key: {{employee_key}}\n"
            "Position: {{position_title}}\n"
            "Department: {{department}}\n"
            "Employment status: {{employment_status}}\n"
            "Hire date: {{hire_date}}\n"
            "Issue date: {{issue_date}}\n"
            "Language: EN\n"
            "{{template_disclaimer}}\n"
        ),
        "ar": (
            "شهادة عمل\n"
            "الشركة: {{company_name}}\n"
            "الموظف: {{employee_name}}\n"
            "رقم الموظف: {{employee_key}}\n"
            "المنصب: {{position_title}}\n"
            "القسم: {{department}}\n"
            "حالة التوظيف: {{employment_status}}\n"
            "تاريخ التعيين: {{hire_date}}\n"
            "تاريخ الإصدار: {{issue_date}}\n"
            "اللغة: AR\n"
            "{{template_disclaimer}}\n"
        ),
    },
    "experience_letter": {
        "en": (
            "EXPERIENCE / SERVICE LETTER\n"
            "Company: {{company_name}}\n"
            "Employee: {{employee_name}}\n"
            "Employee key: {{employee_key}}\n"
            "Position: {{position_title}}\n"
            "Department: {{department}}\n"
            "Service from: {{hire_date}}\n"
            "Service to: {{service_to}}\n"
            "Issue date: {{issue_date}}\n"
            "{{template_disclaimer}}\n"
        ),
        "ar": (
            "خطاب خبرة / خدمة\n"
            "الشركة: {{company_name}}\n"
            "الموظف: {{employee_name}}\n"
            "رقم الموظف: {{employee_key}}\n"
            "المنصب: {{position_title}}\n"
            "القسم: {{department}}\n"
            "الخدمة من: {{hire_date}}\n"
            "الخدمة إلى: {{service_to}}\n"
            "تاريخ الإصدار: {{issue_date}}\n"
            "{{template_disclaimer}}\n"
        ),
    },
    "salary_certificate": {
        "en": (
            "SALARY CERTIFICATE\n"
            "Company: {{company_name}}\n"
            "Employee: {{employee_name}}\n"
            "Employee key: {{employee_key}}\n"
            "Position: {{position_title}}\n"
            "Compensation source: {{comp_source}}\n"
            "Currency: {{currency}}\n"
            "Amount: {{salary_amount}}\n"
            "Issue date: {{issue_date}}\n"
            "{{template_disclaimer}}\n"
        ),
        "ar": (
            "شهادة راتب\n"
            "الشركة: {{company_name}}\n"
            "الموظف: {{employee_name}}\n"
            "رقم الموظف: {{employee_key}}\n"
            "المنصب: {{position_title}}\n"
            "مصدر التعويض: {{comp_source}}\n"
            "العملة: {{currency}}\n"
            "المبلغ: {{salary_amount}}\n"
            "تاريخ الإصدار: {{issue_date}}\n"
            "{{template_disclaimer}}\n"
        ),
    },
}

STATUS_LABELS = {
    "requested": {"en": "Requested", "ar": "مطلوب"},
    "under_review": {"en": "Under review", "ar": "قيد المراجعة"},
    "approved": {"en": "Approved", "ar": "معتمد"},
    "processing": {"en": "Processing", "ar": "قيد المعالجة"},
    "issued": {"en": "Issued", "ar": "مُصدَر"},
    "rejected": {"en": "Rejected", "ar": "مرفوض"},
    "cancelled": {"en": "Cancelled", "ar": "ملغى"},
    "applied": {"en": "Applied", "ar": "مُطبَّق"},
    "salary_certificate": {"en": "Salary certificate", "ar": "شهادة راتب"},
    "employment_certificate": {"en": "Employment certificate", "ar": "شهادة عمل"},
    "experience_letter": {"en": "Experience / service letter", "ar": "خطاب خبرة / خدمة"},
    "spouse": {"en": "Spouse", "ar": "زوج/زوجة"},
    "child": {"en": "Child", "ar": "ابن/ابنة"},
    "parent": {"en": "Parent", "ar": "والد/والدة"},
    "sibling": {"en": "Sibling", "ar": "أخ/أخت"},
    "other": {"en": "Other", "ar": "أخرى"},
}

_PLACEHOLDER_RE = re.compile(r"\{\{\s*([a-zA-Z0-9_]+)\s*\}\}")


def _env_on(name: str, default: str = "off") -> bool:
    return (os.environ.get(name) or default).strip().lower() in _ON


def _digits(value: Any) -> str:
    return "".join(ch for ch in str(value or "") if ch.isdigit())


def company_code_norm(company_code: str | None) -> str:
    return str(company_code or "").strip().upper()


def normalize_letter_type(letter_type: str | None) -> str:
    raw = str(letter_type or "").strip().lower()
    return LETTER_TYPE_ALIASES.get(raw, raw)


def status_label(status: str | None, *, lang: str = "en") -> str:
    key = str(status or "").strip().lower()
    pack = STATUS_LABELS.get(key) or {"en": key or "unknown", "ar": key or "غير معروف"}
    return str(pack.get("ar" if lang.lower().startswith("ar") else "en"))


def ess_letters_dependents_c2_runtime_on() -> bool:
    return _env_on("WATHEFNI_ESS_LETTERS_DEPENDENTS_C2", "off")


def ess_letters_dependents_company_allowlist() -> set[str]:
    raw = str(os.environ.get("WATHEFNI_ESS_LETTERS_DEPENDENTS_COMPANIES") or "").strip()
    if not raw:
        return set()
    return {p.strip().upper() for p in raw.split(",") if p.strip()}


def honesty_payload(*, company_code: str | None = None) -> dict[str, Any]:
    return {
        "phase": PHASE,
        "contract_version": CONTRACT_VERSION,
        "assistant_mutations": False,
        "payroll_required": False,
        "benefits_required": False,
        "offboarding_required": False,
        "silent_pdf_when_fulfill_off": False,
        "invented_legal_wording": False,
        "salary_payroll_link_optional": True,
        "dependents_are_not_benefits": True,
        "issued_versions_immutable": True,
        "company_code": company_code_norm(company_code) if company_code else None,
    }


def rollback_guidance() -> dict[str, Any]:
    return {
        "phase": PHASE,
        "steps": [
            "WATHEFNI_ESS_LETTERS_DEPENDENTS_C2=off",
            "Clear WATHEFNI_ESS_LETTERS_DEPENDENTS_COMPANIES",
            "disable_company_ess_letters_dependents(canary)",
            "Issued letter versions + dependent history retained (no purge)",
        ],
        "history_intact": True,
    }


def runtime_gate_for_company(company_code: str | None) -> dict[str, Any]:
    company = company_code_norm(company_code)
    if not company:
        return {"ok": False, "enabled": False, "error": "company_required", "phase": PHASE}
    if not ess_letters_dependents_c2_runtime_on():
        return {
            "ok": False,
            "enabled": False,
            "error": "ess_letters_dependents_c2_off",
            "gate": "runtime_flag",
            "phase": PHASE,
        }
    allow = ess_letters_dependents_company_allowlist()
    if not allow:
        return {
            "ok": False,
            "enabled": False,
            "error": "ess_letters_dependents_company_not_allowlisted",
            "gate": "company_allowlist",
            "phase": PHASE,
            "message": "ESS letters/dependents allowlist empty — fail closed (nobody).",
        }
    if company not in allow:
        return {
            "ok": False,
            "enabled": False,
            "error": "ess_letters_dependents_company_not_allowlisted",
            "gate": "company_allowlist",
            "phase": PHASE,
            "company_code": company,
        }
    return {"ok": True, "enabled": True, "company_code": company, "phase": PHASE}


def ensure_ess_letters_dependents_c2_schema(cur: Any, *, force: bool = False) -> None:
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS ess_letters_dependents_c2_company_settings (
          company_code text PRIMARY KEY,
          enabled boolean NOT NULL DEFAULT false,
          letters_enabled boolean NOT NULL DEFAULT true,
          letters_fulfill boolean NOT NULL DEFAULT false,
          dependents_enabled boolean NOT NULL DEFAULT false,
          dependents_require_hr_review boolean NOT NULL DEFAULT true,
          salary_cert_use_payroll boolean NOT NULL DEFAULT false,
          require_distinct_approver boolean NOT NULL DEFAULT true,
          enabled_letter_types jsonb NOT NULL DEFAULT
            '["salary_certificate","employment_certificate","experience_letter"]'::jsonb,
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
        CREATE TABLE IF NOT EXISTS ess_letter_templates (
          template_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
          company_code text NOT NULL,
          letter_type text NOT NULL,
          lang text NOT NULL DEFAULT 'en',
          body_template text NOT NULL,
          disclaimer text NOT NULL DEFAULT
            'Template placeholders only — company Setup owns final wording. Not legal advice.',
          version int NOT NULL DEFAULT 1,
          active boolean NOT NULL DEFAULT true,
          created_by_phone text,
          created_at timestamptz NOT NULL DEFAULT now(),
          updated_at timestamptz NOT NULL DEFAULT now(),
          metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
          CONSTRAINT ess_letter_templates_type_chk
            CHECK (letter_type IN (
              'salary_certificate','employment_certificate','experience_letter'
            )),
          CONSTRAINT ess_letter_templates_lang_chk CHECK (lang IN ('en','ar')),
          UNIQUE (company_code, letter_type, lang, version)
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS ess_letter_requests (
          request_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
          company_code text NOT NULL,
          employee_key text NOT NULL,
          letter_type text NOT NULL,
          lang text NOT NULL DEFAULT 'en',
          status text NOT NULL DEFAULT 'requested',
          row_version int NOT NULL DEFAULT 1,
          purpose text,
          payload jsonb NOT NULL DEFAULT '{}'::jsonb,
          employment_snapshot jsonb NOT NULL DEFAULT '{}'::jsonb,
          requested_by_phone text NOT NULL,
          reviewed_by_phone text,
          reviewed_at timestamptz,
          approved_by_phone text,
          approved_at timestamptz,
          rejected_by_phone text,
          rejected_at timestamptz,
          cancelled_by_phone text,
          cancelled_at timestamptz,
          issued_version_id uuid,
          corrects_version_id uuid,
          decision_note text,
          created_at timestamptz NOT NULL DEFAULT now(),
          updated_at timestamptz NOT NULL DEFAULT now(),
          metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
          CONSTRAINT ess_letter_requests_type_chk
            CHECK (letter_type IN (
              'salary_certificate','employment_certificate','experience_letter'
            )),
          CONSTRAINT ess_letter_requests_lang_chk CHECK (lang IN ('en','ar')),
          CONSTRAINT ess_letter_requests_status_chk
            CHECK (status IN (
              'requested','under_review','approved','processing','issued',
              'rejected','cancelled'
            ))
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS ess_letter_versions (
          version_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
          company_code text NOT NULL,
          employee_key text NOT NULL,
          request_id uuid NOT NULL,
          letter_type text NOT NULL,
          lang text NOT NULL DEFAULT 'en',
          version_number int NOT NULL,
          supersedes_version_id uuid,
          body_text text NOT NULL,
          content_hash text NOT NULL,
          storage_ref text NOT NULL,
          artifact_format text NOT NULL DEFAULT 'text/v1',
          template_id uuid,
          template_version int,
          employment_snapshot jsonb NOT NULL DEFAULT '{}'::jsonb,
          compensation_snapshot jsonb NOT NULL DEFAULT '{}'::jsonb,
          issued_by_phone text NOT NULL,
          issued_at timestamptz NOT NULL DEFAULT now(),
          immutable boolean NOT NULL DEFAULT true,
          metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
          UNIQUE (company_code, employee_key, letter_type, lang, version_number)
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS employee_dependents (
          dependent_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
          company_code text NOT NULL,
          employee_key text NOT NULL,
          relationship text NOT NULL,
          name_en text NOT NULL,
          name_ar text,
          date_of_birth date,
          identity_meta jsonb NOT NULL DEFAULT '{}'::jsonb,
          evidence_ref text,
          status text NOT NULL DEFAULT 'active',
          row_version int NOT NULL DEFAULT 1,
          duplicate_fingerprint text NOT NULL,
          created_by_phone text,
          updated_by_phone text,
          archived_by_phone text,
          archived_at timestamptz,
          created_at timestamptz NOT NULL DEFAULT now(),
          updated_at timestamptz NOT NULL DEFAULT now(),
          metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
          CONSTRAINT employee_dependents_rel_chk
            CHECK (relationship IN ('spouse','child','parent','sibling','other')),
          CONSTRAINT employee_dependents_status_chk
            CHECK (status IN ('active','archived'))
        )
        """
    )
    cur.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS employee_dependents_active_dup_uq
          ON employee_dependents (company_code, employee_key, duplicate_fingerprint)
          WHERE status = 'active'
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS employee_dependent_change_requests (
          change_request_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
          company_code text NOT NULL,
          employee_key text NOT NULL,
          action text NOT NULL,
          dependent_id uuid,
          status text NOT NULL DEFAULT 'requested',
          row_version int NOT NULL DEFAULT 1,
          proposed jsonb NOT NULL DEFAULT '{}'::jsonb,
          requested_by_phone text NOT NULL,
          reviewed_by_phone text,
          reviewed_at timestamptz,
          decision_note text,
          created_at timestamptz NOT NULL DEFAULT now(),
          updated_at timestamptz NOT NULL DEFAULT now(),
          metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
          CONSTRAINT employee_dependent_change_action_chk
            CHECK (action IN ('create','edit','archive')),
          CONSTRAINT employee_dependent_change_status_chk
            CHECK (status IN (
              'requested','under_review','approved','applied','rejected','cancelled'
            ))
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS employee_dependent_history (
          history_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
          company_code text NOT NULL,
          employee_key text NOT NULL,
          dependent_id uuid NOT NULL,
          action text NOT NULL,
          before_snapshot jsonb NOT NULL DEFAULT '{}'::jsonb,
          after_snapshot jsonb NOT NULL DEFAULT '{}'::jsonb,
          actor_phone text,
          reason text,
          created_at timestamptz NOT NULL DEFAULT now()
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS ess_letters_dependents_c2_audit (
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
        INSERT INTO ess_letters_dependents_c2_audit (
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
    ensure_ess_letters_dependents_c2_schema(cur)
    cur.execute(
        "SELECT * FROM ess_letters_dependents_c2_company_settings WHERE company_code=%s",
        (company_code_norm(company_code),),
    )
    row = cur.fetchone()
    return dict(row) if row else None


def feature_visibility(cur: Any, company_code: str | None) -> dict[str, Any]:
    """Employee App hide contract — disabled capabilities disappear cleanly."""
    gate = runtime_gate_for_company(company_code)
    settings = get_company_settings(cur, company_code) if gate.get("ok") else None
    enabled = bool(gate.get("ok") and settings and settings.get("enabled"))
    letters = bool(enabled and settings and settings.get("letters_enabled"))
    dependents = bool(enabled and settings and settings.get("dependents_enabled"))
    return {
        "ok": True,
        "module_enabled": enabled,
        "letters_visible": letters,
        "dependents_visible": dependents,
        "letters_fulfill": bool(settings.get("letters_fulfill")) if settings else False,
        "salary_cert_use_payroll": bool(settings.get("salary_cert_use_payroll")) if settings else False,
        "assistant_mutations": False,
        "phase": PHASE,
        **honesty_payload(company_code=company_code),
    }


def enable_company_ess_letters_dependents(
    cur: Any,
    *,
    company_code: str,
    actor_phone: str,
    reason: str,
    letters_enabled: bool = True,
    letters_fulfill: bool = False,
    dependents_enabled: bool = False,
    dependents_require_hr_review: bool = True,
    salary_cert_use_payroll: bool = False,
    require_distinct_approver: bool = True,
    seed_default_templates: bool = True,
) -> dict[str, Any]:
    if not str(reason or "").strip():
        return {"ok": False, "error": "audit_reason_required"}
    gate = runtime_gate_for_company(company_code)
    if not gate.get("ok"):
        return gate
    company = company_code_norm(company_code)
    ensure_ess_letters_dependents_c2_schema(cur)
    cur.execute(
        """
        INSERT INTO ess_letters_dependents_c2_company_settings (
          company_code, enabled, letters_enabled, letters_fulfill, dependents_enabled,
          dependents_require_hr_review, salary_cert_use_payroll, require_distinct_approver,
          enabled_by_phone, enabled_reason, enabled_at, updated_by_phone, updated_at, disabled_at
        ) VALUES (%s,true,%s,%s,%s,%s,%s,%s,%s,%s,now(),%s,now(),NULL)
        ON CONFLICT (company_code) DO UPDATE SET
          enabled=true,
          letters_enabled=EXCLUDED.letters_enabled,
          letters_fulfill=EXCLUDED.letters_fulfill,
          dependents_enabled=EXCLUDED.dependents_enabled,
          dependents_require_hr_review=EXCLUDED.dependents_require_hr_review,
          salary_cert_use_payroll=EXCLUDED.salary_cert_use_payroll,
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
            bool(letters_enabled),
            bool(letters_fulfill),
            bool(dependents_enabled),
            bool(dependents_require_hr_review),
            bool(salary_cert_use_payroll),
            bool(require_distinct_approver),
            _digits(actor_phone),
            str(reason).strip()[:500],
            _digits(actor_phone),
        ),
    )
    row = dict(cur.fetchone())
    if seed_default_templates:
        _seed_default_templates(cur, company_code=company, actor_phone=actor_phone)
    _audit(
        cur,
        company_code=company,
        action="enable_ess_letters_dependents",
        actor_phone=actor_phone,
        reason=reason,
        subject_type="company",
        subject_id=company,
        payload={
            "letters_fulfill": letters_fulfill,
            "dependents_enabled": dependents_enabled,
            "salary_cert_use_payroll": salary_cert_use_payroll,
        },
    )
    return {"ok": True, "company": row, "phase": PHASE, **honesty_payload(company_code=company)}


def disable_company_ess_letters_dependents(
    cur: Any,
    *,
    company_code: str,
    actor_phone: str,
    reason: str,
) -> dict[str, Any]:
    if not str(reason or "").strip():
        return {"ok": False, "error": "audit_reason_required"}
    company = company_code_norm(company_code)
    ensure_ess_letters_dependents_c2_schema(cur)
    cur.execute(
        """
        UPDATE ess_letters_dependents_c2_company_settings
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
        action="disable_ess_letters_dependents",
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
    gate = runtime_gate_for_company(company_code)
    if not gate.get("ok"):
        return gate
    settings = get_company_settings(cur, company_code)
    if not settings or not settings.get("enabled"):
        return {
            "ok": False,
            "enabled": False,
            "error": "ess_letters_dependents_not_enabled",
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


def _seed_default_templates(cur: Any, *, company_code: str, actor_phone: str | None) -> None:
    company = company_code_norm(company_code)
    for letter_type, langs in DEFAULT_TEMPLATE_BODIES.items():
        for lang, body in langs.items():
            cur.execute(
                """
                SELECT template_id FROM ess_letter_templates
                 WHERE company_code=%s AND letter_type=%s AND lang=%s AND active=true
                 LIMIT 1
                """,
                (company, letter_type, lang),
            )
            if cur.fetchone():
                continue
            cur.execute(
                """
                INSERT INTO ess_letter_templates (
                  company_code, letter_type, lang, body_template, version, active, created_by_phone
                ) VALUES (%s,%s,%s,%s,1,true,%s)
                """,
                (company, letter_type, lang, body, _digits(actor_phone) or None),
            )


def upsert_letter_template(
    cur: Any,
    *,
    company_code: str,
    letter_type: str,
    lang: str,
    body_template: str,
    actor_phone: str,
    reason: str,
    disclaimer: str | None = None,
) -> dict[str, Any]:
    if not str(reason or "").strip():
        return {"ok": False, "error": "audit_reason_required"}
    enabled = module_enabled_for_company(cur, company_code)
    if not enabled.get("ok"):
        return enabled
    lt = normalize_letter_type(letter_type)
    if lt not in LETTER_TYPES:
        return {"ok": False, "error": "invalid_letter_type", "allowed": list(LETTER_TYPES)}
    lang_n = "ar" if str(lang).lower().startswith("ar") else "en"
    body = str(body_template or "").strip()
    if not body or "{{" not in body:
        return {"ok": False, "error": "template_must_use_placeholders"}
    company = company_code_norm(company_code)
    cur.execute(
        """
        UPDATE ess_letter_templates SET active=false, updated_at=now()
         WHERE company_code=%s AND letter_type=%s AND lang=%s AND active=true
        """,
        (company, lt, lang_n),
    )
    cur.execute(
        """
        SELECT COALESCE(MAX(version),0)+1 AS v FROM ess_letter_templates
         WHERE company_code=%s AND letter_type=%s AND lang=%s
        """,
        (company, lt, lang_n),
    )
    version = int(dict(cur.fetchone())["v"])
    cur.execute(
        """
        INSERT INTO ess_letter_templates (
          company_code, letter_type, lang, body_template, disclaimer, version, active, created_by_phone
        ) VALUES (%s,%s,%s,%s,%s,%s,true,%s)
        RETURNING *
        """,
        (
            company,
            lt,
            lang_n,
            body,
            (
                disclaimer
                or "Template placeholders only — company Setup owns final wording. Not legal advice."
            ),
            version,
            _digits(actor_phone),
        ),
    )
    row = dict(cur.fetchone())
    _audit(
        cur,
        company_code=company,
        action="upsert_letter_template",
        actor_phone=actor_phone,
        reason=reason,
        subject_type="letter_template",
        subject_id=str(row["template_id"]),
        payload={"letter_type": lt, "lang": lang_n, "version": version},
    )
    return {"ok": True, "template": row}


def _employee_snapshot(cur: Any, *, company_code: str, employee_key: str) -> dict[str, Any]:
    company = company_code_norm(company_code)
    cur.execute(
        """
        SELECT e.employee_key, e.company_code, e.name, e.phone, e.profile, e.employment_status,
               e.hire_date, e.start_date, c.name AS company_name
          FROM employees e
          LEFT JOIN companies c ON c.company_code = e.company_code
         WHERE e.company_code=%s AND e.employee_key=%s
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
    hire = d.get("hire_date") or d.get("start_date")
    return {
        "employee_key": d.get("employee_key"),
        "company_code": company,
        "company_name": d.get("company_name") or company,
        "employee_name": d.get("name"),
        "phone": d.get("phone"),
        "employment_status": d.get("employment_status"),
        "department": profile.get("department"),
        "position_title": profile.get("position_title") or profile.get("title"),
        "hire_date": str(hire) if hire else "",
        "service_to": "present",
        "profile": profile,
    }


def _compensation_snapshot(
    cur: Any,
    *,
    company_code: str,
    employee_key: str,
    use_payroll: bool,
) -> dict[str, Any]:
    if not use_payroll:
        return {
            "comp_source": "not_linked",
            "currency": "",
            "salary_amount": "[not disclosed — payroll contract off]",
            "payroll_linked": False,
        }
    try:
        import payroll_authority_wave1 as pw1
    except Exception:
        return {
            "comp_source": "payroll_unavailable",
            "currency": "",
            "salary_amount": "[payroll module unavailable]",
            "payroll_linked": False,
            "error": "payroll_import_failed",
        }
    today = date.today()
    try:
        pw1.ensure_payroll_wave1_schema(cur)
        rows = pw1.list_overlapping_approved(
            cur,
            company_code=company_code,
            employee_key=employee_key,
            effective_from=today,
            effective_to=today,
        )
    except Exception as exc:
        return {
            "comp_source": "payroll_error",
            "currency": "",
            "salary_amount": "[payroll read failed]",
            "payroll_linked": False,
            "error": str(exc)[:200],
        }
    if not rows:
        return {
            "comp_source": "no_approved_contract",
            "currency": "",
            "salary_amount": "[no approved compensation contract]",
            "payroll_linked": True,
            "found": False,
        }
    contract = rows[-1]
    full = pw1.get_contract(cur, company_code=company_code, contract_id=str(contract["contract_id"])) or contract
    components = full.get("components") or []
    total = 0.0
    for c in components:
        try:
            total += float(c.get("amount") or 0)
        except Exception:
            pass
    return {
        "comp_source": "payroll_approved_contract",
        "currency": full.get("currency") or "KWD",
        "salary_amount": f"{total:.3f}",
        "payroll_linked": True,
        "contract_id": str(full.get("contract_id")),
        "found": True,
    }


def _render_template(body: str, values: dict[str, Any]) -> str:
    def repl(match: re.Match[str]) -> str:
        key = match.group(1)
        val = values.get(key)
        return "" if val is None else str(val)

    return _PLACEHOLDER_RE.sub(repl, body)


def _active_template(cur: Any, *, company_code: str, letter_type: str, lang: str) -> dict[str, Any] | None:
    cur.execute(
        """
        SELECT * FROM ess_letter_templates
         WHERE company_code=%s AND letter_type=%s AND lang=%s AND active=true
         ORDER BY version DESC LIMIT 1
        """,
        (company_code_norm(company_code), letter_type, lang),
    )
    row = cur.fetchone()
    return dict(row) if row else None


def request_letter(
    cur: Any,
    *,
    company_code: str,
    employee_key: str,
    letter_type: str,
    actor_phone: str,
    lang: str = "en",
    purpose: str | None = None,
    corrects_version_id: str | None = None,
) -> dict[str, Any]:
    enabled = module_enabled_for_company(cur, company_code)
    if not enabled.get("ok"):
        return enabled
    settings = enabled["settings"]
    if not settings.get("letters_enabled"):
        return {"ok": False, "error": "letters_disabled", "gate": "letters_enabled", "phase": PHASE}
    lt = normalize_letter_type(letter_type)
    if lt not in LETTER_TYPES:
        return {"ok": False, "error": "invalid_letter_type", "allowed": list(LETTER_TYPES)}
    lang_n = "ar" if str(lang).lower().startswith("ar") else "en"
    snap = _employee_snapshot(cur, company_code=company_code, employee_key=employee_key)
    if snap.get("missing"):
        return {"ok": False, "error": "employee_not_found"}
    if corrects_version_id:
        cur.execute(
            """
            SELECT version_id FROM ess_letter_versions
             WHERE company_code=%s AND employee_key=%s AND version_id=%s
            """,
            (company_code_norm(company_code), employee_key, corrects_version_id),
        )
        if not cur.fetchone():
            return {"ok": False, "error": "corrects_version_not_found"}
    company = company_code_norm(company_code)
    cur.execute(
        """
        INSERT INTO ess_letter_requests (
          company_code, employee_key, letter_type, lang, status, purpose,
          employment_snapshot, requested_by_phone, corrects_version_id
        ) VALUES (%s,%s,%s,%s,'requested',%s,%s::jsonb,%s,%s)
        RETURNING *
        """,
        (
            company,
            employee_key,
            lt,
            lang_n,
            (str(purpose).strip()[:500] if purpose else None),
            json.dumps(snap, default=str),
            _digits(actor_phone),
            corrects_version_id,
        ),
    )
    row = dict(cur.fetchone())
    _audit(
        cur,
        company_code=company,
        action="letter_requested",
        actor_phone=actor_phone,
        reason=purpose,
        subject_type="letter_request",
        subject_id=str(row["request_id"]),
        payload={"letter_type": lt, "lang": lang_n},
    )
    return {
        "ok": True,
        "request": _decorate_letter_request(row),
        "visibility": feature_visibility(cur, company),
    }


def get_letter_request(cur: Any, *, company_code: str, request_id: str) -> dict[str, Any] | None:
    ensure_ess_letters_dependents_c2_schema(cur)
    cur.execute(
        "SELECT * FROM ess_letter_requests WHERE company_code=%s AND request_id=%s",
        (company_code_norm(company_code), str(request_id)),
    )
    row = cur.fetchone()
    return _decorate_letter_request(dict(row)) if row else None


def _decorate_letter_request(row: dict[str, Any]) -> dict[str, Any]:
    out = dict(row)
    out["status_label_en"] = status_label(out.get("status"), lang="en")
    out["status_label_ar"] = status_label(out.get("status"), lang="ar")
    out["letter_type_label_en"] = status_label(out.get("letter_type"), lang="en")
    out["letter_type_label_ar"] = status_label(out.get("letter_type"), lang="ar")
    return out


def _bump_letter(
    cur: Any,
    *,
    company_code: str,
    request_id: str,
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
    params: list[Any] = [to_status, *extra_params, company, str(request_id), list(from_statuses)]
    version_clause = ""
    if expected_version is not None:
        version_clause = " AND row_version=%s"
        params.append(int(expected_version))
    cur.execute(
        f"""
        UPDATE ess_letter_requests
           SET status=%s,
               row_version = row_version + 1,
               updated_at = now()
               {extra_sets}
         WHERE company_code=%s AND request_id=%s
           AND status = ANY(%s)
           {version_clause}
        RETURNING *
        """,
        tuple(params),
    )
    row = cur.fetchone()
    if not row:
        cur.execute(
            "SELECT status, row_version FROM ess_letter_requests WHERE company_code=%s AND request_id=%s",
            (company, str(request_id)),
        )
        existing = cur.fetchone()
        if not existing:
            return {"ok": False, "error": "letter_request_not_found"}
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
        subject_type="letter_request",
        subject_id=str(d["request_id"]),
        payload={"status": to_status},
    )
    return {"ok": True, "request": _decorate_letter_request(d)}


def start_letter_review(
    cur: Any,
    *,
    company_code: str,
    request_id: str,
    actor_phone: str,
    expected_version: int | None = None,
) -> dict[str, Any]:
    enabled = module_enabled_for_company(cur, company_code)
    if not enabled.get("ok"):
        return enabled
    return _bump_letter(
        cur,
        company_code=company_code,
        request_id=request_id,
        expected_version=expected_version,
        from_statuses=(ST_REQUESTED,),
        to_status=ST_UNDER_REVIEW,
        actor_phone=actor_phone,
        action="letter_under_review",
        extra_sets=", reviewed_by_phone=%s, reviewed_at=now()",
        extra_params=(_digits(actor_phone),),
    )


def approve_letter(
    cur: Any,
    *,
    company_code: str,
    request_id: str,
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
    req = get_letter_request(cur, company_code=company_code, request_id=request_id)
    if not req:
        return {"ok": False, "error": "letter_request_not_found"}
    if settings.get("require_distinct_approver") and _digits(actor_phone) == _digits(req.get("requested_by_phone")):
        return {"ok": False, "error": "sod_self_approve_forbidden"}
    return _bump_letter(
        cur,
        company_code=company_code,
        request_id=request_id,
        expected_version=expected_version,
        from_statuses=(ST_UNDER_REVIEW, ST_REQUESTED),
        to_status=ST_APPROVED,
        actor_phone=actor_phone,
        action="letter_approved",
        reason=reason,
        extra_sets=", approved_by_phone=%s, approved_at=now(), decision_note=%s",
        extra_params=(_digits(actor_phone), str(reason).strip()[:500]),
    )


def reject_letter(
    cur: Any,
    *,
    company_code: str,
    request_id: str,
    actor_phone: str,
    reason: str,
    expected_version: int | None = None,
) -> dict[str, Any]:
    if not str(reason or "").strip():
        return {"ok": False, "error": "audit_reason_required"}
    enabled = module_enabled_for_company(cur, company_code)
    if not enabled.get("ok"):
        return enabled
    return _bump_letter(
        cur,
        company_code=company_code,
        request_id=request_id,
        expected_version=expected_version,
        from_statuses=(ST_REQUESTED, ST_UNDER_REVIEW, ST_APPROVED),
        to_status=ST_REJECTED,
        actor_phone=actor_phone,
        action="letter_rejected",
        reason=reason,
        extra_sets=", rejected_by_phone=%s, rejected_at=now(), decision_note=%s",
        extra_params=(_digits(actor_phone), str(reason).strip()[:500]),
    )


def cancel_letter(
    cur: Any,
    *,
    company_code: str,
    request_id: str,
    actor_phone: str,
    reason: str,
    expected_version: int | None = None,
) -> dict[str, Any]:
    if not str(reason or "").strip():
        return {"ok": False, "error": "audit_reason_required"}
    enabled = module_enabled_for_company(cur, company_code)
    if not enabled.get("ok"):
        return enabled
    return _bump_letter(
        cur,
        company_code=company_code,
        request_id=request_id,
        expected_version=expected_version,
        from_statuses=(ST_REQUESTED, ST_UNDER_REVIEW, ST_APPROVED),
        to_status=ST_CANCELLED,
        actor_phone=actor_phone,
        action="letter_cancelled",
        reason=reason,
        extra_sets=", cancelled_by_phone=%s, cancelled_at=now(), decision_note=%s",
        extra_params=(_digits(actor_phone), str(reason).strip()[:500]),
    )


def issue_letter(
    cur: Any,
    *,
    company_code: str,
    request_id: str,
    actor_phone: str,
    reason: str,
    expected_version: int | None = None,
) -> dict[str, Any]:
    """Approve→processing→issued with immutable artifact. Fails if fulfill off."""
    if not str(reason or "").strip():
        return {"ok": False, "error": "audit_reason_required"}
    enabled = module_enabled_for_company(cur, company_code)
    if not enabled.get("ok"):
        return enabled
    settings = enabled["settings"]
    if not settings.get("letters_fulfill"):
        return {
            "ok": False,
            "error": "letters_fulfill_off",
            "gate": "letters_fulfill",
            "message": "No silent PDF invent when fulfill off — request stays pending/approved.",
            "phase": PHASE,
        }
    req = get_letter_request(cur, company_code=company_code, request_id=request_id)
    if not req:
        return {"ok": False, "error": "letter_request_not_found"}
    if expected_version is not None and int(req.get("row_version") or 0) != int(expected_version):
        return {"ok": False, "error": "stale_row_version", "row_version": req.get("row_version")}
    if req.get("status") not in (ST_APPROVED, ST_PROCESSING):
        # allow issue from under_review only after approve; auto-approve path not used
        if req.get("status") in (ST_REQUESTED, ST_UNDER_REVIEW):
            return {"ok": False, "error": "letter_not_approved", "status": req.get("status")}
        return {"ok": False, "error": "invalid_status_transition", "status": req.get("status")}

    company = company_code_norm(company_code)
    # Move to processing
    proc = _bump_letter(
        cur,
        company_code=company,
        request_id=request_id,
        expected_version=int(req["row_version"]),
        from_statuses=(ST_APPROVED, ST_PROCESSING),
        to_status=ST_PROCESSING,
        actor_phone=actor_phone,
        action="letter_processing",
        reason=reason,
    )
    if not proc.get("ok"):
        return proc
    req = proc["request"]

    lang = req["lang"]
    lt = req["letter_type"]
    tpl = _active_template(cur, company_code=company, letter_type=lt, lang=lang)
    if not tpl:
        return {"ok": False, "error": "letter_template_missing", "letter_type": lt, "lang": lang}

    emp_snap = req.get("employment_snapshot") or {}
    if isinstance(emp_snap, str):
        emp_snap = json.loads(emp_snap)
    # Refresh employment truth at issue time
    live = _employee_snapshot(cur, company_code=company, employee_key=req["employee_key"])
    if not live.get("missing"):
        emp_snap = live
    comp = {}
    if lt == "salary_certificate":
        comp = _compensation_snapshot(
            cur,
            company_code=company,
            employee_key=req["employee_key"],
            use_payroll=bool(settings.get("salary_cert_use_payroll")),
        )
    values = {
        **{k: ("" if v is None else v) for k, v in emp_snap.items() if not isinstance(v, (dict, list))},
        "issue_date": date.today().isoformat(),
        "template_disclaimer": tpl.get("disclaimer")
        or "Template placeholders only — company Setup owns final wording. Not legal advice.",
        "comp_source": comp.get("comp_source", ""),
        "currency": comp.get("currency", ""),
        "salary_amount": comp.get("salary_amount", ""),
    }
    body = _render_template(str(tpl["body_template"]), values)
    content_hash = hashlib.sha256(body.encode("utf-8")).hexdigest()

    cur.execute(
        """
        SELECT COALESCE(MAX(version_number),0)+1 AS v FROM ess_letter_versions
         WHERE company_code=%s AND employee_key=%s AND letter_type=%s AND lang=%s
        """,
        (company, req["employee_key"], lt, lang),
    )
    version_number = int(dict(cur.fetchone())["v"])
    supersedes = req.get("corrects_version_id")
    version_id = str(uuid.uuid4())
    storage_ref = f"ess-letter://{company}/{req['employee_key']}/{lt}/{lang}/v{version_number}/{version_id}"

    cur.execute(
        """
        INSERT INTO ess_letter_versions (
          version_id, company_code, employee_key, request_id, letter_type, lang,
          version_number, supersedes_version_id, body_text, content_hash, storage_ref,
          artifact_format, template_id, template_version, employment_snapshot,
          compensation_snapshot, issued_by_phone, immutable
        ) VALUES (
          %s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'text/v1',%s,%s,%s::jsonb,%s::jsonb,%s,true
        )
        RETURNING *
        """,
        (
            version_id,
            company,
            req["employee_key"],
            req["request_id"],
            lt,
            lang,
            version_number,
            supersedes,
            body,
            content_hash,
            storage_ref,
            tpl.get("template_id"),
            tpl.get("version"),
            json.dumps(emp_snap, default=str),
            json.dumps(comp, default=str),
            _digits(actor_phone),
        ),
    )
    version_row = dict(cur.fetchone())

    # Align ESS overlay letter order (pending → issued) without inventing a second body SoT
    _sync_ess_letter_order(
        cur,
        company=company,
        employee_key=req["employee_key"],
        letter_type=lt,
        request_id=str(req["request_id"]),
        version=version_row,
    )
    # Align Art. 54 service certificate track for experience letters
    if lt == "experience_letter":
        _sync_lifecycle_service_certificate(
            cur,
            company=company,
            employee_key=req["employee_key"],
            version=version_row,
            actor_phone=actor_phone,
        )

    cur.execute(
        """
        UPDATE ess_letter_requests
           SET status='issued',
               issued_version_id=%s,
               row_version = row_version + 1,
               updated_at=now(),
               decision_note=%s
         WHERE company_code=%s AND request_id=%s AND status='processing'
        RETURNING *
        """,
        (version_id, str(reason).strip()[:500], company, str(request_id)),
    )
    issued_req = cur.fetchone()
    if not issued_req:
        return {"ok": False, "error": "issue_finalize_failed"}
    _audit(
        cur,
        company_code=company,
        action="letter_issued",
        actor_phone=actor_phone,
        reason=reason,
        subject_type="letter_version",
        subject_id=version_id,
        payload={
            "request_id": str(request_id),
            "version_number": version_number,
            "content_hash": content_hash,
            "storage_ref": storage_ref,
        },
    )
    return {
        "ok": True,
        "request": _decorate_letter_request(dict(issued_req)),
        "version": version_row,
        "download": {
            "version_id": version_id,
            "storage_ref": storage_ref,
            "content_hash": content_hash,
            "body_text": body,
            "immutable": True,
        },
    }


def _sync_ess_letter_order(
    cur: Any,
    *,
    company: str,
    employee_key: str,
    letter_type: str,
    request_id: str,
    version: dict[str, Any],
) -> None:
    """Best-effort EXTEND of Wave 5 pending overlay — C2 version remains SoT for body."""
    legacy_type = {
        "employment_certificate": "employment_letter",
        "experience_letter": "service_certificate",
        "salary_certificate": "salary_certificate",
    }.get(letter_type, letter_type)
    try:
        cur.execute(
            """
            SELECT to_regclass('public.employee_ess_letter_orders') AS t
            """
        )
        if not dict(cur.fetchone()).get("t"):
            return
        payload = {
            "c2_version_id": str(version.get("version_id")),
            "content_hash": version.get("content_hash"),
            "storage_ref": version.get("storage_ref"),
            "issued_at": str(version.get("issued_at")),
            "sot": PHASE,
        }
        cur.execute(
            """
            INSERT INTO employee_ess_letter_orders (
              company_code, employee_key, letter_type, status, request_id, payload, updated_at
            ) VALUES (%s,%s,%s,'issued',%s,%s::jsonb,now())
            """,
            (company, employee_key, legacy_type, request_id, json.dumps(payload, default=str)),
        )
    except Exception:
        pass


def _sync_lifecycle_service_certificate(
    cur: Any,
    *,
    company: str,
    employee_key: str,
    version: dict[str, Any],
    actor_phone: str,
) -> None:
    try:
        cur.execute("SELECT to_regclass('public.employee_lifecycle_service_certificates') AS t")
        if not dict(cur.fetchone()).get("t"):
            return
        cur.execute(
            """
            INSERT INTO employee_lifecycle_service_certificates (
              company_code, employee_key, status, payload, created_at, updated_at
            ) VALUES (
              %s,%s,'issued',%s::jsonb,now(),now()
            )
            """,
            (
                company,
                employee_key,
                json.dumps(
                    {
                        "c2_version_id": str(version.get("version_id")),
                        "content_hash": version.get("content_hash"),
                        "storage_ref": version.get("storage_ref"),
                        "sot": PHASE,
                        "issued_by_phone": _digits(actor_phone),
                    },
                    default=str,
                ),
            ),
        )
    except Exception:
        # Column shapes vary — do not fail issue on alignment miss; audit covers C2 SoT
        pass


def get_letter_version(cur: Any, *, company_code: str, version_id: str) -> dict[str, Any] | None:
    ensure_ess_letters_dependents_c2_schema(cur)
    cur.execute(
        "SELECT * FROM ess_letter_versions WHERE company_code=%s AND version_id=%s",
        (company_code_norm(company_code), str(version_id)),
    )
    row = cur.fetchone()
    return dict(row) if row else None


def download_letter_version(
    cur: Any,
    *,
    company_code: str,
    version_id: str,
    actor_phone: str | None = None,
    employee_key: str | None = None,
) -> dict[str, Any]:
    """Employee/HR download of issued immutable version. Self-scope when employee_key set."""
    enabled = module_enabled_for_company(cur, company_code)
    if not enabled.get("ok"):
        return enabled
    ver = get_letter_version(cur, company_code=company_code, version_id=version_id)
    if not ver:
        return {"ok": False, "error": "letter_version_not_found"}
    if employee_key and str(ver.get("employee_key")) != str(employee_key):
        return {"ok": False, "error": "forbidden_self_scope"}
    _audit(
        cur,
        company_code=company_code,
        action="letter_downloaded",
        actor_phone=actor_phone,
        subject_type="letter_version",
        subject_id=str(version_id),
        payload={"employee_key": ver.get("employee_key")},
    )
    return {
        "ok": True,
        "version_id": str(ver["version_id"]),
        "body_text": ver["body_text"],
        "content_hash": ver["content_hash"],
        "storage_ref": ver["storage_ref"],
        "immutable": True,
        "version_number": ver["version_number"],
        "letter_type": ver["letter_type"],
        "lang": ver["lang"],
    }


def attempt_mutate_issued_version(
    cur: Any,
    *,
    company_code: str,
    version_id: str,
    new_body: str,
) -> dict[str, Any]:
    """Honesty prove — issued versions must not silently change."""
    ver = get_letter_version(cur, company_code=company_code, version_id=version_id)
    if not ver:
        return {"ok": False, "error": "letter_version_not_found"}
    if ver.get("immutable"):
        return {
            "ok": False,
            "error": "issued_version_immutable",
            "content_hash": ver.get("content_hash"),
            "message": "Correction requires a new letter request/version.",
        }
    # Should never reach — table default immutable=true and no update API
    return {"ok": False, "error": "issued_version_immutable"}


def correct_letter(
    cur: Any,
    *,
    company_code: str,
    prior_version_id: str,
    actor_phone: str,
    purpose: str,
) -> dict[str, Any]:
    """Correction = new request linked to prior immutable version."""
    ver = get_letter_version(cur, company_code=company_code, version_id=prior_version_id)
    if not ver:
        return {"ok": False, "error": "letter_version_not_found"}
    return request_letter(
        cur,
        company_code=company_code,
        employee_key=str(ver["employee_key"]),
        letter_type=str(ver["letter_type"]),
        actor_phone=actor_phone,
        lang=str(ver["lang"]),
        purpose=purpose,
        corrects_version_id=str(prior_version_id),
    )


# ----- Dependents -----


def _dep_fingerprint(*, relationship: str, name_en: str, date_of_birth: date | str | None) -> str:
    dob = str(date_of_birth or "").strip()
    raw = f"{relationship.strip().lower()}|{name_en.strip().lower()}|{dob}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def create_dependent(
    cur: Any,
    *,
    company_code: str,
    employee_key: str,
    relationship: str,
    name_en: str,
    actor_phone: str,
    reason: str,
    name_ar: str | None = None,
    date_of_birth: date | str | None = None,
    identity_meta: dict[str, Any] | None = None,
    evidence_ref: str | None = None,
) -> dict[str, Any]:
    if not str(reason or "").strip():
        return {"ok": False, "error": "audit_reason_required"}
    enabled = module_enabled_for_company(cur, company_code)
    if not enabled.get("ok"):
        return enabled
    if not enabled["settings"].get("dependents_enabled"):
        return {"ok": False, "error": "dependents_disabled", "gate": "dependents_enabled"}
    rel = str(relationship or "").strip().lower()
    if rel not in DEP_RELATIONS:
        return {"ok": False, "error": "invalid_relationship", "allowed": list(DEP_RELATIONS)}
    name = str(name_en or "").strip()
    if not name:
        return {"ok": False, "error": "name_en_required"}
    snap = _employee_snapshot(cur, company_code=company_code, employee_key=employee_key)
    if snap.get("missing"):
        return {"ok": False, "error": "employee_not_found"}
    company = company_code_norm(company_code)
    fp = _dep_fingerprint(relationship=rel, name_en=name, date_of_birth=date_of_birth)
    cur.execute(
        """
        SELECT dependent_id FROM employee_dependents
         WHERE company_code=%s AND employee_key=%s AND duplicate_fingerprint=%s AND status='active'
        """,
        (company, employee_key, fp),
    )
    if cur.fetchone():
        return {"ok": False, "error": "duplicate_dependent"}
    cur.execute(
        """
        INSERT INTO employee_dependents (
          company_code, employee_key, relationship, name_en, name_ar, date_of_birth,
          identity_meta, evidence_ref, status, duplicate_fingerprint, created_by_phone, updated_by_phone
        ) VALUES (%s,%s,%s,%s,%s,%s,%s::jsonb,%s,'active',%s,%s,%s)
        RETURNING *
        """,
        (
            company,
            employee_key,
            rel,
            name,
            (str(name_ar).strip() if name_ar else None),
            date_of_birth,
            json.dumps(identity_meta or {}, default=str),
            evidence_ref,
            fp,
            _digits(actor_phone),
            _digits(actor_phone),
        ),
    )
    row = dict(cur.fetchone())
    _dep_history(
        cur,
        company_code=company,
        employee_key=employee_key,
        dependent_id=str(row["dependent_id"]),
        action="create",
        before={},
        after=row,
        actor_phone=actor_phone,
        reason=reason,
    )
    _audit(
        cur,
        company_code=company,
        action="dependent_created",
        actor_phone=actor_phone,
        reason=reason,
        subject_type="dependent",
        subject_id=str(row["dependent_id"]),
    )
    return {"ok": True, "dependent": _decorate_dependent(row)}


def _decorate_dependent(row: dict[str, Any]) -> dict[str, Any]:
    out = dict(row)
    out["relationship_label_en"] = status_label(out.get("relationship"), lang="en")
    out["relationship_label_ar"] = status_label(out.get("relationship"), lang="ar")
    return out


def _dep_history(
    cur: Any,
    *,
    company_code: str,
    employee_key: str,
    dependent_id: str,
    action: str,
    before: dict[str, Any],
    after: dict[str, Any],
    actor_phone: str | None,
    reason: str | None,
) -> None:
    cur.execute(
        """
        INSERT INTO employee_dependent_history (
          company_code, employee_key, dependent_id, action,
          before_snapshot, after_snapshot, actor_phone, reason
        ) VALUES (%s,%s,%s,%s,%s::jsonb,%s::jsonb,%s,%s)
        """,
        (
            company_code_norm(company_code),
            employee_key,
            dependent_id,
            action,
            json.dumps(before, default=str),
            json.dumps(after, default=str),
            _digits(actor_phone) or None,
            (str(reason).strip()[:500] if reason else None),
        ),
    )


def get_dependent(cur: Any, *, company_code: str, dependent_id: str) -> dict[str, Any] | None:
    ensure_ess_letters_dependents_c2_schema(cur)
    cur.execute(
        "SELECT * FROM employee_dependents WHERE company_code=%s AND dependent_id=%s",
        (company_code_norm(company_code), str(dependent_id)),
    )
    row = cur.fetchone()
    return _decorate_dependent(dict(row)) if row else None


def edit_dependent(
    cur: Any,
    *,
    company_code: str,
    dependent_id: str,
    actor_phone: str,
    reason: str,
    expected_version: int | None = None,
    name_en: str | None = None,
    name_ar: str | None = None,
    relationship: str | None = None,
    date_of_birth: date | str | None = None,
    identity_meta: dict[str, Any] | None = None,
    evidence_ref: str | None = None,
) -> dict[str, Any]:
    if not str(reason or "").strip():
        return {"ok": False, "error": "audit_reason_required"}
    enabled = module_enabled_for_company(cur, company_code)
    if not enabled.get("ok"):
        return enabled
    if not enabled["settings"].get("dependents_enabled"):
        return {"ok": False, "error": "dependents_disabled"}
    dep = get_dependent(cur, company_code=company_code, dependent_id=dependent_id)
    if not dep:
        return {"ok": False, "error": "dependent_not_found"}
    if dep.get("status") != "active":
        return {"ok": False, "error": "dependent_not_active"}
    if expected_version is not None and int(dep.get("row_version") or 0) != int(expected_version):
        return {"ok": False, "error": "stale_row_version", "row_version": dep.get("row_version")}
    rel = str(relationship or dep["relationship"]).strip().lower()
    if rel not in DEP_RELATIONS:
        return {"ok": False, "error": "invalid_relationship"}
    name = str(name_en if name_en is not None else dep["name_en"]).strip()
    dob = date_of_birth if date_of_birth is not None else dep.get("date_of_birth")
    fp = _dep_fingerprint(relationship=rel, name_en=name, date_of_birth=dob)
    company = company_code_norm(company_code)
    cur.execute(
        """
        SELECT dependent_id FROM employee_dependents
         WHERE company_code=%s AND employee_key=%s AND duplicate_fingerprint=%s
           AND status='active' AND dependent_id <> %s
        """,
        (company, dep["employee_key"], fp, dependent_id),
    )
    if cur.fetchone():
        return {"ok": False, "error": "duplicate_dependent"}
    meta = identity_meta if identity_meta is not None else (dep.get("identity_meta") or {})
    cur.execute(
        """
        UPDATE employee_dependents
           SET relationship=%s,
               name_en=%s,
               name_ar=%s,
               date_of_birth=%s,
               identity_meta=%s::jsonb,
               evidence_ref=COALESCE(%s, evidence_ref),
               duplicate_fingerprint=%s,
               row_version = row_version + 1,
               updated_by_phone=%s,
               updated_at=now()
         WHERE company_code=%s AND dependent_id=%s AND status='active'
           AND (%s::int IS NULL OR row_version=%s)
        RETURNING *
        """,
        (
            rel,
            name,
            (str(name_ar).strip() if name_ar is not None else dep.get("name_ar")),
            dob,
            json.dumps(meta, default=str),
            evidence_ref,
            fp,
            _digits(actor_phone),
            company,
            dependent_id,
            expected_version,
            expected_version,
        ),
    )
    row = cur.fetchone()
    if not row:
        return {"ok": False, "error": "stale_row_version_or_missing"}
    d = dict(row)
    _dep_history(
        cur,
        company_code=company,
        employee_key=str(dep["employee_key"]),
        dependent_id=str(dependent_id),
        action="edit",
        before=dep,
        after=d,
        actor_phone=actor_phone,
        reason=reason,
    )
    _audit(
        cur,
        company_code=company,
        action="dependent_edited",
        actor_phone=actor_phone,
        reason=reason,
        subject_type="dependent",
        subject_id=str(dependent_id),
    )
    return {"ok": True, "dependent": _decorate_dependent(d)}


def archive_dependent(
    cur: Any,
    *,
    company_code: str,
    dependent_id: str,
    actor_phone: str,
    reason: str,
    expected_version: int | None = None,
) -> dict[str, Any]:
    if not str(reason or "").strip():
        return {"ok": False, "error": "audit_reason_required"}
    enabled = module_enabled_for_company(cur, company_code)
    if not enabled.get("ok"):
        return enabled
    if not enabled["settings"].get("dependents_enabled"):
        return {"ok": False, "error": "dependents_disabled"}
    dep = get_dependent(cur, company_code=company_code, dependent_id=dependent_id)
    if not dep:
        return {"ok": False, "error": "dependent_not_found"}
    if expected_version is not None and int(dep.get("row_version") or 0) != int(expected_version):
        return {"ok": False, "error": "stale_row_version"}
    company = company_code_norm(company_code)
    cur.execute(
        """
        UPDATE employee_dependents
           SET status='archived',
               archived_by_phone=%s,
               archived_at=now(),
               row_version = row_version + 1,
               updated_by_phone=%s,
               updated_at=now()
         WHERE company_code=%s AND dependent_id=%s AND status='active'
           AND (%s::int IS NULL OR row_version=%s)
        RETURNING *
        """,
        (
            _digits(actor_phone),
            _digits(actor_phone),
            company,
            dependent_id,
            expected_version,
            expected_version,
        ),
    )
    row = cur.fetchone()
    if not row:
        return {"ok": False, "error": "stale_row_version_or_missing"}
    d = dict(row)
    _dep_history(
        cur,
        company_code=company,
        employee_key=str(dep["employee_key"]),
        dependent_id=str(dependent_id),
        action="archive",
        before=dep,
        after=d,
        actor_phone=actor_phone,
        reason=reason,
    )
    _audit(
        cur,
        company_code=company,
        action="dependent_archived",
        actor_phone=actor_phone,
        reason=reason,
        subject_type="dependent",
        subject_id=str(dependent_id),
    )
    return {"ok": True, "dependent": _decorate_dependent(d)}


def request_dependent_change(
    cur: Any,
    *,
    company_code: str,
    employee_key: str,
    action: str,
    actor_phone: str,
    proposed: dict[str, Any],
    dependent_id: str | None = None,
) -> dict[str, Any]:
    enabled = module_enabled_for_company(cur, company_code)
    if not enabled.get("ok"):
        return enabled
    settings = enabled["settings"]
    if not settings.get("dependents_enabled"):
        return {"ok": False, "error": "dependents_disabled"}
    act = str(action or "").strip().lower()
    if act not in ("create", "edit", "archive"):
        return {"ok": False, "error": "invalid_dependent_action"}
    snap = _employee_snapshot(cur, company_code=company_code, employee_key=employee_key)
    if snap.get("missing"):
        return {"ok": False, "error": "employee_not_found"}
    if act in ("edit", "archive") and not dependent_id:
        return {"ok": False, "error": "dependent_id_required"}
    company = company_code_norm(company_code)
    # If HR review not required, apply immediately via HR-style path still audited
    if not settings.get("dependents_require_hr_review"):
        if act == "create":
            return create_dependent(
                cur,
                company_code=company,
                employee_key=employee_key,
                relationship=str(proposed.get("relationship") or ""),
                name_en=str(proposed.get("name_en") or ""),
                name_ar=proposed.get("name_ar"),
                date_of_birth=proposed.get("date_of_birth"),
                identity_meta=proposed.get("identity_meta") if isinstance(proposed.get("identity_meta"), dict) else None,
                evidence_ref=proposed.get("evidence_ref"),
                actor_phone=actor_phone,
                reason="employee_self_service_direct",
            )
        if act == "edit":
            return edit_dependent(
                cur,
                company_code=company,
                dependent_id=str(dependent_id),
                actor_phone=actor_phone,
                reason="employee_self_service_direct",
                **{k: proposed[k] for k in ("name_en", "name_ar", "relationship", "date_of_birth", "identity_meta", "evidence_ref") if k in proposed},
            )
        return archive_dependent(
            cur,
            company_code=company,
            dependent_id=str(dependent_id),
            actor_phone=actor_phone,
            reason="employee_self_service_direct",
        )
    cur.execute(
        """
        INSERT INTO employee_dependent_change_requests (
          company_code, employee_key, action, dependent_id, status, proposed, requested_by_phone
        ) VALUES (%s,%s,%s,%s,'requested',%s::jsonb,%s)
        RETURNING *
        """,
        (
            company,
            employee_key,
            act,
            dependent_id,
            json.dumps(proposed or {}, default=str),
            _digits(actor_phone),
        ),
    )
    row = dict(cur.fetchone())
    _audit(
        cur,
        company_code=company,
        action="dependent_change_requested",
        actor_phone=actor_phone,
        subject_type="dependent_change_request",
        subject_id=str(row["change_request_id"]),
        payload={"action": act},
    )
    return {"ok": True, "change_request": row, "requires_hr_review": True}


def review_dependent_change(
    cur: Any,
    *,
    company_code: str,
    change_request_id: str,
    actor_phone: str,
    decision: str,
    reason: str,
    expected_version: int | None = None,
) -> dict[str, Any]:
    if not str(reason or "").strip():
        return {"ok": False, "error": "audit_reason_required"}
    enabled = module_enabled_for_company(cur, company_code)
    if not enabled.get("ok"):
        return enabled
    settings = enabled["settings"]
    company = company_code_norm(company_code)
    cur.execute(
        """
        SELECT * FROM employee_dependent_change_requests
         WHERE company_code=%s AND change_request_id=%s
        """,
        (company, str(change_request_id)),
    )
    row = cur.fetchone()
    if not row:
        return {"ok": False, "error": "change_request_not_found"}
    req = dict(row)
    if expected_version is not None and int(req.get("row_version") or 0) != int(expected_version):
        return {"ok": False, "error": "stale_row_version"}
    if req.get("status") not in ("requested", "under_review"):
        return {"ok": False, "error": "invalid_status_transition", "status": req.get("status")}
    if settings.get("require_distinct_approver") and _digits(actor_phone) == _digits(req.get("requested_by_phone")):
        return {"ok": False, "error": "sod_self_approve_forbidden"}
    dec = str(decision or "").strip().lower()
    if dec == "reject":
        cur.execute(
            """
            UPDATE employee_dependent_change_requests
               SET status='rejected', reviewed_by_phone=%s, reviewed_at=now(),
                   decision_note=%s, row_version=row_version+1, updated_at=now()
             WHERE company_code=%s AND change_request_id=%s
            RETURNING *
            """,
            (_digits(actor_phone), str(reason).strip()[:500], company, str(change_request_id)),
        )
        out = dict(cur.fetchone())
        _audit(
            cur,
            company_code=company,
            action="dependent_change_rejected",
            actor_phone=actor_phone,
            reason=reason,
            subject_type="dependent_change_request",
            subject_id=str(change_request_id),
        )
        return {"ok": True, "change_request": out}
    if dec != "approve":
        return {"ok": False, "error": "invalid_decision"}

    cur.execute(
        """
        UPDATE employee_dependent_change_requests
           SET status='under_review', reviewed_by_phone=%s, reviewed_at=now(),
               row_version=row_version+1, updated_at=now()
         WHERE company_code=%s AND change_request_id=%s
        RETURNING *
        """,
        (_digits(actor_phone), company, str(change_request_id)),
    )
    req = dict(cur.fetchone())
    proposed = req.get("proposed") or {}
    if isinstance(proposed, str):
        proposed = json.loads(proposed)
    act = str(req.get("action") or "")
    applied: dict[str, Any]
    if act == "create":
        applied = create_dependent(
            cur,
            company_code=company,
            employee_key=str(req["employee_key"]),
            relationship=str(proposed.get("relationship") or ""),
            name_en=str(proposed.get("name_en") or ""),
            name_ar=proposed.get("name_ar"),
            date_of_birth=proposed.get("date_of_birth"),
            identity_meta=proposed.get("identity_meta") if isinstance(proposed.get("identity_meta"), dict) else None,
            evidence_ref=proposed.get("evidence_ref"),
            actor_phone=actor_phone,
            reason=reason,
        )
    elif act == "edit":
        applied = edit_dependent(
            cur,
            company_code=company,
            dependent_id=str(req.get("dependent_id")),
            actor_phone=actor_phone,
            reason=reason,
            name_en=proposed.get("name_en"),
            name_ar=proposed.get("name_ar"),
            relationship=proposed.get("relationship"),
            date_of_birth=proposed.get("date_of_birth"),
            identity_meta=proposed.get("identity_meta") if isinstance(proposed.get("identity_meta"), dict) else None,
            evidence_ref=proposed.get("evidence_ref"),
        )
    elif act == "archive":
        applied = archive_dependent(
            cur,
            company_code=company,
            dependent_id=str(req.get("dependent_id")),
            actor_phone=actor_phone,
            reason=reason,
        )
    else:
        return {"ok": False, "error": "invalid_dependent_action"}
    if not applied.get("ok"):
        return applied
    dep_id = None
    if applied.get("dependent"):
        dep_id = str(applied["dependent"].get("dependent_id") or req.get("dependent_id") or "")
    cur.execute(
        """
        UPDATE employee_dependent_change_requests
           SET status='applied',
               dependent_id=COALESCE(%s::uuid, dependent_id),
               decision_note=%s,
               row_version=row_version+1,
               updated_at=now()
         WHERE company_code=%s AND change_request_id=%s
        RETURNING *
        """,
        (dep_id, str(reason).strip()[:500], company, str(change_request_id)),
    )
    out = dict(cur.fetchone())
    _audit(
        cur,
        company_code=company,
        action="dependent_change_applied",
        actor_phone=actor_phone,
        reason=reason,
        subject_type="dependent_change_request",
        subject_id=str(change_request_id),
        payload={"action": act, "dependent_id": dep_id},
    )
    return {"ok": True, "change_request": out, "dependent": applied.get("dependent")}


def list_dependents_for_employee(
    cur: Any,
    *,
    company_code: str,
    employee_key: str,
    include_archived: bool = False,
) -> dict[str, Any]:
    enabled = module_enabled_for_company(cur, company_code)
    if not enabled.get("ok"):
        return enabled
    if not enabled["settings"].get("dependents_enabled"):
        return {"ok": False, "error": "dependents_disabled", "dependents": []}
    company = company_code_norm(company_code)
    if include_archived:
        cur.execute(
            """
            SELECT * FROM employee_dependents
             WHERE company_code=%s AND employee_key=%s
             ORDER BY created_at
            """,
            (company, employee_key),
        )
    else:
        cur.execute(
            """
            SELECT * FROM employee_dependents
             WHERE company_code=%s AND employee_key=%s AND status='active'
             ORDER BY created_at
            """,
            (company, employee_key),
        )
    rows = [_decorate_dependent(dict(r)) for r in (cur.fetchall() or [])]
    return {"ok": True, "dependents": rows}


def list_letter_requests_for_employee(
    cur: Any,
    *,
    company_code: str,
    employee_key: str,
) -> dict[str, Any]:
    enabled = module_enabled_for_company(cur, company_code)
    if not enabled.get("ok"):
        return enabled
    if not enabled["settings"].get("letters_enabled"):
        return {"ok": False, "error": "letters_disabled", "requests": []}
    cur.execute(
        """
        SELECT * FROM ess_letter_requests
         WHERE company_code=%s AND employee_key=%s
         ORDER BY created_at DESC
        """,
        (company_code_norm(company_code), employee_key),
    )
    return {"ok": True, "requests": [_decorate_letter_request(dict(r)) for r in (cur.fetchall() or [])]}
