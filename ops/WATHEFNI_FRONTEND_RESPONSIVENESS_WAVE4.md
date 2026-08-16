# Wathefni Frontend Responsiveness — Wave 4

**Date:** 2026-07-30  
**Status:** **PASS**  
**Binding audit:** `ops/WATHEFNI_FRONTEND_RESPONSIVENESS_AUDIT.md`  
**Prior waves:** Wave 1–3 PASS  
**Constraint honored:** No UI redesign · No backend business-logic changes · Query authority unchanged (except import boundaries)

---

## Goal

Reduce initial bundle size and unnecessary React work by splitting the dashboard into maintainable route/page islands with `React.lazy` / `Suspense`, while preserving TanStack Query as the single server-state authority.

---

## New component / module structure

```
apps/wathefni-dashboard/src/
  App.tsx                         # Shell: nav, auth, Query wiring, page switch (~2.7k lines)
  pages/
    lazy.tsx                      # React.lazy registry for heavy routes
    PageSkeleton.tsx              # Stable Suspense fallback (no full-app blank)
    OverviewPage.tsx              # Eager (first paint)
    CandidatesPage.tsx            # Lazy
    JobsPage.tsx                  # Lazy (+ qrcode dependency)
    InterviewsPage.tsx            # Lazy (+ memo InterviewQueueRow)
    AssessmentsPage.tsx           # Lazy (+ AssessmentReport / Product2)
    RankingPage.tsx               # Lazy
    ReportsPage.tsx               # Lazy
    SettingsPage.tsx              # Lazy (admin/mailbox/integrations)
    NotificationsPage.tsx         # Lazy
    AdminAIPage.tsx               # Lazy
    ShellStates.tsx               # Eager boot: AccessVerification / Loading / NeedsSettings
    shared/
      access.ts                  # Permission helpers
      format.ts                  # Labels / errors / ranking helpers
      primitives.tsx             # EmptyState / Info / MetricGrid / ScoreBreakdown
  components/
    CalendarShell.tsx             # Lazy via lazy.tsx
    candidates/CandidateProfilePage.tsx  # Lazy drawer
    JobWorkspace.tsx              # Lazy
  posthire/PostHire.tsx           # Lazy page + delivery center
```

**Centralized in `App.tsx`:** navigation, tenant access, permissions, notices, mutations, `useDashboardServerState` / QueryClient usage, URL nav state.

---

## Exact files changed (Wave 4)

| Area | Files |
|---|---|
| Shell | `src/App.tsx` (pages extracted; Suspense islands) |
| Pages | `src/pages/*` (new module tree above) |
| Build | `vite.config.ts` — `manualChunks` for `react-vendor`, `react-query`, `lucide` |
| Memo | `CandidatesTable.tsx` (`CandidateTableRow` memo) · `InterviewsPage.tsx` (`InterviewQueueRow` memo) |
| Tests | `src/lib/lifecycle-labels.test.ts` (interview `allowed_actions` now in `InterviewsPage.tsx`) |
| Cleanup | Removed unused Wave 1 `requestSafety` product path (already unused after Wave 2/3) |

**Not changed:** backend · Query keys/defaults/invalidation semantics · visual design language

---

## Bundle comparison

| Artifact | Wave 3 (before) | Wave 4 (after) |
|---|---:|---:|
| Main `dashboard-*.js` | **723 KB** | **200 KB** (−72%) |
| React vendor chunk | (inlined) | **182 KB** (shared, cached across routes) |
| React Query chunk | (inlined) | **25 KB** |
| Lucide chunk | (inlined) | **25 KB** |
| Calendar route | in main | **42 KB** on demand |
| Assessments route | in main | **48 KB** on demand |
| Candidate profile | in main | **45 KB** on demand |
| Post-hire modules | in main | **149 KB** on demand |
| Reports | in main | **6 KB** on demand |
| Settings | in main | **21 KB** on demand |

**Initial Overview path (approximate transferred JS):**  
`dashboard` + `react-vendor` + `react-query` + `lucide` (+ CSS) — **without** Calendar / Assessments / Reports / Settings / PostHire / Profile chunks.

**Proof of on-demand:** those route files exist as separate `dist/assets/*Page*.js` / `CalendarShell-*.js` / `PostHire-*.js` and are only referenced via `import()` from `pages/lazy.tsx`.

---

## Loading behavior

- Nav / aside / shell remain mounted during lazy load.
- Suspense fallback = `PageSkeleton` (lightweight pulse cards) — **no full-dashboard blank**.
- Overview is **eager** so first interactive paint does not wait on a page chunk.
- Query cache lives on the root `QueryClientProvider` → survives lazy unmount/remount; cached revisits still paint immediately after the chunk resolves.
- Navigation state / drafts remain in App shell state (unchanged).

---

## Rerender comparison

| Change | Effect |
|---|---|
| Page islands only mount when `activePage` matches | Unrelated page trees are not in the React tree |
| `CandidateTableRow` / `InterviewQueueRow` memo | Row churn reduced when parent list re-renders with stable row props |
| No blanket `memo` on every component | Avoided false confidence / prop-thrash |

Automated React Profiler counts were not collected in a browser session this pass; structural isolation (unmount inactive pages) is the primary rerender win. Operator can confirm in React DevTools Profiler: switch Overview → Calendar → Overview and note Calendar tree absent on Overview.

---

## Query preservation

- One `dashboardQueryClient` / `QueryClientProvider` in `main.tsx` (unchanged).
- Lazy pages consume the same hooks/keys; no second QueryClient.
- Tenant-safe keys + targeted invalidation unchanged from Wave 2/3.
- Cache survives route chunk remount (`gcTime` still 5m).

---

## Measurement / instrumentation

Wave 3 `window.__WATHEFNI_DASHBOARD_PERF__` remains available for:

- Overview interactive time  
- Page first-load vs cached-return  
- Request counts  

Wave 4 adds bundle/chunk evidence above. Memory: PostHire/Calendar no longer permanently resident after leaving those routes (eligible for GC with their chunks’ module state); Query cache retention is intentional and tenant-scoped.

---

## Tests

| Suite | Result |
|---|---|
| `apps/wathefni-dashboard` vitest (**18** files / **94** tests) | **PASS** |
| `tsc -b` + `vite build` | **PASS** |
| Lifecycle contract test updated for Interviews extraction | **PASS** |

---

## Rollback evidence

Frontend-only.

1. Revert `App.tsx` + `src/pages/**` + `vite.config.ts` manualChunks (or redeploy prior `dist`).  
2. No DB / API / Query contract rollback required.

Feature flags: none.

---

## Wave 4 PASS/FAIL

### **PASS**

Stop criteria met:

- [x] `App.tsx` split into page islands; shell remains centralized  
- [x] Heavy pages lazy-loaded (Calendar, Assessments, Reports, Settings, Candidates, Interviews, Jobs, Ranking, AI, PostHire, Profile, JobWorkspace)  
- [x] Overview loads without downloading those heavy page chunks  
- [x] Stable page skeletons; no full-dashboard blanking  
- [x] Query cache survives remount; single QueryClient  
- [x] Main bundle **723 KB → 200 KB**  
- [x] Dashboard tests + build green  

---

## Is Wave 5 backend work needed?

**Not required from Wave 4 evidence.**

Waves 1–4 fixed frontend interaction architecture, caching, boot fan-out, list crawling, and bundle weight. On the evidence tenant, Overview/Calendar builders were already single-digit to low tens of ms.

Revisit Wave 5 **only if** production RUM / Wave 3 perf snapshots still show:

1. `work-queue?scope=mine` wall time growing with company queue size, or  
2. Candidates person-aggregation needing a true person-page API beyond first-page apps, or  
3. Calendar event volume making projection SQL slow.

Until then, **stop after Wave 4**.
