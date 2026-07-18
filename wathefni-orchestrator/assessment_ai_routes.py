"""Dashboard routes for Assessment Product-2 authoring.

No publish route exists here.  All endpoints are gated by the existing
non-production authoring kill switch and assessment.manage entitlement.
"""

from __future__ import annotations

import os
from typing import Any, Literal

from fastapi import Depends, HTTPException, Query
from pydantic import BaseModel, Field

import assessment_ai_service as service


class BlueprintCreateRequest(BaseModel):
    blueprint_key: str = Field(min_length=1, max_length=120)
    blueprint: dict[str, Any]
    approve: bool = False


class GenerateItemsRequest(BaseModel):
    blueprint_version_id: str = Field(min_length=1, max_length=200)
    requested_item_count: int = Field(default=1, ge=1, le=20)


class ManualDraftRequest(BaseModel):
    blueprint_version_id: str = Field(min_length=1, max_length=200)
    content: dict[str, Any]


class AdaptDraftRequest(BaseModel):
    target_locale: Literal["en", "ar"]


class HumanRewriteRequest(BaseModel):
    content: dict[str, Any]


class RegistryActivationRequest(BaseModel):
    qualification_eval_run_id: str = Field(min_length=1, max_length=200)


class BilingualHumanReviewRequest(BaseModel):
    decision: Literal["approve", "rewrite", "retire"]
    notes: str | None = Field(default=None, max_length=4000)
    arabic_checklist: dict[str, bool] | None = None


class EvalRunRecordRequest(BaseModel):
    eval_corpus_version: str = Field(min_length=1, max_length=120)
    gate_profile_version: str = Field(min_length=1, max_length=120)
    role_key: str = Field(min_length=1, max_length=120)
    registry_version_id: str = Field(min_length=1, max_length=200)
    prompt_version_id: str = Field(min_length=1, max_length=200)
    mode: Literal["recorded_replay", "live_staging", "blinded_compare", "prompt_regression"]
    artifact_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    metrics: dict[str, Any]
    passed: bool


def _http_error(exc: service.AssessmentAIError) -> HTTPException:
    return HTTPException(
        status_code=exc.status_code,
        detail={"error": exc.code, "message": exc.message, **exc.detail},
    )


def register_assessment_ai_routes(app: Any, legacy: Any) -> None:
    # Registration occurs before the assessment-specific dependency is defined
    # in the legacy monolith; the shared context has the same authenticated
    # tenant identity and each handler applies the stricter authoring gate.
    authoring_context = legacy.dashboard_context

    @app.get("/dashboard/prehire/assessments/authoring/product2/status")
    def product2_status(
        context: dict[str, Any] = Depends(authoring_context),
    ):
        legacy.require_assessment_authoring_access(context)
        with legacy.db_connect() as conn:
            with conn.cursor() as cur:
                payload = service.authoring_status(cur, company_code=context["company_code"])
        payload["global_flag"] = (
            os.environ.get("WATHEFNI_ASSESSMENT_AUTHORING", "").strip().lower()
            in {"1", "true", "yes", "on", "enabled"}
        )
        payload["environment"] = str(os.environ.get("WATHEFNI_ENV") or "").lower()
        return payload

    @app.post("/dashboard/prehire/assessments/authoring/product2/model-registry/{registry_version_id}/activate")
    def activate_model_registry(
        registry_version_id: str,
        request: RegistryActivationRequest,
        context: dict[str, Any] = Depends(authoring_context),
    ):
        legacy.require_assessment_authoring_access(context)
        legacy.require_entitlement(context, "assessments", "settings.manage")
        actor_id = legacy.assessment_dashboard_actor_id(context)
        try:
            with legacy.db_connect() as conn:
                with conn.cursor() as cur:
                    activated = service.activate_model_registry_version(
                        cur,
                        registry_version_id=registry_version_id,
                        qualification_eval_run_id=request.qualification_eval_run_id,
                        actor_user_id=actor_id,
                    )
                conn.commit()
        except service.AssessmentAIError as exc:
            raise _http_error(exc) from exc
        return {
            "ok": True,
            "model_registry_version": legacy.json_safe(activated),
            "human_approved": True,
            "publish_available": False,
        }

    @app.post("/dashboard/prehire/assessments/authoring/product2/eval-runs")
    def record_eval_run(
        request: EvalRunRecordRequest,
        context: dict[str, Any] = Depends(authoring_context),
    ):
        legacy.require_assessment_authoring_access(context)
        legacy.require_entitlement(context, "assessments", "settings.manage")
        actor_id = legacy.assessment_dashboard_actor_id(context)
        try:
            with legacy.db_connect() as conn:
                with conn.cursor() as cur:
                    eval_run = service.record_eval_run(
                        cur,
                        company_code=context["company_code"],
                        eval_corpus_version=request.eval_corpus_version,
                        gate_profile_version=request.gate_profile_version,
                        role_key=request.role_key,
                        registry_version_id=request.registry_version_id,
                        prompt_version_id=request.prompt_version_id,
                        mode=request.mode,
                        artifact_sha256=request.artifact_sha256,
                        metrics=request.metrics,
                        passed=request.passed,
                        actor_user_id=actor_id,
                        environment=str(os.environ.get("WATHEFNI_ENV") or "").lower(),
                    )
                conn.commit()
        except service.AssessmentAIError as exc:
            raise _http_error(exc) from exc
        return {
            "ok": True,
            "eval_run": legacy.json_safe(eval_run),
            "model_activated": False,
            "publish_available": False,
        }

    @app.post("/dashboard/prehire/assessments/authoring/product2/blueprints")
    def create_blueprint(
        request: BlueprintCreateRequest,
        context: dict[str, Any] = Depends(authoring_context),
    ):
        legacy.require_assessment_authoring_access(context)
        actor_id = legacy.assessment_dashboard_actor_id(context)
        try:
            with legacy.db_connect() as conn:
                with conn.cursor() as cur:
                    blueprint = service.create_blueprint_version(
                        cur,
                        company_code=context["company_code"],
                        blueprint_key=request.blueprint_key,
                        blueprint=request.blueprint,
                        created_by_user_id=actor_id,
                        approve=request.approve,
                        approved_by_user_id=actor_id if request.approve else None,
                    )
                conn.commit()
        except service.AssessmentAIError as exc:
            raise _http_error(exc) from exc
        return {
            "ok": True,
            "blueprint": legacy.json_safe(blueprint),
            "publish_available": False,
        }

    @app.get("/dashboard/prehire/assessments/authoring/product2/blueprints")
    def list_blueprints(
        status: str | None = None,
        limit: int = Query(default=50, ge=1, le=200),
        context: dict[str, Any] = Depends(authoring_context),
    ):
        legacy.require_assessment_authoring_access(context)
        where = ["company_code=%s"]
        params: list[Any] = [context["company_code"]]
        if status:
            where.append("status=%s")
            params.append(status)
        with legacy.db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    f"""
                    SELECT * FROM assessment_blueprint_versions
                    WHERE {' AND '.join(where)}
                    ORDER BY blueprint_key,version DESC LIMIT %s
                    """,
                    [*params, limit],
                )
                rows = [legacy.json_safe(dict(row)) for row in cur.fetchall()]
        return {"ok": True, "blueprints": rows, "publish_available": False}

    @app.post("/dashboard/prehire/assessments/authoring/product2/generate")
    def generate_items(
        request: GenerateItemsRequest,
        context: dict[str, Any] = Depends(authoring_context),
    ):
        legacy.require_assessment_authoring_access(context)
        actor_id = legacy.assessment_dashboard_actor_id(context)
        environment = str(os.environ.get("WATHEFNI_ENV") or "").lower()
        try:
            with legacy.db_connect() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        SELECT * FROM assessment_blueprint_versions
                        WHERE blueprint_version_id=%s AND company_code=%s AND status='approved'
                        """,
                        (request.blueprint_version_id, context["company_code"]),
                    )
                    blueprint = cur.fetchone()
                    if not blueprint:
                        raise service.AssessmentAIError(
                            "approved_blueprint_required",
                            "An approved, tenant-scoped blueprint is required.",
                            status_code=409,
                        )
                    input_payload = service.build_authoring_request(
                        dict(blueprint),
                        requested_item_count=request.requested_item_count,
                    )
                    run = service.enqueue_run(
                        cur,
                        company_code=context["company_code"],
                        role_key="assessment.author_primary",
                        environment=environment,
                        input_payload=input_payload,
                        created_by_user_id=actor_id,
                        blueprint_version_id=request.blueprint_version_id,
                    )
                conn.commit()
        except service.AssessmentAIError as exc:
            raise _http_error(exc) from exc
        return {
            "ok": True,
            "run": legacy.json_safe(run),
            "queued": run.get("status") == "queued",
            "publish_available": False,
        }

    @app.post("/dashboard/prehire/assessments/authoring/product2/manual-drafts")
    def create_manual_draft(
        request: ManualDraftRequest,
        context: dict[str, Any] = Depends(authoring_context),
    ):
        legacy.require_assessment_authoring_access(context)
        actor_id = legacy.assessment_dashboard_actor_id(context)
        try:
            with legacy.db_connect() as conn:
                with conn.cursor() as cur:
                    draft, revision = service.create_manual_product2_draft(
                        cur,
                        company_code=context["company_code"],
                        blueprint_version_id=request.blueprint_version_id,
                        content=request.content,
                        actor_user_id=actor_id,
                    )
                conn.commit()
        except service.AssessmentAIError as exc:
            raise _http_error(exc) from exc
        return {
            "ok": True,
            "draft": legacy.json_safe(draft),
            "revision": legacy.json_safe(revision),
            "ai_used": False,
            "publish_available": False,
        }

    @app.post("/dashboard/prehire/assessments/authoring/product2/drafts/{draft_id}/secondary-review")
    def enqueue_secondary_review(
        draft_id: str,
        context: dict[str, Any] = Depends(authoring_context),
    ):
        legacy.require_assessment_authoring_access(context)
        actor_id = legacy.assessment_dashboard_actor_id(context)
        try:
            with legacy.db_connect() as conn:
                with conn.cursor() as cur:
                    run = service.enqueue_secondary_review(
                        cur,
                        company_code=context["company_code"],
                        draft_id=draft_id,
                        actor_user_id=actor_id,
                        environment=str(os.environ.get("WATHEFNI_ENV") or "").lower(),
                    )
                conn.commit()
        except service.AssessmentAIError as exc:
            raise _http_error(exc) from exc
        return {"ok": True, "run": legacy.json_safe(run), "publish_available": False}

    @app.post("/dashboard/prehire/assessments/authoring/product2/drafts/{draft_id}/adapt")
    def enqueue_adaptation(
        draft_id: str,
        request: AdaptDraftRequest,
        context: dict[str, Any] = Depends(authoring_context),
    ):
        legacy.require_assessment_authoring_access(context)
        actor_id = legacy.assessment_dashboard_actor_id(context)
        try:
            with legacy.db_connect() as conn:
                with conn.cursor() as cur:
                    run = service.enqueue_bilingual_adaptation(
                        cur,
                        company_code=context["company_code"],
                        draft_id=draft_id,
                        target_locale=request.target_locale,
                        actor_user_id=actor_id,
                        environment=str(os.environ.get("WATHEFNI_ENV") or "").lower(),
                    )
                conn.commit()
        except service.AssessmentAIError as exc:
            raise _http_error(exc) from exc
        return {"ok": True, "run": legacy.json_safe(run), "publish_available": False}

    @app.post("/dashboard/prehire/assessments/authoring/product2/translation-pairs/{translation_pair_id}/review")
    def enqueue_translation_review(
        translation_pair_id: str,
        context: dict[str, Any] = Depends(authoring_context),
    ):
        legacy.require_assessment_authoring_access(context)
        actor_id = legacy.assessment_dashboard_actor_id(context)
        try:
            with legacy.db_connect() as conn:
                with conn.cursor() as cur:
                    run = service.enqueue_bilingual_review(
                        cur,
                        company_code=context["company_code"],
                        translation_pair_id=translation_pair_id,
                        actor_user_id=actor_id,
                        environment=str(os.environ.get("WATHEFNI_ENV") or "").lower(),
                    )
                conn.commit()
        except service.AssessmentAIError as exc:
            raise _http_error(exc) from exc
        return {"ok": True, "run": legacy.json_safe(run), "publish_available": False}

    @app.post("/dashboard/prehire/assessments/authoring/product2/translation-pairs/{translation_pair_id}/human-review")
    def bilingual_human_review(
        translation_pair_id: str,
        request: BilingualHumanReviewRequest,
        context: dict[str, Any] = Depends(authoring_context),
    ):
        legacy.require_assessment_authoring_access(context)
        actor_id = legacy.assessment_dashboard_actor_id(context)
        try:
            with legacy.db_connect() as conn:
                with conn.cursor() as cur:
                    pair = service.record_bilingual_human_review(
                        cur,
                        company_code=context["company_code"],
                        translation_pair_id=translation_pair_id,
                        actor_user_id=actor_id,
                        decision=request.decision,
                        notes=request.notes,
                        arabic_checklist=request.arabic_checklist,
                    )
                conn.commit()
        except service.AssessmentAIError as exc:
            raise _http_error(exc) from exc
        return {
            "ok": True,
            "translation_pair": legacy.json_safe(pair),
            "human_reviewed": True,
            "publish_available": False,
        }

    @app.post("/dashboard/prehire/assessments/authoring/product2/drafts/{draft_id}/rewrite")
    def human_rewrite(
        draft_id: str,
        request: HumanRewriteRequest,
        context: dict[str, Any] = Depends(authoring_context),
    ):
        legacy.require_assessment_authoring_access(context)
        actor_id = legacy.assessment_dashboard_actor_id(context)
        try:
            with legacy.db_connect() as conn:
                with conn.cursor() as cur:
                    draft, revision = service.create_human_rewrite_revision(
                        cur,
                        draft_id=draft_id,
                        company_code=context["company_code"],
                        content=request.content,
                        actor_user_id=actor_id,
                    )
                conn.commit()
        except service.AssessmentAIError as exc:
            raise _http_error(exc) from exc
        return {
            "ok": True,
            "draft": legacy.json_safe(draft),
            "revision": legacy.json_safe(revision),
            "prior_reviews_invalidated": True,
            "publish_available": False,
        }

    @app.get("/dashboard/prehire/assessments/authoring/product2/drafts/{draft_id}/evidence")
    def draft_evidence(
        draft_id: str,
        context: dict[str, Any] = Depends(authoring_context),
    ):
        legacy.require_assessment_authoring_access(context)
        with legacy.db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT d.*,r.content_json,r.content_sha256,r.revision,
                           r.compiled_scoring_sha256
                    FROM assessment_item_drafts d
                    LEFT JOIN assessment_item_draft_revisions r
                      ON r.draft_revision_id=d.current_revision_id
                    WHERE d.draft_id=%s AND d.company_code=%s
                    """,
                    (draft_id, context["company_code"]),
                )
                draft = cur.fetchone()
                if not draft:
                    raise HTTPException(status_code=404, detail={"error": "assessment_item_draft_not_found"})
                cur.execute(
                    """
                    SELECT * FROM assessment_item_draft_revisions
                    WHERE draft_id=%s AND company_code=%s ORDER BY revision DESC
                    """,
                    (draft_id, context["company_code"]),
                )
                revisions = [legacy.json_safe(dict(row)) for row in cur.fetchall()]
                cur.execute(
                    """
                    SELECT * FROM assessment_item_reviews
                    WHERE draft_id=%s AND company_code=%s ORDER BY created_at DESC
                    """,
                    (draft_id, context["company_code"]),
                )
                reviews = [legacy.json_safe(dict(row)) for row in cur.fetchall()]
                cur.execute(
                    """
                    SELECT * FROM assessment_authoring_events
                    WHERE draft_id=%s AND company_code=%s ORDER BY created_at DESC
                    """,
                    (draft_id, context["company_code"]),
                )
                events = [legacy.json_safe(dict(row)) for row in cur.fetchall()]
        return {
            "ok": True,
            "draft": legacy.json_safe(dict(draft)),
            "revisions": revisions,
            "reviews": reviews,
            "events": events,
            "publish_available": False,
        }

    @app.get("/dashboard/prehire/assessments/authoring/product2/runs/{run_id}")
    def run_status(
        run_id: str,
        context: dict[str, Any] = Depends(authoring_context),
    ):
        legacy.require_assessment_authoring_access(context)
        with legacy.db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT * FROM assessment_ai_runs WHERE run_id=%s AND company_code=%s",
                    (run_id, context["company_code"]),
                )
                row = cur.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail={"error": "assessment_ai_run_not_found"})
        return {"ok": True, "run": legacy.json_safe(dict(row)), "publish_available": False}
