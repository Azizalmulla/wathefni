# Pre-hiring Candidate Knowledge — Phase 6 Implementation

Date: 2026-07-26  
Scope: local Phase 6 only (`RankingEvidenceAdapter` + shadow parity)  
Production deploy: none  
Live action-registry tool registration: none  
Live AI recruiter exposure: none  
Production backfill: none  
Live Ranking path cutover: none  
Role Profiles: none  
Phase 7+: not started

## Verdict

Phase 6 local Ranking evidence adapter and shadow parity are complete and tested.

**GO for Phase 7 local/staging qualification planning**, in a separate authorized task.  
**NO-GO** for production deploy, live tool registration, live Ranking cutover, Role Profiles, or Phase 7 execution in this task.

Evidence: `ops/evidence/candidate-knowledge-phase6-impl/`

---

## Files added or changed

### Added

| File | Role |
|---|---|
| `wathefni-orchestrator/ranking_evidence_adapter.py` | Pure read-only `RankingEvidenceAdapter`, pins, staleness |
| `wathefni-orchestrator/ranking_evidence_shadow.py` | Dual-path shadow parity harness + difference classification |
| `wathefni-orchestrator/test_ranking_evidence_adapter.py` | Adapter, versioning, missing-evidence, shadow parity tests |

### Not modified (intentionally)

- `candidate_ranking.py` production scoring/run lifecycle
- `action_registry.py`
- live Ranking HTTP/predicates
- Phase 5 shadow tools registration policy

---

## RankingEvidenceAdapter contract

### Input

- authorized `CandidateKnowledgeRecord`
- exact tenant + Job/position context (`RankingJobContext`)
- exact `criteria_version` (required)
- optional application/governance rows for eligibility
- evidence policy / interview-summary permission flags

### Output (`RankingEvidenceBundle`)

- scorer-compatible `row` for `evaluate_application_eligibility` / `soft_component_scores`
- eligibility + denial reason
- version pins + evidence digest
- coverage / unavailable sections (`unknown_not_negative`)
- HR-confirmed vs AI-suggested classifications (separated)
- screening claims with source labels
- assessment summaries (when module permitted)
- interview summaries only when explicitly permitted
- actionability
- zero side-effect counters

### Inclusion

- effective reviewed CV facts → `application_cv_facts` snapshot shape
- current canonical CV version readiness fields
- bounded facts-derived semantic projection (not full CV body)
- candidate-reply / cv-prefill screening claims
- assessment summaries under existing Ranking policy posture
- classification labels with authority separation
- `knowledge_version` and source/review fingerprints

### Exclusion

- `applications.raw_json`
- `candidates.profile`
- unrestricted CV text
- identity-review alternatives
- private notes
- assessment answer sets
- full interview transcripts / meet links / secrets
- contact values
- internal storage paths

---

## Eligibility and held-state behavior

Uses `evaluate_candidate_record_state` / actionability:

| State | Adapter result |
|---|---|
| live eligible (`shortlisted`, etc.) | `eligible=True` |
| held (`needs_role` / `import_review` / `import_archived`) | `eligible=False` (`held_or_job_ranking_ineligible`) |
| archived | `eligible=False` |
| restricted / deletion-completed | hard `candidate_restricted` |
| cross-tenant Job context | denied |
| missing position/criteria version | `invalid_comparison_context` |

Held Talent Pool candidates remain searchable via Candidate Knowledge tools, but the adapter never admits/binds them to a Job and never creates ranking rows.

---

## Version pinning and staleness

Every adapted evaluation pins:

- `candidate_ref`, `app_key`
- `knowledge_version`
- canonical CV version
- fact snapshot + review fingerprint
- classification run + review fingerprint
- assessment/interview ids when used
- criteria version + scorer model version
- evidence digest + retrieved_at

`is_evaluation_stale(...)` reports stale reasons when any effective input changes and sets `rewrites_historical=false`.

---

## Dual-path shadow comparison

`run_shadow_parity`:

1. **Existing path**: legacy-shaped row (`raw_json` / `candidate_profile`) → existing scorers
2. **Adapter path**: CK record → `RankingEvidenceAdapter` → same scorers
3. Paths never mixed
4. Differences classified as:
   - `expected_evidence_improvement`
   - `expected_authority_difference`
   - `bug`
   - `unexplained`
   - `blocked_by_missing_canonical_evidence`
5. Unexplained score differences fail qualification
6. Confirms no ranking/lifecycle/communication/identity/extraction/indexing side effects

Preserves Phase 0 boundary: job-scoped `candidate_ranking` remains production authority; live AI registry ranking/search is not silently unified.

Confirmed reconciliations:

- production authority is job-scoped `candidate_ranking`
- obsolete local-only role_profile / screening-before-assign defects are not reintroduced
- `compare_candidates` remains a separate tool-registration gap (shadow-only in Phase 5)
- no name-first deduplication in the adapter

---

## Exact test results

```text
python3 -m unittest test_ranking_evidence_adapter \
  test_candidate_knowledge_phase5 \
  test_candidate_knowledge_phase4 \
  test_candidate_knowledge_phase3 \
  test_candidate_knowledge_phase2 \
  test_candidate_knowledge_phase1 \
  test_candidate_knowledge_phase0_contracts \
  test_candidate_ranking
```

**167/167 PASS**

Phase 6 cases cover:

- valid eligible candidate
- held / archived / restricted / deleted denial
- cross-tenant + missing Job/criteria context
- facts + HR/AI classification separation
- candidate-reply vs cv-prefill labeling
- assessment included; interview gated; sensitive data excluded
- knowledge/CV/fact/classification/criteria staleness
- WhatsApp/manual incomplete missing-evidence = unknown, not automatic zero merit
- dual-path shadow parity + held exclusion + zero side effects
- Arabic/bilingual facts

Log: `ops/evidence/candidate-knowledge-phase6-impl/unittest.txt`

---

## Qualification results

Artifact: `ops/evidence/candidate-knowledge-phase6-impl/qualification.json`

| Area | Result |
|---|---|
| Evidence coverage | Adapter drops legacy profile fallback; uses canonical facts |
| Eligibility parity | Held exclusion matches production policy |
| Scores/breakdowns | Compared via same scorers; differences classified |
| Stale/version | CV version change marks prior evaluation stale; no rewrite |
| Latency | Sub-ms local scorer+adapter path in smoke |
| Missing evidence | Unavailable sections flagged `unknown_not_negative` |
| Arabic/bilingual | Skills preserve Arabic + English values |
| Zero side effects | All mutation counters remain 0 |
| Live cutover | false |
| Live tools registered | false |

---

## Zero-mutation proof

1. Adapter exposes mutation counters that remain 0 across adapt calls.
2. Shadow harness scores in-memory only; no `rank_job_applications` persistence.
3. No Ranking run writes, Job admission, communication, identity, OCR/extraction, or index jobs.
4. No production action-registry registration and no live recruiter exposure.

---

## Unresolved gaps (non-blocking for Phase 6)

1. Live Ranking cutover not performed (by design).
2. Full production pool SQL dual-run against real DB is deferred to Phase 7 staging qualification.
3. LLM explanation quality against stored Ranking narratives is not evaluated here.
4. Assessment contribution still follows default Ranking policy (`assessment=unused`) unless criteria explicitly select it.
5. Phase 7 qualification matrices / staging plan not started.

---

## GO / NO-GO

| Decision | Result |
|---|---|
| Phase 6 local complete | **GO** |
| Phase 7 local/staging qualification planning | **GO** (separate task only) |
| Begin Phase 7 in this task | **NO-GO** |
| Production deploy | **NO-GO** |
| Live Ranking cutover | **NO-GO** |
| Register CK tools in live action registry | **NO-GO** |
| Role Profiles | **NO-GO** |

### Exact permitted Phase 7 scope (when authorized later)

- Local then staging qualification matrices from the architecture plan
- Synthetic-only staging data unless separately governed
- Still no production cutover/backfill/tool exposure unless separately authorized

---

## Stop

Stopped after this report. Phase 7 was not started.
