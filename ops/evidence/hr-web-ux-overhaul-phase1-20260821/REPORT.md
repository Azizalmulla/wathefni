# OctoHR HR Web Product UX Overhaul — Phase 1

**Automated Surface Census + interaction-performance audit**  
As of 2026-08-21 · no visual redesign · no production deploy

Source of truth: `apps/wathefni-dashboard/src/lib/hrWebSurfaceRegistry.ts`  
Capability authority (unchanged): `apps/wathefni-dashboard/src/lib/workspaceCapability.ts` → backend `workspace_capability.py`  
This phase does **not** recreate business truth in the frontend.

---

## Verdict

Phase 1 is an inventory and contract layer, not a reskin.

The authenticated HR Web app already has a strong shell, EN/AR + RTL, ResourceState (failure never looks empty), and a pre-hire TanStack Query cache. It is **not** instant-feeling yet because:

1. Eight entitled Post-Hire SKUs are missing from `App.tsx` `navItems`, so Setup deep links and `?page=` URLs fall back to Overview.
2. Most enterprise workspace tabs and all Settings sections are React state only — back/forward and deep links cannot restore them.
3. Every module switch unmounts the previous page and flashes `PageSkeleton` through `Suspense`.
4. `PostHire.tsx` is one lazy chunk, so the first post-hire visit pays for Leave + Payroll + Talent + … together.

Palette is **not frozen**. Semantic aliases (`--color-semantic-*`) now point at current tokens so a later central swap is possible.

---

## 1. Complete Surface Registry

The live registry is the TypeScript module above. Coverage contracts fail CI if a new Page, `navItems` id, PostHire `case`, `?page=` / `opsHref`, Settings section, workspace `Tab` union, or named Modal/Drawer/Dialog is added without a row (or an exclusion with a reason).

**Counts (locked by tests):** 34 `Page` union members, 26 sidebar items, ≥140 registry surfaces (pages + tabs + details + drawers/modals + overview actions + Setup + auth + aliases).

### 1.1 Authenticated pages

| surface_id | route | parent | module | permission | component | backend/API authority | EN/AR | RTL | responsive | loading/error/empty | migration |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| page.overview | `/dashboard?page=overview` | — | pre_hiring | candidate.manage \| jobs.create \| report.export | OverviewPage | `/dashboard/prehire/summary` + work-queue | EN/AR | yes | shell | yes | canonical |
| page.ai | `/dashboard?page=ai` | — | pre_hiring (+ post-hire) | several read/manage | AdminAIPage | `/dashboard/assistant` (not a second evaluator) | EN/AR | yes | shell | yes | preserve |
| page.jobs | `/dashboard?page=jobs` | — | pre_hiring | jobs.read | JobsPage + JobWorkspace | `/dashboard/prehire/positions` | EN/AR | yes | shell | yes | canonical |
| page.requisitions | `/dashboard?page=requisitions` | — | requisitions | requisitions.read | RequisitionsWorkspace | `/dashboard/prehire/requisitions` | EN/AR | yes | shell | yes | enterprise |
| page.candidates | `/dashboard?page=candidates` | — | pre_hiring | candidates.read | CandidatesPage | `/dashboard/prehire/applications` | EN/AR | yes | shell | yes | canonical |
| page.interviews | `/dashboard?page=interviews` | — | interviews \| video_interviews | prehire.read | InterviewsPage | `/dashboard/prehire/interviews` | EN/AR | yes | shell | yes | canonical |
| page.calendar | `/dashboard?page=calendar` | — | calendar | calendar.read | CalendarShell | `/dashboard/prehire/calendar` | EN/AR | yes | shell | yes | preserve |
| page.assessments | `/dashboard?page=assessments` | — | assessments | assessment.manage | AssessmentsPage | `/dashboard/prehire/assessments` | EN/AR | yes | shell | yes | canonical |
| page.ranking | `/dashboard?page=ranking` | — | pre_hiring | candidate.manage \| jobs.create \| report.export | RankingPage | `/dashboard/prehire/ranking` | EN/AR | yes | shell | yes | preserve |
| page.reports | `/dashboard?page=reports` | — | pre_hiring | report.export | ReportsPage | `/dashboard/prehire/reports` | EN/AR | yes | shell | yes | preserve |
| page.employees | `/dashboard?page=employees` | — | people spine | employees.read | EmployeesPage | `/dashboard/posthire/employees` | EN/AR | yes | shell | yes | canonical |
| page.workforce | `/dashboard?page=workforce` | — | people spine | employees.read | WorkforcePage | org projection on employees | EN/AR | yes | shell | yes | preserve |
| page.inbox | `/dashboard?page=inbox` | — | several post-hire | fail-closed offerable | ActionInboxPage | `/dashboard/posthire/action-inbox` | EN/AR | yes | shell | yes | preserve |
| page.preboarding | `/dashboard?page=preboarding` | — | preboarding | preboarding.read | PreboardingWorkspace | `/dashboard/posthire/preboarding` | EN/AR | yes | shell | yes | enterprise |
| page.onboarding | `/dashboard?page=onboarding` | — | onboarding | onboarding.read | OnboardingPage | `/dashboard/posthire/onboarding` | EN/AR | yes | shell | yes | canonical |
| page.probation | `/dashboard?page=probation` | — | probation | probation.read | ProbationWorkspace | `/dashboard/posthire/probation` | EN/AR | yes | shell | yes | enterprise |
| page.attendance | `/dashboard?page=attendance` | — | attendance | attendance.read | AttendancePage | `/dashboard/posthire/attendance` | EN/AR | yes | shell | yes | canonical |
| page.leave | `/dashboard?page=leave` | — | leave | leave.read | LeaveWorkspace | `/dashboard/posthire/leave` | EN/AR | yes | shell | yes | canonical |
| page.performance | `/dashboard?page=performance` | — | performance | performance.read | PerformanceWorkspace | `/dashboard/posthire/performance` | EN/AR | yes | shell | yes | preserve |
| page.talent | `/dashboard?page=talent` | — | talent | talent.read | TalentWorkspace | `/dashboard/posthire/talent` | EN/AR | yes | shell | yes | **broken deep link** |
| page.learning | `/dashboard?page=learning` | — | learning | learning.read | LearningWorkspace | `/dashboard/posthire/learning` | EN/AR | yes | shell | yes | **broken deep link** |
| page.benefits | `/dashboard?page=benefits` | — | benefits | benefits.read | BenefitsWorkspace | `/dashboard/posthire/benefits` | EN/AR | yes | shell | yes | **broken deep link** |
| page.employee-relations | `/dashboard?page=employee-relations` | — | employee_relations | er.read | EmployeeRelationsWorkspace | `/dashboard/posthire/employee-relations` | EN/AR | yes | shell | yes | **broken deep link** |
| page.engagement | `/dashboard?page=engagement` | — | engagement | engagement.read \| manager | EngagementWorkspace | `/dashboard/posthire/engagement` | EN/AR | yes | shell | yes | **broken deep link** |
| page.compensation-planning | `/dashboard?page=compensation-planning` | — | comp_planning | read \| manager | CompensationPlanningWorkspace | `/dashboard/posthire/comp-planning` | EN/AR | yes | shell | yes | **broken deep link** |
| page.workforce-planning | `/dashboard?page=workforce-planning` | — | workforce_planning | read \| manager | WorkforcePlanningWorkspace | `/dashboard/posthire/workforce-planning` | EN/AR | yes | shell | yes | **broken deep link** |
| page.job-architecture | `/dashboard?page=job-architecture` | — | (permission only) | job_architecture.read | JobArchitectureWorkspace | `/dashboard/posthire/job-architecture` | EN/AR | yes | shell | yes | **broken deep link** |
| page.shifts | `/dashboard?page=shifts` | — | shifts | shifts.read | ShiftsWorkspace | `/dashboard/posthire/shifts` | EN/AR | yes | shell | yes | canonical |
| page.payroll | `/dashboard?page=payroll` | — | payroll | payroll.read | PayrollPage | `/dashboard/posthire/payroll` | EN/AR | yes | shell | yes | canonical |
| page.analytics | `/dashboard?page=analytics` | — | analytics | analytics.read | IntelligenceWorkspace | `/dashboard/intelligence` | EN/AR | yes | shell | yes | enterprise |
| page.compliance | `/dashboard?page=compliance` | — | compliance | compliance.read | CompliancePage | `/dashboard/posthire/compliance` | EN/AR | yes | shell | yes | canonical |
| page.notifications | `/dashboard?page=notifications` | — | shared workspace | alerts manage | NotificationsPage | `/dashboard/prehire/notifications` | EN/AR | yes | shell | yes | preserve |
| page.activity | `/dashboard?page=activity` | — | — | audit.read | Activity | `/dashboard/audit` | EN/AR | yes | shell | yes | preserve |
| page.settings | `/dashboard?page=settings` | — | — | settings.manage \| users.manage | SettingsPage | `/dashboard/settings` + users | EN/AR | yes | shell | yes | preserve |

### 1.2 Nested / overlay / alias families (see registry file for each row)

- **URL tabs:** Candidates saved views (`all|active|talent_pool|hired|archived|restricted`); Interviews (`upcoming|needs_feedback|video_interviews|completed|all|no_show|cancelled`); Assessments (`send|resend|delivery_failed|in_progress|sent_pending|completed|attempts|reports|needs_review`).
- **Local-only enterprise tabs:** Performance, Talent, Learning, Benefits, Employee Relations, Engagement, Compensation Planning, Workforce Planning, Job Architecture (full `Tab` unions). Leave `active|history`. Attendance capture `connectors|mapping|missing|conflicts`.
- **Settings sections (local-only):** `account|team|company|communications|integrations|advanced`. Capability still names `settings.platform` — drift vs `advanced`.
- **Details:** Candidate profile (`?candidate=`), Job workspace (local selection).
- **Drawers/modals (all named TSX overlays):** Add/Edit/Import/Activation/Approver employee; AddToJob; Interview detail + action; Calendar event; Onboarding detail; Leave file + detail; Attendance import; Payroll export detail; shared ConfirmDialog (+ duplicate inside PostHire).
- **Overview actions:** review / assessment / follow-up / work queue (backend destination objects).
- **Setup Console:** `/setup-console` views `modules|policies|classic` (adjacent MPA; listed because Settings and ownership cards link here).
- **Legacy alias:** `?page=migration-sync` → `?page=employees&view=migration`.
- **Auth (excluded from product nav):** sign-in, invite acceptance.
- **Intentional exclusions:** `employee_app` (must never appear in HR nav); empty `futureModuleItems`; `setup-console.html` Vite entry.

---

## 2. Static vs runtime coverage

Static discovery (`hrWebSurfaceCensus.ts`) walks the dashboard source: `Page` union, `navItems`, PostHire `case` branches, `WORKSPACE_SURFACES` nav pages, `?page=` / `opsHref`, workspace `type Tab =`, Settings sections, named overlays.

Runtime explorer (`hrWebSurfaceRuntimeExplorer.test.tsx`) exercises the live shell with DOM/router/API assertions (no screenshots):

| Matrix | Result |
| --- | --- |
| Owner vs recruiter vs viewer | Recruiter/viewer cannot open talent, payroll, or settings; recruiter keeps jobs; viewer keeps leave.read. No permission leak in `resolveWorkspaceAuthority`. |
| Composition matrix (module combos) | Disabled modules stay off nav. Unchanged fail-closed behavior. |
| Disabled-module deep link `?page=interviews` with only `pre_hiring` | Remaps away from Interviews. Correct fallback. |
| Entitled deep link `?page=talent` with talent module + talent.read | **Capability says offerable; App drops it.** Sidebar has no Talent; heading never becomes Talent. Incorrect fallback to Overview. |
| EN / AR | `dir=rtl` + `lang=ar` on the signed-in document. |
| Desktop 1440 / laptop 1280 / smaller 768 | `app-shell`, `app-sidebar`, `app-main` present at each width. |
| Back after Jobs | `popstate` + `readDashboardNavState` restores Overview (URL-backed pages only). |

---

## 3. Orphan / dead / duplicate / broken destinations

### P0 — broken deep links / sidebar orphans (locked as `HR_WEB_SIDEBAR_COVERAGE_GAPS`)

These exist in the `Page` union, `WORKSPACE_SURFACES`, PostHire dispatcher, labels/subtitles, and Setup `opsHref`, but **not** in `App.tsx` `navItems`. Initial state and `applyNavStateToUi` both gate on `navItems.some(...)`, so the URL is ignored:

`talent` · `learning` · `benefits` · `employee-relations` · `engagement` · `compensation-planning` · `workforce-planning` · `job-architecture`

Runtime proof: talent module on + `?page=talent` still lands on Overview.

### P1 — local-only surfaces (dead as deep links)

- All enterprise workspace tabs listed in §1.2.
- Settings sections (back cannot restore Team vs Account).
- Selected job in JobWorkspace.
- Open drawers/modals.

### P1 — duplicate / drift

- Two `ConfirmDialog` implementations (`components/ConfirmDialog.tsx` and a local copy in `PostHire.tsx`).
- Capability `settings.platform` vs Settings UI `advanced`.
- `App.tsx` `navItems` is a second, incomplete copy of `WORKSPACE_SURFACES`.

### Not dead

- `migration-sync` is a deliberate alias, not a missing page.
- `employee_app` is correctly excluded from HR nav.
- Disabled-module Interviews remap is correct (not a leak).

---

## 4. Performance / jank findings

Do **not** fake mutation success. Payroll, leave, and other writes stay backend-canonical (`QueryClient` mutations `retry: 0`; no optimistic payroll path).

| Finding | Evidence | Instant-feeling impact |
| --- | --- | --- |
| Full-page skeleton on every lazy switch | `App.tsx` `fallback={<PageSkeleton />}` + `{activePage === 'x' && (` | Flash on every module change, including return visits |
| No keep-alive | Pages unmount; no `hidden={activePage !==}` cache | State loss; refetch; no cached paint |
| One PostHire chunk | `lazy.tsx` imports only `@/posthire/PostHire` | First post-hire visit downloads every workspace |
| Pre-hire cache is already good | `placeholderData: keepPreviousData`; Overview does not enable applications/interviews/assessments/jobs queries | Overview itself is closer to instant; sibling lists stay cold until opened |
| Work-queue correctly opts out of keepPreviousData | Wrong-scope rows would flash My vs Company | Keep this exception |
| Visibility refetch | `FRESHNESS_MS` 60–120s, paused when hidden | Good; do not add tighter polls for “snappiness” |
| Local tabs | `useState<Tab>` in workspaces | Back cannot restore; feels like a remount |
| Remaining layout/token hex | `StatusPill` neutral `bg-[#eee5d4]` | CLS-adjacent inconsistency when swapping palette later |
| `scrollTo` on Overview restore | Present; jsdom cannot prove CLS | Keep scroll restore; do not add layout-shifting skeletons on refresh |

**Already preserve:** Rendering Stability Wave 2 (`isColdLoad` / `isSoftRefreshing`), Overview not warming Candidates, `dashboardPerf` marks, tenant query clear on company change.

---

## 5. Shared UX / design-system findings

Disposition is in `hrWebUxInventory.ts`. Summary:

| Family | Preserve | Consolidate | Replace later |
| --- | --- | --- | --- |
| App shell / sidebar | Viewport-locked shell, 3 groups, RTL dir | Derive `navItems` from the registry | — |
| Headers | Page personalities | App `h1` vs `PageIntro` duplication | — |
| Actions | Shared `Button` pending | — | — |
| Tabs | Interviews/Assessments URL tabs | — | Put enterprise tabs on the same URL contract |
| Search/filters | `dashboardNavigation` URL keys | — | Extend to post-hire |
| Tables/lists | List IA | Ad-hoc tables + hex cream | Shared table later, not this phase |
| Cards | `SoftKeepSurface` | — | — |
| Forms | `field.tsx` | Raw inputs in some workspaces | — |
| Drawers/modals | Shared ConfirmProvider | Delete PostHire-local confirm | — |
| Status | `StatusPill` / `Badge` | One leftover hex on neutral pill | Adopt `--color-semantic-*` |
| Loading/error/empty/unavailable | `ResourceState` EN+AR, fail ≠ empty | — | Replace full-page `PageSkeleton` with cached paint |

Semantic tokens added in `index.css` as **aliases only** (`var(--color-wf-*)` / `var(--color-accent)`). Contract: they must not contain hex. Current OctoHR palette is not frozen.

---

## 6. Recommended shell + interaction architecture

Keep backend authority, modules, permissions / `allowed_actions`, tenant isolation, and current auth/resource-state. Frontend stays a projection.

1. **Single destination list.** `navItems` and deep-link allowlisting should be derived from the Surface Registry + `resolveWorkspaceAuthority` (already the offerable oracle). Delete the `navItems.some` gate.
2. **URL is the workspace.** Page, tab, selected record, and filters belong in `dashboardNavigation` (query keys). Local `useState<Tab>` is the exception to retire, not the pattern to copy.
3. **Cached shell.** Keep the current `app-shell` / sidebar / main split. Keep visited pages mounted and hidden (or restore from React Query) so return visits paint from cache, then soft-refresh. `PageSkeleton` only on true cold load (`!data`).
4. **Split PostHire by module** (`React.lazy` per workspace) so Leave does not download Talent.
5. **Prefetch on hover/intent** of sidebar items using existing query keys — prefetch, do not guess mutation results.
6. **One overlay system.** ConfirmProvider + a single drawer chrome. Module drawers stay, shared motion/width/RTL.
7. **Palette swap later** by retargeting `--color-wf-*` and `--color-accent` only. Components should migrate onto `--color-semantic-*` without changing look in this phase.

---

## 7. Systematic migration order

Do **not** start visual redesign in the next slice. Order is interaction correctness, then perceived speed, then (later) visual consolidation.

0. **Shell lockstep (Overview + every module reachable)** — add the eight SKUs to nav from the registry; honor `?page=` when capability says offerable. This unblocks Setup Console links. No new colors.
1. **Overview** — keep Wave 2/3 cache; replace Suspense flash on return; keep work-queue scope opt-out.
2. **Leave, Attendance, Shifts, Payroll** — operational landing priority; URL-state for leave active/history; keep payroll mutations honest.
3. **Onboarding, Preboarding, Probation, Employees, Organization, Inbox** — people spine; keep drawers; add `?employee=` / case ids where missing.
4. **Compliance, Analytics/Intelligence** — enterprise, preserve methodology copy.
5. **Performance → Talent → Learning → Benefits → ER → Engagement → Comp planning → Workforce planning → Job architecture** — put `Tab` unions on `?tab=` so back works; then shared tab chrome.
6. **Jobs, Candidates, Interviews, Assessments, Calendar, Ranking, Reports, Assistant** — already closer to the target; adopt semantic tokens; keep-alive.
7. **Settings, Alerts & Delivery, Activity** — URL sections; align `advanced` with capability `platform`.
8. **Visual overhaul (later phase)** — only after destinations and cached paint are honest. Palette change is a token retarget, not a page-by-page restyle.

---

## 8. Automated contracts added

| Contract | Where | What fails |
| --- | --- | --- |
| Surface Registry coverage | `apps/wathefni-dashboard/src/lib/hrWebSurfaceRegistry.contract.test.ts` | New Page / nav / PostHire case / `?page=` / Settings section / workspace Tab / named overlay not in the registry |
| Static census | `apps/wathefni-dashboard/src/lib/hrWebSurfaceCensus.ts` | Discovery helpers used by the contract |
| Sidebar gap lock | same contract + `HR_WEB_SIDEBAR_COVERAGE_GAPS` | Gap list drifting without an explicit update (fixing the eight SKUs requires updating this list) |
| Runtime explorer | `hrWebSurfaceRuntimeExplorer.test.tsx` | Permission leak, disabled-module leak, talent deep-link regression (currently asserts the bug), EN/AR, widths, back |
| Interaction perf | `hrWebInteractionPerf.audit.test.ts` | Accidental keep-alive claims, PostHire split, optimistic payroll, Overview prefetch of sibling lists |
| Semantic tokens | `semanticColorContract.test.ts` + `index.css` | Semantic aliases freezing hex |
| UX inventory families | registry contract | Missing a required UX family |
| Smoke | `ops/e2e/web-hr-surface-census.py` + `ops/test-smoke` | Registry file missing or Page/nav/PostHire/`?page=` uncovered |
| Prebuild | `ops/full-web-e2e/run-hr-web-surface-census.cjs` | Same coverage at dashboard `npm run build` |

`npm test` in `apps/wathefni-dashboard` is the developer loop. `./ops/test-smoke` now runs the Python census plus the registry + perf Vitest files.

---

## Out of scope (this phase)

- No page visual redesign, no production deploy, no KPI/math changes, no second permission model, no optimistic mutation of backend-owned calculations.
- The eight sidebar SKUs are **found and locked**, not silently patched here, so Phase 2 can fix them as a dedicated shell-lockstep slice.
