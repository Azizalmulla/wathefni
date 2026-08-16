-- Payroll Payslip Wave 3 — employee release gate (additive)
-- Document lifecycle stays: active | replaced | revoked
-- Employee visibility is orthogonal: not_released | released
-- Employee App may only see status=active AND employee_visibility=released.
-- Period open|locked|closed never implies employee visibility.

ALTER TABLE payroll_payslip_documents
  ADD COLUMN IF NOT EXISTS employee_visibility text NOT NULL DEFAULT 'not_released';

ALTER TABLE payroll_payslip_documents
  ADD COLUMN IF NOT EXISTS employee_released_at timestamptz;

ALTER TABLE payroll_payslip_documents
  ADD COLUMN IF NOT EXISTS employee_released_by_phone text;

ALTER TABLE payroll_payslip_documents
  ADD COLUMN IF NOT EXISTS employee_release_note text;

DO $$
BEGIN
  ALTER TABLE payroll_payslip_documents
    ADD CONSTRAINT payroll_payslip_employee_visibility_chk
    CHECK (employee_visibility IN ('not_released', 'released'));
EXCEPTION
  WHEN duplicate_object THEN NULL;
END $$;

CREATE INDEX IF NOT EXISTS idx_payroll_payslip_employee_released
  ON payroll_payslip_documents (company_code, employee_key, period_start DESC, created_at DESC)
  WHERE employee_visibility = 'released' AND status = 'active';
