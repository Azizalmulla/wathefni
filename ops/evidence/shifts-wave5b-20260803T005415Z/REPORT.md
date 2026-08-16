# Shifts Wave 5B — production synthetic publish, open-shift & coverage canary

**Stamp:** `20260803T005415Z`  
**Evidence:** `ops/evidence/shifts-wave5b-20260803T005415Z/`  
**Staging gate:** `/Users/azizalmulla/Desktop/claw/ops/evidence/shifts-wave5-20260803T004110Z` (**GO**)  
**Module:** `shifts_publish_wave5.py` **v5.0.0** · cleanup contract **1.2.0**

## Scope
Production WATHEFNI synthetic-only canary for draft → review → approve → publish, open shifts, and coverage.  
Markers: **SHW5B** / **965535***. Real allowlists empty. Real mutation gate **on**. Real reminders **off**. Integrity jobs **0**. CAPTURE_INGEST **off**.

## Verdicts

| Scope | Verdict |
|---|---|
| Production synthetic Wave 5 (publish/open/coverage) | **NO-GO** |
| Controlled real draft creation | **NO-GO** |
| Controlled real publishing | **NO-GO** |
| Controlled real open shifts | **NO-GO** |
| HR/manager production scheduling | **NO-GO** (allowlists empty) |
| Wave 6 readiness | **NO-GO** (rotations/remote hitches/PAM not built) |
| Broad employee-app access | **NO-GO** |

## Deploy / rollback
- Deploy #1 / redeploy #2: see `tests/deploy*.out`
- Rollback: **YES** (`tests/rollback.out`, `rollback/`)
- Flags: `remote/flags/shifts-wave5b-synthetic.conf`
- UI probe: **YES** (`tests/ui-probe1.out`)
- Preflight / verify: `remote/preflight/`, `remote/verify/`

### SHAs / flags
```
=== SHAs before ===
c5a0c198239c8da90367fab984424f0bea464b7d502e7188dedb4d022c7fe32f  /opt/wathefni/orchestrator/app.py
d6172b85d6aa071813018df60d85a4a1dc3520bb188419ee102b4563b43db336  /opt/wathefni/orchestrator/shifts_publish_wave5.py
2ff2e89d3be656069297253e9c7e8bb3c10dd2a74268487fef6c3878a811997f  /opt/wathefni/orchestrator/shifts_templates_wave4.py
a518c5d0f427169661036098abfb04c0f5c80e83a364a6c9699bd973e4b8b3d1  /opt/wathefni/orchestrator/shifts_synthetic_cleanup.py
088dd8a1dff8d107ff96a6797a8aa6ca12857210348679edaf4f261e6a23cbc8  /opt/wathefni/orchestrator/shifts_wave3_controlled.py
0f26fa3c65e4a81976f4ddec4ee515a4b66727d6d9e72599d81ca66ad7582593  /opt/wathefni/orchestrator/shifts_authority_wave1.py
af4c283f0bff577ae9eca461426c92d025fbbc08d43dbea420296589632efaad  /opt/wathefni/orchestrator/shifts_schedule_integrity_wave2.py
=== flags before ===
WATHEFNI_ATTENDANCE_CAPTURE_INGEST=off
WATHEFNI_DASHBOARD_DIST=/opt/wathefni/dashboard-dist
WATHEFNI_SHIFTS_ALLOW_OVERNIGHT=1
WATHEFNI_SHIFTS_AUTHORITY_COMPANIES=WATHEFNI
WATHEFNI_SHIFTS_AUTHORITY_SYNTHETIC_KEY_MARKERS=SHW1B,SHW1B-SYNTH|,SHW1,SHW1-SYNTH|,SHW2,SHW2-SYNTH|,SHW2B,SHW2B-SYNTH|,SHW3B,SHW3B-SYNTH|,SHW4B,SHW4B-SYNTH|
WATHEFNI_SHIFTS_AUTHORITY_SYNTHETIC_ONLY=1
WATHEFNI_SHIFTS_AUTHORITY_SYNTHETIC_PHONE_PREFIXES=965529,965528,965530,965531,965533
WATHEFNI_SHIFTS_AUTHORITY_WAVE1=1
WATHEFNI_SHIFTS_HR_ALLOWLIST=
WATHEFNI_SHIFTS_INTEGRITY_COMPANIES=WATHEFNI
WATHEFNI_SHIFTS_INTEGRITY_JOBS=0
WATHEFNI_SHIFTS_INTEGRITY_SYNTHETIC_KEY_MARKERS=SHW2,SHW2-SYNTH|,SHW2B,SHW2B-SYNTH|,SHW2C,SHW3B,SHW3B-SYNTH|,SHW4B,SHW4B-SYNTH|
WATHEFNI_SHIFTS_INTEGRITY_SYNTHETIC_ONLY=1
WATHEFNI_SHIFTS_INTEGRITY_SYNTHETIC_PHONE_PREFIXES=965529,965530,965531,965533
WATHEFNI_SHIFTS_INTEGRITY_WAVE2=1
WATHEFNI_SHIFTS_MANAGER_ALLOWLIST=
WATHEFNI_SHIFTS_REAL_MUTATION_GATE=1
WATHEFNI_SHIFTS_REAL_REMINDERS=0
WATHEFNI_SHIFTS_WAVE3=1
WATHEFNI_SHIFTS_WAVE3_COMPANIES=WATHEFNI
WATHEFNI_SHIFTS_WAVE3_SYNTHETIC_KEY_MARKERS=SHW3B,SHW3B-SYNTH|,SHW4B,SHW4B-SYNTH|
---
=== SHAs after ===
53b6e4553a5f95ab156e24ecce82b66569fcc0924b5f9a442516c9c2ff9f40c6  /opt/wathefni/orchestrator/app.py
d6172b85d6aa071813018df60d85a4a1dc3520bb188419ee102b4563b43db336  /opt/wathefni/orchestrator/shifts_publish_wave5.py
2ff2e89d3be656069297253e9c7e8bb3c10dd2a74268487fef6c3878a811997f  /opt/wathefni/orchestrator/shifts_templates_wave4.py
aee228f34711b434ad81ab0a86480690108845f1db641a9f72344361846cef03  /opt/wathefni/orchestrator/shifts_synthetic_cleanup.py
=== schema after ===
shift_schedule_periods shift_schedule_periods
shift_schedule_versions shift_schedule_versions
shift_schedule_draft_rows shift_schedule_draft_rows
shift_open_shifts shift_open_shifts
shift_open_shift_claims shift_open_shift_claims
shift_coverage_rules shift_coverage_rules
w5_l0_cols ['schedule_period_id', 'schedule_source', 'schedule_version_id']
```

## Canary results
- Canary #1: 83 passed, 0 failed
- Canary #2: 83 passed, 0 failed
- Real fingerprints unchanged: YES
- Cleanup residual zero: YES
- Canary artifacts: `remote/canary/{canary1,canary2}/` (ids, fps, residual, results.json)

## Coexistence / regressions
- Wave 1B: YES · Wave 2B: YES · Wave 3B: YES · Wave 4B: NO
- Wave 1 smoke: YES · Wave 2: YES · Wave 3 UX: YES
- Freezes: YES (rc=0)
- Details: `tests/coexistence.out`

## Gates held
- WATHEFNI only · SHW5B / 965535* · empty HR/manager allowlists · real mutation gate on · real reminders off · integrity jobs 0 · CAPTURE_INGEST off · no real publishing / real open-shift claims / rotations / PAM / Payroll money

## Honesty
Payroll money false · Leave balances not mutated · Attendance authority not mutated · Draft/publish/open/coverage true for Wave 5 honesty · Rotations/PAM false · Wave 4 honesty still publishing false.

## Gate result
PROD_SYNTHETIC_WAVE5_PUBLISH_NO_GO
