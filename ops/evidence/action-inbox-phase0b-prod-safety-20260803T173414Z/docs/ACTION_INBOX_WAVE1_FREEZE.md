# Unified Action Inbox Wave 1 — Freeze

**Gate:** `PROD_SYNTHETIC_ACTION_INBOX_WAVE1_GO`  
**Evidence:** `ops/evidence/action-inbox-wave1b-prod-canary-20260803T170914Z/`  
**Phase 0-B:** `PROD_ACTION_INBOX_PHASE0_SAFETY_GO` → `ops/evidence/action-inbox-phase0b-prod-safety-20260803T173414Z/`  
**Freeze:** **GO** for Wave 1 Unified Action Inbox (synthetic-only + Phase 0 fail-closed gates)

## Frozen posture

- Read-only composition of Analytics attention[], Compliance findings[], Employees 360 next actions
- Inbox **composes and ranks only** — frozen modules remain systems of action
- `WATHEFNI_ACTION_INBOX_WAVE1=1`, `SYNTHETIC_ONLY=1`, markers `AIW1` / phones `965542*`
- Phase 0: empty viewer/subject allowlists, `EXCLUDE_PAYROLL=1`
- `mutates_records`: **false**
- Alerts & Delivery owns notifications
- Hiring Reports stay separate
- No AI; no Compliance Wave 2; no Analytics Wave 2
- No Payroll money work; no Attendance ingest; no Shifts manager expansion

## Proven on production

- Wave 1-B synthetic compose/rank + ACK residual 0
- Phase 0-B: API denial + nav hide with empty allowlists; payroll/timesheet exclusion;
  soft-kill clear; `ACTION_INBOX_WAVE1=0` kill switch; rollback + redeploy
- Sibling freezes green

## Explicit NO-GO (outside this freeze)

- Another differentiation wave
- AI inside Action Inbox
- Mutations from inbox
- Compliance Wave 2 / Analytics Wave 2
- Payroll money work / Attendance ingest / Shifts manager expansion
- Reopening frozen module boundaries
- Real HR production canary without **separate** explicit Aziz/Talal change-control

## Rollback

Phase 0-B: `/opt/wathefni/backups/production-pre-action-inbox-phase0b-*` + `ROLLBACK.sh`  
Wave 1-B: `/opt/wathefni/backups/production-pre-action-inbox-wave1b-*` + `ROLLBACK.sh`
