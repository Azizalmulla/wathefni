# Module-Aware Shell Wave 0 — Focused Workforce Experience Freeze

**Gate:** `PROD_SYNTHETIC_MODULE_AWARE_SHELL_WAVE0_GO`  
**Evidence:** `ops/evidence/module-aware-shell-wave0b-prod-canary-20260803T204936Z/`  
**Staging prerequisite:** `ops/evidence/module-aware-shell-wave0-staging-20260803T204315Z/` (`STAGING_MODULE_AWARE_SHELL_WAVE0_GO`)  
**Freeze:** **GO** for Module-Aware Shell Wave 0 (production synthetic WATHEFNI posture)

## Frozen posture

- Employees = shared people spine (not a purchasable SKU)
- One operational module → land on that module
- Several workforce modules → Action Inbox when offerable + entitled source; else deterministic priority
- Payroll-only landing preserved; full-suite Pre-Hiring Overview preserved
- Inbox omits never-purchased Analytics/Compliance; partial = entitled failures only
- Assistant catalog module-truth; Alerts post-hire delivery rows when Pre-Hiring off
- Mutations off · Attendance ingest off · HR dashboard

## Proven on production synthetic

- Deploy + migrate/ACK; canary residual **0**; durable ACK retained
- Landing/nav/catalog/inbox honesty/alerts/E360 for Leave, Shifts, Attendance, Payroll,
  Onboarding+Compliance, Shifts+Attendance+Leave, Leave+Attendance+Shifts+Payroll, full suite
- Rollback verified; redeploy canary green; sibling freezes green

## Explicit NO-GO (outside this freeze)

- Further shell / mobile waves
- Assistant Wave 3 · AI mutations · Payroll money · Attendance ingest
- WhatsApp / manager / employee / mobile widening
- Home rebuild / dashboard rebuild / frozen-module contract changes

## Rollback

Backup + `ROLLBACK.sh` under `/opt/wathefni/backups/production-pre-module-aware-shell-wave0b-*`
