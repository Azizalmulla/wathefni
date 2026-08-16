# Setup Console Wave A — Launch Readiness Freeze

**Gate:** `PROD_SYNTHETIC_SETUP_CONSOLE_WAVE_A_GO`  
**Evidence:** `ops/evidence/setup-console-wave-ab-prod-canary-20260803T190801Z/`  
**Staging prerequisite:** `ops/evidence/setup-console-wave-a-staging-20260803T185950Z/` (`STAGING_SETUP_CONSOLE_WAVE_A_GO`)  
**Freeze:** **GO** for Wave A Launch Readiness (production synthetic WATHEFNI posture)

## Frozen posture

- Operator-only Launch Readiness for **WATHEFNI**
- Honest states: `not_purchased` · `setup_required` · `blocked` · `ready_for_canary` · `live_controlled` · `paused`
- Console toggles never override freezes, env gates, allowlists, or `SYNTHETIC_ONLY`
- `WATHEFNI_SETUP_CONSOLE_WAVE_A=1`, companies `WATHEFNI`
- Payroll money **off** · Attendance ingest **off** (`CAPTURE_INGEST=off`) · no rollout widening · no AI/mobile · no frozen-module contract changes

## Proven on production synthetic

- Deploy + migrate/ACK (schema-less; residual **0**)
- Six-stage checklist, overall readiness, important blockers + deep links, pause impact
- EN/AR + mobile web markers in UI source and dashboard dist
- Entitlements cannot bypass freezes / allowlists / SYNTHETIC_ONLY / CAPTURE_INGEST=off
- Rollback verified; redeploy canary green
- Sibling freezes green (Employees 360 / Onboarding / Attendance / Leave / Shifts)

## Explicit NO-GO (outside this freeze)

- Setup Wave B / external company onboarding
- Enabling Attendance ingest or Payroll money from Setup
- Broad rollout widening / AI / mobile app work

## Rollback

Backup + `ROLLBACK.sh` under `/opt/wathefni/backups/production-pre-setup-console-wave-ab-*`
