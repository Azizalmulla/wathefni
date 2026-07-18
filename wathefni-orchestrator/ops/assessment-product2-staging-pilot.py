#!/usr/bin/env python3
"""Explicit synthetic, non-decision staging pilot for Assessment Product-2.

Normal staging and production services keep authoring disabled.  This harness
requires a time-bounded process override plus an exact confirmation string,
uses recorded model responses, sends no messages, touches no candidate rows,
and removes every synthetic authoring fixture in a finally block.
"""

from __future__ import annotations

import argparse
import json
import os
import uuid
from typing import Any

import app
import assessment_ai_contracts as contracts
import assessment_ai_service as service
import assessment_lifecycle as lifecycle


PILOT_COMPANY = "WATHEFNI_P2_SYNTHETIC"
CONFIRM = "staging-product2-synthetic-nondecision-pilot"
LIVE_TABLES = (
    "assessment_items",
    "assessment_batteries",
    "assessment_content_versions",
    "assessment_attempts",
    "assessment_responses",
    "assessment_scores",
    "assessment_reports",
    "applications",
    "interviews",
    "offers",
    "employees",
    "outbound_delivery_events",
)


def table_counts(cur: Any) -> dict[str, int]:
    counts: dict[str, int] = {}
    for table in LIVE_TABLES:
        cur.execute("SELECT to_regclass(%s) IS NOT NULL AS exists", (f"public.{table}",))
        if not bool(cur.fetchone()["exists"]):
            counts[table] = 0
            continue
        cur.execute(f"SELECT COUNT(*)::int AS count FROM {table}")
        counts[table] = int(cur.fetchone()["count"])
    return counts


def pass_dimensions(names: list[str]) -> list[dict[str, Any]]:
    return [
        {
            "dimension": name,
            "verdict": "pass",
            "severity": "none",
            "confidence": 0.99,
            "evidence": [],
            "explanation": "Synthetic recorded fixture satisfies this gate.",
        }
        for name in names
    ]


def pass_equivalence_dimensions(names: list[str]) -> list[dict[str, Any]]:
    return [
        {
            "dimension": name,
            "verdict": "pass",
            "severity": "none",
            "evidence": [],
            "explanation": "Synthetic recorded bilingual fixture satisfies this gate.",
        }
        for name in names
    ]


def recorded_adapter(registry: dict[str, Any], prompt: dict[str, Any], run: dict[str, Any]) -> service.ProviderResult:
    run_kind = run["run_kind"]
    source = run["input_json"]
    if run_kind == "author_primary":
        payload = {
            "schema_version": contracts.SCHEMA_VERSION,
            "request_id": source["request_id"],
            "items": [
                {
                    "draft_local_id": "synthetic-warehouse-allocation",
                    "locale": "en",
                    "prompt_text": "In the synthetic Product Two pilot, a supervisor has 12 equal work units. What is one quarter of the units?",
                    "choices": [
                        {"key": "A", "text": "2 units"},
                        {"key": "B", "text": "3 units"},
                        {"key": "C", "text": "4 units"},
                        {"key": "D", "text": "6 units"},
                    ],
                    "proposed_answer_key": "B",
                    "proposed_scoring": {
                        "family": "answer_key",
                        "correct_points": 1,
                        "incorrect_points": 0,
                        "max_points": 1,
                        "choice_points": [],
                    },
                    "rationale": "Tests basic proportional reasoning using synthetic values.",
                    "explanation": "One quarter of twelve equals three.",
                    "distractor_rationales": [
                        {"choice_key": "A", "rationale": "Divides by six."},
                        {"choice_key": "C", "rationale": "Divides by three."},
                        {"choice_key": "D", "rationale": "Divides by two."},
                    ],
                    "competency_tags": ["numerical_reasoning"],
                    "skill_tags": ["fractions"],
                    "role_tags": ["supervisor"],
                    "difficulty_rationale": "A direct one-step calculation.",
                    "assumptions": [],
                    "original_content_attested": True,
                    "safety_flags": [],
                }
            ],
            "generation_notes": ["Recorded synthetic staging fixture."],
            "refusal_reason": None,
        }
    elif run_kind == "review_secondary":
        payload = {
            "schema_version": contracts.SCHEMA_VERSION,
            "draft_revision_id": source["draft_revision_id"],
            "draft_sha256": source["draft_sha256"],
            "reviewer_role_version": str(registry["registry_version_id"]),
            "dimensions": pass_dimensions(source["review_dimensions"]),
            "overall_recommendation": "pass",
            "critical_findings": [],
            "refusal_reason": None,
        }
    elif run_kind == "adapt_bilingual":
        translated = {
            "A": "2 وحدات",
            "B": "3 وحدات",
            "C": "4 وحدات",
            "D": "6 وحدات",
        }
        payload = {
            "schema_version": contracts.SCHEMA_VERSION,
            "source_revision_id": source["source_revision_id"],
            "source_sha256": source["source_sha256"],
            "source_locale": source["source_locale"],
            "target_locale": source["target_locale"],
            "adapted_prompt_text": "في تجربة المنتج الثانية الاصطناعية، لدى مشرف 12 وحدة عمل متساوية. كم يساوي ربع عدد الوحدات؟",
            "adapted_choices": [
                {"key": choice["key"], "text": translated[choice["key"]]}
                for choice in source["source_choices"]
            ],
            "terminology_decisions": ["استخدام عبارة وحدة عمل."],
            "cultural_adaptations": [],
            "back_translation_summary": "A supervisor has 12 equal work units; asks for one quarter.",
            "preserved_invariants": ["option_keys", "answer_key", "scoring", "difficulty"],
            "refusal_reason": None,
        }
    elif run_kind == "review_bilingual":
        payload = {
            "schema_version": contracts.SCHEMA_VERSION,
            "translation_pair_id": source["translation_pair_id"],
            "source_sha256": source["source_sha256"],
            "target_sha256": source["target_sha256"],
            "findings": pass_equivalence_dimensions(source["review_dimensions"]),
            "overall_recommendation": "pass",
            "refusal_reason": None,
        }
    else:
        raise RuntimeError(f"recorded_fixture_missing:{run_kind}")
    return service.ProviderResult(
        payload=payload,
        provider_response_model=str(
            registry.get("qualified_provider_model_id") or registry["requested_model"]
        ),
        provider_request_id=f"recorded-{uuid.uuid4()}",
        input_tokens=0,
        output_tokens=0,
        cached_tokens=0,
        latency_ms=1,
    )


def cleanup(cur: Any) -> None:
    cur.execute("DELETE FROM assessment_translation_pairs WHERE company_code=%s", (PILOT_COMPANY,))
    cur.execute("DELETE FROM assessment_authoring_events WHERE company_code=%s", (PILOT_COMPANY,))
    cur.execute("DELETE FROM assessment_item_reviews WHERE company_code=%s", (PILOT_COMPANY,))
    cur.execute("DELETE FROM assessment_ai_runs WHERE company_code=%s", (PILOT_COMPANY,))
    cur.execute("DELETE FROM assessment_item_drafts WHERE company_code=%s", (PILOT_COMPANY,))
    cur.execute("DELETE FROM assessment_blueprint_versions WHERE company_code=%s", (PILOT_COMPANY,))
    cur.execute("DELETE FROM assessment_eval_runs WHERE company_code=%s", (PILOT_COMPANY,))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--confirm", required=True)
    args = parser.parse_args()
    if args.confirm != CONFIRM:
        raise RuntimeError("assessment_product2_pilot_confirmation_mismatch")
    identity = app.assert_runtime_environment_binding()
    if identity.application_environment != "staging" or identity.database_environment != "staging":
        raise RuntimeError("assessment_product2_pilot_refuses_non_staging")
    service.assert_authoring_enabled(
        environment=identity.application_environment,
        flag_value=os.environ.get("WATHEFNI_ASSESSMENT_AUTHORING"),
    )
    if str(os.environ.get("WATHEFNI_DELIVERY_MODE") or "").lower() != "dry_run":
        raise RuntimeError("assessment_product2_pilot_requires_dry_run_delivery")

    app.ensure_schema(force=True)
    required_roles = {
        "assessment.author_primary",
        "assessment.review_secondary",
        "assessment.adapt_bilingual",
        "assessment.review_bilingual",
    }
    with app.db_connect() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT role_key FROM assessment_ai_model_registry_versions
                WHERE enabled IS TRUE AND retired_at IS NULL
                  AND qualified_provider_model_id IS NOT NULL
                  AND 'staging'=ANY(allowed_environments)
                """
            )
            qualified_roles = {str(row["role_key"]) for row in cur.fetchall()}
            cur.execute(
                "SELECT 1 FROM pg_roles WHERE rolname='wathefni_assessment_ai_runner'"
            )
            least_privilege_role_ready = bool(cur.fetchone())
    missing_roles = sorted(required_roles - qualified_roles)
    if missing_roles:
        raise RuntimeError(
            f"assessment_product2_pilot_requires_qualified_model_roles:{','.join(missing_roles)}"
        )
    if not least_privilege_role_ready:
        raise RuntimeError("assessment_product2_pilot_requires_least_privilege_db_role")
    evidence: dict[str, Any] = {
        "environment": identity.public(),
        "recorded_responses_only": True,
        "candidate_data_used": False,
        "outbound_sent": False,
        "publish_available": False,
        "qualified_model_roles": sorted(qualified_roles),
        "least_privilege_db_role_ready": least_privilege_role_ready,
    }
    before: dict[str, int] = {}
    try:
        with app.db_connect() as conn:
            with conn.cursor() as cur:
                cleanup(cur)
                before = table_counts(cur)
                blueprint = service.create_blueprint_version(
                    cur,
                    company_code=PILOT_COMPANY,
                    blueprint_key="synthetic_product2_v1",
                    blueprint={
                        "battery_key": "wathefni_ability_v1",
                        "source_locale": "en",
                        "required_locales": ["en", "ar"],
                        "section": "Synthetic numerical reasoning",
                        "constructs": ["proportional_reasoning"],
                        "item_type": "single_choice",
                        "difficulty_target": "easy",
                        "reading_level": "plain",
                        "role_context": ["supervisor"],
                        "allowed_context": ["synthetic work allocation"],
                        "prohibited_content": ["candidate data", "third-party tests", "protected attributes"],
                        "scoring_family": "answer_key",
                        "choice_count": 4,
                        "originality_policy_version": service.ORIGINALITY_POLICY_VERSION,
                    },
                    created_by_user_id="synthetic-author",
                    approve=True,
                    approved_by_user_id="synthetic-blueprint-approver",
                )
                request = service.build_authoring_request(blueprint, requested_item_count=1)
                run = service.enqueue_run(
                    cur,
                    company_code=PILOT_COMPANY,
                    role_key="assessment.author_primary",
                    environment="staging",
                    input_payload=request,
                    created_by_user_id="synthetic-author",
                    blueprint_version_id=str(blueprint["blueprint_version_id"]),
                )
            conn.commit()
        generated = service.process_queued_run(app, str(run["run_id"]), adapter=recorded_adapter)
        created = generated["output_json"]["created_drafts"][0]
        with app.db_connect() as conn:
            with conn.cursor() as cur:
                secondary = service.enqueue_secondary_review(
                    cur,
                    company_code=PILOT_COMPANY,
                    draft_id=created["draft_id"],
                    actor_user_id="synthetic-author",
                    environment="staging",
                )
            conn.commit()
        secondary_result = service.process_queued_run(app, str(secondary["run_id"]), adapter=recorded_adapter)
        with app.db_connect() as conn:
            with conn.cursor() as cur:
                adaptation = service.enqueue_bilingual_adaptation(
                    cur,
                    company_code=PILOT_COMPANY,
                    draft_id=created["draft_id"],
                    target_locale="ar",
                    actor_user_id="synthetic-author",
                    environment="staging",
                )
            conn.commit()
        adaptation_result = service.process_queued_run(app, str(adaptation["run_id"]), adapter=recorded_adapter)
        pair_id = adaptation_result["output_json"]["translation_pair_id"]
        with app.db_connect() as conn:
            with conn.cursor() as cur:
                bilingual = service.enqueue_bilingual_review(
                    cur,
                    company_code=PILOT_COMPANY,
                    translation_pair_id=pair_id,
                    actor_user_id="synthetic-author",
                    environment="staging",
                )
            conn.commit()
        bilingual_result = service.process_queued_run(app, str(bilingual["run_id"]), adapter=recorded_adapter)
        with app.db_connect() as conn:
            with conn.cursor() as cur:
                ready, review_evidence = service.product2_human_transition_ready(
                    cur,
                    draft_id=created["draft_id"],
                    company_code=PILOT_COMPANY,
                )
                if not ready:
                    raise RuntimeError("synthetic_product2_human_gate_not_ready")
                service.record_bilingual_human_review(
                    cur,
                    company_code=PILOT_COMPANY,
                    translation_pair_id=pair_id,
                    actor_user_id="synthetic-bilingual-reviewer",
                    decision="approve",
                    notes="Synthetic non-decision pilot.",
                )
                target_draft_id = adaptation_result["output_json"]["target_draft_id"]
                target_revision_id = adaptation_result["output_json"]["target_revision_id"]
                target_ready, target_review_evidence = service.product2_human_transition_ready(
                    cur,
                    draft_id=target_draft_id,
                    company_code=PILOT_COMPANY,
                )
                if not target_ready:
                    raise RuntimeError("synthetic_product2_bilingual_human_gate_not_ready")
                final_lifecycles: dict[str, str] = {}
                for locale, draft_ref, revision_ref in (
                    ("en", created["draft_id"], created["draft_revision_id"]),
                    ("ar", target_draft_id, target_revision_id),
                ):
                    current = "automated_review"
                    for target in ("human_review", "pilot", "approved"):
                        if not lifecycle.validate_authoring_transition(current, target):
                            raise RuntimeError(f"synthetic_product2_invalid_transition:{current}:{target}")
                        cur.execute(
                            """
                            UPDATE assessment_item_drafts SET lifecycle_status=%s,updated_at=now()
                            WHERE draft_id=%s AND company_code=%s AND lifecycle_status=%s
                            """,
                            (target, draft_ref, PILOT_COMPANY, current),
                        )
                        service.record_authoring_event(
                            cur,
                            company_code=PILOT_COMPANY,
                            draft_id=draft_ref,
                            draft_revision_id=revision_ref,
                            event_type="synthetic_human_transition",
                            actor_type="human",
                            actor_user_id=f"synthetic-{locale}-{target}-reviewer",
                            from_status=current,
                            to_status=target,
                            payload={
                                "non_decision_pilot": True,
                                "human_originality_attested": target == "human_review",
                                "published": False,
                            },
                        )
                        current = target
                    final_lifecycles[locale] = current
                evidence.update(
                    {
                        "primary_status": generated["status"],
                        "secondary_status": secondary_result["status"],
                        "adaptation_status": adaptation_result["status"],
                        "bilingual_review_status": bilingual_result["status"],
                        "human_gate_ready": ready,
                        "bilingual_human_gate_ready": target_ready,
                        "review_digest_evidence": review_evidence,
                        "bilingual_review_digest_evidence": target_review_evidence,
                        "final_lifecycles": final_lifecycles,
                        "final_lifecycle": (
                            "approved"
                            if set(final_lifecycles.values()) == {"approved"}
                            else "incomplete"
                        ),
                    }
                )
            conn.commit()
    finally:
        with app.db_connect() as conn:
            with conn.cursor() as cur:
                cleanup(cur)
                after = table_counts(cur)
            conn.commit()
        evidence["synthetic_cleanup_complete"] = True
        evidence["live_table_counts_before"] = before
        evidence["live_table_counts_after"] = after
        evidence["live_tables_unchanged"] = before == after
    print(json.dumps(evidence, ensure_ascii=False, sort_keys=True, default=str))
    return 0 if evidence.get("live_tables_unchanged") and evidence.get("final_lifecycle") == "approved" else 1


if __name__ == "__main__":
    raise SystemExit(main())
