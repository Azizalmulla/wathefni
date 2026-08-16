CREATE TABLE IF NOT EXISTS employee_lifecycle_company_policies (
  company_code text PRIMARY KEY,
  tier text NOT NULL DEFAULT 'small',
  timezone text NOT NULL DEFAULT 'Asia/Kuwait',
  notice_hint_monthly_days int NOT NULL DEFAULT 90,
  notice_hint_other_days int NOT NULL DEFAULT 30,
  revoke_mode text NOT NULL DEFAULT 'end_of_last_working_day',
  effective_time_mode text NOT NULL DEFAULT 'start_of_effective_date',
  downstream_mode text NOT NULL DEFAULT 'warn_first',
  require_impact_ack boolean NOT NULL DEFAULT true,
  require_counsel_gate boolean NOT NULL DEFAULT true,
  allow_self_approval boolean NOT NULL DEFAULT false,
  rehire_same_employee_key boolean NOT NULL DEFAULT true,
  scheduler_cadence text NOT NULL DEFAULT 'hourly',
  lag_alert_seconds int NOT NULL DEFAULT 7200,
  policy_json jsonb NOT NULL DEFAULT '{}'::jsonb,
  updated_by_user_id uuid,
  updated_at timestamptz NOT NULL DEFAULT now(),
  created_at timestamptz NOT NULL DEFAULT now(),
  CHECK (tier IN ('small','medium','enterprise')),
  CHECK (revoke_mode IN ('end_of_last_working_day','start_of_effective_date','immediate_on_summary')),
  CHECK (downstream_mode IN ('warn_first','block_submitted_payroll','enterprise_configurable')),
  CHECK (allow_self_approval = false)
);

CREATE TABLE IF NOT EXISTS employee_lifecycle_counsel_reviews (
  review_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  company_code text NOT NULL,
  checklist_version text NOT NULL,
  answers jsonb NOT NULL DEFAULT '{}'::jsonb,
  signed_by_name text NOT NULL,
  signed_by_role text NOT NULL,
  signed_reference text NOT NULL,
  signed_at timestamptz NOT NULL DEFAULT now(),
  status text NOT NULL DEFAULT 'signed',
  notes text,
  UNIQUE (company_code, checklist_version),
  CHECK (status IN ('signed','revoked','expired'))
);

ALTER TABLE IF EXISTS employee_lifecycle_requests
  ADD COLUMN IF NOT EXISTS impact_snapshot_id uuid;
ALTER TABLE IF EXISTS employee_lifecycle_requests
  ADD COLUMN IF NOT EXISTS impact_snapshot_hash text;
ALTER TABLE IF EXISTS employee_lifecycle_requests
  ADD COLUMN IF NOT EXISTS impact_ack_at timestamptz;
ALTER TABLE IF EXISTS employee_lifecycle_requests
  ADD COLUMN IF NOT EXISTS impact_ack_by_user_id uuid;
ALTER TABLE IF EXISTS employee_lifecycle_requests
  ADD COLUMN IF NOT EXISTS impact_ack_text text;

ALTER TABLE IF EXISTS employee_employments
  ADD COLUMN IF NOT EXISTS access_revoke_at timestamptz;
ALTER TABLE IF EXISTS employee_employments
  ADD COLUMN IF NOT EXISTS access_revoked_at timestamptz;
ALTER TABLE IF EXISTS employee_employments
  ADD COLUMN IF NOT EXISTS access_revoke_status text;

CREATE TABLE IF NOT EXISTS employee_lifecycle_settlement_packets (
  packet_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  company_code text NOT NULL,
  employee_key text NOT NULL,
  person_id uuid NOT NULL,
  employment_id uuid NOT NULL,
  case_id uuid,
  request_id uuid,
  status text NOT NULL DEFAULT 'draft',
  packet jsonb NOT NULL DEFAULT '{}'::jsonb,
  handed_off_at timestamptz,
  closed_at timestamptz,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  CHECK (status IN ('draft','handed_to_payroll','closed','cancelled'))
);

CREATE TABLE IF NOT EXISTS employee_lifecycle_downstream_actions (
  action_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  company_code text NOT NULL,
  employee_key text NOT NULL,
  employment_id uuid NOT NULL,
  case_id uuid,
  request_id uuid,
  action_type text NOT NULL,
  status text NOT NULL DEFAULT 'pending',
  idempotency_key text NOT NULL,
  request_hash text NOT NULL,
  payload jsonb NOT NULL DEFAULT '{}'::jsonb,
  result jsonb NOT NULL DEFAULT '{}'::jsonb,
  reverse_of_action_id uuid,
  requester_user_id uuid NOT NULL,
  designated_approver_user_id uuid NOT NULL,
  decided_by_user_id uuid,
  decided_at timestamptz,
  executed_at timestamptz,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  CHECK (status IN ('pending','approved','rejected','cancelled','executed','reversed')),
  CHECK (requester_user_id <> designated_approver_user_id),
  UNIQUE (company_code, idempotency_key)
);

CREATE TABLE IF NOT EXISTS employee_lifecycle_scheduler_runs (
  run_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  company_code text NOT NULL,
  environment text NOT NULL DEFAULT 'staging',
  status text NOT NULL DEFAULT 'started',
  started_at timestamptz NOT NULL DEFAULT now(),
  finished_at timestamptz,
  terminations_executed int NOT NULL DEFAULT 0,
  revokes_executed int NOT NULL DEFAULT 0,
  lag_seconds int,
  error_text text,
  evidence jsonb NOT NULL DEFAULT '{}'::jsonb,
  CHECK (status IN ('started','succeeded','failed','partial'))
);

CREATE TABLE IF NOT EXISTS employee_lifecycle_schema_meta_3c (
  schema_name text PRIMARY KEY,
  schema_version text NOT NULL,
  applied_at timestamptz NOT NULL DEFAULT now()
);

-- Expand Wave 3 case_type CHECKs for cancel_scheduled / reinstate / downstream_action.
ALTER TABLE employee_lifecycle_cases DROP CONSTRAINT IF EXISTS employee_lifecycle_cases_case_type_check;
ALTER TABLE employee_lifecycle_cases
  ADD CONSTRAINT employee_lifecycle_cases_case_type_check
  CHECK (case_type IN (
    'termination','reversal','rehire','notice','suspension','unsuspend','activate_start',
    'cancel_scheduled','reinstate','downstream_action'
  ));
ALTER TABLE employee_lifecycle_requests DROP CONSTRAINT IF EXISTS employee_lifecycle_requests_case_type_check;
-- requests table may not have named case_type check; ignore if absent.
