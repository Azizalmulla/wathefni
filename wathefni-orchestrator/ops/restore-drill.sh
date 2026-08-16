#!/usr/bin/env bash
# Wathefni restore drill: restores the latest (or a given) DB dump into a throwaway
# database, runs functional checks against it, verifies file linkage, and drops the
# test DB. This proves backups are actually restorable — not just present.
#
# Usage:
#   restore-drill.sh [<backup-run-dir>|<path-to-db.dump>]
set -euo pipefail

BACKUP_ROOT="${WATHEFNI_BACKUP_ROOT:-/opt/wathefni/backups}"
ENV_FILE="${WATHEFNI_POSTGRES_ENV:-/root/.openclaw/secrets/postgres.env}"
TEST_DB="${WATHEFNI_RESTORE_TEST_DB:-wathefni_restore_test}"
VENV_PY="${WATHEFNI_VENV_PY:-/opt/wathefni/orchestrator/.venv/bin/python}"
ORCH_DIR="${WATHEFNI_ORCH_DIR:-/opt/wathefni/orchestrator}"
SRC="${1:-}"

TMP_DUMP=""
log() { printf '%s [restore-drill] %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$*"; }
fail() { log "FAILED: $*"; exit 1; }
cleanup() {
  sudo -u postgres psql -c "DROP DATABASE IF EXISTS ${TEST_DB};" >/dev/null 2>&1 || true
  [ -n "$TMP_DUMP" ] && rm -f "$TMP_DUMP" 2>/dev/null || true
}
trap cleanup EXIT

# 1) Locate dump
if [ -z "$SRC" ]; then
  latest="$(ls -1dt "$BACKUP_ROOT"/daily/*/ 2>/dev/null | head -1 || true)"
  [ -n "$latest" ] || fail "no daily backup found under $BACKUP_ROOT/daily"
  DUMP="${latest%/}/db.dump"
elif [ -d "$SRC" ]; then
  DUMP="$SRC/db.dump"
else
  DUMP="$SRC"
fi
[ -s "$DUMP" ] || fail "dump not found or empty: $DUMP"
log "using dump: $DUMP"

# 2) Integrity: table of contents must be readable
toc_count="$(pg_restore --list "$DUMP" | grep -c 'TABLE DATA' || true)"
[ "$toc_count" -gt 0 ] || fail "pg_restore --list returned no TABLE DATA entries"
log "pg_restore --list OK ($toc_count table-data entries)"

set -a; . "$ENV_FILE"; set +a
APP_ROLE="$(printf '%s' "$WATHEFNI_DATABASE_URL" | sed -E 's#^[a-z]+://([^:]+):.*#\1#')"
[ -n "$APP_ROLE" ] || fail "could not parse app role from WATHEFNI_DATABASE_URL"

# 3) Fresh throwaway database
sudo -u postgres psql -v ON_ERROR_STOP=1 -c "DROP DATABASE IF EXISTS ${TEST_DB};" >/dev/null
sudo -u postgres psql -v ON_ERROR_STOP=1 -c "CREATE DATABASE ${TEST_DB} OWNER ${APP_ROLE};" >/dev/null
log "created fresh database ${TEST_DB} (owner ${APP_ROLE})"

# 4) Restore (as superuser so extensions create cleanly), then grant the app role access.
# The dump lives in a root-only (700) backup dir, so stage a copy the postgres user can read.
TMP_DUMP="$(mktemp /tmp/wathefni-restore-XXXXXX.dump)"
cp "$DUMP" "$TMP_DUMP"
chown postgres:postgres "$TMP_DUMP" 2>/dev/null || chmod 0644 "$TMP_DUMP"
sudo -u postgres pg_restore --no-owner --no-privileges -d "${TEST_DB}" "$TMP_DUMP" 2>/tmp/wathefni-restore-drill.err || {
  log "pg_restore completed with warnings:"; tail -n 5 /tmp/wathefni-restore-drill.err || true;
}
sudo -u postgres psql -v ON_ERROR_STOP=1 -d "${TEST_DB}" >/dev/null <<SQL
GRANT ALL ON SCHEMA public TO ${APP_ROLE};
GRANT ALL ON ALL TABLES IN SCHEMA public TO ${APP_ROLE};
GRANT ALL ON ALL SEQUENCES IN SCHEMA public TO ${APP_ROLE};
-- Make the app role own the restored objects so it can run schema migrations,
-- exactly as it does in production (extensions stay owned by the superuser).
DO \$\$
DECLARE r record;
BEGIN
  FOR r IN SELECT tablename FROM pg_tables WHERE schemaname='public' LOOP
    EXECUTE format('ALTER TABLE public.%I OWNER TO ${APP_ROLE}', r.tablename);
  END LOOP;
  FOR r IN SELECT sequencename FROM pg_sequences WHERE schemaname='public' LOOP
    EXECUTE format('ALTER SEQUENCE public.%I OWNER TO ${APP_ROLE}', r.sequencename);
  END LOOP;
  FOR r IN SELECT table_name FROM information_schema.views WHERE table_schema='public' LOOP
    EXECUTE format('ALTER VIEW public.%I OWNER TO ${APP_ROLE}', r.table_name);
  END LOOP;
END\$\$;
SQL
log "restored into ${TEST_DB}, granted + reassigned ownership to ${APP_ROLE}"

# 5) Record verification
counts="$(sudo -u postgres psql -tA -d "${TEST_DB}" -F '|' -c "
  SELECT 'candidates', count(*) FROM candidates
  UNION ALL SELECT 'applications', count(*) FROM applications
  UNION ALL SELECT 'positions', count(*) FROM positions
  UNION ALL SELECT 'candidate_interviews', count(*) FROM candidate_interviews
  UNION ALL SELECT 'candidate_video_interview_responses', count(*) FROM candidate_video_interview_responses
  UNION ALL SELECT 'dashboard_users', count(*) FROM dashboard_users
  UNION ALL SELECT 'action_results', count(*) FROM action_results;
")"
log "restored record counts:"
printf '%s\n' "$counts" | sed 's/^/    /'

# 6) Video interview file linkage: restored rows should still point to files on disk
"$VENV_PY" - "$TEST_DB" <<'PYV'
import os, subprocess, sys
test_db = sys.argv[1]
q = ("SELECT COALESCE(local_path, storage_object_key) FROM file_registry "
     "WHERE file_kind='video_interview_response' AND local_path IS NOT NULL "
     "ORDER BY created_at DESC LIMIT 10;")
out = subprocess.run(["sudo","-u","postgres","psql","-tA","-d",test_db,"-c",q], text=True, capture_output=True).stdout
paths = [p.strip() for p in out.splitlines() if p.strip()]
if not paths:
    print("    video file linkage: no video responses recorded yet (skipped)")
else:
    present = sum(1 for p in paths if os.path.exists(p))
    print(f"    video file linkage: {present}/{len(paths)} referenced files present on disk")
PYV

# 7) Functional smoke against the restored DB (app must operate on it)
RESTORE_URL="$(printf '%s' "$WATHEFNI_DATABASE_URL" | sed -E "s#/[^/?]+(\?|$)#/${TEST_DB}\1#")"
log "running smoke against restored DB"
(
  cd "$ORCH_DIR"
  WATHEFNI_DATABASE_URL="$RESTORE_URL" "$VENV_PY" - <<'PYSMOKE'
import app
app.ensure_schema(force=True)   # app can initialise/operate on the restored schema
with app.db_connect() as conn:
    with conn.cursor() as cur:
        cur.execute("SELECT count(*) AS c FROM applications")
        apps = cur.fetchone()["c"]
        cur.execute("SELECT count(*) AS c FROM dashboard_users")
        users = cur.fetchone()["c"]
print(f"    app on restored DB OK: applications={apps} dashboard_users={users}")
PYSMOKE
  WATHEFNI_DATABASE_URL="$RESTORE_URL" "$VENV_PY" smoke-test-tenant-read-behavior.py | sed 's/^/    /'
)

# 8) Cleanup
sudo -u postgres psql -v ON_ERROR_STOP=1 -c "DROP DATABASE IF EXISTS ${TEST_DB};" >/dev/null
log "dropped ${TEST_DB}"
log "RESTORE DRILL PASSED"
