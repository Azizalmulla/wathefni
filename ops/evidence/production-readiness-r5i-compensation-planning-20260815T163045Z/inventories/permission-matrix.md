# R5I permission matrix

| Permission | Owner / HR admin / HR manager | Manager / team manager | Viewer |
|---|---|---|---|
| `comp_planning.read` | Yes | No | No |
| `comp_planning.manage` | Yes | No | No |
| `comp_planning.recommend` | Yes | No | No |
| `comp_planning.calibrate` | Yes | No | No |
| `comp_planning.approve` | Yes | No | No |
| `comp_planning.finalize` | Yes | No | No |
| `comp_planning.export` | Yes | No | No |
| `comp_planning.manager` | Yes | Yes only | No |

Ordinary HR (`leave.read`, `employees.read`) does not imply Compensation Planning access.

SOD: same `actor_key` cannot approve its own recommendation. Recommend-only cannot approve.
