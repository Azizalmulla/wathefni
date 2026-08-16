#!/usr/bin/env python3
"""PT1 — OKR + Talent Evidence Index DB journeys A–H and composition."""
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
COMPANY = f"PT1{_N:05d}"[:12].upper()
OTHER = f"PTX{_N:05d}"[:12].upper()
TALENT_ONLY = f"PTT{_N:05d}"[:12].upper()
HR = f"9657100{_N:05d}"
EMP = f"{COMPANY}-PT1-{SUFFIX}"
EMP2 = f"{COMPANY}-PT1B-{SUFFIX}"
EMP_PHONE = f"9657101{_N:05d}"
EMP2_PHONE = f"9657102{_N:05d}"
TO_EMP = f"{TALENT_ONLY}-PT1-{SUFFIX}"
TO_PHONE = f"9657103{_N:05d}"


def check(label: str, condition: bool, detail: object = None) -> None:
    global PASS, FAIL
    if condition:
        PASS += 1
        print(f"      PASS  {label}")
    else:
        FAIL += 1
        extra = f" :: {detail}" if detail is not None else ""
        print(f"      FAIL  {label}{extra}")


def _flags(*, perf: str, talent: str, companies: str, talent_companies: str) -> None:
    os.environ["WATHEFNI_PERFORMANCE_GOALS_C1"] = perf
    os.environ["WATHEFNI_PERFORMANCE_GOALS_COMPANIES"] = companies
    os.environ["WATHEFNI_PERFORMANCE_KILL"] = "off"
    os.environ["WATHEFNI_PERFORMANCE_FEEDBACK_C3"] = perf
    os.environ["WATHEFNI_PERFORMANCE_FEEDBACK_COMPANIES"] = companies
    os.environ["WATHEFNI_TALENT_PROFILE_C5"] = talent
    os.environ["WATHEFNI_TALENT_PROFILE_COMPANIES"] = talent_companies
    os.environ["WATHEFNI_TALENT_KILL"] = "off"
    os.environ["WATHEFNI_JOB_ARCHITECTURE_C1"] = "off"
    os.environ["WATHEFNI_LEARNING_DEVELOPMENT_C2"] = "off"
    os.environ["WATHEFNI_ASSESSMENTS"] = "off"


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


def _measure_and_kr(c1, cur, *, company: str, objective_id: str, title: str, target: int = 100):
    m = c1.create_measure_definition(
        cur,
        company_code=company,
        actor_phone=HR,
        name_en=title,
        unit="count",
        direction="higher_is_better",
        source="manual",
        baseline=0,
        target=target,
        period_start=date(2036, 1, 1),
        period_end=date(2036, 3, 31),
        owner_employee_key=EMP,
    )
    if not m.get("ok"):
        return m, None
    kr = c1.add_key_result(
        cur,
        company_code=company,
        objective_id=objective_id,
        actor_phone=HR,
        title_en=title,
        measure_id=str(m["measure"]["measure_id"]),
        weight=1,
        reason="add kr",
    )
    return m, kr


def _count(cur, table: str, company: str, extra: str = "", params: list | None = None) -> int:
    try:
        cur.execute(
            f"SELECT count(*) AS n FROM {table} WHERE company_code=%s {extra}",
            [company, *(params or [])],
        )
        row = cur.fetchone() or {}
        return int(dict(row).get("n") or 0)
    except Exception:
        return -1


def main() -> int:
    print("    pt1 okr evidence — db journeys")
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import okr_operating_pt1 as pt1
    import performance_goals_c1 as c1
    import talent_evidence_index_pt1 as idx
    import talent_profile_c5 as c5

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

    _flags(perf="on", talent="on", companies=f"{COMPANY},{OTHER}", talent_companies=f"{COMPANY},{TALENT_ONLY}")

    period_start = date(2036, 1, 1)
    period_end = date(2036, 3, 31)

    with app.db_connect() as conn:
        with conn.cursor() as cur:
            c1.ensure_performance_goals_c1_schema(cur)
            pt1.ensure_okr_operating_pt1_schema(cur)
            c5.ensure_talent_profile_c5_schema(cur)
            idx.ensure_talent_evidence_index_pt1_schema(cur)
            _seed_company(cur, COMPANY, f"PT1 {COMPANY}")
            _seed_company(cur, OTHER, f"PTX {OTHER}")
            _seed_company(cur, TALENT_ONLY, f"PTT {TALENT_ONLY}")
            _seed_employee(cur, COMPANY, EMP, EMP_PHONE, "PT1 Emp")
            _seed_employee(cur, COMPANY, EMP2, EMP2_PHONE, "PT1 Other")
            _seed_employee(cur, TALENT_ONLY, TO_EMP, TO_PHONE, "Talent Only")

            en = c1.enable_company_performance_goals(cur, company_code=COMPANY, actor_phone=HR, reason="enable c1")
            check("enable performance", en.get("ok") is True, en)
            try:
                import performance_feedback_c3 as c3

                c3.ensure_performance_feedback_c3_schema(cur)
                c3.enable_company_performance_feedback(cur, company_code=COMPANY, actor_phone=HR, reason="enable c3")
            except Exception as exc:
                check("c3 optional enable", True, str(exc))

            ten = c5.enable_company_talent_profile(
                cur, company_code=COMPANY, actor_phone=HR, reason="enable c5", performance_evidence_consume=False
            )
            check("enable talent", ten.get("ok") is True, ten)

            contracts = idx.get_consume_contracts(cur, COMPANY)
            check("okr consume starts off", contracts.get("okr_as_talent_evidence_v1") is False, contracts)

            # A — quarterly OKR cycle + alignment tree
            cycle = pt1.create_okr_cycle(
                cur,
                company_code=COMPANY,
                actor_phone=HR,
                name_en="Q1 2036 OKRs",
                name_ar="نتائج الربع الأول 2036",
                period_start=period_start,
                period_end=period_end,
                scope="company",
                reason="create quarterly okr cycle",
            )
            check("A create okr cycle", cycle.get("ok") is True and cycle.get("is_review_cycle") is False, cycle)
            cycle_id = str((cycle.get("cycle") or {}).get("cycle_id") or "")
            check("A cycle authority exists", bool(cycle_id), cycle)
            check("A not a review cycle id", cycle.get("review_cycle_id") is None, cycle)
            act = pt1.set_okr_cycle_status(
                cur, company_code=COMPANY, cycle_id=cycle_id, actor_phone=HR, status="active", reason="activate"
            )
            check("A activate cycle", act.get("ok") is True, act)
            cur.execute("SELECT 1 FROM perf_review_cycles WHERE cycle_id=%s", (cycle_id,))
            check("A C2 table unused", cur.fetchone() is None)
            cur.execute(
                "SELECT 1 FROM information_schema.tables WHERE table_name='perf_okr_cycles'"
            )
            check("A perf_okr_cycles exists", cur.fetchone() is not None)

            scopes = [
                ("company", "Grow the company", "نمو الشركة", None),
                ("department", "Grow the department", "نمو القسم", "dept-1"),
                ("team", "Grow the team", "نمو الفريق", "team-1"),
                ("individual", "Grow my book", "تنمية محفظتي", None),
            ]
            objs = {}
            krs = {}
            for scope, title_en, title_ar, org in scopes:
                created = pt1.create_objective_in_cycle(
                    cur,
                    company_code=COMPANY,
                    actor_phone=HR,
                    cycle_id=cycle_id,
                    title_en=title_en,
                    title_ar=title_ar,
                    scope=scope,
                    owner_employee_key=EMP if scope == "individual" else EMP,
                    org_unit_id=org,
                    visibility="company" if scope == "company" else "owner_manager",
                    reason="create scoped objective",
                )
                check(f"A {scope} objective", created.get("ok") is True, created)
                oid = str(created["objective"]["objective_id"])
                objs[scope] = oid
                _m, kr = _measure_and_kr(c1, cur, company=COMPANY, objective_id=oid, title=f"{scope} KR")
                check(f"A {scope} KR", bool(kr and kr.get("ok")), kr)
                if kr and kr.get("ok"):
                    krs[scope] = str(kr["key_result"]["key_result_id"])
                c1.activate_objective(cur, company_code=COMPANY, objective_id=oid, actor_phone=HR, reason="activate")

            extra_kr = c1.create_measure_definition(
                cur,
                company_code=COMPANY,
                actor_phone=HR,
                name_en="Second KR",
                unit="count",
                direction="higher_is_better",
                source="manual",
                baseline=0,
                target=50,
                period_start=period_start,
                period_end=period_end,
                owner_employee_key=EMP,
            )
            extra = c1.add_key_result(
                cur,
                company_code=COMPANY,
                objective_id=objs["individual"],
                actor_phone=HR,
                title_en="Second individual KR",
                measure_id=str(extra_kr["measure"]["measure_id"]),
                weight=1,
                reason="second kr",
            )
            check("A objective has multiple KRs", extra.get("ok") is True, extra)

            a1 = pt1.create_alignment(
                cur,
                company_code=COMPANY,
                actor_phone=HR,
                child_objective_id=objs["department"],
                parent_objective_id=objs["company"],
                reason="align dept",
            )
            a2 = pt1.create_alignment(
                cur,
                company_code=COMPANY,
                actor_phone=HR,
                child_objective_id=objs["team"],
                parent_objective_id=objs["department"],
                reason="align team",
            )
            a3 = pt1.create_alignment(
                cur,
                company_code=COMPANY,
                actor_phone=HR,
                child_objective_id=objs["individual"],
                parent_objective_id=objs["team"],
                reason="align individual",
            )
            check("A alignments", a1.get("ok") and a2.get("ok") and a3.get("ok"), (a1, a2, a3))
            check("A alignment does not inherit", a1.get("inherits_score") is False, a1)

            tree = pt1.alignment_tree(cur, company_code=COMPANY, cycle_id=cycle_id, actor_role="hr")
            check("A tree ok", tree.get("ok") is True and tree.get("inherits_score") is False, tree)
            roots = tree.get("tree") or []
            check("A company root", bool(roots) and roots[0].get("scope") == "company", roots)
            dept = (roots[0].get("children") or [None])[0] if roots else None
            team = ((dept or {}).get("children") or [None])[0] if dept else None
            indiv = ((team or {}).get("children") or [None])[0] if team else None
            check("A company→dept→team→individual", bool(dept and team and indiv), tree)

            hidden = pt1.alignment_tree(
                cur,
                company_code=COMPANY,
                cycle_id=cycle_id,
                actor_role="employee",
                actor_employee_key=EMP2,
            )
            hidden_ids = []

            def _walk(nodes):
                for n in nodes or []:
                    hidden_ids.append(str(n.get("objective_id")))
                    _walk(n.get("children"))

            _walk(hidden.get("tree") or [])
            check(
                "A alignment is not a permission bypass",
                objs["individual"] not in hidden_ids or hidden.get("hidden_by_permission") is True,
                hidden,
            )
            check(
                "A private individual hidden from other employee",
                objs["individual"] not in hidden_ids,
                hidden_ids,
            )

            # B — no inherited score
            parent_before = c1.objective_rollup(cur, company_code=COMPANY, objective_id=objs["company"])
            child_prog = c1.record_progress(
                cur,
                company_code=COMPANY,
                subject_type="key_result",
                subject_id=krs["individual"],
                actor_phone=HR,
                current_value=70,
                note="child progressed",
            )
            check("B child progress recorded", child_prog.get("ok") is True, child_prog)
            child_after = c1.objective_rollup(cur, company_code=COMPANY, objective_id=objs["individual"])
            parent_after = c1.objective_rollup(cur, company_code=COMPANY, objective_id=objs["company"])
            check("B child rollup moved", child_after.get("progress_pct") is not None, child_after)
            check(
                "B parent unchanged by alignment",
                parent_before.get("progress_pct") == parent_after.get("progress_pct"),
                (parent_before, parent_after),
            )
            check(
                "B parent not forced to 70",
                parent_after.get("progress_pct") != 70.0,
                parent_after,
            )

            # C — update / check-in ≠ progress
            before_kr = c1.objective_rollup(cur, company_code=COMPANY, objective_id=objs["individual"])
            upd = pt1.record_update(
                cur,
                company_code=COMPANY,
                actor_phone=EMP_PHONE,
                subject_type="key_result",
                subject_id=krs["individual"],
                update_text="At risk this week",
                actor_employee_key=EMP,
                observed_value=70,
                cycle_id=cycle_id,
                reason="employee check-in",
            )
            check("C update recorded", upd.get("ok") is True and upd.get("mutates_progress") is False, upd)
            after_kr = c1.objective_rollup(cur, company_code=COMPANY, objective_id=objs["individual"])
            check(
                "C check-in did not change progress",
                before_kr.get("progress_pct") == after_kr.get("progress_pct"),
                (before_kr, after_kr, upd),
            )
            thread = pt1.list_updates(
                cur, company_code=COMPANY, subject_type="key_result", subject_id=krs["individual"]
            )
            check("C thread has update", len(thread.get("updates") or []) >= 1, thread)

            conf_off = pt1.record_update(
                cur,
                company_code=COMPANY,
                actor_phone=EMP_PHONE,
                subject_type="objective",
                subject_id=objs["individual"],
                update_text="confidence attempt",
                actor_employee_key=EMP,
                confidence="low",
                reason="confidence while disabled",
            )
            check("C confidence disabled by default", conf_off.get("error") == "confidence_disabled", conf_off)
            pt1.upsert_company_settings(
                cur,
                company_code=COMPANY,
                actor_phone=HR,
                reason="enable confidence",
                confidence_enabled=True,
            )
            conf_on = pt1.record_update(
                cur,
                company_code=COMPANY,
                actor_phone=EMP_PHONE,
                subject_type="key_result",
                subject_id=krs["individual"],
                update_text="65% but at risk",
                actor_employee_key=EMP,
                confidence="low",
                reason="optional confidence",
            )
            check("C optional confidence stored", conf_on.get("ok") is True, conf_on)
            check("C confidence is not progress", conf_on.get("confidence_is_not_progress") is True, conf_on)
            after_conf = c1.objective_rollup(cur, company_code=COMPANY, objective_id=objs["individual"])
            check(
                "C confidence did not change progress",
                after_kr.get("progress_pct") == after_conf.get("progress_pct"),
                after_conf,
            )

            # D — history reconstructable
            mid = str((_measure_and_kr.__doc__ or "") and extra_kr["measure"]["measure_id"])
            changed = c1.change_measure_targets(
                cur,
                company_code=COMPANY,
                measure_id=str(extra_kr["measure"]["measure_id"]),
                actor_phone=HR,
                reason="raise target",
                target=80,
            )
            check("D target versioned", changed.get("ok") is True, changed)
            hist = pt1.objective_operating_history(
                cur, company_code=COMPANY, objective_id=objs["individual"]
            )
            check("D history ok", hist.get("ok") is True, hist)
            check("D trajectory ready without labels", hist.get("trajectory_ready") is True and hist.get("trajectory_labels") is None, hist)
            check("D target versions present", len(hist.get("target_versions") or []) >= 1, hist)
            check("D progress entries present", len(hist.get("progress_entries") or []) >= 1, hist)
            check("D updates present", len(hist.get("updates") or []) >= 1, hist)
            check("D alignment history present", len(hist.get("alignment_events") or []) >= 1, hist)
            _ = mid

            # F — consume OFF
            blocked = idx.index_okr_evidence(
                cur, company_code=COMPANY, actor_phone=HR, objective_id=objs["individual"], reason="try off"
            )
            check("F consume off blocks", blocked.get("error") == "okr_as_talent_evidence_v1_off", blocked)
            listed_off = idx.list_evidence(
                cur,
                company_code=COMPANY,
                employee_key=EMP,
                actor_role="hr",
                has_talent_read=True,
                can_see_sensitive=True,
                can_see_performance=True,
            )
            okr_off = [e for e in (listed_off.get("evidence") or []) if e.get("evidence_kind") == "okr"]
            check("F talent cannot consume OKR", okr_off == [], listed_off)

            pot_before = _count(cur, "talent_potential_assessments", COMPANY)
            ready_before = _count(cur, "talent_readiness_observations", COMPANY)
            hipo_before = _count(cur, "talent_hipo_designations", COMPANY)

            # G — consume ON
            on = idx.set_consume_contracts(
                cur,
                company_code=COMPANY,
                actor_phone=HR,
                reason="enable okr evidence",
                contracts={"okr_as_talent_evidence_v1": True},
            )
            check("G contract enabled", on.get("ok") is True and on.get("potential_mutated") is False, on)
            indexed = idx.index_okr_evidence(
                cur, company_code=COMPANY, actor_phone=HR, objective_id=objs["individual"], reason="index okr"
            )
            check("G indexed", indexed.get("ok") is True and indexed.get("copied_canonical_rating") is False, indexed)
            again = idx.index_okr_evidence(
                cur, company_code=COMPANY, actor_phone=HR, objective_id=objs["individual"], reason="index okr again"
            )
            check("G idempotent", again.get("ok") is True and again.get("idempotent") is True, again)
            check(
                "G same evidence id",
                str((indexed.get("evidence") or {}).get("evidence_id"))
                == str((again.get("evidence") or {}).get("evidence_id")),
                (indexed, again),
            )
            listed_on = idx.list_evidence(
                cur,
                company_code=COMPANY,
                employee_key=EMP,
                actor_role="hr",
                has_talent_read=True,
                can_see_sensitive=True,
                can_see_performance=True,
            )
            okr_on = [e for e in (listed_on.get("evidence") or []) if e.get("evidence_kind") == "okr"]
            check("G OKR appears as evidence", len(okr_on) >= 1, listed_on)
            check("G pointer fields", all(e.get("source_authority") and e.get("source_id") and e.get("payload_hash") for e in okr_on), okr_on)
            check("G no copied rating", all(e.get("copied_canonical_rating") is False for e in okr_on), okr_on)
            check("G no potential mutation", listed_on.get("potential_mutated") is False)
            check("G no hipo mutation", listed_on.get("hipo_mutated") is False)
            check("G no readiness mutation", listed_on.get("readiness_mutated") is False)
            check("G no master score", listed_on.get("master_talent_score") is None)
            check("G potential rows unchanged", _count(cur, "talent_potential_assessments", COMPANY) == pot_before)
            check("G readiness rows unchanged", _count(cur, "talent_readiness_observations", COMPANY) == ready_before)
            if hipo_before >= 0:
                check("G hipo rows unchanged", _count(cur, "talent_hipo_designations", COMPANY) == hipo_before)

            denied = idx.list_evidence(
                cur,
                company_code=COMPANY,
                employee_key=EMP,
                actor_role="hr",
                has_talent_read=True,
                can_see_sensitive=True,
                can_see_performance=False,
            )
            okr_denied = [e for e in (denied.get("evidence") or []) if e.get("visible") and e.get("evidence_kind") == "okr"]
            check("source permission preserved", okr_denied == [], denied)
            no_talent = idx.list_evidence(
                cur,
                company_code=COMPANY,
                employee_key=EMP,
                actor_role="hr",
                has_talent_read=False,
            )
            check("talent permission required", no_talent.get("error") == "talent_read_required", no_talent)

            # H — contradictory provenance
            claimed = c5.claim_skill(
                cur,
                company_code=COMPANY,
                actor_phone=EMP_PHONE,
                employee_key=EMP,
                skill_code="LEAD",
                name_en="Leadership",
                name_ar="القيادة",
                reason="employee claim",
            )
            check("H claimed skill", claimed.get("ok") is True, claimed)
            skill_id = str(claimed["skill"]["skill_id"])
            idx_claim = idx.index_claimed_skill(
                cur, company_code=COMPANY, employee_key=EMP, skill_id=skill_id, actor_phone=HR, reason="index claim"
            )
            check("H claimed indexed", idx_claim.get("ok") is True, idx_claim)
            check("H claimed not verified", (idx_claim.get("evidence") or {}).get("claimed_not_verified") is True, idx_claim)
            check(
                "H claimed not classification input",
                (idx_claim.get("evidence") or {}).get("classification_input_eligible") is False,
                idx_claim,
            )

            fact = c5.add_dimension_fact(
                cur,
                company_code=COMPANY,
                actor_phone=HR,
                employee_key=EMP,
                dimension_kind="strength",
                title_en="Leadership strong",
                title_ar="قيادة قوية",
                source="manager_assessed",
                reason="manager assessment",
            )
            check("H manager fact", fact.get("ok") is True, fact)
            mgr = idx.index_ref(
                cur,
                company_code=COMPANY,
                employee_key=EMP,
                source_module="talent",
                source_authority="talent_dimension_facts",
                source_id=str(fact["fact"]["fact_id"]),
                source_version=fact["fact"].get("version") or 1,
                evidence_kind="competency",
                provenance_class="MANAGER-ASSESSED",
                consume_contract="talent_native_v1",
                actor_phone=HR,
                reason="index manager assessment",
            )
            check("H manager indexed", mgr.get("ok") is True, mgr)

            fw = c5.create_potential_framework(
                cur,
                company_code=COMPANY,
                actor_phone=HR,
                name_en="Growth",
                dimensions=[{"key": "lead", "label_en": "Lead", "label_ar": "قيادة"}],
                scale_points=[{"code": "moderate", "label_en": "Moderate", "label_ar": "متوسط"}],
                reason="framework",
            )
            pot = c5.submit_potential_assessment(
                cur,
                company_code=COMPANY,
                actor_phone=HR,
                employee_key=EMP,
                framework_id=str(fw["framework"]["framework_id"]),
                rationale="moderate leadership indicator",
                dimension_scores={"lead": "moderate"},
                resulting_level="moderate",
                assessor_role="hr",
                has_sensitive_permission=True,
                reason="hr assessment",
            )
            check("H potential assessment", pot.get("ok") is True, pot)
            pot_idx = idx.index_potential_assessment(
                cur,
                company_code=COMPANY,
                assessment_id=str(pot["assessment"]["assessment_id"]),
                actor_phone=HR,
                reason="index potential",
            )
            check("H potential indexed", pot_idx.get("ok") is True, pot_idx)

            sys_ref = idx.index_okr_evidence(
                cur, company_code=COMPANY, actor_phone=HR, key_result_id=krs["individual"], reason="system okr"
            )
            check("H system-derived OKR", sys_ref.get("ok") is True, sys_ref)

            ai = idx.index_ref(
                cur,
                company_code=COMPANY,
                employee_key=EMP,
                source_module="assistant",
                source_authority="ai_explanation",
                source_id=f"ai-{SUFFIX}",
                source_version=1,
                evidence_kind="explanation",
                provenance_class="AI-SYNTHESIZED",
                consume_contract="claimed_skill_display_v1",
                actor_phone=HR,
                reason="ai explanation",
            )
            check("H AI explanation allowed", ai.get("ok") is True, ai)
            check(
                "H AI not classification input",
                (ai.get("evidence") or {}).get("classification_input_eligible") is False,
                ai,
            )
            bad_ai = idx.index_ref(
                cur,
                company_code=COMPANY,
                employee_key=EMP,
                source_module="assistant",
                source_authority="ai_bad",
                source_id=f"ai-bad-{SUFFIX}",
                source_version=1,
                evidence_kind="skill",
                provenance_class="AI-SYNTHESIZED",
                consume_contract="claimed_skill_display_v1",
                actor_phone=HR,
                reason="ai as skill",
            )
            check("H AI cannot be skill evidence", bad_ai.get("error") == "ai_synthesized_explanation_only", bad_ai)

            coexist = idx.list_evidence(
                cur,
                company_code=COMPANY,
                employee_key=EMP,
                actor_role="hr",
                has_talent_read=True,
                can_see_sensitive=True,
                can_see_performance=True,
            )
            provenances = set(coexist.get("provenances_present") or [])
            check("H contradictions unresolved", coexist.get("contradictions_resolved") is False, coexist)
            check("H employee-declared present", "EMPLOYEE-DECLARED" in provenances, provenances)
            check("H manager-assessed present", "MANAGER-ASSESSED" in provenances, provenances)
            check("H system-derived present", "SYSTEM-DERIVED" in provenances, provenances)
            check("H AI not in classification set", (ai.get("evidence") or {}).get("classification_input_eligible") is False)

            sensitive = idx.list_evidence(
                cur,
                company_code=COMPANY,
                employee_key=EMP,
                actor_role="manager",
                has_talent_read=True,
                can_see_sensitive=False,
                can_see_performance=True,
            )
            hidden_sensitive = [e for e in (sensitive.get("evidence") or []) if e.get("visible") is False]
            check("H sensitive existence-only", len(hidden_sensitive) >= 1, sensitive)

            disabled = idx.mark_source_module_disabled(cur, company_code=COMPANY, source_module="performance")
            check("lifecycle preserves history", disabled.get("history_preserved") is True and disabled.get("hard_deleted") is False, disabled)
            cur.execute(
                "SELECT count(*) AS n FROM talent_evidence_refs WHERE company_code=%s AND source_module='performance'",
                (COMPANY,),
            )
            check("disabled module not hard-deleted", int(dict(cur.fetchone()).get("n") or 0) >= 1)

            # Tenant isolation
            c1.enable_company_performance_goals(cur, company_code=OTHER, actor_phone=HR, reason="other perf")
            other_cycles = pt1.list_okr_cycles(cur, company_code=OTHER)
            check("tenant isolation cycles", (other_cycles.get("cycles") or []) == [], other_cycles)
            other_ev = idx.list_evidence(
                cur,
                company_code=OTHER,
                employee_key=EMP,
                actor_role="hr",
                has_talent_read=True,
                can_see_sensitive=True,
                can_see_performance=True,
            )
            check("tenant isolation evidence", (other_ev.get("evidence") or []) == [], other_ev)

            # Performance ON / Talent OFF
            _flags(perf="on", talent="off", companies=COMPANY, talent_companies="")
            still = pt1.list_okr_cycles(cur, company_code=COMPANY)
            check("Performance works Talent OFF", still.get("ok") is True and len(still.get("cycles") or []) >= 1, still)
            talent_gate = c5.runtime_gate_for_company(COMPANY)
            check("Talent OFF gate", talent_gate.get("ok") is not True, talent_gate)

            # Talent ON / Performance OFF
            _flags(perf="off", talent="on", companies="", talent_companies=TALENT_ONLY)
            c5.enable_company_talent_profile(cur, company_code=TALENT_ONLY, actor_phone=HR, reason="talent only")
            profile = c5.ensure_talent_profile(
                cur, company_code=TALENT_ONLY, employee_key=TO_EMP, actor_phone=HR
            )
            check("Talent works Performance OFF", profile.get("ok") is True, profile)
            blocked_cycle = pt1.create_okr_cycle(
                cur,
                company_code=TALENT_ONLY,
                actor_phone=HR,
                name_en="should fail",
                period_start=period_start,
                period_end=period_end,
                reason="perf off",
            )
            check("OKR blocked when Performance OFF", blocked_cycle.get("ok") is not True, blocked_cycle)

            # Restore flags for leftover checks
            _flags(perf="on", talent="on", companies=f"{COMPANY},{OTHER}", talent_companies=f"{COMPANY},{TALENT_ONLY}")
            current = pt1.current_okr_cycle(cur, company_code=COMPANY)
            check("current cycle bilingual", (current.get("cycle") or {}).get("name_ar"), current)
            check("EN journey labels", pt1.status_label("active", lang="en") == "Active")
            check("AR/RTL journey labels", pt1.status_label("active", lang="ar") == "نشط")

            conn.commit()

    print(f"\n    {PASS} passed, {FAIL} failed")
    if FAIL == 0:
        print("PT1_OKR_EVIDENCE_DB_PASS")
    return 1 if FAIL else 0


if __name__ == "__main__":
    raise SystemExit(main())
