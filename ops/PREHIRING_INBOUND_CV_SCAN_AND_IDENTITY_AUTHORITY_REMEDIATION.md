# Pre-Hiring Inbound CV Scan and Identity Authority Remediation

Date: 2026-07-26  
Scope: durable malware-scan authority and safe candidate identity resolution for inbound CV email only  
Production automation: **OFF throughout; not re-enabled**  
Production retained Noor/Esraa evidence: **preserved; no cleanup or correction executed**

## Verdict

**NO-GO to rearm the internal production automatic email canary now.**

The contained remediation is **GO for an exact production-dark promotion**. Local
and staging qualification are green, including real staging ClamAV, real scanned
CV OCR, Noor-like identity conflict isolation, document-current versioning, frozen
regressions, and zero synthetic residue.

Rearming remains NO-GO because the production runtime is intentionally unchanged.
Before rearming, the exact qualified authority artifact must be promoted to
production with automation still OFF, the retained Noor/Esraa correction must be
executed under that authority, and production-dark scan/identity/current-boundary
checks must pass.

## Scope control

Changed:

- durable attachment scan decisions;
- scan fail-closed enforcement;
- tenant-scoped CV identity resolution;
- held identity review/conflict records;
- document-current promotion gating;
- qualification and staging patch tooling.

Not changed:

- classification logic, taxonomy, classifier version, or suggestion behavior;
- Unified Candidates UX;
- Jobs, lifecycle, ranking, outreach, offers, assessments, or Role Profiles;
- external tenant classification enablement;
- production automatic enqueue, bounded worker, or historical backfill.

## Production posture

Final production check:

- orchestrator: `active`;
- automatic classification timer: `inactive` / `disabled`;
- bounded classification worker: `inactive`;
- `WATHEFNI_TALENT_POOL_AUTO_EMAIL_CLASSIFICATION=off`;
- `WATHEFNI_TALENT_POOL_CLASSIFICATION_WORKERS=off`;
- manual classification: `on`;
- internal classification UI: `on`;
- production `app.py` SHA-256 remains
  `eb49fbb9a40349812293e57f1e9c660e51641034b15af097e1b91c6d37f90acb`.

No production code, schema, candidate row, document row, classification row, or
service configuration was changed in this remediation. No production CV email was
sent.

Staging posture after qualification:

- orchestrator: `active`;
- `WATHEFNI_INBOUND_EMAIL=off`;
- sender acknowledgment: `off`;
- durable intake service worker: `inactive` / `disabled`;
- owner-manual intake monitor processes: `0`;
- qualification invoked only explicit, job-type-scoped in-process stages;
- classification automatic enqueue and classification workers were forced OFF in
  every qualification process.

## Root cause

### Missing durable malware-scan authority

The failed production path was the legacy synchronous Postmark import path, not
the durable email-ingress pipeline.

For inbound `809f5c46-b9eb-41fb-9898-14427946cc90`:

- production had no `intake_submissions`, `intake_documents`, or
  `intake_processing_jobs` authority rows;
- no scanner engine, scanner version, signature database version, started/completed
  timestamps, result, failure reason, quarantine reference, or service actor was
  persisted;
- `validation_status=accepted` and `storage_status=stored` were incorrectly the
  only observable acceptance signals;
- those signals are storage/format outcomes and are not malware-scan proof.

The path therefore permitted extraction and candidate mutation with no durable
clean decision.

### Sender-derived candidate binding

The production legacy Postmark handler called `_import_process_one_file` with:

`meta={"email": from_address}`

The shared import path then:

1. treated that sender address as `candidate_email`;
2. called `import_surrogate_phone(company, email=sender, checksum=...)`;
3. preferred email over content hash;
4. derived the application key from that surrogate plus
   `WATHEFNI-IMPORT`;
5. upserted the existing candidate and application before CV extraction;
6. extracted Noor's actual identity only after the document was already bound.

The exact matching inputs considered by the old binding were:

- tenant: `WATHEFNI`;
- sender email: `azizalmulla16@gmail.com`;
- position: empty / `IMPORT`;
- checksum: available, but not used for identity because sender email took
  precedence;
- filename-derived name: `Noor Tahat`, stored as import metadata but not used to
  prevent reuse;
- extracted CV email `noortahat3@gmail.com`: unavailable to the binding decision.

The sender-derived surrogate was
`imp-wathefni-06ffffc36d7fd375`, which already belonged to Esraa Aziz. The
candidate upsert preserved Esraa's non-empty name/email, while the application
upsert replaced its current CV projection.

Follow-up inspection found the same unsafe shared seam in legacy Gmail mailbox
sync: it passed the parsed sender as `meta.email` and did not enter the durable
scan pipeline. The remediated Postmark path never does this. Live legacy mailbox
sync is now fail-closed with
`durable_scan_and_identity_authority_required` before provider fetch, import-batch
creation, extraction, or candidate mutation. Dry-run mailbox inspection remains
read-only. The shared import core also rejects any `email` or `email_inbound`
source that lacks an accepted governed identity resolution.

## Retained Noor/Esraa failure evidence

Inbound:

- inbound ID: `809f5c46-b9eb-41fb-9898-14427946cc90`;
- provider message ID: `6bc87818-67ed-43f4-be12-ba0d3253acc5`;
- sender: `azizalmulla16@gmail.com`;
- received: `2026-07-26T01:46:28Z`;
- import batch: `26a1e420-456c-41bc-8c36-7062f4d59305`;
- import item: `2c2a70da-43c5-43e4-8bc9-b86f8d56a820`.

Incorrect binding:

- candidate phone: `imp-wathefni-06ffffc36d7fd375`;
- candidate name: `Esraa Aziz`;
- application:
  `imp-wathefni-06ffffc36d7fd375-WATHEFNI-IMPORT`;
- imported filename: `Noor Tahat - CV.pdf`;
- imported item candidate name: `Noor Tahat`;
- imported item candidate email: sender
  `azizalmulla16@gmail.com`;
- extracted CV email: `noortahat3@gmail.com`;
- source SHA-256:
  `d951c3e27796318075c7c532be45d641e04170e3cd738081efd8ab4d5e2b2934`;
- file registry ID: `c2cc57ed-427a-4840-b981-74a03df8fb61`;
- candidate document ID: `5608a4ef-87d2-49d8-9c7a-9ec5666a92ef`.

Documents mutated:

1. June Esraa document
   `d47f6c3f-eb02-4e64-8443-10d1e497e418`
   was changed to `latest=false`, superseded at
   `2026-07-26T01:46:55Z`.
2. July Esraa document
   `71a889fd-7e45-4825-bd2e-da15d00888ba`
   was changed to `latest=false`, superseded at the same timestamp.
3. Noor document
   `5608a4ef-87d2-49d8-9c7a-9ec5666a92ef`
   became `latest=true`.
4. Esraa's application `raw_json.cv` and file-registry current marker changed to
   Noor's file.
5. Canonical current text/evidence/facts/profile projection changed to Noor's
   extraction.

All three source files still exist under distinct content-addressed paths.

Noor extraction/classification:

- immutable text version:
  `56d4b532-1f8d-49c1-b2f4-1dc87fec7961`;
- extraction finalization:
  `ce987791-0cc8-4688-99da-28a4a0b29a61`;
- evidence: `36e7a36b-7dd5-4d14-badf-97597bbce85f`;
- facts: `74aaf075-fe51-4b9c-839e-ee66597c47ff`;
- classification job:
  `057f5dbd-fac3-46cb-abfc-1bc0ad5f086c`;
- classification run:
  `a48f3779-3abc-41fb-bec1-92c36ff24587`;
- job status: completed, one attempt, no retry/dead letter;
- run status: `classified_multi`;
- exact document version:
  `5608a4ef-87d2-49d8-9c7a-9ec5666a92ef`;
- classifier/taxonomy:
  `classifier.deterministic_v1.2` /
  `taxonomy_v1.1.0`.

Protected production deltas remained zero:

- Job linkage;
- lifecycle events;
- ranking evaluations;
- outbound events;
- sender acknowledgment;
- intake admission.

## Durable scan schema and authority

Primary table: `inbound_attachment_scan_decisions`.

Persisted authority fields:

- decision ID and attempt sequence;
- tenant;
- inbound ID;
- intake document/attachment ID and ordinal;
- content SHA-256;
- scanner policy version;
- exact state;
- scanner engine;
- scanner software version;
- signature/database version;
- scan started and completed timestamps;
- result and failure reason;
- quarantine object reference;
- actor/service identity;
- prior clean decision reference when reuse is allowed;
- durable scanner evidence.

Exact durable states:

- `pending_scan`;
- `clean`;
- `infected`;
- `scan_failed`;
- `quarantined`.

Authority rules:

1. Receipt stores the source in quarantine and creates no candidate/application.
2. Validation may enqueue scanning but cannot assert clean.
3. Every scan first appends `pending_scan`.
4. A terminal durable decision is appended after the scanner result and static
   safety checks.
5. Scanner unavailable, timeout, malformed response, or ambiguous response records
   `scan_failed` and raises a retryable failure.
6. Malware records `infected`.
7. Unsupported/corrupt/unsafe content records `quarantined`.
8. Only the latest complete decision for the exact tenant, attachment ID, content
   hash, and `inbound-cv-scan-v1` policy can authorize identity extraction.
9. The CV extraction job rechecks durable scan and identity binding authority; the
   legacy `safety_state='clean'` column alone is insufficient.
10. Infected, failed, quarantined, or missing decisions cannot enqueue identity,
    candidate preparation, CV extraction, OCR, embedding, or classification.

Clean-result reuse is allowed only when all are true:

- same tenant;
- exact content SHA-256;
- same scanner policy version;
- completed clean result;
- decision falls inside
  `WATHEFNI_INTAKE_SCAN_REUSE_HOURS` (default 168 hours).

The new decision records `reused_from_decision_id`; the prior decision is not
rewritten.

Authority records are append-only. A scoped database session setting permits only
explicit synthetic qualification cleanup.

## Identity resolution contract

Tables:

- `inbound_cv_identity_extractions`;
- `inbound_cv_identity_resolutions`;
- `inbound_cv_identity_reviews`;
- `inbound_cv_identity_events`;
- `candidate_identity_keys`;
- `candidate_classification_run_invalidations`.

The sequence is:

1. require the exact durable clean decision;
2. run canonical native extraction or canonical OCR/rescue against the quarantined
   file;
3. persist extraction method, text hash, identity evidence, and document evidence;
4. normalize CV email, CV phone, and full name;
5. search only candidate/application rows inside the routed tenant;
6. consider exact candidate fields, CV-owned identity keys, and HR-confirmed keys;
7. store sender email only as `sender_email_provenance`;
8. append one resolution and one event;
9. enqueue accepted preparation only for
   `safe_exact_reuse` or `new_candidate` with ownership confirmed;
10. create an open identity-review record for weak, unclear, or conflicting
    evidence.

### Merge/reuse decision table

| Evidence | Outcome | Automatic attachment |
| --- | --- | --- |
| Exact tenant-scoped CV email, non-conflicting identity | Safe exact reuse | Yes |
| Exact tenant-scoped CV phone, non-conflicting identity | Safe exact reuse | Yes |
| Active HR-confirmed stable identity key | Safe exact reuse | Yes |
| Exact email and phone resolve to different candidates | Conflict | No |
| Exact strong key but CV name/email/phone conflicts with candidate | Conflict | No |
| Exact/similar name only | Possible match / review required | No |
| Partial or weak phone only | Possible match / review required | No |
| Sender email only | Ignored for identity; provenance only | No reuse |
| No tenant-scoped match | New held candidate | Yes, after full authority |
| Same key exists only in another tenant | New held candidate in routed tenant | No cross-tenant reuse |
| Unclear/failed identity extraction | Possible match / review required | No |
| Duplicate attachment hash | Idempotent duplicate / bounded clean-scan reuse | No duplicate version |

Name comparison strips generic filename terms such as `CV`, `resume`, `updated`,
and `v2`. Disjoint person-name tokens on an otherwise exact email/phone match are
treated as a conflict. This is what makes the staged Noor-like case fail closed
while allowing an existing candidate's legitimate `v2` CV.

## Conflict handling

For `possible_match` or `conflict`:

- no candidate or application is created or reused;
- no candidate document is inserted;
- no file-registry current marker changes;
- no prior document is superseded;
- no CV extraction, embedding, or classification job is enqueued;
- the quarantined source remains referenced by the intake document;
- an append-only identity event and open held review record capture candidate
  matches, reason codes, and evidence;
- HR may later resolve the held record under a separately authorized action.

## Document-current boundary

Accepted preparation now creates a governed candidate document as
`latest=false`.

The application stores it as `cv_pending`, not `cv`. The prior current document,
file-registry marker, and application `raw_json.cv` remain unchanged.

The candidate-specific CV extraction stage verifies again:

- exact clean scan authority;
- accepted identity outcome;
- selected candidate phone;
- selected application key;
- content SHA-256;
- confirmed ownership.

Only after canonical extraction succeeds does the existing atomic finalization:

- promote the new document to `latest=true`;
- set the prior document to `latest=false` with `superseded_at`;
- move `cv_pending` to the application current CV projection;
- materialize current evidence/facts.

If extraction fails or authority is missing, the pending document cannot become
current and the prior version remains current.

## Noor/Esraa governed correction plan

**Not executed.** Production does not yet contain the qualified authority.

After exact production-dark promotion, with automatic enqueue and all workers
still OFF:

1. Take a database backup and content-hash all three retained source files.
2. Lock the Esraa candidate, application, three document rows, file-registry rows,
   text versions, evidence, facts, job, and run in one correction transaction.
3. Materialize a durable legacy intake submission/document for Noor's retained
   inbound and copy—not move—the source file into quarantine.
4. Record `scan_failed` with reason
   `historical_scan_authority_missing`. Do not manufacture a historical clean
   result.
5. Persist Noor's already extracted identity as retained evidence and append an
   `identity_conflict` resolution/review referencing:
   - sender provenance;
   - Noor's extracted name/email;
   - Esraa's incorrectly selected candidate/application;
   - original document, text, evidence, facts, job, and run IDs.
6. Move Noor's authority to that isolated held identity-review record. Do not
   create a Noor candidate from an historically unproven scan. A future candidate
   may be created only after a new clean scan or an explicitly governed rescan.
7. Restore Esraa's July CV as current:
   - document `71a889fd-7e45-4825-bd2e-da15d00888ba`;
   - file SHA
     `b137161b0cc92d9402a0e3d27e50c9bbc03898c84af3c04bbc0650169b48e36b`;
   - text version `44cfbc94-9220-4d11-8af7-fd7823376079`;
   - extraction finalization
     `d74fe502-b83e-4965-b948-f2bcd847af42`;
   - evidence `bfc07d74-a8fb-4de6-b2ae-0b0760c82645`;
   - facts `b13833b8-af95-4c90-9576-c610c9dd1eea`.
8. Keep the June document
   `d47f6c3f-eb02-4e64-8443-10d1e497e418`
   historical and preserved.
9. Mark Noor's misbound document/text/evidence/facts non-current and
   `invalidated_identity_misbinding`; do not delete or rewrite their source
   evidence.
10. Restore Esraa's application current CV and candidate profile projection from
    the July evidence/facts snapshot.
11. Append a `candidate_classification_run_invalidations` record for run
    `a48f3779-3abc-41fb-bec1-92c36ff24587` with reason
    `identity_misbinding`. Keep the original completed run, suggestions, and job
    immutable.
12. Assert exactly one Esraa current document/text/evidence/facts chain, Noor held
    in review, and zero Job/lifecycle/ranking/outbound/intake-admit deltas.
13. Commit only if every assertion passes; otherwise roll back the correction
    transaction and preserve the current failure evidence.

No source file, import row, extraction row, job, run, suggestion, or audit event is
deleted by this plan.

## Qualification

### Local isolated matrix

Artifact:

`wathefni-orchestrator/qualify-inbound-cv-scan-identity-authority.py`

Result: **PASS**.

- exact schema and five scan states: PASS;
- full scan/identity matrix: PASS;
- protected mutation baseline/delta: all zero;
- zero synthetic residue: PASS.

Evidence:

`/tmp/inbound-authority-local-qualification.json`

### Staging isolated matrix

Evidence root:

`/opt/wathefni/staging/staging-evidence/inbound-cv-authority-remediation/20260726T023124Z`

| Scenario | Local | Staging | Result |
| --- | --- | --- | --- |
| Candidate sends own CV | PASS | PASS | New held candidate decision |
| HR forwards candidate CV | PASS | PASS | CV identity used; sender provenance only |
| Recruiter sends several candidates | PASS | PASS | Three distinct identities |
| Same sender sends different people | PASS | PASS | No sender-based merge |
| Legacy Gmail/mailbox live sync | PASS | PASS | Fails closed before provider fetch or mutation |
| Exact CV email match | PASS | PASS | Safe exact reuse |
| Exact CV phone match | PASS | PASS | Safe exact reuse |
| Name-only match | PASS | PASS | Held review; no auto-merge |
| Conflicting name/email | PASS | PASS | Conflict; no attachment |
| Noor-like conflicting CV | PASS | PASS end-to-end | No candidate document/current mutation |
| Duplicate attachment resend | PASS | PASS | Message/hash idempotency and bounded scan reuse |
| Existing candidate, legitimate newer CV | PASS | PASS end-to-end | Prior version remains current until extraction; then preserved/superseded |
| Scanned CV | Authority simulation PASS | Real staging PASS | `mistral-ocr-4-0+cache`; identity extracted |
| Malware clean | PASS | Real ClamAV PASS | Durable `clean` |
| Malware infected | PASS | Real ClamAV durable PASS | `infected`; zero extraction |
| Scanner unavailable | PASS | PASS | Durable `scan_failed` |
| Missing scan result | PASS | PASS | Not authorized |
| Scan timeout | PASS | PASS | Durable `scan_failed` |
| Malformed scanner result | PASS | PASS | Durable `scan_failed` |
| Cross-tenant same email/phone | PASS | PASS | No cross-tenant reuse |
| Unclear CV | PASS | PASS | Held review |
| Classification before authority | PASS | PASS | Zero classification jobs |
| Job/lifecycle/ranking/outbound/intake-admit | PASS | PASS | Zero deltas |
| Worker posture | PASS | PASS | Service workers OFF |
| Synthetic cleanup | PASS | PASS | Zero residue |

Real staging scanner:

- engine: ClamAV;
- scanner version: `ClamAV 1.5.3`;
- signature database:
  `ClamAV 1.5.3/28071/Sat Jul 25 06:24:03 2026`;
- health: `PONG`, valid primary pool;
- clean source: `clean`;
- EICAR source: `infected`, `malware_detected`;
- infected identity-extraction count: `0`.

Real scanned-CV staging proof:

- durable receipt: PASS;
- durable real ClamAV decision: `clean`;
- extraction: `mistral-ocr-4-0+cache`;
- extracted name: `Scanned Authority Candidate`;
- extracted email: `scanned.authority@example.test`;
- extracted phone: `96550007788`;
- sender: `recruiter@example.test`, provenance only;
- outcome: `new_candidate`;
- candidates/applications/classification jobs before preparation: `0`;
- zero residue: PASS.

Staging end-to-end smoke also proved:

- receipt creates no candidate synchronously;
- only clean sources reach identity;
- a new document is non-current before extraction;
- canonical extraction promotes it;
- a legitimate newer CV inserts a second immutable row;
- the prior row remains current until new extraction succeeds;
- the new row becomes current and prior row is auditably superseded;
- a Noor-like name/email conflict produces no accepted-preparation job;
- the conflict document has no candidate application/document binding;
- sender/candidate outreach count remains zero.

The final staging posture audit found a stale owner-manual monitor process and
`WATHEFNI_INBOUND_EMAIL=on` left from an earlier staging session. Its retained log
showed no inbound processing after startup. The monitor was stopped, inbound was
set OFF, the orchestrator was restarted, and the prior worker-posture assertion
was discarded. Final requalification at `2026-07-26T03:15:49Z` proved:

- direct legacy mailbox imports without governed identity return
  `durable_scan_and_identity_authority_required`;
- live mailbox sync creates no import batch, candidate, application, document, or
  cursor change;
- Gmail transport parsing, attachment filtering, token hygiene, and label access
  remain green independently of the blocked live mutation path;
- mailbox sync and Gmail adapter smoke tests pass;
- authority cleanup again leaves zero synthetic residue;
- the systemd staging intake worker remains inactive/disabled;
- no owner-manual monitor process exists before or after the run;
- staging inbound remains OFF.

## Frozen regressions

All run against the remediated staging app with classification automatic enqueue
and workers OFF:

- classification units: **18/18 PASS**;
- held communication authority: **14/14 PASS**;
- combined Python units: **32 tests PASS**;
- Candidates C0/C1: **44/44 PASS**;
- optional-module boundary: **301/301 PASS**;
- Assistant A0-A3: **79/79 PASS**;
- canonical recruiting lifecycle: **78/78 PASS**;
- Complete Classification UI staging pack: **47/47 PASS**;
- Unified Candidates staging pack: **50/50 PASS**;
- dashboard Vitest: **13 files / 60 tests PASS**;
- local and staging authority zero-residue audits: **PASS**.
- legacy mailbox fail-closed smoke: **PASS**;
- Gmail adapter/fail-closed smoke: **PASS**.

No classification, taxonomy, Unified Candidates UX, Job, lifecycle, ranking, or
outreach regression was observed.

## Changed-file allowlist

Runtime authority:

- `wathefni-orchestrator/app.py`
  - imports/creates authority schema;
  - inserts the identity stage between clean scan and accepted preparation;
  - requires accepted identity binding;
  - gates candidate CV current promotion;
  - rejects ungoverned email imports and blocks legacy live mailbox sync.
- `wathefni-orchestrator/durable_email_ingress.py`
  - adds `cv_identity_resolution`;
  - persists exact scan decisions;
  - maps clean/infected/failed/quarantined outcomes;
  - enqueues identity instead of candidate preparation.
- `wathefni-orchestrator/inbound_cv_authority.py`
  - new scan schema/authority;
  - new identity schema/contract;
  - append-only reviews/events/invalidation ledger.

Qualification/test-only:

- `wathefni-orchestrator/smoke-test-inbound-email.py`;
- `wathefni-orchestrator/smoke-test-mailbox-sync.py`;
- `wathefni-orchestrator/smoke-test-mailbox-gmail.py`;
- `wathefni-orchestrator/qualify-inbound-cv-scan-identity-authority.py`;
- `wathefni-orchestrator/ops/qualify-staging-scanned-cv-authority.py`;
- `wathefni-orchestrator/ops/patch-staging-app-inbound-cv-authority.py`;
- `wathefni-orchestrator/local-qualify-durable-email-ingress.py`;
- this report.

No dashboard, classification, taxonomy, Unified Candidates route/component, Job,
lifecycle, ranking, outreach, or Role Profile file changed for this remediation.

Because the working tree contains pre-existing unrelated changes, do **not** deploy
the local `app.py` wholesale. Apply
`patch-staging-app-inbound-cv-authority.py` to the exact target environment app and
verify the marker and compiled artifact.

## Artifact identities

Source revision:

`40a4e2621f4818bf7c0f6ce3642032297bfbe7b2`

Qualified staging files:

- staged `app.py`:
  `7e7caf5f7bfb9e98a74c33e7267af34119fc4b93959bb7e871d69e55371fecd4`;
- `durable_email_ingress.py`:
  `0257f8fb4ebc5bc70e33b2775ae7338f1a06b67f1cdceea18042365f54d0ab66`;
- `inbound_cv_authority.py`:
  `8e1b843f211c73a2c917e514d9caa9da05b52a5d96eda6d31e2bcb57d5affd92`;
- `smoke-test-inbound-email.py`:
  `5d7d0de4ce0017c8da5b4b98f76e87563c429aac0119fdbad7a2f590f3ca167e`;
- authority matrix:
  `2e7eeaa6d06d76b3a481832018bac1084ff651ba1f2bce638aeae5b8d9f0b925`;
- mailbox fail-closed smoke:
  `ae4dfc6e6a794eb912da36d2886cadce470e34bd59494c0f11cdf096d2fe131f`;
- Gmail adapter/fail-closed smoke:
  `0524bc7731ff6e754a024501cb7ab7bd34880a89b6759b206fb08a0916a125c0`;
- scanned-CV qualifier:
  `58d94b61044c0c081a28d82db493feefce9c977279d2d3027156e2964e118559`.

Combined qualified staging authority artifact:

`799862e50d55ecb74abb1ee02849e06ab445821e81586d90223229f87411512c`

Staging backup:

`/opt/wathefni/backups/staging-pre-inbound-cv-authority-20260726T023124Z`

## Rollback

Staging rollback:

1. stop/disable the staging intake worker;
2. restore `app.py` and prior ingress modules from the staging backup above;
3. restart and health-check the staging orchestrator;
4. leave additive authority tables in place;
5. do not delete retained scan/identity audit records.

Production promotion rollback, when separately authorized, must:

- disable automatic enqueue first;
- disable/reset the bounded worker and timer;
- restore the exact pre-promotion app/modules;
- restart and health-check production;
- preserve additive schema and all Noor/Esraa audit evidence;
- perform no candidate cleanup.

## Residual risks and gates

1. Production still runs the legacy artifact. The remediated authority is not
   active there.
2. The retained Noor source has no historical durable clean scan. The correction
   must record that truth and hold it for review, not manufacture a clean result.
3. The Noor/Esraa correction has not been executed. Esraa's production current CV
   still points to Noor until the separately guarded correction transaction runs.
4. The append-only run invalidation table exists only in local/staging. Production
   run `a48f...` is not yet invalidated.
5. Production-dark promotion must confirm the real production quarantine backend,
   ClamAV health/signature version, service identity, retention window, and durable
   journey visibility before any rearm.
6. The first production rearm must remain `WATHEFNI`-only, start-time bounded,
   no historical backfill, and owner-operated.
7. Legacy live Gmail/mailbox sync is intentionally unavailable until it is routed
   through the same durable receipt, scan, and identity stages. It must not be
   re-enabled by bypassing the fail-closed gate.

## Stop state

- Local qualification: complete and green.
- Staging deployment/qualification: complete and green.
- Production automation: OFF.
- Production bounded worker/timer: inactive/disabled.
- External tenant automation: not enabled.
- Noor/Esraa retained evidence: not cleaned.
- Noor/Esraa correction: planned, not executed.
- Production canary rearm: **NO-GO pending production-dark promotion and governed
  correction**.
