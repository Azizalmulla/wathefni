# Pre-Hiring Talent Pool — Classification Authority Design

**Status:** read-only authority and implementation design — **no implementation, no deploy**  
**Date:** 2026-07-25  
**Foundation (frozen):** Unified Candidates + Talent Pool production canary  
- master `WATHEFNI_UNIFIED_CANDIDATES_TALENT_POOL=off`  
- tenant override `WATHEFNI_UNIFIED_CANDIDATES_TENANTS=WATHEFNI` only  
- external tenants remain disabled unless separately approved  
- no global enablement in this design  

**Evidence base:**
- `ops/PREHIRING_UNIFIED_CANDIDATES_PRODUCTION_CANARY_QUALIFICATION.md`
- `ops/PREHIRING_TALENT_POOL_PRODUCT_AND_FACT_AUTHORITY_DESIGN.md` (§2 fact authority, §4 search)
- Staging held-intake QA (`ops/PREHIRING_DURABLE_EMAIL_INGRESS_STAGING_LIVE_QUALIFICATION.md` §12)
- Canonical pipeline: normalized CV text → `application-cv-facts-v1` → Voyage `semantic_documents`
- Current Unified Candidates sidecars: `candidate_fact_review_events`, `candidate_saved_views`, `candidate_record_governance`

**Non-actions:** do not implement, deploy, enable classification workers, begin Role Profile ranking, call `intake_admit`, mutate lifecycle, or change production/staging from this document alone.

---

## Verdict (design gate)

**GO** for a **contained local implementation design** of advisory, multi-label, evidence-backed Talent Pool classification — as a **separate authority** after CV extraction, under the frozen Unified Candidates canary foundation.

**NO-GO** for:
- global feature enablement;
- external tenant enablement;
- Job assignment / `intake_admit` / shortlist / reject / outreach;
- Role Profile hiring scores;
- treating classification as a substitute for stronger fact extraction without disclosure;
- shipping classification before owner decisions in §Owner decisions are recorded.

---

## Product question (restated)

Organize thousands of held CVs **even when the tenant has zero Job Openings**.

Classification answers only:

| May answer | Must not answer |
| --- | --- |
| Relevant career areas | Which Job to assign |
| Likely roles | Shortlist / reject / contact |
| Evidenced skills & industries | Suitability for a specific hiring need without Role Profile or Job |
| Seniority & experience bands | Lifecycle or Ranking outcomes |
| Confidence per suggestion | “Candidate lacks X” from missing extraction |
| Exact CV evidence supporting each label | Automatic Job binding |

Mental model:

```text
Classification  →  What kind of candidate is this?
Role Profiles   →  How well does this candidate match this hiring need?   (later, separate)
intake_admit    →  Only explicit HR bridge into a live Job                (frozen closed)
```

---

## 1. Classification authority

### 1.1 Properties (hard requirements)

| Property | Meaning |
| --- | --- |
| Advisory | Never authoritative for hiring actions |
| Tenant-scoped | Reads/writes only within `company_code`; global taxonomy is shared read-only |
| Multi-label | Multiple functions/roles/skills allowed |
| Evidence-backed | Every suggestion cites CV span / section / fact path / document version |
| Confidence-aware | Numeric score + display band; weak → refuse or `unclassified` |
| Versioned | Taxonomy + classifier + prompt/model + input snapshot versions pinned |
| Reproducible | Same inputs + versions ⇒ same suggestion set (within declared non-determinism policy) |
| HR-correctable | Confirm / reject / add / correct without erasing AI history |
| Lifecycle-independent | Never creates Jobs, changes status, ranks for a Job, or sends outreach |

### 1.2 Hard non-mutations

Classification workers and APIs must never:

- create or bind a Job / `position_code`;
- call `intake_admit` or Link to Job;
- change `applications.status` or lifecycle events;
- shortlist, reject, hire, interview, offer;
- contact a candidate (WhatsApp/email/outbound);
- overwrite HR-confirmed facts or HR-confirmed classification labels;
- interpret “not extracted” as candidate weakness;
- write Ranking evaluation artifacts for held rows;
- promote labels into Job-scoped eligibility.

Fail-closed: any attempted mutation returns **403/409/422** and is auditable.

### 1.3 Record scope

Primary targets: held Talent Pool rows (`needs_role`, `import_review`, optionally archived held under explicit filter).

Live Job applications **may** receive the same advisory labels later (same authority, same tables) but **must not** use classification to change Job lifecycle. Phase-1 implementation should prioritize held rows; live labeling is optional follow-on under the same contracts.

---

## 2. Classification input contract

### 2.1 Preferred inputs (canonical pipeline — no re-OCR)

| Input | Role | Required? |
| --- | --- | --- |
| Normalized CV text (`semantic_documents.content` or extraction text store) | Primary evidence for skills/roles when structured facts are weak | **Required** for classify |
| `application-cv-facts-v1` snapshot | Structured atoms + extractor confidence | Strongly preferred |
| HR-confirmed fact projection (`candidate_fact_review_events` effective view) | Elevates confirmed skills/employment/education | Optional; never overwritten |
| Employment / education evidence spans | Seniority, industry, role inference | Preferred |
| Existing Voyage embedding | Retrieval assist / nearest taxonomy exemplars only | Optional |
| `document_version_id` + extraction version id | Provenance + cache key | **Required** |
| Extraction quality / completeness summary | Refusal gating | **Required** |
| Source channel + language hints | Taxonomy alias selection (AR/EN) | Optional |

**Rule:** classification consumes **stored** text/facts/embeddings. Taxonomy or classifier changes **never** trigger OCR/Mistral/GPT vision re-runs.

### 2.2 Effective evidence merge (read-only)

```text
evidence_bundle =
  HR-confirmed facts (labeled confirmed)
  ∪ extracted facts (labeled extracted / unconfirmed)
  ∪ raw CV text spans (labeled text)
  ∪ embedding (labeled retrieval_assist; never sole basis for high confidence)
```

Display and scoring must keep layers distinct. Precedence for **label confirmation** later is HR events; precedence for **suggestion generation** may use all layers with disclosure.

### 2.3 Refusal / `unclassified` gates

Produce **`unclassified`** (or empty suggestions with `refusal_reason`) when any of:

1. **No usable text** (empty/near-empty normalized text; OCR failed and no local text).  
2. **Extraction completeness band `low`** and text length below threshold (e.g. < N tokens / characters — exact N is an owner decision).  
3. **Identity-only CV** (name/contacts only; no employment, education, skills, or role-bearing prose).  
4. **Conflicting unresolved document versions** without a designated current version.  
5. **Restricted / legal-hold / deletion-pending** records (do not classify into normal indexes).  
6. **Classifier/taxonomy unavailable** for tenant (config error) → soft fail, retryable; candidate remains searchable.

`unclassified` is a first-class state, not a silent empty array. Talent Pool membership and text/metadata search remain intact.

### 2.4 Fact extraction vs classification compensation

Staging QA (Noor Tahat exemplar) showed: weak skills, missing languages/certs/location, thin employment, over-segmented education — while raw CV text contained the missing stack.

| Approach | Recommendation |
| --- | --- |
| Rely on structured facts alone | **NO-GO** for strong labels |
| Classification over raw text + facts + disclosure | **GO** for advisory organization |
| Improve fact extraction first | **Parallel track** — improves HR fact UX and reduces classifier load; **not a blocker** for classification local design if classifiers must cite text evidence and refuse when weak |

Classification **may compensate** for weak skills extraction by labeling from text evidence, but must:

- disclose `evidence_kind=cv_text` vs `extracted_fact` vs `hr_confirmed`;
- avoid high-confidence role labels when only sparse text cues exist;
- never invent employment tenure not supported by text or facts.

---

## 3. Taxonomy model

### 3.1 Recommended model: global canonical bilingual tree + tenant extensions

Avoid shallow hardcoded enum lists. Use a **versioned taxonomy pack**:

```text
taxonomy_release (global)
  ├── career_function          (broad: Technology, HR, Finance, …)
  ├── likely_role              (Software Engineer, HR Generalist, …)
  ├── skill                    (Python, Excel, …)
  ├── industry                 (Banking, Oil & Gas, …)
  ├── seniority                (Intern, Junior, Mid, Senior, Lead, …)
  ├── experience_band          (0–1y, 1–3y, 3–5y, 5–10y, 10y+)
  ├── education_field          (Computer Science, Accounting, …)
  ├── certification            (when evidenced)
  └── language                 (only when evidenced in CV/facts)
```

Each node:

| Field | Notes |
| --- | --- |
| `node_id` | Stable canonical ID (`fn.technology`, `role.software_engineer`, …) |
| `node_type` | One of the dimensions above |
| `label_en` / `label_ar` | Required bilingual labels |
| `aliases[]` | Synonyms AR/EN (incl. common CV spellings) |
| `parent_ids[]` | Optional hierarchy (role → function) |
| `status` | `active` / `deprecated` |
| `release_version` | Taxonomy pack semver / date stamp |

### 3.2 Tenant extensions

| Rule | Detail |
| --- | --- |
| Custom nodes | `company_code`-scoped; IDs namespaced (`tenant.WATHEFNI.role.xxx`) |
| Mapping | Optional `maps_to_canonical_node_id` for rollup filters |
| Isolation | Tenant A cannot read/write Tenant B nodes or mutate global pack |
| Deprecation | Deprecated nodes remain readable for history; new runs skip them unless migration maps them |

### 3.3 Multi-label and ambiguity

- Candidates may receive multiple functions and roles.  
- Ambiguous / low-evidence CVs stay `unclassified` or receive only broad function at low confidence.  
- No forced single “primary folder” in Phase 1 (optional HR-chosen primary later).

### 3.4 Taxonomy releases

- Immutable published releases (`taxonomy_vYYYYMMDD` or semver).  
- Classifier cache key includes taxonomy release.  
- Changing taxonomy **stales** prior AI suggestions; does **not** rewrite HR confirmations; triggers optional reclassify queue.

---

## 4. Suggestion vs HR-confirmed authority

### 4.1 AI classification suggestions (immutable per run)

Each suggestion row:

| Field | Purpose |
| --- | --- |
| `suggestion_id` | Stable id |
| `run_id` | Classification run |
| `company_code`, `app_key` | Tenant + record |
| `node_id`, `node_type` | Taxonomy reference |
| `confidence` + `confidence_band` | e.g. high / medium / low |
| `evidence[]` | Quotes, offsets, fact paths, `evidence_kind` |
| `document_version_id`, `extraction_version_id` | Input pin |
| `taxonomy_version` | Pack pin |
| `classifier_version` | Model/prompt/code pin |
| `state` | `active` / `stale` / `superseded_by_run` |
| `created_at` | Audit |

Reclassification creates a **new run**; previous suggestions become `stale`/`superseded`. Never mutate in place.

### 4.2 HR-confirmed assignments (append-only)

| Field | Purpose |
| --- | --- |
| `event_id` | Append-only |
| `action` | `confirm` / `reject` / `add` / `correct` / `supersede` |
| `node_id` (or corrected node) | Target label |
| `actor_user_id`, `actor_email` | Attribution |
| `reason` | Optional |
| `supersedes_event_id` | History chain |
| `created_at` | Audit |

Rules:

1. HR confirmations survive AI reclassification.  
2. Rejected AI labels are excluded from “confirmed” filters and from compact row chips; may still show under “rejected suggestions” in profile.  
3. HR-added labels do not require a prior AI suggestion.  
4. Deprecated taxonomy nodes on confirmed labels require explicit migration/review UI — no silent rewrite.  
5. Effective read projection:

```text
effective_labels =
  HR-confirmed/added (minus superseded)
  ∪ AI-active suggestions not HR-rejected
     (AI never overrides HR on same node_id)
```

### 4.3 Parallel to fact review

Mirror the existing fact-review pattern (`candidate_fact_review_events`): extraction/classification snapshots immutable; HR events append-only; effective projection for UI/search.

Do **not** store classification confirmations inside `application-cv-facts-v1`.

---

## 5. Unified Candidates UX integration

### 5.1 Keep the Candidates table clean

**Do not** add permanent multi-column taxonomy grids.

Organization appears through:

- filters;
- search;
- saved views;
- candidate profile;
- **at most one** compact secondary advisory chip on the row when thresholds pass.

Example chip (only if confidence ≥ approved threshold **and** evidence present):

```text
Technology · Software Engineer
```

Chip sources precedence: HR-confirmed pair → else high-confidence AI function+role. Always tooltip: “Advisory” vs “HR confirmed.”

### 5.2 Filters (tenant-scoped)

| Filter | Values |
| --- | --- |
| Career area | taxonomy functions (confirmed and/or AI — **separate toggles**) |
| Likely role | roles |
| Skill | skills |
| Industry | industries |
| Seniority | seniority nodes |
| Experience band | bands |
| Classification confidence | high / medium / low / unclassified |
| Label authority | Confirmed only · AI suggested · Either |

Saved views may persist these filters under existing `candidate_saved_views` (extend filter JSON; no new global flag).

### 5.3 Profile panel (authoritative disclosure surface)

Show:

- all active AI suggestions grouped by `node_type`;
- confidence band + evidence quotes;
- taxonomy + classifier versions;
- confirmed / rejected / pending;
- refusal / insufficient evidence reasons;
- link to document/extraction versions used.

Actions: confirm, reject, add, correct (confirm-required). Never Link to Job from this panel.

### 5.4 Attention / Intake Operations

Classification queue failures belong in Intake Operations or a small “Classification dead letter” bucket — **not** duplicated as a second Candidates list.

---

## 6. Search interaction

Existing Unified Candidates search (metadata, CV text, extracted facts, confirmed facts, education/employment, semantic) **continues unchanged** without classification.

Classification adds:

| Addition | Behavior |
| --- | --- |
| Optional filters | §5.2 |
| Match reason chips | Distinct strings; never blended |

Proposed match reasons (additive):

- `Matched confirmed career area`
- `Matched confirmed role`
- `Matched confirmed skill`
- `Matched AI-suggested career area`
- `Matched AI-suggested role`
- `Matched classification evidence`

**Rules:**

- Do not silently mix HR-confirmed and AI-suggested into one “Matched classification” chip.  
- Semantic similarity remains `Semantic similarity` (embedding), not a classification chip.  
- Restricted/archived exclusion rules from Unified Candidates remain unchanged.  
- `unclassified` records still match text/metadata/semantic paths.

---

## 7. Processing model

### 7.1 Stage placement

```text
durable intake → validation/scan → prep → cv_extraction (text+facts+embedding)
                                              ↓
                                    classification job (async, idempotent)
                                              ↓
                                    suggestions + projection (advisory)
```

Separate **job type** (e.g. `talent_pool_classify_v1`). Not inside Ranking, not inside outbound, not inside OCR.

### 7.2 Idempotency and cache key

```text
cache_key = hash(
  company_code,
  app_key,
  document_version_id,
  extraction_version_id,
  taxonomy_version,
  classifier_version,
  input_bundle_hash
)
```

Same key ⇒ reuse prior run (no duplicate billable inference).

### 7.3 Reclassify triggers (only)

1. Source CV / document version changes  
2. Extraction version changes  
3. Taxonomy release changes (tenant opted into auto-refresh or HR bulk request)  
4. Classifier/prompt/model version changes  
5. Explicit HR “Reclassify” (confirm + cost/quota preview)

### 7.4 Queue behavior

| Concern | Design |
| --- | --- |
| Tenant fairness | Per-tenant concurrency + daily quota |
| Retry | Exponential backoff on transient model/API errors |
| Dead letter | Terminal after N failures; candidate stays in Talent Pool/search |
| Failure impact | Suggestions missing/`unclassified`; **never** remove from search or held membership |
| Priority | Newer received_at first within tenant; optional HR “classify now” bump |

### 7.5 Feature gating

Separate flag from Unified Candidates, e.g.:

- `WATHEFNI_TALENT_POOL_CLASSIFICATION=off` (master)  
- `WATHEFNI_TALENT_POOL_CLASSIFICATION_TENANTS=` (allowlist; empty ⇒ nobody)

Align with canary pattern: master OFF + tenant allowlist; never global-by-default. Initial local/staging allowlist proposal: `WATHEFNI` only.

---

## 8. Existing fact quality — classifier policy

### 8.1 Staging QA implications

| Weak area | Classifier policy |
| --- | --- |
| Skills weak vs text | Prefer text+alias match for skill nodes; disclose `cv_text`; cap confidence if no extracted corroboration |
| Languages/certs missing | Suggest language/cert **only** with explicit text or confirmed fact; else omit (not “none”) |
| Employment thin | Seniority/experience bands require date/title evidence; else low band or refuse |
| Education over-segmented | Deduplicate by org/degree before education_field labels; do not multiply confidence from duplicates |

### 8.2 False-negative avoidance

- Prefer **under-labeling** over aggressive role assignment.  
- Broad function at medium confidence beats wrong specific role at high confidence.  
- Multidisciplinary CVs: multiple labels OK; do not force a single primary.  
- Career-change CVs: label **evidenced** recent and historical areas separately; do not invent “target role intent” without text support.

### 8.3 Extraction improvement track (parallel, not blocking)

Recommended later hardening (separate remediation): skills densification, language section detection, employment coverage vs text heuristics, education de-dupe. Classification design assumes these remain imperfect and therefore **must** use text + refusal rules.

---

## 9. Role Profiles boundary

| Authority | Question | Output |
| --- | --- | --- |
| Classification | What kind of candidate is this? | Multi-label taxonomy + evidence + confidence |
| Role Profile ranking (future) | How well does this match a hiring need? | Score vs Profile criteria + CV evidence |
| Job Ranking (frozen) | How do applicants rank for this Job? | Existing Ranking authority |

**Classification must not produce a hiring score.**

Future Role Profile ranking may:

- use confirmed (and optionally high-confidence AI) labels as **pre-filters**;
- still ground the final score in Profile criteria and CV evidence;
- treat missing extraction / missing classification as **coverage gaps**, never candidate weakness.

No Role Profile implementation in this design phase.

---

## 10. Qualification design (tests to require later)

| Case | Expectation |
| --- | --- |
| Clear software/IT CV | Function Technology + role Software Engineer (or equiv.) with text/fact evidence |
| Clear HR CV | Function HR + likely HR role |
| Clear finance CV | Function Finance + likely finance role |
| Multidisciplinary CV | ≥2 functions/roles; no forced single primary |
| Career-change CV | Labels for evidenced history; no invented target Job |
| Low-information CV | `unclassified` or low-confidence broad only |
| Arabic / English / bilingual CV | Correct alias path; bilingual labels on nodes |
| Skills missing in facts but present in text | Skill suggestions from text with disclosure; not silent |
| Conflicting CV versions | Classify current version only; stale suggestions on old version |
| HR-confirmed classification | Survives reclassify; AI cannot overwrite |
| Taxonomy version change | Prior AI stale; HR confirmations retained; new run version-pinned |
| Tenant extension | Visible only to owning tenant; maps to canonical when configured |
| Cross-tenant isolation | No reads/writes across `company_code`; global taxonomy read-only |
| Reclassification idempotency | Same cache key ⇒ no duplicate active runs |
| Non-mutation | Zero lifecycle / Job / Ranking / outbound / `intake_admit` side effects |
| Search without classification | Still works |
| Search with classification | Distinct confirmed vs AI match reasons |

Synthetic names/documents only in local/staging; production canary tenant remains flag-gated.

---

## Closing recommendations

### Recommended taxonomy model

**Global versioned bilingual taxonomy pack** (functions, roles, skills, industries, seniority, experience bands, education fields, certifications, languages) with **tenant-scoped extension nodes** and optional canonical parent mapping. Stable IDs, aliases, deprecation with explicit migration — not a shallow hardcoded list.

### Classification input contract

Require normalized CV text + document/extraction version ids + completeness summary; prefer `application-cv-facts-v1` and HR-confirmed fact projection; optionally use existing embeddings as retrieval assist only. **Never re-OCR** on taxonomy/classifier change.

### Confidence and refusal rules

Confidence bands with evidence; refuse/`unclassified` on empty text, identity-only CVs, low completeness without text, unresolved version conflicts, or restricted privacy states. Prefer under-labeling; missing extraction ≠ weakness.

### Suggestion vs HR-confirmed authority

Immutable AI suggestion runs + append-only HR confirm/reject/add/correct events; reclassify never overwrites HR; effective projection keeps layers separate for filters and search chips.

### Queue and versioning model

Async idempotent `talent_pool_classify_v1` after extraction; versioned cache key; tenant quotas; retry + dead letter; failure leaves Talent Pool/search intact; reclassify only on document/extraction/taxonomy/classifier change or explicit HR request.

### Unified Candidates UX integration

No multi-column table bloat: filters, saved views, profile evidence panel, optional single compact chip above threshold. Additive disclosed search reasons; search works without classification.

### Minimum additive schema (logical)

| Piece | Purpose |
| --- | --- |
| `taxonomy_releases` + `taxonomy_nodes` | Global pack |
| `taxonomy_tenant_nodes` + optional `taxonomy_tenant_maps` | Tenant extensions |
| `candidate_classification_runs` | Version-pinned runs + cache key + status |
| `candidate_classification_suggestions` | AI labels + evidence + confidence + active/stale |
| `candidate_classification_review_events` | Append-only HR confirm/reject/add/correct |
| `candidate_classification_effective` (projection or materialized view) | Filter/search performance |
| Feature flags | Master OFF + tenant allowlist (canary pattern) |

No changes to meaning of frozen lifecycle tables; no Person Registry; no Ranking artifact tables for classification.

### Contained implementation sequence (local only, later approval)

1. Schema + taxonomy pack v1 (fixtures) + unit contracts.  
2. Classifier adapter (deterministic first optional; LLM second) producing versioned suggestion runs from stored text/facts.  
3. HR review events + effective projection APIs.  
4. Unified Candidates filters / profile panel / match reasons (feature-flagged).  
5. Async queue worker + idempotency + DLQ (local/staging).  
6. Qualification matrix (§10) on synthetic fixtures.  
7. Stop — no production enablement without separate canary approval.

### Frozen authorities that remain untouched

- Unified Candidates canary posture (master OFF; `WATHEFNI` tenant override).  
- Candidates C0–C3 lifecycle, Ranking, Reports, Interviews, Offers/Hiring, Assessments, Assistant.  
- `intake_admit` / Link to Job (disabled).  
- Outbound / outreach.  
- OCR / durable email worker contracts (classification does not re-OCR).  
- Person Registry (not started).  
- Role Profile ranking (not started).

### Owner decisions required

1. Initial taxonomy pack ownership and bilingual review process.  
2. Confidence thresholds for compact row chip vs profile-only display.  
3. Auto-reclassify on taxonomy change: on / off / opt-in per tenant.  
4. Whether live Job applications receive labels in the same phase as held Talent Pool.  
5. Classifier provider (deterministic+LLM mix), model pin, and cost quotas.  
6. Minimum text-length / completeness cutoffs for `unclassified`.  
7. Whether fact-extraction hardening is a parallel sprint before first staging canary of classification.

### GO / NO-GO for local implementation

| Gate | Verdict |
| --- | --- |
| Proceed to **contained local implementation** of this classification authority (flagged off; no deploy) after owner decisions above | **GO** |
| Global enablement / external tenants / production classification worker | **NO-GO** |
| Role Profile ranking / Job assignment / outreach | **NO-GO** |
| Treating classification as hiring authority | **NO-GO** |

---

## Stop line

Design complete. **Do not implement. Do not deploy. Do not begin Role Profile ranking.**  
Keep Unified Candidates production canary frozen: master OFF, `WATHEFNI` only.
