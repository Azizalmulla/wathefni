# Exit Close C5 — Freeze Amendment

**Status:** FROZEN (qualified pending stamp) — AMENDS Offboarding completion / employment-left posture for Wave 3 **C5 only**  
**Charter:** `WAVE3_EMPLOYEE_LIFECYCLE_CHARTER: APPROVED`  
**Prior:** C4 `OFFBOARDING_FULL_PASS` ACCEPTED / frozen  
**Pass stamp:** `EXIT_CLOSE_HANDOFF_FULL_PASS`  
**Qualify:** `ops/qualify-exit-close-c5-staging.sh`  
**Module:** `wathefni-orchestrator/exit_close_c5.py`

## What changes

| Prior | C5 amendment |
|---|---|
| Offboarding `completed` ≠ employment left | Sole close authority: `pending_close → ready_to_close → closed` sets employment `left` |
| Settlement finalize floating | OPTIONAL settlement ack/waiver consuming Wave 2 C6; finalized ≠ ack ≠ paid |
| No exit interview product | Lightweight invite/complete/decline/skip (non-blocking default) |
| No alumni episode | `employment_alumni_episodes` with rehire eligibility + person_key continuity |

## What C5 does **not** do

1. Unlock real non-synthetic termination  
2. Invent fake settlement rows to unblock close  
3. Equate finalized/ack with paid  
4. Require Payroll / IdP / Exit Interview universally  
5. Build Alumni portal or Engagement product  
6. Silently reopen closed employment  
7. Revoke real user sessions in synthetic qualify  
8. Assistant mutations  

## Enablement (canary / synthetic)

```text
WATHEFNI_EXIT_CLOSE_C5=on
WATHEFNI_EXIT_CLOSE_COMPANIES=<canary>
WATHEFNI_REAL_TERMINATION_CANARY=off
enable_company_exit_close(...)
```

## Rollback

```text
WATHEFNI_EXIT_CLOSE_C5=off
Clear WATHEFNI_EXIT_CLOSE_COMPANIES
disable_company_exit_close(canary)
Closed employment + alumni/interview history retained
```

## Next

C5 frozen after qualify. **Stop for owner review before C6 Wave 3 Product Acceptance.** Real termination remains dark.
