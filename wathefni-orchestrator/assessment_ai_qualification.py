"""Product-2 qualification thresholds and gate evaluation.

Gates are first-class evidence. Placeholder / unavailable metrics never count
as passed evidence. Failed gates block model-role activation and block draft
progression beyond ai_draft.
"""

from __future__ import annotations

from typing import Any, Mapping, Sequence

GATE_PROFILE_VERSION = "assessment_product2_offline_gate_v2"
CORPUS_VERSION = "assessment_product2_eval_corpus_v2"

# Minimum qualification thresholds (owner-approved staging bar).
QUALIFICATION_THRESHOLDS: dict[str, float] = {
    "schema_success": 0.98,
    "answer_key_validity": 0.95,
    "translation_equivalence": 0.90,
    "duplicate_precision": 0.95,
    "duplicate_recall": 0.95,
    "arabic_linguistic_quality": 0.90,
    "english_quality": 0.90,
    "semantic_equivalence": 0.90,
    "cultural_suitability": 0.95,
    "competency_alignment": 0.90,
    "difficulty_alignment": 0.90,
    "distractor_quality": 0.90,
    "originality": 0.95,
    "ambiguity_failure_rate_max": 0.05,
    "reviewer_disagreement_rate_max": 0.25,
    "critical_miss_rate_max": 0.0,
}

# Live-only caps (replay leaves these unavailable — not pass evidence).
LIVE_COST_LATENCY_CAPS: dict[str, float] = {
    "max_estimated_cost_usd": 5.0,
    "max_latency_p95_ms": 45000.0,
    "max_total_input_tokens": 120000.0,
    "max_total_output_tokens": 60000.0,
}

ARABIC_HUMAN_REVIEW_CHECKLIST: tuple[str, ...] = (
    "natural_professional_arabic",
    "no_literal_machine_translation",
    "gulf_kuwait_cultural_suitability",
    "same_construct_and_difficulty",
    "answer_key_equivalence",
    "no_language_specific_clueing",
)

# Metrics that are required for offline/replay qualification evidence.
REPLAY_REQUIRED_METRICS: tuple[str, ...] = (
    "schema_success",
    "answer_key_validity",
    "translation_equivalence",
    "duplicate_precision",
    "duplicate_recall",
    "arabic_linguistic_quality",
    "english_quality",
    "semantic_equivalence",
    "cultural_suitability",
    "competency_alignment",
    "difficulty_alignment",
    "distractor_quality",
    "originality",
    "ambiguity_failure_rate",
    "critical_miss_rate",
    "reviewer_disagreement_rate",
)

LIVE_REQUIRED_METRICS: tuple[str, ...] = REPLAY_REQUIRED_METRICS + (
    "cost_usd",
    "latency_p95_ms",
    "input_tokens",
    "output_tokens",
)


def _metric_value(first_class: Mapping[str, Any], key: str) -> Any:
    node = first_class.get(key)
    if isinstance(node, Mapping):
        if "rate" in node:
            return node.get("rate")
        if "value" in node:
            return node.get("value")
        if "usd" in node:
            return node.get("usd")
        if "ms" in node:
            return node.get("ms")
        if "count" in node and key.endswith("_count"):
            return node.get("count")
    return node


def evaluate_qualification_gates(
    metrics: Mapping[str, Any],
    *,
    mode: str,
    require_live_cost_latency: bool | None = None,
) -> dict[str, Any]:
    """Return gate result. Unavailable required metrics fail closed."""

    first_class = metrics.get("first_class") if isinstance(metrics.get("first_class"), Mapping) else {}
    if not first_class:
        return {
            "passed": False,
            "failures": ["first_class_metrics_missing"],
            "mode": mode,
            "thresholds": dict(QUALIFICATION_THRESHOLDS),
        }

    live_required = require_live_cost_latency
    if live_required is None:
        live_required = mode in {"live", "live_staging", "blinded_compare"}

    required = LIVE_REQUIRED_METRICS if live_required else REPLAY_REQUIRED_METRICS
    failures: list[str] = []

    def require_min(name: str, threshold_key: str) -> None:
        value = _metric_value(first_class, name)
        threshold = QUALIFICATION_THRESHOLDS[threshold_key]
        if value is None:
            failures.append(f"{name}:unavailable_not_pass_evidence")
            return
        if float(value) < float(threshold):
            failures.append(f"{name}:{value}<{threshold}")

    def require_max(name: str, threshold_key: str) -> None:
        value = _metric_value(first_class, name)
        threshold = QUALIFICATION_THRESHOLDS[threshold_key]
        if value is None:
            failures.append(f"{name}:unavailable_not_pass_evidence")
            return
        if float(value) > float(threshold):
            failures.append(f"{name}:{value}>{threshold}")

    for name in required:
        if name not in first_class:
            failures.append(f"{name}:missing")

    require_min("schema_success", "schema_success")
    require_min("answer_key_validity", "answer_key_validity")
    require_min("translation_equivalence", "translation_equivalence")
    require_min("duplicate_precision", "duplicate_precision")
    require_min("duplicate_recall", "duplicate_recall")
    require_min("arabic_linguistic_quality", "arabic_linguistic_quality")
    require_min("english_quality", "english_quality")
    require_min("semantic_equivalence", "semantic_equivalence")
    require_min("cultural_suitability", "cultural_suitability")
    require_min("competency_alignment", "competency_alignment")
    require_min("difficulty_alignment", "difficulty_alignment")
    require_min("distractor_quality", "distractor_quality")
    require_min("originality", "originality")
    require_max("ambiguity_failure_rate", "ambiguity_failure_rate_max")
    require_max("critical_miss_rate", "critical_miss_rate_max")
    require_max("reviewer_disagreement_rate", "reviewer_disagreement_rate_max")

    if live_required:
        cost = _metric_value(first_class, "cost_usd")
        latency = _metric_value(first_class, "latency_p95_ms")
        in_tok = _metric_value(first_class, "input_tokens")
        out_tok = _metric_value(first_class, "output_tokens")
        if cost is None:
            failures.append("cost_usd:unavailable_not_pass_evidence")
        elif float(cost) > LIVE_COST_LATENCY_CAPS["max_estimated_cost_usd"]:
            failures.append(f"cost_usd:{cost}>{LIVE_COST_LATENCY_CAPS['max_estimated_cost_usd']}")
        if latency is None:
            failures.append("latency_p95_ms:unavailable_not_pass_evidence")
        elif float(latency) > LIVE_COST_LATENCY_CAPS["max_latency_p95_ms"]:
            failures.append(f"latency_p95_ms:{latency}>{LIVE_COST_LATENCY_CAPS['max_latency_p95_ms']}")
        if in_tok is None:
            failures.append("input_tokens:unavailable_not_pass_evidence")
        elif float(in_tok) > LIVE_COST_LATENCY_CAPS["max_total_input_tokens"]:
            failures.append(f"input_tokens:{in_tok}>{LIVE_COST_LATENCY_CAPS['max_total_input_tokens']}")
        if out_tok is None:
            failures.append("output_tokens:unavailable_not_pass_evidence")
        elif float(out_tok) > LIVE_COST_LATENCY_CAPS["max_total_output_tokens"]:
            failures.append(f"output_tokens:{out_tok}>{LIVE_COST_LATENCY_CAPS['max_total_output_tokens']}")

    # Placeholder bags are never pass evidence.
    for banned in ("quality_placeholders", "latency_cost_placeholders", "usage_placeholders"):
        bag = metrics.get(banned)
        if isinstance(bag, Mapping) and any(v is not None for v in bag.values() if not isinstance(v, str)):
            # Presence is allowed for diagnostics, but if gates relied on them we fail.
            pass
        if metrics.get("gate_used_placeholders") is True:
            failures.append(f"{banned}:placeholder_used_as_evidence")

    return {
        "passed": not failures,
        "failures": failures,
        "mode": mode,
        "thresholds": dict(QUALIFICATION_THRESHOLDS),
        "live_caps": dict(LIVE_COST_LATENCY_CAPS) if live_required else None,
        "required_metrics": list(required),
    }


def arabic_human_review_complete(payload: Mapping[str, Any] | None) -> tuple[bool, list[str]]:
    """Arabic approval requires an explicit human checklist — AI pass is insufficient."""

    if not isinstance(payload, Mapping):
        return False, ["arabic_human_review_missing"]
    missing = [key for key in ARABIC_HUMAN_REVIEW_CHECKLIST if payload.get(key) is not True]
    if payload.get("approved") is not True and payload.get("decision") not in {"approve", "approved"}:
        missing.append("arabic_human_decision_not_approve")
    return not missing, missing


def item_progression_gate(
    *,
    deterministic: Mapping[str, Any] | None,
    secondary: Mapping[str, Any] | None,
    locale: str | None = None,
    arabic_human_review: Mapping[str, Any] | None = None,
    qualification_gate: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Block progression beyond ai_draft unless item + model qualification gates pass."""

    failures: list[str] = []
    deterministic = deterministic if isinstance(deterministic, Mapping) else {}
    secondary = secondary if isinstance(secondary, Mapping) else {}
    if deterministic.get("passed") is not True:
        failures.append("deterministic_review_not_passed")
    if secondary.get("passed") is not True:
        failures.append("secondary_review_not_passed")
    if qualification_gate is not None and qualification_gate.get("passed") is not True:
        failures.append("model_qualification_gate_failed")
        failures.extend(list(qualification_gate.get("failures") or [])[:20])
    if str(locale or "").lower().startswith("ar"):
        ok, missing = arabic_human_review_complete(arabic_human_review)
        if not ok:
            failures.append("arabic_human_review_required")
            failures.extend(missing)
    return {"passed": not failures, "failures": failures}
