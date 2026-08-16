# Offboarding C4 — Freeze Amendment

**Status:** FROZEN (qualified 2026-08-12) — NEW commercial module `offboarding` for Wave 3 **C4 only**  
**Charter:** `WAVE3_EMPLOYEE_LIFECYCLE_CHARTER: APPROVED`  
**Prior:** C3 `RESIGNATION_TERMINATION_FULL_PASS` ACCEPTED / frozen  
**Pass stamp:** `OFFBOARDING_FULL_PASS`  
**Qualify:** `ops/qualify-offboarding-c4-staging.sh`  
**Module:** `wathefni-orchestrator/offboarding_c4.py`

## What changes

| Prior | C4 amendment |
|---|---|
| Exit intent ends at `ready_for_offboarding` with deferred handoff | Canonical `offboarding_case` from exit intent (1:1; duplicate handoff idempotent) |
| No clearance product | Clearance **sub-workflow** inside Offboarding (required/optional, deps, waive, reject/return) |
| Impact preview ≠ clearance | Explicit Setup template items — not cosmetic status toggles |
| Identity revoke undefined | OPTIONAL manual IT confirm and/or IdP adapter request/ack (request ≠ revoked) |

## What C4 does **not** do

1. Full Asset Management product (clearance refs only)  
2. Treat revoke-requested as access revoked without ack  
3. Imply settlement finalized / paid / exit interview on completion  
4. Silently mark employment left  
5. Invent company checklist in code — templates belong to Setup  
6. Unlock real non-synthetic termination  
7. Require Payroll or IdP adapter  
8. Assistant mutations  

## Case SM

```text
not_started → in_progress → blocked | ready_to_close → completed
(+ cancelled)
```

`ready_to_close` only when all **required** items are `completed|waived`.

## Enablement (canary / synthetic)

```text
WATHEFNI_OFFBOARDING_C4=on
WATHEFNI_OFFBOARDING_COMPANIES=<canary>
WATHEFNI_REAL_TERMINATION_CANARY=off
WATHEFNI_OFFBOARDING_KILL=off
enable_company_offboarding(...)
```

## Rollback

```text
WATHEFNI_OFFBOARDING_C4=off
Clear WATHEFNI_OFFBOARDING_COMPANIES
disable_company_offboarding(canary)
# optional immediate block:
WATHEFNI_OFFBOARDING_KILL=on
History retained
```

## Next

C4 frozen after qualify. **Stop for owner review before C5 Exit Close / settlement ack/waiver / exit interview.**
