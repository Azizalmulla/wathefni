-- Payroll Authority P4A — Kuwait statutory architecture + counsel-gated packaging (v1.0.0)
-- Additive. Does NOT invent Kuwait legal rates. Does NOT unlock Mode A / native PDF / payments.
-- Fixtures may use is_architecture_fixture=true with legal_claim=false only.
-- Payroll money paths consume approval_status=approved AND legal_claim=true only.

-- Country-scoped statutory package (Kuwait first; GCC-extensible via country_code)
CREATE TABLE IF NOT EXISTS payroll_statutory_packages (
  package_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  country_code text NOT NULL DEFAULT 'KW',
  company_code text, -- NULL = country-level template; set for company overlay
  package_code text NOT NULL,
  version_number integer NOT NULL,
  approval_status text NOT NULL DEFAULT 'draft',
  legal_claim boolean NOT NULL DEFAULT false,
  is_architecture_fixture boolean NOT NULL DEFAULT false,
  effective_from date NOT NULL,
  effective_to date,
  title_en text NOT NULL,
  title_ar text,
  content_fingerprint text NOT NULL,
  provenance jsonb NOT NULL DEFAULT '{}'::jsonb,
  decision_note text,
  created_by_phone text,
  validated_by_phone text,
  validated_at timestamptz,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  row_version integer NOT NULL DEFAULT 1,
  CONSTRAINT payroll_stat_pkg_status_chk
    CHECK (approval_status IN (
      'draft',
      'awaiting_legal_validation',
      'approved',
      'superseded',
      'cancelled'
    )),
  CONSTRAINT payroll_stat_pkg_dates_chk
    CHECK (effective_to IS NULL OR effective_to >= effective_from),
  CONSTRAINT payroll_stat_pkg_legal_fixture_chk
    CHECK (NOT (legal_claim AND is_architecture_fixture)),
  CONSTRAINT payroll_stat_pkg_legal_requires_approved_chk
    CHECK (legal_claim = false OR approval_status = 'approved')
);

CREATE UNIQUE INDEX IF NOT EXISTS payroll_stat_pkg_version_uniq
  ON payroll_statutory_packages (
    country_code, (COALESCE(company_code, '')), package_code, version_number
  );

CREATE INDEX IF NOT EXISTS idx_payroll_stat_pkg_lookup
  ON payroll_statutory_packages (country_code, company_code, package_code, approval_status, effective_from DESC);

-- Versioned rule families inside a package
CREATE TABLE IF NOT EXISTS payroll_statutory_rule_versions (
  rule_version_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  package_id uuid NOT NULL REFERENCES payroll_statutory_packages(package_id),
  country_code text NOT NULL DEFAULT 'KW',
  company_code text,
  rule_family text NOT NULL,
  output_class text NOT NULL,
  approval_status text NOT NULL DEFAULT 'draft',
  legal_claim boolean NOT NULL DEFAULT false,
  is_architecture_fixture boolean NOT NULL DEFAULT false,
  version_label text NOT NULL,
  effective_from date NOT NULL,
  effective_to date,
  -- Structured rate payload. Legal tables must leave numeric rates null until counsel signs.
  -- Architecture fixtures may include placeholder numbers with legal_claim=false.
  rate_payload jsonb NOT NULL DEFAULT '{}'::jsonb,
  multiplier numeric(12,6),
  fraction_payload jsonb NOT NULL DEFAULT '{}'::jsonb,
  p3_rate_table_id uuid, -- optional bridge to payroll_rate_tables
  counsel_signed boolean NOT NULL DEFAULT false,
  counsel_note text,
  content_fingerprint text NOT NULL,
  provenance jsonb NOT NULL DEFAULT '{}'::jsonb,
  decision_note text,
  created_by_phone text,
  validated_by_phone text,
  validated_at timestamptz,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT payroll_stat_rule_family_chk
    CHECK (rule_family IN (
      'pifss',
      'ot_ordinary',
      'rest_day_work',
      'public_holiday_work',
      'sick_leave_fractions',
      'eos_indemnity'
    )),
  CONSTRAINT payroll_stat_rule_output_chk
    CHECK (output_class IN (
      'A_employee_net',
      'B_employer_liability',
      'C_settlement',
      'D_remittance_reporting',
      'mixed_pifss_pack' -- PIFSS package expands to A+B+D child specs
    )),
  CONSTRAINT payroll_stat_rule_status_chk
    CHECK (approval_status IN (
      'draft',
      'awaiting_legal_validation',
      'approved',
      'superseded',
      'cancelled'
    )),
  CONSTRAINT payroll_stat_rule_legal_fixture_chk
    CHECK (NOT (legal_claim AND is_architecture_fixture)),
  CONSTRAINT payroll_stat_rule_legal_approved_chk
    CHECK (legal_claim = false OR (approval_status = 'approved' AND counsel_signed = true)),
  CONSTRAINT payroll_stat_rule_dates_chk
    CHECK (effective_to IS NULL OR effective_to >= effective_from)
);

CREATE INDEX IF NOT EXISTS idx_payroll_stat_rule_lookup
  ON payroll_statutory_rule_versions (
    country_code, company_code, rule_family, approval_status, effective_from DESC
  );

-- PIFSS contribution sides kept distinct (EE deduction / ER liability / remittance)
CREATE TABLE IF NOT EXISTS payroll_pifss_contribution_specs (
  spec_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  rule_version_id uuid NOT NULL REFERENCES payroll_statutory_rule_versions(rule_version_id),
  country_code text NOT NULL DEFAULT 'KW',
  employee_category text NOT NULL,
  contribution_side text NOT NULL,
  output_class text NOT NULL,
  fund_code text NOT NULL DEFAULT 'unspecified',
  base_definition text NOT NULL DEFAULT 'contributory_wage',
  cap_definition text,
  -- Rate fields intentionally nullable until counsel-signed legal tables exist.
  rate_percent numeric(8,4),
  rate_is_architecture_fixture boolean NOT NULL DEFAULT false,
  rate_awaiting_legal_validation boolean NOT NULL DEFAULT false,
  eligibility_notes text,
  remittance_notes text,
  metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT payroll_pifss_cat_chk
    CHECK (employee_category IN ('kuwaiti_national', 'gcc_national', 'expatriate', 'all')),
  CONSTRAINT payroll_pifss_side_chk
    CHECK (contribution_side IN (
      'employee_deduction',
      'employer_contribution',
      'remittance_obligation'
    )),
  CONSTRAINT payroll_pifss_out_chk
    CHECK (output_class IN (
      'A_employee_net',
      'B_employer_liability',
      'D_remittance_reporting'
    )),
  CONSTRAINT payroll_pifss_fixture_rate_chk
    CHECK (
      rate_percent IS NULL
      OR rate_is_architecture_fixture = true
      OR rate_awaiting_legal_validation = true
      OR COALESCE(source_classification, '') = 'OFFICIAL_CLEAR'
    ),
  CONSTRAINT payroll_pifss_spec_uniq
    UNIQUE (rule_version_id, employee_category, contribution_side, fund_code)
);

-- EOS settlement snapshots — never monthly G2N lines; never auto-pay
CREATE TABLE IF NOT EXISTS payroll_eos_settlement_snapshots (
  settlement_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  company_code text NOT NULL,
  country_code text NOT NULL DEFAULT 'KW',
  employee_key text NOT NULL,
  service_start date NOT NULL,
  service_end date NOT NULL,
  termination_reason text,
  termination_context jsonb NOT NULL DEFAULT '{}'::jsonb,
  compensation_basis jsonb NOT NULL DEFAULT '{}'::jsonb,
  rule_version_id uuid REFERENCES payroll_statutory_rule_versions(rule_version_id),
  package_id uuid REFERENCES payroll_statutory_packages(package_id),
  approval_status text NOT NULL DEFAULT 'draft',
  legal_claim boolean NOT NULL DEFAULT false,
  is_architecture_fixture boolean NOT NULL DEFAULT false,
  money_authority text NOT NULL DEFAULT 'preview_non_authoritative',
  payment_processing text NOT NULL DEFAULT 'disabled',
  posts_payment boolean NOT NULL DEFAULT false,
  auto_payable boolean NOT NULL DEFAULT false,
  provisional_amount numeric(14,3),
  currency text NOT NULL DEFAULT 'KWD',
  input_fingerprint text NOT NULL,
  content_fingerprint text NOT NULL,
  result_payload jsonb NOT NULL DEFAULT '{}'::jsonb,
  blockers jsonb NOT NULL DEFAULT '[]'::jsonb,
  warnings jsonb NOT NULL DEFAULT '[]'::jsonb,
  provenance jsonb NOT NULL DEFAULT '{}'::jsonb,
  decision_note text,
  created_by_phone text,
  reviewed_by_phone text,
  reviewed_at timestamptz,
  created_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT payroll_eos_settle_status_chk
    CHECK (approval_status IN (
      'draft',
      'in_review',
      'awaiting_legal_validation',
      'architecture_qualified',
      'approved',
      'superseded',
      'cancelled'
    )),
  CONSTRAINT payroll_eos_settle_money_chk
    CHECK (money_authority = 'preview_non_authoritative'),
  CONSTRAINT payroll_eos_settle_pay_chk
    CHECK (payment_processing = 'disabled'),
  CONSTRAINT payroll_eos_settle_no_posts_chk
    CHECK (posts_payment = false),
  CONSTRAINT payroll_eos_settle_no_auto_chk
    CHECK (auto_payable = false),
  CONSTRAINT payroll_eos_settle_legal_fixture_chk
    CHECK (NOT (legal_claim AND is_architecture_fixture)),
  CONSTRAINT payroll_eos_settle_dates_chk
    CHECK (service_end >= service_start)
);

CREATE INDEX IF NOT EXISTS idx_payroll_eos_settle_emp
  ON payroll_eos_settlement_snapshots (company_code, employee_key, service_end DESC);

-- Classified statutory evaluation outputs (A/B/C/D) for a period preview
CREATE TABLE IF NOT EXISTS payroll_statutory_eval_runs (
  eval_run_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  company_code text NOT NULL,
  country_code text NOT NULL DEFAULT 'KW',
  period_start date NOT NULL,
  period_end date NOT NULL,
  input_snapshot_id uuid,
  package_id uuid,
  content_fingerprint text NOT NULL,
  status text NOT NULL DEFAULT 'evaluated',
  money_authority text NOT NULL DEFAULT 'preview_non_authoritative',
  legal_claim boolean NOT NULL DEFAULT false,
  payment_processing text NOT NULL DEFAULT 'disabled',
  result_payload jsonb NOT NULL DEFAULT '{}'::jsonb,
  blockers jsonb NOT NULL DEFAULT '[]'::jsonb,
  decision_note text,
  created_by_phone text,
  created_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT payroll_stat_eval_status_chk
    CHECK (status IN ('evaluated', 'blocked', 'superseded')),
  CONSTRAINT payroll_stat_eval_money_chk
    CHECK (money_authority = 'preview_non_authoritative'),
  CONSTRAINT payroll_stat_eval_pay_chk
    CHECK (payment_processing = 'disabled'),
  CONSTRAINT payroll_stat_eval_legal_chk
    CHECK (legal_claim = false)
);

CREATE TABLE IF NOT EXISTS payroll_statutory_eval_lines (
  line_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  eval_run_id uuid NOT NULL REFERENCES payroll_statutory_eval_runs(eval_run_id),
  company_code text NOT NULL,
  employee_key text,
  rule_family text NOT NULL,
  output_class text NOT NULL,
  component_code text,
  amount numeric(14,3),
  amount_is_architecture_fixture boolean NOT NULL DEFAULT true,
  legal_claim boolean NOT NULL DEFAULT false,
  rule_version_id uuid,
  calc_notes jsonb NOT NULL DEFAULT '{}'::jsonb,
  provenance jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT payroll_stat_eval_line_class_chk
    CHECK (output_class IN (
      'A_employee_net',
      'B_employer_liability',
      'C_settlement',
      'D_remittance_reporting'
    )),
  CONSTRAINT payroll_stat_eval_line_legal_chk
    CHECK (legal_claim = false)
);

CREATE TABLE IF NOT EXISTS payroll_statutory_events (
  event_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  company_code text,
  country_code text NOT NULL DEFAULT 'KW',
  entity_kind text NOT NULL,
  entity_id uuid,
  event_type text NOT NULL,
  payload jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_by_phone text,
  created_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT payroll_stat_event_kind_chk
    CHECK (entity_kind IN (
      'package',
      'rule_version',
      'pifss_spec',
      'eos_settlement',
      'eval_run'
    ))
);

CREATE INDEX IF NOT EXISTS idx_payroll_stat_events
  ON payroll_statutory_events (country_code, company_code, created_at DESC);

-- Additive P4B-prep: allow candidate rates awaiting legal validation (never legal_claim).
ALTER TABLE payroll_pifss_contribution_specs
  ADD COLUMN IF NOT EXISTS rate_awaiting_legal_validation boolean NOT NULL DEFAULT false;

ALTER TABLE payroll_pifss_contribution_specs
  ADD COLUMN IF NOT EXISTS fund_code text NOT NULL DEFAULT 'unspecified';

ALTER TABLE payroll_pifss_contribution_specs
  ADD COLUMN IF NOT EXISTS source_classification text;

-- Recreate rate check: fixture, awaiting-legal candidate, or OFFICIAL_CLEAR public baseline.
ALTER TABLE payroll_pifss_contribution_specs DROP CONSTRAINT IF EXISTS payroll_pifss_fixture_rate_chk;

UPDATE payroll_pifss_contribution_specs
SET source_classification = 'OFFICIAL_CLEAR'
WHERE rate_percent IS NOT NULL
  AND COALESCE(source_classification, '') = ''
  AND (
    COALESCE(metadata->>'authority_kind', '') = 'wathefni_public_baseline'
    OR COALESCE(metadata->>'phase', '') = 'p4b'
  );

UPDATE payroll_pifss_contribution_specs
SET rate_awaiting_legal_validation = true
WHERE rate_percent IS NOT NULL
  AND rate_is_architecture_fixture = false
  AND rate_awaiting_legal_validation = false
  AND COALESCE(source_classification, '') NOT IN ('OFFICIAL_CLEAR');

ALTER TABLE payroll_pifss_contribution_specs
  ADD CONSTRAINT payroll_pifss_fixture_rate_chk
  CHECK (
    rate_percent IS NULL
    OR rate_is_architecture_fixture = true
    OR rate_awaiting_legal_validation = true
    OR COALESCE(source_classification, '') = 'OFFICIAL_CLEAR'
  );

-- Migrate uniqueness to include fund_code (multiple PIFSS funds share category+side).
ALTER TABLE payroll_pifss_contribution_specs
  DROP CONSTRAINT IF EXISTS payroll_pifss_contribution_specs_rule_version_id_employee_category_contribution_side_key;
ALTER TABLE payroll_pifss_contribution_specs
  DROP CONSTRAINT IF EXISTS payroll_pifss_contribution_sp_rule_version_id_employee_cate_key;
ALTER TABLE payroll_pifss_contribution_specs
  DROP CONSTRAINT IF EXISTS payroll_pifss_spec_uniq;
ALTER TABLE payroll_pifss_contribution_specs
  ADD CONSTRAINT payroll_pifss_spec_uniq
  UNIQUE (rule_version_id, employee_category, contribution_side, fund_code);

-- Bridge: extend P3 rate table statuses documentation via comment only (no DDL change required).
-- P4A never auto-promotes counsel_required P3 rows to legally approved.
