# Pre-Hiring Talent Pool Classification — Local Remediation

**Status:** Contained **local implementation + qualification complete**  
**Date:** 2026-07-25  
**Deploy:** **not performed**  
**Production classification workers:** **not enabled**  
**External tenants:** **not enabled**  
**Role Profiles / ranking / Person Registry / outreach / Job assignment / lifecycle:** **not implemented**

**Foundation (frozen):** Unified Candidates production canary  
- master Unified Candidates OFF  
- tenant override `WATHEFNI` only  
- classification flags remain independent and OFF for production

---

## Verdict

| Gate | Result |
| --- | --- |
| Contained local classification authority | **GO_LOCAL** |
| Staging deploy / production workers / external tenants | **NO-GO** |
| Role Profile ranking / Job assignment / outreach | **NO-GO** |

Local matrix: **60/60 PASS** (`ops/screenshots/talent-pool-classification/qualification.json`)  
Unit tests: **13/13 PASS** (`test_talent_pool_classification.py`)  
Unified Candidates units: **9/9 PASS** (unchanged authority)  
Dashboard Vitest: ClassificationFilters + CandidatesTable **8/8 PASS**

---

## 1. Taxonomy schema and sample hierarchy

Pack: `wathefni-orchestrator/talent_pool_taxonomy_v1.json`  
Version: `taxonomy_v1.0.0` (immutable release)

Dimensions (stable IDs + EN/AR labels + aliases):

| Type | Examples |
| --- | --- |
| career_function | `fn.technology`, `fn.hr`, `fn.finance`, `fn.engineering`, `fn.sales_marketing` |
| likely_role | `role.software_engineer`, `role.hr_generalist`, `role.accountant`, … |
| skill | `skill.python`, `skill.sql`, `skill.excel`, … |
| industry | `ind.banking`, `ind.oil_gas`, `ind.retail` |
| seniority / experience_band | `sen.junior`…`sen.senior`, `exp.0_1`…`exp.10_plus` |
| education_field / certification / language | CS, Accounting, PMP, AWS, English, Arabic |

Tenant extensions: `taxonomy_tenant_nodes` with namespaced IDs `tenant.{COMPANY}.*` and optional `maps_to_canonical_node_id`. Tenants cannot edit global pack or other tenants.

Sample hierarchy snapshot: `ops/screenshots/talent-pool-classification/sample-hierarchy.json`

---

## 2. Classification input contract

`talent_pool_classification.build_input_bundle(...)` accepts only stored artifacts:

- normalized CV text  
- `application-cv-facts-v1` / candidate profile facts  
- HR-confirmed effective facts  
- employment/education evidence inside facts  
- document + extraction version ids  
- completeness summary  
- embedding presence flag (retrieval assist only; not required)

**Never sets `ocr_rerun=true`.** Refusal if OCR rerun is requested. Taxonomy/classifier/reclassify paths use stored text only.

---

## 3. Confidence and refusal contract

| Internal score | UI band | Promotion |
| --- | --- | --- |
| ≥ 0.78 | **High** | Default filters + optional compact chip |
| ≥ 0.55 | **Medium** | Only when HR opts into “Include Medium AI” |
| < 0.55 | **Low** | Not stored as active suggestions |

Refusal / `unclassified` when evidence insufficient (identity-only / empty text without role cues / completeness too low). Missing extraction is never “candidate lacks X.”

Every active suggestion requires non-empty `evidence[]` (DB CHECK + classifier gate).

---

## 4. Suggestion and HR-confirmed authority

| Layer | Storage | Mutability |
| --- | --- | --- |
| AI runs | `candidate_classification_runs` | Immutable; reclassify = new run; prior suggestions → `stale` |
| AI suggestions | `candidate_classification_suggestions` | Evidence-backed; High/Medium only |
| HR events | `candidate_classification_review_events` | Append-only confirm/reject/add/correct/supersede |

Effective projection (`effective_classification`) keeps HR confirmed above AI; rejected nodes stay in audit and are excluded from AI display; HR confirmations survive reclassification.

No hiring score / Role Profile score / Job assignment fields are populated (`null`).

---

## 5. Queue and idempotency model

- Job type: `talent_pool_classify_v1`  
- Table: `talent_pool_classification_jobs` (queued / completed_manual / dead_letter capable)  
- Idempotency key = hash(company, app_key, document_version, extraction_version, taxonomy_version, classifier_version, input_bundle_hash)  
- Manual/local execution path only (`FEATURE_WORKERS` must stay OFF; `assert_workers_disabled_for_local`)  
- Classification failure leaves Talent Pool/search intact (proven in local matrix)

---

## 6. Unified Candidates UX

Preserved clean table — **no permanent columns** for career/role/skill/industry/seniority/confidence.

Added:

- `ClassificationFilterBar` (authority disclosure + Medium opt-in)  
- optional one `ClassificationCompactChip` (`Technology · Software Engineer`) for High + evidence + not rejected  
- `CandidateClassificationSection` on governed profile (confirmed / AI / rejected / versions / confirm-reject actions)  
- search reason helpers: confirmed vs AI vs evidence (no silent blend) via `unified_candidates.search_match_reasons(..., classification_effective=...)`

Feature fetch is **decoupled** from Unified Candidates (`getTalentPoolClassificationFeature`).

---

## 7. Changed files

### Backend
- `wathefni-orchestrator/talent_pool_classification.py` (new)  
- `wathefni-orchestrator/talent_pool_classification_routes.py` (new)  
- `wathefni-orchestrator/talent_pool_taxonomy_v1.json` (new)  
- `wathefni-orchestrator/test_talent_pool_classification.py` (new)  
- `wathefni-orchestrator/local-qualify-talent-pool-classification.py` (new)  
- `wathefni-orchestrator/unified_candidates.py` (additive classification match-reason hooks only)

### Frontend
- `apps/wathefni-dashboard/src/components/candidates/ClassificationFilters.tsx`  
- `apps/wathefni-dashboard/src/components/candidates/ClassificationFilters.test.tsx`  
- `apps/wathefni-dashboard/src/components/candidates/CandidateClassificationSection.tsx`  
- `apps/wathefni-dashboard/src/components/candidates/CandidatesTable.tsx` (chip only)  
- `apps/wathefni-dashboard/src/components/candidates/CandidateGovernedProfile.tsx`  
- `apps/wathefni-dashboard/src/App.tsx` (flag fetch + filter bar + profile enablement)  
- `apps/wathefni-dashboard/src/lib/api.ts`  
- `apps/wathefni-dashboard/src/types.ts`

### Evidence / docs
- `ops/screenshots/talent-pool-classification/*`  
- `ops/PREHIRING_TALENT_POOL_CLASSIFICATION_LOCAL_REMEDIATION.md` (this file)

---

## 8. Screenshots

Index: `ops/screenshots/talent-pool-classification/INDEX.md`

| Shot | Path |
| --- | --- |
| Table + chip | `ops/screenshots/talent-pool-classification/candidates-table-with-chip.png` |
| Profile classification | `ops/screenshots/talent-pool-classification/classification-profile.png` |
| Filters disclosure | `ops/screenshots/talent-pool-classification/classification-filters.png` |

---

## 9. Complete matrix

From `local-qualify-talent-pool-classification.py` (**60/60**):

- clear software/IT, HR, finance, engineering, sales/marketing  
- multidisciplinary + career-change multi-label  
- low-information → unclassified  
- Arabic / English / bilingual  
- skills in raw text with empty structured facts  
- conflicting CV versions differ  
- HR confirm + reject survive re-projection  
- taxonomy/classifier version change cache keys  
- tenant extension namespace + usable labels  
- failed classification keeps search  
- cross-tenant feature isolation  
- compact chip High-only; Medium no chip  
- no hiring/Job/Role Profile outputs  
- workers/master default OFF; decoupled from Unified Candidates  
- zero local residue (no DB writes in matrix)

Unit coverage: taxonomy bilingual, refusal, multilabel evidence, HR precedence, search reason separation, idempotency, tenant namespace enforcement.

---

## 10. Frozen regression proof

| Pack | Result |
| --- | --- |
| `test_unified_candidates.py` | PASS (9) |
| `test_talent_pool_classification.py` | PASS (13) |
| Dashboard ClassificationFilters + CandidatesTable Vitest | PASS (8) |
| `smoke-test-jobs-phase2-stage-a-unit.py` | PASS |
| `smoke-test-notification-semantics.py` | FAIL (pre-existing / unrelated to classification; no classification imports) |

No lifecycle, Ranking, Offers, Interviews, outreach, or `intake_admit` code paths were modified for mutation behavior.

---

## 11. Feature flags (local posture)

| Flag | Local qualify | Production posture |
| --- | --- | --- |
| `WATHEFNI_TALENT_POOL_CLASSIFICATION` (master) | off | **OFF** |
| `WATHEFNI_TALENT_POOL_CLASSIFICATION_TENANTS` | `LOCALTPC` in tests | empty / not `WATHEFNI` for classification |
| `WATHEFNI_TALENT_POOL_CLASSIFICATION_SCHEMA` | on in tests | OFF until staging |
| `WATHEFNI_TALENT_POOL_CLASSIFICATION_MANUAL` | on in tests | OFF until staging |
| `WATHEFNI_TALENT_POOL_CLASSIFICATION_WORKERS` | **off** | **OFF** |
| `WATHEFNI_TALENT_POOL_CLASSIFICATION_UI` | on in tests | OFF until staging |

Not coupled to Unified Candidates enablement.

---

## 12. Residual risks

1. Deterministic classifier v1 is alias/evidence based — multilingual recall and seniority/experience-band precision will need richer exemplars before staging canary.  
2. LLM classifier provider not wired (by design for local); staging should pin model/prompt versions behind `classifier_version`.  
3. Application-list API still needs server-side classification filter query wiring for saved-view persistence at scale (UI filter bar is present; backend filter helper exists).  
4. Mount of `talent_pool_classification_routes` into staging `app.py` is deferred to guarded staging sequence.  
5. Notification-semantics smoke failure is unrelated and should be tracked separately.

---

## 13. Guarded staging sequence (do not start yet)

1. Owner approves taxonomy pack v1 bilingual review.  
2. Contained staging deploy of classification modules + schema only; flags OFF globally.  
3. Enable SCHEMA+MANUAL+UI for staging `WATHEFNI` only; workers remain OFF.  
4. Seed taxonomy; run manual classify on synthetic fixtures; prove non-mutation + residue cleanup.  
5. Qualify search/filter/profile/chip against staging Unified Candidates (already ON for WATHEFNI).  
6. Only later: optional worker canary with quotas — separate approval.  
7. Production classification remains OFF (including internal WATHEFNI) until explicit canary plan.

---

## Stop line

Local implementation and qualification are complete.  
**Do not deploy. Do not enable production workers. Do not enable external tenants. Do not begin Role Profiles.**
