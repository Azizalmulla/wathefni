"""Local additive Candidate Knowledge index schema (Phase 4).

Search projection only. Not identity, CV truth, classification, merge, or hiring
authority. Safe to drop and rebuild from CandidateKnowledgeAuthority sources.
"""

from __future__ import annotations

CANDIDATE_KNOWLEDGE_CHUNKS_DDL = """
CREATE TABLE IF NOT EXISTS candidate_knowledge_chunks (
  chunk_id text PRIMARY KEY,
  company_code text NOT NULL,
  candidate_ref text NOT NULL,
  app_key text NOT NULL,
  candidate_key text,
  document_version_id text,
  source_channel text,
  source_family text NOT NULL,
  source_record_id text NOT NULL,
  section_type text NOT NULL,
  chunk_ordinal integer NOT NULL,
  chunk_text text NOT NULL,
  text_hash text NOT NULL,
  language text,
  char_start integer,
  char_end integer,
  token_start integer,
  token_end integer,
  evidence_refs jsonb NOT NULL DEFAULT '[]'::jsonb,
  state text NOT NULL DEFAULT 'current',
  chunker_version text NOT NULL,
  embedding_provider text,
  embedding_model text,
  embedding_dimensions integer,
  embedding_index_version text,
  embedding vector,
  display_name text,
  searchable_metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now(),
  indexed_at timestamptz,
  CHECK (state IN ('current','superseded','invalidated','restricted')),
  UNIQUE (company_code, source_family, source_record_id, chunker_version, chunk_ordinal, text_hash)
);

CREATE INDEX IF NOT EXISTS idx_ck_chunks_tenant_state
  ON candidate_knowledge_chunks (company_code, state, app_key);

CREATE INDEX IF NOT EXISTS idx_ck_chunks_candidate_ref
  ON candidate_knowledge_chunks (company_code, candidate_ref, state);

CREATE INDEX IF NOT EXISTS idx_ck_chunks_version
  ON candidate_knowledge_chunks (company_code, document_version_id, state);

CREATE INDEX IF NOT EXISTS idx_ck_chunks_lexical
  ON candidate_knowledge_chunks
  USING gin (to_tsvector('simple', coalesce(chunk_text, '')));
"""

CANDIDATE_KNOWLEDGE_INDEX_JOBS_DDL = """
CREATE TABLE IF NOT EXISTS candidate_knowledge_index_jobs (
  job_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  company_code text NOT NULL,
  app_key text NOT NULL,
  candidate_ref text,
  document_version_id text,
  source_key text NOT NULL,
  reason text NOT NULL,
  idempotency_key text NOT NULL,
  available_at timestamptz NOT NULL DEFAULT now(),
  attempts integer NOT NULL DEFAULT 0,
  claim_owner text,
  claim_lease_until timestamptz,
  status text NOT NULL DEFAULT 'pending',
  dead_letter boolean NOT NULL DEFAULT false,
  last_error text,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  completed_at timestamptz,
  CHECK (status IN ('pending','claimed','completed','failed','cancelled')),
  UNIQUE (company_code, idempotency_key)
);

CREATE INDEX IF NOT EXISTS idx_ck_index_jobs_claim
  ON candidate_knowledge_index_jobs (company_code, status, available_at)
  WHERE dead_letter = false;
"""

CANDIDATE_KNOWLEDGE_ACCESS_EVENTS_DDL = """
CREATE TABLE IF NOT EXISTS candidate_knowledge_access_events (
  event_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  company_code text NOT NULL,
  actor_user_id text NOT NULL,
  request_id text,
  operation text NOT NULL,
  scope text,
  candidate_ref text,
  retrieval_mode text,
  result_count integer,
  reason_codes jsonb NOT NULL DEFAULT '[]'::jsonb,
  -- Content-free: never store CV text, snippets, contacts, or embeddings.
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_ck_access_events_tenant
  ON candidate_knowledge_access_events (company_code, created_at DESC);
"""

PHASE4_LOCAL_SCHEMA_DDL = "\n".join(
    [
        CANDIDATE_KNOWLEDGE_CHUNKS_DDL,
        CANDIDATE_KNOWLEDGE_INDEX_JOBS_DDL,
        CANDIDATE_KNOWLEDGE_ACCESS_EVENTS_DDL,
    ]
)

CHUNK_STATES = frozenset({"current", "superseded", "invalidated", "restricted"})
INDEX_JOB_STATUSES = frozenset({"pending", "claimed", "completed", "failed", "cancelled"})

__all__ = [
    "PHASE4_LOCAL_SCHEMA_DDL",
    "CANDIDATE_KNOWLEDGE_CHUNKS_DDL",
    "CANDIDATE_KNOWLEDGE_INDEX_JOBS_DDL",
    "CANDIDATE_KNOWLEDGE_ACCESS_EVENTS_DDL",
    "CHUNK_STATES",
    "INDEX_JOB_STATUSES",
]
