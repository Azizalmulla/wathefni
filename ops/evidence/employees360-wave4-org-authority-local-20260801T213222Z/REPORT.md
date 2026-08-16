# Employees 360 Wave 4 — Organization authority, effective history, migration & bulk ops

**Stamp:** `20260801T213222Z`  
**Evidence:** `ops/evidence/employees360-wave4-org-authority-local-20260801T213222Z/`  
**Schema:** `employees360-wave4-org-authority-v1`  
**Mode:** Local implementation + staging synthetic qualification  
**Production deploy:** **NOT DONE**  
**Real-employee lifecycle use:** **NOT ENABLED** (Wave 3 synthetic-only remains)  
**Wave 5 / visual redesign / pre-hiring / Wave D:** **UNTOUCHED**

---

## Verdict

**PASS** (local/staging)

| Gate | Result |
|---|---|
| Org structure create/update (legal employer, branch, department, team, location, position, cost center) | **PASS** |
| Effective-dated assignment history; prior slices closed, never overwritten | **PASS** |
| Transfer preserves prior history | **PASS** |
| Future-dated manager change (scheduled → executed; effective_from future) | **PASS** |
| Overlapping / same-open-day assignments fail closed | **PASS** |
| Migration dry-run / pause / commit chunk / resume / rollback | **PASS** |
| Duplicate / conflict / ambiguous rows → review queue (no auto-merge) | **PASS** |
| No silent partial import success | **PASS** |
| Export joins hub + Wave 2 authority + open Wave 4 history | **PASS** |
| Bulk assign idempotent + reversible | **PASS** |
| Small / medium / enterprise policy tiers | **PASS** |
| Cross-tenant + out-of-scope manager mutations fail closed | **PASS** |
| Unit tests | **33/33 PASS** |
| Staging smoke | **58/58 PASS** |
| Production deploy / Wave 4 flag on prod | **NOT DONE** |
| Prod `employee_org_wave4.py` | **Absent** |
| Prod health `8010` / staging health `8011` | **200 / 200** |

---

## Architecture

```
Hub employees.employee_key  ──compatibility──►  Wave 2 person/employment/assignment
                                                      ▲
                                                      │ sync (non-destructive)
Wave 4 org units + assignment history slices ─────────┘
        │
        ├── change requests (transfer / manager / job / dept / location)
        ├── migration batches (map → dry-run → commit/pause/resume/rollback)
        └── bulk jobs (assign dept/team/location/manager; reverse)
```

**Flags (staging/local only):**
- `WATHEFNI_EMPLOYEE_ORG_V4=on`
- `WATHEFNI_EMPLOYEE_ORG_V4_COMPANIES=WATHEFNI` (default)
- Requires Wave 2: `WATHEFNI_EMPLOYEE_AUTHORITY_V2=on` for the same tenant

**Module:** `wathefni-orchestrator/employee_org_wave4.py`  
**Routes:** `/dashboard/posthire/employee-org/*` (flag-gated; no UI redesign)

---

## Schema (additive)

DDL: `schema/wave4-org-schema.sql`

| Table | Role |
|---|---|
| `employee_org_schema_meta` | Schema version marker |
| `employee_org_company_policies` | small / medium / enterprise knobs |
| `employee_org_units` | Legal employer, branch, department, team, location, position, cost center |
| `employee_org_assignment_history` | Effective-dated slices (append + close; never in-place overwrite) |
| `employee_org_change_requests` | Job/dept/location/manager/transfer workflows + idempotency |
| `employee_migration_batches` / `employee_migration_rows` | Staged CSV/XLSX import with mapping, validation, review queue |
| `employee_bulk_jobs` / `employee_bulk_job_items` | Async-style bulk assign + reverse |
| `employee_org_migration_journal` | Rollback / ops evidence |

Every mutation records **effective dates**, **actor**, **reason**, **version**, and provenance / request / bulk / batch linkage where applicable.

---

## Organization & assignment model

- **Org units** are typed, keyed, versioned, optionally parent-linked, and effective-dated.
- **Assignment history** is a time-sliced ledger per `(company_code, employee_key)`:
  - Open slice: `effective_to IS NULL`
  - On change: prior open slice closed to `effective_from - 1 day`; new slice appended
  - Historical closed rows are never mutated in place
- Overlaps fail closed (`409 overlapping_assignment`)
- Wave 2 assignment readable fields (department/location/manager/title) are synced when an authority map exists; `employee_key` remains the hub alias

**Policy tiers**

| Tier | Org depth | Dual approval |
|---|---|---|
| small | department, location, position | off |
| medium | + legal_employer, branch, team | off |
| enterprise | all unit types | on (no self-approval) |

---

## Migration workflow

1. `create_migration_batch` — store raw rows + column mapping (auto-suggest aliases)
2. `dry_run_migration_batch` — validate; classify `valid` / `invalid` / `duplicate` / `conflict` / `needs_review`
3. `pause` / `commit` (optional `max_rows`) / `resume`
4. Only **`valid`** rows create employees + history; review rows never auto-create or auto-merge
5. `rollback_migration_batch` — removes committed Wave 4 history slices (hub rows not auto-deleted; journaled)
6. `export_org_reconciliation` — hub × Wave 2 map × open Wave 4 history

**Hard rules:** no silent partial success flag; ambiguous phone/name → `needs_review`.

---

## Bulk-operation design

- `create_bulk_assign_job` → pending items → `run_bulk_assign_job`
- Each item applies an effective-dated `bulk_assign` slice (scope-checked)
- Re-run of succeeded job is **idempotent**
- `reverse_bulk_assign_job` deletes job-created slices and reopens prior `effective_to` where recorded

Large imports/bulk actions are modeled as **batch/job rows** (async-ready); smoke executes them in-process against staging DB.

---

## Tests and evidence

| Artifact | Path |
|---|---|
| Unit (33) | `verify/unit.log`, `tests/smoke-test-employee-wave4-org-unit.py` |
| Staging smoke (58) | `verify/e360-w4-smoke.log`, `tests/smoke-test-employee-wave4-org.py` |
| Module | `tests/employee_org_wave4.py` |
| Schema | `schema/wave4-org-schema.sql` |
| API routes | `verify/api-routes.txt` |
| Staging SHAs | `verify/e360-w4-shas.txt` |
| Prod untouched | `verify/e360-w4-prod-app-sha.txt`, `verify/e360-w4-prod-flags.txt` |

**Proven on staging DB (`wathefni_staging`):** org CRUD; transfer history; future manager; overlap fail-closed; migration dry-run/pause/commit/resume/rollback; review queue; export↔Wave 2; bulk idempotent/reverse; policy tiers; cross-tenant + manager scope deny.

---

## Remaining risks

1. **Hub employees from migration are not auto-deleted on rollback** — only Wave 4 history slices roll back; operators must scrub hub rows deliberately.
2. **Future-dated open slices** become the sole open end before the calendar date; “as-of today” readers must filter by `effective_from <= as_of`.
3. **Staging service was not restarted** with Wave 4 routes/flags — code is present under `/opt/wathefni/staging/orchestrator` for qualification; live HTTP on `8011` may still be pre-Wave-4 until an explicit staging restart.
4. **No production canary** — Wave 4 must not be enabled in prod without a separate authorize/deploy gate.
5. **Legacy hub org tables** (`company_branches`, `employee_org_assignments`, etc.) remain parallel; Wave 4 is additive authority, not a hard cutover.
6. **Enterprise dual-approval** gates request creation; full separate-approver execute UX is API-ready, UI not built (by design — no redesign).

---

## Explicit non-goals (honored)

- No production deploy  
- No real-employee lifecycle enablement  
- No Wave 5 start  
- No Employees 360 visual redesign  
- No pre-hiring or Wave D behavior changes  
