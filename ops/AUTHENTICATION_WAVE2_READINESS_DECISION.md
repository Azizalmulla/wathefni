# Authentication Wave 2 — formal readiness decision

Date: 2026-08-06 · Paired evidence:
`ops/evidence/bank-ess-onboarding-completion-20260806T052304Z/`
Plan under gate: `ops/AUTHENTICATION_WAVE2_AUDIT_AND_PLAN.md`

## Decision

**Auth Wave 2 remains `blocked`.** Its two named dependencies are now
production-qualified, but two gate conditions are not satisfied by evidence.

## Gate conditions

| condition | status | evidence |
|---|---|---|
| Bank ESS production-qualified | met | 43/43 live cases, canary scope |
| Onboarding completion production-qualified | met | 27/27 live cases |
| Permissions proven | met | HR decisions via real `dashboard_context`; unauthorized employee, unauthorized HR (401), non-owner withdraw (403) |
| Tenant isolation proven | met | unknown-key 404, zero cross-tenant storage rows, HR cross-tenant 404 |
| Sensitive-data handling proven | met | sealed at rest, masked by default, no plaintext in effective rows or notifications, private evidence storage, retention purge + cascade |
| Retry / idempotency proven | met | create replay, apply replay leaves one effective row, recompute writes no duplicate event, reminder dedup key stable |
| Mobile + Arabic critical paths proven | **partial** | Arabic strings and the mobile projection contract are proven at the API layer; no employee-mobile device pass for the bank screens or the new completion block |
| Existing / partially onboarded employees migrate safely | **not proven** | no backfill has been run: 51 real employees have snapshots only where activity touched them; legacy completed employees have no `first_completed_at`, so a later requirement change shows `waiting_on_*` rather than `reopened` |
| No downstream payroll or employee-profile regression | met | 16 suites green including employees360 and onboarding freeze regressions; the ESS concurrency regression found during this run is fixed and covered |

## What must close before Auth Wave 2 starts

1. **Completion backfill for existing employees.** Run `recompute()` across all
   active employees so every employee has a canonical snapshot, and stamp
   `first_completed_at` for those already complete. Without it, `reopened` is
   unreachable for the legacy population — and Auth Wave 2 is expected to gate
   access on completion, so a legacy employee could be judged by a state the
   contract cannot yet express for them.
2. **Employee-mobile device pass** for the bank ESS screens and the onboarding
   completion block, EN + AR, LTR + RTL, on the Aziz/Talal canary, per the
   continuous-wave process.

Both are prerequisites, not blockers of the work already qualified.

## Why the gate is not waived

Auth Wave 2 intends to make access decisions downstream of onboarding
completion. A completion contract that is correct for new employees but silent
for the legacy population is not yet a safe dependency for an authentication
decision: the failure mode is locking out or wrongly admitting existing staff.
The contract is proven; its coverage of the existing population is not.
