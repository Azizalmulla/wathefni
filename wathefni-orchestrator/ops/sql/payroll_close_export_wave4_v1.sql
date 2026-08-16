-- Payroll Wave 4 — close + finance export foundation (v1.0.0)
-- Additive only. Does NOT alter Wave 1 / 2A / 2B / 3 DDL.
-- Closed-run snapshots are immutable. Journal drafts + bank-export contracts only.
-- payment_processing remains disabled. No real bank format, WPS/AS'HAL, PIFSS, EOS, payments, or AI.
-- Native results remain preview/non-authoritative; external payroll remains money authority.

CREATE TABLE IF NOT EXISTS payroll_close_runs (
  close_run_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  company_code text NOT NULL,
  period_id uuid,
  period_start date NOT NULL,
  period_end date NOT NULL,
  source_kind text NOT NULL,
  source_run_id uuid NOT NULL,
  status text NOT NULL DEFAULT 'draft',
  money_authority text NOT NULL,
  authoritative_label text NOT NULL,
  payment_processing text NOT NULL DEFAULT 'disabled',
  posts_payment boolean NOT NULL DEFAULT false,
  currency text NOT NULL DEFAULT 'KWD',
  totals_earnings numeric(14,3) NOT NULL DEFAULT 0,
  totals_deductions numeric(14,3) NOT NULL DEFAULT 0,
  totals_net numeric(14,3) NOT NULL DEFAULT 0,
  employee_count integer NOT NULL DEFAULT 0,
  source_fingerprint text NOT NULL,
  snapshot_fingerprint text,
  snapshot_payload jsonb,
  snapshot_immutable boolean NOT NULL DEFAULT false,
  created_by_phone text,
  submitted_by_phone text,
  submitted_at timestamptz,
  approved_by_phone text,
  approved_at timestamptz,
  closed_by_phone text,
  closed_at timestamptz,
  reopen_pending boolean NOT NULL DEFAULT false,
  decision_note text,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  row_version integer NOT NULL DEFAULT 1,
  CONSTRAINT payroll_close_source_kind_chk
    CHECK (source_kind IN ('native_preview', 'external_import')),
  CONSTRAINT payroll_close_status_chk
    CHECK (status IN ('draft', 'in_review', 'approved', 'closed', 'reopened')),
  CONSTRAINT payroll_close_money_authority_chk
    CHECK (money_authority IN ('preview_non_authoritative', 'external')),
  CONSTRAINT payroll_close_payment_disabled_chk
    CHECK (payment_processing = 'disabled'),
  CONSTRAINT payroll_close_no_posts_payment_chk
    CHECK (posts_payment = false),
  CONSTRAINT payroll_close_snapshot_closed_chk
    CHECK (
      (status = 'closed' AND snapshot_immutable = true AND snapshot_payload IS NOT NULL AND snapshot_fingerprint IS NOT NULL)
      OR (status <> 'closed')
    )
);

CREATE UNIQUE INDEX IF NOT EXISTS payroll_close_active_source_uniq
  ON payroll_close_runs (company_code, source_kind, source_run_id)
  WHERE status IN ('draft', 'in_review', 'approved', 'closed');

CREATE INDEX IF NOT EXISTS idx_payroll_close_runs_co
  ON payroll_close_runs (company_code, period_start DESC, created_at DESC);

CREATE TABLE IF NOT EXISTS payroll_close_run_events (
  event_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  close_run_id uuid,
  company_code text NOT NULL,
  event_type text NOT NULL,
  payload jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_by_phone text,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_payroll_close_events_co
  ON payroll_close_run_events (company_code, created_at DESC);

CREATE TABLE IF NOT EXISTS payroll_close_dual_control (
  action_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  company_code text NOT NULL,
  close_run_id uuid NOT NULL REFERENCES payroll_close_runs(close_run_id),
  action_kind text NOT NULL,
  status text NOT NULL DEFAULT 'pending_second',
  initiated_by_phone text NOT NULL,
  confirmed_by_phone text,
  confirmed_at timestamptz,
  payload jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT payroll_close_dual_kind_chk
    CHECK (action_kind IN ('reopen_closed_run')),
  CONSTRAINT payroll_close_dual_status_chk
    CHECK (status IN ('pending_second', 'confirmed', 'cancelled'))
);

CREATE INDEX IF NOT EXISTS idx_payroll_close_dual_run
  ON payroll_close_dual_control (company_code, close_run_id, status);

CREATE TABLE IF NOT EXISTS payroll_account_mappings (
  mapping_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  company_code text NOT NULL,
  component_code text NOT NULL,
  component_kind text NOT NULL,
  account_code text NOT NULL,
  cost_centre text,
  journal_side text NOT NULL,
  active boolean NOT NULL DEFAULT true,
  decision_note text,
  created_by_phone text,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  row_version integer NOT NULL DEFAULT 1,
  CONSTRAINT payroll_acct_map_kind_chk
    CHECK (component_kind IN ('earning', 'allowance', 'deduction', 'employer_cost', 'net_payable', 'clearing')),
  CONSTRAINT payroll_acct_map_side_chk
    CHECK (journal_side IN ('debit', 'credit')),
  CONSTRAINT payroll_acct_map_code_chk
    CHECK (account_code ~ '^[A-Za-z0-9._-]{2,64}$')
);

CREATE UNIQUE INDEX IF NOT EXISTS payroll_acct_map_active_uniq
  ON payroll_account_mappings (company_code, component_code)
  WHERE active = true;

CREATE TABLE IF NOT EXISTS payroll_journal_drafts (
  journal_draft_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  company_code text NOT NULL,
  close_run_id uuid NOT NULL REFERENCES payroll_close_runs(close_run_id),
  status text NOT NULL DEFAULT 'draft',
  currency text NOT NULL DEFAULT 'KWD',
  total_debit numeric(14,3) NOT NULL DEFAULT 0,
  total_credit numeric(14,3) NOT NULL DEFAULT 0,
  balanced boolean NOT NULL DEFAULT false,
  content_fingerprint text NOT NULL,
  source_snapshot_fingerprint text NOT NULL,
  mapping_fingerprint text NOT NULL,
  posts_to_erp boolean NOT NULL DEFAULT false,
  payment_processing text NOT NULL DEFAULT 'disabled',
  decision_note text,
  created_by_phone text,
  approved_by_phone text,
  approved_at timestamptz,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  row_version integer NOT NULL DEFAULT 1,
  CONSTRAINT payroll_journal_status_chk
    CHECK (status IN ('draft', 'validated', 'approved', 'superseded')),
  CONSTRAINT payroll_journal_no_erp_chk
    CHECK (posts_to_erp = false),
  CONSTRAINT payroll_journal_payment_disabled_chk
    CHECK (payment_processing = 'disabled'),
  CONSTRAINT payroll_journal_balanced_chk
    CHECK (balanced = (total_debit = total_credit))
);

CREATE INDEX IF NOT EXISTS idx_payroll_journal_close
  ON payroll_journal_drafts (company_code, close_run_id, created_at DESC);

CREATE TABLE IF NOT EXISTS payroll_journal_lines (
  line_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  journal_draft_id uuid NOT NULL REFERENCES payroll_journal_drafts(journal_draft_id),
  company_code text NOT NULL,
  line_no integer NOT NULL,
  account_code text NOT NULL,
  cost_centre text,
  component_code text,
  description text,
  debit numeric(14,3) NOT NULL DEFAULT 0,
  credit numeric(14,3) NOT NULL DEFAULT 0,
  currency text NOT NULL DEFAULT 'KWD',
  created_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT payroll_journal_line_dc_chk
    CHECK (
      (debit > 0 AND credit = 0) OR (credit > 0 AND debit = 0) OR (debit = 0 AND credit = 0)
    )
);

CREATE INDEX IF NOT EXISTS idx_payroll_journal_lines_draft
  ON payroll_journal_lines (journal_draft_id, line_no);

CREATE TABLE IF NOT EXISTS payroll_bank_export_drafts (
  bank_export_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  company_code text NOT NULL,
  close_run_id uuid NOT NULL REFERENCES payroll_close_runs(close_run_id),
  status text NOT NULL DEFAULT 'draft',
  contract_schema text NOT NULL DEFAULT 'payroll_bank_export_contract@1.0.0',
  currency text NOT NULL DEFAULT 'KWD',
  employee_count integer NOT NULL DEFAULT 0,
  totals_net numeric(14,3) NOT NULL DEFAULT 0,
  content_fingerprint text NOT NULL,
  source_snapshot_fingerprint text NOT NULL,
  contract_payload jsonb NOT NULL DEFAULT '{}'::jsonb,
  validation_errors jsonb NOT NULL DEFAULT '[]'::jsonb,
  real_bank_format boolean NOT NULL DEFAULT false,
  bank_connection boolean NOT NULL DEFAULT false,
  wps_submission boolean NOT NULL DEFAULT false,
  payment_processing text NOT NULL DEFAULT 'disabled',
  posts_payment boolean NOT NULL DEFAULT false,
  decision_note text,
  created_by_phone text,
  approved_by_phone text,
  approved_at timestamptz,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  row_version integer NOT NULL DEFAULT 1,
  CONSTRAINT payroll_bank_export_status_chk
    CHECK (status IN ('draft', 'validated', 'approved', 'superseded', 'invalid')),
  CONSTRAINT payroll_bank_export_no_real_format_chk
    CHECK (real_bank_format = false),
  CONSTRAINT payroll_bank_export_no_connection_chk
    CHECK (bank_connection = false),
  CONSTRAINT payroll_bank_export_no_wps_chk
    CHECK (wps_submission = false),
  CONSTRAINT payroll_bank_export_payment_disabled_chk
    CHECK (payment_processing = 'disabled'),
  CONSTRAINT payroll_bank_export_no_posts_payment_chk
    CHECK (posts_payment = false)
);

CREATE INDEX IF NOT EXISTS idx_payroll_bank_export_close
  ON payroll_bank_export_drafts (company_code, close_run_id, created_at DESC);

CREATE TABLE IF NOT EXISTS payroll_finance_exports (
  finance_export_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  company_code text NOT NULL,
  close_run_id uuid NOT NULL REFERENCES payroll_close_runs(close_run_id),
  export_kind text NOT NULL,
  artifact_id uuid NOT NULL,
  status text NOT NULL DEFAULT 'recorded',
  content_fingerprint text NOT NULL,
  source_snapshot_fingerprint text NOT NULL,
  reconciliation_status text NOT NULL DEFAULT 'unmatched',
  approved_by_phone text,
  approved_at timestamptz,
  exported_by_phone text,
  decision_note text,
  drift_detail jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT payroll_finance_export_kind_chk
    CHECK (export_kind IN ('journal_draft', 'bank_contract')),
  CONSTRAINT payroll_finance_export_status_chk
    CHECK (status IN ('recorded', 'approved', 'superseded', 'quarantined')),
  CONSTRAINT payroll_finance_recon_chk
    CHECK (reconciliation_status IN ('unmatched', 'matched', 'drift', 'quarantined'))
);

CREATE UNIQUE INDEX IF NOT EXISTS payroll_finance_export_fp_uniq
  ON payroll_finance_exports (company_code, export_kind, content_fingerprint)
  WHERE status IN ('recorded', 'approved');

CREATE INDEX IF NOT EXISTS idx_payroll_finance_exports_close
  ON payroll_finance_exports (company_code, close_run_id, created_at DESC);
