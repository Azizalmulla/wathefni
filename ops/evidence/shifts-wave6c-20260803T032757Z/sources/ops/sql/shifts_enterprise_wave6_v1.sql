-- Shifts Wave 6A — rotations, remote roster metadata, compliance profiles, PAM export foundation.
-- Staging/synthetic only. Rotations are planning instructions; Wave 5 draft→publish remains the operational gate.
-- Does NOT: submit to PAM, calculate Payroll money, enable real allowlists, deploy to production.

-- Allow rotation as a draft source_kind (additive; drop-and-replace CHECK).
DO $$
BEGIN
  IF EXISTS (
    SELECT 1 FROM information_schema.table_constraints
    WHERE table_name='shift_schedule_draft_rows' AND constraint_name='shift_schedule_draft_rows_source_chk'
  ) THEN
    ALTER TABLE shift_schedule_draft_rows DROP CONSTRAINT shift_schedule_draft_rows_source_chk;
  END IF;
END $$;
ALTER TABLE shift_schedule_draft_rows
  ADD CONSTRAINT shift_schedule_draft_rows_source_chk
  CHECK (source_kind IN ('draft','template_recurrence','manual','open_shift','rollback','rotation'));

CREATE TABLE IF NOT EXISTS shift_rotation_patterns (
  pattern_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  company_code text NOT NULL,
  name text NOT NULL,
  pattern_kind text NOT NULL,
  -- Preset params (nullable depending on kind)
  on_days integer,
  off_days integer,
  hitch_on_days integer,
  hitch_off_days integer,
  -- Arbitrary cycle: [{kind: work|rest|travel|standby, template_slot?: day|night|primary|alternate}]
  cycle_sequence jsonb NOT NULL DEFAULT '[]'::jsonb,
  day_template_id uuid,
  night_template_id uuid,
  timezone text NOT NULL DEFAULT 'Asia/Kuwait',
  remote_defaults jsonb NOT NULL DEFAULT '{}'::jsonb,
  status text NOT NULL DEFAULT 'active',
  created_by_phone text,
  updated_by_phone text,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT shift_rotation_patterns_kind_chk
    CHECK (pattern_kind IN (
      'n_on_m_off','alternating_day_night','panama_223','four_on_four_off',
      'six_on_one_off','hitch_n_n','custom_sequence'
    )),
  CONSTRAINT shift_rotation_patterns_status_chk
    CHECK (status IN ('active','archived'))
);
CREATE INDEX IF NOT EXISTS idx_shift_rotation_patterns_company
  ON shift_rotation_patterns(company_code, status, name);

CREATE TABLE IF NOT EXISTS shift_rotation_assignments (
  assignment_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  company_code text NOT NULL,
  pattern_id uuid NOT NULL REFERENCES shift_rotation_patterns(pattern_id) ON DELETE CASCADE,
  name text NOT NULL,
  target_type text NOT NULL DEFAULT 'employee',
  target_key text NOT NULL,
  employee_key text,
  employee_name text,
  employee_phone text,
  cycle_offset integer NOT NULL DEFAULT 0,
  cycle_anchor_date date NOT NULL,
  effective_start date NOT NULL,
  effective_end date,
  -- Optional remote / industrial planning metadata (never monetary)
  remote_site_key text,
  camp_key text,
  transport_required boolean NOT NULL DEFAULT false,
  transport_group text,
  pickup_location text,
  accommodation_required boolean NOT NULL DEFAULT false,
  mobilization_date date,
  demobilization_date date,
  access_warnings jsonb NOT NULL DEFAULT '[]'::jsonb,
  certification_warnings jsonb NOT NULL DEFAULT '[]'::jsonb,
  remote_meta jsonb NOT NULL DEFAULT '{}'::jsonb,
  status text NOT NULL DEFAULT 'active',
  created_by_phone text,
  updated_by_phone text,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT shift_rotation_assignments_target_chk
    CHECK (target_type IN ('employee','crew','team','site','role')),
  CONSTRAINT shift_rotation_assignments_status_chk
    CHECK (status IN ('active','paused','ended','archived'))
);
CREATE INDEX IF NOT EXISTS idx_shift_rotation_assignments_company
  ON shift_rotation_assignments(company_code, status, effective_start);
CREATE INDEX IF NOT EXISTS idx_shift_rotation_assignments_pattern
  ON shift_rotation_assignments(pattern_id, status);

CREATE TABLE IF NOT EXISTS shift_rotation_events (
  event_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  company_code text NOT NULL,
  pattern_id uuid,
  assignment_id uuid,
  event_type text NOT NULL,
  payload jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_by_phone text,
  created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_shift_rotation_events_company
  ON shift_rotation_events(company_code, created_at DESC);

-- Company policy profiles — default warn; block only when profile says so.
CREATE TABLE IF NOT EXISTS shift_compliance_profiles (
  profile_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  company_code text NOT NULL,
  name text NOT NULL,
  sector_key text,
  enabled boolean NOT NULL DEFAULT true,
  default_enforcement text NOT NULL DEFAULT 'warn',
  -- Profiles: ramadan hours, midday outdoor, daily/weekly hours, breaks, rest days, holidays
  rules jsonb NOT NULL DEFAULT '[]'::jsonb,
  effective_start date,
  effective_end date,
  created_by_phone text,
  updated_at timestamptz NOT NULL DEFAULT now(),
  created_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT shift_compliance_profiles_mode_chk
    CHECK (default_enforcement IN ('warn','block')),
  CONSTRAINT shift_compliance_profiles_uniq UNIQUE (company_code, name)
);
CREATE INDEX IF NOT EXISTS idx_shift_compliance_profiles_company
  ON shift_compliance_profiles(company_code, enabled);

-- PAM declaration/export foundation — read-only export artifacts, no submission.
CREATE TABLE IF NOT EXISTS shift_pam_exports (
  export_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  company_code text NOT NULL,
  period_id uuid REFERENCES shift_schedule_periods(period_id) ON DELETE SET NULL,
  version_id uuid REFERENCES shift_schedule_versions(version_id) ON DELETE SET NULL,
  export_contract_version text NOT NULL,
  locale text NOT NULL DEFAULT 'en',
  status text NOT NULL DEFAULT 'ready',
  fingerprint text NOT NULL,
  payload jsonb NOT NULL DEFAULT '{}'::jsonb,
  csv_en text,
  csv_ar text,
  report_en text,
  report_ar text,
  unsupported_notes jsonb NOT NULL DEFAULT '[]'::jsonb,
  created_by_phone text,
  created_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT shift_pam_exports_status_chk
    CHECK (status IN ('ready','manual_submission_required','unsupported','superseded')),
  CONSTRAINT shift_pam_exports_locale_chk CHECK (locale IN ('en','ar','both'))
);
CREATE INDEX IF NOT EXISTS idx_shift_pam_exports_company
  ON shift_pam_exports(company_code, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_shift_pam_exports_version
  ON shift_pam_exports(version_id);

-- Provenance helpers on draft rows / L0 (additive)
ALTER TABLE shift_schedule_draft_rows ADD COLUMN IF NOT EXISTS rotation_pattern_id uuid;
ALTER TABLE shift_schedule_draft_rows ADD COLUMN IF NOT EXISTS rotation_assignment_id uuid;
ALTER TABLE shift_schedule_draft_rows ADD COLUMN IF NOT EXISTS day_kind text;
ALTER TABLE shift_assignments ADD COLUMN IF NOT EXISTS rotation_pattern_id uuid;
ALTER TABLE shift_assignments ADD COLUMN IF NOT EXISTS rotation_assignment_id uuid;
