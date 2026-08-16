# Attendance Wave 3 — HR/Manager Ops Qualify

**Stamp:** 20260802T113543Z
**Scope:** local + staging only (no production deploy, no real clocking, no devices)

## Results
- local: 56/56 passed, 0 failed
- staging: 55/55 passed, 0 failed
- staging migrate: OK
- staging postgres ops smoke: OK
- staging Employees 360 freeze: OK
- staging onboarding freeze: pre-existing staging app.py drift noted (local onboarding freeze green)

## State model
Exception kinds: missing_check_in/out, ambiguous_punches, incomplete_session, absence, lateness, early_leave, connector_issue.

Statuses: open → assigned → in_review → pending_dual_approval → resolved|rejected|reopened → closed.

Correction cases: requested → review(approve|reject) → **apply** (separate, idempotent).

Disputes: raise → resolve(upheld|overturned) → optional reopen with evidence.

## Permission / ownership matrix
| Actor | Open/assign | Request | Review | Apply | Dispute | Reopen |
|-------|-------------|---------|--------|-------|---------|--------|
| HR | yes | yes | yes | yes | resolve | yes |
| Manager (configured + Employees 360 scope) | yes | yes (not self) | yes (not self) | yes (not self) | resolve | limited |
| Manager unconfigured / out of scope / self | deny | deny | deny | deny | deny | deny |
| Employee | — | — | — | — | raise | — |

Ownership fields: owner_phone, priority, due_at, status. Dual approval for absence/early_leave.

## Workflow
1. Projection/connector opens exception (`payroll_excluded=true`).
2. Assign owner; request correction (authority correction + ops case; before snapshot).
3. Review approve/reject **without** applying punches.
4. Apply (idempotent) writes correction punches + new day-projection version (after snapshot).
5. Dispute → resolution; reopen if new evidence and period unlocked.

## Rules enforced
- Raw punches immutable; corrections create new projection versions
- Incomplete/disputed excluded from payroll
- Locked payroll periods deny mutation
- Leave reversal preserves later manual corrections
- Optimistic concurrency (`row_version`) fail-closed
- Tenant isolation by `company_code`

## Remaining blockers
- none for staging ops qualification

## GO/NO-GO — WATHEFNI-only production **synthetic** ops canary
**CONDITIONAL GO**

Required for any future prod canary (not executed in this wave):
- Keep `CAPTURE_INGEST=off`, `AUTHORITY_SYNTHETIC_ONLY=on`, ops synthetic markers only
- No customer devices, no real clocking, no QR/GPS/kiosk

**Real clocking / customer devices / full Attendance UI redesign: NO-GO**
