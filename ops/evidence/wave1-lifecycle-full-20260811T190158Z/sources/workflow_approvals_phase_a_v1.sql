-- Phase A slice 1 — workflow_approvals authority schema (version 1.0.0)
-- Applied via workflow_approvals.ensure_workflow_approvals_schema.
-- Runtime remains dark until WATHEFNI_WORKFLOW_APPROVALS=on AND company allowlist
-- AND workflow_approval_settings.enabled=true for that company.
-- Does not migrate legacy offer/leave dual-control paths.

CREATE TABLE IF NOT EXISTS workflow_approval_settings (
  company_code text PRIMARY KEY,
  enabled boolean NOT NULL DEFAULT false,
  updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS workflow_approval_policies (
  policy_id uuid PRIMARY KEY,
  company_code text NOT NULL,
  subject_type text NOT NULL,
  name text NOT NULL,
  forbid_self_approval boolean NOT NULL DEFAULT true,
  steps_json jsonb NOT NULL DEFAULT '[]'::jsonb,
  active boolean NOT NULL DEFAULT true,
  version integer NOT NULL DEFAULT 1,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT workflow_approval_policies_subject_chk
    CHECK (char_length(trim(subject_type)) > 0),
  CONSTRAINT workflow_approval_policies_name_chk
    CHECK (char_length(trim(name)) > 0)
);

CREATE UNIQUE INDEX IF NOT EXISTS workflow_approval_policies_active_uniq
  ON workflow_approval_policies (company_code, subject_type)
  WHERE active = true;

CREATE INDEX IF NOT EXISTS workflow_approval_policies_company_idx
  ON workflow_approval_policies (company_code, subject_type);

CREATE TABLE IF NOT EXISTS workflow_approval_instances (
  instance_id uuid PRIMARY KEY,
  company_code text NOT NULL,
  policy_id uuid NOT NULL REFERENCES workflow_approval_policies(policy_id),
  policy_version integer NOT NULL,
  subject_type text NOT NULL,
  subject_id text NOT NULL,
  status text NOT NULL,
  current_step_order integer,
  created_by_user_id text,
  created_by_phone text,
  idempotency_key text,
  row_version integer NOT NULL DEFAULT 1,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT workflow_approval_instances_status_chk
    CHECK (status IN ('draft', 'pending', 'approved', 'rejected', 'cancelled', 'expired'))
);

CREATE UNIQUE INDEX IF NOT EXISTS workflow_approval_instances_idem_uniq
  ON workflow_approval_instances (company_code, idempotency_key)
  WHERE idempotency_key IS NOT NULL AND idempotency_key <> '';

CREATE UNIQUE INDEX IF NOT EXISTS workflow_approval_instances_open_subject_uniq
  ON workflow_approval_instances (company_code, subject_type, subject_id)
  WHERE status IN ('draft', 'pending');

CREATE INDEX IF NOT EXISTS workflow_approval_instances_company_status_idx
  ON workflow_approval_instances (company_code, status, updated_at DESC);

CREATE TABLE IF NOT EXISTS workflow_approval_steps (
  step_id uuid PRIMARY KEY,
  instance_id uuid NOT NULL REFERENCES workflow_approval_instances(instance_id),
  company_code text NOT NULL,
  step_order integer NOT NULL,
  status text NOT NULL,
  assignee_role text,
  assignee_user_id text,
  decided_by_user_id text,
  decided_by_phone text,
  decision_id text,
  comment text,
  decided_at timestamptz,
  row_version integer NOT NULL DEFAULT 1,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT workflow_approval_steps_status_chk
    CHECK (status IN ('pending', 'approved', 'rejected', 'skipped', 'delegated')),
  CONSTRAINT workflow_approval_steps_order_chk
    CHECK (step_order >= 1)
);

CREATE UNIQUE INDEX IF NOT EXISTS workflow_approval_steps_order_uniq
  ON workflow_approval_steps (instance_id, step_order);

CREATE UNIQUE INDEX IF NOT EXISTS workflow_approval_steps_decision_uniq
  ON workflow_approval_steps (step_id, decision_id)
  WHERE decision_id IS NOT NULL AND decision_id <> '';

CREATE INDEX IF NOT EXISTS workflow_approval_steps_instance_idx
  ON workflow_approval_steps (instance_id, step_order);

CREATE TABLE IF NOT EXISTS workflow_delegation_grants (
  grant_id uuid PRIMARY KEY,
  company_code text NOT NULL,
  delegator_user_id text NOT NULL,
  delegate_user_id text NOT NULL,
  scope_subject_types text[],
  status text NOT NULL,
  starts_at timestamptz NOT NULL,
  ends_at timestamptz,
  created_at timestamptz NOT NULL DEFAULT now(),
  revoked_at timestamptz,
  revoked_by_user_id text,
  row_version integer NOT NULL DEFAULT 1,
  CONSTRAINT workflow_delegation_grants_status_chk
    CHECK (status IN ('scheduled', 'active', 'revoked', 'expired')),
  CONSTRAINT workflow_delegation_grants_parties_chk
    CHECK (delegator_user_id <> '' AND delegate_user_id <> ''),
  CONSTRAINT workflow_delegation_grants_self_chk
    CHECK (delegator_user_id <> delegate_user_id)
);

CREATE INDEX IF NOT EXISTS workflow_delegation_grants_company_delegate_idx
  ON workflow_delegation_grants (company_code, delegate_user_id, status);

CREATE INDEX IF NOT EXISTS workflow_delegation_grants_company_delegator_idx
  ON workflow_delegation_grants (company_code, delegator_user_id, status);

CREATE TABLE IF NOT EXISTS workflow_approval_events (
  event_id uuid PRIMARY KEY,
  company_code text NOT NULL,
  instance_id uuid,
  grant_id uuid,
  step_id uuid,
  event_type text NOT NULL,
  actor_user_id text,
  actor_phone text,
  payload jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS workflow_approval_events_company_idx
  ON workflow_approval_events (company_code, created_at DESC);

CREATE INDEX IF NOT EXISTS workflow_approval_events_instance_idx
  ON workflow_approval_events (instance_id, created_at);
