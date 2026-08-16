# R5B Web / App / Mobile convergence

All three clients read the same C1–C4 authorities through `performance_http` + `performance_surfaces`. No client-side progress, status, or rating math.

| Concern | HR Web | Employee App | HR Mobile |
|---|---|---|---|
| Workspace summary | GET `/dashboard/performance/workspace` | GET `/app/performance` (calibration stripped) | Queue counts via `/dashboard/mobile/performance` |
| Goals | Create / KR / activate / history | Own list + detail + progress | Not cloned |
| Progress | POST `/dashboard/performance/progress` | POST `/app/performance/progress` (owned) | — |
| Reviews | Cycle admin + all layers | Self + assigned 360 only | Pending queue + submit |
| Calibration | Authorized tab only | Hidden | Hidden |
| Development | Create / advance | Own list | — |
| Check-ins | Create / complete | Own list | Optional future; not required for enable |
| Talent vocabulary | Honesty copy only; no product fields | `talentOff` EN/AR | None |
| Truth states | `ResourceState` / `resolveListDataState` | query error ≠ empty; `FeatureUnavailableState` | same R4 contract |
| Auth | Bearer + dashboard context | Bearer + employee context | Operator mobile + dashboard context |

Agreement proved: surface rollup == C1 `objective_rollup` for the same objective; employee and HR see the same objective/KR rows; review layers remain distinct across close.
