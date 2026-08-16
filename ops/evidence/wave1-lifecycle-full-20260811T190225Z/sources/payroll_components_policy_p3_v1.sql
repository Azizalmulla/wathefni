-- Payroll Authority P3 — Components + time-pay policy + Mode A preview calc (v1.0.0)
-- Additive. Does NOT unlock Mode A money authority / official native PDF / payments.
-- Preview results remain money_authority=preview_non_authoritative.
-- OT/rest-day/PH/sick statutory rates remain counsel_gated until approved rate tables.

-- Expand catalog categories for lateness / absence deductions (additive CHECK via new seeds only;
-- existing category CHECK already covers needed families; add new codes).

INSERT INTO payroll_component_catalog (
  component_code, category, label_en, label_ar, line_kind, amount_unit,
  statutory_treatment, counsel_gated, metadata
) VALUES
  ('ALLOWANCE.PHONE', 'earning_allowance_recurring', 'Phone allowance', 'بدل هاتف', 'earning', 'monthly', NULL, false, '{"phase":"p3"}'::jsonb),
  ('ALLOWANCE.BONUS', 'earning_allowance_one_off', 'Bonus', 'مكافأة', 'earning', 'one_time', NULL, false, '{"phase":"p3"}'::jsonb),
  ('ALLOWANCE.COMMISSION', 'earning_allowance_one_off', 'Commission / manual earning', 'عمولة / أجر يدوي', 'earning', 'one_time', NULL, false, '{"phase":"p3"}'::jsonb),
  ('DEDUCTION.LOAN', 'deduction_recurring', 'Loan deduction', 'استقطاع قرض', 'deduction', 'monthly', NULL, false, '{"phase":"p3"}'::jsonb),
  ('DEDUCTION.LATENESS', 'deduction_one_off', 'Lateness deduction', 'استقطاع تأخير', 'deduction', 'daily', NULL, false, '{"phase":"p3","policy_driven":true}'::jsonb),
  ('DEDUCTION.ABSENCE', 'deduction_unpaid_leave', 'Unpaid absence deduction', 'استقطاع غياب بدون راتب', 'deduction', 'daily', NULL, false, '{"phase":"p3","policy_driven":true}'::jsonb),
  ('CUSTOM.EARNING', 'other', 'Custom earning', 'أرباح مخصصة', 'earning', 'monthly', NULL, false, '{"phase":"p3","company_defined":true}'::jsonb),
  ('CUSTOM.DEDUCTION', 'other', 'Custom deduction', 'استقطاع مخصص', 'deduction', 'monthly', NULL, false, '{"phase":"p3","company_defined":true}'::jsonb)
ON CONFLICT (component_code) DO NOTHING;

CREATE TABLE IF NOT EXISTS payroll_company_policy_versions (
  policy_version_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  company_code text NOT NULL,
  version_number integer NOT NULL,
  status text NOT NULL DEFAULT 'draft',
  effective_from date NOT NULL,
  effective_to date,
  attendance_payroll_mode text NOT NULL DEFAULT 'required',
  lateness_money_enabled boolean NOT NULL DEFAULT false,
  lateness_grace_minutes integer NOT NULL DEFAULT 0,
  absence_money_enabled boolean NOT NULL DEFAULT true,
  unpaid_leave_money_enabled boolean NOT NULL DEFAULT true,
  ot_money_enabled boolean NOT NULL DEFAULT false,
  rest_day_money_enabled boolean NOT NULL DEFAULT false,
  public_holiday_money_enabled boolean NOT NULL DEFAULT false,
  sick_leave_money_enabled boolean NOT NULL DEFAULT false,
  ot_eligible_groups jsonb NOT NULL DEFAULT '["all"]'::jsonb,
  rounding_mode text NOT NULL DEFAULT 'half_up_3',
  currency text NOT NULL DEFAULT 'KWD',
  policy_payload jsonb NOT NULL DEFAULT '{}'::jsonb,
  content_fingerprint text NOT NULL,
  decision_note text,
  created_by_phone text,
  approved_by_phone text,
  approved_at timestamptz,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  row_version integer NOT NULL DEFAULT 1,
  CONSTRAINT payroll_policy_status_chk
    CHECK (status IN ('draft', 'approved', 'superseded', 'cancelled')),
  CONSTRAINT payroll_policy_att_mode_chk
    CHECK (attendance_payroll_mode IN ('required', 'informational', 'ignored')),
  CONSTRAINT payroll_policy_round_chk
    CHECK (rounding_mode IN ('half_up_3', 'floor_3', 'ceil_3')),
  CONSTRAINT payroll_policy_dates_chk
    CHECK (effective_to IS NULL OR effective_to >= effective_from),
  UNIQUE (company_code, version_number)
);

CREATE UNIQUE INDEX IF NOT EXISTS payroll_policy_active_uniq
  ON payroll_company_policy_versions (company_code, effective_from)
  WHERE status = 'approved';

CREATE INDEX IF NOT EXISTS idx_payroll_policy_co
  ON payroll_company_policy_versions (company_code, status, effective_from DESC);

CREATE TABLE IF NOT EXISTS payroll_rate_tables (
  rate_table_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  company_code text NOT NULL,
  rule_family text NOT NULL,
  status text NOT NULL DEFAULT 'counsel_required',
  country_code text NOT NULL DEFAULT 'KW',
  version_label text NOT NULL,
  effective_from date NOT NULL,
  effective_to date,
  multiplier numeric(8,4),
  fraction_payload jsonb NOT NULL DEFAULT '{}'::jsonb,
  counsel_signed boolean NOT NULL DEFAULT false,
  counsel_note text,
  content_fingerprint text NOT NULL,
  created_by_phone text,
  approved_by_phone text,
  approved_at timestamptz,
  created_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT payroll_rate_family_chk
    CHECK (rule_family IN (
      'ot_ordinary',
      'rest_day_work',
      'public_holiday_work',
      'sick_leave_fractions'
    )),
  CONSTRAINT payroll_rate_status_chk
    CHECK (status IN ('counsel_required', 'draft', 'approved', 'superseded', 'cancelled'))
);

CREATE INDEX IF NOT EXISTS idx_payroll_rate_tables_co
  ON payroll_rate_tables (company_code, rule_family, status, effective_from DESC);

CREATE TABLE IF NOT EXISTS payroll_company_components (
  company_component_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  company_code text NOT NULL,
  catalog_code text NOT NULL,
  component_code text NOT NULL,
  label_en text NOT NULL,
  label_ar text,
  line_kind text NOT NULL,
  amount_unit text NOT NULL DEFAULT 'monthly',
  default_amount numeric(14,3),
  is_custom boolean NOT NULL DEFAULT false,
  active boolean NOT NULL DEFAULT true,
  effective_from date NOT NULL DEFAULT CURRENT_DATE,
  effective_to date,
  metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_by_phone text,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT payroll_co_comp_line_chk
    CHECK (line_kind IN ('earning', 'deduction')),
  CONSTRAINT payroll_co_comp_unit_chk
    CHECK (amount_unit IN ('monthly', 'one_time', 'hourly', 'daily', 'percent_of_base', 'percent_of_gross')),
  UNIQUE (company_code, component_code)
);

CREATE TABLE IF NOT EXISTS payroll_component_assignments (
  assignment_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  company_code text NOT NULL,
  employee_key text,
  employee_group text,
  company_component_id uuid NOT NULL REFERENCES payroll_company_components(company_component_id),
  amount numeric(14,3) NOT NULL,
  effective_from date NOT NULL,
  effective_to date,
  status text NOT NULL DEFAULT 'active',
  decision_note text,
  created_by_phone text,
  created_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT payroll_assign_status_chk
    CHECK (status IN ('active', 'ended', 'cancelled')),
  CONSTRAINT payroll_assign_target_chk
    CHECK (
      (employee_key IS NOT NULL AND employee_group IS NULL)
      OR (employee_key IS NULL AND employee_group IS NOT NULL)
    )
);

CREATE INDEX IF NOT EXISTS idx_payroll_assign_emp
  ON payroll_component_assignments (company_code, employee_key, status, effective_from);

CREATE TABLE IF NOT EXISTS payroll_one_off_adjustments (
  adjustment_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  company_code text NOT NULL,
  employee_key text NOT NULL,
  period_start date NOT NULL,
  period_end date NOT NULL,
  component_code text NOT NULL,
  line_kind text NOT NULL,
  amount numeric(14,3) NOT NULL,
  label_en text,
  label_ar text,
  status text NOT NULL DEFAULT 'approved',
  decision_note text NOT NULL,
  created_by_phone text,
  approved_by_phone text,
  created_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT payroll_adj_line_chk
    CHECK (line_kind IN ('earning', 'deduction')),
  CONSTRAINT payroll_adj_status_chk
    CHECK (status IN ('draft', 'approved', 'cancelled'))
);

CREATE INDEX IF NOT EXISTS idx_payroll_adj_period
  ON payroll_one_off_adjustments (company_code, employee_key, period_start, period_end);

CREATE TABLE IF NOT EXISTS payroll_calc_preview_runs (
  calc_run_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  company_code text NOT NULL,
  period_start date NOT NULL,
  period_end date NOT NULL,
  input_snapshot_id uuid NOT NULL,
  policy_version_id uuid NOT NULL,
  catalog_fingerprint text NOT NULL,
  compensation_fingerprint text NOT NULL,
  policy_fingerprint text NOT NULL,
  input_fingerprint text NOT NULL,
  content_fingerprint text NOT NULL,
  status text NOT NULL DEFAULT 'calculated',
  money_authority text NOT NULL DEFAULT 'preview_non_authoritative',
  payment_processing text NOT NULL DEFAULT 'disabled',
  posts_payment boolean NOT NULL DEFAULT false,
  currency text NOT NULL DEFAULT 'KWD',
  employee_count integer NOT NULL DEFAULT 0,
  totals_earnings numeric(14,3) NOT NULL DEFAULT 0,
  totals_deductions numeric(14,3) NOT NULL DEFAULT 0,
  totals_gross numeric(14,3) NOT NULL DEFAULT 0,
  totals_net numeric(14,3) NOT NULL DEFAULT 0,
  blocker_count integer NOT NULL DEFAULT 0,
  warning_count integer NOT NULL DEFAULT 0,
  result_payload jsonb NOT NULL DEFAULT '{}'::jsonb,
  provenance jsonb NOT NULL DEFAULT '{}'::jsonb,
  decision_note text,
  created_by_phone text,
  created_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT payroll_calc_status_chk
    CHECK (status IN ('calculated', 'blocked', 'superseded')),
  CONSTRAINT payroll_calc_money_chk
    CHECK (money_authority = 'preview_non_authoritative'),
  CONSTRAINT payroll_calc_payment_chk
    CHECK (payment_processing = 'disabled'),
  CONSTRAINT payroll_calc_no_posts_chk
    CHECK (posts_payment = false)
);

CREATE UNIQUE INDEX IF NOT EXISTS payroll_calc_idempotent_uniq
  ON payroll_calc_preview_runs (company_code, content_fingerprint)
  WHERE status = 'calculated';

CREATE INDEX IF NOT EXISTS idx_payroll_calc_input
  ON payroll_calc_preview_runs (company_code, input_snapshot_id, created_at DESC);

CREATE TABLE IF NOT EXISTS payroll_calc_preview_employee_results (
  result_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  calc_run_id uuid NOT NULL REFERENCES payroll_calc_preview_runs(calc_run_id),
  company_code text NOT NULL,
  employee_key text NOT NULL,
  status text NOT NULL,
  totals_earnings numeric(14,3) NOT NULL DEFAULT 0,
  totals_deductions numeric(14,3) NOT NULL DEFAULT 0,
  totals_gross numeric(14,3) NOT NULL DEFAULT 0,
  totals_net numeric(14,3) NOT NULL DEFAULT 0,
  blockers jsonb NOT NULL DEFAULT '[]'::jsonb,
  warnings jsonb NOT NULL DEFAULT '[]'::jsonb,
  provenance jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (calc_run_id, employee_key)
);

CREATE TABLE IF NOT EXISTS payroll_calc_preview_lines (
  line_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  calc_run_id uuid NOT NULL REFERENCES payroll_calc_preview_runs(calc_run_id),
  company_code text NOT NULL,
  employee_key text NOT NULL,
  component_code text NOT NULL,
  catalog_code text,
  line_kind text NOT NULL,
  category text,
  label_en text,
  label_ar text,
  amount numeric(14,3) NOT NULL DEFAULT 0,
  currency text NOT NULL DEFAULT 'KWD',
  policy_version_id uuid,
  input_line_id uuid,
  contract_id uuid,
  sort_order integer NOT NULL DEFAULT 0,
  calc_notes jsonb NOT NULL DEFAULT '{}'::jsonb,
  provenance jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_payroll_calc_lines
  ON payroll_calc_preview_lines (calc_run_id, employee_key, sort_order);

CREATE TABLE IF NOT EXISTS payroll_calc_preview_events (
  event_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  calc_run_id uuid,
  company_code text NOT NULL,
  event_type text NOT NULL,
  payload jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_by_phone text,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_payroll_calc_events
  ON payroll_calc_preview_events (company_code, created_at DESC);
