-- Payroll Authority P4B — Wathefni-owned Kuwait public statutory baseline (v1.0.0)
-- Additive on P4A. Activates OFFICIAL_CLEAR public rules only.
-- Does NOT unlock Mode A / native PDF / payment processing.
-- Ambiguous/special-regime cases remain review-gated.

ALTER TABLE payroll_statutory_rule_versions
  ADD COLUMN IF NOT EXISTS source_classification text;

ALTER TABLE payroll_statutory_rule_versions
  ADD COLUMN IF NOT EXISTS authority_kind text NOT NULL DEFAULT 'unspecified';

ALTER TABLE payroll_statutory_rule_versions
  ADD COLUMN IF NOT EXISTS applicability jsonb NOT NULL DEFAULT '{}'::jsonb;

ALTER TABLE payroll_statutory_rule_versions
  ADD COLUMN IF NOT EXISTS official_source_ref text;

ALTER TABLE payroll_statutory_rule_versions
  ADD COLUMN IF NOT EXISTS policy_version text;

ALTER TABLE payroll_statutory_packages
  ADD COLUMN IF NOT EXISTS authority_kind text NOT NULL DEFAULT 'unspecified';

ALTER TABLE payroll_statutory_packages
  ADD COLUMN IF NOT EXISTS policy_version text;

ALTER TABLE payroll_pifss_contribution_specs
  ADD COLUMN IF NOT EXISTS source_classification text;

ALTER TABLE payroll_pifss_contribution_specs
  ADD COLUMN IF NOT EXISTS official_source_ref text;

-- Public baseline rates may be legal_claim when authority_kind=wathefni_public_baseline
-- (rate_awaiting_legal_validation OR architecture fixture OR public baseline attested).
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

DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint WHERE conname = 'payroll_stat_rule_authority_chk'
  ) THEN
    ALTER TABLE payroll_statutory_rule_versions
      ADD CONSTRAINT payroll_stat_rule_authority_chk
      CHECK (authority_kind IN (
        'unspecified',
        'architecture_fixture',
        'awaiting_review',
        'wathefni_public_baseline',
        'company_exception'
      ));
  END IF;
END $$;

DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1 FROM pg_constraint WHERE conname = 'payroll_stat_rule_source_class_chk'
  ) THEN
    ALTER TABLE payroll_statutory_rule_versions
      ADD CONSTRAINT payroll_stat_rule_source_class_chk
      CHECK (
        source_classification IS NULL
        OR source_classification IN (
          'OFFICIAL_CLEAR',
          'OFFICIAL_NEEDS_INTERPRETATION',
          'SECONDARY_ONLY',
          'UNSUPPORTED'
        )
      );
  END IF;
END $$;

-- Public baseline may set legal_claim with Wathefni statutory attestation (counsel_signed reused as authority attestation).
-- company_exception never allowed with legal_claim on country mandatory families (enforced in app).

CREATE INDEX IF NOT EXISTS idx_payroll_stat_rule_baseline
  ON payroll_statutory_rule_versions (
    country_code, rule_family, authority_kind, approval_status, effective_from DESC
  );

-- Ensure PIFSS uniqueness includes fund_code (Postgres may truncate auto names).
ALTER TABLE payroll_pifss_contribution_specs
  DROP CONSTRAINT IF EXISTS payroll_pifss_contribution_specs_rule_version_id_employee_category_contribution_side_key;
ALTER TABLE payroll_pifss_contribution_specs
  DROP CONSTRAINT IF EXISTS payroll_pifss_contribution_sp_rule_version_id_employee_cate_key;
ALTER TABLE payroll_pifss_contribution_specs
  DROP CONSTRAINT IF EXISTS payroll_pifss_spec_uniq;
ALTER TABLE payroll_pifss_contribution_specs
  ADD CONSTRAINT payroll_pifss_spec_uniq
  UNIQUE (rule_version_id, employee_category, contribution_side, fund_code);
