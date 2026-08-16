#!/usr/bin/env python3
"""Wave 5 C3 — Recruiting + Hire→Ready Intelligence (company-scoped).

Builds on frozen C1 Registry/evaluator (+ C2 hire authority for reconciliation).
Commercial key remains `analytics`. Internal namespace: hr_intelligence_*.

Authority:
  - Requisition / application / offer / hire-bridge projections (not alternate SoT)
  - Time-to-fill / time-to-hire with explicit Registry milestones
  - Offer acceptance + source metrics (no universal effectiveness score)
  - Preboarding / onboarding / probation Hire→Ready metrics (module-gated)
  - Formula kinds registered into C1 shared evaluator

Does NOT:
  - Create a second analytics math engine
  - Duplicate hire authority (uses canonical employment_period_key bridge)
  - Invent source from free text
  - Publish a single "source effectiveness" score
  - UI dashboard redesign
"""
from __future__ import annotations

import json
import os
import uuid
from datetime import date, datetime, timedelta, timezone
from typing import Any

import hr_intelligence_registry_c1 as c1

PHASE = "hr_intelligence_recruiting_c3"
CONTRACT_VERSION = "hr_intelligence_recruiting_c3_v1"
PASS_STAMP = "HR_INTELLIGENCE_RECRUITING_FULL_PASS"
COMMERCIAL_MODULE_KEY = "analytics"
_ON = {"1", "true", "yes", "on"}

# Charter-locked TTF milestones (explicit in formula_contract — never buried in SQL alone)
TTF_MILESTONES = {
    "start_milestone": "requisition_opened",
    "end_milestone": "requisition_filled",
    "elapsed": "calendar_days",
    "cancelled_behavior": "exclude_from_completed_observations",
    "reopened_behavior": "new_open_cycle_from_reopen_event",
    "unfilled_behavior": "exclude_from_average_insufficient_if_none",
    "internal_vs_external_fill": "include_same_treatment",
}

TTH_MILESTONES = {
    "start_milestone": "application_received",
    "end_milestone": "hire_completed",
    "elapsed": "calendar_days",
    "terminal_non_hire": ["rejected", "withdrawn"],
    "include_only_completed_hires": True,
    "distinct_from_time_to_fill": True,
}

# Governed source taxonomy — unknown stays unknown (never invent "organic")
SOURCE_TAXONOMY = (
    "careers_site",
    "referral",
    "recruiter_manual",
    "agency",
    "job_board",
    "imported_migrated",
    "whatsapp",
    "email",
    "other",
    "unknown",
)

SOURCE_LABELS = {
    "careers_site": {"en": "Careers site", "ar": "موقع الوظائف"},
    "referral": {"en": "Referral", "ar": "إحالة"},
    "recruiter_manual": {"en": "Recruiter / manual", "ar": "مسؤول توظيف / يدوي"},
    "agency": {"en": "Agency", "ar": "وكالة"},
    "job_board": {"en": "Job board", "ar": "لوحة وظائف"},
    "imported_migrated": {"en": "Imported / migrated", "ar": "مستورد / مرحّل"},
    "whatsapp": {"en": "WhatsApp", "ar": "واتساب"},
    "email": {"en": "Email", "ar": "بريد"},
    "other": {"en": "Other (governed)", "ar": "أخرى (محكومة)"},
    "unknown": {"en": "Unknown", "ar": "غير معروف"},
}

TTF_KEY = "recruiting.time_to_fill"
TTH_KEY = "recruiting.time_to_hire"
OFFER_ISSUED_KEY = "recruiting.offers.issued"
OFFER_ACCEPTED_KEY = "recruiting.offers.accepted"
OFFER_DECLINED_KEY = "recruiting.offers.declined"
OFFER_ACCEPT_RATE_KEY = "recruiting.offer_acceptance_rate"
APPS_BY_SOURCE_KEY = "recruiting.applications_by_source"
HIRES_BY_SOURCE_KEY = "recruiting.hires_by_source"
OFFER_ACCEPTS_BY_SOURCE_KEY = "recruiting.offer_accepts_by_source"
APP_HIRE_CONV_KEY = "recruiting.application_to_hire_by_source"
RECRUITING_HIRES_KEY = "recruiting.hires.count"
FUNNEL_KEY = "recruiting.funnel.events"
PREBOARD_RATE_KEY = "hire_ready.preboarding_completion_rate"
ONBOARD_RATE_KEY = "hire_ready.onboarding_completion_rate"
ONBOARD_TIME_KEY = "hire_ready.onboarding_completion_time"
PROBATION_KEY = "hire_ready.probation_outcomes"

# Explicitly NOT published — no universal source effectiveness score
FORBIDDEN_SCORE_KEY = "recruiting.source_effectiveness_score"

STATUS_LABELS = {
    "draft": {"en": "Draft", "ar": "مسودة"},
    "open": {"en": "Open", "ar": "مفتوح"},
    "filled": {"en": "Filled", "ar": "مُشغل"},
    "cancelled": {"en": "Cancelled", "ar": "ملغى"},
    "paused": {"en": "Paused", "ar": "موقوف مؤقتاً"},
    "reopened": {"en": "Reopened", "ar": "أُعيد فتحه"},
    "issued": {"en": "Issued", "ar": "مُصدَر"},
    "accepted": {"en": "Accepted", "ar": "مقبول"},
    "declined": {"en": "Declined", "ar": "مرفوض"},
    "expired": {"en": "Expired", "ar": "منتهٍ"},
    "withdrawn": {"en": "Withdrawn", "ar": "مسحوب"},
    "insufficient_data": {"en": "Insufficient data", "ar": "بيانات غير كافية"},
    "not_applicable": {"en": "Not applicable", "ar": "غير منطبق"},
    "unavailable": {"en": "Unavailable", "ar": "غير متاح"},
    "suppressed": {"en": "Suppressed", "ar": "محجوب"},
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


def source_label(source: str | None, *, lang: str = "en") -> str:
    key = normalize_source(source)
    pack = SOURCE_LABELS.get(key) or SOURCE_LABELS["unknown"]
    return str(pack.get("ar" if lang.lower().startswith("ar") else "en"))


def normalize_source(raw: Any) -> str:
    """Map only known governed tokens. Never invent organic/campaign from free text."""
    s = str(raw or "").strip().lower()
    if not s:
        return "unknown"
    if s in SOURCE_TAXONOMY:
        return s
    # token maps — explicit only
    if any(t in s for t in ("career", "careers_site", "website_apply")):
        return "careers_site"
    if any(t in s for t in ("referral", "referred")):
        return "referral"
    if any(t in s for t in ("agency", "staffing")):
        return "agency"
    if any(t in s for t in ("job_board", "linkedin", "bayt", "indeed")):
        return "job_board"
    if any(t in s for t in ("bulk", "import", "migrat", "csv", "spreadsheet")):
        return "imported_migrated"
    if any(t in s for t in ("whatsapp", "apply_code", "qr")):
        return "whatsapp"
    if any(t in s for t in ("email", "mailbox")):
        return "email"
    if any(t in s for t in ("manual", "recruiter", "dashboard", "operator")):
        return "recruiter_manual"
    if s in ("other", "governed_other"):
        return "other"
    return "unknown"


def honesty_payload(*, company_code: str | None = None) -> dict[str, Any]:
    return {
        "phase": PHASE,
        "contract_version": CONTRACT_VERSION,
        "pass_stamp": PASS_STAMP,
        "commercial_module_key": COMMERCIAL_MODULE_KEY,
        "uses_c1_registry_evaluator": True,
        "no_second_analytics_math_engine": True,
        "ttf_milestones": dict(TTF_MILESTONES),
        "tth_milestones": dict(TTH_MILESTONES),
        "ttf_distinct_from_tth": True,
        "no_universal_source_effectiveness_score": True,
        "unknown_source_stays_unknown": True,
        "no_source_from_freetext_invention": True,
        "canonical_hire_bridge": True,
        "reconciles_with_c2_hire_authority": True,
        "module_off_returns_unavailable_not_fake_zero": True,
        "demographics_off_by_default": True,
        "assistant_mutations": False,
        "forbidden_semantic_keys": [FORBIDDEN_SCORE_KEY],
        "company_code": company_code_norm(company_code) if company_code else None,
    }


def rollback_guidance() -> dict[str, Any]:
    return {
        "phase": PHASE,
        "preserves_history": True,
        "steps": [
            "WATHEFNI_HR_INTELLIGENCE_RECRUITING_C3=off",
            "Clear WATHEFNI_HR_INTELLIGENCE_RECRUITING_COMPANIES",
            "WATHEFNI_ANALYTICS_KILL=on (optional)",
            "C1/C2 history retained",
        ],
    }


def runtime_gate_for_company(company_code: str | None) -> dict[str, Any]:
    company = company_code_norm(company_code)
    if not company:
        return {"ok": False, "enabled": False, "error": "company_required", "phase": PHASE}
    if _env_on("WATHEFNI_ANALYTICS_KILL", "off"):
        return {"ok": False, "enabled": False, "error": "analytics_kill_switch", "gate": "kill", "phase": PHASE}
    c1_gate = c1.runtime_gate_for_company(company)
    if not c1_gate.get("ok"):
        return {**c1_gate, "error": "c1_registry_required", "phase": PHASE}
    if not _env_on("WATHEFNI_HR_INTELLIGENCE_RECRUITING_C3", "off"):
        return {
            "ok": False,
            "enabled": False,
            "error": "hr_intelligence_recruiting_c3_off",
            "gate": "runtime_flag",
            "phase": PHASE,
        }
    raw = str(os.environ.get("WATHEFNI_HR_INTELLIGENCE_RECRUITING_COMPANIES") or "").strip()
    allow = {p.strip().upper() for p in raw.split(",") if p.strip()} if raw else set()
    if not allow:
        return {
            "ok": False,
            "enabled": False,
            "error": "hr_intelligence_recruiting_company_not_allowlisted",
            "gate": "company_allowlist",
            "phase": PHASE,
        }
    if company not in allow:
        return {
            "ok": False,
            "enabled": False,
            "error": "hr_intelligence_recruiting_company_not_allowlisted",
            "gate": "company_allowlist",
            "phase": PHASE,
            "company_code": company,
        }
    return {"ok": True, "enabled": True, "company_code": company, "phase": PHASE}


def ensure_hr_intelligence_recruiting_c3_schema(cur: Any, *, force: bool = False) -> None:
    _ = force
    c1.ensure_hr_intelligence_registry_c1_schema(cur)
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS hr_intelligence_c3_company_settings (
          company_code text PRIMARY KEY,
          enabled boolean NOT NULL DEFAULT false,
          recruiting_module_enabled boolean NOT NULL DEFAULT true,
          preboarding_module_enabled boolean NOT NULL DEFAULT true,
          onboarding_module_enabled boolean NOT NULL DEFAULT true,
          probation_module_enabled boolean NOT NULL DEFAULT true,
          source_taxonomy jsonb NOT NULL DEFAULT '[]'::jsonb,
          enabled_by_phone text,
          enabled_reason text,
          enabled_at timestamptz,
          disabled_at timestamptz,
          updated_at timestamptz NOT NULL DEFAULT now()
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS hr_intelligence_recruiting_requisitions (
          row_id uuid PRIMARY KEY,
          company_code text NOT NULL,
          requisition_key text NOT NULL,
          status text NOT NULL,
          opened_at date,
          filled_at date,
          cancelled_at date,
          reopened_at date,
          open_cycle_id text NOT NULL DEFAULT '1',
          fill_type text,
          department text,
          location text,
          job_role text,
          hiring_manager_key text,
          recruiter_key text,
          headcount_openings integer NOT NULL DEFAULT 1,
          dims_effective_from date,
          source_authority text NOT NULL DEFAULT 'domain_requisition',
          source_version text,
          event_time timestamptz,
          recorded_at timestamptz NOT NULL DEFAULT now(),
          superseded_by uuid,
          UNIQUE (company_code, requisition_key, open_cycle_id)
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS hr_intelligence_recruiting_applications (
          row_id uuid PRIMARY KEY,
          company_code text NOT NULL,
          application_key text NOT NULL,
          person_key text,
          requisition_key text,
          job_key text,
          status text NOT NULL,
          source_bucket text NOT NULL DEFAULT 'unknown',
          received_at date,
          hired_at date,
          rejected_at date,
          withdrawn_at date,
          merged_into_application_key text,
          hiring_manager_key text,
          recruiter_key text,
          department text,
          location text,
          job_role text,
          source_authority text NOT NULL DEFAULT 'domain_application',
          source_version text,
          event_time timestamptz,
          recorded_at timestamptz NOT NULL DEFAULT now(),
          superseded_by uuid,
          UNIQUE (company_code, application_key)
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS hr_intelligence_recruiting_offers (
          row_id uuid PRIMARY KEY,
          company_code text NOT NULL,
          business_offer_key text NOT NULL,
          offer_version integer NOT NULL DEFAULT 1,
          application_key text,
          person_key text,
          status text NOT NULL,
          issued_at date,
          accepted_at date,
          declined_at date,
          expired_at date,
          withdrawn_at date,
          superseded_by_version integer,
          is_current_business_offer boolean NOT NULL DEFAULT true,
          source_bucket text NOT NULL DEFAULT 'unknown',
          hiring_manager_key text,
          recruiter_key text,
          department text,
          job_role text,
          source_authority text NOT NULL DEFAULT 'domain_offer',
          source_version text,
          event_time timestamptz,
          recorded_at timestamptz NOT NULL DEFAULT now(),
          superseded_by uuid,
          UNIQUE (company_code, business_offer_key, offer_version)
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS hr_intelligence_recruiting_hires (
          row_id uuid PRIMARY KEY,
          company_code text NOT NULL,
          hire_operation_key text NOT NULL,
          employment_period_key text NOT NULL,
          application_key text,
          person_key text,
          requisition_key text,
          job_key text,
          hire_completed_at date NOT NULL,
          source_bucket text NOT NULL DEFAULT 'unknown',
          department text,
          hiring_manager_key text,
          recruiter_key text,
          source_authority text NOT NULL DEFAULT 'domain_hire_bridge',
          source_version text,
          event_time timestamptz,
          recorded_at timestamptz NOT NULL DEFAULT now(),
          superseded_by uuid,
          UNIQUE (company_code, hire_operation_key),
          UNIQUE (company_code, employment_period_key)
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS hr_intelligence_funnel_events (
          event_id uuid PRIMARY KEY,
          company_code text NOT NULL,
          application_key text NOT NULL,
          from_stage text,
          to_stage text NOT NULL,
          event_at date NOT NULL,
          source_authority text NOT NULL DEFAULT 'domain_lifecycle',
          recorded_at timestamptz NOT NULL DEFAULT now(),
          superseded_by uuid,
          UNIQUE (company_code, application_key, to_stage, event_at)
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS hr_intelligence_hire_ready_cases (
          row_id uuid PRIMARY KEY,
          company_code text NOT NULL,
          case_type text NOT NULL,
          case_key text NOT NULL,
          employment_period_key text,
          application_key text,
          status text NOT NULL,
          started_at date,
          completed_at date,
          outcome text,
          template_version text,
          duration_days integer,
          source_authority text NOT NULL,
          source_version text,
          event_time timestamptz,
          recorded_at timestamptz NOT NULL DEFAULT now(),
          superseded_by uuid,
          UNIQUE (company_code, case_type, case_key)
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS hr_intelligence_c3_audit (
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
        """
    )


def _audit(cur, *, company_code, action, actor_phone, reason=None, subject_type=None, subject_id=None, payload=None):
    cur.execute(
        """
        INSERT INTO hr_intelligence_c3_audit
          (company_code, action, actor_phone, reason, subject_type, subject_id, payload)
        VALUES (%s,%s,%s,%s,%s,%s,%s::jsonb)
        """,
        (
            company_code_norm(company_code) if company_code else None,
            action,
            _digits(actor_phone) if actor_phone else None,
            (str(reason).strip()[:500] if reason else None),
            subject_type,
            subject_id,
            json.dumps(payload or {}, default=str),
        ),
    )


def _entitled(cur, company_code: str) -> dict[str, Any]:
    gate = runtime_gate_for_company(company_code)
    if not gate.get("ok"):
        return gate
    company = gate["company_code"]
    ensure_hr_intelligence_recruiting_c3_schema(cur)
    c1_ent = c1._entitled(cur, company)
    if not c1_ent.get("ok"):
        return {"ok": False, "error": "c1_company_intelligence_disabled", "detail": c1_ent}
    cur.execute("SELECT * FROM hr_intelligence_c3_company_settings WHERE company_code=%s", (company,))
    row = cur.fetchone()
    if not row or not bool(dict(row).get("enabled")):
        return {"ok": False, "error": "company_recruiting_intelligence_disabled", "company_code": company}
    return {"ok": True, "company_code": company, "settings": dict(row), "c1_settings": c1_ent["settings"]}


def enable_company_recruiting_intelligence(
    cur: Any,
    *,
    company_code: str,
    actor_phone: str,
    reason: str,
    recruiting_module_enabled: bool = True,
    preboarding_module_enabled: bool = True,
    onboarding_module_enabled: bool = True,
    probation_module_enabled: bool = True,
) -> dict[str, Any]:
    if not str(reason or "").strip():
        return {"ok": False, "error": "audit_reason_required"}
    gate = runtime_gate_for_company(company_code)
    if not gate.get("ok"):
        return gate
    company = gate["company_code"]
    c1.enable_company_hr_intelligence(cur, company_code=company, actor_phone=actor_phone, reason="c3 requires c1")
    ensure_hr_intelligence_recruiting_c3_schema(cur)
    cur.execute(
        """
        INSERT INTO hr_intelligence_c3_company_settings (
          company_code, enabled, recruiting_module_enabled, preboarding_module_enabled,
          onboarding_module_enabled, probation_module_enabled, source_taxonomy,
          enabled_by_phone, enabled_reason, enabled_at, disabled_at, updated_at
        ) VALUES (%s,true,%s,%s,%s,%s,%s::jsonb,%s,%s,now(),NULL,now())
        ON CONFLICT (company_code) DO UPDATE SET
          enabled=true,
          recruiting_module_enabled=EXCLUDED.recruiting_module_enabled,
          preboarding_module_enabled=EXCLUDED.preboarding_module_enabled,
          onboarding_module_enabled=EXCLUDED.onboarding_module_enabled,
          probation_module_enabled=EXCLUDED.probation_module_enabled,
          source_taxonomy=EXCLUDED.source_taxonomy,
          enabled_by_phone=EXCLUDED.enabled_by_phone,
          enabled_reason=EXCLUDED.enabled_reason,
          enabled_at=now(),
          disabled_at=NULL,
          updated_at=now()
        RETURNING *
        """,
        (
            company,
            bool(recruiting_module_enabled),
            bool(preboarding_module_enabled),
            bool(onboarding_module_enabled),
            bool(probation_module_enabled),
            json.dumps(list(SOURCE_TAXONOMY)),
            _digits(actor_phone),
            str(reason).strip()[:500],
        ),
    )
    row = dict(cur.fetchone())
    _audit(cur, company_code=company, action="company_enabled", actor_phone=actor_phone, reason=reason, subject_type="company", subject_id=company)
    seed_recruiting_definitions(cur, actor_phone=actor_phone)
    _register_handlers()
    return {"ok": True, "settings": row, **honesty_payload(company_code=company)}


def disable_company_recruiting_intelligence(cur, *, company_code: str, actor_phone: str, reason: str) -> dict[str, Any]:
    if not str(reason or "").strip():
        return {"ok": False, "error": "audit_reason_required"}
    company = company_code_norm(company_code)
    ensure_hr_intelligence_recruiting_c3_schema(cur)
    cur.execute(
        """
        UPDATE hr_intelligence_c3_company_settings
           SET enabled=false, disabled_at=now(), updated_at=now()
         WHERE company_code=%s RETURNING *
        """,
        (company,),
    )
    row = cur.fetchone()
    _audit(cur, company_code=company, action="company_disabled", actor_phone=actor_phone, reason=reason, payload={"preserves_history": True})
    return {"ok": True, "settings": dict(row) if row else None, "preserves_history": True}


def set_module_flags(
    cur,
    *,
    company_code: str,
    actor_phone: str,
    reason: str,
    recruiting_module_enabled: bool | None = None,
    preboarding_module_enabled: bool | None = None,
    onboarding_module_enabled: bool | None = None,
    probation_module_enabled: bool | None = None,
) -> dict[str, Any]:
    if not str(reason or "").strip():
        return {"ok": False, "error": "audit_reason_required"}
    ent = _entitled(cur, company_code)
    if not ent.get("ok"):
        return ent
    company = ent["company_code"]
    s = ent["settings"]
    vals = {
        "recruiting_module_enabled": s["recruiting_module_enabled"] if recruiting_module_enabled is None else bool(recruiting_module_enabled),
        "preboarding_module_enabled": s["preboarding_module_enabled"] if preboarding_module_enabled is None else bool(preboarding_module_enabled),
        "onboarding_module_enabled": s["onboarding_module_enabled"] if onboarding_module_enabled is None else bool(onboarding_module_enabled),
        "probation_module_enabled": s["probation_module_enabled"] if probation_module_enabled is None else bool(probation_module_enabled),
    }
    cur.execute(
        """
        UPDATE hr_intelligence_c3_company_settings SET
          recruiting_module_enabled=%s,
          preboarding_module_enabled=%s,
          onboarding_module_enabled=%s,
          probation_module_enabled=%s,
          updated_at=now()
         WHERE company_code=%s RETURNING *
        """,
        (
            vals["recruiting_module_enabled"],
            vals["preboarding_module_enabled"],
            vals["onboarding_module_enabled"],
            vals["probation_module_enabled"],
            company,
        ),
    )
    row = dict(cur.fetchone())
    _audit(cur, company_code=company, action="module_flags_updated", actor_phone=actor_phone, reason=reason, payload=vals)
    return {"ok": True, "settings": row}


def _as_date(value: Any) -> date | None:
    if value is None or value == "":
        return None
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, datetime):
        return value.date()
    return date.fromisoformat(str(value)[:10])


def _parse_window(time_window: dict[str, Any]) -> tuple[date, date]:
    start = _as_date(time_window.get("period_start") or time_window.get("start"))
    end = _as_date(time_window.get("period_end") or time_window.get("end"))
    if not start or not end:
        end = date.today()
        start = end - timedelta(days=90)
    return start, end


def _scope_ok(row: dict[str, Any], filters: dict[str, Any], actor_role: str) -> bool:
    if actor_role == "hiring_manager":
        allowed = set(filters.get("hiring_manager_scope_keys") or [])
        if not allowed:
            return False
        return str(row.get("hiring_manager_key") or "") in allowed
    if actor_role == "recruiter":
        allowed = set(filters.get("recruiter_scope_keys") or [])
        if not allowed:
            return False
        return str(row.get("recruiter_key") or "") in allowed
    return True


def _candidate_drill_allowed(filters: dict[str, Any], actor_role: str) -> bool:
    if actor_role in ("hr", "admin"):
        return True
    return bool(filters.get("has_recruiting_candidate_access"))


# ── Upserts ──────────────────────────────────────────────────────────────────


def upsert_requisition(
    cur,
    *,
    company_code: str,
    actor_phone: str,
    requisition_key: str,
    status: str,
    reason: str,
    opened_at: date | str | None = None,
    filled_at: date | str | None = None,
    cancelled_at: date | str | None = None,
    reopened_at: date | str | None = None,
    open_cycle_id: str = "1",
    fill_type: str | None = None,
    department: str | None = None,
    location: str | None = None,
    job_role: str | None = None,
    hiring_manager_key: str | None = None,
    recruiter_key: str | None = None,
    headcount_openings: int = 1,
    dims_effective_from: date | str | None = None,
    emit_facts: bool = True,
) -> dict[str, Any]:
    if not str(reason or "").strip():
        return {"ok": False, "error": "audit_reason_required"}
    ent = _entitled(cur, company_code)
    if not ent.get("ok"):
        return ent
    company = ent["company_code"]
    st = str(status).strip().lower()
    rid = str(uuid.uuid4())
    oa, fa, ca, ra = _as_date(opened_at), _as_date(filled_at), _as_date(cancelled_at), _as_date(reopened_at)
    def_from = _as_date(dims_effective_from) or oa or date.today()
    cur.execute(
        """
        INSERT INTO hr_intelligence_recruiting_requisitions (
          row_id, company_code, requisition_key, status, opened_at, filled_at, cancelled_at, reopened_at,
          open_cycle_id, fill_type, department, location, job_role, hiring_manager_key, recruiter_key,
          headcount_openings, dims_effective_from, source_version, event_time
        ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,now())
        ON CONFLICT (company_code, requisition_key, open_cycle_id) DO UPDATE SET
          status=EXCLUDED.status,
          opened_at=EXCLUDED.opened_at,
          filled_at=EXCLUDED.filled_at,
          cancelled_at=EXCLUDED.cancelled_at,
          reopened_at=EXCLUDED.reopened_at,
          fill_type=EXCLUDED.fill_type,
          department=COALESCE(hr_intelligence_recruiting_requisitions.department, EXCLUDED.department),
          location=COALESCE(hr_intelligence_recruiting_requisitions.location, EXCLUDED.location),
          job_role=COALESCE(hr_intelligence_recruiting_requisitions.job_role, EXCLUDED.job_role),
          hiring_manager_key=COALESCE(hr_intelligence_recruiting_requisitions.hiring_manager_key, EXCLUDED.hiring_manager_key),
          recruiter_key=COALESCE(hr_intelligence_recruiting_requisitions.recruiter_key, EXCLUDED.recruiter_key),
          headcount_openings=EXCLUDED.headcount_openings,
          source_version=EXCLUDED.source_version,
          recorded_at=now(),
          superseded_by=NULL
        RETURNING *
        """,
        (
            rid, company, requisition_key, st, oa, fa, ca, ra, str(open_cycle_id),
            fill_type, department, location, job_role, hiring_manager_key, recruiter_key,
            int(headcount_openings or 1), def_from, f"v:{st}:{oa}:{fa}:{open_cycle_id}",
        ),
    )
    row = dict(cur.fetchone())
    # Preserve historical dims: do not overwrite department if already set (COALESCE above)
    if emit_facts:
        c1.ingest_fact(
            cur,
            company_code=company,
            actor_phone=actor_phone,
            fact_type="recruiting_requisition",
            entity_type="requisition",
            entity_id=f"{requisition_key}:{open_cycle_id}",
            source_authority="domain_requisition",
            measures={"status": st, "opened_at": str(oa) if oa else None, "filled_at": str(fa) if fa else None},
            dimensions={"department": row.get("department"), "hiring_manager_key": row.get("hiring_manager_key")},
            ingest_key=f"req:{company}:{requisition_key}:{open_cycle_id}",
            reason=reason,
        )
    return {"ok": True, "requisition": row}


def correct_requisition_dates(
    cur,
    *,
    company_code: str,
    actor_phone: str,
    requisition_key: str,
    reason: str,
    open_cycle_id: str = "1",
    opened_at: date | str | None = None,
    filled_at: date | str | None = None,
) -> dict[str, Any]:
    """Correction via re-upsert + fact supersession — does not rewrite domain audit."""
    ent = _entitled(cur, company_code)
    if not ent.get("ok"):
        return ent
    company = ent["company_code"]
    cur.execute(
        """
        SELECT * FROM hr_intelligence_recruiting_requisitions
         WHERE company_code=%s AND requisition_key=%s AND open_cycle_id=%s AND superseded_by IS NULL
        """,
        (company, requisition_key, open_cycle_id),
    )
    prev = cur.fetchone()
    if not prev:
        return {"ok": False, "error": "requisition_not_found"}
    prev = dict(prev)
    out = upsert_requisition(
        cur,
        company_code=company,
        actor_phone=actor_phone,
        requisition_key=requisition_key,
        status=prev["status"],
        reason=reason,
        opened_at=opened_at if opened_at is not None else prev.get("opened_at"),
        filled_at=filled_at if filled_at is not None else prev.get("filled_at"),
        cancelled_at=prev.get("cancelled_at"),
        reopened_at=prev.get("reopened_at"),
        open_cycle_id=open_cycle_id,
        fill_type=prev.get("fill_type"),
        department=prev.get("department"),
        location=prev.get("location"),
        job_role=prev.get("job_role"),
        hiring_manager_key=prev.get("hiring_manager_key"),
        recruiter_key=prev.get("recruiter_key"),
        headcount_openings=prev.get("headcount_openings") or 1,
        dims_effective_from=prev.get("dims_effective_from"),
    )
    out["domain_audit_rewritten"] = False
    return out


def upsert_application(
    cur,
    *,
    company_code: str,
    actor_phone: str,
    application_key: str,
    status: str,
    reason: str,
    person_key: str | None = None,
    requisition_key: str | None = None,
    job_key: str | None = None,
    source_raw: str | None = None,
    received_at: date | str | None = None,
    hired_at: date | str | None = None,
    rejected_at: date | str | None = None,
    withdrawn_at: date | str | None = None,
    merged_into_application_key: str | None = None,
    hiring_manager_key: str | None = None,
    recruiter_key: str | None = None,
    department: str | None = None,
    location: str | None = None,
    job_role: str | None = None,
    emit_facts: bool = True,
) -> dict[str, Any]:
    if not str(reason or "").strip():
        return {"ok": False, "error": "audit_reason_required"}
    ent = _entitled(cur, company_code)
    if not ent.get("ok"):
        return ent
    company = ent["company_code"]
    bucket = normalize_source(source_raw)
    st = str(status).strip().lower()
    rid = str(uuid.uuid4())
    recv, hired, rej, wit = _as_date(received_at), _as_date(hired_at), _as_date(rejected_at), _as_date(withdrawn_at)
    cur.execute(
        """
        INSERT INTO hr_intelligence_recruiting_applications (
          row_id, company_code, application_key, person_key, requisition_key, job_key, status, source_bucket,
          received_at, hired_at, rejected_at, withdrawn_at, merged_into_application_key,
          hiring_manager_key, recruiter_key, department, location, job_role, source_version, event_time
        ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,now())
        ON CONFLICT (company_code, application_key) DO UPDATE SET
          status=EXCLUDED.status,
          person_key=COALESCE(EXCLUDED.person_key, hr_intelligence_recruiting_applications.person_key),
          requisition_key=COALESCE(EXCLUDED.requisition_key, hr_intelligence_recruiting_applications.requisition_key),
          job_key=COALESCE(EXCLUDED.job_key, hr_intelligence_recruiting_applications.job_key),
          source_bucket=EXCLUDED.source_bucket,
          received_at=EXCLUDED.received_at,
          hired_at=EXCLUDED.hired_at,
          rejected_at=EXCLUDED.rejected_at,
          withdrawn_at=EXCLUDED.withdrawn_at,
          merged_into_application_key=EXCLUDED.merged_into_application_key,
          hiring_manager_key=COALESCE(hr_intelligence_recruiting_applications.hiring_manager_key, EXCLUDED.hiring_manager_key),
          recruiter_key=COALESCE(hr_intelligence_recruiting_applications.recruiter_key, EXCLUDED.recruiter_key),
          department=COALESCE(hr_intelligence_recruiting_applications.department, EXCLUDED.department),
          location=COALESCE(hr_intelligence_recruiting_applications.location, EXCLUDED.location),
          job_role=COALESCE(hr_intelligence_recruiting_applications.job_role, EXCLUDED.job_role),
          recorded_at=now(),
          superseded_by=NULL
        RETURNING *
        """,
        (
            rid, company, application_key, person_key, requisition_key, job_key, st, bucket,
            recv, hired, rej, wit, merged_into_application_key,
            hiring_manager_key, recruiter_key, department, location, job_role, f"v:{st}:{bucket}",
        ),
    )
    row = dict(cur.fetchone())
    if emit_facts and not merged_into_application_key:
        c1.ingest_fact(
            cur,
            company_code=company,
            actor_phone=actor_phone,
            fact_type="recruiting_application",
            entity_type="application",
            entity_id=application_key,
            source_authority="domain_application",
            measures={"status": st},
            dimensions={"source_bucket": bucket, "person_key": person_key, "department": department},
            ingest_key=f"app:{company}:{application_key}",
            reason=reason,
        )
    return {"ok": True, "application": row, "source_bucket": bucket}


def merge_applications(
    cur,
    *,
    company_code: str,
    actor_phone: str,
    survivor_application_key: str,
    merged_application_key: str,
    reason: str,
) -> dict[str, Any]:
    """Candidate merge: mark merged app; do not double-count facts."""
    if not str(reason or "").strip():
        return {"ok": False, "error": "audit_reason_required"}
    ent = _entitled(cur, company_code)
    if not ent.get("ok"):
        return ent
    company = ent["company_code"]
    cur.execute(
        """
        SELECT * FROM hr_intelligence_recruiting_applications
         WHERE company_code=%s AND application_key=%s AND superseded_by IS NULL
        """,
        (company, merged_application_key),
    )
    merged = cur.fetchone()
    if not merged:
        return {"ok": False, "error": "merged_application_not_found"}
    merged = dict(merged)
    out = upsert_application(
        cur,
        company_code=company,
        actor_phone=actor_phone,
        application_key=merged_application_key,
        status="merged",
        reason=reason,
        person_key=merged.get("person_key"),
        requisition_key=merged.get("requisition_key"),
        job_key=merged.get("job_key"),
        source_raw=merged.get("source_bucket"),
        received_at=merged.get("received_at"),
        hired_at=merged.get("hired_at"),
        rejected_at=merged.get("rejected_at"),
        withdrawn_at=merged.get("withdrawn_at"),
        merged_into_application_key=survivor_application_key,
        hiring_manager_key=merged.get("hiring_manager_key"),
        recruiter_key=merged.get("recruiter_key"),
        department=merged.get("department"),
        location=merged.get("location"),
        job_role=merged.get("job_role"),
        emit_facts=False,
    )
    # Supersede facts for merged application (self-supersede → excluded from active fact queries)
    cur.execute(
        """
        UPDATE hr_intelligence_facts
           SET superseded_by=fact_id
         WHERE company_code=%s AND entity_id=%s AND fact_type='recruiting_application'
           AND superseded_by IS NULL
        """,
        (company, merged_application_key),
    )
    _audit(
        cur,
        company_code=company,
        action="application_merged",
        actor_phone=actor_phone,
        reason=reason,
        subject_type="application",
        subject_id=merged_application_key,
        payload={"survivor": survivor_application_key},
    )
    out["survivor"] = survivor_application_key
    out["domain_audit_rewritten"] = False
    return out


def upsert_offer(
    cur,
    *,
    company_code: str,
    actor_phone: str,
    business_offer_key: str,
    status: str,
    reason: str,
    offer_version: int = 1,
    application_key: str | None = None,
    person_key: str | None = None,
    issued_at: date | str | None = None,
    accepted_at: date | str | None = None,
    declined_at: date | str | None = None,
    expired_at: date | str | None = None,
    withdrawn_at: date | str | None = None,
    superseded_by_version: int | None = None,
    is_current_business_offer: bool = True,
    source_raw: str | None = None,
    hiring_manager_key: str | None = None,
    recruiter_key: str | None = None,
    department: str | None = None,
    job_role: str | None = None,
    emit_facts: bool = True,
) -> dict[str, Any]:
    if not str(reason or "").strip():
        return {"ok": False, "error": "audit_reason_required"}
    ent = _entitled(cur, company_code)
    if not ent.get("ok"):
        return ent
    company = ent["company_code"]
    st = str(status).strip().lower()
    bucket = normalize_source(source_raw)
    rid = str(uuid.uuid4())
    iss, acc, dec, exp, wit = (
        _as_date(issued_at),
        _as_date(accepted_at),
        _as_date(declined_at),
        _as_date(expired_at),
        _as_date(withdrawn_at),
    )
    # When creating a new version, mark prior versions non-current
    if offer_version > 1:
        cur.execute(
            """
            UPDATE hr_intelligence_recruiting_offers
               SET is_current_business_offer=false, superseded_by_version=%s, recorded_at=now()
             WHERE company_code=%s AND business_offer_key=%s AND offer_version < %s
            """,
            (offer_version, company, business_offer_key, offer_version),
        )
    cur.execute(
        """
        INSERT INTO hr_intelligence_recruiting_offers (
          row_id, company_code, business_offer_key, offer_version, application_key, person_key, status,
          issued_at, accepted_at, declined_at, expired_at, withdrawn_at, superseded_by_version,
          is_current_business_offer, source_bucket, hiring_manager_key, recruiter_key, department, job_role,
          source_version, event_time
        ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,now())
        ON CONFLICT (company_code, business_offer_key, offer_version) DO UPDATE SET
          status=EXCLUDED.status,
          issued_at=EXCLUDED.issued_at,
          accepted_at=EXCLUDED.accepted_at,
          declined_at=EXCLUDED.declined_at,
          expired_at=EXCLUDED.expired_at,
          withdrawn_at=EXCLUDED.withdrawn_at,
          superseded_by_version=EXCLUDED.superseded_by_version,
          is_current_business_offer=EXCLUDED.is_current_business_offer,
          source_bucket=EXCLUDED.source_bucket,
          recorded_at=now(),
          superseded_by=NULL
        RETURNING *
        """,
        (
            rid, company, business_offer_key, int(offer_version), application_key, person_key, st,
            iss, acc, dec, exp, wit, superseded_by_version, bool(is_current_business_offer), bucket,
            hiring_manager_key, recruiter_key, department, job_role, f"v:{offer_version}:{st}",
        ),
    )
    row = dict(cur.fetchone())
    if emit_facts and is_current_business_offer:
        c1.ingest_fact(
            cur,
            company_code=company,
            actor_phone=actor_phone,
            fact_type="recruiting_offer",
            entity_type="business_offer",
            entity_id=business_offer_key,
            source_authority="domain_offer",
            measures={"status": st, "offer_version": int(offer_version)},
            dimensions={"source_bucket": bucket},
            ingest_key=f"offer:{company}:{business_offer_key}",
            reason=reason,
        )
    return {"ok": True, "offer": row}


def upsert_hire(
    cur,
    *,
    company_code: str,
    actor_phone: str,
    hire_operation_key: str,
    employment_period_key: str,
    hire_completed_at: date | str,
    reason: str,
    application_key: str | None = None,
    person_key: str | None = None,
    requisition_key: str | None = None,
    job_key: str | None = None,
    source_raw: str | None = None,
    department: str | None = None,
    hiring_manager_key: str | None = None,
    recruiter_key: str | None = None,
    emit_facts: bool = True,
) -> dict[str, Any]:
    """Canonical hire bridge — employment_period_key is shared with C2 hire authority."""
    if not str(reason or "").strip():
        return {"ok": False, "error": "audit_reason_required"}
    ent = _entitled(cur, company_code)
    if not ent.get("ok"):
        return ent
    company = ent["company_code"]
    hd = _as_date(hire_completed_at)
    if not hd:
        return {"ok": False, "error": "hire_completed_at_required"}
    bucket = normalize_source(source_raw)
    rid = str(uuid.uuid4())
    cur.execute(
        """
        INSERT INTO hr_intelligence_recruiting_hires (
          row_id, company_code, hire_operation_key, employment_period_key, application_key, person_key,
          requisition_key, job_key, hire_completed_at, source_bucket, department, hiring_manager_key,
          recruiter_key, source_version, event_time
        ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,now())
        ON CONFLICT (company_code, hire_operation_key) DO UPDATE SET
          employment_period_key=EXCLUDED.employment_period_key,
          application_key=EXCLUDED.application_key,
          person_key=EXCLUDED.person_key,
          requisition_key=EXCLUDED.requisition_key,
          job_key=EXCLUDED.job_key,
          hire_completed_at=EXCLUDED.hire_completed_at,
          source_bucket=EXCLUDED.source_bucket,
          department=EXCLUDED.department,
          hiring_manager_key=EXCLUDED.hiring_manager_key,
          recruiter_key=EXCLUDED.recruiter_key,
          recorded_at=now(),
          superseded_by=NULL
        RETURNING *
        """,
        (
            rid, company, hire_operation_key, employment_period_key, application_key, person_key,
            requisition_key, job_key, hd, bucket, department, hiring_manager_key, recruiter_key,
            f"v:{hd}:{employment_period_key}",
        ),
    )
    row = dict(cur.fetchone())
    if emit_facts:
        # Same employment_period_key as C2 workforce_hire_event — no second hire authority
        c1.ingest_fact(
            cur,
            company_code=company,
            actor_phone=actor_phone,
            fact_type="recruiting_hire_bridge",
            entity_type="employment_period",
            entity_id=employment_period_key,
            source_authority="domain_hire_bridge",
            measures={"hire_completed_at": str(hd), "hire_operation_key": hire_operation_key},
            dimensions={"application_key": application_key, "source_bucket": bucket},
            ingest_key=f"hire_bridge:{company}:{employment_period_key}",
            reason=reason,
        )
    return {"ok": True, "hire": row, "canonical_employment_period_key": employment_period_key}


def record_funnel_event(
    cur,
    *,
    company_code: str,
    actor_phone: str,
    application_key: str,
    to_stage: str,
    event_at: date | str,
    reason: str,
    from_stage: str | None = None,
) -> dict[str, Any]:
    if not str(reason or "").strip():
        return {"ok": False, "error": "audit_reason_required"}
    ent = _entitled(cur, company_code)
    if not ent.get("ok"):
        return ent
    company = ent["company_code"]
    ea = _as_date(event_at)
    if not ea:
        return {"ok": False, "error": "event_at_required"}
    eid = str(uuid.uuid4())
    cur.execute(
        """
        INSERT INTO hr_intelligence_funnel_events (
          event_id, company_code, application_key, from_stage, to_stage, event_at
        ) VALUES (%s,%s,%s,%s,%s,%s)
        ON CONFLICT (company_code, application_key, to_stage, event_at) DO NOTHING
        RETURNING *
        """,
        (eid, company, application_key, from_stage, str(to_stage).strip().lower(), ea),
    )
    row = cur.fetchone()
    return {"ok": True, "event": dict(row) if row else {"idempotent": True}, "actor": _digits(actor_phone)}


def upsert_hire_ready_case(
    cur,
    *,
    company_code: str,
    actor_phone: str,
    case_type: str,
    case_key: str,
    status: str,
    reason: str,
    employment_period_key: str | None = None,
    application_key: str | None = None,
    started_at: date | str | None = None,
    completed_at: date | str | None = None,
    outcome: str | None = None,
    template_version: str | None = None,
    source_authority: str | None = None,
) -> dict[str, Any]:
    if not str(reason or "").strip():
        return {"ok": False, "error": "audit_reason_required"}
    ent = _entitled(cur, company_code)
    if not ent.get("ok"):
        return ent
    company = ent["company_code"]
    ct = str(case_type).strip().lower()
    if ct not in ("preboarding", "onboarding", "probation"):
        return {"ok": False, "error": "invalid_case_type"}
    st = str(status).strip().lower()
    sa = source_authority or f"domain_{ct}"
    start_d, comp_d = _as_date(started_at), _as_date(completed_at)
    dur = None
    if start_d and comp_d:
        dur = (comp_d - start_d).days
    # Probation: outcome must be governed decision, not inferred from due date
    if ct == "probation" and outcome and str(outcome).strip().lower() not in (
        "confirmed", "extended", "failed", "cancelled", "under_review", "active", "scheduled"
    ):
        return {"ok": False, "error": "invalid_probation_outcome", "message": "Governed outcomes only"}
    rid = str(uuid.uuid4())
    cur.execute(
        """
        INSERT INTO hr_intelligence_hire_ready_cases (
          row_id, company_code, case_type, case_key, employment_period_key, application_key,
          status, started_at, completed_at, outcome, template_version, duration_days,
          source_authority, source_version, event_time
        ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,now())
        ON CONFLICT (company_code, case_type, case_key) DO UPDATE SET
          status=EXCLUDED.status,
          started_at=EXCLUDED.started_at,
          completed_at=EXCLUDED.completed_at,
          outcome=EXCLUDED.outcome,
          template_version=COALESCE(hr_intelligence_hire_ready_cases.template_version, EXCLUDED.template_version),
          duration_days=EXCLUDED.duration_days,
          employment_period_key=EXCLUDED.employment_period_key,
          recorded_at=now(),
          superseded_by=NULL
        RETURNING *
        """,
        (
            rid, company, ct, case_key, employment_period_key, application_key,
            st, start_d, comp_d, outcome, template_version, dur, sa, f"v:{st}:{outcome}:{template_version}",
        ),
    )
    row = dict(cur.fetchone())
    c1.ingest_fact(
        cur,
        company_code=company,
        actor_phone=actor_phone,
        fact_type=f"hire_ready_{ct}",
        entity_type=ct,
        entity_id=case_key,
        source_authority=sa,
        measures={"status": st, "outcome": outcome, "duration_days": dur},
        dimensions={"template_version": template_version},
        ingest_key=f"hr_{ct}:{company}:{case_key}",
        reason=reason,
    )
    return {"ok": True, "case": row}


def rebuild_recruiting_facts(cur, *, company_code: str, actor_phone: str, reason: str) -> dict[str, Any]:
    """Idempotent rebuild from projections — no double counting."""
    if not str(reason or "").strip():
        return {"ok": False, "error": "audit_reason_required"}
    ent = _entitled(cur, company_code)
    if not ent.get("ok"):
        return ent
    company = ent["company_code"]
    counts = {"requisitions": 0, "applications": 0, "offers": 0, "hires": 0, "hire_ready": 0}
    cur.execute(
        "SELECT * FROM hr_intelligence_recruiting_requisitions WHERE company_code=%s AND superseded_by IS NULL",
        (company,),
    )
    for r in cur.fetchall():
        d = dict(r)
        upsert_requisition(
            cur, company_code=company, actor_phone=actor_phone, requisition_key=d["requisition_key"],
            status=d["status"], reason=reason, opened_at=d.get("opened_at"), filled_at=d.get("filled_at"),
            cancelled_at=d.get("cancelled_at"), reopened_at=d.get("reopened_at"),
            open_cycle_id=d.get("open_cycle_id") or "1", fill_type=d.get("fill_type"),
            department=d.get("department"), location=d.get("location"), job_role=d.get("job_role"),
            hiring_manager_key=d.get("hiring_manager_key"), recruiter_key=d.get("recruiter_key"),
            headcount_openings=d.get("headcount_openings") or 1, dims_effective_from=d.get("dims_effective_from"),
        )
        counts["requisitions"] += 1
    cur.execute(
        "SELECT * FROM hr_intelligence_recruiting_applications WHERE company_code=%s AND superseded_by IS NULL",
        (company,),
    )
    for r in cur.fetchall():
        d = dict(r)
        if d.get("merged_into_application_key"):
            continue
        upsert_application(
            cur, company_code=company, actor_phone=actor_phone, application_key=d["application_key"],
            status=d["status"], reason=reason, person_key=d.get("person_key"),
            requisition_key=d.get("requisition_key"), job_key=d.get("job_key"),
            source_raw=d.get("source_bucket"), received_at=d.get("received_at"), hired_at=d.get("hired_at"),
            rejected_at=d.get("rejected_at"), withdrawn_at=d.get("withdrawn_at"),
            hiring_manager_key=d.get("hiring_manager_key"), recruiter_key=d.get("recruiter_key"),
            department=d.get("department"), location=d.get("location"), job_role=d.get("job_role"),
        )
        counts["applications"] += 1
    cur.execute(
        """
        SELECT * FROM hr_intelligence_recruiting_offers
         WHERE company_code=%s AND superseded_by IS NULL AND is_current_business_offer=true
        """,
        (company,),
    )
    for r in cur.fetchall():
        d = dict(r)
        upsert_offer(
            cur, company_code=company, actor_phone=actor_phone, business_offer_key=d["business_offer_key"],
            status=d["status"], reason=reason, offer_version=int(d["offer_version"]),
            application_key=d.get("application_key"), person_key=d.get("person_key"),
            issued_at=d.get("issued_at"), accepted_at=d.get("accepted_at"), declined_at=d.get("declined_at"),
            expired_at=d.get("expired_at"), withdrawn_at=d.get("withdrawn_at"),
            is_current_business_offer=True, source_raw=d.get("source_bucket"),
            hiring_manager_key=d.get("hiring_manager_key"), recruiter_key=d.get("recruiter_key"),
            department=d.get("department"), job_role=d.get("job_role"),
        )
        counts["offers"] += 1
    cur.execute(
        "SELECT * FROM hr_intelligence_recruiting_hires WHERE company_code=%s AND superseded_by IS NULL",
        (company,),
    )
    for r in cur.fetchall():
        d = dict(r)
        upsert_hire(
            cur, company_code=company, actor_phone=actor_phone, hire_operation_key=d["hire_operation_key"],
            employment_period_key=d["employment_period_key"], hire_completed_at=d["hire_completed_at"],
            reason=reason, application_key=d.get("application_key"), person_key=d.get("person_key"),
            requisition_key=d.get("requisition_key"), job_key=d.get("job_key"),
            source_raw=d.get("source_bucket"), department=d.get("department"),
            hiring_manager_key=d.get("hiring_manager_key"), recruiter_key=d.get("recruiter_key"),
        )
        counts["hires"] += 1
    cur.execute(
        "SELECT * FROM hr_intelligence_hire_ready_cases WHERE company_code=%s AND superseded_by IS NULL",
        (company,),
    )
    for r in cur.fetchall():
        d = dict(r)
        upsert_hire_ready_case(
            cur, company_code=company, actor_phone=actor_phone, case_type=d["case_type"],
            case_key=d["case_key"], status=d["status"], reason=reason,
            employment_period_key=d.get("employment_period_key"), application_key=d.get("application_key"),
            started_at=d.get("started_at"), completed_at=d.get("completed_at"),
            outcome=d.get("outcome"), template_version=d.get("template_version"),
            source_authority=d.get("source_authority"),
        )
        counts["hire_ready"] += 1
    _audit(cur, company_code=company, action="rebuild_facts", actor_phone=actor_phone, reason=reason, payload=counts)
    return {"ok": True, "counts": counts, "idempotent": True}


# ── Handlers ─────────────────────────────────────────────────────────────────


def _module_unavailable(settings: dict, flag: str, module_name: str) -> dict[str, Any] | None:
    if not bool(settings.get(flag, True)):
        return {
            "status": "unavailable",
            "value": None,
            "population_ids": [],
            "error": f"{module_name}_module_disabled",
            "explain": {
                "module_off": True,
                "message_en": f"{module_name} module disabled — metric unavailable (not zero).",
                "message_ar": f"وحدة {module_name} معطّلة — المؤشر غير متاح (وليس صفراً).",
            },
        }
    return None


def _active_apps(cur, company: str) -> list[dict]:
    cur.execute(
        """
        SELECT * FROM hr_intelligence_recruiting_applications
         WHERE company_code=%s AND superseded_by IS NULL
           AND (merged_into_application_key IS NULL OR merged_into_application_key='')
        """,
        (company,),
    )
    return [dict(r) for r in cur.fetchall()]


def _active_reqs(cur, company: str) -> list[dict]:
    cur.execute(
        "SELECT * FROM hr_intelligence_recruiting_requisitions WHERE company_code=%s AND superseded_by IS NULL",
        (company,),
    )
    return [dict(r) for r in cur.fetchall()]


def _current_offers(cur, company: str) -> list[dict]:
    cur.execute(
        """
        SELECT * FROM hr_intelligence_recruiting_offers
         WHERE company_code=%s AND superseded_by IS NULL AND is_current_business_offer=true
        """,
        (company,),
    )
    return [dict(r) for r in cur.fetchall()]


def _active_hires(cur, company: str) -> list[dict]:
    cur.execute(
        "SELECT * FROM hr_intelligence_recruiting_hires WHERE company_code=%s AND superseded_by IS NULL",
        (company,),
    )
    return [dict(r) for r in cur.fetchall()]


def _handler_ttf(cur, *, company_code, settings, formula_contract, publication, filters, time_window, actor_phone, actor_role):
    unavail = _module_unavailable(settings, "recruiting_module_enabled", "recruiting")
    if unavail:
        return unavail
    start, end = _parse_window(time_window)
    milestones = {**TTF_MILESTONES, **{k: formula_contract[k] for k in TTF_MILESTONES if k in formula_contract}}
    obs = []
    for r in _active_reqs(cur, company_code):
        if not _scope_ok(r, filters, actor_role):
            continue
        if r.get("cancelled_at") and milestones.get("cancelled_behavior") == "exclude_from_completed_observations":
            if str(r.get("status") or "") == "cancelled" or r.get("cancelled_at"):
                if not r.get("filled_at"):
                    continue
        oa, fa = _as_date(r.get("opened_at")), _as_date(r.get("filled_at"))
        if not oa or not fa:
            continue
        if fa < start or fa > end:
            continue
        days = (fa - oa).days
        obs.append({
            "requisition_key": r["requisition_key"],
            "open_cycle_id": r.get("open_cycle_id"),
            "opened_at": str(oa),
            "filled_at": str(fa),
            "calendar_days": days,
            "department": r.get("department"),
            "hiring_manager_key": r.get("hiring_manager_key"),
            "recruiter_key": r.get("recruiter_key"),
            "fill_type": r.get("fill_type"),
        })
    if not obs:
        return {
            "status": "insufficient_data",
            "value": None,
            "population_ids": [],
            "explain": {
                "milestones": milestones,
                "message_en": "No filled requisitions in period for TTF.",
                "message_ar": "لا توجد طلبات توظيف مكتملة في الفترة لزمن الإشغال.",
                "period_start": str(start),
                "period_end": str(end),
            },
        }
    avg = sum(o["calendar_days"] for o in obs) / len(obs)
    return {
        "status": "ok",
        "value": float(avg),
        "unit": "days",
        "population_ids": [f"{o['requisition_key']}:{o['open_cycle_id']}" for o in obs],
        "explain": {"milestones": milestones, "observations": obs, "period_start": str(start), "period_end": str(end)},
    }


def _handler_tth(cur, *, company_code, settings, formula_contract, publication, filters, time_window, actor_phone, actor_role):
    unavail = _module_unavailable(settings, "recruiting_module_enabled", "recruiting")
    if unavail:
        return unavail
    start, end = _parse_window(time_window)
    milestones = {**TTH_MILESTONES, **{k: formula_contract[k] for k in TTH_MILESTONES if k in formula_contract}}
    # Prefer hire bridge for end milestone when present
    hires_by_app = {h["application_key"]: h for h in _active_hires(cur, company_code) if h.get("application_key")}
    obs = []
    for a in _active_apps(cur, company_code):
        if not _scope_ok(a, filters, actor_role):
            continue
        st = str(a.get("status") or "")
        if st in milestones.get("terminal_non_hire", ["rejected", "withdrawn"]):
            continue
        recv = _as_date(a.get("received_at"))
        hired = _as_date(a.get("hired_at"))
        bridge = hires_by_app.get(a["application_key"])
        if bridge:
            hired = _as_date(bridge.get("hire_completed_at")) or hired
        if not recv or not hired:
            continue
        if hired < start or hired > end:
            continue
        days = (hired - recv).days
        obs.append({
            "application_key": a["application_key"],
            "person_key": a.get("person_key"),
            "received_at": str(recv),
            "hire_completed_at": str(hired),
            "calendar_days": days,
            "source_bucket": a.get("source_bucket"),
            "employment_period_key": (bridge or {}).get("employment_period_key"),
        })
    if not obs:
        return {
            "status": "insufficient_data",
            "value": None,
            "population_ids": [],
            "explain": {
                "milestones": milestones,
                "distinct_from_ttf": True,
                "message_en": "No completed hire journeys in period for TTH.",
                "message_ar": "لا توجد رحلات تعيين مكتملة في الفترة لزمن التعيين.",
            },
        }
    avg = sum(o["calendar_days"] for o in obs) / len(obs)
    return {
        "status": "ok",
        "value": float(avg),
        "unit": "days",
        "population_ids": [o["application_key"] for o in obs],
        "explain": {"milestones": milestones, "observations": obs, "distinct_from_ttf": True},
    }


def _offer_population(cur, company, filters, actor_role, *, status_in=None, date_field=None, start=None, end=None):
    members = []
    for o in _current_offers(cur, company):
        if not _scope_ok(o, filters, actor_role):
            continue
        st = str(o.get("status") or "")
        if status_in and st not in status_in:
            continue
        if date_field and start and end:
            d = _as_date(o.get(date_field))
            if not d or d < start or d > end:
                continue
        members.append(o)
    return members


def _handler_offers_issued(cur, *, company_code, settings, formula_contract, publication, filters, time_window, actor_phone, actor_role):
    unavail = _module_unavailable(settings, "recruiting_module_enabled", "recruiting")
    if unavail:
        return unavail
    start, end = _parse_window(time_window)
    # Eligible issued = current business offers with issued_at in window (any terminal/non-terminal after issue)
    members = []
    for o in _current_offers(cur, company_code):
        if not _scope_ok(o, filters, actor_role):
            continue
        iss = _as_date(o.get("issued_at"))
        if not iss or iss < start or iss > end:
            continue
        members.append(o)
    ids = [m["business_offer_key"] for m in members]
    return {
        "status": "ok",
        "value": float(len(ids)),
        "population_ids": ids,
        "explain": {
            "denominator_basis": "current_business_offers_with_issued_at_in_period",
            "offer_versions_not_multiplied": True,
            "members": [{"business_offer_key": m["business_offer_key"], "offer_version": m["offer_version"], "status": m["status"]} for m in members],
        },
    }


def _handler_offers_accepted(cur, *, company_code, settings, formula_contract, publication, filters, time_window, actor_phone, actor_role):
    unavail = _module_unavailable(settings, "recruiting_module_enabled", "recruiting")
    if unavail:
        return unavail
    start, end = _parse_window(time_window)
    members = _offer_population(cur, company_code, filters, actor_role, status_in={"accepted"}, date_field="accepted_at", start=start, end=end)
    ids = [m["business_offer_key"] for m in members]
    return {"status": "ok", "value": float(len(ids)), "population_ids": ids, "explain": {"members": members}}


def _handler_offers_declined(cur, *, company_code, settings, formula_contract, publication, filters, time_window, actor_phone, actor_role):
    unavail = _module_unavailable(settings, "recruiting_module_enabled", "recruiting")
    if unavail:
        return unavail
    start, end = _parse_window(time_window)
    members = _offer_population(cur, company_code, filters, actor_role, status_in={"declined"}, date_field="declined_at", start=start, end=end)
    ids = [m["business_offer_key"] for m in members]
    return {"status": "ok", "value": float(len(ids)), "population_ids": ids, "explain": {"members": members}}


def _handler_offer_accept_rate(cur, *, company_code, settings, formula_contract, publication, filters, time_window, actor_phone, actor_role):
    unavail = _module_unavailable(settings, "recruiting_module_enabled", "recruiting")
    if unavail:
        return unavail
    start, end = _parse_window(time_window)
    issued = []
    for o in _current_offers(cur, company_code):
        if not _scope_ok(o, filters, actor_role):
            continue
        iss = _as_date(o.get("issued_at"))
        if not iss or iss < start or iss > end:
            continue
        issued.append(o)
    accepted = [o for o in issued if str(o.get("status") or "") == "accepted"]
    den = float(len(issued))
    num = float(len(accepted))
    if den == 0:
        return {
            "status": "not_applicable",
            "value": None,
            "numerator_value": 0.0,
            "denominator_value": 0.0,
            "population_ids": [],
            "explain": {
                "denominator": "offers_extended_current_business_offers_issued_in_period",
                "message_en": "No issued eligible offers — acceptance rate not 0%.",
                "message_ar": "لا عروض مؤهلة صادرة — معدل القبول ليس ٠٪.",
            },
        }
    return {
        "status": "ok",
        "value": (num / den) * 100.0,
        "unit": "percent",
        "numerator_value": num,
        "denominator_value": den,
        "population_ids": [o["business_offer_key"] for o in issued],
        "explain": {
            "numerator_ids": [o["business_offer_key"] for o in accepted],
            "denominator_ids": [o["business_offer_key"] for o in issued],
            "denominator": "offers_extended",
            "offer_versions_not_multiplied": True,
        },
    }


def _handler_recruiting_hires(cur, *, company_code, settings, formula_contract, publication, filters, time_window, actor_phone, actor_role):
    unavail = _module_unavailable(settings, "recruiting_module_enabled", "recruiting")
    if unavail:
        return unavail
    start, end = _parse_window(time_window)
    members = []
    for h in _active_hires(cur, company_code):
        if not _scope_ok(h, filters, actor_role):
            continue
        hd = _as_date(h.get("hire_completed_at"))
        if not hd or hd < start or hd > end:
            continue
        members.append(h)
    ids = [m["employment_period_key"] for m in members]
    return {
        "status": "ok",
        "value": float(len(ids)),
        "population_ids": ids,
        "explain": {
            "canonical_hire_bridge": True,
            "employment_period_keys": ids,
            "reconcile_with_c2": "workforce.hires.count uses same employment_period_key hire_event_date",
            "members": members,
        },
    }


def _handler_apps_by_source(cur, *, company_code, settings, formula_contract, publication, filters, time_window, actor_phone, actor_role):
    unavail = _module_unavailable(settings, "recruiting_module_enabled", "recruiting")
    if unavail:
        return unavail
    start, end = _parse_window(time_window)
    source_filter = filters.get("source_bucket")
    members = []
    for a in _active_apps(cur, company_code):
        if not _scope_ok(a, filters, actor_role):
            continue
        recv = _as_date(a.get("received_at"))
        if not recv or recv < start or recv > end:
            continue
        if source_filter and a.get("source_bucket") != source_filter:
            continue
        members.append(a)
    # Sensitive candidate cohort: suppress small source segments when requested
    sensitive = bool(formula_contract.get("sensitive_aggregate"))
    if sensitive and source_filter:
        min_n = int((settings.get("c1_settings") or {}).get("min_cohort_n") or 5)
        # c1 settings nested differently — use filters/settings
        try:
            min_n = int(c1._entitled(cur, company_code)["settings"].get("min_cohort_n") or 5)
        except Exception:
            min_n = 5
        if len(members) < min_n:
            return {
                "status": "suppressed",
                "value": None,
                "population_ids": [] if not _candidate_drill_allowed(filters, actor_role) else [],
                "explain": {"min_cohort_n": min_n, "segment_count": len(members)},
            }
    ids = [m["application_key"] for m in members]
    if not _candidate_drill_allowed(filters, actor_role):
        # Aggregate OK but drill identities withheld
        return {
            "status": "ok",
            "value": float(len(ids)),
            "population_ids": [],
            "explain": {
                "by_source": _tally_source(members, "application_key"),
                "candidate_ids_withheld": True,
                "count": len(ids),
            },
        }
    return {
        "status": "ok",
        "value": float(len(ids)),
        "population_ids": ids,
        "explain": {"by_source": _tally_source(members, "application_key"), "unknown_preserved": True},
    }


def _tally_source(members: list[dict], id_field: str) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for m in members:
        b = normalize_source(m.get("source_bucket"))
        out.setdefault(b, {"count": 0, "ids": [], "label_en": source_label(b, lang="en"), "label_ar": source_label(b, lang="ar")})
        out[b]["count"] += 1
        out[b]["ids"].append(m.get(id_field))
    return out


def _handler_hires_by_source(cur, *, company_code, settings, formula_contract, publication, filters, time_window, actor_phone, actor_role):
    unavail = _module_unavailable(settings, "recruiting_module_enabled", "recruiting")
    if unavail:
        return unavail
    start, end = _parse_window(time_window)
    source_filter = filters.get("source_bucket")
    members = []
    for h in _active_hires(cur, company_code):
        if not _scope_ok(h, filters, actor_role):
            continue
        hd = _as_date(h.get("hire_completed_at"))
        if not hd or hd < start or hd > end:
            continue
        if source_filter and h.get("source_bucket") != source_filter:
            continue
        members.append(h)
    ids = [m["employment_period_key"] for m in members]
    return {
        "status": "ok",
        "value": float(len(ids)),
        "population_ids": ids,
        "explain": {"by_source": _tally_source(members, "employment_period_key"), "observed_outcome_not_causal": True},
    }


def _handler_offer_accepts_by_source(cur, *, company_code, settings, formula_contract, publication, filters, time_window, actor_phone, actor_role):
    unavail = _module_unavailable(settings, "recruiting_module_enabled", "recruiting")
    if unavail:
        return unavail
    start, end = _parse_window(time_window)
    source_filter = filters.get("source_bucket")
    members = []
    for o in _current_offers(cur, company_code):
        if not _scope_ok(o, filters, actor_role):
            continue
        if str(o.get("status") or "") != "accepted":
            continue
        acc = _as_date(o.get("accepted_at"))
        if not acc or acc < start or acc > end:
            continue
        if source_filter and o.get("source_bucket") != source_filter:
            continue
        members.append(o)
    ids = [m["business_offer_key"] for m in members]
    return {
        "status": "ok",
        "value": float(len(ids)),
        "population_ids": ids,
        "explain": {"by_source": _tally_source(members, "business_offer_key"), "observed_outcome_not_causal": True},
    }


def _handler_app_hire_conversion(cur, *, company_code, settings, formula_contract, publication, filters, time_window, actor_phone, actor_role):
    unavail = _module_unavailable(settings, "recruiting_module_enabled", "recruiting")
    if unavail:
        return unavail
    start, end = _parse_window(time_window)
    source_filter = filters.get("source_bucket")
    apps = []
    for a in _active_apps(cur, company_code):
        if not _scope_ok(a, filters, actor_role):
            continue
        recv = _as_date(a.get("received_at"))
        if not recv or recv < start or recv > end:
            continue
        if source_filter and a.get("source_bucket") != source_filter:
            continue
        apps.append(a)
    hire_apps = {h.get("application_key") for h in _active_hires(cur, company_code)}
    hired = [a for a in apps if a["application_key"] in hire_apps or a.get("hired_at")]
    den = float(len(apps))
    num = float(len(hired))
    if den == 0:
        return {
            "status": "not_applicable",
            "value": None,
            "numerator_value": 0.0,
            "denominator_value": 0.0,
            "population_ids": [],
            "explain": {"message_en": "No applications in cohort.", "message_ar": "لا طلبات في الدفعة."},
        }
    return {
        "status": "ok",
        "value": (num / den) * 100.0,
        "unit": "percent",
        "numerator_value": num,
        "denominator_value": den,
        "population_ids": [a["application_key"] for a in apps],
        "explain": {
            "numerator_ids": [a["application_key"] for a in hired],
            "source_filter": source_filter,
            "observed_outcome_not_causal": True,
            "no_universal_effectiveness_score": True,
        },
    }


def _handler_funnel(cur, *, company_code, settings, formula_contract, publication, filters, time_window, actor_phone, actor_role):
    unavail = _module_unavailable(settings, "recruiting_module_enabled", "recruiting")
    if unavail:
        return unavail
    start, end = _parse_window(time_window)
    stage = filters.get("to_stage")
    cur.execute(
        """
        SELECT * FROM hr_intelligence_funnel_events
         WHERE company_code=%s AND superseded_by IS NULL
           AND event_at >= %s AND event_at <= %s
        """,
        (company_code, start, end),
    )
    events = [dict(r) for r in cur.fetchall()]
    if stage:
        events = [e for e in events if e.get("to_stage") == stage]
    # Event-based: same application can appear in different stages; not double-counted within one stage+date unique key
    ids = [f"{e['application_key']}:{e['to_stage']}:{e['event_at']}" for e in events]
    by_stage: dict[str, int] = {}
    for e in events:
        by_stage[e["to_stage"]] = by_stage.get(e["to_stage"], 0) + 1
    return {
        "status": "ok",
        "value": float(len(events)),
        "population_ids": ids if _candidate_drill_allowed(filters, actor_role) else [],
        "explain": {
            "by_stage": by_stage,
            "event_based_not_current_state_only": True,
            "candidate_ids_withheld": not _candidate_drill_allowed(filters, actor_role),
        },
    }


def _handler_preboard_rate(cur, *, company_code, settings, formula_contract, publication, filters, time_window, actor_phone, actor_role):
    unavail = _module_unavailable(settings, "preboarding_module_enabled", "preboarding")
    if unavail:
        return unavail
    start, end = _parse_window(time_window)
    cur.execute(
        """
        SELECT * FROM hr_intelligence_hire_ready_cases
         WHERE company_code=%s AND case_type='preboarding' AND superseded_by IS NULL
        """,
        (company_code,),
    )
    cases = [dict(r) for r in cur.fetchall()]
    started = []
    for c in cases:
        sd = _as_date(c.get("started_at"))
        if sd and start <= sd <= end:
            started.append(c)
    completed = [c for c in started if str(c.get("status") or "") in ("ready", "completed", "converted") or c.get("completed_at")]
    den = float(len(started))
    num = float(len(completed))
    if den == 0:
        return {
            "status": "not_applicable",
            "value": None,
            "population_ids": [],
            "explain": {"message_en": "No preboarding starts in cohort.", "message_ar": "لا بدايات تهيئة في الدفعة."},
        }
    return {
        "status": "ok",
        "value": (num / den) * 100.0,
        "unit": "percent",
        "numerator_value": num,
        "denominator_value": den,
        "population_ids": [c["case_key"] for c in started],
        "explain": {"completion_authority": "canonical_preboarding_readiness", "completed_ids": [c["case_key"] for c in completed]},
    }


def _handler_onboard_rate(cur, *, company_code, settings, formula_contract, publication, filters, time_window, actor_phone, actor_role):
    unavail = _module_unavailable(settings, "onboarding_module_enabled", "onboarding")
    if unavail:
        return unavail
    start, end = _parse_window(time_window)
    cur.execute(
        """
        SELECT * FROM hr_intelligence_hire_ready_cases
         WHERE company_code=%s AND case_type='onboarding' AND superseded_by IS NULL
        """,
        (company_code,),
    )
    cases = [dict(r) for r in cur.fetchall()]
    started = []
    for c in cases:
        sd = _as_date(c.get("started_at"))
        if sd and start <= sd <= end:
            started.append(c)
    completed = [c for c in started if str(c.get("status") or "") == "completed" or c.get("completed_at")]
    den = float(len(started))
    num = float(len(completed))
    if den == 0:
        return {
            "status": "not_applicable",
            "value": None,
            "population_ids": [],
            "explain": {"message_en": "No onboarding starts in cohort.", "message_ar": "لا بدايات تأهيل في الدفعة."},
        }
    return {
        "status": "ok",
        "value": (num / den) * 100.0,
        "unit": "percent",
        "numerator_value": num,
        "denominator_value": den,
        "population_ids": [c["case_key"] for c in started],
        "explain": {
            "completion_authority": "onboarding_completion_contract",
            "not_task_count_ratio": True,
            "template_versions": {c["case_key"]: c.get("template_version") for c in started},
            "completed_ids": [c["case_key"] for c in completed],
        },
    }


def _handler_onboard_time(cur, *, company_code, settings, formula_contract, publication, filters, time_window, actor_phone, actor_role):
    unavail = _module_unavailable(settings, "onboarding_module_enabled", "onboarding")
    if unavail:
        return unavail
    start, end = _parse_window(time_window)
    cur.execute(
        """
        SELECT * FROM hr_intelligence_hire_ready_cases
         WHERE company_code=%s AND case_type='onboarding' AND superseded_by IS NULL
           AND completed_at IS NOT NULL AND started_at IS NOT NULL
        """,
        (company_code,),
    )
    obs = []
    for c in cur.fetchall():
        d = dict(c)
        cd = _as_date(d.get("completed_at"))
        sd = _as_date(d.get("started_at"))
        if not cd or not sd or cd < start or cd > end:
            continue
        days = d.get("duration_days")
        if days is None:
            days = (cd - sd).days
        obs.append({
            "case_key": d["case_key"],
            "duration_days": int(days),
            "template_version": d.get("template_version"),
            "started_at": str(sd),
            "completed_at": str(cd),
        })
    if not obs:
        return {
            "status": "unavailable",
            "value": None,
            "population_ids": [],
            "explain": {
                "message_en": "No completed onboarding cohort for completion-time.",
                "message_ar": "لا دفعة تأهيل مكتملة لزمن الإكمال.",
            },
        }
    avg = sum(o["duration_days"] for o in obs) / len(obs)
    return {
        "status": "ok",
        "value": float(avg),
        "unit": "days",
        "population_ids": [o["case_key"] for o in obs],
        "explain": {"observations": obs, "historical_template_version_preserved": True},
    }


def _handler_probation(cur, *, company_code, settings, formula_contract, publication, filters, time_window, actor_phone, actor_role):
    unavail = _module_unavailable(settings, "probation_module_enabled", "probation")
    if unavail:
        return unavail
    start, end = _parse_window(time_window)
    outcome_filter = filters.get("outcome")
    cur.execute(
        """
        SELECT * FROM hr_intelligence_hire_ready_cases
         WHERE company_code=%s AND case_type='probation' AND superseded_by IS NULL
        """,
        (company_code,),
    )
    members = []
    for c in cur.fetchall():
        d = dict(c)
        # Outcome from governed decision only
        outcome = str(d.get("outcome") or "").strip().lower()
        if outcome not in ("confirmed", "extended", "failed", "cancelled"):
            continue
        decided = _as_date(d.get("completed_at")) or _as_date(d.get("started_at"))
        if decided and (decided < start or decided > end):
            continue
        if outcome_filter and outcome != outcome_filter:
            continue
        members.append(d)
    dist: dict[str, list] = {"confirmed": [], "extended": [], "failed": [], "cancelled": []}
    for m in members:
        dist.setdefault(m["outcome"], []).append(m["case_key"])
    return {
        "status": "ok",
        "value": float(len(members)),
        "population_ids": [m["case_key"] for m in members],
        "explain": {
            "distribution": {k: len(v) for k, v in dist.items()},
            "ids_by_outcome": dist,
            "not_inferred_from_due_date": True,
            "governed_decision_only": True,
        },
    }


def _register_handlers() -> None:
    c1.register_formula_handler("recruiting_time_to_fill", _handler_ttf)
    c1.register_formula_handler("recruiting_time_to_hire", _handler_tth)
    c1.register_formula_handler("recruiting_offers_issued", _handler_offers_issued)
    c1.register_formula_handler("recruiting_offers_accepted", _handler_offers_accepted)
    c1.register_formula_handler("recruiting_offers_declined", _handler_offers_declined)
    c1.register_formula_handler("recruiting_offer_acceptance_rate", _handler_offer_accept_rate)
    c1.register_formula_handler("recruiting_hires", _handler_recruiting_hires)
    c1.register_formula_handler("recruiting_applications_by_source", _handler_apps_by_source)
    c1.register_formula_handler("recruiting_hires_by_source", _handler_hires_by_source)
    c1.register_formula_handler("recruiting_offer_accepts_by_source", _handler_offer_accepts_by_source)
    c1.register_formula_handler("recruiting_app_hire_conversion", _handler_app_hire_conversion)
    c1.register_formula_handler("recruiting_funnel_events", _handler_funnel)
    c1.register_formula_handler("hire_ready_preboarding_rate", _handler_preboard_rate)
    c1.register_formula_handler("hire_ready_onboarding_rate", _handler_onboard_rate)
    c1.register_formula_handler("hire_ready_onboarding_time", _handler_onboard_time)
    c1.register_formula_handler("hire_ready_probation_outcomes", _handler_probation)


def seed_recruiting_definitions(cur: Any, *, actor_phone: str) -> dict[str, Any]:
    c1.ensure_hr_intelligence_registry_c1_schema(cur)
    created = []

    def _ensure(key: str, **kwargs):
        want_kind = (kwargs.get("formula_contract") or {}).get("kind")
        cur.execute(
            """
            SELECT kpi_definition_id, status, effective_version, formula_contract
              FROM hr_kpi_definitions WHERE semantic_key=%s
             ORDER BY effective_version DESC LIMIT 1
            """,
            (key,),
        )
        ex = cur.fetchone()
        if ex:
            ex = dict(ex)
            fc = ex.get("formula_contract")
            if isinstance(fc, str):
                fc = json.loads(fc)
            if want_kind and (not fc or fc.get("kind") != want_kind):
                ver = c1.version_kpi_definition(
                    cur, actor_phone=actor_phone, semantic_key=key, reason=f"c3 activate {key}",
                    updates={**kwargs, "status": kwargs.get("status") or "published"},
                )
                if ver.get("ok"):
                    created.append(key)
                    if (kwargs.get("status") or "published") == "published":
                        c1.publish_kpi_definition(
                            cur, actor_phone=actor_phone,
                            kpi_definition_id=str(ver["definition"]["kpi_definition_id"]), reason="c3 publish",
                        )
                return
            if kwargs.get("status") == "published" and ex["status"] not in ("published", "blocked"):
                c1.publish_kpi_definition(
                    cur, actor_phone=actor_phone, kpi_definition_id=str(ex["kpi_definition_id"]), reason="c3 seed publish"
                )
            return
        out = c1.create_kpi_definition(cur, actor_phone=actor_phone, semantic_key=key, **kwargs)
        if out.get("ok"):
            created.append(key)
            if kwargs.get("status") == "published":
                c1.publish_kpi_definition(
                    cur, actor_phone=actor_phone,
                    kpi_definition_id=str(out["definition"]["kpi_definition_id"]), reason="c3 seed publish",
                )

    _ensure(
        TTF_KEY,
        name_en="Time to fill", name_ar="زمن إشغال الشاغر",
        description_en="Average calendar days from requisition opened to filled.",
        description_ar="متوسط الأيام التقويمية من فتح طلب التوظيف إلى إشغاله.",
        business_meaning="Requisition-level clock; distinct from time-to-hire.",
        formula_contract={"kind": "recruiting_time_to_fill", **TTF_MILESTONES, "sensitive_aggregate": False},
        unit="days", time_semantics="period_average", permission_class="workforce_general", status="published",
        numerator={"description": "sum of open→fill calendar days"}, denominator={"description": "filled requisitions in period"},
        owner="wave5_c3", reason="c3 ttf", canonical_source_facts=["recruiting_requisition"],
        supported_dimensions=["department", "hiring_manager", "recruiter", "job_role"],
    )
    _ensure(
        TTH_KEY,
        name_en="Time to hire", name_ar="زمن التعيين",
        description_en="Average calendar days from application received to hire completed.",
        description_ar="متوسط الأيام التقويمية من استلام الطلب إلى إكمال التعيين.",
        business_meaning="Application/candidate journey; distinct from time-to-fill.",
        formula_contract={"kind": "recruiting_time_to_hire", **TTH_MILESTONES, "sensitive_aggregate": False},
        unit="days", time_semantics="period_average", permission_class="workforce_general", status="published",
        owner="wave5_c3", reason="c3 tth", canonical_source_facts=["recruiting_application", "recruiting_hire_bridge"],
    )
    _ensure(
        OFFER_ISSUED_KEY,
        name_en="Offers issued", name_ar="العروض الصادرة",
        description_en="Current business offers with issued_at in period (versions not multiplied).",
        description_ar="عروض العمل الحالية الصادرة في الفترة (الإصدارات لا تُضاعف).",
        business_meaning="Denominator basis for acceptance rate.",
        formula_contract={"kind": "recruiting_offers_issued", "sensitive_aggregate": False},
        unit="count", time_semantics="event_count", permission_class="workforce_general", status="published",
        owner="wave5_c3", reason="c3 offers issued",
    )
    _ensure(
        OFFER_ACCEPTED_KEY,
        name_en="Offers accepted", name_ar="العروض المقبولة",
        description_en="Accepted current business offers in period.",
        description_ar="العروض الحالية المقبولة في الفترة.",
        business_meaning="Offer acceptance ≠ hire unless KPI says so.",
        formula_contract={"kind": "recruiting_offers_accepted", "sensitive_aggregate": False},
        unit="count", time_semantics="event_count", permission_class="workforce_general", status="published",
        owner="wave5_c3", reason="c3 offers accepted",
    )
    _ensure(
        OFFER_DECLINED_KEY,
        name_en="Offers declined", name_ar="العروض المرفوضة",
        description_en="Declined current business offers in period.",
        description_ar="العروض الحالية المرفوضة في الفترة.",
        business_meaning="Declined outcomes from canonical offer status.",
        formula_contract={"kind": "recruiting_offers_declined", "sensitive_aggregate": False},
        unit="count", time_semantics="event_count", permission_class="workforce_general", status="published",
        owner="wave5_c3", reason="c3 offers declined",
    )
    _ensure(
        OFFER_ACCEPT_RATE_KEY,
        name_en="Offer acceptance rate", name_ar="معدل قبول العرض",
        description_en="Accepted ÷ offers extended (issued current business offers) × 100.",
        description_ar="المقبولة ÷ العروض الممددة (الحالية الصادرة) × ١٠٠.",
        business_meaning="Denominator = offers extended; zero denom → not_applicable.",
        formula_contract={"kind": "recruiting_offer_acceptance_rate", "sensitive_aggregate": False},
        unit="percent", time_semantics="rate_over_window", permission_class="workforce_general", status="published",
        numerator={"description": "accepted"}, denominator={"description": "offers extended"},
        owner="wave5_c3", reason="c3 offer accept rate",
    )
    _ensure(
        RECRUITING_HIRES_KEY,
        name_en="Recruiting hires (bridge)", name_ar="تعيينات التوظيف (جسر)",
        description_en="Canonical hire-bridge count by employment_period_key.",
        description_ar="عدد التعيينات عبر جسر التوظيف بمفتاح فترة التوظيف.",
        business_meaning="Reconciles with C2 workforce.hires.count via same employment_period_key.",
        formula_contract={"kind": "recruiting_hires", "sensitive_aggregate": False},
        unit="count", time_semantics="event_count", permission_class="workforce_general", status="published",
        owner="wave5_c3", reason="c3 recruiting hires",
        canonical_source_facts=["recruiting_hire_bridge"],
    )
    _ensure(
        APPS_BY_SOURCE_KEY,
        name_en="Applications by source", name_ar="الطلبات حسب المصدر",
        description_en="Application counts by governed source bucket.",
        description_ar="عدد الطلبات حسب سلة المصدر المحكومة.",
        business_meaning="Observed attribution; unknown stays unknown.",
        formula_contract={"kind": "recruiting_applications_by_source", "sensitive_aggregate": True},
        unit="count", time_semantics="event_count", permission_class="workforce_general", status="published",
        owner="wave5_c3", reason="c3 apps by source",
        supported_dimensions=["source"],
    )
    _ensure(
        HIRES_BY_SOURCE_KEY,
        name_en="Hires by source", name_ar="التعيينات حسب المصدر",
        description_en="Hires by governed source — observed outcome, not causal proof.",
        description_ar="التعيينات حسب المصدر — نتيجة مرصودة وليست إثبات سببية.",
        business_meaning="Separate metric; not a universal effectiveness score.",
        formula_contract={"kind": "recruiting_hires_by_source", "sensitive_aggregate": False},
        unit="count", time_semantics="event_count", permission_class="workforce_general", status="published",
        owner="wave5_c3", reason="c3 hires by source",
    )
    _ensure(
        OFFER_ACCEPTS_BY_SOURCE_KEY,
        name_en="Offer accepts by source", name_ar="قبول العروض حسب المصدر",
        description_en="Accepted offers by source bucket.",
        description_ar="العروض المقبولة حسب سلة المصدر.",
        business_meaning="Separate observed metric.",
        formula_contract={"kind": "recruiting_offer_accepts_by_source", "sensitive_aggregate": False},
        unit="count", time_semantics="event_count", permission_class="workforce_general", status="published",
        owner="wave5_c3", reason="c3 offer accepts by source",
    )
    _ensure(
        APP_HIRE_CONV_KEY,
        name_en="Application→hire conversion by source", name_ar="تحويل الطلب→تعيين حسب المصدر",
        description_en="Hires ÷ applications in cohort (optional source filter).",
        description_ar="التعيينات ÷ الطلبات في الدفعة (تصفية مصدر اختيارية).",
        business_meaning="Explicit num/den; not a magical effectiveness score.",
        formula_contract={"kind": "recruiting_app_hire_conversion", "sensitive_aggregate": False},
        unit="percent", time_semantics="rate_over_window", permission_class="workforce_general", status="published",
        owner="wave5_c3", reason="c3 app hire conversion",
    )
    _ensure(
        FUNNEL_KEY,
        name_en="Recruiting funnel events", name_ar="أحداث قمع التوظيف",
        description_en="Lifecycle transition events (not current-state stage counts alone).",
        description_ar="أحداث انتقال دورة الحياة (وليست أعداد المرحلة الحالية وحدها).",
        business_meaning="Event-based funnel integrity.",
        formula_contract={"kind": "recruiting_funnel_events", "sensitive_aggregate": True},
        unit="count", time_semantics="event_count", permission_class="workforce_general", status="published",
        owner="wave5_c3", reason="c3 funnel",
    )
    _ensure(
        PREBOARD_RATE_KEY,
        name_en="Preboarding completion rate", name_ar="معدل إكمال التهيئة",
        description_en="Completed/ready preboards ÷ starts in cohort.",
        description_ar="التهيئة المكتملة/الجاهزة ÷ البدايات في الدفعة.",
        business_meaning="Canonical preboarding readiness — optional steps not forced incomplete.",
        formula_contract={"kind": "hire_ready_preboarding_rate", "sensitive_aggregate": False},
        unit="percent", time_semantics="cohort", permission_class="workforce_general", status="published",
        owner="wave5_c3", reason="c3 preboard rate",
    )
    _ensure(
        ONBOARD_RATE_KEY,
        name_en="Onboarding completion rate", name_ar="معدل إكمال التأهيل",
        description_en="Completed onboardings ÷ starts (completion contract, not task ratio).",
        description_ar="التأهيلات المكتملة ÷ البدايات (عقد الإكمال وليس نسبة المهام).",
        business_meaning="Uses onboarding_completion_contract semantics.",
        formula_contract={"kind": "hire_ready_onboarding_rate", "sensitive_aggregate": False},
        unit="percent", time_semantics="cohort", permission_class="workforce_general", status="published",
        owner="wave5_c3", reason="c3 onboard rate",
    )
    _ensure(
        ONBOARD_TIME_KEY,
        name_en="Onboarding completion time", name_ar="زمن إكمال التأهيل",
        description_en="Average days start→completion for completed cohort.",
        description_ar="متوسط الأيام من البداية إلى الإكمال للدفعة المكتملة.",
        business_meaning="Historical template version preserved on case.",
        formula_contract={"kind": "hire_ready_onboarding_time", "sensitive_aggregate": False},
        unit="days", time_semantics="period_average", permission_class="workforce_general", status="published",
        owner="wave5_c3", reason="c3 onboard time",
    )
    _ensure(
        PROBATION_KEY,
        name_en="Probation outcomes", name_ar="نتائج فترة التجربة",
        description_en="Governed probation decisions (confirmed/extended/failed).",
        description_ar="قرارات فترة التجربة المحكومة (تأكيد/تمديد/رسوب).",
        business_meaning="Never inferred merely because due date passed.",
        formula_contract={"kind": "hire_ready_probation_outcomes", "sensitive_aggregate": False},
        unit="count", time_semantics="event_count", permission_class="workforce_general", status="published",
        owner="wave5_c3", reason="c3 probation",
    )
    # Explicitly refuse universal score definition
    forbid = c1.create_kpi_definition(
        cur,
        actor_phone=actor_phone,
        semantic_key=FORBIDDEN_SCORE_KEY,
        name_en="Source effectiveness score",
        name_ar="درجة فعالية المصدر",
        description_en="Forbidden universal score.",
        description_ar="درجة شاملة محظورة.",
        business_meaning="Do not publish.",
        formula_contract={"kind": "blocked", "reason": "no_universal_source_effectiveness_score"},
        unit="score",
        time_semantics="event_count",
        permission_class="workforce_general",
        status="blocked",
        reason="forbid universal source score",
    )
    _ = forbid
    return {"ok": True, "created_semantic_keys": created, "ttf_milestones": TTF_MILESTONES, "tth_milestones": TTH_MILESTONES}


def publish_recruiting_kpis_for_company(cur, *, company_code: str, actor_phone: str, reason: str) -> dict[str, Any]:
    if not str(reason or "").strip():
        return {"ok": False, "error": "audit_reason_required"}
    ent = _entitled(cur, company_code)
    if not ent.get("ok"):
        return ent
    company = ent["company_code"]
    seed_recruiting_definitions(cur, actor_phone=actor_phone)
    _register_handlers()
    keys = [
        TTF_KEY, TTH_KEY, OFFER_ISSUED_KEY, OFFER_ACCEPTED_KEY, OFFER_DECLINED_KEY, OFFER_ACCEPT_RATE_KEY,
        RECRUITING_HIRES_KEY, APPS_BY_SOURCE_KEY, HIRES_BY_SOURCE_KEY, OFFER_ACCEPTS_BY_SOURCE_KEY,
        APP_HIRE_CONV_KEY, FUNNEL_KEY, PREBOARD_RATE_KEY, ONBOARD_RATE_KEY, ONBOARD_TIME_KEY, PROBATION_KEY,
    ]
    published = []
    for key in keys:
        pub = c1.publish_kpi_for_company(
            cur, company_code=company, actor_phone=actor_phone, semantic_key=key, reason=reason
        )
        if pub.get("ok"):
            published.append(key)
    # Ensure forbidden score is not published
    bad = c1.publish_kpi_for_company(
        cur, company_code=company, actor_phone=actor_phone, semantic_key=FORBIDDEN_SCORE_KEY, reason="should fail"
    )
    return {
        "ok": True,
        "published": published,
        "universal_score_blocked": bad.get("ok") is not True,
        **honesty_payload(company_code=company),
    }


def reconcile_hires_with_c2(
    cur,
    *,
    company_code: str,
    period_start: date | str,
    period_end: date | str,
) -> dict[str, Any]:
    """Explain C3 vs C2 hire counts via shared employment_period_key authority."""
    start, end = _as_date(period_start), _as_date(period_end)
    c3_keys = set()
    for h in _active_hires(cur, company_code_norm(company_code)):
        hd = _as_date(h.get("hire_completed_at"))
        if hd and start and end and start <= hd <= end:
            c3_keys.add(h["employment_period_key"])
    c2_keys = set()
    try:
        cur.execute(
            """
            SELECT employment_period_key, hire_event_date
              FROM hr_intelligence_employment_periods
             WHERE company_code=%s AND superseded_by IS NULL
               AND hire_event_date IS NOT NULL
               AND hire_event_date >= %s AND hire_event_date <= %s
               AND COALESCE(worker_class,'employee')='employee'
            """,
            (company_code_norm(company_code), start, end),
        )
        for r in cur.fetchall():
            c2_keys.add(dict(r)["employment_period_key"])
    except Exception as exc:
        return {
            "ok": True,
            "c3_employment_period_keys": sorted(c3_keys),
            "c2_available": False,
            "c2_error": str(exc),
            "shared_authority": "employment_period_key",
            "explanation_en": "C2 projection table absent or unread — C3 still uses employment_period_key bridge.",
            "explanation_ar": "جدول إسقاط C2 غير متاح — C3 ما زال يستخدم جسر مفتاح فترة التوظيف.",
        }
    only_c3 = sorted(c3_keys - c2_keys)
    only_c2 = sorted(c2_keys - c3_keys)
    shared = sorted(c3_keys & c2_keys)
    return {
        "ok": True,
        "c3_count": len(c3_keys),
        "c2_count": len(c2_keys),
        "shared_count": len(shared),
        "shared_employment_period_keys": shared,
        "only_c3": only_c3,
        "only_c2": only_c2,
        "shared_authority": "employment_period_key",
        "explanation_en": (
            "Same hire authority (employment_period_key). Count differences mean different cohort membership "
            "(e.g. recruiting window vs workforce hire_event_date window), not two hire definitions."
        ),
        "explanation_ar": (
            "نفس سلطة التعيين (مفتاح فترة التوظيف). اختلاف العدد يعني عضوية دفعة مختلفة وليس تعريفَي تعيين."
        ),
    }


# Register on import so evaluator finds handlers when module loaded
_register_handlers()
