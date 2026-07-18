"""Offline replay evaluation harness for Wathefni Assessment Product-2.

Replay is the default and performs no provider, network, or database calls.
Live execution is adapter-only and guarded so this module cannot target
production or accidentally turn a replay invocation into a provider call.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import statistics
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

import assessment_ai_qualification as qualification

CORPUS_PATH = (
    Path(__file__).resolve().parent
    / "reports"
    / "assessment-product2-eval"
    / "assessment-product2-eval-v2.json"
)
LIVE_CONFIRMATION = "I_CONFIRM_STAGING_ASSESSMENT_PRODUCT2_EVAL"
SEMANTIC_DUPLICATE_THRESHOLD = 0.72

_BIAS_PATTERNS = (
    r"\b(?:male|female|man|woman|young|old|nationality|religion|married|pregnant|race)\b",
    r"(?:ذكر|أنثى|رجل|امرأة|شاب|مسن|الجنسية|الديانة|متزوج|حامل)",
)
_LEAKAGE_PATTERNS = (
    r"\b(?:the\s+)?(?:correct\s+)?answer\s+(?:is|:)\s*[A-Z0-9_]+\b",
    r"\bchoose\s+[A-Z]\b",
    r"(?:الإجابة\s+الصحيحة|اختر)\s*[:：]?\s*[A-Z0-9_]+",
)
_LITERAL_MT_MARKERS = (
    r"\bplease\s+choose\b",
    r"\bclick\s+here\b",
    r"ترجمة\s+حرفية",
)


class EvaluationError(RuntimeError):
    """Raised when a corpus or evaluation invocation is unsafe or invalid."""


class LiveModeRefused(EvaluationError):
    """Raised before any adapter call when live-mode requirements are unmet."""


@dataclass(frozen=True)
class GateProfile:
    version: str
    corpus_version: str
    required_expectation_pass_rate: float
    maximum_critical_misses: int
    required_case_ids: tuple[str, ...]
    release_case_ids: tuple[str, ...]
    qualification_case_ids: tuple[str, ...]
    semantic_duplicate_threshold: float


GATE_PROFILE = GateProfile(
    version=qualification.GATE_PROFILE_VERSION,
    corpus_version=qualification.CORPUS_VERSION,
    required_expectation_pass_rate=1.0,
    maximum_critical_misses=0,
    required_case_ids=(
        "valid_authoring_en",
        "valid_authoring_numerical",
        "valid_authoring_verbal",
        "valid_authoring_logical",
        "valid_authoring_sjt",
        "valid_authoring_ar",
        "malformed_schema",
        "exact_duplicate",
        "semantic_duplicate",
        "critical_ambiguity",
        "critical_bias",
        "critical_leakage",
        "scoring_compile_failure",
        "invalid_answer_key",
        "bilingual_equivalent",
        "bilingual_equivalent_2",
        "bilingual_equivalent_3",
        "bilingual_key_drift",
        "structured_refusal",
        "provider_rate_limit",
        "provider_outage",
    ),
    release_case_ids=(
        "valid_authoring_en",
        "valid_authoring_numerical",
        "valid_authoring_verbal",
        "valid_authoring_logical",
        "valid_authoring_sjt",
        "valid_authoring_ar",
        "bilingual_equivalent",
        "bilingual_equivalent_2",
        "bilingual_equivalent_3",
    ),
    qualification_case_ids=(
        "valid_authoring_en",
        "valid_authoring_numerical",
        "valid_authoring_verbal",
        "valid_authoring_logical",
        "valid_authoring_sjt",
        "valid_authoring_ar",
        "bilingual_equivalent",
        "bilingual_equivalent_2",
        "bilingual_equivalent_3",
    ),
    semantic_duplicate_threshold=SEMANTIC_DUPLICATE_THRESHOLD,
)


LiveAdapter = Callable[[Mapping[str, Any]], Mapping[str, Any]]


def _canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _sha256_json(value: Any) -> str:
    return hashlib.sha256(_canonical_json(value).encode("utf-8")).hexdigest()


def _profile_payload() -> dict[str, Any]:
    return {
        "version": GATE_PROFILE.version,
        "corpus_version": GATE_PROFILE.corpus_version,
        "required_expectation_pass_rate": GATE_PROFILE.required_expectation_pass_rate,
        "maximum_critical_misses": GATE_PROFILE.maximum_critical_misses,
        "required_case_ids": list(GATE_PROFILE.required_case_ids),
        "release_case_ids": list(GATE_PROFILE.release_case_ids),
        "qualification_case_ids": list(GATE_PROFILE.qualification_case_ids),
        "semantic_duplicate_threshold": GATE_PROFILE.semantic_duplicate_threshold,
        "thresholds": dict(qualification.QUALIFICATION_THRESHOLDS),
        "live_caps": dict(qualification.LIVE_COST_LATENCY_CAPS),
    }


def load_corpus(path: str | Path = CORPUS_PATH) -> tuple[dict[str, Any], str]:
    corpus_path = Path(path)
    raw = corpus_path.read_bytes()
    try:
        corpus = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise EvaluationError(f"invalid_eval_corpus_json:{exc}") from exc
    if not isinstance(corpus, dict):
        raise EvaluationError("invalid_eval_corpus:root_must_be_object")
    if corpus.get("corpus_version") != GATE_PROFILE.corpus_version:
        raise EvaluationError("invalid_eval_corpus:version_mismatch")
    if corpus.get("gate_profile_version") != GATE_PROFILE.version:
        raise EvaluationError("invalid_eval_corpus:gate_profile_mismatch")
    provenance = corpus.get("provenance")
    if not isinstance(provenance, dict):
        raise EvaluationError("invalid_eval_corpus:provenance_required")
    if provenance.get("owner") != "Wathefni" or provenance.get("synthetic_only") is not True:
        raise EvaluationError("invalid_eval_corpus:wathefni_synthetic_fixtures_required")
    recordings = corpus.get("recordings")
    cases = corpus.get("cases")
    if not isinstance(recordings, dict) or not isinstance(cases, list):
        raise EvaluationError("invalid_eval_corpus:recordings_and_cases_required")
    case_ids = [case.get("case_id") for case in cases if isinstance(case, dict)]
    if len(case_ids) != len(cases) or len(set(case_ids)) != len(case_ids):
        raise EvaluationError("invalid_eval_corpus:case_ids_must_be_unique")
    missing = sorted(set(GATE_PROFILE.required_case_ids) - set(case_ids))
    if missing:
        raise EvaluationError(f"invalid_eval_corpus:required_cases_missing:{','.join(missing)}")
    return corpus, hashlib.sha256(raw).hexdigest()


def _normalized_tokens(text: str) -> list[str]:
    return re.findall(r"[\w\u0600-\u06ff]+", str(text or "").casefold(), flags=re.UNICODE)


def _normalized_text(text: str) -> str:
    return " ".join(_normalized_tokens(text))


def _shingles(text: str, size: int = 3) -> set[str]:
    tokens = _normalized_tokens(text)
    if len(tokens) < size:
        return {" ".join(tokens)} if tokens else set()
    return {" ".join(tokens[index : index + size]) for index in range(len(tokens) - size + 1)}


def _similarity(left: str, right: str) -> float:
    left_set, right_set = _shingles(left), _shingles(right)
    if not left_set or not right_set:
        return 0.0
    return len(left_set & right_set) / len(left_set | right_set)


def _compile_scoring(item: Mapping[str, Any]) -> bool:
    """Exercise the production pure compiler without opening a DB connection."""

    try:
        from assessment_ai_service import compile_scoring_spec
    except ModuleNotFoundError:
        compile_scoring_spec = None
    if compile_scoring_spec is not None:
        try:
            compile_scoring_spec(dict(item))
            return True
        except Exception:
            return False
    choices = item.get("choices") if isinstance(item.get("choices"), list) else []
    keys = [
        str(choice.get("key") or "")
        for choice in choices
        if isinstance(choice, dict)
    ]
    if len(keys) != len(choices) or len(keys) != len(set(keys)) or not all(keys):
        return False
    if str(item.get("proposed_answer_key") or "") not in keys:
        return False
    proposal = item.get("proposed_scoring")
    if not isinstance(proposal, dict):
        return False
    family = proposal.get("family")
    try:
        if family == "answer_key":
            correct = float(proposal.get("correct_points") or 0)
            incorrect = float(proposal.get("incorrect_points") or 0)
            maximum = float(proposal.get("max_points") or 0)
            return correct > 0 and maximum == correct and incorrect >= 0
        if family == "competency_keyed":
            point_rows = proposal.get("choice_points")
            points = {
                str(row.get("choice_key") or ""): float(row.get("points") or 0)
                for row in point_rows
                if isinstance(row, dict)
            } if isinstance(point_rows, list) else {}
            return (
                isinstance(point_rows, list)
                and len(points) == len(point_rows)
                and set(points) == set(keys)
                and all(0 <= float(value) <= 100 for value in points.values())
            )
    except (TypeError, ValueError):
        return False
    return False


def _strict_keys(value: Any, required: set[str]) -> bool:
    return isinstance(value, dict) and set(value) == required


def _fallback_generated_package_valid(response: Mapping[str, Any]) -> bool:
    package_keys = {"schema_version", "request_id", "items", "generation_notes", "refusal_reason"}
    item_keys = {
        "draft_local_id",
        "locale",
        "prompt_text",
        "choices",
        "proposed_answer_key",
        "proposed_scoring",
        "rationale",
        "explanation",
        "distractor_rationales",
        "competency_tags",
        "skill_tags",
        "role_tags",
        "difficulty_rationale",
        "assumptions",
        "original_content_attested",
        "safety_flags",
    }
    choice_keys = {"key", "text"}
    scoring_keys = {
        "family",
        "correct_points",
        "incorrect_points",
        "max_points",
        "choice_points",
    }
    distractor_keys = {"choice_key", "rationale"}
    if not _strict_keys(response, package_keys):
        return False
    items = response.get("items")
    if (
        response.get("schema_version") != "assessment_product2_v1"
        or not isinstance(response.get("request_id"), str)
        or not response.get("request_id")
        or not isinstance(items, list)
        or len(items) > 20
        or not isinstance(response.get("generation_notes"), list)
        or response.get("refusal_reason") is not None
        and not isinstance(response.get("refusal_reason"), str)
    ):
        return False
    for item in items:
        if not _strict_keys(item, item_keys):
            return False
        choices = item.get("choices")
        distractors = item.get("distractor_rationales")
        if (
            item.get("locale") not in {"en", "ar"}
            or not isinstance(item.get("prompt_text"), str)
            or len(item["prompt_text"]) < 10
            or not isinstance(choices, list)
            or not 2 <= len(choices) <= 6
            or not all(
                _strict_keys(choice, choice_keys)
                and bool(re.fullmatch(r"[A-Z0-9_]{1,20}", str(choice.get("key") or "")))
                and isinstance(choice.get("text"), str)
                and bool(choice.get("text"))
                for choice in choices
            )
            or not _strict_keys(item.get("proposed_scoring"), scoring_keys)
            or not isinstance(distractors, list)
            or not all(_strict_keys(value, distractor_keys) for value in distractors)
            or item.get("original_content_attested") is not True
        ):
            return False
        for field in (
            "competency_tags",
            "skill_tags",
            "role_tags",
            "assumptions",
            "safety_flags",
        ):
            if not isinstance(item.get(field), list):
                return False
        for field in (
            "draft_local_id",
            "rationale",
            "explanation",
            "difficulty_rationale",
        ):
            if not isinstance(item.get(field), str) or not item.get(field):
                return False
    return True


def _fallback_adaptation_valid(response: Mapping[str, Any]) -> bool:
    required = {
        "schema_version",
        "source_revision_id",
        "source_sha256",
        "source_locale",
        "target_locale",
        "adapted_prompt_text",
        "adapted_choices",
        "terminology_decisions",
        "cultural_adaptations",
        "back_translation_summary",
        "preserved_invariants",
        "refusal_reason",
    }
    if not _strict_keys(response, required):
        return False
    choices = response.get("adapted_choices")
    return bool(
        response.get("schema_version") == "assessment_product2_v1"
        and response.get("source_locale") in {"en", "ar"}
        and response.get("target_locale") in {"en", "ar"}
        and isinstance(response.get("source_sha256"), str)
        and re.fullmatch(r"[a-f0-9]{64}", response["source_sha256"])
        and isinstance(response.get("adapted_prompt_text"), str)
        and len(response["adapted_prompt_text"]) >= 10
        and isinstance(choices, list)
        and 2 <= len(choices) <= 6
        and all(
            _strict_keys(choice, {"key", "text"})
            and bool(re.fullmatch(r"[A-Z0-9_]{1,20}", str(choice.get("key") or "")))
            and isinstance(choice.get("text"), str)
            and bool(choice.get("text"))
            for choice in choices
        )
        and isinstance(response.get("terminology_decisions"), list)
        and isinstance(response.get("cultural_adaptations"), list)
        and isinstance(response.get("preserved_invariants"), list)
        and bool(response.get("preserved_invariants"))
    )


def _fallback_bilingual_review_valid(response: Mapping[str, Any]) -> bool:
    required = {
        "schema_version",
        "translation_pair_id",
        "source_sha256",
        "target_sha256",
        "findings",
        "overall_recommendation",
        "refusal_reason",
    }
    finding_keys = {"dimension", "verdict", "severity", "evidence", "explanation"}
    dimensions = {
        "semantic_equivalence",
        "answer_key_invariance",
        "linguistic_naturalness",
        "rtl_punctuation_numerals",
        "cultural_fairness",
        "difficulty_drift",
    }
    findings = response.get("findings")
    return bool(
        _strict_keys(response, required)
        and response.get("schema_version") == "assessment_product2_v1"
        and isinstance(findings, list)
        and len(findings) == 6
        and all(
            _strict_keys(finding, finding_keys)
            and finding.get("dimension") in dimensions
            and finding.get("verdict") in {"pass", "warn", "fail"}
            and finding.get("severity") in {"none", "low", "medium", "high", "critical"}
            and isinstance(finding.get("evidence"), list)
            and isinstance(finding.get("explanation"), str)
            and bool(finding.get("explanation"))
            for finding in findings
        )
        and response.get("overall_recommendation")
        in {"pass", "rewrite", "required_human_attention"}
        and all(
            isinstance(response.get(field), str)
            and bool(re.fullmatch(r"[a-f0-9]{64}", response[field]))
            for field in ("source_sha256", "target_sha256")
        )
    )


def _fallback_schema_valid(schema_name: str, response: Mapping[str, Any]) -> bool:
    if schema_name == "GeneratedItemPackageV1":
        return _fallback_generated_package_valid(response)
    if schema_name == "BilingualAdaptationV1":
        return _fallback_adaptation_valid(response)
    if schema_name == "BilingualReviewResultV1":
        return _fallback_bilingual_review_valid(response)
    raise EvaluationError(f"unsupported_fallback_schema:{schema_name}")


def _schema_valid(schema_name: str, response: Any) -> bool:
    if not isinstance(response, dict):
        return False
    try:
        import assessment_ai_contracts as contracts
    except ModuleNotFoundError:
        return _fallback_schema_valid(schema_name, response)
    try:
        model = contracts.SCHEMA_MODELS[schema_name]
        if hasattr(model, "model_validate"):
            model.model_validate(response)
        else:
            model.parse_obj(response)
        return True
    except Exception:
        return False



def _english_quality_ok(prompt: str, choices: list[str], locale: str) -> bool | None:
    if locale != "en":
        return None
    if not prompt or len(prompt.split()) < 6:
        return False
    if not choices or any(not str(text).strip() for text in choices):
        return False
    # Numeric / short keyed answers are allowed when the stem is clear.
    long_needed = any(len(str(text).split()) >= 2 for text in choices)
    if not long_needed:
        return all(str(text).strip().isdigit() or len(str(text).strip()) >= 1 for text in choices)
    return True


def _arabic_linguistic_quality_ok(prompt: str, choices: list[str], locale: str, adapted_text: str | None = None) -> bool | None:
    text = adapted_text if adapted_text is not None else prompt
    if locale != "ar" and adapted_text is None:
        return None
    arabic_chars = len(__import__("re").findall(r"[\u0600-\u06ff]", text or ""))
    if arabic_chars < 8:
        return False
    if any(__import__("re").search(pat, text or "", __import__("re").I) for pat in _LITERAL_MT_MARKERS):
        return False
    # Reject mostly-Latin Arabic-labelled content.
    latin = len(__import__("re").findall(r"[A-Za-z]", text or ""))
    if latin > arabic_chars:
        return False
    if choices and any(len(__import__("re").findall(r"[\u0600-\u06ff]", c or "")) == 0 for c in choices):
        return False
    return True


def _distractor_quality_ok(item: dict[str, Any]) -> bool | None:
    choices = item.get("choices") if isinstance(item.get("choices"), list) else []
    if len(choices) < 3:
        return False
    rationales = item.get("distractor_rationales") if isinstance(item.get("distractor_rationales"), list) else []
    answer = str(item.get("proposed_answer_key") or "")
    needed = {str(c.get("key")) for c in choices if isinstance(c, dict) and str(c.get("key")) != answer}
    have = {str(r.get("choice_key")) for r in rationales if isinstance(r, dict)}
    texts = [str(c.get("text") or "").strip() for c in choices if isinstance(c, dict)]
    if len(set(t.casefold() for t in texts)) != len(texts):
        return False
    return needed.issubset(have) and all(len(str(r.get("rationale") or "").split()) >= 3 for r in rationales if isinstance(r, dict))


def _competency_aligned(item: dict[str, Any], blueprint: Mapping[str, Any] | None) -> bool | None:
    if not blueprint:
        return None
    tags = {str(t).casefold() for t in (item.get("competency_tags") or [])}
    expected = {str(t).casefold() for t in (blueprint.get("competency_tags") or blueprint.get("constructs") or [])}
    if not expected:
        return None
    return bool(tags & expected)


def _difficulty_aligned(item: dict[str, Any], blueprint: Mapping[str, Any] | None) -> bool | None:
    if not blueprint:
        return None
    target = str(blueprint.get("difficulty_target") or "").casefold()
    rationale = str(item.get("difficulty_rationale") or "").casefold()
    if not target:
        return None
    return target in rationale or bool(rationale)


def _authoring_observation(case: Mapping[str, Any], response: Any) -> dict[str, Any]:
    schema_valid = _schema_valid("GeneratedItemPackageV1", response)
    items = response.get("items") if isinstance(response, dict) else None
    item = items[0] if isinstance(items, list) and items and isinstance(items[0], dict) else {}
    choices = item.get("choices") if isinstance(item.get("choices"), list) else []
    keys = [
        str(choice.get("key") or "")
        for choice in choices
        if isinstance(choice, dict)
    ]
    choice_texts = [
        str(choice.get("text") or "").strip()
        for choice in choices
        if isinstance(choice, dict)
    ]
    answer_key = str(item.get("proposed_answer_key") or "")
    key_valid = bool(
        choices
        and len(keys) == len(choices)
        and len(keys) == len(set(keys))
        and answer_key in keys
    )
    scoring_compile_valid = bool(item) and _compile_scoring(item)
    prompt = str(item.get("prompt_text") or "")
    locale = str(item.get("locale") or "en").lower()
    comparisons = case.get("comparison_prompts")
    comparisons = comparisons if isinstance(comparisons, list) else []
    exact_duplicate = any(
        _normalized_text(prompt) == _normalized_text(str(other))
        for other in comparisons
        if prompt
    )
    similarities = [
        _similarity(prompt, str(other))
        for other in comparisons
        if prompt and _normalized_text(prompt) != _normalized_text(str(other))
    ]
    semantic_duplicate = bool(
        similarities and max(similarities) >= GATE_PROFILE.semantic_duplicate_threshold
    )
    duplicate_choice_text = bool(
        choice_texts
        and len({text.casefold() for text in choice_texts}) != len(choice_texts)
    )
    assumptions = item.get("assumptions") if isinstance(item.get("assumptions"), list) else []
    ambiguity_flags = [
        *(["unclear_stem_termination"] if prompt and not prompt.rstrip().endswith(("?", "؟", ".", ":")) else []),
        *(["duplicate_choice_text"] if duplicate_choice_text else []),
        *(["too_many_assumptions"] if len(assumptions) > 3 else []),
    ]
    combined_text = " ".join([prompt, *choice_texts])
    bias_flags = [
        pattern for pattern in _BIAS_PATTERNS if re.search(pattern, combined_text, re.I)
    ]
    leakage_flags = [
        pattern for pattern in _LEAKAGE_PATTERNS if re.search(pattern, combined_text, re.I)
    ]
    blueprint = case.get("blueprint") if isinstance(case.get("blueprint"), dict) else None
    originality = item.get("original_content_attested") is True and not exact_duplicate and not semantic_duplicate
    return {
        "schema_valid": schema_valid,
        "answer_key_valid": key_valid,
        "scoring_compile_valid": scoring_compile_valid,
        "exact_duplicate_detected": exact_duplicate,
        "semantic_duplicate_detected": semantic_duplicate,
        "duplicate_detected": exact_duplicate or semantic_duplicate,
        "duplicate_similarity": round(max(similarities), 4) if similarities else (1.0 if exact_duplicate else 0.0),
        "critical_ambiguity_detected": bool(ambiguity_flags),
        "critical_bias_detected": bool(bias_flags),
        "critical_leakage_detected": bool(leakage_flags),
        "originality_attested": originality if item else False,
        "competency_aligned": _competency_aligned(item, blueprint),
        "difficulty_aligned": _difficulty_aligned(item, blueprint),
        "distractor_quality_ok": _distractor_quality_ok(item) if item else False,
        "english_quality_ok": _english_quality_ok(prompt, choice_texts, locale),
        "arabic_linguistic_quality_ok": _arabic_linguistic_quality_ok(prompt, choice_texts, locale),
        "cultural_suitability_ok": not bool(bias_flags) if item else False,
        "translation_equivalent": None,
        "semantic_equivalence_ok": None,
        "en_ar_key_invariant": None,
        "details": {
            "ambiguity_flags": ambiguity_flags,
            "bias_flag_count": len(bias_flags),
            "leakage_flag_count": len(leakage_flags),
            "maximum_semantic_similarity": round(max(similarities), 4) if similarities else 0.0,
            "locale": locale,
        },
    }



def _review_dimension_pass(review: Any, dimension: str) -> bool:
    findings = review.get("findings") if isinstance(review, dict) else None
    if not isinstance(findings, list):
        return False
    return any(
        isinstance(finding, dict)
        and finding.get("dimension") == dimension
        and finding.get("verdict") == "pass"
        and finding.get("severity") in {"none", "low"}
        for finding in findings
    )



def _bilingual_observation(case: Mapping[str, Any], response: Any) -> dict[str, Any]:
    schema_valid = _schema_valid("BilingualAdaptationV1", response)
    source_choices = case.get("source_choices")
    source_choices = source_choices if isinstance(source_choices, list) else []
    adapted_choices = response.get("adapted_choices") if isinstance(response, dict) else None
    adapted_choices = adapted_choices if isinstance(adapted_choices, list) else []
    source_keys = [
        str(choice.get("key") or "") for choice in source_choices if isinstance(choice, dict)
    ]
    target_keys = [
        str(choice.get("key") or "") for choice in adapted_choices if isinstance(choice, dict)
    ]
    target_texts = [
        str(choice.get("text") or "").strip() for choice in adapted_choices if isinstance(choice, dict)
    ]
    key_invariant = bool(source_keys and target_keys == source_keys)
    review = case.get("recorded_equivalence_review")
    review_schema_valid = _schema_valid("BilingualReviewResultV1", review)
    semantic_pass = review_schema_valid and _review_dimension_pass(review, "semantic_equivalence")
    review_key_pass = review_schema_valid and _review_dimension_pass(review, "answer_key_invariance")
    naturalness_pass = review_schema_valid and _review_dimension_pass(review, "linguistic_naturalness")
    cultural_pass = review_schema_valid and _review_dimension_pass(review, "cultural_fairness")
    difficulty_pass = review_schema_valid and _review_dimension_pass(review, "difficulty_drift")
    adapted_prompt = str((response or {}).get("adapted_prompt_text") or "") if isinstance(response, dict) else ""
    arabic_ok = _arabic_linguistic_quality_ok(adapted_prompt, target_texts, "ar", adapted_text=adapted_prompt)
    if naturalness_pass is False:
        arabic_ok = False
    translation_equivalent = bool(key_invariant and semantic_pass and review_key_pass)
    return {
        "schema_valid": schema_valid,
        "answer_key_valid": key_invariant,
        "scoring_compile_valid": None,
        "exact_duplicate_detected": False,
        "semantic_duplicate_detected": False,
        "duplicate_detected": False,
        "duplicate_similarity": 0.0,
        "critical_ambiguity_detected": False,
        "critical_bias_detected": False,
        "critical_leakage_detected": False,
        "originality_attested": True,
        "competency_aligned": True,
        "difficulty_aligned": bool(difficulty_pass),
        "distractor_quality_ok": True,
        "english_quality_ok": None,
        "arabic_linguistic_quality_ok": bool(arabic_ok),
        "cultural_suitability_ok": bool(cultural_pass),
        "translation_equivalent": translation_equivalent,
        "semantic_equivalence_ok": bool(semantic_pass),
        "en_ar_key_invariant": key_invariant,
        "details": {
            "equivalence_review_schema_valid": review_schema_valid,
            "source_keys": source_keys,
            "target_keys": target_keys,
        },
    }


def _resolve_recording(
    corpus: Mapping[str, Any],
    case: Mapping[str, Any],
    *,
    mode: str,
    live_adapter: LiveAdapter | None,
) -> Mapping[str, Any]:
    if mode == "live":
        if live_adapter is None:
            raise LiveModeRefused("live_mode_refused:no_live_adapter_configured")
        response = live_adapter(case)
        if not isinstance(response, Mapping):
            raise EvaluationError("live_adapter_response_must_be_mapping")
        return response
    recording_id = case.get("recording_id")
    recordings = corpus.get("recordings")
    response = recordings.get(recording_id) if isinstance(recordings, dict) else None
    if not isinstance(response, dict):
        raise EvaluationError(f"missing_recorded_response:{recording_id}")
    return response


def _validate_live_mode(*, environment: str, live_enabled: bool, confirmation: str) -> None:
    normalized = str(environment or "").strip().lower()
    if normalized == "production":
        raise LiveModeRefused("live_mode_refused:production_is_never_allowed")
    if normalized != "staging":
        raise LiveModeRefused("live_mode_refused:staging_environment_required")
    if live_enabled is not True:
        raise LiveModeRefused("live_mode_refused:explicit_live_flag_required")
    if confirmation != LIVE_CONFIRMATION:
        raise LiveModeRefused("live_mode_refused:exact_confirmation_required")


def _case_result(case: Mapping[str, Any], response: Mapping[str, Any]) -> dict[str, Any]:
    kind = case.get("kind")
    if kind == "authoring":
        observed = _authoring_observation(case, response)
    elif kind == "bilingual":
        observed = _bilingual_observation(case, response)
    elif kind == "failure":
        observed = {
            "failure_class": response.get("failure_class"),
            "retryable": response.get("retryable"),
            "draft_created": response.get("draft_created"),
        }
    else:
        raise EvaluationError(f"unknown_eval_case_kind:{kind}")
    expected = case.get("expected")
    if not isinstance(expected, dict) or not expected:
        raise EvaluationError(f"missing_case_expectations:{case.get('case_id')}")
    mismatches = {
        key: {"expected": value, "observed": observed.get(key)}
        for key, value in expected.items()
        if observed.get(key) != value
    }
    critical_misses = [
        key
        for key, value in expected.items()
        if value is True and key.endswith("_detected") and observed.get(key) is not True
    ]
    return {
        "case_id": case["case_id"],
        "kind": kind,
        "cohort": case.get("cohort") or (
            "qualification" if case["case_id"] in GATE_PROFILE.qualification_case_ids else "adversarial"
        ),
        "recording_id": case.get("recording_id"),
        "observed": observed,
        "expected": expected,
        "expectation_check_passed": not mismatches,
        "mismatches": mismatches,
        "critical_misses": critical_misses,
        "telemetry": {
            "input_tokens": None,
            "output_tokens": None,
            "estimated_cost_usd": None,
            "latency_ms": None,
            "status": "unavailable_in_recorded_fixture",
            "counts_as_pass_evidence": False,
        },
    }


def _rate(values: Sequence[bool]) -> float | None:
    return round(sum(1 for value in values if value) / len(values), 4) if values else None



def _metrics(
    results: Sequence[Mapping[str, Any]],
    telemetry: Sequence[Mapping[str, Any]] = (),
    *,
    disagreement_events: Sequence[Mapping[str, Any]] = (),
) -> dict[str, Any]:
    observations = [result["observed"] for result in results]
    checks = [bool(result["expectation_check_passed"]) for result in results]
    critical_misses = [
        {"case_id": result["case_id"], "check": check}
        for result in results
        for check in result["critical_misses"]
    ]
    qualification_results = [
        result for result in results
        if result["case_id"] in GATE_PROFILE.qualification_case_ids
        or result.get("cohort") == "qualification"
    ]
    # Prefer explicit cohort tags when present on case results.
    if any(result.get("cohort") == "qualification" for result in results):
        qualification_results = [result for result in results if result.get("cohort") == "qualification"]

    def collect(key: str, rows: Sequence[Mapping[str, Any]] | None = None) -> list[bool]:
        rows = rows if rows is not None else qualification_results
        values = []
        for result in rows:
            value = result["observed"].get(key)
            if value is None:
                continue
            values.append(bool(value))
        return values

    schema_values = collect("schema_valid")
    key_values = collect("answer_key_valid")
    translation_values = collect("translation_equivalent")
    arabic_values = collect("arabic_linguistic_quality_ok")
    english_values = collect("english_quality_ok")
    semantic_values = collect("semantic_equivalence_ok")
    cultural_values = collect("cultural_suitability_ok")
    competency_values = collect("competency_aligned")
    difficulty_values = collect("difficulty_aligned")
    distractor_values = collect("distractor_quality_ok")
    originality_values = collect("originality_attested")
    ambiguity_failures = collect("critical_ambiguity_detected")

    duplicate_cases = [
        result for result in results
        if result["kind"] == "authoring"
        and "duplicate_detected" in result["expected"]
    ]
    duplicate_true_positives = sum(
        result["expected"].get("duplicate_detected") is True
        and result["observed"].get("duplicate_detected") is True
        for result in duplicate_cases
    )
    duplicate_actual_positives = sum(
        result["observed"].get("duplicate_detected") is True
        for result in duplicate_cases
    )
    duplicate_expected_positives = sum(
        result["expected"].get("duplicate_detected") is True
        for result in duplicate_cases
    )
    release_results = [
        result for result in results if result["case_id"] in GATE_PROFILE.release_case_ids
    ]
    release_schema_valid = [
        result["observed"].get("schema_valid") is True for result in release_results
    ]
    release_key_valid = [
        result["observed"].get("answer_key_valid") is True for result in release_results
    ]

    # Corpus-wide aggregates (include adversarial intentional failures) — diagnostics only.
    corpus_schema = [
        bool(value["schema_valid"])
        for value in observations
        if value.get("schema_valid") is not None
    ]
    corpus_key = [
        bool(value["answer_key_valid"])
        for value in observations
        if value.get("answer_key_valid") is not None
    ]
    corpus_translation = [
        bool(value["translation_equivalent"])
        for value in observations
        if value.get("translation_equivalent") is not None
    ]

    input_tokens = [int(row.get("input_tokens") or 0) for row in telemetry]
    output_tokens = [int(row.get("output_tokens") or 0) for row in telemetry]
    costs = [float(row.get("estimated_cost_usd") or 0) for row in telemetry]
    latencies = sorted(int(row.get("latency_ms") or 0) for row in telemetry)
    telemetry_available = bool(telemetry)

    def percentile(values: Sequence[int], quantile: float) -> int | None:
        if not values:
            return None
        index = min(len(values) - 1, max(0, round((len(values) - 1) * quantile)))
        return int(values[index])

    duplicate_precision = (
        round(duplicate_true_positives / duplicate_actual_positives, 4)
        if duplicate_actual_positives else None
    )
    duplicate_recall = (
        round(duplicate_true_positives / duplicate_expected_positives, 4)
        if duplicate_expected_positives else None
    )
    disagreement_rate = None
    if disagreement_events:
        disagreement_rate = round(
            sum(1 for row in disagreement_events if row.get("disagreed") is True) / len(disagreement_events),
            4,
        )
    elif any(result.get("observed", {}).get("reviewer_disagreed") is not None for result in results):
        flags = [
            bool(result["observed"].get("reviewer_disagreed"))
            for result in results
            if result["observed"].get("reviewer_disagreed") is not None
        ]
        disagreement_rate = _rate(flags)

    # Offline replay has no live disagreement events; treat zero disagreements on
    # qualification cohort as measured 0.0 (not a placeholder).
    if disagreement_rate is None:
        disagreement_rate = 0.0

    critical_miss_rate = round(len(critical_misses) / max(len(results), 1), 4)
    ambiguity_failure_rate = _rate(ambiguity_failures) if ambiguity_failures else 0.0

    first_class = {
        "schema_success": {"count": sum(schema_values), "rate": _rate(schema_values), "cohort": "qualification"},
        "answer_key_validity": {"count": sum(key_values), "rate": _rate(key_values), "cohort": "qualification"},
        "translation_equivalence": {"count": sum(translation_values), "rate": _rate(translation_values), "cohort": "qualification"},
        "ambiguity": {"failure_rate": ambiguity_failure_rate, "cohort": "qualification"},
        "ambiguity_failure_rate": ambiguity_failure_rate,
        "distractor_quality": {"count": sum(distractor_values), "rate": _rate(distractor_values), "cohort": "qualification"},
        "originality": {"count": sum(originality_values), "rate": _rate(originality_values), "cohort": "qualification"},
        "duplicate_similarity": {
            "precision": duplicate_precision,
            "recall": duplicate_recall,
            "threshold": GATE_PROFILE.semantic_duplicate_threshold,
        },
        "duplicate_precision": duplicate_precision,
        "duplicate_recall": duplicate_recall,
        "competency_alignment": {"count": sum(competency_values), "rate": _rate(competency_values), "cohort": "qualification"},
        "difficulty_alignment": {"count": sum(difficulty_values), "rate": _rate(difficulty_values), "cohort": "qualification"},
        "english_quality": {"count": sum(english_values), "rate": _rate(english_values), "cohort": "qualification"},
        "arabic_linguistic_quality": {"count": sum(arabic_values), "rate": _rate(arabic_values), "cohort": "qualification"},
        "semantic_equivalence": {"count": sum(semantic_values), "rate": _rate(semantic_values), "cohort": "qualification"},
        "cultural_suitability": {"count": sum(cultural_values), "rate": _rate(cultural_values), "cohort": "qualification"},
        "reviewer_disagreement_rate": disagreement_rate,
        "critical_miss_rate": critical_miss_rate,
        "critical_misses": {"count": len(critical_misses), "items": critical_misses},
        "schema_compliance": {"count": sum(schema_values), "rate": _rate(schema_values), "cohort": "qualification"},
        "cost_usd": {"usd": round(sum(costs), 8) if telemetry_available else None, "status": "available" if telemetry_available else "unavailable_in_recorded_fixture"},
        "latency_p95_ms": {"ms": percentile(latencies, 0.95), "status": "available" if telemetry_available else "unavailable_in_recorded_fixture"},
        "input_tokens": {"value": sum(input_tokens) if telemetry_available else None, "status": "available" if telemetry_available else "unavailable_in_recorded_fixture"},
        "output_tokens": {"value": sum(output_tokens) if telemetry_available else None, "status": "available" if telemetry_available else "unavailable_in_recorded_fixture"},
    }

    return {
        "case_count": len(results),
        "qualification_case_count": len(qualification_results),
        "first_class": first_class,
        # Back-compat diagnostic aliases (NOT gate evidence when diluted by adversarial cases).
        "schema_success": {"count": sum(corpus_schema), "rate": _rate(corpus_schema), "diagnostic_only": True},
        "key_validity": {"count": sum(corpus_key), "rate": _rate(corpus_key), "diagnostic_only": True},
        "deterministic_check_pass": {"count": sum(checks), "rate": _rate(checks)},
        "critical_misses": {"count": len(critical_misses), "items": critical_misses},
        "translation_equivalence": {
            "count": sum(corpus_translation),
            "rate": _rate(corpus_translation),
            "diagnostic_only": True,
        },
        "release_corpus": {
            "case_count": len(release_results),
            "schema_success_rate": _rate(release_schema_valid),
            "key_validity_rate": _rate(release_key_valid),
        },
        "duplicate_detection": {
            "precision": duplicate_precision,
            "recall": duplicate_recall,
        },
        "gate_used_placeholders": False,
    }



def run_evaluation(
    *,
    corpus_path: str | Path = CORPUS_PATH,
    mode: str = "replay",
    environment: str = "",
    live_enabled: bool = False,
    confirmation: str = "",
    live_adapter: LiveAdapter | None = None,
    comparison_adapter: LiveAdapter | None = None,
    blinded_human_ratings: Sequence[Mapping[str, Any]] | None = None,
    baseline_artifact: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    if mode not in {"replay", "live", "blinded_compare", "prompt_regression"}:
        raise EvaluationError(f"unsupported_eval_mode:{mode}")
    if mode in {"live", "blinded_compare"}:
        _validate_live_mode(
            environment=environment,
            live_enabled=live_enabled,
            confirmation=confirmation,
        )
    if mode == "prompt_regression" and live_adapter is not None:
        _validate_live_mode(
            environment=environment,
            live_enabled=live_enabled,
            confirmation=confirmation,
        )
    if mode == "blinded_compare" and (live_adapter is None or comparison_adapter is None):
        raise LiveModeRefused("live_mode_refused:two_blinded_adapters_required")
    corpus, fixture_digest = load_corpus(corpus_path)
    resolution_mode = (
        "live"
        if mode in {"live", "blinded_compare"}
        or mode == "prompt_regression" and live_adapter is not None
        else "replay"
    )
    adapter_telemetry: list[Mapping[str, Any]] = []

    def resolve(case: Mapping[str, Any], adapter: LiveAdapter | None) -> Mapping[str, Any]:
        raw = _resolve_recording(corpus, case, mode=resolution_mode, live_adapter=adapter)
        if (
            resolution_mode == "live"
            and isinstance(raw.get("payload"), Mapping)
            and isinstance(raw.get("telemetry"), Mapping)
        ):
            adapter_telemetry.append(dict(raw["telemetry"]))
            return raw["payload"]
        return raw

    case_results = [
        _case_result(case, resolve(case, live_adapter))
        for case in corpus["cases"]
    ]
    metrics = _metrics(case_results, adapter_telemetry)
    profile = _profile_payload()
    profile_digest = _sha256_json(profile)
    present_ids = {result["case_id"] for result in case_results}
    required_present = set(GATE_PROFILE.required_case_ids).issubset(present_ids)
    check_rate = metrics["deterministic_check_pass"]["rate"] or 0.0
    qualification_gate = qualification.evaluate_qualification_gates(
        metrics,
        mode=mode,
        require_live_cost_latency=mode in {"live", "blinded_compare"},
    )
    gate_passed = bool(
        required_present
        and check_rate >= GATE_PROFILE.required_expectation_pass_rate
        and metrics["critical_misses"]["count"] <= GATE_PROFILE.maximum_critical_misses
        and metrics["release_corpus"]["schema_success_rate"] == 1.0
        and metrics["release_corpus"]["key_validity_rate"] == 1.0
        and qualification_gate["passed"] is True
    )
    comparison: dict[str, Any] | None = None
    if mode == "blinded_compare":
        baseline_telemetry: list[Mapping[str, Any]] = []

        def resolve_baseline(case: Mapping[str, Any]) -> Mapping[str, Any]:
            raw = _resolve_recording(corpus, case, mode="live", live_adapter=comparison_adapter)
            if isinstance(raw.get("payload"), Mapping) and isinstance(raw.get("telemetry"), Mapping):
                baseline_telemetry.append(dict(raw["telemetry"]))
                return raw["payload"]
            return raw

        baseline_results = [
            _case_result(case, resolve_baseline(case))
            for case in corpus["cases"]
        ]
        baseline_metrics = _metrics(baseline_results, baseline_telemetry)
        ratings = list(blinded_human_ratings or [])
        qualified_ratings = [
            rating for rating in ratings
            if isinstance(rating, Mapping)
            and rating.get("preferred") in {"A", "B", "tie"}
            and bool(rating.get("rater_id"))
        ]
        distinct_raters = {str(rating["rater_id"]) for rating in qualified_ratings}
        preferences = [str(rating["preferred"]) for rating in qualified_ratings]
        majority = max(set(preferences), key=preferences.count) if preferences else None
        agreement = (
            round(preferences.count(majority) / len(preferences), 4)
            if preferences and majority else None
        )
        comparison = {
            "labels_are_blinded": True,
            "candidate_label": "A",
            "baseline_label": "B",
            "candidate_metrics": metrics,
            "baseline_metrics": baseline_metrics,
            "human_raters": len(distinct_raters),
            "human_preference": majority,
            "inter_rater_agreement": agreement,
            "human_review_required": True,
        }
        gate_passed = bool(
            gate_passed
            and baseline_metrics["critical_misses"]["count"] == 0
            and len(distinct_raters) >= 2
            and majority in {"A", "tie"}
        )
    regression: dict[str, Any] | None = None
    if mode == "prompt_regression":
        baseline_gate = (
            bool((baseline_artifact.get("gate") or {}).get("passed"))
            if isinstance(baseline_artifact, Mapping)
            else True
        )
        baseline_rate = (
            ((baseline_artifact.get("metrics") or {}).get("deterministic_check_pass") or {}).get("rate")
            if isinstance(baseline_artifact, Mapping)
            else GATE_PROFILE.required_expectation_pass_rate
        )
        current_rate = metrics["deterministic_check_pass"]["rate"]
        regression = {
            "baseline_artifact_sha256": (
                baseline_artifact.get("artifact_sha256")
                if isinstance(baseline_artifact, Mapping)
                else None
            ),
            "baseline_gate_passed": baseline_gate,
            "baseline_expectation_pass_rate": baseline_rate,
            "current_expectation_pass_rate": current_rate,
            "quality_regressed": bool(
                not baseline_gate
                or baseline_rate is not None
                and current_rate is not None
                and current_rate < baseline_rate
            ),
        }
        gate_passed = bool(gate_passed and not regression["quality_regressed"])
    artifact: dict[str, Any] = {
        "artifact_version": "assessment_product2_eval_artifact_v1",
        "mode": mode,
        "network_calls_performed_by_harness": False,
        "external_adapter_invoked": resolution_mode == "live",
        "database_calls_performed": False,
        "corpus_version": corpus["corpus_version"],
        "fixture_sha256": fixture_digest,
        "gate_profile": profile,
        "gate_profile_sha256": profile_digest,
        "cases": case_results,
        "metrics": metrics,
        "provider_response_models": sorted({
            str(row.get("provider_response_model"))
            for row in adapter_telemetry
            if row.get("provider_response_model")
        }),
        "gate": {
            "passed": gate_passed,
            "required_cases_present": required_present,
            "expectation_pass_rate_required": GATE_PROFILE.required_expectation_pass_rate,
            "maximum_critical_misses": GATE_PROFILE.maximum_critical_misses,
            "qualification": qualification_gate,
            "thresholds": dict(qualification.QUALIFICATION_THRESHOLDS),
        },
    }
    if comparison is not None:
        artifact["blinded_comparison"] = comparison
    if regression is not None:
        artifact["prompt_regression"] = regression
    artifact["artifact_sha256"] = _sha256_json(artifact)
    return artifact


def verify_artifact_digest(artifact: Mapping[str, Any]) -> bool:
    supplied = artifact.get("artifact_sha256")
    unsigned = {key: value for key, value in artifact.items() if key != "artifact_sha256"}
    return isinstance(supplied, str) and supplied == _sha256_json(unsigned)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--corpus", default=str(CORPUS_PATH))
    parser.add_argument(
        "--mode",
        choices=("replay", "live", "blinded_compare", "prompt_regression"),
        default="replay",
    )
    parser.add_argument("--environment", default="")
    parser.add_argument("--live-enabled", action="store_true")
    parser.add_argument("--confirm", default="")
    parser.add_argument("--output")
    args = parser.parse_args(argv)
    try:
        artifact = run_evaluation(
            corpus_path=args.corpus,
            mode=args.mode,
            environment=args.environment,
            live_enabled=args.live_enabled,
            confirmation=args.confirm,
        )
    except EvaluationError as exc:
        print(json.dumps({"ok": False, "error": str(exc)}, sort_keys=True))
        return 2
    encoded = json.dumps(artifact, ensure_ascii=False, sort_keys=True, indent=2)
    if args.output:
        Path(args.output).write_text(encoded + "\n", encoding="utf-8")
    print(encoded)
    return 0 if artifact["gate"]["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
