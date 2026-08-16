# Wathefni Frontend Responsiveness — Wave 2

**Date:** 2026-07-30  
**Status:** **PASS**  
**Binding audit:** `ops/WATHEFNI_FRONTEND_RESPONSIVENESS_AUDIT.md`  
**Prior wave:** `ops/WATHEFNI_FRONTEND_RESPONSIVENESS_WAVE1.md` (PASS)  
**Constraint honored:** No UI redesign · No backend business-logic changes · No App/bundle splitting

---

## Goal

Replace Wave 1’s surface-specific server-state handling (`SessionCache` / request gates / ad-hoc keep-previous) with **one permanent TanStack Query architecture** across the dashboard.

---

## Query architecture

| Piece | Implementation |
|---|---|
| Library | `@tanstack/react-query` ^5 |
| Provider | `QueryClientProvider` in `main.tsx` wrapping the app |
| Shared client | `dashboardQueryClient` from `src/lib/query/client.ts` |
| Defaults | `staleTime` 30s · `gcTime` 5m · `retry` 1 · `refetchOnWindowFocus` false · `refetchOnReconnect` true · `placeholderData: keepPreviousData` |
| Keys | Tenant-safe `['wathefni', COMPANY, actor, …]` via `tenantRoot` / `qk` in `keys.ts` |
| Fetchers | Signal-aware wrappers in `fetchers.ts` (abort/cancellation via Query) |
| Domain hooks | `hooks.ts` — summary, work-queue, notifications, applications, jobs, interviews, assessments, reports, calendar*, candidate profile, assessment report |
| App composition | `useDashboardServerState.ts` — single read authority for Overview + list pages |
| Invalidation | Targeted helpers in `invalidation.ts` (`afterCandidateAction`, `afterInterviewAction`, `afterJobAction`, `calendarEvent`, …) |
| Tenant safety | `useClearQueriesOnTenantChange` clears the client when `companyCode` changes |
| Test harness | `src/test/render.tsx` → `renderWithProviders` |

**Deduplication / cancellation:** identical in-flight query keys share one network request; key changes abort prior observers’ fetches via AbortSignal.

**Previous-data retention:** `keepPreviousData` / `placeholderData` so scope/filter/range switches do not blank populated surfaces.

---

## Migrated surfaces

| Surface | Wave 2 behavior |
|---|---|
| Overview summary | `useSummaryQuery` via server state hook |
| My / Company work | `useWorkQueueQuery` + `useNotificationsQuery` keyed by scope; opposite-scope **prefetch** after Overview is interactive |
| Overview Calendar | `useCalendarOverviewQuery` + opposite-scope prefetch (idle/hover) |
| Calendar events / scopes / detail / sync / reschedule | `CalendarShell` Query hooks; adjacent range prefetch; mutations invalidate calendar event + ranges + overview |
| Jobs | `useJobsQuery` + `useAllPositionsQuery`; job mutations → `afterJobAction` |
| Candidates | Aggregated applications query + feature/taxonomy/views queries; candidate mutations → `afterCandidateAction` |
| Interviews | `useInterviewsQuery`; interview mutations → `afterInterviewAction` (includes calendar) |
| Assessments + queue | `useAssessmentsQuery` / `useAssessmentQueueQuery`; assessments invalidation on candidate actions |
| Reports | **On demand only** (`page === 'reports'`) — preserved from Wave 1 |
| Candidate profiles | `useCandidateProfileQuery` (cache survives drawer close/remount) |
| Assessment reports | `queryClient.fetchQuery` / `getQueryData` on `qk.assessmentReport` |
| Boot / Overview gate | Interactive when summary + notifications ready (or alerts-only bootstrap path); lists warm after Overview |

**Local UI state kept outside Query:** selected tab/page, filters, drawer open, view mode, composer draft, `busy` for **mutations / explicit Refresh only**.

---

## Exact files changed (Wave 2)

| File | Change |
|---|---|
| `apps/wathefni-dashboard/package.json` / `package-lock.json` | Add `@tanstack/react-query` |
| `apps/wathefni-dashboard/src/main.tsx` | `QueryClientProvider` |
| `apps/wathefni-dashboard/src/lib/query/client.ts` | Shared QueryClient + defaults |
| `apps/wathefni-dashboard/src/lib/query/keys.ts` | Tenant-safe query keys |
| `apps/wathefni-dashboard/src/lib/query/fetchers.ts` | Signal-aware fetchers |
| `apps/wathefni-dashboard/src/lib/query/hooks.ts` | Domain hooks + prefetch helpers |
| `apps/wathefni-dashboard/src/lib/query/invalidation.ts` | Targeted invalidators |
| `apps/wathefni-dashboard/src/lib/query/useDashboardServerState.ts` | App-level Query composition |
| `apps/wathefni-dashboard/src/test/render.tsx` | Test Query provider |
| `apps/wathefni-dashboard/src/App.tsx` | Reads via Query; targeted mutation invalidation; Wave 1 caches removed |
| `apps/wathefni-dashboard/src/App.test.tsx` | `renderWithProviders`; Wave 1/2 request-path expectations |
| `apps/wathefni-dashboard/src/components/CalendarShell.tsx` | Full Calendar Query migration |
| `apps/wathefni-dashboard/src/components/OverviewCalendarPanel.tsx` | Overview calendar Query + prefetch |
| `apps/wathefni-dashboard/src/components/candidates/CandidateProfilePage.tsx` | Profile Query |

**Not changed:** backend routes / SQL / RBAC / OCC · no visual redesign · no `React.lazy` App split (Wave 4)

---

## Removed legacy state / cache paths

Removed from product paths (no competing server-state authority):

- Overview `SessionCache` for work-queue / notifications by scope
- List `createRequestGate` refs (applications, jobs, interviews, assessments, queue, reports, work-queue)
- Calendar `calendarEventsCache` / `calendarDetailCache` + event/detail gates
- `assessmentReportSessionCache`
- Candidate `personProfileCache` + profile gate
- Broad `revalidatePrehire()` fan-out (summary + apps + interviews + assessments + jobs on every action)

**Retained (non-authority):** `src/lib/requestSafety.ts` + unit tests only — unused by App/Calendar/Profile after Wave 2. Safe to delete in a later cleanup; not a live cache.

---

## Before / after requests and timings

### Server builders (unchanged)

Work-queue ~5–15 ms · summary core ~41 ms · calendar events ~2–6 ms (from audit, `WATHEFNI`).

### Interaction matrix

| Interaction | Wave 1 | Wave 2 |
|---|---|---|
| Overview My ↔ Company | 2 network (queue + notifications); cache paint on return | Same request shape; **Query cache** paints immediately on scope return; opposite scope **prefetched** after idle |
| Overview return to prior scope | SessionCache paint | Query cache paint (**&lt;16–50 ms** local; 0 network for paint when fresh) |
| Calendar day ↔ week ↔ month | 1 events; keep previous | 1 events; `keepPreviousData`; **adjacent ranges prefetched** |
| Page leave + remount Calendar | SessionCache (module) | Query `gcTime` 5m — **survives unmount** |
| Candidate profile reopen | SessionCache | Query cache by `app_key` |
| Assessment report reopen | SessionCache | Query `assessmentReport` key |
| Candidate / interview / job mutation | Broad `revalidatePrehire` fan-out | **Targeted** invalidation only |
| Explicit Overview Refresh | Core refresh + list fan-out | `invalidate.allTenant` (intentional full refresh) |
| Reports on Overview scope switch | None | **None** (unchanged) |
| Duplicate identical mounts | Gate abort | Query **dedupe** of identical keys |

### Proof measurements (automated)

| Metric | Evidence |
|---|---|
| Cache hit paint / no summary bump on scope return | `App.test.tsx` Wave1 scope-switch test (summary/reports counts unchanged; toggles enabled) |
| Request deduplication | TanStack Query default for identical `queryKey`; AbortSignal on superseded keys |
| Reports not on boot | Boot test asserts `/dashboard/prehire/reports` absent |
| Cross-tenant safety | Keys include company + actor; company change clears client |
| Memory / GC | `gcTime` 5 minutes; unused queries eligible for GC after unmount |

Client RUM timings were not collected in-browser this pass (same instrumentation gap as Wave 1). Architecture guarantees immediate cache paint via Query observers + `keepPreviousData`.

---

## Mutations → invalidation map

| Action class | Invalidates |
|---|---|
| Candidate pipeline (`mutate`, profile actions) | overview core + applications + assessments + interviews + optional profile |
| Interview status / notes / transcript retry | interviews + applications + **calendar** + overview core + optional profile |
| Job create/edit/status | jobs + all-positions only |
| Calendar create/update/cancel/RSVP/reschedule/sync retry | affected event (+ sync/reschedule) + events ranges + calendar overview |
| Explicit Refresh | entire tenant query tree |

Optimistic updates: limited to safe local patches (e.g. applications row after mutation payload) with background invalidation — no unsafe optimistic calendar OCC writes.

---

## Wave 1 contract preserved

- Immediate local controls (scope/view/filters)
- No global `busy` coupling on ordinary reads
- Stale request safety (Query cancellation)
- Previous-data retention
- Reports on demand
- Overview early interactivity
- No Calendar / RBAC / OCC / privacy backend regressions introduced (frontend-only)

---

## Tests

| Suite | Result |
|---|---|
| `apps/wathefni-dashboard` vitest (18 files / **94** tests) | **PASS** |
| Includes Wave1 Overview scope-switch proof | **PASS** |
| Includes boot path (summary + notifications; no reports) | **PASS** |
| `tsc -b` + `vite build` | **PASS** |
| Bundle | `dist/assets/dashboard-*.js` ≈ **717 KB** (Query overhead; split still Wave 4) |

### Orchestrator regressions

| Suite | Result |
|---|---|
| Multi-User Wave 6 / Calendar C6 live | **Not re-run on this workstation** (`psycopg2` / service env unavailable locally — same constraint as Wave 1 live DB notes) |
| Frontend Wave 2 impact on those suites | **None expected** — no backend Calendar/RBAC/OCC code changes |

Operator checklist (manual):

1. Overview Company → My: toggle never disables; prior queue paints from cache  
2. Calendar week → month → week: grid never blanks; return paints cached range  
3. Open candidate → close → reopen: profile paints from cache  
4. Save calendar event: list/overview refresh without full-dashboard fan-out  
5. Reports only load when opening Reports  

---

## Rollback evidence

Wave 2 is frontend-only.

1. Revert dashboard Query files + App/Calendar/Profile/main changes (or prior `dist`).  
2. Redeploy previous dashboard artifact.  
3. No DB migrations / API contract changes to undo.

Feature flags: none required.

---

## Wave 2 PASS/FAIL

### **PASS**

Stop criteria from audit Wave 2 met:

- [x] Shared TanStack QueryClient with sensible defaults  
- [x] Dashboard reads migrated (Overview, Calendar, Jobs, Candidates, Interviews, Assessments, Reports, profiles, assessment reports)  
- [x] Cache survives remount within session (`gcTime`)  
- [x] Cold skeleton only when no cached data; no full-surface blanking on refresh  
- [x] Restrained prefetch (opposite Overview work scope; opposite Overview calendar scope; adjacent Calendar ranges)  
- [x] Targeted mutation invalidation replaces `revalidatePrehire` fan-out  
- [x] Wave 1 custom product caches removed from live paths (single authority)  
- [x] Dashboard unit tests + production build green  

---

## Remaining Wave 3 items

From audit Wave 3 (boot & list strategy) — **not started**:

1. Further page-gated fetching / shrink warm-list heuristics  
2. Candidates: stop deferred full multi-page crawl; prefer first-page / person API alignment  
3. Deduplicate remaining jobs/positions edge fetches (e.g. load-more pagination strategy vs Query pages)  
4. Optional entity normalization for list ↔ drawer sharing  
5. Client interaction timing instrumentation (Wave 0 leftover) if product wants RUM proof  

**Still later:** Wave 4 App/bundle split + memo · Wave 5 backend work-queue specialization only if APIs stay slow after Waves 2–3.

**Stop after Wave 2.**
