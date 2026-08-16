#!/usr/bin/env bash
set -euo pipefail
ROOT=$(cd "$(dirname "$0")" && pwd)
CSV="$ROOT/ode-null-or-wave1-pre.csv"
test -f "$CSV"
test -f "$ROOT/db.dump"
STAGE=$(mktemp /tmp/ode-wave1-rollback-XXXX.csv)
cp "$CSV" "$STAGE"
chmod 644 "$STAGE"
sudo -u postgres psql -d wathefni -v ON_ERROR_STOP=1 <<SQL
CREATE TEMP TABLE ode_wave1_rollback (
  delivery_id text PRIMARY KEY,
  company_code text,
  payload jsonb
);
\\copy ode_wave1_rollback FROM '$STAGE' WITH (FORMAT csv, HEADER true);
UPDATE outbound_delivery_events ode
   SET company_code = r.company_code,
       payload = COALESCE(r.payload, '{}'::jsonb),
       updated_at = now()
  FROM ode_wave1_rollback r
 WHERE ode.delivery_id = r.delivery_id;
SQL
rm -f "$STAGE"
echo MIGRATION_ROLLBACK_SQL_OK
echo "Full DB restore if needed: sudo -u postgres pg_restore --clean --if-exists -d wathefni $ROOT/db.dump"
