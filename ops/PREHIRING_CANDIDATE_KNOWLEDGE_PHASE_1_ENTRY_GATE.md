# Pre-hiring Candidate Knowledge — Phase 1 Entry Gate

Date: 2026-07-26  
Prior: Phase 0 NO-GO accepted → runtime/source reconciliation accepted → Phase 1 entry gate re-run  
Implementation in this task: **none**  
Production deploy: **none**  
Schema / indexing / Voyage / backfill / Role Profiles: **none**

## Verdict

**GO for implementing Phase 1 locally.**

Every listed entry prerequisite passes against the reconciled checkout. Remaining items are documented non-blockers or later-phase work.

Evidence pack: `ops/evidence/candidate-knowledge-phase1-entry/`

---

## Contract verification (reconciled checkout)

| Contract | Evidence | Result |
|---|---|---|
| Production-aligned `cv_extraction.py` | SHA `2859dc7e…` matches production; `record_extraction_finalization` present | **PASS** |
| Production-aligned `action_registry.py` | SHA `b7992797…` matches production; 75 registered actions; job-scoped ranking via `candidate_ranking` | **PASS** |
| Production-aligned `app.py` | SHA `f2a3a829…` = production base + documented local-only additive surface; **0 missing production symbols**; wires facts/evidence/`rank_candidates_compat`/`materialize_extracted_cv`/`extract_application_cv_facts`/`talent_pool_auto_email` | **PASS** |
| Restored `candidate_cv_facts` | SHA `4c01145e…` | **PASS** |
| Restored `candidate_cv_evidence` | SHA `06de2da2…` | **PASS** |
| Restored `candidate_ranking` | SHA `9b8a54f1…` | **PASS** |
| Runtime deps | `assistant_*`, `ranking_result_presentation`, `candidate_collaboration`, `candidate_identity`, `interview_*`, `reports_v1`, `talent_pool_auto_email_classification` SHA-match production copies | **PASS** |

Hash matrix: `ops/evidence/candidate-knowledge-phase1-entry/contract-hash-matrix.txt`

### Tests re-run for this gate

| Suite | Result |
|---|---|
| `test_candidate_cv_facts` + `test_candidate_cv_evidence` + `test_candidate_ranking` + `test_candidate_knowledge_phase0_contracts` | **70/70 PASS** |
| `smoke-test-cv-extraction-ocr.py` | **32/32 PASS** |
| `smoke-test-cv-docx.py` | **25/25 PASS** |

Logs under `ops/evidence/candidate-knowledge-phase1-entry/`.

Note: DB-backed inbound/registry parity smokes remain environment-blocked locally (`psycopg2` / test DB). They are **not** required merely to implement Phase 1 policy/resolution locally.

---

## Prerequisite checklist

### 1. Production/runtime drift blockers cleared

**PASS**

- Phase 0 blockers were `cv_extraction`, `action_registry`, and unwired `app.py`.
- Reconciliation restored production byte identity for `cv_extraction` / `action_registry` and production-superset `app.py`.
- Evidence materialization tests now pass (finalization contract present).
- References: `ops/PREHIRING_CANDIDATE_KNOWLEDGE_RUNTIME_SOURCE_RECONCILIATION.md`

Residual non-blocker: reconciled `app.py` is intentionally not a byte clone of production (local-only additive UI/debug endpoints). All production symbols and CV facts/evidence/ranking wiring are present.

### 2. `candidate-knowledge-v1` DTOs and JSON schema remain valid

**PASS**

- DTOs: `wathefni-orchestrator/candidate_knowledge_types.py`
- JSON Schema: `wathefni-orchestrator/schemas/candidate_knowledge_v1.json`
- Synthetic `CandidateKnowledgeRecord.to_dict()` contains every schema `required` key
- `schema` const = `candidate-knowledge-v1`
- `candidate_ref` matches `^app:.+`
- No `CandidateKnowledgeAuthority` implementation exists (correct for this gate)

### 3. Exact `app:<app_key>` references compatible with current data

**PASS**

- DTO helpers: `candidate_ref_from_app_key` / `app_key_from_candidate_ref`
- Live resolver: `find_application_by_key(app_key, company_code)` requires non-empty key **and** resolved company scope, then `WHERE a.app_key=%s AND a.company_code=%s`
- Applications are the durable anchor in production schema (`applications.app_key`)
- Phase 0 fixtures already use app-keyed subjects (Mariam / multi-app / surrogate)

Compatible with current phone-keyed `candidates` table: ref is application-anchored; person aggregation is a later read of already-bound apps, not a new identity invent.

### 4. Tenant-scoped application and candidate resolution contracts understood

**PASS**

Documented current contracts:

| Operation | Contract |
|---|---|
| Exact app read | `find_application_by_key` — tenant + app_key; joins `candidates` on `phone` |
| Sibling apps for same candidate key | same `company_code` + same `phone` (including `imp-…` surrogates) |
| Production search/rank pool | `production_application_predicate` excludes held intake statuses + non-production sources/tests |
| Name-only | must not bind/merge; Phase 1 returns ambiguity (architecture rule) |
| Surrogate vs real phone | remain separate until governed identity links them |

No inferred production behavior required: these are present in reconciled source.

### 5. Backend-current permission context can be enforced fail-closed

**PASS** (as a Phase 1 implementation requirement that current primitives support)

Existing primitives:

- `permission_authority` / `backend_current` / `backend_current_required` surfaces in `app.py`
- `permission_authority_preflight`
- `dashboard_context_has_permission` — empty permission set denies (`requested in context_permissions`)
- Tool map baseline permission for recruiter reads: `prehire.read`

Explicit Phase 1 rule (architecture): empty/untrusted permission lists are **denial**, including read tools. Current `tool_call_orchestrator` still admits empty perms for `*.read` when strict WhatsApp flag is off — Phase 1 authority **must not inherit** that compatibility. That is an implementation constraint, not an entry blocker.

### 6. `CandidateRecordStatePolicy` inputs and divergent held states fully mapped

**PASS**

Artifact: `ops/evidence/candidate-knowledge-phase1-entry/held-state-policy-inputs.json`

| Domain | Held / special treatment |
|---|---|
| App + communication | `needs_role`, `import_review`, `import_archived` (`HELD_IMPORT_STATUSES`) |
| Production search predicate | same three excluded; **`review_pending` included** |
| Inbound identity / retention | adds **`review_pending`** (`inbound_retention_policy.HELD_APPLICATION_STATUSES`) |
| Governance | independent archived / restricted / legal-hold / deletion states via `candidate_record_governance` + communication authority constants |
| Ranking eligibility | job-scoped ranking uses production predicate / ranking module; held intake excluded from production pools |

Phase 1 must encode named decisions (`intake_hold_state`, `communication_allowed`, `job_ranking_eligible`, `talent_pool_search_eligible`, `retention_blocked`, `read_projection`, reason codes) rather than collapsing to one boolean.

### 7. Source tables queryable through documented read contracts

**PASS** for Phase 1 entry (tables exist; read modules/contracts known)

From Phase 0 production schema manifest (33 knowledge tables, `missing: []`) plus read-only production probe for collaboration notes:

| Family | Tables / contract | Present |
|---|---|---|
| Subject / apps | `applications`, `candidates` | yes |
| Governance | `candidate_record_governance` | yes (0 rows currently; schema exists) |
| Identity | `candidate_identity_keys`, `inbound_cv_identity_reviews`, `inbound_cv_identity_resolutions`; `candidate_identity.py` readers | yes |
| CV / extraction | `candidate_documents`, `candidate_cv_text_versions`, `cv_extraction_*`, `file_registry` | yes |
| Facts / evidence | `application_cv_fact_snapshots`, `candidate_fact_review_events`, `application_cv_evidence_materializations`; facts/evidence modules | yes |
| Classification | `candidate_classification_*`, taxonomy tables | yes |
| Assessments | `assessment_attempts`, `assessment_scores`, `assessment_reports` | yes |
| Interviews | `candidate_interviews`; `interview_lifecycle` / `interview_service` | yes |
| Ranking | `candidate_rank_evaluations`, `ranking_runs`, `ranking_run_items`, `semantic_documents`; `candidate_ranking` | yes |
| Screening | application `raw_json.screening` / columns (no separate table required for Phase 1 policy) | yes |
| Notes / collab | `application_notes`, note/task/tag event tables | **yes in production** (Phase 0 manifest gap only; probe: `notes-tables-probe.json`) |

Phase 1 itself only needs policy + exact subject resolution; full section readers are Phases 2–3. Entry requires that those sources are known and reachable without inventing runtime behavior.

### 8. No source reader requires inferred or missing production behavior

**PASS**

Reconciled checkout includes the production readers/modules Phase 1 will call into later:

- facts/evidence/ranking modules restored and SHA-matched
- `cv_extraction` finalization contract restored
- collaboration/identity/interview/assistant ranking presentation modules restored
- `find_application_by_key` and governance loaders exist in source

No Voyage/index/schema change is required for Phase 1 policy/resolution.

### 9. `compare_candidates` unregistered does not block Phase 1

**PASS** (non-blocker; later tool-registration gap)

- `compare_candidates` remains implemented in `app.py` but **not** registry-registered in production.
- Phase 1 delivers request context, exact `candidate_ref` resolution, aggregation policy, and actionability — not tool registration.
- Architecture places new `compare_candidates` on the authority in **Phase 5**.
- Recorded gap: register/replace compare tooling only after authority exact-read parity.

### 10. No production mutation / schema / indexing / Voyage / backfill required for local Phase 1

**PASS**

Phase 1 is local policy + exact subject resolution + denial tests. It does not:

- alter production data
- add Candidate Knowledge storage schema
- index chunks
- call Voyage
- backfill facts/embeddings
- begin Role Profiles

---

## Remaining non-blockers

1. Reconciled `app.py` is a production **superset** (local additive UI/debug endpoints). Keep marker; do not silently drop or promote without review.
2. Staging-only `internal_intake_readiness` still absent from checkout.
3. Collaboration note tables were missing from the Phase 0 schema manifest document (they exist in production). Update documentation when Phase 3 notes federation starts.
4. Live tool orchestrator empty-perm read admission still exists — Phase 1 authority must fail closed independently.
5. DB-backed inbound/registry canaries not re-run in this local environment.
6. `compare_candidates` registry registration deferred to later tool phase.

None of these block local Phase 1 implementation.

---

## Remaining blockers

**None for local Phase 1 entry.**

---

## GO / NO-GO

| Decision | Result |
|---|---|
| Implement Phase 1 locally | **GO** |
| Deploy production | **NO-GO** (not requested; not authorized) |
| Add Candidate Knowledge schema / indexing / Voyage / backfill | **NO-GO** |
| Begin Role Profiles | **NO-GO** |
| Implement authority beyond Phase 1 in the same task | **NO-GO** — stop after this report |

---

## Exact permitted scope if GO

Implement **only** architecture Phase 1 — policy and exact subject resolution:

1. `CandidateKnowledgeRequestContext` requiring non-empty tenant, actor, `permission_authority=backend_current`, matching subject user/company, explicit `prehire.read`.
2. Fail-closed denial for empty/untrusted permissions (do not inherit tool-orchestrator empty-perm compatibility).
3. Exact `candidate_ref = "app:" + app_key` resolution via existing tenant-scoped application lookup.
4. Aggregate only applications already bound by existing candidate key within the same tenant (phone / surrogate key as today).
5. Name-only exact reads return ambiguity; no merge/binding.
6. `CandidateRecordStatePolicy` encoding the mapped divergent held/governance decisions and actionability.
7. Cross-tenant and empty-permission denial tests.
8. No source reader execution before policy + tenant resolution (Phase 1 exit gate).

Out of scope until a later authorized task:

- Phase 2+ CV/facts/classification assembly
- Phase 3 history/notes federation
- Phase 4 indexing / Voyage
- Phase 5 tool registration (`search_candidates` / `get_candidate_knowledge` / new `compare_candidates`)
- Phase 6 Ranking adapter
- production promotion
- Role Profiles

---

## Stop

Gate evaluation complete. **Do not begin Phase 1 implementation in this task.**
