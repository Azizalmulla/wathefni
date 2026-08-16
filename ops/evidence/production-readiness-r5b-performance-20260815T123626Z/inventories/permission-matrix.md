# R5B permission matrix

Menu visibility is not proof. Direct API tests in `smoke-test-r5b-performance-surface-db.py` cover the rows below.

| Actor | Permissions | Allowed | Denied (proved) |
|---|---|---|---|
| Unauthenticated | none | — | GET `/dashboard/performance/workspace` 401/403; GET `/app/performance` 401/403/503 |
| Employee self | employee feature `performance` | Own workspace, goals, progress on owned subjects, self-review, assigned 360, own check-ins, own development | Other employees' objectives (404), others' progress (403 `progress_not_owned`), manager reviews, calibration, Talent |
| Manager (empty scope) | `performance.read` (+ manage for writes) | Empty lists (fail-closed) | Company-wide goals, calibration, cycle launch |
| Manager (in scope) | `performance.read`, `performance.manage` | Team goals, review queue, check-ins, development for scoped keys | Out-of-scope employees, cycle admin, calibration unless `performance.calibrate`, raw 360 identities without `performance.sensitive` |
| HR Performance operator | `performance.read`, `performance.manage` | Workspace, goals, reviews, check-ins, development, cycle create/configure/launch/close | Calibration adjust/lock without `performance.calibrate`; Talent |
| Cycle admin | HR role + `performance.manage` | Scales, templates, cycle configure / launch / close | Manager with manage cannot launch (`cycle_admin_required`) |
| Calibration participant | `performance.calibrate` | Session list/detail, adjust, lock | Unauthorized actor 403 |
| Sensitive final / 360 | `performance.sensitive` | Raw 360 identities when config allows | Without perm: 403 `sensitive_360_permission_required`; employee never sees identities when anonymous |
| Setup admin | Setup policy PATCH `wave4_performance_*` | Enable / disable Performance policies after R5B | Talent / Wave 6 PATCH still 409 `capability_not_customer_enableable` |

## Role mapping in HTTP

`performance_http._role`:

- `owner` / `hr_admin` / `hr_manager` / `admin` → HR
- `manager` → manager (scoped)
- `performance.calibrate` or `performance.manage` without manager role → HR
- Employee routes use `employee_app_context` + `require_employee_app_feature("performance")`

`context_permissions` only returns perms when `permission_authority == "backend_current"` and subject user/company match.

## Catalog / entitlement

- SKU `performance` in `MODULE_CATALOG` (order 155, audience `employee`, `app_surface_key="performance"`)
- Talent is not a catalog SKU
- Disabled Performance: nav disappears, new work blocked, history preserved, deep links fail cleanly, no new Performance notifications (R4 `flow=performance` suppression)
