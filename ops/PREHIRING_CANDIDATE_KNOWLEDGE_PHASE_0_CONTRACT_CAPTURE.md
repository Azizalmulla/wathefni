# Pre-hiring Candidate Knowledge — Phase 0 Contract Capture

Date: 2026-07-26  
Status: Phase 0 complete (contract capture only)  
Production mutation: none  
Voyage calls for this phase: none  
Indexing / schema additions: none  
`CandidateKnowledgeAuthority`: not implemented  
Role Profiles: not started

## Verdict

**NO-GO for Phase 1.**

The three deployed CV facts / evidence / ranking modules were restored and SHA-match production and staging. Broader checked-in runtime contracts still disagree with deployed production (`app.py`, `cv_extraction.py`, `action_registry.py`). Per the Phase 0 stop rule, Phase 1 must not begin until that drift is reconciled.

---

## Restored module inventory

| Module | Checkout path | Evidence pack | SHA-256 | Prod | Staging |
|---|---|---|---|---|---|
| CV facts | `wathefni-orchestrator/candidate_cv_facts.py` | `ops/evidence/candidate-knowledge-phase0/candidate_cv_facts.py` | `4c01145e0379554cf3f61a1d06d7d4d1d35859f270549934c1588b142276153d` | match | match |
| CV evidence | `wathefni-orchestrator/candidate_cv_evidence.py` | `ops/evidence/candidate-knowledge-phase0/candidate_cv_evidence.py` | `06de2da2fba4638161edcfca64b6a55c2b75f5f63cf5332abee400dd8d5a26f4` | match | match |
| Ranking | `wathefni-orchestrator/candidate_ranking.py` | `ops/evidence/candidate-knowledge-phase0/candidate_ranking.py` | `9b8a54f19d10da7ddd8c1ef8b5207833cde4aa1cfc71e3b72d47bae1f3efd8c8` | match | match |

Frozen contract versions inside restored modules:

- `application-cv-facts-v1` / extractor `cv-facts-deterministic-v1`
- `application-cv-evidence-v1`
- ranking `ranking-soft-v2`, embedding model `voyage-4-large`

Matching deployed module tests were also checked in:

- `test_candidate_cv_facts.py` — pass
- `test_candidate_cv_evidence.py` — **1 error** under local `cv_extraction` (see drift)
- `test_candidate_ranking.py` — present in evidence pack / checkout

---

## Source / runtime drift findings

### Agree (restored)

- Production and staging copies of the three restored modules are identical to each other and to checkout.
- Production schema tables required by those modules exist (`missing: []` in the Phase 0 manifest).

### Disagree (hard Phase 1 blockers)

| File | Local SHA (prefix) | Production SHA (prefix) | Contract impact |
|---|---|---|---|
| `cv_extraction.py` | `4dace00f5ab1…` | `2859dc7e5e95…` | Local lacks `record_extraction_finalization`; restored evidence `materialize_extracted_cv` cannot run. Evidence materialization unittest errors. |
| `app.py` | `d7a9f7ec25f8…` (~58.6k lines) | `b4a9a4b032ab…` (~60.1k lines) | Production imports and wires `candidate_cv_facts`, `candidate_cv_evidence`, `candidate_ranking.rank_candidates_compat`, and `materialize_extracted_cv` / `extract_application_cv_facts`. Local checkout does **not**. |
| `action_registry.py` | `92ea89bcfcab…` (~5.6k lines) | `b7992797bd6d…` (~6.8k lines) | Live AI tool surface differs from production binary; defect pins below are from local checkout and must be re-verified against the production registry before Phase 1. |

Additional note: staging `app.py` (`7e7caf5f7bfb…`) also differs from production `app.py`. Phase 0 treats production as the runtime authority for restore checks.

Stop rule applied: restored modules match; surrounding runtime contracts do not. **No Phase 1 authority work.**

---

## Schema manifest (read-only)

Captured from production at `2026-07-26 17:22:49.032809+00:00`.

Artifact: `ops/evidence/candidate-knowledge-phase0/production-schema-manifest.json`

- Tables inventoried: **33**
- Missing expected knowledge tables: **none**
- Capture mode: read-only row/column/index metadata (no writes)

| Table | Rows | Columns |
|---|---:|---:|
| `candidates` | 21 | 13 |
| `applications` | 18 | 30 |
| `semantic_documents` | 18 | 17 |
| `candidate_documents` | 14 | 18 |
| `candidate_cv_text_versions` | 4 | 16 |
| `application_cv_fact_snapshots` | 17 | 20 |
| `application_cv_evidence_materializations` | 17 | 27 |
| `candidate_fact_review_events` | 0 | 15 |
| `cv_extraction_runs` | 25 | 21 |
| `cv_extraction_cache` | 9 | 16 |
| `cv_extraction_finalizations` | 17 | 13 |
| `cv_extraction_leases` | 0 | 9 |
| `file_registry` | 30 | 26 |
| `inbound_cv_identity_resolutions` | 3 | 21 |
| `inbound_cv_identity_reviews` | 2 | 13 |
| `candidate_identity_keys` | 3 | 11 |
| `candidate_classification_runs` | 2 | 12 |
| `candidate_classification_suggestions` | 33 | 11 |
| `candidate_classification_review_events` | 17 | 15 |
| `candidate_classification_run_invalidations` | 1 | 9 |
| `taxonomy_releases` | 1 | 6 |
| `taxonomy_nodes` | 43 | 8 |
| `candidate_record_governance` | 0 | 20 |
| `candidate_job_contexts` | 0 | 25 |
| `candidate_rank_evaluations` | 25 | 14 |
| `ranking_runs` | 31 | 25 |
| `ranking_run_items` | 27 | 20 |
| `job_ranking_criteria_sets` | 0 | 14 |
| `job_ranking_criteria` | 0 | 13 |
| `assessment_attempts` | 4 | 28 |
| `assessment_scores` | 1 | 12 |
| `assessment_reports` | 1 | 7 |
| `candidate_interviews` | 4 | 52 |

No Candidate Knowledge storage tables were created in this phase.

---

## Both ranking paths and parity boundary

Artifact: `ops/evidence/candidate-knowledge-phase0/ranking-path-notes.json`

### Path A — live AI registry rank

- Entry: `action_registry._rank_candidates_executor`
- Registered tools: `rank_candidates`, `candidate_cv_evaluation`
- Pool: applications (+ candidates + `semantic_documents`), tenant-scoped
- Limits: pool via `RANK_CANDIDATES_POOL_LIMIT` (app default **500**; registry getattr fallback **200**); top N max **10**; default top N **5**
- Signal: Voyage similarity first; position/status are boosts, not SQL filters
- Held exclusion: `production_application_predicate` excludes `needs_role`, `import_review`, `import_archived`
- Scorer: `legacy.rank_candidate_row(...)`

### Path B — dashboard / mobile job ranking

- Production entry: `candidate_ranking.rank_candidates_compat` → `rank_job_applications`
- Local checkout entry: still `app.rank_candidates` (compat wiring absent)
- Requires exact job/position
- Contract: `ranking-soft-v2`, model `voyage-4-large`
- Uses restored CV facts + evidence modules when wired

### Parity boundary (frozen)

Scores are **not** required to match across Path A and Path B.

Shared invariants that **must** agree:

- tenant `company_code` isolation
- held-status exclusions from the production predicate
- top_n hard cap of 10 for legacy-shaped responses
- ranking reads never mutate lifecycle
- embeddings never merge identity

Must **not** claim parity for:

- absolute score values
- free-text registry ordering without an exact job
- role-profile criterion depth
- ranking-soft-v2 narrative/brief fields

Replacement rule: Candidate Knowledge may later feed both paths, but each path keeps its own ranking semantics until an explicit unified ranker cutover.

---

## Frozen current behavior tests

Suite: `wathefni-orchestrator/test_candidate_knowledge_phase0_contracts.py`  
Result: **26/26 pass**

Pinned limits / exclusions:

- `CV_TEXT_MAX_CHARS = 6000`
- `RANK_CANDIDATES_DEFAULT_TOP_N = 5`
- `RANK_CANDIDATES_MAX_TOP_N = 10`
- `RANK_CANDIDATES_POOL_LIMIT = 500`
- Voyage document embed / CV extract window `[:12000]` present in local `app.py`
- production predicate excludes held intake statuses

Pinned known defects (local checkout):

- `compare_candidates` implemented in `app.py` but **not** registry-registered
- registry `rank_candidate_row` call omits required `role_profile`
- registry uses `screening` before assigning it
- empty permissions still admit `*.read` tools when `WATHEFNI_STRICT_WHATSAPP_PERMS` is off

Pinned drift markers (intentionally failing-closed until reconciliation):

- local `cv_extraction` missing `record_extraction_finalization`
- local `app.py` missing facts/evidence/compat wiring
- local `action_registry.py` SHA ≠ production

Supporting module tests:

- `test_candidate_cv_facts.py` — pass
- `test_candidate_cv_evidence.py` — blocked by `cv_extraction` drift on materialization

---

## Fixture coverage

Module: `wathefni-orchestrator/fixtures/candidate_knowledge_phase0.py`

| Fixture | Purpose |
|---|---|
| GCC shared surname (Mariam Almulla vs Aziz/Hamad Almulla) | Name-only must not conflate identities |
| Exact email/phone identity fields on those fixtures | Exact-match authority only |
| Open identity review | Resolution-required read path |
| Held states (`needs_role`, `import_review`, `import_archived`) | Readable but not actionable / not talent-pool ranked |
| `review_pending` policy matrix | Intentional divergence: search includes; inbound retention treats as held |
| Long CV beyond 12,000 chars | Tail after embed/eval windows must be disclosed, not silently lost |
| Multiple applications one phone | Aggregate all bound apps under one `candidate_ref` |
| Manual surrogate `imp-…` vs real phone | Surrogate must not merge to real-phone control |
| Permission empty / `backend_current` / missing `prehire.read` | Current admission vs Phase 1 fail-closed target |
| Tenant isolation WATHEFNI vs OTHERCO | Cross-tenant miss / no leak |

---

## `candidate-knowledge-v1` schema and typed DTOs

Defined only (no authority implementation):

- Typed DTOs: `wathefni-orchestrator/candidate_knowledge_types.py`
  - `CandidateKnowledgeRecord`, `EvidenceRef`, `CoverageItem`, `Actionability`, `CandidateKnowledgeSubject`
  - helpers `candidate_ref_from_app_key` / `app_key_from_candidate_ref` (`app:` prefix)
- JSON Schema: `wathefni-orchestrator/schemas/candidate_knowledge_v1.json`
- Explicit absence: no `candidate_knowledge_authority.py`

---

## Unresolved blockers

1. **Checkout `app.py` ≠ production `app.py`** — facts/evidence/ranking compat wiring missing locally.
2. **Checkout `cv_extraction.py` ≠ production** — missing `record_extraction_finalization` required by restored evidence materialization.
3. **Checkout `action_registry.py` ≠ production** — tool-surface parity unverified against the live binary.
4. **Evidence materialization unittest cannot pass** until `cv_extraction` contract is restored or explicitly version-gated.
5. **Staging `app.py` also differs from production** — cutover/reconcile path must name which binary is authoritative before Phase 1.
6. Registry defects (`role_profile`, `screening`, unregistered `compare_candidates`) remain frozen, not fixed.
7. Empty-permission read-tool admission remains live behavior; Phase 1 must fail closed on non-`backend_current` contexts.

---

## GO / NO-GO for Phase 1

| Gate | Result |
|---|---|
| Freeze / contract capture artifacts present | GO |
| Restored facts/evidence/ranking modules SHA-match deployed | GO |
| Read-only production schema manifest captured | GO |
| Both ranking paths + parity boundary documented | GO |
| Limits / exclusions / defects pinned in tests | GO |
| Required fixtures checked in | GO |
| `candidate-knowledge-v1` DTO + JSON schema defined | GO |
| Checked-in source agrees with deployed runtime contracts beyond the three modules | **NO-GO** |
| Safe to implement `CandidateKnowledgeAuthority` | **NO-GO** |

**Phase 1 decision: NO-GO.**

Do not implement Candidate Knowledge authority, add schema, start indexing, call Voyage for indexing, modify production, run backfill, or begin Role Profiles until the unresolved blockers above are cleared and this gate is re-run.

---

## Phase 0 deliverable index

- Report: `ops/PREHIRING_CANDIDATE_KNOWLEDGE_PHASE_0_CONTRACT_CAPTURE.md` (this file)
- Evidence pack: `ops/evidence/candidate-knowledge-phase0/`
- Restored modules: `wathefni-orchestrator/candidate_cv_{facts,evidence}.py`, `candidate_ranking.py`
- Fixtures: `wathefni-orchestrator/fixtures/candidate_knowledge_phase0.py`
- Frozen tests: `wathefni-orchestrator/test_candidate_knowledge_phase0_contracts.py`
- DTOs: `wathefni-orchestrator/candidate_knowledge_types.py`
- JSON schema: `wathefni-orchestrator/schemas/candidate_knowledge_v1.json`
