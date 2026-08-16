-- Wave 1 — Requisitions authority schema (version 1.0.0)
-- Dark until WATHEFNI_REQUISITIONS=on + company allowlist + company_modules.requisitions
-- + (for job gate) jobs_require_approved_requisition when pre_hiring also enabled.

CREATE TABLE IF NOT EXISTS requisition_settings (
  company_code text PRIMARY KEY,
  enabled boolean NOT NULL DEFAULT false,
  jobs_require_approved_requisition boolean NOT NULL DEFAULT true,
  updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS requisitions (
  requisition_id uuid PRIMARY KEY,
  company_code text NOT NULL,
  title_en text NOT NULL,
  title_ar text,
  department text,
  org_unit_id text,
  headcount integer NOT NULL DEFAULT 1,
  target_hire_date date,
  budget_ref text,
  position_id text,
  status text NOT NULL,
  approval_instance_id uuid,
  created_by_user_id text,
  created_by_phone text,
  row_version integer NOT NULL DEFAULT 1,
  idempotency_key text,
  metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT requisitions_status_chk
    CHECK (status IN (
      'draft', 'pending_approval', 'approved', 'rejected',
      'open', 'filled', 'cancelled'
    )),
  CONSTRAINT requisitions_headcount_chk CHECK (headcount >= 1)
);

CREATE UNIQUE INDEX IF NOT EXISTS requisitions_idem_uniq
  ON requisitions (company_code, idempotency_key)
  WHERE idempotency_key IS NOT NULL AND idempotency_key <> '';

CREATE INDEX IF NOT EXISTS requisitions_company_status_idx
  ON requisitions (company_code, status, updated_at DESC);

CREATE TABLE IF NOT EXISTS requisition_job_links (
  link_id uuid PRIMARY KEY,
  company_code text NOT NULL,
  requisition_id uuid NOT NULL REFERENCES requisitions(requisition_id),
  position_code text NOT NULL,
  linked_at timestamptz NOT NULL DEFAULT now(),
  linked_by_user_id text,
  UNIQUE (company_code, position_code)
);

CREATE INDEX IF NOT EXISTS requisition_job_links_req_idx
  ON requisition_job_links (company_code, requisition_id);

CREATE TABLE IF NOT EXISTS requisition_events (
  event_id uuid PRIMARY KEY,
  company_code text NOT NULL,
  requisition_id uuid,
  event_type text NOT NULL,
  actor_user_id text,
  actor_phone text,
  payload jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS requisition_events_company_idx
  ON requisition_events (company_code, created_at DESC);

-- Optional soft pointer on jobs (positions) — no HARD FK.
ALTER TABLE IF EXISTS positions
  ADD COLUMN IF NOT EXISTS requisition_id uuid;
