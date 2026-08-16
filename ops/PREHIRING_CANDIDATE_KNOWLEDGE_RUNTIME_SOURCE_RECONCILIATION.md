# Pre-hiring Candidate Knowledge — Runtime / Source Reconciliation

Date: 2026-07-26  
Status: local reconciliation complete; **no production deploy**  
Prior gate: Phase 0 **NO-GO** (source/runtime drift) — accepted  
CandidateKnowledgeAuthority: not implemented  
Candidate Knowledge schema / indexing / Voyage / backfill / Role Profiles: not started

## Verdict

| Gate | Result |
|---|---|
| Local source now represents production contracts for the three drifted files (+ required deps) | **YES** (with documented additive overlay on `app.py`) |
| Promote reconciled runtime source to production in this task | **NO-GO** (not authorized; see promotion plan) |
| Re-run Phase 1 entry gate | **GO** |

---

## Exact three-way inventory

Evidence pack: `ops/evidence/candidate-knowledge-runtime-reconciliation/`

| File | Preimage local SHA | Production SHA | Staging SHA | Reconciled checkout SHA | Prod==Staging | Reconciled==Prod |
|---|---|---|---|---|---|---|
| `cv_extraction.py` | `4dace00f…` | `2859dc7e…` | `2859dc7e…` | `2859dc7e…` | yes | **yes** |
| `action_registry.py` | `92ea89bc…` | `b7992797…` | `b7992797…` | `b7992797…` | yes | **yes** |
| `app.py` | `d7a9f7ec…` | `b4a9a4b0…` | `7e7caf5f…` | `f2a3a829…` | no | no (prod + local-only graft) |

Line counts:

| File | Local | Production | Staging | Reconciled |
|---|---:|---:|---:|---:|
| `cv_extraction.py` | 1740 | 1822 | 1822 | 1822 |
| `action_registry.py` | 5627 | 6758 | 6758 | 6758 |
| `app.py` | 58588 | 60118 | 60270 | 60592 |

Diff artifacts:

- `diffs/cv_extraction.local-vs-prod.diff` (~100 lines; additive only)
- `diffs/action_registry.local-vs-prod.diff` (~2563 lines)
- `diffs/action_registry.prod-vs-staging.diff` (empty — identical)
- `diffs/app.prod-vs-staging.diff` (~445 lines)
- `diffs/app.prod-vs-reconciled.diff` (+474 lines only; pure additive tail)
- `diffs/app-merge-decisions.json`
- `diffs/reconciliation-summary.json`

---

## Why the drift occurred

Evidence-backed causes (not speculation beyond the trees):

1. **Checkout lagged the deployed facts/evidence/ranking cutover.**  
   Production/staging already imported and wired `candidate_cv_facts`, `candidate_cv_evidence`, and `candidate_ranking`, including `materialize_extracted_cv`, `extract_application_cv_facts`, and `rank_candidates_compat`. Preimage local `app.py` did not.

2. **`cv_extraction` finalization contract landed in runtime first.**  
   Local vs prod diff is purely additive: `cv_extraction_finalizations` DDL inside `ensure_cv_extraction_schema` plus `record_extraction_finalization`. No local-only functions existed. Production and staging already matched.

3. **Assistant ranking was replaced on production, not patched in the old local executor.**  
   Preimage local `_rank_candidates_executor` was still the obsolete semantic pool scorer (`rank_candidate_row`, pool-limit getattr, screening-before-assign). Production registry already delegates to job-scoped `candidate_ranking` (`replay_only` default). Phase 0 “defects” were **preimage-local**, not production behavior.

4. **Registry surface expanded on production** (+11 actions for ownership/tasks/notes/timeline/identity/reports/interview cancel-reschedule). Local had a strict subset (64 vs 75). Production==staging for `action_registry.py`.

5. **`app.py` three-way divergence is real.**  
   - Production has C2/C3 collaboration/identity surfaces and stricter governed inbound provenance in `process_candidate_cv_document`, plus `talent_pool_auto_email` enqueue.  
   - Staging shares facts/evidence/ranking wiring with production but still carries `internal_intake_*` debug endpoints and lacks production’s `talent_pool_auto_email` path; staging `process_candidate_cv_document` is behind production’s inbound authority checks.  
   - Local preimage lacked facts/evidence wiring but had newer dashboard unified-candidate/saved-view/intake-operations UI plus most `internal_intake_*` debug routes (without staging’s `internal_intake_readiness`).

---

## Per-file analysis and chosen authority

### `cv_extraction.py`

| Category | Finding |
|---|---|
| Production-only | `record_extraction_finalization` + `cv_extraction_finalizations` schema |
| Local-only | none |
| Staging-only | none (identical to production) |
| Generated/config-only | none |
| Obsolete/unsafe | none in local relative to prod |
| Deps on restored modules | required by `candidate_cv_evidence.materialize_extracted_cv` |

**Authority:** exact production copy.  
**Restored contracts:** finalization recorder, finalizations table ensure, evidence materialization prerequisite.

### `action_registry.py`

| Category | Finding |
|---|---|
| Production-only actions | `assign_candidate_owner`, `cancel_interview`, `create_candidate_task`, `get_candidate_ownership`, `get_candidate_timeline`, `get_person_identity`, `get_reports_metrics`, `list_candidate_notes`, `list_candidate_tasks`, `list_duplicate_suggestions`, `reschedule_interview` |
| Local-only actions | none |
| Staging-only | none (identical to production) |
| Rank path | production = job-scoped `candidate_ranking`; local preimage = obsolete semantic scorer |
| `compare_candidates` | **not registered** in production (same as local) |
| `role_profile` / screening defects | **absent in production** (executor no longer calls `rank_candidate_row`) |
| Pool limits | production assistant rank uses top_n caps via legacy getattr; no obsolete `POOL_LIMIT` semantic scorer path |
| Permission admission | unchanged live behavior via `tool_call_orchestrator` empty-perm `*.read` admission when strict WhatsApp flag is off |

**Authority:** exact production copy.  
**Required supporting modules restored from production into checkout** (previously missing locally):

| Module | SHA-256 |
|---|---|
| `assistant_jobs_ux.py` | `2c294e2c4b23a868e35e3e6493e602df3f3a27b2b135e3cfedd0b83ed5132627` |
| `assistant_policy.py` | `122aad29e15792ce860b878329ad32d39221aac69f08a9228fd9e04dbf92f2ac` |
| `assistant_privacy.py` | `feb5b707a933c2becfc3303b187a5000bb6ba3a1aca09cad1600332bf3554f28` |
| `ranking_result_presentation.py` | `8d2f3c9f10931e2d528dc98282c1bfec892301e3838e7c6b0b2b13ff953be64b` |
| `candidate_collaboration.py` | `f6385812766801be01a9b45e956d3c52c50a1e2b018c737e355d94b676430efa` |
| `candidate_identity.py` | `ce21ed97a55e54a24bf3f99d029d3e115c6d8c83c3888cc522d44b9ef3248b3a` |
| `interview_lifecycle.py` | `09a6a91b96a5a009345e2193dbadcb3c1debe760a46e4e04f2fa235cbeab3784` |
| `interview_service.py` | `17e1a33d85eea15bdb1773891b49b8746cf0ff9b4a537f4fc0cf5e226f505e9d` |
| `reports_v1.py` | `52c7bade5335141630bbfd7723f6bb382e2ad3f677d3f4a13fbcae1e50257965` |

`talent_pool_auto_email_classification.py` was already present locally and already matched production (`f1503ab5…`).

### `app.py`

| Category | Finding |
|---|---|
| Production-only (vs preimage local) | facts/evidence/ranking imports + wiring; C2/C3 collaboration/identity APIs; `talent_pool_auto_email` enqueue; stricter governed inbound provenance in CV processing |
| Staging-only vs production | `internal_intake_*` debug endpoints including `internal_intake_readiness`; weaker inbound provenance than production in shared CV processing |
| Local-only vs production | unified candidate profile/facts/saved-views/intake-operations dashboard endpoints; `internal_intake_*` (without readiness) |
| Shared body conflicts (75 funcs) | **production won** (runtime authority). No shared-function local-only signal justified overriding production |
| Generated/config-only | not the dominant delta |

**Authority / merge strategy:** `production_base_plus_local_only_symbols`

- Base = exact production `app.py`
- Grafted additive local-only symbols (decorators included) at file end under `LOCAL-ONLY ADDITIVE SURFACE`
- Grafted names:
  - `_unified_candidate_profile_payload`
  - `dashboard_prehire_application_profile` / `_facts` / `_fact_review`
  - `dashboard_prehire_saved_views` / `_save_view` / `_delete_saved_view`
  - `dashboard_prehire_intake_operations` / `_intake_attention`
  - `internal_intake_operations` / `_worker_run` / `_job_replay` / `_quarantine_sweep` / `_signed_download` / `_quarantine_download`
- Not grafted: staging-only `internal_intake_readiness` (absent from local preimage)

Reconciled `app.py` vs production diffstat: **+474 lines only** (no production lines removed).

---

## Restored contracts (qualification targets)

Confirmed present in reconciled checkout:

- `record_extraction_finalization` + finalizations schema ensure
- `materialize_extracted_cv` / `extract_application_cv_facts` wiring in `process_candidate_cv_document`
- `candidate_ranking.rank_candidates_compat` via `app.rank_candidates`
- production assistant rank path through registry → `candidate_ranking`
- inbound durable email ingress surface retained
- local intake debug worker endpoints retained additively
- held-status exclusions via `production_application_predicate`
- tenant scope preserved in grafted helpers (`company_code` filters)

Phase 0 “defect” pins were corrected to production truth:

- obsolete local `role_profile` / screening defects are retained only as **historical preimage evidence**
- production does **not** exhibit those defects
- `compare_candidates` remains unimplemented in the registry on production (still true)

---

## Tests

All run locally; **no production mutation**.

| Suite | Result | Notes |
|---|---|---|
| `test_candidate_cv_facts` | PASS | |
| `test_candidate_cv_evidence` | PASS | materialization now works with restored finalization |
| `test_candidate_ranking` | PASS | 30 tests |
| `test_candidate_knowledge_phase0_contracts` | PASS | updated for reconciled contracts; historical drift preserved |
| Combined battery above | **70/70 OK** | log: `diffs/unittest-full-battery.txt` |
| `smoke-test-cv-extraction-ocr.py` | 32/32 PASS | |
| `smoke-test-cv-docx.py` | 25/25 PASS | |
| `smoke-test-toolcall-orchestrator.py` | PASS | |
| `smoke-test-prehire-registry-parity.py` | SKIP | needs psycopg2 / staging DB |
| `smoke-test-inbound-email.py` | SKIP/blocked | needs isolated test DB URL |
| `smoke-test-dashboard-data-hygiene.py` | blocked locally | `psycopg2` missing in local Python |
| Module compile of reconciled + deps | PASS | |

Phase 0 tests now:

- assert preimage local hashes/behavior under `ops/evidence/candidate-knowledge-runtime-reconciliation/local/`
- assert live checkout matches production for `cv_extraction` / `action_registry`
- assert `app.py` has production wiring **and** additive local surface marker

---

## Unresolved conflicts / residual gaps

1. **`app.py` reconciled ≠ production SHA** by design (local-only additive UI/debug endpoints).  
2. **Staging `internal_intake_readiness` not in reconciled checkout** (was staging-only; not in local preimage).  
3. **75 shared `app.py` function bodies** where local differed from production were resolved entirely in favor of production; if any local shared-body fix was intended as a forward-port, it was not cherry-picked (no clear keep-local signal found).  
4. **DB-backed inbound / registry parity smokes** not executed locally (no psycopg2 / test DB in this environment).  
5. **Production promotion of additive local endpoints** not reviewed for prod safety (debug intake routes, unified dashboard surfaces).  
6. Candidate Knowledge Phase 1 authority still not implemented (out of scope).

---

## Artifact hashes (reconciled checkout)

### Target files

- `cv_extraction.py` = `2859dc7e5e9598fc26e4561aaf5ecda8bcc26b0f62a30e04121ab18a4e18a229` (**production**)
- `action_registry.py` = `b7992797bd6db01dd2461c3803e80089e10de91248cddaeecf1f8a2cba8d2bfb` (**production**)
- `app.py` = `f2a3a8292b2d046e6a97989f6e86859b87d392664a8c7dc31ad35257db5b6a42` (**production + local-only graft**)

### Already-restored Phase 0 modules (unchanged)

- `candidate_cv_facts.py` = `4c01145e…`
- `candidate_cv_evidence.py` = `06de2da2…`
- `candidate_ranking.py` = `9b8a54f1…`

### Newly checked-in production dependency modules

See table above; copies also under `ops/evidence/candidate-knowledge-runtime-reconciliation/production-deps/`.

### Source commits

Working tree on branch `authority-cutover` (dirty; reconciliation not committed in this task). Recent `app.py` history tip at reconciliation time included interview/lifecycle commits (`d8d38ec`, `85b15cd`, …) but the deployed production `app.py` binary is ahead of that checkout lineage for facts/evidence/ranking/C2/C3.

---

## Does local source now faithfully represent production?

**For the Phase 0 stop-rule contracts: yes.**

- `cv_extraction.py` and `action_registry.py` are byte-identical to production.  
- `app.py` contains **all** production top-level symbols and the production facts/evidence/ranking/inbound-authority behavior, plus an explicitly marked local-only additive section.  
- No production behavior was deleted to keep local shared-body variants.

**Caveat:** reconciled `app.py` is a faithful production **superset**, not a byte clone.

---

## Production promotion plan (do not execute here)

### Scope if later promoted

1. **No-op on production today:** `cv_extraction.py`, `action_registry.py`, and the nine dependency modules already match production hashes.  
2. **Decision required for `app.py`:** either  
   - promote **exact production** (drop local additives), or  
   - promote **reconciled supersets** after owner review of additive dashboard/debug endpoints.

### Required before any promote

- Staging canary with DB-backed suites: inbound email smoke, prehire registry parity, continuous/debug intake worker, dashboard hygiene.  
- Confirm production flags unchanged (`WATHEFNI_*` ranking replay mode, OCR flags, inbound freeze posture).  
- Migration requirements: **none new** for Candidate Knowledge; `cv_extraction_finalizations` already exists in production schema manifest.  
- Rollback artifacts: keep preimage files under `ops/evidence/candidate-knowledge-runtime-reconciliation/local/` and current production copies under `.../production/`.  
- Diff review sign-off on `diffs/app.prod-vs-reconciled.diff` if additives are included.

### Promotion GO/NO-GO

**NO-GO for production promotion in this task.**

Reasons: deploy not authorized; additive `app.py` surface not production-safety reviewed; DB-backed inbound/registry canaries not run here.

---

## Phase 1 gate re-run

**GO to re-run the Phase 1 entry gate.**

Phase 0’s hard blocker (checked-in source disagreeing with deployed runtime for facts/evidence/ranking prerequisites) is cleared for the targeted contracts. Re-run should confirm:

- restored module SHAs still match
- `cv_extraction` / `action_registry` still match production
- `app.py` still contains production wiring (and document additive overlay)
- Phase 0 contract tests still pass

Do **not** implement `CandidateKnowledgeAuthority` until that re-run explicitly passes and Phase 1 work is authorized.

---

## Stop

Stopped after this report. No Candidate Knowledge Phase 1 implementation. No production deploy. No Voyage indexing. No backfill. No Role Profiles.
