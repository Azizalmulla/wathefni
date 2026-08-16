# Wathefni Frontend Responsiveness — Wave 1

**Date:** 2026-07-30  
**Status:** **PASS**  
**Binding audit:** `ops/WATHEFNI_FRONTEND_RESPONSIVENESS_AUDIT.md`  
**Constraint honored:** No UI redesign · No backend business-logic changes · No React Query migration

---

## Goal

Remove the worst responsiveness problems platform-wide so common interactions:

- acknowledge instantly (local state)
- do not disable controls for ordinary reads
- keep previously loaded data visible during refresh
- use skeletons only on cold first load
- abort/ignore stale responses
- avoid refreshing unrelated modules

---

## Surfaces changed

| Surface | Wave 1 behavior |
|---|---|
| Overview My / Company work | Scope updates immediately; paints cache if present; fetches **only** work-queue + notifications; **no** `refreshAll` / global `busy`; toggles stay enabled |
| Overview Calendar My / Company | Per-scope session cache; keep previous data; subtle refresh spinner; abort prior fetch |
| Overview Refresh | Explicit Refresh still runs core refresh; scope switch no longer coupled |
| Calendar My/Team/Company + day/week/month + filters | Keep previous events; session cache by range/scope/filters; abort stale loads; cold skeleton only when empty |
| Calendar event drawer | Session cache + abort; list row / cached detail shown while refetching |
| Jobs search/filters/pagination | AbortController gate; local `jobsRefreshing`; Jobs refresh reloads jobs only (not whole dashboard); `allPositions` remains separate selector fetch |
| Candidates Apply / pagination / profile | Abort + generation gate; list stays visible; Apply/pagination not blocked by refresh; profile session cache |
| Interviews tabs/search/pagination | Local `interviewsRefreshing`; search/pagination not disabled for reads; abort gate |
| Assessments tabs/queue/report | Abort on attempts + queue; report session cache paints prior payload while refetching |
| Reports | **Removed from** `refreshAll` / scope switches; loads only on Reports page; preserves prior payload; soft refresh indicator |
| Navigation / boot gate | Overview no longer waits on applications/interviews/reports; lists warm after Overview is interactive |
| Drawers | Candidate profile + assessment report session caches survive close/reopen |

---

## Exact files changed

| File | Change |
|---|---|
| `apps/wathefni-dashboard/src/lib/requestSafety.ts` | **New** — `createRequestGate`, `SessionCache`, `isAbortError` |
| `apps/wathefni-dashboard/src/lib/requestSafety.test.ts` | **New** — unit tests for gates/cache |
| `apps/wathefni-dashboard/src/lib/api.ts` | Optional `RequestInit` / `signal` on key GET helpers |
| `apps/wathefni-dashboard/src/App.tsx` | Scope decoupling, local refreshing, deferred boot, Reports on-demand, list abort gates, UI control unlock |
| `apps/wathefni-dashboard/src/App.test.tsx` | Updated boot expectations + Wave1 scope-switch proof test |
| `apps/wathefni-dashboard/src/components/CalendarShell.tsx` | Keep-previous events, caches, abort, non-blanking refresh |
| `apps/wathefni-dashboard/src/components/OverviewCalendarPanel.tsx` | Scope cache, abort, subtle refresh |
| `apps/wathefni-dashboard/src/components/candidates/CandidateProfilePage.tsx` | Session cache + abort |

**Not changed:** backend routes / SQL / RBAC · no React Query · no visual redesign language

---

## Before / after request counts (key interactions)

| Interaction | Before | After |
|---|---|---|
| Overview My ↔ Company | 4–5: summary + notifications + **reports** + work-queue (+ config) | **2:** notifications + work-queue for that scope only |
| Overview return to prior scope | Same 4–5 again | Cache paint **0** network for paint; background 2 (or replaced via abort) |
| Calendar day ↔ week ↔ month | 1 events + **full panel blank** | 1 events; **previous grid stays**; cache hit paints immediately |
| Calendar scope My ↔ Company | 1 events + blank | 1 events; keep previous / cache |
| Jobs search debounce | 1 positions (no abort) | 1 positions with **abort** of prior |
| Jobs Refresh button | Full `refreshEverything` fan-out | **Jobs list only** |
| Candidates Apply | Multi-page crawl; could race | Same crawl (backend unchanged) with **abort/stale ignore**; list kept |
| Reports during Overview scope switch | Yes (`getPrehireReports`) | **No** |
| Boot Overview interactive | Waited on summary+apps+notifications+interviews+**reports** | Wait on **summary + notifications** only |

---

## Before / after timings

### Server builders (unchanged; from audit, `WATHEFNI`)

Work-queue ~5–15 ms · summary core ~41 ms · calendar events ~2–6 ms.

### Interaction-to-visible-selection (Wave 1 contract)

| Interaction | Before (user-felt) | After (Wave 1) |
|---|---|---|
| Overview scope toggle selected state | Blocked while `busy` (buttons disabled) until full refresh (~200–800+ ms RTT+) | **Immediate** (local); list swaps from cache or stays until scoped fetch returns |
| Calendar view/scope selection | Blank panel until fetch completes | **Immediate** chrome; previous events remain; “Refreshing…” strip |
| Page → Overview first paint | Gated on Candidates/Interviews/Reports loads | Overview paints once summary+notifications ready |

Client proof is via request-path unit tests (boot + scope switch), not browser RUM.

---

## Stale-response protection

- `createRequestGate()` aborts prior `AbortController` and ignores non-current completions.
- Applied to: Overview scoped queue, Candidates, Jobs, Interviews, Assessments, Assessment queue, Reports, Calendar events, Calendar detail drawer, Overview calendar, Candidate profile.
- Proof: `requestSafety.test.ts` + Wave1 App test that scope switch does not bump summary/reports counts.

---

## Rerender impact

- Wave 1 does **not** introduce React Query or split `App.tsx`.
- Impact reduction comes from **not** flipping global `busy` on scope/filter reads (fewer disabled-control + notice-driven tree updates).
- Remaining Wave 2/4 work: QueryClient, memo/lazy, further App split.

---

## Tests

| Suite | Result |
|---|---|
| `apps/wathefni-dashboard` vitest (18 files / 94 tests) | **PASS** |
| Includes `requestSafety.test.ts` | **PASS** |
| Includes Wave1 Overview scope-switch test | **PASS** |
| `tsc -b` + `vite build` | **PASS** |

### Orchestrator regressions (production host, 2026-07-30)

| Suite | Result |
|---|---|
| Multi-User Wave 6 final | **ALL CHECKS PASSED** |
| Calendar C6 static route/UX checks | **10 PASS** |
| Calendar C6 live DB proofs | Not re-run under systemd env in this pass (CLI without service env → `application_environment_missing_or_invalid`). Frontend Wave 1 does not change backend Calendar code. |

---

## Screenshots / recordings

No visual redesign. Wave 1 is interaction/plumbing. Evidence:

1. Automated request-path tests (boot + scope switch)
2. Build artifact `dist/assets/dashboard-*.js` (~679 KB)
3. Manual operator checklist:
   - Overview: click Company work → toggle never disables; title updates immediately; no “Refreshing hiring dashboard…” notice
   - Click My work again → prior items appear from cache without blanking
   - Calendar: switch week/month → grid does not disappear
   - Reports page first visit loads reports; Overview scope switch does not hit `/dashboard/prehire/reports`

---

## Rollback evidence

Wave 1 is frontend-only. Rollback:

1. Revert the listed dashboard files (or prior release artifact).
2. Redeploy previous `apps/wathefni-dashboard/dist`.
3. No DB migrations / API contract changes to undo.

Feature flags: none required.

---

## Wave 1 PASS/FAIL

### **PASS**

Stop criteria from audit Wave 1 met:

- [x] Overview scope decoupled from `refreshAll`
- [x] Calendar keeps previous events while fetching
- [x] Abort / generation protection on user-driven loads
- [x] Scope toggles not disabled for ordinary reads
- [x] Reports not loaded on unrelated refreshes/scope switches
- [x] Overview not blocked on Candidates/Interviews/Reports
- [x] Dashboard unit tests green; production build green

---

## Remaining Wave 2 items

1. Introduce **TanStack Query** as server-state layer
2. Default `staleTime` / `placeholderData` / dedupe across remounts
3. Prefetch opposite Overview scope + adjacent calendar ranges on hover/idle
4. Narrow mutation invalidation (replace broad `revalidatePrehire` fan-out)
5. Optional entity normalization for list↔drawer sharing

Later waves still open: boot/list strategy hardening (Wave 3), render/bundle split (Wave 4), backend work-queue specialization if needed (Wave 5).
