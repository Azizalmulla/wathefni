#!/usr/bin/env bash
# Contained STAGING deploy for held-record communication authority.
# Does NOT touch production. Does NOT change classification flags/workers.
# Uploads authority module + surgically patches staging app/registry/offer only.
set -euo pipefail

VPS_HOST="${WATHEFNI_VPS_HOST:-root@76.13.63.68}"
SSH=(ssh -o BatchMode=yes -o ConnectTimeout=30 "$VPS_HOST")
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
ORCH_SRC="$REPO_ROOT/wathefni-orchestrator"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
LOCAL_STAGE="/tmp/held-notify-authority-staging-$STAMP"
REMOTE_EVIDENCE="/opt/wathefni/staging/staging-evidence/held-notify-authority/$STAMP"
REMOTE_BACKUP="/opt/wathefni/backups/staging-pre-held-notify-authority-$STAMP"
STAGING_ORCH="/opt/wathefni/staging/orchestrator"
# Prefer restoring from the first remediation backup if present (clean pre-authority tree).
PRIOR_BACKUP="${HELD_NOTIFY_PRIOR_BACKUP:-/opt/wathefni/backups/staging-pre-held-notify-authority-20260725T210854Z}"

log() { printf '\n=== %s ===\n' "$*"; }

mkdir -p "$LOCAL_STAGE"
log "source commit + artifact SHA"
COMMIT="$(git -C "$REPO_ROOT" rev-parse HEAD)"
{
  ( cd "$ORCH_SRC" && shasum -a 256 \
      candidate_communication_authority.py \
      test_candidate_communication_authority.py \
      ops/patch-staging-app-held-notify-authority.py \
      ops/patch-staging-registry-held-notify-authority.py \
      ops/patch-staging-offer-held-notify-authority.py )
} | tee "$LOCAL_STAGE/allowlist.sha256"
ARTIFACT_SHA="$(shasum -a 256 "$LOCAL_STAGE/allowlist.sha256" | awk '{print $1}')"
echo "$COMMIT" > "$LOCAL_STAGE/source.commit"
echo "$ARTIFACT_SHA" > "$LOCAL_STAGE/artifact.sha256"
printf 'commit=%s\nartifact=%s\n' "$COMMIT" "$ARTIFACT_SHA"

log "local unit gate"
( cd "$ORCH_SRC" && python3 -m unittest test_candidate_communication_authority.py test_unified_candidates.py test_talent_pool_classification.py -q )

log "fetch staging baselines (prefer prior pre-authority backup)"
"${SSH[@]}" "set -e
  if [[ -f '$PRIOR_BACKUP/app.py.pre' ]]; then
    cp -a '$PRIOR_BACKUP/app.py.pre' /tmp/held-notify-app.pre
    cp -a '$PRIOR_BACKUP/action_registry.py' /tmp/held-notify-registry.pre
    cp -a '$PRIOR_BACKUP/offer_service.py' /tmp/held-notify-offer.pre
    echo BASELINE_FROM_PRIOR_BACKUP
  else
    cp -a $STAGING_ORCH/app.py /tmp/held-notify-app.pre
    cp -a $STAGING_ORCH/action_registry.py /tmp/held-notify-registry.pre
    cp -a $STAGING_ORCH/offer_service.py /tmp/held-notify-offer.pre
    echo BASELINE_FROM_LIVE_STAGING
  fi
"
scp -o BatchMode=yes "$VPS_HOST:/tmp/held-notify-app.pre" "$LOCAL_STAGE/app.py.pre"
scp -o BatchMode=yes "$VPS_HOST:/tmp/held-notify-registry.pre" "$LOCAL_STAGE/action_registry.pre.py"
scp -o BatchMode=yes "$VPS_HOST:/tmp/held-notify-offer.pre" "$LOCAL_STAGE/offer_service.pre.py"

log "surgical patch app + registry + offer"
python3 "$ORCH_SRC/ops/patch-staging-app-held-notify-authority.py" \
  "$LOCAL_STAGE/app.py.pre" "$LOCAL_STAGE/app.py.patched"
python3 "$ORCH_SRC/ops/patch-staging-registry-held-notify-authority.py" \
  "$LOCAL_STAGE/action_registry.pre.py" "$LOCAL_STAGE/action_registry.patched.py"
python3 "$ORCH_SRC/ops/patch-staging-offer-held-notify-authority.py" \
  "$LOCAL_STAGE/offer_service.pre.py" "$LOCAL_STAGE/offer_service.patched.py"
grep -q HELD_COMMUNICATION_AUTHORITY_STAGING_PATCH "$LOCAL_STAGE/app.py.patched"
grep -q HELD_COMMUNICATION_AUTHORITY_STAGING_PATCH "$LOCAL_STAGE/action_registry.patched.py"
grep -q HELD_COMMUNICATION_AUTHORITY_STAGING_PATCH "$LOCAL_STAGE/offer_service.patched.py"
# Staging registry must retain clarify_first compatibility
grep -q 'clarify_first: bool = False' "$LOCAL_STAGE/action_registry.patched.py"
shasum -a 256 \
  "$LOCAL_STAGE/app.py.pre" "$LOCAL_STAGE/app.py.patched" \
  "$LOCAL_STAGE/action_registry.pre.py" "$LOCAL_STAGE/action_registry.patched.py" \
  "$LOCAL_STAGE/offer_service.pre.py" "$LOCAL_STAGE/offer_service.patched.py" \
  | tee "$LOCAL_STAGE/patched.sha256"

log "remote backup"
"${SSH[@]}" "set -e
  mkdir -p '$REMOTE_BACKUP' '$REMOTE_EVIDENCE'
  cp -a $STAGING_ORCH/app.py '$REMOTE_BACKUP/app.py.live_before'
  cp -a $STAGING_ORCH/action_registry.py '$REMOTE_BACKUP/action_registry.live_before' 2>/dev/null || true
  cp -a $STAGING_ORCH/offer_service.py '$REMOTE_BACKUP/offer_service.live_before' 2>/dev/null || true
  cp -a /tmp/held-notify-app.pre '$REMOTE_BACKUP/app.py.pre'
  cp -a /tmp/held-notify-registry.pre '$REMOTE_BACKUP/action_registry.py'
  cp -a /tmp/held-notify-offer.pre '$REMOTE_BACKUP/offer_service.py'
  cp -a /etc/systemd/system/wathefni-orchestrator-staging.service.d/unified-candidates.conf '$REMOTE_BACKUP/' 2>/dev/null || true
  cp -a /etc/systemd/system/wathefni-orchestrator-staging.service.d/talent-pool-classification.conf '$REMOTE_BACKUP/' 2>/dev/null || true
  tmpdump=\$(mktemp /tmp/wathefni-staging-held-notify-XXXX.dump)
  chown postgres:postgres \"\$tmpdump\"
  sudo -u postgres pg_dump -Fc -d wathefni_staging -f \"\$tmpdump\"
  mv \"\$tmpdump\" '$REMOTE_BACKUP/db.dump'
  chmod 640 '$REMOTE_BACKUP/db.dump'
  sha256sum '$REMOTE_BACKUP/db.dump' '$REMOTE_BACKUP/app.py.pre' '$REMOTE_BACKUP/action_registry.py' '$REMOTE_BACKUP/offer_service.py' > '$REMOTE_BACKUP/SHA256SUMS'
  cat > '$REMOTE_BACKUP/ROLLBACK.sh' <<'EOS'
#!/usr/bin/env bash
set -euo pipefail
ROOT=\$(cd \"\$(dirname \"\$0\")\" && pwd)
systemctl stop wathefni-orchestrator-staging.service || true
cp -a \"\$ROOT/app.py.pre\" /opt/wathefni/staging/orchestrator/app.py
cp -a \"\$ROOT/action_registry.py\" /opt/wathefni/staging/orchestrator/action_registry.py
cp -a \"\$ROOT/offer_service.py\" /opt/wathefni/staging/orchestrator/offer_service.py
rm -f /opt/wathefni/staging/orchestrator/candidate_communication_authority.py
rm -f /opt/wathefni/staging/orchestrator/test_candidate_communication_authority.py
systemctl daemon-reload
systemctl restart wathefni-orchestrator-staging.service
curl -sf http://127.0.0.1:8011/health
EOS
  chmod +x '$REMOTE_BACKUP/ROLLBACK.sh'
  echo BACKUP_OK
"

log "upload modules + surgically patched surfaces"
scp -o BatchMode=yes \
  "$ORCH_SRC/candidate_communication_authority.py" \
  "$ORCH_SRC/test_candidate_communication_authority.py" \
  "$LOCAL_STAGE/app.py.patched" \
  "$LOCAL_STAGE/action_registry.patched.py" \
  "$LOCAL_STAGE/offer_service.patched.py" \
  "$LOCAL_STAGE/allowlist.sha256" \
  "$LOCAL_STAGE/artifact.sha256" \
  "$LOCAL_STAGE/source.commit" \
  "$LOCAL_STAGE/patched.sha256" \
  "$VPS_HOST:$REMOTE_EVIDENCE/"

"${SSH[@]}" "set -e
  cp '$REMOTE_EVIDENCE/candidate_communication_authority.py' $STAGING_ORCH/
  cp '$REMOTE_EVIDENCE/test_candidate_communication_authority.py' $STAGING_ORCH/
  cp '$REMOTE_EVIDENCE/app.py.patched' $STAGING_ORCH/app.py
  cp '$REMOTE_EVIDENCE/action_registry.patched.py' $STAGING_ORCH/action_registry.py
  cp '$REMOTE_EVIDENCE/offer_service.patched.py' $STAGING_ORCH/offer_service.py
  systemctl reset-failed wathefni-orchestrator-staging.service || true
  systemctl restart wathefni-orchestrator-staging.service
  for i in \$(seq 1 90); do curl -sf http://127.0.0.1:8011/health >/dev/null && break; sleep 1; done
  curl -sf http://127.0.0.1:8011/health >/dev/null
  test ! -f /opt/wathefni/orchestrator/candidate_communication_authority.py
  grep -q 'clarify_first: bool = False' $STAGING_ORCH/action_registry.py
  grep -q 'HELD_COMMUNICATION_AUTHORITY_STAGING_PATCH' $STAGING_ORCH/app.py
  grep -q 'HELD_COMMUNICATION_AUTHORITY_STAGING_PATCH' $STAGING_ORCH/action_registry.py
  grep -q 'HELD_COMMUNICATION_AUTHORITY_STAGING_PATCH' $STAGING_ORCH/offer_service.py
  grep -q 'TENANTS=WATHEFNI' /etc/systemd/system/wathefni-orchestrator-staging.service.d/talent-pool-classification.conf || true
  grep -q 'WORKERS=off' /etc/systemd/system/wathefni-orchestrator-staging.service.d/talent-pool-classification.conf || true
  echo HELD_NOTIFY_DEPLOY_OK evidence=$REMOTE_EVIDENCE backup=$REMOTE_BACKUP
"

printf '%s\n' "$REMOTE_EVIDENCE" > /tmp/held-notify-staging-evidence.path
printf '%s\n' "$ARTIFACT_SHA" > /tmp/held-notify-staging-artifact.sha
printf '%s\n' "$COMMIT" > /tmp/held-notify-staging-commit.sha
echo "DONE stamp=$STAMP artifact=$ARTIFACT_SHA commit=$COMMIT"
