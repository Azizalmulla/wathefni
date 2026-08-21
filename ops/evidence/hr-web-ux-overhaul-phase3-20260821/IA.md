# OctoHR HR Web Product UX Overhaul — Phase 3 IA

**Overview Reference Experience — information architecture only**  
As of 2026-08-21 · no visual rewrite yet · no other-module redesign · no palette freeze

Phase 2 checkpoint: `1c87daa9` `feat(hr-web): lock sidebar destinations and split post-hire navigation` on `origin/authority-cutover`.

This note is the stop-before-reskin contract. Implementation: `REPORT.md` in this folder (2026-08-21).

---

## Verdict

Overview is a **hiring home** today. Phase 3 makes it the first **canonical OctoHR surface**: attention, approvals, workforce signals, and key metrics, still entirely backend-owned.

No new business truth. No frontend formulas. Empty bands omit. Capability still decides who sees Overview at all (payroll-only composition stays excluded).

---

## Current audit (`OverviewPage.tsx`)

| Region | Authority | Keep | Drop / change |
| --- | --- | --- | --- |
| Setup readiness | `GET /dashboard/setup/readiness` | When not ready + `users.manage` | Tokenize cream hex onto `HrSection` |
| Greeting + `totalAttention` | Client sum of review + follow-up + assessment | Greeting, date, locale, refresh | Drop the sum. Do not invent a replacement total |
| Three action cards | `prehire_overview.action_counts` | Backend people/application counts + destinations | Do not restack the same cohorts as giant pastel cards |
| Next priority role | `prehire_overview.role_priority` | One role-pressure surface | Merge with roles list; stop two competing heroes |
| Work queue mine/company | `GET /dashboard/prehire/overview/work-queue` | Canonical hiring attention list; Wave 2 contracts | Wrap `SoftKeepSurface`; keep `keepPreviousData` opt-out |
| Calendar peek | `calendar_projections.project_overview` | Context, not attention | Tokenize chrome only |
| Roles needing attention | `prehire_overview.role_next_steps` | Secondary list under role pressure | Same band as role_priority |
| `next_action` prop | `prehire_overview.next_action` | Unused already | Do not revive |

Preserve Wave 2: people vs applications, row `item.destination`, error ≠ empty, mine/company scope, no miswired “View all”.

Presentation mapping (labels, EN/AR, RTL) stays. Invented copy such as “Consider promoting this role” when the backend detail is empty does not.

---

## Proposed bands

Capability-gated. Omit when not offerable. Do not show a zeroed shell.

1. **Setup** — existing readiness steps; destinations are backend `action_page`.
2. **Header** — `HrPageHeader`. Greeting/date/locale/refresh. No client attention total. Eyebrow is company home, not “Hiring workspace”, but Overview remains offerable only when capability says so.
3. **Attention** — work-queue rows (mine/company) + **one** role-pressure surface (`role_priority`, with `role_next_steps` as “more”). Deep links are backend destinations only.
4. **Approvals** — existing `GET /dashboard/posthire/action-inbox` when `action_inbox.offerable`. Present `summary.total` and the already-ranked peek. Do **not** client-filter mixed inbox rows into a new “approvals” count. Open `?page=inbox` (or the item `deep_link`).
5. **Workforce signals** — `POST /dashboard/posthire/intelligence/overview` when analytics + C6 are offerable. Render C1 evaluations as published (`ok` / `stale` / `insufficient_data` / `suppressed`). Never label payroll money or unverified tiles current. Open `?page=analytics`.
6. **Key metrics** — backend metric blocks already published: hiring `action_counts` (people + applications), inbox `summary.by_stream` if offerable. Click = existing cohort destination. No client arithmetic.
7. **Calendar** — existing overview calendar projection when `overview.calendar` offerable.

Desktop: primary column = Attention + Approvals. Rail = Metrics + Signals + Calendar.  
Mobile: Setup → Header → Attention → Approvals → Metrics → Signals → Calendar.

---

## Authority and refresh

Do **not** add an Overview formula service.

| Band | Existing authority | Freshness |
| --- | --- | --- |
| Hiring attention + metrics | `prehire_overview` summary + work-queue | RQ `FRESHNESS_MS.workQueue` (60s, visibility-paused); summary default staleTime |
| Approvals peek | `action_inbox_wave1` | Same interval as Inbox (`FRESHNESS_MS.actionInbox`) |
| Workforce signals | C6 presents C1; projection tails domain events (`projection_from_domain_events`) | Existing intelligence overview fetch; honest stale/refreshing status |
| Calendar | `calendar_projections.project_overview` | `FRESHNESS_MS.calendarOverview` |

Frontend may invalidate those queries on Refresh. Frontend may not sum, blend, or re-rank them.

---

## Shared primitives Overview will freeze

Later modules migrate onto these. Overview is the first consumer.

| Primitive | Status | Contract |
| --- | --- | --- |
| `HrPageHeader` | New, from `PageIntro` + Overview header | eyebrow, title, description, actions, `dir`; one `h1` |
| `HrSection` | New | title, trailing, `SoftKeepSurface` wrapper, `ResourceState` slot |
| `HrMetricTile` | New | backend primary + `unitLabel` + optional hint; click = destination |
| `HrAttentionRow` | New | owner / due / next / source as published; one destination action |
| `HrDestinationButton` | New | navigates a backend destination; never computes a cohort |
| `SoftKeepSurface` | Exists | required on every Overview band |
| `ResourceState` | Exists | failure never looks empty; EN/AR |
| `--color-semantic-*` | Exists | no remaining Overview hex; do not freeze the palette |

Motion: ~160ms opacity/color. No hover translate, no decorative shadow, no layout-shifting skeleton.

EN/AR/RTL and responsive from the first Overview paint of this phase.

---

## Build order (after IA acceptance)

A. Extract primitives; restyle Overview chrome onto tokens without changing content.  
B. Collapse duplicated hiring cards into Attention + Metrics. Keep Wave 2 contracts green.  
C. Add Approvals peek from the existing inbox payload when offerable.  
D. Add C1 signal tiles only when the intelligence snapshot is offerable.

Do not redesign Jobs, Candidates, Leave, or enterprise workspaces in this phase.
