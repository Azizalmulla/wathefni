ALTER TABLE IF EXISTS employee_employments
  ADD COLUMN IF NOT EXISTS lifecycle_state text;
ALTER TABLE IF EXISTS employee_employments
  ADD COLUMN IF NOT EXISTS notice_starts_on date;
ALTER TABLE IF EXISTS employee_employments
  ADD COLUMN IF NOT EXISTS last_working_day date;
ALTER TABLE IF EXISTS employee_employments
  ADD COLUMN IF NOT EXISTS termination_effective_on date;
ALTER TABLE IF EXISTS employee_employments
  ADD COLUMN IF NOT EXISTS termination_type text;
ALTER TABLE IF EXISTS employee_employments
  ADD COLUMN IF NOT EXISTS termination_reason text;
ALTER TABLE IF EXISTS employee_employments
  ADD COLUMN IF NOT EXISTS suspended_on date;
ALTER TABLE IF EXISTS employee_employments
  ADD COLUMN IF NOT EXISTS suspension_reason text;
ALTER TABLE IF EXISTS employee_employments
  ADD COLUMN IF NOT EXISTS lifecycle_version bigint NOT NULL DEFAULT 1;

UPDATE employee_employments
SET lifecycle_state = CASE
  WHEN lower(coalesce(employment_status,'active')) = 'left' THEN 'terminated'
  ELSE 'active'
END
WHERE lifecycle_state IS NULL;

CREATE TABLE IF NOT EXISTS employee_lifecycle_cases (
  case_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  company_code text NOT NULL,
  employee_key text NOT NULL,
  person_id uuid NOT NULL,
  employment_id uuid NOT NULL,
  case_type text NOT NULL,
  status text NOT NULL DEFAULT 'open',
  summary text,
  impact_snapshot_id uuid,
  provenance jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_by_user_id uuid,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  closed_at timestamptz,
  CHECK (case_type IN ('termination','reversal','rehire','notice','suspension','unsuspend','activate_start')),
  CHECK (status IN ('open','pending_approval','executed','cancelled','rejected'))
);

CREATE INDEX IF NOT EXISTS idx_employee_lifecycle_cases_employee
  ON employee_lifecycle_cases (company_code, employee_key, created_at DESC);

CREATE TABLE IF NOT EXISTS employee_lifecycle_requests (
  request_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  company_code text NOT NULL,
  case_id uuid NOT NULL REFERENCES employee_lifecycle_cases(case_id),
  employee_key text NOT NULL,
  person_id uuid NOT NULL,
  employment_id uuid NOT NULL,
  case_type text NOT NULL,
  idempotency_key text NOT NULL,
  request_hash text NOT NULL,
  payload jsonb NOT NULL DEFAULT '{}'::jsonb,
  expected_lifecycle_state text NOT NULL,
  expected_lifecycle_version bigint NOT NULL,
  expected_hub_updated_at timestamptz NOT NULL,
  reason text NOT NULL,
  approval_reference text NOT NULL,
  requester_user_id uuid NOT NULL,
  designated_approver_user_id uuid NOT NULL,
  status text NOT NULL DEFAULT 'pending',
  decision_reason text,
  decided_by_user_id uuid,
  decided_at timestamptz,
  executed_at timestamptz,
  resulting_event_id uuid,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  CHECK (status IN ('pending','approved','rejected','cancelled','executed','expired')),
  CHECK (requester_user_id <> designated_approver_user_id),
  UNIQUE (company_code, idempotency_key)
);

CREATE INDEX IF NOT EXISTS idx_employee_lifecycle_requests_pending
  ON employee_lifecycle_requests (company_code, designated_approver_user_id, status, created_at DESC)
  WHERE status = 'pending';

CREATE TABLE IF NOT EXISTS employee_lifecycle_events (
  event_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  company_code text NOT NULL,
  case_id uuid,
  request_id uuid,
  employee_key text NOT NULL,
  person_id uuid NOT NULL,
  employment_id uuid NOT NULL,
  from_state text,
  to_state text NOT NULL,
  event_type text NOT NULL,
  effective_on date,
  last_working_day date,
  termination_type text,
  reason text,
  actor_user_id uuid,
  payload jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_employee_lifecycle_events_employment
  ON employee_lifecycle_events (company_code, employment_id, created_at DESC);

CREATE TABLE IF NOT EXISTS employee_lifecycle_impact_snapshots (
  snapshot_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  company_code text NOT NULL,
  employee_key text NOT NULL,
  employment_id uuid NOT NULL,
  as_of_date date NOT NULL,
  preview jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS employee_lifecycle_migration_journal (
  journal_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  company_code text NOT NULL,
  action text NOT NULL,
  idempotency_key text NOT NULL,
  before_json jsonb NOT NULL DEFAULT '{}'::jsonb,
  after_json jsonb NOT NULL DEFAULT '{}'::jsonb,
  evidence jsonb NOT NULL DEFAULT '{}'::jsonb,
  status text NOT NULL DEFAULT 'applied',
  created_at timestamptz NOT NULL DEFAULT now(),
  rolled_back_at timestamptz,
  UNIQUE (company_code, idempotency_key)
);

CREATE TABLE IF NOT EXISTS employee_lifecycle_schema_meta (
  schema_name text PRIMARY KEY,
  schema_version text NOT NULL,
  applied_at timestamptz NOT NULL DEFAULT now()
);
