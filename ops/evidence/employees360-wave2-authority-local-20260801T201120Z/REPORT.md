# Employees 360 Wave 2 — Canonical employee authority (local/staging)

**Stamp:** `20260801T201120Z`  
**Evidence:** `ops/evidence/employees360-wave2-authority-local-20260801T201120Z/`  
**Mode:** Local implementation + staging synthetic qualification  
**Production deploy / prod backfill:** **NOT DONE**

---

## Verdict

**PASS** (local/staging)

| Gate | Result |
|---|---|
| Schema: person / employment / assignment + aliases + employee_number | PASS |
| Deterministic IDs match approved Wave 1C map | PASS (unit 19/19) |
| Idempotent backfill | PASS |
| No duplicate person/employment/assignment rows | PASS |
| Compatible hub API card fields unchanged | PASS |
| Edits sync to correct authority rows | PASS |
| Rehire reuses person; new employment + assignment; history retained | PASS |
| Cross-tenant access fail-closed | PASS |
| Scoped rollback + restore-new | PASS |
| Wave 1 guards / freeze baselines / visual redesign | Untouched |
| Production | **Not deployed** |

---

## Schema and authority design

### Model

| Entity | Meaning | Immutable key |
|---|---|---|
| **Person** | Human identity + contacts + tenant `employee_number` | `person_id` (UUIDv5) |
| **Employment** | Legal employer relationship, service period, state | `employment_id` (UUIDv5) |
| **Assignment** | Role / dept / location / manager / team / cost center / pattern | `assignment_id` (UUIDv5) |

### Tables (additive)

- `employee_persons`
- `employee_person_contact_aliases` (phone/email, tenant-unique)
- `employee_employments` (`legacy_employee_key` compatibility)
- `employee_assignments`
- `employee_key_authority_map` (hub alias → authority triple)
- `employee_authority_migration_journal`
- Nullable hub pointers: `employees.person_id|employment_id|assignment_id`

DDL: `schema/wave2-authority-schema.sql`

### Uniqueness (tenant-safe, non-destructive)

- `(company_code, alias_type, alias_value)` unique on contact aliases
- `(company_code, employee_number)` unique where set
- `(company_code, legacy_employee_key)` unique on employments where set
- `(company_code, employment_id)` unique on authority map (1 legacy key ↔ 1 employment during migration)
- **No** new `UNIQUE(company_code, phone)` on hub `employees` (Wave 1 constraint still deferred)

### Rehire

`open_rehire_employment`:
1. Marks prior active employments `left` (history retained)
2. Reuses `person_id`
3. Mints **new** `employment_id` + `assignment_id` + hub `employee_key`
4. Maps new key → same person

---

## Migration plan

1. Enable flag `WATHEFNI_EMPLOYEE_AUTHORITY_V2=on` (staging/canary first)
2. `ensure_authority_schema`
3. `backfill_company_authority(company, employee_keys=…)` using approved map for WATHEFNI’s 4 real keys
4. Keep hub `employee_key` as live compatibility alias
5. Shadow-sync on create / edit / hire when flag on
6. No hard cutover of child tables in Wave 2
7. Rollback: scoped or tenant `rollback_company_authority` clears authority rows + hub pointers; hub business columns untouched

Idempotency: journal key `wave2-backfill:{COMPANY}` (or scoped smoke keys)

---

## Compatibility strategy

| Concern | Strategy |
|---|---|
| Employees / Onboarding / Compliance / Shifts / Attendance / Leave / Payroll | Continue to hang off `employee_key`; unchanged |
| API cards | Same fields via `posthire_employee_card` |
| Authority reads | `get_authority_projection(company, employee_key)` |
| Writes | Hub remains source of truth for APIs; shadow upsert when flag on |
| Wave 1 manager scope / permissions | Unchanged (still key-scoped) |
| Synthetic orphans | Still excluded from person mint |

---

## Tests

| Suite | Result |
|---|---|
| Unit (approved map + determinism + seed fail-closed) | **19/19 PASS** — `tests/wave2-unit.txt` |
| Staging synthetic smoke | **27/27 PASS** — `tests/wave2-staging-smoke.txt` |

Covered on staging: backfill, idempotent rerun, edit sync, rehire+history, cross-tenant deny, compatible cards, scoped rollback, restore-new.

Module: `wathefni-orchestrator/employee_authority_wave2.py`  
Hooks (local tree): create/update in `app.py`, hire TX in `hire_operations.py` (behind flag)

---

## Remaining risks

1. **Staging hub hooks not fully deployed** — smoke forced authority sync after edit; production enablement must ship `app.py` / `hire_operations.py` hooks with the module.
2. **Child tables still key-addressed** — true FK cutover to `employment_id` is later; Wave 2 is shadow authority only.
3. **Phone change vs person identity** — changing hub phone does not remint `person_id` in this wave (employment/assignment stay; alias upsert may add new phone). Needs explicit merge policy later.
4. **Approved map backfill on staging** skipped when the 4 prod keys are absent — production apply must run against live WATHEFNI rows.
5. **Tenant-wide rollback** is destructive to all authority rows for that company; prefer scoped `employee_keys` on shared tenants.
6. **Employee number** is sequential per tenant at insert time — concurrent backfills should run single-threaded per company.

---

## Explicit non-actions

- No production deploy / prod backfill
- No visual redesign
- No destructive hub rewrite / hard cutover
- No Wave D / pre-hiring changes
- No uniqueness on hub phone yet

---

## Approval ask

Owner approval required before production schema create + WATHEFNI deterministic backfill of the 4 approved map rows.
