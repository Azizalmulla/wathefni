-- Wave 1 — Preboarding authority schema (version 1.0.0)
-- Dark until WATHEFNI_PREBOARDING=on + company allowlist + company enable.
-- HARD attach: canonical employee_key / employment (pending_start provisional OK).
-- ready is derived from required items — never a cosmetic manual flag.

CREATE TABLE IF NOT EXISTS preboarding_settings (
  company_code text PRIMARY KEY,
  enabled boolean NOT NULL DEFAULT false,
  auto_create_on_offer_accept boolean NOT NULL DEFAULT true,
  required_for_ready_mark boolean NOT NULL DEFAULT true,
  handoff_onboarding_enabled boolean NOT NULL DEFAULT false,
  updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS preboarding_templates (
  template_id text NOT NULL,
  company_code text NOT NULL,
  version text NOT NULL DEFAULT '1.0.0',
  title_en text NOT NULL,
  title_ar text,
  active boolean NOT NULL DEFAULT true,
  metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (company_code, template_id)
);

CREATE TABLE IF NOT EXISTS preboarding_template_items (
  company_code text NOT NULL,
  template_id text NOT NULL,
  item_key text NOT NULL,
  title_en text NOT NULL,
  title_ar text,
  category text NOT NULL,
  item_type text NOT NULL DEFAULT 'task',
  owner_role text NOT NULL,
  required boolean NOT NULL DEFAULT false,
  due_offset_days integer,
  depends_on jsonb NOT NULL DEFAULT '[]'::jsonb,
  document_type text,
  sort_order integer NOT NULL DEFAULT 0,
  metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
  PRIMARY KEY (company_code, template_id, item_key),
  CONSTRAINT preboarding_template_items_owner_chk
    CHECK (owner_role IN ('employee', 'hr', 'manager', 'it', 'other', 'system')),
  CONSTRAINT preboarding_template_items_type_chk
    CHECK (item_type IN ('document', 'task', 'ack', 'form', 'comms'))
);

CREATE TABLE IF NOT EXISTS preboard_assignments (
  assignment_id uuid PRIMARY KEY,
  company_code text NOT NULL,
  employee_key text NOT NULL,
  employment_id text,
  status text NOT NULL,
  joining_date date,
  template_id text NOT NULL DEFAULT 'default_kuwait_preboard',
  template_version text NOT NULL DEFAULT '1.0.0',
  application_id text,
  offer_id text,
  manager_user_id text,
  blocker_reasons jsonb NOT NULL DEFAULT '[]'::jsonb,
  readiness jsonb NOT NULL DEFAULT '{}'::jsonb,
  cancel_reason text,
  created_by_user_id text,
  created_by_phone text,
  row_version integer NOT NULL DEFAULT 1,
  idempotency_key text,
  metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT preboard_assignments_status_chk
    CHECK (status IN (
      'not_started', 'in_progress', 'ready', 'blocked', 'converted', 'cancelled'
    )),
  CONSTRAINT preboard_assignments_cancel_chk
    CHECK (
      cancel_reason IS NULL
      OR cancel_reason IN ('cancelled', 'no_show', 'withdrawn', 'other')
    )
);

CREATE UNIQUE INDEX IF NOT EXISTS preboard_assignments_open_uniq
  ON preboard_assignments (company_code, employee_key)
  WHERE status NOT IN ('converted', 'cancelled');

CREATE UNIQUE INDEX IF NOT EXISTS preboard_assignments_idem_uniq
  ON preboard_assignments (company_code, idempotency_key)
  WHERE idempotency_key IS NOT NULL AND idempotency_key <> '';

CREATE INDEX IF NOT EXISTS preboard_assignments_company_status_idx
  ON preboard_assignments (company_code, status, updated_at DESC);

CREATE INDEX IF NOT EXISTS preboard_assignments_joining_idx
  ON preboard_assignments (company_code, joining_date);

CREATE TABLE IF NOT EXISTS preboard_items (
  item_id uuid PRIMARY KEY,
  assignment_id uuid NOT NULL REFERENCES preboard_assignments(assignment_id),
  company_code text NOT NULL,
  employee_key text NOT NULL,
  item_key text NOT NULL,
  title_en text NOT NULL,
  title_ar text,
  category text NOT NULL,
  item_type text NOT NULL DEFAULT 'task',
  owner_role text NOT NULL,
  required boolean NOT NULL DEFAULT false,
  depends_on jsonb NOT NULL DEFAULT '[]'::jsonb,
  due_at timestamptz,
  status text NOT NULL DEFAULT 'pending',
  blocker_reason text,
  evidence_document_id text,
  document_type text,
  waived_by_user_id text,
  waive_reason text,
  completed_at timestamptz,
  row_version integer NOT NULL DEFAULT 1,
  metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT preboard_items_status_chk
    CHECK (status IN ('pending', 'in_progress', 'done', 'waived', 'blocked')),
  CONSTRAINT preboard_items_owner_chk
    CHECK (owner_role IN ('employee', 'hr', 'manager', 'it', 'other', 'system')),
  UNIQUE (assignment_id, item_key)
);

CREATE INDEX IF NOT EXISTS preboard_items_assignment_idx
  ON preboard_items (company_code, assignment_id, status);

CREATE INDEX IF NOT EXISTS preboard_items_owner_idx
  ON preboard_items (company_code, owner_role, status);

CREATE TABLE IF NOT EXISTS preboard_events (
  event_id uuid PRIMARY KEY,
  company_code text NOT NULL,
  assignment_id uuid,
  item_id uuid,
  event_type text NOT NULL,
  actor_user_id text,
  actor_phone text,
  payload jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS preboard_events_company_idx
  ON preboard_events (company_code, created_at DESC);

CREATE INDEX IF NOT EXISTS preboard_events_assignment_idx
  ON preboard_events (assignment_id, created_at DESC);
