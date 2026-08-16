# Action Inbox Phase 0 — Real-canary safety gates

**Staging gate:** `STAGING_ACTION_INBOX_PHASE0_GO`  
**Production gate:** `PROD_ACTION_INBOX_PHASE0_SAFETY_GO`  
**Evidence (prod):** `ops/evidence/action-inbox-phase0b-prod-safety-20260803T173414Z/`  
**Real-HR canary:** **not enabled** (viewer/subject allowlists empty on production)

## Gates (fail-closed)

| Control | Env | Empty behavior |
|---|---|---|
| Viewer allowlist | `WATHEFNI_ACTION_INBOX_REAL_VIEWER_ALLOWLIST` | API `action_inbox_viewer_denied` + nav hidden |
| Subject allowlist | `WATHEFNI_ACTION_INBOX_REAL_SUBJECT_ALLOWLIST` | No person-scoped items |
| Payroll exclude | `WATHEFNI_ACTION_INBOX_EXCLUDE_PAYROLL` (default on) | No payroll/timesheet SoA rows |
| Wave kill | `WATHEFNI_ACTION_INBOX_WAVE1=0` | API `action_inbox_disabled` |

Approved boundary (code-pinned): viewer `96599338566` / Talal `WATHEFNI-96550252254` only.

## Future canary (separate change-control)

Set both allowlists to Aziz + Talal on production **only** after a dedicated real-HR canary qualify. Soft-kill = clear allowlists.

## Explicit NO-GO in this phase

- Enabling lasting real-HR canary / populating production allowlists
- AI / new differentiation wave
- Compliance/Analytics Wave 2
- Payroll money / Attendance ingest / Shifts manager expansion
