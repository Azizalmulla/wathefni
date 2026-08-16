# Overview Wave 4 — Ranking Truth

**Date:** 2026-07-28 (Asia/Kuwait)  
**Stamp:** `20260728T000054Z`  
**Host:** `root@76.13.63.68`  
**Scope:** Ranking authority, score reliability, latest-run loading, HR presentation  
**Not in this wave:** Overview counts/destinations, assessment cohorts, color redesign, unrelated pages

---

## Final verdict

**PASS — Wave 4**

Ranking now returns one coherent, database-backed decision contract. The CK reader `UndefinedFunction` (`uuid = text`) root cause is fixed with `ANY(%s::uuid[])`. Infrastructure CK failures fail soft (overlay inactive) instead of voiding advisory scores to `0/100`. Accounting Excel auto-loads its latest valid current run (`mode=current`) with score **69.5/100**, human-readable strengths/evidence, V2 facts (`facts_id` present), no raw JSON or internal error codes, and idempotent re-rank (`current_runs == 1`). Overview Wave 3 assessment primary remains **2 people / 3 apps**.

---

## Ranking decision contract

Authority: `ranking_result_presentation.build_ranking_decision` → `ranking_decision` on each candidate.

| Field | Meaning |
|---|---|
| `ranking_status` | Card/decision state (`ranked`, thin, blocked, unavailable, …) |
| `eligibility` | Bucket + human labels (`label`, `fit_code`, `fit_label`) |
| `advisory_score` | Numeric advisory score **or `null`** (never coerced to 0) |
| `score_state` | `{ show_numeric, label, reason }` — only show a number when `show_numeric` and value exist |
| `fit_summary` | Short human fit narrative aligned to score state |
| `strengths` | Top human-readable strengths |
| `gaps` | Key gaps |
| `missing_evidence` | Missing information (HR-safe labels only) |
| `component_scores` | V2 components; missing keys stay `null` (not 0) |
| `recommended_next_action` | Concise next step |
| `evidence_references` | Human evidence labels (not raw objects) |
| `run_freshness` | `current` / `stale` / `missing` |
| `app_key` / `application_stage` / `job` / `candidate_name` | Application- and job-specific clarity |

Legacy `candidate.score` is set to `null` when `show_numeric` is false so clients cannot `Math.round(null)` → `0`.

---

## CK reader root cause and correction

### Root cause

`ck_ranking_reader_failed:UndefinedFunction` came from Postgres:

```text
operator does not exist: uuid = text
… attempt_id = ANY(%s)
```

in `PostgresCandidateKnowledgeStore.list_assessment_scores` / `list_assessment_report_summaries` / interview feedback `ANY(%s)`.

The ranking reader overlay then **fail-closed**, putting `ck_ranking_reader_failed:UndefinedFunction` into missing/required bags and voiding an otherwise usable soft score. The UI treated a null/voided score as **0/100** while narrative could stay positive.

### Correction

1. **SQL:** `ANY(%s::uuid[])` in `candidate_knowledge_store.py`.
2. **Overlay:** governance `CandidateKnowledgeError` still fail-closed; infrastructure exceptions set `active: False`, log `ck_ranking_reader_infra_failed`, and leave soft scoring intact (`candidate_knowledge_live_registration.py`).
3. **Presentation / legacy shape:** strip platform codes from HR missing labels; human strengths/gaps/evidence; null score does not keep a contradictory positive-only story (`candidate_ranking.py`, `ranking_result_presentation.py`).
4. **Load path:** poisoned historical runs (CK infra codes in missing bags) auto force one recalculation on `mode=current|latest`.

Live contrast: old uncast query still raises `UndefinedFunction`; casted store reads succeed (`scores_rows: 1`).

---

## Score-state rules

| Condition | HR display |
|---|---|
| Valid advisory score + `show_numeric` | Show `N / 100` |
| `advisory_score` is `null` | **Score unavailable** (never `0`) |
| Incomplete / blocked / thin / stale / setup | Clear state label + reason; no invented number |
| Internal `ck_ranking_reader_failed` / `UndefinedFunction` | Platform logs only — not HR copy |
| Missing V2 component key | Omit row (do not render as 0) |

Frontend: `rankingScoreLabel` / `rankingDecisionFor` require `show_numeric && advisory_score != null`.

---

## Latest-run loading behavior

`GET /dashboard/prehire/rank`:

- `mode=current|latest` → load current valid run; **no new run** if one exists.
- No current run → `{ needs_run: true, candidates: [] }` with clear message (UI: **Run ranking**).
- Poisoned CK-infra historical run → one forced recalculation.
- `force=true` / Re-rank → recalculate; idempotent via `request_hash` / `is_current` (no duplicate current runs).
- Role/job pressure alone is never presented as a completed ranking result.

Dashboard: opening Ranking with a selected job auto-calls `loadCurrentRanking` (`mode=current`). Re-rank uses `force=true`.

---

## HR presentation before / after

| Before | After |
|---|---|
| `0/100` beside usable evidence when CK reader failed | Valid score when advisory exists (Accounting Excel **69.5/100**) |
| Raw evidence objects / field keys like `cv_education` | Labels: “CV skills”, “Education and certifications” |
| Internal codes in missing bags | Stripped from HR; logged for platform |
| Positive narrative + voided score | Decision fields agree; legacy score nulled when hidden |
| Manual Rank required even when current run exists | Auto-load latest valid run |
| Duplicate/confusing evidence blocks | Single decision surface: score, eligibility, fit, strengths, gaps, missing, evidence, next action |

Live Accounting Excel sample (`96597485758-WATHEFNI-ACCOUNTING_EXCEL`):

- Candidate: Hamad Almulla  
- Job: Accounting Excel (`ACCOUNTING_EXCEL`)  
- Stage: `screening_complete`  
- Status: `ranked` / Worth reviewing  
- Score: **69.5** (`show_numeric: true`)  
- Components: skills 22.5, experience 14.0, education 15.0, assessment `null` (not shown as 0), semantic 7.58  
- V2 facts: `facts_id=a263978a-7779-4f61-b1c5-133e2a1b4531`, CK overlay active  

---

## Production proof (`20260728T000054Z`)

Evidence: `/opt/wathefni/production-evidence/overview-wave4-ranking-truth/20260728T000054Z/`

| Assertion | Result |
|---|---|
| CK reader SQL OK (no UndefinedFunction) | **PASS** |
| Old uuid=text mismatch still reproducible | **PASS** (documents root cause) |
| Overlay uses V2 facts / does not void on infra | **PASS** (`facts_id` present, `active: true`) |
| Accounting Excel auto-load latest valid | **PASS** (`run_id=3db6d67a-…`, 1 candidate, 69.5) |
| Null never displayed as 0 | **PASS** |
| Score / narrative / eligibility / strengths / gaps / missing agree | **PASS** |
| No raw JSON or technical HR labels | **PASS** |
| Re-rank idempotent (`current_runs <= 1`, same run id) | **PASS** |
| EN + AR presentation attached | **PASS** (AR labels/summary) |
| Ranking RTL (`dir=rtl` when AR) | **PASS** |
| Overview assessment primary unchanged 2/3 | **PASS** |
| Dashboard asset | `dashboard-nFyK_VKW.js` |
| Health 200 before/after/rollback/restore | **PASS** |
| Post-restore autoload still 69.5 | **PASS** |

Files changed (orchestrator):

- `candidate_knowledge_store.py`
- `candidate_knowledge_live_registration.py`
- `candidate_ranking.py`
- `ranking_result_presentation.py`
- `app.py` (surgical `/dashboard/prehire/rank` only)

Dashboard:

- `src/lib/rankingPresentation.ts`, `src/lib/api.ts`, `src/types.ts`, Ranking UI in `src/App.tsx`

---

## Health / rollback / restore

| Step | Result |
|---|---|
| Health after orchestrator deploy | **200** |
| Rollback Wave 4 orchestrator modules + `app.py` | Health **200** |
| Restore Wave 4 orchestrator | Health **200**; Accounting Excel autoload **69.5** |
| Dashboard rollback → Wave 3 asset | `dashboard-Bg3l7rqq.js`; health **200** |
| Dashboard restore Wave 4 | `dashboard-nFyK_VKW.js`; health **200** |

Rollback artifacts under the stamp directory: `*.before` / `*.after`, `wathefni-dashboard.wave4-before|after`, `live-proof.json`, `post-restore-autoload.json`.

---

## Remaining limitations

- Canonical CV `version_id` may still be null for some apps while `facts_id` is present; Ranking uses available V2 effective facts.
- Assessment component stays `null` until assessment evidence exists for that application (correct; not rendered as 0).
- Terra/narrative prose may still mix EN fragments inside AR locale for some strengths; score/eligibility labels are localized.
- Force re-rank is idempotent on current marker/request hash; historical non-current runs may remain for audit.

---

## PASS / FAIL gates

| Gate | Result |
|---|---|
| Ranking decision contract present and coherent | **PASS** |
| CK reader UndefinedFunction fixed | **PASS** |
| Infra CK failure safely degraded (not silent 0/100) | **PASS** |
| Null never displays as 0 | **PASS** |
| Auto-load latest valid run (Accounting Excel) | **PASS** |
| Missing/stale/needs_run handled honestly | **PASS** |
| No raw JSON / technical HR labels | **PASS** |
| V2 CV facts used | **PASS** |
| Re-rank idempotent | **PASS** |
| Application/job/stage clarity | **PASS** |
| EN/AR + RTL | **PASS** |
| Overview counts/cohorts unchanged | **PASS** |
| Health 200 + rollback/restore | **PASS** |
| No unrelated mutations / color redesign | **PASS** |

**Stop after Wave 4.**
