#!/usr/bin/env bash
# Hybrid Email Phase 1 — production-DARK deploy.
# Additive schema + code only. No Microsoft Mail.Send grants. No tenant mode flips.
set -euo pipefail

VPS_HOST="${WATHEFNI_VPS_HOST:-root@76.13.63.68}"
SSH=(ssh -o BatchMode=yes -o ConnectTimeout=30 "$VPS_HOST")
SCP=(scp -o BatchMode=yes -o ConnectTimeout=30)
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
ORCH_SRC="$REPO_ROOT/wathefni-orchestrator"
DASH_DIST="$REPO_ROOT/apps/wathefni-dashboard/dist"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
REMOTE_BACKUP="/opt/wathefni/backups/production-pre-hybrid-email-phase1-$STAMP"
REMOTE_EVIDENCE="/opt/wathefni/production-evidence/hybrid-email-phase1/$STAMP"
LOCAL_EVIDENCE="$REPO_ROOT/ops/evidence/hybrid-email-phase1-prod-dark-$STAMP"
PROD_ORCH=/opt/wathefni/orchestrator
PROD_DASH=/var/www/wathefni-dashboard
REMOTE_TMP="/tmp/hybrid-email-phase1-$STAMP"

log() { printf '%s %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$*"; }

log "stamp=$STAMP"
mkdir -p "$LOCAL_EVIDENCE"
echo "$STAMP" > "$LOCAL_EVIDENCE/STAMP.txt"
echo "$REMOTE_BACKUP" > "$LOCAL_EVIDENCE/BACKUP_PATH.txt"
git -C "$REPO_ROOT" rev-parse HEAD > "$LOCAL_EVIDENCE/LOCAL_GIT_HEAD.txt" || true
test -d "$DASH_DIST" || { echo "missing dist — run npm run build first"; exit 1; }

# Refuse if mail SP would be enabled accidentally
if "${SSH[@]}" 'tr "\0" "\n" < /proc/$(systemctl show -p MainPID --value wathefni-orchestrator.service)/environ | grep -q "^WATHEFNI_M365_MAIL_CLIENT_ID="'; then
  echo "REFUSING: WATHEFNI_M365_MAIL_CLIENT_ID already set in production"
  exit 2
fi

"${SSH[@]}" 'curl -sS -o /dev/null -w "%{http_code}\n" http://127.0.0.1:8010/health' | tee "$LOCAL_EVIDENCE/health_before.txt"

log "backup $REMOTE_BACKUP"
"${SSH[@]}" "STAMP='$STAMP' BACKUP='$REMOTE_BACKUP' ORCH='$PROD_ORCH' DASH='$PROD_DASH' bash -s" <<'REMOTE'
set -euo pipefail
mkdir -p "$BACKUP/dashboard-dist" "$BACKUP/modules"
for f in app.py action_registry.py; do
  cp -a "$ORCH/$f" "$BACKUP/$f.pre"
done
for f in tenant_email_authority.py microsoft_mail_send.py test_tenant_email_authority.py test_tenant_email_qualification.py prove-hybrid-email-production-dark.py; do
  if [ -f "$ORCH/$f" ]; then cp -a "$ORCH/$f" "$BACKUP/modules/$f.pre"; else touch "$BACKUP/modules/$f.MISSING"; fi
done
rsync -a "$DASH/" "$BACKUP/dashboard-dist/"
sha256sum "$ORCH/app.py" "$ORCH/action_registry.py" > "$BACKUP/PRE_SHA256.txt"
cat > "$BACKUP/ROLLBACK.sh" <<EOF
#!/usr/bin/env bash
set -euo pipefail
ROOT="\$(cd "\$(dirname "\$0")" && pwd)"
ORCH=/opt/wathefni/orchestrator
cp -a "\$ROOT/app.py.pre" "\$ORCH/app.py"
cp -a "\$ROOT/action_registry.py.pre" "\$ORCH/action_registry.py"
for f in tenant_email_authority.py microsoft_mail_send.py test_tenant_email_authority.py test_tenant_email_qualification.py prove-hybrid-email-production-dark.py; do
  if [ -f "\$ROOT/modules/\$f.pre" ]; then
    cp -a "\$ROOT/modules/\$f.pre" "\$ORCH/\$f"
  elif [ -f "\$ROOT/modules/\$f.MISSING" ]; then
    rm -f "\$ORCH/\$f"
  fi
done
rsync -a --delete "\$ROOT/dashboard-dist/" /var/www/wathefni-dashboard/
systemctl restart wathefni-orchestrator.service
for i in 1 2 3 4 5 6 7 8 9 10; do
  sleep 2
  code=\$(curl -sS -o /dev/null -w "%{http_code}" http://127.0.0.1:8010/health || true)
  if [ "\$code" = "200" ]; then break; fi
done
systemctl reload caddy || true
curl -sS -o /dev/null -w "rollback_health=%{http_code}\\n" http://127.0.0.1:8010/health
echo "Rolled back hybrid email phase1 ${STAMP}"
EOF
chmod 755 "$BACKUP/ROLLBACK.sh"
echo "$BACKUP"
REMOTE

log "upload artifacts"
"${SSH[@]}" "mkdir -p $REMOTE_TMP/dashboard-dist $REMOTE_EVIDENCE"
"${SCP[@]}" \
  "$ORCH_SRC/app.py" \
  "$ORCH_SRC/action_registry.py" \
  "$ORCH_SRC/tenant_email_authority.py" \
  "$ORCH_SRC/microsoft_mail_send.py" \
  "$ORCH_SRC/test_tenant_email_authority.py" \
  "$ORCH_SRC/test_tenant_email_qualification.py" \
  "$ORCH_SRC/prove-hybrid-email-production-dark.py" \
  "$VPS_HOST:$REMOTE_TMP/"
rsync -az -e "ssh -o BatchMode=yes" "$DASH_DIST/" "$VPS_HOST:$REMOTE_TMP/dashboard-dist/"

log "apply + schema + smoke"
"${SSH[@]}" "STAMP='$STAMP' TMP='$REMOTE_TMP' ORCH='$PROD_ORCH' DASH='$PROD_DASH' EVIDENCE='$REMOTE_EVIDENCE' BACKUP='$REMOTE_BACKUP' bash -s" <<'REMOTE'
set -euo pipefail
cp -a "$TMP/app.py" "$ORCH/app.py"
cp -a "$TMP/action_registry.py" "$ORCH/action_registry.py"
cp -a "$TMP/tenant_email_authority.py" "$ORCH/tenant_email_authority.py"
cp -a "$TMP/microsoft_mail_send.py" "$ORCH/microsoft_mail_send.py"
cp -a "$TMP/test_tenant_email_authority.py" "$ORCH/test_tenant_email_authority.py"
cp -a "$TMP/test_tenant_email_qualification.py" "$ORCH/test_tenant_email_qualification.py"
cp -a "$TMP/prove-hybrid-email-production-dark.py" "$ORCH/prove-hybrid-email-production-dark.py"
cd "$ORCH"
.venv/bin/python -m py_compile tenant_email_authority.py microsoft_mail_send.py
# Compile-check app via AST only (full import needs service env)
.venv/bin/python -c "import ast; ast.parse(open('app.py').read()); print('app_ast_ok')"
rsync -a --delete "$TMP/dashboard-dist/" "$DASH/"
systemctl restart wathefni-orchestrator.service
for i in 1 2 3 4 5 6 7 8 9 10 11 12; do
  sleep 2
  code=$(curl -sS -o /dev/null -w "%{http_code}" http://127.0.0.1:8010/health || true)
  echo "health_try_$i=$code" | tee -a "$EVIDENCE/health_tries.txt"
  if [ "$code" = "200" ]; then break; fi
done
echo "$code" | tee "$EVIDENCE/health_after_deploy.txt"
test "$code" = "200"
systemctl reload caddy || true

# Additive schema via ensure_schema under service env
PID=$(systemctl show -p MainPID --value wathefni-orchestrator.service)
ENV_FILE=$(mktemp)
tr '\0' '\n' < /proc/$PID/environ > "$ENV_FILE"
set -a
# shellcheck disable=SC1090
source <(grep -E '^(WATHEFNI_|PATH|HOME|VIRTUAL_ENV|PG|DATABASE)' "$ENV_FILE" | sed 's/^/export /')
set +a
rm -f "$ENV_FILE"

cd "$ORCH"
.venv/bin/python - <<'PY' | tee "$EVIDENCE/schema_apply.txt"
import app
import tenant_email_authority as tea
app.ensure_schema(force=True)
# Prove additive tables/columns exist
with app.db_connect() as conn:
    with conn.cursor() as cur:
        cur.execute("""
          SELECT table_name FROM information_schema.tables
          WHERE table_schema='public'
            AND table_name IN ('company_email_settings','company_operational_mailboxes','company_email_domains')
          ORDER BY 1
        """)
        tables = [r["table_name"] if isinstance(r, dict) else r[0] for r in cur.fetchall()]
        cur.execute("""
          SELECT column_name FROM information_schema.columns
          WHERE table_name='outbound_delivery_events'
            AND column_name IN ('sender_mode','visible_from','visible_reply_to','provider','purpose','provider_accept_status')
          ORDER BY 1
        """)
        cols = [r["column_name"] if isinstance(r, dict) else r[0] for r in cur.fetchall()]
        cur.execute("""
          SELECT column_name FROM information_schema.columns
          WHERE table_name='company_email_settings'
            AND column_name='allow_wathefni_emergency_fallback'
        """)
        fb = cur.fetchone()
print("tables=", tables)
print("delivery_cols=", cols)
print("emergency_fallback_col=", bool(fb))
assert set(tables) == {"company_email_settings","company_operational_mailboxes","company_email_domains"}
assert len(cols) == 6
assert fb
print("SCHEMA_ADDITIVE_OK")
PY

# Refuse mail SP in live env
.venv/bin/python - <<'PY' | tee "$EVIDENCE/mail_sp_dark.txt"
import os
assert not (os.environ.get("WATHEFNI_M365_MAIL_CLIENT_ID") or "").strip(), "mail SP must stay unset"
print("mail_sp_unset=OK")
print("calendar_client_present=", bool((os.environ.get("WATHEFNI_M365_CLIENT_ID") or "").strip()))
PY

.venv/bin/python test_tenant_email_authority.py | tee "$EVIDENCE/unit_authority.txt"
.venv/bin/python -m unittest test_tenant_email_qualification.py -v > "$EVIDENCE/qualification.txt" 2>&1
cat "$EVIDENCE/qualification.txt"
grep -q 'FAILED' "$EVIDENCE/qualification.txt" && exit 1
grep -q 'OK' "$EVIDENCE/qualification.txt"
.venv/bin/python prove-hybrid-email-production-dark.py | tee "$EVIDENCE/prove_dark.txt"
grep -q 'ALL_DARK_PROOFS_PASS' "$EVIDENCE/prove_dark.txt"

# Artifact SHAs
sha256sum app.py action_registry.py tenant_email_authority.py microsoft_mail_send.py | tee "$EVIDENCE/POST_SHA256.txt"
# Dashboard marker
python3 - <<'PY' | tee "$EVIDENCE/dashboard_bundle_probe.txt"
from pathlib import Path
root = Path("/var/www/wathefni-dashboard/assets")
hits = []
for p in root.glob("*.js"):
    text = p.read_text(encoding="utf-8", errors="ignore")
    if "Email sending" in text or "Also send an email with calendar invitations" in text or "Allow Wathefni emergency fallback" in text:
        hits.append(p.name)
print("bundle_hits=" + ",".join(hits[:8]) if hits else "bundle_hits=NONE")
print("pass" if hits else "fail")
assert hits
PY
echo "$BACKUP" > "$EVIDENCE/BACKUP_PATH.txt"
REMOTE

log "rollback verification (rollback then re-apply)"
"${SSH[@]}" "BACKUP='$REMOTE_BACKUP' EVIDENCE='$REMOTE_EVIDENCE' TMP='$REMOTE_TMP' ORCH='$PROD_ORCH' DASH='$PROD_DASH' bash -s" <<'REMOTE'
set -euo pipefail
"$BACKUP/ROLLBACK.sh" | tee "$EVIDENCE/rollback_run.txt"
# Confirm pre files restored
sha256sum "$ORCH/app.py" | tee "$EVIDENCE/rollback_app_sha.txt"
# Pre SHA must match backup
pre=$(awk '/app.py/{print $1}' "$BACKUP/PRE_SHA256.txt")
now=$(awk '{print $1}' "$EVIDENCE/rollback_app_sha.txt")
echo "pre=$pre now=$now" | tee "$EVIDENCE/rollback_compare.txt"
test "$pre" = "$now"
echo ROLLBACK_OK | tee "$EVIDENCE/rollback_ok.txt"

# Re-apply forward deploy so production stays on Phase 1 dark
cp -a "$TMP/app.py" "$ORCH/app.py"
cp -a "$TMP/action_registry.py" "$ORCH/action_registry.py"
cp -a "$TMP/tenant_email_authority.py" "$ORCH/tenant_email_authority.py"
cp -a "$TMP/microsoft_mail_send.py" "$ORCH/microsoft_mail_send.py"
cp -a "$TMP/test_tenant_email_authority.py" "$ORCH/test_tenant_email_authority.py"
cp -a "$TMP/test_tenant_email_qualification.py" "$ORCH/test_tenant_email_qualification.py"
cp -a "$TMP/prove-hybrid-email-production-dark.py" "$ORCH/prove-hybrid-email-production-dark.py"
rsync -a --delete "$TMP/dashboard-dist/" "$DASH/"
systemctl restart wathefni-orchestrator.service
for i in 1 2 3 4 5 6 7 8 9 10 11 12; do
  sleep 2
  code=$(curl -sS -o /dev/null -w "%{http_code}" http://127.0.0.1:8010/health || true)
  if [ "$code" = "200" ]; then break; fi
done
echo "$code" | tee "$EVIDENCE/health_after_reapply.txt"
test "$code" = "200"
systemctl reload caddy || true
# Re-run schema ensure (idempotent) + prove under service env
PID=$(systemctl show -p MainPID --value wathefni-orchestrator.service)
ENV_FILE=$(mktemp)
tr '\0' '\n' < /proc/$PID/environ > "$ENV_FILE"
set -a
source <(grep -E '^(WATHEFNI_|PATH|HOME|VIRTUAL_ENV|PG|DATABASE)' "$ENV_FILE" | sed 's/^/export /')
set +a
rm -f "$ENV_FILE"
cd "$ORCH"
.venv/bin/python -c "import app; app.ensure_schema(force=True); print('schema_reaffirm_ok')"
.venv/bin/python prove-hybrid-email-production-dark.py | tee "$EVIDENCE/prove_dark_final.txt"
sha256sum app.py action_registry.py tenant_email_authority.py microsoft_mail_send.py | tee "$EVIDENCE/FINAL_SHA256.txt"
REMOTE

log "pull evidence"
mkdir -p "$LOCAL_EVIDENCE/remote"
rsync -az -e "ssh -o BatchMode=yes" "$VPS_HOST:$REMOTE_EVIDENCE/" "$LOCAL_EVIDENCE/remote/" || true
echo "$STAMP" > "$LOCAL_EVIDENCE/DEPLOY_STAMP.txt"
log "done stamp=$STAMP evidence=$LOCAL_EVIDENCE"
