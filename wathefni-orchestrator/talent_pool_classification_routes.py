"""Flag-gated HTTP routes for Talent Pool Classification (local/manual phase).

Does not start background workers. Does not mutate lifecycle/Jobs/outreach.
Mount only when schema/manual/UI flags allow; production workers stay OFF.
"""

from __future__ import annotations

from typing import Any

from fastapi import Depends, HTTPException, Query

import talent_pool_classification as tpc


def require_classification_tenant(context: dict[str, Any]) -> str:
    company = str(context.get("company_code") or "").strip().upper()
    if not tpc.feature_enabled_for_company(company):
        raise HTTPException(
            status_code=404,
            detail={
                "error": "talent_pool_classification_disabled",
                "status": tpc.feature_status(company),
            },
        )
    return company


def require_manual_or_schema() -> None:
    if not (tpc.feature_manual_enabled() or tpc.feature_schema_enabled()):
        raise HTTPException(status_code=404, detail={"error": "classification_execution_disabled"})
    tpc.assert_workers_disabled_for_local()


def mount_talent_pool_classification_routes(app_mod: Any) -> None:
    app = app_mod.app

    @app.get("/dashboard/prehire/classification/feature")
    def classification_feature(context: dict[str, Any] = Depends(app_mod.prehire_dashboard_context)):
        company = str(context.get("company_code") or "").strip().upper()
        return {"ok": True, **tpc.feature_status(company)}

    @app.get("/dashboard/prehire/classification/taxonomy")
    def classification_taxonomy(context: dict[str, Any] = Depends(app_mod.prehire_dashboard_context)):
        company = require_classification_tenant(context)
        if not tpc.feature_schema_enabled() and not tpc.feature_ui_enabled():
            raise HTTPException(status_code=404, detail={"error": "classification_schema_disabled"})
        pack = tpc.load_taxonomy_pack()
        tenant_nodes: list[dict[str, Any]] = []
        with app_mod.db_connect() as conn:
            with conn.cursor() as cur:
                tpc.ensure_classification_schema(cur)
                tpc.seed_global_taxonomy(cur, pack)
                try:
                    cur.execute(
                        "SELECT * FROM taxonomy_tenant_nodes WHERE company_code=%s AND status='active'",
                        (company,),
                    )
                    tenant_nodes = [dict(r) for r in cur.fetchall()]
                except Exception:
                    tenant_nodes = []
                conn.commit()
        dimensions = tpc.taxonomy_dimensions(pack, tenant_nodes=tenant_nodes)
        return {
            "ok": True,
            "taxonomy_version": pack.get("taxonomy_version"),
            "nodes": pack.get("nodes") or [],
            "tenant_nodes": tenant_nodes,
            **dimensions,
        }

    @app.get("/dashboard/prehire/applications/{app_key}/classification")
    def get_classification(
        app_key: str,
        runs_offset: int = Query(default=0, ge=0),
        runs_limit: int = Query(default=20, ge=1, le=100),
        context: dict[str, Any] = Depends(app_mod.prehire_dashboard_context),
    ):
        company = require_classification_tenant(context)
        if not tpc.feature_ui_enabled() and not tpc.feature_schema_enabled():
            raise HTTPException(status_code=404, detail={"error": "classification_ui_disabled"})
        with app_mod.db_connect() as conn:
            with conn.cursor() as cur:
                tpc.ensure_classification_schema(cur)
                cur.execute(
                    """
                    SELECT count(*) AS count
                    FROM candidate_classification_runs
                    WHERE company_code=%s AND app_key=%s
                    """,
                    (company, app_key),
                )
                runs_total = int(cur.fetchone()["count"])
                cur.execute(
                    """
                    SELECT *
                    FROM candidate_classification_runs
                    WHERE company_code=%s AND app_key=%s
                    ORDER BY created_at DESC
                    OFFSET %s LIMIT %s
                    """,
                    (company, app_key, runs_offset, runs_limit),
                )
                runs = [dict(r) for r in cur.fetchall()]
                cur.execute(
                    """
                    SELECT i.*
                    FROM candidate_classification_run_invalidations i
                    JOIN candidate_classification_runs r
                      ON r.company_code=i.company_code AND r.run_id=i.run_id
                    WHERE i.company_code=%s AND r.app_key=%s
                    ORDER BY i.created_at DESC
                    """,
                    (company, app_key),
                )
                invalidations = [dict(r) for r in cur.fetchall()]
                invalidations_by_run: dict[str, list[dict[str, Any]]] = {}
                for invalidation in invalidations:
                    invalidations_by_run.setdefault(
                        str(invalidation.get("run_id") or ""), []
                    ).append(invalidation)
                for run in runs:
                    run_invalidations = invalidations_by_run.get(
                        str(run.get("run_id") or ""), []
                    )
                    run["invalidated"] = bool(run_invalidations)
                    run["invalidations"] = run_invalidations
                current_run = next(
                    (item for item in runs if not item.get("invalidated")),
                    None,
                )
                cur.execute(
                    """
                    SELECT *
                    FROM candidate_classification_suggestions
                    WHERE company_code=%s AND app_key=%s
                    ORDER BY created_at DESC
                    """,
                    (company, app_key),
                )
                all_suggestions = [dict(r) for r in cur.fetchall()]
                invalidated_run_ids = set(invalidations_by_run)
                if current_run:
                    suggestions = [
                        item
                        for item in all_suggestions
                        if str(item.get("run_id") or "") not in invalidated_run_ids
                        and (
                            str(item.get("run_id")) == str(current_run.get("run_id"))
                            or item.get("state") == tpc.STATE_ACTIVE
                        )
                    ]
                    # Prefer exact current-run suggestions when present.
                    current_only = [
                        item
                        for item in all_suggestions
                        if str(item.get("run_id")) == str(current_run.get("run_id"))
                        and str(item.get("run_id") or "") not in invalidated_run_ids
                    ]
                    if current_only:
                        suggestions = current_only
                else:
                    suggestions = [
                        item
                        for item in all_suggestions
                        if item.get("state") == tpc.STATE_ACTIVE
                        and str(item.get("run_id") or "") not in invalidated_run_ids
                    ]
                cur.execute(
                    """
                    SELECT *
                    FROM candidate_classification_review_events
                    WHERE company_code=%s AND app_key=%s
                    ORDER BY created_at ASC
                    """,
                    (company, app_key),
                )
                events = [dict(r) for r in cur.fetchall()]
                conn.commit()
        section = tpc.profile_classification_section(
            run=current_run,
            suggestions=suggestions,
            review_events=events,
            runs=runs,
            runs_total=runs_total,
            runs_offset=runs_offset,
            runs_limit=runs_limit,
            invalidations=invalidations,
        )
        return {"ok": True, "classification": section}

    @app.post("/dashboard/prehire/applications/{app_key}/classification/run")
    def run_classification(app_key: str, body: dict[str, Any], context: dict[str, Any] = Depends(app_mod.prehire_dashboard_context)):
        app_mod.require_entitlement(context, "pre_hiring", "candidate.manage")
        company = require_classification_tenant(context)
        require_manual_or_schema()
        if tpc.feature_workers_enabled():
            raise HTTPException(
                status_code=409,
                detail={
                    "error": "workers_forbidden_in_this_phase",
                    "message": "Manual classification is unavailable while classification workers are active.",
                },
            )
        # Load stored artifacts only — never OCR
        with app_mod.db_connect() as conn:
            with conn.cursor() as cur:
                tpc.ensure_classification_schema(cur)
                pack_version = tpc.seed_global_taxonomy(cur)
                cur.execute(
                    """
                    SELECT a.app_key, a.raw_json, c.profile AS candidate_profile,
                           sd.content AS semantic_content
                    FROM applications a
                    LEFT JOIN candidates c ON c.phone=a.phone
                    LEFT JOIN semantic_documents sd ON sd.entity_type='application' AND sd.entity_key=a.app_key
                    WHERE a.company_code=%s AND a.app_key=%s
                    LIMIT 1
                    """,
                    (company, app_key),
                )
                row = cur.fetchone()
                if not row:
                    raise HTTPException(
                        status_code=404,
                        detail={"error": "application_not_found", "message": "We couldn't find that candidate."},
                    )
                document_version_id = str(body.get("document_version_id") or "current")
                extraction_version_id = str(body.get("extraction_version_id") or "current")
                facts = row.get("candidate_profile") if isinstance(row.get("candidate_profile"), dict) else {}
                raw_json = row.get("raw_json") if isinstance(row.get("raw_json"), dict) else {}
                # Prefer stored normalized CV text; fall back to semantic content. Never OCR.
                cv_text = str(
                    raw_json.get("normalized_cv_text")
                    or raw_json.get("cv_text")
                    or row.get("semantic_content")
                    or ""
                )
                if not facts and isinstance(row.get("candidate_profile"), dict):
                    facts = row.get("candidate_profile") or {}
                bundle = tpc.build_input_bundle(
                    cv_text=cv_text,
                    facts=facts,
                    hr_confirmed_facts=body.get("hr_confirmed_facts") if isinstance(body.get("hr_confirmed_facts"), dict) else {},
                    document_version_id=document_version_id,
                    extraction_version_id=extraction_version_id,
                    completeness=body.get("completeness") if isinstance(body.get("completeness"), list) else [],
                    embedding_present=bool(row.get("semantic_content")),
                )
                result = tpc.run_manual_classification(
                    company_code=company,
                    app_key=app_key,
                    bundle=bundle,
                )
                persisted = tpc.persist_classification_run(
                    cur,
                    company_code=company,
                    app_key=app_key,
                    bundle=bundle,
                    result=result,
                    document_version_id=document_version_id,
                    extraction_version_id=extraction_version_id,
                )
                job = tpc.enqueue_classification_job(
                    cur,
                    company_code=company,
                    app_key=app_key,
                    idempotency_key_value=persisted["idempotency_key"],
                    payload={"run_id": persisted["run_id"], "mode": "manual"},
                )
                cur.execute(
                    """
                    UPDATE talent_pool_classification_jobs
                    SET status='completed_manual', updated_at=now()
                    WHERE job_id=%s
                    """,
                    (job["job_id"],),
                )
                conn.commit()
        app_mod.record_admin_audit(
            context,
            "candidate_classification_run",
            summary="Ran manual candidate classification.",
            target_type="application",
            target=app_key,
            details={
                "run_id": str(persisted.get("run_id") or ""),
                "job_id": str(job.get("job_id") or ""),
                "taxonomy_version": pack_version,
            },
        )
        return {
            "ok": True,
            "taxonomy_version": pack_version,
            "result": result,
            "persisted": persisted,
            "job": {**job, "status": "completed_manual"},
            "workers_started": False,
            "ocr_triggered": False,
            "lifecycle_mutated": False,
        }

    @app.post("/dashboard/prehire/applications/{app_key}/classification/review")
    def review_classification(app_key: str, body: dict[str, Any], context: dict[str, Any] = Depends(app_mod.prehire_dashboard_context)):
        app_mod.require_entitlement(context, "pre_hiring", "candidate.manage")
        company = require_classification_tenant(context)
        if not tpc.feature_ui_enabled() and not tpc.feature_manual_enabled():
            raise HTTPException(
                status_code=404,
                detail={
                    "error": "classification_review_disabled",
                    "message": "Classification review is not enabled for this company.",
                },
            )
        action = str(body.get("action") or "").strip().lower()
        node_id = str(body.get("node_id") or "").strip()
        if action not in tpc.REVIEW_ACTIONS:
            raise HTTPException(
                status_code=422,
                detail={
                    "error": "invalid_classification_review_action",
                    "message": "Choose a valid classification review action.",
                },
            )
        if action == "correct" and not body.get("previous_node_id"):
            raise HTTPException(
                status_code=422,
                detail={
                    "error": "previous_node_id_required_for_correct",
                    "message": "Choose the classification being corrected.",
                },
            )
        if action == "add" and not node_id:
            raise HTTPException(
                status_code=422,
                detail={
                    "error": "node_id_required_for_add",
                    "message": "Choose a classification to add.",
                },
            )
        with app_mod.db_connect() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT 1 FROM applications WHERE company_code=%s AND app_key=%s LIMIT 1",
                    (company, app_key),
                )
                if not cur.fetchone():
                    raise HTTPException(
                        status_code=404,
                        detail={"error": "application_not_found", "message": "We couldn't find that candidate."},
                    )
                conn.commit()
        pack = tpc.load_taxonomy_pack()
        index = tpc.taxonomy_index(pack)
        node = index.get(node_id) or {}
        access = context.get("access") if isinstance(context.get("access"), dict) else {}
        access_user = access.get("user") if isinstance(access.get("user"), dict) else {}
        hr_user = context.get("hr_user") if isinstance(context.get("hr_user"), dict) else {}
        event = tpc.append_review_event(
            action=action,
            node_id=node_id,
            actor_user_id=str(
                context.get("actor_user_id")
                or hr_user.get("user_id")
                or access_user.get("user_id")
                or ""
            ),
            actor_email=str(hr_user.get("email") or access_user.get("email") or ""),
            suggestion_id=body.get("suggestion_id"),
            previous_node_id=body.get("previous_node_id"),
            reason=body.get("reason"),
            node_type=body.get("node_type") or node.get("node_type"),
            label_en=body.get("label_en") or node.get("label_en"),
            label_ar=body.get("label_ar") or node.get("label_ar"),
            supersedes_event_id=body.get("supersedes_event_id"),
        )
        if body.get("preview") and not body.get("confirm"):
            return {"ok": True, "preview": True, "event": event, "message": "Preview only — confirm to append."}
        if not body.get("confirm"):
            raise HTTPException(
                status_code=422,
                detail={"error": "confirm_required", "message": "Review the change, then confirm it."},
            )
        with app_mod.db_connect() as conn:
            with conn.cursor() as cur:
                tpc.ensure_classification_schema(cur)
                cur.execute(
                    """
                    INSERT INTO candidate_classification_review_events(
                      event_id, company_code, app_key, action, node_id, previous_node_id,
                      suggestion_id, reason, actor_user_id, actor_email, supersedes_event_id,
                      node_type, label_en, label_ar
                    ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                    """,
                    (
                        event["event_id"],
                        company,
                        app_key,
                        event["action"],
                        event["node_id"],
                        event.get("previous_node_id"),
                        event.get("suggestion_id"),
                        event.get("reason"),
                        event.get("actor_user_id"),
                        event.get("actor_email"),
                        event.get("supersedes_event_id"),
                        event.get("node_type"),
                        event.get("label_en"),
                        event.get("label_ar"),
                    ),
                )
                conn.commit()
        app_mod.record_admin_audit(
            context,
            "candidate_classification_reviewed",
            summary="Recorded a human classification review.",
            target_type="application",
            target=app_key,
            details={
                "event_id": event["event_id"],
                "action": event["action"],
                "node_id": event["node_id"],
                "previous_node_id": event.get("previous_node_id"),
            },
        )
        return {"ok": True, "preview": False, "event": event}
