"""Canonical authority primitives for Wathefni Assessments Cleanup-1.

This module owns additive schema, immutable content-version snapshots, attempt
states, token/delivery/review facets, and append-only lifecycle events. It has
no provider or SHL integration and deliberately does not import ``app``.
"""

from __future__ import annotations

import hashlib
import json
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any

from psycopg2.extras import Json


ATTEMPT_STATUSES = ("pending", "in_progress", "completed", "cancelled", "expired")
OPEN_ATTEMPT_STATUSES = ("pending", "in_progress")
TERMINAL_ATTEMPT_STATUSES = ("completed", "cancelled", "expired")
DELIVERY_STATUSES = ("pending", "sent", "failed", "intentionally_skipped")
REVIEW_STATUSES = ("unreviewed", "reviewed")
AUTHORING_STATUSES = (
    "ai_draft",
    "automated_review",
    "human_review",
    "pilot",
    "approved",
    "retired",
)
DEFAULT_ATTEMPT_TTL_DAYS = 14


class AssessmentAuthorityError(RuntimeError):
    def __init__(self, code: str, message: str, *, status_code: int = 409, extra: dict[str, Any] | None = None):
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code
        self.extra = dict(extra or {})

    def as_detail(self) -> dict[str, Any]:
        return {"error": self.code, "message": self.message, **self.extra}


def ensure_assessment_schema(cur: Any) -> None:
    """Apply Cleanup-1 schema additively."""

    cur.execute(
        """
        ALTER TABLE assessment_batteries ADD COLUMN IF NOT EXISTS content_version integer NOT NULL DEFAULT 1;
        ALTER TABLE assessment_batteries ADD COLUMN IF NOT EXISTS frozen_at timestamptz;
        ALTER TABLE assessment_batteries ADD COLUMN IF NOT EXISTS retired_at timestamptz;
        ALTER TABLE assessment_batteries ADD COLUMN IF NOT EXISTS scoring_rules_json jsonb NOT NULL DEFAULT '{}'::jsonb;
        ALTER TABLE assessment_batteries ADD COLUMN IF NOT EXISTS report_logic_version text NOT NULL DEFAULT 'wathefni_report_v1';

        ALTER TABLE assessment_items ADD COLUMN IF NOT EXISTS content_version integer NOT NULL DEFAULT 1;
        ALTER TABLE assessment_items ADD COLUMN IF NOT EXISTS authoring_status text NOT NULL DEFAULT 'approved';
        ALTER TABLE assessment_items ADD COLUMN IF NOT EXISTS approved_at timestamptz;
        ALTER TABLE assessment_items ADD COLUMN IF NOT EXISTS retired_at timestamptz;

        CREATE TABLE IF NOT EXISTS assessment_content_versions (
          assessment_version_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
          company_code text NOT NULL,
          battery_key text NOT NULL,
          content_version integer NOT NULL,
          battery_snapshot jsonb NOT NULL,
          items_snapshot jsonb NOT NULL,
          scoring_rules_snapshot jsonb NOT NULL DEFAULT '{}'::jsonb,
          report_logic_version text NOT NULL,
          norm_version text NOT NULL,
          content_sha256 text NOT NULL,
          created_by_user_id text,
          created_at timestamptz NOT NULL DEFAULT now(),
          UNIQUE (company_code, battery_key, content_version),
          UNIQUE (company_code, content_sha256)
        );

        ALTER TABLE assessment_attempts ADD COLUMN IF NOT EXISTS assessment_version_id uuid;
        ALTER TABLE assessment_attempts ADD COLUMN IF NOT EXISTS expires_at timestamptz;
        ALTER TABLE assessment_attempts ADD COLUMN IF NOT EXISTS cancelled_at timestamptz;
        ALTER TABLE assessment_attempts ADD COLUMN IF NOT EXISTS cancel_reason text;
        ALTER TABLE assessment_attempts ADD COLUMN IF NOT EXISTS expired_at timestamptz;
        ALTER TABLE assessment_attempts ADD COLUMN IF NOT EXISTS progress_version integer NOT NULL DEFAULT 0;
        ALTER TABLE assessment_attempts ADD COLUMN IF NOT EXISTS delivery_status text NOT NULL DEFAULT 'pending';
        ALTER TABLE assessment_attempts ADD COLUMN IF NOT EXISTS review_status text NOT NULL DEFAULT 'unreviewed';
        ALTER TABLE assessment_attempts ADD COLUMN IF NOT EXISTS reviewed_at timestamptz;
        ALTER TABLE assessment_attempts ADD COLUMN IF NOT EXISTS reviewed_by_user_id text;
        ALTER TABLE assessment_attempts ADD COLUMN IF NOT EXISTS review_notes text;

        DO $$
        BEGIN
          IF NOT EXISTS (
            SELECT 1 FROM pg_constraint WHERE conname='assessment_attempts_version_fkey'
          ) THEN
            ALTER TABLE assessment_attempts
              ADD CONSTRAINT assessment_attempts_version_fkey
              FOREIGN KEY (assessment_version_id)
              REFERENCES assessment_content_versions(assessment_version_id);
          END IF;
          IF NOT EXISTS (
            SELECT 1 FROM pg_constraint WHERE conname='assessment_attempts_status_check'
          ) THEN
            ALTER TABLE assessment_attempts
              ADD CONSTRAINT assessment_attempts_status_check
              CHECK (status IN ('pending','in_progress','completed','cancelled','expired')) NOT VALID;
          END IF;
          IF NOT EXISTS (
            SELECT 1 FROM pg_constraint WHERE conname='assessment_attempts_delivery_status_check'
          ) THEN
            ALTER TABLE assessment_attempts
              ADD CONSTRAINT assessment_attempts_delivery_status_check
              CHECK (delivery_status IN ('pending','sent','failed','intentionally_skipped')) NOT VALID;
          END IF;
          IF NOT EXISTS (
            SELECT 1 FROM pg_constraint WHERE conname='assessment_attempts_review_status_check'
          ) THEN
            ALTER TABLE assessment_attempts
              ADD CONSTRAINT assessment_attempts_review_status_check
              CHECK (review_status IN ('unreviewed','reviewed')) NOT VALID;
          END IF;
        END $$;

        CREATE UNIQUE INDEX IF NOT EXISTS assessment_attempts_one_open_app_uq
          ON assessment_attempts (company_code, app_key)
          WHERE status IN ('pending','in_progress');
        CREATE INDEX IF NOT EXISTS assessment_attempts_expiry_idx
          ON assessment_attempts (company_code, status, expires_at)
          WHERE status IN ('pending','in_progress');

        ALTER TABLE assessment_responses ADD COLUMN IF NOT EXISTS company_code text;
        ALTER TABLE assessment_responses ADD COLUMN IF NOT EXISTS assessment_version_id uuid;
        ALTER TABLE assessment_responses ADD COLUMN IF NOT EXISTS item_content_version integer;
        ALTER TABLE assessment_responses ADD COLUMN IF NOT EXISTS answer_key_snapshot text;
        ALTER TABLE assessment_responses ADD COLUMN IF NOT EXISTS scoring_snapshot jsonb NOT NULL DEFAULT '{}'::jsonb;
        ALTER TABLE assessment_responses ADD COLUMN IF NOT EXISTS is_final boolean NOT NULL DEFAULT true;

        ALTER TABLE assessment_scores ADD COLUMN IF NOT EXISTS assessment_version_id uuid;
        ALTER TABLE assessment_scores ADD COLUMN IF NOT EXISTS immutable boolean NOT NULL DEFAULT false;
        ALTER TABLE assessment_reports ADD COLUMN IF NOT EXISTS assessment_version_id uuid;
        ALTER TABLE assessment_reports ADD COLUMN IF NOT EXISTS immutable boolean NOT NULL DEFAULT false;

        CREATE TABLE IF NOT EXISTS assessment_events (
          event_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
          attempt_id uuid NOT NULL REFERENCES assessment_attempts(attempt_id) ON DELETE CASCADE,
          company_code text NOT NULL,
          event_type text NOT NULL,
          actor_type text NOT NULL DEFAULT 'system',
          actor_user_id text,
          from_status text,
          to_status text,
          payload_json jsonb NOT NULL DEFAULT '{}'::jsonb,
          created_at timestamptz NOT NULL DEFAULT now()
        );
        CREATE INDEX IF NOT EXISTS assessment_events_attempt_idx
          ON assessment_events (company_code, attempt_id, created_at DESC);

        CREATE TABLE IF NOT EXISTS assessment_tokens (
          token_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
          attempt_id uuid NOT NULL REFERENCES assessment_attempts(attempt_id) ON DELETE CASCADE,
          company_code text NOT NULL,
          token_hash text NOT NULL UNIQUE,
          purpose text NOT NULL DEFAULT 'take',
          expires_at timestamptz NOT NULL,
          used_at timestamptz,
          revoked_at timestamptz,
          revoked_reason text,
          created_at timestamptz NOT NULL DEFAULT now()
        );
        CREATE INDEX IF NOT EXISTS assessment_tokens_attempt_idx
          ON assessment_tokens (company_code, attempt_id, created_at DESC);

        CREATE TABLE IF NOT EXISTS assessment_invitations (
          invitation_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
          attempt_id uuid NOT NULL REFERENCES assessment_attempts(attempt_id) ON DELETE CASCADE,
          company_code text NOT NULL,
          app_key text NOT NULL,
          channel text NOT NULL,
          status text NOT NULL DEFAULT 'pending',
          token_id uuid REFERENCES assessment_tokens(token_id) ON DELETE SET NULL,
          outbound_event_id text,
          message_kind text NOT NULL DEFAULT 'assessment_invite',
          sent_at timestamptz,
          failed_at timestamptz,
          last_error text,
          metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
          created_at timestamptz NOT NULL DEFAULT now(),
          updated_at timestamptz NOT NULL DEFAULT now(),
          CHECK (channel IN ('email','whatsapp')),
          CHECK (status IN ('pending','sent','failed','intentionally_skipped')),
          CHECK (message_kind IN ('assessment_invite','assessment_resend','assessment_reminder'))
        );
        CREATE INDEX IF NOT EXISTS assessment_invitations_attempt_idx
          ON assessment_invitations (company_code, attempt_id, created_at DESC);

        CREATE TABLE IF NOT EXISTS assessment_item_drafts (
          draft_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
          company_code text NOT NULL,
          battery_key text NOT NULL,
          lifecycle_status text NOT NULL DEFAULT 'ai_draft',
          section text NOT NULL,
          competency_tags jsonb NOT NULL DEFAULT '[]'::jsonb,
          skill_tags jsonb NOT NULL DEFAULT '[]'::jsonb,
          role_tags jsonb NOT NULL DEFAULT '[]'::jsonb,
          difficulty text,
          locale text NOT NULL DEFAULT 'en',
          prompt_text text NOT NULL,
          choices jsonb NOT NULL DEFAULT '[]'::jsonb,
          proposed_answer_key text,
          proposed_scoring jsonb NOT NULL DEFAULT '{}'::jsonb,
          rationale text,
          explanation text,
          bias_flags jsonb NOT NULL DEFAULT '[]'::jsonb,
          duplication_flags jsonb NOT NULL DEFAULT '[]'::jsonb,
          ambiguity_flags jsonb NOT NULL DEFAULT '[]'::jsonb,
          leakage_flags jsonb NOT NULL DEFAULT '[]'::jsonb,
          translation_flags jsonb NOT NULL DEFAULT '[]'::jsonb,
          ai_model text,
          source_blueprint_id text,
          human_reviewer_id text,
          reviewed_at timestamptz,
          rejection_reason text,
          created_by_user_id text,
          created_at timestamptz NOT NULL DEFAULT now(),
          updated_at timestamptz NOT NULL DEFAULT now(),
          CHECK (lifecycle_status IN ('ai_draft','automated_review','human_review','pilot','approved','retired')),
          CHECK (locale IN ('en','ar'))
        );
        CREATE INDEX IF NOT EXISTS assessment_item_drafts_company_status_idx
          ON assessment_item_drafts (company_code, battery_key, lifecycle_status, updated_at DESC);

        CREATE TABLE IF NOT EXISTS assessment_item_reviews (
          review_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
          draft_id uuid NOT NULL REFERENCES assessment_item_drafts(draft_id) ON DELETE CASCADE,
          company_code text NOT NULL,
          review_type text NOT NULL,
          reviewer_type text NOT NULL,
          reviewer_id text,
          from_status text,
          to_status text,
          findings_json jsonb NOT NULL DEFAULT '{}'::jsonb,
          notes text,
          created_at timestamptz NOT NULL DEFAULT now()
        );
        CREATE INDEX IF NOT EXISTS assessment_item_reviews_draft_idx
          ON assessment_item_reviews (company_code, draft_id, created_at DESC);

        CREATE TABLE IF NOT EXISTS assessment_blueprint_versions (
          blueprint_version_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
          company_code text NOT NULL,
          blueprint_key text NOT NULL,
          version integer NOT NULL,
          status text NOT NULL DEFAULT 'draft',
          blueprint_json jsonb NOT NULL,
          blueprint_sha256 text NOT NULL,
          created_by_user_id text NOT NULL,
          approved_by_user_id text,
          created_at timestamptz NOT NULL DEFAULT now(),
          approved_at timestamptz,
          retired_at timestamptz,
          UNIQUE (company_code, blueprint_key, version),
          UNIQUE (company_code, blueprint_sha256),
          CHECK (status IN ('draft','approved','retired'))
        );
        CREATE INDEX IF NOT EXISTS assessment_blueprints_company_status_idx
          ON assessment_blueprint_versions (company_code, status, blueprint_key, version DESC);

        CREATE TABLE IF NOT EXISTS assessment_ai_model_registry_versions (
          registry_version_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
          role_key text NOT NULL,
          version integer NOT NULL,
          provider text NOT NULL,
          requested_model text NOT NULL,
          qualified_provider_model_id text,
          api_kind text NOT NULL DEFAULT 'openai-responses',
          capability_requirements jsonb NOT NULL DEFAULT '{}'::jsonb,
          parameter_profile jsonb NOT NULL DEFAULT '{}'::jsonb,
          budget_profile jsonb NOT NULL DEFAULT '{}'::jsonb,
          pricing_snapshot jsonb NOT NULL DEFAULT '{}'::jsonb,
          fallback_policy jsonb NOT NULL DEFAULT '{}'::jsonb,
          allowed_environments text[] NOT NULL DEFAULT ARRAY['staging']::text[],
          prompt_key text NOT NULL,
          output_schema_name text NOT NULL,
          output_schema_version text NOT NULL,
          enabled boolean NOT NULL DEFAULT false,
          approved_by_user_id text NOT NULL,
          activated_at timestamptz,
          retired_at timestamptz,
          created_at timestamptz NOT NULL DEFAULT now(),
          UNIQUE (role_key, version)
        );
        CREATE UNIQUE INDEX IF NOT EXISTS assessment_ai_model_one_active_role_uq
          ON assessment_ai_model_registry_versions (role_key)
          WHERE enabled IS TRUE AND retired_at IS NULL;
        ALTER TABLE assessment_ai_model_registry_versions
          ADD COLUMN IF NOT EXISTS qualified_provider_model_id text;

        CREATE TABLE IF NOT EXISTS assessment_prompt_versions (
          prompt_version_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
          prompt_key text NOT NULL,
          version integer NOT NULL,
          role_key text NOT NULL,
          prompt_text text NOT NULL,
          prompt_sha256 text NOT NULL,
          schema_name text NOT NULL,
          schema_version text NOT NULL,
          schema_sha256 text NOT NULL,
          rubric_version text NOT NULL,
          blueprint_compatibility jsonb NOT NULL DEFAULT '{}'::jsonb,
          created_by_user_id text NOT NULL,
          approved_by_user_id text NOT NULL,
          activated_at timestamptz,
          retired_at timestamptz,
          created_at timestamptz NOT NULL DEFAULT now(),
          UNIQUE (prompt_key, version),
          UNIQUE (prompt_key, prompt_sha256)
        );
        CREATE UNIQUE INDEX IF NOT EXISTS assessment_prompt_one_active_key_uq
          ON assessment_prompt_versions (prompt_key)
          WHERE activated_at IS NOT NULL AND retired_at IS NULL;

        CREATE TABLE IF NOT EXISTS assessment_ai_runs (
          run_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
          company_code text NOT NULL,
          role_key text NOT NULL,
          run_kind text NOT NULL,
          status text NOT NULL DEFAULT 'queued',
          registry_version_id uuid NOT NULL REFERENCES assessment_ai_model_registry_versions(registry_version_id),
          prompt_version_id uuid NOT NULL REFERENCES assessment_prompt_versions(prompt_version_id),
          blueprint_version_id uuid REFERENCES assessment_blueprint_versions(blueprint_version_id),
          draft_id uuid REFERENCES assessment_item_drafts(draft_id) ON DELETE SET NULL,
          draft_revision_id uuid,
          parent_run_id uuid REFERENCES assessment_ai_runs(run_id) ON DELETE SET NULL,
          requested_model text NOT NULL,
          provider_response_model text,
          schema_name text NOT NULL,
          schema_version text NOT NULL,
          schema_sha256 text NOT NULL,
          input_json jsonb NOT NULL,
          output_json jsonb,
          input_sha256 text NOT NULL,
          dedupe_sha256 text NOT NULL,
          output_sha256 text,
          provider_request_id text,
          input_tokens integer,
          output_tokens integer,
          cached_tokens integer,
          estimated_cost_usd numeric,
          pricing_snapshot jsonb NOT NULL DEFAULT '{}'::jsonb,
          latency_ms integer,
          attempt_count integer NOT NULL DEFAULT 0,
          refusal_reason text,
          error_code text,
          error_message text,
          queued_at timestamptz NOT NULL DEFAULT now(),
          started_at timestamptz,
          completed_at timestamptz,
          created_by_user_id text NOT NULL,
          CHECK (run_kind IN ('author_primary','review_secondary','adapt_bilingual','review_bilingual','eval_judge')),
          CHECK (status IN ('queued','running','completed','failed','refused','budget_blocked'))
        );
        CREATE INDEX IF NOT EXISTS assessment_ai_runs_queue_idx
          ON assessment_ai_runs (status, queued_at) WHERE status='queued';
        CREATE INDEX IF NOT EXISTS assessment_ai_runs_company_idx
          ON assessment_ai_runs (company_code, role_key, queued_at DESC);
        ALTER TABLE assessment_ai_runs ADD COLUMN IF NOT EXISTS dedupe_sha256 text;
        UPDATE assessment_ai_runs SET dedupe_sha256=input_sha256 WHERE dedupe_sha256 IS NULL;
        ALTER TABLE assessment_ai_runs ALTER COLUMN dedupe_sha256 SET NOT NULL;
        CREATE INDEX IF NOT EXISTS assessment_ai_runs_dedupe_idx
          ON assessment_ai_runs
          (company_code,role_key,registry_version_id,prompt_version_id,dedupe_sha256);

        CREATE TABLE IF NOT EXISTS assessment_item_draft_revisions (
          draft_revision_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
          draft_id uuid NOT NULL REFERENCES assessment_item_drafts(draft_id) ON DELETE CASCADE,
          company_code text NOT NULL,
          revision integer NOT NULL,
          parent_revision_id uuid REFERENCES assessment_item_draft_revisions(draft_revision_id) ON DELETE SET NULL,
          source_run_id uuid REFERENCES assessment_ai_runs(run_id) ON DELETE SET NULL,
          revision_kind text NOT NULL,
          content_json jsonb NOT NULL,
          content_sha256 text NOT NULL,
          locale text NOT NULL,
          answer_key_id text NOT NULL,
          compiled_scoring_json jsonb NOT NULL DEFAULT '{}'::jsonb,
          compiled_scoring_sha256 text NOT NULL,
          created_by_actor_type text NOT NULL,
          created_by_user_id text,
          created_at timestamptz NOT NULL DEFAULT now(),
          UNIQUE (draft_id, revision),
          UNIQUE (draft_id, content_sha256),
          CHECK (locale IN ('en','ar')),
          CHECK (revision_kind IN ('ai_generated','human_rewrite','bilingual_adaptation')),
          CHECK (created_by_actor_type IN ('ai','human','system'))
        );
        CREATE INDEX IF NOT EXISTS assessment_draft_revisions_company_idx
          ON assessment_item_draft_revisions (company_code, draft_id, revision DESC);

        ALTER TABLE assessment_item_drafts ADD COLUMN IF NOT EXISTS current_revision_id uuid;
        ALTER TABLE assessment_item_drafts ADD COLUMN IF NOT EXISTS blueprint_version_id uuid;
        ALTER TABLE assessment_item_drafts ADD COLUMN IF NOT EXISTS source_run_id uuid;

        DO $$
        BEGIN
          IF NOT EXISTS (
            SELECT 1 FROM pg_constraint WHERE conname='assessment_drafts_current_revision_fkey'
          ) THEN
            ALTER TABLE assessment_item_drafts
              ADD CONSTRAINT assessment_drafts_current_revision_fkey
              FOREIGN KEY (current_revision_id)
              REFERENCES assessment_item_draft_revisions(draft_revision_id);
          END IF;
          IF NOT EXISTS (
            SELECT 1 FROM pg_constraint WHERE conname='assessment_drafts_blueprint_version_fkey'
          ) THEN
            ALTER TABLE assessment_item_drafts
              ADD CONSTRAINT assessment_drafts_blueprint_version_fkey
              FOREIGN KEY (blueprint_version_id)
              REFERENCES assessment_blueprint_versions(blueprint_version_id);
          END IF;
          IF NOT EXISTS (
            SELECT 1 FROM pg_constraint WHERE conname='assessment_drafts_source_run_fkey'
          ) THEN
            ALTER TABLE assessment_item_drafts
              ADD CONSTRAINT assessment_drafts_source_run_fkey
              FOREIGN KEY (source_run_id)
              REFERENCES assessment_ai_runs(run_id);
          END IF;
          IF NOT EXISTS (
            SELECT 1 FROM pg_constraint WHERE conname='assessment_ai_runs_draft_revision_fkey'
          ) THEN
            ALTER TABLE assessment_ai_runs
              ADD CONSTRAINT assessment_ai_runs_draft_revision_fkey
              FOREIGN KEY (draft_revision_id)
              REFERENCES assessment_item_draft_revisions(draft_revision_id);
          END IF;
        END $$;

        CREATE TABLE IF NOT EXISTS assessment_translation_pairs (
          translation_pair_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
          company_code text NOT NULL,
          source_revision_id uuid NOT NULL REFERENCES assessment_item_draft_revisions(draft_revision_id),
          target_revision_id uuid NOT NULL REFERENCES assessment_item_draft_revisions(draft_revision_id),
          source_locale text NOT NULL,
          target_locale text NOT NULL,
          source_sha256 text NOT NULL,
          target_sha256 text NOT NULL,
          pair_sha256 text NOT NULL,
          status text NOT NULL DEFAULT 'automated_review',
          adaptation_run_id uuid REFERENCES assessment_ai_runs(run_id) ON DELETE SET NULL,
          review_run_id uuid REFERENCES assessment_ai_runs(run_id) ON DELETE SET NULL,
          findings_json jsonb NOT NULL DEFAULT '{}'::jsonb,
          human_reviewer_id text,
          reviewed_at timestamptz,
          created_at timestamptz NOT NULL DEFAULT now(),
          UNIQUE (source_revision_id, target_revision_id),
          UNIQUE (company_code, pair_sha256),
          CHECK (source_locale IN ('en','ar')),
          CHECK (target_locale IN ('en','ar')),
          CHECK (source_locale<>target_locale),
          CHECK (status IN ('automated_review','human_review','approved','retired'))
        );
        CREATE INDEX IF NOT EXISTS assessment_translation_pairs_company_idx
          ON assessment_translation_pairs (company_code, status, created_at DESC);

        CREATE TABLE IF NOT EXISTS assessment_eval_runs (
          eval_run_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
          company_code text NOT NULL DEFAULT 'GLOBAL',
          eval_corpus_version text NOT NULL,
          gate_profile_version text NOT NULL,
          role_key text NOT NULL,
          registry_version_id uuid REFERENCES assessment_ai_model_registry_versions(registry_version_id),
          prompt_version_id uuid REFERENCES assessment_prompt_versions(prompt_version_id),
          mode text NOT NULL,
          artifact_sha256 text NOT NULL,
          metrics_json jsonb NOT NULL,
          passed boolean NOT NULL,
          created_by_user_id text NOT NULL,
          created_at timestamptz NOT NULL DEFAULT now(),
          CHECK (mode IN ('recorded_replay','live_staging','blinded_compare','prompt_regression'))
        );
        CREATE INDEX IF NOT EXISTS assessment_eval_runs_role_idx
          ON assessment_eval_runs (role_key, created_at DESC);

        CREATE TABLE IF NOT EXISTS assessment_authoring_events (
          event_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
          company_code text NOT NULL,
          draft_id uuid REFERENCES assessment_item_drafts(draft_id) ON DELETE CASCADE,
          draft_revision_id uuid REFERENCES assessment_item_draft_revisions(draft_revision_id) ON DELETE SET NULL,
          run_id uuid REFERENCES assessment_ai_runs(run_id) ON DELETE SET NULL,
          event_type text NOT NULL,
          actor_type text NOT NULL,
          actor_user_id text,
          from_status text,
          to_status text,
          payload_json jsonb NOT NULL DEFAULT '{}'::jsonb,
          created_at timestamptz NOT NULL DEFAULT now(),
          CHECK (actor_type IN ('ai','human','system'))
        );
        CREATE INDEX IF NOT EXISTS assessment_authoring_events_company_idx
          ON assessment_authoring_events (company_code, draft_id, created_at DESC);
        """
    )


def canonical_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)


def content_digest(payload: dict[str, Any]) -> str:
    return hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()


def token_hash(raw_token: str) -> str:
    return hashlib.sha256(str(raw_token).encode("utf-8")).hexdigest()


def record_event(
    cur: Any,
    *,
    attempt_id: str,
    company_code: str,
    event_type: str,
    actor_type: str = "system",
    actor_user_id: str | None = None,
    from_status: str | None = None,
    to_status: str | None = None,
    payload: dict[str, Any] | None = None,
) -> None:
    cur.execute(
        """
        INSERT INTO assessment_events
          (attempt_id, company_code, event_type, actor_type, actor_user_id,
           from_status, to_status, payload_json)
        VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
        """,
        (
            attempt_id,
            str(company_code or "").upper(),
            event_type,
            actor_type,
            actor_user_id,
            from_status,
            to_status,
            Json(payload or {}),
        ),
    )


def issue_token(
    cur: Any,
    *,
    attempt_id: str,
    company_code: str,
    expires_at: datetime | None = None,
    actor_user_id: str | None = None,
) -> tuple[str, dict[str, Any]]:
    raw_token = secrets.token_urlsafe(32)
    expiry = expires_at or (datetime.now(timezone.utc) + timedelta(days=DEFAULT_ATTEMPT_TTL_DAYS))
    cur.execute(
        """
        INSERT INTO assessment_tokens
          (attempt_id, company_code, token_hash, purpose, expires_at)
        VALUES (%s,%s,%s,'take',%s)
        RETURNING *
        """,
        (attempt_id, str(company_code or "").upper(), token_hash(raw_token), expiry),
    )
    token = dict(cur.fetchone())
    record_event(
        cur,
        attempt_id=attempt_id,
        company_code=company_code,
        event_type="token_issued",
        actor_type="human" if actor_user_id else "system",
        actor_user_id=actor_user_id,
        payload={"token_id": str(token["token_id"]), "expires_at": expiry.isoformat()},
    )
    return raw_token, token


def revoke_active_tokens(
    cur: Any,
    *,
    attempt_id: str,
    company_code: str,
    reason: str,
    actor_type: str = "system",
    actor_user_id: str | None = None,
) -> list[str]:
    cur.execute(
        """
        UPDATE assessment_tokens
        SET revoked_at=COALESCE(revoked_at, now()),
            revoked_reason=COALESCE(revoked_reason, %s)
        WHERE attempt_id=%s AND company_code=%s
          AND revoked_at IS NULL AND expires_at>now()
        RETURNING token_id::text AS token_id
        """,
        (reason, attempt_id, str(company_code or "").upper()),
    )
    revoked = [str(row["token_id"]) for row in cur.fetchall()]
    for token_id in revoked:
        record_event(
            cur,
            attempt_id=attempt_id,
            company_code=company_code,
            event_type="token_revoked",
            actor_type=actor_type,
            actor_user_id=actor_user_id,
            payload={"token_id": token_id, "reason": reason},
        )
    return revoked


def validate_authoring_transition(from_status: str, to_status: str) -> bool:
    allowed = {
        "ai_draft": {"automated_review", "retired"},
        "automated_review": {"human_review", "ai_draft", "retired"},
        "human_review": {"pilot", "ai_draft", "retired"},
        "pilot": {"approved", "human_review", "retired"},
        "approved": {"retired"},
        "retired": set(),
    }
    return to_status == from_status or to_status in allowed.get(from_status, set())
