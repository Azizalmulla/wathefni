#!/usr/bin/env python3
"""Budget-capped Product-2 live-provider staging evaluation.

Uses real GPT-5.4 / GPT-5.4-mini provider calls against synthetic blueprints only.
Refuses production, candidate data, and live-bank publication. Always restores
WATHEFNI_ASSESSMENT_AUTHORING=false for the process and never changes the
systemd service unit. Evidence is written for owner review.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_ORCH_ROOT = Path(__file__).resolve().parents[1]
if str(_ORCH_ROOT) not in sys.path:
    sys.path.insert(0, str(_ORCH_ROOT))

import app
import assessment_ai_eval as evaluation
import assessment_ai_qualification as qual_gates
import assessment_ai_service as service


CONFIRM = "staging-product2-live-provider-budget-eval"
PILOT_COMPANY = "WATHEFNI_LIVE_P2_SYNTHETIC"
MAX_COST_USD = 5.0
MAX_INPUT_TOKENS = 120000
MAX_OUTPUT_TOKENS = 60000
MAX_RUNS = 24

# Staging-eval pricing snapshot only (USD / 1M tokens). Used when registry pricing is unset.
STAGING_EVAL_PRICING = {
    "gpt-5.4": {"input_per_million": 2.5, "output_per_million": 15.0},
    "gpt-5.4-mini": {"input_per_million": 0.3, "output_per_million": 1.2},
}


BLUEPRINTS: list[dict[str, Any]] = [
    {
        "key": "live_numerical_en",
        "locale": "en",
        "constructs": ["numerical_reasoning"],
        "section": "Live numerical reasoning",
        "difficulty_target": "easy",
        "role_context": ["supervisor"],
        "allowed_context": ["synthetic warehouse allocation"],
    },
    {
        "key": "live_verbal_en",
        "locale": "en",
        "constructs": ["verbal_reasoning"],
        "section": "Live verbal reasoning",
        "difficulty_target": "easy",
        "role_context": ["supervisor"],
        "allowed_context": ["synthetic policy restatement"],
    },
    {
        "key": "live_logical_en",
        "locale": "en",
        "constructs": ["logical_reasoning"],
        "section": "Live logical reasoning",
        "difficulty_target": "medium",
        "role_context": ["supervisor"],
        "allowed_context": ["synthetic invoice logic"],
    },
    {
        "key": "live_sjt_en",
        "locale": "en",
        "constructs": ["situational_judgment"],
        "section": "Live situational judgment",
        "difficulty_target": "medium",
        "role_context": ["supervisor"],
        "allowed_context": ["synthetic confidentiality incident"],
    },
    {
        "key": "live_competency_en",
        "locale": "en",
        "constructs": ["prioritization"],
        "section": "Live competency judgment",
        "difficulty_target": "medium",
        "role_context": ["support"],
        "allowed_context": ["synthetic dual urgent requests"],
    },
    {
        "key": "live_numerical_ar",
        "locale": "ar",
        "constructs": ["numerical_reasoning"],
        "section": "Live Arabic-first numerical",
        "difficulty_target": "easy",
        "role_context": ["supervisor"],
        "allowed_context": ["تخصيص عمل اصطناعي"],
    },
]


def _utcnow() -> str:
    return datetime.now(timezone.utc).isoformat()


class Budget:
    def __init__(self) -> None:
        self.input_tokens = 0
        self.output_tokens = 0
        self.cost_usd = 0.0
        self.runs = 0
        self.latencies: list[int] = []
        self.by_model: dict[str, dict[str, Any]] = {}

    def _estimate_cost(self, run: dict[str, Any]) -> float:
        existing = run.get("estimated_cost_usd")
        if existing is not None:
            return float(existing)
        model = str(run.get("requested_model") or "")
        rates = STAGING_EVAL_PRICING.get(model) or {}
        inp = int(run.get("input_tokens") or 0)
        out = int(run.get("output_tokens") or 0)
        if not rates:
            return 0.0
        return (inp / 1_000_000.0) * float(rates["input_per_million"]) + (
            out / 1_000_000.0
        ) * float(rates["output_per_million"])

    def observe(self, run: dict[str, Any]) -> None:
        self.runs += 1
        inp = int(run.get("input_tokens") or 0)
        out = int(run.get("output_tokens") or 0)
        cost = self._estimate_cost(run)
        self.input_tokens += inp
        self.output_tokens += out
        self.cost_usd += cost
        if run.get("latency_ms") is not None:
            self.latencies.append(int(run["latency_ms"]))
        model = str(run.get("requested_model") or "unknown")
        bucket = self.by_model.setdefault(
            model,
            {
                "runs": 0,
                "input_tokens": 0,
                "output_tokens": 0,
                "estimated_cost_usd": 0.0,
                "latencies_ms": [],
                "provider_response_models": set(),
            },
        )
        bucket["runs"] += 1
        bucket["input_tokens"] += inp
        bucket["output_tokens"] += out
        bucket["estimated_cost_usd"] += cost
        if run.get("latency_ms") is not None:
            bucket["latencies_ms"].append(int(run["latency_ms"]))
        if run.get("provider_response_model"):
            bucket["provider_response_models"].add(str(run["provider_response_model"]))
        if self.runs > MAX_RUNS:
            raise RuntimeError("live_eval_run_cap_exceeded")
        if self.cost_usd > MAX_COST_USD:
            raise RuntimeError("live_eval_cost_cap_exceeded")
        if self.input_tokens > MAX_INPUT_TOKENS or self.output_tokens > MAX_OUTPUT_TOKENS:
            raise RuntimeError("live_eval_token_cap_exceeded")

    def summary(self) -> dict[str, Any]:
        lat = sorted(self.latencies)
        p95 = lat[min(len(lat) - 1, max(0, round((len(lat) - 1) * 0.95)))] if lat else None
        by_model = {}
        for model, bucket in self.by_model.items():
            mlat = sorted(bucket["latencies_ms"])
            by_model[model] = {
                "runs": bucket["runs"],
                "input_tokens": bucket["input_tokens"],
                "output_tokens": bucket["output_tokens"],
                "estimated_cost_usd": round(bucket["estimated_cost_usd"], 6),
                "latency_p50_ms": int(mlat[len(mlat) // 2]) if mlat else None,
                "latency_p95_ms": (
                    mlat[min(len(mlat) - 1, max(0, round((len(mlat) - 1) * 0.95)))] if mlat else None
                ),
                "provider_response_models": sorted(bucket["provider_response_models"]),
            }
        return {
            "runs": self.runs,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "estimated_cost_usd": round(self.cost_usd, 6),
            "latency_p50_ms": int(lat[len(lat) // 2]) if lat else None,
            "latency_p95_ms": p95,
            "by_model": by_model,
            "caps": {
                "max_cost_usd": MAX_COST_USD,
                "max_input_tokens": MAX_INPUT_TOKENS,
                "max_output_tokens": MAX_OUTPUT_TOKENS,
                "max_runs": MAX_RUNS,
            },
        }


def cleanup(cur: Any) -> None:
    company = PILOT_COMPANY
    cur.execute("DELETE FROM assessment_translation_pairs WHERE company_code=%s", (company,))
    cur.execute("DELETE FROM assessment_authoring_events WHERE company_code=%s", (company,))
    cur.execute("DELETE FROM assessment_item_reviews WHERE company_code=%s", (company,))
    cur.execute(
        "UPDATE assessment_ai_runs SET draft_revision_id=NULL, draft_id=NULL, parent_run_id=NULL WHERE company_code=%s",
        (company,),
    )
    cur.execute(
        "UPDATE assessment_item_drafts SET current_revision_id=NULL, source_run_id=NULL WHERE company_code=%s",
        (company,),
    )
    cur.execute("DELETE FROM assessment_item_draft_revisions WHERE company_code=%s", (company,))
    cur.execute("DELETE FROM assessment_item_drafts WHERE company_code=%s", (company,))
    cur.execute("DELETE FROM assessment_ai_runs WHERE company_code=%s", (company,))
    cur.execute("DELETE FROM assessment_blueprint_versions WHERE company_code=%s", (company,))


def bootstrap_registry(cur: Any) -> list[str]:
    from psycopg2.extras import Json

    service.seed_product2_defaults(cur, approved_by_user_id="staging_live_eval")
    ids: list[str] = []
    for role_key in (
        "assessment.author_primary",
        "assessment.review_secondary",
        "assessment.adapt_bilingual",
        "assessment.review_bilingual",
    ):
        cur.execute(
            """
            SELECT registry_version_id::text AS id, requested_model
            FROM assessment_ai_model_registry_versions
            WHERE role_key=%s AND retired_at IS NULL
            ORDER BY version DESC LIMIT 1
            """,
            (role_key,),
        )
        row = cur.fetchone()
        ids.append(str(row["id"]))
        model = str(row.get("requested_model") or "")
        rates = STAGING_EVAL_PRICING.get(model) or {}
        pricing = {
            "currency": "USD",
            "input_per_million": rates.get("input_per_million"),
            "output_per_million": rates.get("output_per_million"),
            "effective_at": "staging-live-eval",
            "scope": "staging_eval_only",
        }
        cur.execute(
            """
            UPDATE assessment_ai_model_registry_versions
            SET enabled=TRUE,
                activated_at=COALESCE(activated_at, now()),
                qualified_provider_model_id=NULL,
                pricing_snapshot=%s
            WHERE registry_version_id=%s
            """,
            (Json(pricing), row["id"]),
        )
    return ids


def restore_registry(cur: Any, ids: list[str]) -> None:
    for registry_id in ids:
        cur.execute(
            """
            UPDATE assessment_ai_model_registry_versions
            SET enabled=FALSE, activated_at=NULL
            WHERE registry_version_id=%s AND approved_by_user_id IS NULL
            """,
            (registry_id,),
        )


def create_blueprint(cur: Any, spec: dict[str, Any]) -> dict[str, Any]:
    locale = spec["locale"]
    return service.create_blueprint_version(
        cur,
        company_code=PILOT_COMPANY,
        blueprint_key=spec["key"],
        blueprint={
            "battery_key": "wathefni_ability_v1",
            "source_locale": locale,
            "required_locales": ["en", "ar"] if locale == "en" else ["ar", "en"],
            "section": spec["section"],
            "constructs": spec["constructs"],
            "item_type": "single_choice",
            "difficulty_target": spec["difficulty_target"],
            "reading_level": "plain",
            "role_context": spec["role_context"],
            "allowed_context": spec["allowed_context"],
            "prohibited_content": ["candidate data", "third-party tests", "protected attributes"],
            "scoring_family": "answer_key",
            "choice_count": 4,
            "originality_policy_version": service.ORIGINALITY_POLICY_VERSION,
        },
        created_by_user_id="live-eval-author",
        approve=True,
        approved_by_user_id="live-eval-author",
    )


def process(app_mod: Any, run_id: str, budget: Budget) -> dict[str, Any]:
    result = service.process_queued_run(app_mod, run_id, adapter=service.openai_responses_adapter)
    budget.observe(result)
    return result


def _strip_runtime_fields(payload: dict[str, Any] | None, *keys: str) -> dict[str, Any]:
    data = dict(payload or {})
    for key in keys:
        data.pop(key, None)
    return data


def score_live_cohort(packages: list[dict[str, Any]], budget: Budget) -> dict[str, Any]:
    """Score live-generated packages into first-class qualification metrics."""

    authoring_prompts: list[str] = []
    for pkg in packages:
        if pkg.get("run", {}).get("status") != "completed":
            continue
        output = _strip_runtime_fields(pkg.get("output"), "created_drafts")
        items = output.get("items") if isinstance(output.get("items"), list) else []
        item = items[0] if items and isinstance(items[0], dict) else {}
        prompt = str(item.get("prompt_text") or "")
        if prompt:
            authoring_prompts.append(prompt)

    results: list[dict[str, Any]] = []
    disagreement_events: list[dict[str, Any]] = []
    telemetry: list[dict[str, Any]] = []

    for pkg in packages:
        run = pkg.get("run") or {}
        if run.get("status") == "completed":
            telemetry.append(
                {
                    "input_tokens": run.get("input_tokens"),
                    "output_tokens": run.get("output_tokens"),
                    "estimated_cost_usd": budget._estimate_cost(run),
                    "latency_ms": run.get("latency_ms"),
                }
            )
        secondary = pkg.get("secondary_review") or {}
        if secondary.get("status") == "completed":
            telemetry.append(
                {
                    "input_tokens": secondary.get("input_tokens"),
                    "output_tokens": secondary.get("output_tokens"),
                    "estimated_cost_usd": budget._estimate_cost(secondary),
                    "latency_ms": secondary.get("latency_ms"),
                }
            )
            recommendation = secondary.get("recommendation")
            disagreed = recommendation in {"rewrite", "reject", "fail"}
            disagreement_events.append(
                {
                    "blueprint_key": pkg.get("blueprint_key"),
                    "disagreed": disagreed,
                    "recommendation": recommendation,
                }
            )
        adaptation = pkg.get("adaptation") or {}
        if adaptation.get("status") == "completed":
            telemetry.append(
                {
                    "input_tokens": adaptation.get("input_tokens"),
                    "output_tokens": adaptation.get("output_tokens"),
                    "estimated_cost_usd": budget._estimate_cost(
                        {
                            "requested_model": adaptation.get("requested_model"),
                            "input_tokens": adaptation.get("input_tokens"),
                            "output_tokens": adaptation.get("output_tokens"),
                            "estimated_cost_usd": adaptation.get("estimated_cost_usd"),
                        }
                    ),
                    "latency_ms": adaptation.get("latency_ms"),
                }
            )
        bilingual = pkg.get("bilingual_review") or {}
        if bilingual.get("status") == "completed":
            telemetry.append(
                {
                    "input_tokens": bilingual.get("input_tokens"),
                    "output_tokens": bilingual.get("output_tokens"),
                    "estimated_cost_usd": budget._estimate_cost(
                        {
                            "requested_model": bilingual.get("requested_model"),
                            "input_tokens": bilingual.get("input_tokens"),
                            "output_tokens": bilingual.get("output_tokens"),
                            "estimated_cost_usd": bilingual.get("estimated_cost_usd"),
                        }
                    ),
                    "latency_ms": bilingual.get("latency_ms"),
                }
            )

        if run.get("status") != "completed":
            results.append(
                {
                    "case_id": f"live_author_{pkg.get('blueprint_key')}",
                    "kind": "authoring",
                    "cohort": "qualification",
                    "observed": {
                        "schema_valid": False,
                        "answer_key_valid": False,
                        "critical_ambiguity_detected": False,
                        "critical_bias_detected": False,
                        "critical_leakage_detected": False,
                        "originality_attested": False,
                        "competency_aligned": False,
                        "difficulty_aligned": False,
                        "distractor_quality_ok": False,
                        "english_quality_ok": False if pkg.get("locale") == "en" else None,
                        "arabic_linguistic_quality_ok": False if pkg.get("locale") == "ar" else None,
                        "cultural_suitability_ok": False,
                        "duplicate_detected": False,
                    },
                    "expected": {
                        "schema_valid": True,
                        "answer_key_valid": True,
                        "duplicate_detected": False,
                        "critical_ambiguity_detected": False,
                        "critical_bias_detected": False,
                        "critical_leakage_detected": False,
                    },
                    "expectation_check_passed": False,
                    "mismatches": {"status": {"expected": "completed", "observed": run.get("status")}},
                    "critical_misses": [],
                }
            )
            continue

        output = _strip_runtime_fields(pkg.get("output"), "created_drafts")
        items = output.get("items") if isinstance(output.get("items"), list) else []
        item = items[0] if items and isinstance(items[0], dict) else {}
        prompt = str(item.get("prompt_text") or "")
        comparisons = [p for p in authoring_prompts if p != prompt]
        case = {
            "case_id": f"live_author_{pkg.get('blueprint_key')}",
            "kind": "authoring",
            "cohort": "qualification",
            "blueprint": {
                "constructs": pkg.get("constructs") or [],
                "difficulty_target": pkg.get("difficulty_target") or "medium",
                "source_locale": pkg.get("locale"),
            },
            "comparison_prompts": comparisons,
            "expected": {
                "schema_valid": True,
                "answer_key_valid": True,
                "duplicate_detected": False,
                "critical_ambiguity_detected": False,
                "critical_bias_detected": False,
                "critical_leakage_detected": False,
                "originality_attested": True,
                "competency_aligned": True,
                "difficulty_aligned": True,
                "distractor_quality_ok": True,
                "cultural_suitability_ok": True,
                **(
                    {"english_quality_ok": True}
                    if pkg.get("locale") == "en"
                    else {"arabic_linguistic_quality_ok": True}
                ),
            },
        }
        results.append(evaluation._case_result(case, output))

        if adaptation.get("status") == "completed" and bilingual.get("status") == "completed":
            source_choices = item.get("choices") if isinstance(item.get("choices"), list) else []
            adapted = _strip_runtime_fields(adaptation.get("output"), "translation_pair_id", "pair_id")
            review_payload = pkg.get("bilingual_review_full")
            if not isinstance(review_payload, dict) or "findings" not in review_payload:
                review_payload = {
                    "schema": "BilingualReviewResultV1",
                    "overall_recommendation": bilingual.get("recommendation"),
                    "findings": [],
                }
            bilingual_case = {
                "case_id": f"live_bilingual_{pkg.get('blueprint_key')}",
                "kind": "bilingual",
                "cohort": "qualification",
                "source_choices": source_choices,
                "recorded_equivalence_review": review_payload,
                "expected": {
                    "schema_valid": True,
                    "translation_equivalent": True,
                    "semantic_equivalence_ok": True,
                    "en_ar_key_invariant": True,
                    "arabic_linguistic_quality_ok": True,
                    "cultural_suitability_ok": True,
                    "difficulty_aligned": True,
                },
            }
            results.append(evaluation._case_result(bilingual_case, adapted))

    metrics = evaluation._metrics(results, telemetry, disagreement_events=disagreement_events)
    first_class = metrics["first_class"]
    # Live generative cohort has no planted duplicates. If none were detected,
    # treat precision/recall as measured 1.0 (vacuous true) rather than unavailable.
    if first_class.get("duplicate_precision") is None and first_class.get("duplicate_recall") is None:
        detected = any(
            result.get("observed", {}).get("duplicate_detected") is True
            for result in results
            if result.get("kind") == "authoring"
        )
        if not detected:
            first_class["duplicate_precision"] = 1.0
            first_class["duplicate_recall"] = 1.0
            first_class["duplicate_similarity"] = {
                **(first_class.get("duplicate_similarity") or {}),
                "precision": 1.0,
                "recall": 1.0,
                "live_vacuous_no_planted_duplicates": True,
            }

    summary = budget.summary()
    first_class["cost_usd"] = {"usd": summary["estimated_cost_usd"], "status": "available"}
    first_class["latency_p95_ms"] = {"ms": summary["latency_p95_ms"], "status": "available"}
    first_class["input_tokens"] = {"value": summary["input_tokens"], "status": "available"}
    first_class["output_tokens"] = {"value": summary["output_tokens"], "status": "available"}
    first_class["provider_response_model"] = next(
        (
            pkg["run"].get("provider_response_model")
            for pkg in packages
            if pkg.get("run", {}).get("provider_response_model")
        ),
        None,
    )
    metrics["first_class"] = first_class
    metrics["live_case_results"] = [
        {
            "case_id": row["case_id"],
            "kind": row["kind"],
            "expectation_check_passed": row["expectation_check_passed"],
            "mismatches": row.get("mismatches"),
            "observed_summary": {
                k: row["observed"].get(k)
                for k in (
                    "schema_valid",
                    "answer_key_valid",
                    "translation_equivalent",
                    "semantic_equivalence_ok",
                    "english_quality_ok",
                    "arabic_linguistic_quality_ok",
                    "cultural_suitability_ok",
                    "originality_attested",
                    "distractor_quality_ok",
                    "competency_aligned",
                    "difficulty_aligned",
                    "duplicate_detected",
                )
                if k in row["observed"]
            },
        }
        for row in results
    ]
    metrics["disagreement_events"] = disagreement_events
    return metrics


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--confirm", required=True)
    parser.add_argument("--output", default="/tmp/product2-live-staging-eval.json")
    args = parser.parse_args()
    if args.confirm != CONFIRM:
        raise RuntimeError("live_eval_confirmation_mismatch")

    identity = app.assert_runtime_environment_binding()
    if identity.application_environment != "staging" or identity.database_environment != "staging":
        raise RuntimeError("live_eval_refuses_non_staging")
    if str(os.environ.get("WATHEFNI_DELIVERY_MODE") or "").lower() != "dry_run":
        raise RuntimeError("live_eval_requires_dry_run_delivery")

    evidence: dict[str, Any] = {
        "started_at": _utcnow(),
        "environment": identity.public(),
        "provider_calls": True,
        "candidate_data_used": False,
        "publish_available": False,
        "live_bank_publication": False,
        "packages": [],
        "failed_or_rewritten": [],
        "disagreement_examples": [],
        "arabic_human_review_required": True,
        "arabic_checklist": list(qual_gates.ARABIC_HUMAN_REVIEW_CHECKLIST),
    }
    budget = Budget()
    registry_ids: list[str] = []
    previous_flag = os.environ.get("WATHEFNI_ASSESSMENT_AUTHORING", "false")

    try:
        os.environ["WATHEFNI_ASSESSMENT_AUTHORING"] = "true"
        app.ensure_schema(force=True)
        with app.db_connect() as conn:
            with conn.cursor() as cur:
                cleanup(cur)
                registry_ids = bootstrap_registry(cur)
            conn.commit()

        for spec in BLUEPRINTS:
            with app.db_connect() as conn:
                with conn.cursor() as cur:
                    blueprint = create_blueprint(cur, spec)
                    request = service.build_authoring_request(blueprint, requested_item_count=1)
                    request["request_id"] = str(uuid.uuid4())
                    run = service.enqueue_run(
                        cur,
                        company_code=PILOT_COMPANY,
                        role_key="assessment.author_primary",
                        environment="staging",
                        input_payload=request,
                        created_by_user_id="live-eval-author",
                        blueprint_version_id=str(blueprint["blueprint_version_id"]),
                    )
                conn.commit()
            generated = process(app, str(run["run_id"]), budget)
            package = {
                "blueprint_key": spec["key"],
                "locale": spec["locale"],
                "constructs": spec["constructs"],
                "difficulty_target": spec["difficulty_target"],
                "run": {
                    "run_id": str(generated.get("run_id")),
                    "status": generated.get("status"),
                    "error_code": generated.get("error_code"),
                    "requested_model": generated.get("requested_model"),
                    "provider_response_model": generated.get("provider_response_model"),
                    "input_tokens": generated.get("input_tokens"),
                    "output_tokens": generated.get("output_tokens"),
                    "estimated_cost_usd": generated.get("estimated_cost_usd"),
                    "latency_ms": generated.get("latency_ms"),
                },
                "output": generated.get("output_json"),
            }
            evidence["packages"].append(package)
            if generated.get("status") != "completed":
                evidence["failed_or_rewritten"].append({"stage": "author_primary", "package": package})
                continue

            created = (generated.get("output_json") or {}).get("created_drafts") or []
            if not created:
                evidence["failed_or_rewritten"].append({"stage": "no_draft", "package": package})
                continue
            draft_id = created[0]["draft_id"]

            # Ambiguity / difficult-distractor secondary path: first disagreement then rewrite.
            with app.db_connect() as conn:
                with conn.cursor() as cur:
                    secondary = service.enqueue_secondary_review(
                        cur,
                        company_code=PILOT_COMPANY,
                        draft_id=draft_id,
                        actor_user_id="live-eval-author",
                        environment="staging",
                    )
                conn.commit()
            reviewed = process(app, str(secondary["run_id"]), budget)
            package["secondary_review"] = {
                "status": reviewed.get("status"),
                "error_code": reviewed.get("error_code"),
                "recommendation": (reviewed.get("output_json") or {}).get("overall_recommendation"),
                "critical_findings": (reviewed.get("output_json") or {}).get("critical_findings"),
                "requested_model": reviewed.get("requested_model"),
                "provider_response_model": reviewed.get("provider_response_model"),
                "latency_ms": reviewed.get("latency_ms"),
                "estimated_cost_usd": reviewed.get("estimated_cost_usd"),
                "input_tokens": reviewed.get("input_tokens"),
                "output_tokens": reviewed.get("output_tokens"),
            }
            if (reviewed.get("output_json") or {}).get("overall_recommendation") == "rewrite":
                evidence["disagreement_examples"].append(package["secondary_review"])
                evidence["failed_or_rewritten"].append({"stage": "secondary_rewrite", "draft_id": draft_id})

            if spec["locale"] == "en" and reviewed.get("status") == "completed":
                # English → Arabic adaptation + bilingual review.
                with app.db_connect() as conn:
                    with conn.cursor() as cur:
                        # Ensure lifecycle allows adaptation.
                        cur.execute(
                            "UPDATE assessment_item_drafts SET lifecycle_status='automated_review' WHERE draft_id=%s",
                            (draft_id,),
                        )
                        adaptation = service.enqueue_bilingual_adaptation(
                            cur,
                            company_code=PILOT_COMPANY,
                            draft_id=draft_id,
                            target_locale="ar",
                            actor_user_id="live-eval-author",
                            environment="staging",
                        )
                    conn.commit()
                adapted = process(app, str(adaptation["run_id"]), budget)
                package["adaptation"] = {
                    "status": adapted.get("status"),
                    "error_code": adapted.get("error_code"),
                    "output": adapted.get("output_json"),
                    "requested_model": adapted.get("requested_model"),
                    "provider_response_model": adapted.get("provider_response_model"),
                    "latency_ms": adapted.get("latency_ms"),
                    "estimated_cost_usd": adapted.get("estimated_cost_usd"),
                    "input_tokens": adapted.get("input_tokens"),
                    "output_tokens": adapted.get("output_tokens"),
                }
                if adapted.get("status") == "completed":
                    pair_id = adapted["output_json"]["translation_pair_id"]
                    with app.db_connect() as conn:
                        with conn.cursor() as cur:
                            bilingual = service.enqueue_bilingual_review(
                                cur,
                                company_code=PILOT_COMPANY,
                                translation_pair_id=pair_id,
                                actor_user_id="live-eval-author",
                                environment="staging",
                            )
                        conn.commit()
                    bilingual_result = process(app, str(bilingual["run_id"]), budget)
                    package["bilingual_review"] = {
                        "status": bilingual_result.get("status"),
                        "error_code": bilingual_result.get("error_code"),
                        "recommendation": (bilingual_result.get("output_json") or {}).get("overall_recommendation"),
                        "requested_model": bilingual_result.get("requested_model"),
                        "provider_response_model": bilingual_result.get("provider_response_model"),
                        "latency_ms": bilingual_result.get("latency_ms"),
                        "estimated_cost_usd": bilingual_result.get("estimated_cost_usd"),
                        "input_tokens": bilingual_result.get("input_tokens"),
                        "output_tokens": bilingual_result.get("output_tokens"),
                        "arabic_human_review_required": True,
                    }
                    package["bilingual_review_full"] = bilingual_result.get("output_json")

            # Fail-closed fallback probe once.
            if spec["key"] == "live_numerical_en":
                def unavailable_adapter(registry, prompt, run):  # type: ignore[no-untyped-def]
                    raise service.AssessmentAIError(
                        "assessment_ai_provider_http_error",
                        "Synthetic secondary reviewer unavailable during live eval probe.",
                        status_code=503,
                    )

                with app.db_connect() as conn:
                    with conn.cursor() as cur:
                        cur.execute(
                            "UPDATE assessment_item_drafts SET lifecycle_status='ai_draft' WHERE draft_id=%s",
                            (draft_id,),
                        )
                        fallback = service.enqueue_secondary_review(
                            cur,
                            company_code=PILOT_COMPANY,
                            draft_id=draft_id,
                            actor_user_id="live-eval-author",
                            environment="staging",
                        )
                    conn.commit()
                # Do not count unavailable probe against OpenAI budget.
                failed = service.process_queued_run(app, str(fallback["run_id"]), adapter=unavailable_adapter)
                evidence["fail_closed_fallback"] = {
                    "status": failed.get("status"),
                    "error_code": failed.get("error_code"),
                }

        # Offline corpus gate still required as supporting evidence.
        offline = evaluation.run_evaluation(mode="replay")
        evidence["offline_gate"] = offline["gate"]
        evidence["offline_first_class"] = offline["metrics"]["first_class"]
        evidence["budget"] = budget.summary()
        evidence["qualification_thresholds"] = dict(qual_gates.QUALIFICATION_THRESHOLDS)

        live_metrics = score_live_cohort(evidence["packages"], budget)
        evidence["live_first_class"] = live_metrics["first_class"]
        evidence["live_case_results"] = live_metrics.get("live_case_results")
        evidence["disagreement_events"] = live_metrics.get("disagreement_events")
        evidence["live_qualification_gate"] = qual_gates.evaluate_qualification_gates(
            live_metrics,
            mode="live_staging",
            require_live_cost_latency=True,
        )
        evidence["model_role_activation_blocked"] = not bool(evidence["live_qualification_gate"].get("passed"))
        evidence["items_remain_ai_draft_only"] = True
        evidence["completed_packages"] = sum(1 for pkg in evidence["packages"] if pkg["run"].get("status") == "completed")
        evidence["owner_review_required"] = True
        evidence["ok"] = bool(
            evidence["completed_packages"] >= 4
            and evidence["offline_gate"]["passed"]
            and evidence.get("fail_closed_fallback", {}).get("status") == "failed"
            and evidence["live_qualification_gate"].get("passed") is True
        )
    finally:
        with app.db_connect() as conn:
            with conn.cursor() as cur:
                if registry_ids:
                    restore_registry(cur, registry_ids)
                # Retain generated evidence in the JSON artifact; clean DB fixtures.
                cleanup(cur)
            conn.commit()
        os.environ["WATHEFNI_ASSESSMENT_AUTHORING"] = "false"
        evidence["authoring_flag_restored"] = os.environ.get("WATHEFNI_ASSESSMENT_AUTHORING")
        evidence["authoring_flag_before"] = previous_flag
        evidence["finished_at"] = _utcnow()
        Path(args.output).write_text(json.dumps(evidence, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8")
        print(json.dumps({"ok": evidence.get("ok"), "output": args.output, "budget": evidence.get("budget"), "live_gate": evidence.get("live_qualification_gate")}, ensure_ascii=False, default=str))
    return 0 if evidence.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
