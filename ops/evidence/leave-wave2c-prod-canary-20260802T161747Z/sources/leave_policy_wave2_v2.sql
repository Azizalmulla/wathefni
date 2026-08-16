-- Leave Wave 2 / 2B — policy & balance correctness pack (local/staging only)
-- Applied via leave_policy_wave2.ensure_leave_policy_wave2_schema + seed helpers.
-- enforced=false / legal_reviewed=false always in this wave.
-- Wave 2B adds holiday year versions + audit for yearly review fail-closed.

ALTER TABLE leave_balances
  ADD COLUMN IF NOT EXISTS reserved numeric(6,2) NOT NULL DEFAULT 0;

ALTER TABLE public_holidays
  ADD COLUMN IF NOT EXISTS source_provenance text,
  ADD COLUMN IF NOT EXISTS effective_from date,
  ADD COLUMN IF NOT EXISTS effective_to date,
  ADD COLUMN IF NOT EXISTS review_status text NOT NULL DEFAULT 'unreviewed',
  ADD COLUMN IF NOT EXISTS calendar_code text;

CREATE TABLE IF NOT EXISTS leave_policy_packs (
  pack_code text NOT NULL,
  version text NOT NULL,
  jurisdiction_code text NOT NULL,
  worker_category text NOT NULL,
  timezone text NOT NULL DEFAULT 'Asia/Kuwait',
  weekend_days text[] NOT NULL DEFAULT ARRAY['fri','sat'],
  exclude_public_holidays boolean NOT NULL DEFAULT true,
  carryover_enabled boolean NOT NULL DEFAULT false,
  carryover_rules jsonb NOT NULL DEFAULT '{}'::jsonb,
  legal_reviewed boolean NOT NULL DEFAULT false,
  enforced boolean NOT NULL DEFAULT false,
  source_matrix jsonb NOT NULL DEFAULT '[]'::jsonb,
  policies jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (pack_code, version)
);

CREATE TABLE IF NOT EXISTS leave_company_policy_bindings (
  company_code text PRIMARY KEY,
  pack_code text NOT NULL,
  pack_version text NOT NULL,
  jurisdiction_code text NOT NULL DEFAULT 'KW',
  worker_category text NOT NULL DEFAULT 'private_sector',
  updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS leave_holiday_calendars (
  calendar_code text PRIMARY KEY,
  jurisdiction_code text NOT NULL,
  display_name text NOT NULL,
  timezone text NOT NULL DEFAULT 'Asia/Kuwait',
  yearly_review_status text NOT NULL DEFAULT 'pending_yearly_review',
  last_reviewed_year int,
  source_notes text,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS leave_holiday_year_versions (
  calendar_code text NOT NULL,
  year int NOT NULL,
  version int NOT NULL DEFAULT 1,
  status text NOT NULL DEFAULT 'draft',
  source_announcement_ref text,
  source_url text,
  source_sha256 text,
  approved_by text,
  approved_at timestamptz,
  notes text,
  created_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (calendar_code, year, version),
  CONSTRAINT leave_holiday_year_status_chk
    CHECK (status IN ('draft','pending_review','approved','superseded','rejected'))
);

CREATE TABLE IF NOT EXISTS leave_holiday_audit (
  audit_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  calendar_code text,
  year int,
  holiday_date date,
  action text NOT NULL,
  actor text,
  payload jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_leave_ledger_reservation_idem
  ON leave_ledger (leave_id, entry_kind)
  WHERE leave_id IS NOT NULL AND entry_kind IN ('reservation','reservation_release');

CREATE TABLE IF NOT EXISTS leave_balance_reconcile_runs (
  run_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  company_code text NOT NULL,
  employee_key text,
  leave_type text,
  period_year int,
  ok boolean NOT NULL,
  drift jsonb NOT NULL DEFAULT '[]'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now()
);
