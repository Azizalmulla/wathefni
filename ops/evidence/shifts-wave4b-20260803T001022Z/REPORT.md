# Shifts Wave 4B — production synthetic templates & recurring schedules canary

**Stamp:** `20260803T001022Z`  
**Evidence:** `ops/evidence/shifts-wave4b-20260803T001022Z/`  
**Staging gate:** `ops/evidence/shifts-wave4-20260802T234919Z` (**GO**)  
**Module:** `shifts_templates_wave4.py` **v4.0.0** · cleanup contract **1.1.0**

## Scope
Production WATHEFNI synthetic-only canary for templates + weekly/cycle recurrence materialization.  
Markers: **SHW4B** / **965533***. Real allowlists empty. Real mutation gate **on**. Real reminders **off**. Integrity jobs **0** (service). CAPTURE_INGEST **off**.

## Verdicts

| Scope | Verdict |
|---|---|
| Production synthetic templates & recurring schedules | **GO** |
| Controlled real template use | **NO-GO** |
| Controlled real recurrence materialization | **NO-GO** |
| HR/manager production scheduling | **NO-GO** (allowlists empty) |
| Draft/publish readiness | **NO-GO** |
| Broad employee-app access | **NO-GO** |

## Production SHAs / flags (post-redeploy)
- `app.py` `c5a0c198…fe32f`
- `shifts_templates_wave4.py` `2ff2e89d…1997f` (deadlock-retry materialize)
- `shifts_synthetic_cleanup.py` `a518c5d0…b3d1` (contract **1.1.0**, `wave4b_scope`)
- Drop-in: `remote/flags/shifts-wave4b-synthetic.conf`
- Live: `WATHEFNI_SHIFTS_WAVE4=1` · `SYNTHETIC_ONLY=1` · markers `SHW4B,SHW4B-SYNTH|` · phones `965533` · `INTEGRITY_JOBS=0` · `REAL_REMINDERS=0` · empty HR/manager allowlists · `CAPTURE_INGEST=off`

## Backup / rollback
- Backup path recorded under `rollback/` / remote `BACKUP_PATH.txt`
- Table dumps: `shift_assignments` + Wave 4 planning tables
- Rollback exercised: **ROLLBACK_OK** (`tests/rollback.out`) then redeploy #2

## Synthetic IDs (canary #2 tag `88988BA1`)
- Templates: day `1ad5e255-…`, night `2df93218-…`, afternoon `33b0a656-…`
- Recurrences: weekly `c10bc6b1-…`, six-on `b10a1afe-…`, alt `76e0536b-…`, team `9bd54a0f-…`, site `671ebd86-…`, role `86c31202-…`, split `bf022886-…`, miss-target `83df9148-…`
- Employees: `WATHEFNI-SHW4B-88988BA1`, `WATHEFNI-SHW4B-B-88988BA1`
- Sample weekly generated assignment IDs: see `remote/canary/canary2/results.json` (`weekly_created`, 16 rows)

## Materialization / regeneration evidence
- Preview classes exercised; incomplete target → explicit `skipped_target`
- Duplicate materialize idempotent; concurrent advisory lock one winner
- Overnight / split / team / site / role / six-on materialize
- Pause / resume / end; skip + one-off exception; cancelled_held; manual detach
- Template edit bumps planning version without silent historical rewrite
- Artifacts: `remote/canary/canary{1,2}/{preview-weekly,fps-*,cleanup,residual-final,results}.json`

## Cleanup contract updates
- Version **1.1.0**
- `wave4b_scope()` → markers `SHW4B` / `SHW4B-SYNTH|`, phones `965533*`
- Residual + delete cover templates, recurrences, exceptions, recurrence events, provenance `occurrence_key`

## Test counts
| Suite | Before redeploy (canary #1) | After redeploy (canary #2) |
|---|---|---|
| Wave 4B canary | **75 passed, 0 failed** | **75 passed, 0 failed** |
| Real fps unchanged | PASS | PASS |
| Residual zero | PASS | PASS |

### Coexistence (post-hygiene; W2B jobs in-process only)
| Suite | Result |
|---|---|
| Wave 1B canary | **57/0** |
| Wave 2B canary | **108/0** (`INTEGRITY_JOBS=1` in-process; service remains `0`) |
| Wave 3B canary | **31/0** |
| Wave 3 UX | **43/0** |
| Wave 1 smoke | **90/0** |
| Wave 2 smoke | **82/0** |
| Freezes E360/ONB/ATT/LEAVE | **57/0 · 54/0 · 22/0 · 34/0** |
| Service `INTEGRITY_JOBS` after coexist | **0** (confirmed) |

## Fingerprint / residual proof
- Real assignment / template / recurrence / exception / version fps unchanged across both canaries
- SHW4B residual total **0** after each canary cleanup
- Coexistence hygiene cleared prior-wave synthetic leftovers before W1B/W2B/W3B

## Remaining blockers
- Real template authoring / real recurrence materialization still gated (synthetic-only)
- Empty HR/manager allowlists — controlled real scheduling **NO-GO**
- Draft/publish, rotations, coverage, open shifts, PAM — not built
- Real reminders / timers remain disabled by design
- Broad employee-app access — **NO-GO**

## Gate result
**PROD_SYNTHETIC_WAVE4_TEMPLATES_GO**
