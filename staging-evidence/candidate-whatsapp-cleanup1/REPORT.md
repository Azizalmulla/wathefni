# WhatsApp Candidate-Flow Cleanup — Staging Result

## Verdict

Contained cleanup passed on staging in dry-run mode. Production was not touched.

- Artifact SHA-256: `56f250ec79a4d23e71f138ea3d31ce3ce2ed5a689dd02f4ecdbd661409b3985d`
- Candidate template version: `candidate_flow_v1`
- Positive proof: `49/49`
- Negative proof: `22/22`
- Focused template/intent smoke: `25/25`
- Canonical lifecycle regression: `77/77`
- Real external messages: `0`
- Synthetic cleanup after proof: applications `0`, documents `0`, inbound events `0`, HR tasks `0`

## Implemented controls

- One versioned EN/AR catalog for the 17 candidate-visible messages, including the required two-step withdrawal confirmation.
- APPLY-code and exact-role starts bind one company, conversation, phone, and application before CV mutation.
- File receipt returns only the checking message. Success/failure is sent only after readability validation.
- Replacement CVs remain pending; an invalid replacement cannot supersede the last accepted CV.
- Provider-message IDs are required and durably deduplicated before candidate-flow mutation.
- Reused provider IDs with different sender/conversation/payload identity fail closed.
- Empty or malformed WhatsApp recipients fail in dry-run and live paths.
- Arabic status, CV replacement, withdrawal, and HR-handoff intents are deterministic.
- Candidate withdrawal requires a second confirmation and creates one lifecycle audit event.
- HR handoff creates one idempotent task, pauses automation, and resumes when the task is resolved.
- Generic headings such as `CV`, `Resume`, `Curriculum Vitae`, and `السيرة الذاتية` cannot become candidate names.
- Empty permission sets grant no candidate/interview decision permissions.
- Canonical lifecycle is required at candidate ingress and explicitly enabled on staging.
- The legacy `ai-recruiter` listener is absent; only the localhost staging orchestrator listener is present.

## CV validation evidence

Accepted:

- PDF: local `pdftotext`
- DOCX English: `docx-local-v2`
- DOCX Arabic: `docx-local-v2`
- DOCX mixed Arabic/English: `docx-local-v2`
- Image: staging vision rescue
- Updated CV after successful revalidation

Rejected:

- Blank DOCX
- Corrupt DOCX
- Blank PDF
- Corrupt PDF
- Password-protected PDF
- Unsupported text attachment

Duplicate provider webhook and duplicate content produced no second candidate document. Invalid replacement preserved the previously accepted content SHA.

## Remaining defects / limits

1. Password-protected PDFs are safely rejected, but the internal extraction reason is generic (`ocr_required_mistral_disabled`) rather than a dedicated `password_protected` diagnostic.
2. Link-message proof used exact dry-run entity-bound synthetic URLs. A separate controlled provider canary is still required before production delivery.
3. Provider payload mapping must be verified to always pass the real Octopus/WhatsApp message ID; candidate ingress now refuses mutation when it is missing.
4. Text-only WhatsApp CV ingestion remains intentionally unsupported.

## Production recommendation

Do not promote automatically. The contained flow is ready for production-change review, but production should remain frozen until the provider-message-ID mapping is confirmed and a separately authorized dry-run/canary validates real assessment, interview, and offer entity links. No production action was performed.
