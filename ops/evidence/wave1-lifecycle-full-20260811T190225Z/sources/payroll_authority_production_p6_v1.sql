-- Payroll Authority P6 — Kuwait production readiness + controlled Mode A entitlement
-- Additive. payment_processing remains disabled. No invented payment_date.
-- Does NOT globally unlock Mode A for all tenants.

CREATE TABLE IF NOT EXISTS payroll_company_mode_a_entitlement (
  company_code text PRIMARY KEY,
  entitlement_state text NOT NULL DEFAULT 'disabled',
  mode_a_opt_in boolean NOT NULL DEFAULT false,
  payroll_mode text NOT NULL DEFAULT 'native',
  readiness_status text NOT NULL DEFAULT 'incomplete',
  readiness_fingerprint text,
  readiness_payload jsonb NOT NULL DEFAULT '{}'::jsonb,
  opted_in_at timestamptz,
  opted_in_by_phone text,
  opted_in_reason text,
  metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  updated_by_phone text,
  CONSTRAINT payroll_p6_entitlement_state_chk CHECK (
    entitlement_state IN (
      'disabled',
      'preview_only',
      'authoritative_allowlisted',
      'authoritative'
    )
  ),
  CONSTRAINT payroll_p6_entitlement_readiness_chk CHECK (
    readiness_status IN ('incomplete', 'ready', 'blocked')
  ),
  CONSTRAINT payroll_p6_entitlement_mode_chk CHECK (
    payroll_mode IN ('native', 'external', 'parallel_shadow')
  )
);

CREATE TABLE IF NOT EXISTS payroll_mode_a_employee_allowlist (
  allowlist_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  company_code text NOT NULL,
  employee_key text NOT NULL,
  status text NOT NULL DEFAULT 'active',
  reason text NOT NULL,
  added_by_phone text,
  added_at timestamptz NOT NULL DEFAULT now(),
  revoked_at timestamptz,
  revoked_by_phone text,
  metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
  CONSTRAINT payroll_p6_allowlist_status_chk CHECK (status IN ('active', 'revoked')),
  CONSTRAINT payroll_p6_allowlist_uniq UNIQUE (company_code, employee_key)
);

CREATE INDEX IF NOT EXISTS idx_payroll_p6_allowlist_co
  ON payroll_mode_a_employee_allowlist (company_code, status);

CREATE TABLE IF NOT EXISTS payroll_mode_a_variance_policy (
  company_code text PRIMARY KEY,
  gross_delta_abs numeric(14,3) NOT NULL DEFAULT 50,
  net_delta_abs numeric(14,3) NOT NULL DEFAULT 50,
  gross_delta_pct numeric(8,4) NOT NULL DEFAULT 0.10,
  net_delta_pct numeric(8,4) NOT NULL DEFAULT 0.10,
  flag_component_add_remove boolean NOT NULL DEFAULT true,
  flag_zero_or_negative_net boolean NOT NULL DEFAULT true,
  metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
  updated_at timestamptz NOT NULL DEFAULT now(),
  updated_by_phone text
);

CREATE TABLE IF NOT EXISTS payroll_mode_a_run_review_items (
  review_item_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  company_code text NOT NULL,
  calc_run_id uuid,
  finalize_run_id uuid,
  period_start date,
  period_end date,
  employee_key text,
  severity text NOT NULL DEFAULT 'info',
  bucket text NOT NULL,
  code text NOT NULL,
  message_en text NOT NULL,
  message_ar text,
  source_refs jsonb NOT NULL DEFAULT '{}'::jsonb,
  advisory boolean NOT NULL DEFAULT true,
  created_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT payroll_p6_review_severity_chk CHECK (
    severity IN ('info', 'warning', 'blocked', 'ready', 'changed')
  ),
  CONSTRAINT payroll_p6_review_bucket_chk CHECK (
    bucket IN ('ready', 'needs_review', 'blocked', 'changed_since_previous')
  )
);

CREATE INDEX IF NOT EXISTS idx_payroll_p6_review_co_run
  ON payroll_mode_a_run_review_items (company_code, calc_run_id, bucket);

CREATE TABLE IF NOT EXISTS payroll_mode_a_controlled_overrides (
  override_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  company_code text NOT NULL,
  employee_key text,
  override_kind text NOT NULL,
  reason text NOT NULL,
  actor_phone text NOT NULL,
  allowed boolean NOT NULL DEFAULT false,
  payload jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT payroll_p6_override_kind_chk CHECK (
    override_kind IN (
      'company_policy_decision',
      'review_ack_unusual_variance',
      'component_exception_ack'
    )
  )
);

CREATE TABLE IF NOT EXISTS payroll_mode_a_entitlement_events (
  event_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  company_code text NOT NULL,
  event_type text NOT NULL,
  payload jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_by_phone text,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_payroll_p6_entitlement_events
  ON payroll_mode_a_entitlement_events (company_code, created_at DESC);
