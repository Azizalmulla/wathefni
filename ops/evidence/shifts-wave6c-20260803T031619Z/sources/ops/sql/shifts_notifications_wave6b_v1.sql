-- Shifts Wave 6B — channel-agnostic notification outbox (synthetic / mock adapters only).
-- No real provider messages. Wathefni remains acknowledgement authority.
-- Does NOT: send WhatsApp/Teams/Telegram/email/SMS, enable real reminders, PAM submit, Payroll money.

CREATE TABLE IF NOT EXISTS shift_channel_preferences (
  preference_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  company_code text NOT NULL,
  scope_type text NOT NULL DEFAULT 'company', -- company | employee
  scope_key text NOT NULL DEFAULT '*',
  channel_order jsonb NOT NULL DEFAULT '["app","push","whatsapp","email"]'::jsonb,
  fallback_enabled boolean NOT NULL DEFAULT true,
  enabled_channels jsonb NOT NULL DEFAULT '["app","push","whatsapp","teams","telegram","email","sms","web"]'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT shift_channel_preferences_scope_chk
    CHECK (scope_type IN ('company','employee')),
  CONSTRAINT shift_channel_preferences_uniq UNIQUE (company_code, scope_type, scope_key)
);
CREATE INDEX IF NOT EXISTS idx_shift_channel_preferences_company
  ON shift_channel_preferences(company_code, scope_type);

CREATE TABLE IF NOT EXISTS shift_notification_events (
  event_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  company_code text NOT NULL,
  event_type text NOT NULL,
  employee_key text NOT NULL,
  employee_phone text,
  employee_name text,
  shift_id uuid,
  schedule_period_id uuid,
  schedule_version_id uuid,
  open_shift_id uuid,
  dedupe_key text NOT NULL,
  payload jsonb NOT NULL DEFAULT '{}'::jsonb,
  status text NOT NULL DEFAULT 'pending',
  requires_ack boolean NOT NULL DEFAULT false,
  acked_at timestamptz,
  acked_via_channel text,
  invalidated_at timestamptz,
  invalidate_reason text,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT shift_notification_events_status_chk
    CHECK (status IN ('pending','delivering','delivered','acked','failed','invalidated','suppressed')),
  CONSTRAINT shift_notification_events_dedupe_uniq UNIQUE (company_code, dedupe_key)
);
CREATE INDEX IF NOT EXISTS idx_shift_notification_events_employee
  ON shift_notification_events(company_code, employee_key, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_shift_notification_events_type
  ON shift_notification_events(company_code, event_type, status);

CREATE TABLE IF NOT EXISTS shift_notification_deliveries (
  delivery_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  company_code text NOT NULL,
  event_id uuid NOT NULL REFERENCES shift_notification_events(event_id) ON DELETE CASCADE,
  channel text NOT NULL,
  attempt_no integer NOT NULL DEFAULT 1,
  status text NOT NULL DEFAULT 'queued',
  provider text NOT NULL DEFAULT 'mock',
  provider_message_id text,
  correlation_id text,
  error_code text,
  error_detail text,
  next_retry_at timestamptz,
  delivered_at timestamptz,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT shift_notification_deliveries_status_chk
    CHECK (status IN ('queued','sent','delivered','failed','skipped','unsupported','terminal_failed')),
  CONSTRAINT shift_notification_deliveries_channel_chk
    CHECK (channel IN ('app','push','whatsapp','teams','telegram','email','sms','web','connector'))
);
CREATE INDEX IF NOT EXISTS idx_shift_notification_deliveries_event
  ON shift_notification_deliveries(event_id, attempt_no);
CREATE UNIQUE INDEX IF NOT EXISTS idx_shift_notification_deliveries_dedupe
  ON shift_notification_deliveries(event_id, channel, attempt_no);

CREATE TABLE IF NOT EXISTS shift_notification_acks (
  ack_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  company_code text NOT NULL,
  event_id uuid NOT NULL REFERENCES shift_notification_events(event_id) ON DELETE CASCADE,
  channel text NOT NULL,
  actor_phone text,
  actor_employee_key text,
  payload jsonb NOT NULL DEFAULT '{}'::jsonb,
  created_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT shift_notification_acks_event_uniq UNIQUE (event_id)
);
CREATE INDEX IF NOT EXISTS idx_shift_notification_acks_company
  ON shift_notification_acks(company_code, created_at DESC);
