"""Model-agnostic authoring services for Wathefni Assessment Product-2.

This module is intentionally absent from candidate runtime paths.  It can
append blueprints, model/prompt registry versions, AI runs, draft revisions,
reviews, and translation pairs.  It has no functions that publish items,
score candidates, activate norms, or mutate recruiting decisions.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
import time
import urllib.error
import urllib.request
import uuid
from dataclasses import dataclass
from typing import Any, Callable

from psycopg2.extras import Json

import assessment_ai_contracts as contracts
import assessment_ai_qualification as qual_gates
import assessment_lifecycle as lifecycle


PRODUCT_VERSION = "assessment_product2_v1"
ORIGINALITY_POLICY_VERSION = "wathefni_originality_v1"
RUBRIC_VERSION = "wathefni_item_review_v1"
DEFAULT_PRIMARY_MODEL = "gpt-5.4"
DEFAULT_SECONDARY_MODEL = "gpt-5.4-mini"
RUN_KINDS = {
    "assessment.author_primary": "author_primary",
    "assessment.review_secondary": "review_secondary",
    "assessment.adapt_bilingual": "adapt_bilingual",
    "assessment.review_bilingual": "review_bilingual",
    "assessment.eval_judge": "eval_judge",
}
ROLE_SCHEMAS = {
    "assessment.author_primary": "GeneratedItemPackageV1",
    "assessment.review_secondary": "AssessmentReviewResultV1",
    "assessment.adapt_bilingual": "BilingualAdaptationV1",
    "assessment.review_bilingual": "BilingualReviewResultV1",
    "assessment.eval_judge": "OfflineEvalResultV1",
}
ROLE_PROMPTS = {
    "assessment.author_primary": """You author original OctoHR assessment draft items from the supplied approved blueprint only.
Never imitate or quote SHL or any third-party test. Never use candidate data. Return only the strict schema.
Propose an answer key and a closed deterministic scoring family, but never publish, score a candidate, set a norm,
or make a recruiting decision. If the blueprint is unsafe or insufficient, return no items and a refusal_reason.""",
    "assessment.review_secondary": """You independently review one OctoHR draft item. Do not rewrite it.
Return evidence-only findings for all required dimensions. You have no authority to publish, change an answer key,
score candidates, select norms, or make recruiting decisions. Mark uncertainty as required_human_attention.""",
    "assessment.adapt_bilingual": """Adapt the supplied OctoHR item between English and Arabic while preserving meaning,
difficulty, option key IDs, and scoring invariants. Use clear MSA for scored Arabic unless the blueprint explicitly
requires Kuwaiti dialect. Do not return or alter an answer key. Return only the strict schema.""",
    "assessment.review_bilingual": """Independently review a linked English/Arabic assessment pair for semantic equivalence,
answer-key invariance, natural language, RTL/numerals, cultural fairness, and difficulty drift. Return findings only.""",
    "assessment.eval_judge": """Evaluate recorded assessment-authoring output against the supplied offline rubric.
This is advisory offline evidence only and cannot activate a model, publish an item, score a candidate, or make a decision.""",
}
FORBIDDEN_OUTPUT_KEYS = {
    "publish",
    "published",
    "publish_item",
    "activate_norm",
    "norm_percentiles",
    "candidate_score",
    "score_candidate",
    "hire",
    "reject_candidate",
    "shortlist_candidate",
    "candidate_decision",
    "application_status",
}
FORBIDDEN_AUTHORING_INPUT_KEYS = {
    "candidate",
    "candidate_name",
    "candidate_phone",
    "candidate_email",
    "cv",
    "application",
    "application_id",
    "app_key",
    "interview",
    "offer",
    "employee",
    "live_response",
    "candidate_response",
    "api_key",
    "access_token",
    "secret",
    "password",
}
_BIAS_PATTERNS = (
    r"\b(?:male|female|man|woman|young|old|nationality|religion|married|pregnant|race|passport|neighbou?rhood|accent)\b",
    r"(?:ذكر|أنثى|رجل|امرأة|شاب|مسن|الجنسية|الديانة|متزوج|حامل|جواز|المنطقة|اللهجة)",
)
_LEAKAGE_PATTERNS = (
    r"\b(?:the\s+)?(?:correct\s+)?answer\s+(?:is|:)\s*[A-Z0-9_]+\b",
    r"\bchoose\s+[A-Z]\b",
    r"(?:الإجابة\s+الصحيحة|اختر)\s*[:：]?\s*[A-Z0-9_]+",
    r"\bSHL\b",
)


class AssessmentAIError(RuntimeError):
    def __init__(self, code: str, message: str, *, status_code: int = 409, detail: dict[str, Any] | None = None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code
        self.detail = dict(detail or {})


@dataclass
class ProviderResult:
    payload: dict[str, Any] | None
    provider_response_model: str | None
    provider_request_id: str | None
    input_tokens: int | None
    output_tokens: int | None
    cached_tokens: int | None
    latency_ms: int
    refusal_reason: str | None = None


ProviderAdapter = Callable[[dict[str, Any], dict[str, Any], dict[str, Any]], ProviderResult]


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


def sha256_json(value: Any) -> str:
    return hashlib.sha256(canonical_json(value).encode("utf-8")).hexdigest()


def _dict(row: Any) -> dict[str, Any] | None:
    return dict(row) if row else None


def _model_dump(value: Any) -> dict[str, Any]:
    return contracts.model_to_dict(value)


def assert_authoring_enabled(*, environment: str | None, flag_value: str | None) -> None:
    if str(environment or "").strip().lower() == "production":
        raise AssessmentAIError("assessment_authoring_disabled", "Assessment authoring is never enabled in production.", status_code=403)
    if str(flag_value or "").strip().lower() not in {"1", "true", "yes", "on", "enabled"}:
        raise AssessmentAIError("assessment_authoring_disabled", "Assessment authoring is disabled.", status_code=403)


def assert_authoring_payload_safe(payload: Any) -> None:
    def walk(value: Any, path: str = "") -> None:
        if isinstance(value, dict):
            for key, nested in value.items():
                normalized = str(key).strip().lower()
                if normalized in FORBIDDEN_AUTHORING_INPUT_KEYS:
                    raise AssessmentAIError(
                        "candidate_context_forbidden",
                        "Candidate and recruiting data cannot enter assessment authoring prompts.",
                        status_code=422,
                        detail={"path": f"{path}.{key}".strip(".")},
                    )
                walk(nested, f"{path}.{key}".strip("."))
        elif isinstance(value, list):
            for index, nested in enumerate(value):
                walk(nested, f"{path}[{index}]")
        elif isinstance(value, str):
            if re.search(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", value, re.I):
                raise AssessmentAIError(
                    "authoring_pii_forbidden",
                    "Email addresses cannot enter assessment authoring prompts.",
                    status_code=422,
                    detail={"path": path},
                )
            compact = re.sub(r"[\s().-]", "", value)
            if re.search(r"\+\d{8,15}\b", compact):
                raise AssessmentAIError(
                    "authoring_pii_forbidden",
                    "Phone numbers cannot enter assessment authoring prompts.",
                    status_code=422,
                    detail={"path": path},
                )
    walk(payload)


def assert_model_output_non_authoritative(payload: Any) -> None:
    def walk(value: Any, path: str = "") -> None:
        if isinstance(value, dict):
            for key, nested in value.items():
                normalized = str(key).strip().lower()
                if normalized in FORBIDDEN_OUTPUT_KEYS:
                    raise AssessmentAIError(
                        "model_authority_field_forbidden",
                        "Model output attempted to include an authority-bearing field.",
                        status_code=422,
                        detail={"path": f"{path}.{key}".strip(".")},
                    )
                walk(nested, f"{path}.{key}".strip("."))
        elif isinstance(value, list):
            for index, nested in enumerate(value):
                walk(nested, f"{path}[{index}]")
    walk(payload)


def seed_product2_defaults(cur: Any, *, approved_by_user_id: str = "assessment_product2_design") -> None:
    """Seed inactive-by-flag registry/prompt versions without enabling authoring."""

    role_models = {
        "assessment.author_primary": DEFAULT_PRIMARY_MODEL,
        "assessment.review_secondary": DEFAULT_SECONDARY_MODEL,
        "assessment.adapt_bilingual": DEFAULT_PRIMARY_MODEL,
        "assessment.review_bilingual": DEFAULT_SECONDARY_MODEL,
        "assessment.eval_judge": DEFAULT_SECONDARY_MODEL,
    }
    for role_key, requested_model in role_models.items():
        reasoning_effort = "medium" if role_key in {"assessment.author_primary", "assessment.adapt_bilingual"} else "low"
        prompt_key = role_key.replace(".", "_")
        schema_name = ROLE_SCHEMAS[role_key]
        prompt_text = ROLE_PROMPTS[role_key]
        prompt_hash = hashlib.sha256(prompt_text.encode("utf-8")).hexdigest()
        schema_hash = contracts.schema_sha256(schema_name)
        cur.execute(
            """
            INSERT INTO assessment_prompt_versions
              (prompt_key,version,role_key,prompt_text,prompt_sha256,schema_name,
               schema_version,schema_sha256,rubric_version,blueprint_compatibility,
               created_by_user_id,approved_by_user_id,activated_at)
            VALUES (%s,1,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,now())
            ON CONFLICT (prompt_key,version) DO NOTHING
            """,
            (
                prompt_key,
                role_key,
                prompt_text,
                prompt_hash,
                schema_name,
                contracts.SCHEMA_VERSION,
                schema_hash,
                RUBRIC_VERSION,
                Json({"product_version": PRODUCT_VERSION}),
                approved_by_user_id,
                approved_by_user_id,
            ),
        )
        cur.execute(
            """
            INSERT INTO assessment_ai_model_registry_versions
              (role_key,version,provider,requested_model,api_kind,
               capability_requirements,parameter_profile,budget_profile,
               pricing_snapshot,fallback_policy,allowed_environments,prompt_key,
               output_schema_name,output_schema_version,enabled,
               approved_by_user_id,activated_at)
            VALUES (%s,1,'openai',%s,'openai-responses',%s,%s,%s,%s,%s,%s,%s,%s,%s,FALSE,%s,NULL)
            ON CONFLICT (role_key,version) DO NOTHING
            """,
            (
                role_key,
                requested_model,
                Json({"strict_json_schema": True, "explicit_refusal": True, "tools": False}),
                Json({"reasoning": {"effort": reasoning_effort}, "max_output_tokens": 12000}),
                Json({
                    "max_input_tokens": 30000,
                    "max_output_tokens": 12000,
                    "max_latency_ms": 120000,
                    "max_cost_usd": None,
                    "max_daily_cost_usd": None,
                }),
                Json({"currency": "USD", "input_per_million": None, "output_per_million": None, "effective_at": None}),
                Json({"transient_retries": 2, "schema_retries": 1, "silent_model_downgrade": False}),
                ["development", "test", "staging"],
                prompt_key,
                schema_name,
                contracts.SCHEMA_VERSION,
                approved_by_user_id,
            ),
        )


def assert_registry_qualification_gate(cur: Any, *, registry_version_id: str) -> dict[str, Any]:
    """Failed/missing qualification gates block progression beyond ai_draft.

    Temporary synthetic bootstrap (enabled without formal activator) is skipped so
    recorded staging pilots can exercise the pipeline. Formal activation always
    requires a green live/blinded qualification gate and a pinned
    qualified_provider_model_id.
    """

    cur.execute(
        """
        SELECT registry_version_id::text, approved_by_user_id, activated_at, enabled,
               qualified_provider_model_id
        FROM assessment_ai_model_registry_versions
        WHERE registry_version_id=%s
        """,
        (registry_version_id,),
    )
    registry = _dict(cur.fetchone())
    if not registry:
        raise AssessmentAIError("assessment_model_registry_version_not_found", "Model registry version was not found.", status_code=404)
    # Formal activation pins qualified_provider_model_id. Design-seeded
    # approved_by_user_id alone must not require a prior live gate (chicken/egg).
    if not registry.get("qualified_provider_model_id"):
        return {"skipped": "not_formally_activated", "registry_version_id": registry_version_id}
    cur.execute(
        """
        SELECT eval_run_id::text, mode, passed, gate_profile_version, metrics_json
        FROM assessment_eval_runs
        WHERE registry_version_id=%s
          AND mode IN ('live_staging','blinded_compare')
        ORDER BY created_at DESC
        LIMIT 1
        """,
        (registry_version_id,),
    )
    row = _dict(cur.fetchone())
    if not row or row.get("passed") is not True:
        raise AssessmentAIError(
            "assessment_model_qualification_required",
            "A passed qualification eval is required before drafts can leave ai_draft.",
            status_code=409,
        )
    metrics = row.get("metrics_json") if isinstance(row.get("metrics_json"), dict) else {}
    gate = qual_gates.evaluate_qualification_gates(
        metrics,
        mode=str(row.get("mode") or "live_staging"),
        require_live_cost_latency=True,
    )
    if gate.get("passed") is not True:
        raise AssessmentAIError(
            "assessment_model_qualification_gate_failed",
            "Qualification gate failed; drafts remain in ai_draft.",
            status_code=409,
            detail={"failures": gate.get("failures") or []},
        )
    if str(row.get("gate_profile_version") or "") != qual_gates.GATE_PROFILE_VERSION:
        raise AssessmentAIError(
            "assessment_model_gate_profile_mismatch",
            "Qualification gate profile is stale.",
            status_code=409,
        )
    return {"eval_run_id": row["eval_run_id"], "gate": gate}


def activate_model_registry_version(
    cur: Any,
    *,
    registry_version_id: str,
    qualification_eval_run_id: str,
    actor_user_id: str,
) -> dict[str, Any]:
    """Human activation gate; requires a passed non-replay qualification run."""

    cur.execute(
        "SELECT * FROM assessment_ai_model_registry_versions WHERE registry_version_id=%s FOR UPDATE",
        (registry_version_id,),
    )
    registry = _dict(cur.fetchone())
    if not registry:
        raise AssessmentAIError("assessment_model_registry_version_not_found", "Model registry version was not found.", status_code=404)
    if registry.get("enabled") and registry.get("activated_at"):
        return registry
    cur.execute(
        """
        SELECT * FROM assessment_eval_runs
        WHERE eval_run_id=%s AND registry_version_id=%s AND role_key=%s
          AND passed IS TRUE AND mode IN ('live_staging','blinded_compare')
        """,
        (qualification_eval_run_id, registry_version_id, registry["role_key"]),
    )
    qualification = _dict(cur.fetchone())
    if not qualification:
        raise AssessmentAIError(
            "assessment_model_qualification_required",
            "A passed staging or blinded-human qualification run is required; replay alone cannot activate a model.",
            status_code=409,
        )
    if str(actor_user_id) == str(qualification.get("created_by_user_id")):
        raise AssessmentAIError(
            "assessment_model_independent_approver_required",
            "Model activation requires a human other than the qualification-run creator.",
            status_code=409,
        )
    qualification_metrics = qualification.get("metrics_json") if isinstance(qualification.get("metrics_json"), dict) else {}
    gate = qual_gates.evaluate_qualification_gates(
        qualification_metrics,
        mode=str(qualification.get("mode") or "live_staging"),
        require_live_cost_latency=True,
    )
    if gate.get("passed") is not True:
        raise AssessmentAIError(
            "assessment_model_qualification_gate_failed",
            "Qualification metrics do not meet Product-2 thresholds; activation is blocked.",
            status_code=409,
            detail={"failures": gate.get("failures") or []},
        )
    if str(qualification.get("gate_profile_version") or "") != qual_gates.GATE_PROFILE_VERSION:
        raise AssessmentAIError(
            "assessment_model_gate_profile_mismatch",
            "Qualification gate profile does not match the current Product-2 gate.",
            status_code=409,
        )
    provider_models = qualification_metrics.get("provider_response_models")
    provider_response_model = str(qualification_metrics.get("provider_response_model") or "").strip()
    if not provider_response_model and isinstance(provider_models, list) and len(provider_models) == 1:
        provider_response_model = str(provider_models[0] or "").strip()
    # Also accept nested first_class live identity if recorded that way.
    if not provider_response_model:
        provider_response_model = str(
            ((qualification_metrics.get("first_class") or {}) if isinstance(qualification_metrics.get("first_class"), dict) else {}).get("provider_response_model")
            or ""
        ).strip()
    if not provider_response_model:
        raise AssessmentAIError(
            "assessment_model_provider_identity_required",
            "Qualification evidence must record the provider-returned model identity.",
            status_code=409,
        )
    cur.execute(
        """
        SELECT prompt_version_id FROM assessment_prompt_versions
        WHERE prompt_key=%s AND activated_at IS NOT NULL AND retired_at IS NULL
        ORDER BY version DESC LIMIT 1
        """,
        (registry["prompt_key"],),
    )
    prompt = _dict(cur.fetchone())
    if not prompt or str(prompt["prompt_version_id"]) != str(qualification.get("prompt_version_id")):
        raise AssessmentAIError(
            "assessment_model_prompt_drift",
            "Qualification does not match the currently activated prompt version.",
            status_code=409,
        )
    cur.execute(
        """
        UPDATE assessment_ai_model_registry_versions
        SET enabled=FALSE,retired_at=COALESCE(retired_at,now())
        WHERE role_key=%s AND enabled IS TRUE AND retired_at IS NULL
          AND registry_version_id<>%s
        """,
        (registry["role_key"], registry_version_id),
    )
    cur.execute(
        """
        UPDATE assessment_ai_model_registry_versions
        SET enabled=TRUE,activated_at=now(),approved_by_user_id=%s,
            qualified_provider_model_id=%s
        WHERE registry_version_id=%s AND activated_at IS NULL
        RETURNING *
        """,
        (actor_user_id, provider_response_model, registry_version_id),
    )
    activated = _dict(cur.fetchone())
    if not activated:
        raise AssessmentAIError("assessment_model_activation_conflict", "Registry version could not be activated.")
    return activated


def record_eval_run(
    cur: Any,
    *,
    company_code: str,
    eval_corpus_version: str,
    gate_profile_version: str,
    role_key: str,
    registry_version_id: str,
    prompt_version_id: str,
    mode: str,
    artifact_sha256: str,
    metrics: dict[str, Any],
    passed: bool,
    actor_user_id: str,
    environment: str,
) -> dict[str, Any]:
    if mode not in {"recorded_replay", "live_staging", "blinded_compare", "prompt_regression"}:
        raise AssessmentAIError("invalid_assessment_eval_mode", "Evaluation mode is invalid.", status_code=422)
    if role_key not in ROLE_SCHEMAS:
        raise AssessmentAIError("invalid_assessment_model_role", "Assessment model role is invalid.", status_code=422)
    if mode == "live_staging" and environment != "staging":
        raise AssessmentAIError("assessment_live_eval_staging_only", "Live model evaluation is staging-only.", status_code=403)
    if not re.fullmatch(r"[a-f0-9]{64}", artifact_sha256):
        raise AssessmentAIError("invalid_assessment_eval_artifact", "Evaluation artifact digest is invalid.", status_code=422)
    assert_authoring_payload_safe(metrics)
    if mode == "blinded_compare" and passed:
        if metrics.get("human_reviewed") is not True or int(metrics.get("human_raters") or 0) < 2:
            raise AssessmentAIError(
                "blinded_human_review_required",
                "Passed blinded comparisons require at least two qualified human ratings.",
                status_code=409,
            )
    cur.execute(
        """
        SELECT m.role_key,p.prompt_key
        FROM assessment_ai_model_registry_versions m
        JOIN assessment_prompt_versions p ON p.prompt_version_id=%s
        WHERE m.registry_version_id=%s AND m.role_key=%s
          AND p.prompt_key=m.prompt_key
          AND p.schema_name=m.output_schema_name
          AND p.schema_sha256=%s
        """,
        (
            prompt_version_id,
            registry_version_id,
            role_key,
            contracts.schema_sha256(ROLE_SCHEMAS[role_key]),
        ),
    )
    if not cur.fetchone():
        raise AssessmentAIError("assessment_eval_configuration_mismatch", "Evaluation configuration does not match the registry contract.", status_code=409)
    cur.execute(
        """
        INSERT INTO assessment_eval_runs
          (company_code,eval_corpus_version,gate_profile_version,role_key,
           registry_version_id,prompt_version_id,mode,artifact_sha256,
           metrics_json,passed,created_by_user_id)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
        RETURNING *
        """,
        (
            str(company_code).upper(),
            eval_corpus_version,
            gate_profile_version,
            role_key,
            registry_version_id,
            prompt_version_id,
            mode,
            artifact_sha256,
            Json(metrics),
            passed,
            actor_user_id,
        ),
    )
    return dict(cur.fetchone())


def create_blueprint_version(
    cur: Any,
    *,
    company_code: str,
    blueprint_key: str,
    blueprint: dict[str, Any],
    created_by_user_id: str,
    approve: bool = False,
    approved_by_user_id: str | None = None,
) -> dict[str, Any]:
    assert_authoring_payload_safe(blueprint)
    required = {
        "source_locale",
        "required_locales",
        "section",
        "constructs",
        "item_type",
        "difficulty_target",
        "reading_level",
        "role_context",
        "allowed_context",
        "prohibited_content",
        "scoring_family",
        "choice_count",
        "originality_policy_version",
    }
    missing = sorted(required - set(blueprint))
    if missing:
        raise AssessmentAIError("invalid_blueprint", "Blueprint is missing required fields.", status_code=422, detail={"missing": missing})
    if blueprint.get("source_locale") not in contracts.LOCALES:
        raise AssessmentAIError("invalid_blueprint_locale", "Blueprint locale must be en or ar.", status_code=422)
    required_locales = blueprint.get("required_locales")
    if (
        not isinstance(required_locales, list)
        or not required_locales
        or len(required_locales) != len(set(required_locales))
        or any(locale not in contracts.LOCALES for locale in required_locales)
        or blueprint.get("source_locale") not in required_locales
    ):
        raise AssessmentAIError(
            "invalid_blueprint_required_locales",
            "Blueprint required_locales must be unique, supported, and include the source locale.",
            status_code=422,
        )
    company = str(company_code).upper()
    digest = sha256_json(blueprint)
    cur.execute(
        "SELECT COALESCE(MAX(version),0)+1 AS next_version FROM assessment_blueprint_versions WHERE company_code=%s AND blueprint_key=%s",
        (company, blueprint_key),
    )
    version = int(cur.fetchone()["next_version"])
    status = "approved" if approve else "draft"
    approver = approved_by_user_id if approve else None
    if approve and not approver:
        raise AssessmentAIError("blueprint_approver_required", "Approved blueprints require a human approver.", status_code=422)
    cur.execute(
        """
        INSERT INTO assessment_blueprint_versions
          (company_code,blueprint_key,version,status,blueprint_json,blueprint_sha256,
           created_by_user_id,approved_by_user_id,approved_at)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,CASE WHEN %s='approved' THEN now() END)
        RETURNING *
        """,
        (company, blueprint_key, version, status, Json(blueprint), digest, created_by_user_id, approver, status),
    )
    return dict(cur.fetchone())


def active_model_role(cur: Any, role_key: str, *, environment: str) -> dict[str, Any]:
    cur.execute(
        """
        SELECT * FROM assessment_ai_model_registry_versions
        WHERE role_key=%s AND enabled IS TRUE AND retired_at IS NULL
          AND %s=ANY(allowed_environments)
        ORDER BY version DESC LIMIT 1
        """,
        (role_key, environment),
    )
    row = _dict(cur.fetchone())
    if not row:
        raise AssessmentAIError("assessment_model_role_unavailable", f"No active model is approved for {role_key}.", status_code=503)
    return row


def active_prompt(cur: Any, prompt_key: str, *, expected_schema: str) -> dict[str, Any]:
    cur.execute(
        """
        SELECT * FROM assessment_prompt_versions
        WHERE prompt_key=%s AND activated_at IS NOT NULL AND retired_at IS NULL
        ORDER BY version DESC LIMIT 1
        """,
        (prompt_key,),
    )
    row = _dict(cur.fetchone())
    if not row or row.get("schema_name") != expected_schema:
        raise AssessmentAIError("assessment_prompt_unavailable", f"No compatible active prompt exists for {prompt_key}.", status_code=503)
    actual_hash = hashlib.sha256(str(row["prompt_text"]).encode("utf-8")).hexdigest()
    if actual_hash != row.get("prompt_sha256") or contracts.schema_sha256(expected_schema) != row.get("schema_sha256"):
        raise AssessmentAIError("assessment_prompt_integrity_failed", "Prompt or schema digest does not match its activated version.", status_code=409)
    return row


def enqueue_run(
    cur: Any,
    *,
    company_code: str,
    role_key: str,
    environment: str,
    input_payload: dict[str, Any],
    created_by_user_id: str,
    blueprint_version_id: str | None = None,
    draft_id: str | None = None,
    draft_revision_id: str | None = None,
    parent_run_id: str | None = None,
) -> dict[str, Any]:
    assert_authoring_payload_safe(input_payload)
    assert_model_output_non_authoritative(input_payload)
    company = str(company_code).upper()
    if not company.endswith("_P2_SYNTHETIC"):
        cur.execute(
            "SELECT enabled FROM company_modules WHERE company_code=%s AND module_key='assessments'",
            (company,),
        )
        entitlement = _dict(cur.fetchone())
        if not entitlement or entitlement.get("enabled") is not True:
            raise AssessmentAIError(
                "assessment_tenant_capability_disabled",
                "Assessment authoring is not enabled for this tenant.",
                status_code=403,
            )
    registry = active_model_role(cur, role_key, environment=environment)
    input_payload = dict(input_payload)
    if role_key == "assessment.review_secondary":
        input_payload["reviewer_role_version"] = str(registry["registry_version_id"])
    schema_name = str(registry["output_schema_name"])
    prompt = active_prompt(cur, str(registry["prompt_key"]), expected_schema=schema_name)
    digest_payload = dict(input_payload)
    if role_key == "assessment.author_primary":
        digest_payload.pop("request_id", None)
    input_hash = sha256_json(input_payload)
    dedupe_hash = sha256_json(digest_payload)
    cur.execute(
        """
        SELECT * FROM assessment_ai_runs
        WHERE company_code=%s AND role_key=%s AND dedupe_sha256=%s
          AND registry_version_id=%s AND prompt_version_id=%s
          AND status IN ('queued','running','completed')
        ORDER BY queued_at DESC LIMIT 1
        """,
        (company, role_key, dedupe_hash, registry["registry_version_id"], prompt["prompt_version_id"]),
    )
    existing = _dict(cur.fetchone())
    if existing:
        return {**existing, "idempotent": True}
    cur.execute(
        """
        INSERT INTO assessment_ai_runs
          (company_code,role_key,run_kind,registry_version_id,prompt_version_id,
           blueprint_version_id,draft_id,draft_revision_id,parent_run_id,
           requested_model,schema_name,schema_version,schema_sha256,input_json,
           input_sha256,dedupe_sha256,pricing_snapshot,created_by_user_id)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
        RETURNING *
        """,
        (
            company,
            role_key,
            RUN_KINDS[role_key],
            registry["registry_version_id"],
            prompt["prompt_version_id"],
            blueprint_version_id,
            draft_id,
            draft_revision_id,
            parent_run_id,
            registry["requested_model"],
            schema_name,
            registry["output_schema_version"],
            contracts.schema_sha256(schema_name),
            Json(input_payload),
            input_hash,
            dedupe_hash,
            Json(registry.get("pricing_snapshot") or {}),
            created_by_user_id,
        ),
    )
    return {**dict(cur.fetchone()), "idempotent": False}


def build_authoring_request(
    blueprint: dict[str, Any],
    *,
    requested_item_count: int,
    request_id: str | None = None,
) -> dict[str, Any]:
    content = blueprint.get("blueprint_json") if isinstance(blueprint.get("blueprint_json"), dict) else {}
    payload = {
        "schema_version": contracts.SCHEMA_VERSION,
        "request_id": request_id or str(uuid.uuid4()),
        "blueprint_id": str(blueprint["blueprint_version_id"]),
        "blueprint_version": int(blueprint["version"]),
        "blueprint_sha256": str(blueprint["blueprint_sha256"]),
        "source_locale": content.get("source_locale"),
        "section": content.get("section"),
        "constructs": content.get("constructs") or [],
        "item_type": content.get("item_type"),
        "difficulty_target": content.get("difficulty_target"),
        "reading_level": content.get("reading_level"),
        "role_context": content.get("role_context") or [],
        "allowed_context": content.get("allowed_context") or [],
        "prohibited_content": content.get("prohibited_content") or [],
        "scoring_family": content.get("scoring_family"),
        "choice_count": content.get("choice_count"),
        "requested_item_count": requested_item_count,
        "originality_policy_version": content.get("originality_policy_version") or ORIGINALITY_POLICY_VERSION,
    }
    validated = contracts.validate_contract("AssessmentAuthoringRequestV1", payload)
    return _model_dump(validated)


def _extract_responses_payload(parsed: dict[str, Any]) -> tuple[dict[str, Any] | None, str | None]:
    for output in parsed.get("output") or []:
        if not isinstance(output, dict) or output.get("type") != "message":
            continue
        for content in output.get("content") or []:
            if not isinstance(content, dict):
                continue
            if content.get("type") == "refusal":
                return None, str(content.get("refusal") or "provider_refusal")
            if isinstance(content.get("parsed"), dict):
                return dict(content["parsed"]), None
            if content.get("type") in {"output_text", "text"}:
                text = content.get("text")
                if isinstance(text, str):
                    try:
                        value = json.loads(text)
                        if isinstance(value, dict):
                            return value, None
                    except json.JSONDecodeError:
                        continue
    output_text = parsed.get("output_text")
    if isinstance(output_text, str):
        try:
            value = json.loads(output_text)
            return (value if isinstance(value, dict) else None), None
        except json.JSONDecodeError:
            pass
    return None, None


def openai_responses_adapter(registry: dict[str, Any], prompt: dict[str, Any], run: dict[str, Any]) -> ProviderResult:
    api_key = (
        os.environ.get("WATHEFNI_ASSESSMENT_AI_API_KEY")
        or os.environ.get("OPENAI_API_KEY")
        or ""
    ).strip()
    if not api_key:
        raise AssessmentAIError("assessment_ai_api_key_missing", "Assessment AI provider is not configured.", status_code=503)
    base_url = (os.environ.get("WATHEFNI_ASSESSMENT_AI_BASE_URL") or "https://api.openai.com/v1").rstrip("/")
    if registry.get("provider") != "openai" or registry.get("api_kind") != "openai-responses":
        raise AssessmentAIError("unsupported_assessment_ai_provider", "No adapter is installed for the selected model role.", status_code=503)
    schema_name = str(run["schema_name"])
    parameters = registry.get("parameter_profile") if isinstance(registry.get("parameter_profile"), dict) else {}
    body: dict[str, Any] = {
        "model": str(registry["requested_model"]),
        "input": [
            {"role": "system", "content": str(prompt["prompt_text"])},
            {"role": "user", "content": canonical_json(run["input_json"])},
        ],
        "text": {
            "format": {
                "type": "json_schema",
                "name": schema_name,
                "strict": True,
                "schema": contracts.schema_for(schema_name),
            }
        },
        "max_output_tokens": int(parameters.get("max_output_tokens") or 12000),
    }
    if parameters.get("temperature") is not None:
        body["temperature"] = float(parameters["temperature"])
    if isinstance(parameters.get("reasoning"), dict):
        body["reasoning"] = dict(parameters["reasoning"])
    request = urllib.request.Request(
        f"{base_url}/responses",
        data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        method="POST",
    )
    timeout_s = max(10, int((registry.get("budget_profile") or {}).get("max_latency_ms") or 120000) // 1000)
    started = time.monotonic()
    try:
        with urllib.request.urlopen(request, timeout=timeout_s) as response:
            parsed = json.loads(response.read().decode("utf-8", errors="replace"))
    except urllib.error.HTTPError as exc:
        body_text = exc.read().decode("utf-8", errors="replace")[:1000]
        raise AssessmentAIError("assessment_ai_provider_http_error", body_text or str(exc), status_code=503) from exc
    except Exception as exc:
        raise AssessmentAIError("assessment_ai_provider_error", str(exc), status_code=503) from exc
    if str(parsed.get("status") or "").lower() in {"incomplete", "failed", "cancelled"}:
        reason = parsed.get("incomplete_details") or parsed.get("error") or parsed.get("status")
        raise AssessmentAIError(
            "assessment_ai_incomplete_output",
            f"Provider did not complete the structured response: {reason}",
            status_code=503,
        )
    payload, refusal = _extract_responses_payload(parsed)
    usage = parsed.get("usage") if isinstance(parsed.get("usage"), dict) else {}
    input_details = usage.get("input_tokens_details") if isinstance(usage.get("input_tokens_details"), dict) else {}
    return ProviderResult(
        payload=payload,
        provider_response_model=str(parsed.get("model") or "") or None,
        provider_request_id=str(parsed.get("id") or "") or None,
        input_tokens=usage.get("input_tokens"),
        output_tokens=usage.get("output_tokens"),
        cached_tokens=input_details.get("cached_tokens"),
        latency_ms=int((time.monotonic() - started) * 1000),
        refusal_reason=refusal,
    )


def estimate_cost_usd(
    *,
    pricing_snapshot: dict[str, Any],
    input_tokens: int | None,
    output_tokens: int | None,
) -> float | None:
    input_rate = pricing_snapshot.get("input_per_million")
    output_rate = pricing_snapshot.get("output_per_million")
    if input_rate is None or output_rate is None:
        return None
    return round(
        ((int(input_tokens or 0) * float(input_rate)) + (int(output_tokens or 0) * float(output_rate))) / 1_000_000,
        8,
    )


def enforce_result_budget(registry: dict[str, Any], result: ProviderResult) -> None:
    budget = registry.get("budget_profile") if isinstance(registry.get("budget_profile"), dict) else {}
    if result.input_tokens is not None and int(result.input_tokens) > int(budget.get("max_input_tokens") or 30000):
        raise AssessmentAIError("assessment_ai_budget_exceeded", "Provider input-token usage exceeded the approved run budget.", status_code=409)
    if result.output_tokens is not None and int(result.output_tokens) > int(budget.get("max_output_tokens") or 12000):
        raise AssessmentAIError("assessment_ai_budget_exceeded", "Provider output-token usage exceeded the approved run budget.", status_code=409)
    if result.latency_ms > int(budget.get("max_latency_ms") or 120000):
        raise AssessmentAIError("assessment_ai_budget_exceeded", "Provider latency exceeded the approved run budget.", status_code=409)
    estimated = estimate_cost_usd(
        pricing_snapshot=registry.get("pricing_snapshot") if isinstance(registry.get("pricing_snapshot"), dict) else {},
        input_tokens=result.input_tokens,
        output_tokens=result.output_tokens,
    )
    if budget.get("max_cost_usd") is not None and estimated is not None and estimated > float(budget["max_cost_usd"]):
        raise AssessmentAIError("assessment_ai_budget_exceeded", "Provider cost exceeded the approved run budget.", status_code=409)


def compile_scoring_spec(item: dict[str, Any]) -> tuple[dict[str, Any], str]:
    choices = item.get("choices") if isinstance(item.get("choices"), list) else []
    keys = [str(choice.get("key") or "") for choice in choices if isinstance(choice, dict)]
    if len(keys) != len(choices) or len(set(keys)) != len(keys):
        raise AssessmentAIError("invalid_choice_keys", "Choice keys must be unique and non-empty.", status_code=422)
    answer_key = str(item.get("proposed_answer_key") or "")
    if answer_key not in keys:
        raise AssessmentAIError("invalid_answer_key", "Proposed answer key is not one of the choice IDs.", status_code=422)
    proposal = item.get("proposed_scoring") if isinstance(item.get("proposed_scoring"), dict) else {}
    family = str(proposal.get("family") or "")
    if family not in {"answer_key", "competency_keyed"}:
        raise AssessmentAIError("unsupported_scoring_family", "Only deterministic allowlisted scoring families are accepted.", status_code=422)
    if family == "answer_key":
        correct = float(proposal.get("correct_points") or 0)
        incorrect = float(proposal.get("incorrect_points") or 0)
        maximum = float(proposal.get("max_points") or 0)
        if correct <= 0 or maximum != correct or incorrect < 0:
            raise AssessmentAIError("invalid_answer_key_scoring", "Answer-key scoring must use bounded deterministic points.", status_code=422)
        compiled = {"type": "answer_key", "correct": correct, "incorrect": incorrect, "max_score": maximum}
    else:
        choice_point_rows = proposal.get("choice_points") if isinstance(proposal.get("choice_points"), list) else []
        choice_points = {
            str(row.get("choice_key") or ""): float(row.get("points") or 0)
            for row in choice_point_rows
            if isinstance(row, dict)
        }
        if len(choice_points) != len(choice_point_rows) or set(choice_points) != set(keys):
            raise AssessmentAIError("invalid_competency_scoring", "Competency scoring must assign every choice exactly once.", status_code=422)
        points = {key: choice_points[key] for key in keys}
        if any(point < 0 or point > 100 for point in points.values()):
            raise AssessmentAIError("invalid_competency_scoring", "Competency points are outside approved bounds.", status_code=422)
        compiled = {"type": "competency_keyed", "choice_points": points, "max_score": max(points.values())}
    return compiled, sha256_json(compiled)


def normalize_item_content(item: dict[str, Any]) -> dict[str, Any]:
    compiled, compiled_hash = compile_scoring_spec(item)
    normalized = {
        "draft_local_id": str(item["draft_local_id"]),
        "locale": str(item["locale"]),
        "prompt_text": str(item["prompt_text"]).strip(),
        "choices": [
            {"key": str(choice["key"]).strip().upper(), "text": str(choice["text"]).strip()}
            for choice in item["choices"]
        ],
        "proposed_answer_key": str(item["proposed_answer_key"]).strip().upper(),
        "proposed_scoring": dict(item["proposed_scoring"]),
        "compiled_scoring": compiled,
        "compiled_scoring_sha256": compiled_hash,
        "rationale": str(item["rationale"]).strip(),
        "explanation": str(item["explanation"]).strip(),
        "distractor_rationales": list(item.get("distractor_rationales") or []),
        "competency_tags": list(item.get("competency_tags") or []),
        "skill_tags": list(item.get("skill_tags") or []),
        "role_tags": list(item.get("role_tags") or []),
        "difficulty_rationale": str(item["difficulty_rationale"]).strip(),
        "assumptions": list(item.get("assumptions") or []),
        "original_content_attested": bool(item.get("original_content_attested")),
        "safety_flags": list(item.get("safety_flags") or []),
    }
    assert_model_output_non_authoritative(normalized)
    return normalized


def validate_item_against_authoring_request(item: dict[str, Any], request: dict[str, Any]) -> None:
    if item.get("locale") != request.get("source_locale"):
        raise AssessmentAIError("generated_item_locale_mismatch", "Generated item locale does not match the approved blueprint.", status_code=422)
    if len(item.get("choices") or []) != int(request.get("choice_count") or 0):
        raise AssessmentAIError("generated_item_choice_count_mismatch", "Generated item choice count does not match the blueprint.", status_code=422)
    proposal = item.get("proposed_scoring") if isinstance(item.get("proposed_scoring"), dict) else {}
    if proposal.get("family") != request.get("scoring_family"):
        raise AssessmentAIError("generated_item_scoring_mismatch", "Generated scoring family does not match the blueprint.", status_code=422)
    if item.get("original_content_attested") is not True:
        raise AssessmentAIError("generated_item_originality_attestation_missing", "Generated item lacks the required originality attestation.", status_code=422)


def _normalized_tokens(text: str) -> list[str]:
    return re.findall(r"[\w\u0600-\u06ff]+", str(text or "").lower(), flags=re.UNICODE)


def _shingles(text: str, size: int = 3) -> set[str]:
    tokens = _normalized_tokens(text)
    if len(tokens) < size:
        return {" ".join(tokens)} if tokens else set()
    return {" ".join(tokens[index:index + size]) for index in range(len(tokens) - size + 1)}


def similarity(left: str, right: str) -> float:
    left_set, right_set = _shingles(left), _shingles(right)
    if not left_set or not right_set:
        return 0.0
    return len(left_set & right_set) / len(left_set | right_set)


def minhash_similarity(left: str, right: str, *, permutations: int = 32) -> float:
    left_set, right_set = _shingles(left), _shingles(right)
    if not left_set or not right_set:
        return 0.0

    def signature(values: set[str]) -> list[int]:
        return [
            min(
                int.from_bytes(
                    hashlib.sha256(f"{seed}:{value}".encode("utf-8")).digest()[:8],
                    "big",
                )
                for value in values
            )
            for seed in range(permutations)
        ]

    left_signature, right_signature = signature(left_set), signature(right_set)
    return sum(a == b for a, b in zip(left_signature, right_signature)) / permutations


def local_embedding_similarity(left: str, right: str, *, dimensions: int = 128) -> float:
    def vector(text: str) -> list[float]:
        output = [0.0] * dimensions
        for token in _normalized_tokens(text):
            digest = hashlib.sha256(token.encode("utf-8")).digest()
            index = int.from_bytes(digest[:4], "big") % dimensions
            output[index] += -1.0 if digest[4] & 1 else 1.0
        magnitude = math.sqrt(sum(value * value for value in output))
        return [value / magnitude for value in output] if magnitude else output

    left_vector, right_vector = vector(left), vector(right)
    return sum(a * b for a, b in zip(left_vector, right_vector))


def deterministic_bilingual_checks(
    *,
    source_content: dict[str, Any],
    target_content: dict[str, Any],
    expected_scoring_sha256: str,
) -> dict[str, Any]:
    source_choices = source_content.get("choices") if isinstance(source_content.get("choices"), list) else []
    target_choices = target_content.get("choices") if isinstance(target_content.get("choices"), list) else []
    source_keys = [str(choice.get("key") or "") for choice in source_choices if isinstance(choice, dict)]
    target_keys = [str(choice.get("key") or "") for choice in target_choices if isinstance(choice, dict)]
    source_text = " ".join(
        [str(source_content.get("prompt_text") or ""), *[str(choice.get("text") or "") for choice in source_choices]]
    )
    target_text = " ".join(
        [str(target_content.get("prompt_text") or ""), *[str(choice.get("text") or "") for choice in target_choices]]
    )
    arabic_digit_map = str.maketrans("٠١٢٣٤٥٦٧٨٩", "0123456789")
    source_numbers = re.findall(r"\d+(?:[.,]\d+)?", source_text.translate(arabic_digit_map))
    target_numbers = re.findall(r"\d+(?:[.,]\d+)?", target_text.translate(arabic_digit_map))
    unit_pattern = r"(?:%|\bkg\b|\bkm\b|\bkwd\b|د\.?\s*ك|كجم|كيلوغرام|كيلومتر)"
    unit_aliases = {
        "كجم": "kg",
        "كيلوغرام": "kg",
        "كيلومتر": "km",
        "د.ك": "kwd",
        "د ك": "kwd",
    }
    source_units = sorted(unit_aliases.get(value.casefold(), value.casefold()) for value in re.findall(unit_pattern, source_text, re.I))
    target_units = sorted(unit_aliases.get(value.casefold(), value.casefold()) for value in re.findall(unit_pattern, target_text, re.I))
    target_locale = str(target_content.get("locale") or "")
    arabic_chars = len(re.findall(r"[\u0600-\u06ff]", target_text))
    latin_words = re.findall(r"\b[A-Za-z]{4,}\b", target_text)
    rtl_controls = re.findall(r"[\u202a-\u202e\u2066-\u2069]", target_text)
    findings = {
        "option_key_order_preserved": source_keys == target_keys and bool(source_keys),
        "answer_key_invariant": source_content.get("proposed_answer_key") == target_content.get("proposed_answer_key"),
        "scoring_invariant": target_content.get("compiled_scoring_sha256") == expected_scoring_sha256,
        "numerals_preserved": sorted(source_numbers) == sorted(target_numbers),
        "units_preserved": source_units == target_units,
        "target_script_present": target_locale != "ar" or arabic_chars >= 8,
        "untranslated_fragments": latin_words if target_locale == "ar" else [],
        "explicit_bidi_controls": rtl_controls,
    }
    findings["critical"] = not all(
        findings[key]
        for key in (
            "option_key_order_preserved",
            "answer_key_invariant",
            "scoring_invariant",
            "numerals_preserved",
            "units_preserved",
            "target_script_present",
        )
    )
    findings["passed"] = not findings["critical"] and not findings["untranslated_fragments"]
    return findings


def deterministic_solver_check(content: dict[str, Any]) -> bool | None:
    """Solve narrowly supported arithmetic stems; return None when unsupported."""

    prompt = str(content.get("prompt_text") or "").lower()
    match = re.search(r"\bone\s+quarter\s+of(?:\s+the)?(?:\s+\w+){0,4}?\s+(\d+(?:\.\d+)?)\b", prompt)
    if not match:
        match = re.search(r"\b(\d+(?:\.\d+)?)\b.*\bone\s+quarter\b", prompt)
    if not match:
        match = re.search(r"(?:ربع)[^\d٠-٩]{0,40}([0-9٠-٩]+)", prompt)
    if not match:
        return None
    number_text = match.group(1).translate(str.maketrans("٠١٢٣٤٥٦٧٨٩", "0123456789"))
    expected = float(number_text) / 4
    word_numbers = {
        "zero": 0,
        "one": 1,
        "two": 2,
        "three": 3,
        "four": 4,
        "five": 5,
        "six": 6,
        "seven": 7,
        "eight": 8,
        "nine": 9,
        "ten": 10,
        "eleven": 11,
        "twelve": 12,
    }
    keyed_value: float | None = None
    for choice in content.get("choices") or []:
        if choice.get("key") != content.get("proposed_answer_key"):
            continue
        text = str(choice.get("text") or "").lower().translate(str.maketrans("٠١٢٣٤٥٦٧٨٩", "0123456789"))
        numeric = re.search(r"-?\d+(?:\.\d+)?", text)
        if numeric:
            keyed_value = float(numeric.group(0))
            break
        for word, value in word_numbers.items():
            if re.search(rf"\b{word}\b", text):
                keyed_value = float(value)
                break
    return keyed_value is not None and abs(keyed_value - expected) < 1e-9


def deterministic_product2_review(
    cur: Any,
    *,
    company_code: str,
    battery_key: str,
    content: dict[str, Any],
    exclude_draft_id: str | None = None,
) -> dict[str, Any]:
    prompt = str(content.get("prompt_text") or "")
    choices = content.get("choices") if isinstance(content.get("choices"), list) else []
    keys = [str(choice.get("key") or "") for choice in choices if isinstance(choice, dict)]
    choice_texts = [str(choice.get("text") or "").strip() for choice in choices if isinstance(choice, dict)]
    answer_key = str(content.get("proposed_answer_key") or "")
    cur.execute(
        """
        SELECT item_id::text AS source_id, prompt_text,answer_key, 'live' AS source_kind
        FROM assessment_items WHERE battery_key=%s
        UNION ALL
        SELECT d.draft_id::text, r.content_json->>'prompt_text',
               r.content_json->>'proposed_answer_key','draft'
        FROM assessment_item_drafts d
        JOIN assessment_item_draft_revisions r ON r.draft_revision_id=d.current_revision_id
        WHERE d.company_code=%s AND d.battery_key=%s
          AND (%s IS NULL OR d.draft_id<>%s::uuid)
        """,
        (battery_key, str(company_code).upper(), battery_key, exclude_draft_id, exclude_draft_id),
    )
    comparisons = [dict(row) for row in cur.fetchall()]
    prior_answer_keys = [str(row.get("answer_key") or "") for row in comparisons if row.get("answer_key")]
    exact = []
    semantic = []
    normalized_prompt = " ".join(_normalized_tokens(prompt))
    for candidate in comparisons:
        other = str(candidate.get("prompt_text") or "")
        if " ".join(_normalized_tokens(other)) == normalized_prompt:
            exact.append(candidate["source_id"])
            continue
        ngram_score = similarity(prompt, other)
        minhash_score = minhash_similarity(prompt, other)
        embedding_score = local_embedding_similarity(prompt, other)
        if ngram_score >= 0.65 or minhash_score >= 0.65 or embedding_score >= 0.86:
            semantic.append(
                {
                    "source_id": candidate["source_id"],
                    "source_kind": candidate["source_kind"],
                    "ngram_similarity": round(ngram_score, 4),
                    "minhash_similarity": round(minhash_score, 4),
                    "local_embedding_similarity": round(embedding_score, 4),
                }
            )
    combined_text = " ".join([prompt, *choice_texts])
    bias = [pattern for pattern in _BIAS_PATTERNS if re.search(pattern, combined_text, re.I)]
    leakage = [pattern for pattern in _LEAKAGE_PATTERNS if re.search(pattern, combined_text, re.I)]
    duplicate_choices = len({text.casefold() for text in choice_texts}) != len(choice_texts)
    choice_lengths = [len(_normalized_tokens(text)) for text in choice_texts]
    answer_index = keys.index(answer_key) if answer_key in keys else -1
    solver_agreement = deterministic_solver_check(content)
    answer_length_cue = bool(
        answer_index >= 0
        and choice_lengths
        and choice_lengths[answer_index] > max(1, min(choice_lengths)) * 2.5
    )
    answer_position_pattern = bool(
        len(prior_answer_keys) >= 5
        and answer_key
        and (sum(key == answer_key for key in prior_answer_keys) / len(prior_answer_keys)) >= 0.7
    )
    sentences = [part for part in re.split(r"[.!?؟]+", prompt) if part.strip()]
    average_sentence_words = (
        sum(len(_normalized_tokens(sentence)) for sentence in sentences) / len(sentences)
        if sentences
        else 0
    )
    readability_flags = [
        *(["stem_too_long"] if len(_normalized_tokens(prompt)) > 120 else []),
        *(["sentence_complexity"] if average_sentence_words > 35 else []),
        *(["choice_too_long"] if any(len(_normalized_tokens(text)) > 60 for text in choice_texts) else []),
    ]
    findings = {
        "schema_valid": bool(prompt and 2 <= len(choices) <= 6 and len(keys) == len(set(keys))),
        "answer_key_valid": bool(answer_key and answer_key in keys),
        "compiled_scoring_valid": bool(content.get("compiled_scoring_sha256")),
        "deterministic_solver_agreement": solver_agreement,
        "exact_duplicates": exact,
        "semantic_duplicates": semantic,
        "duplicate_choice_text": duplicate_choices,
        "ambiguity_flags": [
            *([] if prompt.rstrip().endswith(("?", "؟", ".", ":")) else ["unclear_stem_termination"]),
            *([] if not duplicate_choices else ["duplicate_choice_text"]),
            *([] if len(content.get("assumptions") or []) <= 3 else ["too_many_assumptions"]),
        ],
        "bias_flags": bias,
        "readability_flags": readability_flags,
        "leakage_flags": [
            *leakage,
            *(["answer_length_cue"] if answer_length_cue else []),
            *(["answer_position_pattern"] if answer_position_pattern else []),
        ],
        "original_content_attested": content.get("original_content_attested") is True,
    }
    findings["critical"] = bool(
        not findings["schema_valid"]
        or not findings["answer_key_valid"]
        or not findings["compiled_scoring_valid"]
        or solver_agreement is False
        or exact
        or bias
        or leakage
    )
    findings["passed"] = bool(
        not findings["critical"]
        and not semantic
        and not findings["ambiguity_flags"]
        and not findings["leakage_flags"]
        and not readability_flags
        and findings["original_content_attested"]
    )
    return findings


def create_draft_revision_from_generated_item(
    cur: Any,
    *,
    company_code: str,
    battery_key: str,
    blueprint_version_id: str,
    source_run_id: str,
    item: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    content = normalize_item_content(item)
    content_hash = sha256_json(content)
    cur.execute(
        """
        INSERT INTO assessment_item_drafts
          (company_code,battery_key,lifecycle_status,section,competency_tags,
           skill_tags,role_tags,difficulty,locale,prompt_text,choices,
           proposed_answer_key,proposed_scoring,rationale,explanation,
           ai_model,source_blueprint_id,created_by_user_id,blueprint_version_id,
           source_run_id)
        SELECT %s,%s,'ai_draft',b.blueprint_json->>'section',%s,%s,%s,
               b.blueprint_json->>'difficulty_target',%s,%s,%s,%s,%s,%s,%s,
               r.requested_model,b.blueprint_key,'assessment_ai',b.blueprint_version_id,
               r.run_id
        FROM assessment_blueprint_versions b
        JOIN assessment_ai_runs r ON r.run_id=%s
        WHERE b.blueprint_version_id=%s AND b.status='approved'
        RETURNING *
        """,
        (
            str(company_code).upper(),
            battery_key,
            Json(content["competency_tags"]),
            Json(content["skill_tags"]),
            Json(content["role_tags"]),
            content["locale"],
            content["prompt_text"],
            Json(content["choices"]),
            content["proposed_answer_key"],
            Json(content["proposed_scoring"]),
            content["rationale"],
            content["explanation"],
            source_run_id,
            blueprint_version_id,
        ),
    )
    draft = _dict(cur.fetchone())
    if not draft:
        raise AssessmentAIError("approved_blueprint_required", "AI drafts require an approved blueprint.", status_code=409)
    cur.execute(
        """
        INSERT INTO assessment_item_draft_revisions
          (draft_id,company_code,revision,parent_revision_id,source_run_id,
           revision_kind,content_json,content_sha256,locale,answer_key_id,
           compiled_scoring_json,compiled_scoring_sha256,created_by_actor_type,
           created_by_user_id)
        VALUES (%s,%s,1,NULL,%s,'ai_generated',%s,%s,%s,%s,%s,%s,'ai',NULL)
        RETURNING *
        """,
        (
            draft["draft_id"],
            str(company_code).upper(),
            source_run_id,
            Json(content),
            content_hash,
            content["locale"],
            content["proposed_answer_key"],
            Json(content["compiled_scoring"]),
            content["compiled_scoring_sha256"],
        ),
    )
    revision = dict(cur.fetchone())
    cur.execute(
        "UPDATE assessment_item_drafts SET current_revision_id=%s WHERE draft_id=%s RETURNING *",
        (revision["draft_revision_id"], draft["draft_id"]),
    )
    draft = dict(cur.fetchone())
    record_authoring_event(
        cur,
        company_code=company_code,
        draft_id=str(draft["draft_id"]),
        draft_revision_id=str(revision["draft_revision_id"]),
        run_id=source_run_id,
        event_type="ai_draft_created",
        actor_type="ai",
        to_status="ai_draft",
        payload={"content_sha256": content_hash, "published": False},
    )
    return draft, revision


def create_manual_product2_draft(
    cur: Any,
    *,
    company_code: str,
    blueprint_version_id: str,
    content: dict[str, Any],
    actor_user_id: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Human-only fallback when the primary model is unavailable or blocked."""

    cur.execute(
        """
        SELECT * FROM assessment_blueprint_versions
        WHERE blueprint_version_id=%s AND company_code=%s AND status='approved'
        """,
        (blueprint_version_id, str(company_code).upper()),
    )
    blueprint = _dict(cur.fetchone())
    if not blueprint:
        raise AssessmentAIError("approved_blueprint_required", "Manual Product-2 drafts require an approved blueprint.", status_code=409)
    normalized = normalize_item_content(content)
    request = build_authoring_request(blueprint, requested_item_count=1)
    validate_item_against_authoring_request(normalized, request)
    content_hash = sha256_json(normalized)
    blueprint_json = blueprint.get("blueprint_json") if isinstance(blueprint.get("blueprint_json"), dict) else {}
    cur.execute(
        """
        INSERT INTO assessment_item_drafts
          (company_code,battery_key,lifecycle_status,section,competency_tags,
           skill_tags,role_tags,difficulty,locale,prompt_text,choices,
           proposed_answer_key,proposed_scoring,rationale,explanation,ai_model,
           source_blueprint_id,created_by_user_id,blueprint_version_id,source_run_id)
        VALUES (%s,%s,'ai_draft',%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,NULL,%s,%s,%s,NULL)
        RETURNING *
        """,
        (
            str(company_code).upper(),
            str(blueprint_json.get("battery_key") or "wathefni_ability_v1"),
            blueprint_json["section"],
            Json(normalized["competency_tags"]),
            Json(normalized["skill_tags"]),
            Json(normalized["role_tags"]),
            blueprint_json["difficulty_target"],
            normalized["locale"],
            normalized["prompt_text"],
            Json(normalized["choices"]),
            normalized["proposed_answer_key"],
            Json(normalized["proposed_scoring"]),
            normalized["rationale"],
            normalized["explanation"],
            blueprint["blueprint_key"],
            actor_user_id,
            blueprint_version_id,
        ),
    )
    draft = dict(cur.fetchone())
    cur.execute(
        """
        INSERT INTO assessment_item_draft_revisions
          (draft_id,company_code,revision,parent_revision_id,source_run_id,
           revision_kind,content_json,content_sha256,locale,answer_key_id,
           compiled_scoring_json,compiled_scoring_sha256,created_by_actor_type,
           created_by_user_id)
        VALUES (%s,%s,1,NULL,NULL,'human_rewrite',%s,%s,%s,%s,%s,%s,'human',%s)
        RETURNING *
        """,
        (
            draft["draft_id"],
            str(company_code).upper(),
            Json(normalized),
            content_hash,
            normalized["locale"],
            normalized["proposed_answer_key"],
            Json(normalized["compiled_scoring"]),
            normalized["compiled_scoring_sha256"],
            actor_user_id,
        ),
    )
    revision = dict(cur.fetchone())
    cur.execute(
        "UPDATE assessment_item_drafts SET current_revision_id=%s WHERE draft_id=%s RETURNING *",
        (revision["draft_revision_id"], draft["draft_id"]),
    )
    draft = dict(cur.fetchone())
    record_authoring_event(
        cur,
        company_code=company_code,
        draft_id=str(draft["draft_id"]),
        draft_revision_id=str(revision["draft_revision_id"]),
        event_type="manual_product2_draft_created",
        actor_type="human",
        actor_user_id=actor_user_id,
        to_status="ai_draft",
        payload={"primary_model_bypassed": True, "published": False},
    )
    return draft, revision


def record_authoring_event(
    cur: Any,
    *,
    company_code: str,
    event_type: str,
    actor_type: str,
    draft_id: str | None = None,
    draft_revision_id: str | None = None,
    run_id: str | None = None,
    actor_user_id: str | None = None,
    from_status: str | None = None,
    to_status: str | None = None,
    payload: dict[str, Any] | None = None,
) -> None:
    cur.execute(
        """
        INSERT INTO assessment_authoring_events
          (company_code,draft_id,draft_revision_id,run_id,event_type,actor_type,
           actor_user_id,from_status,to_status,payload_json)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
        """,
        (
            str(company_code).upper(),
            draft_id,
            draft_revision_id,
            run_id,
            event_type,
            actor_type,
            actor_user_id,
            from_status,
            to_status,
            Json(payload or {}),
        ),
    )


def _load_run_bundle(cur: Any, run_id: str, *, for_update: bool = False) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    cur.execute(
        f"SELECT * FROM assessment_ai_runs WHERE run_id=%s {'FOR UPDATE' if for_update else ''}",
        (run_id,),
    )
    run = _dict(cur.fetchone())
    if not run:
        raise AssessmentAIError("assessment_ai_run_not_found", "Assessment AI run was not found.", status_code=404)
    cur.execute("SELECT * FROM assessment_ai_model_registry_versions WHERE registry_version_id=%s", (run["registry_version_id"],))
    registry = _dict(cur.fetchone())
    cur.execute("SELECT * FROM assessment_prompt_versions WHERE prompt_version_id=%s", (run["prompt_version_id"],))
    prompt = _dict(cur.fetchone())
    if not registry or not prompt:
        raise AssessmentAIError("assessment_ai_run_configuration_missing", "Run configuration is unavailable.", status_code=409)
    return run, registry, prompt


def _update_run_result(
    cur: Any,
    *,
    run_id: str,
    status: str,
    result: ProviderResult | None = None,
    payload: dict[str, Any] | None = None,
    attempt_count: int,
    error: AssessmentAIError | None = None,
) -> dict[str, Any]:
    output_hash = sha256_json(payload) if payload is not None else None
    pricing = {}
    cur.execute("SELECT pricing_snapshot FROM assessment_ai_runs WHERE run_id=%s", (run_id,))
    current = cur.fetchone()
    if current and isinstance(current.get("pricing_snapshot"), dict):
        pricing = current["pricing_snapshot"]
    cost = estimate_cost_usd(
        pricing_snapshot=pricing,
        input_tokens=result.input_tokens if result else None,
        output_tokens=result.output_tokens if result else None,
    )
    cur.execute(
        """
        UPDATE assessment_ai_runs
        SET status=%s,output_json=%s,output_sha256=%s,
            provider_response_model=%s,provider_request_id=%s,input_tokens=%s,
            output_tokens=%s,cached_tokens=%s,estimated_cost_usd=%s,latency_ms=%s,
            attempt_count=%s,refusal_reason=%s,error_code=%s,error_message=%s,
            completed_at=now()
        WHERE run_id=%s
        RETURNING *
        """,
        (
            status,
            Json(payload) if payload is not None else None,
            output_hash,
            result.provider_response_model if result else None,
            result.provider_request_id if result else None,
            result.input_tokens if result else None,
            result.output_tokens if result else None,
            result.cached_tokens if result else None,
            cost,
            result.latency_ms if result else None,
            attempt_count,
            result.refusal_reason if result else None,
            error.code if error else None,
            error.message[:1000] if error else None,
            run_id,
        ),
    )
    return dict(cur.fetchone())


def process_queued_run(
    app_mod: Any,
    run_id: str,
    *,
    adapter: ProviderAdapter | None = None,
) -> dict[str, Any]:
    """Process one queued authoring run. Candidate runtime never calls this."""

    environment = str(os.environ.get("WATHEFNI_ENV") or "").lower()
    assert_authoring_enabled(
        environment=environment,
        flag_value=os.environ.get("WATHEFNI_ASSESSMENT_AUTHORING"),
    )
    with app_mod.db_connect() as conn:
        with conn.cursor() as cur:
            run, registry, prompt = _load_run_bundle(cur, run_id, for_update=True)
            if run["status"] == "completed":
                return {**run, "idempotent": True}
            if run["status"] != "queued":
                raise AssessmentAIError("assessment_ai_run_not_queued", "Only queued runs can be processed.")
            try:
                import tenant_control_queue_gate as _tc_qg

                company = str(run.get("company_code") or "WATHEFNI").upper()
                queued_epoch = _tc_qg.persist_work_epoch(
                    cur,
                    company_code=company,
                    work_kind="assessment_ai",
                    work_ref=str(run_id),
                    module_key="assessments",
                )
                allowed, decision = _tc_qg.gate_or_skip(
                    cur,
                    company_code=company,
                    module_key="assessments",
                    work_kind="assessment_ai",
                    work_ref=str(run_id),
                    queued_epoch=queued_epoch,
                    surface="workers",
                )
                if not allowed:
                    return {
                        **run,
                        "status": "held",
                        "held": True,
                        "reason": decision.reason_code,
                        "correlation_id": decision.audit_correlation_id,
                    }
            except Exception:
                pass
            budget = registry.get("budget_profile") if isinstance(registry.get("budget_profile"), dict) else {}
            estimated_input_tokens = max(1, len(canonical_json(run["input_json"])) // 4)
            if estimated_input_tokens > int(budget.get("max_input_tokens") or 30000):
                blocked = _update_run_result(
                    cur,
                    run_id=run_id,
                    status="budget_blocked",
                    attempt_count=0,
                    error=AssessmentAIError("assessment_ai_budget_exceeded", "Estimated input exceeds the approved token budget."),
                )
                conn.commit()
                return blocked
            if budget.get("max_daily_cost_usd") is not None:
                cur.execute(
                    """
                    SELECT COALESCE(SUM(estimated_cost_usd),0) AS daily_cost
                    FROM assessment_ai_runs
                    WHERE role_key=%s AND queued_at>=date_trunc('day',now())
                    """,
                    (run["role_key"],),
                )
                daily_cost = float((cur.fetchone() or {}).get("daily_cost") or 0)
                if daily_cost >= float(budget["max_daily_cost_usd"]):
                    blocked = _update_run_result(
                        cur,
                        run_id=run_id,
                        status="budget_blocked",
                        attempt_count=0,
                        error=AssessmentAIError("assessment_ai_daily_budget_exceeded", "Daily role budget is exhausted."),
                    )
                    conn.commit()
                    return blocked
            cur.execute(
                """
                SELECT COUNT(*)::int AS count
                FROM assessment_ai_runs
                WHERE role_key=%s AND completed_at>=now()-interval '10 minutes'
                  AND error_code IN ('assessment_ai_provider_error','assessment_ai_provider_http_error')
                """,
                (run["role_key"],),
            )
            recent_provider_failures = int((cur.fetchone() or {}).get("count") or 0)
            if recent_provider_failures >= 5:
                blocked = _update_run_result(
                    cur,
                    run_id=run_id,
                    status="failed",
                    attempt_count=0,
                    error=AssessmentAIError(
                        "assessment_ai_provider_circuit_open",
                        "Provider circuit is open after repeated recent failures.",
                        status_code=503,
                    ),
                )
                conn.commit()
                return blocked
            cur.execute(
                "UPDATE assessment_ai_runs SET status='running',started_at=now(),attempt_count=attempt_count+1 WHERE run_id=%s",
                (run_id,),
            )
        conn.commit()
    call_adapter = adapter or openai_responses_adapter
    fallback = registry.get("fallback_policy") if isinstance(registry.get("fallback_policy"), dict) else {}
    max_attempts = 1 + max(int(fallback.get("transient_retries") or 0), int(fallback.get("schema_retries") or 0))
    last_error: AssessmentAIError | None = None
    result: ProviderResult | None = None
    payload: dict[str, Any] | None = None
    attempts = 0
    while attempts < max_attempts:
        attempts += 1
        try:
            result = call_adapter(registry, prompt, run)
            if result.refusal_reason:
                corrective_retries = int(fallback.get("schema_retries") or 0)
                if attempts <= corrective_retries:
                    continue
                with app_mod.db_connect() as conn, conn.cursor() as cur:
                    completed = _update_run_result(cur, run_id=run_id, status="refused", result=result, payload=None, attempt_count=attempts)
                    conn.commit()
                return completed
            if not isinstance(result.payload, dict):
                raise AssessmentAIError("assessment_ai_empty_output", "Provider returned no structured output.", status_code=503)
            enforce_result_budget(registry, result)
            qualified_model = str(registry.get("qualified_provider_model_id") or "").strip()
            if qualified_model and str(result.provider_response_model or "") != qualified_model:
                raise AssessmentAIError(
                    "assessment_ai_provider_model_drift",
                    "Provider-returned model identity differs from the qualified registry version.",
                    status_code=409,
                )
            assert_authoring_payload_safe(result.payload)
            assert_model_output_non_authoritative(result.payload)
            validated = contracts.validate_contract(str(run["schema_name"]), result.payload)
            payload = _model_dump(validated)
            break
        except AssessmentAIError as exc:
            last_error = exc
            if exc.code in {
                "assessment_ai_budget_exceeded",
                "assessment_ai_provider_model_drift",
                "model_authority_field_forbidden",
            }:
                break
        except Exception as exc:
            last_error = AssessmentAIError("assessment_ai_schema_invalid", str(exc), status_code=422)
    if payload is None:
        with app_mod.db_connect() as conn, conn.cursor() as cur:
            failed = _update_run_result(
                cur,
                run_id=run_id,
                status="budget_blocked" if last_error and last_error.code == "assessment_ai_budget_exceeded" else "failed",
                result=result,
                payload=None,
                attempt_count=attempts,
                error=last_error or AssessmentAIError("assessment_ai_failed", "Assessment AI run failed."),
            )
            conn.commit()
        return failed
    if payload.get("refusal_reason"):
        if result is not None:
            result.refusal_reason = str(payload["refusal_reason"])
        with app_mod.db_connect() as conn, conn.cursor() as cur:
            refused = _update_run_result(
                cur,
                run_id=run_id,
                status="refused",
                result=result,
                payload=payload,
                attempt_count=attempts,
            )
            conn.commit()
        return refused

    try:
        with app_mod.db_connect() as conn:
            with conn.cursor() as cur:
                run, registry, prompt = _load_run_bundle(cur, run_id, for_update=True)
                if run["run_kind"] == "author_primary":
                    if not run.get("blueprint_version_id"):
                        raise AssessmentAIError("blueprint_required", "Primary authoring requires an approved blueprint.", status_code=422)
                    requested_count = int((run.get("input_json") or {}).get("requested_item_count") or 0)
                    if str(payload.get("request_id") or "") != str((run.get("input_json") or {}).get("request_id") or ""):
                        raise AssessmentAIError(
                            "assessment_ai_request_id_mismatch",
                            "Structured output is not bound to the queued request.",
                            status_code=422,
                        )
                    if len(payload.get("items") or []) != requested_count:
                        raise AssessmentAIError(
                            "assessment_ai_item_count_mismatch",
                            "Structured output item count does not match the approved request.",
                            status_code=422,
                        )
                    cur.execute(
                        "SELECT * FROM assessment_blueprint_versions WHERE blueprint_version_id=%s AND status='approved'",
                        (run["blueprint_version_id"],),
                    )
                    blueprint = _dict(cur.fetchone())
                    if not blueprint:
                        raise AssessmentAIError("approved_blueprint_required", "Primary authoring requires an approved blueprint.", status_code=409)
                    drafts = []
                    for item in payload.get("items") or []:
                        validate_item_against_authoring_request(item, run.get("input_json") or {})
                        draft, revision = create_draft_revision_from_generated_item(
                            cur,
                            company_code=run["company_code"],
                            battery_key=str((blueprint.get("blueprint_json") or {}).get("battery_key") or "wathefni_ability_v1"),
                            blueprint_version_id=str(run["blueprint_version_id"]),
                            source_run_id=run_id,
                            item=item,
                        )
                        drafts.append({"draft_id": str(draft["draft_id"]), "draft_revision_id": str(revision["draft_revision_id"])})
                    payload = {**payload, "created_drafts": drafts}
                elif run["run_kind"] == "review_secondary":
                    _persist_secondary_review(cur, run=run, payload=payload)
                elif run["run_kind"] == "adapt_bilingual":
                    payload = {**payload, **_persist_bilingual_adaptation(cur, run=run, payload=payload)}
                elif run["run_kind"] == "review_bilingual":
                    _persist_bilingual_review(cur, run=run, payload=payload)
                completed = _update_run_result(cur, run_id=run_id, status="completed", result=result, payload=payload, attempt_count=attempts)
            conn.commit()
    except Exception as exc:
        persistence_error = exc if isinstance(exc, AssessmentAIError) else AssessmentAIError("assessment_ai_persistence_failed", str(exc), status_code=500)
        with app_mod.db_connect() as conn, conn.cursor() as cur:
            failed = _update_run_result(
                cur,
                run_id=run_id,
                status="failed",
                result=result,
                payload=payload,
                attempt_count=attempts,
                error=persistence_error,
            )
            conn.commit()
        return failed
    try:
        app_mod.record_llm_call(
            call_name=f"assessment_product2_{run['run_kind']}",
            provider={
                "model": registry.get("requested_model"),
                "provider": registry.get("provider"),
                "api": registry.get("api_kind"),
            },
            prompt_mode=f"{prompt.get('prompt_key')}@{prompt.get('version')}",
            prompt_docs_loaded=False,
            prompt_hash=prompt.get("prompt_sha256"),
            estimated_input_tokens=None,
            latency_ms=result.latency_ms if result else None,
            status="ok",
            parsed={
                "id": result.provider_request_id if result else None,
                "model": result.provider_response_model if result else None,
                "usage": {
                    "input_tokens": result.input_tokens if result else None,
                    "output_tokens": result.output_tokens if result else None,
                    "input_tokens_details": {"cached_tokens": result.cached_tokens if result else None},
                },
            },
            metadata={"assessment_ai_run_id": run_id, "schema_sha256": run.get("schema_sha256")},
        )
    except Exception:
        pass
    return completed


def _revision_for_run(cur: Any, run: dict[str, Any], *, for_update: bool = False) -> tuple[dict[str, Any], dict[str, Any]]:
    if not run.get("draft_id") or not run.get("draft_revision_id"):
        raise AssessmentAIError("draft_revision_required", "This run requires an exact draft revision.", status_code=422)
    cur.execute(
        f"""
        SELECT d.*,r.draft_revision_id,r.content_json,r.content_sha256,r.answer_key_id,
               r.compiled_scoring_json,r.compiled_scoring_sha256,r.locale AS revision_locale
        FROM assessment_item_drafts d
        JOIN assessment_item_draft_revisions r ON r.draft_id=d.draft_id
        WHERE d.draft_id=%s AND r.draft_revision_id=%s AND d.company_code=%s
        {'FOR UPDATE OF d' if for_update else ''}
        """,
        (run["draft_id"], run["draft_revision_id"], run["company_code"]),
    )
    row = _dict(cur.fetchone())
    if not row or str(row.get("current_revision_id")) != str(run["draft_revision_id"]):
        raise AssessmentAIError("stale_draft_revision", "Review/adaptation run is not bound to the current revision.", status_code=409)
    revision = {
        "draft_revision_id": row["draft_revision_id"],
        "content_json": row["content_json"],
        "content_sha256": row["content_sha256"],
        "answer_key_id": row["answer_key_id"],
        "compiled_scoring_json": row["compiled_scoring_json"],
        "compiled_scoring_sha256": row["compiled_scoring_sha256"],
        "locale": row["revision_locale"],
    }
    return row, revision


def enqueue_secondary_review(
    cur: Any,
    *,
    company_code: str,
    draft_id: str,
    actor_user_id: str,
    environment: str,
) -> dict[str, Any]:
    cur.execute(
        """
        SELECT d.*,r.content_json,r.content_sha256,r.draft_revision_id,
               b.blueprint_json,b.blueprint_sha256
        FROM assessment_item_drafts d
        JOIN assessment_item_draft_revisions r ON r.draft_revision_id=d.current_revision_id
        JOIN assessment_blueprint_versions b ON b.blueprint_version_id=d.blueprint_version_id
        WHERE d.draft_id=%s AND d.company_code=%s
        """,
        (draft_id, str(company_code).upper()),
    )
    row = _dict(cur.fetchone())
    if not row:
        raise AssessmentAIError("assessment_item_draft_not_found", "Draft was not found.", status_code=404)
    deterministic = deterministic_product2_review(
        cur,
        company_code=company_code,
        battery_key=str(row["battery_key"]),
        content=dict(row["content_json"]),
        exclude_draft_id=draft_id,
    )
    cur.execute(
        """
        INSERT INTO assessment_item_reviews
          (draft_id,company_code,review_type,reviewer_type,reviewer_id,
           from_status,to_status,findings_json,notes)
        VALUES (%s,%s,'deterministic_product2','system',NULL,%s,%s,%s,%s)
        """,
        (
            draft_id,
            str(company_code).upper(),
            row["lifecycle_status"],
            row["lifecycle_status"],
            Json({**deterministic, "draft_revision_id": str(row["draft_revision_id"]), "draft_sha256": row["content_sha256"]}),
            "Deterministic Product-2 checks; never publishes or changes scoring.",
        ),
    )
    if not deterministic["passed"]:
        raise AssessmentAIError(
            "deterministic_review_not_passed",
            "Draft failed deterministic review and cannot be sent to the secondary model.",
            detail={"findings": deterministic},
        )
    stored_content = dict(row["content_json"])
    blinded_draft = {
        key: stored_content.get(key)
        for key in (
            "locale",
            "prompt_text",
            "choices",
            "proposed_answer_key",
            "proposed_scoring",
            "compiled_scoring",
            "competency_tags",
            "skill_tags",
            "role_tags",
            "assumptions",
            "safety_flags",
        )
    }
    input_payload = {
        "schema_version": contracts.SCHEMA_VERSION,
        "draft_revision_id": str(row["draft_revision_id"]),
        "draft_sha256": str(row["content_sha256"]),
        "draft": blinded_draft,
        "blueprint": row["blueprint_json"],
        "review_dimensions": [
            "schema_blueprint_fit",
            "answer_correctness",
            "ambiguity",
            "duplicate_risk",
            "bias_fairness",
            "leakage",
            "distractor_quality",
            "difficulty",
            "language_quality",
        ],
        "rubric_version": RUBRIC_VERSION,
    }
    return enqueue_run(
        cur,
        company_code=company_code,
        role_key="assessment.review_secondary",
        environment=environment,
        input_payload=input_payload,
        created_by_user_id=actor_user_id,
        blueprint_version_id=str(row["blueprint_version_id"]),
        draft_id=draft_id,
        draft_revision_id=str(row["draft_revision_id"]),
        parent_run_id=str(row["source_run_id"]) if row.get("source_run_id") else None,
    )


def _persist_secondary_review(cur: Any, *, run: dict[str, Any], payload: dict[str, Any]) -> None:
    draft, revision = _revision_for_run(cur, run, for_update=True)
    if payload.get("draft_sha256") != revision["content_sha256"]:
        raise AssessmentAIError("secondary_review_digest_mismatch", "Secondary review is not bound to the current revision.", status_code=409)
    if str(payload.get("reviewer_role_version") or "") != str(run["registry_version_id"]):
        raise AssessmentAIError("secondary_review_role_version_mismatch", "Secondary review returned the wrong model-role version.", status_code=409)
    critical = list(payload.get("critical_findings") or [])
    recommendation = str(payload.get("overall_recommendation") or "")
    passed = recommendation == "pass" and not critical and all(
        dimension.get("verdict") != "fail" for dimension in payload.get("dimensions") or []
    )
    findings = {
        **payload,
        "passed": passed,
        "draft_revision_id": str(revision["draft_revision_id"]),
        "draft_sha256": revision["content_sha256"],
        "run_id": str(run["run_id"]),
        "registry_version_id": str(run["registry_version_id"]),
        "prompt_version_id": str(run["prompt_version_id"]),
        "schema_name": run["schema_name"],
        "schema_version": run["schema_version"],
        "schema_sha256": run["schema_sha256"],
    }
    cur.execute(
        """
        INSERT INTO assessment_item_reviews
          (draft_id,company_code,review_type,reviewer_type,reviewer_id,
           from_status,to_status,findings_json,notes)
        VALUES (%s,%s,'secondary_model','ai',%s,%s,'automated_review',%s,%s)
        """,
        (
            draft["draft_id"],
            run["company_code"],
            run["requested_model"],
            draft["lifecycle_status"],
            Json(findings),
            "Independent findings only; model cannot rewrite, publish, score, or decide.",
        ),
    )
    if passed:
        # Model-role qualification gate must be green before leaving ai_draft.
        assert_registry_qualification_gate(cur, registry_version_id=str(run["registry_version_id"]))
        cur.execute(
            """
            UPDATE assessment_item_drafts
            SET lifecycle_status='automated_review',updated_at=now()
            WHERE draft_id=%s AND current_revision_id=%s AND lifecycle_status='ai_draft'
            """,
            (draft["draft_id"], revision["draft_revision_id"]),
        )
    record_authoring_event(
        cur,
        company_code=run["company_code"],
        draft_id=str(draft["draft_id"]),
        draft_revision_id=str(revision["draft_revision_id"]),
        run_id=str(run["run_id"]),
        event_type="secondary_review_completed",
        actor_type="ai",
        from_status=str(draft["lifecycle_status"]),
        to_status="automated_review" if passed else str(draft["lifecycle_status"]),
        payload={"passed": passed, "published": False},
    )


def enqueue_bilingual_adaptation(
    cur: Any,
    *,
    company_code: str,
    draft_id: str,
    target_locale: str,
    actor_user_id: str,
    environment: str,
) -> dict[str, Any]:
    cur.execute(
        """
        SELECT d.*,r.content_json,r.content_sha256,r.draft_revision_id,r.locale AS source_locale,
               r.answer_key_id,r.compiled_scoring_sha256,b.blueprint_json
        FROM assessment_item_drafts d
        JOIN assessment_item_draft_revisions r ON r.draft_revision_id=d.current_revision_id
        JOIN assessment_blueprint_versions b ON b.blueprint_version_id=d.blueprint_version_id
        WHERE d.draft_id=%s AND d.company_code=%s
        """,
        (draft_id, str(company_code).upper()),
    )
    row = _dict(cur.fetchone())
    if not row:
        raise AssessmentAIError("assessment_item_draft_not_found", "Draft was not found.", status_code=404)
    if target_locale not in contracts.LOCALES or target_locale == row["source_locale"]:
        raise AssessmentAIError("invalid_target_locale", "Target locale must be the other supported locale.", status_code=422)
    if row["lifecycle_status"] not in {"automated_review", "human_review"}:
        raise AssessmentAIError("source_review_required", "Source draft must pass automated review before adaptation.")
    content = dict(row["content_json"])
    input_payload = {
        "schema_version": contracts.SCHEMA_VERSION,
        "source_revision_id": str(row["draft_revision_id"]),
        "source_sha256": row["content_sha256"],
        "source_locale": row["source_locale"],
        "target_locale": target_locale,
        "source_prompt_text": content["prompt_text"],
        "source_choices": content["choices"],
        "immutable_option_keys": [choice["key"] for choice in content["choices"]],
        "immutable_scoring_sha256": row["compiled_scoring_sha256"],
        "blueprint": row["blueprint_json"],
        "adaptation_policy": {
            "default_arabic": "MSA",
            "kuwaiti_dialect_only_when_blueprint_requires": True,
            "literal_translation_required": False,
        },
    }
    return enqueue_run(
        cur,
        company_code=company_code,
        role_key="assessment.adapt_bilingual",
        environment=environment,
        input_payload=input_payload,
        created_by_user_id=actor_user_id,
        blueprint_version_id=str(row["blueprint_version_id"]),
        draft_id=draft_id,
        draft_revision_id=str(row["draft_revision_id"]),
        parent_run_id=str(row["source_run_id"]) if row.get("source_run_id") else None,
    )


def _persist_bilingual_adaptation(cur: Any, *, run: dict[str, Any], payload: dict[str, Any]) -> dict[str, Any]:
    source_draft, source_revision = _revision_for_run(cur, run)
    if payload.get("source_sha256") != source_revision["content_sha256"]:
        raise AssessmentAIError("translation_source_digest_mismatch", "Adaptation is not bound to the source revision.", status_code=409)
    source_content = dict(source_revision["content_json"])
    source_keys = [choice["key"] for choice in source_content["choices"]]
    adapted_choices = list(payload.get("adapted_choices") or [])
    adapted_keys = [choice.get("key") for choice in adapted_choices]
    if adapted_keys != source_keys:
        raise AssessmentAIError("translation_key_invariance_failed", "Translation changed option key identity or order.", status_code=422)
    target_locale = str(payload.get("target_locale") or "")
    if target_locale == source_revision["locale"] or target_locale not in contracts.LOCALES:
        raise AssessmentAIError("invalid_target_locale", "Adaptation target locale is invalid.", status_code=422)
    content = {
        **source_content,
        "locale": target_locale,
        "prompt_text": str(payload["adapted_prompt_text"]).strip(),
        "choices": [{"key": str(choice["key"]), "text": str(choice["text"]).strip()} for choice in adapted_choices],
        "translation": {
            "source_revision_id": str(source_revision["draft_revision_id"]),
            "terminology_decisions": payload.get("terminology_decisions") or [],
            "cultural_adaptations": payload.get("cultural_adaptations") or [],
            "back_translation_summary": payload.get("back_translation_summary"),
            "preserved_invariants": payload.get("preserved_invariants") or [],
        },
    }
    bilingual_findings = deterministic_bilingual_checks(
        source_content=source_content,
        target_content=content,
        expected_scoring_sha256=str(source_revision["compiled_scoring_sha256"]),
    )
    if bilingual_findings["critical"]:
        raise AssessmentAIError(
            "translation_deterministic_checks_failed",
            "Adaptation changed a required bilingual invariant.",
            status_code=422,
            detail={"findings": bilingual_findings},
        )
    content_hash = sha256_json(content)
    cur.execute(
        """
        INSERT INTO assessment_item_drafts
          (company_code,battery_key,lifecycle_status,section,competency_tags,
           skill_tags,role_tags,difficulty,locale,prompt_text,choices,
           proposed_answer_key,proposed_scoring,rationale,explanation,ai_model,
           source_blueprint_id,created_by_user_id,blueprint_version_id,source_run_id)
        VALUES (%s,%s,'ai_draft',%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,
                'assessment_ai',%s,%s)
        RETURNING *
        """,
        (
            run["company_code"],
            source_draft["battery_key"],
            source_draft["section"],
            Json(content.get("competency_tags") or []),
            Json(content.get("skill_tags") or []),
            Json(content.get("role_tags") or []),
            source_draft.get("difficulty"),
            target_locale,
            content["prompt_text"],
            Json(content["choices"]),
            source_revision["answer_key_id"],
            Json(source_content["proposed_scoring"]),
            content.get("rationale"),
            content.get("explanation"),
            run["requested_model"],
            source_draft["source_blueprint_id"],
            source_draft["blueprint_version_id"],
            run["run_id"],
        ),
    )
    target_draft = dict(cur.fetchone())
    cur.execute(
        """
        INSERT INTO assessment_item_draft_revisions
          (draft_id,company_code,revision,parent_revision_id,source_run_id,
           revision_kind,content_json,content_sha256,locale,answer_key_id,
           compiled_scoring_json,compiled_scoring_sha256,created_by_actor_type)
        VALUES (%s,%s,1,%s,%s,'bilingual_adaptation',%s,%s,%s,%s,%s,%s,'ai')
        RETURNING *
        """,
        (
            target_draft["draft_id"],
            run["company_code"],
            source_revision["draft_revision_id"],
            run["run_id"],
            Json(content),
            content_hash,
            target_locale,
            source_revision["answer_key_id"],
            Json(source_revision["compiled_scoring_json"]),
            source_revision["compiled_scoring_sha256"],
        ),
    )
    target_revision = dict(cur.fetchone())
    cur.execute(
        "UPDATE assessment_item_drafts SET current_revision_id=%s WHERE draft_id=%s",
        (target_revision["draft_revision_id"], target_draft["draft_id"]),
    )
    pair_payload = {
        "source_revision_id": str(source_revision["draft_revision_id"]),
        "target_revision_id": str(target_revision["draft_revision_id"]),
        "source_sha256": source_revision["content_sha256"],
        "target_sha256": content_hash,
    }
    pair_hash = sha256_json(pair_payload)
    cur.execute(
        """
        INSERT INTO assessment_translation_pairs
          (company_code,source_revision_id,target_revision_id,source_locale,
           target_locale,source_sha256,target_sha256,pair_sha256,status,
           adaptation_run_id,findings_json)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,'automated_review',%s,%s)
        RETURNING *
        """,
        (
            run["company_code"],
            source_revision["draft_revision_id"],
            target_revision["draft_revision_id"],
            source_revision["locale"],
            target_locale,
            source_revision["content_sha256"],
            content_hash,
            pair_hash,
            run["run_id"],
            Json({**bilingual_findings, "published": False}),
        ),
    )
    pair = dict(cur.fetchone())
    record_authoring_event(
        cur,
        company_code=run["company_code"],
        draft_id=str(target_draft["draft_id"]),
        draft_revision_id=str(target_revision["draft_revision_id"]),
        run_id=str(run["run_id"]),
        event_type="bilingual_adaptation_created",
        actor_type="ai",
        to_status="ai_draft",
        payload={"translation_pair_id": str(pair["translation_pair_id"]), "published": False},
    )
    return {
        "target_draft_id": str(target_draft["draft_id"]),
        "target_revision_id": str(target_revision["draft_revision_id"]),
        "translation_pair_id": str(pair["translation_pair_id"]),
        "answer_key_invariant": True,
        "scoring_invariant": True,
    }


def enqueue_bilingual_review(
    cur: Any,
    *,
    company_code: str,
    translation_pair_id: str,
    actor_user_id: str,
    environment: str,
) -> dict[str, Any]:
    cur.execute(
        """
        SELECT p.*,sr.content_json AS source_content,tr.content_json AS target_content
        FROM assessment_translation_pairs p
        JOIN assessment_item_draft_revisions sr ON sr.draft_revision_id=p.source_revision_id
        JOIN assessment_item_draft_revisions tr ON tr.draft_revision_id=p.target_revision_id
        WHERE p.translation_pair_id=%s AND p.company_code=%s
        """,
        (translation_pair_id, str(company_code).upper()),
    )
    pair = _dict(cur.fetchone())
    if not pair:
        raise AssessmentAIError("translation_pair_not_found", "Translation pair was not found.", status_code=404)
    input_payload = {
        "schema_version": contracts.SCHEMA_VERSION,
        "translation_pair_id": str(pair["translation_pair_id"]),
        "source_sha256": pair["source_sha256"],
        "target_sha256": pair["target_sha256"],
        "source_locale": pair["source_locale"],
        "target_locale": pair["target_locale"],
        "source": pair["source_content"],
        "target": pair["target_content"],
        "review_dimensions": [
            "semantic_equivalence",
            "answer_key_invariance",
            "linguistic_naturalness",
            "rtl_punctuation_numerals",
            "cultural_fairness",
            "difficulty_drift",
        ],
    }
    return enqueue_run(
        cur,
        company_code=company_code,
        role_key="assessment.review_bilingual",
        environment=environment,
        input_payload=input_payload,
        created_by_user_id=actor_user_id,
        draft_revision_id=str(pair["target_revision_id"]),
        parent_run_id=str(pair["adaptation_run_id"]) if pair.get("adaptation_run_id") else None,
    )


def _persist_bilingual_review(cur: Any, *, run: dict[str, Any], payload: dict[str, Any]) -> None:
    pair_id = str(payload.get("translation_pair_id") or "")
    cur.execute(
        "SELECT * FROM assessment_translation_pairs WHERE translation_pair_id=%s AND company_code=%s FOR UPDATE",
        (pair_id, run["company_code"]),
    )
    pair = _dict(cur.fetchone())
    if not pair:
        raise AssessmentAIError("translation_pair_not_found", "Translation pair was not found.", status_code=404)
    if pair["source_sha256"] != payload.get("source_sha256") or pair["target_sha256"] != payload.get("target_sha256"):
        raise AssessmentAIError("translation_review_digest_mismatch", "Bilingual review is stale.", status_code=409)
    critical = any(
        finding.get("severity") == "critical" or finding.get("verdict") == "fail"
        for finding in payload.get("findings") or []
    )
    passed = payload.get("overall_recommendation") == "pass" and not critical
    cur.execute(
        """
        UPDATE assessment_translation_pairs
        SET review_run_id=%s,findings_json=%s,status=%s
        WHERE translation_pair_id=%s
        """,
        (run["run_id"], Json({**payload, "passed": passed}), "human_review" if passed else "automated_review", pair_id),
    )
    cur.execute(
        """
        SELECT tr.draft_id FROM assessment_translation_pairs p
        JOIN assessment_item_draft_revisions tr ON tr.draft_revision_id=p.target_revision_id
        WHERE p.translation_pair_id=%s
        """,
        (pair_id,),
    )
    target = _dict(cur.fetchone())
    if target:
        cur.execute(
            """
            INSERT INTO assessment_item_reviews
              (draft_id,company_code,review_type,reviewer_type,reviewer_id,
               from_status,to_status,findings_json,notes)
            VALUES (%s,%s,'bilingual_secondary_model','ai',%s,'ai_draft',%s,%s,%s)
            """,
            (
                target["draft_id"],
                run["company_code"],
                run["requested_model"],
                "automated_review" if passed else "ai_draft",
                Json({
                    **payload,
                    "passed": passed,
                    "run_id": str(run["run_id"]),
                    "registry_version_id": str(run["registry_version_id"]),
                    "prompt_version_id": str(run["prompt_version_id"]),
                }),
                "Independent bilingual findings; answer key and scoring remained server-controlled.",
            ),
        )
        if passed:
            assert_registry_qualification_gate(cur, registry_version_id=str(run["registry_version_id"]))
            cur.execute(
                """
                UPDATE assessment_item_drafts
                SET lifecycle_status='automated_review',updated_at=now()
                WHERE draft_id=%s AND current_revision_id=%s AND lifecycle_status='ai_draft'
                """,
                (target["draft_id"], pair["target_revision_id"]),
            )


def record_bilingual_human_review(
    cur: Any,
    *,
    company_code: str,
    translation_pair_id: str,
    actor_user_id: str,
    decision: str,
    notes: str | None,
    arabic_checklist: dict[str, Any] | None = None,
) -> dict[str, Any]:
    if decision not in {"approve", "rewrite", "retire"}:
        raise AssessmentAIError("invalid_bilingual_human_decision", "Bilingual decision is invalid.", status_code=422)
    cur.execute(
        """
        SELECT p.*,tr.draft_id AS target_draft_id, tr.locale AS target_locale
        FROM assessment_translation_pairs p
        JOIN assessment_item_draft_revisions tr ON tr.draft_revision_id=p.target_revision_id
        WHERE p.translation_pair_id=%s AND p.company_code=%s FOR UPDATE OF p
        """,
        (translation_pair_id, str(company_code).upper()),
    )
    pair = _dict(cur.fetchone())
    if not pair:
        raise AssessmentAIError("translation_pair_not_found", "Translation pair was not found.", status_code=404)
    if pair["status"] != "human_review":
        raise AssessmentAIError("bilingual_model_review_required", "A passed independent bilingual review is required.", status_code=409)
    target_locale = str(pair.get("target_locale") or "").lower()
    checklist_payload = dict(arabic_checklist or {})
    checklist_payload["decision"] = decision
    if decision == "approve" and target_locale.startswith("ar"):
        ok, missing = qual_gates.arabic_human_review_complete(checklist_payload)
        if not ok:
            raise AssessmentAIError(
                "arabic_human_review_checklist_required",
                "Arabic approval requires the full human Arabic quality checklist.",
                status_code=409,
                detail={"missing": missing, "required": list(qual_gates.ARABIC_HUMAN_REVIEW_CHECKLIST)},
            )
    next_status = {"approve": "approved", "rewrite": "automated_review", "retire": "retired"}[decision]
    findings = dict(pair.get("findings_json") or {})
    findings["human_review"] = {
        "decision": decision,
        "notes": notes,
        "reviewer_id": actor_user_id,
        "arabic_checklist": checklist_payload if target_locale.startswith("ar") else None,
    }
    cur.execute(
        """
        UPDATE assessment_translation_pairs
        SET status=%s,findings_json=%s,human_reviewer_id=%s,reviewed_at=now()
        WHERE translation_pair_id=%s
        RETURNING *
        """,
        (next_status, Json(findings), actor_user_id, translation_pair_id),
    )
    reviewed = dict(cur.fetchone())
    record_authoring_event(
        cur,
        company_code=company_code,
        draft_id=str(pair["target_draft_id"]),
        draft_revision_id=str(pair["target_revision_id"]),
        event_type="bilingual_human_review",
        actor_type="human",
        actor_user_id=actor_user_id,
        payload={
            "translation_pair_id": translation_pair_id,
            "decision": decision,
            "published": False,
        },
    )
    return reviewed


def product2_human_transition_ready(cur: Any, *, draft_id: str, company_code: str) -> tuple[bool, dict[str, Any]]:
    cur.execute(
        """
        SELECT d.current_revision_id,d.lifecycle_status,r.revision_kind
        FROM assessment_item_drafts d
        LEFT JOIN assessment_item_draft_revisions r ON r.draft_revision_id=d.current_revision_id
        WHERE d.draft_id=%s AND d.company_code=%s
        """,
        (draft_id, str(company_code).upper()),
    )
    draft = _dict(cur.fetchone())
    if not draft or not draft.get("current_revision_id"):
        return False, {"error": "product2_revision_required"}
    revision_id = str(draft["current_revision_id"])
    if draft.get("revision_kind") == "bilingual_adaptation":
        cur.execute(
            """
            SELECT p.status,p.findings_json,r.status AS run_status,
                   m.enabled,m.retired_at AS model_retired_at,
                   pv.retired_at AS prompt_retired_at
            FROM assessment_translation_pairs p
            LEFT JOIN assessment_ai_runs r ON r.run_id=p.review_run_id
            LEFT JOIN assessment_ai_model_registry_versions m
              ON m.registry_version_id=r.registry_version_id
            LEFT JOIN assessment_prompt_versions pv ON pv.prompt_version_id=r.prompt_version_id
            WHERE p.company_code=%s AND p.target_revision_id=%s
            ORDER BY p.created_at DESC LIMIT 1
            """,
            (str(company_code).upper(), revision_id),
        )
        pair = _dict(cur.fetchone())
        ready = bool(
            draft["lifecycle_status"] == "automated_review"
            and pair
            and pair.get("status") in {"human_review", "approved"}
            and (pair.get("findings_json") or {}).get("passed") is True
            and pair.get("run_status") == "completed"
            and pair.get("enabled") is True
            and pair.get("model_retired_at") is None
            and pair.get("prompt_retired_at") is None
        )
        return ready, {
            "bilingual_pair": pair or {},
            "bilingual_run_qualified": ready,
            "current_revision_id": revision_id,
        }
    cur.execute(
        """
        SELECT review_type,findings_json FROM assessment_item_reviews
        WHERE draft_id=%s AND review_type IN ('deterministic_product2','secondary_model')
        ORDER BY created_at DESC
        """,
        (draft_id,),
    )
    by_type: dict[str, dict[str, Any]] = {}
    for row in cur.fetchall():
        if row["review_type"] not in by_type:
            by_type[row["review_type"]] = row["findings_json"] if isinstance(row["findings_json"], dict) else {}
    deterministic = by_type.get("deterministic_product2") or {}
    secondary = by_type.get("secondary_model") or {}
    secondary_run_id = secondary.get("run_id")
    run_qualified = False
    if secondary_run_id:
        cur.execute(
            """
            SELECT r.status,m.enabled,m.retired_at AS model_retired_at,
                   p.retired_at AS prompt_retired_at
            FROM assessment_ai_runs r
            JOIN assessment_ai_model_registry_versions m
              ON m.registry_version_id=r.registry_version_id
            JOIN assessment_prompt_versions p ON p.prompt_version_id=r.prompt_version_id
            WHERE r.run_id=%s AND r.company_code=%s
            """,
            (secondary_run_id, str(company_code).upper()),
        )
        qualified = _dict(cur.fetchone())
        run_qualified = bool(
            qualified
            and qualified.get("status") == "completed"
            and qualified.get("enabled") is True
            and qualified.get("model_retired_at") is None
            and qualified.get("prompt_retired_at") is None
        )
    ready = bool(
        draft["lifecycle_status"] == "automated_review"
        and deterministic.get("passed") is True
        and secondary.get("passed") is True
        and str(deterministic.get("draft_revision_id")) == revision_id
        and str(secondary.get("draft_revision_id")) == revision_id
        and run_qualified
    )
    arabic_ready = True
    arabic_missing: list[str] = []
    cur.execute(
        """
        SELECT locale FROM assessment_item_draft_revisions WHERE draft_revision_id=%s
        """,
        (revision_id,),
    )
    locale_row = _dict(cur.fetchone()) or {}
    if str(locale_row.get("locale") or "").lower().startswith("ar"):
        # Prefer explicit Arabic checklist on the latest bilingual human review if present.
        cur.execute(
            """
            SELECT findings_json FROM assessment_translation_pairs
            WHERE company_code=%s AND target_revision_id=%s
            ORDER BY created_at DESC LIMIT 1
            """,
            (str(company_code).upper(), revision_id),
        )
        pair_findings = ((_dict(cur.fetchone()) or {}).get("findings_json") or {})
        human = (pair_findings.get("human_review") or {}) if isinstance(pair_findings, dict) else {}
        arabic_ready, arabic_missing = qual_gates.arabic_human_review_complete(human)
        ready = bool(ready and arabic_ready)
    return ready, {
        "deterministic": deterministic,
        "secondary": secondary,
        "secondary_run_qualified": run_qualified,
        "current_revision_id": revision_id,
        "arabic_human_review_ready": arabic_ready,
        "arabic_human_review_missing": arabic_missing,
    }


def create_human_rewrite_revision(
    cur: Any,
    *,
    draft_id: str,
    company_code: str,
    content: dict[str, Any],
    actor_user_id: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    cur.execute(
        """
        SELECT d.*,r.revision,r.draft_revision_id AS parent_revision_id
        FROM assessment_item_drafts d
        JOIN assessment_item_draft_revisions r ON r.draft_revision_id=d.current_revision_id
        WHERE d.draft_id=%s AND d.company_code=%s FOR UPDATE OF d
        """,
        (draft_id, str(company_code).upper()),
    )
    draft = _dict(cur.fetchone())
    if not draft:
        raise AssessmentAIError("assessment_item_draft_not_found", "Draft was not found.", status_code=404)
    if draft.get("lifecycle_status") in {"approved", "retired"}:
        raise AssessmentAIError(
            "immutable_approved_revision",
            "Approved or retired Product-2 revisions cannot be rewritten; create a new draft lineage.",
            status_code=409,
        )
    normalized = normalize_item_content(content)
    content_hash = sha256_json(normalized)
    cur.execute(
        """
        INSERT INTO assessment_item_draft_revisions
          (draft_id,company_code,revision,parent_revision_id,revision_kind,
           content_json,content_sha256,locale,answer_key_id,compiled_scoring_json,
           compiled_scoring_sha256,created_by_actor_type,created_by_user_id)
        VALUES (%s,%s,%s,%s,'human_rewrite',%s,%s,%s,%s,%s,%s,'human',%s)
        RETURNING *
        """,
        (
            draft_id,
            str(company_code).upper(),
            int(draft["revision"]) + 1,
            draft["parent_revision_id"],
            Json(normalized),
            content_hash,
            normalized["locale"],
            normalized["proposed_answer_key"],
            Json(normalized["compiled_scoring"]),
            normalized["compiled_scoring_sha256"],
            actor_user_id,
        ),
    )
    revision = dict(cur.fetchone())
    cur.execute(
        """
        UPDATE assessment_item_drafts
        SET current_revision_id=%s,lifecycle_status='ai_draft',prompt_text=%s,
            choices=%s,proposed_answer_key=%s,proposed_scoring=%s,rationale=%s,
            explanation=%s,updated_at=now()
        WHERE draft_id=%s RETURNING *
        """,
        (
            revision["draft_revision_id"],
            normalized["prompt_text"],
            Json(normalized["choices"]),
            normalized["proposed_answer_key"],
            Json(normalized["proposed_scoring"]),
            normalized["rationale"],
            normalized["explanation"],
            draft_id,
        ),
    )
    updated = dict(cur.fetchone())
    record_authoring_event(
        cur,
        company_code=company_code,
        draft_id=draft_id,
        draft_revision_id=str(revision["draft_revision_id"]),
        event_type="human_rewrite_created",
        actor_type="human",
        actor_user_id=actor_user_id,
        from_status=str(draft["lifecycle_status"]),
        to_status="ai_draft",
        payload={"content_sha256": content_hash, "prior_reviews_invalidated": True, "published": False},
    )
    return updated, revision


def authoring_status(cur: Any, *, company_code: str) -> dict[str, Any]:
    cur.execute(
        """
        SELECT DISTINCT ON (role_key)
               registry_version_id,role_key,version,provider,requested_model,api_kind,enabled,
               qualified_provider_model_id,output_schema_name,
               output_schema_version,activated_at,retired_at
        FROM assessment_ai_model_registry_versions
        ORDER BY role_key,version DESC
        """
    )
    roles = [dict(row) for row in cur.fetchall()]
    cur.execute(
        """
        SELECT lifecycle_status,COUNT(*)::int AS count
        FROM assessment_item_drafts WHERE company_code=%s
        GROUP BY lifecycle_status ORDER BY lifecycle_status
        """,
        (str(company_code).upper(),),
    )
    counts = {row["lifecycle_status"]: int(row["count"]) for row in cur.fetchall()}
    return {
        "product_version": PRODUCT_VERSION,
        "global_flag": False,
        "production_hard_off": True,
        "publish_available": False,
        "live_scoring_ai_calls": False,
        "model_roles": roles,
        "draft_counts": counts,
    }
