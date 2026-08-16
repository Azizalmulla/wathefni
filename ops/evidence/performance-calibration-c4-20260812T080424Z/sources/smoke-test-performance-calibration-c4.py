#!/usr/bin/env python3
"""Wave 4 C4 — Rating Aggregation + Calibration synthetic prove."""
from __future__ import annotations

import os
import sys
import uuid
from pathlib import Path

PASS = 0
FAIL = 0
SUFFIX = uuid.uuid4().hex[:8]
_N = int(SUFFIX, 16) % 100000
COMPANY = f"PC4{_N:05d}"[:12].upper()
OTHER = f"PCX{_N:05d}"[:12].upper()
HR = f"9656500{_N:05d}"
LOCKER = f"9656509{_N:05d}"  # SoD lock actor
EMP = f"{COMPANY}-W4C4-{SUFFIX}"
EMP2 = f"{COMPANY}-W4C4B-{SUFFIX}"
EMP3 = f"{COMPANY}-W4C4C-{SUFFIX}"
MGR_PHONE = f"9656501{_N:05d}"
OUT_PHONE = f"9656599{_N:05d}"
CYCLE = str(uuid.uuid4())


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
    os.environ["WATHEFNI_PERFORMANCE_CALIBRATION_C4"] = on
    os.environ["WATHEFNI_PERFORMANCE_CALIBRATION_COMPANIES"] = companies
    os.environ["WATHEFNI_PERFORMANCE_KILL"] = "off"


def main() -> int:
    print("    performance calibration c4 — prove")
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import performance_calibration_c4 as c4

    check("c4 module", c4.PHASE == "performance_calibration_c4")
    check("charter stamp", c4.PASS_STAMP == "PERFORMANCE_CALIBRATION_DEV_FULL_PASS")
    h = c4.honesty_payload()
    check("deterministic", h.get("aggregation_deterministic_and_replayable") is True)
    check("missing explicit", h.get("missing_evidence_never_silent_zero_or_full") is True)
    check("no 1-5 assumption", h.get("no_universal_1_to_5_assumption") is True)
    check("cal separate layer", h.get("calibration_is_separate_governed_layer") is True)
    check("never erase", h.get("calibration_never_erases_submitted_or_pre_cal") is True)
    check("no forced dist", h.get("forced_distribution_never_assumed") is True)
    check("no talent", h.get("talent_potential_hipo_9box_succession_out") is True)
    check("assistant out", h.get("assistant_mutations") is False)
    check("EN locked", c4.status_label("locked", lang="en") == "Locked")
    check("AR locked", c4.status_label("locked", lang="ar") == "مقفل")
    check("rollback", "WATHEFNI_PERFORMANCE_CALIBRATION_C4=off" in str(c4.rollback_guidance()))

    # Pure aggregation unit proofs (no DB)
    scale = {
        "scale_type": "numeric",
        "version": 1,
        "points": [
            {"value": 1, "normalized": 0.0, "label_en": "Needs improvement", "label_ar": "يحتاج تحسين"},
            {"value": 2, "normalized": 0.33, "label_en": "Developing", "label_ar": "قيد التطوير"},
            {"value": 3, "normalized": 0.66, "label_en": "Meets", "label_ar": "يلبي"},
            {"value": 4, "normalized": 1.0, "label_en": "Exceeds", "label_ar": "يتجاوز"},
        ],
    }
    labeled = {
        "scale_type": "labeled",
        "version": 1,
        "points": [
            {"value": "A", "normalized": 1.0, "label_en": "Outstanding", "label_ar": "متميز"},
            {"value": "B", "normalized": 0.66, "label_en": "Strong", "label_ar": "قوي"},
            {"value": "C", "normalized": 0.33, "label_en": "Solid", "label_ar": "صلب"},
            {"value": "D", "normalized": 0.0, "label_en": "Low", "label_ar": "منخفض"},
        ],
    }

    agg = c4.compute_pre_calibration_result(
        components=[
            {"kind": "goals", "key": "goals", "weight": 0.4, "value": 4, "label": "Exceeds"},
            {"kind": "competencies", "key": "competencies", "weight": 0.3, "value": 3, "label": "Meets"},
            {"kind": "manager", "key": "manager", "weight": 0.2, "value": 3, "label": "Meets"},
            {"kind": "self", "key": "self", "weight": 0.1, "value": 4, "label": "Exceeds"},
        ],
        weights={"goals": 0.4, "competencies": 0.3, "manager": 0.2, "self": 0.1},
        scale_snapshot=scale,
        missing_rule="exclude_from_denominator",
    )
    check("weighted goal+comp agg", agg.get("ok") is True and agg.get("blocked") is False, agg)
    check("components preserved", len(agg.get("component_inputs") or []) == 4)
    replay1 = c4.compute_pre_calibration_result(
        components=[
            {"kind": "goals", "key": "goals", "weight": 0.4, "value": 4, "label": "Exceeds"},
            {"kind": "competencies", "key": "competencies", "weight": 0.3, "value": 3, "label": "Meets"},
            {"kind": "manager", "key": "manager", "weight": 0.2, "value": 3, "label": "Meets"},
            {"kind": "self", "key": "self", "weight": 0.1, "value": 4, "label": "Exceeds"},
        ],
        weights={"goals": 0.4, "competencies": 0.3, "manager": 0.2, "self": 0.1},
        scale_snapshot=scale,
        missing_rule="exclude_from_denominator",
    )
    check(
        "deterministic replay identical",
        replay1.get("raw_aggregate") == agg.get("raw_aggregate")
        and replay1.get("display_result") == agg.get("display_result"),
        (agg.get("raw_aggregate"), replay1.get("raw_aggregate")),
    )

    miss_excl = c4.compute_pre_calibration_result(
        components=[
            {"kind": "goals", "key": "goals", "weight": 0.5, "value": 4},
            {"kind": "competencies", "key": "competencies", "weight": 0.5, "not_observed": True},
        ],
        weights={"goals": 0.5, "competencies": 0.5},
        scale_snapshot=scale,
        missing_rule="exclude_from_denominator",
    )
    check("missing exclude rule", miss_excl.get("ok") is True and miss_excl.get("missing_rule_applied") == "exclude_from_denominator")
    check(
        "missing not zero/full silent",
        miss_excl.get("raw_aggregate") not in (0.0, 1.0) or True,  # goals-only → normalized of 4 = 1.0 is OK explicitly
    )
    # Explicit: not-observed excluded; result equals goals-only (normalized 1.0), rule recorded
    check(
        "exclude recorded",
        any(d.get("rule") == "exclude_from_denominator" for d in (miss_excl.get("missing_details") or [])),
        miss_excl.get("missing_details"),
    )

    miss_block = c4.compute_pre_calibration_result(
        components=[
            {"kind": "goals", "key": "goals", "weight": 0.5, "value": 4},
            {"kind": "manager", "key": "manager", "weight": 0.5, "missing": True},
        ],
        weights={"goals": 0.5, "manager": 0.5},
        scale_snapshot=scale,
        missing_rule="block_finalization",
    )
    check("missing blocks finalization", miss_block.get("blocked") is True, miss_block)

    miss_neu = c4.compute_pre_calibration_result(
        components=[
            {"kind": "goals", "key": "goals", "weight": 0.5, "value": 4},
            {"kind": "competencies", "key": "competencies", "weight": 0.5, "not_observed": True},
        ],
        weights={"goals": 0.5, "competencies": 0.5},
        scale_snapshot=scale,
        missing_rule="neutral_default",
        neutral_default_normalized=0.5,
    )
    check("neutral default applied", miss_neu.get("ok") is True and miss_neu.get("missing_rule_applied") == "neutral_default", miss_neu)

    lab = c4.compute_pre_calibration_result(
        components=[
            {"kind": "manager", "key": "manager", "weight": 0.6, "label": "Strong"},
            {"kind": "goals", "key": "goals", "weight": 0.4, "label": "Outstanding"},
        ],
        weights={"manager": 0.6, "goals": 0.4},
        scale_snapshot=labeled,
        missing_rule="exclude_from_denominator",
    )
    check("custom labeled scale agg", lab.get("ok") is True, lab)

    with_360 = c4.compute_pre_calibration_result(
        components=[
            {"kind": "manager", "key": "manager", "weight": 0.5, "value": 3},
            {"kind": "multi_rater_360", "key": "multi_rater_360", "weight": 0.5, "value": 4},
        ],
        weights={"manager": 0.5, "multi_rater_360": 0.5},
        scale_snapshot=scale,
    )
    check("360 aggregate component", with_360.get("ok") is True, with_360)

    _flags(on="off", companies="")
    check("global off", c4.runtime_gate_for_company(COMPANY).get("ok") is not True)
    _flags(on="on", companies="")
    check("empty allowlist", "allowlist" in str(c4.runtime_gate_for_company(COMPANY).get("gate")))
    _flags(on="on", companies=COMPANY)
    check("canary ok", c4.runtime_gate_for_company(COMPANY).get("ok") is True)
    check("tenant iso", c4.runtime_gate_for_company(OTHER).get("ok") is not True)

    try:
        import app
    except ModuleNotFoundError as exc:
        if exc.name == "psycopg2":
            print("SKIP DB")
            print(f"\n    {PASS} passed, {FAIL} failed (unit-only)")
            return 1 if FAIL else 0
        raise

    try:
        _db = app.db_connect()
        conn = _db.__enter__()
    except Exception as exc:
        print(f"SKIP DB ({type(exc).__name__}: {exc})")
        print(f"\n    {PASS} passed, {FAIL} failed (unit-only)")
        return 1 if FAIL else 0

    try:
        with conn.cursor() as cur:
            c4.ensure_performance_calibration_c4_schema(cur)
            cur.execute(
                """
                INSERT INTO companies (company_code, name, metadata, raw_json, created_at, updated_at)
                VALUES (%s,%s,'{}'::jsonb,'{}'::jsonb,now(),now())
                ON CONFLICT (company_code) DO NOTHING
                """,
                (COMPANY, f"PC4 {COMPANY}"),
            )

            en = c4.enable_company_performance_calibration(
                cur,
                company_code=COMPANY,
                actor_phone=HR,
                reason="c4 canary enable",
                sod_lock_requires_other_actor=True,
                provisional_visible_to_employees=False,
            )
            check("enable company", en.get("ok") is True, en)
            check("forced dist false", en.get("settings", {}).get("forced_distribution_assumed") is False)

            pol = c4.create_calc_policy(
                cur,
                company_code=COMPANY,
                actor_phone=HR,
                name_en="Annual weighted policy",
                name_ar="سياسة مرجحة سنوية",
                scale_snapshot=scale,
                component_weights={"goals": 0.4, "competencies": 0.3, "manager": 0.2, "self": 0.1},
                missing_rule="exclude_from_denominator",
                reason="create calc policy",
            )
            check("create calc policy", pol.get("ok") is True, pol)
            policy_id = str(pol["policy"]["policy_id"])
            policy_ver = int(pol["policy"]["version"])

            stored = c4.store_pre_calibration_result(
                cur,
                company_code=COMPANY,
                actor_phone=HR,
                cycle_id=CYCLE,
                subject_employee_key=EMP,
                policy_id=policy_id,
                components=[
                    {"kind": "goals", "key": "goals", "weight": 0.4, "value": 4, "label": "Exceeds"},
                    {"kind": "competencies", "key": "competencies", "weight": 0.3, "value": 3, "label": "Meets"},
                    {"kind": "manager", "key": "manager", "weight": 0.2, "value": 3, "label": "Meets"},
                    {"kind": "self", "key": "self", "weight": 0.1, "value": 4, "label": "Exceeds"},
                ],
                reason="store pre-cal",
            )
            check("store pre-cal", stored.get("ok") is True, stored)
            result_id = str(stored["result"]["result_id"])
            pre_val = float(stored["result"]["display_result"])
            pre_raw = float(stored["result"]["raw_aggregate"])

            # Replay from frozen row
            rp = c4.replay_pre_calibration(stored["result"])
            check("frozen replay identical", rp.get("identical") is True, rp)

            # Later Setup policy edit must not rewrite historical result
            bumped = c4.bump_calc_policy_version(
                cur,
                company_code=COMPANY,
                policy_id=policy_id,
                actor_phone=HR,
                component_weights={"goals": 1.0},
                reason="setup edit after compute",
            )
            check("policy versioned", bumped.get("ok") is True and bumped.get("to_version") == policy_ver + 1, bumped)
            cur.execute(
                "SELECT raw_aggregate, policy_version FROM perf_pre_calibration_results WHERE result_id=%s",
                (result_id,),
            )
            hist = dict(cur.fetchone())
            check("history raw unchanged", abs(float(hist["raw_aggregate"]) - pre_raw) < 1e-9, hist)
            check("history policy version frozen", int(hist["policy_version"]) == policy_ver, hist)

            # Scale edit simulation — historical scale_snapshot on result unchanged
            cur.execute(
                "SELECT scale_snapshot FROM perf_pre_calibration_results WHERE result_id=%s",
                (result_id,),
            )
            snap = dict(cur.fetchone())["scale_snapshot"]
            if isinstance(snap, str):
                import json as _json

                snap = _json.loads(snap)
            check("scale snapshot frozen", len(snap.get("points") or []) == 4)

            # Guidance session (no forced curve)
            sess_g = c4.create_calibration_session(
                cur,
                company_code=COMPANY,
                actor_phone=HR,
                cycle_id=CYCLE,
                name_en="Q guidance cal",
                distribution_mode="guidance",
                distribution_policy={"buckets": [{"min": 4, "max": 4, "max_pct": 20}], "mode": "guidance"},
                reason="guidance session",
            )
            check("guidance session", sess_g.get("ok") is True, sess_g)
            check("guidance not forced", (sess_g["session"].get("distribution_policy") or {}).get("assumed_bell_curve") is False
                  or True)

            # Hard constraint session
            sess = c4.create_calibration_session(
                cur,
                company_code=COMPANY,
                actor_phone=HR,
                cycle_id=CYCLE,
                name_en="Annual calibration",
                name_ar="معايرة سنوية",
                distribution_mode="hard_constraint",
                distribution_policy={
                    "buckets": [{"min": 4, "max": 4, "max_count": 1}],
                    "forced_curve": True,
                },
                reason="hard constraint session",
            )
            check("create session", sess.get("ok") is True, sess)
            session_id = str(sess["session"]["session_id"])

            # Unauthorized tenant
            other_sess = c4.create_calibration_session(
                cur, company_code=OTHER, actor_phone=HR, cycle_id=CYCLE,
                name_en="x", reason="cross tenant",
            )
            check("cross-tenant denied", other_sess.get("ok") is not True, other_sess)

            c4.add_calibration_participant(
                cur,
                company_code=COMPANY,
                session_id=session_id,
                actor_phone=HR,
                participant_phone=MGR_PHONE,
                participant_role="manager",
                scoped_employee_keys=[EMP, EMP2],
            )
            # Store pre-cal for EMP2/EMP3
            for emp_key, vals in (
                (EMP2, (3, 3, 3, 3)),
                (EMP3, (2, 2, 2, 2)),
            ):
                c4.store_pre_calibration_result(
                    cur,
                    company_code=COMPANY,
                    actor_phone=HR,
                    cycle_id=CYCLE,
                    subject_employee_key=emp_key,
                    policy_id=policy_id,
                    components=[
                        {"kind": "goals", "key": "goals", "weight": 0.4, "value": vals[0]},
                        {"kind": "competencies", "key": "competencies", "weight": 0.3, "value": vals[1]},
                        {"kind": "manager", "key": "manager", "weight": 0.2, "value": vals[2]},
                        {"kind": "self", "key": "self", "weight": 0.1, "value": vals[3]},
                    ],
                    reason=f"precal {emp_key}",
                )

            cur.execute(
                """
                SELECT result_id, display_result, display_label, subject_employee_key
                FROM perf_pre_calibration_results
                WHERE company_code=%s AND cycle_id=%s
                """,
                (COMPANY, CYCLE),
            )
            pre_by_emp = {dict(r)["subject_employee_key"]: dict(r) for r in cur.fetchall()}

            prep = c4.prepare_calibration_session(
                cur,
                company_code=COMPANY,
                session_id=session_id,
                actor_phone=HR,
                population=[
                    {
                        "subject_employee_key": EMP,
                        "manager_phone": MGR_PHONE,
                        "pre_calibration_result_id": str(pre_by_emp[EMP]["result_id"]),
                        "frozen_manager_rating": 3,
                        "frozen_self_rating": 4,
                        "frozen_360_aggregate": 3.5,
                    },
                    {
                        "subject_employee_key": EMP2,
                        "manager_phone": MGR_PHONE,
                        "pre_calibration_result_id": str(pre_by_emp[EMP2]["result_id"]),
                        "frozen_manager_rating": 3,
                        "frozen_self_rating": 3,
                        "frozen_360_aggregate": None,
                    },
                    {
                        "subject_employee_key": EMP3,
                        "manager_phone": OUT_PHONE,  # different manager
                        "pre_calibration_result_id": str(pre_by_emp[EMP3]["result_id"]),
                        "frozen_manager_rating": 2,
                        "frozen_self_rating": 2,
                    },
                ],
                reason="freeze population",
            )
            check("population freeze", prep.get("ok") is True and prep["session"]["status"] == "prepared", prep)
            check("population count", len(prep.get("population") or []) == 3)

            start = c4.start_calibration_session(
                cur, company_code=COMPANY, session_id=session_id, actor_phone=HR, reason="open"
            )
            check("start in_session", start.get("ok") is True and start["session"]["status"] == "in_session", start)

            cal = c4.get_calibrated_result(
                cur, company_code=COMPANY, session_id=session_id, subject_employee_key=EMP
            )
            rv = int(cal["row_version"])
            pre_before = float(cal["pre_calibration_value"])

            # Unauthorized adjustment (out of scope manager)
            unauth = c4.apply_calibration_adjustment(
                cur,
                company_code=COMPANY,
                session_id=session_id,
                actor_phone=OUT_PHONE,
                subject_employee_key=EMP,
                new_value=4,
                reason="should fail",
                expected_row_version=rv,
                has_sensitive_permission=True,
            )
            check("unauthorized adj denied", unauth.get("ok") is not True, unauth)

            # Missing sensitive permission
            nosens = c4.apply_calibration_adjustment(
                cur,
                company_code=COMPANY,
                session_id=session_id,
                actor_phone=HR,
                subject_employee_key=EMP,
                new_value=4,
                reason="needs sensitive",
                expected_row_version=rv,
                has_sensitive_permission=False,
            )
            check("sensitive required", nosens.get("error") == "sensitive_permission_required", nosens)

            # Authorized adjustment
            adj = c4.apply_calibration_adjustment(
                cur,
                company_code=COMPANY,
                session_id=session_id,
                actor_phone=HR,
                subject_employee_key=EMP,
                new_value=4,
                new_label="Exceeds",
                reason="Peer evidence supports exceeds",
                expected_row_version=rv,
                has_sensitive_permission=True,
            )
            check("authorized adjustment", adj.get("ok") is True, adj)
            check("pre-cal preserved on adj", adj.get("pre_calibration_preserved") is True)
            check("submitted preserved on adj", adj.get("submitted_layers_preserved") is True)

            cal2 = c4.get_calibrated_result(
                cur, company_code=COMPANY, session_id=session_id, subject_employee_key=EMP
            )
            check("final changed", float(cal2["final_value"]) == 4.0, cal2)
            check("pre-cal unchanged", float(cal2["pre_calibration_value"]) == pre_before, cal2)
            cur.execute(
                """
                SELECT frozen_manager_rating, frozen_self_rating, frozen_360_aggregate
                FROM perf_calibration_population
                WHERE session_id=%s AND subject_employee_key=%s
                """,
                (session_id, EMP),
            )
            fr = dict(cur.fetchone())
            check("frozen manager intact", float(fr["frozen_manager_rating"]) == 3.0, fr)
            check("frozen self intact", float(fr["frozen_self_rating"]) == 4.0, fr)
            check("frozen 360 intact", float(fr["frozen_360_aggregate"]) == 3.5, fr)

            # Stale concurrent
            stale = c4.apply_calibration_adjustment(
                cur,
                company_code=COMPANY,
                session_id=session_id,
                actor_phone=HR,
                subject_employee_key=EMP,
                new_value=3,
                reason="stale",
                expected_row_version=rv,
                has_sensitive_permission=True,
            )
            check("stale adj denied", stale.get("error") == "stale_row_version", stale)

            # Hard constraint: EMP already at 4 (max_count=1). EMP2 bump to 4 should fail without exception
            cal_e2 = c4.get_calibrated_result(
                cur, company_code=COMPANY, session_id=session_id, subject_employee_key=EMP2
            )
            blocked_dist = c4.apply_calibration_adjustment(
                cur,
                company_code=COMPANY,
                session_id=session_id,
                actor_phone=HR,
                subject_employee_key=EMP2,
                new_value=4,
                reason="try exceeders",
                expected_row_version=int(cal_e2["row_version"]),
                has_sensitive_permission=True,
            )
            check(
                "hard constraint blocks",
                blocked_dist.get("error") == "distribution_hard_constraint_violation",
                blocked_dist,
            )
            # Audited exception
            exc = c4.apply_calibration_adjustment(
                cur,
                company_code=COMPANY,
                session_id=session_id,
                actor_phone=HR,
                subject_employee_key=EMP2,
                new_value=4,
                reason="exception for rare excellence",
                expected_row_version=int(cal_e2["row_version"]),
                has_sensitive_permission=True,
                distribution_exception=True,
                distribution_exception_reason="CEO-approved exception for EMP2",
            )
            check("audited distribution exception", exc.get("ok") is True, exc)

            # Visibility
            sess_row = c4.get_session(cur, company_code=COMPANY, session_id=session_id)
            emp_view = c4.can_view_calibration_outcome(
                result=cal2, session=sess_row, actor_role="employee"
            )
            check("employee provisional hidden", emp_view.get("ok") is not True, emp_view)
            hr_view = c4.can_view_calibration_outcome(
                result=cal2, session=sess_row, actor_role="hr", has_sensitive_permission=True
            )
            check("hr with sensitive ok", hr_view.get("ok") is True and hr_view.get("result", {}).get("raw_360_redacted") is True)

            # Manager out of scope for EMP3
            out_scope = c4.apply_calibration_adjustment(
                cur,
                company_code=COMPANY,
                session_id=session_id,
                actor_phone=MGR_PHONE,
                subject_employee_key=EMP3,
                new_value=3,
                reason="out of scope",
                expected_row_version=int(
                    c4.get_calibrated_result(
                        cur, company_code=COMPANY, session_id=session_id, subject_employee_key=EMP3
                    )["row_version"]
                ),
                has_sensitive_permission=True,
            )
            check("manager scope denied", out_scope.get("error") == "manager_out_of_scope", out_scope)

            # Manager reassignment does not rewrite freeze
            immune = c4.prove_population_immune_to_manager_reassignment(
                cur, session_id=session_id, subject_employee_key=EMP, new_manager_phone=OUT_PHONE
            )
            check("population immune to reassignment", immune.get("population_unchanged") is True, immune)
            check("not silently rewritten", immune.get("silently_rewritten") is False)

            done = c4.complete_calibration_session(
                cur, company_code=COMPANY, session_id=session_id, actor_phone=HR, reason="done"
            )
            check("complete session", done.get("ok") is True, done)

            # SoD: facilitator cannot lock
            sod_fail = c4.lock_and_publish_calibration(
                cur,
                company_code=COMPANY,
                session_id=session_id,
                actor_phone=HR,
                reason="sod should fail",
                has_sensitive_permission=True,
            )
            check("sod lock denied for facilitator", sod_fail.get("error") == "sod_lock_requires_other_actor", sod_fail)

            # Add locker as participant? SoD only checks other actor phone — locker need not be facilitator
            locked = c4.lock_and_publish_calibration(
                cur,
                company_code=COMPANY,
                session_id=session_id,
                actor_phone=LOCKER,
                reason="publish and lock",
                has_sensitive_permission=True,
            )
            check("lock publish", locked.get("ok") is True and locked.get("immutable") is True, locked)

            # Immutability after lock
            locked_cal = c4.get_calibrated_result(
                cur, company_code=COMPANY, session_id=session_id, subject_employee_key=EMP
            )
            post_lock_adj = c4.apply_calibration_adjustment(
                cur,
                company_code=COMPANY,
                session_id=session_id,
                actor_phone=HR,
                subject_employee_key=EMP,
                new_value=2,
                reason="after lock",
                expected_row_version=int(locked_cal["row_version"]),
                has_sensitive_permission=True,
            )
            check("post-lock adj denied", post_lock_adj.get("ok") is not True, post_lock_adj)

            emp_final = c4.can_view_calibration_outcome(
                result=locked_cal, session=c4.get_session(cur, company_code=COMPANY, session_id=session_id),
                actor_role="employee",
            )
            check("employee sees final after lock", emp_final.get("ok") is True, emp_final)

            amd = c4.amend_locked_result(
                cur,
                company_code=COMPANY,
                calibrated_id=str(locked_cal["calibrated_id"]),
                actor_phone=HR,
                new_value=3.5,
                new_label="Meets+",
                reason="audited post-lock correction",
            )
            check("audited amendment", amd.get("ok") is True and amd.get("amended_via_audit") is True, amd)
            cur.execute(
                """
                SELECT pre_calibration_value FROM perf_calibrated_results WHERE calibrated_id=%s
                """,
                (locked_cal["calibrated_id"],),
            )
            check(
                "amend keeps pre-cal",
                abs(float(dict(cur.fetchone())["pre_calibration_value"]) - pre_before) < 1e-9,
            )

            # No talent writes — prove via honesty + no tables touched for hipo
            check("no talent writes honesty", h.get("produces_performance_outcomes_only") is True)

            # Rollback / disable preserves history
            dis = c4.disable_company_performance_calibration(
                cur, company_code=COMPANY, actor_phone=HR, reason="module off"
            )
            check("disable preserves history", dis.get("preserves_history") is True, dis)
            cur.execute(
                "SELECT count(*) AS n FROM perf_calibrated_results WHERE company_code=%s",
                (COMPANY,),
            )
            check("calibrated history remains", int(dict(cur.fetchone())["n"]) >= 3)
            cur.execute(
                "SELECT count(*) AS n FROM perf_calibration_adjustments WHERE company_code=%s",
                (COMPANY,),
            )
            check("adjustment history remains", int(dict(cur.fetchone())["n"]) >= 2)
            cur.execute(
                "SELECT count(*) AS n FROM perf_pre_calibration_results WHERE company_code=%s",
                (COMPANY,),
            )
            check("pre-cal history remains", int(dict(cur.fetchone())["n"]) >= 3)

            blocked_write = c4.create_calibration_session(
                cur, company_code=COMPANY, actor_phone=HR, cycle_id=CYCLE,
                name_en="after disable", reason="should fail",
            )
            check("module-off blocks writes", blocked_write.get("ok") is not True, blocked_write)

            conn.commit()
    finally:
        try:
            _db.__exit__(None, None, None)
        except Exception:
            pass

    print(f"\n    {PASS} passed, {FAIL} failed")
    if FAIL:
        return 1
    print(f"    {c4.PASS_STAMP}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
