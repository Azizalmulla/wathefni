#!/usr/bin/env python3
"""Local unit qualification for Talent Pool Classification read/interaction model.

Does not change classifier scoring. Does not start workers. Does not touch production.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import talent_pool_classification as tpc


def main() -> int:
    failures: list[str] = []

    def check(name: str, cond: bool, detail: str = "") -> None:
        if not cond:
            failures.append(f"{name}: {detail}".strip())

    dims = tpc.taxonomy_dimensions()
    check("dimensions", {d["dimension"] for d in dims["dimensions"]} == set(tpc.FILTERABLE_DIMENSIONS))
    check("node_ids_stable", all(n.get("node_id") for d in dims["dimensions"] for n in d["nodes"]))

    parsed = tpc.parse_classification_filter_query(
        {
            "career_area": "fn.finance,fn.technology",
            "likely_role": ["role.accountant"],
            "skill": "skill.python",
            "authority": "confirmed_only",
            "confidence": "High",
            "include_medium_ai": False,
        }
    )
    check("or_within_dimension", parsed["dimension_nodes"]["career_area"] == ["fn.finance", "fn.technology"])
    check("and_across_dimensions", set(parsed["dimension_nodes"]) >= {"career_area", "likely_role", "skill"})

    sql, params = tpc.classification_filter_sql(
        company_code="WATHEFNI",
        filters={"career_area": "fn.technology", "skill": "skill.python", "authority": "either"},
    )
    check("server_sql_exists", "EXISTS" in sql and "AND" in sql)
    check("server_sql_uses_ids", "fn.technology" in str(params) and "skill.python" in str(params))

    unclassified_sql, _ = tpc.classification_filter_sql(
        company_code="WATHEFNI",
        filters={"confidence": "Unclassified"},
    )
    check("unclassified_sql", "NOT EXISTS" in unclassified_sql)

    high = tpc.effective_classification(
        suggestions=[
            {
                "node_id": "fn.technology",
                "node_type": "career_function",
                "label_en": "Technology",
                "confidence_band": "High",
                "state": "active",
                "evidence": [{"kind": "skill", "text": "Python"}],
            },
            {
                "node_id": "role.software_engineer",
                "node_type": "likely_role",
                "label_en": "Software Engineer",
                "confidence_band": "High",
                "state": "active",
                "evidence": [{"kind": "role", "text": "software engineer"}],
            },
        ],
        review_events=[],
    )
    check("chip_high", bool(high.get("chip")) and "Technology" in str(high.get("chip")))

    medium = tpc.effective_classification(
        suggestions=[
            {
                "node_id": "fn.technology",
                "node_type": "career_function",
                "label_en": "Technology",
                "confidence_band": "Medium",
                "state": "active",
                "evidence": [{"kind": "skill", "text": "Python"}],
            }
        ],
        review_events=[],
    )
    check("no_medium_chip", not medium.get("chip"))

    rejected = tpc.effective_classification(
        suggestions=[
            {
                "node_id": "fn.technology",
                "node_type": "career_function",
                "label_en": "Technology",
                "confidence_band": "High",
                "state": "active",
                "evidence": [{"kind": "skill", "text": "Python"}],
            }
        ],
        review_events=[{"action": "reject", "node_id": "fn.technology", "created_at": "1"}],
    )
    check("no_rejected_chip", not rejected.get("chip"))

    corrected = tpc.append_review_event(
        action="correct",
        node_id="fn.finance",
        previous_node_id="fn.technology",
        actor_user_id="tester",
        node_type="career_function",
        label_en="Finance",
    )
    check("correct_is_supersede_shape", corrected["action"] == "correct" and corrected["previous_node_id"] == "fn.technology")

    added = tpc.append_review_event(
        action="add",
        node_id="skill.python",
        actor_user_id="tester",
        node_type="skill",
        label_en="Python",
    )
    check("add_is_hr_event", added["action"] == "add" and added["node_id"] == "skill.python")

    saved = tpc.normalize_saved_view_classification(
        {"classification": {"career_area": ["missing.node"], "authority": "either", "include_medium_ai": True}}
    )
    check("saved_view_versioned", saved["schema"] == tpc.SAVED_VIEW_CLASSIFICATION_SCHEMA)
    check("deprecated_disclosed", bool(saved["deprecated_nodes"]))

    section = tpc.profile_classification_section(
        run={
            "run_id": "r1",
            "status": "classified",
            "taxonomy_version": dims["taxonomy_version"],
            "classifier_version": tpc.CLASSIFIER_VERSION,
            "document_version_id": "d1",
            "extraction_version_id": "e1",
        },
        suggestions=high["ai_suggested"],
        review_events=[added, corrected],
        runs=[
            {
                "run_id": "r1",
                "status": "classified",
                "taxonomy_version": dims["taxonomy_version"],
                "classifier_version": tpc.CLASSIFIER_VERSION,
                "document_version_id": "d1",
                "extraction_version_id": "e1",
            },
            {
                "run_id": "r0",
                "status": "classified",
                "taxonomy_version": dims["taxonomy_version"],
                "classifier_version": tpc.CLASSIFIER_VERSION,
                "document_version_id": "d0",
                "extraction_version_id": "e0",
            },
        ],
        runs_total=2,
        runs_offset=0,
        runs_limit=20,
    )
    check("profile_current_stale", section["runs"][0]["currency"] == "current" and section["runs"][1]["currency"] == "stale")
    check("profile_history", len(section["history"]) == 2)
    check("profile_actions", set(section["actions"]) == {"confirm", "reject", "add", "correct"})
    check("no_job_authority", section["job_assignment"] is None and section["hiring_score"] is None)

    # Classifier version must remain v1.2 for this phase
    check("classifier_frozen", tpc.CLASSIFIER_VERSION == "classifier.deterministic_v1.2")

    print(json.dumps({
        "ok": not failures,
        "failures": failures,
        "taxonomy_version": dims["taxonomy_version"],
        "classifier_version": tpc.CLASSIFIER_VERSION,
        "chip": high.get("chip"),
        "filter_sql_preview": sql[:180],
    }, indent=2))
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
