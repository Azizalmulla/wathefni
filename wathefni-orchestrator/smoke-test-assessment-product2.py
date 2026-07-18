#!/usr/bin/env python3
"""Offline authority and contract proof for Assessment Product-2."""

from __future__ import annotations

import json
import os
import pathlib
import sys
from typing import Any
from unittest import mock

import assessment_ai_contracts as contracts
import assessment_ai_service as service
import assessment_lifecycle as lifecycle


ROOT = pathlib.Path(__file__).resolve().parent
checks: list[dict[str, Any]] = []


def check(name: str, condition: bool, detail: Any = None) -> None:
    checks.append({"name": name, "passed": bool(condition), "detail": detail})
    if not condition:
        raise AssertionError(f"{name}: {detail}")


def expect_error(name: str, expected: str, callback: Any) -> None:
    try:
        callback()
    except service.AssessmentAIError as exc:
        check(name, exc.code == expected, exc.code)
        return
    raise AssertionError(f"{name}: expected {expected}")


def walk_schema(node: Any) -> None:
    if isinstance(node, dict):
        if node.get("type") == "object" or "properties" in node:
            properties = node.get("properties") or {}
            check("schema object forbids extras", node.get("additionalProperties") is False)
            check("schema object requires every property", set(node.get("required") or []) == set(properties))
        for value in node.values():
            walk_schema(value)
    elif isinstance(node, list):
        for value in node:
            walk_schema(value)


class FakeCursor:
    def __init__(self, rows: list[dict[str, Any]]):
        self.rows = rows

    def execute(self, sql: str, params: Any = None) -> None:
        self.sql = sql
        self.params = params

    def fetchall(self) -> list[dict[str, Any]]:
        return list(self.rows)


def valid_item() -> dict[str, Any]:
    return {
        "draft_local_id": "p2-synthetic-1",
        "locale": "en",
        "prompt_text": "A team has twelve equal tasks. What is one quarter of the tasks?",
        "choices": [
            {"key": "A", "text": "Two tasks"},
            {"key": "B", "text": "Three tasks"},
            {"key": "C", "text": "Four tasks"},
            {"key": "D", "text": "Six tasks"},
        ],
        "proposed_answer_key": "B",
        "proposed_scoring": {
            "family": "answer_key",
            "correct_points": 1,
            "incorrect_points": 0,
            "max_points": 1,
            "choice_points": [],
        },
        "rationale": "Synthetic basic proportional reasoning.",
        "explanation": "One quarter of twelve is three.",
        "distractor_rationales": [
            {"choice_key": "A", "rationale": "Divides by six."},
            {"choice_key": "C", "rationale": "Divides by three."},
            {"choice_key": "D", "rationale": "Divides by two."},
        ],
        "competency_tags": ["numerical_reasoning"],
        "skill_tags": ["fractions"],
        "role_tags": [],
        "difficulty_rationale": "Single step.",
        "assumptions": [],
        "original_content_attested": True,
        "safety_flags": [],
    }


def main() -> int:
    for name in contracts.SCHEMA_MODELS:
        schema = contracts.schema_for(name)
        walk_schema(schema)
        check(f"{name} has stable sha", len(contracts.schema_sha256(name)) == 64)

    review_schema_text = json.dumps(contracts.schema_for("AssessmentReviewResultV1"), sort_keys=True)
    adaptation_schema_text = json.dumps(contracts.schema_for("BilingualAdaptationV1"), sort_keys=True)
    for forbidden in ("candidate_score", "publish_item", "norm_percentiles", "candidate_decision"):
        check(f"review schema excludes {forbidden}", forbidden not in review_schema_text)
        check(f"adaptation schema excludes {forbidden}", forbidden not in adaptation_schema_text)
    check("adaptation schema has no answer key", "answer_key" not in adaptation_schema_text)

    provider_payload = {
        "schema_version": contracts.SCHEMA_VERSION,
        "request_id": "offline-provider-contract",
        "items": [valid_item()],
        "generation_notes": [],
        "refusal_reason": None,
    }
    captured_request: dict[str, Any] = {}

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, *args: Any) -> None:
            return None

        def read(self) -> bytes:
            return json.dumps(
                {
                    "id": "recorded-response",
                    "model": "gpt-5.4-qualified-snapshot",
                    "output": [
                        {
                            "type": "message",
                            "content": [{"type": "output_text", "text": json.dumps(provider_payload)}],
                        }
                    ],
                    "usage": {"input_tokens": 10, "output_tokens": 20},
                }
            ).encode()

    def fake_urlopen(request: Any, timeout: int):
        captured_request["body"] = json.loads(request.data.decode())
        captured_request["timeout"] = timeout
        return FakeResponse()

    with mock.patch.dict(os.environ, {"WATHEFNI_ASSESSMENT_AI_API_KEY": "offline-key"}, clear=False):
        with mock.patch("assessment_ai_service.urllib.request.urlopen", fake_urlopen):
            provider_result = service.openai_responses_adapter(
                {
                    "provider": "openai",
                    "api_kind": "openai-responses",
                    "requested_model": "gpt-5.4",
                    "parameter_profile": {"reasoning": {"effort": "medium"}, "max_output_tokens": 12000},
                    "budget_profile": {"max_latency_ms": 120000},
                },
                {"prompt_text": "Offline strict authoring fixture."},
                {"schema_name": "GeneratedItemPackageV1", "input_json": {"request_id": "offline-provider-contract"}},
            )
    check("GPT-5.4 primary model requested", captured_request["body"]["model"] == "gpt-5.4")
    check("Responses strict JSON schema enabled", captured_request["body"]["text"]["format"]["strict"] is True)
    check("authoring request exposes no tools", "tools" not in captured_request["body"])
    check("provider-returned model recorded", provider_result.provider_response_model == "gpt-5.4-qualified-snapshot")

    expect_error(
        "candidate data excluded from prompts",
        "candidate_context_forbidden",
        lambda: service.assert_authoring_payload_safe({"blueprint": {"candidate_email": "not-allowed@example.invalid"}}),
    )
    expect_error(
        "model cannot publish",
        "model_authority_field_forbidden",
        lambda: service.assert_model_output_non_authoritative({"publish": True}),
    )
    expect_error(
        "model cannot score candidate",
        "model_authority_field_forbidden",
        lambda: service.assert_model_output_non_authoritative({"candidate_score": 99}),
    )
    expect_error(
        "production remains hard off",
        "assessment_authoring_disabled",
        lambda: service.assert_authoring_enabled(environment="production", flag_value="true"),
    )
    expect_error(
        "flag off fails closed",
        "assessment_authoring_disabled",
        lambda: service.assert_authoring_enabled(environment="staging", flag_value="false"),
    )
    service.assert_authoring_enabled(environment="staging", flag_value="true")
    check("explicit staging override can run isolated pilot", True)

    normalized = service.normalize_item_content(valid_item())
    check("server compiles deterministic scoring", normalized["compiled_scoring"]["type"] == "answer_key")
    check("compiled scoring is content addressed", len(normalized["compiled_scoring_sha256"]) == 64)
    invalid = valid_item()
    invalid["proposed_answer_key"] = "Z"
    expect_error("invalid answer key rejected", "invalid_answer_key", lambda: service.normalize_item_content(invalid))
    invalid = valid_item()
    invalid["proposed_scoring"]["family"] = "executable_expression"
    expect_error("executable scoring rejected", "unsupported_scoring_family", lambda: service.normalize_item_content(invalid))
    target = {
        **normalized,
        "locale": "ar",
        "prompt_text": "لدى فريق اثنتا عشرة مهمة متساوية. كم يساوي ربع عدد المهام؟",
        "choices": [
            {"key": "A", "text": "مهمتان"},
            {"key": "B", "text": "ثلاث مهام"},
            {"key": "C", "text": "أربع مهام"},
            {"key": "D", "text": "ست مهام"},
        ],
    }
    bilingual = service.deterministic_bilingual_checks(
        source_content=normalized,
        target_content=target,
        expected_scoring_sha256=normalized["compiled_scoring_sha256"],
    )
    check("EN/AR deterministic invariants pass", bilingual["passed"] is True, bilingual)
    target_with_reordered_keys = {**target, "choices": list(reversed(target["choices"]))}
    bilingual = service.deterministic_bilingual_checks(
        source_content=normalized,
        target_content=target_with_reordered_keys,
        expected_scoring_sha256=normalized["compiled_scoring_sha256"],
    )
    check("EN/AR key reordering fails closed", bilingual["critical"] is True, bilingual)

    review = service.deterministic_product2_review(
        FakeCursor([]),
        company_code="SYNTHETIC",
        battery_key="synthetic",
        content=normalized,
    )
    check("clean synthetic deterministic review passes", review["passed"] is True, review)
    biased = dict(normalized)
    biased["prompt_text"] = "Only a young male supervisor should answer this?"
    review = service.deterministic_product2_review(
        FakeCursor([]),
        company_code="SYNTHETIC",
        battery_key="synthetic",
        content=biased,
    )
    check("protected-attribute proxy detected", bool(review["bias_flags"]), review)
    leaked = dict(normalized)
    leaked["prompt_text"] = "The correct answer is B. Which option should be selected?"
    review = service.deterministic_product2_review(
        FakeCursor([]),
        company_code="SYNTHETIC",
        battery_key="synthetic",
        content=leaked,
    )
    check("answer leakage detected", bool(review["leakage_flags"]), review)
    duplicate = service.deterministic_product2_review(
        FakeCursor([{"source_id": "live-1", "prompt_text": normalized["prompt_text"], "source_kind": "live"}]),
        company_code="SYNTHETIC",
        battery_key="synthetic",
        content=normalized,
    )
    check("exact live duplicate blocks review", duplicate["critical"] and duplicate["exact_duplicates"] == ["live-1"], duplicate)
    check(
        "semantic duplicate similarity works",
        service.similarity(
            "A team has twelve equal tasks and needs one quarter.",
            "A team has twelve equal tasks and needs one quarter of them.",
        ) >= 0.65,
    )

    check("ai_draft to automated_review valid", lifecycle.validate_authoring_transition("ai_draft", "automated_review"))
    check("automated_review to human_review valid", lifecycle.validate_authoring_transition("automated_review", "human_review"))
    check("human_review to pilot valid", lifecycle.validate_authoring_transition("human_review", "pilot"))
    check("pilot to approved valid", lifecycle.validate_authoring_transition("pilot", "approved"))
    check("approved content cannot move backwards", not lifecycle.validate_authoring_transition("approved", "pilot"))

    service_source = (ROOT / "assessment_ai_service.py").read_text()
    route_source = (ROOT / "assessment_ai_routes.py").read_text()
    schema_source = (ROOT / "assessment_lifecycle.py").read_text()
    worker_source = (ROOT / "assessment-ai-worker.py").read_text()
    role_source = (ROOT / "ops" / "provision-assessment-ai-db-role.py").read_text()
    staging_unit = (ROOT / "ops" / "wathefni-orchestrator-staging.service").read_text()
    production_unit = (ROOT / "ops" / "wathefni-orchestrator-production-environment.conf").read_text()
    forbidden_writes = [
        "UPDATE assessment_items",
        "UPDATE assessment_batteries",
        "UPDATE assessment_content_versions",
        "UPDATE assessment_attempts",
        "UPDATE assessment_responses",
        "UPDATE assessment_scores",
        "UPDATE assessment_reports",
        "UPDATE applications",
        "UPDATE offers",
        "UPDATE employees",
    ]
    check("AI service has no live/recruiting updates", not any(sql in service_source for sql in forbidden_writes))
    check("Product-2 routes expose no publish operation", "/publish" not in route_source)
    check("worker refuses production", "assessment_ai_worker_refuses_production" in worker_source)
    check(
        "worker requires dedicated DB credential",
        "assessment_ai_worker_requires_dedicated_database_credential" in worker_source,
    )
    check("DB role provisioning is staging-only", "assessment_ai_db_role_provision_refuses_non_staging" in role_source)
    check("DB role grants only item-bank read columns", "GRANT SELECT (item_id,battery_key,prompt_text,answer_key)" in role_source)
    check("DB role gets no delete grant", "GRANT DELETE" not in role_source)
    check("append-only revision table exists", "assessment_item_draft_revisions" in schema_source)
    check("model registry versions exist", "assessment_ai_model_registry_versions" in schema_source)
    check("prompt versions exist", "assessment_prompt_versions" in schema_source)
    check("AI run provenance exists", "assessment_ai_runs" in schema_source)
    check("translation pairs exist", "assessment_translation_pairs" in schema_source)
    check("staging service authoring is off", "WATHEFNI_ASSESSMENT_AUTHORING=false" in staging_unit)
    check("production authoring is explicitly off", "WATHEFNI_ASSESSMENT_AUTHORING=false" in production_unit)
    check("primary role starts with GPT-5.4", service.DEFAULT_PRIMARY_MODEL == "gpt-5.4")
    check("secondary role is independently configurable", service.DEFAULT_SECONDARY_MODEL == "gpt-5.4-mini")
    check("candidate runtime module does not import AI authoring", "assessment_ai_" not in (ROOT / "assessment_service.py").read_text())

    print(json.dumps({"passed": len(checks), "failed": 0, "checks": checks}, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(json.dumps({"passed": sum(1 for row in checks if row["passed"]), "failed": 1, "error": str(exc)}, ensure_ascii=False))
        raise
