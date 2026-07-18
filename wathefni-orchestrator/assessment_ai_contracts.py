"""Strict, provider-neutral contracts for Assessment Product-2.

These contracts describe data returned by authoring models.  They deliberately
contain no publish, live scoring, norm activation, or recruiting-decision
fields.  JSON schemas are generated from these types and then hardened for
providers that require every property to be explicitly required.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any, Literal

from pydantic import BaseModel, Field


SCHEMA_VERSION = "assessment_product2_v1"
LOCALES = ("en", "ar")


class StrictModel(BaseModel):
    class Config:
        extra = "forbid"


class AssessmentAuthoringRequestV1(StrictModel):
    schema_version: Literal["assessment_product2_v1"]
    request_id: str = Field(min_length=1, max_length=200)
    blueprint_id: str = Field(min_length=1, max_length=200)
    blueprint_version: int = Field(ge=1)
    blueprint_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    source_locale: Literal["en", "ar"]
    section: str = Field(min_length=1, max_length=120)
    constructs: list[str] = Field(min_length=1, max_length=20)
    item_type: Literal["single_choice", "competency_keyed"]
    difficulty_target: Literal["easy", "medium", "hard"]
    reading_level: str = Field(min_length=1, max_length=120)
    role_context: list[str] = Field(max_length=20)
    allowed_context: list[str] = Field(max_length=50)
    prohibited_content: list[str] = Field(min_length=1, max_length=100)
    scoring_family: Literal["answer_key", "competency_keyed"]
    choice_count: int = Field(ge=2, le=6)
    requested_item_count: int = Field(ge=1, le=20)
    originality_policy_version: str = Field(min_length=1, max_length=120)


class GeneratedChoiceV1(StrictModel):
    key: str = Field(pattern=r"^[A-Z0-9_]{1,20}$")
    text: str = Field(min_length=1, max_length=4000)


class DistractorRationaleV1(StrictModel):
    choice_key: str = Field(pattern=r"^[A-Z0-9_]{1,20}$")
    rationale: str = Field(min_length=1, max_length=4000)


class ChoicePointV1(StrictModel):
    choice_key: str = Field(pattern=r"^[A-Z0-9_]{1,20}$")
    points: float = Field(ge=0, le=100)


class ScoringSpecProposalV1(StrictModel):
    family: Literal["answer_key", "competency_keyed"]
    correct_points: float = Field(ge=0, le=100)
    incorrect_points: float = Field(ge=0, le=100)
    max_points: float = Field(gt=0, le=100)
    choice_points: list[ChoicePointV1] = Field(max_length=6)


class GeneratedItemV1(StrictModel):
    draft_local_id: str = Field(min_length=1, max_length=120)
    locale: Literal["en", "ar"]
    prompt_text: str = Field(min_length=10, max_length=8000)
    choices: list[GeneratedChoiceV1] = Field(min_length=2, max_length=6)
    proposed_answer_key: str = Field(pattern=r"^[A-Z0-9_]{1,20}$")
    proposed_scoring: ScoringSpecProposalV1
    rationale: str = Field(min_length=1, max_length=8000)
    explanation: str = Field(min_length=1, max_length=8000)
    distractor_rationales: list[DistractorRationaleV1]
    competency_tags: list[str] = Field(max_length=20)
    skill_tags: list[str] = Field(max_length=20)
    role_tags: list[str] = Field(max_length=20)
    difficulty_rationale: str = Field(min_length=1, max_length=4000)
    assumptions: list[str] = Field(max_length=20)
    original_content_attested: Literal[True]
    safety_flags: list[str] = Field(max_length=50)


class GeneratedItemPackageV1(StrictModel):
    schema_version: Literal["assessment_product2_v1"]
    request_id: str = Field(min_length=1, max_length=200)
    items: list[GeneratedItemV1] = Field(max_length=20)
    generation_notes: list[str] = Field(max_length=50)
    refusal_reason: str | None


class EvidenceSpanV1(StrictModel):
    field: str = Field(min_length=1, max_length=120)
    quote: str = Field(max_length=2000)
    explanation: str = Field(min_length=1, max_length=4000)


class ReviewDimensionV1(StrictModel):
    dimension: Literal[
        "schema_blueprint_fit",
        "answer_correctness",
        "ambiguity",
        "duplicate_risk",
        "bias_fairness",
        "leakage",
        "distractor_quality",
        "difficulty",
        "language_quality",
    ]
    verdict: Literal["pass", "warn", "fail"]
    severity: Literal["none", "low", "medium", "high", "critical"]
    confidence: float = Field(ge=0, le=1)
    evidence: list[EvidenceSpanV1] = Field(max_length=20)
    explanation: str = Field(min_length=1, max_length=8000)


class AssessmentReviewResultV1(StrictModel):
    schema_version: Literal["assessment_product2_v1"]
    draft_revision_id: str = Field(min_length=1, max_length=200)
    draft_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    reviewer_role_version: str = Field(min_length=1, max_length=200)
    dimensions: list[ReviewDimensionV1] = Field(min_length=9, max_length=9)
    overall_recommendation: Literal["pass", "rewrite", "required_human_attention"]
    critical_findings: list[str] = Field(max_length=50)
    refusal_reason: str | None


class AdaptedChoiceV1(StrictModel):
    key: str = Field(pattern=r"^[A-Z0-9_]{1,20}$")
    text: str = Field(min_length=1, max_length=4000)


class BilingualAdaptationV1(StrictModel):
    schema_version: Literal["assessment_product2_v1"]
    source_revision_id: str = Field(min_length=1, max_length=200)
    source_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    source_locale: Literal["en", "ar"]
    target_locale: Literal["en", "ar"]
    adapted_prompt_text: str = Field(min_length=10, max_length=8000)
    adapted_choices: list[AdaptedChoiceV1] = Field(min_length=2, max_length=6)
    terminology_decisions: list[str] = Field(max_length=50)
    cultural_adaptations: list[str] = Field(max_length=50)
    back_translation_summary: str = Field(min_length=1, max_length=8000)
    preserved_invariants: list[str] = Field(min_length=1, max_length=50)
    refusal_reason: str | None


class EquivalenceFindingV1(StrictModel):
    dimension: Literal[
        "semantic_equivalence",
        "answer_key_invariance",
        "linguistic_naturalness",
        "rtl_punctuation_numerals",
        "cultural_fairness",
        "difficulty_drift",
    ]
    verdict: Literal["pass", "warn", "fail"]
    severity: Literal["none", "low", "medium", "high", "critical"]
    evidence: list[EvidenceSpanV1] = Field(max_length=20)
    explanation: str = Field(min_length=1, max_length=8000)


class BilingualReviewResultV1(StrictModel):
    schema_version: Literal["assessment_product2_v1"]
    translation_pair_id: str = Field(min_length=1, max_length=200)
    source_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    target_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    findings: list[EquivalenceFindingV1] = Field(min_length=6, max_length=6)
    overall_recommendation: Literal["pass", "rewrite", "required_human_attention"]
    refusal_reason: str | None


class DeterministicEvalMetricsV1(StrictModel):
    schema_valid: bool
    answer_key_valid: bool
    deterministic_solver_agreement: bool | None
    duplicate_detected: bool
    critical_ambiguity_detected: bool
    critical_bias_detected: bool
    critical_leakage_detected: bool
    translation_equivalent: bool | None
    difficulty_drift: float | None


class OfflineEvalResultV1(StrictModel):
    schema_version: Literal["assessment_product2_v1"]
    eval_case_id: str = Field(min_length=1, max_length=200)
    eval_corpus_version: str = Field(min_length=1, max_length=120)
    model_role_version: str = Field(min_length=1, max_length=200)
    prompt_version: str = Field(min_length=1, max_length=200)
    output_schema_version: str = Field(min_length=1, max_length=120)
    deterministic_metrics: DeterministicEvalMetricsV1
    blinded_human_rating: float | None = Field(ge=0, le=5)
    input_tokens: int = Field(ge=0)
    output_tokens: int = Field(ge=0)
    estimated_cost_usd: float = Field(ge=0)
    latency_ms: int = Field(ge=0)
    failure_class: str | None
    gate_profile_version: str = Field(min_length=1, max_length=120)
    passed: bool


SCHEMA_MODELS: dict[str, type[StrictModel]] = {
    "AssessmentAuthoringRequestV1": AssessmentAuthoringRequestV1,
    "GeneratedItemPackageV1": GeneratedItemPackageV1,
    "AssessmentReviewResultV1": AssessmentReviewResultV1,
    "BilingualAdaptationV1": BilingualAdaptationV1,
    "BilingualReviewResultV1": BilingualReviewResultV1,
    "OfflineEvalResultV1": OfflineEvalResultV1,
}


def _model_json_schema(model: type[StrictModel]) -> dict[str, Any]:
    if hasattr(model, "model_json_schema"):
        schema = model.model_json_schema()  # type: ignore[attr-defined]
    else:
        schema = model.schema()
    return _strictify_schema(schema)


def _strictify_schema(node: Any) -> Any:
    if isinstance(node, list):
        return [_strictify_schema(value) for value in node]
    if not isinstance(node, dict):
        return node
    out = {key: _strictify_schema(value) for key, value in node.items()}
    if out.get("type") == "object" or "properties" in out:
        properties = out.get("properties") if isinstance(out.get("properties"), dict) else {}
        out["additionalProperties"] = False
        out["required"] = list(properties)
    return out


def schema_for(name: str) -> dict[str, Any]:
    try:
        return _model_json_schema(SCHEMA_MODELS[name])
    except KeyError as exc:
        raise ValueError(f"unknown_assessment_ai_schema:{name}") from exc


def schema_sha256(name: str) -> str:
    encoded = json.dumps(schema_for(name), sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def validate_contract(name: str, payload: dict[str, Any]) -> StrictModel:
    try:
        model = SCHEMA_MODELS[name]
    except KeyError as exc:
        raise ValueError(f"unknown_assessment_ai_schema:{name}") from exc
    if hasattr(model, "model_validate"):
        validated = model.model_validate(payload)  # type: ignore[attr-defined]
    else:
        validated = model.parse_obj(payload)
    _validate_semantic_invariants(name, model_to_dict(validated))
    return validated


def _validate_semantic_invariants(name: str, payload: dict[str, Any]) -> None:
    if name == "GeneratedItemPackageV1":
        items = payload.get("items") or []
        if (payload.get("refusal_reason") and items) or (not payload.get("refusal_reason") and not items):
            raise ValueError("generated_item_refusal_invariant_failed")
        for item in items:
            keys = [choice["key"] for choice in item.get("choices") or []]
            if len(keys) != len(set(keys)) or item.get("proposed_answer_key") not in keys:
                raise ValueError("generated_item_choice_key_invariant_failed")
            distractor_keys = [row["choice_key"] for row in item.get("distractor_rationales") or []]
            expected = {key for key in keys if key != item.get("proposed_answer_key")}
            if set(distractor_keys) != expected or len(distractor_keys) != len(expected):
                raise ValueError("generated_item_distractor_rationale_invariant_failed")
    elif name == "AssessmentReviewResultV1":
        expected = {
            "schema_blueprint_fit",
            "answer_correctness",
            "ambiguity",
            "duplicate_risk",
            "bias_fairness",
            "leakage",
            "distractor_quality",
            "difficulty",
            "language_quality",
        }
        dimensions = [row["dimension"] for row in payload.get("dimensions") or []]
        if set(dimensions) != expected or len(dimensions) != len(expected):
            raise ValueError("assessment_review_dimension_invariant_failed")
    elif name == "BilingualAdaptationV1":
        if payload.get("source_locale") == payload.get("target_locale"):
            raise ValueError("bilingual_adaptation_locale_invariant_failed")
        keys = [choice["key"] for choice in payload.get("adapted_choices") or []]
        if len(keys) != len(set(keys)):
            raise ValueError("bilingual_adaptation_choice_key_invariant_failed")
    elif name == "BilingualReviewResultV1":
        expected = {
            "semantic_equivalence",
            "answer_key_invariance",
            "linguistic_naturalness",
            "rtl_punctuation_numerals",
            "cultural_fairness",
            "difficulty_drift",
        }
        dimensions = [row["dimension"] for row in payload.get("findings") or []]
        if set(dimensions) != expected or len(dimensions) != len(expected):
            raise ValueError("bilingual_review_dimension_invariant_failed")


def model_to_dict(value: StrictModel) -> dict[str, Any]:
    if hasattr(value, "model_dump"):
        return value.model_dump(mode="json")  # type: ignore[attr-defined]
    return value.dict()
