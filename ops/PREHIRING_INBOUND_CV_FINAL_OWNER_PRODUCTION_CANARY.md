# Pre-Hiring Inbound CV Final Owner Production Canary

Date: 2026-07-26  
Tenant: `WATHEFNI`  
Environment: production  
Canary start boundary: `2026-07-26T15:24:39Z`  
Exact recipient:
`92d69b51cdadf3b594fc08710326ff6b@inbound.postmarkapp.com`

## Verdict

**GO — freeze the inbound Talent Pool automation phase.**

The single owner-operated production email completed the approved journey:

- one durable inbound message;
- one PDF attachment;
- durable `clean` ClamAV decision;
- CV-derived candidate identity with the sender retained only as provenance;
- safe creation of one held candidate with confirmed document ownership;
- one immutable current CV text version;
- canonical `pdftotext` extraction with no OCR;
- one automatically enqueued and owner-invoked classification job;
- one evidence-backed classification run;
- correct Talent Pool row projection, filter match, chip, and profile projection;
- no Job, lifecycle, ranking, interview, outbound, or sender-acknowledgment
  mutation;
- no unrelated queue claim.

Automatic inbound intake and automatic email classification were disabled
immediately after the journey. The owner record and all evidence remain intact.

## Sealed evidence

Production evidence root:

`/opt/wathefni/production-evidence/final-owner-canary/20260726T152439Z`

Primary evidence:

- `armed-posture.json`
- `post-send-preclaim.json`
- `after-step-01-validation.json`
- `after-step-02-scan.json`
- `after-step-03-identity.json`
- `after-step-04-prepare.json`
- `after-step-05-extraction.json`
- `before-step-06-classification.json`
- `after-step-06-classification.json`
- `final-canary-proof.json`
- `final-canary-proof-summary.json`
- `final-leave-state.json`
- `kill-switch.out`
- `evidence-manifest.sha256`

No owner record or source object was cleaned.

## Runtime and initial authority

- Health before arming: `200`
- Dashboard before arming: `200`
- Runtime composite SHA-256:
  `7cdb2c4de06b92f5da9a1a25c17c6ce2b278267780e1f6f82777c638eecfe9ce`
- Active retention policy: `inbound-retention-ops-v1`
- Pre-existing eligible intake jobs: `0`
- Pre-existing eligible classification jobs: `0`
- Pre-existing inbound messages after the start boundary: `0`
- Exact active tenant: `WATHEFNI`
- Exact recipient: the recipient recorded above

The runtime composite remained identical after the canary.

## Flag and control timeline

- `2026-07-26T15:24:39Z`: exact UTC canary boundary recorded.
- `2026-07-26T15:26:41.760445Z`: canary posture verified armed.
- `2026-07-26T15:37:11.751887Z`: the one owner message became durable.
- `2026-07-26T15:40:34Z`: the pre-existing
  `wathefni-prehire-cv-process.timer` was paused to prevent a race with the
  owner-operated one-shot extraction path.
- `2026-07-26T15:42:50.111589Z`: intake validation completed.
- `2026-07-26T15:43:01.181785Z`: durable clean scan completed.
- `2026-07-26T15:43:14.898540Z`: identity decision and ownership confirmation
  recorded.
- `2026-07-26T15:44:18.751140Z`: held candidate preparation completed.
- `2026-07-26T15:44:33.619155Z`: canonical extraction completed.
- `2026-07-26T15:44:33.602999Z`: bounded automatic classification enqueue
  recorded in the job payload.
- `2026-07-26T15:45:37.623276Z`: the one classification job was claimed.
- `2026-07-26T15:45:37.720857Z`: classification journey completed.
- `2026-07-26T15:46:04Z`: kill switch started.
- `2026-07-26T15:46:07Z`: kill switch completed; health remained `200`.

Armed flags were:

- `WATHEFNI_INBOUND_EMAIL=on`
- `WATHEFNI_INTAKE_TENANT_CONCURRENCY=1`
- `WATHEFNI_TALENT_POOL_AUTO_EMAIL_CLASSIFICATION=on`
- `WATHEFNI_TALENT_POOL_AUTO_EMAIL_CLASSIFICATION_TENANTS=WATHEFNI`
- `WATHEFNI_TALENT_POOL_AUTO_EMAIL_CLASSIFICATION_STARTED_AT=2026-07-26T15:24:39Z`
- `WATHEFNI_TALENT_POOL_AUTO_EMAIL_CLASSIFICATION_RECIPIENT=<exact recipient>`
- `WATHEFNI_TALENT_POOL_AUTO_EMAIL_CLASSIFICATION_MAX_ATTEMPTS=1`

The following stayed off throughout:

- sender acknowledgment;
- generic classification workers;
- retention cleanup;
- Gmail/mailbox live synchronization;
- external tenants;
- historical backfill.

## One-shot runner note

The initially prepared intake runner called the approved
`/orchestrator/debug/intake-worker/run?limit=1` path. Production returned `404`;
the route is not present in the deployed `app.py`. The failed call claimed no
job and changed no database state.

The evidence-local one-shot runner was corrected to invoke the existing
production function `app.run_durable_email_ingress_worker(limit=1)` directly.
This used the same production claim and handler authority, retained one-job
concurrency, and was guarded before and after every invocation. No production
runtime source file was changed.

Disposition: **operator harness correction; not a product-authority failure**.

## Durable inbound receipt

- Inbound ID: `66fa2013-b5cb-53d5-9f00-847bc9c47f32`
- Provider message ID: `77d55ef9-5972-477a-b42d-62408c936043`
- Submission ID: `7ab1f2dc-c1b7-5266-869b-c211adf96f50`
- Intake document ID: `7305943e-01c7-5455-96f4-c85942ce4e21`
- Attachment ordinal: `1`
- Filename: `Yasser_Al_Dossary_CV_Test.pdf`
- MIME type: `application/pdf`
- Size: `50,329` bytes
- Content SHA-256:
  `36eca4bf7229da1b11b37b6d2562a78ab6aca206e667fa0ea53fbd53f70595a3`
- Storage state: `stored`
- Duplicate-of document: none

Exactly one post-boundary message, one submission, and one document existed.
There was no duplicate anomaly.

## Malware scan proof

- Decision ID: `e6fe4d49-715f-4d60-9db8-b95b53a067d6`
- Policy: `inbound-cv-scan-v1`
- State/result: `clean` / `clean`
- Engine: `clamav`
- Engine version: `ClamAV 1.5.3`
- Signature evidence:
  `ClamAV 1.5.3/28073/Sun Jul 26 06:25:14 2026`
- Scanner transport: TCP `127.0.0.1:3311`
- Scanner response: `stream: OK`
- Bytes scanned: `50,329`
- PDF pages: `2`
- Service identity: `wathefni-orchestrator-production`
- Reused decision: none
- Quarantine reference:
  `WATHEFNI/66fa2013-b5cb-53d5-9f00-847bc9c47f32/0001/36eca4bf7229da1b11b37b6d2562a78ab6aca206e667fa0ea53fbd53f70595a3.bin`

The hash in the scan decision matches the durable intake document and the
canonical source version.

## Identity and ownership proof

Identity was extracted from the CV:

- Full name: `Yasser Al Dossary`
- Email: `yasser.aldossary@example.com`
- Phone: `96555501842`
- Extraction method: `pdftotext`
- Extraction status: `completed`
- Identity extraction ID: `4aa850dd-bbf6-41ad-97a1-2740fbfbda4b`

Sender provenance:

- Envelope sender: `azizalmulla16@gmail.com`
- Resolution `sender_email_provenance`: `azizalmulla16@gmail.com`
- Candidate email used by identity authority:
  `yasser.aldossary@example.com`

The sender and candidate identity are different, proving the sender was not
used as the candidate identity.

Resolution:

- Resolution ID: `d4f106a3-ceed-40ba-8dcc-16128b281e8a`
- Outcome: `new_candidate`
- Confidence: `0.95000`
- Reason: `no_tenant_scoped_identity_match`
- Selected application:
  `imp-wathefni-837eb9b1bf14506b-WATHEFNI-IMPORT`
- Ownership confirmed: `true`
- Identity review/conflict: none

## Held Talent Pool and document-version proof

Application:

- App key: `imp-wathefni-837eb9b1bf14506b-WATHEFNI-IMPORT`
- Company: `WATHEFNI`
- Status: `needs_role`
- Current step: `import_review`
- Position code: empty
- Held: `true`
- Auto-admitted: `false`
- Admit reason: none
- Job binding: none

Candidate document:

- Document ID: `46c4c057-7962-4825-8c88-35332cbb3ffc`
- Ownership app key: the app key above
- Intake document ID: `7305943e-01c7-5455-96f4-c85942ce4e21`
- Identity resolution ID: `d4f106a3-ceed-40ba-8dcc-16128b281e8a`
- Extraction status: `ok`
- Current/latest: `true`

Immutable current text version:

- Version ID: `c36c0291-ceec-4697-91d8-02e4c108d5b5`
- Status: `ready`
- Current: `true`
- Source hash:
  `36eca4bf7229da1b11b37b6d2562a78ab6aca206e667fa0ea53fbd53f70595a3`
- Extracted text hash:
  `8c4ce7781bf7a840aca88009f6ff639b81012f852ea51ed7f5ec30c5730d2136`
- Finalization ID: `0b37ab57-80e9-492b-a944-4492de84f068`
- Evidence ID: `d11dd42e-56ba-4e7c-b228-ee9051b5beed`
- Facts ID: `7ad7eefe-0e8f-4e6b-8fd9-0b8f324776b5`

## Extraction and OCR decision

- Canonical method: `pdftotext`
- Pages: `2`
- Pages requiring OCR: `0`
- OCR triggered by extraction: `false`
- OCR triggered by classification: `false`
- Extracted text status: `ready`

OCR was not required and was not run.

## Automatic queue timing and isolation

The exact intake sequence contained five jobs:

1. `intake_validation`
   - Job: `176d22b2-0a47-496b-a87e-475dc152fc56`
   - Created: `2026-07-26T15:37:11.751887Z`
   - Completed: `2026-07-26T15:42:50.111589Z`
2. `file_safety_scan`
   - Job: `2e413f40-9f29-40a8-a504-20ab3eecec95`
   - Created: `2026-07-26T15:42:50.107571Z`
   - Completed: `2026-07-26T15:43:01.676905Z`
3. `cv_identity_resolution`
   - Job: `2efaa588-a43b-4c6b-a362-4432a472fcfd`
   - Created: `2026-07-26T15:43:01.181785Z`
   - Completed: `2026-07-26T15:43:15.011420Z`
4. `accepted_intake_preparation`
   - Job: `82c43739-1651-4bdc-a846-120781ae7fa5`
   - Created: `2026-07-26T15:43:14.898540Z`
   - Completed: `2026-07-26T15:44:18.751140Z`
5. `cv_extraction`
   - Job: `6bab3991-c47f-4194-85cf-4a67951b3603`
   - Created: `2026-07-26T15:44:18.708461Z`
   - Completed: `2026-07-26T15:44:33.619155Z`

Each job:

- belonged to `WATHEFNI`;
- belonged to this canary chain;
- was processed once;
- completed successfully;
- was guarded before and after its claim.

There were no older active jobs before the first claim, no second active job at
any guard boundary, and no active intake job after extraction.

## Automatic classification proof

The classification job was created by canonical extraction without a manual
classification action:

- Job ID: `4aa1834d-d301-497b-a66e-c0be0725abd7`
- Source: `automatic_post_extraction`
- Tenant: `WATHEFNI`
- App key: the canary app key
- Exact authorized recipient: the canary recipient
- Exact canary start: `2026-07-26T15:24:39Z`
- Max attempts: `1`
- Attempt count: `1`
- Dead letter: `false`
- OCR triggered: `false`
- Status: `completed`

Result:

- Run ID: `8d00dbc2-95e5-423b-a3fd-b875dbf1b652`
- Status: `classified_multi`
- Taxonomy: `taxonomy_v1.1.0`
- Classifier: `classifier.deterministic_v1.2`
- Suggestions: `16`
- High confidence: `9`
- Medium confidence: `7`
- Invalidations: `0`

Every suggestion is active and contains source evidence. The effective labels
include Technology, Engineering, Software Engineering, Data and AI,
Cybersecurity, IT Support, Python, SQL, Computer Science, AWS, English, Arabic,
Intern, and Junior.

## Dashboard proof

The production read model was evaluated after the run:

- Talent Pool row app key:
  `imp-wathefni-837eb9b1bf14506b-WATHEFNI-IMPORT`
- Classification state: `classified_multi`
- Row chip: `Technology · Software Engineering`
- Effective node IDs: present
- Current profile run:
  `8d00dbc2-95e5-423b-a3fd-b875dbf1b652`
- Profile suggestions: evidence-backed effective suggestions present
- Job assignment: `null`
- Hiring score: `null`
- Role Profile score: `null`

Server-side filter proof:

- Filter node: `cert.aws`
- Authority: `either`
- Matched app keys: exactly the canary app key

The row projection, filter predicate, chip, and profile projection all resolve
from the same current run.

## Mutation deltas

Expected canary deltas:

- inbound messages: `+1`
- intake submissions: `+1`
- intake documents: `+1`
- completed intake jobs: `+5`
- held applications: `+1`
- candidate documents: `+1`
- current immutable CV versions: `+1`
- classification jobs: `+1`
- classification runs: `+1`
- classification suggestions: `+16`

Forbidden canary-app deltas:

- Job link: `0`
- lifecycle events: `0`
- ranking evaluations: `0`
- interviews: `0`
- outbound delivery events: `0`
- sender-acknowledgment jobs: `0`
- automatic intake admission: `0`

No active intake or classification jobs remained.

## Kill-switch proof

The prepared kill switch ran immediately after the classification result:

- Started: `2026-07-26T15:46:04Z`
- Completed: `2026-07-26T15:46:07Z`
- Result: `KILL_SWITCH_OK health=200`

Both configured environment and active process environment now show:

- `WATHEFNI_INBOUND_EMAIL=off`
- `WATHEFNI_TALENT_POOL_AUTO_EMAIL_CLASSIFICATION=off`
- `WATHEFNI_TALENT_POOL_AUTO_EMAIL_CLASSIFICATION_TENANTS=` empty
- `WATHEFNI_SENDER_ACKNOWLEDGMENT=off`
- `WATHEFNI_TALENT_POOL_CLASSIFICATION_WORKERS=off`
- `WATHEFNI_INTAKE_RETENTION_CLEANUP=off`

The start timestamp, exact recipient, max-attempt value, and concurrency value
remain as inert audit/configuration metadata; both enabling flags are off and
the classification tenant allowlist is empty.

## Final leave-state

- Production health: `200`
- Runtime composite: unchanged
- Retention policy: `inbound-retention-ops-v1`
- Orchestrator: active
- Automatic inbound email: off
- Automatic email classification: off
- Classification tenant allowlist: empty
- Generic classification workers: off
- Inbound worker service: inactive
- Inbound timer: inactive
- Pre-hire CV timer: inactive; unit remains enabled but was not restarted
- Gmail/mailbox live sync: off
- Sender acknowledgment: off
- Retention cleanup: off
- External tenants: not enabled
- Historical backfill: not run
- Active intake jobs: `0`
- Active classification jobs: `0`
- Owner canary record count: `1`
- Owner record cleanup: not run

## Residual operational note

Before any future operator-run canary, update the documented one-shot command:
the deployed production runtime does not expose the previously documented debug
HTTP endpoint. Use a sealed, guarded direct one-shot invocation or deliberately
promote and qualify an authenticated administrative endpoint first.

This does not change the canary verdict. The production intake, scan, identity,
ownership, extraction, classification, dashboard read-model, and mutation
authorities all passed the one-record production journey.

## Stop state

The final owner canary is complete. Automation is dark, queues are empty, and
the owner record is preserved for review. No cleanup or next product phase was
started.
