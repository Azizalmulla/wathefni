-- Wave 1 — Probation authority schema (version 1.0.0)
-- Dark until WATHEFNI_PROBATION=on + company allowlist + company enable.
-- HARD: binds to canonical employment. OPTIONAL: offer term sync / onboarding start mode.

CREATE TABLE IF NOT EXISTS probation_settings (
  company_code text PRIMARY KEY,
  enabled boolean NOT NULL DEFAULT false,
  auto_plan_on_hire boolean NOT NULL DEFAULT true,
  start_mode text NOT NULL DEFAULT 'hire_date',
  default_probation_days integer NOT NULL DEFAULT 90,
  updated_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT probation_settings_start_mode_chk
    CHECK (start_mode IN ('hire_date', 'onboarding_complete'))
);

CREATE TABLE IF NOT EXISTS probation_plan_templates (
  template_id text NOT NULL,
  company_code text NOT NULL,
  version text NOT NULL DEFAULT '1.0.0',
  title_en text NOT NULL,
  title_ar text,
  active boolean NOT NULL DEFAULT true,
  metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (company_code, template_id)
);

CREATE TABLE IF NOT EXISTS probation_plan_template_milestones (
  company_code text NOT NULL,
  template_id text NOT NULL,
  milestone_key text NOT NULL,
  title_en text NOT NULL,
  title_ar text,
  offset_days integer NOT NULL,
  sort_order integer NOT NULL DEFAULT 0,
  metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
  PRIMARY KEY (company_code, template_id, milestone_key)
);

CREATE TABLE IF NOT EXISTS probation_cases (
  case_id uuid PRIMARY KEY,
  company_code text NOT NULL,
  employee_key text NOT NULL,
  employment_id text,
  status text NOT NULL,
  probation_start date NOT NULL,
  probation_end date NOT NULL,
  template_id text NOT NULL DEFAULT 'default_kuwait_30_60_90',
  template_version text NOT NULL DEFAULT '1.0.0',
  manager_user_id text,
  decision_reason text,
  decided_by_user_id text,
  decided_at timestamptz,
  extension_count integer NOT NULL DEFAULT 0,
  row_version integer NOT NULL DEFAULT 1,
  idempotency_key text,
  metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT probation_cases_status_chk
    CHECK (status IN (
      'scheduled', 'active', 'under_review',
      'confirmed', 'extended', 'failed', 'cancelled'
    )),
  CONSTRAINT probation_cases_dates_chk
    CHECK (probation_end >= probation_start)
);

CREATE UNIQUE INDEX IF NOT EXISTS probation_cases_open_uniq
  ON probation_cases (company_code, employee_key)
  WHERE status IN ('scheduled', 'active', 'under_review', 'extended');

CREATE UNIQUE INDEX IF NOT EXISTS probation_cases_idem_uniq
  ON probation_cases (company_code, idempotency_key)
  WHERE idempotency_key IS NOT NULL AND idempotency_key <> '';

CREATE INDEX IF NOT EXISTS probation_cases_company_status_idx
  ON probation_cases (company_code, status, probation_end);

CREATE TABLE IF NOT EXISTS probation_milestones (
  milestone_id uuid PRIMARY KEY,
  case_id uuid NOT NULL REFERENCES probation_cases(case_id),
  company_code text NOT NULL,
  employee_key text NOT NULL,
  milestone_key text NOT NULL,
  title_en text NOT NULL,
  title_ar text,
  due_on date NOT NULL,
  status text NOT NULL DEFAULT 'pending',
  completed_at timestamptz,
  completed_by_user_id text,
  notes text,
  row_version integer NOT NULL DEFAULT 1,
  metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT probation_milestones_status_chk
    CHECK (status IN ('pending', 'completed', 'skipped', 'overdue')),
  UNIQUE (case_id, milestone_key)
);

CREATE INDEX IF NOT EXISTS probation_milestones_case_idx
  ON probation_milestones (company_code, case_id, status);

CREATE INDEX IF NOT EXISTS probation_milestones_due_idx
  ON probation_milestones (company_code, due_on, status);

CREATE TABLE IF NOT EXISTS probation_events (
  event_id uuid PRIMARY KEY,
  company_code text NOT NULL,
  case_id uuid,
  milestone_id uuid,
  event_type text NOT NULL,
  actor_user_id text,
  payload jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS probation_events_company_idx
  ON probation_events (company_code, created_at DESC);

CREATE INDEX IF NOT EXISTS probation_events_case_idx
  ON probation_events (case_id, created_at DESC);
