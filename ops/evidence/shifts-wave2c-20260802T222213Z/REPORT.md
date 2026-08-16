# Shifts Wave 2C — canary compatibility and qualification closure

**Stamp:** `20260802T222213Z`  
**Evidence:** `ops/evidence/shifts-wave2c-20260802T222213Z/`  
**Remote:** `/opt/wathefni/production-evidence/shifts-wave2c-compat/20260802T222213Z/`  
**Cleanup contract:** `shifts_synthetic_cleanup.py` **v1.0.0**

Scope: production WATHEFNI synthetic-only. No real-employee mutations, no dashboard UX, no templates/recurring, no broad app access, no Payroll money.

---

## Final verdict — close Shifts Wave 2

| Decision | Result |
|---|---|
| **Close Shifts Wave 2 (synthetic schedule integrity)** | **GO** |
| Controlled real-use UX / HR scheduling | **NO-GO** (separate authorization) |
| Real-employee mutations | **NO-GO** (`SYNTHETIC_ONLY=1` retained) |
| Recurring job timers for production traffic | **NO-GO** (units installed, timers **disabled**) |

Wave 2B synthetic Schedule Integrity remains **GO**. Wave 2C closes the canary-compat gap that previously required operator mop-up.

---

## Shared cleanup contract and deletion order

**Module:** `wathefni-orchestrator/shifts_synthetic_cleanup.py`  
**Presets:** `wave1b_scope()` (SHW1B / 965529*) · `wave2b_scope()` (SHW2B / 965530*)

**Rules**
- Marker + phone-prefix scoped only; never deletes non-marker rows
- Protected orphan allowlist never hard-deleted
- SAVEPOINT around optional Wave 2 tables (idempotent after partial failure)
- Sibling waves cannot delete each other
- Qualification fails if `residual_total != 0` (no operator cleanup as a pass)

**Deletion order (children → parents)**

1. `shift_reminder_queue`
2. `shift_reconciliation_flags`
3. `shift_assignment_versions`
4. `shift_lifecycle_flags`
5. `shift_orphan_quarantine` (synthetic only)
6. `shift_swap_events`
7. `shift_swap_requests`
8. `shift_events`
9. `employee_availability_requests`
10. `shift_assignments`
11. `leave_requests`
12. `shift_seasonal_policies`
13. `employees`

Wave 1B + Wave 2B canaries both call `cleanup_synthetic_scope(...)`.

---

## Updated Wave 1B and Wave 2B results

| Suite | Passed | Failed | Residual |
|---|---:|---:|---:|
| Wave 1B canary (under Wave 2 schema) | **57** | **0** | **0** |
| Wave 2B canary | **108** | **0** | **0** |
| Wave 2C compat prove | **26** | **0** | **0** (both families) |

Wave 1B previously failed residual under Wave 2 FK/history tables; shared cleanup now clears versions / reminders / recon flags and fails closed if any remain.

---

## Timer-unit and kill-switch evidence

**Installed (disabled by default)**

| Unit | Enabled | Active |
|---|---|---|
| `wathefni-shifts-reminder-drain.timer` | disabled | inactive |
| `wathefni-shifts-lifecycle-recon.timer` | disabled | inactive |
| `wathefni-shifts-leave-recon.timer` | disabled | inactive |

Install: `ops/install-shifts-wave2-job-timers.sh` → `SHIFTS_W2C_TIMERS_INSTALLED_DISABLED`  
Final: `TIMERS_STILL_DISABLED`

**Proven**
- oneshot `systemctl start --wait` for each service (synthetic-only runner)
- kill switch `WATHEFNI_SHIFTS_INTEGRITY_JOBS=0` → `shifts_wave2_jobs_disabled`
- advisory lock contention → `job_lock_held`; resume OK after release
- timers left disabled after qualification (no recurring real-record activation)

Runbook: `ops/runbooks/shifts-wave2b-operator-jobs.md`

---

## Residual and fingerprint proof

| Check | Result |
|---|---|
| Wave 1B residual | **0** |
| Wave 2B residual | **0** |
| Cross-marker isolation | Wave1 cleanup leaves Wave2; Wave2 cleanup leaves Wave1 |
| Interrupted cleanup rerun | residual **0** (idempotent) |
| Real assignment fingerprints | **unchanged** (count **23**) |
| Real events / swaps / availability / versions / reminders | **unchanged** across prove |
| Orphan quarantine allowlist | preserved (never hard-deleted) |

---

## Remaining blockers (post Wave 2 close)

1. Real-employee schedule integrity still gated
2. Dashboard UX for ack / warnings / recon / terminal board not built
3. Job timers installed but not enabled (intentional)
4. Templates / recurring / rotations / publishing / open shifts / PAM out of scope
5. Controlled HR / manager / Talal / broad app scheduling still **NO-GO**

---

## Bottom line

**Shifts Wave 2 is closed for production synthetic Schedule Integrity: GO.**  
Canaries are mutually compatible and self-cleaning. Operator job foundations are packaged and proven with timers remaining disabled. Controlled real-use UX is the next authorized step — not enabled by this wave.
