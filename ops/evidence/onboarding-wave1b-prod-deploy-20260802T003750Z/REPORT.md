# Onboarding Wave 1B — Production deployment & read-path qualification

**Stamp:** `20260802T003750Z`  
**Evidence:** `ops/evidence/onboarding-wave1b-prod-deploy-20260802T003750Z/`  
**Prior wave:** Wave 1 local/staging repair `onboarding-wave1-loader-repair-20260802T002257Z`

---

## Verdict

| Gate | Result |
|---|---|
| Production deploy of Wave 1 read-path | **PASS** |
| Production read-path qualification | **PASS** (`ok: true`) |
| Four-real checklists unchanged | **PASS** (fingerprint match) |
| SEED / HR_MUTATE remain off | **PASS** |
| Staging HR_MUTATE cleanup | **PASS** (`off`) |
| Employees 360 freeze (local full suite) | **PASS** `54/54` |
| **Wave 2 staging preparation** | **GO** |
| Wave 2 enable SEED/HR_MUTATE / backfill | **NO-GO** (separate controlled wave) |

---

## Production SHAs and flags

### SHAs

| File | SHA256 |
|---|---|
| **Before** `/opt/wathefni/orchestrator/app.py` | `0e3e10f1fb0596c3add6aedcd92a319deb8d75254167bbe3ee792c9fe37648e5` |
| **After** (prod = staging = local candidate) | `a73ee60b369a4a5b8a764cf3736e67b8a7a57608eba6de695852d6bcbf77a99a` |

Pre-deploy corruption confirmed: `candidates.read` **in** loader; no `load_onboarding_items`.  
Post-deploy: `candidates.read` **absent** from loader; `load_onboarding_items` present.

### Flags (process)

| Env | `ONBOARDING_SEED` | `ONBOARDING_HR_MUTATE` | Notes |
|---|---|---|---|
| **Production** | **off** | **unset → False** | App allowlist still Talal-only (unchanged) |
| **Staging** | **off** | **off** | Corrected from unit `=true` via unit edit + `zz-onboarding-hr-mutate-off.conf` |

Artifacts: `flags/final-flags.txt`, `flags/staging-hr-mutate-cleanup.txt`, `preflight/before-deploy.txt`.

---

## Backup and rollback proof

| Item | Path / proof |
|---|---|
| Backup dir | `/opt/wathefni/backups/production-pre-onboarding-wave1b-20260802T003750Z/` |
| Pre-image `app.py` | SHA `0e3e10f1…` (`backup/app.py.sha256`) |
| Rollback script | `backup/ROLLBACK.sh` (restores `app.py`, restarts prod, health-checks) |
| Tested | `verify/rollback-tested.txt` — syntax OK, cmp OK; **full rollback not executed** (would undo GO) |

---

## What was deployed

Production `app.py` only (Wave 1 correctness):

- `load_onboarding_items` + repaired `employee_onboarding_items`
- Canonical reads for list counts, detail, app, E360 profile, WA summary
- Tenant-safe reminder/queue scans
- Manager-scope gates retained on list/detail
- Waived/completion count alignment + recompute
- Plaintext bank freeze → ESS handoff

**Not done:** checklist backfill, SEED/HR_MUTATE enable, employee-app broaden, UI redesign, E360/pre-hire/Wave D changes, real checklist mutations.

---

## Production reconciliation (four reals)

Fingerprint **unchanged** (19 rows). Helper ≡ summary ≡ SQL; wrong-tenant empty; recompute match.

| Employee | Items | Pending | Received | Gates |
|---|---|---|---|---|
| Talal `…252254` | 6 | 4 | 0 | all true |
| Fouad `…363363` | 6 | 4 | 0 | all true |
| Mohammad `…727743` | 6 | 2 | 2 | all true |
| Brian `…411617` | 1 | 1 | 0 | all true |

Source: `verify/prod-qualification.json`, `preflight/onboarding-counts-before.json`.

---

## Bank-freeze evidence

- `validate_onboarding_item_receipt("bank_details", IBAN text)` → `(False, bank_via_ess_required)`
- Helper `onboarding_plaintext_bank_forbidden("bank_details")` → `True`
- Mohammad historical `bank_details=received` value **not rewritten**; read path redacts bank values

Artifact: `verify/manager-scope-and-bank.txt`, qualification JSON.

---

## Cleanup evidence

Synthetic waived probe employee `W1B-*` inserted then **deleted** (`cleanup_probe_deleted: true`). No lasting prod rows beyond Wave 1 code.

Staging crash-loop from a prior corrupt staging `app.py` was repaired by re-syncing the same qualified SHA; staging health OK.

---

## Other qualification proofs

| Proof | Result |
|---|---|
| Wave 1 smoke (prod DB) | **38/38** |
| Reminder without company | empty (fail closed) |
| Reminder foreign tenants | 0 |
| Manager gate on detail / SQL scope on list | present |
| SEED / HR_MUTATE | False / False |
| E360 freeze (local full) | **54/54** |
| E360 modules on prod tree | 5/5 lite checks |

---

## Remaining blockers (for Wave 2 *enablement*, not staging prep)

1. Legacy short checklists vs `default_kuwait` (~32 missing items) — backfill not applied  
2. Brian single-item checklist  
3. ESS bank real allowlist still empty — bank setup frozen to ESS but not opened for reals  
4. No cancel / start-date / concurrency (later waves)  
5. Staging full freeze-doc suite path differs on server (local 54/54 remains authority for freeze docs)

---

## GO / NO-GO

**GO for Wave 2 staging preparation** — Wave 1 read-path is live on production and staging; SEED/HR_MUTATE off; staging mutate flag cleaned; four-real truth unchanged and reconciled.

**NO-GO for enabling SEED, HR_MUTATE, or checklist backfill** until a separate Wave 2 controlled plan with explicit approval and evidence.
