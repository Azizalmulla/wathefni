# Pre-hiring Candidate Knowledge — Phase 5 Implementation

Date: 2026-07-26  
Scope: local Phase 5 only (governed tools in **shadow mode**)  
Production deploy: none  
Live production action registry registration: none  
Live AI recruiter / production user exposure: none  
Production backfill: none  
Live Ranking integration: none  
Role Profiles: none  
Phase 6+: not started

## Verdict

Phase 5 local shadow tools are complete and tested.

**GO for Phase 6 local Ranking evidence adapter work**, in a separate authorized task.  
**NO-GO** for production deploy, live tool registration, production exposure, Ranking cutover, Role Profiles, or Phase 6 work in this task.

Evidence: `ops/evidence/candidate-knowledge-phase5-impl/`

---

## Files added or changed

### Added

| File | Role |
|---|---|
| `wathefni-orchestrator/candidate_knowledge_tools.py` | Shadow-mode `search_candidates`, `get_candidate_knowledge`, `compare_candidates` |
| `wathefni-orchestrator/test_candidate_knowledge_phase5.py` | Shadow tool, audit, registry-isolation, budget, malice tests |

### Changed

| File | Change |
|---|---|
| `candidate_knowledge_errors.py` | Added audit/shadow/comparison typed errors |
| `candidate_knowledge_search.py` | Accept `statuses` alias + `languages` filter |

Production `action_registry.py` was **not** modified and received **no** new registrations.

---

## Tool contracts (shadow)

All tools are thin adapters over:

- `CandidateKnowledgeAuthority` (authorize/resolve/assemble)
- Phase 2/3 readers (via assemble)
- Phase 4 `CandidateKnowledgeSearchService` + index audit store

They never open SQL and never choose source authority.

### Shared requirements enforced

- non-empty tenant
- active actor
- `permission_authority=backend_current`
- matching permission subject user/tenant
- explicit `prehire.read`
- module entitlement via authority gate
- dedicated access-audit write **before** evidence return; fail closed on audit failure
- no legacy empty-permission inheritance

### Shared response envelope

- `request_id`
- `as_of`
- `knowledge_version` / index version metadata
- `retrieval_mode`
- `coverage`
- `redactions` / `omission_reasons`
- evidence references
- actionability
- `mode: "shadow"`

### `search_candidates`

Scopes: `talent_pool` | `active_applications` | `all_authorized`  
Filters: statuses/status, skills, classification_node_ids, source_channels, languages, include_finalized/archived  
Returns candidate-level hits with match reasons, snippets, actionability, and search-relevance (not hiring score).

### `get_candidate_knowledge`

Exact `app:<app_key>` via authority assemble.  
Model projection:

- full CV text omitted (`text_omitted=true`)
- relevant CV chunks under budget (≤3, snippet ≤240 chars)
- concise effective facts
- coverage + omission reasons
- application/evidence cursors

### `compare_candidates`

2–5 exact refs; one as-of/schema; unknown stated explicitly.  
No best-candidate recommendation without/despite job context auto-pick.  
Stored ranking may be attached when `job_context.position_code` is provided (read-only, no rescoring).  
Protected-trait questions fail closed.

---

## Shadow registration policy

- Enabled only when runtime `enabled=True` / `WATHEFNI_CK_SHADOW_TOOLS_ENABLED=1`
- `build_shadow_registry()` returns local callables only
- Explicitly does **not** call `action_registry.register`
- Proof: production registered intents unchanged; `search_candidates` absent from production registry

---

## Audit fail-closed

`write_access_audit_or_fail`:

1. writes content-free `candidate_knowledge_access_events` row
2. requires `event_id`
3. rejects forbidden content fields (`chunk_text`, `snippet`, `email`, `phone`, `embedding`, `query_text`, `cv_text`)
4. on failure → `audit_write_failed` and no evidence returned

---

## Tests and exact results

```text
python3 -m unittest test_candidate_knowledge_phase5 \
  test_candidate_knowledge_phase4 \
  test_candidate_knowledge_phase3 \
  test_candidate_knowledge_phase2 \
  test_candidate_knowledge_phase1 \
  test_candidate_knowledge_phase0_contracts
```

**123/123 PASS**

Phase 5 cases include:

- shadow enable/disable fail-closed
- search / get / compare happy paths
- CV chunk budget + full-text omission
- compare no-best without job context
- protected-trait refusal + arity checks
- audit failure blocks evidence
- empty permissions denied
- production action registry untouched
- zero lifecycle/communication/ranking/identity mutation
- malicious prompt does not mutate or bypass `backend_current`

Log: `ops/evidence/candidate-knowledge-phase5-impl/unittest.txt`  
Smoke: `ops/evidence/candidate-knowledge-phase5-impl/shadow-smoke.json`

---

## Proof of no production exposure

1. Tools only run when shadow runtime is enabled.
2. Production `action_registry` intents unchanged after building shadow registry.
3. Responses labeled `mode: "shadow"`.
4. No live recruiter wiring, HTTP exposure, or production registration added.
5. Zero production backfill / Ranking integration / Role Profiles.

---

## Unresolved gaps (non-blocking for Phase 5)

1. Shadow tools are local-callable only; no staging HTTP façade yet.
2. Old recruiter tools remain available and are not parity-diffed in this task.
3. Job-context compare attaches stored ranking when present but still refuses auto “best” selection.
4. Phase 6 RankingEvidenceAdapter not started.
5. Live tool flag cutover intentionally deferred.

---

## GO / NO-GO

| Decision | Result |
|---|---|
| Phase 5 local shadow tools complete | **GO** |
| Phase 6 local Ranking evidence adapter | **GO** (separate task only) |
| Begin Phase 6 in this task | **NO-GO** |
| Register tools in live production action registry | **NO-GO** |
| Expose to production users / live AI recruiter | **NO-GO** |
| Production deploy / backfill | **NO-GO** |
| Live Ranking integration | **NO-GO** |
| Role Profiles | **NO-GO** |

### Exact permitted Phase 6 scope (when authorized later)

- Pure `RankingEvidenceAdapter` over authorized CandidateKnowledgeRecord
- Pin knowledge/evidence versions in local evaluations
- Prove held rows cannot enter job ranking
- Prove Candidate Knowledge reads never create ranking rows
- Still no production deploy or Role Profiles unless separately authorized

---

## Stop

Stopped after this report. Phase 6 was not started.
