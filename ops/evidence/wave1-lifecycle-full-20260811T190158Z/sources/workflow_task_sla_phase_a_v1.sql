-- Phase A slice 2 — unified task ontology + SLA/reminder policy (version 1.0.0)
-- Extends hr_tasks (no second inbox SoT). Runtime dark until company-scoped flags.
-- Does not bind Requisitions/Preboarding product subjects in UI.

ALTER TABLE hr_tasks
  ADD COLUMN IF NOT EXISTS subject_type text;

ALTER TABLE hr_tasks
  ADD COLUMN IF NOT EXISTS subject_id text;

ALTER TABLE hr_tasks
  ADD COLUMN IF NOT EXISTS due_at timestamptz;

ALTER TABLE hr_tasks
  ADD COLUMN IF NOT EXISTS sla_clock_id uuid;

ALTER TABLE hr_tasks
  ADD COLUMN IF NOT EXISTS row_version integer NOT NULL DEFAULT 1;

CREATE INDEX IF NOT EXISTS idx_hr_tasks_company_subject
  ON hr_tasks (company_code, subject_type, subject_id);

CREATE INDEX IF NOT EXISTS idx_hr_tasks_company_due
  ON hr_tasks (company_code, due_at)
  WHERE status = 'open' AND due_at IS NOT NULL;

CREATE TABLE IF NOT EXISTS workflow_task_settings (
  company_code text PRIMARY KEY,
  enabled boolean NOT NULL DEFAULT false,
  updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS workflow_task_type_catalogue (
  task_type text PRIMARY KEY,
  subject_type text,
  display_en text NOT NULL,
  display_ar text,
  inbox_visible boolean NOT NULL DEFAULT true,
  active boolean NOT NULL DEFAULT true,
  created_at timestamptz NOT NULL DEFAULT now()
);

INSERT INTO workflow_task_type_catalogue
  (task_type, subject_type, display_en, display_ar, inbox_visible, active)
VALUES
  ('requisition_approval', 'requisition', 'Requisition approval', 'اعتماد طلب توظيف', true, true),
  ('preboard_item', 'preboard_item', 'Preboarding item', 'بند تهيئة ما قبل المباشرة', true, true),
  ('preboard_readiness', 'preboard_assignment', 'Preboarding readiness', 'جاهزية ما قبل المباشرة', true, true),
  ('probation_milestone', 'probation_milestone', 'Probation milestone', 'مرحلة فترة التجربة', true, true),
  ('probation_decision', 'probation_case', 'Probation decision', 'قرار فترة التجربة', true, true),
  ('sla_breach', NULL, 'SLA breach', 'تجاوز مهلة الخدمة', true, true)
ON CONFLICT (task_type) DO NOTHING;

CREATE TABLE IF NOT EXISTS workflow_sla_settings (
  company_code text PRIMARY KEY,
  enabled boolean NOT NULL DEFAULT false,
  reminders_enabled boolean NOT NULL DEFAULT false,
  updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS workflow_sla_policies (
  policy_id uuid PRIMARY KEY,
  company_code text NOT NULL,
  subject_type text NOT NULL,
  name text NOT NULL,
  priority text NOT NULL DEFAULT 'normal',
  due_in_seconds integer NOT NULL,
  remind_before_seconds integer,
  escalate_to_role text,
  escalate_to_user_id text,
  escalate_task_type text NOT NULL DEFAULT 'sla_breach',
  active boolean NOT NULL DEFAULT true,
  version integer NOT NULL DEFAULT 1,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT workflow_sla_policies_due_chk CHECK (due_in_seconds > 0),
  CONSTRAINT workflow_sla_policies_priority_chk
    CHECK (priority IN ('low', 'normal', 'high', 'urgent'))
);

CREATE UNIQUE INDEX IF NOT EXISTS workflow_sla_policies_active_uniq
  ON workflow_sla_policies (company_code, subject_type, priority)
  WHERE active = true;

CREATE TABLE IF NOT EXISTS workflow_sla_clocks (
  clock_id uuid PRIMARY KEY,
  company_code text NOT NULL,
  policy_id uuid NOT NULL REFERENCES workflow_sla_policies(policy_id),
  subject_type text NOT NULL,
  subject_id text NOT NULL,
  status text NOT NULL,
  priority text NOT NULL DEFAULT 'normal',
  due_at timestamptz NOT NULL,
  remind_at timestamptz,
  reminded_at timestamptz,
  breached_at timestamptz,
  satisfied_at timestamptz,
  cancelled_at timestamptz,
  breach_task_id uuid,
  idempotency_key text,
  row_version integer NOT NULL DEFAULT 1,
  metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT workflow_sla_clocks_status_chk
    CHECK (status IN ('running', 'breached', 'satisfied', 'cancelled'))
);

CREATE UNIQUE INDEX IF NOT EXISTS workflow_sla_clocks_idem_uniq
  ON workflow_sla_clocks (company_code, idempotency_key)
  WHERE idempotency_key IS NOT NULL AND idempotency_key <> '';

CREATE UNIQUE INDEX IF NOT EXISTS workflow_sla_clocks_open_subject_uniq
  ON workflow_sla_clocks (company_code, subject_type, subject_id)
  WHERE status = 'running';

CREATE INDEX IF NOT EXISTS workflow_sla_clocks_due_idx
  ON workflow_sla_clocks (company_code, status, due_at);

CREATE TABLE IF NOT EXISTS workflow_task_sla_events (
  event_id uuid PRIMARY KEY,
  company_code text NOT NULL,
  task_id uuid,
  clock_id uuid,
  event_type text NOT NULL,
  actor_user_id text,
  actor_phone text,
  payload jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS workflow_task_sla_events_company_idx
  ON workflow_task_sla_events (company_code, created_at DESC);
