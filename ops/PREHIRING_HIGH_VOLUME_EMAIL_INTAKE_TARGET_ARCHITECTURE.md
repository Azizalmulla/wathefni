# Pre-Hiring High-Volume Email Intake — Target Architecture

**Status:** final read-only architecture assessment  
**Date:** 2026-07-25 (Kuwait)  
**Scope:** architecture only — no code, schema, data, configuration, or deployment changes  
**Primary scenario:** a tenant advertises `careers@company.com`, forwards it to Wathefni, receives thousands of mostly unsolicited CVs, rarely creates Jobs, and still needs governed search, organization, advisory ranking, and AI Recruiter answers.

---

## Executive decision

Wathefni should become an **email-first intake and talent intelligence platform**, while keeping the frozen job pipeline separate.

The safe target is:

```text
Postmark ingress
  → durable tenant-scoped intake ledger + quarantined source files
  → asynchronous scan / validation
  → Option B held record (`needs_role`) for accepted candidate material
  → asynchronous text extraction, structuring, embedding, and classification
  → Talent Pool search
  → advisory Role Profile ranking
  → explicit HR admission to a real open Job
  → frozen job Ranking and recruiting lifecycle
```

The principal decisions are:

1. **Postmark is the SMTP and webhook delivery edge, not Wathefni's processing queue.**
2. **The webhook must acknowledge only after the message metadata and source attachments are durable.** It must not perform candidate registration, Drive upload, OCR, classification, or ranking in the request.
3. **Use a Postgres leased queue for the first release.** `FOR UPDATE SKIP LOCKED`, leases, delayed retries, dead-letter state, and per-tenant fairness are sufficient for bursts of thousands. Redis/Celery is not required initially.
4. **Keep source intake, candidate identity, held Talent Pool membership, and job application as distinct authorities.**
5. **Retain Talent Pool Option B for Phase 1:** accepted CVs receive a compatibility candidate surrogate and a held `applications` row in `needs_role` / `import_review`; held rows stay excluded from the frozen Candidates pipeline and job Ranking.
6. **Do not use sender email as a person key.** The current behavior can collapse different CVs sent by the same agency or shared mailbox into one surrogate application.
7. **Introduce a stable, tenant-scoped `subject_id` in Phase 1, but do not call it a Person.** It identifies one intake subject/envelope and gives a future Person Registry something non-destructive to link.
8. **Never auto-merge people.** Exact message and file duplicates may be suppressed automatically; person-equivalence is a separate, reversible HR decision.
9. **Store OCR text as a versioned reusable artifact.** Structuring, taxonomy classification, embedding upgrades, and ranking must not cause re-OCR.
10. **Use a global canonical taxonomy with tenant extensions.** AI suggestions and HR-confirmed classifications remain separate.
11. **Role Profiles remain separate from Job Openings.** Their ranking runs are advisory, immutable, version-grounded, and incapable of lifecycle or outbound side effects.
12. **Retention values and legal basis are tenant/controller decisions.** The product supplies policy, deadline, restriction, legal-hold, deletion, and audit mechanisms without inventing periods.

The current implementation is suitable for controlled pilot volume, not the target scenario. Its Postmark handler performs synchronous attachment decoding, storage, candidate/application creation, and batch completion before returning. It also returns HTTP 200 on an unhandled processing exception, which can turn an uncommitted message into silent loss because Postmark is told not to retry.

---

## Evidence and current-state constraints

This target uses the current production direction documented in:

- `wathefni-orchestrator/app.py`
  - `process_postmark_inbound`
  - `webhook_postmark_inbound`
  - `resolve_intake_address`
  - `_import_process_one_file`
  - `register_imported_cv`
  - `run_candidate_cv_processing_worker`
  - `production_application_predicate`
- `wathefni-orchestrator/cv_extraction.py`
- `wathefni-orchestrator/cv_docx.py`
- `wathefni-orchestrator/recruiting_lifecycle.py`
- `wathefni-orchestrator/docs/CV_OCR_MISTRAL.md`
- `ops/PREHIRING_INTAKE_OCR_AND_TALENT_POOL_AUDIT.md`
- `ops/PREHIRING_TALENT_POOL_AUTHORITY_DESIGN_ASSESSMENT.md`

### Current strengths to preserve

- Postmark inbound has a message ledger with unique `(provider, provider_message_id)`.
- Recipient routing derives `company_code` from `intake_addresses`, not from sender-controlled candidate data.
- Exact CV checksum checks are company-scoped.
- Spam can be quarantined before candidate/application creation.
- Uncertain role intake lands in held statuses and is excluded by `production_application_predicate`.
- CV OCR is local-first, tenant-cached, leased, and instrumented.
- Frozen job Ranking is job-scoped, advisory, versioned, and separate from lifecycle actions.
- The existing `intake_admit` path is the correct bridge from held intake to an open Job.

### Current constraints that cannot carry high volume

1. The FastAPI Postmark route becomes blocking after `await request.json()`.
2. Every attachment is base64-decoded and passed through the shared import core in the webhook transaction.
3. Storage operations can occur while the database transaction and HTTP request remain open.
4. The inbound route has no Wathefni attachment-count or total-byte limit equivalent to the dashboard bulk limits.
5. There is no malware scanner or password-protected-file state.
6. An exception returns HTTP 200 with `ok: false`; there is no durable Wathefni retry or dead-letter queue.
7. `inbound_messages.auth_results` exists but is not populated by this path.
8. CV work is selected by a simple FIFO query without a robust multi-worker claim.
9. The current surrogate uses `(company, sender email)` before CV extraction. A referral agency sending several candidates from one mailbox can collide on one surrogate and one `...-IMPORT` app key.
10. `.doc` and `.rtf` can pass the import extension allowlist even though extraction may not support them.
11. There is no sender receipt/privacy acknowledgment.
12. There is no first-class imported-CV retention, erasure, or legal-hold authority.

---

# 1. High-volume intake gateway

## 1.1 Address model

Use one governed intake-address registry with explicit destination type:

| Address type | Example | Destination authority | Default behavior |
|---|---|---|---|
| Company-wide | `careers@company.com` → tenant inbound alias | Tenant only | Held Talent Pool |
| Department | `technology-careers@company.com` | Tenant + department tag | Held Talent Pool; department is classification/routing evidence, not a Job |
| Job-bound | Job-specific forwarding alias | Tenant + exact open `position_code` snapshot | May create/admit a job application only under an approved tenant policy |

Rules:

- The forwarding alias must map to exactly one tenant.
- `company_code` must come only from the active address record.
- Plus-address text, display names, sender fields, subject text, and attachment content must never choose the tenant.
- Department aliases add an intake tag and ownership queue; they do not invent a Job.
- A job-bound route must resolve to the same tenant and an open, intake-eligible Job at processing time.
- If the Job is missing, paused, closed, or belongs to another tenant, preserve the route evidence but place the item in `needs_role`; never silently bind it.
- Address create, rotate, disable, and delete actions must be audited.
- Disabling an address stops new processing but does not rewrite historical submissions.

## 1.2 Target ingress transaction

The ingress service should do only bounded, durable work:

```text
1. Authenticate Postmark request.
2. Enforce HTTP body and message safety caps.
3. Parse provider message id and envelope recipient.
4. Resolve intake address → tenant and route snapshot.
5. Upsert inbound message idempotency key.
6. Stream/decode each permitted attachment to tenant quarantine storage.
7. Hash bytes and persist attachment manifests.
8. Commit inbound message + submission + documents + queue outbox.
9. Return HTTP 200.
```

It must not:

- create or update a person match;
- call Poppler, Mistral, GPT, Voyage, or a classifier;
- upload to optional downstream storage synchronously;
- create a Role Profile rank;
- call `intake_admit`;
- send a candidate acknowledgment in the request;
- hold a database transaction open while performing expensive processing.

### Durability boundary

HTTP 200 means:

- the message idempotency key is committed;
- accepted source attachments are durable in tenant quarantine storage;
- their checksums and manifests are committed;
- at least one queue/outbox record exists for further processing.

If the database or quarantine storage is unavailable before that boundary, return a retryable non-2xx response so Postmark can redeliver. Do not preserve the current “always 200 on processing exception” behavior.

Object storage and PostgreSQL cannot share one atomic transaction. Use idempotent object keys plus an outbox/saga:

- object key includes tenant, inbound id, attachment ordinal, and SHA-256;
- retries write the same object or verify it;
- the database commit makes the object reachable;
- a sweeper removes old unreferenced quarantine objects after a configured safety window;
- no candidate record is created until the scan/validation stage succeeds.

## 1.3 Postmark, Wathefni, and queue responsibilities

### Postmark owns

- receiving internet email;
- SMTP behavior and sender delivery acceptance;
- parsing inbound email into webhook payloads;
- provider message identity;
- provider-level delivery attempts to the Wathefni endpoint;
- initial spam/authentication signals that it includes in the payload;
- provider availability, documented message limits, and delivery logs.

Postmark does not own:

- Wathefni tenant resolution;
- durable candidate-intake acceptance after Wathefni returns 200;
- malware decisions;
- CV-type classification;
- OCR, extraction, embedding, or ranking;
- identity resolution;
- Talent Pool or application lifecycle;
- Wathefni retention and deletion policy.

### Wathefni ingress owns

- webhook authentication and secret rotation;
- tenant and route resolution;
- Wathefni safety limits;
- message/attachment idempotency;
- durable source capture;
- spam policy beyond provider hints;
- immutable provenance;
- queue creation;
- prompt HTTP acknowledgment after durability.

### Separate processing workers own

- malware and file-safety scanning;
- attachment role detection: CV, cover letter, supporting document, unsupported;
- candidate-intake item creation;
- compatibility held record creation;
- OCR/text extraction;
- structured profile extraction;
- embeddings;
- advisory classification;
- acknowledgments and processing notices;
- retention restriction and deletion;
- on-demand Role Profile ranking.

## 1.4 Queue model

Use a Wathefni-owned Postgres queue in the first release. It fits the existing stack and a burst measured in thousands, provided claims are short and indexed.

Required claim fields:

```text
job_id
company_code
job_type
subject_type / subject_id
priority
status
available_at
attempt_count / max_attempts
lease_owner / lease_expires_at
idempotency_key
last_error_code
last_error_redacted
created_at / started_at / completed_at
```

Claim with `FOR UPDATE SKIP LOCKED`, commit the lease immediately, and process outside the claim transaction.

Use separate job types and worker pools:

1. `intake_validate` — route, manifest, attachment role.
2. `file_scan` — malware, content-type, encryption/password, decompression safety.
3. `held_record_create` — idempotent Option B compatibility record.
4. `cv_extract_text` — Poppler/DOCX/Mistral/GPT.
5. `cv_structure` — deterministic and LLM profile extraction.
6. `cv_embed` — Voyage.
7. `cv_classify` — taxonomy suggestions.
8. `sender_ack` — rate-limited transactional acknowledgment.
9. `retention_enforce` / `privacy_delete` — restriction and deletion.
10. `role_profile_rank` — explicit advisory run, isolated from ingestion.

These may share one physical queue table initially, but they require separate worker concurrency and quotas. OCR must never block file scanning; sender email must never block OCR; ranking must never starve intake.

Do not couple this queue to the separate `ai-recruiter` service's current queue. Its `FOR UPDATE SKIP LOCKED` pattern is a useful reference, but intake durability belongs with the orchestrator's intake authority.

## 1.5 Delivery semantics, retries, and dead letters

The system is **at-least-once**, not exactly-once. Every stage must be idempotent.

Idempotency layers:

- message: `(provider, provider_message_id)`;
- attachment: `(inbound_id, provider_attachment_ordinal)` plus content SHA;
- source object: tenant + inbound + ordinal + SHA;
- intake item: `(submission_id, primary_document_id)`;
- held compatibility application: one idempotency key per intake subject;
- extraction: content SHA + preprocessing version + provider/model/options;
- structure: extracted-text version + schema/prompt/model version;
- embedding: normalized-text hash + embedding model/version;
- classification: source artifact + taxonomy version + classifier version;
- acknowledgment: submission + acknowledgment template/version;
- ranking: profile version + pool snapshot/query hash + scoring version.

Retry rules:

- retry network timeouts, provider 429/5xx, expired leases, and temporary storage/database errors;
- honor provider `Retry-After` where available;
- use bounded exponential backoff with jitter;
- do not retry unsupported formats, password-protected files, safety violations, or deterministic parser rejection until inputs/configuration change;
- `waiting_quota` and `waiting_budget` are non-terminal states, not extraction failures;
- after configured attempts, move to `dead_letter` with a redacted error and alert;
- replay creates a new attempt record but preserves the original source and failure history.

## 1.6 Attachment and security policy

Exact numeric limits require owner approval. The architecture must support:

- maximum webhook body bytes;
- maximum attachments per message;
- maximum bytes per attachment and total;
- maximum PDF pages;
- maximum image dimensions/pixels;
- maximum DOCX/ZIP expanded bytes, member count, nesting, and expansion ratio;
- accepted MIME signatures, not filename extension alone;
- tenant daily/monthly messages, source bytes, OCR pages, and AI cost;
- hard platform safety caps that tenants cannot override.

Processing outcomes are explicit:

| Outcome | Behavior |
|---|---|
| Clean supported CV | Continue asynchronously |
| Clean cover letter/support file | Preserve and link to the intake item; do not OCR as CV unless needed |
| Unsupported type | Preserve minimal manifest under policy; mark unsupported; do not create a candidate solely from it |
| Extension/MIME mismatch | Quarantine for review |
| Password-protected/encrypted | Mark `password_protected`; do not repeatedly OCR |
| Malware/suspicious archive | Quarantine; no candidate, OCR, embedding, or acknowledgment attachment detail |
| Oversize/hard-cap breach | Reject processing safely and record reason |
| Scanner unavailable | Fail closed into `scan_pending` / `quarantined`; never send to OCR |

Postmark spam headers are one signal. Wathefni still owns:

- tenant spam threshold;
- rate and reputation controls;
- malware scanning;
- MIME/content validation;
- quarantine review;
- suppression of acknowledgment backscatter.

## 1.7 Multiple attachments

One email is one `intake_submission`. It may contain many `intake_documents`.

After scanning:

- create one `intake_item` per candidate-like primary CV;
- associate clearly related cover letters/support files to that item;
- if an email contains two CVs, create two intake items and two provisional intake subjects;
- if association is uncertain, leave the supporting file unassigned for HR review;
- never assume all CVs from one sender describe one person;
- never assume different files describe different people for identity purposes;
- preserve every original document and source relationship.

This resolves the agency/shared-mailbox collision in the current sender-email surrogate model.

## 1.8 Sender acknowledgment

Acknowledgment is a separate, tenant-configured, rate-limited queue.

Send only after:

- tenant route is known;
- the message is not spam/malware;
- at least the durable receipt is complete;
- duplicate acknowledgment idempotency passes.

The receipt should:

- confirm receipt, not job acceptance;
- state whether files could be processed at a high level;
- identify the tenant/controller;
- link the approved privacy notice;
- explain that classification/ranking is advisory and HR-controlled where required;
- provide the approved privacy/deletion contact;
- carry the exact notice/template version and sent timestamp.

Do not send an acknowledgment for unknown recipients, clear spam, or abusive sources. Do not expose internal quarantine, model, ranking, or security details.

## 1.9 Observability and quotas

Operational views and alerts must include:

- ingress acknowledgment latency and error rate;
- source-storage success and orphan count;
- queue depth/oldest age by stage, tenant, and priority;
- lease expiry and retry counts;
- quarantine, unsupported, password-protected, and dead-letter counts;
- OCR pages, cache-hit rate, provider calls, rescue rate, latency, and estimated/actual cost;
- structuring, embedding, and classification completion/missing rates;
- acknowledgment sends, suppressions, bounces, and complaints;
- retention deadlines, restricted records, deletion backlog, and legal holds;
- per-tenant quota consumption and throttling.

Fairness controls:

- global concurrency per external provider;
- per-tenant concurrency;
- weighted round-robin or capped consecutive claims per tenant;
- per-tenant token buckets for OCR/LLM/Voyage;
- high/normal/backfill priority classes;
- circuit breakers for a degraded provider;
- no silent drop when a quota is reached.

## 1.10 Strict tenant isolation

- Every intake, subject, document, job, classification, profile, and ranking row carries `company_code`.
- Uniqueness and lookup indexes include `company_code` unless the identifier is only an opaque global UUID.
- Workers claim tenant-scoped jobs and include tenant predicates on every join/update.
- Object keys, encryption context, and signed downloads are tenant-scoped.
- OCR caches remain company-scoped even for identical hashes.
- Identity suggestions, semantic search, classification counts, and ranking pools never cross tenants.
- No UI-visible global checksum dedupe may disclose another tenant's document.
- Database row-level security or equivalent connection-scoped enforcement should be added as defense in depth; application predicates remain mandatory.
- Support/admin cross-tenant access must be explicit, audited, least-privileged, and absent from normal HR tools.

---

# 2. Intake record vs candidate vs application

## 2.1 Authority model

| Authority | Meaning | May mutate another authority? |
|---|---|---|
| `inbound_message` | Provider delivery event and idempotency receipt | No person/job decision |
| `intake_submission` | Tenant-routed submission, source, basis, notice, retention | May create items only |
| `intake_document` | Immutable source file/version, storage, hash, security state | May produce derived artifacts |
| `intake_item` | One candidate-like unit within a submission | May create one compatibility held record idempotently |
| `intake_subject` | Stable tenant-scoped technical subject for one accepted item | Not proof of a unique Person |
| `candidate` (Phase 1) | Existing compatibility identity keyed by real/surrogate phone | Must not become cross-channel Person authority |
| held Talent Pool record | Existing `applications` row in held status | Not a job application in product semantics |
| job application | Explicit person/candidate-to-open-Job work item after admission | Owns frozen recruiting lifecycle |

### Critical terminology

Under Option B, a held row physically exists in `applications`, but it is a **compatibility held-intake record**, not evidence that the person applied to a Job. UI, reports, Assistant, and ranking must maintain this distinction.

## 2.2 Creation timeline

### Immediately at email receipt

Create only:

- `inbound_message`;
- `intake_submission`;
- attachment manifests / `intake_documents`;
- quarantine storage objects;
- queue/outbox jobs;
- immutable route and sender provenance;
- policy/retention snapshot identifiers.

Do not immediately create:

- a Person;
- an identity merge/link;
- a job application;
- a classification;
- a Role Profile rank;
- a lifecycle event.

### After scan and file acceptance

For each candidate-like intake item:

1. create `intake_item`;
2. create an opaque tenant-scoped `intake_subject.subject_id`;
3. create a new UUID-derived compatibility surrogate candidate, not an email-derived one;
4. create the idempotent Option B held row (`needs_role`, or `import_review` only when a real role suggestion exists);
5. link document, item, subject, surrogate candidate, and held app in sidecar mappings;
6. queue extraction.

Unsupported, malicious, or password-protected files do not create a candidate/held app unless HR explicitly resolves them.

### When a job application may exist

A semantic job application is allowed only when:

- HR explicitly admits a held person/item to a selected open Job; or
- a valid job-bound alias and approved tenant auto-admit policy provide an exact, current Job binding.

Even in the second case:

- the Job must be open and tenant-matched at processing time;
- the action is auditable;
- uncertainty falls back to held intake;
- no Role Profile or classifier may auto-admit.

Company-wide and department aliases never create a job-bound application automatically.

## 2.3 Compatibility with current `needs_role`

Keep unchanged:

- `HELD_IMPORT_STATUSES = needs_role | import_review | import_archived`;
- exclusion from `production_application_predicate`;
- exclusion from job Ranking, pipeline counts, offers, interviews, and reports;
- HR `intake_admit` as the transition bridge;
- existing `app_key`, `phone`, document, and lifecycle references.

Add sidecar links instead of rewriting historical keys:

```text
intake_subject_application_links
  company_code
  subject_id
  app_key
  link_kind = held_compatibility | admitted_job_application
  created_at
```

Existing held rows can receive links lazily. Missing `subject_id` must not make them disappear from Talent Pool Phase 1; the UI can use `app_key` as a legacy fallback while a controlled backfill is pending.

## 2.4 Avoiding frozen-module changes

Phase 1 must not:

- change the `candidates.phone` primary key;
- rewrite `app_key`;
- make candidate-without-application a core Candidates assumption;
- include held records in frozen job Ranking;
- reuse job `ranking_runs` for Role Profiles;
- convert held statuses into canonical lifecycle stages;
- bind held items to fake/draft Jobs;
- let Assistant call lifecycle tools from advisory results.

The first release is additive around the frozen core:

```text
new intake/subject/classification/profile sidecars
  → held app compatibility boundary
  → existing explicit intake_admit
  → unchanged job pipeline
```

## 2.5 Future Person Registry without intake-history rewrite

The immutable source chain remains:

```text
inbound_message
  → intake_submission
  → intake_item
  → intake_subject
  → documents and derived artifacts
```

Phase 2 adds:

```text
persons
person_subject_links
person_identifiers
person_application_links
```

A Person links to one or more historical `subject_id` values. No inbound message, document, held app, phone key, or app key is rewritten. Existing applications may gain a mapping to `person_id`; their historical identity key remains as a compatibility alias.

---

# 3. Identity resolution

## 3.1 Identity layers compared

| Model | Strength | Risk | Decision |
|---|---|---|---|
| Current surrogate phone | Protects current phone/application schemas; tenant prefix | Sender-email collisions, weak cross-channel identity, no split/link authority | Preserve only as compatibility key |
| Additive identity-link layer | Reversible evidence and HR decisions without key rewrites | Requires careful UI and transitive-link handling | Build in Phase 1 |
| First-class Person Registry | Correct long-term person independent of application | Reopens broad frozen assumptions if introduced now | Defer to Phase 2 |

## 3.2 Evidence model

Evidence must be tenant-scoped, source-specific, versioned, and explainable.

### Deterministic event/document evidence

- same provider message id: same inbound event;
- same attachment ordinal on a retried message: same source attachment;
- same tenant + exact content SHA: same document bytes;
- same authenticated WhatsApp conversation/account continuity: same channel identity;
- same tenant-approved external agency/referral identifier: same external reference.

These facts can suppress duplicate work. They do not prove two different submissions are the same natural person.

### Strong identity suggestions

- exact normalized phone extracted from CV and observed on an established tenant channel;
- exact normalized email found inside the CV, especially when repeated across CV versions;
- exact confirmed identifier already attached by HR;
- same agency candidate reference where the agency namespace is known.

### Semantic/weak suggestions

- similar name/transliteration;
- overlapping employment and education timeline;
- similar skills/summary;
- high CV-text or profile embedding similarity;
- changed CV with strong content continuity;
- sender address matching CV address.

Weak/semantic evidence never links automatically. Name alone is insufficient.

## 3.3 Channel-specific treatment

| Scenario | Safe behavior |
|---|---|
| Repeated identical email/CV | Deduplicate event/document; preserve the later receipt event if provider id differs |
| Same email, changed CV | New source document/version and new item subject unless HR confirms identity |
| Different email addresses | Suggest a match only from extracted identifiers/semantic evidence |
| Email later appears on WhatsApp | Suggest email subject ↔ WhatsApp candidate; HR confirms |
| Manual HR upload | Record uploader/source; email/phone metadata are observations, not automatic merges |
| Referral/agency | Sender belongs to agency, not candidate; require candidate identifiers or agency reference |
| Multiple CVs from one sender | Separate intake items/subjects |
| Candidate changes name/contact | Preserve old identifiers with validity/provenance; add suggestions |

## 3.4 Phase 1 identity tables

Do **not** introduce `persons` in Phase 1 merely to hold one row per surrogate; that would be an ungoverned Person Registry in disguise.

Introduce:

1. `intake_subjects`
   - `subject_id`, `company_code`, originating `intake_item_id`, status, timestamps.
   - One accepted intake item initially creates one subject.
   - Explicitly documented as technical, not unique-person authority.

2. `identity_match_suggestions`
   - tenant-scoped subject/candidate/application pair;
   - score band, status, algorithm/version, created/expired timestamps;
   - `suggested | confirmed | rejected | superseded`.

3. `identity_match_evidence`
   - suggestion id, signal type, normalized hash/value policy, source reference, confidence, model/version;
   - sensitive raw values shown only under permission; do not leak in logs.

4. `identity_link_decisions`
   - actor, timestamp, preview snapshot, decision, reason, supersedes decision id;
   - append-only.

5. `identity_subject_links`
   - active reversible edge between two tenant subjects or a subject and current candidate key;
   - derived from confirmed decisions only;
   - no cross-tenant rows.

6. `intake_subject_application_links` and `intake_subject_document_links`
   - preserve existing `app_key`, candidate phone, `document_id`, and `file_id`.

## 3.5 No automatic merge

The system may automatically state:

- “same Postmark event”;
- “exact duplicate document”;
- “OCR cache hit”;
- “possible same person.”

It may not automatically:

- update a candidate primary key;
- move documents between candidates;
- collapse held applications;
- select a canonical email/phone;
- connect email intake to WhatsApp identity;
- combine records across tenants.

HR confirmation preview must show:

- both identities/subjects;
- every source channel;
- all current applications;
- exact and semantic evidence separately;
- which fields/documents/search results will be grouped;
- any transitive links that would be affected;
- the reversible nature of the operation.

## 3.6 Split/unlink

An incorrect confirmation is corrected by a new append-only decision:

1. mark the active identity edge revoked/superseded;
2. preserve the original decision and actor;
3. recompute grouped search projections;
4. invalidate classification/ranking projections that depended on the grouping;
5. leave all source submissions, documents, candidates, and applications in their original ownership;
6. never “restore” by guessing previous values.

If a future Person has been created, unlinking may split subjects into a new Person only after previewing affected applications, identifiers, retention, and legal holds.

## 3.7 Cross-tenant protection

- Identity candidate generation is `company_code` bounded.
- Pair rows require both sides to have the same tenant.
- Semantic nearest-neighbor queries always include tenant filters before returning candidates.
- HR cannot query another tenant's exact email/phone match.
- A support-only global abuse signal, if ever added, must not expose candidate existence or create a person link.

## 3.8 Safest migration path

1. Stop using sender email to mint shared deterministic surrogates for new high-volume email items; use opaque per-subject compatibility keys.
2. Add stable intake subjects and sidecar links.
3. Generate match suggestions after extraction.
4. Add HR confirm/reject/unlink with append-only audit.
5. Use confirmed links only to group Talent Pool display/search; keep underlying rows unchanged.
6. Later add Person Registry and map confirmed subjects into persons.
7. Keep legacy phone/app keys indefinitely as source-system aliases.

---

# 4. CV extraction and processing

## 4.1 Existing stack at high volume

The existing stages are appropriate if scheduled independently:

```text
PDF/DOCX/image
  → local preflight and Poppler/DOCX extraction
  → Mistral OCR only for pages needing OCR
  → GPT vision rescue only after quality failure
  → deterministic + LLM structured profile
  → Voyage embedding
```

Current verified components:

- Poppler: `pdftotext`, `pdfinfo`, `pdfimages`, `pdftoppm`;
- DOCX local XML extraction and selective embedded-image OCR;
- Mistral `mistral-ocr-4-0`;
- GPT vision rescue through the planner/tool-agent model;
- structured profile extraction with confidence/provenance;
- Voyage semantic embeddings;
- `cv_extraction_cache`, `cv_extraction_leases`, and `cv_extraction_runs`.

These components should be retained. The worker orchestration around them must change for volume.

## 4.2 Priority policy

Use explicit priority classes:

1. security scan and durable intake validation;
2. active open-Job submissions awaiting review;
3. HR-requested interactive reprocess;
4. new company-wide/department Talent Pool intake;
5. classification/embedding repair;
6. historical backfill.

Use per-tenant fairness inside each class. A large tenant's backfill cannot starve another tenant's new intake. A job-bound item may be faster, but it does not receive a different identity or evidence standard.

## 4.3 Stage-specific state

Do not flatten the pipeline to one `extraction_status`.

Recommended facets:

```text
security: received | scan_pending | clean | quarantined | malware | scan_failed
format: supported | unsupported | password_protected | invalid | too_large
text: pending | processing | complete | partial | failed
structure: pending | complete | partial | failed
embedding: pending | complete | missing | failed
classification: pending | complete | unclassified | failed | stale
overall availability: processing | searchable_partial | searchable | restricted | deleted
```

Partial text/profile remains visible with disclosure. Missing embedding disables semantic search/ranking but not metadata search. A classifier failure does not erase OCR success.

## 4.4 Retry policy

| Failure | Retry |
|---|---|
| Poppler/DOCX deterministic unsupported/password error | No, until file/config changes |
| Local tool transient process failure | Bounded retry; then manual/dead letter |
| Mistral/GPT/Voyage timeout, 429, 5xx | Backoff + jitter; honor provider guidance |
| Provider invalid request / unsupported media | No automatic retry |
| Quality below threshold | Advance to the configured rescue tier once |
| Budget/quota exceeded | Wait in explicit state |
| Lease expires | Reclaim idempotently |
| Structuring schema failure | Retry with same recorded version, then partial/fail |
| Embedding failure | Retry independently; never re-OCR |

## 4.5 Artifact and provenance model

Keep immutable, versioned artifacts:

1. source document bytes;
2. per-page local/OCR text;
3. assembled normalized text;
4. structured profile;
5. embedding;
6. classification suggestions;
7. HR-confirmed classification;
8. ranking-run input snapshot.

Each derived artifact records:

- tenant and source document/version;
- input content hash;
- preprocessing version;
- stage and tier;
- provider;
- requested and returned model identifiers;
- API/prompt/schema/algorithm version;
- page indexes;
- provider request id;
- quality/confidence;
- cache hit;
- latency, billable units, and cost;
- error code and redacted detail;
- creation time and active/superseded relation.

## 4.6 Cache reuse and avoiding repeated OCR

Use separate cache keys:

| Artifact | Cache key |
|---|---|
| Text extraction | tenant + source SHA + page hashes + preprocessing + OCR provider/model/options |
| Structured profile | extracted-text artifact + schema/prompt/model |
| Embedding | normalized-text hash + embedding model + projection version |
| Classification | structured/text artifact + taxonomy version + classifier/prompt/model |
| Role ranking | profile version + candidate artifact versions + filters + scoring/retrieval versions |

Consequences:

- taxonomy edits rerun classification only;
- Role Profile edits rerun ranking only;
- Voyage model changes rerun embedding only;
- structured schema changes rerun structuring from stored text;
- OCR reruns only when source bytes, preprocessing, OCR model/options, or an explicit authorized force request changes.

## 4.7 Cost and concurrency

- Local extraction always precedes paid OCR.
- OCR only pages classified as needing it.
- GPT rescue is limited to quality-failed pages/items.
- Global and tenant provider semaphores prevent bursts.
- Monthly/daily tenant budgets gate paid stages.
- Estimated cost is checked before dispatch and actual usage is recorded after.
- Backfill has a separate budget and can be paused.
- Circuit breakers stop repeated provider failure.
- Cache hits consume no provider quota.
- HR reprocess preview states which stages and estimated paid work will run.

---

# 5. Advisory CV classification

## 5.1 Recommended taxonomy model

Use a **global canonical base with tenant extensions**.

Reject:

- global-only taxonomy: too rigid for tenant roles and GCC terminology;
- tenant-only taxonomy: fragments search, bilingual labels, analytics, migration, and model training;
- silently mapping tenant labels into global labels: loses tenant meaning.

The model is:

```text
global taxonomy version
  → stable canonical nodes and relationships
  → Arabic and English labels/aliases
  → tenant extension namespace
      → custom nodes
      → optional parent/mapping to global node
```

Global nodes have stable IDs across label changes. A taxonomy release is immutable; a later release supersedes it. Tenant extensions are versioned independently and cannot modify another tenant or the global definition.

## 5.2 Dimensions

Controlled multi-label dimensions may include:

- broad career function;
- likely roles;
- seniority;
- experience band;
- skills;
- industries;
- education fields/levels;
- certifications;
- languages;
- location/availability where actually evidenced.

Not every dimension needs forced taxonomy selection. Factual extracted values such as institution, employer, and exact location can remain structured facts and optionally map to taxonomy nodes.

No candidate is forced into one category. An item can have:

- several role families;
- several skills/industries;
- no seniority label;
- an explicit `unclassified` result because evidence is insufficient.

## 5.3 Suggested and confirmed authority

Keep separate stores:

### AI suggestion

- classification run id;
- taxonomy/global and tenant-extension versions;
- node id;
- confidence;
- evidence references/quotes/pages;
- classifier model/prompt/version;
- source text/profile artifact version;
- active/stale state.

### HR-confirmed assignment

- subject/person scope;
- node id and taxonomy version;
- actor and timestamp;
- optional reason;
- confirmation/supersession history.

Reclassification:

- creates a new suggestion run;
- does not overwrite HR-confirmed values;
- marks old suggestions stale;
- can flag a confirmed node as deprecated/mapped but does not silently change it.

## 5.4 Confidence and evidence

- Thresholds are dimension-specific and versioned.
- Below threshold, emit no label or “needs review”; do not pick the nearest category.
- Confidence is not displayed as false precision where calibration is weak; use bands if appropriate.
- Every suggested label includes supporting CV evidence and source artifact.
- Evidence may be multilingual; labels display in the HR user's chosen Arabic/English locale.
- Evidence and extracted text are derived personal data and follow the same restriction/deletion policy as the CV.

## 5.5 Filters and counts

Every filter/count discloses its authority:

- `HR confirmed`;
- `AI suggested`;
- `confirmed or AI suggested`;
- confidence threshold and taxonomy version where relevant.

UI must not combine them into one unlabeled number. Recommended default:

- show confirmed and AI-suggested facets separately;
- let HR explicitly include high-confidence AI suggestions;
- preserve the chosen source mode in saved searches and ranking-run snapshots.

## 5.6 Suggested tables

```text
taxonomy_versions
taxonomy_nodes
taxonomy_node_labels
taxonomy_relationships
tenant_taxonomy_versions
tenant_taxonomy_nodes
tenant_taxonomy_mappings

classification_runs
classification_suggestions
classification_evidence
classification_confirmations
```

All classification rows are tenant-scoped through their subject and run. Global taxonomy administration is a separate privileged control plane.

---

# 6. Role Profiles and advisory pool ranking

## 6.1 Authority

Use the approved separate Role Profile direction:

```text
role_profiles
  → role_profile_versions
      → role_profile_criteria
      → approval record

role_profile_ranking_runs
  → role_profile_ranking_items
```

A Role Profile:

- is not a Job Opening;
- does not publish or accept applications;
- has immutable approved versions;
- may have drafts without affecting approved versions;
- has separate management permission;
- can later be copied into a draft Job through an explicit conversion.

## 6.2 Eligible pool

Default pool:

- same tenant;
- held Option B rows in `needs_role` / `import_review`;
- not archived unless owner explicitly enables archived inclusion;
- not restricted, expired, deleted, malware-quarantined, or unresolved duplicate-only;
- enough current extraction evidence for the requested criteria.

Classification filters run before expensive ranking:

1. apply tenant/status/retention constraints;
2. apply explicit HR-confirmed/AI-suggested taxonomy filters with source mode;
3. apply deterministic criteria;
4. retrieve semantic candidates;
5. compute advisory score/evidence on the bounded eligible set.

The run records the pre-filter count, eligible count, retrieval count, scored count, and omissions. It must not imply that unprocessed/missing-embedding candidates were assessed.

## 6.3 Efficient large-pool ranking

For large pools:

- index held status, tenant, subject, classifications, experience facts, and artifact freshness;
- build a Role Profile query embedding from the approved version;
- use tenant-filtered pgvector/ANN retrieval for semantic criteria;
- combine full-pool SQL filters with bounded semantic top-K retrieval;
- run expensive LLM narratives only for the top configured results, never to determine lifecycle;
- cache by immutable run request hash;
- process runs asynchronously and expose progress.

If ANN retrieval is used, the UI/audit must disclose retrieval method and candidate counts. Do not label a top-K retrieval as an exhaustive comparison unless exhaustive scoring was actually performed.

## 6.4 Reproducibility

Every ranking run snapshots:

- `company_code`;
- Role Profile id and exact approved version;
- criteria and weights;
- filter expression and classification authority mode;
- taxonomy versions;
- pool query hash and eligibility statuses;
- each subject/app key;
- CV document and extracted-text versions;
- structured profile, embedding model, and classification versions;
- scoring algorithm and semantic retrieval version;
- narrative model/prompt where used;
- start/completion time, actor, and request hash.

Run items store component scores, evidence, gaps, missing evidence, and exclusion reasons.

Approved Profile edits create a new version. They do not mutate an old run.

## 6.5 Staleness

A run becomes stale when:

- a new Profile version is approved;
- a candidate's active CV/text/profile/embedding/classification changes;
- an identity unlink changes the grouped subject;
- retention restriction removes a candidate;
- scoring or retrieval version changes.

Old runs remain immutable and auditable, but are not presented as current. Rerun creates a new run. Staleness never changes a candidate lifecycle.

## 6.6 No side effects

Role Profile ranking is forbidden from:

- creating an application;
- changing `position_code`, status, or current step;
- calling `intake_admit`;
- shortlisting, rejecting, interviewing, offering, or hiring;
- sending email or WhatsApp;
- writing job `ranking_runs.is_current`;
- changing HR-confirmed classification;
- auto-converting a Profile to a Job.

The rank action itself is read/derive-only and does not require destructive confirmation. Subsequent admit/contact/convert actions require separate preview and confirmation.

## 6.7 AI Recruiter grounding

AI Recruiter must cite:

- Role Profile title;
- profile id;
- exact approved version;
- ranking run id/time;
- whether results are current or stale;
- classification filter source where material.

If no approved Role Profile/version is selected, return:

> No valid ranking context. Select an approved Role Profile or an open Job.

It must not:

- auto-select a draft Job;
- invent criteria from a question;
- use an unapproved draft by default;
- mix job Ranking and Role Profile ranking;
- claim a hiring decision;
- hide missing CV/embedding/classification evidence.

## 6.8 Conversion and admission

### Role Profile → Job

1. Preview exact Profile version and copied fields/criteria.
2. Create a new draft Job.
3. Copy, do not move, criteria into job-owned criteria authority.
4. Require the approved Jobs publish/open permission and confirmation.
5. Keep the Role Profile and historical ranking runs unchanged.

### Held person → Job

1. Select a real open Job.
2. Preview duplicate/same-role applications and identity grouping.
3. Use existing `intake_admit` per held row/subject.
4. Re-run frozen job Ranking separately after admission.
5. Never carry the Role Profile advisory score into job Ranking as an authoritative score.

---

# 7. Talent Pool first release vs future Person Registry

## 7.1 Phase 1 — Option B

Authority:

- source: inbound/submission/document/item records;
- technical subject: `intake_subject`;
- compatibility identity: current `candidates` surrogate;
- Talent Pool membership: held `applications` row;
- job lifecycle: absent until `intake_admit`.

Features:

- high-volume durable email intake;
- Talent Pool UX over held rows;
- full-text/structured/semantic search;
- advisory multi-label classification;
- duplicate/identity suggestions;
- separate Role Profiles;
- advisory pool ranking;
- explicit admit to Job.

Phase 1 must not claim that a surrogate candidate is a unique real person.

## 7.2 Phase 2 — Person Registry

Authority:

- `person_id` exists independently of applications;
- a Person may have many emails, phones, submissions, documents, and applications;
- identifiers have provenance, verification, validity, and retention;
- links are HR-confirmed/reversible;
- applications point to Person through additive mappings;
- historical intake subjects remain the immutable source boundary.

## 7.3 Required Phase 1 identifiers/tables

Minimum non-destructive foundation:

| Identifier/table | Why Phase 2 needs it |
|---|---|
| Stable `inbound_id` | Preserve provider event |
| Stable `submission_id` | Channel-neutral source unit |
| Stable `document_id` + content SHA | Preserve source/version and cache |
| Stable `intake_item_id` | Distinguish multiple CVs in one email |
| Stable tenant-scoped `subject_id` | Map future Person without rewriting source/app |
| Subject↔document link | Preserve all source documents |
| Subject↔held app link | Keep Option B compatibility |
| Identity suggestion/evidence/decision ids | Migrate only governed decisions |
| Versioned extraction/profile/embedding ids | Reproduce search/ranking |
| Retention policy/deadline/hold ids | Person migration cannot erase obligations |
| Taxonomy/classification run ids | Preserve suggested vs confirmed authority |
| Role Profile/version/run ids | Preserve advisory context |

Existing `import_batches` / `import_items` can be evolved or mapped into the channel-neutral submission/item model. Do not run two competing source authorities. If new tables are introduced, record a 1:1 legacy mapping and make one side canonical.

## 7.4 Phase 2 migration

1. Create tenant-scoped `persons`.
2. Create `person_subject_links` from confirmed Phase 1 identity decisions.
3. Add verified person identifiers with source provenance.
4. Link historical held/live applications by mapping table; do not rewrite app keys.
5. Read Person-first in new Talent Pool APIs while frozen modules continue reading current candidate/application keys.
6. Migrate features one module at a time behind flags.
7. Keep unconfirmed subjects separate.
8. Support unlink/split before making Person Registry authoritative.

---

# 8. Consent, retention, and deletion

## 8.1 Source and basis

For each submission record:

- source channel and forwarding address;
- sender address and whether it is candidate, employee, agency, or unknown when known;
- tenant/controller;
- purpose at collection;
- tenant-configured legal/processing basis code;
- privacy notice id, version/hash, and effective language;
- acknowledgment outcome;
- policy version;
- received date;
- retention trigger and calculated deadline.

Do not label unsolicited email as “consent” unless the tenant's approved policy and facts establish consent. The product records the tenant-approved basis; it does not choose legal basis automatically.

## 8.2 Retention policy

Provide tenant-configured policy rules by data class/source, without defaulting to invented legal periods:

```text
policy_id / version
company_code
scope (unsolicited CV, job application, referral, agency, etc.)
trigger
duration or externally approved rule reference
archive behavior
notice version
legal-hold behavior
effective dates
approver
```

Deadlines are materialized per submission/subject so later policy edits do not silently rewrite history. A governed recalculation action may update deadlines with audit.

## 8.3 Archive vs restriction vs deletion

- **Archive** is an HR organization state. It does not satisfy deletion by itself.
- **Restriction** removes records from normal search, AI Recruiter, classification reruns, and ranking while disposition is pending.
- **Deletion** removes source files and derived personal data when approved and not held.
- **Legal hold** prevents purge but does not automatically authorize continued recruiting use.

At retention expiry:

1. mark the subject processing-restricted;
2. remove it from search, filters, counts, ranking, and Assistant;
3. evaluate legal hold/policy;
4. delete or retain in restricted hold storage;
5. record completion/failure.

## 8.4 Candidate deletion request

Workflow:

1. intake privacy request through the separate privacy authority;
2. verify requester identity proportionately;
3. find tenant-scoped subjects/person, documents, applications, and derived data;
4. show legal hold and required-retention conflicts;
5. preview deletion scope;
6. authorized HR/privacy user confirms;
7. immediately restrict ordinary processing;
8. enqueue idempotent deletion;
9. reconcile all stores;
10. record completion and communicate through the approved channel.

Delete/reconcile:

- quarantine and primary stored files;
- `file_registry`/document content pointers as policy allows;
- local extracted text;
- OCR cache/result content;
- structured profile;
- embeddings and semantic index;
- AI classification suggestions/evidence;
- HR classification if deletion scope requires it;
- ranking item evidence/narratives containing personal data;
- search projections and cached AI context;
- outbound acknowledgment/contact data under its own policy.

Provider-side requests must be included where applicable. The present Mistral path prefers direct base64 and no Files API object, which reduces provider-file deletion risk.

Backups follow the approved backup expiry/restore-suppression process; do not falsely claim immediate physical removal from immutable backups. Restores must reapply deletion tombstones.

## 8.5 Legal hold

A legal hold records:

- tenant and scope;
- authorized actor;
- reason code/reference without unnecessary sensitive detail;
- start/review/end dates;
- affected subjects/documents;
- processing restriction;
- release approval.

Hold data is excluded from normal recruiting processing after the ordinary purpose/retention expires, unless an approved policy explicitly permits continued use.

## 8.6 Audit without prohibited content

After deletion, retain only the minimum approved audit tombstone:

- opaque event/subject reference;
- tenant;
- request/decision type;
- actor/role;
- timestamps;
- policy/basis/hold reference;
- outcome and reconciliation status;
- non-reversible hashes only where approved.

Do not retain:

- CV bytes/text;
- names, emails, or phones in general audit detail;
- embedding vectors;
- extracted evidence quotes;
- model prompts containing candidate content.

---

# 9. Search and HR experience

## 9.1 Required screens

### A. Intake setup

- company-wide, department, and job-bound forwarding aliases;
- route state and verification instructions;
- acknowledgment/privacy template;
- approved limits/quotas;
- retention policy association;
- test receipt using synthetic fixture only.

### B. Intake operations

- inbound rate and queue health;
- oldest queued work;
- stage failures/retries;
- tenant quota usage;
- spam/malware/unsupported/password-protected quarantine;
- dead-letter replay;
- acknowledgment delivery health.

### C. Talent Pool

- held `needs_role` / `import_review` records only;
- full-text and semantic search;
- categories/tags with confirmed vs AI badges;
- source channel/date/department;
- processing completeness and stale indicators;
- retention deadline/restriction;
- saved searches and counts with authority mode.

### D. Talent profile

- grouped view over one subject or confirmed identity group;
- original source timeline;
- all CV versions/documents;
- extracted facts and evidence;
- AI classification suggestions;
- HR-confirmed categories/tags;
- identity match suggestions;
- held and live applications clearly separated;
- privacy/retention status.

### E. Duplicate review

- candidate pair side-by-side;
- exact vs semantic signals;
- affected records and transitive links;
- confirm same person, reject suggestion, unlink/split;
- complete decision history.

### F. Taxonomy and tags

- browse canonical bilingual taxonomy;
- manage tenant extensions/mappings;
- inspect deprecated nodes;
- reclassify from stored text;
- never overwrite HR confirmations.

### G. Role Profiles

- create/edit draft;
- criteria, hard/soft requirements, evidence policy;
- approve immutable version;
- compare versions;
- convert approved version to draft Job.

### H. Advisory ranking

- choose approved Role Profile version;
- choose classification filters and authority mode;
- show pool/eligible/retrieved/scored counts;
- async run progress;
- score components, evidence, gaps, missing/stale inputs;
- run id/version/reproducibility details;
- selection for later explicit admit.

### I. AI Recruiter

- search/summarize Talent Pool;
- cite source profile/document evidence under permission;
- rank only with selected approved Role Profile or Job;
- state “no valid ranking context” otherwise;
- disclose stale/missing data;
- no direct lifecycle or outbound action from an answer.

### J. Privacy and retention

- deadlines and restricted items;
- deletion requests;
- legal holds;
- deletion reconciliation;
- notice/template versions;
- access-controlled audit.

## 9.2 Actions requiring preview and confirmation

Require preview + explicit confirmation:

- activating/changing a forwarding route that changes tenant/job destination;
- releasing a quarantined file;
- paid force-reprocess that bypasses cache or exceeds normal budget;
- confirming or unlinking identity;
- bulk HR classification confirmation/replacement;
- approving a Role Profile version;
- converting Role Profile to Job;
- publishing/opening that Job;
- admitting held people to a Job;
- any bulk contact action if built later;
- archive of many records;
- retention-policy recalculation;
- legal hold create/release;
- deletion approval;
- dead-letter replay when it may create held records.

No destructive confirmation is needed for:

- search/filter;
- opening source/evidence under permission;
- generating AI classification suggestions;
- running a side-effect-free advisory rank;
- saving a draft Role Profile.

## 9.3 HR journey

```text
1. Setup Console verifies forwarding + policy.
2. Intake Operations shows durable receipt and processing health.
3. Clean CV items appear in Talent Pool as held records.
4. HR searches/filter by confirmed and disclosed AI suggestions.
5. HR reviews duplicate suggestions and confirms/rejects links.
6. HR creates and approves a Role Profile.
7. HR filters the pool and runs advisory ranking.
8. AI Recruiter cites the same Profile version/run and evidence.
9. HR may convert Profile → draft Job.
10. HR publishes the Job through the existing Jobs authority.
11. HR previews and admits selected held records.
12. Frozen job Ranking/lifecycle begins only then.
13. HR archives, restricts, or deletes under policy.
```

---

# 10. Decision output

## Recommended target architecture

An ack-fast Postmark gateway durably stores tenant-routed message metadata and quarantined attachments, then commits a Postgres outbox/leased queue. Independent tenant-fair workers scan, validate, create Option B held records, extract text, structure profiles, embed, classify, acknowledge senders, enforce retention, and run explicit advisory Role Profile ranks. The frozen Job/Candidates/Ranking lifecycle begins only after explicit admission to an open Job.

## First-release authority

- `inbound_message` owns provider receipt/idempotency.
- `intake_submission` owns source, route, basis, notice, and retention.
- `intake_document` owns immutable files and security state.
- `intake_item` owns each candidate-like unit.
- `intake_subject` provides a stable non-person technical identifier.
- existing surrogate `candidate` + held `applications` row provide Option B compatibility.
- `needs_role` / `import_review` remain Talent Pool membership authority.
- `intake_admit` remains the only normal bridge into the frozen job lifecycle.

## Future Person Registry migration path

Add a tenant-scoped Person Registry later and link Persons to stable Phase 1 `subject_id` values using confirmed, reversible decisions. Map historical candidates/applications/documents without changing phone/app keys or rewriting source history. Unconfirmed subjects remain separate.

## Taxonomy model

Use a versioned global canonical taxonomy with Arabic/English labels and tenant-versioned extensions/mappings. Classification is multi-label. AI suggestions, evidence, confidence, and version remain separate from append-only HR-confirmed assignments.

## Scale and queue model

- Postgres `FOR UPDATE SKIP LOCKED` leased queue;
- at-least-once, idempotent stages;
- separate worker concurrency for scan, extraction, derivation, acknowledgment, retention, and ranking;
- tenant fairness, quotas, priority classes, circuit breakers, and dead letters;
- object storage before webhook acknowledgment;
- managed external queue only if later multi-region/throughput evidence requires it.

## Identity-resolution model

Exact event/file duplicates are deterministic. Person matching is advisory, tenant-scoped, evidence-backed, HR-confirmed, and reversible. Sender email is provenance, not person authority. Phase 1 uses intake subjects and link decisions; Phase 2 introduces Persons.

## Talent Pool and Role Profile interaction

Approved immutable Role Profile versions filter and rank held pool records in separate advisory runs. Runs snapshot all profile, pool, taxonomy, CV, embedding, and scoring versions. Ranking cannot create/admit/contact or mutate lifecycle. Conversion to Job and admission are separate confirmed actions.

## Privacy/retention model

Record source, tenant/controller basis, notice/version, policy, deadline, restriction, legal hold, and deletion status per submission/subject. Do not invent periods. Expired/requested records leave search/ranking immediately, then files and derived data are deleted or placed in restricted legal hold. Retain only minimal content-free audit tombstones.

## Smallest safe implementation sequence

Do not start from this assessment without owner approval.

1. Approve limits, quotas, acknowledgment, privacy basis/notice, retention policy values, and malware service.
2. Add durable ingress ledger/source storage/outbox and change Postmark acknowledgment boundary; no candidate behavior change yet.
3. Add leased workers, retry/dead-letter, tenant fairness, and operations UI.
4. Add file-safety scanning, explicit unsupported/password states, and async acknowledgment.
5. Add `submission_id`, `intake_item_id`, opaque `subject_id`, and sidecar links; preserve existing held apps.
6. Stop email-sender surrogate collision for new intake items; use per-subject compatibility surrogates.
7. Move Option B held-record creation behind clean accepted intake items; qualify all frozen predicates and `intake_admit`.
8. Productize Talent Pool search over held rows with processing/retention disclosure.
9. Add versioned extraction/structure/embed orchestration and cache-aware reprocessing.
10. Add identity suggestions + HR confirm/reject/unlink.
11. Add global-base/tenant-extension taxonomy and advisory classification.
12. Add separate Role Profile CRUD/version approval.
13. Add separate advisory pool ranking and reproducibility/staleness.
14. Add AI Recruiter grounding, Profile→Job conversion, and per-person admission previews.
15. Requalify frozen Jobs, Candidates, job Ranking, Reports, Assistant, Offers, Interviews, and lifecycle.
16. Consider Person Registry only after Phase 1 identity links and split/unlink are proven.

## Components that must remain separate

1. Postmark delivery vs Wathefni durable processing.
2. Webhook ingress vs processing workers.
3. Spam/malware quarantine vs OCR.
4. Inbound message vs submission vs document vs intake item.
5. Intake subject/current surrogate vs future Person.
6. Held Talent Pool record vs job application.
7. Recruiting CV OCR vs identity/employment-document OCR.
8. OCR text extraction vs LLM structuring vs embedding vs classification vs ranking.
9. AI-suggested classification vs HR-confirmed classification.
10. Role Profile/Hiring Brief vs Job Opening.
11. Role Profile advisory ranking vs frozen job Ranking.
12. Ranking/AI answer vs lifecycle/contact action.
13. Archive vs restriction vs legal hold vs deletion.
14. Candidate intake acknowledgment vs recruiting communication.
15. Pipeline reports vs advisory Talent Pool analytics.

## Owner decisions still required

1. Final company-wide/department/job-bound alias naming and verification model.
2. Wathefni hard message, attachment, page, archive, and image safety limits.
3. Tenant quotas, budget behavior, and paid-stage concurrency.
4. Malware scanning provider, fail-closed policy, quarantine access, and retention.
5. Whether job-bound aliases may auto-admit; recommendation: only exact open Job + explicit tenant policy.
6. Whether company-wide/department aliases always hold; recommendation: yes.
7. Multiple-CV and supporting-document review policy.
8. Sender acknowledgment enablement, language, sender identity, template, backscatter controls, and privacy URL.
9. Tenant-approved processing basis and notice text for unsolicited CVs.
10. Retention periods/triggers by source/data class and archive behavior.
11. Legal-hold permission and review process.
12. Deletion verification, approval roles, and backup handling.
13. Canonical taxonomy governance and tenant extension approval.
14. Classification confidence thresholds and default confirmed-vs-AI filter mode.
15. Role Profile permission (`role_profile.manage` recommended).
16. Approved-only vs draft Profile use by AI Recruiter; approved-only recommended.
17. Archived-held-row eligibility for advisory ranking; excluded by default recommended.
18. Large-pool retrieval/top-K policy and required disclosure.
19. Historical held-record subject-id backfill scope.
20. Trigger/criteria for beginning Phase 2 Person Registry.

## Items that should explicitly not be built yet

- first-class Person Registry or candidate-without-application core authority;
- automatic person merge or cross-channel identity collapse;
- cross-tenant person matching or visible global CV dedupe;
- fake/private/draft Jobs used as Role Profiles;
- any modification to frozen job Ranking authority;
- one shared ranking run table/write path for Jobs and Role Profiles;
- automatic admission, shortlist, rejection, interview, offer, hire, or contact from classification/ranking;
- classification that overwrites HR-confirmed labels;
- taxonomy/ranking changes that trigger re-OCR;
- broad historical OCR/classification backfill before quotas and retention are approved;
- direct Gmail/M365/IMAP expansion before Postmark durable ingress is proven;
- referral/agency workflow automation beyond reserved provenance/identifier types;
- unsupported-file conversion that bypasses scanning;
- automatic hard deletion without an approved tenant policy and legal-hold check;
- Talent Pool analytics mixed into job pipeline/funnel reports.

---

## Final recommendation

Approve the architecture direction, but do not implement Talent Pool, Role Profiles, automatic CV classification, or Person Registry from this report alone.

The first engineering cut, when separately authorized, should be only the **durable Postmark ingress boundary, tenant-safe quarantine storage, leased queue, retry/dead-letter controls, and operational observability**. That foundation fixes the present silent-loss/burst risk without reopening frozen pre-hiring authority. Option B Talent Pool, identity suggestions, classification, Role Profiles, and advisory ranking should then be layered additively in the sequence above.

**Stop point:** assessment complete; no implementation performed.
