# Pre-hiring Unified Inbound CV Pipeline — Architecture Review

Date: 2026-07-27 (Asia/Kuwait)  
Scope: WATHEFNI current source, deployed production contracts, and read-only production state  
Production mutations: none  
Related evidence:

- `ops/PREHIRING_WHATSAPP_UNSOLICITED_CV_AUDIT.md`
- `ops/PREHIRING_WHATSAPP_EMAIL_MANUAL_CV_PIPELINE_CONSISTENCY_REVIEW.md`
- `ops/PREHIRING_HIGH_VOLUME_EMAIL_INTAKE_TARGET_ARCHITECTURE.md`
- `ops/PREHIRING_CANONICAL_CANDIDATE_KNOWLEDGE_ARCHITECTURE_AND_IMPLEMENTATION_PLAN.md`
- `ops/PREHIRING_CANDIDATE_KNOWLEDGE_FINAL_LIVE_RELEASE_AND_FREEZE.md`

## Executive decision

The proposed direction is the correct long-term direction, with four required
clarifications.

1. One canonical pipeline must mean one set of post-ingress authorities, not one
   monolithic webhook. Email, WhatsApp, dashboard upload, and future APIs still
   need thin channel adapters.
2. A Talent Pool entry needs both immutable intake records and a canonical
   person/CV projection. An intake row alone is not a candidate; a person row
   alone loses receipt, security, consent, and provenance history.
3. The long-term person authority should be the existing additive
   `persons` + `person_company_memberships` registry, not the legacy
   phone-primary-key `candidates` table. The registry is only partially adopted
   in production and cannot yet be switched on as the sole authority.
4. A Talent Pool record should not itself become or masquerade as a Job
   application. The target model creates or reuses a separate exact Job
   application and binds a selected canonical CV version. During migration,
   existing `needs_role` / `import_review` application rows remain the
   compatibility representation and use the existing `intake_admit` lifecycle
   trigger.

Recommended topology:

```text
channel adapter
  -> durable tenant-routed intake event/submission/document
  -> quarantine + byte validation + malware scan
  -> accepted intake item
  -> text extraction/OCR + immutable derived artifacts
  -> tenant-scoped identity resolution
  -> person + company membership, or provisional identity-review subject
  -> canonical CV version + Talent Pool entry
  -> Candidate Knowledge (readable, non-actionable)
  -> exact Job + consent/binding preflight
  -> create/reuse Job application + bind selected CV version
  -> existing Job Ranking and recruiting lifecycle
```

The architecture verdict is:

- **GO** for a phased, additive implementation behind WATHEFNI-only flags.
- **NO-GO** for a big-bang rewrite, direct production channel cutover, or
  representing the current channels as unified today.

## Current production facts

Read-only inspection on 2026-07-27 found:

- `wathefni-orchestrator`: active.
- `wathefni-inbound-intake-worker.timer`: active and enabled.
- `wathefni-talent-pool-auto-email-classification.timer`: active and enabled.
- `wathefni-prehire-cv-process.timer`: inactive and disabled.
- `wathefni-ck-index`: active and enabled.
- Effective orchestrator flags:
  - inbound email `on`;
  - ClamAV scanner `clamav`;
  - automatic email classification `on`, tenant `WATHEFNI`;
  - Candidate Knowledge schema, workers, tools, and Ranking reader `on`,
    tenant `WATHEFNI`.

Current durable-email rows:

- three intake submissions: one `accepted`, one `durable`, and one
  `identity_review_required`;
- three intake documents: two `clean` under ClamAV and one `scan_pending`;
- eight completed intake processing jobs;
- identity outcomes: two `new_candidate`, one `possible_match`;
- four CV text-version rows: three `ready`, one preserved legacy source without
  text;
- two completed automatic classification jobs.

Current Person Registry adoption is partial:

- 7 `persons`, all active;
- 7 active company memberships;
- 13 contact points, none marked verified;
- 4 of 18 WATHEFNI applications have `person_id`;
- 7 of 21 legacy candidates have `person_id`;
- 0 of 30 WATHEFNI `file_registry` rows have person/membership links.

Candidate Knowledge currently contains 10 current chunks for two
`needs_role` applications. This proves that held Talent Pool CVs can be indexed
and read while Ranking remains denied. It does not prove person-native or
application-free Candidate Knowledge, because the current key remains
`app:<app_key>`.

## Assessment of the nine proposal requirements

### 1. Accept and store without a Job

**Correct.** Durable acceptance must occur before identity, OCR, or Job
resolution. “Accepted” initially means safely stored in tenant quarantine with
an immutable manifest and queue record. It must not mean “valid CV,” “candidate
identified,” or “Job application created.”

Email already has this boundary. Unsolicited WhatsApp does not: it currently
keeps a two-hour `candidate_pending_media` local-path reference. Manual import
also writes directly toward canonical candidate storage without the same
quarantine authority.

### 2. Validate, scan, OCR, and extract automatically

**Correct, with ordered and independently retryable stages.**

Required order:

```text
durable bytes
  -> size/signature/archive/PDF/image preflight
  -> malware scan
  -> accepted document classification
  -> local extraction
  -> bounded OCR/rescue
  -> structured facts
  -> embedding/classification/index
```

No OCR, model call, canonical file registration, or Candidate Knowledge indexing
may run before an authoritative clean scan. OCR, structuring, embedding, and
classification must be separate versioned artifacts so a taxonomy or embedding
change does not re-OCR a CV.

### 3. Identity and duplicate resolution

**Correct, but identity and duplicate files are different problems.**

- Provider-message replay and identical bytes may be deduplicated
  deterministically.
- Person equivalence may be resolved automatically only under a narrowly
  approved, tenant-scoped exact-key policy with no conflict.
- Name, transliteration, employment similarity, and embeddings are suggestions
  only.
- A WhatsApp sender, email sender, uploader, or API principal is provenance and
  possible evidence; none is automatically the person described by the CV.
- Cross-tenant matching must never be visible or used for person reuse.

The current email `inbound_cv_authority` resolves against legacy candidate keys.
The current `candidate_identity` Person Registry owns persons, memberships,
contacts, duplicate suggestions, confirmed merges, reversal, privacy, and legal
hold. These two authorities must be composed; neither should silently replace
the other.

### 4. Create or update a canonical Talent Pool candidate/CV

**Correct, but the canonical target is not one row.**

The required authority split is:

- intake event/submission/document/item: source and processing truth;
- person + company membership: identity truth;
- Talent Pool entry: tenant recruiting-pool membership and governance state;
- CV version: reusable document/profile truth;
- legacy candidate + held application: temporary production compatibility;
- Job application: exact Job relationship only.

The legacy `candidates` row is unsuitable as the long-term authority because its
primary key is phone and is not tenant-composite. `persons` and
`person_company_memberships` already provide the correct additive foundation,
but production linkage coverage and contact verification are not yet sufficient
for a cutover.

### 5. Make it visible to authorized HR

**Correct.** Visibility should begin at durable intake for Intake Operations,
then expand to the Talent Pool after the file is accepted. HR must see explicit
states such as:

- received;
- scan pending;
- quarantined/rejected;
- extracting/partial/failed;
- identity review required;
- accepted Talent Pool;
- restricted/archived/deletion pending;
- Job-bound.

Malware bodies and quarantined file downloads require a separate restricted
permission. Normal Talent Pool users should never receive unsafe bytes.

### 6. Index in Candidate Knowledge

**Correct after clean acceptance and governance checks.** Candidate Knowledge is
a rebuildable search/read projection, not identity, CV, Talent Pool, or Job
authority.

Near term, held compatibility applications can continue to use `app:` refs.
The target must add `person:<person_id>` and provisional
`subject:<subject_id>` references, make `app_key` optional in index jobs/chunks,
and resolve an `app:` alias into the same person record plus application
context.

### 7. Keep it unassigned to a Job

**Correct.** Department, role text, filename, CV content, email subject, or
WhatsApp caption can create routing suggestions only. They cannot set
`position_code`.

An exact Job binding requires a tenant-matched canonical Job, binding evidence,
and approved consent/authority. If any part is missing or ambiguous, the item
stays in the Talent Pool.

### 8. Block Job downstream behavior

**Correct and mandatory.** The present held-state predicates are useful but not
sufficient as the permanent proof because they depend on status conventions
and do not establish how a non-held application obtained its Job binding.

The target needs a universal verified-Job-binding authority consumed by:

- Ranking pool/materialization and the Candidate Knowledge Ranking adapter;
- screening and assessment creation/sending;
- interview creation/invitation;
- recruiting lifecycle transitions;
- candidate communication;
- shortlist, reject, offer, and hire actions.

The gate must verify a committed application-to-Job binding and capability
state. Job-open/intake-eligible is required when creating the binding; later
processing of an already valid application follows the existing Job/lifecycle
policy and must not be invalidated merely because intake later closes.

Three current implementation details require closure before this can be treated
as a universal contract:

- the manual single-item assign endpoint has one extra SQL parameter in its
  application update and is not a qualified promotion path;
- explicit-role manual imports default to auto-admit when the company setting is
  absent, while governed email deliberately never auto-admits;
- Candidate Knowledge aggregates sibling applications by phone and computes the
  strictest actionability across all siblings, so one held sibling can over-deny
  a separate live application's subject-level capabilities.

### 9. Reuse the CV later

**Correct.** Reuse means binding an existing immutable `cv_version_id` to a new
or existing application. It does not mean copying the file, rerunning OCR,
moving document ownership, or changing the Talent Pool person's identity.

The application binding pins the CV version used for that application. A later
CV may become the person's current Talent Pool CV without silently rewriting
historical application evidence or past Ranking runs.

## What the email intake already provides

The live email path is the correct foundation for these shared concerns:

1. Trusted tenant routing through the intake-address registry.
2. Provider/message idempotency.
3. Durable submission and attachment manifests before processing.
4. Tenant quarantine storage with immutable source provenance.
5. Byte-detected MIME, PDF/DOCX/image safety checks, and limits.
6. Fail-closed ClamAV scanning with evidence.
7. PostgreSQL leased processing jobs, retries, dead letters, and tenant
   concurrency controls.
8. Sender treated as provenance rather than candidate identity.
9. CV-derived identity extraction and explicit outcomes:
   `safe_exact_reuse`, `new_candidate`, `possible_match`, `conflict`.
10. Binding authorization before canonical candidate/document registration.
11. Shared local-first extraction and bounded OCR/rescue.
12. Canonical extraction evidence and fact snapshots.
13. Immutable CV text versions.
14. Automatic Talent Pool classification.
15. Candidate Knowledge indexing and held-state actionability.

These capabilities should be extracted and generalized, not independently
reimplemented in the WhatsApp and dashboard handlers.

## Email assumptions that must not become shared contracts

The current email implementation still contains channel and application
assumptions:

- `intake_submissions.inbound_id` and `intake_documents.inbound_id` are required
  foreign keys to the email `inbound_messages` table.
- `provider_message_id`, `envelope_recipient`, and sender-address fields are
  email-shaped.
- `source_channel` defaults to `email_inbound`.
- accepted preparation registers through `register_imported_cv`.
- accepted documents are projected into `candidate_documents` and text versions
  by `app_key`.
- email documents are labelled `bulk_import` in part of the canonical
  projection, so source filters require sidecar joins.
- automatic classification is explicitly email/recipient/canary scoped.
- current identity reuse is built around candidate phone keys, not fully adopted
  person/membership keys.

The shared core therefore must be extracted below these assumptions, while the
working email adapter remains behavior-compatible.

## What must remain channel-specific

### Email

- Postmark webhook authentication and provider-message fields;
- envelope-recipient to tenant/route resolution;
- SPF/DKIM/spam signals;
- multi-attachment email association;
- sender acknowledgment, bounce, complaint, and backscatter controls;
- company/department/Job-bound alias policy.

### WhatsApp

- Octopus account, provider message/media IDs, download, and replay identity;
- sender phone, conversation, locale, and conversation continuity;
- apply-code/role-selection dialogue;
- explicit application preview and confirmation;
- candidate-facing processing messages;
- conversation-to-application binding after application creation.

The WhatsApp phone is a verified channel endpoint, not proof that the uploaded
CV belongs to that sender.

### Manual dashboard upload

- authenticated HR uploader and permission;
- batch/ZIP/CSV/XLSX orchestration;
- agency/referral and source metadata;
- optional candidate/person selection;
- explicit duplicate-review and role-admission actions;
- no candidate acknowledgment unless separately requested and authorized.

Arbitrary ZIP, legacy DOC, and RTF must not bypass the canonical accepted-format
and archive-safety policy.

### Future API/import

- client/service authentication;
- tenant entitlement and rate quota;
- caller idempotency key and external reference namespace;
- declared source/agency and processing-basis metadata;
- asynchronous status callback or polling contract;
- no caller-supplied `company_code`, person ID, or Job ID without authorization
  and tenant verification.

### Shared but parameterized

Technical limits, accepted formats, retention policy, acknowledgment policy,
auto-admit policy, and paid-provider budgets may vary by approved tenant policy,
but the enforcing authority and state machine must remain shared.

## Recommended canonical data model

### Use intake record and candidate/person record — both

The answer is **both**, with an explicit boundary:

```text
intake record
  = what arrived, through which channel, for which tenant, with which bytes,
    safety state, notice/basis, and route/consent claims

person/company membership
  = who the tenant currently believes the subject is

Talent Pool entry
  = whether that membership is available for governed recruiting discovery

CV version
  = reusable accepted evidence for the membership

Job application
  = exact relationship to one verified Job
```

An intake record must exist even when:

- the file is malicious or unsupported;
- identity is unresolved;
- the same file is a replay;
- the sender is an agency;
- the person already exists;
- no application is ever created;
- a later privacy/deletion operation must reconcile source and derived data.

A person/Talent Pool record must not be created solely because arbitrary bytes
arrived. It is created or linked only after accepted-item and identity policy.

### Existing schema to retain

Retain and evolve:

- `inbound_messages` as the email provider ledger;
- `whatsapp_inbound_messages` as the WhatsApp provider ledger;
- `intake_submissions`;
- `intake_documents`;
- `intake_processing_jobs` and event/quota/tenant-queue tables;
- `persons`;
- `person_company_memberships`;
- `person_contact_points`;
- `person_duplicate_suggestions`;
- `person_merge_operations` and immutable merge/reversal evidence;
- `file_registry`;
- extraction evidence/fact/classification tables;
- Candidate Knowledge index/access tables;
- `applications`, `candidates`, and `candidate_documents` as compatibility
  surfaces during migration.

### Add or generalize

#### `intake_source_events`

Canonical channel event and idempotency envelope:

```text
event_id uuid primary key
company_code text not null
channel text not null
provider text not null
provider_account_id text
external_event_id text not null
trusted_route_key text
route_snapshot jsonb not null
provenance jsonb not null
received_at timestamptz not null
unique(company_code, channel, provider, provider_account_id, external_event_id)
```

Backfill email rows from `inbound_messages`; link WhatsApp events from
`whatsapp_inbound_messages`. Existing ledgers remain provider-specific evidence.

#### Evolve `intake_submissions` and `intake_documents`

- add `event_id` referencing `intake_source_events`;
- backfill existing email rows;
- only after parity, allow legacy email `inbound_id` to be nullable for non-email
  submissions;
- preserve existing IDs and immutable provenance triggers;
- add explicit source-document role and retention/governance references;
- do not rename or drop the live email columns during the first release.

#### `intake_items` and `intake_item_documents`

One submission can contain several CVs and supporting files:

```text
intake_items(
  item_id, company_code, submission_id, subject_id,
  item_kind, acceptance_state, identity_state, processing_state,
  requested_job_binding_state, created_at, updated_at
)

intake_item_documents(
  company_code, item_id, document_id,
  document_role, is_primary, created_at
)
```

Never infer that two CVs from one sender are one person.

#### `intake_subjects`

Create an opaque tenant-scoped subject before person resolution:

```text
subject_id uuid primary key
company_code text not null
originating_item_id uuid not null
status text not null
person_id uuid
membership_id uuid
created_at timestamptz not null
updated_at timestamptz not null
```

`subject_id` is a technical intake identity, not a natural-person claim. It
allows HR visibility and provisional Candidate Knowledge without forcing an
unsafe person merge.

#### Generalized identity ledger

Evolve the current `inbound_cv_identity_*` schema to identify `item_id` /
`subject_id` and `channel`, while retaining `intake_document_id` for evidence.
It records:

- observed identifiers and provenance;
- strong/weak signals separately;
- outcome and policy version;
- candidate/person/membership selected, if any;
- conflict/review state;
- actor/service and decision evidence.

`candidate_identity` remains the only owner of person/membership/contact rows,
duplicate suggestions, merge, and reversal.

#### `talent_pool_entries`

Make Talent Pool membership explicit:

```text
entry_id uuid primary key
company_code text not null
subject_id uuid not null
person_id uuid
membership_id uuid
state text not null
governance_state jsonb not null
legacy_held_app_key text
created_at timestamptz not null
updated_at timestamptz not null
```

Use one active entry per tenant membership when identity is confirmed. Keep
separate provisional entries for unresolved subjects. Existing held applications
remain linked compatibility rows, not the long-term pool authority.

#### `candidate_cv_versions`

Canonical reusable CV authority:

```text
cv_version_id uuid primary key
company_code text not null
subject_id uuid not null
person_id uuid
membership_id uuid
source_document_id uuid not null
content_sha256 text not null
text_version_id uuid
status text not null
received_at timestamptz not null
supersedes_cv_version_id uuid
provenance jsonb not null
```

Use a separate current-version relation or partial unique constraint scoped to
the confirmed company membership. Do not treat identical content hashes as
proof of the same person.

`candidate_cv_text_versions` should be migrated from `app_key` ownership to
`cv_version_id` ownership. Keep `app_key` as a nullable compatibility link until
all current readers are migrated.

#### `application_cv_bindings`

```text
company_code text not null
app_key text not null
cv_version_id uuid not null
binding_kind text not null
consent_event_id uuid
bound_by text not null
bound_at timestamptz not null
is_current boolean not null
```

This pins which reusable CV version an application uses without copying the
document or changing person-level current-CV state.

#### `application_job_bindings`

```text
binding_id uuid primary key
company_code text not null
app_key text not null unique
position_code text not null
source_item_id uuid
binding_method text not null
consent_event_id uuid
verified_at timestamptz not null
verified_by text not null
verification_policy_version text not null
revoked_at timestamptz
```

This is the positive evidence required by downstream gates. Existing
applications require a separately audited legacy backfill classification; a
nonblank `position_code` alone is not sufficient proof for new records.

#### `intake_consent_events`

Record candidate consent or authorized HR processing basis without conflating
them:

```text
consent_event_id, company_code, subject_id, channel,
event_kind, scope, evidence_ref, notice_version,
actor_type, actor_id, occurred_at, revoked_at
```

An unsolicited CV receipt must not be labelled consent unless the approved
tenant policy and actual interaction establish it.

## Duplicate prevention across channels

Use layered idempotency:

1. **Provider event**
   - email: provider message ID;
   - WhatsApp: provider/account/message ID;
   - dashboard: upload request/batch item;
   - API: client + caller idempotency key.
2. **Source attachment**
   - event + ordinal/media ID.
3. **Exact bytes**
   - tenant + SHA-256.
   - Reuse clean scan/OCR only when policy, scanner freshness, preprocessing, and
     model/cache versions allow it.
4. **Accepted intake item**
   - submission + primary document.
5. **CV version**
   - subject/membership + source document/content hash.
6. **Person**
   - exact tenant-scoped governed identifiers or human-confirmed identity link.
7. **Application**
   - person/membership + company + exact Job + active-state policy.

Required person rules:

- never merge on name, filename, sender, employer overlap, or embedding;
- CV-extracted email/phone are observations until verification policy says
  otherwise;
- exact conflicts create review;
- possible matches create suggestions, not automatic ownership changes;
- confirmed merges remain previewed, permissioned, audited, and reversible;
- same bytes submitted for two people must not collapse the people;
- different CV bytes for one person create versions, not duplicate people.

The current `applications_one_active_same_role_uq` index is phone-based. Add a
person-aware partial unique constraint for new linked applications only after a
duplicate audit:

```text
unique(company_code, person_id, position_code)
where person_id is not null and application is active/non-held
```

Promotion must preflight both person-aware and legacy phone-aware applications
until migration is complete.

## Candidate Knowledge for general Talent Pool candidates

### Current safe behavior to preserve

- held `needs_role` CVs are indexed and readable;
- held actionability denies communication, lifecycle mutation, and Job Ranking;
- index rows are tenant-scoped and rebuildable;
- embeddings are retrieval only, never identity authority;
- restricted/deleted versions are invalidated or hidden;
- Ranking pins evidence versions and retains the held-deny overlay.

### Required target changes

1. Extend Candidate Knowledge reference parsing:
   - `person:<person_id>` for confirmed Talent Pool people;
   - `subject:<subject_id>` for unresolved provisional intake;
   - `app:<app_key>` for exact application context and compatibility.
2. Change `candidate_knowledge_chunks` and
   `candidate_knowledge_index_jobs`:
   - add `subject_id`, `person_id`, `membership_id`, and `cv_version_id`;
   - make `app_key` nullable after all call sites support non-app subjects;
   - retain application context as metadata, not person identity.
3. Make canonical CV/facts/classification readers resolve through
   `cv_version_id`, not only `app_key`.
4. Keep unresolved subjects separate. Identity confirmation triggers:
   - invalidate old subject chunks;
   - index under the confirmed person;
   - preserve access/index events without rewriting source intake history.
5. Search scope must explicitly distinguish:
   - Talent Pool discovery;
   - active Job applications;
   - archived/restricted records.
6. Every result must carry:
   - identity-review state;
   - source channels;
   - CV/artifact versions;
   - processing completeness;
   - actionability and reason codes.
7. Application Ranking uses the CV version pinned by
   `application_cv_bindings`; it must not silently switch to a newer Talent Pool
   CV.

Candidate Knowledge must never:

- merge or select persons;
- create a Job application;
- bind a CV to a Job;
- admit held intake;
- send communication;
- treat semantic similarity as identity;
- make a provisional subject actionable.

## How Talent Pool becomes an exact Job application

Target transaction:

1. Receive an exact apply code/Job selection or an authorized HR selection.
2. Resolve the canonical Job under the same tenant.
3. At binding time, require the Job to be open and intake-eligible.
4. Capture approved consent/authority evidence and the exact Job preview/version.
5. Resolve the Talent Pool subject to a person/company membership, or stop for
   identity review.
6. Lock the person/membership and target Job application scope.
7. Preflight existing applications by:
   - `(company_code, person_id, position_code)`;
   - legacy `(company_code, phone, position_code)`;
   - conversation/application binding where relevant.
8. If an eligible application already exists:
   - reuse it;
   - bind or update the selected CV version only under the approved replacement
     policy;
   - do not create a duplicate.
9. Otherwise create the exact Job application and
   `application_job_bindings` row.
10. Bind the selected `cv_version_id` through `application_cv_bindings`.
11. Write lifecycle/audit and channel bindings transactionally or through an
    idempotent outbox.
12. Only after commit may downstream Job capabilities become eligible.

### Transitional production behavior

While frozen modules remain application-centric:

- keep one linked held application as the compatibility work item;
- assign the exact Job and enter `ready_for_review` only through
  `recruiting_lifecycle.update_application_status(...,
  trigger="intake_admit")`;
- preserve the immutable intake item, Talent Pool entry, and canonical CV
  version even if the compatibility application row is admitted;
- add a real preview/confirm API and UI—the current Unified Candidates surface
  explicitly reserves Link to Job and does not implement it.

Long term, `talent_pool_entries` remains independent and admission creates or
reuses a separate application. This avoids losing pool history and avoids
treating a general submission as if it had always been an application.

## Exact shared authority modules

### New channel-neutral modules

#### `inbound_cv_intake.py`

Own:

- source event/submission/document/item creation;
- idempotency;
- quarantine manifests;
- intake state machine;
- queue/outbox orchestration;
- tenant quotas/fairness;
- immutable provenance.

Extract the generic parts from `durable_email_ingress.py`. Keep
`durable_email_ingress.py` as the Postmark adapter until behavior parity is
proven.

#### `inbound_cv_processing.py`

Own:

- accepted-item stage orchestration;
- scan -> extract -> structure -> classify -> index transitions;
- idempotent retries/dead letters;
- versioned artifact dependencies;
- no channel conversation behavior.

#### `talent_pool_authority.py`

Own:

- `talent_pool_entries`;
- subject/person/membership linkage;
- CV version current/superseded state;
- held compatibility projection;
- archive/restrict/delete eligibility;
- no Job lifecycle.

#### `job_application_binding.py`

Own:

- exact Job resolution and tenant checks;
- consent/basis verification;
- duplicate-application preflight;
- `application_job_bindings`;
- `application_cv_bindings`;
- create/reuse/admit transaction;
- `assert_verified_job_binding`.

### Existing modules to retain and narrow

- `durable_email_ingress.py`
  - Postmark adapter plus temporary compatibility wrappers.
- `inbound_cv_authority.py`
  - scan/binding evidence and intake identity-resolution ledger;
  - stop owning person truth through legacy phone keys.
- `candidate_identity.py`
  - sole Person Registry, company membership, contact, duplicate suggestion,
    merge/reversal, privacy, and legal-hold authority.
- `cv_extraction.py`, `cv_docx.py`
  - shared format/extraction implementation.
- `candidate_cv_evidence.py`, `candidate_cv_facts.py`
  - shared versioned evidence/fact authorities.
- `talent_pool_classification.py`
  - channel-neutral advisory classification.
- `talent_pool_auto_email_classification.py`
  - replace with a channel-neutral eligibility worker; retain an email wrapper
    during migration.
- `candidate_record_state_policy.py`
  - shared read/actionability projection, extended to Talent Pool entries and
    verified binding state.
- `candidate_knowledge_authority.py`,
  `candidate_knowledge_indexer.py`,
  `candidate_knowledge_index_schema.py`,
  `candidate_knowledge_store.py`
  - add person/subject/CV-version references and app aliases.
- `recruiting_lifecycle.py`
  - remains application lifecycle authority after verified binding.
- `candidate_communication_authority.py`
  - remains communication gate and consumes verified binding.
- `candidate_ranking.py` and the Ranking evidence adapter
  - remain Job Ranking authority and consume verified binding/CV version.
- `unified_candidates.py`, `unified_candidates_routes.py`
  - Talent Pool and Intake Operations projection, not mutation authority.
- `jobs_phase2_stage_b.py`
  - WhatsApp conversion becomes a caller of `job_application_binding.py`, not a
    separate application/document creation authority.
- `app.py`
  - route composition only; remove duplicated channel-specific canonical writes.
- `plugins/octopus-channel/octopus-channel.ts`
  - transport download and provider metadata only.

## Production compatibility and migration risks

### 1. Live email path regression

Inbound email, scanning, extraction, automatic classification, and CK indexing
are live. Moving code before dual-write parity could lose or duplicate intake.

Mitigation: email is the reference adapter; first extract generic functions
without changing its IDs, HTTP acknowledgment boundary, state names, or worker
results.

### 2. Application-centric storage

`candidate_cv_text_versions`, Candidate Knowledge refs, classification jobs,
and many readers are keyed by `app_key`.

Mitigation: add subject/person/CV-version columns and dual-write first. Do not
make `app_key` nullable or switch readers until production-fidelity comparison
is green.

### 3. Partial Person Registry adoption

Most applications/files are not linked to a person, and current contact points
are unverified. Automatically trusting those rows would create false reuse.

Mitigation: no broad automatic person backfill/merge. Use one-person-per-legacy-
candidate migration only as compatibility, create match suggestions, and require
review for ambiguity. Backfill file/person links from proven application and
document ownership only.

### 4. Dual identity authorities

`inbound_cv_authority` uses candidate identity keys; `candidate_identity` owns
persons and merges. Independent evolution would produce conflicting decisions.

Mitigation: define one composition contract. Intake identity resolution emits a
decision; only `candidate_identity` may create/link/merge persons.

### 5. Duplicate active applications

The current unique active same-role index is phone-based and excludes held
statuses. Person-linked duplicates can bypass it if legacy phones differ.

Mitigation: person-aware preflight, locking, idempotency key, then a partial
person-aware unique index after production duplicate audit.

### 6. Provenance drift

Email may appear as `bulk_import`; source filters read different sidecars.

Mitigation: `intake_source_events.channel` becomes canonical provenance. Legacy
fields remain projections and must not drive security or identity.

### 7. WhatsApp transport/runtime drift

The deployed Octopus plugin was not byte-identical to the repository during the
unsolicited-CV audit.

Mitigation: pin and hash the production transport artifact before any adapter
change; qualify provider replay, download failure, and local-path cleanup.

### 8. Worker coverage mismatch

The generic CV timer is disabled while email-specific bounded workers are live.
Simply enabling it would process manual/WhatsApp backlog under older authority.

Mitigation: do not enable the old timer. Introduce channel-neutral accepted-item
workers with explicit cutover markers and bounded backfill.

### 9. Held-state status dependence

Current safety relies heavily on `needs_role` / `import_review` and duplicated
predicates.

Mitigation: retain those predicates and add positive verified-binding evidence.
Qualification must prove both layers until the compatibility held application
is retired.

### 10. Historical CV semantics

Changing a person's current CV could silently change old application evidence.

Mitigation: immutable CV versions and explicit application-CV bindings; old
Ranking runs retain their pinned versions.

### 11. Privacy, retention, and consent

Different channels provide different evidence and may involve agencies or HR
uploads.

Mitigation: record source, controller/tenant, approved processing basis, notice
version, retention deadline, consent/authority events, restriction, legal hold,
and deletion reconciliation. Do not invent consent from submission.

### 12. Rollback

A schema-only rollback cannot remove accepted submissions or safely undo person
links.

Mitigation: additive schema, flags, idempotent dual-write, append-only link
decisions, reversible person merges, and no destructive legacy cleanup until
after a sustained compatibility window.

### 13. Current single-item promotion defect

`dashboard_prehire_import_assign` executes an `UPDATE applications ... WHERE
app_key=%s` statement but passes both `app_key` and a trailing `company`
parameter. The preceding read is tenant-scoped, but the update's placeholder
count does not match its arguments. The bulk assign path is the currently
credible implementation reference.

Mitigation: fix and production-fidelity test the single-item endpoint before
building Link to Job on it. The final update must include
`WHERE app_key=%s AND company_code=%s`, verify one affected row, and then invoke
the same idempotent `intake_admit` authority as bulk promotion.

### 14. Manual auto-admit default

`company_auto_admit_imports()` returns true when
`intake_auto_admit_explicit` is unset. Non-governed manual imports with an
explicit `position_code` can therefore enter `review_pending` immediately,
while governed email is forced held.

Mitigation: a unified pipeline must make admission an explicit tenant policy
with recorded authority/consent evidence. During migration, default new unified
sources to held and preserve the old setting only for the legacy manual path
until the owner approves a behavior change.

### 15. Candidate Knowledge sibling actionability

`CandidateKnowledgeAuthority` resolves siblings by legacy phone and requires all
sibling decisions to allow contact, lifecycle, or Ranking. A held import sibling
can therefore make an otherwise live sibling look non-actionable in a
subject-level CK response. Job Ranking still applies row-level SQL and the
Ranking overlay, but tool semantics can be over-conservative.

Mitigation: keep person-level Talent Pool search non-actionable by default, but
compute Job capabilities against the exact `app:<app_key>` context. Rename or
split the misleading `talent_pool_search_eligible` policy field into
`talent_pool_visible` and `job_pipeline_eligible`.

## Recommended phased implementation

### Phase 0 — contract freeze and tests

1. Freeze current email, manual, WhatsApp, Person Registry, Candidate Knowledge,
   and lifecycle contracts.
2. Add fixtures for every channel and:
   - CV only;
   - CV then apply code;
   - apply code then CV;
   - multiple files;
   - agency/shared sender;
   - identical and changed CVs;
   - possible match/conflict;
   - unsupported/corrupt/password/malware;
   - concurrent duplicate application;
   - single-item and bulk assign parity;
   - mixed held/live siblings under one legacy phone;
   - explicit-role manual import with the auto-admit setting missing, false, and
     true.
3. Add a zero-downstream-mutation fingerprint.

Exit: current behavior is reproducible before refactoring.

### Phase 1 — generic intake envelope, email unchanged

1. Add `intake_source_events`, `intake_items`, document links, and subject IDs.
2. Extract `inbound_cv_intake.py`.
3. Dual-write live email into the generic envelope.
4. Compare counts, checksums, route snapshots, job events, and outcomes.
5. Keep all readers and user-visible behavior on the existing email path.

Exit: every email row has one exact generic mapping with no duplicate candidate,
application, file, OCR, classification, or CK write.

### Phase 2 — shared security and processing authority

1. Extract channel-neutral scan and accepted-item workers.
2. Move immutable text/fact/classification dependencies to `cv_version_id`.
3. Preserve email wrappers and results.
4. Prove scanner outage, dead letter, retry, cache, and kill switch.

Exit: one accepted document produces the same artifacts regardless of adapter.

### Phase 3 — manual upload adapter

1. Route manual files through the generic envelope and quarantine.
2. Reject formats unsupported by the canonical safety/extraction policy.
3. Preserve batch/metadata/agency provenance.
4. Allow explicit existing-person selection, otherwise run shared identity
   resolution.
5. Keep old direct import write path behind rollback flag during canary.
6. Keep unified-source auto-admit off by default; require an explicit approved
   tenant policy and binding evidence before enabling it.

Exit: manual uploads no longer bypass scan/identity and do not create surrogate
duplicates under exact existing identities.

### Phase 4 — unsolicited WhatsApp adapter

1. Replace temporary `candidate_pending_media` as document authority with the
   durable envelope.
2. Keep provider/account/message/conversation/media provenance.
3. Store and scan before claiming successful CV acceptance.
4. Make processing and identity-review state visible to HR.
5. Do not create or bind any Job application.

Exit: CV-only WhatsApp produces a durable, visible, non-actionable Talent Pool
item and survives process restart/provider replay.

### Phase 5 — Person Registry and Talent Pool authority

1. Create/link intake subjects through `candidate_identity`.
2. Add `talent_pool_entries` and canonical CV versions.
3. Dual-write legacy candidate and held application compatibility rows.
4. Add identity suggestions and governed confirm/reject/merge/unlink UI.
5. Backfill only proven links; leave uncertain historical records separate.

Exit: a person can have multiple channels and CV versions without duplicate
people or rewriting source history.

### Phase 6 — Candidate Knowledge person/subject indexing

1. Add `person:` and `subject:` refs.
2. Dual-index a bounded WATHEFNI canary and compare with `app:` results.
3. Keep held/provisional actionability denied.
4. Prove identity correction invalidation/reindex order.
5. Prove restricted/deleted data disappears from all retrieval modes.
6. Separate person-level discovery actionability from exact application-level
   Job capabilities so a held sibling cannot disable an unrelated valid
   application.

Exit: general Talent Pool search no longer requires an application as the
canonical identity, while legacy exact reads remain compatible.

### Phase 7 — exact Job binding and consent

1. Add consent events, application-Job bindings, and application-CV bindings.
2. Implement one preview/confirm promotion service.
3. Make Stage B, dashboard Link to Job, email Job aliases, and future APIs call
   that service.
4. Add person-aware duplicate application locking and uniqueness.
5. Retain `intake_admit` as the compatibility lifecycle entry.
6. Before wiring Link to Job, correct the single-item assign SQL tenant
   predicate/parameter mismatch and qualify it against the bulk path.

Exit: CV then apply code, apply code then CV, and HR admission all produce one
exact application with one pinned CV and auditable authority.

### Phase 8 — universal downstream gate

1. Add `assert_verified_job_binding`.
2. Integrate it into Ranking, screening, assessments, interviews,
   communication, lifecycle, offer, hire, and CK Ranking adapters.
3. Backfill historical application bindings only after audit.
4. Run shadow-deny mode before enforcement.

Exit: no unverified/unassigned record can enter any Job workflow even if a
status or `position_code` is malformed.

### Phase 9 — future API/import adapter and cutover

1. Publish the authenticated asynchronous adapter contract.
2. Canary one source and one tenant.
3. Observe backlog, duplicate, identity-review, cost, and downstream-denial
   metrics.
4. Cut channels over separately.
5. Retire old direct write paths only after rollback windows and restore drills.

## Required qualification gates

Before any live channel cutover:

- zero source/document loss across restart and provider replay;
- no OCR before authoritative clean scan;
- no cross-tenant object, identity, CK, or application visibility;
- exact-byte dedupe without false person merge;
- changed CV creates a version without repeated person/application creation;
- possible-match/conflict remains reviewable and non-actionable;
- one person/Job has at most one eligible active application under concurrency;
- the selected CV version is pinned to the application;
- no Talent Pool item can rank for a Job, screen, assess, interview, receive Job
  communication, advance lifecycle, offer, or hire without verified binding;
- CK held/provisional records are readable only to authorized actors and remain
  non-actionable;
- restriction/deletion invalidates CK and derived artifacts;
- worker, channel, CK, and downstream-gate kill switches and restores are
  proven;
- external tenants remain off until separately qualified.

## Recommended architecture

Adopt a layered canonical intake architecture:

1. thin channel adapters establish provider authenticity, tenant route, source
   provenance, and any Job/consent claim;
2. one durable intake authority owns submissions, source documents, quarantine,
   state, and work orchestration;
3. one security/extraction pipeline produces immutable reusable artifacts;
4. `candidate_identity` owns person/company identity and governed duplicate
   decisions;
5. an explicit Talent Pool authority owns pool membership and person-level CV
   versions;
6. Candidate Knowledge indexes accepted person/subject evidence as a
   non-authoritative, held-aware projection;
7. one exact Job-binding authority creates/reuses an application and pins a CV
   only after tenant, Job, consent/authority, identity, and duplicate checks;
8. existing recruiting lifecycle and Job Ranking remain downstream and require
   positive verified-binding evidence.

This design generalizes the strongest live email contracts, preserves
channel-specific conversation and provider behavior, uses the existing Person
Registry rather than inventing another candidate identity, and keeps the frozen
Job pipeline isolated until an exact application exists.

## Final GO / NO-GO

### Architecture and implementation

**GO — phased implementation is recommended.**

The proposal is the correct long-term design when implemented with the
intake/person/Talent Pool/application separation, Person Registry integration,
canonical CV versions, and positive verified-Job-binding gate described above.

### Production cutover

**NO-GO — do not reroute or enable production channels from this review.**

The current email path is live, Person Registry adoption is partial, Candidate
Knowledge is application-keyed, manual/WhatsApp security differs, and the
universal verified-Job gate does not yet exist. Begin only with Phase 0 and an
additive production-dark Phase 1 under separate authorization.

