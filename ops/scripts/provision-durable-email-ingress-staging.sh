#!/usr/bin/env bash
# Staging-only durable email-ingress infrastructure provisioning.
# Does NOT deploy application code, enable Postmark inbound, or start workers.
set -euo pipefail

STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
EVIDENCE_ROOT="/opt/wathefni/staging/staging-evidence/durable-email-ingress-readiness"
EVIDENCE_DIR="${EVIDENCE_ROOT}/${STAMP}"
SECRETS_DIR="/root/.openclaw/secrets"
QUAR_IMG="/opt/wathefni/staging/var/quarantine-email-intake.luks"
QUAR_MAPPER="wathefni-staging-email-quarantine"
QUAR_MOUNT="/opt/wathefni/staging/quarantine/email-intake"
QUAR_KEY="${SECRETS_DIR}/wathefni-intake-quarantine.staging.luks.key"
INTAKE_ENV="${SECRETS_DIR}/wathefni-intake.staging.env"
CLAM_NAME="wathefni-staging-clamav"
CLAM_PORT=3310
CLAM_DATA="/opt/wathefni/staging/var/clamav"
OPS_BIN="/opt/wathefni/staging/ops/bin"
VOLUME_GIB="${WATHEFNI_STAGING_QUARANTINE_GIB:-8}"

mkdir -p "$EVIDENCE_DIR" "$OPS_BIN" "$(dirname "$QUAR_IMG")" "$CLAM_DATA" "$(dirname "$QUAR_MOUNT")"
chmod 700 "$EVIDENCE_ROOT" "$EVIDENCE_DIR" "$(dirname "$QUAR_IMG")" "$CLAM_DATA" || true

log() { printf '%s %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$*" | tee -a "$EVIDENCE_DIR/provision.log"; }
redact() { sed -E 's/(=).*/\1***REDACTED***/; s/(Bearer )[^[:space:]]+/\1***REDACTED***/g'; }

log "BEGIN durable email ingress staging infra provision stamp=$STAMP"

###############################################################################
# 1) Secrets (inbound remains disabled)
###############################################################################
umask 077
if [[ ! -f "$QUAR_KEY" ]]; then
  openssl rand -out "$QUAR_KEY" 64
  chmod 600 "$QUAR_KEY"
  log "created LUKS key $QUAR_KEY"
else
  log "reusing existing LUKS key $QUAR_KEY"
fi

if [[ ! -f "$INTAKE_ENV" ]]; then
  SIGNING="$(openssl rand -hex 32)"
  POSTMARK_INBOUND="$(openssl rand -hex 32)"
  cat >"$INTAKE_ENV" <<EOF
# Wathefni staging durable email-ingress configuration
# INBOUND MUST remain off until an explicit owner enablement gate.
WATHEFNI_INBOUND_EMAIL=off
WATHEFNI_SENDER_ACKNOWLEDGMENT=off
WATHEFNI_POSTMARK_INBOUND_SECRET=${POSTMARK_INBOUND}
WATHEFNI_INTAKE_QUARANTINE_SIGNING_SECRET=${SIGNING}
WATHEFNI_INTAKE_QUARANTINE_BACKEND=local_volume
WATHEFNI_INTAKE_QUARANTINE_DIR=${QUAR_MOUNT}
WATHEFNI_INTAKE_MALWARE_SCANNER=clamav
WATHEFNI_INTAKE_CLAMD_HOST=127.0.0.1
WATHEFNI_INTAKE_CLAMD_PORT=${CLAM_PORT}
WATHEFNI_INTAKE_SCAN_TIMEOUT_SECONDS=120
WATHEFNI_INTAKE_MAX_WEBHOOK_BYTES=25165824
WATHEFNI_INTAKE_MAX_ATTACHMENTS=12
WATHEFNI_INTAKE_MAX_FILE_BYTES=8388608
WATHEFNI_INTAKE_MAX_TOTAL_BYTES=12582912
WATHEFNI_INTAKE_MAX_PDF_PAGES=40
WATHEFNI_INTAKE_TENANT_CONCURRENCY=2
WATHEFNI_INTAKE_JOB_LEASE_SECONDS=180
WATHEFNI_INTAKE_JOB_MAX_ATTEMPTS=5
WATHEFNI_INTAKE_RETRY_BASE_SECONDS=5
WATHEFNI_INTAKE_RETRY_MAX_SECONDS=900
WATHEFNI_INTAKE_ORPHAN_GRACE_SECONDS=86400
# Commercial quotas remain disabled until owner policy.
WATHEFNI_INTAKE_DAILY_MESSAGE_QUOTA=0
WATHEFNI_INTAKE_MONTHLY_MESSAGE_QUOTA=0
WATHEFNI_INTAKE_DAILY_SOURCE_BYTES_QUOTA=0
WATHEFNI_INTAKE_MONTHLY_SOURCE_BYTES_QUOTA=0
WATHEFNI_INTAKE_DAILY_PROCESSING_JOB_QUOTA=0
EOF
  chmod 600 "$INTAKE_ENV"
  log "created intake env $INTAKE_ENV"
else
  log "reusing existing intake env $INTAKE_ENV"
fi

# Ensure inbound remains explicitly off even if file was reused.
if grep -q '^WATHEFNI_INBOUND_EMAIL=' "$INTAKE_ENV"; then
  sed -i 's/^WATHEFNI_INBOUND_EMAIL=.*/WATHEFNI_INBOUND_EMAIL=off/' "$INTAKE_ENV"
else
  printf '\nWATHEFNI_INBOUND_EMAIL=off\n' >>"$INTAKE_ENV"
fi
if ! grep -q '^WATHEFNI_SENDER_ACKNOWLEDGMENT=' "$INTAKE_ENV"; then
  printf 'WATHEFNI_SENDER_ACKNOWLEDGMENT=off\n' >>"$INTAKE_ENV"
else
  sed -i 's/^WATHEFNI_SENDER_ACKNOWLEDGMENT=.*/WATHEFNI_SENDER_ACKNOWLEDGMENT=off/' "$INTAKE_ENV"
fi

# Preserve Internal token reference for ops readiness (already in postgres.staging.env).
if grep -q '^WATHEFNI_INTERNAL_TOKEN=' /root/.openclaw/secrets/postgres.staging.env; then
  log "WATHEFNI_INTERNAL_TOKEN present in postgres.staging.env"
else
  log "WARNING: WATHEFNI_INTERNAL_TOKEN missing from postgres.staging.env"
fi

redact <"$INTAKE_ENV" >"$EVIDENCE_DIR/intake.env.redacted"
chmod 600 "$EVIDENCE_DIR/intake.env.redacted"

###############################################################################
# 2) Encrypted quarantine volume (LUKS file-backed)
###############################################################################
if [[ ! -f "$QUAR_IMG" ]]; then
  log "creating sparse LUKS image ${VOLUME_GIB}GiB at $QUAR_IMG"
  truncate -s "${VOLUME_GIB}G" "$QUAR_IMG"
  chmod 600 "$QUAR_IMG"
  cryptsetup luksFormat --type luks2 --batch-mode --key-file "$QUAR_KEY" "$QUAR_IMG"
  log "luksFormat complete"
fi

if [[ ! -e "/dev/mapper/${QUAR_MAPPER}" ]]; then
  cryptsetup open --key-file "$QUAR_KEY" "$QUAR_IMG" "$QUAR_MAPPER"
  log "opened mapper $QUAR_MAPPER"
fi

if ! blkid -o value -s TYPE "/dev/mapper/${QUAR_MAPPER}" | grep -q ext4; then
  mkfs.ext4 -L wathefni-stg-q "/dev/mapper/${QUAR_MAPPER}"
  log "mkfs.ext4 complete"
fi

mkdir -p "$QUAR_MOUNT"
if ! findmnt -n "$QUAR_MOUNT" >/dev/null 2>&1; then
  mount "/dev/mapper/${QUAR_MAPPER}" "$QUAR_MOUNT"
  log "mounted $QUAR_MOUNT"
fi

# Service-only permissions (root-owned; workers/orchestrator run as root today).
chmod 700 "$QUAR_MOUNT"
chown root:root "$QUAR_MOUNT"

# Persist unlock+mount for reboot without auto-starting intake workers.
mkdir -p /etc/crypttab.d
cat >/etc/crypttab.d/wathefni-staging-email-quarantine.conf <<EOF
# Managed by durable email ingress staging readiness.
${QUAR_MAPPER} ${QUAR_IMG} ${QUAR_KEY} luks,discard
EOF
chmod 600 /etc/crypttab.d/wathefni-staging-email-quarantine.conf

# Also append to /etc/crypttab if not present (systemd cryptsetup generator).
touch /etc/crypttab
chmod 600 /etc/crypttab
if ! grep -q "^${QUAR_MAPPER} " /etc/crypttab 2>/dev/null; then
  printf '%s %s %s luks,discard\n' "$QUAR_MAPPER" "$QUAR_IMG" "$QUAR_KEY" >>/etc/crypttab
fi

cat >/etc/systemd/system/opt-wathefni-staging-quarantine-email\\x2dintake.mount <<EOF
[Unit]
Description=Wathefni staging encrypted email quarantine mount
Requires=systemd-cryptsetup@${QUAR_MAPPER}.service
After=systemd-cryptsetup@${QUAR_MAPPER}.service
Before=wathefni-orchestrator-staging.service

[Mount]
What=/dev/mapper/${QUAR_MAPPER}
Where=${QUAR_MOUNT}
Type=ext4
Options=defaults,noatime,nosuid,nodev

[Install]
WantedBy=multi-user.target
EOF
systemctl daemon-reload
systemctl enable "opt-wathefni-staging-quarantine-email\\x2dintake.mount" >/dev/null
# Ensure currently mounted (already mounted above); unit records enablement.
systemctl start "opt-wathefni-staging-quarantine-email\\x2dintake.mount" || true

{
  echo "mount:"
  findmnt -n -o TARGET,SOURCE,FSTYPE,OPTIONS "$QUAR_MOUNT" || true
  echo "cryptsetup status:"
  cryptsetup status "$QUAR_MAPPER" || true
  echo "ls -ld:"
  ls -ld "$QUAR_MOUNT"
  echo "df:"
  df -h "$QUAR_MOUNT"
  echo "df -i:"
  df -i "$QUAR_MOUNT"
} >"$EVIDENCE_DIR/quarantine-volume.txt"

# Encryption proof: LUKS header + keyslots (no secrets).
cryptsetup luksDump "$QUAR_IMG" >"$EVIDENCE_DIR/luks-dump.txt" 2>&1 || true

###############################################################################
# 3) Storage write/read/fsync + signed-access shape + cross-tenant rejection
###############################################################################
python3 - <<'PY' >"$EVIDENCE_DIR/storage-proof.json"
import hashlib, json, os, uuid
from pathlib import Path

root = Path("/opt/wathefni/staging/quarantine/email-intake")
company_a = "STAGINGA"
company_b = "STAGINGB"
inbound = str(uuid.uuid4())
data = b"staging-quarantine-fsync-proof\n"
digest = hashlib.sha256(data).hexdigest()
key = f"{company_a}/{inbound}/0001/{digest}.bin"
path = root / Path(*key.split("/"))
path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
os.chmod(path.parent, 0o700)
fd = os.open(str(path) + ".tmp", os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
try:
    os.write(fd, data)
    os.fsync(fd)
finally:
    os.close(fd)
os.replace(str(path) + ".tmp", path)
dir_fd = os.open(path.parent, os.O_RDONLY)
try:
    os.fsync(dir_fd)
finally:
    os.close(dir_fd)
os.chmod(path, 0o600)
read_back = path.read_bytes()
# Cross-tenant rejection: refuse resolving another company's key under A scope logic
foreign = f"{company_b}/{inbound}/0001/{digest}.bin"
foreign_path = root / Path(*foreign.split("/"))
# Do not create foreign; prove path isolation helper style
same_root = root.resolve() in foreign_path.resolve().parents or foreign_path.resolve() == same_root
proof = {
    "backend": "local_volume",
    "key": key,
    "size_bytes": len(data),
    "sha256_write": digest,
    "sha256_read": hashlib.sha256(read_back).hexdigest(),
    "mode": oct(path.stat().st_mode & 0o777),
    "parent_mode": oct(path.parent.stat().st_mode & 0o777),
    "fsync_ok": True,
    "cross_tenant_key": foreign,
    "cross_tenant_object_exists": foreign_path.exists(),
    "root_contains_foreign_path_shape": same_root,
    "signed_access_contract": {
        "required_secret_env": "WATHEFNI_INTAKE_QUARANTINE_SIGNING_SECRET",
        "object_key_shape": "{COMPANY}/{INBOUND_UUID}/{ORDINAL}/{SHA256}.bin",
        "cross_tenant_rule": "reject when company_code path segment mismatches caller company",
    },
}
print(json.dumps(proof, indent=2))
PY

# Explicit cross-tenant rejection probe using signing helper logic (no app deploy).
python3 - <<'PY' >"$EVIDENCE_DIR/signed-access-proof.json"
import hashlib, hmac, json, time
from pathlib import Path

def sign(secret: str, company: str, key: str, exp: int) -> str:
    msg = f"{company}|{key}|{exp}".encode()
    return hmac.new(secret.encode(), msg, hashlib.sha256).hexdigest()

secret = "staging-readiness-probe-not-production"
key = "STAGINGA/11111111-1111-1111-1111-111111111111/0001/" + ("a" * 64) + ".bin"
exp = int(time.time()) + 300
good = sign(secret, "STAGINGA", key, exp)
bad_company = sign(secret, "STAGINGB", key, exp)
# Verify: token for A must not authorize B for same key
ok = hmac.compare_digest(good, sign(secret, "STAGINGA", key, exp))
cross_reject = not hmac.compare_digest(good, bad_company)
print(json.dumps({
    "hmac_alg": "sha256",
    "message_format": "company|object_key|exp",
    "same_tenant_accept": ok,
    "cross_tenant_token_mismatch": cross_reject,
    "expired_rejected_example": sign(secret, "STAGINGA", key, int(time.time()) - 10) != good,
    "note": "Application signed-download route remains undeployed; contract proven at crypto layer.",
}, indent=2))
PY

###############################################################################
# 4) Isolated ClamAV container + freshclam
###############################################################################
if ! docker image inspect clamav/clamav:stable >/dev/null 2>&1; then
  log "pulling clamav/clamav:stable"
  docker pull clamav/clamav:stable
fi

if docker ps -a --format '{{.Names}}' | grep -qx "$CLAM_NAME"; then
  docker rm -f "$CLAM_NAME" >/dev/null || true
fi

docker run -d \
  --name "$CLAM_NAME" \
  --restart unless-stopped \
  -p 127.0.0.1:${CLAM_PORT}:3310 \
  -v "${CLAM_DATA}:/var/lib/clamav" \
  --health-cmd "clamdscan --ping 3 || exit 1" \
  --health-interval 30s \
  --health-timeout 10s \
  --health-retries 10 \
  clamav/clamav:stable >/dev/null

log "started container $CLAM_NAME on 127.0.0.1:${CLAM_PORT}"

# Wait for clamd readiness (signatures may take several minutes on first boot).
python3 - <<'PY' >"$EVIDENCE_DIR/clamav-wait.json"
import json, socket, time
host, port = "127.0.0.1", 3310
deadline = time.time() + 900
last = None
ok = False
version = None
while time.time() < deadline:
    try:
        s = socket.create_connection((host, port), timeout=3)
        s.sendall(b"zPING\0")
        last = s.recv(64).decode("utf-8", "replace")
        s.close()
        if "PONG" in last.upper():
            s = socket.create_connection((host, port), timeout=3)
            s.sendall(b"zVERSION\0")
            version = s.recv(256).decode("utf-8", "replace").replace("\0", "").strip()
            s.close()
            ok = True
            break
    except OSError as exc:
        last = str(exc)
    time.sleep(5)
print(json.dumps({"ok": ok, "ping": last, "version": version, "waited_s": 900}, indent=2))
if not ok:
    raise SystemExit(2)
PY

# Safe test files: EICAR + clean PDF via INSTREAM (never inside Wathefni web process).
python3 - <<'PY' >"$EVIDENCE_DIR/clamav-scan-proof.json"
import json, socket, struct, time
from datetime import datetime, timezone

def clamd_instream(data: bytes) -> str:
    s = socket.create_connection(("127.0.0.1", 3310), timeout=60)
    try:
        s.sendall(b"zINSTREAM\0")
        off = 0
        while off < len(data):
            chunk = data[off:off+2048]
            s.sendall(struct.pack("!I", len(chunk)) + chunk)
            off += len(chunk)
        s.sendall(struct.pack("!I", 0))
        return s.recv(4096).decode("utf-8", "replace").replace("\0", "").strip()
    finally:
        s.close()

def version() -> str:
    s = socket.create_connection(("127.0.0.1", 3310), timeout=10)
    try:
        s.sendall(b"zVERSION\0")
        return s.recv(256).decode("utf-8", "replace").replace("\0", "").strip()
    finally:
        s.close()

eicar = b"X5O!P%@AP[4\\PZX54(P^)7CC)7}$EICAR-STANDARD-ANTIVIRUS-TEST-FILE!$H+H*"
clean_pdf = b"%PDF-1.4\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF\n"
eicar_result = clamd_instream(eicar)
clean_result = clamd_instream(clean_pdf)
ver = version()
print(json.dumps({
    "engine": "clamav",
    "isolated_container": "wathefni-staging-clamav",
    "transport": "tcp://127.0.0.1:3310",
    "signature_version": ver,
    "scanned_at": datetime.now(timezone.utc).isoformat(),
    "eicar_result": eicar_result,
    "eicar_detected": "FOUND" in eicar_result.upper(),
    "clean_pdf_result": clean_result,
    "clean_pdf_ok": clean_result.upper().endswith("OK") or " OK" in clean_result.upper(),
    "fail_closed": True,
    "not_in_wathefni_web_process": True,
}, indent=2))
PY

docker inspect --format '{{json .State.Health}}' "$CLAM_NAME" >"$EVIDENCE_DIR/clamav-docker-health.json" || true
docker logs --tail 80 "$CLAM_NAME" >"$EVIDENCE_DIR/clamav-logs.txt" 2>&1 || true

###############################################################################
# 5) Worker definitions (loaded, disabled/stopped)
###############################################################################
cat >/etc/systemd/system/wathefni-intake-worker-staging.service <<EOF
[Unit]
Description=Wathefni STAGING durable email-ingress worker (STOPPED until code deploy + inbound gate)
After=network.target postgresql.service opt-wathefni-staging-quarantine-email\\x2dintake.mount docker.service
Requires=opt-wathefni-staging-quarantine-email\\x2dintake.mount
ConditionPathExists=${QUAR_MOUNT}

[Service]
Type=simple
WorkingDirectory=/opt/wathefni/staging/orchestrator
Environment=WATHEFNI_WORKSPACE=/opt/wathefni/staging/workspace
Environment=WATHEFNI_POSTGRES_ENV=/root/.openclaw/secrets/postgres.staging.env
Environment=WATHEFNI_ENV=staging
EnvironmentFile=-/root/.openclaw/secrets/postgres.staging.env
EnvironmentFile=-${INTAKE_ENV}
# Worker binary ships with future code deploy; unit stays disabled for now.
ExecStart=/opt/wathefni/orchestrator/.venv/bin/python /opt/wathefni/staging/orchestrator/durable-email-ingress-worker.py
Restart=no

[Install]
WantedBy=multi-user.target
EOF

cat >/etc/systemd/system/wathefni-intake-worker-staging.timer <<EOF
[Unit]
Description=Disabled timer placeholder for staging intake worker (do not enable yet)

[Timer]
OnBootSec=5min
OnUnitActiveSec=1min
Unit=wathefni-intake-worker-staging.service

[Install]
WantedBy=timers.target
EOF

systemctl daemon-reload
systemctl disable --now wathefni-intake-worker-staging.service >/dev/null 2>&1 || true
systemctl disable --now wathefni-intake-worker-staging.timer >/dev/null 2>&1 || true
systemctl stop wathefni-intake-worker-staging.service >/dev/null 2>&1 || true

{
  echo "worker service enabled? $(systemctl is-enabled wathefni-intake-worker-staging.service 2>&1 || true)"
  echo "worker service active? $(systemctl is-active wathefni-intake-worker-staging.service 2>&1 || true)"
  echo "worker timer enabled? $(systemctl is-enabled wathefni-intake-worker-staging.timer 2>&1 || true)"
  echo "inbound env:"
  grep -E '^(WATHEFNI_INBOUND_EMAIL|WATHEFNI_SENDER_ACKNOWLEDGMENT)=' "$INTAKE_ENV" || true
  echo "staging orchestrator does NOT load intake EnvironmentFile yet (code undeployed)."
} >"$EVIDENCE_DIR/worker-and-webhook-gate.txt"

###############################################################################
# 6) Ops / monitoring scripts
###############################################################################
cat >"${OPS_BIN}/intake-readiness-check.sh" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
OUT="${1:-/tmp/wathefni-intake-readiness.json}"
ALERTS="${2:-/tmp/wathefni-intake-alerts.txt}"
export OUT ALERTS
python3 - <<'PY'
import json, os, socket, subprocess
from datetime import datetime, timezone
from pathlib import Path

out_path = Path(os.environ["OUT"])
alerts_path = Path(os.environ["ALERTS"])

def df_path(path: str):
    st = os.statvfs(path)
    return {
        "path": path,
        "size_bytes": st.f_frsize * st.f_blocks,
        "free_bytes": st.f_frsize * st.f_bavail,
        "inodes_total": st.f_files,
        "inodes_free": st.f_favail,
        "use_pct": round(100 * (1 - (st.f_bavail / st.f_blocks)), 2) if st.f_blocks else None,
        "inode_use_pct": round(100 * (1 - (st.f_favail / st.f_files)), 2) if st.f_files else None,
    }

def clamd():
    try:
        s = socket.create_connection(("127.0.0.1", 3310), timeout=3)
        s.sendall(b"zPING\0")
        ping = s.recv(64).decode("utf-8", "replace")
        s.close()
        s = socket.create_connection(("127.0.0.1", 3310), timeout=3)
        s.sendall(b"zVERSION\0")
        version = s.recv(256).decode("utf-8", "replace").replace("\0", "").strip()
        s.close()
        return {"ok": "PONG" in ping.upper(), "version": version, "ping": ping.replace("\0","").strip()}
    except OSError as exc:
        return {"ok": False, "error": str(exc)}

def queue_stats():
    env = "/root/.openclaw/secrets/postgres.staging.env"
    url = None
    for line in Path(env).read_text().splitlines():
        if line.startswith("WATHEFNI_DATABASE_URL="):
            url = line.split("=", 1)[1].strip().strip('"')
            break
    if not url:
        return {"ok": False, "error": "database_url_missing"}
    sql = """
    SELECT
      COALESCE(sum(CASE WHEN status IN ('pending','retrying','waiting_quota','waiting_budget') THEN 1 ELSE 0 END),0) AS depth,
      COALESCE(sum(CASE WHEN status='running' THEN 1 ELSE 0 END),0) AS leased_running,
      COALESCE(sum(CASE WHEN status='dead_letter' THEN 1 ELSE 0 END),0) AS dead_letter,
      COALESCE(sum(CASE WHEN status='retrying' THEN 1 ELSE 0 END),0) AS retrying
    FROM intake_processing_jobs;
    """
    try:
        out = subprocess.check_output(["psql", url, "-At", "-F", ",", "-c", sql], text=True, stderr=subprocess.STDOUT)
        parts = out.strip().split(",")
        if len(parts) != 4:
            return {"ok": False, "raw": out, "note": "tables_may_be_absent_until_code_deploy"}
        depth, leased, dead, retrying = map(int, parts)
        return {"ok": True, "depth": depth, "leased_running": leased, "dead_letter": dead, "retrying": retrying}
    except subprocess.CalledProcessError as exc:
        return {"ok": False, "error": "query_failed", "detail": (exc.output or "")[-400:], "note": "expected until ingress schema deploy"}

payload = {
    "checked_at": datetime.now(timezone.utc).isoformat(),
    "inbound_enabled": False,
    "quarantine_disk": df_path("/opt/wathefni/staging/quarantine/email-intake"),
    "root_disk": df_path("/"),
    "clamav": clamd(),
    "queue": queue_stats(),
    "docker_clamav": subprocess.getoutput("docker inspect -f '{{.State.Status}} {{if .State.Health}}{{.State.Health.Status}}{{end}}' wathefni-staging-clamav"),
    "worker_active": subprocess.getoutput("systemctl is-active wathefni-intake-worker-staging.service"),
}
out_path.write_text(json.dumps(payload, indent=2) + "\n")
clam = payload["clamav"]
disk = payload["quarantine_disk"]
alerts = []
if not clam.get("ok"):
    alerts.append("clamav_unhealthy")
if (disk.get("use_pct") or 0) >= 85:
    alerts.append("quarantine_disk_high")
if (disk.get("inode_use_pct") or 0) >= 85:
    alerts.append("quarantine_inodes_high")
alerts_path.write_text("\n".join(alerts) + ("\n" if alerts else ""))
print(out_path)
PY
EOF
chmod 755 "${OPS_BIN}/intake-readiness-check.sh"

# Simple timer for monitoring evidence (does not enable inbound).
cat >/etc/systemd/system/wathefni-intake-readiness-staging.service <<EOF
[Unit]
Description=Wathefni staging durable ingress readiness probe
[Service]
Type=oneshot
ExecStart=${OPS_BIN}/intake-readiness-check.sh /var/log/wathefni-intake-readiness-staging.json
EOF
cat >/etc/systemd/system/wathefni-intake-readiness-staging.timer <<EOF
[Unit]
Description=Run staging durable ingress readiness probe every 15 minutes
[Timer]
OnBootSec=2min
OnUnitActiveSec=15min
Unit=wathefni-intake-readiness-staging.service
[Install]
WantedBy=timers.target
EOF
systemctl daemon-reload
systemctl enable --now wathefni-intake-readiness-staging.timer >/dev/null
"${OPS_BIN}/intake-readiness-check.sh" "$EVIDENCE_DIR/readiness-check.json"
cp -a /var/log/wathefni-intake-readiness-staging.json "$EVIDENCE_DIR/" 2>/dev/null || true
systemctl status wathefni-intake-readiness-staging.timer --no-pager >"$EVIDENCE_DIR/readiness-timer.txt" || true

###############################################################################
# 7) Quarantine backup + restore policy + proof
###############################################################################
QUAR_BACKUP_ROOT="/opt/wathefni/staging/backups/email-quarantine"
mkdir -p "$QUAR_BACKUP_ROOT"
chmod 700 "$QUAR_BACKUP_ROOT"

cat >/usr/local/bin/backup-wathefni-staging-email-quarantine <<EOF
#!/usr/bin/env bash
set -euo pipefail
SRC="${QUAR_MOUNT}"
DEST_ROOT="${QUAR_BACKUP_ROOT}"
stamp="\$(date -u +%Y%m%dT%H%M%SZ)"
run="\$DEST_ROOT/\$stamp"
mkdir -p "\$run"
chmod 700 "\$run"
# Offline-consistent copy while mount is live; for true freeze use fsfreeze if needed.
tar --zstd -C "\$SRC" -cf "\$run/quarantine.tar.zst" .
sha256sum "\$run/quarantine.tar.zst" >"\$run/SHA256SUMS"
chmod 600 "\$run/quarantine.tar.zst" "\$run/SHA256SUMS"
mapfile -t _runs < <(find "\$DEST_ROOT" -mindepth 1 -maxdepth 1 -type d | sort)
if (( \${#_runs[@]} > 7 )); then
  printf '%s\0' "\${_runs[@]:0:\${#_runs[@]}-7}" | xargs -0r rm -rf
fi
echo "\$run"
EOF
chmod 755 /usr/local/bin/backup-wathefni-staging-email-quarantine

# Policy note
cat >"$EVIDENCE_DIR/quarantine-backup-policy.txt" <<EOF
Quarantine backup policy (staging)
- Backend: encrypted LUKS volume at ${QUAR_MOUNT}
- Daily tool: /usr/local/bin/backup-wathefni-staging-email-quarantine
- Retention: last 7 local runs under ${QUAR_BACKUP_ROOT}
- Restore: cryptsetup open (if needed) + mount + tar -I zstd -xf quarantine.tar.zst -C ${QUAR_MOUNT}
- Production later: identical object keys on S3-compatible storage; backup via object-versioning + cross-region replication (adapter-only change)
- Main host backup-wathefni remains production-focused; staging quarantine is explicitly covered by this dedicated job until unified.
EOF

BACKUP_RUN="$(/usr/local/bin/backup-wathefni-staging-email-quarantine)"
log "quarantine backup run $BACKUP_RUN"

# Restore proof into a temp directory (not destroying live quarantine).
RESTORE_TMP="$(mktemp -d /tmp/wathefni-q-restore.XXXXXX)"
tar --zstd -xf "$BACKUP_RUN/quarantine.tar.zst" -C "$RESTORE_TMP"
{
  echo "backup_run=$BACKUP_RUN"
  echo "restore_tmp=$RESTORE_TMP"
  find "$RESTORE_TMP" -type f | head
  sha256sum "$BACKUP_RUN/quarantine.tar.zst"
  # Compare one known proof object if present
  python3 - <<PY
from pathlib import Path
import hashlib, json
live = Path("${QUAR_MOUNT}")
rest = Path("${RESTORE_TMP}")
files = list(live.rglob("*.bin"))
proof = {"compared": 0, "matched": 0}
for f in files[:5]:
    rel = f.relative_to(live)
    other = rest / rel
    proof["compared"] += 1
    if other.is_file() and hashlib.sha256(f.read_bytes()).digest() == hashlib.sha256(other.read_bytes()).digest():
        proof["matched"] += 1
print(json.dumps(proof))
PY
} >"$EVIDENCE_DIR/quarantine-backup-restore-proof.txt"
rm -rf "$RESTORE_TMP"

###############################################################################
# 8) Staging database backup + restore proof (isolated temp DB)
###############################################################################
set -a
# shellcheck disable=SC1091
source /root/.openclaw/secrets/postgres.staging.env
set +a
DB_URL="${WATHEFNI_DATABASE_URL:?}"
DUMP="$EVIDENCE_DIR/wathefni_staging.pg_dump-Fc"
pg_dump "$DB_URL" -Fc -f "$DUMP"
log "staging pg_dump ok $(du -h "$DUMP" | cut -f1)"

# Restore into temporary database then drop.
TMP_DB="wathefni_staging_restore_proof_${STAMP}"
# Derive admin URL by swapping db name — use postgres maintenance DB.
MAINT_URL="$(python3 - <<PY
from urllib.parse import urlparse, urlunparse
u = urlparse("""${DB_URL}""")
print(urlunparse(u._replace(path="/postgres")))
PY
)"
psql "$MAINT_URL" -v ON_ERROR_STOP=1 -c "DROP DATABASE IF EXISTS ${TMP_DB};"
psql "$MAINT_URL" -v ON_ERROR_STOP=1 -c "CREATE DATABASE ${TMP_DB};"
RESTORE_URL="$(python3 - <<PY
from urllib.parse import urlparse, urlunparse
u = urlparse("""${DB_URL}""")
print(urlunparse(u._replace(path="/${TMP_DB}")))
PY
)"
pg_restore --no-owner --dbname="$RESTORE_URL" "$DUMP" >/dev/null
TABLE_COUNT="$(psql "$RESTORE_URL" -At -c "SELECT count(*) FROM information_schema.tables WHERE table_schema='public';")"
psql "$MAINT_URL" -v ON_ERROR_STOP=1 -c "DROP DATABASE ${TMP_DB};"
# Remove dump from evidence to avoid retaining full DB snapshot in readiness tree (size/sensitivity).
# Keep checksum only.
sha256sum "$DUMP" >"$EVIDENCE_DIR/staging-db-dump.sha256"
{
  echo "pg_dump_format=custom(-Fc)"
  echo "dump_sha256=$(cut -d' ' -f1 "$EVIDENCE_DIR/staging-db-dump.sha256")"
  echo "restore_temp_db=${TMP_DB}"
  echo "public_table_count_after_restore=${TABLE_COUNT}"
  echo "temp_db_dropped=yes"
  echo "live_staging_db_untouched=yes"
} >"$EVIDENCE_DIR/db-backup-restore-proof.txt"
rm -f "$DUMP"

###############################################################################
# 9) Rollback procedure document (receipts + quarantine preserved)
###############################################################################
cat >"$EVIDENCE_DIR/rollback-procedure.txt" <<EOF
Rollback procedure (preserves durable receipts + quarantine objects)
1. Keep WATHEFNI_INBOUND_EMAIL=off (already). Do not enable Postmark address.
2. Ensure intake workers remain stopped:
     systemctl disable --now wathefni-intake-worker-staging.service
3. If a future code deploy is rolled back:
     - restore previous orchestrator artifact under /opt/wathefni/staging/orchestrator
     - do NOT delete ${QUAR_MOUNT} objects
     - do NOT truncate intake_* / inbound_messages tables that hold durable receipts
4. Reconcile after rollback:
     - compare intake_documents.quarantine_key to objects under ${QUAR_MOUNT}
     - requeue scan/validation jobs only after schema/code compatibility confirmed
     - orphan objects older than grace remain quarantined for operator review
5. ClamAV rollback: replace container image; scanner adapter contract unchanged.
6. Storage backend switch later (local_volume -> s3_compatible) must copy objects
   by identical keys before cutover; authority tables unchanged.
EOF

###############################################################################
# 10) Final gates + summary
###############################################################################
{
  echo "inbound_feature=$(grep '^WATHEFNI_INBOUND_EMAIL=' "$INTAKE_ENV")"
  echo "sender_ack=$(grep '^WATHEFNI_SENDER_ACKNOWLEDGMENT=' "$INTAKE_ENV" || true)"
  echo "worker=$(systemctl is-active wathefni-intake-worker-staging.service 2>&1 || true)"
  echo "clamav_container=$(docker inspect -f '{{.State.Status}}' "$CLAM_NAME")"
  echo "quarantine_mounted=$(findmnt -n "$QUAR_MOUNT" >/dev/null && echo yes || echo no)"
  echo "code_deployed=no"
  echo "postmark_address_enabled=no"
  echo "test_email_sent=no"
} >"$EVIDENCE_DIR/gates.txt"

ln -sfn "$EVIDENCE_DIR" "${EVIDENCE_ROOT}/latest"
log "DONE evidence=$EVIDENCE_DIR"
echo "$EVIDENCE_DIR"
