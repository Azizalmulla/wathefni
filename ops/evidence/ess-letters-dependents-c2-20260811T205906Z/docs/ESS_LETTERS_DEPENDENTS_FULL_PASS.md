# ESS_LETTERS_DEPENDENTS_FULL_PASS

**Status:** QUALIFIED 2026-08-11 — awaiting owner acceptance; **stop before C3**  
**Date:** 2026-08-11  
**Evidence:** `ops/evidence/ess-letters-dependents-c2-20260811T205906Z`  
**Charter:** `WAVE3_EMPLOYEE_LIFECYCLE_CHARTER: APPROVED`  
**Prior:** C1 `EMPLOYMENT_CHANGE_FULL_PASS` ACCEPTED / frozen  
**Freeze amendment:** `ops/ESS_LETTERS_DEPENDENTS_C2_FREEZE_AMENDMENT.md`  
**Qualify:** `ops/qualify-ess-letters-dependents-c2-staging.sh`  
**Module:** `wathefni-orchestrator/ess_letters_dependents_c2.py`

## Proven (65/65 staging)

1. Global OFF + empty allowlist deny (fail closed)
2. Employee requests letter → under_review → SoD / stale → approved
3. `letters_fulfill` OFF blocks issue (no silent invent)
4. HR fulfills → issued immutable artifact; employee download; self-scope
5. Correction creates new version; prior hash intact
6. EN/AR template/output path (experience letter AR)
7. Reject / cancel honest paths
8. Salary certificate without payroll; with OPTIONAL payroll contract truth
9. Dependents add/edit/archive; duplicate + stale protection
10. Employee-requested dependent change + HR review + SoD
11. Feature visibility hides disabled dependents; module-off after disable preserves history
12. Letters independent of Offboarding/Benefits; Assistant mutations OUT

## Posture

- Canary only — **no broad enable**
- Production systemd: global C2 remains **OFF**
- Templates/policies = Setup placeholders only (no invented legal claims)
- Benefits / insurance dependents = OUT (Wave 6)
- Real non-synthetic termination remains **dark**

## Stop

**Do not start C3 Resignation / Termination / EOC** until owner accepts this stamp.
