-- Payroll Authority Wave 1 — mode-agnostic foundation (v1.0.0)
-- Local/staging only via payroll_authority_wave1.ensure_schema /
-- ops/migrate-payroll-authority-wave1.sh.
-- Does NOT enable payment_processing, gross-to-net, PIFSS, bank/WPS, EOS,
-- payslips-as-money, journals, or XBRL.

CREATE TABLE IF NOT EXISTS payroll_company_settings (
  company_code text PRIMARY KEY,
  payroll_mode text NOT NULL DEFAULT 'native',
  payment_processing text NOT NULL DEFAULT 'disabled',
  attendance_input_source text NOT NULL DEFAULT 'legacy_records',
  annual_leave_eligibility_months integer NOT NULL DEFAULT 6,
  updated_by_phone text,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT payroll_company_settings_mode_chk
    CHECK (payroll_mode IN ('native', 'external', 'parallel_shadow')),
  CONSTRAINT payroll_company_settings_payment_chk
    CHECK (payment_processing = 'disabled'),
  CONSTRAINT payroll_company_settings_attendance_chk
    CHECK (attendance_input_source IN ('legacy_records', 'approved_snapshots')),
  CONSTRAINT payroll_company_settings_art70_chk
    CHECK (annual_leave_eligibility_months = 6)
);

CREATE TABLE IF NOT EXISTS payroll_compensation_contracts (
  contract_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  company_code text NOT NULL,
  employee_key text NOT NULL,
  status text NOT NULL DEFAULT 'draft',
  currency text NOT NULL DEFAULT 'KWD',
  effective_from date NOT NULL,
  effective_to date,
  source_kind text NOT NULL DEFAULT 'manual',
  source_offer_id text,
  row_version integer NOT NULL DEFAULT 1,
  created_by_phone text,
  approved_by_phone text,
  approved_at timestamptz,
  superseded_by uuid,
  decision_note text,
  metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT payroll_comp_contract_status_chk
    CHECK (status IN ('draft', 'approved', 'superseded', 'cancelled')),
  CONSTRAINT payroll_comp_contract_source_chk
    CHECK (source_kind IN ('manual', 'offer_seed', 'import')),
  CONSTRAINT payroll_comp_contract_dates_chk
    CHECK (effective_to IS NULL OR effective_to >= effective_from)
);

CREATE INDEX IF NOT EXISTS idx_payroll_comp_contracts_emp
  ON payroll_compensation_contracts(company_code, employee_key, status, effective_from);

CREATE TABLE IF NOT EXISTS payroll_compensation_components (
  component_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  contract_id uuid NOT NULL REFERENCES payroll_compensation_contracts(contract_id) ON DELETE CASCADE,
  company_code text NOT NULL,
  component_kind text NOT NULL,
  code text NOT NULL,
  label_en text,
  label_ar text,
  amount numeric(14,3) NOT NULL DEFAULT 0,
  amount_unit text NOT NULL DEFAULT 'monthly',
  is_basic boolean NOT NULL DEFAULT false,
  sort_order integer NOT NULL DEFAULT 0,
  metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT payroll_comp_component_kind_chk
    CHECK (component_kind IN ('earning', 'allowance', 'deduction')),
  CONSTRAINT payroll_comp_component_unit_chk
    CHECK (amount_unit IN ('monthly', 'hourly', 'daily', 'one_time'))
);

CREATE INDEX IF NOT EXISTS idx_payroll_comp_components_contract
  ON payroll_compensation_components(contract_id);

CREATE TABLE IF NOT EXISTS payroll_compensation_events (
  event_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  contract_id uuid REFERENCES payroll_compensation_contracts(contract_id) ON DELETE SET NULL,
  company_code text NOT NULL,
  event_type text NOT NULL,
  payload jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_by_phone text,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS payroll_periods (
  period_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  company_code text NOT NULL,
  period_start date NOT NULL,
  period_end date NOT NULL,
  status text NOT NULL DEFAULT 'open',
  payroll_mode text NOT NULL DEFAULT 'native',
  attendance_input_source text NOT NULL DEFAULT 'legacy_records',
  row_version integer NOT NULL DEFAULT 1,
  locked_at timestamptz,
  locked_by_phone text,
  closed_at timestamptz,
  closed_by_phone text,
  reopen_reason text,
  decision_note text,
  metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_by_phone text,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT payroll_periods_status_chk
    CHECK (status IN ('open', 'locked', 'closed')),
  CONSTRAINT payroll_periods_mode_chk
    CHECK (payroll_mode IN ('native', 'external', 'parallel_shadow')),
  CONSTRAINT payroll_periods_attendance_chk
    CHECK (attendance_input_source IN ('legacy_records', 'approved_snapshots')),
  CONSTRAINT payroll_periods_dates_chk
    CHECK (period_end >= period_start),
  CONSTRAINT payroll_periods_uniq UNIQUE (company_code, period_start, period_end)
);

CREATE INDEX IF NOT EXISTS idx_payroll_periods_company_status
  ON payroll_periods(company_code, status, period_start DESC);

CREATE TABLE IF NOT EXISTS payroll_period_events (
  event_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  period_id uuid REFERENCES payroll_periods(period_id) ON DELETE SET NULL,
  company_code text NOT NULL,
  event_type text NOT NULL,
  payload jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_by_phone text,
  created_at timestamptz NOT NULL DEFAULT now()
);

-- Soft-quarantine marker for legacy smoke timesheets (never hard-delete).
ALTER TABLE payroll_timesheets
  ADD COLUMN IF NOT EXISTS quarantine_status text;
ALTER TABLE payroll_timesheets
  ADD COLUMN IF NOT EXISTS row_version integer NOT NULL DEFAULT 1;

CREATE INDEX IF NOT EXISTS idx_payroll_timesheets_quarantine
  ON payroll_timesheets(company_code, quarantine_status)
  WHERE quarantine_status IS NOT NULL;
