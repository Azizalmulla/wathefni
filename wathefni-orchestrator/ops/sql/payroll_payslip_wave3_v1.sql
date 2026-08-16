-- Payroll Payslip Wave 3 — display payslips (v1.0.0)
-- Additive only. Does NOT alter Wave 1 / 2A / 2B DDL.
-- Native payslips = non-authoritative preview documents.
-- External payslips = mirror of imported results; money_authority remains external.
-- payment_processing remains disabled. No bank/WPS/PIFSS/EOS/journals/payments.

CREATE TABLE IF NOT EXISTS payroll_payslip_documents (
  payslip_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  company_code text NOT NULL,
  source_kind text NOT NULL,
  source_run_id uuid NOT NULL,
  employee_key text NOT NULL,
  period_start date NOT NULL,
  period_end date NOT NULL,
  version_number integer NOT NULL DEFAULT 1,
  status text NOT NULL DEFAULT 'active',
  replaces_payslip_id uuid,
  superseded_by uuid,
  content_fingerprint text NOT NULL,
  money_authority text NOT NULL,
  authoritative_label text NOT NULL,
  payment_processing text NOT NULL DEFAULT 'disabled',
  posts_payment boolean NOT NULL DEFAULT false,
  currency text NOT NULL DEFAULT 'KWD',
  totals_earnings numeric(14,3) NOT NULL DEFAULT 0,
  totals_deductions numeric(14,3) NOT NULL DEFAULT 0,
  totals_net numeric(14,3) NOT NULL DEFAULT 0,
  document_payload jsonb NOT NULL DEFAULT '{}'::jsonb,
  locale_default text NOT NULL DEFAULT 'en',
  decision_note text,
  created_by_phone text,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  row_version integer NOT NULL DEFAULT 1,
  CONSTRAINT payroll_payslip_source_kind_chk
    CHECK (source_kind IN ('native_preview', 'external_import')),
  CONSTRAINT payroll_payslip_status_chk
    CHECK (status IN ('active', 'replaced', 'revoked')),
  CONSTRAINT payroll_payslip_money_authority_chk
    CHECK (money_authority IN ('preview_non_authoritative', 'external')),
  CONSTRAINT payroll_payslip_payment_disabled_chk
    CHECK (payment_processing = 'disabled'),
  CONSTRAINT payroll_payslip_no_posts_payment_chk
    CHECK (posts_payment = false),
  CONSTRAINT payroll_payslip_locale_chk
    CHECK (locale_default IN ('en', 'ar'))
);

CREATE UNIQUE INDEX IF NOT EXISTS payroll_payslip_active_uniq
  ON payroll_payslip_documents (company_code, source_kind, source_run_id, employee_key)
  WHERE status = 'active';

CREATE INDEX IF NOT EXISTS idx_payroll_payslip_employee
  ON payroll_payslip_documents (company_code, employee_key, period_start DESC, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_payroll_payslip_source
  ON payroll_payslip_documents (company_code, source_kind, source_run_id);

CREATE TABLE IF NOT EXISTS payroll_payslip_lines (
  line_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  payslip_id uuid NOT NULL REFERENCES payroll_payslip_documents(payslip_id),
  company_code text NOT NULL,
  employee_key text NOT NULL,
  line_kind text NOT NULL,
  code text NOT NULL,
  label_en text,
  label_ar text,
  amount numeric(14,3) NOT NULL DEFAULT 0,
  currency text NOT NULL DEFAULT 'KWD',
  sort_order integer NOT NULL DEFAULT 0,
  calc_notes jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_payroll_payslip_lines_doc
  ON payroll_payslip_lines (payslip_id, sort_order);

CREATE TABLE IF NOT EXISTS payroll_payslip_events (
  event_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  payslip_id uuid,
  company_code text NOT NULL,
  event_type text NOT NULL,
  payload jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_by_phone text,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_payroll_payslip_events_co
  ON payroll_payslip_events (company_code, created_at DESC);
