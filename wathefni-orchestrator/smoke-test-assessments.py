#!/usr/bin/env python3
"""Smoke tests for deterministic assessment scoring helpers."""

import app


def assert_true(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def main() -> None:
    validation = app.validate_assessment_item_bank()
    assert_true(validation["ok"], f"assessment item bank must validate: {validation.get('errors')}")

    item = app.ASSESSMENT_ITEM_BANK[0]
    competency_item = next(seeded for seeded in app.ASSESSMENT_ITEM_BANK if seeded["section"] == "competency_judgment")
    assert_true(app.parse_assessment_answer("B", item) == "B", "single-letter answer must parse")
    assert_true(app.parse_assessment_answer("b) 10", item) == "B", "letter with text must parse")
    assert_true(app.parse_assessment_answer("10", item) == "B", "exact choice text must parse")
    assert_true(app.parse_assessment_answer("not sure", item) is None, "unknown answer must not be guessed")

    assert_true(app.assessment_band(85) == "strong", "80+ must be strong")
    assert_true(app.assessment_band(65) == "qualified", "60+ must be qualified")
    assert_true(app.assessment_band(45) == "needs_review", "40+ must need review")
    assert_true(app.assessment_band(20) == "low", "below 40 must be low")
    assert_true(app.selected_item_score(item, "B") == (1.0, True), "ability item must score by answer key")
    competency_score, competency_correct = app.selected_item_score(competency_item, "B")
    assert_true(competency_score == 5.0 and competency_correct is None, "competency item must score by keyed choice")
    norms = app.ability_norm_scores(75)
    assert_true({"percentile", "t_score", "sten", "band"} <= set(norms), "ability norms must include SHL-style transforms")
    empirical_norms = app.ability_norm_scores(
        75,
        {
            "norm_key": "fixture_norm",
            "sample_size": 250,
            "source": "empirical_company_completed_attempts",
            "percentiles": {"p10": 40, "p25": 55, "p50": 70, "p75": 82, "p90": 92},
        },
    )
    assert_true(empirical_norms["norm_source"] == "empirical_company_completed_attempts", "empirical norms must be used when sample size is credible")
    assert_true(app.percentile_cutoff([10, 20, 30, 40], 50) == 25, "percentile cutoff must interpolate")
    assert_true(app.percentile_rank_from_cutoffs(75, {"p50": 70, "p75": 82}) > 50, "percentile rank must interpolate from cutoffs")

    attempt = {"current_item_index": 0, "total_items": 6}
    question = app.format_assessment_question(attempt, item)
    assert_true("Question 1/6" in question, "question must include progress")
    assert_true("Reply with A, B, C, or D." in question, "question must include answer format")
    assert_true("Wathefni" not in item["prompt_text"] or item["answer_key"], "seeded items must have answer keys")

    keys = {seeded["item_id"] for seeded in app.ASSESSMENT_ITEM_BANK}
    assert_true(len(keys) == len(app.ASSESSMENT_ITEM_BANK), "assessment item ids must be unique")
    assert_true(
        all(seeded.get("answer_key") or seeded.get("scoring", {}).get("type") == "competency_keyed" for seeded in app.ASSESSMENT_ITEM_BANK),
        "all seeded items need answer keys or competency scoring metadata",
    )
    assert_true("teller" in app.NBK_ROLE_PROFILES, "NBK teller role profile must be seeded")
    assert_true("hr_recruiter" in app.NBK_ROLE_PROFILES, "HR/recruiter role profile must be seeded")
    assert_true(len(app.NBK_COMPETENCY_FRAMEWORK["competencies"]) >= 20, "NBK competency framework must expose at least 20 competencies")
    assert_true(len(app.ASSESSMENT_ITEM_BANK) >= 22, "official v1 item bank must have expanded baseline coverage")
    section_counts = {}
    for seeded in app.ASSESSMENT_ITEM_BANK:
        section_counts[seeded["section"]] = section_counts.get(seeded["section"], 0) + 1
    assert_true(section_counts.get("numerical_reasoning", 0) >= 4, "numerical reasoning needs baseline coverage")
    assert_true(section_counts.get("verbal_reasoning", 0) >= 4, "verbal reasoning needs baseline coverage")
    assert_true(section_counts.get("logical_reasoning", 0) >= 4, "logical reasoning needs baseline coverage")
    assert_true(section_counts.get("competency_judgment", 0) >= 10, "competency judgment needs baseline coverage")

    items = app.ASSESSMENT_ITEM_BANK
    item_by_id = {seeded["item_id"]: seeded for seeded in items}
    fixture_keys = {
        seeded["item_id"]: seeded.get("answer_key") or "B"
        for seeded in items
    }
    responses = []
    for order, item_id in enumerate(fixture_keys, 1):
        seeded = item_by_id[item_id]
        score, is_correct = app.selected_item_score(seeded, fixture_keys[item_id])
        responses.append({
            "item_id": item_id,
            "item_order": order,
            "selected_key": fixture_keys[item_id],
            "is_correct": is_correct,
            "score_numeric": score,
        })
    report_one = app.build_assessment_report_json(
        attempt={"attempt_id": "fixture", "app_key": "fixture-app", "candidate_name": "Fixture", "position_title": "Teller"},
        items=items,
        responses=responses,
    )
    report_two = app.build_assessment_report_json(
        attempt={"attempt_id": "fixture", "app_key": "fixture-app", "candidate_name": "Fixture", "position_title": "Teller"},
        items=items,
        responses=responses,
    )
    assert_true(report_one == report_two, "same fixture responses must produce identical official report JSON")
    assert_true(report_one["job_match"]["role_profile_key"] == "teller", "Teller fixture must map to teller role profile")
    assert_true(report_one["job_match"]["fit_band"] == "high", "strong fixture must produce high Teller fit")
    assert_true("percentile" in next(iter(report_one["ability_scores"].values())), "ability score must include percentile")
    report_sections = report_one["report_sections"]
    assert_true("verify_ability" in report_sections, "official report JSON must include Verify-style ability section")
    assert_true("competency_profile" in report_sections, "official report JSON must include competency profile section")
    assert_true("mass_assessment" in report_sections, "official report JSON must include mass-assessment section")
    assert_true(report_sections["interview_probes"], "official report JSON must include deterministic interview probes")
    html_preview = app.assessment_report_html({"attempt": report_one, "report": report_one, "responses": responses}).body.decode("utf-8")
    assert_true("Official deterministic score JSON" in html_preview, "HTML report artifact must identify official scoring source")
    assert_true("Structured Interview Probes" in html_preview, "HTML report artifact must expose interview probes")
    assert_true(report_one["guardrails"]["ai_may_change_scores"] is False, "AI must not be allowed to change official scores")
    report_empirical = app.build_assessment_report_json(
        attempt={"attempt_id": "fixture", "app_key": "fixture-app", "candidate_name": "Fixture", "position_title": "Teller"},
        items=items,
        responses=responses,
        norm_lookup={
            "numerical_reasoning": {
                "norm_key": "fixture_num_empirical",
                "sample_size": 250,
                "source": "empirical_company_completed_attempts",
                "percentiles": {"p10": 40, "p25": 55, "p50": 70, "p75": 82, "p90": 92},
            }
        },
    )
    assert_true("fixture_num_empirical" in report_empirical["norm_version"], "official report must carry empirical norm version when active")

    print("assessment smoke tests passed")


if __name__ == "__main__":
    main()
