CREATE TABLE IF NOT EXISTS employee_ess_schema_meta (
  schema_name text PRIMARY KEY,
  schema_version text NOT NULL,
  updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS employee_ess_requests (
  request_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  company_code text NOT NULL,
  employee_key text NOT NULL,
  employment_id uuid,
  request_type text NOT NULL,
  state text NOT NULL DEFAULT 'draft',
  requester_kind text NOT NULL,
  requester_user_id uuid,
  requester_employee_key text,
  proposed_values jsonb NOT NULL DEFAULT '{}'::jsonb,
  old_value_snapshot jsonb NOT NULL DEFAULT '{}'::jsonb,
  approval_route jsonb NOT NULL DEFAULT '[]'::jsonb,
  approval_cursor int NOT NULL DEFAULT 0,
  comments jsonb NOT NULL DEFAULT '[]'::jsonb,
  evidence jsonb NOT NULL DEFAULT '{}'::jsonb,
  concurrency_version bigint NOT NULL DEFAULT 1,
  expected_hub_updated_at timestamptz,
  expected_assignment_version bigint,
  idempotency_key text NOT NULL,
  request_hash text NOT NULL,
  designated_approver_user_id uuid,
  applied_authority_ref jsonb,
  applied_at timestamptz,
  applied_by_user_id uuid,
  fail_reason text,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  CHECK (state IN (
    'draft','submitted','needs_information','pending_manager','pending_hr',
    'pending_payroll','approved','applied','rejected','withdrawn','failed'
  )),
  CHECK (requester_kind IN ('employee','manager','hr')),
  UNIQUE (company_code, idempotency_key)
);

CREATE INDEX IF NOT EXISTS employee_ess_requests_employee_idx
  ON employee_ess_requests (company_code, employee_key, created_at DESC);
CREATE INDEX IF NOT EXISTS employee_ess_requests_state_idx
  ON employee_ess_requests (company_code, state, updated_at DESC);
CREATE INDEX IF NOT EXISTS employee_ess_requests_requester_idx
  ON employee_ess_requests (company_code, requester_employee_key, created_at DESC);

CREATE TABLE IF NOT EXISTS employee_ess_request_events (
  event_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  company_code text NOT NULL,
  request_id uuid NOT NULL REFERENCES employee_ess_requests(request_id) ON DELETE CASCADE,
  actor_user_id uuid,
  actor_employee_key text,
  action text NOT NULL,
  from_state text,
  to_state text,
  detail jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS employee_ess_request_events_req_idx
  ON employee_ess_request_events (request_id, created_at);

CREATE TABLE IF NOT EXISTS employee_ess_personal_profiles (
  company_code text NOT NULL,
  employee_key text NOT NULL,
  profile_json jsonb NOT NULL DEFAULT '{}'::jsonb,
  emergency_json jsonb NOT NULL DEFAULT '{}'::jsonb,
  version bigint NOT NULL DEFAULT 1,
  updated_at timestamptz NOT NULL DEFAULT now(),
  updated_by_request_id uuid,
  PRIMARY KEY (company_code, employee_key)
);

CREATE TABLE IF NOT EXISTS employee_ess_bank_profiles (
  company_code text NOT NULL,
  employee_key text NOT NULL,
  bank_ciphertext jsonb NOT NULL DEFAULT '{}'::jsonb,
  bank_fingerprint text,
  version bigint NOT NULL DEFAULT 1,
  updated_at timestamptz NOT NULL DEFAULT now(),
  updated_by_request_id uuid,
  PRIMARY KEY (company_code, employee_key)
);

CREATE TABLE IF NOT EXISTS employee_ess_document_versions (
  document_version_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  company_code text NOT NULL,
  employee_key text NOT NULL,
  document_key text NOT NULL,
  version_number int NOT NULL,
  storage_ref text,
  metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
  replaced_version_id uuid,
  request_id uuid,
  status text NOT NULL DEFAULT 'active',
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (company_code, employee_key, document_key, version_number)
);

CREATE TABLE IF NOT EXISTS employee_ess_letter_orders (
  letter_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  company_code text NOT NULL,
  employee_key text NOT NULL,
  letter_type text NOT NULL,
  status text NOT NULL DEFAULT 'pending',
  request_id uuid,
  payload jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS employee_ess_audit_journal (
  journal_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  company_code text NOT NULL,
  action text NOT NULL,
  idempotency_key text NOT NULL,
  payload jsonb NOT NULL DEFAULT '{}'::jsonb,
  status text NOT NULL DEFAULT 'ok',
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (company_code, action, idempotency_key)
);
