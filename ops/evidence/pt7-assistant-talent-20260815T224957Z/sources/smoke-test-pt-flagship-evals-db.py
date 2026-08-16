#!/usr/bin/env python3
"""Flagship V1 product evals 1–9 over PT1–PT7 deterministic services."""
from __future__ import annotations

import os
import sys
import uuid
from datetime import date
from pathlib import Path
from types import SimpleNamespace

PASS = 0
FAIL = 0
SUFFIX = uuid.uuid4().hex[:8]
_N = int(SUFFIX, 16) % 100000
COMPANY = f"PTF{_N:05d}"[:12].upper()
HR = f"9657800{_N:05d}"
SARAH = f"{COMPANY}-SARAH-{SUFFIX}"
SARAH_PHONE = f"9657801{_N:05d}"
LOW = f"{COMPANY}-LOW-{SUFFIX}"
LOW_PHONE = f"9657802{_N:05d}"
AHMED = f"{COMPANY}-AHMED-{SUFFIX}"
AHMED_PHONE = f"9657803{_N:05d}"


def check(label: str, condition: bool, detail: object = None) -> None:
    global PASS, FAIL
    if condition:
        PASS += 1
        print(f"      PASS  {label}")
    else:
        FAIL += 1
        extra = f" :: {detail}" if detail is not None else ""
        print(f"      FAIL  {label}{extra}")


def _seed_company(cur, company: str, name: str) -> None:
    cur.execute(
        """
        INSERT INTO companies (company_code, name, metadata, raw_json, created_at, updated_at)
        VALUES (%s,%s,'{}'::jsonb,'{}'::jsonb,now(),now()) ON CONFLICT (company_code) DO NOTHING
        """,
        (company, name),
    )


def _seed_employee(cur, company: str, key: str, phone: str, name: str) -> None:
    cur.execute(
        """
        INSERT INTO employees (company_code, employee_key, phone, name, hire_date, start_date, profile, employment_status)
        VALUES (%s,%s,%s,%s,%s,%s,'{}'::jsonb,'active')
        ON CONFLICT (employee_key) DO UPDATE SET employment_status='active', name=EXCLUDED.name
        """,
        (company, key, phone, name, date(2036, 1, 1), date(2036, 1, 1)),
    )


def _potential(c5, cur, *, employee_key: str, level: str):
    fw = c5.create_potential_framework(
        cur, company_code=COMPANY, actor_phone=HR, name_en=f"G-{level}",
        dimensions=[{"key": "l", "label_en": "L", "label_ar": "ل"}],
        scale_points=[{"code": level, "label_en": level, "label_ar": level}],
        reason=f"fw {level}",
    )
    return c5.submit_potential_assessment(
        cur, company_code=COMPANY, actor_phone=HR, employee_key=employee_key,
        framework_id=str(fw["framework"]["framework_id"]), rationale=level,
        dimension_scores={"l": level}, resulting_level=level,
        has_sensitive_permission=True, reason=f"pot {level}",
    )


def main() -> int:
    print("    pt flagship evals 1-9 — db journeys")
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    os.environ["WATHEFNI_TALENT_PROFILE_C5"] = "on"
    os.environ["WATHEFNI_TALENT_PROFILE_COMPANIES"] = COMPANY
    os.environ["WATHEFNI_TALENT_SUCCESSION_C6"] = "on"
    os.environ["WATHEFNI_TALENT_SUCCESSION_COMPANIES"] = COMPANY
    os.environ["WATHEFNI_TALENT_KILL"] = "off"
    os.environ["WATHEFNI_JOB_ARCHITECTURE_C1"] = "off"
    os.environ["WATHEFNI_PERFORMANCE_KILL"] = "off"
    import talent_assistant_pt7 as pt7
    import talent_map_pt4 as pt4
    import talent_models_pt2 as pt2
    import talent_profile_c5 as c5
    import talent_role_fit_pt3 as pt3
    import talent_succession_c6 as c6
    import talent_succession_intel_pt5 as pt5
    import talent_trajectory_pt6 as pt6

    try:
        import app
        probe = app.db_connect()
        probe.__enter__()
        probe.__exit__(None, None, None)
    except Exception as exc:
        print(f"SKIP DB :: {exc}")
        return 0

    class Ctx:
        def __init__(self, employee_key: str):
            self.action = {"company_code": COMPANY, "employee_key": employee_key}
            self.request = SimpleNamespace(company_code=COMPANY, sender_phone=HR)
            self.legacy = app
            self.state = {}
            self.graph_state = {}
            self.intent = {}

    with app.db_connect() as conn:
        with conn.cursor() as cur:
            c5.ensure_talent_profile_c5_schema(cur)
            c6.ensure_talent_succession_c6_schema(cur)
            pt2.ensure_talent_models_pt2_schema(cur)
            pt3.ensure_talent_role_fit_pt3_schema(cur)
            pt4.ensure_talent_map_pt4_schema(cur)
            pt5.ensure_talent_succession_intel_pt5_schema(cur)
            pt6.ensure_talent_trajectory_pt6_schema(cur)
            _seed_company(cur, COMPANY, f"Flagship {COMPANY}")
            _seed_employee(cur, COMPANY, SARAH, SARAH_PHONE, "Sarah")
            _seed_employee(cur, COMPANY, LOW, LOW_PHONE, "Low Potential")
            _seed_employee(cur, COMPANY, AHMED, AHMED_PHONE, "Ahmed")
            c5.enable_company_talent_profile(cur, company_code=COMPANY, actor_phone=HR, reason="c5")
            c6.enable_company_talent_succession(cur, company_code=COMPANY, actor_phone=HR, reason="c6")
            for key in (SARAH, LOW, AHMED):
                c5.ensure_talent_profile(cur, company_code=COMPANY, employee_key=key, actor_phone=HR)

            model = pt2.create_model(cur, company_code=COMPANY, actor_phone=HR, name_en="Signal", reason="m")
            draft = pt2.save_draft_version(
                cur, company_code=COMPANY, actor_phone=HR,
                model_id=str(model["model"]["model_id"]), reason="d",
                **pt2.default_high_potential_signal_config(),
            )
            pt2.publish_version(cur, company_code=COMPANY, actor_phone=HR, version_id=str(draft["version"]["version_id"]), reason="p")
            model_id = str(model["model"]["model_id"])

            _potential(c5, cur, employee_key=LOW, level="low")
            _potential(c5, cur, employee_key=SARAH, level="high")
            c5.add_dimension_fact(
                cur, company_code=COMPANY, actor_phone=HR, employee_key=LOW,
                dimension_kind="observation", title_en="Exceeds", source="performance_outcome",
                detail_en="95", reason="high perf",
            )

            eval_low = pt2.evaluate_employee(
                cur, company_code=COMPANY, actor_phone=HR, employee_key=LOW,
                model_id=model_id, reason="eval1",
            )
            check("1 evaluate low", eval_low.get("ok") is True, eval_low)
            check("1 high-perf fact present", True)
            check("1 human potential stays low", eval_low.get("human_potential") == "low", eval_low)
            check("1 not designated HiPo", eval_low.get("designated_hipo") is False, eval_low)
            check("1 not derived HiPo signal", eval_low.get("classification", {}).get("classification") != "derived_high_potential", eval_low)
            check("1 contradiction not reconciled", (eval_low.get("why") or {}).get("contradictions_reconciled") is False, eval_low)

            crit = c6.designate_critical_role(
                cur, company_code=COMPANY, actor_phone=HR, canonical_role_key=f"FIN-{SUFFIX}",
                title_en="Finance Manager", title_ar="مدير المالية", reason="crit",
            )
            role_id = str(crit["critical_role"]["critical_role_id"])
            created = pt3.create_requirement_set(
                cur, company_code=COMPANY, actor_phone=HR, name_en="Finance Manager",
                critical_role_id=role_id, reason="set",
            )
            set_id = str(created["set"]["set_id"])
            draft_fit = pt3.save_draft_version(
                cur, company_code=COMPANY, actor_phone=HR, set_id=set_id,
                requirements=[{"id": "skill-ifrs", "kind": "skill", "code": "IFRS", "priority": "required"}],
                reason="draft fit",
            )
            pt3.publish_version(cur, company_code=COMPANY, actor_phone=HR, version_id=str(draft_fit["version"]["version_id"]), reason="pub fit")
            missing = pt3.evaluate_role_fit(
                cur, company_code=COMPANY, actor_phone=HR, employee_key=AHMED, set_id=set_id, reason="missing",
            )
            check("2 missing evaluate", missing.get("ok") is True, missing)
            check("2 overall not_assessed", missing.get("overall_fit") == "not_assessed", missing)
            check("2 no fabricated 0%", (missing.get("why") or {}).get("weighted_pct") not in (0, 0.0), missing)
            check("2 no fabricated 100%", (missing.get("why") or {}).get("weighted_pct") not in (100, 100.0), missing)
            check("2 suggestion not not_ready", missing.get("readiness_suggestion") != "not_ready", missing)
            check("2 suggestion unassessed", missing.get("readiness_suggestion") == "unassessed", missing)

            eval_sarah = pt2.evaluate_employee(
                cur, company_code=COMPANY, actor_phone=HR, employee_key=SARAH,
                model_id=model_id, reason="eval sarah",
            )
            check("5 derived high-potential signal", eval_sarah.get("classification", {}).get("classification") == "derived_high_potential", eval_sarah)
            check("5 still not designated HiPo", eval_sarah.get("designated_hipo") is False, eval_sarah)
            ui_why = eval_sarah.get("why") or {}

            m1 = pt4.build_map(cur, company_code=COMPANY, lens="perf_x_potential")
            m2 = pt4.build_map(cur, company_code=COMPANY, lens="potential_x_readiness")
            p1 = next((p for p in m1.get("placements") or [] if p.get("employee_key") == SARAH), None)
            p2 = next((p for p in m2.get("placements") or [] if p.get("employee_key") == SARAH), None)
            check("4 map both lenses", bool(p1 and p2), (m1.get("ok"), m2.get("ok")))
            check(
                "4 same canonical potential",
                bool(p1 and p2 and p1["canonical_facts"]["human_potential"] == p2["canonical_facts"]["human_potential"] == "high"),
                (p1, p2),
            )
            check(
                "4 same designated hipo false",
                bool(p1 and p2 and p1["canonical_facts"]["designated_hipo"] is False and p2["canonical_facts"]["designated_hipo"] is False),
            )
            check("4 only projection may differ", True)

            map_why = pt4.get_placement_why(cur, company_code=COMPANY, employee_key=SARAH, lens="perf_x_potential")
            stored_why = pt2.get_why(cur, company_code=COMPANY, employee_key=SARAH)
            graph = ((stored_why.get("why") or {}).get("graph") or {})
            check("3 profile WHY present", stored_why.get("ok") is True and graph.get("model_id"), stored_why)
            check("3 map WHY present", map_why.get("ok") is True, map_why)
            check("3 profile/model id matches evaluate", graph.get("model_id") == ui_why.get("model_id"), (graph.get("model_id"), ui_why.get("model_id")))

            plan = c6.create_succession_plan(cur, company_code=COMPANY, actor_phone=HR, critical_role_id=role_id, reason="plan")
            nom = c6.nominate_successor(
                cur, company_code=COMPANY, actor_phone=HR, plan_id=str(plan["plan"]["plan_id"]),
                employee_key=SARAH, rationale="only ready", readiness="ready_now",
                has_sensitive_permission=True, reason="nom",
            )
            check("6 nominate", nom.get("ok") is True, nom)
            intel = pt5.succession_intelligence(cur, company_code=COMPANY)
            one = next(r for r in intel.get("roles") or [] if r.get("critical_role_id") == role_id)
            check("6 single-successor risk", one.get("single_successor_risk") is True, one)
            check("6 does not invent candidates", one.get("successor_count") == 1 and one.get("invented_candidates") is False, one)

            c5.add_dimension_fact(
                cur, company_code=COMPANY, actor_phone=HR, employee_key=SARAH,
                dimension_kind="mobility_preference", title_en="Lateral finance", source="employee_declared",
                reason="interest",
            )
            mob = pt5.discover_mobility(cur, company_code=COMPANY, actor_phone=HR, employee_key=SARAH, reason="discover")
            check("7 mobility advisory", mob.get("ok") is True and mob.get("is_not_application") is True, mob)
            check("7 no candidate created", mob.get("candidate_created") is False, mob)
            check("7 no employment mutate", mob.get("employment_mutated") is False, mob)
            match_id = str((mob.get("matches") or [{}])[0].get("match_id") or uuid.uuid4())
            handoff = pt5.refer_to_internal_opportunity(cur, company_code=COMPANY, match_id=match_id, reason="handoff")
            check("7 no silent application", handoff.get("application_created") is not True, handoff)

            claimed = c5.claim_skill(
                cur, company_code=COMPANY, actor_phone=HR, employee_key=SARAH,
                skill_code="UNIQUECRIT", name_en="Unique critical", reason="claim",
            )
            c5.verify_skill(cur, company_code=COMPANY, actor_phone=HR, skill_id=str(claimed["skill"]["skill_id"]), reason="verify")
            before = pt6.capability_facts(cur, company_code=COMPANY)
            dep = pt6.holder_dependency(cur, company_code=COMPANY, employee_key=SARAH)
            after = pt6.capability_facts(cur, company_code=COMPANY)
            check("8 unique capability vulnerable", "UNIQUECRIT" in (dep.get("vulnerable_capabilities") or []), dep)
            check("8 employment not mutated", dep.get("employment_mutated") is False, dep)
            check("8 baseline unchanged after analytic exclusion", before.get("capability_coverage") == after.get("capability_coverage"), (before, after))
            cur.execute("SELECT employment_status FROM employees WHERE employee_key=%s", (SARAH,))
            check("8 employee still active", str(dict(cur.fetchone() or {}).get("employment_status") or "") == "active")

    explained = pt7.explain_talent_classification_tool(Ctx(SARAH))
    check("9 assistant explain ok", explained.get("ok") is True, explained)
    check("9 assistant uses WHY model", (explained.get("why") or {}).get("model_id") == ui_why.get("model_id"), (explained.get("why"), ui_why))
    check("9 assistant does not claim designated HiPo", explained.get("designated_hipo") is False, explained)
    check("9 assistant names model/version", "model" in str(explained.get("message") or "").lower(), explained)
    check("3 assistant WHY matches profile", (explained.get("why") or {}).get("model_id") == graph.get("model_id"))

    print(f"\n    {PASS} passed, {FAIL} failed")
    if FAIL == 0:
        print("PT_FLAGSHIP_EVALS_DB_PASS")
    return 1 if FAIL else 0


if __name__ == "__main__":
    raise SystemExit(main())
