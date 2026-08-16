# R5J API inventory

Prefixes:

- `/dashboard/workforce-planning`
- `/dashboard/posthire/workforce-planning` (alias)

Not registered:

- `/app/workforce-planning`
- `/dashboard/mobile/workforce-planning`

| Family | Routes |
|---|---|
| Workspace | `GET /`, `GET /workspace` |
| Cycles / plans | `GET /plans`, `GET /cycles`, `POST /plans`, `GET /plans/{plan_id}` |
| Baseline | `GET /plans/{plan_id}/baseline`, `POST /plans/{plan_id}/baseline` |
| Scenarios | `GET /plans/{plan_id}/scenarios`, `POST /plans/{plan_id}/scenarios`, `POST /plans/{plan_id}/revise` |
| Assumptions | `GET /scenarios/{scenario_id}/assumptions`, `POST /assumptions` |
| Demand | `GET /demand`, `POST /demand` |
| Planned positions | `GET /scenarios/{scenario_id}/planned-positions` |
| Headcount projection | `GET /scenarios/{scenario_id}/projection`, `GET /scenarios/{scenario_id}/headcount` |
| Planned cost | `GET /scenarios/{scenario_id}/cost` |
| Gaps | `POST /gaps`, `GET /scenarios/{scenario_id}/gaps` |
| Comparison | `POST /compare` |
| Approvals | `POST /plans/{plan_id}/submit`, `POST /approve`, `GET /plans/{plan_id}/approvals` |
| Execution / handoff | `POST /handoffs`, `GET /plans/{plan_id}/handoffs`, `GET /plans/{plan_id}/execution`, `POST /handoffs/{handoff_id}/cancel` |
| Actual vs plan | `GET /actual-vs-plan` |
| History / version | `GET /history` |
| Export | `GET /plans/{plan_id}/export` |
| Assistant (read/explain) | `POST /assistant` |
| Manager (scoped) | `GET /manager`, `POST /manager/demand` |

Tenant / actor come from authenticated server context only. No client `X-Company-Code` write authority.
