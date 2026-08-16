# Ranking Consistency Audit — Matching, Eligible & Leaderboard

**Date:** 2026-07-30  
**Scope:** Ranking follow-up only (audit; **no implement, no deploy**)  
**Tenant proof:** `WATHEFNI` production  
**Verdict:** **FAIL** vs a single consistent matching / eligible / ranked / opened-Candidates contract  

Jobs / Candidates / Assessments: **not touched**. No visual redesign.

Evidence: `ops/evidence/ranking-consistency-audit-20260730/live-proof.json`  
Prior pointer: `ops/evidence/interviews-consistency-audit-20260730/FOLLOWUP_RANKING.md`

---

## 1. Page purpose (as producted today)

Ranking is an **advisory, job-scoped review-order surface**: “who should HR review first” for **one exact job**, with evidence and next-step chrome. It does **not** mutate lifecycle stage.

| Axis | Finding |
|---|---|
| Purpose | Advisory soft-rank of applications for one job |
| Unit of ranking | **Application** (`app_key`) — not person. Same person can appear once per application / job |
| Job binding | Exact `position_code` (plus title-with-spaces OR) |
| Product language | Copy says “matching candidates” while authority is **applications** |

Authority module: `wathefni-orchestrator/candidate_ranking.py` (pool, eligibility, soft score, run persistence).  
Dashboard: `apps/wathefni-dashboard/src/pages/RankingPage.tsx`.  
Route: `GET /dashboard/prehire/rank` (`app.py`).

---

## 2. Exact current authorities

### A. Matching pool → header `total_matching`

| Layer | Location |
|---|---|
| Loader | `candidate_ranking.load_job_application_pool` (~1182–1329); full scan `load_complete_job_pool` (~1332–1351) |
| Persist | `ranking_runs.pool_total` |
| API | `to_legacy_rank_candidates_shape`: `total_matching = pool_total` (~3398–3400) |
| UI | `RankingPage` description: “top N of **M matching** candidates” (~40–46) |

**Predicate (SQL sketch):**

```sql
FROM applications a
WHERE a.company_code = :company
  AND (upper(a.position_code)=:POS OR upper(coalesce(a.position_title,''))=:POS_SPACES)
  AND production_application_predicate(a)   -- production + ¬needs_role/import_* + test denylist
  AND a.status NOT IN ('hired','rejected','withdrawn')  -- include_terminal=false
-- NO reviewable / CV gate
-- NO exclusion of status='archived'
-- NO assignment / visibility SQL
```

`_reviewable_predicate` is defined (~1175–1179) but **unused** in the pool loader.

### B. Eligible count → `eligible_count` (unused in UI)

| Layer | Location |
|---|---|
| Compute | `rank_job_applications`: `sum(bucket == "eligible")` (~3044) |
| Persist | `ranking_runs.eligible_count` |
| API | Returned in legacy shape (~3403) |
| UI | **Never read** — `RankingResponse` (`types.ts` ~1347–1364) has **no** `eligible_count`; `RankingPage` never references it |

**Eligibility:** `evaluate_application_eligibility` (~1479–1542)

- Default evidence policy: **CV required**, assessment **unused** (`DEFAULT_EVIDENCE_POLICY` ~122–133).
- Hard criteria → buckets: `eligible` | `requirement_not_met` | `insufficient_information`.
- No hard criteria + evidence complete → `not_applicable` (advisory still ranks).
- Missing required CV → usually `insufficient_information`.

**Counter gap:** `not_met_count` / `unknown_count` cover `requirement_not_met` / `insufficient_information` only. **`not_applicable` is omitted** → `eligible + not_met + unknown` need not equal `pool_total`.

### C. Soft-front / rankable (no dedicated badge)

Sort (~3014–3026): prefer  
`eligibility_bucket ∈ {eligible, not_applicable}` ∧ `required_evidence_complete`,  
then `-advisory_score`, then `pool_ordinal`.  
**Never drops** rows from the pool.

`soft_rank` assigned only when `required_evidence_complete`; else `null` (~3031–3037).

So **eligible_count ≠ soft-front set** (soft-front includes `not_applicable`).

### D. Leaderboard rows (shown cards)

| Layer | Behavior |
|---|---|
| Order | Full ordered pool |
| Slice | `items[:top_n]`; dashboard `getRanking` hard-codes **`top_n=10`** |
| UI | Maps `ranking.candidates`; copy uses `total_matching` vs `candidates.length` |

Rows are **not** “eligible only”. After soft-front, remaining slots can be `requirement_not_met` / `insufficient_information`.

### E. Filters / navigation

| Control | Behavior |
|---|---|
| Job select | Required; empty → `job_required` / empty UI |
| Run / Re-rank | `mode=current` load vs `force=true` |
| `cohort_key: ranking:POS` | URL/nav only — **no** Candidates list predicate for it |
| Open row | Builds thin `ApplicationSummary` and opens candidate drawer — **not** “open Candidates filtered to ranking-eligible” |

### F. Related surfaces (not Ranking chrome)

| Surface | Relation |
|---|---|
| Jobs / Overview `active_pipeline` | reviewable (prod+CV) ∧ ¬{hired,rejected,withdrawn,**archived**} |
| Reports `_ranking_summary` | Uses run `pool_total` / `eligible_count` — closer to dual truth than Ranking UI |
| Overview Ranking destination | Opens Ranking page only; **no shared count** |

---

## 3. Populations (must stay separate)

| Population | Definition | In header “matching”? | In top-N cards? |
|---|---|---|---|
| **Matching** | Job-scoped production non-terminal apps (A) | Yes (`total_matching`) | Source set |
| **Eligible** | Hard bucket `eligible` only | No (field unused) | Preferentially first |
| **Rankable / soft-front** | `{eligible,not_applicable}` ∧ complete required evidence | No dedicated count | Preferentially first; get `soft_rank` |
| **In-pool demoted** | `requirement_not_met`, `insufficient_information`, CK held/restricted overlay | Yes | After soft-front |
| **Out of pool** | hired / rejected / withdrawn; needs_role / import_*; test; non-production | No | No |
| **Archived** | status=`archived` | **Still in Ranking matching** (code) | Possible |
| **No usable CV** | Still in matching; CV-required policy demotes eligibility / score | Yes | Usually demoted |

---

## 4. Scope matrix (tenant / role / visibility / CV / lifecycle)

| Axis | Matching header | Eligible | Shown rows | Candidates / Jobs same job |
|---|---|---|---|---|
| Tenant | `company_code` | same | same | same |
| Auth | `prehire` dashboard context | — | — | + visibility plan |
| Assignment visibility | **None** (company-wide) | — | — | Detail assignment SQL |
| CV gate | **None** | Soft/eligibility via policy (default required) | Score may hide | Default reviewable = prod+CV |
| Terminal | ¬ hired/rejected/withdrawn | subset | subset | Also ¬ **archived** (`active_pipeline`) |
| Held / talent-pool statuses | Excluded via production predicate | — | — | Unified Candidates held surfaces |

**FAIL** vs “counts and displayed rows use the same CV and lifecycle scope as opened Candidates / Jobs pipeline.”

---

## 5. Assessments (locked CV-first rule)

**Product rule in code (preserved):** Ranking is primarily CV-based; assessments are **optional additional evidence only when explicitly approved**.

| Gate | Behavior |
|---|---|
| Default policy | `assessment: unused` (~122–133) |
| Module off or no selection | `effective_assessment_mode` → `unused` (~553–577) |
| Explicit selection required | `ASSESSMENT_SELECTION_REQUIRED_KEYS` (~136–144) before assessment can change score/order |
| Soft contribution | Only if mode≠unused ∧ selection ∧ matching attempt ∧ completed ∧ percent ∧ same position |

**Structural gap:** `assessment_pool_lateral_sql` (~601–671) implements policy-matching attempt join but is **never called** (definition only). Pool still joins **latest any attempt**; soft scoring then filters with `assessment_attempt_matches_selection`. A newer unrelated attempt can hide an older matching completed attempt.

**Live:** default assessment mode = `unused` — **PASS** for the locked CV-first rule on soft scoring. Lateral unwired — **FAIL** for pool/selection consistency if assessment is later approved.

---

## 6. Edge-case audit

| Case | Behavior | Live WATHEFNI |
|---|---|---|
| **No job** | Empty UI / `job_required` | — |
| **No current run** | `needs_run`; header can show 0 until Run | observed for empty jobs |
| **Hired / rejected / withdrawn** | Out of matching pool | none in positive pools |
| **Archived** | **In** Ranking matching (code); **out** of Jobs `active_pipeline` | 0 archived live (latent code FAIL) |
| **Restricted / held (CK)** | May stay in SQL pool; overlay demotes + voids score | not sampled as separate rows |
| **Missing CV** | In matching; usually incomplete / insufficient | **FULLSTACK_DEVELOPER**: pool includes `awaiting_cv` |
| **Failed extraction / low confidence** | Readiness / confidence demote soft-front; still in matching | FINANCE / FULLSTACK → `insufficient_information` |
| **Low-confidence classification** | Soft confidence; may still show if otherwise complete | latent |
| **Multiple applications** | One row per `app_key` | 0 multi-person in current positive pools |
| **Draft/paused job** | `load_job` does not gate job status | latent |

---

## 7. Live proof (WATHEFNI)

| Job | Matching (`pool_total`) | Eligible | Jobs `active_pipeline` | Item buckets | Result |
|---|---:|---:|---:|---|---|
| `FULLSTACK_DEVELOPER` | **2** | **0** | **1** | insufficient_information×2 (`screening_complete` + `awaiting_cv`) | **FAIL** header≠eligible; pool≠Jobs (CV) |
| `HR` | **2** | **0** | 2 | not_applicable×2 | **FAIL** header≠eligible; counters omit NA |
| `ACCOUNTING` | 1 | 0 | 1 | not_applicable×1 | **FAIL** counters omit NA |
| `ACCOUNTING_EXCEL` | 1 | 0 | 1 | not_applicable×1 | **FAIL** |
| `FINANCE` | 1 | 0 | 1 | insufficient_information×1 | **FAIL** header≠eligible |
| `SOCIAL_MEDIA_MANAGER` | 1 | 0 | 1 | not_applicable×1 | **FAIL** |

All current positive runs: **eligible_count = 0** while header can still say “N matching” and show up to N cards.

---

## 8. Root cause

1. **Primary:** Three populations presented as one — **matching pool** (header), **eligible** (persisted, unused), **top-N of sorted full pool** (cards) — without shared naming or filters.
2. **Secondary:** Ranking matching ignores CV + archived rules used by Jobs/Candidates `active_pipeline`, and ignores assignment visibility.
3. **Tertiary:** `not_applicable` participates in soft-front but is omitted from run counters; UI never surfaces eligibility.
4. **Quaternary (assessment):** Soft path correctly defaults unused, but pool SQL does not use the selection lateral — latent inconsistency when assessment evidence is approved.

---

## 9. Exact files

| Area | Path |
|---|---|
| Pool / eligibility / soft rank / legacy shape | `wathefni-orchestrator/candidate_ranking.py` |
| Presentation / score visibility | `wathefni-orchestrator/ranking_result_presentation.py` |
| CK held/restricted overlay | `wathefni-orchestrator/ranking_evidence_adapter.py` (+ live registration) |
| Route | `wathefni-orchestrator/app.py` (`/dashboard/prehire/rank`, evidence-policy routes) |
| Jobs comparison predicate | `wathefni-orchestrator/jobs_queue_contract.py` |
| CV readiness | `wathefni-orchestrator/candidate_cv_evidence.py` |
| Reports summary | `wathefni-orchestrator/reports_v1.py` |
| UI header / cards | `apps/wathefni-dashboard/src/pages/RankingPage.tsx` |
| Score chrome | `apps/wathefni-dashboard/src/lib/rankingPresentation.ts` |
| Types omit `eligible_count` | `apps/wathefni-dashboard/src/types.ts` |
| Client `top_n=10` | `apps/wathefni-dashboard/src/lib/api.ts` |
| Nav cohort (no list predicate) | `apps/wathefni-dashboard/src/App.tsx` |
| Open-row thin application | `apps/wathefni-dashboard/src/pages/shared/format.ts` |

---

## 10. Proposed Ranking contract (for approval — do not implement yet)

Named scopes — **do not mix** matching, eligible, and top-N on the same badge/copy unless labeled.

| Axis ID | Meaning | Unit | Predicate sketch | UI ownership |
|---|---|---|---|---|
| `ranking.pool.matching` | Job application pool for Ranking | applications | production ∧ job match ∧ ¬{hired,rejected,withdrawn} **[+ decide archived, CV, visibility]** | Header “matching” **only** if this is intentional |
| `ranking.pool.eligible` | Hard-eligible only | applications | matching ∧ `eligibility_bucket=eligible` | Eligible badge / filter |
| `ranking.pool.rankable` | Soft-front | applications | matching ∧ bucket∈{eligible,not_applicable} ∧ required evidence complete | Soft-rank denominator |
| `ranking.run.top_n` | Leaderboard slice | run items | ordered rankable then others; `LIMIT N` | Cards; copy must say “top N of matching” **or** “of rankable” consistently |
| `ranking.evidence.cv` | Default required CV readiness | — | CV-first components | Score |
| `ranking.evidence.assessment` | Optional | — | module on ∧ policy≠unused ∧ complete selection ∧ wired attempt SQL | Assessment component only |
| `ranking.scope.visibility` | Decide company-wide vs assignment | — | Currently company-wide | Align with Candidates or document exception |

**Hard rules for a later implement:**

1. One named axis per badge / copy / opened list — no silent cross-fallback.  
2. Header and `eligible_count` must not be confused; counters must account for `not_applicable` or rename axes.  
3. Assessment never changes order/score without `ranking.evidence.assessment`; wire or delete `assessment_pool_lateral_sql`.  
4. Decide archived + CV + visibility once vs Jobs/Candidates, or document Ranking-exception explicitly.  
5. Preserve: Ranking is primarily CV-based; assessments optional only when explicitly approved for the job.

### Out of scope for this contract

UI redesign, changing soft-score formulas, inventing new lifecycle stages, Jobs/Candidates/Assessments (already shipped).

---

## 11. PASS / FAIL

| Check | Result |
|---|---|
| Header matching ≡ eligible | **FAIL** (e.g. FULLSTACK 2 vs 0; all positive runs eligible=0) |
| Header matching ≡ leaderboard population (not just top-N of pool) | **FAIL** (top-N of full sorted pool; not eligible-filtered) |
| Matching ≡ Jobs/Candidates active pipeline (CV + archived + scope) | **FAIL** (FULLSTACK 2 vs active_pipeline 1; no visibility SQL; archived not excluded in code) |
| Counters sum to pool | **FAIL** when `not_applicable` present (HR, ACCOUNTING, …) |
| CV-first assessment default | **PASS** (`assessment: unused`) |
| Assessment selection lateral wired into pool | **FAIL** (defined, unused) |
| Hired/rejected/withdrawn excluded from matching | **PASS** |
| Automated contract locking axes | **FAIL** (missing) |
| Implementation / deploy | **NOT STARTED** (audit only) |

---

## 12. Approval gate

Do **not** implement or deploy Ranking count fixes until this contract is approved. After approval, implementation should:

1. Split matching / eligible / rankable / top-N axes (no cross-fallback).  
2. Align Ranking pool scope with the approved CV / archived / visibility decision.  
3. Surface or stop persisting unused `eligible_count` without UI.  
4. Fix counter accounting for `not_applicable`.  
5. Wire or remove `assessment_pool_lateral_sql`; keep assessment fail-closed without explicit approval.  
6. Add regression tests + WATHEFNI live matrix (FULLSTACK matching≠pipeline; header≠eligible).

**Out of scope:** UI redesign, Jobs/Candidates/Assessments product surfaces beyond shared predicates Ranking may adopt.
