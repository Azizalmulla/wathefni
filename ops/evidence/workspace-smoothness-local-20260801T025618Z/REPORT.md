# Workspace smoothness audit & fix — local qualification

**Stamp:** `20260801T025618Z`  
**Deployment:** **NO — local only (awaiting approval)**  
**Verdict:** **PASS** (local code + unit contracts; browser matrix documented as QA checklist before deploy)

## Goal

Remove visible flicker, layout jumps, wrong default tabs/scopes, duplicate loading states, and controls that change after first render — across Overview, Assistant, Jobs, Candidates, Interviews, Calendar, Assessments, Ranking, Reports, and post-hire — without changing URL/prefs/permissions/API semantics.

## Root causes found

| # | Cause | Symptom |
|---|---|---|
| 1 | Content gated on full dashboard bootstrap with `LoadingDashboard`, then remapped `activePage` before authority ready | Notifications / wrong page flash on hard refresh |
| 2 | Nav resolved with empty `enabled_modules` before bootstrap | Sidebar / mobile rail grew after modules loaded |
| 3 | Candidates list enabled only after feature flags; empty state painted first | Empty flash before rows |
| 4 | Assessments `writeDashboardUrl` cohort-derived `tab` overwrote surface tabs | `attempts`/`reports`/`needs_review` snapped to cohort tab |
| 5 | Needs-review chip mounted only after count arrived | Assessments tab row shifted |
| 6 | Interviews corrected video tab when `videoInterviewsEnabled` was still falsy-while-loading | Wrong tab then correct |
| 7 | Calendar assumed desktop `week` before matchMedia | Mobile week→day snap |
| 8 | Overview work-queue scope always started as `mine` | Scope control changed after prefs/hint |
| 9 | Assistant always set empty status to `loading` on every AI visit + module deps | Empty chrome spinner flash / remount flicker |
| 10 | Jobs status tiles appeared only after summary counts | Filters jumped down |
| 11 | Settings visibility select defaulted before fetch | Control value changed after load |
| 12 | Ranking position select empty until positions roster loaded | Control populated late |
| 13 | Reports spinner/empty before pending settled | Empty/wrong state flash |
| 14 | Post-hire `useModuleData` kept stale rows when loader identity changed | Leave/Compliance/Attendance showed wrong bucket while refreshing |
| 15 | Profile `videoInterviewsEnabled` required boolean before authority ready | Type/action flash risk |

## Pages affected

| Page | Fix |
|---|---|
| Shell / all | Sticky URL `page` until `authorityReady`; content `PageSkeleton`; nav skeleton (desktop + mobile rail) |
| Overview | Persist/restore work-queue scope (`wathefni_work_queue_scope`) |
| Assistant | Keep ready empty chrome while refreshing; drop module-state reload deps; show cached empty over spinner |
| Jobs | Reserve status-tile shell during first load |
| Candidates | `listLoading` → list skeleton (no empty flash); wait for `featuresReady` |
| Interviews | Correct video tab only when `videoInterviewsEnabled === false` |
| Calendar | Sync `isMobile`/`view` from matchMedia; persist scope |
| Assessments | Surface-tab URL parity in `writeDashboardUrl`; needs-review chip placeholder while loading |
| Ranking | Keep URL `rankPosition` option while roster loads |
| Reports | Skeleton while pending |
| Settings | `visibilityPolicy` null + disabled “Loading…” until fetch |
| Candidate profile | `videoInterviewsEnabled` optional until authority ready |
| Post-hire (Leave, Compliance, Attendance, Payroll, Shifts, …) | `useModuleData` clears data on loader change; request-id race guard; delivery strip waits for settle |

## Fixes made (key files)

- `App.tsx` — authority sticky page, nav skeletons, assessments URL, assistant reload, video flag gating
- `lib/query/useDashboardServerState.ts` — `bootstrapSettled`, `candidatesListPending`, `featuresReady`
- `pages/CandidatesPage.tsx`, `JobsPage.tsx`, `AssessmentsPage.tsx`, `AdminAIPage.tsx`, `ReportsPage.tsx`, `RankingPage.tsx`, `OverviewPage.tsx`, `InterviewsPage.tsx`, `SettingsPage.tsx`
- `components/CalendarShell.tsx`, `components/candidates/CandidateProfilePage.tsx`
- `posthire/PostHire.tsx` — `useModuleData` param-change loading
- `lib/workspaceSmoothness.test.ts` — smoothness contracts

## Tests & evidence

### Automated

```
npx tsc -b → EXIT 0
npx vitest run workspaceSmoothness + dashboardNavigation + assessmentCohorts + candidateFilterAuthority
→ 4 files / 30 tests passed
npm run build → dashboard-CmztGRNg.js
  sha256 3afa9f3d6114cbcab80280e5dd610b66893c91f94f974c08b80f67bb9ee0ed42
```

Build markers (`verify/local-markers.json`): nav skeleton, jobs status tiles, assistant empty chrome, calendar matchMedia, work-queue scope key, authority gate — all present.

Artifacts: `verify/tsc.txt`, `verify/smoothness-unit.txt`, `verify/build.log`, `verify/local-markers.json`, `before-after/MATRIX.md`

### Before → after (behavioral)

| Scenario | Before | After |
|---|---|---|
| Hard refresh deep-link | Wrong page / Notifications flash; empty nav then grow | Sticky URL page + nav skeleton until authority; content skeleton |
| Candidates first paint | Empty state then rows | List skeleton until features + apps ready |
| Assessments surface tab + openPage | Tab rewritten to cohort | Surface tabs preserved in URL write |
| Assistant re-visit empty chat | Spinner/chips flash | Prior empty chrome stays ready |
| Jobs first load | Filters jump when tiles appear | Tile shell reserved |
| Calendar mobile | week→day snap | day from first paint when mobile |
| Overview scope | Always mine then flip | Stored scope / hint-aware init |
| Post-hire Leave History / Compliance bucket | Stale rows under new chip | Skeleton until matching loader returns |
| Interviews video disabled | Tab corrected after mount | No correction until known `false` |

### Manual QA checklist (pre-deploy)

- [ ] Hard refresh on each listed page (EN + AR)
- [ ] In-app nav + browser back/forward
- [ ] Desktop + mobile widths
- [ ] Slow-3G / throttle: no wrong tab/scope flash; skeletons only
- [ ] Loading + error states (API fail) stay stable
- [ ] Post-hire Leave Active↔History and Compliance bucket chips

## PASS / FAIL

**PASS (local).** Do not deploy until approved.

## Out of scope / residual

- Conditional page remount on leave/return remains (by design); Assistant empty state is cached in App to mitigate.
- Jobs filter URL continuity not added (state-only filters preserved).
- Delivery strip can still appear once after settle when delivery is dirty (clean workspaces stay null→null).
- Unrelated pre-existing unit failure: `candidateProfilePresentation.test.ts` (“New” vs “—”) — not introduced by this pass.
