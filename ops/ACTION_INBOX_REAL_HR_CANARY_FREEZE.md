# Unified Action Inbox — Controlled Real-HR Canary Freeze

**Gate:** `PROD_ACTION_INBOX_REAL_HR_CANARY_GO`  
**Evidence:** `ops/evidence/action-inbox-real-hr-canary-20260803T175831Z/`  
**Prerequisites:** `PROD_SYNTHETIC_ACTION_INBOX_WAVE1_GO` · `PROD_ACTION_INBOX_PHASE0_SAFETY_GO`

## Controlled posture (do not widen)

| Control | Value |
|---|---|
| Tenant | `WATHEFNI` only |
| Viewer | Aziz `96599338566` only |
| Subject | Talal `WATHEFNI-96550252254` only |
| Payroll/timesheet | `EXCLUDE_PAYROLL=1` |
| Mutations | forbidden (`mutates_records: false`) |
| Notifications | Alerts & Delivery |
| AI / Wave 2 / money / ingest / shifts-manager expand | **NO-GO** |

## Soft-kill / rollback

- Clear either allowlist → soft-kill (viewer deny or zero person items)
- `WATHEFNI_ACTION_INBOX_WAVE1=0` → API `action_inbox_disabled`
- Backup + `ROLLBACK.sh` under `/opt/wathefni/backups/production-pre-action-inbox-real-hr-*`

## Explicit NO-GO

- Adding any other viewer or employee subject
- Broad HR / manager rollout
- AI inside inbox / mutations / frozen-module reopen
