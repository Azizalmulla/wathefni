# R5C API inventory

Company and actor identity come from authenticated `dashboard_context` / `employee_app_context` only. No `X-Company-Code` write authority. Distinct from recruiting `talent_pool`.

## Dashboard (canonical + alias)

Both prefixes are bound: `/dashboard/posthire/talent` and `/dashboard/talent`.

| Method | Path | Authority |
|---|---|---|
| GET | `/workspace` | workspace summary; manager empty scope → fail-closed zeros |
| GET | `/profiles` | governed profile list |
| POST | `/profiles` | ensure profile (`talent.manage` or other write perm) |
| GET | `/profiles/{employee_key}` | profile + distinct dimensions + history |
| GET | `/profiles/{employee_key}/history` | versioned facts / decisions |
| POST | `/evidence` | dimension fact (not a score) |
| POST | `/skills` | skill claim |
| GET / POST | `/potential/frameworks` | `talent.sensitive` |
| POST | `/potential/assessments` | explicit potential; `talent.sensitive` |
| POST | `/potential/assessments/{id}/accept` | `talent.sensitive` |
| POST | `/performance-evidence` | optional sealed Performance link; never becomes potential |
| POST | `/readiness` | readiness **observation** (not a nomination) |
| GET / POST | `/reviews` | `talent.review` |
| GET | `/reviews/{review_id}` | review + frozen population |
| POST | `/reviews/{review_id}/prepare` | freeze population |
| POST | `/reviews/{review_id}/start` | facilitator; notification `talent_review_requested` |
| POST | `/reviews/{review_id}/lock` | `talent.sensitive` |
| POST | `/hipo` | explicit HiPo; `talent.sensitive` |
| GET | `/succession` | `talent.succession` |
| POST | `/critical-roles` | target / critical role |
| POST | `/plans` | succession plan; notification `talent_succession_review_required` |
| GET | `/plans/{plan_id}` | multi-successor slate |
| POST | `/plans/{plan_id}/nominations` | target-specific readiness; does not notify the nominee |
| GET / POST | `/nine-box` | config list / create (HR) |
| POST | `/nine-box/project` | derived visualization only |
| GET | `/mobility/{employee_key}` | interest; recruiting handoff when enabled |
| GET | `/development/{employee_key}` | reused C3 development truth |

## Employee App

| Method | Path | Allowed |
|---|---|---|
| GET | `/app/talent` | stripped workspace (`potential_hidden`, `hipo_hidden`) |
| GET | `/app/talent/profile` | self profile only |
| POST | `/app/talent/aspirations` | employee-declared career interest |
| POST | `/app/talent/skills` | allowed skill claim |
| GET / POST | `/app/talent/mobility` | mobility preference; `talent_mobility_action` notification |

HR Mobile: none. No `/dashboard/mobile/talent` and no `/hr/talent`.
