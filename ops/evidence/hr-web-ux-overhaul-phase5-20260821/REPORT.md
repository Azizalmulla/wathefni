# OctoHR HR Web Product UX Overhaul — Phase 5

**People Spine UX Migration**  
As of 2026-08-21 · Employees, Employee 360, Organization, Onboarding, Preboarding, Probation, Action Inbox (Needs Attention) · no Recruiting / remaining enterprise / Settings restyle · no palette freeze · no production deploy

---

## Verdict

The People batch now shares the Phase 3/4 chrome language (canonical `HrPageHeader`, surface tabs, section surfaces, ResourceState, semantic tokens, URL-backed operator chrome) **without** collapsing each workflow into one table or inventing employee/employment/org/approvals rules in the frontend.

Shared employee / employment / org truth, `allowed_actions`, module entitlements, and lifecycle remain backend-canonical. Mutations still wait for the server. Cached paint + soft refresh is preserved: return visits do not flash a full-page skeleton.

---

## UX changes by surface

### Employees

- Shell uses `HrPageHeader` (`density=page`). Directory is `HrSection` with Add employee (primary), Migration & Sync (secondary), and ghost refresh.
- Search, employment status, department, and onboarding filters stay the same workflow; they are now URL-backed.
- Opening a row still goes to Employee 360. Mobile cards + desktop table remain. Empty/manage/read states are unchanged in meaning.
- Cold load uses `ResourceState`; refetch keeps painted rows (`SoftKeepSurface`). Directory hex chrome moved onto semantic tokens.

### Employee 360

- Canonical employee record. Identity header is `HrPageHeader` (h2) with bilingual employment actions. Jump nav (`HrAnchorNav`) scrolls to existing section ids — it does not add data.
- Record order of travel: identity → next actions → employment (app access) → org assignment → bank (payroll-accessible) → onboarding → attendance / leave / shifts → payroll → documents. Module cards still only present backend-published `sections.*`.
- Mutating onboarding/leave/attendance/payroll/shifts still routes to the owning module (`Open in …`). Profile next-actions stay backend-ranked; onboarding mutates stay demoted.
- Soft-keep on return/refetch. EN/AR coverage for the identity chrome and section titles.

### Organization (workforce)

- Duplicate inner page title removed (shell owns it). Structure remains first paint; Advanced administration stays behind the toggle.
- Unit hierarchy is still not manager reporting lines. `?tab=` is URL-backed; legacy `?workforce=` still restores the same Advanced section.
- Permission gates (`employees.read` / `employees.manage` / status approve) unchanged.

### Onboarding

- Queue-first IA preserved: filters, one primary action + More menu, checklist drawer, mutation handshake.
- Filter, search (`?q=`), and `?employee=` checklist focus are URL-backed. Soft-keep on the queue. Filter chips are `HrSurfaceTabs` using existing queue counts.

### Preboarding

- Frozen preboarding authority unchanged (create / start / waive / remind / joining date still hit the same APIs).
- Duplicate inner h1 removed. Status filter is `HrSurfaceTabs` with published `counts.*`. Selected joiner is URL-backed (`?employee=`). Queue no longer blanks on filter/refresh.

### Probation

- Frozen probation authority unchanged (recommend / decide / extend / milestones).
- Duplicate inner h1 removed. Status chips are `HrSurfaceTabs` with published `counts.*`. Selected case is URL-backed (`?employee=`). Soft-keep on the queue.

### Action Inbox (Needs Attention)

- Still a cross-module routing surface: ranked `items` from `/dashboard/posthire/action-inbox`, deep-link to the owning module, no in-page resolve, no client regrouping of grouped document cases.
- Presentation filters (`needs_action` / `due_soon` / `blocked` / `all`) are URL-backed (`?tab=`). The All title uses published `summary.total` when the backend sends it. Filter chip counts remain the existing presentation sizes of the ranked list — not a new approvals total.
- Soft-keep + honest partial/stale/source-error banners (tokenized).

---

## Shared primitives added / changed

| Primitive | Change |
| --- | --- |
| `HrAnchorNav` | **New.** In-page jump links; 150ms color only; scrolls to existing ids. |
| `HrPageHeader` | People spine uses `density=page` from the shell (`isPeopleSpinePage`). 360 uses h2, no extra border. |
| `useUrlBackedParam` | **New.** Free-form URL chrome (`q`, `department`, `employee`). |
| `useUrlBackedTab` | People tabs: workforce, onboarding, preboarding, probation, inbox; employees `view` / `status` / `onboarding`. |
| `HrSurfaceTabs` / `HrSection` / `SoftKeepSurface` / `ResourceState` | Reused. |

Reused `Button` for mutations. Final colors remain unfrozen (semantic tokens only).

---

## Deep-link / URL state

| Surface | URL |
| --- | --- |
| Employees directory search | `?page=employees&q=` |
| Employment status | `?page=employees&status=left\|all` (default active omitted) |
| Department | `?page=employees&department=` |
| Onboarding filter | `?page=employees&onboarding=open\|complete\|not_started` |
| Employee 360 | `?page=employees&employee={key}` (push so back returns to the directory) |
| Migration Sync | `?page=employees&view=migration` (legacy `?page=migration-sync` still aliases) |
| Organization section | `?page=workforce&tab=organization\|lifecycle\|…` (legacy `?workforce=` still read) |
| Onboarding queue filter | `?page=onboarding&tab=needs_attention\|…` |
| Onboarding checklist | `?page=onboarding&employee={key}` |
| Onboarding search | `?page=onboarding&q=` |
| Preboarding status | `?page=preboarding&tab=all\|blocked\|ready\|…` |
| Preboarding joiner | `?page=preboarding&employee={key}` |
| Probation status | `?page=probation&tab=attention\|active\|…` |
| Probation case | `?page=probation&employee={key}` |
| Needs Attention filter | `?page=inbox&tab=needs_action\|due_soon\|blocked\|all` |

Not URL-backed (intentional): Add/Import/Edit modals, onboarding More menu, preboarding config overlay, 360 jump-nav scroll position, Organization Advanced toggle when the section is Structure.

---

## Performance / perceived speed

- Phase 2 cached paint is unchanged: return visits skip `PageSkeleton` when the chunk is loaded; pages still unmount.
- Employees, 360, Onboarding, Inbox, Preboarding, and Probation no longer replace painted content with a full-page skeleton on refetch or filter change.
- Preboarding/Probation loaders use refs so filter/soft-refresh does not retrigger a remount loop.
- New chrome motion is 150ms color/opacity only.

---

## EN / AR / RTL

- Every migrated People surface already set `dir` from `useEmployees360Locale()`.
- 360 identity, employment actions, section titles, next-actions empty, and tenure are bilingual.
- Directory, Onboarding, Inbox, Preboarding, and Probation copy was already EN/AR; RTL layout is unchanged (`ms`/`me`, `text-start`).
- Remaining mixed English in some 360 module card details (attendance stat labels, a few leave/document strings) is noted below — not a new source of truth.

---

## Surface Registry migration status

| Surface id | Status |
| --- | --- |
| `page.employees` | canonical · Phase 5 |
| `detail.employees.profile` | canonical · new |
| `page.workforce` | canonical · Phase 5 (`?tab=`) |
| `page.onboarding` | canonical · Phase 5 |
| `page.preboarding` | canonical · Phase 5 (authority still frozen) |
| `page.probation` | canonical · Phase 5 (authority still frozen) |
| `page.inbox` | canonical · Phase 5 |
| `tab.workforce.*` / `tab.onboarding.*` / `tab.preboarding.*` / `tab.probation.*` / `tab.inbox.*` | query-backed |

Census: **34 pages, 34 nav items**. Recruiting, remaining enterprise modules, and Settings stay unmigrated.

---

## Tests

- `PeoplePhase5Contract.test.ts` (new)
- `dashboardNavigation.test.ts` (People URL chrome + workforce alias)
- `hrWebInteractionPerf.audit.test.ts` (People URL backing)
- `hrWebSurfaceRegistry.contract.test.ts`
- Employees directory / 360 closure / Onboarding Wave 1 / Needs Attention Wave 1 / Organization Wave 1 / Action Inbox Wave 1
- Leave / Shifts / Payroll Wave 1 (Phase 4 still green)
- `run-hr-web-surface-census.cjs` → PASS

---

## Remaining issues

- Recruiting / remaining enterprise / Settings not migrated (Phase 6+). Palette still unfrozen.
- Employee 360 documents card still sits after payroll in the DOM; jump nav lists documents with the record IA. Do not add fields the backend does not publish.
- Some 360 module-card strings remain English-only (attendance Present/Late/Absent labels, a few leave/document lines).
- Inbox presentation filters still classify rows with existing client label/severity helpers. Totals for All prefer `summary.total`; no new approvals model.
- Attendance capture tabs and Shifts inner panels remain local (Phase 4).
- Leave Active switch with history status can still double-push history (Phase 4 leftover).
- `tsc -b` may still report pre-existing Benefits/ER errors.

Do not deploy production. Do not start the next migration phase unless explicitly approved.
