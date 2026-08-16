#!/usr/bin/env python3
"""Wave 4 C2 — Performance Review Cycles / Ratings / Multi-rater (company-scoped).

Owner-approved under WAVE4_PERFORMANCE_TALENT_CHARTER (2026-08-12) §0.8.3–0.8.4.

Cycle SM:
  draft → configured → launched → in_progress
       → calibration_ready → closed | cancelled

Launch is the snapshot authority boundary (template/scale/competency/weights/
reviewers/population/visibility/anonymity/due dates). Later Setup edits do not
mutate in-flight or historical cycles.

Review truth layers (never overwrite):
  self → manager → additional/360 → final (calibrated later in C4; C2 may set
  final from manager on close with audit, without erasing submitted layers).

360: anonymity + min respondent threshold; fail closed below threshold.
Goals: OPTIONAL consume of C1 evidence snapshotted at launch/submit.
No Talent/HiPo/potential classification.

Gates (fail-closed):
  1) WATHEFNI_PERFORMANCE_REVIEWS_C2 must be on
  2) company in WATHEFNI_PERFORMANCE_REVIEWS_COMPANIES (empty = nobody)
  3) company entitlement in performance_reviews_c2_company_settings
"""
from __future__ import annotations

import json
import os
from datetime import date, datetime
from typing import Any

PHASE = "performance_reviews_c2"
CONTRACT_VERSION = "performance_reviews_c2_v1"
PASS_STAMP = "PERFORMANCE_REVIEWS_FULL_PASS"
COMMERCIAL_MODULE_KEY = "performance"
_ON = {"1", "true", "yes", "on"}

CYCLE_STATES = (
    "draft",
    "configured",
    "launched",
    "in_progress",
    "calibration_ready",
    "closed",
    "cancelled",
)
REVIEW_ROLES = ("self", "manager", "additional", "peer", "subordinate", "stakeholder")
REVIEW_STATES = ("not_started", "draft", "submitted", "acknowledged", "declined_ack")

STATUS_LABELS = {
    "draft": {"en": "Draft", "ar": "مسودة"},
    "configured": {"en": "Configured", "ar": "مُعدّ"},
    "launched": {"en": "Launched", "ar": "مُطلَق"},
    "in_progress": {"en": "In progress", "ar": "قيد التنفيذ"},
    "calibration_ready": {"en": "Calibration ready", "ar": "جاهز للمعايرة"},
    "closed": {"en": "Closed", "ar": "مغلق"},
    "cancelled": {"en": "Cancelled", "ar": "ملغى"},
    "not_started": {"en": "Not started", "ar": "لم يبدأ"},
    "submitted": {"en": "Submitted", "ar": "مُقدَّم"},
    "acknowledged": {"en": "Acknowledged", "ar": "مُقرّ"},
    "declined_ack": {"en": "Ack declined", "ar": "رفض الإقرار"},
    "self": {"en": "Self review", "ar": "تقييم ذاتي"},
    "manager": {"en": "Manager review", "ar": "تقييم المدير"},
    "peer": {"en": "Peer review", "ar": "تقييم الزميل"},
    "additional": {"en": "Additional reviewer", "ar": "مراجع إضافي"},
    "subordinate": {"en": "Direct-report review", "ar": "تقييم المرؤوس"},
    "stakeholder": {"en": "Stakeholder review", "ar": "تقييم صاحب مصلحة"},
    "anonymity_threshold_not_met": {
        "en": "Anonymity threshold not met",
        "ar": "لم يُستوفَ حد إخفاء الهوية",
    },
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


def performance_reviews_c2_runtime_on() -> bool:
    return _env_on("WATHEFNI_PERFORMANCE_REVIEWS_C2", "off")


def performance_reviews_company_allowlist() -> set[str]:
    raw = str(os.environ.get("WATHEFNI_PERFORMANCE_REVIEWS_COMPANIES") or "").strip()
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
        "talent_required": False,
        "hipo_classification_in_c2": False,
        "potential_classification_in_c2": False,
        "cycle_launch_snapshots_rules": True,
        "setup_cannot_mutate_launched_cycle": True,
        "self_manager_360_final_are_separate_layers": True,
        "calibration_never_erases_submitted": True,
        "goals_integration_optional": True,
        "anonymity_fail_closed_below_threshold": True,
        "fake_anonymity_forbidden": True,
        "company_code": company_code_norm(company_code) if company_code else None,
    }


def rollback_guidance() -> dict[str, Any]:
    return {
        "phase": PHASE,
        "ok": True,
        "steps": [
            "WATHEFNI_PERFORMANCE_REVIEWS_C2=off",
            "Clear WATHEFNI_PERFORMANCE_REVIEWS_COMPANIES",
            "WATHEFNI_PERFORMANCE_KILL=on (optional immediate block)",
            "Disable company entitlement — historical reviews preserved",
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
    if not performance_reviews_c2_runtime_on():
        return {
            "ok": False,
            "enabled": False,
            "error": "performance_reviews_c2_off",
            "gate": "runtime_flag",
            "phase": PHASE,
        }
    allow = performance_reviews_company_allowlist()
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
                "error": "performance_reviews_company_not_allowlisted",
                "gate": "company_allowlist",
                "phase": PHASE,
                "company_code": company,
                "message": "Performance-reviews allowlist empty — fail closed (nobody).",
            }
    return {"ok": True, "enabled": True, "company_code": company, "phase": PHASE}


def ensure_performance_reviews_c2_schema(cur: Any, *, force: bool = False) -> None:
    _ = force
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS performance_reviews_c2_company_settings (
          company_code text PRIMARY KEY,
          enabled boolean NOT NULL DEFAULT false,
          goals_integration_enabled boolean NOT NULL DEFAULT true,
          competencies_enabled boolean NOT NULL DEFAULT false,
          review_360_enabled boolean NOT NULL DEFAULT false,
          anonymity_default boolean NOT NULL DEFAULT true,
          min_respondent_threshold int NOT NULL DEFAULT 3,
          allow_hr_raw_360 boolean NOT NULL DEFAULT false,
          require_self_review boolean NOT NULL DEFAULT true,
          require_manager_review boolean NOT NULL DEFAULT true,
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
        CREATE TABLE IF NOT EXISTS perf_rating_scales (
          scale_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
          company_code text NOT NULL,
          name_en text NOT NULL,
          name_ar text,
          version int NOT NULL DEFAULT 1,
          scale_type text NOT NULL DEFAULT 'numeric',
          points jsonb NOT NULL,
          allow_not_observed boolean NOT NULL DEFAULT true,
          status text NOT NULL DEFAULT 'active',
          created_by_phone text,
          created_at timestamptz NOT NULL DEFAULT now(),
          updated_at timestamptz NOT NULL DEFAULT now(),
          CONSTRAINT perf_scale_type_chk CHECK (scale_type IN ('numeric','labeled','mixed'))
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS perf_review_templates (
          template_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
          company_code text NOT NULL,
          name_en text NOT NULL,
          name_ar text,
          version int NOT NULL DEFAULT 1,
          sections jsonb NOT NULL DEFAULT '[]'::jsonb,
          include_goals boolean NOT NULL DEFAULT true,
          include_competencies boolean NOT NULL DEFAULT false,
          status text NOT NULL DEFAULT 'active',
          created_by_phone text,
          created_at timestamptz NOT NULL DEFAULT now(),
          updated_at timestamptz NOT NULL DEFAULT now()
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS perf_competency_frameworks (
          framework_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
          company_code text NOT NULL,
          name_en text NOT NULL,
          name_ar text,
          version int NOT NULL DEFAULT 1,
          competencies jsonb NOT NULL DEFAULT '[]'::jsonb,
          status text NOT NULL DEFAULT 'active',
          created_by_phone text,
          created_at timestamptz NOT NULL DEFAULT now()
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS perf_review_cycles (
          cycle_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
          company_code text NOT NULL,
          name_en text NOT NULL,
          name_ar text,
          status text NOT NULL DEFAULT 'draft',
          period_start date,
          period_end date,
          due_self date,
          due_manager date,
          due_360 date,
          template_id uuid,
          scale_id uuid,
          framework_id uuid,
          goals_integration boolean NOT NULL DEFAULT false,
          competencies_enabled boolean NOT NULL DEFAULT false,
          review_360_enabled boolean NOT NULL DEFAULT false,
          anonymity_enabled boolean NOT NULL DEFAULT true,
          min_respondent_threshold int NOT NULL DEFAULT 3,
          visibility_rules jsonb NOT NULL DEFAULT '{}'::jsonb,
          goal_weight_rules jsonb NOT NULL DEFAULT '{}'::jsonb,
          snapshot jsonb,
          launched_at timestamptz,
          launched_by_phone text,
          closed_at timestamptz,
          closed_by_phone text,
          row_version int NOT NULL DEFAULT 1,
          created_by_phone text,
          created_at timestamptz NOT NULL DEFAULT now(),
          updated_at timestamptz NOT NULL DEFAULT now(),
          metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
          CONSTRAINT perf_cycle_status_chk CHECK (status IN (
            'draft','configured','launched','in_progress','calibration_ready','closed','cancelled'
          ))
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS perf_cycle_participants (
          participant_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
          company_code text NOT NULL,
          cycle_id uuid NOT NULL REFERENCES perf_review_cycles(cycle_id),
          employee_key text NOT NULL,
          manager_employee_key text,
          manager_phone text,
          frozen_at timestamptz NOT NULL DEFAULT now(),
          UNIQUE (cycle_id, employee_key)
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS perf_cycle_reviewer_assignments (
          assignment_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
          company_code text NOT NULL,
          cycle_id uuid NOT NULL REFERENCES perf_review_cycles(cycle_id),
          subject_employee_key text NOT NULL,
          reviewer_role text NOT NULL,
          reviewer_employee_key text,
          reviewer_phone text,
          anonymous boolean NOT NULL DEFAULT false,
          status text NOT NULL DEFAULT 'assigned',
          reassigned_from_assignment_id uuid,
          row_version int NOT NULL DEFAULT 1,
          created_at timestamptz NOT NULL DEFAULT now(),
          updated_at timestamptz NOT NULL DEFAULT now(),
          CONSTRAINT perf_assign_role_chk CHECK (reviewer_role IN (
            'self','manager','additional','peer','subordinate','stakeholder'
          ))
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS perf_reviews (
          review_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
          company_code text NOT NULL,
          cycle_id uuid NOT NULL REFERENCES perf_review_cycles(cycle_id),
          assignment_id uuid REFERENCES perf_cycle_reviewer_assignments(assignment_id),
          subject_employee_key text NOT NULL,
          reviewer_role text NOT NULL,
          reviewer_employee_key text,
          reviewer_phone text,
          status text NOT NULL DEFAULT 'not_started',
          overall_rating_value numeric,
          overall_rating_label text,
          rationale text,
          confidential_comment text,
          components jsonb NOT NULL DEFAULT '[]'::jsonb,
          goal_evidence_snapshot jsonb,
          competency_ratings jsonb,
          submitted_at timestamptz,
          acknowledged_at timestamptz,
          row_version int NOT NULL DEFAULT 1,
          created_at timestamptz NOT NULL DEFAULT now(),
          updated_at timestamptz NOT NULL DEFAULT now(),
          metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
          CONSTRAINT perf_review_role_chk CHECK (reviewer_role IN (
            'self','manager','additional','peer','subordinate','stakeholder'
          )),
          CONSTRAINT perf_review_status_chk CHECK (status IN (
            'not_started','draft','submitted','acknowledged','declined_ack'
          ))
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS perf_review_final_ratings (
          final_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
          company_code text NOT NULL,
          cycle_id uuid NOT NULL,
          subject_employee_key text NOT NULL,
          final_rating_value numeric,
          final_rating_label text,
          source text NOT NULL DEFAULT 'manager_close',
          self_review_id uuid,
          manager_review_id uuid,
          rationale text,
          created_by_phone text,
          created_at timestamptz NOT NULL DEFAULT now(),
          UNIQUE (cycle_id, subject_employee_key),
          CONSTRAINT perf_final_source_chk CHECK (source IN (
            'manager_close','calibration','admin_set'
          ))
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS perf_review_amendments (
          amendment_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
          company_code text NOT NULL,
          review_id uuid NOT NULL REFERENCES perf_reviews(review_id),
          reason text NOT NULL,
          before_payload jsonb NOT NULL,
          after_payload jsonb,
          actor_phone text,
          created_at timestamptz NOT NULL DEFAULT now()
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS performance_reviews_c2_audit (
          audit_id bigserial PRIMARY KEY,
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
    for idx in (
        "CREATE INDEX IF NOT EXISTS perf_cycles_company_idx ON perf_review_cycles(company_code, status)",
        "CREATE INDEX IF NOT EXISTS perf_reviews_cycle_idx ON perf_reviews(cycle_id, subject_employee_key)",
        "CREATE INDEX IF NOT EXISTS perf_assign_cycle_idx ON perf_cycle_reviewer_assignments(cycle_id)",
    ):
        cur.execute(idx)


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
        INSERT INTO performance_reviews_c2_audit (
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
    ensure_performance_reviews_c2_schema(cur)
    cur.execute(
        "SELECT * FROM performance_reviews_c2_company_settings WHERE company_code=%s",
        (company_code_norm(company_code),),
    )
    row = cur.fetchone()
    return dict(row) if row else None


def enable_company_performance_reviews(
    cur: Any,
    *,
    company_code: str,
    actor_phone: str,
    reason: str,
    goals_integration_enabled: bool = True,
    competencies_enabled: bool = False,
    review_360_enabled: bool = False,
    anonymity_default: bool = True,
    min_respondent_threshold: int = 3,
    allow_hr_raw_360: bool = False,
) -> dict[str, Any]:
    if not str(reason or "").strip():
        return {"ok": False, "error": "audit_reason_required"}
    gate = runtime_gate_for_company(company_code)
    if not gate.get("ok"):
        return gate
    if int(min_respondent_threshold) < 2:
        return {
            "ok": False,
            "error": "min_respondent_threshold_too_low",
            "message": "Threshold < 2 enables fake anonymity (n=1 unmask).",
        }
    company = company_code_norm(company_code)
    ensure_performance_reviews_c2_schema(cur)
    cur.execute(
        """
        INSERT INTO performance_reviews_c2_company_settings (
          company_code, enabled, goals_integration_enabled, competencies_enabled,
          review_360_enabled, anonymity_default, min_respondent_threshold, allow_hr_raw_360,
          enabled_by_phone, enabled_reason, enabled_at, updated_by_phone, updated_at, disabled_at
        ) VALUES (%s,true,%s,%s,%s,%s,%s,%s,%s,%s,now(),%s,now(),NULL)
        ON CONFLICT (company_code) DO UPDATE SET
          enabled=true,
          goals_integration_enabled=EXCLUDED.goals_integration_enabled,
          competencies_enabled=EXCLUDED.competencies_enabled,
          review_360_enabled=EXCLUDED.review_360_enabled,
          anonymity_default=EXCLUDED.anonymity_default,
          min_respondent_threshold=EXCLUDED.min_respondent_threshold,
          allow_hr_raw_360=EXCLUDED.allow_hr_raw_360,
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
            bool(goals_integration_enabled),
            bool(competencies_enabled),
            bool(review_360_enabled),
            bool(anonymity_default),
            int(min_respondent_threshold),
            bool(allow_hr_raw_360),
            _digits(actor_phone),
            str(reason).strip()[:500],
            _digits(actor_phone),
        ),
    )
    row = dict(cur.fetchone())
    _audit(
        cur,
        company_code=company,
        action="enable_performance_reviews",
        actor_phone=actor_phone,
        reason=reason,
        subject_type="company",
        subject_id=company,
    )
    return {"ok": True, "company": row, **honesty_payload(company_code=company)}


def disable_company_performance_reviews(
    cur: Any, *, company_code: str, actor_phone: str, reason: str
) -> dict[str, Any]:
    if not str(reason or "").strip():
        return {"ok": False, "error": "audit_reason_required"}
    company = company_code_norm(company_code)
    ensure_performance_reviews_c2_schema(cur)
    cur.execute(
        """
        UPDATE performance_reviews_c2_company_settings
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
        action="disable_performance_reviews",
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
    gate = runtime_gate_for_company(company_code)
    if not gate.get("ok"):
        return gate
    settings = get_company_settings(cur, company_code)
    if not settings or not settings.get("enabled"):
        return {
            "ok": False,
            "error": "performance_reviews_entitlement_off",
            "gate": "company_entitlement",
            "phase": PHASE,
        }
    return {"ok": True, "settings": settings, **honesty_payload(company_code=company_code)}


def feature_visibility(cur: Any, company_code: str | None) -> dict[str, Any]:
    gate = runtime_gate_for_company(company_code)
    settings = get_company_settings(cur, company_code) if gate.get("ok") else None
    enabled = bool(gate.get("ok") and settings and settings.get("enabled"))
    return {
        "ok": True,
        "module_enabled": enabled,
        "review_cycles_visible": enabled,
        "review_360_visible": bool(enabled and settings and settings.get("review_360_enabled")),
        "competencies_visible": bool(enabled and settings and settings.get("competencies_enabled")),
        "goals_integration_visible": bool(
            enabled and settings and settings.get("goals_integration_enabled")
        ),
        "talent_visible": False,
        "calibration_mutate_visible": False,
        "assistant_mutations": False,
        **honesty_payload(company_code=company_code),
    }


def create_rating_scale(
    cur: Any,
    *,
    company_code: str,
    actor_phone: str,
    name_en: str,
    points: list[dict[str, Any]],
    scale_type: str = "numeric",
    name_ar: str | None = None,
    allow_not_observed: bool = True,
    reason: str = "create scale",
) -> dict[str, Any]:
    enabled = module_enabled_for_company(cur, company_code)
    if not enabled.get("ok"):
        return enabled
    if not points or not isinstance(points, list):
        return {"ok": False, "error": "points_required"}
    st = str(scale_type or "numeric").strip().lower()
    if st not in ("numeric", "labeled", "mixed"):
        return {"ok": False, "error": "invalid_scale_type"}
    company = company_code_norm(company_code)
    cur.execute(
        """
        INSERT INTO perf_rating_scales (
          company_code, name_en, name_ar, scale_type, points, allow_not_observed, created_by_phone
        ) VALUES (%s,%s,%s,%s,%s::jsonb,%s,%s)
        RETURNING *
        """,
        (
            company,
            str(name_en).strip()[:200],
            (str(name_ar).strip()[:200] if name_ar else None),
            st,
            json.dumps(points, default=str),
            bool(allow_not_observed),
            _digits(actor_phone),
        ),
    )
    row = dict(cur.fetchone())
    _audit(
        cur,
        company_code=company,
        action="rating_scale_created",
        actor_phone=actor_phone,
        reason=reason,
        subject_type="rating_scale",
        subject_id=str(row["scale_id"]),
        payload={"version": 1, "scale_type": st},
    )
    return {"ok": True, "scale": row, **honesty_payload(company_code=company)}


def bump_rating_scale_version(
    cur: Any, *, company_code: str, scale_id: str, actor_phone: str, points: list[dict[str, Any]], reason: str
) -> dict[str, Any]:
    """New version row — does not mutate scales already snapshotted on launched cycles."""
    if not str(reason or "").strip():
        return {"ok": False, "error": "audit_reason_required"}
    enabled = module_enabled_for_company(cur, company_code)
    if not enabled.get("ok"):
        return enabled
    company = company_code_norm(company_code)
    cur.execute(
        "SELECT * FROM perf_rating_scales WHERE company_code=%s AND scale_id=%s",
        (company, scale_id),
    )
    old = cur.fetchone()
    if not old:
        return {"ok": False, "error": "scale_not_found"}
    old = dict(old)
    cur.execute(
        """
        INSERT INTO perf_rating_scales (
          company_code, name_en, name_ar, version, scale_type, points, allow_not_observed, created_by_phone
        ) VALUES (%s,%s,%s,%s,%s,%s::jsonb,%s,%s)
        RETURNING *
        """,
        (
            company,
            old["name_en"],
            old.get("name_ar"),
            int(old.get("version") or 1) + 1,
            old.get("scale_type") or "numeric",
            json.dumps(points, default=str),
            bool(old.get("allow_not_observed")),
            _digits(actor_phone),
        ),
    )
    row = dict(cur.fetchone())
    _audit(
        cur,
        company_code=company,
        action="rating_scale_versioned",
        actor_phone=actor_phone,
        reason=reason,
        subject_type="rating_scale",
        subject_id=str(row["scale_id"]),
        payload={"prior_scale_id": str(scale_id), "version": row.get("version")},
    )
    return {"ok": True, "scale": row, "prior_scale_id": str(scale_id), **honesty_payload(company_code=company)}


def create_review_template(
    cur: Any,
    *,
    company_code: str,
    actor_phone: str,
    name_en: str,
    sections: list[dict[str, Any]] | None = None,
    include_goals: bool = True,
    include_competencies: bool = False,
    name_ar: str | None = None,
    reason: str = "create template",
) -> dict[str, Any]:
    enabled = module_enabled_for_company(cur, company_code)
    if not enabled.get("ok"):
        return enabled
    company = company_code_norm(company_code)
    secs = sections or [
        {"key": "overall", "title_en": "Overall", "title_ar": "الإجمالي", "weight": 1}
    ]
    cur.execute(
        """
        INSERT INTO perf_review_templates (
          company_code, name_en, name_ar, sections, include_goals, include_competencies, created_by_phone
        ) VALUES (%s,%s,%s,%s::jsonb,%s,%s,%s)
        RETURNING *
        """,
        (
            company,
            str(name_en).strip()[:200],
            (str(name_ar).strip()[:200] if name_ar else None),
            json.dumps(secs, default=str),
            bool(include_goals),
            bool(include_competencies),
            _digits(actor_phone),
        ),
    )
    row = dict(cur.fetchone())
    _audit(
        cur,
        company_code=company,
        action="review_template_created",
        actor_phone=actor_phone,
        reason=reason,
        subject_type="review_template",
        subject_id=str(row["template_id"]),
    )
    return {"ok": True, "template": row, **honesty_payload(company_code=company)}


def create_competency_framework(
    cur: Any,
    *,
    company_code: str,
    actor_phone: str,
    name_en: str,
    competencies: list[dict[str, Any]],
    name_ar: str | None = None,
    reason: str = "create framework",
) -> dict[str, Any]:
    enabled = module_enabled_for_company(cur, company_code)
    if not enabled.get("ok"):
        return enabled
    company = company_code_norm(company_code)
    cur.execute(
        """
        INSERT INTO perf_competency_frameworks (
          company_code, name_en, name_ar, competencies, created_by_phone
        ) VALUES (%s,%s,%s,%s::jsonb,%s)
        RETURNING *
        """,
        (
            company,
            str(name_en).strip()[:200],
            (str(name_ar).strip()[:200] if name_ar else None),
            json.dumps(competencies or [], default=str),
            _digits(actor_phone),
        ),
    )
    row = dict(cur.fetchone())
    _audit(
        cur,
        company_code=company,
        action="competency_framework_created",
        actor_phone=actor_phone,
        reason=reason,
        subject_type="competency_framework",
        subject_id=str(row["framework_id"]),
    )
    return {"ok": True, "framework": row, **honesty_payload(company_code=company)}


def get_cycle(cur: Any, *, company_code: str, cycle_id: str) -> dict[str, Any] | None:
    cur.execute(
        "SELECT * FROM perf_review_cycles WHERE company_code=%s AND cycle_id=%s",
        (company_code_norm(company_code), cycle_id),
    )
    row = cur.fetchone()
    return dict(row) if row else None


def create_cycle(
    cur: Any,
    *,
    company_code: str,
    actor_phone: str,
    name_en: str,
    period_start: date | str,
    period_end: date | str,
    template_id: str,
    scale_id: str,
    name_ar: str | None = None,
    framework_id: str | None = None,
    goals_integration: bool | None = None,
    competencies_enabled: bool | None = None,
    review_360_enabled: bool | None = None,
    anonymity_enabled: bool | None = None,
    min_respondent_threshold: int | None = None,
    due_self: date | str | None = None,
    due_manager: date | str | None = None,
    due_360: date | str | None = None,
    visibility_rules: dict[str, Any] | None = None,
    goal_weight_rules: dict[str, Any] | None = None,
    reason: str = "create cycle",
) -> dict[str, Any]:
    enabled = module_enabled_for_company(cur, company_code)
    if not enabled.get("ok"):
        return enabled
    settings = enabled["settings"]
    company = company_code_norm(company_code)
    thr = int(min_respondent_threshold if min_respondent_threshold is not None else settings.get("min_respondent_threshold") or 3)
    if thr < 2:
        return {"ok": False, "error": "min_respondent_threshold_too_low"}
    cur.execute(
        """
        INSERT INTO perf_review_cycles (
          company_code, name_en, name_ar, status, period_start, period_end,
          due_self, due_manager, due_360, template_id, scale_id, framework_id,
          goals_integration, competencies_enabled, review_360_enabled,
          anonymity_enabled, min_respondent_threshold, visibility_rules, goal_weight_rules,
          created_by_phone
        ) VALUES (
          %s,%s,%s,'draft',%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb,%s::jsonb,%s
        )
        RETURNING *
        """,
        (
            company,
            str(name_en).strip()[:300],
            (str(name_ar).strip()[:300] if name_ar else None),
            str(period_start)[:10],
            str(period_end)[:10],
            str(due_self)[:10] if due_self else None,
            str(due_manager)[:10] if due_manager else None,
            str(due_360)[:10] if due_360 else None,
            template_id,
            scale_id,
            framework_id,
            bool(settings.get("goals_integration_enabled") if goals_integration is None else goals_integration),
            bool(settings.get("competencies_enabled") if competencies_enabled is None else competencies_enabled),
            bool(settings.get("review_360_enabled") if review_360_enabled is None else review_360_enabled),
            bool(settings.get("anonymity_default") if anonymity_enabled is None else anonymity_enabled),
            thr,
            json.dumps(visibility_rules or {"reveal_self_to_manager": True, "reveal_final_to_employee": True}),
            json.dumps(goal_weight_rules or {"include_okr": True, "include_kpi": True}),
            _digits(actor_phone),
        ),
    )
    row = dict(cur.fetchone())
    _audit(
        cur,
        company_code=company,
        action="cycle_created",
        actor_phone=actor_phone,
        reason=reason,
        subject_type="review_cycle",
        subject_id=str(row["cycle_id"]),
    )
    return {"ok": True, "cycle": row, **honesty_payload(company_code=company)}


def configure_cycle(
    cur: Any,
    *,
    company_code: str,
    cycle_id: str,
    actor_phone: str,
    participants: list[dict[str, Any]],
    peer_assignments: list[dict[str, Any]] | None = None,
    reason: str = "configure cycle",
) -> dict[str, Any]:
    """Add population + reviewer assignments; move draft → configured."""
    enabled = module_enabled_for_company(cur, company_code)
    if not enabled.get("ok"):
        return enabled
    company = company_code_norm(company_code)
    cycle = get_cycle(cur, company_code=company, cycle_id=cycle_id)
    if not cycle:
        return {"ok": False, "error": "cycle_not_found"}
    if cycle["status"] not in ("draft", "configured"):
        return {"ok": False, "error": "cycle_not_configurable", "status": cycle["status"]}
    if not participants:
        return {"ok": False, "error": "participants_required"}

    # Clear prior config only while not launched
    cur.execute("DELETE FROM perf_cycle_reviewer_assignments WHERE cycle_id=%s", (cycle_id,))
    cur.execute("DELETE FROM perf_cycle_participants WHERE cycle_id=%s", (cycle_id,))

    for p in participants:
        emp = str(p.get("employee_key") or "")
        mgr = p.get("manager_employee_key")
        mgr_phone = p.get("manager_phone")
        emp_phone = p.get("employee_phone")
        if not emp:
            return {"ok": False, "error": "participant_employee_key_required"}
        cur.execute(
            """
            INSERT INTO perf_cycle_participants (
              company_code, cycle_id, employee_key, manager_employee_key, manager_phone
            ) VALUES (%s,%s,%s,%s,%s)
            """,
            (company, cycle_id, emp, mgr, _digits(mgr_phone) if mgr_phone else None),
        )
        # self
        cur.execute(
            """
            INSERT INTO perf_cycle_reviewer_assignments (
              company_code, cycle_id, subject_employee_key, reviewer_role,
              reviewer_employee_key, reviewer_phone, anonymous
            ) VALUES (%s,%s,%s,'self',%s,%s,false)
            """,
            (company, cycle_id, emp, emp, _digits(emp_phone) if emp_phone else None),
        )
        # manager
        if mgr or mgr_phone:
            cur.execute(
                """
                INSERT INTO perf_cycle_reviewer_assignments (
                  company_code, cycle_id, subject_employee_key, reviewer_role,
                  reviewer_employee_key, reviewer_phone, anonymous
                ) VALUES (%s,%s,%s,'manager',%s,%s,false)
                """,
                (company, cycle_id, emp, mgr, _digits(mgr_phone) if mgr_phone else None),
            )

    if cycle.get("review_360_enabled") and peer_assignments:
        for pa in peer_assignments:
            cur.execute(
                """
                INSERT INTO perf_cycle_reviewer_assignments (
                  company_code, cycle_id, subject_employee_key, reviewer_role,
                  reviewer_employee_key, reviewer_phone, anonymous
                ) VALUES (%s,%s,%s,%s,%s,%s,%s)
                """,
                (
                    company,
                    cycle_id,
                    str(pa["subject_employee_key"]),
                    str(pa.get("reviewer_role") or "peer"),
                    pa.get("reviewer_employee_key"),
                    _digits(pa.get("reviewer_phone")) if pa.get("reviewer_phone") else None,
                    bool(cycle.get("anonymity_enabled")),
                ),
            )

    cur.execute(
        """
        UPDATE perf_review_cycles
           SET status='configured', row_version=row_version+1, updated_at=now()
         WHERE company_code=%s AND cycle_id=%s
        RETURNING *
        """,
        (company, cycle_id),
    )
    row = dict(cur.fetchone())
    _audit(
        cur,
        company_code=company,
        action="cycle_configured",
        actor_phone=actor_phone,
        reason=reason,
        subject_type="review_cycle",
        subject_id=str(cycle_id),
        payload={"participant_count": len(participants)},
    )
    return {"ok": True, "cycle": row, **honesty_payload(company_code=company)}


def _load_entity(cur: Any, table: str, company: str, id_col: str, id_val: str) -> dict[str, Any] | None:
    cur.execute(f"SELECT * FROM {table} WHERE company_code=%s AND {id_col}=%s", (company, id_val))
    row = cur.fetchone()
    return dict(row) if row else None


def _snapshot_goal_evidence(cur: Any, *, company: str, employee_key: str) -> dict[str, Any]:
    """OPTIONAL C1 consume — snapshot current OKR/KPI evidence; empty if C1 off/unavailable."""
    out: dict[str, Any] = {"contract": "performance.goals_in_reviews", "objectives": [], "goals": []}
    try:
        cur.execute(
            """
            SELECT objective_id, title_en, title_ar, status, scope
              FROM perf_objectives
             WHERE company_code=%s AND owner_employee_key=%s
               AND status IN ('active','completed')
            """,
            (company, employee_key),
        )
        for obj in cur.fetchall() or []:
            o = dict(obj)
            oid = str(o["objective_id"])
            cur.execute(
                """
                SELECT kr.key_result_id, kr.title_en, kr.weight, kr.current_value, kr.status,
                       m.baseline, m.target, m.direction, m.unit, m.version AS measure_version
                  FROM perf_key_results kr
                  JOIN perf_measure_definitions m ON m.measure_id=kr.measure_id
                 WHERE kr.objective_id=%s
                """,
                (oid,),
            )
            krs = [dict(r) for r in (cur.fetchall() or [])]
            # Prefer C1 rollup if importable
            try:
                import performance_goals_c1 as c1

                roll = c1.objective_rollup(cur, company_code=company, objective_id=oid)
            except Exception:
                roll = {"progress_pct": None}
            out["objectives"].append(
                {
                    "objective_id": oid,
                    "title_en": o.get("title_en"),
                    "status": o.get("status"),
                    "rollup_progress_pct": roll.get("progress_pct"),
                    "key_results": krs,
                    "snapshotted_at": datetime.utcnow().isoformat() + "Z",
                }
            )
        cur.execute(
            """
            SELECT g.goal_id, g.goal_kind, g.title_en, g.status, g.current_value,
                   m.baseline, m.target, m.direction, m.version AS measure_version
              FROM perf_goals g
              LEFT JOIN perf_measure_definitions m ON m.measure_id=g.measure_id
             WHERE g.company_code=%s AND g.owner_employee_key=%s
               AND g.status IN ('active','completed')
            """,
            (company, employee_key),
        )
        out["goals"] = [dict(r) for r in (cur.fetchall() or [])]
    except Exception as exc:
        out["unavailable"] = str(exc)[:200]
    return out


def launch_cycle(
    cur: Any, *, company_code: str, cycle_id: str, actor_phone: str, reason: str
) -> dict[str, Any]:
    """Authority boundary: freeze snapshot + population; status → launched → in_progress."""
    if not str(reason or "").strip():
        return {"ok": False, "error": "audit_reason_required"}
    enabled = module_enabled_for_company(cur, company_code)
    if not enabled.get("ok"):
        return enabled
    company = company_code_norm(company_code)
    cycle = get_cycle(cur, company_code=company, cycle_id=cycle_id)
    if not cycle:
        return {"ok": False, "error": "cycle_not_found"}
    if cycle["status"] != "configured":
        return {"ok": False, "error": "cycle_must_be_configured_to_launch", "status": cycle["status"]}

    tmpl = _load_entity(cur, "perf_review_templates", company, "template_id", str(cycle["template_id"]))
    scale = _load_entity(cur, "perf_rating_scales", company, "scale_id", str(cycle["scale_id"]))
    if not tmpl or not scale:
        return {"ok": False, "error": "template_or_scale_missing"}
    framework = None
    if cycle.get("framework_id"):
        framework = _load_entity(
            cur, "perf_competency_frameworks", company, "framework_id", str(cycle["framework_id"])
        )

    cur.execute(
        "SELECT * FROM perf_cycle_participants WHERE cycle_id=%s",
        (cycle_id,),
    )
    participants = [dict(r) for r in (cur.fetchall() or [])]
    if not participants:
        return {"ok": False, "error": "empty_population"}
    cur.execute(
        "SELECT * FROM perf_cycle_reviewer_assignments WHERE cycle_id=%s",
        (cycle_id,),
    )
    assignments = [dict(r) for r in (cur.fetchall() or [])]

    goal_snapshots = {}
    if cycle.get("goals_integration"):
        for p in participants:
            goal_snapshots[str(p["employee_key"])] = _snapshot_goal_evidence(
                cur, company=company, employee_key=str(p["employee_key"])
            )

    snapshot = {
        "snapshot_version": 1,
        "snapshotted_at": datetime.utcnow().isoformat() + "Z",
        "template": tmpl,
        "rating_scale": scale,
        "competency_framework": framework,
        "goal_weight_rules": cycle.get("goal_weight_rules") or {},
        "visibility_rules": cycle.get("visibility_rules") or {},
        "anonymity_rules": {
            "enabled": bool(cycle.get("anonymity_enabled")),
            "min_respondent_threshold": int(cycle.get("min_respondent_threshold") or 3),
        },
        "due_dates": {
            "due_self": str(cycle.get("due_self") or ""),
            "due_manager": str(cycle.get("due_manager") or ""),
            "due_360": str(cycle.get("due_360") or ""),
        },
        "flags": {
            "goals_integration": bool(cycle.get("goals_integration")),
            "competencies_enabled": bool(cycle.get("competencies_enabled")),
            "review_360_enabled": bool(cycle.get("review_360_enabled")),
        },
        "population": participants,
        "reviewer_assignments": assignments,
        "goal_evidence_by_employee": goal_snapshots,
    }

    # Materialize review shells
    for a in assignments:
        cur.execute(
            """
            INSERT INTO perf_reviews (
              company_code, cycle_id, assignment_id, subject_employee_key, reviewer_role,
              reviewer_employee_key, reviewer_phone, status,
              goal_evidence_snapshot
            ) VALUES (%s,%s,%s,%s,%s,%s,%s,'not_started',%s::jsonb)
            """,
            (
                company,
                cycle_id,
                a["assignment_id"],
                a["subject_employee_key"],
                a["reviewer_role"],
                a.get("reviewer_employee_key"),
                a.get("reviewer_phone"),
                json.dumps(goal_snapshots.get(str(a["subject_employee_key"])) if cycle.get("goals_integration") else None, default=str)
                if cycle.get("goals_integration")
                else None,
            ),
        )

    cur.execute(
        """
        UPDATE perf_review_cycles
           SET status='in_progress',
               snapshot=%s::jsonb,
               launched_at=now(),
               launched_by_phone=%s,
               row_version=row_version+1,
               updated_at=now()
         WHERE company_code=%s AND cycle_id=%s AND status='configured'
        RETURNING *
        """,
        (json.dumps(snapshot, default=str), _digits(actor_phone), company, cycle_id),
    )
    row = cur.fetchone()
    if not row:
        return {"ok": False, "error": "launch_failed_stale"}
    _audit(
        cur,
        company_code=company,
        action="cycle_launched",
        actor_phone=actor_phone,
        reason=reason,
        subject_type="review_cycle",
        subject_id=str(cycle_id),
        payload={"participant_count": len(participants), "assignment_count": len(assignments)},
    )
    return {
        "ok": True,
        "cycle": dict(row),
        "snapshot_frozen": True,
        **honesty_payload(company_code=company),
    }


def attempt_mutate_launched_setup(
    cur: Any, *, company_code: str, cycle_id: str, new_name_en: str
) -> dict[str, Any]:
    """Prove Setup-like edits cannot rewrite snapshotted cycle rules."""
    cycle = get_cycle(cur, company_code=company_code, cycle_id=cycle_id)
    if not cycle:
        return {"ok": False, "error": "cycle_not_found"}
    if cycle.get("snapshot") and cycle["status"] in (
        "launched",
        "in_progress",
        "calibration_ready",
        "closed",
    ):
        return {
            "ok": False,
            "error": "launched_cycle_immutable",
            "message": "Later Setup changes must not mutate an in-flight or historical cycle snapshot.",
            "snapshot_preserved": True,
        }
    return {"ok": False, "error": "not_launched"}


def get_review_for_assignment(
    cur: Any, *, company_code: str, cycle_id: str, assignment_id: str
) -> dict[str, Any] | None:
    cur.execute(
        """
        SELECT * FROM perf_reviews
         WHERE company_code=%s AND cycle_id=%s AND assignment_id=%s
        """,
        (company_code_norm(company_code), cycle_id, assignment_id),
    )
    row = cur.fetchone()
    return dict(row) if row else None


def _assignment(cur: Any, *, company: str, assignment_id: str) -> dict[str, Any] | None:
    cur.execute(
        "SELECT * FROM perf_cycle_reviewer_assignments WHERE company_code=%s AND assignment_id=%s",
        (company, assignment_id),
    )
    row = cur.fetchone()
    return dict(row) if row else None


def submit_review(
    cur: Any,
    *,
    company_code: str,
    cycle_id: str,
    assignment_id: str,
    actor_phone: str,
    overall_rating_value: Any,
    rationale: str,
    components: list[dict[str, Any]] | None = None,
    competency_ratings: list[dict[str, Any]] | None = None,
    confidential_comment: str | None = None,
    overall_rating_label: str | None = None,
    expected_version: int | None = None,
    actor_employee_key: str | None = None,
) -> dict[str, Any]:
    enabled = module_enabled_for_company(cur, company_code)
    if not enabled.get("ok"):
        return enabled
    company = company_code_norm(company_code)
    cycle = get_cycle(cur, company_code=company, cycle_id=cycle_id)
    if not cycle:
        return {"ok": False, "error": "cycle_not_found"}
    if cycle["status"] in ("closed", "cancelled"):
        return {"ok": False, "error": "cycle_closed"}
    if cycle["status"] not in ("in_progress", "launched", "calibration_ready"):
        return {"ok": False, "error": "cycle_not_open_for_submission", "status": cycle["status"]}
    if not str(rationale or "").strip():
        return {"ok": False, "error": "rationale_required"}

    asn = _assignment(cur, company=company, assignment_id=assignment_id)
    if not asn or str(asn.get("cycle_id")) != str(cycle_id):
        return {"ok": False, "error": "assignment_not_found"}

    # Reviewer enforcement
    actor = _digits(actor_phone)
    if asn.get("reviewer_phone") and actor != _digits(asn.get("reviewer_phone")):
        # allow match by employee_key if phone unset
        if not (
            actor_employee_key
            and asn.get("reviewer_employee_key")
            and str(actor_employee_key) == str(asn.get("reviewer_employee_key"))
        ):
            return {"ok": False, "error": "reviewer_assignment_mismatch"}

    rev = get_review_for_assignment(
        cur, company_code=company, cycle_id=cycle_id, assignment_id=assignment_id
    )
    if not rev:
        return {"ok": False, "error": "review_shell_missing"}
    if rev["status"] == "submitted":
        return {
            "ok": True,
            "idempotent_duplicate_submission": True,
            "review": rev,
            **honesty_payload(company_code=company),
        }
    if expected_version is not None and int(rev.get("row_version") or 1) != int(expected_version):
        return {"ok": False, "error": "stale_row_version", "expected": expected_version}

    # Refresh goal evidence snapshot at submit (still frozen relative to later edits via stored JSON)
    goal_snap = rev.get("goal_evidence_snapshot")
    if cycle.get("goals_integration") and not goal_snap:
        goal_snap = _snapshot_goal_evidence(
            cur, company=company, employee_key=str(asn["subject_employee_key"])
        )

    cur.execute(
        """
        UPDATE perf_reviews
           SET status='submitted',
               overall_rating_value=%s,
               overall_rating_label=%s,
               rationale=%s,
               confidential_comment=%s,
               components=%s::jsonb,
               competency_ratings=%s::jsonb,
               goal_evidence_snapshot=COALESCE(goal_evidence_snapshot, %s::jsonb),
               submitted_at=now(),
               row_version=row_version+1,
               updated_at=now()
         WHERE company_code=%s AND review_id=%s AND status IN ('not_started','draft')
           AND (%s::int IS NULL OR row_version=%s)
        RETURNING *
        """,
        (
            overall_rating_value,
            overall_rating_label,
            str(rationale).strip()[:4000],
            (str(confidential_comment).strip()[:4000] if confidential_comment else None),
            json.dumps(components or [], default=str),
            json.dumps(competency_ratings, default=str) if competency_ratings is not None else None,
            json.dumps(goal_snap, default=str) if goal_snap else None,
            company,
            rev["review_id"],
            expected_version,
            expected_version,
        ),
    )
    row = cur.fetchone()
    if not row:
        return {"ok": False, "error": "stale_or_invalid_status"}
    _audit(
        cur,
        company_code=company,
        action="review_submitted",
        actor_phone=actor_phone,
        subject_type="review",
        subject_id=str(row["review_id"]),
        payload={"role": asn.get("reviewer_role"), "subject": asn.get("subject_employee_key")},
    )
    return {"ok": True, "review": dict(row), **honesty_payload(company_code=company)}


def attempt_mutate_submitted_review(
    cur: Any, *, company_code: str, review_id: str, new_rating: Any
) -> dict[str, Any]:
    cur.execute(
        "SELECT * FROM perf_reviews WHERE company_code=%s AND review_id=%s",
        (company_code_norm(company_code), review_id),
    )
    rev = cur.fetchone()
    if not rev:
        return {"ok": False, "error": "review_not_found"}
    rev = dict(rev)
    if rev.get("status") == "submitted":
        return {
            "ok": False,
            "error": "submitted_review_immutable",
            "message": "Corrections require explicit reopen/amendment authority.",
        }
    return {"ok": False, "error": "not_submitted"}


def reopen_review_for_amendment(
    cur: Any,
    *,
    company_code: str,
    review_id: str,
    actor_phone: str,
    reason: str,
) -> dict[str, Any]:
    if not str(reason or "").strip():
        return {"ok": False, "error": "audit_reason_required"}
    enabled = module_enabled_for_company(cur, company_code)
    if not enabled.get("ok"):
        return enabled
    company = company_code_norm(company_code)
    cur.execute(
        "SELECT r.*, c.status AS cycle_status FROM perf_reviews r JOIN perf_review_cycles c ON c.cycle_id=r.cycle_id WHERE r.company_code=%s AND r.review_id=%s",
        (company, review_id),
    )
    rev = cur.fetchone()
    if not rev:
        return {"ok": False, "error": "review_not_found"}
    rev = dict(rev)
    if rev.get("cycle_status") == "closed":
        return {"ok": False, "error": "closed_cycle_cannot_reopen_silently"}
    if rev.get("status") != "submitted":
        return {"ok": False, "error": "review_not_submitted"}
    before = {
        "overall_rating_value": rev.get("overall_rating_value"),
        "rationale": rev.get("rationale"),
        "status": rev.get("status"),
    }
    cur.execute(
        """
        UPDATE perf_reviews
           SET status='draft', row_version=row_version+1, updated_at=now()
         WHERE review_id=%s
        RETURNING *
        """,
        (review_id,),
    )
    after = dict(cur.fetchone())
    cur.execute(
        """
        INSERT INTO perf_review_amendments (
          company_code, review_id, reason, before_payload, after_payload, actor_phone
        ) VALUES (%s,%s,%s,%s::jsonb,%s::jsonb,%s)
        RETURNING *
        """,
        (
            company,
            review_id,
            str(reason).strip()[:500],
            json.dumps(before, default=str),
            json.dumps({"status": "draft"}, default=str),
            _digits(actor_phone),
        ),
    )
    amd = dict(cur.fetchone())
    _audit(
        cur,
        company_code=company,
        action="review_reopened_for_amendment",
        actor_phone=actor_phone,
        reason=reason,
        subject_type="review",
        subject_id=str(review_id),
    )
    return {"ok": True, "review": after, "amendment": amd, **honesty_payload(company_code=company)}


def reassign_manager_reviewer(
    cur: Any,
    *,
    company_code: str,
    cycle_id: str,
    subject_employee_key: str,
    new_manager_employee_key: str,
    new_manager_phone: str,
    actor_phone: str,
    reason: str,
) -> dict[str, Any]:
    if not str(reason or "").strip():
        return {"ok": False, "error": "audit_reason_required"}
    enabled = module_enabled_for_company(cur, company_code)
    if not enabled.get("ok"):
        return enabled
    company = company_code_norm(company_code)
    cycle = get_cycle(cur, company_code=company, cycle_id=cycle_id)
    if not cycle:
        return {"ok": False, "error": "cycle_not_found"}
    if cycle["status"] == "closed":
        return {"ok": False, "error": "closed_cycle_immutable"}
    cur.execute(
        """
        SELECT * FROM perf_cycle_reviewer_assignments
         WHERE company_code=%s AND cycle_id=%s AND subject_employee_key=%s AND reviewer_role='manager'
         ORDER BY created_at DESC LIMIT 1
        """,
        (company, cycle_id, subject_employee_key),
    )
    old = cur.fetchone()
    if not old:
        return {"ok": False, "error": "manager_assignment_not_found"}
    old = dict(old)
    cur.execute(
        """
        UPDATE perf_cycle_reviewer_assignments
           SET status='reassigned', row_version=row_version+1, updated_at=now()
         WHERE assignment_id=%s
        """,
        (old["assignment_id"],),
    )
    cur.execute(
        """
        INSERT INTO perf_cycle_reviewer_assignments (
          company_code, cycle_id, subject_employee_key, reviewer_role,
          reviewer_employee_key, reviewer_phone, anonymous, reassigned_from_assignment_id
        ) VALUES (%s,%s,%s,'manager',%s,%s,false,%s)
        RETURNING *
        """,
        (
            company,
            cycle_id,
            subject_employee_key,
            new_manager_employee_key,
            _digits(new_manager_phone),
            old["assignment_id"],
        ),
    )
    new_a = dict(cur.fetchone())
    # New review shell if prior not submitted; keep old submitted layer intact
    cur.execute(
        """
        SELECT review_id, status FROM perf_reviews
         WHERE assignment_id=%s
        """,
        (old["assignment_id"],),
    )
    old_rev = cur.fetchone()
    if not old_rev or dict(old_rev).get("status") != "submitted":
        cur.execute(
            """
            INSERT INTO perf_reviews (
              company_code, cycle_id, assignment_id, subject_employee_key, reviewer_role,
              reviewer_employee_key, reviewer_phone, status
            ) VALUES (%s,%s,%s,%s,'manager',%s,%s,'not_started')
            """,
            (
                company,
                cycle_id,
                new_a["assignment_id"],
                subject_employee_key,
                new_manager_employee_key,
                _digits(new_manager_phone),
            ),
        )
    cur.execute(
        """
        UPDATE perf_cycle_participants
           SET manager_employee_key=%s, manager_phone=%s
         WHERE cycle_id=%s AND employee_key=%s
        """,
        (new_manager_employee_key, _digits(new_manager_phone), cycle_id, subject_employee_key),
    )
    _audit(
        cur,
        company_code=company,
        action="manager_reviewer_reassigned",
        actor_phone=actor_phone,
        reason=reason,
        subject_type="review_cycle",
        subject_id=str(cycle_id),
        payload={
            "subject": subject_employee_key,
            "from_assignment": str(old["assignment_id"]),
            "to_assignment": str(new_a["assignment_id"]),
        },
    )
    return {
        "ok": True,
        "assignment": new_a,
        "prior_assignment_id": str(old["assignment_id"]),
        **honesty_payload(company_code=company),
    }


def assert_manager_scope(
    cur: Any,
    *,
    company_code: str,
    cycle_id: str,
    manager_phone: str,
    subject_employee_key: str,
) -> dict[str, Any]:
    company = company_code_norm(company_code)
    cur.execute(
        """
        SELECT assignment_id FROM perf_cycle_reviewer_assignments
         WHERE company_code=%s AND cycle_id=%s AND subject_employee_key=%s
           AND reviewer_role='manager' AND status='assigned'
           AND reviewer_phone=%s
        LIMIT 1
        """,
        (company, cycle_id, subject_employee_key, _digits(manager_phone)),
    )
    row = cur.fetchone()
    if not row:
        return {"ok": False, "error": "manager_out_of_scope"}
    return {"ok": True, "assignment_id": str(dict(row)["assignment_id"])}


def get_360_aggregate(
    cur: Any,
    *,
    company_code: str,
    cycle_id: str,
    subject_employee_key: str,
    actor_role: str = "manager",
) -> dict[str, Any]:
    """Anonymous aggregate — fail closed below threshold; never returns reviewer identities."""
    company = company_code_norm(company_code)
    cycle = get_cycle(cur, company_code=company, cycle_id=cycle_id)
    if not cycle:
        return {"ok": False, "error": "cycle_not_found"}
    if not cycle.get("review_360_enabled"):
        return {"ok": False, "error": "review_360_disabled"}
    thr = int(cycle.get("min_respondent_threshold") or 3)
    cur.execute(
        """
        SELECT overall_rating_value, status
          FROM perf_reviews
         WHERE company_code=%s AND cycle_id=%s AND subject_employee_key=%s
           AND reviewer_role IN ('peer','subordinate','stakeholder')
           AND status='submitted'
        """,
        (company, cycle_id, subject_employee_key),
    )
    rows = [dict(r) for r in (cur.fetchall() or [])]
    n = len(rows)
    if cycle.get("anonymity_enabled") and n < thr:
        return {
            "ok": False,
            "error": "anonymity_threshold_not_met",
            "respondent_count": n,
            "threshold": thr,
            "aggregate": None,
            "identities": None,
            "fail_closed": True,
            "label_en": status_label("anonymity_threshold_not_met", lang="en"),
            "label_ar": status_label("anonymity_threshold_not_met", lang="ar"),
        }
    vals = [float(r["overall_rating_value"]) for r in rows if r.get("overall_rating_value") is not None]
    avg = sum(vals) / len(vals) if vals else None
    return {
        "ok": True,
        "respondent_count": n,
        "threshold": thr,
        "average_rating": avg,
        "identities_redacted": True,
        "actor_role": actor_role,
        **honesty_payload(company_code=company),
    }


def get_raw_360_responses(
    cur: Any,
    *,
    company_code: str,
    cycle_id: str,
    subject_employee_key: str,
    actor_phone: str,
    has_sensitive_hr_permission: bool,
) -> dict[str, Any]:
    settings = get_company_settings(cur, company_code) or {}
    if not has_sensitive_hr_permission or not settings.get("allow_hr_raw_360"):
        return {
            "ok": False,
            "error": "sensitive_360_permission_required",
            "message": "Raw 360 responses require explicit sensitive HR permission and company policy allow.",
        }
    company = company_code_norm(company_code)
    cur.execute(
        """
        SELECT review_id, reviewer_role, overall_rating_value, rationale, confidential_comment,
               reviewer_employee_key, reviewer_phone, submitted_at
          FROM perf_reviews
         WHERE company_code=%s AND cycle_id=%s AND subject_employee_key=%s
           AND reviewer_role IN ('peer','subordinate','stakeholder')
           AND status='submitted'
        """,
        (company, cycle_id, subject_employee_key),
    )
    rows = [dict(r) for r in (cur.fetchall() or [])]
    _audit(
        cur,
        company_code=company,
        action="raw_360_accessed",
        actor_phone=actor_phone,
        subject_type="review_cycle",
        subject_id=str(cycle_id),
        payload={"subject": subject_employee_key, "count": len(rows)},
    )
    return {"ok": True, "responses": rows, "sensitive": True}


def acknowledge_review(
    cur: Any,
    *,
    company_code: str,
    review_id: str,
    actor_phone: str,
    decision: str = "acknowledged",
) -> dict[str, Any]:
    enabled = module_enabled_for_company(cur, company_code)
    if not enabled.get("ok"):
        return enabled
    company = company_code_norm(company_code)
    st = "acknowledged" if decision == "acknowledged" else "declined_ack"
    cur.execute(
        """
        UPDATE perf_reviews
           SET status=%s, acknowledged_at=now(), row_version=row_version+1, updated_at=now()
         WHERE company_code=%s AND review_id=%s AND status='submitted'
        RETURNING *
        """,
        (st, company, review_id),
    )
    row = cur.fetchone()
    if not row:
        return {"ok": False, "error": "ack_failed"}
    _audit(
        cur,
        company_code=company,
        action="review_acknowledged" if st == "acknowledged" else "review_ack_declined",
        actor_phone=actor_phone,
        subject_type="review",
        subject_id=str(review_id),
    )
    return {"ok": True, "review": dict(row), **honesty_payload(company_code=company)}


def mark_calibration_ready(
    cur: Any, *, company_code: str, cycle_id: str, actor_phone: str, reason: str
) -> dict[str, Any]:
    enabled = module_enabled_for_company(cur, company_code)
    if not enabled.get("ok"):
        return enabled
    company = company_code_norm(company_code)
    cur.execute(
        """
        UPDATE perf_review_cycles
           SET status='calibration_ready', row_version=row_version+1, updated_at=now()
         WHERE company_code=%s AND cycle_id=%s AND status='in_progress'
        RETURNING *
        """,
        (company, cycle_id),
    )
    row = cur.fetchone()
    if not row:
        return {"ok": False, "error": "cycle_not_in_progress"}
    _audit(
        cur,
        company_code=company,
        action="cycle_calibration_ready",
        actor_phone=actor_phone,
        reason=reason,
        subject_type="review_cycle",
        subject_id=str(cycle_id),
    )
    return {"ok": True, "cycle": dict(row), **honesty_payload(company_code=company)}


def close_cycle(
    cur: Any, *, company_code: str, cycle_id: str, actor_phone: str, reason: str
) -> dict[str, Any]:
    """Close authority boundary — set final from manager without erasing self/manager/360 layers."""
    if not str(reason or "").strip():
        return {"ok": False, "error": "audit_reason_required"}
    enabled = module_enabled_for_company(cur, company_code)
    if not enabled.get("ok"):
        return enabled
    company = company_code_norm(company_code)
    cycle = get_cycle(cur, company_code=company, cycle_id=cycle_id)
    if not cycle:
        return {"ok": False, "error": "cycle_not_found"}
    if cycle["status"] == "closed":
        return {"ok": True, "idempotent_duplicate_close": True, "cycle": cycle}
    if cycle["status"] not in ("in_progress", "calibration_ready"):
        return {"ok": False, "error": "cycle_not_closable", "status": cycle["status"]}

    cur.execute(
        "SELECT DISTINCT employee_key FROM perf_cycle_participants WHERE cycle_id=%s",
        (cycle_id,),
    )
    subjects = [str(dict(r)["employee_key"]) for r in (cur.fetchall() or [])]
    for subj in subjects:
        cur.execute(
            """
            SELECT review_id, overall_rating_value, overall_rating_label, rationale
              FROM perf_reviews
             WHERE cycle_id=%s AND subject_employee_key=%s AND reviewer_role='manager'
               AND status IN ('submitted','acknowledged','declined_ack')
             ORDER BY submitted_at DESC NULLS LAST LIMIT 1
            """,
            (cycle_id, subj),
        )
        mgr = cur.fetchone()
        cur.execute(
            """
            SELECT review_id FROM perf_reviews
             WHERE cycle_id=%s AND subject_employee_key=%s AND reviewer_role='self'
               AND status IN ('submitted','acknowledged','declined_ack')
             ORDER BY submitted_at DESC NULLS LAST LIMIT 1
            """,
            (cycle_id, subj),
        )
        self_r = cur.fetchone()
        if mgr:
            mgr = dict(mgr)
            cur.execute(
                """
                INSERT INTO perf_review_final_ratings (
                  company_code, cycle_id, subject_employee_key,
                  final_rating_value, final_rating_label, source,
                  self_review_id, manager_review_id, rationale, created_by_phone
                ) VALUES (%s,%s,%s,%s,%s,'manager_close',%s,%s,%s,%s)
                ON CONFLICT (cycle_id, subject_employee_key) DO NOTHING
                """,
                (
                    company,
                    cycle_id,
                    subj,
                    mgr.get("overall_rating_value"),
                    mgr.get("overall_rating_label"),
                    str(dict(self_r)["review_id"]) if self_r else None,
                    str(mgr["review_id"]),
                    mgr.get("rationale"),
                    _digits(actor_phone),
                ),
            )

    cur.execute(
        """
        UPDATE perf_review_cycles
           SET status='closed', closed_at=now(), closed_by_phone=%s,
               row_version=row_version+1, updated_at=now()
         WHERE company_code=%s AND cycle_id=%s
           AND status IN ('in_progress','calibration_ready')
        RETURNING *
        """,
        (_digits(actor_phone), company, cycle_id),
    )
    row = cur.fetchone()
    if not row:
        return {"ok": False, "error": "close_failed"}
    _audit(
        cur,
        company_code=company,
        action="cycle_closed",
        actor_phone=actor_phone,
        reason=reason,
        subject_type="review_cycle",
        subject_id=str(cycle_id),
        payload={"final_source": "manager_close", "layers_preserved": True},
    )
    return {
        "ok": True,
        "cycle": dict(row),
        "layers_preserved": True,
        **honesty_payload(company_code=company),
    }


def attempt_reopen_closed_cycle(
    cur: Any, *, company_code: str, cycle_id: str
) -> dict[str, Any]:
    cycle = get_cycle(cur, company_code=company_code, cycle_id=cycle_id)
    if not cycle:
        return {"ok": False, "error": "cycle_not_found"}
    if cycle.get("status") == "closed":
        return {
            "ok": False,
            "error": "closed_cycle_cannot_silently_reopen",
            "message": "Closed cycles require explicit audited reopen policy (default forbidden in C2).",
        }
    return {"ok": False, "error": "not_closed"}


def get_layer_ratings(
    cur: Any, *, company_code: str, cycle_id: str, subject_employee_key: str
) -> dict[str, Any]:
    """Return separate self/manager/360/final layers — never collapsed."""
    company = company_code_norm(company_code)
    cur.execute(
        """
        SELECT review_id, reviewer_role, overall_rating_value, rationale, status, submitted_at
          FROM perf_reviews
         WHERE company_code=%s AND cycle_id=%s AND subject_employee_key=%s
           AND status IN ('submitted','acknowledged','declined_ack')
        """,
        (company, cycle_id, subject_employee_key),
    )
    reviews = [dict(r) for r in (cur.fetchall() or [])]
    cur.execute(
        """
        SELECT * FROM perf_review_final_ratings
         WHERE company_code=%s AND cycle_id=%s AND subject_employee_key=%s
        """,
        (company, cycle_id, subject_employee_key),
    )
    final = cur.fetchone()
    layers = {
        "self": next((r for r in reviews if r["reviewer_role"] == "self"), None),
        "manager": next((r for r in reviews if r["reviewer_role"] == "manager"), None),
        "additional_360": [r for r in reviews if r["reviewer_role"] in ("peer", "subordinate", "stakeholder", "additional")],
        "final": dict(final) if final else None,
    }
    return {
        "ok": True,
        "layers": layers,
        "collapsed": False,
        **honesty_payload(company_code=company),
    }
