# Ranking Queue Contract — Production Report

**Stamp:** `20260730T170805Z`  
**Verdict:** **PASS**  
**Environment:** Production (`root@76.13.63.68`)  
**Tenant proof:** `WATHEFNI`

## Summary

Implemented the approved Ranking consistency contract. Ranking is a job-scoped advisory review order for applications HR can currently review; the ranking unit remains one application (`app_key`). Matching requires usable CV evidence and the same assignment/visibility scope as Candidates. Leaderboard ranks and Top-N come only from the rankable pool. Assessment stays unused by default; the approved matching assessment lateral is wired. Opening a ranked row resolves full application authority via `openCandidateByKey`. No score-formula changes and no broad UI redesign.

## Contract

| Axis | Unit | Owns |
|---|---|---|
| `ranking.pool.matching` | application | Exact job + production + usable CV + Candidates visibility; exclude hired/rejected/withdrawn/archived |
| `ranking.pool.rankable` | application | Matching ∧ required evidence complete ∧ bucket ∈ {eligible, not_applicable} |
| `ranking.pool.eligible` | application | Hard-criteria eligible only (distinct from rankable) |
| `ranking.pool.excluded` | application | requirement_not_met / insufficient_information / restricted-held — explain only, no soft_rank |
| `ranking.run.top_n` | application | Slice only from rankable (never fill with unrankable) |

## Live proof (WATHEFNI)

| Check | Result |
|---|---|
| FULLSTACK matching ≡ Candidates active_pipeline | **1 ≡ 1** (missing-CV excluded; was 2 in audit) |
| FULLSTACK rankable / eligible / top-N | **0 / 0 / 0** (`insufficient_information` not ranked) |
| HR `not_applicable` rankable, not hard-eligible | **matching 2 · rankable 2 · eligible 0** |
| ACCOUNTING `not_applicable` rankable | **matching 1 · rankable 1 · eligible 0** |
| Counters reconcile (eligible + N/A + not_met + unknown → matching) | **PASS** (all jobs) |
| Top-N never contains not_met / insufficient_information | **PASS** |
| Archived / hired / rejected / withdrawn never in matching | **PASS** (hired present on SOCIAL_MEDIA_MANAGER DB, excluded from pool) |
| Owner matching ≡ Candidates reviewable pipeline | **PASS** |
| Empty-assignment recruiter matching = 0 | **PASS** |
| Assessment default unused + lateral wired | **PASS** |
| Health | **PASS** `200` |

Evidence: `live-proof.json`.

## Files

### Backend
- `wathefni-orchestrator/ranking_queue_contract.py` (**new**)
- `wathefni-orchestrator/candidate_ranking.py` — matching CV gate; archived exclusion; visibility; assessment lateral; rankable-only soft_rank / top_n; counters
- `wathefni-orchestrator/app.py` — `dashboard_prehire_rank` detail visibility; assignment-scoped actors force scoped recalculation
- `wathefni-orchestrator/test_ranking_queue_contract.py` (**new**)
- `wathefni-orchestrator/test_candidate_ranking.py` — capped assertion aligned to rankable

### Dashboard
- `apps/wathefni-dashboard/src/lib/rankingQueueContract.ts` / `.test.ts`
- `apps/wathefni-dashboard/src/pages/RankingPage.tsx` — matching / rankable / eligible copy + badges
- `apps/wathefni-dashboard/src/App.tsx` — Ranking open → `openCandidateByKey(app_key)`
- `apps/wathefni-dashboard/src/types.ts` — matching/rankable/eligible counts

### Live assets
- `RankingPage-D0_GbFEP.js`
- `dashboard-lzflJFQy.js`

## Migration impact

**None.** Runtime pool/count/visibility predicates only. No schema change.

## Rollback

```bash
/opt/wathefni/backups/production-pre-ranking-queue-contract-20260730T170805Z/ROLLBACK.sh
```

Restores prior `app.py`, `candidate_ranking.py`, ranking tests, dashboard dist; removes `ranking_queue_contract.py` if it was newly introduced.

## Tests — PASS/FAIL

| Check | Result |
|---|---|
| Unit contract suite (prod) | **PASS** 8/8 |
| Local vitest `rankingQueueContract` | **PASS** 2/2 |
| Live FULLSTACK missing-CV excluded | **PASS** |
| Live HR / Accounting not_applicable rankable ≠ eligible | **PASS** |
| Live Top-N rankable-only | **PASS** |
| Live visibility empty-assignment = 0 | **PASS** |
| Health | **PASS** `200` |

## Out of scope (unchanged)

Score formulas, broad Ranking UI redesign, Jobs/Candidates/Assessments contracts (already shipped).
