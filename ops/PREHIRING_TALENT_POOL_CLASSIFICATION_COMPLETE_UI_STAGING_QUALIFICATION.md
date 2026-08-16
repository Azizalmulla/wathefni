# Pre-Hiring Talent Pool Classification — Complete UI Staging Qualification

**Date:** 2026-07-26 (UTC+3)  
**Scope:** Contained local implementation + staging qualification of the complete  
Talent Pool Classification read/interaction experience  
**Production deploy:** **none**  
**External tenants:** **not enabled**  
**Persistent classification workers:** **off**  
**Classifier logic:** **unchanged** (`classifier.deterministic_v1.2`)  
**Role Profiles / ranking / Person Registry / outreach / Job assignment / lifecycle:** **not started**

## Executive verdict

**Staging classification UI contract: PASS (47/47 API + browser screenshots).**  
**Production dashboard promotion / final internal canary: NO-GO.**

The generic taxonomy-driven classification read model, server-correct Candidates
filtering/pagination, taxonomy-driven dashboard filters, versioned saved views,
multi-run profile history, and HR confirm/reject/add/correct actions are
implemented and staging-qualified for internal `WATHEFNI` only.

Production is untouched:

- `/var/www/wathefni-dashboard` SHA still  
  `c7b8b954a48f14c2c3c03d4c7e330772259a4527a53fe6c612524868dbc91e02`
- production classification flags fully OFF
- no production dashboard promote
- no external tenant enablement

Frozen Unified Candidates staging qualify remains **fixture-blocked** by
pre-existing staging schema drift in its seed harness (`applications.position_code`
NOT NULL; `semantic_documents.semantic_id` NOT NULL). That failure is not caused by
classification filter/projection code and does not invalidate the classification
UI proofs, but it blocks a fully green “promote production dashboard” gate.

---

## 1. Architecture — generic classification read model

Classification is a **sidecar read model**, not columns on canonical
`candidates` / `applications`.

| Layer | Authority |
| --- | --- |
| Taxonomy pack `taxonomy_v1.1.0` | Stable `node_id` + `node_type` metadata |
| Filter dimensions | Mapped via `DIMENSION_TYPES` (display labels never filter authority) |
| Suggestions | Immutable classifier runs + current/stale suggestion rows |
| HR authority | Append-only `candidate_classification_review_events` |
| Candidates list | Bulk sidecar load → compact projection only |
| Filters | Single composable `EXISTS` SQL predicate (`classification_filter_sql`) |

Initial dimensions (product name → taxonomy `node_type`):

| Product dimension | Taxonomy `node_type` |
| --- | --- |
| career area | `career_function` |
| likely role | `likely_role` |
| skill | `skill` |
| industry | `industry` |
| seniority | `seniority` |
| experience band | `experience_band` |

AND/OR contract:

- multiple node IDs **within one dimension**: **OR**
- separate dimension groups: **AND**
- authority/confidence/state apply to the matched evidence pool
- list filters are **current-only** by default
- historical/stale inspection is profile-only (paginated runs)

Chip eligibility (at most one compact chip):

- current
- High confidence
- evidence-backed
- not HR-rejected
- not contradicted by HR-confirmed current label

---

## 2. API / query contract

### Candidates list (`GET /dashboard/prehire/applications`)

Additive query params (stable IDs, not English labels):

- `classification_career_area`
- `classification_likely_role`
- `classification_skill`
- `classification_industry`
- `classification_seniority`
- `classification_experience_band`
- `classification_node_ids`
- `classification_authority`  
  (`confirmed_only` | `ai_suggested` | `confirmed_or_high_ai` | `either`)
- `classification_confidence`  
  (`High` | `Medium` | `Needs review` | `Unclassified`)
- `classification_include_medium_ai`

Additive row projection (sidecars only):

- `classification_chip`
- `classification_chip_confirmed`
- `classification_state`
- `classification_authority_summary`
- `classification_node_ids`

Pagination/count run **before** row materialization; filters are SQL `EXISTS`
predicates over sidecars (no client-side page filtering, no N+1).

Search continues when classification is absent or projection fails (wrapped).

### Taxonomy (`GET /dashboard/prehire/classification/taxonomy`)

Returns taxonomy version, bilingual nodes, tenant extension nodes (tenant-scoped),
and `dimensions[]` for dashboard selectors.

### Profile (`GET /dashboard/prehire/applications/{app_key}/classification`)

Additive fields:

- current effective confirmed / AI suggested / rejected
- evidence, confidence/state bands (no decimals in UI)
- taxonomy + classifier versions
- `runs[]` with `currency` = `current` | `stale` (bounded pagination)
- append-only `history[]`
- document/extraction version ids per run
- `actions`: confirm, reject, add, correct
- `hiring_score` / `role_profile_score` / `job_assignment` always `null`

### Review (`POST .../classification/review`)

Requires `confirm: true` (or preview). Correct requires `previous_node_id` and is
a superseding append-only event. Add creates HR-confirmed authority without
pretending classifier authorship. Classifier runs are never mutated.

---

## 3. Taxonomy-driven dashboard filters

Rendered from taxonomy metadata (not hardcoded lists in the bundle):

- searchable selectors per dimension
- bilingual labels
- broad vs specific markers
- selected chips removable
- authority + confidence/state + Include Medium AI
- **fully hidden when feature OFF**

Saved views use versioned payload `classification-filters-v1` nested under
`filters.classification`. Old views without classification continue to work.
Missing/deprecated nodes are disclosed and do not silently remap.

---

## 4. Changed-file allowlist (this phase)

Orchestrator:

- `wathefni-orchestrator/talent_pool_classification.py` (read model; classifier scoring untouched)
- `wathefni-orchestrator/talent_pool_classification_routes.py`
- `wathefni-orchestrator/unified_candidates.py` (saved-view classification normalize only)
- `wathefni-orchestrator/ops/patch-staging-app-talent-pool-classification-complete-ui.py`
- `wathefni-orchestrator/ops/local-qualify-talent-pool-classification-complete-ui.py`
- surgical staging `app.py` patch markers:  
  `TALENT_POOL_CLASSIFICATION_COMPLETE_UI_PATCH`

Dashboard:

- `apps/wathefni-dashboard/src/components/candidates/ClassificationFilters.tsx`
- `apps/wathefni-dashboard/src/components/candidates/CandidateClassificationSection.tsx`
- `apps/wathefni-dashboard/src/components/candidates/CandidateGovernedProfile.tsx`
- `apps/wathefni-dashboard/src/components/candidates/ClassificationFilters.test.tsx`
- `apps/wathefni-dashboard/src/lib/api.ts`
- `apps/wathefni-dashboard/src/types.ts`
- `apps/wathefni-dashboard/src/App.tsx`

Ops:

- `ops/deploy-talent-pool-classification-complete-ui-staging.sh`
- `ops/talent-pool-classification-complete-ui-staging-qualify.py`
- `ops/talent-pool-classification-complete-ui-staging-screenshots.py`
- `ops/run-talent-pool-classification-complete-ui-staging-regressions.py`

---

## 5. Artifact identities

| Item | Value |
| --- | --- |
| Source commit | `40a4e2621f4818bf7c0f6ce3642032297bfbe7b2` |
| Classifier | `classifier.deterministic_v1.2` |
| Classifier file SHA-256 | `4e091456d98f69b3dbf1537051d7de814db60238f22dd24ab97a4524665f3a30` |
| Taxonomy | `taxonomy_v1.1.0` |
| Orchestrator allowlist artifact SHA-256 | `bf5674acae8c47932185810a919142936fa10f14af6467f41b79c505ff7caca5` |
| Dashboard manifest SHA-256 | `ea282fce7c6c571843b1ff0691b4f09e677922af421a439642c3a499a9b1473f` |
| Dashboard main bundle | `dashboard-C0lgzkSg.js` / `997e5c18f70f346cc800bf3ac53b0ac59fefe346c46fc1f72de878fb2252d50f` |
| Staging evidence | `/opt/wathefni/staging/staging-evidence/talent-pool-classification-complete-ui/20260726T001509Z` |
| Staging backup / rollback | `/opt/wathefni/backups/staging-pre-tpc-complete-ui-20260726T001509Z` |
| Production dashboard SHA (unchanged) | `c7b8b954a48f14c2c3c03d4c7e330772259a4527a53fe6c612524868dbc91e02` |

Staging dashboard path only: `/opt/wathefni/staging/dashboard-dist`  
(**not** `/var/www/wathefni-dashboard`).

---

## 6. Local qualification

| Gate | Result |
| --- | --- |
| `test_talent_pool_classification.py` | PASS (18) |
| `ops/local-qualify-talent-pool-classification-complete-ui.py` | PASS |
| Dashboard ClassificationFilters + CandidatesTable tests | PASS (11) |
| Dashboard production build | PASS |

---

## 7. Staging API matrix (complete UI)

Script: `ops/talent-pool-classification-complete-ui-staging-qualify.py`  
Evidence: `ops/screenshots/talent-pool-classification-complete-ui-staging/complete-ui-qualification.json`

**47/47 PASS**, including:

- each taxonomy dimension catalog
- OR within dimension / AND across dimensions
- High / Medium / Needs review / Unclassified
- confirmed / suggested / either authority
- server pagination under classification filters
- chip eligibility (High only; Medium/Unclassified no chip)
- profile current + stale runs + history
- confirm (preview + confirm-required + append)
- reject / add / correct supersede
- saved-view versioning + deprecated-node disclosure
- feature OFF hide + allowlist isolation
- zero synthetic residue

---

## 8. Browser staging screenshots

Captured against staging `:8011` dashboard-dist via Playwright (not component-only).

Local copies: `ops/screenshots/talent-pool-classification-complete-ui-staging/`

| Screenshot | Proof |
| --- | --- |
| `01-table-chip.png` | Compact High advisory chip on Candidates rows |
| `02-filter-*.png` | Each dimension filter group rendered from taxonomy |
| `03-combined-filters.png` | Combined taxonomy filter application |
| `04-saved-view.png` | Classification-aware save-view controls |
| `05-profile-current.png` | Current suggestions + advisory copy + versions |
| `06-immutable-run-history.png` | Expandable immutable run history |
| `07-hr-confirm-dialog.png` | Explicit confirm dialog |
| `08-hr-confirm-done.png` | Confirm recorded |
| `09-hr-add-dialog.png` | Add confirmation dialog |
| `10-hr-reject-dialog.png` | Reject confirmation dialog |
| `11-feature-off.png` | Classification controls fully absent when OFF |

Browser checks: filter bar visible; all 6 dimensions present; profile section present;
feature-off hides bar; residue 0.

Correct was API-qualified as an explicit superseding event; browser covered
confirm/add/reject dialogs.

---

## 9. Frozen regressions (staging)

| Pack | Result | Notes |
| --- | --- | --- |
| Classification unit | PASS | v1.2 frozen |
| Candidates C0/C1 | **44/44 PASS** | |
| Candidates C2 | PASS | |
| Candidates C3 | PASS | |
| Optional-module boundary | **301/301 PASS** | `gates=301 failed=0` |
| Ranking R0–R3 | PASS | |
| Reports v1 | PASS | |
| Interviews | PASS | |
| Offers/Hiring | PASS | |
| Assessments on/off | PASS | |
| Assistant A0–A3 | **79/79 PASS** | required `WATHEFNI_EMBEDDING_MODEL=voyage-4-large` |
| Unified Candidates staging qualify | **FAIL / fixture-blocked** | seed harness outdated vs schema (`position_code`, `semantic_documents.semantic_id`) — not a classification projection defect |
| Dashboard / HR mobile dedicated packs | not re-executed as separate named packs in this runner; dashboard contract proven by build + browser shots against staging dist | |

Synthetic classification residue after cleanup: **0**.

---

## 10. Feature boundaries proven

Classification remained advisory. Staging runs proved:

- no OCR triggered
- no lifecycle mutation from classification run/review
- no Job assignment / `position_code` mutation from classification
- no intake_admit / shortlist / reject / interview / offer / hire / outreach side effects from classification actions
- workers never started

---

## 11. Residual risks

1. **Unified Candidates staging qualify harness drift** must be repaired before any
   production dashboard promote that claims a fully green UC pack.
2. Staging leave-state intentionally keeps classification UI ON for `WATHEFNI`
   only (workers OFF, master OFF). Production remains fully OFF.
3. Correct action is fully API-governed; browser screenshot coverage emphasized
   confirm/add/reject dialogs.
4. Large Talent Pool pagination was proven with synthetic fillers under
   Unclassified; extreme multi-tenant load was not a production canary.

---

## 12. Leave-state

**Staging**

- master OFF
- tenants=`WATHEFNI`
- schema ON, manual ON, UI ON
- workers OFF
- dashboard dist = complete UI artifact above

**Production**

- classification fully OFF
- dashboard SHA unchanged (`c7b8b954…`)
- no promote performed

---

## 13. GO / NO-GO

| Decision | Verdict |
| --- | --- |
| Staging complete classification UI qualification | **GO / PASS** |
| Production dashboard promotion | **NO-GO** |
| Final internal production canary | **NO-GO** |
| Enable external tenants | **NO-GO** |
| Begin Role Profiles | **NO-GO** |

**Stop after staging qualification. Do not deploy to production.**
