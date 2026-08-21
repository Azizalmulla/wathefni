# OctoHR HR Web Product UX Overhaul — Phase 6

**Enterprise Flagship UX Migration**  
As of 2026-08-21 · Performance/OKRs, Talent (mapping/succession/mobility), Learning, Benefits, Employee Relations, Engagement, Compensation Planning, Workforce Planning, Job Architecture, Governed HR Intelligence · no Recruiting/pre-hiring · no Settings · no palette freeze · no production deploy

Phase 5 checkpoint: `ce47afab` on `authority-cutover` (pushed).

---

## Verdict

The enterprise batch now shares the Phase 3–5 interaction language (canonical `HrPageHeader`, `HrSurfaceTabs`, ResourceState, semantic tokens, URL-backed operator chrome, cached paint) **without** collapsing Performance or Talent into generic admin tables, and without recreating KPI math, 9-box scoring, benefits/payroll deductions, ER outcomes, or planning formulas in the frontend.

Backend remains authoritative for workflows, calculations, `allowed_actions`, permissions, module gates, and intelligence freshness/suppression/drill. Mutations still wait for the server. Palette is not locked.

---

## UX changes by surface

### Performance / OKRs

- Shell owns the page title (`HrPageHeader` density=`page`). Inner duplicate title removed.
- Goals / Reviews / Calibration / Development stay distinct workspaces behind `HrSurfaceTabs`. Calibration remains permission-gated.
- Overview still presents the active OKR cycle, review cycle, and published counts — not a people table.
- Progress, rollup, ratings, and sealing stay backend. Talent / HiPo / 9-box vocabulary remains forbidden here.
- Soft-keep: refetch does not blank a painted workspace.

### Talent Intelligence / Mapping / Succession / Mobility

- Same shared chrome. Tabs still include people, reviews, succession, mobility, derived 9-box, models, role fit, and talent map.
- 9-box remains a derived visualization, not an authoring checklist. There is still no universal talent score.
- Distinct from Performance and from recruiting `talent_pool`.

### Learning

- Catalog / assignments / sessions / certifications / requests / history stay the existing authoring workflows.
- Boundary copy kept: completion does not close development plans.
- Shared tabs + ghost refresh. Soft-keep on workspace payload.

### Benefits

- Plans / enrollment / coverage / contributions / history unchanged in meaning.
- Eligible ≠ enrolled ≠ coverage ≠ payroll deduction remains a displayed boundary, not a frontend calculator.

### Employee Relations

- Overview / cases / detail / my-work / history preserved. Investigation and decision still go through `allowed_actions` APIs.
- Opening a case now URL-backs `?tab=detail&q={case_id}`.

### Engagement

- Surveys / results / actions / history preserved. Below-threshold suppression still comes from the backend (`results.suppressed`).
- Opening results URL-backs `?tab=results&q={campaign_id}`.
- Honesty lines kept (not generic BI).

### Compensation Planning

- Worksheet / calibration / approvals / finalized / history preserved. Amounts stay backend money authority.
- Opening a cycle URL-backs `?tab=worksheet&q={cycle_id}`.
- KWD-only and job-architecture-required notes kept.

### Workforce Planning

- Plan / scenarios / demand / cost / approvals / execution / history preserved.
- Planned headcount is still not actual headcount; planned cost is still not payroll.

### Job Architecture

- Catalog / grades / paths / mappings preserved. Career edges are still not eligibility. Not recruiting job descriptions.

### Governed HR Intelligence

- Shell title is the existing Analytics destination; the workspace keeps the governed-KPI subtitle.
- Families and published metrics still render from bootstrap/overview. Metric cards no longer use hover-translate or cream hex.
- Detail drawer is URL-backed via `?q={semantic_key}`. Refresh/back restores the same metric and re-runs governed evaluate/trend/drill — the UI does not compute KPIs.
- Freshness, `suppressed` / `insufficient_data` / blocked states, and drill re-authorization stay backend-displayed.
- Ops Attention remains a separate inbox link, not mixed into intelligence.

---

## Shared primitives added/changed

No new primitives. Phase 6 reused:

- `HrPageHeader` (App shell, `density=page`) via `isEnterpriseFlagshipPage`
- `HrSurfaceTabs` (150ms color/opacity only)
- `useUrlBackedTab` (already present) + `useUrlBackedParam` for detail keys
- Semantic tokens on Intelligence chrome (drawer, overlay, trend bars, card hover)

---

## Deep links / URL state

| Chrome | URL |
| --- | --- |
| Performance tabs | `?page=performance&tab=overview\|goals\|reviews\|calibration\|development` |
| Talent tabs | `?page=talent&tab=overview\|people\|reviews\|succession\|mobility\|ninebox\|models\|rolefit\|map` |
| Learning tabs | `?page=learning&tab=overview\|catalog\|assignments\|…` |
| Benefits tabs | `?page=benefits&tab=overview\|plans\|enrollment\|…` |
| ER tabs + case | `?page=employee-relations&tab=detail&q={case_id}` |
| Engagement results | `?page=engagement&tab=results&q={campaign_id}` |
| Comp worksheet | `?page=compensation-planning&tab=worksheet&q={cycle_id}` |
| Workforce planning tabs | `?page=workforce-planning&tab=overview\|plan\|scenarios\|…` |
| Job architecture tabs | `?page=job-architecture&tab=overview\|catalog\|grades\|paths\|mappings` |
| Intelligence metric | `?page=analytics&q={semantic_key}` |

Not URL-backed (intentional): authoring forms, local inner panel filters, Intelligence segment values, saved-view name, 9-box config picker internals, recruiting/Settings chrome.

---

## Performance / perceived speed

- Phase 2 cached paint is unchanged: return visits skip `PageSkeleton` when the chunk is loaded.
- Workspace-level refetch no longer sets cold `loading` when a payload is already painted, so ResourceState does not replace the page with a skeleton.
- Intelligence refresh uses the existing soft `refreshing` path and keeps bootstrap/overview painted.
- New chrome motion is 150ms color/opacity only (no card translate/shadow).

---

## EN / AR / RTL

- Existing bilingual `copy(isAr)` / locale dir on each workspace is unchanged.
- Duplicate inner titles removed so the App `HrPageHeader` is the single EN/AR page title.
- Boundary/honesty strings that are unique vs the App subtitle were kept (Learning/Benefits/ER/Engagement/Comp/Workforce Planning, Intelligence methodology).

---

## Surface Registry

Pages marked `canonical` with Phase 6 notes:

`page.performance`, `page.talent`, `page.learning`, `page.benefits`, `page.employee-relations`, `page.engagement`, `page.compensation-planning`, `page.workforce-planning`, `page.job-architecture`, `page.analytics`

Nested workspace tabs for those pages are `canonical` + `url_state: query`. New nested surface:

- `drawer.analytics.metric` → `/dashboard?page=analytics&q={semantic_key}`

Census: **34 pages, 34 nav items** (unchanged). Recruiting and Settings remain unmigrated.

---

## Tests

Passed:

- `EnterprisePhase6Contract.test.ts` (new)
- `dashboardNavigation.test.ts` (enterprise `q` write)
- `hrWebInteractionPerf.audit.test.ts` (metric/case/campaign/cycle URL)
- `hrWebSurfaceRegistry.contract.test.ts`
- `OperationalPhase4Contract.test.ts` / `PeoplePhase5Contract.test.ts` (Recruiting/Settings still not restyled)
- `TalentWorkspace.test.tsx` (tabs are `role=tab`)
- `resourceFailureStates.test.tsx`
- `IntelligenceSurfacesContract.test.ts`
- `AnalyticsWave1Contract.test.ts` / `analyticsAttentionWave1.test.ts` (fallback Analytics page untouched)
- `run-hr-web-surface-census.cjs` → PASS (34/34)

---

## Remaining issues

- Recruiting / pre-hiring and Settings are not in this phase.
- Shared `Button` still uses cream hex and hover-translate; not restyled here (would affect Recruiting too).
- Inner tab panels (Performance goals, Talent people/nine-box, etc.) still cold-load on first visit of that tab; only the workspace payload is soft-kept.
- Intelligence fallback `AnalyticsPage` remains for the gated-off path; it was not visually migrated.
- Palette is not frozen.
- No production deploy.
