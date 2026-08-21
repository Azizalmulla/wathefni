# OctoHR HR Web Product UX Overhaul — Phase 7

**Recruiting / Pre-Hiring UX Migration**  
As of 2026-08-21 · Jobs, Requisitions, Candidates, Interviews, Assessments, Calendar, Ranking, Reports, Assistant · no Settings / Alerts / Activity · no palette freeze · no production deploy

Phase 6 checkpoint: `460ecb7e` on `authority-cutover`.

---

## Verdict

The recruiting/pre-hiring batch now shares the Phase 3–6 interaction language (canonical `HrPageHeader`, `HrSurfaceTabs` where the surface actually has tabs, ResourceState, semantic tokens, URL-backed operator chrome, cached paint) **without** collapsing Jobs, Ranking, Calendar, or Assistant into generic admin tables.

Backend remains authoritative for workflows, permissions, module gates, ranking methodology, assessment scoring, requisition SoD, interview states, and Assistant capabilities. The frontend does not invent ranking scores. Assistant remains a consumer of canonical domain APIs, not a second evaluator. Mutations still wait for the server. Palette is not locked.

---

## UX changes by surface

### Jobs

- Shell owns the page title (`HrPageHeader` density=`page`, Recruiting eyebrow). Openings stay an inventory with status tiles — not a generic table.
- Search and status filter are URL-backed (`?q=`, `?status=`). Refresh/back restore the same list chrome.
- Status chips and skeletons use semantic tokens. Create / Assistant-create / language actions stay.

### Requisitions

- Inner duplicate `h1` removed. Queue filters use `HrSurfaceTabs`.
- Tab and selected requisition are URL-backed (`?tab=`, `?q={requisition_id}`).
- Soft-keep: refresh does not blank a painted queue. Create / submit / approve / reject / SoD stay on existing APIs.

### Candidates

- Saved views (`all`, with a job, no job / talent pool, hired, archived, restricted) stay distinct from Talent Intelligence.
- View pills use `HrSurfaceTabs` (`role=tab`). Restricted remains permission-gated.
- Existing candidate filter URL authority, specialist drawer, and list personality are unchanged. Filter chips and avatars use semantic tokens.

### Interviews

- Status tiles stay (upcoming / needs feedback / completed). Primary tabs move onto `HrSurfaceTabs`. No-show / cancelled stay behind the More menu.
- Existing URL tabs plus search `?q=` now survive refresh. Interview states and allowed actions stay backend.
- Drawer / notes / video evidence chrome is tokenized; workflow is unchanged.

### Assessments

- Send / attempts / reports / needs-review use `HrSurfaceTabs`. Send-cohort chips inside Send stay.
- Report fetch still paints from cache (`cachedPayload`) and does not invent scores. Setup remains secondary and permission-gated.
- Attempt workspace / report drawer tokenized; inner report sections stay a dedicated assessment personality.

### Calendar

- Spatial board personality kept (no extra hierarchy eyebrow). Shell title + compact refresh icon remain.
- Day / week / month and the anchor date are URL-backed (`?tab=`, `?date=`). Scope (mine / team / company) stays a local preference.
- Interview-managed events still deep-link into Interviews.

### Ranking

- Evidence cards, eligibility copy, CV-primary / assessment-gated breakdown, and run/stale/failed/none-rankable states stay.
- Job selection remains URL-backed (`?position_code=`). The UI displays backend ranking components; it does not compute a score.
- Cream hex replaced with semantic tokens. Stale banner uses warning tokens.

### Reports

- Quiet leadership snapshot kept (overview / breakdowns / exports). Section titles stay; they are not flattened into one table.
- Count pills use `bg-semantic-ink` instead of cream hex. Metrics still come from the reports API.

### Assistant

- Chat personality kept (compact header, no Recruiting subtitle, history / new chat frame).
- Empty-state chips stay capability-catalog driven and untinted. Chip motion is 150ms color only.
- User bubbles use `bg-semantic-ink` instead of frozen gradient hex. Capabilities still load from `/dashboard/prehire/assistant/capabilities`.

---

## Shared primitives added/changed

No new primitives. Phase 7 reused:

- `HrPageHeader` via `isRecruitingPrehirePage` (chat/calendar use compact `density=hero` without the page rule)
- `HrSurfaceTabs` (count `0` now renders; 150ms color/opacity only)
- `useUrlBackedTab` / `useUrlBackedParam` for Requisitions and Calendar chrome
- Semantic tokens on recruiting page-local cream hex (Jobs, Candidates, Interviews, Assessments, Ranking, Reports, Assistant, assessment drawers)

`HrSurfaceTabs` is **not** forced onto Jobs tiles, Ranking evidence, Reports snapshot, or Calendar spatial controls.

---

## Deep links / URL state

| Chrome | URL |
| --- | --- |
| Jobs search / status | `?page=jobs&q=&status=` |
| Requisitions queue + row | `?page=requisitions&tab=attention\|draft\|…&q={requisition_id}` |
| Candidate views / filters | existing `?page=candidates&view=&…` |
| Interview tabs + search | `?page=interviews&tab=&q=&role=&date=&interviewer=` |
| Assessment tabs / cohort | existing `?page=assessments&tab=&assessment_cohort=` |
| Calendar view + date | `?page=calendar&tab=day\|week\|month&date=YYYY-MM-DD` |
| Ranking job | existing `?page=ranking&position_code=` |

Not URL-backed (intentional): Calendar mine/team/company scope (local preference), Jobs extra department/location/deadline filters, interview More-menu is still a tab value, Assistant chat transcript, Settings / Alerts / Activity.

---

## Performance / perceived speed

- Phase 2 cached paint is unchanged: return visits skip `PageSkeleton` when the chunk is loaded.
- Requisitions refresh no longer blanks a painted queue.
- Assessment report still paints cached payload before the network catch-up.
- Ranking / reports / interviews keep existing Query `keepPreviousData` behavior.
- New chrome motion is 150ms color/opacity only on shared tabs. Assistant empty chips no longer translate on hover.

---

## EN / AR / RTL

All nine surfaces keep existing bilingual copy and `dir`. Restricted / video / assessment-gated labels were not rewritten. Calendar day/week/month and Requisition queue labels stay EN+AR.

---

## Surface Registry migration status

| Page | Status |
| --- | --- |
| `ai`, `jobs`, `requisitions`, `candidates`, `interviews`, `calendar`, `assessments`, `ranking`, `reports` | `canonical` (Phase 7 notes) |
| Nested Requisition / Calendar tabs | `canonical`, `url_state=query` |
| Candidate views, Interview tabs, Assessment tabs | already `canonical` / query |
| Settings, Alerts (`notifications`), Activity | unchanged (`preserve`) |

Census: **34 pages, 34 nav items**. No extra sidebar destinations.

---

## Tests

- New: `apps/wathefni-dashboard/src/lib/RecruitingPhase7Contract.test.ts`
- Updated: Phase 4/5/6 Settings-only restyle guards; Reports/semantic/Assistant chip tokens; Interview Video/All as `role=tab`; Candidate view pills as `role=tab`
- Passing locally: Phase 4–7 contracts, surface registry, dashboardNavigation, Interviews, Jobs, Reports, Ranking, Assistant, Candidates table, Calendar Wave 1b/1c, Candidates Wave 3/4, Assessments UX, resource failure states, interaction perf audit, surface census

---

## Remaining issues (do not start next)

- Settings / Alerts / Activity are still on the generic App `h1` and cream-adjacent chrome.
- Shared `Button`, `Card`/`surface.tsx`, and form focus rings still use cream hex / hover-translate — left alone so Settings is not restyled by a global primitive change.
- Assistant composer send/stop still uses slight translate (chat control personality).
- Calendar scope remains localStorage, not URL.
- Inner tab panels can still cold-load on first visit of that tab.
- Palette remains unfrozen.

**Stop.** Do not start Settings / Alerts / Activity or the final palette phase unless the owner directs it.
