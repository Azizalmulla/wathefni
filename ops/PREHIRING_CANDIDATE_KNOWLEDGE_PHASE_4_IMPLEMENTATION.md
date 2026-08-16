# Pre-hiring Candidate Knowledge — Phase 4 Implementation

Date: 2026-07-26  
Scope: local Phase 4 only (indexing + hybrid retrieval)  
Production deploy / production data / production backfill: none  
Model-facing recruiter tools: not registered  
Live Ranking path: not integrated  
Role Profiles: not started  
Phase 5+: not started

## Verdict

Phase 4 local indexing and hybrid retrieval is complete and tested.

**GO for Phase 5 local governed-tool implementation**, in a separate authorized task.  
**NO-GO** for production deploy, production backfill, live Ranking integration, model tool registration, Role Profiles, or Phase 5 work in this task.

Evidence: `ops/evidence/candidate-knowledge-phase4-impl/`

---

## Files and schema added

### Added modules

| File | Role |
|---|---|
| `candidate_knowledge_index_schema.py` | Local additive DDL for chunks, index jobs, content-free access events |
| `candidate_knowledge_chunker.py` | Deterministic section-aware chunking + size benchmarks |
| `candidate_knowledge_embeddings.py` | Mock + Voyage providers, query cache, pinned models |
| `candidate_knowledge_index_store.py` | In-memory index/job/audit store (search projection only) |
| `candidate_knowledge_indexer.py` | Authority-sourced indexing, invalidation, identity-correction order |
| `candidate_knowledge_search.py` | Scopes, structured/lexical/semantic hybrid search, RRF, pagination |
| `test_candidate_knowledge_phase4.py` | Phase 4 focused suite |

### Changed

| File | Change |
|---|---|
| `candidate_knowledge_errors.py` | Added `index_not_ready`, `retrieval_degraded` |

### Local schema (additive)

- `candidate_knowledge_chunks`
- `candidate_knowledge_index_jobs`
- `candidate_knowledge_access_events`

No denormalized `candidate_knowledge_records` JSON truth table.

---

## Index contract

The index is a **rebuildable search projection**.

It is never:

- candidate identity authority
- canonical CV truth
- classification authority
- candidate merge authority
- hiring-decision authority

Indexed by default from authorized `CandidateKnowledgeRecord` sources:

- current valid immutable CV text
- effective reviewed CV facts (skills/employment/education/certs/languages/projects/years)
- classification labels with HR-confirmed vs AI-suggested preserved separately
- authorized searchable application metadata (position/status/channel)

Never indexed:

- emails / phones
- names for identity matching/merging
- identity-review alternatives
- malware/quarantine metadata
- private notes
- raw assessment answers
- unrestricted interview transcripts
- secrets / tokens / signed links

Display names may appear as display metadata only and never drive merge/identity.

---

## Chunking design

- Version: `ck-chunker-v1`
- Section boundaries: summary, employment, education, skills, certifications, languages, projects, other
- Heading retained with windowed content
- Stable char/token offsets into immutable CV text
- Stable chunk IDs from tenant + source + chunker version + ordinal + text hash
- Qualification targets: 800 / 1000 / 1200 tokens with overlap 100 (default target 1000)
- Long CV tails beyond prior 6k/12k limits remain chunked and retrievable

Benchmark artifact: `qualification.json` → `chunk_size_benchmark`

---

## Voyage configuration

Local-only runtime:

- `WATHEFNI_CK_EMBEDDINGS_ENABLED`
- `WATHEFNI_CK_VOYAGE_ENABLED` + `VOYAGE_API_KEY` required for real Voyage
- Document/query models pinned to `voyage-4-large`
- No silent model switching
- Provider/model/dimensions/index version stored per chunk
- Batch document embed + query embed
- Query embedding cache: tenant + model + policy scope + normalized query, TTL 300s, max 512
- Deterministic `MockEmbeddingProvider` for unit tests
- Real Voyage only when explicitly enabled and credentialed (not run in this qualification)

Forbidden Voyage uses remain blocked: identity, merge, ownership, held admission, lifecycle, final hiring decisions.

---

## Hybrid retrieval design

Pipeline:

1. exact structured filters (status, skills, channels, classification nodes, scope)
2. lexical token overlap over eligible current chunks
3. vector similarity (top-N, min score threshold)
4. classification filters with HR/AI labels kept separate
5. reciprocal-rank fusion
6. candidate-level aggregation (max 3 section matches / candidate; no name merge)

Match reasons returned separately:

- `structured_match`
- `lexical_match`
- `semantic_match`
- `classification_match`

Semantic similarity is labeled `search_relevance_not_hiring_score`.

Retrieval modes:

- `hybrid`
- `lexical_only`
- `structured_only`
- `index_not_ready`
- `retrieval_degraded`

Voyage/query-embed failure discloses `retrieval_degraded` and does not pretend to be equivalent semantic search.

---

## Search scopes

| Scope | Behavior |
|---|---|
| `talent_pool` | Held intake statuses (`needs_role`, `import_review`, …) searchable when authorized |
| `active_applications` | Live pipeline statuses excluding intake holds |
| `all_authorized` | Union with explicit finalized/archived filters |

Held Talent Pool hits remain non-actionable for communication, lifecycle mutation, and Job ranking via projected actionability.

Archived / restricted / deletion-completed follow `CandidateRecordStatePolicy` and are excluded from default current search.

---

## Freshness / invalidation

Enqueue/idempotent jobs on versioned source key:

`company + app + document_version + source_record + content_hash + chunker + embedding_model + policy`

Triggers covered:

- current CV version indexed
- superseded / invalidated versions marked
- facts/classification changes re-indexable via indexer
- governance restricted/deleted → invalidate or restrict
- identity ownership correction order:
  1. invalidate old-owner chunks
  2. exclude immediately from search
  3. build corrected-owner chunks
  4. visibility only after valid indexing

---

## Benchmarks / qualification

Artifact: `ops/evidence/candidate-knowledge-phase4-impl/qualification.json`

| Metric | Result |
|---|---|
| Long CV size | ~30.6k chars; tail marker retrievable |
| Chunk targets 800/1000/1200 | 7 / 5 / 5 chunks on long synthetic CV |
| Arabic / English | `ar`, `en`, bilingual `ar_en` detected |
| Synthetic pool | 1500 candidates; ~3000 chunks |
| Index latency | ~1.6s (local mock embed) |
| Search latency | ~23ms |
| Pagination | page size 20, zero overlap across pages |
| Invalidation | ~1ms; needle immediately invisible |
| Incomplete index | `index_not_ready` |
| Voyage failure | `retrieval_degraded` with disclosed error; lexical hit retained |
| Real Voyage calls | 0 |
| Estimated Voyage cost | $0.00 |

---

## Exact test results

```text
python3 -m unittest test_candidate_knowledge_phase4 \
  test_candidate_knowledge_phase3 \
  test_candidate_knowledge_phase2 \
  test_candidate_knowledge_phase1 \
  test_candidate_knowledge_phase0_contracts
```

**112/112 PASS**

Phase 4 coverage includes:

- deterministic section chunking / overlap / stable IDs
- long CV tail retrieval
- current-version-only default search
- superseded/invalidated/restricted exclusion
- identity ownership correction order
- multi-chunk non-domination + same-surname non-merge
- Arabic/bilingual chunks
- lexical / semantic-mock / structured / hybrid
- classification authority label separation
- stable pagination
- 1200+ synthetic candidate search
- cross-tenant denial
- held Talent Pool searchable + non-actionable
- Voyage failure disclosure
- no PII/notes embedding
- zero lifecycle/communication/ranking/identity mutation
- zero production access

Log: `ops/evidence/candidate-knowledge-phase4-impl/unittest.txt`

---

## Proof of no production mutation

1. Index/search operate on local in-memory projection only.
2. Mutation probes (`mutate_lifecycle`, `mutate_communication`, `mutate_ranking`, `mutate_identity`, `access_production`) raise and are counted.
3. Access audit stores content-free events only (no chunk text/snippets/contacts/embeddings).
4. No production DB wiring, backfill runner, or live Ranking adapter was added.
5. No model-facing tools registered.

---

## Unresolved gaps (non-blocking for Phase 4)

1. Postgres/pgvector adapter DDL is present; live local Postgres ANN wiring is not exercised in CI (in-memory vector scan used).
2. Real Voyage qualification not run (credentials not explicitly enabled in this task).
3. Index worker claim/lease loop exists in store primitives but is not a background daemon.
4. Phase 2/3 authority assembly is not auto-subscribed to index jobs yet (indexer is explicit/local).
5. Phase 5 governed tools (`search_candidates`, `get_candidate_knowledge`, `compare_candidates`) not implemented/registered.
6. Live Ranking evidence adapter remains Phase 6.

---

## GO / NO-GO

| Decision | Result |
|---|---|
| Phase 4 local complete | **GO** |
| Phase 5 local governed tools | **GO** (separate task only) |
| Begin Phase 5 in this task | **NO-GO** |
| Production deploy / backfill | **NO-GO** |
| Register recruiter model tools | **NO-GO** |
| Live Ranking integration | **NO-GO** |
| Role Profiles | **NO-GO** |

### Exact permitted Phase 5 scope (when authorized later)

- Implement `search_candidates`, `get_candidate_knowledge`, `compare_candidates` on this authority/index
- Register only behind tools flag in local shadow mode
- Keep old tools for parity; do not mix outputs
- Log source IDs, coverage, redactions, latency, retrieval mode
- Still no production deploy, Ranking cutover, or Role Profiles unless separately authorized

---

## Stop

Stopped after this report. Phase 5 was not started.
