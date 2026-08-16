# Wathefni Frontend Responsiveness — Wave 3

**Date:** 2026-07-30  
**Status:** **PASS**  
**Binding audit:** `ops/WATHEFNI_FRONTEND_RESPONSIVENESS_AUDIT.md`  
**Prior waves:** Wave 1 PASS · Wave 2 PASS  
**Constraint honored:** No UI redesign · No backend business-logic changes · No App/bundle splitting

---

## Goal

Reduce unnecessary boot work and large-list fetching so the dashboard stays fast as tenants grow — page-gated Query fetches, bounded first-page lists, and lightweight client instrumentation.

---

## Exact files changed

| File | Change |
|---|---|
| `apps/wathefni-dashboard/src/lib/query/useDashboardServerState.ts` | Remove Overview `warmLists`; page-gate Candidates/Jobs/Interviews/Assessments/Reports/positions/config; expose infinite load-more |
| `apps/wathefni-dashboard/src/lib/query/fetchers.ts` | `fetchApplicationsPage` / `fetchAssessmentQueuePage` (no 1000-row crawl) |
| `apps/wathefni-dashboard/src/lib/query/hooks.ts` | `useApplicationsInfiniteQuery` · `useAssessmentQueueInfiniteQuery` · request counters |
| `apps/wathefni-dashboard/src/lib/query/keys.ts` | Stable `applications` / `assessment-queue` infinite keys |
| `apps/wathefni-dashboard/src/lib/perf/dashboardPerf.ts` | **New** — interaction / cached paint / network / Overview interactive / page visit / request counts (no PII) |
| `apps/wathefni-dashboard/src/lib/perf/dashboardPerf.test.ts` | **New** — unit tests for instrumentation |
| `apps/wathefni-dashboard/src/main.tsx` | Install `window.__WATHEFNI_DASHBOARD_PERF__` |
| `apps/wathefni-dashboard/src/App.tsx` | Candidates/Assessments load-more wiring; InfiniteData mutation patch |
| `apps/wathefni-dashboard/src/App.test.tsx` | Wave 3 boot + Candidates bounded-page proofs |

**Not changed:** backend routes / SQL / RBAC · no new pagination endpoint · no visual redesign · no `React.lazy` App split (Wave 4)

---

## What changed (behavior)

### 1. Page-gated fetching
- Overview loads **bootstrap + summary + notifications + work-queue** (and opposite-scope prefetch only).
- **No** deferred warm of Candidates, Interviews, Assessments, Jobs, Reports, or `positions-all`.
- Heavy module queries enable only when that page is active (or selector surfaces that need positions: Candidates / Ranking / Assessments).

### 2. Candidates
- Replaced multi-page crawl (up to 1000 apps) with **infinite query**, first page `limit=100`.
- Additional pages only via Load more / Next-at-end.
- Filters, counts (`total` from server), drawer profile Query, and person aggregation over **loaded** rows preserved.

### 3. Assessments
- Queue crawl removed; **infinite** cohort pages (`limit=50`) only while Assessments is open.
- Attempts/config also Assessments-page-gated (config no longer Overview-warm).
- Cohort counts still come from summary authority (canonical ranking/assessment truth unchanged).

### 4. Jobs / positions
- Jobs list only on Jobs page.
- `positions-all` only for selector pages (Candidates / Ranking / Assessments).
- Unfiltered Jobs page reuses jobs payload as selector fallback — avoids duplicate `positions-all` on Jobs alone.
- Load-more still appends via Query `setQueryData` (no second authority).

### 5. Interviews / Reports
- Interviews only when Interviews page is open.
- Reports only when Reports page is open (Wave 1/2 preserved).
- Cached revisits remain immediate via TanStack Query (`staleTime` / `gcTime` / `keepPreviousData`).

### 6. Query architecture
- Single authority (Wave 2 QueryClient).
- Infinite keys: `['wathefni', COMPANY, actor, 'applications'|'assessment-queue', 'infinite', …]`.
- Targeted invalidation helpers unchanged (prefix match still works).

### 7. Instrumentation
- `dashboardPerf*` marks: interaction start, cached paint, network complete, Overview interactive, page first-load / cached-return, request counts.
- Global: `window.__WATHEFNI_DASHBOARD_PERF__.snapshot()` / `.reset()`.
- No personal, candidate, token, or phone data in events.

---

## Before / after boot request counts

| Phase | Wave 2 (after Overview interactive + ~1.1s warm) | Wave 3 |
|---|---|---|
| Core Overview | bootstrap (optional), summary, notifications, work-queue | **Same core** |
| Background warm | applications crawl (1–N), interviews, assessments (±config), jobs/positions | **None** |
| Reports | Not on boot | Not on boot |

**Proof:** `App.test.tsx` boot test waits 1.5s after Overview paint and asserts **zero** `/applications`, `/interviews`, `/assessments`, `/positions` calls.

Typical Overview interactive path (prehire): **~3–4** GETs (summary + notifications + work-queue ± bootstrap).

---

## Before / after list request counts

| Interaction | Wave 2 | Wave 3 |
|---|---|---|
| Candidates first screen | Up to **10** × `limit=100` crawl (cap 1000) | **1** × `limit=100&offset=0` (+ feature flags) |
| Candidates load more | N/A (already fully crawled) | **1** next page when requested |
| Assessments queue open | Up to **10** × cohort applications crawl | **1** × `limit=50&offset=0` |
| Assessments queue more | N/A | **1** next page when requested |
| Jobs page | 1 jobs (± warm positions-all) | 1 jobs; positions-all **not** unless selector page |
| Interviews page | 1 (also warmed from Overview) | 1 **only** when page opened |
| Cached page return | Query cache paint | Query cache paint (unchanged, still immediate) |

**Proof:** Wave3 Candidates test asserts first open uses `limit=100&offset=0` and **no** `offset=100`.

---

## Timing instrumentation results

| Signal | How measured | Result this pass |
|---|---|---|
| Overview interactive | `dashboardPerfMarkOverviewInteractive` after summary+notifications | Fired once per session boot (unit + runtime hook) |
| Request counts | `dashboardPerfCountRequest` on list fetchers | Unit-tested; live snapshot via `__WATHEFNI_DASHBOARD_PERF__` |
| Interaction → cached paint | Marked on Candidates list when cache present during fetch | Hooked in server-state |
| Page first-load vs cached return | `dashboardPerfMarkPageVisit` | Unit-tested |
| PII safety | Snapshot JSON must not contain emails/tokens/phones | Unit-tested |

Browser RUM wall-clock on production was not collected in this workstation pass; architecture + automated request-path tests are the Wave 3 proof (same evidence style as Waves 1–2).

Operator read-out:

```js
window.__WATHEFNI_DASHBOARD_PERF__.snapshot()
```

---

## Cross-tenant safety

- Query keys still include company + actor (`tenantRoot`).
- `useClearQueriesOnTenantChange` clears client on company change.
- Unchanged from Wave 2 PASS.

---

## Tests

| Suite | Result |
|---|---|
| `apps/wathefni-dashboard` vitest (**19** files / **98** tests) | **PASS** |
| Includes Wave3 boot no-list-warm | **PASS** |
| Includes Wave3 Candidates bounded page | **PASS** |
| Includes `dashboardPerf.test.ts` | **PASS** |
| Wave1 scope-switch + Wave2 Query provider | **PASS** |
| `tsc -b` + `vite build` | **PASS** |
| Bundle | `dist/assets/dashboard-*.js` ≈ **723 KB** (split still Wave 4) |

Orchestrator Multi-User / Calendar live smokes: not re-run locally (no service env / `psycopg2`) — **no backend changes** in Wave 3.

---

## Rollback evidence

Wave 3 is frontend-only.

1. Revert the listed dashboard files (or prior `dist`).  
2. Redeploy previous dashboard artifact.  
3. No DB migrations / API contract changes to undo.  
4. Deprecated crawl helpers remain in `fetchers.ts` only as comments/aliases — not used by live hooks.

Feature flags: none required.

---

## Wave 3 PASS/FAIL

### **PASS**

Stop criteria met:

- [x] Overview interactive without Candidates / Interviews / Assessments / Reports / Jobs list crawls  
- [x] Candidates first screen bounded (single page, load-more for more)  
- [x] Assessments queue on-demand + paginated  
- [x] Jobs/positions duplicate warm removed; selector fetch scoped  
- [x] Cached page return remains Query-backed / immediate  
- [x] No second server-state authority; Wave 2 invalidation kept  
- [x] Lightweight client instrumentation without PII  
- [x] Dashboard tests + production build green  

---

## Remaining Wave 4 items

From audit Wave 4 (render / bundle hygiene) — **not started**:

1. Split `App.tsx` into route islands  
2. `React.lazy` / code-split heavy pages (Calendar, Assessments reports, etc.)  
3. Memo expensive tables / reduce god-component rerenders  
4. Main chunk size reduction (currently ~723 KB)  
5. Optional entity normalization for list ↔ drawer sharing (still optional)

**Still later:** Wave 5 backend work-queue specialization only if APIs remain slow after Waves 2–4.

**Stop after Wave 3.**
