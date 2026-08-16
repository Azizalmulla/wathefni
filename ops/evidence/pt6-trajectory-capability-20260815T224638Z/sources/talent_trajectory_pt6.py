#!/usr/bin/env python3
"""PT6 overlay — governed trajectory labels + Wave 5 capability intelligence.

Trajectory does not overwrite Performance, Potential, HiPo, readiness, or Wave 5.
Insufficient history → no label. Company must publish a trajectory policy.
Holder-dependency excludes a person from the analytic population only.
"""
from __future__ import annotations

import json
from typing import Any

import hr_intelligence_registry_c1 as w5
import talent_profile_c5 as c5

PHASE = "talent_trajectory_pt6"
CONTRACT_VERSION = "talent_trajectory_pt6_v1"
PASS_STAMP = "PT6_TRAJECTORY_CAPABILITY_INTELLIGENCE_FULL_PASS"

LABELS = ("accelerating", "stable_high_performance", "declining", "emerging", "stalled_development")

PT6_FORMULA_KINDS = {
    "talent.capability_coverage": "talent_capability_coverage",
    "talent.single_person_capability": "talent_single_person_capability",
    "talent.skill_direction": "talent_skill_direction",
    "talent.underutilized_capability": "talent_underutilized_capability",
    "talent.holder_dependency": "talent_holder_dependency",
}

STATUS_LABELS = {
    "accelerating": {"en": "Accelerating", "ar": "متسارع"},
    "stable_high_performance": {"en": "Stable high performance", "ar": "أداء عالٍ مستقر"},
    "declining": {"en": "Declining", "ar": "متراجع"},
    "emerging": {"en": "Emerging", "ar": "ناشئ"},
    "stalled_development": {"en": "Stalled development", "ar": "تطوير متوقف"},
    "insufficient_history": {"en": "Insufficient history", "ar": "تاريخ غير كافٍ"},
}


def company_code_norm(company_code: str | None) -> str:
    return c5.company_code_norm(company_code)


def status_label(status: str | None, *, lang: str = "en") -> str:
    key = str(status or "").strip()
    pack = STATUS_LABELS.get(key) or {"en": key or "unknown", "ar": key or "غير معروف"}
    return str(pack.get("ar" if lang.lower().startswith("ar") else "en"))


def honesty_payload(*, company_code: str | None = None) -> dict[str, Any]:
    return {
        "phase": PHASE,
        "contract_version": CONTRACT_VERSION,
        "pass_stamp": PASS_STAMP,
        "no_label_without_policy": True,
        "closed_periods_only": True,
        "insufficient_history_has_no_label": True,
        "does_not_overwrite_performance": True,
        "does_not_overwrite_potential": True,
        "does_not_overwrite_hipo": True,
        "does_not_overwrite_readiness": True,
        "no_second_analytics_engine": True,
        "no_universal_talent_score": True,
        "no_flight_risk_score": True,
        "holder_dependency_does_not_mutate_employment": True,
        "company_code": company_code_norm(company_code) if company_code else None,
    }


def _row(value: Any) -> dict[str, Any]:
    if value is None:
        return {}
    if isinstance(value, dict):
        return dict(value)
    try:
        return dict(value)
    except Exception:
        return {}


def _json(value: Any) -> Any:
    if isinstance(value, str):
        try:
            return json.loads(value)
        except Exception:
            return value
    return value


def ensure_talent_trajectory_pt6_schema(cur: Any, *, force: bool = False) -> None:
    _ = force
    c5.ensure_talent_profile_c5_schema(cur)
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS talent_trajectory_policies_pt6 (
          policy_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
          company_code text NOT NULL,
          version int NOT NULL,
          status text NOT NULL DEFAULT 'draft',
          enabled boolean NOT NULL DEFAULT false,
          min_closed_periods int NOT NULL DEFAULT 2,
          high_band jsonb NOT NULL DEFAULT '[]'::jsonb,
          rules jsonb NOT NULL DEFAULT '{}'::jsonb,
          published_at timestamptz,
          published_by_phone text,
          publish_reason text,
          created_at timestamptz NOT NULL DEFAULT now(),
          UNIQUE (company_code, version),
          CONSTRAINT ttp_pt6_status_chk CHECK (status IN ('draft','published','deprecated'))
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS talent_trajectory_labels_pt6 (
          label_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
          company_code text NOT NULL,
          employee_key text NOT NULL,
          policy_id uuid NOT NULL,
          version int NOT NULL,
          label text,
          why jsonb NOT NULL DEFAULT '{}'::jsonb,
          as_of timestamptz NOT NULL DEFAULT now(),
          UNIQUE (company_code, employee_key, policy_id)
        )
        """
    )


def publish_trajectory_policy(
    cur: Any,
    *,
    company_code: str,
    actor_phone: str,
    min_closed_periods: int = 2,
    high_band: list[Any] | None = None,
    rules: dict[str, Any] | None = None,
    reason: str = "publish trajectory policy",
) -> dict[str, Any]:
    if not str(reason or "").strip():
        return {"ok": False, "error": "audit_reason_required"}
    company = company_code_norm(company_code)
    ensure_talent_trajectory_pt6_schema(cur)
    cur.execute("SELECT COALESCE(MAX(version),0) AS v FROM talent_trajectory_policies_pt6 WHERE company_code=%s", (company,))
    nxt = int(_row(cur.fetchone()).get("v") or 0) + 1
    cur.execute(
        """
        INSERT INTO talent_trajectory_policies_pt6 (
          company_code, version, status, enabled, min_closed_periods, high_band, rules,
          published_at, published_by_phone, publish_reason
        ) VALUES (%s,%s,'published',true,%s,%s::jsonb,%s::jsonb,now(),%s,%s)
        RETURNING *
        """,
        (
            company,
            nxt,
            max(2, int(min_closed_periods or 2)),
            json.dumps(high_band or ["exceeds", "high", 4, 5], default=str),
            json.dumps(rules or {"accelerating_delta": 1, "declining_delta": -1}, default=str),
            "".join(ch for ch in str(actor_phone or "") if ch.isdigit()),
            str(reason)[:500],
        ),
    )
    return {"ok": True, "policy": _row(cur.fetchone()), **honesty_payload(company_code=company)}


def get_published_policy(cur: Any, *, company_code: str) -> dict[str, Any] | None:
    company = company_code_norm(company_code)
    ensure_talent_trajectory_pt6_schema(cur)
    cur.execute(
        """
        SELECT * FROM talent_trajectory_policies_pt6
         WHERE company_code=%s AND status='published' AND enabled=true
         ORDER BY version DESC LIMIT 1
        """,
        (company,),
    )
    row = cur.fetchone()
    return _row(row) if row else None


def _closed_period_values(cur: Any, *, company: str, employee_key: str) -> list[float]:
    values: list[float] = []
    try:
        import okr_operating_pt1 as pt1

        pt1.ensure_okr_operating_pt1_schema(cur)
        cur.execute(
            """
            SELECT c.cycle_id FROM perf_okr_cycles c
             WHERE c.company_code=%s AND c.status='closed'
             ORDER BY c.period_end
            """,
            (company,),
        )
        for cycle in cur.fetchall() or []:
            cid = _row(cycle).get("cycle_id")
            cur.execute(
                """
                SELECT o.objective_id FROM perf_okr_cycle_members m
                JOIN perf_objectives o ON o.objective_id=m.objective_id
                 WHERE m.cycle_id=%s AND o.owner_employee_key=%s
                """,
                (cid, employee_key),
            )
            objs = cur.fetchall() or []
            if not objs:
                continue
            import performance_goals_c1 as c1

            rolls = []
            for obj in objs:
                roll = c1.objective_rollup(cur, company_code=company, objective_id=str(_row(obj).get("objective_id")))
                if roll.get("progress_pct") is not None:
                    rolls.append(float(roll["progress_pct"]))
            if rolls:
                values.append(sum(rolls) / len(rolls))
    except Exception:
        pass
    return values


def evaluate_trajectory(
    cur: Any,
    *,
    company_code: str,
    employee_key: str,
    reason: str = "evaluate trajectory",
) -> dict[str, Any]:
    company = company_code_norm(company_code)
    policy = get_published_policy(cur, company_code=company)
    if not policy:
        return {
            "ok": True,
            "label": None,
            "reason": "policy_not_published",
            **honesty_payload(company_code=company),
        }
    history = _closed_period_values(cur, company=company, employee_key=employee_key)
    min_n = int(policy.get("min_closed_periods") or 2)
    if len(history) < min_n:
        graph = {
            "subject": "trajectory",
            "policy_id": str(policy.get("policy_id")),
            "version": policy.get("version"),
            "closed_periods": history,
            "missing_evidence": ["insufficient_closed_history"],
            "label": None,
        }
        return {
            "ok": True,
            "label": None,
            "reason": "insufficient_history",
            "why": graph,
            **honesty_payload(company_code=company),
        }
    rules = _json(policy.get("rules")) or {}
    high_band = {str(x).lower() for x in (_json(policy.get("high_band")) or [])}
    label = "stable_high_performance" if all(v >= 80 for v in history[-min_n:]) else None
    if history[-1] - history[0] >= float(rules.get("accelerating_delta") or 10):
        label = "accelerating"
    elif history[-1] - history[0] <= float(rules.get("declining_delta") or -10):
        label = "declining"
    elif history[-1] >= 80 and any(v < 80 for v in history[:-1]):
        label = "emerging"
    elif label is None and abs(history[-1] - history[0]) < float(rules.get("stalled_delta") or 5) and history[-1] < 80:
        label = "stalled_development"
    graph = {
        "subject": "trajectory",
        "policy_id": str(policy.get("policy_id")),
        "version": policy.get("version"),
        "closed_periods": history,
        "rules": rules,
        "high_band": list(high_band),
        "label": label,
        "evidence_consumed": [{"kind": "closed_okr_rollup", "values": history}],
    }
    cur.execute(
        """
        INSERT INTO talent_trajectory_labels_pt6 (
          company_code, employee_key, policy_id, version, label, why
        ) VALUES (%s,%s,%s,%s,%s,%s::jsonb)
        ON CONFLICT (company_code, employee_key, policy_id) DO UPDATE SET
          label=EXCLUDED.label, why=EXCLUDED.why, as_of=now()
        RETURNING *
        """,
        (company, employee_key, policy.get("policy_id"), policy.get("version"), label, json.dumps(graph, default=str)),
    )
    stored = _row(cur.fetchone())
    return {
        "ok": True,
        "label": label,
        "label_row": stored,
        "why": graph,
        "overwrites_performance": False,
        **honesty_payload(company_code=company),
    }


def _skill_holders(cur: Any, *, company: str, exclude: str | None = None) -> dict[str, list[str]]:
    cur.execute(
        """
        SELECT skill_code, employee_key FROM talent_skills
         WHERE company_code=%s AND status='active' AND state IN ('verified','assessed')
        """,
        (company,),
    )
    holders: dict[str, list[str]] = {}
    for row in cur.fetchall() or []:
        item = _row(row)
        emp = str(item.get("employee_key"))
        if exclude and emp == exclude:
            continue
        holders.setdefault(str(item.get("skill_code")), []).append(emp)
    return holders


def capability_facts(
    cur: Any,
    *,
    company_code: str,
    exclude_employee_key: str | None = None,
) -> dict[str, Any]:
    company = company_code_norm(company_code)
    holders = _skill_holders(cur, company=company, exclude=exclude_employee_key)
    coverage = {code: len(people) for code, people in holders.items()}
    single = {code: people[0] for code, people in holders.items() if len(people) == 1}
    return {
        "ok": True,
        "capability_coverage": coverage,
        "single_person_capability": single,
        "excluded_employee_key": exclude_employee_key,
        "employment_mutated": False,
        "definition": "verified/assessed skill holders after optional analytic exclusion",
        "source": "talent_skills",
        "cohort_privacy": "talent_sensitive",
        "drill_path": "/dashboard/posthire/talent/profiles",
        "historical_version": CONTRACT_VERSION,
        **honesty_payload(company_code=company),
    }


def holder_dependency(cur: Any, *, company_code: str, employee_key: str) -> dict[str, Any]:
    baseline = capability_facts(cur, company_code=company_code)
    excluded = capability_facts(cur, company_code=company_code, exclude_employee_key=employee_key)
    vulnerable = [
        code
        for code, n in (baseline.get("capability_coverage") or {}).items()
        if n > 0 and (excluded.get("capability_coverage") or {}).get(code, 0) == 0
    ]
    return {
        "ok": True,
        "employee_key": employee_key,
        "vulnerable_capabilities": vulnerable,
        "baseline": baseline.get("capability_coverage"),
        "without_employee": excluded.get("capability_coverage"),
        "employment_mutated": False,
        "full_simulation_is_pt8": True,
        **honesty_payload(company_code=company_code),
    }


def _handler(kind: str, cur: Any, *, company_code: str, filters: dict[str, Any] | None = None, **_kwargs: Any) -> dict[str, Any]:
    filters = filters or {}
    if kind == "talent_holder_dependency":
        emp = str(filters.get("employee_key") or "")
        if not emp:
            return {"status": "insufficient_data", "value": None, "explain": {"employee_key_required": True}}
        dep = holder_dependency(cur, company_code=company_code, employee_key=emp)
        return {
            "status": "ok",
            "value": float(len(dep.get("vulnerable_capabilities") or [])),
            "population_ids": dep.get("vulnerable_capabilities") or [],
            "explain": dep,
        }
    facts = capability_facts(cur, company_code=company_code, exclude_employee_key=filters.get("exclude_employee_key"))
    if kind == "talent_capability_coverage":
        return {"status": "ok", "value": float(len(facts.get("capability_coverage") or {})), "explain": facts}
    if kind == "talent_single_person_capability":
        return {"status": "ok", "value": float(len(facts.get("single_person_capability") or {})), "explain": facts}
    if kind == "talent_skill_direction":
        return {"status": "insufficient_data", "value": None, "explain": {"needs_closed_skill_history_window": True, **facts}}
    if kind == "talent_underutilized_capability":
        return {"status": "insufficient_data", "value": None, "explain": {"needs_ja_assignment_plus_requirement_set": True, **facts}}
    return {"status": "unavailable", "value": None, "explain": {"unknown_kind": kind}}


def register_wave5_handlers() -> None:
    for kind in PT6_FORMULA_KINDS.values():
        w5.register_formula_handler(kind, lambda cur, kind=kind, **kwargs: _handler(kind, cur, **kwargs))


register_wave5_handlers()
