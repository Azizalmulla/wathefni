# Unified Action Inbox Wave 1 — Freeze

**Gate:** `PROD_SYNTHETIC_ACTION_INBOX_WAVE1_GO`  
**Evidence:** `ops/evidence/action-inbox-wave1b-prod-canary-20260803T170914Z/`  
**Freeze:** **GO** for Wave 1 Unified Action Inbox (synthetic-only production posture)

## Frozen posture

- Read-only composition of Analytics attention[], Compliance findings[], Employees 360 next actions
- Inbox **composes and ranks only** — frozen modules remain systems of action
- `WATHEFNI_ACTION_INBOX_WAVE1=1`, `SYNTHETIC_ONLY=1`, markers `AIW1` / phones `965542*`
- `mutates_records`: **false**
- Alerts & Delivery owns notifications
- Hiring Reports stay separate
- No AI; no Compliance Wave 2; no Analytics Wave 2
- No Payroll money work; no Attendance ingest; no Shifts manager expansion

## Proven on production synthetic

- ACK migrate (`action_inbox_wave_acks`) with production ACK
- Cross-source ranking, E360 dedupe, clears-on-resolve
- Owner / deadline / escalation / evidence / authority labels + deep links
- Freshness / as_of (Asia/Kuwait), EN/AR, mobile web responsive shell
- Tenant/manager scope wiring; residual canary ACK = 0
- Rollback verified; redeploy canary green
- Sibling freezes green (Analytics / Compliance / Employees 360 / Onboarding / Attendance / Leave / Shifts / Payroll)

## Explicit NO-GO (outside this freeze)

- Another differentiation wave
- AI inside Action Inbox
- Mutations from inbox
- Compliance Wave 2 / Analytics Wave 2
- Payroll money work / Attendance ingest / Shifts manager expansion
- Reopening frozen module boundaries
- Real HR production rollout (synthetic-only until separate change-control)

## Rollback

Backup + `ROLLBACK.sh` under `/opt/wathefni/backups/production-pre-action-inbox-wave1b-*`  
(Drop-in removal restores pre-Wave-1 Action Inbox flags; durable wave ACK rows retained.)
