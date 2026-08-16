# CV Extraction V2 — Mistral Document AI

**Date:** 2026-07-27 (UTC)  
**Initial stamp:** `20260727T192901Z`  
**Routing-correction stamp:** `20260727T195947Z`  
**Host:** `root@76.13.63.68`  
**Orchestrator:** `/opt/wathefni/orchestrator` (`127.0.0.1:8010`)  
**Scope:** Long-term CV Extraction V2 with Mistral as the main document-understanding provider, plus Wathefni internal V2 fallback. No second intake pipeline. No profile UI/color changes.

**Evidence**
- Remote (initial): `/opt/wathefni/production-evidence/cv-extraction-v2/20260727T192901Z/`
- Remote (routing correction): `/opt/wathefni/production-evidence/cv-extraction-v2-routing/20260727T195947Z/`
- Local: `ops/evidence/cv-extraction-v2/` and `ops/evidence/cv-extraction-v2-routing/`
- Backups:
  - `/opt/wathefni/backups/production-pre-cv-extraction-v2-20260727T192901Z/`
  - `/opt/wathefni/backups/production-pre-cv-v2-routing-20260727T195947Z/`

---

## Final PASS / FAIL

| Gate | Result |
|---|---|
| Shared durable CV pipeline retained | **PASS** |
| PDF / scanned PDF / image / **DOCX** all use Mistral OCR 4 + Document AI as primary | **PASS** |
| Same `cv-extraction-v2` contract for all formats | **PASS** |
| No `*-latest` production authority; OCR pinned `mistral-ocr-4-0`; chat pin `mistral-small-2506` (disabled by default) | **PASS** |
| Wathefni internal extractor outputs schema-valid V2 | **PASS** |
| Simulated outage routes to internal; does not overwrite stronger Mistral current | **PASS** |
| Weak DOCX employment case improved (0 → 1) or diagnosed | **PASS** |
| No duplicate CV versions / fact snapshots / current V2 rows | **PASS** |
| Canonical profile authority unchanged (`candidate-profile-facts-v2`) | **PASS** |
| Health 200; rollback + restore | **PASS** |
| GPT Vision not used in this path | **PASS** |

**Final: PASS**

---

## Final format-routing architecture

V2 runs **inside** the existing shared durable path (`process_candidate_cv_document`). It does **not** create a parallel intake queue.

```text
inbound (email | WhatsApp | manual upload | import)
  → durable CV registration / lease / extract_candidate_cv_document
  → evidence + application-cv-facts-v1 (preserved; never replaced by V2 contract)
  → CV Extraction V2
       PRIMARY (all formats with file bytes):
         PDF | scanned PDF | image | DOCX
           → mistral-ocr-4-0
           → Document AI document_annotation (cv-extraction-v2)
       Native DOCX/PDF text:
         → preserved source evidence
         → comparison / internal input
         → NOT production DOCX authority
       FALLBACK (same cv-extraction-v2 contract):
         Wathefni internal extractor
           when Mistral unavailable / timeout / rate-limit /
           retries exhausted / explicit local policy /
           or no document bytes for OCR
  → application_cv_extraction_v2
       extractor_version = mistral-document-ai-v2 | wathefni-internal-v2
       both attempts preserved when more than one runs
  → candidate-profile-facts-v2 (publish flag)
  → person-profile API
```

### Routing rules

| Condition | Route |
|---|---|
| File bytes available (PDF/image/DOCX) | Mistral OCR 4 + Document AI |
| Mistral 429/5xx/timeout/missing key after retries | Internal V2 fallback |
| `WATHEFNI_CV_V2_FORCE_INTERNAL=true` | Internal V2 only |
| No file bytes (text-only evidence) | Internal V2 |
| Stronger Mistral current already `ready` | Internal may store as **non-current** evidence only — never silently overwrite |

GPT Vision rescue is **not** implemented on this path.

---

## Pinned model configuration

| Role | Pin | Notes |
|---|---|---|
| OCR / Document AI | `mistral-ocr-4-0` | Never `mistral-ocr-latest` |
| Optional chat intermediate | `mistral-small-2506` | Version-pinned; **default OFF** (`WATHEFNI_CV_V2_CHAT_FALLBACK=false`). Not DOCX authority |
| Internal extractor | `wathefni-internal-v2` | Local deterministic V2 contract |

DOCX OCR note: Mistral requires `image_limit=0` when not returning DOCX embedded images as base64.

### Feature flags (production)

| Flag | Value | Meaning |
|---|---|---|
| `WATHEFNI_CV_EXTRACTION_V2` | `true` | Run V2 on shared CV worker |
| `WATHEFNI_CV_PROFILE_FACTS_V2` | `true` | Publish to canonical profile facts / person-profile |
| `WATHEFNI_CV_GPT_VISION_RESCUE` | `false` | GPT Vision off |
| `WATHEFNI_CV_V2_CHAT_FALLBACK` | `false` | No chat authority |
| `WATHEFNI_CV_V2_CHAT_FALLBACK_MODEL` | `mistral-small-2506` | Pinned if ever enabled |
| `WATHEFNI_CV_V2_MISTRAL_RETRIES` | `2` | Retry budget before internal fallback |
| `WATHEFNI_CV_V2_FORCE_INTERNAL` | unset/`false` | Explicit local-processing policy |

Drop-in: `/etc/systemd/system/wathefni-orchestrator.service.d/cv-extraction-v2.conf`

---

## Modules

| Module | Role |
|---|---|
| `cv_extraction_v2_schema.py` | Strict `cv-extraction-v2` JSON schema + annotation prompt |
| `cv_extraction_v2.py` | Mistral OCR annotation, routing, validation, materialization |
| `cv_extraction_v2_internal.py` | Provider-independent Wathefni V2 extractor |
| `candidate_profile_facts.py` | Canonical projection (`v1`/`v2`) |
| `unified_person_profile.py` | Prefers V2 when publish flag is on |
| `app.py` | Shared durable hook after v1 facts |
| `ops/backfill-cv-extraction-v2.py` | Idempotent backfill |
| `ops/regress-cv-extraction-v2.py` | Regression + Yasser gates |
| `ops/prove-cv-extraction-v2-routing-correction.py` | DOCX/outage/idempotency proof |

---

## Internal extractor design

Purpose: serious **provider-independent fallback**, not a second facts system.

- Outputs the **exact** `cv-extraction-v2` schema.
- Uses native PDF/DOCX text + document structure already preserved by the durable pipeline.
- Semantic multilingual heading aliases (EN/AR), inline-field detection, deterministic block segmentation.
- Structured employment/education parsing, date/contact parsing, contamination prevention.
- Unknown/ambiguous content → `unmodeled_sections[]` (never silently dropped; never invented).

Must never:

- create a different canonical schema;
- overwrite stronger Mistral facts silently;
- invent information;
- become a competing candidate-truth authority.

Authority when both exist: Mistral current `ready` wins; internal is stored with `extractor_version=wathefni-internal-v2` and `is_current=false` unless Mistral failed / force-internal policy.

---

## V2 schema (`cv-extraction-v2`)

Supported top-level fields:

- `professional_summary`, `contact_details`, `availability`
- `employment[]`, `volunteer_work[]`, `education[]`
- `skills[]`, `languages[]`, `projects[]`, `publications[]`
- `certifications[]`, `training_courses[]`, `memberships_activities[]`
- `awards_honors[]`, `references[]`
- `unmodeled_sections[]`

Semantic classification examples (not exact heading matching): Career History → employment; Academic Background → education; Recognition/الجوائز → awards_honors; Community Service → volunteer_work; Professional Development → training_courses.

Validation remains non-destructive: immutable raw provider response preserved; warnings/moves only; integrity failures alone block publication.

---

## Outage fallback proof (`20260727T195947Z`)

From `routing-correction-proof.json`:

| Check | Result |
|---|---|
| DOCX uses `ocr_document_annotation` | **PASS** |
| Same V2 schema on DOCX | **PASS** |
| Weak Finance DOCX employment | **0 (old chat) → 1 (OCR)**; role diagnosed as simulated/academic finance intern |
| All four WATHEFNI DOCX re-extracted via OCR | **PASS** (`ocr_document_annotation`) |
| Forced internal outage route | **PASS** (`wathefni_internal_fallback`) |
| Internal schema-valid V2 | **PASS** |
| Internal does not overwrite stronger Mistral current | **PASS** (`is_current=false`) |
| No duplicate fact snapshots / current V2 apps | **PASS** |
| Canonical profile authority unchanged | **PASS** |
| Health 200 | **PASS** |
| Rollback + restore health 200; flags restored | **PASS** |

### Benchmark differences (Finance DOCX)

| Field | Mistral OCR+Annotation | Internal fallback |
|---|---|---|
| employment | **1** | 0 |
| education | 1 | 1 |
| skills | **7** | 0 |
| languages | 2 | 2 |
| projects | **2** | 1 |
| unmodeled_sections | 1 | 1 |

Internal is continuity/benchmark, not a replacement when Mistral succeeds.

### DOCX OCR results (all WATHEFNI DOCX)

| App | Path | Employment | Languages |
|---|---|---|---|
| `96550252254-…SOCIAL_MEDIA_MANAGER` | `ocr_document_annotation` | 2 | 2 |
| `96597727743-…MARKETING_SPECIALIST` | `ocr_document_annotation` | 3 | 2 |
| `96598900677-…FINANCE` (previously weak) | `ocr_document_annotation` | 1 | 2 |
| `96599652277-…SOCIAL_MEDIA_MANAGER` | `ocr_document_annotation` | 2 | 2 |

---

## Initial V2 regression (retained)

Stamp `20260727T192901Z` — WATHEFNI n=12, Yasser proof PASS, contamination 0, publish to `candidate-profile-facts-v2` after gates. See prior evidence tree for full metrics.

---

## Rollback

```bash
# Behavioral rollback
Environment=WATHEFNI_CV_PROFILE_FACTS_V2=false
Environment=WATHEFNI_CV_EXTRACTION_V2=false
systemctl daemon-reload && systemctl restart wathefni-orchestrator

# Module restore
cp /opt/wathefni/backups/production-pre-cv-v2-routing-20260727T195947Z/* \
   /opt/wathefni/orchestrator/
```

Proven at stamp `20260727T195947Z`: rollback health 200 → restore health 200 → flags back to V2 extract+publish ON.

---

## Remaining limitations

| Item | Notes |
|---|---|
| Text-only / smoke CVs | No Document AI file bytes → internal path only |
| Layout-heavy DOCX still depends on Mistral OCR quality | Internal is weaker on employment/skills for some CVs (see Finance benchmark) |
| Optional pinned chat | Available but **off**; not used as DOCX authority |
| Education honors prose | May still mention clubs inline while structured memberships also exist |
| DOCX `image_limit=0` | Embedded DOCX images are not annotated; text/layout/tables remain the OCR target |

---

## Verdict

**CV Extraction V2 architecture correction is PASS.**

Primary authority for PDF, scanned PDF, image, and DOCX is Mistral OCR 4 + Document AI on the shared durable pipeline. Wathefni internal extractor is the schema-identical continuity fallback — not a competing truth system.
