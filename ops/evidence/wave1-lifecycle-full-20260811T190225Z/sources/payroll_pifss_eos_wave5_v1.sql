-- Payroll Wave 5 — PIFSS + EOS review worksheets (v1.0.0)
-- Additive only. Does NOT alter Wave 1–4 DDL.
-- Worksheets are non-authoritative review artefacts only.
-- No remittance, statutory filing, automatic compliance claim, bank/WPS/AS'HAL, or payable instruction.
-- payment_processing remains disabled. Native remains non-authoritative; external remains money authority.

CREATE TABLE IF NOT EXISTS payroll_statutory_rule_tables (
  rule_table_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  company_code text NOT NULL,
  rule_domain text NOT NULL,
  rule_code text NOT NULL,
  employee_category text NOT NULL,
  version_label text NOT NULL,
  effective_from date NOT NULL,
  effective_to date,
  counsel_status text NOT NULL DEFAULT 'pending',
  source_citation text NOT NULL,
  provenance jsonb NOT NULL DEFAULT '{}'::jsonb,
  rule_payload jsonb NOT NULL DEFAULT '{}'::jsonb,
  decision_note text,
  created_by_phone text,
  counsel_approved_by_phone text,
  counsel_approved_at timestamptz,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  row_version integer NOT NULL DEFAULT 1,
  CONSTRAINT payroll_stat_rule_domain_chk
    CHECK (rule_domain IN ('pifss', 'eos')),
  CONSTRAINT payroll_stat_rule_category_chk
    CHECK (employee_category IN (
      'kuwaiti_national', 'gcc_national', 'expatriate', 'any'
    )),
  CONSTRAINT payroll_stat_rule_counsel_chk
    CHECK (counsel_status IN ('pending', 'approved', 'revoked', 'unsupported')),
  CONSTRAINT payroll_stat_rule_dates_chk
    CHECK (effective_to IS NULL OR effective_to >= effective_from)
);

CREATE UNIQUE INDEX IF NOT EXISTS payroll_stat_rule_active_uniq
  ON payroll_statutory_rule_tables (company_code, rule_domain, rule_code, employee_category, version_label);

CREATE INDEX IF NOT EXISTS idx_payroll_stat_rule_lookup
  ON payroll_statutory_rule_tables (company_code, rule_domain, employee_category, effective_from DESC);

CREATE TABLE IF NOT EXISTS payroll_pifss_worksheets (
  worksheet_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  company_code text NOT NULL,
  employee_key text NOT NULL,
  employee_category text NOT NULL,
  period_start date NOT NULL,
  period_end date NOT NULL,
  status text NOT NULL DEFAULT 'draft',
  rule_table_id uuid REFERENCES payroll_statutory_rule_tables(rule_table_id),
  rule_version_label text,
  input_fingerprint text NOT NULL,
  content_fingerprint text NOT NULL,
  source_provenance jsonb NOT NULL DEFAULT '{}'::jsonb,
  worksheet_payload jsonb NOT NULL DEFAULT '{}'::jsonb,
  money_authority text NOT NULL DEFAULT 'review_non_authoritative',
  payment_processing text NOT NULL DEFAULT 'disabled',
  posts_payment boolean NOT NULL DEFAULT false,
  remittance boolean NOT NULL DEFAULT false,
  statutory_filing boolean NOT NULL DEFAULT false,
  automatic_legal_compliance_claim boolean NOT NULL DEFAULT false,
  authoritative_label text NOT NULL DEFAULT 'review_worksheet_only',
  exception_code text,
  exception_evidence jsonb NOT NULL DEFAULT '{}'::jsonb,
  supersedes_worksheet_id uuid,
  superseded_by uuid,
  created_by_phone text,
  submitted_by_phone text,
  submitted_at timestamptz,
  approved_by_phone text,
  approved_at timestamptz,
  decision_note text,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  row_version integer NOT NULL DEFAULT 1,
  CONSTRAINT payroll_pifss_category_chk
    CHECK (employee_category IN ('kuwaiti_national', 'gcc_national', 'expatriate')),
  CONSTRAINT payroll_pifss_status_chk
    CHECK (status IN (
      'draft', 'in_review', 'exception', 'approved', 'superseded',
      'unsupported', 'counsel_required'
    )),
  CONSTRAINT payroll_pifss_money_chk
    CHECK (money_authority = 'review_non_authoritative'),
  CONSTRAINT payroll_pifss_payment_chk
    CHECK (payment_processing = 'disabled'),
  CONSTRAINT payroll_pifss_no_posts_chk
    CHECK (posts_payment = false),
  CONSTRAINT payroll_pifss_no_remit_chk
    CHECK (remittance = false),
  CONSTRAINT payroll_pifss_no_filing_chk
    CHECK (statutory_filing = false),
  CONSTRAINT payroll_pifss_no_auto_claim_chk
    CHECK (automatic_legal_compliance_claim = false)
);

CREATE UNIQUE INDEX IF NOT EXISTS payroll_pifss_active_uniq
  ON payroll_pifss_worksheets (company_code, employee_key, period_start, period_end)
  WHERE status IN ('draft', 'in_review', 'exception', 'approved', 'unsupported', 'counsel_required');

CREATE INDEX IF NOT EXISTS idx_payroll_pifss_employee
  ON payroll_pifss_worksheets (company_code, employee_key, period_start DESC);

CREATE TABLE IF NOT EXISTS payroll_eos_worksheets (
  worksheet_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  company_code text NOT NULL,
  employee_key text NOT NULL,
  employee_category text NOT NULL,
  termination_date date NOT NULL,
  termination_reason text NOT NULL,
  service_start date NOT NULL,
  service_end date NOT NULL,
  status text NOT NULL DEFAULT 'draft',
  rule_table_id uuid REFERENCES payroll_statutory_rule_tables(rule_table_id),
  rule_version_label text,
  art_51_53_status text NOT NULL DEFAULT 'unresolved_blocked',
  law_17_2018_status text NOT NULL DEFAULT 'unresolved_blocked',
  input_fingerprint text NOT NULL,
  content_fingerprint text NOT NULL,
  source_provenance jsonb NOT NULL DEFAULT '{}'::jsonb,
  service_period_evidence jsonb NOT NULL DEFAULT '{}'::jsonb,
  worksheet_payload jsonb NOT NULL DEFAULT '{}'::jsonb,
  money_authority text NOT NULL DEFAULT 'review_non_authoritative',
  payment_processing text NOT NULL DEFAULT 'disabled',
  posts_payment boolean NOT NULL DEFAULT false,
  automatic_payable_instruction boolean NOT NULL DEFAULT false,
  remittance boolean NOT NULL DEFAULT false,
  statutory_filing boolean NOT NULL DEFAULT false,
  automatic_legal_compliance_claim boolean NOT NULL DEFAULT false,
  authoritative_label text NOT NULL DEFAULT 'review_worksheet_only',
  exception_code text,
  exception_evidence jsonb NOT NULL DEFAULT '{}'::jsonb,
  supersedes_worksheet_id uuid,
  superseded_by uuid,
  created_by_phone text,
  submitted_by_phone text,
  submitted_at timestamptz,
  approved_by_phone text,
  approved_at timestamptz,
  decision_note text,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  row_version integer NOT NULL DEFAULT 1,
  CONSTRAINT payroll_eos_category_chk
    CHECK (employee_category IN ('kuwaiti_national', 'gcc_national', 'expatriate')),
  CONSTRAINT payroll_eos_status_chk
    CHECK (status IN (
      'draft', 'in_review', 'exception', 'approved', 'superseded',
      'unsupported', 'counsel_required'
    )),
  CONSTRAINT payroll_eos_art_chk
    CHECK (art_51_53_status IN ('resolved', 'unresolved_blocked', 'counsel_required', 'not_applicable')),
  CONSTRAINT payroll_eos_law17_chk
    CHECK (law_17_2018_status IN ('resolved', 'unresolved_blocked', 'counsel_required', 'not_applicable')),
  CONSTRAINT payroll_eos_money_chk
    CHECK (money_authority = 'review_non_authoritative'),
  CONSTRAINT payroll_eos_payment_chk
    CHECK (payment_processing = 'disabled'),
  CONSTRAINT payroll_eos_no_posts_chk
    CHECK (posts_payment = false),
  CONSTRAINT payroll_eos_no_payable_chk
    CHECK (automatic_payable_instruction = false),
  CONSTRAINT payroll_eos_no_remit_chk
    CHECK (remittance = false),
  CONSTRAINT payroll_eos_no_filing_chk
    CHECK (statutory_filing = false),
  CONSTRAINT payroll_eos_no_auto_claim_chk
    CHECK (automatic_legal_compliance_claim = false),
  CONSTRAINT payroll_eos_service_chk
    CHECK (service_end >= service_start)
);

CREATE UNIQUE INDEX IF NOT EXISTS payroll_eos_active_uniq
  ON payroll_eos_worksheets (company_code, employee_key, termination_date)
  WHERE status IN ('draft', 'in_review', 'exception', 'approved', 'unsupported', 'counsel_required');

CREATE INDEX IF NOT EXISTS idx_payroll_eos_employee
  ON payroll_eos_worksheets (company_code, employee_key, termination_date DESC);

CREATE TABLE IF NOT EXISTS payroll_statutory_worksheet_events (
  event_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  company_code text NOT NULL,
  worksheet_kind text NOT NULL,
  worksheet_id uuid,
  event_type text NOT NULL,
  payload jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_by_phone text,
  created_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT payroll_stat_event_kind_chk
    CHECK (worksheet_kind IN ('pifss', 'eos', 'rule_table'))
);

CREATE INDEX IF NOT EXISTS idx_payroll_stat_events_co
  ON payroll_statutory_worksheet_events (company_code, created_at DESC);

CREATE TABLE IF NOT EXISTS payroll_statutory_dual_control (
  action_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  company_code text NOT NULL,
  worksheet_kind text NOT NULL,
  worksheet_id uuid NOT NULL,
  action_kind text NOT NULL,
  status text NOT NULL DEFAULT 'pending_second',
  initiated_by_phone text NOT NULL,
  confirmed_by_phone text,
  confirmed_at timestamptz,
  payload jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT payroll_stat_dual_kind_ws_chk
    CHECK (worksheet_kind IN ('pifss', 'eos')),
  CONSTRAINT payroll_stat_dual_action_chk
    CHECK (action_kind IN ('manual_override_exception')),
  CONSTRAINT payroll_stat_dual_status_chk
    CHECK (status IN ('pending_second', 'confirmed', 'cancelled'))
);

CREATE INDEX IF NOT EXISTS idx_payroll_stat_dual_ws
  ON payroll_statutory_dual_control (company_code, worksheet_kind, worksheet_id, status);
