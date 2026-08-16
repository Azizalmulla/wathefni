"""Phase 3 history and workflow readers for Candidate Knowledge.

Read-only. No ranking side effects, OCR, Voyage, raw JSON pass-through, or
Role Profile creation.
"""

from __future__ import annotations

from typing import Any

from candidate_knowledge_readers import SectionRead, _coverage, _evidence_id, _norm, _truthy_current
from candidate_knowledge_types import AuthorityLevel, CoverageState, EvidenceRef
from candidate_record_state_policy import (
    FINALIZED_STATUSES,
    INTAKE_HOLD_STATUSES,
    LIVE_PIPELINE_STATUSES,
    evaluate_candidate_record_state,
)


PHASE3_READER_VERSION = "candidate-knowledge-phase3-readers-v1"
MANAGE_PERMISSION = "candidate.manage"

SECRET_INTERVIEW_FIELDS = frozenset(
    {
        "calendar_payload",
        "calendar_event_id",
        "meet_link",
        "sent_body",
        "sent_subject",
        "public_link",
        "signed_link",
        "consent_payload",
        "transcript",
        "delivery_payload",
        "invite_token",
        "oauth_token",
    }
)

SCREENING_SOURCE_ALIASES = {
    "candidate_reply": "candidate_reply",
    "candidate": "candidate_reply",
    "reply": "candidate_reply",
    "cv_prefill": "cv_prefill",
    "cv": "cv_prefill",
    "prefill": "cv_prefill",
    "parser": "parser",
    "system": "system",
}


def _authority_for_screening_source(source: str) -> AuthorityLevel:
    if source == "cv_prefill":
        return "cv_prefill"
    if source == "candidate_reply":
        return "candidate_reply"
    return "operational_mirror"


def _lifecycle_bucket(status: str) -> str:
    value = _norm(status).lower()
    if value in INTAKE_HOLD_STATUSES:
        return "held"
    if value in FINALIZED_STATUSES:
        return "finalized"
    if value in LIVE_PIPELINE_STATUSES:
        return "live"
    return "other"


def _sort_ts(item: dict[str, Any], *keys: str) -> str:
    for key in keys:
        value = item.get(key)
        if value:
            return str(value)
    return ""


def read_applications(
    store: Any,
    *,
    company_code: str,
    applications: list[dict[str, Any]],
    governance_by_app_key: dict[str, dict[str, Any]],
    read_projection: str = "full",
    limit: int = 50,
    offset: int = 0,
) -> SectionRead:
    company = _norm(company_code).upper()
    if read_projection in {"denied", "not_authorized"}:
        return SectionRead(
            section="applications",
            payload={"items": [], "pagination": {"limit": limit, "offset": offset, "total": 0}},
            coverage=_coverage("applications", "not_authorized", "read_projection_denied"),
        )
    if read_projection in {"restricted", "metadata_only"}:
        return SectionRead(
            section="applications",
            payload={
                "items": [
                    {"app_key": item.get("app_key"), "status": item.get("status"), "suppressed": True}
                    for item in applications
                ],
                "pagination": {"limit": limit, "offset": offset, "total": len(applications)},
            },
            coverage=_coverage("applications", "restricted", "metadata_only"),
        )

    page_limit = max(1, min(int(limit or 50), 200))
    page_offset = max(0, int(offset or 0))
    ranked = sorted(
        [dict(item) for item in applications if isinstance(item, dict)],
        key=lambda item: (
            _sort_ts(item, "updated_at", "ingested_at", "created_at"),
            _norm(item.get("app_key")),
        ),
        reverse=True,
    )
    page = ranked[page_offset : page_offset + page_limit]
    evidence: list[EvidenceRef] = []
    items: list[dict[str, Any]] = []

    for app in page:
        app_key = _norm(app.get("app_key"))
        gov = governance_by_app_key.get(app_key) or store.get_governance(company_code=company, app_key=app_key) or {}
        decision = evaluate_candidate_record_state(app, governance=gov)
        events = store.list_lifecycle_events(company_code=company, app_key=app_key)
        versions = store.list_cv_text_versions(company_code=company, app_key=app_key)
        current_versions = [item for item in versions if _truthy_current(item.get("is_current"))]
        cv_ref = None
        if len(current_versions) == 1:
            cv_ref = {
                "version_id": current_versions[0].get("version_id"),
                "document_id": current_versions[0].get("document_id"),
                "status": current_versions[0].get("status"),
            }
        elif len(current_versions) > 1:
            cv_ref = {"conflict": True, "current_version_count": len(current_versions)}

        status = _norm(app.get("status")).lower()
        channel = _norm(app.get("data_source_detail") or app.get("data_source") or app.get("source_channel")).lower() or "unknown"
        item = {
            "app_key": app_key,
            "company_code": company,
            "position_code": app.get("position_code"),
            "position_title": app.get("position_title"),
            "source_channel": channel,
            "created_at": app.get("created_at"),
            "updated_at": app.get("updated_at") or app.get("ingested_at"),
            "lifecycle_status": status,
            "lifecycle_bucket": _lifecycle_bucket(status),
            "held_state": decision.held_state,
            "live": status in LIVE_PIPELINE_STATUSES and status not in INTAKE_HOLD_STATUSES,
            "finalized": status in FINALIZED_STATUSES,
            "lifecycle_dates": {
                "screening_completed_at": app.get("screening_completed_at"),
                "ingested_at": app.get("ingested_at"),
                "created_at": app.get("created_at"),
                "updated_at": app.get("updated_at"),
            },
            "lifecycle_events": [
                {
                    "event_id": event.get("event_id"),
                    "from_stage": event.get("from_stage"),
                    "to_stage": event.get("to_stage"),
                    "trigger": event.get("trigger"),
                    "created_at": event.get("created_at"),
                }
                for event in events[:20]
            ],
            "current_cv_document_ref": cv_ref,
            "communication_eligible": decision.communication_allowed,
            "lifecycle_mutation_eligible": decision.lifecycle_mutation_allowed,
            "assessment_eligible": decision.lifecycle_mutation_allowed and status not in FINALIZED_STATUSES,
            "interview_eligible": decision.lifecycle_mutation_allowed and status not in FINALIZED_STATUSES,
            "job_ranking_eligible": decision.job_ranking_eligible,
            "provenance": {
                "data_source": app.get("data_source"),
                "data_source_detail": app.get("data_source_detail"),
            },
            "coverage": "available",
        }
        # Never pass raw JSON through.
        assert "raw_json" not in item
        items.append(item)
        evidence.append(
            EvidenceRef(
                evidence_id=_evidence_id(company, app_key, "application", status),
                source_kind="applications",
                source_record_id=app_key,
                company_code=company,
                app_key=app_key,
                authority_level="canonical",
                review_state="not_applicable",
                observed_at=_norm(app.get("updated_at") or app.get("created_at")) or None,
            )
        )

    state: CoverageState = "available" if items else "not_recorded"
    return SectionRead(
        section="applications",
        payload={
            "items": items,
            "pagination": {
                "limit": page_limit,
                "offset": page_offset,
                "total": len(ranked),
                "returned": len(items),
                "has_more": page_offset + len(items) < len(ranked),
            },
            "deduplicated_by_name": False,
        },
        coverage=_coverage("applications", state, "tenant_bound_applications"),
        evidence=evidence,
    )


def read_screening_evidence(
    store: Any,
    *,
    company_code: str,
    app_keys: list[str],
    read_projection: str = "full",
) -> SectionRead:
    company = _norm(company_code).upper()
    if read_projection in {"denied", "not_authorized"}:
        return SectionRead(
            section="screening_evidence",
            payload={"items": []},
            coverage=_coverage("screening_evidence", "not_authorized", "read_projection_denied"),
        )
    if read_projection in {"restricted", "metadata_only"}:
        return SectionRead(
            section="screening_evidence",
            payload={"items": [], "suppressed": True},
            coverage=_coverage("screening_evidence", "restricted", "metadata_only"),
        )

    items: list[dict[str, Any]] = []
    evidence: list[EvidenceRef] = []
    stale_count = 0
    for app_key in [_norm(item) for item in app_keys if _norm(item)]:
        facet = store.get_screening_facet(company_code=company, app_key=app_key)
        if not facet:
            continue
        # Guard against full raw JSON leakage from adapters/tests.
        if "raw_json" in facet and "screening" not in facet:
            continue
        screening = facet.get("screening") if isinstance(facet.get("screening"), dict) else {}
        answers = screening.get("answers") if isinstance(screening.get("answers"), dict) else {}
        sources = screening.get("answer_sources") if isinstance(screening.get("answer_sources"), dict) else {}
        answer_evidence = (
            screening.get("answer_evidence") if isinstance(screening.get("answer_evidence"), dict) else {}
        )
        questions = screening.get("questions") if isinstance(screening.get("questions"), list) else []
        prompt_by_key = {
            _norm(q.get("key") or q.get("question_key")): _norm(q.get("prompt") or q.get("label") or q.get("text"))
            for q in questions
            if isinstance(q, dict)
        }
        completed_at = facet.get("screening_completed_at") or screening.get("completed_at")
        last_answered_at = screening.get("last_answered_at")
        status = _norm(facet.get("screening_status") or screening.get("status")).lower()

        keys = sorted(
            {_norm(k) for k in answers.keys() if _norm(k)}
            | {_norm(k) for k in sources.keys() if _norm(k)}
        )
        for question_key in keys:
            source_raw = _norm(sources.get(question_key)).lower() or "unknown"
            source = SCREENING_SOURCE_ALIASES.get(source_raw, source_raw if source_raw in {"candidate_reply", "cv_prefill", "parser", "system"} else "system")
            # Never relabel cv_prefill as candidate_reply.
            if source_raw in {"cv_prefill", "cv", "prefill"}:
                source = "cv_prefill"
            ev = answer_evidence.get(question_key) if isinstance(answer_evidence.get(question_key), dict) else {}
            corrections = screening.get("corrections") if isinstance(screening.get("corrections"), dict) else {}
            correction = ev.get("correction") or corrections.get(question_key)
            captured_at = ev.get("captured_at") or last_answered_at or completed_at
            stale = False
            if status and status not in {"completed", "complete", "screening_complete"} and answers.get(question_key) is not None:
                stale = True
            if ev.get("stale") is True or _norm(ev.get("state")).lower() == "stale":
                stale = True
            if stale:
                stale_count += 1
            record = {
                "question_key": question_key,
                "question_prompt": prompt_by_key.get(question_key) or None,
                "answer_value": answers.get(question_key),
                "source": source,
                "captured_at": captured_at,
                "correction_state": correction or ("corrected" if ev.get("corrected") else None),
                "confidence": ev.get("confidence"),
                "parser": ev.get("parser") or ev.get("model"),
                "model": ev.get("model"),
                "stale": stale,
                "application_provenance": {
                    "app_key": app_key,
                    "company_code": company,
                    "screening_status": status or None,
                    "conversation_id": screening.get("conversation_id") or facet.get("conversation_id"),
                },
            }
            items.append(record)
            evidence.append(
                EvidenceRef(
                    evidence_id=_evidence_id(company, app_key, "screening", question_key, source, captured_at),
                    source_kind="applications.screening",
                    source_record_id=f"{app_key}:{question_key}",
                    company_code=company,
                    app_key=app_key,
                    authority_level=_authority_for_screening_source(source),
                    review_state="not_applicable",
                    observed_at=_norm(captured_at) or None,
                )
            )

    if not items:
        return SectionRead(
            section="screening_evidence",
            payload={"items": []},
            coverage=_coverage("screening_evidence", "not_recorded", "no_screening_answers"),
            evidence=[],
        )
    state: CoverageState = "stale" if stale_count and stale_count == len(items) else ("partial" if stale_count else "available")
    return SectionRead(
        section="screening_evidence",
        payload={"items": items, "stale_count": stale_count},
        coverage=_coverage("screening_evidence", state, "typed_screening_evidence"),
        evidence=evidence,
    )


def read_assessments(
    store: Any,
    *,
    company_code: str,
    app_keys: list[str],
    modules_enabled: tuple[str, ...] | list[str] = (),
    module_enabled: Any = None,
    read_projection: str = "full",
) -> SectionRead:
    company = _norm(company_code).upper()
    if read_projection in {"denied", "not_authorized"}:
        return SectionRead(
            section="assessments",
            payload={"items": []},
            coverage=_coverage("assessments", "not_authorized", "read_projection_denied"),
        )
    enabled = "assessments" in {_norm(item) for item in modules_enabled}
    if not enabled and module_enabled is not None:
        try:
            enabled = bool(module_enabled(company, "assessments"))
        except Exception:
            enabled = False
    if not enabled:
        return SectionRead(
            section="assessments",
            payload={"items": [], "module": "assessments"},
            coverage=_coverage("assessments", "module_disabled", "assessments_module_disabled"),
        )
    if read_projection in {"restricted", "metadata_only"}:
        return SectionRead(
            section="assessments",
            payload={"items": [], "suppressed": True},
            coverage=_coverage("assessments", "restricted", "metadata_only"),
        )

    attempts = store.list_assessment_attempts(company_code=company, app_keys=list(app_keys))
    attempt_ids = [_norm(item.get("attempt_id")) for item in attempts if _norm(item.get("attempt_id"))]
    scores = {
        _norm(item.get("attempt_id")): item
        for item in store.list_assessment_scores(company_code=company, attempt_ids=attempt_ids)
    }
    reports = {
        _norm(item.get("attempt_id")): item
        for item in store.list_assessment_report_summaries(company_code=company, attempt_ids=attempt_ids)
    }
    items: list[dict[str, Any]] = []
    evidence: list[EvidenceRef] = []
    for attempt in attempts:
        attempt_id = _norm(attempt.get("attempt_id"))
        score = scores.get(attempt_id) or {}
        report = reports.get(attempt_id) or {}
        status = _norm(attempt.get("status")).lower()
        item = {
            "attempt_id": attempt_id,
            "app_key": attempt.get("app_key"),
            "battery_key": attempt.get("battery_key"),
            "assessment_version_id": attempt.get("assessment_version_id"),
            "status": status,
            "completed_score": score.get("percent") if score.get("percent") is not None else score.get("raw_score"),
            "score_band": score.get("band"),
            "section_scores": score.get("section_scores") if isinstance(score.get("section_scores"), dict) else {},
            "approved_report_summary": report.get("summary"),
            "job_match_summary": report.get("job_match") if isinstance(report.get("job_match"), dict) else None,
            "review_state": attempt.get("review_status"),
            "cancelled": bool(attempt.get("cancelled_at")) or status == "cancelled",
            "expired": bool(attempt.get("expired_at")) or status == "expired",
            "timestamps": {
                "started_at": attempt.get("started_at"),
                "completed_at": attempt.get("completed_at"),
                "cancelled_at": attempt.get("cancelled_at"),
                "expired_at": attempt.get("expired_at"),
                "created_at": attempt.get("created_at"),
            },
        }
        # Explicit non-exposure of raw answers / unrestricted report payloads.
        assert "answers" not in item
        assert "report_json" not in item
        items.append(item)
        evidence.append(
            EvidenceRef(
                evidence_id=_evidence_id(company, attempt_id, status),
                source_kind="assessment_attempts",
                source_record_id=attempt_id,
                company_code=company,
                app_key=_norm(attempt.get("app_key")) or None,
                authority_level="canonical",
                review_state="hr_confirmed" if _norm(attempt.get("review_status")).lower() in {"approved", "reviewed"} else "unreviewed",
                observed_at=_norm(attempt.get("completed_at") or attempt.get("created_at")) or None,
            )
        )

    if not items:
        return SectionRead(
            section="assessments",
            payload={"items": []},
            coverage=_coverage("assessments", "not_recorded", "no_assessment_attempts"),
        )
    return SectionRead(
        section="assessments",
        payload={"items": items},
        coverage=_coverage("assessments", "available", "assessment_attempts"),
        evidence=evidence,
    )


def read_interviews(
    store: Any,
    *,
    company_code: str,
    app_keys: list[str],
    modules_enabled: tuple[str, ...] | list[str] = (),
    module_enabled: Any = None,
    read_projection: str = "full",
) -> SectionRead:
    company = _norm(company_code).upper()
    if read_projection in {"denied", "not_authorized"}:
        return SectionRead(
            section="interviews",
            payload={"items": []},
            coverage=_coverage("interviews", "not_authorized", "read_projection_denied"),
        )
    # Interviews require pre-hire posture (already authorized upstream).
    # Explicit interviews module gate only when listed in modules_enabled.
    modules = {_norm(item) for item in modules_enabled}
    if "interviews" in modules and module_enabled is not None:
        try:
            if not bool(module_enabled(company, "interviews")):
                return SectionRead(
                    section="interviews",
                    payload={"items": [], "module": "interviews"},
                    coverage=_coverage("interviews", "module_disabled", "interviews_module_disabled"),
                )
        except Exception:
            return SectionRead(
                section="interviews",
                payload={"items": [], "module": "interviews"},
                coverage=_coverage("interviews", "module_disabled", "interviews_module_check_failed"),
            )
    if read_projection in {"restricted", "metadata_only"}:
        return SectionRead(
            section="interviews",
            payload={"items": [], "suppressed": True},
            coverage=_coverage("interviews", "restricted", "metadata_only"),
        )

    interviews = store.list_interviews(company_code=company, app_keys=list(app_keys))
    interview_ids = [_norm(item.get("interview_id")) for item in interviews if _norm(item.get("interview_id"))]
    feedback_rows = store.list_interview_feedback_submissions(company_code=company, interview_ids=interview_ids)
    feedback_by_interview: dict[str, list[dict[str, Any]]] = {}
    for row in feedback_rows:
        feedback_by_interview.setdefault(_norm(row.get("interview_id")), []).append(row)

    items: list[dict[str, Any]] = []
    evidence: list[EvidenceRef] = []
    for interview in interviews:
        interview_id = _norm(interview.get("interview_id"))
        safe_interview = {
            key: value for key, value in interview.items() if key not in SECRET_INTERVIEW_FIELDS
        }
        ai_summary_raw = safe_interview.get("ai_summary")
        ai_summary = None
        if isinstance(ai_summary_raw, dict):
            ai_summary = {
                "text": ai_summary_raw.get("summary") or ai_summary_raw.get("text"),
                "labeled_as": "ai_generated",
            }
        elif isinstance(ai_summary_raw, str) and ai_summary_raw.strip():
            ai_summary = {"text": ai_summary_raw.strip(), "labeled_as": "ai_generated"}
        human_notes = []
        if _norm(safe_interview.get("notes")):
            human_notes.append(
                {
                    "source": "interview_record",
                    "text": safe_interview.get("notes"),
                    "authority": "hr_confirmed",
                }
            )
        for fb in feedback_by_interview.get(interview_id, []):
            if _norm(fb.get("free_text_notes")):
                human_notes.append(
                    {
                        "source": "interview_feedback_submission",
                        "text": fb.get("free_text_notes"),
                        "submission_id": fb.get("submission_id"),
                        "authority": "hr_confirmed",
                    }
                )
        transcript_available = bool(safe_interview.get("transcript_available"))
        if interview.get("transcript"):
            transcript_available = True
        item = {
            "interview_id": interview_id,
            "app_key": safe_interview.get("app_key"),
            "interview_type": safe_interview.get("interview_type"),
            "schedule": {
                "scheduled_start": safe_interview.get("scheduled_start"),
                "scheduled_end": safe_interview.get("scheduled_end"),
                "timezone": safe_interview.get("timezone"),
                "duration_minutes": safe_interview.get("duration_minutes"),
                "location": safe_interview.get("location"),
            },
            "status": safe_interview.get("status"),
            "feedback_status": safe_interview.get("feedback_status")
            or safe_interview.get("human_feedback_status"),
            "human_feedback_notes": human_notes,
            "transcript_available": transcript_available,
            "ai_summary": ai_summary,
            "consent_state": {
                "accepted": bool(safe_interview.get("consent_accepted_at")),
                "accepted_at": safe_interview.get("consent_accepted_at"),
            },
            "timestamps": {
                "created_at": safe_interview.get("created_at"),
                "updated_at": safe_interview.get("updated_at"),
                "completed_at": safe_interview.get("completed_at"),
                "cancelled_at": safe_interview.get("cancelled_at"),
            },
        }
        for secret in SECRET_INTERVIEW_FIELDS:
            assert secret not in item
            assert secret not in (item.get("schedule") or {})
        items.append(item)
        evidence.append(
            EvidenceRef(
                evidence_id=_evidence_id(company, interview_id, interview.get("status")),
                source_kind="candidate_interviews",
                source_record_id=interview_id,
                company_code=company,
                app_key=_norm(safe_interview.get("app_key")) or None,
                authority_level="canonical",
                review_state="hr_confirmed" if human_notes else "unreviewed",
                observed_at=_norm(
                    safe_interview.get("completed_at")
                    or safe_interview.get("scheduled_start")
                    or safe_interview.get("created_at")
                )
                or None,
            )
        )

    if not items:
        return SectionRead(
            section="interviews",
            payload={"items": []},
            coverage=_coverage("interviews", "not_recorded", "no_interviews"),
        )
    return SectionRead(
        section="interviews",
        payload={"items": items},
        coverage=_coverage("interviews", "available", "candidate_interviews"),
        evidence=evidence,
    )


def read_ranking_evaluations(
    store: Any,
    *,
    company_code: str,
    app_keys: list[str],
    read_projection: str = "full",
) -> SectionRead:
    company = _norm(company_code).upper()
    if read_projection in {"denied", "not_authorized"}:
        return SectionRead(
            section="ranking_evaluations",
            payload={"items": []},
            coverage=_coverage("ranking_evaluations", "not_authorized", "read_projection_denied"),
        )
    if read_projection in {"restricted", "metadata_only"}:
        return SectionRead(
            section="ranking_evaluations",
            payload={"items": [], "suppressed": True},
            coverage=_coverage("ranking_evaluations", "restricted", "metadata_only"),
        )

    items: list[dict[str, Any]] = []
    evidence: list[EvidenceRef] = []
    stale_count = 0

    for row in store.list_rank_evaluations(company_code=company, app_keys=list(app_keys)):
        item = {
            "evaluation_id": row.get("evaluation_id"),
            "source_family": "candidate_rank_evaluations",
            "app_key": row.get("app_key"),
            "score": row.get("deterministic_score"),
            "scale": "0_100_advisory",
            "breakdown": row.get("score_breakdown") if isinstance(row.get("score_breakdown"), dict) else {},
            "evidence_summary": None,
            "job_context": {
                "position_code": row.get("position_code"),
                "position_title": row.get("position_title"),
            },
            "criteria_context": {
                "role_profile_key": row.get("role_profile_key"),
                "historical_only": True,
            },
            "scorer_model_version": row.get("model"),
            "evidence_digest": row.get("evidence_digest"),
            "current": True,
            "stale": False,
            "timestamp": row.get("created_at"),
            "not_general_candidate_quality": True,
        }
        items.append(item)
        evidence.append(
            EvidenceRef(
                evidence_id=_evidence_id(company, row.get("evaluation_id"), row.get("position_code")),
                source_kind="candidate_rank_evaluations",
                source_record_id=_norm(row.get("evaluation_id")),
                company_code=company,
                app_key=_norm(row.get("app_key")) or None,
                authority_level="canonical",
                review_state="not_applicable",
                observed_at=_norm(row.get("created_at")) or None,
                content_hash=_norm(row.get("evidence_digest")) or None,
            )
        )

    for row in store.list_ranking_run_items_for_apps(company_code=company, app_keys=list(app_keys)):
        stale = not _truthy_current(row.get("is_current")) or bool(row.get("stale_reason") or row.get("stale_at"))
        if stale:
            stale_count += 1
        evidence_summary = row.get("explanation")
        if not evidence_summary and isinstance(row.get("evidence"), list):
            evidence_summary = f"{len(row.get('evidence') or [])} evidence items"
        item = {
            "evaluation_id": row.get("item_id"),
            "run_id": row.get("run_id"),
            "source_family": "ranking_run_items",
            "app_key": row.get("app_key"),
            "score": row.get("advisory_score"),
            "scale": "advisory_run_score",
            "breakdown": row.get("component_scores") if isinstance(row.get("component_scores"), dict) else {},
            "evidence_summary": evidence_summary,
            "job_context": {
                "position_code": row.get("position_code"),
                "job_id": row.get("job_id"),
                "job_version": row.get("job_version"),
            },
            "criteria_context": {
                "criteria_set_id": row.get("criteria_set_id"),
                "criteria_version": row.get("criteria_version"),
                "scoring_config_version": row.get("scoring_config_version"),
            },
            "scorer_model_version": row.get("embedding_model"),
            "evidence_digest": row.get("request_hash"),
            "current": not stale,
            "stale": stale,
            "stale_reason": row.get("stale_reason"),
            "timestamp": row.get("created_at"),
            "not_general_candidate_quality": True,
        }
        items.append(item)
        evidence.append(
            EvidenceRef(
                evidence_id=_evidence_id(company, row.get("item_id"), row.get("run_id"), row.get("position_code")),
                source_kind="ranking_run_items",
                source_record_id=_norm(row.get("item_id")),
                company_code=company,
                app_key=_norm(row.get("app_key")) or None,
                authority_level="canonical",
                review_state="not_applicable",
                observed_at=_norm(row.get("created_at")) or None,
                content_hash=_norm(row.get("request_hash")) or None,
            )
        )

    if not items:
        return SectionRead(
            section="ranking_evaluations",
            payload={"items": []},
            coverage=_coverage("ranking_evaluations", "not_recorded", "no_stored_rankings"),
        )
    state: CoverageState = "stale" if stale_count and stale_count == len(items) else ("partial" if stale_count else "available")
    return SectionRead(
        section="ranking_evaluations",
        payload={"items": items, "creates_new_evaluations": False},
        coverage=_coverage("ranking_evaluations", state, "stored_ranking_only"),
        evidence=evidence,
    )


def read_notes(
    store: Any,
    *,
    company_code: str,
    app_keys: list[str],
    candidate_phone: str = "",
    permissions: tuple[str, ...] | list[str] = (),
    interviews_payload: list[dict[str, Any]] | None = None,
    read_projection: str = "full",
) -> SectionRead:
    company = _norm(company_code).upper()
    if read_projection in {"denied", "not_authorized"}:
        return SectionRead(
            section="notes",
            payload={"items": []},
            coverage=_coverage("notes", "not_authorized", "read_projection_denied"),
        )
    if read_projection in {"restricted", "metadata_only"}:
        return SectionRead(
            section="notes",
            payload={"items": [], "suppressed": True},
            coverage=_coverage("notes", "restricted", "metadata_only"),
        )

    can_manage = MANAGE_PERMISSION in { _norm(item) for item in permissions }
    items: list[dict[str, Any]] = []
    evidence: list[EvidenceRef] = []

    for note in store.list_application_notes(company_code=company, app_keys=list(app_keys)):
        visibility = "internal"
        items.append(
            {
                "note_id": note.get("note_id"),
                "source_workflow": "application",
                "author": note.get("created_by_user_id"),
                "timestamp": note.get("created_at"),
                "app_key": note.get("app_key"),
                "visibility": visibility,
                "authority_state": "hr_confirmed",
                "body": note.get("body"),
            }
        )
        evidence.append(
            EvidenceRef(
                evidence_id=_evidence_id(company, note.get("note_id"), "application_note"),
                source_kind="application_notes",
                source_record_id=_norm(note.get("note_id")),
                company_code=company,
                app_key=_norm(note.get("app_key")) or None,
                authority_level="hr_confirmed",
                review_state="hr_confirmed",
                observed_at=_norm(note.get("created_at")) or None,
            )
        )

    for app_key in [_norm(item) for item in app_keys if _norm(item)]:
        for event in store.list_fact_review_events(company_code=company, app_key=app_key):
            if not _norm(event.get("note")):
                continue
            items.append(
                {
                    "note_id": event.get("event_id") or event.get("review_event_id"),
                    "source_workflow": "fact_review",
                    "author": event.get("actor_user_id") or event.get("reviewed_by"),
                    "timestamp": event.get("created_at"),
                    "app_key": app_key,
                    "visibility": "internal",
                    "authority_state": "hr_confirmed",
                    "body": event.get("note"),
                }
            )
        for event in store.list_classification_review_events(company_code=company, app_key=app_key):
            if not _norm(event.get("reason") or event.get("note")):
                continue
            items.append(
                {
                    "note_id": event.get("event_id") or event.get("review_event_id"),
                    "source_workflow": "classification_review",
                    "author": event.get("actor_user_id") or event.get("reviewed_by"),
                    "timestamp": event.get("created_at"),
                    "app_key": app_key,
                    "visibility": "internal",
                    "authority_state": "hr_confirmed",
                    "body": event.get("reason") or event.get("note"),
                }
            )
        facet = store.get_screening_facet(company_code=company, app_key=app_key)
        screening = facet.get("screening") if isinstance(facet, dict) and isinstance(facet.get("screening"), dict) else {}
        if isinstance(screening.get("notes"), str) and screening.get("notes").strip():
            items.append(
                {
                    "note_id": f"screening-note:{app_key}",
                    "source_workflow": "screening",
                    "author": screening.get("notes_author") or "system",
                    "timestamp": screening.get("notes_at") or screening.get("last_answered_at"),
                    "app_key": app_key,
                    "visibility": "internal",
                    "authority_state": "operational_mirror",
                    "body": screening.get("notes"),
                }
            )

    for interview in interviews_payload or []:
        for note in interview.get("human_feedback_notes") or []:
            items.append(
                {
                    "note_id": f"interview-note:{interview.get('interview_id')}:{note.get('submission_id') or 'record'}",
                    "source_workflow": "interview",
                    "author": note.get("author") or "interviewer",
                    "timestamp": interview.get("timestamps", {}).get("completed_at") or interview.get("timestamps", {}).get("created_at"),
                    "app_key": interview.get("app_key"),
                    "visibility": "internal",
                    "authority_state": "hr_confirmed",
                    "body": note.get("text"),
                }
            )

    for attempt in store.list_assessment_attempts(company_code=company, app_keys=list(app_keys)):
        if not _norm(attempt.get("review_notes")):
            continue
        items.append(
            {
                "note_id": f"assessment-review:{attempt.get('attempt_id')}",
                "source_workflow": "assessment_review",
                "author": attempt.get("reviewed_by"),
                "timestamp": attempt.get("reviewed_at") or attempt.get("completed_at"),
                "app_key": attempt.get("app_key"),
                "visibility": "internal",
                "authority_state": "hr_confirmed",
                "body": attempt.get("review_notes"),
            }
        )

    if can_manage:
        for app_key in [_norm(item) for item in app_keys if _norm(item)]:
            # Identity notes only with candidate.manage; do not expose match phones.
            for review in store.list_identity_reviews(
                company_code=company,
                app_key=app_key,
                candidate_phone=candidate_phone,
            ):
                if not _norm(review.get("resolution_note")):
                    continue
                items.append(
                    {
                        "note_id": f"identity-review:{review.get('review_id')}",
                        "source_workflow": "identity_review",
                        "author": review.get("resolved_by"),
                        "timestamp": review.get("resolved_at") or review.get("created_at"),
                        "app_key": app_key,
                        "visibility": "restricted_manage",
                        "authority_state": "hr_confirmed",
                        "body": review.get("resolution_note"),
                    }
                )

    items.sort(key=lambda item: str(item.get("timestamp") or ""), reverse=True)
    if not items:
        return SectionRead(
            section="notes",
            payload={
                "items": [],
                "complete_hr_note_history": False,
                "note": "No single canonical freeform HR notes authority exists.",
            },
            coverage=_coverage("notes", "not_recorded", "no_federated_notes"),
        )
    return SectionRead(
        section="notes",
        payload={
            "items": items,
            "complete_hr_note_history": False,
            "note": "Federated workflow-owned notes only; not a complete HR notes history.",
        },
        coverage=_coverage("notes", "partial" if not can_manage else "available", "workflow_owned_notes_federation"),
        evidence=evidence,
    )


def read_identity_state(
    store: Any,
    *,
    company_code: str,
    app_key: str,
    candidate_phone: str,
    permissions: tuple[str, ...] | list[str] = (),
    read_projection: str = "full",
) -> SectionRead:
    company = _norm(company_code).upper()
    if read_projection in {"denied", "not_authorized"}:
        return SectionRead(
            section="identity_state",
            payload={},
            coverage=_coverage("identity_state", "not_authorized", "read_projection_denied"),
        )
    if read_projection in {"restricted", "metadata_only"}:
        return SectionRead(
            section="identity_state",
            payload={"state": "restricted", "suppressed": True, "open_identity_review_resolves": False},
            coverage=_coverage("identity_state", "restricted", "metadata_only"),
        )

    can_manage = MANAGE_PERMISSION in { _norm(item) for item in permissions }
    reviews = store.list_identity_reviews(
        company_code=company,
        app_key=app_key,
        candidate_phone=candidate_phone,
    )
    resolutions = store.list_identity_resolutions(
        company_code=company,
        app_key=app_key,
        candidate_phone=candidate_phone,
    )
    keys = store.list_identity_keys(company_code=company, candidate_phone=candidate_phone)

    open_reviews = [
        item for item in reviews if _norm(item.get("status")).lower() in {"open", "pending", "in_review"}
    ]
    conflict_reviews = [
        item
        for item in reviews
        if _norm(item.get("status")).lower() == "conflict"
        or _norm(item.get("review_type")).lower() == "conflict"
    ]
    conflict_resolutions = [
        item for item in resolutions if _norm(item.get("outcome")).lower() in {"conflict", "possible_match"}
    ]

    if conflict_reviews or any(_norm(item.get("outcome")).lower() == "conflict" for item in resolutions):
        state = "conflict"
    elif open_reviews:
        state = "open_review"
    elif any(_norm(item.get("outcome")).lower() in {"safe_exact_reuse", "new_candidate", "resolved"} for item in resolutions):
        state = "resolved"
    elif keys and not resolutions and not reviews:
        state = "provisional"
    elif not reviews and not resolutions and not keys:
        state = "not_governed_by_current_identity_authority"
    else:
        state = "provisional"

    strong_key_types = sorted(
        {
            _norm(item.get("key_type"))
            for item in keys
            if _norm(item.get("key_type")) and _norm(item.get("authority")).lower() in {"strong", "exact", "canonical", ""}
        }
        | {
            _norm(t)
            for res in resolutions
            for t in (res.get("strong_key_types") or [])
            if _norm(t)
        }
    )

    payload: dict[str, Any] = {
        "state": state,
        "open_identity_review_resolves": False,
        "policy_version": next(
            (_norm(item.get("policy_version")) for item in resolutions if _norm(item.get("policy_version"))),
            None,
        ),
        "resolution_reference": _norm(resolutions[0].get("resolution_id")) if resolutions else None,
        "strong_key_types": strong_key_types,
        "warning": "Identity is unresolved; Candidate Knowledge does not merge or select candidates."
        if state in {"open_review", "conflict", "provisional"}
        else None,
    }

    evidence = []
    if reviews or resolutions:
        evidence.append(
            EvidenceRef(
                evidence_id=_evidence_id(company, app_key, "identity", state),
                source_kind="inbound_cv_identity_reviews",
                source_record_id=_norm((reviews[0] if reviews else resolutions[0]).get("review_id") or (resolutions[0].get("resolution_id") if resolutions else "none")),
                company_code=company,
                app_key=app_key,
                authority_level="canonical",
                review_state="unreviewed" if state == "open_review" else "hr_confirmed",
            )
        )

    if can_manage:
        payload["detail"] = {
            "open_review_count": len(open_reviews),
            "conflict_count": len(conflict_reviews) + len([r for r in conflict_resolutions if _norm(r.get("outcome")).lower() == "conflict"]),
            "review_ids": [_norm(item.get("review_id")) for item in reviews[:20]],
            "resolution_notes": [
                {
                    "review_id": item.get("review_id"),
                    "resolution_note": item.get("resolution_note"),
                    "status": item.get("status"),
                }
                for item in reviews
                if _norm(item.get("resolution_note"))
            ],
            # Explicitly omit unrelated possible-match identity values from default; manage gets counts only.
            "possible_match_identities_exposed": False,
        }
    else:
        payload["detail_denied"] = True
        payload["detail_requires"] = MANAGE_PERMISSION

    coverage_state: CoverageState = "available" if reviews or resolutions or keys else "not_recorded"
    if state == "conflict":
        coverage_state = "conflict"
    return SectionRead(
        section="identity_state",
        payload=payload,
        coverage=_coverage("identity_state", coverage_state, f"identity_{state}"),
        evidence=evidence,
    )


__all__ = [
    "PHASE3_READER_VERSION",
    "MANAGE_PERMISSION",
    "read_applications",
    "read_screening_evidence",
    "read_assessments",
    "read_interviews",
    "read_ranking_evaluations",
    "read_notes",
    "read_identity_state",
]
