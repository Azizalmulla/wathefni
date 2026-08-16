# Pre-hiring AI recruiter candidate-knowledge review

Date: 2026-07-26  
Production snapshot: 2026-07-26 17:02:25 UTC  
Scope: current deployed `WATHEFNI` runtime, production database (read-only), and local source  
Production mutations: none

## Executive conclusion

No: the current AI recruiter does **not** know all available details about every candidate.

It has two materially different read paths:

1. `rank_candidates` can search a tenant-scoped subset of live production applications, use an application-level semantic CV index for ranking, and return at most 10 summarized candidates.
2. `candidate_cv_evaluation` can load one resolved application and up to the first 6,000 characters of that application's `semantic_documents.content`.

Neither path assembles the complete canonical candidate record. In particular, the AI recruiter does not query:

- `candidate_cv_text_versions`;
- `application_cv_fact_snapshots`;
- `candidate_classification_runs` or `candidate_classification_suggestions`;
- `inbound_cv_identity_resolutions` or `inbound_cv_identity_reviews`;
- `candidate_fact_review_events`;
- `candidate_job_contexts`;
- canonical assessment, interview, or stored ranking tables in the active registry rank query.

Some of the same facts may be visible indirectly through `candidates.profile`, `applications.raw_json`, screening mirrors, or truncated CV text. That is partial access, not canonical retrieval.

The intended behavior is therefore **not implemented end-to-end**:

```text
Current:
tenant-scoped live application search
  -> optional application semantic document
  -> limited candidate/application JSON
  -> top 10 summary

Specific candidate:
resolved application
  -> first 6,000 characters of semantic_documents.content
  -> limited stage/CV/assessment/notes summary

Not current:
canonical candidate
  -> all CV versions and structured facts
  -> classification, identity, assessments, rankings, notes and channel evidence
  -> one authorized complete candidate context
```

## Verdict

**NO-GO for claiming complete AI recruiter candidate knowledge.**

The recruiter is useful for:

- semantic discovery of live, indexed applications;
- semantic ordering plus direct position/status boosts;
- reading a bounded portion of one indexed CV;
- reasoning over profile/application JSON that happens to be present;
- targeted candidate status/evaluation questions.

It is not currently a complete candidate knowledge layer and cannot reliably answer detailed questions from all authoritative evidence stored in the database.

The live deterministic rank scorer is also degraded by an argument mismatch, and the dedicated `compare_candidates` implementation is not registered in the live tool catalog.

## Status definitions

- **fully accessible**: the active recruiter path reliably loads the authoritative current value.
- **partially accessible**: only a subset, mirror, unstructured text occurrence, truncated value, or path-dependent representation is loaded.
- **not accessible**: the data exists or can exist, but the active recruiter path does not query it.
- **not indexed**: the current source journey has no recruiter semantic/profile index available.
- **unproven**: current production has no representative completed source journey proving the behavior.

## 1. Active recruiter retrieval surfaces

### Broad search: `rank_candidates`

The active action-registry executor:

- requires a tenant/company context;
- queries `applications` and joins `candidates`;
- optionally joins one `semantic_documents` row by `entity_type='application'` and `entity_key=app_key`;
- uses Voyage query embeddings when configured;
- applies `production_application_predicate`;
- excludes `needs_role`, `import_review`, and `import_archived`;
- excludes hired, rejected, and withdrawn records unless a finalized status is explicitly requested;
- orders by vector distance when an embedding is available;
- considers at most 500 application rows;
- deduplicates by candidate name first, then phone;
- returns at most 10 candidates;
- does not page through the remaining pool;
- does not join canonical CV facts, classifications, identity review, candidate evidence, or candidate CV text versions.

The rows supplied to the intended deterministic scorer contain:

- application fields and `applications.raw_json`;
- `candidates.profile` and `candidates.raw_json`;
- `semantic_documents.content`;
- any screening data mirrored into application JSON.

However, the live registry executor currently calls `rank_candidate_row` without its required `role_profile` argument. The broad exception handler converts that failure to:

- score `0.0`;
- empty score breakdown;
- empty evidence;
- low confidence;
- no matched terms.

Position and status boosts can still be added after that fallback. SQL semantic ordering is also preserved when otherwise-equal rows are stably sorted. Therefore the live broad path is currently better described as **semantic SQL retrieval plus optional position/status boosts**, not functioning deterministic skill/experience ranking.

The final model does not receive the complete semantic CV body from `rank_candidates`; it receives the selected candidate summaries and profile/application JSON. Current deterministic evidence/reasons are empty unless added by a direct position/status boost.

### Specific candidate: `candidate_cv_evaluation`

This path first resolves one application by app key, phone, email, or name. It then returns:

- app key;
- candidate name;
- job/position;
- stage/current step;
- CV received status;
- `semantic_documents.content`, truncated to 6,000 characters;
- a current ranking score only if mirrored in application JSON;
- assessment status/score only if mirrored into the application summary;
- a generic notes value selected from application/screening JSON;
- last application activity;
- prior-turn ranking score/reasons if the candidate was ranked in the same scoped conversation.

It does **not** dynamically assemble structured skills, employment, education, classification, identity, assessment reports, prior applications, or channel evidence from their canonical tables.

The executor also returns the resolved `applications` row. This can expose WhatsApp screening fields if they are stored in `applications.raw_json`, but it still does not join a complete candidate evidence graph.

### Candidate comparison

`compare_candidates` is present in legacy code, documentation and the permission map, but is **not registered in the live action-registry tool catalog**. The current AI recruiter therefore has no live dedicated comparison tool.

It can receive several candidates from `rank_candidates` and phrase a comparison from those bounded summaries, but this is not a canonical comparison authority. The dormant legacy comparison is also narrow: stage, CV status, assessment mirror, ranking mirror, one note and last activity—not full CV facts or evidence.

### Conversation memory

The tool-call orchestrator keeps:

- at most 10 history messages;
- at most the last three tool outputs in saved state;
- at most five summarized candidates in the previous-result summary;
- at most 4,000 CV-text characters when a prior candidate context is copied into the next state summary.

This is conversation continuity, not a persistent candidate knowledge index.

The stored tool output itself is not size-capped before being returned to the model in the current turn. Large profile/application JSON can therefore consume context unpredictably even though the explicit CV field is capped.

## 2. Dynamic retrieval versus cached/profile summaries

The answer is mixed, but mostly limited.

Dynamic on each relevant tool call:

- `applications`;
- `candidates`;
- one application-level `semantic_documents` record;
- current tenant and actor permission context.

Materialized or cached inputs:

- `semantic_documents.content` is a materialized copy of extracted application CV text;
- `semantic_documents.embedding` is generated from only the first 12,000 characters of that content;
- `candidates.profile` is a parsed/materialized profile;
- `applications.raw_json` contains operational and screening mirrors;
- prior-turn rank results are read from conversation state.

Not dynamically loaded:

- immutable canonical CV text versions;
- current structured CV fact snapshots;
- classification results;
- identity-review evidence;
- all previous applications;
- canonical assessment reports in the active registry query;
- canonical ranking-evaluation history.

The recruiter therefore does not dynamically retrieve “everything known about this person.” It retrieves an application-centric subset.

## 3. Search scale and semantic retrieval

### Can it search thousands of candidates?

Partially.

- It does not require a candidate ID for broad `rank_candidates` search.
- With a query embedding, PostgreSQL orders eligible rows by vector distance and returns at most the nearest 500 rows for Python scoring.
- The response is capped at 10 candidates.
- There is no recruiter pagination or “next 500” continuation.
- With thousands of eligible applications, candidates outside the first 500 semantic neighbors are not considered.
- Without a usable embedding provider, the query falls back to at most 500 status/recency-ordered rows. It does not scan the whole pool despite the executor's success message saying it did.
- The current Python deterministic scorer fails closed to zero because the live executor omits the required `role_profile` argument. Vector order and direct position/status boosts, rather than functioning evidence scoring, determine the current result order.

### Does it use semantic search or embeddings?

Yes, conditionally.

- Query provider: Voyage.
- Default model: `voyage-4`.
- Search operator: pgvector cosine distance, `embedding <=> query_vector`.
- Document embedding input: only the first 12,000 characters of the application CV content.
- Query embedding failure degrades silently to non-semantic limited-pool ranking.
- Rows with no embedding sort after embedded rows and may be excluded by the 500-row pool cap.

Semantic search is therefore implemented, but it is application-index dependent and bounded.

## 4. Production indexing by source

Read-only production snapshot:

| Source | CV documents | Extracted OK | Indexed application semantic records | Embeddings | Profiles | Immutable text versions | Fact snapshots | Classification runs |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Inbound email | 4 | 4 | 2 | 2 | 2 | 2 | 2 | 2 |
| WhatsApp | 10 | 10 | 11 | 11 | 10 | 0 | 10 | 0 |
| Manual dashboard upload | 0 proven current samples | 0 proven | 0 proven | 0 proven | 0 proven | 0 proven | 0 proven | 0 proven |

Important qualifications:

- The 4 inbound-email document versions belong to 2 applications. Both applications have a semantic record, but the index is application-level, so it does not preserve 4 separately searchable CV versions.
- All 4 inbound-email semantic contents observed through their application joins are longer than the 6,000-character candidate-context cap. Current email candidate evaluation is therefore demonstrably truncated.
- Current inbound-email semantic contents range from 6,680 to 8,396 characters.
- Existing WhatsApp semantic contents range from 129 to 2,363 characters, within the current 6,000-character single-candidate cap.
- The 10 WhatsApp records are historical outputs. The current generic WhatsApp/manual CV processing timer remains disabled, so this does not prove continuous indexing for new WhatsApp CVs.
- No current production manual-dashboard `bulk_upload` sample proves extraction or indexing. Current bulk-import rows are inbound-email imports.

### Are all processed email CV candidates indexed?

At application level, yes for the current production sample:

- 2 distinct extracted inbound-email applications;
- 2 application semantic records;
- 0 extracted inbound-email applications without a semantic record.

At document/version level, no:

- 4 extracted inbound-email CV document versions;
- 2 application semantic records;
- the semantic ID is application-scoped and later CV processing updates the same application index.

Additionally, both current held `needs_role` applications are indexed and embedded, but broad recruiter ranking excludes them.

### Checkout versus deployed authority

The production database and deployed runtime include the evidence/fact materialization path used by inbound email. The local checkout does not contain the deployed `candidate_cv_facts.py` / `candidate_cv_evidence.py` authorities or the complete production extraction-to-classification hook as ordinary runtime modules; parts remain represented by deployment patch scripts.

This does not change the retrieval conclusion—the live recruiter still does not query those tables—but it means the complete production materialization path cannot currently be reproduced from the checked-in runtime alone.

## 5. Source-specific knowledge behavior

### Inbound email CV

Current completed email candidates receive:

- application and candidate rows;
- application-level semantic content and embedding;
- parsed candidate profile;
- canonical facts and immutable text versions;
- automatic classification.

The AI recruiter reads only the first three categories. Canonical facts, versions, identity state and classification are not joined.

Because inbound email creates held `needs_role` Talent Pool records, these candidates are excluded from broad `rank_candidates`. A candidate can still be resolved directly by an exact app key/name/email/phone and read through `candidate_cv_evaluation`, subject to tenant scope.

### WhatsApp CV

Existing historical WhatsApp candidates can be found through live application ranking and have application-level semantic content/profile data.

WhatsApp screening evidence can be visible when mirrored into `applications.raw_json`, including answers such as salary or availability. The recruiter does not query a dedicated conversational evidence table or join canonical CV facts into the same context.

The existing records lack immutable `candidate_cv_text_versions` and classification runs, and new WhatsApp CV indexing is not continuously proven because the generic processing timer is disabled.

### Manual dashboard upload

Current production has no completed manual-dashboard upload sample. The path creates held applications, and the current generic processor is disabled.

Therefore:

- current recruiter indexing is unproven;
- broad ranking would exclude held `needs_role`/`import_review` rows even if indexed;
- exact application lookup could read a processed semantic document if one were created;
- the manual surrogate phone is not equivalent to a grounded candidate phone, although parsed contact values may be present in profile/import JSON.

## 6. Exact candidate-knowledge gap table

| Candidate information | Inbound email CV | WhatsApp CV | Manual dashboard upload | Exact reason |
|---|---|---|---|---|
| Full canonical CV text | partially accessible | partially accessible | unproven | Single-candidate read uses application semantic text, not `candidate_cv_text_versions`, and truncates at 6,000 characters. Email truncation is present in production; no manual sample exists. |
| Extracted skills | partially accessible | partially accessible | unproven | May appear in `candidates.profile` and CV text; canonical fact snapshot is not queried. |
| Complete employment history | partially accessible | partially accessible | unproven | Only profile/text fragments are available; `application_cv_fact_snapshots.facts.employment` is invisible. |
| Years of experience | partially accessible | partially accessible | unproven | May be inferred or mirrored in profile/text; canonical `facts.experience_years` is invisible. |
| Education | partially accessible | partially accessible | unproven | Profile/text may contain it; canonical education facts are not loaded. |
| Certifications | partially accessible | partially accessible | unproven | May occur in CV text; canonical certification facts are not loaded. |
| Languages | partially accessible | partially accessible | unproven | May occur in CV/profile text; canonical language facts are not loaded. |
| Projects | partially accessible | partially accessible | unproven | May occur in bounded text; canonical project facts are not loaded. |
| Classified job families | not accessible | not accessible | not accessible | No recruiter join to classification runs or suggestions. |
| Suggested roles | not accessible | not accessible | not accessible | Stored email classification suggestions are invisible; semantic ranking is not the same authority. |
| Seniority classification | not accessible | not accessible | not accessible | Classification output is not loaded. |
| Industry signals | not accessible | not accessible | not accessible | Classification output is not loaded. |
| Contact details | fully accessible | fully accessible | unproven | Candidate/application phone and email are available for email/WhatsApp; manual path uses a surrogate candidate phone and has no production proof. |
| Previous applications | partially accessible | partially accessible | unproven | `candidates.profile.applications` can contain summaries, but no authoritative application-history aggregation is loaded. Ranking deduplicates to one candidate result. |
| WhatsApp screening answers | not accessible | partially accessible | not accessible | Visible only when mirrored into application/profile JSON; no dedicated evidence join. |
| Salary expectation | not accessible | partially accessible | not accessible | Can be present in WhatsApp screening JSON but is not a canonical recruiter field. |
| Availability | not accessible | partially accessible | not accessible | Can be present in WhatsApp screening JSON but is not loaded from a candidate evidence authority. |
| Notice period | not accessible | partially accessible | not accessible | Same limitation as screening answers. |
| HR notes | partially accessible | partially accessible | unproven | A generic raw/screening note can be read; complete HR notes and canonical interview-note history are not joined. |
| Identity-review state | not accessible | not accessible | not accessible | No join to inbound identity resolution/review ledgers. |
| Assessment results | partially accessible | partially accessible | unproven | Only assessment mirrors in application JSON are reliable in the active registry path; canonical attempts/scores/reports are not joined. |
| Ranking results and explanations | partially accessible | partially accessible | unproven | Semantic similarity/order and direct boosts are visible, but the live deterministic scorer currently falls back to zero/empty evidence. Stored `candidate_rank_evaluations` history is not loaded. Held rows cannot enter broad rank. |

## 7. Information present in production but invisible to the recruiter

Current `WATHEFNI` rows that the active candidate retrieval path does not query:

| Evidence family | Production rows | Recruiter visibility |
|---|---:|---|
| `candidate_cv_text_versions` | 4 | not queried |
| `application_cv_fact_snapshots` | 13 | not queried |
| `candidate_classification_runs` | 2 | not queried |
| `candidate_classification_suggestions` | 33 | not queried |
| `inbound_cv_identity_resolutions` | 3 | not queried |
| `inbound_cv_identity_reviews` | 2 | not queried |
| Open inbound identity reviews | 2 | not queried |
| `candidate_rank_evaluations` | 25 | not queried by the active registry rank/evaluation context |
| `assessment_attempts` | 4 | not joined by the active registry rank query |
| `candidate_interviews` | 4 | not joined by the active registry rank query |

Every current CV fact snapshot contains structured sections for:

- skills;
- employment;
- experience years;
- education;
- certifications;
- languages;
- projects;
- confidence and extraction metadata.

Those authoritative fact sections are currently invisible as structured fields to the AI recruiter.

Production candidate profiles expose a narrower set of top-level keys such as:

- skills;
- education;
- role-relevant experience;
- contact;
- summary;
- screening answers;
- application summaries.

This explains why some answers may appear possible while still missing the canonical detail.

## 8. Held Talent Pool behavior

Current production has:

- 2 `needs_role` applications;
- 2 semantic documents for those applications;
- 2 embeddings;
- 2 parsed profiles.

Behavior:

- **Broad search:** not searchable. `rank_candidates` applies `production_application_predicate`, which excludes `needs_role`, `import_review`, and `import_archived`.
- **Exact lookup:** readable if the resolver is given a sufficiently exact candidate/app reference. `resolve_candidate` and `find_application_by_key` do not apply the held predicate.
- **Communication:** held-record communication is explicitly denied by candidate communication authority.
- **Unified Candidates UI:** held rows advertise only safe read actions such as CV preview/download.
- **Lifecycle mutation:** `recruiting_lifecycle.transition_application` rejects held applications with `held_intake_application` unless the explicit operation is `intake_admit`. AI shortlist/reject/hire paths use the governed status-transition authority and cannot bypass this merely because the resolver can read the record.
- **Job binding:** held rows remain outside live Job/application ranking and require explicit intake admission before lifecycle progression.

The intended “searchable/readable while blocked from communication and lifecycle mutation” behavior is therefore partially met: targeted assistant reads work and mutations/communication fail closed, but broad assistant semantic search excludes held candidates. Unified Candidates/Talent Pool dashboard search remains the held-aware search surface.

## 9. WhatsApp conversation evidence plus CV facts

The recruiter does not construct one complete authorized candidate context.

What can be combined today:

- one application's raw screening JSON;
- one parsed candidate profile;
- one application semantic CV document;
- limited stage, score and note fields.

What is not combined:

- all WhatsApp conversation/job-context evidence;
- canonical CV facts;
- immutable CV versions;
- classification results;
- identity-review state;
- assessment reports;
- ranking history;
- all prior applications.

Production currently has no `candidate_job_contexts` rows, so there is also no live production sample proving a dedicated conversational-context join.

WhatsApp answers are additional evidence in application/profile JSON, not a separate candidate type. The gap is retrieval completeness, not necessarily record identity.

## 10. Raw file versus canonical extraction

The AI recruiter does not reread raw PDFs or DOCX files.

It uses:

- `semantic_documents.content`;
- `semantic_documents.embedding`;
- `candidates.profile`;
- `candidates.raw_json`;
- `applications.raw_json`.

This is the correct direction for safety and efficiency, but the selected materializations are not the complete canonical truth. The correct future source should be authorized canonical extracted text plus current structured evidence, not raw-file rereading.

## 11. Token and context limits

Confirmed explicit limits:

- candidate CV text: 6,000 characters per specific-candidate tool result;
- prior-turn candidate CV context: 4,000 characters in state summary;
- document embedding input: first 12,000 characters;
- conversation history: 10 messages;
- remembered candidate summaries: 5;
- saved prior tool outputs: 3;
- tool loops per turn: 4;
- broad ranking pool: 500 applications;
- broad result count: 10 candidates.

The recruiter prompt also asks the final response to cite only a small number of relevant facts rather than dump the CV. This response-shaping rule further limits how much retrieved evidence is normally surfaced in one answer.

Consequences:

- long CVs are truncated for detailed candidate questions;
- embedding similarity ignores CV text after character 12,000;
- older work history, projects, certifications or education near the end of a long CV may not influence semantic retrieval;
- a follow-up may have less CV text than the first answer;
- comparing more than 10 discovered candidates is not supported in one rank response;
- thousands of candidates are not all individually reasoned over in one request.

## 12. Permissions and tenant boundaries

Positive controls:

- tool-call turns pin an active company code;
- candidate reads require the same company in `find_application_by_key`;
- broad ranking includes `a.company_code=%s`;
- tool-call memory is scoped by company, actor, conversation, channel, module and session;
- candidate read tools map to `prehire.read`;
- mutating actions use separate permissions and confirmation flows;
- held communication has a dedicated fail-closed authority.

Residual concerns:

- when the permission list is present, `prehire.read` is enforced for candidate tools;
- when the permission list is empty, tools retain legacy admin-compatible behavior; if `WATHEFNI_STRICT_WHATSAPP_PERMS` is off, this also affects mutation-tool admission before entitlement checks;
- the entitlement layer still requires company, actor, active HR identity, known role, enabled module and applicable permission, but the split between legacy tool admission and backend-current entitlement makes an empty permission set a configuration-sensitive risk;
- the semantic-document CV lookup filters by app key but does not independently include `company_code`; it relies on the preceding tenant-scoped application resolution;
- candidate identity-review visibility and field-level PII policy are not represented in the candidate context.

Tenant isolation is present at application resolution and ranking query level. Fine-grained evidence authorization is not.

## Answers to the ten verification questions

1. **Dynamic canonical retrieval or limited summary?**  
   Limited dynamic application/candidate reads plus materialized semantic/profile summaries. It does not dynamically assemble all canonical tables.

2. **Can it search thousands or require an ID?**  
   It can search without an ID, but only the first 500 semantic/status-ordered eligible applications are considered and only 10 are returned. Current deterministic scoring falls back to zero because of a live argument mismatch. A specific candidate requires successful application resolution.

3. **Semantic search or embeddings?**  
   Yes, Voyage/pgvector when configured. It silently degrades to a limited non-semantic pool if query embedding fails.

4. **Are all processed email CV candidates indexed?**  
   All 2 current extracted email applications are indexed. All 4 CV document versions are not separately indexed. Both current held records are indexed but excluded from broad ranking.

5. **Are held `needs_role` candidates searchable/readable but mutation-blocked?**  
   Exact lookup and held-aware dashboard search are readable; broad assistant ranking excludes them. Communication and lifecycle mutations fail closed until explicit intake admission.

6. **Are WhatsApp conversation details combined with CV facts?**  
   Only partially through application/profile JSON plus one semantic CV document. No complete canonical evidence assembly exists.

7. **What exists but is invisible?**  
   Canonical CV versions/facts, classifications, identity reviews, complete assessment/interview records, stored ranking history, and complete cross-application evidence.

8. **Do token/context limits truncate long histories?**  
   Yes. The specific-candidate CV cap is 6,000 characters, follow-up state cap is 4,000, and embeddings use only 12,000 characters.

9. **Does it reread raw PDFs?**  
   No. It uses extracted/materialized semantic content and profile/application JSON.

10. **What controls permissions and tenant boundaries?**  
    Company-scoped SQL/application resolution, scoped conversation memory, `prehire.read`, module/role context, separate mutation permissions/confirmation, and held communication authority. Empty-permission legacy read behavior remains a residual concern.

## Narrow recommendations

No production change was made. The narrowest future remediation sequence is:

1. Correct and regress the live `rank_candidate_row(..., role_profile=...)` call so current results no longer silently fall back to zero scores and empty evidence.
2. Add one read-only, tenant-scoped `get_candidate_knowledge` authority that accepts an exact `app_key`/candidate identity and returns:
   - current canonical CV text version;
   - current reviewed structured facts;
   - application history;
   - effective non-invalidated classification;
   - identity-review state appropriate for the caller;
   - assessment/interview summaries;
   - current ranking evidence;
   - authorized WhatsApp screening evidence and HR notes.
3. Register a grounded comparison tool only after it consumes that same canonical knowledge authority.
4. Add a held-aware Talent Pool search mode rather than weakening `production_application_predicate`.
5. Keep held communication and lifecycle actions fail-closed and preserve explicit intake admission as the only promotion path.
6. Index every current canonical document version with tenant, candidate, application and provenance metadata; retain a separate current-candidate pointer.
7. Chunk long CVs for embedding and retrieval instead of embedding only the first 12,000 characters or rendering only the first 6,000.
8. Require explicit backend-current `prehire.read` authority for recruiter reads; do not rely on empty-permission legacy behavior.
9. Expose evidence source/version/review state so the model can distinguish authoritative facts, unreviewed extraction and conversational claims.

Until those changes are qualified, describe the feature as an **application-level semantic recruiter with bounded CV context**, not as complete AI knowledge of every Unified Candidate/Talent Pool record.
