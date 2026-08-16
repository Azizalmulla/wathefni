#!/usr/bin/env bash
# Guarded production-dark deployment for Talent Pool Classification plus the
# staging-qualified held-record communication authority safety gate.
#
# Classification remains fully OFF: master, tenant allowlist, workers, UI,
# manual execution, and schema runtime flag. This script applies additive
# schema/global taxonomy definitions directly, but performs no classification.
set -euo pipefail

VPS_HOST="${WATHEFNI_VPS_HOST:-root@76.13.63.68}"
SSH=(ssh -o BatchMode=yes -o ConnectTimeout=30 "$VPS_HOST")
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
PACKAGE="${1:-$(cat /tmp/tpc-prod-dark.package.path 2>/dev/null || true)}"

SOURCE_COMMIT="40a4e2621f4818bf7c0f6ce3642032297bfbe7b2"
CLASSIFICATION_ARTIFACT="052743494cbc47efed07e999913e8b8ddbf509124ea3f17efac76c467a3fa973"
HELD_AUTHORITY_ARTIFACT="a94c4178721b247201f5186817bd461a44b628cd95d0a187daf709ca50d1811e"
COMPOSITE_ARTIFACT="3c894921621fb6b6082e087340f421722718714c488cb4f10c21c482cb972d64"

STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
PROD_ORCH="/opt/wathefni/orchestrator"
REMOTE_EVIDENCE="/opt/wathefni/production-evidence/talent-pool-classification-dark/$STAMP"
REMOTE_BACKUP="/opt/wathefni/backups/production-pre-talent-pool-classification-dark-$STAMP"
STAGING_APP_SHA="54f2be02ca9856a307d2946c5008c7d4d3cda248f60c343f2e2000281c6cad54"
STAGING_REGISTRY_SHA="b7992797bd6db01dd2461c3803e80089e10de91248cddaeecf1f8a2cba8d2bfb"
STAGING_OFFER_SHA="74c14abe376bbe6ddc322e64d58aa64270eeb948cb53dce252faa5e92c57162a"

log() { printf '\n=== %s ===\n' "$*"; }
refuse() { echo "REFUSING: $*" >&2; exit 2; }

[[ -n "$PACKAGE" && -d "$PACKAGE/final" ]] || refuse "package missing: $PACKAGE"
[[ "$(cat "$PACKAGE/final/SOURCE-COMMIT")" == "$SOURCE_COMMIT" ]] || refuse "source commit mismatch"
[[ "$(cat "$PACKAGE/final/PRODUCTION-DARK-ARTIFACT.sha256")" == "$COMPOSITE_ARTIFACT" ]] || refuse "composite artifact mismatch"
(cd "$PACKAGE/final" && sha256sum -c DEPLOY-MANIFEST.sha256)
grep -qx "classification_artifact=$CLASSIFICATION_ARTIFACT" "$PACKAGE/final/IDENTITY.txt"
grep -qx "held_authority_artifact=$HELD_AUTHORITY_ARTIFACT" "$PACKAGE/final/IDENTITY.txt"

log "predeployment fail-closed checks"
"${SSH[@]}" "set -euo pipefail
  test \$(curl -sf -o /dev/null -w '%{http_code}' http://127.0.0.1:8010/health) = 200
  test ! -f '$PROD_ORCH/talent_pool_classification.py'
  test ! -f '$PROD_ORCH/candidate_communication_authority.py'
  test ! -f /etc/systemd/system/wathefni-orchestrator.service.d/talent-pool-classification.conf
  test \$(ps -ef | grep -iE 'talent_pool_classification|classif.*worker' | grep -v grep | wc -l) = 0
  grep -q '^Environment=WATHEFNI_UNIFIED_CANDIDATES_TALENT_POOL=off$' /etc/systemd/system/wathefni-orchestrator.service.d/unified-candidates.conf
  grep -q '^Environment=WATHEFNI_UNIFIED_CANDIDATES_TENANTS=WATHEFNI$' /etc/systemd/system/wathefni-orchestrator.service.d/unified-candidates.conf
  test \$(sha256sum /opt/wathefni/staging/orchestrator/app.py | awk '{print \$1}') = '$STAGING_APP_SHA'
  test \$(sha256sum /opt/wathefni/staging/orchestrator/action_registry.py | awk '{print \$1}') = '$STAGING_REGISTRY_SHA'
  test \$(sha256sum /opt/wathefni/staging/orchestrator/offer_service.py | awk '{print \$1}') = '$STAGING_OFFER_SHA'
  test \$(cat /opt/wathefni/staging/staging-evidence/talent-pool-classification/20260725T203327Z/artifact.sha256) = '$CLASSIFICATION_ARTIFACT'
  test \$(cat /opt/wathefni/staging/staging-evidence/held-notify-authority/20260725T211236Z/artifact.sha256) = '$HELD_AUTHORITY_ARTIFACT'
  echo PREDEPLOY_CHECKS_OK
"

log "fresh production backup and rollback artifact"
"${SSH[@]}" "set -euo pipefail
  mkdir -p '$REMOTE_BACKUP' '$REMOTE_EVIDENCE'
  cp -a '$PROD_ORCH/app.py' '$REMOTE_BACKUP/app.py.pre'
  cp -a '$PROD_ORCH/action_registry.py' '$REMOTE_BACKUP/action_registry.py.pre'
  cp -a '$PROD_ORCH/offer_service.py' '$REMOTE_BACKUP/offer_service.py.pre'
  cp -a '$PROD_ORCH/unified_candidates.py' '$REMOTE_BACKUP/unified_candidates.py.pre'
  cp -a '$PROD_ORCH/unified_candidates_routes.py' '$REMOTE_BACKUP/unified_candidates_routes.py.pre'
  cp -a /etc/systemd/system/wathefni-orchestrator.service.d/unified-candidates.conf '$REMOTE_BACKUP/unified-candidates.conf.pre'
  if test -d /var/www/wathefni-dashboard; then cp -a /var/www/wathefni-dashboard '$REMOTE_BACKUP/dashboard-dist.pre'; fi

  /usr/local/bin/backup-wathefni daily
  tmpdump=\$(mktemp /tmp/wathefni-prod-tpc-XXXX.dump)
  chown postgres:postgres \"\$tmpdump\"
  sudo -u postgres pg_dump -Fc -d wathefni -f \"\$tmpdump\"
  mv \"\$tmpdump\" '$REMOTE_BACKUP/db.dump'
  chmod 640 '$REMOTE_BACKUP/db.dump'
  pg_restore --list '$REMOTE_BACKUP/db.dump' > '$REMOTE_BACKUP/db.restore-list'
  test -s '$REMOTE_BACKUP/db.restore-list'
  sha256sum \
    '$REMOTE_BACKUP/db.dump' \
    '$REMOTE_BACKUP/app.py.pre' \
    '$REMOTE_BACKUP/action_registry.py.pre' \
    '$REMOTE_BACKUP/offer_service.py.pre' \
    > '$REMOTE_BACKUP/SHA256SUMS'

  {
    echo timestamp=\$(date -u +%FT%TZ)
    echo source_commit='$SOURCE_COMMIT'
    echo classification_artifact='$CLASSIFICATION_ARTIFACT'
    echo held_authority_artifact='$HELD_AUTHORITY_ARTIFACT'
    echo composite_artifact='$COMPOSITE_ARTIFACT'
    echo health=\$(curl -sf -o /dev/null -w '%{http_code}' http://127.0.0.1:8010/health)
    echo app_sha=\$(sha256sum '$PROD_ORCH/app.py' | awk '{print \$1}')
    echo registry_sha=\$(sha256sum '$PROD_ORCH/action_registry.py' | awk '{print \$1}')
    echo offer_sha=\$(sha256sum '$PROD_ORCH/offer_service.py' | awk '{print \$1}')
    echo dashboard_sha=\$(find /var/www/wathefni-dashboard -type f -print0 2>/dev/null | sort -z | xargs -0 sha256sum | sha256sum | awk '{print \$1}')
    echo classification_workers=0
    cat /etc/systemd/system/wathefni-orchestrator.service.d/unified-candidates.conf
  } > '$REMOTE_EVIDENCE/PREDEPLOY.txt'

  cat > '$REMOTE_BACKUP/ROLLBACK.sh' <<'EOS'
#!/usr/bin/env bash
set -euo pipefail
ROOT=\$(cd \"\$(dirname \"\$0\")\" && pwd)
systemctl stop wathefni-orchestrator.service || true
cp -a \"\$ROOT/app.py.pre\" /opt/wathefni/orchestrator/app.py
cp -a \"\$ROOT/action_registry.py.pre\" /opt/wathefni/orchestrator/action_registry.py
cp -a \"\$ROOT/offer_service.py.pre\" /opt/wathefni/orchestrator/offer_service.py
cp -a \"\$ROOT/unified_candidates.py.pre\" /opt/wathefni/orchestrator/unified_candidates.py
cp -a \"\$ROOT/unified_candidates_routes.py.pre\" /opt/wathefni/orchestrator/unified_candidates_routes.py
cp -a \"\$ROOT/unified-candidates.conf.pre\" /etc/systemd/system/wathefni-orchestrator.service.d/unified-candidates.conf
rm -f /opt/wathefni/orchestrator/talent_pool_classification.py
rm -f /opt/wathefni/orchestrator/talent_pool_classification_routes.py
rm -f /opt/wathefni/orchestrator/talent_pool_taxonomy_v1.json
rm -f /opt/wathefni/orchestrator/test_talent_pool_classification.py
rm -f /opt/wathefni/orchestrator/local-qualify-talent-pool-classification.py
rm -f /opt/wathefni/orchestrator/candidate_communication_authority.py
rm -f /opt/wathefni/orchestrator/test_candidate_communication_authority.py
rm -f /etc/systemd/system/wathefni-orchestrator.service.d/talent-pool-classification.conf
systemctl daemon-reload
systemctl restart wathefni-orchestrator.service
for i in \$(seq 1 60); do
  curl -sf http://127.0.0.1:8010/health >/dev/null && break
  sleep 1
done
curl -sf http://127.0.0.1:8010/health >/dev/null
EOS
  chmod +x '$REMOTE_BACKUP/ROLLBACK.sh'
  echo '$REMOTE_BACKUP' > /opt/wathefni/backups/.last-predeploy-tpc-dark
  echo BACKUP_OK
"

log "upload exact artifact"
scp -o BatchMode=yes \
  "$PACKAGE/final/app.py" \
  "$PACKAGE/final/action_registry.py" \
  "$PACKAGE/final/offer_service.py" \
  "$PACKAGE/final/candidate_communication_authority.py" \
  "$PACKAGE/final/test_candidate_communication_authority.py" \
  "$PACKAGE/final/talent_pool_classification.py" \
  "$PACKAGE/final/talent_pool_classification_routes.py" \
  "$PACKAGE/final/talent_pool_taxonomy_v1.json" \
  "$PACKAGE/final/test_talent_pool_classification.py" \
  "$PACKAGE/final/local-qualify-talent-pool-classification.py" \
  "$PACKAGE/final/talent-pool-classification.conf" \
  "$PACKAGE/final/DEPLOY-MANIFEST.sha256" \
  "$PACKAGE/final/PRODUCTION-DARK-ARTIFACT.sha256" \
  "$PACKAGE/final/SOURCE-COMMIT" \
  "$PACKAGE/final/IDENTITY.txt" \
  "$VPS_HOST:$REMOTE_EVIDENCE/"

log "verify uploaded artifact and apply additive schema"
"${SSH[@]}" "set -euo pipefail
  cd '$REMOTE_EVIDENCE'
  sha256sum -c DEPLOY-MANIFEST.sha256
  test \$(cat PRODUCTION-DARK-ARTIFACT.sha256) = '$COMPOSITE_ARTIFACT'

  export WATHEFNI_ENV=production
  export WATHEFNI_POSTGRES_ENV=/root/.openclaw/secrets/postgres.env
  export WATHEFNI_WORKSPACE=/root/.openclaw/workspaces/company-wathefni
  export WATHEFNI_EXPECTED_DATABASE_HOST=127.0.0.1
  export WATHEFNI_EXPECTED_DATABASE_PORT=5432
  export WATHEFNI_EXPECTED_DATABASE_NAME=wathefni
  export WATHEFNI_DATABASE_ENVIRONMENT_MARKER=wathefni-production-isolation-v1
  export WATHEFNI_TALENT_POOL_CLASSIFICATION=off
  export WATHEFNI_TALENT_POOL_CLASSIFICATION_TENANTS=
  export WATHEFNI_TALENT_POOL_CLASSIFICATION_SCHEMA=off
  export WATHEFNI_TALENT_POOL_CLASSIFICATION_MANUAL=off
  export WATHEFNI_TALENT_POOL_CLASSIFICATION_WORKERS=off
  export WATHEFNI_TALENT_POOL_CLASSIFICATION_UI=off
  PYTHONPATH='$REMOTE_EVIDENCE' /opt/wathefni/orchestrator/.venv/bin/python - <<'PY'
import pathlib
import psycopg2
import talent_pool_classification as tpc

vals = {}
for line in pathlib.Path('/root/.openclaw/secrets/postgres.env').read_text().splitlines():
    if '=' in line and not line.strip().startswith('#'):
        key, value = line.split('=', 1)
        vals[key.strip()] = value.strip().strip('\"')
conn = psycopg2.connect(vals['WATHEFNI_DATABASE_URL'])
try:
    with conn.cursor() as cur:
        tpc.ensure_classification_schema(cur)
        version = tpc.seed_global_taxonomy(cur)
    conn.commit()
    print('ADDITIVE_SCHEMA_OK', version)
finally:
    conn.close()
PY
"

log "deploy with every classification flag OFF"
"${SSH[@]}" "set -euo pipefail
  cp '$REMOTE_EVIDENCE/app.py' '$PROD_ORCH/app.py'
  cp '$REMOTE_EVIDENCE/action_registry.py' '$PROD_ORCH/action_registry.py'
  cp '$REMOTE_EVIDENCE/offer_service.py' '$PROD_ORCH/offer_service.py'
  cp '$REMOTE_EVIDENCE/candidate_communication_authority.py' '$PROD_ORCH/'
  cp '$REMOTE_EVIDENCE/test_candidate_communication_authority.py' '$PROD_ORCH/'
  cp '$REMOTE_EVIDENCE/talent_pool_classification.py' '$PROD_ORCH/'
  cp '$REMOTE_EVIDENCE/talent_pool_classification_routes.py' '$PROD_ORCH/'
  cp '$REMOTE_EVIDENCE/talent_pool_taxonomy_v1.json' '$PROD_ORCH/'
  cp '$REMOTE_EVIDENCE/test_talent_pool_classification.py' '$PROD_ORCH/'
  cp '$REMOTE_EVIDENCE/local-qualify-talent-pool-classification.py' '$PROD_ORCH/'
  cp '$REMOTE_EVIDENCE/talent-pool-classification.conf' /etc/systemd/system/wathefni-orchestrator.service.d/talent-pool-classification.conf
  systemctl daemon-reload
  systemctl restart wathefni-orchestrator.service
  for i in \$(seq 1 90); do
    curl -sf http://127.0.0.1:8010/health >/dev/null && break
    sleep 1
  done
  test \$(curl -sf -o /dev/null -w '%{http_code}' http://127.0.0.1:8010/health) = 200
  grep -qx 'Environment=WATHEFNI_TALENT_POOL_CLASSIFICATION=off' /etc/systemd/system/wathefni-orchestrator.service.d/talent-pool-classification.conf
  grep -qx 'Environment=WATHEFNI_TALENT_POOL_CLASSIFICATION_TENANTS=' /etc/systemd/system/wathefni-orchestrator.service.d/talent-pool-classification.conf
  grep -qx 'Environment=WATHEFNI_TALENT_POOL_CLASSIFICATION_SCHEMA=off' /etc/systemd/system/wathefni-orchestrator.service.d/talent-pool-classification.conf
  grep -qx 'Environment=WATHEFNI_TALENT_POOL_CLASSIFICATION_MANUAL=off' /etc/systemd/system/wathefni-orchestrator.service.d/talent-pool-classification.conf
  grep -qx 'Environment=WATHEFNI_TALENT_POOL_CLASSIFICATION_WORKERS=off' /etc/systemd/system/wathefni-orchestrator.service.d/talent-pool-classification.conf
  grep -qx 'Environment=WATHEFNI_TALENT_POOL_CLASSIFICATION_UI=off' /etc/systemd/system/wathefni-orchestrator.service.d/talent-pool-classification.conf
  test \$(ps -ef | grep -iE 'talent_pool_classification|classif.*worker' | grep -v grep | wc -l) = 0
  grep -q '^Environment=WATHEFNI_UNIFIED_CANDIDATES_TALENT_POOL=off$' /etc/systemd/system/wathefni-orchestrator.service.d/unified-candidates.conf
  grep -q '^Environment=WATHEFNI_UNIFIED_CANDIDATES_TENANTS=WATHEFNI$' /etc/systemd/system/wathefni-orchestrator.service.d/unified-candidates.conf
  test \$(sha256sum /opt/wathefni/staging/orchestrator/app.py | awk '{print \$1}') = '$STAGING_APP_SHA'
  test \$(sha256sum /opt/wathefni/staging/orchestrator/action_registry.py | awk '{print \$1}') = '$STAGING_REGISTRY_SHA'
  test \$(sha256sum /opt/wathefni/staging/orchestrator/offer_service.py | awk '{print \$1}') = '$STAGING_OFFER_SHA'
  cd '$PROD_ORCH'
  grep -v '  talent-pool-classification.conf$' '$REMOTE_EVIDENCE/DEPLOY-MANIFEST.sha256' | sha256sum -c -
  expected_conf=\$(awk '\$2 == \"talent-pool-classification.conf\" {print \$1}' '$REMOTE_EVIDENCE/DEPLOY-MANIFEST.sha256')
  test \"\$(sha256sum /etc/systemd/system/wathefni-orchestrator.service.d/talent-pool-classification.conf | awk '{print \$1}')\" = \"\$expected_conf\"
  {
    echo source_commit='$SOURCE_COMMIT'
    echo classification_artifact='$CLASSIFICATION_ARTIFACT'
    echo held_authority_artifact='$HELD_AUTHORITY_ARTIFACT'
    echo composite_artifact='$COMPOSITE_ARTIFACT'
    echo backup='$REMOTE_BACKUP'
    echo health=200
    echo classification_master=off
    echo classification_tenants=
    echo classification_schema_flag=off
    echo classification_manual=off
    echo classification_workers=off
    echo classification_ui=off
    echo unified_master=off
    echo unified_tenants=WATHEFNI
  } > '$REMOTE_EVIDENCE/DEPLOYED.txt'
  echo PRODUCTION_DARK_DEPLOY_OK
"

printf '%s\n' "$STAMP" > /tmp/tpc-prod-dark.stamp
printf '%s\n' "$REMOTE_EVIDENCE" > /tmp/tpc-prod-dark.evidence
printf '%s\n' "$REMOTE_BACKUP" > /tmp/tpc-prod-dark.backup
echo "DONE stamp=$STAMP evidence=$REMOTE_EVIDENCE backup=$REMOTE_BACKUP composite=$COMPOSITE_ARTIFACT"
