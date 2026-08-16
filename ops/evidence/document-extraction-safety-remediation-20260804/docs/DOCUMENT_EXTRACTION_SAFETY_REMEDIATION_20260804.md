# Document Extraction Safety Remediation

Date: 2026-08-04  
Scope: change-control only; production orphan cancellation plus staging synthetic safety proof  
Production routing: unchanged  
Paid OCR calls: none  
Migration Wave 1-B qualification: not run

## Outcome

**GO to resume Migration Wave 1-B through a new owner-approved qualification run.**

The run must begin with deployment of the remediated `app.py`, migration module, and canary. The 1,000/10,000 qualification was intentionally not run during this remediation.

## Production orphan cancellation

- Exactly 349 WATHEFNI `cv_extraction` jobs from the failed Wave 1-B `other_ats_export` window were locked and cancelled transactionally.
- Before cancellation: 325 pending, 24 retrying, 0 running.
- Linked candidate documents: 0.
- Linked applications: 0.
- After cancellation: active pending/running/retrying/waiting count 0.
- Every job ID, original status, attempts, timestamps, subject identifiers, and cancellation reason was preserved.
- Cancellation reason: `orphan_wave1b_owner_approved_safety_remediation`.
- No queue jobs were deleted.
- Current `email_inbound` jobs were not selected or modified.

Evidence:

- `ops/evidence/document-extraction-safety-remediation-20260804/orphan-cleanup/cancel-349-transaction.json`
- `ops/evidence/document-extraction-safety-remediation-20260804/orphan-cleanup/post-cancel-verification.json`

## Remaining failed-canary residue

Read-only verification found one dedicated synthetic `MIGW1BRAVO` company and one already rolled-back batch. The transaction refused cleanup until it proved:

- applications: 0;
- candidates linked to the company: 0;
- linked documents/apps for its queue jobs: 0;
- actual import batch/items behind the stale reference: 0;
- five queue jobs were terminal `dead_letter` records with `candidate_document_missing`.

Only synthetic migration/company metadata was removed. The five terminal jobs were retained. Five equivalent terminal jobs for the other isolation tenant were also retained and not modified.

Final production state:

- synthetic isolation companies: 0;
- migration batches in WATHEFNI/MIGW1ALPHA/MIGW1BRAVO scope: 0;
- committed migration rows: 0;
- active `other_ats_export` queue jobs: 0;
- jobs linked to current documents/apps: 0;
- terminal queue evidence retained: 349 cancelled and 10 dead-letter jobs.

Evidence:

- `ops/evidence/document-extraction-safety-remediation-20260804/residual-cleanup/migw1bravo-synthetic-residual.json`
- `ops/evidence/document-extraction-safety-remediation-20260804/residual-cleanup/production-final-residual.json`

## Implemented controls

1. Migration extraction jobs carry `migration_batch_id`, migration contract, workload class, and synthetic provenance.
2. Explicit extraction policies are limited to `enqueue` and `defer`.
3. Synthetic scale lanes use `defer`: documents are marked `deferred_migration` and no extraction queue job is created.
4. Enqueued migration extraction jobs use priority 500; live CV/email work keeps its existing higher priority.
5. Rollback cancels active extraction jobs by batch tag, app key, or document ID before deleting source records.
6. Rollback cancellation writes durable queue events and preserves cancelled job rows.
7. Residual-zero includes active queue jobs and reports queue status counts.
8. Chunk workers claim only the requested migration batch.
9. Runtime schema DDL is separated from chunk insert transactions.
10. Per-file and per-chunk savepoints recover aborted PostgreSQL transactions.
11. SQLSTATE `40P01` deadlocks receive bounded retry delay; rollback itself has bounded deadlock retries.
12. The production deploy/rollback path now includes `app.py` and refuses a non-zero active migration queue preflight.
13. The production canary no longer changes WATHEFNI auto-admit settings or broadly deletes unrelated migration records.

Poppler, Mistral, GPT rescue, and PDF routing logic were not changed.

## Focused staging proof

Only 20 synthetic text CVs were used. The 1,000 and 10,000 lanes were disabled.

- held applications: 19;
- external IDs preserved: 19;
- tagged extraction jobs: 19;
- migration queue priority: 500;
- deferred extraction queue jobs: 0;
- deferred document state: `deferred_migration`;
- rollback-cancelled extraction jobs: 19;
- rollback active queue residual: 0;
- total synthetic residual: 0;
- injected PostgreSQL transaction-abort path reached failed, dead-letter, replay, and completion successfully.

Evidence:

- `ops/evidence/document-extraction-safety-remediation-20260804/staging/focused-remediation-smoke-final.out`

## Resume conditions

The next Wave 1-B action still requires explicit owner approval. Its mandatory order is:

1. stage and deploy the remediated files, including `app.py`;
2. pass active migration queue residual preflight;
3. run the small core canary first;
4. use deferred extraction for 1,000/10,000 synthetic scale lanes;
5. perform rollback and require queue-inclusive active residual zero;
6. keep all terminal queue evidence retained;
7. stop on any deadlock exhaustion, queue residual, tenant leak, or sibling-freeze regression.

