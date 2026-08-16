# Pre-Hiring Talent Pool — Product and Fact Authority Design

**Status:** read-only design and authority assessment — **no implementation**  
**Date:** 2026-07-25  
**Evidence base:**  
- Staging durable email journey (receipt → validation → ClamAV → accepted prep → `cv_extraction`)  
- `ops/PREHIRING_DURABLE_EMAIL_INGRESS_STAGING_LIVE_QUALIFICATION.md` §12 Held Intake Review and QA  
- Phase 1 authority: Option B held intake (`needs_role` / `import_review`) from `ops/PREHIRING_TALENT_POOL_AUTHORITY_DESIGN_ASSESSMENT.md`  
- High-volume intake target architecture (Option B, distinct authorities, deferred Person Registry)

**Non-actions:** no code, schema, data, UI, classification, ranking, admission, outreach, workers, staging changes, or production changes from this document alone.

---

## Verdict

**GO** to treat Talent Pool Phase 1 as a **productization of held intake** (Option B), not a Person Registry.

The staging email record proves the backend authority already works for:

- durable multi-channel CV acceptance;
- held `needs_role` membership without Job binding;
- exclusion from Candidates pipeline, job Ranking, Interviews, Offers, and hiring-funnel Reports;
- canonical CV extraction / facts / embeddings;
- explicit later bridge via `intake_admit` only.

What is missing is the **HR experience, fact/evidence governance, privacy/retention fields, and search disclosure** — not a new candidate-only authority.

**NO-GO** in this phase for automatic classification, Role Profile ranking, Person Registry, outreach, or production deployment.

---

## Product goal (restated)

First-class HR experience for thousands of unsolicited / unassigned CVs from email, WhatsApp, bulk upload, dashboard upload, and future channels.

Talent Pool Phase 1 authority remains:

```text
held applications ∈ {needs_role, import_review[, import_archived]}
  → visible in Talent Pool
  → excluded from live recruiting lifecycle and job Ranking
  → enter a real Job only via explicit HR link + intake_admit
```

Do **not** introduce candidate-only or Person Registry authority now.

---

## 1. Talent Pool information architecture

### 1.1 Surface map

```text
Talent Pool overview  →  Talent profile  →  Link to Job (future confirm)
        │
        └── Intake operations (processing / failures / quarantine)
```

Clear product partitions (never mixed as one “applications” list without labels):

| Partition | Authority | Product label |
|---|---|---|
| Held intake | `needs_role` / `import_review` | **Talent Pool** |
| Live Job applications | open/reviewable lifecycle statuses with `position_code` | **Candidates / Job applications** |
| Archived intake | `import_archived` (or equivalent archive flag) | **Archived intake** |
| Restricted / deletion-pending | privacy restriction / deletion workflow | **Restricted** (not in normal counts) |

**Rule:** UI and APIs must never label held intake as a “real job application.” Preferred wording: “Held CV”, “Unassigned intake”, “Talent Pool member.”

### 1.2 Talent Pool overview

#### Columns / card fields

| Column | Source | Notes |
|---|---|---|
| Display name | CV-grounded profile name | Fallback: filename stem; never sender-only |
| Grounded contacts | CV email / CV phone | Redact/permission; show provenance “from CV” |
| Compatibility key | synthetic `imp-…` / technical subject | **Operator/debug only** — not HR primary contact |
| Source channel | email / WhatsApp / dashboard / bulk / agency | Icon + short label |
| Received at | inbound/import received timestamp | Required |
| Processing state | see §3 | Distinct badges, not one “AI processed” |
| Current CV version | latest candidate_document / intake document | Version id + filename |
| Held reason | company-wide route / no role / review required | Explicit, human-readable |
| Likely role (advisory) | only if folder hint / explicit role evidence exists | Labeled **suggestion**; never assigned Job |
| Privacy / retention state | §5 fields | Missing → show “not configured” |
| Duplicate suggestion | advisory only | Count / “possible match” |
| Archive / restriction | §5 | Separate from held reason |

#### Search, filters, saved views

**Filters (Phase 1):** channel, received date range, processing state, held reason, has grounded email/phone, facts completeness band, archive/restriction, has duplicate suggestion, CV version count.

**Saved views:** HR-owned named filter presets (tenant-scoped). No shared mutation of underlying records.

**Bulk actions that are safe in Phase 1:**

- export selected (permissioned, audited);
- archive selected (confirm);
- add HR tag / note (confirm);
- request reprocess (paid path; confirm + cost preview).

**Bulk actions forbidden:** reject-all, shortlist-all, admit-all, message-all, AI-assign-Job-all.

#### Pagination / large volume

- Keyset pagination on `(received_at DESC, app_key)`.
- Default page size 25–50; hard cap on unbounded export.
- Denormalized Talent Pool read model recommended for 10k–100k rows (see §10 schema).
- Never load live ranking or interview joins into the overview query.

### 1.3 Talent profile (single governed screen)

Sections, in order:

1. **Header** — name, held badge, channel, received at, why held, processing completeness.  
2. **Identity strip** — CV contacts vs sender provenance vs compatibility key (labeled).  
3. **Source timeline** — inbound → quarantine/scan → submission → prep → extraction runs → fact versions → HR corrections.  
4. **Documents / CV versions** — original PDF(s), checksum, scan result, download under permission.  
5. **Structured facts** — with evidence, confidence, missing/unknown, AI vs HR-confirmed (§2).  
6. **Uncertainty panel** — missing languages/skills/location etc. as “not extracted,” never “does not have.”  
7. **Identity-link suggestions** — preview / confirm / reject / unlink (§6).  
8. **Applications split** — **Held** vs **Live Job applications** as separate lists.  
9. **Privacy & retention** — notice, basis, deadline, archive/restrict/hold/delete (§5).  
10. **Actions** — Link to Job (disabled until confirm flow), archive, restrict, delete request, reprocess.

### 1.4 Intake operations

HR/operator view (may be Setup/Operations scoped):

| State | Meaning | Safe actions |
|---|---|---|
| Queued | durable receipt, jobs pending | inspect |
| Processing | validation / scan / prep / extract running | inspect |
| Failed / dead letter | terminal job failure | retry with preview; escalate |
| Unsupported / password-protected | rejected before or at validation | show reason; no silent drop |
| Quarantined / malware | fail-closed | no download to general HR; security path |
| Incomplete extraction | local/OCR partial | reprocess confirm; mark incomplete |
| Ready held | `needs_role`/`import_review` + facts ready/partial | open Talent profile |

Always show: source, route (company-wide vs job-bound), sender acknowledgment status (**off / not introduced** until separately gated).

---

## 2. Extracted-fact authority

### 2.1 Staging QA evidence (must drive design)

From Noor Tahat held QA:

| Area | Finding |
|---|---|
| Skills | weak / prose fragment; technical stack in CV not captured |
| Languages | missing though present in CV |
| Location | missing though Kuwait in CV |
| Certifications / courses | under-captured |
| Employment | thin vs multiple roles in CV |
| Education | over-segmented / duplicated |
| Name / CV email / CV phone / summary | correct and grounded |

Therefore product trust **cannot** rest on “facts ready” alone.

### 2.2 Fact authority model (per CV fact)

Every fact atom (skill, language, employer, degree, etc.) has layers:

| Layer | Authority | Mutable? |
|---|---|---|
| `raw_text_span` | normalized extracted text + page/offset or quote | Immutable per extraction version |
| `extracted_suggestion` | deterministic and/or LLM suggestion | Immutable per extraction version |
| `evidence_ref` | quote / page / section / document_version_id | Immutable |
| `confidence` / `completeness` | extractor metadata | Immutable per version |
| `hr_confirmed_value` | HR acceptance of a suggestion or typed value | Append-only event |
| `hr_correction` | HR override | Append-only event; does **not** erase source |
| `superseded_by` | points to newer fact version / event | Append-only |
| `missing_unknown` | explicit state: not extracted / unknown / not present in this CV version | Distinct from false |

**Rules**

1. AI/deterministic extractions are **advisory**.  
2. Missing ≠ negative (absence of language/cert in extraction ≠ candidate lacks it).  
3. HR corrections never overwrite source evidence or prior extraction blobs.  
4. Corrections are append-only, attributable (`actor`, `at`, `reason`).  
5. Reprocessing creates a **new extraction version**; prior review events remain.  
6. Facts from separate CV versions keep `document_version_id` provenance.  
7. Display precedence: HR-confirmed → HR-corrected → latest extracted suggestion (labeled) → missing/unknown.

### 2.3 Is `application-cv-facts-v1` enough?

**Sufficient as the extraction output contract** for the combined CV worker (keep generating it).

**Not sufficient alone** for Talent Pool governance. Needs an **additive versioned fact/evidence sidecar** (logical or physical):

```text
application-cv-facts-v1          → immutable extraction snapshot per run
talent_fact_review_events[]      → append-only HR confirm/correct/reject
talent_fact_current_projection   → read model: effective value + provenance pointer
```

Do not fork a channel-specific facts schema for email.

---

## 3. CV quality and completeness UX

### 3.1 Ban generic “AI processed”

Replace with multi-signal status:

| Signal | Example |
|---|---|
| Text extraction | local OK / OCR used / OCR failed / password-protected |
| Facts completeness | high / partial / low (section-aware) |
| Review state | unreviewed / partially confirmed / HR-corrected |
| Freshness | current / stale (newer CV uploaded) |
| Conflict | multiple CV versions disagree |

### 3.2 Completeness summary (section-aware)

Do not require every CV to have the same sections. Score only sections that are **expected or evidenced**:

```text
Completeness = f(
  identity contacts grounded?,
  summary present?,
  employment coverage vs text heuristics?,
  education coverage?,
  skills density?,
  languages if section detected?,
  certifications if section detected?
)
```

For the Noor Tahat exemplar, UI should say roughly:

> Extraction complete (local PDF text). Profile partially structured: contacts OK; employment/skills/languages incomplete; education may be over-split. HR review recommended before Job link.

Missing languages → “Not extracted from this CV” — **not** “No languages.”

---

## 4. Search authority

### 4.1 Channels of match

| Index | Matches | Disclosure label |
|---|---|---|
| Exact metadata | name, channel, dates, status | Matched metadata |
| Extracted facts | skills/education/employment suggestions | Matched AI/extracted fact |
| HR-confirmed tags/facts | confirmed only | Matched confirmed fact |
| Full CV text | normalized text | Matched CV text |
| Semantic embeddings | similarity | Semantic similarity |
| Future AI classifications | taxonomy suggestions | Matched AI classification (deferred) |

**Rule:** never silently blend confirmed and AI suggestion ranks without disclosure chips on each result.

### 4.2 Result card must show why matched

Examples:

- “Matched confirmed skill: MATLAB”  
- “Matched CV text: LangChain”  
- “Semantic similarity to query”  
- “Matched education org: GUST”  
- “Matched AI suggestion (unconfirmed): Python”

### 4.3 Large-volume search before classification

Phase 1 search stack:

1. SQL/metadata filters (held statuses only).  
2. Trigram / full-text on name + normalized text.  
3. Optional semantic top-k **within** filtered set.  
4. Always apply retention/restriction tombstones (§5).  

Do not wait for classification to ship useful search. Classification later adds advisory facets, not a rewrite.

---

## 5. Privacy, retention and deletion

### 5.1 QA gap

Staging held record has received timestamp + source, but lacks privacy notice, processing basis, retention policy/deadline, archive/restriction/deletion states.

### 5.2 Additive authority (do not invent legal values)

Attach **identifiers and versions only**; legal text and periods are owner/policy inputs:

| Field | Purpose |
|---|---|
| `source` + `received_at` | already partially present |
| `tenant_controller_code` | tenant / controller |
| `processing_basis_code` | opaque code, not prose |
| `privacy_notice_id` + `version` | notice pin |
| `retention_policy_id` + `version` | policy pin |
| `retention_deadline_at` | calculated from policy+trigger |
| `archive_state` | archived / active |
| `restriction_state` | restricted / unrestricted |
| `legal_hold_state` | hold / none |
| `deletion_request_state` | none → requested → in_progress → completed |
| `deletion_completed_at` | when done |
| `audit_tombstone_id` | content-free remnant |

### 5.3 Behavioral rules

1. Restricted or expired → disappear from normal Talent Pool search, AI context, ranking inputs, and default counts.  
2. Archive ≠ deletion (hidden from default pool, recoverable under permission).  
3. Legal hold ≠ continued recruiting use (blocks deletion; still restricted from normal use unless policy says otherwise).  
4. Deletion covers: source files, quarantine objects, extracted text, facts snapshots, embeddings, cached AI context, and **future** classification/ranking artifacts.  
5. Backups follow restore-suppression via tombstone.  
6. Sender Gmail and CV contacts follow the **same** retention/deletion rules.  
7. This design does **not** invent bases, notice wording, or retention days — owner must supply policy pack.

---

## 6. Identity presentation (Phase 1)

### 6.1 Display model

| Concept | UI treatment |
|---|---|
| Technical `intake_subject` / `app_key` | Secondary / copyable id |
| Compatibility candidate key (`imp-…` phone) | Labeled “system identity key — not a verified phone” |
| CV-grounded phone/email | Primary contacts when present |
| Sender provenance | “Email sender” / “WhatsApp sender” separate chip |
| Duplicate suggestions | Advisory list with evidence |
| HR-confirmed / rejected links | Explicit state on suggestion |

**Never** claim the compatibility surrogate is a unique real person.  
**Never** auto-merge.

### 6.2 Link workflow (design only; no Person Registry)

1. **Preview** — show both records’ contacts, sources, CVs, held/live apps, retention/holds.  
2. **Confirm** — creates append-only link event; display grouping only.  
3. **Reject** — dismiss suggestion with reason.  
4. **Unlink** — append-only reverse; does not delete underlying rows.  

Underlying held applications remain separate rows until `intake_admit` creates a real Job binding.

---

## 7. Safe HR actions

### 7.1 Read-only / no confirmation

- search / filter / saved views;  
- view Talent profile;  
- view CV/evidence under permission;  
- inspect processing / intake operations status.

### 7.2 Requires preview + confirmation

- confirm / correct extracted facts;  
- confirm / reject / unlink identity suggestions;  
- archive;  
- restrict;  
- initiate deletion;  
- reprocess with paid OCR/LLM;  
- **Link to Job** (`position_code` assign + `intake_admit`);  
- bulk archive / bulk tag / bulk export.

### 7.3 Forbidden from Talent Pool alone

- automatic rejection / shortlist;  
- interview or offer creation;  
- hiring;  
- contact / outreach / sender acknowledgment send;  
- lifecycle stage changes other than held→admitted via explicit link flow;  
- assigning a Job by AI inference.

---

## 8. Cross-channel contract

All channels converge **after safe acceptance** on the same authorities:

```text
canonical documents → cv_extraction → application-cv-facts-v1
  → embeddings → Talent Pool read model → (later) admit to Job
```

| Channel | Source-specific only |
|---|---|
| Email | Postmark recipient/route, sender Gmail provenance, company-wide vs job alias |
| WhatsApp | verified channel identity, APPLY/job context when present |
| Dashboard upload | uploader actor, optional role hint |
| Bulk import | batch id, folder hints as **suggestions only** |
| Future agency/referral | partner source tag, contractual notice pins |

**Do not** build email-specific Talent Pool, facts, or search implementations.

Staging proof: email path already lands on `bulk_import:…` preparation + shared `process_candidate_cv_document`.

---

## 9. Boundary to future classification and Role Profiles

```text
NOW (this phase)
  Talent Pool UX + fact review + privacy fields + disclosed search
        │
LATER   ├─ Classification adds advisory taxonomy (does not change held authority)
        ├─ Role Profiles add advisory pool ranking (does not admit or bind Jobs)
        └─ intake_admit remains the only bridge to live Jobs
```

### What Phase 1 must expose now (to avoid rewrite)

1. Stable Talent Pool member id (`app_key` + optional `intake_subject_id`).  
2. Document version ids + content hashes.  
3. Fact atoms with evidence refs + review events.  
4. Completeness / missing/unknown states (not false negatives).  
5. Search match provenance chips.  
6. Privacy/retention/restriction tombstone hooks.  
7. Explicit “Link to Job” action slot (wired later to `intake_admit`).  
8. Held vs live application split on profile.

### Ranking disclosure rule (future)

Weak/missing extraction must be passed to Role Profile ranking as **coverage gaps**, never as candidate weakness.

---

## 10. Closing recommendations

### Recommended Talent Pool information architecture

Three product surfaces — **Overview**, **Talent profile**, **Intake operations** — over Option B held rows, strictly partitioned from live Job applications, archived intake, and restricted/deletion-pending records.

### Fact / evidence authority

Keep `application-cv-facts-v1` as extraction snapshots; add append-only review/evidence projection so HR corrections never erase source and missing ≠ negative.

### HR correction model

Preview → confirm/correct → attributable append-only events → effective read projection; reprocess = new extraction version.

### Privacy / retention model

Additive policy pins + deadline + archive/restrict/hold/delete/tombstone; no invented legal prose in engineering.

### Identity presentation

Separate CV contacts, sender provenance, and synthetic compatibility keys; advisory duplicates with preview/confirm/reject/unlink; no auto-merge; no Person Registry.

### Search authority

Metadata + text + confirmed facts + semantic, each with match disclosure; large-volume keyset + filtered semantic; respect restriction tombstones.

### Safe action boundaries

Read-only vs confirm-required vs forbidden (no lifecycle/outreach/AI job assign from pool alone).

### Cross-channel contract

One Talent Pool / one facts / one document / one search authority; channel differences limited to provenance and route context.

### Minimum additive schema (logical)

| Additive piece | Purpose |
|---|---|
| `talent_pool_member_projection` (read model) | overview performance |
| `cv_document_versions` link table (if not already explicit) | version provenance |
| `talent_fact_review_events` | append-only HR review |
| `talent_fact_effective` projection | display precedence |
| `intake_privacy_retention` (or columns on submission/app) | notice/basis/policy/deadline/states |
| `identity_link_suggestions` + `identity_link_events` | advisory links |
| `talent_pool_saved_views` | HR saved filters |
| Optional `intake_subject_id` lazy link | future-safe without Option A |

No change to frozen Candidates lifecycle tables’ meaning; no new Person table in Phase 1.

### Exact contained implementation sequence

1. **Read model + Talent Pool overview API** (held statuses only; exclusions proven).  
2. **Talent profile API** (timeline, documents, facts with missing/unknown, identity strip).  
3. **Fact review events** (confirm/correct) + effective projection.  
4. **Privacy/retention field attachment** once owner supplies policy pack ids.  
5. **Search v1** with match disclosure (metadata/text first; semantic second).  
6. **Intake operations** views for failed/quarantine/incomplete.  
7. **Link to Job** confirm UI wiring to existing `intake_admit` (separate gate).  
8. Only later: classification facets; Role Profile advisory rank; Person Registry if still needed.

### Frozen modules that must remain untouched

- Canonical recruiting lifecycle semantics;  
- Job-based Ranking (`rank_job_applications` / `ranking_runs` current behavior);  
- Interviews / Offers / hiring-funnel Reports predicates;  
- WhatsApp APPLY hard gates;  
- Existing `intake_admit` contract (extend UX, don’t redefine);  
- Production Postmark inbound configuration;  
- Person Registry / candidate-without-application create paths.

### Owner decisions still required

1. Approve Option B Talent Pool naming (Talent Pool vs General Applications vs Import Review).  
2. Supply privacy notice ids/versions and processing basis codes.  
3. Supply retention policy ids/versions and calculation triggers.  
4. Decide whether `import_archived` appears in default pool or archive-only.  
5. Decide who may see quarantine/malware evidence (HR vs security operator).  
6. Decide paid reprocess cost confirmation UX.  
7. Decide whether department email tags are visible filters before classification ships.  
8. Approve that synthetic compatibility keys are hidden from primary HR contact UI.

### Explicitly deferred

- Automatic classification  
- Role Profile ranking  
- Person Registry / Option A  
- Outreach / sender acknowledgment productization  
- Production deployment of Talent Pool UX or email intake at scale  

---

## Alignment with staging proof

The single staging email CV (`Noor Tahat - CV.pdf`) already validates Phase 1 backend authority. This design converts that proof into the **HR product and fact-governance contract** required before Talent Pool implementation — without reopening frozen modules or pretending extraction quality is complete.

**Stop.** No implementation from this assessment.
