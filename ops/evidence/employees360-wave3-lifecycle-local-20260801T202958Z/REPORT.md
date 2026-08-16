# Employees 360 Wave 3 — Employment lifecycle (local/staging)

**Stamp:** `20260801T202958Z`  
**Evidence:** `ops/evidence/employees360-wave3-lifecycle-local-20260801T202958Z/`  
**Mode:** Local implementation + staging synthetic qualification  
**Production deploy:** **NOT DONE** (explicitly out of scope)

Builds on live Wave 2 person / employment / assignment authority.

---

## Verdict

**PASS** (local/staging)

| Gate | Result |
|---|---|
| Lifecycle state model (pending_start → … → terminated) | PASS |
| Two-person approval preserved | PASS |
| Normal termination (effective today → terminated, hub `left`) | PASS |
| Future-dated termination → `notice_period`, hub stays `active` | PASS |
| Cancel pending request before approval | PASS |
| Cancel scheduled termination before effective (reversal) | PASS |
| Reversal after termination (same employment) | PASS |
| True rehire: same `person_id`, new `employment_id` + `assignment_id` | PASS |
| Prior service history immutable (prior employment stays terminated) | PASS |
| Downstream impact preview accurate + non-automatic | PASS |
| Idempotent retries / conflict on payload reuse | PASS |
| Stale concurrency fail-closed (409) | PASS |
| Out-of-scope manager fail-closed (404) | PASS |
| Cross-tenant fail-closed | PASS |
| WATHEFNI-only flag allowlist | PASS |
| Rollback clears Wave 3 overlays; Wave 2 authority survives | PASS |
| Unit tests | PASS (22/22) |
| Staging smoke | PASS (51/51) |
| Production | **Not deployed** |
| Wave 4 / Employees 360 redesign | **Not started** |

---

## Lifecycle state model

Canonical state lives on `employee_employments.lifecycle_state`.

| State | Meaning | Hub projection (`employees.employment_status`) |
|---|---|---|
| `pending_start` | Hired, not yet started | `active` |
| `active` | In service | `active` |
| `notice_period` | Termination scheduled / notice running | `active` |
| `suspended` | Justified suspension | `active` |
| `terminated` | Employment ended | `left` |

Compatibility rule: **only** `terminated` projects to hub `left`. Existing modules that only understand `active|left` keep working.

Optimistic concurrency: `lifecycle_version` + hub `updated_at` (expected tokens on every mutation request).

Termination metadata (effective-dated, auditable):

- `termination_effective_on`, `last_working_day`
- `termination_type` ∈ resignation | dismissal | end_of_contract | mutual | other
- `termination_reason`, `notice_starts_on`
- Suspension: `suspended_on`, `suspension_reason`

Events append-only in `employee_lifecycle_events`.

---

## API and workflow design

Flag: `WATHEFNI_EMPLOYEE_LIFECYCLE_V3=on` + `WATHEFNI_EMPLOYEE_LIFECYCLE_V3_COMPANIES=WATHEFNI`  
Requires Wave 2: `WATHEFNI_EMPLOYEE_AUTHORITY_V2=on` for the same company.

### Endpoints (dashboard)

| Method | Path | Actor |
|---|---|---|
| GET | `/dashboard/posthire/employees/{key}/lifecycle` | `employees.manage` + scope |
| GET | `/dashboard/posthire/employees/{key}/lifecycle/impact-preview` | `employees.manage` + scope |
| GET | `/dashboard/posthire/employee-lifecycle/pending` | manage or `employees.status.approve` |
| POST | `/dashboard/posthire/employees/{key}/lifecycle/requests` | manage + scope |
| POST | `/dashboard/posthire/employee-lifecycle/requests/{id}/cancel` | requester |
| POST | `/dashboard/posthire/employee-lifecycle/requests/{id}/decide` | designated approver + `employees.status.approve` |

### Case types

`termination` | `reversal` | `rehire` | `notice` | `suspension` | `unsuspend` | `activate_start`

### Workflow

1. Requester creates case + request with idempotency key, expected lifecycle version/state, hub `updated_at`, reason, approval reference, designated approver.
2. Impact snapshot captured at request time (preview only).
3. Approver approve/reject; self-approval forbidden; only designated approver may decide.
4. Approve path re-checks concurrency tokens (stale → 409 fail-closed).
5. Future termination → `notice_period` + stored effective date; due date applied by `execute_due_scheduled_terminations`.
6. Immediate/past effective → `terminated` now.
7. Reversal restores **same** employment (never invents a new one).
8. Rehire requires terminated prior employment; creates **new** employment + assignment under **same** `person_id` (Wave 2 `open_rehire_employment`); prior row remains terminated.

Module: `wathefni-orchestrator/employee_lifecycle_wave3.py`  
Schema version: `employees360-wave3-lifecycle-v1`

---

## Downstream impact rules

`preview_downstream_impact` is **read-only**. Every domain sets `automatic: false`. Disclaimer: no legal/payroll decisions.

| Domain | Assessed | Recommended action (explicit, reversible) |
|---|---|---|
| Future shifts | `shift_assignments` where `shift_date >= as_of` | review_and_cancel_or_reassign |
| Open leave | pending/approved/open/requested overlapping as_of | review_pending_leave |
| Leave balances | `leave_balances` / `leave_ledger` row counts | manual_final_settlement_input |
| Attendance exceptions | recent pending/late/early rows | resolve_exceptions |
| Payroll timesheets | draft/open/pending/submitted | finalize_or_hold_timesheets |
| Onboarding | open onboarding items (if table present) | close_or_waive_open_items |
| Compliance | missing/pending/expired docs (if present) | review_missing_or_expired_docs |
| Documents | retained document count | retain_per_policy |
| App access | active sessions + open invites | revoke_sessions_and_invites_on_effective_termination |

Offboarding case stores `impact_snapshot_id` on the lifecycle case. No domain is auto-mutated by Wave 3.

---

## True rehire vs reactivation

| Path | Behavior |
|---|---|
| Reversal | Same `employment_id` / `assignment_id`; clears termination fields; hub → `active` |
| Rehire | **Forbidden** while not terminated; reuses `person_id`; mints new `employment_id` + `assignment_id` + hub key; prior employment stays `terminated`/`left` |

No simple `left → active` reactivation for rehire.

---

## Tests and evidence

| Artifact | Path |
|---|---|
| Unit (22) | `verify/unit.log`, `tests/smoke-test-employee-wave3-lifecycle-unit.py` |
| Staging smoke (51) | `verify/staging-smoke.log`, `tests/smoke-test-employee-wave3-lifecycle.py` |
| Schema DDL | `schema/wave3-lifecycle-schema.sql` |
| Module diff | `diff/employee_lifecycle_wave3.py` |
| Approver eligibility fix | `diff/employee_status_approval.py` (SELECT `*` so grants resolve) |
| Staging SHAs | `verify/staging-shas.txt` |
| Prod not deployed | `verify/prod-not-deployed.txt` |
| API routes | `verify/api-routes.txt` |

Staging qualification used synthetic WATHEFNI employees only; cleanup in `finally`. Staging service was **not** permanently flag-enabled; smoke sets flags in-process. Staging received module copies for qualification only.

---

## Remaining legal / product decisions

1. **Notice period length / statutory notice** — not computed; operators supply effective date and LWD.
2. **Final settlement / end-of-service** — impact preview exposes leave/payroll inputs only; no calculation or payment instruction.
3. **Suspension grounds** — reason required; legal justification matrix not encoded.
4. **App access revoke timing** — recommended on effective termination; not auto-executed.
5. **Rehire phone / hub key policy** — default mints `{COMPANY}-{digits}-Rxxxx` to avoid PK collision; product may prefer same phone with superseded map.
6. **Document retention / legal hold** — retain_per_policy only; no deletion.
7. **Whether `pending_start` is required for all hires** — supported; not forced on existing Wave 2 actives.
8. **Scheduler ops** — `execute_due_scheduled_terminations` exists; cron/ops ownership undecided.
9. **Cross-module hard cutover** — child tables still key off hub `employee_key`; Wave 4 territory.

---

## Rollback

`rollback_lifecycle_wave3(company, idempotency_key, employee_keys=…)`:

- Deletes Wave 3 cases/requests/events/impact snapshots for scoped keys
- Resets lifecycle overlay fields to Wave 2-compatible `active`/`terminated` from authority `employment_status`
- Does **not** destroy Wave 2 persons/employments/assignments or hub business history

---

## Explicit non-goals (honored)

- No production deploy
- No Wave 4
- No Employees 360 UI redesign
- No automatic legal or payroll decisions
- No destructive overwrite of prior employment history
- Pre-hire / Wave D untouched
