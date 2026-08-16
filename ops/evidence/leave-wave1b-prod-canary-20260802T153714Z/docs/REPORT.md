# Leave Wave 1B — Production synthetic authority canary

**Stamp:** `20260802T153714Z`  
**Evidence:** `ops/evidence/leave-wave1b-prod-canary-20260802T153714Z/`  
**Remote:** `/opt/wathefni/production-evidence/leave-wave1b-prod-canary/20260802T153714Z/`  
**Company:** WATHEFNI only · synthetic markers `LVW1B` / `LVW1B-SYNTH|` / phone prefix `965525`

---

## Separate verdicts

| Concern | Verdict |
|---|---|
| **Synthetic production leave authority** | **GO** — canary `58/58` (initial + post-redeploy); schema `1.0.0` live; synthetic-only flags on |
| **Controlled real HR leave decisions** | **NO-GO** — Wave 1 lifecycle/stale gates intentionally **not** applied to real employees while `SYNTHETIC_ONLY=on`; real ops not enabled |
| **Balance enforcement** | **NO-GO** — `balances_enforced=false`, policy `enforced=false`, `legal_reviewed=false`; observe-only only |
| **Payroll money impact** | **NO-GO / none** — provisional timesheet invalidation only; approved timesheets untouched; no payment mutation |

---

## Production SHAs and flags (final)

| File | SHA256 |
|---|---|
| `app.py` | `040e2035890a6633cd4f68517b4e0c6f42013ca0302d6ff8a617e635c8fe505d` |
| `leave_authority_wave1.py` | `ad906eec780669b41b9ce26f75c91b3ba0e94e70ba91282b3eae1b46fba90aa2` |
| `employee_lifecycle_wave3c.py` | `d981624d0f641d7e2ec64e3f619d76cde383cb4ec1e5e1c8bf349dc2d8c4a7a8` |

| Flag | Value |
|---|---|
| `WATHEFNI_LEAVE_AUTHORITY` | **on** |
| `WATHEFNI_LEAVE_AUTHORITY_COMPANIES` | **WATHEFNI** |
| `WATHEFNI_LEAVE_AUTHORITY_SYNTHETIC_ONLY` | **on** |
| `WATHEFNI_LEAVE_AUTHORITY_SYNTHETIC_KEY_MARKERS` | `LVW1B,LVW1B-SYNTH|` |
| `WATHEFNI_LEAVE_AUTHORITY_SYNTHETIC_PHONE_PREFIXES` | `965525` |
| `WATHEFNI_LEAVE_BALANCES` | on (observe-only) |
| `WATHEFNI_ATTENDANCE_CAPTURE_INGEST` | **off** |
| `WATHEFNI_ONBOARDING_SEED` | **off** |
| Accrual timer `wathefni-leave-accrual.timer` | **enabled / active** (unchanged) |

Drop-in: `/etc/systemd/system/wathefni-orchestrator.service.d/zzzz-leave-authority-wave1b-synthetic.conf`

---

## Schema, backup, rollback

| Item | Evidence |
|---|---|
| Schema pack `1.0.0` | `row_version`, `leave_authority_settings`, `leave_type_catalogue` · `MIGRATE_OK` |
| Backup | `/opt/wathefni/backups/production-pre-leave-wave1b-20260802T153714Z/` |
| Fingerprints | `leave-requests/balances/ledger-fingerprint.csv` + `SHA256SUMS` |
| Rollback script | `backup/ROLLBACK.sh` — executed → `ROLLBACK_OK`; `LEAVE_AUTHORITY` unset |
| Redeploy + canary | `verify/rollback-redeploy.out` → `ROLLBACK_REDEPLOY_OK` · post-redeploy canary `58/58` |

---

## Real leave fingerprints (unchanged)

| leave_id | status | type | fp |
|---|---|---|---|
| `e3217e0e-…` | approved | sick | `abf4cba7cb8702b2d7c067db795d0701` |
| `51cd940f-…` | rejected | sick | `8f6d67e3cc4fbf5ee321af235ecbb20d` |
| `dbf82ecf-…` | requested (stale dates) | annual | `34c7cf18a4d758698bbf7cac6da70d1f` |

Post-canary: **3** requests · **10** events · **28** ledger · **4** balances · **0** synthetic residual. Real stale request still `requested` (not expired by synthetic-only path).

---

## Synthetic IDs (examples)

| Run | Tag | Notes |
|---|---|---|
| Initial canary | `57b4df9d` | `remote/canary/canary-run.out` · phones `9655251…` / `9655252…` |
| Post-redeploy | `eb338db8` | `remote/canary/canary-post-redeploy.out` |

Markers: name `LVW1B-SYNTH|…`, phone prefix `965525`. Full IDs in remote `canary-run/ids.json` / `canary-post-redeploy/ids.json`.

---

## Concurrency & lifecycle evidence

Proven in canary (`58/58`):

- Self-approve / self-reject → `self_approval_forbidden`
- `expected_row_version` mismatch → `stale_row_version` on approve & cancel
- Lifecycle gates: terminated, suspended, future_start, notice_period blocked
- Stale synthetic → `expired_stale` (+ audit); real stale untouched
- Lifecycle decline → `declined_lifecycle`; reverse → `requested` (**not** `pending`)
- Cancel preserves `requested`/`approved`/`cancelled` event history
- Tenant isolation: other company cannot approve WATHEFNI leave
- Canonical types: annual, sick, `vacation`→`annual`; legacy vacation posts annual ledger

---

## Attendance / Payroll boundary

- Approve derived Attendance (`approved_leave` provenance)
- Manual correction after leave preserved on cancel/reverse
- Draft timesheet → `recalculation_required` only
- No payroll money mutation path
- `CAPTURE_INGEST` remained **off**

---

## Cleanup proof

- Synthetic leave/employee residual **0** after each canary
- Real fingerprints identical pre/mid/post
- Ledger/balance company totals for reals preserved (28 / 4)

---

## Freeze regressions

| Suite | Result |
|---|---|
| Employees 360 | **57/57** |
| Onboarding | **54/54** |
| Attendance | **26/26** |

---

## Remaining blockers

- Real HR leave authority still synthetic-gated (intentional)
- Legal review / `enforced=true` not started
- Production holiday calendar still empty (code path proven)
- No partial-day, attachments, carryover, unpaid workflow
- Clients must honor honesty flags (`balances_binding=false`)
- Real stale pending leave not auto-resolved until synthetic-only is lifted under a controlled Wave

---

## What was deployed (synthetic-only)

Self-approval ban (global safety) · lifecycle + stale gates for synthetics · row_version concurrency · canonical types · lifecycle reverse hygiene · API honesty flags · schema `1.0.0`.  

**Not** enabled: real employee operation, balance enforcement, new leave features, UI redesign, payroll money impact.
