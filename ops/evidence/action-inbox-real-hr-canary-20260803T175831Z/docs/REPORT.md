# Action Inbox — controlled real-HR canary

**Stamp:** `20260803T175831Z`  
**Evidence:** `/Users/azizalmulla/Desktop/claw/ops/evidence/action-inbox-real-hr-canary-20260803T175831Z`  
**Prerequisites:** Phase 0-B `PROD_ACTION_INBOX_PHASE0_SAFETY_GO` · Wave 1-B synthetic GO

## Verdicts

| Scope | Verdict |
|---|---|
| Controlled real-HR canary (Aziz / Talal) | **GO** |
| Freeze inbox for controlled real-HR use | **GO** |
| Widen beyond Aziz / Talal | **NO-GO** |
| Broad HR / manager rollout | **NO-GO** |
| AI / mutations / Wave 2 / money / ingest | **NO-GO** |

## Scope

| Control | Value |
|---|---|
| Tenant | `WATHEFNI` |
| Viewer | Aziz `96599338566` |
| Subject | Talal `WATHEFNI-96550252254` |
| Payroll exclude | `EXCLUDE_PAYROLL=1` |

## Items shown (Aziz live payload)

Total: **6**
By source: `{"compliance": 5, "onboarding": 1}`
By system_of_action: `{"onboarding": 6}`

| id | source | SoA | employee | severity | what | deep_link |
|---|---|---|---|---|---|---|
| `compliance:missing:WATHEFNI-96550252254:civil_id` | compliance | onboarding | `WATHEFNI-96550252254` | medium | Talal Fadhli's Civil ID is missing | onboarding |
| `compliance:missing:WATHEFNI-96550252254:medical` | compliance | onboarding | `WATHEFNI-96550252254` | medium | Talal Fadhli's Medical certificate is missing | onboarding |
| `compliance:missing:WATHEFNI-96550252254:passport` | compliance | onboarding | `WATHEFNI-96550252254` | medium | Talal Fadhli's Passport is missing | onboarding |
| `compliance:missing:WATHEFNI-96550252254:residence` | compliance | onboarding | `WATHEFNI-96550252254` | medium | Talal Fadhli's Residence is missing | onboarding |
| `compliance:missing:WATHEFNI-96550252254:work_permit` | compliance | onboarding | `WATHEFNI-96550252254` | medium | Talal Fadhli's Work permit is missing | onboarding |
| `employees:WATHEFNI-96550252254:onboarding:incomplete` | onboarding | onboarding | `WATHEFNI-96550252254` | medium | Onboarding incomplete | onboarding |

Summary counters: total=6 · by_source={"compliance":5,"onboarding":1} · by_soa={"onboarding":6}

## Privacy / scope

- Fouad + other non-allowlisted viewers → `action_inbox_viewer_denied`
- All inbox employee keys = Talal only (Analytics / Compliance / E360 filtered)
- No payroll/timesheet SoA rows
- Deep links permission-safe pages only (no payroll page under exclude)
- Soft-kill: clear viewer → deny; clear subject → zero person items
- `ACTION_INBOX_WAVE1=0` → `action_inbox_disabled`
- Residual canary ACK = 0; sibling freezes green

## Proof bits

- Canary before rollback fail=0 → 1
- Rollback verified (allowlists empty) → 1
- Canary after redeploy fail=0 → 1
- Final Aziz/Talal flags → 1
- Sibling freezes → 1

## Rollback

`/opt/wathefni/backups/production-pre-action-inbox-real-hr-*` + `ROLLBACK.sh`
