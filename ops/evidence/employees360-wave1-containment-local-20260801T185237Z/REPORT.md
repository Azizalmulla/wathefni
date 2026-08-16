# Employees 360 Wave 1 — Immediate Risk Containment (LOCAL ONLY)

**Stamp:** `20260801T185237Z`  
**Evidence:** `ops/evidence/employees360-wave1-containment-local-20260801T185237Z/`  
**Mode:** local engineering only — **no deploy**, **no production data mutation**, **no uniqueness constraints**, **no person/employment migration**, **no UX redesign**  
**Baselines preserved:** frozen pre-hiring + Wave D; existing `employee_key` scheme; status-transition idempotency/approval mechanics (canary now allowlisted)

---

## Verdict

**PASS (local containment engineering)**

| Gate | Result |
|---|---|
| Phone canonicalization + alias-aware lookup | PASS (unit harness) |
| Duplicate prevention without DB UNIQUE | PASS (unit harness) |
| Canary restricted to WATHEFNI + allowlisted envs | PASS (pure + unit) |
| Manager-scope denial on PATCH/status | PASS (unit harness) |
| Optimistic concurrency on employee edits | PASS (unit harness) |
| Orphan-document scope bypass closed | PASS (source + restricted path) |
| Integrity diagnostics expanded | PASS (unit + source) |
| Audit evidence for denials/collisions | PASS (source + unit) |
| Production deploy | **NOT DONE** (explicitly out of scope) |
| Live Postgres integration smoke | SKIP locally (no `WATHEFNI_POSTGRES_ENV`) |

---

## Root causes (from Wave 0 + code)

1. **Phone identity split:** roster/import used `canonical_employee_phone` (8→`965…`) while hire used `digits()` only, and lookup matched exact `phone=` — local and 965 forms could mint two hubs for one person.
2. **No application-side alias dedupe:** PK is `employee_key` only; no `UNIQUE(company_code, phone)` and no alias collision check → duplicates possible once formats diverge.
3. **`self_approved_internal_canary` unrestricted:** any dual-grant operator in any tenant/env could self-approve status changes; UI always sent canary.
4. **Manager scope on reads only:** PATCH/status (and orphan document file access when employee row missing) could bypass delegated scope.
5. **No optimistic concurrency on normal edits:** concurrent HR edits silently last-write-wins.
6. **Integrity scan incomplete:** orphans in messages/sessions/invites/status/org/file_registry/onboarding were invisible.

---

## Exact local changes

### Orchestrator — `wathefni-orchestrator/app.py`
- Added `employee_phone_alias_list` / `find_employee_by_phone_aliases`; `find_employee_by_phone` + `employee_company_code_for_phone` are alias-aware.
- `create_company_employee`: pre-insert alias collision → `exists` (+ `identity_collision` when keys/phones differ).
- `update_company_employee`: alias-aware phone collision; optional `expected_updated_at` optimistic lock → `conflict`.
- `DashboardEmployeeUpdate.expected_updated_at` **required** on HTTP PATCH; 409 `employee_version_conflict`.
- `employee_status_canary_allowed`: fail-closed company+env allowlists  
  - defaults: companies=`WATHEFNI`; envs=`local,dev,development,staging,stage,test,pytest,harness` (**not** production)  
  - override: `WATHEFNI_EMPLOYEE_STATUS_CANARY_COMPANIES`, `WATHEFNI_EMPLOYEE_STATUS_CANARY_ENVS`
- `require_employee_mutation_scope` on PATCH + status; audits `employee_mutation_denied`.
- Document file GET: restricted managers cannot use orphan/missing employee to bypass scope; unrestricted orphan access audits `orphan_document_accessed`.
- Create/edit collisions audit `employee_identity_collision`.
- `INTEGRITY_SCAN_SPECS` expands to messages, sessions, invites, status_changes, org_assignments, hr_tasks, document_storage_operations, file_registry, onboarding_items, employee_documents.

### Hire — `wathefni-orchestrator/hire_operations.py`
- Uses `canonical_employee_phone` + `phone_identity_candidates` for match/insert; stores canonical phone; links existing alias rows instead of creating a second key.

### Dashboard
- `updateEmployee` requires `expected_updated_at`.
- `EditEmployeeModal` sends `employee.updated_at`.

### Tests
- `wathefni-orchestrator/smoke-test-employee-wave1-containment.py` (DB when available; pure-only otherwise)
- `smoke-test-employee-lifecycle.py` updated for PATCH concurrency + `WATHEFNI_ENV=test` default for canary
- Evidence harness: `verify/wave1_unit_harness.py` (**23/23 PASS**)

---

## Compatibility impact

| Surface | Impact |
|---|---|
| Employee keys / existing rows | Unchanged; no rewrite/migration |
| `PATCH /dashboard/posthire/employees/{key}` | **Breaking additive:** clients must send `expected_updated_at` |
| Status transition idempotency / request hash | Unchanged |
| `self_approved_internal_canary` | **Fail-closed** outside allowlist; production denied by default |
| Import / roster create / hire lookup | Compatible; stronger alias matching |
| DB schema | No UNIQUE constraints added |
| Pre-hiring / Wave D | Untouched |

---

## Tests executed (local)

```
verify/wave1_unit_harness.py     → 23 passed, 0 failed
smoke-test-employee-wave1-containment.py → 5 pure PASS; DB SKIP (no postgres env)
```

Covered: phone aliases, duplicate prevention, manager-scope denial + audit, canary restriction matrix, optimistic concurrency, integrity expansion markers, hire source markers.

---

## Production deployment risks & required remediation plan

**Do not deploy this pack yet.** Wave 0 production deploy/repair remains NO-GO until the plan below is explicitly approved.

### Risks if deployed without remediation
1. **Status UI breakage in production:** dashboard still sends `self_approved_internal_canary`. With default allowlist, **production WATHEFNI status changes via canary will 403** until either:
   - `WATHEFNI_EMPLOYEE_STATUS_CANARY_ENVS` explicitly includes `production` **and** companies remain WATHEFNI-only, **or**
   - UI switches to `separate_approval` with a real second approver.
2. **PATCH clients without `expected_updated_at`:** any non-updated client gets validation/409 failures.
3. **Alias matching may surface latent collisions:** create/import/hire that previously would have minted a second hub now returns `exists` / collision audit — correct, but ops must triage any blocked creates.
4. **Restricted managers:** out-of-scope PATCH/status/orphan-doc access becomes 404 (intended). Confirm org scopes before enabling hierarchy for external tenants.
5. **No DB UNIQUE yet:** application-side dedupe is best-effort; concurrent inserts of true identical keys still rely on PK only. Wave 2+ may add careful uniqueness after cleanup.

### Required remediation before production enablement
1. Ship dashboard + orchestrator together (concurrency field + canary gate).
2. Decide canary policy for prod WATHEFNI:
   - Preferred: change UI to `separate_approval` for production; keep canary for internal non-prod only.
   - Alternate: set systemd drop-in  
     `WATHEFNI_EMPLOYEE_STATUS_CANARY_COMPANIES=WATHEFNI`  
     `WATHEFNI_EMPLOYEE_STATUS_CANARY_ENVS=production`  
     (still deny all other companies).
3. Staging soak: run `smoke-test-employee-wave1-containment.py` + lifecycle against staging DB.
4. Read-only integrity scan on prod after deploy (no orphan deletes yet — Wave 0 synthetic orphans stay).
5. Do **not** clean null statuses / delete P0-DUP orphans / add UNIQUE in this wave.
6. Explicit owner approval required for deploy.

---

## Explicit non-actions (confirmed)

- No production data mutation
- No null `employment_status` cleanup
- No deletion of three synthetic orphan messages
- No database uniqueness constraints
- No person/employment/assignment migration
- No Employees 360 redesign
- No deploy
