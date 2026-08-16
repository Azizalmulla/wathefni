# Pre-hiring Candidate Knowledge — Phase 2 Implementation

Date: 2026-07-26  
Scope: local Phase 2 only  
Production deploy: none  
Candidate Knowledge storage tables / indexing / Voyage / backfill / model tools / Role Profiles: none  
Phase 3+: not started

## Verdict

Phase 2 local implementation is complete and tested.

**GO for Phase 3 local implementation** (history / screening / assessments / interviews / ranking / notes federation), in a separate authorized task.  
**NO-GO** for production deploy, schema additions, indexing, Voyage, backfill, tool registration, Role Profiles, or Phase 3 work in this task.

Evidence: `ops/evidence/candidate-knowledge-phase2-impl/`

---

## Files added or changed

### Added

| File | Role |
|---|---|
| `wathefni-orchestrator/candidate_knowledge_store.py` | Extended read-only store protocol, Postgres adapter, in-memory store |
| `wathefni-orchestrator/candidate_knowledge_readers.py` | Canonical CV / effective facts / classification readers + evidence/coverage |
| `wathefni-orchestrator/test_candidate_knowledge_phase2.py` | Phase 2 reader, channel, isolation, zero-side-effect tests |

### Changed

| File | Change |
|---|---|
| `wathefni-orchestrator/candidate_knowledge_authority.py` | Added `assemble_phase2`; re-exports store adapters; Phase 3+ reader gate preserved |
| `wathefni-orchestrator/test_candidate_knowledge_phase1.py` | Updated post-resolution reader gate expectations for Phase 2 boundary |

### Reused (not rewritten)

- `unified_candidates.effective_facts_from_events`
- `talent_pool_classification.effective_classification`
- Phase 1 request context / exact resolve / state policy / actionability

---

## DB adapter contract

`CandidateKnowledgeStore` (protocol) + `PostgresCandidateKnowledgeStore`:

| Method | Tenant scoping |
|---|---|
| `get_application` | `applications.company_code=%s AND app_key=%s` |
| `list_bound_applications` | `company_code=%s AND phone=%s` |
| `get_governance` | `candidate_record_governance.company_code=%s AND app_key=%s` |
| `list_cv_text_versions` | `candidate_cv_text_versions.company_code=%s AND app_key=%s` |
| `get_candidate_document` | join `applications` with `a.company_code=%s` |
| `list_fact_snapshots` | `application_cv_fact_snapshots.company_code=%s AND app_key=%s` |
| `list_fact_review_events` | `candidate_fact_review_events.company_code=%s AND app_key=%s` |
| `list_classification_*` | always `company_code=%s` (+ app/run joins) |
| taxonomy reads | version-keyed (global taxonomy tables) |

Guarantees:

- no writes / locks / DDL / jobs
- `mutate`, `trigger_ocr`, `call_voyage` raise and increment counters in the in-memory store
- every application-scoped SQL includes `company_code`

---

## CV reader behavior

`read_canonical_cv`:

1. Lists tenant-scoped `candidate_cv_text_versions`
2. Fail-closed on multiple `is_current=true` → coverage `conflict` (no silent pick)
3. Requires single current row with ready/completed status and non-empty `text_content`
4. Returns version id, text, extraction method/finalization id, hashes, channel/provenance, timestamps
5. Never reads `semantic_documents`, `candidates.profile`, or `applications.raw_json`
6. Never opens PDF/DOCX or triggers OCR

Coverage outcomes used: `available`, `not_recorded`, `not_extracted`, `invalidated`, `conflict`, `source_pipeline_incomplete`, `not_authorized`, `restricted`

---

## Fact projection behavior

`read_effective_facts`:

1. Loads current `application_cv_fact_snapshots` (conflict if multiple current)
2. Loads `candidate_fact_review_events`
3. Applies `effective_facts_from_events` (HR confirm/correct/add/supersede override; reject clears)
4. Returns extraction snapshot, effective values, review map, skills/employment/education/languages/projects/experience_years, schema/extractor versions, completeness
5. Missing snapshot → `not_recorded` with explicit unknown policy (never negative evidence)
6. No LLM inference; no profile-mirror fallback

---

## Classification projection behavior

`read_effective_classification`:

1. Loads runs, suggestions, review events, invalidations (tenant-scoped)
2. Excludes invalidated runs
3. Selects latest eligible run
4. Applies `effective_classification` keeping **HR-confirmed** and **AI-suggested** separate
5. Returns rejected nodes separately
6. Preserves taxonomy/classifier versions and optional taxonomy release/node labels
7. Missing runs → `not_recorded` (coverage, not weakness)
8. No Job assignment or lifecycle mutation

---

## Evidence manifest format

Each `EvidenceRef` includes:

- stable `evidence_id` (hash digest)
- `source_kind` / `source_record_id`
- `company_code` / `app_key`
- document/version ids where relevant
- `authority_level` (`canonical` / `hr_confirmed` / `ai_suggested`)
- `review_state`
- timestamp
- content hash / digest when available

Full CV text and sensitive fact values are not copied into evidence metadata.

---

## Coverage matrix (cross-channel samples)

Artifact: `ops/evidence/candidate-knowledge-phase2-impl/cross-channel-coverage.json`

| Channel fixture | `canonical_cv` | `effective_facts` | `classifications` |
|---|---|---|---|
| Inbound email (complete) | `available` | `available` | `available` |
| WhatsApp (facts only) | `not_recorded` | `available` | `not_recorded` |
| Manual upload (pending empty text) | `source_pipeline_incomplete` | `not_recorded` | `not_recorded` |

Gaps are disclosed; legacy mirrors are not used to fill them.

---

## CandidateKnowledgeRecord integration

`CandidateKnowledgeAuthority.assemble_phase2(context, candidate_ref)`:

1. Reuses Phase 1 authorize + exact `app:` resolve + sibling aggregation + state policy/actionability
2. Executes Phase 2 readers only after successful resolution
3. Populates `canonical_cv`, `effective_facts`, `classifications`, `evidence_manifest`, `coverage`
4. Leaves Phase 3+ sections as `not_authorized`
5. Honors `read_projection` (`restricted`/`metadata_only` suppresses bodies; deletion-completed still raises `candidate_restricted`)

`phase1_record_shell` remains available and still returns empty Phase 2 payloads.

---

## Tests and exact results

```text
python3 -m unittest test_candidate_knowledge_phase2 \
  test_candidate_knowledge_phase1 \
  test_candidate_knowledge_phase0_contracts
```

**73/73 PASS**

Including Phase 2 cases for:

- inbound-email canonical CV
- multiple versions / one current
- superseded + invalidated exclusion
- conflicting current versions
- missing canonical version
- current facts + HR override + rejected path
- stale / invalidated / missing facts-as-unknown
- AI / HR / rejected classification
- invalidated run exclusion + taxonomy version
- WhatsApp partial + manual incomplete coverage
- cross-tenant denial on assemble
- restricted suppression + deletion restriction
- no profile/raw/semantic fallback
- no OCR / Voyage / writes
- Phase 3 section assemble denied

Log: `ops/evidence/candidate-knowledge-phase2-impl/unittest.txt`

---

## Zero-mutation / zero-external-call proof

1. In-memory store `write_attempts`, `ocr_triggers`, `external_calls` remain 0 across successful assemblies.
2. Explicit `mutate` / `trigger_ocr` / `call_voyage` raise and are the only increments.
3. Authority `mutation_count` stays 0.
4. No Voyage/indexing/schema code paths are invoked by Phase 2 modules.
5. Assembled records never contain profile-mirror or raw_json CV text when canonical versions are absent.

---

## Unresolved gaps (non-blocking for Phase 2)

1. Postgres adapter is implemented but not live-wired into production HTTP/tool routes (local Phase 2 only).
2. Sibling applications are aggregated for identity/actionability; Phase 2 section payloads are assembled for the **anchor** `app_key` (per-app section fan-out can come later if needed).
3. Document “latest” soft metadata on `candidate_documents` is supporting only; text authority remains `candidate_cv_text_versions`.
4. Phase 3 history/notes/assessments/interviews/ranking/screening readers not started.
5. Model-facing tools remain unregistered (`compare_candidates` gap unchanged).

---

## GO / NO-GO

| Decision | Result |
|---|---|
| Phase 2 local complete | **GO** |
| Phase 3 local implementation | **GO** (separate task only) |
| Begin Phase 3 in this task | **NO-GO** |
| Production deploy | **NO-GO** |
| Add Candidate Knowledge storage tables / indexing / Voyage / backfill | **NO-GO** |
| Register model-facing tools | **NO-GO** |
| Role Profiles | **NO-GO** |

### Exact permitted Phase 3 scope (when authorized later)

- Complete tenant-scoped application history
- Normalize screening evidence/source labels
- Assessments, interviews, ranking history, workflow notes federation
- Module-disabled / section-not-authorized coverage expansion
- Still no indexing/Voyage search index, production deploy, or Role Profiles unless separately authorized

---

## Stop

Stopped after this report. Phase 3 was not started.
