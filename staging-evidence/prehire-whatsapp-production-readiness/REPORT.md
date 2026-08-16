# Pre-Hiring WhatsApp Production Readiness + LLM Intent Audit

## Decision

**Do not promote commit `061c93c7851fe9f4e64abd41bdfe1d36fd57372d` yet.**

The staging-green backend artifact remains valid for its original contained
candidate-flow scope, but this wider readiness audit found two production
blockers:

1. The deployed Octopus channel extracts the real inbound WhatsApp message ID
   but does not forward it in a metadata field the orchestrator dedupe gate
   reads. Production-shaped candidate turns therefore reach the orchestrator
   without a usable provider ID.
2. There is no general candidate LLM intent classifier. The deterministic
   layer scored only `57.5%` intent accuracy across 120 balanced natural
   English, MSA, Gulf, and Arabizi/mixed messages. Critical Gulf/Arabizi
   phrasings for CV replacement, withdrawal, status, and HR handoff are missed.

No production system was changed and no real message was sent.

## Audited baseline

- Commit: `061c93c7851fe9f4e64abd41bdfe1d36fd57372d`
- Original staging artifact SHA-256:
  `56f250ec79a4d23e71f138ea3d31ce3ce2ed5a689dd02f4ecdbd661409b3985d`
- Existing cleanup proof: 49/49 positive, 22/22 negative, zero external
  messages, zero synthetic rows after cleanup.
- New evaluation: 120 offline/staging-code messages and 16 staging provider
  role-option calls.
- New provider proof: synthetic staging DB only; no delivery; synthetic
  inbound ledger row count returned to zero.

## Current candidate interpretation architecture

The real current path is:

1. The Octopus channel parses the webhook, conversation, phone, media,
   language hint, and provider message ID.
2. The channel calls `/orchestrator/whatsapp-turn`.
3. The orchestrator requires and claims a durable provider message ID before
   routing or mutation.
4. `_whatsapp_turn_impl` sends non-HR traffic through a fixed deterministic
   handler order.
5. Most intents are regular expressions, exact tokens, current media, or
   current backend state. There is no candidate-wide LLM intent call.
6. GPT is used only in two candidate subflows:
   - fallback mapping of a reply to one of job options already listed;
   - parsing answers while an application is waiting for screening answers.
   Async CV processing also uses bounded vision/profile extraction after the
   turn, but that is document interpretation rather than message-intent
   classification.
7. Backend functions resolve/bind the application, validate state, perform any
   permitted action, and render a versioned candidate template.

The current candidate handler precedence is employee status handlers first,
then withdrawal, HR handoff, CV replacement, application status, handoff
pause, file upload, active assessment, APPLY code, public role selection,
apply-by-role, screening, process FAQ, CV truth, onboarding, casual, and
fallback.

This means deterministic handlers run before any candidate LLM use. GPT is not
called for ordinary welcome, APPLY-code, upload, replacement, status,
withdrawal, handoff, assessment, interview, offer, or unknown messages.

## Current model and prompts

Staging provider configuration resolves to:

- Provider: `openai-sse`
- API: OpenAI Responses
- Model: `gpt-5.4`
- Temperature: `0`

The model should not be changed merely because a newer model exists. The
16-case role-option evaluation scored `93.75%`, so there is no evidence that a
model replacement is required.

### Role-option fallback

The unversioned system prompt is:

> Map the candidate's reply to one of the listed public job options. Return
> JSON only. Do not invent an option.

The payload describes, but does not enforce as a strict provider schema:

- `selected_index: integer|null`
- `confidence: number 0..1`
- `reason: short string`

The result is accepted at confidence `>= 0.55` and only when the index is
within the backend-provided role list. Timeout is 12 seconds. There is no
retry. Errors, invalid JSON, low confidence, or an invalid index return `None`.
The function does not record prompt hash, model response ID, token use, cost,
latency, confidence, or failure in `llm_call_logs`.

### Screening-answer parser

The system prompt is:

> You parse candidate screening replies into structured answers for an HR
> application. Do not invent. Return JSON only.

Its output shape is:

- `answers` keyed only by backend-provided question keys
- `corrections` keyed only by backend-provided question keys
- `candidate_question`
- `unsupported_request`
- `confidence`
- `reason`

The parser labels stored evidence as `gpt_screening_reply_v1`, uses a 16-second
timeout, has no retry, and falls back to deterministic binding of the message
to the next missing question.

The nominal confidence boundary is `0.55`, but it is not a hard gate:
low-confidence answers or corrections are still accepted when non-empty. This
must be corrected before production use of natural screening replies.

### Async CV extraction

Scanned/image CVs may use bounded vision rescue after local extraction fails.
The vision result has `text`, `confidence`, and `reason`, uses a 45-second
timeout and an acceptance threshold of 0.45. Structured candidate-profile
extraction is identified as `llm_cv_profile_v1`, caps CV text at 12,000
characters, uses a 20-second timeout, and only merges at confidence `>=0.55`.
Human-authoritative fields are preserved and generic CV headings are rejected.
These calls cannot accept the CV before the backend readability gate.

## Language and locale behavior

- Versioned candidate replies support English and Arabic.
- Arabic-script detection works for MSA and tested Gulf messages.
- The separate general language detector recognizes a very small Arabizi
  vocabulary, but candidate templates use `candidate_messages.infer_locale`,
  which only checks for Arabic Unicode characters.
- The Octopus channel sends `latest_user_language`; the candidate template
  helper looks for `locale` or `language`, not `latest_user_language`.
- A locale may be stored as `raw_json.candidate_locale` and reused, but its
  initial inference is wrong for most pure Arabizi.

Measured locale accuracy:

- English: 100%
- MSA: 100%
- Gulf Arabic script: 100%
- Arabizi/mixed bucket: 26.67%
- Overall: 81.67%

## Required intent support

Strong current support:

- APPLY code: exact deterministic parser, 100% in the evaluation.
- CV upload: media-driven, 100%.
- Apply by role: 87.5% at text-extraction level; actual role resolution still
  depends on matching the extracted terms to tenant role titles.
- Explicit status phrases: 75%.
- Exact withdrawal confirmation and cancellation tokens: 75% each.

Partial support:

- Ask whether CV was received: merged into status handling, 50%.
- Replace CV: 25%.
- Withdrawal request: 37.5%.
- Speak to HR: 37.5%.
- Gulf and Arabizi variants are the main misses.

Context-only or unsupported:

- Assessment: no general intent classifier. When an active attempt exists,
  almost any otherwise-unhandled message returns the assessment link.
- Interview question: no inbound candidate handler.
- Offer question: no inbound candidate handler.
- Resume after HR handoff: supported as a backend HR task-resolution action,
  not as a candidate intent. Resolution clears the exact binding's
  `automation_paused` flag.
- Unknown or ambiguous messages: generic fallback only.

## Evaluation results

The 120-message corpus has exactly 30 examples in each group: English, MSA,
Gulf, and Arabizi/mixed. It covers all requested intents, ambiguity,
adversarial instructions, false confirmations, media, spelling variation, and
short messages.

- Intent accuracy: **57.50%**
- Entity extraction accuracy: **87.50%** on cases with an expected entity
- Language detection accuracy: **81.67%**
- False mutation attempts: **0**
- Generic unknown/fallback rate: **51.67%**
- Ambiguous/adversarial safe-unknown rate: **100%**
- Deterministic classifier p50: 0.0177 ms
- Deterministic classifier p95: 0.0784 ms
- Provider calls for the 120-message deterministic corpus: 0
- Provider cost for that corpus: 0

Per-language intent accuracy:

- English: 70.00%
- MSA: 70.00%
- Gulf: 56.67%
- Arabizi/mixed: 33.33%

The separate 16-case GPT-5.4 role-option fallback evaluation produced:

- Accuracy: 15/16, **93.75%**
- English: 4/4
- MSA: 4/4
- Gulf: 4/4
- Arabizi: 3/4
- p50 latency: 1,320.2 ms
- p95 latency: 2,419.4 ms
- Failed: `tani wa7da` did not resolve to the second listed role.

Exact monetary cost is not observable because this candidate function discards
provider usage and does not write `llm_call_logs`. This is a telemetry defect,
not evidence of zero cost.

Representative failures:

- `sent wrong cv` → unknown
- `قدمت السي في الغلط` → unknown
- `ابي ابدل الـ CV` → unknown
- `شنو صار على طلبي؟` → unknown
- `خلاص ما ابي الوظيفة` → incorrectly interpreted as apply-by-role
- `abii aqadem 3ala finance` → unknown
- `abi akalem hr` → unknown
- assessment, interview, and offer questions → unknown without special backend
  context

Representative passes:

- `I want to apply for finance`
- `ابي اقدم على الموارد البشرية`
- `ابي اكلم موظف`
- `status?`
- explicit `CONFIRM`, `CANCEL`, `تأكيد`, `إلغاء`, `اسحب`, and `خله`

## Authority boundaries

Controls that hold:

- The role LLM can select only an index in a backend-supplied list.
- It cannot invent a role accepted by the backend.
- Candidate stage mutations remain in backend lifecycle functions.
- Withdrawal requires a pending action and explicit second confirmation.
- Multiple applications fail closed through conversation/application
  resolution.
- CV acceptance is sent only after backend readability validation.
- Assessment, interview, offer, shortlist, reject, and hire remain separate
  backend actions.
- The candidate reply policy blocks several English internal-score, ranking,
  notes, decision, and salary claims.
- The 120-message adversarial set produced zero mutation attempts.

Boundary defects:

- Screening lookup is phone-based rather than exact conversation/application
  binding, and its update is scoped by `app_key` without company. LLM-extracted
  screening answers therefore need a binding hardening pass.
- Candidate intent classifications do not have a structured audit record.
- The role-option and screening LLM calls do not use strict structured output
  enforcement or standard LLM telemetry.
- Candidate reply-policy patterns are English-only.
- `public_candidate_*` handlers do not pass through the same
  `apply_candidate_reply_policy` guard as `candidate_*` handlers.

## Low-confidence and clarification behavior

There is no candidate-wide confidence score or approved low-confidence
threshold today.

- Role-option fallback uses 0.55 and returns no selection below it.
- Screening uses 0.55 only when no answer/correction/question was extracted.
- General unknown messages receive a generic capability reply.
- No durable intent-clarification object is written.
- Public role options are durable for two hours and scoped by phone, account,
  and conversation, but that session is not a general intent clarification.
- Multiple applications fail closed and ask for an APPLY code.

The requested short clarification menu is not implemented. Therefore the
system does not satisfy durable low-confidence clarification readiness.

Candidate turns also do not enter the HR classify graph or create an
`hr_turns` intent-classification record. Durable evidence is instead the
claimed `whatsapp_inbound_messages` row and its stored response, plus
screening answer evidence, lifecycle events, tasks, and conversation-binding
metadata. There is no durable candidate classification audit containing
prompt version, confidence, or extracted entities.

## Provider message-ID mapping proof

The real channel extractor accepts:

- top-level `message_id`
- top-level `messageId`
- `messages[0].id`
- the first nested extracted message `id`

For a production-shaped WhatsApp payload the authoritative field is
`messages[0].id`, for example `wamid.HBgLREADINESS0001`.

The dedupe backend itself is sound:

- Key: `(provider, account_id, provider_message_id)`
- Company is stored for audit but is not part of the unique key.
- A two-thread staging race produced one claimant, one in-flight duplicate,
  and one row.
- Reusing the same ID with changed text produced
  `identity_match=false`; the HTTP path rejects it.
- Missing provider ID has no generated/local fallback and fails closed.
- Synthetic row count returned to zero.

However, the deployed Octopus channel forwards only `source`,
`latest_user_language`, and nested `provider_payload`. It does not forward
`provider_message_id`, `message_id`, `wamid`, or `external_message_id`.
The orchestrator does not inspect nested `provider_payload`.

The resulting behavior is worse than a simple visible rejection: the
orchestrator returns `authoritative=true` with no reply text, while the channel
only accepts an authoritative result when reply text is present. Candidate
traffic can then fall through to the generic OpenClaw agent path without the
new durable candidate ingress claim. This is an authority-boundary bypass and
must be closed at the channel edge.

Production-shaped mapping result: **failed (`mapping_ok=false`)**.

This is a hard promotion blocker. The contained fix is to pass the channel's
already-extracted `messageId` as:

- `metadata.provider = "octopus"`
- `metadata.provider_message_id = messageId`

The channel must refuse candidate orchestration when `messageId` is empty. It
must not generate a local fallback inbound ID.

## Contained fixes recommended

Do not change GPT-5.4 based on this evaluation.

1. Fix the Octopus-to-orchestrator provider ID mapping and add a
   production-shaped channel contract test.
2. Add a candidate-only intent classifier after deterministic high-certainty
   handlers fail. Keep GPT-5.4 initially.
3. Use a strict versioned schema containing only intent, confidence, locale,
   role text, APPLY code, confirmation, and clarification fields. It must not
   contain action/tool names.
4. Use a proposed threshold of 0.80 for accepting an ambiguous intent.
   Consequential intents still require exact backend binding and explicit
   confirmation regardless of confidence.
5. Persist low-confidence/multi-intent clarification state against company,
   account, conversation, phone, and app key with an expiry.
6. Route the requested clarification menu through a versioned EN/AR template.
7. Reuse the general language detector for candidate locale, expand tested
   Kuwaiti/Arabizi signals, and persist the result.
8. Harden screening to exact conversation/application/company binding and make
   0.55 a true minimum before accepting LLM-extracted answers.
9. Add read-only, backend-grounded assessment/interview/offer inquiry handlers.
10. Record candidate LLM prompt version/hash, model, response ID, confidence,
    token use, latency, failure, conversation ID, app key, and selected intent.

## Prepared internal production canary plan — not executed

Authorization prerequisites:

- Written owner approval naming one internal WATHEFNI recipient, locale,
  battery/version, expiry, and execution window.
- Provider-ID mapping fix reviewed and deployed first.
- Two-person check of recipient and application/attempt identifiers.
- One-shot command with an approval nonce and an allowlist containing exactly
  the authorized recipient.

Preflight:

1. Assert runtime and database identity are production and company is exactly
   `WATHEFNI`.
2. Assert canonical lifecycle is enabled and assessment authoring remains off.
3. Validate the recipient in E.164-like form and compare its hash to the
   authorization record.
4. Create or select one marked internal synthetic application with no external
   email recipient.
5. Snapshot application stage, offer/hire state, and external-tenant counters.
6. Resolve and pin the approved battery/version and requested locale.
7. Create one attempt bound to exact company, app key, candidate, battery
   version, locale, and expiry.
8. Generate one token bound to that attempt and verify the secure URL locally.

One-shot delivery:

1. Switch only this controlled command to live delivery; all normal deployment
   automation remains unchanged.
2. Deliver exactly one assessment invitation to the allowlisted internal
   recipient.
3. Require a real provider delivery result and store provider ID, invitation
   ID, outbound event ID, attempt ID, app key, template version, and locale.
4. Stop immediately on recipient mismatch, missing conversation binding,
   ambiguous app, provider error, or any stage difference.

Verification:

1. Verify the received link opens the exact attempt and locale.
2. Verify application stage is byte-for-byte unchanged.
3. Verify no shortlist, reject, interview, offer, hire, or external-tenant row
   changed.
4. Verify delivery status is tied to the exact invitation/attempt and is not
   reported sent on provider failure.

Cleanup:

1. Revoke the token.
2. Remove the synthetic attempt, responses, score/report, invitations, and
   synthetic candidate/application rows in dependency order.
3. Remove transient conversation binding only if it was created for the
   canary.
4. Preserve a redacted immutable canary audit record; do not pretend the real
   WhatsApp message can be recalled.
5. Recount synthetic rows and external-tenant counters and require zero
   synthetic business rows and no external changes.

## Final recommendation

The staging artifact is **not safe to promote as the complete production
WhatsApp candidate experience**. Keep production frozen.

Promotion review may resume after:

- provider message-ID forwarding is fixed and contract-tested;
- the contained Gulf/Arabizi intent and durable clarification fixes pass a new
  balanced 100+ message evaluation;
- screening binding and confidence enforcement are hardened;
- the owner separately authorizes the one-recipient internal link canary.

