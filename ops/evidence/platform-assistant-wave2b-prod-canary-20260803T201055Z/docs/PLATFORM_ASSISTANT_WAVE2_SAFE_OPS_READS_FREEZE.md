# Platform Assistant Wave 2 — Safe Ops Queue Reads Freeze

**Gate:** `PROD_SYNTHETIC_PLATFORM_ASSISTANT_WAVE2_SAFE_OPS_READS_GO`  
**Evidence:** `ops/evidence/platform-assistant-wave2b-prod-canary-20260803T201055Z/`  
**Staging prerequisite:** `ops/evidence/platform-assistant-wave2-staging-20260803T200430Z/` (`STAGING_PLATFORM_ASSISTANT_WAVE2_SAFE_OPS_READS_GO`)  
**Freeze:** **GO** for Wave 2 Safe Ops Queue Reads (production synthetic WATHEFNI posture)

## Frozen posture

- Grounded read-only Leave request queue + Attendance exception queue
- `WATHEFNI_PLATFORM_ASSISTANT_WAVE2=1`, companies `WATHEFNI` (requires Wave 1)
- HR dashboard-only · mutations off · master kill retained
- Attendance labeled ingest-off / existing-record based
- Leave and Attendance remain systems of action (prepare deep links only)
- Citations · freshness · authority · grouping · EN/AR · audit events
- No Payroll · Shifts · Onboarding · WhatsApp · manager/employee/mobile assistants
- No money · Attendance ingest · mutations · frozen-module contract changes

## Proven on production synthetic

- Deploy + migrate/ACK (`assistant.wave2b_production_ack`); canary residual **0**; durable ACK retained
- Leave queue + Attendance exceptions summarize (citations, freshness, authority, groups, deep links)
- Tenant / permission / manager-scope isolation; WhatsApp tools hidden; mutations hidden
- Master kill + mutation kill; rollback verified; redeploy canary green
- Sibling freezes green (Employees 360 / Onboarding / Attendance / Leave / Shifts)

## Explicit NO-GO (outside this freeze)

- Assistant Wave 3
- Payroll / Shifts / Onboarding assistant surfaces
- WhatsApp widening / manager or employee assistants / mobile
- Payroll money · Attendance ingest · frozen-module contract changes

## Rollback

Backup + `ROLLBACK.sh` under `/opt/wathefni/backups/production-pre-platform-assistant-wave2b-*`
