#!/usr/bin/env bash
# Wathefni lightweight deploy tool. Runs from the repo on an operator machine and
# drives the VPS over ssh/rsync. No CI, no containers.
#
#   ops/deploy.sh staging        Build + deploy to staging (:8011), run staging smoke suite.
#   ops/deploy.sh production      Promote the staging-tested artifact to prod (gated on staging green).
#   ops/deploy.sh rollback        Restore the most recent pre-deploy production snapshot.
#
# Production refuses to deploy unless the exact app.py that is about to ship already
# passed on staging (sha256 recorded by the staging run).
set -euo pipefail

VPS_HOST="${WATHEFNI_VPS_HOST:-root@76.13.63.68}"
SSH=(ssh -o BatchMode=yes -o ConnectTimeout=20 "$VPS_HOST")

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ORCH_SRC="$(cd "$SCRIPT_DIR/.." && pwd)"          # wathefni-orchestrator/
REPO_ROOT="$(cd "$ORCH_SRC/.." && pwd)"
DASH_SRC="$REPO_ROOT/apps/wathefni-dashboard"

CODE_FILES=(app.py candidate_messages.py candidate_semantic_router.py runtime_environment.py company_setup.py module_catalog.py tool_call_orchestrator.py action_registry.py outbound_delivery.py attendance_import.py channel_account_routing.py cv_extraction.py cv_docx.py recruiting_lifecycle.py hire_operations.py offer_lifecycle.py offer_service.py offer_routes.py assessment_lifecycle.py assessment_service.py assessment_ai_contracts.py assessment_ai_service.py assessment_ai_routes.py assessment_ai_qualification.py assessment-ai-worker.py assessment_ai_eval.py delivery-sweep-worker.py document-storage-reconcile-worker.py video-interview-worker.py leave-accrual-worker.py operator_mobile.py operator_mobile_data.py prehire_overview.py prehire_jobs.py jobs_phase2_stage_b.py)
RUNTIME_OPS_FILES=(ops/provision-environment-identity.py ops/provision-assessment-ai-db-role.py ops/document-storage-reconciliation.py ops/migrate-assessments-cleanup1.py ops/assessment-product2-staging-pilot.py ops/assessment-product2-staging-validation.py ops/assessment-product2-live-staging-eval.py ops/staging-smoke.sh ops/wathefni-orchestrator-staging.service ops/wathefni-orchestrator-production-environment.conf ops/wathefni-jobs-apply-production.conf ops/wathefni-document-storage-reconcile-staging.service ops/wathefni-document-storage-reconcile-staging.timer ops/wathefni-document-storage-reconcile.service ops/wathefni-document-storage-reconcile.timer ops/wathefni-delivery-sweep-staging.service ops/wathefni-delivery-sweep.service ops/wathefni-leave-accrual.service)

PROD_ORCH=/opt/wathefni/orchestrator
PROD_DASH_DIST=/opt/wathefni/apps/wathefni-dashboard/dist
PROD_DASH_PUBLIC=/var/www/wathefni-dashboard
STAGING_ORCH=/opt/wathefni/staging/orchestrator
STAGING_DASH=/opt/wathefni/staging/dashboard-dist
GREEN_FILE=/opt/wathefni/staging/last-green.sha256

PUBLIC_BASE="${WATHEFNI_PUBLIC_BASE:-https://api.wathefni.ai}"

log() { printf '\n=== %s ===\n' "$*"; }
fail() { printf 'DEPLOY FAILED: %s\n' "$*" >&2; exit 1; }

# Verifies the live public edge (through Caddy + TLS), not the app port. Catches
# proxy/routing mistakes — e.g. a /dashboard API route that Caddy serves as the
# static SPA shell (HTML) instead of proxying to the backend (JSON). This is the
# exact failure class that previously blanked the production dashboard.
guard_public_routes() {
  log "public-route guard (real edge: $PUBLIC_BASE)"
  local failed=0 out code ct r shell asset
  # Backend/API routes must be served by the app (JSON), never the SPA shell.
  # Probed unauthenticated: a JSON 4xx still proves the request reached the
  # backend rather than Caddy's static handler. The last entry is a deliberately
  # bogus route — it must fail clearly as JSON 404, not return the index shell.
  local api_routes=(
    /dashboard/auth/me
    /dashboard/prehire/summary
    /dashboard/setup/readiness
    /dashboard/superadmin/setup/companies
    /dashboard/__routing_probe_should_404__
  )
  for r in "${api_routes[@]}"; do
    out="$(curl -sS -o /dev/null -w '%{http_code} %{content_type}' "$PUBLIC_BASE$r" 2>/dev/null || echo '000 curl-error')"
    code="${out%% *}"; ct="${out#* }"
    if printf '%s' "$ct" | grep -qi 'text/html'; then
      printf '  FAIL  %-44s -> HTML (code=%s ct=%s): Caddy is serving the SPA instead of the backend\n' "$r" "$code" "$ct" >&2
      failed=1
    else
      printf '  ok    %-44s -> code=%s ct=%s\n' "$r" "$code" "$ct"
    fi
  done
  # SPA shell must be HTML and contain the React mount point.
  shell="$(curl -sS "$PUBLIC_BASE/dashboard" 2>/dev/null || true)"
  if printf '%s' "$shell" | grep -q 'id="root"'; then
    printf '  ok    %-44s -> HTML shell with #root\n' "/dashboard"
  else
    printf '  FAIL  %-44s -> shell missing #root mount point\n' "/dashboard" >&2
    failed=1
  fi
  # The hashed asset referenced by the shell must load as JavaScript.
  asset="$(printf '%s' "$shell" | grep -oE '/dashboard/assets/(index|dashboard)-[A-Za-z0-9_.-]+\.js' | head -1)"
  if [ -n "$asset" ]; then
    out="$(curl -sS -o /dev/null -w '%{http_code} %{content_type}' "$PUBLIC_BASE$asset" 2>/dev/null || echo '000 curl-error')"
    code="${out%% *}"; ct="${out#* }"
    if [ "$code" = 200 ] && printf '%s' "$ct" | grep -qiE 'javascript|ecmascript'; then
      printf '  ok    %-44s -> code=%s ct=%s\n' "$asset" "$code" "$ct"
    else
      printf '  FAIL  %-44s -> code=%s ct=%s (asset not served as JS)\n' "$asset" "$code" "$ct" >&2
      failed=1
    fi
  else
    printf '  FAIL  %-44s -> no hashed asset reference found in shell\n' "/dashboard" >&2
    failed=1
  fi
  [ "$failed" = 0 ] || return 1
  printf 'public-route guard: ALL CHECKS PASSED\n'
}

preflight() {
  log "local preflight (build + tests)"
  ( cd "$DASH_SRC" && npm test -- --run && npm run build ) || fail "dashboard test/build failed"
  ( cd "$ORCH_SRC" && python3 -m py_compile "${CODE_FILES[@]}" ) || fail "python compile failed"
  ( cd "$ORCH_SRC" && python3 smoke-test-prehire-overview-unit.py && python3 smoke-test-tenant-read-hardening.py && python3 smoke-test-toolcall-orchestrator.py && python3 smoke-test-whatsapp-identity.py && python3 smoke-test-channel-account-routing.py && python3 smoke-test-cv-extraction-ocr.py && python3 smoke-test-cv-docx.py && python3 smoke-test-canonical-recruiting-lifecycle.py && python3 smoke-test-offer-lifecycle.py && python3 smoke-test-offer-hire-override.py ) || fail "local source smokes failed"
}

artifact_sha() {
  {
    ( cd "$ORCH_SRC" && shasum -a 256 "${CODE_FILES[@]}" "${RUNTIME_OPS_FILES[@]}" requirements.txt ops/deploy.sh )
    shasum -a 256 "$DASH_SRC"/dist/*.html "$DASH_SRC"/dist/*.svg "$DASH_SRC"/dist/assets/*
  } | shasum -a 256 | awk '{print $1}'
}

sync_code() {  # $1 = dest orchestrator dir
  rsync -az "${CODE_FILES[@]/#/$ORCH_SRC/}" "$ORCH_SRC/requirements.txt" "$ORCH_SRC"/smoke-test-*.py "$ORCH_SRC/integrity-scan.py" "$VPS_HOST:$1/"
  rsync -az "$ORCH_SRC/ops/" "$VPS_HOST:$1/ops/"
  "${SSH[@]}" "mkdir -p '$1/reports/assessment-product2-eval'"
  rsync -az "$ORCH_SRC/reports/assessment-product2-eval/" "$VPS_HOST:$1/reports/assessment-product2-eval/"
}

install_pinned_runtime_dependencies() {  # $1 = remote orchestrator dir
  local dest="$1"
  "${SSH[@]}" "set -e; \
    pure=\$(awk '/^puremagic==/{print; exit}' '$dest/requirements.txt'); \
    mistral=\$(awk '/^mistralai==/{print; exit}' '$dest/requirements.txt'); \
    [ \"\$pure\" = 'puremagic==2.2.0' ] || { echo 'missing or unexpected puremagic pin' >&2; exit 1; }; \
    [ \"\$mistral\" = 'mistralai==2.6.0' ] || { echo 'missing or unexpected mistralai pin' >&2; exit 1; }; \
    /opt/wathefni/orchestrator/.venv/bin/pip install --disable-pip-version-check --no-deps \"\$pure\" \"\$mistral\""
}

deploy_staging() {
  preflight
  log "sync code -> staging"
  sync_code "$STAGING_ORCH"
  log "install pinned runtime dependencies"
  install_pinned_runtime_dependencies "$STAGING_ORCH"
  rsync -az --delete "$DASH_SRC/dist/" "$VPS_HOST:$STAGING_DASH/"
  log "compile + migrate (staging DB) + restart"
  "${SSH[@]}" "set -e; install -m 0644 $STAGING_ORCH/ops/wathefni-orchestrator-staging.service /etc/systemd/system/; install -m 0644 $STAGING_ORCH/ops/wathefni-document-storage-reconcile-staging.service /etc/systemd/system/; install -m 0644 $STAGING_ORCH/ops/wathefni-document-storage-reconcile-staging.timer /etc/systemd/system/; install -m 0644 $STAGING_ORCH/ops/wathefni-delivery-sweep-staging.service /etc/systemd/system/; systemctl daemon-reload; cd $STAGING_ORCH; /opt/wathefni/orchestrator/.venv/bin/python -m py_compile app.py candidate_messages.py candidate_semantic_router.py runtime_environment.py company_setup.py module_catalog.py tool_call_orchestrator.py action_registry.py outbound_delivery.py attendance_import.py channel_account_routing.py cv_extraction.py cv_docx.py recruiting_lifecycle.py hire_operations.py offer_lifecycle.py offer_service.py offer_routes.py assessment_lifecycle.py assessment_service.py assessment_ai_contracts.py assessment_ai_service.py assessment_ai_routes.py assessment_ai_qualification.py assessment-ai-worker.py assessment_ai_eval.py delivery-sweep-worker.py document-storage-reconcile-worker.py operator_mobile.py operator_mobile_data.py prehire_overview.py prehire_jobs.py jobs_phase2_stage_b.py; \
    /opt/wathefni/orchestrator/.venv/bin/python ops/provision-environment-identity.py --env-file /root/.openclaw/secrets/postgres.staging.env --environment staging --expected-host 127.0.0.1 --expected-port 5432 --expected-database wathefni_staging --marker wathefni-staging-hr2-isolation-v1 --apply --confirm staging:wathefni_staging:wathefni-staging-hr2-isolation-v1; \
    WATHEFNI_ENV=staging WATHEFNI_POSTGRES_ENV=/root/.openclaw/secrets/postgres.staging.env WATHEFNI_WORKSPACE=/opt/wathefni/staging/workspace WATHEFNI_EXPECTED_DATABASE_HOST=127.0.0.1 WATHEFNI_EXPECTED_DATABASE_PORT=5432 WATHEFNI_EXPECTED_DATABASE_NAME=wathefni_staging WATHEFNI_DATABASE_ENVIRONMENT_MARKER=wathefni-staging-hr2-isolation-v1 /opt/wathefni/orchestrator/.venv/bin/python -c 'import app; app.assert_runtime_environment_binding(); app.ensure_schema(force=True); print(\"staging schema ok\")'; \
    WATHEFNI_ENV=staging WATHEFNI_POSTGRES_ENV=/root/.openclaw/secrets/postgres.staging.env WATHEFNI_WORKSPACE=/opt/wathefni/staging/workspace WATHEFNI_EXPECTED_DATABASE_HOST=127.0.0.1 WATHEFNI_EXPECTED_DATABASE_PORT=5432 WATHEFNI_EXPECTED_DATABASE_NAME=wathefni_staging WATHEFNI_DATABASE_ENVIRONMENT_MARKER=wathefni-staging-hr2-isolation-v1 /opt/wathefni/orchestrator/.venv/bin/python ops/migrate-assessments-cleanup1.py; \
    systemctl restart wathefni-orchestrator-staging.service; systemctl enable --now wathefni-document-storage-reconcile-staging.timer; sleep 3; systemctl is-active wathefni-orchestrator-staging.service; systemctl is-active wathefni-document-storage-reconcile-staging.timer"
  log "staging smoke suite"
  "${SSH[@]}" "$STAGING_ORCH/ops/staging-smoke.sh"
  log "record staging-green artifact hash"
  local sha; sha="$(artifact_sha)"
  "${SSH[@]}" "printf '%s\n' '$sha' > $GREEN_FILE"
  printf '\nStaging deploy OK. artifact sha256=%s recorded as staging-green.\n' "$sha"
}

deploy_production() {
  preflight
  local sha; sha="$(artifact_sha)"
  log "production gate: complete artifact must have passed staging"
  local green; green="$("${SSH[@]}" "cat $GREEN_FILE 2>/dev/null || true")"
  [ -n "$green" ] || fail "no staging-green record found — run 'deploy.sh staging' first"
  [ "$green" = "$sha" ] || fail "artifact ($sha) does not match staging-green ($green) — run staging for THIS build first"
  log "pre-deploy backup + snapshot"
  "${SSH[@]}" "set -e; /usr/local/bin/backup-wathefni daily >/dev/null; \
    ts=\$(date -u +%Y%m%dT%H%M%SZ); snap=/opt/wathefni/backups/predeploy-\$ts; mkdir -p \"\$snap\"; \
    tar --exclude='.venv' --exclude='__pycache__' --exclude='*.pyc' -czf \"\$snap/orchestrator.tgz\" -C $PROD_ORCH . ; \
    tar -czf \"\$snap/dashboard-public.tgz\" -C $PROD_DASH_PUBLIC . ; \
    printf '%s\n' \"\$snap\" > /opt/wathefni/backups/.last-predeploy; echo snapshot \"\$snap\""
  log "sync code + dashboard -> production"
  sync_code "$PROD_ORCH"
  log "install pinned runtime dependencies"
  install_pinned_runtime_dependencies "$PROD_ORCH"
  rsync -az --delete "$DASH_SRC/dist/" "$VPS_HOST:$PROD_DASH_DIST/"
  log "compile + migrate + restart + publish dashboard"
  if "${SSH[@]}" "set -e; mkdir -p /etc/systemd/system/wathefni-orchestrator.service.d; install -m 0644 $PROD_ORCH/ops/wathefni-orchestrator-production-environment.conf /etc/systemd/system/wathefni-orchestrator.service.d/environment.conf; install -m 0644 $PROD_ORCH/ops/wathefni-jobs-apply-production.conf /etc/systemd/system/wathefni-orchestrator.service.d/jobs-apply-whatsapp.conf; systemctl daemon-reload; cd $PROD_ORCH; /opt/wathefni/orchestrator/.venv/bin/python -m py_compile app.py candidate_messages.py candidate_semantic_router.py runtime_environment.py company_setup.py module_catalog.py tool_call_orchestrator.py action_registry.py outbound_delivery.py attendance_import.py channel_account_routing.py cv_extraction.py cv_docx.py recruiting_lifecycle.py hire_operations.py offer_lifecycle.py offer_service.py offer_routes.py assessment_lifecycle.py assessment_service.py assessment_ai_contracts.py assessment_ai_service.py assessment_ai_routes.py assessment_ai_qualification.py assessment-ai-worker.py assessment_ai_eval.py operator_mobile.py operator_mobile_data.py prehire_jobs.py jobs_phase2_stage_b.py; \
    WATHEFNI_ENV=production WATHEFNI_POSTGRES_ENV=/root/.openclaw/secrets/postgres.env WATHEFNI_WORKSPACE=/root/.openclaw/workspaces/company-wathefni WATHEFNI_EXPECTED_DATABASE_HOST=127.0.0.1 WATHEFNI_EXPECTED_DATABASE_PORT=5432 WATHEFNI_EXPECTED_DATABASE_NAME=wathefni WATHEFNI_DATABASE_ENVIRONMENT_MARKER=wathefni-production-isolation-v1 /opt/wathefni/orchestrator/.venv/bin/python -c 'import app; app.assert_runtime_environment_binding(); app.ensure_schema(force=True); print(\"prod schema ok\")'; \
    systemctl restart wathefni-orchestrator.service; sleep 3; systemctl is-active wathefni-orchestrator.service >/dev/null; \
    rm -rf $PROD_DASH_PUBLIC.new; mkdir -p $PROD_DASH_PUBLIC.new; cp -a $PROD_DASH_DIST/. $PROD_DASH_PUBLIC.new/; rsync -a --delete $PROD_DASH_PUBLIC.new/ $PROD_DASH_PUBLIC/; rm -rf $PROD_DASH_PUBLIC.new; systemctl reload caddy; \
    h=\$(curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:8010/health); [ \"\$h\" = 200 ] || { echo health=\$h; exit 1; }; echo prod_health=\$h"; then
    if guard_public_routes; then
      printf '\nProduction deploy OK.\n'
    else
      printf '\nPublic-route guard FAILED — rolling back.\n' >&2
      rollback
      fail "public-route guard failed (Caddy/proxy routing mistake) and deploy was rolled back"
    fi
  else
    printf '\nProduction deploy FAILED — rolling back.\n' >&2
    rollback
    fail "production deploy failed and was rolled back"
  fi
}

rollback() {
  log "rollback to last pre-deploy snapshot"
  "${SSH[@]}" "set -e; snap=\$(cat /opt/wathefni/backups/.last-predeploy 2>/dev/null || true); \
    [ -n \"\$snap\" ] && [ -d \"\$snap\" ] || { echo 'no snapshot to roll back to'; exit 1; }; \
    echo restoring \"\$snap\"; \
    tar -xzf \"\$snap/orchestrator.tgz\" -C $PROD_ORCH; \
    rm -rf $PROD_DASH_PUBLIC.rb; mkdir -p $PROD_DASH_PUBLIC.rb; tar -xzf \"\$snap/dashboard-public.tgz\" -C $PROD_DASH_PUBLIC.rb; rsync -a --delete $PROD_DASH_PUBLIC.rb/ $PROD_DASH_PUBLIC/; rm -rf $PROD_DASH_PUBLIC.rb; \
    cd $PROD_ORCH; systemctl restart wathefni-orchestrator.service; sleep 3; systemctl reload caddy; \
    h=\$(curl -s -o /dev/null -w '%{http_code}' http://127.0.0.1:8010/health); echo rollback_health=\$h"
  printf '\nRollback complete.\n'
}

case "${1:-}" in
  staging) deploy_staging ;;
  production) deploy_production ;;
  rollback) rollback ;;
  *) echo "usage: $0 {staging|production|rollback}"; exit 2 ;;
esac
