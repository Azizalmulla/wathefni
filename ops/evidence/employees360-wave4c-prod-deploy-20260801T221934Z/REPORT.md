# Employees 360 Wave 4C — Production deploy + synthetic qualification

**Stamp:** `20260801T221934Z`  
**Evidence:** `ops/evidence/employees360-wave4c-prod-deploy-20260801T221934Z/`  
**Remote:** `/opt/wathefni/production-evidence/employees360-wave4c-prod-deploy/20260801T221934Z/`  
**Backup:** `/opt/wathefni/backups/production-pre-employees360-wave4c-20260801T221934Z/`  
**Schema:** `employees360-wave4b-org-authority-v1`  
**Allowlist:** phones `965547*`, names `W4C-SYNTH|`

**Boundary honored:** WATHEFNI only · Wave 3F/3H preserved · `SYNTHETIC_ONLY=on` · four reals untouched · no Wave 5 / UI redesign / pre-hire / Wave D changes.

---

## Separate GO / NO-GO verdicts

| Track | Verdict | Exact blocker (if NO-GO) |
|---|---|---|
| **Wave 4 synthetic production use** | **GO** | — |
| **Org and assignment production authority** | **GO** | — |
| **Migration and bulk operations** | **GO** | — |
| **Controlled real-employee readiness** | **NO-GO** | `SYNTHETIC_ONLY=on` (required) + 4 reals still `policy_pack_status=remediation` with null jurisdiction/category (unclassified by design) |

---

## Production SHAs (after)

| File | SHA256 |
|---|---|
| `app.py` | `fb3522fc939ec87666853a99dac9e5bc7db757bf95dcfc6dea908ab7a248662b` |
| `employee_org_wave4.py` | `2828df20cbedca6905ec15adf602994abfa96f678648947ffdf1d3577f2bb5f5` |
| `lifecycle-effective-worker.py` | `aed53ec6c8244a1a1f0d31b18fc5a3e466dda30ea79247e798bd8ff3245a6f0f` |
| `canary-prod-wave4c-org.py` | `ebb4063562cd5074d3acfa587d1a3c16cf02adc5f2cd491b72adefe16ebb096c` |
| `employee_lifecycle_wave3c.py` (unchanged) | `dad7fbc7aabb8d2eb859ce697a6459b4ce54ca5414077992ced77a8f3637d696` |
| `employee_policy_packs_wave3h.py` (unchanged) | `31e0a7c5f8ea0ce61814363956e3bcbc321513a80112a1da946e5a5cb7fc3b19` |

**Before:** no `employee_org_wave4.py`; 0 employee-org routes; only legacy `employee_org_assignments` table.  
Artifacts: `remote/preflight/before.txt`, `remote/preflight/after-deploy.txt`.

---

## Flags (live)

```
WATHEFNI_EMPLOYEE_ORG_V4=on
WATHEFNI_EMPLOYEE_ORG_V4_COMPANIES=WATHEFNI
WATHEFNI_EMPLOYEE_ORG_V4_ACTIVATE_DUE=on
WATHEFNI_EMPLOYEE_ORG_V4_ACTIVATE_LOOKBACK_DAYS=7
WATHEFNI_EMPLOYEE_LIFECYCLE_V3_SYNTHETIC_ONLY=on   # preserved
WATHEFNI_EMPLOYEE_POLICY_PACKS_V3H=on              # preserved
WATHEFNI_EMPLOYEE_AUTHORITY_V2=on                 # preserved
```

Drop-ins:  
- `/etc/systemd/system/wathefni-orchestrator.service.d/employee-org-v4.conf`  
- `/etc/systemd/system/wathefni-lifecycle-effective.service.d/wave4c-org.conf`

---

## Backup + rollback proof

- Backup dir contains pre-deploy `app.py`, `lifecycle-effective-worker.py`, Wave 3F/3H modules, lifecycle drop-in, timer units, schema/data dumps, executable `ROLLBACK.sh`
- `bash -n` + executable bit verified (`rollback_syntax_ok` / `rollback_exec_ok`)
- Rollback restores prior `app.py` + worker, removes `employee_org_wave4.py` + org drop-ins, keeps lifecycle timer + SYNTHETIC_ONLY
- Migration API rollback (canary): removes migration-owned hub + Wave 2 authority + Wave 4 history; **shared org units retained**; ghost check empty
- Additive schema only (new Wave 4 tables created; no destructive alters to shared employments)

---

## Schema evidence

`employee_org_schema_meta.schema_version = employees360-wave4b-org-authority-v1`

Tables present: `employee_org_units`, `employee_org_assignment_history`, `employee_org_change_requests`, `employee_org_company_policies`, `employee_org_migration_journal`, `employee_migration_batches`, `employee_migration_rows`, `employee_bulk_jobs`, `employee_bulk_job_items` (+ pre-existing `employee_org_assignments`).

14 employee-org / org-as-of / org-history routes registered. Unauth policy → **401**.

---

## Scheduler decision

**Choice: share existing `wathefni-lifecycle-effective.timer` / oneshot worker** (no separate org timer).

Rationale: same hourly unattended cadence already proven in Wave 3E/3I; activate-due is idempotent and cheap; one kill switch surface.

| Proof | Evidence |
|---|---|
| Unattended future activation | Worker JSON `org_activate_due.enabled=true` with lookback days; canary synced Wave 2 on due day |
| Persistence across restart | Orchestrator + worker restart during deploy; timer remains enabled/active; subsequent oneshot succeeded |
| Retry + idempotency | Double `activate_due` → single journal key (`journal_count=1`) |
| Lag detection | Worker emits `ORG_ACTIVATE_LAG_ALERT` when Wave 2 manager ≠ covering as-of slice; canary run `lag_count=0` |
| Kill switch | `WATHEFNI_EMPLOYEE_ORG_V4_ACTIVATE_DUE=off` → log `ORG_ACTIVATE_DUE skipped`; restore → `enabled=true` |

Future assignment activation is **not** dependent on manual execution.

---

## Synthetic qualification — **67/67 PASS**

Allowlist-only phones/keys (`965547*`, `W4C-SYNTH|`).

### Synthetic IDs (canary tag `cf05e93c`)

| Role | ID |
|---|---|
| Units | LE/BR/Dept/Team/Loc/Pos/CC — see `canary-evidence.json` `ids.units` |
| Employees A/B/C/Sched | `WATHEFNI-96554791100` … `91102`, `91109` |
| Migration batch | `b02c13e4-1d4c-458c-bf49-90b753c90a73` |
| Migration hubs (rolled back) | `…91103`–`91105` |
| Shared ImpDept (survived rollback) | `aafc43e3-…` (name `ImpDept-cf05e93c`) |

Proved:

- Create legal employer, branch, department, team, location, position, cost center  
- Import batch dry-run → commit interrupt → resume without duplication  
- Duplicate rows enter review; never auto-merge  
- Current transfer closes previous assignment slice  
- Future department + manager resolve correctly via as-of reads  
- `activate_due` updates Wave 2 authority at effective time  
- Overlapping assignments fail closed  
- Bulk assign succeeds idempotently; partial failure → `failed` + safe retry (no duplicate slices)  
- Export / reconcile join canonical Wave 2 + Wave 4 as-of  
- Migration rollback removes owned hub/authority/history; shared units remain; no ghosts  
- Manager scope + cross-tenant mutations fail closed  
- All four real employees unchanged; org history count 0  
- Final synthetic cleanup → **0** leftover `965547*` / `W4C-SYNTH|` hubs  

Artifacts: `remote/canary/canary-run.log`, `remote/canary/canary-evidence.json`.

---

## Remediation-queue classification

| Category | Count | Action |
|---|---|---|
| Real active employments (unclassified) | **4** | Left in `remediation`; jurisdiction/category null; **not classified** |
| Confirmed synthetic/test leftovers | **8** | Quarantined → `quarantined_synthetic_test` with provenance stamp |
| Preserved genuine historical (non-synth) | **0** | — |
| Unknown skipped | **0** | — |

**Final remediation queue count: 4** (the four reals only).  
Artifacts: `remote/remediation/hygiene-report.json`, `remote/remediation/final-counts.txt`.

---

## Cleanup proof

- Canary cleanup: 0 Wave 4C synthetic employees remaining  
- Migration rollback ghost check empty for owned keys  
- Shared catalog units retained through migration rollback (then canary final cleanup removes tagged units only)  
- Reals still active + remediation + unclassified  

---

## Deploy boundary checklist

| Constraint | Status |
|---|---|
| WATHEFNI only | Yes |
| Preserve Wave 3F/3H | Yes (SHAs unchanged) |
| Synthetic-only lifecycle | Yes |
| Four reals untouched / not classified | Yes |
| Strict synthetic phone/key allowlist | Yes (`965547*`) |
| No Wave 5 / UI redesign | Yes |
| No pre-hire / Wave D changes | Yes |
| Additive migrations only | Yes |
| Unattended activate-due | Yes (shared timer) |
