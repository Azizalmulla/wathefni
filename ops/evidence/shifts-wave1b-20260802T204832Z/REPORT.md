# Shifts Wave 1B — WATHEFNI production synthetic canary

**Stamp:** `20260802T204832Z`  
**Evidence:** `ops/evidence/shifts-wave1b-20260802T204832Z/`  
**Module:** `shifts_authority_wave1.py` **v1.1.0**  
**Mode:** production WATHEFNI-only · **SYNTHETIC_ONLY** · markers **SHW1B** / **965529***  
**Prior:** Wave 1A staging GO (`20260802T182104Z`)

---

## Verdicts

| Scope | Verdict |
|---|---|
| Production synthetic Shifts authority | **GO** |
| Controlled HR Shifts use (real employees) | **NO-GO** |
| Scoped manager Shifts use | **NO-GO** |
| Talal employee-app Shifts use (expanded) | **NO-GO** |
| Broad employee-app rollout | **NO-GO** |
| Templates / recurring schedules | **NO-GO** (out of scope) |
| Payroll monetary impact | **NO-GO / none** — `payroll_money=false`; no money calculations |

Synthetic canary closed: overnight, lifecycle, concurrency, swap E2E, orphan quarantine, dashboard token, rollback→redeploy, residual **0**.

---

## Production SHAs and flags

**Before deploy**
- `app.py` `73036b5909191b09a4e3af55d8d989ba12af7e9103f5d48961cf949019699029`
- `shifts_authority_wave1.py` absent
- `WATHEFNI_ATTENDANCE_CAPTURE_INGEST=off`

**After redeploy (live)**
```
4b55894a7a9249bb5a86276095fd44f49d2c8c2a1ac15ff942a3202375702ee1  app.py
82262f2e0e7b6e9dc04c7a6e3305d50eef4816659a6b931bb40742d8160f0da7  shifts_authority_wave1.py

WATHEFNI_SHIFTS_AUTHORITY_WAVE1=1
WATHEFNI_SHIFTS_AUTHORITY_COMPANIES=WATHEFNI
WATHEFNI_SHIFTS_AUTHORITY_SYNTHETIC_ONLY=1
WATHEFNI_SHIFTS_AUTHORITY_SYNTHETIC_KEY_MARKERS=SHW1B,SHW1B-SYNTH|
WATHEFNI_SHIFTS_AUTHORITY_SYNTHETIC_PHONE_PREFIXES=965529
WATHEFNI_ATTENDANCE_CAPTURE_INGEST=off
```

Drop-in: `/etc/systemd/system/wathefni-orchestrator.service.d/zzzzzzzz-shifts-authority-wave1b-synthetic.conf`

---

## Backup and rollback evidence

| Item | Path / result |
|---|---|
| Backup | `/opt/wathefni/backups/production-pre-shifts-wave1b-20260802T204832Z` |
| Contents | `app.py`, pre-deploy dashboard-dist, systemd dropins, `shift-assignments.csv`, `shift-events.csv`, `ROLLBACK.sh` |
| Rollback | **VERIFIED** — flags cleared, health OK (`tests/rollback.out`) |
| Redeploy | **OK** — stamp `20260802T204832Z-redeploy`; canary re-run **57/0** |

---

## Orphan quarantine evidence

Allowlisted Wave 0 orphans soft-cancelled under change control (**never deleted**):

| shift_id | employee_key | result |
|---|---|---|
| `0a6e73dd-9c6d-49a0-b253-39a9922ebd70` | `WATHEFNI-96596552203` | cancelled + quarantine + audit |
| `6a84a671-eb7f-43ea-870e-af859a440467` | `WATHEFNI-96552202357` | cancelled + quarantine + audit |
| `f9ebecf3-8838-456a-8124-c34c3c7600ca` | `WATHEFNI-96552263564` | cancelled + quarantine + audit |

- `shift_events.event_type=orphan_quarantined`
- `shift_lifecycle_flags` open (`orphan_employee_key`)
- `shift_orphan_quarantine` snapshots with reversible metadata (`quarantine_active=3`)
- No valid employee assignment mutated

---

## Synthetic IDs

Tags: before-rollback `8928b7bd` · after-redeploy `a5a2f037`  
Marker `SHW1B` · phones `965529*` · full dumps: `artifacts/synthetic-ids-final.json`, `remote/canary/*/synthetic-ids.json`

After-redeploy cleanup deleted shift IDs (sample set): see `qualification.json` → `cleanup.deleted_shift_ids`.

---

## Test counts

| Suite | Before rollback | After redeploy |
|---|---:|---:|
| Production synthetic canary | **57 / 0** | **57 / 0** |
| Employees 360 freeze (local) | 57 / 0 | — |
| Onboarding freeze (local) | 54 / 0 | — |
| Attendance freeze (local) | 26 / 0 | — |
| Leave freeze (local) | 35 / 0 | — |
| Employees 360 freeze (prod) | — | 57 / 0 |
| Onboarding freeze (prod) | — | 54 / 0 |
| Attendance freeze (prod) | — | 21 / 1* |
| Leave freeze (prod) | — | 34 / 0 |

\*Prod attendance freeze miss is **cursor rule path only** (`/opt/wathefni/.cursor/rules/…` absent on VPS). Local attendance freeze **26/0**; authority/ops assertions on prod passed. Not a Shifts regression.

Proven: same-day create/cancel · overnight 22–06 create+dashboard reschedule · split · overlaps · idempotent create/cancel · stale + concurrent reschedule · lifecycle matrix · leave require_ack/block/cancel_shift · swap E2E · tenant isolation · break/site metadata · Attendance overnight parity · no Leave/Payroll money mutation · dashboard `expected_updated_at`.

---

## Cleanup and fingerprint proof

- Residual synthetic assignments / employees / swaps: **0**
- Real assignment fingerprints unchanged except the three quarantined orphans (+ their audit/quarantine rows)
- Final state: `artifacts/final-state.txt`

---

## Remaining blockers

1. Real-employee Wave 1 authority still **NO-GO** (SYNTHETIC_ONLY retained).  
2. Controlled HR / scoped manager / Talal expanded / broad app — **NO-GO**.  
3. Templates / recurring / rotations / publish / open shifts — not built.  
4. Prod attendance freeze cursor-rule path gap on VPS (pre-existing; local green).  
5. Quarantined orphans remain cancelled pending any future restore decision (reversible via quarantine metadata).

---

## Scope notes

- Wave 1 lifecycle / leave / overnight gates apply to **SHW1B / 965529*** only under SYNTHETIC_ONLY; legacy same-day behaviour retained for real employees.  
- Dashboard dist rebuilt and deployed with concurrency token.  
- No templates, recurring, rotations, publish, open shifts, or Payroll money enabled.
