# Shifts Wave 2B — WATHEFNI production synthetic schedule-integrity canary

**Stamp:** `20260802T214616Z`  
**Evidence:** `ops/evidence/shifts-wave2b-20260802T214616Z/`  
**Remote:** `/opt/wathefni/production-evidence/shifts-wave2b-prod-canary/20260802T214616Z/`  
**Module:** `shifts_schedule_integrity_wave2.py` **v2.0.0** (+ Wave 1 authority **1.1.0**)  
**Mode:** production WATHEFNI-only · **SYNTHETIC_ONLY** · markers **SHW2B** / **965530***  

Real employee shifts, availability, swaps, and reconciliation remain blocked. No dashboard UX, templates, recurring schedules, rotations, publishing, open shifts, PAM export, or Payroll money.

---

## Verdicts

| Scope | Verdict |
|---|---|
| Production synthetic Schedule Integrity | **GO** |
| Controlled HR scheduling | **NO-GO** |
| Scoped manager scheduling | **NO-GO** |
| Talal employee-app scheduling | **NO-GO** |
| Broad employee-app rollout | **NO-GO** |
| Templates and recurring schedules | **NO-GO** (out of scope) |
| Payroll monetary impact | **NO-GO / none** — `payroll_money=false`; no money calculations |

---

## Production SHAs and flags

### Before deploy (Wave 1B posture)

| Artifact | SHA256 |
|---|---|
| `app.py` | `4b55894a7a9249bb5a86276095fd44f49d2c8c2a1ac15ff942a3202375702ee1` |
| `shifts_authority_wave1.py` | `82262f2e0e7b6e9dc04c7a6e3305d50eef4816659a6b931bb40742d8160f0da7` |
| `shifts_schedule_integrity_wave2.py` | absent |

Flags before:

```
WATHEFNI_SHIFTS_AUTHORITY_WAVE1=1
WATHEFNI_SHIFTS_AUTHORITY_COMPANIES=WATHEFNI
WATHEFNI_SHIFTS_AUTHORITY_SYNTHETIC_ONLY=1
WATHEFNI_SHIFTS_AUTHORITY_SYNTHETIC_KEY_MARKERS=SHW1B,SHW1B-SYNTH|
WATHEFNI_SHIFTS_AUTHORITY_SYNTHETIC_PHONE_PREFIXES=965529
WATHEFNI_ATTENDANCE_CAPTURE_INGEST=off
```

### After redeploy (live)

| Artifact | SHA256 |
|---|---|
| `app.py` | `89ba8c7e32596761dce6596bd6d3c4bae165502442209f0538dcd4ad940dd5d3` |
| `shifts_authority_wave1.py` | `0f26fa3c65e4a81976f4ddec4ee515a4b66727d6d9e72599d81ca66ad7582593` |
| `shifts_schedule_integrity_wave2.py` | `af4c283f0bff577ae9eca461426c92d025fbbc08d43dbea420296589632efaad` |

Flags live:

```
WATHEFNI_SHIFTS_AUTHORITY_WAVE1=1
WATHEFNI_SHIFTS_AUTHORITY_COMPANIES=WATHEFNI
WATHEFNI_SHIFTS_AUTHORITY_SYNTHETIC_ONLY=1
WATHEFNI_SHIFTS_AUTHORITY_SYNTHETIC_KEY_MARKERS=SHW1B,SHW1B-SYNTH|,SHW2B,SHW2B-SYNTH|
WATHEFNI_SHIFTS_AUTHORITY_SYNTHETIC_PHONE_PREFIXES=965529,965530
WATHEFNI_SHIFTS_INTEGRITY_WAVE2=1
WATHEFNI_SHIFTS_INTEGRITY_COMPANIES=WATHEFNI
WATHEFNI_SHIFTS_INTEGRITY_SYNTHETIC_ONLY=1
WATHEFNI_SHIFTS_INTEGRITY_SYNTHETIC_KEY_MARKERS=SHW2B,SHW2B-SYNTH|
WATHEFNI_SHIFTS_INTEGRITY_SYNTHETIC_PHONE_PREFIXES=965530
WATHEFNI_SHIFTS_INTEGRITY_JOBS=1
WATHEFNI_ATTENDANCE_CAPTURE_INGEST=off
```

Drop-in: `/etc/systemd/system/wathefni-orchestrator.service.d/zzzzzzzz-shifts-integrity-wave2b-synthetic.conf` (**DROPIN_PRESENT**)

---

## Backup and rollback evidence

| Item | Path / result |
|---|---|
| Backup | `/opt/wathefni/backups/production-pre-shifts-wave2b-20260802T214616Z` |
| Contents | `app.py`, Wave modules, dashboard-dist, systemd drop-ins, CSV dumps of assignments/events/swaps/availability/versions/reminders/seasonal/recon, `ROLLBACK.sh`, `SHA256SUMS` |
| Rollback | **VERIFIED** — `ROLLBACK_OK` · `SHIFTS_INTEGRITY_FLAGS_CLEARED` · `ROLLBACK_VERIFIED` (Wave 2B drop-in removed) |
| Redeploy | **OK** — stamp `20260802T214616Z-redeploy`; canary re-run **108/0** |

Evidence: `remote/backup/`, `tests/rollback.out`, `tests/redeploy.out`.

---

## Job schedules, locking and runbooks

Source: `wathefni-orchestrator/ops/runbooks/shifts-wave2b-operator-jobs.md`  
Runner: `ops/run-shifts-wave2b-jobs.sh` (manual / operator-driven; not systemd timers yet)

| Job | Advisory lock | Cadence (suggested) | Bound |
|---|---|---|---|
| Reminder drain | `820260201` | every 5–15 min | `limit≤200` |
| Lifecycle reconciliation | `820260202` | after employment fact changes / hourly | `limit≤200` |
| Leave reconciliation | `820260203` | after leave approvals / hourly | `limit≤200` |

Controls proven in canary:

- Concurrent overlap → `job_lock_held`
- Kill switch → `WATHEFNI_SHIFTS_INTEGRITY_JOBS=0` disables jobs; resume after re-enable
- Synthetic-only filter; flag-only recon (no silent cancel)
- Terminal failure visibility via reminder scan `terminal_failures`

---

## Synthetic IDs

Markers: **SHW2B** · phones **965530*** · gate-check phone intentionally outside allowlist (**965528***) to prove synthetic-only block.

### Before rollback (tag `2f680304`)

| Kind | IDs |
|---|---|
| Employees | `WATHEFNI-SHW2B-2f680304`, `…-B-…`, `…-C-…`, gate `WATHEFNI-W2GATECHK-2f680304` |
| Phones | `965530268030`, `965530680309`, `965530803077`, gate `965528268030` |
| Shifts (18) | `7265c443-…`, `a097d4fa-…`, `40ced753-…`, `310909c4-…`, `6b8c1628-…`, `84d63bf4-…`, `f5eea050-…`, `21c1a309-…`, `172c90ef-…`, `8d73d6c0-…`, `030b1b51-…`, `4050e528-…`, `237bb890-…`, `3d536348-…`, `3cfdc5bf-…`, `5bfea82f-…`, `f7d97f0d-…`, `2e2dffa1-…` |
| Swaps (5) | `c7841926-…`, `9c292e99-…`, `1cb9d3a6-…`, `adf2e986-…`, `225a915c-…` |
| Availability (2) | `f4b61c97-…`, `19e8511d-…` |
| Leave (2) | `fec6d961-…`, `576f6612-…` |
| Policies (3) | `1f7e1271-…`, `12fe7203-…`, `c0573cce-…` |
| Recon flags (3) | `0f893927-…`, `270be3d2-…`, `fbebb627-…` |

### After redeploy (tag `d253b563`)

| Kind | IDs |
|---|---|
| Employees | `WATHEFNI-SHW2B-d253b563`, `…-B-…`, `…-C-…`, gate `WATHEFNI-W2GATECHK-d253b563` |
| Phones | `965530253563`, `965530535639`, `965530356377`, gate `965528253563` |
| Shifts (18) | `56572a3f-…`, `728295fc-…`, `c9311b5d-…`, `47369899-…`, `15234f85-…`, `0de263f8-…`, `99c25392-…`, `86b586b6-…`, `38a44383-…`, `d1a2956d-…`, `12d22152-…`, `5739265f-…`, `9d399eb4-…`, `e17765b0-…`, `c707e722-…`, `23f725f8-…`, `c81c57ce-…`, `c4989505-…` |
| Swaps (5) | `6cb2be1e-…`, `a14c5ba0-…`, `88add21e-…`, `72a2f827-…`, `40f4dc5b-…` |
| Availability (2) | `cf8a4ce5-…`, `175af9d5-…` |
| Leave (2) | `3b225995-…`, `dfc1e7ef-…` |
| Policies (3) | `85599f69-…`, `e63c5609-…`, `45484342-…` |
| Recon flags (3) | `a29ebc43-…`, `eebc573a-…`, `1488ef44-…` |

Full UUID lists: `remote/canary/*/qualification.json`.

---

## Test counts

| Pass | Passed | Failed |
|---|---:|---:|
| Canary before rollback | **108** | **0** |
| Canary after redeploy | **108** | **0** |
| Wave 1B synthetic coexistence regress | 56 | 1 (cleanup residual; operator-cleaned; baseline restored — not a Wave 2B product fail) |
| Employees 360 freeze | 57 | 0 |
| Onboarding freeze | 54 | 0 |
| Attendance freeze | 22 | 0 |
| Leave freeze | 34 | 0 |

Canary coverage (synthetic only): immutable multi-reschedule versions; one current authority; stale/concurrent fail-closed; availability approve/reject + warn/require_ack/block; swap approve/reject/replay/lineage; overlap/lifecycle/leave/scope denials; normal/split/overnight Attendance matching; ambiguous fail-closed; reminder enqueue/claim/retry/backoff/terminal; no duplicate delivery; reschedule cancels stale reminder; Ramadan + midday seasonal scope; lifecycle/leave recon flags; ack + audited soft-cancel; real-employee gate block; jobs lock + kill switch; residual **0**; fingerprints unchanged.

**Note:** generic `smoke-test-shifts-authority-wave1.py` is **not** a valid prod regressor under current SYNTHETIC_ONLY (uses SHW1 / 965528 outside allowlist). Use `canary-prod-shifts-wave1b.py` for Wave 1 coexistence.

---

## Cleanup and fingerprint proof

| Check | Before rollback | After redeploy |
|---|---|---|
| Residual synthetic total | **0** | **0** |
| Real assignment count | **23** | **23** |
| Real assignment fingerprints | unchanged | unchanged |
| Events / swaps / availability baseline | 31 / 0 / 0 | 31 / 0 / 0 |

Pre-deploy fingerprint baseline: `remote/preflight/fingerprints-before.json` (`assignment_count=23`).  
Orphan quarantine rows from Wave 1C remain cancelled (fps unchanged): `0a6e73dd-…`, `6a84a671-…`, `f9ebecf3-…`.

Wave 1B regress temporarily left 2 assignments + 2 swaps (Wave 2 FK/version tables); operator cleanup restored exact pre-2B baseline (**BASELINE_RESTORED**). Wave 2B canaries themselves cleaned to residual **0**.

---

## Remaining blockers

1. Real-employee schedule integrity still gated (`SYNTHETIC_ONLY=1`)
2. Dashboard UX for ack/warnings/recon/terminal board not built
3. Operator jobs are runbook/manual — not systemd timers yet
4. Templates / recurring / rotations / publishing / open shifts / PAM still out of scope
5. Wave 1B canary cleanup should learn Wave 2 FK tables (versions/reminders) to avoid residual when co-run

---

## Bottom line

**Production synthetic Schedule Integrity: GO.**  
All other product scopes remain **NO-GO** pending separate authorization.
