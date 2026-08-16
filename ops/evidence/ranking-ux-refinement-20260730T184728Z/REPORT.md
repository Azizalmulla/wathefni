# Ranking UX Refinement — Production Report

**Stamp:** `20260730T184728Z`  
**Verdict:** **PASS**  
**Environment:** Production (`root@76.13.63.68`)  
**Contract baseline preserved:** `ranking-queue-contract-20260730T170805Z`  
**UX audit baseline:** `ranking-page-ux-audit-20260730` (FAIL → addressed)

## Summary

Dashboard-only Ranking desk refinement. **No** changes to pool predicates, visibility, eligibility logic, Top-N behavior, or score formulas.

Shipped:

1. **Plain-language counts** — primary **In review order** (= rankable); secondary **Job matches** / **Meets all requirements**; EN/AR helper explaining why eligible can be 0 while candidates remain in review order (`not_applicable`).
2. **Quieter header** — removed repeated count wording; one chip row + helper + optional excluded note.
3. **On-page states** — no job / no run / running / stale / failed / matching but none rankable.
4. **Excluded** — quiet excluded-count line only when matching > rankable; never as leaderboard cards.
5. **Evidence** — CV primary; assessment components only when job `evidence_policy.sources.assessment` is `required` or `optional`.
6. **EN/AR + mobile** — shared `rankingCopy` / eligibility labels; `dir=rtl`; card header stacks on narrow viewports.
7. **Profiler + marks** — `ranking:results` Profiler; `ranking_job_switch`, `ranking_run`, `ranking_expand_evidence`, `ranking_open_candidate`.
8. **Return path** — open from Ranking stays on Ranking; **Back to Ranking** / Escape / focus restore via `useOverlayFocus` + return focus el.
9. **Restored** `rankingQueueContract.ts` so source and tests align.

## Profiler evidence

| Event | When |
|---|---|
| `profiler_commit` · `ranking:results` | React.Profiler onRender |
| `interaction_start` / `network_complete` · `ranking_job_switch` | Job select |
| `ranking_run` | Run / Re-rank |
| `ranking_expand_evidence` | Expand evidence details |
| `ranking_open_candidate` | Open profile from card |

Read live: `window.__WATHEFNI_DASHBOARD_PERF__.snapshot()` after Ranking interactions.  
Asset proof: production chunks contain the mark strings — see `live-proof.json` / `asset-markers.json`.

## Exact files

### Dashboard
- `apps/wathefni-dashboard/src/lib/rankingQueueContract.ts` — **restored**; counts, EN/AR copy, eligibility labels, assessment gate
- `apps/wathefni-dashboard/src/lib/rankingQueueContract.test.ts`
- `apps/wathefni-dashboard/src/lib/rankingPresentation.ts` — CV-first component rows; assessment gated
- `apps/wathefni-dashboard/src/pages/RankingPage.tsx` — states, quiet counts, Profiler, marks, stacking
- `apps/wathefni-dashboard/src/pages/RankingUxContract.test.tsx` — UX contract tests
- `apps/wathefni-dashboard/src/App.tsx` — `rankingError`; return-to-Ranking; return focus
- `apps/wathefni-dashboard/src/components/candidates/CandidateProfilePage.tsx` — Escape/focus/`aria-modal`; `returnLabel`
- `apps/wathefni-dashboard/src/lib/candidateProfilePresentation.ts` — `backToRanking` EN/AR
- `apps/wathefni-dashboard/src/types.ts` — optional `provenance` / `evidence_policy` on `RankingResponse`
- `ops/deploy-ranking-ux-refinement.sh`

### Backend
- **None** (dashboard-only)

### Live assets
- `RankingPage-Bm2jdD3O.js`
- `dashboard-CyJ83Ezy.js`
- `CandidateProfilePage-Bq8t1dkq.js`
- `useOverlayA11y-D0zfUN-J.js` / `dashboardPerf-BkT7Ij7A.js`

## Production evidence

| Check | Result |
|---|---|
| Vitest (`rankingQueueContract` + `RankingUxContract`) | **PASS** 9/9 |
| Build | **PASS** |
| Health after deploy | **PASS** `200` |
| EN plain-language markers | **PASS** |
| AR markers | **PASS** |
| State / excluded / CV evidence markers | **PASS** |
| Profiler mark strings in assets | **PASS** |
| Back to Ranking EN+AR in assets | **PASS** |
| Live proof verdict | **PASS** (`live-proof.json`) |

## Rollback

```bash
/opt/wathefni/backups/production-pre-ranking-ux-refinement-20260730T184728Z/ROLLBACK.sh
```

## Preserved (unchanged)

- `ranking.pool.matching` / `rankable` / `eligible` / `excluded`
- `ranking.run.top_n`
- CV-first scoring; assessment weight only when job-approved
- Visibility / assignment scope
- Score formulas

## Verdict

**PASS**
