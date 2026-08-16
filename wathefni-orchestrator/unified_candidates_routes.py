"""HTTP routes for Unified Candidates + Talent Pool (flag-gated).

Mounted surgically onto staging/production FastAPI app without replacing
C0–C3 collaboration / ranking surfaces.

Important: resolve app_mod helpers lazily inside handlers — mount may run
while app.py is still importing.
"""

from __future__ import annotations

from typing import Any

from fastapi import Depends, HTTPException

import unified_candidates as uc


def require_unified(context: dict[str, Any]) -> None:
    company = str(context.get("company_code") or "").strip().upper()
    if not uc.feature_enabled_for_company(company):
        raise HTTPException(
            status_code=404,
            detail={
                "error": "unified_candidates_disabled",
                "flag": uc.FEATURE_FLAG,
                "company_code": company,
                "status": uc.feature_status(company),
            },
        )


def mount_unified_candidate_routes(app_mod: Any) -> None:
    """Register flag-gated routes on an already-constructed FastAPI app module."""
    app = app_mod.app

    def prehire_dashboard_context():
        raise RuntimeError("prehire_dashboard_context placeholder")

    # Capture Depends callable by attribute lookup at request time via wrapper.
    class _Ctx:
        def __call__(self):
            return None

    def _context_dep():
        # FastAPI will replace this; we use app_mod.prehire_dashboard_context directly below.
        return app_mod.prehire_dashboard_context

    def _profile_payload(company: str, app_key: str, context: dict[str, Any]) -> dict[str, Any]:
        ensure_schema = app_mod.ensure_schema
        find_application_by_key = app_mod.find_application_by_key
        db_connect = app_mod.db_connect
        prehire_application_summary = app_mod.prehire_application_summary
        company_has_module = app_mod.company_has_module
        candidate_cv_truth = app_mod.candidate_cv_truth
        json_safe = app_mod.json_safe
        held_statuses = app_mod.HELD_IMPORT_STATUSES

        ensure_schema()
        application = find_application_by_key(app_key, company_code=company)
        if not application:
            raise HTTPException(status_code=404, detail={"error": "application_not_found"})
        with db_connect() as conn:
            with conn.cursor() as cur:
                uc.ensure_unified_candidates_schema(cur)
                cur.execute(
                    """
                    SELECT a.*, c.name AS candidate_name, c.email AS candidate_email,
                           c.profile AS candidate_profile, c.raw_json AS candidate_raw_json,
                           sd.content AS semantic_content
                    FROM applications a
                    LEFT JOIN candidates c ON c.phone=a.phone
                    LEFT JOIN semantic_documents sd ON sd.entity_type='application' AND sd.entity_key=a.app_key
                    WHERE a.company_code=%s AND a.app_key=%s
                    LIMIT 1
                    """,
                    (company, app_key),
                )
                row = dict(cur.fetchone() or application)
                try:
                    cur.execute(
                        """
                        SELECT facts, facts_hash, document_id, contract_version, extractor_version,
                               materialized_at, is_current
                        FROM application_cv_fact_snapshots
                        WHERE company_code=%s AND app_key=%s AND is_current=true
                        LIMIT 1
                        """,
                        (company, app_key),
                    )
                    snap_row = cur.fetchone()
                    if snap_row and isinstance(snap_row.get("facts"), dict):
                        row = dict(row)
                        row["_cv_fact_snapshot"] = dict(snap_row)
                except Exception:
                    conn.rollback()
                    uc.ensure_unified_candidates_schema(cur)
                gov = uc.load_governance(cur, company_code=company, app_key=app_key)
                events = uc.list_fact_review_events(cur, company_code=company, app_key=app_key)
                cur.execute(
                    """
                    SELECT file_id, file_kind, document_type, original_filename, storage_provider,
                           storage_url, storage_status, storage_error, stored_at, updated_at, created_at
                    FROM file_registry
                    WHERE company_code=%s AND subject_type='application' AND subject_key=%s
                    ORDER BY updated_at DESC, created_at DESC
                    LIMIT 25
                    """,
                    (company, app_key),
                )
                files = [json_safe(dict(item)) for item in cur.fetchall()]
                try:
                    cur.execute(
                        """
                        SELECT d.document_id, d.document_type, d.filename, d.source,
                               d.extraction_status, d.extraction_method, d.extraction_chars,
                               jsonb_strip_nulls(jsonb_build_object(
                                 'latest', d.metadata->'latest',
                                 'superseded_at', d.metadata->'superseded_at',
                                 'superseded_by_document_id', d.metadata->'superseded_by_document_id',
                                 'validation_status', d.metadata->'validation_status',
                                 'validated_at', d.metadata->'validated_at',
                                 'versioned_at', d.metadata->'versioned_at',
                                 'facts_id', d.metadata->'facts_id',
                                 'content_sha256', COALESCE(
                                   d.metadata->'content_sha256',
                                   d.raw_json#>'{storage,sha256}'
                                 )
                               )) AS metadata,
                               d.received_at, d.created_at, d.updated_at
                        FROM candidate_documents d
                        JOIN applications a ON a.app_key=d.app_key
                        WHERE a.company_code=%s AND d.app_key=%s
                        ORDER BY d.updated_at DESC NULLS LAST, d.created_at DESC
                        LIMIT 25
                        """,
                        (company, app_key),
                    )
                    documents = [json_safe(dict(item)) for item in cur.fetchall()]
                except Exception:
                    documents = []
                cur.execute(
                    """
                    SELECT app_key, status, position_code, position_title, ingested_at, updated_at
                    FROM applications
                    WHERE company_code=%s AND phone=%s
                    ORDER BY ingested_at DESC NULLS LAST
                    """,
                    (company, row.get("phone")),
                )
                siblings = [json_safe(dict(item)) for item in cur.fetchall()]
                conn.commit()

        summary = prehire_application_summary(
            row,
            include_raw=True,
            include_assessment=company_has_module(company, "assessments"),
            permissions=context.get("permissions") or [],
        )
        summary = uc.enrich_application_summary(
            summary,
            row,
            gov=gov,
            permissions=context.get("permissions") or [],
        )
        snapshot = uc.extract_facts_snapshot(row)
        if isinstance(row.get("_cv_fact_snapshot"), dict):
            snap = row["_cv_fact_snapshot"]
            snapshot = {
                "schema": snap.get("contract_version") or "application-cv-facts-v1",
                "immutable": True,
                "snapshot": snap.get("facts") or {},
                "facts_hash": snap.get("facts_hash"),
                "document_id": snap.get("document_id"),
                "extractor_version": snap.get("extractor_version"),
                "materialized_at": json_safe(snap.get("materialized_at")),
                "source": "application_cv_fact_snapshots",
            }
        effective = uc.effective_facts_from_events(snapshot, events)
        held_rows = [s for s in siblings if str(s.get("status") or "") in held_statuses]
        live_rows = [s for s in siblings if str(s.get("status") or "") not in held_statuses]
        timeline = [
            {"label": "Received", "at": summary.get("ingested_at")},
            {"label": "Updated", "at": summary.get("updated_at")},
        ]
        for event in events[-10:]:
            timeline.append(
                {
                    "label": f"Fact review: {event.get('action')} {event.get('fact_path')}",
                    "at": json_safe(event.get("created_at")),
                    "actor": event.get("actor_email") or event.get("actor_user_id"),
                }
            )
        return {
            "company_code": company,
            "application": summary,
            "record_state": summary.get("record_state"),
            "held_reason": uc.held_reason(row),
            "source_channel": summary.get("intake_source"),
            "sender_provenance": uc.sender_provenance(row),
            "grounded_contacts": summary.get("grounded_contacts"),
            "documents": documents,
            "files": files,
            "facts": {
                "extraction_snapshot": snapshot,
                "effective": effective.get("effective"),
                "reviews_by_path": effective.get("reviews_by_path"),
                "events": json_safe(events),
                "completeness": summary.get("completeness"),
                "missing_policy": "Not extracted or Unknown — never a negative fact",
            },
            "privacy": summary.get("privacy"),
            "held_applications": held_rows,
            "live_applications": live_rows,
            "processing_timeline": timeline,
            "link_to_job": summary.get("link_to_job"),
            "cv_truth": candidate_cv_truth(row),
        }

    # Use a Depends factory that looks up the real dependency after app import completes.
    def _prehire_ctx_dep():
        return app_mod.prehire_dashboard_context

    # FastAPI needs the actual callable at decoration time for Depends().
    # Offer routes do the same via register_* after helpers exist; staging mounts us
    # mid-file, so we use a thin proxy dependency.
    async def _proxy_prehire_context():
        dep = app_mod.prehire_dashboard_context
        # prehire_dashboard_context is a FastAPI dependency function.
        # Call through the same mechanism as Depends(dep) would — but since we are
        # already inside a dependency, invoke the underlying sync function via
        # FastAPI's solution: re-register using Annotated after import.
        raise RuntimeError("unreachable")

    # Simpler approach: register routes with Depends(app_mod.prehire_dashboard_context)
    # AFTER ensuring the attribute exists by delaying mount to end of app.py.
    # For mid-file mount, patcher will also append a late remount marker; here we
    # bind Depends lazily by reading the function object when the route is first hit
    # is not supported. So we require the patcher to mount at END of file instead.

    # Temporary: look up dependency now if present, else use a deferred binder installed
    # by ensure_mounted_late().
    ctx_dep = getattr(app_mod, "prehire_dashboard_context", None)
    if ctx_dep is None:
        # Defer full mount; install a bootstrap that app.py can call at end.
        def ensure_mounted_late() -> None:
            mount_unified_candidate_routes_late(app_mod)

        app_mod.ensure_unified_candidates_routes = ensure_mounted_late
        app_mod._UNIFIED_CANDIDATES_ROUTES_PENDING = True
        return

    mount_unified_candidate_routes_late(app_mod)


def mount_unified_candidate_routes_late(app_mod: Any) -> None:
    if getattr(app_mod, "_UNIFIED_CANDIDATES_ROUTES_MOUNTED", False):
        return
    app = app_mod.app
    prehire_dashboard_context = app_mod.prehire_dashboard_context
    require_entitlement = app_mod.require_entitlement
    find_application_by_key = app_mod.find_application_by_key
    ensure_schema = app_mod.ensure_schema
    db_connect = app_mod.db_connect
    json_safe = app_mod.json_safe
    record_admin_audit = app_mod.record_admin_audit

    def _profile_payload(company: str, app_key: str, context: dict[str, Any]) -> dict[str, Any]:
        # Re-enter through the early helper by temporarily setting attrs — duplicate
        # minimal body using late-bound helpers.
        from unified_candidates_routes import _build_profile_payload

        return _build_profile_payload(app_mod, company, app_key, context)

    @app.get("/dashboard/prehire/candidates/feature")
    def dashboard_unified_candidates_feature(context: dict[str, Any] = Depends(prehire_dashboard_context)):
        company = context["company_code"]
        status = uc.feature_status(company)
        return {"ok": True, **status}

    @app.get("/dashboard/prehire/applications/{app_key}/profile")
    def dashboard_prehire_application_profile(app_key: str, context: dict[str, Any] = Depends(prehire_dashboard_context)):
        require_unified(context)
        return _build_profile_payload(app_mod, context["company_code"], app_key, context)

    @app.get("/dashboard/prehire/applications/{app_key}/person-profile")
    def dashboard_prehire_application_person_profile(
        app_key: str,
        context: dict[str, Any] = Depends(prehire_dashboard_context),
    ):
        """Canonical person-aware Candidate profile.

        Independent of Candidates-list pagination / browser-loaded rows.
        Confirmed identity only (person_id / grounded email / grounded phone).
        """
        require_unified(context)
        require_entitlement(context, "pre_hiring", "candidates.read")
        import unified_person_profile as upp

        return upp.build_person_profile(
            app_mod,
            company=context["company_code"],
            app_key=app_key,
            context=context,
        )

    @app.post("/dashboard/prehire/applications/{app_key}/person-profile/add-to-job")
    def dashboard_prehire_application_person_add_to_job(
        app_key: str,
        request: dict[str, Any],
        context: dict[str, Any] = Depends(prehire_dashboard_context),
    ):
        """Add a general candidate to a job through person-profile authority.

        Uses existing assign + intake_admit binding path after person-scoped
        duplicate preflight. Never auto-assigns without confirm=true.
        """
        require_unified(context)
        require_entitlement(context, "pre_hiring", "candidate.import")
        import unified_person_profile as upp

        body = request or {}
        if not bool(body.get("confirm")):
            raise HTTPException(
                status_code=422,
                detail={
                    "error": "confirmation_required",
                    "message": "Confirm Add to job before creating the application.",
                },
            )
        position_code = str(body.get("position_code") or "").strip()
        position_title = str(body.get("position_title") or "").strip()
        person_profile = upp.build_person_profile(
            app_mod,
            company=context["company_code"],
            app_key=app_key,
            context=context,
        )
        preflight = upp.person_add_to_job_preflight(person_profile, position_code=position_code)
        if not preflight.get("ok"):
            error = str(preflight.get("error") or "add_to_job_unavailable")
            status = 409 if error == "duplicate_active_application" else 400
            if error == "missing_candidate_import_permission":
                status = 403
            raise HTTPException(
                status_code=status,
                detail={
                    "error": error,
                    "message": preflight.get("message"),
                    "blocked_position_codes": (person_profile.get("add_to_job") or {}).get("blocked_position_codes"),
                },
            )
        held_app_key = str(preflight.get("held_app_key") or "").strip()
        # Existing canonical assign + intake_admit authority (unchanged).
        return app_mod.dashboard_prehire_import_assign(
            {
                "app_key": held_app_key,
                "position_code": position_code,
                "position_title": position_title or None,
                "promote": True,
            },
            context,
        )

    @app.get("/dashboard/prehire/applications/{app_key}/facts")
    def dashboard_prehire_application_facts(app_key: str, context: dict[str, Any] = Depends(prehire_dashboard_context)):
        require_unified(context)
        payload = _build_profile_payload(app_mod, context["company_code"], app_key, context)
        return {"company_code": payload["company_code"], "app_key": app_key, "facts": payload["facts"]}

    @app.post("/dashboard/prehire/applications/{app_key}/facts/review")
    def dashboard_prehire_application_fact_review(
        app_key: str,
        request: dict[str, Any],
        context: dict[str, Any] = Depends(prehire_dashboard_context),
    ):
        require_unified(context)
        require_entitlement(context, "pre_hiring", "candidate.manage")
        company = context["company_code"]
        application = find_application_by_key(app_key, company_code=company)
        if not application:
            raise HTTPException(status_code=404, detail={"error": "application_not_found"})
        body = request or {}
        preview = bool(body.get("preview"))
        action = str(body.get("action") or "").strip().lower()
        fact_path = str(body.get("fact_path") or "").strip()
        if action not in uc.FACT_EVENT_ACTIONS:
            raise HTTPException(status_code=422, detail={"error": "invalid_fact_review_action"})
        if not fact_path:
            raise HTTPException(status_code=422, detail={"error": "fact_path_required"})
        preview_payload = {
            "ok": True,
            "preview": True,
            "company_code": company,
            "app_key": app_key,
            "action": action,
            "fact_path": fact_path,
            "new_value": body.get("new_value"),
            "previous_value": body.get("previous_value"),
            "note": body.get("note"),
            "confirmation_required": True,
            "message": "Confirm to append an immutable HR fact-review event. Extraction snapshots are never overwritten.",
        }
        if preview or not bool(body.get("confirm")):
            return preview_payload
        with db_connect() as conn:
            with conn.cursor() as cur:
                uc.ensure_unified_candidates_schema(cur)
                try:
                    event = uc.append_fact_review_event(
                        cur,
                        company_code=company,
                        app_key=app_key,
                        fact_path=fact_path,
                        action=action,
                        actor_user_id=str(context.get("actor_user_id") or "") or None,
                        actor_email=str(context.get("actor_email") or context.get("hr_email") or "") or None,
                        new_value=body.get("new_value"),
                        previous_value=body.get("previous_value"),
                        evidence_refs=body.get("evidence_refs") if isinstance(body.get("evidence_refs"), list) else [],
                        note=str(body.get("note") or "") or None,
                        document_version_id=str(body.get("document_version_id") or "") or None,
                        extraction_version_id=str(body.get("extraction_version_id") or "") or None,
                        supersedes_event_id=str(body.get("supersedes_event_id") or "") or None,
                    )
                except ValueError as exc:
                    raise HTTPException(status_code=422, detail={"error": str(exc)}) from exc
                conn.commit()
        record_admin_audit(
            context,
            "candidate_fact_review",
            summary=f"Appended fact review {action} on {fact_path} for {app_key}.",
            target_type="application",
            target=app_key,
            details={"action": action, "fact_path": fact_path, "event_id": event.get("event_id")},
        )
        return {"ok": True, "company_code": company, "app_key": app_key, "event": json_safe(event), "preview": False}

    @app.get("/dashboard/prehire/candidates/saved-views")
    def dashboard_prehire_saved_views(context: dict[str, Any] = Depends(prehire_dashboard_context)):
        require_unified(context)
        company = context["company_code"]
        actor = str(context.get("actor_user_id") or "").strip()
        if not actor:
            raise HTTPException(status_code=400, detail={"error": "actor_required"})
        with db_connect() as conn:
            with conn.cursor() as cur:
                uc.ensure_unified_candidates_schema(cur)
                views = uc.list_saved_views(cur, company_code=company, actor_user_id=actor)
                conn.commit()
        return {"company_code": company, "views": json_safe(views)}

    @app.post("/dashboard/prehire/candidates/saved-views")
    def dashboard_prehire_save_view(request: dict[str, Any], context: dict[str, Any] = Depends(prehire_dashboard_context)):
        require_unified(context)
        company = context["company_code"]
        actor = str(context.get("actor_user_id") or "").strip()
        if not actor:
            raise HTTPException(status_code=400, detail={"error": "actor_required"})
        body = request or {}
        with db_connect() as conn:
            with conn.cursor() as cur:
                uc.ensure_unified_candidates_schema(cur)
                try:
                    view = uc.upsert_saved_view(
                        cur,
                        company_code=company,
                        actor_user_id=actor,
                        name=str(body.get("name") or ""),
                        filters=body.get("filters") if isinstance(body.get("filters"), dict) else {},
                        view_id=str(body.get("view_id") or "") or None,
                    )
                except ValueError as exc:
                    raise HTTPException(status_code=422, detail={"error": str(exc)}) from exc
                conn.commit()
        return {"ok": True, "company_code": company, "view": json_safe(view)}

    @app.delete("/dashboard/prehire/candidates/saved-views/{view_id}")
    def dashboard_prehire_delete_saved_view(view_id: str, context: dict[str, Any] = Depends(prehire_dashboard_context)):
        require_unified(context)
        company = context["company_code"]
        actor = str(context.get("actor_user_id") or "").strip()
        if not actor:
            raise HTTPException(status_code=400, detail={"error": "actor_required"})
        with db_connect() as conn:
            with conn.cursor() as cur:
                uc.ensure_unified_candidates_schema(cur)
                deleted = uc.delete_saved_view(cur, company_code=company, actor_user_id=actor, view_id=view_id)
                conn.commit()
        if not deleted:
            raise HTTPException(status_code=404, detail={"error": "saved_view_not_found"})
        return {"ok": True, "company_code": company, "view_id": view_id}

    def _actor_is_platform_admin(context: dict[str, Any]) -> bool:
        checker = getattr(app_mod, "context_is_platform_admin", None)
        if callable(checker):
            return bool(checker(context))
        phones = getattr(app_mod, "platform_admin_phones", lambda: set())()
        digit_fn = getattr(app_mod, "digits", lambda value: str(value or ""))
        candidates = [
            context.get("hr_phone"),
            context.get("actor_phone"),
            (context.get("hr_user") or {}).get("phone") if isinstance(context.get("hr_user"), dict) else None,
            ((context.get("access") or {}).get("user") or {}).get("phone")
            if isinstance(context.get("access"), dict)
            else None,
        ]
        for raw in candidates:
            phone = digit_fn(raw)
            if phone and phone in phones:
                return True
        return bool((context.get("access") or {}).get("is_platform_admin"))

    @app.get("/dashboard/prehire/intake-operations")
    def dashboard_prehire_intake_operations(context: dict[str, Any] = Depends(prehire_dashboard_context)):
        require_unified(context)
        if not _actor_is_platform_admin(context):
            raise HTTPException(
                status_code=403,
                detail={
                    "error": "platform_support_only",
                    "message": "Intake Operations is available only to OctoHR platform support.",
                },
            )
        company = context["company_code"]
        with db_connect() as conn:
            with conn.cursor() as cur:
                uc.ensure_unified_candidates_schema(cur)
                summary = uc.intake_operations_summary(cur, company_code=company)
                conn.commit()
        return {**summary, "intake_ops_visible": True, "audience": "platform_support"}

    @app.get("/dashboard/prehire/intake-operations/attention")
    def dashboard_prehire_intake_attention(context: dict[str, Any] = Depends(prehire_dashboard_context)):
        require_unified(context)
        company = context["company_code"]
        platform_admin = _actor_is_platform_admin(context)
        with db_connect() as conn:
            with conn.cursor() as cur:
                uc.ensure_unified_candidates_schema(cur)
                summary = uc.intake_operations_summary(cur, company_code=company)
                conn.commit()
        attention = int(summary.get("attention_count") or 0)
        return {
            "company_code": company,
            "attention_count": attention,
            "banner": summary.get("banner") if attention else None,
            "link": "/intake-operations" if platform_admin and attention else None,
            "intake_ops_visible": platform_admin,
            "audience": "platform_support" if platform_admin else "hr",
        }

    app_mod._UNIFIED_CANDIDATES_ROUTES_MOUNTED = True
    app_mod._UNIFIED_CANDIDATES_ROUTES_PENDING = False


def _build_profile_payload(app_mod: Any, company: str, app_key: str, context: dict[str, Any]) -> dict[str, Any]:
    ensure_schema = app_mod.ensure_schema
    find_application_by_key = app_mod.find_application_by_key
    db_connect = app_mod.db_connect
    prehire_application_summary = app_mod.prehire_application_summary
    company_has_module = app_mod.company_has_module
    candidate_cv_truth = app_mod.candidate_cv_truth
    json_safe = app_mod.json_safe
    held_statuses = app_mod.HELD_IMPORT_STATUSES

    ensure_schema()
    application = find_application_by_key(app_key, company_code=company)
    if not application:
        raise HTTPException(status_code=404, detail={"error": "application_not_found"})
    with db_connect() as conn:
        with conn.cursor() as cur:
            uc.ensure_unified_candidates_schema(cur)
            cur.execute(
                """
                SELECT a.*, c.name AS candidate_name, c.email AS candidate_email,
                       c.profile AS candidate_profile, c.raw_json AS candidate_raw_json,
                       sd.content AS semantic_content
                FROM applications a
                LEFT JOIN candidates c ON c.phone=a.phone
                LEFT JOIN semantic_documents sd ON sd.entity_type='application' AND sd.entity_key=a.app_key
                WHERE a.company_code=%s AND a.app_key=%s
                LIMIT 1
                """,
                (company, app_key),
            )
            row = dict(cur.fetchone() or application)
            try:
                cur.execute(
                    """
                    SELECT facts, facts_hash, document_id, contract_version, extractor_version,
                           materialized_at, is_current
                    FROM application_cv_fact_snapshots
                    WHERE company_code=%s AND app_key=%s AND is_current=true
                    LIMIT 1
                    """,
                    (company, app_key),
                )
                snap_row = cur.fetchone()
                if snap_row and isinstance(snap_row.get("facts"), dict):
                    row = dict(row)
                    row["_cv_fact_snapshot"] = dict(snap_row)
            except Exception:
                conn.rollback()
                with conn.cursor() as cur2:
                    uc.ensure_unified_candidates_schema(cur2)
            gov = uc.load_governance(cur, company_code=company, app_key=app_key)
            events = uc.list_fact_review_events(cur, company_code=company, app_key=app_key)
            cur.execute(
                """
                SELECT file_id, file_kind, document_type, original_filename, storage_provider,
                       storage_url, storage_status, storage_error, stored_at, updated_at, created_at
                FROM file_registry
                WHERE company_code=%s AND subject_type='application' AND subject_key=%s
                ORDER BY updated_at DESC, created_at DESC
                LIMIT 25
                """,
                (company, app_key),
            )
            files = [json_safe(dict(item)) for item in cur.fetchall()]
            try:
                cur.execute(
                    """
                    SELECT d.document_id, d.document_type, d.filename, d.source,
                           d.extraction_status, d.extraction_method, d.extraction_chars,
                           jsonb_strip_nulls(jsonb_build_object(
                             'latest', d.metadata->'latest',
                             'superseded_at', d.metadata->'superseded_at',
                             'superseded_by_document_id', d.metadata->'superseded_by_document_id',
                             'validation_status', d.metadata->'validation_status',
                             'validated_at', d.metadata->'validated_at',
                             'versioned_at', d.metadata->'versioned_at',
                             'facts_id', d.metadata->'facts_id',
                             'content_sha256', COALESCE(
                               d.metadata->'content_sha256',
                               d.raw_json#>'{storage,sha256}'
                             )
                           )) AS metadata,
                           d.received_at, d.created_at, d.updated_at
                    FROM candidate_documents d
                    JOIN applications a ON a.app_key=d.app_key
                    WHERE a.company_code=%s AND d.app_key=%s
                    ORDER BY d.updated_at DESC NULLS LAST, d.created_at DESC
                    LIMIT 25
                    """,
                    (company, app_key),
                )
                documents = [json_safe(dict(item)) for item in cur.fetchall()]
            except Exception:
                conn.rollback()
                uc.ensure_unified_candidates_schema(cur)
                documents = []
            cur.execute(
                """
                SELECT app_key, status, position_code, position_title, ingested_at, updated_at
                FROM applications
                WHERE company_code=%s AND phone=%s
                ORDER BY ingested_at DESC NULLS LAST
                """,
                (company, row.get("phone")),
            )
            siblings = [json_safe(dict(item)) for item in cur.fetchall()]
            conn.commit()

    summary = prehire_application_summary(
        row,
        include_raw=True,
        include_assessment=company_has_module(company, "assessments"),
        permissions=context.get("permissions") or [],
    )
    summary = uc.enrich_application_summary(
        summary,
        row,
        gov=gov,
        permissions=context.get("permissions") or [],
    )
    snapshot = uc.extract_facts_snapshot(row)
    if isinstance(row.get("_cv_fact_snapshot"), dict):
        snap = row["_cv_fact_snapshot"]
        snapshot = {
            "schema": snap.get("contract_version") or "application-cv-facts-v1",
            "immutable": True,
            "snapshot": snap.get("facts") or {},
            "facts_hash": snap.get("facts_hash"),
            "document_id": snap.get("document_id"),
            "extractor_version": snap.get("extractor_version"),
            "materialized_at": json_safe(snap.get("materialized_at")),
            "source": "application_cv_fact_snapshots",
        }
    effective = uc.effective_facts_from_events(snapshot, events)
    held_rows = [s for s in siblings if str(s.get("status") or "") in held_statuses]
    live_rows = [s for s in siblings if str(s.get("status") or "") not in held_statuses]
    timeline = [
        {"label": "Received", "at": summary.get("ingested_at")},
        {"label": "Updated", "at": summary.get("updated_at")},
    ]
    for event in events[-10:]:
        timeline.append(
            {
                "label": f"Fact review: {event.get('action')} {event.get('fact_path')}",
                "at": json_safe(event.get("created_at")),
                "actor": event.get("actor_email") or event.get("actor_user_id"),
            }
        )
    return {
        "company_code": company,
        "application": summary,
        "record_state": summary.get("record_state"),
        "held_reason": uc.held_reason(row),
        "source_channel": summary.get("intake_source"),
        "sender_provenance": uc.sender_provenance(row),
        "grounded_contacts": summary.get("grounded_contacts"),
        "documents": documents,
        "files": files,
        "facts": {
            "extraction_snapshot": snapshot,
            "effective": effective.get("effective"),
            "reviews_by_path": effective.get("reviews_by_path"),
            "events": json_safe(events),
            "completeness": summary.get("completeness"),
            "missing_policy": "Not extracted or Unknown — never a negative fact",
        },
        "privacy": summary.get("privacy"),
        "held_applications": held_rows,
        "live_applications": live_rows,
        "processing_timeline": timeline,
        "link_to_job": summary.get("link_to_job"),
        "cv_truth": candidate_cv_truth(row),
    }
