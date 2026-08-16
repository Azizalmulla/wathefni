# Migration Wave 1-B — production synthetic Foundation + Chunked CV Intake

**Stamp:** `20260804T024331Z`  
**Evidence:** `ops/evidence/migration-wave1b-prod-canary-20260804T024331Z/`  
**Staging prerequisite:** `ops/evidence/migration-wave1-staging-20260803T211505Z`  
**Freeze doc:** `ops/MIGRATION_WAVE1_FOUNDATION_CV_FREEZE.md`

## Verdicts

| Scope | Verdict |
|---|---|
| Production synthetic Migration Wave 1 | **GO** |
| Freeze Migration Wave 1 | **GO** |
| Migration Wave 2 | **NO-GO** (not started) |
| Real customer / millions cutover | **NO-GO** |

## Proof

- Deploy + ACK migrate → True
- Canary before rollback (1k+10k, residual 0) → True
- Drop-in/module rollback verified → True
- Canary after redeploy → True
- Sibling freezes green → True
- Lanes: {"1k": {"elapsed_s": 28.94, "committed": 981, "duplicates": 19}, "10k": {"elapsed_s": 284.11, "committed": 9981, "duplicates": 19}}

## Flags

`WATHEFNI_MIGRATION_WAVE1=1` · `SYNTHETIC_ONLY=1` · `COMPANIES=WATHEFNI` · ingest off · mutations off

## Rollback

`/opt/wathefni/backups/production-pre-migration-wave1b-*` + `ROLLBACK.sh`  
(Durable `migration_wave_acks` rows retained.)

## Wave 1-BR / deadlock remediation (this rerun)

- Runtime DDL: `apply_calls=0` on both canary passes
- `WATHEFNI_SCHEMA_APPLY` unset throughout
- DeadlockDetected lines in canary logs: **0**
- Scale lanes used `extraction_policy=defer` (extraction_jobs_cancelled=0 on rollback)
- Document-processing foundation SHAs unchanged; hybrid `production_authority`; GPT auto OCR `off`
- Failed counts on scale lanes: **0** (committed+duplicates account for full N)

