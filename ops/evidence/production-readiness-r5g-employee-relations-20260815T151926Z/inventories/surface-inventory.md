# R5G surface inventory

| Surface | Status |
|---|---|
| HTTP `/dashboard/employee-relations/...` + `/dashboard/posthire/employee-relations/...` | shipped |
| HTTP `/dashboard/mobile/employee-relations/...` | shipped (thin) |
| HTTP `/app/employee-relations/...` | not required; not shipped |
| HR Web sealed ER workspace (Overview / Cases / Case Detail / My Work / History-Audit) | shipped |
| Setup `Wave6EmployeeRelationsPoliciesCard` (`#classic-wave6-employee-relations`) | remounted |
| HR Mobile queue / scoped summary / acknowledge | shipped (authorized ER actors only) |
| Manager ER workspace | not required; dashboard routes 403 |
| Employee App ER case-management | not required; not shipped |
| People 360 ER section | not shipped (`people_surface=false`) |
