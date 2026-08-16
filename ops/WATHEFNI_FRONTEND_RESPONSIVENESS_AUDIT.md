# Wathefni Frontend Responsiveness Audit

**Date:** 2026-07-29  
**Scope:** Read-only audit of `apps/wathefni-dashboard` interaction latency  
**Constraint:** No UI redesign, no backend business-logic changes, no fixes implemented  
**Evidence tenant measured:** `WATHEFNI` (production orchestrator in-process timings)

---

## Executive verdict

The dashboard does **not** feel premium primarily because of **frontend interaction architecture**, not because Overview/Calendar backends are slow on the evidence tenant.

There is **no server-state cache** (no React Query / SWR / Redux), **no per-tab result memory**, **no request abort/dedupe**, and several interactions **disable controls and wait on network** (or blank the panel) before the UI can settle.

On `WATHEFNI`, core backend builders are typically **single-digit to low tens of ms**. Perceived lag is dominated by:

1. Coupling local tab/scope UI to a **global non-silent refresh**
2. **Blanking** calendar content while refetching
3. **Eager boot fan-out** + hard loading gate
4. **Monolithic `App.tsx` re-renders** (~7.9k lines, ~101 hooks, no `memo`/`lazy`)
5. Missing stale-while-revalidate / previous-data retention

---

## Stack facts (current)

| Item | Finding |
|---|---|
| App | Vite + React 19 SPA (`apps/wathefni-dashboard`) |
| Router | None — `page` state + `history.pushState` (`dashboardNavigation.ts`) |
| Server state | `useState` + `useEffect` + raw `fetch` in `lib/api.ts` |
| Cache / SWR | **None** |
| Abort / dedupe | **None** (`AbortController` unused) |
| Code splitting | **None** (`React.lazy` / `Suspense` unused) |
| Memoization | `useMemo`/`useCallback` for some loaders; **zero** `React.memo` |
| Main bundle | `dist/assets/dashboard-*.js` ≈ **657 KB** (672,763 bytes) |
| God component | `App.tsx` ≈ **7,941 lines**, ~**101** `useState`/`useEffect`/`useCallback`/`useMemo` occurrences |

---

## Measured timings

### A) Backend builders (production host, in-process, `WATHEFNI`)

Measured via orchestrator venv against live DB (3 samples). These are **server compute**, not browser RTT.

| Workload | avg | min | max | Notes |
|---|---:|---:|---:|---|
| `work_queue` scope=`mine` | **10 ms** | 7 | 15 | 0 items for sampled owner actor |
| `work_queue` scope=`company` | **5 ms** | 5 | 6 | 3 items |
| `build_overview_authority` (summary core) | **41 ms** | 38 | 48 | Used by `/dashboard/prehire/summary` |
| `applications` page `limit=100` | **27 ms** | 21 | 36 | tenant has **14** production applications |
| 3 sequential application pages | **62 ms** wall | — | — | sizes `[11,0,0]` |
| calendar events week `mine` | **4 ms** | 3 | 6 | 0 events in sample |
| calendar events week `company` | **2 ms** | 2 | 3 | 0 events |
| calendar events month-grid `mine` | **3 ms** | 2 | 3 | 0 events |
| calendar overview `mine`/`company` | **4–5 ms** | 4 | 5 | empty month/upcoming |
| positions payload `limit=25` | **10 ms** | — | — | |

**Approx Overview scope-switch server wall** (parallel summary-ish + work-queue for `mine`): **~110–335 ms**, avg **~212 ms** in one short burst (thread-pool contention / cache variance).

### B) What the browser still adds (not directly timed; reasoned)

Live HTTP timings through nginx were unavailable (no access-log `request_time` samples; no dashboard user session for authenticated curl). Expected additional cost per interaction:

- TLS + API proxy RTT to `api.wathefni.ai`
- JSON parse of summary/reports/notifications payloads
- Full `App` re-render while `busy=true`
- Control lock (`disabled={busy}`) until refresh finishes

**Implication:** even with 5–50 ms backends, users can still feel **200–800+ ms** “dead” UI when the frontend waits on a global refresh and disables the toggle.

### C) Backend endpoints that are *genuinely* at risk when tenants grow

Not slow on `WATHEFNI` today, but architecture is **O(tenant work)** and will become user-visible without frontend caching:

| Endpoint / builder | Why it can get slow |
|---|---|
| `GET /dashboard/prehire/overview/work-queue` | Always builds a **company queue (limit 100)** then filters to `mine`/`company` (`prehire_personal_work.build_scoped_work_queue`) |
| `GET /dashboard/prehire/summary` | Multiple aggregates + overview authority + recent apps + positions |
| `GET /dashboard/prehire/applications` (client multi-page) | Frontend may issue **up to 10 sequential** `limit=100` calls (hard cap 1000) on boot / Apply |
| `GET /dashboard/calendar/events` | Fine now; cost grows with range × scoped event volume / projection rules |

---

## Surface-by-surface findings

### 1) Overview — My work / Company work

**Files:** `App.tsx` (`workQueueScope`, `refreshAll`, Overview UI)

**What happens on click**

1. `setWorkQueueScope(next)` — local label updates immediately.
2. `refreshAll` identity changes because it closes over `workQueueScope`.
3. Boot effect `[access, accessIssue, refreshAll]` re-runs and calls **`refreshAll(access)` without `silent`**.
4. `setBusy(true)` + notice “Refreshing…”.
5. Parallel fetches:
   - `GET /dashboard/prehire/summary`
   - `GET /dashboard/prehire/notifications?scope=mine|company`
   - `GET /dashboard/prehire/reports`
   - `GET /dashboard/prehire/overview/work-queue?limit=10&scope=mine|company`
   - optionally assessment config
6. Scope toggle buttons are **`disabled={busy}`**.
7. List rows keep **previous scope’s `workQueue.items`** until response lands (stale content under the new title).
8. Switching back repeats the full refresh — **no per-scope cache**.

**Requests per switch:** 4–5 (unnecessary: summary + reports do not need to change with work-queue scope).

**Race:** overlapping refreshes possible; last `setWorkQueue` wins (no generation token / abort).

**Root cause rank for this exact complaint:** #1.

---

### 2) Overview mini-calendar — My / Company

**File:** `OverviewCalendarPanel.tsx`

- Local `scope` + `data` + `busy`.
- Fetch: `GET /dashboard/calendar/overview?scope=…`
- Loader only when `busy && !data` — previous data retained (better than full Calendar).
- Still: no per-scope cache, no abort, scope change always network-bound for content correctness.

---

### 3) Calendar page — My / Team / Company + day / week / month

**File:** `CalendarShell.tsx`

**Requests**

- Scope/view/range/filter change → `GET /dashboard/calendar/events?...`
- Mount / `orgScopeId` churn → also `GET /dashboard/calendar/team-scopes`
- Event select → **3 parallel** detail calls (`event`, `reschedule-requests`, `sync`)

**UX defect**

Any refetch **replaces the entire calendar surface with a spinner** (`busy ? Loading : grid`) — layout jump + lost previous view. This is the opposite of stale-while-revalidate.

**Race:** `load()` has no abort / request id; rapid day→week→month can apply an older range’s events after a newer one.

**Day/week/month:** changing `view` recomputes `range` → new `load` → blank → fetch. Previously loaded week/month ranges are discarded.

---

### 4) Page navigation

- Conditional render in `App` (`activePage === '…'`). Leaving a page **unmounts** it; returning remounts and may refetch (Calendar especially).
- Sidebar/`App` stay mounted — good — but page-local caches die with unmount.
- Hard gate: `dashboardLoaded = summary && applications && notifications && interviews && reports`
- Overview can sit behind **Candidates + Interviews + Reports** loads even if the user only wanted Overview.
- Boot eagerly fires (not page-gated): summary/notifications/reports/work-queue, applications (multi-page), interviews, assessments, jobs, all-positions.

---

### 5) Filters and search

| Surface | Behavior | Issues |
|---|---|---|
| Jobs search | 350 ms debounce (`search-input.tsx`) | No abort; each debounced value refetches; no cache |
| Candidates filters | Local until **Apply** | Apply triggers multi-page aggregation up to 1000 rows |
| Interviews | Tab/paging auto-refetch; search button explicit | No abort; global `busy` often shared |
| Activity log | 350 ms debounce | Better pattern |
| People picker | 180 ms debounce | Better pattern |

No shared query key cache → identical filter sets refetch from scratch.

---

### 6) Drawers and modals

All are **mount/unmount**, not keep-alive:

| Surface | Open cost |
|---|---|
| Candidate profile | `GET .../person-profile` every open |
| Assessment report | `GET .../assessments/:id` then mount report |
| Job workspace | Uses list row (cheaper) |
| Interview drawer | Local selection; state lost on close |
| Confirm dialog | Conditional mount from provider |

Reopening feels slow because nothing is remembered.

---

### 7) Candidates / Jobs / Interviews / Assessments / Reports

| Tab | Load pattern | Responsiveness issue |
|---|---|---|
| Candidates | Boot + Apply; sequential pages; `aggregateCandidatesForList` in render path | Boot contention; heavy client aggregation; table under global `busy` |
| Jobs | Boot + filter/search effect | Duplicate positions fetch (`jobs` list + `allPositions` limit 200) |
| Interviews | Boot + tab/filter effects | Shared busy; remount loses UI state |
| Assessments | Boot attempts; queue only on Assessments page | Queue can pull up to 1000 applications sequentially |
| Reports | Loaded in **every** `refreshAll`, not on Reports entry | Scope switches and refreshes pay reports cost for no UI reason |

---

### 8) Arabic / English

- `recruitingLocale` in `App` + `localStorage`; sets `dir` and copy helpers.
- **Does not** refetch Overview lists/Calendar by design (good).
- **Does** refetch Ranking when on Ranking page (`useEffect` deps include `recruitingLocale`).
- Full tree re-renders on locale flip (expected), amplified by lack of memoized leaf components.

---

## Root causes ranked by impact

1. **Overview scope toggle triggers global non-silent `refreshAll`**  
   Disables controls, refreshes unrelated summary/reports, no per-scope cache → exact “switch back feels laggy” bug.

2. **No server-state cache / SWR layer**  
   Every remount, revisit, scope/view change, and many mutations pay full network. No dedupe, no stale-while-revalidate, no prefetch.

3. **Calendar blanks on every refetch**  
   `busy ? spinner : grid` destroys perceived continuity even when APIs are 2–10 ms.

4. **No abort / request generation tokens**  
   Stale responses can overwrite newer user choices (Calendar range/scope, Jobs search, overlapping refreshAll).

5. **Eager boot fan-out + `dashboardLoaded` gate**  
   Time-to-interactive for Overview blocked by lists the user may never open; many parallel requests compete.

6. **Monolithic `App.tsx` + no memo/lazy**  
   Global `busy`/notice/list updates re-render large trees; 657 KB main chunk; page modules not split.

7. **Candidates multi-page aggregation strategy**  
   Fine at 14 apps; becomes multi-second sequential waterfalls at hundreds/thousands of applications.

8. **Drawers discard state**  
   Repeat opens always refetch; no session memory.

9. **StrictMode double-mount in dev** (`main.tsx`)  
   Amplifies duplicate fetches during local development only.

---

## Exact proposed fixes (no implementation yet)

### Interaction contract (product rule)

For every tab/scope/filter control:

1. **Update local UI state synchronously** (selected tab/scope/view always instant).
2. If cache hit for that key → **paint immediately**.
3. If miss → show **skeleton only on first load**; otherwise keep previous paint.
4. Refresh in background; never disable the control that the user just used unless submitting a mutation.
5. Ignore/abort responses that are not the latest request id for that key.

### Recommended long-term architecture

Adopt **TanStack Query (React Query)** as the server-state layer (fits Vite SPA; team already uses effect-fetch patterns):

- Query keys, e.g.
  - `['prehire','work-queue', company, scope]`
  - `['calendar','events', company, scope, start, end, filters…]`
  - `['prehire','applications', company, filters]`
- Defaults: `staleTime: 30_000`, `gcTime: 5 * 60_000`, `placeholderData: keepPreviousData` (or `(prev) => prev`).
- `prefetchQuery` on hover/idle for opposite Overview scope and adjacent calendar ranges.
- Mutations call targeted `invalidateQueries` — **not** a global `refreshEverything` unless user hits Refresh.

Keep **UI selection state** in React local state (or a tiny Zustand store) **separate** from fetched payloads.

Optional later: normalize entities (candidates/jobs) if list+drawer sharing gets painful — not required for Wave 1.

### Per-surface exact fixes

| Surface | Fix |
|---|---|
| Overview My/Company | Local scope state; fetch **only** work-queue (+ notifications if scope-specific). Cache both scopes. Do **not** call `refreshAll` / `setBusy`. Prefetch the other scope on idle/hover. |
| Overview calendar | Cache `overview` by scope; keep previous data; soft indicator only, not full blank. |
| Calendar shell | Keep previous events while `isFetching`; abort prior `load`; cache by `(scope, range, filters)`; prefetch week when landing on day and adjacent months on idle. |
| Navigation | Soft-cache page query sets; Query cache survives unmount. Gate Overview on summary/work-queue only. |
| Candidates | Server-driven person page **or** keep aggregation but cache filter key; never block Overview boot on full candidate crawl. |
| Jobs | Dedupe list vs selector queries; abort debounced search. |
| Drawers | `placeholderData` from list row + background detail fetch; keep last profile in query cache. |
| i18n | Keep locale client-only; Ranking should pass `locale` as query key without tearing other pages. |
| Bundle | `React.lazy` Calendar, Assessments report, Post-hire, Setup-heavy panels. |

### Stale-request protection (minimum viable even before React Query)

```ts
let seq = 0
async function load() {
  const my = ++seq
  const data = await api(...)
  if (my !== seq) return
  setData(data)
}
// better: AbortController passed to fetch
```

### Cache invalidation after mutations

- Create/update/cancel calendar event → invalidate that range + overview + selected event only.
- Candidate status / interview write → invalidate affected lists + work-queue scopes + summary action counts.
- Avoid `revalidatePrehire()` blasting **all** lists after every action (current pattern).

---

## Recommended implementation waves

### Wave 0 — Instrumentation (½–1 day)

- Add lightweight client timings: interaction start → paint of target key → network end.
- Log duplicate in-flight query keys in dev.
- Add nginx/API `request_time` for `/dashboard/*` (ops).  
**Stop criteria:** heatmap of slow interactions with p50/p95.

### Wave 1 — Instant local UI + stop global busy coupling (2–4 days) — **highest ROI**

- Decouple Overview scope from `refreshAll`.
- Calendar: keep previous events while fetching; remove full-panel spinner.
- Introduce request seq/abort on Calendar + Overview queue.
- Stop disabling scope toggles on global `busy`.  
**Stop criteria:** My↔Company and day/week/month feel instant; no blank calendar on toggle.

### Wave 2 — React Query + tab caches (1–1.5 weeks)

- Wrap dashboard data loaders in QueryClient.
- `placeholderData` / SWR defaults; prefetch opposite Overview scope + adjacent calendar ranges.
- Narrow mutation invalidation.  
**Stop criteria:** Revisiting tabs paints cached data in under 50 ms local; network quiet in background.

### Wave 3 — Boot & list strategy (1 week)

- Page-gated fetching; shrink `dashboardLoaded` gate.
- Candidates: stop boot-time full crawl; prefer paged person API or first-page-only.
- Deduplicate jobs/positions fetches.  
**Stop criteria:** Overview interactive without waiting on Candidates/Interviews/Reports.

### Wave 4 — Render/bundle hygiene (3–5 days)

- Split `App.tsx` route islands; `lazy` heavy pages; memo expensive tables.
- Preserve drawer query cache across open/close.  
**Stop criteria:** Main chunk down; interaction profiler shows scoped rerenders.

### Wave 5 — Backend only if Wave 0–3 still show slow APIs

- Specialize `work-queue?scope=mine` so it does not always materialize company-100 then filter.
- Add list pagination that matches UI person aggregation.
- Calendar projection indexes / tighter SQL if event volume grows.

---

## Interaction matrix (requests today)

| Interaction | Requests fired | UI waits on network? | Cache hit on return? | Stale-race guarded? |
|---|---|---|---|---|
| Overview My↔Company | 4–5 (summary, notifications, reports, work-queue, ±config) | **Yes** (`busy`, buttons disabled) | **No** | **No** |
| Overview calendar My↔Company | 1 overview | Soft (keeps old data) | **No** | **No** |
| Calendar My/Team/Company | 1 events (+ team-scopes sometimes) | **Yes** (full blank) | **No** | **No** |
| Calendar day/week/month | 1 events (new range) | **Yes** (full blank) | **No** | **No** |
| Page nav to Calendar | 1–2 on mount | First load spinner | Lost on unmount | Partial (detail only) |
| Jobs debounced search | 1 positions | List refresh | **No** | **No** |
| Candidates Apply | 1–N applications pages (+ views) | **Yes** | **No** | **No** |
| Open candidate profile | 1 person-profile | Drawer waits | **No** | N/A |
| Locale EN↔AR | 0 (Ranking: 1) | No (except Ranking) | N/A | N/A |

---

## Target “premium app” checklist

- [ ] Controls acknowledge in the same frame (&lt;16 ms local state)
- [ ] Cached views paint immediately; network is background
- [ ] Skeletons only for cold first load
- [ ] No full-section blanking on refresh
- [ ] No duplicate in-flight identical queries
- [ ] Stale responses never overwrite newer selections
- [ ] Mutations invalidate narrowly
- [ ] Overview boot not blocked by unused modules
- [ ] Bundle split for Calendar / heavy reports

---

## Out of scope / explicitly not done

- No UI redesign
- No code fixes applied
- No backend business-logic changes
- Microsoft / Calendar provider work unchanged

---

## Appendix — key code anchors

- Global refresh + scope coupling: `App.tsx` `refreshAll` / `workQueueScope` / effect deps
- Overview toggle disabled while busy: Overview buttons `disabled={busy}`
- Calendar blanking: `CalendarShell.tsx` `{busy ? Loading : grid}`
- Candidates multi-page crawl: `App.tsx` `loadApplications` `while` loop (`batchSize=100`, `hardCap=1000`)
- API transport: `lib/api.ts` `request()` — no `signal`, no cache
- Work-queue backend always company-then-filter: `prehire_personal_work.build_scoped_work_queue`
