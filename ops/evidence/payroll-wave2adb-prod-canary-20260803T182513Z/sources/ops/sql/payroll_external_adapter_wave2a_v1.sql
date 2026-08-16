-- Payroll External Adapter Wave 2A — synthetic CSV/SFTP foundation (v1.0.0)
-- Staging only via payroll_external_adapter_wave2a.ensure_schema /
-- ops/migrate-payroll-external-adapter-wave2a.sh.
-- Does NOT alter Wave 1 contract/period DDL.
-- Does NOT enable payment_processing, bank files, native G2N, PIFSS, WPS, EOS, journals, XBRL.
-- Money authority remains EXTERNAL (mirror-only imports).

CREATE TABLE IF NOT EXISTS payroll_adapter_export_runs (
  export_run_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  company_code text NOT NULL,
  period_id uuid,
  period_start date,
  period_end date,
  adapter_kind text NOT NULL DEFAULT 'synthetic_csv_sftp',
  schema_version text NOT NULL DEFAULT 'payroll_input_export@1.0.0',
  status text NOT NULL DEFAULT 'exported',
  input_fingerprint text NOT NULL,
  payload jsonb NOT NULL DEFAULT '{}'::jsonb,
  artifact_csv text,
  artifact_sha256 text,
  external_run_id text,
  money_authority text NOT NULL DEFAULT 'external',
  payment_processing text NOT NULL DEFAULT 'disabled',
  posts_payment boolean NOT NULL DEFAULT false,
  row_version integer NOT NULL DEFAULT 1,
  created_by_phone text,
  decision_note text,
  metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT payroll_adapter_export_adapter_chk
    CHECK (adapter_kind IN ('synthetic_csv_sftp')),
  CONSTRAINT payroll_adapter_export_status_chk
    CHECK (status IN ('exported', 'superseded', 'rolled_back')),
  CONSTRAINT payroll_adapter_export_money_chk
    CHECK (money_authority = 'external'),
  CONSTRAINT payroll_adapter_export_payment_chk
    CHECK (payment_processing = 'disabled'),
  CONSTRAINT payroll_adapter_export_posts_chk
    CHECK (posts_payment = false)
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_payroll_adapter_export_fp
  ON payroll_adapter_export_runs(company_code, input_fingerprint)
  WHERE status = 'exported';

CREATE INDEX IF NOT EXISTS idx_payroll_adapter_export_period
  ON payroll_adapter_export_runs(company_code, period_start, period_end, created_at DESC);

CREATE TABLE IF NOT EXISTS payroll_adapter_import_runs (
  import_run_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  company_code text NOT NULL,
  export_run_id uuid REFERENCES payroll_adapter_export_runs(export_run_id) ON DELETE SET NULL,
  adapter_kind text NOT NULL DEFAULT 'synthetic_csv_sftp',
  schema_version text NOT NULL DEFAULT 'payroll_result_import@1.0.0',
  status text NOT NULL DEFAULT 'imported',
  external_run_id text NOT NULL,
  result_fingerprint text NOT NULL,
  payload jsonb NOT NULL DEFAULT '{}'::jsonb,
  artifact_csv text,
  artifact_sha256 text,
  money_authority text NOT NULL DEFAULT 'external',
  payment_processing text NOT NULL DEFAULT 'disabled',
  posts_payment boolean NOT NULL DEFAULT false,
  mirror_only boolean NOT NULL DEFAULT true,
  matched_count integer NOT NULL DEFAULT 0,
  unmatched_count integer NOT NULL DEFAULT 0,
  quarantined_count integer NOT NULL DEFAULT 0,
  row_version integer NOT NULL DEFAULT 1,
  created_by_phone text,
  decision_note text,
  metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT payroll_adapter_import_adapter_chk
    CHECK (adapter_kind IN ('synthetic_csv_sftp')),
  CONSTRAINT payroll_adapter_import_status_chk
    CHECK (status IN ('imported', 'idempotent_replay', 'partial', 'quarantined', 'rolled_back')),
  CONSTRAINT payroll_adapter_import_money_chk
    CHECK (money_authority = 'external'),
  CONSTRAINT payroll_adapter_import_payment_chk
    CHECK (payment_processing = 'disabled'),
  CONSTRAINT payroll_adapter_import_posts_chk
    CHECK (posts_payment = false),
  CONSTRAINT payroll_adapter_import_mirror_chk
    CHECK (mirror_only = true)
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_payroll_adapter_import_ext_run
  ON payroll_adapter_import_runs(company_code, external_run_id)
  WHERE status IN ('imported', 'idempotent_replay', 'partial');

CREATE INDEX IF NOT EXISTS idx_payroll_adapter_import_export
  ON payroll_adapter_import_runs(export_run_id, created_at DESC);

CREATE TABLE IF NOT EXISTS payroll_adapter_import_lines (
  line_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  import_run_id uuid NOT NULL REFERENCES payroll_adapter_import_runs(import_run_id) ON DELETE CASCADE,
  company_code text NOT NULL,
  employee_key text,
  component_code text,
  line_status text NOT NULL DEFAULT 'matched',
  opaque_amount numeric(14,3),
  currency text DEFAULT 'KWD',
  match_notes text,
  raw_row jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT payroll_adapter_line_status_chk
    CHECK (line_status IN ('matched', 'unmatched_employee', 'unmatched_component', 'quarantined', 'duplicate'))
);

CREATE INDEX IF NOT EXISTS idx_payroll_adapter_lines_run
  ON payroll_adapter_import_lines(import_run_id, line_status);

CREATE TABLE IF NOT EXISTS payroll_adapter_quarantine (
  quarantine_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  company_code text NOT NULL,
  source_kind text NOT NULL,
  export_run_id uuid,
  import_run_id uuid,
  reason text NOT NULL,
  artifact_excerpt text,
  payload jsonb NOT NULL DEFAULT '{}'::jsonb,
  hard_deleted boolean NOT NULL DEFAULT false,
  created_by_phone text,
  created_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT payroll_adapter_q_source_chk
    CHECK (source_kind IN ('malformed_import', 'schema_reject', 'unmatched_employee', 'fingerprint_mismatch', 'other')),
  CONSTRAINT payroll_adapter_q_no_hard_delete_chk
    CHECK (hard_deleted = false)
);

CREATE INDEX IF NOT EXISTS idx_payroll_adapter_quarantine_company
  ON payroll_adapter_quarantine(company_code, created_at DESC);

CREATE TABLE IF NOT EXISTS payroll_adapter_reconciliations (
  reconciliation_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  company_code text NOT NULL,
  export_run_id uuid NOT NULL REFERENCES payroll_adapter_export_runs(export_run_id) ON DELETE CASCADE,
  import_run_id uuid NOT NULL REFERENCES payroll_adapter_import_runs(import_run_id) ON DELETE CASCADE,
  status text NOT NULL DEFAULT 'ok',
  employees_expected integer NOT NULL DEFAULT 0,
  employees_matched integer NOT NULL DEFAULT 0,
  employees_missing integer NOT NULL DEFAULT 0,
  employees_extra integer NOT NULL DEFAULT 0,
  components_diff jsonb NOT NULL DEFAULT '[]'::jsonb,
  totals_export numeric(14,3),
  totals_import numeric(14,3),
  totals_delta numeric(14,3),
  differences jsonb NOT NULL DEFAULT '[]'::jsonb,
  money_authority text NOT NULL DEFAULT 'external',
  payment_processing text NOT NULL DEFAULT 'disabled',
  created_by_phone text,
  decision_note text,
  created_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT payroll_adapter_recon_status_chk
    CHECK (status IN ('ok', 'differences', 'blocked')),
  CONSTRAINT payroll_adapter_recon_money_chk
    CHECK (money_authority = 'external'),
  CONSTRAINT payroll_adapter_recon_payment_chk
    CHECK (payment_processing = 'disabled')
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_payroll_adapter_recon_pair
  ON payroll_adapter_reconciliations(export_run_id, import_run_id);

CREATE TABLE IF NOT EXISTS payroll_adapter_events (
  event_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  company_code text NOT NULL,
  export_run_id uuid,
  import_run_id uuid,
  event_type text NOT NULL,
  payload jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_by_phone text,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_payroll_adapter_events_company
  ON payroll_adapter_events(company_code, created_at DESC);
