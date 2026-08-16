# Ranking Page — Deep UX Audit (Pre-UI)

**Date:** 2026-07-30  
**Scope:** Ranking page only — **audit; no implement; no deploy**  
**Contract baseline:** `ops/evidence/ranking-queue-contract-20260730T170805Z` (**PASS** — preserve)  
**UX audit verdict:** **FAIL** vs calm HR-ready Ranking desk (contract remains PASS)  
**Canvas:** `ranking-page-ux-audit.canvas.tsx`

---

## Exact purpose

Ranking is the **job-scoped advisory desk**: given one job, show which applications HR should review first (CV-first), with evidence and a recommended next step. Unit = one application (`app_key`). Ranking does **not** mutate lifecycle.

| Surface | Owns | Does **not** own |
|---|---|---|
| **Ranking** | Advisory review order for one job; rankable top-N; open full application | Pipeline stages; send/review assessments; job publish; CSV export |
| **Candidates** | Pipeline + full application authority | Soft-rank leaderboard |
| **Assessments** | Send / attempts / reports | Ranking order (feeds score only when approved) |
| **Jobs** | Openings lifecycle + share | Who to review first |
| **Overview** | Today’s CTAs (may deep-link Ranking) | Full ranking desk |
| **Reports** | Leadership metrics / export | Day-to-day re-rank |

### Preserve (locked)

`ranking.pool.matching` · `rankable` · `eligible` · `excluded` · `ranking.run.top_n` · CV-first · assessment optional only when job-approved · visibility/assignment · **no score-formula changes**.

---

## Current structure

| Block | What exists |
|---|---|
| Job selector + Run / Re-rank | `RankingPage.tsx` card controls |
| Header counts | Description line + Matching / Rankable / Eligible badges |
| Comparison / fit profile | Optional banners above list |
| Leaderboard | Rankable top-N cards only |
| Excluded evidence | **Absent** (counters unused in UI) |
| Empty | Job-required / no-run / no ranked candidates |

Primary files: `RankingPage.tsx`, `App.tsx` (load/re-rank/`openCandidateByKey`), `rankingPresentation.ts`, `types.ts` Ranking*, backend `ranking_queue_contract.py` + `candidate_ranking.py` + `GET /dashboard/prehire/rank`.

Note: contract REPORT listed `rankingQueueContract.ts` — **file missing**; only `rankingQueueContract.test.ts` on disk.

---

## Vocabulary & counts

- **matching / rankable / eligible** shown as jargon (EN + AR) with no plain-language gloss.
- Rankable includes `not_applicable`; eligible is hard-criteria only — can diverge (live: HR matching 2 · rankable 2 · eligible 0).
- Same three numbers repeated in description + badges → visual noise.
- Advisory score framing is good; eligibility may fall back to `stageLabel` title-case.

---

## Row clarity

| Question | Today |
|---|---|
| Why this candidate is here | Partial — name, job, stage, eligibility label |
| Why this rank | Partial — display index + advisory score + fit summary; weak vs peers |
| Missing evidence | Yes — gaps snapshot (≤3); more in details |
| What HR should do next | Yes — recommended next step |

Evidence / score components live under `<details>`. Assessment score component is visually equal to CV relevance when present (backend still CV-first by default).

---

## Excluded / unrankable

Backend: retained for explanation; never soft-ranked / never in top_n.  
UI: **no cards and no quiet summary** — if matching > 0 and leaderboard empty, HR lacks an excluded explanation.

**Recommendation for later (not now):** optional one-line quiet note only; never leaderboard cards.

---

## States

| State | Reality |
|---|---|
| Job-required | Copy + empty; clear ranking when no position |
| No-run | `needs_run` + Run ranking CTA |
| Running | Global `busy` only |
| Stale-run | API `stale` **unread** by RankingPage |
| Empty rankable | EmptyState; badges may still show counts |
| Partial evidence | Comparison / score hide / gaps |
| Failed-run | Global notice; no page panel |
| Permission | Nav gate; API via prehire context + visibility SQL |

---

## Open candidate / drawer

- Open → `openCandidateByKey(app_key)` → Candidates profile (full authority) — **correct**.
- Profile: body scroll lock **yes**; Escape / focus trap **no**.
- Leaves Ranking context (page switches to Candidates).

---

## Mobile / Arabic / RTL

- Root `dir` when `locale === 'ar'`.
- Most chrome bilingual; **DecisionSnapshot** fallback “Not captured yet.” always EN.
- Dense three-column snapshots + card stacks; no Ranking-specific mobile simplification.

---

## Permissions / audit / rerun / concurrency

- Nav: `pre_hiring` + candidate/jobs/report capability.
- Re-rank: GET `force=true` (no UI OCC tokens; ranking runs use backend request_hash).
- Assignment-scoped actors: forced scoped recalc (contract).
- No Ranking-page audit UI.

---

## React Profiler

**Critical evidence gap:** no `React.Profiler`, no interaction marks for job switch / re-rank / expand / open candidate. Only generic page-visit via dashboard server state. **No timings invented.**

---

## Findings ranked

### Critical
1. **No React Profiler / Ranking interaction perf proof** before UI redesign.

### High
1. **matching / rankable / eligible too technical** (and repeated).  
2. **Excluded pool invisible** despite contract “explain only.”  
3. **Stale / failed / running** under-served on-page.  
4. **Open profile** abandons Ranking; Escape/focus incomplete on profile path.  
5. **Assessment evidence not visually secondary** to CV when components show.

### Medium
1. Header count noise.  
2. Row only partially answers “why this rank.”  
3. EN DecisionSnapshot fallback.  
4. Raw eligibility `stageLabel` fallback.  
5. Missing `rankingQueueContract.ts` (REPORT drift).  
6. Generic Card chrome vs cream system.  
7. Dense three-column decision snapshots on mobile.

### Leave alone
- Locked pool / top_n / visibility / CV-first / optional assessment gate.  
- No score-formula changes.  
- Leaderboard = rankable only.  
- Open → full application authority.  
- Job selector + Run / Re-rank model.  
- Advisory score framing.

---

## Recommended visual direction

Match **Overview / Jobs / Interviews / Assessments**:

- Warm cream (`#fffaf0` / `#f8f3e9`), strong ink (`#23211d`), muted secondary (`#716a5e`), restrained borders.
- Less is more: **one job → one primary count (in review order / rankable) → ranked list → one next action**.
- Plain-language labels; demote Matching / Hard-eligible to quiet secondary chips.
- Optional one-line excluded note when matching > rankable.
- CV evidence above assessment; score components under More.
- Explicit state chrome (no-run / running / stale / error).
- Add Profiler marks **before** cream visual pass.

**Suggested sequence (not started):** Profiler → plain-language counts → quiet excluded + states → CV>assessment hierarchy → cream visual pass.  
**Do not** reopen pool predicates or score formulas.

---

## Exact files (audit scope)

| Path | Role |
|---|---|
| `apps/wathefni-dashboard/src/pages/RankingPage.tsx` | Page UI |
| `apps/wathefni-dashboard/src/App.tsx` | Load / re-rank / openCandidateByKey |
| `apps/wathefni-dashboard/src/lib/rankingPresentation.ts` | Decision / score labels |
| `apps/wathefni-dashboard/src/lib/rankingQueueContract.test.ts` | Contract helpers (module `.ts` missing) |
| `apps/wathefni-dashboard/src/types.ts` | RankingResponse / Candidate |
| `wathefni-orchestrator/ranking_queue_contract.py` | Locked pools |
| `wathefni-orchestrator/candidate_ranking.py` | Authority |
| `wathefni-orchestrator/app.py` | `GET /dashboard/prehire/rank` |
| `ops/evidence/ranking-queue-contract-20260730T170805Z/REPORT.md` | Contract PASS |

---

## PASS / FAIL

| Gate | Verdict |
|---|---|
| Ranking consistency contract (production-locked) | **PASS** |
| Ranking page UX readiness for calm cream desk (this audit) | **FAIL** |
| Implement / deploy | **Not started** (audit only) |
