-- Shifts Wave 1 — authority, overnight, soft-cancel quarantine foundation
CREATE TABLE IF NOT EXISTS shift_authority_settings (
  company_code text PRIMARY KEY,
  allow_overnight boolean NOT NULL DEFAULT true,
  rest_weekdays integer[] NOT NULL DEFAULT ARRAY[4],
  leave_conflict_mode text NOT NULL DEFAULT 'require_ack',
  block_terminated boolean NOT NULL DEFAULT true,
  block_suspended boolean NOT NULL DEFAULT true,
  block_future_start boolean NOT NULL DEFAULT true,
  block_notice_period boolean NOT NULL DEFAULT true,
  synthetic_only boolean NOT NULL DEFAULT false,
  updated_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT shift_leave_conflict_mode_chk
    CHECK (leave_conflict_mode IN ('block','require_ack','cancel_shift'))
);

CREATE TABLE IF NOT EXISTS shift_orphan_quarantine (
  quarantine_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  company_code text NOT NULL,
  shift_id uuid NOT NULL,
  employee_key text,
  snapshot jsonb NOT NULL DEFAULT '{}'::jsonb,
  reason text NOT NULL DEFAULT 'orphan_employee_key',
  status text NOT NULL DEFAULT 'quarantined',
  quarantined_by_phone text,
  restored_by_phone text,
  quarantined_at timestamptz NOT NULL DEFAULT now(),
  restored_at timestamptz,
  CONSTRAINT shift_orphan_status_chk CHECK (status IN ('quarantined','restored','purged'))
);
CREATE INDEX IF NOT EXISTS idx_shift_orphan_company_status
  ON shift_orphan_quarantine(company_code, status);

ALTER TABLE shift_assignments ADD COLUMN IF NOT EXISTS ends_next_day boolean NOT NULL DEFAULT false;
ALTER TABLE shift_assignments ADD COLUMN IF NOT EXISTS break_minutes integer;
ALTER TABLE shift_assignments ADD COLUMN IF NOT EXISTS site_key text;
ALTER TABLE shift_assignments ADD COLUMN IF NOT EXISTS branch_key text;
ALTER TABLE shift_assignments ADD COLUMN IF NOT EXISTS team_key text;
ALTER TABLE shift_assignments ADD COLUMN IF NOT EXISTS position_key text;
ALTER TABLE shift_assignments ADD COLUMN IF NOT EXISTS idempotency_key text;
ALTER TABLE shift_assignments ADD COLUMN IF NOT EXISTS row_version integer NOT NULL DEFAULT 1;

CREATE UNIQUE INDEX IF NOT EXISTS idx_shift_assignments_idempotency
  ON shift_assignments(company_code, idempotency_key)
  WHERE idempotency_key IS NOT NULL AND idempotency_key <> '';

INSERT INTO shift_authority_settings (company_code)
VALUES ('WATHEFNI')
ON CONFLICT (company_code) DO NOTHING;
