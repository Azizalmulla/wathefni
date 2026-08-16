#!/usr/bin/env python3
"""PT4 overlay — Dynamic Talent Map over canonical Talent + PT2/PT3 facts.

Not a 9-box product. 9-box remains one derived lens via C6 project_nine_box().
Switching lenses re-projects the same facts; it does not rewrite the employee.
Unknown stays unknown — never forced into a middle bucket.
"""
from __future__ import annotations

import json
from typing import Any

import talent_models_pt2 as pt2
import talent_profile_c5 as c5
import talent_role_fit_pt3 as pt3
import talent_succession_c6 as c6
import talent_surfaces as surfaces

PHASE = "talent_map_pt4"
CONTRACT_VERSION = "talent_map_pt4_v1"
PASS_STAMP = "PT4_DYNAMIC_TALENT_MAP_FULL_PASS"

LENSES = (
    "perf_x_potential",
    "potential_x_readiness",
    "fit_x_readiness",
    "growth_x_contribution",
)

STATUS_LABELS = {
    "perf_x_potential": {"en": "Performance × Potential", "ar": "الأداء × الإمكانات"},
    "potential_x_readiness": {"en": "Potential × Readiness", "ar": "الإمكانات × الجاهزية"},
    "fit_x_readiness": {"en": "Role fit × Readiness", "ar": "الملاءمة × الجاهزية"},
    "growth_x_contribution": {"en": "Growth × Contribution", "ar": "النمو × المساهمة"},
    "unknown": {"en": "Unknown", "ar": "غير معروف"},
    "nine_box": {"en": "9-box (derived)", "ar": "شبكة التسعة (عرض مشتق)"},
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
        "not_a_nine_box_product": True,
        "nine_box_is_one_lens": True,
        "unknown_stays_unknown": True,
        "no_middle_bucket_forcing": True,
        "same_facts_across_lenses": True,
        "no_universal_talent_score": True,
        "no_decorative_ai": True,
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


def ensure_talent_map_pt4_schema(cur: Any, *, force: bool = False) -> None:
    _ = force
    c5.ensure_talent_profile_c5_schema(cur)
    c6.ensure_talent_succession_c6_schema(cur)
    pt2.ensure_talent_models_pt2_schema(cur)
    pt3.ensure_talent_role_fit_pt3_schema(cur)
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS talent_map_placements_pt4 (
          placement_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
          company_code text NOT NULL,
          employee_key text NOT NULL,
          lens text NOT NULL,
          cell text,
          unknown boolean NOT NULL DEFAULT false,
          facts_hash text,
          why jsonb NOT NULL DEFAULT '{}'::jsonb,
          as_of timestamptz NOT NULL DEFAULT now(),
          UNIQUE (company_code, employee_key, lens)
        )
        """
    )


def canonical_employee_facts(
    cur: Any,
    *,
    company_code: str,
    employee_key: str,
    can_see_sensitive: bool = True,
    can_see_performance: bool = True,
) -> dict[str, Any]:
    company = company_code_norm(company_code)
    pot = c5.get_potential_for_viewer(
        cur, company_code=company, employee_key=employee_key, viewer_role="hr", has_sensitive_permission=can_see_sensitive
    )
    assessments = pot.get("assessments") if pot.get("ok") else []
    latest_pot = next((a for a in assessments if str(a.get("status")) in {"submitted", "accepted"}), None)
    hipo = c6.get_hipo_for_viewer(
        cur, company_code=company, employee_key=employee_key, viewer_role="hr", has_sensitive_permission=can_see_sensitive
    )
    designations = hipo.get("designations") if hipo.get("ok") else []
    current_hipo = next((d for d in designations if not d.get("superseded_by_designation_id")), None)
    derived = pt2.list_classifications(cur, company_code=company)
    mine = [c for c in (derived.get("classifications") or []) if str(c.get("employee_key")) == employee_key]
    fits = pt3.list_evaluations(cur, company_code=company)
    my_fit = next((e for e in (fits.get("evaluations") or []) if str(e.get("employee_key")) == employee_key), None)
    cur.execute(
        """
        SELECT readiness FROM talent_successor_nominations
         WHERE company_code=%s AND employee_key=%s AND status='active'
         ORDER BY updated_at DESC LIMIT 1
        """,
        (company, employee_key),
    )
    nom = cur.fetchone()
    human_readiness = str(_row(nom).get("readiness") or "") or None
    perf_value = None
    if can_see_performance:
        cur.execute(
            """
            SELECT detail_en, title_en FROM talent_dimension_facts
             WHERE company_code=%s AND employee_key=%s AND source='performance_outcome' AND status='active'
             ORDER BY version DESC LIMIT 1
            """,
            (company, employee_key),
        )
        fact = cur.fetchone()
        if fact:
            raw = _row(fact).get("detail_en") or _row(fact).get("title_en")
            try:
                perf_value = float(raw)
            except (TypeError, ValueError):
                perf_value = 80.0 if raw else None
    org: dict[str, Any] = {}
    cur.execute(
        "SELECT profile FROM employees WHERE company_code=%s AND employee_key=%s",
        (company, employee_key),
    )
    prow = cur.fetchone()
    raw_profile = _json((_row(prow) if prow else {}).get("profile")) or {}
    if isinstance(raw_profile, dict):
        org = {
            "department": raw_profile.get("department") or raw_profile.get("org_unit"),
            "team": raw_profile.get("team"),
            "manager": raw_profile.get("manager_key") or raw_profile.get("manager"),
            "location": raw_profile.get("location"),
            "grade": raw_profile.get("grade"),
            "job_family": raw_profile.get("job_family"),
            "role": raw_profile.get("role") or raw_profile.get("job_title"),
        }
    return {
        "employee_key": employee_key,
        "human_potential": (latest_pot or {}).get("resulting_level"),
        "designated_hipo": str((current_hipo or {}).get("status") or "") in {"designated", "nominated"},
        "human_hipo": str((current_hipo or {}).get("status") or "not_designated"),
        "derived_classification": (mine[0] or {}).get("classification") if mine else None,
        "role_fit": (my_fit or {}).get("overall_fit"),
        "human_readiness": human_readiness,
        "readiness_suggestion": (my_fit or {}).get("readiness_suggestion"),
        "performance_value": perf_value,
        "trajectory_label": None,
        "org": org,
        "why_classification": str((mine[0] or {}).get("why_id") or "") if mine else None,
        "why_fit": _json((my_fit or {}).get("why")) if my_fit else None,
    }


def project_lens(facts: dict[str, Any], lens: str, *, nine_box_config: dict[str, Any] | None = None) -> dict[str, Any]:
    if lens not in LENSES:
        return {"ok": False, "error": "unknown_lens", "allowed": list(LENSES)}
    x = y = None
    unknown = False
    cell = None
    if lens == "perf_x_potential":
        if nine_box_config:
            proj = c6.project_nine_box(
                config=nine_box_config,
                performance_value=facts.get("performance_value"),
                potential_level=facts.get("human_potential"),
            )
            if not proj.get("available"):
                unknown = True
                cell = None
            else:
                cell = proj.get("cell")
                x = proj.get("performance_band")
                y = proj.get("potential_band")
        else:
            x = facts.get("performance_value")
            y = facts.get("human_potential")
            unknown = x is None or y is None
            cell = None if unknown else f"{x}x{y}"
    elif lens == "potential_x_readiness":
        x = facts.get("human_potential")
        y = facts.get("human_readiness")
        unknown = x is None or y is None
        cell = None if unknown else f"{x}x{y}"
    elif lens == "fit_x_readiness":
        x = facts.get("role_fit")
        y = facts.get("human_readiness") or facts.get("readiness_suggestion")
        unknown = x in (None, "unavailable", "not_assessed") or y in (None, "unassessed")
        cell = None if unknown else f"{x}x{y}"
    else:
        x = facts.get("trajectory_label")
        y = facts.get("performance_value")
        unknown = x is None or y is None
        cell = None if unknown else f"{x}x{y}"
    return {
        "ok": True,
        "lens": lens,
        "x": x,
        "y": y,
        "cell": cell,
        "unknown": unknown,
        "forced_middle": False,
        "employee_key": facts.get("employee_key"),
        "canonical_facts": {
            "human_potential": facts.get("human_potential"),
            "designated_hipo": facts.get("designated_hipo"),
            "derived_classification": facts.get("derived_classification"),
            "role_fit": facts.get("role_fit"),
            "human_readiness": facts.get("human_readiness"),
            "performance_value": facts.get("performance_value"),
        },
    }


def _matches_filters(facts: dict[str, Any], filters: dict[str, Any] | None) -> bool:
    if not filters:
        return True
    org = facts.get("org") or {}
    for key in ("department", "team", "manager", "location", "grade", "job_family", "role"):
        wanted = filters.get(key)
        if not wanted:
            continue
        actual = org.get(key) or org.get("manager_key" if key == "manager" else key)
        if actual is None:
            return False
        if str(actual).lower() != str(wanted).lower():
            return False
    return True


def build_map(
    cur: Any,
    *,
    company_code: str,
    lens: str = "perf_x_potential",
    filters: dict[str, Any] | None = None,
    can_see_sensitive: bool = True,
    can_see_performance: bool = True,
    manager_scope_keys: list[str] | None = None,
    actor_role: str = "hr",
) -> dict[str, Any]:
    if lens not in LENSES:
        return {"ok": False, "error": "unknown_lens", "allowed": list(LENSES)}
    company = company_code_norm(company_code)
    ensure_talent_map_pt4_schema(cur)
    listed = surfaces.list_profiles(cur, company_code=company, manager_scope_keys=manager_scope_keys, actor_role=actor_role)
    nine_cfg = None
    cur.execute(
        "SELECT * FROM talent_nine_box_configs WHERE company_code=%s ORDER BY created_at DESC LIMIT 1",
        (company,),
    )
    row = cur.fetchone()
    if row:
        nine_cfg = _row(row)
    placements = []
    fact_snapshots = []
    for profile in listed.get("profiles") or []:
        key = str(profile.get("employee_key") or "")
        if not key:
            continue
        facts = canonical_employee_facts(
            cur, company_code=company, employee_key=key,
            can_see_sensitive=can_see_sensitive, can_see_performance=can_see_performance,
        )
        if not _matches_filters(facts, filters):
            continue
        place = project_lens(facts, lens, nine_box_config=nine_cfg)
        why = {
            "subject": "placement",
            "lens": lens,
            "employee_key": key,
            "evidence_consumed": [k for k, v in (place.get("canonical_facts") or {}).items() if v not in (None, "", False)],
            "missing_evidence": [k for k, v in (place.get("canonical_facts") or {}).items() if v in (None, "")],
            "unknown": place.get("unknown"),
            "forced_middle": False,
            "classification_why_id": facts.get("why_classification"),
            "role_fit_why": facts.get("why_fit"),
            "model_id": None,
            "version": None,
        }
        cur.execute(
            """
            INSERT INTO talent_map_placements_pt4 (
              company_code, employee_key, lens, cell, unknown, why
            ) VALUES (%s,%s,%s,%s,%s,%s::jsonb)
            ON CONFLICT (company_code, employee_key, lens) DO UPDATE SET
              cell=EXCLUDED.cell, unknown=EXCLUDED.unknown, why=EXCLUDED.why, as_of=now()
            RETURNING *
            """,
            (company, key, lens, place.get("cell"), bool(place.get("unknown")), json.dumps(why, default=str)),
        )
        stored = _row(cur.fetchone())
        placements.append({**place, "placement_id": stored.get("placement_id"), "why": why})
        fact_snapshots.append(facts)
    return {
        "ok": True,
        "lens": lens,
        "lenses": [{"id": item, "label_en": status_label(item, lang="en"), "label_ar": status_label(item, lang="ar")} for item in LENSES],
        "placements": placements,
        "unknown_count": sum(1 for p in placements if p.get("unknown")),
        "fact_snapshots": fact_snapshots,
        "filters_applied": {k: v for k, v in (filters or {}).items() if v},
        "progressive_filters_only": True,
        **honesty_payload(company_code=company),
    }


def get_placement_why(cur: Any, *, company_code: str, employee_key: str, lens: str) -> dict[str, Any]:
    company = company_code_norm(company_code)
    ensure_talent_map_pt4_schema(cur)
    cur.execute(
        "SELECT * FROM talent_map_placements_pt4 WHERE company_code=%s AND employee_key=%s AND lens=%s",
        (company, employee_key, lens),
    )
    row = cur.fetchone()
    if not row:
        return {"ok": False, "error": "placement_not_found"}
    item = _row(row)
    return {"ok": True, "why": _json(item.get("why")) or {}, "placement": item, **honesty_payload(company_code=company)}
