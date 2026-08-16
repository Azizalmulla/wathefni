# Exit Intent C3 — Freeze Amendment

**Status:** FROZEN (qualified 2026-08-12) — AMENDS E360 lifecycle / ESS resign posture for Wave 3 **C3 only**  
**Charter:** `WAVE3_EMPLOYEE_LIFECYCLE_CHARTER: APPROVED`  
**Prior:** C2 `ESS_LETTERS_DEPENDENTS_FULL_PASS` ACCEPTED / frozen  
**Pass stamp:** `RESIGNATION_TERMINATION_FULL_PASS`  
**Qualify:** `ops/qualify-exit-intent-c3-staging.sh`  
**Module:** `wathefni-orchestrator/exit_intent_c3.py`

## What changes

| Prior | C3 amendment |
|---|---|
| HR-only lifecycle terminate; no ESS resign product | Company-scoped exit-intent SM for resignation / termination / EOC |
| Collapsed exit statuses | Explicit: `draft → submitted → pending_approval → approved → notice_period → ready_for_offboarding` (+ rejected/withdrawn/cancelled) |
| Contract expiry silent / ad-hoc | EOC renewal vs non-renewal decisions + pre-expiry tasks; expiry ≠ termination |
| Notice hints only | Versioned notice authority from company Setup policy (legal pack ref required if source=legal_pack) |

## What C3 does **not** do

1. Clearance / Offboarding checklist (C4)  
2. Access revoke / settlement finalize / employee paid  
3. Mark employment `left`/`terminated` on approve or notice  
4. Invent statutory notice / EOS formulas  
5. Real non-synthetic termination (`WATHEFNI_REAL_TERMINATION_CANARY` stays **off**)  
6. Assistant mutations  
7. Require Payroll or Offboarding modules  

## Boundary

C3 ends at **ready_for_offboarding** with OPTIONAL `exit_intent.offboarding_handoff` (deferred when Offboarding absent).

## Enablement (canary / synthetic only)

```text
WATHEFNI_RESIGNATION_ESS_C3=on
WATHEFNI_RESIGNATION_ESS_COMPANIES=<canary>
WATHEFNI_REAL_TERMINATION_CANARY=off
enable_company_exit_intent(...)
```

## Rollback

```text
WATHEFNI_RESIGNATION_ESS_C3=off
Clear WATHEFNI_RESIGNATION_ESS_COMPANIES
disable_company_exit_intent(canary)
Case/notice history retained; employment truth not purged
```

## Next

C3 frozen and owner-accepted 2026-08-12. C4 Offboarding + Clearance may proceed; do not reopen C3.
