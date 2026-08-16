# Pre-Hiring Intake, OCR, and Talent Pool — Read-Only Audit

**Status:** audit only — **no code changes, no deploy**  
**Date:** 2026-07-25 (Kuwait)  
**Production pin at audit time:** `6018796d265c1a8d77e3bd880849b8e65f627003dc20ca544403db426d2097e1` (Kuwait pilot document journey green)  
**Host:** `root@76.13.63.68` · orchestrator `:8010` · DB `wathefni`  
**Authority:** code + live process/env + schema counts (read-only)

---

## Verdict

Wathefni has **three separate systems** that must not be collapsed:

1. **Recruiting CV OCR** — Mistral `mistral-ocr-4-0` (+ Poppler local text + GPT vision rescue) → text → LLM structuring → Voyage embedding → ranking. **Live on production** (`WATHEFNI_CV_MISTRAL_OCR=true`). OCR **can** move recruiting lifecycle (`awaiting_cv` ↔ `cv_processing` ↔ `ready_for_review`).
2. **Identity / employment-document OCR** — separate OpenAI planner vision path (`gpt-5.6-terra` default). **Only WhatsApp onboarding (+ internal backfill)** typically triggers it. Employee app, renew, and HR dashboard uploads **skip OCR**. Proposals are **`authoritative: false`**. HR review is **not** PACI/MOI/PAM verification.
3. **Inbound candidate intake** — shared import core with Postmark forwarding webhook (**ON** in production via secrets file load), optional Gmail OAuth sync (**OFF**; mailbox tables not fully present), WhatsApp APPLY, and dashboard bulk upload. Uncertain emailed CVs land in **Import Review / `needs_role`** — not a named Talent Pool. **No silent job assignment under uncertainty.**

**Largest product gaps before Setup Console:** tenant-admin self-serve for intake addresses / mailbox connect, M365/IMAP, subject/AI job matching, named Talent Pool / candidate-without-application authority, email↔WhatsApp person merge, sender acknowledgment, malware scanning, consent/retention for imported CVs, and canonical `residence` missing from the identity OCR allowlist.

---

## 1. Recruiting CV OCR

### Exact production stack (verified live)

| Layer | Production value |
|---|---|
| Master flag | `WATHEFNI_CV_MISTRAL_OCR=true` (systemd drop-in `cv-mistral-ocr.conf`) |
| GPT rescue | `WATHEFNI_CV_GPT_VISION_RESCUE=true` |
| OCR provider / model | Mistral · **`mistral-ocr-4-0`** · `POST https://api.mistral.ai/v1/ocr` |
| Local-first PDF | Poppler `pdftotext` / `pdfinfo` / `pdfimages` / `pdftoppm` |
| Vision rescue model | Planner/tool-agent · live **`gpt-5.6-terra`** (`WATHEFNI_TOOL_AGENT_MODEL`) |
| Structuring LLM | Same planner provider (default `gpt-5.6-terra`) |
| Embedding / ranking | Voyage · live **`voyage-4-large`** (post-extraction only) |
| Cost assumption (docs) | ~`$0.004` / page |

Canonical code: `wathefni-orchestrator/cv_extraction.py`, `cv_docx.py`, worker wiring in `app.py`. Design doc: `docs/CV_OCR_MISTRAL.md` (docs still say “GPT-5.4” in places; **live model is `gpt-5.6-terra`**).

### Pipeline distinction (critical)

```text
CV file
  → TEXT EXTRACTION (Poppler / DOCX XML / Mistral OCR / GPT vision rescue)
  → DETERMINISTIC contacts + regex profile
  → LLM STRUCTURED PROFILE (planner model)
  → VOYAGE EMBEDDING of extracted text → semantic_documents
  → RANKING later (similarity + other signals — not OCR)
```

OCR does **not** call Voyage. Voyage does **not** OCR. Ranking does **not** re-OCR.

### Fallback / rescue

| Tier | When |
|---|---|
| Poppler | Digital PDF with usable embedded text |
| Mistral OCR | Scanned / image-only / `needs_ocr` pages when flag ON |
| GPT vision rescue | After Mistral quality fail (flag ON with OCR) |
| Legacy image path | Images when OCR flag OFF but vision callback present |

No HTTP retry/backoff on Mistral OCR call (single attempt). Worker may re-pick `pending_extraction` docs later.

### Supported file types

| Type | Behavior |
|---|---|
| PDF | Local text and/or per-page OCR; mixed digital+scanned supported |
| Images (jpg/png/webp) | Full-file Mistral OCR / GPT rescue |
| DOCX | Local XML (`cv_docx`) + selective OCR of embedded text-candidate images |
| TXT/MD/CSV | Plain text |
| `.doc` / `.rtf` | Often **accepted** on bulk allowlist; extraction may be `unsupported` unless converted — **gap** |
| HEIC | Not on WhatsApp CV allowlist |

### Arabic / English / layout

- Arabic alone does **not** force OCR.
- Digit / bidi normalization for contacts; bilingual headings/dates.
- PDF uses `pdftotext -layout`; Mistral requests markdown tables; DOCX walks table cells.
- No dedicated multi-column reconstructor beyond Poppler layout + OCR markdown.

### Caching, leases, timeouts

| Mechanism | Detail |
|---|---|
| Cache | `cv_extraction_cache` · company-scoped SHA of content + preprocess + provider + model + options |
| Lease | `cv_extraction_leases` · ~180s single-flight per document |
| Telemetry | `cv_extraction_runs` |
| Timeouts | Mistral ~120s; GPT rescue ~45s; structuring ~20s; Voyage embed ~18s; Poppler 20–60s |

### Confidence / validation

- Local/OCR text quality gates (min chars/words, alpha ratio, mojibake).
- GPT rescue rejects low confidence (&lt; ~0.45).
- LLM profile fields merge only if confidence ≥ ~0.55.
- Human-verified fields preserved.
- Mistral page confidence scores are collected but **not** a hard reject gate.

### Partial failure

- Mixed PDFs: OCR only needed pages; merge with local text.
- Overall fail: `extraction_status=failed`; non-replacement can transition to `awaiting_cv`.
- Replacement fail: flags failure without forcing awaiting_cv.
- Embedding fail: text may still store with `embedding_status=missing`.

### Candidate facts from extraction

Into `candidates` / profile: name, email, phone, skills, summary, education, experience, languages, tools, evidence, provenance.  
Into `applications.raw_json`: processing flags / screening prefill when allowed.  
Into `semantic_documents`: full text + embedding.  
Into `candidate_documents`: text path, method, metadata (OCR blocks often stripped from stored dump).

### HR source evidence

- HR **can** preview/download the original CV and see ranking evidence strings.
- HR **does not** get OCR bbox / page-block provenance UI.

### Lifecycle mutation — **yes**

| Trigger | Stage effect |
|---|---|
| CV stored | → `cv_processing` |
| Extraction success | → `ready_for_review` (+ HR task) |
| Extraction failure (non-held, non-replacement) | → `awaiting_cv` |
| Held imports | Auto stage advance skipped |

### Cost / retention implications

- Mistral: prefer base64 direct (avoid Files API retention); docs note ~30-day Files retention if upload path used; delete helper exists.
- GPT rescue labeled ephemeral request.
- CV body/PII must not be written to general logs (documented policy).
- Voyage retention for embeddings: **not** documented in CV OCR docs.

---

## 2. Civil ID and employee-document OCR

**Separate stack from recruiting CV OCR.**  
Canonical extract: `extract_compliance_document_metadata` in `app.py` (OpenAI/planner vision, live model **`gpt-5.6-terra`**).  
Governed storage: `kuwait_pilot_document_journey.py` · `ocr_proposal` with **`authoritative: false`**.  
Encrypted Civil ID master (`kuwait_first_client_foundation.py`) exists but is **not wired** from document OCR into product HTTP/UI.

**Do not describe HR review as government verification.** Product copy and API notes state HR reviewed evidence only — **not PACI, MOI, or PAM**.

### Channel behavior (all types)

| Channel | OCR? |
|---|---|
| WhatsApp onboarding media | **Yes** (verify/classify + extract for allowlisted types) |
| Employee app onboarding upload | **No** (`extraction={}`) |
| Employee Documents renew | **No** |
| HR dashboard upload | **No** |
| Internal backfill `/orchestrator/posthire/documents/extract` | **Yes** (operator/async) |

**Raw document to external AI:** **Yes** on WhatsApp/backfill — base64 data URI of file bytes (≤8 MiB) sent to planner provider. App/dashboard/renew avoid that by skipping OCR.

### Extractor allowlist

Runs only for: `civil_id`, `passport`, `medical`, `residency`, `work_permit`.

**Gap:** canonical Kuwait type is `residence`, but allowlist/backfill still use `residency` → **canonical residence uploads do not get metadata OCR** even if extraction were invoked.

### Per-document matrix

| Document | Upload channels that trigger OCR | Skip OCR | Provider/model | Fields proposed | Logged? | HR confirmation | Masking/encryption | Failure fallback | Raw doc / ID to external AI? |
|---|---|---|---|---|---|---|---|---|---|
| **Civil ID** | WhatsApp (identity gate + extract); backfill | App, renew, HR dashboard | Planner `gpt-5.6-terra` | number, issue/expiry, nationality, full name, DOB, confidence | employee_documents metadata; compliance; `ocr_proposal`; governed events | Approve / reject / Enter dates (`correct_metadata`). UI does **not** set `confirm_ocr:true` | OCR numbers on compliance path are **plaintext**. Fernet Civil ID master path **not productized** from this OCR | WhatsApp reject on low conf / name mismatch; app upload still succeeds | **Yes** (WhatsApp/backfill) |
| **Passport** | Same as Civil ID | Same skip set | Same | Same schema; passport-focused prompt | Same | Same | Same | Same | **Yes** |
| **Residence** (canonical) | Effectively **none** via extractor (`residence` ∉ allowlist) | App/HR/renew; WhatsApp media path weak | N/A for metadata OCR | N/A unless legacy `residency` label | Journey versions if uploaded | HR review / dates | Foundation `residence_number` encrypt unused by doc OCR | HR manual dates | Classify/verify may still send image on WhatsApp if used |
| **Residency** (legacy label) | WhatsApp/backfill if labeled `residency` | App/HR | Same vision | Same generic schema | Same | Same | Same | Same | **Yes** if extract runs |
| **Work permit** | In allowlist but **not** in WhatsApp `MEDIA_REQUIRED` → rare | App/HR/renew | Same | Same | Same | Same | Identity encrypt unused | HR dates | Only if extract invoked |
| **Medical** | WhatsApp (extract after verify; no name gate); backfill | App/HR/renew | Same | Generic number/dates/name | Same | Same | None special | HR dates | **Yes** |
| **Education certificate** | Metadata OCR **no**; WhatsApp may still verify/classify | App/HR | Classify/verify only | No metadata proposal | Limited | Checklist / journey if versioned | None | Upload without OCR | Image may still hit vision for type check |
| **Employment contract** | **None** | All primary upload channels | — | — | Receipt/checklist; no compliance dual-write for contract OCR | Onboarding/journey without OCR | — | Manual | **No** for extract; not media-required |

### HR confirmation (honest legitimacy)

- Upload → `pending_hr_review`.
- Approve → `hr_reviewed` / legitimacy `hr_reviewed_only_not_government_verified`.
- Reject → re-upload required; prior approved version stays current.
- Correct metadata → HR-entered dates/number when OCR wrong/absent.
- Dashboard: “Mark as HR reviewed?” explicitly **not PACI/MOI/PAM**.

### Foundation identity OCR (unused product surface)

`stage_ocr_identity_value` / `confirm_identity_field` can stage plaintext then encrypt on confirm — **matrix/tests only; no product routes**. Do not claim encrypted Civil ID storage for the live document-OCR path.

---

## 3. Company email CV intake (`careers@company.com`)

### Supported connection methods

| Method | Status | Notes |
|---|---|---|
| **Forwarding → Wathefni intake address** | **SUPPORTED** (production ON) | Client forwards careers mailbox → `{local_part}@inbound.wathefni.ai` → Postmark inbound webhook |
| **Postmark webhook** | **SUPPORTED** | `POST /webhook/postmark/inbound`; secret fail-closed |
| **Gmail OAuth sync** | **CODED / OFF** | Read-only `gmail.readonly`; dashboard UI exists behind `WATHEFNI_MAILBOX_SYNC`; **live mailbox ingestion OFF**; `company_mailboxes` relation **absent** on prod |
| **Microsoft 365** | **UNSUPPORTED** | Declared in `MAILBOX_PROVIDERS`; adapter `NotImplementedError` |
| **IMAP** | **UNSUPPORTED** | Same |
| **Native Gmail/M365 of careers@ without Wathefni address** | **UNSUPPORTED** unless Gmail OAuth path enabled and connected |

### Production runtime (read-only)

- App loads `WATHEFNI_POSTGRES_ENV` secrets file → `inbound_email_enabled() == True`.
- `mailbox_ingestion_enabled() == False`.
- One intake address for `WATHEFNI` with **`position_code = null`** (company-wide inbox, not per-job).
- `inbound_messages` count: **6**; `import_batches` with `source=email_inbound`: **1**; held apps `needs_role`: **1**.

### Controls

| Concern | Status |
|---|---|
| Tenant isolation | **SUPPORTED** — recipient → `intake_addresses.company_code`; unknown recipient rejected |
| Mailbox permissions | Gmail path read-only when enabled; dashboard needs `settings.manage` + flag |
| Attachment extraction | Postmark base64 / Gmail download; extension allowlist |
| Types | pdf/docx/doc/rtf/txt/md/png/jpg/jpeg/webp (+ zip on bulk) |
| Duplicates | MessageID idempotency + company file checksum |
| Malware / AV | **UNSUPPORTED**; spam quarantine via score / headers only |
| Applicant acknowledgment | **UNSUPPORTED** (explicit: no auto-message on inbound) |
| Source attribution | **SUPPORTED** (`email_inbound` / mailbox provenance fields) |
| Audit | **SUPPORTED** (`inbound_messages`, import items, admin audit on address CRUD) |
| Retry | Idempotent MessageID; non-500 on processing errors to limit provider retry storms |
| Tenant-admin self-serve | **PARTIAL** — Gmail connect UI when flag on; **intake-address API exists but no dashboard client wiring found** → effectively **developer/ops** today |

---

## 4. Job matching for emailed CVs

| Mechanism | Status |
|---|---|
| Dedicated email / intake alias per job | **PARTIAL** — `intake_addresses.position_code` API; **no UI**; prod WATHEFNI address has no position |
| Job code in subject/body | **UNSUPPORTED** — subject stored as provenance only |
| Folder/label as role | Mailbox label is **filter**, not assigner; ZIP folder hint **suggests only** |
| AI job classification | **UNSUPPORTED** |
| Manual HR assignment | **SUPPORTED** — Import Review assign/confirm/archive |
| Default inbox | **SUPPORTED** — lands `needs_role` / Intake “unclear” |

### Behavior table

| Situation | Behavior |
|---|---|
| Valid open job + **explicit** intake `position_code` / exact metadata match | May **auto-admit** if `intake_auto_admit_explicit` ON; still **not** auto-messaged / auto-decided |
| Paused / closed / missing job | Not in open position set → **held** (`needs_role`) with optional non-binding suggestion |
| Several jobs / fuzzy match | Suggest only if confidence &lt; assign threshold (~0.9); **held** |
| No job mentioned | **`needs_role`**; Ranking/Candidates lists exclude held intake statuses |

**Authority rule (proven in code/smokes):** AI/metadata may **suggest** a job; uncertain CVs create a **held application**, not a silent live pipeline entry under a guessed job. WhatsApp public APPLY is stricter: hard-rejects non-open jobs.

---

## 5. Unsolicited CV / no open position

### What exists today

| Desired product | Today |
|---|---|
| General Applications inbox | **Functional stand-in:** Import Review / Intake (`needs_role`, unclear group) + company intake address without `position_code` |
| Talent Pool | **UNSUPPORTED** as named module/authority |
| Unassigned Candidates queue | **PARTIAL** — unassigned applications (blank/orphan `position_code`) |
| Candidate-only (no application) | **UNSUPPORTED** — import always creates **candidate + application** (often surrogate phone) |

### Intended safe behavior vs today

| Intended | Today |
|---|---|
| Preserve candidate + original source | **Yes** (held app + provenance) |
| Do not invent a job | **Yes** for uncertain email/bulk |
| Do not run job-specific Ranking while held | **Yes** — held statuses excluded |
| Do not advance recruiting lifecycle | **Mostly yes** until HR admits |
| HR review/tag/link later | **Yes** via Import Review assign/promote |
| Prevent duplicate candidates | **Partial** — checksum same-file; **no** email↔WhatsApp person merge |
| Consent + retention basis | **Unsupported** for email/bulk intake |
| Archive/delete per policy | **Partial** — `import_archived`; WhatsApp withdrawal elsewhere; no first-class imported-CV erasure |

**Assessment:** Needs a **new authority model** if “Talent Pool / General Applications / candidate-without-application” is a contractual product. Current authority is **import hold queue**, not talent-pool.

---

## 6. Intake-channel matrix

| Channel | Candidate? | Application? | Job required? | OCR (CV)? | Confirmation? | Duplicate handling? | HR review? | Source / consent? | Supported now? |
|---|---|---|---|---|---|---|---|---|---|
| Public job application (WhatsApp APPLY) | Yes (real phone) | Yes after convert (Stage B gated) | Yes — must be `open` | Async after store (Mistral ON in prod) | Preview / apply confirm | Same-role handling + ingress dedupe | Pipeline review | WhatsApp / apply_code; no CV-consent object | **SUPPORTED** (WhatsApp). **No** public web careers page |
| WhatsApp CV without clear role | Session / pending | Often held until role | Effectively yes | Same | Candidate messaging | Provider dedupe | Held | Channel metadata | **SUPPORTED** with hold |
| Email CV (Postmark forward) | Yes (surrogate phone) | Yes (held default) | No | Same async | **No** sender ack | MessageID + checksum | Import Review | `email_inbound`; **no consent** | **SUPPORTED** (ON) |
| Email CV (Gmail sync) | Same | Same | No | Same | No | Cursor + checksum | Import Review | `email` | **CODED / OFF** |
| Manual HR upload | Yes (surrogate) | Yes | Optional destination | Same | HR UX | Checksum | Intake or auto-admit | bulk / ATS tags; no consent | **SUPPORTED** |
| Referral | — | — | — | — | — | — | — | — | **UNSUPPORTED** |
| Unsolicited / general | Via email/bulk | Held `needs_role` | No | Same | No | Checksum | Intake | email/bulk | **PARTIAL** (queue, not Talent Pool) |
| Recruitment agency | Via bulk only | Yes | Optional metadata/ZIP | Same | HR | Checksum | Intake | ATS-export tags — **not** agency workflow | **UNSUPPORTED** as agency product |

---

## 7. Real scenarios (code / smoke / prod traces)

| Scenario | Result |
|---|---|
| CV emailed with valid job code in **subject** | **Unsupported** — subject not matched |
| CV emailed to intake address with bound `position_code` (open job) | May auto-admit; else held |
| CV emailed without job | **`needs_role`** · Ranking excluded |
| CV emailed for closed/paused job | Held (not in open set) |
| Duplicate CV email + WhatsApp | **No person merge** if identities differ (surrogate vs phone); same-file checksum only on import registry |
| Arabic scanned CV | OCR path ON in prod; Arabic alone does not force OCR |
| DOCX CV | Import + `cv_docx` extraction; selective image OCR |
| Password-protected / corrupt PDF | May store; extraction fails quality → failed / awaiting_cv paths |
| Multiple CV attachments | One import item per attachment; unsupported → failed item |
| Agency sending several candidates | Only via bulk ZIP/metadata — no agency channel |
| Non-CV attachment | Failed / unsupported item |
| Candidate deletion request | WhatsApp withdraw exists; email intake **no** automated erasure; privacy mailbox is separate |
| Cross-tenant mailbox / recipient | Rejected / isolated by company map |

Smoke assets (local): `smoke-test-inbound-email.py`, `smoke-test-mailbox-*.py`, `smoke-test-bulk-cv-import.py`, `smoke-test-tiered-intake.py`, `smoke-test-cv-extraction-ocr.py`, `smoke-test-cv-docx.py`.  
No dedicated staging-green package for mailbox/inbound was found under `ops/` green reports.

---

## Candidate vs application data model (intake)

```text
Email / bulk import
  → always creates Candidate (+ often surrogate phone identity)
  → always creates Application
  → status ∈ {needs_role, import_review, import_archived} until HR admits
  → excluded from live Ranking / Candidates predicates while held

WhatsApp APPLY (open job)
  → Candidate (phone) + Application on convert
  → enters canonical recruiting stages
  → CV worker may advance awaiting_cv → cv_processing → ready_for_review
```

There is **no** first-class “candidate without application” intake record today.

---

## What works today

- Production CV OCR (Mistral + rescue) with cache/leases and lifecycle advancement.
- Shared import core with safe hold for uncertain roles.
- Postmark forwarding intake ON for at least one company address.
- WhatsApp APPLY with hard open-job gates.
- Dashboard bulk CV import + Import Review assign/admit/archive.
- Document journey HR review with non-government legitimacy (separate from CV OCR).
- Tenant isolation on inbound recipient mapping.

---

## Hidden / developer-only configuration

| Item | Why hidden |
|---|---|
| Intake address CRUD | API exists; **no dashboard UI** found |
| `WATHEFNI_INBOUND_*` / Postmark secret | Secrets file / ops — not Setup Console |
| Gmail mailbox sync | Feature flag OFF; schema incomplete on prod |
| M365/IMAP | Named only |
| CV OCR flags | Systemd drop-ins / enable script |
| Identity OCR encrypt confirm | Foundation APIs without product routes |
| Internal document extract backfill | Orchestrator route, not HR self-serve |

---

## Production blockers / risks

1. **No Talent Pool authority** — unsolicited CVs are held applications, not a consent-aware pool.
2. **Intake admin UX missing** — companies cannot safely self-serve `careers@` → Wathefni address without ops.
3. **Gmail/M365 not production-ready** — sync OFF; M365 unimplemented; mailbox table missing.
4. **Subject/AI job matching absent** — operators expect subject job codes; product does not honor them.
5. **Email↔WhatsApp duplicates** create parallel identities.
6. **No sender acknowledgment / malware AV / intake consent-retention**.
7. **Identity OCR channel skew** — WhatsApp gets vision OCR; app/HR uploads do not; `residence` allowlist gap; Civil ID OCR plaintext on compliance path.
8. **CV OCR mutates lifecycle** — extraction failure can bounce candidates to `awaiting_cv` (by design; operators must understand).
9. **Docs drift** — CV OCR doc still mentions GPT-5.4; live rescue/structuring is `gpt-5.6-terra`.

---

## Smallest safe remediation sequence

1. **Document & freeze current contracts** (this audit) — do not expand scope into Setup Console features yet.  
2. **Setup Console / Integrations (intake)** — tenant-admin: create/rotate Wathefni intake address, show forwarding instructions, optional per-job address; keep Postmark path as default.  
3. **Import Review productization** — rename/clarify “General / Unsolicited” queue; preserve hold authority; still no silent job invent.  
4. **Fix identity OCR allowlist** — accept canonical `residence`; keep proposals non-authoritative; do not claim government verification.  
5. **Decide Talent Pool authority** — either elevate held imports into an explicit pool (candidate±application rules, consent, retention) **or** formally keep Import Review as the only unsolicited path.  
6. **Duplicate identity** — bounded email↔phone merge / link suggestions (fail-closed; HR confirm).  
7. **Only then** consider Gmail GA, M365, subject-code matching, sender ack, AV — each as its own gated project.

---

## Stop

Audit complete. **No implementation. No deploy.**  
Next owner step (separate project): Setup Console — only after explicit instruction.
