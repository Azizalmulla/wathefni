# Before / after matrix

| Area | Before | After |
|---|---|---|
| Authority / page | Remap before bootstrap → Notifications flash | Sticky URL page until `authorityReady` |
| Nav | Empty then populate | Skeleton until authority ready (desktop + mobile rail) |
| Content gate | Full `LoadingDashboard` | Neutral `PageSkeleton` |
| Candidates | Empty flash behind feature flags | `listLoading` skeleton |
| Assessments URL | `openPage` overwrote surface tabs | Surface tabs preserved |
| Assessments chips | Needs-review late insert | Placeholder while attempts loading |
| Assistant | Loading flash every visit | Keep ready / show cached empty |
| Jobs tiles | Pop-in layout shift | Reserved tile shell |
| Calendar | Desktop week then mobile day | matchMedia-synced initial view |
| Overview scope | Always `mine` | localStorage + hint |
| Interviews video | Correct while loading | Correct only when `=== false` |
| Settings visibility | Default `shared_company` | Null / Loading until fetch |
| Ranking select | Empty until roster | Keep URL position option |
| Reports | Spinner/empty flash | Skeleton while pending |
| Post-hire filters | Stale data on param change | Clear + skeleton on loader change |
| Profile video flag | Required boolean early | `undefined` until authority ready |
