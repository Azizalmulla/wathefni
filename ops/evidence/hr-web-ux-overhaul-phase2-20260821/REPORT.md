# OctoHR HR Web Product UX Overhaul — Phase 2

**Shell lockstep + instant navigation foundation**  
As of 2026-08-21 · no visual redesign · no palette swap · no production deploy

Capability authority (unchanged): `workspaceCapability.ts` → backend `workspace_capability.py`  
Presentation catalog: `apps/wathefni-dashboard/src/lib/hrWebNavCatalog.ts`  
Coverage inventory: `apps/wathefni-dashboard/src/lib/hrWebSurfaceRegistry.ts`

This phase does **not** recreate business truth in the frontend. Modules, permissions, tenant isolation, and mutation honesty stay backend-canonical.

---

## Verdict

Phase 2 closes the eight broken enterprise destinations and makes the Surface Registry + `resolveWorkspaceAuthority` the destination allowlist. Entitled `?page=` deep links open directly. Disabled or unauthorized destinations still fail closed.

Navigation is faster on **return visits** because JS chunks stay cached and Suspense no longer paints a full-page skeleton when the chunk is already loaded. Pages still unmount when you leave them (no keep-every-page-alive). Query cache + URL state are the restore path.

Palette is unchanged.

---

## Before vs after (measured)

Phase 1 numbers are from `ops/evidence/hr-web-ux-overhaul-phase1-20260821/REPORT.md`. After numbers are from the Phase 2 source census, runtime explorer, and CJS/Python coverage gates on 2026-08-21.

| Metric | Before (Phase 1) | After (Phase 2) | How measured |
| --- | --- | --- | --- |
| Sidebar / catalog destinations | **26** `App.tsx` `navItems` | **34** catalog pages = capability nav | Python census `nav_ids()`; CJS `HR_WEB_SURFACE_CENSUS_PASS  34 pages, 34 nav items` |
| Capability pages missing from sidebar | **8** (`HR_WEB_SIDEBAR_COVERAGE_GAPS`) | **0** | Registry contract: `capabilityNotInSidebar === []` |
| Deep-link allowlist | `navItems.some(...)` (incomplete copy) | `isRegisteredDashboardPage` then `resolveWorkspaceAuthority.pageAllowed` | Source audit + runtime explorer |
| Entitled `?page=talent` (talent module + `talent.read`) | Lands on Overview; no Talent sidebar button | Sidebar lists Talent; `h1` is Talent | `hrWebSurfaceRuntimeExplorer.test.tsx` |
| `?page=talent` with talent **module off** | Also Overview (for the wrong reason) | Remaps away from Talent (fail closed) | Same runtime explorer |
| Disabled Interviews deep link | Remaps away (correct) | Unchanged | Existing runtime test |
| PostHire JS loading | One lazy import of `PostHire.tsx` | Dispatcher lazy-imports each workspace (`TalentWorkspace`, `LeaveWorkspace`, …). People-ops pages (Employees / Attendance / Payroll / …) stay in the core `PostHire.tsx` chunk. | `lazy.tsx` + `PostHireDispatcher.tsx` |
| Full-page skeleton on return visit | `fallback={<PageSkeleton />}` every switch | `PagePaintFallback` returns `null` when `pageChunkLoaded(page)` | Source audit; first visit still skeletons while the chunk downloads |
| Keep-alive of visited pages | None | None (intentional) | `hidden={activePage !==` still absent |
| Enterprise tabs / Settings / Leave view | `useState` only | URL-backed `?tab=` / Leave `?view=` | `useUrlBackedTab`; `buildDashboardSearchParams` writes tab/view |
| Hover prefetch | None | Chunk prefetch on pointerenter/focus; data prefetch only for jobs (empty filters), reports, calendar overview `mine` | `prefetchDashboardDestination` — does **not** prefetch applications from Overview |
| Overview sibling-list prefetch | Off (Wave 3) | Still off | `useDashboardServerState` unchanged |
| Optimistic payroll / leave | Forbidden | Still forbidden | Interaction-perf audit |
| Query freshness used as a speed score | Test QueryClient `staleTime: 0` (not a fair speed metric) | Same test client. Production `staleTime` is **30s** with `placeholderData: keepPreviousData` | `query/client.ts` vs `test/render.tsx` |

Refetch counts inside Vitest are **not** reported as a win: the test QueryClient forces `staleTime: 0`, so every mount refetches. Production already soft-keeps list paint via `keepPreviousData`. Enterprise workspaces still use local `useState` + fetch, so a Talent remount still does an in-page ResourceState load — not a full-page `PageSkeleton`.

---

## What changed

### 1. Shell lockstep (the eight SKUs)

`DASHBOARD_NAV_CATALOG` is derived from `WORKSPACE_SURFACES` (`kind === 'nav'`) plus icons. `App.tsx` no longer owns a second destination list.

The eight previously broken pages now appear in the sidebar when offerable:

`talent` · `learning` · `benefits` · `employee-relations` · `engagement` · `compensation-planning` · `workforce-planning` · `job-architecture`

Unknown `?page=` still starts at Overview. After bootstrap, `pageAvailableForSummary(..., workspaceAuthority.navIds)` remaps unauthorized / module-off pages to `defaultWorkspacePage` and shows the existing “not enabled” notice on click.

`HR_WEB_SIDEBAR_COVERAGE_GAPS` is now `[]`. The eight registry rows are `in_sidebar: true`, `migration_status: 'enterprise'`.

### 2. URL-backed workspace chrome

`useUrlBackedTab` restores:

- Settings sections (`?page=settings&tab=team`)
- Performance + the eight enterprise workspace tabs (`?tab=`)
- Leave `active` / `history` (`?page=leave&view=history`)

Refresh / back / forward restore that chrome. Unauthorized Settings sections still fall back in-page (visible-nav filter). Writes do not invent backend truth.

### 3. Lazy split + cached paint + prefetch

`LazyPostHirePage` loads `PostHireDispatcher`, which `React.lazy`s each workspace. Opening Talent no longer downloads Leave + Payroll + Employees first.

Return visits skip the full-page skeleton when the chunk is already in memory. Hover/focus prefetches the destination chunk. Data prefetch is limited to existing query keys with default filters (jobs / reports / calendar mine). Applications are not prefetched from Overview or from a guessed filter.

Pages still unmount on leave. That is the measured choice: Query cache + URL state, not a hidden stack of every module.

### 4. Contracts

The runtime explorer assertion that talent was **unreachable** is now a **correctness** assertion (opens + sidebar). Module-off talent remaps. Coverage contract requires catalog = capability and `navItems.some` gone.

Python smoke (`ops/e2e/web-hr-surface-census.py`) and dashboard `prebuild` CJS census parse the catalog + dispatcher.

---

## Preserved

- Backend modules + permissions remain the offerable oracle.
- Tenant `company_code` predicates unchanged.
- Mutations `retry: 0`; no optimistic payroll/leave success.
- Overview does not warm Candidates / Interviews / Assessments lists.
- Work-queue still opts out of `keepPreviousData`.
- `employee_app` stays excluded from HR nav.
- EN/AR + RTL shell, ResourceState honesty (failure ≠ empty).
- No palette change. `StatusPill` one-off hex remains a later token move.

---

## Not done (intentionally)

- No module visual redesign.
- No keep-alive of every visited page.
- Enterprise workspaces are not yet on TanStack Query (in-page loading on remount remains).
- Capability `settings.platform` vs Settings UI `advanced` naming drift is unchanged.
- Two ConfirmDialog implementations still exist.

Stop here. Do not start the visual overhaul.
