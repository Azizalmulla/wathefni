-- Payroll Native Preview Wave 2B — deterministic preview engine (v1.0.0)
-- Staging via payroll_native_preview_wave2b.ensure_schema /
-- ops/migrate-payroll-native-preview-wave2b.sh.
-- Does NOT alter Wave 1 or Wave 2A DDL.
-- Does NOT enable payment_processing, bank/WPS, PIFSS remittance, EOS,
-- payslips-as-money, journals, or payments.

CREATE TABLE IF NOT EXISTS payroll_preview_policies (
  policy_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  company_code text NOT NULL,
  policy_version text NOT NULL,
  currency text NOT NULL DEFAULT 'KWD',
  decimal_places integer NOT NULL DEFAULT 3,
  rounding_mode text NOT NULL DEFAULT 'ROUND_HALF_UP',
  proration_basis text NOT NULL DEFAULT 'calendar_days',
  pay_type_supported text NOT NULL DEFAULT 'monthly_salaried',
  unsupported_rules jsonb NOT NULL DEFAULT '["pifss","overtime_premiums","sick_leave_pay_fractions","eos","public_holiday_rest_day_pay"]'::jsonb,
  payload jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_by_phone text,
  created_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT payroll_preview_policies_uniq UNIQUE (company_code, policy_version),
  CONSTRAINT payroll_preview_policies_rounding_chk
    CHECK (rounding_mode IN ('ROUND_HALF_UP')),
  CONSTRAINT payroll_preview_policies_proration_chk
    CHECK (proration_basis IN ('calendar_days')),
  CONSTRAINT payroll_preview_policies_pay_type_chk
    CHECK (pay_type_supported IN ('monthly_salaried'))
);

CREATE TABLE IF NOT EXISTS payroll_preview_adjustments (
  adjustment_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  company_code text NOT NULL,
  period_id uuid,
  period_start date NOT NULL,
  period_end date NOT NULL,
  employee_key text NOT NULL,
  component_kind text NOT NULL,
  code text NOT NULL,
  label_en text,
  amount numeric(14,3) NOT NULL,
  currency text NOT NULL DEFAULT 'KWD',
  status text NOT NULL DEFAULT 'active',
  decision_note text,
  created_by_phone text,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT payroll_preview_adj_kind_chk
    CHECK (component_kind IN ('earning', 'deduction')),
  CONSTRAINT payroll_preview_adj_status_chk
    CHECK (status IN ('active', 'cancelled'))
);

CREATE INDEX IF NOT EXISTS idx_payroll_preview_adj_period
  ON payroll_preview_adjustments(company_code, period_start, period_end, employee_key);

CREATE TABLE IF NOT EXISTS payroll_preview_runs (
  preview_run_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  company_code text NOT NULL,
  period_id uuid,
  period_start date NOT NULL,
  period_end date NOT NULL,
  policy_version text NOT NULL,
  status text NOT NULL DEFAULT 'calculated',
  input_fingerprint text NOT NULL,
  policy_fingerprint text NOT NULL,
  calculation_fingerprint text,
  money_authority text NOT NULL DEFAULT 'preview_non_authoritative',
  payment_processing text NOT NULL DEFAULT 'disabled',
  authoritative boolean NOT NULL DEFAULT false,
  posts_payment boolean NOT NULL DEFAULT false,
  employee_count integer NOT NULL DEFAULT 0,
  totals_earnings numeric(14,3) NOT NULL DEFAULT 0,
  totals_deductions numeric(14,3) NOT NULL DEFAULT 0,
  totals_net_preview numeric(14,3) NOT NULL DEFAULT 0,
  currency text NOT NULL DEFAULT 'KWD',
  inputs jsonb NOT NULL DEFAULT '{}'::jsonb,
  result_summary jsonb NOT NULL DEFAULT '{}'::jsonb,
  decision_note text,
  created_by_phone text,
  superseded_by uuid,
  row_version integer NOT NULL DEFAULT 1,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT payroll_preview_runs_status_chk
    CHECK (status IN ('calculated', 'superseded', 'rolled_back', 'failed')),
  CONSTRAINT payroll_preview_runs_payment_chk
    CHECK (payment_processing = 'disabled'),
  CONSTRAINT payroll_preview_runs_auth_chk
    CHECK (authoritative = false),
  CONSTRAINT payroll_preview_runs_posts_chk
    CHECK (posts_payment = false)
);

CREATE INDEX IF NOT EXISTS idx_payroll_preview_runs_company
  ON payroll_preview_runs(company_code, period_start DESC, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_payroll_preview_runs_fp
  ON payroll_preview_runs(company_code, input_fingerprint, policy_fingerprint);

CREATE TABLE IF NOT EXISTS payroll_preview_employee_results (
  employee_result_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  preview_run_id uuid NOT NULL REFERENCES payroll_preview_runs(preview_run_id) ON DELETE CASCADE,
  company_code text NOT NULL,
  employee_key text NOT NULL,
  status text NOT NULL DEFAULT 'ok',
  active_days integer NOT NULL DEFAULT 0,
  period_days integer NOT NULL DEFAULT 0,
  unpaid_days numeric(10,3) NOT NULL DEFAULT 0,
  totals_earnings numeric(14,3) NOT NULL DEFAULT 0,
  totals_deductions numeric(14,3) NOT NULL DEFAULT 0,
  totals_net_preview numeric(14,3) NOT NULL DEFAULT 0,
  currency text NOT NULL DEFAULT 'KWD',
  employment_start date,
  employment_end date,
  breakdown jsonb NOT NULL DEFAULT '{}'::jsonb,
  blockers jsonb NOT NULL DEFAULT '[]'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT payroll_preview_emp_status_chk
    CHECK (status IN ('ok', 'blocked', 'partial'))
);

CREATE INDEX IF NOT EXISTS idx_payroll_preview_emp_run
  ON payroll_preview_employee_results(preview_run_id, employee_key);

CREATE TABLE IF NOT EXISTS payroll_preview_lines (
  line_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  preview_run_id uuid NOT NULL REFERENCES payroll_preview_runs(preview_run_id) ON DELETE CASCADE,
  employee_result_id uuid REFERENCES payroll_preview_employee_results(employee_result_id) ON DELETE CASCADE,
  company_code text NOT NULL,
  employee_key text NOT NULL,
  line_kind text NOT NULL,
  code text NOT NULL,
  label_en text,
  amount numeric(14,3) NOT NULL DEFAULT 0,
  currency text NOT NULL DEFAULT 'KWD',
  calc_notes jsonb NOT NULL DEFAULT '{}'::jsonb,
  sort_order integer NOT NULL DEFAULT 0,
  created_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT payroll_preview_line_kind_chk
    CHECK (line_kind IN (
      'earning', 'allowance', 'deduction', 'unpaid_leave_deduction',
      'one_time_earning', 'one_time_deduction', 'proration', 'blocker', 'unsupported'
    ))
);

CREATE INDEX IF NOT EXISTS idx_payroll_preview_lines_run
  ON payroll_preview_lines(preview_run_id, employee_key);

CREATE TABLE IF NOT EXISTS payroll_preview_events (
  event_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  company_code text NOT NULL,
  preview_run_id uuid REFERENCES payroll_preview_runs(preview_run_id) ON DELETE SET NULL,
  event_type text NOT NULL,
  payload jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_by_phone text,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_payroll_preview_events_run
  ON payroll_preview_events(company_code, preview_run_id, created_at DESC);
