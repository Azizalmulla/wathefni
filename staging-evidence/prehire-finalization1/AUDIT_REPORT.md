# Pre-Hiring Finalization-1 — Audit and staging proof

Date: 2026-07-19  
Scope: repository + synthetic staging only  
Production touched: no  
External messages sent: no (`WATHEFNI_DELIVERY_MODE=dry_run`)

## Executive decision

**Continue fixing. Do not freeze or promote pre-hiring yet.**

The canonical lifecycle, assessment, interview, offer, acceptance, and hire controls work in staging, but the candidate communication layer is incomplete and English-only. Three release-blocking defects were reproduced:

1. Candidate withdrawal and HR handoff have no executable candidate flow.
2. Dry-run WhatsApp reports success for an empty recipient, proving recipient validation can be bypassed by the simulated transport.
3. Arabic candidate messages and secure pages are absent; the Arabic journey completed only through English copy.

Additional high-risk gaps are WhatsApp ingress deduplication, direct CV-worker stage updates outside the canonical transition authority, and an empty-permission fallback that can over-grant recruiting actions.

## 1. Current WhatsApp architecture

The canonical Wathefni path is `wathefni-orchestrator`, not the quarantined `ai-recruiter/` prototype.

1. Candidate inbound turns arrive with `account_id`, `conversation_id`, phone, text, and optional media.
2. With canonical lifecycle enabled, `resolve_conversation_application` uses a durable conversation binding or exactly one eligible application. Zero or multiple matches fail closed.
3. `handle_candidate_file_turn` accepts PDF, DOC/DOCX, image, and text-file media, stores the file against the exact application, writes the file registry and candidate document, and transitions the application to CV processing.
4. The asynchronous CV worker extracts text, parses a profile, updates processing evidence, creates a version-bound HR task, and moves the application to `ready_for_review`.
5. Candidate outbound messages pass through `candidate_communication_router`; assessment, interview, and offer links are entity-bound.
6. Application lifecycle authority is `recruiting_lifecycle.transition_application`; shortlist, interview, reject, and hire require human confirmation and permission.
7. Assessment, interview, and offer remain separate entities/facets.

The standalone `ai-recruiter/` webhook is explicitly quarantined by repository contracts. It contains an in-memory screening session, no durable WhatsApp message-id dedupe, creates applications directly, and acknowledges a CV without downloading or parsing it. It must remain unreachable.

## 2. Exact existing candidate message inventory

All canonical candidate copy below is hardcoded and unversioned unless noted. No canonical Arabic equivalent exists for any listed English message.

### 1. Initial greeting

Exists, automatic on candidate greeting/fallback:

> Hi, welcome to Wathefni.
>
> I can help you apply or continue an application.
>
> If you have an APPLY code, send it here.

The function appends either current open roles or:

> If you don’t have a code, please ask the company for the job QR or APPLY code.

Source: `wathefni-orchestrator/app.py` `public_candidate_welcome_reply`.

### 2. Request to upload CV

Exists, automatic after application start/status:

> Your application for {title} is started. Next step: please send your CV here as a PDF, Word document, image, or clear text.

Apply-code variant:

> Your application for {role} is started. Please send your CV here as a PDF, Word document, image, or clear text.

Inconsistency: free-form text is invited, but the CV ingestion path requires media.

### 3. CV received successfully

Exists after backend storage succeeds:

> Got it — I received your CV and I’m processing it now. I’ll continue with the next step once it’s ready.

Receipt inquiry after storage truth:

> Yes, I have your CV saved. Wathefni HR will review it and follow up with the next step.

### 4. CV is being processed

Exists only as a status response, not a separate push:

> I received your CV and I’m still processing it. I’ll continue with the next step once it’s ready.

### 5. CV processing completed

No dedicated proactive candidate message.

Possible status reply after screening completeness:

> Your application is complete for review. Wathefni HR will review it and follow up with the next step.

In the canonical `ready_for_review` staging journey, the actual response instead asked the next screening question.

### 6. CV unreadable or unsupported

Only storage failure has copy:

> I received your file, but I could not save it safely. Please resend your CV as a clear PDF, Word document, or image.

Unsupported MIME silently falls through. Blank/corrupt/password-protected/extraction-failed files have no dedicated candidate message.

### 7. Missing information

Exists as a dynamic screening question:

> Your CV is received. Next step: please answer this quick application question:
>
> {next_question}

### 8. Duplicate or updated CV

Update request exists:

> No problem — please send the updated CV here as a PDF, Word document, image, or clear text. I’ll save the new version to your application and process it again.

Actual duplicate or updated upload receives the generic message from item 3. There is no distinct duplicate/update confirmation.

### 9. Application received

Exists after screening answers are saved:

> Thanks — I’ve saved your screening answers. Your application is now complete for review.

Application-start copy is dynamic as described in item 2.

### 10. Assessment invitation

Exists after an HR action creates/resumes a pinned attempt:

> Hi {name},
>
> {optional_note}
>
> You have been invited to complete an application assessment for {title}.
>
> Open your assessment here:
> {attempt_bound_link}
>
> Complete it in your browser. Your answers are saved after each question.

Message kind is `assessment_invite` or `assessment_resend`; the body itself has no template version.

### 11. Assessment reminder

Candidate-initiated continuation reply:

> Continue your assessment in your browser ({answered}/{total} answered):
> {new_attempt_bound_link}
>
> WhatsApp does not accept assessment answers. Reply CANCEL if you want to cancel the attempt.

Generic email-purpose reminder also exists:

> Hi {name},
>
> This is a reminder to complete your application assessment. Please keep an eye on your email and phone for the assessment details and complete it as soon as possible.
>
> Best,
> Wathefni HR

No scheduled reminder proof was found.

### 12. Assessment completed

No candidate WhatsApp completion message. The browser records deterministic completion.

### 13. Shortlisted

Exists only when HR separately invokes candidate notification:

> Hi {name}, you have been shortlisted. Wathefni HR will contact you with the next step.

Shortlisting the application does not automatically send this message.

### 14. Rejected

No canonical candidate rejection message.

### 15. Interview invitation

Scheduled interview:

> Hi {name},
>
> Your Wathefni interview for {role} is scheduled for {time_label}.
> {Google Meet link, calendar-invite notice, or separate-details notice}
>
> Best,
> Wathefni HR

Asynchronous video:

> Hi {name},
>
> {optional_note}
>
> You have been invited to complete a short video interview for your application.
>
> Please open the link below when you are ready. You will be asked to review the instructions, give consent, and answer a few questions by video.
>
> {interview_bound_link}
>
> This video interview helps the hiring team review your application. The final decision is always made by the hiring team.
>
> Thank you,
> Wathefni HR

### 16. Interview reminder

No dedicated candidate reminder. A generic “Interview Follow-up” email body exists but is not bound to a reminder event/version.

### 17. Interview rescheduled or cancelled

No candidate message.

### 18. Offer sent

Exists after human-approved offer send:

> You have received an employment offer{ for position_title}.
> Review and respond: {offer_version_bound_link}

English only and unversioned body; delivery metadata pins `offer_id`, version, and document SHA.

### 19. Offer accepted or declined

No WhatsApp acknowledgement. The offer page says:

> Thank you

and:

> Your response ({status}) was recorded.

The page is English-only.

### 20. Application withdrawn

No candidate withdrawal handler and no confirmation message.

### 21. HR handoff

No candidate HR-handoff handler and no handoff confirmation. Generic fallback:

> I can help with your application status, CV upload/update, quick application questions, and next steps. What would you like to check?

### 22. Delivery failure or retry

No candidate-facing message. HR receives:

> I couldn't send {subject_label}. {humanized_reason}.

A retry resends the original content; no candidate retry-specific copy exists.

## 3. Missing or misleading messages

Release-blocking:

- Arabic equivalents for all 22 moments.
- CV unreadable, corrupt, blank, password-protected, and unsupported outcomes.
- Application withdrawal and HR handoff.
- Rejection and interview cancellation/reschedule.
- Assessment completion and offer-response acknowledgement.
- Candidate name parsing: staging extracted `CURRICULUM VITAE` / `السيرة الذاتية` as the candidate name and used it in invitations.

Misleading:

- The successful storage acknowledgement says “processing” before extraction begins. This is acceptable only as future-tense processing, but no later failure message corrects it.
- Blank CV storage receives successful processing copy, then extraction fails silently.
- “Clear text” is offered as a CV input although text-only turns are not ingested as CVs.
- Dry-run transport accepted an empty phone and reported a simulated WhatsApp success.

## 4. Full CV-upload behavior

- PDF: accepted; digital extraction is local-first, OCR fallback for failed/scanned pages.
- DOCX: accepted; headers, footers, tables, text boxes, hyperlinks, Arabic, mixed language, and selective image OCR are covered by passing smoke tests.
- DOC: accepted MIME, but extraction coverage is weaker than DOCX.
- Image: accepted; OCR path is available.
- Text file: accepted.
- Text-only WhatsApp turn: not accepted as a CV despite candidate copy.
- Unsupported MIME: candidate file handler returns no result; no deterministic error reply.
- Duplicate same filename: safe storage update/reprocessing, but no webhook-level message-id dedupe and no distinct duplicate reply.
- Updated filename: previous CV metadata is retained and latest version marked; candidate gets generic receipt copy.
- Blank/corrupt/password-protected: storage may succeed, extraction fails, candidate gets no failure correction.
- Arabic/mixed: extraction supports both; downstream candidate copy remains English.
- Multiple attachments: no atomic multi-attachment contract was found; each file turn is handled separately.
- Ambiguous conversation: with canonical lifecycle on, attachment is refused and APPLY-code clarification is returned.
- Long-stale conversation: durable binding validates phone/account/company and terminal status; otherwise resolution fails closed when ambiguous.

## 5. Communication trigger and authority map

- AI: intent/entity understanding and phrasing only.
- Backend lifecycle: sole application-stage truth.
- Human-confirmed transitions: shortlist, interview/schedule, reject, hire.
- CV worker: system transition after storage/processing; currently contains direct SQL updates that should be consolidated through lifecycle authority.
- Assessment: human send; browser-only answers; deterministic scoring; completion does not mutate application stage.
- Interview: human create/send/update; link binds interview ID.
- Offer: human create, approve, send; candidate token accept/decline; link binds exact offer version.
- Hire: accepted-offer gate when Offer-1 is enabled; human confirmation and `candidate.decide`.
- Candidate messages: consequential copy is not automatically coupled to every successful transition. Shortlist notification is a separate optional action; rejection/withdrawal/handoff have no flow.

## 6. Delivery, retry, and idempotency

Passing controls:

- Application lifecycle idempotency keys and stale-stage checks.
- Version-bound assessment attempts, progress-version concurrency, token revoke/resend, immutable score/report.
- Offer version/token checks, expiry/revoke, accepted-offer hire gate.
- Ready-for-review task idempotency by application + CV version.
- Tenant-scoped routes and mobile confirmation scope.
- Dry-run assessment and offer recorded as `intentionally_skipped`.

Defects:

- No durable WhatsApp inbound `wamid` seen-set was found.
- Candidate communication dry-run can report success with an empty recipient.
- Ready-for-review tasks are not automatically resolved when the application advances.
- Interview dry-run result was successful but the proof’s normalized delivery status field was null, showing inconsistent delivery vocabularies.
- Empty registry permissions can fall back to recruiting grants in some executors.

## 7. EN/AR end-to-end staging results

Synthetic company: `PHF1`.

Both journeys completed:

`WhatsApp CV upload → CV processing → ready_for_review → assessment completion → human shortlist → human interview → offer approval/send → candidate acceptance → accepted-offer gate → human hire`

Evidence:

- 32/32 positive proof checks passed.
- 9/12 negative checks passed.
- During proof: 4 applications, 2 assessment attempts, 2 interviews, 2 offers, 8 lifecycle events, 8 outbound events.
- After cleanup: all six counters returned to zero.
- No external delivery; assessment and offer were `intentionally_skipped`.
- English and Arabic candidates both reached `hired`.
- Arabic outbound messages and both secure pages were English, so Arabic journey parity failed.
- Artifact SHA-256: `c0c0a407e3a308c5ad4b71ce2971b2e79403595fba741712f85b55b03d3dd592`.

Negative checks reproduced:

- Pass: unsupported CV rejected by handler.
- Pass: blank CV extraction failed.
- Pass: wrong tenant denied.
- Pass: ambiguous application failed closed.
- Pass: stale stage denied.
- Pass: expired and revoked offer links denied for EN and AR.
- Fail/defect: empty-recipient dry-run delivery reported success.
- Fail/defect: no candidate withdrawal handler.
- Fail/defect: no candidate HR-handoff handler.

Assessment expiry/revoke and wrong-tenant behavior passed the existing 29-check assessment cleanup suite. Offer stale/expiry/revoke behavior passed the custom proof and Offer-1 tests.

## 8. Broken or inconsistent steps

- Arabic candidate journey is not localized.
- No withdrawal or human handoff from candidate WhatsApp.
- Unsupported/unreadable CV failures do not consistently produce candidate-safe copy.
- Candidate name extraction can select a document heading.
- Candidate status intent regexes are English-oriented; Arabic status/receipt questions returned no deterministic handler response.
- Assessment and offer public URLs used the production public base in staging-generated messages, despite staging DB/service binding. No message was actually sent, but staging link configuration is unsafe for future controlled sends.
- Browser-assessment smoke failed with `KeyError: attempt`; the custom direct assessment flow passed.
- Interview workflow smoke failed because its psycopg2 stub shadowed the installed package; the live custom interview path and authenticated mobile proof passed.
- Context-guardrails smoke failed candidate-name focus classification.

## 9. Web/mobile/Assistant/WhatsApp parity

- Web: full lifecycle and separate assessment/interview/offer surfaces; dashboard build and 42 tests passed.
- Mobile: backend-owned `allowed_actions`, authenticated staging proof 36/36 passed, mobile typecheck and 44 tests passed.
- Mobile intentionally omits scheduling; it also lacks equivalent offer and assessment operator UI.
- Assistant: uses the same registry and confirmation model, but empty-permission fallback must be removed.
- WhatsApp: safe application binding only when canonical lifecycle is enabled; staging has it enabled.
- Secure assessment: token + attempt + immutable content version; browser-only answers.
- Secure offer: token + offer version; expiry/revoke/stale checks.
- Tasks: idempotent creation, incomplete auto-resolution.

## 10. Permission and tenant isolation

Passed:

- Wrong-company application action failed.
- Ambiguous candidate/application attachment failed closed.
- Tenant-isolation harness passed 24/24.
- Mobile permissions were backend current and restricted actions were omitted/rejected.
- AI stage mutation and offer mutation are blocked.

Open:

- Registry empty-permission fallback can over-grant.
- Hire may be advertised before accepted-offer eligibility even though execution later rejects it.
- Canonical lifecycle is default-off in code; deployment must explicitly pin it on.

## 11. Exact contained fixes required

P0:

1. Add durable WhatsApp inbound message-id idempotency before any candidate/application mutation.
2. Add a backend-owned candidate withdrawal flow with exact application binding, human/audit visibility, and terminal confirmation.
3. Add explicit HR-handoff intent, task/event, conversation pause, and candidate confirmation.
4. Validate recipients before dry-run or live transport; empty phone/email must be failed, never simulated success.
5. Add versioned EN/AR candidate templates for the 22 moments and locale selection bound to candidate/application.
6. Route CV processing stage writes through canonical lifecycle authority only.
7. Remove empty-permission default grants.

P1:

8. Add deterministic unsupported/unreadable/password/blank CV outcomes and retries.
9. Couple consequential notifications to successful transitions using an outbox/idempotency key, while retaining explicit HR confirmation policy.
10. Resolve ready-for-review tasks when an application leaves that stage.
11. Gate advertised `hire` on accepted offer when Offer-1 is enabled.
12. Correct staging public base URLs.
13. Fix candidate-name heading rejection.
14. Localize assessment and offer secure pages.

P2:

15. Add mobile read-only assessment facet and Offer-1 controls according to the existing backend capability contract.
16. Normalize delivery status vocabulary across assessment/interview/offer.
17. Repair the three failing smoke harnesses and keep them as staging gates.

## 12. Production risk assessment

Overall: **High**.

- Data/state authority: medium-low risk when canonical flags are enabled.
- Candidate communication correctness: high risk.
- Arabic parity: high risk.
- Wrong-recipient/duplicate prevention: high risk until WhatsApp ingress dedupe and recipient validation are closed.
- Offer/assessment token integrity: low risk based on proof.
- Tenant isolation: low-medium risk based on passing proofs, with empty-permission fallback still open.
- Operational observability: medium risk due delivery-status inconsistency and task non-resolution.

## 13. Recommendation

**Continue fixing and keep production frozen for Pre-Hiring Finalization-1.**

Re-run the two journeys only after P0 fixes. Freeze pre-hiring when:

- all 22 EN/AR templates exist and are event-bound,
- withdrawal/handoff are executable and audited,
- unreadable/unsupported CVs receive deterministic outcomes,
- WhatsApp ingress dedupe and recipient validation pass,
- Arabic candidate messages and secure pages pass,
- accepted-offer hire advertisement and task lifecycle are aligned,
- all relevant staging smoke files pass,
- synthetic counters return to zero.

## Evidence files

- `STAGING_PROOF.json`
- `SMOKE_SUITE.txt`
- `prehire-finalization1-mobile.txt`
- `wathefni-orchestrator/ops/prehire-finalization1-staging-proof.py`
