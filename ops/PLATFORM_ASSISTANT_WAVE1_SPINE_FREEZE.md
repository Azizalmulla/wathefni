# Platform Assistant Wave 1 — Spine Contract Freeze

**Gate:** `PROD_SYNTHETIC_PLATFORM_ASSISTANT_WAVE1_SPINE_GO`  
**Evidence:** `ops/evidence/platform-assistant-wave1b-prod-canary-20260803T194413Z/`  
**Staging prerequisite:** `ops/evidence/platform-assistant-wave1-staging-20260803T192918Z/` (`STAGING_PLATFORM_ASSISTANT_WAVE1_SPINE_GO`)  
**Freeze:** **GO** for Wave 1 Spine Contract (production synthetic WATHEFNI posture)

## Frozen posture

- One platform assistant spine for **WATHEFNI**, HR dashboard-first
- `WATHEFNI_PLATFORM_ASSISTANT_WAVE1=1`, companies `WATHEFNI`
- Master kill `WATHEFNI_ASSISTANT_KILL` · mutation kill `WATHEFNI_ASSISTANT_MUTATIONS=0`
- Read/prepare only: Unified Action Inbox (default post-hire entry), Employees 360, Setup Launch Readiness
- Grounded envelopes · assistant audit events · EN/AR fallbacks
- No WhatsApp widening · no mobile · no manager/employee assistants · no CK · no AI in frozen module UIs · no new mutation tools
- Payroll money **off** · Attendance ingest **off**

## Proven on production synthetic

- Deploy + migrate/ACK (`assistant_spine_events`); canary residual **0**; durable ACK retained
- Inbox / E360 / Setup readiness read-only tools
- Citations, freshness, authority labels; EN/AR fallbacks
- Tenant isolation; WhatsApp spine tools hidden; mutations hidden; pending confirmations blocked when mutations off
- Master kill + mutation kill
- Rollback verified; redeploy canary green
- Sibling freezes green (Employees 360 / Onboarding / Attendance / Leave / Shifts)

## Explicit NO-GO (outside this freeze)

- Assistant Wave 2 / safe-reads widen / CK wiring
- WhatsApp widening / manager or employee assistants / mobile
- Payroll money · Attendance ingest · frozen-module contract changes

## Rollback

Backup + `ROLLBACK.sh` under `/opt/wathefni/backups/production-pre-platform-assistant-wave1b-*`
