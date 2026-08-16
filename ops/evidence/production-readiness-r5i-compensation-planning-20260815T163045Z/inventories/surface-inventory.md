# R5I surface inventory

| Surface | Shipped | Notes |
|---|---|---|
| HTTP `/dashboard/compensation-planning` | Yes | Plus `/dashboard/posthire/compensation-planning` alias |
| HTTP `/app/compensation-planning` | No | Employee App not required |
| HTTP `/dashboard/mobile/compensation-planning` | No | HR Mobile not required |
| HR Web `CompensationPlanningWorkspace` | Yes | Overview / Worksheet / Calibration / Approvals / Finalized / History |
| Setup `Wave6CompensationPlanningPoliciesCard` | Yes | `#classic-wave6-comp-planning` |
| Manager scoped worksheet | Yes | Optional; empty scope = zero rows |
| Employee App Compensation | No | Intentionally omitted |
| HR Mobile Compensation | No | Intentionally omitted |
| People 360 Compensation section | No | `people_surface=false` |
