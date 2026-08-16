# R5J surface inventory

| Surface | Shipped | Notes |
|---|---|---|
| HTTP `/dashboard/workforce-planning` | Yes | Plus `/dashboard/posthire/workforce-planning` alias |
| HTTP `/app/workforce-planning` | No | Employee App not required |
| HTTP `/dashboard/mobile/workforce-planning` | No | HR Mobile not required |
| HR Web `WorkforcePlanningWorkspace` | Yes | Overview / Plan / Scenarios / Demand / Cost / Approvals / Execution / History |
| Setup `Wave6WorkforcePlanningPoliciesCard` | Yes | `#classic-wave6-workforce-planning` |
| Manager scoped demand / review / submit | Yes | Optional; empty scope = zero rows |
| Employee App Workforce Planning | No | Intentionally omitted |
| HR Mobile Workforce Planning | No | Intentionally omitted |
| People 360 Workforce Planning section | No | `people_surface=false` |
