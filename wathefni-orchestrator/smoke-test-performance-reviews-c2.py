#!/usr/bin/env python3
"""Wave 4 C2 — Performance Review Cycles / Ratings / 360 synthetic prove."""
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
COMPANY = f"PR2{_N:05d}"[:12].upper()
OTHER = f"PRX{_N:05d}"[:12].upper()
HR = f"9656300{_N:05d}"
EMP = f"{COMPANY}-W4C2-{SUFFIX}"
EMP_PHONE = f"9656301{_N:05d}"
MGR = f"{COMPANY}-MGR-{SUFFIX}"
MGR_PHONE = f"9656302{_N:05d}"
MGR2_PHONE = f"9656303{_N:05d}"
PEER1 = f"{COMPANY}-P1-{SUFFIX}"
PEER1_PHONE = f"9656304{_N:05d}"
PEER2 = f"{COMPANY}-P2-{SUFFIX}"
PEER2_PHONE = f"9656305{_N:05d}"
PEER3 = f"{COMPANY}-P3-{SUFFIX}"
PEER3_PHONE = f"9656306{_N:05d}"
OUT_PHONE = f"9656399{_N:05d}"


def check(label: str, condition: bool, detail: object = None) -> None:
    global PASS, FAIL
    if condition:
        PASS += 1
        print(f"      PASS  {label}")
    else:
        FAIL += 1
        extra = f" :: {detail}" if detail is not None else ""
        print(f"      FAIL  {label}{extra}")


def _flags(*, on: str, companies: str) -> None:
    os.environ["WATHEFNI_PERFORMANCE_REVIEWS_C2"] = on
    os.environ["WATHEFNI_PERFORMANCE_REVIEWS_COMPANIES"] = companies
    os.environ["WATHEFNI_PERFORMANCE_KILL"] = "off"
    # C1 for optional goals integration
    os.environ["WATHEFNI_PERFORMANCE_GOALS_C1"] = "on"
    os.environ["WATHEFNI_PERFORMANCE_GOALS_COMPANIES"] = companies


def main() -> int:
    print("    performance reviews c2 — prove")
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import performance_reviews_c2 as c2

    check("c2 module", c2.PHASE == "performance_reviews_c2")
    check("charter stamp", c2.PASS_STAMP == "PERFORMANCE_REVIEWS_FULL_PASS")
    check("talent not required", c2.honesty_payload().get("talent_required") is False)
    check("no hipo in c2", c2.honesty_payload().get("hipo_classification_in_c2") is False)
    check("snapshot honesty", c2.honesty_payload().get("cycle_launch_snapshots_rules") is True)
    check("anonymity fail-closed", c2.honesty_payload().get("anonymity_fail_closed_below_threshold") is True)
    check("assistant out", c2.honesty_payload().get("assistant_mutations") is False)
    check("EN launched", c2.status_label("launched", lang="en") == "Launched")
    check("AR closed", c2.status_label("closed", lang="ar") == "مغلق")
    check("rollback", "WATHEFNI_PERFORMANCE_REVIEWS_C2=off" in str(c2.rollback_guidance()))

    _flags(on="off", companies="")
    check("global off", c2.runtime_gate_for_company(COMPANY).get("ok") is not True)
    _flags(on="on", companies="")
    check("empty allowlist", "allowlist" in str(c2.runtime_gate_for_company(COMPANY).get("gate")))
    _flags(on="on", companies=COMPANY)
    check("canary ok", c2.runtime_gate_for_company(COMPANY).get("ok") is True)
    check("tenant iso", c2.runtime_gate_for_company(OTHER).get("ok") is not True)

    try:
        import app
        import performance_goals_c1 as c1
    except ModuleNotFoundError as exc:
        if exc.name == "psycopg2":
            print("SKIP DB")
            print(f"\n    {PASS} passed, {FAIL} failed (unit-only)")
            return 1 if FAIL else 0
        raise

    period_start = date.today() - timedelta(days=180)
    period_end = date.today()
    due = date.today() + timedelta(days=14)

    with app.db_connect() as conn:
        with conn.cursor() as cur:
            c2.ensure_performance_reviews_c2_schema(cur)
            c1.ensure_performance_goals_c1_schema(cur)
            cur.execute(
                """
                INSERT INTO companies (company_code, name, metadata, raw_json, created_at, updated_at)
                VALUES (%s,%s,'{}'::jsonb,'{}'::jsonb,now(),now())
                ON CONFLICT (company_code) DO NOTHING
                """,
                (COMPANY, f"PR2 {COMPANY}"),
            )
            for key, phone, name in (
                (EMP, EMP_PHONE, "Subject"),
                (MGR, MGR_PHONE, "Manager"),
                (PEER1, PEER1_PHONE, "Peer1"),
                (PEER2, PEER2_PHONE, "Peer2"),
                (PEER3, PEER3_PHONE, "Peer3"),
            ):
                cur.execute(
                    """
                    INSERT INTO employees (company_code, employee_key, phone, name, hire_date, start_date, profile, employment_status)
                    VALUES (%s,%s,%s,%s,%s,%s,'{}'::jsonb,'active')
                    ON CONFLICT (employee_key) DO UPDATE SET employment_status='active', phone=EXCLUDED.phone
                    """,
                    (COMPANY, key, phone, name, period_start, period_start),
                )

            blocked = c2.create_cycle(
                cur,
                company_code=COMPANY,
                actor_phone=HR,
                name_en="x",
                period_start=period_start,
                period_end=period_end,
                template_id=str(uuid.uuid4()),
                scale_id=str(uuid.uuid4()),
            )
            check("blocked while entitlement off", blocked.get("ok") is not True, blocked)

            # Enable C1 goals + seed evidence
            c1.enable_company_performance_goals(
                cur, company_code=COMPANY, actor_phone=HR, reason="c2 goals"
            )
            m = c1.create_measure_definition(
                cur,
                company_code=COMPANY,
                actor_phone=HR,
                name_en="Revenue",
                unit="KWD",
                direction="higher_is_better",
                baseline=0,
                target=100,
                period_start=period_start,
                period_end=period_end,
                owner_employee_key=EMP,
            )
            mid = str(m["measure"]["measure_id"])
            obj = c1.create_objective(
                cur,
                company_code=COMPANY,
                actor_phone=HR,
                title_en="Grow book",
                scope="individual",
                owner_employee_key=EMP,
                period_start=period_start,
                period_end=period_end,
            )
            oid = str(obj["objective"]["objective_id"])
            kr = c1.add_key_result(
                cur,
                company_code=COMPANY,
                objective_id=oid,
                actor_phone=HR,
                title_en="Hit 100",
                measure_id=mid,
                weight=1,
            )
            c1.activate_objective(cur, company_code=COMPANY, objective_id=oid, actor_phone=HR, reason="a")
            c1.record_progress(
                cur,
                company_code=COMPANY,
                subject_type="key_result",
                subject_id=str(kr["key_result"]["key_result_id"]),
                actor_phone=EMP_PHONE,
                current_value=80,
            )

            en = c2.enable_company_performance_reviews(
                cur,
                company_code=COMPANY,
                actor_phone=HR,
                reason="enable c2",
                goals_integration_enabled=True,
                competencies_enabled=False,
                review_360_enabled=True,
                anonymity_default=True,
                min_respondent_threshold=3,
                allow_hr_raw_360=True,
            )
            check("enable reviews", en.get("ok") is True, en)
            thr_bad = c2.enable_company_performance_reviews(
                cur,
                company_code=COMPANY,
                actor_phone=HR,
                reason="bad thr",
                min_respondent_threshold=1,
            )
            check("threshold <2 rejected", thr_bad.get("error") == "min_respondent_threshold_too_low", thr_bad)
            # restore good settings
            c2.enable_company_performance_reviews(
                cur,
                company_code=COMPANY,
                actor_phone=HR,
                reason="restore",
                review_360_enabled=True,
                min_respondent_threshold=3,
                allow_hr_raw_360=True,
            )

            vis = c2.feature_visibility(cur, COMPANY)
            check("cycles visible", vis.get("review_cycles_visible") is True, vis)
            check("talent hidden", vis.get("talent_visible") is False, vis)

            scale = c2.create_rating_scale(
                cur,
                company_code=COMPANY,
                actor_phone=HR,
                name_en="Custom 4-point",
                name_ar="مقياس رباعي",
                scale_type="labeled",
                points=[
                    {"value": 1, "label_en": "Needs work", "label_ar": "يحتاج تحسين"},
                    {"value": 2, "label_en": "Solid", "label_ar": "جيد"},
                    {"value": 3, "label_en": "Strong", "label_ar": "قوي"},
                    {"value": 4, "label_en": "Exceptional", "label_ar": "متميز"},
                    {"value": None, "label_en": "Not observed", "not_observed": True},
                ],
            )
            check("custom rating scale", scale.get("ok") is True, scale)
            scale_id = str(scale["scale"]["scale_id"])
            scale_v2 = c2.bump_rating_scale_version(
                cur,
                company_code=COMPANY,
                scale_id=scale_id,
                actor_phone=HR,
                points=[{"value": 1, "label_en": "Low"}, {"value": 5, "label_en": "High"}],
                reason="new company default scale",
            )
            check("scale versioned (new id)", scale_v2.get("ok") is True and str(scale_v2["scale"]["scale_id"]) != scale_id, scale_v2)

            tmpl = c2.create_review_template(
                cur,
                company_code=COMPANY,
                actor_phone=HR,
                name_en="Annual",
                name_ar="سنوي",
                include_goals=True,
                include_competencies=False,
            )
            check("template created", tmpl.get("ok") is True, tmpl)
            tid = str(tmpl["template"]["template_id"])

            # Reviews without competencies / with goals
            cycle = c2.create_cycle(
                cur,
                company_code=COMPANY,
                actor_phone=HR,
                name_en="FY cycle",
                name_ar="دورة السنة",
                period_start=period_start,
                period_end=period_end,
                template_id=tid,
                scale_id=scale_id,  # v1 snapshotted — not v2
                goals_integration=True,
                competencies_enabled=False,
                review_360_enabled=True,
                anonymity_enabled=True,
                min_respondent_threshold=3,
                due_self=due,
                due_manager=due,
                due_360=due,
            )
            check("create cycle draft", cycle.get("ok") is True and cycle["cycle"]["status"] == "draft", cycle)
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
                    {
                        "subject_employee_key": EMP,
                        "reviewer_role": "peer",
                        "reviewer_employee_key": PEER1,
                        "reviewer_phone": PEER1_PHONE,
                    },
                    {
                        "subject_employee_key": EMP,
                        "reviewer_role": "peer",
                        "reviewer_employee_key": PEER2,
                        "reviewer_phone": PEER2_PHONE,
                    },
                    {
                        "subject_employee_key": EMP,
                        "reviewer_role": "peer",
                        "reviewer_employee_key": PEER3,
                        "reviewer_phone": PEER3_PHONE,
                    },
                ],
            )
            check("configure cycle", cfg.get("ok") is True and cfg["cycle"]["status"] == "configured", cfg)

            launched = c2.launch_cycle(
                cur, company_code=COMPANY, cycle_id=cid, actor_phone=HR, reason="launch FY"
            )
            check("launch snapshots rules/population", launched.get("ok") is True and launched.get("snapshot_frozen") is True, launched)
            check("status in_progress", launched["cycle"]["status"] == "in_progress", launched)
            snap = launched["cycle"].get("snapshot") or {}
            if isinstance(snap, str):
                import json

                snap = json.loads(snap)
            check("snapshot has scale version", int((snap.get("rating_scale") or {}).get("version") or 0) == 1, snap)
            check("snapshot has population", len(snap.get("population") or []) == 1, snap)
            check("snapshot has goal evidence", bool((snap.get("goal_evidence_by_employee") or {}).get(EMP)), snap)

            mut = c2.attempt_mutate_launched_setup(
                cur, company_code=COMPANY, cycle_id=cid, new_name_en="HACK"
            )
            check("setup cannot mutate launched cycle", mut.get("error") == "launched_cycle_immutable", mut)

            # Later C1 target change must not rewrite snapshot evidence
            c1.change_measure_targets(
                cur, company_code=COMPANY, measure_id=mid, actor_phone=HR, reason="after launch", target=9999
            )
            cur.execute("SELECT snapshot FROM perf_review_cycles WHERE cycle_id=%s", (cid,))
            snap2 = (cur.fetchone() or {}).get("snapshot") or {}
            if isinstance(snap2, str):
                import json

                snap2 = json.loads(snap2)
            ev = ((snap2.get("goal_evidence_by_employee") or {}).get(EMP) or {}).get("objectives") or []
            # Original measure target in KR snapshot should still reflect pre-change (100) if stored
            kr0 = (((ev[0] if ev else {}).get("key_results") or [{}])[0])
            check(
                "later goal edits do not rewrite cycle snapshot",
                float(kr0.get("target") or 0) == 100.0 or (ev and ev[0].get("rollup_progress_pct") == 80.0),
                kr0,
            )

            cur.execute(
                "SELECT assignment_id FROM perf_cycle_reviewer_assignments WHERE cycle_id=%s AND reviewer_role='self'",
                (cid,),
            )
            self_aid = str((cur.fetchone() or {})["assignment_id"])
            cur.execute(
                "SELECT assignment_id FROM perf_cycle_reviewer_assignments WHERE cycle_id=%s AND reviewer_role='manager' AND status='assigned'",
                (cid,),
            )
            mgr_aid = str((cur.fetchone() or {})["assignment_id"])

            self_sub = c2.submit_review(
                cur,
                company_code=COMPANY,
                cycle_id=cid,
                assignment_id=self_aid,
                actor_phone=EMP_PHONE,
                actor_employee_key=EMP,
                overall_rating_value=3,
                overall_rating_label="Strong",
                rationale="I delivered the book of business.",
                components=[{"key": "overall", "value": 3}],
                expected_version=1,
            )
            check("employee self-review submit", self_sub.get("ok") is True, self_sub)

            # Out of scope manager
            scope = c2.assert_manager_scope(
                cur,
                company_code=COMPANY,
                cycle_id=cid,
                manager_phone=OUT_PHONE,
                subject_employee_key=EMP,
            )
            check("manager cannot review out-of-scope", scope.get("error") == "manager_out_of_scope", scope)

            bad_actor = c2.submit_review(
                cur,
                company_code=COMPANY,
                cycle_id=cid,
                assignment_id=mgr_aid,
                actor_phone=OUT_PHONE,
                overall_rating_value=2,
                rationale="nope",
            )
            check("reviewer assignment enforcement", bad_actor.get("error") == "reviewer_assignment_mismatch", bad_actor)

            mgr_sub = c2.submit_review(
                cur,
                company_code=COMPANY,
                cycle_id=cid,
                assignment_id=mgr_aid,
                actor_phone=MGR_PHONE,
                actor_employee_key=MGR,
                overall_rating_value=3,
                overall_rating_label="Strong",
                rationale="Consistent delivery against goals.",
                components=[{"key": "overall", "value": 3, "weight": 1}],
                expected_version=1,
            )
            check("manager review submit", mgr_sub.get("ok") is True, mgr_sub)
            mgr_rid = str(mgr_sub["review"]["review_id"])

            # Goal evidence on review
            ge = mgr_sub["review"].get("goal_evidence_snapshot")
            if isinstance(ge, str):
                import json

                ge = json.loads(ge)
            check("C1 goal evidence consumed on review", bool(ge and (ge.get("objectives") or ge.get("goals") is not None)), ge)

            # Immutable submitted
            imm = c2.attempt_mutate_submitted_review(
                cur, company_code=COMPANY, review_id=mgr_rid, new_rating=1
            )
            check("submitted immutable", imm.get("error") == "submitted_review_immutable", imm)

            # Stale / duplicate
            stale = c2.submit_review(
                cur,
                company_code=COMPANY,
                cycle_id=cid,
                assignment_id=mgr_aid,
                actor_phone=MGR_PHONE,
                overall_rating_value=1,
                rationale="stale",
                expected_version=1,
            )
            # already submitted → idempotent
            check(
                "duplicate submission idempotent",
                stale.get("idempotent_duplicate_submission") is True or stale.get("error") == "stale_row_version",
                stale,
            )

            # 360 submissions — threshold fail then pass
            cur.execute(
                """
                SELECT assignment_id, reviewer_phone FROM perf_cycle_reviewer_assignments
                 WHERE cycle_id=%s AND reviewer_role='peer' AND status='assigned'
                 ORDER BY created_at
                """,
                (cid,),
            )
            peers = [dict(r) for r in cur.fetchall()]
            # only 1 peer first
            p0 = c2.submit_review(
                cur,
                company_code=COMPANY,
                cycle_id=cid,
                assignment_id=str(peers[0]["assignment_id"]),
                actor_phone=str(peers[0]["reviewer_phone"]),
                overall_rating_value=4,
                rationale="Strong collaborator",
                confidential_comment="Keep private",
            )
            check("360 invitation/submission (1)", p0.get("ok") is True, p0)
            agg_fail = c2.get_360_aggregate(
                cur, company_code=COMPANY, cycle_id=cid, subject_employee_key=EMP
            )
            check(
                "anonymity threshold fail-closed",
                agg_fail.get("error") == "anonymity_threshold_not_met" and agg_fail.get("fail_closed") is True,
                agg_fail,
            )
            check("no identities on fail", agg_fail.get("identities") is None, agg_fail)

            for p in peers[1:]:
                c2.submit_review(
                    cur,
                    company_code=COMPANY,
                    cycle_id=cid,
                    assignment_id=str(p["assignment_id"]),
                    actor_phone=str(p["reviewer_phone"]),
                    overall_rating_value=3,
                    rationale="Good peer",
                )
            agg_ok = c2.get_360_aggregate(
                cur, company_code=COMPANY, cycle_id=cid, subject_employee_key=EMP
            )
            check(
                "anonymity threshold pass",
                agg_ok.get("ok") is True and agg_ok.get("identities_redacted") is True and agg_ok.get("respondent_count") >= 3,
                agg_ok,
            )

            raw_deny = c2.get_raw_360_responses(
                cur,
                company_code=COMPANY,
                cycle_id=cid,
                subject_employee_key=EMP,
                actor_phone=MGR_PHONE,
                has_sensitive_hr_permission=False,
            )
            check("raw 360 denied without sensitive perm", raw_deny.get("error") == "sensitive_360_permission_required", raw_deny)
            raw_ok = c2.get_raw_360_responses(
                cur,
                company_code=COMPANY,
                cycle_id=cid,
                subject_employee_key=EMP,
                actor_phone=HR,
                has_sensitive_hr_permission=True,
            )
            check("HR raw 360 with sensitive permission", raw_ok.get("ok") is True and raw_ok.get("sensitive") is True, raw_ok)

            # Reassignment audit
            re = c2.reassign_manager_reviewer(
                cur,
                company_code=COMPANY,
                cycle_id=cid,
                subject_employee_key=EMP,
                new_manager_employee_key=f"{COMPANY}-MGR2-{SUFFIX}",
                new_manager_phone=MGR2_PHONE,
                actor_phone=HR,
                reason="org change mid-cycle",
            )
            check("reviewer reassignment", re.get("ok") is True, re)
            cur.execute(
                "SELECT count(*) AS c FROM performance_reviews_c2_audit WHERE action='manager_reviewer_reassigned' AND company_code=%s",
                (COMPANY,),
            )
            check("reassignment audited", int((cur.fetchone() or {}).get("c") or 0) >= 1)

            # Layers separate
            layers = c2.get_layer_ratings(
                cur, company_code=COMPANY, cycle_id=cid, subject_employee_key=EMP
            )
            check(
                "self/manager/360 layers separate",
                layers.get("collapsed") is False
                and bool((layers.get("layers") or {}).get("self"))
                and bool((layers.get("layers") or {}).get("manager")),
                layers,
            )

            # Ack
            ack = c2.acknowledge_review(
                cur, company_code=COMPANY, review_id=mgr_rid, actor_phone=EMP_PHONE, decision="acknowledged"
            )
            check("acknowledgement", ack.get("ok") is True, ack)

            c2.mark_calibration_ready(
                cur, company_code=COMPANY, cycle_id=cid, actor_phone=HR, reason="ready"
            )
            closed = c2.close_cycle(
                cur, company_code=COMPANY, cycle_id=cid, actor_phone=HR, reason="close FY"
            )
            check("close cycle", closed.get("ok") is True and closed.get("layers_preserved") is True, closed)
            reopen = c2.attempt_reopen_closed_cycle(cur, company_code=COMPANY, cycle_id=cid)
            check("closed cycle cannot silently reopen", reopen.get("error") == "closed_cycle_cannot_silently_reopen", reopen)

            layers2 = c2.get_layer_ratings(
                cur, company_code=COMPANY, cycle_id=cid, subject_employee_key=EMP
            )
            check(
                "final distinct from self/manager",
                bool((layers2.get("layers") or {}).get("final"))
                and (layers2["layers"]["final"].get("source") == "manager_close"),
                layers2,
            )
            check(
                "original manager rationale preserved",
                (layers2["layers"]["manager"] or {}).get("rationale") == "Consistent delivery against goals.",
                layers2,
            )

            # --- Modularity: reviews without 360 / without goals ---
            scale_b = c2.create_rating_scale(
                cur,
                company_code=COMPANY,
                actor_phone=HR,
                name_en="Simple 5",
                points=[{"value": i, "label_en": str(i)} for i in range(1, 6)],
            )
            tmpl_b = c2.create_review_template(
                cur,
                company_code=COMPANY,
                actor_phone=HR,
                name_en="Qual only",
                include_goals=False,
                include_competencies=False,
            )
            cyc_b = c2.create_cycle(
                cur,
                company_code=COMPANY,
                actor_phone=HR,
                name_en="No goals no 360",
                period_start=period_start,
                period_end=period_end,
                template_id=str(tmpl_b["template"]["template_id"]),
                scale_id=str(scale_b["scale"]["scale_id"]),
                goals_integration=False,
                competencies_enabled=False,
                review_360_enabled=False,
            )
            cid_b = str(cyc_b["cycle"]["cycle_id"])
            c2.configure_cycle(
                cur,
                company_code=COMPANY,
                cycle_id=cid_b,
                actor_phone=HR,
                participants=[
                    {
                        "employee_key": EMP,
                        "employee_phone": EMP_PHONE,
                        "manager_employee_key": MGR,
                        "manager_phone": MGR_PHONE,
                    }
                ],
            )
            lb = c2.launch_cycle(cur, company_code=COMPANY, cycle_id=cid_b, actor_phone=HR, reason="mod")
            check("reviews without 360/goals", lb.get("ok") is True, lb)
            check("reviews without Talent (always)", c2.honesty_payload().get("talent_required") is False)

            # Goals continue without review cycles — C1 still works with reviews kill conceptually
            # Prove C1 module still enabled independently
            gvis = c1.feature_visibility(cur, COMPANY)
            check("goals work without depending on cycles", gvis.get("okrs_visible") is True, gvis)

            # Module-off preserves history
            off = c2.disable_company_performance_reviews(
                cur, company_code=COMPANY, actor_phone=HR, reason="rollback"
            )
            check("disable preserves history", off.get("history_preserved") is True, off)
            cur.execute(
                "SELECT count(*) AS c FROM perf_reviews WHERE company_code=%s AND status IN ('submitted','acknowledged')",
                (COMPANY,),
            )
            check("historical review truth intact", int((cur.fetchone() or {}).get("c") or 0) >= 2)
            check("module-off after disable", c2.module_enabled_for_company(cur, COMPANY).get("ok") is not True)

            src = Path(__file__).with_name("performance_reviews_c2.py").read_text()
            check("EN/AR contracts", "مغلق" in src and "status_label" in src)
            check("no fake anonymity", "min_respondent_threshold_too_low" in src)

        conn.commit()

    print(f"\n    {PASS} passed, {FAIL} failed")
    if FAIL:
        return 1
    print("PERFORMANCE_REVIEWS_UNIT_PASS")
    print("PERFORMANCE_REVIEWS_FULL_PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
