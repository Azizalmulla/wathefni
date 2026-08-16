-- Payroll Authority P5 — Mode A authoritative finalize (v1.0.0)
-- Additive. SYNTHETIC_ONLY retained. payment_processing disabled. No payment_date invent.
-- Preview calc rows remain preview_non_authoritative; seal creates separate money_authority=wathefni snapshots.

CREATE TABLE IF NOT EXISTS payroll_mode_a_finalize_runs (
  finalize_run_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  company_code text NOT NULL,
  calc_run_id uuid NOT NULL,
  input_snapshot_id uuid NOT NULL,
  policy_version_id uuid NOT NULL,
  period_start date NOT NULL,
  period_end date NOT NULL,
  status text NOT NULL DEFAULT 'draft',
  money_authority text NOT NULL DEFAULT 'pending_seal',
  content_fingerprint text NOT NULL,
  gate_payload jsonb NOT NULL DEFAULT '{}'::jsonb,
  blockers jsonb NOT NULL DEFAULT '[]'::jsonb,
  statutory_provenance jsonb NOT NULL DEFAULT '{}'::jsonb,
  approval_actor_chain jsonb NOT NULL DEFAULT '[]'::jsonb,
  company_finalize_policy jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_by_phone text,
  reviewed_by_phone text,
  reviewed_at timestamptz,
  approved_by_phone text,
  approved_at timestamptz,
  finalized_by_phone text,
  finalized_at timestamptz,
  decision_note text,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  row_version integer NOT NULL DEFAULT 1,
  CONSTRAINT payroll_p5_finalize_status_chk
    CHECK (status IN (
      'draft',
      'in_review',
      'approved',
      'finalized',
      'cancelled',
      'superseded'
    )),
  CONSTRAINT payroll_p5_finalize_money_chk
    CHECK (money_authority IN ('pending_seal', 'wathefni')),
  CONSTRAINT payroll_p5_finalize_payment_disabled_implicit CHECK (true)
);

CREATE INDEX IF NOT EXISTS idx_payroll_p5_finalize_co
  ON payroll_mode_a_finalize_runs (company_code, status, period_start DESC);

CREATE UNIQUE INDEX IF NOT EXISTS payroll_p5_finalize_calc_active_uniq
  ON payroll_mode_a_finalize_runs (company_code, calc_run_id)
  WHERE status IN ('draft', 'in_review', 'approved', 'finalized');

CREATE TABLE IF NOT EXISTS payroll_mode_a_finalize_events (
  event_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  company_code text NOT NULL,
  finalize_run_id uuid,
  event_type text NOT NULL,
  payload jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_by_phone text,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_payroll_p5_finalize_events
  ON payroll_mode_a_finalize_events (company_code, created_at DESC);

-- Company finalize policy defaults (SME-friendly, SOD-capable)
CREATE TABLE IF NOT EXISTS payroll_mode_a_company_finalize_policy (
  company_code text PRIMARY KEY,
  require_review_step boolean NOT NULL DEFAULT true,
  require_distinct_reviewer boolean NOT NULL DEFAULT true,
  require_distinct_approver boolean NOT NULL DEFAULT true,
  require_distinct_finalizer boolean NOT NULL DEFAULT true,
  allow_approver_as_finalizer boolean NOT NULL DEFAULT true,
  metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
  updated_at timestamptz NOT NULL DEFAULT now(),
  updated_by_phone text
);

-- Extend payslip documents for Mode A sealed wathefni projections
ALTER TABLE payroll_payslip_documents DROP CONSTRAINT IF EXISTS payroll_payslip_source_kind_chk;
ALTER TABLE payroll_payslip_documents
  ADD CONSTRAINT payroll_payslip_source_kind_chk
  CHECK (source_kind IN ('native_preview', 'external_import', 'native_authoritative'));

ALTER TABLE payroll_payslip_documents DROP CONSTRAINT IF EXISTS payroll_payslip_money_authority_chk;
ALTER TABLE payroll_payslip_documents
  ADD CONSTRAINT payroll_payslip_money_authority_chk
  CHECK (money_authority IN ('preview_non_authoritative', 'external', 'wathefni'));

-- Unique active payslip for native_authoritative uses authority snapshot id as source_run_id
CREATE UNIQUE INDEX IF NOT EXISTS payroll_payslip_native_auth_active_uniq
  ON payroll_payslip_documents (company_code, source_kind, source_run_id, employee_key)
  WHERE status = 'active' AND source_kind = 'native_authoritative';
