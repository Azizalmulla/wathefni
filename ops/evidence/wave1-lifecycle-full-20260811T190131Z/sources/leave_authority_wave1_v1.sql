-- Leave Authority Wave 1 schema pack (version 1.0.0)
-- Applied via leave_authority_wave1.ensure_leave_authority_wave1_schema /
-- ops/migrate-leave-authority-wave1.sh (local/staging only).
-- Never sets balances_enforced or legal_reviewed to true.

ALTER TABLE leave_requests
  ADD COLUMN IF NOT EXISTS row_version integer NOT NULL DEFAULT 1;

CREATE TABLE IF NOT EXISTS leave_authority_settings (
  company_code text PRIMARY KEY,
  block_terminated boolean NOT NULL DEFAULT true,
  block_suspended boolean NOT NULL DEFAULT true,
  block_future_start boolean NOT NULL DEFAULT true,
  block_notice_period boolean NOT NULL DEFAULT true,
  stale_pending_action text NOT NULL DEFAULT 'expire',
  balances_enforced boolean NOT NULL DEFAULT false,
  legal_reviewed boolean NOT NULL DEFAULT false,
  updated_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT leave_authority_stale_action_chk
    CHECK (stale_pending_action IN ('expire', 'needs_review'))
);

CREATE TABLE IF NOT EXISTS leave_type_catalogue (
  leave_type text PRIMARY KEY,
  display_en text NOT NULL,
  display_ar text,
  maps_from text[] NOT NULL DEFAULT '{}'::text[],
  ledger_eligible boolean NOT NULL DEFAULT false,
  active boolean NOT NULL DEFAULT true,
  created_at timestamptz NOT NULL DEFAULT now()
);

INSERT INTO leave_type_catalogue (leave_type, display_en, display_ar, maps_from, ledger_eligible)
VALUES
  ('annual', 'Annual leave', 'إجازة سنوية',
   ARRAY['vacation','holiday','time_off','timeoff','personal','pto','annual_leave'], true),
  ('sick', 'Sick leave', 'إجازة مرضية',
   ARRAY['medical','ill','sick_leave'], true),
  ('unpaid', 'Unpaid leave', 'إجازة بدون راتب',
   ARRAY['unpaid_leave'], false),
  ('other', 'Other leave', 'إجازة أخرى',
   ARRAY[]::text[], false)
ON CONFLICT (leave_type) DO NOTHING;
