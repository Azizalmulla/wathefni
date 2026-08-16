-- Payroll Authority P1 — Canonical sealed money snapshot (v1.0.0)
-- Additive only. Does NOT alter Wave 1 / 2A / 2B / 3 / 4 / 5 money semantics.
--
-- money_authority ∈ {wathefni, external}
-- P1 Mode B seals external imports as money_authority=external.
-- P1 Mode A foundation only: wathefni seal path exists in schema but is refused until
-- a future authoritative-finalize phase (native preview remains preview_non_authoritative).
--
-- Period close (Wave 4) is NOT money seal. payment_processing remains disabled.
-- No invented payment_date. No statutory formulas. No payment rails.

CREATE TABLE IF NOT EXISTS payroll_component_catalog (
  component_code text PRIMARY KEY,
  category text NOT NULL,
  label_en text NOT NULL,
  label_ar text NOT NULL,
  line_kind text NOT NULL,
  amount_unit text NOT NULL DEFAULT 'monthly',
  taxable_treatment text,
  statutory_treatment text,
  counsel_gated boolean NOT NULL DEFAULT false,
  kuwait_ready boolean NOT NULL DEFAULT true,
  gcc_extensible boolean NOT NULL DEFAULT true,
  source_default text,
  policy_version_hook text,
  metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT payroll_component_category_chk
    CHECK (category IN (
      'earning_basic',
      'earning_allowance_recurring',
      'earning_allowance_one_off',
      'earning_overtime',
      'earning_rest_day_ph',
      'earning_attendance_impact',
      'deduction_recurring',
      'deduction_one_off',
      'deduction_unpaid_leave',
      'deduction_sick_leave',
      'statutory_pifss_ee',
      'statutory_pifss_er',
      'statutory_eos',
      'external_opaque',
      'other'
    )),
  CONSTRAINT payroll_component_line_kind_chk
    CHECK (line_kind IN ('earning', 'deduction', 'employer_statutory', 'info')),
  CONSTRAINT payroll_component_amount_unit_chk
    CHECK (amount_unit IN ('monthly', 'one_time', 'hourly', 'daily', 'percent_of_base', 'percent_of_gross', 'opaque'))
);

INSERT INTO payroll_component_catalog (
  component_code, category, label_en, label_ar, line_kind, amount_unit,
  statutory_treatment, counsel_gated, metadata
) VALUES
  ('BASIC', 'earning_basic', 'Basic salary', 'الراتب الأساسي', 'earning', 'monthly', NULL, false, '{"phase":"p1_foundation"}'::jsonb),
  ('ALLOWANCE.TRANSPORT', 'earning_allowance_recurring', 'Transport allowance', 'بدل مواصلات', 'earning', 'monthly', NULL, false, '{"phase":"p1_foundation"}'::jsonb),
  ('ALLOWANCE.HOUSING', 'earning_allowance_recurring', 'Housing allowance', 'بدل سكن', 'earning', 'monthly', NULL, false, '{"phase":"p1_foundation"}'::jsonb),
  ('ALLOWANCE.ONE_OFF', 'earning_allowance_one_off', 'One-off allowance', 'بدل لمرة واحدة', 'earning', 'one_time', NULL, false, '{"phase":"p1_foundation"}'::jsonb),
  ('DEDUCTION.ONE_OFF', 'deduction_one_off', 'One-off deduction', 'استقطاع لمرة واحدة', 'deduction', 'one_time', NULL, false, '{"phase":"p1_foundation"}'::jsonb),
  ('DEDUCTION.RECURRING', 'deduction_recurring', 'Recurring deduction', 'استقطاع متكرر', 'deduction', 'monthly', NULL, false, '{"phase":"p1_foundation"}'::jsonb),
  ('UNPAID_LEAVE', 'deduction_unpaid_leave', 'Unpaid leave', 'إجازة بدون راتب', 'deduction', 'daily', NULL, false, '{"phase":"p1_foundation","calc_phase":"p2_plus"}'::jsonb),
  ('SICK_LEAVE', 'deduction_sick_leave', 'Sick leave pay impact', 'أثر إجازة مرضية', 'deduction', 'daily', 'kuwait_art_69', true, '{"phase":"p1_foundation","calc_phase":"counsel_gated"}'::jsonb),
  ('OT_ORDINARY', 'earning_overtime', 'Ordinary overtime', 'عمل إضافي عادي', 'earning', 'hourly', 'kuwait_art_66', true, '{"phase":"p1_foundation","calc_phase":"counsel_gated"}'::jsonb),
  ('OT_REST_DAY_PH', 'earning_rest_day_ph', 'Rest day / public holiday pay', 'أجر راحة / عطلة رسمية', 'earning', 'hourly', 'kuwait_art_66', true, '{"phase":"p1_foundation","calc_phase":"counsel_gated"}'::jsonb),
  ('ATTENDANCE_IMPACT', 'earning_attendance_impact', 'Attendance pay impact', 'أثر الحضور على الأجر', 'earning', 'daily', NULL, false, '{"phase":"p1_foundation","calc_phase":"p2_plus"}'::jsonb),
  ('PIFSS_EE', 'statutory_pifss_ee', 'PIFSS employee share', 'حصة الموظف PIFSS', 'deduction', 'monthly', 'kuwait_pifss', true, '{"phase":"p1_foundation","calc_phase":"counsel_gated"}'::jsonb),
  ('PIFSS_ER', 'statutory_pifss_er', 'PIFSS employer share', 'حصة صاحب العمل PIFSS', 'employer_statutory', 'monthly', 'kuwait_pifss', true, '{"phase":"p1_foundation","calc_phase":"counsel_gated"}'::jsonb),
  ('EOS_INDEMNITY', 'statutory_eos', 'End of service indemnity', 'مكافأة نهاية الخدمة', 'info', 'one_time', 'kuwait_eos', true, '{"phase":"p1_foundation","calc_phase":"counsel_gated"}'::jsonb),
  ('EXTERNAL.OPAQUE', 'external_opaque', 'External opaque component', 'مكون خارجي غير شفاف', 'earning', 'opaque', NULL, false, '{"phase":"p1_mode_b"}'::jsonb)
ON CONFLICT (component_code) DO NOTHING;

CREATE TABLE IF NOT EXISTS payroll_authority_snapshots (
  authority_snapshot_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  company_code text NOT NULL,
  employee_key text NOT NULL,
  period_id uuid,
  period_start date NOT NULL,
  period_end date NOT NULL,
  currency text NOT NULL DEFAULT 'KWD',
  money_authority text NOT NULL,
  source_kind text NOT NULL,
  source_mode text NOT NULL,
  status text NOT NULL DEFAULT 'sealed',
  import_run_id uuid,
  preview_run_id uuid,
  close_run_id uuid,
  external_run_id text,
  source_fingerprint text NOT NULL,
  content_fingerprint text NOT NULL,
  calculation_policy_version text,
  compensation_source text,
  compensation_version text,
  totals_earnings numeric(14,3) NOT NULL DEFAULT 0,
  totals_deductions numeric(14,3) NOT NULL DEFAULT 0,
  totals_gross numeric(14,3) NOT NULL DEFAULT 0,
  totals_net numeric(14,3) NOT NULL DEFAULT 0,
  payment_processing text NOT NULL DEFAULT 'disabled',
  posts_payment boolean NOT NULL DEFAULT false,
  snapshot_payload jsonb NOT NULL DEFAULT '{}'::jsonb,
  provenance jsonb NOT NULL DEFAULT '{}'::jsonb,
  replaces_snapshot_id uuid,
  superseded_by uuid,
  payslip_id uuid,
  sealed_at timestamptz NOT NULL DEFAULT now(),
  sealed_by_phone text,
  finalized_by_phone text,
  approval_actor_chain jsonb NOT NULL DEFAULT '[]'::jsonb,
  decision_note text,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  row_version integer NOT NULL DEFAULT 1,
  CONSTRAINT payroll_auth_snap_money_chk
    CHECK (money_authority IN ('wathefni', 'external')),
  CONSTRAINT payroll_auth_snap_source_kind_chk
    CHECK (source_kind IN ('external_import', 'native_authoritative', 'native_preview_refused')),
  CONSTRAINT payroll_auth_snap_source_mode_chk
    CHECK (source_mode IN ('mode_b_external', 'mode_a_wathefni', 'mode_a_foundation_refused')),
  CONSTRAINT payroll_auth_snap_status_chk
    CHECK (status IN ('sealed', 'replaced', 'revoked')),
  CONSTRAINT payroll_auth_snap_payment_disabled_chk
    CHECK (payment_processing = 'disabled'),
  CONSTRAINT payroll_auth_snap_no_posts_payment_chk
    CHECK (posts_payment = false),
  CONSTRAINT payroll_auth_snap_currency_kwd_chk
    CHECK (currency = 'KWD')
);

CREATE UNIQUE INDEX IF NOT EXISTS payroll_auth_snap_current_sealed_uniq
  ON payroll_authority_snapshots (company_code, employee_key, period_start, period_end)
  WHERE status = 'sealed';

CREATE UNIQUE INDEX IF NOT EXISTS payroll_auth_snap_external_source_uniq
  ON payroll_authority_snapshots (company_code, import_run_id, employee_key)
  WHERE status = 'sealed' AND import_run_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_payroll_auth_snap_employee
  ON payroll_authority_snapshots (company_code, employee_key, period_start DESC, sealed_at DESC);

CREATE INDEX IF NOT EXISTS idx_payroll_auth_snap_import
  ON payroll_authority_snapshots (company_code, import_run_id);

CREATE INDEX IF NOT EXISTS idx_payroll_auth_snap_status
  ON payroll_authority_snapshots (company_code, status, sealed_at DESC);

CREATE TABLE IF NOT EXISTS payroll_authority_snapshot_lines (
  line_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  authority_snapshot_id uuid NOT NULL REFERENCES payroll_authority_snapshots(authority_snapshot_id),
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
  source text NOT NULL,
  policy_version text,
  taxable_treatment text,
  statutory_treatment text,
  sort_order integer NOT NULL DEFAULT 0,
  provenance jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT payroll_auth_line_kind_chk
    CHECK (line_kind IN ('earning', 'deduction', 'employer_statutory', 'info'))
);

CREATE INDEX IF NOT EXISTS idx_payroll_auth_lines_snap
  ON payroll_authority_snapshot_lines (authority_snapshot_id, sort_order);

CREATE TABLE IF NOT EXISTS payroll_authority_snapshot_events (
  event_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  authority_snapshot_id uuid,
  company_code text NOT NULL,
  event_type text NOT NULL,
  payload jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_by_phone text,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_payroll_auth_events_co
  ON payroll_authority_snapshot_events (company_code, created_at DESC);

-- Link payslip projection → sealed money authority (additive; nullable for legacy rows).
ALTER TABLE payroll_payslip_documents
  ADD COLUMN IF NOT EXISTS authority_snapshot_id uuid;

CREATE INDEX IF NOT EXISTS idx_payroll_payslip_authority_snapshot
  ON payroll_payslip_documents (authority_snapshot_id)
  WHERE authority_snapshot_id IS NOT NULL;
