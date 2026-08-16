# Wave 6 C3 — Freeze Amendment (Benefits Administration)

**Stamp:** `BENEFITS_FULL_PASS`  
**Evidence:** `ops/evidence/benefits-administration-c3-20260812T112934Z`  
**Charter:** `ops/WATHEFNI_HCM_WAVE6_HCM_EXPANSION_BUILD_CHARTER.md` (`WAVE6_HCM_EXPANSION_CHARTER: APPROVED`)  
**Date:** 2026-08-12  

## What freezes with C3

- Benefits plans/versions, eligibility rules/evaluations, enrollment windows, enrollments, coverage periods  
- Dependent coverage **links** (refs only)  
- Contributions + optional payroll handoff instructions  
- Provider/member references (honest internal vs provider-confirmed)  
- Setup Wave 6 Benefits module card + company policy knobs  
- Typed Wave 5 fact outbox for benefits events  
- Flags: `WATHEFNI_BENEFITS_C3` + `WATHEFNI_BENEFITS_COMPANIES`  

## What does **not** change

1. Waves 1–5 remain frozen  
2. C1 Job Architecture + C2 Learning remain frozen  
3. Wave 3 `employee_dependents` remains dependent master SoT  
4. Payroll remains money/execution authority  
5. Claims / adjudication / reimbursement OUT  
6. No ER / Engagement / Comp / WFP product slices yet  
7. Global flags remain off / company-gated; FULL_PASS ≠ broad rollout  

## Rollback

`WATHEFNI_BENEFITS_C3=off` + clear company allowlist; benefits history retained; no payroll rewrite.
