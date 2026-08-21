# OctoHR HR Web Product UX Overhaul — Phase 8

**Settings, Alerts & Delivery, Activity / Audit**  
As of 2026-08-21 · Settings, Alerts (`notifications`), Activity · no already-migrated product modules · no palette freeze · no production deploy

Phase 7 checkpoint: `6e777825` on `authority-cutover`.

---

## Verdict

Settings, Alerts & Delivery, and Activity now share the Phase 3–7 interaction language (canonical `HrPageHeader` with a Workspace eyebrow, `HrSurfaceTabs` where the surface actually has tabs, ResourceState, semantic tokens, URL-backed operator chrome, cached paint) **without** turning Settings into a dumping ground, inventing a second delivery path, or reinterpreting audit events.

Backend remains authoritative for permissions, module gates, integrations, channel/delivery configuration, and immutable audit records. Settings section IDs and configuration APIs are unchanged. Advanced stays admin-only recovery/diagnostics and is not merged into Integrations. Alerts still resolve through `resolveHrTask` and canonical outbound/HR-task feeds. Activity still reads `/dashboard/activity` and labels known action types for display only. Palette is not locked.

---

## UX changes by surface

### Settings

- Shell owns the page title (`HrPageHeader` density=`page`, Workspace eyebrow). Inner duplicate heading was already absent.
- Section chrome moves onto `HrSurfaceTabs` (`account`, `team`, `company`, `communications`, `integrations`, `advanced`). Unauthorized sections still fall back in-page.
- Sections remain URL-backed (`?tab=`). Configuration APIs, invite/role confirms, visibility policy, mailbox, email sending, and Setup Console ownership copy stay.
- Advanced is not merged into Integrations: Integrations remains day-to-day connectors; Advanced remains backup access, diagnostics, and the advanced integrations variant.
- Page-local cream/warning hex replaced with semantic tokens.

### Alerts & Delivery

- Shell owns the page title and purpose copy. Live issue counts stay in-page (`data-alerts-summary`).
- Needs follow-up / Failed / Retrying / Resolved / All move onto `HrSurfaceTabs` and are URL-backed (`?tab=`). Refresh/back restore the same filter.
- In-page Refresh remains so HR-task and outbound delivery feeds reload (App recruiting Refresh does not own those APIs).
- Soft-keep is unchanged: refresh does not blank a painted queue (`alertsPaintedRef`). Failures still render `ResourceState`, not an all-clear empty.
- Channel/delivery ownership copy stays. Resolve still goes through `resolveHrTask`. Issue rows use semantic surface tokens instead of cream shadow hex.

### Activity / Audit

- Shell owns the page title and purpose copy. Event count stays in-page (`data-activity-summary`).
- Timeline personality kept (date groups, who/what/affected/when/outcome, Details for technical evidence). No frontend-derived event meaning beyond existing display labels that mirror backend action types.
- Search, date range, and result filter are URL-backed (`?q=`, `?date=`, `?date_end=`, `?status=`). Actor, category, and action type stay local (backend-dynamic; not invented chrome keys).
- Soft-keep is unchanged: refresh does not blank a painted timeline. CSV export and read-only ownership copy stay.
- Sensitive-row cream hex replaced with semantic accent tokens. Motion is 150ms color only.

---

## Shared primitives added/changed

No new primitives. Phase 8 reused:

- `HrPageHeader` via `isWorkspaceOpsPage` (density=`page`, Workspace eyebrow — not Recruiting, not Post-Hire)
- `HrSurfaceTabs` on Settings sections and Alerts filters (150ms color/opacity only)
- `useUrlBackedTab` / `useUrlBackedParam` for Settings, Alerts, and Activity chrome
- Semantic tokens on page-local cream hex in Settings, Alerts, and Activity

`HrSurfaceTabs` is **not** forced onto the Activity timeline. Settings Cards remain configuration cards, not a generic admin table.

---

## Deep links / URL state

| Chrome | URL |
| --- | --- |
| Settings section | `?page=settings&tab=account\|team\|company\|communications\|integrations\|advanced` |
| Alerts filter | `?page=notifications&tab=needs_follow_up\|failed\|retrying\|resolved\|all` |
| Activity search / dates / result | `?page=activity&q=&date=&date_end=&status=` |

Not URL-backed (intentional): Activity actor / category / action type (backend-dynamic list chrome), Settings inner form fields, Alerts expanded issue id.

---

## Performance / perceived speed

- Phase 2 cached paint is unchanged: return visits skip `PageSkeleton` when the chunk is loaded.
- Alerts refresh still paints the previous issue list (`alertsPaintedRef`).
- Activity refresh still paints the previous timeline (`hasItemsRef`).
- New chrome motion is 150ms color/opacity only on shared tabs and Activity rows.
- Settings inner cards are not remounted on section URL restore beyond the existing section switch.

---

## EN / AR / RTL

All three surfaces keep existing bilingual copy and `dir`. Settings section labels, Alerts filter labels, Activity filter labels, forbidden/empty/error copy, and ownership honesty lines were not rewritten into a second language source.

---

## Surface Registry migration status

| Page | Status |
| --- | --- |
| `settings`, `notifications`, `activity` | `canonical` (Phase 8 notes) |
| Nested Settings sections | `canonical` except `settings.advanced` (`consolidate` — capability registry still names `settings.platform`; not merged into Integrations) |
| Nested Alerts filters | `canonical`, `url_state=query` |
| Already-migrated product modules (Overview, operational core, People, enterprise, recruiting) | unchanged |

Census: **34 pages, 34 nav items**. No extra sidebar destinations.

---

## Tests

- New: `apps/wathefni-dashboard/src/lib/WorkspacePhase8Contract.test.ts`
- Updated: Phase 4/5/6/7 “does not restyle Settings” guards removed now that Phase 8 owns those surfaces; Settings Wave 1 nav attribute; Activity Wave 1 status URL backing; Surface Registry / UX inventory notes
- Local results (2026-08-21): **15 files, 96 tests passed** when including `dashboardNavigation.test.ts` — Phase 4–8 contracts, Settings Wave 1, Alerts Wave 1, Activity Wave 1, NotificationsPage resource states, Settings email sending, surface registry, dashboard navigation, interaction perf audit, semantic color contract, alerts delivery access
- Surface census: **`HR_WEB_SURFACE_CENSUS_PASS  34 pages, 34 nav items`**

---

## Remaining issues (do not start next)

- Shared `Button`, `Card`/`surface.tsx`, and form focus rings still use cream hex / hover-translate — left alone so already-migrated modules are not restyled by a global primitive change.
- Compliance (if still on the leftover App `h1`) was out of Phase 8 scope.
- Activity actor / category / action type remain local, not URL-backed.
- Inner Settings/Alerts panels can still cold-load on first visit of that section.
- Palette remains unfrozen. Final launch qualification is not started.

**Stop.** Do not start the final palette / launch qualification phase unless the owner directs it.
