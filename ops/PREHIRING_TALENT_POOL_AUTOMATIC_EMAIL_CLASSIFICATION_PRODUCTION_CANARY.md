# Talent Pool Automatic Email Classification — Production Canary Readiness

Date: 2026-07-26  
Environment: production  
Tenant: `WATHEFNI` only  
Evidence root: `/opt/wathefni/production-evidence/talent-pool-auto-email-canary/20260726T012324Z`

## Verdict and stop point

**NO-GO — the first owner-operated automatic journey completed technically but failed scan-evidence and candidate-identity authority. Automatic enqueue and the bounded worker are disabled.**

The readable-PDF journey produced an automatic queue claim and classification run without a manual trigger. It cannot be accepted because no durable malware-scan result exists and Noor Tahat's CV was incorrectly attached to Esraa Aziz's existing application.

The worker timer was disabled, the automatic feature was set OFF with an empty automatic tenant allowlist, and all evidence was retained. No production record was cleaned.

Production inbound address confirmed:

`92d69b51cdadf3b594fc08710326ff6b@inbound.postmarkapp.com`

The address is active, belongs to `WATHEFNI`, and has no `position_code`; it therefore creates held Talent Pool intake rather than a Job-bound application.

## Current production state

- Canonical service health: **200**
- Orchestrator: **active**
- Automatic worker timer: **inactive + disabled**
- Automatic worker service: **inactive**
- Automatic feature: OFF
- Automatic tenant allowlist: empty
- Canary boundary: `2026-07-26T01:26:12Z`
- Authorized automatic route: exactly `92d69b51cdadf3b594fc08710326ff6b@inbound.postmarkapp.com`
- External tenant evaluation: disabled
- Generic classification workers: OFF
- Classification master: OFF
- Classification tenant allowlist: exactly `WATHEFNI`
- Classification schema: ON
- Classification manual route: ON
- Classification UI: ON
- Sender acknowledgment: OFF
- Historical backfill: OFF
- Retained automatic jobs: `1` completed
- Retained automatic classification runs: `1`

## Esraa CV version-authority proof

Application:

- `app_key`: `imp-wathefni-06ffffc36d7fd375-WATHEFNI-IMPORT`
- state: `needs_role`
- current step: `import_review`
- Job position: empty

### June CV

- Document ID: `d47f6c3f-eb02-4e64-8443-10d1e497e418`
- Filename: `cv-resume-5.webp`
- Created: `2026-06-01T14:30:21.880442Z`
- Source SHA-256: `e99bd3352bf3ce1c216ab6265fba1f6e6f1c34897e6017f3452771b0d295993d`
- Extraction method: `gpt-5.4-vision`
- Recorded extracted characters: `2462`
- Legacy semantic text hash: `668882bf9f189a902ddca398603913676207a6f5f16d4791c13275da832fd6a8`
- Source file still exists and matches its original hash.
- Document metadata is `latest=false`.
- It was superseded at `2026-07-26T01:04:25Z` by the July document.
- Its legacy profile snapshot, extraction method, character count, source hash, semantic hash, and source file are preserved.

Pre-existing limitation: the June row pointed to the same application-level text path later used by July. The exact June extracted-text file and canonical fact-snapshot row were not historically versioned and cannot be claimed as preserved. The source CV itself was not overwritten or deleted. No historical OCR was rerun to manufacture a replacement snapshot.

An explicit immutable audit version now records this limitation:

- Version ID: `a6a48d35-90e0-4a81-9397-7042a2af5950`
- Status: `legacy_source_preserved_text_unavailable`
- Current: false
- Historical OCR rerun: false
- Historical classification enqueued: false

### July 26 CV

- Document ID: `71a889fd-7e45-4825-bd2e-da15d00888ba`
- Filename: `Esraa Aziz_260724_142430.pdf`
- Created: `2026-07-26T01:03:56.549645Z`
- Source SHA-256: `b137161b0cc92d9402a0e3d27e50c9bbc03898c84af3c04bbc0650169b48e36b`
- Extraction method: `pdftotext`
- Extracted characters: `15611`
- OCR pages: `0`
- Extracted-text hash: `ebd8020c3370bb945c5ebc2c4559c0d00efa612b016cff8476454a7bf39f6d56`
- Extraction finalization ID: `d74fe502-b83e-4965-b948-f2bcd847af42`
- Evidence ID: `bfc07d74-a8fb-4de6-b2ae-0b0760c82645`
- Facts ID: `b13833b8-af95-4c90-9576-c610c9dd1eea`
- Immutable text-version ID: `44cfbc94-9220-4d11-8af7-fd7823376079`
- Current: true

The immutable text content hashes exactly to the canonical extraction evidence. Exactly two CV versions are visible and exactly one is current.

### Profile and HR history

- Governed profile API returns two document-history entries and two registered files.
- Exactly one document is labeled current.
- The production dashboard now renders bilingual `Document history / سجل المستندات` with `Current / الحالي` and `Previous / سابق` markers.
- Esraa has `0` persisted classification runs and `0` classification review events. The previously reported manual UI action did not produce a stored run in the production classification tables.
- No existing HR confirm/reject/add/correct event was changed or deleted.
- Future classification runs use exact `document_version_id` and `extraction_version_id`; review events remain append-only and separate.

## Automatic post-extraction boundary

One integration marker is installed immediately after canonical extraction has:

1. validated and stored the document;
2. completed native extraction or canonical OCR/rescue;
3. materialized canonical extraction finalization;
4. materialized current CV evidence;
5. materialized current deterministic facts;
6. updated current/superseded document authority.

The integration then atomically:

- inserts the exact extracted text in `candidate_cv_text_versions`;
- marks prior text versions superseded;
- creates one `talent_pool_classify_v1` job keyed to the document, extraction finalization, evidence, facts, taxonomy, and classifier versions.

It does not enqueue when:

- the automatic feature is OFF;
- the tenant is not explicitly allowlisted;
- the document is not linked through `import_batch_id` to the exact authorized
  `WATHEFNI` production inbound recipient;
- the document predates `2026-07-26T01:26:12Z`;
- evidence or facts are not current and ready;
- the immutable text hash does not match canonical evidence.

An attempted re-enqueue of Esraa’s current document returned:

`eligible=false, reason=document_before_canary_start`

The queue remained empty after the probe.

The enqueue step is isolated by a database savepoint. If automatic snapshot or
queue creation fails, its partial writes are rolled back to that savepoint,
the failure is logged as `enqueue_failed`, and the already successful canonical
CV extraction transaction is still allowed to commit.

## Worker authority and execution

The worker:

- permits exactly `WATHEFNI`;
- permits only documents proven to originate from the exact authorized
  production email recipient and its durable import batch;
- rechecks that recipient, inbound identity, import batch, held status, and
  empty Job position again when claiming the queue row;
- claims only `talent_pool_classify_v1`;
- claims only `automatic_post_extraction` jobs;
- requires both job and source document timestamps at or after the canary boundary;
- claims one row with `FOR UPDATE ... SKIP LOCKED LIMIT 1`;
- reads the exact immutable text, current evidence, and current fact snapshot;
- verifies the stored text hash before classification;
- persists the run against the exact document and extraction finalization;
- never imports or calls CV extraction, OCR, lifecycle, ranking, outbound, or Job-assignment code.

Retry controls:

- maximum attempts: `3`
- retry delay: `30 seconds`
- retry state: `retrying`
- terminal failure state: `dead_letter`
- monitoring columns: `available_at`, `claimed_at`, `completed_at`, `dead_lettered_at`, `claim_owner`, `max_attempts`

Idempotency:

- queue uniqueness: `(company_code, idempotency_key)`
- run uniqueness: existing immutable classification cache key
- text-version uniqueness: `(company_code, app_key, document_id, source_content_sha256)`
- one current immutable text version per `(company_code, app_key)`

The generic worker flag remains OFF. After the failed first journey, the dedicated bounded email worker and automatic enqueue flag were also disabled. Manual classification and the classification UI remain available for safe owner/HR review.

## Qualification completed before owner email

- Classification units: **18/18 PASS**
- Dashboard tests: **60/60 PASS**
- Dashboard TypeScript + production build: PASS
- Production document-history asset markers: PASS
- Production service health: **200**
- Tenant gate: `WATHEFNI=true`, external tenant=false
- Historical-job gate: **0**
- No-op worker cycles: success
- Current Esraa classifier dry proof from immutable stored artifacts:
  - outcome: `classified_multi`
  - suggestions: `8`
  - OCR triggered by classification: false
  - no run was persisted by this dry proof

Protected state since worker enablement:

- Esraa Job linkage: none
- Esraa lifecycle events: `0`
- Esraa ranking evaluations: `0`
- Esraa outbound events: `0`
- Global lifecycle events since boundary: `0`
- Global ranking evaluations since boundary: `0`
- Global outbound events since boundary: `0`
- Intake-admit event table: absent; no intake-admit mutation was introduced

## First owner-operated automatic journey

No manual classification endpoint was called.

Inbound:

- Inbound ID: `809f5c46-b9eb-41fb-9898-14427946cc90`
- Postmark message ID: `6bc87818-67ed-43f4-be12-ba0d3253acc5`
- Received: `2026-07-26T01:46:28Z`
- Route: exact authorized `WATHEFNI` address
- Attachment: one `application/pdf`, `157235` bytes
- Content SHA-256: `d951c3e27796318075c7c532be45d641e04170e3cd738081efd8ab4d5e2b2934`
- Import batch: `26a1e420-456c-41bc-8c36-7062f4d59305`
- Batch result: one imported, zero duplicate, zero failed, one `needs_role`

Scan gate:

- **UNPROVEN / FAIL**
- Production has no `intake_submissions`, `intake_documents`, or
  `intake_processing_jobs` tables for this path.
- No `scan_result`, scan engine/signature, quarantine decision, file-registry
  scan metadata, or service-log scan event was recorded.
- `validation_status=accepted` and `storage_status=stored` do not prove a
  malware scan occurred.

Identity and application authority:

- **FAILED_UNSAFE_REUSE**
- Imported person: Noor Tahat; CV-extracted email `noortahat3@gmail.com`.
- Reused application/candidate: Esraa Aziz,
  `imp-wathefni-06ffffc36d7fd375-WATHEFNI-IMPORT`, created 2026-06-01.
- The sender email `azizalmulla16@gmail.com` remained the candidate email and
  was used by the import path despite the CV containing a different identity.
- Noor's document became current on Esraa's record and superseded both Esraa
  CV versions. This is retained as failure evidence and was not corrected or
  cleaned.

Document and extraction:

- New document ID: `5608a4ef-87d2-49d8-9c7a-9ec5666a92ef`
- Immutable text version: `56d4b532-1f8d-49c1-b2f4-1dc87fec7961`
- Method: native `pdftotext` / Poppler
- Pages: `2/2`, both accepted locally
- Extracted characters: `8396`
- OCR count: `0`
- Extraction finalization: `ce987791-0cc8-4688-99da-28a4a0b29a61`
- Evidence: `36e7a36b-7dd5-4d14-badf-97597bbce85f`, ready/current
- Facts: `74aaf075-fe51-4b9c-839e-ee66597c47ff`,
  ready/current, confidence `0.8964`

Automatic queue:

- Job ID: `057f5dbd-fac3-46cb-abfc-1bc0ad5f086c`
- Created: `2026-07-26T01:46:55.432234Z`
- Claimed: `2026-07-26T01:47:00.645008Z`
- Completed: `2026-07-26T01:47:00.654378Z`
- Receipt to queue: `27.432234s`
- Queue to claim: `5.212774s`
- Claim to completion: `0.009370s`
- Receipt to classification completion: `32.654378s`
- Attempts: `1`; retries: `0`; dead letters: `0`; error: none

Classification:

- Run ID: `a48f3779-3abc-41fb-bec1-92c36ff24587`
- Status: `classified_multi`
- Taxonomy: `taxonomy_v1.1.0`
- Classifier: `classifier.deterministic_v1.2`
- Exact source document and extraction IDs match the rows above.
- Suggestions: `17`, all active.
- High-confidence nodes: Software Engineering `0.88`, Technology `0.88`,
  Data & AI `0.80`, Cybersecurity `0.80`, Python `0.80`, Excel `0.80`,
  Engineering `0.80`, Computer Science `0.78`.
- Medium-confidence nodes: Arabic, Banking, Oil & Gas, Intern, Junior, AWS,
  English (`0.70` each), AutoCAD and Human Resources (`0.60` each).
- Evidence is persisted per suggestion. Representative evidence includes
  “AI-driven software engineering” for Software Engineering, “Computer
  Science” plus deployed RAG/Python evidence for Technology, “machine
  learning” for Data & AI, and “Cybersecurity & AI Bootcamp” for
  Cybersecurity.
- Some lower-quality matches are visible: “excel” from prose, “energy” mapped
  to Oil & Gas, `cad` mapped to AutoCAD, and `hr` mapped to Human Resources.
  No classifier/taxonomy change was made during observation.

Dashboard/read projection:

- Candidate is visible in Talent Pool search.
- Chip: `Technology · Software Engineering`.
- Classification state: `classified_multi`.
- Server-side `likely_role=role.software_engineer` filter returns the row.
- Profile classification history exposes the run and all 17 suggestions.
- Profile document history exposes three documents, but now mixes Noor's CV
  with Esraa's two CV versions; this is the same identity-authority failure.
- The dashboard row still displays candidate `Esraa Aziz` while its current CV
  is `Noor Tahat - CV.pdf`.

Protected authority:

- Job linkage: none; `position_code` empty; Talent Pool `needs_role`.
- Lifecycle events for the application: `0`.
- Ranking evaluations: `0`.
- Outbound events: `0`.
- Sender acknowledgment/outreach: none.
- Intake admission mutation: none.

Full retained evidence:

`/opt/wathefni/production-evidence/talent-pool-auto-email-canary/20260726T012324Z/journeys/809f5c46-b9eb-41fb-9898-14427946cc90.final.json`

## Remaining owner-operated journeys

Further automatic canary sends are stopped pending remediation. Not run:

- DOCX;
- scanned/image CV requiring OCR;
- existing candidate with a newer CV;
- duplicate resend;
- Arabic or bilingual CV;
- unclear CV.

For each owner email, the installed monitor captures:

- provider inbound identity and timestamps;
- tenant and production route;
- import items and attachment records;
- scan/validation metadata;
- candidate/application resolution;
- document IDs and immutable text versions;
- extraction runs and finalizations;
- OCR trigger count and reason-bearing extraction records;
- queue creation, claim, completion, retry, and dead-letter timestamps;
- end-to-end latency;
- idempotency key and duplicate outcome;
- document, extraction, evidence, facts, and classification run IDs;
- suggestions, evidence, confidence, and state;
- Job, lifecycle, ranking, and outbound counts;
- retained-record state with cleanup explicitly false.

Monitoring command:

`/opt/wathefni/orchestrator/.venv/bin/python /opt/wathefni/production-evidence/talent-pool-auto-email-canary/20260726T012324Z/deployed/monitor-talent-pool-auto-email-production-canary.py once`

No cleanup will occur until the owner confirms manual production testing is complete.

## Rollback

Rollback artifact:

`/opt/wathefni/production-evidence/talent-pool-auto-email-canary/20260726T012324Z/ROLLBACK.sh`

SHA-256:

`1730cd6b9e1768c94e880e2654730f7992095f84135bef903bf74fe73b2e709b`

Rollback:

- disables and removes the bounded timer/service;
- removes automatic enqueue flags;
- restores the pre-canary orchestrator, Unified Candidates route, and dashboard artifact;
- restores or removes the worker module as appropriate;
- restarts and health-checks production;
- intentionally preserves additive schema, immutable evidence, queue/run evidence, and owner records.

It performs no candidate cleanup.

## Artifact identities

Source revision: `40a4e2621f4818bf7c0f6ce3642032297bfbe7b2`

Runtime hashes:

- orchestrator `app.py`: `eb49fbb9a40349812293e57f1e9c660e51641034b15af097e1b91c6d37f90acb`
- Unified Candidates routes: `3e9b68b75530a66d6e67bae05a424924e8928a8da523b4cd910905e6ba381d4b`
- bounded worker module: `f1503ab5216e4977f8aa874cdedc00dc36d5259ad2ae083599425577e95a193e`
- disabled worker service: `955f671b8282d9245c59a1f7545adbdcc24143fbdce8b603ae7a6e88ed8c256c`
- worker timer: `8fc24a9314d1dc55d70e7eff23f8529f2d3929af2b0932c93b633143a3bce9fc`
- disabled automatic-enqueue drop-in: `0ff2c769491c4f64660c1bcba046ae9d217807b6e7fdae59c3ac6ee1c0c3578a`
- document-history UI source: `e6d5223bd04f54f67268019879ea6c4d5689a4df7169c2c18bb45d2a4dbed323`
- dashboard asset-tree: `b6c8d7e9a8fe72d11537f2d6d642ae013657637101ce752514b0c1fd21c615db`
- monitor: `a21c27fbc54cf996b0464fc601bee4b9d438fa08e17836935c7d1144dfa19dd0`
- preparation artifact: `d2ece74a482ec0ebb4b46e13151ee0282c1e3b8aadfad94bfe2b7676d963ff4d`

Armed production canary composite identity:

`6b7cfdd108420ddcf5a8a814e6717d37a0deaa334bbf538daca8c4b9242b2643`

Post-failure safe-state composite identity:

`2f6addcc1dac9ad0ec85a5a612169428af31285b8aedc4f4ca57e7ea13d2aa55`

## Retained-record statement

This phase intentionally retained:

- Esraa’s two source document rows;
- two explicit immutable/audit text-version authority rows;
- current canonical extraction, evidence, and facts rows;
- all existing import, file-registry, and profile records;
- production evidence, monitoring state, and rollback artifacts.

The first owner email created and retained one new document/text/evidence/facts version, one completed automatic job, one classification run, and 17 suggestions. It created no Job linkage, lifecycle event, ranking evaluation, outbound event, intake admission, or sender acknowledgment.

The system is stopped in the safe failure posture. Do not send another automatic canary email until scan evidence and candidate identity resolution are remediated and requalified.
