# Shifts MSS C3 — Freeze Amendment

**Status:** AMENDS `ops/SHIFTS_CONTROLLED_ROLLOUT_COMPLETION_AND_FREEZE.md` for Wave 2 **C3 only**  
**Charter:** `WAVE2_WORKFORCE_TRUTH_CHARTER: APPROVED`  
**Pass stamp:** `SHIFTS_MSS_FULL_PASS`  
**Qualify:** `ops/qualify-shifts-mss-c3-staging.sh`

## What changes

| Prior freeze | C3 amendment |
|---|---|
| Scoped manager production scheduling **NO-GO** | Company-scoped MSS via `shifts_mss_c3` after non-empty company + manager allowlists **and** real `manager_scopes` |
| `WATHEFNI_SHIFTS_MANAGER_ALLOWLIST` must stay empty | **Still empty** — C3 uses `WATHEFNI_SHIFTS_MSS_MANAGER_ALLOWLIST` (separate) |
| Global manager unlock banned | **Global** `WATHEFNI_SHIFTS_MSS_C3` stays **off** in systemd; empty `*_COMPANIES` = nobody |

## What does **not** change

1. Existing shift_assignment / open / swap SMs and frozen UX  
2. Self-decision bans  
3. Manager scope fail-closed (`employee_outside_manager_scope`)  
4. Concurrency / stale decision tokens  
5. Wave 6C HR pin (`APPROVED_HR_OPERATORS`) and notify canary boundary  
6. Reminder timers, PAM automation, Payroll money — still NO-GO  
7. Broad employee-app write — still NO-GO (self view/ack/claim/swap remains self-scoped)  
8. Attendance optional — Shifts does not require Attendance  
9. Assistant mutations remain OUT of Wave 2 MVP  

## Enablement sequence (canary only)

1. Seed real `manager_scopes` (+ branch/team/direct members) for the manager  
2. Process-scoped `WATHEFNI_SHIFTS_MSS_C3=on`  
3. `WATHEFNI_SHIFTS_MSS_COMPANIES=<canary>` (non-empty)  
4. `WATHEFNI_SHIFTS_MSS_MANAGER_ALLOWLIST=<manager phones>` (non-empty)  
5. Keep `WATHEFNI_SHIFTS_MANAGER_ALLOWLIST=` empty  

## Rollback

```text
WATHEFNI_SHIFTS_MSS_C3=off
Clear WATHEFNI_SHIFTS_MSS_COMPANIES
Clear WATHEFNI_SHIFTS_MSS_MANAGER_ALLOWLIST
Keep WATHEFNI_SHIFTS_MANAGER_ALLOWLIST empty
```

## Next

Stop for owner review. **Do not start C4 Payroll Authority** until `SHIFTS_MSS_FULL_PASS` is accepted.
