# Employees 360 Wave 4B — Production-safe org authority & migration qualification

**Stamp:** `20260801T213935Z`  
**Evidence:** `ops/evidence/employees360-wave4b-org-qualification-local-20260801T213935Z/`  
**Schema:** `employees360-wave4b-org-authority-v1`  
**Mode:** Local implementation + staging qualification + live staging HTTP  
**Production deploy:** **NOT DONE**  
**Real-employee lifecycle:** **NOT ENABLED** (`SYNTHETIC_ONLY=on` retained)  
**Wave 5 / redesign / pre-hiring / Wave D:** **UNTOUCHED**

---

## Verdict

| Gate | Result |
|---|---|
| Local/staging technical qualification | **PASS** |
| Unit | **42/42 PASS** |
| Wave 4B staging smoke | **42/42 PASS** |
| Wave 4 regression smoke | **58/58 PASS** |
| Staging restarted onto Wave 4B build + flags | **PASS** (`8011=200`) |
| Live HTTP employee-org routes | **PASS** (auth 200; unauth 401) |
| Prod untouched | **PASS** (no `employee_org_wave4.py`; no `ORG_V4`; `8010=200`) |
| WATHEFNI-only **production** synthetic canary | **NO-GO** |

### Dual GO / NO-GO

- **GO** for continued staging use of Wave 4B (org / migration / bulk).
- **NO-GO** for a WATHEFNI-only production synthetic canary until explicit deploy authorization, production backup + rollback drill, and a canary allowlist for migration-created phones/keys.

---

## Exact fixes (Wave 4 → 4B)

1. **Ghost-free migration rollback**
   - Commit accepts only brand-new hub creates (`status=created`); races on pre-existing hubs → `needs_review`.
   - Stamps `employees.raw_json` with `wave4_migration_batch_id` + `wave4_hub_created`.
   - Rows record `hub_created=true`.
   - Rollback deletes hub + Wave 2 authority map/assignment/employment/person (if unused) + all Wave 4 history for owned keys.
   - Ends with `assert_no_migration_ghosts` (fail closed if any hub/authority/history remains).

2. **Authoritative as-of reads**
   - `get_assignment_as_of(company, employee_key, as_of)` selects covering slice by `effective_from <= as_of <= effective_to` (open end allowed).
   - Does **not** treat a future open slice as “current”.
   - `get_current_org_projection` exposes assignment + scheduled_next + Wave 2 pointers.
   - Export/reconcile use as-of lateral join (not `effective_to IS NULL` alone).

3. **Future slices become current**
   - `activate_due_assignment_slices(as_of)` syncs Wave 2 assignment fields when a slice’s `effective_from` arrives.
   - Proved: as-of today keeps prior manager; as-of future day shows new manager; activate syncs Wave 2.

4. **Interrupt / resume without duplicates**
   - Commit only processes `status=valid`; committed rows never re-selected.
   - History for same `(employee_key, batch_id)` reused on resume.
   - Bulk: failed job status when any item fails; `retry_failed` requeues failures only; already-applied slices not duplicated.

5. **Audit**
   - `employee_org_migration_journal` entries for assignment changes, migration commit/rollback, bulk run/reverse, activate-due.

6. **Staging live**
   - EnvironmentFile `/opt/wathefni/staging/var/employees360-wave4.env`
   - Staging service restarted; flags live in process; 14 posthire org routes registered.

---

## Final rollback contract

```
Migration batch rollback (Wave 4B):
  FOR EACH committed row with hub_created=true:
    1. Require employees.raw_json.wave4_migration_batch_id == batch_id
    2. DELETE Wave 4 history / change_requests / bulk items for employee_key
    3. DELETE Wave 2 authority map + assignment + employment
    4. DELETE person (+aliases) only if no remaining employments
    5. DELETE hub employees row
  Shared org units created during import are RETAINED (catalog).
  Ghost check MUST return empty for owned keys or rollback aborts (409).
  Idempotent via journal key. Never auto-merges ambiguous people.
```

Transfer / manager / bulk reverse remain history-preserving (close/reopen or delete job slice only) — they do not delete hub employees.

---

## As-of read model

| Reader | Behavior |
|---|---|
| `get_assignment_as_of(as_of)` | Covering slice for that calendar date |
| `get_current_org_projection(as_of)` | As-of assignment + next scheduled slice + Wave 2 |
| Export / reconcile | Lateral as-of history join |
| Wave 2 field sync on write | Only when `effective_from <= today` |
| Activate-due | When calendar hits `effective_from`, sync Wave 2 from as-of slice |

**Rule:** never use `effective_to IS NULL` alone as “current assignment”.

---

## Staging HTTP evidence

| Check | Result |
|---|---|
| `GET /dashboard/posthire/employee-org/policy` | 200 |
| `GET .../units` | 200 |
| `GET .../export` | 200 |
| `GET .../reconcile` | 200 |
| Unauthenticated policy | 401 |
| Routes registered | 14 (incl. `org-as-of`, `org-history`, `activate-due`) |
| Staging flags | `ORG_V4=on`, `AUTHORITY_V2=on`, `LIFECYCLE_V3_SYNTHETIC_ONLY=on` |
| Prod | No Wave 4 module / no `ORG_V4` |

Artifacts: `http/e360-w4b-http.json`, `verify/e360-w4b-routes-full.txt`, `verify/e360-w4b-stg-flags.txt`, `verify/e360-w4b-envfile.txt`

---

## Migration reconciliation report

`reconcile_org_authority` + `export_org_reconciliation(as_of=today)`:

- Joins hub `employee_key` × Wave 2 map × Wave 4 **as-of** history  
- Flags: missing Wave 2 map, missing Wave 4 coverage (info), manager drift when as-of is current, multiple open slices  
- Smoke proved export row for transferred employee has `person_id` + `as_of_history_id`

---

## Tests re-run

| Suite | Result | Log |
|---|---|---|
| Unit | 42/42 | `verify/unit.log` |
| Wave 4B smoke | 42/42 | `verify/e360-w4b-smoke.log` |
| Wave 4 regression | 58/58 | `verify/e360-w4-regression-smoke.log` |
| Live HTTP | PASS | `verify/e360-w4b-http.json` |

Proved: future transfer/manager as-of; activate-due; import commit→interrupt→resume→ghost-free rollback; bulk partial failure→safe retry→reverse; export/reconcile; cross-tenant + out-of-scope denial.

---

## Remaining blockers (prod canary)

1. **No explicit production deploy authorization** for Wave 4/4B.  
2. **No production backup + restore drill** for org schema / migration rollback on live WATHEFNI.  
3. **Canary allowlist** for migration-created phones not yet defined for prod (staging uses synthetic `96554*` / `96553*`).  
4. Legacy hub org tables (`company_branches`, etc.) remain parallel — not a hard cutover.  
5. Enterprise dual-approval UI still absent (API-only; intentional — no redesign).  
6. Activate-due is on-demand API; no production timer (acceptable for canary if ops/cron planned).

---

## Explicit non-goals (honored)

- No production deploy  
- No Wave 5  
- No Employees 360 redesign  
- No real-employee lifecycle enablement  
- No pre-hiring / Wave D changes  
