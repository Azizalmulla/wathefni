# Pre-hiring WhatsApp, inbound email, and manual CV pipeline consistency review

Date: 2026-07-26  
Scope: current `WATHEFNI` production runtime, production database (read-only), local source, and deployed systemd posture  
Production mutations: none

## Executive conclusion

The three channels do **not** currently converge through one equivalent intake authority.

- Inbound email is the only channel connected end-to-end to durable quarantine, ClamAV, CV-derived identity resolution, confirmed ownership, canonical extraction, immutable CV text versioning, and automatic Talent Pool classification.
- WhatsApp writes to the shared `candidates`, `applications`, `file_registry`, and `candidate_documents` tables, and historical WhatsApp CVs were processed by the shared extraction code. However, receipt still trusts the WhatsApp sender/application binding as candidate identity, writes directly to canonical file storage without the inbound scan/quarantine authority, and does not currently have an active worker that performs extraction or classification. A successfully attached WhatsApp CV normally belongs to a live, role-bound application; it does not enter the held Talent Pool intake view.
- Manual dashboard upload is the Import Center bulk-import path, not an attach-to-an-existing-canonical-candidate path. It creates or reuses a tenant-derived surrogate candidate key, does not use CV-derived identity resolution, does not scan or quarantine the file, and does not currently have an active extraction/classification worker.

The shared tables create partial convergence, but they do not make the authority, record identity, version model, evidence, or downstream capabilities equivalent.

Current actual architecture:

```text
WhatsApp
  -> sender/conversation/application binding
  -> direct canonical file storage
  -> candidates/applications/file_registry/candidate_documents
  -> inactive legacy CV worker

Inbound email
  -> durable submission/document
  -> tenant quarantine + ClamAV
  -> CV identity extraction + inbound_cv_authority
  -> confirmed candidate/application ownership
  -> candidates/applications/file_registry/candidate_documents
  -> bounded intake worker
  -> canonical extraction/evidence/facts/text version
  -> bounded automatic classification worker

Manual dashboard
  -> Import Center extension/metadata processing
  -> tenant surrogate candidate/application
  -> direct canonical file storage
  -> file_registry/candidate_documents
  -> inactive legacy CV worker
```

This is not yet the intended:

```text
channel intake
  -> shared scan and identity authority
  -> shared canonical candidate
  -> shared canonical CV extraction/version
  -> shared classification/search data
  -> Ranking and AI recruiter
```

## Evidence and current production posture

Relevant source:

- `wathefni-orchestrator/durable_email_ingress.py`
- `wathefni-orchestrator/inbound_cv_authority.py`
- `wathefni-orchestrator/app.py`
- deployed `candidate_cv_facts.py`
- `wathefni-orchestrator/talent_pool_auto_email_classification.py`
- `wathefni-orchestrator/unified_candidates.py`
- `wathefni-orchestrator/unified_candidates_routes.py`
- `wathefni-orchestrator/talent_pool_classification.py`
- dashboard Import Center route and UI

Read-only production service check:

| Unit | Enabled | Active | Consequence |
|---|---:|---:|---|
| `wathefni-prehire-cv-process.timer` | no | no | New WhatsApp/manual `candidate_documents` are not automatically extracted |
| `wathefni-inbound-intake-worker.timer` | yes | yes | Governed inbound-email jobs are processed |
| `wathefni-talent-pool-auto-email-classification.timer` | yes | yes | Eligible post-activation inbound-email classifications are processed |

Read-only production data snapshot:

- 10 `whatsapp_document` CV rows exist. All 10 have completed extraction and current evidence/fact snapshots from the historical worker, but there are **zero** `candidate_cv_text_versions` and **zero** classification runs for them.
- 4 CV rows are labelled `bulk_import`. Production `import_batches` currently report `email_inbound`, not a dashboard `bulk_upload`; therefore production contains no clean live sample proving the current manual dashboard journey.
- The governed email journey has a durable intake-document reference, immutable text version, current evidence/facts, and classification run.
- `candidate_documents.source='bulk_import'` is also used for inbound email. Exact email provenance remains recoverable through `import_batches.source='email_inbound'`, `import_items`, `intake_document_id`, and inbound ledgers, but the candidate-document source field alone is not channel-accurate.
- Dashboard source filters do not read every provenance location consistently. In particular, WhatsApp provenance may live in `candidate_documents.source`, CV JSON, job context, or `source_channel`, while the candidate-list SQL checks a narrower set of intake/import fields. Source filtering is therefore not a reliable channel authority.

Historical WhatsApp extraction proves that the shared extraction function can process WhatsApp documents when invoked. It does not prove current continuous processing because the only generic CV timer is disabled.

## 1. Entry and provenance

### WhatsApp CV

Entry is `handle_candidate_file_turn()` and `register_candidate_cv_file()` in `app.py`.

- Accepts media from the WhatsApp turn.
- Resolves a role/application using apply-code, conversation binding, or one eligible application.
- If the application is ambiguous or unavailable, media is held in `candidate_pending_media`.
- Once bound, the sender/application phone is used as the candidate key.
- Writes:
  - existing `candidates`/`applications`;
  - `file_registry`;
  - `candidate_documents`;
  - `applications.raw_json.cv`;
  - WhatsApp metadata including `conversation_id`, `account_id`, locale, and source.
- Document provenance is `whatsapp_document`; file-registry provenance is `candidate_whatsapp_media`.

The sender is not merely provenance. It is part of identity and application binding.

### Inbound email CV

Entry is the Postmark inbound route and `durable_email_ingress`.

- Resolves the exact tenant intake address.
- Persists submission, message, attachment, quarantine object, safety state, jobs, and audit evidence before downstream processing.
- Extracts identity from the CV while the object is still under quarantine authority.
- Treats sender email as provenance only.
- Uses `inbound_cv_authority` to create, reuse, review, or reject the candidate binding.
- Registers the authorized result through `register_imported_cv()`.
- Writes the shared application/document tables plus durable email, scan, identity, and ownership ledgers.

This is the only channel that follows the intended entry authority.

### Manual dashboard upload

The current pre-hire dashboard entry is:

`POST /dashboard/prehire/import/upload`

It is a bulk Import Center route, not a single-CV upload to an already selected candidate.

- Accepts CV files, ZIP containers, optional CSV/XLSX metadata, and optional default role.
- Creates an `import_batches` row and `import_items`.
- Derives a tenant-scoped surrogate phone:
  - `imp-{tenant}-{hash(email-or-content)}`
- Creates/reuses the candidate on that surrogate key.
- Creates an application with `needs_role`, `import_review`, or optional auto-admitted state.
- Writes `file_registry`, `candidate_documents`, and `applications.raw_json.import`.

Manual upload does not search for or bind to an existing real candidate through `inbound_cv_authority`. The same person can therefore exist as a WhatsApp/real-phone candidate and a separate import-surrogate candidate.

## 2. Security

| Control | WhatsApp | Inbound email | Manual dashboard |
|---|---|---|---|
| Server byte-signature validation | no; provider MIME is trusted | yes; detected bytes, extension, and claimed MIME must agree | no; extension and guessed MIME only |
| Malware scan | no | yes; durable ClamAV result with engine/signature evidence | no |
| Tenant quarantine before canonical storage | no | yes | no |
| Non-clean fail-closed gate | no scan authority exists | yes; only durable `clean` may continue | no scan authority exists |
| PDF structural/page checks | no receipt-time gate | encrypted/corrupt/page-limit checks | no receipt-time gate |
| DOCX archive safety | no receipt-time gate | member/expanded-size/ratio/encryption/package checks | no archive safety gate |
| Per-file size limit | no application-level limit found | 8 MiB operational default | none; only batch total |
| Total limit | upstream/provider limit unproven | 12 MiB attachment total; 24 MiB webhook | 250 MiB upload total |
| Count limit | upstream/provider limit unproven | 12 attachments | 300 top-level files; ZIP members are not equivalently bounded |

Supported types:

- WhatsApp: any provider-declared `image/*`, PDF, DOCX.
- Inbound email: PDF, DOCX, PNG, JPG/JPEG, WEBP.
- Manual Import Center: PDF, DOCX, legacy DOC, RTF, TXT, MD, PNG, JPG/JPEG, WEBP, plus ZIP as a container.

There is also a manual-format mismatch: Import Center accepts legacy `.doc` and `.rtf`, while the canonical extractor supports text, DOCX, PDF, and images. `.doc`/`.rtf` fall to `unsupported_mime` when extraction is attempted.

Security verdict: **inconsistent**. WhatsApp and manual uploads reach canonical file storage without the production inbound malware/quarantine authority.

## 3. Identity

| Behavior | WhatsApp | Inbound email | Manual dashboard |
|---|---|---|---|
| Name source before binding | existing candidate/application; role flow | extracted CV text | metadata or filename |
| Email source before binding | existing candidate/application | extracted CV text | metadata |
| Phone source before binding | WhatsApp sender/application | extracted CV text | metadata |
| Resolver | lifecycle conversation/application resolver | `inbound_cv_authority.resolve_identity()` | none |
| Existing candidate reuse | sender/application match | exact governed candidate keys; review/conflict rules | only same deterministic import surrogate |
| Unsafe ambiguity | hold pending media | `possible_match`/review or conflict; no ownership | new surrogate or metadata-derived import identity |
| Tenant isolation | company/conversation application binding; ambiguity holds | resolver queries and evidence are tenant-scoped | tenant is embedded in surrogate and application |
| Sender as provenance only | no | yes | not applicable |

Important consequences:

1. Inbound email can converge with an existing WhatsApp candidate when the CV's exact governed email/phone keys identify that candidate in the same tenant.
2. WhatsApp does not run CV-derived identity before ownership. A sender submitting another person's CV can bind it to the sender's application.
3. Manual import intentionally avoids cross-tenant merging, but it also avoids same-tenant canonical reuse. Matching email/phone is preserved in profile/import metadata while the primary candidate key remains the surrogate.
4. The shared `candidates` table is keyed by `phone`, not `(company_code, phone)`. Applications are tenant-scoped, but candidate truth itself is not a complete tenant-scoped person registry.

Duplicate handling also differs:

- WhatsApp deduplicates by application/file-kind/content hash.
- Manual import deduplicates within the batch and across company `file_registry` content hashes.
- Inbound email has durable provider/message idempotency, content hash handling, clean-scan reuse, and the import content-hash guard.

Identity verdict: **inconsistent**.

## 4. CV processing

### Shared code that exists

Once `process_candidate_cv_document()` is invoked, the channels can use the same extraction functions:

- PDF: local `pdftotext`/Poppler first.
- DOCX: local structured `cv_docx` extraction; OCR only for image candidates where required.
- Images/scanned PDF: bounded Mistral OCR with GPT vision rescue where enabled and needed.
- Canonical evidence: `application_cv_evidence_materializations`.
- Canonical facts: `application_cv_fact_snapshots`.
- Search/index material: application semantic document and candidate profile projection.

The deployed facts contract is `application-cv-facts-v1` with:

- skills;
- employment;
- experience years;
- education;
- certifications;
- languages;
- projects;
- source excerpts, confidence, hashes, extractor version, and current/superseded authority.

Seniority and normalized role/occupation signals are not base fields in that facts contract. They come from Talent Pool classification suggestions/taxonomy. That distinction matters because only inbound email is automatically classified.

### Operational divergence

| Stage | WhatsApp | Inbound email | Manual dashboard |
|---|---|---|---|
| Canonical extraction automatically invoked now | no | yes | no |
| Native PDF extraction when invoked | yes | yes | yes |
| DOCX extraction when invoked | yes | yes | yes |
| OCR/rescue when required and enabled | code-capable | yes, governed | code-capable but not continuously invoked |
| Evidence/fact snapshots | historical rows exist | yes | code-capable; current live path unproven |
| Immutable `candidate_cv_text_versions` | no production WhatsApp rows | yes | no standard automatic path |
| Automatic classification | no | yes | no |
| Seniority/role taxonomy suggestions | no current run | yes | no current automatic run |

The generic CV worker would process WhatsApp/manual documents, but it is intentionally disabled because it is not the governed bounded email worker. The inbound worker invokes the extraction directly for the one authorized intake job. Consequently, new WhatsApp and manual documents currently stop at `pending_extraction` unless an operator manually invokes the generic worker.

CV-processing verdict: **partially consistent in code, inconsistent in current operation**.

## 5. Canonical storage and authority

Shared physical tables:

- `candidates`
- `applications`
- `file_registry`
- `candidate_documents`
- candidate profile/application JSON
- extraction evidence/facts tables when extraction runs

Channel-specific evidence:

- WhatsApp:
  - `candidate_pending_media`
  - `candidate_job_contexts`
  - conversation/application bindings
  - screening answers in `applications.raw_json.screening`
- Inbound email:
  - `intake_submissions`
  - `inbound_messages`
  - `intake_documents`
  - `intake_jobs`
  - malware scan evidence
  - identity extractions/resolutions/reviews
  - ownership/binding evidence
  - immutable CV text versions
  - automatic classification jobs/runs
- Manual:
  - `import_batches`
  - `import_items`
  - import metadata and role suggestions

Authority rules are not identical:

- WhatsApp sets `applications.raw_json.cv` and creates `candidate_documents` before malware scan or CV-derived identity.
- Non-governed manual imports mark the imported CV as latest at registration.
- Governed inbound email initially records replacement/pending state and requires durable clean scan, safe identity, and confirmed ownership before current-document extraction/authority.
- `candidate_documents.source` does not retain exact inbound-email provenance; it is hardcoded to `bulk_import`. The durable joins recover the channel, but readers that use only the source column can misclassify it.

Canonical-storage verdict: **partially consistent**. The same table names are used, but record identity, provenance fields, current-version authority, and sidecar ledgers differ.

## 6. Downstream access

| Downstream | WhatsApp | Inbound email | Manual dashboard |
|---|---|---|---|
| Unified Candidates | yes after a successful application attach; active/hired views, not held intake | yes; held Talent Pool view | yes after import registration |
| Talent Pool filters/classification | not in the held Talent Pool view; no automatic classification; zero production runs | yes; automatic governed classification | held view is available, but classification is not automatic |
| CV fact/search data | historical extracted rows; new uploads currently stop | yes | only after generic extraction, currently not scheduled |
| Ranking | available for role-bound, non-held applications; existing WhatsApp records use it | held `needs_role` inbound records are deliberately excluded until promoted/bound | only if explicitly promoted/auto-admitted with a role |
| AI recruiter read/search | application/candidate is visible, with WhatsApp screening/profile evidence | candidate/application is visible; held mutation/communication remains restricted | surrogate candidate is visible, but may duplicate canonical person truth |
| Assessments | available to eligible role-bound application workflows | not while held/unbound | available only after role assignment/promotion |
| Future Role Profiles | unproven; no current channel contract | unproven; best canonical substrate | unproven |
| HR notes/review | structured fact review and live interview notes are available; no general held-candidate notes store or inbound identity-review ledger | structured fact review plus governed identity review/conflict evidence; no unified freeform notes store | import review is available; fact review depends on extraction; no unified freeform notes store |

Ranking uses the shared application/candidate/profile/search data, but it excludes `needs_role` and `import_review` through the production/reviewable predicates. Therefore “stored in shared tables” is not equivalent to “available for Ranking.”

The AI recruiter can resolve/read shared candidates and applications, but its evidence quality and safe actions differ by state. Held email/manual records remain fail-closed for communication and lifecycle actions.

The classification API/UI is separately flag-gated and can support operator-driven runs where its prerequisites exist. That is not an automatic WhatsApp/manual connection, and no production WhatsApp classification run or complete current manual-upload classification journey was found.

## 7. WhatsApp-only conversational information

The WhatsApp screening flow supports role-configured questions and defaults including:

- visa/residency status;
- salary expectation;
- availability/start date;
- relevant experience;
- tools/software;
- role-specific questions such as channels, campaign examples, content tools, account scope, or experience years.

Production contains WhatsApp answer keys including:

- `salary_expectation`
- `availability`
- `visa_status`
- `relevant_experience`
- role-specific experience/tool/channel fields

Four current WhatsApp applications have evidence explicitly marked `candidate_reply`.

Storage:

```text
applications.raw_json.screening.answers
applications.raw_json.screening.answer_sources
applications.raw_json.screening.answer_evidence
applications.raw_json.screening.questions
```

Each answer can preserve reply text, captured timestamp, parser/model, confidence, correction flag, and source `candidate_reply`. CV-prefilled answers use source `cv_prefill`.

Preferred/selected role is stored primarily as canonical application `position_code`/`position_title`, with pre-application conversational context in `candidate_job_contexts` and public candidate session metadata.

Notice period is not a universal default field in the reviewed screening schema. It may be configured as a tenant/role-specific screening question, but no dedicated canonical notice-period column was found.

These fields do not require a structurally separate WhatsApp candidate table. They are additive application evidence. However, they are not yet normalized into a shared, channel-neutral candidate-evidence contract; they remain JSON under the application and some ranking logic reads that JSON directly.

WhatsApp-only evidence verdict: **partially consistent with the intended architecture**—additive rather than a separate candidate, but not yet a fully shared evidence model.

## 8. Exact gap table

Status vocabulary is limited to: `consistent`, `partially consistent`, `inconsistent`, `not connected`, `unproven`.

| Area | WhatsApp | Inbound email | Manual dashboard | Exact gap |
|---|---|---|---|---|
| Tenant-specific entry | partially consistent | consistent | consistent | WhatsApp is conversation/application scoped but candidate key remains global phone |
| Channel provenance retained | consistent | partially consistent | consistent | Email document source is `bulk_import`; exact channel requires joins |
| Shared durable submission ledger | not connected | consistent | not connected | Only email uses durable intake submissions/documents/jobs |
| Byte-signature validation | not connected | consistent | not connected | WhatsApp/manual trust MIME/extension |
| Malware scan | not connected | consistent | not connected | No WhatsApp/manual ClamAV record |
| Quarantine | not connected | consistent | not connected | WhatsApp/manual write directly to canonical storage |
| Size/type safety | inconsistent | consistent | inconsistent | Different allowlists and limits; manual accepts extractor-unsupported DOC/RTF |
| CV-derived name/email/phone | not connected | consistent | not connected | WhatsApp uses sender/app; manual uses metadata/filename |
| Shared identity resolver | not connected | consistent | not connected | Only email uses `inbound_cv_authority` |
| Sender as provenance only | inconsistent | consistent | not connected | WhatsApp sender is identity/binding authority; manual upload has no message sender |
| Candidate create/reuse/review/conflict | inconsistent | consistent | inconsistent | WhatsApp app binding and manual surrogate do not implement email review/conflict rules |
| Cross-channel candidate convergence | partially consistent | partially consistent | inconsistent | Email can reuse existing exact identity; manual creates surrogate; WhatsApp cannot resolve from CV |
| Tenant isolation | partially consistent | consistent | consistent | Application/import scope is tenant-safe, but shared candidate key is not tenant-composite |
| Duplicate handling | partially consistent | consistent | partially consistent | Different dedupe scopes and evidence |
| Shared `candidate_documents` | consistent | consistent | consistent | All write the table |
| Identical document provenance fields | inconsistent | inconsistent | inconsistent | Source values/sidecars differ and email is labelled bulk import |
| Identical current-document authority | inconsistent | consistent | inconsistent | WhatsApp/manual may mark latest before scan/identity |
| Shared PDF/DOCX/OCR code | partially consistent | consistent | partially consistent | Shared only after worker invocation |
| Continuous extraction | not connected | consistent | not connected | Generic timer is disabled |
| Canonical evidence/facts | partially consistent | consistent | unproven | Historical WhatsApp proof; no current manual production sample |
| Immutable CV text version | not connected | consistent | not connected | Current versioning/enqueue module is email-authorized |
| Structured skills/experience/education | partially consistent | consistent | unproven | Depends on extraction running |
| Seniority/role taxonomy signals | not connected | consistent | not connected | Supplied by automatic classification, currently email only |
| Unified Candidates | partially consistent | consistent | consistent | Attached WhatsApp applications are projected, but unbound held media has no candidate row |
| Talent Pool classification/filter chips | not connected | consistent | partially consistent | Manual imports enter the held view, but no automatic/manual production classification journey was proven |
| Ranking | partially consistent | partially consistent | partially consistent | Requires non-held role-bound application; held records are excluded |
| AI recruiter | partially consistent | partially consistent | partially consistent | Shared reads exist, but authority/evidence and safe actions differ |
| Assessments | partially consistent | not connected | partially consistent | Held inbound records are not assessment-eligible until role-bound/promoted |
| Future Role Profiles | unproven | unproven | unproven | Phase and cross-channel contract are not qualified |
| HR notes/review workflows | partially consistent | partially consistent | partially consistent | Review types are split across fact, identity, import, and interview workflows; no shared freeform notes authority |
| Conversational screening evidence | consistent | not connected | not connected | Additive WhatsApp application evidence, not separate candidate truth |

## Final verdict

**The pipelines are inconsistent and must not be represented as one canonical end-to-end CV pipeline today.**

What is genuinely shared:

- the core application/candidate/document tables;
- the extraction implementation when invoked;
- evidence/fact snapshot schemas when extraction runs;
- Unified Candidates projection;
- portions of downstream application tooling.

What is not shared:

- scan/quarantine authority;
- CV-derived identity authority;
- candidate-key semantics;
- document-current authority;
- continuous extraction worker coverage;
- immutable CV text versioning;
- automatic classification;
- resulting Talent Pool classification and downstream readiness.

The narrow architectural correction is to route WhatsApp and dashboard uploads through a channel-neutral durable intake envelope that invokes the existing scan and `inbound_cv_authority` contracts, then emits one authorized canonical document/extraction event consumed by a channel-neutral bounded worker. WhatsApp conversation data should remain additional application/candidate evidence, and manual upload should be able to select or safely resolve a canonical candidate rather than always creating an import surrogate.

No production change or cleanup was performed during this review.
