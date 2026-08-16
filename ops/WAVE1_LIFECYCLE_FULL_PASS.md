# Wave 1 Full Lifecycle Qualification

**Status:** QUALIFIED — `WAVE1_LIFECYCLE_FULL_PASS` (backend authority chain)  
**Evidence:** `ops/evidence/wave1-lifecycle-full-20260811T190225Z`  
**Qualify:** `ops/qualify-wave1-lifecycle-full-staging.sh`

## Proven chain

Requisition → approval (SoD) → Job link + publish gate → Candidate app (soft) → Offer accept bridge → `pending_start` → Preboarding ready → Hire (same `employment_id`) → Onboarding auto-start → 30/60/90 → Probation confirm.

## Modularity

- Without Offers (manual future joiner)
- Without Onboarding (clean skip)
- Without Requisitions (publish gate not required)
- `pending_start` never active early

## Superseded for product completion

This stamp proves the **canonical authority lifecycle** on staging with process-scoped canaries.

Product acceptance (surfaces + Setup + modularity + canary seed + regressions) is stamped separately as **`WAVE1_PRODUCT_FULL_PASS`** — see `ops/WAVE1_PRODUCT_FULL_PASS.md` / `ops/WAVE1_PRODUCT_FREEZE.md`.  
Wave 2 remains blocked pending owner sign-off on that product stamp.
