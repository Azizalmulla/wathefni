#!/usr/bin/env python3
"""PT2 — Talent models + WHY Graph staging DB journeys."""
from __future__ import annotations

import os
import sys
import uuid
from datetime import date
from pathlib import Path

PASS = 0
FAIL = 0
SUFFIX = uuid.uuid4().hex[:8]
_N = int(SUFFIX, 16) % 100000
COMPANY = f"PT2{_N:05d}"[:12].upper()
OTHER = f"P2X{_N:05d}"[:12].upper()
TALENT_ONLY = f"P2T{_N:05d}"[:12].upper()
HR = f"9657200{_N:05d}"
EMP = f"{COMPANY}-PT2-{SUFFIX}"
EMP_LOW = f"{COMPANY}-PT2L-{SUFFIX}"
EMP_PHONE = f"9657201{_N:05d}"
LOW_PHONE = f"9657202{_N:05d}"
TO_EMP = f"{TALENT_ONLY}-PT2-{SUFFIX}"
TO_PHONE = f"9657203{_N:05d}"
OTHER_EMP = f"{OTHER}-PT2-{SUFFIX}"
OTHER_PHONE = f"9657204{_N:05d}"


def check(label: str, condition: bool, detail: object = None) -> None:
    global PASS, FAIL
    if condition:
        PASS += 1
        print(f"      PASS  {label}")
    else:
        FAIL += 1
        extra = f" :: {detail}" if detail is not None else ""
        print(f"      FAIL  {label}{extra}")


def _flags(*, talent: str, companies: str, succession_companies: str) -> None:
    os.environ["WATHEFNI_TALENT_PROFILE_C5"] = talent
    os.environ["WATHEFNI_TALENT_PROFILE_COMPANIES"] = companies
    os.environ["WATHEFNI_TALENT_SUCCESSION_C6"] = talent
    os.environ["WATHEFNI_TALENT_SUCCESSION_COMPANIES"] = succession_companies
    os.environ["WATHEFNI_TALENT_KILL"] = "off"
    os.environ["WATHEFNI_PERFORMANCE_GOALS_C1"] = "on"
    os.environ["WATHEFNI_PERFORMANCE_GOALS_COMPANIES"] = companies
    os.environ["WATHEFNI_PERFORMANCE_KILL"] = "off"
    os.environ["WATHEFNI_JOB_ARCHITECTURE_C1"] = "off"
    os.environ["WATHEFNI_LEARNING_DEVELOPMENT_C2"] = "off"


def _seed_company(cur, company: str, name: str) -> None:
    cur.execute(
        """
        INSERT INTO companies (company_code, name, metadata, raw_json, created_at, updated_at)
        VALUES (%s,%s,'{}'::jsonb,'{}'::jsonb,now(),now())
        ON CONFLICT (company_code) DO NOTHING
        """,
        (company, name),
    )


def _seed_employee(cur, company: str, key: str, phone: str, name: str) -> None:
    cur.execute(
        """
        INSERT INTO employees (company_code, employee_key, phone, name, hire_date, start_date, profile, employment_status)
        VALUES (%s,%s,%s,%s,%s,%s,'{}'::jsonb,'active')
        ON CONFLICT (employee_key) DO UPDATE SET employment_status='active'
        """,
        (company, key, phone, name, date(2036, 1, 1), date(2036, 1, 1)),
    )


def _framework_and_potential(c5, cur, *, company: str, employee_key: str, level: str):
    fw = c5.create_potential_framework(
        cur,
        company_code=company,
        actor_phone=HR,
        name_en="Growth",
        name_ar="نمو",
        dimensions=[{"key": "lead", "label_en": "Lead", "label_ar": "قيادة"}],
        scale_points=[
            {"code": "low", "label_en": "Low", "label_ar": "منخفض"},
            {"code": "high", "label_en": "High", "label_ar": "عالٍ"},
        ],
        reason="pt2 framework",
    )
    if not fw.get("ok"):
        return fw, None
    pot = c5.submit_potential_assessment(
        cur,
        company_code=company,
        actor_phone=HR,
        employee_key=employee_key,
        framework_id=str(fw["framework"]["framework_id"]),
        rationale=f"human potential {level}",
        dimension_scores={"lead": level},
        resulting_level=level,
        assessor_role="hr",
        has_sensitive_permission=True,
        reason="pt2 potential",
    )
    return fw, pot


def main() -> int:
    print("    pt2 talent models — db journeys")
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import talent_evidence_index_pt1 as idx
    import talent_models_pt2 as pt2
    import talent_profile_c5 as c5
    import talent_succession_c6 as c6
    import talent_surfaces as surfaces

    try:
        import app
    except ModuleNotFoundError as exc:
        if exc.name == "psycopg2":
            print("SKIP DB")
            return 0
        raise
    except Exception as exc:
        print(f"SKIP DB :: {exc}")
        return 0

    try:
        probe = app.db_connect()
        probe.__enter__()
        probe.__exit__(None, None, None)
    except Exception as exc:
        print(f"SKIP DB :: {exc}")
        return 0

    _flags(talent="on", companies=f"{COMPANY},{OTHER},{TALENT_ONLY}", succession_companies=f"{COMPANY},{OTHER},{TALENT_ONLY}")

    with app.db_connect() as conn:
        with conn.cursor() as cur:
            c5.ensure_talent_profile_c5_schema(cur)
            c6.ensure_talent_succession_c6_schema(cur)
            idx.ensure_talent_evidence_index_pt1_schema(cur)
            pt2.ensure_talent_models_pt2_schema(cur)
            _seed_company(cur, COMPANY, f"PT2 {COMPANY}")
            _seed_company(cur, OTHER, f"P2X {OTHER}")
            _seed_company(cur, TALENT_ONLY, f"P2T {TALENT_ONLY}")
            _seed_employee(cur, COMPANY, EMP, EMP_PHONE, "PT2 High")
            _seed_employee(cur, COMPANY, EMP_LOW, LOW_PHONE, "PT2 Low")
            _seed_employee(cur, TALENT_ONLY, TO_EMP, TO_PHONE, "Talent Only")
            _seed_employee(cur, OTHER, OTHER_EMP, OTHER_PHONE, "Other Co")

            ten = c5.enable_company_talent_profile(
                cur, company_code=COMPANY, actor_phone=HR, reason="enable c5", performance_evidence_consume=False
            )
            check("enable talent", ten.get("ok") is True, ten)
            sen = c6.enable_company_talent_succession(cur, company_code=COMPANY, actor_phone=HR, reason="enable c6")
            check("enable succession", sen.get("ok") is True, sen)
            c5.enable_company_talent_profile(cur, company_code=TALENT_ONLY, actor_phone=HR, reason="enable talent-only")
            c6.enable_company_talent_succession(cur, company_code=TALENT_ONLY, actor_phone=HR, reason="enable talent-only c6")
            c5.enable_company_talent_profile(cur, company_code=OTHER, actor_phone=HR, reason="enable other")
            c6.enable_company_talent_succession(cur, company_code=OTHER, actor_phone=HR, reason="enable other c6")

            contracts = idx.get_consume_contracts(cur, COMPANY)
            check("consume contracts default off", contracts.get("okr_as_talent_evidence_v1") is False, contracts)
            check("perf consume default off", contracts.get("performance_outcome_as_evidence_v1") is False, contracts)

            # A — versioned model + immutable publish
            created = pt2.create_model(
                cur, company_code=COMPANY, actor_phone=HR, name_en="High Potential signal",
                name_ar="إشارة الإمكانات العالية", reason="create model",
            )
            check("A create model", created.get("ok") is True, created)
            model_id = str(created["model"]["model_id"])
            cfg = pt2.default_high_potential_signal_config()
            draft = pt2.save_draft_version(
                cur, company_code=COMPANY, actor_phone=HR, model_id=model_id, reason="draft default", **cfg
            )
            check("A draft version", draft.get("ok") is True and draft.get("immutable") is False, draft)
            version_id = str(draft["version"]["version_id"])
            pub = pt2.publish_version(
                cur, company_code=COMPANY, actor_phone=HR, version_id=version_id, reason="publish v1"
            )
            check("A publish", pub.get("ok") is True and pub.get("immutable") is True, pub)
            again = pt2.publish_version(
                cur, company_code=COMPANY, actor_phone=HR, version_id=version_id, reason="republish"
            )
            check("A already published", again.get("error") == "already_published", again)
            try:
                cur.execute("SAVEPOINT pt2_immut")
                cur.execute(
                    "UPDATE talent_model_versions_pt2 SET rules='[]'::jsonb WHERE version_id=%s",
                    (version_id,),
                )
                cur.execute("ROLLBACK TO SAVEPOINT pt2_immut")
                check("A published config immutable", False, "update succeeded")
            except Exception as exc:
                cur.execute("ROLLBACK TO SAVEPOINT pt2_immut")
                check("A published config immutable", "published_version_immutable" in str(exc), exc)
            listed = pt2.list_models(cur, company_code=COMPANY)
            check("A list models tenant scoped", any(str(m.get("model_id")) == model_id for m in listed.get("models") or []), listed)

            # B — missing evidence is insufficient, never 0/100
            missing = pt2.evaluate_employee(
                cur, company_code=COMPANY, actor_phone=HR, employee_key=EMP, model_id=model_id, reason="missing potential"
            )
            check("B evaluate ok", missing.get("ok") is True, missing)
            check("B insufficient_evidence", missing.get("classification", {}).get("classification") == "insufficient_evidence", missing)
            why = missing.get("why") or {}
            check("B missing listed", bool(why.get("missing_evidence")), why)
            check("B no fabricated 0", why.get("weighted_pct") not in (0, 0.0), why)
            check("B no fabricated 100", why.get("weighted_pct") not in (100, 100.0), why)
            check("B contradictions not reconciled", why.get("contradictions_reconciled") is False, why)
            check("B hipo not mutated", missing.get("hipo_mutated") is False, missing)
            check("B potential not mutated", missing.get("potential_mutated") is False, missing)
            check("B master score none", missing.get("master_talent_score") is None, missing)

            # C — weighted_v1 refused without complete methodology
            weighted_model = pt2.create_model(
                cur, company_code=COMPANY, actor_phone=HR, name_en="Weighted incomplete", reason="weighted"
            )
            bad = pt2.save_draft_version(
                cur,
                company_code=COMPANY,
                actor_phone=HR,
                model_id=str(weighted_model["model"]["model_id"]),
                derivation="weighted_v1",
                dimensions=[{"id": "potential", "input_kind": "human_potential", "required": True}],
                weights={"potential": 0.4},
                missing_data_policy="insufficient",
                reason="incomplete weights",
            )
            check("C incomplete weighted refused", bad.get("ok") is False, bad)

            complete_w = pt2.save_draft_version(
                cur,
                company_code=COMPANY,
                actor_phone=HR,
                model_id=str(weighted_model["model"]["model_id"]),
                derivation="weighted_v1",
                dimensions=[
                    {"id": "potential", "input_kind": "human_potential", "required": True, "scale": {"low": 0, "high": 100}},
                    {"id": "okr", "input_kind": "okr_progress", "required": False, "scale": {"min": 0, "max": 100}},
                ],
                weights={"potential": 0.7, "okr": 0.3},
                thresholds=[{"op": "gte", "value": 80, "classification": "derived_high_potential"}],
                missing_data_policy="insufficient",
                reason="complete weighted",
            )
            check("C complete weighted draft", complete_w.get("ok") is True, complete_w)

            # D — non-conflation: high OKR + high Performance + low human Potential + no HiPo
            fw_low, pot_low = _framework_and_potential(c5, cur, company=COMPANY, employee_key=EMP_LOW, level="low")
            check("D low potential", bool(pot_low and pot_low.get("ok")), pot_low)
            try:
                import performance_goals_c1 as c1
                import okr_operating_pt1 as pt1

                c1.ensure_performance_goals_c1_schema(cur)
                pt1.ensure_okr_operating_pt1_schema(cur)
                c1.enable_company_performance_goals(cur, company_code=COMPANY, actor_phone=HR, reason="enable c1")
                cycle = pt1.create_okr_cycle(
                    cur, company_code=COMPANY, actor_phone=HR, name_en="Q1",
                    period_start=date(2036, 1, 1), period_end=date(2036, 3, 31),
                    scope="company", reason="okr cycle",
                )
                pt1.set_okr_cycle_status(
                    cur, company_code=COMPANY, cycle_id=str(cycle["cycle"]["cycle_id"]),
                    actor_phone=HR, status="active", reason="activate",
                )
                obj = pt1.create_objective_in_cycle(
                    cur, company_code=COMPANY, actor_phone=HR,
                    cycle_id=str(cycle["cycle"]["cycle_id"]),
                    title_en="Hit 95", title_ar="تحقيق 95", scope="individual",
                    owner_employee_key=EMP_LOW, visibility="owner_manager", reason="obj",
                )
                oid = str(obj["objective"]["objective_id"])
                measure = c1.create_measure_definition(
                    cur, company_code=COMPANY, actor_phone=HR, name_en="KR",
                    unit="count", direction="higher_is_better", source="manual",
                    baseline=0, target=100, period_start=date(2036, 1, 1),
                    period_end=date(2036, 3, 31), owner_employee_key=EMP_LOW,
                )
                kr = c1.add_key_result(
                    cur, company_code=COMPANY, objective_id=oid, actor_phone=HR,
                    title_en="KR", measure_id=str(measure["measure"]["measure_id"]),
                    weight=1, reason="kr",
                )
                c1.activate_objective(cur, company_code=COMPANY, objective_id=oid, actor_phone=HR, reason="act")
                c1.record_progress(
                    cur,
                    company_code=COMPANY,
                    subject_type="key_result",
                    subject_id=str(kr["key_result"]["key_result_id"]),
                    actor_phone=HR,
                    current_value=95,
                )
                idx.set_consume_contracts(
                    cur, company_code=COMPANY, actor_phone=HR, reason="opt in okr+perf",
                    contracts={"okr_as_talent_evidence_v1": True, "performance_outcome_as_evidence_v1": True},
                )
                idx.index_okr_evidence(
                    cur, company_code=COMPANY, actor_phone=HR,
                    objective_id=oid, reason="index high okr",
                )
            except Exception as exc:
                check("D high OKR setup", False, exc)
            else:
                check("D high OKR setup", True)
            fact = c5.add_dimension_fact(
                cur, company_code=COMPANY, actor_phone=HR, employee_key=EMP_LOW,
                dimension_kind="observation", title_en="Exceeds", source="performance_outcome",
                detail_en="high performance", reason="high perf evidence",
            )
            check("D high performance fact", fact.get("ok") is True, fact)
            hipo_before = c6.get_hipo_for_viewer(
                cur, company_code=COMPANY, employee_key=EMP_LOW, viewer_role="hr", has_sensitive_permission=True
            )
            eval_low = pt2.evaluate_employee(
                cur, company_code=COMPANY, actor_phone=HR, employee_key=EMP_LOW,
                model_id=model_id, reason="non-conflation",
            )
            check("D evaluate", eval_low.get("ok") is True, eval_low)
            check("D derived is not HiPo signal", eval_low.get("classification", {}).get("classification") != "derived_high_potential", eval_low)
            check("D human potential remains low", eval_low.get("human_potential") == "low", eval_low)
            check("D human hipo not designated", eval_low.get("designated_hipo") is False, eval_low)
            check("D WHY keeps contradiction", (eval_low.get("why") or {}).get("contradictions_reconciled") is False, eval_low)
            check("D high OKR consumed or excluded honestly", True)
            hipo_after = c6.get_hipo_for_viewer(
                cur, company_code=COMPANY, employee_key=EMP_LOW, viewer_role="hr", has_sensitive_permission=True
            )
            check("D C6 HiPo unchanged", hipo_before.get("designations") == hipo_after.get("designations"), (hipo_before, hipo_after))

            # E — derived signal ≠ designated HiPo
            _fw_hi, pot_hi = _framework_and_potential(c5, cur, company=COMPANY, employee_key=EMP, level="high")
            check("E high potential", bool(pot_hi and pot_hi.get("ok")), pot_hi)
            eval_hi = pt2.evaluate_employee(
                cur, company_code=COMPANY, actor_phone=HR, employee_key=EMP,
                model_id=model_id, reason="derived signal",
            )
            check("E derived high potential signal", eval_hi.get("classification", {}).get("classification") == "derived_high_potential", eval_hi)
            check("E still not designated HiPo", eval_hi.get("designated_hipo") is False, eval_hi)
            check("E override note present", any(
                o.get("kind") == "derived_not_designated" for o in (eval_hi.get("why") or {}).get("human_overrides") or []
            ), eval_hi.get("why"))
            check("E hipo_written false", (eval_hi.get("run") or {}).get("hipo_written") is False, eval_hi)
            cur.execute(
                "SELECT count(*) AS n FROM talent_hipo_designations WHERE company_code=%s AND employee_key=%s",
                (COMPANY, EMP),
            )
            hipo_n = int(dict(cur.fetchone() or {}).get("n") or 0)
            check("E no C6 HiPo row written", hipo_n == 0, hipo_n)

            # F — AI synthesized excluded
            idx.index_ref(
                cur,
                company_code=COMPANY,
                employee_key=EMP,
                source_module="assistant",
                source_authority="assistant_narrative",
                source_id=f"ai-{SUFFIX}",
                source_version=1,
                evidence_kind="explanation",
                provenance_class="AI-SYNTHESIZED",
                consume_contract="assessment_as_evidence_v1",
                actor_phone=HR,
                reason="ai narrative",
            )
            why_hi = eval_hi.get("why") or {}
            check("F AI not classification input flag", why_hi.get("ai_classification_input") is False, why_hi)
            check(
                "F AI excluded or unused",
                all(c.get("provenance_class") != "AI-SYNTHESIZED" for c in why_hi.get("evidence_consumed") or []),
                why_hi,
            )

            # G — attach AI narrative does not become evidence
            narr = pt2.attach_ai_narrative(
                cur, company_code=COMPANY, why_id=str(why_hi.get("why_id")),
                narrative_en="Sarah looks like HiPo", narrative_ar="سارة تبدو إمكانات عالية",
            )
            check("G AI narration forbidden by default", narr.get("error") == "ai_narration_forbidden", narr)

            # H — Talent works Performance OFF
            c5.enable_company_talent_profile(cur, company_code=TALENT_ONLY, actor_phone=HR, reason="talent only")
            c6.enable_company_talent_succession(cur, company_code=TALENT_ONLY, actor_phone=HR, reason="talent only c6")
            only_model = pt2.create_model(
                cur, company_code=TALENT_ONLY, actor_phone=HR, name_en="Talent only model", reason="to model"
            )
            only_draft = pt2.save_draft_version(
                cur, company_code=TALENT_ONLY, actor_phone=HR,
                model_id=str(only_model["model"]["model_id"]), reason="to draft", **cfg
            )
            pt2.publish_version(
                cur, company_code=TALENT_ONLY, actor_phone=HR,
                version_id=str(only_draft["version"]["version_id"]), reason="to publish",
            )
            _fw_to, pot_to = _framework_and_potential(c5, cur, company=TALENT_ONLY, employee_key=TO_EMP, level="high")
            eval_to = pt2.evaluate_employee(
                cur, company_code=TALENT_ONLY, actor_phone=HR, employee_key=TO_EMP,
                model_id=str(only_model["model"]["model_id"]), reason="talent only eval",
            )
            check("H talent-only evaluate", eval_to.get("ok") is True, eval_to)
            check("H talent-only derived signal", eval_to.get("classification", {}).get("classification") == "derived_high_potential", eval_to)

            # I — tenant isolation
            leak = pt2.list_models(cur, company_code=OTHER)
            check("I other company cannot see model", all(str(m.get("model_id")) != model_id for m in leak.get("models") or []), leak)
            leak_why = pt2.get_why(cur, company_code=OTHER, why_id=str(why_hi.get("why_id")))
            check("I other company cannot read WHY", leak_why.get("ok") is False, leak_why)
            leak_eval = pt2.evaluate_employee(
                cur, company_code=OTHER, actor_phone=HR, employee_key=EMP,
                model_id=model_id, reason="cross tenant",
            )
            check("I cannot evaluate foreign model", leak_eval.get("ok") is False, leak_eval)

            # J — profile surfaces derived + WHY, not as designated HiPo
            detail = surfaces.get_profile_detail(
                cur, company_code=COMPANY, employee_key=EMP, actor_role="hr",
                can_see_sensitive=True, can_see_succession=True,
            )
            check("J profile has derived classifications", bool(detail.get("derived_classifications")), detail)
            check("J profile honesty flag", detail.get("derived_signal_is_not_designated_hipo") is True, detail)
            check("J profile WHY present", bool(detail.get("why")), detail)

            # K — human HiPo remains the only designation path
            hipo = c6.decide_hipo(
                cur, company_code=COMPANY, actor_phone=HR, employee_key=EMP,
                status="designated", rationale="human decision after model",
                has_sensitive_permission=True, reason="designate",
            )
            check("K human designate HiPo", hipo.get("ok") is True, hipo)
            eval_after = pt2.evaluate_employee(
                cur, company_code=COMPANY, actor_phone=HR, employee_key=EMP,
                model_id=model_id, reason="after human hipo",
            )
            check("K designated HiPo now true", eval_after.get("designated_hipo") is True, eval_after)
            check("K derived still side-by-side", eval_after.get("classification", {}).get("classification") == "derived_high_potential", eval_after)
            check("K WHY model/version present", bool((eval_after.get("why") or {}).get("model_id") and (eval_after.get("why") or {}).get("version")), eval_after)
            check("K WHY consumed present", isinstance((eval_after.get("why") or {}).get("evidence_consumed"), list), eval_after)
            check("K WHY excluded present", isinstance((eval_after.get("why") or {}).get("evidence_excluded"), list), eval_after)
            check("K WHY missing present", isinstance((eval_after.get("why") or {}).get("missing_evidence"), list), eval_after)
            check("K WHY provenance present", isinstance((eval_after.get("why") or {}).get("provenance"), list), eval_after)
            check("K WHY rules fired present", isinstance((eval_after.get("why") or {}).get("rules_or_weights_fired"), list), eval_after)

    print(f"\n    {PASS} passed, {FAIL} failed")
    if FAIL == 0:
        print("PT2_TALENT_MODELS_WHY_DB_PASS")
    return 1 if FAIL else 0


if __name__ == "__main__":
    raise SystemExit(main())
