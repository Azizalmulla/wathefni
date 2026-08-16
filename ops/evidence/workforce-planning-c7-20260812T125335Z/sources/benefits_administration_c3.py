"""Wave 6 C3 — Benefits Administration (Kuwait-first infrastructure).

Canonical authority:
  plan → eligibility → enrollment/waiver → dependent coverage refs →
  effective coverage → contributions → provider/member refs

Does NOT own employee/employment/dependent master/payroll/claims.
Wave 3 employee_dependents remain SoT. Payroll handoff OPTIONAL.
Claims/adjudication OUT. No invented statutory Kuwait entitlements.
Assistant mutations OUT. No second analytics engine.
"""
from __future__ import annotations

import json
import os
import uuid
from datetime import date, datetime, timedelta
from typing import Any

PHASE = "benefits_administration_c3"
CONTRACT_VERSION = "benefits_administration_c3_v1"
PASS_STAMP = "BENEFITS_FULL_PASS"
COMMERCIAL_MODULE_KEY = "benefits"
FLAG = "WATHEFNI_BENEFITS_C3"
COMPANIES_FLAG = "WATHEFNI_BENEFITS_COMPANIES"
_ON = {"1", "true", "yes", "on"}

PLAN_CATEGORIES = ("medical", "life_accident", "allowance_perk", "other_employer_sponsored")
PLAN_STATUSES = ("draft", "published", "retired")
ENROLL_STATES = (
    "eligible",
    "enrollment_open",
    "elected",
    "waived",
    "pending_evidence",
    "pending_approval",
    "confirmed",
    "coverage_active",
    "declined",
    "cancelled",
    "ended",
)
COVERAGE_STATES = ("requested", "elected", "confirmed", "active", "ended")
WINDOW_TYPES = ("new_hire", "open_enrollment", "qualifying_life_event")
TIER_OPTIONS = ("employee_only", "employee_spouse", "employee_children", "family")
CONTRIB_KINDS = ("employer", "employee")
CONTRIB_MODES = ("fixed", "percent")

STATUS_LABELS = {
    "eligible": {"en": "Eligible", "ar": "مؤهل"},
    "enrollment_open": {"en": "Enrollment open", "ar": "التسجيل مفتوح"},
    "elected": {"en": "Elected", "ar": "مختار"},
    "waived": {"en": "Waived", "ar": "متنازل"},
    "pending_evidence": {"en": "Pending evidence", "ar": "بانتظار المستندات"},
    "pending_approval": {"en": "Pending approval", "ar": "بانتظار الاعتماد"},
    "confirmed": {"en": "Confirmed", "ar": "مؤكد"},
    "coverage_active": {"en": "Coverage active", "ar": "التغطية سارية"},
    "declined": {"en": "Declined", "ar": "مرفوض"},
    "cancelled": {"en": "Cancelled", "ar": "ملغى"},
    "ended": {"en": "Ended", "ar": "منتهية"},
    "active": {"en": "Active", "ar": "ساري"},
    "benefits": {"en": "Benefits", "ar": "المزايا"},
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


def _as_date(value: date | str | None) -> date | None:
    if value is None:
        return None
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    return date.fromisoformat(str(value)[:10])


def honesty_payload(*, company_code: str | None = None) -> dict[str, Any]:
    return {
        "phase": PHASE,
        "contract_version": CONTRACT_VERSION,
        "pass_stamp": PASS_STAMP,
        "commercial_module_key": COMMERCIAL_MODULE_KEY,
        "does_not_own_employee_employment": True,
        "does_not_own_dependent_master": True,
        "does_not_own_payroll_execution": True,
        "claims_adjudication_out": True,
        "no_claim_tables_in_c3": True,
        "eligible_not_enrolled": True,
        "election_not_confirmed_coverage": True,
        "internal_state_not_provider_confirmation": True,
        "contribution_not_payroll_deduction": True,
        "payroll_integration_optional": True,
        "works_payroll_off": True,
        "ja_optional": True,
        "no_invented_statutory_kuwait_policy": True,
        "manager_fail_closed_on_private_detail": True,
        "assistant_mutations": False,
        "emits_typed_facts_not_analytics_engine": True,
        "costs_not_compensation_engine": True,
        "company_code": company_code_norm(company_code) if company_code else None,
    }


def surface_composition_rules() -> dict[str, Any]:
    return {
        "hr_web": {
            "primary_admin": True,
            "separates_setup_from_operations": True,
        },
        "manager": {
            "private_benefit_detail": False,
            "status_only_when_policy_allows": True,
            "fail_closed": True,
        },
        "employee_app": {
            "my_benefits": True,
            "no_hr_admin": True,
            "states_not_conflated": True,
        },
        "hr_mobile": {
            "intentionally_operational": True,
            "no_full_plan_authoring": True,
        },
        "assistant": {"mutations": False, "read_explain_deep_link": True},
        "setup": {"owns_company_policy": True},
    }


def runtime_gate_for_company(company_code: str | None) -> dict[str, Any]:
    company = company_code_norm(company_code)
    if not company:
        return {"ok": False, "enabled": False, "error": "company_required", "phase": PHASE}
    if not _env_on(FLAG, "off"):
        return {"ok": False, "enabled": False, "error": "benefits_c3_off", "gate": "runtime_flag", "phase": PHASE}
    raw = str(os.environ.get(COMPANIES_FLAG) or "").strip()
    allow = {p.strip().upper() for p in raw.split(",") if p.strip()} if raw else set()
    if not allow:
        return {
            "ok": False,
            "enabled": False,
            "error": "benefits_company_not_allowlisted",
            "gate": "company_allowlist",
            "phase": PHASE,
        }
    if company not in allow:
        return {
            "ok": False,
            "enabled": False,
            "error": "benefits_company_not_allowlisted",
            "gate": "company_allowlist",
            "phase": PHASE,
            "company_code": company,
        }
    return {"ok": True, "enabled": True, "company_code": company, "phase": PHASE}


def ensure_benefits_administration_c3_schema(cur: Any, *, force: bool = False) -> None:
    _ = force
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS bn_company_settings (
          company_code text PRIMARY KEY,
          enabled boolean NOT NULL DEFAULT false,
          employee_self_service_enabled boolean NOT NULL DEFAULT true,
          manager_sees_private_detail boolean NOT NULL DEFAULT false,
          payroll_handoff_enabled boolean NOT NULL DEFAULT false,
          ja_eligibility_enabled boolean NOT NULL DEFAULT false,
          require_documents_when_configured boolean NOT NULL DEFAULT true,
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
    for ddl in (
        """
        CREATE TABLE IF NOT EXISTS bn_providers (
          provider_id uuid PRIMARY KEY,
          company_code text NOT NULL,
          code text NOT NULL,
          name_en text NOT NULL,
          name_ar text NOT NULL,
          status text NOT NULL DEFAULT 'active',
          created_at timestamptz NOT NULL DEFAULT now(),
          UNIQUE (company_code, code)
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS bn_plans (
          plan_id uuid PRIMARY KEY,
          company_code text NOT NULL,
          code text NOT NULL,
          category text NOT NULL,
          title_en text NOT NULL,
          title_ar text NOT NULL,
          description_en text NOT NULL DEFAULT '',
          description_ar text NOT NULL DEFAULT '',
          provider_id uuid REFERENCES bn_providers(provider_id),
          policy_group_ref text NOT NULL DEFAULT '',
          status text NOT NULL DEFAULT 'draft',
          effective_version int NOT NULL DEFAULT 1,
          tier_options jsonb NOT NULL DEFAULT '["employee_only"]'::jsonb,
          dependent_eligibility jsonb NOT NULL DEFAULT '{}'::jsonb,
          contribution_policy jsonb NOT NULL DEFAULT '{}'::jsonb,
          required_documents jsonb NOT NULL DEFAULT '[]'::jsonb,
          effective_start date,
          effective_end date,
          created_by_phone text,
          updated_by_phone text,
          created_at timestamptz NOT NULL DEFAULT now(),
          updated_at timestamptz NOT NULL DEFAULT now(),
          UNIQUE (company_code, code),
          CHECK (category IN ('medical','life_accident','allowance_perk','other_employer_sponsored')),
          CHECK (status IN ('draft','published','retired'))
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS bn_plan_versions (
          version_id uuid PRIMARY KEY,
          company_code text NOT NULL,
          plan_id uuid NOT NULL REFERENCES bn_plans(plan_id),
          effective_version int NOT NULL,
          snapshot jsonb NOT NULL,
          created_at timestamptz NOT NULL DEFAULT now(),
          UNIQUE (plan_id, effective_version)
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS bn_eligibility_rules (
          rule_id uuid PRIMARY KEY,
          company_code text NOT NULL,
          plan_id uuid NOT NULL REFERENCES bn_plans(plan_id),
          code text NOT NULL,
          rule_version int NOT NULL DEFAULT 1,
          title_en text NOT NULL,
          title_ar text NOT NULL,
          criteria jsonb NOT NULL,
          status text NOT NULL DEFAULT 'active',
          created_by_phone text,
          created_at timestamptz NOT NULL DEFAULT now(),
          UNIQUE (company_code, code, rule_version)
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS bn_enrollment_windows (
          window_id uuid PRIMARY KEY,
          company_code text NOT NULL,
          plan_id uuid NOT NULL REFERENCES bn_plans(plan_id),
          window_type text NOT NULL,
          window_version int NOT NULL DEFAULT 1,
          starts_on date NOT NULL,
          ends_on date NOT NULL,
          status text NOT NULL DEFAULT 'open',
          created_by_phone text,
          created_at timestamptz NOT NULL DEFAULT now(),
          CHECK (window_type IN ('new_hire','open_enrollment','qualifying_life_event'))
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS bn_eligibility_evaluations (
          evaluation_id uuid PRIMARY KEY,
          company_code text NOT NULL,
          employee_key text NOT NULL,
          plan_id uuid NOT NULL REFERENCES bn_plans(plan_id),
          rule_id uuid NOT NULL REFERENCES bn_eligibility_rules(rule_id),
          rule_version int NOT NULL,
          evaluated_on date NOT NULL,
          eligible boolean NOT NULL,
          explanation jsonb NOT NULL DEFAULT '{}'::jsonb,
          attributes_snapshot jsonb NOT NULL DEFAULT '{}'::jsonb,
          created_at timestamptz NOT NULL DEFAULT now()
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS bn_enrollments (
          enrollment_id uuid PRIMARY KEY,
          company_code text NOT NULL,
          employee_key text NOT NULL,
          plan_id uuid NOT NULL REFERENCES bn_plans(plan_id),
          plan_version int NOT NULL,
          eligibility_rule_id uuid,
          eligibility_rule_version int,
          eligibility_evaluation_id uuid,
          window_id uuid REFERENCES bn_enrollment_windows(window_id),
          window_version int,
          status text NOT NULL DEFAULT 'eligible',
          tier text,
          source text NOT NULL DEFAULT 'employee_self',
          actor_phone text,
          reason text NOT NULL DEFAULT '',
          elected_at timestamptz,
          confirmed_at timestamptz,
          provider_confirmed boolean NOT NULL DEFAULT false,
          created_at timestamptz NOT NULL DEFAULT now(),
          updated_at timestamptz NOT NULL DEFAULT now(),
          metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
          CHECK (status IN (
            'eligible','enrollment_open','elected','waived','pending_evidence','pending_approval',
            'confirmed','coverage_active','declined','cancelled','ended'
          ))
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS bn_coverage_periods (
          coverage_id uuid PRIMARY KEY,
          company_code text NOT NULL,
          enrollment_id uuid NOT NULL REFERENCES bn_enrollments(enrollment_id),
          employee_key text NOT NULL,
          plan_id uuid NOT NULL REFERENCES bn_plans(plan_id),
          plan_version int NOT NULL,
          tier text NOT NULL,
          status text NOT NULL DEFAULT 'requested',
          start_date date NOT NULL,
          end_date date,
          provider_confirmed boolean NOT NULL DEFAULT false,
          provenance text NOT NULL DEFAULT 'internal_recorded',
          created_by_phone text,
          created_at timestamptz NOT NULL DEFAULT now(),
          updated_at timestamptz NOT NULL DEFAULT now(),
          CHECK (status IN ('requested','elected','confirmed','active','ended')),
          CHECK (provenance IN ('internal_recorded','provider_confirmed','imported'))
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS bn_dependent_coverage_links (
          link_id uuid PRIMARY KEY,
          company_code text NOT NULL,
          coverage_id uuid NOT NULL REFERENCES bn_coverage_periods(coverage_id),
          enrollment_id uuid NOT NULL REFERENCES bn_enrollments(enrollment_id),
          dependent_id uuid NOT NULL,
          relationship_snapshot text NOT NULL DEFAULT '',
          evidence_ref text NOT NULL DEFAULT '',
          status text NOT NULL DEFAULT 'covered',
          created_at timestamptz NOT NULL DEFAULT now(),
          UNIQUE (coverage_id, dependent_id)
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS bn_evidence_requests (
          evidence_id uuid PRIMARY KEY,
          company_code text NOT NULL,
          enrollment_id uuid NOT NULL REFERENCES bn_enrollments(enrollment_id),
          document_type text NOT NULL,
          status text NOT NULL DEFAULT 'required',
          shared_intake_ref text NOT NULL DEFAULT '',
          created_at timestamptz NOT NULL DEFAULT now(),
          updated_at timestamptz NOT NULL DEFAULT now()
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS bn_contributions (
          contribution_id uuid PRIMARY KEY,
          company_code text NOT NULL,
          plan_id uuid NOT NULL REFERENCES bn_plans(plan_id),
          plan_version int NOT NULL,
          enrollment_id uuid REFERENCES bn_enrollments(enrollment_id),
          coverage_id uuid REFERENCES bn_coverage_periods(coverage_id),
          kind text NOT NULL,
          mode text NOT NULL,
          amount numeric,
          percent numeric,
          currency text NOT NULL DEFAULT 'KWD',
          effective_start date NOT NULL,
          effective_end date,
          contribution_version int NOT NULL DEFAULT 1,
          created_by_phone text,
          created_at timestamptz NOT NULL DEFAULT now(),
          CHECK (kind IN ('employer','employee')),
          CHECK (mode IN ('fixed','percent'))
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS bn_payroll_handoffs (
          handoff_id uuid PRIMARY KEY,
          company_code text NOT NULL,
          enrollment_id uuid NOT NULL REFERENCES bn_enrollments(enrollment_id),
          coverage_id uuid REFERENCES bn_coverage_periods(coverage_id),
          employee_key text NOT NULL,
          employee_amount numeric,
          employer_amount numeric,
          currency text NOT NULL DEFAULT 'KWD',
          period_start date NOT NULL,
          period_end date,
          component_mapping jsonb NOT NULL DEFAULT '{}'::jsonb,
          status text NOT NULL DEFAULT 'ready',
          applied_to_payroll boolean NOT NULL DEFAULT false,
          finalized_payroll_rewritten boolean NOT NULL DEFAULT false,
          created_at timestamptz NOT NULL DEFAULT now(),
          CHECK (finalized_payroll_rewritten = false)
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS bn_provider_member_refs (
          member_ref_id uuid PRIMARY KEY,
          company_code text NOT NULL,
          enrollment_id uuid REFERENCES bn_enrollments(enrollment_id),
          coverage_id uuid REFERENCES bn_coverage_periods(coverage_id),
          employee_key text,
          dependent_id uuid,
          policy_group_number text NOT NULL DEFAULT '',
          member_id text NOT NULL DEFAULT '',
          source text NOT NULL DEFAULT 'internal',
          provider_status_confirmed boolean NOT NULL DEFAULT false,
          created_at timestamptz NOT NULL DEFAULT now()
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS bn_wave5_fact_outbox (
          fact_id uuid PRIMARY KEY,
          company_code text NOT NULL,
          fact_type text NOT NULL,
          entity_type text NOT NULL,
          entity_id text NOT NULL,
          payload jsonb NOT NULL,
          created_at timestamptz NOT NULL DEFAULT now()
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS bn_audit_events (
          audit_id uuid PRIMARY KEY,
          company_code text NOT NULL,
          actor_phone text,
          action text NOT NULL,
          entity_type text NOT NULL,
          entity_id text NOT NULL,
          detail jsonb NOT NULL DEFAULT '{}'::jsonb,
          created_at timestamptz NOT NULL DEFAULT now()
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS bn_notification_dedupe (
          dedupe_key text PRIMARY KEY,
          company_code text NOT NULL,
          created_at timestamptz NOT NULL DEFAULT now()
        )
        """,
    ):
        cur.execute(ddl)


def _audit(cur: Any, *, company: str, actor: str, action: str, entity_type: str, entity_id: str, detail: dict | None = None) -> None:
    cur.execute(
        """
        INSERT INTO bn_audit_events (audit_id, company_code, actor_phone, action, entity_type, entity_id, detail)
        VALUES (%s,%s,%s,%s,%s,%s,%s::jsonb)
        """,
        (str(uuid.uuid4()), company, _digits(actor), action, entity_type, entity_id, json.dumps(detail or {})),
    )


def _emit(cur: Any, *, company: str, fact_type: str, entity_type: str, entity_id: str, payload: dict) -> None:
    cur.execute(
        """
        INSERT INTO bn_wave5_fact_outbox (fact_id, company_code, fact_type, entity_type, entity_id, payload)
        VALUES (%s,%s,%s,%s,%s,%s::jsonb)
        """,
        (str(uuid.uuid4()), company, fact_type, entity_type, entity_id, json.dumps(payload)),
    )


def _row(cur: Any) -> dict[str, Any] | None:
    fetched = cur.fetchone()
    return dict(fetched) if fetched else None


def enable_company_benefits(cur: Any, *, company_code: str, actor_phone: str, reason: str, **kwargs: Any) -> dict[str, Any]:
    if not str(reason or "").strip():
        return {"ok": False, "error": "audit_reason_required"}
    gate = runtime_gate_for_company(company_code)
    if not gate.get("ok"):
        return gate
    company = gate["company_code"]
    ensure_benefits_administration_c3_schema(cur)
    cur.execute(
        """
        INSERT INTO bn_company_settings (
          company_code, enabled, employee_self_service_enabled, manager_sees_private_detail,
          payroll_handoff_enabled, ja_eligibility_enabled, require_documents_when_configured,
          enabled_by_phone, enabled_reason, enabled_at, disabled_at, updated_by_phone, updated_at
        ) VALUES (%s,true,%s,%s,%s,%s,%s,%s,%s,now(),NULL,%s,now())
        ON CONFLICT (company_code) DO UPDATE SET
          enabled=true,
          employee_self_service_enabled=EXCLUDED.employee_self_service_enabled,
          manager_sees_private_detail=EXCLUDED.manager_sees_private_detail,
          payroll_handoff_enabled=EXCLUDED.payroll_handoff_enabled,
          ja_eligibility_enabled=EXCLUDED.ja_eligibility_enabled,
          require_documents_when_configured=EXCLUDED.require_documents_when_configured,
          enabled_by_phone=EXCLUDED.enabled_by_phone, enabled_reason=EXCLUDED.enabled_reason,
          enabled_at=now(), disabled_at=NULL, updated_by_phone=EXCLUDED.updated_by_phone, updated_at=now()
        RETURNING *
        """,
        (
            company,
            bool(kwargs.get("employee_self_service_enabled", True)),
            bool(kwargs.get("manager_sees_private_detail", False)),
            bool(kwargs.get("payroll_handoff_enabled", False)),
            bool(kwargs.get("ja_eligibility_enabled", False)),
            bool(kwargs.get("require_documents_when_configured", True)),
            _digits(actor_phone),
            str(reason).strip()[:500],
            _digits(actor_phone),
        ),
    )
    row = _row(cur)
    _audit(cur, company=company, actor=actor_phone, action="enable", entity_type="company", entity_id=company, detail={"reason": reason})
    return {"ok": True, "settings": row, "honesty": honesty_payload(company_code=company)}


def disable_company_benefits(cur: Any, *, company_code: str, actor_phone: str, reason: str) -> dict[str, Any]:
    company = company_code_norm(company_code)
    ensure_benefits_administration_c3_schema(cur)
    cur.execute(
        """
        UPDATE bn_company_settings
           SET enabled=false, disabled_at=now(), updated_by_phone=%s, updated_at=now()
         WHERE company_code=%s RETURNING *
        """,
        (_digits(actor_phone), company),
    )
    row = _row(cur)
    _audit(cur, company=company, actor=actor_phone, action="disable", entity_type="company", entity_id=company, detail={"reason": reason})
    return {"ok": True, "settings": row, "history_retained": True}


def module_enabled_for_company(cur: Any, company_code: str) -> bool:
    gate = runtime_gate_for_company(company_code)
    if not gate.get("ok"):
        return False
    ensure_benefits_administration_c3_schema(cur)
    cur.execute("SELECT enabled FROM bn_company_settings WHERE company_code=%s", (gate["company_code"],))
    row = cur.fetchone()
    return bool(row and dict(row).get("enabled"))


def _require_enabled(cur: Any, company_code: str) -> dict[str, Any]:
    gate = runtime_gate_for_company(company_code)
    if not gate.get("ok"):
        return gate
    if not module_enabled_for_company(cur, gate["company_code"]):
        return {"ok": False, "error": "benefits_disabled_for_company", "company_code": gate["company_code"]}
    return {"ok": True, "company_code": gate["company_code"]}


def _settings(cur: Any, company: str) -> dict[str, Any]:
    cur.execute("SELECT * FROM bn_company_settings WHERE company_code=%s", (company,))
    return _row(cur) or {}


def upsert_provider(cur: Any, *, company_code: str, actor_phone: str, code: str, name_en: str, name_ar: str) -> dict[str, Any]:
    ent = _require_enabled(cur, company_code)
    if not ent.get("ok"):
        return ent
    company = ent["company_code"]
    provider_id = str(uuid.uuid4())
    cur.execute(
        """
        INSERT INTO bn_providers (provider_id, company_code, code, name_en, name_ar)
        VALUES (%s,%s,%s,%s,%s)
        ON CONFLICT (company_code, code) DO UPDATE SET name_en=EXCLUDED.name_en, name_ar=EXCLUDED.name_ar
        RETURNING *
        """,
        (provider_id, company, str(code).strip(), name_en.strip(), name_ar.strip()),
    )
    return {"ok": True, "provider": _row(cur)}


def upsert_plan(
    cur: Any,
    *,
    company_code: str,
    actor_phone: str,
    code: str,
    category: str,
    title_en: str,
    title_ar: str,
    status: str = "draft",
    provider_id: str | None = None,
    policy_group_ref: str = "",
    tier_options: list[str] | None = None,
    dependent_eligibility: dict | None = None,
    contribution_policy: dict | None = None,
    required_documents: list | None = None,
    description_en: str = "",
    description_ar: str = "",
    effective_start: date | str | None = None,
    reason: str = "upsert plan",
) -> dict[str, Any]:
    ent = _require_enabled(cur, company_code)
    if not ent.get("ok"):
        return ent
    company = ent["company_code"]
    cat = str(category or "").lower()
    st = str(status or "draft").lower()
    if cat not in PLAN_CATEGORIES:
        return {"ok": False, "error": "invalid_category", "allowed": list(PLAN_CATEGORIES)}
    if st not in PLAN_STATUSES:
        return {"ok": False, "error": "invalid_status"}
    if not str(code).strip() or not title_en.strip() or not title_ar.strip():
        return {"ok": False, "error": "code_and_bilingual_titles_required"}
    tiers = list(tier_options or ["employee_only"])
    for t in tiers:
        if t not in TIER_OPTIONS:
            return {"ok": False, "error": "invalid_tier", "tier": t}
    # Must not invent ownership of employee/dependent/payroll
    for blob in (dependent_eligibility or {}, contribution_policy or {}):
        for forbidden in ("employee_key", "payroll_run_id", "claim_id"):
            if forbidden in blob:
                return {"ok": False, "error": "must_not_own_external_truth", "field": forbidden}
    cur.execute("SELECT * FROM bn_plans WHERE company_code=%s AND code=%s", (company, str(code).strip()))
    existing = _row(cur)
    snapshot = {
        "title_en": title_en.strip(),
        "title_ar": title_ar.strip(),
        "category": cat,
        "tier_options": tiers,
        "dependent_eligibility": dependent_eligibility or {},
        "contribution_policy": contribution_policy or {},
        "required_documents": required_documents or [],
        "policy_group_ref": policy_group_ref,
    }
    if existing:
        ver = int(existing["effective_version"]) + 1
        cur.execute(
            """
            UPDATE bn_plans SET category=%s, title_en=%s, title_ar=%s, description_en=%s, description_ar=%s,
              provider_id=%s, policy_group_ref=%s, status=%s, effective_version=%s, tier_options=%s::jsonb,
              dependent_eligibility=%s::jsonb, contribution_policy=%s::jsonb, required_documents=%s::jsonb,
              effective_start=%s, updated_by_phone=%s, updated_at=now()
             WHERE plan_id=%s RETURNING *
            """,
            (
                cat, title_en.strip(), title_ar.strip(), description_en, description_ar, provider_id,
                policy_group_ref, st, ver, json.dumps(tiers), json.dumps(dependent_eligibility or {}),
                json.dumps(contribution_policy or {}), json.dumps(required_documents or []),
                _as_date(effective_start), _digits(actor_phone), str(existing["plan_id"]),
            ),
        )
        row = _row(cur)
    else:
        plan_id = str(uuid.uuid4())
        cur.execute(
            """
            INSERT INTO bn_plans (
              plan_id, company_code, code, category, title_en, title_ar, description_en, description_ar,
              provider_id, policy_group_ref, status, tier_options, dependent_eligibility, contribution_policy,
              required_documents, effective_start, created_by_phone, updated_by_phone
            ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb,%s::jsonb,%s::jsonb,%s::jsonb,%s,%s,%s) RETURNING *
            """,
            (
                plan_id, company, str(code).strip(), cat, title_en.strip(), title_ar.strip(), description_en,
                description_ar, provider_id, policy_group_ref, st, json.dumps(tiers),
                json.dumps(dependent_eligibility or {}), json.dumps(contribution_policy or {}),
                json.dumps(required_documents or []), _as_date(effective_start),
                _digits(actor_phone), _digits(actor_phone),
            ),
        )
        row = _row(cur)
    assert row
    cur.execute(
        """
        INSERT INTO bn_plan_versions (version_id, company_code, plan_id, effective_version, snapshot)
        VALUES (%s,%s,%s,%s,%s::jsonb)
        ON CONFLICT (plan_id, effective_version) DO NOTHING
        """,
        (str(uuid.uuid4()), company, str(row["plan_id"]), int(row["effective_version"]), json.dumps(snapshot)),
    )
    _audit(cur, company=company, actor=actor_phone, action="upsert_plan", entity_type="plan", entity_id=str(row["plan_id"]), detail={"reason": reason})
    return {"ok": True, "plan": row, "stable_id": str(row["plan_id"]), "claims_engine_absent": True}


def create_eligibility_rule(
    cur: Any,
    *,
    company_code: str,
    actor_phone: str,
    plan_id: str,
    code: str,
    title_en: str,
    title_ar: str,
    criteria: dict[str, Any],
    rule_version: int = 1,
) -> dict[str, Any]:
    ent = _require_enabled(cur, company_code)
    if not ent.get("ok"):
        return ent
    company = ent["company_code"]
    rule_id = str(uuid.uuid4())
    cur.execute(
        """
        INSERT INTO bn_eligibility_rules (
          rule_id, company_code, plan_id, code, rule_version, title_en, title_ar, criteria, created_by_phone
        ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s::jsonb,%s) RETURNING *
        """,
        (
            rule_id, company, plan_id, code, int(rule_version), title_en, title_ar,
            json.dumps(criteria or {}), _digits(actor_phone),
        ),
    )
    return {"ok": True, "rule": _row(cur)}


def evaluate_eligibility(
    cur: Any,
    *,
    company_code: str,
    employee_key: str,
    plan_id: str,
    rule_id: str,
    attributes: dict[str, Any] | None = None,
    evaluated_on: date | str | None = None,
) -> dict[str, Any]:
    """Explainable evaluation — eligible ≠ enrolled. Never infer from prior enrollment."""
    ent = _require_enabled(cur, company_code)
    if not ent.get("ok"):
        return ent
    company = ent["company_code"]
    cur.execute(
        "SELECT * FROM bn_eligibility_rules WHERE company_code=%s AND rule_id=%s AND plan_id=%s",
        (company, rule_id, plan_id),
    )
    rule = _row(cur)
    if not rule:
        return {"ok": False, "error": "eligibility_rule_not_found"}
    attrs = dict(attributes or {})
    criteria = dict(rule.get("criteria") or {})
    reasons = []
    eligible = True
    # Simple explicit criteria: employment_status, employment_type, location, grade, tenure_days_min
    for key, expected in criteria.items():
        actual = attrs.get(key)
        if key == "tenure_days_min":
            ok = int(attrs.get("tenure_days") or 0) >= int(expected)
            if not ok:
                eligible = False
                reasons.append({"field": key, "expected_min": expected, "actual": attrs.get("tenure_days")})
            continue
        if actual != expected:
            eligible = False
            reasons.append({"field": key, "expected": expected, "actual": actual})
    day = _as_date(evaluated_on) or date.today()
    evaluation_id = str(uuid.uuid4())
    explanation = {"eligible": eligible, "reasons": reasons, "inferred_from_enrollment": False}
    cur.execute(
        """
        INSERT INTO bn_eligibility_evaluations (
          evaluation_id, company_code, employee_key, plan_id, rule_id, rule_version, evaluated_on,
          eligible, explanation, attributes_snapshot
        ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb,%s::jsonb) RETURNING *
        """,
        (
            evaluation_id, company, employee_key, plan_id, rule_id, int(rule["rule_version"]), day,
            eligible, json.dumps(explanation), json.dumps(attrs),
        ),
    )
    row = _row(cur)
    _emit(
        cur,
        company=company,
        fact_type="benefits.eligible_population",
        entity_type="eligibility_evaluation",
        entity_id=evaluation_id,
        payload={"employee_key": employee_key, "plan_id": plan_id, "eligible": eligible, "rule_version": rule["rule_version"]},
    )
    return {
        "ok": True,
        "evaluation": row,
        "eligible": eligible,
        "enrolled": False,
        "eligible_not_enrolled": True,
        "never_inferred_from_enrollment": True,
    }


def open_enrollment_window(
    cur: Any,
    *,
    company_code: str,
    actor_phone: str,
    plan_id: str,
    window_type: str,
    starts_on: date | str,
    ends_on: date | str,
    window_version: int = 1,
) -> dict[str, Any]:
    ent = _require_enabled(cur, company_code)
    if not ent.get("ok"):
        return ent
    company = ent["company_code"]
    wt = str(window_type or "").lower()
    if wt not in WINDOW_TYPES:
        return {"ok": False, "error": "invalid_window_type", "allowed": list(WINDOW_TYPES)}
    window_id = str(uuid.uuid4())
    cur.execute(
        """
        INSERT INTO bn_enrollment_windows (
          window_id, company_code, plan_id, window_type, window_version, starts_on, ends_on, created_by_phone
        ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s) RETURNING *
        """,
        (
            window_id, company, plan_id, wt, int(window_version),
            _as_date(starts_on), _as_date(ends_on), _digits(actor_phone),
        ),
    )
    row = _row(cur)
    _notify_dedupe(cur, company=company, key=f"window_open:{window_id}")
    return {"ok": True, "window": row}


def start_enrollment(
    cur: Any,
    *,
    company_code: str,
    actor_phone: str,
    employee_key: str,
    plan_id: str,
    evaluation_id: str,
    window_id: str | None = None,
    source: str = "employee_self",
) -> dict[str, Any]:
    ent = _require_enabled(cur, company_code)
    if not ent.get("ok"):
        return ent
    company = ent["company_code"]
    cur.execute("SELECT * FROM bn_plans WHERE company_code=%s AND plan_id=%s", (company, plan_id))
    plan = _row(cur)
    if not plan:
        return {"ok": False, "error": "plan_not_found"}
    cur.execute(
        "SELECT * FROM bn_eligibility_evaluations WHERE company_code=%s AND evaluation_id=%s",
        (company, evaluation_id),
    )
    ev = _row(cur)
    if not ev or not ev.get("eligible"):
        return {"ok": False, "error": "not_eligible", "eligible_not_enrolled": True}
    window_version = None
    if window_id:
        cur.execute(
            "SELECT * FROM bn_enrollment_windows WHERE company_code=%s AND window_id=%s",
            (company, window_id),
        )
        win = _row(cur)
        if not win:
            return {"ok": False, "error": "window_not_found"}
        window_version = int(win["window_version"])
    enrollment_id = str(uuid.uuid4())
    cur.execute(
        """
        INSERT INTO bn_enrollments (
          enrollment_id, company_code, employee_key, plan_id, plan_version,
          eligibility_rule_id, eligibility_rule_version, eligibility_evaluation_id,
          window_id, window_version, status, source, actor_phone
        ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'enrollment_open',%s,%s) RETURNING *
        """,
        (
            enrollment_id, company, employee_key, plan_id, int(plan["effective_version"]),
            str(ev["rule_id"]), int(ev["rule_version"]), evaluation_id,
            window_id, window_version, source, _digits(actor_phone),
        ),
    )
    row = _row(cur)
    _emit(
        cur,
        company=company,
        fact_type="benefits.enrollment_population",
        entity_type="enrollment",
        entity_id=enrollment_id,
        payload={"employee_key": employee_key, "plan_id": plan_id, "plan_version": plan["effective_version"], "status": "enrollment_open"},
    )
    return {"ok": True, "enrollment": row, "election_not_confirmed_coverage": True}


def elect_or_waive(
    cur: Any,
    *,
    company_code: str,
    actor_phone: str,
    enrollment_id: str,
    waive: bool = False,
    tier: str | None = None,
    reason: str = "",
) -> dict[str, Any]:
    ent = _require_enabled(cur, company_code)
    if not ent.get("ok"):
        return ent
    company = ent["company_code"]
    settings = _settings(cur, company)
    if settings.get("employee_self_service_enabled") is False and str(actor_phone):
        # HR/ops may still act; self-service flag is for employee path honesty
        pass
    cur.execute(
        "SELECT * FROM bn_enrollments WHERE company_code=%s AND enrollment_id=%s",
        (company, enrollment_id),
    )
    enr = _row(cur)
    if not enr:
        return {"ok": False, "error": "enrollment_not_found"}
    if enr["status"] not in {"enrollment_open", "eligible", "pending_evidence"}:
        return {"ok": False, "error": "enrollment_not_open", "status": enr["status"]}
    if waive:
        cur.execute(
            """
            UPDATE bn_enrollments SET status='waived', elected_at=now(), reason=%s, actor_phone=%s, updated_at=now()
             WHERE enrollment_id=%s RETURNING *
            """,
            (str(reason)[:500], _digits(actor_phone), enrollment_id),
        )
        row = _row(cur)
        _emit(
            cur, company=company, fact_type="benefits.waiver", entity_type="enrollment",
            entity_id=enrollment_id, payload={"employee_key": enr["employee_key"]},
        )
        return {"ok": True, "enrollment": row, "waived": True, "coverage_active": False, "election_not_confirmed_coverage": True}
    if not tier or tier not in TIER_OPTIONS:
        return {"ok": False, "error": "tier_required", "allowed": list(TIER_OPTIONS)}
    # Required documents may move to pending_evidence
    cur.execute("SELECT required_documents FROM bn_plans WHERE plan_id=%s", (enr["plan_id"],))
    plan = _row(cur) or {}
    docs = plan.get("required_documents") or []
    if isinstance(docs, str):
        docs = json.loads(docs)
    next_status = "pending_evidence" if docs and settings.get("require_documents_when_configured", True) else "elected"
    cur.execute(
        """
        UPDATE bn_enrollments
           SET status=%s, tier=%s, elected_at=now(), reason=%s, actor_phone=%s, updated_at=now()
         WHERE enrollment_id=%s RETURNING *
        """,
        (next_status, tier, str(reason)[:500], _digits(actor_phone), enrollment_id),
    )
    row = _row(cur)
    assert row
    for doc in docs:
        cur.execute(
            """
            INSERT INTO bn_evidence_requests (evidence_id, company_code, enrollment_id, document_type)
            VALUES (%s,%s,%s,%s)
            """,
            (str(uuid.uuid4()), company, enrollment_id, str(doc)),
        )
    return {
        "ok": True,
        "enrollment": row,
        "waived": False,
        "election_not_confirmed_coverage": True,
        "coverage_active": False,
    }


def submit_evidence(
    cur: Any, *, company_code: str, actor_phone: str, enrollment_id: str, document_type: str, shared_intake_ref: str
) -> dict[str, Any]:
    ent = _require_enabled(cur, company_code)
    if not ent.get("ok"):
        return ent
    company = ent["company_code"]
    if not str(shared_intake_ref).strip():
        return {"ok": False, "error": "shared_intake_ref_required"}
    cur.execute(
        """
        UPDATE bn_evidence_requests
           SET status='submitted', shared_intake_ref=%s, updated_at=now()
         WHERE company_code=%s AND enrollment_id=%s AND document_type=%s
        RETURNING *
        """,
        (shared_intake_ref, company, enrollment_id, document_type),
    )
    evid = _row(cur)
    if not evid:
        return {"ok": False, "error": "evidence_request_not_found"}
    cur.execute(
        """
        SELECT COUNT(*) AS c FROM bn_evidence_requests
         WHERE enrollment_id=%s AND status='required'
        """,
        (enrollment_id,),
    )
    remaining = int(dict(cur.fetchone())["c"])
    if remaining == 0:
        cur.execute(
            """
            UPDATE bn_enrollments SET status='elected', updated_at=now(), actor_phone=%s
             WHERE enrollment_id=%s AND status='pending_evidence' RETURNING *
            """,
            (_digits(actor_phone), enrollment_id),
        )
        enr = _row(cur)
    else:
        cur.execute("SELECT * FROM bn_enrollments WHERE enrollment_id=%s", (enrollment_id,))
        enr = _row(cur)
    return {"ok": True, "evidence": evid, "enrollment": enr, "remaining_required": remaining}


def confirm_enrollment(
    cur: Any,
    *,
    company_code: str,
    actor_phone: str,
    enrollment_id: str,
    coverage_start: date | str,
    coverage_end: date | str | None = None,
    provider_confirmed: bool = False,
) -> dict[str, Any]:
    """Approval/confirmation — not the same as provider activation unless provider_confirmed."""
    ent = _require_enabled(cur, company_code)
    if not ent.get("ok"):
        return ent
    company = ent["company_code"]
    cur.execute(
        "SELECT * FROM bn_enrollments WHERE company_code=%s AND enrollment_id=%s",
        (company, enrollment_id),
    )
    enr = _row(cur)
    if not enr:
        return {"ok": False, "error": "enrollment_not_found"}
    if enr["status"] not in {"elected", "pending_approval"}:
        return {"ok": False, "error": "enrollment_not_ready_to_confirm", "status": enr["status"]}
    # Internal confirmation can activate internal coverage; provider flag separate
    provenance = "provider_confirmed" if provider_confirmed else "internal_recorded"
    coverage_id = str(uuid.uuid4())
    cur.execute(
        """
        INSERT INTO bn_coverage_periods (
          coverage_id, company_code, enrollment_id, employee_key, plan_id, plan_version, tier,
          status, start_date, end_date, provider_confirmed, provenance, created_by_phone
        ) VALUES (%s,%s,%s,%s,%s,%s,%s,'active',%s,%s,%s,%s,%s) RETURNING *
        """,
        (
            coverage_id, company, enrollment_id, enr["employee_key"], enr["plan_id"], enr["plan_version"],
            enr["tier"] or "employee_only", _as_date(coverage_start), _as_date(coverage_end),
            bool(provider_confirmed), provenance, _digits(actor_phone),
        ),
    )
    coverage = _row(cur)
    cur.execute(
        """
        UPDATE bn_enrollments
           SET status='coverage_active', confirmed_at=now(), provider_confirmed=%s, updated_at=now(), actor_phone=%s
         WHERE enrollment_id=%s RETURNING *
        """,
        (bool(provider_confirmed), _digits(actor_phone), enrollment_id),
    )
    enrollment = _row(cur)
    _emit(
        cur,
        company=company,
        fact_type="benefits.coverage_active",
        entity_type="coverage",
        entity_id=coverage_id,
        payload={
            "employee_key": enr["employee_key"],
            "plan_id": str(enr["plan_id"]),
            "plan_version": enr["plan_version"],
            "provider_confirmed": bool(provider_confirmed),
            "provenance": provenance,
        },
    )
    _emit(
        cur,
        company=company,
        fact_type="benefits.enrollment_completion",
        entity_type="enrollment",
        entity_id=enrollment_id,
        payload={"status": "coverage_active"},
    )
    return {
        "ok": True,
        "enrollment": enrollment,
        "coverage": coverage,
        "election_not_confirmed_coverage": False,
        "internal_recorded": provenance == "internal_recorded",
        "provider_confirmed": bool(provider_confirmed),
        "approval_not_provider_activation": not provider_confirmed,
    }


def link_dependent_coverage(
    cur: Any,
    *,
    company_code: str,
    actor_phone: str,
    coverage_id: str,
    dependent_id: str,
    evidence_ref: str = "",
) -> dict[str, Any]:
    """Coverage relationship to Wave 3 canonical dependent — no second dependent master."""
    ent = _require_enabled(cur, company_code)
    if not ent.get("ok"):
        return ent
    company = ent["company_code"]
    cur.execute(
        "SELECT * FROM bn_coverage_periods WHERE company_code=%s AND coverage_id=%s",
        (company, coverage_id),
    )
    cov = _row(cur)
    if not cov:
        return {"ok": False, "error": "coverage_not_found"}
    # Reference Wave 3 dependent if table exists; never create dependent
    relationship = ""
    cur.execute("SELECT to_regclass('employee_dependents') AS t")
    if dict(cur.fetchone()).get("t"):
        cur.execute(
            """
            SELECT dependent_id, relationship, status FROM employee_dependents
             WHERE company_code=%s AND dependent_id=%s
            """,
            (company, dependent_id),
        )
        dep = cur.fetchone()
        if not dep:
            return {"ok": False, "error": "canonical_dependent_not_found", "does_not_create_dependent_master": True}
        dep_d = dict(dep)
        if dep_d.get("status") != "active":
            return {"ok": False, "error": "dependent_not_active"}
        relationship = str(dep_d.get("relationship") or "")
    else:
        # Extensible when dependents table absent — still store reference only
        relationship = "referenced"
    link_id = str(uuid.uuid4())
    cur.execute(
        """
        INSERT INTO bn_dependent_coverage_links (
          link_id, company_code, coverage_id, enrollment_id, dependent_id, relationship_snapshot, evidence_ref
        ) VALUES (%s,%s,%s,%s,%s,%s,%s) RETURNING *
        """,
        (link_id, company, coverage_id, cov["enrollment_id"], dependent_id, relationship, evidence_ref),
    )
    return {
        "ok": True,
        "link": _row(cur),
        "does_not_create_dependent_master": True,
        "references_canonical_dependent": True,
    }


def define_contribution(
    cur: Any,
    *,
    company_code: str,
    actor_phone: str,
    plan_id: str,
    plan_version: int,
    kind: str,
    mode: str,
    amount: float | None = None,
    percent: float | None = None,
    currency: str = "KWD",
    effective_start: date | str,
    enrollment_id: str | None = None,
    coverage_id: str | None = None,
    contribution_version: int = 1,
) -> dict[str, Any]:
    ent = _require_enabled(cur, company_code)
    if not ent.get("ok"):
        return ent
    company = ent["company_code"]
    k = str(kind).lower()
    m = str(mode).lower()
    if k not in CONTRIB_KINDS or m not in CONTRIB_MODES:
        return {"ok": False, "error": "invalid_contribution"}
    contribution_id = str(uuid.uuid4())
    cur.execute(
        """
        INSERT INTO bn_contributions (
          contribution_id, company_code, plan_id, plan_version, enrollment_id, coverage_id,
          kind, mode, amount, percent, currency, effective_start, contribution_version, created_by_phone
        ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING *
        """,
        (
            contribution_id, company, plan_id, int(plan_version), enrollment_id, coverage_id,
            k, m, amount, percent, currency, _as_date(effective_start), int(contribution_version),
            _digits(actor_phone),
        ),
    )
    row = _row(cur)
    _emit(
        cur,
        company=company,
        fact_type="benefits.contribution",
        entity_type="contribution",
        entity_id=contribution_id,
        payload={"kind": k, "mode": m, "currency": currency, "not_payroll_deduction": True},
    )
    return {
        "ok": True,
        "contribution": row,
        "contribution_not_payroll_deduction": True,
        "paid_amount": None,
    }


def create_payroll_handoff(
    cur: Any,
    *,
    company_code: str,
    actor_phone: str,
    enrollment_id: str,
    coverage_id: str | None,
    employee_amount: float,
    employer_amount: float,
    period_start: date | str,
    period_end: date | str | None = None,
    component_mapping: dict | None = None,
) -> dict[str, Any]:
    """OPTIONAL Payroll consume instruction — Benefits ≠ payroll applied."""
    ent = _require_enabled(cur, company_code)
    if not ent.get("ok"):
        return ent
    company = ent["company_code"]
    settings = _settings(cur, company)
    if not settings.get("payroll_handoff_enabled"):
        return {"ok": False, "error": "payroll_handoff_disabled", "works_payroll_off": True}
    cur.execute(
        "SELECT * FROM bn_enrollments WHERE company_code=%s AND enrollment_id=%s",
        (company, enrollment_id),
    )
    enr = _row(cur)
    if not enr:
        return {"ok": False, "error": "enrollment_not_found"}
    if enr["status"] != "coverage_active":
        return {
            "ok": False,
            "error": "enrollment_confirmed_not_enough_without_active_coverage_for_handoff",
            "benefit_enrollment_confirmed_not_payroll_deduction_applied": True,
        }
    handoff_id = str(uuid.uuid4())
    cur.execute(
        """
        INSERT INTO bn_payroll_handoffs (
          handoff_id, company_code, enrollment_id, coverage_id, employee_key,
          employee_amount, employer_amount, period_start, period_end, component_mapping,
          applied_to_payroll, finalized_payroll_rewritten
        ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb,false,false) RETURNING *
        """,
        (
            handoff_id, company, enrollment_id, coverage_id, enr["employee_key"],
            employee_amount, employer_amount, _as_date(period_start), _as_date(period_end),
            json.dumps(component_mapping or {}),
        ),
    )
    return {
        "ok": True,
        "handoff": _row(cur),
        "applied_to_payroll": False,
        "benefit_enrollment_confirmed_not_payroll_deduction_applied": True,
        "benefits_contribution_not_paid_amount": True,
        "finalized_payroll_not_rewritten": True,
        "payroll_remains_execution_authority": True,
    }


def set_provider_member_ref(
    cur: Any,
    *,
    company_code: str,
    enrollment_id: str | None = None,
    coverage_id: str | None = None,
    employee_key: str | None = None,
    dependent_id: str | None = None,
    policy_group_number: str = "",
    member_id: str = "",
    provider_status_confirmed: bool = False,
) -> dict[str, Any]:
    ent = _require_enabled(cur, company_code)
    if not ent.get("ok"):
        return ent
    company = ent["company_code"]
    member_ref_id = str(uuid.uuid4())
    cur.execute(
        """
        INSERT INTO bn_provider_member_refs (
          member_ref_id, company_code, enrollment_id, coverage_id, employee_key, dependent_id,
          policy_group_number, member_id, provider_status_confirmed
        ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING *
        """,
        (
            member_ref_id, company, enrollment_id, coverage_id, employee_key, dependent_id,
            policy_group_number, member_id, bool(provider_status_confirmed),
        ),
    )
    return {
        "ok": True,
        "member_ref": _row(cur),
        "not_proof_of_insurer_active_unless_provider_confirmed": not provider_status_confirmed,
    }


def consume_employment_end_event(
    cur: Any,
    *,
    company_code: str,
    actor_phone: str,
    employee_key: str,
    employment_end_date: date | str,
    continuation_in_mvp: bool = False,
) -> dict[str, Any]:
    """Consume lifecycle event — do not mutate employment. Continuation modeled honestly if not in MVP."""
    ent = _require_enabled(cur, company_code)
    if not ent.get("ok"):
        return ent
    company = ent["company_code"]
    end_day = _as_date(employment_end_date)
    if not continuation_in_mvp:
        cur.execute(
            """
            UPDATE bn_coverage_periods
               SET end_date=COALESCE(end_date, %s), status='ended', updated_at=now()
             WHERE company_code=%s AND employee_key=%s AND status='active'
            RETURNING coverage_id
            """,
            (end_day, company, employee_key),
        )
        ended = [dict(r)["coverage_id"] for r in cur.fetchall()]
        cur.execute(
            """
            UPDATE bn_enrollments SET status='ended', updated_at=now(), actor_phone=%s
             WHERE company_code=%s AND employee_key=%s AND status='coverage_active'
            """,
            (_digits(actor_phone), company, employee_key),
        )
        return {
            "ok": True,
            "ended_coverage_ids": [str(x) for x in ended],
            "employment_mutated": False,
            "continuation_coverage_in_mvp": False,
            "modeled_honestly_without_invented_kuwait_rules": True,
        }
    return {"ok": False, "error": "continuation_not_implemented"}


def resolve_coverage_as_of(
    cur: Any, *, company_code: str, employee_key: str, as_of: date | str
) -> dict[str, Any]:
    gate = runtime_gate_for_company(company_code)
    if not gate.get("ok"):
        return gate
    company = gate["company_code"]
    day = _as_date(as_of)
    cur.execute(
        """
        SELECT * FROM bn_coverage_periods
         WHERE company_code=%s AND employee_key=%s
           AND start_date <= %s
           AND (end_date IS NULL OR end_date >= %s)
         ORDER BY start_date DESC
        """,
        (company, employee_key, day, day),
    )
    rows = [dict(r) for r in cur.fetchall()]
    return {"ok": True, "as_of": str(day), "coverage": rows, "reconstructable": True}


def employee_benefits_view(cur: Any, *, company_code: str, employee_key: str) -> dict[str, Any]:
    gate = runtime_gate_for_company(company_code)
    if not gate.get("ok"):
        return gate
    company = gate["company_code"]
    if not module_enabled_for_company(cur, company):
        return {"ok": False, "error": "benefits_disabled_for_company"}
    settings = _settings(cur, company)
    if settings.get("employee_self_service_enabled") is False:
        return {"ok": False, "error": "employee_self_service_disabled"}
    cur.execute(
        "SELECT enrollment_id, plan_id, plan_version, status, tier, provider_confirmed, elected_at, confirmed_at FROM bn_enrollments WHERE company_code=%s AND employee_key=%s ORDER BY created_at DESC",
        (company, employee_key),
    )
    enrollments = [dict(r) for r in cur.fetchall()]
    cur.execute(
        "SELECT coverage_id, plan_id, plan_version, tier, status, start_date, end_date, provider_confirmed, provenance FROM bn_coverage_periods WHERE company_code=%s AND employee_key=%s ORDER BY start_date DESC",
        (company, employee_key),
    )
    coverage = [dict(r) for r in cur.fetchall()]
    return {
        "ok": True,
        "employee_key": employee_key,
        "enrollments": enrollments,
        "coverage": coverage,
        "states_not_conflated": True,
        "hr_admin_exposed": False,
    }


def manager_benefits_status_view(
    cur: Any, *, company_code: str, manager_scope_employee_keys: list[str]
) -> dict[str, Any]:
    """Fail-closed: status only; no plan/member/private election detail unless policy allows (default false)."""
    gate = runtime_gate_for_company(company_code)
    if not gate.get("ok"):
        return gate
    company = gate["company_code"]
    if not module_enabled_for_company(cur, company):
        return {"ok": False, "error": "benefits_disabled_for_company"}
    settings = _settings(cur, company)
    if settings.get("manager_sees_private_detail"):
        return {"ok": False, "error": "manager_private_detail_requires_explicit_ops_surface", "fail_closed": True}
    if not manager_scope_employee_keys:
        return {"ok": True, "statuses": [], "scope_empty": True}
    cur.execute(
        """
        SELECT employee_key, status,
               CASE WHEN status IN ('enrollment_open','pending_evidence','pending_approval') THEN true ELSE false END AS action_required,
               CASE WHEN status IN ('enrollment_open','pending_evidence') THEN true ELSE false END AS enrollment_incomplete
          FROM bn_enrollments
         WHERE company_code=%s AND employee_key = ANY(%s)
        """,
        (company, list(manager_scope_employee_keys)),
    )
    statuses = [dict(r) for r in cur.fetchall()]
    return {
        "ok": True,
        "statuses": statuses,
        "private_detail_included": False,
        "plan_member_ids_exposed": False,
        "fail_closed": True,
        "uses_canonical_manager_scope": True,
    }


def assistant_query_benefits(
    cur: Any, *, company_code: str, actor: str, question_kind: str, employee_key: str | None = None
) -> dict[str, Any]:
    _ = actor
    if question_kind == "my_coverage" and employee_key:
        view = employee_benefits_view(cur, company_code=company_code, employee_key=employee_key)
        return {"ok": True, "mutations": False, "coverage": view.get("coverage"), "enrollments": view.get("enrollments")}
    if question_kind == "missing_documents" and employee_key:
        gate = runtime_gate_for_company(company_code)
        if not gate.get("ok"):
            return gate
        cur.execute(
            """
            SELECT e.document_type, e.status, e.enrollment_id
              FROM bn_evidence_requests e
              JOIN bn_enrollments n ON n.enrollment_id=e.enrollment_id
             WHERE e.company_code=%s AND n.employee_key=%s AND e.status='required'
            """,
            (gate["company_code"], employee_key),
        )
        return {"ok": True, "mutations": False, "missing": [dict(r) for r in cur.fetchall()]}
    if question_kind in {"enroll", "waive", "approve_coverage", "change_contribution", "claim_insurer_active"}:
        return {"ok": False, "error": "mutation_forbidden", "mutations": False}
    return {"ok": False, "error": "unsupported_or_forbidden", "mutations": False}


def _notify_dedupe(cur: Any, *, company: str, key: str) -> dict[str, Any]:
    dedupe_key = f"{company}:{key}"
    sp = f"bn_nd_{uuid.uuid4().hex[:12]}"
    cur.execute(f"SAVEPOINT {sp}")
    try:
        cur.execute(
            "INSERT INTO bn_notification_dedupe (dedupe_key, company_code) VALUES (%s,%s)",
            (dedupe_key, company),
        )
        cur.execute(f"RELEASE SAVEPOINT {sp}")
        return {"sent": True, "deduped": False}
    except Exception:
        cur.execute(f"ROLLBACK TO SAVEPOINT {sp}")
        cur.execute(f"RELEASE SAVEPOINT {sp}")
        return {"sent": False, "deduped": True}


def claims_engine_absent_check() -> dict[str, Any]:
    # Avoid embedding the exact DDL needle in this function (self-false-positive).
    src = open(__file__, encoding="utf-8").read().lower()
    needle_a = "create table if not exists " + "bn_claim"
    needle_b = "create table if not exists " + "benefit_claim"
    has_ddl = needle_a in src or needle_b in src
    return {
        "ok": True,
        "claims_adjudication_out": True,
        "has_claim_table_ddl": has_ddl,
        "no_claim_tables_in_c3": not has_ddl,
    }
