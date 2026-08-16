-- Shifts Wave 4 — templates + recurring schedules (planning instructions only).
-- Generated L0 shift_assignments remain sole operational authority.
-- Does NOT: draft/publish, rotations, coverage, open shifts, PAM, Payroll money.

CREATE TABLE IF NOT EXISTS shift_templates (
  template_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  company_code text NOT NULL,
  name text NOT NULL,
  status text NOT NULL DEFAULT 'active',
  start_time time NOT NULL,
  end_time time NOT NULL,
  ends_next_day boolean NOT NULL DEFAULT false,
  break_minutes integer,
  role text,
  site_key text,
  branch_key text,
  team_key text,
  position_key text,
  location text,
  timezone text NOT NULL DEFAULT 'Asia/Kuwait',
  notes text,
  planning_version integer NOT NULL DEFAULT 1,
  row_version integer NOT NULL DEFAULT 1,
  created_by_phone text,
  updated_by_phone text,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT shift_templates_status_chk CHECK (status IN ('active','archived'))
);
CREATE INDEX IF NOT EXISTS idx_shift_templates_company_status
  ON shift_templates(company_code, status, name);

CREATE TABLE IF NOT EXISTS shift_recurrences (
  recurrence_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  company_code text NOT NULL,
  name text NOT NULL,
  status text NOT NULL DEFAULT 'active',
  template_id uuid NOT NULL REFERENCES shift_templates(template_id),
  alternate_template_id uuid REFERENCES shift_templates(template_id),
  cycle_type text NOT NULL,
  weekdays integer[] NOT NULL DEFAULT ARRAY[]::integer[],
  on_days integer,
  off_days integer,
  cycle_anchor_date date,
  effective_start date NOT NULL,
  effective_end date,
  horizon_days integer NOT NULL DEFAULT 90,
  target_type text NOT NULL,
  target_key text NOT NULL,
  planning_version integer NOT NULL DEFAULT 1,
  row_version integer NOT NULL DEFAULT 1,
  created_by_phone text,
  updated_by_phone text,
  paused_at timestamptz,
  ended_at timestamptz,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT shift_recurrences_status_chk CHECK (status IN ('active','paused','ended')),
  CONSTRAINT shift_recurrences_cycle_chk CHECK (cycle_type IN ('weekly_weekdays','n_on_m_off','alternating_templates')),
  CONSTRAINT shift_recurrences_target_chk CHECK (target_type IN ('employee','team','site','role')),
  CONSTRAINT shift_recurrences_horizon_chk CHECK (horizon_days >= 1 AND horizon_days <= 180)
);
CREATE INDEX IF NOT EXISTS idx_shift_recurrences_company_status
  ON shift_recurrences(company_code, status, effective_start);

CREATE TABLE IF NOT EXISTS shift_recurrence_exceptions (
  exception_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  company_code text NOT NULL,
  recurrence_id uuid NOT NULL REFERENCES shift_recurrences(recurrence_id) ON DELETE CASCADE,
  exception_date date NOT NULL,
  kind text NOT NULL,
  override_template_id uuid REFERENCES shift_templates(template_id),
  override_start_time time,
  override_end_time time,
  notes text,
  created_by_phone text,
  created_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT shift_recurrence_exceptions_kind_chk CHECK (kind IN ('skip','one_off_override')),
  CONSTRAINT shift_recurrence_exceptions_uniq UNIQUE (recurrence_id, exception_date)
);
CREATE INDEX IF NOT EXISTS idx_shift_recurrence_exceptions_rec
  ON shift_recurrence_exceptions(recurrence_id, exception_date);

CREATE TABLE IF NOT EXISTS shift_recurrence_events (
  event_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  company_code text NOT NULL,
  recurrence_id uuid NOT NULL,
  event_type text NOT NULL,
  payload jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_by_phone text,
  created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_shift_recurrence_events_rec
  ON shift_recurrence_events(recurrence_id, created_at DESC);

-- Provenance on L0 authority rows (additive; manual path defaults preserved)
ALTER TABLE shift_assignments ADD COLUMN IF NOT EXISTS source_kind text NOT NULL DEFAULT 'manual';
ALTER TABLE shift_assignments ADD COLUMN IF NOT EXISTS template_id uuid;
ALTER TABLE shift_assignments ADD COLUMN IF NOT EXISTS recurrence_id uuid;
ALTER TABLE shift_assignments ADD COLUMN IF NOT EXISTS occurrence_key text;
ALTER TABLE shift_assignments ADD COLUMN IF NOT EXISTS regen_detached boolean NOT NULL DEFAULT false;
ALTER TABLE shift_assignments ADD COLUMN IF NOT EXISTS generated_from_version text;

CREATE INDEX IF NOT EXISTS idx_shift_assignments_occurrence_key
  ON shift_assignments(company_code, occurrence_key)
  WHERE occurrence_key IS NOT NULL AND occurrence_key <> '';

CREATE INDEX IF NOT EXISTS idx_shift_assignments_recurrence
  ON shift_assignments(company_code, recurrence_id)
  WHERE recurrence_id IS NOT NULL;
