# Migration Wave 1 — Foundation + Chunked CV Intake (staging)

**Stamp:** 20260803T211505Z  
**Evidence:** `ops/evidence/migration-wave1-staging-20260803T211505Z/`  
**Gate:** `STAGING_MIGRATION_WAVE1_FOUNDATION_CV_GO`

## Scope shipped
- Shared migration batch / row / chunk-job / event contract
- Dry-run + exception queue
- Durable chunked CV intake with retry + DLQ replay
- Staged folder / object-storage-style intake under workspace stage root
- Optional external ATS candidate ID preservation (sidecar / meta.json)
- Held-by-default authority; auto-admit forced OFF on Wave 1 path
- Checksum deduplication without auto-merge
- Progress, audit events, rollback; residual 0 after teardown

## Explicit out of scope
Real customer data, millions claim, Migration Center UI, employee/leave/compensation migration,
Payroll money, Attendance ingest, AI assistant expand, mobile, Migration Wave 2, production synthetic.

## Proof
- Staging smoke: core + 1 000 + 10 000 synthetic CVs — PASS
- Retry / resume / DLQ replay covered in core lane
- Duplicate handling + tenant isolation + no auto-admit asserted
- Residual 0 after rollback/teardown
- Sibling freezes: green
- Lanes: 1k ≈36.7s (981 committed / 19 duplicates); 10k ≈521.5s (9981 committed / 19 duplicates)

## Production synthetic qualification
**NO-GO** until a separate Wave 1-B authorization. Staging GO does not authorize prod synthetic.

## Next (not this wave)
Migration Wave 2 — **not started**.
