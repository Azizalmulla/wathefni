# Pre-hiring Candidate Knowledge — Phase 1 Implementation

Date: 2026-07-26  
Scope: local Phase 1 only  
Production deploy: none  
Candidate Knowledge storage schema / indexing / Voyage / backfill / Role Profiles: none  
Phase 2+: not started

## Verdict

Phase 1 local implementation is complete and tested.

**GO for Phase 2 local implementation** (canonical CV / facts / classification readers), subject to a separate authorized task.  
**NO-GO** for production deploy, schema, indexing, Voyage, backfill, Role Profiles, or Phase 2 work in this task.

Evidence: `ops/evidence/candidate-knowledge-phase1-impl/`

---

## Files added or changed

### Added

| File | Role |
|---|---|
| `wathefni-orchestrator/candidate_knowledge_errors.py` | Typed fail-closed errors |
| `wathefni-orchestrator/candidate_record_state_policy.py` | `CandidateRecordStatePolicy` / `evaluate_candidate_record_state` |
| `wathefni-orchestrator/candidate_knowledge_authority.py` | Request context, exact resolve, sibling aggregation, Phase 1 shell |
| `wathefni-orchestrator/test_candidate_knowledge_phase1.py` | Denial, isolation, policy, boundary tests |

### Changed

| File | Change |
|---|---|
| `wathefni-orchestrator/test_candidate_knowledge_phase0_contracts.py` | Updated historical “no authority in Phase 0” pin to keep Phase 0 report evidence while allowing Phase 1 authority file |

### Unchanged (intentionally)

- No production deploy
- No new DB schema
- No Voyage / indexing / backfill
- No CV/facts/classification/assessment/interview/ranking/notes/screening readers
- No Role Profiles
- `candidate_knowledge_types.py` reused as-is for shell record / actionability DTOs

---

## Request-context contract

`CandidateKnowledgeRequestContext` requires:

| Field | Rule |
|---|---|
| `company_code` | non-empty (normalized upper) |
| `actor_user_id` | non-empty active actor |
| `permission_authority` | exactly `backend_current` |
| `permission_subject_user_id` | must equal `actor_user_id` |
| `permission_subject_company` | must equal `company_code` |
| `permissions` | non-empty and must include `prehire.read` |
| pre-hiring module | enabled via `module_enabled(company, "pre_hiring")` or `modules_enabled` |

Deny codes:

- `tenant_scope_required`
- `actor_required`
- `backend_current_permission_required`
- `permission_subject_mismatch`
- `permission_denied` (empty perms or missing `prehire.read`)
- `module_disabled`

Empty / missing / legacy / untrusted authorities are denied. This path does **not** inherit tool-orchestrator empty-permission read compatibility.

---

## Candidate-reference contract

```text
candidate_ref = app:<app_key>
```

Rules enforced by `parse_exact_candidate_ref` + `CandidateKnowledgeAuthority.resolve_exact`:

1. Exact `app:` prefix required.
2. Resolve only through tenant-scoped store lookup (`company_code` + `app_key`).
3. Missing row → `candidate_not_found` with no cross-tenant existence signal.
4. No names, embeddings, semantic search, or fuzzy matching.
5. No identity create/merge/bind.

Invalid exact refs → `invalid_candidate_ref`.  
Name-only / non-app input → `candidate_ambiguous`.

---

## Aggregation rules

After exact application resolution:

1. Candidate key = existing application `phone` (including `imp-…` surrogates).
2. Aggregate only applications with the **same** `company_code` and **same** candidate key.
3. Do not aggregate across:
   - tenants
   - different phones
   - manual surrogate ↔ real phone
   - shared surnames / similar names
   - open identity-review alternatives

Open identity review is not a resolver. Name-only remains ambiguous.

---

## Record-state policy matrix

Policy version: `candidate-record-state-policy-v1`  
Artifact: `ops/evidence/candidate-knowledge-phase1-impl/policy-matrix.json`

Named decisions returned:

- `intake_hold_state`
- `communication_allowed`
- `lifecycle_mutation_allowed`
- `job_ranking_eligible`
- `talent_pool_search_eligible`
- `retention_blocked`
- `read_projection` (`full` / `redacted` / `metadata_only` / `denied`)
- `held_state`
- `reason_codes`
- `policy_version`

Intentional domain differences preserved:

| Status / governance | Search / ranking | Communication | Retention | Read projection |
|---|---|---|---|---|
| `needs_role` / `import_review` | ineligible | blocked | blocked | full (readable, not actionable) |
| `import_archived` | ineligible | blocked | blocked | redacted |
| `review_pending` | eligible | allowed | **blocked** | full |
| live (`shortlisted`, etc.) | eligible | allowed | not blocked | full |
| finalized (`hired`/`rejected`/`withdrawn`) | ineligible | depends on non-hold | not blocked by hold set | full |
| archived governance | ineligible | blocked | blocked | redacted |
| restricted | ineligible | blocked | — | metadata_only |
| legal hold | otherwise unchanged | — | **blocked** | full unless other flags |
| deletion requested/in progress | blocked mutations | blocked | blocked | redacted |
| deletion completed | — | — | blocked | denied → `candidate_restricted` |

Existing communication / lifecycle / ranking / intake / retention authorities remain the mutation gates. This policy is a shared read/actionability projection only.

---

## Typed failures

| Code | When |
|---|---|
| `tenant_scope_required` | missing company |
| `actor_required` | missing actor |
| `backend_current_permission_required` | authority ≠ `backend_current` |
| `permission_subject_mismatch` | subject user/company mismatch |
| `permission_denied` | empty perms or missing `prehire.read` |
| `module_disabled` | pre-hiring module off |
| `invalid_candidate_ref` | malformed `app:` ref |
| `candidate_not_found` | no same-tenant exact app (no existence leak) |
| `candidate_ambiguous` | name-only / non-app exact-read input |
| `candidate_restricted` | deletion-completed / denied projection |
| `source_reader_blocked` | any CV/facts/history reader before/within Phase 1 |

Error payloads omit cross-tenant existence fields.

---

## Phase 1 authority boundary

`CandidateKnowledgeAuthority`:

1. `authorize(context)` — fail-closed context checks
2. `resolve_exact(context, candidate_ref)` — authorize → exact resolve → sibling aggregate → per-app state → aggregate actionability
3. `resolve_name_only(...)` — always ambiguous
4. `assert_source_reader_blocked(name)` — proves readers cannot run
5. `phase1_record_shell(resolved)` — typed shell with empty source sections and `phase1_shell_only` coverage

No silent fallback to `candidates.profile`, `applications.raw_json`, or `semantic_documents`.

Store protocol is read-only. `InMemoryCandidateKnowledgeStore.mutate()` increments a write counter and raises; production DB adapters are not wired in Phase 1.

---

## Tests and exact results

Suite: `python3 -m unittest test_candidate_knowledge_phase1`

**28/28 PASS**

Also re-validated Phase 0 contracts after the historical pin update:

`python3 -m unittest test_candidate_knowledge_phase1 test_candidate_knowledge_phase0_contracts` → **57/57 PASS**

Covered:

- valid backend-current context
- empty permissions
- missing `prehire.read`
- legacy/untrusted authority
- actor mismatch
- company mismatch
- missing tenant / actor
- module disabled
- exact same-tenant resolution
- cross-tenant denial without existence leak
- invalid `app:` ref
- name-only ambiguity
- multi-application aggregation
- manual surrogate separation
- shared-surname separation
- open identity review does not resolve/merge
- each held state
- `review_pending` domain differences
- archived / restricted / legal-hold / deletion governance
- source readers blocked before and after resolution
- zero mutation proof

Logs: `ops/evidence/candidate-knowledge-phase1-impl/unittest.txt`

---

## Proof of zero mutations

1. Phase 1 authority exposes `mutation_count` (always 0 in this phase).
2. In-memory store `write_attempts` unchanged across successful resolves.
3. Explicit `store.mutate(...)` raises `RuntimeError("... read-only")` and is the only path that increments write attempts.
4. No SQL, schema DDL, Voyage, indexing, or backfill code paths are invoked by Phase 1 modules.
5. Shell record source sections remain empty (`canonical_cv={} `, lists empty).

---

## Unresolved gaps (non-blocking for Phase 1)

1. No production DB-backed store adapter yet (Phase 1 uses injectable store; wiring to `find_application_by_key` / sibling queries is Phase 2/integration work).
2. `compare_candidates` remains unregistered in the action registry (later tool phase).
3. Tool orchestrator still admits empty-perm reads for some tools; Candidate Knowledge independently fail-closes.
4. Identity-review state is not loaded into the shell beyond “does not resolve” behavior; Phase 2/3 should surface identity coverage explicitly.
5. Contact values are intentionally omitted from the Phase 1 shell (`contact_*_present=False`).

---

## GO / NO-GO

| Decision | Result |
|---|---|
| Phase 1 local complete | **GO** |
| Phase 2 local implementation (CV/facts/classification readers) | **GO** (separate task only) |
| Begin Phase 2 in this task | **NO-GO** |
| Production deploy | **NO-GO** |
| Add Candidate Knowledge storage schema / indexing / Voyage / backfill | **NO-GO** |
| Role Profiles | **NO-GO** |

### Exact permitted Phase 2 scope (when authorized later)

- Read current valid immutable CV text version
- Read fact snapshots + review projection
- Read non-invalidated classifications + HR review events
- Evidence manifest + per-section coverage
- No silent profile/raw_json fallback; disclose gaps
- Still no indexing, Voyage calls for search index, production deploy, or Role Profiles unless separately authorized

---

## Stop

Stopped after this report. Phase 2 was not started.
