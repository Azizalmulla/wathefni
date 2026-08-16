# Pre-Hiring Durable Email Ingress — Local Remediation

**Status:** LOCAL-GREEN  
**Date:** 2026-07-25  
**Deployment:** None  
**Data scope:** Isolated synthetic test tenants only  
**Production/staging mutation:** None

## Executive result

The Postmark candidate-intake path is now locally remediated to acknowledge a
provider delivery only after the source intake is durable.

The implemented boundary is:

```text
authenticated Postmark webhook
  → bounded body read
  → immutable provider/message identity
  → tenant route resolution
  → inbound message + submission ledger
  → tenant-scoped quarantine objects + attachment manifests
  → Postgres queue/outbox work
  → database commit
  → HTTP 200
```

Candidate creation, application creation, OCR, LLM calls, embeddings,
classification, ranking, `intake_admit`, optional downstream storage, and sender
acknowledgment are no longer part of the webhook request.

If the ledger, quarantine files, or queue cannot become durable, the webhook
raises a non-2xx error. The prior catch-and-ack behavior that returned HTTP 200
after an unhandled intake failure has been removed. A disabled inbound feature
also returns HTTP 503 rather than silently acknowledging and discarding mail.

The existing candidate, application, surrogate-phone, held-intake, Ranking, and
recruiting lifecycle authorities were not redesigned.

## Scope boundaries

Implemented:

- Postmark-only durable candidate-intake receipt;
- additive intake message/submission/document authority;
- immutable tenant route and source provenance;
- local filesystem quarantine contract;
- Postgres leased queue with `FOR UPDATE SKIP LOCKED`;
- retries, jittered backoff, lease reclamation, dead letters, and replay;
- file safety states and fail-closed scanner behavior;
- configurable technical limits and tenant quotas;
- tenant-fair worker claims and per-tenant concurrency;
- internal operations, replay, sweep, worker, and signed-download surfaces;
- asynchronous handoff to the existing held-import authority;
- local synthetic failure/load qualification.

Not implemented:

- Talent Pool UX;
- Role Profiles or Hiring Briefs;
- automatic CV classification;
- identity merging or Person Registry;
- Gmail, Microsoft 365, or IMAP;
- new candidate/application/phone/lifecycle authority;
- a new commercial quota policy;
- a production malware-provider selection;
- deployment or staging/production data migration.

## Durability boundary

HTTP 200 is emitted only after all applicable durable-receipt requirements have
completed:

1. Postmark authentication has passed.
2. The request body has been read under the configured byte ceiling.
3. `MessageID` is present and mapped to a deterministic UUID.
4. `OriginalRecipient`/mailbox hash resolves to one `intake_addresses` row and
   one company.
5. The inbound message and intake submission are persisted.
6. Every attachment accepted under the technical limits has:
   - decoded bytes;
   - SHA-256;
   - an idempotent quarantine key;
   - a fsynced source object;
   - a tenant-scoped document manifest.
7. Deterministically rejected attachments have an explicit manifest and safety
   reason; they are not silently skipped.
8. Tenant quota consumption is recorded.
9. An `intake_validation` queue job exists, either runnable or visibly
   `waiting_quota`.
10. The database transaction commits.

Unknown recipients are durably recorded as rejected and receive no tenant work.
Cross-tenant reuse of one provider `MessageID` fails closed with
`provider_message_route_conflict`.

Oversize request bodies cannot be parsed safely and receive HTTP 413. Invalid
JSON/payloads receive HTTP 400. Authentication failures receive HTTP 401.
Database/storage/durability failures receive HTTP 503 so Postmark may retry.

## Ingress transaction

The transaction is intentionally short and contains no downstream processing:

```text
BEGIN
  insert/select inbound_messages by (provider, provider_message_id)
  lock provider identity
  resolve intake address
  insert intake_submissions with full route snapshot
  for each attachment:
    decode under limits
    calculate SHA-256 and detected MIME
    fsync tenant quarantine object
    insert intake_documents manifest
  atomically increment day/month usage
  insert intake_processing_jobs(intake_validation)
  insert/update tenant queue state
  stamp durable_at and receipt latency
COMMIT
```

Object storage cannot participate in a Postgres transaction. The mitigation is:

- stable UUIDv5 message/submission/document IDs;
- stable object keys;
- full size and SHA-256 verification when an object already exists;
- database rollback on any pre-commit failure;
- provider retry reuses and verifies the same object;
- unreferenced objects are reported and swept only after a configured grace
  period.

The database never points to an object until that object has been written,
renamed atomically, permissioned, and fsynced.

## Additive authority and schema contract

### Existing `inbound_messages` additions

- `submission_id`
- `durable_at`
- `durability_latency_ms`
- `route_snapshot`
- `source_provenance`
- `total_attachment_bytes`
- `processing_error_code`

### `intake_submissions`

One durable candidate-intake submission per inbound message:

- tenant and `intake_id`;
- provider and provider message ID;
- envelope recipient and sender provenance;
- subject/received time;
- immutable route snapshot;
- immutable source provenance;
- attachment counts and source bytes;
- quota state;
- asynchronous status;
- optional later `import_batch_id`.

A database trigger rejects mutation of company, intake route, provider identity,
recipient, sender, route snapshot, or source provenance.

### `intake_documents`

One manifest per attachment ordinal, including duplicates:

- deterministic document ID;
- tenant, submission, and inbound message;
- attachment ordinal;
- original filename;
- claimed MIME and detected MIME;
- decoded byte size and SHA-256;
- quarantine object key;
- storage and safety states;
- duplicate-of document link;
- optional later links to existing application/file/candidate-document records.

A database trigger rejects mutation of source identity, original filename, MIME
claim, ordinal, size, checksum, or object key. Safety and processing state may
advance without rewriting source provenance.

### `intake_processing_jobs`

- `job_id`
- `company_code`
- extensible `job_type`
- `subject_type` and `subject_id`
- priority
- status
- `available_at`
- attempts/max attempts
- lease owner and expiry
- tenant-scoped idempotency key
- bounded payload/result
- redacted error code/detail
- replay count
- created/started/completed/updated timestamps

### Supporting tables

- `intake_processing_job_events`: append-only claim, retry, lease-expiry,
  dead-letter, completion, defer, and replay evidence;
- `intake_tenant_queue_state`: serialized per-tenant claim state and running
  concurrency;
- `intake_quota_usage`: day/month message, attachment, source-byte, and
  processing-job usage.

No foreign key or mutation was added to candidate, application, phone, Ranking,
or lifecycle authority.

## Queue and worker contract

Claims use `SELECT ... FOR UPDATE SKIP LOCKED`. The tenant queue-state row is
locked first, then one eligible tenant job is locked and leased. Claim order is:

1. tenant with the oldest `last_claimed_at`;
2. lowest numeric priority within that tenant;
3. oldest available job.

This prevents a continuously busy tenant from starving another tenant.
`WATHEFNI_INTAKE_TENANT_CONCURRENCY` caps active leases per tenant.
Job-bound intake routes receive priority 50; general intake receives priority
100.

The lease transaction commits before the handler runs. Processing happens
outside the claim transaction. Completion/failure requires the matching lease
owner and a non-expired lease.

Supported job types:

- `intake_validation`
- `file_safety_scan`
- `accepted_intake_preparation`
- `cv_extraction`
- `profile_structuring`
- `embedding`
- `sender_acknowledgment`
- `retention_privacy`

The first four are connected to the current pipeline. Profile structuring and
embedding remain part of the frozen combined CV worker and are reserved as
independent queue types for a future qualified split. Sender acknowledgment is
disabled, and retention/privacy is reserved pending owner policy.

`accepted_intake_preparation` invokes the existing shared import core only after
`clean`. It deliberately passes no sender email as candidate metadata. Shared
agency senders therefore do not collapse several CVs into one candidate.

`cv_extraction` is enqueued only after clean safety processing and performs a
second database check that the linked intake document is still `clean` before
calling the existing CV worker.

## Retry, dead-letter, and replay rules

- Delivery is at least once.
- Queue inserts are tenant-scoped and idempotent.
- Attempts increment when a lease is claimed.
- Transient failures become `retrying`.
- Backoff is exponential, bounded, and includes deterministic per-job jitter.
- Expired leases are reclaimed by later claimers.
- An expired lease at max attempts becomes `dead_letter`.
- Unsupported, corrupt, MIME-mismatched, password-protected, malware, and
  oversize documents complete safety work in a terminal document state; they do
  not create infinite queue loops.
- Scanner unavailability is transient, leaves the document `scan_pending`, and
  retries until dead-letter rather than allowing OCR.
- Error detail is bounded and redacts email addresses, filesystem paths, and
  token-like strings.
- Dead letters retain job/event evidence and require explicit company-scoped
  replay.
- Replay resets attempts, increments `replay_count`, and appends an operator
  event.
- `waiting_quota` and `waiting_budget` are visible, non-terminal states. Deferred
  work does not consume an attempt.

## Quarantine storage contract

Local object keys are:

```text
{COMPANY_CODE}/{INBOUND_UUID}/{ATTACHMENT_ORDINAL}/{SHA256}.bin
```

Properties:

- no untrusted filename is used in the path;
- directory traversal and cross-root resolution fail closed;
- directories are mode `0700`;
- objects are mode `0600`;
- writes use same-directory temporary files, file fsync, atomic rename, and
  directory fsync;
- retry verifies full existing bytes against expected size and SHA-256;
- source files stay outside normal HR file registries until clean validation;
- original filename and MIME claim remain in the manifest;
- detected MIME, size, and checksum are preserved;
- orphan reports compare disk objects with live manifests;
- deletion is disabled by default and requires an explicit internal apply call;
- the grace period defaults to 24 hours;
- quarantine download requires internal authentication, company match, an
  expiry, and an HMAC signature bound to company/document/expiry.

This local remediation uses a filesystem root. Staging must provision it on a
durable encrypted volume or replace the adapter with an owner-approved object
store before receiving real mail.

## Safety states

Implemented source-document states:

- `scan_pending`
- `clean`
- `quarantined`
- `malware_suspicious`
- `unsupported_type`
- `mime_mismatch`
- `password_protected`
- `too_large`
- `invalid_corrupt`

Preflight checks cover:

- extension allowlist;
- claimed MIME versus detected MIME;
- extension versus detected MIME;
- PDF encryption, EOF, and page limit;
- DOCX package validity, encrypted members, member count, expanded bytes, and
  expansion ratio;
- PNG/JPEG dimensions and total pixels;
- decoded per-file and per-message byte ceilings.

Arbitrary ZIP archives are not accepted by this foundation; only valid DOCX ZIP
packages pass. The scanner adapter defaults to `unavailable`, which fails
closed. `test_clean` is test-only and guarded. A ClamAV command adapter exists
but is not a production-provider approval.

## Limits, quotas, and configuration

Conservative technical defaults:

- webhook body: 16 MiB;
- attachment count: 12;
- decoded file: 8 MiB;
- decoded total: 12 MiB;
- PDF pages: 80;
- image pixels: 30,000,000;
- archive members: 200;
- archive expanded bytes: 32 MiB;
- archive expansion ratio: 100;
- lease: 180 seconds;
- attempts: 5;
- retry: 5 seconds base, 900 seconds maximum;
- tenant concurrency: 2;
- orphan grace: 24 hours.

Environment variables:

- `WATHEFNI_INTAKE_QUARANTINE_DIR`
- `WATHEFNI_INTAKE_MAX_WEBHOOK_BYTES`
- `WATHEFNI_INTAKE_MAX_ATTACHMENTS`
- `WATHEFNI_INTAKE_MAX_FILE_BYTES`
- `WATHEFNI_INTAKE_MAX_TOTAL_BYTES`
- `WATHEFNI_INTAKE_MAX_PDF_PAGES`
- `WATHEFNI_INTAKE_MAX_IMAGE_PIXELS`
- `WATHEFNI_INTAKE_MAX_ARCHIVE_MEMBERS`
- `WATHEFNI_INTAKE_MAX_ARCHIVE_EXPANDED_BYTES`
- `WATHEFNI_INTAKE_MAX_ARCHIVE_RATIO`
- `WATHEFNI_INTAKE_ORPHAN_GRACE_SECONDS`
- `WATHEFNI_INTAKE_JOB_LEASE_SECONDS`
- `WATHEFNI_INTAKE_JOB_MAX_ATTEMPTS`
- `WATHEFNI_INTAKE_RETRY_BASE_SECONDS`
- `WATHEFNI_INTAKE_RETRY_MAX_SECONDS`
- `WATHEFNI_INTAKE_TENANT_CONCURRENCY`
- `WATHEFNI_INTAKE_DAILY_MESSAGE_QUOTA`
- `WATHEFNI_INTAKE_MONTHLY_MESSAGE_QUOTA`
- `WATHEFNI_INTAKE_DAILY_SOURCE_BYTES_QUOTA`
- `WATHEFNI_INTAKE_MONTHLY_SOURCE_BYTES_QUOTA`
- `WATHEFNI_INTAKE_DAILY_PROCESSING_JOB_QUOTA`
- `WATHEFNI_INTAKE_MALWARE_SCANNER`
- `WATHEFNI_INTAKE_QUARANTINE_SIGNING_SECRET`

Commercial tenant quotas default to zero (disabled), not invented values.
Qualification explicitly set small synthetic quotas to prove visible waiting.

## Operations and observability

Internal-authenticated surfaces:

- `GET /orchestrator/debug/intake-operations`
- `POST /orchestrator/debug/intake-worker/run`
- `POST /orchestrator/debug/intake-jobs/{job_id}/replay`
- `POST /orchestrator/debug/intake-quarantine/sweep`
- `POST /orchestrator/debug/intake-documents/{document_id}/signed-download`
- `GET /orchestrator/debug/intake-documents/{document_id}/download`

The operations summary exposes:

- messages received and durably acknowledged;
- average/max durable receipt latency;
- queue counts by status;
- oldest queued/retrying/waiting age;
- safety-state counts, including quarantine/unsupported;
- day/month tenant quota consumption;
- current tenant running leases and last claim time;
- referenced and orphan quarantine objects.

The standalone worker supports one pass or a loop, per-job-type worker pools,
and dry-run/apply orphan sweep selection.

## Changed files

- `wathefni-orchestrator/durable_email_ingress.py` — new schema, ingress,
  quarantine, queue, safety, quota, replay, signed access, and operations module.
- `wathefni-orchestrator/durable-email-ingress-worker.py` — new standalone worker
  entrypoint.
- `wathefni-orchestrator/app.py` — schema registration, durable Postmark
  boundary, background handlers, and internal operations routes.
- `wathefni-orchestrator/smoke-test-inbound-email.py` — frozen inbound behavior
  updated from synchronous import to durable receipt plus explicit worker stages.
- `wathefni-orchestrator/local-qualify-durable-email-ingress.py` — isolated
  durability/failure/load qualification and cleanup harness.
- `ops/PREHIRING_DURABLE_EMAIL_INGRESS_LOCAL_REMEDIATION.md` — this report.

`app.py` already contained unrelated uncommitted Kuwait document-journey changes
before this remediation. They were not reverted, committed, or included in this
scope.

## Local qualification matrix

Final clean sequential run: **26/26 passed**.

| Case | Result | Evidence |
|---|---:|---|
| One email / one CV | PASS | durable message, submission, object, manifest, validation job; zero synchronous candidates |
| Several CVs | PASS | three manifests and source objects |
| Duplicate Postmark delivery | PASS | same deterministic message/submission; no second work |
| Duplicate attachment | PASS | separate ordinal manifest with `duplicate_of_document_id`; one existing-CV duplicate later |
| Shared/agency sender | PASS | three distinct checksum surrogates; candidate emails remained null |
| Unknown recipient | PASS | durable rejected ledger; no tenant processing |
| Cross-tenant recipient attempt | PASS | same MessageID across routes failed closed |
| Database failure before durability | PASS | HTTP-503-class exception; transaction absent; retry reused verified object |
| Storage failure before durability | PASS | HTTP-503-class exception; no acknowledged ledger |
| Failure after durable acknowledgment | PASS | job moved to visible retry; message remained durable |
| Worker crash | PASS | expired lease reclaimed by another worker |
| Retry/dead-letter | PASS | bounded attempts, redacted evidence, dead letter |
| Dead-letter replay | PASS | explicit company-scoped reset and replay event |
| Password-protected PDF | PASS | terminal `password_protected`; no accepted preparation |
| Unsupported type | PASS | terminal `unsupported_type` |
| MIME mismatch | PASS | terminal `mime_mismatch` |
| Oversize file | PASS | durable rejected manifest with `too_large` |
| Scanner unavailable | PASS | remained `scan_pending`; queue retried; no OCR |
| Quota exhaustion | PASS | second message durable and `waiting_quota` |
| Tenant fairness | PASS | 6/6 jobs claimed across both tenants without starvation |
| 1,000-message burst | PASS | 1,000 messages, 1,000 submissions, 1,000 jobs |
| Burst synchronous candidate work | PASS | zero candidate creation |
| Burst synchronous OCR work | PASS | zero extraction runs |
| Operator metrics | PASS | message/job/age/safety/quota/lease/orphan metrics returned |
| Tenant-scoped signed access | PASS | valid company accepted; cross-tenant signature rejected |
| Orphan sweep and zero residue | PASS | orphan deleted; all synthetic rows/files removed |

The final clean 1,000-message burst completed in **1.589 seconds** on the local
synthetic environment (about **629 receipts/second**). Messages had no
attachments, so this is a durability-path stress check, not a production
capacity forecast. No OCR/LLM/provider call occurred.

During one earlier attempt, the ingress smoke and load harness were mistakenly
started concurrently against the same isolated database and collided on their
test queue/cleanup locks. Both suites were rerun sequentially; the final evidence
above is from clean sequential runs with zero residue.

## Frozen regression proof

Current-worktree/local database:

- Python compile for all changed backend/test files: PASS.
- `git diff --check`: PASS.
- inbound email smoke: PASS.
- bulk CV import smoke: PASS.
- tiered intake smoke: PASS.
- summary/Reports counts: **6/6**.
- canonical recruiting lifecycle: **78/78**.
- Candidates registry parity: **61/61**.
- Assistant HR reads: **44/44**.
- Assistant pre-hiring parity: PASS.
- tool-call orchestrator smoke: PASS.
- pre-hiring overview unit invariants: PASS.
- dashboard Vitest: **49/49**, 11 files.
- dashboard TypeScript/Vite build: PASS; existing chunk-size warning only.

Frozen local authority snapshots (read-only, no files changed):

- Ranking R0–R3 contract: **30/30**.
- Ranking result presentation: **24/24**.
- Reports V1: **12/12**.
- Pre-Hiring Assistant A0–A3 remediation: **22/22**.
- Assistant Jobs/Ranking UX: **14/14**.

The staging-only HTTP overview remediation script was not run because this phase
forbids deployment and no staging token was used. Its local unit invariants
passed. No production or staging matrix was executed against live data.

## Residual owner decisions

Required before staging:

1. Select and approve the production malware scanner/provider, outage policy,
   timeout, signature-update SLA, and evidence retention.
2. Select the staging/production quarantine backend: encrypted persistent volume
   versus tenant-keyed object storage.
3. Approve final body, attachment, page, image, archive, and worker limits.
4. Approve commercial day/month quotas and reset/escalation behavior.
5. Approve per-tenant concurrency and priority classes.
6. Approve orphan grace and retention/deletion periods.
7. Approve encryption-at-rest, backup, key rotation, and quarantine signing
   secret custody.
8. Approve sender acknowledgment consent/copy/suppression rules.
9. Decide whether profile structuring and embedding should remain in the
   combined CV extraction worker or become separately leased jobs.
10. Decide whether database row-level security is required in addition to the
    implemented application/company scoping.
11. Approve whether legacy `.doc`, arbitrary ZIP, or other formats will ever be
    accepted. This foundation rejects them.
12. Approve Postmark retry/retention settings for 4xx/5xx and maximum provider
    payload size.

## Staging deployment order

No deployment was performed. Recommended guarded order:

1. Resolve the owner decisions above.
2. Freeze the exact source artifact and configuration manifest.
3. Take and verify a staging database backup.
4. Provision a dedicated encrypted persistent quarantine root with service-only
   permissions; verify backup and restore separately from normal HR files.
5. Apply only the additive tables, indexes, columns, functions, and triggers.
6. Verify the current staging artifact still operates before code activation.
7. Deploy code with inbound disabled and all new workers stopped.
8. Configure Postmark secret, signing secret, limits, quotas, scanner, and
   quarantine root.
9. Start an operations-only worker/readiness check.
10. Enable webhook receipt for one isolated staging intake address.
11. Prove durable receipt and duplicate delivery with validation workers stopped.
12. Start only validation and safety-scan workers; prove fail-closed behavior.
13. Start accepted-intake preparation; confirm existing held authority and no
    sender identity assumption.
14. Start CV extraction separately after clean-state proof.
15. Run the full load/failure matrix and frozen staging regressions.
16. Verify zero synthetic rows, files, leases, events, and orphan objects.
17. Stop for owner approval before any production activity.

Rollback should first disable new webhook receipt and stop workers. The additive
ledger and quarantine objects must be retained for reconciliation; do not delete
durable receipts as part of code rollback.

## Final local disposition

The durable Postmark intake foundation is **local-green** for the contained
scope. It is not staging-green or production-green. Real inbound mail must not
be enabled until an owner-approved scanner and durable quarantine backend are
configured and the guarded staging sequence passes.
