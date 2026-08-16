# R5J permission matrix

| Permission | Owner / HR admin / HR manager | Manager / team manager | Viewer |
|---|---|---|---|
| `workforce_planning.read` | Yes | No | No |
| `workforce_planning.manage` | Yes | No | No |
| `workforce_planning.plan` | Yes | No | No |
| `workforce_planning.cost` | Yes | No | No |
| `workforce_planning.approve` | Yes | No | No |
| `workforce_planning.execute` | Yes | No | No |
| `workforce_planning.export` | Yes | No | No |
| `workforce_planning.manager` | Yes | Yes only | No |

Ordinary HR (`leave.read`, `employees.read`) does not imply Workforce Planning access.

Cost GET requires `workforce_planning.cost` (or manage). Approve requires `.approve`. Handoff / cancel require `.execute`. Export requires `.export`.

Managers are refused the administration workspace. Empty manager scope is fail-closed zero rows, never company-wide plans, restructuring, or cost-sensitive data.
