# Pre-Hiring Durable Email Ingress — Staging Live Qualification

**Status:** HELD-INTAKE QA COMPLETE — architecture phase gated  
**Date:** 2026-07-25  
**Host:** `srv1419988` (`76.13.63.68`)  
**Staging backend:** `127.0.0.1:8011` · DB `wathefni_staging`  
**Evidence (validation/scan):** `/opt/wathefni/staging/staging-evidence/durable-email-ingress-live/20260725T130436Z`  
**Evidence (accepted prep):** `/opt/wathefni/staging/staging-evidence/durable-email-ingress-live/20260725T130823Z-accepted-prep`  
**Evidence (cv extraction):** `/opt/wathefni/staging/staging-evidence/durable-email-ingress-live/20260725T131236Z-cv-extraction`  
**Evidence (held-intake QA):** `/opt/wathefni/staging/staging-evidence/durable-email-ingress-live/20260725T132319Z-held-intake-qa`  
**Production:** Postmark JSON unchanged; no production mutation  

## Verdict

Email → durable receipt → validation → ClamAV → accepted preparation → canonical `cv_extraction` → **held-intake review/QA** is complete for this single staging record.

**GO** to begin the next **contained design/architecture phase** for Talent Pool / held-intake HR presentation (read models, provenance UX, privacy/retention fields, facts-confidence display).  

**NO-GO** for implementing classification, Role Profiles, ranking, admission, outreach, persistent workers, or production changes in that next phase without a separate gate.

---

## 1. Pipeline so far (single CV)

| Stage | Result |
|---|---|
| Postmark staging inbound | durable receipt `7c65a576-…` |
| `intake_validation` | completed |
| `file_safety_scan` | completed · ClamAV clean |
| `accepted_intake_preparation` | completed · held `needs_role` |
| `cv_extraction` | **completed** (this phase) |

Source file: `Noor Tahat - CV.pdf`  
Intake document: `5d47a7c8-9e28-58b3-9a6d-44abfcaa73bd`  
Candidate document: `2e985454-ea88-4116-a2be-be821442564b`  
`app_key`: `imp-wathefni-79836cd85ba33d11-WATHEFNI-IMPORT`  
Checksum: `d951c3e27796318075c7c532be45d641e04170e3cd738081efd8ab4d5e2b2934` (unchanged)

---

## 2. Extraction job evidence

One-shot only (systemd worker never enabled):

```text
durable-email-ingress-worker.py --limit 1 --job-type cv_extraction
# processed=1 · job 10a82735-32bf-4bfe-b0ed-acbf056b4207 → completed
durable-email-ingress-worker.py --limit 1 --job-type cv_extraction
# idempotent repeat · processed=0
```

| Field | Value |
|---|---|
| Job ID | `10a82735-32bf-4bfe-b0ed-acbf056b4207` |
| Status / attempts | completed / 1 |
| Subject | candidate_document `2e985454-…` |
| Handler | `process_candidate_cv_document` (shared with WhatsApp/dashboard/bulk) |
| Run ID | `dfbeaa06-5860-4395-ac5a-442481eb7fcd` |

Workers afterward: service + timer **inactive / disabled**.

---

## 3. Local / OCR / rescue tier

| Gate | Result |
|---|---|
| Local first | **Yes** — `stage=local_extract`, `tier=poppler`, `provider=local` |
| Model requested / returned | `pdftotext` / `pdftotext` |
| Pages | 2 accepted local · `pages_needs_ocr=0` |
| Quality | `quality_ok=true` |
| Mistral OCR | **Not invoked** (not required) |
| GPT rescue | **Not invoked** (not required) |
| Billable OCR pages | 0 |
| Document method/status | `extraction_method=pdftotext` · `extraction_status=ok` · 8396 chars |

Escalation policy followed: local succeeded → no Mistral/GPT.

---

## 4. Model / version / cache / lease provenance

| Item | Evidence |
|---|---|
| `cv_extraction_runs` | 1 row · WATHEFNI · same content SHA |
| Cache hit | `false` (first local extract; OCR cache N/A) |
| Leases after run | 0 (released) |
| Engine call retention | `local_only` |
| Page dispositions | `accepted_local`, `accepted_local` |

Canonical authority tables used: `cv_extraction_runs`, `cv_extraction_cache`, `cv_extraction_leases` — same as other channels.

---

## 5. Extracted profile summary (redacted)

| Field | Value |
|---|---|
| Name | Noor Tahat |
| Contact email / phone | ***REDACTED*** (from CV text; **not** sender Gmail identity key) |
| Parser | `regex_cv_profile_v1+deterministic_contacts_v1` |
| Facts status | `ready` · confidence `0.8964` |
| Facts contract | `application-cv-facts-v1` |
| Facts extractor | `cv-facts-deterministic-v1` |
| Education entries | 12 |
| Employment entries | 1 |
| `not_found` | `[]` |
| Validation status | `accepted` |
| Semantic embed | `embedded=true` · id `application:imp-wathefni-79836cd85ba33d11-WATHEFNI-IMPORT:cv` |
| Held status | still **`needs_role`** · `current_step=import_review` |
| Job binding | none (`position_code` empty) |

Structured profile/facts/semantic artifacts were produced by the **same combined CV worker**, not an email-specific implementation. Source provenance remains import/bulk-style (`metadata.source` / `data_source_detail=bulk_import:…`).

---

## 6. Canonical cross-channel parity

| Contract element | Parity proof |
|---|---|
| Authority function | Email `cv_extraction` job → `process_candidate_cv_document` |
| Run / cache / lease tables | Shared `cv_extraction_*` |
| Extraction method | `pdftotext` also present on other staging candidate documents (`ok`) alongside `docx-stdlib` / `text` |
| Processing status fields | `extraction_status` + `extraction_method` + `extraction_chars` + text artifact |
| Structured profile / facts schema | `profile`, `facts` (`application-cv-facts-v1`), `semantic` on candidate_documents metadata |
| Escalation rules | local → (Mistral/GPT only if needed); this PDF stopped at local |
| Embedding authority | canonical semantic embed created (`semantic.embedded=true`) |
| Channel-only difference | inbound/email provenance + import batch linkage; not a separate OCR stack |

Peer method distribution on staging includes `pdftotext`/`ok` for non-email docs — same method family.

---

## 7. Cache / idempotency

| Check | Result |
|---|---|
| First extraction | completed · cache_hit false |
| Immediate one-shot repeat | `processed: 0` |
| Still exactly one `cv_extraction` job row | Pass |
| Still exactly one extraction run for document | Pass |
| Candidate / application counts unchanged by repeat | Pass |

---

## 8. Held-status and no-job-binding

| Check | Result |
|---|---|
| Application status | `needs_role` |
| `position_code` / title | unbound |
| Lifecycle admission / promote | none |
| Second candidate | none |
| Second application since inbound | none |
| Classification / ranking jobs | none created |
| Outbound since inbound | none |
| Sender Gmail used as person key | no |

Source intake checksum + quarantine object unchanged through extraction.

---

## 9. Downstream jobs

After extraction, intake job set remains only:

1. `intake_validation` completed  
2. `file_safety_scan` completed  
3. `accepted_intake_preparation` completed  
4. `cv_extraction` completed  

No automatic classification, ranking, acknowledgment, or admit jobs were enqueued.

---

## 10. Proof suite

`extract_proofs.json`: **31/31** pass (job completion, idempotency, tenant, checksum, local-tier provenance, held status, no ranking/outbound/admission, shared authority function, workers stopped, production unchanged).

Production Postmark server JSON before/after: byte-identical.

---

## 11. Unresolved risks / notes

1. Local regex/deterministic profile/skills quality is good enough for this qualification but is not LLM structuring; Mistral/GPT were correctly skipped.
2. Semantic embedding was created by the combined worker; treat any later ranking/retrieval use as a separate gated phase.
3. Held record remains invisible to active Candidates / job Ranking / Interviews / Offers under existing held-status filters — do not promote without an explicit admit/role gate.

---

## 12. Held Intake Review and QA

Read-only assessment of `Noor Tahat - CV.pdf` held record  
`app_key=imp-wathefni-79836cd85ba33d11-WATHEFNI-IMPORT`.  
No classification, ranking, admission, outreach, workers, or production changes.

### 12.1 Source-chain proof

Tenant-scoped chain is intact and traceable in staging data:

| Link | Evidence |
|---|---|
| Inbound email | `inbound_id=7c65a576-…` · Postmark · subject `my cv` · status `processed` |
| Sender provenance | `azizalmulla16@gmail.com` on inbound only |
| Original recipient | `965f89c46a9dfbca61a0831f8ba1f631@inbound.postmarkapp.com` |
| Intake route | company-wide held label · `position_code=null` · `WATHEFNI` |
| Submission | `253a016b-…` · status `accepted` |
| Source PDF | `Noor Tahat - CV.pdf` · SHA `d951c3e2…` · MIME PDF |
| Quarantine + scan | stored object matches SHA · ClamAV `clean` · sig `1.5.3/28071` |
| Held application | `needs_role` · unbound |
| Extraction run | local `poppler`/`pdftotext` · quality OK |
| Structured facts | `application-cv-facts-v1` · status `ready` |
| Semantic embedding | `embedded=true` · semantic id present |

### 12.2 Extraction accuracy review

Compared original/normalized text (8396 chars, `pdftotext`) to profile/facts **without silent correction**.

| Field | Verdict |
|---|---|
| Name | **correct** (`Noor Tahat`) |
| Email from CV | **correct** (grounded in CV text; not sender Gmail) |
| Phone from CV | **correct** (CV contact present; compat phone remains synthetic `imp-…`) |
| Summary | **correct** (present) |
| Employment | **partial_missing** — CV shows GUST RA, Oxford visiting, peer tutor, Kamco ML intern; facts.employment count = 1 |
| Education | **over_segmented/duplicated** — orgs present, but facts.education count = 12 |
| Skills | **weak/incomplete** — prose fragment only; Python/MATLAB/AWS/LangChain/Docker visible in CV text |
| Languages | **missing** — English/Arabic/Turkish in CV, facts.languages empty |
| Years of experience | **missing/null** |
| Location | **missing** — Kuwait visible in CV, no structured location |
| Certifications / courses | **missing/under-captured** — Coursera/online courses in CV, facts.certifications empty |

**Invented/unsupported:** none observed for sender-as-identity; CV contacts are evidence-grounded.  
**Duplication risk:** education over-segmentation.  
**Formatting/section-order:** Experience/Additional Information sections not fully mapped into discrete facts.

### 12.3 Identity-authority review

| Check | Result |
|---|---|
| Sender Gmail = provenance only | Pass |
| Candidate/profile email from CV evidence | Pass |
| Compatibility phone synthetic import key | Pass |
| Must not imply confirmed unique person via compat phone | Required product rule (data supports it) |
| No WhatsApp/email identity merge observed | Pass |
| Duplicate suggestions | None observed in this QA scope |

### 12.4 Held-status exclusion proof

| Surface | Result |
|---|---|
| Status | `needs_role` (`current_step=import_review`) |
| Job / `position_code` | unbound |
| Active Candidates filter | excluded |
| Job Ranking | excluded (no position) |
| Interviews / Offers | 0 rows |
| Hiring-funnel Reports filter | excluded |
| Lifecycle promote/admit | not promoted |
| Automatic outreach | no outbound since inbound |
| Real job application? | **No** — held company-wide intake |

### 12.5 Searchability proof (read-only)

| Query | Found |
|---|---|
| Candidate name `Noor Tahat` | Yes |
| Skill fragment in metadata | Yes |
| Education org `Gulf University` | Yes |
| Free-text metadata | Yes |
| Normalized text file | Yes |
| Semantic embedding | Present (`semantic_id` set); HR semantic-search UX not exercised |

No Talent Pool classification or Role Profile ranking introduced.

### 12.6 Current HR presentation gaps

Data exists for held status, filename, processing completion, and bulk-import source detail, but before Talent Pool productization HR still lacks:

1. Clear copy that this is **held because no Job/role was bound** (company-wide email intake).  
2. Explicit separation of **inbound sender** vs **CV contact**.  
3. Guardrails so synthetic `imp-…` phone is never shown as a callable number.  
4. Easy original-PDF + scan/quarantine evidence access in client HR views.  
5. Guided next actions: assign role/Job vs keep in pool vs archive.  
6. Visible facts confidence / missing-field warnings (skills/languages/employment gaps).  
7. Held-intake semantic search exposure (embedding exists; UX may not).

### 12.7 Privacy / retention gaps

Present today:

- received/durable timestamps  
- source (`bulk_import:…` / email inbound chain)

**Missing on this record** (not invented):

`privacy_notice_version`, `processing_basis` / `legal_basis`, `retention_policy` (+ version), `retention_deadline` / `retain_until`, archive/restriction/deletion state fields, consent version.

### 12.8 Cross-channel parity

| Contract | Email held record |
|---|---|
| Extraction method/status | `pdftotext` / `ok` (same family as other staging PDFs) |
| Facts authority | `application-cv-facts-v1` + `cv-facts-deterministic-v1` |
| Profile + semantic | present; embedding created by combined CV worker |
| Cache/run/lease authority | shared `cv_extraction_*` |
| Source path | `bulk_import:…` via accepted email preparation |
| Differs only by | email/Postmark provenance + company-wide **no Job bind** → `needs_role` |

### 12.9 Residual risks

1. Deterministic facts quality is not Talent-Pool-ready for skills/languages/full employment without stronger extraction or review UX.  
2. Education over-segmentation can mislead HR counts/filters.  
3. Privacy/retention metadata is not yet attached to email-held records.  
4. HR may misread import/compat identity as real contact identity.  
5. Semantic search readiness ≠ productized held-intake search.

### 12.10 Recommended next architecture phase

**Design-only / contained implementation planning** for:

1. Held-intake / Talent Pool **read model + HR presentation** (provenance, why-held, next actions).  
2. Identity display rules (sender vs CV contact vs synthetic compat key).  
3. Privacy/retention field attachment for email intake.  
4. Facts confidence / missing-evidence presentation (no silent rewrite).  

Defer classification, Role Profiles, ranking, and admit behind a later gate.

### 12.11 GO / NO-GO for beginning the next contained design/implementation phase

| Decision | Verdict |
|---|---|
| Start Talent Pool / held-intake **architecture + UX design** (and later read-model implementation) | **GO** |
| Start automatic classification | **NO-GO** |
| Start Role Profile ranking | **NO-GO** |
| Start `intake_admit` / Job binding automation | **NO-GO** |
| Start candidate/sender outreach | **NO-GO** |
| Enable persistent intake workers / production email intake | **NO-GO** |

---

## 13. Explicit non-actions (held-intake QA phase)

- No classification  
- No ranking  
- No admission  
- No contact / outreach  
- No persistent workers  
- No production changes  
- No deploy  
- No silent data correction  
