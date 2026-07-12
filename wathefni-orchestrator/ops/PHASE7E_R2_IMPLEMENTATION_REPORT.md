# Phase 7E-R2 implementation report

**Verdict:** R2A and R2B are implemented and staging-green. The focused R2 checkpoint is **24/24**, and the unchanged complete Phase 7E matrix is **57/57**. C07k and C07l now pass under their original assertions.

This is a staging-readiness result only. No production deployment or production flag change was performed. Phase 7D routing, shared WhatsApp routing, onboarding seed, push, store work, dashboard/bootstrap, and production tenants were not changed.

## R2A — provider-aware storage compensation

- Every employee-app upload commits a `document_storage_operations` row before external storage.
- New local and Drive objects carry an opaque operation trace in the provider name.
- Provider success is persisted before the canonical receipt transaction.
- Onboarding, Document Hub/file/compliance writes and `canonical_committed` status commit in one transaction.
- A failed or uncertain canonical commit rechecks current DB truth before any deletion.
- Local deletion requires the recorded and current company storage roots, item path, and trace to agree.
- Drive deletion requires a provider metadata read proving file ID, company folder, company/item name, and trace before permanent deletion.
- Missing objects are idempotent success. Unknown provider/DB outcomes remain durable and retryable.
- Canonical references, cross-tenant keys, ownership mismatches, and unsupported providers are never blindly deleted.
- Reconciliation uses leases, bounded backoff, eight-attempt terminal review, structured operator events, and a safe company-scoped CLI.
- The staging one-shot worker and five-minute timer are installed and active. A real service-path run completed successfully with zero pending work.

## R2B — rejected-upload audit

Content-validation rejection now writes one `employee_document_upload_rejected` event per request when the audit sink is available. The payload contains only:

- event ID
- company and employee identifiers
- canonical onboarding item
- employee-app route/method context
- rejection code
- normalized declared MIME
- sanitized extension
- attempted byte size
- database timestamp

No bytes, content-derived hash, temporary path, raw filename, provider data, detector output, or full request payload is persisted. Audit failure is best-effort for observability but fail-closed for the upload: the original 4xx remains unchanged and no object or canonical row is created.

## Schema and services

Additive migration:

- `document_storage_operations`
- due-work, company/status, and provider/object indexes

New operational files:

- `document-storage-reconcile-worker.py`
- `ops/document-storage-reconciliation.py`
- staging and production service/timer templates

Only the staging service/timer was installed and enabled. Production templates remain inactive.

## Verification evidence

Focused R2 checkpoint:

- Result: **24/24 pass**
- DB failure plus successful local compensation
- provider failure/unknown outcome plus successful retry
- prepared-state crash recovery
- DB-truth uncertainty preserves the object
- lease concurrency and expiry recovery
- already-missing idempotency
- canonical-reference protection
- cross-tenant deletion refusal
- mocked Drive ownership verification and permanent deletion
- exactly-one rejection audits for extension, MIME, signature, and detector failures
- approved metadata-only audit shape
- no rejected-upload storage/canonical state
- audit-sink failure preserves the original 4xx
- no retryable fixture residue

Complete Phase 7E verifier:

- Original and expanded matrix: **57/57 pass**
- C07k: permanent orphan after DB failure — **pass**
- C07l: metadata-only rejection audit — **pass**
- Production protected flags remained OFF
- Staging protected flags remained OFF
- Production WATHEFNI snapshot unchanged
- Protected staging WATHEFNI snapshot unchanged
- P7ESTG01/P7ESTG02 fixtures removed
- Delivery proof ran with `WATHEFNI_DELIVERY_MODE=dry_run`; no live provider message was sent

Evidence files:

- `ops/staging-phase7e-r2-checkpoint.py`
- `ops/reports/phase7e-e2-verifier-report.json`
- `ops/reports/phase7e-e2-verifier-report.md`

## Rollback

Disable employee-app uploads for the staging fixture/module, disable the staging reconciliation timer, and inspect/drain pending operations before reverting application or worker code. Retain the additive table and any unresolved rows; do not drop reconciliation truth. R2B can be reverted independently without weakening content validation.

## Recommendation

Phase 7E now meets its staging-green exit condition. This does not authorize Phase 8, employee-app production enablement, production deployment, or any protected flag change; those remain separate approval decisions.
