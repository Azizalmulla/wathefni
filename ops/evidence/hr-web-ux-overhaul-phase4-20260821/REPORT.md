# OctoHR HR Web Product UX Overhaul — Phase 4

**Operational Core UX Migration**  
As of 2026-08-21 · Leave, Attendance, Shifts, Payroll · no Employees / Recruiting / enterprise / Settings restyle · no palette freeze

---

## Verdict

Leave, Attendance, Shifts, and Payroll now share the Phase 3 chrome language (header hierarchy, surface tabs, section surfaces, ResourceState, semantic tokens) **without** collapsing their workflows into one table. Backend `allowed_actions`, temporal state, and money/leave calculations stay authoritative. There are no frontend leave/payroll formulas and no optimistic fake-success.

---

## UX changes by module

### Leave

- Page header is `HrPageHeader` (density `page`) from the shell. Module chrome is Active / History `HrSurfaceTabs` + File leave (primary) + refresh (secondary).
- Active queue (pending + upcoming) and History table are unchanged workflows: one row primary + More menu, dual-control still a separate authority, balances remain `enforced=false`.
- History status filter is URL-backed (`?status=`). Switching to Active clears it.
- Cold load uses `ResourceState`; return/refetch uses `SoftKeepSurface`. Refresh errors keep painted rows and show an error banner.

### Attendance

- Board-first IA preserved. Ops request → dual review → apply remains the only correction path. Capture / Import / Export stay behind collapsed Operations.
- Date chrome (Today / 7 days / month / custom) is URL-backed (`?date=` / `?date_end=`). `null` range still means backend today.
- Capture inner tabs (connectors / mapping / missing / conflicts) stay **local** so a refresh does not expand Operations.
- Board wraps `HrSection` + `SoftKeepSurface`. Attention strip still presents published row life-states, not a new formula.

### Shifts

- Schedule / Requests / Planning remain the three surfaces; Schedule is still first paint with one primary “Schedule a shift”.
- Surface tab is URL-backed (`?tab=`). Request/planning inner panels and org filters stay local (operator scope, not chrome).
- Existing board soft-keep (committed week, prefetch adjacent, no `setData(null)`) is unchanged.

### Payroll

- Run / Hours / Records tabs are URL-backed (`?tab=`). Records panels (payslips / close / statutory) use `?view=`.
- External money path still defaults to Run. Hours export stays secondary. No optimistic payroll mutate.

---

## Shared primitives added / changed

| Primitive | Change |
| --- | --- |
| `HrSurfaceTabs` | **New.** Color/opacity 150ms; optional backend/list `count`; no hover translate. |
| `HrPageHeader` | Added `density: 'hero' \| 'page'`. Operational core uses `page`. |
| `useUrlBackedTab` | Query keys: `tab` \| `view` \| `status` \| `date` \| `date_end`. `patchDashboardNavFilters` writes one history entry. |
| `useUrlBackedDateRange` | **New.** Attendance board range. |
| `StatusPill` | Neutral cream hex → semantic tokens. |
| `ResourceState` empty marker | Hex → `bg-semantic-accent`. |

Reused: `HrSection`, `SoftKeepSurface`, `ResourceState`, `Button` (mutations stay on Button, not `HrDestinationButton`).

---

## Performance / perceived speed

- Phase 2 cached paint is unchanged: return visits skip `PageSkeleton` when the chunk is loaded; pages still unmount.
- Leave and Attendance no longer replace painted content with a full-page skeleton on refetch or date/view change. `loading` remains cold-only (`refreshing && data === null`).
- Shifts board range soft-keep is preserved.
- Motion on new chrome is 150ms color/opacity only.

---

## Deep-link coverage

| Surface | URL |
| --- | --- |
| Leave active / history | `?page=leave&view=active\|history` |
| Leave history status | `?page=leave&view=history&status=approved` (etc.) |
| Attendance range | `?page=attendance&date=YYYY-MM-DD&date_end=YYYY-MM-DD` |
| Shifts surfaces | `?page=shifts&tab=schedule\|requests\|planning` |
| Payroll surfaces | `?page=payroll&tab=run\|hours\|records` |
| Payroll records panels | `?page=payroll&tab=records&view=payslips\|close\|statutory` |

Not URL-backed (intentional): Attendance capture tabs, Attendance Operations open, Shifts request/planning inner panels, Shifts org filters, Shifts day/week anchor.

---

## EN / AR / RTL

- All four roots already set `dir` / `lang` from locale. New tabs, headers, ResourceState, and date chrome use existing bilingual copy.
- Shell `HrPageHeader` for these pages follows `recruitingLocale` dir.
- No new English-only chrome.

---

## Tests

| Suite | Intent |
| --- | --- |
| `OperationalPhase4Contract.test.ts` | primitives, URL catalog, registry notes, no other-module restyle |
| `dashboardNavigation.test.ts` | leave status, attendance dates, payroll tab/view |
| `LeaveWave1Contract` / `AttendanceWave1Contract` / `ShiftsWave1Contract` / `PayrollWave1Contract` | preserved workflows; URL-backed tabs replace local `useState` |
| `hrWebInteractionPerf.audit.test.ts` | semantic StatusPill + operational URL backing |
| `hrWebSurfaceRegistry.contract.test.ts` | coverage including `tab.shifts.*` and `tab.payroll.*` |

---

## Remaining issues

- Employees, Recruiting, enterprise modules, and Settings were **not** migrated.
- Attendance capture tabs and Shifts inner request/planning panels stay local.
- Shifts day/week anchor is not in the URL (mobile still forces day view; URL week would fight that).
- There is still no shared DataTable — by design. Palette remains unfrozen (semantic aliases only).
- Payroll timesheet / export workspaces inside Records were not rewritten; they already demoted honesty and duplicate h2s in Wave 1.
- Dashboard `tsc -b` may still report pre-existing errors in Benefits/ER workspaces unrelated to this phase.

## Stop

Do not migrate Employees, Recruiting, enterprise modules, or Settings until the owner asks.
