"""Wathefni Calendar C1 — schema / ensure helpers.

Creates the canonical first-party event spine tables. Recurrence columns,
resource tables, and calendar_link_outbox are infrastructure-only in C1
(no product behavior). Interview enqueue/worker remains C2.
"""

from __future__ import annotations

from typing import Any


CALENDAR_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS calendar_events (
  event_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  company_code text NOT NULL,
  event_type text NOT NULL,
  title text NOT NULL,
  title_ar text,
  description text,
  description_ar text,
  visibility text NOT NULL DEFAULT 'attendees_only',
  sensitivity text NOT NULL DEFAULT 'normal',
  status text NOT NULL DEFAULT 'confirmed',
  start_at timestamptz NOT NULL,
  end_at timestamptz NOT NULL,
  timezone text NOT NULL DEFAULT 'Asia/Kuwait',
  all_day boolean NOT NULL DEFAULT false,
  location text,
  meeting_url text,
  org_scope_kind_hint text,
  legacy_team_key text,
  creator_user_id text NOT NULL,
  organizer_user_id text NOT NULL,
  owner_user_id text,
  version int NOT NULL DEFAULT 1,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  updated_by_user_id text,
  cancelled_at timestamptz,
  completed_at timestamptz,
  recurrence_rule text,
  recurrence_timezone text,
  recurrence_series_id uuid,
  recurrence_series_version int NOT NULL DEFAULT 1,
  recurrence_parent_id uuid,
  is_recurrence_exception boolean NOT NULL DEFAULT false,
  recurrence_original_start_at timestamptz,
  metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
  CONSTRAINT calendar_events_time_order CHECK (end_at >= start_at),
  CONSTRAINT calendar_events_type_chk CHECK (
    event_type IN ('meeting','interview','personal_block','deadline','hold','out_of_office','other')
  ),
  CONSTRAINT calendar_events_visibility_chk CHECK (
    visibility IN ('private','attendees_only','team','company')
  ),
  CONSTRAINT calendar_events_sensitivity_chk CHECK (
    sensitivity IN ('normal','candidate_confidential','sensitive')
  ),
  CONSTRAINT calendar_events_status_chk CHECK (
    status IN ('tentative','confirmed','cancelled','completed')
  )
);

CREATE INDEX IF NOT EXISTS idx_calendar_events_company_range
  ON calendar_events (company_code, start_at, end_at);
CREATE INDEX IF NOT EXISTS idx_calendar_events_company_visibility
  ON calendar_events (company_code, visibility, start_at);
CREATE INDEX IF NOT EXISTS idx_calendar_events_company_organizer
  ON calendar_events (company_code, organizer_user_id, start_at);
CREATE INDEX IF NOT EXISTS idx_calendar_events_company_status
  ON calendar_events (company_code, status, start_at);
CREATE INDEX IF NOT EXISTS idx_calendar_events_series
  ON calendar_events (company_code, recurrence_series_id);

CREATE TABLE IF NOT EXISTS calendar_event_org_scopes (
  event_id uuid NOT NULL REFERENCES calendar_events(event_id) ON DELETE CASCADE,
  company_code text NOT NULL,
  org_scope_id text NOT NULL,
  org_scope_kind text,
  created_at timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (event_id, org_scope_id)
);
CREATE INDEX IF NOT EXISTS idx_calendar_event_org_scopes_company
  ON calendar_event_org_scopes (company_code, org_scope_id);

CREATE TABLE IF NOT EXISTS calendar_attendees (
  attendee_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  event_id uuid NOT NULL REFERENCES calendar_events(event_id) ON DELETE CASCADE,
  company_code text NOT NULL,
  user_id text NOT NULL,
  role text NOT NULL DEFAULT 'required',
  rsvp_status text NOT NULL DEFAULT 'needs_action',
  response_at timestamptz,
  is_organizer boolean NOT NULL DEFAULT false,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT calendar_attendees_role_chk CHECK (
    role IN ('organizer','required','optional','resource_owner')
  ),
  CONSTRAINT calendar_attendees_rsvp_chk CHECK (
    rsvp_status IN ('needs_action','accepted','declined','tentative','removed')
  )
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_calendar_attendees_active
  ON calendar_attendees (event_id, user_id)
  WHERE rsvp_status <> 'removed';
CREATE INDEX IF NOT EXISTS idx_calendar_attendees_user
  ON calendar_attendees (company_code, user_id, event_id);

CREATE TABLE IF NOT EXISTS calendar_guests (
  guest_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  event_id uuid NOT NULL REFERENCES calendar_events(event_id) ON DELETE CASCADE,
  company_code text NOT NULL,
  email text,
  phone text,
  display_name text,
  guest_kind text NOT NULL DEFAULT 'external',
  person_key text,
  app_key text,
  rsvp_status text NOT NULL DEFAULT 'needs_action',
  invite_channel text NOT NULL DEFAULT 'none',
  last_invited_at timestamptz,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT calendar_guests_kind_chk CHECK (
    guest_kind IN ('candidate','external','other')
  ),
  CONSTRAINT calendar_guests_rsvp_chk CHECK (
    rsvp_status IN ('needs_action','accepted','declined','tentative','removed')
  ),
  CONSTRAINT calendar_guests_channel_chk CHECK (
    invite_channel IN ('email','whatsapp','none')
  )
);
CREATE INDEX IF NOT EXISTS idx_calendar_guests_event
  ON calendar_guests (company_code, event_id);
CREATE INDEX IF NOT EXISTS idx_calendar_guests_person
  ON calendar_guests (company_code, person_key)
  WHERE person_key IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_calendar_guests_app
  ON calendar_guests (company_code, app_key)
  WHERE app_key IS NOT NULL;

CREATE TABLE IF NOT EXISTS calendar_event_links (
  link_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  company_code text NOT NULL,
  event_id uuid NOT NULL REFERENCES calendar_events(event_id) ON DELETE CASCADE,
  source_workflow text NOT NULL,
  source_record_id text NOT NULL,
  link_status text NOT NULL DEFAULT 'active',
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT calendar_event_links_status_chk CHECK (
    link_status IN ('active','detached','superseded')
  )
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_calendar_event_links_active
  ON calendar_event_links (company_code, source_workflow, source_record_id)
  WHERE link_status = 'active';
CREATE INDEX IF NOT EXISTS idx_calendar_event_links_event
  ON calendar_event_links (company_code, event_id);

CREATE TABLE IF NOT EXISTS calendar_event_audit (
  audit_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  event_id uuid NOT NULL,
  company_code text NOT NULL,
  actor_user_id text,
  action text NOT NULL,
  before jsonb,
  after jsonb,
  request_id text,
  created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_calendar_event_audit_event
  ON calendar_event_audit (company_code, event_id, created_at DESC);

-- Reminders table (storage only in C1 — no worker).
CREATE TABLE IF NOT EXISTS calendar_reminders (
  reminder_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  event_id uuid NOT NULL REFERENCES calendar_events(event_id) ON DELETE CASCADE,
  company_code text NOT NULL,
  user_id text,
  kind text NOT NULL DEFAULT 'event',
  offset_minutes int,
  channel text NOT NULL DEFAULT 'in_app',
  fire_at timestamptz,
  sent_at timestamptz,
  status text NOT NULL DEFAULT 'pending',
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT calendar_reminders_kind_chk CHECK (kind IN ('event','personal')),
  CONSTRAINT calendar_reminders_channel_chk CHECK (channel IN ('in_app','whatsapp','email'))
);

-- Resource infrastructure (unused product in C1; EXCLUDE activation is later).
CREATE TABLE IF NOT EXISTS calendar_resources (
  resource_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  company_code text NOT NULL,
  resource_type text NOT NULL DEFAULT 'room',
  name text NOT NULL,
  capacity int,
  timezone text,
  metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
  is_active boolean NOT NULL DEFAULT true,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_calendar_resources_company
  ON calendar_resources (company_code, is_active);

CREATE TABLE IF NOT EXISTS calendar_resource_bookings (
  booking_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  event_id uuid NOT NULL REFERENCES calendar_events(event_id) ON DELETE CASCADE,
  resource_id uuid NOT NULL REFERENCES calendar_resources(resource_id) ON DELETE CASCADE,
  company_code text NOT NULL,
  status text NOT NULL DEFAULT 'confirmed',
  start_at timestamptz NOT NULL,
  end_at timestamptz NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_calendar_resource_bookings_resource
  ON calendar_resource_bookings (company_code, resource_id, start_at, end_at);

-- C2 outbox (created unused in C1 — no enqueue/worker).
CREATE TABLE IF NOT EXISTS calendar_link_outbox (
  outbox_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  company_code text NOT NULL,
  source_workflow text NOT NULL,
  source_record_id text NOT NULL,
  operation text NOT NULL,
  idempotency_key text NOT NULL,
  payload jsonb NOT NULL DEFAULT '{}'::jsonb,
  status text NOT NULL DEFAULT 'pending',
  attempt_count int NOT NULL DEFAULT 0,
  next_attempt_at timestamptz,
  last_error text,
  processed_at timestamptz,
  created_at timestamptz NOT NULL DEFAULT now(),
  updated_at timestamptz NOT NULL DEFAULT now(),
  CONSTRAINT calendar_link_outbox_status_chk CHECK (
    status IN ('pending','processing','processed','failed','dead')
  ),
  CONSTRAINT calendar_link_outbox_operation_chk CHECK (
    operation IN ('ensure','cancel','complete','sync_attendees')
  )
);
CREATE UNIQUE INDEX IF NOT EXISTS uq_calendar_link_outbox_idempotency
  ON calendar_link_outbox (company_code, idempotency_key);
CREATE INDEX IF NOT EXISTS idx_calendar_link_outbox_claim
  ON calendar_link_outbox (status, next_attempt_at);
"""


def ensure_calendar_schema(cur: Any) -> None:
    """Idempotent Calendar spine DDL."""
    cur.execute(CALENDAR_SCHEMA_SQL)
    # C2 additive lease columns for outbox claim/crash recovery (safe if already present).
    # Must run after CREATE TABLE IF NOT EXISTS — existing C1 tables lack these columns.
    cur.execute(
        """
        ALTER TABLE IF EXISTS calendar_link_outbox
          ADD COLUMN IF NOT EXISTS lease_owner text;
        ALTER TABLE IF EXISTS calendar_link_outbox
          ADD COLUMN IF NOT EXISTS lease_expires_at timestamptz;
        """
    )
    cur.execute(
        """
        CREATE INDEX IF NOT EXISTS idx_calendar_link_outbox_lease
          ON calendar_link_outbox (lease_expires_at)
          WHERE status = 'processing';
        """
    )
    # C4 — guest tokens, reschedule requests, delivery outbox, reminder worker columns.
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS calendar_guest_tokens (
          token_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
          company_code text NOT NULL,
          event_id uuid NOT NULL REFERENCES calendar_events(event_id) ON DELETE CASCADE,
          guest_id uuid NOT NULL REFERENCES calendar_guests(guest_id) ON DELETE CASCADE,
          token_hash text NOT NULL UNIQUE,
          purpose text NOT NULL DEFAULT 'rsvp',
          expires_at timestamptz NOT NULL,
          revoked_at timestamptz,
          used_at timestamptz,
          last_action text,
          created_at timestamptz NOT NULL DEFAULT now(),
          CONSTRAINT calendar_guest_tokens_purpose_chk CHECK (
            purpose IN ('rsvp','invite')
          )
        );
        CREATE INDEX IF NOT EXISTS idx_calendar_guest_tokens_guest
          ON calendar_guest_tokens (company_code, guest_id, created_at DESC);
        CREATE INDEX IF NOT EXISTS idx_calendar_guest_tokens_event
          ON calendar_guest_tokens (company_code, event_id);

        CREATE TABLE IF NOT EXISTS calendar_reschedule_requests (
          request_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
          company_code text NOT NULL,
          event_id uuid NOT NULL REFERENCES calendar_events(event_id) ON DELETE CASCADE,
          guest_id uuid REFERENCES calendar_guests(guest_id) ON DELETE SET NULL,
          interview_id text,
          status text NOT NULL DEFAULT 'pending',
          preferred_times jsonb NOT NULL DEFAULT '[]'::jsonb,
          note text,
          resolved_at timestamptz,
          resolved_by_user_id text,
          resolution_note text,
          created_at timestamptz NOT NULL DEFAULT now(),
          updated_at timestamptz NOT NULL DEFAULT now(),
          CONSTRAINT calendar_reschedule_requests_status_chk CHECK (
            status IN ('pending','accepted','declined','cancelled','superseded')
          )
        );
        CREATE UNIQUE INDEX IF NOT EXISTS uq_calendar_reschedule_pending_guest
          ON calendar_reschedule_requests (company_code, event_id, guest_id)
          WHERE status = 'pending' AND guest_id IS NOT NULL;
        CREATE INDEX IF NOT EXISTS idx_calendar_reschedule_event
          ON calendar_reschedule_requests (company_code, event_id, status);

        CREATE TABLE IF NOT EXISTS calendar_delivery_outbox (
          delivery_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
          company_code text NOT NULL,
          event_id uuid NOT NULL,
          guest_id uuid,
          reminder_id uuid,
          channel text NOT NULL,
          purpose text NOT NULL,
          idempotency_key text NOT NULL,
          payload jsonb NOT NULL DEFAULT '{}'::jsonb,
          status text NOT NULL DEFAULT 'queued',
          attempt_count int NOT NULL DEFAULT 0,
          next_attempt_at timestamptz NOT NULL DEFAULT now(),
          lease_owner text,
          lease_expires_at timestamptz,
          last_error text,
          provider_ref text,
          delivered_at timestamptz,
          created_at timestamptz NOT NULL DEFAULT now(),
          updated_at timestamptz NOT NULL DEFAULT now(),
          CONSTRAINT calendar_delivery_outbox_channel_chk CHECK (
            channel IN ('email','whatsapp','in_app','routed')
          ),
          CONSTRAINT calendar_delivery_outbox_purpose_chk CHECK (
            purpose IN (
              'guest_invite','guest_reminder','guest_cancel','guest_update',
              'attendee_invite','attendee_reminder','attendee_cancel','attendee_update',
              'rsvp_notice','reschedule_notice'
            )
          ),
          CONSTRAINT calendar_delivery_outbox_status_chk CHECK (
            status IN ('not_queued','queued','processing','delivered','failed','dead','cancelled')
          )
        );
        CREATE UNIQUE INDEX IF NOT EXISTS uq_calendar_delivery_idempotency
          ON calendar_delivery_outbox (company_code, idempotency_key);
        CREATE INDEX IF NOT EXISTS idx_calendar_delivery_claim
          ON calendar_delivery_outbox (status, next_attempt_at);
        """
    )
    # Existing DBs may still have the pre-correction channel CHECK without `routed`.
    cur.execute("ALTER TABLE IF EXISTS calendar_delivery_outbox DROP CONSTRAINT IF EXISTS calendar_delivery_outbox_channel_chk")
    cur.execute(
        """
        ALTER TABLE IF EXISTS calendar_delivery_outbox
          ADD CONSTRAINT calendar_delivery_outbox_channel_chk
          CHECK (channel IN ('email','whatsapp','in_app','routed'))
        """
    )
    cur.execute(
        """
        ALTER TABLE IF EXISTS calendar_reminders
          ADD COLUMN IF NOT EXISTS guest_id uuid,
          ADD COLUMN IF NOT EXISTS idempotency_key text,
          ADD COLUMN IF NOT EXISTS attempt_count int NOT NULL DEFAULT 0,
          ADD COLUMN IF NOT EXISTS next_attempt_at timestamptz,
          ADD COLUMN IF NOT EXISTS lease_owner text,
          ADD COLUMN IF NOT EXISTS lease_expires_at timestamptz,
          ADD COLUMN IF NOT EXISTS last_error text,
          ADD COLUMN IF NOT EXISTS version int NOT NULL DEFAULT 1;
        ALTER TABLE IF EXISTS calendar_guests
          ADD COLUMN IF NOT EXISTS invite_status text NOT NULL DEFAULT 'not_queued',
          ADD COLUMN IF NOT EXISTS last_delivery_error text,
          ADD COLUMN IF NOT EXISTS rsvp_version int NOT NULL DEFAULT 1;
        ALTER TABLE IF EXISTS calendar_attendees
          ADD COLUMN IF NOT EXISTS rsvp_version int NOT NULL DEFAULT 1;
        """
    )
    cur.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS uq_calendar_reminders_idempotency
          ON calendar_reminders (company_code, idempotency_key)
          WHERE idempotency_key IS NOT NULL;
        CREATE INDEX IF NOT EXISTS idx_calendar_reminders_claim
          ON calendar_reminders (status, fire_at)
          WHERE status IN ('pending','failed');
        """
    )
    # C5 — provider-neutral external sync (Google first; no provider logic in domain).
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS calendar_sync_connections (
          connection_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
          company_code text NOT NULL,
          provider_key text NOT NULL,
          mode text NOT NULL DEFAULT 'company',
          owner_user_id text,
          status text NOT NULL DEFAULT 'not_connected',
          credentials_ref text,
          account_email text,
          external_calendar_id text NOT NULL DEFAULT 'primary',
          display_name text,
          sync_event_types jsonb NOT NULL DEFAULT '["meeting","interview","personal_block","hold","out_of_office","deadline","other"]'::jsonb,
          sync_include_candidate_name boolean NOT NULL DEFAULT false,
          with_meet_default boolean NOT NULL DEFAULT false,
          last_sync_at timestamptz,
          last_error text,
          health jsonb NOT NULL DEFAULT '{}'::jsonb,
          metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
          created_at timestamptz NOT NULL DEFAULT now(),
          updated_at timestamptz NOT NULL DEFAULT now(),
          disconnected_at timestamptz,
          CONSTRAINT calendar_sync_connections_provider_chk CHECK (
            provider_key IN ('google','microsoft','other')
          ),
          CONSTRAINT calendar_sync_connections_mode_chk CHECK (
            mode IN ('company','user','legacy_operator')
          ),
          CONSTRAINT calendar_sync_connections_status_chk CHECK (
            status IN ('not_connected','connected','error','disconnected')
          )
        );
        CREATE UNIQUE INDEX IF NOT EXISTS uq_calendar_sync_conn_company_provider_mode
          ON calendar_sync_connections (company_code, provider_key, mode)
          WHERE status <> 'disconnected' AND mode = 'legacy_operator';
        CREATE INDEX IF NOT EXISTS idx_calendar_sync_conn_company
          ON calendar_sync_connections (company_code, status);

        CREATE TABLE IF NOT EXISTS calendar_sync_credentials (
          credential_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
          connection_id uuid NOT NULL REFERENCES calendar_sync_connections(connection_id) ON DELETE CASCADE,
          company_code text NOT NULL,
          secret_type text NOT NULL DEFAULT 'refresh_token',
          ciphertext text NOT NULL,
          key_version text NOT NULL,
          alg text NOT NULL DEFAULT 'fernet',
          token_meta jsonb NOT NULL DEFAULT '{}'::jsonb,
          created_at timestamptz NOT NULL DEFAULT now(),
          updated_at timestamptz NOT NULL DEFAULT now(),
          UNIQUE (connection_id, secret_type)
        );
        CREATE INDEX IF NOT EXISTS idx_calendar_sync_creds_company
          ON calendar_sync_credentials (company_code, connection_id);

        CREATE TABLE IF NOT EXISTS calendar_sync_bindings (
          binding_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
          company_code text NOT NULL,
          event_id uuid NOT NULL,
          connection_id uuid NOT NULL REFERENCES calendar_sync_connections(connection_id) ON DELETE CASCADE,
          provider_event_id text,
          provider_calendar_id text,
          external_html_link text,
          sync_status text NOT NULL DEFAULT 'queued',
          last_pushed_version int,
          last_synced_at timestamptz,
          last_error text,
          metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
          created_at timestamptz NOT NULL DEFAULT now(),
          updated_at timestamptz NOT NULL DEFAULT now(),
          CONSTRAINT calendar_sync_bindings_status_chk CHECK (
            sync_status IN ('queued','synced','partially_synced','failed','conflict')
          ),
          UNIQUE (connection_id, event_id)
        );
        CREATE UNIQUE INDEX IF NOT EXISTS uq_calendar_sync_binding_provider_event
          ON calendar_sync_bindings (connection_id, provider_event_id)
          WHERE provider_event_id IS NOT NULL;
        CREATE INDEX IF NOT EXISTS idx_calendar_sync_bindings_event
          ON calendar_sync_bindings (company_code, event_id);

        CREATE TABLE IF NOT EXISTS calendar_sync_outbox (
          outbox_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
          company_code text NOT NULL,
          connection_id uuid NOT NULL,
          event_id uuid NOT NULL,
          operation text NOT NULL,
          event_version int NOT NULL,
          idempotency_key text NOT NULL,
          payload jsonb NOT NULL DEFAULT '{}'::jsonb,
          status text NOT NULL DEFAULT 'queued',
          attempt_count int NOT NULL DEFAULT 0,
          next_attempt_at timestamptz NOT NULL DEFAULT now(),
          lease_owner text,
          lease_expires_at timestamptz,
          last_error text,
          coalesced_into uuid,
          created_at timestamptz NOT NULL DEFAULT now(),
          updated_at timestamptz NOT NULL DEFAULT now(),
          CONSTRAINT calendar_sync_outbox_op_chk CHECK (
            operation IN ('upsert','cancel','repair')
          ),
          CONSTRAINT calendar_sync_outbox_status_chk CHECK (
            status IN ('queued','processing','delivered','failed','dead','cancelled','suppressed')
          ),
          UNIQUE (company_code, idempotency_key)
        );
        CREATE INDEX IF NOT EXISTS idx_calendar_sync_outbox_claim
          ON calendar_sync_outbox (status, next_attempt_at);

        CREATE TABLE IF NOT EXISTS calendar_sync_audit (
          audit_id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
          company_code text NOT NULL,
          connection_id uuid,
          event_id uuid,
          actor_user_id text,
          action text NOT NULL,
          before_json jsonb NOT NULL DEFAULT '{}'::jsonb,
          after_json jsonb NOT NULL DEFAULT '{}'::jsonb,
          created_at timestamptz NOT NULL DEFAULT now()
        );
        CREATE INDEX IF NOT EXISTS idx_calendar_sync_audit_company
          ON calendar_sync_audit (company_code, created_at DESC);
        """
    )
    # Platform integrations foundation (shared company connections).
    try:
        import platform_integrations as pi

        pi.ensure_schema(cur)
    except Exception:
        pass
    # Expand provider_key to include microsoft if older DBs lack it (idempotent; avoid lock churn).
    cur.execute(
        """
        SELECT pg_get_constraintdef(oid) AS def
        FROM pg_constraint
        WHERE conrelid = 'calendar_sync_connections'::regclass
          AND conname = 'calendar_sync_connections_provider_chk'
        LIMIT 1
        """
    )
    row = cur.fetchone()
    defn = ""
    if row:
        defn = str(row["def"] if isinstance(row, dict) else row[0] or "")
    if "microsoft" not in defn:
        cur.execute("ALTER TABLE IF EXISTS calendar_sync_connections DROP CONSTRAINT IF EXISTS calendar_sync_connections_provider_chk")
        cur.execute(
            """
            ALTER TABLE IF EXISTS calendar_sync_connections
              ADD CONSTRAINT calendar_sync_connections_provider_chk
              CHECK (provider_key IN ('google','microsoft','other'))
            """
        )
