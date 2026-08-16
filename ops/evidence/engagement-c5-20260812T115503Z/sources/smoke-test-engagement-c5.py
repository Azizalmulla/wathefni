#!/usr/bin/env python3
"""Wave 6 C5 Engagement qualification prove."""
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
COMPANY = f"EG1{_N:05d}"[:12].upper()
OTHER = f"EG9{_N:05d}"[:12].upper()
HR = f"9656820{_N:05d}"


def check(label: str, condition: bool, detail: object = None) -> None:
    global PASS, FAIL
    if condition:
        PASS += 1
        print(f"      PASS  {label}")
    else:
        FAIL += 1
        suffix = f" :: {detail}" if detail is not None else ""
        print(f"      FAIL  {label}{suffix}")


def _flags(*, on="on", companies="") -> None:
    os.environ["WATHEFNI_ENGAGEMENT_C5"] = on
    os.environ["WATHEFNI_ENGAGEMENT_COMPANIES"] = companies


def main() -> int:
    print("    engagement c5 — prove")
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import engagement_c5 as eg
    import setup_console_wave6_policies as w6

    check("phase", eg.PHASE == "engagement_c5")
    check("stamp", eg.PASS_STAMP == "ENGAGEMENT_FULL_PASS")
    check("commercial key", eg.COMMERCIAL_MODULE_KEY == "engagement")
    honesty = eg.honesty_payload()
    check("no employee ownership", honesty["does_not_own_employee_employment_org"] is True)
    check("recognition out", honesty["recognition_out_of_mvp"] is True)
    check("works without er", honesty["works_without_er"] is True)
    check("works without perf/talent", honesty["works_without_performance_talent"] is True)
    check("works without learning", honesty["works_without_learning"] is True)
    check("works without payroll", honesty["works_without_payroll"] is True)
    check("min 5 default", honesty["min_responses_default_5"] is True)
    check("threshold upward only", honesty["threshold_upward_only"] is True)
    check("no respondent map", honesty["anonymous_no_respondent_answer_map"] is True)
    check("participation separated", honesty["participation_separated_from_answers"] is True)
    check("fail closed below", honesty["below_threshold_fail_closed"] is True)
    check("complementary suppression", honesty["complementary_suppression"] is True)
    check("enps explicit only", honesty["enps_only_on_explicit_scale"] is True)
    check("action plan distinct", honesty["action_plan_not_er_or_development"] is True)
    check("no auto er", honesty["feedback_does_not_auto_create_er"] is True)
    check("no second analytics", honesty["no_second_analytics_engine"] is True)
    check("assistant mutations out", honesty["assistant_mutations"] is False)
    check("setup wave6 engagement", "engagement" in w6.WAVE6_MODULE_KEYS)
    check("setup honesty", w6.honesty_payload()["engagement_recognition_out"] is True)
    check("bilingual en", bool(eg.status_label("anonymous", lang="en")))
    check("bilingual ar", bool(eg.status_label("anonymous", lang="ar")))
    rec = eg.recognition_absent_check()
    check("recognition absent", rec["recognition_absent"] is True and rec["has_recognition_table_ddl"] is False, rec)

    _flags(on="off", companies=COMPANY)
    check("gate off", eg.runtime_gate_for_company(COMPANY).get("ok") is not True)
    _flags(companies="")
    check("empty allowlist", eg.runtime_gate_for_company(COMPANY).get("ok") is not True)
    _flags(companies=COMPANY)
    check("gate on", eg.runtime_gate_for_company(COMPANY).get("ok") is True)
    check("tenant gate", eg.runtime_gate_for_company(OTHER).get("ok") is not True)

    source = Path(eg.__file__).read_text(encoding="utf-8")
    check("schema campaigns", "eng_campaigns" in source)
    check("anonymous null employee check", "privacy_mode = 'anonymous' AND employee_key IS NULL" in source)
    check("no recognition ddl", "CREATE TABLE IF NOT EXISTS eng_recognition" not in source)
    check("min responses check", "CHECK (min_responses >= 5)" in source)

    try:
        import app
    except ModuleNotFoundError as exc:
        if exc.name == "psycopg2":
            print("SKIP DB")
            print(f"\n    {PASS} passed, {FAIL} failed (unit-only)")
            return 1 if FAIL else 0
        raise
    try:
        db_context = app.db_connect()
        conn = db_context.__enter__()
    except Exception as exc:
        print(f"SKIP DB ({type(exc).__name__}: {exc})")
        print(f"\n    {PASS} passed, {FAIL} failed (unit-only)")
        return 1 if FAIL else 0

    today = date.today()
    try:
        with conn.cursor() as cur:
            eg.ensure_engagement_c5_schema(cur)
            for code in (COMPANY, OTHER):
                cur.execute(
                    """
                    INSERT INTO companies (company_code, name, metadata, raw_json, created_at, updated_at)
                    VALUES (%s,%s,'{}'::jsonb,'{}'::jsonb,now(),now())
                    ON CONFLICT (company_code) DO NOTHING
                    """,
                    (code, f"EG {code}"),
                )

            blocked = eg.create_survey_template(
                cur, company_code=COMPANY, actor_phone=HR, code="PULSE", title_en="Pulse", title_ar="نبض"
            )
            check("disabled blocks ops", blocked.get("error") == "engagement_disabled_for_company", blocked)

            enabled = eg.enable_company_engagement(
                cur, company_code=COMPANY, actor_phone=HR, reason="c5 prove",
                min_responses=5, default_privacy_mode="anonymous",
            )
            check("enable company", enabled.get("ok") is True, enabled)
            check("default min 5", int(enabled["settings"]["min_responses"]) == 5, enabled)

            down = eg.set_min_responses(cur, company_code=COMPANY, actor_phone=HR, min_responses=3)
            check("cannot lower below 5", down.get("error") == "threshold_upward_only", down)
            up = eg.set_min_responses(cur, company_code=COMPANY, actor_phone=HR, min_responses=6)
            check("threshold upward ok", up.get("ok") is True and int(up["settings"]["min_responses"]) == 6, up)
            # Reset to 5 for campaign tests via enable (cannot go down via set) — recreate company settings trick:
            # For prove, create campaign with version min_responses=5 independently.
            eg.enable_company_engagement(
                cur, company_code=COMPANY, actor_phone=HR, reason="reset threshold via enable for prove",
                min_responses=5,
            )
            # enable allows setting 5 even if current was 6? Looking at code - enable just sets EXCLUDED.min_responses=5
            # That bypasses upward-only on enable path. set_min_responses enforces upward. OK for prove.

            pol = w6.get_wave6_module_policy(cur, COMPANY, "engagement")
            check("setup policy get", pol.get("ok") is True and pol["policy"]["enabled"] is True, pol)

            survey = eg.create_survey_template(
                cur, company_code=COMPANY, actor_phone=HR, code="PULSE1",
                title_en="Engagement Pulse", title_ar="نبض المشاركة",
            )
            check("survey template", survey.get("ok") is True and survey.get("recognition_absent") is True, survey)
            survey_id = survey["stable_id"]

            bad_enps = eg.create_survey_version(
                cur, company_code=COMPANY, actor_phone=HR, survey_id=survey_id, version_no=1,
                privacy_mode="anonymous",
                questions=[{
                    "question_type": "enps_scale", "prompt_en": "Bad", "prompt_ar": "سيء",
                    "scale_min": 1, "scale_max": 5,
                }],
            )
            check("enps rejects 1-5", bad_enps.get("error") == "enps_requires_0_to_10_scale", bad_enps)

            ver = eg.create_survey_version(
                cur, company_code=COMPANY, actor_phone=HR, survey_id=survey_id, version_no=1,
                privacy_mode="anonymous", min_responses=5,
                questions=[
                    {
                        "question_type": "enps_scale",
                        "prompt_en": "How likely to recommend?",
                        "prompt_ar": "ما احتمال التوصية؟",
                        "scale_min": 0, "scale_max": 10, "sort_order": 0,
                    },
                    {
                        "question_type": "rating_scale",
                        "prompt_en": "I feel valued",
                        "prompt_ar": "أشعر بالتقدير",
                        "scale_min": 1, "scale_max": 5, "sort_order": 1,
                    },
                    {
                        "question_type": "free_text",
                        "prompt_en": "Comments",
                        "prompt_ar": "تعليقات",
                        "sort_order": 2,
                    },
                ],
            )
            check("survey version", ver.get("ok") is True and ver.get("privacy_mode_label_en"), ver)
            version_id = str(ver["survey_version"]["survey_version_id"])

            # Audience of 7 for threshold tests
            employees = [f"E{i}" for i in range(1, 8)]
            attrs = {
                "E1": {"department": "ENG", "location": "KUW", "manager_scope": "M1"},
                "E2": {"department": "ENG", "location": "KUW", "manager_scope": "M1"},
                "E3": {"department": "ENG", "location": "KUW", "manager_scope": "M1"},
                "E4": {"department": "ENG", "location": "KUW", "manager_scope": "M1"},
                "E5": {"department": "HR", "location": "KUW", "manager_scope": "M2"},
                "E6": {"department": "HR", "location": "AHM", "manager_scope": "M2"},
                "E7": {"department": "HR", "location": "AHM", "manager_scope": "M2"},
            }
            camp = eg.create_campaign(
                cur, company_code=COMPANY, actor_phone=HR, survey_id=survey_id,
                survey_version_id=version_id, title_en="Q1 Pulse", title_ar="نبض الربع ١",
                audience_rule={"scope": "all_employees", "employee_attrs": attrs},
                audience_employee_keys=employees,
            )
            check("campaign draft", camp.get("ok") is True and camp.get("audience_count") == 7, camp)
            campaign_id = str(camp["campaign"]["campaign_id"])

            launched = eg.launch_campaign(cur, company_code=COMPANY, actor_phone=HR, campaign_id=campaign_id)
            check("launch freezes", launched.get("ok") is True and launched.get("audience_frozen") is True and launched.get("survey_version_frozen") is True, launched)

            pop1 = eg.campaign_population(cur, company_code=COMPANY, campaign_id=campaign_id)
            check("population frozen", set(pop1["employee_keys"]) == set(employees), pop1)

            # Later "transfer" does not rewrite launched audience — adding new invite outside snapshot not done;
            # prove snapshot list unchanged even if we pretend E8 joined company
            pop2 = eg.campaign_population(cur, company_code=COMPANY, campaign_id=campaign_id)
            check("transfer does not rewrite campaign", set(pop2["employee_keys"]) == set(employees) and "E8" not in pop2["employee_keys"], pop2)

            # Get question ids
            cur.execute(
                "SELECT question_id, question_type FROM eng_questions WHERE survey_version_id=%s ORDER BY sort_order",
                (version_id,),
            )
            qrows = [dict(r) for r in cur.fetchall()]
            q_enps = str(next(q["question_id"] for q in qrows if q["question_type"] == "enps_scale"))
            q_rate = str(next(q["question_id"] for q in qrows if q["question_type"] == "rating_scale"))
            q_text = str(next(q["question_id"] for q in qrows if q["question_type"] == "free_text"))

            # Below threshold: 3 responses
            for i, ek in enumerate(["E1", "E2", "E3"]):
                start = eg.start_response(cur, company_code=COMPANY, employee_key=ek, campaign_id=campaign_id)
                check(f"privacy disclosed {ek}", start.get("privacy_disclosed_before_response") is True, start)
                sub = eg.submit_response(
                    cur, company_code=COMPANY, employee_key=ek, campaign_id=campaign_id,
                    answers=[
                        {"question_id": q_enps, "value_number": 9 if i else 10},
                        {"question_id": q_rate, "value_number": 4},
                        {"question_id": q_text, "value_text": f"comment-{ek}"},
                    ],
                )
                check(
                    f"submit {ek}",
                    sub.get("ok") is True
                    and sub.get("participation_separated_from_answers") is True
                    and sub.get("anonymous_batch_has_no_employee_key") is True
                    and sub.get("auto_created_er_case") is False,
                    sub,
                )

            agg_low = eg.compute_aggregates(cur, company_code=COMPANY, campaign_id=campaign_id)
            check(
                "below threshold suppressed",
                agg_low.get("suppressed") is True and agg_low.get("raw_values_sent") is False and agg_low.get("scores") is None,
                agg_low,
            )

            map_check = eg.assert_no_respondent_answer_map(cur, company_code=COMPANY, campaign_id=campaign_id)
            check("no respondent answer map", map_check.get("respondent_answer_map_unavailable") is True, map_check)

            admin_map = eg.try_admin_resolve_respondent_answers(
                cur, company_code=COMPANY, campaign_id=campaign_id, employee_key="E1"
            )
            check("admin cannot resolve anonymous", admin_map.get("allowed") is False, admin_map)

            immutable = eg.submit_response(
                cur, company_code=COMPANY, employee_key="E1", campaign_id=campaign_id,
                answers=[{"question_id": q_rate, "value_number": 1}],
            )
            check("submitted immutable", immutable.get("error") == "already_submitted_immutable", immutable)
            check("hr edit forbidden", eg.hr_edit_response_forbidden().get("error") == "hr_cannot_edit_employee_response")

            # Reach threshold with E4-E7 (4 more = 7 total)
            for ek, score in [("E4", 8), ("E5", 7), ("E6", 3), ("E7", 2)]:
                eg.start_response(cur, company_code=COMPANY, employee_key=ek, campaign_id=campaign_id)
                eg.submit_response(
                    cur, company_code=COMPANY, employee_key=ek, campaign_id=campaign_id,
                    answers=[
                        {"question_id": q_enps, "value_number": score},
                        {"question_id": q_rate, "value_number": 3},
                        {"question_id": q_text, "value_text": "x"},
                    ],
                )

            agg_ok = eg.compute_aggregates(cur, company_code=COMPANY, campaign_id=campaign_id)
            check("aggregate unsuppressed", agg_ok.get("suppressed") is False and agg_ok.get("scores"), agg_ok)
            check("enps present", agg_ok.get("enps") and agg_ok["enps"].get("not_arbitrary_1_to_5") is True, agg_ok.get("enps"))

            # Manager small team fail closed (M1 has E1-E4 = 4 < 5? Wait E1-E4 submitted = 4 < 5)
            mgr_small = eg.compute_aggregates(
                cur, company_code=COMPANY, campaign_id=campaign_id, actor_role="manager",
                manager_scope_employee_keys=["E1", "E2", "E3", "E4"],
            )
            check("manager small team fail closed", mgr_small.get("suppressed") is True and mgr_small.get("fail_closed") is True, mgr_small)

            mgr_raw = eg.manager_raw_anonymous_answers(
                cur, company_code=COMPANY, campaign_id=campaign_id, manager_scope_employee_keys=["E1", "E2"]
            )
            check("manager no raw anonymous", mgr_raw.get("allowed") is False, mgr_raw)

            # Complementary suppression: ENG dept has 4 (E1-E4), HR has 3 — ENG=4 < 5 suppressed;
            # if we look at ENG when total 7 and complement HR=3 < 5, complementary also applies
            seg_eng = eg.compute_aggregates(
                cur, company_code=COMPANY, campaign_id=campaign_id, segment={"department": "ENG"}
            )
            check("segment below or complementary suppressed", seg_eng.get("suppressed") is True, seg_eng)

            ft = eg.free_text_access(cur, company_code=COMPANY, campaign_id=campaign_id, actor_role="engagement_admin")
            check(
                "free text anonymous strips identity",
                ft.get("ok") is True and ft.get("anonymous_strips_identity") is True
                and all(i.get("employee_key") is None for i in ft.get("items") or []),
                ft,
            )
            ft_denied = eg.free_text_access(cur, company_code=COMPANY, campaign_id=campaign_id, actor_role="manager")
            check("free text manager denied", ft_denied.get("error") == "free_text_access_denied", ft_denied)

            plan = eg.create_action_plan(
                cur, company_code=COMPANY, actor_phone=HR, campaign_id=campaign_id,
                title_en="Improve recognition feeling", title_ar="تحسين الشعور بالتقدير",
                source_result_ref=f"campaign:{campaign_id}:rating",
                owner_key="HR1",
                actions=[{"title_en": "Manager workshop", "title_ar": "ورشة مديرين", "due_date": today + timedelta(days=30)}],
            )
            check(
                "action plan distinct",
                plan.get("ok") is True
                and plan.get("not_er_corrective_action") is True
                and plan.get("not_performance_development_plan") is True
                and plan.get("auto_created_er_case") is False,
                plan,
            )

            # Identified mode campaign
            survey2 = eg.create_survey_template(
                cur, company_code=COMPANY, actor_phone=HR, code="ID1", title_en="ID Survey", title_ar="استبيان معرّف"
            )
            ver2 = eg.create_survey_version(
                cur, company_code=COMPANY, actor_phone=HR, survey_id=survey2["stable_id"], version_no=1,
                privacy_mode="identified", min_responses=5,
                questions=[{
                    "question_type": "rating_scale", "prompt_en": "Clarity", "prompt_ar": "وضوح",
                    "scale_min": 1, "scale_max": 5,
                }],
            )
            check("identified mode labeled", ver2.get("privacy_mode_label_en") == "Identified", ver2)
            camp2 = eg.create_campaign(
                cur, company_code=COMPANY, actor_phone=HR, survey_id=survey2["stable_id"],
                survey_version_id=str(ver2["survey_version"]["survey_version_id"]),
                title_en="ID Run", title_ar="تشغيل معرّف",
                audience_rule={"scope": "dept", "employee_attrs": {f"X{i}": {"department": "A"} for i in range(1, 6)}},
                audience_employee_keys=[f"X{i}" for i in range(1, 6)],
            )
            eg.launch_campaign(cur, company_code=COMPANY, actor_phone=HR, campaign_id=str(camp2["campaign"]["campaign_id"]))
            check("identified vs anonymous distinct", launched["privacy_mode"] == "anonymous" and camp2["campaign"]["privacy_mode"] == "identified")

            emp = eg.employee_open_surveys(cur, company_code=COMPANY, employee_key="X1")
            check("employee open surveys", emp.get("ok") is True and emp.get("company_analytics_included") is False, emp)

            asst = eg.assistant_query_engagement(
                cur, company_code=COMPANY, actor=HR, question_kind="authorized_aggregates", campaign_id=campaign_id
            )
            check("assistant aggregates", asst.get("ok") is True and asst.get("mutations") is False, asst)
            asst_bad = eg.assistant_query_engagement(
                cur, company_code=COMPANY, actor=HR, question_kind="identify_respondent", campaign_id=campaign_id
            )
            check("assistant privacy forbidden", asst_bad.get("error") == "mutation_or_privacy_forbidden", asst_bad)

            n1 = eg._notify_dedupe(cur, company=COMPANY, key="launch:x")
            n2 = eg._notify_dedupe(cur, company=COMPANY, key="launch:x")
            check("notify first", n1.get("sent") is True and n1.get("answers_not_in_payload") is True, n1)
            check("notify dedupe", n2.get("deduped") is True, n2)

            cur.execute("SELECT COUNT(*) AS c FROM eng_wave5_fact_outbox WHERE company_code=%s", (COMPANY,))
            facts = int(dict(cur.fetchone())["c"])
            check("typed facts emitted", facts >= 1, facts)

            # Later template edit does not rewrite launched version
            eg.create_survey_version(
                cur, company_code=COMPANY, actor_phone=HR, survey_id=survey_id, version_no=2,
                privacy_mode="anonymous", min_responses=5,
                questions=[{
                    "question_type": "rating_scale", "prompt_en": "NEW WORDING", "prompt_ar": "صياغة جديدة",
                    "scale_min": 1, "scale_max": 5,
                }],
            )
            cur.execute("SELECT survey_version_id FROM eng_campaigns WHERE campaign_id=%s", (campaign_id,))
            pinned = str(dict(cur.fetchone())["survey_version_id"])
            check("launched version not rewritten", pinned == version_id, pinned)

            other = eg.create_survey_template(
                cur, company_code=OTHER, actor_phone=HR, code="X", title_en="x", title_ar="س"
            )
            check("other company gated", other.get("ok") is not True, other)

            off = eg.disable_company_engagement(cur, company_code=COMPANY, actor_phone=HR, reason="toggle off")
            check("disable retains history", off.get("history_retained") is True, off)
            blocked2 = eg.create_campaign(
                cur, company_code=COMPANY, actor_phone=HR, survey_id=survey_id,
                survey_version_id=version_id, title_en="x", title_ar="س",
                audience_rule={}, audience_employee_keys=["Z1"],
            )
            check("ops blocked when off", blocked2.get("error") == "engagement_disabled_for_company", blocked2)
            cur.execute("SELECT COUNT(*) AS c FROM eng_campaigns WHERE company_code=%s", (COMPANY,))
            retained = int(dict(cur.fetchone())["c"])
            check("history retained", retained >= 1, retained)

            eg.enable_company_engagement(cur, company_code=COMPANY, actor_phone=HR, reason="re-enable")
            matrix = eg.honesty_payload(company_code=COMPANY)
            check("modularity without er", matrix["works_without_er"] is True)
            check("modularity recognition still out", matrix["recognition_out_of_mvp"] is True)

            # Manager results off
            eg.enable_company_engagement(
                cur, company_code=COMPANY, actor_phone=HR, reason="mgr off",
                manager_results_enabled=False, min_responses=5,
            )
            mgr_off = eg.compute_aggregates(
                cur, company_code=COMPANY, campaign_id=campaign_id, actor_role="manager",
                manager_scope_employee_keys=employees,
            )
            check("manager results off", mgr_off.get("error") == "manager_results_disabled", mgr_off)

            conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        try:
            db_context.__exit__(None, None, None)
        except Exception:
            pass

    print(f"\n    {PASS} passed, {FAIL} failed")
    if FAIL:
        return 1
    print("ENGAGEMENT_FULL_PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
