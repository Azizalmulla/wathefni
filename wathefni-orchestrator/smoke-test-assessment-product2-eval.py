"""DB-free smoke tests for the Assessment Product-2 offline eval harness."""

from __future__ import annotations

import json
import urllib.request
from dataclasses import FrozenInstanceError
from typing import Any, Callable
from unittest import mock

import assessment_ai_eval as evaluation
import assessment_ai_qualification as qualification


class Checks:
    def __init__(self) -> None:
        self.passed: list[str] = []
        self.failed: list[str] = []

    def check(self, label: str, value: bool | Callable[[], bool]) -> None:
        try:
            ok = bool(value() if callable(value) else value)
        except Exception as exc:
            self.failed.append(f"{label}: {type(exc).__name__}: {exc}")
            return
        (self.passed if ok else self.failed).append(label)

    def report(self) -> int:
        payload = {
            "suite": "assessment_product2_eval",
            "passed": len(self.passed),
            "failed": len(self.failed),
            "checks": {"passed": self.passed, "failed": self.failed},
            "database_used": False,
            "network_used": False,
            "production_touched": False,
        }
        print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
        return 1 if self.failed else 0


def refuses_live(**kwargs: Any) -> str:
    try:
        evaluation.run_evaluation(mode="live", **kwargs)
    except evaluation.LiveModeRefused as exc:
        return str(exc)
    return ""


def main() -> int:
    checks = Checks()
    network_attempts: list[str] = []

    def reject_network(*args: Any, **kwargs: Any) -> Any:
        network_attempts.append("attempted")
        raise AssertionError("network access is forbidden in replay smoke tests")

    with mock.patch.object(urllib.request, "urlopen", side_effect=reject_network):
        replay = evaluation.run_evaluation()
        replay_again = evaluation.run_evaluation()

    fc = replay["metrics"]["first_class"]
    checks.check("replay gate passes", replay["gate"]["passed"] is True)
    checks.check("qualification gate passes", replay["gate"]["qualification"]["passed"] is True)
    checks.check("all adversarial expectations pass", replay["metrics"]["deterministic_check_pass"]["rate"] == 1.0)
    checks.check("critical misses are zero", replay["metrics"]["critical_misses"]["count"] == 0)
    checks.check("first-class schema success meets threshold", (fc["schema_success"]["rate"] or 0) >= 0.98)
    checks.check("first-class answer-key validity meets threshold", (fc["answer_key_validity"]["rate"] or 0) >= 0.95)
    checks.check("first-class translation equivalence meets threshold", (fc["translation_equivalence"]["rate"] or 0) >= 0.90)
    checks.check("first-class Arabic quality meets threshold", (fc["arabic_linguistic_quality"]["rate"] or 0) >= 0.90)
    checks.check("first-class English quality meets threshold", (fc["english_quality"]["rate"] or 0) >= 0.90)
    checks.check("first-class distractor quality meets threshold", (fc["distractor_quality"]["rate"] or 0) >= 0.90)
    checks.check("first-class originality meets threshold", (fc["originality"]["rate"] or 0) >= 0.95)
    checks.check("first-class duplicate precision/recall meet threshold", (fc["duplicate_precision"] or 0) >= 0.95 and (fc["duplicate_recall"] or 0) >= 0.95)
    checks.check("placeholders are not pass evidence", replay["metrics"].get("gate_used_placeholders") is False)
    checks.check("cost is unavailable in replay and not treated as pass", fc["cost_usd"]["usd"] is None and fc["cost_usd"]["status"] == "unavailable_in_recorded_fixture")
    checks.check("artifact digest verifies", evaluation.verify_artifact_digest(replay))
    checks.check("artifact is reproducible", replay["artifact_sha256"] == replay_again["artifact_sha256"])
    checks.check("replay performs no network calls", not network_attempts and replay["network_calls_performed_by_harness"] is False)
    checks.check("replay performs no database calls", replay["database_calls_performed"] is False)
    checks.check("fixture digest is pinned", len(replay["fixture_sha256"]) == 64)
    checks.check("gate profile digest is pinned", len(replay["gate_profile_sha256"]) == 64)
    checks.check("corpus is v2", replay["corpus_version"] == qualification.CORPUS_VERSION)
    checks.check("gate profile is v2", replay["gate_profile"]["version"] == qualification.GATE_PROFILE_VERSION)

    by_id = {case["case_id"]: case for case in replay["cases"]}
    checks.check("exact duplicate detected", by_id["exact_duplicate"]["observed"]["exact_duplicate_detected"] is True)
    checks.check("semantic duplicate detected", by_id["semantic_duplicate"]["observed"]["semantic_duplicate_detected"] is True)
    checks.check("ambiguity detected", by_id["critical_ambiguity"]["observed"]["critical_ambiguity_detected"] is True)
    checks.check("bias detected", by_id["critical_bias"]["observed"]["critical_bias_detected"] is True)
    checks.check("leakage detected", by_id["critical_leakage"]["observed"]["critical_leakage_detected"] is True)
    checks.check("invalid scoring rejected", by_id["scoring_compile_failure"]["observed"]["scoring_compile_valid"] is False)
    checks.check("invalid answer key rejected", by_id["invalid_answer_key"]["observed"]["answer_key_valid"] is False)
    checks.check("EN/AR key invariance accepted", by_id["bilingual_equivalent"]["observed"]["en_ar_key_invariant"] is True)
    checks.check("EN/AR key drift rejected", by_id["bilingual_key_drift"]["observed"]["en_ar_key_invariant"] is False)
    checks.check("Arabic-first quality measured", by_id["valid_authoring_ar"]["observed"]["arabic_linguistic_quality_ok"] is True)
    checks.check("structured refusal creates no draft", by_id["structured_refusal"]["observed"]["draft_created"] is False)
    checks.check("rate limit remains retryable", by_id["provider_rate_limit"]["observed"]["retryable"] is True)
    checks.check("provider outage remains retryable", by_id["provider_outage"]["observed"]["retryable"] is True)

    weak = {
        "first_class": {
            "schema_success": {"rate": 0.5},
            "answer_key_validity": {"rate": 0.5},
            "translation_equivalence": {"rate": 0.5},
            "duplicate_precision": 0.5,
            "duplicate_recall": 0.5,
            "arabic_linguistic_quality": {"rate": 0.5},
            "english_quality": {"rate": 0.5},
            "semantic_equivalence": {"rate": 0.5},
            "cultural_suitability": {"rate": 0.5},
            "competency_alignment": {"rate": 0.5},
            "difficulty_alignment": {"rate": 0.5},
            "distractor_quality": {"rate": 0.5},
            "originality": {"rate": 0.5},
            "ambiguity_failure_rate": 0.5,
            "critical_miss_rate": 0.1,
            "reviewer_disagreement_rate": 0.5,
        }
    }
    weak_gate = qualification.evaluate_qualification_gates(weak, mode="replay")
    checks.check("weak metrics fail qualification gate", weak_gate["passed"] is False and bool(weak_gate["failures"]))

    arabic_ok, arabic_missing = qualification.arabic_human_review_complete(
        {
            "decision": "approve",
            "natural_professional_arabic": True,
            "no_literal_machine_translation": True,
            "gulf_kuwait_cultural_suitability": True,
            "same_construct_and_difficulty": True,
            "answer_key_equivalence": True,
            "no_language_specific_clueing": True,
        }
    )
    checks.check("Arabic human checklist accepts complete approval", arabic_ok and not arabic_missing)
    arabic_bad, _ = qualification.arabic_human_review_complete({"decision": "approve", "natural_professional_arabic": True})
    checks.check("Arabic human checklist rejects incomplete approval", arabic_bad is False)

    def profile_is_frozen() -> bool:
        try:
            evaluation.GATE_PROFILE.version = "mutated"  # type: ignore[misc]
        except FrozenInstanceError:
            return True
        return False

    checks.check("gate profile is immutable", profile_is_frozen)
    checks.check(
        "production live mode is explicitly refused",
        "production_is_never_allowed" in refuses_live(environment="production", live_enabled=True, confirmation=evaluation.LIVE_CONFIRMATION),
    )
    checks.check(
        "live mode requires staging",
        "staging_environment_required" in refuses_live(environment="dev", live_enabled=True, confirmation=evaluation.LIVE_CONFIRMATION),
    )
    checks.check(
        "live mode requires explicit flag",
        "explicit_live_flag_required" in refuses_live(environment="staging", live_enabled=False, confirmation=evaluation.LIVE_CONFIRMATION),
    )
    checks.check(
        "live mode requires exact confirmation",
        "exact_confirmation_required" in refuses_live(environment="staging", live_enabled=True, confirmation="nope"),
    )

    def live_adapter(case: dict[str, Any]) -> dict[str, Any]:
        recording_id = case["recording_id"]
        corpus, _ = evaluation.load_corpus()
        payload = corpus["recordings"][recording_id]
        return {
            "payload": payload,
            "telemetry": {
                "input_tokens": 100,
                "output_tokens": 50,
                "estimated_cost_usd": 0.01,
                "latency_ms": 200,
                "provider_response_model": "gpt-5.4-staging-qualified",
                "status": "ok",
            },
        }

    live = evaluation.run_evaluation(
        mode="live",
        environment="staging",
        live_enabled=True,
        confirmation=evaluation.LIVE_CONFIRMATION,
        live_adapter=live_adapter,
    )
    checks.check("guarded live with recorded adapter passes", live["gate"]["passed"] is True)
    checks.check("live cost is recorded as first-class evidence", live["metrics"]["first_class"]["cost_usd"]["usd"] is not None)

    return checks.report()


if __name__ == "__main__":
    raise SystemExit(main())
