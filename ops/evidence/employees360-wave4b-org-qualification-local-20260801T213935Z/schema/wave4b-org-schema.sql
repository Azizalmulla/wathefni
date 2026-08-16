
CREATE TABLE IF NOT EXISTS employee_org_schema_meta (
  schema_name text PRIMARY KEY,
  schema_version text NOT NULL,
  updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS employee_org_company_policies (
  company_code text PRIMARY KEY,
  tier text NOT NULL DEFAULT 'small',
  policy_json jsonb NOT NULL DEFAULT '{}'::jsonb,
  updated_by_user_id uuid,
  updated_at timestamptz NOT NULL DEFAULT now(),
  created_at timestamptz NOT NULL DEFAULT now(),
  CHECK (tier IN ('small','medium','enterprise'))
);

CREATE TABLE IF NOT EXISTS employee_org_units (
  org_unit_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  company_code text NOT NULL,
  unit_type text NOT NULL,
  unit_key text NOT NULL,
  name text NOT NULL,
  parent_org_unit_id uuid,
  status text NOT NULL DEFAULT 'active',
  attributes jsonb NOT NULL DEFAULT '{}'::jsonb,
  version int NOT NULL DEFAULT 1,
  effective_from date NOT NULL DEFAULT CURRENT_DATE,
  effective_to date,
  created_by_user_id uuid,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  CHECK (unit_type IN ('legal_employer','branch','department','team','location','position','cost_center')),
  CHECK (status IN ('active','archived')),
  UNIQUE (company_code, unit_type, unit_key)
);

CREATE INDEX IF NOT EXISTS employee_org_units_company_type_idx
  ON employee_org_units (company_code, unit_type, status);

CREATE TABLE IF NOT EXISTS employee_org_assignment_history (
  history_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  company_code text NOT NULL,
  employee_key text NOT NULL,
  person_id uuid,
  employment_id uuid,
  wave2_assignment_id uuid,
  legal_employer_unit_id uuid,
  branch_unit_id uuid,
  department_unit_id uuid,
  team_unit_id uuid,
  location_unit_id uuid,
  position_unit_id uuid,
  cost_center_unit_id uuid,
  manager_employee_key text,
  position_title text,
  effective_from date NOT NULL,
  effective_to date,
  change_type text NOT NULL DEFAULT 'transfer',
  reason text NOT NULL DEFAULT '',
  actor_user_id uuid,
  request_id uuid,
  bulk_job_id uuid,
  batch_id uuid,
  version int NOT NULL DEFAULT 1,
  provenance jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now(),
  CHECK (change_type IN ('transfer','manager_change','job_change','department_change','location_change','bulk_assign','migration','initial')),
  CHECK (effective_to IS NULL OR effective_to >= effective_from)
);

CREATE INDEX IF NOT EXISTS employee_org_assignment_history_emp_idx
  ON employee_org_assignment_history (company_code, employee_key, effective_from DESC);

CREATE INDEX IF NOT EXISTS employee_org_assignment_history_open_idx
  ON employee_org_assignment_history (company_code, employee_key)
  WHERE effective_to IS NULL;

CREATE TABLE IF NOT EXISTS employee_org_change_requests (
  request_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  company_code text NOT NULL,
  employee_key text NOT NULL,
  change_type text NOT NULL,
  effective_on date NOT NULL,
  payload jsonb NOT NULL DEFAULT '{}'::jsonb,
  reason text NOT NULL,
  status text NOT NULL DEFAULT 'pending',
  requester_user_id uuid NOT NULL,
  designated_approver_user_id uuid,
  decided_by_user_id uuid,
  decided_at timestamptz,
  executed_at timestamptz,
  resulting_history_id uuid,
  expected_open_history_id uuid,
  idempotency_key text NOT NULL,
  request_hash text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  CHECK (status IN ('pending','approved','rejected','executed','cancelled','scheduled')),
  CHECK (change_type IN ('transfer','manager_change','job_change','department_change','location_change','bulk_assign','migration','initial')),
  UNIQUE (company_code, idempotency_key)
);

CREATE TABLE IF NOT EXISTS employee_migration_batches (
  batch_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  company_code text NOT NULL,
  filename text NOT NULL,
  status text NOT NULL DEFAULT 'draft',
  tier text NOT NULL DEFAULT 'small',
  column_mapping jsonb NOT NULL DEFAULT '{}'::jsonb,
  validation_summary jsonb NOT NULL DEFAULT '{}'::jsonb,
  provenance jsonb NOT NULL DEFAULT '{}'::jsonb,
  idempotency_key text NOT NULL,
  created_by_user_id uuid,
  paused_at timestamptz,
  committed_at timestamptz,
  rolled_back_at timestamptz,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  CHECK (status IN ('draft','mapped','dry_run','staged','committing','committed','paused','failed','rolled_back')),
  UNIQUE (company_code, idempotency_key)
);

CREATE TABLE IF NOT EXISTS employee_migration_rows (
  row_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  batch_id uuid NOT NULL REFERENCES employee_migration_batches(batch_id) ON DELETE CASCADE,
  company_code text NOT NULL,
  row_number int NOT NULL,
  raw jsonb NOT NULL DEFAULT '{}'::jsonb,
  normalized jsonb NOT NULL DEFAULT '{}'::jsonb,
  status text NOT NULL DEFAULT 'pending',
  conflict_reason text,
  employee_key text,
  person_id uuid,
  history_id uuid,
  review_note text,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  CHECK (status IN ('pending','valid','invalid','duplicate','conflict','needs_review','committed','skipped')),
  UNIQUE (batch_id, row_number)
);

CREATE TABLE IF NOT EXISTS employee_bulk_jobs (
  job_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  company_code text NOT NULL,
  job_type text NOT NULL,
  status text NOT NULL DEFAULT 'pending',
  payload jsonb NOT NULL DEFAULT '{}'::jsonb,
  result jsonb NOT NULL DEFAULT '{}'::jsonb,
  idempotency_key text NOT NULL,
  created_by_user_id uuid,
  reverse_of_job_id uuid,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  finished_at timestamptz,
  CHECK (job_type IN ('bulk_assign','export','reconcile')),
  CHECK (status IN ('pending','running','succeeded','failed','reversed','cancelled')),
  UNIQUE (company_code, idempotency_key)
);

CREATE TABLE IF NOT EXISTS employee_bulk_job_items (
  item_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  job_id uuid NOT NULL REFERENCES employee_bulk_jobs(job_id) ON DELETE CASCADE,
  company_code text NOT NULL,
  employee_key text NOT NULL,
  status text NOT NULL DEFAULT 'pending',
  before_history_id uuid,
  after_history_id uuid,
  error_text text,
  created_at timestamptz NOT NULL DEFAULT now(),
  CHECK (status IN ('pending','applied','skipped','failed','reversed'))
);

CREATE TABLE IF NOT EXISTS employee_org_migration_journal (
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
