# Pre-hiring Candidate Knowledge — Phase 3 Implementation

Date: 2026-07-26  
Scope: local Phase 3 only  
Production deploy: none  
Candidate Knowledge indexing tables / Voyage / backfill / model tools / Role Profiles: none  
Phase 4+: not started

## Verdict

Phase 3 local implementation is complete and tested.

**GO for Phase 4 local indexing and retrieval work**, in a separate authorized task.  
**NO-GO** for production deploy, indexing schema, Voyage calls, backfill, tool registration, Role Profiles, or Phase 4 work in this task.

Evidence: `ops/evidence/candidate-knowledge-phase3-impl/`

---

## Files added or changed

### Added

| File | Role |
|---|---|
| `wathefni-orchestrator/candidate_knowledge_phase3_readers.py` | Application history, screening, assessments, interviews, ranking, notes, identity readers |
| `wathefni-orchestrator/test_candidate_knowledge_phase3.py` | Phase 3 focused regression suite |

### Changed

| File | Change |
|---|---|
| `wathefni-orchestrator/candidate_knowledge_store.py` | Phase 3 read-only store protocol + Postgres/InMemory adapters |
| `wathefni-orchestrator/candidate_knowledge_authority.py` | `assemble_phase3`; Phase 3 section gate; preserves Phase 1/2 |

---

## Reader contracts

| Reader | Sources | Payload |
|---|---|---|
| `read_applications` | Bound apps + governance + lifecycle events + current CV version refs | Newest-first paginated history with eligibility flags |
| `read_screening_evidence` | `get_screening_facet` only (screening JSON facet) | Typed answers with `candidate_reply` / `cv_prefill` / parser/system |
| `read_assessments` | `assessment_attempts` + scores + approved report summary fields | Attempt state/score/band/section scores/review/cancel/expiry |
| `read_interviews` | `candidate_interviews` + feedback submissions | Schedule/status/human notes/transcript availability/AI summary/consent |
| `read_ranking_evaluations` | `candidate_rank_evaluations` + `ranking_run_items`/`ranking_runs` | Job-scoped stored scores only; no rescoring |
| `read_notes` | application notes + screening/interview/assessment/fact/classification/identity notes | Federated workflow notes; not a complete HR notes store |
| `read_identity_state` | identity reviews/resolutions/keys | Safe summary state; detail requires `candidate.manage` |

All readers return `SectionRead(payload, coverage, evidence)` and run only after authorize + exact resolve via `assemble_phase3`.

---

## Permissions and redaction rules

| Section | Minimum gate |
|---|---|
| applications / screening | `backend_current` + `prehire.read` + `pre_hiring` |
| assessments | above + assessments module entitlement |
| interviews | above + pre-hire posture; explicit `interviews` module gate only when listed |
| ranking history | `prehire.read` (read stored evidence only) |
| notes (non-identity) | `prehire.read` |
| identity detail / identity notes | `candidate.manage` |
| contacts | remain redacted in default subject projection |
| restricted / deletion | `CandidateRecordStatePolicy` → section `restricted` or whole-record `candidate_restricted` |

Forbidden sources remain blocked: `applications.raw_json`, `candidates.profile`, `semantic_documents`.

Interview secrets excluded: calendar payloads/tokens, meet links, sent bodies/subjects, signed links, full transcripts, consent payloads.

Assessment secrets excluded: raw answer sets, unrestricted `report_json`, artifact paths, tokens.

---

## Application-history behavior

- Uses already-bound same-tenant applications from Phase 1 resolution (phone/`imp-…` key).
- Newest first by `updated_at` / `ingested_at` / `created_at`.
- Paginated (`limit`/`offset`, max 200).
- Never deduplicates by candidate name.
- Never merges manual surrogate phones with real phones.
- Preserves held (`needs_role`/`import_review`/`import_archived`), live pipeline, and finalized (`hired`/`rejected`/`withdrawn`) buckets.
- Emits communication / lifecycle-mutation / assessment / interview / job-ranking eligibility from state policy.
- Includes lifecycle event summaries and current CV version ref when unambiguous.

---

## Screening evidence behavior

- Reads screening facet only; does not expose full application `raw_json`.
- Labels sources explicitly; `cv_prefill` is never relabeled as `candidate_reply`.
- Preserves salary/availability/visa/etc. values with timestamps, confidence, parser/model, correction state.
- Marks stale answers (`stale` flag / incomplete screening status).
- Missing dedicated fields are omitted, not invented.

---

## Assessment / interview behavior

Assessments:

- Module-disabled coverage when assessments entitlement is absent.
- Returns completed/pending/cancelled/expired states.
- Exposes approved summary fields only.

Interviews:

- Human feedback notes remain human-authored.
- AI summaries labeled `ai_generated`.
- Transcript availability boolean only (no transcript body).
- Consent accepted/timestamp only (no consent payload).

---

## Ranking-history behavior

- Federates stored `candidate_rank_evaluations` and `ranking_run_items`.
- Every score carries exact job/position and criteria/version context.
- Explicit `not_general_candidate_quality=true`.
- Stale when run `is_current=false` or stale markers present.
- `creates_new_evaluations=false`; `create_rank_evaluation` raises and increments side-effect counters.

---

## Notes federation

Federates where present:

- application notes (non-deleted)
- screening notes
- interview human notes
- assessment review notes
- fact-review notes
- classification-review notes
- identity-review notes (`candidate.manage` only)

Each note keeps source workflow, author, timestamp, app, visibility, authority state.  
Payload states `complete_hr_note_history=false`.

---

## Identity-state behavior

Safe states:

- `resolved`
- `open_review`
- `conflict`
- `provisional`
- `not_governed_by_current_identity_authority`

Always `open_identity_review_resolves=false`.  
Default projection omits unrelated possible-match identities.  
`candidate.manage` unlocks detail counts/review ids/notes without exposing match phone lists.

---

## Coverage matrix

Artifact: `ops/evidence/candidate-knowledge-phase3-impl/coverage-matrix.json`

Sample assemble (`app-live` + held sibling):

| Section | Sample state |
|---|---|
| applications | `available` |
| screening_evidence | `available` |
| assessments | `available` |
| interviews | `available` |
| ranking_evaluations | `available` |
| notes | `partial`/`available` |
| identity_state | `available` (`open_review`) |

Also covered by tests: `module_disabled`, `restricted`, `stale`, `conflict`, `not_recorded`, `not_authorized`.

---

## Test results

```text
python3 -m unittest test_candidate_knowledge_phase3 \
  test_candidate_knowledge_phase2 \
  test_candidate_knowledge_phase1 \
  test_candidate_knowledge_phase0_contracts
```

**92/92 PASS**

Phase 3 cases include:

- multi-app ordering/pagination
- held/live/finalized history
- WhatsApp reply vs CV-prefill + salary/availability labeling
- stale/corrected screening
- completed/pending/cancelled/expired assessments
- assessments module disabled
- interview human feedback + AI summary + consent + transcript unavailable
- job-scoped ranking + stale ranking + zero ranking side effects
- federated notes + deleted-note visibility + identity-note manage gate
- open identity review + conflict + detail denial without `candidate.manage`
- cross-tenant denial
- restricted/deletion suppression
- no raw JSON pass-through
- zero writes / OCR / Voyage
- Phase 4 section denied; Phase 2 still cannot assemble Phase 3 sections

Log: `ops/evidence/candidate-knowledge-phase3-impl/unittest.txt`

---

## Zero-mutation proof

1. Successful `assemble_phase3` leaves `write_attempts`, `external_calls`, `ocr_triggers`, `ranking_side_effects` unchanged.
2. Authority `mutation_count` remains 0.
3. Explicit `mutate` / `call_voyage` / `trigger_ocr` / `create_rank_evaluation` raise and are the only increments.
4. Assembled dicts contain no `raw_json`, meet links, transcripts, or unrestricted assessment report payloads.

---

## Unresolved gaps (non-blocking for Phase 3)

1. Postgres adapter is implemented but not live-wired into production HTTP/tool routes.
2. Screening still originates from application screening JSON facet (canonical for WhatsApp today); no dedicated screening table rewrite.
3. Notes federation is intentionally incomplete versus a hypothetical single HR notes store.
4. Identity manage detail still withholds possible-match identity values by design.
5. Phase 2 anchor-only CV/facts/classification behavior unchanged inside `assemble_phase3` (history fans out; Phase 2 sections remain anchor-scoped).
6. Phase 4 indexing/Voyage/search tools not started.
7. Model-facing tools remain unregistered.

---

## GO / NO-GO

| Decision | Result |
|---|---|
| Phase 3 local complete | **GO** |
| Phase 4 local indexing/retrieval | **GO** (separate task only) |
| Begin Phase 4 in this task | **NO-GO** |
| Production deploy | **NO-GO** |
| Add Candidate Knowledge indexing tables / Voyage / backfill | **NO-GO** |
| Register model-facing tools | **NO-GO** |
| Role Profiles | **NO-GO** |

### Exact permitted Phase 4 scope (when authorized later)

- Local schema for chunks / index jobs / access events
- Deterministic section-aware chunking of immutable current CV versions
- Lexical search + Voyage/pgvector retrieval with disclosed degradation
- Invalidation and governance suppression
- Still no production deploy, Role Profiles, or tool registration unless separately authorized

---

## Stop

Stopped after this report. Phase 4 was not started.
