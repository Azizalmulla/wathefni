#!/usr/bin/env bash
# Wathefni full backup.
#
# Produces, per run:
#   - db.dump            PostgreSQL custom-format dump (pg_dump -Fc, restorable with pg_restore)
#   - files.tar.zst      CVs, video interviews, transcripts/evidence, media, dashboard bundle, app snapshot, OpenClaw config
#   - secrets.tar.gz.gpg secrets/env inventory, AES256-encrypted (the backup passphrase itself is excluded)
#   - MANIFEST.txt + SHA256SUMS
#   - an encrypted offsite bundle in <root>/offsite that contains all of the above
#
# Retention: keeps N daily runs + N weekly runs (weekly promoted on Sundays).
# Offsite: pushes the encrypted bundle when WATHEFNI_BACKUP_RCLONE_REMOTE or
#          WATHEFNI_BACKUP_RSYNC_TARGET is configured; otherwise logs a clear SKIPPED line.
#
# Usage: backup-wathefni [daily|weekly]
set -euo pipefail

MODE="${1:-daily}"
BACKUP_ROOT="${WATHEFNI_BACKUP_ROOT:-/opt/wathefni/backups}"
LOG_FILE="${WATHEFNI_BACKUP_LOG:-/var/log/wathefni-backup.log}"
ENV_FILE="${WATHEFNI_POSTGRES_ENV:-/root/.openclaw/secrets/postgres.env}"
PASSPHRASE_FILE="${WATHEFNI_BACKUP_PASSPHRASE_FILE:-/root/.openclaw/secrets/backup-passphrase}"
SECRETS_DIR="/root/.openclaw/secrets"
WORKSPACE_DIR="/root/.openclaw/workspaces/company-wathefni"
OPENCLAW_CONFIG="/root/.openclaw/openclaw.json"
OPENCLAW_MEDIA="/root/.openclaw/media"
PUBLIC_MEDIA="/var/www/wathefni-media"
DASHBOARD_PUBLIC="/var/www/wathefni-dashboard"
DASHBOARD_DIST="/opt/wathefni/apps/wathefni-dashboard/dist"
ORCH_DIR="/opt/wathefni/orchestrator"
DAILY_KEEP="${WATHEFNI_BACKUP_DAILY_KEEP:-7}"
WEEKLY_KEEP="${WATHEFNI_BACKUP_WEEKLY_KEEP:-4}"

stamp="$(date -u +%Y%m%dT%H%M%SZ)"

log() { printf '%s [backup] %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$*" | tee -a "$LOG_FILE" >&2; }
fail() { log "FAILED: $*"; exit 1; }
trap 'log "ERROR at line $LINENO (mode=$MODE stamp=$stamp)"' ERR

mkdir -p "$BACKUP_ROOT/daily" "$BACKUP_ROOT/weekly" "$BACKUP_ROOT/offsite"
chmod 700 "$BACKUP_ROOT" "$BACKUP_ROOT/daily" "$BACKUP_ROOT/weekly" "$BACKUP_ROOT/offsite" 2>/dev/null || true
touch "$LOG_FILE"; chmod 600 "$LOG_FILE" 2>/dev/null || true

set -a; . "$ENV_FILE"; set +a
[ -n "${WATHEFNI_DATABASE_URL:-}" ] || fail "WATHEFNI_DATABASE_URL not set in $ENV_FILE"

if [ ! -s "$PASSPHRASE_FILE" ]; then
  log "generating new backup passphrase at $PASSPHRASE_FILE — STORE THIS IN A PASSWORD MANAGER; offsite restores need it"
  ( umask 077; openssl rand -base64 48 > "$PASSPHRASE_FILE" )
  chmod 600 "$PASSPHRASE_FILE"
fi

run="$BACKUP_ROOT/daily/$stamp"
mkdir -p "$run"; chmod 700 "$run"
log "start mode=$MODE stamp=$stamp db=$(echo "$WATHEFNI_DATABASE_URL" | sed -E 's#:[^:@/]+@#:***@#')"

# 1) Database (custom format, supports pg_restore --list and selective restore)
pg_dump "$WATHEFNI_DATABASE_URL" -Fc -f "$run/db.dump" || fail "pg_dump failed"
log "db.dump $(du -h "$run/db.dump" | cut -f1)"

# 2) Files: candidate CVs, video interviews, transcripts/evidence, media, dashboard bundle, app snapshot, config
includes=()
for p in "$WORKSPACE_DIR" "$PUBLIC_MEDIA" "$OPENCLAW_MEDIA" "$DASHBOARD_PUBLIC" "$DASHBOARD_DIST" "$OPENCLAW_CONFIG" "$ORCH_DIR"; do
  [ -e "$p" ] && includes+=("$p")
done
tar --zstd \
  --exclude='*/.venv' --exclude='*/.venv/*' \
  --exclude='*/__pycache__/*' --exclude='*.pyc' \
  --warning=no-file-changed \
  -cf "$run/files.tar.zst" "${includes[@]}" 2>>"$LOG_FILE" || fail "files archive failed"
log "files.tar.zst $(du -h "$run/files.tar.zst" | cut -f1)"

# 3) Secrets: encrypted, with the passphrase file itself excluded
tar -czf - -C "$SECRETS_DIR" --exclude="$(basename "$PASSPHRASE_FILE")" . \
  | gpg --batch --yes --symmetric --cipher-algo AES256 --passphrase-file "$PASSPHRASE_FILE" \
        -o "$run/secrets.tar.gz.gpg" || fail "secrets encryption failed"
chmod 600 "$run/secrets.tar.gz.gpg"
log "secrets.tar.gz.gpg encrypted (AES256)"

# 4) Manifest + checksums
{
  echo "stamp=$stamp"
  echo "mode=$MODE"
  echo "host=$(hostname)"
  echo "database=$(echo "$WATHEFNI_DATABASE_URL" | sed -E 's#:[^:@/]+@#:***@#')"
  echo "includes:"
  printf '  %s\n' "${includes[@]}"
  echo "excluded: orchestrator/.venv, __pycache__, *.pyc, $PASSPHRASE_FILE"
} > "$run/MANIFEST.txt"
( cd "$run" && sha256sum db.dump files.tar.zst secrets.tar.gz.gpg > SHA256SUMS )
log "manifest + sha256 written"

# 5) Encrypted offsite bundle (everything in one AES256 file)
offsite_name="offsite-$MODE-$stamp.tar.zst.gpg"
tar --zstd -C "$run" -cf - db.dump files.tar.zst secrets.tar.gz.gpg MANIFEST.txt SHA256SUMS \
  | gpg --batch --yes --symmetric --cipher-algo AES256 --passphrase-file "$PASSPHRASE_FILE" \
        -o "$BACKUP_ROOT/offsite/$offsite_name" || fail "offsite bundle failed"
chmod 600 "$BACKUP_ROOT/offsite/$offsite_name"
log "offsite bundle $offsite_name $(du -h "$BACKUP_ROOT/offsite/$offsite_name" | cut -f1)"

# 6) Weekly promotion (Sundays, or explicit weekly mode)
if [ "$MODE" = "weekly" ] || [ "$(date -u +%u)" = "7" ]; then
  cp -a "$run" "$BACKUP_ROOT/weekly/$stamp"
  cp -a "$BACKUP_ROOT/offsite/$offsite_name" "$BACKUP_ROOT/offsite/offsite-weekly-$stamp.tar.zst.gpg"
  log "promoted to weekly"
fi

# 7) Offsite push (pluggable; safe no-op if unconfigured)
if [ -n "${WATHEFNI_BACKUP_RCLONE_REMOTE:-}" ] && command -v rclone >/dev/null 2>&1; then
  if rclone copy "$BACKUP_ROOT/offsite/$offsite_name" "$WATHEFNI_BACKUP_RCLONE_REMOTE" >>"$LOG_FILE" 2>&1; then
    log "offsite_push rclone OK -> $WATHEFNI_BACKUP_RCLONE_REMOTE"
  else
    log "offsite_push rclone FAILED -> $WATHEFNI_BACKUP_RCLONE_REMOTE"
  fi
elif [ -n "${WATHEFNI_BACKUP_RSYNC_TARGET:-}" ]; then
  if rsync -az "$BACKUP_ROOT/offsite/$offsite_name" "$WATHEFNI_BACKUP_RSYNC_TARGET" >>"$LOG_FILE" 2>&1; then
    log "offsite_push rsync OK -> $WATHEFNI_BACKUP_RSYNC_TARGET"
  else
    log "offsite_push rsync FAILED -> $WATHEFNI_BACKUP_RSYNC_TARGET"
  fi
else
  log "offsite_push SKIPPED: set WATHEFNI_BACKUP_RCLONE_REMOTE or WATHEFNI_BACKUP_RSYNC_TARGET to enable automated offsite"
fi

# 8) Retention
python3 - "$BACKUP_ROOT" "$DAILY_KEEP" "$WEEKLY_KEEP" <<'PYRET'
import sys, shutil
from pathlib import Path
root = Path(sys.argv[1]); daily_keep = int(sys.argv[2]); weekly_keep = int(sys.argv[3])

def prune_dirs(d, keep):
    if not d.exists():
        return
    dirs = sorted([p for p in d.iterdir() if p.is_dir()], key=lambda p: p.name, reverse=True)
    for old in dirs[keep:]:
        shutil.rmtree(old, ignore_errors=True)

prune_dirs(root / 'daily', daily_keep)
prune_dirs(root / 'weekly', weekly_keep)
off = root / 'offsite'
if off.exists():
    for tag, keep in (('offsite-daily-', daily_keep), ('offsite-weekly-', weekly_keep)):
        arts = sorted([p for p in off.iterdir() if p.name.startswith(tag)], key=lambda p: p.name, reverse=True)
        for old in arts[keep:]:
            old.unlink(missing_ok=True)
PYRET
log "retention applied (daily_keep=$DAILY_KEEP weekly_keep=$WEEKLY_KEEP)"
log "SUCCESS stamp=$stamp"
