-- R8 delivery safety: first-party error events. Ledger is created by the framework.
CREATE TABLE IF NOT EXISTS wathefni_error_events (
  event_id text PRIMARY KEY,
  created_at timestamptz NOT NULL DEFAULT now(),
  surface text NOT NULL,
  level text NOT NULL,
  message text NOT NULL,
  detail jsonb NOT NULL DEFAULT '{}'::jsonb
);

CREATE INDEX IF NOT EXISTS wathefni_error_events_created_idx
  ON wathefni_error_events (created_at DESC);

CREATE INDEX IF NOT EXISTS wathefni_error_events_surface_idx
  ON wathefni_error_events (surface, created_at DESC);
