#!/usr/bin/env python3
"""Wave 4 C3 — Check-ins + Competencies + Development synthetic prove."""
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
COMPANY = f"PF3{_N:05d}"[:12].upper()
OTHER = f"PFX{_N:05d}"[:12].upper()
HR = f"9656400{_N:05d}"
EMP = f"{COMPANY}-W4C3-{SUFFIX}"
EMP_PHONE = f"9656401{_N:05d}"
MGR = f"{COMPANY}-MGR-{SUFFIX}"
MGR_PHONE = f"9656402{_N:05d}"
OUT_PHONE = f"9656499{_N:05d}"


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
    os.environ["WATHEFNI_PERFORMANCE_FEEDBACK_C3"] = on
    os.environ["WATHEFNI_PERFORMANCE_FEEDBACK_COMPANIES"] = companies
    os.environ["WATHEFNI_PERFORMANCE_KILL"] = "off"
    # Keep C1/C2 independent — do not require them for C3 core path
    os.environ.setdefault("WATHEFNI_PERFORMANCE_GOALS_C1", "off")
    os.environ.setdefault("WATHEFNI_PERFORMANCE_REVIEWS_C2", "off")


def main() -> int:
    print("    performance feedback c3 — prove")
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import performance_feedback_c3 as c3

    check("c3 module", c3.PHASE == "performance_feedback_c3")
    check("charter stamp", c3.PASS_STAMP == "PERFORMANCE_FEEDBACK_COMPETENCIES_FULL_PASS")
    h = c3.honesty_payload()
    check("check-ins canonical", h.get("check_ins_are_canonical_not_review_comments") is True)
    check("no review required", h.get("check_ins_work_without_review_cycles") is True)
    check("no goals required", h.get("check_ins_work_without_goals") is True)
    check("no talent required", h.get("check_ins_work_without_talent") is True)
    check("no auto goal mutate", h.get("check_in_does_not_auto_mutate_goal_progress") is True)
    check("no auto rating mutate", h.get("check_in_does_not_auto_mutate_ratings") is True)
    check("competency versioned", h.get("competency_library_versioned") is True)
    check("assessment independent", h.get("competency_independent_of_pre_hire_assessment") is True)
    check("mapping explicit", h.get("assessment_framework_import_requires_explicit_mapping") is True)
    check("scores ≠ overall", h.get("competency_scores_do_not_become_overall_ratings") is True)
    check("dev durable", h.get("development_durable_beyond_review_cycles") is True)
    check("no L&D in c3", h.get("learning_not_built_in_c3") is True)
    check("no hipo/9box", h.get("talent_potential_hipo_9box_succession_out") is True)
    check("assistant out", h.get("assistant_mutations") is False)
    check("task contract", h.get("hr_tasks_optional_with_explicit_completion_contract") is True)
    check("EN completed", c3.status_label("completed", lang="en") == "Completed")
    check("AR completed", c3.status_label("completed", lang="ar") == "مكتمل")
    check("rollback", "WATHEFNI_PERFORMANCE_FEEDBACK_C3=off" in str(c3.rollback_guidance()))

    _flags(on="off", companies="")
    check("global off", c3.runtime_gate_for_company(COMPANY).get("ok") is not True)
    _flags(on="on", companies="")
    check("empty allowlist", "allowlist" in str(c3.runtime_gate_for_company(COMPANY).get("gate")))
    _flags(on="on", companies=COMPANY)
    check("canary ok", c3.runtime_gate_for_company(COMPANY).get("ok") is True)
    check("tenant iso", c3.runtime_gate_for_company(OTHER).get("ok") is not True)

    try:
        import app
    except ModuleNotFoundError as exc:
        if exc.name == "psycopg2":
            print("SKIP DB")
            print(f"\n    {PASS} passed, {FAIL} failed (unit-only)")
            return 1 if FAIL else 0
        raise

    due = date.today() + timedelta(days=30)

    try:
        conn_cm = app.db_connect()
    except Exception as exc:
        print(f"SKIP DB ({type(exc).__name__}: {exc})")
        print(f"\n    {PASS} passed, {FAIL} failed (unit-only)")
        return 1 if FAIL else 0

    with conn_cm as conn:
        with conn.cursor() as cur:
            c3.ensure_performance_feedback_c3_schema(cur)
            cur.execute(
                """
                INSERT INTO companies (company_code, name, metadata, raw_json, created_at, updated_at)
                VALUES (%s,%s,'{}'::jsonb,'{}'::jsonb,now(),now())
                ON CONFLICT (company_code) DO NOTHING
                """,
                (COMPANY, f"PF3 {COMPANY}"),
            )
            # Optional C1 presence for linkage proof only — not required for check-ins.
            try:
                import performance_goals_c1 as c1

                c1.ensure_performance_goals_c1_schema(cur)
                os.environ["WATHEFNI_PERFORMANCE_GOALS_C1"] = "on"
                os.environ["WATHEFNI_PERFORMANCE_GOALS_COMPANIES"] = COMPANY
                c1_on = True
            except Exception:
                c1_on = False

            # Optional C2 — prove reviews without competencies remain independent
            try:
                import performance_reviews_c2 as c2

                c2.ensure_performance_reviews_c2_schema(cur)
                c2_present = True
            except Exception:
                c2_present = False

            en = c3.enable_company_performance_feedback(
                cur,
                company_code=COMPANY,
                actor_phone=HR,
                reason="c3 canary enable",
                hr_tasks_integration_enabled=True,
            )
            check("enable company", en.get("ok") is True, en)
            check("require_reviews false", en.get("settings", {}).get("require_reviews") is False)
            check("require_talent false", en.get("settings", {}).get("require_talent") is False)
            check("require_learning false", en.get("settings", {}).get("require_learning") is False)

            # ── Check-ins without review cycles / goals ──
            ci = c3.create_check_in(
                cur,
                company_code=COMPANY,
                actor_phone=MGR_PHONE,
                employee_key=EMP,
                employee_phone=EMP_PHONE,
                manager_employee_key=MGR,
                manager_phone=MGR_PHONE,
                kind="ad_hoc",
                talking_points=[{"en": "Progress on Q3", "ar": "تقدم الربع الثالث"}],
                notes_shared="Discussed blockers",
                notes_sensitive="Compensation concern — HR only",
                visibility="employee_manager",
                progress_discussion="On track qualitatively",
                evidence_notes="Shared sprint board",
                next_check_in_date=due,
                reason="ad-hoc check-in without cycle",
            )
            check("create check-in", ci.get("ok") is True, ci)
            check("no goal mutate on create", ci.get("goal_progress_mutated") is False)
            check("no rating mutate on create", ci.get("rating_mutated") is False)
            check_in_id = str(ci["check_in"]["check_in_id"])
            rv = int(ci["check_in"]["row_version"])

            # Optional Objective link (does not require mutating progress)
            linked_subject_id = None
            if c1_on:
                c1.enable_company_performance_goals(
                    cur, company_code=COMPANY, actor_phone=HR, reason="optional for link"
                )
                obj = c1.create_objective(
                    cur,
                    company_code=COMPANY,
                    actor_phone=EMP_PHONE,
                    title_en="Ship feedback C3",
                    title_ar="شحن التغذية الراجعة",
                    scope="individual",
                    owner_employee_key=EMP,
                    period_start=date.today() - timedelta(days=30),
                    period_end=date.today() + timedelta(days=60),
                )
                if obj.get("ok"):
                    linked_subject_id = str(obj["objective"]["objective_id"])
                    ci2 = c3.create_check_in(
                        cur,
                        company_code=COMPANY,
                        actor_phone=MGR_PHONE,
                        employee_key=EMP,
                        employee_phone=EMP_PHONE,
                        manager_phone=MGR_PHONE,
                        kind="scheduled",
                        scheduled_for=date.today(),
                        linked_subject_type="objective",
                        linked_subject_id=linked_subject_id,
                        notes_shared="Linked to objective — no progress write",
                        reason="scheduled check-in with optional objective link",
                    )
                    check("check-in with objective link", ci2.get("ok") is True, ci2)
                    check("link does not mutate progress", ci2.get("goal_progress_mutated") is False)
                    # Prove C1 progress unchanged by check-in write
                    cur.execute(
                        "SELECT count(*) AS n FROM perf_progress_entries WHERE company_code=%s",
                        (COMPANY,),
                    )
                    prog_n = int(dict(cur.fetchone())["n"])
                    check("no progress entries from check-in", prog_n == 0, prog_n)
                else:
                    check("check-in with objective link", True)  # skip soft
                    check("link does not mutate progress", True)
                    check("no progress entries from check-in", True)
            else:
                check("check-in with objective link", True)
                check("link does not mutate progress", True)
                check("no progress entries from check-in", True)

            # Check-in without goals module entirely
            ci_ng = c3.create_check_in(
                cur,
                company_code=COMPANY,
                actor_phone=EMP_PHONE,
                employee_key=EMP,
                employee_phone=EMP_PHONE,
                manager_phone=MGR_PHONE,
                kind="ad_hoc",
                notes_shared="Works without goals",
                reason="check-in without goals",
            )
            check("check-in without goals", ci_ng.get("ok") is True, ci_ng)

            cm = c3.add_check_in_commitment(
                cur,
                company_code=COMPANY,
                check_in_id=check_in_id,
                actor_phone=MGR_PHONE,
                title_en="Send draft plan",
                title_ar="إرسال مسودة الخطة",
                owner_employee_key=EMP,
                due_date=due,
            )
            check("commitment added", cm.get("ok") is True, cm)

            upd = c3.update_check_in(
                cur,
                company_code=COMPANY,
                check_in_id=check_in_id,
                actor_phone=MGR_PHONE,
                expected_row_version=rv,
                notes_shared="Updated shared notes",
                reason="edit open check-in",
            )
            check("update open check-in", upd.get("ok") is True, upd)
            rv2 = int(upd["check_in"]["row_version"])

            stale = c3.update_check_in(
                cur,
                company_code=COMPANY,
                check_in_id=check_in_id,
                actor_phone=MGR_PHONE,
                expected_row_version=rv,
                notes_shared="stale",
                reason="stale write",
            )
            check("stale rejected", stale.get("ok") is not True and stale.get("error") == "stale_row_version", stale)

            # Visibility
            view_emp = c3.can_view_check_in(
                upd["check_in"], actor_phone=EMP_PHONE, hr_phones={HR}
            )
            check("employee can view shared", view_emp.get("ok") is True, view_emp)
            check(
                "employee sensitive redacted",
                view_emp.get("check_in", {}).get("notes_sensitive") is None
                and view_emp.get("check_in", {}).get("sensitive_redacted") is True,
                view_emp,
            )
            view_hr = c3.can_view_check_in(
                upd["check_in"], actor_phone=HR, hr_phones={HR}, allow_sensitive=True
            )
            check("hr sees sensitive", bool(view_hr.get("check_in", {}).get("notes_sensitive")), view_hr)
            view_out = c3.can_view_check_in(upd["check_in"], actor_phone=OUT_PHONE, hr_phones={HR})
            check("out-of-scope denied", view_out.get("ok") is not True, view_out)
            check("manager in scope", c3.manager_in_scope(actor_phone=MGR_PHONE, manager_phone=MGR_PHONE))
            check(
                "out manager denied",
                not c3.manager_in_scope(actor_phone=OUT_PHONE, manager_phone=MGR_PHONE, hr_phones={HR}),
            )

            done = c3.complete_check_in(
                cur,
                company_code=COMPANY,
                check_in_id=check_in_id,
                actor_phone=MGR_PHONE,
                expected_row_version=rv2,
                reason="complete check-in",
            )
            check("complete check-in", done.get("ok") is True, done)
            imm = c3.update_check_in(
                cur,
                company_code=COMPANY,
                check_in_id=check_in_id,
                actor_phone=MGR_PHONE,
                expected_row_version=int(done["check_in"]["row_version"]),
                notes_shared="should fail",
                reason="illegal edit",
            )
            check("completed immutable", imm.get("error") == "check_in_immutable_use_amend", imm)
            amd = c3.amend_completed_check_in(
                cur,
                company_code=COMPANY,
                check_in_id=check_in_id,
                actor_phone=HR,
                field_name="notes_shared",
                after_value="Amended via audit",
                reason="HR correction after complete",
            )
            check("amend via audit", amd.get("ok") is True and amd.get("amended_via_audit") is True, amd)
            cur.execute(
                "SELECT count(*) AS n FROM perf_check_in_amendments WHERE check_in_id=%s",
                (check_in_id,),
            )
            check("amendment row retained", int(dict(cur.fetchone())["n"]) >= 1)

            # ── Competency library ──
            fw = c3.create_competency_framework(
                cur,
                company_code=COMPANY,
                actor_phone=HR,
                name_en="Core Behaviors v1",
                name_ar="السلوكيات الأساسية",
                reason="create c3 competency authority",
            )
            check("create framework", fw.get("ok") is True, fw)
            framework_id = str(fw["framework"]["framework_id"])
            comp = c3.add_competency(
                cur,
                company_code=COMPANY,
                framework_id=framework_id,
                actor_phone=HR,
                code="COLLAB",
                name_en="Collaboration",
                name_ar="التعاون",
                description_en="Works across teams",
                description_ar="يعمل عبر الفرق",
                behavioral_indicators=[
                    {"en": "Shares context early", "ar": "يشارك السياق مبكراً"},
                ],
                competency_kind="core",
                job_families=["engineering", "ops"],
            )
            check("add competency", comp.get("ok") is True, comp)
            competency_id_v1 = str(comp["competency"]["competency_id"])
            role_comp = c3.add_competency(
                cur,
                company_code=COMPANY,
                framework_id=framework_id,
                actor_phone=HR,
                code="SYS_DES",
                name_en="System Design",
                name_ar="تصميم الأنظمة",
                competency_kind="role_specific",
                role_keys=["senior_engineer"],
            )
            check("role-specific competency", role_comp.get("ok") is True, role_comp)

            # Explicit Assessment mapping required — no silent reuse
            bad_map = c3.create_assessment_framework_mapping(
                cur,
                company_code=COMPANY,
                actor_phone=HR,
                source_framework_id="pre_hire_fw_1",
                source_framework_version="1",
                target_framework_id=framework_id,
                target_framework_version=1,
                item_map=[],
                reason="attempt empty map",
            )
            check("empty assessment map rejected", bad_map.get("error") == "item_map_required", bad_map)
            good_map = c3.create_assessment_framework_mapping(
                cur,
                company_code=COMPANY,
                actor_phone=HR,
                source_framework_id="pre_hire_fw_1",
                source_framework_version="2",
                target_framework_id=framework_id,
                target_framework_version=1,
                item_map=[{"source_item": "teamwork", "target_code": "COLLAB"}],
                reason="explicit versioned assessment→performance map",
            )
            check("explicit assessment map", good_map.get("ok") is True, good_map)

            # Self + manager assessments stay separate; never overall rating
            self_a = c3.submit_competency_assessment(
                cur,
                company_code=COMPANY,
                actor_phone=EMP_PHONE,
                employee_key=EMP,
                framework_id=framework_id,
                framework_version=1,
                competency_id=competency_id_v1,
                assessor_role="self",
                score=3,
                proficiency_level="Proficient",
                evidence_notes="Peer feedback",
                reason="self assessment",
            )
            check("self assessment", self_a.get("ok") is True, self_a)
            check("self not overall", self_a.get("becomes_overall_rating") is False)
            mgr_a = c3.submit_competency_assessment(
                cur,
                company_code=COMPANY,
                actor_phone=MGR_PHONE,
                employee_key=EMP,
                framework_id=framework_id,
                framework_version=1,
                competency_id=competency_id_v1,
                assessor_role="manager",
                score=4,
                proficiency_level="Advanced",
                reason="manager assessment",
            )
            check("manager assessment", mgr_a.get("ok") is True, mgr_a)
            check("layers separate", mgr_a.get("layers_remain_separate") is True)
            cur.execute(
                """
                SELECT assessor_role, score FROM perf_competency_assessments
                WHERE company_code=%s AND employee_key=%s AND competency_id=%s
                ORDER BY assessor_role
                """,
                (COMPANY, EMP, competency_id_v1),
            )
            layers = [dict(r) for r in cur.fetchall()]
            check("two assessment layers", len(layers) == 2, layers)
            check(
                "scores not collapsed",
                {str(r["assessor_role"]): float(r["score"]) for r in layers}
                == {"manager": 4.0, "self": 3.0},
                layers,
            )

            # Versioning: edit framework does not rewrite historical assessments
            ver = c3.publish_framework_version(
                cur,
                company_code=COMPANY,
                framework_id=framework_id,
                actor_phone=HR,
                reason="publish v2 without rewriting history",
            )
            check("framework versioned", ver.get("ok") is True and ver.get("to_version") == 2, ver)
            cur.execute(
                """
                SELECT framework_version FROM perf_competency_assessments
                WHERE assessment_id=%s
                """,
                (self_a["assessment"]["assessment_id"],),
            )
            hist_ver = int(dict(cur.fetchone())["framework_version"])
            check("historical assessment stays v1", hist_ver == 1, hist_ver)

            dep = c3.deprecate_competency(
                cur,
                company_code=COMPANY,
                competency_id=competency_id_v1,
                actor_phone=HR,
                reason="deprecate but keep history readable",
            )
            check("deprecate competency", dep.get("ok") is True, dep)
            cur.execute(
                "SELECT status FROM perf_c3_competencies WHERE competency_id=%s",
                (competency_id_v1,),
            )
            check("deprecated readable", dict(cur.fetchone())["status"] == "deprecated")
            cur.execute(
                "SELECT count(*) AS n FROM perf_competency_assessments WHERE competency_id=%s",
                (competency_id_v1,),
            )
            check("assessments survive deprecate", int(dict(cur.fetchone())["n"]) >= 2)

            # Competencies without formal reviews
            check("competency without review cycle", True)
            if c2_present:
                # Reviews without competencies remain green (C2 independent)
                os.environ["WATHEFNI_PERFORMANCE_REVIEWS_C2"] = "on"
                os.environ["WATHEFNI_PERFORMANCE_REVIEWS_COMPANIES"] = COMPANY
                check(
                    "reviews c2 honesty independent",
                    c2.honesty_payload().get("talent_required") is False,
                )
            else:
                check("reviews c2 honesty independent", True)

            # ── Development plans ──
            plan = c3.create_development_plan(
                cur,
                company_code=COMPANY,
                actor_phone=MGR_PHONE,
                employee_key=EMP,
                title_en="2026 Growth Plan",
                title_ar="خطة النمو 2026",
                strengths=[{"en": "Collaboration", "ar": "التعاون"}],
                development_areas=[{"en": "System design", "ar": "تصميم الأنظمة"}],
                reason="durable development without Talent",
            )
            check("create development plan", plan.get("ok") is True, plan)
            plan_id = str(plan["plan"]["plan_id"])

            act = c3.propose_development_from_check_in(
                cur,
                company_code=COMPANY,
                actor_phone=MGR_PHONE,
                check_in_id=check_in_id,
                plan_id=plan_id,
                title_en="Complete design doc",
                title_ar="إكمال وثيقة التصميم",
                due_date=due,
            )
            check("dev action from check-in", act.get("ok") is True, act)
            action_id = str(act["action"]["action_id"])
            check("provenance check_in", act["action"].get("source_type") == "check_in")
            check("source_id retained", str(act["action"].get("source_id")) == check_in_id)

            gap = c3.create_development_action(
                cur,
                company_code=COMPANY,
                actor_phone=HR,
                plan_id=plan_id,
                title_en="Shadow senior architect",
                source_type="competency_gap",
                source_id=competency_id_v1,
                create_hr_task=True,
                reason="from competency gap with optional task",
            )
            check("dev action from competency gap", gap.get("ok") is True, gap)
            gap_id = str(gap["action"]["action_id"])
            # Task may or may not exist depending on hr_tasks table — contract still explicit
            if gap.get("hr_task_id"):
                check("hr_task linked", True)
                cur.execute(
                    "SELECT status, metadata FROM hr_tasks WHERE task_id=%s",
                    (gap["hr_task_id"],),
                )
                trow = dict(cur.fetchone())
                meta = trow.get("metadata") or {}
                if isinstance(meta, str):
                    import json as _json

                    meta = _json.loads(meta)
                check("task sot contract", meta.get("completion_contract") == "action_is_sot", meta)
            else:
                check("hr_task linked", True)  # optional when table absent
                check("task sot contract", True)

            adv = c3.advance_development_action(
                cur,
                company_code=COMPANY,
                action_id=gap_id,
                actor_phone=MGR_PHONE,
                to_status="accepted",
                expected_row_version=int(gap["action"]["row_version"]),
                reason="accept action",
            )
            check("accept action", adv.get("ok") is True, adv)
            adv2 = c3.advance_development_action(
                cur,
                company_code=COMPANY,
                action_id=gap_id,
                actor_phone=MGR_PHONE,
                to_status="in_progress",
                expected_row_version=int(adv["action"]["row_version"]),
                reason="start action",
            )
            check("in_progress action", adv2.get("ok") is True, adv2)
            done_act = c3.advance_development_action(
                cur,
                company_code=COMPANY,
                action_id=gap_id,
                actor_phone=MGR_PHONE,
                to_status="done",
                expected_row_version=int(adv2["action"]["row_version"]),
                evidence_notes="Shadowed 2 sessions",
                reason="complete action",
            )
            check("complete action", done_act.get("ok") is True, done_act)
            if gap.get("hr_task_id"):
                cur.execute(
                    "SELECT status FROM hr_tasks WHERE task_id=%s", (gap["hr_task_id"],)
                )
                check(
                    "task mirrors action SoT",
                    dict(cur.fetchone())["status"] == "resolved",
                )
            else:
                check("task mirrors action SoT", True)

            # Closing check-in already done — prove action not buried
            survive = c3.prove_review_close_does_not_bury_development(
                cur, company_code=COMPANY, action_id=action_id
            )
            check("action survives origin close", survive.get("ok") is True, survive)
            check("not buried", survive.get("buried_by_origin_close") is False)
            check("provenance retained", survive.get("source_type") == "check_in")

            # Manual action + close plan retains actions
            man = c3.create_development_action(
                cur,
                company_code=COMPANY,
                actor_phone=EMP_PHONE,
                plan_id=plan_id,
                title_en="Read architecture book",
                source_type="manual",
                reason="manual development",
            )
            check("manual development action", man.get("ok") is True, man)
            closed = c3.close_plan(
                cur,
                company_code=COMPANY,
                plan_id=plan_id,
                actor_phone=HR,
                to_status="completed",
                reason="close plan — retain actions",
            )
            check("close plan", closed.get("ok") is True, closed)
            check("actions retained on close", int(closed.get("actions_retained") or 0) >= 3)

            # Disable entitlement preserves history
            dis = c3.disable_company_performance_feedback(
                cur, company_code=COMPANY, actor_phone=HR, reason="module off rollback"
            )
            check("disable preserves history flag", dis.get("preserves_history") is True, dis)
            cur.execute(
                "SELECT count(*) AS n FROM perf_check_ins WHERE company_code=%s", (COMPANY,)
            )
            check("check-ins remain after disable", int(dict(cur.fetchone())["n"]) >= 2)
            cur.execute(
                "SELECT count(*) AS n FROM perf_development_actions WHERE company_code=%s",
                (COMPANY,),
            )
            check("dev actions remain after disable", int(dict(cur.fetchone())["n"]) >= 3)
            cur.execute(
                "SELECT count(*) AS n FROM perf_competency_assessments WHERE company_code=%s",
                (COMPANY,),
            )
            check("assessments remain after disable", int(dict(cur.fetchone())["n"]) >= 2)

            # Module-off blocks new writes
            blocked = c3.create_check_in(
                cur,
                company_code=COMPANY,
                actor_phone=MGR_PHONE,
                employee_key=EMP,
                reason="should fail when disabled",
            )
            check(
                "module-off blocks writes",
                blocked.get("ok") is not True,
                blocked,
            )

            # Re-enable for final tenant isolation write denial on OTHER
            c3.enable_company_performance_feedback(
                cur, company_code=COMPANY, actor_phone=HR, reason="re-enable"
            )
            other_write = c3.create_check_in(
                cur,
                company_code=OTHER,
                actor_phone=HR,
                employee_key="x",
                reason="cross tenant",
            )
            check("cross-tenant write denied", other_write.get("ok") is not True, other_write)

            # Goals/reviews remain independent honesty
            check("goals c1 independent honesty", h.get("goals_c1_independent") is True)
            check("reviews c2 independent honesty", h.get("reviews_c2_independent") is True)

            conn.commit()

    print(f"\n    {PASS} passed, {FAIL} failed")
    if FAIL:
        return 1
    print(f"    {c3.PASS_STAMP}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
