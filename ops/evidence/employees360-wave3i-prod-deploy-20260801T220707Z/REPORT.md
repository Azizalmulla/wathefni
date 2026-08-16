# Employees 360 Wave 3I — Production deploy (Wave 3F/3H) + jurisdiction remediation

**Stamp:** `20260801T220707Z`  
**Evidence:** `ops/evidence/employees360-wave3i-prod-deploy-20260801T220707Z/`  
**Remote:** `/opt/wathefni/production-evidence/employees360-wave3i-prod-deploy/20260801T220707Z/`  
**Backup:** `/opt/wathefni/backups/production-pre-employees360-wave3i-20260801T220707Z/`  
**Schema:** `employees360-wave3h-jurisdiction-packs-v1`  
**Pack:** `KW_PRIVATE_SECTOR@1.0.0` only (hash `fc0f28b1…`)

**Disclaimer:** Not legal advice. Real-employee lifecycle remains blocked by synthetic-only + incomplete remediation classification.

---

## Separate GO / NO-GO verdicts

| Track | Verdict | Exact blocker (if NO-GO) | Blocker type |
|---|---|---|---|
| **Synthetic production lifecycle** | **GO** | — | — |
| **Jurisdiction remediation workflow** | **GO** (queue + dual-control classify; no auto-bind) | Existing records still need explicit HR dual-control classification before lifecycle | Missing employee data (intentional fail-closed until classified) |
| **Controlled real-employee lifecycle readiness** | **NO-GO** | `SYNTHETIC_ONLY=on` (required) + all 4 real employments in remediation with null jurisdiction/category/classification | Intentional safety gate + missing employee data |
| **Unsupported jurisdictions** | **GO (fail-closed)** | Reserved/unsupported packs correctly reject (`pack_not_implemented` / `unsupported_jurisdiction`) | — (correct product behaviour) |

---

## Deploy boundary honored

| Constraint | Status |
|---|---|
| WATHEFNI only | **Yes** |
| `WATHEFNI_EMPLOYEE_LIFECYCLE_V3_SYNTHETIC_ONLY=on` | **Preserved** |
| Hourly lifecycle timer | **enabled + active** |
| Only `KW_PRIVATE_SECTOR@1.0.0` enabled | **Yes** |
| Reserved packs fail closed | **Yes** |
| No real termination / real lifecycle | **Yes** |
| No Wave 4 / Wave 5 / pre-hire / Wave D | **Untouched** |

---

## Production SHAs (after)

| File | SHA256 |
|---|---|
| `employee_lifecycle_wave3c.py` | `dad7fbc7aabb8d2eb859ce697a6459b4ce54ca5414077992ced77a8f3637d696` |
| `employee_policy_packs_wave3h.py` | `31e0a7c5f8ea0ce61814363956e3bcbc321513a80112a1da946e5a5cb7fc3b19` |
| `canary-prod-wave3i-jurisdiction.py` | `29629724d10c0dc9ed9efa9139090069490fe727182f15f30a9e52db9c6fdbe0` |

Before: Wave 3D schema `employees360-wave3d-public-law-policy-v1`; packs module absent.  
See `remote/preflight/before.txt` and `remote/preflight/after-deploy.txt`.

---

## Backup + rollback proof

- Backup dir: `/opt/wathefni/backups/production-pre-employees360-wave3i-20260801T220707Z/`
- Contains: prior `employee_lifecycle_wave3c.py`, wave3, worker, app.py, drop-in, timer units, `lifecycle-tables.dump.sql`, executable `ROLLBACK.sh`
- Evidence: `remote/verify/backup-listing.txt`, `remote/verify/rollback-proof.txt`
- Rollback restores Wave 3D modules, removes packs module, restores drop-in, keeps timer enabled

---

## Synthetic qualification

**56/56 PASS** — `remote/canary-run.log` / `remote/canary/canary-evidence.json`

Proved:

- KW_PRIVATE_SECTOR@1.0.0 resolution  
- Unsupported jurisdiction fail-closed  
- Missing worker category fail-closed  
- Incomplete records fail-closed  
- Dual-control classification (no lifecycle execution)  
- Pack freeze on approve (hash matches catalog; historical freeze immutable)  
- Tenant override cannot weaken mandatory rules  
- Normal / fixed-term / probation / exceptional synthetic paths  
- Live scheduler + retry idempotency  
- Service certificate pending + inputs-only settlement  
- True rehire  
- Tenant isolation + manager scope deny  
- All 4 real employees untouched + still active  
- Synthetic cleanup → zero  

---

## Remediation report (existing employments)

Migration key `wave3i-prod-remediation-queue-20260801`:

```json
{"resolved": 0, "already_resolved": 1, "remediation": 12, "total": 13}
```

Read-only queue: **12** rows needing classification (`remote/remediation/10-record-report.json`).

**All 4 real employees** are in remediation with missing:

`jurisdiction_code`, `worker_category`, `contract_type`, `pay_frequency`, `probation_status`

| Employee | Status | Pack status |
|---|---|---|
| WATHEFNI-96550252254 (Talal Fadhli) | active | remediation |
| WATHEFNI-96566363363 (Fouad Burhamad) | active | remediation |
| WATHEFNI-96597727743 (mohammad alqattan) | active | remediation |
| WATHEFNI-96599411617 (Brian Saleh) | active | remediation |

No auto-classify. Classification only via dual-controlled `create_classification_request` / `decide_classification_request` (no lifecycle mutation).

---

## Pack freeze evidence

- Freeze count (WATHEFNI): **4** during canary  
- All freezes: `KW_PRIVATE_SECTOR` / `1.0.0` / hash `fc0f28b1…`  
- Registry: only KW enabled; 9 reserved packs `enabled=false`  
- File: `remote/verify/pack-registry-and-freezes.json`, `remote/canary/pack-freeze.json`

---

## Scheduler evidence

- Timer: **active** after deploy (`remote/verify/timer-still-active.txt`)  
- Canary scheduler run + idempotent retry: `remote/canary/scheduler.json`, `scheduler-retry.json`

---

## Flags (production)

```
WATHEFNI_EMPLOYEE_LIFECYCLE_V3=on
WATHEFNI_EMPLOYEE_LIFECYCLE_V3_COMPANIES=WATHEFNI
WATHEFNI_EMPLOYEE_LIFECYCLE_V3_SYNTHETIC_ONLY=on
WATHEFNI_EMPLOYEE_POLICY_PACKS_V3H=on
WATHEFNI_EMPLOYEE_POLICY_PACKS_V3H_COMPANIES=WATHEFNI
WATHEFNI_LIFECYCLE_COUNSEL_GATE=off
```

---

## Remaining gates before real lifecycle

1. Keep synthetic-only until explicitly authorized to disable  
2. Dual-control classify each real employment (KW + private_sector + contract/pay/probation)  
3. Re-run fail-closed proofs that classified reals can create lifecycle requests  
4. Explicit ops authorization for first controlled real case  

---

## Verdict: **PASS** (deploy + synthetic qualification)

Real-employee lifecycle remains **NO-GO** by design until remediation completes and synthetic-only is intentionally lifted.
