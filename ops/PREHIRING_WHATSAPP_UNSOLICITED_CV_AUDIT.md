# Pre-hiring WhatsApp Unsolicited CV Audit

Audit stamp: `20260726T222422Z` / `2026-07-27 01:24:22 Asia/Kuwait`  
Environment: WATHEFNI production (`wathefni`, host `76.13.63.68`)  
Production health at audit: HTTP `200`  
Method: deployed-source inspection, systemd/runtime flag inspection, and read-only production SQL. No production mutation or live WhatsApp test was performed.

## Executive finding

A brand-new WhatsApp sender's CV is **transport-downloaded but not accepted as a canonical CV and not extracted**. The orchestrator creates:

1. a deduplicated `whatsapp_inbound_messages` ingress-ledger row; and
2. a `candidate_pending_media` row with `status='pending'` and a two-hour expiry.

It does **not** create a candidate, application, Job binding, conversation/application binding, `candidate_documents` row, `file_registry` row, or durable Intake/Talent Pool record. It does not set an application to `needs_role`; the phrase “needs role” exists only in the response template and handler name.

The candidate receives:

> I am holding this file temporarily, but I need one exact job before an application can start. Send the APPLY code or tell me which role you mean.

The file is not visible to HR in the current dashboard. An exact APPLY code entered later does not itself consume the held CV. Within two hours, a subsequent explicit “ready to apply” confirmation, or another CV after the Job preview was successfully sent, can create the application and attach the latest pending file.

This is fail-closed against accidental Job entry, but it is not a complete or reliable unsolicited-CV intake product. The hold is a temporary local-path reference, corruption is not checked before the hold response, a Job name in the CV caption is ignored, and the production CV-processing timer is disabled.

**Verdict: NO-GO for advertising or treating unsolicited WhatsApp CV intake as supported.**

## Production authority inspected

### Deployed transport

- `/root/.openclaw/extensions/octopus-channel.ts`
  - SHA-256: `ac1cf9e6606b46a9175db524527d171284b81441f316de7bb96256c47e54ad78`
  - `extractDocumentMessage`
  - `saveDocumentMessage`
  - `formatDocumentAsText`
  - `handleInboundMessage`
  - `callHrOrchestratorTurn`
  - `maybeSendFastCvAcknowledgement`
- `/root/.openclaw/openclaw.json`
  - Octopus enabled
  - `agentId="wathefni-hr"`
  - `dmPolicy="open"`
  - `allowFrom=["*"]`
  - `mediaMaxMb=50`
  - webhook `/webhook/octopus/wathefni`

The checked-in `plugins/octopus-channel/octopus-channel.ts` is **not byte-identical** to production (local SHA-256 `59403e64...`). Findings about the transport use the deployed production file, not the local copy.

### Deployed orchestrator

The following production files are byte-identical to the inspected repository versions:

- `wathefni-orchestrator/app.py` / `/opt/wathefni/orchestrator/app.py`
  - SHA-256 `eddf2ff6b6fb4230df096f79c591c0d58890c37d54cdb00b528f235e176f4270`
- `wathefni-orchestrator/prehire_jobs.py`
  - SHA-256 `ca2d7d0eb29d575df11a5975cb4e1014941cd0a2429f8b4573a2cec5fc435d08`
- `wathefni-orchestrator/jobs_phase2_stage_b.py`
  - SHA-256 `2dda3a101d8fe55b30d85e2d7bfc089740d8141b45be1f258de98f189c588479`
- `wathefni-orchestrator/recruiting_lifecycle.py`
  - SHA-256 `dc7ead5774517cfb8513667aa874ee78f03a70e3179b28a79512d6eb452a8560`
- `wathefni-orchestrator/candidate_messages.py`
  - SHA-256 `c72487ff530257c1b0a3f25b153c66ad7a15fd590ec4047d456323d58dcc25da`
- `wathefni-orchestrator/candidate_ranking.py`
  - SHA-256 `f0e838d03d5dc1dc8180e3c7cb75a83558a490f596c8fc5986dbf93d95fdad65`
- `wathefni-orchestrator/ranking_evidence_adapter.py`
  - SHA-256 `c41bdb6c4525de6670d7386007d3752c1f3dcc2962aa8d747850e0d6cedb87d0`
- `wathefni-orchestrator/unified_candidates.py`
- `wathefni-orchestrator/candidate_communication_authority.py`
- `wathefni-orchestrator/candidate_record_state_policy.py`
- `wathefni-orchestrator/cv_extraction.py`

## Exact production flags and worker state

From `/etc/systemd/system/wathefni-orchestrator.service.d/environment.conf` and the running service:

```text
WATHEFNI_CANONICAL_LIFECYCLE=true
WATHEFNI_STAGE_B_ENABLED=1
WATHEFNI_STAGE_B_CANARY_ONLY=0
WATHEFNI_STAGE_B_PUBLIC_POSITIONS=J2P2_PROD_TEST
WATHEFNI_STAGE_B_PUBLIC_APPLY_CODES=APPLY-WATHEFNI-J2P2_PROD_TEST
WATHEFNI_STAGE_B_LIVE_WHATSAPP=1
WATHEFNI_CV_MISTRAL_OCR=true
WATHEFNI_CV_GPT_VISION_RESCUE=true
WATHEFNI_TALENT_POOL_CLASSIFICATION=on
WATHEFNI_TALENT_POOL_CLASSIFICATION_WORKERS=off
```

Consequences:

- Canonical conversation/application resolution is active.
- Stage B conversion is active.
- Because `WATHEFNI_STAGE_B_CANARY_ONLY=0`, `stage_b_convert_allowed_for_job` permits **all otherwise eligible Jobs**, not only `J2P2_PROD_TEST`. The public position/apply-code values do not narrow conversion while this flag is `0`.
- Job previews can be sent live over WhatsApp.
- OCR providers are enabled, but they are not called for an unbound CV.

Production CV worker:

- `/etc/systemd/system/wathefni-prehire-cv-process.service`: loaded, oneshot, last result `success`.
- `/etc/systemd/system/wathefni-prehire-cv-process.timer`: `inactive`, `disabled`, no last trigger.
- The service would call `/orchestrator/prehire/cv/process?dry_run=false&limit=10&force=false&send_screening=true`.
- `process_candidate_cv_document` forcibly sets `send_screening=False`, so validation cannot auto-send screening even when the service is invoked.

## Exact full path: brand-new sender sends only a CV

### 1. AI Octopus receives and downloads the media

Production `/root/.openclaw/extensions/octopus-channel.ts`:

- `extractDocumentMessage` reads the WhatsApp document URL, MIME type, filename, caption, media ID, and message ID.
- `saveDocumentMessage` fetches the whole file, rejects a zero-byte download, enforces the configured 50 MB limit, chooses the response/provider MIME type, and calls `saveMediaBuffer(..., "inbound", ...)`.
- It does **not** parse the CV, sniff its true content, scan it for malware, or establish candidate identity.
- If no caption exists, `formatDocumentAsText` produces `Document shared: <filename>`.
- `callHrOrchestratorTurn` POSTs the local path and MIME type to `/orchestrator/whatsapp-turn`.
- `maybeSendFastCvAcknowledgement` returns immediately for `agentId="wathefni-hr"`, so it does not send a second fast acknowledgement in this production account.

### 2. The orchestrator claims the inbound message

`app.py`:

- `whatsapp_turn`
- `claim_whatsapp_inbound`
- `_whatsapp_inbound_identity`

`claim_whatsapp_inbound` inserts one `whatsapp_inbound_messages` row keyed by:

```text
(provider, account_id, provider_message_id)
```

For a new unknown phone:

- `provider='octopus'`
- `status='processing'`, then `status='completed'`
- `company_code=NULL`
- `sender_phone` and `conversation_id` are present
- only `payload_sha256` is retained, not a canonical CV/document record
- `response_json` contains the authoritative handler response

Exact provider-message replay is idempotent. A replay with mismatched phone, conversation, or payload hash is rejected.

### 3. No tenant or prior application resolves

`_whatsapp_turn_impl` first calls `refresh_conversation_link_from_inbound`.

For a brand-new sender:

- `request_company_code(..., default=None)` returns `None`;
- no employee/application is found;
- no `conversation_links` row is inserted;
- no `conversation_application_bindings` row exists.

### 4. The deterministic file handler runs before role-name handling

`handle_non_hr_conversational_turn` runs `handle_candidate_file_turn` before:

- `handle_public_candidate_apply_code_turn`;
- `handle_public_candidate_role_selection_turn`; and
- `handle_public_candidate_apply_interest_turn`.

`handle_candidate_file_turn` accepts only these declared MIME classes:

```text
image/*
application/pdf
application/vnd.openxmlformats-officedocument.wordprocessingml.document
```

This check is MIME-string-only. It is not extraction or content validation.

### 5. Application resolution fails closed

With no apply code, Job context, tenant, existing application, or conversation binding:

- `active_candidate_job_context` returns no row;
- `recruiting_lifecycle.resolve_conversation_application` returns `tenant_scope_required`;
- `handle_candidate_file_turn` calls `hold_candidate_pending_media`;
- `application_created=False`.

### 6. Only a temporary pending-media row is created

`hold_candidate_pending_media`:

1. updates prior `candidate_pending_media` rows in the same phone/account/conversation scope from `pending` to `expired`;
2. inserts a new row with:

```text
phone=<sender phone>
account_id=<Octopus account>
conversation_id=<Octopus conversation>
media={"path": "<local inbound file path>", "type": "<declared MIME>"}
raw_text=<caption or "Document shared: ...">
status='pending'
expires_at=now() + interval '2 hours'
```

There is no checksum, durable object reference, scan decision, extraction record, company, Job, candidate, application, or app key in this row.

### 7. Exact outbound response

`candidate_messages.py`, template `cv_held_needs_role`, version `candidate_flow_v1`:

English:

> I am holding this file temporarily, but I need one exact job before an application can start. Send the APPLY code or tell me which role you mean.

Arabic:

> سأحتفظ بالملف مؤقتاً، لكن أحتاج تحديد وظيفة واحدة بالضبط قبل بدء طلب التوظيف. أرسل رمز APPLY أو اكتب اسم الوظيفة المقصودة.

A bare document usually becomes English because the transport supplies the English synthetic text `Document shared: <filename>`. An Arabic caption or Arabic filename can cause Arabic inference.

The authoritative response has:

```text
intent='handle_candidate_file'
turn_focus='candidate_file'
final_reply_source='candidate_file_handler'
```

`apply_candidate_reply_policy` does not alter either template.

## Answers to the requested questions

### 1. Does the system accept and extract the CV?

**Transport accept: yes, conditionally. Canonical CV accept/extract: no.**

- AI Octopus downloads and saves a non-empty file up to 50 MB.
- The orchestrator accepts only a declared PDF, DOCX, or `image/*` MIME into the temporary hold.
- It does not copy the unbound file into canonical application storage.
- It does not create `candidate_documents`, `file_registry`, `cv_extraction_runs`, Candidate Knowledge chunks, scan decisions, or identity resolutions.
- It does not call `extract_candidate_cv_document`.

The candidate-facing word “holding” is therefore stronger than the current durability/validation guarantee.

### 2. Does it create a candidate, application, conversation binding, or intake record?

For the stated scenario:

- `candidates`: **no row**
- `applications`: **no row**
- `conversation_application_bindings`: **no row**
- `conversation_links`: **no row**
- `candidate_job_contexts`: **no row**
- `public_candidate_sessions`: **no row**
- `candidate_documents`: **no row**
- `file_registry`: **no row**
- durable email-style `inbound_messages` / `intake_documents`: **no row**
- `whatsapp_inbound_messages`: **one ingress-ledger row**
- `candidate_pending_media`: **one temporary hold row**

`candidate_pending_media` is a temporary transport handoff record, not the dashboard Intake/Talent Pool record.

### 3. Does it attach the CV to any Job automatically?

**No.**

The pending row has no company, Job ID, position code, apply code, or app key. No Job guess is made from the filename, CV text, or message caption.

### 4. Is the candidate placed in `needs_role`, held, unassigned, or rejected?

There is no candidate/application to carry any of those statuses.

- Application `status='needs_role'`: **no**
- Application `status='import_review'`: **no**
- Dashboard unassigned application: **no**
- Rejected candidate/application: **no**
- Temporary media `status='pending'`: **yes**, for two hours

The operational description is “temporarily held without role,” but this is not the canonical `needs_role` state.

### 5. What WhatsApp response does the candidate receive?

The exact `cv_held_needs_role` message quoted above, unless:

- the transport cannot download/save the media;
- the MIME is unsupported;
- ingress lacks a provider message ID; or
- an unexpected backend failure occurs.

Unsupported MIME receives `cv_invalid`:

> We could not accept this CV because it is unsupported, blank, corrupt, password-protected, or unreadable. Please send a readable PDF, DOCX, or clear image.

That copy overstates the check: at this point the code has only rejected the MIME class; it has not checked blank/corrupt/password-protected content.

### 6. Can HR see the candidate anywhere in the dashboard?

**No.**

- `/dashboard/prehire/import/intake` reads `applications` whose statuses are `needs_role` or `import_review`.
- `/dashboard/prehire/intake-operations` reads `intake_processing_jobs` and held application processing flags.
- normal Candidates/Ranking surfaces read applications and canonical candidate data.
- none reads `candidate_pending_media` or `whatsapp_inbound_messages` as a candidate queue.

A database operator can inspect the two technical rows, but HR has no current dashboard candidate/file record.

### 7. Can the candidate later enter an apply code and reuse the same uploaded CV?

**Conditionally, but not on the apply-code message alone.**

Required sequence:

1. The original `candidate_pending_media` row must still be `pending` and unexpired (two hours).
2. The sender must use the same phone/account/conversation scope.
3. The exact apply code must resolve to one accepting Job.
4. `handle_public_candidate_apply_code_turn` creates an `awaiting_apply_confirmation` `candidate_job_contexts` row and sends/stamps a Job preview.
5. The candidate must then send an explicit apply confirmation such as `ready to apply`, or send another CV.
6. `jobs_phase2_stage_b.convert_job_context_to_application` reads the latest pending media, creates/binds the application, attaches the file, and marks pending rows `attached`.

If the two-hour row has expired or its local path no longer exists, the old CV is not reusable. The apply-code turn itself does not report that the earlier file remains reusable.

### 8. Could duplicate candidates/applications be created?

For the exact same provider message, no: `whatsapp_inbound_messages` has a production unique key on `(provider, account_id, provider_message_id)`.

Within one phone and one active Job, duplicate active applications are strongly limited by:

- `candidate_job_contexts_one_active_uidx`;
- the Stage B advisory transaction lock;
- `candidate_job_contexts_convert_idem_uidx`;
- `applications_one_active_same_role_uq`; and
- existing same-role lookup before creation.

Residual duplicate risks:

1. `candidate_pending_media` has no unique active-row constraint and `hold_candidate_pending_media` has no transaction advisory lock. Concurrent distinct messages can race and leave more than one `pending` row.
2. Different conversation IDs create separate pending scopes.
3. Different WhatsApp numbers create different `candidates.phone` identities for the same human.
4. WhatsApp attachment does not run `inbound_cv_authority.resolve_identity`; it binds by sender phone. An existing email/bulk-import surrogate candidate may coexist with the new WhatsApp-phone candidate.
5. A new application is permitted after a same-role application is terminal (`rejected`, `withdrawn`, or `hired`), using a timestamp suffix if the base app key already exists.
6. Different Jobs correctly create different applications, but may look like duplicates if person-level identity is not reconciled.

### 9. Exact scenario behavior

#### CV only

- file downloaded;
- ingress ledger inserted;
- supported MIME held in `candidate_pending_media`;
- no extraction, candidate, Job context, application, or HR visibility;
- receives `cv_held_needs_role`.

#### CV, then apply code

After the CV:

- pending media exists for two hours.

After the apply code:

- `resolve_public_role_by_apply_code` verifies the exact `positions.apply_code`, Job status, visibility/access, deadline, and vacancies;
- `upsert_candidate_job_context` creates `status='awaiting_apply_confirmation'`;
- `upsert_public_candidate_session` creates/updates `status='active'`;
- `deliver_and_stamp_job_preview` sends the Job preview and stamps `preview_sent_at` on successful delivery;
- no candidate/application is created yet;
- the old pending CV is not attached yet.

A third `ready to apply` confirmation can create the application and reuse the held file while it is still valid.

#### Apply code, then CV

The apply code creates and previews the Job context without starting an application.

If preview delivery was stamped and the Job still accepts applications, the later CV:

- is first inserted into `candidate_pending_media`;
- triggers `convert_job_context_to_application` because Stage B is enabled for all eligible Jobs;
- creates/updates `candidates` keyed by WhatsApp phone;
- inserts an `applications` row at `awaiting_cv`;
- inserts an `application_lifecycle_events` event for `explicit_apply`;
- inserts/updates `conversation_application_bindings` with `bound_reason='qualifying_cv'`;
- stores the CV through `register_candidate_cv_file`;
- creates `file_registry` and `candidate_documents(extraction_status='pending_extraction')`;
- transitions the application to `cv_processing`;
- marks pending media `attached`;
- replies `file_received_checking`:

> We received your file and are checking that it is a supported, readable CV.

If preview delivery was not stamped, the CV remains held and no application is created.

Because the production CV-processing timer is disabled, automatic extraction/validation after this point is not currently guaranteed; the application can remain `cv_processing` and the document `pending_extraction`.

#### CV carrying an exact apply code in its caption

`handle_candidate_file_turn` recognizes the code, holds the file, creates the Job context, sends the preview, and returns before conversion. It does not start the application in the same turn. A later confirmation or CV is required.

#### CV with a message naming a Job but no apply code

The file handler preempts the role-name handlers. It does not call `public_role_matches` and does not bind from the role name. The file is held with the generic `cv_held_needs_role` reply.

This means the instruction “or tell me which role you mean” is not fulfilled when the role name is supplied in the same message as the CV.

#### Multiple CVs before Job binding

- A new CV in the same phone/account/conversation scope marks prior `pending` rows `expired` and inserts the new one.
- Only the latest still-pending file is selected for later Stage B attachment.
- The earlier row remains in the database as `expired`; it is not a canonical document version.
- Concurrent messages can race because no active-row uniqueness/lock protects this operation.
- Different conversations can each retain a pending row.

#### Multiple CVs after an application exists

- exact same content for the same application is deduplicated through `file_registry` checksum lookup;
- a different file is treated as a replacement;
- the new document is stored as `awaiting_confirmation`;
- the current CV remains authoritative until the candidate replies `CONFIRM`;
- the candidate receives:

> I received the new CV. Reply CONFIRM to replace your current CV, or CANCEL to keep the current one.

#### Unsupported file

- The Octopus transport may still download/save it.
- `handle_candidate_file_turn` rejects declared MIME types outside PDF, DOCX, and `image/*`.
- No pending-media row is created.
- The candidate receives `cv_invalid`.

#### Empty, oversized, or download-failed file

- The production transport rejects empty downloads and files over 50 MB and catches download/save errors.
- If there is no separate caption/body, it can exit with “no actionable content” and send no orchestrator response.
- If text remains, it reaches the orchestrator as a text-only turn and can receive a generic Job/welcome reply rather than `cv_invalid`.

#### Corrupt, blank, password-protected, or forged supported-MIME file

- Before Job binding, it is held exactly like a valid CV; no extraction check occurs.
- After Job binding, it is stored and reported as “being checked.”
- `process_candidate_cv_document` can later classify it invalid and send `cv_invalid`, but the production timer that invokes this worker is disabled.

### 10. Can an unbound CV enter Ranking, screening, interview, communication automation, or lifecycle?

For the exact new-sender WhatsApp path: **no downstream entry occurs**.

Structural proof:

- No `applications` row exists, so there is no lifecycle entity.
- No `candidate_documents` or canonical CV evidence exists.
- Ranking `load_job_application_pool` requires exact company and `position_code` matching the requested Job and applies `production_application_predicate`.
- `production_application_predicate` excludes `needs_role`, `import_review`, and `import_archived`.
- `ranking_evidence_adapter` independently denies held/restricted records.
- `resolve_conversation_application` excludes held Intake statuses.
- no screening questions, assessment, interview, HR task, or application lifecycle event is created by `hold_candidate_pending_media`.
- `process_candidate_cv_document` forces `send_screening=False`.
- `candidate_communication_authority` requires an application; only the direct transactional hold reply is sent without one.

However, the stronger system-wide invariant requested cannot be fully confirmed:

- `candidate_communication_authority.evaluate_candidate_communication_authority` checks app key, tenant, held/restricted state, data source, and test identity, but does not verify that `position_code` maps to a current canonical `positions` row.
- `recruiting_lifecycle.transition_application` validates tenant, status transition, permissions, and confirmation, but does not re-verify canonical Job binding on every transition.
- screening/interview paths generally rely on the existence/stage of an application rather than a single explicit `verified_job_binding` authority.

Therefore:

- **PASS**: this exact unsolicited WhatsApp CV cannot enter those systems because it creates no application.
- **PASS**: Job Ranking itself requires an exact Job pool.
- **FAIL as a global invariant**: there is no universal downstream `verified_job_binding` gate shared by communication, screening, interview, and lifecycle authorities. A malformed/orphan application created by another ingress path is not conclusively blocked by one common authority.

## Production database snapshot

Read-only aggregate snapshot at audit time:

```text
candidate_pending_media:
  no rows

candidate_job_contexts:
  no rows

public_candidate_sessions:
  active=9
  completed=5

whatsapp_inbound_messages:
  completed=7
```

The database had no live pending-media example to inspect. The path above is based on the exact deployed source, active flags, schema, indexes, and service state. A production test was intentionally not generated because this task prohibited production changes.

Relevant production indexes:

- `whatsapp_inbound_messages_provider_account_id_provider_mess_key` — unique provider/account/message ID
- `candidate_pending_media_pkey` — unique only by `pending_id`; no one-active-row uniqueness
- `candidate_job_contexts_one_active_uidx` — one active context per phone/account/conversation
- `candidate_job_contexts_convert_idem_uidx` — unique conversion idempotency key
- `conversation_application_bindi_company_code_conversation_id_key` — one app binding per tenant/conversation
- `applications_one_active_same_role_uq` — one nonterminal, non-held application per phone/company/position

## CURRENT BEHAVIOR

1. Public WhatsApp is open to new senders.
2. The channel downloads a non-empty file up to 50 MB into local inbound media storage.
3. The orchestrator records inbound idempotency.
4. A PDF, DOCX, or declared image with no Job/application is referenced by `candidate_pending_media` for two hours.
5. No parsing, malware scan, identity resolution, candidate, application, Intake record, or HR-visible record is created.
6. The response says the file is being held and asks for a Job/apply code.
7. Exact apply code creates a Job preview/context but does not itself attach the earlier CV.
8. A later explicit confirmation or CV can convert the context and reuse the pending file.
9. Once attached, the application reaches `cv_processing`, but the production CV-processing timer is disabled.
10. The unbound CV itself cannot enter the hiring pipeline.

## RISKS

### High

1. **False durability impression:** “I am holding this file” means a two-hour DB pointer to a local path, not durable canonical storage.
2. **Invisible intake:** HR cannot see or recover the sender/file from the dashboard.
3. **Validation gap:** corrupt/password-protected/forged supported-MIME files receive the same hold response as valid CVs.
4. **Half-started applications:** production Stage B is enabled for all eligible Jobs while the automatic CV-processing timer is disabled.
5. **No global verified-Job invariant:** communication/lifecycle authorities do not share one canonical Job-binding check.

### Medium

6. **Broken instruction:** a role name in the same CV message is ignored even though the reply says “tell me which role.”
7. **Reuse is implicit and fragile:** apply code alone does not attach the file; reuse requires another turn, same scope, unexpired row, and surviving local path.
8. **Cross-channel/person duplication:** WhatsApp uses sender phone and does not reuse inbound CV identity authority.
9. **Pending-media race:** no advisory lock or one-active unique index.
10. **Transport failure ambiguity:** empty/oversized/download failures can be silent or appear as a text-only conversation.
11. **Overbroad rollout:** `WATHEFNI_STAGE_B_CANARY_ONLY=0` makes the configured public canary lists non-limiting.

## RECOMMENDED BEHAVIOR

1. Accept a new CV into a durable, security-scanned **pre-application WhatsApp Intake** record.
2. Do not create a candidate or application until an exact canonical Job is verified and the candidate confirms apply intent.
3. Show the candidate an honest state:
   - file received;
   - validation result;
   - Job not yet selected;
   - expiry/retention window;
   - exact next action.
4. Expose the pre-application record in a tenant-safe HR Intake queue after tenant/Job scope is established; before that, restrict it to platform operations.
5. Reuse the validated document after exact apply code + explicit confirmation without requiring re-upload.
6. Treat a role name as a search/clarification hint only; never silently bind fuzzy text.
7. Version multiple CVs explicitly and ask which is current when ambiguous.
8. Run person-level identity resolution at binding time before candidate/application creation.
9. Require one shared `verified_job_binding` decision for Ranking, screening, assessment, interview, communication, and lifecycle.
10. Enable and monitor CV processing only after backlog, invalid-file response, rollback, and alerting are proven.

## GO/NO-GO

**NO-GO**

The current behavior is safe against an unsolicited CV silently entering a Job, but unsafe/confusing as a supported intake experience. The blocking reasons are temporary/noncanonical storage, no HR visibility, no immediate content validation, fragile reuse, disabled automatic CV processing after application creation, and lack of a universal verified-Job downstream gate.

## Exact fix plan

No fixes were applied in this audit.

### Phase 0 — contain current behavior

1. Keep unbound CVs excluded from candidate/application creation.
2. Change `cv_held_needs_role` copy so it does not promise durable holding until durability exists.
3. Decide explicitly whether full Stage B is intended:
   - if not, set `WATHEFNI_STAGE_B_CANARY_ONLY=1` and use exact Job allowlists;
   - if yes, retain `0` only after the CV worker is live and monitored.
4. Do not enable the CV timer until pending backlog and invalid-file notification effects are reviewed.

### Phase 1 — canonical pre-application intake

1. In `prehire_jobs.py`, replace or extend `candidate_pending_media` with a durable intake schema containing:
   - provider/account/message ID;
   - phone/conversation;
   - provider media ID and original filename;
   - content SHA-256 and sniffed MIME;
   - encrypted/quarantine object reference;
   - scan, extraction, identity, Job-binding, and retention states;
   - `bound_app_key` and a single consumption idempotency key.
2. Use states such as:
   - `received`;
   - `scan_pending`;
   - `invalid`;
   - `quarantined`;
   - `awaiting_job_binding`;
   - `awaiting_apply_confirmation`;
   - `bound`;
   - `expired`.
3. Add a one-active-intake unique constraint or advisory lock per phone/account/conversation and a unique provider-message identity.
4. Reuse `inbound_cv_authority` scan/identity primitives after generalizing provider assumptions from email-only to inbound-document provenance.

### Phase 2 — transport and validation

1. In production `octopus-channel.ts`:
   - pass provider media ID, filename, size, declared MIME, and message ID to the orchestrator;
   - return a deterministic file-download error response;
   - never silently downgrade a failed file to a text-only success path.
2. In `app.py::handle_candidate_file_turn`:
   - sniff content instead of trusting MIME alone;
   - persist first, then scan/extract asynchronously;
   - distinguish unsupported, corrupt, password-protected, quarantined, and awaiting-Job states;
   - avoid claiming readable/valid before worker completion.
3. Add a monitored worker/timer with backlog age, failures, dead letters, and delivery alerts.

### Phase 3 — exact Job binding and reuse

1. Keep `resolve_public_role_by_apply_code` as the exact Job authority.
2. On CV then apply code:
   - bind the intake to the verified Job context;
   - tell the candidate the CV is ready to reuse;
   - require explicit `ready to apply` confirmation before application creation.
3. On apply code then CV:
   - allow the CV to count as confirmation only if this consent rule is explicitly approved and stated in the preview;
   - otherwise ask for confirmation.
4. For role-name captions:
   - use `public_role_matches` only to present bounded options;
   - require an exact selection/confirmation;
   - never create an application from a fuzzy match.
5. In `jobs_phase2_stage_b.convert_job_context_to_application`, consume exactly one validated intake record transactionally and make intake-to-application binding idempotent.

### Phase 4 — person identity and duplicate control

1. Before inserting `candidates`, run tenant-scoped identity resolution using:
   - WhatsApp phone;
   - extracted CV phone/email;
   - existing `candidate_identity_keys`;
   - existing person/membership records.
2. Safe exact matches reuse the person/candidate.
3. Possible matches/conflicts create an HR identity-review task and do not create a second live application.
4. Preserve the current one-active-same-role constraint and test concurrent conversion, provider replay, different conversations, and terminal re-apply.

### Phase 5 — dashboard

1. Add a WhatsApp pre-application section to `unified_candidates.intake_operations_summary`.
2. Add a governed Intake list endpoint that does not expose cross-tenant/unbound files to normal HR.
3. Update:
   - `apps/wathefni-dashboard/src/lib/api.ts`;
   - `apps/wathefni-dashboard/src/types.ts`;
   - `apps/wathefni-dashboard/src/components/candidates/IntakeOperationsPage.tsx`.
4. Display source, received time, validation state, expiry, Job-binding state, duplicate/identity review, and the permitted next action.

### Phase 6 — universal downstream gate

1. Introduce one shared `assert_verified_job_binding(application)` authority that verifies:
   - company;
   - nonblank position;
   - matching canonical `positions` row/job ID;
   - binding provenance;
   - allowed Job/application state.
2. Call it from:
   - Ranking pool/materialization;
   - screening/assessment creation and sending;
   - interview creation/invitation;
   - candidate communication authority;
   - lifecycle transitions;
   - Candidate Knowledge ranking adapters.
3. Keep held/pre-application states readable only where authorized and non-actionable everywhere.

### Phase 7 — qualification and rollout

1. Add production-fidelity tests for every scenario in this report.
2. Prove zero downstream mutation before exact Job confirmation.
3. Prove valid reuse and invalid-file rejection.
4. Prove HR visibility and tenant isolation.
5. Prove no duplicate person/application under concurrency and webhook replay.
6. Prove worker kill switch, backlog recovery, and rollback.
7. Canary one Job first; only then decide whether `WATHEFNI_STAGE_B_CANARY_ONLY=0` is safe.

