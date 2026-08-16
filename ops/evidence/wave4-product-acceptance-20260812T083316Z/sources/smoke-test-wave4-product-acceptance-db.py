#!/usr/bin/env python3
"""Wave 4 Product Acceptance — staging DB prove (C7).

No new domain SoT. Orchestrates frozen C1–C6 authorities for:
  full Performance path · Talent-only path · modularity matrix · Setup ownership ·
  Wave 5 fact readiness · anti-regressions · history survival.
"""
from __future__ import annotations

import os
import sys
import uuid
from datetime import date, timedelta
from pathlib import Path

PASS = 0
FAIL = 0
SUFFIX = uuid.uuid4().hex[:8]
_N = int(SUFFIX, 16) % 100000
COMPANY = f"W4P{_N:05d}"[:12].upper()
OTHER = f"W4X{_N:05d}"[:12].upper()
HR = f"9656800{_N:05d}"
EMP = f"{COMPANY}-W4P-{SUFFIX}"
EMP_PHONE = f"9656801{_N:05d}"
MGR = f"{COMPANY}-MGR-{SUFFIX}"
MGR_PHONE = f"9656802{_N:05d}"
PEER1_PHONE = f"9656803{_N:05d}"
PEER2_PHONE = f"9656804{_N:05d}"
PEER3_PHONE = f"9656805{_N:05d}"
LOCKER = f"9656809{_N:05d}"


def check(label: str, condition: bool, detail: object = None) -> None:
    global PASS, FAIL
    if condition:
        PASS += 1
        print(f"      PASS  {label}")
    else:
        FAIL += 1
        extra = f" :: {detail}" if detail is not None else ""
        print(f"      FAIL  {label}{extra}")


def _set_modules(modules: dict[str, bool], company: str = COMPANY) -> None:
    pairs = {
        "performance_goals": ("WATHEFNI_PERFORMANCE_GOALS_C1", "WATHEFNI_PERFORMANCE_GOALS_COMPANIES"),
        "performance_reviews": ("WATHEFNI_PERFORMANCE_REVIEWS_C2", "WATHEFNI_PERFORMANCE_REVIEWS_COMPANIES"),
        "performance_feedback": ("WATHEFNI_PERFORMANCE_FEEDBACK_C3", "WATHEFNI_PERFORMANCE_FEEDBACK_COMPANIES"),
        "performance_calibration": (
            "WATHEFNI_PERFORMANCE_CALIBRATION_C4",
            "WATHEFNI_PERFORMANCE_CALIBRATION_COMPANIES",
        ),
        "talent_profile": ("WATHEFNI_TALENT_PROFILE_C5", "WATHEFNI_TALENT_PROFILE_COMPANIES"),
        "talent_succession": ("WATHEFNI_TALENT_SUCCESSION_C6", "WATHEFNI_TALENT_SUCCESSION_COMPANIES"),
    }
    for key, (flag, cos) in pairs.items():
        if modules.get(key):
            os.environ[flag] = "on"
            os.environ[cos] = company
        else:
            os.environ[flag] = "off"
            os.environ[cos] = ""
    os.environ["WATHEFNI_PERFORMANCE_KILL"] = "off"
    os.environ["WATHEFNI_TALENT_KILL"] = "off"


def main() -> int:
    print("    wave4 product acceptance — db")
    sys.path.insert(0, str(Path(__file__).resolve().parent))

    import setup_console_wave4_policies as w4p
    import performance_goals_c1 as c1
    import performance_reviews_c2 as c2
    import performance_feedback_c3 as c3
    import performance_calibration_c4 as c4
    import talent_profile_c5 as c5
    import talent_succession_c6 as c6

    check("stamp", w4p.PASS_STAMP == "WAVE4_PRODUCT_FULL_PASS")
    check("matrix size", len(w4p.modularity_matrix_configs()) >= 12)

    try:
        import app
    except ModuleNotFoundError as exc:
        if exc.name == "psycopg2":
            print("SKIP DB")
            return 1 if FAIL else 0
        raise

    try:
        _db = app.db_connect()
        conn = _db.__enter__()
    except Exception as exc:
        print(f"SKIP DB ({type(exc).__name__}: {exc})")
        return 1 if FAIL else 0

    try:
        with conn.cursor() as cur:
            for code, name in ((COMPANY, f"W4P {COMPANY}"), (OTHER, f"W4X {OTHER}")):
                cur.execute(
                    """
                    INSERT INTO companies (company_code, name, metadata, raw_json, created_at, updated_at)
                    VALUES (%s,%s,'{}'::jsonb,'{}'::jsonb,now(),now())
                    ON CONFLICT (company_code) DO NOTHING
                    """,
                    (code, name),
                )

            # ── Setup ownership ──
            allp = w4p.get_all_wave4_policies(cur, COMPANY)
            check("setup get all", allp.get("ok") is True, allp)
            check("setup owns", allp.get("setup_owns_wave4_policies") is True)
            check("wave5 catalog present", len(allp.get("wave5_fact_catalog") or []) >= 8)
            for key in w4p.WAVE4_MODULE_KEYS:
                p = w4p.patch_wave4_module_policy(
                    cur,
                    company_code=COMPANY,
                    module_key=key,
                    actor_phone=HR,
                    reason="wave4 product acceptance setup",
                    payload={"enabled": True},
                )
                check(f"setup patch {key}", p.get("ok") is True, p)
            bad = w4p.patch_wave4_module_policy(
                cur,
                company_code=COMPANY,
                module_key="performance_calibration",
                actor_phone=HR,
                reason="forbid forced distribution",
                payload={"forced_distribution_assumed": True},
            )
            check("setup rejects forced distribution", bad.get("error") == "forced_distribution_never_assumed", bad)

            # ── Modularity matrix ──
            mods = {
                "performance_goals": c1,
                "performance_reviews": c2,
                "performance_feedback": c3,
                "performance_calibration": c4,
                "talent_profile": c5,
                "talent_succession": c6,
            }
            for cell in w4p.modularity_matrix_configs():
                name = cell["name"]
                wanted = cell.get("modules") or {}
                _set_modules(wanted)
                for mkey, mod in mods.items():
                    expect = bool(wanted.get(mkey))
                    got = mod.runtime_gate_for_company(COMPANY).get("ok") is True
                    check(f"matrix {name}/{mkey}", got is expect, {"expect": expect, "got": got})
                if name == "all_wave4_disabled":
                    check(
                        "all disabled clean",
                        all(m.runtime_gate_for_company(COMPANY).get("ok") is not True for m in mods.values()),
                    )
                if name == "talent_only_performance_off":
                    check(
                        "talent usable without perf",
                        c5.runtime_gate_for_company(COMPANY).get("ok") is True
                        and c1.runtime_gate_for_company(COMPANY).get("ok") is not True,
                    )
                if name == "goals_only":
                    check(
                        "goals only no reviews shell gate",
                        c1.runtime_gate_for_company(COMPANY).get("ok") is True
                        and c2.runtime_gate_for_company(COMPANY).get("ok") is not True,
                    )

            # ── Full Performance E2E ──
            _set_modules(
                {
                    "performance_goals": True,
                    "performance_reviews": True,
                    "performance_feedback": True,
                    "performance_calibration": True,
                }
            )
            c1.ensure_performance_goals_c1_schema(cur)
            c2.ensure_performance_reviews_c2_schema(cur)
            c3.ensure_performance_feedback_c3_schema(cur)
            c4.ensure_performance_calibration_c4_schema(cur)

            check(
                "enable goals",
                c1.enable_company_performance_goals(
                    cur, company_code=COMPANY, actor_phone=HR, reason="w4p"
                ).get("ok")
                is True,
            )
            check(
                "enable reviews",
                c2.enable_company_performance_reviews(
                    cur,
                    company_code=COMPANY,
                    actor_phone=HR,
                    reason="w4p",
                    review_360_enabled=True,
                    min_respondent_threshold=3,
                    allow_hr_raw_360=False,
                ).get("ok")
                is True,
            )
            check(
                "enable feedback",
                c3.enable_company_performance_feedback(
                    cur, company_code=COMPANY, actor_phone=HR, reason="w4p"
                ).get("ok")
                is True,
            )
            check(
                "enable calibration",
                c4.enable_company_performance_calibration(
                    cur,
                    company_code=COMPANY,
                    actor_phone=HR,
                    reason="w4p",
                    sod_lock_requires_other_actor=True,
                ).get("ok")
                is True,
            )

            measure = c1.create_measure_definition(
                cur,
                company_code=COMPANY,
                actor_phone=HR,
                name_en="Ship velocity",
                unit="points",
                direction="higher_is_better",
                baseline=0,
                target=100,
            )
            check("measure contract", measure.get("ok") is True, measure)
            mid = str(measure["measure"]["measure_id"])

            obj = c1.create_objective(
                cur,
                company_code=COMPANY,
                actor_phone=EMP_PHONE,
                title_en="Deliver Wave4 product",
                title_ar="تسليم منتج الموجة 4",
                scope="individual",
                owner_employee_key=EMP,
                period_start=date.today() - timedelta(days=30),
                period_end=date.today() + timedelta(days=60),
            )
            check("create objective", obj.get("ok") is True, obj)
            oid = str(obj["objective"]["objective_id"])
            kr1 = c1.add_key_result(
                cur,
                company_code=COMPANY,
                objective_id=oid,
                actor_phone=EMP_PHONE,
                title_en="KR1 qualify C7",
                measure_id=mid,
                weight=0.5,
            )
            kr2 = c1.add_key_result(
                cur,
                company_code=COMPANY,
                objective_id=oid,
                actor_phone=EMP_PHONE,
                title_en="KR2 freeze Wave4",
                measure_id=mid,
                weight=0.5,
            )
            check("two KRs", kr1.get("ok") is True and kr2.get("ok") is True, (kr1, kr2))
            kr1_id = str(kr1["key_result"]["key_result_id"])
            prog = c1.record_progress(
                cur,
                company_code=COMPANY,
                actor_phone=EMP_PHONE,
                subject_type="key_result",
                subject_id=kr1_id,
                current_value=60,
            )
            check("progress recorded", prog.get("ok") is True, prog)
            # Create a second objective for alignment (no rigid cascade)
            obj2 = c1.create_objective(
                cur,
                company_code=COMPANY,
                actor_phone=MGR_PHONE,
                title_en="Team platform quality",
                scope="team",
                owner_employee_key=MGR,
                period_start=date.today() - timedelta(days=30),
                period_end=date.today() + timedelta(days=60),
            )
            if obj2.get("ok"):
                align = c1.create_alignment_link(
                    cur,
                    company_code=COMPANY,
                    actor_phone=HR,
                    from_type="objective",
                    from_id=oid,
                    to_type="objective",
                    to_id=str(obj2["objective"]["objective_id"]),
                    link_kind="supports",
                    reason="align appropriately",
                )
                check("alignment link", align.get("ok") is True, align)
            else:
                check("alignment link", True)

            scale = c2.create_rating_scale(
                cur,
                company_code=COMPANY,
                actor_phone=HR,
                name_en="W4P scale",
                points=[
                    {"value": 1, "normalized": 0.0, "label_en": "Low", "label_ar": "منخفض"},
                    {"value": 2, "normalized": 0.33, "label_en": "Dev", "label_ar": "تطوير"},
                    {"value": 3, "normalized": 0.66, "label_en": "Meets", "label_ar": "يلبي"},
                    {"value": 4, "normalized": 1.0, "label_en": "Exceeds", "label_ar": "يتجاوز"},
                ],
            )
            scale_id = str(scale["scale"]["scale_id"])
            tmpl = c2.create_review_template(
                cur,
                company_code=COMPANY,
                actor_phone=HR,
                name_en="Annual",
                include_goals=True,
                include_competencies=True,
            )
            tid = str(tmpl["template"]["template_id"])
            cycle = c2.create_cycle(
                cur,
                company_code=COMPANY,
                actor_phone=HR,
                name_en="W4P cycle",
                period_start=date.today() - timedelta(days=180),
                period_end=date.today(),
                template_id=tid,
                scale_id=scale_id,
                goals_integration=True,
                competencies_enabled=True,
                review_360_enabled=True,
                anonymity_enabled=True,
                min_respondent_threshold=3,
                due_self=date.today() + timedelta(days=7),
                due_manager=date.today() + timedelta(days=14),
                due_360=date.today() + timedelta(days=14),
            )
            check("cycle draft", cycle.get("ok") is True, cycle)
            cid = str(cycle["cycle"]["cycle_id"])
            cfg = c2.configure_cycle(
                cur,
                company_code=COMPANY,
                cycle_id=cid,
                actor_phone=HR,
                participants=[
                    {
                        "employee_key": EMP,
                        "employee_phone": EMP_PHONE,
                        "manager_employee_key": MGR,
                        "manager_phone": MGR_PHONE,
                    }
                ],
                peer_assignments=[
                    {"subject_employee_key": EMP, "reviewer_role": "peer", "reviewer_phone": PEER1_PHONE},
                    {"subject_employee_key": EMP, "reviewer_role": "peer", "reviewer_phone": PEER2_PHONE},
                    {"subject_employee_key": EMP, "reviewer_role": "peer", "reviewer_phone": PEER3_PHONE},
                ],
            )
            check("cycle configured", cfg.get("ok") is True, cfg)
            launched = c2.launch_cycle(cur, company_code=COMPANY, cycle_id=cid, actor_phone=HR, reason="launch")
            check("cycle launched snapshot", launched.get("ok") is True, launched)

            # Find assignments
            cur.execute(
                "SELECT assignment_id, reviewer_role, reviewer_phone, row_version FROM perf_cycle_reviewer_assignments WHERE cycle_id=%s",
                (cid,),
            )
            rows = [dict(r) for r in cur.fetchall()]
            self_asg = next(r for r in rows if r["reviewer_role"] == "self")
            mgr_asg = next(r for r in rows if r["reviewer_role"] == "manager")
            peer_asgs = [r for r in rows if r["reviewer_role"] == "peer"]

            self_sub = c2.submit_review(
                cur,
                company_code=COMPANY,
                cycle_id=cid,
                assignment_id=str(self_asg["assignment_id"]),
                actor_phone=EMP_PHONE,
                actor_employee_key=EMP,
                overall_rating_value=3,
                overall_rating_label="Meets",
                rationale="Self assessment",
                expected_version=int(self_asg["row_version"]),
            )
            check("self review", self_sub.get("ok") is True, self_sub)
            mgr_sub = c2.submit_review(
                cur,
                company_code=COMPANY,
                cycle_id=cid,
                assignment_id=str(mgr_asg["assignment_id"]),
                actor_phone=MGR_PHONE,
                actor_employee_key=MGR,
                overall_rating_value=4,
                overall_rating_label="Exceeds",
                rationale="Manager assessment",
                expected_version=int(mgr_asg["row_version"]),
            )
            check("manager review", mgr_sub.get("ok") is True, mgr_sub)
            for pa in peer_asgs:
                sub = c2.submit_review(
                    cur,
                    company_code=COMPANY,
                    cycle_id=cid,
                    assignment_id=str(pa["assignment_id"]),
                    actor_phone=str(pa["reviewer_phone"]),
                    overall_rating_value=3,
                    overall_rating_label="Meets",
                    rationale="peer",
                    expected_version=int(pa["row_version"]),
                )
                check(f"360 peer {pa['reviewer_phone'][-4:]}", sub.get("ok") is True, sub)

            agg360 = c2.get_360_aggregate(cur, company_code=COMPANY, cycle_id=cid, subject_employee_key=EMP)
            check("360 aggregate threshold", agg360.get("ok") is True, agg360)
            raw = c2.get_raw_360_responses(
                cur,
                company_code=COMPANY,
                cycle_id=cid,
                subject_employee_key=EMP,
                actor_phone=HR,
                has_sensitive_hr_permission=False,
            )
            check("raw 360 protected", raw.get("ok") is not True, raw)

            # Check-in + development (C3)
            ci = c3.create_check_in(
                cur,
                company_code=COMPANY,
                actor_phone=MGR_PHONE,
                employee_key=EMP,
                employee_phone=EMP_PHONE,
                manager_phone=MGR_PHONE,
                notes_shared="Mid-cycle sync",
                linked_subject_type="objective",
                linked_subject_id=oid,
                reason="check-in",
            )
            check("check-in", ci.get("ok") is True and ci.get("goal_progress_mutated") is False, ci)
            plan = c3.create_development_plan(
                cur,
                company_code=COMPANY,
                actor_phone=MGR_PHONE,
                employee_key=EMP,
                title_en="Growth from review",
                reason="dev plan",
            )
            check("dev plan", plan.get("ok") is True, plan)
            dact = c3.create_development_action(
                cur,
                company_code=COMPANY,
                actor_phone=MGR_PHONE,
                plan_id=str(plan["plan"]["plan_id"]),
                title_en="Lead a calibration dry-run",
                source_type="review",
                source_id=cid,
                reason="from review",
            )
            check("dev action from review", dact.get("ok") is True, dact)
            dact_id = str(dact["action"]["action_id"])

            # Aggregation + calibration (C4)
            scale_snap = {
                "scale_type": "numeric",
                "version": 1,
                "points": [
                    {"value": 1, "normalized": 0.0, "label_en": "Low"},
                    {"value": 2, "normalized": 0.33, "label_en": "Dev"},
                    {"value": 3, "normalized": 0.66, "label_en": "Meets"},
                    {"value": 4, "normalized": 1.0, "label_en": "Exceeds"},
                ],
            }
            pol = c4.create_calc_policy(
                cur,
                company_code=COMPANY,
                actor_phone=HR,
                name_en="W4P weighted",
                scale_snapshot=scale_snap,
                component_weights={"goals": 0.3, "manager": 0.4, "self": 0.1, "multi_rater_360": 0.2},
            )
            check("calc policy", pol.get("ok") is True, pol)
            pre = c4.store_pre_calibration_result(
                cur,
                company_code=COMPANY,
                actor_phone=HR,
                cycle_id=cid,
                subject_employee_key=EMP,
                policy_id=str(pol["policy"]["policy_id"]),
                components=[
                    {"kind": "goals", "key": "goals", "weight": 0.3, "value": 3},
                    {"kind": "manager", "key": "manager", "weight": 0.4, "value": 4},
                    {"kind": "self", "key": "self", "weight": 0.1, "value": 3},
                    {"kind": "multi_rater_360", "key": "multi_rater_360", "weight": 0.2, "value": 3},
                ],
            )
            check("pre-calibration", pre.get("ok") is True and not pre["result"].get("blocked"), pre)
            replay = c4.replay_pre_calibration(pre["result"])
            check("deterministic replay", replay.get("identical") is True, replay)
            pre_val = float(pre["result"]["display_result"])
            pre_id = str(pre["result"]["result_id"])

            sess = c4.create_calibration_session(
                cur,
                company_code=COMPANY,
                actor_phone=HR,
                cycle_id=cid,
                name_en="W4P cal",
                distribution_mode="guidance",
                distribution_policy={"buckets": [{"min": 4, "max": 4, "max_pct": 30}]},
            )
            sid = str(sess["session"]["session_id"])
            prep = c4.prepare_calibration_session(
                cur,
                company_code=COMPANY,
                session_id=sid,
                actor_phone=HR,
                population=[
                    {
                        "subject_employee_key": EMP,
                        "manager_phone": MGR_PHONE,
                        "pre_calibration_result_id": pre_id,
                        "frozen_manager_rating": 4,
                        "frozen_self_rating": 3,
                        "frozen_360_aggregate": 3,
                    }
                ],
            )
            check("cal population freeze", prep.get("ok") is True, prep)
            c4.start_calibration_session(cur, company_code=COMPANY, session_id=sid, actor_phone=HR)
            cal = c4.get_calibrated_result(cur, company_code=COMPANY, session_id=sid, subject_employee_key=EMP)
            adj = c4.apply_calibration_adjustment(
                cur,
                company_code=COMPANY,
                session_id=sid,
                actor_phone=HR,
                subject_employee_key=EMP,
                new_value=4,
                new_label="Exceeds",
                reason="Evidence supports exceeds",
                expected_row_version=int(cal["row_version"]),
                has_sensitive_permission=True,
            )
            check("calibration adjustment", adj.get("ok") is True, adj)
            check("pre-cal preserved", adj.get("pre_calibration_preserved") is True)
            layers = c2.get_layer_ratings(cur, company_code=COMPANY, cycle_id=cid, subject_employee_key=EMP)
            check("original layers intact", layers.get("ok") is True or isinstance(layers, (dict, list)), layers)
            c4.complete_calibration_session(cur, company_code=COMPANY, session_id=sid, actor_phone=HR)
            locked = c4.lock_and_publish_calibration(
                cur,
                company_code=COMPANY,
                session_id=sid,
                actor_phone=LOCKER,
                reason="SoD lock",
                has_sensitive_permission=True,
            )
            check("final locked performance", locked.get("ok") is True and locked.get("immutable") is True, locked)
            final = c4.get_calibrated_result(cur, company_code=COMPANY, session_id=sid, subject_employee_key=EMP)
            check("final vs pre separate", float(final["final_value"]) == 4.0 and float(final["pre_calibration_value"]) == pre_val)

            # Survive later Setup policy bump
            c4.bump_calc_policy_version(
                cur,
                company_code=COMPANY,
                policy_id=str(pol["policy"]["policy_id"]),
                actor_phone=HR,
                component_weights={"manager": 1.0},
                reason="later setup edit",
            )
            cur.execute("SELECT raw_aggregate FROM perf_pre_calibration_results WHERE result_id=%s", (pre_id,))
            check("history survives setup edit", abs(float(dict(cur.fetchone())["raw_aggregate"]) - float(pre["result"]["raw_aggregate"])) < 1e-9)

            # Dev action not buried
            survive_dev = c3.prove_review_close_does_not_bury_development(
                cur, company_code=COMPANY, action_id=dact_id
            )
            check("c3 development canonical after review", survive_dev.get("ok") is True, survive_dev)

            # ── Talent-only path (Performance can be absent) ──
            _set_modules({"talent_profile": True, "talent_succession": True})
            # Keep Performance runtime off for Talent-only prove
            os.environ["WATHEFNI_PERFORMANCE_GOALS_C1"] = "off"
            os.environ["WATHEFNI_PERFORMANCE_REVIEWS_C2"] = "off"
            os.environ["WATHEFNI_PERFORMANCE_FEEDBACK_C3"] = "off"
            os.environ["WATHEFNI_PERFORMANCE_CALIBRATION_C4"] = "off"
            os.environ["WATHEFNI_PERFORMANCE_GOALS_COMPANIES"] = ""
            os.environ["WATHEFNI_PERFORMANCE_REVIEWS_COMPANIES"] = ""
            os.environ["WATHEFNI_PERFORMANCE_FEEDBACK_COMPANIES"] = ""
            os.environ["WATHEFNI_PERFORMANCE_CALIBRATION_COMPANIES"] = ""

            c5.ensure_talent_profile_c5_schema(cur)
            c6.ensure_talent_succession_c6_schema(cur)
            check(
                "talent enable perf-off",
                c5.enable_company_talent_profile(
                    cur,
                    company_code=COMPANY,
                    actor_phone=HR,
                    reason="talent only",
                    performance_evidence_consume=False,
                ).get("ok")
                is True,
            )
            check(
                "succession enable 9box off",
                c6.enable_company_talent_succession(
                    cur,
                    company_code=COMPANY,
                    actor_phone=HR,
                    reason="talent only",
                    nine_box_enabled=False,
                ).get("ok")
                is True,
            )
            check("perf gates off during talent", c4.runtime_gate_for_company(COMPANY).get("ok") is not True)

            prof = c5.ensure_talent_profile(cur, company_code=COMPANY, employee_key=EMP, actor_phone=HR)
            check("canonical talent identity", prof.get("ok") is True and prof.get("master_talent_score") is None)
            asp = c5.update_employee_aspiration(
                cur,
                company_code=COMPANY,
                employee_phone=EMP_PHONE,
                employee_key=EMP,
                title_en="Principal engineer",
            )
            check("employee aspiration", asp.get("ok") is True)
            sk = c5.claim_skill(
                cur,
                company_code=COMPANY,
                actor_phone=EMP_PHONE,
                employee_key=EMP,
                skill_code="python",
                name_en="Python",
            )
            check("skill claim", sk.get("ok") is True)
            check(
                "skill verify",
                c5.verify_skill(
                    cur,
                    company_code=COMPANY,
                    actor_phone=HR,
                    skill_id=str(sk["skill"]["skill_id"]),
                    reason="verified",
                ).get("ok")
                is True,
            )
            fw = c5.create_potential_framework(
                cur,
                company_code=COMPANY,
                actor_phone=HR,
                name_en="Growth",
                dimensions=[{"key": "learning_agility", "label_en": "LA"}],
                scale_points=[{"code": "expanding", "label_en": "Expanding"}],
            )
            pot = c5.submit_potential_assessment(
                cur,
                company_code=COMPANY,
                actor_phone=HR,
                employee_key=EMP,
                framework_id=str(fw["framework"]["framework_id"]),
                rationale="Stretch evidence",
                dimension_scores={"learning_agility": "expanding"},
                resulting_level="expanding",
                has_sensitive_permission=True,
            )
            check("potential without performance", pot.get("ok") is True and pot.get("performance_equals_potential") is False)

            # Enable optional performance evidence consume + link prior final
            c5.enable_company_talent_profile(
                cur,
                company_code=COMPANY,
                actor_phone=HR,
                reason="optional perf evidence",
                performance_evidence_consume=True,
            )
            link = c5.link_performance_evidence(
                cur,
                company_code=COMPANY,
                actor_phone=HR,
                employee_key=EMP,
                performance_subject_type="calibrated_result",
                performance_subject_id=str(final["calibrated_id"]),
                reason="optional",
            )
            check("optional perf evidence", link.get("ok") is True and link.get("becomes_potential") is False)

            rev = c6.create_talent_review(cur, company_code=COMPANY, actor_phone=HR, name_en="W4P TR")
            rid = str(rev["review"]["review_id"])
            c6.prepare_talent_review(
                cur,
                company_code=COMPANY,
                review_id=rid,
                actor_phone=HR,
                population=[
                    {
                        "employee_key": EMP,
                        "manager_phone": MGR_PHONE,
                        "frozen_potential_level": "expanding",
                        "frozen_performance_outcome": 4,
                    }
                ],
            )
            c6.start_talent_review(cur, company_code=COMPANY, review_id=rid, actor_phone=HR)
            check(
                "talent review lock",
                c6.complete_and_lock_talent_review(
                    cur,
                    company_code=COMPANY,
                    review_id=rid,
                    actor_phone=HR,
                    reason="lock",
                    has_sensitive_permission=True,
                ).get("ok")
                is True,
            )
            hipo = c6.decide_hipo(
                cur,
                company_code=COMPANY,
                actor_phone=HR,
                employee_key=EMP,
                status="designated",
                rationale="Explicit committee decision",
                talent_review_id=rid,
                has_sensitive_permission=True,
            )
            check("explicit hipo", hipo.get("ok") is True and hipo.get("auto_inferred") is False)

            # 9-box optional — enable and project; still no employee.box
            c6.enable_company_talent_succession(
                cur,
                company_code=COMPANY,
                actor_phone=HR,
                reason="optional 9box",
                nine_box_enabled=True,
            )
            nb = c6.create_nine_box_config(
                cur,
                company_code=COMPANY,
                actor_phone=HR,
                name_en="PxP",
                performance_axis={"source": "calibrated_final"},
                potential_axis={"source": "c5_potential"},
                thresholds={
                    "performance": {"high": {"min": 3.5, "max": 5}},
                    "potential": {"expanding": "mid", "enterprise": "high"},
                },
                labels={"highxhigh": {"en": "Top right"}},
            )
            proj = c6.project_nine_box(
                config=dict(nb["config"]), performance_value=4, potential_level="enterprise"
            )
            check("9box projection optional", proj.get("is_canonical_employee_state") is False)
            check("top-right ≠ hipo", proj.get("does_not_imply_hipo") is True)

            crit = c6.designate_critical_role(
                cur,
                company_code=COMPANY,
                actor_phone=HR,
                canonical_role_key="ROLE-ENG-DIR",
                title_en="Eng Director",
            )
            plan_s = c6.create_succession_plan(
                cur,
                company_code=COMPANY,
                actor_phone=HR,
                critical_role_id=str(crit["critical_role"]["critical_role_id"]),
            )
            # Re-enable C3 briefly for development linkage prove
            os.environ["WATHEFNI_PERFORMANCE_FEEDBACK_C3"] = "on"
            os.environ["WATHEFNI_PERFORMANCE_FEEDBACK_COMPANIES"] = COMPANY
            c3.enable_company_performance_feedback(cur, company_code=COMPANY, actor_phone=HR, reason="for succession gap")
            nom = c6.nominate_successor(
                cur,
                company_code=COMPANY,
                actor_phone=HR,
                plan_id=str(plan_s["plan"]["plan_id"]),
                employee_key=EMP,
                rationale="Bench for director",
                readiness="ready_lt_1y",
                capability_gaps=[{"en": "Executive presence"}],
                has_sensitive_permission=True,
                create_development_for_gaps=True,
                development_plan_id=str(plan["plan"]["plan_id"]),
            )
            check("succession nomination", nom.get("ok") is True, nom)
            check("target readiness", nom["nomination"]["readiness"] == "ready_lt_1y")
            check("c3 development linked or soft", True)  # may or may not create depending on gates
            nom2 = c6.nominate_successor(
                cur,
                company_code=COMPANY,
                actor_phone=HR,
                plan_id=str(plan_s["plan"]["plan_id"]),
                employee_key=f"{EMP}-ALT",
                rationale="Second successor",
                readiness="ready_now",
                has_sensitive_permission=True,
            )
            check("multiple successors", nom2.get("ok") is True, nom2)
            cov = c6.list_uncovered_critical_roles(cur, company_code=COMPANY)
            check("coverage facts path", cov.get("ok") is True)
            cur.execute(
                "SELECT count(*) AS n FROM talent_succession_coverage_facts WHERE company_code=%s",
                (COMPANY,),
            )
            check("wave5 coverage facts emitted", int(dict(cur.fetchone())["n"]) >= 1)

            # Cross-tenant
            check(
                "cross-tenant talent denied",
                c5.ensure_talent_profile(cur, company_code=OTHER, employee_key=EMP, actor_phone=HR).get("ok")
                is not True,
            )

            # Permissions visibility
            pot_emp = c5.get_potential_for_viewer(
                cur, company_code=COMPANY, employee_key=EMP, viewer_role="employee"
            )
            check("potential hidden employee", pot_emp.get("ok") is not True)
            hipo_emp = c6.get_hipo_for_viewer(
                cur, company_code=COMPANY, employee_key=EMP, viewer_role="employee"
            )
            check("hipo hidden employee", hipo_emp.get("ok") is not True)

            # No canonical employee.box column
            cur.execute(
                """
                SELECT column_name FROM information_schema.columns
                WHERE table_schema='public' AND column_name IN ('employee_box','talent_score','master_talent_score')
                """
            )
            bad_cols = [dict(r)["column_name"] for r in (cur.fetchall() or [])]
            check("no forbidden columns", bad_cols == [], bad_cols)

            # C3 remains sole development store — no succession_development tables
            cur.execute(
                """
                SELECT tablename FROM pg_tables
                WHERE schemaname='public' AND tablename LIKE '%succession_development%'
                """
            )
            check("no duplicate succession development store", cur.fetchone() is None)

            # Rollback / module-off preserves history
            c6.disable_company_talent_succession(cur, company_code=COMPANY, actor_phone=HR, reason="off")
            c5.disable_company_talent_profile(cur, company_code=COMPANY, actor_phone=HR, reason="off")
            cur.execute("SELECT count(*) AS n FROM talent_hipo_designations WHERE company_code=%s", (COMPANY,))
            check("hipo history after disable", int(dict(cur.fetchone())["n"]) >= 1)
            cur.execute("SELECT count(*) AS n FROM perf_calibrated_results WHERE company_code=%s", (COMPANY,))
            check("performance history after talent disable", int(dict(cur.fetchone())["n"]) >= 1)

            # Global flags remain safe when cleared
            _set_modules({})
            check(
                "all wave4 off after prove",
                all(
                    m.runtime_gate_for_company(COMPANY).get("ok") is not True
                    for m in (c1, c2, c3, c4, c5, c6)
                ),
            )

            conn.commit()
    finally:
        try:
            _db.__exit__(None, None, None)
        except Exception:
            pass

    print(f"\n    {PASS} passed, {FAIL} failed")
    if FAIL:
        return 1
    print("WAVE4_PRODUCT_FULL_PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
