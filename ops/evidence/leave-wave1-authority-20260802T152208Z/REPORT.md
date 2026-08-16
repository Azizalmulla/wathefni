# Leave Wave 1 — Authority & safety hardening (local/staging)

**Stamp:** `20260802T152208Z`  
**Evidence:** `ops/evidence/leave-wave1-authority-20260802T152208Z/`  
**Scope:** Local + **staging only** (`wathefni_staging`). No production deploy.  
**Flags:** `balances_enforced=false`, `legal_reviewed=false` (hard). No `enforced=true`.

---

## Verdict

| Gate | Result |
|---|---|
| Staging migrate schema pack `1.0.0` | **PASS** (`MIGRATE_OK`) |
| Staging smoke `smoke-test-leave-authority-wave1.py` | **PASS** `51/51` |
| Employees 360 freeze regression | **PASS** `57/57` |
| Onboarding freeze regression | **PASS** `54/54` |
| Attendance freeze regression | **PASS** `26/26` |
| Production deploy / `enforced=true` | **Not done** (out of scope) |
| **WATHEFNI-only production synthetic canary** | **GO** (code-only; synthetic leave rows; balances remain observe-only; no UI redesign; no frozen-module behavior change beyond leave-side lifecycle reverse→`requested`) |

---

## Canonical type catalogue

| Canonical | Ledger eligible | Maps from (aliases) |
|---|---|---|
| `annual` | yes | `vacation`, `holiday`, `time_off`, `timeoff`, `personal`, `pto`, `annual_leave` |
| `sick` | yes | `medical`, `ill`, `sick_leave` |
| `unpaid` | no (catalogue only; no unpaid workflow) | `unpaid_leave` |
| `other` | no | unknown free-text |

**History rule:** stored `leave_type` on existing rows is **not rewritten**. Runtime `canonicalize_leave_type()` maps aliases for new writes, ledger observe, and metadata `leave_type_canonical`.

Module: `wathefni-orchestrator/leave_authority_wave1.py` · SQL pack: `ops/sql/leave_authority_wave1_v1.sql`

---

## Final state model

Primary statuses:

`requested` → `approved` | `rejected` | `cancelled` | `expired_stale` | `needs_review` | `declined_lifecycle`

| Status | Meaning |
|---|---|
| `requested` | Awaiting decision |
| `needs_review` | Stale-pending policy promoted past-start requests for human review |
| `approved` / `rejected` / `cancelled` | Terminal decision outcomes (cancel also from approved) |
| `expired_stale` | Deterministic stale-pending expiry |
| `declined_lifecycle` | Lifecycle downstream; **not** decidable via approve/reject |

**Decidable:** `requested`, `needs_review`  
**Cancelable:** `requested`, `approved`, `needs_review`  
**Forbidden bypass:** reverse of `declined_lifecycle` restores `requested` / `approved` / `needs_review` — **never** `pending`.

Optimistic concurrency: `leave_requests.row_version` required match on approve/reject/cancel when `expected_row_version` supplied; mismatch → `stale_row_version` (fail closed).

---

## Lifecycle policy

Company settings table `leave_authority_settings` (defaults all **block=true**):

| Setting | Default |
|---|---|
| `block_terminated` | true |
| `block_suspended` | true |
| `block_future_start` | true |
| `block_notice_period` | true |
| `stale_pending_action` | `expire` (`expired_stale`) or `needs_review` |
| `balances_enforced` | **false** (API hard) |
| `legal_reviewed` | **false** (API hard) |

Gates apply on **request** and **approve**. Labels resolved from hub `employment_status` + `employee_employments.lifecycle_state` / start dates.

---

## Schema / migration design

| Artifact | Role |
|---|---|
| `leave_authority_wave1.LEAVE_AUTHORITY_SCHEMA_VERSION = 1.0.0` | Version pin |
| `ops/sql/leave_authority_wave1_v1.sql` | Versioned SQL pack |
| `ops/migrate-leave-authority-wave1.sh` | Staging/local applicator; **refuses** `production` env and DB `wathefni` |
| Runtime `ensure_leave_authority_wave1_schema(cur)` | Idempotent bootstrap still available |

Adds:

- `leave_requests.row_version`
- `leave_authority_settings`
- `leave_type_catalogue` seed

---

## Exact fixes

1. **Self-decision hard ban** on approve/reject (and cancel-of-others is HR path; self-cancel allowed).
2. **Lifecycle gates** wired into `request_leave` / `approve_leave_request`.
3. **Stale pending:** past `start_date` + `requested` → `expired_stale`|`needs_review` with `stale_pending_resolved` audit; approve of past-start returns `leave_stale_pending_resolved`.
4. **Optimistic concurrency** on approve/reject/cancel.
5. **Canonical types** + alias map; ledger observe uses canonicalize so legacy `vacation`/`time_off` do not silently skip.
6. **Lifecycle reverse** in `employee_lifecycle_wave3c` stores `lifecycle_prev_status` and restores into primary machine (not `pending`).
7. **Honesty flags** on request/approve/reject/cancel, employee app leave, capabilities, home leave section, dashboard leave payloads: `balances_enforced=false`, `legal_reviewed=false`, `balances_binding=false`, `observe_only=true`.
8. **Pending queue** includes `needs_review` with `requested`.
9. Manager still **lacks** `leave.request` (unchanged).
10. Attendance reverse + provisional timesheet invalidate preserved; **no payroll money mutation**.

---

## Tests and evidence

| Proof | Path / result |
|---|---|
| Migrate | `migrate/leave-w1-migrate.out` → `MIGRATE_OK` |
| Smoke | `tests/leave-w1-smoke.out` → **51 passed, 0 failed** |
| E360 freeze | `tests/freeze-employees360.out` → 57/57 |
| Onboarding freeze | `tests/freeze-onboarding.out` → 54/54 |
| Attendance freeze | `tests/freeze-attendance.out` → 26/26 |
| Qualify script | `wathefni-orchestrator/ops/qualify-leave-authority-wave1-staging.sh` |

Smoke covers: self-deny, lifecycle blocks, stale expire + audit, concurrency fail-closed, canonical mapping, reverse≠pending, holiday chargeable path, honesty flags, manager no `leave.request`, payroll invalidate non-money.

---

## Remaining blockers (before enforced leave product)

- Legal review of Kuwait balance figures (`legal_reviewed` still false)
- Holiday calendar empty in production (code path proven; data not seeded)
- No partial-day/hourly, attachments, carryover, unpaid workflow
- No balance reservation / enforcement
- UI still may *display* balances unless clients honor honesty flags (APIs now explicit)
- Production leave rows still need a controlled synthetic canary pass after code promote
- Attendance↔leave durable linkage on real prod history remains thin (Wave 0 truth)

---

## GO / NO-GO — WATHEFNI-only production synthetic canary

**GO** for a **WATHEFNI-only production synthetic canary** of Leave Wave 1 authority code, with constraints:

- Synthetic employees/requests only; cleanup required  
- Do **not** set `balances_enforced` / policy `enforced=true`  
- Do **not** enable new UI redesign or unpaid/partial-day  
- Do **not** change Attendance capture ingest or frozen Onboarding/E360 flags  
- Prefer promote after backup + same smoke against production code path in synthetic company/keys  

**NO-GO** for real-employee leave authority rollout, legal balance enforcement, or any payroll money path.
