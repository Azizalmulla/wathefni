#!/usr/bin/env bash
# -----------------------------------------------------------------------------
# Nightly backup of customer profile memory.
#
# Scope
# -----
# Backs up the per-customer JSON memory at
# `$RIDERS_CUSTOMER_MEMORY_DIR` (default:
# `/root/.openclaw-delivery/customer-profiles/`) into a local rotating archive
# at `/root/backups/customer-profiles/`. Keeps the last N days of backups
# (default 30) and deletes older ones.
#
# Why local-only (for now)
# -----------------------
# Zero external dependencies, zero credentials, zero failure modes beyond
# local disk. Protects against accidental deletion, sanitizer bugs, schema
# migration mistakes, and the vast majority of "we broke memory" scenarios.
# It does NOT protect against full VPS loss — for that, add an offsite
# upload step (S3 / Backblaze / rsync to secondary host). Instructions at
# the bottom of this file.
#
# How to install on the VPS
# -------------------------
#   1. scp this script to the VPS:
#        scp scripts/backup-customer-profiles.sh root@<vps>:/usr/local/bin/
#   2. Make executable:
#        ssh root@<vps> 'chmod +x /usr/local/bin/backup-customer-profiles.sh'
#   3. Add to root crontab (runs every day at 03:17 UTC — off-peak, not on
#      the hour to avoid deploy collisions):
#        ssh root@<vps> 'echo "17 3 * * * /usr/local/bin/backup-customer-profiles.sh >> /var/log/customer-profile-backup.log 2>&1" | crontab -'
#   4. Verify it runs once:
#        ssh root@<vps> '/usr/local/bin/backup-customer-profiles.sh && ls -la /root/backups/customer-profiles/'
#
# Monitoring
# ----------
# Each run appends one-line status to `/var/log/customer-profile-backup.log`.
# Grep for `[backup] failed` to spot problems. If the archive count drops
# below the retention window unexpectedly, investigate.
# -----------------------------------------------------------------------------
set -euo pipefail

SOURCE_DIR="${RIDERS_CUSTOMER_MEMORY_DIR:-/root/.openclaw-delivery/customer-profiles}"
BACKUP_DIR="${RIDERS_CUSTOMER_BACKUP_DIR:-/root/backups/customer-profiles}"
RETENTION_DAYS="${RIDERS_CUSTOMER_BACKUP_RETENTION_DAYS:-30}"

timestamp="$(date -u +%Y%m%dT%H%M%SZ)"
archive_path="${BACKUP_DIR}/customer-profiles-${timestamp}.tar.gz"

log_line() {
  # Timestamped, greppable status. Use `[backup] ok` / `[backup] failed`
  # so ops can distinguish real failures from noise.
  echo "$(date -u +%Y-%m-%dT%H:%M:%SZ) $*"
}

if [[ ! -d "${SOURCE_DIR}" ]]; then
  log_line "[backup] failed source_dir_missing path=${SOURCE_DIR}"
  exit 1
fi

mkdir -p "${BACKUP_DIR}"

# File count BEFORE tar — included in the log line so we can spot a sudden
# drop (e.g. accidental rm -rf that happened pre-backup).
file_count_before="$(find "${SOURCE_DIR}" -maxdepth 1 -type f | wc -l | tr -d ' ')"

if ! tar -czf "${archive_path}" -C "$(dirname "${SOURCE_DIR}")" "$(basename "${SOURCE_DIR}")" 2>/dev/null; then
  log_line "[backup] failed tar_error path=${archive_path}"
  exit 1
fi

archive_size="$(stat -c '%s' "${archive_path}" 2>/dev/null || stat -f '%z' "${archive_path}")"

# Retention: delete archives older than RETENTION_DAYS. Uses -mtime so a
# clock skew won't silently prune everything (find reports days since
# modification, not absolute age).
deleted_count="$(find "${BACKUP_DIR}" -maxdepth 1 -name 'customer-profiles-*.tar.gz' -type f -mtime "+${RETENTION_DAYS}" -print -delete | wc -l | tr -d ' ')"

archive_count_after="$(find "${BACKUP_DIR}" -maxdepth 1 -name 'customer-profiles-*.tar.gz' -type f | wc -l | tr -d ' ')"

log_line "[backup] ok archive=${archive_path} size_bytes=${archive_size} profiles=${file_count_before} pruned=${deleted_count} retained=${archive_count_after}"

# -----------------------------------------------------------------------------
# OPTIONAL: offsite upload
# -----------------------------------------------------------------------------
# To extend this to a second location (recommended before heavy traffic),
# uncomment ONE of the following blocks and set the relevant env vars in
# `/etc/environment` or the systemd unit:
#
# S3 (requires aws-cli configured on the VPS):
#   if command -v aws >/dev/null 2>&1 && [[ -n "${RIDERS_BACKUP_S3_URI:-}" ]]; then
#     aws s3 cp "${archive_path}" "${RIDERS_BACKUP_S3_URI}/" --only-show-errors \
#       && log_line "[backup] s3_upload_ok dest=${RIDERS_BACKUP_S3_URI}" \
#       || log_line "[backup] failed s3_upload_error dest=${RIDERS_BACKUP_S3_URI}"
#   fi
#
# Backblaze B2 (requires b2-cli):
#   if command -v b2 >/dev/null 2>&1 && [[ -n "${RIDERS_BACKUP_B2_BUCKET:-}" ]]; then
#     b2 upload-file "${RIDERS_BACKUP_B2_BUCKET}" "${archive_path}" \
#       "customer-profiles/$(basename "${archive_path}")" \
#       && log_line "[backup] b2_upload_ok" \
#       || log_line "[backup] failed b2_upload_error"
#   fi
#
# rsync to secondary host:
#   if [[ -n "${RIDERS_BACKUP_RSYNC_DEST:-}" ]]; then
#     rsync -az "${archive_path}" "${RIDERS_BACKUP_RSYNC_DEST}/" \
#       && log_line "[backup] rsync_ok dest=${RIDERS_BACKUP_RSYNC_DEST}" \
#       || log_line "[backup] failed rsync_error dest=${RIDERS_BACKUP_RSYNC_DEST}"
#   fi
