# RESIGNATION_TERMINATION_FULL_PASS

**Status:** ACCEPTED by owner 2026-08-12 — C3 remains **FROZEN** (do not reopen for C4+)  
**Date:** 2026-08-12  
**Evidence:** `ops/evidence/exit-intent-c3-20260811T211012Z`  
**Charter:** `WAVE3_EMPLOYEE_LIFECYCLE_CHARTER: APPROVED`  
**Prior:** C2 `ESS_LETTERS_DEPENDENTS_FULL_PASS` ACCEPTED / frozen  
**Freeze amendment:** `ops/EXIT_INTENT_C3_FREEZE_AMENDMENT.md`  
**Qualify:** `ops/qualify-exit-intent-c3-staging.sh`  
**Module:** `wathefni-orchestrator/exit_intent_c3.py`  
**Alias intent:** exit-intent / `EXIT_INTENT` product boundary (charter stamp name retained)

## Proven (63/63 staging, synthetic)

1. Global OFF + empty allowlist deny; `WATHEFNI_REAL_TERMINATION_CANARY` remains OFF (blocked if on)
2. Employee resignation draft → submit → pending_approval (employment stays active)
3. SoD self-approve forbidden; stale/concurrent decision blocked
4. Resignation approve / reject / permitted withdraw; withdraw blocked after notice
5. Notice period + versioned notice amend audit; ready_for_offboarding
6. OPTIONAL Offboarding handoff deferred when module absent — not clearance/paid/closed
7. HR termination initiation + SoD + approve/reject/cancel; non-HR blocked
8. EOC renewal (keeps active); EOC non-renewal → notice → ready
9. Non-synthetic subjects blocked; legal_pack notice without pack ref refused
10. Payroll/Offboarding not required; history intact after rollback; EN/AR labels

## Posture

- Synthetic qualification only — **no real employment=left/terminated**
- Canary company-scoped; global C3 OFF in systemd
- C3 ends at ready_for_offboarding — clearance/access/settlement = C4+
- Assistant mutations OUT

## Stop

Owner accepted. C3 remains frozen. C4 Offboarding + Clearance proceeded under charter §15.
