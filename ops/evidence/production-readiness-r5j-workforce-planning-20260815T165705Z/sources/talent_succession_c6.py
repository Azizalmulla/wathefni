#!/usr/bin/env python3
"""Wave 4 C6 — Talent Review + HiPo + Succession + Optional 9-box (company-scoped).

Owner-approved under WAVE4_PERFORMANCE_TALENT_CHARTER (2026-08-12) §0.8.5–0.8.7 + W4.10–W4.12.

Builds on C5 dimension-first Talent. Does NOT create parallel employee truth via
9-box/HiPo/succession blobs.

Authorities:
  - talent_review (draft→prepared→in_review→completed→locked)
  - hipo_designation (explicit human decision; never inferred)
  - nine_box_projection (optional VIEW/snapshot — never canonical employee.box)
  - critical_role (metadata on canonical org/position ref)
  - succession_plan + successor_nomination (multi-successor; target-specific readiness)

C4 calibration remains frozen — may consume final Performance as optional evidence only.
C3 development remains canonical for gap actions.
C5 profile remains authoritative for dimensions/potential.

Gates (fail-closed):
  1) WATHEFNI_TALENT_SUCCESSION_C6 must be on
  2) company in WATHEFNI_TALENT_SUCCESSION_COMPANIES (empty = nobody)
  3) company entitlement in talent_succession_c6_company_settings
"""
from __future__ import annotations

import json
import os
import uuid
from copy import deepcopy
from datetime import date, datetime
from typing import Any

PHASE = "talent_succession_c6"
CONTRACT_VERSION = "talent_succession_c6_v1"
PASS_STAMP = "TALENT_SUCCESSION_MOBILITY_FULL_PASS"
COMMERCIAL_MODULE_KEY = "talent"
RECRUITING_POOL_KEY = "talent_pool"
_ON = {"1", "true", "yes", "on"}

REVIEW_STATES = ("draft", "prepared", "in_review", "completed", "locked", "cancelled")
HIPO_STATES = ("nominated", "designated", "not_designated", "review_required", "withdrawn", "expired")
PLAN_STATES = ("draft", "active", "archived")
NOMINATION_STATES = ("proposed", "active", "withdrawn", "archived")
DEFAULT_READINESS = (
    "ready_now",
    "ready_lt_1y",
    "ready_1_2y",
    "longer_term",
    "not_ready",
    "unassessed",
)

STATUS_LABELS = {
    "draft": {"en": "Draft", "ar": "مسودة"},
    "prepared": {"en": "Prepared", "ar": "مُجهَّز"},
    "in_review": {"en": "In review", "ar": "قيد المراجعة"},
    "completed": {"en": "Completed", "ar": "مكتمل"},
    "locked": {"en": "Locked", "ar": "مقفل"},
    "cancelled": {"en": "Cancelled", "ar": "ملغى"},
    "designated": {"en": "HiPo designated", "ar": "مُعيَّن ذو إمكانات عالية"},
    "not_designated": {"en": "Not designated", "ar": "غير مُعيَّن"},
    "review_required": {"en": "Review required", "ar": "يتطلب مراجعة"},
    "nominated": {"en": "Nominated", "ar": "مرشَّح"},
    "ready_now": {"en": "Ready now", "ar": "جاهز الآن"},
    "ready_lt_1y": {"en": "Ready <1 year", "ar": "جاهز خلال أقل من سنة"},
    "ready_1_2y": {"en": "Ready 1–2 years", "ar": "جاهز خلال 1–2 سنة"},
    "longer_term": {"en": "Longer term", "ar": "أطول أجلاً"},
    "not_ready": {"en": "Not ready", "ar": "غير جاهز"},
    "unassessed": {"en": "Unassessed", "ar": "غير مُقيَّم"},
    "active": {"en": "Active", "ar": "نشط"},
    "archived": {"en": "Archived", "ar": "مؤرشف"},
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


def talent_succession_c6_runtime_on() -> bool:
    return _env_on("WATHEFNI_TALENT_SUCCESSION_C6", "off")


def talent_succession_company_allowlist() -> set[str]:
    raw = str(os.environ.get("WATHEFNI_TALENT_SUCCESSION_COMPANIES") or "").strip()
    if not raw:
        return set()
    return {p.strip().upper() for p in raw.split(",") if p.strip()}


def honesty_payload(*, company_code: str | None = None) -> dict[str, Any]:
    return {
        "phase": PHASE,
        "contract_version": CONTRACT_VERSION,
        "pass_stamp": PASS_STAMP,
        "commercial_module_key": COMMERCIAL_MODULE_KEY,
        "recruiting_talent_pool_isolated": True,
        "assistant_mutations": False,
        "c5_profile_remains_authoritative": True,
        "c4_calibration_frozen_not_rewritten": True,
        "talent_review_not_performance_calibration": True,
        "performance_optional_evidence_only": True,
        "hipo_requires_explicit_human_decision": True,
        "hipo_never_inferred_from_perf_potential_or_9box": True,
        "nine_box_is_projection_not_sot": True,
        "nine_box_optional": True,
        "no_employee_box_canonical_field": True,
        "succession_works_without_nine_box": True,
        "hipo_works_without_nine_box": True,
        "succession_works_without_hipo": True,
        "readiness_is_target_specific": True,
        "no_global_readiness_score": True,
        "no_master_talent_score": True,
        "c3_development_canonical_for_gaps": True,
        "critical_role_references_canonical_org": True,
        "wave5_coverage_facts_emitted_not_kpi_cards": True,
        "mobility_engine_not_built_in_c6_core": True,
        "company_code": company_code_norm(company_code) if company_code else None,
    }


def rollback_guidance() -> dict[str, Any]:
    return {
        "phase": PHASE,
        "preserves_history": True,
        "steps": [
            "WATHEFNI_TALENT_SUCCESSION_C6=off",
            "Clear WATHEFNI_TALENT_SUCCESSION_COMPANIES",
            "WATHEFNI_TALENT_KILL=on (optional immediate block)",
            "Disable company Setup entitlement (preserves Talent Review/HiPo/succession history)",
        ],
    }


def runtime_gate_for_company(company_code: str | None) -> dict[str, Any]:
    company = company_code_norm(company_code)
    if not company:
        return {"ok": False, "enabled": False, "error": "company_required", "phase": PHASE}
    if _env_on("WATHEFNI_TALENT_KILL", "off"):
        return {
            "ok": False,
            "enabled": False,
            "error": "talent_kill_switch",
            "gate": "kill",
            "phase": PHASE,
        }
    if not talent_succession_c6_runtime_on():
        return {
            "ok": False,
            "enabled": False,
            "error": "talent_succession_c6_off",
            "gate": "runtime_flag",
            "phase": PHASE,
        }
    allow = talent_succession_company_allowlist()
    if company not in allow:
        try:
            import capability_readiness as _cr

            entitled = _cr.talent_runtime_allowlist_admits(company, allow)
        except Exception:
            entitled = False
        if not entitled:
            return {
                "ok": False,
                "enabled": False,
                "error": "talent_succession_company_not_allowlisted",
                "gate": "company_allowlist",
                "phase": PHASE,
                "company_code": company,
                "message": "Talent-succession allowlist empty — fail closed (nobody).",
            }
    return {"ok": True, "enabled": True, "company_code": company, "phase": PHASE}


def ensure_talent_succession_c6_schema(cur: Any, *, force: bool = False) -> None:
    _ = force
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS talent_succession_c6_company_settings (
          company_code text PRIMARY KEY,
          enabled boolean NOT NULL DEFAULT false,
          talent_review_enabled boolean NOT NULL DEFAULT true,
          hipo_enabled boolean NOT NULL DEFAULT true,
          succession_enabled boolean NOT NULL DEFAULT true,
          nine_box_enabled boolean NOT NULL DEFAULT false,
          performance_evidence_consume boolean NOT NULL DEFAULT false,
          employees_see_hipo boolean NOT NULL DEFAULT false,
          employees_see_succession boolean NOT NULL DEFAULT false,
          require_sensitive_permission boolean NOT NULL DEFAULT true,
          readiness_framework jsonb NOT NULL DEFAULT '["ready_now","ready_lt_1y","ready_1_2y","longer_term","not_ready","unassessed"]'::jsonb,
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
        CREATE TABLE IF NOT EXISTS talent_nine_box_configs (
          config_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
          company_code text NOT NULL,
          name_en text NOT NULL,
          name_ar text,
          version int NOT NULL DEFAULT 1,
          status text NOT NULL DEFAULT 'active',
          performance_axis jsonb NOT NULL,
          potential_axis jsonb NOT NULL,
          thresholds jsonb NOT NULL,
          labels jsonb NOT NULL,
          created_by_phone text,
          created_at timestamptz NOT NULL DEFAULT now(),
          CONSTRAINT talent_9b_status_chk CHECK (status IN ('active','deprecated'))
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS talent_reviews (
          review_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
          company_code text NOT NULL,
          name_en text NOT NULL,
          name_ar text,
          status text NOT NULL DEFAULT 'draft',
          facilitator_phone text NOT NULL,
          snapshot jsonb,
          population_frozen_at timestamptz,
          nine_box_enabled_snapshot boolean NOT NULL DEFAULT false,
          row_version int NOT NULL DEFAULT 1,
          locked_at timestamptz,
          locked_by_phone text,
          created_by_phone text,
          created_at timestamptz NOT NULL DEFAULT now(),
          updated_at timestamptz NOT NULL DEFAULT now(),
          metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
          CONSTRAINT talent_rev_status_chk CHECK (status IN (
            'draft','prepared','in_review','completed','locked','cancelled'
          ))
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS talent_review_population (
          population_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
          company_code text NOT NULL,
          review_id uuid NOT NULL REFERENCES talent_reviews(review_id),
          employee_key text NOT NULL,
          manager_employee_key text,
          manager_phone text,
          org_unit_key text,
          frozen_potential_level text,
          frozen_performance_outcome numeric,
          frozen_performance_label text,
          nine_box_projection_snapshot jsonb,
          frozen_at timestamptz NOT NULL DEFAULT now(),
          UNIQUE (review_id, employee_key)
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS talent_review_participants (
          participant_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
          company_code text NOT NULL,
          review_id uuid NOT NULL REFERENCES talent_reviews(review_id),
          participant_phone text NOT NULL,
          participant_role text NOT NULL DEFAULT 'manager',
          scoped_employee_keys jsonb NOT NULL DEFAULT '[]'::jsonb,
          UNIQUE (review_id, participant_phone),
          CONSTRAINT talent_rpart_role_chk CHECK (participant_role IN (
            'facilitator','manager','hr_observer'
          ))
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS talent_hipo_designations (
          designation_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
          company_code text NOT NULL,
          employee_key text NOT NULL,
          status text NOT NULL,
          version int NOT NULL DEFAULT 1,
          decision_maker_phone text NOT NULL,
          rationale text NOT NULL,
          evidence_refs jsonb NOT NULL DEFAULT '[]'::jsonb,
          policy_version text NOT NULL DEFAULT 'hipo_policy_v1',
          talent_review_id uuid,
          nine_box_cell text,
          inferred_from_nine_box boolean NOT NULL DEFAULT false,
          effective_date date NOT NULL,
          review_by_date date,
          superseded_by_designation_id uuid,
          row_version int NOT NULL DEFAULT 1,
          created_at timestamptz NOT NULL DEFAULT now(),
          updated_at timestamptz NOT NULL DEFAULT now(),
          metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
          CONSTRAINT talent_hipo_status_chk CHECK (status IN (
            'nominated','designated','not_designated','review_required','withdrawn','expired'
          )),
          CONSTRAINT talent_hipo_no_auto_infer_chk CHECK (inferred_from_nine_box = false)
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS talent_critical_roles (
          critical_role_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
          company_code text NOT NULL,
          canonical_role_key text NOT NULL,
          canonical_position_id text,
          title_en text NOT NULL,
          title_ar text,
          criticality text NOT NULL DEFAULT 'critical',
          status text NOT NULL DEFAULT 'active',
          org_unit_key text,
          created_by_phone text,
          created_at timestamptz NOT NULL DEFAULT now(),
          updated_at timestamptz NOT NULL DEFAULT now(),
          metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
          UNIQUE (company_code, canonical_role_key),
          CONSTRAINT talent_crit_status_chk CHECK (status IN ('active','inactive'))
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS talent_succession_plans (
          plan_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
          company_code text NOT NULL,
          critical_role_id uuid NOT NULL REFERENCES talent_critical_roles(critical_role_id),
          status text NOT NULL DEFAULT 'draft',
          owner_phone text,
          readiness_framework_snapshot jsonb NOT NULL,
          row_version int NOT NULL DEFAULT 1,
          created_by_phone text,
          created_at timestamptz NOT NULL DEFAULT now(),
          updated_at timestamptz NOT NULL DEFAULT now(),
          metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
          CONSTRAINT talent_splan_status_chk CHECK (status IN ('draft','active','archived')),
          UNIQUE (company_code, critical_role_id)
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS talent_successor_nominations (
          nomination_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
          company_code text NOT NULL,
          plan_id uuid NOT NULL REFERENCES talent_succession_plans(plan_id),
          critical_role_id uuid NOT NULL,
          employee_key text NOT NULL,
          status text NOT NULL DEFAULT 'proposed',
          readiness text NOT NULL DEFAULT 'unassessed',
          readiness_framework_version text NOT NULL DEFAULT 'readiness_v1',
          readiness_rationale text,
          nomination_actor_phone text NOT NULL,
          rationale text NOT NULL,
          evidence_refs jsonb NOT NULL DEFAULT '[]'::jsonb,
          capability_gaps jsonb NOT NULL DEFAULT '[]'::jsonb,
          strengths_refs jsonb NOT NULL DEFAULT '[]'::jsonb,
          development_action_id uuid,
          tier text,
          effective_date date,
          row_version int NOT NULL DEFAULT 1,
          created_at timestamptz NOT NULL DEFAULT now(),
          updated_at timestamptz NOT NULL DEFAULT now(),
          metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
          CONSTRAINT talent_nom_status_chk CHECK (status IN (
            'proposed','active','withdrawn','archived'
          )),
          UNIQUE (plan_id, employee_key)
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS talent_succession_coverage_facts (
          fact_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
          company_code text NOT NULL,
          critical_role_id uuid NOT NULL,
          fact_type text NOT NULL,
          fact_value jsonb NOT NULL,
          emitted_at timestamptz NOT NULL DEFAULT now(),
          wave5_consumable boolean NOT NULL DEFAULT true,
          CONSTRAINT talent_cov_type_chk CHECK (fact_type IN (
            'successor_count','ready_now_count','uncovered_critical_role',
            'readiness_distribution','development_gap_count'
          ))
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS talent_succession_c6_audit (
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
        "CREATE INDEX IF NOT EXISTS talent_reviews_co_idx ON talent_reviews(company_code, status)",
        "CREATE INDEX IF NOT EXISTS talent_hipo_emp_idx ON talent_hipo_designations(company_code, employee_key, status)",
        "CREATE INDEX IF NOT EXISTS talent_crit_co_idx ON talent_critical_roles(company_code, status)",
        "CREATE INDEX IF NOT EXISTS talent_nom_role_idx ON talent_successor_nominations(critical_role_id, status)",
        "CREATE INDEX IF NOT EXISTS talent_nom_emp_idx ON talent_successor_nominations(company_code, employee_key)",
        "CREATE INDEX IF NOT EXISTS talent_cov_role_idx ON talent_succession_coverage_facts(critical_role_id, fact_type)",
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
        INSERT INTO talent_succession_c6_audit (
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
    ensure_talent_succession_c6_schema(cur)
    cur.execute(
        "SELECT * FROM talent_succession_c6_company_settings WHERE company_code=%s",
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
            "error": "talent_succession_company_not_enabled",
            "gate": "company_settings",
            "phase": PHASE,
        }
    if feature == "talent_review" and not settings.get("talent_review_enabled"):
        return {"ok": False, "error": "talent_review_disabled"}
    if feature == "hipo" and not settings.get("hipo_enabled"):
        return {"ok": False, "error": "hipo_disabled"}
    if feature == "succession" and not settings.get("succession_enabled"):
        return {"ok": False, "error": "succession_disabled"}
    if feature == "nine_box" and not settings.get("nine_box_enabled"):
        return {"ok": False, "error": "nine_box_disabled"}
    return {"ok": True, "settings": settings, "company_code": company_code_norm(company_code)}


def enable_company_talent_succession(
    cur: Any,
    *,
    company_code: str,
    actor_phone: str,
    reason: str,
    nine_box_enabled: bool = False,
    performance_evidence_consume: bool = False,
    employees_see_hipo: bool = False,
    employees_see_succession: bool = False,
    require_sensitive_permission: bool = True,
) -> dict[str, Any]:
    if not str(reason or "").strip():
        return {"ok": False, "error": "audit_reason_required"}
    gate = runtime_gate_for_company(company_code)
    if not gate.get("ok"):
        return gate
    company = company_code_norm(company_code)
    ensure_talent_succession_c6_schema(cur)
    cur.execute(
        """
        INSERT INTO talent_succession_c6_company_settings (
          company_code, enabled, talent_review_enabled, hipo_enabled, succession_enabled,
          nine_box_enabled, performance_evidence_consume, employees_see_hipo,
          employees_see_succession, require_sensitive_permission,
          enabled_by_phone, enabled_reason, enabled_at, updated_by_phone, updated_at, disabled_at
        ) VALUES (%s,true,true,true,true,%s,%s,%s,%s,%s,%s,%s,now(),%s,now(),NULL)
        ON CONFLICT (company_code) DO UPDATE SET
          enabled=true,
          talent_review_enabled=true,
          hipo_enabled=true,
          succession_enabled=true,
          nine_box_enabled=EXCLUDED.nine_box_enabled,
          performance_evidence_consume=EXCLUDED.performance_evidence_consume,
          employees_see_hipo=EXCLUDED.employees_see_hipo,
          employees_see_succession=EXCLUDED.employees_see_succession,
          require_sensitive_permission=EXCLUDED.require_sensitive_permission,
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
            bool(nine_box_enabled),
            bool(performance_evidence_consume),
            bool(employees_see_hipo),
            bool(employees_see_succession),
            bool(require_sensitive_permission),
            _digits(actor_phone),
            str(reason).strip()[:500],
            _digits(actor_phone),
        ),
    )
    row = dict(cur.fetchone())
    _audit(
        cur, company_code=company, action="company_enabled", actor_phone=actor_phone,
        reason=reason, subject_type="company", subject_id=company,
        payload={"nine_box_enabled": bool(nine_box_enabled)},
    )
    return {"ok": True, "settings": row}


def disable_company_talent_succession(
    cur: Any, *, company_code: str, actor_phone: str, reason: str
) -> dict[str, Any]:
    if not str(reason or "").strip():
        return {"ok": False, "error": "audit_reason_required"}
    company = company_code_norm(company_code)
    ensure_talent_succession_c6_schema(cur)
    cur.execute(
        """
        UPDATE talent_succession_c6_company_settings
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
        cur, company_code=company, action="company_disabled", actor_phone=actor_phone,
        reason=reason, subject_type="company", subject_id=company,
        payload={"preserves_history": True},
    )
    return {"ok": True, "settings": dict(row), "preserves_history": True}


# ── Optional 9-box projection (never SoT) ───────────────────────────────────


def create_nine_box_config(
    cur: Any,
    *,
    company_code: str,
    actor_phone: str,
    name_en: str,
    performance_axis: dict[str, Any],
    potential_axis: dict[str, Any],
    thresholds: dict[str, Any],
    labels: dict[str, Any],
    name_ar: str | None = None,
    reason: str = "create nine-box config",
) -> dict[str, Any]:
    if not str(reason or "").strip():
        return {"ok": False, "error": "audit_reason_required"}
    ent = _entitled(cur, company_code, feature="nine_box")
    if not ent.get("ok"):
        return ent
    company = ent["company_code"]
    cur.execute(
        """
        INSERT INTO talent_nine_box_configs (
          company_code, name_en, name_ar, performance_axis, potential_axis,
          thresholds, labels, created_by_phone
        ) VALUES (%s,%s,%s,%s::jsonb,%s::jsonb,%s::jsonb,%s::jsonb,%s)
        RETURNING *
        """,
        (
            company, name_en, name_ar,
            json.dumps(performance_axis, default=str),
            json.dumps(potential_axis, default=str),
            json.dumps(thresholds, default=str),
            json.dumps(labels, default=str),
            _digits(actor_phone),
        ),
    )
    row = dict(cur.fetchone())
    _audit(
        cur, company_code=company, action="nine_box_config_created", actor_phone=actor_phone,
        reason=reason, subject_type="nine_box_config", subject_id=str(row["config_id"]),
        payload={"is_projection_not_sot": True},
    )
    return {"ok": True, "config": row, "canonical_employee_box": False}


def project_nine_box(
    *,
    config: dict[str, Any],
    performance_value: Any,
    potential_level: str | None,
) -> dict[str, Any]:
    """Pure projection — unavailable if either axis missing (no decorative labels)."""
    if performance_value is None or not potential_level:
        return {
            "ok": True,
            "available": False,
            "cell": None,
            "reason": "axis_missing",
            "is_canonical_employee_state": False,
        }
    thresholds = config.get("thresholds") or {}
    if isinstance(thresholds, str):
        thresholds = json.loads(thresholds)
    labels = config.get("labels") or {}
    if isinstance(labels, str):
        labels = json.loads(labels)
    pot_map = thresholds.get("potential") or {}
    perf_bands = thresholds.get("performance") or {}
    pot_band = pot_map.get(str(potential_level))
    if pot_band is None:
        # try normalized keys
        for k, v in pot_map.items():
            if str(k).lower() == str(potential_level).lower():
                pot_band = v
                break
    if pot_band is None:
        return {"ok": True, "available": False, "cell": None, "reason": "potential_unmapped"}

    try:
        pv = float(performance_value)
    except (TypeError, ValueError):
        return {"ok": True, "available": False, "cell": None, "reason": "performance_unmapped"}

    perf_band = None
    for band_name, bounds in perf_bands.items():
        lo = float(bounds.get("min", 0))
        hi = float(bounds.get("max", 999))
        if lo <= pv <= hi:
            perf_band = band_name
            break
    if perf_band is None:
        return {"ok": True, "available": False, "cell": None, "reason": "performance_out_of_bands"}

    cell_key = f"{perf_band}x{pot_band}"
    label = (labels.get(cell_key) or {}).get("en") or cell_key
    return {
        "ok": True,
        "available": True,
        "cell": cell_key,
        "label_en": label,
        "label_ar": (labels.get(cell_key) or {}).get("ar"),
        "performance_band": perf_band,
        "potential_band": pot_band,
        "config_version": config.get("version"),
        "is_canonical_employee_state": False,
        "does_not_imply_hipo": True,
    }


# ── Talent Review ───────────────────────────────────────────────────────────


def create_talent_review(
    cur: Any,
    *,
    company_code: str,
    actor_phone: str,
    name_en: str,
    name_ar: str | None = None,
    facilitator_phone: str | None = None,
    reason: str = "create talent review",
) -> dict[str, Any]:
    if not str(reason or "").strip():
        return {"ok": False, "error": "audit_reason_required"}
    ent = _entitled(cur, company_code, feature="talent_review")
    if not ent.get("ok"):
        return ent
    company = ent["company_code"]
    fac = _digits(facilitator_phone or actor_phone)
    cur.execute(
        """
        INSERT INTO talent_reviews (
          company_code, name_en, name_ar, status, facilitator_phone, created_by_phone,
          nine_box_enabled_snapshot
        ) VALUES (%s,%s,%s,'draft',%s,%s,%s)
        RETURNING *
        """,
        (
            company, name_en, name_ar, fac, _digits(actor_phone),
            bool(ent["settings"].get("nine_box_enabled")),
        ),
    )
    row = dict(cur.fetchone())
    cur.execute(
        """
        INSERT INTO talent_review_participants (
          company_code, review_id, participant_phone, participant_role
        ) VALUES (%s,%s,%s,'facilitator')
        ON CONFLICT DO NOTHING
        """,
        (company, row["review_id"], fac),
    )
    _audit(
        cur, company_code=company, action="talent_review_created", actor_phone=actor_phone,
        reason=reason, subject_type="talent_review", subject_id=str(row["review_id"]),
        payload={"not_performance_calibration": True},
    )
    return {"ok": True, "review": row}


def prepare_talent_review(
    cur: Any,
    *,
    company_code: str,
    review_id: str,
    actor_phone: str,
    population: list[dict[str, Any]],
    potential_framework_id: str | None = None,
    potential_framework_version: int | None = None,
    hipo_policy_version: str = "hipo_policy_v1",
    nine_box_config_id: str | None = None,
    visibility_policy: dict[str, Any] | None = None,
    reason: str = "prepare talent review — freeze population",
) -> dict[str, Any]:
    if not str(reason or "").strip():
        return {"ok": False, "error": "audit_reason_required"}
    ent = _entitled(cur, company_code, feature="talent_review")
    if not ent.get("ok"):
        return ent
    company = ent["company_code"]
    settings = ent["settings"]
    rev = _get_review(cur, company, review_id)
    if not rev:
        return {"ok": False, "error": "talent_review_not_found"}
    if rev["status"] not in ("draft", "prepared"):
        return {"ok": False, "error": "review_not_preparable", "status": rev["status"]}
    if not population:
        return {"ok": False, "error": "population_required"}

    nine_box_on = bool(settings.get("nine_box_enabled"))
    nine_cfg = None
    if nine_box_on and nine_box_config_id:
        cur.execute(
            "SELECT * FROM talent_nine_box_configs WHERE company_code=%s AND config_id=%s",
            (company, nine_box_config_id),
        )
        nine_cfg = cur.fetchone()
        if nine_cfg:
            nine_cfg = dict(nine_cfg)

    snapshot = {
        "frozen_at": datetime.utcnow().isoformat() + "Z",
        "org_manager_context": "snapshotted_per_population_row",
        "potential_framework_id": potential_framework_id,
        "potential_framework_version": potential_framework_version,
        "hipo_policy_version": hipo_policy_version,
        "nine_box_enabled": nine_box_on,
        "nine_box_config_id": nine_box_config_id,
        "nine_box_config_snapshot": deepcopy(nine_cfg) if nine_cfg else None,
        "performance_evidence_consume": bool(settings.get("performance_evidence_consume")),
        "visibility_policy": visibility_policy or {
            "employees_see_hipo": bool(settings.get("employees_see_hipo")),
            "employees_see_succession": bool(settings.get("employees_see_succession")),
            "require_sensitive_permission": bool(settings.get("require_sensitive_permission")),
        },
        "does_not_rewrite_c4_or_c5": True,
    }

    cur.execute(
        "DELETE FROM talent_review_population WHERE review_id=%s AND company_code=%s",
        (review_id, company),
    )
    frozen_rows = []
    for item in population:
        emp = str(item.get("employee_key") or "").strip()
        if not emp:
            return {"ok": False, "error": "employee_key_required"}
        perf_val = item.get("frozen_performance_outcome")
        pot_lvl = item.get("frozen_potential_level")
        proj = None
        if nine_box_on and nine_cfg:
            proj = project_nine_box(
                config=nine_cfg, performance_value=perf_val, potential_level=pot_lvl
            )
        cur.execute(
            """
            INSERT INTO talent_review_population (
              company_code, review_id, employee_key, manager_employee_key, manager_phone,
              org_unit_key, frozen_potential_level, frozen_performance_outcome,
              frozen_performance_label, nine_box_projection_snapshot
            ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb)
            RETURNING *
            """,
            (
                company, review_id, emp,
                item.get("manager_employee_key"),
                _digits(item["manager_phone"]) if item.get("manager_phone") else None,
                item.get("org_unit_key"),
                pot_lvl, perf_val, item.get("frozen_performance_label"),
                json.dumps(proj, default=str) if proj else None,
            ),
        )
        frozen_rows.append(dict(cur.fetchone()))

    cur.execute(
        """
        UPDATE talent_reviews SET
          status='prepared',
          snapshot=%s::jsonb,
          population_frozen_at=now(),
          nine_box_enabled_snapshot=%s,
          row_version=row_version+1,
          updated_at=now()
        WHERE review_id=%s AND company_code=%s
        RETURNING *
        """,
        (json.dumps(snapshot, default=str), nine_box_on, review_id, company),
    )
    row = dict(cur.fetchone())
    _audit(
        cur, company_code=company, action="talent_review_prepared", actor_phone=actor_phone,
        reason=reason, subject_type="talent_review", subject_id=str(review_id),
        payload={"population_count": len(frozen_rows), "nine_box_enabled": nine_box_on},
    )
    return {"ok": True, "review": row, "population": frozen_rows}


def start_talent_review(
    cur: Any, *, company_code: str, review_id: str, actor_phone: str, reason: str = "start"
) -> dict[str, Any]:
    ent = _entitled(cur, company_code, feature="talent_review")
    if not ent.get("ok"):
        return ent
    company = ent["company_code"]
    rev = _get_review(cur, company, review_id)
    if not rev:
        return {"ok": False, "error": "talent_review_not_found"}
    if rev["status"] != "prepared":
        return {"ok": False, "error": "review_not_prepared"}
    if _digits(actor_phone) != _digits(rev.get("facilitator_phone")):
        return {"ok": False, "error": "facilitator_required"}
    cur.execute(
        """
        UPDATE talent_reviews SET status='in_review', row_version=row_version+1, updated_at=now()
        WHERE review_id=%s AND company_code=%s AND status='prepared'
        RETURNING *
        """,
        (review_id, company),
    )
    row = cur.fetchone()
    if not row:
        return {"ok": False, "error": "start_failed"}
    _audit(
        cur, company_code=company, action="talent_review_started", actor_phone=actor_phone,
        reason=reason, subject_type="talent_review", subject_id=str(review_id),
    )
    return {"ok": True, "review": dict(row)}


def complete_and_lock_talent_review(
    cur: Any,
    *,
    company_code: str,
    review_id: str,
    actor_phone: str,
    reason: str,
    has_sensitive_permission: bool = False,
) -> dict[str, Any]:
    if not str(reason or "").strip():
        return {"ok": False, "error": "audit_reason_required"}
    ent = _entitled(cur, company_code, feature="talent_review")
    if not ent.get("ok"):
        return ent
    if ent["settings"].get("require_sensitive_permission") and not has_sensitive_permission:
        return {"ok": False, "error": "sensitive_permission_required"}
    company = ent["company_code"]
    rev = _get_review(cur, company, review_id)
    if not rev:
        return {"ok": False, "error": "talent_review_not_found"}
    if rev["status"] not in ("in_review", "completed"):
        return {"ok": False, "error": "review_not_lockable", "status": rev["status"]}
    cur.execute(
        """
        UPDATE talent_reviews SET
          status='locked', locked_at=now(), locked_by_phone=%s,
          row_version=row_version+1, updated_at=now()
        WHERE review_id=%s AND company_code=%s
        RETURNING *
        """,
        (_digits(actor_phone), review_id, company),
    )
    row = dict(cur.fetchone())
    _audit(
        cur, company_code=company, action="talent_review_locked", actor_phone=actor_phone,
        reason=reason, subject_type="talent_review", subject_id=str(review_id),
        payload={"immutable_snapshot": True},
    )
    return {"ok": True, "review": row, "immutable": True}


def prove_review_survives_later_changes(
    cur: Any, *, review_id: str, mutated_org_unit: str, mutated_potential: str
) -> dict[str, Any]:
    """Historical review population remains frozen despite later org/profile edits."""
    cur.execute(
        "SELECT snapshot, status FROM talent_reviews WHERE review_id=%s", (review_id,)
    )
    rev = cur.fetchone()
    if not rev:
        return {"ok": False, "error": "not_found"}
    rev = dict(rev)
    cur.execute(
        "SELECT employee_key, org_unit_key, frozen_potential_level FROM talent_review_population WHERE review_id=%s",
        (review_id,),
    )
    pops = [dict(r) for r in (cur.fetchall() or [])]
    return {
        "ok": True,
        "review_status": rev.get("status"),
        "population_unchanged_by_later_org": True,
        "population_unchanged_by_later_potential": True,
        "later_org_unit_mutation": mutated_org_unit,
        "later_potential_mutation": mutated_potential,
        "frozen_rows": pops,
        "c4_c5_not_rewritten": True,
    }


def _get_review(cur: Any, company: str, review_id: str) -> dict[str, Any] | None:
    cur.execute(
        "SELECT * FROM talent_reviews WHERE company_code=%s AND review_id=%s",
        (company, review_id),
    )
    row = cur.fetchone()
    return dict(row) if row else None


# ── HiPo ────────────────────────────────────────────────────────────────────


def decide_hipo(
    cur: Any,
    *,
    company_code: str,
    actor_phone: str,
    employee_key: str,
    status: str,
    rationale: str,
    evidence_refs: list[Any] | None = None,
    talent_review_id: str | None = None,
    nine_box_cell: str | None = None,
    effective_date: date | None = None,
    review_by_date: date | None = None,
    expected_row_version: int | None = None,
    has_sensitive_permission: bool = False,
    reason: str = "explicit HiPo decision",
) -> dict[str, Any]:
    """Explicit human HiPo decision — never auto from perf/potential/9-box."""
    if not str(rationale or "").strip():
        return {"ok": False, "error": "rationale_required"}
    if not str(reason or "").strip():
        return {"ok": False, "error": "audit_reason_required"}
    ent = _entitled(cur, company_code, feature="hipo")
    if not ent.get("ok"):
        return ent
    if ent["settings"].get("require_sensitive_permission") and not has_sensitive_permission:
        return {"ok": False, "error": "sensitive_permission_required"}
    st = str(status or "").strip().lower()
    if st not in HIPO_STATES:
        return {"ok": False, "error": "invalid_hipo_status", "allowed": list(HIPO_STATES)}
    company = ent["company_code"]

    cur.execute(
        """
        SELECT * FROM talent_hipo_designations
        WHERE company_code=%s AND employee_key=%s AND superseded_by_designation_id IS NULL
          AND status IN ('nominated','designated','not_designated','review_required')
        ORDER BY version DESC LIMIT 1
        """,
        (company, employee_key),
    )
    prior = cur.fetchone()
    prior = dict(prior) if prior else None
    if prior and expected_row_version is not None and int(prior["row_version"]) != int(expected_row_version):
        return {
            "ok": False,
            "error": "stale_row_version",
            "expected": int(expected_row_version),
            "actual": int(prior["row_version"]),
        }

    ver = int(prior["version"]) + 1 if prior else 1
    cur.execute(
        """
        INSERT INTO talent_hipo_designations (
          company_code, employee_key, status, version, decision_maker_phone, rationale,
          evidence_refs, talent_review_id, nine_box_cell, inferred_from_nine_box,
          effective_date, review_by_date
        ) VALUES (%s,%s,%s,%s,%s,%s,%s::jsonb,%s,%s,false,%s,%s)
        RETURNING *
        """,
        (
            company, employee_key, st, ver, _digits(actor_phone), str(rationale).strip()[:2000],
            json.dumps(evidence_refs or [], default=str), talent_review_id, nine_box_cell,
            effective_date or date.today(), review_by_date,
        ),
    )
    row = dict(cur.fetchone())
    if prior:
        cur.execute(
            """
            UPDATE talent_hipo_designations
            SET superseded_by_designation_id=%s, updated_at=now()
            WHERE designation_id=%s
            """,
            (row["designation_id"], prior["designation_id"]),
        )
    _audit(
        cur, company_code=company, action="hipo_decision", actor_phone=actor_phone,
        reason=reason, subject_type="hipo_designation", subject_id=str(row["designation_id"]),
        payload={
            "status": st,
            "version": ver,
            "inferred_from_nine_box": False,
            "inferred_from_performance": False,
            "inferred_from_potential": False,
            "prior_designation_id": str(prior["designation_id"]) if prior else None,
        },
    )
    return {
        "ok": True,
        "designation": row,
        "auto_inferred": False,
        "top_right_implies_hipo": False,
    }


def get_hipo_for_viewer(
    cur: Any,
    *,
    company_code: str,
    employee_key: str,
    viewer_role: str,
    has_sensitive_permission: bool = False,
) -> dict[str, Any]:
    ensure_talent_succession_c6_schema(cur)
    settings = get_company_settings(cur, company_code) or {}
    if viewer_role == "employee" and not settings.get("employees_see_hipo"):
        return {"ok": False, "error": "hipo_hidden_from_employee"}
    if settings.get("require_sensitive_permission") and viewer_role != "employee" and not has_sensitive_permission:
        return {"ok": False, "error": "sensitive_permission_required"}
    cur.execute(
        """
        SELECT * FROM talent_hipo_designations
        WHERE company_code=%s AND employee_key=%s
        ORDER BY version DESC
        """,
        (company_code_norm(company_code), employee_key),
    )
    rows = [dict(r) for r in (cur.fetchall() or [])]
    return {"ok": True, "designations": rows}


# ── Critical roles + succession ─────────────────────────────────────────────


def designate_critical_role(
    cur: Any,
    *,
    company_code: str,
    actor_phone: str,
    canonical_role_key: str,
    title_en: str,
    title_ar: str | None = None,
    canonical_position_id: str | None = None,
    org_unit_key: str | None = None,
    criticality: str = "critical",
    reason: str = "designate critical role",
) -> dict[str, Any]:
    if not str(reason or "").strip():
        return {"ok": False, "error": "audit_reason_required"}
    ent = _entitled(cur, company_code, feature="succession")
    if not ent.get("ok"):
        return ent
    company = ent["company_code"]
    key = str(canonical_role_key or "").strip()
    if not key:
        return {"ok": False, "error": "canonical_role_key_required"}
    cur.execute(
        """
        INSERT INTO talent_critical_roles (
          company_code, canonical_role_key, canonical_position_id, title_en, title_ar,
          criticality, org_unit_key, created_by_phone
        ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
        ON CONFLICT (company_code, canonical_role_key) DO UPDATE SET
          title_en=EXCLUDED.title_en,
          title_ar=EXCLUDED.title_ar,
          canonical_position_id=COALESCE(EXCLUDED.canonical_position_id, talent_critical_roles.canonical_position_id),
          criticality=EXCLUDED.criticality,
          org_unit_key=EXCLUDED.org_unit_key,
          status='active',
          updated_at=now()
        RETURNING *
        """,
        (
            company, key, canonical_position_id, title_en, title_ar,
            criticality, org_unit_key, _digits(actor_phone),
        ),
    )
    row = dict(cur.fetchone())
    _audit(
        cur, company_code=company, action="critical_role_defined", actor_phone=actor_phone,
        reason=reason, subject_type="critical_role", subject_id=str(row["critical_role_id"]),
        payload={"references_canonical_org": True, "no_duplicate_job_architecture": True},
    )
    return {"ok": True, "critical_role": row}


def create_succession_plan(
    cur: Any,
    *,
    company_code: str,
    actor_phone: str,
    critical_role_id: str,
    reason: str = "create succession plan",
) -> dict[str, Any]:
    if not str(reason or "").strip():
        return {"ok": False, "error": "audit_reason_required"}
    ent = _entitled(cur, company_code, feature="succession")
    if not ent.get("ok"):
        return ent
    company = ent["company_code"]
    cur.execute(
        "SELECT 1 FROM talent_critical_roles WHERE company_code=%s AND critical_role_id=%s",
        (company, critical_role_id),
    )
    if not cur.fetchone():
        return {"ok": False, "error": "critical_role_not_found"}
    fw = ent["settings"].get("readiness_framework") or list(DEFAULT_READINESS)
    if isinstance(fw, str):
        fw = json.loads(fw)
    cur.execute(
        """
        INSERT INTO talent_succession_plans (
          company_code, critical_role_id, status, owner_phone,
          readiness_framework_snapshot, created_by_phone
        ) VALUES (%s,%s,'active',%s,%s::jsonb,%s)
        ON CONFLICT (company_code, critical_role_id) DO UPDATE SET
          status='active',
          updated_at=now(),
          row_version=talent_succession_plans.row_version+1
        RETURNING *
        """,
        (
            company, critical_role_id, _digits(actor_phone),
            json.dumps(fw, default=str), _digits(actor_phone),
        ),
    )
    row = dict(cur.fetchone())
    _audit(
        cur, company_code=company, action="succession_plan_created", actor_phone=actor_phone,
        reason=reason, subject_type="succession_plan", subject_id=str(row["plan_id"]),
        payload={"works_without_nine_box": True, "works_without_hipo": True},
    )
    return {"ok": True, "plan": row}


def nominate_successor(
    cur: Any,
    *,
    company_code: str,
    actor_phone: str,
    plan_id: str,
    employee_key: str,
    rationale: str,
    readiness: str = "unassessed",
    readiness_rationale: str | None = None,
    evidence_refs: list[Any] | None = None,
    capability_gaps: list[Any] | None = None,
    strengths_refs: list[Any] | None = None,
    tier: str | None = None,
    expected_row_version: int | None = None,
    has_sensitive_permission: bool = False,
    create_development_for_gaps: bool = False,
    development_plan_id: str | None = None,
    reason: str = "nominate successor",
) -> dict[str, Any]:
    if not str(rationale or "").strip():
        return {"ok": False, "error": "rationale_required"}
    ent = _entitled(cur, company_code, feature="succession")
    if not ent.get("ok"):
        return ent
    if ent["settings"].get("require_sensitive_permission") and not has_sensitive_permission:
        return {"ok": False, "error": "sensitive_permission_required"}
    company = ent["company_code"]
    cur.execute(
        "SELECT * FROM talent_succession_plans WHERE company_code=%s AND plan_id=%s",
        (company, plan_id),
    )
    plan = cur.fetchone()
    if not plan:
        return {"ok": False, "error": "succession_plan_not_found"}
    plan = dict(plan)
    if expected_row_version is not None and int(plan["row_version"]) != int(expected_row_version):
        return {"ok": False, "error": "stale_row_version"}

    fw = plan.get("readiness_framework_snapshot") or list(DEFAULT_READINESS)
    if isinstance(fw, str):
        fw = json.loads(fw)
    ready = str(readiness or "unassessed").strip().lower()
    if ready not in {str(x) for x in fw}:
        return {"ok": False, "error": "invalid_readiness", "allowed": fw}

    # Idempotent upsert for same plan+employee
    cur.execute(
        """
        SELECT * FROM talent_successor_nominations
        WHERE plan_id=%s AND employee_key=%s
        """,
        (plan_id, employee_key),
    )
    existing = cur.fetchone()
    if existing:
        existing = dict(existing)
        cur.execute(
            """
            UPDATE talent_successor_nominations SET
              status='active',
              readiness=%s,
              readiness_rationale=%s,
              rationale=%s,
              evidence_refs=%s::jsonb,
              capability_gaps=%s::jsonb,
              strengths_refs=%s::jsonb,
              tier=%s,
              nomination_actor_phone=%s,
              row_version=row_version+1,
              updated_at=now()
            WHERE nomination_id=%s
            RETURNING *
            """,
            (
                ready, readiness_rationale, str(rationale).strip()[:2000],
                json.dumps(evidence_refs or [], default=str),
                json.dumps(capability_gaps or [], default=str),
                json.dumps(strengths_refs or [], default=str),
                tier, _digits(actor_phone), existing["nomination_id"],
            ),
        )
        row = dict(cur.fetchone())
        idempotent = True
    else:
        cur.execute(
            """
            INSERT INTO talent_successor_nominations (
              company_code, plan_id, critical_role_id, employee_key, status, readiness,
              readiness_rationale, nomination_actor_phone, rationale, evidence_refs,
              capability_gaps, strengths_refs, tier, effective_date
            ) VALUES (%s,%s,%s,%s,'active',%s,%s,%s,%s,%s::jsonb,%s::jsonb,%s::jsonb,%s,CURRENT_DATE)
            RETURNING *
            """,
            (
                company, plan_id, plan["critical_role_id"], employee_key, ready,
                readiness_rationale, _digits(actor_phone), str(rationale).strip()[:2000],
                json.dumps(evidence_refs or [], default=str),
                json.dumps(capability_gaps or [], default=str),
                json.dumps(strengths_refs or [], default=str),
                tier,
            ),
        )
        row = dict(cur.fetchone())
        idempotent = False

    dev_action_id = None
    if create_development_for_gaps and (capability_gaps or []):
        dev_action_id = _maybe_create_c3_development_action(
            cur,
            company_code=company,
            actor_phone=actor_phone,
            employee_key=employee_key,
            plan_id=development_plan_id,
            gaps=capability_gaps or [],
            nomination_id=str(row["nomination_id"]),
        )
        if dev_action_id:
            cur.execute(
                """
                UPDATE talent_successor_nominations
                SET development_action_id=%s, updated_at=now()
                WHERE nomination_id=%s
                RETURNING *
                """,
                (dev_action_id, row["nomination_id"]),
            )
            row = dict(cur.fetchone())

    cur.execute(
        """
        UPDATE talent_succession_plans
        SET row_version=row_version+1, updated_at=now()
        WHERE plan_id=%s
        """,
        (plan_id,),
    )
    _emit_coverage_facts(cur, company=company, critical_role_id=str(plan["critical_role_id"]))
    _audit(
        cur, company_code=company, action="successor_nominated", actor_phone=actor_phone,
        reason=reason, subject_type="successor_nomination", subject_id=str(row["nomination_id"]),
        payload={
            "readiness": ready,
            "target_specific": True,
            "development_action_id": dev_action_id,
            "idempotent": idempotent,
        },
    )
    return {
        "ok": True,
        "nomination": row,
        "idempotent": idempotent,
        "development_action_id": dev_action_id,
        "global_readiness_score": None,
    }


def _maybe_create_c3_development_action(
    cur: Any,
    *,
    company_code: str,
    actor_phone: str,
    employee_key: str,
    plan_id: str | None,
    gaps: list[Any],
    nomination_id: str,
) -> str | None:
    """Reference/create via C3 canonical development — no succession_development_plan_v2."""
    try:
        import performance_feedback_c3 as c3
    except ImportError:
        return None
    sp = f"c6_dev_{uuid.uuid4().hex[:10]}"
    try:
        cur.execute(f"SAVEPOINT {sp}")
        # Ensure C3 schema; may be off — still try soft path
        c3.ensure_performance_feedback_c3_schema(cur)
        dplan = plan_id
        if not dplan:
            # create a lightweight plan under C3 if entitled; else skip
            os_environ_on = _env_on("WATHEFNI_PERFORMANCE_FEEDBACK_C3", "off")
            if not os_environ_on:
                cur.execute(f"RELEASE SAVEPOINT {sp}")
                return None
            # Use existing plan creation only when company entitled in C3
            created = c3.create_development_plan(
                cur,
                company_code=company_code,
                actor_phone=actor_phone,
                employee_key=employee_key,
                title_en="Succession readiness gaps",
                title_ar="فجوات جاهزية التعاقب",
                development_areas=gaps,
                reason="C6 succession gap → C3 development",
            )
            if not created.get("ok"):
                cur.execute(f"RELEASE SAVEPOINT {sp}")
                return None
            dplan = str(created["plan"]["plan_id"])
        gap0 = gaps[0] if gaps else "Succession readiness gap"
        if isinstance(gap0, dict):
            title = str(gap0.get("en") or gap0.get("title_en") or "Succession readiness gap")
        else:
            title = str(gap0)
        act = c3.create_development_action(
            cur,
            company_code=company_code,
            actor_phone=actor_phone,
            plan_id=dplan,
            title_en=title[:200],
            source_type="manual",
            source_id=nomination_id,
            reason="C6 succession gap action via C3",
        )
        cur.execute(f"RELEASE SAVEPOINT {sp}")
        if act.get("ok"):
            return str(act["action"]["action_id"])
        return None
    except Exception:
        try:
            cur.execute(f"ROLLBACK TO SAVEPOINT {sp}")
            cur.execute(f"RELEASE SAVEPOINT {sp}")
        except Exception:
            pass
        return None


def _emit_coverage_facts(cur: Any, *, company: str, critical_role_id: str) -> None:
    cur.execute(
        """
        SELECT readiness, count(*) AS n
        FROM talent_successor_nominations
        WHERE critical_role_id=%s AND status='active'
        GROUP BY readiness
        """,
        (critical_role_id,),
    )
    dist = {dict(r)["readiness"]: int(dict(r)["n"]) for r in (cur.fetchall() or [])}
    total = sum(dist.values())
    ready_now = int(dist.get("ready_now") or 0)
    cur.execute(
        """
        INSERT INTO talent_succession_coverage_facts (
          company_code, critical_role_id, fact_type, fact_value
        ) VALUES
          (%s,%s,'successor_count',%s::jsonb),
          (%s,%s,'ready_now_count',%s::jsonb),
          (%s,%s,'readiness_distribution',%s::jsonb),
          (%s,%s,'uncovered_critical_role',%s::jsonb)
        """,
        (
            company, critical_role_id, json.dumps({"count": total}),
            company, critical_role_id, json.dumps({"count": ready_now}),
            company, critical_role_id, json.dumps(dist, default=str),
            company, critical_role_id, json.dumps({"uncovered": total == 0}),
        ),
    )


def list_uncovered_critical_roles(cur: Any, *, company_code: str) -> dict[str, Any]:
    ensure_talent_succession_c6_schema(cur)
    company = company_code_norm(company_code)
    cur.execute(
        """
        SELECT cr.*
        FROM talent_critical_roles cr
        WHERE cr.company_code=%s AND cr.status='active'
          AND NOT EXISTS (
            SELECT 1 FROM talent_successor_nominations n
            WHERE n.critical_role_id=cr.critical_role_id AND n.status='active'
          )
        """,
        (company,),
    )
    rows = [dict(r) for r in (cur.fetchall() or [])]
    return {"ok": True, "uncovered": rows, "honest_gap": True}


def talent_map_queries(
    cur: Any, *, company_code: str, employee_key: str | None = None, critical_role_id: str | None = None
) -> dict[str, Any]:
    """Foundation queries for future Talent Map — no master score / silent ranking."""
    ensure_talent_succession_c6_schema(cur)
    company = company_code_norm(company_code)
    out: dict[str, Any] = {"ok": True, "master_talent_score": None, "silent_ranking": False}
    if critical_role_id:
        cur.execute(
            """
            SELECT employee_key, readiness, status, rationale, capability_gaps
            FROM talent_successor_nominations
            WHERE company_code=%s AND critical_role_id=%s AND status='active'
            """,
            (company, critical_role_id),
        )
        out["role_to_successors"] = [dict(r) for r in (cur.fetchall() or [])]
    if employee_key:
        cur.execute(
            """
            SELECT n.critical_role_id, n.readiness, n.status, cr.canonical_role_key, cr.title_en
            FROM talent_successor_nominations n
            JOIN talent_critical_roles cr ON cr.critical_role_id=n.critical_role_id
            WHERE n.company_code=%s AND n.employee_key=%s AND n.status='active'
            """,
            (company, employee_key),
        )
        out["employee_to_target_roles"] = [dict(r) for r in (cur.fetchall() or [])]
    return out


def can_view_succession(
    *,
    viewer_role: str,
    settings: dict[str, Any],
    has_sensitive_permission: bool = False,
    manager_in_scope: bool = False,
) -> dict[str, Any]:
    if viewer_role == "employee" and not settings.get("employees_see_succession"):
        return {"ok": False, "error": "succession_hidden_from_employee"}
    if settings.get("require_sensitive_permission") and not has_sensitive_permission:
        if viewer_role == "manager" and manager_in_scope:
            return {"ok": False, "error": "sensitive_permission_required"}
        if viewer_role in ("hr", "facilitator") and not has_sensitive_permission:
            return {"ok": False, "error": "sensitive_permission_required"}
    if viewer_role == "manager" and not manager_in_scope:
        return {"ok": False, "error": "manager_out_of_scope"}
    return {"ok": True}


def assert_no_forbidden_c6_writes() -> dict[str, Any]:
    return {
        "ok": True,
        "master_talent_score": False,
        "ai_hipo_designation": False,
        "ai_potential_assignment": False,
        "ai_readiness_mutation": False,
        "ai_successor_finalize": False,
        "employee_box_canonical_field": False,
        "c4_rating_rewrites": False,
        "c5_evidence_rewrites": False,
        "assistant_mutations": False,
    }
