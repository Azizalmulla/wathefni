#!/usr/bin/env python3
"""PT5 overlay — succession intelligence + advisory internal mobility.

Deepens frozen C6 without replacing it. No second holder record.
Bench depth is honest counts, not a 0–100 score.
Mobility match ≠ application ≠ selection ≠ employment change.
"""
from __future__ import annotations

import json
from typing import Any

import talent_profile_c5 as c5
import talent_role_fit_pt3 as pt3
import talent_succession_c6 as c6

PHASE = "talent_succession_intel_pt5"
CONTRACT_VERSION = "talent_succession_intel_pt5_v1"
PASS_STAMP = "PT5_SUCCESSION_MOBILITY_INTELLIGENCE_FULL_PASS"

DEFAULT_CONCENTRATION_N = 3

STATUS_LABELS = {
    "uncovered": {"en": "No successors", "ar": "بلا خلفاء"},
    "no_ready_now": {"en": "No ready-now successor", "ar": "لا خلف جاهز الآن"},
    "single_successor": {"en": "Single-successor dependency", "ar": "اعتماد على خلف واحد"},
    "concentration": {"en": "Succession concentration", "ar": "تركّز التعاقب"},
    "advisory_match": {"en": "Advisory mobility match", "ar": "مطابقة تنقل استشارية"},
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
        "c6_remains_succession_sot": True,
        "no_second_holder_record": True,
        "bench_is_counts_not_score": True,
        "no_opaque_rank_score": True,
        "mobility_is_not_application": True,
        "no_silent_candidate": True,
        "no_silent_transfer": True,
        "talent_works_recruiting_off": True,
        "what_if_is_pt8": True,
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


def ensure_talent_succession_intel_pt5_schema(cur: Any, *, force: bool = False) -> None:
    _ = force
    c5.ensure_talent_profile_c5_schema(cur)
    c6.ensure_talent_succession_c6_schema(cur)
    pt3.ensure_talent_role_fit_pt3_schema(cur)
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS talent_mobility_matches_pt5 (
          match_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
          company_code text NOT NULL,
          employee_key text NOT NULL,
          destination_profile_id text,
          destination_role_key text,
          edge_type text,
          overall_fit text,
          is_not_application boolean NOT NULL DEFAULT true,
          recruiting_handoff boolean NOT NULL DEFAULT false,
          candidate_created boolean NOT NULL DEFAULT false,
          employment_mutated boolean NOT NULL DEFAULT false,
          why jsonb NOT NULL DEFAULT '{}'::jsonb,
          created_at timestamptz NOT NULL DEFAULT now(),
          CONSTRAINT tmm_pt5_advisory_chk CHECK (is_not_application = true),
          CONSTRAINT tmm_pt5_no_candidate_chk CHECK (candidate_created = false),
          CONSTRAINT tmm_pt5_no_transfer_chk CHECK (employment_mutated = false)
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS talent_succession_intel_pt5_settings (
          company_code text PRIMARY KEY,
          concentration_n int NOT NULL DEFAULT 3,
          updated_at timestamptz NOT NULL DEFAULT now()
        )
        """
    )


def _current_holder(cur: Any, *, company: str, critical_role: dict[str, Any]) -> dict[str, Any] | None:
    position_id = critical_role.get("canonical_position_id")
    role_key = critical_role.get("canonical_role_key")
    if position_id:
        cur.execute(
            """
            SELECT employee_key FROM employees
             WHERE company_code=%s AND (
               profile->>'position_id' = %s OR profile->>'canonical_position_id' = %s
             )
             LIMIT 1
            """,
            (company, str(position_id), str(position_id)),
        )
        row = cur.fetchone()
        if row:
            return {"employee_key": _row(row).get("employee_key"), "source": "employment_profile"}
    try:
        import job_architecture_c1 as ja

        if ja.runtime_gate_for_company(company).get("ok") and role_key:
            cur.execute(
                """
                SELECT employee_key FROM ja_employment_assignment
                 WHERE company_code=%s AND superseded_by IS NULL AND effective_end IS NULL
                 LIMIT 5
                """,
                (company,),
            )
            # Holder remains employment/JA truth — we do not invent a PT holder row.
    except Exception:
        pass
    return None


def succession_intelligence(cur: Any, *, company_code: str, concentration_n: int | None = None) -> dict[str, Any]:
    company = company_code_norm(company_code)
    ensure_talent_succession_intel_pt5_schema(cur)
    n = int(concentration_n or DEFAULT_CONCENTRATION_N)
    uncovered = c6.list_uncovered_critical_roles(cur, company_code=company)
    cur.execute("SELECT * FROM talent_critical_roles WHERE company_code=%s AND status='active'", (company,))
    roles = [_row(r) for r in (cur.fetchall() or [])]
    cur.execute(
        """
        SELECT critical_role_id, employee_key, readiness, status
          FROM talent_successor_nominations
         WHERE company_code=%s AND status='active'
        """,
        (company,),
    )
    noms = [_row(r) for r in (cur.fetchall() or [])]
    by_role: dict[str, list[dict[str, Any]]] = {}
    by_person: dict[str, list[str]] = {}
    for nom in noms:
        rid = str(nom.get("critical_role_id"))
        by_role.setdefault(rid, []).append(nom)
        by_person.setdefault(str(nom.get("employee_key")), []).append(rid)

    facts = []
    for role in roles:
        rid = str(role.get("critical_role_id"))
        slate = by_role.get(rid) or []
        ready_now = [s for s in slate if s.get("readiness") == "ready_now"]
        holder = _current_holder(cur, company=company, critical_role=role)
        fact = {
            "critical_role_id": rid,
            "canonical_role_key": role.get("canonical_role_key"),
            "title_en": role.get("title_en"),
            "title_ar": role.get("title_ar"),
            "current_holder": holder,
            "successor_count": len(slate),
            "ready_now_count": len(ready_now),
            "ready_lt_1y_count": len([s for s in slate if s.get("readiness") == "ready_lt_1y"]),
            "uncovered": len(slate) == 0,
            "no_ready_now": len(slate) > 0 and len(ready_now) == 0,
            "single_successor_risk": len(slate) == 1,
            "bench_counts": {
                "ready_now": len(ready_now),
                "ready_lt_1y": len([s for s in slate if s.get("readiness") == "ready_lt_1y"]),
                "other": len(slate) - len(ready_now) - len([s for s in slate if s.get("readiness") == "ready_lt_1y"]),
            },
            "bench_score": None,
            "invented_candidates": False,
        }
        facts.append(fact)

    concentration = [
        {"employee_key": emp, "critical_role_ids": roles_for, "role_count": len(roles_for)}
        for emp, roles_for in by_person.items()
        if len(roles_for) >= n
    ]
    return {
        "ok": True,
        "roles": facts,
        "uncovered_critical_roles": [f for f in facts if f["uncovered"]],
        "zero_ready_now": [f for f in facts if f["no_ready_now"]],
        "single_successor": [f for f in facts if f["single_successor_risk"]],
        "concentration_risk": concentration,
        "concentration_n": n,
        "c6_uncovered": uncovered.get("roles") or uncovered.get("uncovered") or [],
        "master_rank_score": None,
        **honesty_payload(company_code=company),
    }


def compare_successors(cur: Any, *, company_code: str, critical_role_id: str) -> dict[str, Any]:
    company = company_code_norm(company_code)
    intel = succession_intelligence(cur, company_code=company)
    role = next((r for r in intel.get("roles") or [] if str(r.get("critical_role_id")) == str(critical_role_id)), None)
    cur.execute(
        """
        SELECT employee_key, readiness, rationale FROM talent_successor_nominations
         WHERE company_code=%s AND critical_role_id=%s AND status='active'
        """,
        (company, critical_role_id),
    )
    noms = [_row(r) for r in (cur.fetchall() or [])]
    comparisons = []
    for nom in noms:
        fits = pt3.list_evaluations(cur, company_code=company)
        mine = next((e for e in (fits.get("evaluations") or []) if str(e.get("employee_key")) == str(nom.get("employee_key"))), None)
        comparisons.append(
            {
                "employee_key": nom.get("employee_key"),
                "human_readiness": nom.get("readiness"),
                "role_fit": (mine or {}).get("overall_fit"),
                "why": _json((mine or {}).get("why")) if mine else {"missing_evidence": ["no_role_fit_evaluation"]},
                "opaque_score": None,
            }
        )
    return {
        "ok": True,
        "critical_role_id": critical_role_id,
        "comparisons": comparisons,
        "silent_ranking": False,
        "role": role,
        **honesty_payload(company_code=company),
    }


def _recruiting_on(company: str) -> bool:
    try:
        import capability_readiness as ready

        return bool(ready.customer_enableable("recruiting"))
    except Exception:
        return False


def discover_mobility(
    cur: Any,
    *,
    company_code: str,
    actor_phone: str,
    employee_key: str,
    reason: str = "advisory mobility discovery",
) -> dict[str, Any]:
    if not str(reason or "").strip():
        return {"ok": False, "error": "audit_reason_required"}
    company = company_code_norm(company_code)
    ensure_talent_succession_intel_pt5_schema(cur)
    interests = c5.list_dimension_facts(
        cur, company_code=company, employee_key=employee_key, viewer_role="hr", has_sensitive_permission=True
    )
    facts = [f for f in (interests.get("facts") or []) if str(f.get("dimension_kind")) in {"role_interest", "job_family_interest", "mobility_preference", "career_aspiration"}]
    destinations: list[dict[str, Any]] = []
    try:
        import job_architecture_c1 as ja

        if ja.runtime_gate_for_company(company).get("ok"):
            cur.execute(
                "SELECT * FROM ja_career_edge WHERE company_code=%s AND status='published'",
                (company,),
            )
            for edge in cur.fetchall() or []:
                edge = _row(edge)
                destinations.append(
                    {
                        "destination_profile_id": edge.get("to_profile_id"),
                        "edge_type": edge.get("edge_type"),
                        "source": "ja_career_edge",
                    }
                )
    except Exception:
        pass
    fits = pt3.list_evaluations(cur, company_code=company)
    my_fits = [e for e in (fits.get("evaluations") or []) if str(e.get("employee_key")) == employee_key]
    matches = []
    seed = list(destinations)
    if not seed and facts:
        seed = [{"destination_role_key": facts[0].get("title_en"), "edge_type": "lateral", "source": "interest"}]
    for dest in seed:
        fit = next((e for e in my_fits if str(e.get("overall_fit")) in {"strong_fit", "partial_fit"}), None)
        why = {
            "subject": "mobility",
            "employee_key": employee_key,
            "destination": dest,
            "interests": [{"kind": f.get("dimension_kind"), "title": f.get("title_en")} for f in facts],
            "role_fit": (fit or {}).get("overall_fit"),
            "is_not_application": True,
            "recruiting_handoff": False,
        }
        cur.execute(
            """
            INSERT INTO talent_mobility_matches_pt5 (
              company_code, employee_key, destination_profile_id, destination_role_key,
              edge_type, overall_fit, why
            ) VALUES (%s,%s,%s,%s,%s,%s,%s::jsonb)
            RETURNING *
            """,
            (
                company,
                employee_key,
                dest.get("destination_profile_id"),
                dest.get("destination_role_key"),
                dest.get("edge_type") or "lateral",
                (fit or {}).get("overall_fit"),
                json.dumps(why, default=str),
            ),
        )
        stored = _row(cur.fetchone())
        matches.append({**stored, "why": why, "is_not_application": True, "recruiting_available": _recruiting_on(company)})
    return {
        "ok": True,
        "matches": matches,
        "is_not_application": True,
        "candidate_created": False,
        "employment_mutated": False,
        "recruiting_handoff_required": True,
        **honesty_payload(company_code=company),
    }


def refer_to_internal_opportunity(
    cur: Any,
    *,
    company_code: str,
    match_id: str,
    reason: str,
) -> dict[str, Any]:
    """Explicit Recruiting handoff only. Never silent candidate creation."""
    if not str(reason or "").strip():
        return {"ok": False, "error": "audit_reason_required"}
    company = company_code_norm(company_code)
    cur.execute("SELECT * FROM talent_mobility_matches_pt5 WHERE company_code=%s AND match_id=%s", (company, match_id))
    row = cur.fetchone()
    if not row:
        return {"ok": False, "error": "match_not_found"}
    if not _recruiting_on(company):
        return {
            "ok": False,
            "error": "recruiting_off",
            "handoff": False,
            "candidate_created": False,
            **honesty_payload(company_code=company),
        }
    return {
        "ok": True,
        "handoff": "ready",
        "candidate_created": False,
        "application_created": False,
        "explicit_handoff_required": True,
        "match": _row(row),
        **honesty_payload(company_code=company),
    }
