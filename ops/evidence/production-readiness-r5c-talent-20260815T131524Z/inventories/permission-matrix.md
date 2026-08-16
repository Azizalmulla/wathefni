# R5C permission matrix

Menu visibility is not proof. Direct API tests in `smoke-test-r5c-talent-surface-db.py` cover the rows below.

| Actor | Permissions | Allowed | Denied (proved) |
|---|---|---|---|
| Unauthenticated | none | — | GET `/dashboard/posthire/talent/workspace` 401/403; GET `/app/talent` 401/403/503 |
| Employee self | employee feature `talent` | Own workspace, aspirations, skills, mobility preference | Potential, HiPo, succession, 9-box, other employees' profiles |
| Manager (empty scope) | `talent.read` + `talent.manage` | Empty lists (fail-closed) | Company-wide profiles, HiPo without `talent.sensitive`, succession without `talent.succession` |
| Manager (in scope) | `talent.read`, `talent.manage` | Team profiles, permitted signals, development / mobility context | Out-of-scope employees, unrestricted HiPo, unrelated slates, compensation |
| HR without manage | `talent.read` only | Workspace read | POST `/profiles` 403 |
| HR Talent operator | `talent.read`, `talent.manage`, `talent.sensitive`, `talent.review`, `talent.succession` | Full workspace, potential, HiPo, reviews, slates | Cross-tenant profile 404 |
| Sensitive | `talent.sensitive` | Potential, HiPo, review lock | Manager default role does not include this |
| Review | `talent.review` | Create / prepare / start reviews | Manager default role does not include this |
| Succession | `talent.succession` | Critical roles, plans, nominations, slate | Manager GET `/succession` 403 |
| Setup admin | Setup policy PATCH `wave4_talent_*` | Enable / disable Talent after R5C | Wave 6 PATCH still 409 `capability_not_customer_enableable` |

## Role mapping in HTTP

`talent_http._role`:

- `owner` / `hr_admin` / `hr_manager` / `admin` → HR
- `manager` → manager (scoped)
- `talent.succession` or `talent.review` without manager role → HR
- Employee routes use `employee_app_context` + `require_employee_app_feature("talent")`

Writes require at least one of `talent.manage`, `talent.review`, `talent.succession`, `talent.sensitive`. Role alone is not enough.

`context_permissions` only returns perms when `permission_authority == "backend_current"` and subject user/company match.

## Catalog / entitlement

- SKU `talent` in `MODULE_CATALOG` (order 156, audience `employee`, `app_surface_key="talent"`)
- Recruiting `talent_pool` / `pre_hiring` remain a different SKU
- Disabled Talent: nav disappears, new work blocked, history preserved, deep links fail cleanly, no new Talent notifications (R4 `flow=talent` suppression)
