# Shifts Visual & UX Wave 2 — Interaction Quality (IQ-12)

**Stamp:** `20260804T155956Z`  
**Evidence:** `ops/evidence/shifts-wave2-iq-prod-deploy-20260804T155956Z/`  
**Live:** `PostHire-DWa5FLLn.js`  
**Backup:** `/opt/wathefni/backups/production-pre-shifts-wave2-iq-20260804T155956Z/`  
**Smoke:** `SHIFTS_WAVE2_IQ_SMOKE_OK` (+ Wave 1 + Interaction Quality rechecks green)  
**Prerequisite:** Shifts Wave 1 UX Closure `20260804T082135Z` · Interaction Quality Wave 1 `20260804T154835Z`

## Verdict

| Gate | Result |
|---|---|
| Production UI deploy | **GO** |
| Safe smoke | **GO** |
| Wave 1 regression | **GO** |
| IQ Wave 1 regression | **GO** |
| Scheduling authority / backend contracts | **NO-GO** (unchanged) |
| Final palette | **NO-GO** (not started) |

## IQ-12 resolved

| Finding | Fix |
|---|---|
| Filter thrash | Debounced employee search (300ms); soft-keep board content while refreshing |
| Filters / date reset | Filter + week/day chrome unchanged across soft reload |
| Drawer disappearance | Sticky `selectedSnapshot` rematch; history soft-keep; close only on user dismiss / cancel success |
| Incomplete confirmation | `needs_confirmation` → governed confirm → ack merge → re-submit (no idle info toast exit) |
| Dialogs close before success | Soft-cancel / recon cancel / materialize use `confirm({ run })` |
| Double submit | Guard `actionBusy` / `rowBusy`; pending on swap actions |
| Layout jumps | Absolute `data-shifts-updating` overlay (no strip reflow) |
| Outcome clarity | Success / error / `Cancelled` notices |

## Non-goals (held)

- Scheduling authority, concurrency tokens, allowlists  
- Payroll money / PAM auto-submit / timers  
- Final palette pass  

## Rollback

```bash
bash /opt/wathefni/backups/production-pre-shifts-wave2-iq-20260804T155956Z/ROLLBACK.sh \
  /opt/wathefni/backups/production-pre-shifts-wave2-iq-20260804T155956Z
```
