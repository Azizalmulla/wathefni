-- Payroll Authority P2 — Attendance + Leave input assembly (v1.0.0)
-- Additive only. Does NOT unlock Mode A money authority.
-- Does NOT calculate OT/sick/PH/PIFSS money. payment_processing remains disabled.
-- Snapshot is a frozen payroll INPUT view of canonical Attendance/Leave/Shift records.

CREATE TABLE IF NOT EXISTS payroll_input_snapshots (
  input_snapshot_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  company_code text NOT NULL,
  period_id uuid,
  period_start date NOT NULL,
  period_end date NOT NULL,
  status text NOT NULL DEFAULT 'assembling',
  attendance_payroll_mode text NOT NULL DEFAULT 'required',
  attendance_input_source text NOT NULL DEFAULT 'approved_snapshots',
  timezone text NOT NULL DEFAULT 'Asia/Kuwait',
  content_fingerprint text NOT NULL,
  source_fingerprint text NOT NULL,
  policy_context jsonb NOT NULL DEFAULT '{}'::jsonb,
  source_counts jsonb NOT NULL DEFAULT '{}'::jsonb,
  employee_count integer NOT NULL DEFAULT 0,
  issue_blocker_count integer NOT NULL DEFAULT 0,
  issue_warning_count integer NOT NULL DEFAULT 0,
  snapshot_payload jsonb NOT NULL DEFAULT '{}'::jsonb,
  provenance jsonb NOT NULL DEFAULT '{}'::jsonb,
  replaces_snapshot_id uuid,
  superseded_by uuid,
  assembled_at timestamptz NOT NULL DEFAULT now(),
  assembled_by_phone text,
  locked_at timestamptz,
  locked_by_phone text,
  decision_note text,
  payment_processing text NOT NULL DEFAULT 'disabled',
  posts_payment boolean NOT NULL DEFAULT false,
  money_calculated boolean NOT NULL DEFAULT false,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  row_version integer NOT NULL DEFAULT 1,
  CONSTRAINT payroll_input_status_chk
    CHECK (status IN ('assembling', 'needs_review', 'ready', 'locked', 'superseded')),
  CONSTRAINT payroll_input_att_mode_chk
    CHECK (attendance_payroll_mode IN ('required', 'informational', 'ignored')),
  CONSTRAINT payroll_input_att_source_chk
    CHECK (attendance_input_source IN ('legacy_records', 'approved_snapshots')),
  CONSTRAINT payroll_input_payment_disabled_chk
    CHECK (payment_processing = 'disabled'),
  CONSTRAINT payroll_input_no_posts_payment_chk
    CHECK (posts_payment = false),
  CONSTRAINT payroll_input_no_money_chk
    CHECK (money_calculated = false)
);

CREATE UNIQUE INDEX IF NOT EXISTS payroll_input_current_uniq
  ON payroll_input_snapshots (company_code, period_start, period_end)
  WHERE status IN ('assembling', 'needs_review', 'ready', 'locked');

CREATE INDEX IF NOT EXISTS idx_payroll_input_snap_co
  ON payroll_input_snapshots (company_code, period_start DESC, assembled_at DESC);

CREATE INDEX IF NOT EXISTS idx_payroll_input_snap_status
  ON payroll_input_snapshots (company_code, status, assembled_at DESC);

CREATE TABLE IF NOT EXISTS payroll_input_snapshot_employees (
  row_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  input_snapshot_id uuid NOT NULL REFERENCES payroll_input_snapshots(input_snapshot_id),
  company_code text NOT NULL,
  employee_key text NOT NULL,
  employment_start date,
  employment_end date,
  active_start date NOT NULL,
  active_end date NOT NULL,
  mid_period_hire boolean NOT NULL DEFAULT false,
  mid_period_leaver boolean NOT NULL DEFAULT false,
  contract_ids jsonb NOT NULL DEFAULT '[]'::jsonb,
  compensation_effective jsonb NOT NULL DEFAULT '[]'::jsonb,
  attendance_summary jsonb NOT NULL DEFAULT '{}'::jsonb,
  leave_summary jsonb NOT NULL DEFAULT '{}'::jsonb,
  readiness_status text NOT NULL DEFAULT 'ready',
  issue_codes jsonb NOT NULL DEFAULT '[]'::jsonb,
  provenance jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT payroll_input_emp_ready_chk
    CHECK (readiness_status IN ('ready', 'needs_review', 'blocked')),
  UNIQUE (input_snapshot_id, employee_key)
);

CREATE INDEX IF NOT EXISTS idx_payroll_input_emp
  ON payroll_input_snapshot_employees (company_code, employee_key);

CREATE TABLE IF NOT EXISTS payroll_input_snapshot_lines (
  line_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  input_snapshot_id uuid NOT NULL REFERENCES payroll_input_snapshots(input_snapshot_id),
  company_code text NOT NULL,
  employee_key text NOT NULL,
  line_kind text NOT NULL,
  fact_date date,
  fact_end_date date,
  classification text,
  expected_minutes numeric(10,2),
  worked_minutes numeric(10,2),
  absent_minutes numeric(10,2),
  late_minutes numeric(10,2),
  early_departure_minutes numeric(10,2),
  overtime_minutes_fact numeric(10,2),
  chargeable_days numeric(8,4),
  chargeable_hours numeric(10,2),
  is_rest_day boolean NOT NULL DEFAULT false,
  is_public_holiday boolean NOT NULL DEFAULT false,
  overnight_shift boolean NOT NULL DEFAULT false,
  suppressed boolean NOT NULL DEFAULT false,
  suppression_reason text,
  precedence_rule text,
  source_table text,
  source_id text,
  source_version text,
  leave_id text,
  attendance_snapshot_id text,
  projection_id text,
  shift_id text,
  holiday_id text,
  label_en text,
  label_ar text,
  fact_payload jsonb NOT NULL DEFAULT '{}'::jsonb,
  provenance jsonb NOT NULL DEFAULT '{}'::jsonb,
  sort_order integer NOT NULL DEFAULT 0,
  created_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT payroll_input_line_kind_chk
    CHECK (line_kind IN (
      'employment_span',
      'schedule_day',
      'attendance_day',
      'attendance_correction',
      'attendance_incomplete',
      'leave_interval',
      'overtime_fact',
      'rest_day_work_fact',
      'public_holiday_work_fact',
      'calendar_day',
      'compensation_span',
      'suppressed_absence'
    ))
);

CREATE INDEX IF NOT EXISTS idx_payroll_input_lines_snap
  ON payroll_input_snapshot_lines (input_snapshot_id, employee_key, sort_order);

CREATE INDEX IF NOT EXISTS idx_payroll_input_lines_date
  ON payroll_input_snapshot_lines (company_code, employee_key, fact_date);

CREATE TABLE IF NOT EXISTS payroll_input_snapshot_issues (
  issue_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  input_snapshot_id uuid NOT NULL REFERENCES payroll_input_snapshots(input_snapshot_id),
  company_code text NOT NULL,
  employee_key text,
  severity text NOT NULL,
  code text NOT NULL,
  message_en text NOT NULL,
  message_ar text,
  fact_date date,
  source_table text,
  source_id text,
  blocks_lock boolean NOT NULL DEFAULT false,
  payload jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT payroll_input_issue_sev_chk
    CHECK (severity IN ('blocker', 'warning', 'info'))
);

CREATE INDEX IF NOT EXISTS idx_payroll_input_issues_snap
  ON payroll_input_snapshot_issues (input_snapshot_id, severity);

CREATE TABLE IF NOT EXISTS payroll_input_snapshot_events (
  event_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  input_snapshot_id uuid,
  company_code text NOT NULL,
  event_type text NOT NULL,
  payload jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_by_phone text,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_payroll_input_events_co
  ON payroll_input_snapshot_events (company_code, created_at DESC);

-- Company policy: attendance impact on payroll (additive).
ALTER TABLE payroll_company_settings
  ADD COLUMN IF NOT EXISTS attendance_payroll_mode text;

ALTER TABLE payroll_periods
  ADD COLUMN IF NOT EXISTS attendance_payroll_mode text;

-- P1 bridge: sealed money may later point at locked inputs (nullable).
ALTER TABLE payroll_authority_snapshots
  ADD COLUMN IF NOT EXISTS input_snapshot_id uuid;

CREATE INDEX IF NOT EXISTS idx_payroll_auth_snap_input
  ON payroll_authority_snapshots (input_snapshot_id)
  WHERE input_snapshot_id IS NOT NULL;
