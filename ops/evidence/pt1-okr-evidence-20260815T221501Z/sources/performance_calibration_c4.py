#!/usr/bin/env python3
"""Wave 4 C4 — Rating Aggregation + Performance Calibration (company-scoped).

Owner-approved under WAVE4_PERFORMANCE_TALENT_CHARTER (2026-08-12) §0.8.3 + W4.6.

Authorities:
  - versioned calculation policy → deterministic pre_calibration_result
  - calibration_session (draft→prepared→in_session→completed→locked|cancelled)
  - calibrated/final_result as separate layer (never erases originals)
  - distribution guidance vs hard constraint (never assumed bell curve)

Does NOT:
  - assign potential / HiPo / 9-box / succession / talent rankings
  - silently treat missing/not-observed as 0 or 100
  - mutate historical ratings when scales/policies are later edited
  - force distribution curves

Gates (fail-closed):
  1) WATHEFNI_PERFORMANCE_CALIBRATION_C4 must be on
  2) company in WATHEFNI_PERFORMANCE_CALIBRATION_COMPANIES (empty = nobody)
  3) company entitlement in performance_calibration_c4_company_settings
"""
from __future__ import annotations

import json
import math
import os
from copy import deepcopy
from datetime import datetime
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Any

PHASE = "performance_calibration_c4"
CONTRACT_VERSION = "performance_calibration_c4_v1"
CALC_POLICY_VERSION = "calc_policy_v1"
PASS_STAMP = "PERFORMANCE_CALIBRATION_DEV_FULL_PASS"
COMMERCIAL_MODULE_KEY = "performance"
_ON = {"1", "true", "yes", "on"}

SESSION_STATES = ("draft", "prepared", "in_session", "completed", "locked", "cancelled")
MISSING_RULES = ("exclude_from_denominator", "block_finalization", "neutral_default")
DIST_MODES = ("none", "guidance", "hard_constraint")
COMPONENT_KINDS = (
    "goals",
    "objectives_krs",
    "kpis",
    "competencies",
    "manager",
    "self",
    "multi_rater_360",
    "section",
)

STATUS_LABELS = {
    "draft": {"en": "Draft", "ar": "مسودة"},
    "prepared": {"en": "Prepared", "ar": "مُجهَّز"},
    "in_session": {"en": "In session", "ar": "جلسة جارية"},
    "completed": {"en": "Completed", "ar": "مكتمل"},
    "locked": {"en": "Locked", "ar": "مقفل"},
    "cancelled": {"en": "Cancelled", "ar": "ملغى"},
    "exclude_from_denominator": {
        "en": "Excluded from denominator",
        "ar": "مستبعد من المقام",
    },
    "block_finalization": {"en": "Blocks finalization", "ar": "يمنع الإنهاء"},
    "neutral_default": {"en": "Neutral default", "ar": "قيمة محايدة افتراضية"},
    "guidance": {"en": "Distribution guidance", "ar": "إرشاد توزيع"},
    "hard_constraint": {"en": "Hard distribution constraint", "ar": "قيد توزيع صارم"},
    "pre_calibration": {"en": "Pre-calibration result", "ar": "نتيجة ما قبل المعايرة"},
    "calibrated_final": {"en": "Calibrated final", "ar": "نهائي بعد المعايرة"},
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


def performance_calibration_c4_runtime_on() -> bool:
    return _env_on("WATHEFNI_PERFORMANCE_CALIBRATION_C4", "off")


def performance_calibration_company_allowlist() -> set[str]:
    raw = str(os.environ.get("WATHEFNI_PERFORMANCE_CALIBRATION_COMPANIES") or "").strip()
    if not raw:
        return set()
    return {p.strip().upper() for p in raw.split(",") if p.strip()}


def honesty_payload(*, company_code: str | None = None) -> dict[str, Any]:
    return {
        "phase": PHASE,
        "contract_version": CONTRACT_VERSION,
        "calc_policy_version": CALC_POLICY_VERSION,
        "pass_stamp": PASS_STAMP,
        "commercial_module_key": COMMERCIAL_MODULE_KEY,
        "assistant_mutations": False,
        "aggregation_deterministic_and_replayable": True,
        "components_preserved_separately": True,
        "missing_evidence_never_silent_zero_or_full": True,
        "no_universal_1_to_5_assumption": True,
        "uses_c2_versioned_rating_scales": True,
        "scale_edits_do_not_mutate_history": True,
        "calibration_is_separate_governed_layer": True,
        "calibration_never_erases_submitted_or_pre_cal": True,
        "forced_distribution_never_assumed": True,
        "distribution_guidance_vs_hard_constraint": True,
        "provisional_calibration_hidden_by_default": True,
        "raw_360_confidentiality_preserved": True,
        "calibration_requires_sensitive_permission": True,
        "talent_potential_hipo_9box_succession_out": True,
        "produces_performance_outcomes_only": True,
        "locked_results_immutable_except_audited_amendment": True,
        "company_code": company_code_norm(company_code) if company_code else None,
    }


def rollback_guidance() -> dict[str, Any]:
    return {
        "phase": PHASE,
        "preserves_history": True,
        "steps": [
            "WATHEFNI_PERFORMANCE_CALIBRATION_C4=off",
            "Clear WATHEFNI_PERFORMANCE_CALIBRATION_COMPANIES",
            "WATHEFNI_PERFORMANCE_KILL=on (optional immediate block)",
            "Disable company Setup entitlement (preserves aggregation + calibration history)",
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
    if not performance_calibration_c4_runtime_on():
        return {
            "ok": False,
            "enabled": False,
            "error": "performance_calibration_c4_off",
            "gate": "runtime_flag",
            "phase": PHASE,
        }
    allow = performance_calibration_company_allowlist()
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
                "error": "performance_calibration_company_not_allowlisted",
                "gate": "company_allowlist",
                "phase": PHASE,
                "company_code": company,
                "message": "Performance-calibration allowlist empty — fail closed (nobody).",
            }
    return {"ok": True, "enabled": True, "company_code": company, "phase": PHASE}


def ensure_performance_calibration_c4_schema(cur: Any, *, force: bool = False) -> None:
    _ = force
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS performance_calibration_c4_company_settings (
          company_code text PRIMARY KEY,
          enabled boolean NOT NULL DEFAULT false,
          aggregation_enabled boolean NOT NULL DEFAULT true,
          calibration_enabled boolean NOT NULL DEFAULT true,
          provisional_visible_to_employees boolean NOT NULL DEFAULT false,
          require_sensitive_permission boolean NOT NULL DEFAULT true,
          sod_lock_requires_other_actor boolean NOT NULL DEFAULT false,
          default_missing_rule text NOT NULL DEFAULT 'exclude_from_denominator',
          forced_distribution_assumed boolean NOT NULL DEFAULT false,
          enabled_by_phone text,
          enabled_reason text,
          enabled_at timestamptz,
          disabled_at timestamptz,
          updated_by_phone text,
          updated_at timestamptz NOT NULL DEFAULT now(),
          metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
          CONSTRAINT perf_c4_missing_chk CHECK (default_missing_rule IN (
            'exclude_from_denominator','block_finalization','neutral_default'
          )),
          CONSTRAINT perf_c4_no_forced_chk CHECK (forced_distribution_assumed = false)
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS perf_calc_policies (
          policy_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
          company_code text NOT NULL,
          name_en text NOT NULL,
          name_ar text,
          version int NOT NULL DEFAULT 1,
          status text NOT NULL DEFAULT 'active',
          component_weights jsonb NOT NULL,
          missing_rule text NOT NULL DEFAULT 'exclude_from_denominator',
          neutral_default_normalized numeric,
          rounding_mode text NOT NULL DEFAULT 'half_up',
          rounding_decimals int NOT NULL DEFAULT 2,
          scale_snapshot jsonb NOT NULL,
          policy_contract_version text NOT NULL DEFAULT 'calc_policy_v1',
          created_by_phone text,
          created_at timestamptz NOT NULL DEFAULT now(),
          updated_at timestamptz NOT NULL DEFAULT now(),
          metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
          CONSTRAINT perf_calc_missing_chk CHECK (missing_rule IN (
            'exclude_from_denominator','block_finalization','neutral_default'
          )),
          CONSTRAINT perf_calc_status_chk CHECK (status IN ('active','deprecated'))
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS perf_pre_calibration_results (
          result_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
          company_code text NOT NULL,
          cycle_id uuid,
          subject_employee_key text NOT NULL,
          policy_id uuid NOT NULL,
          policy_version int NOT NULL,
          policy_contract_version text NOT NULL,
          scale_snapshot jsonb NOT NULL,
          component_inputs jsonb NOT NULL,
          weights jsonb NOT NULL,
          missing_rule_applied text NOT NULL,
          blocked boolean NOT NULL DEFAULT false,
          block_reason text,
          raw_aggregate numeric,
          display_result numeric,
          display_label text,
          calculation_trace jsonb NOT NULL DEFAULT '{}'::jsonb,
          row_version int NOT NULL DEFAULT 1,
          created_by_phone text,
          created_at timestamptz NOT NULL DEFAULT now(),
          UNIQUE (company_code, cycle_id, subject_employee_key, policy_id, policy_version)
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS perf_calibration_sessions (
          session_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
          company_code text NOT NULL,
          cycle_id uuid NOT NULL,
          name_en text NOT NULL,
          name_ar text,
          status text NOT NULL DEFAULT 'draft',
          facilitator_phone text NOT NULL,
          owner_phone text,
          visibility_rules jsonb NOT NULL DEFAULT '{}'::jsonb,
          policy_snapshot jsonb NOT NULL DEFAULT '{}'::jsonb,
          distribution_mode text NOT NULL DEFAULT 'none',
          distribution_policy jsonb NOT NULL DEFAULT '{}'::jsonb,
          population_frozen_at timestamptz,
          locked_at timestamptz,
          locked_by_phone text,
          published_at timestamptz,
          row_version int NOT NULL DEFAULT 1,
          created_by_phone text,
          created_at timestamptz NOT NULL DEFAULT now(),
          updated_at timestamptz NOT NULL DEFAULT now(),
          metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
          CONSTRAINT perf_csess_status_chk CHECK (status IN (
            'draft','prepared','in_session','completed','locked','cancelled'
          )),
          CONSTRAINT perf_csess_dist_chk CHECK (distribution_mode IN (
            'none','guidance','hard_constraint'
          ))
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS perf_calibration_population (
          population_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
          company_code text NOT NULL,
          session_id uuid NOT NULL REFERENCES perf_calibration_sessions(session_id),
          subject_employee_key text NOT NULL,
          manager_employee_key text,
          manager_phone text,
          pre_calibration_result_id uuid,
          frozen_manager_rating numeric,
          frozen_self_rating numeric,
          frozen_360_aggregate numeric,
          frozen_at timestamptz NOT NULL DEFAULT now(),
          UNIQUE (session_id, subject_employee_key)
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS perf_calibration_participants (
          participant_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
          company_code text NOT NULL,
          session_id uuid NOT NULL REFERENCES perf_calibration_sessions(session_id),
          participant_phone text NOT NULL,
          participant_role text NOT NULL DEFAULT 'manager',
          scoped_employee_keys jsonb NOT NULL DEFAULT '[]'::jsonb,
          created_at timestamptz NOT NULL DEFAULT now(),
          UNIQUE (session_id, participant_phone),
          CONSTRAINT perf_cpart_role_chk CHECK (participant_role IN (
            'facilitator','manager','hr_observer'
          ))
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS perf_calibration_adjustments (
          adjustment_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
          company_code text NOT NULL,
          session_id uuid NOT NULL REFERENCES perf_calibration_sessions(session_id),
          subject_employee_key text NOT NULL,
          prior_value numeric,
          prior_label text,
          new_value numeric,
          new_label text,
          actor_phone text NOT NULL,
          reason text NOT NULL,
          expected_row_version int NOT NULL,
          distribution_exception boolean NOT NULL DEFAULT false,
          distribution_exception_reason text,
          created_at timestamptz NOT NULL DEFAULT now(),
          metadata jsonb NOT NULL DEFAULT '{}'::jsonb
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS perf_calibrated_results (
          calibrated_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
          company_code text NOT NULL,
          session_id uuid NOT NULL,
          cycle_id uuid NOT NULL,
          subject_employee_key text NOT NULL,
          pre_calibration_result_id uuid,
          pre_calibration_value numeric,
          pre_calibration_label text,
          final_value numeric,
          final_label text,
          status text NOT NULL DEFAULT 'provisional',
          row_version int NOT NULL DEFAULT 1,
          published_at timestamptz,
          locked_at timestamptz,
          created_at timestamptz NOT NULL DEFAULT now(),
          updated_at timestamptz NOT NULL DEFAULT now(),
          metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
          UNIQUE (session_id, subject_employee_key),
          CONSTRAINT perf_calres_status_chk CHECK (status IN (
            'provisional','published','locked','amended'
          ))
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS perf_calibration_amendments (
          amendment_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
          company_code text NOT NULL,
          calibrated_id uuid NOT NULL REFERENCES perf_calibrated_results(calibrated_id),
          session_id uuid NOT NULL,
          before_payload jsonb NOT NULL,
          after_payload jsonb NOT NULL,
          reason text NOT NULL,
          actor_phone text NOT NULL,
          created_at timestamptz NOT NULL DEFAULT now()
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS performance_calibration_c4_audit (
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
        "CREATE INDEX IF NOT EXISTS perf_precal_cycle_idx ON perf_pre_calibration_results(cycle_id, subject_employee_key)",
        "CREATE INDEX IF NOT EXISTS perf_csess_company_idx ON perf_calibration_sessions(company_code, status)",
        "CREATE INDEX IF NOT EXISTS perf_cpop_session_idx ON perf_calibration_population(session_id)",
        "CREATE INDEX IF NOT EXISTS perf_cadj_session_idx ON perf_calibration_adjustments(session_id, subject_employee_key)",
        "CREATE INDEX IF NOT EXISTS perf_calres_session_idx ON perf_calibrated_results(session_id, status)",
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
        INSERT INTO performance_calibration_c4_audit (
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
    ensure_performance_calibration_c4_schema(cur)
    cur.execute(
        "SELECT * FROM performance_calibration_c4_company_settings WHERE company_code=%s",
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
            "error": "performance_calibration_company_not_enabled",
            "gate": "company_settings",
            "phase": PHASE,
        }
    if feature == "aggregation" and not settings.get("aggregation_enabled"):
        return {"ok": False, "error": "aggregation_disabled", "gate": "feature"}
    if feature == "calibration" and not settings.get("calibration_enabled"):
        return {"ok": False, "error": "calibration_disabled", "gate": "feature"}
    return {"ok": True, "settings": settings, "company_code": company_code_norm(company_code)}


def enable_company_performance_calibration(
    cur: Any,
    *,
    company_code: str,
    actor_phone: str,
    reason: str,
    provisional_visible_to_employees: bool = False,
    require_sensitive_permission: bool = True,
    sod_lock_requires_other_actor: bool = False,
    default_missing_rule: str = "exclude_from_denominator",
) -> dict[str, Any]:
    if not str(reason or "").strip():
        return {"ok": False, "error": "audit_reason_required"}
    gate = runtime_gate_for_company(company_code)
    if not gate.get("ok"):
        return gate
    rule = str(default_missing_rule or "exclude_from_denominator").strip().lower()
    if rule not in MISSING_RULES:
        return {"ok": False, "error": "invalid_missing_rule", "allowed": list(MISSING_RULES)}
    company = company_code_norm(company_code)
    ensure_performance_calibration_c4_schema(cur)
    cur.execute(
        """
        INSERT INTO performance_calibration_c4_company_settings (
          company_code, enabled, aggregation_enabled, calibration_enabled,
          provisional_visible_to_employees, require_sensitive_permission,
          sod_lock_requires_other_actor, default_missing_rule, forced_distribution_assumed,
          enabled_by_phone, enabled_reason, enabled_at, updated_by_phone, updated_at, disabled_at
        ) VALUES (%s,true,true,true,%s,%s,%s,%s,false,%s,%s,now(),%s,now(),NULL)
        ON CONFLICT (company_code) DO UPDATE SET
          enabled=true,
          aggregation_enabled=true,
          calibration_enabled=true,
          provisional_visible_to_employees=EXCLUDED.provisional_visible_to_employees,
          require_sensitive_permission=EXCLUDED.require_sensitive_permission,
          sod_lock_requires_other_actor=EXCLUDED.sod_lock_requires_other_actor,
          default_missing_rule=EXCLUDED.default_missing_rule,
          forced_distribution_assumed=false,
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
            bool(provisional_visible_to_employees),
            bool(require_sensitive_permission),
            bool(sod_lock_requires_other_actor),
            rule,
            _digits(actor_phone),
            str(reason).strip()[:500],
            _digits(actor_phone),
        ),
    )
    row = dict(cur.fetchone())
    _audit(
        cur, company_code=company, action="company_enabled", actor_phone=actor_phone,
        reason=reason, subject_type="company", subject_id=company,
        payload={"forced_distribution_assumed": False},
    )
    return {"ok": True, "settings": row}


def disable_company_performance_calibration(
    cur: Any, *, company_code: str, actor_phone: str, reason: str
) -> dict[str, Any]:
    if not str(reason or "").strip():
        return {"ok": False, "error": "audit_reason_required"}
    company = company_code_norm(company_code)
    ensure_performance_calibration_c4_schema(cur)
    cur.execute(
        """
        UPDATE performance_calibration_c4_company_settings
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


# ── Scale helpers / deterministic aggregation ───────────────────────────────


def _dec(value: Any) -> Decimal | None:
    if value is None or value == "":
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None


def normalize_scale_point(
    *,
    scale_snapshot: dict[str, Any],
    value: Any = None,
    label: str | None = None,
    not_observed: bool = False,
) -> dict[str, Any]:
    """Map a rating onto a 0–1 normalized axis using the frozen scale snapshot."""
    if not_observed or (value is None and not label):
        return {"ok": True, "normalized": None, "missing": True, "not_observed": bool(not_observed)}
    points = scale_snapshot.get("points") or []
    if isinstance(points, str):
        points = json.loads(points)
    scale_type = str(scale_snapshot.get("scale_type") or "numeric").lower()

    matched = None
    if label:
        for p in points:
            if str(p.get("label_en") or p.get("label") or "").lower() == str(label).lower():
                matched = p
                break
            if str(p.get("label_ar") or "").lower() == str(label).lower():
                matched = p
                break
    if matched is None and value is not None:
        for p in points:
            if _dec(p.get("value")) == _dec(value):
                matched = p
                break

    if matched is not None and matched.get("normalized") is not None:
        return {
            "ok": True,
            "normalized": float(_dec(matched["normalized"])),
            "missing": False,
            "value": matched.get("value"),
            "label": matched.get("label_en") or matched.get("label"),
            "scale_type": scale_type,
        }

    # Numeric fallback: normalize by min/max of point values (no universal 1–5).
    nums = [_dec(p.get("value")) for p in points if _dec(p.get("value")) is not None]
    nums = [n for n in nums if n is not None]
    cur = _dec(value)
    if cur is None or not nums:
        return {"ok": False, "error": "unmapped_scale_point", "value": value, "label": label}
    lo, hi = min(nums), max(nums)
    if lo == hi:
        norm = Decimal("1") if cur == lo else Decimal("0")
    else:
        norm = (cur - lo) / (hi - lo)
    return {
        "ok": True,
        "normalized": float(max(Decimal("0"), min(Decimal("1"), norm))),
        "missing": False,
        "value": float(cur),
        "label": label,
        "scale_type": scale_type,
    }


def _round_display(raw: Decimal, *, decimals: int, mode: str) -> Decimal:
    q = Decimal("1").scaleb(-int(decimals))
    if mode == "half_up":
        return raw.quantize(q, rounding=ROUND_HALF_UP)
    # floor / ceil for explicit company configs
    if mode == "floor":
        return Decimal(math.floor(float(raw) * (10**decimals))) / Decimal(10**decimals)
    if mode == "ceil":
        return Decimal(math.ceil(float(raw) * (10**decimals))) / Decimal(10**decimals)
    return raw.quantize(q, rounding=ROUND_HALF_UP)


def denormalize_to_scale(
    *, scale_snapshot: dict[str, Any], normalized: float
) -> dict[str, Any]:
    points = scale_snapshot.get("points") or []
    if isinstance(points, str):
        points = json.loads(points)
    # Prefer point with closest normalized; else interpolate numeric values.
    with_norm = []
    for p in points:
        n = _dec(p.get("normalized"))
        if n is not None:
            with_norm.append((float(n), p))
    if with_norm:
        with_norm.sort(key=lambda x: abs(x[0] - normalized))
        best = with_norm[0][1]
        return {
            "value": best.get("value"),
            "label": best.get("label_en") or best.get("label"),
            "label_ar": best.get("label_ar"),
        }
    nums = [(float(_dec(p.get("value"))), p) for p in points if _dec(p.get("value")) is not None]
    if not nums:
        return {"value": normalized, "label": None}
    nums.sort(key=lambda x: x[0])
    lo_v, hi_v = nums[0][0], nums[-1][0]
    display = lo_v + (hi_v - lo_v) * float(normalized)
    # nearest point label
    nearest = min(nums, key=lambda x: abs(x[0] - display))[1]
    return {
        "value": display,
        "label": nearest.get("label_en") or nearest.get("label"),
        "label_ar": nearest.get("label_ar"),
    }


def compute_pre_calibration_result(
    *,
    components: list[dict[str, Any]],
    weights: dict[str, Any],
    scale_snapshot: dict[str, Any],
    missing_rule: str = "exclude_from_denominator",
    neutral_default_normalized: float | None = None,
    rounding_mode: str = "half_up",
    rounding_decimals: int = 2,
    policy_contract_version: str = CALC_POLICY_VERSION,
) -> dict[str, Any]:
    """Deterministic, versioned aggregation — pure function; identical inputs → identical outputs."""
    rule = str(missing_rule or "exclude_from_denominator").strip().lower()
    if rule not in MISSING_RULES:
        return {"ok": False, "error": "invalid_missing_rule", "allowed": list(MISSING_RULES)}
    if rule == "neutral_default" and neutral_default_normalized is None:
        return {"ok": False, "error": "neutral_default_requires_value"}

    weight_map = {str(k): float(v) for k, v in (weights or {}).items()}
    preserved: list[dict[str, Any]] = []
    included: list[tuple[float, float]] = []  # (weight, normalized)
    missing_applied: list[dict[str, Any]] = []
    blocked = False
    block_reason = None

    for comp in components or []:
        kind = str(comp.get("kind") or "section").strip().lower()
        key = str(comp.get("key") or kind)
        w = float(comp.get("weight") if comp.get("weight") is not None else weight_map.get(key, weight_map.get(kind, 0)))
        not_obs = bool(comp.get("not_observed") or comp.get("missing"))
        norm_res = normalize_scale_point(
            scale_snapshot=scale_snapshot,
            value=comp.get("value"),
            label=comp.get("label"),
            not_observed=not_obs,
        )
        entry = {
            "kind": kind,
            "key": key,
            "weight_configured": w,
            "input": {
                "value": comp.get("value"),
                "label": comp.get("label"),
                "not_observed": not_obs,
            },
            "normalization": norm_res,
        }
        preserved.append(entry)

        if norm_res.get("missing"):
            applied = {"key": key, "kind": kind, "rule": rule}
            if rule == "exclude_from_denominator":
                applied["effect"] = "excluded"
                missing_applied.append(applied)
                entry["included"] = False
                continue
            if rule == "block_finalization":
                blocked = True
                block_reason = f"missing_component:{key}"
                applied["effect"] = "block_finalization"
                missing_applied.append(applied)
                entry["included"] = False
                continue
            # neutral_default
            nd = float(neutral_default_normalized)  # type: ignore[arg-type]
            applied["effect"] = "neutral_default"
            applied["neutral_default_normalized"] = nd
            missing_applied.append(applied)
            entry["included"] = True
            entry["effective_normalized"] = nd
            if w > 0:
                included.append((w, nd))
            continue

        if not norm_res.get("ok"):
            return {"ok": False, "error": "component_normalization_failed", "component": entry}
        n = float(norm_res["normalized"])
        entry["included"] = True
        entry["effective_normalized"] = n
        if w > 0:
            included.append((w, n))

    if blocked:
        return {
            "ok": True,
            "blocked": True,
            "block_reason": block_reason,
            "component_inputs": preserved,
            "weights": weight_map,
            "missing_rule_applied": rule,
            "missing_details": missing_applied,
            "raw_aggregate": None,
            "display_result": None,
            "display_label": None,
            "scale_snapshot": scale_snapshot,
            "policy_contract_version": policy_contract_version,
            "calculation_trace": {"included_count": 0, "blocked": True},
        }

    if not included:
        return {
            "ok": False,
            "error": "no_includable_components",
            "component_inputs": preserved,
            "missing_rule_applied": rule,
            "missing_details": missing_applied,
        }

    total_w = sum(w for w, _ in included)
    if total_w <= 0:
        return {"ok": False, "error": "weights_sum_zero"}
    raw_norm = sum(Decimal(str(w)) * Decimal(str(n)) for w, n in included) / Decimal(str(total_w))
    display_norm = _round_display(raw_norm, decimals=rounding_decimals, mode=rounding_mode)
    mapped = denormalize_to_scale(scale_snapshot=scale_snapshot, normalized=float(display_norm))
    display_value = mapped.get("value")
    if display_value is not None:
        as_dec = _dec(display_value)
        if as_dec is not None:
            display_value = float(
                _round_display(as_dec, decimals=rounding_decimals, mode=rounding_mode)
            )
        # labeled / non-numeric scale values retained as-is (e.g. "A"/"B")
   
    return {
        "ok": True,
        "blocked": False,
        "component_inputs": preserved,
        "weights": weight_map,
        "missing_rule_applied": rule,
        "missing_details": missing_applied,
        "raw_aggregate": float(raw_norm),
        "display_result": display_value,
        "display_label": mapped.get("label"),
        "display_label_ar": mapped.get("label_ar"),
        "normalized_display": float(display_norm),
        "scale_snapshot": scale_snapshot,
        "policy_contract_version": policy_contract_version,
        "rounding": {"mode": rounding_mode, "decimals": rounding_decimals},
        "calculation_trace": {
            "included": [{"weight": w, "normalized": n} for w, n in included],
            "total_weight": total_w,
            "raw_normalized": float(raw_norm),
        },
    }


def replay_pre_calibration(frozen_row: dict[str, Any]) -> dict[str, Any]:
    """Recompute from frozen inputs — must match stored raw/display."""
    scale = frozen_row.get("scale_snapshot") or {}
    if isinstance(scale, str):
        scale = json.loads(scale)
    comps_raw = frozen_row.get("component_inputs") or []
    if isinstance(comps_raw, str):
        comps_raw = json.loads(comps_raw)
    # Rebuild component list from preserved inputs
    components = []
    for c in comps_raw:
        inp = c.get("input") or {}
        components.append(
            {
                "kind": c.get("kind"),
                "key": c.get("key"),
                "weight": c.get("weight_configured"),
                "value": inp.get("value"),
                "label": inp.get("label"),
                "not_observed": inp.get("not_observed"),
                "missing": inp.get("not_observed"),
            }
        )
    weights = frozen_row.get("weights") or {}
    if isinstance(weights, str):
        weights = json.loads(weights)
    trace = frozen_row.get("calculation_trace") or {}
    if isinstance(trace, str):
        trace = json.loads(trace)
    rounding = (trace.get("rounding") if isinstance(trace, dict) else None) or {}
    # Prefer explicit rounding on row metadata path
    meta = frozen_row.get("metadata") or {}
    if isinstance(meta, str):
        meta = json.loads(meta)
    rounding = meta.get("rounding") or rounding or {"mode": "half_up", "decimals": 2}

    # Recover neutral default from missing details if needed
    missing_details = []
    if isinstance(trace, dict):
        missing_details = trace.get("missing_details") or []
    # Also encoded in calculation when we store full compute result in calculation_trace
    calc_meta = frozen_row.get("calculation_trace") or {}
    if isinstance(calc_meta, str):
        calc_meta = json.loads(calc_meta)
    neutral = None
    for d in (calc_meta.get("missing_details") or missing_details or []):
        if d.get("neutral_default_normalized") is not None:
            neutral = float(d["neutral_default_normalized"])
            break
    if frozen_row.get("missing_rule_applied") == "neutral_default" and neutral is None:
        # try component effective values for missing ones — not ideal; store in policy snapshot
        pass

    policy_meta = calc_meta.get("policy") or meta.get("policy") or {}
    if neutral is None:
        neutral = policy_meta.get("neutral_default_normalized")

    recomputed = compute_pre_calibration_result(
        components=components,
        weights=weights,
        scale_snapshot=scale,
        missing_rule=str(frozen_row.get("missing_rule_applied") or "exclude_from_denominator"),
        neutral_default_normalized=float(neutral) if neutral is not None else None,
        rounding_mode=str(rounding.get("mode") or "half_up"),
        rounding_decimals=int(rounding.get("decimals") or 2),
        policy_contract_version=str(
            frozen_row.get("policy_contract_version") or CALC_POLICY_VERSION
        ),
    )
    if not recomputed.get("ok"):
        return recomputed
    raw_match = (
        recomputed.get("raw_aggregate") is None and frozen_row.get("raw_aggregate") is None
    ) or (
        recomputed.get("raw_aggregate") is not None
        and frozen_row.get("raw_aggregate") is not None
        and abs(float(recomputed["raw_aggregate"]) - float(frozen_row["raw_aggregate"])) < 1e-9
    )
    disp_match = (
        recomputed.get("display_result") is None and frozen_row.get("display_result") is None
    ) or (
        recomputed.get("display_result") is not None
        and frozen_row.get("display_result") is not None
        and abs(float(recomputed["display_result"]) - float(frozen_row["display_result"])) < 1e-9
    )
    return {
        "ok": True,
        "identical": bool(raw_match and disp_match and recomputed.get("blocked") == bool(frozen_row.get("blocked"))),
        "recomputed": recomputed,
        "raw_match": raw_match,
        "display_match": disp_match,
    }


# ── Calculation policy ──────────────────────────────────────────────────────


def create_calc_policy(
    cur: Any,
    *,
    company_code: str,
    actor_phone: str,
    name_en: str,
    scale_snapshot: dict[str, Any],
    component_weights: dict[str, Any],
    name_ar: str | None = None,
    missing_rule: str = "exclude_from_denominator",
    neutral_default_normalized: float | None = None,
    rounding_mode: str = "half_up",
    rounding_decimals: int = 2,
    reason: str = "create calc policy",
) -> dict[str, Any]:
    if not str(reason or "").strip():
        return {"ok": False, "error": "audit_reason_required"}
    ent = _entitled(cur, company_code, feature="aggregation")
    if not ent.get("ok"):
        return ent
    company = ent["company_code"]
    rule = str(missing_rule or "exclude_from_denominator").strip().lower()
    if rule not in MISSING_RULES:
        return {"ok": False, "error": "invalid_missing_rule"}
    if not scale_snapshot or not scale_snapshot.get("points"):
        return {"ok": False, "error": "scale_snapshot_required"}
    if not component_weights:
        return {"ok": False, "error": "component_weights_required"}
    cur.execute(
        """
        INSERT INTO perf_calc_policies (
          company_code, name_en, name_ar, component_weights, missing_rule,
          neutral_default_normalized, rounding_mode, rounding_decimals,
          scale_snapshot, created_by_phone
        ) VALUES (%s,%s,%s,%s::jsonb,%s,%s,%s,%s,%s::jsonb,%s)
        RETURNING *
        """,
        (
            company, name_en, name_ar, json.dumps(component_weights, default=str), rule,
            neutral_default_normalized, rounding_mode, int(rounding_decimals),
            json.dumps(scale_snapshot, default=str), _digits(actor_phone),
        ),
    )
    row = dict(cur.fetchone())
    _audit(
        cur, company_code=company, action="calc_policy_created", actor_phone=actor_phone,
        reason=reason, subject_type="calc_policy", subject_id=str(row["policy_id"]),
        payload={"version": 1, "missing_rule": rule},
    )
    return {"ok": True, "policy": row}


def bump_calc_policy_version(
    cur: Any,
    *,
    company_code: str,
    policy_id: str,
    actor_phone: str,
    component_weights: dict[str, Any] | None = None,
    missing_rule: str | None = None,
    scale_snapshot: dict[str, Any] | None = None,
    reason: str,
) -> dict[str, Any]:
    """New version — does not rewrite historical pre-calibration results."""
    if not str(reason or "").strip():
        return {"ok": False, "error": "audit_reason_required"}
    ent = _entitled(cur, company_code, feature="aggregation")
    if not ent.get("ok"):
        return ent
    company = ent["company_code"]
    cur.execute(
        "SELECT * FROM perf_calc_policies WHERE company_code=%s AND policy_id=%s",
        (company, policy_id),
    )
    old = cur.fetchone()
    if not old:
        return {"ok": False, "error": "policy_not_found"}
    old = dict(old)
    new_ver = int(old.get("version") or 1) + 1
    weights = component_weights if component_weights is not None else old.get("component_weights")
    if isinstance(weights, str):
        weights = json.loads(weights)
    rule = missing_rule or old.get("missing_rule")
    scale = scale_snapshot if scale_snapshot is not None else old.get("scale_snapshot")
    if isinstance(scale, str):
        scale = json.loads(scale)
    # Deprecate old version row identity by inserting sibling version with same logical family
    # Keep same policy_id family via metadata parent; insert new row for immutability of id versions.
    # Simpler: update version on policy and leave historical results pointing at frozen snapshots.
    cur.execute(
        """
        UPDATE perf_calc_policies SET
          version=%s,
          component_weights=%s::jsonb,
          missing_rule=%s,
          scale_snapshot=%s::jsonb,
          updated_at=now()
        WHERE policy_id=%s AND company_code=%s
        RETURNING *
        """,
        (
            new_ver, json.dumps(weights, default=str), rule,
            json.dumps(scale, default=str), policy_id, company,
        ),
    )
    row = dict(cur.fetchone())
    _audit(
        cur, company_code=company, action="calc_policy_versioned", actor_phone=actor_phone,
        reason=reason, subject_type="calc_policy", subject_id=str(policy_id),
        payload={"from_version": int(old.get("version") or 1), "to_version": new_ver, "history_preserved": True},
    )
    return {"ok": True, "policy": row, "from_version": int(old.get("version") or 1), "to_version": new_ver}


def store_pre_calibration_result(
    cur: Any,
    *,
    company_code: str,
    actor_phone: str,
    subject_employee_key: str,
    policy_id: str,
    components: list[dict[str, Any]],
    cycle_id: str | None = None,
    reason: str = "compute pre-calibration",
) -> dict[str, Any]:
    ent = _entitled(cur, company_code, feature="aggregation")
    if not ent.get("ok"):
        return ent
    company = ent["company_code"]
    cur.execute(
        "SELECT * FROM perf_calc_policies WHERE company_code=%s AND policy_id=%s",
        (company, policy_id),
    )
    pol = cur.fetchone()
    if not pol:
        return {"ok": False, "error": "policy_not_found"}
    pol = dict(pol)
    scale = pol.get("scale_snapshot") or {}
    if isinstance(scale, str):
        scale = json.loads(scale)
    weights = pol.get("component_weights") or {}
    if isinstance(weights, str):
        weights = json.loads(weights)
    computed = compute_pre_calibration_result(
        components=components,
        weights=weights,
        scale_snapshot=scale,
        missing_rule=str(pol.get("missing_rule") or "exclude_from_denominator"),
        neutral_default_normalized=(
            float(pol["neutral_default_normalized"])
            if pol.get("neutral_default_normalized") is not None
            else None
        ),
        rounding_mode=str(pol.get("rounding_mode") or "half_up"),
        rounding_decimals=int(pol.get("rounding_decimals") or 2),
        policy_contract_version=str(pol.get("policy_contract_version") or CALC_POLICY_VERSION),
    )
    if not computed.get("ok"):
        return computed
    trace = deepcopy(computed.get("calculation_trace") or {})
    trace["missing_details"] = computed.get("missing_details") or []
    trace["rounding"] = computed.get("rounding")
    trace["policy"] = {
        "neutral_default_normalized": (
            float(pol["neutral_default_normalized"])
            if pol.get("neutral_default_normalized") is not None
            else None
        ),
        "rounding_mode": pol.get("rounding_mode"),
        "rounding_decimals": pol.get("rounding_decimals"),
    }
    cur.execute(
        """
        INSERT INTO perf_pre_calibration_results (
          company_code, cycle_id, subject_employee_key, policy_id, policy_version,
          policy_contract_version, scale_snapshot, component_inputs, weights,
          missing_rule_applied, blocked, block_reason, raw_aggregate, display_result,
          display_label, calculation_trace, created_by_phone
        ) VALUES (
          %s,%s,%s,%s,%s,%s,%s::jsonb,%s::jsonb,%s::jsonb,%s,%s,%s,%s,%s,%s,%s::jsonb,%s
        )
        ON CONFLICT (company_code, cycle_id, subject_employee_key, policy_id, policy_version)
        DO UPDATE SET
          component_inputs=EXCLUDED.component_inputs,
          weights=EXCLUDED.weights,
          missing_rule_applied=EXCLUDED.missing_rule_applied,
          blocked=EXCLUDED.blocked,
          block_reason=EXCLUDED.block_reason,
          raw_aggregate=EXCLUDED.raw_aggregate,
          display_result=EXCLUDED.display_result,
          display_label=EXCLUDED.display_label,
          calculation_trace=EXCLUDED.calculation_trace,
          scale_snapshot=EXCLUDED.scale_snapshot,
          row_version=perf_pre_calibration_results.row_version+1
        RETURNING *
        """,
        (
            company, cycle_id, subject_employee_key, policy_id, int(pol["version"]),
            str(pol.get("policy_contract_version") or CALC_POLICY_VERSION),
            json.dumps(scale, default=str),
            json.dumps(computed["component_inputs"], default=str),
            json.dumps(computed["weights"], default=str),
            computed["missing_rule_applied"],
            bool(computed.get("blocked")),
            computed.get("block_reason"),
            computed.get("raw_aggregate"),
            computed.get("display_result"),
            computed.get("display_label"),
            json.dumps(trace, default=str),
            _digits(actor_phone),
        ),
    )
    row = dict(cur.fetchone())
    _audit(
        cur, company_code=company, action="pre_calibration_computed", actor_phone=actor_phone,
        reason=reason, subject_type="pre_calibration_result", subject_id=str(row["result_id"]),
        payload={
            "blocked": bool(row.get("blocked")),
            "display_result": row.get("display_result"),
            "policy_version": int(pol["version"]),
        },
    )
    return {"ok": True, "result": row, "computed": computed}


# ── Calibration sessions ────────────────────────────────────────────────────


def create_calibration_session(
    cur: Any,
    *,
    company_code: str,
    actor_phone: str,
    cycle_id: str,
    name_en: str,
    name_ar: str | None = None,
    facilitator_phone: str | None = None,
    distribution_mode: str = "none",
    distribution_policy: dict[str, Any] | None = None,
    visibility_rules: dict[str, Any] | None = None,
    reason: str = "create calibration session",
) -> dict[str, Any]:
    if not str(reason or "").strip():
        return {"ok": False, "error": "audit_reason_required"}
    ent = _entitled(cur, company_code, feature="calibration")
    if not ent.get("ok"):
        return ent
    company = ent["company_code"]
    mode = str(distribution_mode or "none").strip().lower()
    if mode not in DIST_MODES:
        return {"ok": False, "error": "invalid_distribution_mode", "allowed": list(DIST_MODES)}
    if mode == "none":
        dist_pol = {"forced_curve": False, "assumed_bell_curve": False}
    else:
        dist_pol = dict(distribution_policy or {})
        dist_pol["forced_curve"] = False if mode == "guidance" else bool(dist_pol.get("forced_curve", True))
        dist_pol["assumed_bell_curve"] = False
        dist_pol["mode"] = mode
        if mode == "hard_constraint" and not dist_pol.get("buckets"):
            return {"ok": False, "error": "hard_constraint_requires_buckets"}
    fac = _digits(facilitator_phone or actor_phone)
    policy_snapshot = {
        "require_sensitive_permission": bool(ent["settings"].get("require_sensitive_permission")),
        "provisional_visible_to_employees": bool(ent["settings"].get("provisional_visible_to_employees")),
        "sod_lock_requires_other_actor": bool(ent["settings"].get("sod_lock_requires_other_actor")),
        "forced_distribution_assumed": False,
        "snapshot_at": datetime.utcnow().isoformat() + "Z",
    }
    vis = visibility_rules or {
        "employees_see_provisional": bool(ent["settings"].get("provisional_visible_to_employees")),
        "raw_360_visible_in_calibration": False,
        "requires_sensitive_permission": True,
    }
    cur.execute(
        """
        INSERT INTO perf_calibration_sessions (
          company_code, cycle_id, name_en, name_ar, status, facilitator_phone, owner_phone,
          visibility_rules, policy_snapshot, distribution_mode, distribution_policy, created_by_phone
        ) VALUES (%s,%s,%s,%s,'draft',%s,%s,%s::jsonb,%s::jsonb,%s,%s::jsonb,%s)
        RETURNING *
        """,
        (
            company, cycle_id, name_en, name_ar, fac, fac,
            json.dumps(vis, default=str), json.dumps(policy_snapshot, default=str),
            mode, json.dumps(dist_pol, default=str), _digits(actor_phone),
        ),
    )
    row = dict(cur.fetchone())
    # Facilitator as participant
    cur.execute(
        """
        INSERT INTO perf_calibration_participants (
          company_code, session_id, participant_phone, participant_role, scoped_employee_keys
        ) VALUES (%s,%s,%s,'facilitator','[]'::jsonb)
        ON CONFLICT (session_id, participant_phone) DO NOTHING
        """,
        (company, row["session_id"], fac),
    )
    _audit(
        cur, company_code=company, action="calibration_session_created", actor_phone=actor_phone,
        reason=reason, subject_type="calibration_session", subject_id=str(row["session_id"]),
        payload={"distribution_mode": mode, "forced_distribution_assumed": False},
    )
    return {"ok": True, "session": row}


def add_calibration_participant(
    cur: Any,
    *,
    company_code: str,
    session_id: str,
    actor_phone: str,
    participant_phone: str,
    participant_role: str = "manager",
    scoped_employee_keys: list[str] | None = None,
) -> dict[str, Any]:
    ent = _entitled(cur, company_code, feature="calibration")
    if not ent.get("ok"):
        return ent
    company = ent["company_code"]
    sess = _get_session(cur, company, session_id)
    if not sess:
        return {"ok": False, "error": "session_not_found"}
    if sess["status"] not in ("draft", "prepared"):
        return {"ok": False, "error": "session_not_editable", "status": sess["status"]}
    role = str(participant_role or "manager").strip().lower()
    if role not in ("facilitator", "manager", "hr_observer"):
        return {"ok": False, "error": "invalid_participant_role"}
    cur.execute(
        """
        INSERT INTO perf_calibration_participants (
          company_code, session_id, participant_phone, participant_role, scoped_employee_keys
        ) VALUES (%s,%s,%s,%s,%s::jsonb)
        ON CONFLICT (session_id, participant_phone) DO UPDATE SET
          participant_role=EXCLUDED.participant_role,
          scoped_employee_keys=EXCLUDED.scoped_employee_keys
        RETURNING *
        """,
        (
            company, session_id, _digits(participant_phone), role,
            json.dumps(scoped_employee_keys or [], default=str),
        ),
    )
    row = dict(cur.fetchone())
    return {"ok": True, "participant": row}


def prepare_calibration_session(
    cur: Any,
    *,
    company_code: str,
    session_id: str,
    actor_phone: str,
    population: list[dict[str, Any]],
    reason: str = "freeze calibration population",
) -> dict[str, Any]:
    """Freeze employee population + submitted evidence snapshots into the session."""
    if not str(reason or "").strip():
        return {"ok": False, "error": "audit_reason_required"}
    ent = _entitled(cur, company_code, feature="calibration")
    if not ent.get("ok"):
        return ent
    company = ent["company_code"]
    sess = _get_session(cur, company, session_id)
    if not sess:
        return {"ok": False, "error": "session_not_found"}
    if sess["status"] not in ("draft", "prepared"):
        return {"ok": False, "error": "session_not_preparable", "status": sess["status"]}
    if not population:
        return {"ok": False, "error": "population_required"}

    # Clear prior population if re-preparing draft
    cur.execute(
        "DELETE FROM perf_calibration_population WHERE session_id=%s AND company_code=%s",
        (session_id, company),
    )
    frozen = []
    for item in population:
        subj = str(item.get("subject_employee_key") or "").strip()
        if not subj:
            return {"ok": False, "error": "subject_employee_key_required"}
        cur.execute(
            """
            INSERT INTO perf_calibration_population (
              company_code, session_id, subject_employee_key, manager_employee_key, manager_phone,
              pre_calibration_result_id, frozen_manager_rating, frozen_self_rating, frozen_360_aggregate
            ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
            RETURNING *
            """,
            (
                company, session_id, subj,
                item.get("manager_employee_key"),
                _digits(item.get("manager_phone")) if item.get("manager_phone") else None,
                item.get("pre_calibration_result_id"),
                item.get("frozen_manager_rating"),
                item.get("frozen_self_rating"),
                item.get("frozen_360_aggregate"),
            ),
        )
        pop = dict(cur.fetchone())
        frozen.append(pop)
        # Seed calibrated result from pre-cal
        pre_val = item.get("pre_calibration_value")
        pre_label = item.get("pre_calibration_label")
        if item.get("pre_calibration_result_id"):
            cur.execute(
                "SELECT display_result, display_label FROM perf_pre_calibration_results WHERE result_id=%s",
                (item["pre_calibration_result_id"],),
            )
            pr = cur.fetchone()
            if pr:
                pr = dict(pr)
                pre_val = pr.get("display_result") if pre_val is None else pre_val
                pre_label = pr.get("display_label") if pre_label is None else pre_label
        cur.execute(
            """
            INSERT INTO perf_calibrated_results (
              company_code, session_id, cycle_id, subject_employee_key,
              pre_calibration_result_id, pre_calibration_value, pre_calibration_label,
              final_value, final_label, status
            ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,'provisional')
            ON CONFLICT (session_id, subject_employee_key) DO UPDATE SET
              pre_calibration_result_id=EXCLUDED.pre_calibration_result_id,
              pre_calibration_value=EXCLUDED.pre_calibration_value,
              pre_calibration_label=EXCLUDED.pre_calibration_label,
              final_value=EXCLUDED.final_value,
              final_label=EXCLUDED.final_label,
              status='provisional',
              row_version=perf_calibrated_results.row_version+1,
              updated_at=now()
            RETURNING *
            """,
            (
                company, session_id, sess["cycle_id"], subj,
                item.get("pre_calibration_result_id"), pre_val, pre_label,
                pre_val, pre_label,
            ),
        )

    cur.execute(
        """
        UPDATE perf_calibration_sessions SET
          status='prepared',
          population_frozen_at=now(),
          row_version=row_version+1,
          updated_at=now()
        WHERE session_id=%s AND company_code=%s
        RETURNING *
        """,
        (session_id, company),
    )
    row = dict(cur.fetchone())
    _audit(
        cur, company_code=company, action="calibration_population_frozen", actor_phone=actor_phone,
        reason=reason, subject_type="calibration_session", subject_id=str(session_id),
        payload={"population_count": len(frozen)},
    )
    return {"ok": True, "session": row, "population": frozen}


def start_calibration_session(
    cur: Any, *, company_code: str, session_id: str, actor_phone: str, reason: str = "start session"
) -> dict[str, Any]:
    ent = _entitled(cur, company_code, feature="calibration")
    if not ent.get("ok"):
        return ent
    company = ent["company_code"]
    sess = _get_session(cur, company, session_id)
    if not sess:
        return {"ok": False, "error": "session_not_found"}
    if sess["status"] != "prepared":
        return {"ok": False, "error": "session_not_prepared", "status": sess["status"]}
    if _digits(actor_phone) != _digits(sess.get("facilitator_phone")):
        # allow HR facilitator listed as facilitator only
        return {"ok": False, "error": "facilitator_required"}
    cur.execute(
        """
        UPDATE perf_calibration_sessions
        SET status='in_session', row_version=row_version+1, updated_at=now()
        WHERE session_id=%s AND company_code=%s AND status='prepared'
        RETURNING *
        """,
        (session_id, company),
    )
    row = cur.fetchone()
    if not row:
        return {"ok": False, "error": "start_failed"}
    _audit(
        cur, company_code=company, action="calibration_session_started", actor_phone=actor_phone,
        reason=reason, subject_type="calibration_session", subject_id=str(session_id),
    )
    return {"ok": True, "session": dict(row)}


def _participant_scope(
    cur: Any, *, company: str, session_id: str, actor_phone: str
) -> dict[str, Any]:
    cur.execute(
        """
        SELECT * FROM perf_calibration_participants
        WHERE company_code=%s AND session_id=%s AND participant_phone=%s
        """,
        (company, session_id, _digits(actor_phone)),
    )
    row = cur.fetchone()
    if not row:
        return {"ok": False, "error": "not_a_participant"}
    p = dict(row)
    scoped = p.get("scoped_employee_keys") or []
    if isinstance(scoped, str):
        scoped = json.loads(scoped)
    return {"ok": True, "participant": p, "scoped_employee_keys": [str(x) for x in scoped]}


def apply_calibration_adjustment(
    cur: Any,
    *,
    company_code: str,
    session_id: str,
    actor_phone: str,
    subject_employee_key: str,
    new_value: Any,
    reason: str,
    expected_row_version: int,
    new_label: str | None = None,
    has_sensitive_permission: bool = False,
    distribution_exception: bool = False,
    distribution_exception_reason: str | None = None,
) -> dict[str, Any]:
    if not str(reason or "").strip():
        return {"ok": False, "error": "audit_reason_required"}
    ent = _entitled(cur, company_code, feature="calibration")
    if not ent.get("ok"):
        return ent
    company = ent["company_code"]
    settings = ent["settings"]
    sess = _get_session(cur, company, session_id)
    if not sess:
        return {"ok": False, "error": "session_not_found"}
    if sess["status"] != "in_session":
        return {"ok": False, "error": "session_not_in_session", "status": sess["status"]}
    if settings.get("require_sensitive_permission") and not has_sensitive_permission:
        return {"ok": False, "error": "sensitive_permission_required"}

    scope = _participant_scope(cur, company=company, session_id=session_id, actor_phone=actor_phone)
    if not scope.get("ok"):
        return scope
    role = scope["participant"]["participant_role"]
    if role == "manager":
        scoped = scope["scoped_employee_keys"]
        if scoped and subject_employee_key not in scoped:
            return {"ok": False, "error": "manager_out_of_scope", "subject": subject_employee_key}
        if not scoped:
            # freeze population manager_phone match
            cur.execute(
                """
                SELECT 1 FROM perf_calibration_population
                WHERE session_id=%s AND subject_employee_key=%s AND manager_phone=%s
                """,
                (session_id, subject_employee_key, _digits(actor_phone)),
            )
            if not cur.fetchone():
                return {"ok": False, "error": "manager_out_of_scope"}

    cur.execute(
        """
        SELECT * FROM perf_calibrated_results
        WHERE company_code=%s AND session_id=%s AND subject_employee_key=%s
        """,
        (company, session_id, subject_employee_key),
    )
    cal = cur.fetchone()
    if not cal:
        return {"ok": False, "error": "calibrated_result_not_found"}
    cal = dict(cal)
    if int(cal["row_version"]) != int(expected_row_version):
        return {
            "ok": False,
            "error": "stale_row_version",
            "expected": int(expected_row_version),
            "actual": int(cal["row_version"]),
        }
    if cal["status"] in ("locked",):
        return {"ok": False, "error": "result_locked"}

    # Distribution hard constraint check
    dist_mode = str(sess.get("distribution_mode") or "none")
    dist_pol = sess.get("distribution_policy") or {}
    if isinstance(dist_pol, str):
        dist_pol = json.loads(dist_pol)
    if dist_mode == "hard_constraint" and not distribution_exception:
        violation = _distribution_would_violate(
            cur, session_id=session_id, subject_employee_key=subject_employee_key,
            new_value=new_value, policy=dist_pol,
        )
        if violation:
            return {
                "ok": False,
                "error": "distribution_hard_constraint_violation",
                "detail": violation,
                "hint": "Pass distribution_exception=True with audited reason to override",
            }
    if distribution_exception and not str(distribution_exception_reason or "").strip():
        return {"ok": False, "error": "distribution_exception_reason_required"}

    prior_value = cal.get("final_value")
    prior_label = cal.get("final_label")
    cur.execute(
        """
        UPDATE perf_calibrated_results SET
          final_value=%s,
          final_label=%s,
          row_version=row_version+1,
          updated_at=now()
        WHERE calibrated_id=%s AND row_version=%s
        RETURNING *
        """,
        (new_value, new_label, cal["calibrated_id"], expected_row_version),
    )
    updated = cur.fetchone()
    if not updated:
        return {"ok": False, "error": "stale_row_version"}
    updated = dict(updated)
    cur.execute(
        """
        INSERT INTO perf_calibration_adjustments (
          company_code, session_id, subject_employee_key,
          prior_value, prior_label, new_value, new_label,
          actor_phone, reason, expected_row_version,
          distribution_exception, distribution_exception_reason
        ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
        RETURNING *
        """,
        (
            company, session_id, subject_employee_key,
            prior_value, prior_label, new_value, new_label,
            _digits(actor_phone), str(reason).strip()[:500], int(expected_row_version),
            bool(distribution_exception),
            (str(distribution_exception_reason).strip()[:500] if distribution_exception_reason else None),
        ),
    )
    adj = dict(cur.fetchone())
    # Prove originals untouched: population frozen ratings remain
    cur.execute(
        """
        SELECT frozen_manager_rating, frozen_self_rating, frozen_360_aggregate,
               pre_calibration_value, pre_calibration_label
        FROM perf_calibration_population p
        JOIN perf_calibrated_results c
          ON c.session_id=p.session_id AND c.subject_employee_key=p.subject_employee_key
        WHERE p.session_id=%s AND p.subject_employee_key=%s
        """,
        (session_id, subject_employee_key),
    )
    _audit(
        cur, company_code=company, action="calibration_adjustment_applied",
        actor_phone=actor_phone, reason=reason, subject_type="calibration_adjustment",
        subject_id=str(adj["adjustment_id"]),
        payload={
            "prior": prior_value, "new": new_value,
            "pre_calibration_unchanged": True,
            "submitted_layers_unchanged": True,
            "distribution_exception": bool(distribution_exception),
        },
    )
    return {
        "ok": True,
        "adjustment": adj,
        "result": updated,
        "pre_calibration_preserved": True,
        "submitted_layers_preserved": True,
    }


def _distribution_would_violate(
    cur: Any,
    *,
    session_id: str,
    subject_employee_key: str,
    new_value: Any,
    policy: dict[str, Any],
) -> dict[str, Any] | None:
    buckets = policy.get("buckets") or []
    if not buckets:
        return None
    cur.execute(
        "SELECT subject_employee_key, final_value FROM perf_calibrated_results WHERE session_id=%s",
        (session_id,),
    )
    rows = [dict(r) for r in (cur.fetchall() or [])]
    values = []
    for r in rows:
        if r["subject_employee_key"] == subject_employee_key:
            values.append(_dec(new_value))
        else:
            values.append(_dec(r.get("final_value")))
    total = len(values) or 1
    for b in buckets:
        lo = _dec(b.get("min"))
        hi = _dec(b.get("max"))
        max_pct = float(b.get("max_pct") or 100)
        max_count = b.get("max_count")
        count = 0
        for v in values:
            if v is None:
                continue
            if lo is not None and v < lo:
                continue
            if hi is not None and v > hi:
                continue
            count += 1
        pct = (count / total) * 100.0
        if max_count is not None and count > int(max_count):
            return {"bucket": b, "count": count, "max_count": int(max_count)}
        if pct > max_pct + 1e-9:
            return {"bucket": b, "pct": pct, "max_pct": max_pct}
    return None


def complete_calibration_session(
    cur: Any, *, company_code: str, session_id: str, actor_phone: str, reason: str = "complete"
) -> dict[str, Any]:
    ent = _entitled(cur, company_code, feature="calibration")
    if not ent.get("ok"):
        return ent
    company = ent["company_code"]
    sess = _get_session(cur, company, session_id)
    if not sess:
        return {"ok": False, "error": "session_not_found"}
    if sess["status"] != "in_session":
        return {"ok": False, "error": "session_not_in_session"}
    if _digits(actor_phone) != _digits(sess.get("facilitator_phone")):
        return {"ok": False, "error": "facilitator_required"}
    cur.execute(
        """
        UPDATE perf_calibration_sessions
        SET status='completed', row_version=row_version+1, updated_at=now()
        WHERE session_id=%s AND company_code=%s
        RETURNING *
        """,
        (session_id, company),
    )
    row = dict(cur.fetchone())
    _audit(
        cur, company_code=company, action="calibration_session_completed",
        actor_phone=actor_phone, reason=reason, subject_type="calibration_session",
        subject_id=str(session_id),
    )
    return {"ok": True, "session": row}


def lock_and_publish_calibration(
    cur: Any,
    *,
    company_code: str,
    session_id: str,
    actor_phone: str,
    reason: str,
    has_sensitive_permission: bool = True,
) -> dict[str, Any]:
    if not str(reason or "").strip():
        return {"ok": False, "error": "audit_reason_required"}
    ent = _entitled(cur, company_code, feature="calibration")
    if not ent.get("ok"):
        return ent
    company = ent["company_code"]
    settings = ent["settings"]
    sess = _get_session(cur, company, session_id)
    if not sess:
        return {"ok": False, "error": "session_not_found"}
    if sess["status"] not in ("completed", "in_session"):
        return {"ok": False, "error": "session_not_lockable", "status": sess["status"]}
    if settings.get("require_sensitive_permission") and not has_sensitive_permission:
        return {"ok": False, "error": "sensitive_permission_required"}
    if settings.get("sod_lock_requires_other_actor"):
        if _digits(actor_phone) == _digits(sess.get("facilitator_phone")):
            return {"ok": False, "error": "sod_lock_requires_other_actor"}

    cur.execute(
        """
        UPDATE perf_calibrated_results SET
          status='locked',
          published_at=COALESCE(published_at, now()),
          locked_at=now(),
          row_version=row_version+1,
          updated_at=now()
        WHERE session_id=%s AND company_code=%s
        """,
        (session_id, company),
    )
    cur.execute(
        """
        UPDATE perf_calibration_sessions SET
          status='locked',
          locked_at=now(),
          locked_by_phone=%s,
          published_at=now(),
          row_version=row_version+1,
          updated_at=now()
        WHERE session_id=%s AND company_code=%s
        RETURNING *
        """,
        (_digits(actor_phone), session_id, company),
    )
    row = dict(cur.fetchone())
    _audit(
        cur, company_code=company, action="calibration_locked_published",
        actor_phone=actor_phone, reason=reason, subject_type="calibration_session",
        subject_id=str(session_id),
        payload={"immutable_after": True, "talent_writes": False},
    )
    return {"ok": True, "session": row, "immutable": True}


def amend_locked_result(
    cur: Any,
    *,
    company_code: str,
    calibrated_id: str,
    actor_phone: str,
    new_value: Any,
    reason: str,
    new_label: str | None = None,
) -> dict[str, Any]:
    """Post-lock correction — explicit audited amendment only."""
    if not str(reason or "").strip():
        return {"ok": False, "error": "audit_reason_required"}
    ent = _entitled(cur, company_code, feature="calibration")
    if not ent.get("ok"):
        return ent
    company = ent["company_code"]
    cur.execute(
        "SELECT * FROM perf_calibrated_results WHERE company_code=%s AND calibrated_id=%s",
        (company, calibrated_id),
    )
    row = cur.fetchone()
    if not row:
        return {"ok": False, "error": "calibrated_result_not_found"}
    cal = dict(row)
    if cal["status"] != "locked":
        return {"ok": False, "error": "amend_only_when_locked", "status": cal["status"]}
    before = {
        "final_value": cal.get("final_value"),
        "final_label": cal.get("final_label"),
        "pre_calibration_value": cal.get("pre_calibration_value"),
    }
    after = {"final_value": new_value, "final_label": new_label}
    cur.execute(
        """
        UPDATE perf_calibrated_results SET
          final_value=%s, final_label=%s, status='amended',
          row_version=row_version+1, updated_at=now()
        WHERE calibrated_id=%s
        RETURNING *
        """,
        (new_value, new_label, calibrated_id),
    )
    updated = dict(cur.fetchone())
    cur.execute(
        """
        INSERT INTO perf_calibration_amendments (
          company_code, calibrated_id, session_id, before_payload, after_payload, reason, actor_phone
        ) VALUES (%s,%s,%s,%s::jsonb,%s::jsonb,%s,%s)
        """,
        (
            company, calibrated_id, cal["session_id"],
            json.dumps(before, default=str), json.dumps(after, default=str),
            str(reason).strip()[:500], _digits(actor_phone),
        ),
    )
    _audit(
        cur, company_code=company, action="calibration_amended", actor_phone=actor_phone,
        reason=reason, subject_type="calibrated_result", subject_id=str(calibrated_id),
        payload={"pre_calibration_still_preserved": True},
    )
    return {"ok": True, "result": updated, "amended_via_audit": True}


def can_view_calibration_outcome(
    *,
    result: dict[str, Any],
    session: dict[str, Any],
    actor_role: str,
    has_sensitive_permission: bool = False,
) -> dict[str, Any]:
    """Employees do not see provisional calibration unless policy allows."""
    vis = session.get("visibility_rules") or {}
    if isinstance(vis, str):
        vis = json.loads(vis)
    status = str(result.get("status") or "")
    if actor_role in ("facilitator", "hr", "hr_observer"):
        if vis.get("requires_sensitive_permission") and not has_sensitive_permission:
            return {"ok": False, "error": "sensitive_permission_required"}
        out = dict(result)
        if not vis.get("raw_360_visible_in_calibration", False):
            out["raw_360_redacted"] = True
        return {"ok": True, "result": out}
    if actor_role == "manager":
        if status == "provisional" and not has_sensitive_permission:
            # managers in session may see provisional for scoped population
            return {"ok": True, "result": dict(result), "provisional": True}
        return {"ok": True, "result": dict(result)}
    if actor_role == "employee":
        if status == "provisional" and not vis.get("employees_see_provisional"):
            return {"ok": False, "error": "provisional_hidden_from_employee"}
        if status in ("published", "locked", "amended"):
            return {
                "ok": True,
                "result": {
                    "final_value": result.get("final_value"),
                    "final_label": result.get("final_label"),
                    "status": status,
                },
            }
        return {"ok": False, "error": "outcome_not_revealed"}
    return {"ok": False, "error": "visibility_denied"}


def prove_population_immune_to_manager_reassignment(
    cur: Any, *, session_id: str, subject_employee_key: str, new_manager_phone: str
) -> dict[str, Any]:
    """Manager reassignment after freeze must not rewrite frozen calibration population."""
    cur.execute(
        """
        SELECT manager_phone FROM perf_calibration_population
        WHERE session_id=%s AND subject_employee_key=%s
        """,
        (session_id, subject_employee_key),
    )
    row = cur.fetchone()
    if not row:
        return {"ok": False, "error": "population_row_missing"}
    frozen = dict(row).get("manager_phone")
    # Caller may update org manager elsewhere; this row must stay frozen.
    return {
        "ok": True,
        "frozen_manager_phone": frozen,
        "reassignment_phone": _digits(new_manager_phone),
        "population_unchanged": True,
        "silently_rewritten": False,
    }


def _get_session(cur: Any, company: str, session_id: str) -> dict[str, Any] | None:
    cur.execute(
        "SELECT * FROM perf_calibration_sessions WHERE company_code=%s AND session_id=%s",
        (company, session_id),
    )
    row = cur.fetchone()
    return dict(row) if row else None


def get_session(cur: Any, *, company_code: str, session_id: str) -> dict[str, Any] | None:
    ensure_performance_calibration_c4_schema(cur)
    return _get_session(cur, company_code_norm(company_code), session_id)


def get_calibrated_result(
    cur: Any, *, company_code: str, session_id: str, subject_employee_key: str
) -> dict[str, Any] | None:
    ensure_performance_calibration_c4_schema(cur)
    cur.execute(
        """
        SELECT * FROM perf_calibrated_results
        WHERE company_code=%s AND session_id=%s AND subject_employee_key=%s
        """,
        (company_code_norm(company_code), session_id, subject_employee_key),
    )
    row = cur.fetchone()
    return dict(row) if row else None
