-- Payroll Payslip Official PDF (P0.1) — additive pointers only.
-- PDF bytes live in private workspace storage; these columns bind a versioned payslip_id
-- to immutable generated artifacts (never regenerate under a released fingerprint).

ALTER TABLE payroll_payslip_documents
  ADD COLUMN IF NOT EXISTS official_pdf_en_path text;

ALTER TABLE payroll_payslip_documents
  ADD COLUMN IF NOT EXISTS official_pdf_ar_path text;

ALTER TABLE payroll_payslip_documents
  ADD COLUMN IF NOT EXISTS official_pdf_en_sha256 text;

ALTER TABLE payroll_payslip_documents
  ADD COLUMN IF NOT EXISTS official_pdf_ar_sha256 text;

ALTER TABLE payroll_payslip_documents
  ADD COLUMN IF NOT EXISTS official_pdf_generated_at timestamptz;

ALTER TABLE payroll_payslip_documents
  ADD COLUMN IF NOT EXISTS official_pdf_content_fingerprint text;
