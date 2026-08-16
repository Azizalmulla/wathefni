-- Shifts Wave 5 — schedule periods, draft/publish, open shifts, coverage (local/staging).
-- Drafts never write operational L0. Only published versions promote to shift_assignments.
-- Does NOT: advanced rotations, remote hitches, PAM, Payroll money, production deploy.

CREATE TABLE IF NOT EXISTS shift_schedule_periods (
  period_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  company_code text NOT NULL,
  name text NOT NULL,
  status text NOT NULL DEFAULT 'draft',
  start_date date NOT NULL,
  end_date date NOT NULL,
  timezone text NOT NULL DEFAULT 'Asia/Kuwait',
  site_key text,
  branch_key text,
  team_key text,
  require_publish boolean NOT NULL DEFAULT true,
  published_version_id uuid,
  row_version integer NOT NULL DEFAULT 1,
  created_by_phone text,
  updated_by_phone text,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT shift_schedule_periods_status_chk
    CHECK (status IN ('draft','in_review','approved','published','superseded','cancelled')),
  CONSTRAINT shift_schedule_periods_dates_chk CHECK (end_date >= start_date)
);
CREATE INDEX IF NOT EXISTS idx_shift_schedule_periods_company
  ON shift_schedule_periods(company_code, status, start_date);

CREATE TABLE IF NOT EXISTS shift_schedule_versions (
  version_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  company_code text NOT NULL,
  period_id uuid NOT NULL REFERENCES shift_schedule_periods(period_id) ON DELETE CASCADE,
  version_no integer NOT NULL,
  state text NOT NULL DEFAULT 'draft',
  based_on_version_id uuid REFERENCES shift_schedule_versions(version_id),
  rollback_of_version_id uuid REFERENCES shift_schedule_versions(version_id),
  fingerprint text,
  draft_payload jsonb NOT NULL DEFAULT '{}'::jsonb,
  review_diff jsonb NOT NULL DEFAULT '{}'::jsonb,
  coverage_snapshot jsonb NOT NULL DEFAULT '{}'::jsonb,
  publish_idempotency_key text,
  published_at timestamptz,
  approved_at timestamptz,
  submitted_at timestamptz,
  created_by_phone text,
  updated_by_phone text,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT shift_schedule_versions_state_chk
    CHECK (state IN ('draft','in_review','approved','published','superseded','cancelled')),
  CONSTRAINT shift_schedule_versions_uniq UNIQUE (period_id, version_no)
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_shift_schedule_versions_publish_idem
  ON shift_schedule_versions(company_code, publish_idempotency_key)
  WHERE publish_idempotency_key IS NOT NULL AND publish_idempotency_key <> '';
CREATE INDEX IF NOT EXISTS idx_shift_schedule_versions_period
  ON shift_schedule_versions(period_id, state, version_no DESC);

CREATE TABLE IF NOT EXISTS shift_schedule_draft_rows (
  draft_row_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  company_code text NOT NULL,
  period_id uuid NOT NULL REFERENCES shift_schedule_periods(period_id) ON DELETE CASCADE,
  version_id uuid NOT NULL REFERENCES shift_schedule_versions(version_id) ON DELETE CASCADE,
  employee_key text,
  employee_name text,
  employee_phone text,
  shift_date date NOT NULL,
  start_time time NOT NULL,
  end_time time NOT NULL,
  ends_next_day boolean NOT NULL DEFAULT false,
  role text,
  site_key text,
  branch_key text,
  team_key text,
  location text,
  timezone text NOT NULL DEFAULT 'Asia/Kuwait',
  template_id uuid,
  recurrence_id uuid,
  occurrence_key text,
  source_kind text NOT NULL DEFAULT 'draft',
  row_class text,
  conflict_payload jsonb NOT NULL DEFAULT '{}'::jsonb,
  published_shift_id uuid,
  created_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT shift_schedule_draft_rows_source_chk
    CHECK (source_kind IN ('draft','template_recurrence','manual','open_shift','rollback'))
);
CREATE INDEX IF NOT EXISTS idx_shift_schedule_draft_rows_version
  ON shift_schedule_draft_rows(version_id, shift_date);

CREATE TABLE IF NOT EXISTS shift_schedule_events (
  event_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  company_code text NOT NULL,
  period_id uuid,
  version_id uuid,
  event_type text NOT NULL,
  payload jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_by_phone text,
  created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_shift_schedule_events_period
  ON shift_schedule_events(period_id, created_at DESC);

-- Open shifts
CREATE TABLE IF NOT EXISTS shift_open_shifts (
  open_shift_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  company_code text NOT NULL,
  period_id uuid REFERENCES shift_schedule_periods(period_id) ON DELETE SET NULL,
  status text NOT NULL DEFAULT 'open',
  shift_date date NOT NULL,
  start_time time NOT NULL,
  end_time time NOT NULL,
  ends_next_day boolean NOT NULL DEFAULT false,
  role text,
  site_key text,
  branch_key text,
  team_key text,
  location text,
  timezone text NOT NULL DEFAULT 'Asia/Kuwait',
  notes text,
  assigned_employee_key text,
  assigned_shift_id uuid,
  row_version integer NOT NULL DEFAULT 1,
  created_by_phone text,
  updated_by_phone text,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT shift_open_shifts_status_chk
    CHECK (status IN ('open','claimed','approved','rejected','assigned','cancelled'))
);
CREATE INDEX IF NOT EXISTS idx_shift_open_shifts_company
  ON shift_open_shifts(company_code, status, shift_date);

CREATE TABLE IF NOT EXISTS shift_open_shift_claims (
  claim_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  company_code text NOT NULL,
  open_shift_id uuid NOT NULL REFERENCES shift_open_shifts(open_shift_id) ON DELETE CASCADE,
  employee_key text NOT NULL,
  employee_phone text,
  employee_name text,
  status text NOT NULL DEFAULT 'pending',
  decision_note text,
  decided_by_phone text,
  decided_at timestamptz,
  created_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT shift_open_shift_claims_status_chk
    CHECK (status IN ('pending','approved','rejected','withdrawn')),
  CONSTRAINT shift_open_shift_claims_uniq UNIQUE (open_shift_id, employee_key)
);
CREATE INDEX IF NOT EXISTS idx_shift_open_shift_claims_open
  ON shift_open_shift_claims(open_shift_id, status);

-- Coverage rules
CREATE TABLE IF NOT EXISTS shift_coverage_rules (
  rule_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  company_code text NOT NULL,
  name text NOT NULL,
  enabled boolean NOT NULL DEFAULT true,
  role text,
  site_key text,
  branch_key text,
  team_key text,
  effective_start date NOT NULL,
  effective_end date,
  window_start time NOT NULL,
  window_end time NOT NULL,
  ends_next_day boolean NOT NULL DEFAULT false,
  min_staff integer NOT NULL DEFAULT 1,
  enforcement_mode text NOT NULL DEFAULT 'warn',
  created_by_phone text,
  updated_at timestamptz NOT NULL DEFAULT now(),
  created_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT shift_coverage_rules_mode_chk
    CHECK (enforcement_mode IN ('warn','block')),
  CONSTRAINT shift_coverage_rules_min_chk CHECK (min_staff >= 0)
);
CREATE INDEX IF NOT EXISTS idx_shift_coverage_rules_company
  ON shift_coverage_rules(company_code, enabled, effective_start);

-- Provenance on L0 for published rows (additive)
ALTER TABLE shift_assignments ADD COLUMN IF NOT EXISTS schedule_period_id uuid;
ALTER TABLE shift_assignments ADD COLUMN IF NOT EXISTS schedule_version_id uuid;
ALTER TABLE shift_assignments ADD COLUMN IF NOT EXISTS schedule_source text;

CREATE INDEX IF NOT EXISTS idx_shift_assignments_schedule_period
  ON shift_assignments(company_code, schedule_period_id)
  WHERE schedule_period_id IS NOT NULL;
