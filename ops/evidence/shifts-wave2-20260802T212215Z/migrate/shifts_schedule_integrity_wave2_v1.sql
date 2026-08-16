-- Shifts Wave 2 — schedule integrity schema pack (local/staging).
-- Applied via ensure_shifts_integrity_wave2_schema(); this file is evidence/source of truth.
-- Does NOT: templates, recurring, rotations, publish, open shifts, PAM, Payroll money.

CREATE TABLE IF NOT EXISTS shift_integrity_settings (
  company_code text PRIMARY KEY,
  availability_conflict_mode text NOT NULL DEFAULT 'require_ack',
  seasonal_default_mode text NOT NULL DEFAULT 'warn',
  reminder_max_attempts integer NOT NULL DEFAULT 5,
  reminder_backoff_seconds integer NOT NULL DEFAULT 300,
  updated_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT shift_avail_conflict_mode_chk
    CHECK (availability_conflict_mode IN ('warn','require_ack','block')),
  CONSTRAINT shift_seasonal_default_mode_chk
    CHECK (seasonal_default_mode IN ('warn','block'))
);

CREATE TABLE IF NOT EXISTS shift_assignment_versions (
  version_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  company_code text NOT NULL,
  shift_id uuid NOT NULL,
  version_no integer NOT NULL,
  is_current boolean NOT NULL DEFAULT false,
  effective_at timestamptz NOT NULL DEFAULT now(),
  superseded_at timestamptz,
  reason_code text NOT NULL DEFAULT 'other',
  reason_note text,
  actor_phone text,
  employee_key text,
  previous_employee_key text,
  shift_date date,
  start_time time,
  end_time time,
  ends_next_day boolean NOT NULL DEFAULT false,
  status text,
  snapshot jsonb NOT NULL DEFAULT '{}'::jsonb,
  lineage jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT shift_version_reason_chk CHECK (reason_code <> ''),
  CONSTRAINT shift_version_uniq UNIQUE (company_code, shift_id, version_no)
);
CREATE INDEX IF NOT EXISTS idx_shift_versions_shift
  ON shift_assignment_versions(company_code, shift_id, version_no DESC);
CREATE INDEX IF NOT EXISTS idx_shift_versions_current
  ON shift_assignment_versions(company_code, shift_id) WHERE is_current;

CREATE TABLE IF NOT EXISTS shift_reminder_queue (
  reminder_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  company_code text NOT NULL,
  shift_id uuid NOT NULL,
  employee_key text,
  planned_send_at timestamptz NOT NULL,
  status text NOT NULL DEFAULT 'pending',
  attempt_count integer NOT NULL DEFAULT 0,
  max_attempts integer NOT NULL DEFAULT 5,
  next_attempt_at timestamptz,
  last_error text,
  idempotency_key text NOT NULL,
  delivery_ref text,
  claimed_at timestamptz,
  sent_at timestamptz,
  terminal_at timestamptz,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT shift_reminder_status_chk
    CHECK (status IN ('pending','claimed','sent','failed','terminal_failed','cancelled')),
  CONSTRAINT shift_reminder_idem_uniq UNIQUE (company_code, idempotency_key)
);
CREATE INDEX IF NOT EXISTS idx_shift_reminder_due
  ON shift_reminder_queue(status, next_attempt_at, planned_send_at)
  WHERE status IN ('pending','failed');
CREATE INDEX IF NOT EXISTS idx_shift_reminder_shift
  ON shift_reminder_queue(company_code, shift_id);

CREATE TABLE IF NOT EXISTS shift_seasonal_policies (
  policy_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  company_code text NOT NULL,
  policy_type text NOT NULL,
  name text NOT NULL,
  site_key text,
  branch_key text,
  effective_start date NOT NULL,
  effective_end date NOT NULL,
  window_start time,
  window_end time,
  enforcement_mode text NOT NULL DEFAULT 'warn',
  enabled boolean NOT NULL DEFAULT true,
  metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT shift_seasonal_type_chk
    CHECK (policy_type IN ('ramadan','midday_restriction','custom')),
  CONSTRAINT shift_seasonal_mode_chk
    CHECK (enforcement_mode IN ('warn','block'))
);
CREATE INDEX IF NOT EXISTS idx_shift_seasonal_company_dates
  ON shift_seasonal_policies(company_code, effective_start, effective_end)
  WHERE enabled;

CREATE TABLE IF NOT EXISTS shift_reconciliation_flags (
  flag_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  company_code text NOT NULL,
  shift_id uuid NOT NULL,
  employee_key text,
  flag_type text NOT NULL,
  status text NOT NULL DEFAULT 'open',
  details jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_by_phone text,
  acknowledged_by_phone text,
  created_at timestamptz NOT NULL DEFAULT now(),
  resolved_at timestamptz,
  CONSTRAINT shift_recon_type_chk
    CHECK (flag_type IN ('lifecycle_fact_change','approved_leave_conflict','availability_conflict','seasonal_conflict')),
  CONSTRAINT shift_recon_status_chk
    CHECK (status IN ('open','acknowledged','cancelled','cleared'))
);
CREATE INDEX IF NOT EXISTS idx_shift_recon_open
  ON shift_reconciliation_flags(company_code, status, flag_type);

ALTER TABLE shift_assignments
  ADD COLUMN IF NOT EXISTS current_version_no integer NOT NULL DEFAULT 1;
ALTER TABLE shift_assignments
  ADD COLUMN IF NOT EXISTS schedule_reason_code text;
ALTER TABLE shift_assignments
  ADD COLUMN IF NOT EXISTS lineage_json jsonb NOT NULL DEFAULT '{}'::jsonb;
