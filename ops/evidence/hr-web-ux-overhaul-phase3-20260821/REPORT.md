# OctoHR HR Web Product UX Overhaul — Phase 3

**Overview Reference Experience**  
As of 2026-08-21 · Overview only · no other-module redesign · no palette freeze

Approved IA: `ops/evidence/hr-web-ux-overhaul-phase3-20260821/IA.md`

---

## Verdict

Overview is now the first canonical OctoHR home. It is **module-composed**: recruiting bands hide when `pre_hiring` is off, and the remaining home (header, setup, approvals peek, signals, calendar) still works.

Numbers stay backend-owned. The client `totalAttention` sum is gone. Stale / suppressed / insufficient intelligence is not labelled current.

---

## What changed

1. **Shared primitives** (Overview is the first consumer; other modules are not migrated):
   - `HrPageHeader`
   - `HrSection` (wraps existing `SoftKeepSurface`)
   - `HrMetricTile`
   - `HrAttentionRow`
   - `HrDestinationButton`
2. **Seven capability-gated bands** on `OverviewPage`:
   1. Setup — only when workspace readiness is not ready
   2. Header — greeting, date, refresh, EN/AR (no invented total)
   3. Attention — work queue + one role-pressure surface
   4. Approvals — Action Inbox peek when `action_inbox.offerable`
   5. Workforce signals — C1 tiles from intelligence overview
   6. Key metrics — published hiring `action_counts` and inbox `by_stream` (no sums)
   7. Calendar — context peek, tokenized onto semantic aliases
3. **Capability**: when `pre_hiring` is off, `nav.overview` becomes offerable from remaining post-hire / calendar / approvals / signals bands and moves to the post-hire nav group. Restricted recruiters with recruiting on still do not get Overview nav.
4. Query hooks: `useActionInboxQuery`, `useIntelligenceOverviewQuery` with visibility-paused refetch (60s / 90s). Work-queue still opts out of `keepPreviousData`.

Desktop: Attention + Approvals in the primary column; metrics, signals, calendar on the rail. Mobile stacks in IA order.

---

## Primitives created

| Primitive | Path | Contract |
| --- | --- | --- |
| `HrPageHeader` | `apps/wathefni-dashboard/src/components/hr/HrPageHeader.tsx` | eyebrow, title (`h1`), description, actions, `dir` |
| `HrSection` | `.../HrSection.tsx` | title, trailing, `SoftKeepSurface`, ResourceState as children |
| `HrMetricTile` | `.../HrMetricTile.tsx` | backend primary + unit/hint; `current=false` hides live number |
| `HrAttentionRow` | `.../HrAttentionRow.tsx` | owner / due / next / source as published + destination action |
| `HrDestinationButton` | `.../HrDestinationButton.tsx` | 150ms color only; no hover translate / shadow |

Reused: `SoftKeepSurface`, `ResourceState`, `--color-semantic-*`.

---

## Backend / data gaps

- There is still **no single Overview home projection**. The page composes existing authorities (work-queue, action-inbox, intelligence overview, calendar overview, setup readiness, prehire summary). Refresh invalidates those queries; it does not invent a formula service.
- **Action Inbox** remains fail-closed on bootstrap `action_inbox.offerable`. Approvals peek does not appear from module entitlements alone.
- Inbox `summary` has **no dedicated approvals count**. Overview presents `summary.total` and the already-ranked peek; it does not client-filter mixed streams into a new total.
- Work-queue rows expose **destinations**, not `allowed_actions`. The row button is withheld when `destination.page` is missing.
- Intelligence C6 may be off while the analytics module is on. Overview **omits** the signals band on `intelligence_surfaces` / C1 entitlement errors rather than painting a fake KPI.
- Client poll (visibility-paused) is how the SPA learns projection freshness. Event-tailed projections stay on the backend.

---

## Interaction / performance

- Return visits still skip `PageSkeleton` when the Overview chunk is cached (Phase 2). Pages still unmount.
- Bands wrap `SoftKeepSurface`: first paint can ResourceState-load; refetch does not flash a skeleton.
- Work-queue scope still uses `startTransition` and opposite-scope prefetch; `keepPreviousData` stays opted out so mine/company cannot flash the wrong list.
- Inbox + intelligence use `keepPreviousData` + 60s/90s visibility refetch.
- Motion is 150ms color/opacity. No hover translate on Overview primitives.
- Refresh invalidates work-queue, inbox, intelligence, and calendar overview queries, plus the existing summary refresh.

---

## EN / AR / RTL

- Overview root `dir` follows locale. Header, sections, rows, metrics, inbox peek, signals, and calendar are bilingual.
- Runtime explorer still asserts `What needs attention today` (sr-only) and document `dir`/`lang` on AR.
- Responsive from the start: single column until `lg`, then 1.5 / 0.7 split.

---

## Tests

| Suite | Result |
| --- | --- |
| `OverviewWave2Contract.test.tsx` | pass |
| `OverviewPhase3Contract.test.tsx` | pass |
| `workspaceCapability.test.ts` | pass |
| `hrWebSurfaceRegistry.contract.test.ts` | pass |
| `hrWebSurfaceRuntimeExplorer.test.tsx` | pass |
| `RenderingStabilityWave2Contract.test.ts` | pass |
| `hrWebInteractionPerf.audit.test.ts` | pass |
| `actionInboxWave1.test.ts` | pass |
| `test_workspace_composition_matrix.py` | pass |
| `run-hr-web-surface-census.cjs` | `34 pages, 34 nav items` |

Dashboard `tsc -b` still reports **pre-existing** errors in other modules (Benefits/ER workspaces, unused imports). None in Overview primitives or `OverviewPage.tsx`.

---

## Stop

Other modules were not restyled. Jobs, Candidates, Leave, and enterprise workspaces still use their current chrome. They can migrate onto these primitives in a later phase.
