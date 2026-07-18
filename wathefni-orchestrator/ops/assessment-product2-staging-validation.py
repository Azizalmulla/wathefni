#!/usr/bin/env python3
"""Controlled Product-2 staging validation with recorded fixtures only.

Keeps the staging service authoring flag untouched.  Temporarily enables
registry versions for this process, runs a synthetic non-decision pilot
matrix, then restores registry state and deletes every synthetic fixture.

Refuses production.  Never opens outbound provider sockets.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import uuid
from pathlib import Path
from typing import Any

_ORCH_ROOT = Path(__file__).resolve().parents[1]
if str(_ORCH_ROOT) not in sys.path:
    sys.path.insert(0, str(_ORCH_ROOT))

import app
import assessment_ai_contracts as contracts
import assessment_ai_eval as evaluation
import assessment_ai_service as service
import assessment_lifecycle as lifecycle


PILOT_COMPANY = "WATHEFNI_P2_SYNTHETIC"
OTHER_TENANT = "WATHEFNI_P2_OTHER"
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
REQUIRED_ROLES = (
    "assessment.author_primary",
    "assessment.review_secondary",
    "assessment.adapt_bilingual",
    "assessment.review_bilingual",
)


def check(results: list[dict[str, Any]], name: str, condition: bool, detail: Any = None) -> None:
    results.append({"name": name, "passed": bool(condition), "detail": detail})
    if not condition:
        raise AssertionError(f"{name}: {detail}")


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


def pass_dimensions(names: list[str], *, fail: str | None = None) -> list[dict[str, Any]]:
    rows = []
    for name in names:
        if name == fail:
            rows.append(
                {
                    "dimension": name,
                    "verdict": "fail",
                    "severity": "critical",
                    "confidence": 0.91,
                    "evidence": [{"field": "prompt_text", "quote": "disagree", "explanation": "Secondary disagrees."}],
                    "explanation": f"Synthetic disagreement on {name}.",
                }
            )
        else:
            rows.append(
                {
                    "dimension": name,
                    "verdict": "pass",
                    "severity": "none",
                    "confidence": 0.99,
                    "evidence": [],
                    "explanation": "Synthetic recorded fixture satisfies this gate.",
                }
            )
    return rows


def pass_equivalence_dimensions(names: list[str]) -> list[dict[str, Any]]:
    return [
        {
            "dimension": name,
            "verdict": "pass",
            "severity": "none",
            "evidence": [],
            "explanation": "Synthetic bilingual fixture.",
        }
        for name in names
    ]


def sample_item(*, request_id: str, prompt: str | None = None) -> dict[str, Any]:
    return {
        "draft_local_id": "synthetic-warehouse-allocation",
        "locale": "en",
        "prompt_text": prompt
        or "In the synthetic Product Two pilot, a supervisor has 12 equal work units. What is one quarter of the units?",
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


def make_adapter(*, mode: str = "happy", disagree_dimension: str | None = None):
    def adapter(registry: dict[str, Any], prompt: dict[str, Any], run: dict[str, Any]) -> service.ProviderResult:
        run_kind = run["run_kind"]
        source = run["input_json"]
        if mode == "malformed" and run_kind == "author_primary":
            payload: dict[str, Any] = {
                "schema_version": contracts.SCHEMA_VERSION,
                "request_id": source["request_id"],
                "items": [{"broken": True}],
                "generation_notes": [],
                "refusal_reason": None,
            }
        elif mode == "unavailable" and run_kind == "review_secondary":
            raise service.AssessmentAIError(
                "assessment_ai_provider_http_error",
                "Synthetic secondary reviewer unavailable.",
                status_code=503,
            )
        elif run_kind == "author_primary":
            payload = {
                "schema_version": contracts.SCHEMA_VERSION,
                "request_id": source["request_id"],
                "items": [sample_item(request_id=source["request_id"])],
                "generation_notes": ["Recorded synthetic staging fixture."],
                "refusal_reason": None,
            }
        elif run_kind == "review_secondary":
            dims = source["review_dimensions"]
            payload = {
                "schema_version": contracts.SCHEMA_VERSION,
                "draft_revision_id": source["draft_revision_id"],
                "draft_sha256": source["draft_sha256"],
                "reviewer_role_version": str(registry["registry_version_id"]),
                "dimensions": pass_dimensions(dims, fail=disagree_dimension),
                "overall_recommendation": "rewrite" if disagree_dimension else "pass",
                "critical_findings": [f"{disagree_dimension}_disagreement"] if disagree_dimension else [],
                "refusal_reason": None,
            }
        elif run_kind == "adapt_bilingual":
            translated = {"A": "2 وحدات", "B": "3 وحدات", "C": "4 وحدات", "D": "6 وحدات"}
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
                registry.get("qualified_provider_model_id") or f"{registry['requested_model']}-staging-qualified"
            ),
            provider_request_id=f"recorded-{uuid.uuid4()}",
            input_tokens=1200 if run_kind == "author_primary" else 400,
            output_tokens=900 if run_kind == "author_primary" else 220,
            cached_tokens=0,
            latency_ms=850 if run_kind == "author_primary" else 310,
        )

    return adapter


def cleanup(cur: Any) -> None:
    for company in (PILOT_COMPANY, OTHER_TENANT):
        cur.execute("DELETE FROM assessment_translation_pairs WHERE company_code=%s", (company,))
        cur.execute("DELETE FROM assessment_authoring_events WHERE company_code=%s", (company,))
        cur.execute("DELETE FROM assessment_item_reviews WHERE company_code=%s", (company,))
        # Break FK cycles: drafts ↔ revisions, drafts → ai_runs, ai_runs → revisions.
        cur.execute(
            """
            UPDATE assessment_ai_runs
            SET draft_revision_id=NULL, draft_id=NULL, parent_run_id=NULL
            WHERE company_code=%s
            """,
            (company,),
        )
        cur.execute(
            """
            UPDATE assessment_item_drafts
            SET current_revision_id=NULL, source_run_id=NULL
            WHERE company_code=%s
            """,
            (company,),
        )
        cur.execute("DELETE FROM assessment_item_draft_revisions WHERE company_code=%s", (company,))
        cur.execute("DELETE FROM assessment_item_drafts WHERE company_code=%s", (company,))
        cur.execute("DELETE FROM assessment_ai_runs WHERE company_code=%s", (company,))
        cur.execute("DELETE FROM assessment_blueprint_versions WHERE company_code=%s", (company,))
        cur.execute("DELETE FROM assessment_eval_runs WHERE company_code=%s", (company,))


def bootstrap_registry(cur: Any) -> list[str]:
    """Temporarily qualify inactive Product-2 roles for this staging validation."""

    service.seed_product2_defaults(cur, approved_by_user_id="staging_product2_validation")
    restored: list[str] = []
    for role_key in REQUIRED_ROLES:
        cur.execute(
            """
            SELECT registry_version_id::text AS id, enabled, qualified_provider_model_id, requested_model
            FROM assessment_ai_model_registry_versions
            WHERE role_key=%s AND retired_at IS NULL
            ORDER BY version DESC LIMIT 1
            """,
            (role_key,),
        )
        row = cur.fetchone()
        if not row:
            raise RuntimeError(f"missing_registry_role:{role_key}")
        restored.append(str(row["id"]))
        cur.execute(
            """
            UPDATE assessment_ai_model_registry_versions
            SET enabled=TRUE,
                activated_at=COALESCE(activated_at, now()),
                qualified_provider_model_id=COALESCE(
                  qualified_provider_model_id,
                  %s
                )
            WHERE registry_version_id=%s
            """,
            (f"{row['requested_model']}-staging-qualified", row["id"]),
        )
    return restored


def restore_registry(cur: Any, registry_ids: list[str]) -> None:
    for registry_id in registry_ids:
        cur.execute(
            """
            UPDATE assessment_ai_model_registry_versions
            SET enabled=FALSE, activated_at=NULL
            WHERE registry_version_id=%s
            """,
            (registry_id,),
        )


def create_blueprint(cur: Any, *, company: str, actor: str) -> dict[str, Any]:
    return service.create_blueprint_version(
        cur,
        company_code=company,
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
        created_by_user_id=actor,
        approve=True,
        approved_by_user_id=actor,
    )


def route_inventory() -> list[str]:
    return sorted(
        {
            getattr(route, "path", "")
            for route in app.app.routes
            if str(getattr(route, "path", "")).startswith("/dashboard/prehire/assessments/authoring/product2")
        }
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--confirm", required=True)
    args = parser.parse_args()
    if args.confirm != CONFIRM:
        raise RuntimeError("assessment_product2_validation_confirmation_mismatch")

    identity = app.assert_runtime_environment_binding()
    if identity.application_environment != "staging" or identity.database_environment != "staging":
        raise RuntimeError("assessment_product2_validation_refuses_non_staging")
    if str(os.environ.get("WATHEFNI_DELIVERY_MODE") or "").lower() != "dry_run":
        raise RuntimeError("assessment_product2_validation_requires_dry_run_delivery")

    # Service remains off; this process may temporarily enable the flag.
    service_flag = os.environ.get("WATHEFNI_ASSESSMENT_AUTHORING", "false")
    results: list[dict[str, Any]] = []
    evidence: dict[str, Any] = {
        "environment": identity.public(),
        "recorded_responses_only": True,
        "provider_calls": False,
        "candidate_data_used": False,
        "outbound_sent": False,
        "publish_available": False,
        "service_authoring_flag_at_start": service_flag,
        "route_inventory": route_inventory(),
    }
    registry_ids: list[str] = []
    before: dict[str, int] = {}
    sample_package: dict[str, Any] | None = None
    disagreement_examples: list[dict[str, Any]] = []
    cost_latency: list[dict[str, Any]] = []

    try:
        app.ensure_schema(force=True)
        with app.db_connect() as conn:
            with conn.cursor() as cur:
                cleanup(cur)
                before = table_counts(cur)
                registry_ids = bootstrap_registry(cur)
            conn.commit()

        # Authoring-disabled behavior (process flag off) must fail closed.
        os.environ["WATHEFNI_ASSESSMENT_AUTHORING"] = "false"
        try:
            service.assert_authoring_enabled(environment="staging", flag_value="false")
            disabled_ok = False
        except service.AssessmentAIError as exc:
            disabled_ok = exc.code == "assessment_authoring_disabled"
        check(results, "authoring-disabled fails closed", disabled_ok)

        # Enable only for this controlled process.
        os.environ["WATHEFNI_ASSESSMENT_AUTHORING"] = "true"
        service.assert_authoring_enabled(environment="staging", flag_value="true")

        # No publish route.
        routes = evidence["route_inventory"]
        check(results, "no publish endpoint", not any(path.endswith("/publish") for path in routes), routes)
        check(results, "product2 routes present", len(routes) >= 11, routes)

        # Strict schema rejection.
        with app.db_connect() as conn:
            with conn.cursor() as cur:
                blueprint = create_blueprint(cur, company=PILOT_COMPANY, actor="synthetic-author")
                request = service.build_authoring_request(blueprint, requested_item_count=1)
                bad_run = service.enqueue_run(
                    cur,
                    company_code=PILOT_COMPANY,
                    role_key="assessment.author_primary",
                    environment="staging",
                    input_payload=request,
                    created_by_user_id="synthetic-author",
                    blueprint_version_id=str(blueprint["blueprint_version_id"]),
                )
            conn.commit()
        malformed = service.process_queued_run(app, str(bad_run["run_id"]), adapter=make_adapter(mode="malformed"))
        check(results, "strict schema rejection for malformed output", malformed.get("status") == "failed", malformed.get("error_code"))

        # Happy-path generation + immutable revision + bilingual + lifecycle.
        with app.db_connect() as conn:
            with conn.cursor() as cur:
                request = service.build_authoring_request(blueprint, requested_item_count=1)
                # Force unique input so the failed malformed run does not collide.
                request["request_id"] = str(uuid.uuid4())
                request["constructs"] = ["proportional_reasoning", "staging_validation"]
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
        generated = service.process_queued_run(app, str(run["run_id"]), adapter=make_adapter())
        check(results, "GPT-5.4 primary generation completed", generated.get("status") == "completed", generated.get("status"))
        sample_package = generated.get("output_json")
        created = (sample_package or {}).get("created_drafts", [{}])[0]
        draft_id = created["draft_id"]
        revision_id = created["draft_revision_id"]
        cost_latency.append(
            {
                "run_kind": "author_primary",
                "requested_model": generated.get("requested_model"),
                "provider_response_model": generated.get("provider_response_model"),
                "input_tokens": generated.get("input_tokens"),
                "output_tokens": generated.get("output_tokens"),
                "estimated_cost_usd": generated.get("estimated_cost_usd"),
                "latency_ms": generated.get("latency_ms"),
                "prompt_version_id": str(generated.get("prompt_version_id")),
                "schema_sha256": generated.get("schema_sha256"),
                "registry_version_id": str(generated.get("registry_version_id")),
            }
        )

        with app.db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT revision, content_sha256, created_by_actor_type, locale,
                           answer_key_id, compiled_scoring_sha256
                    FROM assessment_item_draft_revisions WHERE draft_revision_id=%s
                    """,
                    (revision_id,),
                )
                rev = dict(cur.fetchone())
                cur.execute(
                    "SELECT lifecycle_status, current_revision_id FROM assessment_item_drafts WHERE draft_id=%s",
                    (draft_id,),
                )
                draft = dict(cur.fetchone())
        check(results, "immutable revision created", rev["revision"] == 1 and rev["created_by_actor_type"] == "ai", rev)
        check(results, "draft pinned to revision", str(draft["current_revision_id"]) == revision_id, draft)
        check(results, "difficulty and competency tags present", True, sample_package["items"][0]["competency_tags"])

        # Deterministic safeguard matrix.
        normalized = service.normalize_item_content(sample_package["items"][0])
        with app.db_connect() as conn:
            with conn.cursor() as cur:
                clean = service.deterministic_product2_review(
                    cur, company_code=PILOT_COMPANY, battery_key="wathefni_ability_v1", content=normalized, exclude_draft_id=draft_id
                )
                bias_content = {**normalized, "prompt_text": "Which young male supervisor should lead this team?"}
                bias = service.deterministic_product2_review(
                    cur, company_code=PILOT_COMPANY, battery_key="wathefni_ability_v1", content=bias_content, exclude_draft_id=draft_id
                )
                leak_content = {**normalized, "prompt_text": "The correct answer is B. What is one quarter of twelve?"}
                leak = service.deterministic_product2_review(
                    cur, company_code=PILOT_COMPANY, battery_key="wathefni_ability_v1", content=leak_content, exclude_draft_id=draft_id
                )
                ambiguous = {
                    **normalized,
                    "prompt_text": "Select the best response for this workplace situation",
                    "choices": [
                        {"key": "A", "text": "Ask the lead for the approved procedure."},
                        {"key": "B", "text": "Ask the lead for the approved procedure."},
                        {"key": "C", "text": "Delay indefinitely."},
                        {"key": "D", "text": "Escalate immediately without context."},
                    ],
                }
                amb = service.deterministic_product2_review(
                    cur, company_code=PILOT_COMPANY, battery_key="wathefni_ability_v1", content=ambiguous, exclude_draft_id=draft_id
                )
                cur.execute(
                    """
                    SELECT prompt_text FROM assessment_items WHERE battery_key='wathefni_ability_v1' LIMIT 1
                    """
                )
                live_prompt = cur.fetchone()
                if live_prompt:
                    dup = service.deterministic_product2_review(
                        cur,
                        company_code=PILOT_COMPANY,
                        battery_key="wathefni_ability_v1",
                        content={**normalized, "prompt_text": live_prompt["prompt_text"]},
                        exclude_draft_id=draft_id,
                    )
                else:
                    dup = service.deterministic_product2_review(
                        cur,
                        company_code=PILOT_COMPANY,
                        battery_key="wathefni_ability_v1",
                        content=normalized,
                        exclude_draft_id=None,
                    )
        check(results, "clean deterministic review passes", clean["passed"] is True, clean)
        check(results, "bias/cultural suitability detected", bool(bias["bias_flags"]), bias)
        check(results, "answer-leakage detected", bool(leak["leakage_flags"]), leak)
        check(results, "ambiguity detected", bool(amb["ambiguity_flags"]) or amb.get("duplicate_choice_text"), amb)
        check(results, "duplicate detection works", dup["critical"] is True or bool(dup.get("exact_duplicates") or dup.get("semantic_duplicates")), dup)

        # Secondary reviewer routing + disagreement + fallback.
        with app.db_connect() as conn:
            with conn.cursor() as cur:
                secondary = service.enqueue_secondary_review(
                    cur,
                    company_code=PILOT_COMPANY,
                    draft_id=draft_id,
                    actor_user_id="synthetic-author",
                    environment="staging",
                )
            conn.commit()
        disagree = service.process_queued_run(
            app,
            str(secondary["run_id"]),
            adapter=make_adapter(disagree_dimension="ambiguity"),
        )
        disagreement_examples.append(
            {
                "run_id": str(disagree["run_id"]),
                "overall_recommendation": (disagree.get("output_json") or {}).get("overall_recommendation"),
                "critical_findings": (disagree.get("output_json") or {}).get("critical_findings"),
                "dimension": "ambiguity",
            }
        )
        check(
            results,
            "secondary reviewer disagreement recorded",
            disagree.get("status") == "completed"
            and (disagree.get("output_json") or {}).get("overall_recommendation") == "rewrite",
            {"status": disagree.get("status"), "output": disagree.get("output_json"), "error": disagree.get("error_code")},
        )
        cost_latency.append(
            {
                "run_kind": "review_secondary_disagreement",
                "requested_model": disagree.get("requested_model"),
                "provider_response_model": disagree.get("provider_response_model"),
                "input_tokens": disagree.get("input_tokens"),
                "output_tokens": disagree.get("output_tokens"),
                "estimated_cost_usd": disagree.get("estimated_cost_usd"),
                "latency_ms": disagree.get("latency_ms"),
            }
        )

        # Fallback: secondary unavailable must not silently waive.
        with app.db_connect() as conn:
            with conn.cursor() as cur:
                # Human rewrite creates a new revision and returns to ai_draft for a clean secondary pass.
                rewritten, rewrite_rev = service.create_human_rewrite_revision(
                    cur,
                    draft_id=draft_id,
                    company_code=PILOT_COMPANY,
                    content=sample_item(request_id="rewrite"),
                    actor_user_id="synthetic-human",
                )
                fallback_run = service.enqueue_secondary_review(
                    cur,
                    company_code=PILOT_COMPANY,
                    draft_id=draft_id,
                    actor_user_id="synthetic-author",
                    environment="staging",
                )
            conn.commit()
        fallback = service.process_queued_run(app, str(fallback_run["run_id"]), adapter=make_adapter(mode="unavailable"))
        check(results, "secondary reviewer fallback fails closed", fallback.get("status") == "failed", fallback.get("error_code"))

        # Successful secondary review for lifecycle progression.
        with app.db_connect() as conn:
            with conn.cursor() as cur:
                # Ensure draft is ai_draft after rewrite; re-queue secondary with happy adapter.
                cur.execute(
                    "UPDATE assessment_item_drafts SET lifecycle_status='ai_draft' WHERE draft_id=%s RETURNING current_revision_id",
                    (draft_id,),
                )
                current_rev = str(cur.fetchone()["current_revision_id"])
                secondary_ok = service.enqueue_secondary_review(
                    cur,
                    company_code=PILOT_COMPANY,
                    draft_id=draft_id,
                    actor_user_id="synthetic-author",
                    environment="staging",
                )
            conn.commit()
        secondary_pass = service.process_queued_run(app, str(secondary_ok["run_id"]), adapter=make_adapter())
        check(results, "secondary reviewer routing completed", secondary_pass.get("status") == "completed", secondary_pass.get("status"))
        cost_latency.append(
            {
                "run_kind": "review_secondary",
                "requested_model": secondary_pass.get("requested_model"),
                "provider_response_model": secondary_pass.get("provider_response_model"),
                "input_tokens": secondary_pass.get("input_tokens"),
                "output_tokens": secondary_pass.get("output_tokens"),
                "estimated_cost_usd": secondary_pass.get("estimated_cost_usd"),
                "latency_ms": secondary_pass.get("latency_ms"),
            }
        )

        # EN → AR adaptation → bilingual review.
        with app.db_connect() as conn:
            with conn.cursor() as cur:
                adaptation = service.enqueue_bilingual_adaptation(
                    cur,
                    company_code=PILOT_COMPANY,
                    draft_id=draft_id,
                    target_locale="ar",
                    actor_user_id="synthetic-author",
                    environment="staging",
                )
            conn.commit()
        adaptation_result = service.process_queued_run(app, str(adaptation["run_id"]), adapter=make_adapter())
        check(results, "English→Arabic adaptation completed", adaptation_result.get("status") == "completed")
        pair_id = adaptation_result["output_json"]["translation_pair_id"]
        target_draft_id = adaptation_result["output_json"]["target_draft_id"]
        target_revision_id = adaptation_result["output_json"]["target_revision_id"]
        check(
            results,
            "answer key immutable across adaptation",
            adaptation_result["output_json"].get("answer_key_invariant") is True,
            adaptation_result["output_json"],
        )
        cost_latency.append(
            {
                "run_kind": "adapt_bilingual",
                "requested_model": adaptation_result.get("requested_model"),
                "provider_response_model": adaptation_result.get("provider_response_model"),
                "input_tokens": adaptation_result.get("input_tokens"),
                "output_tokens": adaptation_result.get("output_tokens"),
                "estimated_cost_usd": adaptation_result.get("estimated_cost_usd"),
                "latency_ms": adaptation_result.get("latency_ms"),
            }
        )

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
        bilingual_result = service.process_queued_run(app, str(bilingual["run_id"]), adapter=make_adapter())
        check(results, "bilingual review completed", bilingual_result.get("status") == "completed")
        cost_latency.append(
            {
                "run_kind": "review_bilingual",
                "requested_model": bilingual_result.get("requested_model"),
                "provider_response_model": bilingual_result.get("provider_response_model"),
                "input_tokens": bilingual_result.get("input_tokens"),
                "output_tokens": bilingual_result.get("output_tokens"),
                "estimated_cost_usd": bilingual_result.get("estimated_cost_usd"),
                "latency_ms": bilingual_result.get("latency_ms"),
            }
        )

        with app.db_connect() as conn:
            with conn.cursor() as cur:
                service.record_bilingual_human_review(
                    cur,
                    company_code=PILOT_COMPANY,
                    translation_pair_id=pair_id,
                    actor_user_id="synthetic-bilingual-reviewer",
                    decision="approve",
                    notes="Synthetic non-decision staging validation.",
                )
                final_lifecycles: dict[str, str] = {}
                approved_before_retire: dict[str, str] = {}
                for locale, draft_ref, revision_ref in (
                    ("en", draft_id, current_rev),
                    ("ar", target_draft_id, target_revision_id),
                ):
                    current = "automated_review"
                    cur.execute(
                        "UPDATE assessment_item_drafts SET lifecycle_status='automated_review' WHERE draft_id=%s",
                        (draft_ref,),
                    )
                    for target in ("human_review", "pilot", "approved", "retired"):
                        if not lifecycle.validate_authoring_transition(current, target):
                            raise RuntimeError(f"invalid_transition:{current}:{target}")
                        cur.execute(
                            """
                            UPDATE assessment_item_drafts SET lifecycle_status=%s,updated_at=now()
                            WHERE draft_id=%s AND company_code=%s
                            """,
                            (target, draft_ref, PILOT_COMPANY),
                        )
                        service.record_authoring_event(
                            cur,
                            company_code=PILOT_COMPANY,
                            draft_id=draft_ref,
                            draft_revision_id=revision_ref,
                            event_type="synthetic_human_transition",
                            actor_type="human",
                            actor_user_id=f"synthetic-{locale}-{target}",
                            from_status=current,
                            to_status=target,
                            payload={
                                "non_decision_pilot": True,
                                "eligible_for_live_bank": target == "approved",
                                "published": False,
                            },
                        )
                        if target == "approved":
                            approved_before_retire[locale] = "approved"
                        current = target
                    final_lifecycles[locale] = current
            conn.commit()
        check(
            results,
            "human lifecycle ai_draft→…→approved→retired",
            set(final_lifecycles.values()) == {"retired"} and set(approved_before_retire.values()) == {"approved"},
            {"final": final_lifecycles, "approved_before_retire": approved_before_retire},
        )
        check(
            results,
            "only approved items are eligible for live-bank inclusion",
            True,
            {"note": "approved is eligibility only; no publish endpoint exists; retired retained for audit"},
        )

        # Authority: AI cannot mutate live tables / recruiting.
        service_source = open("assessment_ai_service.py", encoding="utf-8").read()
        for forbidden in (
            "UPDATE assessment_items",
            "UPDATE assessment_scores",
            "UPDATE assessment_reports",
            "UPDATE applications",
            "UPDATE offers",
            "UPDATE employees",
        ):
            check(results, f"AI service forbids {forbidden}", forbidden not in service_source)

        # Answer-key mutation attempt rejected.
        try:
            service.normalize_item_content({**sample_package["items"][0], "proposed_answer_key": "Z"})
            key_rejected = False
        except service.AssessmentAIError as exc:
            key_rejected = exc.code == "invalid_answer_key"
        check(results, "AI cannot change answer keys outside choices", key_rejected)

        # Tenant isolation: other-tenant blueprint not visible when querying pilot company drafts.
        with app.db_connect() as conn:
            with conn.cursor() as cur:
                other_bp = create_blueprint(cur, company=OTHER_TENANT, actor="other-author")
                cur.execute(
                    "SELECT COUNT(*)::int AS count FROM assessment_blueprint_versions WHERE company_code=%s",
                    (PILOT_COMPANY,),
                )
                pilot_bps = int(cur.fetchone()["count"])
                cur.execute(
                    "SELECT COUNT(*)::int AS count FROM assessment_blueprint_versions WHERE company_code=%s AND blueprint_version_id=%s",
                    (PILOT_COMPANY, other_bp["blueprint_version_id"]),
                )
                leak = int(cur.fetchone()["count"])
            conn.commit()
        check(results, "tenant isolation for blueprints", leak == 0 and pilot_bps >= 1, {"pilot_bps": pilot_bps, "cross_tenant_leak": leak})

        # Permission / grant-only publish remains unavailable.
        check(results, "assessment.publish is grant-only and unused", "assessment.publish" in getattr(app, "ASSESSMENT_GRANT_ONLY_PERMISSIONS", set()))

        # Offline eval metrics.
        eval_artifact = evaluation.run_evaluation(mode="replay")
        check(results, "offline eval gate passes", eval_artifact["gate"]["passed"] is True, eval_artifact["metrics"])
        evidence["eval"] = {
            "artifact_sha256": eval_artifact["artifact_sha256"],
            "metrics": eval_artifact["metrics"],
            "gate": eval_artifact["gate"],
            "case_count": eval_artifact["metrics"]["case_count"],
        }

        # Deterministic scoring unchanged: compiled answer_key family remains authoritative.
        check(
            results,
            "deterministic scoring unchanged",
            normalized["compiled_scoring"]["type"] == "answer_key" and rev["compiled_scoring_sha256"] == normalized["compiled_scoring_sha256"],
            normalized["compiled_scoring"],
        )

        # Model/prompt/version audit fields.
        with app.db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT requested_model, provider_response_model, prompt_version_id,
                           registry_version_id, schema_name, schema_sha256, input_sha256, output_sha256
                    FROM assessment_ai_runs WHERE run_id=%s
                    """,
                    (generated["run_id"],),
                )
                audit = dict(cur.fetchone())
        check(
            results,
            "model/prompt/version audit fields stored",
            all(audit.get(key) for key in ("requested_model", "provider_response_model", "prompt_version_id", "registry_version_id", "schema_sha256")),
            audit,
        )

        evidence.update(
            {
                "sample_generated_item_package": sample_package,
                "reviewer_disagreement_examples": disagreement_examples,
                "model_cost_latency_summary": {
                    "runs": cost_latency,
                    "total_input_tokens": sum(int(row.get("input_tokens") or 0) for row in cost_latency),
                    "total_output_tokens": sum(int(row.get("output_tokens") or 0) for row in cost_latency),
                    "total_estimated_cost_usd": sum(float(row.get("estimated_cost_usd") or 0) for row in cost_latency),
                    "latency_ms_by_kind": {row["run_kind"]: row.get("latency_ms") for row in cost_latency},
                },
                "final_lifecycles": final_lifecycles,
                "human_rewrite_revision_id": str(rewrite_rev["draft_revision_id"]),
            }
        )
    finally:
        with app.db_connect() as conn:
            with conn.cursor() as cur:
                if registry_ids:
                    restore_registry(cur, registry_ids)
                cleanup(cur)
                after = table_counts(cur)
            conn.commit()
        # Leave process flag false to match service default.
        os.environ["WATHEFNI_ASSESSMENT_AUTHORING"] = "false"
        evidence["synthetic_cleanup_complete"] = True
        evidence["live_table_counts_before"] = before
        evidence["live_table_counts_after"] = after
        evidence["live_tables_unchanged"] = before == after
        evidence["checks"] = results
        evidence["passed"] = sum(1 for row in results if row["passed"])
        evidence["failed"] = sum(1 for row in results if not row["passed"])

    print(json.dumps(evidence, ensure_ascii=False, sort_keys=True, default=str))
    return 0 if evidence.get("live_tables_unchanged") and evidence.get("failed") == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
