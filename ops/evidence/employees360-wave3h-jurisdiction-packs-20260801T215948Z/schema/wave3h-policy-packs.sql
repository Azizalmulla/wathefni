CREATE TABLE IF NOT EXISTS employee_policy_pack_registry (
  pack_code text NOT NULL,
  policy_version text NOT NULL,
  jurisdiction_code text NOT NULL,
  worker_category text NOT NULL,
  status text NOT NULL,
  enabled boolean NOT NULL DEFAULT false,
  effective_from date,
  effective_to date,
  content_hash text NOT NULL,
  pack_json jsonb NOT NULL,
  immutable boolean NOT NULL DEFAULT true,
  created_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (pack_code, policy_version),
  CHECK (status IN ('verified','reserved','deprecated','draft'))
);

CREATE TABLE IF NOT EXISTS employee_policy_pack_tenant_overrides (
  company_code text NOT NULL,
  pack_code text NOT NULL,
  override_json jsonb NOT NULL DEFAULT '{}'::jsonb,
  updated_by_user_id uuid,
  updated_at timestamptz NOT NULL DEFAULT now(),
  created_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (company_code, pack_code)
);

CREATE TABLE IF NOT EXISTS employee_policy_pack_remediation (
  remediation_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  company_code text NOT NULL,
  employee_key text,
  employment_id uuid,
  person_id uuid,
  status text NOT NULL DEFAULT 'open',
  reason_code text NOT NULL,
  detail jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now(),
  resolved_at timestamptz,
  resolved_by_user_id uuid,
  CHECK (status IN ('open','resolved','cancelled'))
);

CREATE INDEX IF NOT EXISTS employee_policy_pack_remediation_open_idx
  ON employee_policy_pack_remediation (company_code, status)
  WHERE status = 'open';

ALTER TABLE IF EXISTS employee_employments
  ADD COLUMN IF NOT EXISTS jurisdiction_code text;
ALTER TABLE IF EXISTS employee_employments
  ADD COLUMN IF NOT EXISTS worker_category text;
ALTER TABLE IF EXISTS employee_employments
  ADD COLUMN IF NOT EXISTS policy_pack_code text;
ALTER TABLE IF EXISTS employee_employments
  ADD COLUMN IF NOT EXISTS policy_pack_version text;
ALTER TABLE IF EXISTS employee_employments
  ADD COLUMN IF NOT EXISTS policy_pack_hash text;
ALTER TABLE IF EXISTS employee_employments
  ADD COLUMN IF NOT EXISTS policy_pack_status text;
-- policy_pack_status: resolved | remediation | unsupported | reserved

ALTER TABLE IF EXISTS employee_lifecycle_requests
  ADD COLUMN IF NOT EXISTS policy_pack_code text;
ALTER TABLE IF EXISTS employee_lifecycle_requests
  ADD COLUMN IF NOT EXISTS policy_pack_version text;
ALTER TABLE IF EXISTS employee_lifecycle_requests
  ADD COLUMN IF NOT EXISTS policy_pack_hash text;
ALTER TABLE IF EXISTS employee_lifecycle_requests
  ADD COLUMN IF NOT EXISTS policy_pack_frozen_at timestamptz;

CREATE TABLE IF NOT EXISTS employee_lifecycle_policy_freezes (
  freeze_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  company_code text NOT NULL,
  request_id uuid NOT NULL,
  case_id uuid,
  employee_key text NOT NULL,
  employment_id uuid,
  pack_code text NOT NULL,
  policy_version text NOT NULL,
  content_hash text NOT NULL,
  pack_snapshot jsonb NOT NULL,
  frozen_at timestamptz NOT NULL DEFAULT now(),
  frozen_by_user_id uuid,
  UNIQUE (company_code, request_id)
);

CREATE TABLE IF NOT EXISTS employee_policy_pack_schema_meta (
  schema_name text PRIMARY KEY,
  schema_version text NOT NULL,
  applied_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS employee_policy_pack_migration_journal (
  journal_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  company_code text NOT NULL,
  action text NOT NULL,
  idempotency_key text NOT NULL,
  before_json jsonb NOT NULL DEFAULT '{}'::jsonb,
  after_json jsonb NOT NULL DEFAULT '{}'::jsonb,
  evidence jsonb NOT NULL DEFAULT '{}'::jsonb,
  status text NOT NULL DEFAULT 'applied',
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (company_code, idempotency_key)
);
