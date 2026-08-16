"""Read-only Candidate Knowledge store contracts and adapters (Phase 2–3).

Every SQL predicate includes company_code. No writes, locks, schema changes,
OCR, Voyage, or background jobs.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Protocol


def _norm(value: Any) -> str:
    return str(value or "").strip()


def _norm_upper(value: Any) -> str:
    return _norm(value).upper()


class CandidateKnowledgeStore(Protocol):
    """Read-only store. Implementations must not mutate durable state."""

    def get_application(self, *, company_code: str, app_key: str) -> dict[str, Any] | None: ...

    def list_bound_applications(
        self,
        *,
        company_code: str,
        candidate_key: str,
    ) -> list[dict[str, Any]]: ...

    def get_governance(self, *, company_code: str, app_key: str) -> dict[str, Any] | None: ...

    def list_cv_text_versions(self, *, company_code: str, app_key: str) -> list[dict[str, Any]]: ...

    def get_candidate_document(self, *, company_code: str, document_id: str) -> dict[str, Any] | None: ...

    def list_fact_snapshots(self, *, company_code: str, app_key: str) -> list[dict[str, Any]]: ...

    def list_fact_review_events(self, *, company_code: str, app_key: str) -> list[dict[str, Any]]: ...

    def list_classification_runs(self, *, company_code: str, app_key: str) -> list[dict[str, Any]]: ...

    def list_classification_suggestions(self, *, company_code: str, app_key: str) -> list[dict[str, Any]]: ...

    def list_classification_review_events(self, *, company_code: str, app_key: str) -> list[dict[str, Any]]: ...

    def list_classification_invalidations(self, *, company_code: str, app_key: str) -> list[dict[str, Any]]: ...

    def get_taxonomy_release(self, *, taxonomy_version: str) -> dict[str, Any] | None: ...

    def list_taxonomy_nodes(self, *, taxonomy_version: str) -> list[dict[str, Any]]: ...

    # --- Phase 3 ---
    def list_lifecycle_events(self, *, company_code: str, app_key: str) -> list[dict[str, Any]]: ...

    def get_screening_facet(self, *, company_code: str, app_key: str) -> dict[str, Any] | None: ...

    def list_assessment_attempts(self, *, company_code: str, app_keys: list[str]) -> list[dict[str, Any]]: ...

    def list_assessment_scores(self, *, company_code: str, attempt_ids: list[str]) -> list[dict[str, Any]]: ...

    def list_assessment_report_summaries(
        self, *, company_code: str, attempt_ids: list[str]
    ) -> list[dict[str, Any]]: ...

    def list_interviews(self, *, company_code: str, app_keys: list[str]) -> list[dict[str, Any]]: ...

    def list_interview_feedback_submissions(
        self, *, company_code: str, interview_ids: list[str]
    ) -> list[dict[str, Any]]: ...

    def list_rank_evaluations(self, *, company_code: str, app_keys: list[str]) -> list[dict[str, Any]]: ...

    def list_ranking_run_items_for_apps(
        self, *, company_code: str, app_keys: list[str]
    ) -> list[dict[str, Any]]: ...

    def list_application_notes(self, *, company_code: str, app_keys: list[str]) -> list[dict[str, Any]]: ...

    def list_identity_reviews(
        self, *, company_code: str, app_key: str, candidate_phone: str
    ) -> list[dict[str, Any]]: ...

    def list_identity_resolutions(
        self, *, company_code: str, app_key: str, candidate_phone: str
    ) -> list[dict[str, Any]]: ...

    def list_identity_keys(self, *, company_code: str, candidate_phone: str) -> list[dict[str, Any]]: ...


CursorFactory = Callable[[], Any]


def _as_app_key_list(app_keys: list[str]) -> list[str]:
    return [_norm(item) for item in app_keys if _norm(item)]


@dataclass
class PostgresCandidateKnowledgeStore:
    """Minimum production DB adapter for Phase 2–3 reads. Read-only."""

    connect: CursorFactory
    write_attempts: int = 0
    external_calls: int = 0

    def _cursor(self):
        return self.connect()

    def get_application(self, *, company_code: str, app_key: str) -> dict[str, Any] | None:
        company = _norm_upper(company_code)
        key = _norm(app_key)
        if not company or not key:
            return None
        with self._cursor() as cur:
            cur.execute(
                """
                SELECT a.*, c.name AS candidate_name, c.email AS candidate_email
                FROM applications a
                LEFT JOIN candidates c ON c.phone = a.phone
                WHERE a.company_code=%s AND a.app_key=%s
                LIMIT 1
                """,
                (company, key),
            )
            row = cur.fetchone()
            return dict(row) if row else None

    def list_bound_applications(self, *, company_code: str, candidate_key: str) -> list[dict[str, Any]]:
        company = _norm_upper(company_code)
        phone = _norm(candidate_key)
        if not company or not phone:
            return []
        with self._cursor() as cur:
            cur.execute(
                """
                SELECT a.*, c.name AS candidate_name, c.email AS candidate_email
                FROM applications a
                LEFT JOIN candidates c ON c.phone = a.phone
                WHERE a.company_code=%s AND a.phone=%s
                ORDER BY a.app_key ASC
                """,
                (company, phone),
            )
            return [dict(row) for row in cur.fetchall()]

    def get_governance(self, *, company_code: str, app_key: str) -> dict[str, Any] | None:
        company = _norm_upper(company_code)
        key = _norm(app_key)
        if not company or not key:
            return None
        with self._cursor() as cur:
            cur.execute(
                """
                SELECT *
                FROM candidate_record_governance
                WHERE company_code=%s AND app_key=%s
                LIMIT 1
                """,
                (company, key),
            )
            row = cur.fetchone()
            return dict(row) if row else None

    def list_cv_text_versions(self, *, company_code: str, app_key: str) -> list[dict[str, Any]]:
        company = _norm_upper(company_code)
        key = _norm(app_key)
        with self._cursor() as cur:
            cur.execute(
                """
                SELECT *
                FROM candidate_cv_text_versions
                WHERE company_code=%s AND app_key=%s
                ORDER BY created_at DESC NULLS LAST, version_id DESC
                """,
                (company, key),
            )
            return [dict(row) for row in cur.fetchall()]

    def get_candidate_document(self, *, company_code: str, document_id: str) -> dict[str, Any] | None:
        company = _norm_upper(company_code)
        doc = _norm(document_id)
        if not company or not doc:
            return None
        with self._cursor() as cur:
            # Prefer tenant-scoped ownership when company_code column exists on join path via app.
            cur.execute(
                """
                SELECT cd.*
                FROM candidate_documents cd
                JOIN applications a ON a.app_key = cd.app_key
                WHERE a.company_code=%s AND cd.document_id=%s
                LIMIT 1
                """,
                (company, doc),
            )
            row = cur.fetchone()
            return dict(row) if row else None

    def list_fact_snapshots(self, *, company_code: str, app_key: str) -> list[dict[str, Any]]:
        company = _norm_upper(company_code)
        key = _norm(app_key)
        with self._cursor() as cur:
            cur.execute(
                """
                SELECT *
                FROM application_cv_fact_snapshots
                WHERE company_code=%s AND app_key=%s
                ORDER BY materialized_at DESC NULLS LAST, created_at DESC NULLS LAST
                """,
                (company, key),
            )
            return [dict(row) for row in cur.fetchall()]

    def list_fact_review_events(self, *, company_code: str, app_key: str) -> list[dict[str, Any]]:
        company = _norm_upper(company_code)
        key = _norm(app_key)
        with self._cursor() as cur:
            cur.execute(
                """
                SELECT *
                FROM candidate_fact_review_events
                WHERE company_code=%s AND app_key=%s
                ORDER BY created_at ASC
                """,
                (company, key),
            )
            return [dict(row) for row in cur.fetchall()]

    def list_classification_runs(self, *, company_code: str, app_key: str) -> list[dict[str, Any]]:
        company = _norm_upper(company_code)
        key = _norm(app_key)
        with self._cursor() as cur:
            cur.execute(
                """
                SELECT *
                FROM candidate_classification_runs
                WHERE company_code=%s AND app_key=%s
                ORDER BY created_at DESC NULLS LAST
                """,
                (company, key),
            )
            return [dict(row) for row in cur.fetchall()]

    def list_classification_suggestions(self, *, company_code: str, app_key: str) -> list[dict[str, Any]]:
        company = _norm_upper(company_code)
        key = _norm(app_key)
        with self._cursor() as cur:
            cur.execute(
                """
                SELECT *
                FROM candidate_classification_suggestions
                WHERE company_code=%s AND app_key=%s
                ORDER BY created_at DESC NULLS LAST
                """,
                (company, key),
            )
            return [dict(row) for row in cur.fetchall()]

    def list_classification_review_events(self, *, company_code: str, app_key: str) -> list[dict[str, Any]]:
        company = _norm_upper(company_code)
        key = _norm(app_key)
        with self._cursor() as cur:
            cur.execute(
                """
                SELECT *
                FROM candidate_classification_review_events
                WHERE company_code=%s AND app_key=%s
                ORDER BY created_at ASC
                """,
                (company, key),
            )
            return [dict(row) for row in cur.fetchall()]

    def list_classification_invalidations(self, *, company_code: str, app_key: str) -> list[dict[str, Any]]:
        company = _norm_upper(company_code)
        key = _norm(app_key)
        with self._cursor() as cur:
            cur.execute(
                """
                SELECT i.*
                FROM candidate_classification_run_invalidations i
                JOIN candidate_classification_runs r
                  ON r.run_id = i.run_id AND r.company_code = i.company_code
                WHERE i.company_code=%s AND r.app_key=%s
                ORDER BY i.created_at DESC NULLS LAST
                """,
                (company, key),
            )
            return [dict(row) for row in cur.fetchall()]

    def get_taxonomy_release(self, *, taxonomy_version: str) -> dict[str, Any] | None:
        version = _norm(taxonomy_version)
        if not version:
            return None
        with self._cursor() as cur:
            cur.execute(
                """
                SELECT *
                FROM taxonomy_releases
                WHERE taxonomy_version=%s
                LIMIT 1
                """,
                (version,),
            )
            row = cur.fetchone()
            return dict(row) if row else None

    def list_taxonomy_nodes(self, *, taxonomy_version: str) -> list[dict[str, Any]]:
        version = _norm(taxonomy_version)
        if not version:
            return []
        with self._cursor() as cur:
            cur.execute(
                """
                SELECT *
                FROM taxonomy_nodes
                WHERE taxonomy_version=%s
                ORDER BY node_type ASC, node_id ASC
                """,
                (version,),
            )
            return [dict(row) for row in cur.fetchall()]

    def list_lifecycle_events(self, *, company_code: str, app_key: str) -> list[dict[str, Any]]:
        company = _norm_upper(company_code)
        key = _norm(app_key)
        with self._cursor() as cur:
            cur.execute(
                """
                SELECT event_id, company_code, app_key, from_stage, to_stage, trigger,
                       actor_user_id, metadata, created_at
                FROM application_lifecycle_events
                WHERE company_code=%s AND app_key=%s
                ORDER BY created_at DESC NULLS LAST
                """,
                (company, key),
            )
            return [dict(row) for row in cur.fetchall()]

    def get_screening_facet(self, *, company_code: str, app_key: str) -> dict[str, Any] | None:
        company = _norm_upper(company_code)
        key = _norm(app_key)
        with self._cursor() as cur:
            cur.execute(
                """
                SELECT company_code, app_key, screening_status, screening_completed_at,
                       data_source, data_source_detail, updated_at, created_at,
                       raw_json -> 'screening' AS screening
                FROM applications
                WHERE company_code=%s AND app_key=%s
                LIMIT 1
                """,
                (company, key),
            )
            row = cur.fetchone()
            if not row:
                return None
            payload = dict(row)
            # Never return the full raw_json blob through this adapter.
            payload.pop("raw_json", None)
            return payload

    def list_assessment_attempts(self, *, company_code: str, app_keys: list[str]) -> list[dict[str, Any]]:
        company = _norm_upper(company_code)
        keys = _as_app_key_list(app_keys)
        if not keys:
            return []
        with self._cursor() as cur:
            cur.execute(
                """
                SELECT attempt_id, company_code, app_key, phone, battery_key, status,
                       assessment_version_id, expires_at, cancelled_at, cancel_reason,
                       expired_at, review_status, reviewed_at, reviewed_by_user_id AS reviewed_by,
                       review_notes, started_at, completed_at, created_at, updated_at
                FROM assessment_attempts
                WHERE company_code=%s AND app_key = ANY(%s)
                ORDER BY created_at DESC NULLS LAST
                """,
                (company, keys),
            )
            return [dict(row) for row in cur.fetchall()]

    def list_assessment_scores(self, *, company_code: str, attempt_ids: list[str]) -> list[dict[str, Any]]:
        company = _norm_upper(company_code)
        ids = [_norm(item) for item in attempt_ids if _norm(item)]
        if not ids:
            return []
        with self._cursor() as cur:
            cur.execute(
                """
                SELECT s.attempt_id, s.raw_score, s.max_score, s.percent, s.band,
                       s.section_scores, s.norm_version, s.immutable, a.company_code
                FROM assessment_scores s
                JOIN assessment_attempts a ON a.attempt_id = s.attempt_id
                WHERE a.company_code=%s AND s.attempt_id = ANY(%s::uuid[])
                """,
                (company, ids),
            )
            return [dict(row) for row in cur.fetchall()]

    def list_assessment_report_summaries(
        self, *, company_code: str, attempt_ids: list[str]
    ) -> list[dict[str, Any]]:
        company = _norm_upper(company_code)
        ids = [_norm(item) for item in attempt_ids if _norm(item)]
        if not ids:
            return []
        with self._cursor() as cur:
            cur.execute(
                """
                SELECT r.attempt_id, a.company_code,
                       r.report_json ->> 'summary' AS summary,
                       r.report_json -> 'job_match' AS job_match,
                       r.immutable
                FROM assessment_reports r
                JOIN assessment_attempts a ON a.attempt_id = r.attempt_id
                WHERE a.company_code=%s AND r.attempt_id = ANY(%s::uuid[])
                """,
                (company, ids),
            )
            return [dict(row) for row in cur.fetchall()]

    def list_interviews(self, *, company_code: str, app_keys: list[str]) -> list[dict[str, Any]]:
        company = _norm_upper(company_code)
        keys = _as_app_key_list(app_keys)
        if not keys:
            return []
        with self._cursor() as cur:
            cur.execute(
                """
                SELECT interview_id, company_code, app_key, interview_type, status,
                       scheduled_start, scheduled_end, timezone, duration_minutes, location,
                       feedback_status, human_feedback_status, notes,
                       CASE WHEN transcript IS NULL OR btrim(transcript) = '' THEN false ELSE true END
                         AS transcript_available,
                       ai_summary, consent_accepted_at,
                       created_at, updated_at, completed_at
                FROM candidate_interviews
                WHERE company_code=%s AND app_key = ANY(%s)
                ORDER BY COALESCE(scheduled_start, created_at) DESC NULLS LAST
                """,
                (company, keys),
            )
            return [dict(row) for row in cur.fetchall()]

    def list_interview_feedback_submissions(
        self, *, company_code: str, interview_ids: list[str]
    ) -> list[dict[str, Any]]:
        company = _norm_upper(company_code)
        ids = [_norm(item) for item in interview_ids if _norm(item)]
        if not ids:
            return []
        with self._cursor() as cur:
            cur.execute(
                """
                SELECT f.submission_id, f.interview_id, f.company_code, f.status,
                       f.free_text_notes, f.submitted_at, f.created_at, f.updated_at
                FROM interview_feedback_submissions f
                WHERE f.company_code=%s AND f.interview_id = ANY(%s::uuid[])
                ORDER BY COALESCE(f.submitted_at, f.created_at) DESC NULLS LAST
                """,
                (company, ids),
            )
            return [dict(row) for row in cur.fetchall()]

    def list_rank_evaluations(self, *, company_code: str, app_keys: list[str]) -> list[dict[str, Any]]:
        company = _norm_upper(company_code)
        keys = _as_app_key_list(app_keys)
        if not keys:
            return []
        with self._cursor() as cur:
            cur.execute(
                """
                SELECT evaluation_id, company_code, app_key, position_code, position_title,
                       role_profile_key, deterministic_score, score_breakdown,
                       evidence_digest, model, source, created_at
                FROM candidate_rank_evaluations
                WHERE company_code=%s AND app_key = ANY(%s)
                ORDER BY created_at DESC NULLS LAST
                """,
                (company, keys),
            )
            return [dict(row) for row in cur.fetchall()]

    def list_ranking_run_items_for_apps(
        self, *, company_code: str, app_keys: list[str]
    ) -> list[dict[str, Any]]:
        company = _norm_upper(company_code)
        keys = _as_app_key_list(app_keys)
        if not keys:
            return []
        with self._cursor() as cur:
            cur.execute(
                """
                SELECT i.item_id, i.run_id, i.company_code, i.position_code, i.app_key,
                       i.eligibility_bucket, i.advisory_score, i.component_scores,
                       i.requirement_results, i.evidence, i.missing_data, i.evidence_coverage,
                       i.confidence, i.explanation, i.soft_rank, i.created_at,
                       r.is_current, r.stale_reason, r.stale_at, r.scoring_config_version,
                       r.embedding_model, r.criteria_set_id, r.criteria_version, r.job_id,
                       r.job_version, r.request_hash
                FROM ranking_run_items i
                JOIN ranking_runs r
                  ON r.run_id = i.run_id AND r.company_code = i.company_code
                WHERE i.company_code=%s AND i.app_key = ANY(%s)
                ORDER BY i.created_at DESC NULLS LAST
                """,
                (company, keys),
            )
            return [dict(row) for row in cur.fetchall()]

    def list_application_notes(self, *, company_code: str, app_keys: list[str]) -> list[dict[str, Any]]:
        company = _norm_upper(company_code)
        keys = _as_app_key_list(app_keys)
        if not keys:
            return []
        with self._cursor() as cur:
            cur.execute(
                """
                SELECT note_id, company_code, app_key, body, version,
                       created_by_user_id, updated_by_user_id, deleted_at,
                       created_at, updated_at
                FROM application_notes
                WHERE company_code=%s AND app_key = ANY(%s) AND deleted_at IS NULL
                ORDER BY created_at DESC NULLS LAST
                """,
                (company, keys),
            )
            return [dict(row) for row in cur.fetchall()]

    def list_identity_reviews(
        self, *, company_code: str, app_key: str, candidate_phone: str
    ) -> list[dict[str, Any]]:
        company = _norm_upper(company_code)
        key = _norm(app_key)
        phone = _norm(candidate_phone)
        with self._cursor() as cur:
            cur.execute(
                """
                SELECT r.review_id, r.company_code, r.resolution_id, r.status, r.review_type,
                       r.possible_candidate_phones, r.possible_app_keys, r.reason_codes,
                       r.resolution_note, r.created_at, r.resolved_at, r.resolved_by
                FROM inbound_cv_identity_reviews r
                WHERE r.company_code=%s
                  AND (
                    r.possible_app_keys ? %s
                    OR EXISTS (
                      SELECT 1
                      FROM inbound_cv_identity_resolutions res
                      WHERE res.resolution_id = r.resolution_id
                        AND res.company_code = r.company_code
                        AND (
                          res.selected_candidate_phone = %s
                          OR res.selected_app_key = %s
                        )
                    )
                  )
                ORDER BY r.created_at DESC NULLS LAST
                """,
                (company, key, phone, key),
            )
            return [dict(row) for row in cur.fetchall()]

    def list_identity_resolutions(
        self, *, company_code: str, app_key: str, candidate_phone: str
    ) -> list[dict[str, Any]]:
        company = _norm_upper(company_code)
        key = _norm(app_key)
        phone = _norm(candidate_phone)
        with self._cursor() as cur:
            # Production schema uses strong_keys/weak_keys jsonb + identity_policy_version.
            # Project aliases so Phase 3 readers keep a stable contract.
            cur.execute(
                """
                SELECT resolution_id,
                       company_code,
                       outcome,
                       strong_keys AS strong_key_types,
                       weak_keys AS weak_key_types,
                       selected_candidate_phone,
                       selected_app_key,
                       identity_policy_version AS policy_version,
                       created_at
                FROM inbound_cv_identity_resolutions
                WHERE company_code=%s
                  AND (selected_candidate_phone=%s OR selected_app_key=%s)
                ORDER BY created_at DESC NULLS LAST
                """,
                (company, phone, key),
            )
            rows = [dict(row) for row in cur.fetchall()]
        # Normalize jsonb key payloads into type lists when objects are stored.
        for row in rows:
            for field in ("strong_key_types", "weak_key_types"):
                raw = row.get(field)
                if isinstance(raw, list):
                    normalized = []
                    for item in raw:
                        if isinstance(item, dict):
                            normalized.append(item.get("key_type") or item.get("type") or item.get("name") or "")
                        else:
                            normalized.append(item)
                    row[field] = [x for x in normalized if str(x or "").strip()]
        return rows

    def list_identity_keys(self, *, company_code: str, candidate_phone: str) -> list[dict[str, Any]]:
        company = _norm_upper(company_code)
        phone = _norm(candidate_phone)
        with self._cursor() as cur:
            cur.execute(
                """
                SELECT identity_key_id, company_code, candidate_phone, key_type, authority,
                       active, confirmed_at, created_at
                FROM candidate_identity_keys
                WHERE company_code=%s AND candidate_phone=%s AND active = true
                ORDER BY key_type ASC
                """,
                (company, phone),
            )
            return [dict(row) for row in cur.fetchall()]

    def mutate(self, *_args: Any, **_kwargs: Any) -> None:
        self.write_attempts += 1
        raise RuntimeError("Candidate Knowledge store is read-only")


@dataclass
class InMemoryCandidateKnowledgeStore:
    """Deterministic in-memory store for Phase 1–3 tests. Read-only API."""

    applications: list[dict[str, Any]] = field(default_factory=list)
    governance: dict[tuple[str, str], dict[str, Any]] = field(default_factory=dict)
    cv_text_versions: list[dict[str, Any]] = field(default_factory=list)
    documents: list[dict[str, Any]] = field(default_factory=list)
    fact_snapshots: list[dict[str, Any]] = field(default_factory=list)
    fact_review_events: list[dict[str, Any]] = field(default_factory=list)
    classification_runs: list[dict[str, Any]] = field(default_factory=list)
    classification_suggestions: list[dict[str, Any]] = field(default_factory=list)
    classification_review_events: list[dict[str, Any]] = field(default_factory=list)
    classification_invalidations: list[dict[str, Any]] = field(default_factory=list)
    taxonomy_releases: list[dict[str, Any]] = field(default_factory=list)
    taxonomy_nodes: list[dict[str, Any]] = field(default_factory=list)
    lifecycle_events: list[dict[str, Any]] = field(default_factory=list)
    screening_facets: list[dict[str, Any]] = field(default_factory=list)
    assessment_attempts: list[dict[str, Any]] = field(default_factory=list)
    assessment_scores: list[dict[str, Any]] = field(default_factory=list)
    assessment_report_summaries: list[dict[str, Any]] = field(default_factory=list)
    interviews: list[dict[str, Any]] = field(default_factory=list)
    interview_feedback_submissions: list[dict[str, Any]] = field(default_factory=list)
    rank_evaluations: list[dict[str, Any]] = field(default_factory=list)
    ranking_run_items: list[dict[str, Any]] = field(default_factory=list)
    application_notes: list[dict[str, Any]] = field(default_factory=list)
    identity_reviews: list[dict[str, Any]] = field(default_factory=list)
    identity_resolutions: list[dict[str, Any]] = field(default_factory=list)
    identity_keys: list[dict[str, Any]] = field(default_factory=list)
    write_attempts: int = 0
    external_calls: int = 0
    ocr_triggers: int = 0
    ranking_side_effects: int = 0

    def get_application(self, *, company_code: str, app_key: str) -> dict[str, Any] | None:
        company = _norm_upper(company_code)
        key = _norm(app_key)
        for item in self.applications:
            if _norm_upper(item.get("company_code")) == company and _norm(item.get("app_key")) == key:
                return dict(item)
        return None

    def list_bound_applications(self, *, company_code: str, candidate_key: str) -> list[dict[str, Any]]:
        company = _norm_upper(company_code)
        phone = _norm(candidate_key)
        return [
            dict(item)
            for item in self.applications
            if _norm_upper(item.get("company_code")) == company and _norm(item.get("phone")) == phone
        ]

    def get_governance(self, *, company_code: str, app_key: str) -> dict[str, Any] | None:
        return dict(self.governance.get((_norm_upper(company_code), _norm(app_key)), {}))

    def list_cv_text_versions(self, *, company_code: str, app_key: str) -> list[dict[str, Any]]:
        company = _norm_upper(company_code)
        key = _norm(app_key)
        return [
            dict(item)
            for item in self.cv_text_versions
            if _norm_upper(item.get("company_code")) == company and _norm(item.get("app_key")) == key
        ]

    def get_candidate_document(self, *, company_code: str, document_id: str) -> dict[str, Any] | None:
        company = _norm_upper(company_code)
        doc = _norm(document_id)
        for item in self.documents:
            if _norm(item.get("document_id")) != doc:
                continue
            app_key = _norm(item.get("app_key"))
            app = self.get_application(company_code=company, app_key=app_key) if app_key else None
            if app or _norm_upper(item.get("company_code")) == company:
                return dict(item)
        return None

    def list_fact_snapshots(self, *, company_code: str, app_key: str) -> list[dict[str, Any]]:
        company = _norm_upper(company_code)
        key = _norm(app_key)
        return [
            dict(item)
            for item in self.fact_snapshots
            if _norm_upper(item.get("company_code")) == company and _norm(item.get("app_key")) == key
        ]

    def list_fact_review_events(self, *, company_code: str, app_key: str) -> list[dict[str, Any]]:
        company = _norm_upper(company_code)
        key = _norm(app_key)
        rows = [
            dict(item)
            for item in self.fact_review_events
            if _norm_upper(item.get("company_code")) == company and _norm(item.get("app_key")) == key
        ]
        rows.sort(key=lambda item: str(item.get("created_at") or ""))
        return rows

    def list_classification_runs(self, *, company_code: str, app_key: str) -> list[dict[str, Any]]:
        company = _norm_upper(company_code)
        key = _norm(app_key)
        return [
            dict(item)
            for item in self.classification_runs
            if _norm_upper(item.get("company_code")) == company and _norm(item.get("app_key")) == key
        ]

    def list_classification_suggestions(self, *, company_code: str, app_key: str) -> list[dict[str, Any]]:
        company = _norm_upper(company_code)
        key = _norm(app_key)
        return [
            dict(item)
            for item in self.classification_suggestions
            if _norm_upper(item.get("company_code")) == company and _norm(item.get("app_key")) == key
        ]

    def list_classification_review_events(self, *, company_code: str, app_key: str) -> list[dict[str, Any]]:
        company = _norm_upper(company_code)
        key = _norm(app_key)
        rows = [
            dict(item)
            for item in self.classification_review_events
            if _norm_upper(item.get("company_code")) == company and _norm(item.get("app_key")) == key
        ]
        rows.sort(key=lambda item: str(item.get("created_at") or ""))
        return rows

    def list_classification_invalidations(self, *, company_code: str, app_key: str) -> list[dict[str, Any]]:
        company = _norm_upper(company_code)
        key = _norm(app_key)
        run_ids = {
            _norm(item.get("run_id"))
            for item in self.classification_runs
            if _norm_upper(item.get("company_code")) == company and _norm(item.get("app_key")) == key
        }
        return [
            dict(item)
            for item in self.classification_invalidations
            if _norm_upper(item.get("company_code")) == company and _norm(item.get("run_id")) in run_ids
        ]

    def get_taxonomy_release(self, *, taxonomy_version: str) -> dict[str, Any] | None:
        version = _norm(taxonomy_version)
        for item in self.taxonomy_releases:
            if _norm(item.get("taxonomy_version")) == version:
                return dict(item)
        return None

    def list_taxonomy_nodes(self, *, taxonomy_version: str) -> list[dict[str, Any]]:
        version = _norm(taxonomy_version)
        return [dict(item) for item in self.taxonomy_nodes if _norm(item.get("taxonomy_version")) == version]

    def list_lifecycle_events(self, *, company_code: str, app_key: str) -> list[dict[str, Any]]:
        company = _norm_upper(company_code)
        key = _norm(app_key)
        rows = [
            dict(item)
            for item in self.lifecycle_events
            if _norm_upper(item.get("company_code")) == company and _norm(item.get("app_key")) == key
        ]
        rows.sort(key=lambda item: str(item.get("created_at") or ""), reverse=True)
        return rows

    def get_screening_facet(self, *, company_code: str, app_key: str) -> dict[str, Any] | None:
        company = _norm_upper(company_code)
        key = _norm(app_key)
        for item in self.screening_facets:
            if _norm_upper(item.get("company_code")) == company and _norm(item.get("app_key")) == key:
                payload = dict(item)
                payload.pop("raw_json", None)
                return payload
        app = self.get_application(company_code=company, app_key=key)
        if not app:
            return None
        screening = app.get("screening")
        if not isinstance(screening, dict):
            raw = app.get("raw_json")
            if isinstance(raw, dict) and isinstance(raw.get("screening"), dict):
                screening = raw.get("screening")
        if not isinstance(screening, dict) and not app.get("screening_status"):
            return None
        return {
            "company_code": company,
            "app_key": key,
            "screening_status": app.get("screening_status"),
            "screening_completed_at": app.get("screening_completed_at"),
            "data_source": app.get("data_source"),
            "data_source_detail": app.get("data_source_detail"),
            "updated_at": app.get("updated_at"),
            "created_at": app.get("created_at"),
            "screening": dict(screening) if isinstance(screening, dict) else None,
        }

    def list_assessment_attempts(self, *, company_code: str, app_keys: list[str]) -> list[dict[str, Any]]:
        company = _norm_upper(company_code)
        keys = set(_as_app_key_list(app_keys))
        rows = [
            dict(item)
            for item in self.assessment_attempts
            if _norm_upper(item.get("company_code")) == company and _norm(item.get("app_key")) in keys
        ]
        rows.sort(key=lambda item: str(item.get("created_at") or ""), reverse=True)
        return rows

    def list_assessment_scores(self, *, company_code: str, attempt_ids: list[str]) -> list[dict[str, Any]]:
        company = _norm_upper(company_code)
        ids = {_norm(item) for item in attempt_ids if _norm(item)}
        attempt_company = {
            _norm(item.get("attempt_id")): _norm_upper(item.get("company_code"))
            for item in self.assessment_attempts
        }
        return [
            dict(item)
            for item in self.assessment_scores
            if _norm(item.get("attempt_id")) in ids
            and attempt_company.get(_norm(item.get("attempt_id")), _norm_upper(item.get("company_code"))) == company
        ]

    def list_assessment_report_summaries(
        self, *, company_code: str, attempt_ids: list[str]
    ) -> list[dict[str, Any]]:
        company = _norm_upper(company_code)
        ids = {_norm(item) for item in attempt_ids if _norm(item)}
        attempt_company = {
            _norm(item.get("attempt_id")): _norm_upper(item.get("company_code"))
            for item in self.assessment_attempts
        }
        out: list[dict[str, Any]] = []
        for item in self.assessment_report_summaries:
            attempt_id = _norm(item.get("attempt_id"))
            if attempt_id not in ids:
                continue
            if attempt_company.get(attempt_id, _norm_upper(item.get("company_code"))) != company:
                continue
            payload = dict(item)
            # Strip unrestricted report payloads if mistakenly provided.
            payload.pop("report_json", None)
            payload.pop("artifact_paths", None)
            payload.pop("answers", None)
            out.append(payload)
        return out

    def list_interviews(self, *, company_code: str, app_keys: list[str]) -> list[dict[str, Any]]:
        company = _norm_upper(company_code)
        keys = set(_as_app_key_list(app_keys))
        rows = [
            dict(item)
            for item in self.interviews
            if _norm_upper(item.get("company_code")) == company and _norm(item.get("app_key")) in keys
        ]
        rows.sort(
            key=lambda item: str(item.get("scheduled_start") or item.get("created_at") or ""),
            reverse=True,
        )
        return rows

    def list_interview_feedback_submissions(
        self, *, company_code: str, interview_ids: list[str]
    ) -> list[dict[str, Any]]:
        company = _norm_upper(company_code)
        ids = {_norm(item) for item in interview_ids if _norm(item)}
        return [
            dict(item)
            for item in self.interview_feedback_submissions
            if _norm_upper(item.get("company_code")) == company and _norm(item.get("interview_id")) in ids
        ]

    def list_rank_evaluations(self, *, company_code: str, app_keys: list[str]) -> list[dict[str, Any]]:
        company = _norm_upper(company_code)
        keys = set(_as_app_key_list(app_keys))
        rows = [
            dict(item)
            for item in self.rank_evaluations
            if _norm_upper(item.get("company_code")) == company and _norm(item.get("app_key")) in keys
        ]
        rows.sort(key=lambda item: str(item.get("created_at") or ""), reverse=True)
        return rows

    def list_ranking_run_items_for_apps(
        self, *, company_code: str, app_keys: list[str]
    ) -> list[dict[str, Any]]:
        company = _norm_upper(company_code)
        keys = set(_as_app_key_list(app_keys))
        rows = [
            dict(item)
            for item in self.ranking_run_items
            if _norm_upper(item.get("company_code")) == company and _norm(item.get("app_key")) in keys
        ]
        rows.sort(key=lambda item: str(item.get("created_at") or ""), reverse=True)
        return rows

    def list_application_notes(self, *, company_code: str, app_keys: list[str]) -> list[dict[str, Any]]:
        company = _norm_upper(company_code)
        keys = set(_as_app_key_list(app_keys))
        rows = [
            dict(item)
            for item in self.application_notes
            if _norm_upper(item.get("company_code")) == company
            and _norm(item.get("app_key")) in keys
            and not item.get("deleted_at")
        ]
        rows.sort(key=lambda item: str(item.get("created_at") or ""), reverse=True)
        return rows

    def list_identity_reviews(
        self, *, company_code: str, app_key: str, candidate_phone: str
    ) -> list[dict[str, Any]]:
        company = _norm_upper(company_code)
        key = _norm(app_key)
        phone = _norm(candidate_phone)
        rows: list[dict[str, Any]] = []
        for item in self.identity_reviews:
            if _norm_upper(item.get("company_code")) != company:
                continue
            possible_apps = item.get("possible_app_keys") or []
            if isinstance(possible_apps, list) and key in { _norm(x) for x in possible_apps }:
                rows.append(dict(item))
                continue
            if _norm(item.get("app_key")) == key or _norm(item.get("candidate_phone")) == phone:
                rows.append(dict(item))
        rows.sort(key=lambda item: str(item.get("created_at") or ""), reverse=True)
        return rows

    def list_identity_resolutions(
        self, *, company_code: str, app_key: str, candidate_phone: str
    ) -> list[dict[str, Any]]:
        company = _norm_upper(company_code)
        key = _norm(app_key)
        phone = _norm(candidate_phone)
        rows = [
            dict(item)
            for item in self.identity_resolutions
            if _norm_upper(item.get("company_code")) == company
            and (
                _norm(item.get("selected_candidate_phone")) == phone
                or _norm(item.get("selected_app_key")) == key
                or _norm(item.get("app_key")) == key
            )
        ]
        rows.sort(key=lambda item: str(item.get("created_at") or ""), reverse=True)
        return rows

    def list_identity_keys(self, *, company_code: str, candidate_phone: str) -> list[dict[str, Any]]:
        company = _norm_upper(company_code)
        phone = _norm(candidate_phone)
        return [
            dict(item)
            for item in self.identity_keys
            if _norm_upper(item.get("company_code")) == company
            and _norm(item.get("candidate_phone")) == phone
            and item.get("active", True) is not False
        ]

    def mutate(self, *_args: Any, **_kwargs: Any) -> None:
        self.write_attempts += 1
        raise RuntimeError("Candidate Knowledge store is read-only")

    def trigger_ocr(self, *_args: Any, **_kwargs: Any) -> None:
        self.ocr_triggers += 1
        raise RuntimeError("Candidate Knowledge reads must not trigger OCR")

    def call_voyage(self, *_args: Any, **_kwargs: Any) -> None:
        self.external_calls += 1
        raise RuntimeError("Candidate Knowledge must not call Voyage")

    def create_rank_evaluation(self, *_args: Any, **_kwargs: Any) -> None:
        self.ranking_side_effects += 1
        self.write_attempts += 1
        raise RuntimeError("Candidate Knowledge reads must not create ranking evaluations")
