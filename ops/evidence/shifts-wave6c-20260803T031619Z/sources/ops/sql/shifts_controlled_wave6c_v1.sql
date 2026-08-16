-- Shifts Wave 6C — controlled real rollout support tables.
-- Adds: recipient consent registry, controlled-subject exclusions, real-delivery
-- provenance columns, and operator job run ledger (no-overlap / batch proof).
-- Does NOT: enable real delivery by itself, submit to PAM, touch Payroll money,
-- mutate Leave balances, or mutate Attendance authority.

CREATE TABLE IF NOT EXISTS shift_notification_consent (
  consent_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  company_code text NOT NULL,
  employee_key text NOT NULL,
  channel text NOT NULL,
  status text NOT NULL DEFAULT 'granted',
  policy_version text NOT NULL DEFAULT 'shifts-notify@1.0.0',
  destination_ref text,
  granted_by text,
  granted_at timestamptz NOT NULL DEFAULT now(),
  withdrawn_at timestamptz,
  evidence_ref text,
  metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT shift_notification_consent_status_chk
    CHECK (status IN ('granted','withdrawn','pending')),
  CONSTRAINT shift_notification_consent_channel_chk
    CHECK (channel IN ('app','push','whatsapp','teams','telegram','email','sms','web','connector')),
  CONSTRAINT shift_notification_consent_uniq UNIQUE (company_code, employee_key, channel)
);
CREATE INDEX IF NOT EXISTS idx_shift_notification_consent_company
  ON shift_notification_consent(company_code, status);

-- Subjects that look real to the gate but are known residue / probes.
-- Wave 6C must never mutate or notify these.
CREATE TABLE IF NOT EXISTS shift_controlled_exclusions (
  exclusion_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  company_code text NOT NULL,
  subject_pattern text NOT NULL,
  reason text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT shift_controlled_exclusions_uniq UNIQUE (company_code, subject_pattern)
);

-- Real-delivery provenance on the canonical delivery ledger.
ALTER TABLE shift_notification_deliveries
  ADD COLUMN IF NOT EXISTS real_sent boolean NOT NULL DEFAULT false;
ALTER TABLE shift_notification_deliveries
  ADD COLUMN IF NOT EXISTS recipient_ref text;
ALTER TABLE shift_notification_deliveries
  ADD COLUMN IF NOT EXISTS provider_receipt jsonb NOT NULL DEFAULT '{}'::jsonb;

CREATE INDEX IF NOT EXISTS idx_shift_notification_deliveries_real
  ON shift_notification_deliveries(company_code, real_sent, status);

-- Operator job runs: bounded batch, advisory lock, no overlapping execution.
CREATE TABLE IF NOT EXISTS shift_controlled_job_runs (
  run_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  company_code text NOT NULL,
  job_key text NOT NULL,
  lock_id bigint NOT NULL,
  batch_size integer NOT NULL,
  status text NOT NULL DEFAULT 'running',
  claimed integer NOT NULL DEFAULT 0,
  processed integer NOT NULL DEFAULT 0,
  failed integer NOT NULL DEFAULT 0,
  skipped_reason text,
  started_at timestamptz NOT NULL DEFAULT now(),
  finished_at timestamptz,
  error_detail text,
  CONSTRAINT shift_controlled_job_runs_status_chk
    CHECK (status IN ('running','completed','failed','skipped_locked','skipped_disabled'))
);
CREATE INDEX IF NOT EXISTS idx_shift_controlled_job_runs_key
  ON shift_controlled_job_runs(company_code, job_key, started_at DESC);
