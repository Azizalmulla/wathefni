#!/usr/bin/env python3
"""Wave 4 C1 — Performance Goals / OKR / KPI framework (company-scoped).

Owner-approved under WAVE4_PERFORMANCE_TALENT_CHARTER (2026-08-12) §0.8.1–0.8.2.

First-class OKRs:
  Objective → multiple Key Results → weighted roll-up
Coexist goal kinds: kpi | milestone | development
Every measurable item requires an explicit measure_definition contract.
Alignment links without forced cascade.
Versioned target changes with audit.
Progress derived from measure engine — never free-typed dashboard %.

Gates (fail-closed):
  1) WATHEFNI_PERFORMANCE_GOALS_C1 must be on
  2) company in WATHEFNI_PERFORMANCE_GOALS_COMPANIES (empty = nobody)
  3) company entitlement in performance_goals_c1_company_settings

Does NOT: review cycles, calibration, talent, 9-box, Assistant mutations,
require Talent module, invent decorative KPI percentages.
"""
from __future__ import annotations

import json
import os
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

PHASE = "performance_goals_c1"
CONTRACT_VERSION = "performance_goals_c1_v1"
PASS_STAMP = "PERFORMANCE_GOALS_FULL_PASS"
COMMERCIAL_MODULE_KEY = "performance"
_ON = {"1", "true", "yes", "on"}

SCOPES = ("individual", "team", "department", "company")
GOAL_KINDS = ("kpi", "milestone", "development")
DIRECTIONS = ("higher_is_better", "lower_is_better", "target_range", "milestone")
SOURCES = ("manual", "wathefni_canonical_fact", "integration")

ST_DRAFT = "draft"
ST_ACTIVE = "active"
ST_COMPLETED = "completed"
ST_CANCELLED = "cancelled"
ST_ARCHIVED = "archived"

STATUS_LABELS = {
    "draft": {"en": "Draft", "ar": "مسودة"},
    "active": {"en": "Active", "ar": "نشط"},
    "completed": {"en": "Completed", "ar": "مكتمل"},
    "cancelled": {"en": "Cancelled", "ar": "ملغى"},
    "archived": {"en": "Archived", "ar": "مؤرشف"},
    "objective": {"en": "Objective", "ar": "هدف رئيسي"},
    "key_result": {"en": "Key Result", "ar": "نتيجة رئيسية"},
    "kpi": {"en": "KPI", "ar": "مؤشر أداء"},
    "milestone": {"en": "Milestone", "ar": "معلم"},
    "development": {"en": "Development goal", "ar": "هدف تطويري"},
    "not_started": {"en": "Not started", "ar": "لم يبدأ"},
    "unknown": {"en": "Unknown", "ar": "غير معروف"},
    "on_track": {"en": "On track", "ar": "على المسار"},
    "individual": {"en": "Individual", "ar": "فردي"},
    "team": {"en": "Team", "ar": "فريق"},
    "department": {"en": "Department", "ar": "قسم"},
    "company": {"en": "Company", "ar": "شركة"},
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


def performance_goals_c1_runtime_on() -> bool:
    return _env_on("WATHEFNI_PERFORMANCE_GOALS_C1", "off")


def performance_goals_company_allowlist() -> set[str]:
    raw = str(os.environ.get("WATHEFNI_PERFORMANCE_GOALS_COMPANIES") or "").strip()
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
        "okrs_first_class": True,
        "objective_is_not_generic_goal": True,
        "key_result_is_not_kpi_alias": True,
        "kpi_math_required": True,
        "decorative_progress_pct_forbidden": True,
        "talent_required": False,
        "review_cycle_required": False,
        "forced_cascade_required": False,
        "company_code": company_code_norm(company_code) if company_code else None,
    }


def rollback_guidance() -> dict[str, Any]:
    return {
        "phase": PHASE,
        "ok": True,
        "steps": [
            "WATHEFNI_PERFORMANCE_GOALS_C1=off",
            "Clear WATHEFNI_PERFORMANCE_GOALS_COMPANIES",
            "WATHEFNI_PERFORMANCE_KILL=on (optional immediate block)",
            "Disable company Setup entitlement (preserves history)",
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
    if not performance_goals_c1_runtime_on():
        return {
            "ok": False,
            "enabled": False,
            "error": "performance_goals_c1_off",
            "gate": "runtime_flag",
            "phase": PHASE,
        }
    allow = performance_goals_company_allowlist()
    if not allow:
        return {
            "ok": False,
            "enabled": False,
            "error": "performance_goals_company_not_allowlisted",
            "gate": "company_allowlist",
            "phase": PHASE,
            "message": "Performance-goals allowlist empty — fail closed (nobody).",
        }
    if company not in allow:
        return {
            "ok": False,
            "enabled": False,
            "error": "performance_goals_company_not_allowlisted",
            "gate": "company_allowlist",
            "phase": PHASE,
            "company_code": company,
        }
    return {"ok": True, "enabled": True, "company_code": company, "phase": PHASE}


def _dec(value: Any) -> Decimal | None:
    if value is None or value == "":
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None


def compute_progress(
    *,
    direction: str,
    baseline: Any,
    target: Any,
    current: Any,
    range_low: Any = None,
    range_high: Any = None,
) -> dict[str, Any]:
    """Versioned measure engine — never invents 100% from missing current."""
    d = str(direction or "").strip().lower()
    if d not in DIRECTIONS:
        return {"ok": False, "error": "invalid_direction", "allowed": list(DIRECTIONS)}
    cur = _dec(current)
    if cur is None:
        return {
            "ok": True,
            "progress_pct": None,
            "status": "not_started",
            "message": "No current value — progress unknown (not 100%).",
            "formula_version": "measure_v1",
        }

    if d == "milestone":
        tgt = _dec(target)
        if tgt is None:
            done = 1.0 if float(cur) >= 1.0 else 0.0
        else:
            done = 1.0 if cur >= tgt else float(cur / tgt) if tgt != 0 else 0.0
        done = max(0.0, min(1.0, done))
        return {
            "ok": True,
            "progress_pct": round(done * 100.0, 4),
            "status": "completed" if done >= 1.0 else "on_track" if done > 0 else "not_started",
            "formula_version": "measure_v1",
        }

    if d == "target_range":
        lo = _dec(range_low if range_low is not None else baseline)
        hi = _dec(range_high if range_high is not None else target)
        if lo is None or hi is None:
            return {"ok": False, "error": "target_range_requires_bounds"}
        if lo > hi:
            lo, hi = hi, lo
        if lo <= cur <= hi:
            return {
                "ok": True,
                "progress_pct": 100.0,
                "status": "on_track",
                "formula_version": "measure_v1",
            }
        # Distance outside range as partial credit toward nearer bound span
        span = hi - lo if hi != lo else Decimal("1")
        dist = (lo - cur) if cur < lo else (cur - hi)
        pct = max(0.0, min(100.0, float((1 - (dist / span)) * 100)))
        return {
            "ok": True,
            "progress_pct": round(pct, 4),
            "status": "on_track" if pct >= 50 else "unknown",
            "formula_version": "measure_v1",
        }

    base = _dec(baseline)
    tgt = _dec(target)
    if base is None or tgt is None:
        return {"ok": False, "error": "baseline_and_target_required"}
    if base == tgt:
        # Already at target baseline — current equals target → 100 else unknown/0
        pct = 100.0 if cur == tgt else 0.0
        return {
            "ok": True,
            "progress_pct": pct,
            "status": "on_track" if pct >= 100 else "unknown",
            "formula_version": "measure_v1",
        }

    if d == "higher_is_better":
        raw = (cur - base) / (tgt - base)
    else:  # lower_is_better
        raw = (base - cur) / (base - tgt)
    pct = max(0.0, min(100.0, float(raw * 100)))
    return {
        "ok": True,
        "progress_pct": round(pct, 4),
        "status": "completed" if pct >= 100 else "on_track" if pct > 0 else "not_started",
        "formula_version": "measure_v1",
    }


def ensure_performance_goals_c1_schema(cur: Any, *, force: bool = False) -> None:
    _ = force
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS performance_goals_c1_company_settings (
          company_code text PRIMARY KEY,
          enabled boolean NOT NULL DEFAULT false,
          okrs_enabled boolean NOT NULL DEFAULT true,
          kpi_goals_enabled boolean NOT NULL DEFAULT true,
          milestone_goals_enabled boolean NOT NULL DEFAULT true,
          development_goals_enabled boolean NOT NULL DEFAULT true,
          allowed_scopes jsonb NOT NULL DEFAULT '["individual","team","department","company"]'::jsonb,
          allow_alignment_links boolean NOT NULL DEFAULT true,
          force_rigid_cascade boolean NOT NULL DEFAULT false,
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
        CREATE TABLE IF NOT EXISTS perf_measure_definitions (
          measure_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
          company_code text NOT NULL,
          name_en text NOT NULL,
          name_ar text,
          unit text NOT NULL,
          direction text NOT NULL,
          source text NOT NULL DEFAULT 'manual',
          baseline numeric,
          target numeric,
          range_low numeric,
          range_high numeric,
          formula_version text NOT NULL DEFAULT 'measure_v1',
          period_start date,
          period_end date,
          owner_employee_key text,
          version int NOT NULL DEFAULT 1,
          status text NOT NULL DEFAULT 'active',
          created_by_phone text,
          created_at timestamptz NOT NULL DEFAULT now(),
          updated_at timestamptz NOT NULL DEFAULT now(),
          metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
          CONSTRAINT perf_measure_direction_chk CHECK (direction IN (
            'higher_is_better','lower_is_better','target_range','milestone'
          )),
          CONSTRAINT perf_measure_source_chk CHECK (source IN (
            'manual','wathefni_canonical_fact','integration'
          ))
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS perf_objectives (
          objective_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
          company_code text NOT NULL,
          title_en text NOT NULL,
          title_ar text,
          scope text NOT NULL,
          owner_employee_key text,
          org_unit_id text,
          status text NOT NULL DEFAULT 'draft',
          period_start date,
          period_end date,
          weight numeric,
          row_version int NOT NULL DEFAULT 1,
          created_by_phone text,
          created_at timestamptz NOT NULL DEFAULT now(),
          updated_at timestamptz NOT NULL DEFAULT now(),
          metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
          CONSTRAINT perf_objective_scope_chk CHECK (scope IN (
            'individual','team','department','company'
          )),
          CONSTRAINT perf_objective_status_chk CHECK (status IN (
            'draft','active','completed','cancelled','archived'
          ))
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS perf_key_results (
          key_result_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
          company_code text NOT NULL,
          objective_id uuid NOT NULL REFERENCES perf_objectives(objective_id),
          title_en text NOT NULL,
          title_ar text,
          measure_id uuid NOT NULL REFERENCES perf_measure_definitions(measure_id),
          weight numeric NOT NULL DEFAULT 1,
          current_value numeric,
          status text NOT NULL DEFAULT 'draft',
          row_version int NOT NULL DEFAULT 1,
          created_by_phone text,
          created_at timestamptz NOT NULL DEFAULT now(),
          updated_at timestamptz NOT NULL DEFAULT now(),
          metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
          CONSTRAINT perf_kr_status_chk CHECK (status IN (
            'draft','active','completed','cancelled','archived'
          ))
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS perf_goals (
          goal_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
          company_code text NOT NULL,
          goal_kind text NOT NULL,
          title_en text NOT NULL,
          title_ar text,
          scope text NOT NULL,
          owner_employee_key text,
          org_unit_id text,
          measure_id uuid REFERENCES perf_measure_definitions(measure_id),
          weight numeric,
          current_value numeric,
          status text NOT NULL DEFAULT 'draft',
          period_start date,
          period_end date,
          row_version int NOT NULL DEFAULT 1,
          created_by_phone text,
          created_at timestamptz NOT NULL DEFAULT now(),
          updated_at timestamptz NOT NULL DEFAULT now(),
          metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
          CONSTRAINT perf_goal_kind_chk CHECK (goal_kind IN ('kpi','milestone','development')),
          CONSTRAINT perf_goal_scope_chk CHECK (scope IN (
            'individual','team','department','company'
          )),
          CONSTRAINT perf_goal_status_chk CHECK (status IN (
            'draft','active','completed','cancelled','archived'
          ))
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS perf_alignment_links (
          link_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
          company_code text NOT NULL,
          from_type text NOT NULL,
          from_id uuid NOT NULL,
          to_type text NOT NULL,
          to_id uuid NOT NULL,
          link_kind text NOT NULL DEFAULT 'aligned',
          created_by_phone text,
          created_at timestamptz NOT NULL DEFAULT now(),
          metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
          CONSTRAINT perf_align_from_chk CHECK (from_type IN ('objective','key_result','goal')),
          CONSTRAINT perf_align_to_chk CHECK (to_type IN ('objective','key_result','goal')),
          CONSTRAINT perf_align_kind_chk CHECK (link_kind IN ('aligned','contributes_to','supports'))
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS perf_target_versions (
          version_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
          company_code text NOT NULL,
          subject_type text NOT NULL,
          subject_id uuid NOT NULL,
          measure_id uuid,
          baseline numeric,
          target numeric,
          range_low numeric,
          range_high numeric,
          reason text NOT NULL,
          created_by_phone text,
          created_at timestamptz NOT NULL DEFAULT now(),
          CONSTRAINT perf_target_subject_chk CHECK (subject_type IN (
            'measure','key_result','goal'
          ))
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS perf_progress_entries (
          entry_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
          company_code text NOT NULL,
          subject_type text NOT NULL,
          subject_id uuid NOT NULL,
          measure_id uuid,
          current_value numeric NOT NULL,
          computed_progress_pct numeric,
          computed_status text,
          source text NOT NULL DEFAULT 'manual',
          note text,
          recorded_by_phone text,
          recorded_at timestamptz NOT NULL DEFAULT now(),
          metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
          CONSTRAINT perf_progress_subject_chk CHECK (subject_type IN ('key_result','goal')),
          CONSTRAINT perf_progress_source_chk CHECK (source IN (
            'manual','wathefni_canonical_fact','integration'
          ))
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS performance_goals_c1_audit (
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
    for idx_sql in (
        "CREATE INDEX IF NOT EXISTS perf_objectives_company_idx ON perf_objectives(company_code, status)",
        "CREATE INDEX IF NOT EXISTS perf_kr_objective_idx ON perf_key_results(objective_id)",
        "CREATE INDEX IF NOT EXISTS perf_goals_company_idx ON perf_goals(company_code, goal_kind, status)",
        "CREATE INDEX IF NOT EXISTS perf_progress_subject_idx ON perf_progress_entries(subject_type, subject_id)",
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
        INSERT INTO performance_goals_c1_audit (
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
    ensure_performance_goals_c1_schema(cur)
    cur.execute(
        "SELECT * FROM performance_goals_c1_company_settings WHERE company_code=%s",
        (company_code_norm(company_code),),
    )
    row = cur.fetchone()
    return dict(row) if row else None


def enable_company_performance_goals(
    cur: Any,
    *,
    company_code: str,
    actor_phone: str,
    reason: str,
    okrs_enabled: bool = True,
    kpi_goals_enabled: bool = True,
    milestone_goals_enabled: bool = True,
    development_goals_enabled: bool = True,
    allowed_scopes: list[str] | None = None,
    allow_alignment_links: bool = True,
) -> dict[str, Any]:
    if not str(reason or "").strip():
        return {"ok": False, "error": "audit_reason_required"}
    gate = runtime_gate_for_company(company_code)
    if not gate.get("ok"):
        return gate
    company = company_code_norm(company_code)
    scopes = list(allowed_scopes or SCOPES)
    for s in scopes:
        if s not in SCOPES:
            return {"ok": False, "error": "invalid_scope", "allowed": list(SCOPES)}
    ensure_performance_goals_c1_schema(cur)
    cur.execute(
        """
        INSERT INTO performance_goals_c1_company_settings (
          company_code, enabled, okrs_enabled, kpi_goals_enabled, milestone_goals_enabled,
          development_goals_enabled, allowed_scopes, allow_alignment_links, force_rigid_cascade,
          enabled_by_phone, enabled_reason, enabled_at, updated_by_phone, updated_at, disabled_at
        ) VALUES (%s,true,%s,%s,%s,%s,%s::jsonb,%s,false,%s,%s,now(),%s,now(),NULL)
        ON CONFLICT (company_code) DO UPDATE SET
          enabled=true,
          okrs_enabled=EXCLUDED.okrs_enabled,
          kpi_goals_enabled=EXCLUDED.kpi_goals_enabled,
          milestone_goals_enabled=EXCLUDED.milestone_goals_enabled,
          development_goals_enabled=EXCLUDED.development_goals_enabled,
          allowed_scopes=EXCLUDED.allowed_scopes,
          allow_alignment_links=EXCLUDED.allow_alignment_links,
          force_rigid_cascade=false,
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
            bool(okrs_enabled),
            bool(kpi_goals_enabled),
            bool(milestone_goals_enabled),
            bool(development_goals_enabled),
            json.dumps(scopes),
            bool(allow_alignment_links),
            _digits(actor_phone),
            str(reason).strip()[:500],
            _digits(actor_phone),
        ),
    )
    row = dict(cur.fetchone())
    _audit(
        cur,
        company_code=company,
        action="enable_performance_goals",
        actor_phone=actor_phone,
        reason=reason,
        subject_type="company",
        subject_id=company,
        payload={"okrs_enabled": okrs_enabled},
    )
    return {"ok": True, "company": row, **honesty_payload(company_code=company)}


def disable_company_performance_goals(
    cur: Any, *, company_code: str, actor_phone: str, reason: str
) -> dict[str, Any]:
    if not str(reason or "").strip():
        return {"ok": False, "error": "audit_reason_required"}
    company = company_code_norm(company_code)
    ensure_performance_goals_c1_schema(cur)
    cur.execute(
        """
        UPDATE performance_goals_c1_company_settings
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
        action="disable_performance_goals",
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
            "error": "performance_goals_entitlement_off",
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
        "okrs_visible": bool(enabled and settings and settings.get("okrs_enabled")),
        "kpi_goals_visible": bool(enabled and settings and settings.get("kpi_goals_enabled")),
        "milestone_goals_visible": bool(enabled and settings and settings.get("milestone_goals_enabled")),
        "development_goals_visible": bool(
            enabled and settings and settings.get("development_goals_enabled")
        ),
        "review_cycles_visible": False,
        "talent_visible": False,
        "assistant_mutations": False,
        **honesty_payload(company_code=company_code),
    }


def create_measure_definition(
    cur: Any,
    *,
    company_code: str,
    actor_phone: str,
    name_en: str,
    unit: str,
    direction: str,
    source: str = "manual",
    baseline: Any = None,
    target: Any = None,
    range_low: Any = None,
    range_high: Any = None,
    period_start: date | str | None = None,
    period_end: date | str | None = None,
    owner_employee_key: str | None = None,
    name_ar: str | None = None,
    reason: str = "create measure",
) -> dict[str, Any]:
    enabled = module_enabled_for_company(cur, company_code)
    if not enabled.get("ok"):
        return enabled
    d = str(direction or "").strip().lower()
    if d not in DIRECTIONS:
        return {"ok": False, "error": "invalid_direction", "allowed": list(DIRECTIONS)}
    src = str(source or "manual").strip().lower()
    if src not in SOURCES:
        return {"ok": False, "error": "invalid_source", "allowed": list(SOURCES)}
    if not str(name_en or "").strip() or not str(unit or "").strip():
        return {"ok": False, "error": "name_and_unit_required"}
    if d != "milestone" and (_dec(baseline) is None or _dec(target) is None) and d != "target_range":
        return {"ok": False, "error": "baseline_and_target_required"}
    if d == "target_range" and (
        _dec(range_low if range_low is not None else baseline) is None
        or _dec(range_high if range_high is not None else target) is None
    ):
        return {"ok": False, "error": "target_range_requires_bounds"}
    company = company_code_norm(company_code)
    ensure_performance_goals_c1_schema(cur)
    cur.execute(
        """
        INSERT INTO perf_measure_definitions (
          company_code, name_en, name_ar, unit, direction, source,
          baseline, target, range_low, range_high, period_start, period_end,
          owner_employee_key, created_by_phone
        ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
        RETURNING *
        """,
        (
            company,
            str(name_en).strip()[:300],
            (str(name_ar).strip()[:300] if name_ar else None),
            str(unit).strip()[:64],
            d,
            src,
            _dec(baseline),
            _dec(target),
            _dec(range_low),
            _dec(range_high),
            str(period_start)[:10] if period_start else None,
            str(period_end)[:10] if period_end else None,
            owner_employee_key,
            _digits(actor_phone),
        ),
    )
    row = dict(cur.fetchone())
    _audit(
        cur,
        company_code=company,
        action="measure_created",
        actor_phone=actor_phone,
        reason=reason,
        subject_type="measure",
        subject_id=str(row["measure_id"]),
        payload={"direction": d, "source": src},
    )
    # Initial target version
    cur.execute(
        """
        INSERT INTO perf_target_versions (
          company_code, subject_type, subject_id, measure_id,
          baseline, target, range_low, range_high, reason, created_by_phone
        ) VALUES (%s,'measure',%s,%s,%s,%s,%s,%s,%s,%s)
        """,
        (
            company,
            row["measure_id"],
            row["measure_id"],
            row.get("baseline"),
            row.get("target"),
            row.get("range_low"),
            row.get("range_high"),
            "initial",
            _digits(actor_phone),
        ),
    )
    return {"ok": True, "measure": row, **honesty_payload(company_code=company)}


def change_measure_targets(
    cur: Any,
    *,
    company_code: str,
    measure_id: str,
    actor_phone: str,
    reason: str,
    baseline: Any = None,
    target: Any = None,
    range_low: Any = None,
    range_high: Any = None,
) -> dict[str, Any]:
    if not str(reason or "").strip():
        return {"ok": False, "error": "audit_reason_required"}
    enabled = module_enabled_for_company(cur, company_code)
    if not enabled.get("ok"):
        return enabled
    company = company_code_norm(company_code)
    cur.execute(
        "SELECT * FROM perf_measure_definitions WHERE company_code=%s AND measure_id=%s",
        (company, measure_id),
    )
    m = cur.fetchone()
    if not m:
        return {"ok": False, "error": "measure_not_found"}
    m = dict(m)
    new_base = _dec(baseline) if baseline is not None else m.get("baseline")
    new_tgt = _dec(target) if target is not None else m.get("target")
    new_lo = _dec(range_low) if range_low is not None else m.get("range_low")
    new_hi = _dec(range_high) if range_high is not None else m.get("range_high")
    cur.execute(
        """
        UPDATE perf_measure_definitions
           SET baseline=%s, target=%s, range_low=%s, range_high=%s,
               version=version+1, updated_at=now()
         WHERE company_code=%s AND measure_id=%s
        RETURNING *
        """,
        (new_base, new_tgt, new_lo, new_hi, company, measure_id),
    )
    row = dict(cur.fetchone())
    cur.execute(
        """
        INSERT INTO perf_target_versions (
          company_code, subject_type, subject_id, measure_id,
          baseline, target, range_low, range_high, reason, created_by_phone
        ) VALUES (%s,'measure',%s,%s,%s,%s,%s,%s,%s,%s)
        RETURNING *
        """,
        (
            company,
            measure_id,
            measure_id,
            new_base,
            new_tgt,
            new_lo,
            new_hi,
            str(reason).strip()[:500],
            _digits(actor_phone),
        ),
    )
    ver = dict(cur.fetchone())
    _audit(
        cur,
        company_code=company,
        action="measure_targets_versioned",
        actor_phone=actor_phone,
        reason=reason,
        subject_type="measure",
        subject_id=str(measure_id),
        payload={"version": row.get("version")},
    )
    return {"ok": True, "measure": row, "target_version": ver, **honesty_payload(company_code=company)}


def create_objective(
    cur: Any,
    *,
    company_code: str,
    actor_phone: str,
    title_en: str,
    scope: str,
    owner_employee_key: str | None = None,
    org_unit_id: str | None = None,
    title_ar: str | None = None,
    period_start: date | str | None = None,
    period_end: date | str | None = None,
    weight: Any = None,
    reason: str = "create objective",
) -> dict[str, Any]:
    enabled = module_enabled_for_company(cur, company_code)
    if not enabled.get("ok"):
        return enabled
    settings = enabled["settings"]
    if not settings.get("okrs_enabled"):
        return {"ok": False, "error": "okrs_disabled", "gate": "okrs_enabled"}
    sc = str(scope or "").strip().lower()
    allowed = settings.get("allowed_scopes") or list(SCOPES)
    if isinstance(allowed, str):
        allowed = json.loads(allowed)
    if sc not in SCOPES or sc not in {str(x) for x in allowed}:
        return {"ok": False, "error": "scope_not_allowed", "allowed": allowed}
    if not str(title_en or "").strip():
        return {"ok": False, "error": "title_required"}
    company = company_code_norm(company_code)
    cur.execute(
        """
        INSERT INTO perf_objectives (
          company_code, title_en, title_ar, scope, owner_employee_key, org_unit_id,
          status, period_start, period_end, weight, created_by_phone
        ) VALUES (%s,%s,%s,%s,%s,%s,'draft',%s,%s,%s,%s)
        RETURNING *
        """,
        (
            company,
            str(title_en).strip()[:500],
            (str(title_ar).strip()[:500] if title_ar else None),
            sc,
            owner_employee_key,
            org_unit_id,
            str(period_start)[:10] if period_start else None,
            str(period_end)[:10] if period_end else None,
            _dec(weight),
            _digits(actor_phone),
        ),
    )
    row = dict(cur.fetchone())
    _audit(
        cur,
        company_code=company,
        action="objective_created",
        actor_phone=actor_phone,
        reason=reason,
        subject_type="objective",
        subject_id=str(row["objective_id"]),
        payload={"scope": sc},
    )
    return {
        "ok": True,
        "objective": row,
        "entity": "objective",
        "not_generic_goal": True,
        **honesty_payload(company_code=company),
    }


def add_key_result(
    cur: Any,
    *,
    company_code: str,
    objective_id: str,
    actor_phone: str,
    title_en: str,
    measure_id: str,
    weight: Any = 1,
    title_ar: str | None = None,
    reason: str = "add key result",
) -> dict[str, Any]:
    enabled = module_enabled_for_company(cur, company_code)
    if not enabled.get("ok"):
        return enabled
    if not enabled["settings"].get("okrs_enabled"):
        return {"ok": False, "error": "okrs_disabled"}
    company = company_code_norm(company_code)
    cur.execute(
        "SELECT * FROM perf_objectives WHERE company_code=%s AND objective_id=%s",
        (company, objective_id),
    )
    obj = cur.fetchone()
    if not obj:
        return {"ok": False, "error": "objective_not_found"}
    cur.execute(
        "SELECT * FROM perf_measure_definitions WHERE company_code=%s AND measure_id=%s",
        (company, measure_id),
    )
    if not cur.fetchone():
        return {"ok": False, "error": "measure_not_found", "message": "KR requires measure contract"}
    if not str(title_en or "").strip():
        return {"ok": False, "error": "title_required"}
    w = _dec(weight) or Decimal("1")
    cur.execute(
        """
        INSERT INTO perf_key_results (
          company_code, objective_id, title_en, title_ar, measure_id, weight,
          status, created_by_phone
        ) VALUES (%s,%s,%s,%s,%s,%s,'draft',%s)
        RETURNING *
        """,
        (
            company,
            objective_id,
            str(title_en).strip()[:500],
            (str(title_ar).strip()[:500] if title_ar else None),
            measure_id,
            w,
            _digits(actor_phone),
        ),
    )
    row = dict(cur.fetchone())
    _audit(
        cur,
        company_code=company,
        action="key_result_created",
        actor_phone=actor_phone,
        reason=reason,
        subject_type="key_result",
        subject_id=str(row["key_result_id"]),
        payload={"objective_id": str(objective_id), "measure_id": str(measure_id)},
    )
    return {
        "ok": True,
        "key_result": row,
        "entity": "key_result",
        "not_kpi_alias": True,
        **honesty_payload(company_code=company),
    }


def activate_objective(
    cur: Any, *, company_code: str, objective_id: str, actor_phone: str, reason: str
) -> dict[str, Any]:
    enabled = module_enabled_for_company(cur, company_code)
    if not enabled.get("ok"):
        return enabled
    company = company_code_norm(company_code)
    cur.execute(
        "SELECT count(*) AS c FROM perf_key_results WHERE objective_id=%s AND status != 'cancelled'",
        (objective_id,),
    )
    if int((cur.fetchone() or {}).get("c") or 0) < 1:
        return {"ok": False, "error": "objective_requires_at_least_one_key_result"}
    cur.execute(
        """
        UPDATE perf_objectives
           SET status='active', row_version=row_version+1, updated_at=now()
         WHERE company_code=%s AND objective_id=%s AND status='draft'
        RETURNING *
        """,
        (company, objective_id),
    )
    obj = cur.fetchone()
    if not obj:
        return {"ok": False, "error": "objective_not_draft_or_missing"}
    cur.execute(
        """
        UPDATE perf_key_results
           SET status='active', row_version=row_version+1, updated_at=now()
         WHERE company_code=%s AND objective_id=%s AND status='draft'
        """,
        (company, objective_id),
    )
    _audit(
        cur,
        company_code=company,
        action="objective_activated",
        actor_phone=actor_phone,
        reason=reason,
        subject_type="objective",
        subject_id=str(objective_id),
    )
    return {"ok": True, "objective": dict(obj), **honesty_payload(company_code=company)}


def create_goal(
    cur: Any,
    *,
    company_code: str,
    actor_phone: str,
    goal_kind: str,
    title_en: str,
    scope: str,
    measure_id: str | None = None,
    owner_employee_key: str | None = None,
    org_unit_id: str | None = None,
    title_ar: str | None = None,
    period_start: date | str | None = None,
    period_end: date | str | None = None,
    weight: Any = None,
    reason: str = "create goal",
) -> dict[str, Any]:
    enabled = module_enabled_for_company(cur, company_code)
    if not enabled.get("ok"):
        return enabled
    settings = enabled["settings"]
    kind = str(goal_kind or "").strip().lower()
    if kind not in GOAL_KINDS:
        return {
            "ok": False,
            "error": "invalid_goal_kind",
            "allowed": list(GOAL_KINDS),
            "message": "Use objective/key_result entities for OKRs — do not store as goal_kind.",
        }
    flag = {
        "kpi": "kpi_goals_enabled",
        "milestone": "milestone_goals_enabled",
        "development": "development_goals_enabled",
    }[kind]
    if not settings.get(flag):
        return {"ok": False, "error": f"{kind}_goals_disabled"}
    sc = str(scope or "").strip().lower()
    allowed = settings.get("allowed_scopes") or list(SCOPES)
    if isinstance(allowed, str):
        allowed = json.loads(allowed)
    if sc not in SCOPES or sc not in {str(x) for x in allowed}:
        return {"ok": False, "error": "scope_not_allowed", "allowed": allowed}
    company = company_code_norm(company_code)
    if kind in ("kpi", "milestone") and not measure_id:
        return {"ok": False, "error": "measure_contract_required", "goal_kind": kind}
    if measure_id:
        cur.execute(
            "SELECT measure_id FROM perf_measure_definitions WHERE company_code=%s AND measure_id=%s",
            (company, measure_id),
        )
        if not cur.fetchone():
            return {"ok": False, "error": "measure_not_found"}
    cur.execute(
        """
        INSERT INTO perf_goals (
          company_code, goal_kind, title_en, title_ar, scope, owner_employee_key, org_unit_id,
          measure_id, weight, status, period_start, period_end, created_by_phone
        ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,'draft',%s,%s,%s)
        RETURNING *
        """,
        (
            company,
            kind,
            str(title_en).strip()[:500],
            (str(title_ar).strip()[:500] if title_ar else None),
            sc,
            owner_employee_key,
            org_unit_id,
            measure_id,
            _dec(weight),
            str(period_start)[:10] if period_start else None,
            str(period_end)[:10] if period_end else None,
            _digits(actor_phone),
        ),
    )
    row = dict(cur.fetchone())
    _audit(
        cur,
        company_code=company,
        action="goal_created",
        actor_phone=actor_phone,
        reason=reason,
        subject_type="goal",
        subject_id=str(row["goal_id"]),
        payload={"goal_kind": kind},
    )
    return {"ok": True, "goal": row, "entity": "goal", **honesty_payload(company_code=company)}


def activate_goal(
    cur: Any, *, company_code: str, goal_id: str, actor_phone: str, reason: str
) -> dict[str, Any]:
    enabled = module_enabled_for_company(cur, company_code)
    if not enabled.get("ok"):
        return enabled
    company = company_code_norm(company_code)
    cur.execute(
        """
        UPDATE perf_goals
           SET status='active', row_version=row_version+1, updated_at=now()
         WHERE company_code=%s AND goal_id=%s AND status='draft'
        RETURNING *
        """,
        (company, goal_id),
    )
    row = cur.fetchone()
    if not row:
        return {"ok": False, "error": "goal_not_draft_or_missing"}
    _audit(
        cur,
        company_code=company,
        action="goal_activated",
        actor_phone=actor_phone,
        reason=reason,
        subject_type="goal",
        subject_id=str(goal_id),
    )
    return {"ok": True, "goal": dict(row), **honesty_payload(company_code=company)}


def reject_decorative_progress_pct(*, progress_pct: Any) -> dict[str, Any]:
    """API guard — free-typed % is never accepted as SoT."""
    return {
        "ok": False,
        "error": "decorative_progress_pct_forbidden",
        "message": "Record a measured current_value via record_progress; progress is computed from the measure contract.",
        "rejected_value": progress_pct,
        **honesty_payload(),
    }


def record_progress(
    cur: Any,
    *,
    company_code: str,
    subject_type: str,
    subject_id: str,
    actor_phone: str,
    current_value: Any,
    source: str = "manual",
    note: str | None = None,
    progress_pct: Any = None,
) -> dict[str, Any]:
    if progress_pct is not None:
        return reject_decorative_progress_pct(progress_pct=progress_pct)
    enabled = module_enabled_for_company(cur, company_code)
    if not enabled.get("ok"):
        return enabled
    st = str(subject_type or "").strip().lower()
    if st not in ("key_result", "goal"):
        return {"ok": False, "error": "invalid_subject_type"}
    src = str(source or "manual").strip().lower()
    if src not in SOURCES:
        return {"ok": False, "error": "invalid_source", "allowed": list(SOURCES)}
    cur_v = _dec(current_value)
    if cur_v is None:
        return {"ok": False, "error": "current_value_required"}
    company = company_code_norm(company_code)
    measure = None
    if st == "key_result":
        cur.execute(
            """
            SELECT kr.*, m.direction, m.baseline, m.target, m.range_low, m.range_high, m.measure_id AS mid
              FROM perf_key_results kr
              JOIN perf_measure_definitions m ON m.measure_id=kr.measure_id
             WHERE kr.company_code=%s AND kr.key_result_id=%s
            """,
            (company, subject_id),
        )
        row = cur.fetchone()
        if not row:
            return {"ok": False, "error": "key_result_not_found"}
        measure = dict(row)
        cur.execute(
            """
            UPDATE perf_key_results
               SET current_value=%s, row_version=row_version+1, updated_at=now()
             WHERE key_result_id=%s
            """,
            (cur_v, subject_id),
        )
    else:
        cur.execute(
            """
            SELECT g.*, m.direction, m.baseline, m.target, m.range_low, m.range_high, m.measure_id AS mid
              FROM perf_goals g
              LEFT JOIN perf_measure_definitions m ON m.measure_id=g.measure_id
             WHERE g.company_code=%s AND g.goal_id=%s
            """,
            (company, subject_id),
        )
        row = cur.fetchone()
        if not row:
            return {"ok": False, "error": "goal_not_found"}
        measure = dict(row)
        if not measure.get("mid") and measure.get("goal_kind") != "development":
            return {"ok": False, "error": "measure_contract_required"}
        if measure.get("mid"):
            cur.execute(
                """
                UPDATE perf_goals
                   SET current_value=%s, row_version=row_version+1, updated_at=now()
                 WHERE goal_id=%s
                """,
                (cur_v, subject_id),
            )
        else:
            # development goal without measure: milestone-like 0/1 only via measure engine with direction milestone
            measure = {
                "direction": "milestone",
                "baseline": 0,
                "target": 1,
                "mid": None,
            }
            cur.execute(
                """
                UPDATE perf_goals
                   SET current_value=%s, row_version=row_version+1, updated_at=now()
                 WHERE goal_id=%s
                """,
                (cur_v, subject_id),
            )

    computed = compute_progress(
        direction=str(measure.get("direction") or "higher_is_better"),
        baseline=measure.get("baseline"),
        target=measure.get("target"),
        current=cur_v,
        range_low=measure.get("range_low"),
        range_high=measure.get("range_high"),
    )
    if not computed.get("ok"):
        return computed
    cur.execute(
        """
        INSERT INTO perf_progress_entries (
          company_code, subject_type, subject_id, measure_id, current_value,
          computed_progress_pct, computed_status, source, note, recorded_by_phone
        ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
        RETURNING *
        """,
        (
            company,
            st,
            subject_id,
            measure.get("mid") or measure.get("measure_id"),
            cur_v,
            computed.get("progress_pct"),
            computed.get("status"),
            src,
            (str(note).strip()[:500] if note else None),
            _digits(actor_phone),
        ),
    )
    entry = dict(cur.fetchone())
    _audit(
        cur,
        company_code=company,
        action="progress_recorded",
        actor_phone=actor_phone,
        subject_type=st,
        subject_id=str(subject_id),
        payload={"current_value": str(cur_v), "progress_pct": computed.get("progress_pct")},
    )
    return {
        "ok": True,
        "entry": entry,
        "computed": computed,
        **honesty_payload(company_code=company),
    }


def objective_rollup(cur: Any, *, company_code: str, objective_id: str) -> dict[str, Any]:
    company = company_code_norm(company_code)
    cur.execute(
        """
        SELECT kr.key_result_id, kr.weight, kr.current_value, kr.status,
               m.direction, m.baseline, m.target, m.range_low, m.range_high
          FROM perf_key_results kr
          JOIN perf_measure_definitions m ON m.measure_id=kr.measure_id
         WHERE kr.company_code=%s AND kr.objective_id=%s
           AND kr.status NOT IN ('cancelled','archived')
        """,
        (company, objective_id),
    )
    rows = [dict(r) for r in (cur.fetchall() or [])]
    if not rows:
        return {"ok": False, "error": "no_key_results"}
    total_w = Decimal("0")
    acc = Decimal("0")
    unknown = 0
    parts = []
    for r in rows:
        w = _dec(r.get("weight")) or Decimal("1")
        total_w += w
        c = compute_progress(
            direction=str(r.get("direction")),
            baseline=r.get("baseline"),
            target=r.get("target"),
            current=r.get("current_value"),
            range_low=r.get("range_low"),
            range_high=r.get("range_high"),
        )
        pct = c.get("progress_pct")
        if pct is None:
            unknown += 1
            parts.append({"key_result_id": str(r["key_result_id"]), "progress_pct": None, "weight": float(w)})
            continue
        acc += w * Decimal(str(pct))
        parts.append({"key_result_id": str(r["key_result_id"]), "progress_pct": pct, "weight": float(w)})
    if total_w == 0:
        return {"ok": False, "error": "zero_weights"}
    if unknown == len(rows):
        return {
            "ok": True,
            "progress_pct": None,
            "status": "not_started",
            "key_results": parts,
            "message": "All KRs lack current values — objective progress unknown (not 100%).",
            "formula_version": "okr_rollup_v1",
        }
    # Weight only KRs with known progress for rollup; document unknown count
    known_w = sum(
        (Decimal(str(p["weight"])) for p in parts if p["progress_pct"] is not None),
        Decimal("0"),
    )
    if known_w == 0:
        rollup = None
    else:
        rollup = float(acc / known_w)
    return {
        "ok": True,
        "progress_pct": round(rollup, 4) if rollup is not None else None,
        "status": "on_track" if rollup and rollup > 0 else "not_started",
        "unknown_kr_count": unknown,
        "key_results": parts,
        "formula_version": "okr_rollup_v1",
        **honesty_payload(company_code=company),
    }


def create_alignment_link(
    cur: Any,
    *,
    company_code: str,
    actor_phone: str,
    from_type: str,
    from_id: str,
    to_type: str,
    to_id: str,
    link_kind: str = "aligned",
    reason: str = "align",
) -> dict[str, Any]:
    enabled = module_enabled_for_company(cur, company_code)
    if not enabled.get("ok"):
        return enabled
    settings = enabled["settings"]
    if settings.get("force_rigid_cascade"):
        return {"ok": False, "error": "rigid_cascade_forbidden_by_charter"}
    if not settings.get("allow_alignment_links"):
        return {"ok": False, "error": "alignment_links_disabled"}
    ft = str(from_type).strip().lower()
    tt = str(to_type).strip().lower()
    if ft not in ("objective", "key_result", "goal") or tt not in ("objective", "key_result", "goal"):
        return {"ok": False, "error": "invalid_alignment_types"}
    company = company_code_norm(company_code)
    cur.execute(
        """
        INSERT INTO perf_alignment_links (
          company_code, from_type, from_id, to_type, to_id, link_kind, created_by_phone
        ) VALUES (%s,%s,%s,%s,%s,%s,%s)
        RETURNING *
        """,
        (company, ft, from_id, tt, to_id, str(link_kind or "aligned"), _digits(actor_phone)),
    )
    row = dict(cur.fetchone())
    _audit(
        cur,
        company_code=company,
        action="alignment_linked",
        actor_phone=actor_phone,
        reason=reason,
        subject_type="alignment_link",
        subject_id=str(row["link_id"]),
        payload={"from_type": ft, "to_type": tt, "forced_cascade": False},
    )
    return {
        "ok": True,
        "link": row,
        "inherits_score": False,
        "forced_cascade": False,
        **honesty_payload(company_code=company),
    }


def list_target_versions(
    cur: Any, *, company_code: str, subject_type: str, subject_id: str
) -> list[dict[str, Any]]:
    cur.execute(
        """
        SELECT * FROM perf_target_versions
         WHERE company_code=%s AND subject_type=%s AND subject_id=%s
         ORDER BY created_at ASC
        """,
        (company_code_norm(company_code), subject_type, subject_id),
    )
    return [dict(r) for r in (cur.fetchall() or [])]
