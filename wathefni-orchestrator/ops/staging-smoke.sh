#!/usr/bin/env bash
# Staging smoke suite — must pass before promoting a release to production.
# Runs HTTP checks against the staging service (:8011) and behavioural checks
# (tenant isolation, entitlement, dry-run delivery) against the staging DB.
set -euo pipefail

PORT="${WATHEFNI_STAGING_PORT:-8011}"
STAGING_ORCH="${WATHEFNI_STAGING_ORCH:-/opt/wathefni/staging/orchestrator}"
STAGING_ENV="${WATHEFNI_STAGING_ENV:-/root/.openclaw/secrets/postgres.staging.env}"
STAGING_WORKSPACE="${WATHEFNI_STAGING_WORKSPACE:-/opt/wathefni/staging/workspace}"
VENV_PY="${WATHEFNI_VENV_PY:-/opt/wathefni/orchestrator/.venv/bin/python}"
HR_PHONE="${WATHEFNI_SMOKE_HR_PHONE:-96599338566}"
BASE="http://127.0.0.1:${PORT}"

log() { printf '%s [staging-smoke] %s\n' "$(date -u +%FT%TZ)" "$*"; }
fail() { printf 'FAILED: %s\n' "$*"; exit 1; }

set -a; . "$STAGING_ENV"; set +a
TOKEN="${WATHEFNI_DASHBOARD_TOKEN:-}"
[ -n "$TOKEN" ] || fail "no staging dashboard token in $STAGING_ENV"

code() { curl -s -o /dev/null -w '%{http_code}' "$@"; }
AUTH=(-H "Authorization: Bearer ${TOKEN}" -H "X-HR-Phone: ${HR_PHONE}" -H "X-Company-Code: WATHEFNI")

# 1) HTTP checks against the staging server
h=$(code "$BASE/health"); [ "$h" = "200" ] || fail "health=$h"; log "health 200"
for path in /dashboard/auth/me /dashboard/prehire/summary /dashboard/team /dashboard/prehire/import/batches /dashboard/posthire/compliance; do
  c=$(code "${AUTH[@]}" "$BASE$path"); [ "$c" = "200" ] || fail "$path=$c"; log "$path 200"
done

# 2) Behavioural checks against the staging DB (app uses staging env + workspace)
export WATHEFNI_POSTGRES_ENV="$STAGING_ENV"
export WATHEFNI_WORKSPACE="$STAGING_WORKSPACE"
cd "$STAGING_ORCH"

log "tenant isolation (behaviour, staging DB)"
"$VENV_PY" smoke-test-tenant-read-behavior.py | sed 's/^/    /'

log "bulk CV import (behaviour, staging DB)"
"$VENV_PY" smoke-test-bulk-cv-import.py | sed 's/^/    /'

log "tiered intake model (behaviour, staging DB)"
"$VENV_PY" smoke-test-tiered-intake.py | sed 's/^/    /'

log "mailbox ingestion foundation (behaviour, staging DB)"
"$VENV_PY" smoke-test-mailbox-foundation.py | sed 's/^/    /'

log "mailbox sync core (behaviour, staging DB)"
"$VENV_PY" smoke-test-mailbox-sync.py | sed 's/^/    /'

log "gmail adapter (behaviour, mocked gog transport, staging DB)"
"$VENV_PY" smoke-test-mailbox-gmail.py | sed 's/^/    /'

log "inbound email intake (behaviour, Postmark payloads, staging DB)"
"$VENV_PY" smoke-test-inbound-email.py | sed 's/^/    /'

log "outbound email provider (behaviour, mocked Postmark/gog, staging DB)"
"$VENV_PY" smoke-test-outbound-email.py | sed 's/^/    /'

log "leave registry pilot (registry/tool-call architecture, mocked legacy)"
"$VENV_PY" smoke-test-leave-registry.py | sed 's/^/    /'

log "post-hire registry migration (attendance/shifts/onboarding/payroll/analytics, mocked legacy)"
"$VENV_PY" smoke-test-posthire-registry.py | sed 's/^/    /'

log "post-hire dashboard action wiring (whitelist/scope/confirmation/audit/RBAC, stubbed orchestrator)"
"$VENV_PY" smoke-test-posthire-dashboard.py | sed 's/^/    /'

log "whatsapp identity hardening (WATHEFNI_STRICT_WHATSAPP_PERMS fail-closed, mocked legacy)"
"$VENV_PY" smoke-test-whatsapp-identity.py | sed 's/^/    /'

log "leave guardrails (behaviour, staging DB)"
"$VENV_PY" smoke-test-leave-guardrails.py | sed 's/^/    /'

log "tenant read hardening (source)"
"$VENV_PY" smoke-test-tenant-read-hardening.py | sed 's/^/    /'

log "second-company tenant isolation harness (behaviour, staging DB)"
"$VENV_PY" smoke-test-tenant-isolation-harness.py | sed 's/^/    /'

log "company-wide summary counts (counts exceed 50-window, match page definitions, staging DB)"
"$VENV_PY" smoke-test-summary-counts.py | sed 's/^/    /'

log "compliance dashboard (company-scoped read, counts/classifier parity, RBAC + module gate, staging DB)"
"$VENV_PY" smoke-test-compliance-dashboard.py | sed 's/^/    /'

log "google sheets is optional (best-effort, off-the-request-path; a sheets outage never breaks a workflow)"
"$VENV_PY" smoke-test-sheets-sync.py | sed 's/^/    /'

log "admin/config audit trail (team/role/whatsapp/mailbox/intake/import changes are traceable + best-effort)"
"$VENV_PY" smoke-test-admin-audit.py | sed 's/^/    /'

log "employee-hub integrity (orphan scan: company-scoped, read-only, catches drift, staging DB)"
"$VENV_PY" smoke-test-hub-integrity.py | sed 's/^/    /'

log "compliance V1.1 actions (send reminder / mark reviewed: registry + RBAC + harness + behaviour, staging DB)"
"$VENV_PY" smoke-test-compliance-actions.py | sed 's/^/    /'

log "onboarding dashboard upgrade (start/restart + mark item: registry + RBAC + flag gate + behaviour, staging DB)"
"$VENV_PY" smoke-test-onboarding-dashboard.py | sed 's/^/    /'

log "employee 360 profile (read-only, tenant + entitlement scoped, staging DB)"
"$VENV_PY" smoke-test-employee-profile.py | sed 's/^/    /'

log "employee roster (add/import: RBAC + dedupe + compliance-seed + no-message + CSV/XLSX, staging DB)"
WATHEFNI_DELIVERY_MODE=dry_run "$VENV_PY" smoke-test-employee-roster.py | sed 's/^/    /'

log "leave balances P1 (chargeable days + flag gate + accrual + observe-only consumption, staging DB)"
"$VENV_PY" smoke-test-leave-balances.py | sed 's/^/    /'

log "employee document hub (tenant isolation + RBAC gate + path-traversal guard + missing/external handling, staging DB)"
"$VENV_PY" smoke-test-document-hub.py | sed 's/^/    /'

log "manager-scoped read isolation (employees/onboarding/compliance/360 reads honor manager scope, staging DB)"
WATHEFNI_DELIVERY_MODE=dry_run "$VENV_PY" smoke-test-manager-read-isolation.py | sed 's/^/    /'

log "HR document upload (flag gate + RBAC + scope + validation + reuse ingestion bundle + downloadable, staging DB)"
WATHEFNI_DELIVERY_MODE=dry_run "$VENV_PY" smoke-test-document-upload.py | sed 's/^/    /'

log "assistant HR reads (list_onboarding_status / list_compliance_documents: flag gate + RBAC + tenant + manager scope + dashboard parity + no leakage, staging DB)"
WATHEFNI_DELIVERY_MODE=dry_run "$VENV_PY" smoke-test-assistant-hr-reads.py | sed 's/^/    /'

log "pre-hire registry migration (WATHEFNI_PREHIRE_VIA_REGISTRY: flag/parity/harness, hire->transition_hire, staging DB)"
WATHEFNI_DELIVERY_MODE=dry_run "$VENV_PY" smoke-test-prehire-registry-parity.py | sed 's/^/    /'

log "setup console V1 (super-admin gate fail-closed, provisioning idempotency, readiness, audit, staging DB)"
WATHEFNI_DELIVERY_MODE=dry_run "$VENV_PY" smoke-test-setup-console.py | sed 's/^/    /'

log "setup readiness B (owner checklist: module-aware, data-driven, tenant-scoped, staging DB)"
WATHEFNI_DELIVERY_MODE=dry_run "$VENV_PY" smoke-test-setup-readiness.py | sed 's/^/    /'

log "manager / org hierarchy V1a (direct scope + manager role + decision gates, flag-gated, staging DB)"
WATHEFNI_DELIVERY_MODE=dry_run "$VENV_PY" smoke-test-org-hierarchy.py | sed 's/^/    /'

log "shared outbound delivery layer Phase A (channel ladder + retry sweep + sensitivity + flags, dark, staging DB)"
WATHEFNI_DELIVERY_MODE=dry_run "$VENV_PY" smoke-test-outbound-delivery.py | sed 's/^/    /'

log "outbound layer Phase C — leave decision routes through the delivery layer (flag on vs off, staging DB)"
WATHEFNI_DELIVERY_MODE=dry_run "$VENV_PY" smoke-test-outbound-leave.py | sed 's/^/    /'

log "outbound layer Phase D — onboarding + compliance route through the delivery layer (flag on vs off, staging DB)"
WATHEFNI_DELIVERY_MODE=dry_run "$VENV_PY" smoke-test-outbound-onboarding-compliance.py | sed 's/^/    /'

log "outbound layer Phase E — shift assign/cancel/reminder route through the delivery layer (flag on vs off, staging DB)"
WATHEFNI_DELIVERY_MODE=dry_run "$VENV_PY" smoke-test-outbound-shift.py | sed 's/^/    /'

log "dry-run delivery sends nothing real"
WATHEFNI_DELIVERY_MODE=dry_run "$VENV_PY" smoke-test-delivery-mode.py | sed 's/^/    /'

log "entitlement hardening (runtime: viewer denied, owner allowed)"
"$VENV_PY" - <<'PY' | sed 's/^/    /'
import app
def ctx(role):
    return {"company_code":"WATHEFNI","actor_user_id":f"smoke-{role}","actor_role":role,
            "hr_user":{"role":role,"status":"active","company_code":"WATHEFNI"},
            "permissions":sorted(app.hr_role_permissions(role)),
            "access":{"role":role,"permissions":sorted(app.hr_role_permissions(role))}}
# Viewer can read, cannot mutate.
app.require_entitlement(ctx("viewer"), "pre_hiring", "prehire.read")
for perm in ("candidate.manage","assessment.manage","users.manage"):
    try:
        app.require_entitlement(ctx("viewer"), "pre_hiring", perm); raise SystemExit(f"viewer wrongly allowed {perm}")
    except app.HTTPException as e:
        assert e.status_code in (403,404,401), e
# Owner can manage.
app.require_entitlement(ctx("owner"), "pre_hiring", "candidate.manage")
# Leave RBAC (post-hire pilot): owner/hr_manager decide; viewer read-only; recruiter none.
assert "leave.read" in app.hr_role_permissions("viewer"), "viewer should read leave"
assert "leave.decide" not in app.hr_role_permissions("viewer"), "viewer must not decide leave"
assert "leave.decide" in app.hr_role_permissions("owner"), "owner should decide leave"
assert "leave.decide" in app.hr_role_permissions("hr_manager"), "hr_manager should decide leave"
assert "leave.read" not in app.hr_role_permissions("recruiter"), "recruiter has no leave perms in pilot"
try:
    app.require_entitlement(ctx("viewer"), "leave", "leave.decide"); raise SystemExit("viewer wrongly allowed leave.decide")
except app.HTTPException as e:
    assert e.status_code in (403,404,401), e
# Post-hire RBAC (broad migration): viewer read-only across modules; owner/hr_manager
# manage + export; hiring_manager team ops but no payroll.manage/export; export gated separately.
for perm in ("attendance.read","shifts.read","payroll.read","analytics.read"):
    assert perm in app.hr_role_permissions("viewer"), f"viewer should hold {perm}"
for perm in ("attendance.manage","shifts.manage","payroll.manage","payroll.export","onboarding.manage"):
    assert perm not in app.hr_role_permissions("viewer"), f"viewer must not hold {perm}"
for perm in ("attendance.manage","shifts.manage","payroll.manage","payroll.export","onboarding.manage","analytics.read"):
    assert perm in app.hr_role_permissions("owner"), f"owner should hold {perm}"
    assert perm in app.hr_role_permissions("hr_manager"), f"hr_manager should hold {perm}"
assert "shifts.manage" in app.hr_role_permissions("hiring_manager"), "hiring_manager manages shifts"
assert "attendance.manage" in app.hr_role_permissions("hiring_manager"), "hiring_manager manages attendance"
assert "payroll.read" in app.hr_role_permissions("hiring_manager"), "hiring_manager reads payroll"
for perm in ("payroll.manage","payroll.export","onboarding.manage"):
    assert perm not in app.hr_role_permissions("hiring_manager"), f"hiring_manager must not hold {perm}"
try:
    app.require_entitlement(ctx("viewer"), "payroll", "payroll.export"); raise SystemExit("viewer wrongly allowed payroll.export")
except app.HTTPException as e:
    assert e.status_code in (403,404,401), e
try:
    app.require_entitlement(ctx("hiring_manager"), "payroll", "payroll.export"); raise SystemExit("hiring_manager wrongly allowed payroll.export")
except app.HTTPException as e:
    assert e.status_code in (403,404,401), e
# Team Manager (org-hierarchy V1a): approve-capable post-hire lead, never company admin.
mgr = set(app.hr_role_permissions("manager"))
for perm in ("leave.decide","attendance.manage","shifts.manage","payroll.manage","analytics.read"):
    assert perm in mgr, f"manager should hold {perm}"
for perm in ("users.manage","settings.manage","payroll.export","candidate.manage","candidate.decide","prehire.read"):
    assert perm not in mgr, f"manager must not hold {perm}"
try:
    app.require_entitlement(ctx("manager"), "payroll", "payroll.export"); raise SystemExit("manager wrongly allowed payroll.export")
except app.HTTPException as e:
    assert e.status_code in (403,404,401), e
print("entitlement checks passed (viewer read-only; owner/hr_manager manage; manager approve-only; post-hire RBAC + payroll.export enforced)")
PY

log "ALL STAGING SMOKE CHECKS PASSED"
