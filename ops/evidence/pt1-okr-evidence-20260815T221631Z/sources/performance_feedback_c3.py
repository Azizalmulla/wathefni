#!/usr/bin/env python3
"""Wave 4 C3 — Check-ins + Competencies + Durable Development (company-scoped).

Owner-approved under WAVE4_PERFORMANCE_TALENT_CHARTER (2026-08-12) §0.8.9 + W4.4–W4.5/W4.8.

Authorities:
  - check_in: continuous performance conversations (canonical; not review comments)
  - competency library: versioned company SoT (independent of pre-hire Assessment)
  - competency assessment: self / manager / other layers (never silently → overall rating)
  - development_plan / development_action: durable beyond review cycles
  - optional hr_tasks: explicit completion contract with development_action as SoT

Does NOT:
  - auto-mutate goal progress or ratings from check-in text
  - overload Assessment frameworks without explicit versioned mapping
  - build L&D, Talent potential/HiPo/9-box/succession
  - require review cycles, goals, Talent, or Learning

Gates (fail-closed):
  1) WATHEFNI_PERFORMANCE_FEEDBACK_C3 must be on
  2) company in WATHEFNI_PERFORMANCE_FEEDBACK_COMPANIES (empty = nobody)
  3) company entitlement in performance_feedback_c3_company_settings
"""
from __future__ import annotations

import json
import os
import uuid
from datetime import date, datetime
from typing import Any

PHASE = "performance_feedback_c3"
CONTRACT_VERSION = "performance_feedback_c3_v1"
PASS_STAMP = "PERFORMANCE_FEEDBACK_COMPETENCIES_FULL_PASS"
COMMERCIAL_MODULE_KEY = "performance"
_ON = {"1", "true", "yes", "on"}

CHECK_IN_STATES = ("scheduled", "open", "submitted", "acknowledged", "completed", "cancelled")
CHECK_IN_KINDS = ("scheduled", "ad_hoc")
VISIBILITY = ("employee_manager", "manager_hr", "hr_only", "shared_team")
COMPETENCY_KINDS = ("core", "role_specific")
ASSESSMENT_ROLES = ("self", "manager", "other")
ASSESSMENT_STATES = ("draft", "submitted", "acknowledged", "cancelled")
DEV_PLAN_STATES = ("draft", "active", "completed", "cancelled")
DEV_ACTION_STATES = ("proposed", "accepted", "in_progress", "done", "cancelled")
DEV_SOURCES = ("review", "check_in", "competency_gap", "manual")
TASK_SYNC_MODES = ("action_is_sot", "task_mirrors_action")

STATUS_LABELS = {
    "scheduled": {"en": "Scheduled", "ar": "مجدول"},
    "open": {"en": "Open", "ar": "مفتوح"},
    "submitted": {"en": "Submitted", "ar": "مُقدَّم"},
    "acknowledged": {"en": "Acknowledged", "ar": "مُقرّ"},
    "completed": {"en": "Completed", "ar": "مكتمل"},
    "cancelled": {"en": "Cancelled", "ar": "ملغى"},
    "ad_hoc": {"en": "Ad-hoc", "ar": "عَرَضي"},
    "draft": {"en": "Draft", "ar": "مسودة"},
    "active": {"en": "Active", "ar": "نشط"},
    "proposed": {"en": "Proposed", "ar": "مقترح"},
    "accepted": {"en": "Accepted", "ar": "مقبول"},
    "in_progress": {"en": "In progress", "ar": "قيد التنفيذ"},
    "done": {"en": "Done", "ar": "منجز"},
    "self": {"en": "Self assessment", "ar": "تقييم ذاتي"},
    "manager": {"en": "Manager assessment", "ar": "تقييم المدير"},
    "other": {"en": "Other assessment", "ar": "تقييم آخر"},
    "core": {"en": "Core competency", "ar": "كفاءة أساسية"},
    "role_specific": {"en": "Role-specific", "ar": "خاصة بالدور"},
    "deprecated": {"en": "Deprecated", "ar": "مهجور"},
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


def performance_feedback_c3_runtime_on() -> bool:
    return _env_on("WATHEFNI_PERFORMANCE_FEEDBACK_C3", "off")


def performance_feedback_company_allowlist() -> set[str]:
    raw = str(os.environ.get("WATHEFNI_PERFORMANCE_FEEDBACK_COMPANIES") or "").strip()
    if not raw:
        return set()
    return {p.strip().upper() for p in raw.split(",") if p.strip()}


def honesty_payload(*, company_code: str | None = None) -> dict[str, Any]:
    return {
        "phase": PHASE,
        "contract_version": CONTRACT_VERSION,
        "pass_stamp": PASS_STAMP,
        "commercial_module_key": COMMERCIAL_MODULE_KEY,
        "assistant_mutations": False,
        "check_ins_are_canonical_not_review_comments": True,
        "check_ins_work_without_review_cycles": True,
        "check_ins_work_without_goals": True,
        "check_ins_work_without_talent": True,
        "check_in_does_not_auto_mutate_goal_progress": True,
        "check_in_does_not_auto_mutate_ratings": True,
        "completed_check_ins_immutable_amend_via_audit": True,
        "competency_library_versioned": True,
        "competency_independent_of_pre_hire_assessment": True,
        "assessment_framework_import_requires_explicit_mapping": True,
        "competency_scores_do_not_become_overall_ratings": True,
        "self_manager_other_assessment_layers_separate": True,
        "development_durable_beyond_review_cycles": True,
        "closing_review_does_not_bury_development": True,
        "development_works_without_talent": True,
        "development_works_without_learning": True,
        "learning_not_built_in_c3": True,
        "talent_potential_hipo_9box_succession_out": True,
        "hr_tasks_optional_with_explicit_completion_contract": True,
        "development_action_is_status_sot_when_task_linked": True,
        "goals_c1_independent": True,
        "reviews_c2_independent": True,
        "company_code": company_code_norm(company_code) if company_code else None,
    }


def rollback_guidance() -> dict[str, Any]:
    return {
        "phase": PHASE,
        "preserves_history": True,
        "steps": [
            "WATHEFNI_PERFORMANCE_FEEDBACK_C3=off",
            "Clear WATHEFNI_PERFORMANCE_FEEDBACK_COMPANIES",
            "WATHEFNI_PERFORMANCE_KILL=on (optional immediate block)",
            "Disable company Setup entitlement (preserves check-in/competency/development history)",
        ],
    }


def runtime_gate_for_company(company_code: str | None) -> dict[str, Any]:
    company = company_code_norm(company_code)
    if not company:
        return {"ok": False, "enabled": False, "error": "company_required", "phase": PHASE}
    if _env_on("WATHEFNI_PERFORMANCE_KILL", "off"):
        return {
            "ok": False,
            "enabled": False,
            "error": "performance_kill_switch",
            "gate": "kill",
            "phase": PHASE,
        }
    if not performance_feedback_c3_runtime_on():
        return {
            "ok": False,
            "enabled": False,
            "error": "performance_feedback_c3_off",
            "gate": "runtime_flag",
            "phase": PHASE,
        }
    allow = performance_feedback_company_allowlist()
    if company not in allow:
        try:
            import capability_readiness as _cr

            entitled = _cr.performance_runtime_allowlist_admits(company, allow)
        except Exception:
            entitled = False
        if not entitled:
            return {
                "ok": False,
                "enabled": False,
                "error": "performance_feedback_company_not_allowlisted",
                "gate": "company_allowlist",
                "phase": PHASE,
                "company_code": company,
                "message": "Performance-feedback allowlist empty — fail closed (nobody).",
            }
    return {"ok": True, "enabled": True, "company_code": company, "phase": PHASE}


def ensure_performance_feedback_c3_schema(cur: Any, *, force: bool = False) -> None:
    _ = force
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS performance_feedback_c3_company_settings (
          company_code text PRIMARY KEY,
          enabled boolean NOT NULL DEFAULT false,
          check_ins_enabled boolean NOT NULL DEFAULT true,
          competencies_enabled boolean NOT NULL DEFAULT true,
          competency_assessments_enabled boolean NOT NULL DEFAULT true,
          development_enabled boolean NOT NULL DEFAULT true,
          hr_tasks_integration_enabled boolean NOT NULL DEFAULT false,
          require_reviews boolean NOT NULL DEFAULT false,
          require_goals boolean NOT NULL DEFAULT false,
          require_talent boolean NOT NULL DEFAULT false,
          require_learning boolean NOT NULL DEFAULT false,
          sensitive_notes_hr_only boolean NOT NULL DEFAULT true,
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
        CREATE TABLE IF NOT EXISTS perf_check_ins (
          check_in_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
          company_code text NOT NULL,
          kind text NOT NULL DEFAULT 'ad_hoc',
          status text NOT NULL DEFAULT 'open',
          employee_key text NOT NULL,
          employee_phone text,
          manager_employee_key text,
          manager_phone text,
          scheduled_for date,
          next_check_in_date date,
          talking_points jsonb NOT NULL DEFAULT '[]'::jsonb,
          notes_shared text,
          notes_sensitive text,
          visibility text NOT NULL DEFAULT 'employee_manager',
          linked_subject_type text,
          linked_subject_id text,
          progress_discussion text,
          evidence_notes text,
          completed_at timestamptz,
          completed_by_phone text,
          row_version int NOT NULL DEFAULT 1,
          created_by_phone text,
          created_at timestamptz NOT NULL DEFAULT now(),
          updated_at timestamptz NOT NULL DEFAULT now(),
          metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
          CONSTRAINT perf_checkin_kind_chk CHECK (kind IN ('scheduled','ad_hoc')),
          CONSTRAINT perf_checkin_status_chk CHECK (status IN (
            'scheduled','open','submitted','acknowledged','completed','cancelled'
          )),
          CONSTRAINT perf_checkin_vis_chk CHECK (visibility IN (
            'employee_manager','manager_hr','hr_only','shared_team'
          ))
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS perf_check_in_commitments (
          commitment_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
          company_code text NOT NULL,
          check_in_id uuid NOT NULL REFERENCES perf_check_ins(check_in_id),
          title_en text NOT NULL,
          title_ar text,
          owner_employee_key text,
          due_date date,
          status text NOT NULL DEFAULT 'open',
          created_at timestamptz NOT NULL DEFAULT now(),
          updated_at timestamptz NOT NULL DEFAULT now(),
          CONSTRAINT perf_commit_status_chk CHECK (status IN ('open','done','cancelled'))
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS perf_check_in_amendments (
          amendment_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
          company_code text NOT NULL,
          check_in_id uuid NOT NULL REFERENCES perf_check_ins(check_in_id),
          field_name text NOT NULL,
          before_value jsonb,
          after_value jsonb,
          reason text NOT NULL,
          actor_phone text,
          created_at timestamptz NOT NULL DEFAULT now()
        )
        """
    )
    # C3 competency authority — independent of C2 cycle snapshot stub and pre-hire Assessment.
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS perf_c3_competency_frameworks (
          framework_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
          company_code text NOT NULL,
          name_en text NOT NULL,
          name_ar text,
          version int NOT NULL DEFAULT 1,
          status text NOT NULL DEFAULT 'active',
          proficiency_levels jsonb NOT NULL DEFAULT '[]'::jsonb,
          created_by_phone text,
          created_at timestamptz NOT NULL DEFAULT now(),
          updated_at timestamptz NOT NULL DEFAULT now(),
          metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
          CONSTRAINT perf_c3_fw_status_chk CHECK (status IN ('active','deprecated'))
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS perf_c3_competencies (
          competency_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
          company_code text NOT NULL,
          framework_id uuid NOT NULL REFERENCES perf_c3_competency_frameworks(framework_id),
          framework_version int NOT NULL,
          code text NOT NULL,
          name_en text NOT NULL,
          name_ar text,
          description_en text,
          description_ar text,
          behavioral_indicators jsonb NOT NULL DEFAULT '[]'::jsonb,
          competency_kind text NOT NULL DEFAULT 'core',
          job_families jsonb NOT NULL DEFAULT '[]'::jsonb,
          role_keys jsonb NOT NULL DEFAULT '[]'::jsonb,
          status text NOT NULL DEFAULT 'active',
          created_by_phone text,
          created_at timestamptz NOT NULL DEFAULT now(),
          updated_at timestamptz NOT NULL DEFAULT now(),
          metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
          CONSTRAINT perf_c3_comp_kind_chk CHECK (competency_kind IN ('core','role_specific')),
          CONSTRAINT perf_c3_comp_status_chk CHECK (status IN ('active','deprecated')),
          UNIQUE (framework_id, code, framework_version)
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS perf_assessment_framework_mappings (
          mapping_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
          company_code text NOT NULL,
          source_system text NOT NULL DEFAULT 'assessment',
          source_framework_id text NOT NULL,
          source_framework_version text NOT NULL,
          target_framework_id uuid NOT NULL REFERENCES perf_c3_competency_frameworks(framework_id),
          target_framework_version int NOT NULL,
          mapping_contract_version text NOT NULL DEFAULT 'assessment_map_v1',
          item_map jsonb NOT NULL DEFAULT '[]'::jsonb,
          status text NOT NULL DEFAULT 'active',
          created_by_phone text,
          reason text NOT NULL,
          created_at timestamptz NOT NULL DEFAULT now(),
          CONSTRAINT perf_map_status_chk CHECK (status IN ('active','deprecated'))
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS perf_competency_assessments (
          assessment_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
          company_code text NOT NULL,
          employee_key text NOT NULL,
          framework_id uuid NOT NULL,
          framework_version int NOT NULL,
          competency_id uuid NOT NULL,
          assessor_role text NOT NULL,
          assessor_phone text,
          assessor_employee_key text,
          score numeric,
          proficiency_level text,
          evidence_notes text,
          status text NOT NULL DEFAULT 'draft',
          check_in_id uuid,
          review_id uuid,
          submitted_at timestamptz,
          row_version int NOT NULL DEFAULT 1,
          created_at timestamptz NOT NULL DEFAULT now(),
          updated_at timestamptz NOT NULL DEFAULT now(),
          metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
          CONSTRAINT perf_cass_role_chk CHECK (assessor_role IN ('self','manager','other')),
          CONSTRAINT perf_cass_status_chk CHECK (status IN (
            'draft','submitted','acknowledged','cancelled'
          ))
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS perf_development_plans (
          plan_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
          company_code text NOT NULL,
          employee_key text NOT NULL,
          title_en text NOT NULL,
          title_ar text,
          status text NOT NULL DEFAULT 'draft',
          strengths jsonb NOT NULL DEFAULT '[]'::jsonb,
          development_areas jsonb NOT NULL DEFAULT '[]'::jsonb,
          owner_employee_key text,
          row_version int NOT NULL DEFAULT 1,
          created_by_phone text,
          created_at timestamptz NOT NULL DEFAULT now(),
          updated_at timestamptz NOT NULL DEFAULT now(),
          metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
          CONSTRAINT perf_dplan_status_chk CHECK (status IN (
            'draft','active','completed','cancelled'
          ))
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS perf_development_actions (
          action_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
          company_code text NOT NULL,
          plan_id uuid NOT NULL REFERENCES perf_development_plans(plan_id),
          title_en text NOT NULL,
          title_ar text,
          description_en text,
          description_ar text,
          status text NOT NULL DEFAULT 'proposed',
          owner_employee_key text,
          due_date date,
          progress_notes text,
          evidence_notes text,
          source_type text NOT NULL DEFAULT 'manual',
          source_id text,
          hr_task_id uuid,
          task_sync_mode text NOT NULL DEFAULT 'action_is_sot',
          row_version int NOT NULL DEFAULT 1,
          created_by_phone text,
          created_at timestamptz NOT NULL DEFAULT now(),
          updated_at timestamptz NOT NULL DEFAULT now(),
          completed_at timestamptz,
          metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
          CONSTRAINT perf_dact_status_chk CHECK (status IN (
            'proposed','accepted','in_progress','done','cancelled'
          )),
          CONSTRAINT perf_dact_source_chk CHECK (source_type IN (
            'review','check_in','competency_gap','manual'
          )),
          CONSTRAINT perf_dact_sync_chk CHECK (task_sync_mode IN (
            'action_is_sot','task_mirrors_action'
          ))
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS performance_feedback_c3_audit (
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
    for idx_sql in (
        "CREATE INDEX IF NOT EXISTS perf_checkins_company_idx ON perf_check_ins(company_code, status)",
        "CREATE INDEX IF NOT EXISTS perf_checkins_emp_idx ON perf_check_ins(company_code, employee_key)",
        "CREATE INDEX IF NOT EXISTS perf_c3_comp_fw_idx ON perf_c3_competencies(framework_id, status)",
        "CREATE INDEX IF NOT EXISTS perf_cass_emp_idx ON perf_competency_assessments(company_code, employee_key)",
        "CREATE INDEX IF NOT EXISTS perf_dplan_emp_idx ON perf_development_plans(company_code, employee_key)",
        "CREATE INDEX IF NOT EXISTS perf_dact_plan_idx ON perf_development_actions(plan_id, status)",
    ):
        cur.execute(idx_sql)


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
        INSERT INTO performance_feedback_c3_audit (
          company_code, action, actor_phone, reason, subject_type, subject_id, payload
        ) VALUES (%s,%s,%s,%s,%s,%s,%s::jsonb)
        """,
        (
            company_code_norm(company_code),
            action,
            _digits(actor_phone) if actor_phone else None,
            (str(reason).strip()[:500] if reason else None),
            subject_type,
            str(subject_id) if subject_id else None,
            json.dumps(payload or {}, default=str),
        ),
    )


def get_company_settings(cur: Any, company_code: str | None) -> dict[str, Any] | None:
    ensure_performance_feedback_c3_schema(cur)
    cur.execute(
        "SELECT * FROM performance_feedback_c3_company_settings WHERE company_code=%s",
        (company_code_norm(company_code),),
    )
    row = cur.fetchone()
    return dict(row) if row else None


def _entitled(cur: Any, company_code: str, *, feature: str | None = None) -> dict[str, Any]:
    gate = runtime_gate_for_company(company_code)
    if not gate.get("ok"):
        return gate
    settings = get_company_settings(cur, company_code)
    if not settings or not settings.get("enabled"):
        return {
            "ok": False,
            "error": "performance_feedback_company_not_enabled",
            "gate": "company_settings",
            "phase": PHASE,
        }
    if feature == "check_ins" and not settings.get("check_ins_enabled"):
        return {"ok": False, "error": "check_ins_disabled", "gate": "feature"}
    if feature == "competencies" and not settings.get("competencies_enabled"):
        return {"ok": False, "error": "competencies_disabled", "gate": "feature"}
    if feature == "assessments" and not settings.get("competency_assessments_enabled"):
        return {"ok": False, "error": "competency_assessments_disabled", "gate": "feature"}
    if feature == "development" and not settings.get("development_enabled"):
        return {"ok": False, "error": "development_disabled", "gate": "feature"}
    return {"ok": True, "settings": settings, "company_code": company_code_norm(company_code)}


def enable_company_performance_feedback(
    cur: Any,
    *,
    company_code: str,
    actor_phone: str,
    reason: str,
    check_ins_enabled: bool = True,
    competencies_enabled: bool = True,
    competency_assessments_enabled: bool = True,
    development_enabled: bool = True,
    hr_tasks_integration_enabled: bool = False,
    sensitive_notes_hr_only: bool = True,
) -> dict[str, Any]:
    if not str(reason or "").strip():
        return {"ok": False, "error": "audit_reason_required"}
    gate = runtime_gate_for_company(company_code)
    if not gate.get("ok"):
        return gate
    company = company_code_norm(company_code)
    ensure_performance_feedback_c3_schema(cur)
    cur.execute(
        """
        INSERT INTO performance_feedback_c3_company_settings (
          company_code, enabled, check_ins_enabled, competencies_enabled,
          competency_assessments_enabled, development_enabled, hr_tasks_integration_enabled,
          require_reviews, require_goals, require_talent, require_learning,
          sensitive_notes_hr_only, enabled_by_phone, enabled_reason, enabled_at,
          updated_by_phone, updated_at, disabled_at
        ) VALUES (%s,true,%s,%s,%s,%s,%s,false,false,false,false,%s,%s,%s,now(),%s,now(),NULL)
        ON CONFLICT (company_code) DO UPDATE SET
          enabled=true,
          check_ins_enabled=EXCLUDED.check_ins_enabled,
          competencies_enabled=EXCLUDED.competencies_enabled,
          competency_assessments_enabled=EXCLUDED.competency_assessments_enabled,
          development_enabled=EXCLUDED.development_enabled,
          hr_tasks_integration_enabled=EXCLUDED.hr_tasks_integration_enabled,
          require_reviews=false,
          require_goals=false,
          require_talent=false,
          require_learning=false,
          sensitive_notes_hr_only=EXCLUDED.sensitive_notes_hr_only,
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
            bool(check_ins_enabled),
            bool(competencies_enabled),
            bool(competency_assessments_enabled),
            bool(development_enabled),
            bool(hr_tasks_integration_enabled),
            bool(sensitive_notes_hr_only),
            _digits(actor_phone),
            str(reason).strip()[:500],
            _digits(actor_phone),
        ),
    )
    row = dict(cur.fetchone())
    _audit(
        cur,
        company_code=company,
        action="company_enabled",
        actor_phone=actor_phone,
        reason=reason,
        subject_type="company",
        subject_id=company,
        payload={"settings": {k: row.get(k) for k in (
            "check_ins_enabled", "competencies_enabled", "development_enabled",
            "hr_tasks_integration_enabled",
        )}},
    )
    return {"ok": True, "settings": row}


def disable_company_performance_feedback(
    cur: Any, *, company_code: str, actor_phone: str, reason: str
) -> dict[str, Any]:
    if not str(reason or "").strip():
        return {"ok": False, "error": "audit_reason_required"}
    company = company_code_norm(company_code)
    ensure_performance_feedback_c3_schema(cur)
    cur.execute(
        """
        UPDATE performance_feedback_c3_company_settings
        SET enabled=false, disabled_at=now(), updated_by_phone=%s, updated_at=now()
        WHERE company_code=%s
        RETURNING *
        """,
        (_digits(actor_phone), company),
    )
    row = cur.fetchone()
    if not row:
        return {"ok": False, "error": "company_settings_not_found"}
    _audit(
        cur,
        company_code=company,
        action="company_disabled",
        actor_phone=actor_phone,
        reason=reason,
        subject_type="company",
        subject_id=company,
        payload={"preserves_history": True},
    )
    return {"ok": True, "settings": dict(row), "preserves_history": True}


# ── Visibility / scope helpers ──────────────────────────────────────────────


def _actor_role(
    *,
    actor_phone: str,
    employee_phone: str | None,
    manager_phone: str | None,
    hr_phones: set[str] | None = None,
) -> str:
    p = _digits(actor_phone)
    if hr_phones and p in {_digits(x) for x in hr_phones}:
        return "hr"
    if employee_phone and p == _digits(employee_phone):
        return "employee"
    if manager_phone and p == _digits(manager_phone):
        return "manager"
    return "other"


def can_view_check_in(
    check_in: dict[str, Any],
    *,
    actor_phone: str,
    hr_phones: set[str] | None = None,
    allow_sensitive: bool = False,
) -> dict[str, Any]:
    role = _actor_role(
        actor_phone=actor_phone,
        employee_phone=check_in.get("employee_phone"),
        manager_phone=check_in.get("manager_phone"),
        hr_phones=hr_phones,
    )
    vis = str(check_in.get("visibility") or "employee_manager")
    allowed = False
    if role == "hr":
        allowed = True
    elif vis == "employee_manager" and role in ("employee", "manager"):
        allowed = True
    elif vis == "manager_hr" and role in ("manager", "hr"):
        allowed = True
    elif vis == "hr_only" and role == "hr":
        allowed = True
    elif vis == "shared_team" and role in ("employee", "manager", "hr"):
        allowed = True
    if not allowed:
        return {"ok": False, "error": "check_in_visibility_denied", "role": role}
    out = dict(check_in)
    if out.get("notes_sensitive") and not (
        role == "hr" or (allow_sensitive and role == "manager")
    ):
        out["notes_sensitive"] = None
        out["sensitive_redacted"] = True
    return {"ok": True, "check_in": out, "role": role}


def manager_in_scope(
    *,
    actor_phone: str,
    manager_phone: str | None,
    hr_phones: set[str] | None = None,
) -> bool:
    p = _digits(actor_phone)
    if hr_phones and p in {_digits(x) for x in hr_phones}:
        return True
    return bool(manager_phone) and p == _digits(manager_phone)


# ── Check-ins ───────────────────────────────────────────────────────────────


def create_check_in(
    cur: Any,
    *,
    company_code: str,
    actor_phone: str,
    employee_key: str,
    employee_phone: str | None = None,
    manager_employee_key: str | None = None,
    manager_phone: str | None = None,
    kind: str = "ad_hoc",
    scheduled_for: date | None = None,
    talking_points: list[Any] | None = None,
    notes_shared: str | None = None,
    notes_sensitive: str | None = None,
    visibility: str = "employee_manager",
    linked_subject_type: str | None = None,
    linked_subject_id: str | None = None,
    progress_discussion: str | None = None,
    evidence_notes: str | None = None,
    next_check_in_date: date | None = None,
    reason: str = "create check-in",
) -> dict[str, Any]:
    if not str(reason or "").strip():
        return {"ok": False, "error": "audit_reason_required"}
    ent = _entitled(cur, company_code, feature="check_ins")
    if not ent.get("ok"):
        return ent
    company = ent["company_code"]
    k = str(kind or "ad_hoc").strip().lower()
    if k not in CHECK_IN_KINDS:
        return {"ok": False, "error": "invalid_check_in_kind", "allowed": list(CHECK_IN_KINDS)}
    vis = str(visibility or "employee_manager").strip().lower()
    if vis not in VISIBILITY:
        return {"ok": False, "error": "invalid_visibility", "allowed": list(VISIBILITY)}
    if linked_subject_type and linked_subject_type not in (
        "objective", "key_result", "kpi_goal", "goal", "competency", None
    ):
        return {"ok": False, "error": "invalid_linked_subject_type"}
    status = "scheduled" if k == "scheduled" and scheduled_for else "open"
    cur.execute(
        """
        INSERT INTO perf_check_ins (
          company_code, kind, status, employee_key, employee_phone,
          manager_employee_key, manager_phone, scheduled_for, next_check_in_date,
          talking_points, notes_shared, notes_sensitive, visibility,
          linked_subject_type, linked_subject_id, progress_discussion, evidence_notes,
          created_by_phone
        ) VALUES (
          %s,%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb,%s,%s,%s,%s,%s,%s,%s,%s
        ) RETURNING *
        """,
        (
            company, k, status, str(employee_key), _digits(employee_phone) if employee_phone else None,
            manager_employee_key, _digits(manager_phone) if manager_phone else None,
            scheduled_for, next_check_in_date,
            json.dumps(talking_points or [], default=str),
            notes_shared, notes_sensitive, vis,
            linked_subject_type, str(linked_subject_id) if linked_subject_id else None,
            progress_discussion, evidence_notes, _digits(actor_phone),
        ),
    )
    row = dict(cur.fetchone())
    _audit(
        cur, company_code=company, action="check_in_created", actor_phone=actor_phone,
        reason=reason, subject_type="check_in", subject_id=str(row["check_in_id"]),
        payload={
            "kind": k, "linked_subject_type": linked_subject_type,
            "does_not_mutate_goal_progress": True,
            "does_not_mutate_ratings": True,
        },
    )
    return {"ok": True, "check_in": row, "goal_progress_mutated": False, "rating_mutated": False}


def add_check_in_commitment(
    cur: Any,
    *,
    company_code: str,
    check_in_id: str,
    actor_phone: str,
    title_en: str,
    title_ar: str | None = None,
    owner_employee_key: str | None = None,
    due_date: date | None = None,
) -> dict[str, Any]:
    ent = _entitled(cur, company_code, feature="check_ins")
    if not ent.get("ok"):
        return ent
    company = ent["company_code"]
    ci = _get_check_in(cur, company, check_in_id)
    if not ci:
        return {"ok": False, "error": "check_in_not_found"}
    if ci["status"] in ("completed", "cancelled"):
        return {"ok": False, "error": "check_in_immutable", "status": ci["status"]}
    cur.execute(
        """
        INSERT INTO perf_check_in_commitments (
          company_code, check_in_id, title_en, title_ar, owner_employee_key, due_date
        ) VALUES (%s,%s,%s,%s,%s,%s) RETURNING *
        """,
        (company, check_in_id, title_en, title_ar, owner_employee_key, due_date),
    )
    row = dict(cur.fetchone())
    _audit(
        cur, company_code=company, action="check_in_commitment_added",
        actor_phone=actor_phone, subject_type="check_in", subject_id=str(check_in_id),
        payload={"commitment_id": str(row["commitment_id"])},
    )
    return {"ok": True, "commitment": row}


def update_check_in(
    cur: Any,
    *,
    company_code: str,
    check_in_id: str,
    actor_phone: str,
    expected_row_version: int,
    notes_shared: str | None = None,
    notes_sensitive: str | None = None,
    talking_points: list[Any] | None = None,
    progress_discussion: str | None = None,
    evidence_notes: str | None = None,
    next_check_in_date: date | None = None,
    reason: str = "update check-in",
) -> dict[str, Any]:
    ent = _entitled(cur, company_code, feature="check_ins")
    if not ent.get("ok"):
        return ent
    company = ent["company_code"]
    ci = _get_check_in(cur, company, check_in_id)
    if not ci:
        return {"ok": False, "error": "check_in_not_found"}
    if ci["status"] in ("completed", "cancelled"):
        return {"ok": False, "error": "check_in_immutable_use_amend", "status": ci["status"]}
    if int(ci["row_version"]) != int(expected_row_version):
        return {
            "ok": False,
            "error": "stale_row_version",
            "expected": int(expected_row_version),
            "actual": int(ci["row_version"]),
        }
    cur.execute(
        """
        UPDATE perf_check_ins SET
          notes_shared=COALESCE(%s, notes_shared),
          notes_sensitive=COALESCE(%s, notes_sensitive),
          talking_points=COALESCE(%s::jsonb, talking_points),
          progress_discussion=COALESCE(%s, progress_discussion),
          evidence_notes=COALESCE(%s, evidence_notes),
          next_check_in_date=COALESCE(%s, next_check_in_date),
          row_version=row_version+1,
          updated_at=now()
        WHERE check_in_id=%s AND company_code=%s AND row_version=%s
        RETURNING *
        """,
        (
            notes_shared, notes_sensitive,
            json.dumps(talking_points, default=str) if talking_points is not None else None,
            progress_discussion, evidence_notes, next_check_in_date,
            check_in_id, company, expected_row_version,
        ),
    )
    row = cur.fetchone()
    if not row:
        return {"ok": False, "error": "stale_row_version"}
    _audit(
        cur, company_code=company, action="check_in_updated", actor_phone=actor_phone,
        reason=reason, subject_type="check_in", subject_id=str(check_in_id),
        payload={"goal_progress_mutated": False},
    )
    return {"ok": True, "check_in": dict(row), "goal_progress_mutated": False}


def complete_check_in(
    cur: Any,
    *,
    company_code: str,
    check_in_id: str,
    actor_phone: str,
    expected_row_version: int,
    reason: str = "complete check-in",
) -> dict[str, Any]:
    ent = _entitled(cur, company_code, feature="check_ins")
    if not ent.get("ok"):
        return ent
    company = ent["company_code"]
    ci = _get_check_in(cur, company, check_in_id)
    if not ci:
        return {"ok": False, "error": "check_in_not_found"}
    if ci["status"] in ("completed", "cancelled"):
        return {"ok": False, "error": "check_in_already_terminal", "status": ci["status"]}
    if int(ci["row_version"]) != int(expected_row_version):
        return {"ok": False, "error": "stale_row_version"}
    cur.execute(
        """
        UPDATE perf_check_ins SET
          status='completed', completed_at=now(), completed_by_phone=%s,
          row_version=row_version+1, updated_at=now()
        WHERE check_in_id=%s AND company_code=%s AND row_version=%s
        RETURNING *
        """,
        (_digits(actor_phone), check_in_id, company, expected_row_version),
    )
    row = cur.fetchone()
    if not row:
        return {"ok": False, "error": "stale_row_version"}
    _audit(
        cur, company_code=company, action="check_in_completed", actor_phone=actor_phone,
        reason=reason, subject_type="check_in", subject_id=str(check_in_id),
        payload={"immutable_after": True},
    )
    return {"ok": True, "check_in": dict(row)}


def amend_completed_check_in(
    cur: Any,
    *,
    company_code: str,
    check_in_id: str,
    actor_phone: str,
    field_name: str,
    after_value: Any,
    reason: str,
) -> dict[str, Any]:
    """Amendment path for completed check-ins — never silent overwrite."""
    if not str(reason or "").strip():
        return {"ok": False, "error": "audit_reason_required"}
    ent = _entitled(cur, company_code, feature="check_ins")
    if not ent.get("ok"):
        return ent
    company = ent["company_code"]
    ci = _get_check_in(cur, company, check_in_id)
    if not ci:
        return {"ok": False, "error": "check_in_not_found"}
    if ci["status"] != "completed":
        return {"ok": False, "error": "amend_only_for_completed", "status": ci["status"]}
    allowed_fields = {
        "notes_shared", "notes_sensitive", "progress_discussion",
        "evidence_notes", "next_check_in_date", "talking_points",
    }
    if field_name not in allowed_fields:
        return {"ok": False, "error": "field_not_amendable", "allowed": sorted(allowed_fields)}
    before = ci.get(field_name)
    if field_name == "talking_points":
        cur.execute(
            """
            UPDATE perf_check_ins SET talking_points=%s::jsonb, updated_at=now()
            WHERE check_in_id=%s AND company_code=%s RETURNING *
            """,
            (json.dumps(after_value, default=str), check_in_id, company),
        )
    elif field_name == "next_check_in_date":
        cur.execute(
            f"""
            UPDATE perf_check_ins SET {field_name}=%s, updated_at=now()
            WHERE check_in_id=%s AND company_code=%s RETURNING *
            """,
            (after_value, check_in_id, company),
        )
    else:
        cur.execute(
            f"""
            UPDATE perf_check_ins SET {field_name}=%s, updated_at=now()
            WHERE check_in_id=%s AND company_code=%s RETURNING *
            """,
            (after_value, check_in_id, company),
        )
    row = dict(cur.fetchone())
    cur.execute(
        """
        INSERT INTO perf_check_in_amendments (
          company_code, check_in_id, field_name, before_value, after_value, reason, actor_phone
        ) VALUES (%s,%s,%s,%s::jsonb,%s::jsonb,%s,%s)
        """,
        (
            company, check_in_id, field_name,
            json.dumps(before, default=str), json.dumps(after_value, default=str),
            str(reason).strip()[:500], _digits(actor_phone),
        ),
    )
    _audit(
        cur, company_code=company, action="check_in_amended", actor_phone=actor_phone,
        reason=reason, subject_type="check_in", subject_id=str(check_in_id),
        payload={"field_name": field_name},
    )
    return {"ok": True, "check_in": row, "amended_via_audit": True}


def _get_check_in(cur: Any, company: str, check_in_id: str) -> dict[str, Any] | None:
    cur.execute(
        "SELECT * FROM perf_check_ins WHERE company_code=%s AND check_in_id=%s",
        (company, check_in_id),
    )
    row = cur.fetchone()
    return dict(row) if row else None


def get_check_in(
    cur: Any, *, company_code: str, check_in_id: str
) -> dict[str, Any] | None:
    ensure_performance_feedback_c3_schema(cur)
    return _get_check_in(cur, company_code_norm(company_code), check_in_id)


# ── Competency library ──────────────────────────────────────────────────────


def create_competency_framework(
    cur: Any,
    *,
    company_code: str,
    actor_phone: str,
    name_en: str,
    name_ar: str | None = None,
    proficiency_levels: list[Any] | None = None,
    reason: str = "create competency framework",
) -> dict[str, Any]:
    if not str(reason or "").strip():
        return {"ok": False, "error": "audit_reason_required"}
    ent = _entitled(cur, company_code, feature="competencies")
    if not ent.get("ok"):
        return ent
    company = ent["company_code"]
    levels = proficiency_levels or [
        {"level": 1, "label_en": "Developing", "label_ar": "قيد التطوير"},
        {"level": 2, "label_en": "Proficient", "label_ar": "متمكن"},
        {"level": 3, "label_en": "Advanced", "label_ar": "متقدم"},
        {"level": 4, "label_en": "Expert", "label_ar": "خبير"},
    ]
    cur.execute(
        """
        INSERT INTO perf_c3_competency_frameworks (
          company_code, name_en, name_ar, version, proficiency_levels, created_by_phone
        ) VALUES (%s,%s,%s,1,%s::jsonb,%s) RETURNING *
        """,
        (company, name_en, name_ar, json.dumps(levels, default=str), _digits(actor_phone)),
    )
    row = dict(cur.fetchone())
    _audit(
        cur, company_code=company, action="competency_framework_created",
        actor_phone=actor_phone, reason=reason, subject_type="competency_framework",
        subject_id=str(row["framework_id"]),
        payload={"independent_of_assessment": True, "independent_of_c2_stub": True},
    )
    return {"ok": True, "framework": row}


def add_competency(
    cur: Any,
    *,
    company_code: str,
    framework_id: str,
    actor_phone: str,
    code: str,
    name_en: str,
    name_ar: str | None = None,
    description_en: str | None = None,
    description_ar: str | None = None,
    behavioral_indicators: list[Any] | None = None,
    competency_kind: str = "core",
    job_families: list[str] | None = None,
    role_keys: list[str] | None = None,
) -> dict[str, Any]:
    ent = _entitled(cur, company_code, feature="competencies")
    if not ent.get("ok"):
        return ent
    company = ent["company_code"]
    cur.execute(
        "SELECT * FROM perf_c3_competency_frameworks WHERE company_code=%s AND framework_id=%s",
        (company, framework_id),
    )
    fw = cur.fetchone()
    if not fw:
        return {"ok": False, "error": "framework_not_found"}
    fw = dict(fw)
    if fw["status"] != "active":
        return {"ok": False, "error": "framework_not_active", "status": fw["status"]}
    kind = str(competency_kind or "core").strip().lower()
    if kind not in COMPETENCY_KINDS:
        return {"ok": False, "error": "invalid_competency_kind", "allowed": list(COMPETENCY_KINDS)}
    cur.execute(
        """
        INSERT INTO perf_c3_competencies (
          company_code, framework_id, framework_version, code, name_en, name_ar,
          description_en, description_ar, behavioral_indicators, competency_kind,
          job_families, role_keys, created_by_phone
        ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb,%s,%s::jsonb,%s::jsonb,%s)
        RETURNING *
        """,
        (
            company, framework_id, int(fw["version"]), code, name_en, name_ar,
            description_en, description_ar,
            json.dumps(behavioral_indicators or [], default=str), kind,
            json.dumps(job_families or []), json.dumps(role_keys or []),
            _digits(actor_phone),
        ),
    )
    row = dict(cur.fetchone())
    _audit(
        cur, company_code=company, action="competency_added", actor_phone=actor_phone,
        subject_type="competency", subject_id=str(row["competency_id"]),
        payload={"framework_version": int(fw["version"]), "kind": kind},
    )
    return {"ok": True, "competency": row}


def publish_framework_version(
    cur: Any,
    *,
    company_code: str,
    framework_id: str,
    actor_phone: str,
    reason: str,
) -> dict[str, Any]:
    """Bump framework version; prior competencies remain readable at their frozen version."""
    if not str(reason or "").strip():
        return {"ok": False, "error": "audit_reason_required"}
    ent = _entitled(cur, company_code, feature="competencies")
    if not ent.get("ok"):
        return ent
    company = ent["company_code"]
    cur.execute(
        "SELECT * FROM perf_c3_competency_frameworks WHERE company_code=%s AND framework_id=%s",
        (company, framework_id),
    )
    fw = cur.fetchone()
    if not fw:
        return {"ok": False, "error": "framework_not_found"}
    fw = dict(fw)
    old_ver = int(fw["version"])
    new_ver = old_ver + 1
    # Copy active competencies to new version rows (historical rows keep old framework_version).
    cur.execute(
        """
        INSERT INTO perf_c3_competencies (
          company_code, framework_id, framework_version, code, name_en, name_ar,
          description_en, description_ar, behavioral_indicators, competency_kind,
          job_families, role_keys, status, created_by_phone, metadata
        )
        SELECT company_code, framework_id, %s, code, name_en, name_ar,
               description_en, description_ar, behavioral_indicators, competency_kind,
               job_families, role_keys, status, %s, metadata
        FROM perf_c3_competencies
        WHERE framework_id=%s AND framework_version=%s AND status='active'
        """,
        (new_ver, _digits(actor_phone), framework_id, old_ver),
    )
    cur.execute(
        """
        UPDATE perf_c3_competency_frameworks
        SET version=%s, updated_at=now()
        WHERE framework_id=%s AND company_code=%s
        RETURNING *
        """,
        (new_ver, framework_id, company),
    )
    row = dict(cur.fetchone())
    _audit(
        cur, company_code=company, action="competency_framework_versioned",
        actor_phone=actor_phone, reason=reason, subject_type="competency_framework",
        subject_id=str(framework_id),
        payload={"from_version": old_ver, "to_version": new_ver, "history_preserved": True},
    )
    return {"ok": True, "framework": row, "from_version": old_ver, "to_version": new_ver}


def deprecate_competency(
    cur: Any,
    *,
    company_code: str,
    competency_id: str,
    actor_phone: str,
    reason: str,
) -> dict[str, Any]:
    if not str(reason or "").strip():
        return {"ok": False, "error": "audit_reason_required"}
    ent = _entitled(cur, company_code, feature="competencies")
    if not ent.get("ok"):
        return ent
    company = ent["company_code"]
    cur.execute(
        """
        UPDATE perf_c3_competencies SET status='deprecated', updated_at=now()
        WHERE company_code=%s AND competency_id=%s
        RETURNING *
        """,
        (company, competency_id),
    )
    row = cur.fetchone()
    if not row:
        return {"ok": False, "error": "competency_not_found"}
    _audit(
        cur, company_code=company, action="competency_deprecated", actor_phone=actor_phone,
        reason=reason, subject_type="competency", subject_id=str(competency_id),
        payload={"historically_readable": True},
    )
    return {"ok": True, "competency": dict(row)}


def create_assessment_framework_mapping(
    cur: Any,
    *,
    company_code: str,
    actor_phone: str,
    source_framework_id: str,
    source_framework_version: str,
    target_framework_id: str,
    target_framework_version: int,
    item_map: list[Any],
    reason: str,
    source_system: str = "assessment",
) -> dict[str, Any]:
    """Explicit versioned mapping — never silent reuse of Assessment frameworks."""
    if not str(reason or "").strip():
        return {"ok": False, "error": "audit_reason_required"}
    if not item_map:
        return {"ok": False, "error": "item_map_required"}
    ent = _entitled(cur, company_code, feature="competencies")
    if not ent.get("ok"):
        return ent
    company = ent["company_code"]
    cur.execute(
        "SELECT 1 FROM perf_c3_competency_frameworks WHERE company_code=%s AND framework_id=%s",
        (company, target_framework_id),
    )
    if not cur.fetchone():
        return {"ok": False, "error": "target_framework_not_found"}
    cur.execute(
        """
        INSERT INTO perf_assessment_framework_mappings (
          company_code, source_system, source_framework_id, source_framework_version,
          target_framework_id, target_framework_version, item_map, created_by_phone, reason
        ) VALUES (%s,%s,%s,%s,%s,%s,%s::jsonb,%s,%s) RETURNING *
        """,
        (
            company, source_system, source_framework_id, source_framework_version,
            target_framework_id, int(target_framework_version),
            json.dumps(item_map, default=str), _digits(actor_phone), str(reason).strip()[:500],
        ),
    )
    row = dict(cur.fetchone())
    _audit(
        cur, company_code=company, action="assessment_framework_mapping_created",
        actor_phone=actor_phone, reason=reason, subject_type="assessment_mapping",
        subject_id=str(row["mapping_id"]),
        payload={"explicit_contract": True, "silent_reuse_forbidden": True},
    )
    return {"ok": True, "mapping": row}


# ── Competency assessments ──────────────────────────────────────────────────


def submit_competency_assessment(
    cur: Any,
    *,
    company_code: str,
    actor_phone: str,
    employee_key: str,
    framework_id: str,
    framework_version: int,
    competency_id: str,
    assessor_role: str,
    score: Any = None,
    proficiency_level: str | None = None,
    evidence_notes: str | None = None,
    assessor_employee_key: str | None = None,
    check_in_id: str | None = None,
    review_id: str | None = None,
    reason: str = "submit competency assessment",
) -> dict[str, Any]:
    if not str(reason or "").strip():
        return {"ok": False, "error": "audit_reason_required"}
    ent = _entitled(cur, company_code, feature="assessments")
    if not ent.get("ok"):
        return ent
    company = ent["company_code"]
    role = str(assessor_role or "").strip().lower()
    if role not in ASSESSMENT_ROLES:
        return {"ok": False, "error": "invalid_assessor_role", "allowed": list(ASSESSMENT_ROLES)}
    cur.execute(
        """
        SELECT * FROM perf_c3_competencies
        WHERE company_code=%s AND competency_id=%s
        """,
        (company, competency_id),
    )
    comp = cur.fetchone()
    if not comp:
        return {"ok": False, "error": "competency_not_found"}
    # Allow assessment against deprecated competencies for historical continuity when version matches.
    cur.execute(
        """
        INSERT INTO perf_competency_assessments (
          company_code, employee_key, framework_id, framework_version, competency_id,
          assessor_role, assessor_phone, assessor_employee_key, score, proficiency_level,
          evidence_notes, status, check_in_id, review_id, submitted_at
        ) VALUES (
          %s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'submitted',%s,%s,now()
        ) RETURNING *
        """,
        (
            company, employee_key, framework_id, int(framework_version), competency_id,
            role, _digits(actor_phone), assessor_employee_key, score, proficiency_level,
            evidence_notes, check_in_id, review_id,
        ),
    )
    row = dict(cur.fetchone())
    _audit(
        cur, company_code=company, action="competency_assessed", actor_phone=actor_phone,
        reason=reason, subject_type="competency_assessment", subject_id=str(row["assessment_id"]),
        payload={
            "assessor_role": role,
            "does_not_become_overall_rating": True,
            "framework_version": int(framework_version),
        },
    )
    return {
        "ok": True,
        "assessment": row,
        "becomes_overall_rating": False,
        "layers_remain_separate": True,
    }


# ── Development plans / actions ─────────────────────────────────────────────


def create_development_plan(
    cur: Any,
    *,
    company_code: str,
    actor_phone: str,
    employee_key: str,
    title_en: str,
    title_ar: str | None = None,
    strengths: list[Any] | None = None,
    development_areas: list[Any] | None = None,
    owner_employee_key: str | None = None,
    reason: str = "create development plan",
) -> dict[str, Any]:
    if not str(reason or "").strip():
        return {"ok": False, "error": "audit_reason_required"}
    ent = _entitled(cur, company_code, feature="development")
    if not ent.get("ok"):
        return ent
    company = ent["company_code"]
    cur.execute(
        """
        INSERT INTO perf_development_plans (
          company_code, employee_key, title_en, title_ar, status,
          strengths, development_areas, owner_employee_key, created_by_phone
        ) VALUES (%s,%s,%s,%s,'active',%s::jsonb,%s::jsonb,%s,%s)
        RETURNING *
        """,
        (
            company, employee_key, title_en, title_ar,
            json.dumps(strengths or [], default=str),
            json.dumps(development_areas or [], default=str),
            owner_employee_key or employee_key, _digits(actor_phone),
        ),
    )
    row = dict(cur.fetchone())
    _audit(
        cur, company_code=company, action="development_plan_created", actor_phone=actor_phone,
        reason=reason, subject_type="development_plan", subject_id=str(row["plan_id"]),
        payload={"talent_required": False, "learning_required": False},
    )
    return {"ok": True, "plan": row}


def create_development_action(
    cur: Any,
    *,
    company_code: str,
    actor_phone: str,
    plan_id: str,
    title_en: str,
    title_ar: str | None = None,
    description_en: str | None = None,
    description_ar: str | None = None,
    owner_employee_key: str | None = None,
    due_date: date | None = None,
    source_type: str = "manual",
    source_id: str | None = None,
    create_hr_task: bool = False,
    reason: str = "create development action",
) -> dict[str, Any]:
    if not str(reason or "").strip():
        return {"ok": False, "error": "audit_reason_required"}
    ent = _entitled(cur, company_code, feature="development")
    if not ent.get("ok"):
        return ent
    company = ent["company_code"]
    src = str(source_type or "manual").strip().lower()
    if src not in DEV_SOURCES:
        return {"ok": False, "error": "invalid_source_type", "allowed": list(DEV_SOURCES)}
    cur.execute(
        "SELECT * FROM perf_development_plans WHERE company_code=%s AND plan_id=%s",
        (company, plan_id),
    )
    plan = cur.fetchone()
    if not plan:
        return {"ok": False, "error": "development_plan_not_found"}
    plan = dict(plan)
    if plan["status"] in ("completed", "cancelled"):
        return {"ok": False, "error": "plan_terminal", "status": plan["status"]}
    cur.execute(
        """
        INSERT INTO perf_development_actions (
          company_code, plan_id, title_en, title_ar, description_en, description_ar,
          status, owner_employee_key, due_date, source_type, source_id, created_by_phone
        ) VALUES (%s,%s,%s,%s,%s,%s,'proposed',%s,%s,%s,%s,%s)
        RETURNING *
        """,
        (
            company, plan_id, title_en, title_ar, description_en, description_ar,
            owner_employee_key or plan.get("owner_employee_key"), due_date,
            src, str(source_id) if source_id else None, _digits(actor_phone),
        ),
    )
    row = dict(cur.fetchone())
    task_id = None
    settings = ent["settings"]
    if create_hr_task and settings.get("hr_tasks_integration_enabled"):
        task_id = _maybe_create_hr_task(
            cur,
            company=company,
            employee_key=str(plan["employee_key"]),
            action=row,
        )
        if task_id:
            cur.execute(
                """
                UPDATE perf_development_actions
                SET hr_task_id=%s, task_sync_mode='action_is_sot', updated_at=now()
                WHERE action_id=%s
                RETURNING *
                """,
                (task_id, row["action_id"]),
            )
            row = dict(cur.fetchone())
    _audit(
        cur, company_code=company, action="development_action_created", actor_phone=actor_phone,
        reason=reason, subject_type="development_action", subject_id=str(row["action_id"]),
        payload={
            "source_type": src, "source_id": source_id, "hr_task_id": task_id,
            "survives_review_close": True,
        },
    )
    return {"ok": True, "action": row, "hr_task_id": task_id}


def _maybe_create_hr_task(
    cur: Any, *, company: str, employee_key: str, action: dict[str, Any]
) -> str | None:
    sp = f"c3_task_{uuid.uuid4().hex[:10]}"
    try:
        cur.execute(f"SAVEPOINT {sp}")
        cur.execute("SELECT to_regclass('public.hr_tasks') AS t")
        if not dict(cur.fetchone()).get("t"):
            cur.execute(f"RELEASE SAVEPOINT {sp}")
            return None
        task_id = str(uuid.uuid4())
        cur.execute(
            """
            INSERT INTO hr_tasks (
              task_id, company_code, employee_key, task_type, source, status, title, metadata
            ) VALUES (
              %s,%s,%s,'development_action_open',%s,'open',%s,%s::jsonb
            )
            """,
            (
                task_id, company, employee_key, PHASE,
                str(action.get("title_en") or "Development action"),
                json.dumps(
                    {
                        "sot": PHASE,
                        "completion_contract": "action_is_sot",
                        "action_id": str(action.get("action_id")),
                        "plan_id": str(action.get("plan_id")),
                        "source_type": action.get("source_type"),
                    },
                    default=str,
                ),
            ),
        )
        cur.execute(f"RELEASE SAVEPOINT {sp}")
        return task_id
    except Exception:
        try:
            cur.execute(f"ROLLBACK TO SAVEPOINT {sp}")
            cur.execute(f"RELEASE SAVEPOINT {sp}")
        except Exception:
            pass
        return None


def advance_development_action(
    cur: Any,
    *,
    company_code: str,
    action_id: str,
    actor_phone: str,
    to_status: str,
    expected_row_version: int,
    progress_notes: str | None = None,
    evidence_notes: str | None = None,
    reason: str = "advance development action",
) -> dict[str, Any]:
    ent = _entitled(cur, company_code, feature="development")
    if not ent.get("ok"):
        return ent
    company = ent["company_code"]
    target = str(to_status or "").strip().lower()
    if target not in DEV_ACTION_STATES:
        return {"ok": False, "error": "invalid_status", "allowed": list(DEV_ACTION_STATES)}
    cur.execute(
        "SELECT * FROM perf_development_actions WHERE company_code=%s AND action_id=%s",
        (company, action_id),
    )
    row = cur.fetchone()
    if not row:
        return {"ok": False, "error": "development_action_not_found"}
    action = dict(row)
    if int(action["row_version"]) != int(expected_row_version):
        return {"ok": False, "error": "stale_row_version"}
    transitions = {
        "proposed": {"accepted", "cancelled"},
        "accepted": {"in_progress", "cancelled"},
        "in_progress": {"done", "cancelled"},
        "done": set(),
        "cancelled": set(),
    }
    if target not in transitions.get(str(action["status"]), set()):
        return {
            "ok": False,
            "error": "invalid_transition",
            "from": action["status"],
            "to": target,
        }
    completed_at = datetime.utcnow() if target == "done" else None
    cur.execute(
        """
        UPDATE perf_development_actions SET
          status=%s,
          progress_notes=COALESCE(%s, progress_notes),
          evidence_notes=COALESCE(%s, evidence_notes),
          completed_at=COALESCE(%s, completed_at),
          row_version=row_version+1,
          updated_at=now()
        WHERE action_id=%s AND company_code=%s AND row_version=%s
        RETURNING *
        """,
        (
            target, progress_notes, evidence_notes, completed_at,
            action_id, company, expected_row_version,
        ),
    )
    updated = cur.fetchone()
    if not updated:
        return {"ok": False, "error": "stale_row_version"}
    updated = dict(updated)
    # Explicit task mirror — action is SoT; do not leave competing status.
    if updated.get("hr_task_id") and updated.get("task_sync_mode") == "action_is_sot":
        _mirror_hr_task_status(cur, action=updated)
    _audit(
        cur, company_code=company, action="development_action_advanced",
        actor_phone=actor_phone, reason=reason, subject_type="development_action",
        subject_id=str(action_id),
        payload={"to": target, "source_type": updated.get("source_type"), "source_id": updated.get("source_id")},
    )
    return {"ok": True, "action": updated}


def _mirror_hr_task_status(cur: Any, *, action: dict[str, Any]) -> None:
    task_id = action.get("hr_task_id")
    if not task_id:
        return
    status_map = {
        "proposed": "open",
        "accepted": "open",
        "in_progress": "open",
        "done": "resolved",
        "cancelled": "cancelled",
    }
    hr_status = status_map.get(str(action.get("status")), "open")
    sp = f"c3_tm_{uuid.uuid4().hex[:10]}"
    try:
        cur.execute(f"SAVEPOINT {sp}")
        cur.execute("SELECT to_regclass('public.hr_tasks') AS t")
        if not dict(cur.fetchone()).get("t"):
            cur.execute(f"RELEASE SAVEPOINT {sp}")
            return
        if hr_status == "resolved":
            cur.execute(
                """
                UPDATE hr_tasks SET status='resolved', resolved_at=now(), updated_at=now(),
                  metadata = COALESCE(metadata,'{}'::jsonb) || %s::jsonb
                WHERE task_id=%s
                """,
                (
                    json.dumps({"mirrored_from_action": str(action.get("action_id")), "sot": PHASE}),
                    task_id,
                ),
            )
        else:
            cur.execute(
                """
                UPDATE hr_tasks SET status=%s, updated_at=now(),
                  metadata = COALESCE(metadata,'{}'::jsonb) || %s::jsonb
                WHERE task_id=%s
                """,
                (
                    hr_status,
                    json.dumps({"mirrored_from_action": str(action.get("action_id")), "sot": PHASE}),
                    task_id,
                ),
            )
        cur.execute(f"RELEASE SAVEPOINT {sp}")
    except Exception:
        try:
            cur.execute(f"ROLLBACK TO SAVEPOINT {sp}")
            cur.execute(f"RELEASE SAVEPOINT {sp}")
        except Exception:
            pass


def propose_development_from_check_in(
    cur: Any,
    *,
    company_code: str,
    actor_phone: str,
    check_in_id: str,
    plan_id: str,
    title_en: str,
    title_ar: str | None = None,
    due_date: date | None = None,
) -> dict[str, Any]:
    """Reviews/check-ins may propose actions; closing origin never deletes them."""
    ci = get_check_in(cur, company_code=company_code, check_in_id=check_in_id)
    if not ci:
        return {"ok": False, "error": "check_in_not_found"}
    return create_development_action(
        cur,
        company_code=company_code,
        actor_phone=actor_phone,
        plan_id=plan_id,
        title_en=title_en,
        title_ar=title_ar,
        due_date=due_date,
        source_type="check_in",
        source_id=str(check_in_id),
        reason="propose development from check-in",
    )


def close_plan(
    cur: Any,
    *,
    company_code: str,
    plan_id: str,
    actor_phone: str,
    to_status: str = "completed",
    reason: str = "close development plan",
) -> dict[str, Any]:
    ent = _entitled(cur, company_code, feature="development")
    if not ent.get("ok"):
        return ent
    company = ent["company_code"]
    target = str(to_status or "completed").strip().lower()
    if target not in ("completed", "cancelled"):
        return {"ok": False, "error": "invalid_plan_close_status"}
    cur.execute(
        """
        UPDATE perf_development_plans
        SET status=%s, row_version=row_version+1, updated_at=now()
        WHERE company_code=%s AND plan_id=%s
        RETURNING *
        """,
        (target, company, plan_id),
    )
    row = cur.fetchone()
    if not row:
        return {"ok": False, "error": "development_plan_not_found"}
    # Actions retain provenance; closing plan does not delete actions.
    cur.execute(
        "SELECT count(*) AS n FROM perf_development_actions WHERE plan_id=%s",
        (plan_id,),
    )
    n = int(dict(cur.fetchone())["n"])
    _audit(
        cur, company_code=company, action="development_plan_closed", actor_phone=actor_phone,
        reason=reason, subject_type="development_plan", subject_id=str(plan_id),
        payload={"to": target, "actions_retained": n},
    )
    return {"ok": True, "plan": dict(row), "actions_retained": n}


def prove_review_close_does_not_bury_development(
    cur: Any, *, company_code: str, action_id: str
) -> dict[str, Any]:
    """Charter proof helper — development survives originating review/check-in close."""
    company = company_code_norm(company_code)
    cur.execute(
        "SELECT * FROM perf_development_actions WHERE company_code=%s AND action_id=%s",
        (company, action_id),
    )
    row = cur.fetchone()
    if not row:
        return {"ok": False, "error": "development_action_not_found"}
    action = dict(row)
    return {
        "ok": True,
        "action_present": True,
        "source_type": action.get("source_type"),
        "source_id": action.get("source_id"),
        "status": action.get("status"),
        "buried_by_origin_close": False,
    }
